#!/usr/bin/env python
"""Fake-provider integration checks for Product V1 whole-set image generation.

Proves, without network access or credentials:

- one provider submission per shot, carrying the exact current prompt and the
  ordered product reference bytes, with the shot prompt hash recorded on the attempt;
- re-clicking with the same idempotency key never submits twice;
- an UNKNOWN submission with a provider task id is reconciled by querying that
  same task id, and blocks any new submission until it is resolved;
- a failed download keeps the task id, does not resubmit, and can be completed
  by a later reconcile;
- partial failure keeps already-materialized candidates and their file hashes;
- candidate bytes are immutable, hash-verified, served by the HTTP route, and
  survive a full reopen of the workspace.

The real qwen-image-3.0 request path is proven separately by a live run; this
file never fabricates a model response for the shipped adapter.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests
from PIL import Image

from app.product_v1_server import ProductApplication, create_product_server
from src.application_service import ApplicationService, ImageUpload
from src.providers.fake_semantic import FakeSemanticProvider
from src.providers.image import ImageProviderError, ImageReference, ImageTask
from src.workspace_store import WorkspaceStore

FIRST_KEY = "product-v1-image-batch-0001"
SECOND_KEY = "product-v1-image-batch-0002"


def png_bytes(color=(40, 90, 140), size=(16, 12)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def reference_png() -> bytes:
    """A 320x240 PNG so the reference image is structurally a real product photo stand-in."""
    return png_bytes((210, 200, 180), (320, 240))


def semantic_responses() -> dict[str, dict]:
    return {
        "analyze_product": {
            "category": {"label": "通勤保温杯", "confidence": 0.91, "source": "model_inference"},
            "facts": [{"key": "材质", "value": "316 不锈钢", "state": "confirmed",
                       "source": "model_inference", "confidence": 0.62, "source_refs": ["description"]}],
            "must_preserve": ["杯身轮廓"], "may_change": ["背景与布光"], "unknowns": ["真实材质"],
        },
        "propose_plan": {
            "style_lock": {"direction": "清爽可信的通勤商品摄影", "palette": ["暖白", "深蓝"],
                           "lighting": "柔和侧光", "background": "简洁通勤场景",
                           "continuity_notes": ["整组光线与色调一致"]},
            "shots": [
                {"archetype_id": "feature", "title": "单手开盖", "purpose": "展示用户确认的单手开盖卖点。",
                 "reason": "卖点由用户提供。", "preserve": ["商品身份、颜色与结构"], "change": ["画面布局"],
                 "reference_asset_sha256": [], "supporting_fact_keys": ["selling_point_1"], "dependencies": []},
                {"archetype_id": "lifestyle", "title": "日常通勤", "purpose": "呈现日常通勤使用情境。",
                 "reason": "情境来自用户意图。", "preserve": ["商品身份、颜色与结构"], "change": ["通勤环境"],
                 "reference_asset_sha256": [], "supporting_fact_keys": [], "dependencies": []},
            ],
        },
        "propose_prompt_blocks": {"blocks": [
            {"id": "style", "kind": "style_lock", "text": "整组保持清爽可信的通勤商品摄影风格。",
             "source_refs": ["plan.style_lock"]},
            {"id": "task", "kind": "shot_task", "text": "围绕当前图片任务清楚展示商品。",
             "source_refs": ["shot_spec.purpose"]},
            {"id": "negative", "kind": "negative", "text": "不要改变商品真实颜色、轮廓和结构。",
             "source_refs": ["shot_spec.preserve"]},
        ]},
        "propose_rework": {
            "keep": ["商品身份与轮廓", "已确认事实", "整组视觉方向"],
            "change": ["按用户指出的问题调整这一张的构图与环境"],
            "expected_result": "只重做当前这一张；保持商品与整组风格不变。",
            "blocks": [
                {"id": "style", "kind": "style_lock",
                 "text": "整组保持清爽可信的通勤商品摄影风格。",
                 "source_refs": ["plan.style_lock"]},
                {"id": "task", "kind": "shot_task",
                 "text": "按用户返工方向重新组织当前图片，但任务目标不变。",
                 "source_refs": ["shot_spec.purpose"]},
                {"id": "negative", "kind": "negative",
                 "text": "不要改变商品真实颜色、轮廓和结构。",
                 "source_refs": ["shot_spec.preserve"]},
            ],
        },
    }


@dataclass(frozen=True)
class Submission:
    status: str
    task_id: str | None
    error: str | None = None


class FakeImageProvider:
    """Deterministic provider fake; records every call and never touches the network."""

    provider_id = "test-fake-image-provider"
    model_id = "test-fake-image-model"

    def __init__(self) -> None:
        self._submissions: list[Submission] = []
        self._query_results: dict[str, ImageTask] = {}
        self._downloadable: dict[str, bytes] = {}
        self._download_failures: dict[str, ImageProviderError] = {}
        self.submit_calls: list[dict] = []
        self.query_calls: list[str] = []
        self.download_calls: list[str] = []

    def plan_submissions(self, submissions: Sequence[Submission]) -> None:
        self._submissions = list(submissions)

    def queue_success(self, task_id: str, content: bytes) -> str:
        url = f"fake://image-result/{task_id}"
        self._downloadable[url] = content
        return url

    def set_query_result(self, task_id: str, *, status: str, url: str | None = None,
                         error: str | None = None) -> None:
        urls = (url,) if url else ()
        self._query_results[task_id] = ImageTask(
            self.provider_id, self.model_id, task_id, status, result_urls=urls, error=error,
        )

    def fail_download(self, url: str, *, status: str = "UNKNOWN", message: str = "下载未确认") -> None:
        self._download_failures[url] = ImageProviderError("RESULT_DOWNLOAD_FAILED", message, status=status)

    def clear_download_failure(self, url: str) -> None:
        self._download_failures.pop(url, None)

    def submit(self, prompt: str, references: Sequence[ImageReference], *, model_id: str | None = None,
               size: str = "1344*1344", seed: int | None = None,
               idempotency_key: str | None = None) -> ImageTask:
        del seed
        if not self._submissions:
            raise AssertionError("unexpected image-provider submission")
        planned = self._submissions.pop(0)
        index = len(self.submit_calls) + 1
        self.submit_calls.append({
            "prompt": prompt, "references": list(references), "model_id": model_id,
            "size": size, "idempotency_key": idempotency_key,
        })
        urls: tuple[str, ...] = ()
        if planned.status.upper() == "SUCCEEDED" and planned.task_id:
            urls = (self.queue_success(planned.task_id, png_bytes((20 + index, 80 + index, 140 + index))),)
        return ImageTask(self.provider_id, self.model_id, planned.task_id, planned.status,
                         result_urls=urls, error=planned.error)

    def query_task(self, task_id: str) -> ImageTask:
        self.query_calls.append(task_id)
        if task_id not in self._query_results:
            raise AssertionError(f"unexpected query for provider task {task_id!r}")
        return self._query_results[task_id]

    def download_result(self, url: str) -> tuple[bytes, str]:
        self.download_calls.append(url)
        failure = self._download_failures.get(url)
        if failure is not None:
            raise failure
        if url not in self._downloadable:
            raise AssertionError(f"unexpected result download {url!r}")
        return self._downloadable[url], "image/png"


def require_ok(response, label: str) -> dict:
    if not response.ok:
        raise AssertionError(f"{label} failed: {response.body}")
    return response.body["data"]


class GenerationFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="amz-product-v1-image-generation-")
        self.workspace = Path(self.temp.name) / "workspace"
        self.image_provider = FakeImageProvider()
        self.reference = reference_png()
        self.service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(semantic_responses()),
            image_provider_factory=lambda: self.image_provider,
        )
        self.plan = self._prepare_workspace()
        self.shots = self.plan["plan"]["shot_specs"]
        self.assertEqual(len(self.shots), 3, "fixture must exercise a multi-shot set")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _prepare_workspace(self) -> dict:
        created = require_ok(self.service.create_workspace(self.workspace), "create workspace")
        intake = require_ok(self.service.save_intake(
            self.workspace, expected_etag=created["workspace"]["revision"],
            product_name="通勤保温杯", description="可重复使用的随行杯，不用于户外露营。",
            selling_points=["单手开盖"], user_intent="突出日常通勤，避免户外露营画面。",
            reference_images=[ImageUpload("reference.png", self.reference, "primary")],
        ), "save product intake")
        draft = require_ok(self.service.generate_product_brief_draft(
            self.workspace, expected_etag=intake["workspace"]["revision"],
        ), "draft product brief")
        brief = require_ok(self.service.save_product_brief(
            self.workspace, expected_etag=draft["workspace_revision"], fields=draft["product_brief"],
        ), "save product brief")
        return require_ok(self.service.generate_product_plan(
            self.workspace, expected_etag=brief["workspace"]["revision"],
        ), "generate product plan")

    def projection(self) -> dict:
        return require_ok(self.service.get_workspace_projection(self.workspace), "load projection")

    def start(self, key: str = FIRST_KEY):
        revision = self.projection()["workspace"]["revision"]
        return self.service.start_generation_set(
            self.workspace, expected_etag=revision, idempotency_key=key,
        )

    def reference_digest(self) -> str:
        return hashlib.sha256(self.reference).hexdigest()

    def candidates_by_shot(self, projection: dict) -> dict[str, list[dict]]:
        return {shot["id"]: list(shot.get("candidates") or []) for shot in projection["plan"]["shot_specs"]}

    def attempts_by_shot(self, projection: dict) -> dict[str, list[dict]]:
        return {shot["id"]: list(shot.get("generation_attempts") or [])
                for shot in projection["plan"]["shot_specs"]}


class WholeSetGenerationChecks(GenerationFixture):
    def test_full_set_submits_once_materializes_candidates_and_survives_reopen(self):
        self.image_provider.plan_submissions([
            Submission("SUCCEEDED", f"task-{index}") for index in (1, 2, 3)
        ])
        response = self.start()
        self.assertEqual(response.status_code, 202, response.body)
        require_ok(response, "start whole-set generation")

        self.assertEqual(len(self.image_provider.submit_calls), 3)
        data = self.projection()
        attempts = self.attempts_by_shot(data)
        candidates = self.candidates_by_shot(data)
        self.assertEqual(sorted(len(items) for items in attempts.values()), [1, 1, 1])
        self.assertEqual(sorted(len(items) for items in candidates.values()), [1, 1, 1])

        uploads = {call["idempotency_key"] for call in self.image_provider.submit_calls}
        self.assertEqual(len(uploads), 3, "each shot needs its own submission identity")
        for shot in data["plan"]["shot_specs"]:
            attempt = attempts[shot["id"]][0]
            candidate = candidates[shot["id"]][0]
            self.assertEqual(attempt["status"], "SUCCEEDED", attempt)
            self.assertTrue(attempt["provider_task_id"])
            self.assertEqual(attempt["provider_id"], "test-fake-image-provider")
            self.assertEqual(attempt["model_id"], "test-fake-image-model")
            self.assertEqual(attempt["reference_asset_sha256"], [self.reference_digest()])
            self.assertEqual(attempt["prompt"]["version"], shot["latest_prompt"]["version"])
            call = next(item for item in self.image_provider.submit_calls
                        if item["idempotency_key"] == attempt["idempotency_key"])
            self.assertEqual(call["prompt"], shot["latest_prompt"]["full_text"])
            self.assertEqual(call["model_id"], "test-fake-image-model")
            self.assertEqual(call["size"], "1344*1344")
            self.assertEqual(len(call["references"]), 1)
            self.assertEqual(call["references"][0].sha256, self.reference_digest())
            self.assertEqual(call["references"][0].content, self.reference)
            expected_request = {
                "provider_id": "test-fake-image-provider", "model_id": "test-fake-image-model",
                "prompt_sha256": hashlib.sha256(shot["latest_prompt"]["full_text"].encode("utf-8")).hexdigest(),
                "reference_asset_sha256": [self.reference_digest()],
                "size": "1344*1344", "prompt_extend": False,
            }
            expected_hash = hashlib.sha256(json.dumps(
                expected_request, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
            self.assertEqual(attempt["request_sha256"], expected_hash)
            record, content = WorkspaceStore.open(self.workspace).read_candidate_by_sha256(candidate["candidate_id"])
            self.assertEqual(record["shot"]["id"], shot["id"])
            self.assertEqual(hashlib.sha256(content).hexdigest(), candidate["candidate_id"])
            with Image.open(io.BytesIO(content)) as decoded:
                self.assertEqual(decoded.size, (candidate["width"], candidate["height"]))
            self.assertTrue(candidate["relative_path"].startswith(f"shots/{shot['id']}/candidates/"))

        # A repeated click with the same identity must not submit anything again.
        before = len(self.image_provider.submit_calls)
        repeated = self.start(key=FIRST_KEY)
        require_ok(repeated, "repeat with the same idempotency key")
        self.assertEqual(len(self.image_provider.submit_calls), before)
        self.assertEqual(len(WorkspaceStore.open(self.workspace).list_records("generation_attempt")), 3)

        reopened = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(semantic_responses()),
            image_provider_factory=lambda: FakeImageProvider(),
        )
        after_reopen = require_ok(reopened.get_workspace_projection(self.workspace), "reopen workspace")
        self.assertEqual(sorted(len(items) for items in self.candidates_by_shot(after_reopen).values()), [1, 1, 1])

    def test_unknown_is_reconciled_by_original_task_id_without_resubmitting(self):
        first_url = self.image_provider.queue_success("task-1", png_bytes((11, 22, 33)))
        self.image_provider.plan_submissions([
            Submission("UNKNOWN", "task-1", "查询超时"), Submission("SUCCEEDED", "task-2"),
            Submission("SUCCEEDED", "task-3"),
        ])
        require_ok(self.start(), "start with one unknown shot")
        self.assertEqual(len(self.image_provider.submit_calls), 3)

        data = self.projection()
        attempts = self.attempts_by_shot(data)
        unknown = next(record for items in attempts.values() for record in items
                       if record["status"] == "UNKNOWN")
        self.assertEqual(unknown["provider_task_id"], "task-1")
        successful_before = {
            shot_id: sorted(item["candidate_id"] for item in items)
            for shot_id, items in self.candidates_by_shot(data).items()
        }
        self.assertEqual(sum(len(item) for item in successful_before.values()), 2)

        blocked = self.start(key=SECOND_KEY)
        self.assertEqual(blocked.status_code, 409, blocked.body)
        self.assertEqual(blocked.body["error"]["code"], "GENERATION_UNRESOLVED")
        self.assertEqual(len(self.image_provider.submit_calls), 3, "no resubmission while unresolved")

        self.image_provider.set_query_result("task-1", status="SUCCEEDED", url=first_url)
        reconciled = require_ok(
            self.service.reconcile_generation(self.workspace, action_ids=[unknown["action_id"]]),
            "reconcile unknown attempt",
        )
        self.assertEqual(self.image_provider.query_calls, ["task-1"])
        resolved = next(record for items in self.attempts_by_shot(reconciled).values() for record in items
                        if record["action_id"] == unknown["action_id"])
        self.assertEqual((resolved["status"], resolved["provider_task_id"]), ("SUCCEEDED", "task-1"))
        self.assertEqual(sorted(len(items) for items in self.candidates_by_shot(reconciled).values()), [1, 1, 1])
        self.assertEqual(len(self.image_provider.submit_calls), 3)
        after = {shot_id: sorted(item["candidate_id"] for item in items)
                 for shot_id, items in self.candidates_by_shot(reconciled).items()}
        for shot_id, digests in successful_before.items():
            if digests:
                self.assertEqual(after[shot_id][:len(digests)], digests, "successful candidates must not change")

        # Reconciling an already-succeeded attempt is a no-op: no extra query, no download.
        downloads = len(self.image_provider.download_calls)
        again = require_ok(
            self.service.reconcile_generation(self.workspace, action_ids=[unknown["action_id"]]),
            "reconcile a succeeded attempt",
        )
        self.assertEqual(self.image_provider.query_calls, ["task-1"])
        self.assertEqual(len(self.image_provider.download_calls), downloads)
        self.assertEqual(sorted(len(items) for items in self.candidates_by_shot(again).values()), [1, 1, 1])

    def test_download_unknown_keeps_task_id_and_completes_on_later_reconcile(self):
        url = self.image_provider.queue_success("task-1", png_bytes((7, 8, 9)))
        self.image_provider.plan_submissions([
            Submission("SUCCEEDED", "task-1"), Submission("SUCCEEDED", "task-2"),
            Submission("SUCCEEDED", "task-3"),
        ])
        self.image_provider.fail_download(url, status="UNKNOWN", message="下载超时")
        require_ok(self.start(), "start with a failing download")

        data = self.projection()
        attempts = self.attempts_by_shot(data)
        pending = next(record for items in attempts.values() for record in items if record["status"] == "UNKNOWN")
        self.assertEqual(pending["provider_task_id"], "task-1")
        self.assertEqual(sorted(len(items) for items in self.candidates_by_shot(data).values()), [0, 1, 1])

        blocked = self.start(key=SECOND_KEY)
        self.assertEqual(blocked.body["error"]["code"], "GENERATION_UNRESOLVED")
        self.assertEqual(len(self.image_provider.submit_calls), 3)

        self.image_provider.clear_download_failure(url)
        self.image_provider.set_query_result("task-1", status="SUCCEEDED", url=url)
        reconciled = require_ok(
            self.service.reconcile_generation(self.workspace, action_ids=[pending["action_id"]]),
            "reconcile after a failed download",
        )
        self.assertEqual(sorted(len(items) for items in self.candidates_by_shot(reconciled).values()), [1, 1, 1])
        self.assertEqual(len(self.image_provider.submit_calls), 3, "reconcile must never submit again")

    def test_rejected_submission_is_terminal_and_a_new_set_preserves_old_candidates(self):
        self.image_provider.plan_submissions([
            Submission("REJECTED", None, "额度不足"), Submission("SUCCEEDED", "task-2"),
            Submission("SUCCEEDED", "task-3"),
        ])
        require_ok(self.start(), "start with a rejected shot")
        data = self.projection()
        rejected = next(record for items in self.attempts_by_shot(data).values() for record in items
                        if record["status"] == "REJECTED")
        self.assertIsNone(rejected["provider_task_id"])
        old_candidates = {shot_id: sorted(item["candidate_id"] for item in items)
                          for shot_id, items in self.candidates_by_shot(data).items()}

        # A rejected request is not an unresolved one: the user may explicitly start a new set.
        self.image_provider.plan_submissions([Submission("SUCCEEDED", f"retry-{index}") for index in (1, 2, 3)])
        require_ok(self.start(key=SECOND_KEY), "start a fresh set after a rejection")
        again = self.projection()
        for shot_id, digests in old_candidates.items():
            if digests:
                current = {item["candidate_id"] for item in self.candidates_by_shot(again)[shot_id]}
                self.assertTrue(set(digests) <= current, "old candidates must be retained")
        for items in self.attempts_by_shot(again).values():
            self.assertEqual(len(items), 2, "the new set appends attempts instead of overwriting them")


class GenerationHTTPChecks(GenerationFixture):
    def test_start_and_candidate_routes_serve_real_bytes(self):
        self.image_provider.plan_submissions([
            Submission("SUCCEEDED", f"task-{index}") for index in (1, 2, 3)
        ])
        app = ProductApplication(service=self.service, recent_index_path=Path(self.temp.name) / "recent.json")
        server = create_product_server("127.0.0.1", 0, application=app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            revision = self.projection()["workspace"]["revision"]
            started = requests.post(
                base + "/api/generation/start",
                json={"directory": str(self.workspace), "expected_etag": revision,
                      "idempotency_key": FIRST_KEY},
                timeout=30,
            )
            self.assertEqual(started.status_code, 202, started.text)
            payload = started.json()
            self.assertTrue(payload["ok"], payload)
            shot = payload["data"]["plan"]["shot_specs"][0]
            candidate = shot["candidates"][0]
            served = requests.get(
                base + f"/api/candidates/{candidate['candidate_id']}",
                params={"directory": str(self.workspace)}, timeout=30,
            )
            self.assertEqual(served.status_code, 200, served.text)
            self.assertEqual(served.headers["Content-Type"], "image/png")
            self.assertEqual(hashlib.sha256(served.content).hexdigest(), candidate["candidate_id"])

            unknown_id = candidate["candidate_id"][:-1] + ("0" if candidate["candidate_id"][-1] != "0" else "1")
            missing = requests.get(
                base + f"/api/candidates/{unknown_id}",
                params={"directory": str(self.workspace)}, timeout=30,
            )
            self.assertEqual(missing.status_code, 404, missing.text)

            reconciled = requests.post(
                base + "/api/generation/reconcile",
                json={"directory": str(self.workspace), "action_ids": []}, timeout=30,
            )
            self.assertEqual(reconciled.status_code, 200, reconciled.text)
            self.assertTrue(reconciled.json()["ok"])

            attempt_id = shot["generation_attempts"][0]["action_id"]
            single = requests.post(
                base + f"/api/attempts/{attempt_id}/reconcile",
                json={"directory": str(self.workspace)}, timeout=30,
            )
            self.assertEqual(single.status_code, 200, single.text)
            self.assertTrue(single.json()["ok"])
            missing_attempt = requests.post(
                base + "/api/attempts/act_0000000000000000000000000000000000000000/reconcile",
                json={"directory": str(self.workspace)}, timeout=30,
            )
            self.assertEqual(missing_attempt.status_code, 404, missing_attempt.text)
            self.assertIn("GENERATION_ATTEMPT_NOT_FOUND", missing_attempt.text)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
