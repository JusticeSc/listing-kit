#!/usr/bin/env python
"""V2.1.1 证据：浏览器 IndexedDB 存储层契约（真实 Chromium，非 Mock）。

检查内容：
  1) 静态：storage 模块全部通过 node --check（ESM 语法门）。
  2) 契约套件：在真实 Chromium 里跑 evals/product-v2/harness/storage-contract.html，
     覆盖 schema / 项目 / 文档版本 / 资产 Blob / 事务 / 指针 / 迁移，含反向探针。
  3) 上下文隔离：两个独立浏览器上下文各有一份项目列表，互不可见。
  4) 浏览器重启恢复：持久化用户目录关闭再打开后项目与当前指针仍在。
  5) 默认库：正式库名与 schema 版本来自代码，不是测试里手抄的常量。

运行（每次跑完把 JSON/TXT 写出到 evals/product-v2/）：
  & "C:\\Users\\31368\\.local\\bin\\uv.exe" run --no-project --with-requirements requirements.txt --with playwright python tools/verify_v2_1_1_indexeddb.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = ROOT / "app" / "product_v2" / "storage"
HARNESS_DIR = ROOT / "evals" / "product-v2" / "harness"
EVIDENCE_DIR = ROOT / "evals" / "product-v2"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}

# 套件必须逐项存在；少一个用例也要变红，防止"悄悄删测试"。
EXPECTED_CASE_IDS = [
    "S01", "S02",
    "P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08",
    "P09",
    "D01", "D02", "D03", "D04", "D05",
    "A01", "A02", "A03",
    "T01", "T02",
    "L01", "L02", "L03", "L04", "L05",
    "M01", "M02", "M03",
]


class StaticHandler(BaseHTTPRequestHandler):
    """只服务测试需要的两类路径：/storage/* 与 /harness/*。"""

    roots = {
        "/storage/": STORAGE_DIR,
        "/harness/": HARNESS_DIR,
    }

    def log_message(self, *_args):  # 关掉 stderr 噪音
        return

    def do_GET(self):  # noqa: N802 (http.server 接口名)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/harness/storage-contract.html")
            self.end_headers()
            return
        for prefix, root in self.roots.items():
            if path.startswith(prefix):
                relative = path[len(prefix):]
                candidate = (root / relative).resolve()
                if not str(candidate).startswith(str(root.resolve())) or not candidate.is_file():
                    break
                payload = candidate.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", MIME.get(candidate.suffix, "application/octet-stream"))
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("not found".encode("utf-8"))


def start_static_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(StaticHandler))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def run_node_check() -> dict:
    files = sorted(STORAGE_DIR.glob("*.js"))
    results = []
    for path in files:
        passed = subprocess.run(
            ["node", "--check", str(path)], cwd=ROOT, capture_output=True, text=True)
        results.append({
            "file": str(path.relative_to(ROOT)).replace("\\", "/"),
            "rc": passed.returncode,
            "stderr": passed.stderr.strip(),
        })
    return {
        "files": results,
        "ok": all(item["rc"] == 0 for item in results) and bool(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.1.1 IndexedDB 契约验证")
    parser.add_argument("--label", default="", help="附加到证据文件名的标签")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright  # noqa: PLC0415 (可选依赖，运行时才需要)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    suite_cases: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    node_result = run_node_check()
    check("V2.1.1-00", "storage 模块通过 node --check（ESM 语法门）", node_result["ok"], node_result)

    server, base_url = start_static_server()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                # --- 1) 契约套件 ---
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(base_url + "/harness/storage-contract.html", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.__V2_STORAGE_RESULTS__ && "
                    "['passed','failed','crashed'].includes(window.__V2_STORAGE_RESULTS__.status)",
                    timeout=120_000,
                )
                suite = page.evaluate("() => window.__V2_STORAGE_RESULTS__")
                suite_cases = suite.get("cases", [])
                case_ids = [item.get("id") for item in suite_cases]
                missing = [item for item in EXPECTED_CASE_IDS if item not in case_ids]
                check(
                    "V2.1.1-01",
                    "契约套件全部通过且用例清单完整",
                    suite.get("status") == "passed" and not missing,
                    {"status": suite.get("status"), "cases": len(suite_cases),
                     "failed": suite.get("failed_ids"), "missing": missing},
                )
                check(
                    "V2.1.1-02",
                    "运行期无 console error / page error",
                    not console_errors and not page_errors,
                    {"console_errors": console_errors, "page_errors": page_errors},
                )

                # --- 2) 默认库身份 ---
                identity = page.evaluate(
                    "async () => {"
                    "  const mod = await import('/storage/index.js');"
                    "  const opened = await mod.openStorage({});"
                    "  const info = { db_name: mod.DB_NAME, version: opened.db.version,"
                    "                 expected_version: mod.STORAGE_SCHEMA_VERSION,"
                    "                 stores: Array.from(opened.db.objectStoreNames).sort() };"
                    "  opened.close();"
                    "  return info;"
                    "}"
                )
                check(
                    "V2.1.1-03",
                    "默认库名与版本取自代码，结构为 projects/assets/documents",
                    identity["version"] == identity["expected_version"]
                    and identity["db_name"] == "amz-listing-kit-v2"
                    and identity["stores"] == ["assets", "documents", "projects"],
                    identity,
                )
                context.close()

                # --- 3) 两个浏览器上下文自然分离 ---
                context_a = browser.new_context()
                context_b = browser.new_context()
                page_a = context_a.new_page()
                page_b = context_b.new_page()
                quiet = "/harness/storage-contract.html?suite=0"
                page_a.goto(base_url + quiet, wait_until="domcontentloaded")
                page_b.goto(base_url + quiet, wait_until="domcontentloaded")
                created = page_a.evaluate(
                    "async () => { const h = window.v2Harness;"
                    "  await h.open({ name: 'amz-listing-kit-v2' });"
                    "  const project = await h.createProject('amz-listing-kit-v2', '隔离验证 A');"
                    "  await h.setCurrentProject('amz-listing-kit-v2', project.project_id);"
                    "  const list = await h.listProjects('amz-listing-kit-v2');"
                    "  return { project_id: project.project_id, count: list.length,"
                    "           keys: h.pointerKeys() }; }"
                )
                isolated = page_b.evaluate(
                    "async () => { const h = window.v2Harness;"
                    "  await h.open({ name: 'amz-listing-kit-v2' });"
                    "  const list = await h.listProjects('amz-listing-kit-v2');"
                    "  const current = await h.getCurrentProject('amz-listing-kit-v2');"
                    "  return { count: list.length, current, keys: h.pointerKeys() }; }"
                )
                check(
                    "V2.1.1-04",
                    "两个独立浏览器配置文件的项目列表互不可见",
                    created["count"] == 1 and created["keys"] and isolated["count"] == 0
                    and isolated["current"] is None and not isolated["keys"],
                    {"context_a": created, "context_b": isolated},
                )
                context_a.close()
                context_b.close()
            finally:
                browser.close()

            # --- 4) 浏览器重启恢复（持久化用户目录） ---
            with tempfile.TemporaryDirectory(prefix="amz-v2-persist-") as raw_dir:
                profile = Path(raw_dir) / "profile"
                first_context = pw.chromium.launch_persistent_context(str(profile), headless=True)
                try:
                    page = first_context.new_page()
                    page.goto(base_url + "/harness/storage-contract.html?suite=0",
                              wait_until="domcontentloaded")
                    first = page.evaluate(
                        "async () => { const h = window.v2Harness;"
                        "  await h.open({ name: 'amz-listing-kit-v2' });"
                        "  const project = await h.createProject('amz-listing-kit-v2', '重启恢复验证');"
                        "  await h.setCurrentProject('amz-listing-kit-v2', project.project_id);"
                        "  return { project_id: project.project_id }; }"
                    )
                finally:
                    first_context.close()
                time.sleep(1.0)
                second_context = pw.chromium.launch_persistent_context(str(profile), headless=True)
                try:
                    page = second_context.new_page()
                    page.goto(base_url + "/harness/storage-contract.html?suite=0",
                              wait_until="domcontentloaded")
                    second = page.evaluate(
                        "async () => { const h = window.v2Harness;"
                        "  await h.open({ name: 'amz-listing-kit-v2' });"
                        "  const list = await h.listProjects('amz-listing-kit-v2');"
                        "  const current = await h.getCurrentProject('amz-listing-kit-v2');"
                        "  return { names: list.map((item) => item.name),"
                        "           current_id: current ? current.project_id : null }; }"
                    )
                finally:
                    second_context.close()
                check(
                    "V2.1.1-05",
                    "浏览器关闭重开后项目与当前指针仍在（IndexedDB 持久化）",
                    second["names"] == ["重启恢复验证"]
                    and second["current_id"] == first["project_id"],
                    {"first": first, "second": second},
                )
    finally:
        server.shutdown()
        server.server_close()

    failed = [item["id"] for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    report = {
        "task": "V2.1.1",
        "suite": "v2.1.1-indexeddb-contract",
        "status": status,
        "finished_at": finished_at,
        "checks": checks,
        "suite_cases": suite_cases,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "expected_case_ids": EXPECTED_CASE_IDS,
        "boundary": (
            "证明浏览器存储层：schema/迁移/事务/版本化 JSON/内容寻址 Blob/轻量指针/"
            "上下文隔离/重启恢复。不证明项目首页、导入导出、无状态服务、模型调用或首次使用者闭环。"
        ),
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.1.1-indexeddb-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.1.1-indexeddb-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.1.1 IndexedDB storage contract",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        mark = "PASS" if item["ok"] else "FAIL"
        lines.append(f"- [{mark}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False))
    lines += [
        "",
        "SUITE CASES",
    ]
    for item in suite_cases:
        mark = "PASS" if item.get("ok") else "FAIL"
        lines.append(f"- [{mark}] {item.get('id')} {item.get('title')}")
        if not item.get("ok"):
            lines.append("  error: " + json.dumps(item.get("error"), ensure_ascii=False))
    lines += [
        "",
        "BOUNDARY",
        report["boundary"],
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.1.1 IndexedDB 存储契约验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
    for item in suite_cases:
        if not item.get("ok"):
            print(f"  ✗ 用例 {item.get('id')}: {json.dumps(item.get('error'), ensure_ascii=False)}")
    print(f"套件用例：{len(suite_cases)} 条，失败 {sum(1 for item in suite_cases if not item.get('ok'))} 条")
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
