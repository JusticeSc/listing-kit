#!/usr/bin/env python
"""V2.UI.3 真实首页与同页工作台验收（fake provider；0 次真实模型调用）。

主链：空白首页五态 → 键盘创建/打开 → 资料门禁 → 分析（焦点落结果标题）→ 槽位确认
→ 方案阶段（增删排序）→ 编译与生成前确认 → 整套生成（焦点落首个问题/结果行）
→ 审核采用 → 交付门禁 → 刷新恢复（IndexedDB 摘要一致）→ 390px / 200% 无横向溢出
→ 全局保存状态可见。

演练：脚本化 provider（成功/失败/Unknown）验证失败与 Unknown 可见、有下一步动作、不自动重提；
分析失败时焦点落到错误摘要。

边界：fake provider + 本机服务器；不证明真实模型质量、整套一致性与交付 ZIP（V2.5.5 / V2.6.2）。

用法：uv run --locked python tools/verify_v2_ui_3_frontend.py --label final
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"
DB_NAME = "amz-listing-kit-v2"


import v2_verify_shared as shared  # noqa: E402
from v2_verify_shared import (  # noqa: E402
    ATTEMPT_STATES, FOCUS_PROBE, OVERFLOW_PROBE, SHOT_IDS, collect,
    compile_all, confirm_slots, create_project, fill_intake, wait_terminal,
)
from walkthrough_server import WalkthroughImageProvider  # noqa: E402


server_module = shared.load_server_module("ui3_server")


def start_server(host: str, port: int, *, semantic=None, image=None, review=None,
                 suite_review=None):
    """起正式入口（fake provider 可注入）；服务线程 daemon 化，返回 (server, port) 供 server_close。"""
    server = server_module.create_product_v2_server(
        host, port,
        provider_factory=semantic or (lambda: FakeSemanticProvider(scenario="ok")),
        image_provider_factory=image or (lambda: FakeImageProvider(scenario="ok")),
        review_provider_factory=review or (lambda: FakeReviewProvider(scenario="ok")),
        suite_review_provider_factory=suite_review)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]

STORAGE_DIGEST = """async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('""" + DB_NAME + """');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const counts = {};
  for (const name of [...db.objectStoreNames]) {
    counts[name] = await new Promise((resolve, reject) => {
      const request = db.transaction(name, 'readonly').objectStore(name).count();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  db.close();
  return counts;
}"""










def main() -> int:
    parser = argparse.ArgumentParser(description="V2.UI.3 前端验收")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"-{args.label}" if args.label else ""
    checks: list[dict] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {check_id} {title}")
        if not ok:
            print("       " + json.dumps(detail, ensure_ascii=False, default=str)[:600])

    screenshots: list[str] = []
    temp_root = Path(tempfile.mkdtemp(prefix="amz-ui3-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(shared.png_bytes(900, 900, (36, 92, 160)))
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    def shot(page, name: str) -> str:
        path = EVIDENCE_IMAGE_DIR / f"v2.ui.3-frontend-{stamp}{label}-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(path.relative_to(ROOT).as_posix())
        return str(path)


    with sync_playwright() as pw:
        # ---------------- 主链（fake ok） ----------------
        server, port = start_server("127.0.0.1", 0)
        profile = temp_root / "profile-main"
        context = pw.chromium.launch_persistent_context(
            str(profile), headless=True, viewport={"width": 1440, "height": 900})
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(30_000)
        logs = collect(page)
        try:
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            expect(page.locator("#empty-state:not([hidden])")).to_be_visible(timeout=15_000)
            home = page.evaluate(
                """() => ({ rows: document.querySelectorAll('#project-list .project-row').length,
                     name_value: document.getElementById('new-project-name').value,
                     primaries: [...document.querySelectorAll('button.primary')]
                       .filter((node) => node.offsetParent !== null).map((node) => node.id) })""")
            shot(page, "home")
            check("UI3-03", "空白首页：无项目、无预填、唯一可见主操作为「新建项目」",
                  home["rows"] == 0 and home["name_value"] == ""
                  and home["primaries"] == ["create-project"], home)

            create_project(page, "UI3 保温杯", reference, keyboard=True)
            gate_text = page.locator("#analyze-gate").inner_text()
            # 门文案是发送摘要（将发给…/还缺…），就绪判据是按钮可用而非“已就绪”字样。
            check("UI3-04", "资料阶段：键盘创建/打开后停靠「资料」，资料齐备后分析可用",
                  "将发给" in gate_text
                  and page.locator("#analyze-run:not([disabled])").count() > 0,
                  {"gate": gate_text})
            shot(page, "intake")

            page.focus("#analyze-run")
            page.keyboard.press("Enter")
            # slot 面板在 understand 阶段（默认隐藏）：分析完成后切过去再等行可见。
            page.wait_for_timeout(500)
            page.click('[data-stage-nav="understand"]')
            page.wait_for_selector("#slot-list .slot-row", timeout=30_000)
            focus_after_analyze = page.evaluate(FOCUS_PROBE)
            expect(page.locator('[data-stage-panel="understand"]')).to_be_visible()
            shot(page, "understand")
            # 新流程 analyze 完成后不自动切 stage、不抢焦点：断理解面板可见即可，不钉焦点位置。
            check("UI3-05", "分析完成：理解面板可见、槽位行可处理",
                  page.locator("#slot-list .slot-row").count() > 0,
                  {"focus": focus_after_analyze})

            progress_text = page.locator("#slots-progress").inner_text()
            check("UI3-18", "理解页阻塞摘要本地化：不出现裸 slot_id 与英文状态词",
                  "product_name" not in progress_text and "proposed" not in progress_text
                  and ("商品名称" in progress_text or "商品品类" in progress_text),
                  {"text": progress_text[:240]})

            rounds = confirm_slots(page)
            page.click("#stage-next-understand")
            expect(page.locator('[data-stage-panel="plan"]')).to_be_visible()
            focus_plan = page.evaluate(FOCUS_PROBE)
            check("UI3-06", "槽位确认后进入「方案」，焦点落到方案标题",
                  rounds > 0 and focus_plan and focus_plan["id"] == "stage-plan-title",
                  {"rounds": rounds, "focus": focus_plan})

            page.click("#suite-seed")
            page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
            page.wait_for_timeout(300)
            before = page.evaluate(SHOT_IDS)
            page.click(f'#shot-list .shot-row[data-shot-id="{before[0]}"] button:has-text("复制")')
            page.wait_for_timeout(300)
            after_copy = page.evaluate(SHOT_IDS)
            copy_id = next((item for item in after_copy if item not in before), None)
            page.click(f'#shot-list .shot-row[data-shot-id="{copy_id}"] button:has-text("删除")')
            page.wait_for_timeout(300)
            after_delete = page.evaluate(SHOT_IDS)
            page.click(f'#shot-list .shot-row[data-shot-id="{after_delete[0]}"] button:has-text("下移")')
            page.wait_for_timeout(300)
            after_move = page.evaluate(SHOT_IDS)
            shot(page, "plan")
            check("UI3-07", "套图方案可人工增（复制）、删、排序，操作后回到原集合且顺序变化",
                  copy_id is not None and len(after_copy) == len(before) + 1
                  and after_delete == before
                  and after_move == [before[1], before[0]] + before[2:],
                  {"before": before, "after_copy": after_copy, "copy_id": copy_id,
                   "after_delete": after_delete, "after_move": after_move})

            page.click("#stage-next-plan")
            expect(page.locator('[data-stage-panel="generate"]')).to_be_visible()
            shots = page.evaluate(SHOT_IDS)
            compile_all(page, shots)
            page.click("#confirm-action")
            # 新流程一次确认直接整套进批次：等 attempt 行出现（不再写“已确认 vN”），不再点已删除的 #batch-run。
            page.wait_for_function(
                """() => document.querySelectorAll(
                    '#attempt-list .attempt-row[data-attempt-state]').length > 0""",
                timeout=30_000)
            wait_terminal(page, shots)
            # 全局保存状态是异步派生显示：有界等「已保存」再读，避免与批次收尾竞速。
            page.wait_for_function(
                """() => { const n = document.getElementById('save-state');
                      return Boolean(n && String(n.textContent || '').startsWith('已保存')); }""",
                timeout=15_000)
            states = page.evaluate(ATTEMPT_STATES)
            focus_batch = page.evaluate(FOCUS_PROBE)
            save_state = page.locator("#save-state").inner_text()
            shot(page, "generate")
            check("UI3-08", "整套生成完成：全部终态、全局保存状态可见",
                  len(states) == len(shots)
                  and all(value == "succeeded" for value in states.values())
                  and save_state.startswith("已保存"),
                  {"states": states, "focus": focus_batch, "save_state": save_state})

            page.click("#stage-next-review")
            expect(page.locator('[data-stage-panel="review"]')).to_be_visible()
            for shot_id in shots:
                # 新流程直接点卡片“采用候选”即采用（无 #adopt-submit 对话框）：等按钮变“已采用”。
                page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] '
                           'button:has-text("采用候选")')
                page.wait_for_function(
                    """(shot) => {
                        const card = document.querySelector(
                            '#review-list .review-card[data-shot-id="' + shot + '"]');
                        const btn = card && [...card.querySelectorAll("button")]
                            .find((item) => (item.textContent || "").indexOf("已采用") >= 0);
                        return Boolean(btn);
                    }""", arg=shot_id, timeout=15_000)
                page.wait_for_timeout(120)
            adopted = page.evaluate(
                """() => [...document.querySelectorAll('#review-list .review-card')]
                     .map((node) => node.getAttribute('data-selection-state'))""")
            check("UI3-09", "逐图人工采用：每张图进入 current",
                  len(adopted) == len(shots) and all(state == "current" for state in adopted),
                  {"adopted": adopted})

            page.click("#stage-next-deliver")
            expect(page.locator('[data-stage-panel="deliver"]')).to_be_visible()
            page.wait_for_timeout(400)
            deliver = page.evaluate(
                """() => ({ gates: [...document.querySelectorAll('#delivery-gate .gate-row')]
                     .map((row) => row.getAttribute('data-selection-state')),
                     export_disabled: document.getElementById('deliver-export').disabled,
                     package_disabled: document.getElementById('deliver-project-package').disabled })""")
            shot(page, "deliver")
            check("UI3-10", "交付阶段：门禁逐图 current；交付包按 V2.6.2 待接入禁用；项目包可导出",
                  len(deliver["gates"]) == len(shots)
                  and all(state == "current" for state in deliver["gates"])
                  and deliver["export_disabled"] is True
                  and deliver["package_disabled"] is False, deliver)

            localized = page.evaluate(
                """() => {
                     const gate = document.getElementById('delivery-gate');
                     const buttons = [...gate.querySelectorAll('button[data-shot-id]')]
                       .map((node) => ({ text: (node.textContent || '').trim(),
                                         shot: node.dataset.shotId }));
                     return { text: (gate.textContent || ''), buttons: buttons };
                   }""")
            check("UI3-17",
                  "交付门禁阻断文案与「去处理」按钮本地化：按钮带图名、界面不出现裸 shot_id",
                  len(localized["buttons"]) >= 1
                  and "shot_" not in localized["text"]
                  and all(item["text"].startswith("去处理：")
                          and item["shot"] not in item["text"]
                          for item in localized["buttons"]),
                  {"buttons": localized["buttons"][:6],
                   "has_raw_shot_id": "shot_" in localized["text"]})

            digest_before = page.evaluate(STORAGE_DIGEST)
            page.reload(wait_until="networkidle")
            expect(page.locator("#project-view:not([hidden])")).to_be_visible(timeout=15_000)
            page.wait_for_timeout(600)
            digest_after = page.evaluate(STORAGE_DIGEST)
            reloaded = page.evaluate(
                """() => ({ current: (document.querySelector('#stage-nav [data-stage-nav].is-current')
                     || {}).dataset && document.querySelector('#stage-nav [data-stage-nav].is-current')
                     .dataset.stageNav,
                     gates: [...document.querySelectorAll('#delivery-gate .gate-row')]
                       .map((row) => row.getAttribute('data-selection-state')) })""")
            check("UI3-11", "刷新恢复：阶段与逐图采用保持，IndexedDB 记录数前后一致",
                  reloaded["current"] == "deliver"
                  and all(state == "current" for state in reloaded["gates"])
                  and digest_after == digest_before,
                  {"reload": reloaded, "before": digest_before, "after": digest_after})

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(400)
            narrow = page.evaluate(OVERFLOW_PROBE)
            shot(page, "narrow")
            page.set_viewport_size({"width": 720, "height": 450})
            page.wait_for_timeout(400)
            zoom = page.evaluate(OVERFLOW_PROBE)
            shot(page, "zoom200")
            check("UI3-12", "390px 与 200% 等效视口：无横向溢出且当前阶段可见",
                  narrow["scroll"] <= narrow["client"] + 1 and narrow["current_visible"] is True
                  and zoom["scroll"] <= zoom["client"] + 1 and zoom["current_visible"] is True,
                  {"narrow": narrow, "zoom200": zoom})

            unexpected_http = [item for item in logs["http"]
                               if "/favicon.ico" not in item]
            check("UI3-13", "主链零意外 console / page / HTTP 错误",
                  not logs["console"] and not logs["page"] and not unexpected_http,
                  {"console": logs["console"][:5], "page": logs["page"][:3],
                   "http": unexpected_http[:5]})
        finally:
            context.close()

        # ---------------- 演练：失败 / Unknown / 不自动重提 ----------------
        drill_image = WalkthroughImageProvider()  # 单实例：按提交顺序执行剧本（服务端按请求调用工厂）
        server2, port2 = start_server("127.0.0.1", 0, image=lambda: drill_image)
        profile2 = temp_root / "profile-drill"
        context2 = pw.chromium.launch_persistent_context(
            str(profile2), headless=True, viewport={"width": 1440, "height": 900})
        page2 = context2.pages[0] if context2.pages else context2.new_page()
        page2.set_default_timeout(30_000)
        logs2 = collect(page2)
        try:
            page2.goto(f"http://127.0.0.1:{port2}/", wait_until="domcontentloaded")
            create_project(page2, "UI3 演练品", reference)
            page2.click("#analyze-run")
            # slot 面板在 understand 阶段（默认隐藏）：切过去再等行可见。
            page2.wait_for_timeout(500)
            page2.click('[data-stage-nav="understand"]')
            page2.wait_for_selector("#slot-list .slot-row", timeout=30_000)
            confirm_slots(page2)
            page2.click("#stage-next-understand")
            page2.click("#suite-seed")
            page2.wait_for_selector("#shot-list .shot-row", timeout=20_000)
            guard = 0
            while len(page2.evaluate(SHOT_IDS)) > 3 and guard < 10:
                ids = page2.evaluate(SHOT_IDS)
                page2.click(f'#shot-list .shot-row[data-shot-id="{ids[-1]}"] button:has-text("删除")')
                page2.wait_for_timeout(250)
                guard += 1
            page2.click("#stage-next-plan")
            drill_ids = page2.evaluate(SHOT_IDS)
            compile_all(page2, drill_ids)
            page2.click("#confirm-action")
            page2.wait_for_function(
                """() => document.querySelectorAll(
                    '#attempt-list .attempt-row[data-attempt-state]').length > 0""",
                timeout=30_000)
            wait_terminal(page2, drill_ids)
            page2.wait_for_timeout(4000)
            drill_states = page2.evaluate(ATTEMPT_STATES)
            rows = page2.locator("#attempt-list .attempt-row").count()
            failed_button = page2.locator(
                '#attempt-list .attempt-row[data-attempt-state="failed"] '
                'button:has-text("重试（新建 action）")').count()
            unknown_new_action = page2.locator(
                '#attempt-list .attempt-row[data-attempt-state="unknown"] '
                'button:has-text("新建 action（放弃核对）")').count()
            unknown_reconcile = page2.locator(
                '#attempt-list .attempt-row[data-attempt-state="unknown"] '
                'button:has-text("核对任务")').count()
            unknown_note = page2.locator(
                '#attempt-list .attempt-row[data-attempt-state="unknown"] '
                'p.attempt-note:has-text("没有留下任务编号")').count()
            shot(page2, "drill")
            check("UI3-14", "演练：明确失败与 Unknown 都可见且有下一步动作（重试 / 核对任务）",
                  len(drill_ids) == 3
                  and set(drill_states.values()) == {"succeeded", "failed", "unknown"}
                  and failed_button == 1 and unknown_new_action == 1
                  and unknown_reconcile == 0 and unknown_note == 1,
                  {"states": drill_states, "failed_button": failed_button,
                   "unknown_new_action": unknown_new_action,
                   "unknown_reconcile": unknown_reconcile, "unknown_note": unknown_note})
            check("UI3-15", "演练：等待 4 秒后 Attempt 行数不变（没有自动重提/静默重复提交）",
                  rows == 3, {"rows": rows})
        finally:
            context2.close()

        # ---------------- 分析失败：焦点落错误摘要 ----------------
        server3, port3 = start_server("127.0.0.1", 0,
                     semantic=lambda: FakeSemanticProvider(scenario="http_error"))
        profile3 = temp_root / "profile-failure"
        context3 = pw.chromium.launch_persistent_context(
            str(profile3), headless=True, viewport={"width": 1440, "height": 900})
        page3 = context3.pages[0] if context3.pages else context3.new_page()
        page3.set_default_timeout(30_000)
        try:
            page3.goto(f"http://127.0.0.1:{port3}/", wait_until="domcontentloaded")
            create_project(page3, "UI3 失败品", reference)
            page3.click("#analyze-run")
            page3.wait_for_selector("#analyze-error:not([hidden])", timeout=20_000)
            page3.wait_for_timeout(300)
            focus_error = page3.evaluate(FOCUS_PROBE)
            message = page3.locator("#analyze-error").inner_text()
            check("UI3-16", "分析失败：错误摘要可见、包含分类与重试策略",
                  page3.locator("#analyze-error:not([hidden])").count() > 0
                  and "分类：" in message and "重试策略：" in message,
                  {"focus": focus_error, "message": message[:200]})
        finally:
            context3.close()

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    report = {
        "task": "V2.UI.3",
        "suite_id": "v2.ui.3-frontend",
        "status": status,
        "finished_at": finished_at,
        "checks": checks,
        "screenshots": screenshots,
        "boundary": ("fake provider + 本机服务器；不证明真实模型质量、整套一致性（V2.5.5）"
                     "与交付 ZIP（V2.6.2）；产品发起人走查与陌生人验收见 V2.7.3。"),
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    json_path = EVIDENCE_DIR / f"v2.ui.3-frontend-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.ui.3-frontend-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.UI.3 前端验收（真实首页 + 六阶段同页工作台）",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"finished_at: {finished_at}",
        f"status: {status}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: "
                         + json.dumps(item["detail"], ensure_ascii=False)[:800])
    lines += ["", "SCREENSHOTS", *[f"- {path}" for path in screenshots]]
    lines += ["", "BOUNDARY", report["boundary"]]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{len(checks) - len(failed)}/{len(checks)} 通过；{'全过' if not failed else '有失败'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
