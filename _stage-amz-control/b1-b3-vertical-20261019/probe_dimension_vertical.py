#!/usr/bin/env python
"""Dimension page-consumer vertical (B1-B3 slice): real bearing source + NSK608 nominal.

Uses existing real approved bearing JPEG (sha 4c4ed76c...) from the preserved
bearing-main final package plus that same project's size_dimensions v3 values
(object/axis/value/unit/source_basis verbatim), entered through the actual UI
dimension editor into an isolated current-format project. No teaching cup
dimensions are written to the real project path.

Flow (actual page, isolated temp profile, Fake providers only, 0 real calls):
 1. create project, upload real bearing JPEG as primary reference
 2. fill + confirm size_dimensions via actual dimension editor (3 NSK nominal rows)
 3. confirm remainingBlocking-free minimal facts as needed, seed suite, bind
    size_dimensions to the size shot, make ordinary decisions
 4. bind each measurement through actual UI (object/axis labels + Nominal),
    save spec, read back persisted ShotSpec from IDB
 5. compile size shot, read literal text + confirmation sheet/fingerprint
 6. change one source measurement through UI, show old binding blocked
    (save gate refuses stale binding; prompt/confirm show stale, unrelated
    shots untouched), then re-confirm binding on new value
 7. screenshot of the dimension binding surface

Evidence: dimension-vertical/*.json + *.png in this directory.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
STAGE_DIR = Path(__file__).resolve().parent
OUT = STAGE_DIR / "dimension-vertical"
OUT.mkdir(parents=True, exist_ok=True)

import v2_stage_nav as stage_nav  # noqa: E402
import v2_verify_shared as shared  # noqa: E402

BEARING_JPEG = STAGE_DIR / "bearing-user-ref.jpg"
BEARING_SHA = "4c4ed76c61c959ace082f8f3698f1b10bf0e1c942c2b1e524b1e62086d4df1e1"
SIZE_SHOT = "shot_size_dimensions"
NSK_BASIS = ("NSK官方608 Series公称规格d8/D22/B7mm；照片608Z按NSK E126h表2.1的Z规则"
             "对应。非用户实测。来源：www.nsk.com/engineering（608 Series）。")
NSK_ROWS = [
    {"object": "内圈", "axis": "diameter", "value": 8, "unit": "mm", "source_basis": NSK_BASIS},
    {"object": "外圈", "axis": "diameter", "value": 22, "unit": "mm", "source_basis": NSK_BASIS},
    {"object": "轴承", "axis": "width", "value": 7, "unit": "mm", "source_basis": NSK_BASIS},
]
LABELS = [
    {"object_label": "Inner ring", "axis_label": "bore diameter"},
    {"object_label": "Outer ring", "axis_label": "outside diameter"},
    {"object_label": "Bearing", "axis_label": "width"},
]

PROBE_FACT = """
async (slotId) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const all = await new Promise((resolve, reject) => {
    const request = db.transaction(["documents"], "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const chain = all.filter((item) => item.kind === "fact_slot" && item.document_id === slotId)
    .sort((a, b) => a.version - b.version);
  return chain.map((item) => ({ version: item.version, status: (item.payload||{}).status,
    value: (item.payload||{}).value, source: (item.payload||{}).source }));
}
"""

PROBE_SHOT_SPEC_FULL = """
async (shotId) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const all = await new Promise((resolve, reject) => {
    const request = db.transaction(["documents"], "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const chain = all.filter((item) => item.kind === "shot_spec" && item.document_id === shotId)
    .sort((a, b) => a.version - b.version);
  if (!chain.length) return null;
  const head = chain[chain.length - 1];
  return { version: head.version, schema_version: head.schema_version, payload: head.payload,
    versions: chain.map((c) => c.version) };
}
"""

PROBE_PROMPT = """
async (shotId) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const all = await new Promise((resolve, reject) => {
    const request = db.transaction(["documents"], "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const chain = all.filter((item) => item.kind === "prompt_version" && item.document_id === shotId)
    .sort((a, b) => a.version - b.version);
  if (!chain.length) return null;
  const head = chain[chain.length - 1];
  const payload = head.payload || {};
  return { version: head.version, schema_version: head.schema_version,
    text: payload.text, compiled: payload.compiled, basis: payload.basis,
    versions: chain.map((c) => c.version) };
}
"""

PROBE_CONFIRM_SHEET = """
async () => {
  const mod = await import("/app/product_v2/prompts.js").catch(() => null);
  return { importable: Boolean(mod) };
}
"""

CONFIRM_DOM = """
() => {
  const el = (id) => document.getElementById(id);
  const rows = [...document.querySelectorAll("#confirm-list .confirm-shot")].map((node) => ({
    shot_id: node.getAttribute("data-shot-id"),
    blocked: node.getAttribute("data-blocked"),
    text: (node.textContent || "").trim().slice(0, 1200),
    blockers: [...node.querySelectorAll(".confirm-shot-blocker")].map((line) => ({
      text: (line.textContent || "").trim(),
      region: line.getAttribute("data-region") })),
  }));
  return {
    editor_hidden: el("confirm-editor") ? el("confirm-editor").hidden : null,
    status: (el("confirm-status") || {}).textContent || "",
    rows: rows,
  };
}
"""


def log(message: str) -> None:
    print(message, flush=True)


def dump(name: str, data: dict) -> Path:
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main() -> int:
    from playwright.sync_api import sync_playwright

    assert BEARING_JPEG.exists(), f"missing bearing JPEG: {BEARING_JPEG}"
    raw = BEARING_JPEG.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == BEARING_SHA, "bearing JPEG bytes mismatch"
    assert len(raw) == 73681

    port = shared.free_port()
    server, _providers = shared.start_product_server(port)
    base = f"http://127.0.0.1:{port}/"
    workdir = Path(tempfile.mkdtemp(prefix="dim-vertical-"))
    observed: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "bearing_sha256": BEARING_SHA,
        "bearing_bytes": len(raw),
        "real_model_calls": 0,
        "providers": "FakeSemantic/FakeImage/FakeReview only",
    }
    exit_code = 1
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(workdir / "profile"), headless=True,
                viewport={"width": 1440, "height": 900})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                logs = shared.collect(page)
                posts: list[dict] = []

                def capture(request) -> None:
                    if request.method == "POST":
                        posts.append({"url": request.url.split("?", 1)[0]})

                page.on("request", capture)
                page.goto(base, wait_until="networkidle")
                shared.create_project(page, "NSK608尺寸绑定验证", BEARING_JPEG)

                # --- 1. fill + confirm size_dimensions through the real dimension editor.
                stage_nav.goto(page, "understand")
                page.wait_for_selector("#slot-list .slot-row:not([hidden])", timeout=30_000)
                # show all facts so the dimension row is reachable
                if page.locator("#slots-toggle").count():
                    label = page.locator("#slots-toggle").inner_text()
                    if "显示全部" in label:
                        page.click("#slots-toggle")
                dim_row = '#slot-list .slot-row[data-slot-id="size_dimensions"]'
                page.wait_for_selector(dim_row, timeout=15_000)
                page.locator(dim_row).scroll_into_view_if_needed()
                fill_btn = page.locator(dim_row).get_by_role("button", name="填值并确认", exact=True)
                if fill_btn.count() == 0:
                    raise AssertionError("dimension row has no fill-and-confirm entry")
                fill_btn.first.click()
                page.wait_for_selector(dim_row + ' [data-dimension-field="object"]', timeout=10_000)
                # editor opens with one row; add two more for the 3 NSK measurements
                add_btn = page.locator(dim_row).get_by_role("button", name="添加测量", exact=True)
                add_btn.first.click()
                page.wait_for_timeout(200)
                add_btn.first.click()
                page.wait_for_timeout(200)
                editor_rows = page.locator(dim_row + " .dimension-row")
                assert editor_rows.count() == 3, f"expected 3 editor rows, got {editor_rows.count()}"
                for index, want in enumerate(NSK_ROWS):
                    row = editor_rows.nth(index)
                    row.locator('[data-dimension-field="object"]').fill(want["object"])
                    row.locator('[data-dimension-field="axis"]').select_option(want["axis"])
                    row.locator('[data-dimension-field="value"]').fill(str(want["value"]))
                    row.locator('[data-dimension-field="unit"]').select_option(want["unit"])
                    row.locator('[data-dimension-field="source_basis"]').fill(want["source_basis"])
                page.locator(dim_row).get_by_role("button", name="确认", exact=True).first.click()
                page.wait_for_function(
                    "() => { const n = document.querySelector("
                    "'#slot-list .slot-row[data-slot-id=\"size_dimensions\"]');"
                    " return n && n.getAttribute('data-status') === 'confirmed'; }",
                    timeout=15_000)
                fact_chain = page.evaluate(PROBE_FACT, "size_dimensions")
                observed["fact_chain_after_confirm"] = fact_chain
                head = fact_chain[-1]
                assert head["status"] == "confirmed", head
                assert head["value"] == NSK_ROWS, "persisted values must equal NSK source rows"
                fact_version = head["version"]
                observed["fact_version"] = fact_version

                # --- 1b. minimal critical facts via manual path (real bearing values;
                # no fake semantic calls). Needed for briefReadiness before prepare.
                critical = {
                    "product_name": "NSK 608Z 深沟球轴承",
                    "product_category": "微型深沟球轴承",
                }
                for slot_id, value in critical.items():
                    row = f'#slot-list .slot-row[data-slot-id="{slot_id}"]'
                    page.wait_for_selector(row, timeout=15_000)
                    page.locator(row).scroll_into_view_if_needed()
                    btn = page.locator(row).get_by_role("button", name="填值并确认", exact=True)
                    if btn.count():
                        btn.first.click()
                        page.wait_for_selector(row + ' #slot-editor-value', timeout=10_000)
                        page.locator(row + ' #slot-editor-value').fill(value)
                        page.locator(row).get_by_role("button", name="确认", exact=True).first.click()
                        page.wait_for_function(
                            """(id) => { const n = document.querySelector(
                              '#slot-list .slot-row[data-slot-id="' + id + '"]');
                              return n && n.getAttribute('data-status') === 'confirmed'; }""",
                            arg=slot_id, timeout=15_000)
                sig_row = '#slot-list .slot-row[data-slot-id="signature_features"]'
                page.wait_for_selector(sig_row, timeout=15_000)
                page.locator(sig_row).scroll_into_view_if_needed()
                sig_btn = page.locator(sig_row).get_by_role("button", name="填值并确认", exact=True)
                if sig_btn.count():
                    sig_btn.first.click()
                    page.wait_for_selector(sig_row + ' #slot-editor-value', timeout=10_000)
                    page.locator(sig_row + ' #slot-editor-value').fill(
                        "单面防尘盖\nNSK 标识\n608 规格")
                    page.locator(sig_row).get_by_role("button", name="确认", exact=True).first.click()
                    page.wait_for_function(
                        """() => { const n = document.querySelector(
                          '#slot-list .slot-row[data-slot-id="signature_features"]');
                          return n && n.getAttribute('data-status') === 'confirmed'; }""",
                        timeout=15_000)
                observed["critical_confirmed"] = ["product_name", "product_category",
                                                 "signature_features"]

                # --- 2. suite: seed; size shot should already bind size_dimensions.
                stage_nav.goto(page, "plan")
                page.click("#suite-seed")
                page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
                shot_ids = page.evaluate(shared.SHOT_IDS)
                observed["shot_ids"] = shot_ids
                assert SIZE_SHOT in shot_ids, f"size shot missing: {shot_ids}"
                bound_now = page.evaluate(
                    """(shotId) => {
                      const card = document.querySelector(
                        '#shot-list .shot-row[data-shot-id="' + shotId + '"]');
                      if (!card) return { found: false };
                      const boxes = [...card.querySelectorAll("input[type='checkbox']")];
                      return { found: true, count: boxes.length,
                        labels: boxes.map((b) => (b.value || '') + '|' + (b.checked ? '1' : '0')) };
                    }""", SIZE_SHOT)
                observed["binding_controls_probe"] = bound_now

                # --- 3. ordinary decisions + bind each measurement through actual UI.
                shared.decide_presentation(page)
                shared.open_specs(page)
                card = f'#shot-spec-list .shot-spec[data-shot-id="{SIZE_SHOT}"]'
                page.wait_for_selector(card, timeout=15_000)
                page.click(f"#spec-print-selected-{SIZE_SHOT}")
                page.wait_for_selector(f"#spec-measurements-{SIZE_SHOT} .measurement-row",
                                       timeout=15_000)
                mrows = page.locator(f"#spec-measurements-{SIZE_SHOT} .measurement-row")
                assert mrows.count() == 3, f"expected 3 measurable rows, got {mrows.count()}"
                for index in range(3):
                    row_id = f"spec-measure-{SIZE_SHOT}-size_dimensions-{index}"
                    page.click(f"#{row_id}-pick")
                    page.wait_for_selector(f"#{row_id}-axis", timeout=10_000)
                    page.fill(f"#{row_id}-object", LABELS[index]["object_label"])
                    page.fill(f"#{row_id}-axis", LABELS[index]["axis_label"])
                    page.click(f"#{row_id}-nominal")
                    page.wait_for_timeout(150)
                    preview = page.locator(f"#{row_id}-preview").inner_text()
                    observed.setdefault("previews", {})[str(index)] = preview
                page.click(f"#spec-layout-{SIZE_SHOT}-product_left_text_right")
                group_box = f"#spec-group-{SIZE_SHOT}-size_dimensions"
                page.wait_for_selector(group_box, timeout=10_000)
                page.click(group_box)
                page.click(card + ' button:has-text("保存")')
                page.wait_for_function(
                    """(id) => {
                      const card = document.querySelector(
                        '#shot-spec-list .shot-spec[data-shot-id="' + id + '"]');
                      const meta = card ? card.querySelector(".shot-spec-head .meta") : null;
                      return Boolean(meta && meta.textContent.includes("规格 v"));
                    }""", arg=SIZE_SHOT, timeout=15_000)
                spec = page.evaluate(PROBE_SHOT_SPEC_FULL, SIZE_SHOT)
                observed["shot_spec_saved"] = spec

                # --- 4. main shot minimal decision so suite can prepare; compile + confirm.
                shared.decide_shot_decision(page, "shot_main_clean", print_intent="none")
                # Only the size shot has its facts; main shot stays prompt-state "none".
                shared.compile_all(page, [SIZE_SHOT])
                prompt = page.evaluate(PROBE_PROMPT, SIZE_SHOT)
                observed["prompt_size"] = prompt
                main_prompt = page.evaluate(PROBE_PROMPT, "shot_main_clean")
                observed["prompt_main_state"] = (
                    {"version": (main_prompt or {}).get("version")} if main_prompt else None)
                stage_nav.goto(page, "generate")
                page.wait_for_selector("#confirm-editor:not([hidden])", timeout=30_000)
                page.wait_for_function(
                    """(id) => Boolean(document.querySelector(
                      '#confirm-list .confirm-shot[data-shot-id="' + id + '"]'))""",
                    arg=SIZE_SHOT, timeout=30_000)
                confirm = page.evaluate(CONFIRM_DOM)
                size_row = next((r for r in confirm["rows"] if r["shot_id"] == SIZE_SHOT), None)
                observed["confirm_size_row"] = size_row
                stage_nav.goto(page, "plan")
                shared.open_specs(page)
                page.wait_for_selector(card, timeout=15_000)
                page.locator(card).scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / "dimension-binding-surface.png"))

                # --- 5. change one source measurement through UI; old binding must block.
                stage_nav.goto(page, "understand")
                dim_row = '#slot-list .slot-row[data-slot-id="size_dimensions"]'
                page.wait_for_selector(dim_row, timeout=15_000)
                page.locator(dim_row).scroll_into_view_if_needed()
                page.locator(dim_row).get_by_role("button", name="修改", exact=True).first.click()
                page.wait_for_selector(dim_row + " [data-dimension-field]", timeout=10_000)
                new_value = page.locator(dim_row + " [data-dimension-field='value']").first
                new_value.fill("9")
                page.locator(dim_row).get_by_role("button", name="保存", exact=True).first.click()
                page.wait_for_function(
                    """() => { const n = document.querySelector(
                      '#slot-list .slot-row[data-slot-id="size_dimensions"]');
                      return n && n.getAttribute('data-version') !== '%d'; }""" % fact_version,
                    timeout=15_000)
                fact_chain2 = page.evaluate(PROBE_FACT, "size_dimensions")
                observed["fact_chain_after_change"] = fact_chain2
                new_version = fact_chain2[-1]["version"]
                assert fact_chain2[-1]["value"][0]["value"] == 9, fact_chain2[-1]["value"]
                log("fact moved v%s -> v%s" % (fact_version, new_version))

                # Revisit spec card: stale notice must appear; save must be blocked.
                stage_nav.goto(page, "plan")
                shared.open_specs(page)
                page.wait_for_selector(card, timeout=15_000)
                stale_id = f"#spec-measure-stale-{SIZE_SHOT}-size_dimensions-0"
                page.wait_for_selector(stale_id, timeout=15_000)
                observed["stale_notice"] = page.locator(stale_id).inner_text()
                spec_before = page.evaluate(PROBE_SHOT_SPEC_FULL, SIZE_SHOT)
                page.click(card + ' button:has-text("保存")')
                page.wait_for_selector("#specs-error:not([hidden])", timeout=10_000)
                observed["save_block_message"] = page.locator("#specs-error").inner_text()
                spec_after = page.evaluate(PROBE_SHOT_SPEC_FULL, SIZE_SHOT)
                observed["spec_versions_before_block"] = spec_before["versions"]
                observed["spec_versions_after_block"] = spec_after["versions"]
                assert spec_before["versions"] == spec_after["versions"], "stale save must not append"
                log("stale save blocked: %s" % observed["save_block_message"][:80])

                # Unrelated shots untouched: main shot prompt state still none/absent.
                stage_nav.goto(page, "generate")
                main_prompt2 = page.evaluate(PROBE_PROMPT, "shot_main_clean")
                observed["prompt_main_after"] = (
                    {"version": (main_prompt2 or {}).get("version")} if main_prompt2 else None)
                size_state = page.evaluate(
                    """(id) => { const n = document.querySelector(
                      '#prompt-list .shot-spec[data-shot-id="' + id + '"]');
                      return n ? n.getAttribute("data-prompt-state") : null; }""", SIZE_SHOT)
                observed["size_prompt_state_after_source_change"] = size_state

                # Screenshot: stale surface (binding surface was captured pre-change).
                stage_nav.goto(page, "plan")
                shared.open_specs(page)
                page.wait_for_selector(card, timeout=15_000)
                page.locator(stale_id).scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / "dimension-stale-block.png"))
                observed["screenshots"] = ["dimension-binding-surface.png",
                                           "dimension-stale-block.png"]
                posts_meta = [p for p in posts if "/api/" in p["url"]]
                observed["api_posts"] = posts_meta
                dump("dimension-vertical-progress.json", observed)
                log("stale proof + screenshots captured")
                exit_code = 0
            finally:
                context.close()
    finally:
        try:
            server.stop()
        except Exception:
            pass
    observed["exit_code"] = exit_code
    dump("dimension-vertical-progress.json", observed)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
