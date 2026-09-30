#!/usr/bin/env python
"""Product V1 双次全回归（D4.12 / C13）。

用法（本机）：

    $env:UV_CACHE_DIR='E:\\workbuddy_workspace\\2026-09-20-16-38-19\\amz-listing-kit\\.uv-cache'
    uv run --locked python tools\\regress_product_v1.py --passes 2

规则：
- 套件顺序执行：并发会让两套 Playwright 同时写证据目录，也会掩盖端口/资源问题；
- 子进程使用与父进程相同的解释器，因此 uv 注入的 Playwright 对全部 UI 套件生效；
- 每个 pass 内部、以及两个 pass 之间，代码与静态资源指纹必须完全一致；
- 只包含假 provider 套件；真实模型脚本（tools/run_real_*.py）不在本回归内，另行单独取证；
- 报告落盘 evals/product-demo/：每个 pass 一份 JSON，另加一份总报告。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.workspace_backup_restore import build_version_record, sha256_file  # noqa: E402

EVIDENCE = ROOT / "evals" / "product-demo"
RUN_LOGS = ROOT / "_working" / "amz-listing-kit-product-demo"
PY = sys.executable
TAIL_LINES = 60
TIMEOUT_SECONDS = 1800

SUITES: list[tuple[str, list[str]]] = [
    ("node-check-ui", ["node", "--check", "app/product_v1/product.js"]),
    ("py-compile", [PY, "-m", "py_compile", "app/product_v1_server.py",
                    "src/application_service.py", "src/workspace_store.py"]),
    ("contracts", [PY, "tools/verify_product_v1_contracts.py"]),
    ("bootstrap", [PY, "tools/verify_product_v1_bootstrap.py"]),
    ("application-service", [PY, "tools/verify_application_service.py"]),
    ("workspace-store", [PY, "tools/verify_workspace_store.py"]),
    ("workspace-store-concurrency", [PY, "tools/verify_workspace_store_concurrency.py"]),
    ("semantic-provider", [PY, "tools/verify_semantic_provider.py"]),
    ("dashscope-image-provider", [PY, "tools/verify_dashscope_image_provider.py"]),
    ("plan", [PY, "tools/verify_product_v1_plan.py"]),
    ("prompt", [PY, "tools/verify_product_v1_prompt.py"]),
    ("plan-edit", [PY, "tools/verify_product_v1_plan_edit.py"]),
    ("image-generation", [PY, "tools/verify_product_v1_image_generation.py"]),
    ("generation-isolation", [PY, "tools/verify_product_v1_generation_isolation.py"]),
    ("suite-command", [PY, "tools/verify_product_v1_suite_command.py"]),
    ("http", [PY, "tools/verify_product_v1_http.py"]),
    ("selection-rework-export", [PY, "tools/verify_product_v1_selection_rework_export.py"]),
    ("delivery-checks", [PY, "tools/verify_product_v1_delivery_checks.py"]),
    ("conflict-guard", [PY, "tools/verify_product_v1_conflict_guard.py"]),
    ("entry-audit", [PY, "tools/verify_product_v1_entry_audit.py"]),
    ("workspace-relocation", [PY, "tools/verify_product_v1_workspace_relocation.py"]),
    ("ui", [PY, "tools/verify_product_v1_ui.py"]),
    ("ui-shot-retry", [PY, "tools/verify_product_v1_ui_shot_retry.py"]),
    ("ui-rework", [PY, "tools/verify_product_v1_ui_rework.py"]),
    ("suite-command-ui", [PY, "tools/verify_product_v1_suite_command_ui.py"]),
    ("generation-recovery-ui", [PY, "tools/verify_product_v1_generation_recovery_ui.py"]),
    ("review-workbench-ui", [PY, "tools/verify_product_v1_review_workbench_ui.py"]),
    ("delivery-ui", [PY, "tools/verify_product_v1_delivery_ui.py"]),
    ("usability-accessibility", [PY, "tools/verify_product_v1_usability_accessibility.py"]),
    ("export-wording-drift", [PY, "tools/verify_product_v1_export_wording_drift.py"]),
    ("guard-project-state", [PY, "tools/check_project_state.py"]),
    ("guard-docs", [PY, "tools/check_docs.py"]),
]


def fingerprint_snapshot() -> dict:
    fingerprints = build_version_record(None)["code_fingerprints"]
    extra_patterns = ("config/**/*", "start_product.bat")
    for pattern in extra_patterns:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file():
                fingerprints[path.relative_to(ROOT).as_posix()] = sha256_file(path)
    return fingerprints


def fingerprint_id(fingerprints: dict) -> str:
    blob = json.dumps(sorted(fingerprints.items()), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def run_suite(name: str, command: list[str], log_dir: Path) -> dict:
    started = time.monotonic()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS, env=env,
        )
        returncode = proc.returncode
        output = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        output = f"TIMEOUT: 超过 {TIMEOUT_SECONDS}s\n{partial}"
    except OSError as exc:
        returncode = 127
        output = f"无法启动：{exc}"
    seconds = round(time.monotonic() - started, 1)
    tail = "\n".join(output.strip().splitlines()[-TAIL_LINES:])
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    log_path.write_text(output, encoding="utf-8")
    print(f"[{name}] rc={returncode} · {seconds}s", flush=True)
    if returncode != 0:
        print(f"── {name} 输出尾部 ──")
        print(tail)
    return {"name": name, "command": command, "rc": returncode, "seconds": seconds,
            "log_path": log_path.relative_to(ROOT).as_posix(),
            "log_sha256": sha256_file(log_path), "tail": tail}


def run_pass(index: int, stamp: str, label: str,
             suites: list[tuple[str, list[str]]]) -> dict:
    print(f"\n===== pass {index} · {stamp} =====", flush=True)
    log_dir = RUN_LOGS / f"regression-{label}{stamp}-pass{index}"
    before = fingerprint_snapshot()
    results = [run_suite(name, command, log_dir) for name, command in suites]
    after = fingerprint_snapshot()
    passed = all(item["rc"] == 0 for item in results)
    return {
        "stamp": stamp,
        "pass_index": index,
        "label": label,
        "fingerprint_id_before": fingerprint_id(before),
        "fingerprint_id_after": fingerprint_id(after),
        "fingerprints_identical": before == after,
        "fingerprints_before": before,
        "fingerprints_after": after,
        "suites": results,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--only", action="append", default=[],
                        help="只跑指定名称的套件（可重复）")
    parser.add_argument("--label", default="", help="报告文件名前缀标签（例如 smoke-）")
    args = parser.parse_args()
    known = {name for name, _ in SUITES}
    unknown = set(args.only) - known
    if unknown:
        print("未知套件：" + ", ".join(sorted(unknown)))
        print("可用套件：" + ", ".join(name for name, _ in SUITES))
        return 2
    suites = [item for item in SUITES if not args.only or item[0] in args.only]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    passes: list[dict] = []
    for index in range(1, args.passes + 1):
        report = run_pass(index, stamp, args.label, suites)
        passes.append(report)
        if not report["passed"]:
            break
    fingerprints_consistent = bool(passes) and all(
        item["fingerprints_identical"] for item in passes) and len(
        {item["fingerprint_id_after"] for item in passes}) == 1
    all_passed = len(passes) == args.passes and all(item["passed"] for item in passes)
    summary = {
        "stamp": stamp,
        "label": args.label,
        "requested_passes": args.passes,
        "suites": [name for name, _ in suites],
        "passes": [{
            "pass_index": item["pass_index"],
            "passed": item["passed"],
            "fingerprint_id": item["fingerprint_id_after"],
            "failed": [suite["name"] for suite in item["suites"] if suite["rc"] != 0],
        } for item in passes],
        "fingerprints_consistent": fingerprints_consistent,
        "all_passed": all_passed,
        "verdict": ("通过：全部套件连续两轮全绿，代码/静态资源指纹一致"
                    if all_passed and fingerprints_consistent else
                    "未通过：见各 pass 报告"),
    }
    for item in passes:
        path = EVIDENCE / (f"d4.12-regression-{args.label}{stamp}-"
                           f"pass{item['pass_index']}.json")
        item["report_path"] = path.relative_to(ROOT).as_posix()
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = EVIDENCE / f"d4.12-regression-{args.label}{stamp}.json"
    summary["report_path"] = summary_path.relative_to(ROOT).as_posix()
    for item in passes:
        item.pop("fingerprints_before", None)
        item.pop("fingerprints_after", None)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if (all_passed and fingerprints_consistent) else 1


if __name__ == "__main__":
    raise SystemExit(main())
