"""Strict Product V1 JSON contracts and cross-record reference checks.

JSON Schema owns document shapes. This module adds only rules JSON Schema cannot
express safely on its own: immutable content hashes, workspace-local references,
configuration membership, and export/selection consistency.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "product-v1.schema.json"
DOCUMENT_KINDS = frozenset({
    "workspace", "product_input", "product_brief", "plan", "shot_spec",
    "prompt", "generation_attempt", "candidate", "selection", "export",
})
CONFIG_KINDS = frozenset({"archetype_registry", "platform_profile", "provider_registry"})
HASHED_KINDS = frozenset({
    "product_input", "product_brief", "plan", "shot_spec", "prompt",
    "selection", "export",
})
VERSIONED_KINDS = HASHED_KINDS
ID_FIELDS = {
    "product_input": "id", "product_brief": "id", "plan": "id",
    "shot_spec": "id", "prompt": "id", "selection": "id", "export": "id",
}
POINTER_KINDS = {
    "product_input": "product_input", "product_brief": "product_brief",
    "plan": "plan", "selection": "selection", "export": "export",
}


class ContractError(ValueError):
    """Raised when a Product V1 document violates its frozen schema."""


@lru_cache(maxsize=1)
def _schema_document() -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = _schema_document()
    return Draft202012Validator(schema, format_checker=FormatChecker())


@lru_cache(maxsize=32)
def _record_validator(kind: str) -> Draft202012Validator:
    """Validate a record against its definition directly for actionable paths."""
    schema = _schema_document()
    record_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{kind}",
    }
    return Draft202012Validator(record_schema, format_checker=FormatChecker())


def _validation_location(error: Any) -> str:
    """Return a JSON-pointer-like path, including a missing required property."""
    parts = [str(part) for part in error.absolute_path]
    if error.validator == "required":
        missing = re.match(r"^'([^']+)' is a required property$", error.message)
        if missing:
            parts.append(missing.group(1))
    elif error.validator == "additionalProperties":
        unexpected = re.search(r"\((.+?) (?:was|were) unexpected\)", error.message)
        if unexpected:
            names = re.findall(r"'([^']+)'", unexpected.group(1))
            if len(names) == 1:
                parts.append(names[0])
            elif names:
                parts.append("{" + ",".join(names) + "}")
    return "/".join(parts) or "record"


def canonical_content_hash(record: Mapping[str, Any]) -> str:
    """Hash canonical UTF-8 JSON, excluding the hash field itself."""
    payload = {key: value for key, value in record.items() if key != "content_hash"}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seal_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with its content_hash set; useful to immutable writers/tests."""
    sealed = dict(record)
    sealed.pop("content_hash", None)
    sealed["content_hash"] = canonical_content_hash(sealed)
    return sealed


