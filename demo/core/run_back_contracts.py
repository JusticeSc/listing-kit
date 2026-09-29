#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D1.P3 —— 后半链契约测试（PC-08 – PC-13），离线、零付费调用。

它回答一个问题：§4.4 的后半链合同，是不是真的能被实现、也真的能被违反。

方法：一条黄金链走通六条合同（四张冻结候选逐张过技术检查与事实路由，再走
返工、选择、确定性合成、最终复检与导出），然后逐向注入一种缺陷，要求实现只报该报的结果。
每条反例都先自证「缺陷真的注入了」，再断言结果 —— 否则「没抓到」可能只是探针没改到东西。

用法：
    python demo/core/run_back_contracts.py            # 全跑，写报告
    python demo/core/run_back_contracts.py --json     # 机器读
    python demo/core/run_back_contracts.py --mutation-test

退出码：
    0  全部符合预期
    1  有反例没被抓住（实现或判据有问题）
    2  契约口径本身不成立
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.core import contracts as C        # noqa: E402
from demo.core import back_chain as B       # noqa: E402
from demo.core import front_chain as FC     # noqa: E402
from demo.verify import verifier_registry as REG   # noqa: E402  验证器能力注册表

LEDGER = ROOT / "evals/product-demo/first-round/ledger.jsonl"
OUT = ROOT / "evals/product-demo/d1-p3/back-contracts.json"

PLAN_ONE_SHOT = {"plan_version": "d1-p3-test", "shots": [{"shot_id": "S2",
                                                          "platform_slot": "scene"}]}
PLAN_FOUR_SHOTS = {"plan_version": "d1-p3-test",
                   "shots": [{"shot_id": s} for s in ("S1", "S2", "S3", "S4")]}

_ORIG = {
    "applicability_of": B.applicability_of,
    "fact_routing": B.fact_routing,
    "select_candidate": B.select_candidate,
    "rework": B.rework,
    "compose": B.compose,
    "technical_check": B.technical_check,
    "_next_package_dir": B._next_package_dir,
    "signature_index": B.signature_index,
}

# 变异用：一份声明被拿掉适用性前置的注册表副本（M12 直接把 REG.REGISTRY 换掉）。
WEAK_REGISTRY_NO_PRECONDITION = copy.deepcopy(REG.REGISTRY)
WEAK_REGISTRY_NO_PRECONDITION["cylinder-v1"]["on_not_applicable"] = "accept"



class Harness:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.tmp: list[Path] = []

    def workdir(self, prefix: str) -> Path:
        d = Path(tempfile.mkdtemp(prefix=prefix))
        self.tmp.append(d)
        return d

    def case(self, code: str, name: str, expect: str, result, checks: list[str],
             detail: dict | None = None) -> None:
        ok = (result.outcome == expect) and not checks
        self.rows.append({
            "case": code, "name": name, "contract": result.contract_id,
            "expect": expect, "actual": result.outcome, "ok": ok,
            "notes": list(result.notes), "failed_checks": checks,
            "detail": detail or {},
        })

    def cleanup(self) -> None:
        for d in self.tmp:
            shutil.rmtree(d, ignore_errors=True)


def raw_case(h: Harness, code: str, name: str, expect: str, actual: str,
             checks: list[str], detail: dict | None = None) -> None:
    h.rows.append({"case": code, "name": name, "contract": "-", "expect": expect,
                   "actual": actual, "ok": False, "notes": [], "failed_checks": checks,
                   "detail": detail or {}})


def golden(h: Harness):
    g = B.golden_candidates()
    return g


def human_with(h: Harness, mutate) -> dict:
    """复制一份人工事实记录再改坏 —— 真素材一个字节不动。"""
    g = golden(h)
    doc = copy.deepcopy(g["human_facts"])
    mutate(doc)
    return doc


def visual_with(h: Harness, cid: str, verdict: str) -> dict:
    g = golden(h)
    doc = copy.deepcopy(g["human_visual"])
    doc["reviews"][cid]["verdict"] = verdict
    return doc


def front_prompt_and_plan(h: Harness):
    r1 = FC.intake(ROOT)
    if not r1.accepted:
        raise RuntimeError("PC-01 未通过：" + str(r1.notes))
    r2 = FC.facts(ROOT, refpack=r1.payload)
    if not r2.accepted:
        raise RuntimeError("PC-02 未通过：" + str(r2.notes))
    r3 = FC.propose_plan(r2.payload, r1.payload, FC.platform_rules(ROOT),
                         goal=None, confirmed_by="demo-user")
    if not r3.accepted:
        raise RuntimeError("PC-03 未通过：" + str(r3.notes))
    r4 = FC.style_spec(r3.payload, r2.payload)
    r5 = FC.compile_prompt(r3.payload, r2.payload, r4.payload, "S2")
    if not r5.accepted:
        raise RuntimeError("PC-05 未通过：" + str(r5.notes))
    return r3.payload, r5.payload


def ledger_sha() -> str:
    return B.sha256_file(LEDGER)

def review_for(g: dict, ids) -> object:
    return B.visual_review("S2", list(ids), copy.deepcopy(g["human_visual"]))


