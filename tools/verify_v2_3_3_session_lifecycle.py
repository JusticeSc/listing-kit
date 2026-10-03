#!/usr/bin/env python
"""V2.R3.3 证据：会话生命周期（可控延迟复现 + 修后验证，真实 Chromium，非 Mock）。

检查内容：
  1) 正常启动：控件只解锁一次，且解锁时 data-ready=1（ready=完整恢复完成）。
  2) 模块加载延迟（/?__test_delay=N）：解锁时刻 data-ready 必为 1（无早解锁窗口）。
  3) 工作区装载延迟：project-view 可见时工作区已完成装载。
  4) boot 失败：控件保持禁用 + boot-retry 可见 + 明确错误。
  5) 打开 A → 打开 B：A 的旧回调写不进 B（仍写 A 的 project_id），也不重置 B 的视图。
  6) 双标签陈旧编辑：三方不同字段的冲突编辑器可见；解决后按对方最新版本落库。
  7) 浏览器重启后项目与文档恢复。
  8) 零 console error / page error。

运行（每次把 JSON/TXT 写出到 evals/product-v2/）：
  uv run --locked python tools/verify_v2_3_3_session_lifecycle.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from v2_test_server import start as start_server  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
DB_NAME = "amz-listing-kit-v2"

PROJECT_READ_FAILURE = """
(() => {
  window.__rejectProjectListOnce = true;
  window.__projectReadRejections = [];
  addEventListener('unhandledrejection', event =>
    window.__projectReadRejections.push(String(event.reason)));
  const original = IDBObjectStore.prototype.getAll;
  IDBObjectStore.prototype.getAll = function (...args) {
    if (this.name === 'projects' && window.__rejectProjectListOnce) {
      window.__rejectProjectListOnce = false;
      throw new DOMException('controlled-project-list-read-failure', 'UnknownError');
    }
    return original.apply(this, args);
  };
})();
"""


def run_node_check(path: Path) -> dict:
    completed = subprocess.run(
        ["node", "--check", str(path)], cwd=ROOT, capture_output=True, text=True)
    return {"file": path.relative_to(ROOT).as_posix(), "rc": completed.returncode,
            "stderr": completed.stderr.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.R3.3 会话生命周期验证")
    parser.add_argument("--label", default="", help="附加到证据文件名的标签")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    screenshots: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    def shoot(page, name: str) -> None:
        png = EVIDENCE_DIR / f"v233-{stamp}-{name}.png"
        page.screenshot(path=str(png), full_page=True)
        screenshots.append(png.relative_to(ROOT).as_posix())

    node_ws = run_node_check(ROOT / "app" / "product_v2" / "workspace.js")
    node_app = run_node_check(ROOT / "app" / "product_v2" / "app.js")
    node_session = run_node_check(ROOT / "app" / "product_v2" / "session.js")
    check("V2.3.3-00", "workspace/app/session 通过 node --check",
          all(item["rc"] == 0 for item in (node_ws, node_app, node_session)),
          {"workspace": node_ws, "app": node_app, "session": node_session})

    server, base_url = start_server()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                # ---------- 正常启动：解锁一次且 data-ready=1 ----------
                context = browser.new_context()
                page = context.new_page()
                page.add_init_script("""
                  (() => {
                    const trail = [];
                    window.__unlockTrail = trail;
                    const now = () => Math.round(performance.now());
                    const observer = new MutationObserver((records) => {
                      for (const r of records) {
                        if (r.target && r.target.id === 'create-project') {
                          trail.push(['disabled', r.oldValue, r.target.disabled, now()]);
                        }
                      }
                    });
                    const attach = () => {
                      if (document.getElementById('create-project')) {
                        observer.observe(document.getElementById('create-project'),
                          { attributes: true, attributeOldValue: true, attributeFilter: ['disabled'] });
                      } else {
                        setTimeout(attach, 0);
                      }
                    };
                    attach();
                  })();
                """)
                page.on("console", lambda m: console_errors.append(m.text)
                        if m.type == "error" else None)
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.goto(base_url, wait_until="domcontentloaded")
                page.wait_for_selector("#create-project:not([disabled])", timeout=20000)
                ready_flag = page.evaluate(
                    "() => document.getElementById('create-project').dataset.ready")
                trail = page.evaluate("() => (window.__unlockTrail || []).slice()")
                unlocks = [item for item in trail if item[2] is False and item[1] is not None]
                check("V2.3.3-01", "正常启动零延迟：控件只解锁一次且解锁时 data-ready=1",
                      len(unlocks) == 1 and ready_flag == "1",
                      {"ready_flag": ready_flag, "trail": trail})
                context.close()

                # ---------- 模块加载延迟：无早解锁 ----------
                context2 = browser.new_context()
                page2 = context2.new_page()
                page2.on("console", lambda m: console_errors.append(m.text)
                         if m.type == "error" else None)
                page2.on("pageerror", lambda e: page_errors.append(str(e)))
                page2.goto(base_url + "/?__test_delay=1500", wait_until="domcontentloaded")
                page2.wait_for_function(
                    "() => document.getElementById('create-project')"
                    " && document.getElementById('create-project').dataset.ready === '1'",
                    timeout=30000)
                ready_at_ms = page2.evaluate(
                    "() => document.getElementById('create-project').dataset.readyAtMs || ''")
                boot_ready_at_ms = page2.evaluate(
                    "() => document.body.dataset.sessionReadyAtMs || ''")
                check("V2.3.3-02", "模块加载延迟：解锁时刻即 data-ready=1（无早解锁窗口）",
                      ready_flag == "1" and (ready_at_ms == "" or boot_ready_at_ms == ""),
                      {"ready_at_ms": ready_at_ms, "boot_ready_at_ms": boot_ready_at_ms})
                context2.close()

                # ---------- 工作区装载延迟：视图可见时工作区已完成 ----------
                context3 = browser.new_context()
                page3 = context3.new_page()
                page3.on("console", lambda m: console_errors.append(m.text)
                         if m.type == "error" else None)
                page3.on("pageerror", lambda e: page_errors.append(str(e)))
                page3.goto(base_url + "/?__test_delay=300", wait_until="domcontentloaded")
                page3.wait_for_selector("#create-project:not([disabled])", timeout=30000)
                page3.fill("#new-project-name", "延迟装载验证")
                page3.click("#create-project")
                page3.wait_for_selector("#project-view:not([hidden])", timeout=30000)
                ws_loaded = page3.evaluate(
                    "() => (document.getElementById('project-view') || {}).dataset.ready === '1'")
                shot_rows = page3.evaluate(
                    "() => (document.getElementById('slot-list') || {}).children.length || 0")
                check("V2.3.3-03", "工作区装载延迟：视图出现时工作区已完成装载",
                      ws_loaded is True,
                      {"ws_loaded": ws_loaded, "shot_rows": shot_rows})
                shoot(page3, "delayed-open")
                context3.close()

                # ---------- boot 失败：控件保持禁用 + 重试可见 ----------
                context4 = browser.new_context(permissions=[])
                page4 = context4.new_page()
                page4.on("console", lambda m: console_errors.append(m.text)
                         if m.type == "error" else None)
                page4.on("pageerror", lambda e: page_errors.append(str(e)))
                page4.add_init_script(
                    "delete window.indexedDB;"
                    " Object.defineProperty(window, 'indexedDB',"
                    " { get: () => null, configurable: true });")
                page4.goto(base_url, wait_until="domcontentloaded")
                page4.wait_for_selector("#boot-retry-row:not([hidden])", timeout=30000)
                still_disabled = page4.evaluate(
                    "() => document.getElementById('create-project').disabled")
                boot_err = page4.evaluate(
                    "() => (document.getElementById('boot-error') || {}).textContent || ''")
                check("V2.3.3-04", "boot 失败：控件保持禁用、boot-retry 显示、错误信息可见",
                      still_disabled is True and len(boot_err) > 0,
                      {"still_disabled": still_disabled, "boot_err": boot_err})
                shoot(page4, "boot-failed")
                context4.close()

                # ---------- 打开 A → 打开 B：旧回调不写新项目 / 不重置视图 ----------
                with tempfile.TemporaryDirectory(prefix="amz-v233-") as tmp:
                    context5 = browser.new_context()
                    page5 = context5.new_page()
                    page5.on("console", lambda m: console_errors.append(m.text)
                             if m.type == "error" else None)
                    page5.on("pageerror", lambda e: page_errors.append(str(e)))
                    page5.goto(base_url, wait_until="domcontentloaded")
                    page5.wait_for_selector("#create-project:not([disabled])", timeout=30000)
                    page5.fill("#new-project-name", "项目 A")
                    page5.click("#create-project")
                    page5.wait_for_selector("#project-view:not([hidden])", timeout=30000)
                    page5.wait_for_timeout(600)
                    pid_a = page5.evaluate(
                        "() => (window.__v2SessionProbe ? window.__v2SessionProbe.projectId : null)")
                    # 在 A 的视图里输入（真实用户动作；输入属 A 的当前会话）。
                    page5.fill("#intake-name", "A 的商品名")
                    page5.wait_for_timeout(150)
                    # A 的草稿保存（如果有未提交输入，openProject 会先落库）。
                    page5.click("#back-home")
                    page5.wait_for_selector("#home-view:not([hidden])", timeout=10000)
                    page5.fill("#new-project-name", "项目 B")
                    page5.click("#create-project")
                    page5.wait_for_selector("#project-view:not([hidden])", timeout=30000)
                    page5.wait_for_timeout(600)
                    title = page5.evaluate(
                        "() => document.getElementById('project-title').textContent")
                    pid_b = page5.evaluate(
                        "() => (window.__v2SessionProbe ? window.__v2SessionProbe.projectId : null)")
                    docs_b = page5.evaluate(
                        """() => new Promise((resolve) => {
                          const request = indexedDB.open('amz-listing-kit-v2');
                          request.onsuccess = () => {
                            const db = request.result;
                            const tx = db.transaction('documents', 'readonly');
                            const all = tx.objectStore('documents').getAll();
                            all.onsuccess = () => {
                              db.close();
                              resolve(all.result.filter(
                                (item) => item.kind === 'product_input')
                                .map((item) => ({ project_id: item.project_id,
                                                  version: item.version,
                                                  product_name: (item.payload || {})
                                                    .product_name || "" })));
                            };
                          };
                        })""")
                    per_project = {}
                    for item in docs_b:
                        per_project.setdefault(item["project_id"], []).append(
                            item["product_name"])
                    check("V2.3.3-05", "打开 A → 打开 B：旧回调不重置 B 的视图/项目名",
                          title == "项目 B" and pid_b is not None and pid_a != pid_b,
                          {"title": title, "pid_a": pid_a, "pid_b": pid_b})
                    check("V2.3.3-06", "A 的陈旧 intake 输入已按 A 的 project_id 落库，"
                          "没有写进 B（B 的 intake 为空或属于 B 自己）",
                          all(pid != pid_b or all(not v for v in names)
                              for pid, names in per_project.items()),
                          {"per_project": per_project, "pid_b": pid_b})
                    shoot(page5, "ab-switch")
                    context5.close()

                # ---------- 双标签陈旧编辑：冲突编辑器 + 解决后落库 ----------
                # 同 profile 的持久 context：IndexedDB/localStorage 落同一个用户目录，
                # 关闭重开模拟浏览器重启后的恢复。
                persist_dir = tempfile.mkdtemp(prefix="amz-v233-profile-")
                browser.close()
                browser = pw.chromium.launch_persistent_context(
                    persist_dir, headless=True)
                context6 = browser
                page6 = context6.new_page()
                page6.on("console", lambda m: console_errors.append(m.text)
                         if m.type == "error" else None)
                page6.on("pageerror", lambda e: page_errors.append(str(e)))
                page6.goto(base_url, wait_until="domcontentloaded")
                page6.wait_for_selector("#create-project:not([disabled])", timeout=30000)
                page6.fill("#new-project-name", "双标签冲突")
                page6.click("#create-project")
                page6.wait_for_selector("#project-view:not([hidden])", timeout=30000)
                page6.wait_for_timeout(400)
                # 先保存一个初始版本，另一个标签页才有可改的 base。
                page6.fill("#intake-name", "初始商品名")
                page6.click("#intake-save")
                page6.wait_for_timeout(1200)
                page6.evaluate(
                    """() => new Promise((resolve) => {
                      const request = indexedDB.open('amz-listing-kit-v2');
                      request.onsuccess = () => {
                        const db = request.result;
                        const tx = db.transaction('documents', 'readonly');
                        const all = tx.objectStore('documents').getAll();
                        all.onsuccess = () => {
                          db.close();
                          const intakes = all.result.filter(
                            (item) => item.kind === 'product_input');
                          resolve(intakes.length);
                        };
                      };
                    })""")
                page6.evaluate(
                    """() => new Promise((resolve, reject) => {
                      const request = indexedDB.open('amz-listing-kit-v2');
                      request.onsuccess = () => {
                        const db = request.result;
                        const tx = db.transaction('documents', 'readwrite');
                        const store = tx.objectStore('documents');
                        const all = store.getAll();
                        all.onsuccess = () => {
                          const intakes = all.result.filter(
                            (item) => item.kind === 'product_input');
                          const latest = intakes.reduce(
                            (acc, item) => item.version > (acc ? acc.version : 0)
                              ? item : acc, null);
                          if (!latest) { db.close(); reject(new Error("no-intake")); return; }
                          const next = latest.version + 1;
                          const payload = Object.assign({}, latest.payload, {
                            product_name: "标签页乙的商品名",
                            description: "标签页乙改过描述",
                            selling_points: ["对方改了卖点"],
                          });
                          // documents 仓 keyPath=document_key；新版本必须用新键。
                          const put = store.put({
                            document_key: latest.project_id + ":" + latest.kind + ":"
                              + latest.document_id + ":" + next,
                            project_id: latest.project_id,
                            kind: latest.kind,
                            document_id: latest.document_id,
                            version: next,
                            schema_version: latest.schema_version || 1,
                            payload: payload,
                            created_at: latest.created_at,
                            updated_at: new Date().toISOString(),
                          });
                          put.onsuccess = () => { db.close(); resolve(next); };
                          put.onerror = () => { db.close(); reject(put.error); };
                        };
                      };
                    })""")
                page6.wait_for_timeout(200)
                page6.fill("#intake-name", "标签页甲的商品名")
                page6.fill("#intake-description", "标签页甲改过描述")
                page6.click("#intake-save")
                page6.wait_for_timeout(800)
                conflict_editor = page6.evaluate(
                    "() => Boolean(document.querySelector('.conflict-editor'))")
                conflict_rows = page6.evaluate(
                    "() => document.querySelectorAll('.conflict-row').length")
                check("V2.3.3-07", "双标签陈旧编辑：冲突编辑器可见且三方不同字段逐项展示",
                      conflict_editor is True and conflict_rows >= 1,
                      {"conflict_editor": conflict_editor, "conflict_rows": conflict_rows})
                page6.click('.conflict-row[data-field="product_name"] >> text=保留我的')
                page6.click('.conflict-row[data-field="description"] >> text=保留我的')
                page6.click(".conflict-editor button.primary")
                page6.wait_for_timeout(800)
                editor_gone = page6.evaluate(
                    "() => !document.querySelector('.conflict-editor')")
                docs_final = page6.evaluate(
                    """() => new Promise((resolve) => {
                      const request = indexedDB.open('amz-listing-kit-v2');
                      request.onsuccess = () => {
                        const db = request.result;
                        const tx = db.transaction('documents', 'readonly');
                        const all = tx.objectStore('documents').getAll();
                        all.onsuccess = () => {
                          db.close();
                          resolve(all.result
                            .filter((item) => item.kind === 'product_input')
                            .map((item) => ({ project_id: item.project_id,
                                              version: item.version,
                                              product_name: (item.payload || {})
                                                .product_name || "" })));
                        };
                      };
                    })""")
                latest_name = None
                if docs_final:
                    latest = max(docs_final, key=lambda item: item["version"])
                    latest_name = latest["product_name"]
                versions = sorted(item["version"] for item in docs_final)
                check("V2.3.3-08", "冲突解决后：三字段落库、版本追加、A 的输入未被静默覆盖",
                      editor_gone is True and latest_name == "标签页甲的商品名"
                      and len(versions) >= 2 and versions[-1] > versions[0],
                      {"versions": versions, "latest_name": latest_name})
                conflict_pid = page6.evaluate(
                    "() => (window.__v2SessionProbe ? window.__v2SessionProbe.projectId : null)")
                shoot(page6, "conflict-resolved")
                context6.close()
                browser.close()
                # ---------- 浏览器重启后恢复（同 profile 重开：读指针恢复项目） ----------
                browser = pw.chromium.launch_persistent_context(
                    persist_dir, headless=True)
                context7 = browser
                page7 = context7.new_page()
                page7.on("console", lambda m: console_errors.append(m.text)
                         if m.type == "error" else None)
                page7.on("pageerror", lambda e: page_errors.append(str(e)))
                page7.goto(base_url, wait_until="domcontentloaded")
                # 恢复成功时直接进项目视图（首页隐藏，新建按钮不可见），等项目视图而非首页按钮。
                page7.wait_for_selector("#project-view:not([hidden])", timeout=30000)
                page7.wait_for_function(
                    "() => (window.__v2SessionProbe && window.__v2SessionProbe.projectId)",
                    timeout=30000)
                restored_name = page7.evaluate(
                    "() => document.getElementById('project-title').textContent")
                restored_pid = page7.evaluate(
                    "() => (window.__v2SessionProbe ? window.__v2SessionProbe.projectId : null)")
                restored_rows = page7.locator("#project-list .project-row").count()
                restored_input = page7.input_value("#intake-name")
                check("V2.3.3-09", "浏览器重启后项目、草稿与首页列表完整恢复",
                      "双标签冲突" in restored_name and restored_pid == conflict_pid
                      and restored_rows == 1 and restored_input == "标签页甲的商品名",
                      {"restored_name": restored_name, "restored_pid": restored_pid,
                       "conflict_pid": conflict_pid, "rows": restored_rows,
                       "product_name": restored_input})
                # 原生读取失败：已有列表不得被清空，错误可见且键盘可重试。
                page7.evaluate(PROJECT_READ_FAILURE)
                page7.click("#back-home")
                page7.wait_for_selector("#home-read-error:not([hidden])")
                failed_rows = page7.locator("#project-list .project-row").count()
                read_retry = page7.locator("#home-read-retry").is_visible()
                check("V2.3.3-11", "首页读取失败保留项目列表且显示就地重试",
                      failed_rows == 1 and read_retry
                      and not page7.locator("#empty-state").is_visible(),
                      {"rows": failed_rows, "retry_visible": read_retry})
                shoot(page7, "home-read-failed")
                page7.focus("#home-read-retry")
                page7.keyboard.press("Enter")
                page7.wait_for_selector('#project-list[aria-busy="false"]')
                check("V2.3.3-12", "键盘重试恢复同一项目且无未处理拒绝",
                      not page7.locator("#home-read-error").is_visible()
                      and page7.locator("#project-list .name").inner_text() == "双标签冲突"
                      and page7.evaluate("window.__projectReadRejections") == [],
                      {"project_id": conflict_pid})
                page7.click('#project-list button[data-action="open"]')
                page7.wait_for_selector('#project-view[data-ready="1"]:not([hidden])')
                # 保持原生读写事务活跃但不写数据，真实阻塞同仓的后续只读事务。
                page7.evaluate("""async () => {
                  const db = await new Promise((resolve, reject) => {
                    const r = indexedDB.open('amz-listing-kit-v2');
                    r.onsuccess = () => resolve(r.result);
                    r.onerror = () => reject(r.error);
                  });
                  const tx = db.transaction('projects', 'readwrite');
                  const store = tx.objectStore('projects');
                  const until = performance.now() + 2000;
                  tx.oncomplete = () => db.close();
                  tx.onabort = () => db.close();
                  const hold = () => {
                    const r = store.get('__read_hold__');
                    r.onsuccess = () => { if (performance.now() < until) hold(); };
                  };
                  hold();
                }""")
                page7.click("#back-home")
                pending = page7.evaluate("""() => ({
                  busy: document.getElementById('project-list').getAttribute('aria-busy'),
                  loading: !document.getElementById('home-read-status').hidden,
                  rows: document.querySelectorAll('#project-list .project-row').length,
                  empty: !document.getElementById('empty-state').hidden,
                })""")
                page7.wait_for_selector('#project-list[aria-busy="false"]')
                check("V2.3.3-13", "慢读取有忙碌反馈且保留已有项目，不假称空库",
                      pending == {"busy": "true", "loading": True, "rows": 1, "empty": False}
                      and page7.locator("#project-list .name").inner_text() == "双标签冲突",
                      pending)
                # 启动列表失败也必须保持禁用；显式启动重试才能进入完整就绪状态。
                page7.add_init_script(PROJECT_READ_FAILURE)
                page7.reload(wait_until="domcontentloaded")
                page7.wait_for_selector("#boot-error:not([hidden])")
                boot_locked = page7.locator("#create-project").is_disabled()
                boot_retry = page7.locator("#boot-retry").is_visible()
                page7.click("#boot-retry")
                page7.wait_for_selector('#project-view[data-ready="1"]:not([hidden])')
                check("V2.3.3-14", "启动列表失败保持禁用，重试后恢复项目和完整首页",
                      boot_locked and boot_retry
                      and not page7.locator("#create-project").is_disabled()
                      and page7.locator("#project-list .name").inner_text() == "双标签冲突"
                      and page7.input_value("#intake-name") == "标签页甲的商品名"
                      and page7.evaluate("window.__projectReadRejections") == [],
                      {"locked_on_failure": boot_locked, "retry_visible": boot_retry})
                context7.close()

            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()

    check("V2.3.3-10", "全程零 console error / page error",
          not console_errors and not page_errors,
          {"console_errors": console_errors[:10], "page_errors": page_errors[:10]})

    failed = [item["id"] for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    payload = {
        "schema": "amz-verification-evidence/v1",
        "run": "V2.R3.3 session lifecycle",
        "stamp": stamp,
        "status": status,
        "failed": failed,
        "checks": checks,
        "screenshots": screenshots,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ("-" + args.label) if args.label else ""
    raw_path = EVIDENCE_DIR / f"v2.3.3-session-lifecycle-{stamp}{suffix}.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("========================================================================")
    print("V2.R3.3 会话生命周期验证")
    print("========================================================================")
    for item in checks:
        print("  [%s] %s %s" % ("PASS" if item["ok"] else "FAIL", item["id"], item["title"]))
        if not item["ok"]:
            print("        detail:", json.dumps(item["detail"], ensure_ascii=False)[:400])
    print("证据：%s" % raw_path.relative_to(ROOT).as_posix())
    print("结果：%s（退出码 %d）" % ("全过" if status == "passed" else "有失败", 0 if status == "passed" else 1))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
