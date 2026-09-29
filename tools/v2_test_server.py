#!/usr/bin/env python
"""V2 验证用的最小静态服务器：把产品静态资源和测试装置挂到同一 origin。

只为 tools/verify_v2_*.py 服务，不进产品入口；V2.1.4 会单独验证正式入口。
路径映射：
  /storage/*  → app/product_v2/storage/*
  /harness/*  → evals/product-v2/harness/*
  /           → app/product_v2/*（产品页面）
"""
from __future__ import annotations

import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DIR = ROOT / "app" / "product_v2"
HARNESS_DIR = ROOT / "evals" / "product-v2" / "harness"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
}


class V2StaticHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # 静音
        return

    def _send_file(self, path: Path) -> None:
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802 (http.server 接口名)
        path = self.path.split("?", 1)[0]
        if path.startswith("/harness/"):
            candidate = (HARNESS_DIR / path[len("/harness/"):]).resolve()
            if str(candidate).startswith(str(HARNESS_DIR.resolve())) and candidate.is_file():
                self._send_file(candidate)
                return
        elif path in ("/", "/index.html"):
            self._send_file(PRODUCT_DIR / "index.html")
            return
        else:
            candidate = (PRODUCT_DIR / path.lstrip("/")).resolve()
            if str(candidate).startswith(str(PRODUCT_DIR.resolve())) and candidate.is_file():
                self._send_file(candidate)
                return
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("not found".encode("utf-8"))


def start() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(V2StaticHandler))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
