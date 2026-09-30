"""Product V2 无状态 HTTP 适配器（V2.4.1）。

职责边界：
  - 只服务 ``app/product_v2/`` 下的产品静态资源，以及无状态 API：
    ``GET /api/v2/capabilities``、``POST /api/v2/semantic/analyze``，以及图像网关三段
    ``POST /api/v2/images/submit`` / ``POST /api/v2/images/status`` / ``POST /api/v2/images/result``。
  - 不接收、不保存任何用户工作空间路径；没有文件夹工作空间、没有最近项目索引，
    没有任何请求字段会被当作本机目录读取。
  - 用户项目、图片与历史全部由浏览器 IndexedDB 持有；本进程只读自己的安装目录。
  - 语义 provider 由 ``config/product-v2/providers.json`` + 环境变量选择
    （见 ``src/providers/v2_registry.py``）；没有密钥或依赖时返回明确的分类错误，不假装成功。
  - 测试装置（``evals/...``）不经正式入口对外服务。

证据入口：``python app/server.py --check``（等价于本模块 ``run_self_check()``）。
"""
from __future__ import annotations

import base64
import json
import hashlib
import re
import sys
import threading
import urllib.parse
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PRODUCT_DIR = (ROOT / "app" / "product_v2").resolve()
MAX_BODY_BYTES = 256 * 1024

CAPABILITIES_PATH = "/api/v2/capabilities"
ANALYZE_PATH = "/api/v2/semantic/analyze"
IMAGE_SUBMIT_PATH = "/api/v2/images/submit"
IMAGE_STATUS_PATH = "/api/v2/images/status"
IMAGE_RESULT_PATH = "/api/v2/images/result"
ANALYZE_FIELDS = ("product_name", "description", "selling_points", "focus", "references",
                  "locale", "platform", "max_slots", "existing_slot_ids")
IMAGE_SUBMIT_FIELDS = ("action_id", "prompt", "references", "size", "seed", "model_id")

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


def default_provider_factory() -> Any:
    """默认语义 provider：注册表 + 环境变量（惰性导入，静态资源路径不依赖模型 SDK）。"""

    from src.providers.v2_registry import create_semantic_provider

    return create_semantic_provider()


def default_image_provider_factory() -> Any:
    """默认图像 provider：注册表 + 环境变量（构造过程不联网、不发图）。"""

    from src.providers.v2_registry import create_image_provider

    return create_image_provider()


def status_for_failure(failure: Any) -> int:
    """分类错误 → HTTP 状态（计划 §9 / §9.2）。"""

    family = getattr(failure, "family", "internal")
    code = getattr(failure, "code", "")
    if family == "input_rejected":
        return 400
    if family == "provider_unknown":
        return 504
    if family == "internal":
        return 503 if code == "PROVIDER_NOT_CONFIGURED" else 500
    return 502


_SECRET_PATTERN = re.compile(r"(sk-|Bearer\s+)[A-Za-z0-9._\-]+")


def redact(text: str, limit: int = 300) -> str:
    """错误消息只保留可诊断信息：不出现密钥片段或请求正文。"""

    return _SECRET_PATTERN.sub("***", str(text))[:limit]


def failure_payload(family: str, code: str, message: str, *, retry_policy: str = "fatal",
                    details: Any = None, unknown: bool = False,
                    http_status: int | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "unknown": bool(unknown),
        "error": {
            "family": family,
            "code": code,
            "message": message,
            "retry_policy": retry_policy,
            "http_status": http_status,
            "request_id": None,
            "details": details,
        },
    }


def input_rejected_payload(message: str, problems: Any = None) -> dict[str, Any]:
    return failure_payload("input_rejected", "INPUT_INVALID", message,
                           retry_policy="fatal", details={"problems": problems})


def internal_error_payload(detail: str) -> dict[str, Any]:
    return failure_payload("internal", "INTERNAL_ERROR",
                           "服务器内部错误；没有产生可用的分析结果。",
                           retry_policy="fatal", details={"detail": detail})


