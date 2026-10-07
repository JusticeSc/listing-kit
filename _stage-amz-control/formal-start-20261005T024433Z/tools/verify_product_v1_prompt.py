#!/usr/bin/env python
"""Verify prompt compilation, per-shot version history, edits, and stale-write guards."""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import product_v1_contracts as contracts
from src.application_service import ApplicationService
from src.providers.fake_semantic import FakeSemanticProvider
from src.semantic_drafts import PROMPT_BLOCKS_DRAFT_SCHEMA
from src.workspace_store import WorkspaceStore
from tools.verify_product_v1_plan import png_1x1, prepare_saved_brief, require_ok, responses


def prompt_blocks(*, include_confirmed_selling_point: bool) -> dict:
    shot_task = (
        "展示单手开盖的实际操作，清楚呈现用户确认的卖点。"
        if include_confirmed_selling_point
        else "清楚呈现商品本体外观，保持构图简洁。"
    )
    return {
        "blocks": [
            {
                "id": "style",
                "kind": "style_lock",
                "text": "延续清爽、可信的通勤商品摄影风格，采用柔和侧光与克制的暖白、深蓝配色。",
                "source_refs": ["plan.style_lock"],
            },
            {
                "id": "task",
                "kind": "shot_task",
                "text": shot_task,
                "source_refs": ["shot_spec.purpose"],
            },
            {
                "id": "negative",
                "kind": "negative",
                "text": "不要改变商品真实颜色、轮廓和结构；不要补充未经核实的材质、性能或认证。",
                "source_refs": ["shot_spec.preserve"],
            },
        ],
    }


def make_provider_fixture(*, prompt: dict | None = None) -> dict:
    result = responses()
    if prompt is not None:
        result["propose_prompt_blocks"] = prompt
    return result


def current_projection(service: ApplicationService, workspace: Path) -> dict:
    return require_ok(service.get_workspace_projection(workspace), "load workspace projection")


def shot_by_id(projection: dict, shot_id: str) -> dict:
    shots = projection["plan"]["shot_specs"]
    return next(shot for shot in shots if shot["id"] == shot_id)


def latest_prompt(shot: dict) -> dict:
    record = shot.get("latest_prompt")
    if not isinstance(record, dict):
        raise AssertionError(f"shot {shot.get('id')} is missing its latest_prompt record: {record!r}")
    versions = shot.get("prompt_versions")
    if not isinstance(versions, list) or not versions:
        raise AssertionError(f"shot {shot.get('id')} is missing prompt_versions: {versions!r}")
    return record


def assert_compiled_prompt(prompt: dict) -> None:
    assert prompt["edit_mode"] == "compiled", prompt
    assert prompt["version"] == 1, prompt
    assert prompt["parent"] is None, prompt
    assert prompt["full_text"] == "\n\n".join(block["text"] for block in prompt["blocks"])
    expected_hash = hashlib.sha256(prompt["full_text"].encode("utf-8")).hexdigest()
    assert prompt["full_text_sha256"] == expected_hash
    contracts.validate_record("prompt", prompt)


def version_map(shot: dict) -> dict[int, dict]:
    versions = shot.get("prompt_versions")
    assert isinstance(versions, list), f"prompt_versions must be a list: {versions!r}"
    result = {record["version"]: record for record in versions}
    assert len(result) == len(versions), f"duplicate prompt versions: {versions!r}"
    return result


