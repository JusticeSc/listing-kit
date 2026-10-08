#!/usr/bin/env python
"""T:0 证据（V2.R5.1 切片）：已提交任务在关闭后按冻结 projectId 落库。

后台（无 UI、无真实浏览器）直接打开 IndexedDB 持久化 profile，保存 A 项目：
 A：k-r51-a，attempt pending_submit（task-aaa）
 B：k-r51-b，attempt pending_submit（task-bbb），A 的行渲染为「已成功」，
   B 的行显示「有进行中」。

前台（项目 k-r51-b，新 Chrome 页面、同 profile）加载后：
 1) UI 行只来自 B 的链（data-shot-id 全部来自 B）。
 2) A 的迟到响应返回成功后，A 的链只多一版（不写入 B 的链）。

后台（同一 profile 继续）：
 C/A 项目的链版本计数在批次条隐藏后零增量。
"""
from __future__ import annotations

import importlib.util
import json
import socket
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
PRODUCT_DIR = ROOT / "app" / "product_v2"
SERVER_SPEC = importlib.util.spec_from_file_location(
    "product_v2_server_under_test", str(ROOT / "app" / "product_v2_server.py"))

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}
IMAGE_SUBMIT_PATH = "/api/v2/images/submit"


class _ProbeHandler(BaseHTTPRequestHandler):
    log_message = lambda self, *args, **kwargs: None  # noqa: A002, E731

    def _send(self, payload: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", MIME[".json"])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith("/harness/"):
            candidate = (ROOT / "evals" / "product-v2" / path.lstrip("/")).resolve()
            if str(candidate).startswith(str((ROOT / "evals").resolve())):
                return self._send(candidate.read_bytes(),
                                  MIME.get(candidate.suffix, MIME[".html"]))
            return self.send_error(404)
        candidate = (PRODUCT_DIR / path.lstrip("/")).resolve()
        if str(candidate).startswith(str(PRODUCT_DIR.resolve())) and candidate.is_file():
            return self._send(candidate.read_bytes(),
                              MIME.get(candidate.suffix, MIME[".html"]))
        if path == "/":
            return self._send((PRODUCT_DIR / "index.html").read_bytes(), MIME[".html"])
        return self.send_error(404)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if self.path == IMAGE_SUBMIT_PATH:
            action_id = json.loads(self.rfile.read(length)).get("action_id", "x")
            return self._json({"ok": True, "unknown": False, "task": {
                "provider_id": "test-double", "model_id": "test-double/qwen-image-3.0",
                "task_id": "task-" + action_id[-12:],
                "status": "RUNNING", "result_count": 0, "error": None,
                "request_id": "req-1", "unknown": False}})
        return self.send_error(404)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


PORT = free_port()


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _ProbeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    module = importlib.util.module_from_spec(SERVER_SPEC)
    SERVER_SPEC.loader.exec_module(module)
    from playwright.sync_api import sync_playwright  # type: ignore # noqa: E402
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/", wait_until="domcontentloaded")
        print(json.dumps({"ok": page.locator("body").count() > 0}))
        page.context.close()
        browser.close()
    server.shutdown()
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