def _provider_error_kind(error: BaseException) -> str:
    if isinstance(error, ImportError):
        return "dependency"
    if type(error).__name__ == "ProviderRegistryError":
        return "registry"
    return "dependency"


def provider_capabilities(provider: Any) -> dict[str, Any]:
    method = getattr(provider, "capabilities", None)
    if not callable(method):
        return {}
    try:
        result = method()
    except Exception:  # noqa: BLE001 - 能力查询失败不应该让路由变成 5xx
        return {}
    return dict(result) if isinstance(result, Mapping) else {}


class ProductV2Handler(BaseHTTPRequestHandler):
    """无状态：请求里没有任何东西会被当成服务器路径；用户数据全在浏览器。"""

    server_version = "AMZListingKitV2/2"

    def log_message(self, fmt, *args):  # noqa: A003 (http.server 接口名)
        """产品输出保持干净：请求日志不混进终端。"""
        return

    @property
    def provider_factory(self) -> Callable[[], Any]:
        factory = getattr(self.server, "provider_factory", None)
        return factory if callable(factory) else default_provider_factory

    @property
    def image_provider_factory(self) -> Callable[[], Any]:
        factory = getattr(self.server, "image_provider_factory", None)
        return factory if callable(factory) else default_image_provider_factory

    def _send_bytes(self, code: int, payload: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (ConnectionError, OSError):
            # 客户端在响应写出前断开（例如刷新打断了正在等待的提交）：这只是这一次连接的失败。
            # 服务端无状态，不因此改变或撤销任何结论；浏览器侧按「没有收到响应」处理。
            pass

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

    def _read_body(self) -> tuple[bytes | None, int, dict[str, Any] | None]:
        """返回 (body, status, payload)；payload 非空表示已经可以结束这个请求。"""
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or not str(raw_length).strip().isdigit():
            return None, 400, input_rejected_payload("请求必须带合法的 Content-Length。")
        length = int(str(raw_length).strip())
        if length <= 0:
            return None, 400, input_rejected_payload("请求体为空。")
        if length > MAX_BODY_BYTES:
            # 先把已声明的正文读完再回 400：直接关闭连接会在客户端仍在发送时触发
            # TCP RST（Windows 上表现为 ConnectionAbortedError），让自检与调用方
            # 拿不到「超限被拒」的明确响应。上限之外再荒谬的长度只读一个限额，
            # 避免被超大 Content-Length 拖住。
            drain_budget = min(length, MAX_BODY_BYTES * 2)
            while drain_budget > 0:
                chunk = self.rfile.read(min(65536, drain_budget))
                if not chunk:
                    break
                drain_budget -= len(chunk)
            return None, 400, input_rejected_payload(
                f"请求体超过上限 {MAX_BODY_BYTES} 字节。",
                {"content_length": length, "limit": MAX_BODY_BYTES})
        body = self.rfile.read(length)
        if len(body) != length:
            return None, 400, input_rejected_payload("请求体在读满之前就结束了。")
        return body, 200, None

    def do_GET(self):  # noqa: N802 (http.server 接口名)
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        # 查询参数在这里没有语义：不存在 directory / workspace 之类的服务端读取。
        if path == "/api/health":
            self._send_json(200, HEALTH)
            return
        if path == CAPABILITIES_PATH:
            self._capabilities()
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
        """写接口都不写服务器状态：语义分析返回提案，图像网关只转发一次调用。"""
        path = urllib.parse.urlsplit(self.path).path
        if path == ANALYZE_PATH:
            self._analyze()
            return
        if path == IMAGE_SUBMIT_PATH:
            self._images_submit()
            return
        if path == IMAGE_STATUS_PATH:
            self._images_status()
            return
        if path == IMAGE_RESULT_PATH:
            self._images_result()
            return
        self._send_not_found(path)

    def _capabilities(self) -> None:
        from src.providers.v2_semantic import SEMANTIC_CONTRACT_VERSION

        payload: dict[str, Any] = {
            "ok": True,
            "semantic_contract": SEMANTIC_CONTRACT_VERSION,
            "analyze_fields": list(ANALYZE_FIELDS),
            "images": self._image_capabilities(),
            "provider": {
                "provider_id": None, "model_id": None,
                "configured": False, "capabilities": {},
            },
            "unavailable": None,
        }
        try:
            provider = self.provider_factory()
        except Exception as error:  # noqa: BLE001 - 能力查询必须给出可用性而不是 5xx
            payload["unavailable"] = {
                "kind": _provider_error_kind(error),
                "detail": redact(type(error).__name__ + ": " + str(error)),
            }
            self._send_json(200, payload)
            return
        payload["provider"] = {
            "provider_id": getattr(provider, "provider_id", None),
            "model_id": getattr(provider, "model_id", None),
            "configured": True,
            "capabilities": provider_capabilities(provider),
        }
        self._send_json(200, payload)

    # ---------------------------------------------------------- 图像网关（V2.4.1）

    def _image_capabilities(self) -> dict[str, Any]:
        from src.providers.v2_image import IMAGE_CONTRACT_VERSION

        block: dict[str, Any] = {
            "contract": IMAGE_CONTRACT_VERSION,
            "endpoints": [IMAGE_SUBMIT_PATH, IMAGE_STATUS_PATH, IMAGE_RESULT_PATH],
            "submit_fields": list(IMAGE_SUBMIT_FIELDS),
            "provider": {"provider_id": None, "model_id": None,
                         "configured": False, "capabilities": {}},
            "unavailable": None,
        }
        try:
            provider = self.image_provider_factory()
        except Exception as error:  # noqa: BLE001 - 能力查询必须给出可用性而不是 5xx
            block["unavailable"] = {
                "kind": _provider_error_kind(error),
                "detail": redact(type(error).__name__ + ": " + str(error)),
            }
            return block
        block["provider"] = {
            "provider_id": getattr(provider, "provider_id", None),
            "model_id": getattr(provider, "model_id", None),
            "configured": bool(getattr(provider, "configured", True)),
            "capabilities": provider_capabilities(provider),
        }
        return block

    def _image_provider(self) -> Any:
        from src.providers.v2_image import ImageFailure

        try:
            return self.image_provider_factory()
        except Exception as error:  # noqa: BLE001 - 构造失败 = 明确的未配置，而不是 500
            raise ImageFailure(
                "internal", "PROVIDER_NOT_CONFIGURED",
                "图像 provider 不可用：检查注册表、依赖与 DASHSCOPE_API_KEY。",
                retry_policy="fatal", http_status=503,
                details={"kind": _provider_error_kind(error),
                         "detail": redact(type(error).__name__ + ": " + str(error))}) from None

    def _image_request(self, model: Any) -> tuple[Any, int, dict[str, Any] | None]:
        """读体 + 契约校验；返回 (request, status, error_payload)。错误时 request 为 None。"""

        from pydantic import ValidationError

        body, status, payload = self._read_body()
        if payload is not None:
            return None, status, payload
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, 400, input_rejected_payload("请求体不是合法 JSON。")
        try:
            return model.model_validate(decoded), 200, None
        except ValidationError as error:
            problems = [{"path": ".".join(str(part) for part in item.get("loc", ())),
                         "message": str(item.get("msg"))}
                        for item in error.errors()[:6]]
            return None, 400, input_rejected_payload(
                "请求字段不符合图像网关契约；没有调用模型。", problems)

    def _image_failure_response(self, failure: Any) -> None:
        self._send_json(status_for_failure(failure), {
            "ok": False,
            "unknown": bool(getattr(failure, "unknown", False)),
            "error": failure.to_dict(),
        })

    def _images_submit(self) -> None:
        from src.providers.v2_image import ImageFailure, SubmitRequest

        request, status, payload = self._image_request(SubmitRequest)
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            task = self._image_provider().submit(request)
        except ImageFailure as failure:
            self._image_failure_response(failure)
            return
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            self._send_json(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
            return
        self._send_json(200, {"ok": True, "unknown": False, "task": task.to_dict()})

    def _images_status(self) -> None:
        from src.providers.v2_image import ImageFailure, TaskRequest

        request, status, payload = self._image_request(TaskRequest)
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            task = self._image_provider().status(request)
        except ImageFailure as failure:
            self._image_failure_response(failure)
            return
        except Exception as error:  # noqa: BLE001
            self._send_json(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
            return
        self._send_json(200, {"ok": True, "unknown": False, "task": task.to_dict()})

    def _images_result(self) -> None:
        from src.providers.v2_image import ImageFailure, TaskRequest

        request, status, payload = self._image_request(TaskRequest)
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            provider = self._image_provider()
            content, media_type = provider.result(request)
        except ImageFailure as failure:
            self._image_failure_response(failure)
            return
        except Exception as error:  # noqa: BLE001
            self._send_json(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
            return
        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Image-Sha256", hashlib.sha256(content).hexdigest())
        self.send_header("X-Provider-Id", str(getattr(provider, "provider_id", "")))
        self.send_header("X-Model-Id", str(getattr(provider, "model_id", "")))
        self.send_header("X-Task-Id", request.task_id)
        self.end_headers()
        self.wfile.write(content)

    def _analyze(self) -> None:
        body, status, payload = self._read_body()
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, input_rejected_payload("请求体不是合法 JSON。"))
            return
        try:
            from src.providers.v2_semantic import (
                SemanticFailure,
                parse_request,
                problems_from_parse_error,
            )
        except Exception as error:  # noqa: BLE001
            self._send_json(503, provider_unavailable_payload(
                "dependency", redact(type(error).__name__ + ": " + str(error))))
            return
        try:
            request = parse_request(decoded)
        except Exception as error:  # noqa: BLE001 - 契约问题一律归 input_rejected
            try:
                problems = problems_from_parse_error(error)
            except Exception:  # noqa: BLE001
                problems = None
            self._send_json(400, input_rejected_payload(
                "请求字段不符合语义请求契约；没有调用模型。", problems))
            return
        try:
            provider = self.provider_factory()
        except Exception as error:  # noqa: BLE001
            self._send_json(503, provider_unavailable_payload(
                _provider_error_kind(error),
                redact(type(error).__name__ + ": " + str(error))))
            return
        try:
            proposal = provider.analyze(request)
        except SemanticFailure as failure:
            body_out = failure.to_dict()
            self._send_json(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": body_out,
            })
            return
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            self._send_json(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
            return
        self._send_json(200, {"ok": True, "unknown": False, "proposal": proposal.to_dict()})


def create_product_v2_server(host: str = "127.0.0.1", port: int = 8780,
                             provider_factory: Callable[[], Any] | None = None,
                             image_provider_factory: Callable[[], Any] | None = None) -> ThreadingHTTPServer:
    """建服务器但不启动；host 由调用方决定（本机默认回环，内网穿透时自行显式放开）。"""
    server = ThreadingHTTPServer((host, port), ProductV2Handler)
    server.provider_factory = provider_factory or default_provider_factory
    server.image_provider_factory = image_provider_factory or default_image_provider_factory
    return server


def run_self_check() -> int:
    """正式入口自检：静态资源可取、两个无状态 API 行为正确、失败被分类、越权路径被拒。"""
    import http.client

    from src.providers.v2_fake_image import FakeImageProvider
    from src.providers.v2_fake_semantic import FakeSemanticProvider

    mode = {"value": "fake"}

    def factory():
        if mode["value"] == "broken":
            raise RuntimeError("自检：语义 provider 构造失败")
        return FakeSemanticProvider(scenario="ok")

    def image_factory():
        if mode["value"] == "broken":
            raise RuntimeError("自检：图像 provider 构造失败")
        return FakeImageProvider(scenario="ok")

    server = create_product_v2_server("127.0.0.1", 0, provider_factory=factory,
                                      image_provider_factory=image_factory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    checks: list[tuple[str, bool, str]] = []

    def request(method: str, path: str, body: bytes | None = None) -> tuple[int, str, bytes]:
        connection = http.client.HTTPConnection(host, port, timeout=20)
        try:
            headers = ({"Content-Type": "application/json; charset=utf-8"}
                       if body is not None else {})
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.getheader("Content-Type") or "", response.read()
        finally:
            connection.close()

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    analyze_body = json.dumps({
        "product_name": "自检商品",
        "description": "自检用的商品资料。",
        "selling_points": ["自检卖点"],
        "focus": "自检重点",
        "references": [{"sha256": "a" * 64, "media_type": "image/png", "role": "primary"}],
        "locale": "zh-CN",
        "platform": "amazon_us",
        "max_slots": 12,
        "existing_slot_ids": [],
    }, ensure_ascii=False).encode("utf-8")

    def json_body(raw: bytes) -> dict:
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

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
        health = json_body(body) if status == 200 else {}
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
        check("不存在其它服务端写接口", status == 404, f"status={status}")

        status, _, body = request("GET", CAPABILITIES_PATH)
        payload = json_body(body)
        check("capabilities 暴露 provider、analyze 字段与契约版本",
              status == 200 and payload.get("ok") is True
              and payload.get("provider", {}).get("configured") is True
              and payload.get("analyze_fields") == list(ANALYZE_FIELDS)
              and bool(payload.get("semantic_contract")),
              f"status={status} provider={payload.get('provider')}")

        images_block = payload.get("images") or {}
        check("capabilities 暴露图像网关（合同、端点、provider 与参考图能力）",
              payload.get("ok") is True
              and images_block.get("provider", {}).get("configured") is True
              and images_block.get("provider", {}).get("model_id") == "qwen-image-3.0"
              and IMAGE_SUBMIT_PATH in (images_block.get("endpoints") or [])
              and images_block.get("provider", {}).get("capabilities", {}).get("reference_images") is True,
              f"images={images_block.get('provider')}")

        status, _, body = request("POST", ANALYZE_PATH, analyze_body)
        payload = json_body(body)
        slots = (payload.get("proposal") or {}).get("slots") or []
        check("语义分析路由（fake provider）返回提案且标记 unknown=false",
              status == 200 and payload.get("ok") is True and payload.get("unknown") is False
              and len(slots) >= 2 and all(item.get("status") == "proposed" for item in slots),
              f"status={status} slots={len(slots)}")

        status, _, body = request("POST", ANALYZE_PATH, b"{not json")
        payload = json_body(body)
        check("非法 JSON 归 input_rejected/400",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected"
              and payload.get("unknown") is False, f"status={status} error={payload.get('error')}")

        oversized = json.dumps({"product_name": "x" * (MAX_BODY_BYTES + 512)}).encode("utf-8")
        status, _, body = request("POST", ANALYZE_PATH, oversized)
        payload = json_body(body)
        check("超过字节上限的请求体被拒（400 input_rejected）",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected",
              f"status={status} bytes={len(oversized)}")

        incomplete = json.dumps({
            "description": "缺少商品名称。",
            "references": [{"sha256": "b" * 64, "media_type": "image/png", "role": "primary"}],
        }, ensure_ascii=False).encode("utf-8")
        status, _, body = request("POST", ANALYZE_PATH, incomplete)
        payload = json_body(body)
        check("合法 JSON 但字段越界归 input_rejected/400（不调用模型）",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected",
              f"status={status} error={payload.get('error')}")

        mode["value"] = "broken"
        status, _, body = request("GET", CAPABILITIES_PATH)
        payload = json_body(body)
        check("provider 不可用时 capabilities 仍 200 且 configured=false",
              status == 200 and payload.get("provider", {}).get("configured") is False
              and (payload.get("unavailable") or {}).get("kind") in ("registry", "dependency"),
              f"status={status} unavailable={payload.get('unavailable')}")

        status, _, body = request("POST", ANALYZE_PATH, analyze_body)
        payload = json_body(body)
        check("provider 不可用时分析路由 503 且错误分类明确",
              status == 503 and payload.get("error", {}).get("code") == "PROVIDER_NOT_CONFIGURED"
              and payload.get("unknown") is False,
              f"status={status} error={payload.get('error')}")
        mode["value"] = "fake"

        status, _, _ = request("POST", "/api/v2/semantic/unknown", analyze_body)
        check("未定义的无状态写路由保持 404", status == 404, f"status={status}")

        sample_png = FakeImageProvider.bytes_for("self-check")
        submit_body = json.dumps({
            "action_id": "self-check-action-01",
            "prompt": "自检用提示词。",
            "references": [{"role": "primary", "media_type": "image/png",
                            "sha256": hashlib.sha256(sample_png).hexdigest(),
                            "data_base64": base64.b64encode(sample_png).decode("ascii")}],
        }, ensure_ascii=False).encode("utf-8")
        status, _, body = request("POST", IMAGE_SUBMIT_PATH, submit_body)
        payload = json_body(body)
        task_id = (payload.get("task") or {}).get("task_id")
        check("图像提交路由（假 provider）返回任务身份且不泄露结果地址",
              status == 200 and payload.get("ok") is True and payload.get("unknown") is False
              and task_id == FakeImageProvider.task_id_for("self-check-action-01")
              and "aliyuncs" not in body.decode("utf-8", "replace"),
              f"status={status} task={task_id}")

        status, _, body = request("POST", IMAGE_STATUS_PATH,
                                  json.dumps({"task_id": task_id}).encode("utf-8"))
        payload = json_body(body)
        check("图像状态查询路由返回成功状态与结果数量",
              status == 200 and (payload.get("task") or {}).get("status") == "SUCCEEDED"
              and (payload.get("task") or {}).get("result_count") == 1,
              f"status={status} task={payload.get('task')}")

        status, ctype, body = request("POST", IMAGE_RESULT_PATH,
                                      json.dumps({"task_id": task_id}).encode("utf-8"))
        check("图像结果路由返回 PNG 字节（不是地址）",
              status == 200 and "image/png" in ctype
              and body.startswith(b"\x89PNG\r\n\x1a\n"),
              f"status={status} type={ctype} bytes={len(body)}")

        bad_body = json.dumps({
            "action_id": "self-check-action-02", "prompt": "x",
            "directory": "/etc", "references": [],
        }, ensure_ascii=False).encode("utf-8")
        status, _, body = request("POST", IMAGE_SUBMIT_PATH, bad_body)
        payload = json_body(body)
        check("图像提交拒绝目录字段与空参考图（input_rejected，不调用上游）",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected"
              and payload.get("unknown") is False,
              f"status={status} error={payload.get('error')}")

        mode["value"] = "broken"
        status, _, body = request("GET", CAPABILITIES_PATH)
        payload = json_body(body)
        check("图像 provider 不可用时 capabilities 仍 200 且 configured=false",
              status == 200
              and (payload.get("images") or {}).get("provider", {}).get("configured") is False
              and ((payload.get("images") or {}).get("unavailable") or {}).get("kind") in ("registry", "dependency"),
              f"images={(payload.get('images') or {}).get('unavailable')}")
        status, _, body = request("POST", IMAGE_SUBMIT_PATH, submit_body)
        payload = json_body(body)
        check("图像 provider 不可用时提交路由 503 且错误分类明确",
              status == 503 and payload.get("error", {}).get("code") == "PROVIDER_NOT_CONFIGURED"
              and payload.get("unknown") is False,
              f"status={status} error={payload.get('error')}")
        mode["value"] = "fake"
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


def provider_unavailable_payload(kind: str, detail: str, *, status: int = 503) -> dict[str, Any]:
    """provider 构造失败（依赖缺失、注册表读不出来、密钥缺失）时的统一响应。"""

    return {
        "ok": False,
        "unknown": False,
        "error": {
            "family": "internal",
            "code": "PROVIDER_NOT_CONFIGURED",
            "message": "语义 provider 不可用：检查注册表、依赖与 DASHSCOPE_API_KEY。",
            "retry_policy": "fatal",
            "http_status": status,
            "request_id": None,
            "details": {"kind": kind, "detail": detail},
        },
    }