def validate_record(kind: str, record: Mapping[str, Any]) -> None:
    """Validate one record's exact shape, schema version, and local digest."""
    if kind not in DOCUMENT_KINDS | CONFIG_KINDS:
        raise ContractError(f"unknown Product V1 contract kind: {kind!r}")
    if not isinstance(record, Mapping):
        raise ContractError(f"{kind}: record must be an object")

    errors = sorted(
        _record_validator(kind).iter_errors(dict(record)),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    if errors:
        first = errors[0]
        location = _validation_location(first)
        raise ContractError(f"{kind}.{location}: {first.message}")

    if kind in HASHED_KINDS:
        actual = canonical_content_hash(record)
        if record.get("content_hash") != actual:
            raise ContractError(
                f"{kind}.content_hash: expected {actual}, got {record.get('content_hash')!r}"
            )
    if kind == "prompt":
        actual = hashlib.sha256(record["full_text"].encode("utf-8")).hexdigest()
        if record["full_text_sha256"] != actual:
            raise ContractError("prompt.full_text_sha256 does not match full_text")
    if kind == "candidate" and record["candidate_id"] != record["file_sha256"]:
        raise ContractError("candidate_id must be the candidate file SHA-256")


def validate_config_bundle(
    archetypes: Mapping[str, Any],
    platform_profile: Mapping[str, Any],
    provider_registry: Mapping[str, Any],
) -> list[str]:
    """Validate the three shipped configs and their cross-config identities."""
    errors: list[str] = []
    for kind, record in (
        ("archetype_registry", archetypes),
        ("platform_profile", platform_profile),
        ("provider_registry", provider_registry),
    ):
        try:
            validate_record(kind, record)
        except ContractError as exc:
            errors.append(str(exc))
    if errors:
        return errors

    archetype_ids = [item["id"] for item in archetypes["archetypes"]]
    if len(archetype_ids) != len(set(archetype_ids)):
        errors.append("archetype_registry: duplicate archetype id")
    if "custom" not in archetype_ids:
        errors.append("archetype_registry.archetypes: required generic fallback 'custom' is missing")
    missing = sorted(set(platform_profile["required_archetypes"]) - set(archetype_ids))
    if missing:
        errors.append(f"platform_profile: required archetypes missing from registry: {missing}")
    file_rules = platform_profile["file_rules"]
    if file_rules["min_long_side_px"] > file_rules["max_long_side_px"]:
        errors.append("platform_profile: minimum long-side pixels exceed maximum")
    if not file_rules["min_long_side_px"] <= file_rules["recommended_zoom_long_side_px"] <= file_rules["max_long_side_px"]:
        errors.append("platform_profile: zoom recommendation is outside accepted pixel bounds")

    providers = {item["id"]: item for item in provider_registry["providers"]}
    if len(providers) != len(provider_registry["providers"]):
        errors.append("provider_registry: duplicate provider id")
    image = providers.get(provider_registry["default_image_provider_id"])
    if image is None or image["role"] != "image":
        errors.append("provider_registry: default_image_provider_id must name an image provider")
    elif not image["capabilities"]["reference_images"] or not image["capabilities"]["query_tasks"]:
        errors.append("provider_registry: default image provider must support reference images and task queries")
    semantic_id = provider_registry["default_semantic_provider_id"]
    if semantic_id is not None:
        semantic = providers.get(semantic_id)
        if semantic is None or semantic["role"] != "semantic":
            errors.append("provider_registry: default_semantic_provider_id must name a semantic provider")
    return errors


def validate_workspace_graph(
    workspace: Mapping[str, Any],
    documents: Mapping[str, list[Mapping[str, Any]]],
    archetypes: Mapping[str, Any],
    platform_profile: Mapping[str, Any],
    provider_registry: Mapping[str, Any],
) -> list[str]:
    """Validate version references and the persisted workflow graph.

    `documents` contains immutable per-workspace records grouped by schema kind;
    `workspace` is the mutable index file and the configs are app-level records.
    This function is read-only and never repairs or guesses broken references.
    """
    errors = validate_config_bundle(archetypes, platform_profile, provider_registry)
    try:
        validate_record("workspace", workspace)
    except ContractError as exc:
        errors.append(str(exc))
    for kind, records in documents.items():
        if kind not in DOCUMENT_KINDS - {"workspace"}:
            errors.append(f"documents: unsupported record kind {kind!r}")
            continue
        for record in records:
            try:
                validate_record(kind, record)
            except ContractError as exc:
                errors.append(str(exc))
    if errors:
        return errors

    workspace_id = workspace["workspace_id"]
    records_by_ref: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    attempts: dict[str, Mapping[str, Any]] = {}
    candidates: dict[str, Mapping[str, Any]] = {}
    for kind, records in documents.items():
        for record in records:
            if record.get("workspace_id") != workspace_id:
                errors.append(f"{kind}: record {record.get('id', record.get('action_id'))!r} belongs to another workspace")
            if kind in VERSIONED_KINDS:
                ref_key = (kind, record[ID_FIELDS[kind]], record["version"])
                if ref_key in records_by_ref:
                    errors.append(f"{kind}: duplicate identity/version {ref_key[1:]} ")
                records_by_ref[ref_key] = record
            elif kind == "generation_attempt":
                action_id = record["action_id"]
                if action_id in attempts:
                    errors.append(f"generation_attempt: duplicate action_id {action_id!r}")
                attempts[action_id] = record
            elif kind == "candidate":
                digest = record["candidate_id"]
                if digest in candidates:
                    errors.append(f"candidate: duplicate file SHA-256 {digest}")
                candidates[digest] = record

    if errors:
        return errors

    def resolve(ref: Mapping[str, Any], expected_kind: str, label: str):
        if ref["kind"] != expected_kind:
            errors.append(f"{label}: expected ref kind {expected_kind}, got {ref['kind']}")
            return None
        target = records_by_ref.get((expected_kind, ref["id"], ref["version"]))
        if target is None:
            errors.append(f"{label}: dangling reference {expected_kind}:{ref['id']}@{ref['version']}")
        return target

    def asset_exists(digest: str, label: str) -> None:
        if digest not in asset_hashes:
            errors.append(f"{label}: source asset {digest} is not in workspace.json")

    asset_hashes: set[str] = set()
    asset_paths: set[str] = set()
    for asset in workspace["assets"]:
        digest = asset["sha256"]
        path = asset["relative_path"]
        if digest in asset_hashes:
            errors.append(f"workspace.assets: duplicate SHA-256 {digest}")
        if not _safe_relative_path(path):
            errors.append(f"workspace.assets: unsafe relative_path {path!r}")
        if path in asset_paths:
            errors.append(f"workspace.assets: duplicate relative_path {path!r}")
        asset_hashes.add(digest)
        asset_paths.add(path)

    for pointer, expected_kind in POINTER_KINDS.items():
        ref = workspace["current"][pointer]
        if ref is not None:
            resolve(ref, expected_kind, f"workspace.current.{pointer}")

    profile_ref = {
        "profile_id": platform_profile["profile_id"],
        "version": platform_profile["version"],
    }
    archetypes_by_id = {item["id"]: item for item in archetypes["archetypes"]}
    archetype_ids = set(archetypes_by_id)
    providers = {item["id"]: item for item in provider_registry["providers"]}
    plan_shots: dict[tuple[str, int], dict[tuple[str, int], bool]] = {}

    for record in documents.get("product_input", []):
        ref = record["platform"]
        if ref != profile_ref:
            errors.append(f"product_input {record['id']}: platform profile ref does not match loaded profile")
        for digest in record["reference_asset_sha256"]:
            asset_exists(digest, f"product_input {record['id']}")

    for record in documents.get("product_brief", []):
        resolve(record["source_input"], "product_input", f"product_brief {record['id']}.source_input")

    for record in documents.get("plan", []):
        brief = resolve(record["source_brief"], "product_brief", f"plan {record['id']}.source_brief")
        if record["platform"] != profile_ref:
            errors.append(f"plan {record['id']}: platform profile ref does not match loaded profile")
        shot_map: dict[tuple[str, int], bool] = {}
        shots_by_id: dict[str, Mapping[str, Any]] = {}
        orders: set[int] = set()
        for item in record["shots"]:
            shot_ref = item["shot"]
            shot = resolve(shot_ref, "shot_spec", f"plan {record['id']}.shots")
            key = (shot_ref["id"], shot_ref["version"])
            if key in shot_map:
                errors.append(f"plan {record['id']}: duplicate shot reference {key}")
            if item["order"] in orders:
                errors.append(f"plan {record['id']}: duplicate shot order {item['order']}")
            orders.add(item["order"])
            shot_map[key] = bool(shot and shot["required"])
            if shot is not None and (shot["plan"]["id"], shot["plan"]["version"]) != (record["id"], record["version"]):
                errors.append(f"plan {record['id']}: shot {shot['id']} points to a different plan version")
            if shot is not None:
                shots_by_id[shot["id"]] = shot
        present_archetypes = {item["archetype_id"] for item in shots_by_id.values()}
        missing_required = sorted(set(platform_profile["required_archetypes"]) - present_archetypes)
        if missing_required:
            errors.append(f"plan {record['id']}: required archetypes missing: {missing_required}")
        for shot in shots_by_id.values():
            should_be_required = shot["archetype_id"] in platform_profile["required_archetypes"]
            if shot["required"] != should_be_required:
                errors.append(f"plan {record['id']}: shot {shot['id']} required flag disagrees with platform profile")
            for dependency in shot["dependencies"]:
                if dependency == shot["id"] or dependency not in shots_by_id:
                    errors.append(f"shot_spec {shot['id']}: dependency {dependency!r} is not another shot in its plan")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit_shot(shot_id: str) -> None:
            if shot_id in visiting:
                errors.append(f"plan {record['id']}: shot dependencies contain a cycle at {shot_id}")
                return
            if shot_id in visited:
                return
            visiting.add(shot_id)
            shot = shots_by_id.get(shot_id)
            if shot is not None:
                for dependency in shot["dependencies"]:
                    if dependency in shots_by_id:
                        visit_shot(dependency)
            visiting.remove(shot_id)
            visited.add(shot_id)

        for shot_id in shots_by_id:
            visit_shot(shot_id)
        plan_shots[(record["id"], record["version"])] = shot_map

    for record in documents.get("shot_spec", []):
        plan = resolve(record["plan"], "plan", f"shot_spec {record['id']}.plan")
        if record["archetype_id"] not in archetype_ids:
            errors.append(f"shot_spec {record['id']}: unknown archetype {record['archetype_id']!r}")
        for digest in record["reference_asset_sha256"]:
            asset_exists(digest, f"shot_spec {record['id']}")
        brief = None
        if plan is not None:
            brief = records_by_ref.get(("product_brief", plan["source_brief"]["id"], plan["source_brief"]["version"]))
        product_input = None
        if brief is not None:
            product_input = records_by_ref.get(("product_input", brief["source_input"]["id"], brief["source_input"]["version"]))
        confirmed_fact_keys = {
            item["key"] for item in (brief or {}).get("facts", [])
            if item.get("state") == "confirmed" and item.get("source") in {"user_input", "user_override"}
        }
        for fact_key in record.get("supporting_fact_keys", []):
            if fact_key not in confirmed_fact_keys:
                errors.append(f"shot_spec {record['id']}: supporting fact {fact_key!r} is not confirmed user evidence")
        known_reference_hashes = set((product_input or {}).get("reference_asset_sha256", []))
        for digest in record["reference_asset_sha256"]:
            if digest not in known_reference_hashes:
                errors.append(f"shot_spec {record['id']}: reference image {digest} is not from its source product input")
        archetype = archetypes_by_id.get(record["archetype_id"], {})
        evidence_policy = archetype.get("evidence_policy")
        has_fact = bool(record.get("supporting_fact_keys"))
        has_reference = bool(record["reference_asset_sha256"])
        has_intent = bool((product_input or {}).get("user_intent"))
        if evidence_policy == "confirmed_fact" and not has_fact:
            errors.append(f"shot_spec {record['id']}: archetype requires a confirmed fact")
        elif evidence_policy == "reference_asset" and not has_reference:
            errors.append(f"shot_spec {record['id']}: archetype requires a reference image")
        elif evidence_policy == "user_intent_or_fact_or_reference" and not (has_intent or has_fact or has_reference):
            errors.append(f"shot_spec {record['id']}: archetype has no supported user intent, fact, or reference")

    for record in documents.get("prompt", []):
        resolve(record["shot"], "shot_spec", f"prompt {record['id']}.shot")
        resolve(record["plan"], "plan", f"prompt {record['id']}.plan")
        if record["shot"]["id"] and record["plan"]["id"]:
            plan_key = (record["plan"]["id"], record["plan"]["version"])
            shot_key = (record["shot"]["id"], record["shot"]["version"])
            if shot_key not in plan_shots.get(plan_key, {}):
                errors.append(f"prompt {record['id']}: shot is not in referenced plan")
        parent = record["parent"]
        if parent is not None:
            resolve(parent, "prompt", f"prompt {record['id']}.parent")

    for record in documents.get("generation_attempt", []):
        shot = resolve(record["shot"], "shot_spec", f"attempt {record['action_id']}.shot")
        prompt = resolve(record["prompt"], "prompt", f"attempt {record['action_id']}.prompt")
        provider = providers.get(record["provider_id"])
        if provider is None or provider["role"] != "image" or provider["model_id"] != record["model_id"]:
            errors.append(f"attempt {record['action_id']}: provider/model is not registered as an image provider")
        if shot is not None and prompt is not None:
            if prompt["shot"]["id"] != shot["id"] or prompt["shot"]["version"] != shot["version"]:
                errors.append(f"attempt {record['action_id']}: prompt belongs to a different shot")
        for digest in record["reference_asset_sha256"]:
            asset_exists(digest, f"attempt {record['action_id']}")

    for record in documents.get("candidate", []):
        attempt = attempts.get(record["attempt_action_id"])
        if attempt is None:
            errors.append(f"candidate {record['candidate_id']}: missing attempt {record['attempt_action_id']!r}")
            continue
        if (record["shot"]["id"], record["shot"]["version"]) != (attempt["shot"]["id"], attempt["shot"]["version"]):
            errors.append(f"candidate {record['candidate_id']}: attempt belongs to a different shot")
        if (record["prompt"]["id"], record["prompt"]["version"]) != (attempt["prompt"]["id"], attempt["prompt"]["version"]):
            errors.append(f"candidate {record['candidate_id']}: attempt used a different prompt version")
        if not _safe_relative_path(record["relative_path"]):
            errors.append(f"candidate {record['candidate_id']}: unsafe relative_path")

    for record in documents.get("selection", []):
        plan = resolve(record["plan"], "plan", f"selection {record['id']}.plan")
        choices_by_shot: dict[tuple[str, int], str] = {}
        for choice in record["choices"]:
            shot_key = (choice["shot"]["id"], choice["shot"]["version"])
            digest = choice["candidate_sha256"]
            if plan is not None and shot_key not in plan_shots.get((plan["id"], plan["version"]), {}):
                errors.append(f"selection {record['id']}: shot {shot_key} is not in its plan")
            if shot_key in choices_by_shot:
                errors.append(f"selection {record['id']}: more than one chosen candidate for shot {shot_key}")
            choices_by_shot[shot_key] = digest
            candidate = candidates.get(digest)
            if candidate is None:
                errors.append(f"selection {record['id']}: missing candidate {digest}")
            elif (candidate["shot"]["id"], candidate["shot"]["version"]) != shot_key:
                errors.append(f"selection {record['id']}: candidate {digest} belongs to another shot")
    for record in documents.get("export", []):
        selection = resolve(record["selection"], "selection", f"export {record['id']}.selection")
        exported: set[str] = set()
        for item in record["files"]:
            digest = item["candidate_sha256"]
            if digest in exported:
                errors.append(f"export {record['id']}: candidate exported more than once: {digest}")
            exported.add(digest)
            candidate = candidates.get(digest)
            if candidate is None:
                errors.append(f"export {record['id']}: missing source candidate {digest}")
            elif (item["shot"]["id"], item["shot"]["version"]) != (candidate["shot"]["id"], candidate["shot"]["version"]):
                errors.append(f"export {record['id']}: file shot does not match candidate {digest}")
            if not _safe_relative_path(item["relative_path"]):
                errors.append(f"export {record['id']}: unsafe file path {item['relative_path']!r}")
        if selection is not None:
            chosen = {choice["candidate_sha256"] for choice in selection["choices"]}
            if exported != chosen:
                errors.append(f"export {record['id']}: exported candidates do not match its selection version")
            plan = resolve(selection["plan"], "plan", f"export {record['id']}.selection.plan")
            if plan is not None:
                required = plan_shots.get((plan["id"], plan["version"]), {})
                selected_shots = {
                    (choice["shot"]["id"], choice["shot"]["version"])
                    for choice in selection["choices"]
                }
                missing = sorted(key for key, is_required in required.items() if is_required and key not in selected_shots)
                if missing:
                    errors.append(f"export {record['id']}: required shots not selected: {missing}")
        if not _safe_relative_path(record["relative_path"]) or not _safe_relative_path(record["manifest_relative_path"]):
            errors.append(f"export {record['id']}: unsafe export path")

    return errors


def _safe_relative_path(value: str) -> bool:
    if not value or "\\" in value or ":" in value or value.startswith("/"):
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts)
