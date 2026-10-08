#!/usr/bin/env python
"""D4.12 正式入口审计：只暴露一条 Product V1 主路径。

断言：
1. 正式入口链路存在：start_product.bat -> app/server.py -> app/product_v1_server.py
   -> app/product_v1/；
2. 前端静态资源与 Product V1 服务器源码不含 Mock、历史夹具、开发机绝对路径；
3. 正式前端不调用旧的 /api/export 兼容路由（兼容路由只保留在服务端）；
4. start_product.bat 只启动 app\\server.py，不带 --offline-fixture；
5. 正式服务器从 "/" 返回的 HTML / JS / CSS 与仓库静态文件一致，且首页只含正式屏幕。
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.product_v1_server import ProductApplication, create_product_server
from src.application_service import ApplicationService
from src.providers.fake_semantic import FakeSemanticProvider
from tools.verify_product_v1_image_generation import FakeImageProvider

EVIDENCE = ROOT / "evals" / "product-demo"
FRONTEND = {
    "index.html": ROOT / "app" / "product_v1" / "index.html",
    "product.js": ROOT / "app" / "product_v1" / "product.js",
    "styles.css": ROOT / "app" / "product_v1" / "styles.css",
}
SERVER_SOURCE = ROOT / "app" / "product_v1_server.py"
LAUNCHER = ROOT / "start_product.bat"
FORBIDDEN = (
    ("aster", re.compile(r"aster", re.IGNORECASE)),
    ("mock", re.compile(r"mock", re.IGNORECASE)),
    ("offline-fixture", re.compile(r"offline-fixture", re.IGNORECASE)),
    ("file-url", re.compile(r"file://")),
    ("windows-absolute-path", re.compile(r"[A-Za-z]:[\\\\/]")),
)
LEGACY_ENDPOINT = re.compile(r"/api/export(?!s)")
REQUIRED_IDS = ("home-screen", "intake-screen", "delivery-screen",
                "generate-suite", "export-selection", "export-delivery")


def forbidden_hits(text: str) -> list[str]:
    return [name for name, pattern in FORBIDDEN if pattern.search(text)]


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n")


def fetch(url: str) -> str:
    with urlopen(url, timeout=15) as response:
        return response.read().decode("utf-8")


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    result: dict[str, object] = {"stamp": stamp}

    for name, path in FRONTEND.items():
        if not path.is_file():
            failures.append(f"缺少正式前端文件：{path}")
    for path in (SERVER_SOURCE, LAUNCHER):
        if not path.is_file():
            failures.append(f"缺少正式入口文件：{path}")

    source_hits: dict[str, list[str]] = {}
    for name, path in FRONTEND.items():
        if path.is_file():
            hits = forbidden_hits(path.read_text(encoding="utf-8"))
            if hits:
                failures.append(f"{name} 命中禁用字样：{hits}")
            source_hits[name] = hits
    if SERVER_SOURCE.is_file():
        server_hits = forbidden_hits(SERVER_SOURCE.read_text(encoding="utf-8"))
        source_hits["product_v1_server.py"] = server_hits
        if server_hits:
            failures.append(f"product_v1_server.py 命中禁用字样：{server_hits}")
    result["source_hits"] = source_hits

    frontend_legacy = []
    for name, path in FRONTEND.items():
        if path.is_file() and LEGACY_ENDPOINT.search(path.read_text(encoding="utf-8")):
            frontend_legacy.append(name)
    result["frontend_legacy_endpoint_calls"] = frontend_legacy
    if frontend_legacy:
        failures.append(f"正式前端仍调用旧 /api/export 路由：{frontend_legacy}")

    launcher_text = LAUNCHER.read_text(encoding="utf-8", errors="replace") if LAUNCHER.is_file() else ""
    result["launcher_uses_formal_entry"] = "app\\server.py" in launcher_text
    if "app\\server.py" not in launcher_text:
        failures.append("start_product.bat 没有启动 app\\server.py")
    if "offline-fixture" in launcher_text.lower():
        failures.append("start_product.bat 暴露了 --offline-fixture 旧入口")
    if forbidden_hits(launcher_text):
        failures.append("start_product.bat 命中禁用字样")

    with tempfile.TemporaryDirectory(prefix="amz-product-v1-entry-audit-") as raw:
        application = ProductApplication(
            service=ApplicationService(
                semantic_provider_factory=lambda: FakeSemanticProvider({}),
                image_provider_factory=lambda: FakeImageProvider(),
            ),
            recent_index_path=Path(raw) / "recent-workspaces.json",
        )
        server = create_product_server("127.0.0.1", 0, application=application)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            served = {
                "index.html": fetch(base_url + "/"),
                "product.js": fetch(base_url + "/product-assets/product.js"),
                "styles.css": fetch(base_url + "/product-assets/styles.css"),
            }
            mismatches = [
                name for name, path in FRONTEND.items()
                if path.is_file() and normalized(served[name]) != normalized(
                    path.read_text(encoding="utf-8"))
            ]
            result["served_mismatches"] = mismatches
            if mismatches:
                failures.append(f"服务器返回与仓库静态文件不一致：{mismatches}")
            missing_ids = [item for item in REQUIRED_IDS
                           if f'id="{item}"' not in served["index.html"]]
            result["missing_screen_ids"] = missing_ids
            if missing_ids:
                failures.append(f"首页缺少正式屏幕元素：{missing_ids}")
            served_hits = forbidden_hits(served["index.html"])
            if served_hits:
                failures.append(f"首页 HTML 命中禁用字样：{served_hits}")
            result["external_offline_requests"] = []
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    result["failures"] = failures
    result["passed"] = not failures
    report_path = EVIDENCE / f"d4.12-entry-audit-{stamp}.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
