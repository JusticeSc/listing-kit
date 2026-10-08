#!/usr/bin/env python
"""Integration checks for D3.6: export surfaces plan/prompt wording drift.

The README and manifest describe every delivered image with the plan's shot
wording. An operator may continue editing a prompt (or rework one shot) after
the plan text was saved, so the exported package must say when the plan wording
no longer describes what was actually delivered instead of shipping a silently
stale title.

Run with:
  <python> tools/verify_product_v1_export_wording_drift.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_product_v1_image_generation import (
    GenerationFixture,
    Submission,
    require_ok,
)
from src.workspace_store import WorkspaceStore
from tools.verify_product_v1_selection_rework_export import (
    RegisteredFakeImageProvider,
    restore_platform_checks,
    use_stub_platform_checks,
)

DRIFT_HEADING = "注意：方案文本与提示词可能不一致"
SESSION_KEY = "amzListingKit.productV1.workspaceDirectory"
PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: object = None) -> None:
    if condition:
        PASSED.append(label)
        print(f"ok   {label}")
    else:
        FAILED.append(label)
        print(f"FAIL {label}: {detail!r}")


def browser_phase(fixture: GenerationFixture, target_title: str) -> None:
    """Prove the S4 screen blocks drift until the operator acknowledges it."""
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("note: Playwright missing; browser drift-confirm check skipped.")
        return
    from app.product_v1_server import ProductApplication, create_product_server

    with tempfile.TemporaryDirectory(prefix="amz-product-v1-drift-ui-") as raw:
        app = ProductApplication(
            service=fixture.service,
            recent_index_path=Path(raw) / "recent-workspaces.json",
            folder_picker=lambda _purpose: str(fixture.workspace),
        )
        server = create_product_server("127.0.0.1", 0, application=app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as driver:
                browser = driver.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.goto(base_url + "/", wait_until="load")
                page.evaluate(
                    "([key, value]) => window.sessionStorage.setItem(key, value)",
                    [SESSION_KEY, str(fixture.workspace)],
                )
                page.reload(wait_until="load")
                page.wait_for_selector("#generation-shots .generation-shot", timeout=20000)
                before = len(WorkspaceStore.open(fixture.workspace).list_records("export"))
                page.click("#export-selection")
                page.wait_for_selector("#delivery-screen:not([hidden])", timeout=20000)
                page.wait_for_selector("#delivery-consistency:not([hidden])", timeout=20000)
                consistency_text = page.locator("#delivery-consistency-list").inner_text()
                check(
                    "S4 delivery check lists the drifted shot",
                    target_title in consistency_text, consistency_text,
                )
                check(
                    "drifted export stays blocked until acknowledged",
                    page.locator("#export-delivery").is_disabled(),
                )
                check(
                    "opening S4 writes no export version",
                    len(WorkspaceStore.open(fixture.workspace).list_records("export")) == before,
                )
                page.check("#delivery-ack")
                check(
                    "acknowledging the drift enables the export button",
                    page.locator("#export-delivery").is_enabled(),
                )
                page.click("#export-delivery")
                deadline = time.monotonic() + 60
                after = before
                while time.monotonic() < deadline:
                    after = len(WorkspaceStore.open(fixture.workspace).list_records("export"))
                    if after > before:
                        break
                    page.wait_for_timeout(300)
                check(
                    "acknowledged export writes exactly one new package",
                    after == before + 1, (before, after),
                )
                check(
                    "delivery status confirms the new export",
                    "已导出" in page.locator("#delivery-status").inner_text(),
                    page.locator("#delivery-status").inner_text(),
                )
                check(
                    "export summary exposes the reveal entry",
                    page.locator("#reveal-export").is_visible(),
                )
                browser.close()
        finally:
            server.shutdown()
            server.server_close()


def main() -> int:
    # The fixture candidates are small PNGs; the deterministic Amazon US rules are
    # verified separately, so this file stubs the platform checks like the shipped
    # selection/export verifier does and keeps the focus on wording drift.
    real_platform = use_stub_platform_checks()
    fixture = GenerationFixture()
    try:
        fixture.setUp()
        provider = RegisteredFakeImageProvider()
        fixture.image_provider = provider
        shots = fixture.plan["plan"]["shot_specs"]
        provider.plan_submissions([
            Submission("SUCCEEDED", f"drift-task-{index}") for index in range(1, len(shots) + 1)
        ])
        require_ok(fixture.start("product-v1-drift-0001"), "start whole-set generation")

        data = fixture.projection()
        shots = data["plan"]["shot_specs"]
        choices = []
        for shot in shots:
            candidates = shot.get("candidates") or []
            check(f"shot {shot['id']} has exactly one candidate", len(candidates) == 1, candidates)
            if candidates:
                choices.append({
                    "shot_id": shot["id"], "candidate_sha256": candidates[0]["candidate_id"],
                })
        saved = require_ok(fixture.service.save_selection(
            fixture.workspace, expected_etag=data["workspace"]["revision"], choices=choices,
        ), "save selection")

        clean = require_ok(fixture.service.export_selection(
            fixture.workspace, expected_etag=saved["workspace"]["revision"],
        ), "export without drift")
        check(
            "clean export carries no wording warnings",
            not (clean.get("plan_wording_warnings") or []), clean.get("plan_wording_warnings"),
        )
        clean_readme = (
            fixture.workspace / clean["export"]["relative_path"] / "README.md"
        ).read_text(encoding="utf-8")
        check("clean README has no drift note", DRIFT_HEADING not in clean_readme)

        target = shots[0]
        prompt = target["latest_prompt"]
        edited_text = (
            prompt["full_text"]
            + "\nOperator note: keep the framing, drop the pocket stitching detail."
        )
        edited = require_ok(fixture.service.save_prompt_edit(
            fixture.workspace, expected_etag=clean["workspace"]["revision"],
            shot_id=target["id"], expected_prompt_version=prompt["version"],
            full_text=edited_text, reason="导出前核对：方案标题需要同步。",
        ), "edit one prompt")
        latest_version = next(
            item for item in edited["plan"]["shot_specs"] if item["id"] == target["id"]
        )["latest_prompt"]["version"]
        check(
            "manual edit advanced only the target prompt",
            latest_version == prompt["version"] + 1, latest_version,
        )

        blocked = fixture.service.export_selection(
            fixture.workspace, expected_etag=edited["workspace"]["revision"],
        )
        check(
            "prompt edit blocks export until the shot is re-adopted",
            blocked.body["error"]["code"] == "SELECTION_INCOMPLETE", blocked.body,
        )
        delivered = next(
            item["candidate_sha256"] for item in saved["selection"]["choices"]
            if item["shot"]["id"] == target["id"]
        )
        readopted = require_ok(fixture.service.save_shot_selection(
            fixture.workspace, expected_etag=edited["workspace"]["revision"],
            shot_id=target["id"], candidate_sha256=delivered,
        ), "re-adopt the delivered candidate after prompt edit")
        refused = fixture.service.export_selection(
            fixture.workspace, expected_etag=readopted["workspace"]["revision"],
        )
        check(
            "drifted export is refused until the operator acknowledges it",
            refused.body["error"]["code"] == "EXPORT_CONSISTENCY_ACK_REQUIRED", refused.body,
        )
        check(
            "acknowledgment request names exactly the edited shot",
            [item.get("shot_id") for item in refused.body["error"]["details"]["issues"]]
            == [target["id"]],
            refused.body,
        )
        drifted = require_ok(fixture.service.export_selection(
            fixture.workspace, expected_etag=readopted["workspace"]["revision"],
            acknowledge_consistency=True,
        ), "acknowledged export with drift")
        warnings = drifted.get("plan_wording_warnings") or []
        check(
            "drift export warns about exactly the edited shot",
            [item.get("shot_id") for item in warnings] == [target["id"]], warnings,
        )
        check(
            "warning names the delivered and latest prompt versions",
            bool(warnings)
            and warnings[0].get("reason") == "delivered_with_older_prompt"
            and warnings[0].get("delivered_prompt_version") == prompt["version"]
            and warnings[0].get("latest_prompt_version") == prompt["version"] + 1,
            warnings[0] if warnings else None,
        )
        drift_readme = (
            fixture.workspace / drifted["export"]["relative_path"] / "README.md"
        ).read_text(encoding="utf-8")
        check(
            "README carries the drift note for the edited shot",
            DRIFT_HEADING in drift_readme and target["title"] in drift_readme,
            drift_readme[-400:],
        )
        manifest = json.loads(
            (fixture.workspace / drifted["export"]["relative_path"] / "manifest.json")
            .read_text(encoding="utf-8")
        )
        check(
            "manifest records the drift warnings",
            [item.get("shot_id") for item in manifest.get("plan_wording_warnings") or []]
            == [target["id"]],
            manifest.get("plan_wording_warnings"),
        )
        browser_phase(fixture, target["title"])
    finally:
        try:
            fixture.tearDown()
        finally:
            restore_platform_checks(real_platform)

    print(f"{len(PASSED)} passed; {len(FAILED)} failed")
    for label in FAILED:
        print(f"failed: {label}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
