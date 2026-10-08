# -*- coding: utf-8 -*-
"""窄视口布局判据：在真浏览器里量三档视口，不靠推理。

用法
----
    uv run --with playwright python evals/probes/viewport_probe.py

做法
----
用自带无头 Chromium 打开离线单页，依次在三个 CSS 视口下测量：
  1280x900   桌面三栏
   900x900   两栏（右栏移到候选画布下方）
   358x377   200% 浏览器缩放的布局 footprint（715x754 的 CSS 视口减半）
每一档都验：没有横向滚动；栅格列数与合同 §4.7.7 一致；「重置演示」可见。
截图存 evals/product-demo/d2-r1c/screenshots/。

边界：无头 Chromium 的 CSS 视口等价于浏览器缩放后的布局宽度，但不覆盖真机 DPI 与用户字体设置；
后两者属于 D2.R2 真人走查。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:8778/"
SHOTS = ROOT / "evals" / "product-demo" / "d2-r1c" / "screenshots"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("缺少 playwright：uv run --with playwright python evals/probes/viewport_probe.py")
        return 2

    problems: list = []
    readings = {}
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(URL, wait_until="load")
        page.wait_for_selector("#canvas-view")
        for label, width, height in (
            ("desktop1280", 1280, 900),
            ("mid900", 900, 900),
            ("narrow358", 358, 377),
        ):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(300)
            data = page.evaluate(
                """() => {
                    const doc = document.documentElement;
                    const workbench = document.querySelector('.workbench');
                    const raw = getComputedStyle(workbench).gridTemplateColumns;
                    const cols = raw.split(' ').filter(Boolean);
                    const inspector = document.querySelector('.inspector-panel');
                    const reset = document.querySelector('#reset-workbench');
                    return {
                        innerWidth: window.innerWidth,
                        clientWidth: doc.clientWidth,
                        scrollWidth: doc.scrollWidth,
                        cols: cols.length,
                        colsRaw: raw,
                        inspectorColumn: getComputedStyle(inspector).gridColumnStart,
                        inspectorRow: getComputedStyle(inspector).gridRowStart,
                        resetVisible: !!reset && reset.getBoundingClientRect().width > 0,
                    };
                }"""
            )
            readings[label] = data
            if data["scrollWidth"] > data["clientWidth"] + 1:
                problems.append(
                    f"{label}: 横向滚动 scrollWidth={data['scrollWidth']} > clientWidth={data['clientWidth']}"
                )
            if not data["resetVisible"]:
                problems.append(f"{label}: 「重置演示」不可见")
            page.screenshot(path=str(SHOTS / (label + ".png")), full_page=True)
        browser.close()

    if readings["desktop1280"]["cols"] != 3:
        problems.append("1280 宽不是三栏：" + readings["desktop1280"]["colsRaw"])
    if readings["mid900"]["cols"] != 2 or readings["mid900"]["inspectorColumn"] != "2":
        problems.append(
            "900 宽不是两栏（右栏应在候选画布下方）："
            + readings["mid900"]["colsRaw"] + " col=" + readings["mid900"]["inspectorColumn"]
        )
    if readings["narrow358"]["cols"] != 1:
        problems.append("358 宽不是单列：" + readings["narrow358"]["colsRaw"])

    print("=" * 72)
    print("窄视口布局判据（无头 Chromium · 真浏览器 · 零付费）")
    print("=" * 72)
    for label, data in readings.items():
        print(
            "  %s: innerWidth=%s clientWidth=%s scrollWidth=%s cols=%s (%s) inspector=(col %s, row %s)"
            % (label, data["innerWidth"], data["clientWidth"], data["scrollWidth"], data["cols"],
               data["colsRaw"], data["inspectorColumn"], data["inspectorRow"])
        )
    print()
    if problems:
        for item in problems:
            print("  ✗ " + item)
        print("结果：不通过（退出码 1）")
        return 1
    print("结果：全过（退出码 0）—— 三档都无横向滚动；358x377（200% 缩放 footprint）单列")
    print("截图：" + str(SHOTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
