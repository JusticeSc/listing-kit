#!/usr/bin/env python
"""D4.11 checks: read-only delivery preflight, consistency acknowledgment, versioned export.

Proves the S4 delivery step: the preflight never writes an ExportVersion, hard
failures and missing selections block export without creating a "completed"
record, wording drift requires an explicit operator acknowledgment that is
recorded in the manifest/README, and re-export never overwrites an old package.

Run with:
  <python> tools/verify_product_v1_delivery_checks.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from app.product_v1_server import ProductApplication, create_product_server
from tools.verify_product_v1_image_generation import (
    FIRST_KEY,
    GenerationFixture,
    Submission,
    require_ok,
    semantic_responses,
)
from tools.verify_product_v1_selection_rework_export import (
    RegisteredFakeImageProvider,
    restore_platform_checks,
    use_stub_platform_checks,
)
from src.application_service import ApplicationService
from src.providers.fake_semantic import FakeSemanticProvider
from src.workspace_store import WorkspaceStore

DRIFT_HEADING = "注意：方案文本与提示词可能不一致"


class DeliveryCheckTests(GenerationFixture):
    def setUp(self):
        super().setUp()
        self.image_provider = RegisteredFakeImageProvider()
        self.service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(semantic_responses()),
            image_provider_factory=lambda: self.image_provider,
        )

    def complete_set(self, key: str = FIRST_KEY) -> dict:
        self.image_provider.plan_submissions([
            Submission("SUCCEEDED", f"{key}-task-{index}")
            for index in range(1, len(self.shots) + 1)
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

    def select_all(self, projection, choices=None):
        choices = choices if choices is not None else self.first_candidate_choices(projection)
        return require_ok(self.service.save_selection(
            self.workspace, expected_etag=projection["workspace"]["revision"], choices=choices,
        ), "save selection")

    def test_preflight_is_read_only_and_reports_clean_state(self):
        projection = self.complete_set()
        selected = self.select_all(projection)
        store = WorkspaceStore.open(self.workspace)
        exports_before = store.list_records("export")

        real_module = use_stub_platform_checks()
        try:
            check = require_ok(self.service.export_preflight(self.workspace), "preflight")
        finally:
            restore_platform_checks(real_module)

        self.assertTrue(check["can_export"])
        self.assertTrue(check["ready"])
        self.assertEqual([], check["consistency"])
        self.assertEqual([], check["missing_shots"])
        self.assertEqual([], check["blockers"])
        self.assertEqual(3, len(check["selected"]))
        self.assertEqual(check["workspace_revision"], selected["workspace"]["revision"])
        for item in check["selected"]:
            self.assertTrue(item["planned_file_name"].startswith("images/"))
            self.assertTrue(item["candidate_id"])
            self.assertEqual("qwen-image-3.0", item["model_id"])

        self.assertEqual(exports_before, store.list_records("export"))
        self.assertIsNone(store.load_workspace().workspace["current"]["export"])

    def test_preflight_lists_missing_shots_and_blocks_export(self):
        projection = self.complete_set()

        empty = require_ok(self.service.export_preflight(self.workspace), "preflight without selection")
        self.assertFalse(empty["can_export"])
        codes = {item["code"] for item in empty["blockers"]}
        self.assertIn("SELECTION_REQUIRED", codes)
        self.assertEqual(3, len(empty["missing_shots"]))

        partial = self.first_candidate_choices(projection)[:1]
        require_ok(self.service.save_shot_selection(
            self.workspace, expected_etag=projection["workspace"]["revision"],
            shot_id=partial[0]["shot_id"], candidate_sha256=partial[0]["candidate_sha256"],
        ), "partial selection")
        check = require_ok(self.service.export_preflight(self.workspace), "preflight partial")
        self.assertFalse(check["can_export"])
        self.assertFalse(check["ready"])
        self.assertEqual(2, len(check["missing_shots"]))
        self.assertEqual(1, len(check["selected"]))
        self.assertEqual([], check["hard_failures"])

    def test_preflight_blocks_a_workspace_without_a_plan(self):
        with tempfile.TemporaryDirectory(prefix="amz-product-v1-delivery-blank-") as tmp:
            blank = Path(tmp) / "workspace"
            require_ok(self.service.create_workspace(blank), "create blank workspace")
            check = require_ok(self.service.export_preflight(blank), "preflight blank")
        self.assertFalse(check["can_export"])
        self.assertEqual(["PLAN_REQUIRED"], [item["code"] for item in check["blockers"]])
        self.assertEqual("intake", check["blockers"][0]["return_to"])
        self.assertEqual([], check["selected"])

    def test_hard_failure_blocks_preflight_and_export_without_writing(self):
        projection = self.complete_set()
        selected = self.select_all(projection)
        real_module = use_stub_platform_checks(hard_failures=[{
            "rule_id": "amazon-us.test.min_size", "rule_version": "1", "passed": False,
            "detail": "测试用硬失败：长边不足。", "scope": "hard",
        }])
        try:
            check = require_ok(self.service.export_preflight(self.workspace), "preflight")
            self.assertFalse(check["can_export"])
            self.assertEqual(
                ["amazon-us.test.min_size"],
                [item["rule_id"] for item in check["hard_failures"]],
            )
            refused = self.service.export_selection(
                self.workspace, expected_etag=selected["workspace"]["revision"],
            )
        finally:
            restore_platform_checks(real_module)
        self.assertFalse(refused.ok)
        self.assertEqual("PLATFORM_CHECK_FAILED", refused.body["error"]["code"])
        store = WorkspaceStore.open(self.workspace)
        self.assertEqual([], store.list_records("export"))
        self.assertIsNone(store.load_workspace().workspace["current"]["export"])

    def test_clean_export_is_versioned_traceable_and_repeat_never_overwrites(self):
        projection = self.complete_set()
        selected = self.select_all(projection)
        real_module = use_stub_platform_checks()
        try:
            first = require_ok(self.service.export_selection(
                self.workspace, expected_etag=selected["workspace"]["revision"],
            ), "first export")
            second = require_ok(self.service.export_selection(
                self.workspace, expected_etag=first["workspace"]["revision"],
            ), "second export")
        finally:
            restore_platform_checks(real_module)

        self.assertNotEqual(first["export"]["id"], second["export"]["id"])
        self.assertGreater(second["export"]["version"], first["export"]["version"])
        first_dir = self.workspace / first["export"]["relative_path"]
        self.assertTrue(first_dir.is_dir())
        self.assertTrue((first_dir / "README.md").is_file())

        manifest = json.loads((first_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("通勤保温杯", manifest["product"]["name"])
        self.assertEqual(3, len(manifest["prompts"]))
        self.assertTrue(manifest["plan"]["id"])
        chosen = {item["candidate_sha256"] for item in manifest["selection"]["choices"]}
        files = manifest["export"]["files"]
        self.assertEqual(3, len(files))
        self.assertEqual(chosen, {item["candidate_sha256"] for item in files})
        for item in files:
            content = (self.workspace / item["relative_path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(content).hexdigest(), item["file_sha256"], item["relative_path"],
            )

    def test_wording_drift_requires_acknowledgment_and_is_recorded(self):
        projection = self.complete_set()
        selected = self.select_all(projection)
        target = selected["plan"]["shot_specs"][0]
        prompt = target["latest_prompt"]
        delivered = target["candidates"][0]["candidate_id"]
        edited = require_ok(self.service.save_prompt_edit(
            self.workspace, expected_etag=selected["workspace"]["revision"],
            shot_id=target["id"], expected_prompt_version=prompt["version"],
            full_text=prompt["full_text"] + "\n交付前核对：保持构图。",
            reason="交付前核对方案文字。",
        ), "edit prompt")
        stale = self.service.export_selection(
            self.workspace, expected_etag=edited["workspace"]["revision"],
        )
        self.assertEqual("SELECTION_INCOMPLETE", stale.body["error"]["code"])

        readopted = require_ok(self.service.save_shot_selection(
            self.workspace, expected_etag=edited["workspace"]["revision"],
            shot_id=target["id"], candidate_sha256=delivered,
        ), "re-adopt delivered candidate")
        real_module = use_stub_platform_checks()
        try:
            check = require_ok(self.service.export_preflight(self.workspace), "preflight drift")
        finally:
            restore_platform_checks(real_module)
        self.assertTrue(check["can_export"])
        self.assertTrue(check["consistency_required"])
        self.assertEqual([target["id"]], [item["shot_id"] for item in check["consistency"]])
        self.assertEqual("delivered_with_older_prompt", check["consistency"][0]["reason"])

        real_module = use_stub_platform_checks()
        try:
            refused = self.service.export_selection(
                self.workspace, expected_etag=readopted["workspace"]["revision"],
            )
            self.assertFalse(refused.ok)
            self.assertEqual("EXPORT_CONSISTENCY_ACK_REQUIRED", refused.body["error"]["code"])
            self.assertEqual(
                [target["id"]],
                [item["shot_id"] for item in refused.body["error"]["details"]["issues"]],
            )
            exported = require_ok(self.service.export_selection(
                self.workspace, expected_etag=readopted["workspace"]["revision"],
                acknowledge_consistency=True,
            ), "acknowledged export")
        finally:
            restore_platform_checks(real_module)

        warnings = exported.get("plan_wording_warnings") or []
        self.assertEqual([target["id"]], [item["shot_id"] for item in warnings])
        readme = (
            self.workspace / exported["export"]["relative_path"] / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn(DRIFT_HEADING, readme)
        self.assertIn(target["title"], readme)
        store = WorkspaceStore.open(self.workspace)
        self.assertEqual(1, len(store.list_records("export")))

    def test_http_routes_preflight_export_and_reveal(self):
        projection = self.complete_set()
        selected = self.select_all(projection)
        revealed: list[str] = []
        application = ProductApplication(
            service=self.service,
            recent_index_path=self.workspace.parent / "recent-http.json",
            reveal_opener=revealed.append,
        )
        server = create_product_server("127.0.0.1", 0, application=application)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        real_module = use_stub_platform_checks()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            preflight = requests.post(
                f"{base}/api/exports/preflight",
                json={"directory": str(self.workspace)}, timeout=10,
            )
            self.assertEqual(200, preflight.status_code, preflight.text[:400])
            payload = preflight.json()["data"]
            self.assertTrue(payload["can_export"])
            self.assertEqual([], WorkspaceStore.open(self.workspace).list_records("export"))

            exported = requests.post(
                f"{base}/api/exports",
                json={
                    "directory": str(self.workspace),
                    "expected_etag": selected["workspace"]["revision"],
                },
                timeout=30,
            )
            self.assertEqual(201, exported.status_code, exported.text[:400])
            record = exported.json()["data"]["export"]

            compat = requests.post(
                f"{base}/api/export",
                json={
                    "directory": str(self.workspace),
                    "expected_etag": exported.json()["data"]["workspace"]["revision"],
                },
                timeout=30,
            )
            self.assertEqual(201, compat.status_code, compat.text[:400])
            self.assertNotEqual(record["id"], compat.json()["data"]["export"]["id"])

            reveal = requests.post(
                f"{base}/api/exports/reveal",
                json={"directory": str(self.workspace), "export_id": record["id"]},
                timeout=10,
            )
            self.assertEqual(200, reveal.status_code, reveal.text[:400])
            self.assertTrue(reveal.json()["data"]["revealed"])
            self.assertEqual(
                str(self.workspace / record["relative_path"]), revealed[0],
            )

            fallback = requests.post(
                f"{base}/api/exports/reveal",
                json={"directory": str(self.workspace)},
                timeout=10,
            )
            self.assertEqual(200, fallback.status_code, fallback.text[:400])
        finally:
            restore_platform_checks(real_module)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
