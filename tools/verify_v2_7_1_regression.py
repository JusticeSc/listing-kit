#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""V2.7.1 Product V2 全回归：两次连续全绿 + 结果指纹一致。

计划 §10.1 的 V2.7.1 要两件东西：

    两次连续全绿、指纹一致   ← 本入口负责
    每个关键守卫被证明能变红 ← `evals/probes/` 下的反向对照各证一段

为什么指纹要单独算：两次「退出码都是 0」并不等于两次「验的是同一件事」。
把每轮的**结果信号**（`[PASS] …` / `[OK  ] …` 行、无信号命令的归一化尾行）
排成有序表再哈希，两轮必须逐字节一致 —— 不一致说明结论本身不可复现，
那这次「全绿」就不能拿来当发布候选的证据。

命令清单**只从 CI 工作流读**（`.github/workflows/ci-cd.yml` 里 `uv run python …` 的行）。
两处清单各自维护时，最先漂的就是「CI 跑的」与「本地跑的」不是同一套；本地照着
CI 重抄一份清单，等于给自己留了一条悄悄少跑几步的路。

额外两条不在 CI 里的探针（`evals/probes/docs_index.py`）在这里补跑：
反向对照证明「守卫会红」，属于验收证据，不属于 CI 的每次开销。

用法
----
    uv run --locked python tools/verify_v2_7_1_regression.py
    uv run --locked python tools/verify_v2_7_1_regression.py --only check_docs
    uv run --locked python tools/verify_v2_7_1_regression.py --rounds 1   # 调试，不当证据

证据：`evals/product-v2/v2.7.1-regression-<时间戳>-final.txt/.json`
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

WORKFLOW = ROOT / ".github" / "workflows" / "ci-cd.yml"
EVID = ROOT / "evals" / "product-v2"
LOCK = EVID / ".v2.7.1-regression.lock"

# CI 里逐条执行的命令行（`uv run python <脚本> [参数]`）
CI_LINE = re.compile(r"^\s*uv run python ([^\s#]+)(.*)$")

# 不在 CI 里、但属于本次验收的反向对照
EXTRA_CHECKS: list[tuple[str, str, list[str]]] = [
    ("探针", "evals/probes/docs_index.py", []),
]

# [PASS]/[OK  ]/FAIL 这类结果行的信号：只认 ASCII 编号，避免把
# 「PASS 整套复核 provider 不可用…」这类中文描述当成可变信号
SIGNAL = re.compile(r"(?m)^\s*\[?(PASS|FAIL|OK|WARN|SKIP)\]?\s+([A-Za-z0-9][A-Za-z0-9._\-]*)")
# 无信号命令的尾行归一化：时间、端口、纯数字都换成 # —— 它们每次都不一样，
# 但换掉之后「结论行」是否变化仍然可测
NOISE = re.compile(
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}:\d{2}"
    r"|\d{1,2}:\d{2}:\d{2}"
    r"|\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}"
    r"|\b\d+\b")

MAX_OUTPUT = 200_000   # 单条命令的原始输出上限（超出截断并标注）


def ci_commands() -> list[tuple[str, str, list[str]]]:
    """从 CI 工作流读命令清单 —— 单一权威，本文件不重抄一份。"""
    if not WORKFLOW.exists():
        return []
    cmds: list[tuple[str, str, list[str]]] = []
    for raw in WORKFLOW.read_text(encoding="utf-8").splitlines():
        m = CI_LINE.match(raw)
        if not m:
            continue
        script = m.group(1).strip()
        rest = m.group(2).strip()
        cmds.append(("CI", script, rest.split() if rest else []))
    return cmds


def signals_of(text: str) -> list[str]:
    found = [f"{a} {b}" for a, b in SIGNAL.findall(text)]
    if found:
        return found
    tail = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return ["tail " + NOISE.sub("#", tail[-1])[:160]] if tail else ["tail <empty>"]


def run_one(script: str, extra: list[str], timeout: int = 900) -> dict:
    argv = ["uv", "run", "--locked", "python", script, *extra]
    t0 = time.monotonic()
    try:
        p = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        rc, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as exc:
        rc = 124
        head = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        tail = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        out = head + tail + f"\n[timeout {timeout}s]"
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n…[截断：原始 {len(out)} 字符]"
    return {
        "argv": argv,
        "rc": rc,
        "seconds": round(time.monotonic() - t0, 1),
        "signals": signals_of(out),
        "output": out,
    }


