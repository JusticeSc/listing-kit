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

命令清单只从 CI verify job 读取 Python 与根 npm 验证模式，复用 tools/check_verification.py 的解析器。
两处清单各自维护时，最先漂的就是「CI 跑的」与「本地跑的」不是同一套；本地照着
CI 重抄一份清单，等于给自己留了一条悄悄少跑几步的路。

为什么指纹要和身份分开记：`[PASS] …` 这类结论文本是**可打印**的，把它当候选身份，
等于拿「打印了什么」冒充「跑了哪份代码」。源码/配置身份另记 HEAD、跟踪改动与关键
文件**字节**哈希（见 `source_identity`）。

为什么单轮／`--only` 只算诊断：准出要的是「两次连续全绿 + 指纹一致」。少一轮就没有
可比较的对象，缺的那部分只能如实写成「未运行」，不能换个说法当成通过。


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
from check_verification import ci_commands  # noqa: E402

enable_utf8()

WORKFLOW = ROOT / ".github" / "workflows" / "ci-cd.yml"
EVID = ROOT / "evals" / "product-v2"
LOCK = EVID / ".v2.7.1-regression.lock"

# 源码/配置身份由这些文件的**真实字节**决定（命令清单权威 + 分类登记 + 锁）。
SOURCE_FILES = (
    WORKFLOW,
    ROOT / "config" / "product-v2" / "verification.json",
    ROOT / "pyproject.toml",
    ROOT / "uv.lock",
    ROOT / "package.json",
    ROOT / "package-lock.json",
)


# [PASS]/[OK  ]/FAIL 这类结果行的信号：只认 ASCII 编号，避免把
# 「PASS 整套复核 provider 不可用…」这类中文描述当成可变信号
SIGNAL = re.compile(r"(?m)^\s*\[?(PASS|FAIL|OK|WARN|SKIP)\]?\s+([A-Za-z0-9][A-Za-z0-9._\-]*)")
# 无信号命令的尾行归一化：时间、端口、纯数字都换成 # —— 它们每次都不一样，
# 但换掉之后「结论行」是否变化仍然可测
NOISE = re.compile(
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}:\d{2}"
    r"|\d{1,2}:\d{2}:\d{2}"
    r"|\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}"
    r"|\b\d+(?:\.\d+)?(?:ms|s)\b"
    r"|\b\d+\b")
MAX_OUTPUT = 200_000   # 单条命令的原始输出上限（超出截断并标注）




def signals_of(text: str) -> list[str]:
    found = [f"{a} {b}" for a, b in SIGNAL.findall(text)]
    if found:
        return found
    tail = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return ["tail " + NOISE.sub("#", tail[-1])[:160]] if tail else ["tail <empty>"]


