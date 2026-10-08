#!/usr/bin/env python
"""C11 evidence: a second, structurally different product through the real compile path.

Builds a fresh workspace for a non-fixture product (a photo of a running shoe),
drives the product's own service methods with the real DashScope semantic model
(intake -> brief -> dynamic plan -> per-shot prompts, no image generation), and
records a structured comparison against the sweater run so the two products can
be judged "different and explainable" from evidence rather than prose.

Usage:
  <python> tools/run_c11_second_product.py --workspace-dir DIR --image PATH [options]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application_service import ApplicationService, ImageUpload
from src.workspace_store import WorkspaceStore

EVIDENCE = ROOT / "evals" / "product-demo"
SWEATER_WORKSPACE = (
    ROOT / "_working" / "amz-listing-kit-product-demo" / "real-ui-run-05" / "workspace"
)


def require_ok(response, label: str) -> dict:
    if not response.ok:
        raise AssertionError(f"{label} failed: {response.body}")
    return response.body["data"]


def describe_workspace(workspace: Path) -> dict:
    """Read the persisted records and describe one product's compiled plan."""
    store = WorkspaceStore.open(workspace)
    snapshot = store.load_workspace()
    current = snapshot.workspace["current"]
    brief = store.get_record(
        "product_brief", current["product_brief"]["id"], version=current["product_brief"]["version"],
    )
    plan = store.get_record("plan", current["plan"]["id"], version=current["plan"]["version"])
    prompts: dict[str, dict] = {}
    for record in store.list_records("prompt"):
        shot_id = record["shot"]["id"]
        kept = prompts.get(shot_id)
        if kept is None or int(record["version"]) > int(kept["version"]):
            prompts[shot_id] = record
    shots = []
    for item in plan["shots"]:
        shot = store.get_record(
            "shot_spec", item["shot"]["id"], version=item["shot"]["version"],
        )
        prompt = prompts.get(shot["id"])
        shots.append({
            "order": item["order"],
            "title": shot["title"],
            "archetype_id": shot["archetype_id"],
            "purpose": shot["purpose"],
            "supporting_fact_keys": list(shot.get("supporting_fact_keys") or []),
            "prompt_version": prompt["version"] if prompt else None,
            "prompt_block_kinds": [block["kind"] for block in (prompt or {}).get("blocks", [])],
            "prompt_text_head": (prompt or {}).get("full_text", "")[:160],
            "prompt_sha256": (prompt or {}).get("full_text_sha256"),
        })
    return {
        "workspace": str(workspace),
        "category": (brief.get("category") or {}).get("label"),
        "facts": [
            {"key": fact.get("key"), "state": fact.get("state"), "source": fact.get("source")}
            for fact in brief.get("facts", [])
        ],
        "shot_count": len(shots),
        "style_lock_direction": (plan.get("style_lock") or {}).get("direction"),
        "shots": shots,
    }


def build_second_product(
    workspace: Path, image: Path, *, product_name: str, description: str,
    selling_points: list[str], user_intent: str,
) -> dict:
    if (workspace / "workspace.json").is_file():
        raise SystemExit(f"workspace already exists: {workspace}")
    service = ApplicationService()  # default factories: real DashScope providers
    created = require_ok(service.create_workspace(workspace), "create workspace")
    intake = require_ok(service.save_intake(
        workspace, expected_etag=created["workspace"]["revision"],
        product_name=product_name, description=description,
        selling_points=selling_points, user_intent=user_intent,
        reference_images=[ImageUpload(image.name, image.read_bytes(), "primary")],
    ), "save intake")
    draft = require_ok(service.generate_product_brief_draft(
        workspace, expected_etag=intake["workspace"]["revision"],
    ), "draft product brief")
    brief = require_ok(service.save_product_brief(
        workspace, expected_etag=draft["workspace_revision"], fields=draft["product_brief"],
    ), "save product brief")
    plan = require_ok(service.generate_product_plan(
        workspace, expected_etag=brief["workspace"]["revision"],
    ), "generate product plan")
    revision = plan["workspace"]["revision"]
    compiled = []
    for shot in plan["plan"]["shot_specs"]:
        prompted = require_ok(service.generate_prompt(
            workspace, expected_etag=revision, shot_id=shot["id"],
        ), f"compile prompt for {shot['title']}")
        revision = prompted["workspace"]["revision"]
        compiled.append({"shot_id": shot["id"], "title": shot["title"]})
    return {"compiled_prompts": compiled, "final_revision": revision}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-dir", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--product-name", default="轻量透气跑步鞋")
    parser.add_argument(
        "--description",
        default="轻量透气跑鞋，网面鞋面配缓震中底，适合日常慢跑与长时间行走。",
    )
    parser.add_argument("--selling-point", action="append", default=None)
    parser.add_argument(
        "--user-intent", default="突出缓震与透气，适合日常慢跑和通勤走路。",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace_dir)
    image = Path(args.image)
    if not image.is_file():
        raise SystemExit(f"reference image missing: {image}")
    workspace.parent.mkdir(parents=True, exist_ok=True)
    selling_points = args.selling_point or ["回弹缓震中底", "透气网面鞋身"]

    started = datetime.now()
    run = build_second_product(
        workspace, image, product_name=args.product_name, description=args.description,
        selling_points=selling_points, user_intent=args.user_intent,
    )
    second = describe_workspace(workspace)
    first = describe_workspace(SWEATER_WORKSPACE) if SWEATER_WORKSPACE.is_dir() else None

    comparison = {
        "schema": "amz-listing-kit/c11-two-products@1",
        "created_at": started.isoformat(timespec="seconds"),
        "first_product": first,
        "second_product": second,
        "differences": {
            "category": [first and first["category"], second["category"]],
            "shot_count": [first and first["shot_count"], second["shot_count"]],
            "archetypes": [
                first and [shot["archetype_id"] for shot in first["shots"]],
                [shot["archetype_id"] for shot in second["shots"]],
            ],
            "fact_keys": [
                first and [fact["key"] for fact in first["facts"]],
                [fact["key"] for fact in second["facts"]],
            ],
        },
        "second_product_run": run,
        "boundary": (
            "Semantic compile path only: no image generation, no human quality review. "
            "Both reference photos are real operator assets, neither is a built-in fixture."
        ),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"c11-two-products-{started.strftime('%Y-%m-%d')}.json"
    out.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "evidence": str(out),
        "second_product": {
            "category": second["category"],
            "shot_count": second["shot_count"],
            "shots": [shot["title"] for shot in second["shots"]],
        },
        "first_product": first and {
            "category": first["category"],
            "shot_count": first["shot_count"],
            "shots": [shot["title"] for shot in first["shots"]],
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
