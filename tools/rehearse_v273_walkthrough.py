#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V2.7.3 走查内部预演：非内置品类 + 全链截图 + 观察采集（fake provider，零模型调用）。

用途：在真人走查（C15/C17）之前，用确定性 fake 通道把「第一次使用者」的完整任务
走一遍，把每个关键节点的界面原文、耗时与截图落盘，供发布前修复可见摩擦点。
它不是 C15/C17 的人工证据：执行者是开发者本人，观察表只用于找问题。

运行：uv run --locked python tools/rehearse_v273_walkthrough.py --label lamp
参考图默认 `_working/amz-listing-kit-product-demo/real-run-lamp/lamp-3m.jpg`（落地灯，非内置品类）。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import socket
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

EVIDENCE = ROOT / "evals" / "product-v2"
IMG = EVIDENCE / "evidence"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ui3 = load_module(ROOT / "tools" / "verify_v2_ui_3_frontend.py", "rehearsal_ui3")

from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider  # noqa: E402


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.7.3 走查内部预演")
    parser.add_argument("--label", default="lamp")
    parser.add_argument("--reference", default="")
    parser.add_argument("--product-name", default="夹式 LED 阅读灯")
    parser.add_argument("--description", default="三档色温夹式 LED 阅读灯，USB-C 供电，关节臂可调。")
    parser.add_argument("--points", default="3 档色温|无级调光|USB-C 供电")
    parser.add_argument("--image-size", type=int, default=1024,
                        help="假图片边长；默认 1024 才越过「最小长边 1000px」平台阻断。")
    parser.add_argument("--skip-rework", action="store_true",
                        help="跳过单图返工步（默认执行：返工第 1 张并保留旧候选）。")
    args = parser.parse_args()

    reference = Path(args.reference) if args.reference else (
        ROOT / "_working" / "amz-listing-kit-product-demo" / "real-run-lamp" / "lamp-3m.jpg")
    if not reference.exists():
        print(f"参考图不存在：{reference}")
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    shots: list[str] = []
    timeline: list[dict] = []
    probes: dict[str, object] = {}

    def snap(page, node: str, full: bool = False) -> str:
        name = f"v273-rehearsal-{stamp}-{node}.png"
        page.screenshot(path=str(IMG / name), full_page=full)
        shots.append(name)
        return name

    def mark(node: str, started: float, **extra: object) -> None:
        item = {"node": node, "seconds": round(time.monotonic() - started, 1)}
        item.update(extra)
        timeline.append(item)

    port = free_port()
    server = ui3.start_server(
        "127.0.0.1", port,
        image=lambda: ui3.FakeImageProvider(scenario="ok", size=args.image_size),
        suite_review=lambda: FakeSuiteReviewProvider(scenario="ok"))
    try:
        with sync_playwright() as pw:
            profile = ROOT / "_working" / f"rehearsal-profile-{args.label}-{stamp}"
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1440, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = ui3.collect(page)
            try:
                started = time.monotonic()
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                expect(page.locator("#empty-state:not([hidden])")).to_be_visible(timeout=15_000)
                probes["home_empty_text"] = page.locator("#empty-state").inner_text()
                snap(page, "home")
                mark("home", started)

                started = time.monotonic()
                page.focus("#new-project-name")
                page.keyboard.type("V273 " + args.product_name)
                page.keyboard.press("Enter")
                page.wait_for_selector("#project-list .project-row", timeout=15_000)
                page.focus('#project-list .project-row button[data-action="open"]')
                page.keyboard.press("Enter")
                page.wait_for_selector("#project-view:not([hidden])", timeout=15_000)
                page.set_input_files("#ref-file", str(reference))
                page.wait_for_selector("#ref-list .ref-row", timeout=15_000)
                page.fill("#intake-name", args.product_name)
                page.fill("#intake-description", args.description)
                page.fill("#intake-selling-points", args.points.replace("|", "\n"))
                page.fill("#intake-focus", "夜间阅读")
                page.wait_for_selector("#analyze-run:not([disabled])", timeout=15_000)
                probes["intake_gate"] = page.locator("#analyze-gate").inner_text()
                snap(page, "intake")
                snap(page, "intake-full", full=True)
                mark("intake", started)

                started = time.monotonic()
                page.click("#analyze-run")
                page.wait_for_selector("#slot-list .slot-row", timeout=60_000)
                page.wait_for_timeout(400)
                probes["slot_rows"] = page.locator("#slot-list .slot-row").count()
                probes["understand_panel_text"] = page.locator(
                    '[data-stage-panel="understand"]').inner_text()[:700]
                snap(page, "understand")
                snap(page, "understand-full", full=True)
                mark("understand", started)

                started = time.monotonic()
                rounds = ui3.confirm_slots(page)
                probes["confirm_rounds"] = rounds
                page.click("#stage-next-understand")
                expect(page.locator('[data-stage-panel="plan"]')).to_be_visible()
                page.click("#suite-seed")
                page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
                page.wait_for_timeout(300)
                probes["plan_shots"] = page.evaluate(ui3.SHOT_IDS)
                snap(page, "plan")
                mark("plan", started, confirm_rounds=rounds)

                started = time.monotonic()
                page.click("#stage-next-plan")
                expect(page.locator('[data-stage-panel="generate"]')).to_be_visible()
                shots_ids = page.evaluate(ui3.SHOT_IDS)
                ui3.compile_all(page, shots_ids)
                snap(page, "generate-confirm")
                page.click("#confirm-action")
                expect(page.locator("#confirm-record")).to_contain_text("已确认 v", timeout=10_000)
                page.click("#batch-run")
                terminal_ok = True
                try:
                    ui3.wait_terminal(page, shots_ids, timeout=90_000)
                except Exception:
                    terminal_ok = False
                page.wait_for_timeout(400)
                probes["generate_terminal_ok"] = terminal_ok
                probes["attempt_states"] = page.evaluate(ui3.ATTEMPT_STATES)
                if not terminal_ok:
                    probes["attempt_list_text"] = page.locator("#attempt-list").inner_text()[:800]
                    probes["batch_bar_text"] = page.locator("#attempt-batch").inner_text()[:300]
                    probes["console_errors_dump"] = logs["console"][-5:]
                    probes["http_errors_dump"] = [item for item in logs["http"]
                                                  if "/favicon.ico" not in item][-5:]
                probes["review_next_disabled"] = page.locator("#stage-next-review").is_disabled()
                probes["review_next_note"] = page.locator("#stage-next-review-note").inner_text()
                probes["attempt_rows"] = page.evaluate(
                    """() => [...document.querySelectorAll('#attempt-list .attempt-row')]
                         .map((row) => ({ shot: row.getAttribute('data-shot-id'),
                                          state: row.getAttribute('data-attempt-state'),
                                          text: (row.innerText || '').slice(0, 160) }))""")
                snap(page, "generate-done")
                snap(page, "generate-done-full", full=True)
                mark("generate", started)

                started = time.monotonic()
                page.click("#stage-next-review")
                expect(page.locator('[data-stage-panel="review"]')).to_be_visible()
                page.wait_for_timeout(400)
                snap(page, "review")
                snap(page, "review-full", full=True)
                probes["review_states_before"] = page.evaluate(
                    """() => [...document.querySelectorAll('#review-list .review-card')]
                         .map((node) => node.getAttribute('data-selection-state'))""")
                first_card = '#review-list .review-card'
                compare = page.locator(first_card + ' button:has-text("比较候选")').first
                if compare.count() > 0:
                    compare.click()
                    page.wait_for_timeout(500)
                    snap(page, "compare")
                    snap(page, "compare-full", full=True)
                rework_shot = shots_ids[0]
                if not args.skip_rework:
                    started = time.monotonic()
                    if compare.count() == 0:
                        page.click(f'#review-list .review-card[data-shot-id="{rework_shot}"] '
                                   'button:has-text("比较候选")')
                        page.wait_for_timeout(400)
                    expect(page.locator("#compare-panel")).to_be_visible(timeout=10_000)
                    candidates_before = page.locator(
                        '#compare-candidates [role="tab"]').count()
                    expect(page.locator("#rework-open")).to_be_enabled(timeout=10_000)
                    page.click("#rework-open")
                    expect(page.locator("#rework-panel")).to_be_visible()
                    page.click('label[data-problem-id="product_fidelity"]')
                    page.fill("#rework-direction",
                              "只修正商品主体的轮廓与比例，颜色、材质和标识保持不变。")
                    page.click("#rework-preview")
                    expect(page.locator("#rework-preview-box")).to_be_visible(timeout=20_000)
                    snap(page, "rework-preview")
                    page.click("#rework-submit")
                    ui3.wait_terminal(page, [rework_shot], timeout=90_000)
                    page.wait_for_timeout(400)
                    page.click(f'#review-list .review-card[data-shot-id="{rework_shot}"] '
                               'button:has-text("比较候选")')
                    page.wait_for_timeout(500)
                    probes["rework"] = {
                        "shot": rework_shot,
                        "candidates_before": candidates_before,
                        "candidates_after": page.locator(
                            '#compare-candidates [role="tab"]').count(),
                        "attempt_state": page.evaluate(ui3.ATTEMPT_STATES).get(rework_shot),
                    }
                    snap(page, "rework-compare")
                    mark("rework", started)
                for shot_id in shots_ids:
                    page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] '
                               'button:has-text("采用候选")')
                    expect(page.locator("#adopt-submit")).to_be_enabled(timeout=10_000)
                    page.click("#adopt-submit")
                    page.wait_for_selector("#adopt-status:not([hidden])", timeout=15_000)
                probes["review_states_after"] = page.evaluate(
                    """() => [...document.querySelectorAll('#review-list .review-card')]
                         .map((node) => node.getAttribute('data-selection-state'))""")
                snap(page, "review-adopted")
                mark("review", started)

                started = time.monotonic()
                page.click("#stage-next-deliver")
                expect(page.locator('[data-stage-panel="deliver"]')).to_be_visible()
                page.wait_for_timeout(500)
                probes["deliver_gate_text"] = page.locator("#delivery-gate").inner_text()[:900]
                probes["deliver_jump_buttons"] = page.evaluate(
                    """() => [...document.querySelectorAll('#delivery-gate button[data-shot-id]')]
                         .map((node) => ({ text: (node.textContent || '').trim(),
                                           shot: node.dataset.shotId }))""")
                probes["deliver_export_disabled"] = page.locator("#deliver-export").is_disabled()
                snap(page, "deliver")
                snap(page, "deliver-full", full=True)

                # 整套一致性阻断应带定位入口：点它回审核阶段的整套检查（假通道 clean）
                suite_jump = page.locator('#delivery-gate button[data-suite-action="run"]')
                probes["deliver_suite_jump_text"] = (
                    suite_jump.first.inner_text() if suite_jump.count() else "")
                if suite_jump.count() == 0:
                    page.click('[data-stage-nav="review"]')
                else:
                    suite_jump.first.click()
                expect(page.locator('[data-stage-panel="review"]')).to_be_visible()
                probes["suite_run_focused"] = page.evaluate(
                    "() => (document.activeElement && document.activeElement.id) || ''")
                page.click("#suite-review-run")
                page.wait_for_function(
                    """() => {
                         const node = document.getElementById("suite-review-status");
                         const text = node ? (node.textContent || "") : "";
                         return Boolean(text) && !text.includes("尚未运行整套检查")
                           && !text.includes("检查中");
                       }""", timeout=90_000)
                probes["suite_status_text"] = page.locator("#suite-review-status").inner_text()
                probes["suite_note_text"] = page.locator("#suite-review-note").inner_text()
                probes["suite_findings_text"] = page.locator(
                    "#suite-review-findings").inner_text()[:400]
                page.click('[data-stage-nav="deliver"]')
                expect(page.locator('[data-stage-panel="deliver"]')).to_be_visible()
                page.wait_for_timeout(600)
                expect(page.locator("#deliver-export")).to_be_enabled(timeout=30_000)
                probes["deliver_export_after_suite"] = not page.locator(
                    "#deliver-export").is_disabled()
                snap(page, "deliver-ready")
                with page.expect_download(timeout=60_000) as download_info:
                    page.click("#deliver-export")
                download = download_info.value
                export_dir = ROOT / "_working" / "amz-listing-kit-product-v2" / "rehearsal-exports"
                export_dir.mkdir(parents=True, exist_ok=True)
                export_path = export_dir / (stamp + "-" + args.label + "-"
                                            + download.suggested_filename)
                download.save_as(str(export_path))
                zip_bytes = export_path.read_bytes()
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
                    names = sorted(archive.namelist())
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                probes["export"] = {
                    "file_name": download.suggested_filename,
                    "bytes": len(zip_bytes),
                    "sha256": hashlib.sha256(zip_bytes).hexdigest(),
                    "entries": names[:12],
                    "has_manifest": any(name.endswith("manifest.json") for name in names),
                    "attempt_states": [item.get("attempt_state")
                                       for item in (manifest.get("images") or [])],
                    "saved_to": str(export_path.relative_to(ROOT)),
                }
                page.wait_for_timeout(400)
                probes["deliver_result_text"] = page.locator(
                    "#delivery-result").inner_text()[:300]
                snap(page, "deliver-exported")
                mark("deliver", started)

                # 390px 复核：理解 / 审核 / 交付三个关键阶段
                page.set_viewport_size({"width": 390, "height": 844})
                for stage, node in (("understand", "understand-390"),
                                    ("review", "review-390"),
                                    ("deliver", "deliver-390")):
                    page.click(f'[data-stage-nav="{stage}"]')
                    page.wait_for_timeout(400)
                    probes[f"overflow_{stage}_390"] = page.evaluate(ui3.OVERFLOW_PROBE)
                    snap(page, node)
                page.set_viewport_size({"width": 1440, "height": 900})
                probes["console_errors"] = logs["console"]
                probes["page_errors"] = logs["page"]
                probes["http_errors"] = [item for item in logs["http"] if "/favicon.ico" not in item]
            except Exception as error:  # 崩了也留现场：截图 + 探针 dump，供人工判断
                probes["crash"] = f"{type(error).__name__}: {error}"[:600]
                try:
                    snap(page, "crash")
                except Exception:  # noqa: BLE001
                    pass
                (EVIDENCE / f"v273-rehearsal-{stamp}-crash.json").write_text(
                    json.dumps({"timeline": timeline, "probes": probes, "screenshots": shots,
                                "crash": probes["crash"]}, ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")
                raise
            finally:
                context.close()
    finally:
        server.shutdown()
        server.server_close()

    report = EVIDENCE / f"v273-rehearsal-{stamp}.md"
    lines = [
        f"# V2.7.3 走查内部预演（非人工证据）· {stamp}",
        "",
        "> NOT-AUTHORITY：本文件是开发者自跑的内部预演（fake 通道、零模型调用），",
        "> 用于在真人走查前暴露摩擦点；不构成 C15/C17 的人工走查证据。",
        "",
        f"- 入口：本机 fake 走查服务器（tools/rehearse_v273_walkthrough.py，label={args.label}）",
        f"- 商品/参考图：{args.product_name}（非内置品类）· {reference.name}",
        "- 剧本：new → intake → understand(确认全部) → plan(推荐方案) → generate(全部成功) →",
        "  review(比较+单图返工+逐图采用) → deliver(整套检查 → 导出 ZIP) → 390px 复核",
        "",
        "## 节点耗时",
        "",
        "| 节点 | 秒 |",
        "|---|---|",
    ]
    for item in timeline:
        lines.append(f"| {item['node']} | {item['seconds']} |")
    lines += ["", "## 采集探针", "", "```json",
              json.dumps(probes, ensure_ascii=False, indent=2)[:6000], "```", "",
              "## 截图", ""]
    for name in shots:
        lines.append(f"- evals/product-v2/evidence/{name}")
    lines += ["", "## 人工视审补充（开发者逐张看截图后填）", "", "（待补充）", ""]
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    payload = {"status": "ok", "finished_at": datetime.now().isoformat(timespec="seconds"),
               "reference": str(reference), "timeline": timeline, "probes": probes,
               "screenshots": shots}
    (EVIDENCE / f"v273-rehearsal-{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    print("报告：" + str(report.relative_to(ROOT)))
    print("截图 " + str(len(shots)) + " 张；节数 " + str(len(timeline)))
    export = probes.get("export") or {}
    print("初次门禁阻断=" + str(probes.get("deliver_export_disabled"))
          + "；跳转按钮=" + str(len(probes.get("deliver_jump_buttons") or [])))
    print("返工候选 " + str((probes.get("rework") or {}).get("candidates_before")) + "→"
          + str((probes.get("rework") or {}).get("candidates_after"))
          + "；整套检查=" + str(probes.get("suite_status_text"))[:40])
    print("导出=" + str(export.get("file_name")) + " bytes=" + str(export.get("bytes"))
          + " manifest=" + str(export.get("has_manifest")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
