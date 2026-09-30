#!/usr/bin/env python
"""V2.UI.1 证据：正式远程入口、Chrome/Edge 能力与精确失败诊断。

检查：
  1) 本机 localhost（安全来源例外）：无工程诊断；新建项目后刷新仍在 IndexedDB。
  2) 远程 HTTPS + Chrome：安全上下文、WebCrypto、IndexedDB 齐备；
     空白新建 → 刷新 → 关页重开仍在（同一浏览器配置文件）。
  3) 远程 HTTPS + Edge：同样的后置条件，独立浏览器路径。
  4) 远程 HTTP 负例：必须精确报 secure_context/WebCrypto 缺口
     （SECURE_CONTEXT_REQUIRED，gap=secure_context），IndexedDB 仍可用，
     新建/导入被禁用，且不得出现旧归因“不支持本地项目存储（IndexedDB）”。
  5) 全程零 console error / page error；关键状态截图留证。

说明：本验证器需要真实远程入口与 Chrome/Edge，因此不进 CI，按需在部署后运行。

运行：
  uv run --locked python tools/verify_v2_ui_1_remote_entry.py
可选参数：
  --https https://47.115.172.233:8080   --http http://47.115.172.233:8780
  --skip-local   --label <tag>
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from v2_test_server import start as start_server  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGES = EVIDENCE_DIR / "evidence"
DEFAULT_HTTPS = "https://47.115.172.233:8080"
DEFAULT_HTTP = "http://47.115.172.233:8780"
OLD_WRONG_CLAIM = "不支持本地项目存储"

HOME_STATE_JS = """
() => {
  const notice = document.getElementById('capability-notice');
  const create = document.getElementById('create-project');
  const importTrigger = document.getElementById('import-trigger');
  const bootError = document.getElementById('boot-error');
  const homeError = document.getElementById('home-error');
  return {
    secure_context: window.isSecureContext === true,
    subtle: typeof crypto.subtle,
    subtle_digest: typeof (crypto.subtle && crypto.subtle.digest),
    random_uuid: typeof crypto.randomUUID,
    indexeddb: typeof indexedDB,
    notice_present: Boolean(notice),
    notice_hidden: notice ? notice.hidden : null,
    notice_code: notice && notice.dataset ? (notice.dataset.errorCode || null) : null,
    notice_gap: notice && notice.dataset ? (notice.dataset.errorGap || null) : null,
    notice_text: notice ? (notice.innerText || '').replace(/\\s+/g, ' ').trim() : '',
    create_disabled: create ? create.disabled : null,
    import_disabled: importTrigger ? importTrigger.disabled : null,
    boot_error_hidden: bootError ? bootError.hidden : null,
    home_error_hidden: homeError ? homeError.hidden : null,
    project_names: Array.from(document.querySelectorAll('#project-list [data-role=name]'))
      .map((node) => node.textContent),
  };
}
"""

INDEXEDDB_JS = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes('amz-listing-kit-v2')) {
    return { db_exists: false, project_count: 0 };
  }
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('amz-listing-kit-v2');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const projects = await new Promise((resolve, reject) => {
    const request = db.transaction('projects', 'readonly').objectStore('projects').getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  return { db_exists: true, project_count: projects.length,
           project_names: projects.map((item) => item.name) };
}
"""

EDGE_GLOBS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\*\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\*\msedge.exe",
)


def newest_edge_binary() -> str | None:
    """部分宿主的 Edge 根目录启动器会立即退出；版本目录里的 msedge.exe 才是真浏览器。"""
    candidates: list[str] = []
    for pattern in EDGE_GLOBS:
        candidates.extend(glob.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def launch(playwright, engine: str):
    if engine == "chrome":
        return playwright.chromium.launch(channel="chrome", headless=True)
    binary = newest_edge_binary()
    if binary:
        return playwright.chromium.launch(executable_path=binary, headless=True)
    return playwright.chromium.launch(channel="msedge", headless=True)


def git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.UI.1 远程入口与能力诊断验证")
    parser.add_argument("--https", default=DEFAULT_HTTPS)
    parser.add_argument("--http", default=DEFAULT_HTTP)
    parser.add_argument("--skip-local", action="store_true")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    screenshots: list[str] = []
    meta: dict = {
        "stamp": stamp,
        "https": args.https,
        "http": args.http,
        "git_head": git_head(),
        "edge_binary": newest_edge_binary(),
    }

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    def shot(page, name: str) -> None:
        EVIDENCE_IMAGES.mkdir(parents=True, exist_ok=True)
        path = EVIDENCE_IMAGES / ("v2.ui.1-remote-entry-" + stamp + "-" + name + ".png")
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(path.relative_to(ROOT).as_posix())

    def attach_errors(page, bucket: list[str]) -> None:
        page.on("console", lambda message: bucket.append("console:" + message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: bucket.append("pageerror:" + str(error)))

    def create_project(page, name: str) -> bool:
        page.fill("#new-project-name", name)
        page.click("#create-project")
        page.wait_for_selector("#project-list .project-row", timeout=20000)
        state = page.evaluate(HOME_STATE_JS)
        return name in (state.get("project_names") or [])

    print("=" * 72)
    print("V2.UI.1 正式远程入口、浏览器能力与错误诊断")
    print("=" * 72)

    server = None
    local_base = None
    try:
        if not args.skip_local:
            server, local_base = start_server()
            meta["local_base"] = local_base

        with sync_playwright() as pw:
            # 1) 本机 localhost：安全来源例外，不得出现工程诊断
            if local_base:
                errors: list[str] = []
                browser = launch(pw, "chrome")
                context = browser.new_context()
                page = context.new_page()
                attach_errors(page, errors)
                page.goto(local_base + "/", wait_until="load", timeout=30000)
                page.wait_for_timeout(800)
                state = page.evaluate(HOME_STATE_JS)
                ok_state = (state["secure_context"] and state["subtle_digest"] == "function"
                            and state["random_uuid"] == "function" and state["indexeddb"] == "object"
                            and state["notice_hidden"] and state["boot_error_hidden"])
                check("V2.UI.1-00", "localhost 是安全来源且不显示工程诊断", ok_state, state)
                name = "UI1 本机 " + stamp
                created = create_project(page, name)
                page.reload(wait_until="load")
                page.wait_for_timeout(600)
                after = page.evaluate(HOME_STATE_JS)
                check("V2.UI.1-01", "localhost 新建项目后刷新仍在（IndexedDB 后置条件）",
                      created and name in (after.get("project_names") or []),
                      {"created": created, "after": after.get("project_names")})
                shot(page, "localhost")
                check("V2.UI.1-02", "localhost 会话零 console/page error", not errors, errors)
                browser.close()

            # 2)+3) 远程 HTTPS：Chrome 与 Edge 各走一遍
            for engine, check_offset in (("chrome", 10), ("edge", 20)):
                errors = []
                browser = launch(pw, engine)
                version = browser.version
                context = browser.new_context()
                page = context.new_page()
                attach_errors(page, errors)
                page.goto(args.https + "/", wait_until="load", timeout=45000)
                page.wait_for_timeout(900)
                state = page.evaluate(HOME_STATE_JS)
                ok_state = (state["secure_context"] and state["subtle_digest"] == "function"
                            and state["random_uuid"] == "function" and state["indexeddb"] == "object"
                            and state["notice_hidden"] and state["boot_error_hidden"])
                check("V2.UI.1-{:02d}".format(check_offset),
                      "远程 HTTPS + " + engine + " 是安全上下文且能力齐备",
                      ok_state, {"version": version, "state": state})
                name = "UI1 远程 " + engine + " " + stamp
                created = create_project(page, name)
                page.reload(wait_until="load")
                page.wait_for_timeout(600)
                after_reload = page.evaluate(HOME_STATE_JS)
                page.close()
                page = context.new_page()
                attach_errors(page, errors)
                page.goto(args.https + "/", wait_until="load", timeout=45000)
                page.wait_for_timeout(900)
                after_reopen = page.evaluate(HOME_STATE_JS)
                db_state = page.evaluate(INDEXEDDB_JS)
                check("V2.UI.1-{:02d}".format(check_offset + 1),
                      "远程 HTTPS + " + engine + " 新建后刷新与关页重开仍在",
                      created and name in (after_reload.get("project_names") or [])
                      and name in (after_reopen.get("project_names") or [])
                      and db_state.get("db_exists") is True,
                      {"created": created,
                       "after_reload": after_reload.get("project_names"),
                       "after_reopen": after_reopen.get("project_names"),
                       "indexeddb": db_state})
                shot(page, engine)
                check("V2.UI.1-{:02d}".format(check_offset + 2),
                      "远程 HTTPS + " + engine + " 会话零 console/page error",
                      not errors, errors)
                browser.close()

            # 4) 远程 HTTP 负例：必须精确报 secure_context/WebCrypto，而不是 IndexedDB
            errors = []
            browser = launch(pw, "chrome")
            context = browser.new_context()
            page = context.new_page()
            attach_errors(page, errors)
            page.goto(args.http + "/", wait_until="load", timeout=45000)
            page.wait_for_timeout(1200)
            negative = page.evaluate(HOME_STATE_JS)
            text = negative.get("notice_text") or ""
            ok_negative = (
                negative["secure_context"] is False
                and negative["indexeddb"] == "object"
                and negative["notice_hidden"] is False
                and negative["notice_gap"] == "secure_context"
                and negative["notice_code"] == "SECURE_CONTEXT_REQUIRED"
                and "HTTPS" in text and "WebCrypto" in text
                and OLD_WRONG_CLAIM not in text
                and negative["create_disabled"] is True
                and negative["import_disabled"] is True
                and negative["boot_error_hidden"] is True
            )
            check("V2.UI.1-30", "远程 HTTP 负例精确报 secure_context/WebCrypto 缺口",
                  ok_negative, negative)
            shot(page, "http-negative")
            check("V2.UI.1-31", "远程 HTTP 负例会话零 console/page error", not errors, errors)
            browser.close()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()

    passed = sum(1 for item in checks if item["ok"])
    failed = len(checks) - passed
    label = ("-" + args.label) if args.label else ""
    text_path = EVIDENCE_DIR / ("v2.ui.1-remote-entry-" + stamp + label + "-final.txt")
    json_path = EVIDENCE_DIR / ("v2.ui.1-remote-entry-" + stamp + label + "-final.json")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "V2.UI.1 正式远程入口、浏览器能力与错误诊断",
        "时间：" + datetime.now().isoformat(timespec="seconds"),
        "git HEAD：" + meta["git_head"],
        "远程 HTTPS：" + args.https,
        "远程 HTTP：" + args.http,
        "Edge 可执行文件：" + str(meta["edge_binary"]),
        "",
    ]
    for item in checks:
        lines.append("[{}] {} {}".format(
            "PASS" if item["ok"] else "FAIL", item["id"], item["title"]))
        if item["detail"] is not None:
            lines.append("       " + json.dumps(item["detail"], ensure_ascii=False))
    lines.append("")
    lines.append("截图：" + (", ".join(screenshots) if screenshots else "（无）"))
    lines.append("结果：{}/{} 通过，{} 失败。".format(passed, len(checks), failed))
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(
        {"meta": meta, "checks": checks, "screenshots": screenshots,
         "passed": passed, "failed": failed}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    for item in checks:
        print("  [{}] {} {}".format("PASS" if item["ok"] else "FAIL", item["id"], item["title"]))
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False))
    print("证据：" + text_path.relative_to(ROOT).as_posix())
    print("证据：" + json_path.relative_to(ROOT).as_posix())
    print("截图：" + str(len(screenshots)) + " 张")
    print("结果：{}/{} 通过，{} 失败。".format(passed, len(checks), failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
