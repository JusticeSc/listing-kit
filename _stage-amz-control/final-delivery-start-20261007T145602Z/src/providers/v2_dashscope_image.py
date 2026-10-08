"""Product V2 图像网关的真实适配器：阿里云百炼 qwen-image-3.0（V2.4.1）。

协议知识不是新发明的：请求/查询/取回三段与 V1 ``src/providers/dashscope_image.py`` 同一套
冻结合同（异步提交头、任务查询 URL、结果地址白名单）。本文件只把它重新表达成 V2 的
分类合同（``ImageFailure`` 四类归口），并且：

  - 复用 ``requests``（已是锁定依赖），不引入第二套 HTTP 客户端；
  - transport 可注入，验证时用假 transport 断言请求形状，不需要联网；
  - 任何消息都不含提示词、图片字节、密钥或签名结果地址。
"""
from __future__ import annotations

import base64
import os
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

import requests

from src.providers import is_arrears_provider_code
from src.providers.v2_credentials import resolve_credentials
from src.providers.v2_image import (DEFAULT_SIZE, IMAGE_MODEL_ID, IMAGE_PROVIDER_ID,
                                    ImageFailure, ImageTaskResult, SubmitRequest,
                                    TaskRequest, image_request_profile)
from src.providers.v2_outbound import DEFAULT_ALLOWED_HOSTS, OutboundPolicyError, validate_outbound_url

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
CREATE_PATH = "/services/aigc/image-generation/generation"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL_ENV = "AMZ_V2_IMAGE_BASE_URL"
DEFAULT_TIMEOUT_ENV = "AMZ_V2_IMAGE_TIMEOUT"

_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
    """把「函数式」HTTP 传输规范化成 Transport 协议对象（默认 transport 就是一个函数）。"""

    __slots__ = ("_call",)

    def __init__(self, call: Callable[..., Any]) -> None:
        self._call = call

    def request(self, method: str, url: str, *, headers: Mapping[str, str],
                json: Mapping[str, Any] | None, timeout: float,
                allow_redirects: bool) -> Any:
        return self._call(method, url, headers=headers, json=json, timeout=timeout,
                          allow_redirects=allow_redirects)


def _as_transport(transport: Transport | None) -> Transport:
    """函数式与对象式传输都归一成带 ``request`` 的对象；默认走 ``_requests_transport``。"""

    if transport is None:
        return _FunctionTransport(_requests_transport)
    if callable(transport) and not hasattr(transport, "request"):
        return _FunctionTransport(transport)
    return transport


def _status_code(response: Any) -> int:
    try:
        return int(getattr(response, "status_code", 0))
    except (TypeError, ValueError):
        return 0


def _payload(response: Any) -> Mapping[str, Any] | None:
    try:
        value = response.json()
    except Exception:  # noqa: BLE001 - 解析失败按“状态未知”处理
        return None
    return value if isinstance(value, Mapping) else None


def _request_id(response: Any, payload: Mapping[str, Any] | None) -> str | None:
    headers = getattr(response, "headers", {}) or {}
    if isinstance(headers, Mapping):
        for name, value in headers.items():
            if str(name).lower() in {"x-request-id", "request-id", "x-dashscope-request-id"}:
                if isinstance(value, str) and _REQUEST_ID_RE.fullmatch(value.strip()):
                    return value.strip()
    if payload:
        candidate = payload.get("request_id") or payload.get("id")
        if isinstance(candidate, str) and _REQUEST_ID_RE.fullmatch(candidate.strip()):
            return candidate.strip()
    return None


def _provider_error_code(payload: Mapping[str, Any] | None) -> str | None:
    if not payload:
        return None
    nested = payload.get("error")
    candidates = [payload.get("code"), nested.get("code") if isinstance(nested, Mapping) else None]
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
        raise ValueError("图像端点不是合法 URL。") from None
    if (parsed.scheme != "https"
            or not (host == "aliyuncs.com" or host.endswith(".aliyuncs.com"))
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443) or parsed.query or parsed.fragment):
        raise ValueError("图像端点必须是阿里云 HTTPS 端点。")
    return raw


