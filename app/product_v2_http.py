"""Product V2 的 HTTP 宿主：ASGI 服务器生命周期与静态文件策略。

职责边界（P3 替换自研 HTTP 之后）：
  - 连接、协议解析、并发与优雅退出交给标准服务器（uvicorn + h11）；
  - 本模块只保留两件产品必须自己拥有的政策：监听地址/端口的真实绑定与端口冲突，
    以及“生产只服务唯一构建产物 ``dist/product-v2``”的静态文件拒绝规则。
  - 路由、正文上限、错误分类、出站白名单、默认关闭与请求级凭据仍在
    ``app/product_v2_server.py``；本模块不复制任何业务判断。

静态目录没有源码回退：构建产物不存在时抛 :class:`StaticRootMissing`，由入口明确报错。
"""
from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
from starlette.responses import FileResponse, Response

ROOT = Path(__file__).resolve().parents[1]
# 唯一生产浏览器产物：Vite 标准构建输出（源码目录不参与生产服务）。
PRODUCTION_STATIC_DIR = ROOT / "dist" / "product-v2"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}
# 浏览器只消费构建产物；TS 源与类型声明（.ts 覆盖 .d.ts）永不外放。
STATIC_DENY_SUFFIXES = frozenset({".ts"})
# 浏览器模块突发不能被默认的 5 个等待连接挡住；交给 OS 的合理上限，
# 这不是业务并发/重试策略，而是服务器监听队列本身。
BACKLOG = 2048
STATIC_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


class StaticRootMissing(RuntimeError):
    """唯一的静态产物目录不存在：生产网关不猜、不回退源码目录。"""


def resolve_static_root(static_dir: Path | str | None = None) -> Path:
    """解析静态根目录；缺省必须是仓库内 ``dist/product-v2``。"""

    root = Path(static_dir) if static_dir is not None else PRODUCTION_STATIC_DIR
    resolved = root.resolve()
    if not resolved.is_dir():
        raise StaticRootMissing(
            f"静态构建产物不存在：{resolved}。先运行前端构建（npm run build:frontend）；"
            "生产网关只服务 dist/product-v2，不回退源码目录。")
    return resolved


def resolve_static_file(root: Path, url_path: str) -> Path | None:
    """只解析静态根目录内的真实文件；目录逃逸与 TS 源一律视为不存在。"""

    relative = url_path.lstrip("/") or "index.html"
    candidate = (root / relative).resolve()
    if candidate == root or root not in candidate.parents:
        return None
    if candidate.suffix.lower() in STATIC_DENY_SUFFIXES:
        return None
    if not candidate.is_file():
        return None
    return candidate


def static_file_response(root: Path, url_path: str) -> Response | None:
    """静态文件的框架响应（FileResponse 负责长度/流式）；不存在返回 None。"""

    path = resolve_static_file(root, url_path)
    if path is None:
        return None
    return FileResponse(
        path,
        media_type=MIME.get(path.suffix, "application/octet-stream"),
        headers=dict(STATIC_HEADERS),
    )


def _bind(host: str, port: int) -> socket.socket:
    """真实绑定监听地址；端口被占时抛 OSError（入口据此给出可读提示）。

    Windows 上不设 SO_REUSEADDR：该选项允许第二个进程静默绑定同一端口
    （历史上表现为“端口仍在监听却无人应答”），这里要求端口冲突直接失败。
    """

    infos = socket.getaddrinfo(host or None, port, type=socket.SOCK_STREAM,
                               flags=socket.AI_PASSIVE)
    last_error: OSError | None = None
    for family, socktype, proto, _name, address in infos:
        probe = socket.socket(family, socktype, proto)
        try:
            if os.name != "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(address)
            return probe
        except OSError as error:
            last_error = error
            probe.close()
    raise last_error if last_error is not None else OSError(f"无法绑定 {host}:{port}")


class ProductV2Server:
    """一个可启动/停止的 ASGI 服务器句柄（产品入口与验证装置共用）。

    接口只有：``start()``（后台线程，就绪后返回）、``run()``（前台阻塞）、
    ``stop()``（优雅退出并关闭监听）、``port`` 与 ``base_url``。
    """

    def __init__(self, app: Any, host: str = "127.0.0.1", port: int = 8780) -> None:
        self._app = app
        self.host = host
        self._socket: socket.socket | None = _bind(host, port)
        self.port = int(self._socket.getsockname()[1])
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        host = "127.0.0.1" if self.host in {"0.0.0.0", "::", ""} else self.host
        return f"http://{host}:{self.port}"

    @property
    def running(self) -> bool:
        """是否已就绪且未被要求退出（诊断/验证记录的宿主状态，不含业务含义）。"""

        server = self._server
        return bool(server is not None and server.started and not server.should_exit)

    def _config(self) -> uvicorn.Config:
        return uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            loop="asyncio",
            http="h11",
            ws="none",
            lifespan="off",
            log_level="warning",
            access_log=False,
            server_header=False,
            date_header=False,
            proxy_headers=False,
            backlog=BACKLOG,
        )

    def start(self) -> "ProductV2Server":
        """后台线程启动并等待真正可连接；失败抛 RuntimeError。"""

        if self._server is not None:
            raise RuntimeError("同一个 ProductV2Server 不能重复启动。")
        self._server = uvicorn.Server(self._config())
        self._thread = threading.Thread(target=self._run_background,
                                        name="product-v2-http", daemon=True)
        self._thread.start()
        self._wait_ready()
        return self

    def _run_background(self) -> None:
        assert self._server is not None
        self._server.run(sockets=[self._socket])

    def _wait_ready(self, timeout: float = 20.0) -> None:
        assert self._server is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                return
            if self._thread is None or not self._thread.is_alive():
                raise RuntimeError("HTTP 服务器线程提前退出（启动失败）。")
            time.sleep(0.01)
        raise RuntimeError(f"HTTP 服务器 {timeout:.0f} 秒内没有就绪。")

    def run(self) -> None:
        """前台阻塞运行（正式入口）；Ctrl+C/SIGTERM 由服务器优雅处理。"""

        if self._server is not None:
            raise RuntimeError("同一个 ProductV2Server 不能重复运行。")
        self._server = uvicorn.Server(self._config())
        try:
            self._server.run(sockets=[self._socket])
        finally:
            self._close_socket()

    def stop(self) -> None:
        """优雅退出：不再接受新连接，等在途请求结束，然后关闭监听。"""

        if self._server is not None:
            self._server.should_exit = True
            thread = self._thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=20)
        self._close_socket()

    def _close_socket(self) -> None:
        sock, self._socket = self._socket, None
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass
