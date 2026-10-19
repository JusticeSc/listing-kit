#!/usr/bin/env python
"""B4 four-stage workbench acceptance probe (batch 7): real bearing data, Fake providers.

Actual isolated headless Chrome + formal product entry. No real model calls, no
paid requests. Flow:

 1. import the preserved real bearing project package (232 docs / 19 blobs) through
    the real import file input; reopen workspace
 2. four-stage contract: nav ids intake/plan/make/deliver only; old understand/
    generate/review panels and #review-list/#attempt-list gone; make holds
    #task-list-mount list + persistent detail (#compare-panel / #rework-panel /
    #shot-execution) instead of duplicate per-shot cards
 3. unique task list: one row per planned shot with thumbnail + label + current
    execution/selection state; viewed-shot selection drives persistent detail
    via the common compare API (dataset.shotId) and never rewrites storage
 4. scope semantics: default single mode tracks viewed shot (count 1); explicit
    batch mode shows checkboxes/counts; viewed-shot change does not alter chosen
    batch range; empty checked range stays 0 (never falls back to all); no POST
    from mode/range/viewed changes
 5. responsive/zoom evidence: 1440/1366/1024/390 viewport screenshots with layout
    seam checks, plus real native Chrome zoom 125% (1440x900) and 200% (1366x900)
    through partition.default_zoom_level (no CSS transform/window shrink)

Evidence: evidence/*.json + *.png|webp in this directory. NOT-AUTHORITY.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
STAGE = Path(__file__).resolve().parent
OUT = STAGE / "evidence"
OUT.mkdir(parents=True, exist_ok=True)

import v2_stage_nav as stage_nav  # noqa: E402
import v2_verify_shared as shared  # noqa: E402

OLD_TREE = ROOT.parent / "amz-listing-kit"
BEARING_PKG = OLD_TREE / "_stage-amz-control" / "formal-resume-20261015T125651Z" / "real-wire" / "bearing-main-final.project.zip"
PKG_SHA = "5dd5b7d27d198b788b2aad5dacf193af5dd4e636b0f493bdc407478084717591"

OVERFLOW_PROBE = """() => ({
  scroll_width: document.documentElement.scrollWidth,
  client_width: document.documentElement.clientWidth,
  body_scroll_width: document.body.scrollWidth,
  inner_width: window.innerWidth,
  device_pixel_ratio: window.devicePixelRatio,
  visual_scale: window.visualViewport ? window.visualViewport.scale : null,
})"""

STAGE_PROBE = """() => {
  const nav = [...document.querySelectorAll('#stage-nav .stage')].map((node) => ({
    id: node.getAttribute('data-stage-nav'),
    label: (node.querySelector('.stage-label') || {}).textContent || '',
  }));
  return {
    nav,
    panels: [...document.querySelectorAll('#stage-panels .stage-panel')]
      .map((node) => node.getAttribute('data-stage-panel')),
    next_buttons: [...document.querySelectorAll('#stage-panels [id^="stage-next-"]')]
      .map((node) => node.id),
    task_list: document.getElementById('task-list-mount'),
    task_rows: [...document.querySelectorAll('#task-list-mount [data-task-shot]')].map((row) => ({
      shot: row.getAttribute('data-task-shot'),
      state: row.getAttribute('data-attempt-state'),
      selection: row.getAttribute('data-selection-state'),
      label: ((row.querySelector('[data-task-label]') || row).textContent || '').trim().slice(0, 80),
      thumb: Boolean(row.querySelector('img, canvas, .thumb')),
      view_entry: Boolean(row.querySelector('[data-view-shot]')),
    })),
    make_shot_select: (() => { const el = document.getElementById('make-shot-select');
      return el ? { visible: !el.hidden, options: el instanceof HTMLSelectElement ? [...el.options].map((o) => o.value) : null } : null; })(),
    mode_single: document.getElementById('make-mode-single'),
    mode_batch: document.getElementById('make-mode-batch'),
    batch_boxes: [...document.querySelectorAll('input[data-batch-shot]')].map((el) => el.getAttribute('data-batch-shot')),
    scope_count: (document.getElementById('generation-scope-count') || {}).textContent || null,
    compare: (() => { const p = document.getElementById('compare-panel');
      return p ? { hidden: p.hidden, shot_id: p.dataset.shotId || null } : null; })(),
    rework: (() => { const p = document.getElementById('rework-panel'); return p ? { hidden: p.hidden } : null; })(),
    shot_execution: (() => { const p = document.getElementById('shot-execution');
      return p ? { hidden: p.hidden, shot_id: p.dataset.shotId || null,
        actions: [...p.querySelectorAll('button')].map((b) => (b.textContent || '').trim()).slice(0, 10) } : null; })(),
    legacy_review_list: Boolean(document.getElementById('review-list-mount')),
    legacy_attempt_list: Boolean(document.getElementById('attempt-list')),
    attempt_editor: Boolean(document.getElementById('attempt-editor')),
  };
}"""

DOC_COUNT_PROBE = """
async () => {
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
  return all.length;
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

    raw = BEARING_PKG.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PKG_SHA, "bearing package bytes mismatch"
    log(f"bearing package {len(raw)} bytes ok")

    port = shared.free_port()
    server, _providers = shared.start_product_server(port)
    base = f"http://127.0.0.1:{port}/"
    observed: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "package_sha256": PKG_SHA,
        "package_bytes": len(raw),
        "real_model_calls": 0,
        "providers": "FakeSemantic/FakeImage/FakeReview/FakeSuite only",
        "views": [],
        "console_errors": [],
        "page_errors": [],
        "posts": [],
    }
    exit_code = 1
    workdir = Path(tempfile.mkdtemp(prefix="b4-workbench-"))
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(workdir / "profile"), headless=True,
                viewport={"width": 1440, "height": 900}, accept_downloads=True)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                logs = shared.collect(page)
                posts: list = []

                def capture(request) -> None:
                    if request.method == "POST":
                        posts.append(request.url.split("?", 1)[0])

                page.on("request", capture)

                def view(name: str) -> None:
                    probe = page.evaluate(OVERFLOW_PROBE)
                    stages = page.evaluate(STAGE_PROBE)
                    rel = f"{name}.png"
                    page.screenshot(path=str(OUT / rel), full_page=True)
                    observed["views"].append({"name": name, "overflow": probe, "stages": stages,
                                              "screenshot": rel})

                # --- 1. import real bearing package through the real UI
                page.goto(base, wait_until="networkidle")
                page.set_input_files("#import-file", str(BEARING_PKG))
                page.wait_for_function(
                    "() => { const node = document.getElementById('home-status');"
                    " return node && node.textContent.indexOf('已导入') >= 0; }", timeout=60_000)
                rows = page.locator("#project-list .project-row").count()
                assert rows >= 1, "imported project not listed"
                page.locator("#project-list .project-row").first.locator(
                    "button, a").first.click(timeout=20_000)
                page.wait_for_selector("#project-view:not([hidden])", timeout=30_000)

                # --- 2. four-stage contract on the real restored project
                stages = page.evaluate(STAGE_PROBE)
                nav_ids = [item["id"] for item in stages["nav"]]
                assert nav_ids == ["intake", "plan", "make", "deliver"], f"stage nav {nav_ids}"
                assert set(stages["panels"]) == {"intake", "plan", "make", "deliver"}, stages["panels"]
                assert not stages["legacy_review_list"] and not stages["legacy_attempt_list"]
                assert stages["task_rows"], "task list empty on restored project"
                view("stage-intake-1440")

                stage_nav.goto(page, "make")
                stages = page.evaluate(STAGE_PROBE)
                assert stages["task_rows"], "task list must render in make"
                assert all(row["thumb"] for row in stages["task_rows"]), stages["task_rows"]
                assert stages["compare"] and stages["compare"]["shot_id"], "no persistent compare detail"
                shot_ids = [row["shot"] for row in stages["task_rows"]]
                log(f"make task rows: {shot_ids}")

                # viewed shot selection drives persistent detail; storage unchanged
                docs_before = page.evaluate(DOC_COUNT_PROBE)
                target = shot_ids[0]
                shared.select_make_shot(page, target)
                stages = page.evaluate(STAGE_PROBE)
                assert stages["compare"]["shot_id"] == target, stages["compare"]
                assert stages["shot_execution"] and stages["shot_execution"]["shot_id"] == target
                view("make-single-1440")

                # --- 3. scope semantics (no POST on any of these interactions)
                posts.clear()
                scope_single = page.evaluate(STAGE_PROBE)
                assert scope_single["mode_single"] and scope_single["mode_batch"], "mode controls missing"
                single_count = (scope_single["scope_count"] or "").strip()
                assert "1" in single_count, f"default single count {single_count!r}"
                viewed = shared.make_viewed_shot(page)
                assert viewed == target, (viewed, target)

                # switch viewed shot twice; count stays 1 and follows viewed shot
                second = shot_ids[1] if len(shot_ids) > 1 else target
                shared.select_make_shot(page, second)
                after_switch = page.evaluate(STAGE_PROBE)
                assert shared.make_viewed_shot(page) == second
                assert "1" in (after_switch["scope_count"] or ""), after_switch["scope_count"]
                assert not posts, f"viewed-shot change caused POSTs: {posts}"
                assert page.evaluate(DOC_COUNT_PROBE) == docs_before, "viewing rewrote storage"

                # explicit batch: checkboxes, independence, empty range, no POST
                batch_two = shot_ids[:2] if len(shot_ids) > 2 else shot_ids
                count = shared.choose_make_batch(page, batch_two)
                assert count == len(batch_two), count
                viewed_before_batch_switch = shared.make_viewed_shot(page)
                other = [sid for sid in shot_ids if sid not in batch_two][0]
                shared.select_make_shot(page, other)
                after_indep = page.evaluate(STAGE_PROBE)
                assert shared.make_viewed_shot(page) == other
                still_checked = page.evaluate(
                    "() => [...document.querySelectorAll('input[data-batch-shot]:checked')]"
                    ".map((el) => el.getAttribute('data-batch-shot'))")
                assert sorted(still_checked) == sorted(batch_two), still_checked
                assert f"{len(batch_two)}" in (after_indep["scope_count"] or ""), after_indep["scope_count"]
                assert not posts, f"batch mode/range change caused POSTs: {posts}"
                view("make-batch-1440")

                # empty range: uncheck all -> count 0, no fallback to all
                page.locator("#make-mode-batch").check()
                for sid in batch_two:
                    page.locator(f'input[data-batch-shot="{sid}"]').uncheck()
                page.wait_for_function(
                    "() => { const node = document.getElementById('generation-scope-count');"
                    " return node && node.textContent.includes('0'); }", timeout=10_000)
                checked_now = page.evaluate(
                    "() => [...document.querySelectorAll('input[data-batch-shot]:checked')].length")
                assert checked_now == 0, checked_now
                assert not posts, f"empty-range change caused POSTs: {posts}"
                view("make-batch-empty-1440")

                # back to single
                page.locator("#make-mode-single").check()
                page.wait_for_function(
                    "() => { const node = document.getElementById('generation-scope-count');"
                    " return node && node.textContent.includes('1'); }", timeout=10_000)

                # --- 4. other stage surfaces reachable from restored data
                stage_nav.goto(page, "plan")
                assert page.locator("#stage-panels [data-stage-panel=plan]:not([hidden])").count() == 1
                view("stage-plan-1440")
                stage_nav.goto(page, "deliver")
                assert page.locator("#stage-panels [data-stage-panel=deliver]:not([hidden])").count() == 1
                view("stage-deliver-1440")
                stage_nav.goto(page, "intake")
                view("stage-intake-restored-1440")

                # --- 5. responsive matrix (same profile, viewport changes)
                for width, height, name in ((1366, 768, "make-1366"), (1024, 768, "make-1024"),
                                            (390, 844, "make-390")):
                    page.set_viewport_size({"width": width, "height": height})
                    stage_nav.goto(page, "make")
                    page.wait_for_timeout(300)
                    narrow = page.evaluate(STAGE_PROBE)
                    probe = page.evaluate(OVERFLOW_PROBE)
                    assert probe["scroll_width"] <= probe["client_width"] + 1, (name, probe)
                    if width <= 900:
                        assert narrow["make_shot_select"] and narrow["make_shot_select"]["visible"], \
                            (name, narrow["make_shot_select"])
                        if narrow["make_shot_select"].get("options"):
                            shared.select_make_shot(page, narrow["make_shot_select"]["options"][-1])
                            assert shared.make_viewed_shot(page) == narrow["make_shot_select"]["options"][-1]
                    else:
                        assert narrow["make_shot_select"] is None or not narrow["make_shot_select"]["visible"], \
                            (name, narrow["make_shot_select"])
                    view(name)
                # --- 5b. long unbroken warning stress on the CURRENT workbench:
                # 归档因果（overflow/causality.json）只证旧 UI 同机制长串；
                # 这里在当前 make 页确认单/风险区注入同机制长串（纯 DOM 注入，
                # 不写存储、不改警告原文），断换行规则罩住、移除后恢复。
                page.set_viewport_size({"width": 1440, "height": 900})
                stage_nav.goto(page, "make")
                long_stress = page.evaluate(
                    """() => {
                      const host = document.getElementById("confirm-blockers")
                        || document.getElementById("confirm-risks")
                        || document.getElementById("confirm-summary");
                      if (!host) return null;
                      const node = document.createElement("p");
                      node.id = "__b4_long_stress";
                      node.className = "confirm-risk";
                      node.textContent = "LONGSTRESS" + "VeryLongUnbrokenEnglishWarningWithoutSpaces".repeat(40);
                      host.appendChild(node);
                      return {
                        scroll_width: document.documentElement.scrollWidth,
                        client_width: document.documentElement.clientWidth,
                      };
                    }""")
                assert long_stress is not None, "confirm risk host missing on current make page"
                assert long_stress["scroll_width"] <= long_stress["client_width"] + 1, long_stress
                page.screenshot(path=str(OUT / "make-longstress-1440.png"), full_page=True)
                observed["views"].append({"name": "make-longstress-1440",
                                          "overflow": long_stress,
                                          "screenshot": "make-longstress-1440.png"})
                page.evaluate(
                    """() => { document.getElementById("__b4_long_stress")?.remove(); }""")
                restored = page.evaluate(OVERFLOW_PROBE)
                assert restored["scroll_width"] <= restored["client_width"] + 1, restored
                page.set_viewport_size({"width": 1440, "height": 900})
            finally:
                observed["console_errors"] = logs["console"]
                observed["page_errors"] = logs["page"]
                context.close()
    finally:
        server.stop()
        observed["finished_at"] = datetime.now(timezone.utc).isoformat()

    exit_code = 0
    dump("b4-workbench-observed.json", observed)
    return exit_code


