#!/usr/bin/env python
"""Verify the reference-photo conflict guard around plan and prompt compilation.

The ProductBrief can carry facts the analysis could not confirm against the
reference photo (state=conflicted). Those words must never be compiled into an
image instruction as if the product really had them: the plan must warn, and
the compiled prompt must state the reference photo decides and close with an
explicit do-not-add override.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application_service import ApplicationService, ImageUpload
from src.providers.fake_semantic import FakeSemanticProvider
from tools.verify_product_v1_plan import png_1x1, prepare_saved_brief, require_ok, responses
from tools.verify_product_v1_prompt import prompt_blocks

CONFLICTED_FACT = {
    "key": "领型",
    "value": "V领",
    "state": "conflicted",
    "source": "model_inference",
    "confidence": 0.5,
    "source_refs": ["semantic:fixture:request:conflict-guard"],
}


def fixture(*, with_conflict: bool) -> dict:
    result = responses()
    if with_conflict:
        result["analyze_product"]["facts"].append(dict(CONFLICTED_FACT))
        shot = result["propose_plan"]["shots"][0]
        shot["title"] = "细节图：V领工艺"
        shot["purpose"] = "用微距镜头表现 V领 与门襟的工艺细节。"
    result["propose_prompt_blocks"] = prompt_blocks(include_confirmed_selling_point=True)
    return result


def blocks_by_id(prompt: dict) -> dict[str, dict]:
    return {block["id"]: block for block in prompt["blocks"]}


def run(*, with_conflict: bool) -> tuple[list[dict], dict]:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(fixture(with_conflict=with_conflict)),
        )
        prepare_saved_brief(service, workspace, png_1x1())
        projection = require_ok(
            service.get_workspace_projection(workspace), "load workspace",
        )
        planned = require_ok(
            service.generate_product_plan(
                workspace, expected_etag=projection["workspace"]["revision"],
            ),
            "generate plan",
        )
        warnings = list(planned.get("compile_warnings") or [])
        shot = planned["plan"]["shot_specs"][0]
        compiled = require_ok(
            service.generate_prompt(
                workspace,
                expected_etag=planned["workspace"]["revision"],
                shot_id=shot["id"],
            ),
            "compile prompt",
        )
        prompt = next(
            item for item in compiled["plan"]["shot_specs"] if item["id"] == shot["id"]
        )["latest_prompt"]
        return warnings, prompt


def test_conflicted_wording_is_flagged_and_guarded() -> None:
    warnings, prompt = run(with_conflict=True)
    codes = [warning.get("code") for warning in warnings]
    assert "CONFLICTED_WORDING_IN_SHOT" in codes, warnings
    flagged = next(item for item in warnings if item["code"] == "CONFLICTED_WORDING_IN_SHOT")
    assert "V领" in flagged["message"], flagged

    blocks = blocks_by_id(prompt)
    fidelity = blocks["product-fidelity"]["text"]
    assert "NOT confirmed" in fidelity, fidelity
    assert "V领" in fidelity, fidelity
    negative = blocks["negative-constraints"]["text"]
    assert "not clearly visible in the reference" in negative, negative
    assert negative.rstrip().endswith("V领."), negative
    assert "V领" in prompt["full_text"]
    # The guard must be part of the hashed text, not decoration outside it.
    assert prompt["full_text"].count("not clearly visible in the reference") == 1


def test_clean_brief_has_no_guard() -> None:
    warnings, prompt = run(with_conflict=False)
    codes = [warning.get("code") for warning in warnings]
    assert "CONFLICTED_WORDING_IN_SHOT" not in codes, warnings
    blocks = blocks_by_id(prompt)
    assert "NOT confirmed" not in blocks["product-fidelity"]["text"]
    assert "not clearly visible in the reference" not in blocks["negative-constraints"]["text"]


USER_PRODUCT_NAME = "粗棒针织套头毛衣"
USER_DESCRIPTION = "宽松落肩的粗棒针织套头毛衣，适合春秋通勤内搭。"
INFERRED_FACTS = [
    {"key": "款式", "value": "套头毛衣", "state": "inferred", "source": "model_inference",
     "confidence": 0.7, "source_refs": ["description"]},
    {"key": "领型", "value": "罗纹领口", "state": "inferred", "source": "model_inference",
     "confidence": 0.6, "source_refs": ["description"]},
]


def build_blocks(task_text: str) -> dict:
    return {"blocks": [
        {"id": "style-1", "kind": "style_lock",
         "text": "Keep the studio backdrop and soft light of the current Style Lock.",
         "source_refs": ["plan.style_lock"]},
        {"id": "task-1", "kind": "shot_task", "text": task_text,
         "source_refs": ["shot_spec.title"]},
        {"id": "neg-1", "kind": "negative",
         "text": "Do not change the product's visible structure, colour, or texture.",
         "source_refs": ["shot_spec.preserve"]},
    ]}


def compile_user_wording_case(task_text: str):
    """Compile one prompt where inferred fact values overlap the user's own words."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        fixture_responses = responses()
        fact_list = fixture_responses["analyze_product"]["facts"]
        fact_list.extend(dict(fact) for fact in INFERRED_FACTS)
        fixture_responses["propose_prompt_blocks"] = build_blocks(task_text)
        service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(fixture_responses),
        )
        created = require_ok(service.create_workspace(workspace), "create workspace")
        intake = require_ok(service.save_intake(
            workspace, expected_etag=created["workspace"]["revision"],
            product_name=USER_PRODUCT_NAME, description=USER_DESCRIPTION,
            selling_points=["粗棒针织纹理，厚实保暖"], user_intent="适合春秋通勤内搭。",
            reference_images=[ImageUpload("reference.png", png_1x1(), "primary")],
        ), "save intake")
        draft = require_ok(service.generate_product_brief_draft(
            workspace, expected_etag=intake["workspace"]["revision"],
        ), "draft product brief")
        brief = require_ok(service.save_product_brief(
            workspace, expected_etag=draft["workspace_revision"], fields=draft["product_brief"],
        ), "save product brief")
        planned = require_ok(service.generate_product_plan(
            workspace, expected_etag=brief["workspace"]["revision"],
        ), "generate plan")
        shot = planned["plan"]["shot_specs"][0]
        compiled = service.generate_prompt(
            workspace, expected_etag=planned["workspace"]["revision"], shot_id=shot["id"],
        )
        if not compiled.ok:
            return False, (compiled.body.get("error") or {}).get("code")
        prompt = next(
            item for item in compiled.body["data"]["plan"]["shot_specs"]
            if item["id"] == shot["id"]
        )["latest_prompt"]
        return True, prompt


def test_user_authoritative_wording_is_allowed() -> None:
    ok, prompt = compile_user_wording_case(
        "Photograph the user's own product, the 粗棒针织套头毛衣, "
        "in the requested 春秋通勤 scene."
    )
    assert ok, prompt
    assert "套头毛衣" in prompt["full_text"], prompt["full_text"]


def test_unknown_inferred_wording_is_blocked() -> None:
    ok, error = compile_user_wording_case(
        "Photograph the product with a clearly visible 罗纹领口 in close-up."
    )
    assert not ok, error
    assert error == "PROMPT_COMPILE_INVALID", error


def main() -> int:
    tests = [
        ("conflicted wording is flagged and guarded", test_conflicted_wording_is_flagged_and_guarded),
        ("clean brief has no guard", test_clean_brief_has_no_guard),
        ("user-authored wording does not trip the inferred-fact guard", test_user_authoritative_wording_is_allowed),
        ("inferred wording absent from user text is still blocked", test_unknown_inferred_wording_is_blocked),
    ]
    failures = 0
    for name, test in tests:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
        else:
            print(f"ok   {name}")
    print(f"{len(tests) - failures} passed; {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
