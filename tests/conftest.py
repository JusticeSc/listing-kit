"""pytest 网关/自检共享装置：真实 TCP + 假 provider，不触网、不付费、不写产品数据。

P3 迁移口径（FastAPI/uvicorn 之前，这两组检查分别住在 `app/product_v2_server.py`
的 `run_self_check()` 与 `tools/verify_v2_4_1_image_gateway.py`）：产品自检只保留
轻量真实健康检查，协议/路由/上限/秘密与图像网关场景在这里按 pytest 组真实跑。
"""
from __future__ import annotations

import http.client
import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from app.product_v2_http import ProductV2Server  # noqa: E402
from app.product_v2_server import create_app  # noqa: E402

# 最小但真实的构建产物形状：页面 + 模块 + CSS，以及永不外放的 TS 源/类型声明。
STATIC_FILES = {
    "index.html": (
        "<!doctype html><html lang=zh-CN><head><meta charset=utf-8>"
        "<title>Product V2</title></head><body>"
        "<div id=\"boot-pending\"></div><script type=module src=app.js></script>"
        "</body></html>"
    ),
    "app.js": "console.log('product-v2');\n",
    "styles.css": "body{margin:0}\n",
    "storage/index.js": "export const openStorage = async () => ({});\n",
    "domain/attempt.js": "export const attemptState = 'idle';\n",
    "domain/attempt.ts": "export const attemptState: string = 'idle';\n",
    "domain/type-contracts.d.ts": "export type Id = string;\n",
}

TEST_STATIC_DIR_ENV = "AMZ_V2_TEST_STATIC_DIR"


def build_static(root: Path) -> Path:
    """写出最小构建产物；返回根目录（测试装置自己的 dist，不写仓库）。"""

    for relative, content in STATIC_FILES.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def default_fakes() -> dict:
    """四类 provider 的显式测试替身工厂（无密钥、无网络、无真实供应商）。"""

    from src.providers.v2_fake_image import FakeImageProvider
    from src.providers.v2_fake_review import FakeReviewProvider
    from src.providers.v2_fake_semantic import FakeSemanticProvider
    from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider

    return {
        "provider_factory": lambda: FakeSemanticProvider(scenario="ok"),
        "image_provider_factory": lambda: FakeImageProvider(scenario="ok"),
        "review_provider_factory": lambda: FakeReviewProvider(scenario="ok"),
        "suite_review_provider_factory": lambda: FakeSuiteReviewProvider(scenario="ok"),
    }


@pytest.fixture
def static_root(tmp_path: Path) -> Path:
    """每次测试独立的最小 dist/product-v2 构建产物目录。"""

    return build_static(tmp_path / "product-v2")


@pytest.fixture
def start_server(static_root: Path, monkeypatch: pytest.MonkeyPatch):
    """按需装配 ASGI app 并按真实 TCP 启动；退出时全部优雅停止（失败也会清理）。"""

    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("AMZ_V2_DEFAULT_TRIAL", raising=False)
    started: list[ProductV2Server] = []

    def _start(*, static_dir: Path | None = None, **overrides) -> ProductV2Server:
        factories = default_fakes()
        factories.update(overrides)
        app = create_app(static_dir=static_dir or static_root, **factories)
        handle = ProductV2Server(app, "127.0.0.1", 0)
        handle.start()
        started.append(handle)
        return handle

    yield _start
    for handle in reversed(started):
        handle.stop()


@pytest.fixture
def gateway(start_server) -> ProductV2Server:
    """默认假 provider 的网关句柄（真实 TCP，真实路由与框架中间件）。"""

    return start_server()


@pytest.fixture
def plain_server(static_root: Path):
    """不注入任何替身的网关：走真实注册表默认与 fail-closed 默认档口径。"""

    handle = ProductV2Server(create_app(static_dir=static_root), "127.0.0.1", 0)
    handle.start()
    yield handle
    handle.stop()


class Client:
    """真实 TCP 客户端：一条连接一次请求，按 HTTP/1.1 读完整响应。"""

    def __init__(self, server: ProductV2Server, *, timeout: float = 20.0) -> None:
        self.host = "127.0.0.1"
        self.port = server.port
        self.timeout = timeout

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            sent = dict(headers or {})
            if body is not None:
                sent.setdefault("Content-Type", "application/json; charset=utf-8")
            connection.request(method, path, body=body, headers=sent)
            response = connection.getresponse()
            payload = response.read()
            return response.status, {key.lower(): value for key, value in response.getheaders()}, payload
        finally:
            connection.close()

    def json(self, method: str, path: str, payload: object | None = None,
             headers: dict[str, str] | None = None) -> tuple[int, dict]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status, _headers, raw = self.request(method, path, body, headers)
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001 - 非 JSON 响应由调用方按字节断言
            decoded = {}
        return status, decoded


@pytest.fixture
def client(gateway: ProductV2Server) -> Client:
    return Client(gateway)


def raw_exchange(server: ProductV2Server, payload: bytes, *,
                 read_limit: int = 65536, timeout: float = 5.0) -> bytes:
    """把原始字节送到真实端口，读回服务端实际写出的字节（帧/连接语义验证用）。"""

    with socket.create_connection(("127.0.0.1", server.port), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(payload)
        received = bytearray()
        try:
            while len(received) < read_limit:
                part = connection.recv(8192)
                if not part:
                    break
                received.extend(part)
        except (socket.timeout, ConnectionResetError):
            pass
    return bytes(received)


def http_head(received: bytes) -> tuple[bytes, bytes, dict[bytes, bytes]]:
    """拆出 (状态行, 正文, 小写头表)。"""

    head, separator, body = received.partition(b"\r\n\r\n")
    headers = {}
    if separator:
        for line in head.split(b"\r\n")[1:]:
            if b":" in line:
                name, value = line.split(b":", 1)
                headers[name.strip().lower()] = value.strip()
    return head.split(b"\r\n")[0], body, headers
