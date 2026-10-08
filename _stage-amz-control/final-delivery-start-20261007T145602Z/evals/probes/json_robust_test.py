"""extract_json 鲁棒性测试 —— 纯函数，零调用。

三类未决 #5 的**不需要模型的那一半**：`extract_json` 是整条离线链上唯一把
LLM 自由文本转成结构化数据的地方。它在离线跑，崩了要人重跑一次编译。

现有实现只做两件事：剥 ``` 围栏、`find("{")` 配 `rfind("}")`。
**`rfind` 是可疑的** —— 它取的是*最后一个* `}`，不是*与第一个 `{` 配对*的那个。
于是两处会崩：① 输出两个对象 ② 正文里出现花括号（`the set {a,b}`）。

判据（每条样本自带期望，**对照必须两边都有**）
------------------------------------------------
- `ok`     应解析成功，且取到**第一个**对象
- `reject` 应显式报错（说明这份输出不能用，应交人 / 重试），**不许静默给出半成品**

左边是现状（v1），右边是配对扫描版（v2）。若 v1 在 `ok` 样本上崩，就是真 bug。

用法
----
    python evals/probes/json_robust_test.py          # 只跑对照，不改代码
    python evals/probes/json_robust_test.py --patch   # 顺带把 v2 写进 prompt_enhance_probe.py

退出码：0 全是预期行为 · 1 有样本没达到期望（**红的是解析器，不是样本**）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prompt_enhance_probe as pe  # 被测对象：现状实现


def extract_json_v1_original(raw: str) -> dict:
    """2026-09-22 之前的实现，**逐字固化在这里当对照**。

    ★ 为什么不直接 import `pe.extract_json` 当对照：patch 之后活代码也变成 v2 了，
      对照会**自己消失**（实测撞到 —— patch 后重跑，v1 列显示 1/22，因为它已经是新代码）。
      **对照必须钉在历史形态上**，否则"改判据"这个动作会把证据一起改掉。
    """
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < 0:
        raise ValueError(f"输出里没有 JSON 对象:\n{raw[:400]}")
    return json.loads(s[i:j + 1])


def _balanced_from(raw: str, i: int) -> str | None:
    """从 raw[i]（应为 `{`）起找**与之配对**的右括号，返回该子串；不平衡返回 None。"""
    depth, in_str, esc = 0, False, False
    for j in range(i, len(raw)):
        ch = raw[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[i:j + 1]
    return None


def extract_json_v2(raw: str) -> dict:
    """抠出**第一个能解析成 dict 的平衡 JSON 对象**。

    与 v1 的差别：v1 用 `rfind("}")` 赌"最后一个右括号就是配对的"，一崩即死。
    v2 从**每个** `{` 起点各试一次：配对 → 解析 → 成功即返回；失败就试下一个。
    这样正文里的 `the set {a,b}` 会被跳过而不是把整段带走。
    """
    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        chunk = _balanced_from(raw, i)
        if chunk is None:
            continue                      # 截断/不平衡 → 换个起点
        try:
            got = json.loads(chunk)
        except Exception:
            continue                      # 不是合法 JSON（如 `{a, b}`、单引号）→ 换个起点
        if isinstance(got, dict):
            return got
    raise ValueError(f"没有找到能解析的 JSON 对象:\\n{raw[:400]}")


# ---------------------------------------------------------------------------
# 样本表：name · 原始输出 · 期望 · 期望里该出现的键
#   ok=True  → 应解析成功；ok=False → 应显式报错
# ---------------------------------------------------------------------------
CASES: list[tuple[str, str, bool, str | None]] = [
    ("clean",                    '{"lock_segment": "x"}', True,  "lock_segment"),
    ("fence_json",               '```json\n{"lock_segment": "x"}\n```', True, "lock_segment"),
    ("fence_plain",              '```\n{"lock_segment": "x"}\n```', True, "lock_segment"),
    ("prefix_suffix",            'Sure! Here:\n{"lock_segment": "x"}\nHope it helps.', True, "lock_segment"),
    ("leading_blank_lines",      '\n\n  {"lock_segment": "x"}\n', True, "lock_segment"),
    ("bom",                      '\ufeff{"lock_segment": "x"}', True, "lock_segment"),
    ("nested_objects",           '{"a": {"b": {"c": 1}}, "lock_segment": "x"}', True, "lock_segment"),
    ("array_then_object",        '[1,2,3]\n{"lock_segment": "x"}', True, "lock_segment"),
    ("brace_inside_string",      '{"note": "use {x} here", "lock_segment": "y"}', True, "lock_segment"),
    ("close_brace_inside_string", '{"note": "ends with }", "lock_segment": "y"}', True, "lock_segment"),
    ("escaped_quote_in_string",  '{"note": "say \\"hi\\"", "lock_segment": "y"}', True, "lock_segment"),
    # ↓ 以下是 v1 的 `rfind` 会崩的两类
    ("TWO_objects",              '{"lock_segment": "first"}\n{"lock_segment": "second"}', True, "lock_segment"),
    ("TWO_fenced_objects",       '```json\n{"lock_segment": "first"}\n```\n```json\n{"lock_segment": "second"}\n```', True, "lock_segment"),
    ("PLAIN_TEXT_braces_before", 'The set {a, b} has letters.\n{"lock_segment": "x"}', True, "lock_segment"),
    ("object_then_array_brace",  '{"lock_segment": "x"}\nTrailing ["}"]', True, "lock_segment"),
    # ↓ 以下是应显式拒绝的（模型真的会吐这些）
    ("reject_trailing_comma",    '{"lock_segment": "x",}', False, None),
    ("reject_single_quotes",     "{'lock_segment': 'x'}", False, None),
    ("reject_cjk_punctuation",   '{"lock_segment"："x"}', False, None),
    ("reject_truncated",         '{"lock_segment": "x', False, None),
    ("reject_no_brace",          'I cannot do that.', False, None),
    ("reject_python_comment",    '{"lock_segment": "x",  # note\n}', False, None),
    ("reject_unquoted_key",      '{lock_segment: "x"}', False, None),
]


def run_one(fn, raw: str, expect_ok: bool, key: str | None) -> tuple[str, str]:
    """返回 (状态, 说明)。状态 ∈ {PASS, CRASH, BAD, WRONG}。"""
    try:
        got = fn(raw)
    except Exception as exc:
        kind = type(exc).__name__
        if expect_ok:
            return "CRASH", f"{kind}: {str(exc)[:48]}"
        return "PASS", f"如期望般拒绝（{kind}）"
    # 解析成功
    if not expect_ok:
        return "BAD", f"**应拒绝却成功**，返回 {str(got)[:40]}"
    if key and key not in got:
        return "WRONG", f"解析成功但缺键 {key}：{str(got)[:40]}"
    return "PASS", f"ok → {{{key}: {str(got.get(key))[:24]}}}"


def first_object_consistency() -> str:
    """额外自洽检查：`TWO_objects` 必须取到 **first** 而不是 second 或拼接。"""
    raw = CASES[[c[0] for c in CASES].index("TWO_objects")][1]
    try:
        got = extract_json_v2(raw)
    except Exception as exc:
        return f"v2 也崩了：{exc}"
    v = got.get("lock_segment")
    return "v2 取到 first ✓" if v == "first" else f"v2 取到 {v!r} ✗（应为 first）"


def main() -> int:
    ap = argparse.ArgumentParser(description="extract_json 脏样本对照（零调用）")
    ap.add_argument("--patch", action="store_true",
                    help="把 v2 写入 prompt_enhance_probe.py（先备份到 _trash/）")
    args = ap.parse_args()

    print("=" * 108)
    print(f"{'sample':28s} {'期望':6s} {'v1 原实现':11s} {'v2 配对扫描':11s} {'活代码 live':11s} 说明")
    print("=" * 108)
    v1_bad = v2_bad = live_bad = 0
    for name, raw, expect_ok, key in CASES:
        s1, m1 = run_one(extract_json_v1_original, raw, expect_ok, key)
        s2, m2 = run_one(extract_json_v2, raw, expect_ok, key)
        s3, _ = run_one(pe.extract_json, raw, expect_ok, key)
        v1_bad += s1 != "PASS"
        v2_bad += s2 != "PASS"
        live_bad += s3 != "PASS"
        exp = "ok" if expect_ok else "reject"
        mark = "" if s2 == "PASS" else "   <<<"
        print(f"{name:28s} {exp:6s} {s1:11s} {s2:11s} {s3:11s} {m1[:26]}{mark}")
    print("=" * 108)
    print(f"不符期望：v1(原) = {v1_bad}/{len(CASES)}   v2(候选) = {v2_bad}/{len(CASES)}   "
          f"live(现役) = {live_bad}/{len(CASES)}")
    if live_bad != v2_bad:
        print("[x] **现役实现与 v2 行为不一致** —— 有人改了却没跑本脚本（或改了别的分支）")
    print(f"first 语义：{first_object_consistency()}")

    if args.patch:
        import inspect

        src = (HERE / "prompt_enhance_probe.py").read_text(encoding="utf-8")

        # ★ 从 v2 的**源码**生成要写入的块，不手写副本。
        #   为什么要这样：第一版是手写字符串，写进去的是"只从第一个 `{` 起配对"的旧版；
        #   后来 v2 升级成"逐个 `{` 当起点试"，手写副本没跟着改 ⇒ **两者失同步**，
        #   靠 `live` 断言才抓到（1/22）。同一逻辑存在两份副本 = 必然漂移。
        new_block = (inspect.getsource(_balanced_from) + "\n\n"
                     + inspect.getsource(extract_json_v2)
                     .replace("def extract_json_v2(", "def extract_json(", 1))

        # 替换区间：`_balanced_from`（若已存在）或 `extract_json` 起，到该块的下一行顶层语句前。
        pat = re.compile(
            r"^(?:def _balanced_from\(.*?\n\n)?def extract_json\(raw: str\) -> dict:.*?\n(?=\S)",
            re.S | re.M)
        old = pat.search(src)
        if not old:
            print("[!] 没找到可替换的 extract_json 块，未改写。请人工改。")
            return 1

        trash = HERE.parent.parent / "_trash"
        trash.mkdir(exist_ok=True)
        (trash / "prompt_enhance_probe.py.bak").write_text(src, encoding="utf-8")
        (HERE / "prompt_enhance_probe.py").write_text(
            src[:old.start()] + new_block + "\n" + src[old.end():], encoding="utf-8")
        print("[ok] 已按 v2 源码写入；原文件备份在 _trash/prompt_enhance_probe.py.bak")
    return 0 if v2_bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
