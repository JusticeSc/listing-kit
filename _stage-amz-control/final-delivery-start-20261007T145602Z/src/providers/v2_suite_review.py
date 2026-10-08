"""Product V2 整套复核（suite review）契约（V2.5.5）。

与单图复核（``v2_review.py``）同构，唯一差别在输入/输出形状：
  - 输入是「已被人工采用」的 1–8 张图的集合，每张带 ShotSpec 摘要（标题/目的/保持/允许）；
  - 输出每条 finding 必须带 ``shot_ids``（⊆ 送审集合），``check`` 只能取 ``SUITE_VLM_CHECKS``；
  - 只产生跨图风险提示：不产生 BLOCK、不做采纳结论、不取消人工选择。

词表镜像：``SUITE_VLM_CHECKS`` 的键集合必须与浏览器
``app/product_v2/domain/suite-review.js`` 的 ``SUITE_VLM_CHECK_TO_RULE`` 完全一致
（由 ``tools/verify_v2_5_5_suite_review.py`` 比对，缺一即失败）。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

from pydantic import (BaseModel, ConfigDict, Field, ValidationError, field_validator,
                      model_validator)

from src.providers.v2_review import (MAX_BASE64_CHARS, MAX_EVIDENCE_LENGTH, MAX_FACTS,
                                     MAX_LIST_ITEM_LENGTH, MAX_LIST_ITEMS,
                                     MAX_TEXT_LENGTH, FactItem, ReviewImage)
from src.providers.v2_semantic import (SemanticFailure, problems_from_validation,
                                       invalid_response)

SUITE_REVIEW_CONTRACT_VERSION = "v2.5.5"

MAX_SUITE_IMAGES = 8
MAX_SUITE_IMAGE_BYTES = 4 * 1024 * 1024
MAX_SUITE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SUITE_FINDINGS = 12
MAX_SHOT_ID_LENGTH = 120

# 模型只能在这组 check 里报告跨图问题；check → rule_id/severity 的唯一权威在浏览器侧。
SUITE_VLM_CHECKS = (
    "suite_product_consistency",
    "suite_color_material_consistency",
    "suite_cross_image_anomaly",
    "suite_style_consistency",
)

SUITE_CHECK_LABELS = {
    "suite_product_consistency": "跨图商品一致性：不同图片里的商品外观、结构或部件不一致",
    "suite_color_material_consistency": "跨图颜色材质一致性：颜色、材质或表面处理在不同图中不一致",
    "suite_cross_image_anomaly": "跨图低级异常：出现与整套其它图冲突的明显错误（变形、穿模、乱码等）",
    "suite_style_consistency": "跨图风格一致性：光线、背景、构图或配色风格明显漂移",
}


def _non_blank(value: Any, label: str, *, limit: int) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{label} 不能为空。")
    if len(value) > limit:
        raise ValueError(f"{label} 最长 {limit} 字符。")
    return value


class SuiteImageInput(BaseModel):
    """送审的一张图：身份（shot/字节）+ ShotSpec 摘要。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shot_id: str = Field(min_length=1, max_length=MAX_SHOT_ID_LENGTH)
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    keep_items: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    allow_changes: tuple[str, ...] = Field(default=(), max_length=MAX_LIST_ITEMS)
    image: ReviewImage

    @field_validator("shot_id", "title")
    @classmethod
    def _not_blank(cls, value: str, info: Any) -> str:
        return _non_blank(value, info.field_name, limit=MAX_SHOT_ID_LENGTH if info.field_name == "shot_id" else 200)

    @field_validator("keep_items", "allow_changes")
    @classmethod
    def _list_shape(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            _non_blank(item, "规格条目", limit=MAX_LIST_ITEM_LENGTH)
        return value


class SuiteReviewRequest(BaseModel):
    """一次整套复核请求：1–8 张已采用图 + 已确认事实 + 公共风格摘要。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    images: tuple[SuiteImageInput, ...] = Field(min_length=1, max_length=MAX_SUITE_IMAGES)
    platform: str = Field(default="amazon_us", min_length=2, max_length=40)
    locale: str = Field(default="zh-CN", min_length=2, max_length=35)
    style_summary: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    product_facts: tuple[FactItem, ...] = Field(default=(), max_length=MAX_FACTS)

    @model_validator(mode="after")
    def _shot_ids_unique(self) -> Self:
        seen: set[str] = set()
        for item in self.images:
            if item.shot_id in seen:
                raise ValueError("shot_id 重复；同一个 Shot 只送一次。")
            seen.add(item.shot_id)
        return self


@dataclass(frozen=True)
class DecodedSuiteImage:
    shot_id: str
    title: str
    purpose: str
    keep_items: tuple[str, ...]
    allow_changes: tuple[str, ...]
    media_type: str
    sha256: str
    data: bytes


@dataclass(frozen=True)
class DecodedSuiteReviewRequest:
    images: tuple[DecodedSuiteImage, ...]
    platform: str
    locale: str
    style_summary: str
    product_facts: tuple[FactItem, ...]

    @property
    def shot_ids(self) -> tuple[str, ...]:
        return tuple(item.shot_id for item in self.images)


def _decode_image(image: ReviewImage, *, role: str) -> bytes:
    try:
        data = base64.b64decode(image.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{role}的 data_base64 不是严格 base64。") from None
    if not data:
        raise ValueError(f"{role}是空字节。")
    if len(data) > MAX_SUITE_IMAGE_BYTES:
        raise ValueError(f"{role}超过 {MAX_SUITE_IMAGE_BYTES} 字节上限。")
    digest = hashlib.sha256(data).hexdigest()
    if digest != image.sha256:
        raise ValueError(f"{role}的 sha256 与收到的字节不一致；拒绝把身份不明的图片送模型。")
    return data


def decode_suite_review_request(request: SuiteReviewRequest) -> DecodedSuiteReviewRequest:
    """解码并复算每张图哈希；任何不一致都是 input_rejected，不产生模型调用。"""

    decoded: list[DecodedSuiteImage] = []
    total = 0
    for index, item in enumerate(request.images):
        role = f"第 {index + 1} 张图（{item.shot_id}）"
        data = _decode_image(item.image, role=role)
        total += len(data)
        decoded.append(DecodedSuiteImage(
            shot_id=item.shot_id,
            title=item.title,
            purpose=item.purpose,
            keep_items=item.keep_items,
            allow_changes=item.allow_changes,
            media_type=item.image.media_type,
            sha256=item.image.sha256,
            data=data,
        ))
    if total > MAX_SUITE_TOTAL_BYTES:
        raise ValueError(f"整套送审图片合计超过 {MAX_SUITE_TOTAL_BYTES} 字节上限。")
    return DecodedSuiteReviewRequest(
        images=tuple(decoded),
        platform=request.platform,
        locale=request.locale,
        style_summary=request.style_summary,
        product_facts=request.product_facts,
    )


def parse_suite_review_request(payload: Mapping[str, Any] | None) -> DecodedSuiteReviewRequest:
    """把 HTTP 请求体投影成已校验的整套复核输入；失败即 input_rejected + fatal。"""

    if not isinstance(payload, Mapping):
        raise SemanticFailure("input_rejected", "INPUT_INVALID", "整套复核请求必须是对象。",
                              retry_policy="fatal", details={"problems": [{"path": "$"}]})
    try:
        request = SuiteReviewRequest.model_validate(dict(payload))
        return decode_suite_review_request(request)
    except ValidationError as error:
        raise SemanticFailure("input_rejected", "INPUT_INVALID",
                              "整套复核请求不满足最小条件；没有调用模型。", retry_policy="fatal",
                              details={"problems": problems_from_validation(error)}) from None
    except ValueError as error:
        raise SemanticFailure("input_rejected", "INPUT_INVALID", str(error)[:200],
                              retry_policy="fatal", details={"problems": [{"path": "$"}]}) from None


# ------------------------------------------------------------ 模型原始输出（RawSuiteReviewOutput）

class RawSuiteFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check: str
    shot_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_SUITE_IMAGES)
    evidence: str = Field(min_length=1, max_length=MAX_EVIDENCE_LENGTH)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("check")
    @classmethod
    def _check_vocabulary(cls, value: str) -> str:
        if value not in SUITE_VLM_CHECKS:
            raise ValueError("check 不在整套复核词表内：" + str(value))
        return value

    @field_validator("evidence")
    @classmethod
    def _evidence_not_blank(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("evidence 不能只有空白字符。")
        return value


class RawSuiteReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    findings: tuple[RawSuiteFinding, ...] = Field(default=(), max_length=MAX_SUITE_FINDINGS)


def parse_raw_suite_output(payload: RawSuiteReviewOutput | Mapping[str, Any] | str | bytes,
                           *, sent_shot_ids: tuple[str, ...]) -> RawSuiteReviewOutput:
    """解析模型原始输出；shot_ids 必须是送审集合的子集，否则整包拒绝（protocol）。"""

    if isinstance(payload, RawSuiteReviewOutput):
        parsed = payload
    else:
        raw = payload
        if isinstance(raw, (str, bytes)):
            try:
                raw = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise invalid_response("整套复核输出不是合法 JSON；整包拒绝。") from None
        try:
            parsed = RawSuiteReviewOutput.model_validate(raw)
        except ValidationError as error:
            raise invalid_response("整套复核输出未通过结构契约；整包拒绝。",
                                   details={"problems": problems_from_validation(error)}) from None
    allowed = set(sent_shot_ids)
    for finding in parsed.findings:
        outside = [shot_id for shot_id in finding.shot_ids if shot_id not in allowed]
        if outside:
            raise invalid_response(
                "整套复核输出引用了未送审的 Shot；整包拒绝。",
                details={"problems": [{"path": "$.findings", "shot_ids": outside}]})
    return parsed


@dataclass(frozen=True)
class SuiteReviewResult:
    """一次完成的整套复核：只含 check/shot_ids/evidence/confidence，不含严重度与采纳结论。"""

    findings: tuple[dict[str, Any], ...]
    summary: str
    provider_id: str
    model_id: str
    request_id: str | None
    usage: dict[str, int]
    latency_ms: int
    checked_shot_ids: tuple[str, ...]
    state: str  # checked | unavailable（unavailable 只由上层投影，provider 只产出 checked）
    checked_at: str
    contract_version: str = SUITE_REVIEW_CONTRACT_VERSION
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "checked_shot_ids": list(self.checked_shot_ids),
            "submitted_shot_ids": list(self.checked_shot_ids),
            "state": self.state,
            "findings": [dict(item) for item in self.findings],
            "summary": self.summary,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "request_id": self.request_id,
            "usage": dict(self.usage),
            "latency_ms": self.latency_ms,
            "checked_at": self.checked_at,
            "attempts": self.attempts,
        }
