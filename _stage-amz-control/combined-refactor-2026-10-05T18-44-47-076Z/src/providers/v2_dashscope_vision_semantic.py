"""商品理解（看图版）适配器：``qwen-vl-max`` 做产品事实提案（V2.6.0）。

与 ``v2_dashscope_review.py`` 同一传输装配（``default_chat_model`` + ``json_mode``
结构化输出），不新建 HTTP 客户端；差异只在输入（商品资料 + 真实参考字节）与输出
（``RawProposal`` 事实提案，不是候选复核 schema）。输出永远是提案：status=proposed、
source=model_inference，不能把任何槽位标成 confirmed，确认权只属于人。

无状态：不读工作空间、不写业务状态；一次调用只做「输入投影 → 结构化提案」。
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.providers.v2_langchain_chat import (
    default_chat_model,
    response_finish_reason,
    response_request_id,
    response_usage,
    visible_text,
)
from src.providers.v2_outbound import OutboundPolicyError, validate_outbound_url
from src.providers.v2_semantic import (
    ANALYZE_BASE_FIELDS,
    CORE_SLOT_REGISTRY,
    MAX_VISION_IMAGE_BYTES,
    MAX_VISION_IMAGES,
    SEMANTIC_CONTRACT_VERSION,
    SEMANTIC_VISION_CONTRACT_VERSION,
    DecodedVisionImage,
    RawProposal,
    SemanticFailure,
    SemanticProposal,
    SemanticRequest,
    assert_proposal_legal,
    internal_failure,
    invalid_response,
    map_openai_exception,
    output_truncated,
    parse_proposal,
    problems_from_parse_error,
    refused,
    to_fact_slots,
    validate_request,
)

DEFAULT_PROVIDER_ID = "dashscope-vision"
DEFAULT_MODEL_ID = "qwen-vl-max"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0
# 看图理解输出与纯文本同一形状（最多 12 槽位 JSON + reasoning 预算）：沿用已实测的 5000。
DEFAULT_MAX_TOKENS = 5000

MODEL_ENV = "VISION_MODEL"
BASE_URL_ENV = "AMZ_V2_VISION_BASE_URL"
TIMEOUT_ENV = "AMZ_V2_VISION_TIMEOUT"
MAX_TOKENS_ENV = "AMZ_V2_VISION_MAX_TOKENS"

SECRET_TOKEN_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")

SYSTEM_PROMPT_RULES = (
    "你是跨境电商商品资料分析助手。你同时看到商品文字资料与真实商品图片。"
    "你的回答必须是单个 JSON 对象，不要输出解释文字、"
    "Markdown 代码块或额外前后缀。\n"
    "任务：结合文字与图片提出「候选事实槽位」，供人工确认。\n"
    "硬规则：\n"
    "1) 只能提出提案，不能声称已确认；不要编造资料与图片里都没有的事实；"
    "图片与文字冲突时以图片为准并写进 questions。\n"
    "2) 每条槽位必须给 confidence（0..1）和至少一条 evidence；没有把握就给低分并写进 questions。\n"
    "3) 每条槽位的 value 形状必须与 value_type 一致（text=字符串、text_list=字符串数组、"
    "number=数字、boolean=true/false、enum=enum_values 之一）。\n"
    "4) 核心槽位只允许使用下面列出的 slot_id；品类专属信息用 authority=category_dynamic "
    "配自定义 slot_id（小写字母开头、可含数字与下划线）。\n"
    "5) 值使用简体中文；品牌、型号等专有名词保留原文。\n"
    "6) value 只写结论，不抄录资料原文；text 值建议不超过 80 字，evidence.note 建议不超过 40 字。\n"
)


def core_slot_lines() -> str:
    return "；".join(f"{slot_id}（{label}，{value_type}）"
                     for slot_id, (label, value_type, _critical) in CORE_SLOT_REGISTRY.items())


def build_system_prompt() -> str:
    """系统提示 = 硬规则 + 由 Pydantic schema 生成的 JSON 格式说明（SEL-007）。"""

    schema = json.dumps(RawProposal.model_json_schema(), ensure_ascii=False,
                        separators=(",", ":"))
    return "\n".join([
        SYSTEM_PROMPT_RULES,
        f"核心槽位清单：{core_slot_lines()}。",
        "输出 JSON 必须满足下面的 JSON Schema，字段名与类型不可改：",
        schema,
    ])


def _image_data_url(image: DecodedVisionImage) -> str:
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{image.media_type};base64,{encoded}"


def build_messages(request: SemanticRequest,
                   images: tuple[DecodedVisionImage, ...]) -> list[Any]:
    """系统与用户消息直接构造；图片顺序=调用方给定顺序（SEL-007 风格，不用 prompt 模板）。"""

    references = [f"- {asset.role} 参考图：{asset.media_type}（内容哈希 {asset.sha256[:12]}…）"
                  for asset in request.references]
    selling_points = "\n".join(f"- {item}" for item in request.selling_points) or "（未提供）"
    image_lines = [f"- 第 {index + 1} 张：{image.role}（{image.media_type}，"
                   f"内容哈希 {image.sha256[:12]}…）"
                   for index, image in enumerate(images)] or ["（无）"]
    user_parts = [
        f"站点/平台：{request.platform}",
        f"商品名称：{request.product_name}",
        f"商品介绍：{request.description or '（未提供）'}",
        f"真实卖点：\n{selling_points}",
        f"本次重点：{request.focus or '（未提供）'}",
        "参考图元数据（身份登记）：\n" + "\n".join(references),
        "本次实际发送的图片字节（按以下顺序附在消息后）：\n" + "\n".join(image_lines),
        f"已存在槽位（不要重复提议）：{', '.join(request.existing_slot_ids) or '（无）'}",
        f"最多提案 {request.max_slots} 个槽位；输出语言：{request.locale}。",
    ]
    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(user_parts)}]
    for image in images:
        content.append({"type": "image_url", "image_url": {"url": _image_data_url(image)}})
    return [SystemMessage(content=build_system_prompt()), HumanMessage(content=content)]


class DashScopeVisionSemanticProvider:
    """``qwen-vl-max`` 看图理解适配器；``llm_factory`` 可注入，供离线契约测试走同一条装配路径。"""

    provider_id = DEFAULT_PROVIDER_ID
    supports_images = True

    def __init__(self, *, api_key: str | None = None, model_id: str | None = None,
                 base_url: str | None = None, timeout: float | None = None,
                 max_tokens: int | None = None,
                 llm_factory: Callable[[], Any] | None = None,
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
        self.model_id = model_id or os.environ.get(MODEL_ENV) or DEFAULT_MODEL_ID
        candidate_url = (base_url or os.getenv(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")
        try:
            validate_outbound_url(candidate_url)
        except OutboundPolicyError as error:
            raise ValueError(
                f"语义端点 {candidate_url} 不满足出站白名单策略：{error.reason}。") from None
        self.base_url = candidate_url
        self.timeout = float(timeout or os.getenv(TIMEOUT_ENV) or DEFAULT_TIMEOUT_SECONDS)
        self.max_tokens = int(max_tokens or os.getenv(MAX_TOKENS_ENV) or DEFAULT_MAX_TOKENS)
        self._llm_factory = llm_factory
        self._clock = clock
        self._llm: Any | None = None
        self._structured: Any | None = None

    # ------------------------------------------------------------ 装配（SEL-007）
    def build_llm(self) -> Any:
        if self._llm is None:
            if self._llm_factory is not None:
                self._llm = self._llm_factory()
            else:
                self._llm = default_chat_model(model_id=self.model_id, base_url=self.base_url,
                                               api_key=self.api_key, timeout=self.timeout)
        return self._llm

    def build_structured_model(self) -> Any:
        """json_mode + include_raw；令牌预算走 extra_body.max_tokens（与纯文本链路同一装配方式）。"""

        if self._structured is None:
            self._structured = self.build_llm().with_structured_output(
                RawProposal, method="json_mode", include_raw=True,
                extra_body={"max_tokens": self.max_tokens})
        return self._structured

    # ------------------------------------------------------------ 一次调用
    def analyze(self, request: SemanticRequest,
                images: tuple[DecodedVisionImage, ...]) -> SemanticProposal:
        """看图理解：文字投影 + 已校验图片字节 → 事实提案（inputs_used 标记 actual_images）。"""

        request = validate_request(request)
        if not images:
            raise SemanticFailure("input_rejected", "VISION_BYTES_REQUIRED",
                                  "看图理解需要至少一张已校验的参考图字节；"
                                  "这次请求没有调用语义模型。",
                                  retry_policy="fatal")
        started = self._clock()
        if not self.api_key:
            if self.credential_source == "none":
                raise SemanticFailure("internal", "PROVIDER_NOT_CONFIGURED",
                                      "默认档密钥处于关闭状态（或未配置密钥）；部署侧显式打开默认档，"
                                      "或用 BYOK 路径带上自己的密钥。没有调用语义模型。",
                                      retry_policy="fatal")
            raise SemanticFailure("internal", "PROVIDER_NOT_CONFIGURED",
                                  f"未配置 {DEFAULT_API_KEY_ENV}，无法调用真实语义模型。",
                                  retry_policy="fatal")
        try:
            result = self.build_structured_model().invoke(build_messages(request, images))
        except SemanticFailure:
            raise
        except Exception as error:
            raise self._map_exception(error) from None
        latency_ms = int((self._clock() - started) * 1000)
        return self._to_proposal(result, request, latency_ms=latency_ms)

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "semantic_contract": SEMANTIC_CONTRACT_VERSION,
            "vision_contract": SEMANTIC_VISION_CONTRACT_VERSION,
            "supports_images": self.supports_images,
            "vision": True,
            "max_reference_images": MAX_VISION_IMAGES,
            "max_reference_bytes": MAX_VISION_IMAGE_BYTES,
            "analyze_fields": [*ANALYZE_BASE_FIELDS, "reference_images"],
            "configured": bool(self.api_key),
            "credential_source": self.credential_source,
            "endpoint_host": self.base_url,
            "timeout_seconds": self.timeout,
            "max_tokens": self.max_tokens,
            "structured_output": "json_mode",
            "transport": "langchain-openai/ChatOpenAI",
        }

    def apply_credentials(self, *, api_key: str) -> None:
        """把本次请求内存态的 BYOK 密钥换上；只影响当前实例，不写盘、不进日志。"""

        if not isinstance(api_key, str) or not api_key.strip():
            raise SemanticFailure("input_rejected", "BYOK_CREDENTIAL_INVALID",
                                  "BYOK 密钥为空或格式非法；这次请求不调用语义模型。",
                                  retry_policy="fatal")
        self.api_key = api_key.strip()
        self.credential_source = "byok"

    # ------------------------------------------------------------ 结果 → 提案
    def _to_proposal(self, result: Any, request: SemanticRequest, *,
                     latency_ms: int) -> SemanticProposal:
        if not isinstance(result, Mapping):
            raise internal_failure("结构化输出装配返回了非映射结果。")
        raw = result.get("raw")
        parsed = result.get("parsed")
        parsing_error = result.get("parsing_error")
        finish_reason = response_finish_reason(raw)
        request_id = response_request_id(raw)
        usage = response_usage(raw)
        if finish_reason == "content_filter":
            raise refused("模型拒绝分析该输入（内容策略）。", request_id=request_id)
        if parsed is None:
            if finish_reason == "length":
                raise output_truncated(
                    "模型输出被 max_tokens 截断（推理型模型会先消耗 reasoning 预算）。",
                    request_id=request_id,
                    details={"max_tokens": self.max_tokens, "usage": usage})
            if visible_text(raw).strip() == "":
                raise invalid_response(
                    "模型没有产生可见文本；推理预算可能被 reasoning 耗尽（提高 max_tokens 后重试）。",
                    request_id=request_id,
                    details={"max_tokens": self.max_tokens, "usage": usage,
                             "visible_chars": 0})
            if parsing_error is not None:
                raise invalid_response(
                    "模型输出无法按结构契约解析；整包拒绝。", request_id=request_id,
                    details={"problems": problems_from_parse_error(parsing_error),
                             "error_type": type(parsing_error).__name__})
            raise invalid_response("模型输出无法按结构契约解析；整包拒绝。",
                                   request_id=request_id,
                                   details={"chars": len(visible_text(raw))})
        proposal = parse_proposal(parsed)
        facts = to_fact_slots(proposal, request, model_id=self.model_id)
        assert_proposal_legal(facts, max_slots=request.max_slots)
        return SemanticProposal(
            slots=facts,
            questions=tuple(proposal.questions),
            summary=proposal.summary,
            provider_id=self.provider_id,
            model_id=self.model_id,
            request_id=request_id,
            usage=usage,
            latency_ms=latency_ms,
            inputs_used=("product_input", "reference_metadata", "actual_images"),
            reference_images_sent=True,
            attempts=1,
        )

    # ------------------------------------------------------------ 异常 → 分类
    def _redact(self, text: str) -> str:
        safe = text or ""
        if self.api_key:
            safe = safe.replace(self.api_key, "***")
        safe = SECRET_TOKEN_PATTERN.sub("sk-***", safe)
        return safe.strip()[:300]

    def _map_exception(self, error: BaseException) -> SemanticFailure:
        """按计划 §9.1 的归口表把 SDK/传输异常映射成分类失败。"""

        return map_openai_exception(error, redact=self._redact, context="语义调用",
                                    max_tokens=self.max_tokens)
