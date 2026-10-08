#!/usr/bin/env python
"""Product V1 selection, single-shot rework, and export checks (fake providers, no network).

Every case runs against the real ApplicationService and WorkspaceStore with injected
providers, so the persisted SelectionVersion, rework isolation, and deliverable files
are the shipped code paths. The platform-checks module is stubbed in-process; its real
rules are verified separately by tools/verify_product_v1_platform_checks.py.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from app.product_v1_server import ProductApplication, create_product_server
from src.application_service import ApplicationService
from src.providers.fake_semantic import FakeSemanticProvider
from src.workspace_store import WorkspaceStore
from tools.verify_product_v1_image_generation import (
    FIRST_KEY,
    FakeImageProvider,
    GenerationFixture,
    Submission,
    require_ok,
    semantic_responses,
)


def stub_platform_checks(*, hard_failures: list = None):
    module = types.ModuleType("src.platform_checks")
    checks = [
        {
            "rule_id": "amazon-us.main_image.size", "rule_version": "1", "passed": True,
            "detail": "1600px 长边", "source_uri": "https://sellercentral.amazon.com/",
            "checked_at": "2026-09-28", "scope": "hard",
        }
    ]
    checks.extend(hard_failures or [])

    def run_export_checks(_workspace_dir):
        failures = [item for item in checks if item.get("scope") == "hard" and not item.get("passed")]
        return {
            "profile": {"profile_id": "amazon-us", "version": 1},
            "checks": checks,
            "hard_failures": failures,
            "manual_notes": [],
        }

    module.run_export_checks = run_export_checks
    return module


def use_stub_platform_checks(*, hard_failures: list = None):
    real_module = sys.modules.get("src.platform_checks")
    sys.modules["src.platform_checks"] = stub_platform_checks(hard_failures=hard_failures)
    return real_module


def restore_platform_checks(real_module):
    if real_module is None:
        sys.modules.pop("src.platform_checks", None)
    else:
        sys.modules["src.platform_checks"] = real_module

class RegisteredFakeImageProvider(FakeImageProvider):
    """Same deterministic fake, but advertised under the shipped registry ids.

    Workspace graph validation requires every attempt's provider/model pair to be a
    registered image provider; the real run uses the same ids.
    """

    provider_id = "dashscope-qwen-image"
    model_id = "qwen-image-3.0"


class SelectionChecks(GenerationFixture):
    def setUp(self):
        super().setUp()
        self.image_provider = RegisteredFakeImageProvider()
        self.service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(semantic_responses()),
            image_provider_factory=lambda: self.image_provider,
        )

    def complete_set(self, key: str = FIRST_KEY) -> dict:
        self.image_provider.plan_submissions([
            Submission("SUCCEEDED", f"{key}-task-{index}") for index in range(1, len(self.shots) + 1)
        ])
        revision = self.projection()["workspace"]["revision"]
        result = require_ok(self.service.start_generation_set(
            self.workspace, expected_etag=revision, idempotency_key=key,
        ), "start generation")
        actions = [
            attempt["action_id"]
            for shot in result["plan"]["shot_specs"] for attempt in shot["generation_attempts"]
        ]
        return require_ok(self.service.reconcile_generation(
            self.workspace, action_ids=actions,
        ), "reconcile generation")

    def first_candidate_choices(self, projection: dict) -> list:
        return [
            {"shot_id": shot["id"], "candidate_sha256": shot["candidates"][0]["candidate_id"]}
            for shot in projection["plan"]["shot_specs"]
        ]

    def test_selection_requires_every_shot_and_versions_are_immutable(self):
        projection = self.complete_set()
        revision = projection["workspace"]["revision"]
        choices = self.first_candidate_choices(projection)
        incomplete = self.service.save_selection(
            self.workspace, expected_etag=revision, choices=choices[:-1],
        )
        self.assertEqual(incomplete.status_code, 409, incomplete.body)
        self.assertEqual(incomplete.body["error"]["code"], "SELECTION_INCOMPLETE")
        cross = self.service.save_selection(
            self.workspace, expected_etag=revision,
            choices=[
                {"shot_id": choices[0]["shot_id"], "candidate_sha256": choices[1]["candidate_sha256"]},
                *choices[1:],
            ],
        )
        self.assertEqual(cross.body["error"]["code"], "CANDIDATE_NOT_FOUND", cross.body)
        saved = require_ok(self.service.save_selection(
            self.workspace, expected_etag=revision, choices=choices,
        ), "save selection")
        self.assertEqual(saved["selection"]["version"], 1, saved["selection"])
        self.assertEqual(len(saved["selection"]["choices"]), len(choices))
        self.assertIsNone(saved["export"])
        second = require_ok(self.service.save_selection(
            self.workspace, expected_etag=saved["workspace"]["revision"], choices=choices,
        ), "save selection again")
        self.assertEqual(second["selection"]["version"], 2)
        self.assertEqual(second["selection"]["id"], saved["selection"]["id"])
        self.assertEqual(len(WorkspaceStore.open(self.workspace).list_records("selection")), 2)

    def test_shot_selection_saves_incrementally_and_rejects_stale_etag(self):
        projection = self.complete_set()
        shots = projection["plan"]["shot_specs"]
        revision = projection["workspace"]["revision"]
        first, second = shots[0], shots[1]
        saved = require_ok(self.service.save_shot_selection(
            self.workspace, expected_etag=revision, shot_id=first["id"],
            candidate_sha256=first["candidates"][0]["candidate_id"],
        ), "save first shot selection")
        self.assertEqual(saved["selection"]["version"], 1, saved["selection"])
        self.assertEqual(
            [item["shot"]["id"] for item in saved["selection"]["choices"]], [first["id"]])
        blocked = self.service.export_selection(
            self.workspace, expected_etag=saved["workspace"]["revision"])
        self.assertEqual(blocked.status_code, 409, blocked.body)
        self.assertEqual(blocked.body["error"]["code"], "SELECTION_INCOMPLETE")
        stale = self.service.save_shot_selection(
            self.workspace, expected_etag=revision, shot_id=second["id"],
            candidate_sha256=second["candidates"][0]["candidate_id"])
        self.assertEqual(stale.status_code, 409, stale.body)
        self.assertEqual(stale.body["error"]["code"], "REVISION_CONFLICT")
        self.assertEqual(len(self.projection()["selection"]["choices"]), 1)
        completed = require_ok(self.service.save_shot_selection(
            self.workspace, expected_etag=saved["workspace"]["revision"], shot_id=second["id"],
            candidate_sha256=second["candidates"][0]["candidate_id"],
        ), "save second shot selection")
        self.assertEqual(completed["selection"]["version"], 2, completed["selection"])
        self.assertEqual(
            {item["shot"]["id"] for item in completed["selection"]["choices"]},
            {first["id"], second["id"]},
        )

    def test_unconfirmed_submission_can_be_abandoned_then_resent(self):
        self.image_provider.plan_submissions([
            Submission("UNKNOWN", None) for _ in self.shots
        ])
        started = require_ok(self.service.start_generation_set(
            self.workspace,
            expected_etag=self.projection()["workspace"]["revision"],
            idempotency_key="abandon-set-1",
        ), "start unknown set")
        attempts = [
            item for shot in started["plan"]["shot_specs"]
            for item in shot["generation_attempts"]
        ]
        self.assertEqual([item["status"] for item in attempts], ["UNKNOWN"] * len(self.shots))
        self.assertTrue(all(item["provider_task_id"] is None for item in attempts))
        blocked = self.service.start_generation_set(
            self.workspace, expected_etag=started["workspace"]["revision"],
            idempotency_key="abandon-set-2",
        )
        self.assertEqual(blocked.body["error"]["code"], "GENERATION_UNRESOLVED", blocked.body)
        no_reason = self.service.abandon_generation_attempt(
            self.workspace, expected_etag=started["workspace"]["revision"],
            action_id=attempts[0]["action_id"], reason=" ",
        )
        self.assertEqual(no_reason.body["error"]["code"], "ABANDON_REASON_REQUIRED", no_reason.body)
        current = started
        for item in attempts:
            current = require_ok(self.service.abandon_generation_attempt(
                self.workspace, expected_etag=current["workspace"]["revision"],
                action_id=item["action_id"], reason="已在服务端核对，这次提交没有任务编号",
            ), "abandon attempt")
        statuses = [
            item["status"] for shot in current["plan"]["shot_specs"]
            for item in shot["generation_attempts"]
        ]
        self.assertEqual(statuses, ["ABANDONED"] * len(self.shots))
        self.image_provider.plan_submissions([
            Submission("SUBMITTED", "known-task-1"),
            *[Submission("SUCCEEDED", f"resent-task-{index}") for index in range(1, len(self.shots))],
        ])
        resent = require_ok(self.service.start_generation_set(
            self.workspace, expected_etag=current["workspace"]["revision"],
            idempotency_key="abandon-set-3",
        ), "start resent set")
        resent_attempts = [
            item for shot in resent["plan"]["shot_specs"]
            for item in shot["generation_attempts"]
        ]
        known = next(item for item in resent_attempts if item["provider_task_id"] == "known-task-1")
        known_stop = self.service.abandon_generation_attempt(
            self.workspace, expected_etag=resent["workspace"]["revision"],
            action_id=known["action_id"], reason="试图放弃",
        )
        self.assertEqual(known_stop.body["error"]["code"], "GENERATION_TASK_KNOWN", known_stop.body)

    def test_rework_only_touches_the_target_shot(self):
        projection = self.complete_set()
        shots = projection["plan"]["shot_specs"]
        target, other_a, other_b = shots[0], shots[1], shots[2]
        before = {
            shot["id"]: [item["candidate_id"] for item in shot["candidates"]] for shot in shots
        }
        target_prompt = target["latest_prompt"]
        edited = target_prompt["full_text"] + "\n\nAdditional rework direction: keep the framing tight."
        saved_prompt = require_ok(self.service.save_prompt_edit(
            self.workspace,
            expected_etag=projection["workspace"]["revision"],
            shot_id=target["id"],
            expected_prompt_version=target_prompt["version"],
            full_text=edited,
            reason="背景杂乱，想收紧构图",
        ), "save prompt edit")
        edited_shot = next(
            shot for shot in saved_prompt["plan"]["shot_specs"] if shot["id"] == target["id"]
        )
        self.assertEqual(edited_shot["latest_prompt"]["version"], target_prompt["version"] + 1)
        self.assertEqual(edited_shot["latest_prompt"]["edit_reason"], "背景杂乱，想收紧构图")
        self.image_provider.plan_submissions([Submission("SUCCEEDED", "rework-task-1")])
        rework = require_ok(self.service.start_shot_generation(
            self.workspace,
            expected_etag=saved_prompt["workspace"]["revision"],
            shot_id=target["id"],
            idempotency_key="rework-key-1",
        ), "start rework")
        rework_actions = [
            attempt["action_id"]
            for shot in rework["plan"]["shot_specs"] for attempt in shot["generation_attempts"]
        ]
        after = require_ok(self.service.reconcile_generation(
            self.workspace, action_ids=rework_actions,
        ), "reconcile rework")
        by_shot = {shot["id"]: shot for shot in after["plan"]["shot_specs"]}
        self.assertEqual(len(by_shot[target["id"]]["generation_attempts"]), 2)
        self.assertEqual(len(by_shot[target["id"]]["candidates"]), 2)
        self.assertNotEqual(
            [item["candidate_id"] for item in by_shot[target["id"]]["candidates"]],
            before[target["id"]],
        )
        for shot in (other_a, other_b):
            self.assertEqual(
                [item["candidate_id"] for item in by_shot[shot["id"]]["candidates"]],
                before[shot["id"]],
            )
            self.assertEqual(len(by_shot[shot["id"]]["generation_attempts"]), 1)
        # Three shots for the initial set plus exactly one rework submission.
        self.assertEqual(len(self.image_provider.submit_calls), 4)

    def test_two_phase_rework_preview_then_confirm_keeps_history(self):
        projection = self.complete_set()
        shots = projection["plan"]["shot_specs"]
        target, other_a, other_b = shots[0], shots[1], shots[2]
        saved = require_ok(self.service.save_selection(
            self.workspace, expected_etag=projection["workspace"]["revision"],
            choices=self.first_candidate_choices(projection),
        ), "save selection")
        projection = saved
        self.assertEqual(len(projection["selection"]["choices"]), 3)
        before_submits = len(self.image_provider.submit_calls)
        before_candidates = {
            shot["id"]: [item["candidate_id"] for item in shot["candidates"]] for shot in shots
        }
        before_attempts = {
            shot["id"]: [item["action_id"] for item in shot["generation_attempts"]] for shot in shots
        }

        preview = require_ok(self.service.preview_shot_rework(
            self.workspace,
            expected_etag=projection["workspace"]["revision"],
            shot_id=target["id"],
            quick_reasons=["scene-background"],
            direction="换成浅色木桌，商品保持居中",
        ), "preview rework")
        # The first step compiles a versioned proposal and never calls the image provider.
        self.assertEqual(preview["image_calls"], 0)
        self.assertEqual(len(self.image_provider.submit_calls), before_submits)
        self.assertEqual(preview["base"]["prompt_version"], target["latest_prompt"]["version"])
        self.assertEqual(
            preview["keep"], ["商品身份", "已确认事实", "整套 Style Lock", "非目标 Shot"])
        self.assertTrue(preview["change"])
        self.assertTrue(preview["expected_result"])
        self.assertTrue(preview["prompt"]["diff"])
        self.assertEqual(preview["input"]["quick_reasons"], ["scene-background"])
        missing_input = self.service.preview_shot_rework(
            self.workspace, expected_etag=projection["workspace"]["revision"],
            shot_id=target["id"], quick_reasons=[], direction="",
        )
        self.assertEqual(
            missing_input.body["error"]["code"], "REWORK_INPUT_REQUIRED", missing_input.body)

        self.image_provider.plan_submissions([Submission("SUCCEEDED", "two-phase-rework-1")])
        confirmed = require_ok(self.service.confirm_shot_rework(
            self.workspace,
            expected_etag=projection["workspace"]["revision"],
            shot_id=target["id"],
            proposal=preview,
            idempotency_key="two-phase-confirm-1",
        ), "confirm rework")
        self.assertEqual(len(self.image_provider.submit_calls), before_submits + 1)
        by_shot = {shot["id"]: shot for shot in confirmed["plan"]["shot_specs"]}
        target_after = by_shot[target["id"]]
        self.assertEqual(
            [item["version"] for item in target_after["prompt_versions"]],
            [item["version"] for item in target["prompt_versions"]] + [preview["base"]["prompt_version"] + 1],
        )
        self.assertEqual(target_after["latest_prompt"]["edit_mode"], "rework")
        self.assertEqual(len(target_after["generation_attempts"]), 2)
        self.assertEqual(len(target_after["candidates"]), 2)
        self.assertEqual(
            [item["candidate_id"] for item in target_after["candidates"]][:1],
            before_candidates[target["id"]],
        )
        for shot in (other_a, other_b):
            self.assertEqual(
                [item["action_id"] for item in by_shot[shot["id"]]["generation_attempts"]],
                before_attempts[shot["id"]],
            )
            self.assertEqual(
                [item["candidate_id"] for item in by_shot[shot["id"]]["candidates"]],
                before_candidates[shot["id"]],
            )
        # The target shot is pending re-confirmation; its old choice stays on disk.
        self.assertEqual(
            sorted(choice["shot"]["id"] for choice in confirmed["selection"]["choices"]),
            sorted([other_a["id"], other_b["id"]]),
        )
        blocked = self.service.export_selection(
            self.workspace, expected_etag=confirmed["workspace"]["revision"],
        )
        self.assertEqual(blocked.body["error"]["code"], "SELECTION_INCOMPLETE", blocked.body)
        selections = WorkspaceStore.open(self.workspace).list_records("selection")
        self.assertTrue(
            any(target["id"] in [choice["shot"]["id"] for choice in record["choices"]]
                for record in selections),
            "the pre-rework SelectionVersion must remain traceable",
        )

        # A double-click with the same key returns the same state without a second submit.
        replay = self.service.confirm_shot_rework(
            self.workspace,
            expected_etag=projection["workspace"]["revision"],
            shot_id=target["id"],
            proposal=preview,
            idempotency_key="two-phase-confirm-1",
        )
        self.assertTrue(replay.ok, replay.body)
        self.assertEqual(len(self.image_provider.submit_calls), before_submits + 1)
        # A different key against the now-committed prompt is rejected as stale.
        stale = self.service.confirm_shot_rework(
            self.workspace,
            expected_etag=confirmed["workspace"]["revision"],
            shot_id=target["id"],
            proposal=preview,
            idempotency_key="two-phase-confirm-2",
        )
        self.assertEqual(stale.body["error"]["code"], "PROPOSAL_STALE", stale.body)

        # Re-picking any old candidate completes the selection again; the delivery
        # check still reports the newer rework prompt, so exporting the old image
        # requires the explicit D4.11 consistency acknowledgment first.
        current = self.projection()
        require_ok(self.service.save_shot_selection(
            self.workspace,
            expected_etag=current["workspace"]["revision"],
            shot_id=target["id"],
            candidate_sha256=before_candidates[target["id"]][0],
        ), "re-adopt old candidate")
        current = self.projection()
        self.assertEqual(len(current["selection"]["choices"]), 3)
        real_module = use_stub_platform_checks()
        try:
            refused = self.service.export_selection(
                self.workspace, expected_etag=current["workspace"]["revision"],
            )
            self.assertEqual(
                refused.body["error"]["code"], "EXPORT_CONSISTENCY_ACK_REQUIRED", refused.body,
            )
            exported = require_ok(self.service.export_selection(
                self.workspace, expected_etag=current["workspace"]["revision"],
                acknowledge_consistency=True,
            ), "export after acknowledgment")
        finally:
            restore_platform_checks(real_module)
        self.assertEqual(exported["export"]["version"], 1)
        self.assertEqual(
            [item["shot_id"] for item in exported.get("plan_wording_warnings") or []],
            [target["id"]],
        )

    def test_prompt_save_marks_target_shot_stale(self):
        projection = self.complete_set()
        shots = projection["plan"]["shot_specs"]
        target = shots[0]
        saved = require_ok(self.service.save_selection(
            self.workspace, expected_etag=projection["workspace"]["revision"],
            choices=self.first_candidate_choices(projection),
        ), "save selection")
        prompt = target["latest_prompt"]
        edited = require_ok(self.service.save_prompt_edit(
            self.workspace,
            expected_etag=saved["workspace"]["revision"],
            shot_id=target["id"],
            expected_prompt_version=prompt["version"],
            full_text=prompt["full_text"] + "\n\nManual clarification for the retake.",
            reason="收紧构图",
        ), "save prompt edit")
        self.assertEqual(
            sorted(choice["shot"]["id"] for choice in edited["selection"]["choices"]),
            sorted(shot["id"] for shot in shots if shot["id"] != target["id"]),
        )
        blocked = self.service.export_selection(
            self.workspace, expected_etag=edited["workspace"]["revision"],
        )
        self.assertEqual(blocked.body["error"]["code"], "SELECTION_INCOMPLETE", blocked.body)
        self.image_provider.plan_submissions([Submission("SUCCEEDED", "prompt-save-retake-1")])
        regenerated = require_ok(self.service.start_shot_generation(
            self.workspace,
            expected_etag=edited["workspace"]["revision"],
            shot_id=target["id"],
            idempotency_key="prompt-save-retake-1",
        ), "regenerate after prompt save")
        shot_after = next(
            shot for shot in regenerated["plan"]["shot_specs"] if shot["id"] == target["id"]
        )
        self.assertEqual(len(shot_after["candidates"]), 2)
        self.assertTrue(
            regenerated["selection"] is None
            or target["id"] not in [choice["shot"]["id"] for choice in regenerated["selection"]["choices"]]
        )

    def test_export_requires_selection_and_writes_deliverable(self):
        projection = self.complete_set()
        without = self.service.export_selection(
            self.workspace, expected_etag=projection["workspace"]["revision"],
        )
        self.assertEqual(without.body["error"]["code"], "SELECTION_REQUIRED", without.body)
        choices = self.first_candidate_choices(projection)
        saved = require_ok(self.service.save_selection(
            self.workspace, expected_etag=projection["workspace"]["revision"], choices=choices,
        ), "save selection")
        real_module = use_stub_platform_checks()
        try:
            exported = require_ok(self.service.export_selection(
                self.workspace, expected_etag=saved["workspace"]["revision"],
            ), "export selection")
        finally:
            restore_platform_checks(real_module)
        record = exported["export"]
        self.assertEqual(record["version"], 1)
        export_dir = self.workspace / record["relative_path"]
        self.assertTrue(export_dir.is_dir(), record)
        for item in record["files"]:
            path = self.workspace / item["relative_path"]
            content = path.read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), item["file_sha256"])
            self.assertTrue(item["relative_path"].startswith(record["relative_path"] + "/images/"))
        manifest = json.loads((self.workspace / record["manifest_relative_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["export"]["id"], record["id"])
        self.assertEqual(len(manifest["prompts"]), len(record["files"]))
        self.assertTrue(manifest["checks"])
        readme = (export_dir / "README.md").read_text(encoding="utf-8")
        self.assertIn("校验方式", readme)

    def test_export_refuses_when_hard_check_fails(self):
        projection = self.complete_set()
        choices = self.first_candidate_choices(projection)
        saved = require_ok(self.service.save_selection(
            self.workspace, expected_etag=projection["workspace"]["revision"], choices=choices,
        ), "save selection")
        real_module = use_stub_platform_checks(hard_failures=[{
            "rule_id": "amazon-us.main_image.white_background", "rule_version": "1",
            "passed": False, "detail": "背景不是纯白", "source_uri": "https://sellercentral.amazon.com/",
            "checked_at": "2026-09-28", "scope": "hard",
        }])
        try:
            result = self.service.export_selection(
                self.workspace, expected_etag=saved["workspace"]["revision"],
            )
        finally:
            restore_platform_checks(real_module)
        self.assertEqual(result.status_code, 409, result.body)
        self.assertEqual(result.body["error"]["code"], "PLATFORM_CHECK_FAILED")
        self.assertEqual(
            result.body["error"]["details"]["failed_rule_ids"],
            ["amazon-us.main_image.white_background"],
        )
        self.assertEqual(len(WorkspaceStore.open(self.workspace).list_records("export")), 0)

    def test_export_refuses_tampered_candidate_file(self):
        projection = self.complete_set()
        choices = self.first_candidate_choices(projection)
        saved = require_ok(self.service.save_selection(
            self.workspace, expected_etag=projection["workspace"]["revision"], choices=choices,
        ), "save selection")
        target = projection["plan"]["shot_specs"][0]["candidates"][0]
        (self.workspace / target["relative_path"]).write_bytes(b"tampered")
        real_module = use_stub_platform_checks()
        try:
            result = self.service.export_selection(
                self.workspace, expected_etag=saved["workspace"]["revision"],
            )
        finally:
            restore_platform_checks(real_module)
        self.assertEqual(result.body["error"]["code"], "CANDIDATE_FILE_INVALID", result.body)


class ExportHTTPChecks(unittest.TestCase):
    def test_export_route_streams_file_and_reveal_opens_folder(self):
        with tempfile.TemporaryDirectory(prefix="amz-export-http-") as raw_root:
            root = Path(raw_root)
            workspace = root / "workspace"
            image_provider = FakeImageProvider()
            from src.application_service import ApplicationService, ImageUpload
            from src.providers.fake_semantic import FakeSemanticProvider
            from tools.verify_product_v1_image_generation import reference_png, semantic_responses

            service = ApplicationService(
                semantic_provider_factory=lambda: FakeSemanticProvider(semantic_responses()),
                image_provider_factory=lambda: image_provider,
            )
            revealed = []
            app = ProductApplication(
                service=service, recent_index_path=root / "recent.json",
                reveal_opener=revealed.append,
            )
            created = require_ok(service.create_workspace(workspace), "create")
            intake = require_ok(service.save_intake(
                workspace, expected_etag=created["workspace"]["revision"],
                product_name="通勤保温杯", description="随行杯", selling_points=["单手开盖"],
                user_intent="通勤", reference_images=[ImageUpload("r.png", reference_png(), "primary")],
            ), "intake")
            draft = require_ok(service.generate_product_brief_draft(
                workspace, expected_etag=intake["workspace"]["revision"],
            ), "brief")
            brief = require_ok(service.save_product_brief(
                workspace, expected_etag=draft["workspace_revision"], fields=draft["product_brief"],
            ), "save brief")
            plan = require_ok(service.generate_product_plan(
                workspace, expected_etag=brief["workspace"]["revision"],
            ), "plan")
            image_provider.plan_submissions([
                Submission("SUCCEEDED", f"http-task-{index}")
                for index in range(1, len(plan["plan"]["shot_specs"]) + 1)
            ])
            started = require_ok(service.start_generation_set(
                workspace, expected_etag=plan["workspace"]["revision"], idempotency_key="http-set-1",
            ), "start set")
            actions = [
                attempt["action_id"] for shot in started["plan"]["shot_specs"]
                for attempt in shot["generation_attempts"]
            ]
            done = require_ok(service.reconcile_generation(workspace, action_ids=actions), "reconcile")
            choices = [
                {"shot_id": shot["id"], "candidate_sha256": shot["candidates"][0]["candidate_id"]}
                for shot in done["plan"]["shot_specs"]
            ]
            selected = require_ok(service.save_selection(
                workspace, expected_etag=done["workspace"]["revision"], choices=choices,
            ), "selection")
            real_module = use_stub_platform_checks()
            try:
                exported = require_ok(service.export_selection(
                    workspace, expected_etag=selected["workspace"]["revision"],
                ), "export")
            finally:
                restore_platform_checks(real_module)
            record = exported["export"]
            server = create_product_server("127.0.0.1", 0, application=app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                response = requests.get(
                    f"{base}/api/exports/{record['id']}/files/0",
                    params={"directory": str(workspace)}, timeout=10,
                )
                self.assertEqual(response.status_code, 200, response.text[:400])
                expected = (workspace / record["files"][0]["relative_path"]).read_bytes()
                self.assertEqual(response.content, expected)
                reveal = requests.post(
                    f"{base}/api/export/reveal",
                    json={"directory": str(workspace), "export_id": record["id"]}, timeout=10,
                )
                self.assertEqual(reveal.status_code, 200, reveal.text[:400])
                self.assertTrue(reveal.json()["data"]["revealed"])
                self.assertEqual(len(revealed), 1)
                self.assertIn(str(workspace / record["relative_path"]), revealed[0])
                missing = requests.get(
                    f"{base}/api/exports/{record['id']}/files/9",
                    params={"directory": str(workspace)}, timeout=10,
                )
                self.assertEqual(missing.status_code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
