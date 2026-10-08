#!/usr/bin/env python
"""V2.2.4 证据：四类商品理解的通用性探针（Gate G2 证据入口）。

判据（计划 §9.3，全部机检；任一条不成立则 Gate G2 不通过）：
  C1 输入驱动：四个 fixture 通过 parse_request，build_messages 的用户消息两两不同。
  C2 合法性：真实 provider 返回的每个槽位都通过消费侧 check_proposal_slot。
  C3 结构差异：四类 category_dynamic 槽位 id 集合两两不全等；至少两类有独有动态槽位。
  C4 可追溯：每个动态槽位 source=model_inference、status=proposed、confidence∈[0,1]、
     至少一条 evidence；提案 summary 非空。
  C5 无常量泄漏：fixture 商品名/品牌/特征词不出现在 src/、config/、app/product_v2/**/*.js；
     系统提示不出现任何品类枚举。

离线（默认，0 次调用）：只跑 C1 与 C5；C2–C4 记录为 SKIP（需要 --live）。
真实（--live）：走注册表的 dashscope-semantic，每类最多 1 次、总计最多 4 次，不重试、
  不抽卡；任何一类失败只按分类记录，该类判未验证并使 G2 不通过。不降标准、不重跑。

运行：
  uv run --locked python tools/verify_v2_2_4_category_generality.py
  uv run --locked python tools/verify_v2_2_4_category_generality.py --live
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
from console import enable_utf8  # noqa: E402
enable_utf8()

from src.providers import v2_semantic as contract  # noqa: E402
from src.providers.v2_dashscope_semantic import (  # noqa: E402
    DEFAULT_API_KEY_ENV,
    DEFAULT_MODEL_ID,
    build_messages,
    build_system_prompt,
)
from src.providers.v2_registry import create_semantic_provider  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
LIVE_BUDGET_CALLS = 4
LIVE_PROVIDER_ID = "dashscope-semantic"

# 常量泄漏扫描范围（计划 §9.3）：src/ 与 config/ 全文件，app/product_v2 只算 JS
#（index.html 的示例文案不算泄漏）。fixture 词只允许出现在本验证脚本里。
SCAN_ROOTS = ("src", "config", "app/product_v2")
JS_ONLY_ROOT = "app/product_v2"

# 系统提示不得出现品类枚举：通用词「品类」不算枚举，具体品类名词才算。
CATEGORY_ENUM_WORDS = (
    "服装", "鞋类", "箱包", "食品", "饮料", "生鲜", "家具", "家电", "厨具",
    "美妆", "个护", "母婴", "玩具", "数码", "珠宝", "宠物", "汽车用品",
)


def fixture_definitions() -> tuple[dict[str, Any], ...]:
    """四个 fixture：只给 SemanticRequest 字段，不给品类标签。"""

    def asset(seed: str, role: str, media_type: str = "image/png") -> dict[str, str]:
        return {"sha256": seed * 64, "media_type": media_type, "role": role,
                "original_name": f"{role}-{seed}.png"}

    return (
        {
            "key": "brand_rigid",
            "label": "品牌刚性商品",
            "expect": "品牌 / 材质 / 性能参数类动态槽位",
            "tokens": ("NORDVAC", "NV-700", "真空保温壶", "12 小时保温≥65°C"),
            "payload": {
                "product_name": "NORDVAC NV-700 真空保温壶",
                "description": "NORDVAC NV-700 采用 18/8 不锈钢双层真空结构，标称 95°C 热水 "
                               "12 小时后仍不低于 65°C；壶盖与壶身一体压铸，配防滑硅胶底座。",
                "selling_points": ["12 小时保温≥65°C", "18/8 不锈钢内胆",
                                   "一体压铸壶盖", "防滑硅胶底座"],
                "focus": "强调保温性能数字与品牌做工",
                "references": [asset("1", "primary"), asset("2", "detail")],
                "locale": "zh-CN",
                "platform": "amazon_us",
                "max_slots": 12,
            },
        },
        {
            "key": "apparel",
            "label": "服装",
            "expect": "面料 / 版型 / 尺码类动态槽位",
            "tokens": ("针织连衣裙", "粘纤混纺垂感", "直筒显瘦版型"),
            "payload": {
                "product_name": "轻薄针织连衣裙",
                "description": "圆领针织连衣裙，95% 粘纤 + 5% 氨纶，垂感面料，直筒版型；"
                               "春秋可单穿或叠穿，适合通勤与约会场景。",
                "selling_points": ["粘纤混纺垂感面料", "直筒显瘦版型",
                                   "通勤约会两用", "春秋单穿或叠穿"],
                "focus": "面料手感与版型呈现",
                "references": [asset("3", "primary"), asset("4", "detail")],
                "locale": "zh-CN",
                "platform": "amazon_us",
                "max_slots": 12,
            },
        },
        {
            "key": "packaged_food",
            "label": "包装食品",
            "expect": "配料 / 净含量 / 保质期类动态槽位",
            "tokens": ("每日坚果", "巴旦木", "净含量 750g", "保质期 9 个月"),
            "payload": {
                "product_name": "每日坚果混合装",
                "description": "每日坚果混合装，含巴旦木、腰果、蔓越莓干与蓝莓干；"
                               "独立小袋 25g×30 袋，净含量 750g，保质期 9 个月。",
                "selling_points": ["巴旦木+腰果+两种果干", "独立小袋 25g",
                                   "净含量 750g / 30 袋", "保质期 9 个月"],
                "focus": "配料表与净含量清晰",
                "references": [asset("5", "primary"), asset("6", "packaging")],
                "locale": "zh-CN",
                "platform": "amazon_us",
                "max_slots": 12,
            },
        },
        {
            "key": "furniture",
            "label": "家具",
            "expect": "尺寸 / 承重 / 安装类动态槽位",
            "tokens": ("升降书桌", "橡木饰面", "承重 80kg", "72–120cm"),
            "payload": {
                "product_name": "电动升降书桌",
                "description": "电动升降书桌，桌板为橡木饰面多层板（140×70cm），"
                               "双电机升降范围 72–120cm，承重 80kg，含安装说明书与工具。",
                "selling_points": ["140×70cm 橡木饰面桌板", "双电机 72–120cm 升降",
                                   "承重 80kg", "含安装工具与说明"],
                "focus": "尺寸、承重与安装信息",
                "references": [asset("7", "primary"), asset("8", "scene")],
                "locale": "zh-CN",
                "platform": "amazon_us",
                "max_slots": 12,
            },
        },
    )


def message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def user_message(request: contract.SemanticRequest) -> str:
    messages = build_messages(request)
    return "\n".join(message_text(item) for item in messages[1:])


def projection(request: contract.SemanticRequest) -> dict[str, Any]:
    return {
        "product_name": request.product_name,
        "description_chars": len(request.description),
        "selling_points": len(request.selling_points),
        "focus": request.focus,
        "references": len(request.references),
        "max_slots": request.max_slots,
        "locale": request.locale,
        "platform": request.platform,
    }


def scan_constant_leaks(tokens: tuple[str, ...]) -> list[dict[str, Any]]:
    """fixture 词出现在实现里 = 把示例当规则写死；返回逐条命中。"""

    folded = [(token, token.casefold()) for token in tokens]
    hits: list[dict[str, Any]] = []
    for relative in SCAN_ROOTS:
        root = ROOT / relative
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if relative == JS_ONLY_ROOT and path.suffix != ".js":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            lowered = text.casefold()
            for token, needle in folded:
                if needle in lowered:
                    hits.append({"path": path.relative_to(ROOT).as_posix(), "token": token})
    return hits


def category_enumeration_hits() -> list[str]:
    prompt = build_system_prompt()
    return [word for word in CATEGORY_ENUM_WORDS if word in prompt]


def dynamic_slots(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    return [slot for slot in proposal.get("slots", ())
            if slot.get("authority") == "category_dynamic"]


def core_slots(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    return [slot for slot in proposal.get("slots", ())
            if slot.get("authority") == "core_fixed"]


def slot_brief(slot: dict[str, Any]) -> dict[str, Any]:
    value = slot.get("value")
    return {
        "slot_id": slot.get("slot_id"),
        "label": slot.get("label"),
        "value_type": slot.get("value_type"),
        "value": str(value)[:120],
        "confidence": slot.get("confidence"),
        "evidence": len(slot.get("evidence") or ()),
        "depends_on": list(slot.get("depends_on") or ()),
    }


def analyze_live(definitions: tuple[dict[str, Any], ...],
                 requests: dict[str, contract.SemanticRequest]) -> tuple[dict[str, Any], int, dict[str, Any]]:
    """按预算逐类调用一次；返回 (逐类结果, 实际调用次数, provider 信息)。"""

    classes: dict[str, Any] = {item["key"]: {"status": "not_evaluated"} for item in definitions}
    calls = 0
    info: dict[str, Any] = {"provider_id": LIVE_PROVIDER_ID}
    if not os.environ.get(DEFAULT_API_KEY_ENV):
        info["configured"] = False
        return classes, calls, info
    try:
        provider = create_semantic_provider(provider_id=LIVE_PROVIDER_ID)
    except Exception as error:  # noqa: BLE001 - 构造失败也要留证
        info["configured"] = False
        info["error"] = f"{type(error).__name__}: {error}"
        return classes, calls, info
    capabilities = provider.capabilities()
    info.update({"configured": bool(capabilities.get("configured")),
                 "model_id": capabilities.get("model_id"),
                 "structured_output": capabilities.get("structured_output"),
                 "transport": capabilities.get("transport")})
    if capabilities.get("model_id") != DEFAULT_MODEL_ID:
        info["model_mismatch"] = capabilities.get("model_id")
    if not capabilities.get("configured"):
        return classes, calls, info
    for item in definitions:
        key = item["key"]
        calls += 1
        try:
            proposal = provider.analyze(requests[key])
        except contract.SemanticFailure as failure:
            classes[key] = {"status": "failed", "failure": failure.to_dict()}
            continue
        except Exception as error:  # noqa: BLE001 - 未分类异常同样判未验证
            classes[key] = {"status": "failed",
                            "failure": {"unclassified": f"{type(error).__name__}: {error}"}}
            continue
        payload = proposal.to_dict()
        classes[key] = {
            "status": "proposed",
            "proposal": payload,
            "dynamic_slots": [slot_brief(slot) for slot in dynamic_slots(payload)],
            "core_slots": [slot_brief(slot) for slot in core_slots(payload)],
        }
    return classes, calls, info


def check_proposal_problems(classes: dict[str, Any]) -> dict[str, Any]:
    problems: dict[str, Any] = {}
    for key, item in classes.items():
        if item.get("status") != "proposed":
            continue
        issues: list[dict[str, Any]] = []
        for index, slot in enumerate(item["proposal"].get("slots", ())):
            for problem in contract.check_proposal_slot(slot):
                issues.append({"slot_index": index, "slot_id": slot.get("slot_id"),
                               "path": problem["path"], "message": problem["message"]})
        problems[key] = issues
    return problems


def dynamic_id_sets(classes: dict[str, Any]) -> dict[str, list[str]]:
    return {key: sorted({slot["slot_id"] for slot in item.get("dynamic_slots", ())})
            for key, item in classes.items()}


def evaluate_structure(classes: dict[str, Any]) -> dict[str, Any]:
    sets = dynamic_id_sets(classes)
    proposed = {key: sorted(ids) for key, ids in sets.items()
                if classes[key].get("status") == "proposed"}
    complete = len(proposed) == len(classes) and bool(classes)
    pairwise: list[dict[str, Any]] = []
    keys = sorted(proposed)
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            pairwise.append({"left": left, "right": right,
                             "equal": proposed[left] == proposed[right]})
    unique: dict[str, list[str]] = {}
    for key in keys:
        others = set()
        for other in keys:
            if other != key:
                others.update(proposed[other])
        unique[key] = [slot_id for slot_id in proposed[key] if slot_id not in others]
    classes_with_unique = sorted(key for key, ids in unique.items() if ids)
    return {
        "complete": complete,
        "sets": sets,
        "pairwise": pairwise,
        "unique": unique,
        "classes_with_unique": classes_with_unique,
        "no_equal_pair": bool(pairwise) and all(not item["equal"] for item in pairwise),
        "unique_classes_ok": len(classes_with_unique) >= 2,
    }


def evaluate_traceability(classes: dict[str, Any]) -> dict[str, Any]:
    per_class: dict[str, Any] = {}
    for key, item in classes.items():
        if item.get("status") != "proposed":
            per_class[key] = {"ok": False, "reason": item.get("status")}
            continue
        proposal = item["proposal"]
        slots = dynamic_slots(proposal)
        bad: list[dict[str, Any]] = []
        for slot in slots:
            confidence = slot.get("confidence")
            reasons = []
            if slot.get("source") != "model_inference":
                reasons.append("source")
            if slot.get("status") != "proposed":
                reasons.append("status")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) \
                    or not (0.0 <= float(confidence) <= 1.0):
                reasons.append("confidence")
            if not slot.get("evidence"):
                reasons.append("evidence")
            if reasons:
                bad.append({"slot_id": slot.get("slot_id"), "reasons": reasons})
        summary_ok = bool(str(proposal.get("summary") or "").strip())
        per_class[key] = {"ok": bool(slots) and not bad and summary_ok,
                          "dynamic_count": len(slots), "bad_slots": bad,
                          "summary_ok": summary_ok}
    return per_class


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.2.4 四类商品理解通用性探针")
    parser.add_argument("--label", default="", help="证据文件名后缀")
    parser.add_argument("--live", action="store_true",
                        help="允许最多 4 次真实调用（每类 1 次，不重试）")
    args = parser.parse_args()

    definitions = fixture_definitions()
    checks: list[dict[str, Any]] = []
    print("=" * 72)
    print("V2.2.4 四类商品理解通用性探针（Gate G2 证据）")
    print("=" * 72)

    def check(check_id: str, title: str, ok: bool | None, detail: object = None,
              mode: str = "offline") -> None:
        checks.append({"id": check_id, "title": title, "ok": ok, "detail": detail,
                       "mode": mode})
        label = "PASS" if ok is True else ("FAIL" if ok is False else "SKIP")
        print(f"  [{label}] {check_id} {title}")
        if ok is False:
            print("       " + json.dumps(detail, ensure_ascii=False)[:800])

    requests: dict[str, contract.SemanticRequest] = {}
    parse_problems: dict[str, str] = {}
    for item in definitions:
        try:
            requests[item["key"]] = contract.parse_request(item["payload"])
        except Exception as error:  # noqa: BLE001 - 契约失败必须留证
            parse_problems[item["key"]] = f"{type(error).__name__}: {error}"

    messages = {key: user_message(request) for key, request in requests.items()}
    fingerprints = {key: hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                    for key, text in messages.items()}
    distinct = len(set(messages.values())) == len(definitions)
    check("V2.2.4-C1", "输入驱动：四个 fixture 通过 parse_request 且用户消息两两不同",
          not parse_problems and len(requests) == len(definitions) and distinct,
          {"parse_problems": parse_problems,
           "projections": {item["key"]: projection(requests[item["key"]])
                           for item in definitions if item["key"] in requests},
           "fingerprints": fingerprints, "distinct_user_messages": distinct})

    all_tokens = tuple(token for item in definitions for token in item["tokens"])
    leaks = scan_constant_leaks(all_tokens)
    enum_hits = category_enumeration_hits()
    check("V2.2.4-C5", "无常量泄漏：fixture 词不在 src/config/JS 里，系统提示无品类枚举",
          not leaks and not enum_hits,
          {"leaks": leaks, "category_enumeration_hits": enum_hits,
           "scanned_tokens": list(all_tokens), "scan_roots": list(SCAN_ROOTS)})

    classes: dict[str, Any] = {item["key"]: {"status": "not_evaluated"} for item in definitions}
    calls_used = 0
    provider_info: dict[str, Any] = {}
    if args.live:
        classes, calls_used, provider_info = analyze_live(definitions, requests)
        if calls_used > LIVE_BUDGET_CALLS:
            check("V2.2.4-L0", f"调用预算：最多 {LIVE_BUDGET_CALLS} 次真实调用", False,
                  {"calls_used": calls_used}, mode="live")
        elif not provider_info.get("configured"):
            check("V2.2.4-L0", "真实调用前置：DASHSCOPE_API_KEY 可用", False,
                  provider_info, mode="live")
        else:
            check("V2.2.4-L0", "真实调用前置：注册表 provider 已配置且一次一类",
                  calls_used <= LIVE_BUDGET_CALLS and bool(provider_info.get("configured")),
                  {"calls_used": calls_used, "budget": LIVE_BUDGET_CALLS, "provider": provider_info},
                  mode="live")

        problems = check_proposal_problems(classes)
        c2_ok = bool(problems) and all(not issues for issues in problems.values())
        check("V2.2.4-C2", "合法性：每个返回槽位都通过消费侧 check_proposal_slot", c2_ok,
              {"problems": problems}, mode="live")

        structure = evaluate_structure(classes)
        check("V2.2.4-C3", "结构差异：四类动态槽位集合两两不全等且至少两类有独有槽位",
              bool(structure["complete"] and structure["no_equal_pair"]
                   and structure["unique_classes_ok"]),
              structure, mode="live")

        traceability = evaluate_traceability(classes)
        check("V2.2.4-C4", "可追溯：动态槽位 source/status/confidence/evidence 与 summary 合规",
              all(item.get("ok") for item in traceability.values()), traceability,
              mode="live")
    else:
        for check_id, title in (
            ("V2.2.4-C2", "合法性：每个返回槽位都通过消费侧 check_proposal_slot"),
            ("V2.2.4-C3", "结构差异：四类动态槽位集合两两不全等且至少两类有独有槽位"),
            ("V2.2.4-C4", "可追溯：动态槽位 source/status/confidence/evidence 与 summary 合规"),
        ):
            check(check_id, title + "（需要 --live）", None,
                  {"reason": "offline 模式按计划 §9.3 只跑 C1 与 C5"}, mode="live")

    failed = [item for item in checks if item["ok"] is False]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mode = "live" if args.live else "offline"
    boundary = (
        "证明四类 fixture 的输入投影两两不同（C1）、实现里没有把 fixture 商品词或品类枚举写成常量"
        "（C5）；--live 另外证明每类一次真实调用返回的槽位合法（C2）、四类动态槽位结构两两不同且"
        "至少两类有独有槽位（C3）、来源/状态/置信度/证据/summary 可追溯（C4）。不证明：槽位语义是否"
        "覆盖该类真实卖点、界面投影是否好用、套图规划/生成/交付闭环，以及模型在别的输入上的稳定性。"
    )
    report = {
        "task": "V2.2.4",
        "suite_id": "v2.2.4-category-generality",
        "status": status,
        "mode": mode,
        "finished_at": finished_at,
        "policy": {"live_budget_calls": LIVE_BUDGET_CALLS, "calls_used": calls_used,
                   "no_retry": True},
        "fixtures": [
            {"key": item["key"], "label": item["label"], "expect": item["expect"],
             "tokens": list(item["tokens"]), "fingerprint": fingerprints.get(item["key"]),
             "projection": projection(requests[item["key"]]) if item["key"] in requests else None}
            for item in definitions
        ],
        "checks": checks,
        "provider": provider_info,
        "classes": classes,
        "boundary": boundary,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.2.4-category-generality-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.2.4-category-generality-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.2.4 category generality probe (Gate G2 evidence)",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        f"mode: {mode}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        f"policy: live_budget_calls={LIVE_BUDGET_CALLS} calls_used={calls_used} no_retry=true",
        "",
        "CRITERIA",
    ]
    for item in checks:
        mark = "PASS" if item["ok"] is True else ("FAIL" if item["ok"] is False else "SKIP")
        lines.append(f"- [{mark}] {item['id']} {item['title']}")
        if item["ok"] is False:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False)[:800])
    lines += ["", "FIXTURES"]
    for item in definitions:
        lines.append(f"- {item['key']}（{item['label']}）：期望 {item['expect']}；"
                     f"用户消息指纹 {fingerprints.get(item['key'], 'n/a')}")
    lines += ["", "CLASSES"]
    for item in definitions:
        key = item["key"]
        entry = classes.get(key, {})
        lines.append(f"## {key}（{item['label']}）status={entry.get('status')}")
        proposal = entry.get("proposal") or {}
        meta = proposal.get("meta") or {}
        if entry.get("status") == "proposed":
            lines.append(f"- summary: {proposal.get('summary')}")
            lines.append("- questions: " + json.dumps(proposal.get("questions"), ensure_ascii=False))
            lines.append("- core_slots: " + json.dumps(entry.get("core_slots"), ensure_ascii=False))
            lines.append("- dynamic_slots: " + json.dumps(entry.get("dynamic_slots"), ensure_ascii=False))
            lines.append("- meta: " + json.dumps(
                {"provider_id": meta.get("provider_id"), "model_id": meta.get("model_id"),
                 "request_id": meta.get("request_id"), "usage": meta.get("usage"),
                 "latency_ms": meta.get("latency_ms"), "attempts": meta.get("attempts")},
                ensure_ascii=False))
        elif entry.get("failure"):
            lines.append("- failure: " + json.dumps(entry["failure"], ensure_ascii=False)[:800])
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("-" * 72)
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    passed = [item for item in checks if item["ok"] is True]
    skipped = [item for item in checks if item["ok"] is None]
    print(f"结果：{len(passed)}/{len(checks) - len(skipped)} 通过"
          f"（SKIP {len(skipped)}：需要 --live）；"
          f"{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
