#!/usr/bin/env python
"""四段界面矩阵：当前线上构建在 1440/1366/1024/390 与 5712/5720 宽下的可用性与溢出。

零模型调用、只读线上服务；独立临时 profile 导入真实项目包。检查：
  UI-01 六个宽度下四段导航都可点击，面板可见且无根横向溢出（5712/5720 覆盖历史异常）
  UI-02 长英文警告/风险文本按 anywhere 折行，元素自身也无横向溢出
  UI-03 窄屏（390）单列工作台＋原生选图器可用，桌面（≥901）双栏
  UI-04 制作区选中图 → 返工面板打开 → 取消后焦点回到触发按钮；比较面板可收起
  UI-05 键盘可达：焦点进入阶段按钮，Enter 切换阶段；Tab 移动焦点
  UI-06 全程零 console/page error
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))

WIDTHS = [
    (1440, 900), (1366, 900), (1024, 900), (390, 844), (5712, 1000), (5720, 1000),
]
STAGES = ["intake", "plan", "make", "deliver"]

MEASURE = """
() => {
  const root = document.documentElement;
  const body = document.body;
  const clientWidth = root.clientWidth;
  const offenders = [...body.querySelectorAll("*")]
    .filter((node) => {
      const style = getComputedStyle(node);
      if (style.position === "fixed" || style.display === "none" || style.visibility === "hidden") return false;
      if (node.closest("[hidden]")) return false;
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.right > clientWidth + 1;
    })
    .slice(0, 4)
    .map((node) => ({
      tag: node.tagName.toLowerCase(),
      cls: String(node.className || "").slice(0, 60),
      right: Math.round(node.getBoundingClientRect().right),
      text: String(node.textContent || "").trim().slice(0, 40),
    }));
  const wrap = (selector) => [...document.querySelectorAll(selector)]
    .filter((node) => !node.closest("[hidden]") && node.getBoundingClientRect().width > 0)
    .map((node) => ({
      overflowWrap: getComputedStyle(node).overflowWrap,
      wordBreak: getComputedStyle(node).wordBreak,
      scrollWidth: node.scrollWidth,
      clientWidth: node.clientWidth,
      text: String(node.textContent || "").trim().slice(0, 24),
    }));
  const panel = document.querySelector('[data-stage-panel]:not([hidden])');
  return {
    clientWidth,
    rootScrollWidth: root.scrollWidth,
    bodyScrollWidth: body.scrollWidth,
    currentStage: (document.querySelector("[data-stage-nav].is-current") || {}).dataset?.stageNav || null,
    panel: panel ? panel.dataset.stagePanel : null,
    offenders,
    promptWarnings: wrap(".prompt-warning"),
    confirmRisks: wrap(".confirm-risk"),
    workbenchColumns: getComputedStyle(document.querySelector(".review-workbench") || body).gridTemplateColumns,
    shotSelectVisible: (() => {
      const node = document.getElementById("make-shot-select");
      return Boolean(node && node.getBoundingClientRect().width > 0);
    })(),
  };
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="四段界面矩阵实测")
    parser.add_argument("--base", default="https://47.115.172.233:8080")
    parser.add_argument("--package", required=True)
    parser.add_argument("--label", default="ui-matrix")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    source = Path(args.package).resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    evidence = HERE / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    console: list[str] = []
    page_errors: list[str] = []
    matrix: list[dict] = []

    def check(cid: str, title: str, ok: bool, detail) -> None:
        checks.append({"id": cid, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid} {title}")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-first-run"])
            try:
                context = browser.new_context(viewport={"width": 1440, "height": 900},
                                              ignore_https_errors=True)
                page = context.new_page()
                page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.goto(args.base + "/", wait_until="networkidle", timeout=60_000)
                page.set_input_files("#import-file", str(source))
                expect(page.locator("#home-status")).to_be_visible(timeout=60_000)
                expect(page.locator("#project-list .project-row")).to_have_count(1, timeout=60_000)
                page.click("#project-list .project-row [data-action='open']")
                expect(page.locator("#project-view:not([hidden])")).to_be_visible(timeout=60_000)

                overflow: list[str] = []
                for width, height in WIDTHS:
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(150)
                    for stage in STAGES:
                        page.evaluate("(id) => document.querySelector('[data-stage-nav=\"' + id + '\"]').click()", stage)
                        page.wait_for_timeout(120)
                        metrics = page.evaluate(MEASURE)
                        page.screenshot(path=str(evidence / f"{stamp}-{args.label}-{width}-{stage}.png"))
                        matrix.append({"width": width, "height": height, "stage": stage, **metrics})
                        if metrics["rootScrollWidth"] > metrics["clientWidth"] + 1:
                            overflow.append(f"{width}/{stage}:{metrics['rootScrollWidth']}>{metrics['clientWidth']}")
                        if metrics["panel"] != stage or metrics["currentStage"] != stage:
                            overflow.append(f"{width}/{stage}:panel={metrics['panel']},current={metrics['currentStage']}")

                check("UI-01", "六个宽度四段可切换且无根横向溢出",
                      not overflow, {"widths": [w for w, _ in WIDTHS], "problems": overflow[:8]})

                warnings = [m for m in matrix if m["promptWarnings"] or m["confirmRisks"]]
                bad_wrap = []
                for m in warnings:
                    for row in m["promptWarnings"] + m["confirmRisks"]:
                        if row["overflowWrap"] != "anywhere" or row["wordBreak"] != "break-word":
                            bad_wrap.append({"width": m["width"], "stage": m["stage"], "style": row})
                        if row["scrollWidth"] > row["clientWidth"] + 1:
                            bad_wrap.append({"width": m["width"], "stage": m["stage"], "overflow": row})
                check("UI-02", "长英文警告/风险文本折行且元素无横向溢出",
                      bool(warnings) and not bad_wrap,
                      {"measured": len(warnings), "bad": bad_wrap[:6]})

                narrow = next(m for m in matrix if m["width"] == 390 and m["stage"] == "make")
                wide = next(m for m in matrix if m["width"] == 1440 and m["stage"] == "make")
                check("UI-03", "390 单列＋选图器、1440 双栏",
                      narrow["shotSelectVisible"] and len(narrow["workbenchColumns"].split()) == 1
                      and len(wide["workbenchColumns"].split()) == 2,
                      {"narrow": [narrow["shotSelectVisible"], narrow["workbenchColumns"]],
                       "wide": wide["workbenchColumns"]})

                page.set_viewport_size({"width": 1440, "height": 900})
                page.evaluate("() => document.querySelector('[data-stage-nav=\"make\"]').click()")
                page.wait_for_timeout(150)
                page.evaluate("""() => {
                  const row = document.querySelector('#task-list-mount [data-task-shot] [data-view-shot]');
                  if (row) row.click();
                }""")
                expect(page.locator("#compare-panel")).to_be_visible(timeout=30_000)
                page.click("#rework-open")
                expect(page.locator("#rework-panel")).to_be_visible(timeout=30_000)
                page.click("#rework-cancel")
                page.wait_for_timeout(150)
                focus_after_cancel = page.evaluate("() => document.activeElement && document.activeElement.id")
                rework_hidden = page.evaluate("() => Boolean(document.getElementById('rework-panel').hidden)")
                page.click("#compare-close")
                page.wait_for_timeout(120)
                compare_hidden = page.evaluate("() => Boolean(document.getElementById('compare-panel').hidden)")
                check("UI-04", "返工取消回焦触发点，比较面板可收起",
                      focus_after_cancel == "rework-open" and rework_hidden and compare_hidden,
                      {"focus": focus_after_cancel})

                page.evaluate("() => document.querySelector('[data-stage-nav=\"deliver\"]').focus()")
                page.keyboard.press("Enter")
                page.wait_for_timeout(120)
                deliver = page.evaluate("() => ({panel: (document.querySelector('[data-stage-panel]:not([hidden])') || {}).dataset?.stagePanel, active: document.activeElement && document.activeElement.dataset?.stageNav})")
                page.keyboard.press("Tab")
                moved = page.evaluate("() => document.activeElement !== document.body && document.activeElement !== null")
                check("UI-05", "键盘 Enter 切段、Tab 移动焦点",
                      deliver["panel"] == "deliver" and moved,
                      deliver)

                check("UI-06", "全程零 console/page error", not console and not page_errors,
                      {"console": console[:5], "page": page_errors[:5]})
                context.close()
            finally:
                browser.close()
    except Exception as error:  # noqa: BLE001
        checks.append({"id": "UI-EXC", "title": "执行异常", "ok": False,
                       "detail": f"{type(error).__name__}: {error}"})
        print(f"  [FAIL] UI-EXC {type(error).__name__}: {error}")

    passed = sum(1 for item in checks if item["ok"])
    payload = {
        "schema": "amz-release-ui-matrix/v1",
        "status": "passed" if passed == len(checks) and checks else "failed",
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "base": args.base, "source_package": str(source),
        "passed": passed, "total": len(checks), "checks": checks,
        "matrix": matrix, "console_errors": console[:20], "page_errors": page_errors[:20],
    }
    (evidence / f"{stamp}-{args.label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("=" * 72)
    print(f"{passed}/{len(checks)} 通过")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