# ---------------------------------------------------------------- 黄金链
def case_b0_golden(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    detail: dict = {}
    led_before = ledger_sha()
    work = h.workdir("back-golden-")

    p08 = {}
    for cid, cand in sorted(g["candidates"].items()):
        r = B.technical_check(cand, g["rules"])
        p08[cid] = r.outcome
        if not r.accepted:
            checks.append(f"PC-08 {cid} = {r.outcome}")
        if any(c["verdict"] == "not_applicable" for c in r.payload["checks"]
               if c["rule"] == "export_format") is False:
            checks.append(f"{cid}: 中间候选却判了导出格式")
    detail["pc08"] = p08

    p09, routes = {}, {}
    for cid, cand in sorted(g["candidates"].items()):
        r = B.fact_routing(cand, g["card"], g["verifier_plan"], g["human_facts"])
        p09[cid] = r.outcome
        routes[cid] = r.payload.get("route_summary")
        if not r.accepted:
            checks.append(f"PC-09 {cid} = {r.outcome}")
            continue
        if len(r.payload["facts"]) != 8:
            checks.append(f"{cid} 的事实条数不是 8：{len(r.payload['facts'])}")
        for f in r.payload["facts"]:
            kinds = {t.get("kind") for t in f["trail"]}
            if f["responsible"] == "cylinder-v1":
                checks.append(f"{cid} {f['fact_id']} 用了不适用的量测器给结论")
            if "deterministic" in kinds and not any(t["result"] == "not_applicable"
                                                    for t in f["trail"]):
                checks.append(f"{cid} {f['fact_id']} 的轨迹里没有适用性判定")
            if f["fact_id"] == "F8" and "deterministic" in kinds:
                checks.append(f"{cid}: F8 挂了确定性规则（机器代理已被证伪）")
        if r.payload["route_summary"].get("human") != 8:
            checks.append(f"{cid} 的人工承担条数 {r.payload['route_summary']} 期望 8")
    detail["pc09"] = p09
    detail["pc09_routes"] = routes

    r10 = review_for(g, sorted(g["candidates"]))
    if not r10.accepted:
        checks.append(f"PC-10 = {r10.outcome}")
    if r10.payload.get("no_composite_score") is not True:
        checks.append("PC-10 报告里没有声明「不生成总分」")

    plan, pv = front_prompt_and_plan(h)
    state = {"shots": {
        "S1": {"candidate_sha256": ["a" * 8], "submit_count": 1},
        "S2": {"candidate_sha256": [c["sha256"] for c in g["candidates"].values()],
               "submit_count": 4},
        "S3": {"candidate_sha256": ["b" * 8], "submit_count": 1},
    }}
    r11 = B.rework(shot_id="S2", reason_code="background_clutter", plan=plan,
                   state=state, prompt_version=pv)
    if not r11.accepted:
        checks.append(f"PC-11 = {r11.outcome} {r11.notes}")
    else:
        ch = r11.payload["change"]
        nv = ch.get("new_prompt_version") or {}
        if ch["category"] != "scene_composition":
            checks.append(f"返工分类 {ch['category']} 不是 scene_composition")
        if nv.get("parent") != pv["version_id"]:
            checks.append("返工没有保留父版本")
        if nv.get("locks_facts") != pv["locks_facts"]:
            checks.append("返工改动了事实锁")
        unt = {u["shot_id"] for u in r11.payload["untouched_shots"]}
        if unt != {"S1", "S3"}:
            checks.append(f"未受影响 Shot 记录不对：{unt}")
        for u in r11.payload["untouched_shots"]:
            src = state["shots"][u["shot_id"]]
            if u["submit_count"] != src["submit_count"]:
                checks.append(f"{u['shot_id']} 的提交数变了")
            if u["candidate_sha256"] != src["candidate_sha256"]:
                checks.append(f"{u['shot_id']} 的候选哈希变了")
        detail["rework"] = {"category": ch["category"],
                            "new_prompt_version": nv.get("version_id"),
                            "untouched": sorted(unt)}

    # 四候选逐一走完整后半链：技术检查 -> 事实路由 -> 选择 -> 合成 -> 最终复检 -> 导出
    per_candidate = {}
    for cid, cand in sorted(g["candidates"].items()):
        row = {}
        r09c = B.fact_routing(cand, g["card"], g["verifier_plan"], g["human_facts"])
        sel_c = B.select_candidate(shot_id="S2", candidate=cand, fact_result=r09c, review=r10)
        row["facts"] = r09c.outcome
        row["select"] = sel_c.outcome
        if sel_c.accepted:
            comp_c = B.compose(sel_c.payload["selection"], cand,
                               out_dir=work / ("path-" + cid))
            row["compose"] = comp_c.outcome
            if comp_c.accepted:
                fin_c = B.finalize(compositions=[comp_c.payload], plan=PLAN_ONE_SHOT,
                                   rules=g["rules"], out_dir=work / ("pkgs-" + cid))
                row["finalize"] = fin_c.outcome
                if fin_c.accepted:
                    code_c, _ = B.verify_package(fin_c.payload["output_version"]["dir"])
                    row["verify_rc"] = code_c
                    if code_c != 0:
                        checks.append(f"{cid} 的导出包换目录核验失败")
                else:
                    checks.append(f"{cid} 最终复检 = {fin_c.outcome}")
            else:
                checks.append(f"{cid} 合成 = {comp_c.outcome}")
                row["finalize"] = "-"
        else:
            checks.append(f"{cid} 选择 = {sel_c.outcome}")
            row["compose"] = row["finalize"] = "-"
        per_candidate[cid] = row
    detail["per_candidate_path"] = per_candidate

    f03 = g["candidates"]["F-03"]
    r09 = B.fact_routing(f03, g["card"], g["verifier_plan"], g["human_facts"])
    sel = B.select_candidate(shot_id="S2", candidate=f03, fact_result=r09, review=r10)
    if not sel.accepted:
        checks.append(f"PC-12 选择 = {sel.outcome} {sel.notes}")
    comp = B.compose(sel.payload["selection"], f03, out_dir=work / "comp") \
        if sel.accepted else sel
    if not comp.accepted:
        checks.append(f"PC-12 合成 = {comp.outcome} {comp.notes}")
    else:
        if comp.payload["kind"] != "identity":
            checks.append("无文案时应记录恒等合成")
        if not comp.payload["pixels_unchanged"]:
            checks.append("恒等合成的输出与候选不一致")
        detail["composition"] = {"kind": comp.payload["kind"],
                                 "sha256": comp.payload["output_sha256"]}

    fin = B.finalize(compositions=[comp.payload], plan=PLAN_ONE_SHOT,
                     rules=g["rules"], out_dir=work / "pkgs") if comp.accepted else comp
    if not fin.accepted:
        checks.append(f"PC-13 = {fin.outcome} {fin.notes}")
    else:
        pkg = fin.payload["output_version"]["dir"]
        code, rep = B.verify_package(pkg)
        if code != 0:
            checks.append(f"换目录核验失败：{rep}")
        if len(fin.payload["output_version"]["files"]) != 1:
            checks.append("导出文件数不是 1")
        detail["package"] = Path(pkg).name
        detail["verify"] = rep

    if ledger_sha() != led_before:
        checks.append("账本变了：本次不该有任何付费动作")
    bad_mock = [cid for cid, c in g["candidates"].items() if c.get("input_image_count") != 1]
    if bad_mock:
        checks.append(f"这些候选的 input_image_count 不是 1：{bad_mock}")
    detail["candidates_input_image_count"] = {cid: c.get("input_image_count")
                                             for cid, c in sorted(g["candidates"].items())}
    h.case("B0", "黄金后半链（PC-08…PC-13）", "accepted", fin, checks, detail)


# ---------------------------------------------------------------- 反例
def case_b1_applicability(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    detail: dict = {}
    router = g["verifier_plan"]["routes"][0]["routers"][0]
    for cid, cand in sorted(g["candidates"].items()):
        app = B.applicability_of(router, cand)
        share = app["measured"]["subject_share_in_band"]
        detail[cid] = {"share": share, "applicable": app["applicable"]}
        if app["applicable"]:
            checks.append(f"{cid} 被判成适用（纯背景列主体占比 {share}）")
        if share <= app["max_share"]:
            checks.append(f"{cid} 的探针读数没有超过阈值 —— 这个反例没有真的注入缺陷")
    fixture = ROOT / "evals/product-demo/fixture-design/pack/01-front-full.png"
    app_f = B.applicability_of(router, {"file": str(fixture)})
    detail["fixture_front_full"] = {"share": app_f["measured"]["subject_share_in_band"],
                                    "applicable": app_f["applicable"]}
    if not app_f["applicable"]:
        checks.append("棚拍夹具上探针也应适用，否则它只会说「不适用」")
    r = B.fact_routing(g["candidates"]["F-01"], g["card"], g["verifier_plan"],
                       g["human_facts"])
    if not r.accepted:
        checks.append(f"不适用被读成了失败：PC-09 = {r.outcome}")
    h.case("B1", "场景候选上 cylinder-v1 必须判不适用而非失败", "accepted", r, checks, detail)


def case_b2_missing_signature(h: Harness) -> None:
    g = golden(h)
    full = len(g["human_facts"]["records"])
    doc = human_with(h, lambda d: d.__setitem__(
        "records", [r for r in d["records"]
                    if not (r["fact_id"] == "F5" and r["candidate_id"] == "F-03")]))
    checks: list[str] = []
    if len(doc["records"]) != full - 1:
        checks.append("沙箱里其实没删掉那条签字（探针失效）")
    r = B.fact_routing(g["candidates"]["F-03"], g["card"], g["verifier_plan"], doc)
    if r.outcome != "needs_human":
        checks.append(f"缺签字时结果是 {r.outcome}，应为 needs_human")
    unresolved = [f["fact_id"] for f in r.payload["facts"]
                  if f["verdict"] in (None, "unknown", "needs_human")]
    if "F5" not in unresolved:
        checks.append(f"未决事实里没有 F5：{unresolved}")
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-03"], fact_result=r,
                             review=review_for(g, ["F-03"]))
    if sel.outcome != "business_reject":
        checks.append(f"未决事实没有挡住选择：{sel.outcome}")
    h.case("B2", "缺人工签字的事实保持未决并阻断选择", "needs_human", r, checks,
           {"records": len(doc["records"]), "unresolved": unresolved})


def case_b3_signed_unknown(h: Harness) -> None:
    g = golden(h)
    doc = human_with(h, lambda d: [r.update({"verdict": "unknown"})
                                   for r in d["records"]
                                   if r["fact_id"] == "F2" and r["candidate_id"] == "F-02"])
    checks: list[str] = []
    got = [r for r in doc["records"]
           if r["fact_id"] == "F2" and r["candidate_id"] == "F-02"][0]["verdict"]
    if got != "unknown":
        checks.append("沙箱里的签字其实没改成 unknown（探针失效）")
    r = B.fact_routing(g["candidates"]["F-02"], g["card"], g["verifier_plan"], doc)
    if r.outcome != "needs_human":
        checks.append(f"签字为 unknown 时结果是 {r.outcome}，应为 needs_human")
    h.case("B3", "人工标 unknown 的事实不得被当成通过", "needs_human", r, checks,
           {"F2": got})


def case_b4_signed_fail(h: Harness) -> None:
    g = golden(h)
    doc = human_with(h, lambda d: [r.update({"verdict": "fail"})
                                   for r in d["records"]
                                   if r["fact_id"] == "F2" and r["candidate_id"] == "F-03"])
    checks: list[str] = []
    r = B.fact_routing(g["candidates"]["F-03"], g["card"], g["verifier_plan"], doc)
    if r.outcome != "business_reject":
        checks.append(f"签字为 fail 时结果是 {r.outcome}，应为 business_reject")
    fails = [f["fact_id"] for f in r.payload["facts"] if f["verdict"] == "fail"]
    if fails != ["F2"]:
        checks.append(f"硬失败事实列表是 {fails}，期望 ['F2']")
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-03"],
                             fact_result=r, review=review_for(g, ["F-03"]))
    if sel.outcome != "business_reject":
        checks.append(f"事实硬失败却仍然可以选择：{sel.outcome}")
    h.case("B4", "人工判 fail 的事实让候选不可用", "business_reject", r, checks,
           {"fails": fails, "selection": sel.outcome})


def case_b5_keep_cannot_cover_fail(h: Harness) -> None:
    g = golden(h)
    doc = human_with(h, lambda d: [r.update({"verdict": "fail"})
                                   for r in d["records"]
                                   if r["fact_id"] == "F2" and r["candidate_id"] == "F-03"])
    checks: list[str] = []
    r = B.fact_routing(g["candidates"]["F-03"], g["card"], g["verifier_plan"], doc)
    rev = review_for(g, ["F-03"])
    if rev.payload["reviews"]["F-03"]["verdict"] != "keep":
        checks.append("这份审美记录不是 keep（探针失效）")
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-03"],
                             fact_result=r, review=rev)
    if sel.outcome != "business_reject":
        checks.append(f"审美 keep 覆盖了事实 fail：选择结果 {sel.outcome}")
    h.case("B5", "审美 keep 不能覆盖事实 fail", "business_reject", sel, checks,
           {"visual": rev.payload["reviews"]["F-03"]["verdict"],
            "fact_outcome": r.outcome})


def case_b6_redo_not_selectable(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    rev = review_for(g, sorted(g["candidates"]))
    rev.payload["reviews"]["F-01"] = dict(rev.payload["reviews"]["F-01"],
                                          verdict="redo",
                                          reasons=["背景干扰"],
                                          notes="变异：标为重做")
    if rev.payload["reviews"]["F-01"]["verdict"] != "redo":
        checks.append("审美记录其实没改成 redo（探针失效）")
    r09 = B.fact_routing(g["candidates"]["F-01"], g["card"], g["verifier_plan"],
                         g["human_facts"])
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-01"],
                             fact_result=r09, review=rev)
    if sel.outcome != "business_reject":
        checks.append(f"redo 的候选被选中了：{sel.outcome}")
    h.case("B6", "人工判 redo 的候选不可选", "business_reject", sel, checks,
           {"visual": rev.payload["reviews"]["F-01"]["verdict"]})


