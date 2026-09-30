"""确定性的假复核 Provider（V2.5.2）。

它是测试替身，不是产品能力：
  - 发现内容只由 scenario 与输入身份（sha256 前缀）决定，不联网、不读工作空间、不写状态；
  - 覆盖正常、无发现、超时 Unknown、非法输出、拒绝、限流、HTTP 错误、鉴权失败与内部错误；
  - 记录 calls，用来证明调用方不会在 Unknown 之后自动重提。

真实模型只在完成证据阶段用 ``v2_dashscope_review`` 调用最少次数（计划 §12.2）。
"""
from __future__ import annotations

from typing import Any

from src.providers.v2_review import DecodedReviewRequest, ReviewResult
from src.providers.v2_semantic import (classify_http_failure, classify_transport_failure,
                                       internal_failure, invalid_response, refused)

FAKE_PROVIDER_ID = "fake-review"
FAKE_MODEL_ID = "fake-qwen-vl-max"
FAKE_CHECKED_AT = "2026-09-30T00:00:00Z"

FAKE_SCENARIOS = (
    "ok",
    "clean",
    "unknown",
    "timeout_before_send",
    "invalid_output",
    "refusal",
    "rate_limited",
    "http_error",
    "auth_failed",
    "internal_error",
)


class FakeReviewProvider:
    """scenario 驱动的假复核 Provider；calls 记录每次请求，证明没有隐藏重提。"""

    provider_id = FAKE_PROVIDER_ID
    model_id = FAKE_MODEL_ID
    supports_reference_images = True

    def __init__(self, scenario: str = "ok", *, latency_ms: int = 0) -> None:
        self.scenario = scenario
        self.latency_ms = latency_ms
        self.calls: list[dict[str, Any]] = []

    def capabilities(self) -> dict[str, Any]:
        """测试替身能力声明；与 config/product-v2/providers.json 的 fake-review 条目一致。"""

        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "reference_images": True,
            "structured_output": "local",
            "stateless": True,
            "test_double": True,
            "scenario": self.scenario,
        }

    def review(self, request: DecodedReviewRequest, *, scenario: str | None = None) -> ReviewResult:
        scenario = scenario or self.scenario
        self.calls.append({
            "scenario": scenario,
            "candidate_sha256": request.candidate.sha256,
            "references": len(request.references),
        })
        if scenario not in FAKE_SCENARIOS:
            raise invalid_response(f"未知假场景 {scenario!r}。",
                                   details={"allowed": list(FAKE_SCENARIOS)})
        if scenario == "unknown":
            raise classify_transport_failure("timeout_after_send", "假复核 Provider：读取超时，无法确认结果。")
        if scenario == "timeout_before_send":
            raise classify_transport_failure("timeout_before_send", "假复核 Provider：连接超时，没有发出请求。")
        if scenario == "invalid_output":
            raise invalid_response("假复核 Provider：输出不符合结构契约；整包拒绝。")
        if scenario == "refusal":
            raise refused("假复核 Provider：模型拒绝复核该输入。")
        if scenario == "rate_limited":
            raise classify_http_failure(429, "Throttling", "假复核 Provider：限流。")
        if scenario == "http_error":
            raise classify_http_failure(503, "ServiceUnavailable", "假复核 Provider：服务不可用。")
        if scenario == "auth_failed":
            raise classify_http_failure(401, "InvalidApiKey", "假复核 Provider：鉴权失败。")
        if scenario == "internal_error":
            raise internal_failure("假复核 Provider：内部错误。")

        findings: list[dict[str, Any]] = []
        if scenario == "ok":
            prefix = request.candidate.sha256[:8]
            findings.append({
                "check": "deformity",
                "evidence": f"假数据（{prefix}）：杯口边缘出现第二道不自然的弧线。",
                "confidence": 0.72,
            })
            findings.append({
                "check": "garbled_text",
                "evidence": f"假数据（{prefix}）：底部标签文字出现乱码笔画。",
                "confidence": 0.58,
            })
        return ReviewResult(
            findings=tuple(findings),
            summary="假复核 Provider：仅用于契约测试与界面开发。",
            provider_id=FAKE_PROVIDER_ID,
            model_id=FAKE_MODEL_ID,
            request_id="fake-review-" + str(len(self.calls)),
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            latency_ms=self.latency_ms,
            candidate_sha256=request.candidate.sha256,
            reference_images_sent=bool(request.references),
            checked_at=FAKE_CHECKED_AT,
        )
