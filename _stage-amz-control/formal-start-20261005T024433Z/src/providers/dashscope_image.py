"""Asynchronous DashScope Qwen Image adapter with safe, provider-neutral results."""
from __future__ import annotations

import base64
import hashlib
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

import requests

from src.providers import is_arrears_provider_code
from src.providers.image import ImageProviderError, ImageReference, ImageTask

DEFAULT_PROVIDER_ID = "dashscope-qwen-image"
DEFAULT_MODEL_ID = "qwen-image-3.0"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
CREATE_PATH = "/services/aigc/image-generation/generation"
DEFAULT_SIZE = "1344*1344"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
_REFERENCE_TYPES = {
    "image/jpeg", "image/png", "image/bmp", "image/tiff", "image/webp", "image/gif",
}
_TASK_STATUSES = {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}
_MAX_REFERENCE_BYTES = 10 * 1024 * 1024
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any] | None,
        timeout: float,
        allow_redirects: bool,
    ) -> Any: ...


def _requests_transport(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    json: Mapping[str, Any] | None,
    timeout: float,
    allow_redirects: bool,
) -> requests.Response:
    return requests.request(
        method,
        url,
        headers=dict(headers),
        json=dict(json) if json is not None else None,
        timeout=timeout,
        allow_redirects=allow_redirects,
    )


class _CallableTransport:
    """Adapt a plain callable transport to the Transport protocol used here."""

    def __init__(self, call: Any) -> None:
        self._call = call

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any] | None,
        timeout: float,
        allow_redirects: bool,
    ) -> Any:
        return self._call(
            method, url, headers=headers, json=json, timeout=timeout,
            allow_redirects=allow_redirects,
        )


_DEFAULT_TRANSPORT = _CallableTransport(_requests_transport)


def _coerce_transport(transport: Transport | None) -> Transport:
    """The provider always speaks to a Transport object with .request(...).

    Real runs use _DEFAULT_TRANSPORT; callers (tests, probes) may pass either a
    Transport object or a plain callable, and both must work - a silent
    AttributeError here used to turn every real submit into a false UNKNOWN.
    """
    if transport is None:
        return _DEFAULT_TRANSPORT
    if hasattr(transport, "request"):
        return transport
    if callable(transport):
        return _CallableTransport(transport)
    raise ValueError("image provider transport must expose .request(...) or be callable")


def _valid_request_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate if _REQUEST_ID_RE.fullmatch(candidate) else None


def _payload(response: Any) -> Mapping[str, Any] | None:
    try:
        value = response.json()
    except Exception:
        return None
    return value if isinstance(value, Mapping) else None


def _request_id(response: Any, payload: Mapping[str, Any] | None) -> str | None:
    headers = getattr(response, "headers", {}) or {}
    if isinstance(headers, Mapping):
        for name, value in headers.items():
            if str(name).lower() in {"x-request-id", "request-id", "x-dashscope-request-id"}:
                candidate = _valid_request_id(value)
                if candidate:
                    return candidate
    if payload:
        return _valid_request_id(payload.get("request_id") or payload.get("id"))
    return None


def _provider_error_code(payload: Mapping[str, Any] | None) -> str | None:
    if not payload:
        return None
    nested = payload.get("error")
    candidates = [payload.get("code"), nested.get("code") if isinstance(nested, Mapping) else None]
    return next((value for value in candidates if isinstance(value, str) and _SAFE_CODE_RE.fullmatch(value)), None)


def _status_code(response: Any) -> int:
    try:
        return int(getattr(response, "status_code", 0))
    except (TypeError, ValueError):
        return 0


