"""阿里云百炼（DashScope）语义适配器：``deepseek-v4.1-flash``（V2.2.2）。

装配与错误分类的操作细节见计划 §9.1；选型依据见项目上下文 §4.1 的 SEL-003/006/007。
无状态：本模块不读工作空间、不写任何业务状态；一次调用只做「输入投影 → 结构化提案」。
密钥只来自环境变量 ``DASHSCOPE_API_KEY``，不进入浏览器、日志、证据或 Git；错误消息按 ``***`` 遮蔽。

单次调用：库层重试被显式关闭（``max_retries=0``）；超时保守归 provider_unknown
（requires_review），调用方不得自动重提。只有确定「请求没有产生结果」或「没有外部副作用」
的失败才允许重试，且重试必须由人可见地决定。
"""
from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.providers.v2_semantic import (
    CORE_SLOT_REGISTRY,
    RawProposal,
    SEMANTIC_CONTRACT_VERSION,
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
from src.providers.v2_langchain_chat import (
    default_chat_model,
    response_finish_reason,
    response_request_id,
    response_usage,
    visible_text,
)

DEFAULT_PROVIDER_ID = "dashscope-semantic"
DEFAULT_MODEL_ID = "deepseek-v4.1-flash"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0
# 令牌预算必须覆盖「reasoning + 12 个槽位的 JSON」：V2.2.4 真实探针实测
# 6 槽 ≈ 950 completion tokens（其中 reasoning 324、prompt 1157），12 槽成功样本 1734
# （reasoning 547）；1400 下 4/4 截断、3200 下仍有 1 类截断，取 5000。
# 参数接受性用一次直连调用确认（max_tokens=5000 正常 stop）。
# 证据：evals/product-v2/v2.2.4-category-generality-20260930-021048.txt 与 -021404.txt。
DEFAULT_MAX_TOKENS = 5000

MODEL_ENV = "SEMANTIC_MODEL"
BASE_URL_ENV = "AMZ_V2_SEMANTIC_BASE_URL"
TIMEOUT_ENV = "AMZ_V2_SEMANTIC_TIMEOUT"
MAX_TOKENS_ENV = "AMZ_V2_SEMANTIC_MAX_TOKENS"

SECRET_TOKEN_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")

SYSTEM_PROMPT_RULES = (
    "你是跨境电商商品资料分析助手。你的回答必须是单个 JSON 对象，不要输出解释文字、"
    "Markdown 代码块或额外前后缀。\n"
    "任务：从给定商品资料中提出「候选事实槽位」，供人工确认。\n"
    "硬规则：\n"
    "1) 只能提出提案，不能声称已确认；不要编造资料里没有的事实。\n"
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


def build_messages(request: SemanticRequest) -> list[Any]:
    """系统与用户消息直接构造；不使用 ChatPromptTemplate（SEL-007）。"""

    references = [f"- {asset.role} 参考图：{asset.media_type}（内容哈希 {asset.sha256[:12]}…）"
                  for asset in request.references]
    selling_points = "\n".join(f"- {item}" for item in request.selling_points) or "（未提供）"
    user_parts = [
        f"站点/平台：{request.platform}",
        f"商品名称：{request.product_name}",
        f"商品介绍：{request.description or '（未提供）'}",
        f"真实卖点：\n{selling_points}",
        f"本次重点：{request.focus or '（未提供）'}",
        "参考图（只提供了元数据，没有像素）：\n" + ("\n".join(references) or "（无）"),
        f"已存在槽位（不要重复提议）：{', '.join(request.existing_slot_ids) or '（无）'}",
        f"最多提案 {request.max_slots} 个槽位；输出语言：{request.locale}。",
    ]
    return [SystemMessage(content=build_system_prompt()),
            HumanMessage(content="\n".join(user_parts))]


class DashScopeSemanticProvider:
    """``deepseek-v4.1-flash`` 适配器；``llm_factory`` 可注入，供离线契约测试走同一条装配路径。"""

    provider_id = DEFAULT_PROVIDER_ID
    supports_images = False

    def __init__(self, *, api_key: str | None = None, model_id: str | None = None,
                 base_url: str | None = None, timeout: float | None = None,
                 max_tokens: int | None = None,
                 llm_factory: Callable[[], Any] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.api_key = api_key if api_key is not None else os.getenv(DEFAULT_API_KEY_ENV)
        self.model_id = model_id or os.getenv(MODEL_ENV) or DEFAULT_MODEL_ID
        self.base_url = (base_url or os.getenv(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")
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
        """json_mode + include_raw；令牌预算走 extra_body.max_tokens（计划 §9.1）。"""

        if self._structured is None:
            self._structured = self.build_llm().with_structured_output(
                RawProposal, method="json_mode", include_raw=True,
                extra_body={"max_tokens": self.max_tokens})
        return self._structured

    # ------------------------------------------------------------ 一次调用
    def analyze(self, request: SemanticRequest) -> SemanticProposal:
        request = validate_request(request)
        if not self.api_key:
            raise SemanticFailure("internal", "PROVIDER_NOT_CONFIGURED",
                                  f"未配置 {DEFAULT_API_KEY_ENV}，无法调用真实语义模型。",
                                  retry_policy="fatal")
        started = self._clock()
        try:
            result = self.build_structured_model().invoke(build_messages(request))
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
            "supports_images": self.supports_images,
            "configured": bool(self.api_key),
            "endpoint_host": self.base_url,
            "timeout_seconds": self.timeout,
            "max_tokens": self.max_tokens,
            "structured_output": "json_mode",
            "transport": "langchain-openai/ChatOpenAI",
        }

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
            inputs_used=("product_input", "reference_metadata"),
            reference_images_sent=False,
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
