#!/usr/bin/env python
"""V2 验证用 ASGI 装置：产品 app + 同 origin 的 /harness/ 映射。

只为 tools/verify_v2_*.py 的契约套件服务，不进产品入口。正式入口（V2.1.4 起）是
`python app/server.py`：它只挂产品静态产物与无状态 API，不挂本文件的 /harness/ 映射。

路由复用产品 app 工厂（`app.product_v2_server.create_app`），因此走的是同一条产品代码路径；
本文件只额外做两件测试装置的事：
  1) 把 `evals/product-v2/harness/` 挂到 `/harness/`；
  2) 提供 `?__test_delay=<ms>` 的可控延迟（会话生命周期验证用），HTML/脚本字节不变。

四类 provider 全部显式固定为测试替身（fake-semantic / fake-qwen-image / fake-review /
fake-suite-review），使契约套件在无密钥、无网络、有真实凭据残留的环境变量下也不会触达
真实供应商。
"""
from __future__ import annotations

import asyncio
import sys
import urllib.parse
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, PlainTextResponse, RedirectResponse, Response  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

from app.product_v2_http import (  # noqa: E402
    STATIC_HEADERS,
    ProductV2Server,
    resolve_static_root,
    static_file_response,
)
from app.product_v2_server import create_app  # noqa: E402
from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402
from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider  # noqa: E402

HARNESS_DIR = (ROOT / "evals" / "product-v2" / "harness").resolve()
# 会话生命周期验证只需要把“模块从发出请求到可用”的窗口拉长，不改变任何字节。
DELAY_PATHS = frozenset({"/storage/index.js", "/workspace.js"})


class TestDelayMiddleware:
    """`?__test_delay=<ms>` 延迟指定静态响应；仅测试装置认识该参数。"""

    def __init__(self, app: Callable[..., Awaitable[Any]],
                 paths: frozenset[str] = DELAY_PATHS) -> None:
        self.app = app
        self.paths = paths

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") == "http" and scope.get("path") in self.paths:
            query = urllib.parse.parse_qs(scope.get("query_string", b"").decode("latin-1"))
            raw = (query.get("__test_delay") or ["0"])[0]
            try:
                delay = max(0, min(int(raw), 10_000))
            except ValueError:
                delay = 0
            if delay:
                await asyncio.sleep(delay / 1000.0)
        await self.app(scope, receive, send)


def create_harness_app(*, static_dir: Path | str | None = None) -> Starlette:
    """产品 app（显式测试替身）+ /harness/ 映射；静态根与正式入口一致。

    /harness/ 映射以产品 MIME 表逐文件服务（不用 StaticFiles）：Windows 的
    mimetypes 会把 .js 判成 text/plain，被 Chromium 严格 MIME 门拒绝；
    目录逃逸与 TS 源与产品同一语义返回 404。
    """

    product = create_app(
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"),
        review_provider_factory=lambda: FakeReviewProvider(scenario="ok"),
        suite_review_provider_factory=lambda: FakeSuiteReviewProvider(scenario="ok"),
        static_dir=static_dir,
    )

    async def _harness(request: Request) -> Response:
        relative = "/" + request.url.path[len("/harness"):].lstrip("/")
        response = static_file_response(HARNESS_DIR, relative)
        if response is None:
            return PlainTextResponse("not found", status_code=404)
        return response

    return Starlette(routes=[
        Route("/harness/{rest:path}", _harness),
        Mount("/", app=TestDelayMiddleware(product)),
    ])


def start(*, static_dir: Path | str | None = None) -> tuple[ProductV2Server, str]:
    """启动测试装置并返回（已启动句柄, base_url）。"""

    server = ProductV2Server(create_harness_app(static_dir=static_dir), "127.0.0.1", 0)
    server.start()
    return server, server.base_url


def create_static_app(roots: dict[str, Path] | None = None, *,
                      index_document: Path | None = None,
                      redirect: str | None = None) -> Starlette:
    """只读静态装置：按 URL 前缀挂目录，可选根路径文档/跳转（不涉及产品 API）。

    契约套件是纯模块测试，只需要同 origin 的模块与 harness 页面；这里不挂任何
    API 路由，也不复用产品业务代码，与 `create_harness_app` 的用途区分开。
    """

    if roots is None:
        roots = {"/harness": HARNESS_DIR, "/": resolve_static_root()}
    routes: list[Any] = []
    if index_document is not None:
        document = index_document

        async def _index(_request):  # noqa: ANN001
            return FileResponse(document, media_type="text/html; charset=utf-8",
                                headers=dict(STATIC_HEADERS))
        routes.append(Route("/", _index))
        routes.append(Route("/index.html", _index))
    if redirect is not None:
        async def _redirect(_request):  # noqa: ANN001
            return RedirectResponse(redirect, status_code=302)
        routes.append(Route("/", _redirect))

    async def _serve(request: Request, root: Path, prefix: str) -> Response:
        """以产品 MIME 表服务的只读静态子路由；类型不猜，目录逃逸/TS 源一律不存在。"""

        relative = request.url.path
        if prefix:
            relative = "/" + request.url.path[len(prefix):].lstrip("/")
        response = static_file_response(root, relative)
        if response is None:
            return PlainTextResponse("not found", status_code=404)
        return response

    for prefix, root in sorted(roots.items(), key=lambda item: -len(item[0])):
        mount = prefix.rstrip("/")

        def _handler(sub_root: Path, sub_prefix: str):
            async def view(request: Request) -> Response:
                return await _serve(request, sub_root, sub_prefix)
            return view

        routes.append(Route(f"{mount}/{{rest:path}}", _handler(root, mount)))
    return Starlette(routes=routes)


def start_static(roots: dict[str, Path] | None = None, *,
                 index_document: Path | None = None,
                 redirect: str | None = None) -> tuple[ProductV2Server, str]:
    """启动只读静态装置并返回（已启动句柄, base_url）。"""

    app = create_static_app(roots, index_document=index_document, redirect=redirect)
    server = ProductV2Server(app, "127.0.0.1", 0)
    server.start()
    return server, server.base_url