def case_b7_unclassified_reason(h: Harness) -> None:
    g = golden(h)
    plan, pv = front_prompt_and_plan(h)
    checks: list[str] = []
    if B.classify_reason("mystery_reason") != "unclassified":
        checks.append("分类器其实认得这个原因（探针失效）")
    r = B.rework(shot_id="S2", reason_code="mystery_reason", plan=plan, prompt_version=pv)
    if r.outcome != "needs_human":
        checks.append(f"归不了类的原因结果是 {r.outcome}，应为 needs_human")
    if r.payload.get("category") != "unclassified":
        checks.append("没有给出 unclassified 分类")
    h.case("B7", "归不了类的返工原因交人工，不自动重跑", "needs_human", r, checks,
           {"category": r.payload.get("category")})


def case_b8_rework_isolation(h: Harness) -> None:
    g = golden(h)
    plan, pv = front_prompt_and_plan(h)
    checks: list[str] = []
    state = {"shots": {
        "S1": {"candidate_sha256": ["a" * 8], "submit_count": 1},
        "S2": {"candidate_sha256": [c["sha256"] for c in g["candidates"].values()],
               "submit_count": 4},
        "S3": {"candidate_sha256": ["b" * 8], "submit_count": 1},
    }}
    r = B.rework(shot_id="S2", reason_code="lighting_harsh", plan=plan, state=state,
                 prompt_version=pv)
    if not r.accepted:
        checks.append(f"PC-11 = {r.outcome} {r.notes}")
    else:
        unt = {u["shot_id"]: u for u in r.payload["untouched_shots"]}
        if set(unt) != {"S1", "S3"}:
            checks.append(f"未受影响 Shot 集合是 {set(unt)}")
        for sid, u in unt.items():
            if u["submit_count"] != state["shots"][sid]["submit_count"]:
                checks.append(f"{sid} 的提交数从 {state['shots'][sid]['submit_count']} "
                              f"变成了 {u['submit_count']}")
            if u["candidate_sha256"] != state["shots"][sid]["candidate_sha256"]:
                checks.append(f"{sid} 的候选哈希变了")
        if r.payload["old_candidates_kept"] is not True:
            checks.append("没有声明旧候选保留")
        if r.payload["target_old_candidates"] != state["shots"]["S2"]["candidate_sha256"]:
            checks.append("目标 Shot 的旧候选没有被记录")
    h.case("B8", "单图返工不动其它 Shot（提交数与哈希都不变）", "accepted", r, checks,
           {"untouched": r.payload.get("untouched_shots")})

def case_b9_double_selection(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    r10 = review_for(g, sorted(g["candidates"]))
    r09 = B.fact_routing(g["candidates"]["F-03"], g["card"], g["verifier_plan"],
                         g["human_facts"])
    first = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-03"],
                               fact_result=r09, review=r10)
    if not first.accepted:
        checks.append(f"第一次选择就没成功：{first.outcome}")
    second = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-01"],
                                fact_result=B.fact_routing(
                                    g["candidates"]["F-01"], g["card"],
                                    g["verifier_plan"], g["human_facts"]),
                                review=r10, existing=first.payload.get("selection"))
    if second.outcome != "business_reject":
        checks.append(f"同一张图的第二次选择被接受：{second.outcome}")
    h.case("B9", "同一张图已有选择时不许后写覆盖", "business_reject", second, checks,
           {"first": first.payload.get("selection", {}).get("candidate_id")})


def case_b10_overflow(h: Harness) -> None:
    g = golden(h)
    work = h.workdir("back-b10-")
    checks: list[str] = []
    r10 = review_for(g, ["F-03"])
    r09 = B.fact_routing(g["candidates"]["F-03"], g["card"], g["verifier_plan"],
                         g["human_facts"])
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-03"],
                             fact_result=r09, review=r10)
    out = work / "comp"
    r = B.compose(sel.payload["selection"], g["candidates"]["F-03"], out_dir=out,
                  text_spec={"text": "Aster 01 insulated stainless steel tumbler",
                             "box": {"x": 0, "y": 0, "w": 40, "h": 16}, "size": 28})
    if r.outcome != "technical_fail":
        checks.append(f"溢出没有被判失败：{r.outcome}")
    if any(out.glob("*.png")):
        checks.append("溢出失败却仍然写出了文件")
    h.case("B10", "排版溢出必须判失败且不产出文件", "technical_fail", r, checks,
           {"text_px": r.payload.get("text_px"), "box": r.payload.get("box")})


def case_b11_font_missing(h: Harness) -> None:
    g = golden(h)
    work = h.workdir("back-b11-")
    checks: list[str] = []
    bogus = str(ROOT / "demo" / "core" / "definitely-not-a-font.ttf")
    if Path(bogus).exists():
        checks.append("那个不存在的字体路径其实存在（探针失效）")
    r10 = review_for(g, ["F-03"])
    r09 = B.fact_routing(g["candidates"]["F-03"], g["card"], g["verifier_plan"],
                         g["human_facts"])
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-03"],
                             fact_result=r09, review=r10)
    r = B.compose(sel.payload["selection"], g["candidates"]["F-03"], out_dir=work / "comp",
                  text_spec={"text": "Aster 01",
                             "box": {"x": 0, "y": 0, "w": 400, "h": 80}, "size": 28},
                  font_path=bogus)
    if r.outcome != "technical_fail":
        checks.append(f"字体缺失没有被判失败：{r.outcome}")
    h.case("B11", "字体缺失必须判失败，不自动换字体", "technical_fail", r, checks,
           {"font": bogus})


