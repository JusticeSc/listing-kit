"""Structured draft contracts returned by the semantic model.

These are provider outputs, not persisted Product V1 records. The application
must compile and validate them before creating immutable workspace versions.
"""
from __future__ import annotations

from typing import Any, Mapping

from jsonschema import Draft202012Validator


def _strings() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string", "minLength": 1}}


_FACT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["key", "value", "state", "source", "confidence", "source_refs"],
    "properties": {
        "key": {"type": "string", "minLength": 1},
        "value": {"type": "string", "minLength": 1},
        "state": {"enum": ["confirmed", "inferred", "unknown", "conflicted"]},
        "source": {"enum": ["user_input", "reference_image", "model_inference", "user_override"]},
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "source_refs": _strings(),
    },
}

PRODUCT_BRIEF_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["category", "facts", "must_preserve", "may_change", "unknowns"],
    "properties": {
        "category": {
            "type": "object",
            "additionalProperties": False,
            "required": ["label", "confidence", "source"],
            "properties": {
                "label": {"type": ["string", "null"]},
                "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "source": {"enum": ["user_input", "reference_image", "model_inference", "user_override"]},
            },
        },
        "facts": {"type": "array", "items": _FACT},
        "must_preserve": _strings(),
        "may_change": _strings(),
        "unknowns": _strings(),
    },
}

PLAN_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["style_lock", "shots"],
    "properties": {
        "style_lock": {
            "type": "object",
            "additionalProperties": False,
            "required": ["direction", "palette", "lighting", "background", "continuity_notes"],
            "properties": {
                "direction": {"type": "string", "minLength": 1},
                "palette": _strings(),
                "lighting": {"type": ["string", "null"]},
                "background": {"type": ["string", "null"]},
                "continuity_notes": _strings(),
            },
        },
        "shots": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "archetype_id", "title", "purpose", "reason",
                    "preserve", "change", "reference_asset_sha256", "supporting_fact_keys",
                    "dependencies",
                ],
                "properties": {
                    "archetype_id": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "purpose": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 1},
                    "preserve": _strings(),
                    "change": _strings(),
                    "reference_asset_sha256": {
                        "type": "array", "uniqueItems": True,
                        "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                    "supporting_fact_keys": {
                        "type": "array", "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                    # The compiler maps these human-readable titles to stable Shot IDs.
                    "dependencies": _strings(),
                },
            },
        },
    },
}

PROMPT_BLOCKS_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["blocks"],
    "properties": {
        "blocks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "kind", "text", "source_refs"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                "kind": {"enum": ["style_lock", "shot_task", "negative"]},
                    "text": {"type": "string", "minLength": 1},
                    "source_refs": _strings(),
                },
            },
        },
    },
}

REWORK_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["keep", "change", "expected_result", "blocks"],
    "properties": {
        "keep": _strings(),
        "change": _strings(),
        "expected_result": {"type": "string", "minLength": 1},
        "blocks": PROMPT_BLOCKS_DRAFT_SCHEMA["properties"]["blocks"],
    },
}

DRAFT_SCHEMAS: dict[str, dict[str, Any]] = {
    "analyze_product": PRODUCT_BRIEF_DRAFT_SCHEMA,
    "propose_plan": PLAN_DRAFT_SCHEMA,
    "propose_prompt_blocks": PROMPT_BLOCKS_DRAFT_SCHEMA,
    "propose_rework": REWORK_DRAFT_SCHEMA,
}


class SemanticDraftValidationError(ValueError):
    """Model output was JSON but did not satisfy the selected draft contract."""


for _schema in DRAFT_SCHEMAS.values():
    Draft202012Validator.check_schema(_schema)

_VALIDATORS = {name: Draft202012Validator(schema) for name, schema in DRAFT_SCHEMAS.items()}


def validate_draft(operation: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate provider output locally; model-side JSON mode is not authority."""
    validator = _VALIDATORS.get(operation)
    if validator is None:
        raise SemanticDraftValidationError(f"unknown semantic operation: {operation}")
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "record"
        raise SemanticDraftValidationError(f"{operation}.{path}: {error.message}")
    return dict(value)
