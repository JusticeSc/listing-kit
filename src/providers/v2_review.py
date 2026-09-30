"""Product V2 复核（VLM Review）Provider 的中立合同（V2.5.2）。

边界（计划 §8.2 第 5 层、§10 V2.5.2）：
  - 这里只有请求/响应形状、校验与常量：不联网、不读工作空间、不写业务状态。
  - 复核只提出「值得人工先看的风险提示」：不产生人工采纳，不把审美判断升级为平台硬阻断。
  - 模型输出不合法（未知 check、越界 confidence、超长证据）时整包拒绝，由浏览器侧记为 Unknown，
    不静默清洗成看起来合法的发现。
  - 错误分类复用 v2_errors 的唯一词表；失败载体是 SemanticFailure（同一套四归口）。
  - 真实调用复用 SEL-003 的 langchain 通道（见 v2_dashscope_review）；本模块不建 HTTP 客户端。

跨语言镜像：VLM_CHECKS 与浏览器侧 app/product_v2/domain/review.js 的 VLM_CHECK_TO_RULE 键集合
必须一致，由 tools/verify_v2_5_2_vlm_review.py 比对；规则/严重度的唯一权威仍在 review.js。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

from pydantic import (BaseModel, ConfigDict, Field, ValidationError, field_validator,
                      model_validator)

from src.providers.v2_semantic import SemanticFailure, problems_from_validation

REVIEW_CONTRACT_VERSION = "v2.5.2"

IMAGE_MEDIA_TYPES = ("image/png", "image/jpeg")
MAX_CANDIDATE_BYTES = 4 * 1024 * 1024
MAX_REFERENCE_BYTES = 4 * 1024 * 1024
MAX_REFERENCE_IMAGES = 3
MAX_TOTAL_IMAGE_BYTES = 16 * 1024 * 1024
MAX_BASE64_CHARS = 6 * 1024 * 1024
MAX_TEXT_LENGTH = 500
MAX_EVIDENCE_LENGTH = 300
MAX_LIST_ITEMS = 8
MAX_LIST_ITEM_LENGTH = 120
MAX_FACTS = 20
MAX_FINDINGS = 12

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# 模型只能在这组 check 里报告问题；check → rule_id/severity/consumer 的唯一权威在浏览器侧。
VLM_CHECKS = (
    "product_fidelity",
    "part_anomaly",
    "deformity",
    "clipping",
    "garbled_text",
    "goal_completion",
    "prohibited_content",
)


def _non_blank(value: Any, label: str, *, limit: int) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{label} 不能为空。")
    if len(value) > limit:
        raise ValueError(f"{label} 最长 {limit} 字符。")
    return value


class ReviewImage(BaseModel):
    """一张送模型的图片：内容身份（sha256）+ 严格 base64 字节；服务端解码后复算哈希。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    media_type: str
    sha256: str
    data_base64: str = Field(min_length=16, max_length=MAX_BASE64_CHARS)

    @field_validator("media_type")
    @classmethod
    def _media_type(cls, value: str) -> str:
        if value not in IMAGE_MEDIA_TYPES:
            raise ValueError("media_type 只接受 " + "、".join(IMAGE_MEDIA_TYPES) + "。")
        return value

    @field_validator("sha256")
    @classmethod
    def _sha256(cls, value: str) -> str:
        if not isinstance(value, str) or not SHA256_PATTERN.match(value):
            raise ValueError("sha256 必须是 64 位小写十六进制。")
        return value

    @field_validator("data_base64")
    @classmethod
    def _base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("data_base64 不是严格 base64。") from None
        return value


class ShotContext(BaseModel):
    """本次要复核的那张图的规格摘要；只描述目标，不做审美判决。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    keep_items: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    allow_changes: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("title 不能只有空白字符。")
        return value

    @field_validator("keep_items", "allow_changes")
    @classmethod
    def _list_shape(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            _non_blank(item, "规格条目", limit=MAX_LIST_ITEM_LENGTH)
        return value


class FactItem(BaseModel):
    """已确认的商品事实投影（只送已确认值；未确认的低置信内容不进入复核输入）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=200)

    @field_validator("label", "value")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("事实字段不能只有空白字符。")
        return value