def case_b12_final_file_fails(h: Harness) -> None:
    from PIL import Image
    g = golden(h)
    work = h.workdir("back-b12-")
    checks: list[str] = []
    cand = g["candidates"]["F-03"]
    sel = B.select_candidate(shot_id="S2", candidate=cand,
                             fact_result=B.fact_routing(cand, g["card"],
                                                        g["verifier_plan"], g["human_facts"]),
                             review=review_for(g, ["F-03"]))
    comp = B.compose(sel.payload["selection"], cand, out_dir=work / "comp",
                     text_spec={"text": "Aster 01",
                                "box": {"x": 40, "y": 40, "w": 600, "h": 120}, "size": 48},
                     size_override=[800, 800])
    if not comp.accepted:
        checks.append(f"合成没成功，反例不成立：{comp.outcome}")
        h.case("B12", "最终文件不合格时不发布", "technical_fail", comp, checks, {})
        return
    with Image.open(comp.payload["output"]) as im:
        size = im.size
    if max(size) >= int(g["rules"]["min_long_side_px"]):
        checks.append(f"合成文件其实没变小（{size}），缺陷没注入")
    if not B.technical_check(cand, g["rules"]).accepted:
        checks.append("中间候选本身就没过，这个反例不成立")
    fin = B.finalize(compositions=[comp.payload], plan=PLAN_ONE_SHOT, rules=g["rules"],
                     out_dir=work / "pkgs")
    if fin.outcome != "technical_fail":
        checks.append(f"最终文件不合格却没有失败：{fin.outcome}")
    pkg = Path(fin.payload.get("package", "")) if fin.payload.get("package") else None
    if pkg and (pkg / "manifest.json").exists():
        checks.append("失败却仍然写了清单（等于宣布发布）")
    h.case("B12", "最终文件不合格时不发布该版本", "technical_fail", fin, checks,
           {"composition_size": size, "candidate_ok": True})


def case_b13_coverage(h: Harness) -> None:
    g = golden(h)
    work = h.workdir("back-b13-")
    checks: list[str] = []
    cand = g["candidates"]["F-03"]
    sel = B.select_candidate(shot_id="S2", candidate=cand,
                             fact_result=B.fact_routing(cand, g["card"],
                                                        g["verifier_plan"], g["human_facts"]),
                             review=review_for(g, ["F-03"]))
    comp = B.compose(sel.payload["selection"], cand, out_dir=work / "comp")
    fin = B.finalize(compositions=[comp.payload], plan=PLAN_FOUR_SHOTS, rules=g["rules"],
                     out_dir=work / "pkgs")
    if fin.outcome != "business_reject":
        checks.append(f"计划覆盖不全却没有被拒：{fin.outcome}")
    if fin.payload.get("missing") != ["S1", "S3", "S4"]:
        checks.append(f"缺图清单不对：{fin.payload.get('missing')}")
    h.case("B13", "计划里的图没有全部选中时不许导出", "business_reject", fin, checks,
           {"missing": fin.payload.get("missing")})


def case_b14_tamper(h: Harness) -> None:
    g = golden(h)
    work = h.workdir("back-b14-")
    checks: list[str] = []
    cand = g["candidates"]["F-03"]
    sel = B.select_candidate(shot_id="S2", candidate=cand,
                             fact_result=B.fact_routing(cand, g["card"],
                                                        g["verifier_plan"], g["human_facts"]),
                             review=review_for(g, ["F-03"]))
    comp = B.compose(sel.payload["selection"], cand, out_dir=work / "comp")
    fin = B.finalize(compositions=[comp.payload], plan=PLAN_ONE_SHOT, rules=g["rules"],
                     out_dir=work / "pkgs")
    pkg = Path(fin.payload["output_version"]["dir"])
    code_ok, rep_ok = B.verify_package(pkg)
    if code_ok != 0:
        checks.append(f"未篡改时核验就失败了：{rep_ok}")
    target = pkg / fin.payload["output_version"]["files"][0]["file"]
    with target.open("ab") as fh:
        fh.write(b"tampered")
    code_bad, rep_bad = B.verify_package(pkg)
    if code_bad == 0:
        checks.append("篡改一个字节后核验仍然通过")
    if not any("哈希" in p for p in rep_bad.get("problems", [])):
        checks.append(f"篡改后的问题列表里没有哈希不一致：{rep_bad.get('problems')}")
    h.case("B14", "导出包被改写时换目录核验必须报红", "accepted", fin, checks,
           {"verify_before": code_ok, "verify_after": code_bad,
            "problems": rep_bad.get("problems")})


def case_b15_reexport(h: Harness) -> None:
    g = golden(h)
    work = h.workdir("back-b15-")
    checks: list[str] = []
    cand = g["candidates"]["F-03"]
    sel = B.select_candidate(shot_id="S2", candidate=cand,
                             fact_result=B.fact_routing(cand, g["card"],
                                                        g["verifier_plan"], g["human_facts"]),
                             review=review_for(g, ["F-03"]))
    ident = B.compose(sel.payload["selection"], cand, out_dir=work / "c1")
    text = B.compose(sel.payload["selection"], cand, out_dir=work / "c2",
                     text_spec={"text": "Aster 01",
                                "box": {"x": 40, "y": 40, "w": 600, "h": 120}, "size": 48})
    if not (ident.accepted and text.accepted):
        checks.append("两次合成没有都成功，反例不成立")
    fin1 = B.finalize(compositions=[ident.payload], plan=PLAN_ONE_SHOT, rules=g["rules"],
                      out_dir=work / "pkgs", package_id="pkg-test")
    pkg1 = Path(fin1.payload["output_version"]["dir"]) if fin1.accepted else None
    before = {f["file"]: f["sha256"] for f in fin1.payload["output_version"]["files"]} \
        if pkg1 else {}
    fin2 = B.finalize(compositions=[text.payload], plan=PLAN_ONE_SHOT, rules=g["rules"],
                      out_dir=work / "pkgs", package_id="pkg-test")
    pkg2 = Path(fin2.payload["output_version"]["dir"]) if fin2.accepted else None
    if pkg1 and pkg2 and pkg1 == pkg2:
        checks.append("重导用了同一个包目录（旧包被覆盖）")
    if pkg1:
        for name, sha in before.items():
            if not (pkg1 / name).exists():
                checks.append(f"旧包里的 {name} 不见了")
            elif B.sha256_file(pkg1 / name) != sha:
                checks.append(f"旧包里的 {name} 被改写了")
    if pkg2 and pkg1 and pkg2.is_dir():
        kinds = [f["composition_kind"] for f in fin2.payload["output_version"]["files"]]
        if kinds != ["text_overlay"]:
            checks.append(f"新包里记录的合成方式是 {kinds}")
    h.case("B15", "重导创建新版本且不覆盖旧包", "accepted", fin2, checks,
           {"pkg1": pkg1.name if pkg1 else None, "pkg2": pkg2.name if pkg2 else None})


