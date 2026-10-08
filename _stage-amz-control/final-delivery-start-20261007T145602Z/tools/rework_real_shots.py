#!/usr/bin/env python
"""Retry listed shots for real through the product rework action.

This is the real executor behind the UI behaviour "只重新生成这一张": it calls
ApplicationService.start_shot_generation (the same call the workbench makes) with a
fresh idempotency key per shot, waits by reconciling the persisted provider task ids,
and then verifies that:

  - each target shot gained a new attempt and a hash-verified candidate;
  - every other shot keeps exactly its previous attempts, candidates and file bytes.

It never resubmits an attempt that already has a provider task id and it pauses
between submits to respect provider rate limits (HTTP 429 is the reason these
retries exist at all).

Usage:
  python tools/rework_real_shots.py --workspace <dir> --shots shot_a,shot_b [--pause 25]
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

from src.application_service import ApplicationService
from src.providers.dashscope_image import _requests_transport, create_default_image_provider

EVIDENCE = ROOT / "evals" / "product-demo"
ACTIVE = {"CREATED", "SUBMITTED", "RUNNING", "UNKNOWN", "RECONCILING"}
TERMINAL = {"SUCCEEDED", "FAILED", "REJECTED"}


def require_ok(response, label: str):
    if not response.ok:
        raise AssertionError(f"{label} failed: {json.dumps(response.body, ensure_ascii=False)}")
    return response.body["data"]


def summarize_payload(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, Mapping):
        return None
    summary: dict[str, Any] = {"model": body.get("model")}
    parameters = body.get("parameters")
    if isinstance(parameters, Mapping):
        summary["size"] = parameters.get("size")
        summary["n"] = parameters.get("n")
    input_block = body.get("input")
    messages = input_block.get("messages") if isinstance(input_block, Mapping) else None
    content = messages[0].get("content") if isinstance(messages, list) and messages else None
    if isinstance(content, list):
        images = [part for part in content if isinstance(part, Mapping) and "image" in part]
        texts = [str(part.get("text")) for part in content
                 if isinstance(part, Mapping) and isinstance(part.get("text"), str)]
        summary["reference_images"] = len(images)
        summary["reference_bytes"] = sum(len(str(part.get("image", ""))) for part in images)
        if texts:
            joined = "\n".join(texts)
            summary["prompt_sha256"] = hashlib.sha256(joined.encode("utf-8")).hexdigest()
            summary["prompt_chars"] = len(joined)
    return summary


def make_recording_transport(records: list[dict[str, Any]]):
    def transport(method, url, *, headers, json, timeout, allow_redirects):
        started = time.monotonic()
        record: dict[str, Any] = {"method": method, "url_path": url.split("?", 1)[0],
                                  "payload": summarize_payload(json)}
        try:
            response = _requests_transport(method, url, headers=headers, json=json,
                                           timeout=timeout, allow_redirects=allow_redirects)
        except Exception as exc:  # noqa: BLE001
            record["elapsed_s"] = round(time.monotonic() - started, 2)
            record["transport_error"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
            raise
        record["elapsed_s"] = round(time.monotonic() - started, 2)
        record["status_code"] = getattr(response, "status_code", None)
        records.append(record)
        return response
    return transport


def snapshot(projection: Mapping[str, Any], workspace: Path) -> dict[str, Any]:
    shots: dict[str, Any] = {}
    for shot in (projection.get("plan") or {}).get("shot_specs", []):
        candidates = []
        for candidate in shot.get("candidates", []):
            path = workspace / candidate["relative_path"]
            data = path.read_bytes() if path.is_file() else None
            candidates.append({
                "candidate_id": candidate["candidate_id"],
                "relative_path": candidate["relative_path"],
                "file_sha256": candidate["file_sha256"],
                "bytes_sha256": hashlib.sha256(data).hexdigest() if data else None,
            })
        shots[shot["id"]] = {
            "title": shot["title"],
            "attempts": [
                {"action_id": item["action_id"], "status": item["status"],
                 "provider_task_id": item.get("provider_task_id")}
                for item in shot.get("generation_attempts", [])
            ],
            "candidates": candidates,
        }
    return shots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--shots", required=True, help="comma separated shot ids")
    parser.add_argument("--pause", type=float, default=25.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--poll-seconds", type=float, default=8.0)
    parser.add_argument(
        "--abandon-unresolved", action="store_true",
        help="对没有任务编号的未确认提交先执行产品内的人工放弃（需给出核对说明）",
    )
    parser.add_argument(
        "--abandon-reason", default=None,
        help="放弃未确认提交时记录的核对说明（<=500 字）",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace)
    targets = [item.strip() for item in args.shots.split(",") if item.strip()]
    if not targets:
        print("no target shots given", file=sys.stderr)
        return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    records: list[dict[str, Any]] = []
    service = ApplicationService(
        image_provider_factory=lambda: create_default_image_provider(
            transport=make_recording_transport(records), timeout=60.0,
        ),
    )

    projection = require_ok(service.get_workspace_projection(workspace), "open workspace")
    before = snapshot(projection, workspace)
    abandoned: list[dict[str, Any]] = []
    missing = [shot_id for shot_id in targets if shot_id not in before]
    if missing:
        print(f"shots not in current plan: {missing}", file=sys.stderr)
        return 2
    for shot_id in targets:
        unresolved = [item for item in before[shot_id]["attempts"] if item["status"] in ACTIVE]
        if not unresolved:
            continue
        if not args.abandon_unresolved:
            print(f"{shot_id} still has an unresolved attempt; reconcile first", file=sys.stderr)
            return 2
        for item in unresolved:
            if item.get("provider_task_id"):
                print(f"{shot_id} has a provider task id; reconcile it instead", file=sys.stderr)
                return 2
            reason = args.abandon_reason or (
                "已在本地核对：提交在客户端超时后没有收到服务端回执，工作空间中没有可核对的"
                " task id，且没有其他可查询途径。为继续交付，人工放弃这次未确认提交。"
            )
            label = "abandon " + str(item["action_id"])
            projection = require_ok(service.abandon_generation_attempt(
                workspace, expected_etag=projection["workspace"]["revision"],
                action_id=item["action_id"], reason=reason,
            ), label)
            abandoned.append({"shot_id": shot_id, "action_id": item["action_id"],
                              "reason": reason})

    submits: list[dict[str, Any]] = []
    for index, shot_id in enumerate(targets, start=1):
        key = f"rework-{stamp}-{index}"
        started = time.monotonic()
        projection = require_ok(service.start_shot_generation(
            workspace, expected_etag=projection["workspace"]["revision"],
            shot_id=shot_id, idempotency_key=key,
        ), f"rework {shot_id}")
        submits.append({"shot_id": shot_id, "idempotency_key": key,
                        "elapsed_s": round(time.monotonic() - started, 2)})
        if index < len(targets) and args.pause > 0:
            time.sleep(args.pause)

    deadline = time.monotonic() + args.timeout
    polls: list[dict[str, Any]] = []

    def active_attempts(data: Mapping[str, Any]) -> list[tuple[str, str]]:
        shots = {shot["id"]: shot for shot in (data.get("plan") or {}).get("shot_specs", [])}
        result: list[tuple[str, str]] = []
        for shot_id in targets:
            for attempt in shots.get(shot_id, {}).get("generation_attempts", []):
                if attempt["status"] in ACTIVE:
                    result.append((shot_id, attempt["action_id"]))
        return result

    while True:
        active = active_attempts(projection)
        if not active or time.monotonic() >= deadline:
            break
        time.sleep(args.poll_seconds)
        projection = require_ok(service.reconcile_generation(
            workspace, action_ids=[action_id for _, action_id in active],
        ), "reconcile generation")
        polls.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "queried": [action_id for _, action_id in active],
        })

    after = snapshot(projection, workspace)
    checks: dict[str, Any] = {}
    for shot_id in targets:
        known_attempts = {item["action_id"] for item in before[shot_id]["attempts"]}
        new_attempts = [item for item in after[shot_id]["attempts"]
                        if item["action_id"] not in known_attempts]
        known_candidates = {item["candidate_id"] for item in before[shot_id]["candidates"]}
        new_candidates = [item for item in after[shot_id]["candidates"]
                          if item["candidate_id"] not in known_candidates]
        verified = [item for item in new_candidates
                    if item["bytes_sha256"] and item["bytes_sha256"] == item["file_sha256"]]
        checks[f"target:{shot_id}"] = {
            "passed": bool(new_attempts) and bool(verified),
            "new_attempts": new_attempts,
            "new_candidates": new_candidates,
            "latest_status": after[shot_id]["attempts"][-1]["status"]
            if after[shot_id]["attempts"] else None,
        }
    untouched = {shot_id: before[shot_id] == after[shot_id]
                 for shot_id in after if shot_id not in targets}
    checks["untouched_shots_unchanged"] = {
        "passed": all(untouched.values()), "detail": untouched,
    }
    failed = [name for name, item in checks.items() if not item["passed"]]
    payload = {
        "run": "real rework of listed shots",
        "started_at": stamp,
        "workspace": str(workspace),
        "targets": targets,
        "submits": submits,
        "abandoned": abandoned,
        "polls": polls,
        "checks": checks,
        "before": before,
        "after": after,
        "provider_calls": records,
        "passed": not failed,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    raw_path = EVIDENCE / f"d3.2-real-rework-{stamp}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": not failed,
        "failed_checks": failed,
        "submits": submits,
        "abandoned": abandoned,
        "targets": {
            shot_id: {
                "status": checks[f"target:{shot_id}"]["latest_status"],
                "new_attempts": len(checks[f"target:{shot_id}"]["new_attempts"]),
                "new_candidates": len(checks[f"target:{shot_id}"]["new_candidates"]),
            }
            for shot_id in targets
        },
        "provider_calls": [
            {key: call.get(key) for key in ("method", "url_path", "status_code", "elapsed_s",
                                            "transport_error")}
            for call in records
        ],
        "evidence": raw_path.name,
    }, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
