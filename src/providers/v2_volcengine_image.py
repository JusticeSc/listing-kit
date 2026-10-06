#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Product V2 图像网关的真实适配器：大陆火山方舟 doubao-seedream-5-0-flash-260915（V2.R5.2）。

协议事实（官方来源，见 evals/product-v2/refactor/two-image-adapters-*.md）：
  - 同步接口：``POST {base}/api/v3/images/generations``；请求体 ``{model, prompt, image[], size,
    response_format, output_format, watermark, background}``；响应 200 且 ``data[]`` 带图。
  - 没有 task id / status 链：提交即拿到结果，同步超时/5xx 之后没有权威对账，只能记 Unknown
    并禁止自动重提；**不得伪造 provider task id**（计划 §V2.R5.2）。
  - 默认档与响应口径按产品合同收敛：``response_format=b64_json``（杀 url 24h TTL 这一类
    时效性载体）、``output_format=png``（网关只收 PNG）、``watermark=false``（主图要求）。
  - flash 的 sequential/stream/组图不在产品合同内：请求体里**不发送**这些键，不发未经
    官方证实的可选字段。

与 DashScope 适配器的关系：目的/能力/凭据各管各的；本适配器不做任务表、不下载结果 URL
（b64 模式不需要），也不复用百炼的签名地址校验。所有上下文与字段在进程内，密钥不进日志、
不进证据、不进错误消息。
"""
from __future__ import annotations

import base64
import binascii
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests

from src.providers import is_arrears_provider_code
from src.providers.v2_image import (DEFAULT_SIZE, FLASH_MIN_AREA, IMAGE_CONTRACT_VERSION,
                                    ImageFailure, ImageTaskResult, SubmitRequest, TaskRequest,
                                    image_request_profile)
from src.providers.v2_outbound import (DEFAULT_ALLOWED_HOSTS,
                                       OutboundPolicyError, validate_outbound_url)

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
CREATE_PATH = "/images/generations"
DEFAULT_API_KEY_ENV = "ARK_API_KEY"
DEFAULT_BASE_URL_ENV = "AMZ_V2_ARK_BASE_URL"
DEFAULT_TIMEOUT_ENV = "AMZ_V2_ARK_TIMEOUT"

VOLCENGINE_PROVIDER_ID = "volcengine-ark"
VOLCENGINE_MODEL_ID = "doubao-seedream-5-0-flash-260915"

# 同步适配器的默认超时放宽：同步接口一次请求直接等图；产品网关三层（提交/查询/取回）
# 里只有提交这一层有真实外呼，超时成本与上游生图时长同级。
DEFAULT_TIMEOUT_SECONDS = 90.0

_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg);base64,[A-Za-z0-9+/=.]+$")


class Transport(Protocol):
    def request(self, method: str, url: str, *, headers: Mapping[str, str],
                json: Mapping[str, Any] | None, timeout: float,
                allow_redirects: bool) -> Any: ...


def _requests_transport(method: str, url: str, *, headers: Mapping[str, str],
                        json: Mapping[str, Any] | None, timeout: float,
                        allow_redirects: bool) -> Any:
    return requests.request(method, url, headers=dict(headers), json=json,
                            timeout=timeout, allow_redirects=allow_redirects)


class _FunctionTransport:
    """把「函数式」HTTP 传输规范化成 Transport 协议对象（验证器注入用）。"""

    def __init__(self, function) -> None:
        self._function = function

    def request(self, method: str, url: str, *, headers: Mapping[str, str],
                json: Mapping[str, Any] | None, timeout: float,
                allow_redirects: bool) -> Any:
        return self._function(method, url, headers=headers, json=json,
                              timeout=timeout, allow_redirects=allow_redirects)


def _as_transport(transport: Transport | None) -> Transport:
    if transport is None:
        return _FunctionTransport(_requests_transport)
    if hasattr(transport, "request"):
        return transport
    return _FunctionTransport(transport)


def _status_code(response: Any) -> int:
    try:
        return int(response.status_code)
    except (AttributeError, TypeError, ValueError):
        return 0


def _payload(response: Any) -> Mapping[str, Any] | None:
    try:
        value = response.json()
    except (AttributeError, ValueError):
        return None
    return value if isinstance(value, Mapping) else None


def _request_id(response: Any, payload: Mapping[str, Any] | None) -> str | None:
    headers = getattr(response, "headers", {}) or {}
    if isinstance(headers, Mapping):
        for name, value in headers.items():
            if str(name).lower() == "x-request-id":
                if isinstance(value, str) and _REQUEST_ID_RE.fullmatch(value.strip()):
                    return value.strip()
    if payload:
        candidate = payload.get("id")
        if isinstance(candidate, str) and _REQUEST_ID_RE.fullmatch(candidate.strip()):
            return candidate.strip()
    return None


def _provider_error_code(payload: Mapping[str, Any] | None) -> str | None:
    if not payload:
        return None
    nested = payload.get("error")
    candidates = [nested.get("code") if isinstance(nested, Mapping) else None,
                  payload.get("code")]
    return next((value for value in candidates
                 if isinstance(value, str) and _SAFE_CODE_RE.fullmatch(value)), None)


def _safe_base_url(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip().rstrip("/")
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise ValueError("火山方舟端点不是合法 URL。") from None
    if (parsed.scheme != "https"
            or not (host == "volces.com" or host.endswith(".volces.com"))
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443) or parsed.query or parsed.fragment):
        raise ValueError("火山方舟端点必须是 volces.com HTTPS 端点。")
    return raw


def _decode_b64_images(payload: Mapping[str, Any] | None) -> tuple[bytes, ...]:
    data = payload.get("data") if payload else None
    if not isinstance(data, list):
        return ()
    chunks: list[bytes] = []
    for item in data:
        encoded = item.get("b64_json") if isinstance(item, Mapping) else None
        if isinstance(encoded, str) and encoded.strip():
            try:
                chunks.append(base64.b64decode(encoded, validate=True))
            except (binascii.Error, ValueError):
                continue
    return tuple(chunks)


class VolcengineImageProvider:
    """同步图像适配器：一次调用只有一个语义（提交→拿结果字节），没有任务表也没有轮询。"""

    def __init__(self, *, api_key: str | None = None, base_url: str | None = DEFAULT_BASE_URL,
                 model_id: str = VOLCENGINE_MODEL_ID, provider_id: str = VOLCENGINE_PROVIDER_ID,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS, transport: Transport | None = None,
                 allowed_hosts: Sequence[str] | None = None,
                 credential_source: str | None = None) -> None:
        resolved_source = credential_source or "env"
        if resolved_source == "none":
            self.api_key = ""
        elif api_key is None:
            self.api_key = os.getenv(DEFAULT_API_KEY_ENV, "")
        else:
            self.api_key = api_key.strip() if isinstance(api_key, str) else ""
        self.credential_source = resolved_source
        self.allowed_hosts = tuple(allowed_hosts) if allowed_hosts else DEFAULT_ALLOWED_HOSTS
        self.base_url = _safe_base_url(base_url)
        self.model_id = model_id.strip() if isinstance(model_id, str) else ""
        self.provider_id = provider_id.strip() if isinstance(provider_id, str) else ""
        try:
            self.timeout = float(timeout)
        except (TypeError, ValueError):
            raise ValueError("火山方舟超时必须是正数。") from None
        if self.timeout <= 0:
            raise ValueError("火山方舟超时必须是正数。")
        self._transport = _as_transport(transport)

    # ------------------------------------------------------------ 能力与就绪

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def capabilities(self) -> dict[str, Any]:
        return {
            "contract": IMAGE_CONTRACT_VERSION,
            "reference_images": True,
            "max_reference_images": 3,
            "async_tasks": False,
            "sync_tasks": True,
            "n_per_submit": 1,
            "prompt_extend": False,
            "watermark": False,
            "stateless": True,
            "test_double": False,
            "size": DEFAULT_SIZE,
            "credential_source": self.credential_source,
            # V2.R5.3 非秘密请求 profile：flash 官方像素面积下界 921600（父级官源核对），
            # 其余沿用产品保守限制，不扩张为官源全能力；BYOK/默认档不改变它。
            "request_profile": image_request_profile(min_area=FLASH_MIN_AREA),
        }

    def apply_credentials(self, *, api_key: str) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ImageFailure("input_rejected", "BYOK_CREDENTIAL_INVALID",
                               "BYOK 密钥为空或格式非法；这次请求不调用图像模型。",
                               retry_policy="fatal", http_status=400)
        self.api_key = api_key.strip()
        self.credential_source = "byok"

    def _ready(self) -> None:
        if not self.api_key:
            if self.credential_source == "none":
                raise ImageFailure(
                    "internal", "PROVIDER_NOT_CONFIGURED",
                    "默认档密钥处于关闭状态（或未配置密钥）；部署侧显式打开默认档，"
                    "或用 BYOK 请求头带上自己的密钥。没有调用图像模型。",
                    retry_policy="fatal", http_status=503)
            raise ImageFailure("internal", "PROVIDER_NOT_CONFIGURED",
                               f"未配置 {DEFAULT_API_KEY_ENV}，没有调用图像模型。",
                               retry_policy="fatal", http_status=503)
        if not self.base_url:
            raise ImageFailure("internal", "PROVIDER_NOT_CONFIGURED",
                               "未配置火山方舟服务端点。", retry_policy="fatal", http_status=503)

    def _call(self, operation: str, method: str, url: str, *,
              headers: Mapping[str, str], json_body: Mapping[str, Any] | None) -> Any:
        try:
            validate_outbound_url(url, allowed_hosts=self.allowed_hosts, label=operation)
        except OutboundPolicyError as error:
            raise ImageFailure(
                "internal", "OUTBOUND_POLICY_REJECTED",
                "出站地址不满足白名单策略；这次操作没有发出去，也不会自动重试。",
                retry_policy="fatal", http_status=503,
                details={"reason": error.reason}) from None
        try:
            return self._transport.request(method, url, headers=headers, json=json_body,
                                           timeout=self.timeout, allow_redirects=False)
        except (requests.exceptions.Timeout, TimeoutError, requests.exceptions.RequestException,
                OSError) as error:
            raise ImageFailure(
                "provider_unknown", "PROVIDER_OUTCOME_UNKNOWN",
                f"同步{operation}的连接中断或超时，结果无法确认；没有可靠的核对途径，"
                "只能显式新建 action，不要自动重提。",
                retry_policy="requires_review",
                details={"kind": type(error).__name__}) from None

    def _upstream_failure(self, status_code: int, request_id: str | None,
                          provider_code: str | None) -> ImageFailure:
        suffix = f"（服务码 {provider_code}）" if provider_code else ""
        if status_code == 429:
            return ImageFailure(
                "provider_failed", "UPSTREAM_RATE_LIMITED",
                f"火山方舟暂时限流（HTTP 429）{suffix}；同步提交没有被受理，稍后可重试这张图。",
                retry_policy="retryable", http_status=429, request_id=request_id)
        if is_arrears_provider_code(provider_code):
            return ImageFailure(
                "provider_failed", "UPSTREAM_ACCOUNT_ARREARS",
                f"火山方舟账户欠费（服务码 {provider_code}）；提交没有被受理，充值后重试。",
                retry_policy="retryable", http_status=status_code, request_id=request_id)
        if 300 <= status_code < 500:
            return ImageFailure(
                "provider_failed", "UPSTREAM_REJECTED",
                f"火山方舟拒绝了提交请求（HTTP {status_code}）{suffix}。",
                retry_policy="fatal", http_status=status_code, request_id=request_id)
        return ImageFailure(
            "provider_unknown", "UPSTREAM_OUTCOME_UNKNOWN",
            f"同步提交响应异常（HTTP {status_code}），结果无法确认；没有可核对的 task id，"
            "只能显式新建 action。",
            retry_policy="requires_review", http_status=status_code, request_id=request_id)

    # ------------------------------------------------------------ 同步三态里的「一步」

    def submit(self, request: SubmitRequest) -> ImageTaskResult:
        self._ready()
        if request.model_id is not None and request.model_id != self.model_id:
            raise ImageFailure("input_rejected", "MODEL_UNSUPPORTED",
                               "本适配器只服务已注册的 doubao-seedream-5-0-flash-260915。",
                               retry_policy="fatal", http_status=400)
        if len(request.references) > self._max_reference_images():
            raise ImageFailure("input_rejected", "REFERENCE_LIMIT_EXCEEDED",
                               "参考图超过火山方舟 flash 的上限；这次没有调用模型。",
                               retry_policy="fatal", http_status=400)
        # V2.R5.3：flash 官方像素面积下界 921600（父级官源核对），与网关 profile 核验同步；
        # 其余尺寸限制由 Pydantic 网关共有限制执行，这里只补真正差异的下界。
        try:
            flash_width, flash_height = (int(value) for value in request.size.split("*", 1))
        except ValueError:
            raise ImageFailure("input_rejected", "INPUT_INVALID",
                               "图像尺寸不符合 request_profile 要求；这次没有调用模型。",
                               retry_policy="fatal", http_status=400) from None
        if flash_width * flash_height < FLASH_MIN_AREA:
            raise ImageFailure("input_rejected", "INPUT_INVALID",
                               "图像尺寸小于当前 provider 921600 像素下限；这次没有调用模型。",
                               retry_policy="fatal", http_status=400)
        # V2.R5.3：output_format/watermark 使用已校验冻结字段，不暗改配置。
        body: dict[str, Any] = {
            "model": self.model_id,
            "prompt": request.prompt,
            "size": request.size.replace("*", "x"),
            "response_format": "b64_json",
            "output_format": request.output_format,
            "watermark": request.watermark,
        }
        if request.references:
            images: list[str] = []
            for item in request.references:
                encoded = base64.b64encode(item.content()).decode("ascii")
                images.append(f"data:{item.media_type};base64,{encoded}")
            body["image"] = images
        response = self._call("同步图像生成", "POST", self.base_url + CREATE_PATH,
                              headers={"Authorization": f"Bearer {self.api_key}",
                                       "Content-Type": "application/json"},
                              json_body=body)
        status_code = _status_code(response)
        payload = _payload(response)
        request_id = _request_id(response, payload)
        if not 200 <= status_code < 300:
            raise self._upstream_failure(status_code, request_id,
                                         _provider_error_code(payload))
        if payload is None:
            raise ImageFailure("provider_unknown", "PROVIDER_OUTCOME_UNKNOWN",
                               "同步响应无法解析，结果无法确认；没有可核对的 task id，"
                               "只能显式新建 action。",
                               retry_policy="requires_review", request_id=request_id)
        chunks = _decode_b64_images(payload)
        if not chunks:
            raise ImageFailure("provider_failed", "UPSTREAM_EMPTY_RESULT",
                               "同步响应没有可用的图片数据（可能被内容安全拦截）；"
                               "这次提交没有产生可用结果。",
                               retry_policy="fatal", request_id=request_id)
        content = chunks[0]
        if not content.startswith(_PNG_SIGNATURE):
            raise ImageFailure("provider_failed", "RESULT_IMAGE_INVALID",
                               "模型返回的结果不是合同要求的 PNG 图片。",
                               retry_policy="fatal", request_id=request_id)
        return ImageTaskResult(
            provider_id=self.provider_id, model_id=self.model_id,
            task_id=None,  # 同步协议没有 task id；伪造是被明确禁止的（§V2.R5.2）。
            status="SUCCEEDED", result_count=1, request_id=request_id,
            unknown=False, sync_result=(content, "image/png"))

    # 同步协议没有 status / result：这两个路由对它没有意义，宁可公正拒绝也不猜。
    def status(self, request: TaskRequest) -> ImageTaskResult:
        raise ImageFailure("provider_unknown", "SYNC_TASK_ID_REQUIRED",
                           "同步协议没有 task 链：它的提交没有任务编号可查，"
                           "不能按任意 task id 核对这次请求。",
                           retry_policy="requires_review")

    def result(self, request: TaskRequest) -> tuple[bytes, str]:
        raise ImageFailure("provider_unknown", "SYNC_TASK_ID_REQUIRED",
                           "同步协议没有 task 链：结果字节在提交响应里一次性给出，"
                           "不能按任意 task id 重新取回。",
                           retry_policy="requires_review")

    def _max_reference_images(self) -> int:
        # 官方教程：flash 支持 ≤10 张参考图；产品合同上限是 3（MAX_REFERENCE_IMAGES 已校验），
        # 这里是真的上限声明而不做第二道合同。
        return 10


def create_default_volcengine_image_provider(*, environ: Mapping[str, str] | None = None,
                                             transport: Transport | None = None,
                                             timeout: float | None = None,
                                             base_url: str | None = None,
                                             byok_api_key: str | None = None
                                             ) -> VolcengineImageProvider:
    """按注册表口径构造真实适配器；构造过程不联网。

    密钥来源统一走 ``v2_credentials.resolve_credentials``：``api_key_env`` 与注册表
    ``volcengine-ark`` 条目一致（ARK_API_KEY）；``AMZ_V2_DEFAULT_TRIAL`` 未开时部署密钥不会
    进入适配器（fail-closed）。``allowed_hosts`` 复用 ``v2_outbound.DEFAULT_ALLOWED_HOSTS``
    （包含 volces.com）。
    """
    from src.providers.v2_credentials import resolve_credentials

    source = os.environ if environ is None else environ
    raw_timeout = source.get(DEFAULT_TIMEOUT_ENV)
    resolved_timeout = timeout
    if resolved_timeout is None:
        try:
            resolved_timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_SECONDS
        except ValueError:
            resolved_timeout = DEFAULT_TIMEOUT_SECONDS
    decision = resolve_credentials({"api_key_env": DEFAULT_API_KEY_ENV}, source, byok_api_key=byok_api_key)
    return VolcengineImageProvider(
        api_key=decision.api_key,
        base_url=base_url or source.get(DEFAULT_BASE_URL_ENV) or DEFAULT_BASE_URL,
        transport=transport, timeout=resolved_timeout, credential_source=decision.source)
