"""Product V2 无状态 HTTP 适配器（V2.4.1）。

职责边界：
  - 只服务 ``app/product_v2/`` 下的产品静态资源，以及无状态 API：
    ``GET /api/v2/capabilities``、``POST /api/v2/semantic/analyze``、图像网关三段
    ``POST /api/v2/images/submit`` / ``POST /api/v2/images/status`` / ``POST /api/v2/images/result``，
    以及 VLM 复核 ``POST /api/v2/review/candidate``（只产生风险提示，不产生人工采纳）。
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
import os
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
# 超限请求在被拒前最多读完的正文长度：只有把声明长度读完再回 400，浏览器 fetch 才不会
# 因连接被提前打断而丢掉这个 400（2026-10-01 走查预演在 679KB 参考图上实测为 unknown）。
# 仅对超过这个荒谬长度的声明提前收手，避免被超大 Content-Length 拖住。
DRAIN_ABSOLUTE_MAX = 128 * 1024 * 1024
# 复核要携带候选图与参考图的 base64；只对复核路由放宽上限，其余路由仍按 256KB 拒绝。
MAX_REVIEW_BODY_BYTES = 24 * 1024 * 1024
# 提交要携带参考图 base64（客户端限单张 ≤10MB、单次最多 3 张 → base64 ≈40MB）；
# 2026-10-01 走查预演发现 256KB 默认上限把 679KB 的真实商品图挡在门外。
MAX_IMAGE_BODY_BYTES = 48 * 1024 * 1024

CAPABILITIES_PATH = "/api/v2/capabilities"
ANALYZE_PATH = "/api/v2/semantic/analyze"
IMAGE_SUBMIT_PATH = "/api/v2/images/submit"
IMAGE_STATUS_PATH = "/api/v2/images/status"
IMAGE_RESULT_PATH = "/api/v2/images/result"
REVIEW_PATH = "/api/v2/review/candidate"
# 整套复核一次最多 8 张 × 4MB，base64 后留 1.5 倍余量；只对这条路由放宽。
MAX_SUITE_REVIEW_BODY_BYTES = 48 * 1024 * 1024
SUITE_REVIEW_PATH = "/api/v2/review/suite"
ANALYZE_FIELDS = ("product_name", "description", "selling_points", "focus", "references",
                  "locale", "platform", "max_slots", "existing_slot_ids")
IMAGE_SUBMIT_FIELDS = ("action_id", "prompt", "references", "size", "seed", "model_id")
# 三用途请求头（V2.6.0）：Provider 选择 + 请求级 BYOK。图像键名保持既有通道（无垫片）；
# 语义/复核是新增有限头。密钥只在本次请求内存里出现，不落盘、不进日志、不进注册表。
SEMANTIC_PROVIDER_HEADER = "X-AMZ-Listing-Provider-Semantic"
IMAGE_PROVIDER_HEADER = "X-AMZ-Listing-Provider-Image"
REVIEW_PROVIDER_HEADER = "X-AMZ-Listing-Provider-Review"
SEMANTIC_BYOK_HEADER = "X-AMZ-Listing-Key-Semantic"
IMAGE_BYOK_HEADER = "X-AMZ-Listing-Key-Image"
REVIEW_BYOK_HEADER = "X-AMZ-Listing-Key-Review"
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
# 渐进 TS 迁移（计划 §9 V2.R7.5）：浏览器只消费生成的 .js；.ts / .d.ts 源码一律不外放，
# 避免把唯一手工维护的 TS 源当静态资源发出去（Docker 里也已排除 .ts）。
STATIC_DENY_SUFFIXES = frozenset({".ts"})

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


def default_review_provider_factory() -> Any:
    """默认复核 provider：注册表 + 环境变量（构造过程不联网、不发图）。"""

    from src.providers.v2_registry import create_review_provider

    return create_review_provider()


def default_suite_review_provider_factory() -> Any:
    """默认整套复核 provider：与单图复核同一注册表条目与模型通道，只换适配器。"""

    from src.providers.v2_registry import create_suite_review_provider

    return create_suite_review_provider()


def status_for_failure(failure: Any) -> int:
    """分类错误 → HTTP 状态（计划 §9 / §9.2）。"""

    family = getattr(failure, "family", "internal")
    code = getattr(failure, "code", "")
    if family == "input_rejected":
        return 400
    if family == "provider_unknown":
        return 504
    if family == "internal":
        if code in ("PROVIDER_NOT_CONFIGURED", "OUTBOUND_POLICY_REJECTED"):
            return 503
        return 500
    return 502


_SECRET_PATTERN = re.compile(r"(sk-|Bearer\s+|x-amz-listing-key-[a-z]+\s*[:=]\s*)"
                             r"[A-Za-z0-9._\-]+", re.IGNORECASE)


def redact(text: str, limit: int = 300, *, secrets: Any = None) -> str:
    """错误消息只保留可诊断信息：不出现密钥片段（含 BYOK 头携带的值）或请求正文。

    secrets：本次请求出现过的请求级密钥原文（任意非 sk 字节也照样遮蔽）；逐字替换后
    再走通用模式遮蔽。密钥只在内存里比对，不进日志、不进响应以外的任何地方。
    """

    safe = str(text)
    candidates: list[str] = []
    if isinstance(secrets, str):
        candidates = [secrets]
    elif isinstance(secrets, (list, tuple, set)):
        candidates = [item for item in secrets if isinstance(item, str)]
    for secret in candidates:
        token = secret.strip()
        if len(token) >= 4:
            safe = safe.replace(token, "***")
    return _SECRET_PATTERN.sub("***", safe)[:limit]


def default_trial_state() -> str:
    """自省口径：open / closed / invalid（解析失败）。只发状态值，不发任何密钥。"""

    from src.providers.v2_credentials import resolve_default_trial

    try:
        return "open" if resolve_default_trial(os.environ) else "closed"
    except ValueError:
        return "invalid"


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
    """无状态：请求里没有任何东西会被当成服务器路径；用户数据全在浏览器。

    连接复用：产品所有响应（静态、JSON、图片字节、send_error 错误页）都带 Content-Length，
    所以按 HTTP/1.1 保持连接是安全的，浏览器不必为每条模块请求新建连接——实测 150 次页面
    加载里，HTTP/1.0 的 8544 次建连出现 3 次 net::ERR_CONNECTION_REFUSED（服务器从未收到
    该请求，端口仍在监听），HTTP/1.1 的 150 次加载 0 次失败。保持连接的前提是本条请求的
    正文必须被读完；读不完的请求一律 `_drop_connection()`，绝不让残留字节被当成下一条请求。
    """

    server_version = "AMZListingKitV2/2"
    protocol_version = "HTTP/1.1"

    def _drop_connection(self) -> None:
        """本请求还有未消费的正文：关掉连接，下一条请求必须在新连接上重新开始。"""

        self.close_connection = True

    def handle(self) -> None:
        """客户端中止连接是正常断连（Windows 回环上表现为 WinError 10053），不是服务器错误。

        这类异常只说明这条连接结束了：不打印 traceback、不影响其它连接或任何结论。
        """

        try:
            super().handle()
        except ConnectionError:
            self.close_connection = True
            return

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

    @property
    def review_provider_factory(self) -> Callable[[], Any]:
        factory = getattr(self.server, "review_provider_factory", None)
        return factory if callable(factory) else default_review_provider_factory

    @property
    def suite_review_provider_factory(self) -> Callable[[], Any]:
        factory = getattr(self.server, "suite_review_provider_factory", None)
        return factory if callable(factory) else default_suite_review_provider_factory

    def _request_headers(self) -> dict[str, str]:
        """把本次请求的 headers 收成普通 dict（只读快照；密钥不存别处）。"""

        return {str(key): str(value) for key, value in self.headers.items()}

    def _is_default_factory(self, factory: Callable[[], Any], default: Callable[[], Any]) -> bool:
        """区分显式注入 factory 与默认 factory：只有默认才允许走注册表覆盖同名实例。"""

        return factory is default or getattr(factory, "__name__", "") == getattr(
            default, "__name__", "\0default")

    def _effective_semantic(self) -> tuple[Any, dict[str, Any]]:
        """语义有效元组：同一解析供能力投影与执行共用；BYOK 只在本次请求内存里。"""

        from src.providers.v2_registry import (
            SEMANTIC_KEY_HEADER,
            SEMANTIC_PROVIDER_HEADER,
            create_semantic_provider,
            resolve_effective,
            resolve_provider_id,
        )

        headers = self._request_headers()
        factory = self.provider_factory
        try:
            return resolve_effective(
                purpose="semantic", role="semantic",
                provider_header=SEMANTIC_PROVIDER_HEADER, key_header=SEMANTIC_KEY_HEADER,
                default_resolver=resolve_provider_id, create=create_semantic_provider,
                env=dict(os.environ), headers=headers, factory=factory,
                is_default_factory=self._is_default_factory(factory, default_provider_factory))
        except Exception as error:  # noqa: BLE001 - 注册表/头校验失败转分类错误
            if type(error).__name__ in ("ByokHeaderError", "ProviderRegistryError"):
                from src.providers.v2_semantic import SemanticFailure
                code = "BYOK_HEADER_INVALID" if type(error).__name__ == "ByokHeaderError" else "INPUT_INVALID"
                secrets = [headers.get(SEMANTIC_KEY_HEADER, ""),
                           headers.get(IMAGE_BYOK_HEADER, ""),
                           headers.get(REVIEW_BYOK_HEADER, "")]
                raise SemanticFailure("input_rejected", code,
                                      redact(str(error)[:200], secrets=secrets),
                                      retry_policy="fatal") from None
            raise

    def _effective_image(self) -> tuple[Any, dict[str, Any]]:
        """图像有效元组：原任务核对用同一元组的凭据来源，不偷用当前配置查旧任务。"""
        from src.providers.v2_image import ImageFailure
        from src.providers.v2_registry import (
            IMAGE_KEY_HEADER,
            IMAGE_PROVIDER_HEADER,
            create_image_provider,
            resolve_effective,
            resolve_image_provider_id,
        )

        headers = self._request_headers()
        factory = self.image_provider_factory
        try:
            return resolve_effective(
                purpose="image", role="image",
                provider_header=IMAGE_PROVIDER_HEADER, key_header=IMAGE_KEY_HEADER,
                default_resolver=resolve_image_provider_id, create=create_image_provider,
                env=dict(os.environ), headers=headers, factory=factory,
                is_default_factory=self._is_default_factory(factory, default_image_provider_factory))
        except Exception as error:  # noqa: BLE001
            if type(error).__name__ in ("ByokHeaderError", "ProviderRegistryError"):
                code = "BYOK_HEADER_INVALID" if type(error).__name__ == "ByokHeaderError" else "INPUT_INVALID"
                raise ImageFailure("input_rejected", code, str(error)[:200],
                                   retry_policy="fatal", http_status=400) from None
            raise

    def _effective_review(self, *, suite: bool = False) -> tuple[Any, dict[str, Any]]:
        """复核有效元组：单图与整套共用同一 review 条目与模型通道，只换适配器类。"""

        from src.providers.v2_registry import (
            REVIEW_KEY_HEADER,
            REVIEW_PROVIDER_HEADER,
            create_review_provider,
            create_suite_review_provider,
            resolve_effective,
            resolve_review_provider_id,
        )
        from src.providers.v2_semantic import SemanticFailure

        headers = self._request_headers()
        factory = self.suite_review_provider_factory if suite else self.review_provider_factory
        default_factory = (default_suite_review_provider_factory if suite
                           else default_review_provider_factory)
        create = create_suite_review_provider if suite else create_review_provider
        try:
            return resolve_effective(
                purpose="review", role="review",
                provider_header=REVIEW_PROVIDER_HEADER, key_header=REVIEW_KEY_HEADER,
                default_resolver=resolve_review_provider_id, create=create,
                env=dict(os.environ), headers=headers, factory=factory,
                is_default_factory=self._is_default_factory(factory, default_factory))
        except Exception as error:  # noqa: BLE001
            if type(error).__name__ in ("ByokHeaderError", "ProviderRegistryError"):
                code = "BYOK_HEADER_INVALID" if type(error).__name__ == "ByokHeaderError" else "INPUT_INVALID"
                raise SemanticFailure("input_rejected", code, str(error)[:200],
                                      retry_policy="fatal") from None
            raise

    def _send_bytes(self, code: int, payload: bytes, ctype: str,
                    extra_headers: tuple[tuple[str, str], ...] = ()) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in extra_headers:
            self.send_header(name, value)
        if self.close_connection:
            # 这条响应之后就要关连接（未读完的正文、未知路由、写坏的连接）：必须告诉客户端，
            # 否则 HTTP/1.1 客户端会以为连接还能复用。
            self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (ConnectionError, OSError):
            # 客户端在响应写出前断开（例如刷新打断了正在等待的提交）：这只是这一次连接的失败。
            # 服务端无状态，不因此改变或撤销任何结论；浏览器侧按「没有收到响应」处理。
            # 这条连接已经写坏了，不能继续复用它等下一条请求。
            self._drop_connection()

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
        if candidate.suffix.lower() in STATIC_DENY_SUFFIXES:
            # TS 源码（含 .d.ts）不是运行时资源：浏览器只能取同目录生成的 .js。
            return None
        if not candidate.is_file():
            return None
        return candidate

    def _read_body(self, max_bytes: int = MAX_BODY_BYTES) -> tuple[bytes | None, int, dict[str, Any] | None]:
        """返回 (body, status, payload)；payload 非空表示已经可以结束这个请求。"""
        raw_length = self.headers.get("Content-Length")
        if self.headers.get("Transfer-Encoding") is not None or raw_length is None:
            # 不解码 chunked；长度不明确或有传输编码时，正文不能留给下一条请求。
            self._drop_connection()
            return None, 400, input_rejected_payload("请求只支持合法的 Content-Length，不支持 Transfer-Encoding。")
        if not str(raw_length).strip().isdigit():
            self._drop_connection()          # 长度不可知：残留正文无法安全跳过
            return None, 400, input_rejected_payload("请求必须带合法的 Content-Length。")
        length = int(str(raw_length).strip())
        if length <= 0:
            return None, 400, input_rejected_payload("请求体为空。")
        if length > max_bytes:
            # 先把已声明的正文读完再回 400：不读完就关闭连接会让浏览器 fetch 丢掉
            # 已经写出的 400（表现为 network error → 客户端误判 unknown，2026-10-01
            # 走查预演在 679KB 参考图上实测）。只有超过 DRAIN_ABSOLUTE_MAX 的荒谬
            # 长度才提前收手，避免被超大 Content-Length 拖住；收手时正文没读完，
            # 这条连接只能关闭，不能让残留字节被当成下一条请求。
            drain_budget = min(length, DRAIN_ABSOLUTE_MAX)
            while drain_budget > 0:
                chunk = self.rfile.read(min(65536, drain_budget))
                if not chunk:
                    break
                drain_budget -= len(chunk)
            if length > DRAIN_ABSOLUTE_MAX or drain_budget > 0:
                self._drop_connection()
            return None, 400, input_rejected_payload(
                f"请求体超过上限 {max_bytes} 字节。",
                {"content_length": length, "limit": max_bytes})
        body = self.rfile.read(length)
        if len(body) != length:
            self._drop_connection()          # 正文没读满：连接已不可信
            return None, 400, input_rejected_payload("请求体在读满之前就结束了。")
        return body, 200, None

    def do_GET(self):  # noqa: N802 (http.server 接口名)
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        # GET 不消费正文：带正文的 GET 是异常请求，读完才复用不安全。
        raw_length = self.headers.get("Content-Length")
        if (self.headers.get("Transfer-Encoding") is not None
                or (raw_length is not None
                    and (not str(raw_length).strip().isdigit() or int(str(raw_length).strip()) > 0))):
            self._drop_connection()
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
        if path == REVIEW_PATH:
            self._review()
            return
        if path == SUITE_REVIEW_PATH:
            self._suite_review()
            return
        # 未知路由也可能带正文：这里不读正文，读完才复用不安全，所以关掉这条连接。
        self._drop_connection()
        self._send_not_found(path)

    def _capabilities(self) -> None:
        from src.providers.v2_registry import load_registry, provider_choices
        from src.providers.v2_semantic import SEMANTIC_CONTRACT_VERSION

        try:
            registry = load_registry()
        except Exception:
            registry = None
        payload: dict[str, Any] = {
            "ok": True,
            "semantic_contract": SEMANTIC_CONTRACT_VERSION,
            "analyze_fields": list(ANALYZE_FIELDS),
            "images": self._image_capabilities(),
            "review": self._review_capabilities(),
            "suite_review": self._suite_review_capabilities(),
            "provider": {
                "provider_id": None, "model_id": None,
                "configured": False, "capabilities": {},
            },
            "unavailable": None,
        }
        if registry is not None:
            payload["provider_choices"] = provider_choices(registry, active_ids=self._seam_ids())
        try:
            _provider, effective = self._effective_semantic()
        except Exception as error:  # noqa: BLE001 - 能力查询必须给出可用性而不是 5xx
            payload["unavailable"] = {
                "kind": _provider_error_kind(error),
                "detail": redact(type(error).__name__ + ": " + str(error)),
            }
            self._send_json(200, payload)
            return
        payload["provider"] = {
            "provider_id": effective.get("provider_id"),
            "model_id": effective.get("model_id"),
            "protocol": effective.get("protocol"),
            "capability_version": None,
            "configured": bool(effective.get("configured")),
            "credential_source": effective.get("credential_source"),
            "capabilities": provider_capabilities(_provider),
        }
        self._send_json(200, payload)

    def _seam_ids(self) -> set[str]:
        """显式注入接缝的 active 身份：fake 只在该接缝的目录里可见，生产目录永不含 fake。"""

        found: set[str] = set()
        for factory in (self.provider_factory, self.image_provider_factory,
                        self.review_provider_factory, self.suite_review_provider_factory):
            try:
                instance = factory()
            except Exception:  # noqa: BLE001 - 造不出就不按接缝处理
                continue
            method = getattr(instance, "capabilities", None)
            try:
                capabilities = method() if callable(method) else None
            except Exception:  # noqa: BLE001
                continue
            if isinstance(capabilities, Mapping):
                value = capabilities.get("provider_id")
                if isinstance(value, str) and value:
                    found.add(value)
        return found

    def _image_capabilities(self) -> dict[str, Any]:
        from src.providers.v2_image import IMAGE_CONTRACT_VERSION, IMAGES_CAPABILITY_VERSION

        block: dict[str, Any] = {
            "contract": IMAGE_CONTRACT_VERSION,
            "endpoints": [IMAGE_SUBMIT_PATH, IMAGE_STATUS_PATH, IMAGE_RESULT_PATH],
            "submit_fields": list(IMAGE_SUBMIT_FIELDS),
            "provider": {"provider_id": None, "model_id": None,
                         "capability_version": IMAGES_CAPABILITY_VERSION,
                         "configured": False, "capabilities": {}},
            "unavailable": None,
        }
        try:
            provider, effective = self._effective_image()
        except Exception as error:  # noqa: BLE001 - 能力查询必须给出可用性而不是 5xx
            block["unavailable"] = {
                "kind": _provider_error_kind(error),
                "detail": redact(type(error).__name__ + ": " + str(error)),
            }
            block["default_trial"] = default_trial_state()
            return block
        block["provider"] = {
            "provider_id": effective.get("provider_id"),
            "model_id": effective.get("model_id"),
            "protocol": IMAGE_CONTRACT_VERSION,
            "capability_version": IMAGES_CAPABILITY_VERSION,
            "configured": bool(effective.get("configured")),
            "credential_source": effective.get("credential_source"),
            "capabilities": provider_capabilities(provider),
        }
        block["default_trial"] = default_trial_state()
        return block

    def _image_provider(self) -> tuple[Any, dict[str, Any]]:
        """图像有效元组：同一解析供提交/状态/结果共用；BYOK 只在本次请求内存里。"""

        from src.providers.v2_image import ImageFailure

        try:
            return self._effective_image()
        except ImageFailure:
            raise
        except Exception as error:  # noqa: BLE001 - 构造失败 = 明确的未配置，而不是 500
            raise ImageFailure(
                "internal", "PROVIDER_NOT_CONFIGURED",
                "图像 provider 不可用：检查注册表、依赖与 DASHSCOPE_API_KEY。",
                retry_policy="fatal", http_status=503,
                details={"kind": _provider_error_kind(error),
                         "detail": redact(type(error).__name__ + ": " + str(error))}) from None

    def _verify_execution_target(self, request: Any, provider: Any, *,
                                 effective: dict[str, Any] | None = None) -> None:
        """按冻结身份核对目标（V2.R4.4/R6.0）：不匹配就 400，绝不转发到别的目标。

        已提交任务保留原协议/目标/模型/能力版本；原任务核对走请求头选中的原目标
        provider（请求头带原 provider id），不偷用新动作模型查旧任务。target 缺省
        （老验证工具）保持既有语义。credential_source 随 target 一起发送时才核对
        （缺省跳过）；失配即 400 CREDENTIAL_REFERENCE_MISMATCH，不调用模型。
        """
        from src.providers.v2_image import (
            EXECUTION_PROTOCOL_PATTERN, IMAGE_CONTRACT_VERSION, IMAGES_CAPABILITY_VERSION,
            ImageFailure,
        )
        target = getattr(request, "target", None)
        if target is None:
            return
        expected = (str(getattr(provider, "provider_id", "")),
                    str(getattr(provider, "model_id", "")),
                    IMAGE_CONTRACT_VERSION, IMAGES_CAPABILITY_VERSION)
        actual = (str(target.provider_id), str(target.model_id),
                  str(target.protocol), target.capability_version)
        if not EXECUTION_PROTOCOL_PATTERN.fullmatch(actual[2]):
            raise ImageFailure("input_rejected", "EXECUTION_IDENTITY_MISMATCH",
                               "冻结执行身份的协议版本不合法；没有调用模型。",
                               retry_policy="fatal", http_status=400)
        if expected[:3] != actual[:3] or expected[3] != actual[3]:
            raise ImageFailure(
                "input_rejected", "EXECUTION_IDENTITY_MISMATCH",
                "冻结执行身份与当前图像网关不一致：已提交任务按原身份核对；"
                "本次请求没有转发、没有调用模型。",
                retry_policy="fatal", http_status=400,
                details={"frozen_target": {"provider_id": actual[0], "model_id": actual[1],
                                           "protocol": actual[2],
                                           "capability_version": actual[3]},
                         "current_target": {"provider_id": expected[0],
                                            "model_id": expected[1],
                                            "protocol": expected[2],
                                            "capability_version": expected[3]}})
        wanted = getattr(target, "credential_source", None)
        if wanted is not None:
            current_source = (effective or {}).get("credential_source", getattr(
                provider, "credential_source", None))
            if wanted != current_source:
                raise ImageFailure(
                    "input_rejected", "CREDENTIAL_REFERENCE_MISMATCH",
                    "冻结凭据引用与当前有效凭据不一致：请用原目标的凭据重带请求头；"
                    "本次请求没有转发、没有调用模型。",
                    retry_policy="fatal", http_status=400,
                    details={"frozen_credential_source": wanted,
                             "current_credential_source": current_source})

    def _image_request(self, model: Any, *,
                       max_bytes: int = MAX_BODY_BYTES) -> tuple[Any, int, dict[str, Any] | None]:
        """读体 + 契约校验；返回 (request, status, error_payload)。错误时 request 为 None。"""

        from pydantic import ValidationError

        body, status, payload = self._read_body(max_bytes)
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

    def _verify_request_profile(self, request: Any, provider: Any) -> None:
        """按 resolved provider 的 request_profile 前置核验（V2.R5.3）。

        非法 = INPUT_INVALID/400，不调用模型、不输出秘密（原因只含计数与参数名）。
        缺 profile 或 profile 不完整 = 同样拒绝（no readiness），不猜 qwen、不回退。
        """
        from src.providers.v2_image import ImageFailure, profile_violation

        capabilities = provider_capabilities(provider)
        profile = capabilities.get("request_profile")
        if profile is None:
            raise ImageFailure("input_rejected", "INPUT_INVALID",
                               "当前 provider 没有可用的 request_profile；不能确认请求是否在其能力内。",
                               retry_policy="fatal", http_status=400)
        reason = profile_violation(request, profile)
        if reason is not None:
            raise ImageFailure("input_rejected", "INPUT_INVALID", reason + "这次没有调用模型。",
                               retry_policy="fatal", http_status=400)

    def _image_failure_response(self, failure: Any) -> None:
        self._send_json(status_for_failure(failure), {
            "ok": False,
            "unknown": bool(getattr(failure, "unknown", False)),
            "error": failure.to_dict(),
        })

    def _images_submit(self) -> None:
        from src.providers.v2_image import ImageFailure, SubmitRequest

        request, status, payload = self._image_request(
            SubmitRequest, max_bytes=MAX_IMAGE_BODY_BYTES)
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            provider, effective = self._image_provider()
            self._verify_execution_target(request, provider, effective=effective)
            self._verify_request_profile(request, provider)
            task = provider.submit(request)
        except ImageFailure as failure:
            self._image_failure_response(failure)
            return
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            self._send_json(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
            return
        payload = {"ok": True, "unknown": False, "task": task.to_dict()}
        sync_block = self._sync_image_envelope(task)
        if sync_block:
            payload.update(sync_block)
        self._send_json(200, payload)

    def _sync_image_envelope(self, task: Any) -> dict[str, Any] | None:
        """同步协议（V2.R5.2）：结果字节一次性随提交信封回浏览器。

        字节只进这一次响应体，不写盘、不进日志、不进第二次响应；浏览器用
        ``image_sha256`` 独立复核字节（不靠服务端口头声明）。没有同步结果就返回
        None，继续用异步三段链的原样响应。
        """
        sync_result = getattr(task, "sync_result", None)
        if not sync_result:
            return None
        content, media_type = sync_result
        if not isinstance(content, bytes) or not content:
            return None
        return {
            "image_base64": base64.b64encode(content).decode("ascii"),
            "image_media_type": media_type,
            "image_sha256": hashlib.sha256(content).hexdigest(),
        }

    def _images_status(self) -> None:
        from src.providers.v2_image import ImageFailure, TaskRequest

        request, status, payload = self._image_request(TaskRequest)
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            provider, effective = self._image_provider()
            self._verify_execution_target(request, provider, effective=effective)
            task = provider.status(request)
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
            provider, effective = self._image_provider()
            self._verify_execution_target(request, provider, effective=effective)
            content, media_type = provider.result(request)
        except ImageFailure as failure:
            self._image_failure_response(failure)
            return
        except Exception as error:  # noqa: BLE001
            self._send_json(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
            return
        self._send_bytes(200, content, media_type, (
            ("X-Image-Sha256", hashlib.sha256(content).hexdigest()),
            ("X-Provider-Id", str(getattr(provider, "provider_id", ""))),
            ("X-Model-Id", str(getattr(provider, "model_id", ""))),
            ("X-Task-Id", request.task_id),
        ))

    def _analyze(self) -> None:
        try:
            from src.providers.v2_semantic import (
                MAX_VISION_IMAGES,
                MAX_VISION_IMAGE_BYTES,
                SemanticFailure,
                decode_vision_images,
                parse_request,
                problems_from_parse_error,
            )
        except Exception as error:  # noqa: BLE001
            self._send_json(503, provider_unavailable_payload(
                "dependency", redact(type(error).__name__ + ": " + str(error))))
            return
        # 语义分析支持纯文本与看图两种有效配置：请求头选用途 provider，
        # 看图配置才接受 reference_images 图片字节（decode+复算哈希后才出网）。
        # 三张 4MiB 图的 base64 上界 + 原文字元数据余量；单图/合计/哈希仍由合同校验。
        max_body_bytes = MAX_BODY_BYTES + MAX_VISION_IMAGES * 4 * ((MAX_VISION_IMAGE_BYTES + 2) // 3)
        body, status, payload = self._read_body(max_body_bytes)
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, input_rejected_payload("请求体不是合法 JSON。"))
            return
        raw_vision = decoded.get("reference_images") if isinstance(decoded, Mapping) else None
        if raw_vision is None:
            vision_items: list[Any] = []
        elif isinstance(raw_vision, list):
            vision_items = list(raw_vision)
        else:
            self._send_json(400, input_rejected_payload(
                "reference_images 必须是数组；没有调用模型。"))
            return
        base_payload = dict(decoded) if isinstance(decoded, Mapping) else {}
        base_payload.pop("reference_images", None)
        try:
            request = parse_request(base_payload)
        except Exception as error:  # noqa: BLE001 - 契约问题一律归 input_rejected
            try:
                problems = problems_from_parse_error(error)
            except Exception:  # noqa: BLE001
                problems = None
            self._send_json(400, input_rejected_payload(
                "请求字段不符合语义请求契约；没有调用模型。", problems))
            return
        try:
            provider, _effective = self._effective_semantic()
        except SemanticFailure as failure:
            self._send_json(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
            return
        except Exception as error:  # noqa: BLE001
            self._send_json(503, provider_unavailable_payload(
                _provider_error_kind(error),
                redact(type(error).__name__ + ": " + str(error))))
            return
        sees_images = bool(getattr(provider, "supports_images", False))
        if vision_items and not sees_images:
            self._send_json(400, input_rejected_payload(
                "当前语义模型不支持图片字节：纯文本配置收到 reference_images；没有调用模型。"))
            return
        if sees_images and not vision_items:
            self._send_json(400, {
                "ok": False,
                "unknown": False,
                "error": {
                    "family": "input_rejected",
                    "code": "VISION_BYTES_REQUIRED",
                    "message": "看图理解需要至少一张已校验的参考图字节（reference_images 1..3 张）；"
                    "这次请求没有调用模型。",
                    "retry_policy": "fatal",
                    "http_status": 400,
                    "request_id": None,
                    "details": None,
                },
            })
            return
        images: tuple[Any, ...] = ()
        if sees_images:
            if len(vision_items) > MAX_VISION_IMAGES:
                self._send_json(400, input_rejected_payload(
                    f"reference_images 一次最多 {MAX_VISION_IMAGES} 张；没有调用模型。"))
                return
            try:
                images = decode_vision_images(vision_items)
            except ValueError as error:
                self._send_json(400, input_rejected_payload(
                    str(error)[:200] + "没有调用模型。"))
                return
            except Exception as error:  # noqa: BLE001
                try:
                    problems = problems_from_parse_error(error)
                except Exception:  # noqa: BLE001
                    problems = None
                self._send_json(400, input_rejected_payload(
                    "reference_images 不满足看图契约；没有调用模型。", problems))
                return
        try:
            if sees_images:
                proposal = provider.analyze(request, images)
            else:
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

    # ---------------------------------------------------------- VLM 复核（V2.5.2）

    def _review_capabilities(self) -> dict[str, Any]:
        from src.providers.v2_review import REVIEW_CONTRACT_VERSION

        block: dict[str, Any] = {
            "contract": REVIEW_CONTRACT_VERSION,
            "endpoint": REVIEW_PATH,
            "provider": {"provider_id": None, "model_id": None,
                         "configured": False, "capabilities": {}},
            "unavailable": None,
        }
        try:
            provider, effective = self._effective_review()
        except Exception as error:  # noqa: BLE001 - 能力查询必须给出可用性而不是 5xx
            block["unavailable"] = {
                "kind": _provider_error_kind(error),
                "detail": redact(type(error).__name__ + ": " + str(error)),
            }
            return block
        block["provider"] = {
            "provider_id": effective.get("provider_id"),
            "model_id": effective.get("model_id"),
            "protocol": effective.get("protocol"),
            "configured": bool(effective.get("configured")),
            "credential_source": effective.get("credential_source"),
            "capabilities": provider_capabilities(provider),
        }
        return block

    def _review(self) -> None:
        """一次无状态复核：请求进 → 结构化风险提示出；服务器不保存图片、不保存结果。"""

        from src.providers.v2_review import parse_review_request
        from src.providers.v2_semantic import SemanticFailure, problems_from_parse_error

        body, status, payload = self._read_body(MAX_REVIEW_BODY_BYTES)
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, input_rejected_payload("请求体不是合法 JSON。"))
            return
        try:
            request = parse_review_request(decoded)
        except SemanticFailure as failure:
            self._send_json(status_for_failure(failure),
                            {"ok": False, "unknown": False, "error": failure.to_dict()})
            return
        except Exception as error:  # noqa: BLE001 - 契约问题一律归 input_rejected
            try:
                problems = problems_from_parse_error(error)
            except Exception:  # noqa: BLE001
                problems = None
            self._send_json(400, input_rejected_payload(
                "复核请求字段不符合契约；没有调用模型。", problems))
            return
        try:
            provider, _effective = self._effective_review()
        except SemanticFailure as failure:
            self._send_json(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
            return
        except Exception as error:  # noqa: BLE001
            self._send_json(503, provider_unavailable_payload(
                _provider_error_kind(error),
                redact(type(error).__name__ + ": " + str(error))))
            return
        try:
            result = provider.review(request)
        except SemanticFailure as failure:
            self._send_json(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
            return
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            self._send_json(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
            return
        self._send_json(200, {"ok": True, "unknown": False, "result": result.to_dict()})

    # ---------------------------------------------------- 整套复核（V2.5.5，跨图）

    def _suite_review_capabilities(self) -> dict[str, Any]:
        from src.providers.v2_suite_review import MAX_SUITE_IMAGES, SUITE_REVIEW_CONTRACT_VERSION

        block: dict[str, Any] = {
            "contract": SUITE_REVIEW_CONTRACT_VERSION,
            "endpoint": SUITE_REVIEW_PATH,
            "max_images": MAX_SUITE_IMAGES,
            "provider": {"provider_id": None, "model_id": None,
                         "configured": False, "capabilities": {}},
            "unavailable": None,
        }
        try:
            provider, effective = self._effective_review(suite=True)
        except Exception as error:  # noqa: BLE001 - 能力查询必须给出可用性而不是 5xx
            block["unavailable"] = {
                "kind": _provider_error_kind(error),
                "detail": redact(type(error).__name__ + ": " + str(error)),
            }
            return block
        block["provider"] = {
            "provider_id": effective.get("provider_id"),
            "model_id": effective.get("model_id"),
            "protocol": effective.get("protocol"),
            "configured": bool(effective.get("configured")),
            "credential_source": effective.get("credential_source"),
            "capabilities": provider_capabilities(provider),
        }
        return block

    def _suite_review(self) -> None:
        """一次无状态整套复核：多张已采用图进 → 跨图提示出；服务器不保存图片、不保存结果。"""

        from src.providers.v2_semantic import SemanticFailure, problems_from_parse_error
        from src.providers.v2_suite_review import parse_suite_review_request

        body, status, payload = self._read_body(MAX_SUITE_REVIEW_BODY_BYTES)
        if payload is not None:
            self._send_json(status, payload)
            return
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, input_rejected_payload("请求体不是合法 JSON。"))
            return
        try:
            request = parse_suite_review_request(decoded)
        except SemanticFailure as failure:
            self._send_json(status_for_failure(failure),
                            {"ok": False, "unknown": False, "error": failure.to_dict()})
            return
        except Exception as error:  # noqa: BLE001 - 契约问题一律归 input_rejected
            try:
                problems = problems_from_parse_error(error)
            except Exception:  # noqa: BLE001
                problems = None
            self._send_json(400, input_rejected_payload(
                "整套复核请求字段不符合契约；没有调用模型。", problems))
            return
        try:
            provider, _effective = self._effective_review(suite=True)
        except SemanticFailure as failure:
            self._send_json(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
            return
        except Exception as error:  # noqa: BLE001
            self._send_json(503, provider_unavailable_payload(
                _provider_error_kind(error),
                redact(type(error).__name__ + ": " + str(error))))
            return
        try:
            result = provider.review(request)
        except SemanticFailure as failure:
            self._send_json(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
            return
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            self._send_json(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
            return
        self._send_json(200, {"ok": True, "unknown": False, "result": result.to_dict()})


def create_product_v2_server(host: str = "127.0.0.1", port: int = 8780,
                             provider_factory: Callable[[], Any] | None = None,
                             image_provider_factory: Callable[[], Any] | None = None,
                             review_provider_factory: Callable[[], Any] | None = None,
                             suite_review_provider_factory: Callable[[], Any] | None = None,
                             ) -> ThreadingHTTPServer:
    """建服务器但不启动；host 由调用方决定（本机默认回环，内网穿透时自行显式放开）。"""
    server = ThreadingHTTPServer((host, port), ProductV2Handler)
    server.provider_factory = provider_factory or default_provider_factory
    server.image_provider_factory = image_provider_factory or default_image_provider_factory
    server.review_provider_factory = review_provider_factory or default_review_provider_factory
    server.suite_review_provider_factory = (suite_review_provider_factory
                                            or default_suite_review_provider_factory)
    return server


def run_self_check() -> int:
    """正式入口自检：静态资源可取、两个无状态 API 行为正确、失败被分类、越权路径被拒。"""
    import http.client
    import io
    import socket

    from PIL import Image

    from src.providers.v2_fake_image import FakeImageProvider
    from src.providers.v2_fake_review import FakeReviewProvider
    from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider
    from src.providers.v2_fake_semantic import FakeSemanticProvider
    from src.providers.v2_semantic import MAX_VISION_IMAGE_BYTES, MAX_VISION_IMAGES

    mode = {"value": "fake"}
    vision_calls = {"count": 0}

    class VisionFakeProvider(FakeSemanticProvider):
        supports_images = True

        def analyze(self, request, images):
            vision_calls["count"] += 1
            return super().analyze(request)

    def factory():
        if mode["value"] == "broken":
            raise RuntimeError("自检：语义 provider 构造失败")
        if mode["value"] == "vision":
            return VisionFakeProvider(scenario="ok")
        return FakeSemanticProvider(scenario="ok")

    def image_factory():
        if mode["value"] == "broken":
            raise RuntimeError("自检：图像 provider 构造失败")
        return FakeImageProvider(scenario="ok")

    def review_factory():
        if mode["value"] == "broken":
            raise RuntimeError("自检：复核 provider 构造失败")
        return FakeReviewProvider(scenario="ok")

    def suite_factory():
        if mode["value"] == "broken":
            raise RuntimeError("自检：整套复核 provider 构造失败")
        return FakeSuiteReviewProvider(scenario="ok")

    server = create_product_v2_server("127.0.0.1", 0, provider_factory=factory,
                                      image_provider_factory=image_factory,
                                      review_provider_factory=review_factory,
                                      suite_review_provider_factory=suite_factory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    checks: list[tuple[str, bool, str]] = []

    def request(method: str, path: str, body: bytes | None = None) -> tuple[int, str, bytes]:
        # 连续起停回环端口时，极少数情况下连接会在读响应时被重置（Windows 上观察到一次）。
        # 自检是无状态、不落盘的，连接级错误重试一次；第二次仍失败才算真失败。
        last_error: Exception | None = None
        for _attempt in range(2):
            connection = http.client.HTTPConnection(host, port, timeout=20)
            try:
                headers = ({"Content-Type": "application/json; charset=utf-8"}
                           if body is not None else {})
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                return response.status, response.getheader("Content-Type") or "", response.read()
            except (ConnectionError, OSError) as error:
                last_error = error
            finally:
                connection.close()
        raise last_error if last_error else RuntimeError("自检请求失败。")

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
        check("正式入口返回 HTML 文档", status == 200 and "text/html" in ctype,
              f"status={status} type={ctype}")

        for asset, expect in (("/app.js", "javascript"), ("/styles.css", "css"),
                              ("/storage/index.js", "javascript"),
                              ("/domain/attempt.js", "javascript")):
            status, ctype, _ = request("GET", asset)
            check(f"产品资源 {asset}", status == 200 and expect in ctype,
                  f"status={status} type={ctype}")

        status, ctype, body = request("GET", "/api/health")
        health = json_body(body) if status == 200 else {}
        check("健康检查表明服务器无业务状态", status == 200 and health.get("product") == "v2"
              and health.get("server_state") == "none", f"status={status} body={health}")

        for path in ("/harness/storage-contract.html", "/api/workspaces/recent",
                     "/api/workspace?directory=C%3A%5CUsers", "/evals/probes/project_state.py",
                     "/domain/attempt.ts", "/domain/config-export.ts",
                     "/domain/type-contracts.d.ts"):
            status, _, _ = request("GET", path)
            check(f"正式入口不外放：{path}", status == 404, f"status={status}")

        for path in ("/../README.md", "/%2e%2e/README.md", "/storage/../../app/server.py"):
            status, _, _ = request("GET", path)
            check(f"目录逃逸被拒：{path}", status == 404, f"status={status}")

        # 连接复用：产品按 HTTP/1.1 保持连接，因此每条响应必须自带 Content-Length，
        # 且没读完正文的请求必须关掉连接——否则残留字节会被当成下一条请求错解。
        connection = http.client.HTTPConnection(host, port, timeout=20)
        try:
            reused: list[tuple[int, str]] = []
            for _ in range(2):
                connection.request("GET", "/api/health")
                response = connection.getresponse()
                reused.append((response.status, response.getheader("Content-Length") or ""))
                response.read()
            check("同一连接连续两次请求都按序返回（连接复用）",
                  all(status == 200 and length.isdigit() for status, length in reused),
                  f"{reused}")
        finally:
            connection.close()

        connection = http.client.HTTPConnection(host, port, timeout=20)
        try:
            connection.request("POST", "/api/v2/not-a-route", body=b"{}",
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            status = response.status
            close_header = (response.getheader("Connection") or "").lower()
            response.read()
            # http.client 会因为 Connection: close 直接丢掉 socket；否则由读端确认对端已关闭。
            closed = connection.sock is None or connection.sock.recv(1) == b""
            check("未知 POST 路由回 404 且关闭留有未读正文的连接",
                  status == 404 and close_header == "close" and closed,
                  f"status={status} connection={close_header} closed={closed}")
        finally:
            connection.close()

        # 将异常正文及下一条合法请求一起送达，验证只返回一份有界响应后关闭连接；
        # 不能只断言首个状态码，否则残留正文被当成新请求的故障仍会漏过。
        for method, path, framing, status in (
            ("POST", ANALYZE_PATH, "Transfer-Encoding: chunked", 400),
            ("POST", ANALYZE_PATH, "Transfer-Encoding: chunked\r\nContent-Length: 0", 400),
            ("POST", ANALYZE_PATH, "", 400),
            ("GET", "/api/health", "Transfer-Encoding: chunked", 200),
            ("GET", "/api/health", "Content-Length: invalid", 200),
        ):
            with socket.create_connection((host, port), timeout=5) as connection:
                connection.settimeout(5)
                wire = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
                        + (f"{framing}\r\n" if framing else "")
                        + "Connection: keep-alive\r\n\r\n2\r\n{}\r\n0\r\n\r\n"
                        + "GET /api/health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                connection.sendall(wire.encode("ascii"))
                received = bytearray()
                eof = False
                try:
                    while len(received) < 65536:
                        part = connection.recv(8192)
                        if not part:
                            eof = True
                            break
                        received.extend(part)
                except socket.timeout:
                    pass
            head, separator, response_body = bytes(received).partition(b"\r\n\r\n")
            headers = dict(line.lower().split(b":", 1) for line in head.split(b"\r\n")[1:]
                           if b":" in line)
            declared = headers.get(b"content-length", b"").strip()
            bounded = declared.isdigit() and len(response_body) == int(declared)
            check(f"{method} {framing or '无 Content-Length'} 拒绝复用未读正文",
                  head.startswith(f"HTTP/1.1 {status} ".encode("ascii"))
                  and bool(separator) and headers.get(b"connection", b"").strip() == b"close"
                  and bounded and eof,
                  f"bounded={bounded} eof={eof} bytes={len(received)} headers={head!r}")

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

        analyze_limit = MAX_BODY_BYTES + MAX_VISION_IMAGES * 4 * ((MAX_VISION_IMAGE_BYTES + 2) // 3)
        oversized = json.dumps({"product_name": "x" * (analyze_limit + 512)}).encode("utf-8")
        status, _, body = request("POST", ANALYZE_PATH, oversized)
        payload = json_body(body)
        check("超过理解路由传输上限被拒且返回实际字节边界",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected"
              and payload.get("error", {}).get("details", {}).get("problems")
              == {"content_length": len(oversized), "limit": analyze_limit},
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

        with io.BytesIO() as buffer:
            Image.new("RGB", (512, 512), color=(64, 96, 128)).save(buffer, format="PNG", compress_level=0)
            vision_bytes = buffer.getvalue()
        vision_digest = hashlib.sha256(vision_bytes).hexdigest()
        vision_metadata = {"sha256": vision_digest, "media_type": "image/png", "role": "primary"}
        vision_input = json.loads(analyze_body)
        vision_input["references"] = [vision_metadata]
        vision_input["reference_images"] = [{
            **vision_metadata, "data_base64": base64.b64encode(vision_bytes).decode("ascii"),
        }]
        vision_body = json.dumps(vision_input).encode("utf-8")
        mode["value"] = "vision"
        status, _, body = request("POST", ANALYZE_PATH, vision_body)
        payload = json_body(body)
        check("合法大图理解不受旧文字256KB传输上限阻断",
              len(vision_body) > MAX_BODY_BYTES and status == 200
              and payload.get("ok") is True and vision_calls["count"] == 1,
              f"status={status} bytes={len(vision_body)}")

        vision_input["reference_images"][0]["sha256"] = "b" * 64
        status, _, body = request("POST", ANALYZE_PATH, json.dumps(vision_input).encode("utf-8"))
        payload = json_body(body)
        check("大图身份哈希不符仍在模型调用前拒绝",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected"
              and vision_calls["count"] == 1, f"status={status} calls={vision_calls['count']}")

        too_large_image = vision_bytes + bytes(MAX_VISION_IMAGE_BYTES + 1 - len(vision_bytes))
        vision_input["reference_images"][0] = {
            **vision_metadata, "sha256": hashlib.sha256(too_large_image).hexdigest(),
            "data_base64": base64.b64encode(too_large_image).decode("ascii"),
        }
        status, _, body = request("POST", ANALYZE_PATH, json.dumps(vision_input).encode("utf-8"))
        payload = json_body(body)
        check("单图字节越界仍在模型调用前拒绝",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected"
              and vision_calls["count"] == 1, f"status={status} calls={vision_calls['count']}")
        mode["value"] = "fake"

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
        review_body = json.dumps({
            "candidate": {"media_type": "image/png",
                          "sha256": hashlib.sha256(sample_png).hexdigest(),
                          "data_base64": base64.b64encode(sample_png).decode("ascii")},
            "references": [],
            "shot": {"title": "自检主图", "purpose": "白底展示商品",
                     "keep_items": ["商品外观"], "allow_changes": ["背景"]},
            "platform": "amazon_us",
            "product_facts": [{"label": "材质", "value": "玻璃"}],
        }, ensure_ascii=False).encode("utf-8")
        sample_b64 = base64.b64encode(sample_png).decode("ascii")
        suite_body = json.dumps({
            "platform": "amazon_us",
            "locale": "zh-CN",
            "style_summary": "自检公共风格：白底、柔和阴影。",
            "product_facts": [{"label": "材质", "value": "玻璃"}],
            "images": [
                {"shot_id": "shot_a", "title": "自检主图", "purpose": "白底展示商品",
                 "keep_items": ["商品外观"], "allow_changes": ["背景"],
                 "image": {"media_type": "image/png",
                           "sha256": hashlib.sha256(sample_png).hexdigest(),
                           "data_base64": sample_b64}},
                {"shot_id": "shot_b", "title": "自检场景图", "purpose": "生活场景",
                 "keep_items": ["商品外观"], "allow_changes": ["背景"],
                 "image": {"media_type": "image/png",
                           "sha256": hashlib.sha256(sample_png).hexdigest(),
                           "data_base64": sample_b64}},
            ],
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

        status, _, body = request("GET", CAPABILITIES_PATH)
        payload = json_body(body)
        review_block = payload.get("review") or {}
        check("capabilities 暴露 VLM 复核（合同、端点、provider 与参考图能力）",
              payload.get("ok") is True
              and review_block.get("provider", {}).get("configured") is True
              and review_block.get("provider", {}).get("model_id") == "fake-qwen-vl-max"
              and review_block.get("endpoint") == REVIEW_PATH
              and review_block.get("provider", {}).get("capabilities", {}).get("reference_images") is True,
              f"review={review_block.get('provider')}")

        status, _, body = request("POST", REVIEW_PATH, review_body)
        payload = json_body(body)
        result = payload.get("result") or {}
        check("复核路由（fake provider）返回绑定候选 sha256 的发现且不含采纳结论",
              status == 200 and payload.get("ok") is True and payload.get("unknown") is False
              and result.get("candidate_sha256") == hashlib.sha256(sample_png).hexdigest()
              and len(result.get("findings") or []) >= 1
              and all(item.get("check") for item in result.get("findings") or [])
              and "accept" not in json.dumps(result, ensure_ascii=False).lower(),
              f"status={status} findings={len(result.get('findings') or [])}")

        status, _, body = request("GET", CAPABILITIES_PATH)
        payload = json_body(body)
        suite_block = payload.get("suite_review") or {}
        check("capabilities 暴露整套复核（合同、端点、张数上限与 provider）",
              payload.get("ok") is True
              and suite_block.get("provider", {}).get("configured") is True
              and suite_block.get("endpoint") == SUITE_REVIEW_PATH
              and suite_block.get("max_images") == 8
              and suite_block.get("provider", {}).get("model_id") == "fake-qwen-vl-max",
              f"suite_review={suite_block.get('provider')}")

        status, _, body = request("POST", SUITE_REVIEW_PATH, suite_body)
        payload = json_body(body)
        result = payload.get("result") or {}
        sent = {"shot_a", "shot_b"}
        check("整套复核路由（fake provider）只给送审集合内提示且不含严重度/采纳结论",
              status == 200 and payload.get("ok") is True and payload.get("unknown") is False
              and result.get("checked_shot_ids") == ["shot_a", "shot_b"]
              and result.get("state") == "checked"
              and all(set(item.get("shot_ids") or []) <= sent
                      for item in (result.get("findings") or []))
              and "block" not in json.dumps(result, ensure_ascii=False).lower(),
              f"status={status} findings={len(result.get('findings') or [])}")

        bad_suite = json.loads(suite_body.decode("utf-8"))
        bad_suite["images"][1]["image"]["sha256"] = "0" * 64
        status, _, body = request("POST", SUITE_REVIEW_PATH,
                                  json.dumps(bad_suite, ensure_ascii=False).encode("utf-8"))
        payload = json_body(body)
        check("整套复核图片哈希与字节不一致 → input_rejected/400（不调用模型）",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected",
              f"status={status} error={payload.get('error')}")

        bad_review = json.loads(review_body.decode("utf-8"))
        bad_review["candidate"]["sha256"] = "0" * 64
        status, _, body = request("POST", REVIEW_PATH,
                                  json.dumps(bad_review, ensure_ascii=False).encode("utf-8"))
        payload = json_body(body)
        check("复核图片哈希与字节不一致 → input_rejected/400（不调用模型）",
              status == 400 and payload.get("error", {}).get("family") == "input_rejected",
              f"status={status} error={payload.get('error')}")

        mode["value"] = "broken"
        status, _, body = request("GET", CAPABILITIES_PATH)
        payload = json_body(body)
        check("复核 provider 不可用时 capabilities 仍 200 且 configured=false",
              status == 200
              and (payload.get("review") or {}).get("provider", {}).get("configured") is False
              and (((payload.get("review") or {}).get("unavailable") or {}).get("kind")
                   in ("registry", "dependency")),
              f"review={(payload.get('review') or {}).get('unavailable')}")
        status, _, body = request("POST", REVIEW_PATH, review_body)
        payload = json_body(body)
        check("复核 provider 不可用时复核路由 503 且错误分类明确",
              status == 503 and payload.get("error", {}).get("code") == "PROVIDER_NOT_CONFIGURED"
              and payload.get("unknown") is False,
              f"status={status} error={payload.get('error')}")
        status, _, body = request("GET", CAPABILITIES_PATH)
        payload = json_body(body)
        check("整套复核 provider 不可用时 capabilities 仍 200 且 configured=false",
              status == 200
              and (payload.get("suite_review") or {}).get("provider", {}).get("configured") is False
              and (((payload.get("suite_review") or {}).get("unavailable") or {}).get("kind")
                   in ("registry", "dependency")),
              f"suite_review={(payload.get('suite_review') or {}).get('unavailable')}")
        status, _, body = request("POST", SUITE_REVIEW_PATH, suite_body)
        payload = json_body(body)
        check("整套复核 provider 不可用时路由 503 且错误分类明确",
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
