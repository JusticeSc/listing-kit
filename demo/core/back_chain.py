# -*- coding: utf-8 -*-
"""PC-08 - PC-13 后半链实现（离线、零付费调用）。

前半链回答「发出去的请求对不对」；后半链回答「回来的东西能不能用、谁给的结论判、
判错了怎么改、最后交出去的文件是不是同一份」。没有实现的合同只是散文，
所以这里给 PC-08-PC-13 一份真能跑、也能被跑红的实现。

五条纪律：

1. 状态不许自造：返回值一律经过 contracts.StepResult，结果必须落在该合同自己声明的闭集合里。
   PC-08 没有 business_reject、PC-12 没有 needs_human —— 这不是风格问题，是合同问题。
2. 上游不过，下游不写：上游非 accepted 时用 contracts.blocked_by。
3. 先问适用性，再给结论：确定性量测的前提不成立时必须返回 not_applicable 并交回路由。
   把不适用的尺子读成失败与读成通过是同一类错误 —— D1.4 的场景候选事故就是这一步缺席。
4. 人工结论必须逐条：事实与审美都要 {事实, 候选} 或 {候选} 粒度的显式记录，
   不许从「四张都 keep」这类聚合结论反推。
5. 离线：本模块不联网、不付费；真实付费路径仍只有 demo/provider/dashscope_i2i.py。

边界：demo/contract/ 是环节身份权威（谁负责什么、结果取值是什么），本模块是实现。
两者冲突时以合同为准，demo/contract/contract_tools.py --check 会报红。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from . import contracts as C
from . import front_chain as FC
from . import packages as PKG
from demo.verify import probes as PROBES   # noqa: E402  验证层探针
from demo.verify import verifier_registry as REG   # noqa: E402  验证器能力注册表

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "demo" / "fixture"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import factcard               # noqa: E402
import measure_cylinder as MC  # noqa: E402

PLATFORM_SUB = FC.SLOTS_REL
# 逐商品数据与逐商品产物位置全部住商品包，一律**调用时**解析（§4.6 硬规矩 1、2）：
# 这里不留任何商品路径常量 —— 导入时焊死默认包，换商品就等于改 .py。

# 计划 9.3 / PC-10 的封闭理由集：审美不给总分，只给可指认的理由。
REASON_VOCAB = ("构图", "主体层级", "光线融合", "材质真实感", "背景干扰", "商业完成度")
VISUAL_VERDICTS = ("keep", "redo", "reject")

# PC-11 的原因分类：先归类，再只改对应变量。
REASON_CODES = {
    "not_decodable": "technical_form",
    "wrong_format": "technical_form",
    "size_too_small": "technical_form",
    "aspect_mismatch": "technical_form",
    "file_too_large": "technical_form",
    "background_clutter": "scene_composition",
    "composition_weak": "scene_composition",
    "lighting_harsh": "scene_composition",
    "product_identity": "identity",
    "product_structure": "identity",
    "exact_text_needed": "exact_text",
}
REWORK_ROUTES = {
    "technical_form": {
        "changes": ["确定性重编码/画布规格"],
        "touches_prompt": False,
        "why": "形态问题由确定性处理解决，改提示词不会让文件边长变合规",
    },
    "scene_composition": {
        "changes": ["这张图的场景设置（场景、构图、光线）", "提示词里未锁住的那部分"],
        "touches_prompt": True,
        "why": "画面策略属于可变量；事实锁段不许动",
    },
    "identity": {
        "changes": ["参考图集合", "模型/编辑路线"],
        "touches_prompt": False,
        "why": "身份与结构失真不靠堆否定词解决；优先换证据",
    },
    "exact_text": {
        "changes": ["排版层（精确文字单独合成，不进生图）"],
        "touches_prompt": False,
        "why": "精确文字不交给生图模型拼",
    },
    "unclassified": {
        "changes": [],
        "touches_prompt": False,
        "why": "原因归不了类时交人工，不做无界自动重试",
    },
}


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def content_id(obj) -> str:
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def candidates_of(project=ROOT, sku=None) -> dict:
    """候选集合 —— 身份取自**商品包声明的候选目录**里的 manifest，不在这里另抄一遍。"""
    runs = PKG.runs_of(project, sku)
    man = load_json(runs["manifest"])
    out = {}
    for c in man["candidates"]:
        rel = Path(c["image_path"])
        try:
            rel = rel.relative_to(Path(project))
        except ValueError:
            pass
        out[c["candidate_id"]] = {
            "candidate_id": c["candidate_id"],
            "action_id": c["action_id"],
            "file": str(Path(project) / rel),
            "sha256": c["image_sha256"],
            "seed": c.get("seed"),
            "prompt_sha256": c.get("prompt_sha256"),
            "task_id": c.get("task_id"),
            "input_image_count": c.get("input_image_count"),
        }
    return out


def export_rules(project=ROOT) -> dict:
    """平台/导出规则只从 config/slots.yaml 读，不在代码里另写一套平台语义。

    唯一的例外是容器格式：slots.yaml 自己写着「格式（JPEG）与色彩空间由代码里
    .convert("RGB") + "JPEG" 硬保证 —— 它们不是配置，是事实」。
    所以这里读的是那份事实，而不是发明一个新字段。
    """
    import yaml
    doc = yaml.safe_load((Path(project) / PLATFORM_SUB).read_text(encoding="utf-8"))
    ex = doc.get("export") or {}
    return {
        "source": PLATFORM_SUB,
        "site": doc.get("site"),
        "aspect_ratio": ex.get("aspect_ratio"),
        "min_long_side_px": ex.get("min_long_side_px"),
        "long_side_px": ex.get("long_side_px"),
        "max_file_mb": ex.get("max_file_mb"),
        "jpeg_quality": ex.get("jpeg_quality"),
        "export_format": "JPEG",
    }


def decode_probe(path) -> dict:
    from PIL import Image
    p = Path(path)
    if not p.is_file():
        return {"error": "文件不存在", "path": str(p)}
    raw = p.read_bytes()
    info = {"path": str(p), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    try:
        with Image.open(p) as im:
            info["width"], info["height"] = im.size
            info["mode"] = im.mode
            info["format"] = im.format
            im.load()
    except Exception as exc:                      # 解码失败是文件问题，不是业务前提
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info

# ------------------------------------------------------------------ PC-08
def technical_check(candidate, rules, *, scope="candidate") -> C.StepResult:
    """PC-08 技术检查：只判文件与平台形态，不判商品。

    scope="candidate" 判中间候选（容器格式由 provider 决定，不做要求）；
    scope="final" 判最终交付文件（必须过导出格式规则）。
    """
    cid = candidate.get("candidate_id")
    info = decode_probe(candidate.get("file"))
    checks: list[dict] = []

    def add(rule, value, verdict, source, why=""):
        checks.append({"rule": rule, "value": value, "verdict": verdict,
                       "source": source, "why": why})

    if "error" in info:
        add("decodable", info["error"], "fail", "文件可解码", "解码失败")
    else:
        add("decodable", {"width": info["width"], "height": info["height"],
                          "mode": info["mode"], "format": info["format"]},
            "pass", "文件可解码")
        long_side = max(info["width"], info["height"])
        floor = rules.get("min_long_side_px")
        if floor is None:
            add("min_long_side_px", long_side, "unknown",
                "slots.yaml export.min_long_side_px", "规则缺参数，不推断")
        else:
            add("min_long_side_px", long_side,
                "pass" if long_side >= int(floor) else "fail",
                "slots.yaml export.min_long_side_px", f"下限 {floor}px")
        spec = rules.get("aspect_ratio")
        if not spec:
            add("aspect_ratio", None, "unknown", "slots.yaml export.aspect_ratio",
                "规则缺参数，不推断")
        else:
            try:
                a, b = (float(x) for x in str(spec).split(":"))
                want = a / b
            except Exception:
                add("aspect_ratio", spec, "unknown", "slots.yaml export.aspect_ratio",
                    f"读不懂的规格 {spec!r}")
            else:
                got = info["width"] / info["height"]
                ok = abs(got - want) <= 0.02
                add("aspect_ratio", round(got, 4), "pass" if ok else "fail",
                    "slots.yaml export.aspect_ratio", f"要求 {spec}（容差 0.02）")
        limit_mb = rules.get("max_file_mb")
        if limit_mb is None:
            add("max_file_mb", round(info["bytes"] / 1e6, 3), "unknown",
                "slots.yaml export.max_file_mb", "规则缺参数，不推断")
        else:
            mb = info["bytes"] / 1e6
            add("max_file_mb", round(mb, 3), "pass" if mb <= float(limit_mb) else "fail",
                "slots.yaml export.max_file_mb", f"上限 {limit_mb}MB")
        if scope == "final":
            want_fmt = str(rules.get("export_format") or "").upper()
            got_fmt = str(info.get("format") or "").upper()
            add("export_format", got_fmt, "pass" if got_fmt == want_fmt else "fail",
                "slots.yaml 注释：格式由代码保证", f"要求 {want_fmt}")
        else:
            add("export_format", str(info.get("format") or ""), "not_applicable",
                "只在最终文件判定", "中间候选的容器格式由 provider 决定")

    fails = [c for c in checks if c["verdict"] == "fail"]
    unknowns = [c for c in checks if c["verdict"] == "unknown"]
    payload = {"candidate_id": cid, "scope": scope, "image": info, "checks": checks}
    if fails:
        return C.StepResult("PC-08", "technical_fail", payload=payload,
                            notes=["平台形态不满足：" + "；".join(
                                f"{c['rule']}={c['value']}" for c in fails)])
    if unknowns:
        return C.StepResult("PC-08", "unknown", payload=payload,
                            notes=["有规则缺参数，无法判定：" + "；".join(
                                c["rule"] for c in unknowns)])
    return C.StepResult("PC-08", "accepted", payload=payload,
                        notes=[f"{len(checks)} 条技术规则全部通过（{scope}）"])


# ------------------------------------------------------------------ PC-09
# 适用性探针与量测缓存住验证层（demo/verify/probes.py）：它们回答"这把尺子在这张图上成不成立"，
# 属于验证器能力声明，不属于处理链。这里按名字重新导出，调用方与变异探针(monkeypatch B.*)不用改。
backdrop_probe = PROBES.backdrop_probe
APPLICABILITY_PROBES = PROBES.APPLICABILITY_PROBES
applicability_of = PROBES.applicability_of
measure_candidate = PROBES.measure_candidate

# 「谁能判哪类事实、默认结论是什么、需要什么声明」全部读注册表（D1.R3）：
# 路由里不再有 if/else 替每个验证器记着脾气。数据与注册表冲突时报未注册，不静默跳过。
VERIFIER_REGISTRY = REG.REGISTRY
FACT_VERDICT_STATE = {"pass": "resolved", "fail": "resolved",
                      "risk": "needs_human", "needs_human": "needs_human",
                      "unknown": "unresolved"}


def signature_index(human_review) -> dict:
    """人工签字索引：键是 (fact_id, candidate_id)。

    这个粒度写在注册表的 human.signature_granularity 里，不是这里现编的。聚合同意
    （"四张都 keep"、"整组通过"）拿不到这个键，因此不会被读成对某条事实的签字。
    """
    return {(r["fact_id"], r["candidate_id"]): r
            for r in human_review.get("records", [])}


def fact_routing(candidate, card, verifier_plan, human_review, *, run_models=False,
                 registry=None, human_source=None, project=ROOT, sku=None) -> C.StepResult:
    """PC-09 商品事实验证：先判适用性 -> 再选责任者 -> 最后合并（三步不并）。

    中间那一步是重点：验证器只能在它声明的前提成立时给结论；前提不成立、
    模型未校准或没有人工签字时，事实保持未决并阻止选择 —— 不假绿，也不假红。

    责任者「能判什么、默认结论是什么」来自注册表：没登记 = 未注册（结论作废，
    不是通过）；登记为不能自动裁决的模型路线只能报 risk/unknown，由人接手。
    """
    reg = VERIFIER_REGISTRY if registry is None else registry
    if human_source is None:            # 调用时解析：默认包只是默认值，不是唯一入口
        human_source = PKG.sub_of(project, "human_facts", sku)
    cid = candidate["candidate_id"]
    signed = signature_index(human_review)
    facts_out: list[dict] = []
    review_items: list[dict] = []
    det_cache: dict = {}
    route_counts: Counter = Counter()

    for fact in card["facts"]:
        fid = fact["id"]
        route = next((r for r in verifier_plan.get("routes", []) if r["fact"] == fid), None)
        trail: list[dict] = []
        verdict = None
        responsible = None
        owner_kind = None
        evidence = None

        if route is None:
            trail.append({"router": None, "kind": None, "result": "no_route",
                          "why": "这条事实没有登记任何责任者"})
        else:
            for router in route["routers"]:
                kind = router["kind"]
                declared = reg.get(router.get("id"))
                if declared is None:
                    trail.append({"router": router.get("id"), "kind": kind,
                                  "result": "unregistered_router",
                                  "why": "该责任者没有登记在验证器注册表里：它的结论一律无效，"
                                         "既不静默跳过也不当成通过"})
                    continue
                if declared.get("kind") != kind:
                    trail.append({"router": router.get("id"), "kind": kind,
                                  "result": "declaration_mismatch",
                                  "why": "数据里的 kind 与注册表不一致（注册表登记为 "
                                         + str(declared.get("kind")) + "），先改声明再跑"})
                    continue
                if kind == "deterministic":
                    app = applicability_of(router, candidate)
                    if not app["applicable"]:
                        trail.append({"router": router["id"], "kind": kind,
                                      "result": "not_applicable", "why": app["why"],
                                      "measured": app.get("measured")})
                        continue
                    if "state" not in det_cache:
                        try:
                            det_cache["state"] = measure_candidate(candidate["file"], card)
                        except Exception as exc:
                            det_cache["state"] = {"error": f"{type(exc).__name__}: {exc}"}
                    state = det_cache["state"]
                    if "error" in state:
                        trail.append({"router": router["id"], "kind": kind,
                                      "result": "verifier_error", "why": state["error"]})
                        continue
                    row = next((f for f in state["report"]["facts"] if f["id"] == fid), None)
                    v = (row or {}).get("verdict")
                    if v in ("pass", "hard_fail"):
                        verdict = "pass" if v == "pass" else "fail"
                        responsible = router["id"]
                        owner_kind = kind
                        evidence = {"machine_checks": row["machine_checks"],
                                    "metric_profile": state["measured"]["metric_profile"],
                                    "candidate_sha256": candidate.get("sha256")}
                        trail.append({"router": router["id"], "kind": kind, "result": verdict,
                                      "why": "适用前提成立且机器判据给出终局结论"})
                        break
                    trail.append({"router": router["id"], "kind": kind,
                                  "result": v or "no_verdict",
                                  "why": "规则给不出终局结论（人工档/缺量测值/纯人工事实），"
                                         "交下一位责任者"})
                    continue
                if kind == "model":
                    default_verdict = declared.get("default_verdict") or "risk"
                    if not run_models:
                        trail.append({"router": router["id"], "kind": kind, "result": "not_run",
                                      "why": router.get("why_not_run") or "本任务离线，未运行模型路线"})
                        continue
                    if declared.get("auto_adjudication"):
                        verdict = default_verdict
                        responsible = router["id"]
                        owner_kind = kind
                        evidence = {"model": declared.get("model"),
                                    "prompt_profile": router.get("prompt_profile"),
                                    "auto_adjudication": True,
                                    "request_sha256": None,
                                    "status": "adjudication_route_not_implemented_in_D1_R3"}
                        trail.append({"router": router["id"], "kind": kind, "result": verdict,
                                      "why": "注册表登记为已校准、允许自动裁决"})
                        break
                    trail.append({"router": router["id"], "kind": kind, "result": default_verdict,
                                  "why": "注册表登记为未校准，默认只报 " + default_verdict
                                         + "，不直接裁决"})
                    continue
                if kind == "human":
                    if not declared.get("requires_explicit_signature", True):
                        trail.append({"router": router["id"], "kind": kind,
                                      "result": "declaration_mismatch",
                                      "why": "注册表没要求显式签字，人工结论无法追责，先改声明"})
                        continue
                    rec = signed.get((fid, cid))
                    if rec is None:
                        trail.append({"router": router["id"], "kind": kind,
                                      "result": "no_signature",
                                      "why": "没有针对这条事实与这张候选的显式人工确认"})
                        continue
                    verdict = rec["verdict"]
                    responsible = router["id"]
                    owner_kind = kind
                    evidence = rec
                    trail.append({"router": router["id"], "kind": kind, "result": rec["verdict"],
                                  "why": "人工显式确认（" + str(rec.get("source", "未写来源")) + "）"})
                    break
                trail.append({"router": router.get("id"), "kind": kind, "result": "unknown_kind",
                              "why": "责任者类型未登记"})

        route_counts[responsible or "unresolved"] += 1
        facts_out.append({"fact_id": fid, "claim": fact["claim"],
                          "modality": fact.get("modality"), "verdict": verdict,
                          "responsible": responsible, "evidence": evidence, "trail": trail})
        # 逐事实 ReviewItem：责任者 + 证据指针 + 结论。粒度与人工签字粒度一致（{事实, 候选}）。
        shape = (reg.get(responsible) or {}) if responsible else {}
        review_items.append({
            "fact_id": fid,
            "candidate_id": cid,
            "claim": fact["claim"],
            "owner": responsible,
            "owner_kind": owner_kind,
            "verdict": verdict,
            "state": FACT_VERDICT_STATE.get(verdict, "unresolved"),
            "evidence_pointer": ("payload.facts[" + str(len(facts_out) - 1) + "].evidence"
                                 if evidence is not None else None),
            "evidence_required": list(shape.get("evidence_shape") or []),
        })

    fails = [f for f in facts_out if f["verdict"] == "fail"]
    risks = [f for f in facts_out if f["verdict"] == "risk"]
    unresolved = [f for f in facts_out if f["verdict"] in (None, "unknown", "needs_human")]
    automated_open = [f["fact_id"] for f in facts_out
                      if f["responsible"] == "human"
                      and not (f.get("evidence") or {}).get("machine_checks")]
    payload = {
        "candidate_id": cid,
        "candidate_sha256": candidate.get("sha256"),
        "facts": facts_out,
        "review_items": review_items,
        "route_summary": dict(route_counts),
        "human_source": human_source,
        "verifier_plan": verifier_plan.get("schema"),
        "verifier_registry": {"declared_in": "demo/verify/verifier_registry.py",
                              "verifiers": sorted(reg)},
        "automated_routes_unverified_for": automated_open,
    }
    if fails:
        return C.StepResult("PC-09", "business_reject", payload=payload,
                            notes=["事实层硬失败：" + "、".join(f["fact_id"] for f in fails)
                                   + "；该候选不可选，必须返工或换路线"])
    if unresolved:
        return C.StepResult("PC-09", "needs_human", payload=payload,
                            notes=["需要人显式确认这些具体事实："
                                   + "、".join(f["fact_id"] for f in unresolved)])
    if risks:
        return C.StepResult("PC-09", "needs_human", payload=payload,
                            notes=["模型只报了风险（未经对照校准），需要人确认："
                                   + "、".join(f["fact_id"] for f in risks)])
    return C.StepResult("PC-09", "accepted", payload=payload,
                        notes=[f"{len(facts_out)} 条事实全部由已声明责任者解析为 pass；"
                               f"责任分布 {dict(route_counts)}"])


# ------------------------------------------------------------------ PC-10
def visual_review(shot_id, candidate_ids, human_visual, *, source=None,
                  project=ROOT, sku=None) -> C.StepResult:
    """PC-10 审美审核：人给 keep/redo/reject + 封闭理由集，不生成总分。"""
    if source is None:                  # 调用时解析：默认包只是默认值，不是唯一入口
        source = PKG.sub_of(project, "human_visual", sku)
    vocab = set(human_visual.get("reason_vocabulary") or REASON_VOCAB)
    reviews = human_visual.get("reviews") or {}
    problems: list[str] = []
    missing: list[str] = []
    out = {}
    for cid in candidate_ids:
        rec = reviews.get(cid)
        if rec is None:
            missing.append(cid)
            continue
        v = rec.get("verdict")
        if v not in VISUAL_VERDICTS:
            problems.append(f"{cid}: 判定 {v!r} 不在 {VISUAL_VERDICTS}")
        bad = [r for r in (rec.get("reasons") or []) if r not in vocab]
        if bad:
            problems.append(f"{cid}: 理由 {bad} 不在封闭集合里")
        if not (rec.get("reasons") or []):
            problems.append(f"{cid}: 没有给出具体理由（审美结论必须能指认）")
        out[cid] = {"verdict": v, "reasons": rec.get("reasons") or [],
                    "notes": rec.get("notes"), "reviewer": human_visual.get("reviewer"),
                    "reviewed_at": rec.get("reviewed_at") or human_visual.get("reviewed_at"),
                    "source": human_visual.get("source")}
    payload = {"shot_id": shot_id, "reviews": out, "reason_vocabulary": sorted(vocab),
               "no_composite_score": True, "source": source}
    if problems:
        return C.StepResult("PC-10", "business_reject", payload=payload,
                            notes=["审美记录不合法：" + "；".join(problems[:3])])
    if missing:
        return C.StepResult("PC-10", "needs_human", payload=payload,
                            notes=["需要人对这些候选给出审美结论：" + "、".join(missing)])
    return C.StepResult("PC-10", "accepted", payload=payload,
                        notes=[f"{len(out)} 个候选都有人工判定与具体理由；不生成客观总分"])


# ------------------------------------------------------------------ PC-11
def classify_reason(reason_code: str) -> str:
    return REASON_CODES.get(reason_code, "unclassified")


def rework(*, shot_id, reason_code, plan, state=None, prompt_version=None,
           new_reference_views=None, budget_left=None) -> C.StepResult:
    """PC-11 返工路由：先归类，再只改对应变量；旧候选保留，未受影响的 Shot 不动。"""
    category = classify_reason(reason_code)
    route = REWORK_ROUTES[category]
    shots = {s["shot_id"]: s for s in plan.get("shots", [])}
    if shot_id not in shots:
        return C.StepResult("PC-11", "business_reject", payload={"shot_id": shot_id},
                            notes=[f"计划里没有这张图：{shot_id}"])
    if category == "unclassified":
        return C.StepResult("PC-11", "needs_human",
                            payload={"shot_id": shot_id, "reason_code": reason_code,
                                     "category": category},
                            notes=[f"原因 {reason_code!r} 归不了类；需要人来判断改什么，"
                                   "不做无界自动重试"])
    if budget_left is not None and budget_left <= 0 and route["touches_prompt"]:
        return C.StepResult("PC-11", "business_reject",
                            payload={"shot_id": shot_id, "category": category},
                            notes=["返工预算已用完；扩大预算需要新的授权"])

    change = {"shot_id": shot_id, "reason_code": reason_code, "category": category,
              "changes": list(route["changes"]), "touches_prompt": route["touches_prompt"],
              "why": route["why"]}
    if category == "scene_composition" and prompt_version is not None:
        child = FC.edit_prompt(prompt_version,
                               append=f"Adjust {reason_code} only; keep every locked "
                                      f"product fact unchanged.")
        if not child.accepted:
            return C.blocked_by("PC-11", child)
        change["new_prompt_version"] = {
            "parent": child.payload.get("parent_version"),
            "version_id": child.payload.get("version_id"),
            "prompt_sha256": child.payload.get("prompt_sha256"),
            "locks_facts": child.payload.get("locks_facts"),
            "diff": child.payload.get("diff"),
        }
    if category == "identity":
        if not new_reference_views:
            return C.StepResult("PC-11", "needs_human",
                                payload={"shot_id": shot_id, "category": category},
                                notes=["身份或结构失真需要换参考图或路线，"
                                       "这一步需要人给新的参考图集合（系统不自己挑）"])
        change["new_reference_views"] = list(new_reference_views)
    if category == "exact_text":
        change["route_to"] = "PC-12 确定性排版"

    untouched = []
    for sid, info in sorted((state or {}).get("shots", {}).items()):
        if sid == shot_id:
            continue
        untouched.append({"shot_id": sid,
                          "candidate_sha256": list(info.get("candidate_sha256") or []),
                          "submit_count": info.get("submit_count", 0)})
    payload = {"change": change, "untouched_shots": untouched, "old_candidates_kept": True,
               "target_old_candidates": list(
                   (((state or {}).get("shots", {}) or {}).get(shot_id, {}) or {})
                   .get("candidate_sha256") or [])}
    return C.StepResult("PC-11", "accepted", payload=payload,
                        notes=[f"原因 {reason_code} -> {category}；只改 "
                               f"{'、'.join(route['changes'])}；旧候选保留"])

# ------------------------------------------------------------------ PC-12
def select_candidate(*, shot_id, candidate, fact_result, review, existing=None,
                     selection_id=None) -> C.StepResult:
    """PC-12 选择：只有事实过关且被人工判为 keep 的候选才能被选。"""
    cid = candidate["candidate_id"]
    if existing:
        return C.StepResult("PC-12", "business_reject",
                            payload={"shot_id": shot_id, "existing": existing},
                            notes=["该图已经有 Selection；冲突要求刷新后重选，不后写覆盖前写"])
    if not fact_result.accepted:
        return C.StepResult("PC-12", "business_reject",
                            payload={"shot_id": shot_id, "candidate_id": cid,
                                     "fact_outcome": fact_result.outcome},
                            notes=[f"事实层没有通过（{fact_result.outcome}）：候选不可选"])
    rev = (review.payload.get("reviews") or {}).get(cid)
    if rev is None:
        return C.StepResult("PC-12", "business_reject",
                            payload={"shot_id": shot_id, "candidate_id": cid},
                            notes=["这个候选没有人工审美记录，不能自动选中"])
    if rev["verdict"] != "keep":
        return C.StepResult("PC-12", "business_reject",
                            payload={"shot_id": shot_id, "candidate_id": cid,
                                     "visual_verdict": rev["verdict"]},
                            notes=[f"人工判定是 {rev['verdict']}，不能作为最终选择"])
    selection = {
        "schema": "demo-selection/1",
        "selection_id": selection_id or content_id(
            {"shot": shot_id, "candidate": cid, "sha": candidate["sha256"]})[:16],
        "shot_id": shot_id,
        "candidate_id": cid,
        "candidate_sha256": candidate["sha256"],
        "fact_responsible": sorted({f["responsible"] for f in fact_result.payload["facts"]
                                    if f["responsible"]}),
        "visual_review": rev,
        "selected_by": "user",
        "note": "keep 不等于已选择；选择是独立事件，不改写 Candidate",
    }
    return C.StepResult("PC-12", "accepted", payload={"selection": selection},
                        notes=[f"选择 {cid} 用于 {shot_id}；事实与审美都记为已核对"])


def compose(selection, candidate, *, out_dir, text_spec=None, font_path=None,
            size_override=None) -> C.StepResult:
    """PC-12 精确合成：精确文案由确定性排版完成；无文案时记录恒等合成。"""
    from PIL import Image, ImageDraw, ImageFont
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Path(candidate["file"])
    stem = f"{selection['shot_id']}_{selection['candidate_id']}"
    base = {"shot_id": selection["shot_id"], "candidate_id": selection["candidate_id"],
            "selection_id": selection["selection_id"], "source_sha256": sha256_file(src)}

    if text_spec is None:
        dst = out_dir / (stem + "_identity.png")
        shutil.copyfile(src, dst)
        payload = dict(base, kind="identity", output=str(dst),
                       output_sha256=sha256_file(dst),
                       note="无文案：恒等合成，像素与容器格式都不变",
                       pixels_unchanged=sha256_file(dst) == sha256_file(src))
        return C.StepResult("PC-12", "accepted", payload=payload,
                            notes=["没有文案要叠：记录恒等合成，输出与候选逐字节相同"])

    text = text_spec.get("text") or ""
    box = text_spec.get("box") or {"x": 0, "y": 0, "w": 0, "h": 0}
    px = int(text_spec.get("size") or 28)
    try:
        font = (ImageFont.truetype(str(font_path), px) if font_path
                else ImageFont.load_default(size=px))
    except OSError as exc:
        return C.StepResult("PC-12", "technical_fail",
                            payload=dict(base, font=str(font_path)),
                            notes=[f"字体缺失：{exc}；不自动换字体，交人处理"])
    with Image.open(src) as im:
        canvas = im.convert("RGB").copy()
    geometry = {"w": canvas.width, "h": canvas.height}
    if size_override:
        canvas = canvas.resize((int(size_override[0]), int(size_override[1])))
        geometry = {"w": canvas.width, "h": canvas.height}
    draw = ImageDraw.Draw(canvas)
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    tw, th = r - l, b - t
    if tw > int(box["w"]) or th > int(box["h"]):
        return C.StepResult("PC-12", "technical_fail",
                            payload=dict(base, text=text, box=box, text_px=[tw, th],
                                         font=str(font_path or "default"),
                                         geometry=geometry),
                            notes=[f"排版溢出：文字 {tw}x{th}px 放不进 "
                                   f"{box['w']}x{box['h']}px 的文本框；不缩小字体、不自动换候选"])
    draw.text((int(box["x"]) - l, int(box["y"]) - t), text, fill=(20, 20, 20), font=font)
    dst = out_dir / (stem + "_text.png")
    canvas.save(dst, "PNG")
    payload = dict(base, kind="text_overlay", output=str(dst), output_sha256=sha256_file(dst),
                   text=text, box=box, text_px=[tw, th], font=str(font_path or "default"),
                   geometry=geometry, pixels_unchanged=False,
                   note="精确文案由确定性排版叠加，不交给生图模型拼字")
    return C.StepResult("PC-12", "accepted", payload=payload,
                        notes=[f"叠字成功：{tw}x{th}px 落在 {box['w']}x{box['h']}px 文本框内"])

# ------------------------------------------------------------------ PC-13
def _next_package_dir(out_dir, base_pid):
    """重导必须开新目录：重导不覆盖旧包。"""
    pkg = Path(out_dir) / base_pid
    suffix = 1
    while pkg.exists():
        suffix += 1
        pkg = Path(out_dir) / f"{base_pid}-r{suffix}"
    return pkg


def finalize(*, compositions, plan, rules, out_dir, package_id=None,
             disclaimer=None) -> C.StepResult:
    """PC-13 最终复检与导出：对最终文件重跑检查；覆盖不全不许发布。"""
    from PIL import Image
    out_dir = Path(out_dir)
    plan_shots = [s["shot_id"] for s in plan.get("shots", [])]
    counts = Counter(c["shot_id"] for c in compositions)
    missing = [s for s in plan_shots if counts.get(s, 0) == 0]
    dup = [s for s, n in counts.items() if n > 1]
    stranger = [s for s in counts if s not in plan_shots]
    if missing or dup or stranger:
        return C.StepResult("PC-13", "business_reject",
                            payload={"missing": missing, "duplicate": dup,
                                     "not_in_plan": stranger},
                            notes=["计划覆盖不成立：" + "；".join(
                                [x for x in (f"缺 {missing}" if missing else None,
                                             f"重复 {dup}" if dup else None,
                                             f"计划外 {stranger}" if stranger else None)
                                 if x])])
    base_pid = package_id or content_id(
        [{"shot": c["shot_id"], "sha": c["output_sha256"]} for c in compositions])[:12]
    pkg = _next_package_dir(out_dir, base_pid)   # 重导创建新版本，不覆盖旧包
    pkg.mkdir(parents=True, exist_ok=True)

    files = []
    for comp in sorted(compositions, key=lambda c: c["shot_id"]):
        export_path = pkg / f"{comp['shot_id']}_{comp['candidate_id']}.jpg"
        with Image.open(comp["output"]) as im:
            im.convert("RGB").save(export_path, "JPEG",
                                   quality=int(rules.get("jpeg_quality") or 92))
        chk = technical_check({"candidate_id": comp["candidate_id"], "file": str(export_path)},
                              rules, scope="final")
        entry = {"shot_id": comp["shot_id"], "candidate_id": comp["candidate_id"],
                 "file": export_path.name, "sha256": sha256_file(export_path),
                 "bytes": export_path.stat().st_size,
                 "composition_sha256": comp["output_sha256"],
                 "composition_kind": comp.get("kind"),
                 "final_checks": chk.payload.get("checks"),
                 "final_outcome": chk.outcome}
        files.append(entry)
        if not chk.accepted:
            return C.StepResult("PC-13", "technical_fail",
                                payload={"package": str(pkg), "failed": entry},
                                notes=[f"最终文件 {export_path.name} 未通过最终复检"
                                       f"（{chk.outcome}）：该 OutputVersion 不发布"])
    manifest = {
        "schema": "demo-output-manifest/1",
        "package_id": pkg.name,
        "created_by": "PC-13 finalize",
        "plan_version": plan.get("plan_version"),
        "platform": {"site": rules.get("site"), "source": rules.get("source"),
                     "export_format": rules.get("export_format"),
                     "jpeg_quality": rules.get("jpeg_quality")},
        "files": files,
        "coverage": {"planned_shots": plan_shots, "covered": sorted(counts)},
        "disclaimer": disclaimer or "虚构演示商品，不对应任何真实品牌或在售产品；不用于真实上架。",
        "does_not_prove": ["不证明 Amazon 实际审核通过", "不证明真实运营提效",
                           "最终复检只覆盖本清单声明的规则"],
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
    readme = pkg / "README.md"
    readme.write_text("\n".join(
        ["# 交付包 " + pkg.name, "",
         "由 demo/core/back_chain.py 的 PC-13 生成；每张图的最终文件都重新过一次",
         "技术与平台检查（不是沿用中间候选的结论）。", "",
         "| 图 | 候选 | 文件 | 合成方式 | 最终复检 |", "|---|---|---|---|---|"]
        + [f"| {f['shot_id']} | {f['candidate_id']} | {f['file']} | "
           f"{f['composition_kind']} | {f['final_outcome']} |" for f in files]
        + ["", "免责声明：" + manifest["disclaimer"], ""]),
        encoding="utf-8", newline="\n")
    payload = {
        "output_version": {"schema": "demo-output-version/1", "package_id": pkg.name,
                           "dir": str(pkg), "files": files,
                           "human_readme": "README.md", "machine_manifest": "manifest.json",
                           "manifest_sha256": sha256_file(pkg / "manifest.json")},
        "coverage": manifest["coverage"],
        "disclaimer": manifest["disclaimer"],
    }
    return C.StepResult("PC-13", "accepted", payload=payload,
                        notes=[f"导出 {len(files)} 个最终文件；每个都重新过检；"
                               f"包 {pkg.name} 为不可变交付单元"])


def verify_package(package_dir) -> tuple[int, dict]:
    """换目录核验：只读，重算哈希并重跑最终检查。"""
    pkg = Path(package_dir)
    man_path = pkg / "manifest.json"
    if not man_path.is_file():
        return 1, {"error": "缺少 manifest.json"}
    man = load_json(man_path)
    problems = []
    rules = export_rules()
    for f in man.get("files", []):
        p = pkg / f["file"]
        if not p.is_file():
            problems.append(f"{f['file']} 不存在")
            continue
        if sha256_file(p) != f["sha256"]:
            problems.append(f"{f['file']} 哈希与清单不一致（被改写）")
        chk = technical_check({"candidate_id": f["candidate_id"], "file": str(p)},
                              rules, scope="final")
        if not chk.accepted:
            problems.append(f"{f['file']} 最终复检 {chk.outcome}")
    return (0 if not problems else 1), {"package": str(pkg), "problems": problems,
                                       "files": len(man.get("files", []))}


def golden_candidates(project=ROOT, sku=None) -> dict:
    """便捷入口：候选取值 + 事实卡 + 人工记录 + 路由计划 + 平台规则。

    所有商品侧路径都由**调用时解析的商品包**给出；返回的 sources 就是证据里要写的
    identity，调用方不必自己拼路径，也就不会拼到另一个商品上去。
    """
    project = Path(project)
    pkg = PKG.resolve(project, sku)
    keys = ("card", "thresholds", "human_facts", "human_visual", "verifier_plan",
            "fact_capability", "refpack", "runs")
    return {
        "sku": pkg.sku,
        "candidates": candidates_of(project, sku=sku),
        "card": factcard.load_card(pkg.path("card")),
        "human_facts": load_json(pkg.path("human_facts")),
        "human_visual": load_json(pkg.path("human_visual")),
        "verifier_plan": load_json(pkg.path("verifier_plan")),
        "rules": export_rules(project),
        "sources": {k: pkg.rel(k) for k in keys},
        "runs": PKG.runs_of(project, sku),
    }
