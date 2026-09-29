# -*- coding: utf-8 -*-
"""v3 原型走查验证 · 第二组（因果、边界、异常路径）"""
import asyncio, json, pathlib
from playwright.async_api import async_playwright

BASE = pathlib.Path(r"E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit/evals/product-demo/d2-r1g")
HTML = (BASE / "frontend-v3-2026-09-28.html").as_uri()
SHOT = BASE / "screenshots"

async def load_fixture(pg, fid):
    await pg.click("summary:has-text('加载示例商品')")
    await pg.click("button[data-act=load][data-val=%s]" % fid)
    await pg.wait_for_timeout(250)
    await pg.click("button[data-act=analyze]")
    await pg.wait_for_timeout(250)
    await pg.click("button[data-act=confirmBrief]")
    await pg.wait_for_timeout(250)

async def main():
    r = {}; errors = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1440, "height": 900})
        pg.on("console", lambda m: errors.append("console." + m.type + ": " + m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        await pg.goto(HTML); await pg.wait_for_timeout(400)

        # 1) 未支持输入：填齐资料后仍停在明确位置
        await pg.fill("#inName", "某品牌保温壶")
        await pg.fill("#inCat", "保温壶")
        await pg.click("button[data-act=addPoint]")
        await pg.wait_for_timeout(150)
        await pg.fill("input[data-pt='0']", "双盖设计，单手开合")
        async with pg.expect_file_chooser() as fc:
            await pg.click("button[data-act=addRef]")
        fcv = await fc.value
        await fcv.set_files(r"E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit/evals/product-demo/product-2/bex-02/raw.png")
        await pg.wait_for_timeout(300)
        r["unsupported_analyze_enabled"] = await pg.locator("button[data-act=analyze]").is_enabled()
        await pg.click("button[data-act=analyze]")
        await pg.wait_for_timeout(350)
        r["unsupported_notice"] = await pg.locator(".notice-warn").count()
        r["still_intake"] = (await pg.inner_text(".stg.cur b")).strip()
        await pg.screenshot(path=str(SHOT / "v3-15-unsupported.png"))

        # 2) 载入 Aster，先调全组视觉再生成（因果：提示词随视觉变化）
        await load_fixture(pg, "aster")
        await pg.click("button[data-act=styleEdit]")
        await pg.wait_for_selector("select[data-sk=tone]")
        await pg.select_option("select[data-sk=tone]", label="冷调极简")
        await pg.fill("#styleExtra", "主光方向保持左上，避免镜面高光")
        await pg.click("button[data-act=saveStyle]")
        await pg.wait_for_timeout(300)
        await pg.click(".shot >> nth=0 >> summary")
        blocks = await pg.inner_text(".shot >> nth=0 >> .blocks")
        r["style_in_prompt"] = ("cool minimal tone" in blocks) and ("Additional note" in blocks)
        r["style_bar"] = (await pg.inner_text(".stylebar")).replace("\n", " ")[:80]
        await pg.screenshot(path=str(SHOT / "v3-16-style-updated.png"), full_page=True)

        # 3) 生成后改提示词 → 只有该张标记需更新
        await pg.click("button[data-act=generate]")
        await pg.wait_for_selector("button[data-act=adopt]", timeout=25000)
        await pg.click("button[data-act=openPrompt]")
        await pg.wait_for_selector("#pb_comp")
        old = await pg.input_value("#pb_comp")
        await pg.fill("#pb_comp", old + " Keep the product centred with generous margins.")
        await pg.click("button[data-act=savePrompt]")
        await pg.wait_for_timeout(300)
        r["stale_after_prompt"] = await pg.evaluate("window.__ui.state().stale")
        r["prompt_btn"] = (await pg.inner_text("button[data-act=openPrompt]")).strip()
        await pg.screenshot(path=str(SHOT / "v3-17-stale-after-prompt.png"))

        # 4) 生成后改全组视觉 → 全部待更新；再按单张更新
        await pg.click("button[data-act=navBack][data-val=plan]")
        await pg.wait_for_timeout(300)
        await pg.click("button[data-act=styleEdit]")
        await pg.select_option("select[data-sk=mood]", label="棚拍极简，结构优先")
        await pg.click("button[data-act=saveStyle]")
        await pg.wait_for_timeout(300)
        r["stale_after_style"] = await pg.evaluate("window.__ui.state().stale")
        r["plan_stale_chips"] = await pg.locator(".shot .chip-warn").count()
        r["plan_update_buttons"] = await pg.locator("button[data-act=updateShot]").count()
        r["plan_generate_label"] = (await pg.inner_text("button[data-act=generate]")).strip()
        await pg.screenshot(path=str(SHOT / "v3-18-stale-plan.png"), full_page=True)
        await pg.click("button[data-act=updateShot] >> nth=0")
        await pg.wait_for_timeout(1900)
        r["stale_after_single_update"] = await pg.evaluate("window.__ui.state().stale")
        await pg.click("button[data-act=gotoReview]")
        await pg.wait_for_timeout(300)
        await pg.click(".railbtn >> nth=1")
        r["review_stale_note"] = await pg.locator(".note-warn").count()
        await pg.screenshot(path=str(SHOT / "v3-18b-stale-review.png"))

        # 5) 第 3 张返工 → 无素材时给「模拟返工候选」占位卡
        await pg.click(".railbtn >> nth=2")
        await pg.wait_for_timeout(200)
        await pg.click("button[data-act=rework]")
        await pg.wait_for_selector("#causes")
        await pg.click("input[value=frame]")
        await pg.click("button[data-act=submitRework]")
        await pg.wait_for_timeout(2200)
        r["placeholder_cards"] = await pg.locator(".phcard").count()
        r["cands_shot3"] = await pg.locator(".candbtn").count()
        await pg.screenshot(path=str(SHOT / "v3-19-rework-placeholder.png"))

        # 6) 结果未知 → 查证 → 重试
        await pg.click("#demoReset"); await pg.wait_for_timeout(300)
        await load_fixture(pg, "aster")
        await pg.click("button[data-scn=unknown]")
        await pg.click("button[data-act=generate]")
        await pg.wait_for_selector("button[data-act=verifyShot]", timeout=25000)
        r["unknown_tile"] = await pg.locator("button[data-act=verifyShot]").count()
        await pg.screenshot(path=str(SHOT / "v3-20-unknown.png"))
        await pg.click("button[data-act=verifyShot]")
        await pg.wait_for_selector("button[data-act=retryShot]", timeout=10000)
        r["verify_resolved_to_failed"] = (await pg.inner_text(".gt >> nth=0 >> .gimg")).replace("\n", " ")[:60]
        await pg.screenshot(path=str(SHOT / "v3-21-verified.png"))
        await pg.click("button[data-act=retryShot]")
        await pg.wait_for_selector("button[data-act=adopt]", timeout=25000)
        r["unknown_recovered"] = True

        # 7) Bex 提示词对照（展开后读取）
        await pg.click("#demoReset"); await pg.wait_for_timeout(300)
        await load_fixture(pg, "bex")
        r["bex_shots"] = await pg.locator(".shot").count()
        await pg.click(".shot >> nth=0 >> summary")
        bex = await pg.inner_text(".shot >> nth=0 >> .blocks")
        r["bex_prompt_has_cube"] = "cube-shaped" in bex
        r["bex_prompt_leaks_aster"] = ("tumbler" in bex) or ("teal" in bex)
        await pg.screenshot(path=str(SHOT / "v3-22-bex-prompt.png"), full_page=True)
        await b.close()

        # 8) 720px（约等于 200% 缩放后的可用宽度）
        b2 = await p.chromium.launch()
        pg2 = await b2.new_page(viewport={"width": 720, "height": 900})
        await pg2.goto(HTML); await pg2.wait_for_timeout(400)
        await load_fixture(pg2, "aster")
        r["zoom_720_overflow"] = await pg2.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        await pg2.click("button[data-act=generate]")
        await pg2.wait_for_selector("button[data-act=adopt]", timeout=25000)
        r["zoom_720_review_overflow"] = await pg2.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        await pg2.screenshot(path=str(SHOT / "v3-23-720-review.png"), full_page=False)
        await b2.close()

    r["console_errors"] = errors
    print(json.dumps(r, ensure_ascii=False, indent=1))

asyncio.run(main())
