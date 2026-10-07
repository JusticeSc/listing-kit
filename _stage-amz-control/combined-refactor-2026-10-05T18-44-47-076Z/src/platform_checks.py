"""Deterministic platform and file checks for the Product V1 export step.

Only the currently selected candidates are measured, and every value comes from
the frozen Amazon US profile or from decoding the exported bytes. Rules that a
machine cannot settle (occupancy, staging, semantics, taste) are reported as
manual notes so they are never dressed up as verified compliance.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src import product_v1_contracts as contracts
from src.product_export import (
    BLOCKING_RULE_IDS,
    blocked_rule_ids,
    file_checks,
    inspect_image,
    review_rule_ids,
)
from src.workspace_store import WorkspaceStore

PLATFORM_PROFILE_PATH = contracts.ROOT / "config" / "product-v1" / "platforms" / "amazon-us.json"


class PlatformCheckError(RuntimeError):
    """The check bundle cannot be produced from the current workspace state."""


def load_platform_profile(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else PLATFORM_PROFILE_PATH
    try:
        profile = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlatformCheckError(f"平台规则配置不可读取：{target.name}") from exc
    if not isinstance(profile, Mapping):
        raise PlatformCheckError("平台规则配置格式无效。")
    return dict(profile)


def _profile_summary(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": profile.get("profile_id"),
        "version": profile.get("version"),
        "marketplace": profile.get("marketplace"),
        "file_rules": dict(profile.get("file_rules") or {}),
        "main_image_guidance": dict(profile.get("main_image_guidance") or {}),
        "source": dict(profile.get("source") or {}),
    }


def run_export_checks(directory: Path, *, profile_path: Path | None = None) -> dict[str, Any]:
    """Measure the selected candidates and split findings into hard vs manual."""
    store = WorkspaceStore.open(directory)
    workspace = store.load_workspace().workspace
    plan_ref = workspace["current"]["plan"]
    selection_ref = workspace["current"]["selection"]
    if plan_ref is None or selection_ref is None:
        raise PlatformCheckError("导出前需要当前套图方案与选择记录。")
    plan = store.get_record("plan", plan_ref["id"], version=plan_ref["version"])
    selection = store.get_record(
        "selection", selection_ref["id"], version=selection_ref["version"],
    )
    choices = {
        item["shot"]["id"]: item["candidate_sha256"] for item in selection["choices"]
    }
    profile = load_platform_profile(profile_path)
    checks: list[dict[str, Any]] = []
    for entry in plan["shots"]:
        shot_ref = entry["shot"]
        digest = choices.get(shot_ref["id"])
        if digest is None:
            continue
        shot = store.get_record("shot_spec", shot_ref["id"], version=shot_ref["version"])
        _record, content = store.read_candidate_by_sha256(digest)
        image = inspect_image(content)
        for check in file_checks(
            image=image,
            content=content,
            platform_profile=profile,
            is_primary=shot.get("archetype_id") == "hero",
        ):
            checks.append({
                **check,
                "shot_id": shot_ref["id"],
                "shot_title": shot.get("title"),
                "archetype_id": shot.get("archetype_id"),
                "width": image["width"],
                "height": image["height"],
            })
    hard_ids = set(BLOCKING_RULE_IDS)
    hard_failures = [item for item in checks if item["rule_id"] in hard_ids and not item["passed"]]
    manual_notes = [
        {
            "rule_id": item["rule_id"],
            "shot_id": item["shot_id"],
            "detail": f"{item['shot_title']}：{item['detail']}",
        }
        for item in checks
        if item["rule_id"] not in hard_ids and not item["passed"]
    ]
    guidance = profile.get("main_image_guidance") or {}
    manual_notes.append({
        "rule_id": "main_image_human_review",
        "shot_id": None,
        "detail": (
            f"主图背景 RGB{tuple(guidance.get('background_rgb', [255, 255, 255]))}、"
            f"商品占比 ≥{guidance.get('minimum_product_occupancy_percent', 85)}%、"
            f"不得叠加文字或水印（该配置自述 verification={guidance.get('verification', 'human_review')}）；"
            "这些项目前只能由人工核对，系统不宣称已自动验证。"
        ),
    })
    manual_notes.append({
        "rule_id": "aesthetic_human_review",
        "shot_id": None,
        "detail": "画面观感、卖点表达是否准确属于人工判断，系统只提供测量值与追溯清单。",
    })
    return {
        "profile": _profile_summary(profile),
        "checks": checks,
        "hard_failures": hard_failures,
        "manual_notes": manual_notes,
        "blocked_rule_ids": blocked_rule_ids(checks),
        "review_rule_ids": review_rule_ids(checks),
    }
