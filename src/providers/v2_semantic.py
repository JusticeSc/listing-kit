"""Product V2 语义 Provider 的中立合同（V2.2.2）。

边界（计划 §4.2 / §4.3 / §9.1）：
  - 这里只有数据形状、分类和校验：不联网、不读工作空间、不写业务状态。
  - 模型输出永远是提案：status=proposed、source=model_inference、必带 confidence 与至少一条
    evidence；提案不能把任何槽位变成 confirmed，确认权只属于人。
  - 非法输出必须变成分类错误，而不是被静默清洗成看起来合法的业务事实（计划 §9.1）。

契约的权威表示是 Pydantic（SEL-006）：Request / RawSlot / RawProposal 三类模型 + 跨字段校验。
浏览器侧 CORE_SLOT_REGISTRY 与 checkFactSlot 是跨语言镜像，由
tools/verify_v2_2_2_semantic_provider.py 比对；这里不复制它们的实现。

错误分类（计划 §9 / §9.1）必须区分「输入拒绝 / Provider 明确失败 / 超时或 Unknown / 内部错误」，
并给出 retry_policy，使调用方不必猜能不能重提。
"""
from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Self

from pydantic import (BaseModel, ConfigDict, Field, ValidationError, field_validator,
                      model_validator)

from src.providers.v2_errors import ERROR_FAMILIES as _ERROR_FAMILIES
from src.providers.v2_errors import RETRY_POLICIES as _RETRY_POLICIES

SEMANTIC_CONTRACT_VERSION = "v2.2.2"
FACT_SLOT_SCHEMA_VERSION = 1

SLOT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

SLOT_VALUE_TYPES = ("text", "text_list", "number", "boolean", "enum")
MODEL_SLOT_AUTHORITIES = ("core_fixed", "category_dynamic")
MODEL_EVIDENCE_KINDS = ("model", "asset", "user")
REFERENCE_ROLES = ("primary", "detail", "packaging", "scene", "competitor", "other")

MAX_PRODUCT_NAME_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 2000
MAX_FOCUS_LENGTH = 500
MAX_LIST_ITEMS = 20
MAX_LIST_ITEM_LENGTH = 200
MAX_TEXT_VALUE_LENGTH = 400
MAX_REFERENCES = 20
MAX_SLOTS = 24
MAX_EVIDENCE_ITEMS = 8
MAX_QUESTIONS = 6
MAX_DEPENDS_ON = 8

ERROR_FAMILIES = _ERROR_FAMILIES
RETRY_POLICIES = _RETRY_POLICIES

# 与 app/product_v2/domain/slots.js 的 CORE_SLOT_REGISTRY 保持一致（label, value_type, critical）。
# 两边不一致属于契约漂移，由 tools/verify_v2_2_2_semantic_provider.py 跨语言比对。
CORE_SLOT_REGISTRY = {
    "product_name": ("商品名称", "text", True),
    "product_category": ("商品品类", "text", True),
    "signature_features": ("必须保持的商品特征", "text_list", True),
    "brand": ("品牌", "text", False),
    "key_material": ("主要材质", "text", False),
    "color_summary": ("颜色概览", "text", False),
    "size_summary": ("尺寸概览", "text", False),
    "package_contents": ("包装内容物", "text_list", False),
}


class SemanticFailure(RuntimeError):
    """一次语义调用的分类失败；消息里不得包含原始请求数据或密钥。"""

    def __init__(self, family: str, code: str, message: str, *, retry_policy: str,
                 http_status: int | None = None, request_id: str | None = None,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        if family not in ERROR_FAMILIES:
            raise ValueError(f"unknown error family: {family}")
        if retry_policy not in RETRY_POLICIES:
            raise ValueError(f"unknown retry policy: {retry_policy}")
        self.family = family
        self.code = code
        self.message = message
        self.retry_policy = retry_policy
        self.http_status = http_status
        self.request_id = request_id
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "code": self.code,
            "message": self.message,
            "retry_policy": self.retry_policy,
            "http_status": self.http_status,
            "request_id": self.request_id,
            "details": self.details,
        }


