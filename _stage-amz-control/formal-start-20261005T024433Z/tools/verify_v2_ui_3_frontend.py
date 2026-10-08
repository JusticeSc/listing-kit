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


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


server_module = load_module(ROOT / "app" / "product_v2_server.py", "ui3_server")
v251 = load_module(ROOT / "tools" / "verify_v2_5_1_deterministic_review.py", "ui3_v251")
walkthrough = load_module(ROOT / "tools" / "walkthrough_server.py", "ui3_walkthrough")

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

OVERFLOW_PROBE = """() => ({
  scroll: document.documentElement.scrollWidth,
  client: document.documentElement.clientWidth,
  current_visible: (() => {
    const el = document.querySelector('#stage-nav [data-stage-nav].is-current');
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return rect.left >= -1 && rect.right <= window.innerWidth + 1;
  })(),
})"""

FOCUS_PROBE = """() => {
  const el = document.activeElement;
  if (!el) return null;
  return { id: el.id || null, cls: String(el.className || ""), shot: el.getAttribute
    ? el.getAttribute("data-shot-id") : null };
}"""

SHOT_IDS = """() => [...document.querySelectorAll('#shot-list .shot-row')]
  .map((row) => row.getAttribute('data-shot-id'))"""

ATTEMPT_STATES = """() => Object.fromEntries(
  [...document.querySelectorAll('#attempt-list .attempt-row[data-shot-id]')]
    .map((row) => [row.getAttribute('data-shot-id'),
                   row.getAttribute('data-attempt-state')]))"""


def compile_all(page, shot_ids: list[str]) -> None:
    for shot_id in shot_ids:
        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
        page.click(card + " .toolbar button")
        page.wait_for_selector(card + '[data-prompt-state="saved"]', timeout=30_000)
        page.wait_for_timeout(120)


def confirm_slots(page) -> int:
    guard = 0
    while (page.locator("#slot-list .slot-row")
           .get_by_role("button", name="确认", exact=True).count() > 0 and guard < 30):
        (page.locator("#slot-list .slot-row")
         .get_by_role("button", name="确认", exact=True).first.click())
        page.wait_for_timeout(200)
        guard += 1
    return guard


def wait_terminal(page, ids: list[str], timeout: int = 60_000) -> None:
    page.wait_for_function(
        """(ids) => ids.every((shotId) => {
             const node = document.querySelector(
               '#attempt-list .attempt-row[data-shot-id="' + shotId + '"]');
             const state = node && node.getAttribute('data-attempt-state');
             return state === 'succeeded' || state === 'failed' || state === 'unknown';
           })""", arg=ids, timeout=timeout)


def fill_intake(page, reference: Path, name: str = "UI3 验收商品") -> None:
    page.set_input_files("#ref-file", str(reference))
    page.wait_for_selector("#ref-list .ref-row", timeout=10_000)
    page.fill("#intake-name", name)
    page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封，杯身哑光。")
    page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
    page.wait_for_selector("#analyze-run:not([disabled])", timeout=15_000)


def create_project(page, name: str, reference: Path, *, keyboard: bool = False) -> None:
    if keyboard:
        page.focus("#new-project-name")
        page.keyboard.type(name)
        page.keyboard.press("Enter")
    else:
        page.fill("#new-project-name", name)
        page.click("#create-project")
    # R3.3：新建即打开——不再回列表行点 open；等待即等“工作台已完整装载”。
    page.wait_for_selector("#project-view:not([hidden])", timeout=15_000)
    page.wait_for_function(
        "() => (document.getElementById('project-view') || {}).dataset.ready === '1'",
        timeout=15_000)
    fill_intake(page, reference, name)


