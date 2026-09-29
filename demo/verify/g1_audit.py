# -*- coding: utf-8 -*-
"""D1.R4 —— 用责任链重新裁决 Gate G1（离线 · 零付费）。

它回答一个问题：计划 §5 Phase 1 的 Gate G1，**当前**的证据能不能证明它的每一条分项。
不是一篇结论性说明，而是一次可重算的审计：输入是冻结的首轮产物、商品包的验证路由与两份
人工记录，输出是逐条读数与一个 verdict（pass / controlled_retest / stop）。

为什么要写成脚本：Gate 的结论会被后面所有阶段当作既成事实引用。一份只会说「通过」的报告，
在有人改动签字、参考图或账本时不会有任何反应；而脚本会当场变红。

七条分项（与计划 §5 G1 的句子一一对应）：

  A 请求真实性     参考图真的进了请求体、非 mock、身份/参数/原图/用量可追溯
  B 预算          首轮 4/8 的读数成立，且没有动用复验预算
  C 事实分项      至少一张候选的 F1-F8 全部由已声明责任者解析为 pass，无 Unknown 无硬失败
  D 责任不混写    结论者的类型与注册表一致；未校准的模型不得给终局结论；
                  确定性责任者必须在自己声明的适用前提成立时才能给 pass
  E 签字粒度      每条人工结论都要有对应的 {fact_id, candidate_id} 记录，不许从聚合同意反推
  F 视觉 keep     至少一张候选的人工商业视觉结论是 keep，且理由取自封闭集合
  G 视觉是独立环节 PC-10 是独立合同：不生成总分、有审阅者与时间、逐候选给结论。
                  「独立第三方」不属于 G1，属 C11/D6.3；本脚本只如实登记这条边界。

用法：
    python demo/verify/g1_audit.py check --project .        # 审计；verdict 不是 pass 就退出码 1
    python demo/verify/g1_audit.py self-test --project .    # 五种改坏必须各自变红
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

VISUAL_VERDICTS = ("keep", "redo", "reject")
EVIDENCE_CLAUSES = ("A_请求真实性", "B_预算", "E_签字粒度", "G_视觉是独立环节")


def _loads(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_inputs(project) -> dict:
    """把本次审计要用的**唯一权威**读进来，不在这里另抄一份身份。"""
    project = Path(project)
    if str(project) not in sys.path:
        sys.path.insert(0, str(project))
    from demo.core import back_chain as B
    from demo.verify import verifier_registry as REG

    pkg = B.PKG.resolve(project)
    runs = B.PKG.runs_of(project)
    ledger_path = runs["ledger"]
    rows = [json.loads(ln) for ln in ledger_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    return {
        "project": project,
        "B": B,
        "REG": REG,
        "pkg": pkg,
        "runs": runs,
        "pkg_sources": {k: pkg.rel(k) for k in ("card", "verifier_plan", "human_facts",
                                                "human_visual", "refpack", "runs")},
        "manifest": B.load_json(runs["manifest"]),
        "ledger": rows,
        "candidates": B.candidates_of(project),
        "card": B.factcard.load_card(pkg.path("card")),
        "plan": B.load_json(pkg.path("verifier_plan")),
        "human_facts": B.load_json(pkg.path("human_facts")),
        "human_visual": B.load_json(pkg.path("human_visual")),
        "registry": REG.REGISTRY,
    }


# ------------------------------------------------------------------ A
def clause_request_truth(inp) -> list:
    B = inp["B"]
    man = inp["manifest"]
    problems: list = []
    rows = {r.get("action_id"): r for r in inp["ledger"]}
    seeds = set()
    for c in man.get("candidates", []):
        cid, aid = c["candidate_id"], c["action_id"]
        base = Path(c["request_json"]).parent
        intent = _loads(base / "intent.json")
        req = _loads(base / "request.json")
        resp = _loads(base / "response-task.json")
        ref = (intent.get("reference_sha256") or [None])[0]
        if intent.get("mode") != "image_to_image":
            problems.append(f"{cid} 的 mode 是 {intent.get('mode')!r}，不是 image_to_image")
        if intent.get("model") != "qwen-image-3.0":
            problems.append(f"{cid} 的模型是 {intent.get('model')!r}")
        if intent.get("prompt_extend") is not False:
            problems.append(f"{cid} 的 prompt_extend 不是 false")
        content = (((req.get("input") or {}).get("messages") or [{}])[0].get("content") or [])
        images = [x for x in content if isinstance(x, dict) and "image" in x]
        if not images:
            problems.append(f"{cid} 的请求体里没有 image 字段 —— 非 mock 这一条不成立")
        elif ref and ("sha256=" + str(ref)) not in str(images[0]["image"]):
            problems.append(f"{cid} 请求体里的参考图不是冻结的那一张")
        if (req.get("parameters") or {}).get("seed") != intent.get("seed"):
            problems.append(f"{cid} 的 seed 与请求参数不一致")
        if ((resp.get("output") or {}).get("task_status")) != "SUCCEEDED":
            problems.append(f"{cid} 的服务端终态不是 SUCCEEDED")
        if int(((resp.get("usage") or {}).get("input_image_count") or 0)) < 1:
            problems.append(f"{cid} 的服务端回执说 input_image_count=0")
        row = rows.get(aid)
        if row is None:
            problems.append(f"{cid}（action {aid}）不在账本里")
        else:
            if row.get("status") != "SUCCEEDED" or not row.get("chargeable"):
                problems.append(f"{cid} 的账本终态/计费标记不对")
            if row.get("reference_sha256") != [ref]:
                problems.append(f"{cid} 账本记的参考图哈希与 intent 不一致")
        if c.get("image_sha256") and Path(c["image_path"]).is_file():
            got = B.sha256_file(c["image_path"])
            if got != c["image_sha256"]:
                problems.append(f"{cid} 的候选文件哈希与 manifest 不符")
        seeds.add(c.get("seed"))
    if len(seeds) != len(man.get("candidates", [])):
        problems.append("四个候选的 seed 不是四个不同值")
    if man.get("prompt_extend") is not False or man.get("watermark") is not False:
        problems.append("manifest 的 prompt_extend / watermark 不是 false")
    return problems


# ------------------------------------------------------------------ B
def clause_budget(inp) -> list:
    man = inp["manifest"]
    problems: list = []
    charged = [r for r in inp["ledger"] if r.get("chargeable")]
    budget = man.get("budget") or {}
    total = int(budget.get("budget_total") or 0)
    if len(charged) != int(budget.get("charged_after") or -1):
        problems.append("账本计费行数与 manifest 的 charged_after 不一致")
    if total and len(charged) > total:
        problems.append(f"计费行 {len(charged)} 超过总预算 {total}")
    if man.get("retest") is not None:
        problems.append("manifest 里有 retest 记录：复验预算被动用过")
    if (man.get("checks") or {}).get("every_success_carried_reference") is not True:
        problems.append("manifest 没有断言「每次成功都带参考图」")
    return problems


# ------------------------------------------------------------------ C / D / E 共用
def route_all(inp) -> dict:
    B = inp["B"]
    return {cid: B.fact_routing(cand, inp["card"], inp["plan"], inp["human_facts"],
                                human_source=inp["pkg_sources"]["human_facts"])
            for cid, cand in sorted(inp["candidates"].items())}


def clause_fact_chain(inp, routing):
    problems: list = []
    clear: list = []
    reading = {}
    for cid, r in sorted(routing.items()):
        items = r.payload["review_items"]
        not_pass = [i["fact_id"] for i in items if i["verdict"] != "pass"]
        reading[cid] = {"outcome": r.outcome,
                        "not_pass": not_pass,
                        "owners": sorted({i["owner"] for i in items if i["owner"]})}
        if not not_pass:
            clear.append(cid)
    if not clear:
        problems.append("没有任何一张候选的 F1-F8 全部解析为 pass")
    return problems, clear, reading


def clause_no_mixing(inp, routing) -> list:
    reg = inp["registry"]
    B = inp["B"]
    problems: list = []
    for cid, cand in sorted(inp["candidates"].items()):
        r = routing.get(cid)
        if r is None:
            continue
        for f, it in zip(r.payload["facts"], r.payload["review_items"]):
            if it["verdict"] is None:
                continue
            owner, kind = it["owner"], it["owner_kind"]
            if owner not in reg:
                problems.append(f"{cid} {it['fact_id']} 的结论者 {owner!r} 不在注册表里")
                continue
            if kind != reg[owner]["kind"]:
                problems.append(f"{cid} {it['fact_id']} 的结论者类型与注册表不一致")
            if f["responsible"] != owner:
                problems.append(f"{cid} {it['fact_id']} 的事实记录与 ReviewItem 责任者不一致")
            if kind == "model" and not reg[owner].get("auto_adjudication"):
                problems.append(f"{cid} {it['fact_id']} 由未校准的模型给出终局结论")
            if kind == "deterministic":
                route = next((x for x in inp["plan"]["routes"] if x["fact"] == it["fact_id"]), None)
                router = next((rt for rt in (route or {}).get("routers", [])
                               if rt["id"] == owner), None)
                if router is None:
                    problems.append(f"{cid} {it['fact_id']} 找不到确定性责任者的数据声明")
                else:
                    app = B.applicability_of(router, cand)
                    if not app.get("applicable"):
                        problems.append(
                            f"{cid} {it['fact_id']} 用不适用的机器尺子给出了 {it['verdict']}")
    return problems


def clause_signature_granularity(inp, routing):
    problems: list = []
    idx = inp["B"].signature_index(inp["human_facts"])
    recs = inp["human_facts"].get("records") or []
    for rec in recs:
        if rec.get("fact_id") in (None, "*") or rec.get("candidate_id") in (None, "*"):
            problems.append("存在聚合/通配签字，人工结论会被误当成推断而来")
        for k in ("reviewer", "reviewer_kind", "reviewed_at", "source", "verdict"):
            if not rec.get(k):
                problems.append(f"{rec.get('fact_id')}/{rec.get('candidate_id')} 的签字缺 {k}")
    needed = set()
    for cid, r in routing.items():
        for it in r.payload["review_items"]:
            if it["verdict"] is not None and it["owner_kind"] == "human":
                needed.add((it["fact_id"], cid))
    missing = sorted(p for p in needed if p not in idx)
    extra = sorted(p for p in idx if p not in needed)
    if missing:
        problems.append("这些人工结论没有对应的逐条签字：" +
                        "、".join(f"{a}/{b}" for a, b in missing))
    if extra:
        problems.append("这些签字没有对应的已解析事实：" +
                        "、".join(f"{a}/{b}" for a, b in extra))
    reading = {"records": len(recs), "human_resolved": len(needed), "indexed": len(idx)}
    return problems, reading


# ------------------------------------------------------------------ F / G
def clause_visual_keep(inp):
    doc = inp["human_visual"]
    vocab = set(doc.get("reason_vocabulary") or [])
    problems: list = []
    keeps: list = []
    for cid, rec in (doc.get("reviews") or {}).items():
        v = rec.get("verdict")
        if v not in VISUAL_VERDICTS:
            problems.append(f"{cid} 的视觉结论 {v!r} 不在 keep/redo/reject 里")
        reasons = rec.get("reasons") or []
        if not reasons:
            problems.append(f"{cid} 的视觉结论没有具体理由")
        for x in reasons:
            if vocab and x not in vocab:
                problems.append(f"{cid} 的理由 {x!r} 不在封闭理由集里")
        if v == "keep":
            keeps.append(cid)
    if not keeps:
        problems.append("没有任何一张候选的人工商业视觉结论是 keep")
    return problems, sorted(keeps)


def clause_visual_is_separate_stage(inp) -> list:
    doc = inp["human_visual"]
    problems: list = []
    if doc.get("no_composite_score") is not True:
        problems.append("视觉审核没有声明「不生成总分」")
    for k in ("reviewer", "reviewer_kind", "reviewed_at", "source"):
        if not doc.get(k):
            problems.append(f"视觉审核缺 {k}")
    if not (doc.get("reviews") or {}):
        problems.append("视觉审核没有任何逐候选结论")
    return problems


# ------------------------------------------------------------------ 汇总
def audit(inp, routing=None) -> dict:
    routing = route_all(inp) if routing is None else routing
    c_fact, clear, fact_reading = clause_fact_chain(inp, routing)
    e_sign, sign_reading = clause_signature_granularity(inp, routing)
    f_visual, keeps = clause_visual_keep(inp)
    clauses = {
        "A_请求真实性": clause_request_truth(inp),
        "B_预算": clause_budget(inp),
        "C_事实分项": c_fact,
        "D_责任不混写": clause_no_mixing(inp, routing),
        "E_签字粒度": e_sign,
        "F_视觉 keep": f_visual,
        "G_视觉是独立环节": clause_visual_is_separate_stage(inp),
    }

    # 停止条款：计划 §5 G1 的失败路径是「0/4 硬失败且已排除尺子问题」。
    hard_fail_all = bool(inp["candidates"])
    ruler_all_ok = True
    for cid, cand in sorted(inp["candidates"].items()):
        route = next((x for x in inp["plan"]["routes"] if x["fact"] == "F1"), None)
        router = next((rt for rt in (route or {}).get("routers", [])
                       if rt.get("kind") == "deterministic"), None)
        if router is None:
            ruler_all_ok = False
            break
        if not inp["B"].applicability_of(router, cand).get("applicable"):
            ruler_all_ok = False
            break
    fails = {cid: [i["fact_id"] for i in routing[cid].payload["review_items"]
                   if i["verdict"] == "fail"] for cid in routing}
    hard_fail_all = all(bool(v) for v in fails.values()) and bool(fails)

    if not any(clauses.values()):
        verdict = "pass"
    elif hard_fail_all and ruler_all_ok:
        verdict = "stop"
    elif any(clauses[k] for k in EVIDENCE_CLAUSES):
        verdict = "stop"
    else:
        verdict = "controlled_retest"

    boundary = [
        "事实分项的责任者分布：" + "、".join(
            f"{cid}→{fact_reading[cid]['owners']}" for cid in sorted(fact_reading)),
        "事实链在四张真实场景候选上**没有任何机器结论**：确定性路线前提不成立、"
        "模型路线本次未运行（注册表 auto_adjudication=false）",
        "人工审阅者身份："
        + str(inp["human_visual"].get("reviewer_kind"))
        + " —— 「独立第三方」不属于 G1，属 C11 / D6.3，目前**未满足**",
        "本审计不证明跨商品通用、不证明 Amazon 审核通过、不证明真实运营提效",
    ]
    return {"clauses": clauses, "verdict": verdict, "clear": clear, "keeps": keeps,
            "fact_reading": fact_reading, "fails": fails, "signature": sign_reading,
            "boundary": boundary,
            "budget": dict(inp["manifest"].get("budget") or {})}


def _print(rep: dict) -> None:
    print("=" * 74)
    print("D1.R4 Gate G1 审计（离线 · 零付费）")
    print("=" * 74)
    for code, problems in rep["clauses"].items():
        mark = "OK  " if not problems else "FAIL"
        print(f"  [{mark}] {code}" + ("" if not problems else "：" + "；".join(problems[:3])))
    print()
    print("  预算：" + str(rep["budget"]))
    print("  逐候选事实读数：")
    for cid, row in sorted(rep["fact_reading"].items()):
        print(f"    {cid}: PC-09={row['outcome']} 未通过事实={row['not_pass'] or '无'} "
              f"责任者={row['owners']}")
    print("  人工签字：" + str(rep["signature"]) + "  视觉 keep：" + str(rep["keeps"]))
    print()
    print("  边界（不是失败条件，是必须写在结论里的范围）：")
    for line in rep["boundary"]:
        print("    · " + line)
    print()
    print("  结论（G1）：" + rep["verdict"])
    print()


def check(project) -> int:
    inp = load_inputs(project)
    rep = audit(inp)
    _print(rep)
    return 0 if rep["verdict"] == "pass" else 1


# ------------------------------------------------------------------ 自检
def selftest(project) -> int:
    """每个分项都要有**恰好**能把它打红的反例 —— 用例设计错也是一种红。

    注意 C 分项的真实边界：G1 只要求「至少一张候选」F1-F8 全清。所以「删掉一条签字」
    不是反例（另外三张仍然全清）；能打红它的是「四张都失去这条签字」。
    """
    inp = load_inputs(project)
    base = audit(inp)
    print("G1 审计自检（每种改坏必须让对应分项变红）")
    if base["verdict"] != "pass":
        print("  [FAIL] 基线不是 pass：" + str({k: v for k, v in base["clauses"].items() if v}))
        return 1
    print("  [OK  ] 基线：七条分项全绿，verdict = pass")

    work = Path(tempfile.mkdtemp(prefix="g1-audit-selftest-"))
    data_keys = ("manifest", "ledger", "candidates", "card", "plan",
                 "human_facts", "human_visual", "registry")

    def mut(fn):
        """只深拷贝数据；模块对象与商品包按引用带上（改动只允许发生在数据上）。"""
        x = {k: v for k, v in inp.items() if k not in data_keys}
        for k in data_keys:
            x[k] = copy.deepcopy(inp[k])
        fn(x)
        return x

    def drop_f5_everywhere():
        return mut(lambda x: x["human_facts"].update(
            {"records": [r for r in x["human_facts"]["records"] if r["fact_id"] != "F5"]}))

    def aggregate_signature():
        return mut(lambda x: x["human_facts"].update(
            {"records": [{"fact_id": "*", "candidate_id": "*", "verdict": "pass",
                          "reviewer": "project-operator",
                          "reviewer_kind": "not_independent_third_party",
                          "reviewed_at": "2026-09-26T00:40:00+08:00",
                          "source": "聚合：整组通过"}]}))

    def request_without_image():
        """不碰冻结产物：把三份回执复制到临时目录、抽掉 image 字段后指过去。"""
        x = mut(lambda y: None)
        c = x["manifest"]["candidates"][0]
        src = Path(c["request_json"]).parent
        dst = work / "attempt-no-image"
        dst.mkdir(exist_ok=True)
        for name in ("intent.json", "request.json", "response-task.json"):
            (dst / name).write_text(
                (src / name).read_text(encoding="utf-8"), encoding="utf-8")
        doc = json.loads((dst / "request.json").read_text(encoding="utf-8"))
        doc["input"]["messages"][0]["content"] = [
            y for y in doc["input"]["messages"][0]["content"] if "image" not in y]
        (dst / "request.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
        c["request_json"] = str(dst / "request.json")
        return x

    C = inp["B"].C
    routing = route_all(inp)
    doctored = dict(routing)
    cand0 = sorted(inp["candidates"])[0]
    payload = dict(routing[cand0].payload)
    items = [dict(i) for i in payload["review_items"]]
    items[0]["owner"] = "cylinder-v1"
    items[0]["owner_kind"] = "deterministic"
    payload["review_items"] = items
    doctored[cand0] = C.StepResult(routing[cand0].contract_id, routing[cand0].outcome,
                                   payload=payload, notes=list(routing[cand0].notes))

    def visual_loses_shape():
        def cut(x):
            doc = x["human_visual"]
            doc.pop("no_composite_score", None)
            doc.pop("reviewer", None)
        return mut(cut)

    cases = [
        ("all_candidates_lose_one_fact", "C_事实分项", lambda: audit(drop_f5_everywhere())),
        ("blank_request_image", "A_请求真实性", lambda: audit(request_without_image())),
        ("extra_ledger_row", "B_预算",
         lambda: audit(mut(lambda x: x["ledger"].append(
             {"action_id": "x", "chargeable": True, "status": "SUCCEEDED"})))),
        ("machine_ruler_gives_pass", "D_责任不混写", lambda: audit(inp, routing=doctored)),
        ("aggregate_signature", "E_签字粒度", lambda: audit(aggregate_signature())),
        ("all_visual_redo", "F_视觉 keep",
         lambda: audit(mut(lambda x: [rec.update({"verdict": "redo"})
                                      for rec in x["human_visual"]["reviews"].values()]))),
        ("visual_stage_loses_shape", "G_视觉是独立环节", lambda: audit(visual_loses_shape())),
    ]
    caught = 0
    total = 0
    problems = []
    try:
        for name, expect, fn in cases:
            total += 1
            rep = fn()
            hit = bool(rep["clauses"][expect])
            caught += 1 if hit else 0
            mark = "OK  " if hit else "FAIL"
            print(f"  [{mark}] {name}\u3000\u2192\u3000{expect}"
                  + ("（已变红）" if hit else "（没有变红！）"))
            if not hit:
                problems.append(name + " 没有让 " + expect + " 变红")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()
    if problems:
        print("自检未通过：" + "；".join(problems))
        return 1
    print(f"自检：{caught}/{total} 种改坏都被对应分项抓住")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                     # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="D1.R4 Gate G1 审计")
    ap.add_argument("mode", nargs="?", default="check", choices=["check", "self-test"])
    ap.add_argument("--project", default=str(ROOT))
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    return selftest(project) if args.mode == "self-test" else check(project)


if __name__ == "__main__":
    raise SystemExit(main())
