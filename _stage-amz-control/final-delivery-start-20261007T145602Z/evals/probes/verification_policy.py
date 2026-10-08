#!/usr/bin/env python
"""真实分类 CLI 的独立配置反例；只写临时夹具，不修改 state/CI/登记权威。"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config/product-v2/verification.json"
WORKFLOW = ROOT / ".github/workflows/ci-cd.yml"
GUARD = ROOT / "tools/check_verification.py"
TARGET = "tools/verify_v2_2_3_intake_understanding.py"
TAG = re.compile(r"^\[FAIL\] ([A-Z_]+)\b", re.M)


def remove_ci(workflow: dict, entrypoint: str) -> None:
    changed = False
    for step in workflow["jobs"]["verify"]["steps"]:
        if "run" not in step:
            continue
        lines = step["run"].splitlines()
        kept = [line for line in lines if entrypoint not in line]
        if kept != lines:
            changed = True
            step["run"] = "\n".join(kept) + "\n"
    if not changed:
        raise RuntimeError(f"反例未改动 CI：{entrypoint}")


def add_ci(workflow: dict, command: str) -> None:
    workflow["jobs"]["verify"]["steps"].append({"name": "独立反例", "run": command})


def main() -> int:
    original = {path: path.read_bytes() for path in (REGISTRY, WORKFLOW, ROOT / "package.json")}
    baseline = json.loads(original[REGISTRY])
    workflow = yaml.safe_load(original[WORKFLOW])
    cases = []

    def case(code: str, mutate, tags: set[str]) -> None:
        registry_copy = copy.deepcopy(baseline)
        workflow_copy = copy.deepcopy(workflow)
        mutate(registry_copy, workflow_copy)
        if tags and registry_copy == baseline and workflow_copy == workflow:
            raise RuntimeError(f"{code} 没有真正注入漂移")
        cases.append((code, registry_copy, workflow_copy, tags))

    case("VPC01", lambda _r, _w: None, set())
    case("VPC02", lambda r, _w: r["entrypoints"].pop(TARGET),
         {"VCLASS_MISSING", "CI_UNCLASSIFIED"})
    case("VPC03", lambda _r, w: remove_ci(w, TARGET), {"CI_MISSING"})
    case("VPC04", lambda _r, w: remove_ci(w, "npm run check:types"), {"CI_MISSING"})
    case("VPC05", lambda _r, w: remove_ci(w, "npm run test:domain"), {"CI_MISSING"})
    live = "tools/verify_v2_2_2_semantic_provider.py"
    case("VPC06", lambda _r, w: add_ci(w, f"uv run python {live} --live"), {"CI_UNCLASSIFIED"})

    def enable_paid(registry, wf):
        registry["entrypoints"][live][1]["ci"] = True
        add_ci(wf, f"uv run python {live} --live")

    case("VPC07", enable_paid, {"CI_RESTRICTED", "CI_UNCLASSIFIED"})

    def enable_restricted(entrypoint: str):
        def mutate(registry, wf):
            registry["entrypoints"][entrypoint][0]["ci"] = True
            add_ci(wf, f"uv run python {entrypoint}")
        return mutate

    case("VPC08", enable_restricted("tools/verify_v2_ui_1_remote_entry.py"),
         {"CI_RESTRICTED", "CI_UNCLASSIFIED"})
    case("VPC09", enable_restricted("tools/verify_v2_7_1_regression.py"),
         {"CI_RESTRICTED", "CI_UNCLASSIFIED"})
    case("VPC10", lambda r, _w: r["human_gates"]["C17"].update(category="browser"), {"VCLASS_HUMAN"})
    case("VPC11", lambda r, _w: r["human_gates"].pop("C15"), {"VCLASS_HUMAN"})
    case("VPC12", lambda _r, w: add_ci(w, f"uv run python {TARGET}"), {"CI_DUPLICATE"})
    case("VPC13", lambda r, _w: r["entrypoints"][TARGET][0].update(category="unknown"),
         {"VCLASS_SCHEMA", "CI_UNCLASSIFIED"})
    case("VPC14", lambda r, _w: r["entrypoints"].update({"tools/verify_v2_ghost.py": [
        {"args": [], "category": "browser", "ci": False, "reason": "仅临时幽灵登记反例"}]}),
         {"VCLASS_GHOST"})

    failed = 0
    with tempfile.TemporaryDirectory(prefix="amz-verification-policy-") as temporary:
        fixture_root = Path(temporary)
        registry_path = fixture_root / "verification.json"
        workflow_path = fixture_root / "workflow.yml"
        for code, registry, wf, expected in cases:
            registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
            workflow_path.write_text(yaml.safe_dump(wf, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(GUARD), "--registry", str(registry_path),
                                     "--workflow", str(workflow_path)], cwd=ROOT,
                                    text=True, capture_output=True, encoding="utf-8", timeout=30)
            tags = set(TAG.findall(result.stdout))
            wanted_rc = 1 if expected else 0
            ok = result.returncode == wanted_rc and tags == expected
            print(f"[{'OK' if ok else 'FAIL'}] {code} rc={result.returncode} tags={sorted(tags)}")
            if not ok:
                failed += 1
                print(result.stdout)
                print(result.stderr)
    changed = [str(path.relative_to(ROOT)) for path, data in original.items()
               if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(data).digest()]
    if changed:
        failed += 1
        print(f"[FAIL] AUTHORITY_MUTATION {changed}")
    if failed:
        return 1
    print(f"[PASS] VERIFICATION-PROBES {len(cases)} 组；真实 CLI 拒绝遗漏/受限接线，未修改权威文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
