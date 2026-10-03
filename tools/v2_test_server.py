#!/usr/bin/env python
"""V2 验证用的最小服务器：把产品静态资源、无状态 API 和测试装置挂到同一 origin。

只为 tools/verify_v2_*.py 的契约套件服务，不进产品入口。
正式入口（V2.1.4 起）是 `python app/server.py`：app/product_v2_server.py 只挂产品静态资源与两个
无状态 API，不挂本文件的 /harness/ 映射；正式入口的证据见 tools/verify_v2_1_4_formal_entry.py。

路由复用正式入口的 ProductV2Handler（含 /api/health、/api/v2/capabilities、
/api/v2/semantic/analyze、图像网关与复核网关），只额外挂一个 /harness/ 映射，并把语义/
图像/单图复核/整套复核四个 provider 全部固定为测试替身（fake-semantic / fake-qwen-image /
fake-review / fake-suite-review），使契约套件在无密钥、无网络、有真实凭据残留的环境变量下
也不会触达真实供应商，同时仍走同一条产品代码路径。

路径映射：
  /harness/*  → evals/product-v2/harness/*
  /           → app/product_v2/*（产品页面与两个无状态 API）
"""
from __future__ import annotations

import sys
import threading
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.product_v2_server import ProductV2Handler  # noqa: E402
from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402
from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider  # noqa: E402

HARNESS_DIR = (ROOT / "evals" / "product-v2" / "harness").resolve()


class V2StaticHandler(ProductV2Handler):
    """正式入口处理器 + /harness/ 映射；其余行为（含两个 API 与失败语义）与产品一致。

    会话生命周期验证（tools/verify_v2_3_3_session_lifecycle.py）需要"可控延迟"：
    `/?__test_delay=<ms>` 只对 /storage/index.js 与 /workspace.js 的静态响应整体
    推迟 <ms> 后再发送——HTML/脚本内容一字节不变，只让"模块从发出请求到可用"
    这段时间被拉长，用来复现旧 ready 窗口。仅本测试服务器认识该参数；正式入口
    （app/server.py）不认识，生产行为零变化。
    """

    def _delay_ms(self) -> int:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        raw = query.get("__test_delay", ["0"])[0]
        try:
            return max(0, min(int(raw), 10_000))
        except ValueError:
            return 0

    def do_GET(self):  # noqa: N802 (http.server 接口名)
        parsed_path = urllib.parse.urlsplit(self.path).path
        delay_ms = self._delay_ms()
        if delay_ms > 0 and parsed_path in ("/storage/index.js", "/workspace.js"):
            import time as _time
            _time.sleep(delay_ms / 1000.0)
        super().do_GET()

    def _resolve_static(self, path: str) -> Path | None:
        if path.startswith("/harness/"):
            candidate = (HARNESS_DIR / path[len("/harness/"):]).resolve()
            if candidate.is_file() and HARNESS_DIR in candidate.parents:
                return candidate
            return None
        return super()._resolve_static(path)


def start() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), V2StaticHandler)
    # 四类全部显式 fake：只注语义 fake 时，image/review/suite-review 会回落注册表默认
    #（dashscope-*；本机实测有 DASHSCOPE_API_KEY 残留时 capabilities 直接报 configured=true，
    # 见 R1.2 证据）。离线审计必须不依赖默认回落。
    server.provider_factory = lambda: FakeSemanticProvider(scenario="ok")
    server.image_provider_factory = lambda: FakeImageProvider(scenario="ok")
    server.review_provider_factory = lambda: FakeReviewProvider(scenario="ok")
    server.suite_review_provider_factory = lambda: FakeSuiteReviewProvider(scenario="ok")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
