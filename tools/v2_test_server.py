#!/usr/bin/env python
"""V2 验证用的最小服务器：把产品静态资源、无状态 API 和测试装置挂到同一 origin。

只为 tools/verify_v2_*.py 的契约套件服务，不进产品入口。
正式入口（V2.1.4 起）是 `python app/server.py`：app/product_v2_server.py 只挂产品静态资源与两个
无状态 API，不挂本文件的 /harness/ 映射；正式入口的证据见 tools/verify_v2_1_4_formal_entry.py。

路由复用正式入口的 ProductV2Handler（含 /api/health、/api/v2/capabilities、
/api/v2/semantic/analyze），只额外挂一个 /harness/ 映射，并把语义 provider 固定为
测试替身 fake-semantic，使契约套件在无密钥、无网络时也能走同一条产品代码路径。

路径映射：
  /harness/*  → evals/product-v2/harness/*
  /           → app/product_v2/*（产品页面与两个无状态 API）
"""
from __future__ import annotations

import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.product_v2_server import ProductV2Handler  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402

HARNESS_DIR = (ROOT / "evals" / "product-v2" / "harness").resolve()


class V2StaticHandler(ProductV2Handler):
    """正式入口处理器 + /harness/ 映射；其余行为（含两个 API 与失败语义）与产品一致。"""

    def _resolve_static(self, path: str) -> Path | None:
        if path.startswith("/harness/"):
            candidate = (HARNESS_DIR / path[len("/harness/"):]).resolve()
            if candidate.is_file() and HARNESS_DIR in candidate.parents:
                return candidate
            return None
        return super()._resolve_static(path)


def start() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), V2StaticHandler)
    server.provider_factory = lambda: FakeSemanticProvider(scenario="ok")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
