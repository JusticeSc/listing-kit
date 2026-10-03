"""Product V2 图像网关的测试替身（V2.4.1）。

作用：让「提交 → 查询 → 取回结果」这条链路在没有密钥、没有网络时可验证。
它只做真实 provider 同形的事，不额外造业务结论：

  - 任务身份由 action_id 决定，因此同样的输入必须得到同样的 task id 与同样的图片 hash；
  - 提交后是 RUNNING，查询时按任务时间线推进到 SUCCEEDED，图片字节由 task id 确定性派生；
  - 每次请求都会新建一个实例（服务端不保存任务表），所以查询与取回都不能依赖「之前调用过」：
    同一个 task id 在任意一个实例上都给出同样的答案。
  - 场景 ``submit_unknown`` / ``status_unknown`` 用来验证 Unknown 语义，``failed`` 验证明确失败。

``calls`` 计数供验证器观察「这条路有没有真的联网」——替身自己永不发起请求。
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from typing import Any

from src.providers.v2_image import (IMAGE_MODEL_ID, IMAGE_PROVIDER_ID, ImageFailure,
                                    ImageTaskResult, SubmitRequest, TaskRequest,
                                    image_request_profile)

FAKE_SCENARIOS = ("ok", "failed", "submit_unknown", "status_unknown", "download_failed")
FAKE_PROVIDER_ID = "fake-qwen-image"


class FakeImageProvider:
    """确定性替身；``scenario`` 决定哪一步失败，默认整条链路成功。"""

    configured = True
    DEFAULT_SIZE = 64

    def __init__(self, scenario: str = "ok", *, size: int = DEFAULT_SIZE) -> None:
        if scenario not in FAKE_SCENARIOS:
            raise ValueError(f"未知的假 provider 场景：{scenario}")
        self.scenario = scenario
        # 交付门禁有平台长边下限（platform.min_long_side = 1000），验证器需要能生成达标尺寸；
        # 默认仍是 64×64，既有调用与断言不变。
        self.size = max(8, int(size))
        self.provider_id = FAKE_PROVIDER_ID
        self.model_id = IMAGE_MODEL_ID
        # 与 capabilities() 声明一致：服务器能力块读实例属性（V2.R4.3/R4.4 统一口径）。
        self.credential_source = "test_double"
        self.calls: dict[str, int] = {"submit": 0, "status": 0, "result": 0}

    # ------------------------------------------------------------ 能力

    def capabilities(self) -> dict[str, Any]:
        return {
            "contract": "v2.4.1",
            "reference_images": True,
            "max_reference_images": 3,
            "async_tasks": True,
            "n_per_submit": 1,
            "prompt_extend": False,
            "watermark": False,
            "stateless": True,
            "test_double": True,
            "credential_source": "test_double",
            "upstream_provider_id": IMAGE_PROVIDER_ID,
            # V2.R5.3：与真实 qwen 同形状有效 profile（qwen 网关限制口径）。
            "request_profile": image_request_profile(),
        }

    def apply_credentials(self, *, api_key: str) -> None:
        """测试替身没有真实密钥轴；BYOK 请求头对替身是显式 no-op（不落盘、不回显）。"""

        return None

    # ------------------------------------------------------------ 内部

    @staticmethod
    def task_id_for(action_id: str) -> str:
        digest = hashlib.sha256(action_id.encode("utf-8")).hexdigest()[:16]
        return "fake-" + digest

    @staticmethod
    def bytes_for(task_id: str, size: int = 64) -> bytes:
        """按 task id 派生的确定性 PNG（颜色随 id 变化，便于肉眼与 hash 双重核对）。"""

        digest = hashlib.sha256(("png:" + task_id).encode("utf-8")).digest()
        color = (digest[0], digest[1], digest[2])
        width = height = max(8, int(size))
        raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

        def chunk(tag: bytes, payload: bytes) -> bytes:
            return (struct.pack(">I", len(payload)) + tag + payload
                    + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

        header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

    # ------------------------------------------------------------ 三步

    def submit(self, request: SubmitRequest) -> ImageTaskResult:
        self.calls["submit"] += 1
        if self.scenario == "submit_unknown":
            raise ImageFailure(
                "provider_unknown", "PROVIDER_OUTCOME_UNKNOWN",
                "提交响应未能确认，服务端是否受理无法判断；先核对，不要自动重提。",
                retry_policy="requires_review")
        if self.scenario == "failed":
            return ImageTaskResult(
                provider_id=self.provider_id, model_id=self.model_id,
                task_id=self.task_id_for(request.action_id), status="RUNNING")
        return ImageTaskResult(
            provider_id=self.provider_id, model_id=self.model_id,
            task_id=self.task_id_for(request.action_id), status="RUNNING")

    def status(self, request: TaskRequest) -> ImageTaskResult:
        self.calls["status"] += 1
        if self.scenario == "status_unknown":
            raise ImageFailure(
                "provider_unknown", "PROVIDER_STATUS_UNKNOWN",
                "暂时无法确认这个任务的状态；请再次查询原任务，不要重新提交。",
                retry_policy="requires_review")
        if self.scenario == "failed":
            return ImageTaskResult(
                provider_id=self.provider_id, model_id=self.model_id,
                task_id=request.task_id, status="FAILED",
                error="图像生成任务失败（错误码 FAKE_CONTENT_REJECTED）。")
        return ImageTaskResult(
            provider_id=self.provider_id, model_id=self.model_id,
            task_id=request.task_id, status="SUCCEEDED", result_count=1)

    def result(self, request: TaskRequest) -> tuple[bytes, str]:
        self.calls["result"] += 1
        if self.scenario == "download_failed":
            raise ImageFailure(
                "provider_failed", "RESULT_DOWNLOAD_FAILED",
                "结果图片下载失败；没有产生可用的候选字节。",
                retry_policy="retryable")
        if self.scenario == "failed":
            raise ImageFailure(
                "provider_failed", "RESULT_NOT_AVAILABLE",
                "任务没有成功结果可下载。", retry_policy="fatal")
        return self.bytes_for(request.task_id, self.size), "image/png"
