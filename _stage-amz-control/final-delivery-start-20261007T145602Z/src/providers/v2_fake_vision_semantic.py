"""确定性的假看图语义 Provider（test-only，packet08）。

它是 `FakeSemanticProvider` 的看图孪生：离线可验证「设置里选了看图档 →
页面真正发出图片字节 → 网关 decode 验 hash → 提案记 actual_images」的整条
有效配置贯通链，不联网、不读工作空间、不写业务状态。

与纯文本替身的区别只有三处（其余行为、场景词表、槽位形状照抄）：
  - ``supports_images = True``，capabilities 声明 reference_images/vision；
  - ``analyze(request, images)`` 要求非空 images（网关已 decode 验 hash，
    这里只记录收到的字节身份，不重验）；
  - proposals 的 inputs_used 含 actual_images、reference_images_sent=True；
  - ``calls`` 逐次记录收到图片的 role/media_type/sha256/byte_size，供验证器
    把「fake 收到的字段」与「页面所示配置」逐字对照（密钥不记录）。

注册方式照抄 ``v2_fake_semantic``：``src/providers/v2_registry.py`` 的
``create_semantic_provider`` 按 adapter 名 ``v2_fake_vision_semantic`` 构造，
场景经 ``AMZ_V2_FAKE_SEMANTIC_SCENARIO`` 注入；provider id 固定
``fake-vision-semantic``，只在显式注入测试接缝里可见，生产目录永不含 fake。
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from src.providers.v2_fake_semantic import _slot
from src.providers.v2_fake_semantic import FAKE_SCENARIOS
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
from src.providers.v2_semantic import ANALYZE_BASE_FIELDS
from src.providers.v2_dashscope_semantic import DEFAULT_MAX_TOKENS

FAKE_VISION_PROVIDER_ID = "fake-vision-semantic"
FAKE_VISION_MODEL_ID = "fake-qwen-vl-max"


class FakeVisionSemanticProvider:
    provider_id = FAKE_VISION_PROVIDER_ID
    model_id = FAKE_VISION_MODEL_ID
    supports_images = True

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "configured": True,
            "semantic_contract": "v2.2.2",
            "vision_contract": "v2.2.2-vision",
            "reference_images": True,
            "supports_images": True,
            "vision": True,
            "max_reference_images": 3,
            "max_reference_bytes": 4 * 1024 * 1024,
            "analyze_fields": [*list(ANALYZE_BASE_FIELDS), "reference_images"],
            "structured_output": "local",
            "stateless": True,
            "test_double": True,
            "credential_source": "test_double",
            "scenario": self.scenario,
        }

    def apply_credentials(self, *, api_key: str) -> None:
        """测试替身没有真实密钥轴；BYOK 请求头对替身是显式 no-op（不落盘、不回显）。"""

        return None

    def __init__(self, scenario: str = "ok", *, latency_ms: int = 0,
                 existing_values: Mapping[str, Any] | None = None,
                 category_hint: str | None = None) -> None:
        self.scenario = scenario
        self.latency_ms = latency_ms
        self.existing_values = dict(existing_values or {})
        self.category_hint = category_hint
        self.credential_source = "test_double"
        self.calls: list[dict[str, Any]] = []

    def analyze(self, request: SemanticRequest, images: Any = None, *,
                scenario: str | None = None,
                existing_values: Mapping[str, Any] | None = None,
                category_hint: str | None = None) -> SemanticProposal:
        scenario = scenario or self.scenario
        existing_values = existing_values if existing_values is not None else self.existing_values
        category_hint = category_hint if category_hint is not None else self.category_hint
        received: list[dict[str, Any]] = []
        for item in images or ():
            data = getattr(item, "data", None)
            digest = getattr(item, "sha256", None)
            if isinstance(data, (bytes, bytearray)):
                digest = hashlib.sha256(bytes(data)).hexdigest()
            received.append({
                "role": getattr(item, "role", None),
                "media_type": getattr(item, "media_type", None),
                "sha256": digest,
                "byte_size": len(data) if isinstance(data, (bytes, bytearray)) else None,
            })
        self.calls.append({"scenario": scenario, "product_name": request.product_name,
                           "vision_images": len(received), "images": received})
        if scenario not in FAKE_SCENARIOS:
            raise invalid_response(f"未知假场景 {scenario!r}。",
                                   details={"allowed": list(FAKE_SCENARIOS)})
        if not received:
            raise SemanticFailure("input_rejected", "VISION_BYTES_REQUIRED",
                                  "看图理解需要至少一张已校验的参考图字节（reference_images 1..3 张）；"
                                  "这次请求没有调用模型。",
                                  retry_policy="fatal")
        if scenario == "refusal":
            raise refused("假看图 Provider：模型拒绝分析该输入。")
        if scenario == "invalid_json":
            raise invalid_response("假看图 Provider：上游返回的不是 JSON。")
        if scenario == "output_truncated":
            raise output_truncated("假看图 Provider：模型输出被 max_tokens 截断。",
                                   details={"max_tokens": DEFAULT_MAX_TOKENS})
        if scenario == "empty_output":
            raise invalid_response("假看图 Provider：模型只产生了 reasoning，没有可见文本。",
                                   details={"max_tokens": DEFAULT_MAX_TOKENS,
                                            "usage": {"completion_tokens": 64}})
        if scenario == "timeout_after_send":
            raise classify_transport_failure("timeout_after_send", "假看图 Provider：读取超时。")
        if scenario == "timeout_before_send":
            raise classify_transport_failure("timeout_before_send", "假看图 Provider：连接超时。")
        if scenario == "unreachable":
            raise classify_transport_failure("unreachable", "假看图 Provider：无法连接。")
        if scenario == "rate_limited":
            raise classify_http_failure(429, "Throttling", "假看图 Provider：限流。")
        if scenario == "http_error":
            raise classify_http_failure(503, "ServiceUnavailable", "假看图 Provider：服务不可用。")
        if scenario == "auth_failed":
            raise classify_http_failure(401, "InvalidApiKey", "假看图 Provider：鉴权失败。")
        if scenario == "internal_error":
            raise internal_failure("假看图 Provider：内部错误。")

        confidence = 0.35 if scenario == "low_confidence" else 0.9
        confirmed = dict(existing_values or {})
        category = category_hint or confirmed.get("product_category") or "通用品类（假看图数据）"
        if scenario == "conflict":
            category = "与已确认值不同的品类（假看图数据）"
        slots: list[dict[str, Any]] = [
            _slot("product_name", "商品名称", "core_fixed", "text", request.product_name,
                  confidence, critical=True, note="取自本次商品资料（看图替身同样只引用文字）。"),
            _slot("product_category", "商品品类", "core_fixed", "text", category,
                  confidence, critical=True, note="假看图 Provider 的品类占位，需人工确认。"),
        ]
        features = list(request.selling_points) or (["（卖点待补充）"] if request.focus else [])
        if features:
            slots.append(_slot("signature_features", "必须保持的商品特征", "core_fixed",
                               "text_list", features, confidence, critical=True,
                               note="假看图 Provider 直接引用卖点文本。"))
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
            summary="假看图 Provider 提案：已收到实际图片字节，仅用于有效配置贯通验证。",
            provider_id=FAKE_VISION_PROVIDER_ID,
            model_id=FAKE_VISION_MODEL_ID,
            request_id="fake-vision-" + str(len(self.calls)),
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            latency_ms=self.latency_ms,
            inputs_used=("product_input", "reference_metadata", "actual_images"),
            reference_images_sent=True,
            attempts=1,
        )
