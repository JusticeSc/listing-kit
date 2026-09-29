from playwright.sync_api import sync_playwright
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8779/", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    print("title:", pg.title(), flush=True)
    print("has-load-example:", pg.locator("button[data-action=load-example]").count(), flush=True)
    print("has-product-name:", pg.locator("#product-name").count(), flush=True)
    print("has-ref-file:", pg.locator("#ref-file").count(), flush=True)
    print("stage:", pg.locator("#stage-chip").inner_text(), flush=True)
    print("input-status:", pg.locator("#input-status").inner_text(), flush=True)
    pg.screenshot(path="E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit/evals/product-demo/d2-r1e/blank-state-2026-09-27.png")
    pg.click("button[data-action=load-example]")
    pg.wait_for_timeout(800)
    print("after-example-title:", pg.title(), flush=True)
    print("example-refs:", pg.locator(".reference-card").count(), flush=True)
    pg.screenshot(path="E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit/evals/product-demo/d2-r1e/example-loaded-2026-09-27.png")
    print("ERRORS:", len(errors), flush=True)
    for e in errors[:10]:
        print("ERR:", e[:300], flush=True)
    b.close()
print("RENDER-CHECK-DONE", flush=True)