def run_one(script: str, extra: list[str], timeout: int = 900) -> dict:
    if script.startswith("npm:"):
        npm = "npm.cmd" if os.name == "nt" else "npm"
        argv = [npm, "run", script[4:]] + (["--", *extra] if extra else [])
    elif script.startswith("pytest:"):
        argv = ["uv", "run", "--locked", "python", "-m", "pytest",
                script[len("pytest:"):], *extra]
    else:
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
    """**结果的**可复现性指纹：只由 {script, args, rc, signals} 组成。

    它回答「两次运行验的是不是同一件结论」，**不是**候选/源码身份 ——
    stdout 里的 `[PASS] …` 是结论文本，谁都能改；把它当代码身份就是把
    「打印了什么」当「跑了哪份代码」。源码/配置身份另由 `source_identity()` 记录。
    """
    body = json.dumps([[r["script"], r["args"], r["rc"], r["signals"]] for r in rows],
                      ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def source_identity() -> dict:
    """被验证的源码/配置身份（HEAD、是否有跟踪改动、关键文件字节哈希）。"""
    def git(*args: str) -> str:
        try:
            p = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return p.stdout.strip() if p.returncode == 0 else ""

    files: dict[str, str] = {}
    for path in SOURCE_FILES:
        rel = path.relative_to(ROOT).as_posix()
        try:
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            files[rel] = "<missing>"
    return {"head": git("rev-parse", "HEAD") or "<unknown>",
            "tracked_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
            "files": files}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--only", default="", help="只跑脚本名里含这段文字的命令（调试用）")
    ap.add_argument("--stamp", default="")
    args = ap.parse_args()
    if args.rounds < 1:
        print("--rounds 至少为 1；0 轮不会产生任何证据，不静默判通过。")
        return 2

    if LOCK.exists():
        print(f"已有另一轮在跑（{LOCK}）—— 并发会让两份指纹互相当成漂移，先等它结束。")
        return 3
    EVID.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(str(os.getpid()), encoding="utf-8")

    stamp = args.stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        checks = ci_commands(WORKFLOW)
        if args.only:
            checks = [c for c in checks if args.only in c[0]]
        if not checks:
            print("命令清单为空 —— CI verify job 没有可执行的已登记验证模式。")
            return 2

        identity = source_identity()
        print(f"V2.7.1 全回归 · {args.rounds} 轮 · {len(checks)} 条命令 · {stamp}"
              f" · 源码身份 {identity['head'][:12]}"
              + ("（有未提交改动）" if identity["tracked_dirty"] else ""))
        rounds: list[dict] = []
        stopped_early = False
        for r in range(1, args.rounds + 1):
            print(f"=== 第 {r}/{args.rounds} 轮")
            rows: list[dict] = []
            for script, extra in checks:
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
            rounds.append({"round": r, "rows": rows,
                           "fingerprint": fingerprint(rows)})
            print(f"--- 第 {r} 轮指纹 {rounds[-1]['fingerprint'][:16]}")
            if r < args.rounds and any(row["rc"] != 0 for row in rows):
                stopped_early = True
                failed_names = [row["script"] for row in rows if row["rc"] != 0]
                print(f"第 {r} 轮有必要失败（{len(failed_names)} 项），不启动第 {r + 1} 轮；"
                      "后续轮次记未运行，独立诊断另行进行。")
                break
        problems: list[str] = []
        for r in rounds:
            for row in r["rows"]:
                if row["rc"] != 0:
                    problems.append(f"第 {r['round']} 轮 {row['script']} 退出码 {row['rc']}")
        if stopped_early:
            problems.append(f"第 1 轮失败后已停止：后 {args.rounds - len(rounds)} 轮未运行，"
                            "不以单轮或后续诊断代替最终两轮。")
        fps = [r["fingerprint"] for r in rounds]
        two_rounds_ran = len(rounds) >= 2 and not stopped_early
        if two_rounds_ran and len(set(fps)) != 1:
            problems.append("两轮指纹不一致：" + "、".join(f[:12] for f in fps))
        # 单轮（或 --only）只是诊断：它不构成「两次连续全绿 + 指纹一致」的准出证据。
        # 但它**不是**产品失败 —— 用独立退出码 4 表示「本轮不可作准出证据」，
        # 免得「没跑够」被当成 0 静默通过，也免得被当成真实红去误改产品。
        diagnostic_only = len(rounds) < 2 or bool(args.only) or stopped_early
        diagnostic = ""
        if diagnostic_only and not problems:
            if len(rounds) < 2 and not args.only:
                diagnostic = "只跑了单轮（--rounds 1），没有第二轮可比较"
            elif args.only:
                diagnostic = "--only 只跑局部命令，不是完整命令集合"
            else:
                diagnostic = "首轮失败后停止，后续轮次未运行"
        if stopped_early:
            fingerprint_note = "（首轮失败后停止，无第二轮可比较）"
        elif len(rounds) < 2:
            fingerprint_note = "（单轮，无从比较）"
        elif len(set(fps)) == 1:
            fingerprint_note = "（两轮一致）"
        else:
            fingerprint_note = "（两轮不一致）"

        identity_text = (f"HEAD {identity['head']}"
                         + ("（有未提交改动）" if identity["tracked_dirty"] else "（工作树干净）"))
        lines = [f"V2.7.1 Product V2 全回归 · {stamp}",
                 f"命令数 {len(checks)} · 轮数 {args.rounds} · 已跑 {len(rounds)} 轮"
                 + ("（首轮失败后停止，后续未运行）" if stopped_early else "") + " · "
                 f"结果指纹 {fps[0][:16]}{fingerprint_note}",
                 f"源码/配置身份：{identity_text}；关键文件哈希："
                 + "、".join(f"{name}={digest[:12]}" for name, digest in identity["files"].items()),
                 "说明：结果指纹只证明两次运行的结论可复现，不是候选/源码身份；源代码身份见上一行。",
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
        if diagnostic:
            lines.append(f"！诊断运行：{diagnostic} —— 不作为最终两轮准出证据（不影响其它独立诊断）。")
        if not problems and not diagnostic:
            lines.append(f"OK：{args.rounds} 轮连续全绿，指纹一致（{fps[0][:16]}）；"
                         f"源码/配置身份 {identity['head'][:12]}。")
        out_txt = EVID / f"v2.7.1-regression-{stamp}-final.txt"
        out_json = EVID / f"v2.7.1-regression-{stamp}-final.json"
        out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

        payload = {
            "task": "V2.7.1",
            "stamp": stamp,
            "rounds": args.rounds,
            "rounds_executed": len(rounds),
            "stopped_early": stopped_early,
            "diagnostic_only": diagnostic_only,
            "diagnostic": diagnostic,
            "checks": len(checks),
            "source": identity,
            "fingerprints": fps,
            "problems": problems,
            "commands": [[row["script"], row["args"], row["rc"], row["seconds"],
                          row["signals"], row["output"]] for r in rounds for row in r["rows"]],
        }
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
        print()
        print("\n".join(lines[-6:]))

        def rel(path: Path) -> str:
            """证据路径只用于回显；EVID 被重定向到仓库外时不能因此炸掉整个入口。"""
            try:
                return path.relative_to(ROOT).as_posix()
            except ValueError:
                return path.as_posix()

        print(f"证据：{rel(out_txt)} / {rel(out_json)}")
        if problems:
            print("结果：有未通过项（退出码 1）。")
            return 1
        if diagnostic:
            print(f"结果：诊断运行，不可作准出证据（退出码 4）—— {diagnostic}。")
            return 4
        print("结果：全过（退出码 0）。")
        return 0
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
