#!/usr/bin/env python
"""D4.7 浏览器级证据：一键整套命令在真实界面上的接线与幂等边界。

两条真实 UI 路径（图片模型用注入的假 provider，不花真实额度）：
  A. 空白工作空间直接「生成整套图片」：双击只发出一次写尝试；第一次请求被中断（模拟
     网络失败）后重试复用同一 action_id；服务端只创建一个 GenerationBatch、每张图各
     一次图片提交；刷新页面不自动重放，批次与候选从磁盘恢复。
  B. 另一个工作空间点「先看方案」：恰好 1 次 /api/plan/compile、0 次 /api/generations、
     0 次图片提交，方案与 Prompt 全部落盘。

运行：
  & "C:\\Users\\31368\\.local\\bin\\uv.exe" run --no-project --with-requirements requirements.txt --with playwright python tools/verify_product_v1_suite_command_ui.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import threading
import time
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

from app.product_v1_server import ProductApplication, create_product_server  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from src.application_service import ApplicationService  # noqa: E402

EVIDENCE = ROOT / "evals" / "product-demo"


def action_id_of(post_data: bytes) -> str | None:
    """Read the action_id from either a multipart form body or a JSON body."""
    if not post_data:
        return None
    found = re.search(rb'name="action_id"\r\n\r\n([A-Za-z0-9_-]+)', post_data)
    if found:
        return found.group(1).decode("ascii")
    json_found = re.search(rb'"action_id"\s*:\s*"([A-Za-z0-9_-]+)"', post_data)
    return json_found.group(1).decode("ascii") if json_found else None


def fill_intake(page, name: str) -> None:
    page.locator("#product-name").fill(name)
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

    with tempfile.TemporaryDirectory(prefix="amz-d47-suite-ui-") as raw:
        root = Path(raw)
        queue = [root / "direct-suite", root / "preview-plan"]
        picked: list[Path] = []
        image_provider = ui.FakeImageProvider()
        service = ApplicationService(
            semantic_provider_factory=ui.semantic_provider_factory,
            image_provider_factory=lambda: image_provider,
        )
        app = ProductApplication(
            service=service,
            recent_index_path=root / "recent.json",
            folder_picker=lambda _purpose: str(
                picked.append(queue.pop(0)) or picked[-1]) if queue else str(root / "extra"),
        )
        server = create_product_server("127.0.0.1", 0, application=app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()

                attempts = {"total": 0, "aborted": 0, "continued": 0, "action_ids": []}
                compile_posts = {"total": 0}

                def watch(request) -> None:
                    path = urlsplit(request.url).path
                    if request.method == "POST" and path == "/api/generations":
                        attempts["total"] += 1
                    if request.method == "POST" and path == "/api/plan/compile":
                        compile_posts["total"] += 1

                page.on("request", watch)

                def interrupt_first_generation(route) -> None:
                    found = action_id_of(route.request.post_data_buffer or b"")
                    if found:
                        attempts["action_ids"].append(found)
                    if attempts["aborted"] == 0:
                        attempts["aborted"] = 1
                        route.abort()
                    else:
                        attempts["continued"] += 1
                        route.continue_()

                page.route("**/api/generations", interrupt_first_generation)
                page.goto(base_url + "/", wait_until="networkidle")

                # ---- A. 空白工作空间 + 直接一键整套。
                page.get_by_role("button", name="新建商品套图").click()
                page.wait_for_selector("#intake-screen:not([hidden])")
                fill_intake(page, "验证商品-直接整套")
                workspace_a = picked[-1]
                url_a = base_url + "/api/workspace?directory=" + quote(str(workspace_a), safe="")

                image_provider.plan(
                    [("SUCCEEDED", f"d47-suite-{index}") for index in range(1, 13)])
                page.evaluate(
                    "() => { const b = document.getElementById('generate-suite'); b.click(); b.click(); }")
                page.wait_for_function(
                    "() => { const b = document.getElementById('generate-suite');"
                    " return b && !b.disabled; }", timeout=30000)
                check("double-click-one-write-attempt", attempts["total"] == 1, dict(attempts))
                check("first-attempt-interrupted", attempts["aborted"] == 1, dict(attempts))

                page.get_by_role("button", name="生成整套图片").click()
                expect(page.locator("#save-state")).to_contain_text("已开始生成")
                page.wait_for_selector("#generation-shots .generation-shot", timeout=60000)
                deadline = time.time() + 90
                rows: list[dict] = []
                while time.time() < deadline:
                    data = page.request.get(url_a).json()["data"]
                    rows = (data.get("plan") or {}).get("shot_specs") or []
                    if rows and all(shot.get("candidates") for shot in rows):
                        break
                    page.wait_for_timeout(500)
                shot_count = len(rows)
                check("generation-materialized", shot_count > 0
                      and all(shot.get("candidates") for shot in rows),
                      {"shots": shot_count})
                expect(page.locator("#generation-shots .generation-state")).to_have_text(
                    ["已完成"] * shot_count, timeout=60000)

                reuse = {"ids": list(attempts["action_ids"]), "total": attempts["total"],
                         "continued": attempts["continued"], "aborted": attempts["aborted"]}
                check("retry-reuses-one-action-id",
                      len(attempts["action_ids"]) == 2 and len(set(attempts["action_ids"])) == 1,
                      reuse)
                check("one-attempt-reached-server",
                      attempts["total"] == 2 and attempts["continued"] == 1, reuse)

                batches = sorted((workspace_a / "generations").glob("batch_*.json"))
                attempt_counts = [len(shot.get("generation_attempts") or []) for shot in rows]
                candidate_counts = [len(shot.get("candidates") or []) for shot in rows]
                check("one-generation-batch", len(batches) == 1, {"batches": len(batches)})
                check("one-attempt-per-shot", attempt_counts == [1] * shot_count, attempt_counts)
                check("each-shot-has-candidate", all(count >= 1 for count in candidate_counts),
                      candidate_counts)
                check("paid-submissions-equal-shots",
                      len(image_provider.submit_calls) == shot_count,
                      {"submissions": len(image_provider.submit_calls), "shots": shot_count})

                page.screenshot(
                    path=str(EVIDENCE / f"d4.7-suite-command-ui-{stamp}-generated.png"),
                    full_page=True)

                total_before_reload = attempts["total"]
                page.reload(wait_until="networkidle")
                page.wait_for_selector("#generation-shots .generation-shot", timeout=60000)
                expect(page.locator("#generation-shots .generation-state")).to_have_text(
                    ["已完成"] * shot_count, timeout=60000)
                check("reload-does-not-resubmit", attempts["total"] == total_before_reload,
                      {"before": total_before_reload, "after": attempts["total"]})
                check("reload-keeps-single-batch",
                      len(sorted((workspace_a / "generations").glob("batch_*.json"))) == 1,
                      {"batches": 1})

                # ---- B. 先看方案：只编译，不提交图片。
                page.get_by_role("button", name="所有工作空间").click()
                page.wait_for_selector("#home-screen:not([hidden])")
                compile_before = compile_posts["total"]
                generations_before = attempts["total"]
                submissions_before = len(image_provider.submit_calls)

                page.get_by_role("button", name="新建商品套图").click()
                page.wait_for_selector("#intake-screen:not([hidden])")
                fill_intake(page, "验证商品-先看方案")
                workspace_b = picked[-1]
                url_b = base_url + "/api/workspace?directory=" + quote(str(workspace_b), safe="")

                page.get_by_role("button", name="先看方案").click()
                expect(page.locator("#save-state")).to_contain_text("方案已生成")
                page.wait_for_selector("#plan-shots .plan-shot", timeout=30000)
                prepared = page.request.get(url_b).json()["data"]
                shots_b = (prepared.get("plan") or {}).get("shot_specs") or []
                check("preview-compile-once", compile_posts["total"] - compile_before == 1,
                      {"compile_posts": compile_posts["total"] - compile_before})
                check("preview-no-generation-post",
                      attempts["total"] == generations_before,
                      {"generations": attempts["total"] - generations_before})
                check("preview-no-image-submission",
                      len(image_provider.submit_calls) == submissions_before,
                      {"submissions": len(image_provider.submit_calls) - submissions_before})
                check("preview-persisted-everything",
                      bool(shots_b) and all(shot.get("latest_prompt") for shot in shots_b),
                      {"shots": len(shots_b)})
                page.screenshot(
                    path=str(EVIDENCE / f"d4.7-suite-command-ui-{stamp}-plan.png"),
                    full_page=True)

                context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    report = {"stamp": stamp, "checks": checks, "failures": failures,
              "passed": not failures, "workspaces": "temp (deleted)"}
    out = EVIDENCE / f"d4.7-suite-command-ui-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        return 1
    print("D4.7 一键整套命令的浏览器级证据通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
