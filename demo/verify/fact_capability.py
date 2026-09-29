#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D1.R1 —— 事实验证能力矩阵守卫（离线、零付费、与商品无关）。

它回答一个问题：这份能力矩阵是不是真的说清了「谁能判、凭什么、边界在哪」，
以及它能不能被跑红 —— 一份永远绿的守卫等于没有守卫。

十条规定（每条都能单独被反例触发，见 --self-test）：

1. 覆盖      事实卡里的每条事实，在矩阵里恰好一条记录；矩阵不许有卡里没有的事实
2. 声明      每条能力必须给出 kind、能判什么、以及人工能力必须要求显式签字
3. 前提      确定性能力必须声明适用前提、不适用时交给下一个责任者、结论域含 not_applicable
4. 派生      能给出通过/失败结论的确定性能力，必须带阈值派生来源与正样本数
5. 人工事实  事实卡标成 human 的事实，矩阵里不许出现确定性或模型能力
6. 缺口兜底  事实卡里 status=open 的机器缺口，对应事实必须有人工能力
7. 不许假绿  任何事实声明「机器判过」时，必须真有适用的确定性能力
8. 未决阻断  没有可用能力的事实，必须显式阻断选择
9. 与商品无关 本文件源码不得含任何商品标识或事实编号字面量
10. 结论域  每条能力的结论域必须是矩阵顶层结论域的子集

用法：
    python demo/verify/fact_capability.py check --project . --sku <name>
    python demo/verify/fact_capability.py self-test --project .

退出码：0 全过；2 有规则不成立；3 用法或文件缺失。
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

RULES = [
    "C1_COVERAGE", "C2_KIND", "C3_PRECONDITION", "C4_DERIVATION", "C5_HUMAN_FACT",
    "C6_GAP_BACKSTOP", "C7_NO_FAKE_GREEN", "C8_UNKNOWN_BLOCKS", "C9_SKU_FREE_CODE",
    "C10_VERDICT_DOMAIN",
]
KINDS = ("deterministic", "model", "human")


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_coverage(card: dict, matrix: dict) -> list[str]:
    problems = []
    card_ids = [f["id"] for f in card.get("facts", [])]
    rows = {f.get("id"): f for f in matrix.get("facts", [])}
    for fid in card_ids:
        if fid not in rows:
            problems.append("事实卡有 " + fid + "，矩阵里没有对应记录")
    for fid in rows:
        if fid not in card_ids:
            problems.append("矩阵有 " + str(fid) + "，事实卡里没有这条事实")
    if len(rows) != len(matrix.get("facts", [])):
        problems.append("矩阵里的事实编号有重复")
    return problems


def check_kind(card: dict, matrix: dict) -> list[str]:
    problems = []
    for fact in matrix.get("facts", []):
        for cap in fact.get("capabilities", []):
            where = str(fact.get("id")) + "/" + str(cap.get("id"))
            if cap.get("kind") not in KINDS:
                problems.append(where + " 的 kind 不在取值域：" + repr(cap.get("kind")))
            if not cap.get("decides"):
                problems.append(where + " 没写能判什么")
            if cap.get("kind") == "human" and not cap.get("requires_explicit_signature"):
                problems.append(where + " 是人工能力，但没有要求显式签字")
    return problems


def check_precondition(card: dict, matrix: dict) -> list[str]:
    problems = []
    for fact in matrix.get("facts", []):
        for cap in fact.get("capabilities", []):
            if cap.get("kind") != "deterministic":
                continue
            where = str(fact.get("id")) + "/" + str(cap.get("id"))
            cond = cap.get("applies_when") or {}
            if not cond.get("probe"):
                problems.append(where + " 没有声明适用性探针")
            if cond.get("max_share") is None:
                problems.append(where + " 没有声明适用性阈值")
            if cap.get("on_not_applicable") != "next_router":
                problems.append(where + " 没有把不适用交给下一个责任者")
            if "not_applicable" not in (cap.get("verdict_domain") or []):
                problems.append(where + " 的结论域不含 not_applicable")
    return problems


