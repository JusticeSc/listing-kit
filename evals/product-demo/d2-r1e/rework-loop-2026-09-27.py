from playwright.sync_api import sync_playwright
errors = []
shot = "E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit/evals/product-demo/d2-r1e/rework"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8779/", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    pg.click("button[data-action=load-example]")
    pg.wait_for_timeout(500)
    pg.check("#confirm-input")
    pg.wait_for_timeout(300)
    pg.click("#input-form button[type=submit]")
    pg.wait_for_function("document.querySelector(\"#plan-status\").textContent.includes(\"v1\")", timeout=8000)
    pg.click("button[data-action=generate-set]")
    pg.wait_for_function("document.querySelector(\"#stage-chip\").textContent.includes(\"审核\")", timeout=30000)
    before = pg.evaluate("""() => { const st = window.__mockService.getState();
      return { s1cands: st.plan.shots.find(x => x.id === "S1").candidates.length,
               others: st.plan.shots.filter(x => x.id !== "S1").map(x => x.id + ":" + x.candidates.length + "/" + x.attempts.length).join(",") }; }""")
    print("before:", before, flush=True)
    pg.evaluate("""async () => { await window.__mockService.focusShot("S1"); }""")
    pg.wait_for_timeout(400)
    pg.check("#rework-form input[name=reason][value=scene]")
    pg.fill("#rework-direction", "背景更暖，但仍然干净无道具")
    pg.screenshot(path=shot + "-form-2026-09-27.png")
    pg.click("#rework-form button[type=submit]")
    pg.wait_for_function("window.__mockService.getState().plan.shots.find(x => x.id === \"S1\").candidates.length === 2", timeout=8000)
    after = pg.evaluate("""() => { const st = window.__mockService.getState();
      const s1 = st.plan.shots.find(x => x.id === "S1");
      return { s1cands: s1.candidates.map(c => c.id).join(","), s1status: s1.status,
               promptVers: s1.promptVersions.length,
               others: st.plan.shots.filter(x => x.id !== "S1").map(x => x.id + ":" + x.candidates.length + "/" + x.attempts.length).join(",") }; }""")
    print("after:", after, flush=True)
    print("isolation-kept:", before["others"] == after["others"], flush=True)
    pg.screenshot(path=shot + "-done-2026-09-27.png")
    tail = pg.evaluate("""async () => { const svc = window.__mockService;
      const st = svc.getState();
      for (const s of st.plan.shots.filter(x => x.candidates.length)) {
        await svc.focusShot(s.id);
        const c = s.candidates[s.candidates.length - 1].id;
        await svc.focusCandidate(c);
        for (const f of ["F4", "F7", "F8"]) { svc.reviewFact(s.id, c, f, "pass"); }
        svc.reviewVisual(s.id, c, "keep");
        svc.selectCandidate(s.id, c);
      }
      await svc.exportDelivery();
      return { phase: svc.getState().task.phase, files: svc.getState().export.files.map(f => f.name).join(",") };
    }""")
    print("export:", tail, flush=True)
    print("ERRORS:", len(errors), flush=True)
    for e in errors[:10]:
        print("ERR:", e[:300], flush=True)
    b.close()
print("REWORK-LOOP-DONE", flush=True)

