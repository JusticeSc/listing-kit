#!/usr/bin/env python
"""D4.8 浏览器级证据：逐图生成、局部失败、欠费指引、Unknown 核对与重启恢复。

场景（一个工作空间、三张图、确定性假图片 provider，不调用真实模型）：
  1. 提交后三张图呈现混合轨迹：RUNNING / FAILED / UNKNOWN（有原任务编号）；
  2. RUNNING 的图由界面自动轮询完成：不点任何按钮，候选自动出现；轮询只查原任务；
  3. UNKNOWN 的图只提供「核对当前生成状态」，核对后完成且不重新提交；
  4. 失败的图先给出可执行的欠费修复指引，再次「重新生成这张」只重跑该图；
  5. 刷新页面与重启服务后状态从磁盘恢复，付费提交次数不变。

运行：
  uv run --locked python tools/verify_product_v1_generation_recovery_ui.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

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
from src.providers.image import ImageProviderError  # noqa: E402

EVIDENCE = ROOT / "evals" / "product-demo"


class RecoveryImageProvider(ui.FakeImageProvider):
    """Adds an arrears rejection to the deterministic fake provider."""

    # Different colours per task: candidate_id is the content digest, so two shots
    # must not resolve to byte-identical fixtures or the second one is reported as a
    # duplicate-candidate conflict instead of a normal completion.
    _COLORS = {
        "rec-task-1": (30, 120, 200),
        "rec-task-3": (210, 90, 40),
        "rec-retry-2": (90, 200, 120),
    }

    def resolve(self, task_id, *, status="SUCCEEDED"):
        url = f"fake://ui-result/{task_id}"
        self._bytes.setdefault(
            url, ui.png_image(64, 48, self._COLORS.get(task_id, (200, 120, 60))))
        self._query_results[task_id] = (status, url)

    def submit(self, prompt, references, *, model_id=None, size="1344*1344",
               seed=None, idempotency_key=None):
        if self._planned and self._planned[0][0] == "ARREARS":
            self._planned.pop(0)
            self.submit_calls.append({
                "prompt": prompt, "references": list(references),
                "idempotency_key": idempotency_key, "task_id": None, "size": size,
            })
            raise ImageProviderError("UPSTREAM_ACCOUNT_ARREARS", "账户余额不足，请充值后重试。")
        return super().submit(prompt, references, model_id=model_id, size=size,
                              seed=seed, idempotency_key=idempotency_key)


def fill_intake(page) -> None:
    page.locator("#product-name").fill("验证商品-恢复轨迹")
    page.locator("#product-description").fill("双层不锈钢结构，日常通勤使用。")
    page.locator("#selling-points").fill("双层结构\n防滑杯底")
    page.locator("#user-intent").fill("突出便携，不出现户外场景。")
    page.locator("#reference-images").set_input_files([
        {"name": "reference-a.png", "mimeType": "image/png", "buffer": ui.png_1x1()},
        {"name": "reference-c.png", "mimeType": "image/png",
         "buffer": ui.png_image(2, 2, (96, 96, 255))},
    ])
    expect(page.locator("#saved-images .image-tile")).to_have_count(2)


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    failures: list[str] = []

    def check(name: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="amz-d48-recovery-ui-") as raw:
        root = Path(raw)
        workspace = root / "recovery-workspace"
        recent_index = root / "recent.json"
        provider = RecoveryImageProvider()
        server, thread, base_url = ui.start_server(recent_index, workspace, provider)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                reconcile_posts: list[str] = []

                def watch(request) -> None:
                    path = urlsplit(request.url).path
                    if request.method == "POST" and re.fullmatch(
                            r"/api/attempts/[A-Za-z0-9_-]+/reconcile", path):
                        reconcile_posts.append(path)

                page.on("request", watch)
                page.goto(base_url + "/", wait_until="networkidle")
                page.get_by_role("button", name="新建商品套图").click()
                page.wait_for_selector("#intake-screen:not([hidden])")
                fill_intake(page)
                workspace_url = (base_url + "/api/workspace?directory="
                                 + quote(str(workspace), safe=""))

                def shot_rows():
                    return page.request.get(workspace_url).json()["data"]["plan"]["shot_specs"]

                provider.resolve("rec-task-1", status="RUNNING")
                provider.plan([
                    ("RUNNING", "rec-task-1"),
                    ("FAILED", "rec-task-2"),
                    ("UNKNOWN", "rec-task-3"),
                ])
                page.get_by_role("button", name="生成整套图片").click()
                expect(page.locator("#save-state")).to_contain_text("已开始生成")
                expect(page.locator("#generation-shots .generation-shot")).to_have_count(
                    3, timeout=60000)
                states = page.locator("#generation-shots .generation-state")
                expect(states).to_have_text(
                    ["生成中", "生成失败", "结果待核对"], timeout=60000)
                check("mixed-trace-rendered", True, states.all_inner_texts())
                strip = page.locator("#generation-shots .generation-shot")
                strip.nth(1).click()
                check("failed-shot-offers-retry", page.locator("#review-retry").is_visible())
                strip.nth(0).click()
                check("unknown-shows-reconcile-button",
                      page.locator("#reconcile-generation").is_visible())
                check("unknown-hint-mentions-reconcile",
                      "核对" in page.locator("#generation-hint").inner_text())
                page.screenshot(
                    path=str(EVIDENCE / f"d4.8-generation-recovery-ui-{stamp}-mixed.png"),
                    full_page=True)

                # 自动轮询：不点任何按钮，界面自己核对 RUNNING 的原任务。
                deadline = datetime.now().timestamp() + 20
                while datetime.now().timestamp() < deadline and not reconcile_posts:
                    page.wait_for_timeout(500)
                check("auto-polling-observed-without-clicks",
                      len(reconcile_posts) >= 1, len(reconcile_posts))
                expect(states).to_have_text(["生成中", "生成失败", "结果待核对"])

                provider.resolve("rec-task-1", status="SUCCEEDED")
                expect(states).to_have_text(
                    ["已完成", "生成失败", "结果待核对"], timeout=30000)
                page.locator("#review-image").wait_for(state="visible", timeout=30000)
                check("running-shot-completed-by-polling-only",
                      len(provider.submit_calls) == 3, len(provider.submit_calls))

                # UNKNOWN：手动核对，只查原任务。
                provider.resolve("rec-task-3", status="SUCCEEDED")
                page.get_by_role("button", name="核对当前生成状态").click()
                expect(states).to_have_text(
                    ["已完成", "生成失败", "已完成"], timeout=30000)
                check("unknown-reconciled-without-resubmit",
                      len(provider.submit_calls) == 3, len(provider.submit_calls))

                # 局部失败：欠费指引 -> 只重跑这一张。
                before_rows = shot_rows()
                before_others = [
                    [len(row["generation_attempts"]),
                     [item["candidate_id"] for item in row["candidates"]]]
                    for row in (before_rows[0], before_rows[2])
                ]
                provider.plan([("ARREARS", None)])
                strip.nth(1).click()
                page.locator("#review-retry").click()
                expect(page.locator("#review-error")).to_contain_text("百炼账户欠费", timeout=30000)
                check("arrears-guidance-visible", True)

                provider.plan([("SUCCEEDED", "rec-retry-2")])
                page.locator("#review-retry").click()
                try:
                    expect(states).to_have_text(
                        ["已完成", "已完成", "已完成"], timeout=30000)
                    retry_ok = True
                except Exception:  # noqa: BLE001 - Playwright raises its own AssertionError
                    retry_ok = False
                after_rows = shot_rows()
                check("retry-shot-completed", retry_ok, {
                    "states": page.locator("#generation-shots .generation-state").all_inner_texts(),
                    "shot2_attempts": [
                        {"status": item["status"], "created_at": item.get("created_at"),
                         "error": item.get("error")}
                        for item in after_rows[1]["generation_attempts"]],
                    "shot2_candidates": [item["candidate_id"] for item in after_rows[1]["candidates"]],
                })
                after_others = [
                    [len(row["generation_attempts"]),
                     [item["candidate_id"] for item in row["candidates"]]]
                    for row in (after_rows[0], after_rows[2])
                ]
                check("retry-submitted-exactly-once-more",
                      len(provider.submit_calls) == 5, len(provider.submit_calls))
                check("unrelated-shots-unchanged",
                      before_others == after_others, [before_others, after_others])
                page.screenshot(
                    path=str(EVIDENCE / f"d4.8-generation-recovery-ui-{stamp}-complete.png"),
                    full_page=True)

                # 刷新：状态从磁盘恢复，不重复提交。
                page.reload(wait_until="networkidle")
                expect(page.locator("#generation-shots .generation-shot")).to_have_count(
                    3, timeout=60000)
                expect(states).to_have_text(
                    ["已完成", "已完成", "已完成"], timeout=60000)
                check("reload-restores-without-resubmit",
                      len(provider.submit_calls) == 5, len(provider.submit_calls))
                context.close()
                browser.close()
        finally:
            ui.stop_server(server, thread)

        # 重启服务 + 新浏览器上下文：状态从磁盘恢复，不重放提交。
        server, thread, base_url = ui.start_server(recent_index, workspace, provider)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                page.goto(base_url + "/", wait_until="networkidle")
                page.locator("#recent-list .recent-open").first.click()
                page.wait_for_selector("#generation-shots .generation-shot", timeout=30000)
                expect(page.locator("#generation-shots .generation-state")).to_have_text(
                    ["已完成", "已完成", "已完成"], timeout=30000)
                check("restart-restores-without-resubmit",
                      len(provider.submit_calls) == 5, len(provider.submit_calls))
                context.close()
                browser.close()
        finally:
            ui.stop_server(server, thread)

    report = {"stamp": stamp, "checks": checks, "failures": failures,
              "passed": not failures, "workspace": "temp (deleted)"}
    out = EVIDENCE / f"d4.8-generation-recovery-ui-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        return 1
    print("D4.8 逐图生成与恢复界面的浏览器证据通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
