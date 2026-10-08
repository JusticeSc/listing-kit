#!/usr/bin/env python
"""Exercise dynamic plan compilation and persistence through the Product V1 HTTP route."""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import threading
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from app.product_v1_server import ProductApplication, create_product_server
from src.application_service import ApplicationService, ImageUpload
from src.providers.fake_semantic import FakeSemanticProvider
from src.semantic_drafts import SemanticDraftValidationError, validate_draft
from src.workspace_store import WorkspaceStore


def png_1x1() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"\x00\xc8\x30\x20"))
            + chunk(b"IEND", b""))


def responses(*, cyclic: bool = False) -> dict[str, dict]:
    first_dependencies = ["第二卖点"] if cyclic else []
    second_dependencies = ["第一卖点"] if cyclic else ["第一卖点"]
    second_fact_keys = ["selling_point_1"] if cyclic else ["材质"]
    return {
        "analyze_product": {
            "category": {"label": "通勤保温杯", "confidence": 0.91, "source": "model_inference"},
            "facts": [{
                "key": "材质", "value": "316 不锈钢", "state": "confirmed",
                "source": "model_inference", "confidence": 0.62, "source_refs": ["description"],
            }],
            "must_preserve": ["杯身轮廓"], "may_change": ["背景与布光"], "unknowns": ["真实材质"],
        },
        "propose_plan": {
            "style_lock": {
                "direction": "清爽、可信的通勤商品摄影",
                "palette": ["暖白", "深蓝"], "lighting": "柔和侧光",
                "background": "简洁通勤场景", "continuity_notes": ["保持整组光线和色调一致"],
            },
            "shots": [
                {
                    "archetype_id": "feature", "title": "第一卖点", "purpose": "清楚展示经用户确认的卖点。",
                    "reason": "用户提供的卖点是本图依据。",
                    "preserve": ["商品身份与颜色"], "change": ["画面布局"],
                    "reference_asset_sha256": [], "supporting_fact_keys": ["selling_point_1"],
                    "dependencies": first_dependencies,
                },
                {
                    "archetype_id": "feature", "title": "第二卖点", "purpose": "表达模型推断的保冷表现。",
                    "reason": "模型认为商品可保冷很久。",
                    "preserve": ["商品身份与颜色"], "change": ["画面布局"],
                    "reference_asset_sha256": [], "supporting_fact_keys": second_fact_keys,
                    "dependencies": second_dependencies,
                },
                {
                    "archetype_id": "new_type_not_in_registry", "title": "通勤情境", "purpose": "说明本商品的通勤使用方式。",
                    "reason": "这是本次用户意图指定的情境。",
                    "preserve": ["商品身份与颜色"], "change": ["通勤环境"],
                    "reference_asset_sha256": [], "supporting_fact_keys": [],
                    "dependencies": [" 第一卖点 "],
                },
            ],
        },
    }


def require_ok(response, label: str):
    if not response.ok:
        raise AssertionError(f"{label} failed: {response.body}")
    return response.body["data"]


def prepare_saved_brief(service: ApplicationService, workspace: Path, image: bytes) -> dict:
    created = require_ok(service.create_workspace(workspace), "create workspace")
    saved_input = require_ok(service.save_intake(
        workspace,
        expected_etag=created["workspace"]["revision"],
        product_name="通勤保温杯",
        description="可重复使用的随行杯，不用于户外露营。",
        selling_points=["单手开盖"],
        user_intent="突出日常通勤，避免户外露营画面。",
        reference_images=[ImageUpload("reference.png", image, "primary")],
    ), "save intake")
    draft = require_ok(service.generate_product_brief_draft(
        workspace, expected_etag=saved_input["workspace"]["revision"],
    ), "draft product brief")
    return require_ok(service.save_product_brief(
        workspace,
        expected_etag=draft["workspace_revision"],
        fields=draft["product_brief"],
    ), "save product brief")


