#!/usr/bin/env python
"""Offline, deterministic acceptance checks for Product V1 contracts.

This verifier reads only the three shipped Product V1 configuration files. All
workspace records and negative cases are constructed in memory; it does not
read or write a user's workspace, contact a provider, or access the network.
Run from the repository root with the pinned jsonschema dependency available:

    python tools/verify_product_v1_contracts.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import product_v1_contracts as contracts  # noqa: E402


STAMP = "2026-09-28T00:00:00Z"
WORKSPACE_ID = "ws_00000001"
ASSET_SHA = "a" * 64
HERO_CANDIDATE_SHA = "b" * 64
CUSTOM_CANDIDATE_SHA = "c" * 64
REQUEST_SHA = "d" * 64


class VerificationFailure(AssertionError):
    pass


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []

    def run(self, name: str, check: Callable[[], None]) -> None:
        try:
            check()
        except Exception as exc:  # Report each case while preserving later coverage.
            self.failed.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        else:
            self.passed += 1
            print(f"PASS {name}")

    def finish(self) -> int:
        print(f"{self.passed} passed; {len(self.failed)} failed")
        return 1 if self.failed else 0


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def record_ref(kind: str, record_id: str, version: int = 1) -> dict[str, object]:
    return {"kind": kind, "id": record_id, "version": version}


def profile_ref(profile: dict) -> dict[str, object]:
    return {"profile_id": profile["profile_id"], "version": profile["version"]}


def seal(record: dict) -> dict:
    return contracts.seal_record(record)


def set_content_hash(record: dict) -> None:
    record["content_hash"] = contracts.canonical_content_hash(record)


def make_fixture(configs: tuple[dict, dict, dict] | None = None) -> dict:
    if configs is None:
        configs = (
            read_json(ROOT / "config/product-v1/archetypes.json"),
            read_json(ROOT / "config/product-v1/platforms/amazon-us.json"),
            read_json(ROOT / "config/product-v1/providers.json"),
        )
    archetypes, platform, providers = copy.deepcopy(configs)
    platform_pointer = profile_ref(platform)

    workspace_asset = {
        "sha256": ASSET_SHA,
        "relative_path": "inputs/originals/product-reference.png",
        "original_name": "product-reference.png",
        "media_type": "image/png",
        "byte_size": 256,
        "width": 640,
        "height": 640,
        "role": "primary",
        "source": "user_upload",
    }
    product_input = seal({
        "schema": "amz-listing-kit/product-input@1",
        "id": "input_00000001",
        "version": 1,
        "content_hash": "",
        "workspace_id": WORKSPACE_ID,
        "created_at": STAMP,
        "product_name": "Sample product",
        "description": None,
        "selling_points": [],
        "platform": platform_pointer,
        "reference_asset_sha256": [ASSET_SHA],
        "user_intent": None,
    })
    brief = seal({
        "schema": "amz-listing-kit/product-brief@1",
        "id": "brief_00000001",
        "version": 1,
        "content_hash": "",
        "workspace_id": WORKSPACE_ID,
        "created_at": STAMP,
        "source_input": record_ref("product_input", product_input["id"]),
        "category": {"label": None, "confidence": None, "source": "model_inference"},
        "facts": [],
        "must_preserve": ["product identity"],
        "may_change": ["scene and composition"],
        "unknowns": [],
    })

    plan_id = "plan_00000001"
    hero_shot = seal({
        "schema": "amz-listing-kit/shot-spec@1",
        "id": "shot_00000001",
        "version": 1,
        "content_hash": "",
        "workspace_id": WORKSPACE_ID,
        "plan": record_ref("plan", plan_id),
        "archetype_id": "hero",
        "title": "Primary product image",
        "purpose": "Show the sellable product clearly.",
        "reason": "Required by the Amazon US profile.",
        "required": True,
        "preserve": ["product identity and color"],
        "change": ["clean white background"],
        "reference_asset_sha256": [ASSET_SHA],
        "supporting_fact_keys": [],
        "dependencies": [],
    })
    custom_shot = seal({
        "schema": "amz-listing-kit/shot-spec@1",
        "id": "shot_00000002",
        "version": 1,
        "content_hash": "",
        "workspace_id": WORKSPACE_ID,
        "plan": record_ref("plan", plan_id),
        "archetype_id": "custom",
        "title": "Product-specific usage moment",
        "purpose": "Explain a task not represented by the registered archetypes.",
        "reason": "This intent is specific to the current product brief.",
        "required": False,
        "preserve": ["product identity and proportions"],
        "change": ["show the user-provided use context"],
        "reference_asset_sha256": [ASSET_SHA],
        "supporting_fact_keys": [],
        "dependencies": [],
    })
    plan = seal({
        "schema": "amz-listing-kit/plan@1",
        "id": plan_id,
        "version": 1,
        "content_hash": "",
        "workspace_id": WORKSPACE_ID,
        "created_at": STAMP,
        "source_brief": record_ref("product_brief", brief["id"]),
        "platform": platform_pointer,
        "style_lock": {
            "direction": "cohesive product photography",
            "palette": ["neutral"],
            "lighting": "soft studio light",
            "background": "clean studio background",
            "continuity_notes": ["keep visual language consistent across shots"],
        },
        "shots": [
            {"shot": record_ref("shot_spec", hero_shot["id"]), "order": 1},
            {"shot": record_ref("shot_spec", custom_shot["id"]), "order": 2},
        ],
    })

    def make_prompt(prompt_id: str, shot: dict, text: str) -> dict:
        return seal({
            "schema": "amz-listing-kit/prompt@1",
            "id": prompt_id,
            "version": 1,
            "content_hash": "",
            "workspace_id": WORKSPACE_ID,
            "created_at": STAMP,
            "shot": record_ref("shot_spec", shot["id"]),
            "plan": record_ref("plan", plan["id"]),
            "blocks": [{
                "id": "product-fidelity",
                "kind": "product_fidelity",
                "text": "Preserve the visible identity of the reference product.",
                "source_refs": ["product_brief.must_preserve"],
            }],
            "full_text": text,
            "full_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "edit_mode": "compiled",
            "parent": None,
            "diff_summary": None,
        })

    hero_prompt = make_prompt("prompt_00000001", hero_shot, "Show the same product on white.")
    custom_prompt = make_prompt("prompt_00000002", custom_shot, "Show the product in the stated use context.")
    image_provider = next(
        item for item in providers["providers"] if item["id"] == providers["default_image_provider_id"]
    )

    def make_attempt(action_id: str, shot: dict, prompt: dict, task_id: str) -> dict:
        return {
            "schema": "amz-listing-kit/generation-attempt@1",
            "action_id": action_id,
            "idempotency_key": "idem_" + action_id,
            "workspace_id": WORKSPACE_ID,
            "created_at": STAMP,
            "updated_at": STAMP,
            "shot": record_ref("shot_spec", shot["id"]),
            "prompt": record_ref("prompt", prompt["id"]),
            "provider_id": image_provider["id"],
            "model_id": image_provider["model_id"],
            "request_sha256": REQUEST_SHA,
            "reference_asset_sha256": [ASSET_SHA],
            "status": "SUCCEEDED",
            "provider_task_id": task_id,
            "error": None,
        }

    hero_attempt = make_attempt("act_00000001", hero_shot, hero_prompt, "provider-task-hero")
    custom_attempt = make_attempt("act_00000002", custom_shot, custom_prompt, "provider-task-custom")

    def make_candidate(candidate_sha: str, shot: dict, prompt: dict, attempt: dict, filename: str) -> dict:
        return {
            "schema": "amz-listing-kit/candidate@1",
            "candidate_id": candidate_sha,
            "workspace_id": WORKSPACE_ID,
            "shot": record_ref("shot_spec", shot["id"]),
            "attempt_action_id": attempt["action_id"],
            "prompt": record_ref("prompt", prompt["id"]),
            "relative_path": f"shots/{shot['id']}/candidates/{filename}.png",
            "file_sha256": candidate_sha,
            "media_type": "image/png",
            "width": 1024,
            "height": 1024,
            "created_at": STAMP,
        }

    hero_candidate = make_candidate(HERO_CANDIDATE_SHA, hero_shot, hero_prompt, hero_attempt, "candidate-hero")
    custom_candidate = make_candidate(CUSTOM_CANDIDATE_SHA, custom_shot, custom_prompt, custom_attempt, "candidate-custom")
    selection = seal({
        "schema": "amz-listing-kit/selection@1",
        "id": "selection_00000001",
        "version": 1,
        "content_hash": "",
        "workspace_id": WORKSPACE_ID,
        "created_at": STAMP,
        "plan": record_ref("plan", plan["id"]),
        "choices": [{
            "shot": record_ref("shot_spec", hero_shot["id"]),
            "candidate_sha256": HERO_CANDIDATE_SHA,
            "selected_at": STAMP,
        }],
    })
    export = seal({
        "schema": "amz-listing-kit/export@1",
        "id": "export_00000001",
        "version": 1,
        "content_hash": "",
        "workspace_id": WORKSPACE_ID,
        "created_at": STAMP,
        "selection": record_ref("selection", selection["id"]),
        "relative_path": "exports/export_00000001",
        "manifest_relative_path": "exports/export_00000001/manifest.json",
        "files": [{
            "shot": record_ref("shot_spec", hero_shot["id"]),
            "candidate_sha256": HERO_CANDIDATE_SHA,
            "relative_path": "exports/export_00000001/images/001.png",
            "file_sha256": HERO_CANDIDATE_SHA,
        }],
        "checks": [],
    })
    workspace = {
        "schema": "amz-listing-kit/workspace@1",
        "workspace_id": WORKSPACE_ID,
        "created_at": STAMP,
        "updated_at": STAMP,
        "app_version": "contract-verifier-fixture",
        "status": "EXPORTED",
        "assets": [workspace_asset],
        "current": {
            "product_input": record_ref("product_input", product_input["id"]),
            "product_brief": record_ref("product_brief", brief["id"]),
            "plan": record_ref("plan", plan["id"]),
            "selection": record_ref("selection", selection["id"]),
            "export": record_ref("export", export["id"]),
        },
    }
    documents = {
        "product_input": [product_input],
        "product_brief": [brief],
        "plan": [plan],
        "shot_spec": [hero_shot, custom_shot],
        "prompt": [hero_prompt, custom_prompt],
        "generation_attempt": [hero_attempt, custom_attempt],
        "candidate": [hero_candidate, custom_candidate],
        "selection": [selection],
        "export": [export],
    }
    return {
        "configs": (archetypes, platform, providers),
        "workspace": workspace,
        "documents": documents,
        "ids": {
            "hero_shot": hero_shot["id"],
            "custom_shot": custom_shot["id"],
            "hero_candidate": HERO_CANDIDATE_SHA,
            "custom_candidate": CUSTOM_CANDIDATE_SHA,
        },
    }


def expect_record_rejected(kind: str, record: dict, expected: tuple[str, ...]) -> None:
    try:
        contracts.validate_record(kind, record)
    except contracts.ContractError as exc:
        message = str(exc)
    else:
        raise VerificationFailure(f"{kind} record was unexpectedly accepted")
    if not all(fragment in message for fragment in expected):
        raise VerificationFailure(f"expected {expected!r} in {message!r}")


def expect_bundle_rejected(configs: tuple[dict, dict, dict], expected: tuple[str, ...]) -> None:
    errors = contracts.validate_config_bundle(*configs)
    if not errors:
        raise VerificationFailure("invalid configuration bundle was unexpectedly accepted")
    message = chr(10).join(errors)
    if not all(fragment in message for fragment in expected):
        raise VerificationFailure(f"expected {expected!r} in {message!r}")


def expect_graph_rejected(fixture: dict, expected: tuple[str, ...]) -> None:
    errors = contracts.validate_workspace_graph(
        fixture["workspace"], fixture["documents"], *fixture["configs"],
    )
    if not errors:
        raise VerificationFailure("invalid workspace graph was unexpectedly accepted")
    message = chr(10).join(errors)
    if not all(fragment in message for fragment in expected):
        raise VerificationFailure(f"expected {expected!r} in {message!r}")


def main() -> int:
    checks = Checks()
    base = make_fixture()
    archetypes, platform, providers = base["configs"]

    checks.run("schema meta-check", lambda: contracts._validator())
    checks.run(
        "shipped configuration bundle",
        lambda: _expect_no_errors(contracts.validate_config_bundle(archetypes, platform, providers), "config bundle"),
    )
    checks.run(
        "complete graph with partial review selection and custom ShotSpec",
        lambda: _expect_no_errors(contracts.validate_workspace_graph(
            base["workspace"], base["documents"], archetypes, platform, providers,
        ), "workspace graph"),
    )

    bad_custom_purpose = copy.deepcopy(base["documents"]["shot_spec"][1])
    bad_custom_purpose.pop("purpose")
    set_content_hash(bad_custom_purpose)
    checks.run(
        "custom ShotSpec requires a task purpose with a localized path",
        lambda: expect_record_rejected("shot_spec", bad_custom_purpose, ("shot_spec.purpose", "required property")),
    )
    unknown_archetype = copy.deepcopy(base)
    shot = unknown_archetype["documents"]["shot_spec"][1]
    shot["archetype_id"] = "unregistered-category-template"
    set_content_hash(shot)
    checks.run(
        "unknown archetype id rejected",
        lambda: expect_graph_rejected(unknown_archetype, ("unknown archetype", "unregistered-category-template")),
    )

    unknown_field = copy.deepcopy(base["documents"]["product_brief"][0])
    unknown_field["unrecognized"] = True
    set_content_hash(unknown_field)
    checks.run(
        "unknown field rejected and named",
        lambda: expect_record_rejected("product_brief", unknown_field, ("product_brief.unrecognized", "unexpected")),
    )
    wrong_version = copy.deepcopy(base["documents"]["shot_spec"][0])
    wrong_version["version"] = 0
    set_content_hash(wrong_version)
    checks.run(
        "invalid record version rejected",
        lambda: expect_record_rejected("shot_spec", wrong_version, ("shot_spec.version", "minimum")),
    )
    wrong_schema = copy.deepcopy(base["documents"]["shot_spec"][0])
    wrong_schema["schema"] = "amz-listing-kit/shot-spec@9"
    set_content_hash(wrong_schema)
    checks.run(
        "invalid record schema version rejected",
        lambda: expect_record_rejected("shot_spec", wrong_schema, ("shot_spec.schema", "was expected")),
    )
    invalid_enum = copy.deepcopy(base["workspace"])
    invalid_enum["status"] = "UNKNOWN_STATUS"
    checks.run(
        "invalid enum rejected with a field path",
        lambda: expect_record_rejected("workspace", invalid_enum, ("workspace.status", "is not one of")),
    )
    malformed_hash = copy.deepcopy(base["documents"]["product_input"][0])
    malformed_hash["content_hash"] = "not-a-sha256"
    checks.run(
        "malformed content hash rejected by shape",
        lambda: expect_record_rejected("product_input", malformed_hash, ("product_input.content_hash", "does not match")),
    )
    bad_hash = copy.deepcopy(base["documents"]["product_input"][0])
    bad_hash["content_hash"] = "f" * 64
    checks.run(
        "record content hash mismatch rejected",
        lambda: expect_record_rejected("product_input", bad_hash, ("product_input.content_hash", "expected")),
    )
    bad_prompt_hash = copy.deepcopy(base["documents"]["prompt"][0])
    bad_prompt_hash["full_text_sha256"] = "e" * 64
    set_content_hash(bad_prompt_hash)
    checks.run(
        "prompt text hash mismatch rejected",
        lambda: expect_record_rejected("prompt", bad_prompt_hash, ("prompt.full_text_sha256", "does not match")),
    )
    bad_candidate_identity = copy.deepcopy(base["documents"]["candidate"][0])
    bad_candidate_identity["candidate_id"] = "f" * 64
    checks.run(
        "candidate identity must equal file hash",
        lambda: expect_record_rejected("candidate", bad_candidate_identity, ("candidate_id", "file SHA-256")),
    )

    duplicate_archetype = copy.deepcopy(base["configs"])
    duplicate_archetype[0]["archetypes"].append(copy.deepcopy(duplicate_archetype[0]["archetypes"][0]))
    checks.run(
        "duplicate archetype id rejected",
        lambda: expect_bundle_rejected(duplicate_archetype, ("duplicate archetype id",)),
    )
    missing_custom = copy.deepcopy(base["configs"])
    missing_custom[0]["archetypes"] = [item for item in missing_custom[0]["archetypes"] if item["id"] != "custom"]
    checks.run(
        "generic custom fallback must exist",
        lambda: expect_bundle_rejected(missing_custom, ("generic fallback 'custom' is missing",)),
    )
    missing_platform_archetype = copy.deepcopy(base["configs"])
    missing_platform_archetype[1]["required_archetypes"].append("not-registered")
    checks.run(
        "platform archetype reference must resolve",
        lambda: expect_bundle_rejected(missing_platform_archetype, ("required archetypes missing", "not-registered")),
    )
    wrong_image_role = copy.deepcopy(base["configs"])
    wrong_image_role[2]["providers"][0]["role"] = "semantic"
    checks.run(
        "default provider role must be image",
        lambda: expect_bundle_rejected(wrong_image_role, ("default_image_provider_id must name an image provider",)),
    )
    no_reference_support = copy.deepcopy(base["configs"])
    no_reference_support[2]["providers"][0]["capabilities"]["reference_images"] = False
    checks.run(
        "default image provider must support reference images and task queries",
        lambda: expect_bundle_rejected(no_reference_support, ("reference images and task queries",)),
    )
    missing_attempt_limit = copy.deepcopy(base["configs"])
    missing_attempt_limit[2]["providers"][0].pop("max_attempts")
    checks.run(
        "provider max_attempts required with a field path",
        lambda: expect_bundle_rejected(missing_attempt_limit, ("provider_registry.providers/0/max_attempts", "required property")),
    )
    invalid_attempt_limit = copy.deepcopy(base["configs"])
    invalid_attempt_limit[2]["providers"][0]["max_attempts"] = 9
    checks.run(
        "provider max_attempts range enforced with a field path",
        lambda: expect_bundle_rejected(invalid_attempt_limit, ("provider_registry.providers/0/max_attempts", "maximum")),
    )

    cross_workspace = copy.deepcopy(base)
    item = cross_workspace["documents"]["product_input"][0]
    item["workspace_id"] = "ws_87654321"
    set_content_hash(item)
    checks.run(
        "cross-workspace record rejected",
        lambda: expect_graph_rejected(cross_workspace, ("belongs to another workspace",)),
    )
    dangling_ref = copy.deepcopy(base)
    dangling_ref["workspace"]["current"]["product_brief"]["version"] = 2
    checks.run(
        "dangling version reference rejected",
        lambda: expect_graph_rejected(dangling_ref, ("dangling reference product_brief", "@2")),
    )
    mismatched_attempt = copy.deepcopy(base)
    mismatched_attempt["documents"]["generation_attempt"][0]["shot"] = record_ref(
        "shot_spec", base["ids"]["custom_shot"],
    )
    checks.run(
        "attempt cannot pair another shot and prompt",
        lambda: expect_graph_rejected(mismatched_attempt, ("prompt belongs to a different shot",)),
    )
    duplicate_selection = copy.deepcopy(base)
    selection = duplicate_selection["documents"]["selection"][0]
    selection["choices"].append(copy.deepcopy(selection["choices"][0]))
    set_content_hash(selection)
    checks.run(
        "selection permits at most one candidate per shot",
        lambda: expect_graph_rejected(duplicate_selection, ("more than one chosen candidate",)),
    )
    export_mismatch = copy.deepcopy(base)
    export_record = export_mismatch["documents"]["export"][0]
    export_record["files"][0]["candidate_sha256"] = base["ids"]["custom_candidate"]
    export_record["files"][0]["shot"] = record_ref("shot_spec", base["ids"]["custom_shot"])
    set_content_hash(export_record)
    checks.run(
        "export candidate set must match selection",
        lambda: expect_graph_rejected(export_mismatch, ("exported candidates do not match",)),
    )
    missing_required_choice = copy.deepcopy(base)
    selection = missing_required_choice["documents"]["selection"][0]
    selection["choices"] = [{
        "shot": record_ref("shot_spec", base["ids"]["custom_shot"]),
        "candidate_sha256": base["ids"]["custom_candidate"],
        "selected_at": STAMP,
    }]
    set_content_hash(selection)
    export_record = missing_required_choice["documents"]["export"][0]
    export_record["files"] = [{
        "shot": record_ref("shot_spec", base["ids"]["custom_shot"]),
        "candidate_sha256": base["ids"]["custom_candidate"],
        "relative_path": "exports/export_00000001/images/002.png",
        "file_sha256": CUSTOM_CANDIDATE_SHA,
    }]
    set_content_hash(export_record)
    checks.run(
        "export rejects a selection missing a required shot",
        lambda: expect_graph_rejected(missing_required_choice, ("required shots not selected",)),
    )
    unsafe_candidate_path = copy.deepcopy(base)
    unsafe_candidate_path["documents"]["candidate"][0]["relative_path"] = "shots/../candidates/escape.png"
    checks.run(
        "unsafe candidate path rejected",
        lambda: expect_graph_rejected(unsafe_candidate_path, ("unsafe relative_path",)),
    )
    absolute_candidate_path = copy.deepcopy(base["documents"]["candidate"][0])
    absolute_candidate_path["relative_path"] = "C:/workspace/shots/candidate.png"
    checks.run(
        "absolute artifact path rejected",
        lambda: expect_record_rejected("candidate", absolute_candidate_path, ("candidate.relative_path", "does not match")),
    )
    backslash_candidate_path = copy.deepcopy(base["documents"]["candidate"][0])
    backslash_candidate_path["relative_path"] = "shots" + chr(92) + "shot_00000001" + chr(92) + "candidates" + chr(92) + "candidate.png"
    checks.run(
        "backslash artifact path rejected",
        lambda: expect_record_rejected("candidate", backslash_candidate_path, ("candidate.relative_path", "does not match")),
    )
    unsafe_asset_path = copy.deepcopy(base)
    unsafe_asset_path["workspace"]["assets"][0]["relative_path"] = "inputs/originals/../escape.png"
    checks.run(
        "unsafe source asset path rejected",
        lambda: expect_graph_rejected(unsafe_asset_path, ("unsafe relative_path",)),
    )

    return checks.finish()


def _expect_no_errors(errors: list[str], label: str) -> None:
    if errors:
        raise VerificationFailure(f"{label} reported: {errors}")


if __name__ == "__main__":
    raise SystemExit(main())