# ---------------------------------------------------------------- 值形状

def value_shape_problem(value_type: str, value: Any, enum_values: Any) -> str | None:
    """返回 None 表示形状合法；否则返回人类可读的问题（不回显原始值）。"""

    if value_type == "text":
        if not isinstance(value, str) or value.strip() == "":
            return "text 值必须是非空字符串。"
        if len(value) > MAX_TEXT_VALUE_LENGTH:
            return f"text 值最长 {MAX_TEXT_VALUE_LENGTH} 字符。"
        return None
    if value_type == "text_list":
        if not isinstance(value, (list, tuple)) or not value:
            return "text_list 值必须是非空数组。"
        if len(value) > MAX_LIST_ITEMS:
            return f"text_list 最多 {MAX_LIST_ITEMS} 项。"
        for item in value:
            if (not isinstance(item, str) or item.strip() == ""
                    or len(item) > MAX_LIST_ITEM_LENGTH):
                return f"列表项必须是非空短字符串（≤{MAX_LIST_ITEM_LENGTH} 字符）。"
        return None
    if value_type == "number":
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(float(value))):
            return "number 值必须是有限数字。"
        return None
    if value_type == "boolean":
        if not isinstance(value, bool):
            return "boolean 值必须是 true/false。"
        return None
    if value_type == "enum":
        if not isinstance(enum_values, (list, tuple)) or not enum_values:
            return "enum 类型必须声明非空 enum_values。"
        for item in enum_values:
            if not isinstance(item, str) or item.strip() == "":
                return "enum_values 只能是非空字符串。"
        if not isinstance(value, str) or value not in enum_values:
            return "enum 值必须是 enum_values 之一。"
        return None
    return f"未知 value_type：{value_type}。"


# ------------------------------------------------------------ 输入投影（Request）