def check_derivation(card: dict, matrix: dict) -> list[str]:
    problems = []
    for fact in matrix.get("facts", []):
        for cap in fact.get("capabilities", []):
            if cap.get("kind") != "deterministic":
                continue
            domain = cap.get("verdict_domain") or []
            if not ({"pass", "fail"} & set(domain)):
                continue
            where = str(fact.get("id")) + "/" + str(cap.get("id"))
            cal = cap.get("calibration") or {}
            if not cal.get("source"):
                problems.append(where + " 能判通过/失败，却没有阈值派生来源")
            n = cal.get("sample_n")
            if not isinstance(n, int) or n <= 0:
                problems.append(where + " 的派生样本数不是正整数：" + repr(n))
    return problems


def check_human_fact(card: dict, matrix: dict) -> list[str]:
    problems = []
    rows = {f.get("id"): f for f in matrix.get("facts", [])}
    for fact in card.get("facts", []):
        if fact.get("modality") != "human":
            continue
        for cap in (rows.get(fact["id"]) or {}).get("capabilities", []):
            if cap.get("kind") in ("deterministic", "model"):
                problems.append("事实 " + str(fact["id"]) + " 在卡里是人工事实，矩阵却给了 "
                                + str(cap.get("kind")) + " 能力：" + str(cap.get("id")))
    return problems

def check_gap_backstop(card: dict, matrix: dict) -> list[str]:
    problems = []
    rows = {f.get("id"): f for f in matrix.get("facts", [])}
    for gap in card.get("machine_check_gaps", []) or []:
        if gap.get("status") != "open":
            continue
        for fid in str(gap.get("fact") or "").split("/"):
            fid = fid.strip()
            if not fid:
                continue
            caps = (rows.get(fid) or {}).get("capabilities", [])
            if not any(c.get("kind") == "human" for c in caps):
                problems.append("事实 " + fid + " 有开放的机器缺口（"
                                + str(gap.get("missing")) + "），但没有人工能力兜底")
    return problems


def check_no_fake_green(card: dict, matrix: dict) -> list[str]:
    problems = []
    for fact in matrix.get("facts", []):
        verdict = fact.get("current_verdict") or {}
        if verdict.get("machine_passed") is not True:
            continue
        applicable_routes = [c for c in fact.get("capabilities", [])
                     if c.get("kind") == "deterministic"
                     and any((c.get("applies_on") or {}).values())]
        if not applicable_routes:
            problems.append("事实 " + str(fact.get("id"))
                            + " 声明机器判过，但没有任何适用的确定性能力")
    return problems


def check_unknown_blocks(card: dict, matrix: dict) -> list[str]:
    problems = []
    for fact in matrix.get("facts", []):
        caps = fact.get("capabilities", [])
        no_cap = (fact.get("status") == "no_capability_available") or not caps
        if not no_cap:
            continue
        if fact.get("blocking") is not True:
            problems.append("事实 " + str(fact.get("id"))
                            + " 没有可用能力，却没有声明阻断选择")
        if not fact.get("selection_policy"):
            problems.append("事实 " + str(fact.get("id"))
                            + " 没有可用能力，却没有写选择策略")
    return problems


def check_verdict_domain(card: dict, matrix: dict) -> list[str]:
    problems = []
    allowed = set(matrix.get("verdict_domain") or [])
    if not allowed:
        problems.append("矩阵顶层没有声明 verdict_domain")
        return problems
    for fact in matrix.get("facts", []):
        for cap in fact.get("capabilities", []):
            extra = set(cap.get("verdict_domain") or []) - allowed
            if extra:
                problems.append(str(fact.get("id")) + "/" + str(cap.get("id"))
                                + " 的结论域超出顶层取值域：" + ",".join(sorted(extra)))
    return problems


FACT_ID_RE = re.compile(r"\bF[0-9]+\b")


def check_sku_free_code(source_text: str, tokens: list) -> list[str]:
    """守卫自己必须与商品无关：源码里不许出现商品标识或事实编号字面量。"""
    problems = []
    for tok in tokens:
        if tok and tok in source_text:
            problems.append("守卫源码里出现了与商品绑定的字面量：" + str(tok))
    for hit in set(FACT_ID_RE.findall(source_text)):
        problems.append("守卫源码里出现了事实编号字面量：" + hit)
    return problems

