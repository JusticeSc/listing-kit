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
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.providers.v2_errors import (ERROR_FAMILIES, RETRY_POLICIES, UNKNOWN_FAMILY,
                                     assert_vocabulary)

IMAGE_CONTRACT_VERSION = "v2.4.1"
# 能力声明版本（V2.R4.4/R5.2）：正整数，随「图像网关能力块内容变化」前移（R4.3 加入凭据来源、
# R4.4 加入执行身份核对、R5.2 加入同步协议标志与第二真实协议）。前端冻结进 attempt 身份；
# 换版本后旧任务按原能力版本核对。
IMAGES_CAPABILITY_VERSION = 3
IMAGE_PROVIDER_ID = "dashscope-qwen-image"
IMAGE_MODEL_ID = "qwen-image-3.0"
DEFAULT_SIZE = "1344*1344"

MAX_REFERENCE_IMAGES = 3
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_PROMPT_CHARS = 4000

# 产品网关当前保守请求限制（V2.R5.3）：不是已证供应商官方范围。边 384..2048、
# 面积与长宽比上下限沿用网关实际限制；flash 官方像素面积下界 921600 由父级官源
# 核对（URL Source），仅 flash 的 min_area 取该值，其余不扩张。
QWEN_MIN_AREA = 512 * 512
FLASH_MIN_AREA = 921600
PROFILE_MAX_AREA = 2048 * 2048
PROFILE_MIN_SIDE = 384
PROFILE_MAX_SIDE = 2048
PROFILE_MIN_RATIO = 1 / 8
PROFILE_MAX_RATIO = 8
PROFILE_REFERENCE_MEDIA_TYPES = ("image/png", "image/jpeg")


def image_request_profile(*, min_area: int = QWEN_MIN_AREA) -> dict[str, Any]:
    """返回非秘密的请求 profile（V2.R5.3）：纯业务投影，不含任何凭据。"""
    return {
        "size": DEFAULT_SIZE,
        "n": 1,
        "prompt_extend": False,
        "watermark": False,
        "output_format": "png",
        "supports_negative_prompt_field": False,
        "max_reference_images": MAX_REFERENCE_IMAGES,
        "reference_media_types": list(PROFILE_REFERENCE_MEDIA_TYPES),
        "min_side": PROFILE_MIN_SIDE,
        "max_side": PROFILE_MAX_SIDE,
        "min_area": min_area,
        "max_area": PROFILE_MAX_AREA,
        "min_ratio": PROFILE_MIN_RATIO,
        "max_ratio": PROFILE_MAX_RATIO,
        "max_prompt_chars": MAX_PROMPT_CHARS,
    }


def profile_violation(request: SubmitRequest, profile: Any) -> str | None:
    """按 resolved provider 的 request_profile 核验已校验请求（V2.R5.3 纯业务函数）。

    Pydantic 层已执行网关共有限制（尺寸格式/边/面积/比例、提示词非空/长度、参考图
    数量/字节/签名/sha256）；这里只核对 profile 声明的请求子集差异（flash 面积下界、
    参考媒体类型白名单等）。返回 None 表示通过，否则返回不含秘密的拒绝原因（只含
    计数与参数名，不含提示词正文、图片字节、密钥）。
    """
    if not isinstance(profile, Mapping):
        return "当前 provider 没有可用的 request_profile；不能确认请求是否在其能力内。"
    try:
        max_refs = int(profile["max_reference_images"])
        allowed_media = tuple(profile["reference_media_types"])
        min_side = int(profile["min_side"])
        max_side = int(profile["max_side"])
        min_area = int(profile["min_area"])
        max_area = int(profile["max_area"])
        max_prompt = int(profile["max_prompt_chars"])
    except (KeyError, TypeError, ValueError):
        return "当前 provider 的 request_profile 不完整；不能确认请求是否在其能力内。"
    if len(request.prompt) > max_prompt:
        return f"图像提示词超过当前 provider {max_prompt} 字上限。"
    if len(request.references) > max_refs:
        return f"一次最多使用 {max_refs} 张参考图。"
    for item in request.references:
        if item.media_type not in allowed_media:
            return f"参考图格式 {item.media_type} 不在当前 provider 能力内。"
    try:
        width_raw, height_raw = request.size.split("*", 1)
        width, height = int(width_raw), int(height_raw)
    except (ValueError, AttributeError):
        return "图像尺寸不符合 request_profile 要求。"
    if (not min_side <= width <= max_side or not min_side <= height <= max_side
            or not min_area <= width * height <= max_area):
        return "图像尺寸不在当前 provider 能力范围内。"
    return None


MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
ACTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
SIZE_PATTERN = re.compile(r"^[0-9]{1,4}\*[0-9]{1,4}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXECUTION_PROTOCOL_PATTERN = re.compile(r"^v[0-9A-Za-z._-]{1,40}$")

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


class ExecutionTarget(BaseModel):
    """冻结执行身份的目标投影（V2.R4.4）：目的地不是猜测源，只按这里给的核对。

    浏览器在提交/核对前把 attempt 冻结身份（协议/目标/模型/能力版本）随请求带上；
    服务端只接受与**本进程图像 provider 身份**和契约版本完全一致的 target，
    不一致即 400 EXECUTION_IDENTITY_MISMATCH（不转发、不查库、不调用模型）。
    target 缺省（老验证工具直发）仍按现状处理：本字段是产品路径的强制口径，
    网关保持对省略请求的既有语义。
    """

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    model_id: str
    protocol: str
    capability_version: int

    @field_validator("provider_id")
    @classmethod
    def _provider(cls, value: str) -> str:
        if not MODEL_ID_PATTERN.fullmatch(value or ""):
            raise ValueError("target.provider_id 不合法。")
        return value

    @field_validator("model_id")
    @classmethod
    def _model(cls, value: str) -> str:
        if not MODEL_ID_PATTERN.fullmatch(value or ""):
            raise ValueError("target.model_id 不合法。")
        return value

    @field_validator("protocol")
    @classmethod
    def _protocol(cls, value: str) -> str:
        if not EXECUTION_PROTOCOL_PATTERN.fullmatch(value or ""):
            raise ValueError("target.protocol 必须是 v 开头的契约版本号。")
        return value

    @field_validator("capability_version")
    @classmethod
    def _capability(cls, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("target.capability_version 必须是正整数。")
        return value


class SubmitRequest(BaseModel):
    """一次提交的完整输入；出现额外字段（含目录/工作空间）即拒绝。

    V2.R5.3：``n``/``prompt_extend``/``watermark``/``output_format`` 是冻结请求参数，
    只接受产品网关当前实际发送的固定值（单图、不扩展、不水印、PNG）；其他值直接
    拒绝。产品路径发送时显式冻结这些参数；省略时使用同一固定请求档。
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str
    prompt: str
    references: list[ReferenceImageIn]
    size: str = DEFAULT_SIZE
    seed: int | None = None
    model_id: str | None = None
    target: ExecutionTarget | None = None
    n: Literal[1] = 1
    prompt_extend: Literal[False] = False
    watermark: Literal[False] = False
    output_format: Literal["png"] = "png"

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
    """按 task id 查询状态或取回结果；服务端不保存任务表。

    target（V2.R4.4）：可选的冻结执行身份投影。浏览器核对旧任务时**总是**携带它；
    服务端与当前 provider 身份/契约版本不符时直接 400 EXECUTION_IDENTITY_MISMATCH，
    保证「同 task 不同 target 不串」，不偷用当前配置查询旧任务。
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    target: ExecutionTarget | None = None

    @field_validator("task_id")
    @classmethod
    def _task(cls, value: str) -> str:
        if not TASK_ID_PATTERN.fullmatch(value or ""):
            raise ValueError("任务编号不合法。")
        return value


@dataclass(frozen=True, slots=True)
class ImageTaskResult:
    """网关对外可观察的任务状态；签名结果地址留在进程内，不进这个对象。

    V2.R5.2：同步协议适配器（火山方舟 flash）在提交响应里一次性给出结果字节；
    ``sync_result`` 只在进程内存活（不进 ``to_dict``，不落任何持久化层），浏览器
    在同一次信封里拿到字节；``task_id`` 为 None 表示「同步协议没有 task 身份」，
    伪造 task id 是被明确禁止的。
    """

    provider_id: str
    model_id: str
    task_id: str | None
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"]
    result_count: int = 0
    error: str | None = None
    request_id: str | None = None
    unknown: bool = False
    sync_result: tuple[bytes, str] | None = None

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
            # V2.R5.2 同步协议标志：只在同步协议出现（浏览器靠它承认「task_id 为空 +
            # 明确状态」的提交信封；异步 provider 的响应不携带这个键）。
            "sync": bool(self.sync_result is not None),
        }