def zoom_runs() -> int:
    """125%/200% 原生浏览器缩放证据（合同口径）：启动前写 profile Preferences
    partition.default_zoom_level x=log(zoom)/log(1.2)，no_viewport=True 实窗，
    outerWidth==窗口宽、DPR==zoom、visualScale==1、CSS zoom==1、无transform；
    不以缩视口/等效CSS视口冒充原生缩放。沿用 formal-development-20261005 包烟囱法。
    """
    import math
    from playwright.sync_api import sync_playwright

    raw = BEARING_PKG.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PKG_SHA
    results: dict = {"observed_at": datetime.now(timezone.utc).isoformat(), "runs": [],
                     "real_model_calls": 0, "method": "native-browser-zoom"}
    exit_code = 1
    port = shared.free_port()
    server, _providers = shared.start_product_server(port)
    base = f"http://127.0.0.1:{port}/"
    try:
        with sync_playwright() as pw:
            for zoom, window_width in ((1.25, 1440), (2.0, 1366)):
                profile = Path(tempfile.mkdtemp(prefix="b4-zoom-native-"))
                preferences = profile / "Default" / "Preferences"
                preferences.parent.mkdir(parents=True, exist_ok=True)
                preferences.write_text(json.dumps({"partition": {
                    "default_zoom_level": {"x": math.log(zoom) / math.log(1.2)}}}),
                    encoding="utf-8")
                context = pw.chromium.launch_persistent_context(
                    str(profile), channel="chrome", headless=True, no_viewport=True,
                    args=["--force-device-scale-factor=1",
                          f"--window-size={window_width},900"],
                    accept_downloads=True)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    logs = shared.collect(page)
                    page.goto(base, wait_until="networkidle")
                    metrics = page.evaluate("""() => ({
                        innerWidth, innerHeight, outerWidth, outerHeight,
                        dpr: devicePixelRatio,
                        visualScale: visualViewport.scale,
                        cssZoom: getComputedStyle(document.documentElement).zoom,
                        transform: getComputedStyle(document.documentElement).transform
                    })""")
                    assert abs(metrics["dpr"] - zoom) < 0.02, metrics
                    assert metrics["outerWidth"] == window_width, metrics
                    assert metrics["visualScale"] == 1 and metrics["cssZoom"] == "1", metrics
                    assert metrics["transform"] == "none", metrics
                    page.set_input_files("#import-file", str(BEARING_PKG))
                    page.wait_for_function(
                        "() => { const node = document.getElementById('home-status');"
                        " return node && node.textContent.indexOf('已导入') >= 0; }",
                        timeout=60_000)
                    page.locator("#project-list .project-row").first.locator(
                        "button, a").first.click(timeout=20_000)
                    page.wait_for_selector("#project-view:not([hidden])", timeout=30_000)
                    stage_nav.goto(page, "make")
                    page.wait_for_timeout(400)
                    probe = page.evaluate(OVERFLOW_PROBE)
                    stages = page.evaluate(STAGE_PROBE)
                    width = probe["inner_width"]
                    if width is not None and width <= 900:
                        assert stages["make_shot_select"] and stages["make_shot_select"]["visible"], stages["make_shot_select"]
                        target = stages["make_shot_select"]["options"][-1]
                    else:
                        assert stages["task_rows"], stages
                        target = stages["task_rows"][0]["shot"]
                    shared.select_make_shot(page, target)
                    entry = {
                        "zoom": zoom, "window_width": window_width, "metrics": metrics,
                        "viewport": [probe["inner_width"], probe.get("client_width")],
                        "overflow": probe,
                        "task_rows": len(stages["task_rows"]),
                        "selected": shared.make_viewed_shot(page),
                        "console_errors": logs["console"], "page_errors": logs["page"],
                        "screenshot": f"make-zoom-{int(zoom * 100)}.png",
                    }
                    page.screenshot(path=str(OUT / entry["screenshot"]), full_page=True)
                    results["runs"].append(entry)
                    assert entry["selected"] == target
                    assert probe["scroll_width"] <= probe["client_width"] + 1, (zoom, probe)
                finally:
                    context.close()
                    shutil.rmtree(profile, ignore_errors=True)
        exit_code = 0
    finally:
        server.stop()
        dump("b4-zoom-observed.json", results)
    return exit_code


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--zoom":
        sys.exit(zoom_runs())
    sys.exit(main())
