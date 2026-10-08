#!/usr/bin/env python
"""Browser verification of the in-product two-phase single-shot rework flow.

Boots the shipped product server with injected fake providers, prepares a real
workspace through the service API, then drives the browser through the visible
flow: 审核态 -> 重做这张 -> 快捷原因/自由方向 -> 生成返工方案 -> 确认并重做这张.

It asserts the shipped promises: the preview compiles a versioned proposal with
zero ImageProvider calls; the confirmation creates exactly one new Prompt /
Attempt / Candidate for the target shot; every other shot keeps its attempts and
candidate bytes; the target shot becomes pending re-confirmation until the
operator adopts an old or a new candidate again.
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

EVIDENCE = ROOT / "evals" / "product-demo"
SESSION_KEY = "amzListingKit.productV1.workspaceDirectory"
REWORK_DIRECTION = "商品占比放大，保持商品轮廓与颜色不变"


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
    result: dict[str, object] = {"direction": REWORK_DIRECTION}
    try:
        provider = RegistryCompatibleFakeImageProvider()
        fixture.image_provider = provider
        provider.plan_submissions([
            Submission("SUCCEEDED", f"two-phase-initial-{index}") for index in range(1, 4)
        ])
        require_ok(fixture.start(FIRST_KEY), "start whole-set generation")

        before = fixture.projection()
        shots = before["plan"]["shot_specs"]
        before_attempts = {
            shot["id"]: [item["action_id"] for item in shot.get("generation_attempts") or []]
            for shot in shots
        }
        before_candidates = {
            shot["id"]: [item["candidate_id"] for item in shot.get("candidates") or []]
            for shot in shots
        }
        result["before"] = {"attempts": before_attempts, "candidates": before_candidates}
        target = shots[1]
        others = [shot["id"] for shot in shots if shot["id"] != target["id"]]

        # Start from a complete selection so the rework must make the target shot pending.
        for shot in shots:
            require_ok(fixture.service.save_shot_selection(
                fixture.workspace,
                expected_etag=fixture.projection()["workspace"]["revision"],
                shot_id=shot["id"],
                candidate_sha256=(shot.get("candidates") or [])[0]["candidate_id"],
            ), f"adopt {shot['id']}")

        with tempfile.TemporaryDirectory(prefix="amz-product-v1-ui-rework-") as raw:
            app = ProductApplication(
                service=fixture.service,
                recent_index_path=Path(raw) / "recent-workspaces.json",
                folder_picker=lambda _purpose: str(fixture.workspace),
            )
            server = create_product_server("127.0.0.1", 0, application=app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            external_requests: list[str] = []
            try:
                with sync_playwright() as driver:
                    browser = driver.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})

                    def watch_requests(request, origin=base_url):
                        host = urlsplit(request.url).netloc
                        if host and host != urlsplit(origin).netloc:
                            external_requests.append(request.url)

                    page.on("request", watch_requests)
                    page.goto(base_url + "/", wait_until="load")
                    opened = page.evaluate(
                        """async (directory) => {
                            const response = await fetch("/api/workspaces/open", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ directory }),
                            });
                            return await response.json();
                        }""",
                        str(fixture.workspace),
                    )
                    if not opened.get("ok"):
                        failures.append("浏览器无法打开工作空间：" + json.dumps(opened, ensure_ascii=False))
                    page.evaluate(
                        "([key, value]) => window.sessionStorage.setItem(key, value)",
                        [SESSION_KEY, str(fixture.workspace)],
                    )
                    page.reload(wait_until="load")
                    page.wait_for_selector("#generation-shots .generation-shot", timeout=20000)
                    cards = page.locator("#generation-shots .generation-shot")
                    if cards.count() != len(shots):
                        failures.append(f"生成结果卡片数量 {cards.count()} 与方案 {len(shots)} 不一致")
                    progress_before = page.locator("#selection-progress").inner_text()
                    result["selection_before"] = progress_before
                    if not progress_before.startswith(f"{len(shots)}/{len(shots)}"):
                        failures.append("进入返工前没有恢复完整选择：" + progress_before)
                    if page.locator("#export-selection").is_disabled():
                        failures.append("完整选择下导出门禁没有放开")
                    page.screenshot(path=str(EVIDENCE / f"ui-rework-{stamp}-before.png"), full_page=True)

                    cards.nth(1).click()
                    rework_button = page.locator("#review-rework")
                    result["rework_button_count"] = rework_button.count()
                    if rework_button.count() != 1:
                        failures.append("审核决策区没有「重做这张」按钮")
                    else:
                        rework_button.click()
                        page.wait_for_selector("#rework-dialog[open]", timeout=10000)
                        if not page.locator("#rework-confirm").is_disabled():
                            failures.append("预览前「确认并重做这张」不应可用")
                        page.locator("#rework-reasons input[value='product-fidelity']").check()
                        page.locator("#rework-direction").fill(REWORK_DIRECTION)
                        page.click("#rework-preview-button")
                        page.wait_for_selector("#rework-preview:not([hidden])", timeout=15000)

                        preview_submits = len(provider.submit_calls)
                        result["preview_submit_calls"] = preview_submits
                        if preview_submits != len(shots):
                            failures.append("预览阶段调用了图片模型")
                        paused = fixture.projection()
                        paused_target = next(
                            shot for shot in paused["plan"]["shot_specs"] if shot["id"] == target["id"]
                        )
                        result["attempts_after_preview"] = len(
                            paused_target.get("generation_attempts") or [])
                        if len(paused_target.get("generation_attempts") or []) != 1:
                            failures.append("预览阶段创建了图片 Attempt")

                        keep = page.locator("#rework-keep li").all_inner_texts()
                        change = page.locator("#rework-change li").all_inner_texts()
                        result_text = page.locator("#rework-result").inner_text().strip()
                        diff_rows = page.locator("#rework-diff .rework-diff-row").count()
                        result["preview"] = {
                            "keep": keep, "change": change,
                            "result": result_text, "diff_rows": diff_rows,
                        }
                        if not keep or not change or not result_text:
                            failures.append("返工预览没有展示保持/改变/结果")
                        if diff_rows < 1:
                            failures.append("返工预览没有展示 Prompt 差异")
                        if page.locator("#rework-confirm").is_disabled():
                            failures.append("预览就绪后「确认并重做这张」仍不可用")

                        provider.plan_submissions([Submission("SUCCEEDED", "two-phase-rework-1")])
                        page.click("#rework-confirm")
                        try:
                            page.wait_for_function(
                                "() => !document.querySelector('#rework-dialog').open",
                                timeout=30000)
                        except Exception:
                            print("返工状态栏：", page.locator("#rework-status").inner_text())
                            raise
                        deadline = time.monotonic() + 30
                        while time.monotonic() < deadline:
                            after = fixture.projection()
                            target_after = next(
                                shot for shot in after["plan"]["shot_specs"]
                                if shot["id"] == target["id"]
                            )
                            if (len(target_after.get("generation_attempts") or []) >= 2
                                    and len(target_after.get("candidates") or []) >= 2):
                                break
                            time.sleep(0.25)
                        else:
                            failures.append("30 秒内没有看到返工产生的新尝试与新候选")
                            after = fixture.projection()
                            target_after = next(
                                shot for shot in after["plan"]["shot_specs"]
                                if shot["id"] == target["id"]
                            )

                        after = fixture.projection()
                        after_by_shot = {shot["id"]: shot for shot in after["plan"]["shot_specs"]}
                        result["after"] = {
                            "attempts": {shot_id: len(shot.get("generation_attempts") or [])
                                         for shot_id, shot in after_by_shot.items()},
                            "candidates": {shot_id: [item["candidate_id"] for item in shot.get("candidates") or []]
                                           for shot_id, shot in after_by_shot.items()},
                        }
                        target_after = after_by_shot[target["id"]]
                        if len(target_after.get("generation_attempts") or []) != 2:
                            failures.append("返工没有为这张图新增且仅新增一条尝试记录")
                        if len(target_after.get("candidates") or []) != 2:
                            failures.append("返工没有为这张图新增且仅新增一个候选")
                        if [item["candidate_id"] for item in target_after["candidates"]][:1] != before_candidates[target["id"]]:
                            failures.append("返工后旧候选没有保留在首位")
                        for shot_id in others:
                            shot = after_by_shot[shot_id]
                            if [item["action_id"] for item in shot.get("generation_attempts") or []] != before_attempts[shot_id]:
                                failures.append(f"无关图片 {shot_id} 的尝试记录发生变化")
                            if [item["candidate_id"] for item in shot.get("candidates") or []] != before_candidates[shot_id]:
                                failures.append(f"无关图片 {shot_id} 的候选文件发生变化")

                        latest_prompt = target_after.get("latest_prompt") or {}
                        result["prompt_version"] = latest_prompt.get("version")
                        result["prompt_edit_mode"] = latest_prompt.get("edit_mode")
                        result["prompt_edit_reason"] = latest_prompt.get("edit_reason")
                        if latest_prompt.get("version") != 2 or latest_prompt.get("edit_mode") != "rework":
                            failures.append("确认返工没有生成 edit_mode=rework 的新提示词版本")
                        if latest_prompt.get("edit_reason") != REWORK_DIRECTION:
                            failures.append("返工方向没有写入新提示词版本的 edit_reason")
                        if len(provider.submit_calls) != len(shots) + 1:
                            failures.append("确认返工没有恰好触发一次图片模型提交")
                        elif provider.submit_calls[-1]["prompt"] != latest_prompt.get("full_text"):
                            failures.append("确认返工提交给模型的提示词不是新版本")

                        current_selection = after.get("selection") or {}
                        chosen = {item["shot"]["id"] for item in current_selection.get("choices", [])}
                        if chosen != set(others):
                            failures.append("确认返工后目标 Shot 没有转为待重新确认")
                        progressed = page.locator("#selection-progress").inner_text()
                        result["selection_after_confirm"] = progressed
                        if not progressed.startswith(f"{len(shots) - 1}/{len(shots)}"):
                            failures.append("确认返工后界面仍显示旧的完整选择：" + progressed)
                        if not page.locator("#export-selection").is_disabled():
                            failures.append("目标 Shot 待重新确认时导出没有被禁用")
                        if page.locator(
                            "#generation-shots .generation-shot").nth(1).get_attribute("data-adopted") != "false":
                            failures.append("确认返工后目标 Shot 仍显示已采用")

                        page.screenshot(path=str(EVIDENCE / f"ui-rework-{stamp}-after.png"), full_page=True)
                        rendered = page.locator("#review-candidates .generation-candidate").count()
                        result["rendered_candidates"] = rendered
                        if rendered != 2:
                            failures.append(f"返工后页面显示 {rendered} 个候选，期望 2 个")
                        labels = page.locator(
                            "#review-candidates .generation-candidate figcaption strong"
                        ).all_inner_texts()
                        result["candidate_labels"] = labels
                        if "历史候选" not in labels:
                            failures.append("页面没有把旧候选标为历史候选")

                        # 重新选择任一旧候选即可恢复完整选择与导出。
                        page.locator(
                            "#review-candidates .review-candidate-button").nth(0).click()
                        page.locator("#review-adopt").click()
                        page.wait_for_function(
                            "() => document.querySelector('#selection-progress').textContent.startsWith('3/3')",
                            timeout=15000)
                        restored = fixture.projection()
                        restored_chosen = {
                            item["shot"]["id"] for item in (restored.get("selection") or {}).get("choices", [])
                        }
                        result["selection_after_readopt"] = page.locator("#selection-progress").inner_text()
                        if restored_chosen != {shot["id"] for shot in shots}:
                            failures.append("重新采用旧候选后选择没有恢复完整")
                        if page.locator("#export-selection").is_disabled():
                            failures.append("重新采用旧候选后导出仍然被禁用")
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            result["external_requests"] = external_requests
            if external_requests:
                failures.append("浏览器访问了产品以外的地址：" + ", ".join(external_requests))
    finally:
        fixture.tearDown()

    result["failures"] = failures
    result["passed"] = not failures
    report_path = EVIDENCE / f"ui-rework-{stamp}.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