def fingerprint(rows: list[dict]) -> str:
    body = json.dumps([[r["script"], r["args"], r["rc"], r["signals"]] for r in rows],
                      ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--only", default="", help="只跑脚本名里含这段文字的命令（调试用）")
    ap.add_argument("--stamp", default="")
    args = ap.parse_args()

    if LOCK.exists():
        print(f"已有另一轮在跑（{LOCK}）—— 并发会让两份指纹互相当成漂移，先等它结束。")
        return 3
    EVID.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(str(os.getpid()), encoding="utf-8")

    stamp = args.stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        checks = ci_commands() + EXTRA_CHECKS
        if args.only:
            checks = [c for c in checks if args.only in c[1]]
        if not checks:
            print("命令清单为空 —— CI 工作流读不到 `uv run python …` 行了吗？")
            return 2

        print(f"V2.7.1 全回归 · {args.rounds} 轮 · {len(checks)} 条命令 · {stamp}")
        rounds: list[dict] = []
        for r in range(1, args.rounds + 1):
            print(f"=== 第 {r}/{args.rounds} 轮")
            rows: list[dict] = []
            for _tag, script, extra in checks:
                row = run_one(script, extra)
                row["script"] = script
                row["args"] = extra
                rows.append(row)
                mark = "OK  " if row["rc"] == 0 else "FAIL"
                print(f"[{mark}] {script} {' '.join(extra)} -> rc={row['rc']}"
                      f" · {row['seconds']}s · {len(row['signals'])} 信号")
                if row["rc"] != 0:
                    for ln in row["output"].splitlines():
                        if ln.strip().startswith("✗") or "[FAIL]" in ln or "Traceback" in ln:
                            print("        | " + ln.strip()[:180])
            rounds.append({"round": r, "rows": rows, "fingerprint": fingerprint(rows)})
            print(f"--- 第 {r} 轮指纹 {rounds[-1]['fingerprint'][:16]}")

        problems: list[str] = []
        for r in rounds:
            for row in r["rows"]:
                if row["rc"] != 0:
                    problems.append(f"第 {r['round']} 轮 {row['script']} 退出码 {row['rc']}")
        fps = [r["fingerprint"] for r in rounds]
        if len(set(fps)) != 1:
            problems.append("两轮指纹不一致：" + "、".join(f[:12] for f in fps))

        lines = [f"V2.7.1 Product V2 全回归 · {stamp}",
                 f"命令数 {len(checks)} · 轮数 {args.rounds} · "
                 f"指纹 {fps[0][:16]}" + ("（两轮一致）" if len(set(fps)) == 1 else "（两轮不一致）"),
                 ""]
        for r in rounds:
            lines.append(f"== 第 {r['round']} 轮 · 指纹 {r['fingerprint']}")
            for row in r["rows"]:
                lines.append(f"[{'PASS' if row['rc'] == 0 else 'FAIL'}] {row['script']} "
                             f"{' '.join(row['args'])} -> rc={row['rc']} · {row['seconds']}s · "
                             f"{len(row['signals'])} 信号")
            lines.append("")
        lines.append("== 结论")
        if problems:
            lines.extend("✗ " + p for p in problems)
        else:
            lines.append(f"OK：{args.rounds} 轮连续全绿，指纹一致（{fps[0][:16]}）。")
        out_txt = EVID / f"v2.7.1-regression-{stamp}-final.txt"
        out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

        payload = {
            "task": "V2.7.1",
            "stamp": stamp,
            "rounds": args.rounds,
            "checks": len(checks),
            "fingerprints": fps,
            "problems": problems,
            "commands": [[row["script"], row["args"], row["rc"], row["seconds"],
                          row["signals"], row["output"]] for r in rounds for row in r["rows"]],
        }
        out_json = EVID / f"v2.7.1-regression-{stamp}-final.json"
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
        print()
        print("\n".join(lines[-6:]))
        print(f"证据：{out_txt.relative_to(ROOT).as_posix()} / "
              f"{out_json.relative_to(ROOT).as_posix()}")
        if problems:
            print("结果：有未通过项（退出码 1）。")
            return 1
        print("结果：全过（退出码 0）。")
        return 0
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
