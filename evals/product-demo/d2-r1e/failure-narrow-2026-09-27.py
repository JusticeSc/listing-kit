from playwright.sync_api import sync_playwright
errors = []
base = "E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit/evals/product-demo/d2-r1e/fail"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8779/?scenario=partial", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    pg.click("button[data-action=load-example]")
    pg.wait_for_timeout(500)
    pg.check("#confirm-input")
    pg.wait_for_timeout(300)
    pg.click("#input-form button[type=submit]")
    pg.wait_for_function("document.querySelector(\"#plan-status\").textContent.includes(\"v1\")", timeout=8000)
    pg.click("button[data-action=generate-set]")
    pg.wait_for_function("window.__mockService.getState().plan.status === \"PARTIAL\"", timeout=30000)
    st = pg.evaluate("() => { const s = window.__mockService.getState().plan.shots; return s.map(x => x.id + \":\" + x.status).join(\",\"); }")
    print("partial-states:", st, flush=True)
    pg.screenshot(path=base + "-partial-2026-09-27.png")
    pg.evaluate("async () => { const s = window.__mockService.getState().plan.shots.find(x => x.id === \"S4\"); await window.__mockService.focusShot(s.id); }")
    pg.wait_for_timeout(400)
    pg.click("button[data-action=reconcile-shot]")
    pg.wait_for_function("window.__mockService.getState().plan.shots.find(x => x.id === \"S4\").status === \"FAILED\"", timeout=8000)
    print("s4-reconciled-to-failed: True", flush=True)
    rec = pg.evaluate("""async () => { const svc = window.__mockService;
      await svc.reworkShot("S3", "scene", "重新给出清晰杯盖细节");
      await svc.reworkShot("S4", "technical", "保持方图并确保底部完整");
      const s = svc.getState().plan.shots; return s.map(x => x.id + ":" + x.status).join(","); }""")
    print("after-rework:", rec, flush=True)
    pg.screenshot(path=base + "-recovered-2026-09-27.png")
    np = b.new_page(viewport={"width": 390, "height": 844})
    np.on("console", lambda m: errors.append("narrow:" + m.text) if m.type == "error" else None)
    np.on("pageerror", lambda e: errors.append("narrow:" + str(e)))
    np.goto("http://127.0.0.1:8779/", wait_until="networkidle")
    np.wait_for_timeout(1200)
    w = np.evaluate("() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth })")
    print("narrow-overflow:", w, flush=True)
    np.screenshot(path=base + "-narrow-2026-09-27.png", full_page=True)
    print("ERRORS:", len(errors), flush=True)
    for e in errors[:10]:
        print("ERR:", e[:200], flush=True)
    b.close()
print("FAILURE-NARROW-DONE", flush=True)