def valid_result_url(value: object) -> bool:
    """签名结果地址只允许阿里云 HTTPS 主机；其余一律不下载。"""

    if not isinstance(value, str) or not value or len(value) > 8192 or any(ord(c) < 32 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return False
    return (parsed.scheme == "https"
            and (host == "aliyuncs.com" or host.endswith(".aliyuncs.com"))
            and parsed.username is None and parsed.password is None and port in (None, 443))


def _result_urls(payload: Mapping[str, Any] | None) -> tuple[str, ...]:
    output = payload.get("output") if payload else None
    if not isinstance(output, Mapping):
        return ()
    candidates: list[object] = []
    choices = output.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            message = choice.get("message") if isinstance(choice, Mapping) else None
            content = message.get("content") if isinstance(message, Mapping) else None
            if isinstance(content, list):
                candidates.extend(part.get("image") for part in content if isinstance(part, Mapping))
    results = output.get("results")
    if isinstance(results, list):
        candidates.extend(item.get("url") for item in results if isinstance(item, Mapping))
    return tuple(dict.fromkeys(value for value in candidates if valid_result_url(value)))


class DashScopeImageProvider:
    """无状态图像网关适配器：一次调用只做一件事，不在进程里留任何任务状态。"""

    def __init__(self, *, api_key: str | None = None, base_url: str | None = DEFAULT_BASE_URL,
                 model_id: str = IMAGE_MODEL_ID, provider_id: str = IMAGE_PROVIDER_ID,
                 timeout: float = 30.0, transport: Transport | None = None,
                 allowed_hosts: Sequence[str] | None = None,
                 credential_source: str | None = None) -> None:
        # credential_source 由 v2_credentials.resolve_credentials 决定（V2.R4.3）：
        #   none    → 默认档被关闭，环境变量里有密钥也不带进适配器；
        #   default → 注册表口径的部署密钥（仅当 AMZ_V2_DEFAULT_TRIAL 显式开启）；
        #   byok    → 本次请求的浏览器内存密钥（apply_credentials 之后）；
        #   env     → 直接构造（验证器/探针）沿用旧口径：api_key is None 时读环境变量。
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
            raise ValueError("图像网关超时必须是正数。") from None
        if self.timeout <= 0:
            raise ValueError("图像网关超时必须是正数。")
        self._transport = _as_transport(transport)

    # ------------------------------------------------------------ 能力与就绪

    @property
    def configured(self) -> bool:
        """密钥与端点是真实调用前提；缺一即未配置（构造本身不报错）。"""

        return bool(self.api_key and self.base_url)

    def capabilities(self) -> dict[str, Any]:
        return {
            "contract": "v2.4.1",
            "reference_images": True,
            "max_reference_images": 3,
            "async_tasks": True,
            "n_per_submit": 1,
            "prompt_extend": False,
            "watermark": False,
            "stateless": True,
            "test_double": False,
            "size": DEFAULT_SIZE,
            "credential_source": self.credential_source,
            # V2.R5.3 非秘密请求 profile：纯业务投影，不含密钥；BYOK/默认档不改变它。
            "request_profile": image_request_profile(),
        }

    def apply_credentials(self, *, api_key: str) -> None:
        """把本次请求内存态的 BYOK 密钥换上；只影响当前实例，不写盘、不进日志。"""

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
                               "未配置图像模型服务端点。", retry_policy="fatal", http_status=503)

    def _call(self, operation: str, method: str, url: str, *,
              headers: Mapping[str, str], json_body: Mapping[str, Any] | None) -> Any:
        # 出站白名单在任何传输生效之前判定：非白名单/私网/非 https 一律不发。
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
                f"{operation}的连接中断或超时，远端结果无法确认；先核对，不要自动重提。",
                retry_policy="requires_review",
                details={"kind": type(error).__name__}) from None

    def _upstream_failure(self, operation: str, status_code: int,
                          request_id: str | None, provider_code: str | None) -> ImageFailure:
        suffix = f"（服务码 {provider_code}）" if provider_code else ""
        if status_code == 429:
            policy = "retryable" if operation.startswith("提交") else "requires_review"
            message = (f"百炼暂时限流（HTTP 429）{suffix}；"
                       + ("这次提交没有被受理，稍后可重试这张图。" if policy == "retryable"
                          else "结果暂时无法确认，请再次查询原任务。"))
            return ImageFailure("provider_failed", "UPSTREAM_RATE_LIMITED", message,
                                retry_policy=policy, http_status=429, request_id=request_id)
        if is_arrears_provider_code(provider_code):
            return ImageFailure(
                "provider_failed", "UPSTREAM_ACCOUNT_ARREARS",
                f"阿里云百炼账户欠费（服务码 {provider_code}）；{operation}没有被受理，充值后重试。",
                retry_policy="retryable", http_status=status_code, request_id=request_id)
        if 400 <= status_code < 500 or 300 <= status_code < 400:
            return ImageFailure(
                "provider_failed", "UPSTREAM_REJECTED",
                f"百炼拒绝了{operation}请求（HTTP {status_code}）{suffix}。",
                retry_policy="fatal", http_status=status_code, request_id=request_id)
        return ImageFailure(
            "provider_unknown", "UPSTREAM_OUTCOME_UNKNOWN",
            f"{operation}响应异常（HTTP {status_code}），远端结果无法确认。",
            retry_policy="requires_review", http_status=status_code, request_id=request_id)

    @staticmethod
    def _task(payload: Mapping[str, Any], *, provider_id: str, model_id: str,
              fallback_task_id: str | None, request_id: str | None) -> ImageTaskResult:
        output = payload.get("output")
        if not isinstance(output, Mapping):
            output = {}
        raw_id = output.get("task_id")
        task_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else fallback_task_id
        raw_status = output.get("task_status")
        status = raw_status.upper() if isinstance(raw_status, str) else "UNKNOWN"
        if status not in ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED"):
            status = "UNKNOWN"
        error = None
        if status == "FAILED":
            code = _provider_error_code(payload)
            error = "图像生成任务失败" + (f"（错误码 {code}）" if code else "") + "。"
        elif status == "UNKNOWN":
            error = "服务端返回的状态无法识别；请再次查询原任务确认结果。"
        urls = _result_urls(payload)
        return ImageTaskResult(
            provider_id=provider_id, model_id=model_id, task_id=task_id,
            status=status, result_count=len(urls), error=error, request_id=request_id,
            unknown=status == "UNKNOWN")

    # ------------------------------------------------------------ 三步

    def submit(self, request: SubmitRequest) -> ImageTaskResult:
        self._ready()
        if request.model_id is not None and request.model_id != self.model_id:
            raise ImageFailure("input_rejected", "MODEL_UNSUPPORTED",
                               "本适配器只服务已注册的 qwen-image-3.0。", retry_policy="fatal",
                               http_status=400)
        content: list[dict[str, str]] = []
        for item in request.references:
            encoded = base64.b64encode(item.content()).decode("ascii")
            content.append({"image": f"data:{item.media_type};base64,{encoded}"})
        content.append({"text": request.prompt})
        # V2.R5.3：实际 body 使用已校验冻结字段，不暗改配置（Pydantic 已拒绝非法值）。
        parameters: dict[str, Any] = {"size": request.size, "n": request.n,
                                      "prompt_extend": request.prompt_extend,
                                      "watermark": request.watermark}
        if request.seed is not None:
            parameters["seed"] = request.seed
        body = {
            "model": self.model_id,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }
        response = self._call("提交图像任务", "POST", self.base_url + CREATE_PATH,
                              headers={"Authorization": f"Bearer {self.api_key}",
                                       "Content-Type": "application/json",
                                       "X-DashScope-Async": "enable"},
                              json_body=body)
        status_code = _status_code(response)
        payload = _payload(response)
        request_id = _request_id(response, payload)
        if not 200 <= status_code < 300:
            raise self._upstream_failure("提交图像任务", status_code, request_id,
                                         _provider_error_code(payload))
        if payload is None:
            raise ImageFailure("provider_unknown", "PROVIDER_OUTCOME_UNKNOWN",
                               "提交响应无法解析，服务端是否受理无法确认；先核对，不要自动重提。",
                               retry_policy="requires_review", request_id=request_id)
        task = self._task(payload, provider_id=self.provider_id, model_id=self.model_id,
                          fallback_task_id=None, request_id=request_id)
        if not task.task_id:
            raise ImageFailure("provider_unknown", "PROVIDER_OUTCOME_UNKNOWN",
                               "提交响应没有可核对的任务编号；先核对，不要自动重提。",
                               retry_policy="requires_review", request_id=request_id)
        return task

    def status(self, request: TaskRequest) -> ImageTaskResult:
        self._ready()
        response = self._call("任务查询", "GET",
                              self.base_url + "/tasks/" + quote(request.task_id, safe=""),
                              headers={"Authorization": f"Bearer {self.api_key}"}, json_body=None)
        status_code = _status_code(response)
        payload = _payload(response)
        request_id = _request_id(response, payload)
        if not 200 <= status_code < 300:
            raise self._upstream_failure("任务查询", status_code, request_id,
                                         _provider_error_code(payload))
        if payload is None:
            raise ImageFailure("provider_unknown", "PROVIDER_STATUS_UNKNOWN",
                               "查询响应无法解析，任务状态尚未确认；请再次查询原任务。",
                               retry_policy="requires_review", request_id=request_id)
        output = payload.get("output")
        returned = output.get("task_id") if isinstance(output, Mapping) else None
        if isinstance(returned, str) and returned.strip() and returned.strip() != request.task_id:
            raise ImageFailure("provider_unknown", "PROVIDER_TASK_MISMATCH",
                               "查询响应里的任务编号与请求不一致；请核对原任务。",
                               retry_policy="requires_review", request_id=request_id)
        return self._task(payload, provider_id=self.provider_id, model_id=self.model_id,
                          fallback_task_id=request.task_id, request_id=request_id)

    def result(self, request: TaskRequest) -> tuple[bytes, str]:
        """先查权威状态，再按任务返回的第一张结果下载；签名地址只在本进程内使用。"""

        self._ready()
        response = self._call("任务查询", "GET",
                              self.base_url + "/tasks/" + quote(request.task_id, safe=""),
                              headers={"Authorization": f"Bearer {self.api_key}"}, json_body=None)
        status_code = _status_code(response)
        payload = _payload(response)
        request_id = _request_id(response, payload)
        if not 200 <= status_code < 300:
            raise self._upstream_failure("任务查询", status_code, request_id,
                                         _provider_error_code(payload))
        if payload is None:
            raise ImageFailure("provider_unknown", "PROVIDER_STATUS_UNKNOWN",
                               "结果取回前无法确认任务状态；请再次查询原任务。",
                               retry_policy="requires_review", request_id=request_id)
        task = self._task(payload, provider_id=self.provider_id, model_id=self.model_id,
                          fallback_task_id=request.task_id, request_id=request_id)
        if task.status != "SUCCEEDED":
            raise ImageFailure("provider_failed", "TASK_NOT_SUCCEEDED",
                               f"任务当前状态是 {task.status}，没有可下载的结果。",
                               retry_policy="retryable" if task.status in ("PENDING", "RUNNING")
                               else "fatal", request_id=request_id)
        urls = _result_urls(payload)
        if not urls:
            raise ImageFailure("provider_failed", "RESULT_URL_MISSING",
                               "任务成功但没有受信的结果地址。", retry_policy="fatal",
                               request_id=request_id)
        response = self._call("结果图片下载", "GET", urls[0],
                              headers={"Accept": "image/png"}, json_body=None)
        status_code = _status_code(response)
        download_request_id = _request_id(response, None) or request_id
        if not 200 <= status_code < 300:
            failure = self._upstream_failure("结果图片下载", status_code, download_request_id, None)
            if failure.family == "provider_failed" and failure.retry_policy == "fatal":
                failure = ImageFailure("provider_failed", "RESULT_DOWNLOAD_REJECTED",
                                       "结果图片地址被拒绝（通常是签名已过期）；重新查询原任务即可。",
                                       retry_policy="retryable", http_status=status_code,
                                       request_id=download_request_id)
            raise failure
        content = getattr(response, "content", None)
        headers = getattr(response, "headers", {}) or {}
        media_type = ""
        if isinstance(headers, Mapping):
            raw = next((str(value) for name, value in headers.items()
                        if str(name).lower() == "content-type"), "")
            media_type = raw.split(";", 1)[0].strip().lower()
        if (not isinstance(content, bytes) or not content.startswith(_PNG_SIGNATURE)
                or media_type not in {"", "application/octet-stream", "image/png"}):
            raise ImageFailure("provider_failed", "RESULT_IMAGE_INVALID",
                               "模型返回的结果不是合同要求的 PNG 图片。", retry_policy="fatal",
                               request_id=download_request_id)
        return content, "image/png"


