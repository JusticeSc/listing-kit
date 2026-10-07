"""Compile editable ProductBrief records from semantic model proposals."""
from __future__ import annotations

from typing import Any, Mapping

from src.semantic_drafts import validate_draft

_FACT_STATES = {"confirmed", "inferred", "unknown", "conflicted"}
_FACT_SOURCES = {"user_input", "reference_image", "model_inference", "user_override"}
_CATEGORY_SOURCES = {"user_input", "reference_image", "model_inference", "user_override"}
_EDITABLE_FIELDS = {"category", "facts", "must_preserve", "may_change", "unknowns"}


class ProductBriefEditError(ValueError):
    """The user-edited ProductBrief projection has an invalid shape."""


def _input_assertions(product_input: Mapping[str, Any]) -> list[dict[str, str]]:
    ref = f"product_input:{product_input['id']}@v{product_input['version']}"
    result = [{"key": "product_name", "value": str(product_input.get("product_name") or "").strip(), "source_ref": ref}]
    for index, point in enumerate(product_input.get("selling_points", []), start=1):
        result.append({"key": f"selling_point_{index}", "value": str(point.get("text") or "").strip(), "source_ref": ref})
    return [item for item in result if item["value"]]


def compile_product_brief_draft(
    draft: Mapping[str, Any], product_input: Mapping[str, Any], *,
    provider_id: str, model_id: str, request_id: str | None,
    reference_asset_sha256: list[str],
) -> dict[str, Any]:
    """Return an editable, unsaved Brief projection from a validated model draft."""
    validate_draft("analyze_product", draft)
    model_ref = f"semantic:{provider_id}:{model_id}" + (f":request:{request_id}" if request_id else "")
    input_facts = _input_assertions(product_input)
    input_keys = {item["key"] for item in input_facts}
    facts: list[dict[str, Any]] = []
    for assertion in input_facts:
        facts.append({"key": assertion["key"], "value": assertion["value"], "state": "confirmed",
                      "source": "user_input", "confidence": 1.0, "source_refs": [assertion["source_ref"]]})
    for item in draft["facts"]:
        key, fact_value = item["key"].strip(), item["value"].strip()
        if key in input_keys:
            continue
        source = "reference_image" if item["source"] == "reference_image" else "model_inference"
        state = item["state"] if item["state"] != "confirmed" else "inferred"
        refs = [model_ref]
        if source == "reference_image":
            refs.extend(f"reference_image:{digest}" for digest in reference_asset_sha256)
        facts.append({"key": key, "value": fact_value, "state": state, "source": source,
                      "confidence": item["confidence"], "source_refs": list(dict.fromkeys(refs))})
    category = dict(draft["category"])
    category["source"] = "model_inference"
    return {"category": category, "facts": facts, "must_preserve": list(draft["must_preserve"]),
            "may_change": list(draft["may_change"]), "unknowns": list(draft["unknowns"])}


def normalize_product_brief_edits(
    value: Mapping[str, Any], product_input: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate editable fields and enforce confirmation/source invariants."""
    if not isinstance(value, Mapping) or set(value) != _EDITABLE_FIELDS:
        raise ProductBriefEditError("商品理解字段不完整或包含不支持的内容，请重新载入后重试。")
    category = value["category"]
    if not isinstance(category, Mapping) or set(category) != {"label", "confidence", "source"}:
        raise ProductBriefEditError("商品类别字段格式无效。")
    label, confidence, category_source = category["label"], category["confidence"], category["source"]
    if label is not None and (not isinstance(label, str) or len(label) > 160):
        raise ProductBriefEditError("商品类别不能超过 160 个字符。")
    if confidence is not None and (
        isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1
    ):
        raise ProductBriefEditError("商品类别置信度格式无效。")
    if category_source not in _CATEGORY_SOURCES:
        raise ProductBriefEditError("商品类别来源无效。")
    if category_source != "user_override":
        category_source = "model_inference"

    raw_facts = value["facts"]
    if not isinstance(raw_facts, list) or len(raw_facts) > 100:
        raise ProductBriefEditError("商品事实列表格式无效。")
    input_ref = f"product_input:{product_input['id']}@v{product_input['version']}"
    input_assertions = {item["key"]: item["value"] for item in _input_assertions(product_input)}
    facts: list[dict[str, Any]] = []
    fields = {"key", "value", "state", "source", "confidence", "source_refs"}
    for item in raw_facts:
        if not isinstance(item, Mapping) or set(item) != fields:
            raise ProductBriefEditError("有一条商品事实字段不完整。")
        key, fact_value, state, source = item["key"], item["value"], item["state"], item["source"]
        confidence, source_refs = item["confidence"], item["source_refs"]
        if not isinstance(key, str) or not key.strip() or len(key) > 160:
            raise ProductBriefEditError("商品事实名称无效。")
        if not isinstance(fact_value, str) or len(fact_value) > 2000:
            raise ProductBriefEditError("商品事实内容无效或过长。")
        if state not in _FACT_STATES or source not in _FACT_SOURCES:
            raise ProductBriefEditError("商品事实的核对状态或来源无效。")
        if confidence is not None and (
            isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1
        ):
            raise ProductBriefEditError("商品事实置信度格式无效。")
        if not isinstance(source_refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in source_refs):
            raise ProductBriefEditError("商品事实来源引用无效。")
        if source == "user_override":
            refs = list(dict.fromkeys([*source_refs, "user_override"]))
        elif source == "user_input" and input_assertions.get(key) == fact_value.strip():
            refs, state = [input_ref], "confirmed"
        else:
            source = "reference_image" if source == "reference_image" else "model_inference"
            if state == "confirmed":
                state = "inferred"
            refs = list(dict.fromkeys(source_refs))
        facts.append({"key": key.strip(), "value": fact_value.strip(), "state": state,
                      "source": source, "confidence": confidence, "source_refs": refs})

    def string_list(name: str) -> list[str]:
        items = value[name]
        if not isinstance(items, list) or len(items) > 100:
            raise ProductBriefEditError(f"{name} 列表格式无效。")
        result = []
        for item in items:
            if not isinstance(item, str) or len(item) > 1000:
                raise ProductBriefEditError(f"{name} 中有无效或过长的内容。")
            if item.strip():
                result.append(item.strip())
        return result

    return {
        "category": {"label": label.strip() if isinstance(label, str) else None,
                     "confidence": confidence, "source": category_source},
        "facts": facts, "must_preserve": string_list("must_preserve"),
        "may_change": string_list("may_change"), "unknowns": string_list("unknowns"),
    }
