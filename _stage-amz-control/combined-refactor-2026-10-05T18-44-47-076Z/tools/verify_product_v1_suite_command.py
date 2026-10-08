#!/usr/bin/env python
"""Offline contract checks for the D4.7 suite commands.

`POST /api/plan/compile` (先看方案) and `POST /api/generations` (一键整套) are
exercised through ApplicationService with a deterministic semantic fixture and
an in-process image provider. No external request is made.
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application_service import ApplicationService, ImageUpload
from src.providers.fake_semantic import FakeSemanticProvider
from src.providers.image import ImageTask
from src.providers.semantic import SemanticProviderError
from src.workspace_store import WorkspaceStore


def png_bytes(rgb: tuple[int, int, int] = (70, 110, 150), size: int = 4) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def semantic_fixture() -> dict[str, dict]:
    return {
        "analyze_product": {
            "category": {"label": "通勤保温杯", "confidence": 0.9, "source": "model_inference"},
            "facts": [{
                "key": "材质", "value": "316 不锈钢", "state": "confirmed",
                "source": "model_inference", "confidence": 0.6, "source_refs": ["description"],
            }],
            "must_preserve": ["杯身轮廓"], "may_change": ["背景与布光"], "unknowns": ["真实材质"],
        },
        "propose_plan": {
            "style_lock": {
                "direction": "清爽、可信的通勤商品摄影", "palette": ["暖白", "深蓝"],
                "lighting": "柔和侧光", "background": "简洁通勤场景",
                "continuity_notes": ["保持整组光线和色调一致"],
            },
            "shots": [
                {
                    "archetype_id": "hero", "title": "主图", "purpose": "清晰展示商品本体。",
                    "reason": "平台主图要求。", "preserve": ["商品身份与颜色"], "change": ["背景"],
                    "reference_asset_sha256": [], "supporting_fact_keys": [], "dependencies": [],
                },
                {
                    "archetype_id": "feature", "title": "卖点图", "purpose": "展示已确认卖点。",
                    "reason": "用户提供的卖点是本图依据。", "preserve": ["商品身份与颜色"],
                    "change": ["画面布局"], "reference_asset_sha256": [],
                    "supporting_fact_keys": ["selling_point_1"], "dependencies": [],
                },
                {
                    "archetype_id": "lifestyle", "title": "通勤情境", "purpose": "说明通勤使用方式。",
                    "reason": "本次用户意图指定的情境。", "preserve": ["商品身份与颜色"],
                    "change": ["通勤环境"], "reference_asset_sha256": [],
                    "supporting_fact_keys": [], "dependencies": ["卖点图"],
                },
            ],
        },
        "propose_prompt_blocks": {
            "blocks": [
                {"id": "style", "kind": "style_lock",
                 "text": "延续清爽、可信的通勤商品摄影风格。", "source_refs": ["plan.style_lock"]},
                {"id": "task", "kind": "shot_task",
                 "text": "清楚呈现本图的画面任务。", "source_refs": ["shot_spec.purpose"]},
                {"id": "negative", "kind": "negative",
                 "text": "不要改变商品真实颜色、轮廓和结构。", "source_refs": ["shot_spec.preserve"]},
            ],
        },
    }


class FakeImageProvider:
    """Deterministic in-process provider; the suite command never spends quota."""

    provider_id = "test-fake-suite-image"
    model_id = "test-fake-suite-image-model"

    def __init__(self, results: list[tuple[str, str]]) -> None:
        self._planned = list(results)
        self._bytes: dict[str, bytes] = {}
        self.submit_calls: list[dict] = []

    def submit(self, prompt, references, *, model_id=None, size="1344*1344",
               seed=None, idempotency_key=None):
        del seed
        if not self._planned:
            raise AssertionError("unexpected image-provider submission")
        status, task_id = self._planned.pop(0)
        index = len(self.submit_calls) + 1
        self.submit_calls.append({
            "prompt": prompt, "references": list(references),
            "idempotency_key": idempotency_key, "status": status, "task_id": task_id,
        })
        urls: tuple[str, ...] = ()
        if status == "SUCCEEDED" and task_id:
            url = f"fake://suite/{task_id}"
            self._bytes[url] = png_bytes((20 + index * 9, 90, 150))
            urls = (url,)
        return ImageTask(self.provider_id, self.model_id, task_id, status, result_urls=urls)

    def query_task(self, task_id: str) -> ImageTask:
        raise AssertionError(f"suite command must not query provider task {task_id!r}")

    def download_result(self, url: str) -> tuple[bytes, str]:
        if url not in self._bytes:
            raise AssertionError(f"unexpected image result download {url!r}")
        return self._bytes[url], "image/png"


class ArrearsSemanticProvider:
    """Every semantic call fails the way an unfunded account does."""

    provider_id = "test-arrears-semantic"
    model_id = "test-arrears-model"

    def analyze_product(self, product_input, source_assets):
        raise SemanticProviderError(
            "UPSTREAM_ACCOUNT_ARREARS", "账户余额不足，请充值后重试。", recoverable=True,
        )

    def propose_plan(self, *args, **kwargs):
        raise AssertionError("plan must not be requested after a failed brief")

    def propose_prompt_blocks(self, *args, **kwargs):
        raise AssertionError("prompt must not be requested after a failed brief")


def require_ok(response, label: str):
    if not response.ok:
        raise AssertionError(f"{label} failed: {response.body}")
    return response.body["data"]


def save_intake(service: ApplicationService, workspace: Path, image: bytes) -> dict:
    created = require_ok(service.create_workspace(workspace), "create workspace")
    return require_ok(service.save_intake(
        workspace,
        expected_etag=created["workspace"]["revision"],
        product_name="通勤保温杯",
        description="可重复使用的随行杯，不用于户外露营。",
        selling_points=["单手开盖"],
        user_intent="突出日常通勤，避免户外露营画面。",
        reference_images=[ImageUpload("reference.png", image, "primary")],
    ), "save intake")


def main() -> int:
    checks: list[str] = []
    failures: list[str] = []
    image = png_bytes()

    def check(label: str, condition: bool) -> None:
        if condition:
            checks.append(label)
            print("ok   " + label)
        else:
            failures.append(label)
            print("FAIL " + label)

    with tempfile.TemporaryDirectory(prefix="amz-suite-command-") as raw_root:
        parent = Path(raw_root)

        # 1. 先看方案: compile and persist Brief/Plan/Prompt with zero image calls.
        provider = FakeImageProvider([])
        service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(semantic_fixture()),
            image_provider_factory=lambda: provider,
        )
        workspace = parent / "prepare-only"
        saved = save_intake(service, workspace, image)
        prepared = require_ok(service.prepare_suite(
            workspace, expected_etag=saved["workspace"]["revision"],
        ), "prepare suite")
        store = WorkspaceStore.open(workspace)
        shot_count = len(prepared["plan"]["shot_specs"])
        check("prepare persists one product brief", prepared["product_brief"]["version"] == 1)
        check("prepare persists a dynamic plan", prepared["plan"]["version"] == 1 and shot_count >= 3)
        check(
            "prepare compiles one prompt per shot",
            all(shot["latest_prompt"] is not None for shot in prepared["plan"]["shot_specs"])
            and len(prepared["prepared"]["shots"]) == shot_count,
        )
        check("prepare never calls the image provider", provider.submit_calls == [])
        check("prepare creates no generation batch", store.list_records("generation_batch") == [])
        check("prepare keeps the workspace out of GENERATING", prepared["workspace"]["status"] != "GENERATING")

        second = require_ok(service.prepare_suite(
            workspace, expected_etag=prepared["workspace"]["revision"],
        ), "prepare suite again")
        check(
            "prepare is idempotent for an already compiled suite",
            second["product_brief"]["version"] == 1
            and second["plan"]["version"] == 1
            and len(store.list_records("prompt")) == shot_count,
        )

        # 2. 一键整套: one command, one batch, one attempt per shot.
        provider = FakeImageProvider([
            ("SUCCEEDED", f"suite-task-{index}") for index in range(1, shot_count + 1)
        ])
        service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(semantic_fixture()),
            image_provider_factory=lambda: provider,
        )
        workspace = parent / "one-command"
        saved = save_intake(service, workspace, image)
        generated = require_ok(service.generate_suite(
            workspace, expected_etag=saved["workspace"]["revision"], action_id="suiteCommand0001",
        ), "generate suite")
        store = WorkspaceStore.open(workspace)
        batches = store.list_records("generation_batch")
        attempts = store.list_records("generation_attempt")
        batch = generated["generation_batch"]
        check("one command creates exactly one batch", len(batches) == 1)
        check(
            "the batch belongs to this command and its plan",
            batch is not None and batch["action_id"] == "suiteCommand0001"
            and batch["plan"]["id"] == generated["plan"]["id"],
        )
        check("the batch covers every shot", batch is not None and len(batch["shots"]) == shot_count)
        check("every shot got exactly one paid submission", len(provider.submit_calls) == shot_count)
        check(
            "batch attempts resolve to the recorded attempts",
            {item["attempt_action_id"] for item in batch["shots"]}
            == {attempt["action_id"] for attempt in attempts},
        )
        check("a completed batch reports COMPLETED", batch["status"] == "COMPLETED")
        check(
            "candidates are materialized for review",
            all(shot["candidates"] for shot in generated["plan"]["shot_specs"]),
        )

        # 3. Refresh / double click with the same action id must replay, not resubmit.
        replay = require_ok(service.generate_suite(
            workspace, expected_etag=saved["workspace"]["revision"], action_id="suiteCommand0001",
        ), "replay generate suite")
        check("a repeated action id replays the batch", bool(replay.get("replayed")))
        check("a repeated action id submits nothing new", len(provider.submit_calls) == shot_count)
        check(
            "a repeated action id keeps one batch",
            len(store.list_records("generation_batch")) == 1
            and len(store.list_records("generation_attempt")) == shot_count,
        )

        # 4. A second intention while an attempt is unresolved is refused.
        unknown_provider = FakeImageProvider(
            [("UNKNOWN", "suite-unknown-1")]
            + [("SUCCEEDED", f"suite-retry-{index}") for index in range(2, shot_count + 1)]
        )
        service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(semantic_fixture()),
            image_provider_factory=lambda: unknown_provider,
        )
        workspace = parent / "unresolved"
        saved = save_intake(service, workspace, image)
        first_suite = require_ok(service.generate_suite(
            workspace, expected_etag=saved["workspace"]["revision"], action_id="suiteCommand0002",
        ), "generate suite with unknown")
        submissions_after_first = len(unknown_provider.submit_calls)
        blocked = service.generate_suite(
            workspace, expected_etag=first_suite["workspace"]["revision"],
            action_id="suiteCommand0003",
        )
        check(
            "an unresolved attempt refuses a new batch",
            blocked.status_code == 409
            and blocked.body["error"]["code"] == "GENERATION_UNRESOLVED",
        )
        check(
            "the refused command submitted nothing",
            len(unknown_provider.submit_calls) == submissions_after_first,
        )
        check(
            "the refused command creates no second batch",
            len(WorkspaceStore.open(workspace).list_records("generation_batch")) == 1,
        )

        # 5. Semantic preparation failure must never submit a paid image task.
        provider = FakeImageProvider([("SUCCEEDED", "never-used")])
        service = ApplicationService(
            semantic_provider_factory=lambda: ArrearsSemanticProvider(),
            image_provider_factory=lambda: provider,
        )
        workspace = parent / "arrears"
        saved = save_intake(service, workspace, image)
        failed = service.generate_suite(
            workspace, expected_etag=saved["workspace"]["revision"], action_id="suiteCommand0004",
        )
        check(
            "a semantic failure surfaces the provider error",
            failed.status_code == 503 and failed.body["error"]["code"] == "UPSTREAM_ACCOUNT_ARREARS",
        )
        check("a semantic failure submits zero images", provider.submit_calls == [])
        check(
            "a semantic failure creates no batch",
            WorkspaceStore.open(workspace).list_records("generation_batch") == [],
        )

        # 6. The command validates its own action id before touching the workspace.
        invalid = service.generate_suite(
            workspace, expected_etag=saved["workspace"]["revision"], action_id="short",
        )
        check(
            "an invalid action id is a request error",
            invalid.status_code == 400 and invalid.body["error"]["code"] == "ACTION_ID_INVALID",
        )

        # 7. S1: the one command persists the submitted form, compiles, and batches.
        provider = FakeImageProvider(
            [("SUCCEEDED", f"inline-{index}") for index in range(1, 4)])
        service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(semantic_fixture()),
            image_provider_factory=lambda: provider,
        )
        workspace = parent / "inline-intake"
        created = require_ok(service.create_workspace(workspace), "create inline workspace")
        inline_fields = {
            "product_name": "折叠收纳箱",
            "description": "可折叠的布艺收纳箱，收起后只有一半高度。",
            "selling_points": ["可折叠"],
            "user_intent": "突出收纳前后的对比。",
            "reference_images": [ImageUpload("inline.png", image, "primary")],
            "reference_order": None,
        }
        inline = require_ok(service.generate_suite(
            workspace,
            expected_etag=created["workspace"]["revision"],
            action_id="suiteInline0001",
            intake=dict(inline_fields),
        ), "inline generate suite")
        check(
            "the command persists the form it received",
            inline["intake"]["product_name"] == "折叠收纳箱"
            and len(inline["intake"]["reference_images"]) == 1,
        )
        check(
            "the same command compiled brief, plan, and prompt",
            inline["product_brief"] is not None and inline["plan"] is not None
            and all(shot["latest_prompt"] for shot in inline["plan"]["shot_specs"]),
        )
        check(
            "the same command created exactly one batch",
            inline["generation_batch"] is not None
            and len(WorkspaceStore.open(workspace).list_records("generation_batch")) == 1,
        )
        check(
            "the inline command paid for one image per shot",
            len(provider.submit_calls) == len(inline["plan"]["shot_specs"]),
        )
        replay = require_ok(service.generate_suite(
            workspace,
            expected_etag=inline["workspace"]["revision"],
            action_id="suiteInline0001",
            intake=dict(inline_fields),
        ), "inline replay")
        again = require_ok(service.prepare_suite(
            workspace,
            expected_etag=replay["workspace"]["revision"],
            intake=dict(inline_fields),
        ), "prepare with the same form again")
        check(
            "a repeated form adds no input version and no second batch",
            bool(replay.get("replayed"))
            and len(WorkspaceStore.open(workspace).list_records("product_input")) == 1
            and len(WorkspaceStore.open(workspace).list_records("generation_batch")) == 1
            and again["intake"]["product_name"] == "折叠收纳箱",
        )

        print(json.dumps({"checks": len(checks), "failed": len(failures)}, ensure_ascii=False))
    if failures:
        for item in failures:
            print("FAIL: " + item)
        return 1
    print(f"suite command checks passed: {len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