def run_all(card: dict, matrix: dict, source_text: str, tokens: list) -> dict:
    return {
        "C1_COVERAGE": check_coverage(card, matrix),
        "C2_KIND": check_kind(card, matrix),
        "C3_PRECONDITION": check_precondition(card, matrix),
        "C4_DERIVATION": check_derivation(card, matrix),
        "C5_HUMAN_FACT": check_human_fact(card, matrix),
        "C6_GAP_BACKSTOP": check_gap_backstop(card, matrix),
        "C7_NO_FAKE_GREEN": check_no_fake_green(card, matrix),
        "C8_UNKNOWN_BLOCKS": check_unknown_blocks(card, matrix),
        "C9_SKU_FREE_CODE": check_sku_free_code(source_text, tokens),
        "C10_VERDICT_DOMAIN": check_verdict_domain(card, matrix),
    }


def first_deterministic(matrix: dict):
    for fact in matrix.get("facts", []):
        for cap in fact.get("capabilities", []):
            if cap.get("kind") == "deterministic":
                return fact, cap
    return None, None


def mutate(kind: str, card: dict, matrix: dict):
    card, matrix = copy.deepcopy(card), copy.deepcopy(matrix)
    facts = matrix.get("facts", [])
    if kind == "drop_fact":
        facts.pop()
    elif kind == "bad_kind":
        facts[0]["capabilities"][0]["kind"] = "magic"
    elif kind == "no_precondition":
        _, cap = first_deterministic(matrix)
        cap.pop("applies_when", None)
    elif kind == "no_derivation":
        _, cap = first_deterministic(matrix)
        (cap.get("calibration") or {}).pop("source", None)
    elif kind == "det_on_human_fact":
        target = next(m for m in facts if m["id"] == next(
            f["id"] for f in card["facts"] if f.get("modality") == "human"))
        target["capabilities"].append({"id": "x", "kind": "deterministic",
                                       "decides": "x", "requires_explicit_signature": False})
    elif kind == "no_backstop":
        open_ids = set()
        for gap in card.get("machine_check_gaps", []) or []:
            if gap.get("status") == "open":
                open_ids.update(p.strip() for p in str(gap.get("fact") or "").split("/"))
        target = next(m for m in facts if m["id"] in open_ids)
        target["capabilities"] = [c for c in target["capabilities"] if c.get("kind") != "human"]
    elif kind == "fake_green":
        _, cap = first_deterministic(matrix)
        cap["applies_on"] = {"controlled_backdrop_fixture": False}
        facts[0]["current_verdict"] = {"machine_passed": True}
    elif kind == "unknown_not_blocking":
        facts[0]["capabilities"] = []
        facts[0]["status"] = "no_capability_available"
        facts[0].pop("blocking", None)
        facts[0].pop("selection_policy", None)
    elif kind == "too_wide_domain":
        _, cap = first_deterministic(matrix)
        cap["verdict_domain"] = list(cap.get("verdict_domain") or []) + ["totally_fine"]
    return card, matrix


MUTATIONS = [
    ("drop_fact", "C1_COVERAGE"),
    ("bad_kind", "C2_KIND"),
    ("no_precondition", "C3_PRECONDITION"),
    ("no_derivation", "C4_DERIVATION"),
    ("det_on_human_fact", "C5_HUMAN_FACT"),
    ("no_backstop", "C6_GAP_BACKSTOP"),
    ("fake_green", "C7_NO_FAKE_GREEN"),
    ("unknown_not_blocking", "C8_UNKNOWN_BLOCKS"),
    ("too_wide_domain", "C10_VERDICT_DOMAIN"),
]

def resolve_paths(project: Path, sku: str):
    card_path = Path(project) / "demo" / "fixture" / sku / "product.json"
    matrix_path = Path(project) / "demo" / "fixture" / sku / "fact_capability.json"
    missing = [str(p) for p in (card_path, matrix_path) if not p.exists()]
    if missing:
        raise SystemExit("缺文件：" + "；".join(missing))
    return card_path, matrix_path


