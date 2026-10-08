"""整套复核（suite review）的真实 provider：百炼兼容端点 + ChatOpenAI（SEL-003/011 复用）。

与 ``v2_dashscope_review.py`` 同一装配路径（``default_chat_model`` + ``json_mode`` 结构化输出），
不新建 HTTP 客户端；差异只在消息构造（多图 + 每图 ShotSpec 摘要）与输出解析（shot_ids 子集校验）。
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.providers.v2_langchain_chat import (default_chat_model, response_finish_reason,
                                             response_request_id, response_usage, visible_text)
from src.providers.v2_outbound import OutboundPolicyError, validate_outbound_url
from src.providers.v2_semantic import (SemanticFailure, internal_failure, invalid_response,
                                       map_openai_exception, output_truncated,
                                       problems_from_parse_error, refused)
from src.providers.v2_suite_review import (SUITE_CHECK_LABELS, SUITE_REVIEW_CONTRACT_VERSION,
                                           DecodedSuiteImage, DecodedSuiteReviewRequest,
                                           RawSuiteReviewOutput, SuiteReviewResult,
                                           parse_raw_suite_output)

DEFAULT_PROVIDER_ID = "dashscope-review"
DEFAULT_MODEL_ID = "qwen-vl-max"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TIMEOUT_SECONDS = 90.0
# 整套一次看最多 8 张图并输出最多 12 条发现；预算覆盖 reasoning 与 JSON 包装。
DEFAULT_MAX_TOKENS = 2400

MODEL_ENV = "SUITE_REVIEW_MODEL"
MODEL_ENV_FALLBACK = "REVIEW_MODEL"
BASE_URL_ENV = "AMZ_V2_REVIEW_BASE_URL"
TIMEOUT_ENV = "AMZ_V2_REVIEW_TIMEOUT"
MAX_TOKENS_ENV = "AMZ_V2_SUITE_REVIEW_MAX_TOKENS"

SECRET_TOKEN_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")


def build_system_prompt() -> str:
    """系统提示 = 硬规则 + 由 Pydantic schema 生成的 JSON 格式说明（与单图复核同一风格）。"""

    schema = json.dumps(RawSuiteReviewOutput.model_json_schema(), ensure_ascii=False,
                        separators=(",", ":"))
    lines = [
        "你是跨境电商商品图整套复核助手。你的回答必须是单个 JSON 对象，不要输出解释文字、"
        "Markdown 代码块或额外前后缀。",
        "任务：对照同一商品的整套已采用图片，找出「跨图之间确实可见」的不一致或低级异常，"
        "供人工优先查看。",
        "硬规则：",
        "1) 单张图内部的问题不在这里报告；只报告跨图对比才能发现的问题。",
        "2) 只报告你能从图片中直接看到的问题；不猜、不编造；没有发现问题就输出空 findings 数组。",
        "3) check 只能取下列词表之一（附含义）：",
    ]
    for key, label in SUITE_CHECK_LABELS.items():
        lines.append(f"- {key}：{label}")
    lines.extend([
        "4) 每条 finding 的 shot_ids 只能引用本次送审清单里的 shot_id（不要臆造、不要越界）；"
        "涉及两张以上图片时全部列出。",
        "5) evidence 只写图中可见证据（涉及哪些图、差在哪里），不超过 120 字；confidence 取 0..1。",
        "6) 你不判断是否可交付、不给严重度、不做审美判决；采纳与返工由人工决定。",
        "7) 输出 JSON 必须满足下面的 JSON Schema，字段名与类型不可改：",
        schema,
    ])
    return "\n".join(lines)


def _image_data_url(image: DecodedSuiteImage) -> str:
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{image.media_type};base64,{encoded}"


def build_messages(request: DecodedSuiteReviewRequest) -> list[Any]:
    """一条用户消息：先给送审清单文本，再按同一顺序附上图片（SEL-007 风格）。"""

    facts = "；".join(f"{item.label}={item.value}" for item in request.product_facts) or "（无）"
    lines = [
        f"平台：{request.platform}",
        f"公共风格摘要：{request.style_summary or '（未说明）'}",
        f"已确认商品事实：{facts}",
        f"输出语言：{request.locale}",
        "送审清单（shot_id、标题、目的、必须保持、允许变化）：",
    ]
    for index, image in enumerate(request.images):
        keep = "；".join(image.keep_items) or "（未说明）"
        allow = "；".join(image.allow_changes) or "（未说明）"
        lines.append(
            f"[{index + 1}] shot_id={image.shot_id}；标题={image.title}；目的={image.purpose or '（未说明）'}"
            f"；必须保持={keep}；允许变化={allow}")
    lines.append("图片顺序与上面的清单一致：第 1 张对应第 1 个 shot_id，依此类推。")
    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(lines)}]
    for image in request.images:
        content.append({"type": "image_url", "image_url": {"url": _image_data_url(image)}})
    return [SystemMessage(content=build_system_prompt()), HumanMessage(content=content)]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class DashScopeSuiteReviewProvider:
    """``qwen-vl-max`` 整套复核适配器；``llm_factory`` 可注入，离线契约测试走同一条装配路径。"""

    provider_id = DEFAULT_PROVIDER_ID
    supports_reference_images = True

    def __init__(self, *, api_key: str | None = None, model_id: str | None = None,
                 base_url: str | None = None, timeout: float | None = None,
                 max_tokens: int | None = None, llm_factory: Callable[[], Any] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 credential_source: str | None = None) -> None:
        # credential_source 由 v2_credentials.resolve_credentials 决定（V2.R4.3）：
        #   none → 默认档被关闭：环境变量里有密钥也不带进适配器；
        #   default/byok → 调用方显式解析后传入（BYOK 走 apply_credentials）；
        #   env → 直接构造（验证器/探针）沿用旧口径：api_key is None 时读环境变量。
        if credential_source == "none":
            self.api_key = ""
        else:
            self.api_key = api_key if api_key is not None else os.environ.get(DEFAULT_API_KEY_ENV)
        self.credential_source = credential_source or "env"
        self.model_id = (model_id or os.environ.get(MODEL_ENV) or os.environ.get(MODEL_ENV_FALLBACK)
                         or DEFAULT_MODEL_ID)
        self.base_url = base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL
        try:
            validate_outbound_url(self.base_url)
        except OutboundPolicyError as error:
            raise ValueError(
                f"整套复核端点 {self.base_url} 不满足出站白名单策略：{error.reason}。") from None
        env_timeout = os.environ.get(TIMEOUT_ENV)
        self.timeout = float(timeout if timeout is not None else (env_timeout or DEFAULT_TIMEOUT_SECONDS))
        env_tokens = os.environ.get(MAX_TOKENS_ENV)
        self.max_tokens = int(max_tokens if max_tokens is not None else (env_tokens or DEFAULT_MAX_TOKENS))
        self._llm_factory = llm_factory
        self._clock = clock
        self._llm: Any = None
        self._structured: Any = None

    def _redact(self, text: str) -> str:
        safe = text or ""
        if self.api_key:
            safe = safe.replace(self.api_key, "***")
        safe = SECRET_TOKEN_PATTERN.sub("sk-***", safe)
        return safe.strip()[:300]

    def build_llm(self) -> Any:
        if self._llm is None:
            if self._llm_factory is not None:
                self._llm = self._llm_factory()
            else:
                self._llm = default_chat_model(model_id=self.model_id, base_url=self.base_url,
                                               api_key=self.api_key, timeout=self.timeout)
        return self._llm

    def build_structured_model(self) -> Any:
        if self._structured is None:
            self._structured = self.build_llm().with_structured_output(
                RawSuiteReviewOutput, method="json_mode", include_raw=True,
                extra_body={"max_tokens": self.max_tokens})
        return self._structured

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "suite_review_contract": SUITE_REVIEW_CONTRACT_VERSION,
            "max_images": 8,
            "configured": bool(self.api_key),
            "credential_source": self.credential_source,
            "endpoint_host": self.base_url,
            "timeout_seconds": self.timeout,
            "max_tokens": self.max_tokens,
            "structured_output": "json_mode",
            "transport": "langchain-openai/ChatOpenAI",
        }

    def apply_credentials(self, *, api_key: str) -> None:
        """把本次请求内存态的 BYOK 密钥换上；整套复核 BYOK 路线在本切片只留接缝。"""

        if not isinstance(api_key, str) or not api_key.strip():
            raise SemanticFailure("input_rejected", "BYOK_CREDENTIAL_INVALID",
                                  "BYOK 密钥为空或格式非法；这次请求不调用整套复核。",
                                  retry_policy="fatal")
        self.api_key = api_key.strip()
        self.credential_source = "byok"

    # ------------------------------------------------------------ 一次调用
    def review(self, request: DecodedSuiteReviewRequest) -> SuiteReviewResult:
        if not self.api_key:
            if self.credential_source == "none":
                raise SemanticFailure("internal", "PROVIDER_NOT_CONFIGURED",
                                      "默认档密钥处于关闭状态（或未配置密钥）；部署侧显式打开默认档，"
                                      "或用 BYOK 路径带上自己的密钥。没有调用整套复核。",
                                      retry_policy="fatal")
            raise SemanticFailure("internal", "PROVIDER_NOT_CONFIGURED",
                                  f"未配置 {DEFAULT_API_KEY_ENV}，无法调用真实整套复核模型。",
                                  retry_policy="fatal")
        started = self._clock()
        try:
            result = self.build_structured_model().invoke(build_messages(request))
        except SemanticFailure:
            raise
        except Exception as error:  # noqa: BLE001 - SDK 异常一律走分类归口
            raise self._map_exception(error) from None
        latency_ms = int((self._clock() - started) * 1000)
        return self._to_result(result, request, latency_ms=latency_ms)

    def _map_exception(self, error: BaseException) -> SemanticFailure:
        return map_openai_exception(error, redact=self._redact, context="整套复核调用",
                                    max_tokens=self.max_tokens)

    def _to_result(self, result: Any, request: DecodedSuiteReviewRequest, *,
                   latency_ms: int) -> SuiteReviewResult:
        if not isinstance(result, Mapping):
            raise internal_failure("整套复核结构化输出装配返回了非映射结果。")
        raw = result.get("raw")
        parsed = result.get("parsed")
        parsing_error = result.get("parsing_error")
        finish_reason = response_finish_reason(raw)
        request_id = response_request_id(raw)
        usage = response_usage(raw)
        if finish_reason == "content_filter":
            raise refused("模型拒绝复核该输入（内容策略）。", request_id=request_id)
        if parsed is None:
            if finish_reason == "length":
                raise output_truncated(
                    "整套复核输出被 max_tokens 截断。", request_id=request_id,
                    details={"max_tokens": self.max_tokens, "usage": usage})
            if visible_text(raw).strip() == "":
                raise invalid_response(
                    "整套复核模型没有产生可见文本；整包拒绝。", request_id=request_id,
                    details={"max_tokens": self.max_tokens, "usage": usage, "visible_chars": 0})
            details: dict[str, Any] = {"error_type": type(parsing_error).__name__} \
                if parsing_error is not None else {"chars": len(visible_text(raw))}
            if parsing_error is not None:
                details["problems"] = problems_from_parse_error(parsing_error)
            raise invalid_response("整套复核输出无法按结构契约解析；整包拒绝。",
                                   request_id=request_id, details=details)
        output = parse_raw_suite_output(parsed, sent_shot_ids=request.shot_ids)
        findings = tuple(
            {"check": item.check, "shot_ids": list(item.shot_ids),
             "evidence": item.evidence, "confidence": item.confidence}
            for item in output.findings)
        summary = (f"已核对 {len(request.images)} 张图，发现 {len(findings)} 条跨图提示。"
                   if findings else f"已核对 {len(request.images)} 张图，未发现跨图问题。")
        return SuiteReviewResult(
            findings=findings,
            summary=summary,
            provider_id=self.provider_id,
            model_id=self.model_id,
            request_id=request_id,
            usage=usage,
            latency_ms=latency_ms,
            checked_shot_ids=request.shot_ids,
            state="checked",
            checked_at=_utc_now_iso(),
        )
