"""Compile model-proposed visual directions into traceable image prompts.

The semantic model may propose visual treatment. Product claims and marketplace
constraints are assembled locally from the current Brief, ShotSpec, and profile.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


class ProductPromptCompilationError(ValueError):
    """A prompt draft cannot be safely bound to the current product task."""


_CONFIRMED_SOURCES = {"user_input", "user_override"}
_MODEL_KINDS = {"style_lock", "shot_task", "negative"}


def _normalized_phrase(value: str) -> str:
    return "".join(character.casefold() for character in value if not character.isspace())


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = value.strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _fact_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _block(block_id: str, kind: str, text: str, source_refs: list[str]) -> dict[str, Any]:
    clean = text.strip()
    if not clean:
        raise ProductPromptCompilationError(f"PromptBlock {block_id} 不能为空。")
    return {
        "id": block_id,
        "kind": kind,
        "text": clean,
        "source_refs": _unique(source_refs),
    }


def _supported_facts(
    product_brief: Mapping[str, Any], shot_spec: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    eligible = {
        fact["key"]: fact
        for fact in product_brief.get("facts", [])
        if isinstance(fact, Mapping)
        and isinstance(fact.get("key"), str)
        and fact.get("state") == "confirmed"
        and fact.get("source") in _CONFIRMED_SOURCES
    }
    keys = shot_spec.get("supporting_fact_keys", [])
    if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
        raise ProductPromptCompilationError("当前图片的商品事实引用格式无效。")
    facts: dict[str, Mapping[str, Any]] = {}
    texts: dict[str, str] = {}
    for key in keys:
        fact = eligible.get(key)
        value = _fact_text(fact.get("value")) if fact else None
        if fact is None or value is None:
            raise ProductPromptCompilationError(
                f"图片“{shot_spec.get('title', '')}”引用了未由用户确认的商品事实“{key}”，提示词未生成。"
            )
        facts[key] = fact
        texts[key] = value
    return facts, texts


def _validate_model_blocks(
    draft: Mapping[str, Any],
    *,
    product_brief: Mapping[str, Any],
    shot_spec: Mapping[str, Any],
    user_intent: str | None,
    supported_fact_keys: set[str],
    user_texts: Sequence[str] = (),
) -> dict[str, Mapping[str, Any]]:
    blocks = draft.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ProductPromptCompilationError("模型没有返回可用的 PromptBlocks，提示词未保存。")

    allowed_by_kind = {
        "style_lock": {"plan.style_lock"},
        "shot_task": {"shot_spec.title", "shot_spec.purpose"}
        | ({"product_input.user_intent"} if user_intent else set())
        | {f"product_brief.fact:{key}" for key in supported_fact_keys},
        "negative": {"shot_spec.preserve", "shot_spec.change"},
    }
    by_kind: dict[str, Mapping[str, Any]] = {}
    seen_ids: set[str] = set()
    generated_text: list[str] = []
    for block in blocks:
        if not isinstance(block, Mapping):
            raise ProductPromptCompilationError("模型返回的 PromptBlock 格式无效，提示词未保存。")
        block_id, kind, text = block.get("id"), block.get("kind"), block.get("text")
        refs = block.get("source_refs")
        if not isinstance(block_id, str) or not block_id.strip() or block_id in seen_ids:
            raise ProductPromptCompilationError("模型返回的 PromptBlock 标识为空或重复，提示词未保存。")
        if kind not in _MODEL_KINDS:
            raise ProductPromptCompilationError("模型试图生成只能由系统规则控制的 PromptBlock。")
        if kind in by_kind:
            raise ProductPromptCompilationError(f"模型重复返回“{kind}”类型 PromptBlock。")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ProductPromptCompilationError(f"模型返回的“{kind}”提示词为空或过长。")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs):
            raise ProductPromptCompilationError(f"模型返回的“{kind}”提示词缺少有效来源。")
        allowed = allowed_by_kind[kind]
        usable_refs = [ref for ref in refs if ref in allowed]
        if not usable_refs:
            raise ProductPromptCompilationError(f"模型返回的“{kind}”提示词引用了当前任务不可用的来源。")
        # A model may attach an extra reference that does not belong to this block
        # kind; drop the unknown reference instead of discarding usable direction,
        # but never accept it as a source.
        refs = usable_refs
        if kind == "style_lock" and "plan.style_lock" not in refs:
            raise ProductPromptCompilationError("风格提示词没有引用当前套图的 Style Lock。")
        if kind == "shot_task" and not ({"shot_spec.title", "shot_spec.purpose"} & set(refs)):
            raise ProductPromptCompilationError("图片任务提示词没有引用当前 Shot 的目标。")
        if kind == "negative" and not ({"shot_spec.preserve", "shot_spec.change"} & set(refs)):
            raise ProductPromptCompilationError("负面约束没有引用当前 Shot 的修改边界。")
        seen_ids.add(block_id)
        by_kind[kind] = {**block, "source_refs": list(refs)}
        generated_text.append(text)

    for required_kind in ("style_lock", "shot_task"):
        if required_kind not in by_kind:
            raise ProductPromptCompilationError(f"模型没有提供必需的“{required_kind}”提示词方向。")

    # A deterministic literal guard complements source binding: exact values from
    # non-supported facts must not leak into affirmative model-written text.
    allowed_values = {
        _normalized_phrase(_fact_text(fact.get("value")) or "")
        for key, fact in (
            (item.get("key"), item)
            for item in product_brief.get("facts", [])
            if isinstance(item, Mapping)
        )
        if key in supported_fact_keys and fact.get("state") == "confirmed"
        and fact.get("source") in _CONFIRMED_SOURCES
    }
    combined = _normalized_phrase("\n".join(generated_text))
    approved_wording = _normalized_phrase("\n".join([
        str(shot_spec.get("title") or ""),
        str(shot_spec.get("purpose") or ""),
        *[str(item) for item in shot_spec.get("preserve", [])],
        *[str(item) for item in shot_spec.get("change", [])],
        str(user_intent or ""),
        # The user's own intake wording is authoritative. An inferred fact whose
        # literal value merely appears inside the user's product name or
        # description (the garment word inside a chunky knit pullover name, for
        # example) must not be rejected as an unauthorised claim.
        *[str(item) for item in user_texts],
    ]))
    for fact in product_brief.get("facts", []):
        if not isinstance(fact, Mapping) or fact.get("key") in supported_fact_keys:
            continue
        if fact.get("state") == "confirmed" and fact.get("source") in _CONFIRMED_SOURCES:
            # The shot-level fact list decides which claims the compiler writes as
            # affirmative copy. A user-confirmed product truth may still appear in
            # the model's visual direction; only unconfirmed or conflicting values
            # must never leak into the prompt text.
            continue
        if fact.get("source") == "reference_image" and fact.get("state") != "conflicted":
            # Something the analysis read off the user's own reference photo (colour,
            # texture, length ...) is legitimate visual vocabulary for a shot task;
            # the fidelity block still makes that photo the sole authority for how the
            # product looks. Blocking these values aborted whole-set generation.
            continue
        value = _fact_text(fact.get("value"))
        phrase = _normalized_phrase(value or "")
        if (
            phrase and len(phrase) >= 3 and phrase not in allowed_values
            and phrase not in approved_wording and phrase in combined
        ):
            raise ProductPromptCompilationError(
                f"模型提示词提到了当前 Shot 未授权的商品事实“{fact.get('key', 'unknown')}”，本版本未保存。"
            )
    return by_kind


def compile_prompt_blocks(
    draft: Mapping[str, Any],
    *,
    product_input: Mapping[str, Any],
    product_brief: Mapping[str, Any],
    shot_spec: Mapping[str, Any],
    plan: Mapping[str, Any],
    platform_profile: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Assemble deterministic product/platform blocks around model visual direction."""
    supported_facts, fact_texts = _supported_facts(product_brief, shot_spec)
    style_lock = plan.get("style_lock")
    if not isinstance(style_lock, Mapping):
        raise ProductPromptCompilationError("当前套图方案缺少 Style Lock。")

    user_intent = product_input.get("user_intent")
    if not isinstance(user_intent, str) or not user_intent.strip():
        user_intent = None
    user_texts = [
        str(product_input.get("product_name") or ""),
        str(product_input.get("description") or ""),
    ]
    for point in product_input.get("selling_points") or []:
        text = point.get("text") if isinstance(point, Mapping) else point
        if isinstance(text, str):
            user_texts.append(text)
    model_blocks = _validate_model_blocks(
        draft,
        product_brief=product_brief,
        shot_spec=shot_spec,
        user_intent=user_intent,
        supported_fact_keys=set(supported_facts),
        user_texts=user_texts,
    )

    preserve = _unique(list(shot_spec.get("preserve", [])))
    conflicted = _unique([
        str(item.get("value")).strip()
        for item in product_brief.get("facts", [])
        if item.get("state") == "conflicted" and str(item.get("value") or "").strip()
    ])
    fidelity_text = (
        "Use the supplied reference image(s) as the sole authority for the product's visual identity. "
        "Preserve the exact visible silhouette, proportions, colors, markings, closure, surface appearance, "
        "and existing parts. Do not add, remove, duplicate, recolor, or redesign product features."
    )
    if conflicted:
        fidelity_text += (
            " These user-supplied words conflict with the reference image and are NOT confirmed: "
            + "; ".join(conflicted)
            + ". The reference image decides every visible part."
        )
    if preserve:
        fidelity_text += " Preserve these user-facing boundaries: " + "; ".join(preserve) + "."
    if fact_texts:
        fidelity_text += (
            " If any product statement is added to the image, use only these user-confirmed statements, "
            "verbatim: " + "; ".join(fact_texts.values()) + ". Do not imply additional specifications or benefits."
        )
    else:
        fidelity_text += " Do not add product claims, specifications, badges, or on-image text."
    fact_refs = [f"product_brief.fact:{key}" for key in fact_texts]
    compiled: list[dict[str, Any]] = [
        _block(
            "product-fidelity", "product_fidelity", fidelity_text,
            ["product_input.reference_asset_sha256", "shot_spec.preserve", *fact_refs],
        )
    ]

    style_fields = [
        ("direction", style_lock.get("direction")),
        ("palette", ", ".join(style_lock.get("palette", []))),
        ("lighting", style_lock.get("lighting")),
        ("background", style_lock.get("background")),
        ("continuity", "; ".join(style_lock.get("continuity_notes", []))),
    ]
    style_text = "; ".join(f"{name}: {value}" for name, value in style_fields if value)
    style_text += "\n" + str(model_blocks["style_lock"]["text"]).strip()
    compiled.append(_block(
        "style-lock", "style_lock", style_text,
        ["plan.style_lock", *model_blocks["style_lock"]["source_refs"]],
    ))

    compiled.append(_block(
        "shot-task", "shot_task", str(model_blocks["shot_task"]["text"]),
        list(model_blocks["shot_task"]["source_refs"]),
    ))

    marketplace = platform_profile.get("marketplace", "amazon.com")
    platform_text = f"Create a clear, compliant product-listing image for {marketplace}."
    if shot_spec.get("archetype_id") == "hero":
        guidance = platform_profile.get("main_image_guidance", {})
        rgb = guidance.get("background_rgb", [255, 255, 255])
        occupancy = guidance.get("minimum_product_occupancy_percent", 85)
        platform_text += (
            f" Main image: use a pure white RGB({rgb[0]}, {rgb[1]}, {rgb[2]}) background; "
            f"aim for product occupancy of at least {occupancy}%; do not add text overlays or watermarks."
        )
    compiled.append(_block(
        "platform-rules", "platform", platform_text,
        [f"platform_profile:{platform_profile.get('profile_id', 'unknown')}@{platform_profile.get('version', 1)}"],
    ))

    if "negative" in model_blocks:
        negative_text = str(model_blocks["negative"]["text"]).strip()
        negative_refs = list(model_blocks["negative"]["source_refs"])
    else:
        negative_text = "No unsupported product features or performance claims; no extra products, parts, or props that change the offer."
        negative_refs = []
    if conflicted:
        # This block is compiled last, so the override keeps the final word when
        # the model's own visual direction asks for a part the photo never had.
        negative_text = negative_text.rstrip().rstrip("。").rstrip(".")
        negative_text += (
            ". Do not add, require, or invent any part that is not clearly visible in the reference "
            "image; ignore any framing or detail requirement that names one of these unconfirmed words: "
            + "; ".join(conflicted) + "."
        )
    compiled.append(_block(
        "negative-constraints", "negative", negative_text,
        [*negative_refs, "shot_spec.preserve", "shot_spec.change"],
    ))

    # Catch literal unsupported facts in all model-authored wording, including the
    # plan fields copied into style or task blocks. This does not claim semantic NLP proof.
    disallowed = {
        fact.get("key"): _fact_text(fact.get("value"))
        for fact in product_brief.get("facts", [])
        if isinstance(fact, Mapping) and fact.get("key") not in supported_facts
        and fact.get("state") != "confirmed"
    }
    final_text = _normalized_phrase("\n".join(block["text"] for block in compiled))
    approved_wording = _normalized_phrase("\n".join([
        str(shot_spec.get("title") or ""),
        str(shot_spec.get("purpose") or ""),
        *[str(item) for item in shot_spec.get("preserve", [])],
        *[str(item) for item in shot_spec.get("change", [])],
        str(user_intent or ""),
        str(style_lock.get("direction") or ""),
        *[str(item) for item in style_lock.get("palette", [])],
        str(style_lock.get("lighting") or ""),
        str(style_lock.get("background") or ""),
        *[str(item) for item in style_lock.get("continuity_notes", [])],
        *fact_texts.values(),
    ]))
    for key, value in disallowed.items():
        phrase = _normalized_phrase(value or "")
        if phrase and len(phrase) >= 3 and phrase in final_text and phrase not in approved_wording:
            raise ProductPromptCompilationError(
                f"当前 Prompt 会把未确认事实“{key}”带入图片任务，版本未保存。"
            )

    full_text = "\n\n".join(block["text"] for block in compiled)
    return compiled, full_text
