#!/usr/bin/env python
"""Real full loop through the shipped product UI, with the real image model.

Blank workspace -> product intake (real reference photo) -> product brief ->
dynamic plan -> one-click whole-set generation -> per-shot retry for anything
the provider refused -> single-shot prompt edit + rework -> per-image selection
-> export -> byte-for-byte verification of the delivered folder through the
product's own HTTP endpoints.

Nothing in this run goes through the command line on the product's behalf: the
only non-UI call is the workspace-folder choice (an OS dialog in the desktop
flow), which is posted exactly as the page does after that dialog returns.

Usage:
  uv run --locked python tools/run_real_ui_full_loop.py --base http://127.0.0.1:8787 --workspace-dir DIR --image PATH
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SESSION_KEY = "amzListingKit.productV1.workspaceDirectory"
EVIDENCE = ROOT / "evals" / "product-demo"
TERMINAL = {"SUCCEEDED", "FAILED", "REJECTED", "ABANDONED"}


class StepLog(list):
    """Step list that persists the report on every append.

    A real run can fail halfway through; the evidence file must still show every
    step that happened before the failure instead of disappearing with the traceback.
    """

    def __init__(self, report: dict, path: Path) -> None:
        super().__init__()
        self._report = report
        self._path = path

    def append(self, item) -> None:  # type: ignore[override]
        super().append(item)
        self._path.write_text(
            json.dumps(self._report, ensure_ascii=False, indent=2), encoding="utf-8",
        )


def projection(page, directory: str) -> dict:
    script = """
    async (directory) => {
      const response = await fetch("/api/workspace?directory=" + encodeURIComponent(directory));
      const payload = await response.json();
      if (!payload.ok) throw new Error(JSON.stringify(payload));
      return payload.data;
    }
    """
    return page.evaluate(script, directory)


def shots(data: dict) -> list[dict]:
    return list((data.get("plan") or {}).get("shot_specs") or [])


def wait_for(page, directory: str, predicate, *, timeout: float, interval: float = 4.0):
    deadline = time.monotonic() + timeout
    data = projection(page, directory)
    while True:
        if predicate(data):
            return data
        if time.monotonic() >= deadline:
            raise AssertionError(
                "timeout waiting for workspace state; shots="
                + json.dumps(
                    [
                        {
                            "title": shot.get("title"),
                            "attempts": [item["status"] for item in shot.get("generation_attempts") or []],
                            "candidates": len(shot.get("candidates") or []),
                        }
                        for shot in shots(data)
                    ],
                    ensure_ascii=False,
                )
            )
        time.sleep(interval)
        data = projection(page, directory)


def all_stable(data: dict) -> bool:
    if not shots(data):
        return False
    for shot in shots(data):
        for attempt in shot.get("generation_attempts") or []:
            if attempt["status"] not in TERMINAL:
                return False
    return True


def reconcile_until_stable(page, directory: str, *, timeout: float) -> dict:
    """Click the product's own reconcile action while anything is still open."""
    deadline = time.monotonic() + timeout
    data = projection(page, directory)
    while True:
        open_attempts = [
            attempt
            for shot in shots(data)
            for attempt in shot.get("generation_attempts") or []
            if attempt["status"] not in TERMINAL
        ]
        if not open_attempts:
            return data
        if time.monotonic() >= deadline:
            return data
        button = page.query_selector("#reconcile-generation")
        if button is not None and button.is_visible() and not button.is_disabled():
            button.click()
            page.wait_for_timeout(1500)
        else:
            page.wait_for_timeout(3000)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#generation-shots .generation-shot")
        data = projection(page, directory)


def empty_shots(data: dict) -> list[dict]:
    return [shot for shot in shots(data) if not shot.get("candidates")]


