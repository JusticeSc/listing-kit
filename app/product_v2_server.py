"""Product V2 无状态 HTTP 网关（FastAPI/Uvicorn，P3）。

职责边界：
  - 只服务唯一静态构建产物 ``dist/product-v2``，以及无状态 API：
    ``GET /api/health``、``GET /api/v2/capabilities``、``POST /api/v2/semantic/analyze``、
    图像网关三段 ``images/submit|status|result``、单图复核 ``review/candidate`` 与
    整套复核 ``review/suite``（复核只产生风险提示，不产生人工采纳）。
  - 不接收、不保存任何用户工作空间路径；没有文件夹工作空间、没有最近项目索引，
    没有任何请求字段会被当作本机目录读取。
  - 用户项目、图片与历史全部由浏览器 IndexedDB 持有；本进程只读自己的安装目录。
  - 语义 provider 由 ``config/product-v2/providers.json`` + 环境变量选择
    （见 ``src/providers/v2_registry.py``）；没有密钥或依赖时返回明确的分类错误，不假装成功。
  - 连接/协议/并发/退出交给 ``app/product_v2_http.py`` 的 ASGI 宿主；本模块只保留
    产品政策：逐路由正文上限、错误分类、默认关闭、请求级凭据、出站白名单与 Unknown 语义。
  - 同步 Provider 一律在 worker 线程执行（``run_in_threadpool``），不阻塞事件循环；
    每次请求都新建 provider 实例，服务端不保存任务表。
  - 测试装置（``evals/...``）不经正式入口对外服务。

证据入口：``python app/server.py --check``（轻量真实健康检查；完整场景矩阵在
``tests/dev/test_selfcheck_matrix.py``，网关合同在 ``tests/gateway/``）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect
from starlette.responses import Response

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.product_v2_http import (  # noqa: E402  （ROOT 先入 sys.path）
    ProductV2Server,
    StaticRootMissing,
    resolve_static_root,
    static_file_response,
)

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

RESPONSE_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}

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

    import os

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


# ---------------------------------------------------------------- 响应构造


def json_response(status: int, body: Any) -> Response:
    """产品 JSON 响应：固定 utf-8 JSON、no-store、nosniff。"""

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return bytes_response(status, payload, "application/json; charset=utf-8")


def bytes_response(status: int, payload: bytes, media_type: str,
                   extra_headers: tuple[tuple[str, str], ...] = ()) -> Response:
    headers = dict(RESPONSE_HEADERS)
    for name, value in extra_headers:
        headers[name] = value
    return Response(content=payload, status_code=status, media_type=media_type,
                    headers=headers)


def _not_found(path: str) -> Response:
    if path.startswith("/api/"):
        return json_response(404, {"ok": False, "error": "NOT_FOUND", "path": path})
    return bytes_response(404, b"not found", "text/plain; charset=utf-8")


# ---------------------------------------------------------------- 正文上限


def analyze_body_limit() -> int:
    """理解路由上限：原文字元数据余量 + 三张 4MiB 图的 base64 上界。"""

    from src.providers.v2_semantic import MAX_VISION_IMAGE_BYTES, MAX_VISION_IMAGES

    return MAX_BODY_BYTES + MAX_VISION_IMAGES * 4 * ((MAX_VISION_IMAGE_BYTES + 2) // 3)


async def read_bounded_body(request: Request, limit: int
                            ) -> tuple[bytes | None, int, dict[str, Any] | None]:
    """按声明长度真实读入正文；返回 (body, status, payload)，payload 非空即可直接响应。

    只接受明确 Content-Length（与旧网关一致，不解码 chunked）。超限时先把声明长度读完
    再回 400，浏览器 fetch 才不会丢掉这个 400；超过荒谬长度才提前收手。读不满的请求
    一律按 400 结束，不让残留字节被当成下一条请求。
    """

    headers = request.headers
    if headers.get("transfer-encoding") is not None:
        return None, 400, input_rejected_payload(
            "请求只支持合法的 Content-Length，不支持 Transfer-Encoding。")
    raw_length = headers.get("content-length")
    if raw_length is None or not str(raw_length).strip().isdigit():
        return None, 400, input_rejected_payload("请求必须带合法的 Content-Length。")
    length = int(str(raw_length).strip())
    if length <= 0:
        return None, 400, input_rejected_payload("请求体为空。")
    if length > limit:
        budget = min(length, DRAIN_ABSOLUTE_MAX)
        consumed = 0
        try:
            async for chunk in request.stream():
                consumed += len(chunk)
                if consumed >= budget:
                    break
        except ClientDisconnect:
            pass
        return None, 400, input_rejected_payload(
            f"请求体超过上限 {limit} 字节。",
            {"content_length": length, "limit": limit})
    chunks: list[bytes] = []
    received = 0
    try:
        async for chunk in request.stream():
            chunks.append(chunk)
            received += len(chunk)
            if received > length:
                break
    except ClientDisconnect:
        return None, 400, input_rejected_payload("请求体在读满之前就结束了。")
    body = b"".join(chunks)
    if len(body) != length:
        return None, 400, input_rejected_payload("请求体在读满之前就结束了。")
    return body, 200, None


# ---------------------------------------------------------------- 请求作用域


class ProviderFactories:
    """一次 app 装配期的四个 provider 工厂；显式注入只用于离线测试接缝。"""

    __slots__ = ("semantic", "image", "review", "suite_review")

    def __init__(self, semantic: Callable[[], Any] | None = None,
                 image: Callable[[], Any] | None = None,
                 review: Callable[[], Any] | None = None,
                 suite_review: Callable[[], Any] | None = None) -> None:
        self.semantic = semantic or default_provider_factory
        self.image = image or default_image_provider_factory
        self.review = review or default_review_provider_factory
        self.suite_review = suite_review or default_suite_review_provider_factory

    def all(self) -> tuple[Callable[[], Any], ...]:
        return (self.semantic, self.image, self.review, self.suite_review)


class _RequestScope:
    """单次请求的只读视图：请求头快照 + 装配期工厂；BYOK 只在本次请求内存里。"""

    def __init__(self, headers: Any, factories: ProviderFactories) -> None:
        items = headers.items() if hasattr(headers, "items") else headers
        self.headers = {str(key): str(value) for key, value in items}
        self.factories = factories

    @property
    def provider_factory(self) -> Callable[[], Any]:
        return self.factories.semantic

    @property
    def image_provider_factory(self) -> Callable[[], Any]:
        return self.factories.image

    @property
    def review_provider_factory(self) -> Callable[[], Any]:
        return self.factories.review

    @property
    def suite_review_provider_factory(self) -> Callable[[], Any]:
        return self.factories.suite_review

    @staticmethod
    def _is_default_factory(factory: Callable[[], Any], default: Callable[[], Any]) -> bool:
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

        headers = self.headers
        factory = self.provider_factory
        try:
            return resolve_effective(
                purpose="semantic", role="semantic",
                provider_header=SEMANTIC_PROVIDER_HEADER, key_header=SEMANTIC_KEY_HEADER,
                default_resolver=resolve_provider_id, create=create_semantic_provider,
                env=dict(__import__("os").environ), headers=headers, factory=factory,
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

        import os

        from src.providers.v2_image import ImageFailure
        from src.providers.v2_registry import (
            IMAGE_KEY_HEADER,
            IMAGE_PROVIDER_HEADER,
            create_image_provider,
            resolve_effective,
            resolve_image_provider_id,
        )

        headers = self.headers
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

        import os

        from src.providers.v2_registry import (
            REVIEW_KEY_HEADER,
            REVIEW_PROVIDER_HEADER,
            create_review_provider,
            create_suite_review_provider,
            resolve_effective,
            resolve_review_provider_id,
        )
        from src.providers.v2_semantic import SemanticFailure

        headers = self.headers
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

    # ------------------------------------------------------------ 能力投影

    def capabilities(self) -> Response:
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
            return json_response(200, payload)
        payload["provider"] = {
            "provider_id": effective.get("provider_id"),
            "model_id": effective.get("model_id"),
            "protocol": effective.get("protocol"),
            "capability_version": None,
            "configured": bool(effective.get("configured")),
            "credential_source": effective.get("credential_source"),
            "capabilities": provider_capabilities(_provider),
        }
        return json_response(200, payload)

    def _seam_ids(self) -> set[str]:
        """显式注入接缝的 active 身份：fake 只在该接缝的目录里可见，生产目录永不含 fake。"""

        found: set[str] = set()
        for factory in self.factories.all():
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

    # ------------------------------------------------------------ 图像网关

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

    def _image_request(self, model: Any, body: bytes) -> tuple[Any, Response | None]:
        """契约校验；返回 (request, error_response)。错误时 request 为 None。"""

        from pydantic import ValidationError

        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, json_response(400, input_rejected_payload("请求体不是合法 JSON。"))
        try:
            return model.model_validate(decoded), None
        except ValidationError as error:
            problems = [{"path": ".".join(str(part) for part in item.get("loc", ())),
                         "message": str(item.get("msg"))}
                        for item in error.errors()[:6]]
            return None, json_response(400, input_rejected_payload(
                "请求字段不符合图像网关契约；没有调用模型。", problems))

    @staticmethod
    def _image_failure_response(failure: Any) -> Response:
        return json_response(status_for_failure(failure), {
            "ok": False,
            "unknown": bool(getattr(failure, "unknown", False)),
            "error": failure.to_dict(),
        })

    def images_submit(self, body: bytes) -> Response:
        from src.providers.v2_image import ImageFailure, SubmitRequest

        request, error = self._image_request(SubmitRequest, body)
        if error is not None:
            return error
        try:
            provider, effective = self._image_provider()
            self._verify_execution_target(request, provider, effective=effective)
            self._verify_request_profile(request, provider)
            task = provider.submit(request)
        except ImageFailure as failure:
            return self._image_failure_response(failure)
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            return json_response(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
        payload = {"ok": True, "unknown": False, "task": task.to_dict()}
        sync_block = self._sync_image_envelope(task)
        if sync_block:
            payload.update(sync_block)
        return json_response(200, payload)

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

    def images_status(self, body: bytes) -> Response:
        from src.providers.v2_image import ImageFailure, TaskRequest

        request, error = self._image_request(TaskRequest, body)
        if error is not None:
            return error
        try:
            provider, effective = self._image_provider()
            self._verify_execution_target(request, provider, effective=effective)
            task = provider.status(request)
        except ImageFailure as failure:
            return self._image_failure_response(failure)
        except Exception as error:  # noqa: BLE001
            return json_response(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
        return json_response(200, {"ok": True, "unknown": False, "task": task.to_dict()})

    def images_result(self, body: bytes) -> Response:
        from src.providers.v2_image import ImageFailure, TaskRequest

        request, error = self._image_request(TaskRequest, body)
        if error is not None:
            return error
        try:
            provider, effective = self._image_provider()
            self._verify_execution_target(request, provider, effective=effective)
            content, media_type = provider.result(request)
        except ImageFailure as failure:
            return self._image_failure_response(failure)
        except Exception as error:  # noqa: BLE001
            return json_response(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
        return bytes_response(200, content, media_type, (
            ("X-Image-Sha256", hashlib.sha256(content).hexdigest()),
            ("X-Provider-Id", str(getattr(provider, "provider_id", ""))),
            ("X-Model-Id", str(getattr(provider, "model_id", ""))),
            ("X-Task-Id", request.task_id),
        ))

    # ------------------------------------------------------------ 语义分析

    def analyze(self, body: bytes) -> Response:
        try:
            from src.providers.v2_semantic import (
                MAX_VISION_IMAGES,
                SemanticFailure,
                decode_vision_images,
                parse_request,
                problems_from_parse_error,
            )
        except Exception as error:  # noqa: BLE001
            return json_response(503, provider_unavailable_payload(
                "dependency", redact(type(error).__name__ + ": " + str(error))))
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return json_response(400, input_rejected_payload("请求体不是合法 JSON。"))
        raw_vision = decoded.get("reference_images") if isinstance(decoded, Mapping) else None
        if raw_vision is None:
            vision_items: list[Any] = []
        elif isinstance(raw_vision, list):
            vision_items = list(raw_vision)
        else:
            return json_response(400, input_rejected_payload(
                "reference_images 必须是数组；没有调用模型。"))
        base_payload = dict(decoded) if isinstance(decoded, Mapping) else {}
        base_payload.pop("reference_images", None)
        try:
            request = parse_request(base_payload)
        except Exception as error:  # noqa: BLE001 - 契约问题一律归 input_rejected
            try:
                problems = problems_from_parse_error(error)
            except Exception:  # noqa: BLE001
                problems = None
            return json_response(400, input_rejected_payload(
                "请求字段不符合语义请求契约；没有调用模型。", problems))
        try:
            provider, _effective = self._effective_semantic()
        except SemanticFailure as failure:
            return json_response(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
        except Exception as error:  # noqa: BLE001
            return json_response(503, provider_unavailable_payload(
                _provider_error_kind(error),
                redact(type(error).__name__ + ": " + str(error))))
        sees_images = bool(getattr(provider, "supports_images", False))
        if vision_items and not sees_images:
            return json_response(400, input_rejected_payload(
                "当前语义模型不支持图片字节：纯文本配置收到 reference_images；没有调用模型。"))
        if sees_images and not vision_items:
            return json_response(400, {
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
        images: tuple[Any, ...] = ()
        if sees_images:
            if len(vision_items) > MAX_VISION_IMAGES:
                return json_response(400, input_rejected_payload(
                    f"reference_images 一次最多 {MAX_VISION_IMAGES} 张；没有调用模型。"))
            try:
                images = decode_vision_images(vision_items)
            except ValueError as error:
                return json_response(400, input_rejected_payload(
                    str(error)[:200] + "没有调用模型。"))
            except Exception as error:  # noqa: BLE001
                try:
                    problems = problems_from_parse_error(error)
                except Exception:  # noqa: BLE001
                    problems = None
                return json_response(400, input_rejected_payload(
                    "reference_images 不满足看图契约；没有调用模型。", problems))
        try:
            if sees_images:
                proposal = provider.analyze(request, images)
            else:
                proposal = provider.analyze(request)
        except SemanticFailure as failure:
            return json_response(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            return json_response(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
        return json_response(200, {"ok": True, "unknown": False, "proposal": proposal.to_dict()})

    # ------------------------------------------------------------ 单图复核

    def review(self, body: bytes) -> Response:
        """一次无状态复核：请求进 → 结构化风险提示出；服务器不保存图片、不保存结果。"""

        from src.providers.v2_review import parse_review_request
        from src.providers.v2_semantic import SemanticFailure, problems_from_parse_error

        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return json_response(400, input_rejected_payload("请求体不是合法 JSON。"))
        try:
            request = parse_review_request(decoded)
        except SemanticFailure as failure:
            return json_response(status_for_failure(failure),
                                 {"ok": False, "unknown": False, "error": failure.to_dict()})
        except Exception as error:  # noqa: BLE001 - 契约问题一律归 input_rejected
            try:
                problems = problems_from_parse_error(error)
            except Exception:  # noqa: BLE001
                problems = None
            return json_response(400, input_rejected_payload(
                "复核请求字段不符合契约；没有调用模型。", problems))
        try:
            provider, _effective = self._effective_review()
        except SemanticFailure as failure:
            return json_response(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
        except Exception as error:  # noqa: BLE001
            return json_response(503, provider_unavailable_payload(
                _provider_error_kind(error),
                redact(type(error).__name__ + ": " + str(error))))
        try:
            result = provider.review(request)
        except SemanticFailure as failure:
            return json_response(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            return json_response(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
        return json_response(200, {"ok": True, "unknown": False, "result": result.to_dict()})

    # ------------------------------------------------------------ 整套复核

    def suite_review(self, body: bytes) -> Response:
        """一次无状态整套复核：多张已采用图进 → 跨图提示出；服务器不保存图片与结果。"""

        from src.providers.v2_semantic import SemanticFailure, problems_from_parse_error
        from src.providers.v2_suite_review import parse_suite_review_request

        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return json_response(400, input_rejected_payload("请求体不是合法 JSON。"))
        try:
            request = parse_suite_review_request(decoded)
        except SemanticFailure as failure:
            return json_response(status_for_failure(failure),
                                 {"ok": False, "unknown": False, "error": failure.to_dict()})
        except Exception as error:  # noqa: BLE001 - 契约问题一律归 input_rejected
            try:
                problems = problems_from_parse_error(error)
            except Exception:  # noqa: BLE001
                problems = None
            return json_response(400, input_rejected_payload(
                "整套复核请求字段不符合契约；没有调用模型。", problems))
        try:
            provider, _effective = self._effective_review(suite=True)
        except SemanticFailure as failure:
            return json_response(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
        except Exception as error:  # noqa: BLE001
            return json_response(503, provider_unavailable_payload(
                _provider_error_kind(error),
                redact(type(error).__name__ + ": " + str(error))))
        try:
            result = provider.review(request)
        except SemanticFailure as failure:
            return json_response(status_for_failure(failure), {
                "ok": False,
                "unknown": getattr(failure, "family", None) == "provider_unknown",
                "error": failure.to_dict(),
            })
        except Exception as error:  # noqa: BLE001 - 未分类异常不冒充 provider 结果
            return json_response(500, internal_error_payload(
                redact(type(error).__name__ + ": " + str(error))))
        return json_response(200, {"ok": True, "unknown": False, "result": result.to_dict()})


# ---------------------------------------------------------------- app 装配


def _scope(request: Request, factories: ProviderFactories) -> _RequestScope:
    return _RequestScope(request.headers.items(), factories)


def _validation_problems(error: RequestValidationError) -> list[dict[str, Any]]:
    """只保留位置与原因；绝不回显原始输入（可能含参考图字节或密钥）。"""

    problems: list[dict[str, Any]] = []
    for item in error.errors()[:6]:
        problems.append({"path": ".".join(str(part) for part in item.get("loc", ())),
                         "message": str(item.get("msg"))})
    return problems


def create_app(*, provider_factory: Callable[[], Any] | None = None,
               image_provider_factory: Callable[[], Any] | None = None,
               review_provider_factory: Callable[[], Any] | None = None,
               suite_review_provider_factory: Callable[[], Any] | None = None,
               static_dir: Path | str | None = None) -> FastAPI:
    """装配产品 ASGI 应用；静态根缺省为唯一构建产物 ``dist/product-v2``。"""

    static_root = resolve_static_root(static_dir)
    factories = ProviderFactories(provider_factory, image_provider_factory,
                                 review_provider_factory, suite_review_provider_factory)
    app = FastAPI(title="AMZ Listing Kit Product V2", docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.static_root = static_root
    app.state.provider_factories = factories

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, error: RequestValidationError) -> Response:
        return json_response(400, input_rejected_payload(
            "请求字段不符合接口契约；没有调用模型。", _validation_problems(error)))

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, error: StarletteHTTPException) -> Response:
        # 旧网关把未知路由与不支持的方法都收敛成 404；这里保持同一可见结果，
        # 且不回显框架默认 detail（可能带模板化路径信息）。
        if error.status_code in (404, 405):
            return _not_found(request.url.path)
        return json_response(error.status_code, failure_payload(
            "input_rejected" if error.status_code < 500 else "internal",
            "HTTP_ERROR", redact(str(error.detail)), retry_policy="fatal"))

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, error: Exception) -> Response:
        # 最后一道防线：响应形状仍是产品错误信封，消息经脱敏，不含请求正文。
        return json_response(500, internal_error_payload(
            redact(type(error).__name__ + ": " + str(error))))

    @app.get("/api/health")
    async def health() -> Response:
        return json_response(200, HEALTH)

    @app.get(CAPABILITIES_PATH)
    async def capabilities(request: Request) -> Response:
        return await run_in_threadpool(_scope(request, factories).capabilities)

    @app.post(ANALYZE_PATH)
    async def analyze(request: Request) -> Response:
        body, status, payload = await read_bounded_body(request, analyze_body_limit())
        if payload is not None:
            return json_response(status, payload)
        return await run_in_threadpool(_scope(request, factories).analyze, body)

    @app.post(IMAGE_SUBMIT_PATH)
    async def images_submit(request: Request) -> Response:
        body, status, payload = await read_bounded_body(request, MAX_IMAGE_BODY_BYTES)
        if payload is not None:
            return json_response(status, payload)
        return await run_in_threadpool(_scope(request, factories).images_submit, body)

    @app.post(IMAGE_STATUS_PATH)
    async def images_status(request: Request) -> Response:
        body, status, payload = await read_bounded_body(request, MAX_BODY_BYTES)
        if payload is not None:
            return json_response(status, payload)
        return await run_in_threadpool(_scope(request, factories).images_status, body)

    @app.post(IMAGE_RESULT_PATH)
    async def images_result(request: Request) -> Response:
        body, status, payload = await read_bounded_body(request, MAX_BODY_BYTES)
        if payload is not None:
            return json_response(status, payload)
        return await run_in_threadpool(_scope(request, factories).images_result, body)

    @app.post(REVIEW_PATH)
    async def review(request: Request) -> Response:
        body, status, payload = await read_bounded_body(request, MAX_REVIEW_BODY_BYTES)
        if payload is not None:
            return json_response(status, payload)
        return await run_in_threadpool(_scope(request, factories).review, body)

    @app.post(SUITE_REVIEW_PATH)
    async def suite_review(request: Request) -> Response:
        body, status, payload = await read_bounded_body(request, MAX_SUITE_REVIEW_BODY_BYTES)
        if payload is not None:
            return json_response(status, payload)
        return await run_in_threadpool(_scope(request, factories).suite_review, body)

    @app.get("/{path:path}")
    async def static_or_not_found(request: Request, path: str) -> Response:  # noqa: ARG001
        url_path = request.url.path
        if url_path.startswith("/api/"):
            return _not_found(url_path)
        target = "/index.html" if url_path in ("/", "/index.html", "/product") else url_path
        response = static_file_response(static_root, target)
        return response if response is not None else _not_found(url_path)

    @app.post("/{path:path}")
    async def post_not_found(request: Request) -> Response:
        return _not_found(request.url.path)

    return app


def create_product_v2_server(host: str = "127.0.0.1", port: int = 8780, *,
                             provider_factory: Callable[[], Any] | None = None,
                             image_provider_factory: Callable[[], Any] | None = None,
                             review_provider_factory: Callable[[], Any] | None = None,
                             suite_review_provider_factory: Callable[[], Any] | None = None,
                             static_dir: Path | str | None = None) -> ProductV2Server:
    """构造（并真实绑定端口）但未启动；host 由调用方决定。"""

    app = create_app(provider_factory=provider_factory,
                     image_provider_factory=image_provider_factory,
                     review_provider_factory=review_provider_factory,
                     suite_review_provider_factory=suite_review_provider_factory,
                     static_dir=static_dir)
    return ProductV2Server(app, host, port)


# ---------------------------------------------------------------- 生产轻量自检


def run_self_check() -> int:
    """正式入口轻量自检：真实 TCP 健康检查 + 唯一构建产物可取。

    完整场景矩阵（假 provider、理解/复核/整套复核、拒绝矩阵）是开发验证，位于
    ``tests/dev/test_selfcheck_matrix.py`` 与 ``tests/gateway/``；生产自检不导入
    任何测试替身，也不依赖 Pillow。
    """

    import http.client

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    try:
        server = create_product_v2_server("127.0.0.1", 0)
    except StaticRootMissing as error:
        print(f"  FAIL  唯一静态产物  {error}")
        print("V2 正式入口轻量自检：0/1 通过（先构建前端产物）。")
        return 2
    server.start()

    def request(method: str, path: str) -> tuple[int, str, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=20)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.getheader("Content-Type") or "", response.read()
        finally:
            connection.close()

    try:
        status, ctype, body = request("GET", "/api/health")
        try:
            health = json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            health = {}
        check("健康检查表明服务器无业务状态",
              status == 200 and health.get("product") == "v2"
              and health.get("server_state") == "none",
              f"status={status} body={health}")
        status, ctype, _ = request("GET", "/")
        check("唯一静态产物首页可取", status == 200 and "text/html" in ctype,
              f"status={status} type={ctype}")
        status, _, _ = request("GET", "/api/v2/not-a-route")
        check("未知 API 路由 404（不猜测业务）", status == 404, f"status={status}")
    finally:
        server.stop()

    width = max(len(name) for name, _, _ in checks)
    failed = 0
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
        failed += not ok
    print(f"V2 正式入口轻量自检：{len(checks) - failed}/{len(checks)} 通过。"
          "（完整场景矩阵在 tests/dev 与 tests/gateway）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run_self_check())
