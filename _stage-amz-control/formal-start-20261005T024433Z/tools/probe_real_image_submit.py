#!/usr/bin/env python
"""D2.5 submit-path probe: one real submit with raw response capture.

Why this exists: the first D2.5 run (2026-09-28 21:09 +08) created five UNKNOWN
attempts with no provider task id - the submit call did not deliver a
reconcilable task id back to the product. The frozen contract keeps an UNKNOWN
without task id in manual handling and forbids automatic resubmission, so before
spending another real generation set this probe records, for one call:

  - the exact request shape (model, ordered reference count, prompt hash, size);
  - real elapsed seconds, HTTP status, response headers and body (never the key);
  - whether a task id came back, and the first query result if it did.

It never retries and never downloads. Evidence lands in evals/product-demo/.

Usage:
  python tools/probe_real_image_submit.py [--timeout 180] [--no-query]
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

from src.providers.dashscope_image import _requests_transport, create_default_image_provider
from src.providers.image import ImageReference

EVIDENCE = ROOT / "evals" / "product-demo"
DEFAULT_IMAGE = Path(
    r"E:\workbuddy_workspace\2026-09-20-16-38-19\ecommerce-skills-main"
    r"\docs\batch-image\sku-a-sweater.jpg"
)
DEFAULT_PROMPT_RECORD = (
    ROOT / "_working" / "amz-listing-kit-product-demo" / "real-run-01"
    / "workspace" / "shots" / "shot_1ce3ff4b08624310" / "prompts" / "prompt-v001.json"
)
MAX_BODY_CHARS = 4000
SAFE_HEADERS = {
    "x-request-id", "request-id", "x-dashscope-request-id", "content-type", "date", "server",
}


def summarize_payload(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, Mapping):
        return None
    summary: dict[str, Any] = {"model": body.get("model")}
    parameters = body.get("parameters")
    if isinstance(parameters, Mapping):
        summary["size"] = parameters.get("size")
        summary["n"] = parameters.get("n")
        summary["prompt_extend"] = parameters.get("prompt_extend")
        summary["watermark"] = parameters.get("watermark")
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
        summary["reference_bytes"] = sum(len(str(part.get("image", ""))) for part in images)
        if texts:
            joined = "\n".join(texts)
            summary["prompt_sha256"] = hashlib.sha256(joined.encode("utf-8")).hexdigest()
            summary["prompt_chars"] = len(joined)
    return summary


def make_recording_transport(records: list[dict[str, Any]]):
    def transport(method, url, *, headers, json, timeout, allow_redirects):
        started = time.monotonic()
        record: dict[str, Any] = {
            "method": method,
            "url_path": url.split("?", 1)[0],
            "requested_timeout_s": timeout,
            "payload": summarize_payload(json),
        }
        try:
            response = _requests_transport(
                method, url, headers=headers, json=json, timeout=timeout,
                allow_redirects=allow_redirects,
            )
        except Exception as exc:  # noqa: BLE001 - record, then re-raise
            record["elapsed_s"] = round(time.monotonic() - started, 2)
            record["transport_error"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
            raise
        record["elapsed_s"] = round(time.monotonic() - started, 2)
        record["status_code"] = getattr(response, "status_code", None)
        response_headers = getattr(response, "headers", {}) or {}
        if isinstance(response_headers, Mapping):
            record["response_headers"] = {
                str(name).lower(): str(value) for name, value in response_headers.items()
                if str(name).lower() in SAFE_HEADERS
            }
        try:
            text = response.text
        except Exception:  # noqa: BLE001
            text = ""
        record["response_body"] = (text or "")[:MAX_BODY_CHARS]
        records.append(record)
        return response

    return transport


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=str(DEFAULT_IMAGE))
    parser.add_argument("--prompt-record", default=str(DEFAULT_PROMPT_RECORD))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--query-wait", type=float, default=3.0)
    parser.add_argument("--no-query", action="store_true")
    args = parser.parse_args()

    image_path = Path(args.image)
    prompt_record_path = Path(args.prompt_record)
    if not image_path.is_file():
        print(f"reference image missing: {image_path}", file=sys.stderr)
        return 2
    prompt_record = json.loads(prompt_record_path.read_text(encoding="utf-8"))
    prompt_text = str(prompt_record.get("full_text") or "")
    if not prompt_text.strip():
        print(f"prompt record has no full_text: {prompt_record_path}", file=sys.stderr)
        return 2

    image_bytes = image_path.read_bytes()
    reference = ImageReference(hashlib.sha256(image_bytes).hexdigest(), "image/jpeg", image_bytes)
    records: list[dict[str, Any]] = []
    provider = create_default_image_provider(
        transport=make_recording_transport(records), timeout=args.timeout,
    )

    started_at = datetime.now().isoformat(timespec="seconds")
    started = time.monotonic()
    outcome: dict[str, Any] = {"provider": provider.provider_id, "model": provider.model_id}
    task_id: str | None = None
    try:
        task = provider.submit(prompt_text, [reference], size="1344*1344")
        outcome.update({
            "status": task.status,
            "task_id": task.task_id,
            "request_id": task.request_id,
            "error": task.error,
            "result_urls": list(task.result_urls),
        })
        task_id = task.task_id
    except Exception as exc:  # noqa: BLE001
        outcome.update({"raised": f"{type(exc).__name__}: {exc}"})
    submit_elapsed = round(time.monotonic() - started, 2)

    query: dict[str, Any] | None = None
    if task_id and not args.no_query:
        time.sleep(args.query_wait)
        try:
            queried = provider.query_task(task_id)
            query = {
                "status": queried.status,
                "task_id": queried.task_id,
                "error": queried.error,
                "result_urls": list(queried.result_urls),
                "request_id": queried.request_id,
            }
        except Exception as exc:  # noqa: BLE001
            query = {"raised": f"{type(exc).__name__}: {exc}"}

    stamp = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "probe": "D2.5 submit-path probe",
        "started_at": started_at,
        "submit_elapsed_s": submit_elapsed,
        "timeout_s": args.timeout,
        "reference_image": {
            "path": str(image_path), "sha256": reference.sha256, "bytes": len(image_bytes),
        },
        "prompt_record": str(prompt_record_path),
        "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        "outcome": outcome,
        "first_query": query,
        "provider_calls": records,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    raw_path = EVIDENCE / f"d2.5-submit-probe-{stamp}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "submit_elapsed_s": submit_elapsed,
        "status": outcome.get("status"),
        "task_id": task_id,
        "first_query_status": (query or {}).get("status"),
        "provider_calls": [
            {key: call.get(key) for key in
             ("method", "url_path", "status_code", "elapsed_s", "transport_error")}
            for call in records
        ],
        "response_body_head": (records[0].get("response_body") or "")[:600] if records else None,
        "evidence": raw_path.name,
    }, ensure_ascii=False, indent=2))
    return 0 if task_id else 1


if __name__ == "__main__":
    raise SystemExit(main())
