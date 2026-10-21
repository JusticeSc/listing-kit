#!/usr/bin/env python
"""真实分类 CLI 的独立配置反例；只写临时夹具，不修改 state/CI/登记权威。"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config/product-v2/verification.json"
WORKFLOW = ROOT / ".github/workflows/ci-cd.yml"
GUARD = ROOT / "tools/check_verification.py"
SELECTOR = ROOT / "tools/select_v2_checks.py"
TARGET = "tools/verify_v2_2_3_intake_understanding.py"
TAG = re.compile(r"^\[FAIL\] ([A-Z_]+)\b", re.M)
REGISTRY_SCHEMA = "amz-verification-registry/v1"

# 反例夹具只落在仓库内已忽略的 evals/.tmp/ 下：脚本要能相对 ROOT 被选择器执行。
FIXTURE_ROOT = ROOT / "evals" / ".tmp"


def selector_run(argv: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", "-B", str(SELECTOR), *argv], cwd=ROOT,
                          text=True, capture_output=True, encoding="utf-8", timeout=timeout)


def selector_json(paths: list[str], *extra: str):
    """跑真实选择 CLI（--emit-github），返回 (进程, 解析后的选择结果|None)。"""
    result = selector_run([*paths, *extra, "--emit-github"])
    data = None
    if result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            data = None
    return result, data


def fixture_workflow(run_lines: list[str]) -> str:
    return yaml.safe_dump({"jobs": {"verify": {"steps": [
        {"name": "反例夹具命令", "run": "\n".join(run_lines) + "\n"}]}}}, allow_unicode=True, sort_keys=False)


def fixture_registry(modes: dict) -> str:
    return json.dumps({"schema": REGISTRY_SCHEMA, "entrypoints": modes,
                       "human_gates": {"C17": {"category": "manual"}, "C15": {"category": "manual"}}},
                      ensure_ascii=False)


def fixture_script(marker: Path, rc: int, tag: str) -> str:
    return ("import pathlib, sys\n"
            f"pathlib.Path(r'{marker.as_posix()}').write_text('ran', encoding='utf-8')\n"
            f"print('[OK  ] FIXTURE {tag}')\n"
            f"sys.exit({rc})\n")


def read_result(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def receipt_argv_ok(entry: dict, script: str, extra: list[str]) -> bool:
    """凭据 argv 必须逐字等于所选模式的真实启动命令，不接受等价改写。"""
    return entry.get("argv") == ["uv", "run", "--locked", "python", script, *extra]


def _receipt_authority_cases(work: Path) -> dict:
    """在独立根目录跑真实CLI，错误保护也只能覆盖自有哨兵文件。"""
    for name in ("tools/select_v2_checks.py", "tools/check_verification.py", "src/console.py"):
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    marker = work / "started.marker"
    action = work / "tools" / "fixture_action.py"
    action.write_text(fixture_script(marker, 0, "AUTHORITY"), encoding="utf-8")
    workflow, registry = work / "workflow.yml", work / "registry.json"
    workflow.write_text(fixture_workflow(["uv run --locked python tools/fixture_action.py"]), encoding="utf-8")
    registry.write_text(fixture_registry({
        "tools/fixture_action.py": [{"args": [], "category": "control", "ci": True}]
    }), encoding="utf-8")

    def run(result: str) -> subprocess.CompletedProcess:
        return subprocess.run([
            sys.executable, "-X", "utf8", "-B", str(work / "tools" / "select_v2_checks.py"),
            "some/unknown/path.xyz", "--workflow", str(workflow), "--registry", str(registry),
            "--run", "--result-json", result,
        ], cwd=work, text=True, capture_output=True, encoding="utf-8", timeout=30)

    normal_path = work / "receipts" / "normal.json"
    positive = run(str(normal_path))
    normal = read_result(normal_path)
    positive_ok = (positive.returncode == 0 and marker.exists()
                   and isinstance(normal, dict) and normal.get("status") == "passed")
    paths = [
        "_working/amz-listing-kit-product-v2/state.md",
        "_working/amz-listing-kit-product-v2/budget-ledger.json",
        "docs/product-v2-refactor-plan.md", ".github/workflows/authority-guard.yml",
        "AGENTS.md", "README.md", ".gitattributes", ".gitignore",
        "receipts/../docs/product-v2-refactor-plan.md",
    ]
    if sys.platform == "win32":
        paths.append("_WORKING/AMZ-LISTING-KIT-PRODUCT-V2/STATE.MD")
    rows = []
    for name in paths:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        original = ("authority sentinel: " + name + "\n").encode("utf-8")
        target.write_bytes(original)
        marker.unlink(missing_ok=True)
        result = run(name)
        rows.append({"target": name, "returncode": result.returncode,
                     "started": marker.exists(), "preserved": target.read_bytes() == original,
                     "stdout": result.stdout, "stderr": result.stderr})
    return {"positive_ok": positive_ok, "positive_returncode": positive.returncode,
            "positive_stderr": positive.stderr, "protected": rows,
            "selector_sha256": hashlib.sha256((work / "tools/select_v2_checks.py").read_bytes()).hexdigest()}


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


def add_ci(workflow: dict, command: str, identity: str) -> None:
    workflow["jobs"]["verify"]["steps"].append({
        "name": "独立反例", "run": command,
        "if": f"contains(fromJSON(needs.changes.outputs.selected), '{identity}')",
    })


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
    case("VPC06", lambda _r, w: add_ci(w, f"uv run python {live} --live", f"{live} --live"), {"CI_UNCLASSIFIED"})

    def enable_paid(registry, wf):
        registry["entrypoints"][live][1]["ci"] = True
        add_ci(wf, f"uv run python {live} --live", f"{live} --live")

    case("VPC07", enable_paid, {"CI_RESTRICTED", "CI_UNCLASSIFIED"})

    def enable_restricted(entrypoint: str):
        def mutate(registry, wf):
            registry["entrypoints"][entrypoint][0]["ci"] = True
            add_ci(wf, f"uv run python {entrypoint}", entrypoint)
        return mutate

    case("VPC08", enable_restricted("tools/verify_v2_ui_1_remote_entry.py"),
         {"CI_RESTRICTED", "CI_UNCLASSIFIED"})
    case("VPC09", enable_restricted("tools/verify_v2_7_1_regression.py"),
         {"CI_RESTRICTED", "CI_UNCLASSIFIED"})
    case("VPC10", lambda r, _w: r["human_gates"]["C17"].update(category="browser"), {"VCLASS_HUMAN"})
    case("VPC11", lambda r, _w: r["human_gates"].pop("C15"), {"VCLASS_HUMAN"})
    case("VPC12", lambda _r, w: add_ci(w, f"uv run python {TARGET}", TARGET), {"CI_DUPLICATE"})
    case("VPC13", lambda r, _w: r["entrypoints"][TARGET][0].update(category="unknown"),
         {"VCLASS_SCHEMA", "CI_UNCLASSIFIED"})
    case("VPC14", lambda r, _w: r["entrypoints"].update({"tools/verify_v2_ghost.py": [
        {"args": [], "category": "browser", "ci": False, "reason": "仅临时幽灵登记反例"}]}),
         {"VCLASS_GHOST"})
    # ---- T5 选择器：只验真实选择/执行/跳过的后果，不做源文本自匹配绿灯 ----
    failed = 0
    t5_count = 0

    def judge(code: str, condition: bool, detail: str) -> None:
        nonlocal failed, t5_count
        t5_count += 1
        print(f"[{'OK  ' if condition else 'FAIL'}] {code} {detail}")
        if not condition:
            failed += 1

    base_result, base = selector_json([])
    judge("T5-FULL-BASELINE", base_result.returncode == 0 and bool(base),
          f"rc={base_result.returncode} full={base and base['full_count']}")
    full_selection = set(base["selected"]) if base else set()
    if not base:
        print(base_result.stdout)
        print(base_result.stderr)

    # 1) 普通说明：只选控制面，不启动浏览器消费者
    docs_result, docs = selector_json(["docs/drafts/requirements-analysis-2026-09-24.md"])
    judge("T5-DOC-PROSE",
          docs_result.returncode == 0 and bool(docs) and 0 < docs["selected_count"] < docs["full_count"]
          and not any("verify_v2" in item for item in docs["selected"]),
          f"rc={docs_result.returncode} selected={docs and docs['selected_count']}/"
          f"{docs and docs['full_count']}")

    # 公共读写/出站合同、锁与未知影响仍保守扩大；不是所有业务/策略变化都必须全选。
    for path in ("app/product_v2/session.ts", "app/server.py", "src/providers/v2_image.py",
                 "uv.lock", "package.json", "some/random/path.xyz"):
        result, data = selector_json([path])
        judge("T5-FULL-" + path.replace("/", "_").replace(".", "-"),
              result.returncode == 0 and bool(data) and set(data["selected"]) == full_selection,
              f"rc={result.returncode} selected={data and data['selected_count']}/{data and data['full_count']}")
    proof_path = "_stage-amz-control/b18-optional-figures-20261020/closeout-stop-20261020.md"
    proof_result, proof = selector_json([proof_path])
    judge("T5-PROOF-ONLY",
          proof_result.returncode == 0 and bool(proof)
          and proof["selected"] == ["tools/check_docs.py --no-run"]
          and not proof["container"] and not proof["browser"],
          f"rc={proof_result.returncode} selected={proof and proof['selected']}")
    ui_path = "app/product_v2/ui/generation-view.ts"
    ui_result, ui = selector_json([ui_path])
    # generation-view 独占 #task-list-mount / #shot-execution：凡真实读取这两个根的工具都在
    # 同一条依赖上。要求集从源码派生，避免手写名单再次静默漏掉新的验证器。
    paid_readers = {"tools/verify_v2_4_5_live_reference.py"}  # 付费/直连，离线集合不选它
    generation_readers = {
        "tools/" + path.name
        for path in (ROOT / "tools").glob("verify_v2*.py")
        if any(sel in path.read_text(encoding="utf-8")
               for sel in ("#task-list-mount", "#shot-execution"))
    } - paid_readers
    ui_required = ({"npm:check:types", "npm:build:frontend"}
                   | generation_readers
                   | {"tools/verify_v2_ui_2_interaction_visual.py",
                      "tools/verify_v2_ui_3_frontend.py",
                      "tools/verify_v2_6_4_accessibility.py"})
    judge("T5-GENERATION-CONSUMERS",
          ui_result.returncode == 0 and bool(ui) and ui_required <= set(ui["selected"])
          and "tools/verify_v2_1_3_project_package.py" not in ui["selected"]
          and ui["container"] and ui["browser"] and ui["frontend"],
          f"rc={ui_result.returncode} selected={ui and ui['selected_count']} "
          f"required={len(ui_required)} missing={sorted(ui_required - set(ui['selected'])) if ui else '?'}")
    verifier_result, verifier = selector_json(["tools/verify_v2_4_4_candidate_blob.py"])
    judge("T5-VERIFIER-OWN-CONSUMER",
          verifier_result.returncode == 0 and bool(verifier)
          and "tools/verify_v2_4_4_candidate_blob.py" in verifier["selected"]
          and "tools/verify_v2_1_3_project_package.py" not in verifier["selected"]
          and verifier["browser"] and not verifier["container"],
          f"rc={verifier_result.returncode} selected={verifier and verifier['selected_count']}")
    for path in ("evals/product-v2/harness/compare-panel.js",
                 "evals/product-v2/harness/compare-panel.html",
                 "config/product-v2/compare-contract.json",
                 "tools/verify_v2_5_3_compare_panel.py"):
        result, data = selector_json([path])
        judge("T5-COMPARE-OWN-CONSUMER-" + Path(path).name,
              result.returncode == 0 and bool(data)
              and {item for item in data["selected"] if item.startswith("tools/verify_v2")}
              == {"tools/verify_v2_5_3_compare_panel.py"}
              and {"npm:check:types", "npm:build:frontend"} <= set(data["selected"])
              and any(item.split()[0] == "pytest:tests/dev" for item in data["selected"])
              and next(index for index, item in enumerate(data["selected"])
                       if item.split()[0] == "pytest:tests/dev")
              < data["selected"].index("tools/verify_v2_5_3_compare_panel.py")
              and data["browser"] and data["frontend"] and not data["container"],
              f"rc={result.returncode} selected={data and data['selected']}")
    for path in ("evals/product-v2/harness/harness-api.js",
                 "evals/product-v2/harness/unknown-owner.js"):
        result, data = selector_json([path])
        judge("T5-HARNESS-CONSERVATIVE-" + Path(path).name,
              result.returncode == 0 and bool(data) and set(data["selected"]) == full_selection,
              f"rc={result.returncode} selected={data and data['selected_count']}/{data and data['full_count']}")
    compare_result, compare = selector_json(["evals/product-v2/harness/compare-panel.js"])
    compare_mixed_result, compare_mixed = selector_json([proof_path, "evals/product-v2/harness/compare-panel.js"])
    judge("T5-COMPARE-MIXED-UNION",
          compare_result.returncode == 0 and compare_mixed_result.returncode == 0
          and bool(compare) and bool(compare_mixed) and bool(proof)
          and set(compare_mixed["selected"]) == set(compare["selected"]) | set(proof["selected"]),
          f"rc={compare_mixed_result.returncode} selected={compare_mixed and compare_mixed['selected']}")
    mixed_result, mixed = selector_json([proof_path, ui_path])
    judge("T5-MIXED-UNION",
          mixed_result.returncode == 0 and bool(mixed) and bool(ui) and bool(proof)
          and set(mixed["selected"]) == set(proof["selected"]) | set(ui["selected"]),
          f"rc={mixed_result.returncode} selected={mixed and mixed['selected_count']}")
    rehearsal_registered, rehearsal_plan = selector_json(["tools/rehearse_v273_walkthrough.py"])
    judge("T5-REHEARSAL-MAINTENANCE",
          rehearsal_registered.returncode == 0 and bool(rehearsal_plan)
          and set(rehearsal_plan["selected"]) == {"tools/check_verification.py",
                                                  "evals/probes/verification_policy.py"}
          and not rehearsal_plan["browser"],
          f"rc={rehearsal_registered.returncode} selected={rehearsal_plan and rehearsal_plan['selected']}")
    missing_registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    missing_registry["entrypoints"].pop("tools/rehearse_v273_walkthrough.py", None)
    missing_registry_path = FIXTURE_ROOT / "verification-registry-without-rehearsal.json"
    missing_registry_path.parent.mkdir(parents=True, exist_ok=True)
    missing_registry_path.write_text(json.dumps(missing_registry, ensure_ascii=False),
                                     encoding="utf-8", newline="\n")
    rehearsal_result, _ = selector_json(["tools/rehearse_v273_walkthrough.py"],
                                        "--registry", str(missing_registry_path))
    missing_registry_path.unlink()
    judge("T5-REHEARSAL-NEEDS-INPUT",
          rehearsal_result.returncode == 2 and "SELECT-INPUT" in rehearsal_result.stdout,
          f"rc={rehearsal_result.returncode} 未登记/缺素材时不冒充走查已验")
    plan_result, plan = selector_json(["docs/product-v2-refactor-plan.md"])
    judge("T5-PLAN-STATE-CONSISTENCY",
          plan_result.returncode == 0 and bool(plan)
          and "evals/probes/project_state.py" in plan["selected"]
          and "tools/check_project_state.py" in plan["selected"] and not plan["container"],
          f"rc={plan_result.returncode} selected={plan and plan['selected']}")
    for path in ("tools/verify_v2_7_1_regression.py", "tools/verify_v2_removed_fixture.py"):
        result, data = selector_json([path])
        judge("T5-VERIFIER-MAINTENANCE-" + Path(path).stem,
              result.returncode == 0 and bool(data)
              and set(data["selected"]) == {"tools/check_verification.py", "evals/probes/verification_policy.py"}
              and path not in data["selected"] and not data["container"],
              f"rc={result.returncode} maintenance_only={data and data['selected']}")
    for path, expected_container in (
        ("config/product-v2/verification.json", False),
        ("tools/select_v2_checks.py", False),
        (".github/workflows/ci-cd.yml", True),
        ("tools/export_image_envelope_schema.py", True),
        ("tools/generate_image_envelope_validator.mjs", True),
        (".dockerignore", True),
        ("config/product-v2/providers.json", True),
        ("deploy/release-transaction.sh", True),
        ("tools/release_transaction_probe.py", True),
    ):
        result, data = selector_json([path])
        judge("T5-RELEASE-IMPACT-" + path.replace("/", "_"),
              result.returncode == 0 and bool(data) and data["container"] is expected_container,
              f"rc={result.returncode} container={data and data['container']}")
    invalid_base, _ = selector_json([], "--base", "0" * 40, "--head", "f" * 40)
    judge("T5-BAD-GIT-BASE",
          invalid_base.returncode == 2 and "SELECT-INPUT" in invalid_base.stdout,
          f"rc={invalid_base.returncode} 坏差量不能按证据-only跳过")
    # 受限模式不得被普通批次选中
    judge("T5-RESTRICTED-EXCLUDED",
          bool(base) and not any("--live" in item for item in base["selected"]),
          f"restricted_in_full={base and [i for i in base['selected'] if '--live' in i]}")

    # 3) 分类依赖 fail-closed：登记坏、命令清单坏 → 明确失败且一条命令都不执行
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="v2-select-fixture-", dir=str(FIXTURE_ROOT)))
    protected_result = ROOT / "tools" / ".tmp" / (workdir.name + "-receipt.json")
    try:
        def rel(path: Path) -> str:
            return path.relative_to(ROOT).as_posix()

        marker_ok = workdir / "ran-ok.marker"
        marker_paid = workdir / "ran-paid.marker"
        marker_first = workdir / "ran-first.marker"
        marker_second = workdir / "ran-second.marker"
        script_ok = workdir / "fixture_ok.py"
        script_paid = workdir / "fixture_paid.py"
        script_first = workdir / "fixture_first.py"
        script_second = workdir / "fixture_second.py"
        script_ok.write_text(fixture_script(marker_ok, 0, "OK"), encoding="utf-8")
        script_paid.write_text(fixture_script(marker_paid, 0, "PAID"), encoding="utf-8")
        script_first.write_text(fixture_script(marker_first, 3, "FIRST"), encoding="utf-8")
        script_second.write_text(fixture_script(marker_second, 0, "SECOND"), encoding="utf-8")

        ok_entry, paid_entry = rel(script_ok), rel(script_paid)
        ok_line = f"uv run --locked python {ok_entry}\n"
        paid_line = f"uv run --locked python {paid_entry} --live\n"
        valid_registry = fixture_registry({
            ok_entry: [{"args": [], "category": "browser", "ci": True}],
            paid_entry: [{"args": ["--live"], "category": "paid", "ci": False, "reason": "反例：真实计费模式"}],
        })
        bad_schema_text = fixture_registry({
            ok_entry: [{"args": [], "category": "browser", "ci": True}]}).replace(REGISTRY_SCHEMA, "amz-registry/other")
        bad_category_text = fixture_registry({
            ok_entry: [{"args": [], "category": "unknown", "ci": True}]})

        def fixture_files(name: str, workflow_text: str, registry_text: str):
            wf = workdir / f"{name}.workflow.yml"
            reg = workdir / f"{name}.registry.json"
            wf.write_text(workflow_text, encoding="utf-8")
            reg.write_text(registry_text, encoding="utf-8")
            return rel(wf), rel(reg)

        okay_workflow = fixture_workflow([ok_line.rstrip("\n")])
        wf_ok, reg_ok = fixture_files("run", okay_workflow, valid_registry)
        # 同一条（会真执行并写 marker 的）夹具命令配坏登记：这样才能证明「没执行」是登记校验拦下的，
        # 而不是夹具本身跑不动。工作流故意复用 wf_ok 的字节。
        wf_bad_schema, reg_bad_schema = fixture_files("badreg", okay_workflow, bad_schema_text)
        wf_bad_category, reg_bad_category = fixture_files("badcat", okay_workflow, bad_category_text)
        wf_paid, reg_paid = fixture_files("paid", fixture_workflow([paid_line.rstrip("\n"), ok_line.rstrip("\n")]),
                                          valid_registry)
        wf_unparsed, _ = fixture_files(
            "unparsed", fixture_workflow(["uv run --locked pytest tools/fixture_gateway_group.py"]), valid_registry)
        wf_first_fail, reg_first = fixture_files(
            "firstfail", fixture_workflow([f"uv run --locked python {rel(script_first)}",
                                           f"uv run --locked python {rel(script_second)}"]),
            fixture_registry({rel(script_first): [{"args": [], "category": "browser", "ci": True}],
                              rel(script_second): [{"args": [], "category": "browser", "ci": True}]}))

        def run_with(args: list[str]):
            return selector_run([*args, "--run"])

        def marker_state() -> dict:
            return {p.name: p.exists() for p in (marker_ok, marker_paid, marker_first, marker_second)}

        before = marker_state()
        # (a) 登记 schema 不对：必须明确失败，且不得执行任何命令
        bad = run_with(["some/unknown/path.xyz", "--workflow", wf_bad_schema, "--registry", reg_bad_schema])
        judge("T5-BAD-REGISTRY-SCHEMA",
              bad.returncode == 2 and "SELECT-INPUT" in bad.stdout and marker_state() == before,
              f"rc={bad.returncode} markers={marker_state()}")
        # (b) 分类取值非法：同上
        bad_cat = run_with(["some/unknown/path.xyz", "--workflow", wf_bad_category, "--registry", reg_bad_category])
        judge("T5-BAD-REGISTRY-CATEGORY",
              bad_cat.returncode == 2 and "SELECT-INPUT" in bad_cat.stdout and marker_state() == before,
              f"rc={bad_cat.returncode} markers={marker_state()}")
        # (c) 命令清单里出现解析器还不认识的验证命令：明确失败，不静默少跑
        unparsed = run_with(["some/unknown/path.xyz", "--workflow", wf_unparsed, "--registry", reg_ok])
        judge("T5-UNPARSED-COMMAND",
              unparsed.returncode == 2 and "SELECT-INPUT" in unparsed.stdout and marker_state() == before,
              f"rc={unparsed.returncode}")
        # 同一条可执行夹具，实际模式未变而选择条件拼错：必须拒绝，不能被skip洗成绿。
        wrong_route = yaml.safe_load(okay_workflow)
        wrong_route["jobs"]["changes"] = {"outputs": {"selected": "fixture"}}
        wrong_route["jobs"]["verify"]["steps"][0]["if"] = "contains(fromJSON(needs.changes.outputs.selected), 'wrong-mode')"
        wf_route, reg_route = fixture_files(
            "badroute", yaml.safe_dump(wrong_route), valid_registry)
        route_rejected = run_with(["some/unknown/path.xyz", "--workflow", wf_route, "--registry", reg_route])
        judge("T5-ROUTING-REFUSES-SILENT-SKIP",
              route_rejected.returncode == 2 and "CI_ROUTING" in route_rejected.stdout
              and marker_state() == before,
              f"rc={route_rejected.returncode} markers={marker_state()}")
        # (d) 正常夹具真跑：确认夹具本身有效（否则后面几条会假绿）
        good = run_with(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok])
        judge("T5-FIXTURE-EXECUTES",
              good.returncode == 0 and marker_ok.exists(),
              f"rc={good.returncode} marker_ok={marker_ok.exists()}")
        # (e) 首个失败保留真实退出码，后续命令不执行
        first_fail = run_with(["some/unknown/path.xyz", "--workflow", wf_first_fail, "--registry", reg_first])
        judge("T5-FIRST-FAIL-STOPS",
              first_fail.returncode == 3 and marker_first.exists() and not marker_second.exists(),
              f"rc={first_fail.returncode} first={marker_first.exists()} second={marker_second.exists()}")
        # (f) 受限（paid）模式不进选择结果，也不会被执行
        paid_result, paid_data = selector_json(["some/unknown/path.xyz", "--workflow", wf_paid, "--registry", reg_paid])
        judge("T5-PAID-MODE-EXCLUDED",
              paid_result.returncode == 0 and bool(paid_data)
              and paid_data["selected"] == [ok_entry] and paid_data["selected_count"] == 1,
              f"rc={paid_result.returncode} selected={paid_data and paid_data['selected']}")
        paid_run = run_with(["some/unknown/path.xyz", "--workflow", wf_paid, "--registry", reg_paid])
        judge("T5-PAID-NOT-EXECUTED",
              paid_run.returncode == 0 and marker_ok.exists() and not marker_paid.exists(),
              f"rc={paid_run.returncode} ok={marker_ok.exists()} paid={marker_paid.exists()}")
        # 精确模式准入：复用既有本地试验的独立 marker；坏项在后也不能先执行好项。
        for name in ("unknown-entry", "unknown-args", "not-approved", "duplicate-mode",
                     "restricted-approved", "invalid-ci", "mixed-plan", "duplicate-plan"):
            marker = workdir / f"{name}.marker"
            prefix_marker = workdir / f"{name}-prefix.marker"
            script = workdir / f"{name}.py"
            script.write_text(fixture_script(marker, 0, name), encoding="utf-8")
            entry = rel(script)
            approved = {"args": [], "category": "control", "ci": True}
            modes = [approved]
            command = f"uv run --locked python {entry}"
            entries = {ok_entry: [{"args": [], "category": "control", "ci": True}]}
            lines = [command]
            if name == "unknown-entry":
                modes = None
            elif name == "unknown-args":
                lines = [command + " --live"]
            elif name == "not-approved":
                modes = [{"args": [], "category": "control", "ci": False,
                          "reason": "独立反例：未批准执行"}]
            elif name == "duplicate-mode":
                modes = [approved, {"args": [], "category": "paid", "ci": False,
                                    "reason": "独立反例：同一模式分类冲突"}]
            elif name == "restricted-approved":
                modes = [{"args": [], "category": "paid", "ci": True}]
            elif name == "invalid-ci":
                modes = [{"args": [], "category": "control", "ci": "true"}]
            elif name == "mixed-plan":
                modes = None
                prefix_script = workdir / f"{name}-prefix.py"
                prefix_script.write_text(fixture_script(prefix_marker, 0, "PREFIX"), encoding="utf-8")
                prefix_entry = rel(prefix_script)
                entries[prefix_entry] = [approved]
                lines.insert(0, f"uv run --locked python {prefix_entry}")
            elif name == "duplicate-plan":
                lines.append(command)
            if modes is not None:
                entries[entry] = modes
            wf, reg = fixture_files(name, fixture_workflow(lines), fixture_registry(entries))
            before_markers = marker_state()
            rejected = run_with(["some/unknown/path.xyz", "--workflow", wf, "--registry", reg])
            judge("T5-EXACT-" + name.upper(),
                  rejected.returncode == 2 and "SELECT-INPUT" in rejected.stdout
                  and not marker.exists() and not prefix_marker.exists()
                  and marker_state() == before_markers,
                  f"rc={rejected.returncode} unapproved_executed={marker.exists()}")
        output_path = workdir / "github-output.txt"
        output_result, output_data = selector_json(
            [proof_path], "--github-output", str(output_path))
        outputs = dict(line.split("=", 1) for line in output_path.read_text(encoding="utf-8").splitlines())
        judge("T5-GITHUB-OUTPUT",
              output_result.returncode == 0 and bool(output_data)
              and json.loads(outputs["selected"]) == ["tools/check_docs.py --no-run"]
              and json.loads(outputs["container"]) is False
              and json.loads(outputs["browser"]) is False,
              f"rc={output_result.returncode} container={outputs.get('container')}")
        # ---- T5 执行凭据：成功/首失败/准入失败的原始结果与受测工作树身份 ----
        ok_result_path = workdir / "receipt-ok.json"
        ok_run = run_with(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok,
                           "--result-json", str(ok_result_path)])
        ok_receipt = read_result(ok_result_path)
        judge("T5-RECEIPT-PASSED",
              ok_run.returncode == 0 and isinstance(ok_receipt, dict)
              and ok_receipt.get("schema") == "amz-selector-result/v1"
              and ok_receipt.get("status") == "passed" and ok_receipt.get("first_failure_returncode") is None
              and ok_receipt.get("selection") == [ok_entry] and ok_receipt.get("not_executed") == []
              and len(ok_receipt.get("executed", [])) == 1
              and ok_receipt["executed"][0].get("returncode") == 0
              and ok_receipt["executed"][0].get("status") == "ok"
              and receipt_argv_ok(ok_receipt["executed"][0], ok_entry, [])
              and str(ok_receipt.get("started_at", "")).endswith("Z")
              and str(ok_receipt.get("finished_at", "")).endswith("Z")
              and str(ok_receipt["executed"][0].get("started_at", "")).endswith("Z"),
              f"rc={ok_run.returncode} status={ok_receipt and ok_receipt.get('status')}")
        fail7_marker_first = workdir / "ran-rc7-first.marker"
        fail7_marker_second = workdir / "ran-rc7-second.marker"
        fail7_first = workdir / "fixture_rc7_first.py"
        fail7_second = workdir / "fixture_rc7_second.py"
        fail7_first.write_text(fixture_script(fail7_marker_first, 7, "RC7-FIRST"), encoding="utf-8")
        fail7_second.write_text(fixture_script(fail7_marker_second, 0, "RC7-SECOND"), encoding="utf-8")
        wf_fail7, reg_fail7 = fixture_files(
            "rc7fail", fixture_workflow([f"uv run --locked python {rel(fail7_first)}",
                                         f"uv run --locked python {rel(fail7_second)}"]),
            fixture_registry({rel(fail7_first): [{"args": [], "category": "browser", "ci": True}],
                              rel(fail7_second): [{"args": [], "category": "browser", "ci": True}]}))
        fail7_result_path = workdir / "receipt-rc7.json"
        fail7 = run_with(["some/unknown/path.xyz", "--workflow", wf_fail7, "--registry", reg_fail7,
                          "--result-json", str(fail7_result_path)])
        fail7_receipt = read_result(fail7_result_path)
        judge("T5-RECEIPT-FIRST-FAIL-RC7",
              fail7.returncode == 7 and isinstance(fail7_receipt, dict)
              and fail7_receipt.get("status") == "failed"
              and fail7_receipt.get("first_failure_returncode") == 7
              and fail7_marker_first.exists() and not fail7_marker_second.exists()
              and len(fail7_receipt.get("executed", [])) == 1
              and fail7_receipt["executed"][0].get("returncode") == 7
              and fail7_receipt["executed"][0].get("status") == "failed"
              and receipt_argv_ok(fail7_receipt["executed"][0], rel(fail7_first), [])
              and fail7_receipt.get("not_executed") == [rel(fail7_second)]
              and str(fail7_receipt.get("started_at", "")).endswith("Z")
              and str(fail7_receipt.get("finished_at", "")).endswith("Z"),
              f"rc={fail7.returncode} second={fail7_marker_second.exists()}")
        trailing_marker = workdir / "trailing-good.marker"
        trailing_script = workdir / "trailing_good.py"
        trailing_script.write_text(fixture_script(trailing_marker, 0, "TRAILING"), encoding="utf-8")
        trailing_entry = rel(trailing_script)
        unapproved_entry = "tools/receipt_trailing_unapproved_probe.py"
        wf_trailing, reg_trailing = fixture_files(
            "trailing-unapproved",
            fixture_workflow([f"uv run --locked python {trailing_entry}",
                              f"uv run --locked python {unapproved_entry} --extra"]),
            fixture_registry({trailing_entry: [{"args": [], "category": "control", "ci": True}]}))
        trailing_result_path = workdir / "receipt-trailing.json"
        trailing = run_with(["some/unknown/path.xyz", "--workflow", wf_trailing, "--registry", reg_trailing,
                             "--result-json", str(trailing_result_path)])
        judge("T5-RECEIPT-UNAPPROVED-TRAILING",
              trailing.returncode == 2 and "SELECT-INPUT" in trailing.stdout
              and not trailing_marker.exists() and not trailing_result_path.exists(),
              f"rc={trailing.returncode} started={trailing_marker.exists()}")
        preview_result_path = workdir / "receipt-preview.json"
        marker_ok.unlink(missing_ok=True)
        preview_run = selector_run(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok,
                                    "--run", "--emit-github", "--result-json", str(preview_result_path)])
        preview_output_path = workdir / "preview-output.txt"
        github_run = selector_run(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok,
                                   "--run", "--github-output", str(preview_output_path),
                                   "--result-json", str(preview_result_path)])
        lone = selector_run(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok,
                             "--result-json", str(preview_result_path)])
        preview_reran = marker_ok.exists()
        marker_ok.write_text("ran", encoding="utf-8")
        judge("T5-RECEIPT-PREVIEW-AMBIGUITY",
              preview_run.returncode == 2 and "SELECT-INPUT" in preview_run.stdout
              and github_run.returncode == 2 and "SELECT-INPUT" in github_run.stdout
              and lone.returncode == 2 and "SELECT-INPUT" in lone.stdout
              and not preview_result_path.exists() and not preview_output_path.exists()
              and not preview_reran,
              f"rc={preview_run.returncode}/{github_run.returncode}/{lone.returncode}")
        marker_ok.unlink(missing_ok=True)
        overwrite_registry = run_with(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok,
                                       "--result-json", reg_ok])
        overwrite_workflow = run_with(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok,
                                       "--result-json", wf_ok])
        protected_arg = rel(protected_result)
        if sys.platform == "win32":
            protected_arg = protected_arg.upper()
        overwrite_source = run_with(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok,
                                     "--result-json", protected_arg])
        authority_cases = _receipt_authority_cases(workdir / "authority-root")
        authority_ok = authority_cases["positive_ok"] and all(
            row["returncode"] == 2 and not row["started"] and row["preserved"]
            for row in authority_cases["protected"])
        overwrite_reran = marker_ok.exists()
        marker_ok.write_text("ran", encoding="utf-8")
        judge("T5-RECEIPT-NO-OVERWRITE-AUTHORITY",
              overwrite_registry.returncode == 2 and "SELECT-INPUT" in overwrite_registry.stdout
              and overwrite_workflow.returncode == 2 and "SELECT-INPUT" in overwrite_workflow.stdout
              and overwrite_source.returncode == 2 and "SELECT-INPUT" in overwrite_source.stdout
              and not overwrite_reran and not protected_result.exists() and authority_ok,
              f"rc={overwrite_registry.returncode}/{overwrite_workflow.returncode}/{overwrite_source.returncode} "
              f"project_authorities={authority_ok}")
        write_fail_dir = workdir / "receipt-is-dir"
        write_fail_dir.mkdir(exist_ok=True)
        write_fail = run_with(["some/unknown/path.xyz", "--workflow", wf_ok, "--registry", reg_ok,
                               "--result-json", str(write_fail_dir)])
        judge("T5-RECEIPT-WRITE-FAIL-NOT-PASSED",
              write_fail.returncode == 1 and "SELECT-RESULT" in write_fail.stdout
              and "所选命令全部通过" not in write_fail.stdout,
              f"rc={write_fail.returncode}")
        write_fail7 = run_with(["some/unknown/path.xyz", "--workflow", wf_fail7, "--registry", reg_fail7,
                                "--result-json", str(write_fail_dir)])
        judge("T5-RECEIPT-WRITE-FAIL-KEEPS-RC7",
              write_fail7.returncode == 7 and fail7_marker_first.exists()
              and not fail7_marker_second.exists(),
              f"rc={write_fail7.returncode} second={fail7_marker_second.exists()}")
        snapshot = ok_receipt.get("source_before") if isinstance(ok_receipt, dict) else None
        after = ok_receipt.get("source_after") if isinstance(ok_receipt, dict) else None
        judge("T5-RECEIPT-SNAPSHOT-IDENTITY",
              isinstance(snapshot, dict) and snapshot.get("schema") == "amz-source-snapshot/v1"
              and isinstance(after, dict) and after.get("schema") == "amz-source-snapshot/v1"
              and snapshot.get("digest") and snapshot.get("files", 0) > 0
              and snapshot.get("scope", {}).get("dirs") and snapshot.get("scope", {}).get("root_files")
              and "tools/select_v2_checks.py" in snapshot.get("entries", {})
              and not any(name.startswith(("evals/product-v2/refactor/", "_working/", "_stage-amz-control/"))
                          for name in snapshot.get("entries", {}))
              and not any("/.tmp/" in name or name.endswith((".pyc", ".env")) for name in snapshot.get("entries", {})),
              f"files={snapshot and snapshot.get('files')}")
        sys.path.insert(0, str(ROOT / "tools"))
        from select_v2_checks import snapshot_source as real_snapshot_source
        snapshot_target = workdir / "source-root" / "tools" / "probe_source.py"
        snapshot_target.parent.mkdir(parents=True, exist_ok=True)
        snapshot_target.write_text("print('probe')\n", encoding="utf-8")
        snapshot_root = workdir / "source-root"
        first = real_snapshot_source(snapshot_root)
        proof_only = snapshot_root / "evals" / "product-v2" / "refactor" / "proof-only-probe.md"
        proof_only.parent.mkdir(parents=True, exist_ok=True)
        proof_only.write_text("receipt fixture\n", encoding="utf-8")
        second = real_snapshot_source(snapshot_root)
        snapshot_target.write_text("print('probe dirty')\n", encoding="utf-8")
        third = real_snapshot_source(snapshot_root)
        judge("T5-RECEIPT-DIRTY-SOURCE-VISIBLE",
              first.get("digest") == second.get("digest")
              and third.get("digest") != first.get("digest")
              and "tools/probe_source.py" in third.get("entries", {})
              and not any(name.startswith("evals/product-v2/refactor/") for name in second.get("entries", {})),
              f"proof_same={first.get('digest') == second.get('digest')} "
              f"dirty_changed={third.get('digest') != first.get('digest')}")
    finally:
        protected_result.unlink(missing_ok=True)
        shutil.rmtree(workdir, ignore_errors=True)


    with tempfile.TemporaryDirectory(prefix="amz-verification-policy-") as temporary:
        fixture_root = Path(temporary)
        registry_path = fixture_root / "verification.json"
        workflow_path = fixture_root / "workflow.yml"
        for code, registry, wf, expected in cases:
            registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
            workflow_path.write_text(yaml.safe_dump(wf, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result = subprocess.run([sys.executable, "-X", "utf8", "-B", str(GUARD), "--registry", str(registry_path),
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
    print(f"[PASS] VERIFICATION-PROBES {len(cases)} 组 + T5 选择/执行后果 {t5_count} 项；"
          f"真实 CLI 拒绝遗漏/受限接线，未修改权威文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
