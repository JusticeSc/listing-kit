from playwright.sync_api import sync_playwright
errors = []
shot = "E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit/evals/product-demo/d2-r1e/loop"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8779/", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    pg.click("button[data-action=load-example]")
    pg.wait_for_timeout(600)
    pg.check("#confirm-input")
    pg.wait_for_timeout(300)
    pg.click("#input-form button[type=submit]")
    pg.wait_for_function("document.querySelector(\"#plan-status\").textContent.includes(\"v1\")", timeout=8000)
    print("plan-ready:", pg.locator("#plan-status").inner_text(), flush=True)
    print("shots:", pg.locator(".shot-card").count(), flush=True)
    pg.screenshot(path=shot + "-plan-2026-09-27.png")
    pg.click("button[data-action=generate-set]")
    pg.wait_for_function("document.querySelector(\"#stage-chip\").textContent.includes(\"审核\")", timeout=30000)
    print("review-stage:", pg.locator("#stage-chip").inner_text(), flush=True)
    pg.screenshot(path=shot + "-review-2026-09-27.png")
    done = pg.evaluate("""async () => {
      const svc = window.__mockService;
      const st = svc.getState();
      for (const s of st.plan.shots.filter(x => x.status === "READY" && x.candidates.length)) {
        await svc.focusShot(s.id);
        const c = s.candidates[0].id;
        await svc.focusCandidate(c);
        for (const f of ["F4", "F7", "F8"]) { svc.reviewFact(s.id, c, f, "pass"); }
        svc.reviewVisual(s.id, c, "keep");
        svc.selectCandidate(s.id, c);
      }
      return svc.getState().task.phase;
    }""")
    print("after-select-phase:", done, flush=True)
    print("delivery:", pg.locator("#delivery-view").inner_text()[:120], flush=True)
    pg.screenshot(path=shot + "-selected-2026-09-27.png")
    pg.click("button[data-action=export]")
    pg.wait_for_timeout(1200)
    print("dialog-open:", pg.evaluate("document.querySelector(\"#export-dialog\").open"), flush=True)
    print("dialog-body:", pg.locator("#export-dialog-body").inner_text()[:200], flush=True)
    pg.screenshot(path=shot + "-export-2026-09-27.png")
    print("ERRORS:", len(errors), flush=True)
    for e in errors[:10]:
        print("ERR:", e[:300], flush=True)
    b.close()
print("FULL-LOOP-DONE", flush=True)