def _safe_base_url(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip().rstrip("/")
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise ValueError("image provider base URL is invalid") from None
    if (
        parsed.scheme != "https"
        or not (host == "aliyuncs.com" or host.endswith(".aliyuncs.com"))
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("image provider base URL must be an HTTPS Aliyun endpoint")
    return raw


def _valid_result_url(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 8192 or any(ord(c) < 32 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and (host == "aliyuncs.com" or host.endswith(".aliyuncs.com"))
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


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
    return tuple(dict.fromkeys(value for value in candidates if _valid_result_url(value)))


class DashScopeImageProvider:
    """ImageProvider for the frozen DashScope async image-generation contract.

    DashScope's frozen contract does not define a remote idempotency header. The
    argument is accepted for interface compatibility but is never transmitted;
    durable submit-once/reconcile behavior belongs to the application store.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = DEFAULT_BASE_URL,
        model_id: str = DEFAULT_MODEL_ID,
        provider_id: str = DEFAULT_PROVIDER_ID,
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = api_key.strip() if isinstance(api_key, str) else ""
        self.base_url = _safe_base_url(base_url)
        self.model_id = model_id.strip() if isinstance(model_id, str) else ""
        self.provider_id = provider_id.strip() if isinstance(provider_id, str) else ""
        try:
            self.timeout = float(timeout)
        except (TypeError, ValueError):
            raise ValueError("image provider timeout must be positive") from None
        self._transport = _coerce_transport(transport)
        if not _MODEL_RE.fullmatch(self.model_id) or not _MODEL_RE.fullmatch(self.provider_id):
            raise ValueError("image provider and model identifiers are invalid")
        if self.timeout <= 0:
            raise ValueError("image provider timeout must be positive")

    def _ready(self, model_id: str | None = None) -> str:
        if not self.api_key:
            raise ImageProviderError(
                "PROVIDER_API_KEY_MISSING",
                f"未配置 {DEFAULT_API_KEY_ENV}，未调用图像模型。",
                status="REJECTED",
            )
        if not self.base_url:
            raise ImageProviderError("PROVIDER_ENDPOINT_MISSING", "未配置图像模型服务端点。", status="REJECTED")
        selected = self.model_id if model_id is None else model_id
        if not isinstance(selected, str) or not _MODEL_RE.fullmatch(selected) or selected != self.model_id:
            raise ImageProviderError(
                "MODEL_UNSUPPORTED", "当前图像适配器只支持已注册的 qwen-image-3.0。", status="REJECTED"
            )
        return selected

    @staticmethod
    def _validate_size(size: str) -> None:
        if not isinstance(size, str) or not re.fullmatch(r"[0-9]{1,4}\*[0-9]{1,4}", size):
            raise ImageProviderError("SIZE_INVALID", "图像尺寸必须是宽*高格式。", status="REJECTED")
        width, height = (int(value) for value in size.split("*", 1))
        if (
            not 384 <= width <= 2048
            or not 384 <= height <= 2048
            or not 512 * 512 <= width * height <= 2048 * 2048
            or not 1 / 8 <= width / height <= 8
        ):
            raise ImageProviderError("SIZE_INVALID", "图像尺寸超出模型合同范围。", status="REJECTED")

    @staticmethod
    def _validate_references(references: Sequence[ImageReference]) -> list[ImageReference]:
        if isinstance(references, (str, bytes, bytearray)):
            raise ImageProviderError("REFERENCE_IMAGES_INVALID", "参考图输入无效。", status="REJECTED")
        try:
            images = list(references)
        except TypeError:
            raise ImageProviderError("REFERENCE_IMAGES_INVALID", "参考图输入无效。", status="REJECTED") from None
        if not images:
            raise ImageProviderError("REFERENCE_IMAGE_REQUIRED", "图生图至少需要一张参考图。", status="REJECTED")
        if len(images) > 3:
            raise ImageProviderError("REFERENCE_IMAGE_LIMIT", "一次图生图最多使用三张参考图。", status="REJECTED")
        for item in images:
            if not isinstance(item, ImageReference):
                raise ImageProviderError("REFERENCE_IMAGES_INVALID", "参考图输入无效。", status="REJECTED")
            if item.media_type not in _REFERENCE_TYPES:
                raise ImageProviderError("REFERENCE_IMAGE_TYPE_UNSUPPORTED", "参考图格式不受当前模型合同支持。", status="REJECTED")
            if not isinstance(item.content, bytes) or not item.content:
                raise ImageProviderError("REFERENCE_IMAGE_INVALID", "参考图内容为空或格式无效。", status="REJECTED")
            if len(item.content) > _MAX_REFERENCE_BYTES:
                raise ImageProviderError("REFERENCE_IMAGE_TOO_LARGE", "单张参考图超过 10MB 合同上限。", status="REJECTED")
            if not isinstance(item.sha256, str) or not _SHA_RE.fullmatch(item.sha256) or hashlib.sha256(item.content).hexdigest() != item.sha256:
                raise ImageProviderError("REFERENCE_IMAGE_HASH_MISMATCH", "参考图内容校验失败，请重新载入素材。", status="REJECTED")
        return images

    def _task(self, payload: Mapping[str, Any], requested_task_id: str | None, request_id: str | None) -> ImageTask:
        output = payload.get("output")
        if not isinstance(output, Mapping):
            output = {}
        raw_id = output.get("task_id")
        task_id = raw_id if isinstance(raw_id, str) and _ID_RE.fullmatch(raw_id) else requested_task_id
        raw_status = output.get("task_status")
        status = raw_status.upper() if isinstance(raw_status, str) else "UNKNOWN"
        if status not in _TASK_STATUSES:
            status = "UNKNOWN"
        error = None
        if status == "FAILED":
            code = _provider_error_code(payload)
            error = f"图像生成任务失败{f'（错误码 {code}）' if code else ''}。"
        elif status == "UNKNOWN":
            error = "服务端返回状态未知；请再次查询原任务确认结果。"
        return ImageTask(
            provider_id=self.provider_id,
            model_id=self.model_id,
            task_id=task_id,
            status=status,
            result_urls=_result_urls(payload),
            error=error,
            request_id=request_id,
        )

    @staticmethod
    def _upstream_error(
        operation: str,
        status_code: int,
        request_id: str | None,
        provider_code: str | None = None,
    ) -> ImageProviderError:
        suffix = f"（服务码 {provider_code}）" if provider_code else ""
        if status_code == 429:
            # A rate limit is a definitive non-acceptance: the server never took
            # the task, so retrying cannot double-charge and must not be reported
            # as a content rejection.
            if "提交" in operation:
                return ImageProviderError(
                    "UPSTREAM_RATE_LIMITED",
                    f"百炼暂时限流（HTTP 429）{suffix}，这次提交没有被受理；稍后可重试这张图。",
                    status="FAILED",
                    request_id=request_id,
                )
            return ImageProviderError(
                "UPSTREAM_RATE_LIMITED",
                f"百炼暂时限流（HTTP 429）{suffix}，结果暂时无法确认。",
                status="UNKNOWN",
                request_id=request_id,
            )
        if is_arrears_provider_code(provider_code):
            # The account is out of credit: the request was never accepted, so it
            # is safe to retry the same submit after a recharge, and the operator
            # needs the fix spelled out instead of a generic rejection.
            return ImageProviderError(
                "UPSTREAM_ACCOUNT_ARREARS",
                f"阿里云百炼账户欠费（服务码 {provider_code}），{operation}未被受理；"
                "这次提交不计入已受理任务，充值后重试即可。",
                status="FAILED" if "提交" in operation else "REJECTED",
                request_id=request_id,
            )
        if 400 <= status_code < 500:
            return ImageProviderError(
                "UPSTREAM_REJECTED",
                f"百炼拒绝了{operation}请求（HTTP {status_code}）{suffix}。",
                status="REJECTED",
                request_id=request_id,
            )
        return ImageProviderError(
            "UPSTREAM_OUTCOME_UNKNOWN",
            f"{operation}响应异常（HTTP {status_code}），远端结果无法确认。",
            status="UNKNOWN",
            request_id=request_id,
        )

    def submit(
        self,
        prompt: str,
        references: Sequence[ImageReference],
        *,
        model_id: str | None = None,
        size: str = DEFAULT_SIZE,
        seed: int | None = None,
        idempotency_key: str | None = None,
    ) -> ImageTask:
        selected_model = self._ready(model_id)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ImageProviderError("PROMPT_REQUIRED", "图像提示词不能为空。", status="REJECTED")
        refs = self._validate_references(references)
        self._validate_size(size)
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 2147483647):
            raise ImageProviderError("SEED_INVALID", "随机种子必须是 0 至 2147483647 的整数。", status="REJECTED")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str)
            or not idempotency_key
            or len(idempotency_key) > 160
            or any(ord(char) < 32 for char in idempotency_key)
        ):
            raise ImageProviderError("IDEMPOTENCY_KEY_INVALID", "提交动作标识无效。", status="REJECTED")

        content = [
            {"image": f"data:{item.media_type};base64,{base64.b64encode(item.content).decode('ascii')}"}
            for item in refs
        ]
        content.append({"text": prompt})
        parameters: dict[str, Any] = {
            "size": size,
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
        }
        if seed is not None:
            parameters["seed"] = seed
        body = {
            "model": selected_model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        try:
            response = self._transport.request(
                "POST",
                self.base_url + CREATE_PATH,
                headers=headers,
                json=body,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except (requests.exceptions.Timeout, TimeoutError, requests.exceptions.RequestException, OSError):
            return ImageTask(
                provider_id=self.provider_id,
                model_id=selected_model,
                task_id=None,
                status="UNKNOWN",
                error="提交超时或连接中断，服务端是否受理无法确认；请先核对，不要自动重提。",
            )

        status_code = _status_code(response)
        payload = _payload(response)
        request_id = _request_id(response, payload)
        if not 200 <= status_code < 300:
            if 400 <= status_code < 500 or 300 <= status_code < 400:
                raise self._upstream_error(
                    "图像提交", status_code, request_id, _provider_error_code(payload)
                ) from None
            return ImageTask(
                provider_id=self.provider_id,
                model_id=selected_model,
                task_id=None,
                status="UNKNOWN",
                error="提交响应异常，服务端是否受理无法确认；请先核对，不要自动重提。",
                request_id=request_id,
            )
        if payload is None:
            return ImageTask(
                provider_id=self.provider_id,
                model_id=selected_model,
                task_id=None,
                status="UNKNOWN",
                error="提交响应无法解析，服务端是否受理无法确认；请先核对，不要自动重提。",
                request_id=request_id,
            )
        task = self._task(payload, None, request_id)
        if task.task_id is None:
            return ImageTask(
                provider_id=self.provider_id,
                model_id=selected_model,
                task_id=None,
                status="UNKNOWN",
                error="提交响应未包含可核对的任务编号；请先核对，不要自动重提。",
                request_id=request_id,
            )
        return task

    def query_task(self, task_id: str) -> ImageTask:
        self._ready()
        if not isinstance(task_id, str) or not _ID_RE.fullmatch(task_id):
            raise ImageProviderError("TASK_ID_INVALID", "图像任务编号无效。", status="REJECTED")
        try:
            response = self._transport.request(
                "GET",
                self.base_url + "/tasks/" + quote(task_id, safe=""),
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=None,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except (requests.exceptions.Timeout, TimeoutError, requests.exceptions.RequestException, OSError):
            return ImageTask(
                provider_id=self.provider_id,
                model_id=self.model_id,
                task_id=task_id,
                status="UNKNOWN",
                error="查询暂时未能确认任务状态；请再次查询原任务，不要重新提交。",
            )

        status_code = _status_code(response)
        payload = _payload(response)
        request_id = _request_id(response, payload)
        if 400 <= status_code < 500 or 300 <= status_code < 400:
            raise self._upstream_error(
                "任务查询", status_code, request_id, _provider_error_code(payload)
            ) from None
        if not 200 <= status_code < 300 or payload is None:
            return ImageTask(
                provider_id=self.provider_id,
                model_id=self.model_id,
                task_id=task_id,
                status="UNKNOWN",
                error="查询响应异常，任务状态尚未确认；请再次查询原任务。",
                request_id=request_id,
            )
        returned_id = (payload.get("output") or {}).get("task_id") if isinstance(payload.get("output"), Mapping) else None
        if returned_id is not None and returned_id != task_id:
            return ImageTask(
                provider_id=self.provider_id,
                model_id=self.model_id,
                task_id=task_id,
                status="UNKNOWN",
                error="查询响应中的任务编号不匹配；请核对原任务。",
                request_id=request_id,
            )
        return self._task(payload, task_id, request_id)

    def download_result(self, url: str) -> tuple[bytes, str]:
        if not _valid_result_url(url):
            raise ImageProviderError("RESULT_URL_REJECTED", "结果图片地址不符合受信 HTTPS 来源。", status="REJECTED")
        try:
            response = self._transport.request(
                "GET",
                url,
                headers={"Accept": "image/png"},
                json=None,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except (requests.exceptions.Timeout, TimeoutError, requests.exceptions.RequestException, OSError):
            raise ImageProviderError(
                "RESULT_DOWNLOAD_UNKNOWN",
                "结果图片下载超时或连接中断；下载结果尚未确认。",
                status="UNKNOWN",
            ) from None

        status_code = _status_code(response)
        request_id = _request_id(response, None)
        if not 200 <= status_code < 300:
            raise self._upstream_error("结果图片下载", status_code, request_id) from None
        content = getattr(response, "content", None)
        headers = getattr(response, "headers", {}) or {}
        content_type = ""
        if isinstance(headers, Mapping):
            content_type = next((str(value) for name, value in headers.items()
                                 if str(name).lower() == "content-type"), "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if (
            not isinstance(content, bytes)
            or not content.startswith(_PNG_SIGNATURE)
            or media_type not in {"", "application/octet-stream", "image/png"}
        ):
            raise ImageProviderError("RESULT_IMAGE_INVALID", "模型返回的结果不是合同要求的 PNG 图片。", status="REJECTED", request_id=request_id)
        return content, "image/png"


def create_default_image_provider(
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    timeout: float = 30.0,
    base_url: str = DEFAULT_BASE_URL,
) -> DashScopeImageProvider:
    """Create the registered default adapter without making a provider call."""
    source = os.environ if environ is None else environ
    return DashScopeImageProvider(
        api_key=source.get(DEFAULT_API_KEY_ENV),
        base_url=base_url,
        transport=transport,
        timeout=timeout,
    )
