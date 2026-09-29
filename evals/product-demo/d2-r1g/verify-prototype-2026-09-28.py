# -*- coding: utf-8 -*-
"""v3 原型走查验证（只读本地文件，零网络）"""
import asyncio, json, pathlib, sys
from playwright.async_api import async_playwright

BASE = pathlib.Path(r"E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit/evals/product-demo/d2-r1g")
HTML = (BASE / "frontend-v3-2026-09-28.html").as_uri()
SHOT = BASE / "screenshots"
SHOT.mkdir(exist_ok=True)

async def main():
    result = {}
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page(viewport={"width": 1440, "height": 900})
        pg.on("console", lambda m: errors.append("console." + m.type + ": " + m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        await pg.goto(HTML)
        await pg.wait_for_timeout(500)

        result["blank_analyze_disabled"] = await pg.locator("button[data-act=analyze]").is_disabled()
        result["blank_checkline"] = (await pg.inner_text("#checkline")).strip()
        await pg.screenshot(path=str(SHOT / "v3-01-blank.png"))

        await pg.click("summary:has-text('加载示例商品')")
        await pg.click("button[data-act=load][data-val=aster]")
        await pg.wait_for_timeout(400)
        result["after_load_checkline"] = (await pg.inner_text("#checkline")).strip()
        result["ref_img_loaded"] = await pg.evaluate("document.querySelector('#refgrid img').naturalWidth")
        await pg.screenshot(path=str(SHOT / "v3-02-intake-aster.png"))

        await pg.click("button[data-act=analyze]")
        await pg.wait_for_timeout(400)
        result["stage_after_analyze"] = (await pg.inner_text(".stg.cur b")).strip()
        await pg.screenshot(path=str(SHOT / "v3-03-brief.png"))

        await pg.click("button[data-act=confirmBrief]")
        await pg.wait_for_timeout(400)
        result["shot_cards"] = await pg.locator(".shot").count()
        await pg.click(".shot >> nth=0 >> summary")
        await pg.wait_for_timeout(250)
        prompt_text = await pg.inner_text(".shot >> nth=0 >> .blocks")
        result["prompt_has_lock"] = "exact same product" in prompt_text
        result["prompt_has_style"] = "Shared visual style" in prompt_text
        await pg.screenshot(path=str(SHOT / "v3-04-plan.png"), full_page=True)

        await pg.click("button[data-act=generate]")
        await pg.wait_for_timeout(700)
        await pg.screenshot(path=str(SHOT / "v3-05-generating.png"))
        await pg.wait_for_selector("button[data-act=adopt]", timeout=25000)
        await pg.wait_for_timeout(500)
        result["review_candidates_first"] = await pg.locator(".candbtn").count()
        await pg.screenshot(path=str(SHOT / "v3-06-review.png"))

        # 第二张重做
        await pg.click(".railbtn >> nth=1")
        await pg.wait_for_timeout(250)
        await pg.click("button[data-act=rework]")
        await pg.wait_for_selector("#causes")
        await pg.click("input[value=scene]")
        await pg.fill("#rwNote", "背景太满，希望更干净；保留杯盖两层阶梯。")
        await pg.wait_for_timeout(200)
        result["corr_preview"] = (await pg.inner_text("#corrPreview")).strip()[:60]
        await pg.screenshot(path=str(SHOT / "v3-07-rework-dialog.png"))
        await pg.click("button[data-act=submitRework]")
        await pg.wait_for_timeout(2200)
        result["cands_after_rework"] = await pg.locator(".candbtn").count()
        result["new_badge"] = await pg.locator(".candbtn .nn").count()
        await pg.click("button[data-act=toggleCompare]")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(SHOT / "v3-08-compare.png"))
        await pg.click("button[data-act=toggleCompare]")

        # 提示词高级区
        await pg.click("button[data-act=openPrompt]")
        await pg.wait_for_selector("#pb_style")
        result["prompt_dialog_version_note"] = (await pg.inner_text(".dlg-body .small")).strip()[:40]
        await pg.screenshot(path=str(SHOT / "v3-09-prompt-dialog.png"))
        await pg.click("button[data-act=closeModal]")

        # 逐张采用
        n = await pg.locator(".railbtn").count()
        for i in range(n):
            await pg.click(".railbtn >> nth=%d" % i)
            await pg.wait_for_timeout(200)
            btn = pg.locator("button[data-act=adopt]")
            if await btn.is_enabled():
                await btn.click()
                await pg.wait_for_timeout(250)
        result["adopted_all"] = await pg.evaluate("window.__ui.state().adopted")
        result["goto_delivery_enabled"] = await pg.locator("button[data-act=gotoDelivery]").is_enabled()
        await pg.click("button[data-act=gotoDelivery]")
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=str(SHOT / "v3-10-delivery.png"), full_page=True)
        await pg.click("button[data-act=export]")
        await pg.wait_for_selector("#expNote")
        result["export_dialog"] = (await pg.inner_text(".dlg-head b")).strip()
        await pg.screenshot(path=str(SHOT / "v3-11-export.png"))
        await pg.click("button[data-act=closeModal]")

        # 情形注入：局部失败
        await pg.click("#demoReset")
        await pg.wait_for_timeout(300)
        await pg.click("summary:has-text('加载示例商品')")
        await pg.click("button[data-act=load][data-val=aster]")
        await pg.click("button[data-act=analyze]")
        await pg.click("button[data-act=confirmBrief]")
        await pg.click("button[data-scn=partial]")
        await pg.click("button[data-act=generate]")
        await pg.wait_for_selector("button[data-act=retryShot]", timeout=25000)
        result["partial_failed_tile"] = await pg.locator("button[data-act=retryShot]").count()
        await pg.screenshot(path=str(SHOT / "v3-12-partial-failure.png"))
        await pg.click("button[data-act=retryShot]")
        await pg.wait_for_selector("button[data-act=adopt]", timeout=20000)

        # 情形注入：结果未知
        await pg.click("#demoReset")
        await pg.wait_for_timeout(300)
        await pg.click("summary:has-text('加载示例商品')")
        await pg.click("button[data-act=load][data-val=bex]")
        await pg.wait_for_timeout(300)
        result["bex_ref"] = await pg.evaluate("document.querySelector('#refgrid img').getAttribute('src')")
        await pg.click("button[data-act=analyze]")
        await pg.wait_for_timeout(300)
        brief_text = await pg.inner_text(".briefgrid")
        result["bex_brief_has_square"] = "直立方体" in brief_text
        result["bex_brief_has_cup_word"] = ("保温杯" in brief_text and "方形" not in brief_text)
        await pg.click("button[data-act=confirmBrief]")
        await pg.wait_for_timeout(300)
        result["bex_shots"] = await pg.locator(".shot").count()
        bex_prompt = await pg.inner_text(".shot >> nth=0 >> .blocks")
        result["bex_prompt_has_cube"] = "cube-shaped" in bex_prompt
        result["bex_prompt_leaks_aster"] = ("tumbler" in bex_prompt) or ("teal" in bex_prompt)
        await pg.screenshot(path=str(SHOT / "v3-13-bex-plan.png"), full_page=True)

        await browser.close()

        # 390px 窄屏
        browser2 = await p.chromium.launch()
        pg2 = await browser2.new_page(viewport={"width": 390, "height": 844})
        await pg2.goto(HTML)
        await pg2.wait_for_timeout(400)
        await pg2.click("summary:has-text('加载示例商品')")
        await pg2.click("button[data-act=load][data-val=aster]")
        await pg2.wait_for_timeout(300)
        await pg2.click("button[data-act=analyze]")
        await pg2.click("button[data-act=confirmBrief]")
        await pg2.wait_for_timeout(500)
        result["narrow_overflow"] = await pg2.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        await pg2.screenshot(path=str(SHOT / "v3-14-390-plan.png"))
        await browser2.close()

    result["console_errors"] = errors
    print(json.dumps(result, ensure_ascii=False, indent=1))

asyncio.run(main())
