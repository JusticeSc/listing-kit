#!/usr/bin/env python
"""D1.1 provider doctor —— 只读、离线、**零付费调用**。

它回答一个问题：**我们打算依赖的 provider 能力，哪些已经被证明、哪些还悬着？**

三条纪律：
  1. 不做任何生成调用。它只读契约文件、环境变量与实现里的常量。
  2. 未知即不支持（契约里的 release_policy.unknown_is_unsupported）：
     status=unknown 的能力一律列进「未解项」，不允许在别处当成能力用。
  3. 判据本身要能被证伪：--self-test 会把契约逐项改坏，要求每一项都被抓到。

用法：
    python demo/provider/doctor.py --project .            # 人读报告
    python demo/provider/doctor.py --project . --json     # 机器读
    python demo/provider/doctor.py --project . --self-test

退出码：
    0  契约、环境、实现三者一致
    2  契约文件本身有问题（缺字段、状态不在取值域、证据文件不存在）
    3  环境缺 DASHSCOPE_API_KEY（不能真跑，但契约仍然有效）
    4  实现里的 endpoint 与契约不一致（配置漂移）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
try:
    from console import enable_utf8  # noqa: E402

    enable_utf8()
except Exception:  # 控制台编码归一失败不该让 doctor 挂掉
    pass

CONTRACT_REL = "demo/provider/dashscope_contract.json"
CALLER_REL = "demo/fixture/reference_views.py"
STATUSES = ("proven_by_our_call", "official_doc", "unknown")
SCHEMA = "amz-listing-kit/provider-contract@1"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_contract(root: Path, data: dict) -> list[str]:
    """契约自身的结构：状态取值域、official_doc 必须有来源、证据文件必须存在。"""
    bad: list[str] = []
    if data.get("schema") != SCHEMA:
        bad.append(f"schema 不是 {SCHEMA}：{data.get('schema')!r}")
    for key in ("provider", "frozen_at", "release_policy", "model", "endpoints", "capabilities"):
        if key not in data:
            bad.append(f"契约缺字段：{key}")
    if not data.get("release_policy", {}).get("unknown_is_unsupported"):
        bad.append("release_policy.unknown_is_unsupported 不是 true —— 未知就会被当成能力用")

    caps = data.get("capabilities") or []
    if not caps:
        bad.append("capabilities 为空")
    seen: set[str] = set()
    for cap in caps:
        cid = cap.get("id")
        if not cid:
            bad.append(f"capability 缺 id：{cap.get('item')!r}")
            continue
        if cid in seen:
            bad.append(f"capability id 重复：{cid}")
        seen.add(cid)
        status = cap.get("status")
        if status not in STATUSES:
            bad.append(f"{cid}: status {status!r} 不在取值域 {STATUSES}")
        if status == "official_doc" and not cap.get("source"):
            bad.append(f"{cid}: official_doc 必须带 source")
        if status == "unknown" and not cap.get("why"):
            bad.append(f"{cid}: unknown 必须写 why（为什么查不到）")
        for rel in cap.get("evidence") or []:
            if not (root / rel).is_file():
                bad.append(f"{cid}: 证据文件不存在 {rel}")

    for key in ("create_async", "query_task"):
        if not data.get("endpoints", {}).get(key):
            bad.append(f"endpoints 缺 {key}")
    return bad


def check_implementation(root: Path, data: dict) -> list[str]:
    """实现里的 endpoint 常量必须与契约一致 —— 否则是配置漂移。"""
    bad: list[str] = []
    src = root / CALLER_REL
    if not src.is_file():
        return [f"找不到调用方实现：{CALLER_REL}"]
    text = src.read_text(encoding="utf-8")
    found = dict(re.findall(r'^(CREATE_URL|TASK_URL)\s*=\s*"([^"]+)"', text, re.M))
    for const, key in (("CREATE_URL", "create_async"), ("TASK_URL", "query_task")):
        impl = found.get(const)
        want = (data.get("endpoints") or {}).get(key)
        if impl is None:
            bad.append(f"{CALLER_REL} 里找不到 {const}")
        elif impl != want:
            bad.append(f"{const} 与契约不一致：实现={impl} 契约={want}")
    if "X-DashScope-Async" not in text:
        bad.append(f"{CALLER_REL} 未设置 X-DashScope-Async 请求头")
    return bad


def unresolved(data: dict) -> list[dict]:
    return [c for c in (data.get("capabilities") or []) if c.get("status") == "unknown"]


def build_report(root: Path) -> tuple[int, dict]:
    contract_path = root / CONTRACT_REL
    if not contract_path.is_file():
        return 2, {"problems": [f"缺契约文件：{CONTRACT_REL}"], "contract": None}
    data = _read_json(contract_path)
    problems = check_contract(root, data)
    impl = check_implementation(root, data)
    env_ok = bool(os.getenv((data.get("auth") or {}).get("env_var") or ""))
    unresolved_caps = unresolved(data)
    code = 0
    if problems:
        code = 2
    elif impl:
        code = 4
    elif not env_ok:
        code = 3
    return code, {
        "contract": str(contract_path),
        "model": (data.get("model") or {}).get("name"),
        "region": (data.get("region") or {}).get("declared"),
        "capabilities": len(data.get("capabilities") or []),
        "unknowns": [{"id": c["id"], "item": c.get("item"), "why": c.get("why")} 
                     for c in unresolved_caps],
        "problems": problems,
        "implementation_drift": impl,
        "env": {"var": (data.get("auth") or {}).get("env_var"), "present": env_ok},
    }


def render(rep: dict) -> str:
    c = rep["contract"]
    lines = [
        "provider doctor（只读 · 离线 · 零付费调用）",
        "=" * 72,
        f"契约：{c}",
        f"模型：{rep['model']}　地域：{rep['region']}　能力条目：{rep['capabilities']}",
        f"环境：{rep['env']['var']} {'已配置' if rep['env']['present'] else '**缺失**'}",
        "",
    ]
    if rep["problems"]:
        lines += [f"契约自身有问题（{len(rep['problems'])} 条）："]
        lines += [f"  ✗ {p}" for p in rep["problems"]]
    else:
        lines.append("契约自身：逐项通过（状态取值域、来源、证据文件都在）")
    if rep["implementation_drift"]:
        lines += [f"实现与契约漂移（{len(rep['implementation_drift'])} 条）："]
        lines += [f"  ✗ {p}" for p in rep["implementation_drift"]]
    else:
        lines.append("实现与契约：endpoint 常量与异步请求头一致")
    lines.append("")
    if rep["unknowns"]:
        lines.append(f"未解项（按「未知即不支持」处理，{len(rep['unknowns'])} 条）：")
        for u in rep["unknowns"]:
            lines.append(f"  ? {u['id']} —— {u['item']}")
            lines.append(f"      为什么查不到：{u['why']}")
    else:
        lines.append("未解项：无")
    return "\n".join(lines)


def self_test(root: Path) -> int:
    """逐项把契约改坏，要求每一项都被抓到 —— 判据必须能被证伪。"""
    base = _read_json(root / CONTRACT_REL)
    cases: list[tuple[str, callable]] = [
        ("状态不在取值域", lambda d: d["capabilities"][0].__setitem__("status", "差不多可用")),
        ("official_doc 缺来源",
         lambda d: d["capabilities"][0].pop("source", None)),
        ("unknown 缺 why",
         lambda d: next(c for c in d["capabilities"] if c["status"] == "unknown").pop("why", None)),
        ("证据文件不存在",
         lambda d: d["capabilities"][2].__setitem__("evidence", ["evals/不存在的文件.png"])),
        ("unknown_is_unsupported 被关掉",
         lambda d: d["release_policy"].__setitem__("unknown_is_unsupported", False)),
        ("端点与实现不一致",
         lambda d: d["endpoints"].__setitem__("create_async", "https://example.invalid/api")),
    ]
    tmp = Path(tempfile.mkdtemp(prefix="doctor-selftest-"))
    bad = 0
    try:
        for name, mutate in cases:
            data = json.loads(json.dumps(base))
            mutate(data)
            (tmp / CONTRACT_REL).parent.mkdir(parents=True, exist_ok=True)
            (tmp / CONTRACT_REL).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
            # 调用方实现与证据文件都在真项目里，所以用真 root 复制一份改造后的契约来校验
            problems = check_contract(root, data) + check_implementation(root, data)
            ok = bool(problems)
            print(f"[{'OK  ' if ok else 'FAIL'}] {name}  →  {problems[0] if problems else '没有被抓到'}")
            bad += 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n自检：{len(cases) - bad}/{len(cases)} 项被正确抓到")
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    root = Path(args.project).resolve()
    if args.self_test:
        return self_test(root)
    code, rep = build_report(root)
    if args.json:
        print(json.dumps({"exit_code": code, **rep}, ensure_ascii=False, indent=2))
    else:
        print(render(rep))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