def case_b16_rule_without_param(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    rules = dict(g["rules"])
    rules.pop("min_long_side_px", None)
    if "min_long_side_px" in rules:
        checks.append("规则其实没被拿掉（探针失效）")
    r = B.technical_check(g["candidates"]["F-01"], rules)
    if r.outcome != "unknown":
        checks.append(f"规则缺参数时结果是 {r.outcome}，应为 unknown")
    if not any(c["rule"] == "min_long_side_px" and c["verdict"] == "unknown"
               for c in r.payload["checks"]):
        checks.append("缺参数的那条规则没有被标成 unknown")
    h.case("B16", "规则缺参数时判 unknown，不判失败", "unknown", r, checks, {})


def case_b17_no_invented_state(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    for cid, outcome in (("PC-08", "business_reject"), ("PC-12", "needs_human"),
                         ("PC-10", "technical_fail")):
        try:
            C.StepResult(cid, outcome, notes=["人"])
        except C.ContractViolation:
            pass
        else:
            checks.append(f"{cid} 接受了合同没声明的 {outcome}")
    try:
        C.StepResult("PC-99", "accepted")
    except C.ContractViolation:
        pass
    else:
        checks.append("未登记的合同 ID 被接受")
    r = B.technical_check(g["candidates"]["F-01"], g["rules"])
    h.case("B17", "实现不许自造合同没声明的状态", "accepted", r, checks, {})


def case_b18_unregistered_router(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    plan = copy.deepcopy(g["verifier_plan"])
    route = next(r for r in plan["routes"] if r["fact"] == "F4")
    route["routers"] = [{"id": "ghost-verifier", "kind": "model"}]
    r = B.fact_routing(g["candidates"]["F-01"], g["card"], plan, g["human_facts"])
    f4 = next(f for f in r.payload["facts"] if f["fact_id"] == "F4")
    results = [t["result"] for t in f4["trail"]]
    if "unregistered_router" not in results:
        checks.append(f"未注册的责任者没有被显式记下：{results}")
    if f4["verdict"] is not None:
        checks.append(f"未注册的责任者仍然给出了结论：{f4['verdict']}")
    if r.outcome != "needs_human":
        checks.append(f"结果是 {r.outcome}；未注册的责任者应让事实保持未决")
    item = next(i for i in r.payload["review_items"] if i["fact_id"] == "F4")
    if item["state"] != "unresolved":
        checks.append(f"ReviewItem 状态是 {item['state']}，期望 unresolved")
    if item["owner"] is not None:
        checks.append("未注册的责任者不该被写成 ReviewItem 的责任者")
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-01"], fact_result=r,
                             review=review_for(g, ["F-01"]))
    if sel.outcome != "business_reject":
        checks.append(f"未注册的责任者没有挡住选择：{sel.outcome}")
    h.case("B18", "未注册的责任者不得静默跳过或当成通过", "needs_human", r, checks,
           {"trail": results})


def case_b19_review_items(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    r = B.fact_routing(g["candidates"]["F-01"], g["card"], g["verifier_plan"], g["human_facts"])
    items = r.payload.get("review_items") or []
    facts = r.payload["facts"]
    if not items or len(items) != len(facts):
        checks.append(f"ReviewItem 条数 {len(items)} 与事实条数 {len(facts)} 不一致")
    by_fact = {i["fact_id"]: i for i in items}
    if len(by_fact) != len(items):
        checks.append("ReviewItem 的 fact_id 有重复")
    for f in facts:
        it = by_fact.get(f["fact_id"])
        if it is None:
            checks.append(f"{f['fact_id']} 没有 ReviewItem")
            continue
        if it["candidate_id"] != "F-01":
            checks.append(f"{f['fact_id']} 的 ReviewItem 没有绑定到具体候选")
        if it["owner"] != f["responsible"]:
            checks.append(f"{f['fact_id']} 的责任者与事实记录不一致")
        if it["verdict"] != f["verdict"]:
            checks.append(f"{f['fact_id']} 的结论与事实记录不一致")
        if f["responsible"] and not it["evidence_pointer"]:
            checks.append(f"{f['fact_id']} 有责任者却没有证据指针")
        if f["responsible"] and not it["evidence_required"]:
            checks.append(f"{f['fact_id']} 的责任者没有带出注册表声明的证据形态")
    human_shape = REG.REGISTRY["human"]["evidence_shape"]
    if by_fact["F4"]["evidence_required"] != human_shape:
        checks.append("ReviewItem 的证据形态与注册表声明不一致")
    h.case("B19", "逐事实 ReviewItem 带责任者、证据指针与结论", "accepted", r, checks,
           {"items": len(items), "human_evidence_shape": human_shape})


def case_b20_aggregate_consent(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    doc = copy.deepcopy(g["human_facts"])
    per_item = len(doc.get("records") or [])
    if per_item == 0:
        checks.append("沙箱里本来就没有逐条签字（探针失效）")
    doc["records"] = [{"fact_id": "*", "candidate_id": "*", "verdict": "pass",
                       "reviewer": "project-operator",
                       "reviewer_kind": "not_independent_third_party",
                       "source": "聚合：四张候选整组通过（本轮反例）"}]
    r = B.fact_routing(g["candidates"]["F-01"], g["card"], g["verifier_plan"], doc)
    if r.outcome != "needs_human":
        checks.append(f"聚合同意被读成了签字：PC-09 = {r.outcome}")
    items = {i["fact_id"]: i for i in r.payload["review_items"]}
    resolved = sorted(fid for fid, i in items.items() if i["state"] == "resolved")
    if resolved:
        checks.append(f"这些事实被聚合同意判成了有结论：{resolved}")
    if items["F4"]["evidence_pointer"] is not None:
        checks.append("没有签字的事实却带了证据指针")
    decl = REG.REGISTRY["human"]
    if decl.get("signature_granularity") != ["fact_id", "candidate_id"]:
        checks.append(f"注册表的签字粒度是 {decl.get('signature_granularity')}")
    if not decl.get("requires_explicit_signature"):
        checks.append("注册表没有要求显式签字")
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"]["F-01"], fact_result=r,
                             review=review_for(g, ["F-01"]))
    if sel.outcome != "business_reject":
        checks.append(f"聚合同意之后仍然可以选：{sel.outcome}")
    h.case("B20", "聚合同意不是逐 {事实, 候选} 的签字", "needs_human", r, checks,
           {"per_item_records_replaced": per_item})


def case_b21_registry_guard(h: Harness) -> None:
    g = golden(h)
    checks: list[str] = []
    plan = g["verifier_plan"]
    matrix = B.PKG.default(B.ROOT).load("fact_capability")
    registry = REG.REGISTRY
    if registry is not B.VERIFIER_REGISTRY:
        checks.append("注册表对象与处理链持有的不是同一份：不许有第二份拷贝")
    results = REG.run_all(plan, matrix, registry)
    red = {code: probs for code, probs in results.items() if probs}
    if red:
        checks.append("注册表守卫在真实商品包上不是全绿：" + str(red))
    used = {rt["id"] for route in plan.get("routes", []) for rt in route["routers"]}
    missing = sorted(used - set(registry))
    if missing:
        checks.append("路由里出现未注册的责任者：" + "、".join(missing))
    if len(registry) < 3:
        checks.append(f"注册表只有 {len(registry)} 个验证器")
    r = B.fact_routing(g["candidates"]["F-01"], g["card"], plan, g["human_facts"])
    if r.payload.get("verifier_registry", {}).get("verifiers") != sorted(registry):
        checks.append("PC-09 载荷里的注册表清单与实现不一致")
    h.case("B21", "注册表守卫与真实商品包交叉核对", "accepted", r, checks,
           {"rules": len(REG.RULES), "verifiers": sorted(registry), "missing": missing})


CASES = [
    case_b0_golden,
    case_b1_applicability,
    case_b2_missing_signature,
    case_b3_signed_unknown,
    case_b4_signed_fail,
    case_b5_keep_cannot_cover_fail,
    case_b6_redo_not_selectable,
    case_b7_unclassified_reason,
    case_b8_rework_isolation,
    case_b9_double_selection,
    case_b10_overflow,
    case_b11_font_missing,
    case_b12_final_file_fails,
    case_b13_coverage,
    case_b14_tamper,
    case_b15_reexport,
    case_b16_rule_without_param,
    case_b17_no_invented_state,
    case_b18_unregistered_router,
    case_b19_review_items,
    case_b20_aggregate_consent,
    case_b21_registry_guard,
]

# ---------------------------------------------------------------- 变异测试
def weak_applicability_always_true(router, candidate):
    real = _ORIG["applicability_of"](router, candidate)
    forced = dict(real)
    forced["applicable"] = True
    forced["why"] = "变异：假装前提永远成立"
    return forced


def weak_fact_routing(candidate, card, verifier_plan, human_review, **kw):
    r = _ORIG["fact_routing"](candidate, card, verifier_plan, human_review, **kw)
    if r.outcome == "needs_human":
        return C.StepResult("PC-09", "accepted", payload=r.payload,
                            notes=["变异：未决被当成通过"])
    return r


def weak_select_ignore_facts(**kw):
    kw["fact_result"] = C.StepResult("PC-09", "accepted", payload={"facts": []})
    return _ORIG["select_candidate"](**kw)


def weak_select_ignore_visual(**kw):
    review = kw["review"]
    forced = {cid: dict(rec, verdict="keep")
              for cid, rec in (review.payload.get("reviews") or {}).items()}
    kw["review"] = C.StepResult("PC-10", "accepted",
                                payload={**review.payload, "reviews": forced},
                                notes=["变异：审美结论被强制成 keep"])
    return _ORIG["select_candidate"](**kw)


def weak_rework_no_isolation(**kw):
    kw["state"] = None
    return _ORIG["rework"](**kw)


def weak_technical_check(candidate, rules, *, scope="candidate"):
    r = _ORIG["technical_check"](candidate, rules, scope=scope)
    if scope == "final":
        return C.StepResult("PC-08", "accepted", payload=r.payload,
                            notes=["变异：最终文件跳过复检"])
    return r


def weak_compose_no_overflow(selection, candidate, **kw):
    r = _ORIG["compose"](selection, candidate, **kw)
    if r.outcome == "technical_fail" and kw.get("text_spec"):
        ts = dict(kw["text_spec"])
        ts["box"] = {"x": 0, "y": 0, "w": 10 ** 7, "h": 10 ** 7}
        return _ORIG["compose"](selection, candidate, **{**kw, "text_spec": ts})
    return r


def weak_package_dir(out_dir, base_pid):
    p = Path(out_dir) / base_pid             # 变异：总是复用同一个目录
    p.mkdir(parents=True, exist_ok=True)
    return p


def weak_fact_routing_unregistered_accepts(candidate, card, verifier_plan, human_review, **kw):
    """变异：未注册的责任者被当成「默认通过」。"""
    r = _ORIG["fact_routing"](candidate, card, verifier_plan, human_review, **kw)
    if r.outcome != "needs_human":
        return r
    payload = dict(r.payload)
    patched = 0
    facts = []
    for f in payload["facts"]:
        if f["verdict"] is None and any(t.get("result") == "unregistered_router"
                                        for t in f["trail"]):
            f = dict(f, verdict="pass", responsible="ghost-verifier")
            patched += 1
        facts.append(f)
    if not patched:
        return r
    payload["facts"] = facts
    return C.StepResult("PC-09", "accepted", payload=payload,
                        notes=["变异：未注册的责任者被当成通过"])


def weak_fact_routing_drop_review_items(candidate, card, verifier_plan, human_review, **kw):
    r = _ORIG["fact_routing"](candidate, card, verifier_plan, human_review, **kw)
    payload = dict(r.payload)
    payload.pop("review_items", None)
    return C.StepResult("PC-09", r.outcome, payload=payload, notes=list(r.notes))


def weak_signature_index_aggregate(human_review):
    """变异：把签字当成「有一条同意 = 所有 {事实, 候选} 都同意」。"""
    base = _ORIG["signature_index"](human_review)
    fallback = (human_review.get("records") or [None])[0]

    class _Permissive(dict):
        def get(self, key, default=None):
            got = super().get(key)
            return fallback if got is None else got

    return _Permissive(base)


MUTATIONS: list[tuple[str, str, str, object, list[str]]] = [
    ("M1", "把适用性前置整段停掉", "B.applicability_of",
     weak_applicability_always_true, ["B1"]),
    ("M2", "把「未决事实阻断选择」停掉（未决当通过）", "B.fact_routing",
     weak_fact_routing, ["B2", "B3"]),
    ("M3", "把「事实没过不可选」停掉", "B.select_candidate",
     weak_select_ignore_facts, ["B4", "B5"]),
    ("M4", "把「审美结论必须 keep」停掉", "B.select_candidate",
     weak_select_ignore_visual, ["B6"]),
    ("M5", "把返工隔离记录停掉", "B.rework", weak_rework_no_isolation, ["B8"]),
    ("M6", "把最终文件复检停掉（沿用中间候选结论）", "B.technical_check",
     weak_technical_check, ["B12"]),
    ("M7", "把排版溢出检测停掉", "B.compose", weak_compose_no_overflow, ["B10"]),
    ("M8", "把「重导创建新包」停掉（原地覆盖）", "B._next_package_dir",
     weak_package_dir, ["B15"]),
    ("M9", "把「未注册责任者结论作废」停掉（当成通过）", "B.fact_routing",
     weak_fact_routing_unregistered_accepts, ["B18"]),
    ("M10", "把逐事实 ReviewItem 停掉", "B.fact_routing",
     weak_fact_routing_drop_review_items, ["B19"]),
    ("M11", "把「签字必须逐 {事实, 候选}」停掉（聚合同意算数）", "B.signature_index",
     weak_signature_index_aggregate, ["B20"]),
    ("M12", "把注册表的适用性前置声明拿掉", "REG.REGISTRY",
     WEAK_REGISTRY_NO_PRECONDITION, ["B21"]),
]


CASE_CODES = {fn: fn.__name__.split("_")[1].upper() for fn in CASES}


def _owner(dotted: str, namespace: dict):
    parts = dotted.split(".")
    obj = namespace[parts[0]]
    for part in parts[1:-1]:
        obj = getattr(obj, part)
    return obj, parts[-1]


def mutation_test(verbose: bool = True) -> int:
    """把实现逐条削弱，要求对应的反例必须变红。"""
    bad = 0
    for code, name, dotted, weakened, targets in MUTATIONS:
        owner, attr_name = _owner(dotted, globals())
        original = getattr(owner, attr_name)
        setattr(owner, attr_name, weakened)
        try:
            h = Harness()
            try:
                for case in CASES:
                    if case.__name__.split("_")[1].upper() in targets:
                        try:
                            case(h)
                        except Exception as exc:
                            raw_case(h, CASE_CODES[case], "（用例异常）", "-", "exception",
                                     [f"{type(exc).__name__}: {exc}"])
            finally:
                h.cleanup()
            got = {r["case"]: r["ok"] for r in h.rows}
            missed = [t for t in targets if got.get(t, True)]
            ok = not missed
            if verbose:
                print(f"[{'OK  ' if ok else 'FAIL'}] {code} {name}　→　"
                      f"{'、'.join(targets)} {'全部变红' if ok else '仍有绿灯：' + '、'.join(missed)}")
            bad += 0 if ok else 1
        finally:
            setattr(owner, attr_name, original)
    if verbose:
        print(f"\n变异测试：{len(MUTATIONS) - bad}/{len(MUTATIONS)} 项被反例抓住")
    return 0 if bad == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D1.P3 后半链契约测试（离线，零付费调用）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--mutation-test", action="store_true",
                    help="把实现逐条削弱，验证反例真的有牙")
    ap.add_argument("--report", default=str(OUT))
    args = ap.parse_args(argv)

    if args.mutation_test:
        return mutation_test()

    h = Harness()
    try:
        for case in CASES:
            try:
                case(h)
            except Exception as exc:
                raw_case(h, CASE_CODES[case], "（用例异常）", "-", "exception",
                         [f"{type(exc).__name__}: {exc}"])
    finally:
        h.cleanup()

    bad = [r for r in h.rows if not r["ok"]]
    report = {
        "schema": "amz-listing-kit/back-contracts-verification@1",
        "plan_version": C.PLAN_VERSION,
        "cases": len(h.rows),
        "passed": len(h.rows) - len(bad),
        "failed": len(bad),
        "paid_calls": 0,
        "rows": h.rows,
        "does_not_prove": [
            "没有调用任何真实模型：模型路线在本次全部记为 not_run（那是 D1.R2/R3 的事）",
            "没有证明场景候选的 F1-F8 由自动路线判过：四张的事实结论全部由显式人工确认承担",
            "没有证明跨商品通用：那属于 D1.P4",
            "没有证明 Amazon 实际审核通过：本文件的规则来自 config/slots.yaml",
            "本次没有产生付费调用，也没有改动冻结候选与账本",
        ],
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")

    if args.json:
        print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                         ensure_ascii=False, indent=2))
    else:
        print("D1.P3 后半链契约测试（离线 · 零付费调用）")
        print("=" * 74)
        for row in h.rows:
            mark = "OK  " if row["ok"] else "FAIL"
            print(f"[{mark}] {row['case']:<4} {row['name']}  →  {row['actual']}"
                  f"（期望 {row['expect']}）")
            for note in row["notes"]:
                print(f"         · {note}")
            for problem in row["failed_checks"]:
                print(f"         ✗ {problem}")
        print()
        print(f"结论：{report['passed']}/{report['cases']} 条符合预期")
        print(f"报告：{path.relative_to(ROOT)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())