#!/usr/bin/env python
"""Verify editable plan persistence, guards, and immutable reference history."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from app.product_v1_server import ProductApplication, create_product_server
from src import product_v1_contracts as contracts
from src.application_service import ApplicationService
from src.providers.fake_semantic import FakeSemanticProvider
from src.workspace_store import WorkspaceStore
from tools.verify_product_v1_plan import png_1x1, prepare_saved_brief, require_ok, responses
from tools.verify_product_v1_prompt import latest_prompt, prompt_blocks


EDITABLE_FIELDS = ("title", "purpose", "reason", "preserve", "change")


def shot_payload(shot: dict, **overrides: object) -> dict:
    result = {"id": shot["id"]}
    result.update({name: copy.deepcopy(shot[name]) for name in EDITABLE_FIELDS})
    result.update(overrides)
    return result


def assert_graph_is_valid(workspace: Path) -> None:
    store = WorkspaceStore.open(workspace)
    snapshot = store.load_workspace()
    documents = {
        kind: store.list_records(kind)
        for kind in contracts.DOCUMENT_KINDS - {"workspace"}
    }
    base = ROOT / "config" / "product-v1"
    archetypes = json.loads((base / "archetypes.json").read_text(encoding="utf-8"))
    platform = json.loads(
        (base / "platforms" / "amazon-us.json").read_text(encoding="utf-8")
    )
    providers = json.loads((base / "providers.json").read_text(encoding="utf-8"))
    errors = contracts.validate_workspace_graph(
        snapshot.workspace, documents, archetypes, platform, providers,
    )
    assert errors == [], errors


def main() -> int:
    provider_fixture = responses()
    provider_fixture["propose_prompt_blocks"] = prompt_blocks(
        include_confirmed_selling_point=True,
    )
    service = ApplicationService(
        semantic_provider_factory=lambda: FakeSemanticProvider(provider_fixture),
    )

    with tempfile.TemporaryDirectory(prefix="amz-product-v1-plan-edit-") as raw_root:
        root = Path(raw_root)
        workspace = root / "workspace"
        prepare_saved_brief(service, workspace, png_1x1())

        before_plan = require_ok(service.get_workspace_projection(workspace), "load before plan")
        plan_data = require_ok(service.generate_product_plan(
            workspace, expected_etag=before_plan["workspace"]["revision"],
        ), "generate plan")
        plan_v1 = copy.deepcopy(plan_data["plan"])
        initial_shots = plan_v1["shot_specs"]
        hero = next(shot for shot in initial_shots if shot["archetype_id"] == "hero")
        feature = next(
            shot for shot in initial_shots
            if "selling_point_1" in shot["supporting_fact_keys"]
        )
        deleted_optional = next(
            shot for shot in initial_shots
            if not shot["required"] and shot["id"] not in {hero["id"], feature["id"]}
        )

        before_prompt = require_ok(service.get_workspace_projection(workspace), "load before prompt")
        prompt_data = require_ok(service.generate_prompt(
            workspace,
            expected_etag=before_prompt["workspace"]["revision"],
            shot_id=feature["id"],
        ), "generate prompt on original plan")
        old_prompt = copy.deepcopy(latest_prompt(
            next(shot for shot in prompt_data["plan"]["shot_specs"] if shot["id"] == feature["id"])
        ))
        old_revision = prompt_data["workspace"]["revision"]
        assert old_prompt["plan"] == {
            "kind": "plan", "id": plan_v1["id"], "version": plan_v1["version"],
        }
        assert old_prompt["shot"] == {
            "kind": "shot_spec", "id": feature["id"], "version": feature["version"],
        }

        app = ProductApplication(service=service, recent_index_path=root / "recent.json")
        server = create_product_server("127.0.0.1", 0, application=app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        def put_plan(expected_etag: str, shots: list[dict]) -> requests.Response:
            return requests.put(
                f"{base_url}/api/plan",
                json={
                    "directory": str(workspace),
                    "expected_etag": expected_etag,
                    "plan": {"shots": shots},
                },
                timeout=10,
            )

        try:
            # Array order is canonical order. This also removes one optional shot.
            edited_shots = [
                shot_payload(
                    hero,
                    title="已调整的主图",
                    purpose="明确展示商品本体。",
                    reason="主图仍遵循平台必需规则。",
                    preserve=["商品外观与真实颜色"],
                    change=["纯白背景"],
                ),
                shot_payload(
                    feature,
                    title="已调整的卖点图",
                    purpose="清楚展示经确认的单手开盖卖点。",
                    reason="将用户确认的卖点作为本图内容依据。",
                    preserve=["商品外观与真实颜色"],
                    change=["信息层级与构图"],
                ),
            ]
            success = put_plan(old_revision, edited_shots)
            assert success.status_code == 200, (success.status_code, success.text)
            payload = success.json()
            assert payload.get("ok") is True, payload
            edited = payload["data"]
            plan_v2 = edited["plan"]
            edited_plan_shots = plan_v2["shot_specs"]
            assert plan_v2["id"] == plan_v1["id"]
            assert plan_v2["version"] == plan_v1["version"] + 1
            assert [shot["id"] for shot in edited_plan_shots] == [hero["id"], feature["id"]]
            assert [shot["order"] for shot in edited_plan_shots] == [1, 2]
            assert [shot["title"] for shot in edited_plan_shots] == [
                "已调整的主图", "已调整的卖点图",
            ]
            assert all(shot["version"] == 2 for shot in edited_plan_shots)
            assert edited_plan_shots[0]["required"] is True
            assert deleted_optional["id"] not in {shot["id"] for shot in edited_plan_shots}
            assert all(shot["latest_prompt"] is None for shot in edited_plan_shots)

            # Reopen reads the committed Plan v2; Plan/ShotSpec v1 and its Prompt stay intact.
            reopened = require_ok(
                ApplicationService().get_workspace_projection(workspace), "reopen edited workspace",
            )
            assert reopened["workspace"]["revision"] == edited["workspace"]["revision"]
            assert reopened["plan"]["content_hash"] == plan_v2["content_hash"]
            assert [shot["id"] for shot in reopened["plan"]["shot_specs"]] == [
                hero["id"], feature["id"],
            ]
            assert reopened["plan"]["shot_specs"][1]["latest_prompt"] is None

            store = WorkspaceStore.open(workspace)
            saved_plan_v1 = store.get_record("plan", plan_v1["id"], version=1)
            saved_plan_v2 = store.get_record("plan", plan_v1["id"], version=2)
            assert saved_plan_v1["content_hash"] == plan_v1["content_hash"]
            assert saved_plan_v2["content_hash"] == plan_v2["content_hash"]
            saved_prompt = store.get_record("prompt", old_prompt["id"], version=old_prompt["version"])
            assert saved_prompt["plan"] == old_prompt["plan"]
            assert saved_prompt["shot"] == old_prompt["shot"]
            assert store.get_record("shot_spec", feature["id"], version=1)["plan"] == old_prompt["plan"]
            assert_graph_is_valid(workspace)

            stable_snapshot = store.load_workspace()
            stable_counts = {
                kind: len(store.list_records(kind)) for kind in ("plan", "shot_spec")
            }
            current_shots = reopened["plan"]["shot_specs"]

            # Required Amazon US hero cannot be removed.
            missing_hero = put_plan(
                stable_snapshot.etag,
                [shot_payload(current_shots[1])],
            )
            assert missing_hero.status_code == 422, (missing_hero.status_code, missing_hero.text)
            assert missing_hero.json()["error"]["code"] == "REQUIRED_SHOT_CANNOT_DELETE"

            # Empty plans and cross-plan/removed Shot IDs are rejected without writes.
            empty = put_plan(stable_snapshot.etag, [])
            assert empty.status_code == 422, (empty.status_code, empty.text)
            assert empty.json()["error"]["code"] == "PLAN_EMPTY"
            foreign = put_plan(stable_snapshot.etag, [
                shot_payload(current_shots[0]), shot_payload(current_shots[1]),
                shot_payload(deleted_optional),
            ])
            assert foreign.status_code == 422, (foreign.status_code, foreign.text)
            assert foreign.json()["error"]["code"] == "SHOT_NOT_IN_CURRENT_PLAN"

            # The pre-edit ETag is stale and cannot append any records.
            stale = put_plan(old_revision, edited_shots)
            assert stale.status_code == 409, (stale.status_code, stale.text)
            assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
            after_rejections = WorkspaceStore.open(workspace)
            assert after_rejections.load_workspace().etag == stable_snapshot.etag
            assert {
                kind: len(after_rejections.list_records(kind)) for kind in ("plan", "shot_spec")
            } == stable_counts
            assert_graph_is_valid(workspace)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    print(json.dumps({
        "endpoint": "PUT /api/plan",
        "edit_reorder_optional_delete": "passed",
        "required_hero_protection": "passed",
        "empty_and_cross_plan_shots_rejected": "passed",
        "stale_revision_no_write": "passed",
        "reopen_restore_and_immutable_prompt_history": "passed",
        "workspace_graph": "passed",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
