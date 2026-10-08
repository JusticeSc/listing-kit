#!/usr/bin/env python
"""Browser verification of the S4 delivery check screen (D4.11).

Boots the shipped product server with injected fake providers and drives the
browser through: incomplete selection -> S4 blocked with a precise return path
-> 返回审核 -> adopt the last candidate -> S4 clean check (no export written)
-> S4 usability at 390px / 200% zoom / keyboard -> 导出交付包 -> export
location + 打开文件夹 consuming the completed version.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
for entry in (str(ROOT), str(TOOLS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from app.product_v1_server import ProductApplication, create_product_server
from src.workspace_store import WorkspaceStore
from tools.verify_product_v1_image_generation import (
    FIRST_KEY,
    FakeImageProvider,
    GenerationFixture,
    Submission,
    require_ok,
)
from tools.verify_product_v1_selection_rework_export import (
    restore_platform_checks,
    use_stub_platform_checks,
)

EVIDENCE = ROOT / "evals" / "product-demo"
SESSION_KEY = "amzListingKit.productV1.workspaceDirectory"
DELIVERY_KEY = "amzListingKit.productV1.deliveryDirectory"


class RegistryCompatibleFakeImageProvider(FakeImageProvider):
    """Fake provider that reports the shipped registry identity."""

    provider_id = "dashscope-qwen-image"
    model_id = "qwen-image-3.0"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("缺少 Playwright：请按脚本用法安装临时浏览器依赖。")
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    fixture = GenerationFixture()
    fixture.setUp()
    failures: list[str] = []
    result: dict[str, object] = {"stamp": stamp}
    real_module = use_stub_platform_checks()
    try:
        provider = RegistryCompatibleFakeImageProvider()
        fixture.image_provider = provider
        provider.plan_submissions([
            Submission("SUCCEEDED", f"delivery-ui-initial-{index}") for index in range(1, 4)
        ])
        require_ok(fixture.start(FIRST_KEY), "start whole-set generation")

        projection = fixture.projection()
        shots = projection["plan"]["shot_specs"]
        for shot in shots[:2]:
            revision = fixture.projection()["workspace"]["revision"]
            require_ok(fixture.service.save_shot_selection(
                fixture.workspace, expected_etag=revision, shot_id=shot["id"],
                candidate_sha256=shot["candidates"][0]["candidate_id"],
            ), "select candidate")
        missing_shot = shots[2]
        result["partial_selection"] = 2

        with tempfile.TemporaryDirectory(prefix="amz-product-v1-delivery-ui-") as raw:
            revealed: list[str] = []
            application = ProductApplication(
                service=fixture.service,
                recent_index_path=Path(raw) / "recent-workspaces.json",
                reveal_opener=revealed.append,
            )
            server = create_product_server("127.0.0.1", 0, application=application)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            external_requests: list[str] = []
            try:
                with sync_playwright() as driver:
                    browser = driver.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})

                    def watch(request):
                        host = urlsplit(request.url).hostname
                        if host not in ("127.0.0.1", "localhost"):
                            external_requests.append(request.url)

                    page.on("request", watch)
                    console_errors: list[str] = []

                    def watch_console(message):
                        if message.type == "error":
                            console_errors.append(message.text)

                    page.on("console", watch_console)
                    page.on("pageerror", lambda error: console_errors.append(str(error)))
                    page.goto(base_url + "/", wait_until="load")
                    page.evaluate(
                        "([workspaceKey, deliveryKey, value]) => {"
                        " window.sessionStorage.setItem(workspaceKey, value);"
                        " window.sessionStorage.setItem(deliveryKey, value); }",
                        [SESSION_KEY, DELIVERY_KEY, str(fixture.workspace)],
                    )
                    page.reload(wait_until="load")

                    # 1. Restored delivery screen with an incomplete selection is blocked.
                    page.wait_for_selector("#delivery-screen:not([hidden])", timeout=30000)
                    page.wait_for_selector("#delivery-blockers:not([hidden])", timeout=30000)
                    blockers = page.locator("#delivery-blocker-list").inner_text()
                    result["blocked_message"] = blockers
                    if missing_shot["title"] not in blockers:
                        failures.append("交付检查没有指出未选定的图片：" + blockers)
                    if not page.locator("#export-delivery").is_disabled():
                        failures.append("未选全时导出交付包按钮没有被禁用")
                    store = WorkspaceStore.open(fixture.workspace)
                    if store.list_records("export"):
                        failures.append("打开交付检查不应写入任何 ExportVersion")
                    page.screenshot(
                        path=str(EVIDENCE / f"ui-delivery-{stamp}-blocked.png"), full_page=True,
                    )

                    # 2. 返回审核 goes back to the review screen.
                    page.click("#delivery-back")
                    page.wait_for_selector("#intake-screen:not([hidden])", timeout=10000)
                    if page.locator("#delivery-screen").is_visible():
                        failures.append("返回审核后交付检查仍然可见")

                    # 3. Adopt the last missing candidate through the review workbench.
                    page.click(
                        '#generation-shots .generation-shot[data-shot-id="%s"]'
                        % missing_shot["id"])
                    page.wait_for_selector(
                        "#review-candidates .review-candidate-button", timeout=20000)
                    page.click("#review-candidates .review-candidate-button")
                    page.locator("#review-adopt").click()
                    page.wait_for_function(
                        "() => document.querySelector('#selection-progress').textContent.startsWith('3/3')",
                        timeout=20000)
                    page.wait_for_selector("#export-selection:not([disabled])", timeout=20000)

                    # 4. Clean delivery check: nothing is written before 导出交付包.
                    page.click("#export-selection")
                    page.wait_for_selector("#delivery-screen:not([hidden])", timeout=30000)
                    page.wait_for_selector("#export-delivery:not([disabled])", timeout=30000)
                    selected_items = page.locator("#delivery-selected .delivery-selected-item").count()
                    result["selected_items"] = selected_items
                    if selected_items != 3:
                        failures.append(f"交付检查显示 {selected_items} 张已选图片，期望 3")
                    if page.locator("#delivery-consistency:not([hidden])").count():
                        failures.append("干净交付不应出现一致性问题")
                    hard_text = page.locator("#delivery-hard-list").inner_text()
                    result["hard_checks"] = hard_text
                    if "通过" not in hard_text:
                        failures.append("硬检查摘要没有显示通过：" + hard_text)
                    if page.locator("#reveal-export").is_visible():
                        failures.append("导出前不应出现打开文件夹入口")
                    page.wait_for_timeout(300)
                    if WorkspaceStore.open(fixture.workspace).list_records("export"):
                        failures.append("打开交付检查不应写入 ExportVersion")
                    page.screenshot(
                        path=str(EVIDENCE / f"ui-delivery-{stamp}-ready.png"), full_page=True,
                    )

                    # 4b. S4 可用性：390px 无横向溢出；200% 缩放下按钮可见可点；键盘可聚焦。
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.wait_for_timeout(250)
                    s4_390 = page.evaluate(
                        "() => ({scrollWidth: document.documentElement.scrollWidth,"
                        " innerWidth: window.innerWidth})"
                    )
                    result["delivery_390px"] = s4_390
                    if s4_390["scrollWidth"] > s4_390["innerWidth"] + 1:
                        failures.append(f"交付检查屏 390px 视口横向溢出：{s4_390}")
                    page.screenshot(
                        path=str(EVIDENCE / f"ui-delivery-{stamp}-ready-390.png"),
                        full_page=True,
                    )
                    page.set_viewport_size({"width": 720, "height": 500})
                    page.wait_for_timeout(250)
                    zoom = page.evaluate(
                        """() => {
                          const check = (selector) => {
                            const el = document.querySelector(selector);
                            if (!el) { return { selector, found: false }; }
                            el.scrollIntoView({ block: 'center', behavior: 'instant' });
                            const rect = el.getBoundingClientRect();
                            const hit = document.elementFromPoint(
                              rect.left + rect.width / 2, rect.top + rect.height / 2);
                            return {
                              selector,
                              found: true,
                              insideViewport: rect.width > 0 && rect.height > 0 &&
                                rect.left >= -1 && rect.top >= -1 &&
                                rect.right <= window.innerWidth + 1 &&
                                rect.bottom <= window.innerHeight + 1,
                              hittable: Boolean(hit) && (el === hit || el.contains(hit) ||
                                hit.contains(el)),
                            };
                          };
                          return ['#delivery-back', '#export-delivery'].map(check);
                        }"""
                    )
                    result["delivery_zoom200"] = zoom
                    for item in zoom:
                        if not item.get("found"):
                            failures.append(f"交付检查屏缺少 {item['selector']}")
                        elif not item.get("insideViewport") or not item.get("hittable"):
                            failures.append(
                                f"200% 缩放下 {item['selector']} 不可见或不可点：{item}")
                    zoom_overflow = page.evaluate(
                        "() => ({scrollWidth: document.documentElement.scrollWidth,"
                        " innerWidth: window.innerWidth})"
                    )
                    result["delivery_zoom200_overflow"] = zoom_overflow
                    if zoom_overflow["scrollWidth"] > zoom_overflow["innerWidth"] + 1:
                        failures.append(f"交付检查屏 200% 缩放横向溢出：{zoom_overflow}")
                    page.screenshot(
                        path=str(EVIDENCE / f"ui-delivery-{stamp}-ready-zoom200.png"),
                        full_page=True,
                    )
                    focus_start = page.evaluate(
                        "() => { const el = document.querySelector('#delivery-back');"
                        " if (!el) { return 'missing'; } el.focus();"
                        " return document.activeElement === el ? 'focused' : 'failed'; }"
                    )
                    result["delivery_keyboard_focus_start"] = focus_start
                    if focus_start == "focused":
                        reached_export = False
                        for _ in range(40):
                            page.keyboard.press("Tab")
                            active = page.evaluate(
                                "() => (document.activeElement && document.activeElement.id) || ''")
                            if active == "export-delivery":
                                reached_export = True
                                break
                        result["delivery_keyboard_reached_export"] = reached_export
                        if not reached_export:
                            failures.append("交付检查屏键盘无法到达导出按钮")
                    else:
                        failures.append("交付检查屏返回按钮无法通过键盘聚焦")
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.wait_for_timeout(200)

                    # 5. 导出交付包 writes one version and exposes the export location.
                    page.click("#export-delivery")
                    page.wait_for_selector("#export-summary:not([hidden])", timeout=60000)
                    page.wait_for_selector("#reveal-export", state="visible", timeout=20000)
                    records = WorkspaceStore.open(fixture.workspace).list_records("export")
                    result["exports_after_export"] = len(records)
                    if len(records) != 1:
                        failures.append(f"导出后有 {len(records)} 个导出版本，期望 1")
                    record = records[0]
                    summary = page.locator("#export-summary").inner_text()
                    result["summary"] = summary
                    if record["relative_path"] not in summary:
                        failures.append("导出结果没有显示导出位置：" + summary)
                    status = page.locator("#delivery-status").inner_text()
                    result["status"] = status
                    if "已导出" not in status:
                        failures.append("导出后没有成功反馈：" + status)
                    page.screenshot(
                        path=str(EVIDENCE / f"ui-delivery-{stamp}-exported.png"), full_page=True,
                    )

                    # 6. 打开文件夹 consumes the completed ExportVersion projection.
                    page.click("#reveal-export")
                    deadline = time.monotonic() + 10
                    while not revealed and time.monotonic() < deadline:
                        page.wait_for_timeout(200)
                    expected_dir = str(fixture.workspace / record["relative_path"])
                    result["revealed"] = revealed
                    if not revealed or expected_dir not in revealed[0]:
                        failures.append("打开文件夹没有消费已完成的导出版本")
                    browser.close()
                    result["console_errors"] = console_errors
                    if console_errors:
                        failures.append(
                            "发现未解释的 console error：" + " | ".join(console_errors[:5]))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            result["external_requests"] = external_requests
            if external_requests:
                failures.append("浏览器访问了产品以外的地址：" + ", ".join(external_requests))
    finally:
        restore_platform_checks(real_module)
        fixture.tearDown()

    result["failures"] = failures
    result["passed"] = not failures
    report_path = EVIDENCE / f"ui-delivery-{stamp}.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
