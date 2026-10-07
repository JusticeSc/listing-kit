#!/usr/bin/env python
"""D3.1-D3.5 on one real workspace: select -> edit prompt -> rework -> select -> export.

Runs against the real DashScope image provider (no mocks). The run never
regenerates the whole set: it reworks only the shots whose compiled prompt
fought the reference photo, keeps every earlier candidate, then exports the
current selection and re-verifies the delivered bytes against the manifest.

Every image-provider HTTP call is recorded (model, size, ordered reference
image count, prompt hash) without the API key or image bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
for entry in (str(ROOT), str(TOOLS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from src.application_service import ApplicationService
from src.providers.dashscope_image import create_default_image_provider
from run_d2_5_real_generation import make_recording_transport

EVIDENCE = ROOT / "evals" / "product-demo"
DEFAULT_WORKSPACE = (
    ROOT / "_working" / "amz-listing-kit-product-demo" / "real-run-01" / "workspace"
)
ACTIVE_STATUSES = {"CREATED", "SUBMITTED", "RUNNING", "UNKNOWN", "RECONCILING"}

# The operator fix that naming and description text must never outrank the photo.
REFERENCE_AUTHORITY_FIX = (
    "参考图中的商品结构（领型、门襟、纽扣、口袋、图案、衣长）是唯一事实来源。"
    "文字描述与参考图冲突时，以参考图为准；不得根据文字添加参考图中不存在的"
    "门襟、纽扣或领型。画面中的商品必须与参考图是同一件商品。"
)


def require_ok(response, label: str):
    if not response.ok:
        raise AssertionError(
            f"{label} failed: {json.dumps(response.body, ensure_ascii=False)}"
        )
    return response.body["data"]


def shots_of(projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list((projection.get("plan") or {}).get("shot_specs", []))


def attempts_of(shot: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(shot.get("generation_attempts") or [])


def shot_snapshot(projection: Mapping[str, Any]) -> dict[str, Any]:
    return {
        shot["id"]: {
            "title": shot["title"],
            "archetype_id": shot["archetype_id"],
            "prompt_version": (shot.get("latest_prompt") or {}).get("version"),
            "prompt_full_text": (shot.get("latest_prompt") or {}).get("full_text"),
            "candidates": [item["candidate_id"] for item in shot.get("candidates", [])],
            "attempts": [item["action_id"] for item in attempts_of(shot)],
        }
        for shot in shots_of(projection)
    }


def newest_candidate(shot: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = list(shot.get("candidates") or [])
    if not candidates:
        raise AssertionError(f"shot {shot['id']} has no candidate to choose")
    return candidates[-1]


def candidate_files_intact(workspace: Path, shot: Mapping[str, Any]) -> bool | None:
    """True when every listed candidate file still hashes to its record."""
    candidates = list(shot.get("candidates") or [])
    if not candidates:
        return None
    for candidate in candidates:
        path = workspace / candidate["relative_path"]
        if not path.is_file():
            return False
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = candidate.get("file_sha256") or candidate.get("candidate_id")
        if digest != expected:
            return False
    return True


def choices_from(projection: Mapping[str, Any]) -> list[dict[str, str]]:
    """Pick the newest candidate of every shot - the operator confirms each one."""
    return [
        {"shot_id": shot["id"], "candidate_sha256": newest_candidate(shot)["candidate_id"]}
        for shot in shots_of(projection)
    ]


def wait_for(service, workspace, projection, action_ids, reconcile_log, timeout, poll_seconds):
    """Reconcile the given actions until none of them is active any more."""
    deadline = time.monotonic() + timeout
    while True:
        active = [
            item for shot in shots_of(projection) for item in attempts_of(shot)
            if item["action_id"] in action_ids and item["status"] in ACTIVE_STATUSES
        ]
        if not active or time.monotonic() >= deadline:
            return projection
        time.sleep(poll_seconds)
        projection = require_ok(service.reconcile_generation(
            workspace, action_ids=[item["action_id"] for item in active],
        ), "reconcile rework")
        reconcile_log.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "queried": [item["action_id"] for item in active],
        })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=8.0)
    parser.add_argument("--rework-delay", type=float, default=30.0)
    parser.add_argument("--idempotency-prefix", default="d3-real-loop-01")
    parser.add_argument(
        "--rework-archetypes", default="lifestyle,detail",
        help="需要按参考图权威规则返工的图型；留空表示不返工，只跑选择与导出。",
    )
    parser.add_argument("--skip-rework", action="store_true")
    parser.add_argument(
        "--edits", default=None,
        help="操作员改写提示词的 JSON 文件：{\"shots\":[{\"shot_id\":..,\"replace\":[[旧,新],..],\"reason\":..}]}",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace)
    targets = [
        item.strip() for item in args.rework_archetypes.split(",") if item.strip()
    ]
    if args.edits:
        spec_file = json.loads(Path(args.edits).read_text(encoding="utf-8"))
        specs: list[dict[str, Any]] = []
        for entry in spec_file.get("shots") or []:
            specs.append({
                "shot_id": entry.get("shot_id"),
                "archetype_id": None,
                "replacements": [tuple(pair) for pair in (entry.get("replace") or [])],
                "reason": entry.get("reason"),
            })
    else:
        specs = [
            {"shot_id": None, "archetype_id": archetype, "replacements": [], "reason": None}
            for archetype in targets
        ]
    call_records: list[dict[str, Any]] = []
    service = ApplicationService(
        image_provider_factory=lambda: create_default_image_provider(
            transport=make_recording_transport(call_records), timeout=60.0,
        ),
    )
    started = time.monotonic()
    started_at = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y-%m-%d")
    raw_path = EVIDENCE / f"d3.1-d3.5-real-loop-{stamp}.json"
    prior_rework: dict[str, dict[str, Any]] = {}
    prior_started_at: str | None = None
    prior_calls: list[dict[str, Any]] = []
    prior_reconcile: list[dict[str, Any]] = []
    if raw_path.is_file():
        try:
            prior = json.loads(raw_path.read_text(encoding="utf-8"))
        except ValueError:
            prior = None
        if isinstance(prior, dict):
            for item in prior.get("reworked") or []:
                if isinstance(item, dict) and item.get("archetype_id"):
                    prior_rework[str(item["archetype_id"])] = item
            if prior_rework:
                prior_started_at = prior.get("started_at")
            prior_calls = [
                item for item in (prior.get("provider_calls") or []) if isinstance(item, dict)
            ]
            prior_reconcile = [
                item for item in (prior.get("reconcile_log") or []) if isinstance(item, dict)
            ]
    projection = require_ok(service.get_workspace_projection(workspace), "open workspace")
    baseline = shot_snapshot(projection)
    steps: list[dict[str, Any]] = []
    reconcile_log: list[dict[str, Any]] = []

    # D3.1 - first human selection of the current candidates.
    projection = require_ok(service.save_selection(
        workspace,
        expected_etag=projection["workspace"]["revision"],
        choices=choices_from(projection),
    ), "save initial selection")
    first_selection = projection["selection"]
    steps.append({
        "id": "D3.1",
        "action": "save_selection",
        "selection_id": first_selection["id"],
        "version": first_selection["version"],
        "chosen": {
            item["shot"]["id"]: item["candidate_sha256"]
            for item in first_selection["choices"]
        },
    })

    reworked: list[dict[str, Any]] = []
    if not args.skip_rework:
        for index, spec in enumerate(specs):
            archetype = spec.get("archetype_id")
            shot = next(
                (
                    item for item in shots_of(projection)
                    if (spec.get("shot_id") and item["id"] == spec["shot_id"])
                    or (archetype and item["archetype_id"] == archetype)
                ),
                None,
            )
            archetype = shot["archetype_id"] if shot else archetype
            if shot is None:
                raise AssertionError(f"no shot matching {spec}")
            before = shot_snapshot(projection)[shot["id"]]
            latest_prompt = shot.get("latest_prompt") or {}
            if not latest_prompt:
                raise AssertionError(f"shot {shot['id']} has no compiled prompt")
            original_text = str(latest_prompt["full_text"])
            already_fixed = original_text.startswith(REFERENCE_AUTHORITY_FIX)
            edited_text = original_text
            for old, new in spec.get("replacements") or []:
                if old not in edited_text:
                    raise AssertionError(
                        f"shot {shot['id']} edit target not found in the compiled prompt: {old!r}"
                    )
                edited_text = edited_text.replace(old, new)
            if spec.get("replacements") and not already_fixed:
                edited_text = REFERENCE_AUTHORITY_FIX + "\n\n" + edited_text.strip()
            if already_fixed and not spec.get("replacements"):
                # The reference-authority fix is already applied; do not spend
                # another provider call, carry the recorded rework forward.
                carried = prior_rework.get(archetype)
                if carried is None:
                    carried = {
                        "shot_id": shot["id"],
                        "archetype_id": archetype,
                        "prompt_version_before": latest_prompt["version"] - 1,
                        "prompt_version_after": latest_prompt["version"],
                        "attempts": [
                            {
                                "action_id": item["action_id"],
                                "provider_task_id": item.get("provider_task_id"),
                                "status": item["status"],
                                "error": item.get("error"),
                            }
                            for item in attempts_of(shot)
                        ],
                        "candidates_before": None,
                        "candidates_after": len(shot.get("candidates") or []),
                        "old_candidate_kept": candidate_files_intact(workspace, shot),
                        "new_candidate": (shot.get("candidates") or [{}])[-1].get("candidate_id"),
                        "source": "workspace state at this run",
                    }
                else:
                    carried = dict(carried)
                    carried["source"] = f"recorded rework from {prior_started_at}"
                reworked.append(carried)
                steps.append({
                    "id": "D3.2",
                    "action": "already fixed - no new provider call",
                    "archetype": archetype,
                    "result": carried,
                })
                continue
            edited = edited_text
            projection = require_ok(service.save_prompt_edit(
                workspace,
                expected_etag=projection["workspace"]["revision"],
                shot_id=shot["id"],
                expected_prompt_version=latest_prompt["version"],
                full_text=edited,
                reason=spec.get("reason")
                or "参考图为准：文字里的领型/门襟与参考图冲突，返工并锁定参考图结构。",
            ), "save prompt edit")
            edited_shot = next(
                item for item in shots_of(projection) if item["id"] == shot["id"]
            )
            new_version = edited_shot["latest_prompt"]["version"]
            assert new_version == before["prompt_version"] + 1, "prompt version did not advance"
            assert edited_shot["latest_prompt"].get("edit_reason"), "edit reason not persisted"

            if index:
                time.sleep(args.rework_delay)
            projection = require_ok(service.start_shot_generation(
                workspace,
                expected_etag=projection["workspace"]["revision"],
                shot_id=shot["id"],
                idempotency_key=f"{args.idempotency_prefix}-{shot['id'][:8]}",
            ), f"start rework for {shot['id']}")
            fresh = next(item for item in shots_of(projection) if item["id"] == shot["id"])
            new_actions = [
                item["action_id"] for item in attempts_of(fresh)
                if item["action_id"] not in before["attempts"]
            ]
            assert new_actions, "rework did not create an attempt"
            projection = wait_for(
                service, workspace, projection, set(new_actions), reconcile_log,
                args.timeout, args.poll_seconds,
            )
            after = shot_snapshot(projection)[shot["id"]]
            new_attempts = [item for item in attempts_of(
                next(item for item in shots_of(projection) if item["id"] == shot["id"])
            ) if item["action_id"] in new_actions]
            reworked.append({
                "shot_id": shot["id"],
                "archetype_id": archetype,
                "prompt_version_before": before["prompt_version"],
                "prompt_version_after": after["prompt_version"],
                "attempts": [
                    {
                        "action_id": item["action_id"],
                        "provider_task_id": item.get("provider_task_id"),
                        "status": item["status"],
                        "error": item.get("error"),
                    }
                    for item in new_attempts
                ],
                "candidates_before": len(before["candidates"]),
                "candidates_after": len(after["candidates"]),
                "old_candidate_kept": all(
                    item in after["candidates"] for item in before["candidates"]
                ),
                "new_candidate": after["candidates"][-1]
                if len(after["candidates"]) > len(before["candidates"]) else None,
                "source": f"live rework at {started_at}",
            })
            steps.append({
                "id": "D3.2",
                "action": "save_prompt_edit + start_shot_generation",
                "archetype": archetype,
                "result": reworked[-1],
            })

    untouched = [
        shot_id for shot_id, before in baseline.items()
        if not any(item["shot_id"] == shot_id for item in reworked)
        and shot_snapshot(projection)[shot_id]["candidates"] != before["candidates"]
    ]
    assert not untouched, f"unrelated shots changed during rework: {untouched}"

    # Keep earlier recorded reworks in the same evidence file instead of losing
    # them when a later run only touches one shot.
    touched = {item["shot_id"] for item in reworked}
    for archetype, item in prior_rework.items():
        if item.get("shot_id") in touched:
            continue
        shot = next(
            (entry for entry in shots_of(projection) if entry["archetype_id"] == archetype),
            None,
        )
        if shot is None:
            continue
        carried = dict(item)
        carried["candidates_after"] = len(shot.get("candidates") or [])
        carried["source"] = (
            f"recorded rework from {prior_started_at}; not re-run in this run"
        )
        reworked.append(carried)

    # D3.1 again - confirm the reworked candidates and keep the untouched shots.
    projection = require_ok(service.save_selection(
        workspace,
        expected_etag=projection["workspace"]["revision"],
        choices=choices_from(projection),
    ), "save final selection")
    final_selection = projection["selection"]
    steps.append({
        "id": "D3.1b",
        "action": "save_selection",
        "selection_id": final_selection["id"],
        "version": final_selection["version"],
        "chosen": {
            item["shot"]["id"]: item["candidate_sha256"]
            for item in final_selection["choices"]
        },
    })

    # D3.3 - deterministic platform/file report for the current selection.
    from src.platform_checks import run_export_checks

    report = run_export_checks(workspace)
    steps.append({
        "id": "D3.3",
        "action": "run_export_checks",
        "profile_id": (report.get("profile") or {}).get("profile_id"),
        "hard_failures": report.get("hard_failures"),
        "checks": report.get("checks"),
        "manual_notes": report.get("manual_notes"),
    })

    # D3.4 - deliverable folder, then verify the bytes we just shipped.
    projection = require_ok(service.export_selection(
        workspace, expected_etag=projection["workspace"]["revision"],
    ), "export selection")
    export = projection["export"]
    delivered = []
    for item in export["files"]:
        path = workspace / item["relative_path"]
        data = path.read_bytes() if path.is_file() else b""
        delivered.append({
            "relative_path": item["relative_path"],
            "byte_size": len(data),
            "sha256_matches_candidate": hashlib.sha256(data).hexdigest() == item["file_sha256"],
        })
    manifest_path = workspace / export["manifest_relative_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    readme_path = manifest_path.parent / "README.md"
    assert all(item["sha256_matches_candidate"] for item in delivered), "exported bytes drifted"
    assert manifest["export"]["id"] == export["id"], "manifest does not describe this export"
    assert readme_path.is_file(), "README missing from the deliverable folder"
    steps.append({
        "id": "D3.4",
        "action": "export_selection",
        "export_id": export["id"],
        "export_version": export["version"],
        "relative_path": export["relative_path"],
        "manifest": export["manifest_relative_path"],
        "readme": str(readme_path.relative_to(workspace)),
        "files": delivered,
    })

    duration = round(time.monotonic() - started, 1)
    stamp = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "run": "D3.1-D3.5 real closed loop",
        "started_at": started_at,
        "duration_seconds": duration,
        "workspace": str(workspace),
        "rework_targets": targets,
        "steps": steps,
        "reworked": reworked,
        "unrelated_shots_untouched": not untouched,
        "provider_calls": call_records,
        "provider_call_count": len(call_records),
        "provider_calls_recorded_earlier": prior_calls,
        "provider_call_count_total": len(call_records) + len(prior_calls),
        "reconcile_log": reconcile_log,
        "reconcile_log_recorded_earlier": prior_reconcile,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    raw_path = EVIDENCE / f"d3.1-d3.5-real-loop-{stamp}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = [
        "# D3.1-D3.5 真实闭环 - 证据",
        "",
        "> EVIDENCE-SNAPSHOT: current · NOT-AUTHORITY",
        "> 本文件是执行证据快照，不是目标、范围或计划的正文；正文只在 docs/product-demo-goal-and-implementation-plan.md。",
        "",
        f"- 运行时间：{started_at}，耗时 {duration}s",
        f"- 工作空间：`{workspace}`",
        f"- 原始证据：`{raw_path.name}`",
        f"- 真实图片 Provider 调用：{len(call_records)} 次（提交与轮询均记录）",
        f"- 未受影响图片保持原候选：{'是' if not untouched else '否'}",
        "",
        "## 逐图返工",
        "",
    ]
    for item in reworked:
        markdown.append(
            f"- {item['archetype_id']}：prompt v{item['prompt_version_before']}→"
            f"v{item['prompt_version_after']}，候选 {item['candidates_before']}→"
            f"{item['candidates_after']}，旧候选保留={item['old_candidate_kept']}，"
            f"新候选={item['new_candidate']}"
        )
        markdown.append(f"  - 来源：{item.get('source')}")
        for attempt in item["attempts"]:
            markdown.append(
                f"  - 返工任务 {attempt['provider_task_id']} → {attempt['status']}"
            )
    markdown += ["", "## 交付包", ""]
    d34 = next(item for item in steps if item["id"] == "D3.4")
    markdown.append(f"- 目录：`{d34['relative_path']}`，清单 `{d34['manifest']}`，`README.md` 同目录")
    for item in d34["files"]:
        markdown.append(f"  - {item['relative_path']} {item['byte_size']}B 哈希核对通过")
    markdown += ["", "## 请求审计（图片 Provider 真实 HTTP 调用）", ""]
    for record in call_records:
        markdown.append(
            f"- {record['method']} {record['url_path']} -> {record['status_code']} "
            f"`{json.dumps(record['payload'], ensure_ascii=False)}`"
        )
    markdown += [
        "",
        "## 边界",
        "",
        "- 本次返工由人工判断驱动：参考图与文字冲突时以参考图为准，属于人工决定，不由程序自动判定。",
        "- 图片是否可用于上架仍由人工审核，本证据只说明链路、版本、哈希与调用真实发生。",
        "- 成本只记录调用次数与耗时；百炼计费单价未在此核验。",
        "",
    ]
    md_path = EVIDENCE / f"d3.1-d3.5-real-loop-{stamp}.md"
    md_path.write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({
        "steps": [item["id"] for item in steps],
        "reworked": [
            {
                "archetype": item["archetype_id"],
                "statuses": [attempt["status"] for attempt in item["attempts"]],
                "candidates": item["candidates_after"],
                "old_candidate_kept": item["old_candidate_kept"],
            }
            for item in reworked
        ],
        "export_id": d34["export_id"],
        "export_files": len(d34["files"]),
        "provider_calls": len(call_records),
        "evidence": raw_path.name,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