def start_server(host: str, port: int, *, semantic=None, image=None, review=None,
                 suite_review=None):
    server = server_module.create_product_v2_server(
        host, port,
        provider_factory=semantic or (lambda: FakeSemanticProvider(scenario="ok")),
        image_provider_factory=image or (lambda: FakeImageProvider(scenario="ok")),
        review_provider_factory=review or (lambda: FakeReviewProvider(scenario="ok")),
        suite_review_provider_factory=suite_review)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def collect(page) -> dict:
    logs = {"console": [], "page": [], "http": []}
    page.on("console", lambda message: logs["console"].append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: logs["page"].append(str(error)))
    page.on("response", lambda response: logs["http"].append(
        f"{response.status} {response.url}") if response.status >= 400 else None)
    return logs


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
    reference.write_bytes(v251.png_bytes(900, 900, (36, 92, 160)))
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    def shot(page, name: str) -> str:
        path = EVIDENCE_IMAGE_DIR / f"v2.ui.3-frontend-{stamp}{label}-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(path.relative_to(ROOT).as_posix())
        return str(path)

    # ---------------- 静态守卫 ----------------
    html = (ROOT / "app" / "product_v2" / "index.html").read_text(encoding="utf-8")
    shell = (ROOT / "app" / "product_v2" / "ui" / "stage-shell.js").read_text(encoding="utf-8")
    home_states = all(marker in html for marker in (
        'id="create-form"', 'id="import-trigger"', 'id="empty-state"',
        'id="project-list"', 'id="home-error"', 'id="home-status"'))
    workbench = all(marker in html for marker in (
        'id="stage-summary"', 'id="save-state"'))
    focusable_titles = len([line for line in html.splitlines()
                            if '<h3 id="stage-' in line and 'tabindex="-1"' in line]) == 6
    shell_clean = not any(bad in shell for bad in (
        "indexedDB", "localStorage", "fetch(", "XMLHttpRequest", "repository"))
    no_inline = 'style="' not in html
    no_external = "http://" not in html.replace("http://www.w3.org", "")
    check("UI3-01", "首页五态（空/列表/创建/导入/异常）与工作台摘要、全局保存状态在正式入口就位",
          home_states and workbench, {"home_states": home_states, "workbench": workbench})
    check("UI3-02", "六阶段标题可聚焦（tabindex=-1）；外壳纯净（无存储/网络引用）；无内联样式与外部资源",
          focusable_titles and shell_clean and no_inline and no_external,
          {"focusable_titles": focusable_titles, "shell_clean": shell_clean,
           "no_inline": no_inline, "no_external": no_external})

    with sync_playwright() as pw:
        # ---------------- 主链（fake ok） ----------------
        port = v251.free_port()
        start_server("127.0.0.1", port)
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
            check("UI3-04", "资料阶段：键盘创建/打开后停靠「资料」，资料齐备后分析可用",
                  "已就绪" in gate_text, {"gate": gate_text})
            shot(page, "intake")

            page.focus("#analyze-run")
            page.keyboard.press("Enter")
            page.wait_for_selector("#slot-list .slot-row", timeout=30_000)
            page.wait_for_timeout(300)
            focus_after_analyze = page.evaluate(FOCUS_PROBE)
            expect(page.locator('[data-stage-panel="understand"]')).to_be_visible()
            shot(page, "understand")
            check("UI3-05", "分析完成：自动进入「理解」且焦点落到结果标题",
                  focus_after_analyze and focus_after_analyze["id"] == "stage-understand-title",
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
            expect(page.locator("#confirm-record")).to_contain_text("已确认 v", timeout=10_000)
            page.click("#batch-run")
            wait_terminal(page, shots)
            page.wait_for_timeout(500)
            states = page.evaluate(ATTEMPT_STATES)
            focus_batch = page.evaluate(FOCUS_PROBE)
            save_state = page.locator("#save-state").inner_text()
            shot(page, "generate")
            check("UI3-08", "整套生成完成：全部终态、焦点落到第一个结果/问题行、全局保存状态可见",
                  len(states) == len(shots)
                  and all(value == "succeeded" for value in states.values())
                  and focus_batch and focus_batch["cls"].startswith("attempt-row")
                  and save_state.startswith("已保存"),
                  {"states": states, "focus": focus_batch, "save_state": save_state})

            page.click("#stage-next-review")
            expect(page.locator('[data-stage-panel="review"]')).to_be_visible()
            for shot_id in shots:
                page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] '
                           'button:has-text("采用候选")')
                expect(page.locator("#adopt-submit")).to_be_enabled(timeout=10_000)
                page.click("#adopt-submit")
                page.wait_for_selector("#adopt-status:not([hidden])", timeout=15_000)
            adopted = page.evaluate(
                """() => [...document.querySelectorAll('#review-list .review-card')]
                     .map((node) => node.getAttribute('data-selection-state'))""")
            shot(page, "review")
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
        port2 = v251.free_port()
        drill_image = walkthrough.WalkthroughImageProvider()  # 单实例：按提交顺序执行剧本（服务端按请求调用工厂）
        start_server("127.0.0.1", port2, image=lambda: drill_image)
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
            expect(page2.locator("#confirm-record")).to_contain_text("已确认 v", timeout=10_000)
            page2.click("#batch-run")
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
        port3 = v251.free_port()
        start_server("127.0.0.1", port3,
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
            check("UI3-16", "分析失败：错误摘要可见、包含分类与重试策略，焦点落到错误摘要",
                  focus_error and focus_error["id"] == "analyze-error"
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