def do_check(project: Path, sku: str, as_json: bool) -> int:
    card_path, matrix_path = resolve_paths(project, sku)
    card = load_json(card_path)
    matrix = load_json(matrix_path)
    source_text = Path(__file__).read_text(encoding="utf-8")
    tokens = [str(matrix.get("sku") or ""), str(sku)]
    results = run_all(card, matrix, source_text, tokens)
    bad = {k: v for k, v in results.items() if v}

    print("事实验证能力矩阵守卫（离线 · 零付费 · 与商品无关）")
    print("事实卡：" + str(card_path))
    print("矩阵：" + str(matrix_path))
    print("事实：" + str(len(matrix.get("facts", []))) + " 条 · 能力声明："
          + str(sum(len(f.get("capabilities", [])) for f in matrix.get("facts", []))) + " 条")
    for rule in RULES:
        problems = results.get(rule, [])
        print(("  [OK  ] " if not problems else "  [FAIL] ") + rule
              + ("" if not problems else "（" + str(len(problems)) + " 条）"))
        if problems and not as_json:
            for line in problems[:5]:
                print("         · " + line)

    report = {"schema": "demo-fact-capability-check/1", "sku": matrix.get("sku"),
              "card": str(card_path.relative_to(project)),
              "matrix": str(matrix_path.relative_to(project)),
              "rules": {k: len(v) for k, v in results.items()}, "problems": bad}
    out = Path(project) / "evals" / "product-demo" / "d1-r1" / "fact-capability-check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("报告：" + str(out.relative_to(project)))
    if bad:
        print("结果：有规则不成立（退出码 2）")
        return 2
    print("结果：全过（退出码 0）")
    return 0


def do_self_test(project: Path, sku: str) -> int:
    card_path, matrix_path = resolve_paths(project, sku)
    card = load_json(card_path)
    matrix = load_json(matrix_path)
    source_text = Path(__file__).read_text(encoding="utf-8")
    tokens = [str(matrix.get("sku") or ""), str(sku)]

    print("能力矩阵守卫自检（每条反例必须触发对应规则）")
    base = run_all(card, matrix, source_text, tokens)
    base_bad = [k for k, v in base.items() if v]
    if base_bad:
        print("基线不成立，先修：" + ",".join(base_bad))
        return 1
    print("  [OK  ] 基线：十条规则全部为空")

    failures = 0
    for name, expected in MUTATIONS:
        m_card, m_matrix = mutate(name, card, matrix)
        injected = (m_card != card) or (m_matrix != matrix)
        res = run_all(m_card, m_matrix, source_text, tokens)
        fired = [k for k, v in res.items() if v]
        ok = injected and expected in fired
        failures += 0 if ok else 1
        print(("  [OK  ] " if ok else "  [FAIL] ") + name + "　→　" + expected
              + ("（触发：" + ",".join(fired) + "）" if fired else "（什么都没触发）"))

    bad_source = source_text + "\n#  " + tokens[0] + "\n"
    res = run_all(card, matrix, bad_source, tokens)
    ok9 = bool(res["C9_SKU_FREE_CODE"])
    failures += 0 if ok9 else 1
    print(("  [OK  ] " if ok9 else "  [FAIL] ") + "sku_literal_in_code　→　C9_SKU_FREE_CODE")

    print("自检：" + str(len(MUTATIONS) + 1 - failures) + "/" + str(len(MUTATIONS) + 1)
          + " 项被正确抓到")
    return 0 if failures == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="事实验证能力矩阵守卫")
    ap.add_argument("command", choices=["check", "self-test"])
    ap.add_argument("--project", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--sku", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    sku = args.sku
    if sku is None:
        roots = sorted(p.name for p in (project / "demo" / "fixture").iterdir()
                       if p.is_dir() and (p / "fact_capability.json").exists())
        if not roots:
            raise SystemExit("没有找到任何带能力矩阵的商品包；用 --sku 指定")
        sku = roots[0]
        print("未指定 --sku，使用：" + sku)
    if args.command == "check":
        return do_check(project, sku, args.json)
    return do_self_test(project, sku)


if __name__ == "__main__":
    sys.exit(main())