#!/usr/bin/env python3
"""退役恢复登记的负向对照；不改候选工作树。"""
from __future__ import annotations

import copy
import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_retired_documents as guard  # noqa: E402

REGISTRY = ROOT / "config" / "retired-documents.json"


def _run(payload: object) -> tuple[int, str]:
    temporary_parent = ROOT / "evals" / ".tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="amz-retired-probe-", dir=temporary_parent) as temporary:
        path = Path(temporary) / "retired-documents.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        previous = guard.REGISTRY
        guard.REGISTRY = path
        output = StringIO()
        try:
            with redirect_stdout(output), redirect_stderr(output):
                status = guard.main()
            return status, output.getvalue()
        finally:
            guard.REGISTRY = previous


def main() -> int:
    baseline = json.loads(REGISTRY.read_text(encoding="utf-8"))
    cases: list[tuple[str, object, str]] = []

    malformed_shape = copy.deepcopy(baseline)
    malformed_shape["documents"][0] = "not an object"
    cases.append(("非对象登记拒绝", malformed_shape, "documents[0]: 必须是对象"))

    wrong_commit = copy.deepcopy(baseline)
    wrong_commit["documents"][0]["commit"] = "0" * 40
    cases.append(("非公共基线拒绝", wrong_commit, "documents[0].commit: 必须是公共基线"))

    unsafe_path = copy.deepcopy(baseline)
    unsafe_path["documents"][0]["path"] = "../outside.md"
    cases.append(("越界路径拒绝", unsafe_path, "documents[0].path: 必须是仓库内相对路径"))

    duplicate = copy.deepcopy(baseline)
    duplicate["documents"].append(copy.deepcopy(duplicate["documents"][0]))
    cases.append(("重复路径拒绝", duplicate, "path 重复"))

    coverage_target = "_stage-amz-control/asset-continuation-20261008T054352Z/README.md"
    if not any(item.get("path") == coverage_target for item in baseline["documents"]):
        print("[FAIL] 基线覆盖反向对照缺少已知超限原件")
        return 1
    missing_coverage = copy.deepcopy(baseline)
    missing_coverage["documents"] = [
        item for item in missing_coverage["documents"] if item.get("path") != coverage_target
    ]
    cases.append((
        "缺少公共基线超限文档覆盖",
        missing_coverage,
        "公共基线有 1 份超过 10000 字节的文档未登记拆分或退役",
    ))

    baseline_status, baseline_output = _run(baseline)
    if baseline_status != 0:
        print(f"[FAIL] 退役登记基线未通过：rc={baseline_status}\n{baseline_output.strip()}")
        return 1

    failures: list[str] = []
    for label, payload, expected in cases:
        status, output = _run(payload)
        if status != 1 or expected not in output:
            failures.append(f"{label}（rc={status}，未找到：{expected}）")
    if failures:
        print("[FAIL] 退役登记反向对照失败：" + "、".join(failures))
        return 1
    print(f"[PASS] 退役登记反向对照通过：{len(cases)} 个畸形输入均被拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
