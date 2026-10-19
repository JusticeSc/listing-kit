#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V2.7.3 走查内部预演：非内置品类 + 全链截图 + 观察采集（fake provider，零模型调用）。

用途：在真人走查（C15/C17）之前，用确定性 fake 通道把「第一次使用者」的完整任务
走一遍，把每个关键节点的界面原文、耗时与截图落盘，供发布前修复可见摩擦点。
它不是 C15/C17 的人工证据：执行者是开发者本人，观察表只用于找问题。

剧本按四段工作台（资料与事实 → 方案 → 制作与审图 → 交付）走：每一步的页面交互
都复用 `v2_verify_shared` 里已被登记验证器使用的惯例（选用批量范围、一次明确提交、
逐图采用、整套检查跳转、导出与独立解包），不在这里另写一套选择器。

判据以「用户看得见的东西」为准：VLM 复核等状态读主行文本/行属性（库只作辅助核对），
整套检查入口必须真的存在并聚焦、390px 与 125%/200% 实际缩放无横向溢出、200% 下键盘
可达导出、交付包 manifest 声明与解包字节逐条
相等，返工后显式选新候选再采用、并核对交付包里的确是那张候选。

运行：uv run --locked python tools/rehearse_v273_walkthrough.py --label lamp
参考图默认 `_working/amz-listing-kit-product-demo/real-run-lamp/lamp-3m.jpg`（落地灯，非内置品类）。
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

EVIDENCE = ROOT / "evals" / "product-v2"
IMG = EVIDENCE / "evidence"


