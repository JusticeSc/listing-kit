#!/usr/bin/env python
"""Real browser walkthrough of the shipped workbench: choose -> save -> export.

Drives the actual product entrypoint (app/server.py + app/product_v1) against a
workspace that already holds real generated candidates. It does not touch the
image provider; it records what a user sees and clicks, and verifies that the
exported bytes are reachable through the product HTTP endpoint.

Usage:
  python tools/run_real_ui_selection_export.py --base http://127.0.0.1:8787 --workspace <dir>
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SESSION_KEY = "amzListingKit.productV1.workspaceDirectory"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8787")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y-%m-%d")
    out_dir = Path(args.out) if args.out else (ROOT / "evals" / "product-demo" / f"real-ui-{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"base": args.base, "workspace": args.workspace, "steps": []}
    steps = report["steps"]

    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(args.base + "/", wait_until="load")
        page.screenshot(path=str(out_dir / "01-home.png"))
        opened = page.evaluate(
            """async (directory) => {
                const response = await fetch("/api/workspaces/open", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ directory }),
                });
                const body = await response.json();
                return { ok: body.ok, error: body.error || null };
            }""",
            args.workspace,
        )
        steps.append({"step": "open_workspace", "result": opened})
        page.evaluate("([key, value]) => window.sessionStorage.setItem(key, value)",
                      [SESSION_KEY, args.workspace])
        page.reload(wait_until="load")
        page.wait_for_selector("#generation-shots .generation-shot", timeout=20000)
        page.screenshot(path=str(out_dir / "02-candidates.png"), full_page=True)
        count = page.locator("#generation-shots .generation-shot").count()
        steps.append({"step": "shots_rendered", "count": count})

        chosen = []
        for index in range(count):
            page.locator("#generation-shots .generation-shot").nth(index).click()
            buttons = page.locator("#review-candidates .review-candidate-button")
            total = buttons.count()
            if total == 0:
                chosen.append({"shot_index": index, "candidate_buttons": 0})
                continue
            target = None
            for button_index in range(total - 1, -1, -1):
                if buttons.nth(button_index).get_attribute("aria-pressed") != "true":
                    target = button_index
                    break
            if target is None:
                chosen.append({"shot_index": index, "candidate_buttons": total,
                               "clicked": False, "note": "already chosen"})
                continue
            buttons.nth(target).click()
            page.wait_for_timeout(200)
            adopt = page.locator("#review-adopt")
            adopted = False
            if adopt.is_enabled():
                adopt.click()
                adopted = True
                page.wait_for_timeout(300)
            chosen.append({"shot_index": index, "candidate_buttons": total,
                           "clicked": True, "button_index": target, "adopted": adopted})
        steps.append({"step": "choose_candidates", "detail": chosen})
        page.screenshot(path=str(out_dir / "03-chosen.png"), full_page=True)
        steps.append({
            "step": "selection_progress",
            "text": page.locator("#selection-progress").inner_text(),
        })

        steps.append({
            "step": "save_selection",
            "clicked": False,
            "note": "采用此图即时保存 SelectionVersion；正式审核台没有批量保存步骤",
        })
        page.wait_for_selector("#export-selection:not([disabled])", timeout=60000)
        page.wait_for_timeout(600)
        steps.append({
            "step": "selection_status",
            "text": page.locator("#selection-status").inner_text(),
        })

        previous_summary = page.evaluate(
            "() => { const el = document.querySelector('#export-summary'); return el && !el.hidden ? el.innerText : ''; }")
        page.click("#export-selection")
        page.wait_for_selector("#delivery-screen:not([hidden])", timeout=60000)
        ack = page.locator("#delivery-ack")
        if page.locator("#delivery-consistency:not([hidden])").count() and not ack.is_checked():
            ack.check()
        page.wait_for_selector("#export-delivery:not([disabled])", timeout=60000)
        page.click("#export-delivery")
        page.wait_for_function(
            "(previous) => { const el = document.querySelector('#export-summary');"
            " return !!el && !el.hidden && el.innerText !== previous; }",
            arg=previous_summary, timeout=60000)
        page.wait_for_timeout(500)
        summary = page.locator("#export-summary").inner_text()
        steps.append({"step": "export", "summary": summary})
        page.screenshot(path=str(out_dir / "04-exported.png"), full_page=True)

        files = page.evaluate(
            """async (directory) => {
                const response = await fetch("/api/workspace?" + new URLSearchParams({ directory }));
                const body = await response.json();
                const record = body?.data?.export || null;
                if (!record) return [];
                const results = [];
                for (let index = 0; index < (record.files || []).length; index += 1) {
                    const url = "/api/exports/" + encodeURIComponent(record.id) + "/files/" + index
                        + "?" + new URLSearchParams({ directory });
                    const file = await fetch(url);
                    const blob = await file.arrayBuffer();
                    results.push({ index, status: file.status, bytes: blob.byteLength,
                                   type: file.headers.get("content-type") });
                }
                return results;
            }""",
            args.workspace,
        )
        steps.append({"step": "export_files_over_http", "detail": files})
        browser.close()

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
