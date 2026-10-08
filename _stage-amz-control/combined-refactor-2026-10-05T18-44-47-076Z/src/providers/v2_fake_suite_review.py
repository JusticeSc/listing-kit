"""确定性的假整套复核 Provider（V2.5.5）。

测试替身，不是产品能力：
  - 发现内容只由 scenario 与输入身份（shot_id / sha256 前缀）决定，不联网、不读工作空间；
  - 覆盖正常、一致（无发现）、跨图漂移、超时 Unknown、非法输出、拒绝、限流与 HTTP 错误；
  - 记录 calls，用来证明调用方不会在 Unknown 之后自动重提，也不会把失败包装成 checked。
"""
from __future__ import annotations

from typing import Any

from src.providers.v2_semantic import (classify_http_failure, classify_transport_failure,
                                       invalid_response, refused)
from src.providers.v2_suite_review import (SUITE_REVIEW_CONTRACT_VERSION,
                                           DecodedSuiteReviewRequest, SuiteReviewResult)

FAKE_PROVIDER_ID = "fake-review"
FAKE_MODEL_ID = "fake-qwen-vl-max"
FAKE_CHECKED_AT = "2026-10-01T00:00:00Z"

FAKE_SCENARIOS = (
    "ok",              # 一致：无发现
    "drift",           # 跨图漂移：商品外观 + 风格各一条
    "unknown",         # 读超时：结果不可知
    "timeout_before_send",
    "invalid_output",
    "refusal",
    "rate_limited",
    "http_error",
    "over_limit",      # 模拟上游张数上限（正常不会触发：浏览器侧先按 8 张截断并记 Unknown）
)


class FakeSuiteReviewProvider:
    """scenario 驱动的假整套复核 Provider；calls 记录每次请求。"""

    provider_id = FAKE_PROVIDER_ID
    model_id = FAKE_MODEL_ID
    supports_reference_images = True

    def __init__(self, scenario: str = "ok", *, latency_ms: int = 0) -> None:
        self.scenario = scenario
        self.latency_ms = latency_ms
        # 与 capabilities() 声明一致：服务器能力块读实例属性（V2.R4.3/R4.4 统一口径）。
        self.credential_source = "test_double"
        self.calls: list[dict[str, Any]] = []

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "suite_review_contract": SUITE_REVIEW_CONTRACT_VERSION,
            "max_images": 8,
            "reference_images": True,
            "structured_output": "local",
            "stateless": True,
            "test_double": True,
            "credential_source": "test_double",
            "scenario": self.scenario,
        }

    def apply_credentials(self, *, api_key: str) -> None:
        """测试替身没有真实密钥轴；BYOK 请求头对替身是显式 no-op（不落盘、不回显）。"""

        return None

    def review(self, request: DecodedSuiteReviewRequest, *,
               scenario: str | None = None) -> SuiteReviewResult:
        scenario = scenario or self.scenario
        self.calls.append({
            "scenario": scenario,
            "shot_ids": list(request.shot_ids),
            "sha256": [item.sha256[:8] for item in request.images],
        })
        if scenario not in FAKE_SCENARIOS:
            raise invalid_response(f"未知假场景 {scenario!r}。",
                                   details={"allowed": list(FAKE_SCENARIOS)})
        if scenario == "unknown":
            raise classify_transport_failure("timeout_after_send",
                                             "假整套复核 Provider：读取超时，无法确认结果。")
        if scenario == "timeout_before_send":
            raise classify_transport_failure("timeout_before_send",
                                             "假整套复核 Provider：连接超时，没有发出请求。")
        if scenario == "invalid_output":
            raise invalid_response("假整套复核 Provider：输出不符合结构契约；整包拒绝。")
        if scenario == "refusal":
            raise refused("假整套复核 Provider：模型拒绝复核该输入。")
        if scenario == "rate_limited":
            raise classify_http_failure(429, "Throttling", "假整套复核 Provider：限流。")
        if scenario == "http_error":
            raise classify_http_failure(503, "ServiceUnavailable", "假整套复核 Provider：服务不可用。")
        if scenario == "over_limit":
            raise invalid_response("假整套复核 Provider：送审张数超过上游上限。",
                                   details={"max_images": 8, "sent": len(request.images)})

        findings: list[dict[str, Any]] = []
        if scenario == "drift":
            shot_ids = list(request.shot_ids)
            findings.append({
                "check": "suite_product_consistency",
                "shot_ids": shot_ids[:min(2, len(shot_ids))],
                "evidence": "假数据：两张图里的商品高光位置与瓶身比例不一致。",
                "confidence": 0.74,
            })
            findings.append({
                "check": "suite_style_consistency",
                "shot_ids": shot_ids,
                "evidence": "假数据：整组背景色温与投影方向不统一。",
                "confidence": 0.61,
            })
        summary = (f"假整套复核 Provider：已核对 {len(request.images)} 张，发现 {len(findings)} 条提示。"
                   if findings else
                   f"假整套复核 Provider：已核对 {len(request.images)} 张，未发现跨图问题。")
        return SuiteReviewResult(
            findings=tuple(findings),
            summary=summary,
            provider_id=FAKE_PROVIDER_ID,
            model_id=FAKE_MODEL_ID,
            request_id="fake-suite-review-" + str(len(self.calls)),
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            latency_ms=self.latency_ms,
            checked_shot_ids=request.shot_ids,
            state="checked",
            checked_at=FAKE_CHECKED_AT,
        )
