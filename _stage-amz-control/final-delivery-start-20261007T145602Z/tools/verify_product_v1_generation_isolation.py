#!/usr/bin/env python
"""Integration checks: one blocked shot must not abort whole-set generation.

Real flow this protects (2026-09-28 real UI run): POST /api/generation/start
compiled every missing shot prompt before submitting anything, and one shot
whose prompt failed to compile (model wording guard, upstream rejection)
turned the whole request into a 502 - every other shot lost its turn too.

Proves, without network access:

- one shot whose prompt cannot be compiled is skipped and reported in
  data["skipped_shots"], while the remaining shots still compile, submit and
  materialize candidates;
- the blocked shot recovers through the existing per-shot entry point
  (start_shot_generation compiles its missing prompt, then submits exactly one
  task, without resubmitting its neighbours);
- early validation failures (missing etag, stale revision, unknown shot)
  answer with their designed envelopes instead of an AttributeError crash.

Run with:
  <python> tools/verify_product_v1_generation_isolation.py
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
from src.providers.semantic import SemanticProviderError
from tools.verify_product_v1_image_generation import (
    Submission,
    reference_png,
    require_ok,
    semantic_responses,
)
from tools.verify_product_v1_ui_rework import RegistryCompatibleFakeImageProvider

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: object = None) -> None:
    if condition:
        PASSED.append(label)
        print(f"ok   {label}")
    else:
        FAILED.append(label)
        print(f"FAIL {label}: {detail!r}")


class FailingPromptSemanticProvider(FakeSemanticProvider):
    """Rejects propose_prompt_blocks for explicitly listed shot titles only.

    The compiler sends the model a safe_shot projection without the record id,
    so the fixture must key on a field the compiler actually forwards.
    """

    def __init__(self, responses) -> None:
        super().__init__(responses)
        self.fail_titles: set[str] = set()

    def propose_prompt_blocks(self, product_brief, shot_spec, style_spec):
        if shot_spec.get("title") in self.fail_titles:
            raise SemanticProviderError(
                "PROMPT_BLOCKS_REJECTED",
                "fixture rejects this shot's prompt blocks",
                recoverable=True,
            )
        return super().propose_prompt_blocks(product_brief, shot_spec, style_spec)


def build_plan(service: ApplicationService, workspace: Path, reference: bytes) -> dict:
    created = require_ok(service.create_workspace(workspace), "create workspace")
    intake = require_ok(service.save_intake(
        workspace, expected_etag=created["workspace"]["revision"],
        product_name="Fixture Product",
        description="A reusable fixture product for isolation checks.",
        selling_points=["keep warm"],
        user_intent="Everyday commute.",
        reference_images=[ImageUpload("reference.png", reference, "primary")],
    ), "save product intake")
    draft = require_ok(service.generate_product_brief_draft(
        workspace, expected_etag=intake["workspace"]["revision"],
    ), "draft product brief")
    brief = require_ok(service.save_product_brief(
        workspace, expected_etag=draft["workspace_revision"], fields=draft["product_brief"],
    ), "save product brief")
    return require_ok(service.generate_product_plan(
        workspace, expected_etag=brief["workspace"]["revision"],
    ), "generate product plan")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="amz-product-v1-generation-isolation-") as temp:
        workspace = Path(temp) / "workspace"
        # The workspace graph validator requires every attempt's provider/model
        # to match config/product-v1/providers.json; the fake therefore carries
        # the shipped registry identity, exactly like the UI rework fixture.
        image_provider = RegistryCompatibleFakeImageProvider()
        reference = reference_png()
        semantic = FailingPromptSemanticProvider(semantic_responses())
        service = ApplicationService(
            semantic_provider_factory=lambda: semantic,
            image_provider_factory=lambda: image_provider,
        )
        plan = build_plan(service, workspace, reference)
        shots = plan["plan"]["shot_specs"]
        check("fixture has a multi-shot set", len(shots) >= 2, len(shots))
        target = shots[-1]
        ready_ids = [shot["id"] for shot in shots if shot["id"] != target["id"]]
        titles = [shot.get("title") for shot in shots]
        check("target title is unique", titles.count(target.get("title")) == 1, titles)
        semantic.fail_titles = {target.get("title")}
        image_provider.plan_submissions([
            Submission("SUCCEEDED", f"task-{index}")
            for index in range(1, len(ready_ids) + 1)
        ])

        revision = require_ok(
            service.get_workspace_projection(workspace), "load projection",
        )["workspace"]["revision"]
        response = service.start_generation_set(
            workspace, expected_etag=revision, idempotency_key="isolation-check-0001",
        )
        check(
            "one blocked shot no longer aborts the whole set",
            response.status_code == 202, response.body,
        )
        if response.ok:
            data = response.body["data"]
            skipped = data.get("skipped_shots") or []
            check(
                "the blocked shot is reported with its error code",
                [entry.get("shot_id") for entry in skipped] == [target["id"]]
                and (skipped[0].get("code") if skipped else None) == "PROMPT_BLOCKS_REJECTED",
                skipped,
            )
            by_shot = {shot["id"]: shot for shot in data["plan"]["shot_specs"]}
            check(
                "every ready shot submitted and materialized a candidate",
                all(len(by_shot[shot_id].get("candidates") or []) == 1 for shot_id in ready_ids)
                and len(image_provider.submit_calls) == len(ready_ids),
                image_provider.submit_calls,
            )
            check(
                "the blocked shot holds no candidate",
                not (by_shot[target["id"]].get("candidates") or []),
                by_shot[target["id"]].get("candidates"),
            )

        missing_etag = service.start_generation_set(
            workspace, expected_etag=None, idempotency_key="isolation-check-0002",
        )
        check(
            "missing etag answers 428 REVISION_REQUIRED",
            missing_etag.status_code == 428
            and (missing_etag.body.get("error") or {}).get("code") == "REVISION_REQUIRED",
            missing_etag.body,
        )
        stale = service.start_generation_set(
            workspace, expected_etag="etag-stale", idempotency_key="isolation-check-0003",
        )
        check(
            "stale revision answers 409 REVISION_CONFLICT",
            stale.status_code == 409
            and (stale.body.get("error") or {}).get("code") == "REVISION_CONFLICT",
            stale.body,
        )
        fresh = require_ok(
            service.get_workspace_projection(workspace), "reload projection",
        )["workspace"]["revision"]
        unknown = service.start_shot_generation(
            workspace, expected_etag=fresh, shot_id="shot-does-not-exist",
            idempotency_key="isolation-check-0004",
        )
        check(
            "unknown shot answers 404 SHOT_NOT_FOUND",
            unknown.status_code == 404
            and (unknown.body.get("error") or {}).get("code") == "SHOT_NOT_FOUND",
            unknown.body,
        )

        semantic.fail_titles = set()
        image_provider.plan_submissions([Submission("SUCCEEDED", "task-recovered")])
        before_submissions = len(image_provider.submit_calls)
        recovered = service.start_shot_generation(
            workspace, expected_etag=fresh, shot_id=target["id"],
            idempotency_key="isolation-check-0005",
        )
        check(
            "the blocked shot recovers through per-shot retry",
            recovered.status_code == 202, recovered.body,
        )
        if recovered.ok:
            recovered_data = recovered.body["data"]
            by_shot = {shot["id"]: shot for shot in recovered_data["plan"]["shot_specs"]}
            check(
                "recovered shot now has a prompt and one candidate",
                by_shot[target["id"]].get("latest_prompt") is not None
                and len(by_shot[target["id"]].get("candidates") or []) == 1,
                by_shot[target["id"]].get("candidates"),
            )
            check(
                "recovery submitted exactly one provider task",
                len(image_provider.submit_calls) == before_submissions + 1,
                len(image_provider.submit_calls),
            )
            check(
                "recovery did not resubmit the ready shots",
                all(
                    len(by_shot[shot_id].get("generation_attempts") or []) == 1
                    for shot_id in ready_ids
                ),
                {
                    shot_id: len(by_shot[shot_id].get("generation_attempts") or [])
                    for shot_id in ready_ids
                },
            )

    print(f"{len(PASSED)} passed; {len(FAILED)} failed")
    for label in FAILED:
        print(f"failed: {label}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