import v2_verify_shared as shared  # noqa: E402
import v2_stage_nav as stage_nav  # noqa: E402


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
    parser.add_argument("--skip-vlm", action="store_true",
                        help="跳过单图 VLM 复核步（默认执行：对第 1 张跑一次假通道复核）。")
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

    def review_report(page, shot_id: str) -> dict:
        """该图最新的复核报告（内存库读取；未跑过返回空对象）。

        同一张图会同时存在确定性报告（vlm=null）与 VLM 报告：只在有 vlm 的行里取最新，
        否则会把早期确定性报告当成复核结果（2026-10-19 独立复核发现的旧读数即由此而来）。
        用户可见的判据在调用处的主行文本上，这里只作辅助核对。
        """
        return page.evaluate(
            """async (shot) => {
              const db = await new Promise((resolve, reject) => {
                const request = indexedDB.open("amz-listing-kit-v2");
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
              });
              const documents = await new Promise((resolve, reject) => {
                const request = db.transaction("documents", "readonly")
                  .objectStore("documents").getAll();
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
              });
              db.close();
              const rows = documents.filter((row) => row.kind === "review_report"
                && row.payload && row.payload.shot_id === shot);
              const withVlm = rows.filter((row) => row.payload.vlm);
              const pool = withVlm.length ? withVlm : rows;
              pool.sort((a, b) => (a.version || 0) - (b.version || 0));
              const last = pool[pool.length - 1];
              return last ? { document_id: last.document_id, version: last.version,
                              vlm: last.payload.vlm || null,
                              versions: rows.map((row) => row.version),
                              vlm_versions: withVlm.map((row) => row.version) } : {};
            }""", arg=shot_id)

    server, _doubles = shared.start_product_server(
        0,
        image_factory=lambda: shared.FakeImageProvider(scenario="ok", size=args.image_size),
        suite_factory=lambda: shared.FakeSuiteReviewProvider(scenario="ok"))
    port = server.port
    try:
        with sync_playwright() as pw:
            profile = ROOT / "_working" / f"rehearsal-profile-{args.label}-{stamp}"
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1440, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = shared.collect(page)
            try:
                started = time.monotonic()
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                expect(page.locator("#empty-state:not([hidden])")).to_be_visible(timeout=15_000)
                probes["home_empty_text"] = page.locator("#empty-state").inner_text()
                snap(page, "home")
                mark("home", started)

                started = time.monotonic()
                # 首页控件在应用就绪前是 disabled；用 fill+点击（产品文案里的真实路径）而不是
                # 盲打字：lit 重渲染会吞掉正在输入的按键（2026-10-19 复跑实测到过一次）。
                page.wait_for_selector("#new-project-name:not([disabled])", timeout=20_000)
                page.wait_for_selector("#create-project:not([disabled])", timeout=20_000)
                project_name = "V273 " + args.product_name
                for _ in range(4):
                    page.fill("#new-project-name", project_name)
                    if page.input_value("#new-project-name") == project_name:
                        break
                    page.wait_for_timeout(300)
                else:
                    raise AssertionError("项目名输入框无法保留输入值（重渲染吞键？）")
                page.click("#create-project")
                page.wait_for_selector("#project-view:not([hidden])", timeout=20_000)
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
                # 分析后产品不自动切页：按 V2.UI.2 纪律点阶段条进入「资料与事实」（用户真实路径）。
                stage_nav.goto(page, "intake")
                page.wait_for_selector("#slot-list .slot-row", timeout=60_000)
                page.wait_for_timeout(400)
                probes["slot_rows"] = page.locator("#slot-list .slot-row").count()
                probes["intake_panel_text"] = page.locator(
                    '[data-stage-panel="intake"]').inner_text()[:700]
                snap(page, "facts")
                snap(page, "facts-full", full=True)
                rounds = shared.confirm_slots(page)
                probes["confirm_rounds"] = rounds
                # 产品自己的进度行：「必须确认的槽位 X / Y 已确认 · 待处理 N 项 · 共 M 项」。
                # 产品只拦关键槽位；非必填槽位可以留空推进，所以断言关键槽位清零，其余如实记录。
                intake_text = page.locator('[data-stage-panel="intake"]').inner_text()
                progress_pattern = re.compile(r"必须确认的槽位\s*(\d+)\s*/\s*(\d+)\s*已确认")
                progress_line = next(
                    (line for line in intake_text.splitlines()
                     if progress_pattern.search(line)), "")
                probes["intake_progress_text"] = progress_line
                match = progress_pattern.search(progress_line)
                if not match or match.group(1) != match.group(2):
                    raise AssertionError("必须确认的槽位没有全部确认：" + repr(progress_line))
                probes["intake_pending_rows"] = page.evaluate(
                    """() => [...document.querySelectorAll('#slot-list .slot-row')]
                         .filter((row) => !["confirmed", "superseded"]
                           .includes(row.getAttribute("data-status") || ""))
                         .map((row) => ({ slot: row.getAttribute("data-slot-id"),
                                          critical: row.getAttribute("data-critical"),
                                          status: row.getAttribute("data-status") }))""")
                mark("facts", started, confirm_rounds=rounds)

                started = time.monotonic()
                page.click("#stage-next-plan")
                expect(page.locator('[data-stage-panel="plan"]')).to_be_visible()
                page.click("#suite-seed")
                page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
                page.wait_for_timeout(300)
                probes["plan_shots"] = page.evaluate(shared.SHOT_IDS)
                snap(page, "plan")
                mark("plan", started)

                started = time.monotonic()
                page.click("#stage-next-make")
                expect(page.locator('[data-stage-panel="make"]')).to_be_visible()
                shots_ids = page.evaluate(shared.SHOT_IDS)
                # Issue #9 差量：先如实记录「默认只发送正看的 1 张」，再显式选全量批量。
                page.wait_for_selector("#confirm-editor:not([hidden])", timeout=30_000)
                page.wait_for_selector("#confirm-list .confirm-shot", timeout=30_000)
                page.wait_for_timeout(200)
                probes["default_scope_text"] = page.locator("#generation-scope-count").inner_text()
                probes["default_scope_rows"] = page.locator("#confirm-list .confirm-shot").count()
                probes["decisions"] = shared.decide_for_compile(page, shots_ids)
                shared.compile_all(page, shots_ids)
                probes["batch_count"] = shared.choose_make_batch(page, shots_ids)
                probes["batch_scope_text"] = page.locator("#generation-scope-count").inner_text()
                snap(page, "make-confirm")
                # 确认即提交，无需二步：一次明确点击，捕获外发请求并核对授权绑定。
                submit = shared.confirm_and_submit(page, expect, shot_ids=shots_ids)
                probes["submit"] = {"ok": submit["ok"], "new_shots": submit["new_shots"],
                                    "captured_actions": submit["captured_actions"]}
                shared.wait_terminal(page, shots_ids, timeout=90_000)
                page.wait_for_timeout(400)
                probes["attempt_states"] = page.evaluate(shared.ATTEMPT_STATES)
                not_done = {key: value for key, value in probes["attempt_states"].items()
                            if value != "succeeded"}
                if not_done:
                    # wait_terminal 也接受 failed/unknown：走查要的是「四张都真的成功」。
                    raise AssertionError("批量提交后有图未成功：" + repr(not_done))
                probes["batch_progress_text"] = page.locator("#batch-progress").inner_text()[:300]
                probes["task_rows"] = page.evaluate(
                    """() => [...document.querySelectorAll('#task-list-mount [data-task-shot]')]
                         .map((row) => ({ shot: row.getAttribute('data-task-shot'),
                                          state: row.getAttribute('data-attempt-state'),
                                          selection: row.getAttribute('data-selection-state'),
                                          text: (row.innerText || '').slice(0, 160) }))""")
                snap(page, "make-done")
                snap(page, "make-done-full", full=True)
                mark("make", started)

                if not args.skip_vlm:
                    # 单图 VLM 复核（假通道返回高风险发现）：只提示、不阻断、不改选择。
                    started = time.monotonic()
                    vlm_target = shots_ids[0]
                    shared.select_make_shot(page, vlm_target)
                    before_report = review_report(page, vlm_target)
                    review_row = page.locator(
                        f'#shot-execution [data-shot-id="{vlm_target}"] .attempt-review')
                    expect(review_row).to_be_visible(timeout=20_000)
                    before_text = review_row.inner_text()[:400]
                    vlm_button = page.locator("#shot-execution button[data-review-action]")
                    expect(vlm_button).to_be_enabled(timeout=20_000)
                    vlm_button.click()
                    # 用户可见的结果先成立：本图执行区主行写「VLM 已检查」（行上的 data-review-*
                    # 是确定性报告视图，vlm 字段不在这里），比较面板的披露区把 outcome 挂在
                    # [data-compare-vlm] 上——两处都读，库里的报告只作辅助核对。
                    expect(review_row).to_contain_text("VLM 已检查", timeout=90_000)
                    compare_vlm = page.locator("#compare-panel [data-compare-vlm]")
                    expect(compare_vlm).to_have_attribute(
                        "data-compare-vlm", "checked", timeout=30_000)
                    after_attr = compare_vlm.get_attribute("data-compare-vlm")
                    after_report = review_report(page, vlm_target)
                    if (after_report.get("vlm") or {}).get("outcome") != "checked":
                        raise AssertionError("复核报告未记 checked：" + repr(after_report))
                    probes["vlm_review"] = {
                        "shot": vlm_target,
                        "before_version": before_report.get("version"),
                        "after_version": after_report.get("version"),
                        "last_versions": after_report.get("versions"),
                        "vlm_versions": after_report.get("vlm_versions"),
                        "compare_vlm_attr": after_attr,
                        "compare_vlm_text": (compare_vlm.text_content() or "")[:200],
                        "outcome": (after_report.get("vlm") or {}).get("outcome"),
                        "before_text": before_text,
                        "after_text": review_row.inner_text()[:400],
                    }
                    snap(page, "vlm-review")
                    mark("vlm-review", started)

                rework_shot = shots_ids[0]
                rework_before_ids: list = []
                adopted_ids: dict[str, str] = {}
                if not args.skip_rework:
                    started = time.monotonic()
                    shared.select_make_shot(page, rework_shot)
                    expect(page.locator("#compare-panel")).to_be_visible(timeout=20_000)
                    candidates_before = page.locator(
                        '#compare-candidates [role="tab"]').count()
                    rework_before_ids = page.evaluate(
                        """() => [...document.querySelectorAll('#compare-candidates [role="tab"]')]
                             .map((tab) => tab.getAttribute("data-candidate-id"))""")
                    expect(page.locator("#rework-open")).to_be_enabled(timeout=20_000)
                    page.click("#rework-open")
                    expect(page.locator("#rework-panel")).to_be_visible()
                    page.click('label[data-problem-id="product_fidelity"]')
                    page.fill("#rework-direction",
                              "只修正商品主体的轮廓与比例，颜色、材质和标识保持不变。")
                    page.click("#rework-preview")
                    expect(page.locator("#rework-preview-box")).to_be_visible(timeout=20_000)
                    snap(page, "rework-preview")
                    page.click("#rework-submit")
                    expect(page.locator("#rework-panel")).to_be_hidden(timeout=40_000)
                    # 返工经单图确认外发：面板关闭只代表提交返回，新候选落库要等候选链增长。
                    page.wait_for_function(
                        """(payload) => document.querySelectorAll(
                             '#compare-candidates [role="tab"]').length > payload""",
                        arg=candidates_before, timeout=90_000)
                    page.wait_for_timeout(300)
                    probes["rework"] = {
                        "shot": rework_shot,
                        "candidates_before": candidates_before,
                        "candidates_after": page.locator(
                            '#compare-candidates [role="tab"]').count(),
                        "attempt_state": page.evaluate(shared.ATTEMPT_STATES).get(rework_shot),
                    }
                    snap(page, "rework-compare")
                    mark("rework", started)

                started = time.monotonic()
                for shot_id in shots_ids:
                    if shot_id == rework_shot and not args.skip_rework:
                        # 返工后显式看新候选再采用：采用哪张是人的决定，不靠面板默认视图。
                        shared.select_make_shot(page, shot_id)
                        tabs = page.locator('#compare-candidates [role="tab"]')
                        new_candidate_id = ""
                        for index in range(tabs.count()):
                            tab = tabs.nth(index)
                            candidate_id = tab.get_attribute("data-candidate-id")
                            if candidate_id not in rework_before_ids:
                                new_candidate_id = candidate_id or ""
                                tab.click()
                                break
                        if not new_candidate_id:
                            raise AssertionError("返工后找不到新候选页签")
                        page.wait_for_timeout(300)
                        adopt = page.locator("#compare-panel #adopt-open")
                        expect(adopt).to_be_enabled(timeout=30_000)
                        adopt.click()
                        page.wait_for_function(
                            """(ids) => {
                              const panel = document.getElementById("compare-panel");
                              if (!panel || panel.hidden) return false;
                              const tab = panel.querySelector(
                                '#compare-candidates [data-candidate-id="' + ids.candidate + '"]');
                              const row = document.querySelector(
                                '#task-list-mount [data-task-shot="' + ids.shot + '"]');
                              return Boolean(tab && tab.querySelector(".badge.is-adopted"))
                                && Boolean(row)
                                && row.getAttribute("data-selection-state") === "current";
                            }""",
                            arg={"shot": shot_id, "candidate": new_candidate_id}, timeout=90_000)
                        adopted_ids[shot_id] = new_candidate_id
                        probes["rework"]["adopted_candidate"] = new_candidate_id
                    else:
                        shared.adopt_make_shot(page, shot_id)
                probes["selection_states_after"] = page.evaluate(
                    """() => [...document.querySelectorAll('#task-list-mount [data-task-shot]')]
                         .map((row) => ({ shot: row.getAttribute('data-task-shot'),
                                          selection: row.getAttribute('data-selection-state') }))""")
                snap(page, "make-adopted")
                mark("adopt", started)

                started = time.monotonic()
                stage_nav.goto(page, "deliver")
                page.wait_for_timeout(500)
                probes["deliver_gate_text"] = page.locator("#delivery-gate").inner_text()[:900]
                probes["deliver_jump_buttons"] = page.evaluate(
                    """() => [...document.querySelectorAll('#delivery-gate button[data-shot-id]')]
                         .map((node) => ({ text: (node.textContent || '').trim(),
                                           shot: node.dataset.shotId }))""")
                probes["deliver_export_disabled"] = page.locator("#deliver-export").is_disabled()
                snap(page, "deliver")
                snap(page, "deliver-full", full=True)

                # 整套一致性阻断应带定位入口：点它聚焦交付阶段里的整套检查（假通道 clean）。
                # 这条正是 V2.6.11 的历史红灯（拒绝时没有入口按钮），不能退化成「有就点、没有也过」。
                suite_jump = page.locator('#delivery-gate button[data-suite-action="run"]')
                expect(suite_jump).to_have_count(1, timeout=15_000)
                jump_text = suite_jump.first.inner_text().strip()
                if "整套检查" not in jump_text:
                    raise AssertionError("整套检查入口文案异常：" + repr(jump_text))
                probes["deliver_suite_jump_text"] = jump_text
                suite_jump.first.click()
                expect(page.locator("#suite-review-run")).to_be_focused(timeout=15_000)
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
                stage_nav.goto(page, "deliver")
                page.wait_for_timeout(600)
                expect(page.locator("#deliver-export")).to_be_enabled(timeout=30_000)
                probes["deliver_export_after_suite"] = not page.locator(
                    "#deliver-export").is_disabled()
                snap(page, "deliver-ready")
                export_dir = ROOT / "_working" / "amz-listing-kit-product-v2" / "rehearsal-exports"
                export_dir.mkdir(parents=True, exist_ok=True)
                export_path = export_dir / f"{stamp}-{args.label}-delivery.zip"
                download = shared.download_delivery(page, export_path)
                inside = shared.inspect_zip(export_path)
                if inside["broken"] is not None:
                    raise AssertionError("交付包内有损坏条目：" + repr(inside["broken"]))
                digest_mismatch = {
                    name: info for name, info in inside["digests"].items()
                    if info["sha256"] != info["declared"]
                    or (info["declared_size"] is not None
                        and info["byte_size"] != info["declared_size"])}
                if digest_mismatch:
                    raise AssertionError("manifest 声明与实际字节不一致：" + repr(digest_mismatch))
                probes["export"] = {
                    "file_name": download["filename"],
                    "bytes": download["bytes"],
                    "sha256": download["sha256"],
                    "entries": inside["names"][:12],
                    "has_manifest": "manifest.json" in inside["names"],
                    "broken": inside["broken"],
                    "manifest_image_count": len(inside["digests"]),
                    "digests": {name: {"sha256": info["sha256"], "declared": info["declared"],
                                       "byte_size": info["byte_size"],
                                       "declared_size": info["declared_size"]}
                                for name, info in inside["digests"].items()},
                    "images": inside["images"],
                    "saved_to": str(export_path.relative_to(ROOT)),
                }
                if adopted_ids.get(rework_shot):
                    expected_name = f"images/{rework_shot}-{adopted_ids[rework_shot]}.png"
                    delivered = [name for name in inside["images"]
                                 if name.startswith(f"images/{rework_shot}-")]
                    if delivered != [expected_name]:
                        raise AssertionError(
                            "交付包里该图不是刚采用的返工候选：" + repr(delivered)
                            + " 期望 " + expected_name)
                    probes["export"]["adopted_rework_image"] = delivered[0]
                page.wait_for_timeout(400)
                probes["deliver_result_text"] = page.locator(
                    "#delivery-result").inner_text()[:300]
                snap(page, "deliver-exported")
                mark("deliver", started)

                # 390px 复核：四个阶段各看一次有没有横向溢出
                page.set_viewport_size({"width": 390, "height": 844})
                for stage in ("intake", "plan", "make", "deliver"):
                    stage_nav.goto(page, stage)
                    page.wait_for_timeout(400)
                    probes[f"overflow_{stage}_390"] = page.evaluate(shared.OVERFLOW_PROBE)
                    snap(page, f"{stage}-390")
                overflow = {key: value for key, value in probes.items()
                            if key.startswith("overflow_") and isinstance(value, dict)
                            and (value.get("scroll") or 0) > (value.get("client") or 0)}
                if overflow:
                    # 只记录不断言的话，这个探针就会在真溢出时也绿着过去。
                    raise AssertionError("390px 出现横向溢出：" + repr(overflow))
                # 先把窗口恢复成 1440×900，否则缩放覆盖会被 390 宽的窗口钳住（实测 390 宽）。
                page.set_viewport_size({"width": 1440, "height": 900})

                # 实际浏览器缩放（125%/200%）：合同要求「实际缩放」，只缩 viewport 不算 zoom。
                # 用 CDP deviceScaleFactor 让 CSS 视口 = 物理 1440×900 ÷ 倍数，截图的物理宽度
                # 必须仍是 1440 —— 那才证明是缩放而不是换了个更窄的窗口。
                zoom_session = context.new_cdp_session(page)

                def apply_zoom(factor: float) -> dict:
                    zoom_session.send("Emulation.setDeviceMetricsOverride", {
                        "width": round(1440 / factor), "height": round(900 / factor),
                        "deviceScaleFactor": factor, "mobile": False,
                        "screenWidth": 1440, "screenHeight": 900})
                    page.wait_for_timeout(350)
                    return page.evaluate(
                        "() => ({inner_width: innerWidth, inner_height: innerHeight,"
                        " dpr: devicePixelRatio})")

                def focus_probe() -> dict:
                    # 与 V2.6.4 同一「焦点可见」定义：轮廓或 box-shadow 任一存在。
                    return page.evaluate("""() => {
                      const el = document.activeElement;
                      if (!el || el === document.body) return {id: "", visible: false};
                      const rect = el.getBoundingClientRect();
                      const style = getComputedStyle(el);
                      const cx = rect.left + rect.width / 2;
                      const cy = rect.top + rect.height / 2;
                      const hit = document.elementFromPoint(cx, cy);
                      return {id: el.id || el.tagName,
                              visible: rect.width > 0 && rect.height > 0,
                              outline: (style.outlineStyle !== "none"
                                        && style.outlineWidth !== "0px")
                                || style.boxShadow !== "none",
                              in_view: rect.top >= -1 && rect.left >= -1
                                && rect.bottom <= innerHeight + 1 && rect.right <= innerWidth + 1,
                              hit_self: !!hit && (hit === el || el.contains(hit))};
                    }""")

                def png_width(raw: bytes) -> int:
                    return struct.unpack(">I", raw[16:20])[0]

                def cdp_screenshot() -> bytes:
                    # Playwright 的 page.screenshot() 会按 context viewport 重设 emulation，
                    # 把我们的缩放覆盖清掉（实测：截图后 documentElement.clientWidth 回到 1440）。
                    # 直接走 CDP 截屏，保住缩放后再读布局数字。
                    data = zoom_session.send("Page.captureScreenshot", {"format": "png"})
                    return base64.b64decode(data["data"])

                def snap_zoom(node: str) -> None:
                    name = f"v273-rehearsal-{stamp}-{node}.png"
                    (IMG / name).write_bytes(cdp_screenshot())
                    shots.append(name)

                zoom_evidence: dict[str, object] = {}
                for factor in (1.25, 2.0):
                    metrics = apply_zoom(factor)
                    if abs(float(metrics.get("dpr") or 0) - factor) > 1e-6:
                        raise AssertionError(f"{factor} 倍缩放没有生效：{metrics}")
                    physical = png_width(cdp_screenshot())
                    if physical != 1440:
                        raise AssertionError(
                            f"{factor} 倍缩放的物理宽度是 {physical}，不是 1440：这不是缩放")
                    per_stage: dict[str, object] = {}
                    for stage in ("intake", "plan", "make", "deliver"):
                        stage_nav.goto(page, stage)
                        page.wait_for_timeout(400)
                        live = page.evaluate(
                            "() => ({dpr: devicePixelRatio, w: innerWidth})")
                        if abs(float(live.get("dpr") or 0) - factor) > 1e-6:
                            raise AssertionError(
                                f"{int(factor * 100)}% 缩放在 {stage} 被重置：{live}")
                        stage_overflow = page.evaluate(shared.OVERFLOW_PROBE)
                        per_stage[stage] = {"overflow": stage_overflow, "focus": focus_probe(),
                                            "metrics": live}
                        snap_zoom(f"{stage}-zoom{int(round(factor * 100))}")
                        if (stage_overflow.get("scroll") or 0) > (stage_overflow.get("client") or 0):
                            raise AssertionError(
                                f"{int(factor * 100)}% 缩放在 {stage} 出现横向溢出："
                                + repr(stage_overflow))
                    # 交付门禁的逐图行带 data-selection-state；面板里的静态说明句也含「已采用」，
                    # 用文本匹配会恒真（独立复核指出的空转判据），所以按行状态与行宽度判。
                    gate_rows = page.evaluate("""() => [...document.querySelectorAll(
                        '[data-stage-panel="deliver"] .gate-row')].map((row) => {
                          const rect = row.getBoundingClientRect();
                          return { shot: row.getAttribute('data-shot-id'),
                                   state: row.getAttribute('data-selection-state'),
                                   in_width: rect.left >= -1 && rect.right <= innerWidth + 1 };
                        })""")
                    not_adopted = [row for row in gate_rows
                                   if row.get("state") != "current"]
                    clipped = [row for row in gate_rows if not row.get("in_width")]
                    zoom_evidence[f"{factor}"] = {
                        "metrics": metrics, "physical_width": physical, "stages": per_stage,
                        "gate_rows": gate_rows}
                    if not gate_rows or not_adopted:
                        raise AssertionError(
                            f"{int(factor * 100)}% 缩放下交付门禁没有全部处于已采用："
                            + repr(not_adopted or "没有门禁行"))
                    if clipped:
                        raise AssertionError(
                            f"{int(factor * 100)}% 缩放下门禁行被横向裁掉：" + repr(clipped))

                # 200% 缩放下用键盘走到交付导出：Tab 全程可达、焦点可见不被遮挡，Enter 真下载。
                # 从文档头开始走：<body> 本身不可聚焦，直接 body.focus() 是空操作，
                # 焦点会沿用上一个点击（导航按钮），那样「全程可达」只证明了相邻控件可达。
                page.evaluate("""() => { document.body.setAttribute('tabindex', '-1');
                                         document.body.focus(); }""")
                if page.evaluate("() => document.activeElement === document.body") is not True:
                    raise AssertionError("无法把键盘起点重置到文档头")
                key_path: list[dict] = []
                reached = False
                for _ in range(160):
                    page.keyboard.press("Tab")
                    focus = focus_probe()
                    if not focus.get("id"):
                        # Tab 走到文档末尾会掉回 body：这本身就是没到达导出。
                        break
                    key_path.append(focus)
                    if focus.get("id") == "deliver-export":
                        reached = True
                        break
                if not reached:
                    raise AssertionError(
                        "200% 缩放下从文档头 Tab 到不了交付导出（" + str(len(key_path)) + " 步）："
                        + repr([item.get("id") for item in key_path][:40]))
                if len(key_path) < 6:
                    raise AssertionError(
                        "键盘路径过短，像没从文档头开始：" + repr([item.get("id") for item in key_path]))
                blocked = [item for item in key_path
                           if not item.get("visible") or not item.get("outline")]
                last_focus = key_path[-1]
                if blocked:
                    raise AssertionError(
                        "键盘路径上存在不可见或无轮廓的焦点：" + repr(blocked[:6]))
                if not last_focus.get("in_view") or not last_focus.get("hit_self"):
                    raise AssertionError("导出按钮获得焦点后被遮挡：" + repr(last_focus))
                export_key_path = export_dir / f"{stamp}-{args.label}-keyboard.zip"
                with page.expect_download(timeout=120_000) as keyboard_download:
                    page.keyboard.press("Enter")
                saved = keyboard_download.value
                saved.save_as(str(export_key_path))
                keyboard_zip = shared.inspect_zip(export_key_path)
                if keyboard_zip["broken"] is not None:
                    raise AssertionError("键盘导出的交付包有损坏条目："
                                         + repr(keyboard_zip["broken"]))
                key_mismatch = {
                    name: info for name, info in keyboard_zip["digests"].items()
                    if info["sha256"] != info["declared"]
                    or (info["declared_size"] is not None
                        and info["byte_size"] != info["declared_size"])}
                if key_mismatch:
                    raise AssertionError("键盘导出的 manifest 声明与实际字节不一致："
                                         + repr(key_mismatch))
                # 不只是数一数：逐图身份（文件名 + sha + 字节数）必须与鼠标导出完全相同。
                def digest_map(source: dict) -> dict:
                    return {name: [info["sha256"], info["byte_size"]]
                            for name, info in source.items()}
                if digest_map(keyboard_zip["digests"]) != digest_map(
                        probes["export"]["digests"]):
                    raise AssertionError(
                        "键盘导出的包与鼠标导出的采用集不一致："
                        + repr(sorted(digest_map(keyboard_zip["digests"]).items())
                               ^ sorted(digest_map(probes["export"]["digests"]).items())))
                zoom_evidence["keyboard"] = {
                    "steps": len(key_path),
                    "focus_ids_tail": [item.get("id") for item in key_path][-6:],
                    "final_focus": last_focus,
                    "file_name": saved.suggested_filename,
                    "bytes": export_key_path.stat().st_size,
                    "has_manifest": "manifest.json" in keyboard_zip["names"],
                    "saved_to": str(export_key_path.relative_to(ROOT))}
                probes["zoom_and_keyboard"] = zoom_evidence
                zoom_session.send("Emulation.clearDeviceMetricsOverride")
                page.wait_for_timeout(300)
                page.set_viewport_size({"width": 1440, "height": 900})
                restored = page.evaluate("() => ({dpr: devicePixelRatio, w: innerWidth})")
                if abs(float(restored.get("dpr") or 0) - 1.0) > 1e-6 or restored.get("w") != 1440:
                    raise AssertionError("缩放没有恢复到 100%：" + repr(restored))
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
        server.stop()

    report = EVIDENCE / f"v273-rehearsal-{stamp}.md"
    lines = [
        f"# V2.7.3 走查内部预演（非人工证据）· {stamp}",
        "",
        "> NOT-AUTHORITY：本文件是开发者自跑的内部预演（fake 通道、零模型调用），",
        "> 用于在真人走查前暴露摩擦点；不构成 C15/C17 的人工走查证据。",
        "",
        f"- 入口：本机 fake 走查服务器（tools/rehearse_v273_walkthrough.py，label={args.label}）",
        f"- 商品/参考图：{args.product_name}（非内置品类）· {reference.name}",
        "- 剧本（四段工作台）：新建项目 → 资料与事实（上传/填写/分析/逐条确认）→ 方案（推荐套图）→",
        "  制作与审图（默认单张范围 → 显式全量批量 → 一次明确提交 → 单图 VLM 复核 →",
        "  单图返工 → 返工图显式选新候选后逐图采用）→ 交付（整套检查 → 导出 ZIP）→ 390px 四阶段复核 →",
        "  实际 125%/200% 缩放（CDP deviceScaleFactor，物理宽仍 1440）与 200% 下键盘导出",
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
          + "；逐图跳转按钮=" + str(len(probes.get("deliver_jump_buttons") or []))
          + "；整套检查入口=" + str(probes.get("deliver_suite_jump_text") or "（缺失）"))
    print("返工候选 " + str((probes.get("rework") or {}).get("candidates_before")) + "→"
          + str((probes.get("rework") or {}).get("candidates_after"))
          + "；整套检查=" + str(probes.get("suite_status_text"))[:40])
    print("导出=" + str(export.get("file_name")) + " bytes=" + str(export.get("bytes"))
          + " manifest=" + str(export.get("has_manifest")))
    zoom = probes.get("zoom_and_keyboard") or {}
    keyboard = zoom.get("keyboard") or {}
    print("缩放=" + str([round(float(key), 2) for key in zoom if key not in ("keyboard",)])
          + " 物理宽=" + str([(zoom[key] or {}).get("physical_width")
                              for key in zoom if key not in ("keyboard",)])
          + "；键盘导出步数=" + str(keyboard.get("steps"))
          + " bytes=" + str(keyboard.get("bytes")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