def create_default_image_provider(*, environ: Mapping[str, str] | None = None,
                                  transport: Transport | None = None,
                                  timeout: float | None = None,
                                  base_url: str | None = None,
                                  byok_api_key: str | None = None) -> DashScopeImageProvider:
    """按注册表口径构造真实适配器；构造过程不联网。

    密钥来源统一走 ``v2_credentials.resolve_credentials``：``api_key_env`` 与注册表
    ``dashscope-qwen-image`` 条目一致（DASHSCOPE_API_KEY）；``AMZ_V2_DEFAULT_TRIAL`` 未开
    时部署密钥不会进入适配器（fail-closed）。 ``allowed_hosts`` 复用
    ``v2_outbound.DEFAULT_ALLOWED_HOSTS``（DashScope/结果地址共用的 aliyuncs.com 白名单）。
    """

    source = os.environ if environ is None else environ
    raw_timeout = source.get(DEFAULT_TIMEOUT_ENV)
    resolved_timeout = timeout
    if resolved_timeout is None:
        try:
            resolved_timeout = float(raw_timeout) if raw_timeout else 30.0
        except ValueError:
            resolved_timeout = 30.0
    decision = resolve_credentials({"api_key_env": DEFAULT_API_KEY_ENV}, source, byok_api_key=byok_api_key)
    return DashScopeImageProvider(
        api_key=decision.api_key,
        base_url=base_url or source.get(DEFAULT_BASE_URL_ENV) or DEFAULT_BASE_URL,
        transport=transport, timeout=resolved_timeout, credential_source=decision.source)
