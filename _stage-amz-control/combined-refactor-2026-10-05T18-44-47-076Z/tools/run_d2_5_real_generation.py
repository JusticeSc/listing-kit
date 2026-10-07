#!/usr/bin/env python
"""D2.5: one complete real generation set against qwen-image-3.0 (no mocks).

Uses the configured DashScope providers (DASHSCOPE_API_KEY required). The run is
resumable: an existing workspace is reopened, open attempts are reconciled by their
saved provider task ids and never resubmitted, and only a run with no attempts at
all starts a new generation set.

Every image-provider HTTP call is wrapped in a recording transport that stores the
request shape (model, ordered reference-image count, prompt hash, size) without the
API key or image bytes. Evidence lands in evals/product-demo/.

Usage:
  python tools/run_d2_5_real_generation.py [--workspace DIR] [--timeout 900]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application_service import ApplicationService, ImageUpload
from src.providers.dashscope_image import _requests_transport, create_default_image_provider

EVIDENCE = ROOT / "evals" / "product-demo"
DEFAULT_WORKSPACE = (
    ROOT / "_working" / "amz-listing-kit-product-demo" / "real-run-01" / "workspace"
)
DEFAULT_IMAGE = Path(
    r"E:\workbuddy_workspace\2026-09-20-16-38-19\ecommerce-skills-main"
    r"\docs\batch-image\sku-a-sweater.jpg"
)
ACTIVE_STATUSES = {"CREATED", "SUBMITTED", "RUNNING", "UNKNOWN", "RECONCILING"}
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "REJECTED", "ABANDONED"}


def require_ok(response, label: str):
    if not response.ok:
        raise AssertionError(
            f"{label} failed: {json.dumps(response.body, ensure_ascii=False)}"
        )
    return response.body["data"]


class RecordingTransport:
    """Transport object the provider can call; a bare function is not a transport."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def request(self, method, url, *, headers, json, timeout, allow_redirects):
        record: dict[str, Any] = {
            "method": method,
            "url_path": url.split("?", 1)[0],
            "payload": _summarize_payload(json),
        }
        response = _requests_transport(
            method, url, headers=headers, json=json, timeout=timeout,
            allow_redirects=allow_redirects,
        )
        record["status_code"] = getattr(response, "status_code", None)
        self._records.append(record)
        return response


def make_recording_transport(records: list[dict[str, Any]]) -> RecordingTransport:
    return RecordingTransport(records)


def _summarize_payload(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, Mapping):
        return None
    summary: dict[str, Any] = {"model": body.get("model")}
    parameters = body.get("parameters")
    if isinstance(parameters, Mapping):
        summary["size"] = parameters.get("size")
        summary["n"] = parameters.get("n")
    input_block = body.get("input")
    messages = input_block.get("messages") if isinstance(input_block, Mapping) else None
    content = None
    if isinstance(messages, list) and messages and isinstance(messages[0], Mapping):
        content = messages[0].get("content")
    if isinstance(content, list):
        images = [part for part in content if isinstance(part, Mapping) and "image" in part]
        texts = [
            str(part.get("text")) for part in content
            if isinstance(part, Mapping) and isinstance(part.get("text"), str)
        ]
        summary["reference_images"] = len(images)
        summary["reference_bytes"] = sum(
            len(str(part.get("image", ""))) for part in images
        )
        if texts:
            joined = "\n".join(texts)
            summary["prompt_sha256"] = hashlib.sha256(joined.encode("utf-8")).hexdigest()
            summary["prompt_chars"] = len(joined)
    return summary


