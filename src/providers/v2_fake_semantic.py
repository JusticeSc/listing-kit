"""确定性的假语义 Provider（V2.2.2）。

它是测试替身，不是产品能力：
  - 内容只由输入投影决定，不联网、不读工作空间、不写业务状态；
  - 通过 scenario（构造函数默认值或逐次显式传入）覆盖正常、低置信、冲突、拒绝、超时、
    非法响应、输出截断与空可见文本等路径；
  - 记录 calls，用来证明调用方不会在 Unknown 之后自动重提。

真实模型只在完成证据阶段用 ``v2_dashscope_semantic`` 调用最少次数（计划 §12.2）。
"""
from __future__ import annotations

from typing import Any, Mapping

from src.providers.v2_semantic import (
    SemanticFailure,
    SemanticProposal,
    SemanticRequest,
    classify_http_failure,
    classify_transport_failure,
    internal_failure,
    invalid_response,
    output_truncated,
    refused,
)
from src.providers.v2_dashscope_semantic import DEFAULT_MAX_TOKENS

FAKE_PROVIDER_ID = "fake-semantic"
FAKE_MODEL_ID = "fake-deepseek-v4.1-flash"

FAKE_SCENARIOS = (
    "ok",
    "low_confidence",
    "conflict",
    "refusal",
    "invalid_json",
    "schema_violation",
    "output_truncated",
    "empty_output",
    "timeout_after_send",
    "timeout_before_send",
    "unreachable",
    "rate_limited",
    "http_error",
    "auth_failed",
    "internal_error",
)


def _slot(slot_id: str, label: str, authority: str, value_type: str, value: Any,
          confidence: float, *, critical: bool | None = None,
          depends_on: list[str] | None = None, note: str = "") -> dict[str, Any]:
    slot: dict[str, Any] = {
        "schema_version": 1,
        "slot_id": slot_id,
        "label": label,
        "authority": authority,
        "value_type": value_type,
        "value": value,
        "source": "model_inference",
        "status": "proposed",
        "confidence": confidence,
        "evidence": [{"kind": "model", "ref": FAKE_MODEL_ID,
                      "note": note or "假 Provider：仅用于契约与界面开发。"}],
        "depends_on": list(depends_on or []),
        "model_id": FAKE_MODEL_ID,
    }
    if critical is not None:
        slot["critical"] = critical
    return slot


class FakeSemanticProvider:
    """scenario 驱动的假 Provider；calls 记录每次请求，证明没有隐藏重提。

    scenario 可注入构造函数（服务端测试替身按环境选择），也可逐次调用传入（用例内切换）。
    """

    provider_id = FAKE_PROVIDER_ID
    model_id = FAKE_MODEL_ID
    supports_images = False

    def capabilities(self) -> dict[str, Any]:
        """测试替身能力声明；与 config/product-v2/providers.json 的 fake-semantic 条目一致。"""

        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "reference_images": False,
            "structured_output": "local",
            "stateless": True,
            "test_double": True,
            "scenario": self.scenario,
        }

    def __init__(self, scenario: str = "ok", *, latency_ms: int = 0,
                 existing_values: Mapping[str, Any] | None = None,
                 category_hint: str | None = None) -> None:
        self.scenario = scenario
        self.latency_ms = latency_ms
        self.existing_values = dict(existing_values or {})
        self.category_hint = category_hint
        self.calls: list[dict[str, Any]] = []

    def analyze(self, request: SemanticRequest, *, scenario: str | None = None,
                existing_values: Mapping[str, Any] | None = None,
                category_hint: str | None = None) -> SemanticProposal:
        scenario = scenario or self.scenario
        existing_values = existing_values if existing_values is not None else self.existing_values
        category_hint = category_hint if category_hint is not None else self.category_hint
        self.calls.append({"scenario": scenario, "product_name": request.product_name})
        if scenario not in FAKE_SCENARIOS:
            raise invalid_response(f"未知假场景 {scenario!r}。",
                                   details={"allowed": list(FAKE_SCENARIOS)})
        if scenario == "refusal":
            raise refused("假 Provider：模型拒绝分析该输入。")
        if scenario == "invalid_json":
            raise invalid_response("假 Provider：上游返回的不是 JSON。")
        if scenario == "output_truncated":
            raise output_truncated("假 Provider：模型输出被 max_tokens 截断。",
                                   details={"max_tokens": DEFAULT_MAX_TOKENS})
        if scenario == "empty_output":
            raise invalid_response("假 Provider：模型只产生了 reasoning，没有可见文本。",
                                   details={"max_tokens": DEFAULT_MAX_TOKENS,
                                            "usage": {"completion_tokens": 64}})
        if scenario == "timeout_after_send":
            raise classify_transport_failure("timeout_after_send", "假 Provider：读取超时。")
        if scenario == "timeout_before_send":
            raise classify_transport_failure("timeout_before_send", "假 Provider：连接超时。")
        if scenario == "unreachable":
            raise classify_transport_failure("unreachable", "假 Provider：无法连接。")
        if scenario == "rate_limited":
            raise classify_http_failure(429, "Throttling", "假 Provider：限流。")
        if scenario == "http_error":
            raise classify_http_failure(503, "ServiceUnavailable", "假 Provider：服务不可用。")
        if scenario == "auth_failed":
            raise classify_http_failure(401, "InvalidApiKey", "假 Provider：鉴权失败。")
        if scenario == "internal_error":
            raise internal_failure("假 Provider：内部错误。")

        confidence = 0.35 if scenario == "low_confidence" else 0.9
        confirmed = dict(existing_values or {})
        category = category_hint or confirmed.get("product_category") or "通用品类（假数据）"
        if scenario == "conflict":
            category = "与已确认值不同的品类（假数据）"
        slots: list[dict[str, Any]] = [
            _slot("product_name", "商品名称", "core_fixed", "text", request.product_name,
                  confidence, critical=True, note="取自本次商品资料。"),
            _slot("product_category", "商品品类", "core_fixed", "text", category,
                  confidence, critical=True, note="假 Provider 的品类占位，需人工确认。"),
        ]
        features = list(request.selling_points) or (["（卖点待补充）"] if request.focus else [])
        if features:
            slots.append(_slot("signature_features", "必须保持的商品特征", "core_fixed",
                               "text_list", features, confidence, critical=True,
                               note="假 Provider 直接引用卖点文本。"))
        if request.focus:
            slots.append(_slot("usage_scene", "使用场景", "category_dynamic", "text",
                               request.focus[:80], confidence, depends_on=["product_category"],
                               note="来自本次重点。"))
        if request.description:
            slots.append(_slot("description_digest", "介绍摘要", "category_dynamic", "text",
                               request.description[:120], confidence,
                               depends_on=["product_category"],
                               note="来自商品介绍。"))
        if scenario == "schema_violation":
            # 故意违反契约：模型不得把提案直接标成 confirmed。
            broken = _slot("brand", "品牌", "core_fixed", "text", "假品牌", confidence,
                           critical=False)
            broken["status"] = "confirmed"
            slots.append(broken)
        questions = ()
        if not request.selling_points:
            questions = ("这个商品最不能出错的卖点是哪一条？",)
        return SemanticProposal(
            slots=tuple(slots),
            questions=tuple(questions),
            summary="假 Provider 提案：仅用于契约测试与界面开发。",
            provider_id=FAKE_PROVIDER_ID,
            model_id=FAKE_MODEL_ID,
            request_id="fake-" + str(len(self.calls)),
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            latency_ms=self.latency_ms,
            inputs_used=("product_input",),
            reference_images_sent=False,
        )