def has_open_attempt(shot: dict) -> bool:
    return any(
        attempt["status"] not in TERMINAL
        for attempt in shot.get("generation_attempts") or []
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8787")
    parser.add_argument("--workspace-dir", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--product-name", default="粗棒针织套头毛衣")
    parser.add_argument(
        "--description",
        default="宽松落肩的长袖针织套头毛衣，圆领粗棒针立体纹理，适合春秋通勤内搭。",
    )
    parser.add_argument("--selling-point", action="append", default=None)
    parser.add_argument(
        "--user-intent",
        default="呈现针织纹理与自然垂感，避免厚重臃肿的效果。",
    )
    parser.add_argument("--generation-timeout", type=float, default=1500.0)
    parser.add_argument("--rework-timeout", type=float, default=900.0)
    parser.add_argument("--retry-rounds", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=20.0)
    args = parser.parse_args()

    selling_points = args.selling_point or ["粗棒针立体纹理", "宽松落肩版型"]
    workspace = Path(args.workspace_dir)
    image = Path(args.image)
    if not image.is_file():
        raise SystemExit(f"reference image missing: {image}")
    if (workspace / "workspace.json").is_file():
        raise SystemExit(f"workspace already exists: {workspace}")

    stamp = datetime.now().strftime("%Y-%m-%d")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = EVIDENCE / f"real-ui-full-loop-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{run_id}-report.json"
    report: dict = {
        "run": "real full loop through the product UI",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "base": args.base,
        "workspace": str(workspace),
        "reference_image": str(image),
        "steps": [],
    }
    steps = StepLog(report, report_path)
    report["steps"] = steps
    started = time.monotonic()

    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: steps.append({"page_error": str(error)}))
        page.goto(args.base, wait_until="domcontentloaded")

        # The desktop build opens a Windows folder dialog here; automation posts the
        # same directory the dialog would return, then continues the flow in the UI.
        created = page.evaluate(
            """
            async (payload) => {
              const response = await fetch("/api/workspaces", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload),
              });
              const body = await response.json();
              if (!body.ok) throw new Error(JSON.stringify(body));
              return body.data;
            }
            """,
            {"directory": str(workspace)},
        )
        steps.append({"step": "create workspace", "status": created["workspace"]["status"]})
        page.evaluate(
            "([key, value]) => sessionStorage.setItem(key, value)",
            [SESSION_KEY, str(workspace)],
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#intake-screen:not([hidden])")

        # 1. product intake through the real form
        page.fill("#product-name", args.product_name)
        page.fill("#product-description", args.description)
        page.fill("#selling-points", "\n".join(selling_points))
        page.fill("#user-intent", args.user_intent)
        page.set_input_files("#reference-images", str(image))
        page.click("#save-intake")
        page.wait_for_selector("#brief-workspace:not([hidden])", timeout=60000)
        saved = projection(page, str(workspace))
        steps.append({
            "step": "save intake",
            "product_name": saved["intake"]["product_name"],
            "reference_images": [item["name"] for item in saved["intake"]["reference_images"]],
        })

        # 2. product brief
        page.click("#analyze-product")
        page.wait_for_selector("#product-brief-form:not([hidden])", timeout=180000)
        page.click("#save-brief")
        page.wait_for_selector("#plan-workspace:not([hidden])", timeout=60000)
        brief = projection(page, str(workspace))
        steps.append({
            "step": "product brief",
            "category": (brief.get("product_brief") or {}).get("category", {}).get("label"),
            "facts": [
                {"key": item.get("key"), "state": item.get("state"), "source": item.get("source")}
                for item in (brief.get("product_brief") or {}).get("facts", [])
            ],
        })

        # 3. dynamic plan
        page.click("#generate-plan")
        page.wait_for_selector("#plan-shots .plan-shot", timeout=300000)
        if page.is_enabled("#save-plan"):
            page.click("#save-plan")
            page.wait_for_timeout(1200)
        planned = wait_for(
            page, str(workspace),
            lambda data: bool(shots(data)),
            timeout=120000,
        )
        steps.append({
            "step": "plan",
            "shot_count": len(shots(planned)),
            "shots": [
                {"title": shot["title"], "archetype": shot["archetype_id"]}
                for shot in shots(planned)
            ],
        })

        # 4. one-click whole-set generation with the real model
        # The whole-set request compiles every missing prompt before it submits, so it
        # can take minutes. Waiting for its own response is what keeps a later per-shot
        # retry from racing the same workspace revision.
        with page.expect_response(
            lambda response: "/api/generation/start" in response.url,
            timeout=args.generation_timeout * 1000,
        ) as started_response:
            page.click("#start-generation")
        response = started_response.value
        submit_step = {"step": "submit whole set", "http_status": response.status}
        try:
            payload = response.json()
            submit_step["ok"] = bool(payload.get("ok"))
            submit_step["message"] = (payload.get("error") or {}).get("message")
        except Exception as error:  # noqa: BLE001 - evidence, not control flow
            submit_step["message"] = f"response not readable: {error}"
        steps.append(submit_step)
        generated = reconcile_until_stable(page, str(workspace), timeout=args.generation_timeout)
        for round_index in range(args.retry_rounds):
            time.sleep(args.retry_delay)
            # Refresh before deciding: a slow task can turn terminal between rounds,
            # and the per-shot rework request must be observed before reconciling.
            generated = projection(page, str(workspace))
            pending = empty_shots(generated)
            if not pending:
                break
            round_errors: list[dict] = []
            for shot in pending:
                fresh = projection(page, str(workspace))
                current = next(
                    (item for item in shots(fresh) if item["id"] == shot["id"]), None,
                )
                if current is None or current.get("candidates") or has_open_attempt(current):
                    continue
                page.reload(wait_until="domcontentloaded")
                page.wait_for_selector("#generation-shots .generation-shot")
                selector = '.generation-retry[data-retry-shot-id="%s"]' % shot["id"]
                if page.query_selector(selector) is None:
                    continue
                with page.expect_response(
                    lambda response: "/api/generation/rework" in response.url,
                    timeout=args.rework_timeout * 1000,
                ) as rework_call:
                    page.click(selector)
                try:
                    rework_payload = rework_call.value.json()
                except Exception:  # noqa: BLE001 - evidence, not control flow
                    rework_payload = {}
                if not rework_payload.get("ok"):
                    round_errors.append({
                        "shot": shot["title"],
                        "http_status": rework_call.value.status,
                        "error": (rework_payload.get("error") or {}).get("message"),
                    })
                generated = reconcile_until_stable(
                    page, str(workspace), timeout=args.rework_timeout,
                )
            steps.append({
                "step": f"retry round {round_index + 1}",
                "attempted": [shot["title"] for shot in pending],
                "errors": round_errors,
                "still_empty": [
                    shot["title"] for shot in shots(generated) if not shot.get("candidates")
                ],
            })
        generated = projection(page, str(workspace))
        empty_titles = [shot["title"] for shot in shots(generated) if not shot.get("candidates")]
        steps.append({
            "step": "generate whole set",
            "shots": [
                {
                    "title": shot["title"],
                    "attempts": [item["status"] for item in shot.get("generation_attempts") or []],
                    "tasks": [
                        item.get("provider_task_id") for item in shot.get("generation_attempts") or []
                    ],
                    "candidates": len(shot.get("candidates") or []),
                }
                for shot in shots(generated)
            ],
            "empty_shots": empty_titles,
        })
        if empty_titles:
            raise AssertionError(f"shots without candidates after retries: {empty_titles}")

        # 5. two-phase single-shot rework (the "not happy, redo this one" path)
        target = next(
            (shot for shot in shots(generated) if shot["archetype_id"] == "lifestyle"),
            shots(generated)[-1],
        )
        before_rework = {
            "shot_id": target["id"],
            "title": target["title"],
            "attempts": len(target.get("generation_attempts") or []),
            "candidates": len(target.get("candidates") or []),
            "prompt_version": (target.get("latest_prompt") or {}).get("version"),
        }
        page.click('#generation-shots .generation-shot[data-shot-id="%s"]' % target["id"])
        rework_selector = '.generation-rework[data-rework-shot-id="%s"]' % target["id"]
        page.wait_for_selector(rework_selector, timeout=60000)
        page.click(rework_selector)
        page.wait_for_selector("#rework-dialog[open]", timeout=30000)
        page.check("#rework-reasons input[value='scene-background']")
        page.fill(
            "#rework-direction",
            "场景太杂，换一个更中性的背景；商品本体的形状、颜色与纹理保持不变。",
        )
        page.click("#rework-preview-button")
        page.wait_for_selector(
            "#rework-preview:not([hidden])", timeout=args.rework_timeout * 1000)
        preview_change = page.locator("#rework-change").inner_text()
        page.click("#rework-confirm")
        page.wait_for_function(
            "() => !document.querySelector('#rework-dialog').open",
            timeout=args.rework_timeout * 1000)
        reworked = reconcile_until_stable(page, str(workspace), timeout=args.rework_timeout)
        target_after = next(shot for shot in shots(reworked) if shot["id"] == target["id"])
        others_unchanged = all(
            len(shot.get("candidates") or []) == 1
            for shot in shots(reworked) if shot["id"] != target["id"]
        )
        steps.append({
            "step": "single-shot rework",
            "before": before_rework,
            "preview_change": preview_change,
            "after": {
                "attempts": len(target_after.get("generation_attempts") or []),
                "candidates": len(target_after.get("candidates") or []),
                "prompt_version": (target_after.get("latest_prompt") or {}).get("version"),
                "edit_reason": (target_after.get("latest_prompt") or {}).get("edit_reason"),
                "tasks": [
                    item.get("provider_task_id")
                    for item in target_after.get("generation_attempts") or []
                ],
                "old_candidate_kept": len(target_after.get("candidates") or [])
                > before_rework["candidates"],
            },
            "unrelated_shots_untouched": others_unchanged,
        })
        if not steps[-1]["after"]["old_candidate_kept"]:
            raise AssertionError("rework lost the earlier candidate")
        if not others_unchanged:
            raise AssertionError("rework changed unrelated shots")

        # 6. per-image selection of the newest candidate through the review workbench
        for shot in shots(reworked):
            newest = (shot.get("candidates") or [])[-1]["candidate_id"]
            page.click(
                '#generation-shots .generation-shot[data-shot-id="%s"]' % shot["id"])
            page.wait_for_selector(
                '#review-candidates .review-candidate-button[data-candidate-id="%s"]'
                % newest, timeout=30000)
            page.click(
                '#review-candidates .review-candidate-button[data-candidate-id="%s"]'
                % newest)
            adopt = page.locator("#review-adopt")
            if adopt.is_enabled():
                adopt.click()
                page.wait_for_timeout(300)
        page.wait_for_selector("#export-selection:not([disabled])", timeout=60000)
        selected = projection(page, str(workspace))
        steps.append({
            "step": "selection",
            "selection_version": selected["selection"]["version"],
            "choices": len(selected["selection"]["choices"]),
        })

        # 7. check the delivery screen (S4), acknowledge any recorded drift, then export
        page.click("#export-selection")
        page.wait_for_selector("#delivery-screen:not([hidden])", timeout=60000)
        ack = page.locator("#delivery-ack")
        if page.locator("#delivery-consistency:not([hidden])").count() and not ack.is_checked():
            ack.check()
        page.wait_for_selector("#export-delivery:not([disabled])", timeout=60000)
        page.click("#export-delivery")
        page.wait_for_selector("#export-summary:not([hidden])", timeout=60000)
        exported = projection(page, str(workspace))
        record = exported["export"]
        delivered = []
        for index, item in enumerate(record["files"]):
            script = """
            async ([directory, exportId, fileIndex]) => {
              const url = "/api/exports/" + encodeURIComponent(exportId) + "/files/" + fileIndex
                + "?directory=" + encodeURIComponent(directory);
              const response = await fetch(url);
              if (!response.ok) return {ok: false, status: response.status};
              const buffer = new Uint8Array(await response.arrayBuffer());
              let binary = "";
              for (const byte of buffer) binary += String.fromCharCode(byte);
              return {ok: true, base64: btoa(binary)};
            }
            """
            payload = page.evaluate(script, [str(workspace), record["id"], index])
            if not payload.get("ok"):
                raise AssertionError(f"export file {index} not reachable through HTTP")
            import base64

            content = base64.b64decode(payload["base64"])
            delivered.append({
                "relative_path": item["relative_path"],
                "byte_size": len(content),
                "sha256_matches_manifest": hashlib.sha256(content).hexdigest()
                == item["file_sha256"],
            })
        steps.append({
            "step": "export",
            "export_id": record["id"],
            "export_version": record["version"],
            "relative_path": record["relative_path"],
            "files": delivered,
        })
        if not all(item["sha256_matches_manifest"] for item in delivered):
            raise AssertionError("exported bytes do not match the manifest")

        page.screenshot(path=str(out_dir / f"{run_id}-after-export.png"), full_page=True)
        browser.close()

    report["duration_seconds"] = round(time.monotonic() - started, 1)
    report["ok"] = True
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "evidence": str(report_path),
        "export": report["steps"][-1]["export_id"],
        "duration_seconds": report["duration_seconds"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