class ReferencedAsset(BaseModel):
    """调用方明确告知的一张参考图（只带元数据，不带本机路径）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sha256: str = Field(pattern=SHA256_PATTERN.pattern, description="参考图内容的 64 位小写 sha256")
    media_type: str = Field(min_length=1, max_length=120, description="例如 image/png")
    role: Literal["primary", "detail", "packaging", "scene", "competitor", "other"]
    original_name: str | None = Field(default=None, max_length=200)


class SemanticRequest(BaseModel):
    """语义分析的输入投影；它只是 ProductInput 的子集，不含任何服务器路径。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product_name: str = Field(min_length=1, max_length=MAX_PRODUCT_NAME_LENGTH)
    description: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)
    selling_points: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    focus: str = Field(default="", max_length=MAX_FOCUS_LENGTH)
    references: tuple[ReferencedAsset, ...] = Field(min_length=1, max_length=MAX_REFERENCES)
    locale: str = Field(default="zh-CN", min_length=2, max_length=35)
    platform: str = Field(default="amazon_us", min_length=2, max_length=40)
    max_slots: int = Field(default=12, ge=1, le=MAX_SLOTS)
    existing_slot_ids: tuple[str, ...] = Field(default=(), max_length=MAX_SLOTS)

    @field_validator("product_name")
    @classmethod
    def _product_name_not_blank(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("商品名称不能只有空白字符。")
        return value

    @field_validator("selling_points")
    @classmethod
    def _selling_points_shape(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not isinstance(item, str) or item.strip() == "" or len(item) > MAX_LIST_ITEM_LENGTH:
                raise ValueError(f"卖点必须是非空短字符串（≤{MAX_LIST_ITEM_LENGTH} 字符）。")
        return value

    @field_validator("existing_slot_ids")
    @classmethod
    def _existing_slot_ids_shape(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not SLOT_ID_PATTERN.match(item):
                raise ValueError("existing_slot_ids 项必须是合法 slot_id。")
        return value


# ---------------------------------------------------------- 模型原始输出（RawProposal）

class RawEvidence(BaseModel):
    """模型为一条槽位给出的来源；系统只原样搬运，不代写。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["model", "asset", "user"]
    ref: str = Field(min_length=1, max_length=64, description="来源标识，例如 product_input")
    note: str | None = Field(default=None, max_length=200)


class RawSlot(BaseModel):
    """模型提出的单条候选槽位；跨字段约束见 _cross_field。

    ``critical`` 不在模型契约里：它是系统字段，归一化时由 ``CORE_SLOT_REGISTRY`` 派生
    （V2.2.4 实测：要求模型回显注册表值只会制造整包拒绝，2/4 类因此失败）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str = Field(pattern=SLOT_ID_PATTERN.pattern, description="小写字母开头的槽位标识")
    label: str = Field(min_length=1, max_length=60)
    authority: Literal["core_fixed", "category_dynamic"]
    value_type: Literal["text", "text_list", "number", "boolean", "enum"]
    value: str | list[str] | bool | int | float
    confidence: float = Field(ge=0.0, le=1.0, description="0..1，仅用于排序，不代表已确认")
    evidence: tuple[RawEvidence, ...] = Field(min_length=1, max_length=MAX_EVIDENCE_ITEMS)
    depends_on: tuple[str, ...] = Field(default=(), max_length=MAX_DEPENDS_ON)
    enum_values: tuple[str, ...] | None = None
    note: str | None = Field(default=None, max_length=300)

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence_number(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("confidence 不接受布尔值。")
        if isinstance(value, int):
            return float(value)  # 显式且唯一的数值加宽：1 与 1.0 是同一个数
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("confidence 必须是有限数字。")
            return value
        raise ValueError("confidence 必须是 0..1 的数字。")

    @field_validator("depends_on")
    @classmethod
    def _depends_on_shape(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not SLOT_ID_PATTERN.match(item):
                raise ValueError("depends_on 项必须是合法 slot_id。")
        return value

    @model_validator(mode="after")
    def _cross_field(self) -> Self:
        problem = value_shape_problem(self.value_type, self.value, self.enum_values)
        if problem:
            raise ValueError(f"value 与 value_type 不一致：{problem}")
        if self.value_type != "enum" and self.enum_values is not None:
            raise ValueError("enum_values 只允许在 value_type=enum 时出现。")
        if self.authority == "core_fixed":
            definition = CORE_SLOT_REGISTRY.get(self.slot_id)
            if definition is None:
                raise ValueError("core_fixed 槽位必须在系统注册表内。")
            if self.value_type != definition[1]:
                raise ValueError(f"核心槽位 value_type 必须与注册表一致（{definition[1]}）。")
        if self.slot_id in self.depends_on:
            raise ValueError("槽位不能依赖自己。")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on 不允许重复。")
        return self


class RawProposal(BaseModel):
    """模型一次分析的全部原始输出。这是 with_structured_output 的结构目标。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(default="", max_length=300, description="一句话概括这次看到的商品资料")
    questions: tuple[str, ...] = Field(default=(), max_length=MAX_QUESTIONS,
                                       description="需要人工回答的关键问题")
    slots: tuple[RawSlot, ...] = Field(min_length=1, max_length=MAX_SLOTS,
                                       description="候选事实槽位；本次数量上限见请求 max_slots")

    @field_validator("questions")
    @classmethod
    def _questions_shape(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not isinstance(item, str) or item.strip() == "" or len(item) > MAX_LIST_ITEM_LENGTH:
                raise ValueError("questions 项必须是非空短字符串。")
        return value


# ------------------------------------------------------- 校验错误 → 分类失败

def _loc_path(loc: Sequence[Any]) -> str:
    path = "$"
    for part in loc:
        path = f"{path}[{part}]" if isinstance(part, int) else f"{path}.{part}"
    return path


def problems_from_validation(error: BaseException, *, limit: int = 8) -> list[dict[str, str]]:
    """把 Pydantic / 解析异常变成不含原始输入与原始输出的 problems 列表。"""

    problems: list[dict[str, str]] = []
    if isinstance(error, ValidationError):
        for item in error.errors()[:limit]:
            problems.append({"path": _loc_path(item.get("loc") or ()),
                             "message": str(item.get("msg", ""))[:200]})
    if not problems:
        problems.append({"path": "$",
                         "message": f"{type(error).__name__}：解析或校验失败（细节已省略）。"})
    return problems


def problems_from_parse_error(error: BaseException, *, limit: int = 8) -> list[dict[str, str]]:
    """解析异常可能是包装层（如 langchain 的 OutputParserException）：
    先展开底层 Pydantic / JSON 错误，拿不到时才退回通用描述。"""

    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ValidationError):
            return problems_from_validation(current, limit=limit)
        current = current.__cause__ or current.__context__
    return problems_from_validation(error, limit=limit)


def parse_request(payload: Mapping[str, Any]) -> SemanticRequest:
    """把 HTTP 请求体投影成已校验的输入；失败即 input_rejected + fatal。"""

    if not isinstance(payload, Mapping):
        raise SemanticFailure("input_rejected", "INPUT_INVALID", "商品资料投影必须是对象。",
                              retry_policy="fatal", details={"problems": [{"path": "$"}]})
    try:
        return SemanticRequest.model_validate(dict(payload))
    except ValidationError as error:
        raise SemanticFailure("input_rejected", "INPUT_INVALID",
                              "商品资料不满足语义分析的最小条件。", retry_policy="fatal",
                              details={"problems": problems_from_validation(error)}) from None


def validate_request(request: SemanticRequest) -> SemanticRequest:
    """已构造对象再过一次全量校验，防止绕过模型直接塞字段。"""

    return parse_request(request.model_dump())


def parse_proposal(payload: RawProposal | Mapping[str, Any] | str | bytes) -> RawProposal:
    """把模型输出变成已校验的原始提案；失败即 INVALID_RESPONSE，整包拒绝。"""

    if isinstance(payload, RawProposal):
        payload = payload.model_dump()
    if isinstance(payload, (str, bytes)):
        text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
        try:
            payload = json.loads(text)
        except ValueError as error:
            raise invalid_response("模型输出不是合法 JSON；整包拒绝。",
                                   details={"problems": problems_from_validation(error),
                                            "chars": len(text)}) from None
    if not isinstance(payload, Mapping):
        raise invalid_response("模型输出的顶层不是对象；整包拒绝。")
    try:
        return RawProposal.model_validate(dict(payload))
    except ValidationError as error:
        raise invalid_response("模型输出未通过结构契约；整包拒绝。",
                               details={"problems": problems_from_validation(error)}) from None


def to_fact_slots(proposal: RawProposal, request: SemanticRequest, *,
                  model_id: str) -> tuple[dict[str, Any], ...]:
    """提案 → FactSlot 形状；超上限/重复身份直接失败，绝不截断或去重掩盖。"""

    limit = min(request.max_slots, MAX_SLOTS)
    if len(proposal.slots) > limit:
        raise invalid_response("模型提案的槽位数超过本次上限；拒绝截断，整包拒绝。",
                               details={"count": len(proposal.slots), "max_slots": limit})
    seen: set[str] = set()
    facts: list[dict[str, Any]] = []
    for index, raw in enumerate(proposal.slots):
        if raw.slot_id in seen:
            raise invalid_response("同一个 slot_id 在一次提案里出现两次；整包拒绝。",
                                   details={"slot_id": raw.slot_id, "index": index})
        seen.add(raw.slot_id)
        slot: dict[str, Any] = {
            "schema_version": FACT_SLOT_SCHEMA_VERSION,
            "slot_id": raw.slot_id,
            "label": raw.label,
            "authority": raw.authority,
            "value_type": raw.value_type,
            "value": list(raw.value) if isinstance(raw.value, tuple) else raw.value,
            "source": "model_inference",
            "status": "proposed",
            "confidence": float(raw.confidence),
            "evidence": [{key: value for key, value in item.model_dump().items()
                          if value is not None} for item in raw.evidence],
            "depends_on": list(raw.depends_on),
            "model_id": model_id,
        }
        if raw.authority == "core_fixed":
            slot["critical"] = bool(CORE_SLOT_REGISTRY[raw.slot_id][2])
        if raw.value_type == "enum":
            slot["enum_values"] = list(raw.enum_values or ())
        facts.append(slot)
    return tuple(facts)


# ---------------------------------------------------------------- 提案结果

@dataclass(frozen=True)
class SemanticProposal:
    """已通过结构校验的提案包；写入项目仍由浏览器侧 domain 契约决定。"""

    slots: tuple[dict[str, Any], ...]
    questions: tuple[str, ...]
    summary: str
    provider_id: str
    model_id: str
    request_id: str | None
    usage: Mapping[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    inputs_used: tuple[str, ...] = ("product_input",)
    reference_images_sent: bool = False
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_contract": SEMANTIC_CONTRACT_VERSION,
            "slots": [dict(slot) for slot in self.slots],
            "questions": list(self.questions),
            "summary": self.summary,
            "meta": {
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "request_id": self.request_id,
                "usage": dict(self.usage),
                "latency_ms": self.latency_ms,
                "inputs_used": list(self.inputs_used),
                "reference_images_sent": self.reference_images_sent,
                "attempts": self.attempts,
            },
        }


# ------------------------------------------------------------ 错误分类

def _safe_text(value: object, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def classify_http_failure(status: int, provider_code: str | None, message: str, *,
                          request_id: str | None = None) -> SemanticFailure:
    """把 Provider 的 HTTP 响应映射成分类失败（计划 §9.1 的归口表）。"""

    safe_message = _safe_text(message, 300) or "Provider 返回错误。"
    if status in (400, 404, 405, 413, 415, 422):
        return SemanticFailure("input_rejected", "INPUT_REJECTED", safe_message,
                               retry_policy="fatal", http_status=status, request_id=request_id,
                               details={"provider_code": provider_code})
    if status in (401, 403):
        return SemanticFailure("provider_failed", "PROVIDER_AUTH_FAILED",
                               "语义模型鉴权失败：请检查 DASHSCOPE_API_KEY 是否有效。",
                               retry_policy="fatal", http_status=status, request_id=request_id,
                               details={"provider_code": provider_code})
    if status == 429:
        return SemanticFailure("provider_failed", "PROVIDER_RATE_LIMITED", safe_message,
                               retry_policy="retryable", http_status=status, request_id=request_id,
                               details={"provider_code": provider_code})
    return SemanticFailure("provider_failed", "PROVIDER_HTTP_ERROR", safe_message,
                           retry_policy="retryable", http_status=status, request_id=request_id,
                           details={"provider_code": provider_code})


def classify_transport_failure(kind: str, message: str, *,
                               request_id: str | None = None) -> SemanticFailure:
    """传输层失败：只有确定「请求没有产生结果」时才允许 retryable。"""

    safe_message = _safe_text(message, 300) or "语义调用失败。"
    if kind == "unreachable":
        return SemanticFailure("provider_failed", "PROVIDER_UNREACHABLE", safe_message,
                               retry_policy="retryable", request_id=request_id)
    if kind == "timeout_before_send":
        return SemanticFailure("provider_failed", "PROVIDER_TIMEOUT", safe_message,
                               retry_policy="retryable", request_id=request_id)
    if kind == "timeout_after_send":
        return SemanticFailure("provider_unknown", "PROVIDER_TIMEOUT", safe_message,
                               retry_policy="requires_review", request_id=request_id)
    if kind == "aborted":
        return SemanticFailure("provider_unknown", "PROVIDER_ABORTED", safe_message,
                               retry_policy="requires_review", request_id=request_id)
    return SemanticFailure("provider_unknown", "PROVIDER_UNKNOWN", safe_message,
                           retry_policy="requires_review", request_id=request_id)


def invalid_response(message: str, *, details: Mapping[str, Any] | None = None,
                     request_id: str | None = None) -> SemanticFailure:
    """模型输出不可用：没有外部副作用，可安全重试，但重试必须是可见决定。"""

    return SemanticFailure("provider_failed", "INVALID_RESPONSE", message,
                           retry_policy="retryable", request_id=request_id, details=details)


def output_truncated(message: str, *, details: Mapping[str, Any] | None = None,
                     request_id: str | None = None) -> SemanticFailure:
    return SemanticFailure("provider_failed", "PROVIDER_OUTPUT_TRUNCATED", message,
                           retry_policy="requires_review", request_id=request_id, details=details)


def refused(message: str, *, request_id: str | None = None) -> SemanticFailure:
    return SemanticFailure("provider_failed", "PROVIDER_REFUSED", message,
                           retry_policy="fatal", request_id=request_id)


def internal_failure(message: str, *, details: Mapping[str, Any] | None = None) -> SemanticFailure:
    return SemanticFailure("internal", "INTERNAL_ERROR", message,
                           retry_policy="requires_review", details=details)


# ---------------------------------------------- 消费侧结构校验（FactSlot 形状）

def _problem(problems: list[dict[str, Any]], path: str, message: str) -> None:
    problems.append({"path": path, "message": message})


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def check_value_shape(problems: list[dict[str, Any]], path: str, value_type: str,
                      value: object, enum_values: object) -> None:
    problem = value_shape_problem(str(value_type), value, enum_values)
    if problem:
        _problem(problems, path, problem)


def check_proposal_slot(slot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """模型提案必须满足的最小形状；它与浏览器侧 checkFactSlot 对齐且更严（必带置信）。"""

    problems: list[dict[str, Any]] = []
    if not isinstance(slot, Mapping):
        _problem(problems, "$", "提案槽位必须是对象。")
        return problems
    if slot.get("schema_version") != FACT_SLOT_SCHEMA_VERSION:
        _problem(problems, "$.schema_version", f"schema_version 必须是 {FACT_SLOT_SCHEMA_VERSION}。")
    slot_id = slot.get("slot_id")
    if not isinstance(slot_id, str) or not SLOT_ID_PATTERN.match(slot_id):
        _problem(problems, "$.slot_id", "slot_id 必须是 2-48 位小写字母开头的标识。")
    if not _is_non_empty_str(slot.get("label")) or len(slot["label"]) > 60:
        _problem(problems, "$.label", "label 必须是 1-60 字符的非空字符串。")
    authority = slot.get("authority")
    if authority not in MODEL_SLOT_AUTHORITIES:
        _problem(problems, "$.authority", "模型只能提案 core_fixed（限注册表）或 category_dynamic。")
    value_type = slot.get("value_type")
    if value_type not in SLOT_VALUE_TYPES:
        _problem(problems, "$.value_type", "value_type 不在词表内。")
    if slot.get("source") != "model_inference":
        _problem(problems, "$.source", "模型提案的 source 只能是 model_inference。")
    if slot.get("status") != "proposed":
        _problem(problems, "$.status", "模型提案的 status 只能是 proposed；确认权只属于人。")
    confidence = slot.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) \
            or not (0.0 <= float(confidence) <= 1.0):
        _problem(problems, "$.confidence", "模型提案必须携带 0..1 的 confidence（用于排序，不代表已确认）。")
    if authority == "core_fixed":
        definition = CORE_SLOT_REGISTRY.get(str(slot_id))
        if definition is None:
            _problem(problems, "$.slot_id", "core_fixed 槽位必须在系统注册表内。")
        else:
            if value_type != definition[1]:
                _problem(problems, "$.value_type", f"核心槽位 value_type 必须与注册表一致（{definition[1]}）。")
            if bool(slot.get("critical")) != bool(definition[2]):
                _problem(problems, "$.critical", "核心槽位 critical 必须与注册表一致。")
    check_value_shape(problems, "$.value", str(value_type), slot.get("value"), slot.get("enum_values"))
    evidence = slot.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        _problem(problems, "$.evidence", "模型提案必须给出至少一条来源证据。")
    else:
        if len(evidence) > MAX_EVIDENCE_ITEMS:
            _problem(problems, "$.evidence", f"证据最多 {MAX_EVIDENCE_ITEMS} 条。")
        for index, item in enumerate(evidence):
            path = f"$.evidence[{index}]"
            if not isinstance(item, Mapping):
                _problem(problems, path, "evidence 项必须是对象。")
                continue
            if item.get("kind") not in MODEL_EVIDENCE_KINDS:
                _problem(problems, path + ".kind", "evidence.kind 不在允许词表内。")
            if not _is_non_empty_str(item.get("ref")):
                _problem(problems, path + ".ref", "evidence.ref 必须是非空字符串。")
            note = item.get("note")
            if note is not None and not isinstance(note, str):
                _problem(problems, path + ".note", "evidence.note 只能是字符串。")
    depends_on = slot.get("depends_on", [])
    if not isinstance(depends_on, list):
        _problem(problems, "$.depends_on", "depends_on 必须是数组。")
    else:
        seen: set[str] = set()
        for index, item in enumerate(depends_on):
            path = f"$.depends_on[{index}]"
            if not isinstance(item, str) or not SLOT_ID_PATTERN.match(item):
                _problem(problems, path, "depends_on 项必须是合法 slot_id。")
            elif item == slot_id:
                _problem(problems, path, "槽位不能依赖自己。")
            elif item in seen:
                _problem(problems, path, "depends_on 不允许重复。")
            else:
                seen.add(item)
    return problems


def check_proposal(slots: Sequence[Mapping[str, Any]], *,
                   max_slots: int = 12) -> list[dict[str, Any]]:
    """对整包提案做集合级校验：数量、重复身份、核心槽位不重复提案。"""

    problems: list[dict[str, Any]] = []
    if not isinstance(slots, (list, tuple)):
        _problem(problems, "$.slots", "slots 必须是数组。")
        return problems
    if len(slots) > min(max_slots, MAX_SLOTS):
        _problem(problems, "$.slots", f"提案槽位数量超过上限（{min(max_slots, MAX_SLOTS)}）。")
    seen: set[str] = set()
    for index, slot in enumerate(slots):
        for item in check_proposal_slot(slot):
            problems.append({"path": f"$.slots[{index}]{item['path'][1:]}",
                             "message": item["message"]})
        slot_id = slot.get("slot_id") if isinstance(slot, Mapping) else None
        if isinstance(slot_id, str):
            if slot_id in seen:
                _problem(problems, f"$.slots[{index}].slot_id",
                         "同一个 slot_id 不能在一次提案里出现两次。")
            seen.add(slot_id)
    return problems


def assert_proposal_legal(slots: Iterable[Mapping[str, Any]], *, max_slots: int) -> None:
    """校验不通过时抛 INVALID_RESPONSE：非法模型输出不许进入项目。"""

    problems = check_proposal(list(slots), max_slots=max_slots)
    if problems:
        raise invalid_response(
            "模型输出未通过结构校验；拒绝写入。",
            details={"problems": problems[:8], "count": len(problems)},
        )