def ensure_plan(service: ApplicationService, workspace: Path, image_path: Path) -> dict:
    if (workspace / "workspace.json").is_file():
        projection = require_ok(service.get_workspace_projection(workspace), "reopen workspace")
    else:
        workspace.mkdir(parents=True, exist_ok=True)
        projection = require_ok(service.create_workspace(workspace), "create workspace")
    intake = projection.get("intake") or {}
    if not intake.get("product_name") or not intake.get("reference_images"):
        image_bytes = image_path.read_bytes()
        projection = require_ok(service.save_intake(
            workspace,
            expected_etag=projection["workspace"]["revision"],
            product_name="粗棒针织开衫毛衣",
            description="宽松落肩的长袖针织开衫，V 领单排扣，适合春秋通勤内搭。",
            selling_points=["粗棒针立体纹理", "宽松落肩版型"],
            user_intent="呈现毛衣的针织纹理与自然垂感，避免厚重臃肿效果。",
            reference_images=[ImageUpload(image_path.name, image_bytes, "primary")],
        ), "save intake")
    if not projection.get("product_brief"):
        draft = require_ok(service.generate_product_brief_draft(
            workspace, expected_etag=projection["workspace"]["revision"],
        ), "brief draft")
        projection = require_ok(service.save_product_brief(
            workspace, expected_etag=draft["workspace_revision"],
            fields=draft["product_brief"],
        ), "save brief")
    if not projection.get("plan"):
        projection = require_ok(service.generate_product_plan(
            workspace, expected_etag=projection["workspace"]["revision"],
        ), "generate plan")
    return projection


def attempts_of(projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    plan = projection.get("plan") or {}
    return [
        attempt
        for shot in plan.get("shot_specs", [])
        for attempt in shot.get("generation_attempts", [])
    ]


def abandon_unresolved(
    service: ApplicationService, workspace: Path, projection: dict, reason: str,
) -> tuple[dict, list[str]]:
    """Release active attempts that have no provider task id (human-verified abandon)."""
    abandoned: list[str] = []
    while True:
        pending = [
            item for item in attempts_of(projection)
            if item["status"] in ACTIVE_STATUSES and not item.get("provider_task_id")
        ]
        if not pending:
            return projection, abandoned
        item = pending[0]
        projection = require_ok(service.abandon_generation_attempt(
            workspace,
            expected_etag=projection["workspace"]["revision"],
            action_id=item["action_id"],
            reason=reason,
        ), "abandon unresolved attempt")
        abandoned.append(item["action_id"])


def run_generation(
    service: ApplicationService, workspace: Path, projection: dict,
    idempotency_key: str, timeout: float, poll_seconds: float,
) -> tuple[dict, list[dict[str, Any]]]:
    active_now = [item for item in attempts_of(projection) if item["status"] in ACTIVE_STATUSES]
    missing_candidates = [
        shot for shot in (projection.get("plan") or {}).get("shot_specs", [])
        if not shot.get("candidates")
    ]
    if not active_now and missing_candidates:
        projection = require_ok(service.start_generation_set(
            workspace,
            expected_etag=projection["workspace"]["revision"],
            idempotency_key=idempotency_key,
        ), "start generation set")
    deadline = time.monotonic() + timeout
    polls: list[dict[str, Any]] = []
    while True:
        active = [item for item in attempts_of(projection) if item["status"] in ACTIVE_STATUSES]
        if not active:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_seconds)
        action_ids = [item["action_id"] for item in active]
        projection = require_ok(service.reconcile_generation(
            workspace, action_ids=action_ids,
        ), "reconcile generation")
        polls.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "queried": action_ids,
            "statuses": {
                item["action_id"]: item["status"] for item in attempts_of(projection)
            },
        })
    return projection, polls


