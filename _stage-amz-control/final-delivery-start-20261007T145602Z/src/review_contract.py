#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""Review Checklist v1 —— 人工事实清单，以及「不接受」这道门（fail-closed）。

它回答两个问题：

    ① 这张候选图，人要看哪几件事、每件事要看到什么才算有依据（清单）；
    ② 这些结论合起来，够不够把它转成 ACCEPTED（判据）。

三个分栏的**后果**不同，这是本模块唯一的重点：

    critical_fact      错了就是错 → fail / unknown / 没判 都阻断接受
    platform_hard_rule 平台硬线   → 同上
    aesthetic          偏好       → **永远不阻断接受**，只影响排序与返工建议

所以「审美高分不能抵消事实失败」不是某处写的一句提醒，而是 `blocks_accept` 这个
字段的取值 —— 审美栏的那几条根本不参与能不能接受的判断（`evaluate()` 里可核）。

不另写规则：平台栏每一条指向已有的权威（`validators.KNOWN_RULES` /
`intake` 的签字项 / `config/brand.json` 的键）。指向不存在的规则名会直接报错；
`KNOWN_RULES` 里新增一条而没有落项也没写排除理由，同样报错。

只读 + 不覆盖：
    `build_checklist()` 纯函数，不改传入对象；
    同一项结论写过一次就不能覆盖（要改就记新的一条事件）；
    每次记录都留下谁、什么时候、依据是什么。

用法：
    from review_contract import load_checklist, build_checklist, record_outcome, evaluate, require_accepted
    contract = load_checklist()                       # 默认 contracts/review-checklist-v1.yaml
    cl = build_checklist(contract, task_id="T1", slot_id="4",
                         candidate_ref="out/.../cand-1.png", facts_version="pfv1-...")
    cl = record_outcome(cl, "cf.structure", "pass", by="运营 A")
    cl = record_outcome(cl, "cf.appearance", "fail", by="运营 A", note="图上杯身印的是旧 logo")
    require_accepted(evaluate(cl))                    # 不接受就抛，不给「默认过」的余地
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "review-checklist/v1"
DEFAULT_PATH = ROOT / "contracts" / "review-checklist-v1.yaml"
BLOCKING_OUTCOMES = ("fail", "unknown")
_REF_FIELDS = ("rule_ref", "config_ref", "attest_ref")


class ChecklistError(Exception):
    """清单契约或清单本身不合法 —— 直接拒绝，不给"勉强能用"的余地。"""


class ReviewRefused(Exception):
    """不能转成 ACCEPTED。

    它**不是技术失败**：这是门正常工作的结果。调用方应当把 `.verdict["blockers"]`
    原样交给评审的人，而不是重试或用审美分把它盖过去。
    """

    def __init__(self, verdict: dict) -> None:
        super().__init__(f"不接受这张候选：{verdict['reason']}"
                         f"（阻断项 {verdict['blockers']}，未判 {verdict['pending']}）")
        self.verdict = verdict


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def checklist_version(contract: dict) -> str:
    """契约的版本：由**语义内容**算出（`updated_at` 不算，改日期不该改版本）。"""
    semantic = {k: v for k, v in contract.items() if k != "updated_at"}
    return "rcv1-" + hashlib.sha256(_canon(semantic).encode("utf-8")).hexdigest()[:12]


