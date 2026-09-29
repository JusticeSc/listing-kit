"""Product V2 无状态 HTTP 适配器（V2.1.4）。

职责边界：
  - 只服务 ``app/product_v2/`` 下的产品静态资源（页面、脚本、样式）。
  - 不接收、不保存任何用户工作空间路径；没有文件夹工作空间、没有最近项目索引，
    没有任何请求字段会被当作本机目录读取。
  - 用户项目、图片与历史全部由浏览器 IndexedDB 持有；本进程只读自己的安装目录。
  - 测试装置（``evals/...``）不经正式入口对外服务。

证据入口：``python app/server.py --check``（等价于本模块 ``run_self_check()``）。
"""
from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DIR = (ROOT / "app" / "product_v2").resolve()

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}

HEALTH = {
    "app": "amz-listing-kit",
    "product": "v2",
    "server_state": "none",
    "user_data": "browser-indexeddb",
}


class ProductV2Handler(BaseHTTPRequestHandler):
    server_version = "AMZListingKitV2/1"

    def log_message(self, fmt, *args):  # noqa: A003 (http.server 接口名)
        """产品输出保持干净：请求日志不混进终端。"""
        return

    def _send_bytes(self, code: int, payload: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, code: int, body: object) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self._send_bytes(code, payload, "application/json; charset=utf-8")

    def _send_not_found(self, path: str) -> None:
        if path.startswith("/api/"):
            self._send_json(404, {"ok": False, "error": "NOT_FOUND", "path": path})
        else:
            self._send_bytes(404, "not found".encode("utf-8"), "text/plain; charset=utf-8")

    def _resolve_static(self, path: str) -> Path | None:
        """只解析 ``app/product_v2/`` 下的真实文件；目录之外一律不存在。"""
        relative = path.lstrip("/") or "index.html"
        candidate = (PRODUCT_DIR / relative).resolve()
        if candidate == PRODUCT_DIR or PRODUCT_DIR not in candidate.parents:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def do_GET(self):  # noqa: N802 (http.server 接口名)
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        # 查询参数在这里没有语义：不存在 directory / workspace 之类的服务端读取。
        if path == "/api/health":
            self._send_json(200, HEALTH)
            return
        if path.startswith("/api/"):
            self._send_not_found(path)
            return
        if path in {"/", "/index.html", "/product"}:
            path = "/index.html"
        candidate = self._resolve_static(path)
        if candidate is None:
            self._send_not_found(path)
            return
        ctype = MIME.get(candidate.suffix, "application/octet-stream")
        self._send_bytes(200, candidate.read_bytes(), ctype)

    def do_POST(self):  # noqa: N802 (http.server 接口名)
        """当前没有任何服务端写接口；用户状态一律由浏览器持有。"""
        path = urllib.parse.urlsplit(self.path).path
        self._send_not_found(path)


def create_product_v2_server(host: str = "127.0.0.1",
                             port: int = 8780) -> ThreadingHTTPServer:
    """建服务器但不启动；host 由调用方决定（本机默认回环，内网穿透时自行显式放开）。"""
    return ThreadingHTTPServer((host, port), ProductV2Handler)


def run_self_check() -> int:
    """正式入口自检：静态资源可取、测试装置与 V1 工作空间 API 不可达、越权路径被拒。"""
    import http.client

    server = create_product_v2_server("127.0.0.1", 0)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    checks: list[tuple[str, bool, str]] = []

    def request(method: str, path: str) -> tuple[int, str, bytes]:
        connection = http.client.HTTPConnection(host, port, timeout=10)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.getheader("Content-Type") or "", response.read()
        finally:
            connection.close()

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    try:
        status, ctype, body = request("GET", "/")
        text = body.decode("utf-8", "replace")
        check("首页可取且是 V2 产品页", status == 200 and "text/html" in ctype
              and "Amazon US 商品套图" in text and "./app.js" in text,
              f"status={status} type={ctype}")

        for asset, expect in (("/app.js", "javascript"), ("/styles.css", "css"),
                              ("/storage/index.js", "javascript")):
            status, ctype, _ = request("GET", asset)
            check(f"产品资源 {asset}", status == 200 and expect in ctype,
                  f"status={status} type={ctype}")

        status, ctype, body = request("GET", "/api/health")
        health = json.loads(body.decode("utf-8")) if status == 200 else {}
        check("健康检查表明服务器无业务状态", status == 200 and health.get("product") == "v2"
              and health.get("server_state") == "none", f"status={status} body={health}")

        for path in ("/harness/storage-contract.html", "/api/workspaces/recent",
                     "/api/workspace?directory=C%3A%5CUsers", "/evals/probes/project_state.py"):
            status, _, _ = request("GET", path)
            check(f"正式入口不外放：{path}", status == 404, f"status={status}")

        for path in ("/../README.md", "/%2e%2e/README.md", "/storage/../../app/server.py"):
            status, _, _ = request("GET", path)
            check(f"目录逃逸被拒：{path}", status == 404, f"status={status}")

        status, _, _ = request("POST", "/api/anything")
        check("不存在服务端写接口", status == 404, f"status={status}")
    finally:
        server.shutdown()
        server.server_close()

    width = max(len(name) for name, _, _ in checks)
    failed = 0
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
        failed += not ok
    print(f"V2 正式入口自检：{len(checks) - failed}/{len(checks)} 通过。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run_self_check())