class ReviewRequest(BaseModel):
    """一次复核请求：候选图（必填）+ 参考图（可选，最多 3 张）+ 有界的上下文文本。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: ReviewImage
    references: tuple[ReviewImage, ...] = Field(default=(), max_length=MAX_REFERENCE_IMAGES)
    shot: ShotContext
    platform: str = Field(default="amazon_us", min_length=2, max_length=40)
    product_facts: tuple[FactItem, ...] = Field(default=(), max_length=MAX_FACTS)
    locale: str = Field(default="zh-CN", min_length=2, max_length=35)

    @model_validator(mode="after")
    def _reference_roles_unique(self) -> Self:
        seen: set[str] = set()
        for image in self.references:
            if image.sha256 in seen:
                raise ValueError("参考图 sha256 重复；同一张图只送一次。")
            seen.add(image.sha256)
        return self


@dataclass(frozen=True)
class DecodedImage:
    media_type: str
    sha256: str
    data: bytes


@dataclass(frozen=True)
class DecodedReviewRequest:
    candidate: DecodedImage
    references: tuple[DecodedImage, ...]
    shot: ShotContext
    platform: str
    product_facts: tuple[FactItem, ...]
    locale: str


def _decode_image(image: ReviewImage, *, role: str, limit: int) -> DecodedImage:
    try:
        data = base64.b64decode(image.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{role}的 data_base64 不是严格 base64。") from None
    if not data:
        raise ValueError(f"{role}是空字节。")
    if len(data) > limit:
        raise ValueError(f"{role}超过 {limit} 字节上限。")
    digest = hashlib.sha256(data).hexdigest()
    if digest != image.sha256:
        raise ValueError(f"{role}的 sha256 与收到的字节不一致；拒绝把身份不明的图片送模型。")
    return DecodedImage(media_type=image.media_type, sha256=digest, data=data)


def decode_review_request(request: ReviewRequest) -> DecodedReviewRequest:
    """解码并复算哈希；任何不一致都是 input_rejected，不产生模型调用。"""

    candidate = _decode_image(request.candidate, role="候选图", limit=MAX_CANDIDATE_BYTES)
    references = tuple(
        _decode_image(image, role=f"参考图 {index + 1}", limit=MAX_REFERENCE_BYTES)
        for index, image in enumerate(request.references))
    total = len(candidate.data) + sum(len(image.data) for image in references)
    if total > MAX_TOTAL_IMAGE_BYTES:
        raise ValueError(f"候选与参考图合计超过 {MAX_TOTAL_IMAGE_BYTES} 字节上限。")
    return DecodedReviewRequest(
        candidate=candidate,
        references=references,
        shot=request.shot,
        platform=request.platform,
        product_facts=request.product_facts,
        locale=request.locale,
    )


def parse_review_request(payload: Mapping[str, Any] | None) -> DecodedReviewRequest:
    """把 HTTP 请求体投影成已校验的复核输入；失败即 input_rejected + fatal。"""

    if not isinstance(payload, Mapping):
        raise SemanticFailure("input_rejected", "INPUT_INVALID", "复核请求必须是对象。",
                              retry_policy="fatal", details={"problems": [{"path": "$"}]})
    try:
        request = ReviewRequest.model_validate(dict(payload))
        return decode_review_request(request)
    except ValidationError as error:
        raise SemanticFailure("input_rejected", "INPUT_INVALID",
                              "复核请求不满足最小条件；没有调用模型。", retry_policy="fatal",
                              details={"problems": problems_from_validation(error)}) from None
    except ValueError as error:
        raise SemanticFailure("input_rejected", "INPUT_INVALID", str(error)[:200],
                              retry_policy="fatal", details={"problems": [{"path": "$"}]}) from None


# ---------------------------------------------------------- 模型原始输出（RawReviewOutput）

class RawFinding(BaseModel):
    """模型报告的一条风险提示；严重度由浏览器侧规则表决定，模型不能自带严重度或采纳结论。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check: str
    evidence: str = Field(min_length=1, max_length=MAX_EVIDENCE_LENGTH)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("check")
    @classmethod
    def _check_vocabulary(cls, value: str) -> str:
        if value not in VLM_CHECKS:
            raise ValueError("check 不在允许的复核词表内：" + str(value)[:60])
        return value

    @field_validator("evidence")
    @classmethod
    def _evidence_not_blank(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("evidence 不能只有空白字符。")
        return value


class RawReviewOutput(BaseModel):
    """复核输出：只列确实可见的问题；没有发现问题时 findings 为空数组。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    findings: tuple[RawFinding, ...] = Field(default=(), max_length=MAX_FINDINGS)
    summary: str = Field(default="", max_length=MAX_TEXT_LENGTH)


def parse_raw_output(payload: RawReviewOutput | Mapping[str, Any] | str | bytes) -> RawReviewOutput:
    """把模型输出变成已校验的原始复核结果；失败即 INVALID_RESPONSE，整包拒绝。"""

    from src.providers.v2_semantic import invalid_response

    if isinstance(payload, RawReviewOutput):
        payload = payload.model_dump()
    if isinstance(payload, (str, bytes)):
        text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
        try:
            import json

            payload = json.loads(text)
        except ValueError as error:
            raise invalid_response("复核输出不是合法 JSON；整包拒绝。",
                                   details={"problems": problems_from_validation(error),
                                            "chars": len(text)}) from None
    if not isinstance(payload, Mapping):
        raise invalid_response("复核输出的顶层不是对象；整包拒绝。")
    try:
        return RawReviewOutput.model_validate(dict(payload))
    except ValidationError as error:
        raise invalid_response("复核输出未通过结构契约；整包拒绝。",
                               details={"problems": problems_from_validation(error)}) from None


# ---------------------------------------------------------------- 结果（ReviewResult）

@dataclass(frozen=True)
class ReviewResult:
    """一次完成的复核：findings 只含 check/evidence/confidence，不含严重度与采纳结论。"""

    findings: tuple[dict[str, Any], ...]
    summary: str
    provider_id: str
    model_id: str
    request_id: str | None
    usage: dict[str, int]
    latency_ms: int
    candidate_sha256: str
    reference_images_sent: bool
    checked_at: str
    contract_version: str = REVIEW_CONTRACT_VERSION
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "candidate_sha256": self.candidate_sha256,
            "findings": [dict(item) for item in self.findings],
            "summary": self.summary,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "request_id": self.request_id,
            "usage": dict(self.usage),
            "latency_ms": self.latency_ms,
            "reference_images_sent": self.reference_images_sent,
            "checked_at": self.checked_at,
            "attempts": self.attempts,
        }
