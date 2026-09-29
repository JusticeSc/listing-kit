# -*- coding: utf-8 -*-
"""D1.R3 验证器注册表：每个验证器显式声明「能判什么、凭什么、边界在哪」。

为什么要有注册表：PC-09 的路由不能靠 if/else 记住每个验证器的脾气。声明与实现分开之后，
三件事才可核对：

  1. 数据里出现的每一个责任者都必须在这里登记 —— 没登记就是未注册，不许静默跳过、
     更不许当成通过；
  2. 适用前提、结论域、证据形态、校准状态只有一处，不散落在实现里；
  3. 「未经对照校准的模型不得自动裁决」是一条**数据**（auto_adjudication），不是一句注释。

边界全部来自 D1.R1 的能力矩阵与 D1.R2 的对照，不是感想：

  · cylinder-v1（确定性）：只在 controlled_backdrop 成立时可用。D1.R2 实测四张场景候选的
    纯背景列里 15.8%–41.6% 的像素被判成主体，上限是 2%，所以整条不适用；它判尺寸与颜色类
    事实，不判同一性、不判文字。
  · refcond-vlm（模型）：默认只报 risk。D1.R2 对照里 6 个必须拦下的变异漏了 2 个
    （多两条筋、画面里多一个杯子），F6 上出现 4 条 Unknown —— 所以 auto_adjudication 保持
    false，直到有新的对照证据。
  · human：逐 {事实, 候选} 显式签字。聚合同意（"四张都 keep"）不是签字。

用法：
    python demo/verify/verifier_registry.py check --project .             # 与商品包数据交叉核对
    python demo/verify/verifier_registry.py self-test --project .         # 每种改坏必须让对应规则变红
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

VERDICT_DOMAIN = ["pass", "manual", "fail", "risk", "unknown", "not_applicable",
                 "needs_human"]
KINDS = ["deterministic", "model", "human"]

# 每条注册项都要有的字段：没有证据形态的结论无法追责，没有结论域的验证器无法被合并。
REQUIRED_FIELDS = ("id", "kind", "implemented_in", "verdict_domain", "evidence_shape",
                   "cannot_prove", "requires_declaration")

REGISTRY: dict = {
    "cylinder-v1": {
        "id": "cylinder-v1",
        "kind": "deterministic",
        "implemented_in": "demo/fixture/measure_cylinder.py（metric_profile = cylinder-v1）",
        # 与 D1.R1 矩阵 F1-F7 的逐能力结论域逐值对齐：实现另会给出 hard_fail/unknown，
        # 接口层把 hard_fail 归到 fail。注册表与矩阵不一致时 R8 会红。
        "verdict_domain": ["pass", "manual", "fail", "unknown", "not_applicable"],
        "on_not_applicable": "next_router",
        "evidence_shape": ["machine_checks", "metric_profile", "measured_colors",
                           "declared_colors", "image_size"],
        "requires_declaration": ["applies_when.probe", "applies_when.max_share"],
        "cannot_prove": ["同一 SKU 身份", "文字/水印", "F4 阶梯级数与盖顶开口", "F7 凸出物的语义"],
        "calibration": {
            "evidence": "evals/product-demo/d1-r1-fact-capability-matrix.md",
            "applicable_on": "受控底衬图（探针 ≤ 上限）",
            "not_applicable_on": "真实场景候选（D1.R2 探针 0.1584/0.3921/0.2063/0.4163，上限 0.02）",
            "rule_gaps": ["F4 级数", "F7 语义", "F8 文字"],
        },
    },
    "refcond-vlm": {
        "id": "refcond-vlm",
        "kind": "model",
        "implemented_in": "未实现；原型见 demo/verify/route_compare.py::route_b（D1.R2 对照脚本）",
        "model": "qwen-vl-max",
        "default_verdict": "risk",
        "auto_adjudication": False,
        "verdict_domain": ["risk", "unknown"],
        "evidence_shape": ["model", "request_sha256", "prompt_profile", "action_id", "usage"],
        "requires_declaration": ["model", "prompt_profile"],
        "cannot_prove": ["同一 SKU 身份", "材质/容量/认证等非视觉事实"],
        "calibration": {
            "evidence": "evals/product-demo/d1-r2-route-comparison-2026-09-26.md",
            "must_catch_total": 6,
            "must_catch_missed": 2,
            "missed_cases": ["neg-05-extra-ribs", "neg-06-second-cup"],
            "unknown_cluster": ["F6"],
            "note": "漏报未修、F6 未定清之前不得自动裁决；调高上限或换模型需要新的用户授权",
        },
    },
    "human": {
        "id": "human",
        "kind": "human",
        "implemented_in": "demo/core/back_chain.py::fact_routing，读商品包的 human_fact_review.json",
        "requires_explicit_signature": True,
        "signature_granularity": ["fact_id", "candidate_id"],
        "rejects": ["聚合同意", "没有指向具体事实的一般性同意", "缺审阅者或时间的记录"],
        "verdict_domain": ["pass", "fail", "unknown"],
        "evidence_shape": ["reviewer", "reviewer_kind", "reviewed_at", "source", "verdict"],
        "requires_declaration": ["source"],
        "cannot_prove": ["独立第三方复核（D1.R1 登记：审阅者是项目操作者）"],
        "calibration": {
            "evidence": "evals/product-demo/d1-r1-fact-capability-matrix.md",
            "note": "人工只能承担「谁给了结论」，不能承担「结论独立」",
        },
    },
}


# ------------------------------------------------------------------ 规则
def rule_unregistered_router(plan, matrix, reg):
    """数据里出现的责任者必须在注册表里 —— 没登记不许静默跳过。"""
    problems = []
    for route in plan.get("routes", []):
        for router in route.get("routers", []):
            if router.get("id") not in reg:
                problems.append(str(route.get("fact")) + " 的责任者 "
                                + repr(router.get("id")) + " 没有登记在验证器注册表里")
    return problems


def rule_missing_declaration(plan, matrix, reg):
    """每条注册项都要写全：能判什么、结论域、证据形态、不能证明什么、需要声明什么。"""
    problems = []
    for vid, cap in reg.items():
        for field in REQUIRED_FIELDS:
            if field not in cap or cap.get(field) in (None, "", [], {}):
                problems.append(vid + " 缺声明字段 " + field)
        if cap.get("kind") not in KINDS:
            problems.append(vid + " 的 kind 不在取值域：" + repr(cap.get("kind")))
        for v in cap.get("verdict_domain") or []:
            if v not in VERDICT_DOMAIN:
                problems.append(vid + " 的结论 " + repr(v) + " 不在取值域")
    return problems


def rule_model_auto_adjudication(plan, matrix, reg):
    """未校准的模型不得自动裁决：声明的漏报没清零之前，auto_adjudication 只能是 false。"""
    problems = []
    for vid, cap in reg.items():
        if cap.get("kind") != "model":
            continue
        cal = cap.get("calibration") or {}
        if cap.get("auto_adjudication") and int(cal.get("must_catch_missed") or 0) > 0:
            problems.append(vid + " 还漏报 " + str(cal.get("must_catch_missed"))
                            + " 例却允许自动裁决（对照证据：" + str(cal.get("evidence")) + "）")
        if not cal.get("evidence"):
            problems.append(vid + " 没有对照证据指针，无法证明它已校准")
    return problems


def rule_model_default_verdict(plan, matrix, reg):
    """不能自动裁决的模型，默认结论只能是 risk 或 unknown，不能是 pass/fail。"""
    problems = []
    for vid, cap in reg.items():
        if cap.get("kind") != "model" or cap.get("auto_adjudication"):
            continue
        if cap.get("default_verdict") not in ("risk", "unknown"):
            problems.append(vid + " 不能自动裁决，默认结论却是 "
                            + repr(cap.get("default_verdict")))
    return problems


def rule_deterministic_precondition(plan, matrix, reg):
    """确定性验证器必须声明适用前提与阈值，并把不适用交给下一个责任者。"""
    problems = []
    for vid, cap in reg.items():
        if cap.get("kind") != "deterministic":
            continue
        if cap.get("on_not_applicable") != "next_router":
            problems.append(vid + " 没有把不适用交给下一个责任者")
        if "not_applicable" not in (cap.get("verdict_domain") or []):
            problems.append(vid + " 的结论域不含 not_applicable")
        declared = set(cap.get("requires_declaration") or [])
        if "applies_when.probe" not in declared or "applies_when.max_share" not in declared:
            problems.append(vid + " 没有声明它需要数据提供适用性探针与阈值")
    # 数据那一侧也要真的写了：只有注册表声明、数据没写，路由就会拿到空前提
    for route in plan.get("routes", []):
        for router in route.get("routers", []):
            if router.get("kind") != "deterministic":
                continue
            cond = router.get("applies_when") or {}
            if not cond.get("probe") or cond.get("max_share") is None:
                problems.append(str(route.get("fact")) + " 的 " + str(router.get("id"))
                                + " 没有在数据里写全适用前提")
    return problems


def rule_human_signature(plan, matrix, reg):
    """人工验证器必须要求逐 {事实, 候选} 的显式签字。"""
    problems = []
    for vid, cap in reg.items():
        if cap.get("kind") != "human":
            continue
        if not cap.get("requires_explicit_signature"):
            problems.append(vid + " 是人工能力，却没有要求显式签字")
        gran = set(cap.get("signature_granularity") or [])
        if not {"fact_id", "candidate_id"} <= gran:
            problems.append(vid + " 的签字粒度不是逐 {事实, 候选}：" + repr(sorted(gran)))
        if not (cap.get("evidence_shape") or []):
            problems.append(vid + " 没有证据形态，结论无法追责")
    return problems


def rule_evidence_shape(plan, matrix, reg):
    """任何验证器都要有证据形态；没有证据形态的结论不能追责。"""
    problems = []
    for vid, cap in reg.items():
        if not cap.get("evidence_shape"):
            problems.append(vid + " 没有声明证据形态")
    return problems


def rule_matrix_alignment(plan, matrix, reg):
    """注册表与能力矩阵必须对得上：矩阵里说能判的，注册表要有同一项。"""
    problems = []
    for fact in matrix.get("facts", []):
        for cap in fact.get("capabilities", []):
            vid = cap.get("id")
            if vid not in reg:
                problems.append(str(fact.get("id")) + " 的能力 " + repr(vid)
                                + " 不在验证器注册表里")
                continue
            entry = reg[vid]
            if entry.get("kind") != cap.get("kind"):
                problems.append(vid + " 的 kind 与能力矩阵不一致：注册表 "
                                + str(entry.get("kind")) + "，矩阵 " + str(cap.get("kind")))
            can_judge = {"pass", "fail"} & set(cap.get("verdict_domain") or [])
            if can_judge and not ({"pass", "fail"} & set(entry.get("verdict_domain") or [])):
                problems.append(vid + " 在矩阵里能判 pass/fail，注册表的结论域却没有")
            # 矩阵的逐能力结论域不得比注册表更宽：宽出来的取值没有实现者，就是空头承诺
            outside = sorted(set(cap.get("verdict_domain") or [])
                             - set(entry.get("verdict_domain") or []))
            if outside:
                problems.append(vid + " 在矩阵里声称能给出 " + "、".join(outside)
                                + "，注册表的结论域里没有")
    return problems


def rule_human_only_fact(plan, matrix, reg):
    """矩阵判定为「机器不可判」的事实，数据里不许给它挂机器责任者。"""
    problems = []
    for fact in matrix.get("facts", []):
        caps = fact.get("capabilities", [])
        if not caps or any(c.get("kind") in ("deterministic", "model") for c in caps):
            continue
        fid = str(fact.get("id"))
        for route in plan.get("routes", []):
            if str(route.get("fact")) != fid:
                continue
            bad = [r.get("id") for r in route.get("routers", [])
                   if r.get("kind") in ("deterministic", "model")]
            if bad:
                problems.append(fid + " 在矩阵里只有人工能力，数据里却挂了机器责任者 "
                                + "、".join(map(str, bad)))
    return problems


RULES = [
    ("R1_UNREGISTERED_ROUTER", rule_unregistered_router),
    ("R2_DECLARATION", rule_missing_declaration),
    ("R3_MODEL_AUTO_ADJUDICATION", rule_model_auto_adjudication),
    ("R4_MODEL_DEFAULT_VERDICT", rule_model_default_verdict),
    ("R5_DETERMINISTIC_PRECONDITION", rule_deterministic_precondition),
    ("R6_HUMAN_SIGNATURE", rule_human_signature),
    ("R7_EVIDENCE_SHAPE", rule_evidence_shape),
    ("R8_MATRIX_ALIGNMENT", rule_matrix_alignment),
    ("R9_HUMAN_ONLY_FACT", rule_human_only_fact),
]


def run_all(plan, matrix, reg) -> dict:
    return {code: fn(plan, matrix, reg) for code, fn in RULES}


# ------------------------------------------------------------------ 入口
def load_package_data(project, sku=None):
    """商品包数据由包解析器给出；这里不写任何商品名（计划 §4.6 硬规矩 1、2）。"""
    sys.path.insert(0, str(project))
    from demo.core import packages as PKG          # 延迟导入：验证层不反向绑定处理链
    pkg = PKG.resolve(project, sku)
    return pkg, pkg.load("verifier_plan"), pkg.load("fact_capability")


def check(project, sku=None) -> int:
    pkg, plan, matrix = load_package_data(project, sku)
    print("验证器注册表守卫（离线 · 零付费 · 与商品无关）")
    print("商品包：" + pkg.root.as_posix())
    print("注册：" + str(len(REGISTRY)) + " 个验证器；数据：" + str(len(plan.get("routes", [])))
          + " 条事实路由")
    results = run_all(plan, matrix, REGISTRY)
    bad = 0
    for code, problems in results.items():
        mark = "OK  " if not problems else "FAIL"
        print("  [" + mark + "] " + code + ("" if not problems else "：" + "；".join(problems[:3])))
        bad += len(problems)
    print()
    print("结果：" + ("全过（退出码 0）" if bad == 0 else "有 " + str(bad) + " 条问题"))
    return 0 if bad == 0 else 1


def selftest(project, sku=None) -> int:
    pkg, plan, matrix = load_package_data(project, sku)
    base = run_all(plan, matrix, REGISTRY)
    problems = []
    print("注册表自检（每种改坏必须让对应规则变红）")
    if any(base.values()):
        print("  [FAIL] 基线：九条规则里有非空的：" + str({k: v for k, v in base.items() if v}))
        return 1
    print("  [OK  ] 基线：九条规则全部为空")

    def mutate_reg(fn):
        reg = copy.deepcopy(REGISTRY)
        fn(reg)
        return reg

    def mutate_plan(fn):
        p = copy.deepcopy(plan)
        fn(p)
        return p

    def matrix_case(patch):
        """矩阵那一侧的改坏共用：按 patch 改一份矩阵副本。"""
        m = copy.deepcopy(matrix)
        for fact in m.get("facts", []):
            for cap in fact.get("capabilities", []):
                if cap.get("kind") == "deterministic":
                    patch(cap)
                    return run_all(plan, m, REGISTRY)
        return {}

    cases = [
        ("drop_precondition", "R5_DETERMINISTIC_PRECONDITION", ["R5_DETERMINISTIC_PRECONDITION"],
         lambda: run_all(plan, matrix, mutate_reg(
             lambda r: r["cylinder-v1"].update({"on_not_applicable": "accept"})))),
        ("model_auto_adjudication", "R3_MODEL_AUTO_ADJUDICATION", ["R3_MODEL_AUTO_ADJUDICATION"],
         lambda: run_all(plan, matrix, mutate_reg(
             lambda r: r["refcond-vlm"].update({"auto_adjudication": True})))),
        ("model_default_pass", "R4_MODEL_DEFAULT_VERDICT", ["R4_MODEL_DEFAULT_VERDICT"],
         lambda: run_all(plan, matrix, mutate_reg(
             lambda r: r["refcond-vlm"].update({"default_verdict": "pass"})))),
        ("human_no_signature", "R6_HUMAN_SIGNATURE", ["R6_HUMAN_SIGNATURE"],
         lambda: run_all(plan, matrix, mutate_reg(
             lambda r: r["human"].update({"requires_explicit_signature": False})))),
        ("no_evidence_shape", "R7_EVIDENCE_SHAPE", ["R7_EVIDENCE_SHAPE", "R2_DECLARATION"],
         lambda: run_all(plan, matrix, mutate_reg(
             lambda r: r["cylinder-v1"].update({"evidence_shape": []})))),
        # 未注册责任者：注入一条 id 不在注册表、但适用前提写全的路由。
        # 前提写全会让 R5 的数据侧保持绿，于是只有 R1 应该变红。
        ("unregistered_router", "R1_UNREGISTERED_ROUTER", ["R1_UNREGISTERED_ROUTER"],
         lambda: run_all(mutate_plan(
             lambda p: p["routes"][0]["routers"].insert(
                 0, {"id": "some-other-verifier", "kind": "deterministic",
                     "applies_when": {"probe": "controlled_backdrop", "max_share": 0.02}})),
             matrix, REGISTRY)),
        ("matrix_capability_missing", "R8_MATRIX_ALIGNMENT", ["R8_MATRIX_ALIGNMENT"],
         lambda: matrix_case(lambda cap: cap.update({"id": "not-registered"}))),
        ("matrix_domain_widens", "R8_MATRIX_ALIGNMENT", ["R8_MATRIX_ALIGNMENT"],
         lambda: matrix_case(lambda cap: cap.update(
             {"id": "cylinder-v1", "verdict_domain": ["pass", "fail", "certified"]}))),
        ("human_only_fact_gets_machine", "R9_HUMAN_ONLY_FACT", ["R9_HUMAN_ONLY_FACT"],
         lambda: run_all(mutate_plan(
             lambda p: [r for r in p["routes"] if r["fact"] == "F8"][0]["routers"].insert(
                 0, {"id": "cylinder-v1", "kind": "deterministic",
                     "applies_when": {"probe": "controlled_backdrop", "max_share": 0.02}})),
             matrix, REGISTRY)),
    ]

    caught = 0
    total = 0
    for name, expect_rule, allowed, fn in cases:
        res = fn()
        total += 1
        hit = bool(res.get(expect_rule))
        extra = sorted(k for k, v in res.items() if v and k != expect_rule)
        unexpected = [k for k in extra if k not in allowed]
        if hit:
            caught += 1
        mark = "OK  " if hit else "FAIL"
        print("  [" + mark + "] " + name + "\u3000\u2192\u3000" + expect_rule
              + ("（已变红）" if hit else "（没有变红！）"))
        if extra:
            print("         一并变红：" + "、".join(extra)
                  + ("" if not unexpected else "\u3000\u2190 其中有未登记的"))
        if not hit:
            problems.append(name + " 没有让 " + expect_rule + " 变红")
        if unexpected:
            problems.append(name + " 还让未登记的规则变红：" + "、".join(unexpected))

    print()
    if problems:
        print("自检未通过：" + "；".join(problems))
        return 1
    print("自检：" + str(caught) + "/" + str(total) + " 种改坏都被对应规则抓住")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="验证器注册表守卫")
    ap.add_argument("mode", nargs="?", default="check", choices=["check", "self-test"],
                    help="check：与商品包数据交叉核对；self-test：每种改坏必须让对应规则变红")
    ap.add_argument("--project", default=str(ROOT))
    ap.add_argument("--sku", default=None)
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    if args.mode == "self-test":
        return selftest(project, args.sku)
    return check(project, args.sku)


if __name__ == "__main__":
    raise SystemExit(main())