def state_hash(checklist: dict) -> str:
    """清单**当前状态**的哈希：只算每项的结论，不算问题的措辞。

    交付包/Selection 引它，就能回答"当时这张图是在哪一份结论状态下被接受的"。
    """
    state = [{k: i.get(k) for k in ("id", "outcome", "by", "at", "note")}
             for i in checklist.get("items") or []]
    return "rvh1-" + hashlib.sha256(_canon(state).encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------ 校验

def validate_checklist(contract) -> list[str]:
    """结构校验：够拦住"分栏去掉了 / 结论取值乱写 / 指向不存在的权威"这三类。"""
    problems: list[str] = []
    if not isinstance(contract, dict):
        return ["顶层不是映射"]
    for key in ("schema", "sections", "outcomes", "items"):
        if key not in contract:
            problems.append(f"缺顶层键 {key}")
    if contract.get("schema") != SCHEMA:
        problems.append(f"schema 不是 {SCHEMA}")

    sections = contract.get("sections")
    if not isinstance(sections, dict) or not sections:
        problems.append("sections 必须是至少一个分栏的映射")
        sections = {}
    for name, meta in sections.items():
        if not isinstance(meta, dict):
            problems.append(f"sections.{name} 不是映射")
            continue
        if not isinstance(meta.get("blocks_accept"), bool):
            problems.append(f"sections.{name} 缺 blocks_accept（true/false）—— "
                            f"「这一栏能不能阻断接受」必须写死，不能靠读的人猜")
        if not str(meta.get("label") or "").strip():
            problems.append(f"sections.{name} 缺 label")

    outcomes = contract.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        problems.append("outcomes 必须是非空列表")
        outcomes = []
    for need in ("pass", "fail", "unknown", "not_applicable"):
        if need not in outcomes:
            problems.append(f"outcomes 里缺 {need} —— 缺一种取值，就会有人用别的词代替")

    kinds = contract.get("evidence_kinds")
    if not isinstance(kinds, dict) or not kinds:
        problems.append("evidence_kinds 必须是至少一种证据的映射")
        kinds = {}

    items = contract.get("items")
    if not isinstance(items, list) or not items:
        problems.append("items 必须是非空列表")
        items = []
    seen: set[str] = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            problems.append(f"items[{i}] 不是映射")
            continue
        iid = str(it.get("id") or "")
        where = f"items[{i}]" + (f"({iid})" if iid else "")
        for key in ("id", "section", "question", "evidence"):
            if key not in it:
                problems.append(f"{where} 缺字段 {key}")
        if not iid:
            problems.append(f"{where} 的 id 是空的")
        elif iid in seen:
            problems.append(f"{where} 的 id 重复")
        else:
            seen.add(iid)
        if it.get("section") not in sections:
            problems.append(f"{where} 的 section={it.get('section')!r} 不在 sections 里")
        if not str(it.get("question") or "").strip():
            problems.append(f"{where} 缺 question —— 人得知道自己在判什么")
        ev = it.get("evidence")
        if not isinstance(ev, list) or not ev:
            problems.append(f"{where} 的 evidence 必须是非空列表（判之前先说要看到什么）")
        else:
            for e in ev:
                if e not in kinds:
                    problems.append(f"{where} 的 evidence 里有没登记的证据种类：{e!r}")
        refs = [f for f in _REF_FIELDS if it.get(f)]
        if len(refs) > 1:
            problems.append(f"{where} 同时写了 {refs} —— 一条项只能指向一处权威，"
                            f"否则'以谁为准'要靠运气")
        if it.get("na_allowed") is not None and not isinstance(it.get("na_allowed"), bool):
            problems.append(f"{where} 的 na_allowed 只能是 true/false")
        if bool(it.get("conditional")) and not bool(it.get("na_allowed")):
            problems.append(f"{where} 是条件项却不允许 not_applicable —— "
                            f"条件不成立时它只能一直挂着，等于永远判不完")

    excl = contract.get("rule_exclusions")
    if excl is not None:
        if not isinstance(excl, dict):
            problems.append("rule_exclusions 必须是映射")
        else:
            for name, why in excl.items():
                if not str(why or "").strip():
                    problems.append(f"rule_exclusions.{name} 没写理由 —— "
                                    f"有理由的排除不是漏项，没理由的排除就是漏项")
    return problems


def check_references(contract, *, known_rules, attest_items, brand_config) -> list[str]:
    """跨模块核对：清单指向的权威必须真的存在，且**已实现的规则不许有漏项**。"""
    problems: list[str] = []
    rules_used: set[str] = set()
    for it in contract.get("items") or []:
        if not isinstance(it, dict):
            continue
        iid = it.get("id")
        rr = it.get("rule_ref")
        if rr:
            rules_used.add(str(rr))
            if rr not in known_rules:
                problems.append(f"{iid} 指向的规则 {rr!r} 不在 src/validators.py 的 "
                                f"KNOWN_RULES 里 —— 这正是'声明了校验但静默跳过'那一类")
        ar = it.get("attest_ref")
        if ar and ar not in attest_items:
            problems.append(f"{iid} 指向的签字项 {ar!r} 不在 src/intake.py 的签字清单里")
        cr = it.get("config_ref")
        if cr and cr not in brand_config:
            problems.append(f"{iid} 指向的配置键 {cr!r} 不在 config/brand.json 里")
    excluded = set((contract.get("rule_exclusions") or {}).keys())
    missing = sorted(set(known_rules) - rules_used - excluded)
    if missing:
        problems.append(f"src/validators.py 里这些规则既没有清单项、也没写排除理由："
                        f"{missing} —— 新加校验忘了配人工清单，就会长成这样")
    unknown_excl = sorted(excluded - set(known_rules))
    if unknown_excl:
        problems.append(f"rule_exclusions 里这些名字不是已实现的规则：{unknown_excl}")
    return problems


def load_checklist(path: str | Path | None = None, *, verify_refs: bool = True) -> dict:
    import yaml
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        raise ChecklistError(f"找不到清单契约：{p}")
    contract = yaml.safe_load(p.read_text(encoding="utf-8"))
    problems = validate_checklist(contract)
    if verify_refs and not problems:
        import intake
        import validators
        problems += check_references(contract,
                                    known_rules=validators.KNOWN_RULES,
                                    attest_items=set(intake.ATTEST_ITEMS)
                                    | {intake.FONT_ATTEST_ITEM, intake.COMPETITOR_ATTEST_ITEM},
                                    brand_config=set(_brand_keys()))
    if problems:
        raise ChecklistError("清单契约不合法：\n  - " + "\n  - ".join(problems))
    return contract


def _brand_keys() -> list[str]:
    brand = json.loads((ROOT / "config" / "brand.json").read_text(encoding="utf-8"))
    return list(brand.keys())


# ------------------------------------------------------------------ 生成清单

def build_checklist(contract: dict, *, task_id: str, slot_id: str, candidate_ref: str,
                    facts_version: str, applicable: dict | None = None) -> dict:
    """为**一张候选图**生成清单。

    `applicable`（可选）限定这一张图真正要判的确定性规则与签字项：
        {"rules": {...}, "attest": {...}}
    传进来的名字必须真的存在 —— 打错一个字就等于悄悄少判一项，所以这里有校验。
    `None` 表示全判（默认更严）。
    """
    for name, val in (("task_id", task_id), ("slot_id", slot_id),
                      ("candidate_ref", candidate_ref), ("facts_version", facts_version)):
        if not str(val or "").strip():
            raise ChecklistError(f"build_checklist 缺 {name} —— 清单必须有对象，"
                                 f"否则它判的是哪张图就说不清了")
    if applicable is not None:
        allowed = {f for k in ("rules", "attest") for f in (applicable.get(k) or set())}
        unknown = sorted(allowed - _all_reference_names(contract))
        if unknown:
            raise ChecklistError(f"applicable 里有清单不认识的名字：{unknown} —— "
                                 f"打错一个字就等于少判一项")

    items = []
    for it in contract.get("items") or []:
        if applicable is not None:
            if it.get("rule_ref") and it["rule_ref"] not in (applicable.get("rules") or set()):
                continue
            if it.get("attest_ref") and it["attest_ref"] not in (applicable.get("attest") or set()):
                continue
            if it.get("conditional") and it.get("attest_ref") not in (applicable.get("attest") or set()):
                continue
        items.append({"id": it["id"], "section": it["section"], "question": it["question"],
                      "evidence": list(it["evidence"]), "plan_refs": list(it.get("plan_refs") or []),
                      "authority": {f: it[f] for f in _REF_FIELDS if it.get(f)} or None,
                      "na_allowed": bool(it.get("na_allowed")),
                      "conditional": bool(it.get("conditional")),
                      "outcome": None, "by": None, "at": None, "note": None})

    cv = checklist_version(contract)
    identity = {"checklist_version": cv, "task_id": task_id, "slot_id": slot_id,
                "candidate_ref": candidate_ref, "facts_version": facts_version}
    cl = {
        "schema": "review-checklist-instance/v1",
        "checklist_version": cv,
        "instance_id": "rvi1-" + hashlib.sha256(_canon(identity).encode("utf-8")).hexdigest()[:12],
        "task_id": task_id, "slot_id": slot_id,
        "candidate_ref": candidate_ref, "facts_version": facts_version,
        "sections": {n: {"label": (m or {}).get("label"),
                         "blocks_accept": bool((m or {}).get("blocks_accept"))}
                     for n, m in (contract.get("sections") or {}).items()},
        "outcomes": list(contract.get("outcomes") or []),
        "items": items,
        "revision": 0,
        "events": [],
    }
    cl["state_hash"] = state_hash(cl)
    return cl


def _all_reference_names(contract: dict) -> set[str]:
    out: set[str] = set()
    for it in contract.get("items") or []:
        for f in _REF_FIELDS:
            if it.get(f):
                out.add(str(it[f]))
    return out


def record_outcome(checklist: dict, item_id: str, outcome: str, *, by: str,
                   note: str | None = None, at=None) -> dict:
    """记一条结论。**不覆盖**：同一项写过就不能再写，要改就记新的一条事件。"""
    if not str(by or "").strip():
        raise ChecklistError("记结论必须写 by（谁判的）—— 没人负责的结论不能进交付包")
    if outcome not in (checklist.get("outcomes") or []):
        raise ChecklistError(f"结论 {outcome!r} 不在取值域 {checklist.get('outcomes')}")
    target = None
    for it in checklist.get("items") or []:
        if it["id"] == item_id:
            target = it
            break
    if target is None:
        raise ChecklistError(f"清单里没有这个项：{item_id}")
    if target.get("outcome") is not None:
        raise ChecklistError(f"{item_id} 已经写过结论（{target['outcome']}，{target.get('by')}）—— "
                             f"清单不覆盖：要改就记新的一条事件，别把旧结论擦掉")
    if outcome == "not_applicable" and not target.get("na_allowed"):
        raise ChecklistError(f"{item_id} 不允许标 not_applicable —— "
                             f"把判不了的项标成'不适用'，就是让最难的题自己消失")
    if outcome in BLOCKING_OUTCOMES and not str(note or "").strip():
        raise ChecklistError(f"{item_id} 判成 {outcome} 必须写依据（note）—— "
                             f"没有依据的 fail/unknown 等于拒绝理由不明")
    new = copy.deepcopy(checklist)
    for it in new["items"]:
        if it["id"] == item_id:
            it["outcome"] = outcome
            it["by"] = by
            it["at"] = _iso(at) or datetime.now().astimezone().isoformat(timespec="seconds")
            it["note"] = note
            break
    new["revision"] = int(checklist.get("revision") or 0) + 1
    new["events"] = list(checklist.get("events") or []) + [
        {"item_id": item_id, "outcome": outcome, "by": by, "at": _iso(at), "note": note}]
    new["state_hash"] = state_hash(new)
    return new


# ------------------------------------------------------------------ 判据

def evaluate(checklist: dict) -> dict:
    """够不够接受。**审美栏不参与**这个判断 —— 它只被记下来。"""
    sections = checklist.get("sections") or {}
    items = checklist.get("items") or []
    blocking = [i for i in items if (sections.get(i["section"]) or {}).get("blocks_accept")]
    soft = [i for i in items if not (sections.get(i["section"]) or {}).get("blocks_accept")]
    blockers = [i["id"] for i in blocking if i.get("outcome") in BLOCKING_OUTCOMES]
    pending = [i["id"] for i in blocking if i.get("outcome") is None]
    aesthetic_counts: dict[str, int] = {}
    for i in soft:
        key = i.get("outcome") or "unjudged"
        aesthetic_counts[key] = aesthetic_counts.get(key, 0) + 1
    if blockers:
        reason = "blocked_by_findings"
    elif pending:
        reason = "checklist_incomplete"
    else:
        reason = "ready_for_acceptance"
    return {
        "instance_id": checklist.get("instance_id"),
        "state_hash": checklist.get("state_hash"),
        "can_accept": not blockers and not pending,
        "reason": reason,
        "blockers": blockers,
        "pending": pending,
        "aesthetic": aesthetic_counts,
        "aesthetic_blocks_accept": False,
        "judged": len([i for i in items if i.get("outcome") is not None]),
        "total": len(items),
    }


def require_accepted(verdict: dict) -> dict:
    """接受入口用它：不许就抛，而不是"返回 False 让人自己记得检查"。"""
    if not verdict.get("can_accept"):
        raise ReviewRefused(verdict)
    return verdict