def main() -> int:
    invalid_required_plan = responses()["propose_plan"]
    invalid_required_plan["shots"][0]["required"] = True
    try:
        validate_draft("propose_plan", invalid_required_plan)
    except SemanticDraftValidationError:
        pass
    else:
        raise AssertionError("model-authored required field must not be accepted")

    image = png_1x1()
    with tempfile.TemporaryDirectory(prefix="amz-product-v1-plan-") as raw_root:
        root = Path(raw_root)
        workspace = root / "workspace"
        service = ApplicationService(semantic_provider_factory=lambda: FakeSemanticProvider(responses()))
        app = ProductApplication(service=service, recent_index_path=root / "recent.json")
        before = prepare_saved_brief(service, workspace, image)
        expected_etag = before["workspace"]["revision"]

        server = create_product_server("127.0.0.1", 0, application=app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            response = requests.post(
                f"http://127.0.0.1:{server.server_address[1]}/api/plan/generate",
                json={"directory": str(workspace), "expected_etag": expected_etag}, timeout=10,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        if not response.ok:
            raise AssertionError(f"plan API returned HTTP {response.status_code}: {response.text}")
        payload = response.json()
        if payload.get("ok") is not True:
            raise AssertionError(f"plan API failed: {payload}")
        data = payload["data"]
        plan = data["plan"]
        shots = plan["shot_specs"]
        by_title = {shot["title"]: shot for shot in shots}

        assert plan["version"] == 1
        assert all("created_at" not in shot for shot in shots)
        assert plan["platform"] == {"profile_id": "amazon-us", "version": 1}
        assert len(shots) == 3, [shot["title"] for shot in shots]
        assert by_title["Amazon US 主图"]["required"] is True
        assert by_title["Amazon US 主图"]["reference_asset_sha256"]
        assert by_title["Amazon US 主图"]["archetype_id"] == "hero"
        assert by_title["通勤情境"]["archetype_id"] == "custom"
        assert by_title["通勤情境"]["dependencies"] == [by_title["第一卖点"]["id"]]
        assert by_title["第一卖点"]["required"] is False
        assert by_title["第一卖点"]["supporting_fact_keys"] == ["selling_point_1"]
        assert "第二卖点" not in by_title
        assert any(item["code"] == "UNSUPPORTED_SHOT_OMITTED" for item in data["compile_warnings"])
        assert any(item["code"] == "ARCHETYPE_FALLBACK" for item in data["compile_warnings"])
        assert any(item["code"] == "REQUIRED_SHOT_ADDED" for item in data["compile_warnings"])

        stored = WorkspaceStore.open(workspace).load_workspace().workspace
        assert stored["current"]["plan"] == {
            "kind": "plan", "id": plan["id"], "version": plan["version"],
        }
        reopened = ApplicationService(semantic_provider_factory=lambda: FakeSemanticProvider(responses()))
        projection = require_ok(reopened.get_workspace_projection(workspace), "reopen workspace")
        assert projection["plan"]["content_hash"] == plan["content_hash"]
        assert [item["title"] for item in projection["plan"]["shot_specs"]] == [item["title"] for item in shots]

        stale = service.generate_product_plan(workspace, expected_etag=expected_etag)
        assert stale.status_code == 409 and stale.body["error"]["code"] == "REVISION_CONFLICT"
        assert len(WorkspaceStore.open(workspace).list_records("plan")) == 1

        cycle_service = ApplicationService(
            semantic_provider_factory=lambda: FakeSemanticProvider(responses(cyclic=True)),
        )
        cycle_before = WorkspaceStore.open(workspace).load_workspace().etag
        cycle_result = cycle_service.generate_product_plan(workspace, expected_etag=cycle_before)
        assert cycle_result.status_code == 502 and cycle_result.body["error"]["code"] == "PLAN_DRAFT_INVALID"
        assert WorkspaceStore.open(workspace).load_workspace().etag == cycle_before
        assert len(WorkspaceStore.open(workspace).list_records("plan")) == 1

    print(json.dumps({
        "dynamic_plan_http": "passed",
        "shot_count": len(shots),
        "omitted_unconfirmed_feature": True,
        "required_hero_added": True,
        "unknown_archetype_uses_custom": True,
        "references_and_fact_evidence_validated": True,
        "dependencies_mapped_to_shot_ids": True,
        "dependency_title_whitespace_trimmed": True,
        "model_required_field_rejected": True,
        "shot_spec_created_at_omitted": True,
        "plan_version_persisted_and_reopened": True,
        "stale_revision_and_cycle_do_not_mutate": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
