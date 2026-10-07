"""Compile provider PlanDrafts into source-checked, editable Product V1 shots."""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Mapping

from src.semantic_drafts import validate_draft


class ProductPlanCompilationError(ValueError):
    """A semantic plan cannot be compiled into a safe, traceable plan."""


def _normalize_title(value: str) -> str:
    """Casefold a reference and drop bracketed qualifiers and separators."""
    text = value.strip().casefold()
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    text = re.sub(r"[【\[][^】\]]*[】\]]", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def compile_product_plan_draft(
    draft: Mapping[str, Any],
    product_input: Mapping[str, Any],
    product_brief: Mapping[str, Any],
    platform_profile: Mapping[str, Any],
    archetype_registry: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Normalize a model proposal and omit shots lacking policy-required evidence.

    Model-provided source labels are not trusted here. A shot can cite only fact
    keys already present in the saved ProductBrief as confirmed user input or an
    explicit user override, and only reference images belonging to this input.
    """
    validate_draft("propose_plan", draft)
    archetypes = {item["id"]: item for item in archetype_registry["archetypes"]}
    fallback = archetypes.get("custom")
    if fallback is None:
        raise ProductPlanCompilationError("Archetype Registry 缺少 custom 通用回退图型。")

    confirmed_facts = {
        item["key"]: item
        for item in product_brief.get("facts", [])
        if item.get("state") == "confirmed" and item.get("source") in {"user_input", "user_override"}
    }
    # Wording the product analysis could not confirm against the reference photo.
    conflicted_values = [
        str(item.get("value")).strip()
        for item in product_brief.get("facts", [])
        if item.get("state") == "conflicted" and str(item.get("value") or "").strip()
    ]
    reference_hashes = list(dict.fromkeys(product_input.get("reference_asset_sha256", [])))
    known_references = set(reference_hashes)
    has_user_intent = bool(str(product_input.get("user_intent") or "").strip())
    required_archetypes = set(platform_profile.get("required_archetypes", []))
    warnings: list[dict[str, str]] = []
    omitted_titles: set[str] = set()
    shots: list[dict[str, Any]] = []

    def warning(code: str, title: str, message: str) -> None:
        warnings.append({"code": code, "title": title, "message": message})

    for proposed in draft["shots"]:
        title = proposed["title"].strip()
        archetype_id = proposed["archetype_id"]
        archetype = archetypes.get(archetype_id)
        if archetype is None:
            warning(
                "ARCHETYPE_FALLBACK", title,
                f"图型“{archetype_id}”不在当前注册表中，已按通用自定义图型处理。",
            )
            archetype_id, archetype = "custom", fallback

        fact_keys = list(proposed["supporting_fact_keys"])
        unknown_facts = [key for key in fact_keys if key not in confirmed_facts]
        refs = list(proposed["reference_asset_sha256"]) or list(reference_hashes)
        foreign_refs = [digest for digest in refs if digest not in known_references]
        if unknown_facts or foreign_refs:
            omitted_titles.add(title.casefold())
            warning(
                "UNSUPPORTED_SHOT_OMITTED", title,
                "该图片方案引用了未确认商品事实或不属于当前商品的参考图，已从方案中排除。",
            )
            continue

        policy = archetype["evidence_policy"]
        supported = (
            (policy == "confirmed_fact" and bool(fact_keys))
            or (policy == "reference_asset" and bool(refs))
            or (
                policy == "user_intent_or_fact_or_reference"
                and bool(fact_keys or refs or has_user_intent)
            )
        )
        if not supported:
            omitted_titles.add(title.casefold())
            warning(
                "UNSUPPORTED_SHOT_OMITTED", title,
                "该图型缺少注册表要求的已确认资料、参考图或用户意图，已从方案中排除。",
            )
            continue

        shots.append({
            "id": f"shot_{uuid.uuid4().hex[:16]}",
            "archetype_id": archetype_id,
            "title": title,
            "purpose": proposed["purpose"].strip(),
            "reason": proposed["reason"].strip(),
            "required": archetype_id in required_archetypes,
            "preserve": list(proposed["preserve"]),
            "change": list(proposed["change"]),
            "reference_asset_sha256": refs,
            "supporting_fact_keys": fact_keys,
            "dependency_titles": list(proposed["dependencies"]),
        })
        shot_text = " ".join([
            title, proposed["purpose"], proposed["reason"],
            *proposed["preserve"], *proposed["change"],
        ])
        used = [term for term in conflicted_values if term in shot_text]
        if used:
            warning(
                "CONFLICTED_WORDING_IN_SHOT", title,
                "该图片方案使用了与参考图冲突且未确认的措辞（" + "、".join(used)
                + "）；编译提示词时以参考图为准，不把它当作商品事实，建议改写标题或任务描述。",
            )

    for required_id in sorted(required_archetypes):
        matching = [shot for shot in shots if shot["archetype_id"] == required_id]
        if matching:
            if len(matching) > 1:
                for duplicate in matching[1:]:
                    shots.remove(duplicate)
                    omitted_titles.add(duplicate["title"].casefold())
                    warning(
                        "DUPLICATE_REQUIRED_SHOT_OMITTED", duplicate["title"],
                        f"平台必需图型“{required_id}”只保留一张，重复方案已排除。",
                    )
            continue

        archetype = archetypes.get(required_id)
        if archetype is None:
            raise ProductPlanCompilationError(f"平台要求未注册的图型：{required_id}。")
        title = "Amazon US 主图" if required_id == "hero" else f"平台必需：{required_id}"
        shots.insert(0, {
            "id": f"shot_{uuid.uuid4().hex[:16]}",
            "archetype_id": required_id,
            "title": title,
            "purpose": archetype["purpose"],
            "reason": f"{platform_profile['marketplace']} 平台配置将此图型列为必需。",
            "required": True,
            "preserve": ["商品身份、可见轮廓与真实颜色"],
            "change": ["按该平台图型要求组织背景与构图"],
            "reference_asset_sha256": list(reference_hashes),
            "supporting_fact_keys": [
                key for key in ("product_name",) if key in confirmed_facts
            ],
            "dependency_titles": [],
        })
        warning(
            "REQUIRED_SHOT_ADDED", title,
            f"模型方案未提供平台必需图型“{required_id}”，系统已按平台配置补入。",
        )

    titles: dict[str, dict[str, Any]] = {}
    archetype_shots: dict[str, dict[str, Any] | None] = {}
    normalized_titles: dict[str, list[dict[str, Any]]] = {}
    for shot in shots:
        key = shot["title"].casefold()
        if key in titles:
            raise ProductPlanCompilationError(f"有两张图片方案使用同一标题“{shot['title']}”。")
        titles[key] = shot
        archetype_key = shot["archetype_id"].strip().casefold()
        # A model may reference an archetype id instead of a shot title; keep it
        # only while it identifies exactly one shot in this plan.
        archetype_shots[archetype_key] = (
            shot if archetype_key not in archetype_shots else None
        )
        normalized_titles.setdefault(_normalize_title(shot["title"]), []).append(shot)

    for shot in shots:
        dependencies = []
        for dependency_title in shot.pop("dependency_titles"):
            raw_reference = dependency_title.strip()
            dependency_key = raw_reference.casefold()
            dependency = titles.get(dependency_key)
            if dependency is None:
                dependency = archetype_shots.get(dependency_key)
            if dependency is None:
                matches = normalized_titles.get(_normalize_title(raw_reference), [])
                if len(matches) == 1:
                    dependency = matches[0]
            if dependency is None:
                if dependency_key in omitted_titles:
                    warning(
                        "OMITTED_SHOT_DEPENDENCY", shot["title"],
                        f"依赖的图片“{raw_reference}”已因证据不足被排除，依赖关系已移除。",
                    )
                else:
                    # A dangling reference is a model slip about ordering, not a
                    # reason to block a new product; drop the edge and record it.
                    warning(
                        "UNRESOLVED_SHOT_DEPENDENCY", shot["title"],
                        f"无法识别的图型参考“{raw_reference}”不能匹配任何图片标题或图型，"
                        "该前置关系已移除。",
                    )
                continue
            if dependency["id"] == shot["id"]:
                warning(
                    "SELF_SHOT_DEPENDENCY", shot["title"],
                    "方案让这张图片依赖自身，该前置关系已移除。",
                )
                continue
            if dependency["id"] not in dependencies:
                dependencies.append(dependency["id"])
        shot["dependencies"] = dependencies

    graph = {shot["id"]: shot["dependencies"] for shot in shots}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(shot_id: str) -> None:
        if shot_id in visiting:
            raise ProductPlanCompilationError("图片之间的前置关系形成循环，请重新生成方案。")
        if shot_id in visited:
            return
        visiting.add(shot_id)
        for dependency in graph[shot_id]:
            visit(dependency)
        visiting.remove(shot_id)
        visited.add(shot_id)

    for shot_id in graph:
        visit(shot_id)

    return {"style_lock": copy.deepcopy(draft["style_lock"]), "shots": shots}, warnings
