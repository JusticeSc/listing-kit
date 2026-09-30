"""Product V2 图像生成网关的中立合同（V2.4.1）。

边界（计划 §9 / §9.10）：
  - 这里只有数据形状、分类与校验：不联网、不读工作空间、不写业务状态、不保存任务。
  - 网关只做三件事：提交一次生成、查询一次任务、取回一次结果字节；任务身份由调用方
    （浏览器）持有，服务端不建任务表，因此重启不改变任何结论。
  - 上游签名结果地址只在本进程内使用，绝不出现在返回给浏览器的 JSON 里。
  - 输入里出现目录、工作空间或路径字段属于契约违规：直接拒绝，不做“兼容”。

契约的权威表示是 Pydantic（SEL-006 的同一选择）；错误词表来自 ``v2_errors.py`` 的唯一一份，
本文件不复制第二套 family / retry_policy。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.providers.v2_errors import (ERROR_FAMILIES, RETRY_POLICIES, UNKNOWN_FAMILY,
                                     assert_vocabulary)

IMAGE_CONTRACT_VERSION = "v2.4.1"
IMAGE_PROVIDER_ID = "dashscope-qwen-image"
IMAGE_MODEL_ID = "qwen-image-3.0"
DEFAULT_SIZE = "1344*1344"

MAX_REFERENCE_IMAGES = 3
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_PROMPT_CHARS = 4000

MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
ACTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
SIZE_PATTERN = re.compile(r"^[0-9]{1,4}\*[0-9]{1,4}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

IMAGE_ROLES = ("primary", "detail", "packaging", "scene", "competitor", "other")
TASK_STATUSES = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN")

_MEDIA_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/bmp": (b"BM",),
    "image/webp": (b"RIFF",),
    "image/tiff": (b"II*\x00", b"MM\x00*"),
}


class ImageFailure(RuntimeError):
    """一次图像网关调用的分类失败；消息里不得含提示词、图片字节、密钥或签名地址。"""

    def __init__(self, family: str, code: str, message: str, *, retry_policy: str,
                 http_status: int | None = None, request_id: str | None = None,
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        assert_vocabulary(family, retry_policy)
        self.family = family
        self.code = code
        self.message = message
        self.retry_policy = retry_policy
        self.http_status = http_status
        self.request_id = request_id
        self.details = dict(details or {})

    @property
    def unknown(self) -> bool:
        return self.family == UNKNOWN_FAMILY

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


def validate_size(size: str) -> str:
    """模型合同里的尺寸范围：384..2048 边长、面积与长宽比都有上下限。"""

    if not isinstance(size, str) or not SIZE_PATTERN.fullmatch(size):
        raise ValueError("图像尺寸必须是「宽*高」格式。")
    width, height = (int(value) for value in size.split("*", 1))
    if (
        not 384 <= width <= 2048
        or not 384 <= height <= 2048
        or not 512 * 512 <= width * height <= 2048 * 2048
        or not 1 / 8 <= width / height <= 8
    ):
        raise ValueError("图像尺寸超出模型合同范围。")
    return size


class ReferenceImageIn(BaseModel):
    """一张参考图：角色 + 媒体类型 + 调用方记录的 sha256 + base64 字节。"""

    model_config = ConfigDict(extra="forbid")

    role: str
    media_type: str
    sha256: str
    data_base64: str

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in IMAGE_ROLES:
            raise ValueError(f"参考图角色不在词表内：{value}")
        return value

    @field_validator("media_type")
    @classmethod
    def _media_type(cls, value: str) -> str:
        if value not in _MEDIA_SIGNATURES:
            raise ValueError(f"参考图格式不受支持：{value}")
        return value

    @field_validator("sha256")
    @classmethod
    def _sha(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value or ""):
            raise ValueError("参考图 sha256 必须是 64 位小写十六进制。")
        return value

    @model_validator(mode="after")
    def _content(self) -> "ReferenceImageIn":
        content = decode_base64(self.data_base64, field="references.data_base64")
        if not content:
            raise ValueError("参考图内容为空。")
        if len(content) > MAX_REFERENCE_BYTES:
            raise ValueError(f"参考图超过 {MAX_REFERENCE_BYTES} 字节上限。")
        signatures = _MEDIA_SIGNATURES[self.media_type]
        if not any(content.startswith(item) for item in signatures):
            raise ValueError("参考图字节与声明的媒体类型不一致。")
        digest = hashlib.sha256(content).hexdigest()
        if digest != self.sha256:
            raise ValueError("参考图 sha256 与字节不一致。")
        return self

    def content(self) -> bytes:
        return decode_base64(self.data_base64, field="references.data_base64")


def decode_base64(value: str, *, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} 不能为空。")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{field} 不是合法 base64。") from None


class SubmitRequest(BaseModel):
    """一次提交的完整输入；出现额外字段（含目录/工作空间）即拒绝。"""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    prompt: str
    references: list[ReferenceImageIn]
    size: str = DEFAULT_SIZE
    seed: int | None = None
    model_id: str | None = None

    @field_validator("action_id")
    @classmethod
    def _action(cls, value: str) -> str:
        if not ACTION_ID_PATTERN.fullmatch(value or ""):
            raise ValueError("action_id 必须是 8–64 位的稳定标识。")
        return value

    @field_validator("prompt")
    @classmethod
    def _prompt(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("图像提示词不能为空。")
        if len(value) > MAX_PROMPT_CHARS:
            raise ValueError(f"图像提示词超过 {MAX_PROMPT_CHARS} 字上限。")
        return value

    @field_validator("size")
    @classmethod
    def _size(cls, value: str) -> str:
        return validate_size(value)

    @field_validator("seed")
    @classmethod
    def _seed(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2147483647:
            raise ValueError("随机种子必须是 0 至 2147483647 的整数。")
        return value

    @field_validator("model_id")
    @classmethod
    def _model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not MODEL_ID_PATTERN.fullmatch(value):
            raise ValueError("模型标识不合法。")
        return value

    @field_validator("references")
    @classmethod
    def _references(cls, value: list[ReferenceImageIn]) -> list[ReferenceImageIn]:
        if not value:
            raise ValueError("图生图至少需要一张参考图。")
        if len(value) > MAX_REFERENCE_IMAGES:
            raise ValueError(f"一次最多使用 {MAX_REFERENCE_IMAGES} 张参考图。")
        return value


class TaskRequest(BaseModel):
    """按 task id 查询状态或取回结果；服务端不保存任务表。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str

    @field_validator("task_id")
    @classmethod
    def _task(cls, value: str) -> str:
        if not TASK_ID_PATTERN.fullmatch(value or ""):
            raise ValueError("任务编号不合法。")
        return value


@dataclass(frozen=True, slots=True)
class ImageTaskResult:
    """网关对外可观察的任务状态；签名结果地址留在进程内，不进这个对象。"""

    provider_id: str
    model_id: str
    task_id: str | None
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"]
    result_count: int = 0
    error: str | None = None
    request_id: str | None = None
    unknown: bool = False

    def __post_init__(self) -> None:
        if self.status not in TASK_STATUSES:
            raise ValueError(f"未知任务状态：{self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": {"provider_id": self.provider_id, "model_id": self.model_id},
            "task_id": self.task_id,
            "status": self.status,
            "result_count": int(self.result_count),
            "error": self.error,
            "request_id": self.request_id,
            "unknown": bool(self.unknown),
        }