def collect(projection: Mapping[str, Any], workspace: Path) -> list[dict[str, Any]]:
    shots = []
    for shot in (projection.get("plan") or {}).get("shot_specs", []):
        candidates = []
        for candidate in shot.get("candidates", []):
            path = workspace / candidate["relative_path"]
            data = path.read_bytes() if path.is_file() else None
            candidates.append({
                "candidate_id": candidate["candidate_id"],
                "relative_path": candidate["relative_path"],
                "byte_size": len(data) if data else None,
                "width": candidate.get("width"),
                "height": candidate.get("height"),
                "sha256_verified": bool(data)
                and hashlib.sha256(data).hexdigest() == candidate["file_sha256"],
            })
        shots.append({
            "shot_id": shot["id"],
            "title": shot["title"],
            "archetype_id": shot["archetype_id"],
            "prompt_full_text": (shot.get("latest_prompt") or {}).get("full_text"),
            "attempts": [
                {
                    "action_id": item["action_id"],
                    "provider_id": item["provider_id"],
                    "model_id": item["model_id"],
                    "provider_task_id": item.get("provider_task_id"),
                    "status": item["status"],
                    "request_sha256": item["request_sha256"],
                    "reference_asset_sha256": item["reference_asset_sha256"],
                    "created_at": item["created_at"],
                    "updated_at": item["updated_at"],
                    "error": item.get("error"),
                }
                for item in shot.get("generation_attempts", [])
            ],
            "candidates": candidates,
        })
    return shots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    parser.add_argument("--image", default=str(DEFAULT_IMAGE))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=8.0)
    parser.add_argument("--idempotency-key", default="d25-real-run-02")
    parser.add_argument(
        "--abandon-unresolved", action="store_true",
        help="先人工放弃没有任务编号的未确认提交（需已核对过），再开始新的一套生成。",
    )
    parser.add_argument(
        "--fill-missing", action="store_true",
        help="只对缺候选的图片逐张发起单图生成（避免整套重发触发限流）。",
    )
    parser.add_argument("--fill-delay", type=float, default=30.0)
    parser.add_argument(
        "--verify-only", action="store_true",
        help="不发起任何新的模型调用，只复核现有工作空间每张图是否都有已验证候选并重写证据。",
    )
    args = parser.parse_args()
    workspace = Path(args.workspace)
    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"reference image missing: {image_path}", file=sys.stderr)
        return 2
    call_records: list[dict[str, Any]] = []
    transport = make_recording_transport(call_records)
    service = ApplicationService(
        image_provider_factory=lambda: create_default_image_provider(
            transport=transport, timeout=60.0,
        ),
    )
    started = time.monotonic()
    started_at = datetime.now().isoformat(timespec="seconds")
    projection = ensure_plan(service, workspace, image_path)
    abandoned: list[str] = []
    if args.abandon_unresolved:
        projection, abandoned = abandon_unresolved(
            service, workspace, projection,
            reason="D2.5 探针：已在服务端核对，这次提交没有任务编号，确认放弃后重发。",
        )
    if args.verify_only:
        polls = []
    elif args.fill_missing:
        missing = [
            shot for shot in (projection.get("plan") or {}).get("shot_specs", [])
            if not shot.get("candidates")
        ]
        polls = []
        for index, shot in enumerate(missing):
            if index:
                time.sleep(args.fill_delay)
            key = f"{args.idempotency_key}-{shot['id'][:8]}"
            projection = require_ok(service.start_shot_generation(
                workspace,
                expected_etag=projection["workspace"]["revision"],
                shot_id=shot["id"],
                idempotency_key=key,
            ), f"start single-shot generation for {shot['id']}")
            deadline = time.monotonic() + args.timeout
            while True:
                active = [
                    item for item in attempts_of(projection)
                    if item["status"] in ACTIVE_STATUSES
                ]
                if not active or time.monotonic() >= deadline:
                    break
                time.sleep(args.poll_seconds)
                projection = require_ok(service.reconcile_generation(
                    workspace, action_ids=[item["action_id"] for item in active],
                ), "reconcile single-shot generation")
                polls.append({
                    "at": datetime.now().isoformat(timespec="seconds"),
                    "queried": [item["action_id"] for item in active],
                    "statuses": {
                        item["action_id"]: item["status"] for item in attempts_of(projection)
                    },
                })
    else:
        projection, polls = run_generation(
            service, workspace, projection, args.idempotency_key, args.timeout, args.poll_seconds,
        )
    shots = collect(projection, workspace)
    duration = round(time.monotonic() - started, 1)
    complete = all(
        shot["candidates"] and all(item["sha256_verified"] for item in shot["candidates"])
        and all(item["status"] in TERMINAL_STATUSES for item in shot["attempts"])
        for shot in shots
    )
    stamp = datetime.now().strftime("%Y-%m-%d")
    mode = "verify-only" if args.verify_only else "generate"
    inherited_calls: list[dict[str, Any]] = []
    inherited_polls: list[dict[str, Any]] = []
    inherited_from: str | None = None
    if args.verify_only:
        prior_path = EVIDENCE / f"d2.5-real-generation-{stamp}.json"
        if prior_path.is_file():
            try:
                prior = json.loads(prior_path.read_text(encoding="utf-8"))
            except ValueError:
                prior = None
            if isinstance(prior, dict) and prior.get("mode", "generate") != "verify-only":
                inherited_calls = prior.get("provider_calls") or []
                inherited_polls = prior.get("polls") or []
                inherited_from = prior.get("started_at")
    payload = {
        "run": "D2.5 real whole-set generation",
        "started_at": started_at,
        "duration_seconds": duration,
        "workspace": str(workspace),
        "mode": mode,
        "complete": complete,
        "shots": shots,
        "polls": polls or inherited_polls,
        "provider_calls": call_records or inherited_calls,
        "provider_calls_measured_this_run": len(call_records),
        "provider_calls_inherited_from": inherited_from,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    raw_path = EVIDENCE / f"d2.5-real-generation-{stamp}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = [
        "# D2.5 真实整套生成 - 证据",
        "",
        "> EVIDENCE-SNAPSHOT: current · NOT-AUTHORITY",
        "> 本文件是执行证据快照，不是目标、范围或计划的正文；正文只在 docs/product-demo-goal-and-implementation-plan.md。",
        "",
        f"- 运行时间：{started_at}，耗时 {duration}s",
        f"- 工作空间：`{workspace}`（可继续用于人工选择/返工/导出）",
        f"- 原始证据：`{raw_path.name}`",
        "- 本次模式："
        + (
            "复核现有工作空间（未发起新的模型调用）"
            if args.verify_only
            else "真实生成（发起模型调用）"
        ),
        f"- 结论：{'每张图片都有已验证的真实候选' if complete else '未完成：仍有缺候选或未终态的任务'}",
        "",
        "## 逐图任务",
        "",
    ]
    for shot in shots:
        task_ids = [item["provider_task_id"] for item in shot["attempts"]]
        markdown.append(
            f"- {shot['title']}（{shot['archetype_id']}）：task_id={task_ids}，"
            f"候选 {len(shot['candidates'])} 张 "
            + "、".join(
                f"{item['relative_path']} {item['width']}x{item['height']} {item['byte_size']}B"
                for item in shot["candidates"]
            )
        )
    markdown += [
        "",
        "## 请求审计（图片 Provider 真实 HTTP 调用）",
        "",
    ]
    if inherited_from:
        markdown.append(
            f"- 以下调用记录来自 {inherited_from} 的真实生成运行；本次复核未新增调用。"
        )
        markdown.append("")
    for record in payload["provider_calls"]:
        markdown.append(
            f"- {record['method']} {record['url_path']} -> {record['status_code']} "
            f"`{json.dumps(record['payload'], ensure_ascii=False)}`"
        )
    markdown += [
        "",
        "## 边界",
        "",
        "- 成本记录仅含调用次数与耗时；百炼计费单价未在此处核验。",
        "- 画质与可交付性由人工审核与后续选择/返工阶段决定，不由本脚本评价。",
        "",
    ]
    md_path = EVIDENCE / f"d2.5-real-generation-{stamp}.md"
    md_path.write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({
        "complete": complete,
        "duration_seconds": duration,
        "shots": [
            {
                "title": shot["title"], "attempts": len(shot["attempts"]),
                "statuses": [item["status"] for item in shot["attempts"]],
                "candidates": len(shot["candidates"]),
            }
            for shot in shots
        ],
        "provider_calls": len(call_records),
        "provider_calls_in_evidence": len(payload["provider_calls"]),
        "mode": mode,
        "evidence": raw_path.name,
    }, ensure_ascii=False, indent=2))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
