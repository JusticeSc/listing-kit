#!/usr/bin/env python
"""D4.9 浏览器级证据：图片优先审核与选择工作台。

覆盖（一个工作空间、三张图、确定性假图片 provider）：
  1. 顶部缩略条 + 中央大图 + 当前图决策区；旧卡片式选择入口退出导航；
  2. 候选不会自动成为最终选择；
  3. 切换 Shot / 候选不丢状态；
  4. 逐张“采用此图”，全部采用后保存选择并放开导出；
  5. 重做后旧候选作为历史候选始终可见；
  6. 候选文件损坏时不可采用但记录不删除，且可改选未损坏的旧候选；
  7. 刷新后采用状态与导出门禁从 Workspace 恢复。

运行：
  uv run --locked python tools/verify_product_v1_review_workbench_ui.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
for _entry in (str(ROOT), str(TOOLS)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

_spec = importlib.util.spec_from_file_location(
    "verify_product_v1_ui", TOOLS / "verify_product_v1_ui.py")
ui = importlib.util.module_from_spec(_spec)
sys.modules["verify_product_v1_ui"] = ui
_spec.loader.exec_module(ui)

from playwright.sync_api import expect, sync_playwright  # noqa: E402

EVIDENCE = ROOT / "evals" / "product-demo"
REWORK_NOTE = "让商品在图中的占比更大。"


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    failures: list[str] = []

    def check(name: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="amz-d49-review-ui-") as raw:
        root = Path(raw)
        workspace = root / "review-workspace"
        provider = ui.FakeImageProvider()
        server, thread, base_url = ui.start_server(root / "recent.json", workspace, provider)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                prompt_responses: list[str] = []

                def capture_prompt_response(response) -> None:
                    if response.url.endswith("/api/prompt") and response.request.method == "PUT":
                        try:
                            body = response.text()[:1500]
                        except Exception:
                            body = "<无法读取响应体>"
                        prompt_responses.append(f"{response.status} {body}")

                page.on("response", capture_prompt_response)
                selection_writes: list[tuple[str, str]] = []

                def track_selection_writes(request) -> None:
                    if request.url.endswith("/api/selection") and request.method == "POST":
                        selection_writes.append(("POST", request.url))
                    elif (request.method == "PUT" and "/api/shots/" in request.url
                          and request.url.endswith("/selection")):
                        selection_writes.append(("PUT", request.url))

                page.on("request", track_selection_writes)
                page.goto(base_url + "/", wait_until="networkidle")
                workspace_url = (base_url + "/api/workspace?directory="
                                 + quote(str(workspace), safe=""))

                def projection() -> dict:
                    return page.request.get(workspace_url).json()["data"]

                # 空白工作空间 -> 一键整套生成。
                page.get_by_role("button", name="新建商品套图").click()
                page.wait_for_selector("#intake-screen:not([hidden])")
                page.locator("#product-name").fill("验证商品-审核工作台")
                page.locator("#product-description").fill("双层不锈钢结构，日常通勤使用。")
                page.locator("#selling-points").fill("双层结构\n防滑杯底")
                page.locator("#user-intent").fill("突出便携，不出现户外场景。")
                page.locator("#reference-images").set_input_files([
                    {"name": "reference-a.png", "mimeType": "image/png", "buffer": ui.png_1x1()},
                    {"name": "reference-c.png", "mimeType": "image/png",
                     "buffer": ui.png_image(2, 2, (96, 96, 255))},
                ])
                expect(page.locator("#saved-images .image-tile")).to_have_count(2)
                provider.plan([("SUCCEEDED", f"review-{index}") for index in (1, 2, 3)])
                page.get_by_role("button", name="生成整套图片").click()
                expect(page.locator("#save-state")).to_contain_text("已开始生成")
                strip = page.locator("#generation-shots .generation-shot")
                expect(strip).to_have_count(3, timeout=60000)
                expect(page.locator("#generation-shots .generation-state")).to_have_text(
                    ["已完成"] * 3, timeout=60000)

                check("workbench-visible", page.locator("#review-workbench").is_visible())
                check("strip-and-stage",
                      strip.count() == 3
                      and page.locator("#review-image").is_visible()
                      and page.locator("#review-candidates .generation-candidate").count() >= 1)
                check("legacy-choice-entry-gone",
                      page.locator(".candidate-choose").count() == 0)

                # 候选不会自动成为最终选择。
                check("no-auto-selection",
                      page.locator("#selection-progress").inner_text().startswith("0/3")
                      and page.locator("#export-selection").is_disabled()
                      and page.locator("#save-selection").count() == 0
                      and page.locator("#generation-shots .generation-shot[data-adopted='true']").count() == 0,
                      {"progress": page.locator("#selection-progress").inner_text()})

                # 重做第 2 张：两阶段返工；旧候选必须作为历史候选保留。
                stored = projection()
                shot_ids = [shot["id"] for shot in stored["plan"]["shot_specs"]]
                strip.nth(1).click()
                expect(page.locator("#review-rework")).to_be_visible()
                provider.plan([("SUCCEEDED", "review-rework-1")])
                page.locator("#review-rework").click()
                page.wait_for_selector("#rework-dialog[open]", timeout=10000)
                check("rework-confirm-gated", page.locator("#rework-confirm").is_disabled())
                page.locator("#rework-reasons input[value='composition-size']").check()
                page.locator("#rework-direction").fill(REWORK_NOTE)
                page.click("#rework-preview-button")
                page.wait_for_selector("#rework-preview:not([hidden])", timeout=15000)
                check("rework-preview-shows-keep-change",
                      page.locator("#rework-keep li").count() >= 1
                      and page.locator("#rework-change li").count() >= 1
                      and bool(page.locator("#rework-result").inner_text().strip()))
                page.click("#rework-confirm")
                try:
                    page.wait_for_function(
                        "() => !document.querySelector('#rework-dialog').open", timeout=30000)
                except Exception:
                    print("返工状态栏：", page.locator("#rework-status").inner_text())
                    raise
                page.wait_for_function(
                    "() => document.querySelectorAll('#review-candidates .generation-candidate').length >= 2",
                    timeout=30000)
                labels = page.locator(
                    "#review-candidates .generation-candidate figcaption strong").all_inner_texts()
                check("history-candidate-visible", "历史候选" in labels, labels)

                # 切换 Shot / 候选不丢状态，并逐张采用。
                strip.nth(0).click()
                page.locator("#review-adopt").click()
                expect(page.locator("#selection-progress")).to_contain_text("1/3")
                strip.nth(2).click()
                page.locator("#review-adopt").click()
                expect(page.locator("#selection-progress")).to_contain_text("2/3")

                strip.nth(1).click()
                candidate_buttons = page.locator("#review-candidates .review-candidate-button")
                expect(candidate_buttons).to_have_count(2, timeout=15000)
                first_src = page.locator("#review-image").get_attribute("src")
                candidate_buttons.nth(0).click()
                second_src = page.locator("#review-image").get_attribute("src")
                check("candidate-switch-changes-preview", first_src != second_src,
                      {"first": bool(first_src), "second": bool(second_src)})
                check("candidate-switch-keeps-adoption",
                      page.locator("#selection-progress").inner_text().startswith("2/3")
                      and page.locator("#generation-shots .generation-shot").nth(0)
                      .get_attribute("data-adopted") == "true")
                candidate_buttons.nth(1).click()
                page.locator("#review-adopt").click()
                expect(page.locator("#selection-progress")).to_contain_text("3/3")
                expect(page.locator("#export-selection")).to_be_enabled()
                check("adoption-persisted-per-shot",
                      len(projection()["selection"]["choices"]) == 3)

                # 切换 Shot 后回来，已采用状态仍在。
                strip.nth(0).click()
                strip.nth(1).click()
                check("shot-switch-keeps-adoption",
                      page.locator("#review-adopt").inner_text().strip() == "已采用这张"
                      and page.locator(
                          "#generation-shots .generation-shot[data-adopted='true']").count() == 3)

                page.reload(wait_until="networkidle")
                expect(strip).to_have_count(3, timeout=60000)
                expect(page.locator("#selection-progress")).to_contain_text("3/3", timeout=30000)
                check("reload-restores-adoption",
                      page.locator("#generation-shots .generation-shot[data-adopted='true']").count() == 3
                      and page.locator("#export-selection").is_enabled())

                # 破坏第 2 张已采用的候选文件：不可采用、记录仍在、可改选旧候选。
                saved = projection()
                chosen = {item["shot"]["id"]: item["candidate_sha256"]
                          for item in (saved.get("selection") or {}).get("choices", [])}
                target_shot = next(
                    shot for shot in saved["plan"]["shot_specs"] if shot["id"] == shot_ids[1])
                adopted = next(
                    item for item in target_shot["candidates"]
                    if item["candidate_id"] == chosen[target_shot["id"]])
                broken_path = workspace / adopted["relative_path"]
                broken_path.write_bytes(b"broken-candidate-bytes")

                # 候选资源按内容寻址并带 immutable 缓存头；同一上下文里已缓存的
                # 旧字节不会再读磁盘。清缓存模拟新会话首次加载已损坏文件。
                context.new_cdp_session(page).send("Network.clearBrowserCache")
                page.reload(wait_until="networkidle")
                expect(strip).to_have_count(3, timeout=60000)
                strip.nth(1).click()
                page.wait_for_selector(
                    "#review-candidates .generation-candidate[data-broken='true']", timeout=30000)
                broken = page.locator(
                    "#review-candidates .generation-candidate[data-broken='true']")
                check("broken-candidate-not-selectable",
                      broken.locator(".review-candidate-button").is_disabled()
                      and page.locator("#review-adopt").is_disabled()
                      and "不可读取" in page.locator("#review-empty").inner_text())
                check("broken-candidate-record-kept",
                      len(projection()["plan"]["shot_specs"][1]["candidates"]) == 2)

                intact = page.locator(
                    "#review-candidates .generation-candidate:not([data-broken='true']) .review-candidate-button")
                expect(intact).to_have_count(1)
                intact.click()
                check("can-still-pick-intact-candidate",
                      page.locator("#review-image").is_visible()
                      and page.locator("#review-adopt").is_enabled())
                check("selection-write-migration",
                      len(selection_writes) >= 3
                      and all(method == "PUT" for method, _ in selection_writes),
                      {"writes": len(selection_writes),
                       "methods": sorted({method for method, _ in selection_writes})})

                page.screenshot(
                    path=str(EVIDENCE / f"d4.9-review-workbench-{stamp}.png"), full_page=True)
                context.close()
                browser.close()
        finally:
            ui.stop_server(server, thread)

    report = {"stamp": stamp, "checks": checks, "failures": failures,
              "passed": not failures, "workspace": "temp (deleted)"}
    out = EVIDENCE / f"d4.9-review-workbench-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        return 1
    print("D4.9 图片优先审核工作台的浏览器证据通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