def main() -> int:
    kinds = set(PROMPT_BLOCKS_DRAFT_SCHEMA["properties"]["blocks"]["items"]["properties"]["kind"]["enum"])
    assert kinds == {"style_lock", "shot_task", "negative"}, kinds

    # Each action gets its own explicit fake response. ProductBrief and Plan use
    # the shared plan-verifier fixtures; prompt proposals differ only so the
    # selling-point shot and the independent shot can be checked separately.
    fixture_queue = iter([
        make_provider_fixture(),
        make_provider_fixture(),
        make_provider_fixture(prompt=prompt_blocks(include_confirmed_selling_point=True)),
        make_provider_fixture(prompt=prompt_blocks(include_confirmed_selling_point=False)),
    ])
    service = ApplicationService(
        semantic_provider_factory=lambda: FakeSemanticProvider(next(fixture_queue)),
    )

    with tempfile.TemporaryDirectory(prefix="amz-product-v1-prompt-") as raw_root:
        workspace = Path(raw_root) / "workspace"
        brief_result = prepare_saved_brief(service, workspace, png_1x1())

        inferred_material = next(
            fact for fact in brief_result["product_brief"]["facts"] if fact["key"] == "材质"
        )
        assert inferred_material["source"] == "model_inference", inferred_material
        assert inferred_material["state"] == "inferred", inferred_material

        before_plan = current_projection(service, workspace)
        plan_result = service.generate_product_plan(
            workspace, expected_etag=before_plan["workspace"]["revision"],
        )
        plan_data = require_ok(plan_result, "generate plan")
        initial_shots = plan_data["plan"]["shot_specs"]
        feature_shot = next(
            shot for shot in initial_shots if "selling_point_1" in shot["supporting_fact_keys"]
        )
        second_shot = next(shot for shot in initial_shots if shot["id"] != feature_shot["id"])

        before_first = current_projection(service, workspace)
        first_result = service.generate_prompt(
            workspace,
            expected_etag=before_first["workspace"]["revision"],
            shot_id=feature_shot["id"],
        )
        first_data = require_ok(first_result, "generate first shot prompt")
        first_shot = shot_by_id(first_data, feature_shot["id"])
        first_v1 = copy.deepcopy(latest_prompt(first_shot))
        assert_compiled_prompt(first_v1)
        first_positive_text = "\n".join(
            block["text"] for block in first_v1["blocks"] if block["kind"] != "negative"
        )
        assert "单手开盖" in first_positive_text, first_positive_text
        assert "316 不锈钢" not in first_positive_text, first_positive_text
        assert "316 不锈钢" not in first_v1["full_text"], first_v1["full_text"]

        before_second = current_projection(service, workspace)
        second_result = service.generate_prompt(
            workspace,
            expected_etag=before_second["workspace"]["revision"],
            shot_id=second_shot["id"],
        )
        second_data = require_ok(second_result, "generate second shot prompt")
        first_after_second = shot_by_id(second_data, feature_shot["id"])
        second_after_second = shot_by_id(second_data, second_shot["id"])
        assert latest_prompt(first_after_second) == first_v1
        second_v1 = copy.deepcopy(latest_prompt(second_after_second))
        assert_compiled_prompt(second_v1)
        assert "316 不锈钢" not in second_v1["full_text"]
        second_v1_snapshot = copy.deepcopy(second_v1)

        third_shot = next(
            shot for shot in second_data["plan"]["shot_specs"]
            if shot["id"] not in {feature_shot["id"], second_shot["id"]}
        )
        before_failure = current_projection(service, workspace)
        third_before = shot_by_id(before_failure, third_shot["id"])
        assert third_before.get("latest_prompt") is None
        assert third_before.get("prompt_versions") == []
        prompt_count_before_failure = len(WorkspaceStore.open(workspace).list_records("prompt"))
        invalid_fixture = make_provider_fixture(
            prompt=prompt_blocks(include_confirmed_selling_point=False),
        )
        invalid_fixture["propose_prompt_blocks"]["unexpected"] = "invalid model output"
        failing_service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(invalid_fixture),
        )
        failure_result = failing_service.generate_prompt(
            workspace,
            expected_etag=before_failure["workspace"]["revision"],
            shot_id=third_shot["id"],
        )
        assert failure_result.status_code == 502, failure_result.body
        assert failure_result.body["error"]["code"] == "PROMPT_DRAFT_INVALID", failure_result.body
        after_failure = current_projection(service, workspace)
        assert after_failure["workspace"]["revision"] == before_failure["workspace"]["revision"]
        assert len(WorkspaceStore.open(workspace).list_records("prompt")) == prompt_count_before_failure
        assert latest_prompt(shot_by_id(after_failure, feature_shot["id"])) == first_v1
        assert latest_prompt(shot_by_id(after_failure, second_shot["id"])) == second_v1_snapshot
        third_after_failure = shot_by_id(after_failure, third_shot["id"])
        assert third_after_failure.get("latest_prompt") is None
        assert third_after_failure.get("prompt_versions") == []

        # A one-phrase change makes the lineage and actual textual diff testable.
        old_phrase = "展示单手开盖的实际操作"
        new_phrase = "突出顺滑自然的单手开盖体验"
        edited_text = first_v1["full_text"].replace(old_phrase, new_phrase, 1)
        assert edited_text != first_v1["full_text"], "fixture phrase was not present in the generated prompt"

        before_edit = current_projection(service, workspace)
        edit_result = service.save_prompt_edit(
            workspace,
            expected_etag=before_edit["workspace"]["revision"],
            shot_id=feature_shot["id"],
            expected_prompt_version=first_v1["version"],
            full_text=edited_text,
        )
        edit_data = require_ok(edit_result, "save prompt edit")
        edited_shot = shot_by_id(edit_data, feature_shot["id"])
        first_v2 = latest_prompt(edited_shot)
        versions = version_map(edited_shot)
        assert set(versions) == {1, 2}, versions
        assert first_v2 == versions[2]
        assert versions[1] == first_v1, "manual edit mutated the compiled prompt version"
        assert first_v2["version"] == 2
        assert first_v2["edit_mode"] == "manual"
        assert first_v2["full_text"] == edited_text
        assert first_v2["parent"] == {
            "kind": "prompt", "id": first_v1["id"], "version": first_v1["version"],
        }
        changed_regions = sum(
            1 for tag, _i1, _i2, _j1, _j2 in difflib.SequenceMatcher(
                None, first_v1["full_text"], edited_text,
            ).get_opcodes() if tag != "equal"
        )
        expected_diff_summary = (
            f"用户编辑提示词：{changed_regions} 处文本变化"
            f"（{len(first_v1['full_text'])} → {len(edited_text)} 字）。"
        )
        assert first_v2["diff_summary"] == expected_diff_summary, first_v2["diff_summary"]
        assert first_v2["full_text_sha256"] == hashlib.sha256(edited_text.encode("utf-8")).hexdigest()
        contracts.validate_record("prompt", first_v2)

        second_after_edit = shot_by_id(edit_data, second_shot["id"])
        second_v1_after_edit = latest_prompt(second_after_edit)
        assert second_v1_after_edit == second_v1_snapshot
        assert second_v1_after_edit["version"] == second_v1_snapshot["version"]
        assert second_v1_after_edit["content_hash"] == second_v1_snapshot["content_hash"]
        assert second_v1_after_edit["full_text_sha256"] == second_v1_snapshot["full_text_sha256"]

        current_revision = edit_data["workspace"]["revision"]
        stale_result = service.save_prompt_edit(
            workspace,
            expected_etag=current_revision,
            shot_id=feature_shot["id"],
            expected_prompt_version=first_v1["version"],
            full_text=first_v1["full_text"],
        )
        assert stale_result.status_code == 409, stale_result.body
        assert stale_result.ok is False, stale_result.body

        after_stale = current_projection(service, workspace)
        stale_versions = version_map(shot_by_id(after_stale, feature_shot["id"]))
        assert set(stale_versions) == {1, 2}, stale_versions
        assert stale_versions[2] == first_v2
        assert after_stale["workspace"]["revision"] == current_revision
        assert latest_prompt(shot_by_id(after_stale, second_shot["id"])) == second_v1_snapshot

        # A new service instance proves prompt history is projected from durable
        # workspace records rather than held only in the generating process.
        reopened = ApplicationService()
        reopened_data = current_projection(reopened, workspace)
        reopened_first = shot_by_id(reopened_data, feature_shot["id"])
        reopened_second = shot_by_id(reopened_data, second_shot["id"])
        assert version_map(reopened_first)[2] == first_v2
        assert latest_prompt(reopened_second) == second_v1_snapshot

        stored = WorkspaceStore.open(workspace)
        assert len(stored.list_records("prompt")) == 3

    print(json.dumps({
        "prompt_block_kinds_are_scoped": sorted(kinds),
        "confirmed_selling_point_in_prompt": True,
        "inferred_material_excluded_from_positive_prompt": True,
        "compiled_text_and_hash_valid": True,
        "two_shots_have_independent_prompt_versions": True,
        "manual_v2_parent_diff_hash_valid": True,
        "invalid_model_output_fails_without_mutation": True,
        "stale_prompt_version_rejected_without_write": True,
        "history_survives_service_reopen": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
