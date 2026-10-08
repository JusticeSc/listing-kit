"""阿里云百炼（DashScope）VLM 复核适配器（V2.5.2）。

传输复用 SEL-003 决定的 langchain-openai ``ChatOpenAI``（与 deepseek-v4.1-flash 同一条通道），
不新建 HTTP 客户端、重试层或解析层；错误映射复用 ``v2_semantic.map_openai_exception``（同一四归口）。
本模块只做「候选图 + 参考图 + 规格摘要 → 结构化风险发现」：不读工作空间、不写业务状态、不自动采纳。
模型输出非法时整包拒绝（INVALID_RESPONSE），由浏览器侧记为 Unknown 并保留人工门。
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
from src.providers.v2_review import (REVIEW_CONTRACT_VERSION, DecodedImage,
                                     DecodedReviewRequest, RawReviewOutput, ReviewResult,
                                     parse_raw_output)
from src.providers.v2_semantic import (SemanticFailure, internal_failure, invalid_response,
                                       map_openai_exception, output_truncated,
                                       problems_from_parse_error, refused)

DEFAULT_PROVIDER_ID = "dashscope-review"
DEFAULT_MODEL_ID = "qwen-vl-max"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0
# 复核输出只有少量 finding；预算覆盖 VLM 的 reasoning 与 JSON 包装（计划 §9.1 的同类经验）。
DEFAULT_MAX_TOKENS = 2000

MODEL_ENV = "REVIEW_MODEL"
BASE_URL_ENV = "AMZ_V2_REVIEW_BASE_URL"
TIMEOUT_ENV = "AMZ_V2_REVIEW_TIMEOUT"
MAX_TOKENS_ENV = "AMZ_V2_REVIEW_MAX_TOKENS"

SECRET_TOKEN_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")

CHECK_LABELS = {
    "product_fidelity": "商品失真：与参考图的颜色、形状、材质、标识或部件不一致",
    "part_anomaly": "部件异常：缺失、多余或结构错误",
    "deformity": "明显畸形：扭曲、比例失衡、器型异常",
    "clipping": "穿模或拼接痕迹：物体互相穿透、贴合处断裂",
    "garbled_text": "文字乱码：包装或标签文字不可读、错误",
    "goal_completion": "目标完成度：画面没有完成这张图的既定目的",
    "prohibited_content": "禁止内容：平台不允许的元素",
}


def build_system_prompt() -> str:
    """系统提示 = 硬规则 + 由 Pydantic schema 生成的 JSON 格式说明（与语义链路同一 SEL-007 风格）。"""

    schema = json.dumps(RawReviewOutput.model_json_schema(), ensure_ascii=False,
                        separators=(",", ":"))
    lines = [
        "你是跨境电商商品图复核助手。你的回答必须是单个 JSON 对象，不要输出解释文字、"
        "Markdown 代码块或额外前后缀。",
        "任务：对照参考图与本次图片规格，找出候选中「确实可见」的问题，供人工优先查看。",
        "硬规则：",
        "1) 只报告你能从图片中直接看到的问题；不猜、不编造；没有发现问题就输出空 findings 数组。",
        "2) check 只能取下列词表之一（附含义）：",
    ]
    for key, label in CHECK_LABELS.items():
        lines.append(f"- {key}：{label}")
    lines.extend([
        "3) evidence 只写图中可见证据（位置与现象），不超过 80 字；confidence 取 0..1。",
        "4) 你不判断是否可交付、不给严重度、不做审美判决；审美与采纳由人工决定。",
        "5) 输出 JSON 必须满足下面的 JSON Schema，字段名与类型不可改：",
        schema,
    ])
    return "\n".join(lines)


def _image_data_url(image: DecodedImage) -> str:
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{image.media_type};base64,{encoded}"


def build_messages(request: DecodedReviewRequest) -> list[Any]:
    """系统与用户消息直接构造；图片顺序=候选优先，随后是参考图（SEL-007 风格，不用 prompt 模板）。"""

    facts = "；".join(f"{item.label}={item.value}" for item in request.product_facts) or "（无）"
    keep = "；".join(request.shot.keep_items) or "（未说明）"
    allow = "；".join(request.shot.allow_changes) or "（未说明）"
    text = "\n".join([
        f"平台：{request.platform}",
        f"本次图片：{request.shot.title}",
        f"图片目的：{request.shot.purpose or '（未说明）'}",
        f"必须保持：{keep}",
        f"允许变化：{allow}",
        f"已确认商品事实：{facts}",
        f"输出语言：{request.locale}",
        "图片顺序：第 1 张是候选图（要复核的），其后是参考图。",
    ])
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    content.append({"type": "image_url", "image_url": {"url": _image_data_url(request.candidate)}})
    for image in request.references:
        content.append({"type": "image_url", "image_url": {"url": _image_data_url(image)}})
    return [SystemMessage(content=build_system_prompt()), HumanMessage(content=content)]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class DashScopeReviewProvider:
    """``qwen-vl-max`` 复核适配器；``llm_factory`` 可注入，供离线契约测试走同一条装配路径。"""

    provider_id = DEFAULT_PROVIDER_ID
    supports_reference_images = True

    def __init__(self, *, api_key: str | None = None, model_id: str | None = None,
                 base_url: str | None = None, timeout: float | None = None,
                 max_tokens: int | None = None, llm_factory: Callable[[], Any] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get(DEFAULT_API_KEY_ENV)
        self.model_id = model_id or os.environ.get(MODEL_ENV) or DEFAULT_MODEL_ID
        self.base_url = base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL
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
        """json_mode + include_raw；令牌预算走 extra_body.max_tokens（与语义链路同一装配方式）。"""

        if self._structured is None:
            self._structured = self.build_llm().with_structured_output(
                RawReviewOutput, method="json_mode", include_raw=True,
                extra_body={"max_tokens": self.max_tokens})
        return self._structured

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "review_contract": REVIEW_CONTRACT_VERSION,
            "supports_reference_images": self.supports_reference_images,
            "configured": bool(self.api_key),
            "endpoint_host": self.base_url,
            "timeout_seconds": self.timeout,
            "max_tokens": self.max_tokens,
            "structured_output": "json_mode",
            "transport": "langchain-openai/ChatOpenAI",
        }

    # ------------------------------------------------------------ 一次调用
    def review(self, request: DecodedReviewRequest) -> ReviewResult:
        if not self.api_key:
            raise SemanticFailure("internal", "PROVIDER_NOT_CONFIGURED",
                                  f"未配置 {DEFAULT_API_KEY_ENV}，无法调用真实复核模型。",
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
        return map_openai_exception(error, redact=self._redact, context="复核调用",
                                    max_tokens=self.max_tokens)

    # ------------------------------------------------------------ 结果 → 发现
    def _to_result(self, result: Any, request: DecodedReviewRequest, *,
                   latency_ms: int) -> ReviewResult:
        if not isinstance(result, Mapping):
            raise internal_failure("复核结构化输出装配返回了非映射结果。")
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
                    "复核输出被 max_tokens 截断。", request_id=request_id,
                    details={"max_tokens": self.max_tokens, "usage": usage})
            if visible_text(raw).strip() == "":
                raise invalid_response(
                    "复核模型没有产生可见文本；整包拒绝。", request_id=request_id,
                    details={"max_tokens": self.max_tokens, "usage": usage, "visible_chars": 0})
            details: dict[str, Any] = {"error_type": type(parsing_error).__name__} \
                if parsing_error is not None else {"chars": len(visible_text(raw))}
            if parsing_error is not None:
                details["problems"] = problems_from_parse_error(parsing_error)
            raise invalid_response("复核输出无法按结构契约解析；整包拒绝。",
                                   request_id=request_id, details=details)
        output = parse_raw_output(parsed)
        findings = tuple(
            {"check": item.check, "evidence": item.evidence, "confidence": item.confidence}
            for item in output.findings)
        return ReviewResult(
            findings=findings,
            summary=output.summary,
            provider_id=self.provider_id,
            model_id=self.model_id,
            request_id=request_id,
            usage=usage,
            latency_ms=latency_ms,
            candidate_sha256=request.candidate.sha256,
            reference_images_sent=bool(request.references),
            checked_at=_utc_now_iso(),
        )
