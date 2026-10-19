"""V2 功能自检矩阵（P3 迁移）：原 ``app/product_v2_server.py::run_self_check()``（HEAD 4bf6d03）
里除传输/帧检查外的全部功能性断言，按 pytest 真实跑。

原自检用 ThreadingHTTPServer + http.client 逐项打勾；P3 网关换 FastAPI/uvicorn 后，
连接/帧语义由框架负责并已在 ``tests/gateway/test_server_contract.py`` 覆盖，本文件只迁移
功能矩阵：能力投影、契约校验、看图理解、图像三段、复核/整套复核、provider 不可用分类、
默认档开关矩阵、秘密不外泄、连接复用与 BYOK。
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import logging
import struct
import zlib

import pytest

from app.product_v2_server import (
    ANALYZE_PATH,
    CAPABILITIES_PATH,
    IMAGE_RESULT_PATH,
    IMAGE_STATUS_PATH,
    IMAGE_SUBMIT_PATH,
    REVIEW_PATH,
    SUITE_REVIEW_PATH,
    analyze_body_limit,
)
from src.providers.v2_fake_image import FakeImageProvider
from src.providers.v2_fake_review import FakeReviewProvider
from src.providers.v2_fake_semantic import FakeSemanticProvider
from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider
from src.providers.v2_semantic import MAX_VISION_IMAGE_BYTES
from tests.conftest import Client

SECRET_SENTINEL = "sk-pytest-secret-9f2c4d6e8a10b12c"


def analyze_payload(**overrides) -> dict:
    payload = {
        "product_name": "自检商品",
        "description": "自检用的商品资料。",
        "selling_points": ["自检卖点"],
        "focus": "自检重点",
        "references": [{"sha256": "a" * 64, "media_type": "image/png", "role": "primary"}],
        "locale": "zh-CN",
        "platform": "amazon_us",
        "max_slots": 12,
        "existing_slot_ids": [],
    }
    payload.update(overrides)
    return payload


def png_1x1() -> bytes:
    """最小合法 PNG（1x1 灰度），避免依赖 Pillow。"""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    raw = zlib.compress(b"\x00\x80")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw)
            + chunk(b"IEND", b""))


def large_png() -> bytes:
    """1x1 合法 PNG 重复到超过旧的 256KB 文字上限；sha256 复算不受影响。"""
    return png_1x1() * 4500


def review_payload(png: bytes, **overrides) -> dict:
    digest = hashlib.sha256(png).hexdigest()
    payload = {
        "candidate": {"media_type": "image/png", "sha256": digest,
                      "data_base64": base64.b64encode(png).decode("ascii")},
        "references": [],
        "shot": {"title": "自检主图", "purpose": "白底展示商品",
                 "keep_items": ["商品外观"], "allow_changes": ["背景"]},
        "platform": "amazon_us",
        "product_facts": [{"label": "材质", "value": "玻璃"}],
    }
    payload.update(overrides)
    return payload


def suite_payload(png: bytes) -> dict:
    digest = hashlib.sha256(png).hexdigest()
    encoded = base64.b64encode(png).decode("ascii")
    return {
        "platform": "amazon_us",
        "locale": "zh-CN",
        "style_summary": "自检公共风格：白底、柔和阴影。",
        "product_facts": [{"label": "材质", "value": "玻璃"}],
        "images": [
            {"shot_id": "shot_a", "title": "自检主图", "purpose": "白底展示商品",
             "keep_items": ["商品外观"], "allow_changes": ["背景"],
             "image": {"media_type": "image/png", "sha256": digest, "data_base64": encoded}},
            {"shot_id": "shot_b", "title": "自检场景图", "purpose": "生活场景",
             "keep_items": ["商品外观"], "allow_changes": ["背景"],
             "image": {"media_type": "image/png", "sha256": digest, "data_base64": encoded}},
        ],
    }


def broken_factory(kind: str):
    def _factory():
        raise RuntimeError(f"自检：{kind} provider 构造失败")
    return _factory


def copy_targets_payload(**overrides) -> dict:
    """文案提议请求：只带已确认中文值槽位的精确版本快照（不送图）。"""
    payload = analyze_payload(copy_targets=[
        {"slot_id": "signature_features", "version": 3, "label": "必须保持的商品特征",
         "value_type": "text_list", "value": ["304不锈钢内胆", "12小时保温"]},
        {"slot_id": "product_name", "version": 1, "label": "商品名称",
         "value_type": "text", "value": "便携保温杯"},
    ])
    payload.update(overrides)
    return payload


def test_capabilities_expose_semantic_provider_and_contracts(client: Client) -> None:
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200 and payload["ok"] is True
    assert payload["provider"]["configured"] is True
    assert payload["analyze_fields"] == list(
        ("product_name", "description", "selling_points", "focus", "references",
         "locale", "platform", "max_slots", "existing_slot_ids", "copy_targets"))
    # 文案提议是独立能力：界面据此决定是否显示「提议文案」，不能凭型号猜。
    assert payload["provider"]["capabilities"]["copy_proposals"] is True
    assert bool(payload["semantic_contract"])


def test_copy_proposals_echo_requested_identity_only(client: Client) -> None:
    status, payload = client.json("POST", ANALYZE_PATH, copy_targets_payload())
    proposal = payload.get("proposal") or {}
    copies = proposal.get("copy_proposals") or []
    assert status == 200 and payload["ok"] is True and payload["unknown"] is False
    # 两种产出不混装：文案模式下没有事实提案。
    assert proposal.get("slots") == []
    assert [(item["source_slot_id"], item["source_slot_version"]) for item in copies] == [
        ("signature_features", 3), ("product_name", 1)]
    assert all(item["text"] for item in copies)
    assert proposal.get("meta", {}).get("reference_images_sent") is False


def test_copy_mode_without_references_is_accepted(client: Client) -> None:
    """页面实况：文案提议只看已确认文字，请求不带参考图元数据（回归：曾被 references≥1 拒绝）。"""

    status, payload = client.json("POST", ANALYZE_PATH, copy_targets_payload(references=[]))
    proposal = payload.get("proposal") or {}
    copies = proposal.get("copy_proposals") or []
    assert status == 200 and payload["ok"] is True, payload
    assert [(item["source_slot_id"], item["source_slot_version"]) for item in copies] == [
        ("signature_features", 3), ("product_name", 1)]
    assert proposal.get("slots") == []
    assert proposal.get("meta", {}).get("reference_images_sent") is False


def test_analyze_still_requires_a_reference(client: Client) -> None:
    """同一条 references 规则不能被放宽：事实理解没有参考图仍然拒在模型之前。"""

    status, payload = client.json("POST", ANALYZE_PATH, analyze_payload(references=[]))
    assert status == 400 and payload["error"]["family"] == "input_rejected", payload


def test_copy_mode_rejects_vision_bytes_without_model_call(start_server) -> None:
    from src.providers.v2_fake_vision_semantic import FakeVisionSemanticProvider

    calls = {"count": 0}

    class CountingVision(FakeVisionSemanticProvider):
        def analyze(self, request, images=None, **kwargs):
            calls["count"] += 1
            return super().analyze(request, images)

    client = Client(start_server(provider_factory=lambda: CountingVision(scenario="ok")))
    image = png_1x1()
    metadata = {"sha256": hashlib.sha256(image).hexdigest(),
                "media_type": "image/png", "role": "primary"}
    payload = copy_targets_payload(references=[metadata],
                                   reference_images=[{**metadata,
                                                      "data_base64": base64.b64encode(image).decode("ascii")}])
    status, decoded = client.json("POST", ANALYZE_PATH, payload)
    assert status == 400 and decoded["error"]["family"] == "input_rejected"
    assert calls["count"] == 0, calls  # 文案提议只看已确认文字，拒在模型之前


def test_copy_targets_contract_rejected_before_model_call(start_server) -> None:
    calls = {"count": 0}

    def counting_factory():
        calls["count"] += 1
        return FakeSemanticProvider(scenario="ok")

    client = Client(start_server(provider_factory=counting_factory))
    target = {"slot_id": "product_name", "version": 1, "label": "商品名称",
              "value_type": "text", "value": "便携保温杯"}
    duplicate = copy_targets_payload(copy_targets=[target, {**target, "version": 2}])
    status, payload = client.json("POST", ANALYZE_PATH, duplicate)
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    structured = copy_targets_payload(copy_targets=[
        {**target, "value_type": "number", "value": 95}])
    status, payload = client.json("POST", ANALYZE_PATH, structured)
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    too_many = copy_targets_payload(copy_targets=[
        {**target, "slot_id": "slot_" + letter} for letter in "abcde"])
    status, payload = client.json("POST", ANALYZE_PATH, too_many)
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    assert calls["count"] == 0, calls  # 契约校验在 provider 构造之前


def test_copy_response_identity_is_echo_only() -> None:
    from src.providers.v2_semantic import (
        SemanticFailure,
        parse_copy_response,
        parse_request,
        to_copy_proposals,
    )

    request = parse_request(analyze_payload(copy_targets=[
        {"slot_id": "product_name", "version": 1, "label": "商品名称",
         "value_type": "text", "value": "便携保温杯"}]))
    good = parse_copy_response({"copy_proposals": [
        {"slot_id": "product_name", "version": 1, "text": "便携保温杯（假文案）"}]})
    assert to_copy_proposals(good, request) == (
        {"text": "便携保温杯（假文案）", "source_slot_id": "product_name", "source_slot_version": 1},)
    invented = parse_copy_response({"copy_proposals": [
        {"slot_id": "signature_features", "version": 1, "text": "凭空出现的文案"}]})
    with pytest.raises(SemanticFailure) as error:
        to_copy_proposals(invented, request)
    assert (error.value.family, error.value.code) == ("provider_failed", "INVALID_RESPONSE")
    doubled = parse_copy_response({"copy_proposals": [
        {"slot_id": "product_name", "version": 1, "text": "第一条"},
        {"slot_id": "product_name", "version": 1, "text": "第二条"}]})
    with pytest.raises(SemanticFailure) as error:
        to_copy_proposals(doubled, request)
    assert (error.value.family, error.value.code) == ("provider_failed", "INVALID_RESPONSE")


def test_capabilities_expose_image_gateway_block(client: Client) -> None:
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200 and payload["ok"] is True
    images = payload["images"]
    assert images["provider"]["configured"] is True
    assert images["provider"]["model_id"] == "qwen-image-3.0"
    assert IMAGE_SUBMIT_PATH in images["endpoints"]
    assert images["provider"]["capabilities"]["reference_images"] is True


def test_analyze_ok_returns_proposal_with_multiple_slots(client: Client) -> None:
    status, payload = client.json("POST", ANALYZE_PATH, analyze_payload())
    slots = (payload.get("proposal") or {}).get("slots") or []
    assert status == 200 and payload["ok"] is True and payload["unknown"] is False
    assert len(slots) >= 2
    assert all(item["status"] == "proposed" for item in slots)


def test_invalid_json_is_input_rejected(client: Client) -> None:
    status, _, body = client.request("POST", ANALYZE_PATH, b"{not json")
    payload = json.loads(body)
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    assert payload["unknown"] is False


def test_oversized_analyze_is_rejected_with_declared_boundary(client: Client) -> None:
    limit = analyze_body_limit()
    oversized = json.dumps({"product_name": "x" * (limit + 512)}).encode("utf-8")
    status, _, body = client.request("POST", ANALYZE_PATH, oversized)
    payload = json.loads(body)
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    assert payload["error"]["details"]["problems"] == {
        "content_length": len(oversized), "limit": limit}


def test_incomplete_fields_rejected_without_model_call(start_server) -> None:
    calls = {"count": 0}

    def counting_factory():
        calls["count"] += 1
        return FakeSemanticProvider(scenario="ok")

    client = Client(start_server(provider_factory=counting_factory))
    status, payload = client.json("POST", ANALYZE_PATH, {
        "description": "缺少商品名称。",
        "references": [{"sha256": "b" * 64, "media_type": "image/png", "role": "primary"}],
    })
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    assert calls["count"] == 0, calls  # 契约校验在 provider 构造之前


def test_vision_fake_accepts_large_reference_image(start_server) -> None:
    from src.providers.v2_fake_vision_semantic import FakeVisionSemanticProvider

    calls = {"count": 0}

    class CountingVision(FakeVisionSemanticProvider):
        def analyze(self, request, images=None, **kwargs):
            calls["count"] += 1
            return super().analyze(request, images)

    client = Client(start_server(provider_factory=lambda: CountingVision(scenario="ok")))
    image = large_png()
    digest = hashlib.sha256(image).hexdigest()
    metadata = {"sha256": digest, "media_type": "image/png", "role": "primary"}
    payload = analyze_payload(references=[metadata],
                              reference_images=[{**metadata,
                                                 "data_base64": base64.b64encode(image).decode("ascii")}])
    status, decoded = client.json("POST", ANALYZE_PATH, payload)
    body_length = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    assert body_length > 256 * 1024, body_length
    assert status == 200 and decoded["ok"] is True
    assert calls["count"] == 1, calls


def test_vision_sha_mismatch_rejected_before_model_call(start_server) -> None:
    from src.providers.v2_fake_vision_semantic import FakeVisionSemanticProvider

    calls = {"count": 0}

    class CountingVision(FakeVisionSemanticProvider):
        def analyze(self, request, images=None, **kwargs):
            calls["count"] += 1
            return super().analyze(request, images)

    client = Client(start_server(provider_factory=lambda: CountingVision(scenario="ok")))
    image = large_png()
    metadata = {"sha256": "b" * 64, "media_type": "image/png", "role": "primary"}
    payload = analyze_payload(references=[metadata],
                              reference_images=[{**metadata,
                                                 "data_base64": base64.b64encode(image).decode("ascii")}])
    status, decoded = client.json("POST", ANALYZE_PATH, payload)
    assert status == 400 and decoded["error"]["family"] == "input_rejected"
    assert calls["count"] == 0, calls


def test_vision_oversized_single_image_rejected_before_model_call(start_server) -> None:
    from src.providers.v2_fake_vision_semantic import FakeVisionSemanticProvider

    calls = {"count": 0}

    class CountingVision(FakeVisionSemanticProvider):
        def analyze(self, request, images=None, **kwargs):
            calls["count"] += 1
            return super().analyze(request, images)

    client = Client(start_server(provider_factory=lambda: CountingVision(scenario="ok")))
    padding = bytes(MAX_VISION_IMAGE_BYTES + 1 - 64)
    image = png_1x1() + padding  # 越界字节不需要是合法 PNG：解码即拒
    metadata = {"sha256": hashlib.sha256(image).hexdigest(),
                "media_type": "image/png", "role": "primary"}
    payload = analyze_payload(references=[metadata],
                              reference_images=[{**metadata,
                                                 "data_base64": base64.b64encode(image).decode("ascii")}])
    status, decoded = client.json("POST", ANALYZE_PATH, payload)
    assert status == 400 and decoded["error"]["family"] == "input_rejected"
    assert calls["count"] == 0, calls


def test_image_lifecycle_with_fakes_and_sha_verification(client: Client) -> None:
    png = FakeImageProvider.bytes_for("self-check")
    submit_body = {
        "action_id": "self-check-action-01",
        "prompt": "自检用提示词。",
        "references": [{"role": "primary", "media_type": "image/png",
                        "sha256": hashlib.sha256(png).hexdigest(),
                        "data_base64": base64.b64encode(png).decode("ascii")}],
    }
    status, payload = client.json("POST", IMAGE_SUBMIT_PATH, submit_body)
    task_id = (payload.get("task") or {}).get("task_id")
    assert status == 200 and payload["ok"] is True and payload["unknown"] is False
    assert task_id == FakeImageProvider.task_id_for("self-check-action-01")
    assert "aliyuncs" not in json.dumps(payload, ensure_ascii=False)

    status, payload = client.json("POST", IMAGE_STATUS_PATH, {"task_id": task_id})
    assert status == 200 and payload["task"]["status"] == "SUCCEEDED"
    assert payload["task"]["result_count"] == 1

    status, headers, body = client.request(
        "POST", IMAGE_RESULT_PATH, json.dumps({"task_id": task_id}).encode("utf-8"))
    assert status == 200 and "image/png" in headers["content-type"]
    assert body.startswith(b"\x89PNG\r\n\x1a\n")
    assert headers["x-image-sha256"] == hashlib.sha256(body).hexdigest()
    # 同一 task id 在任意实例上都给出同样的字节：确定性派生（不是「之前调用过」）。
    expected = FakeImageProvider.bytes_for(task_id)
    assert body == expected


def test_image_submit_rejects_directory_field_and_empty_references(client: Client) -> None:
    status, payload = client.json("POST", IMAGE_SUBMIT_PATH, {
        "action_id": "self-check-action-02", "prompt": "x",
        "directory": "/etc", "references": [],
    })
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    assert payload["unknown"] is False


def test_image_unknown_scenario_status_and_result_with_call_counts(start_server) -> None:
    calls = {"status": 0, "result": 0}

    def image_factory():
        instance = FakeImageProvider(scenario="status_unknown")
        original_status = instance.status

        def status(request):
            calls["status"] += 1
            return original_status(request)

        instance.status = status
        return instance

    client = Client(start_server(image_provider_factory=image_factory))
    status, payload = client.json("POST", IMAGE_STATUS_PATH, {
        "task_id": FakeImageProvider.task_id_for("self-check-action-01")})
    assert status == 504 and payload["unknown"] is True
    assert payload["error"]["code"] == "PROVIDER_STATUS_UNKNOWN"
    assert calls["status"] == 1, calls


def test_image_failed_scenario_status_and_result(start_server) -> None:
    client = Client(start_server(
        image_provider_factory=lambda: FakeImageProvider(scenario="failed")))
    task_id = FakeImageProvider.task_id_for("self-check-action-01")
    status, payload = client.json("POST", IMAGE_STATUS_PATH, {"task_id": task_id})
    assert status == 200 and payload["task"]["status"] == "FAILED"

    status, _headers, body = client.request(
        "POST", IMAGE_RESULT_PATH, json.dumps({"task_id": task_id}).encode("utf-8"))
    payload = json.loads(body)
    assert status == 502
    assert payload["error"]["family"] == "provider_failed"
    assert payload["error"]["code"] == "RESULT_NOT_AVAILABLE"
    assert payload["unknown"] is False


def test_broken_provider_routes_return_503(start_server) -> None:
    client = Client(start_server(
        provider_factory=broken_factory("语义"),
        image_provider_factory=broken_factory("图像"),
        review_provider_factory=broken_factory("复核"),
        suite_review_provider_factory=broken_factory("整套复核"),
    ))

    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200 and payload["provider"]["configured"] is False
    assert (payload.get("unavailable") or {}).get("kind") in ("registry", "dependency")

    status, payload = client.json("POST", ANALYZE_PATH, analyze_payload())
    assert status == 503 and payload["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
    assert payload["unknown"] is False

    submit_png = FakeImageProvider.bytes_for("self-check-broken")
    submit_body = {
        "action_id": "self-check-broken-01",
        "prompt": "自检用提示词。",
        "references": [{"role": "primary", "media_type": "image/png",
                        "sha256": hashlib.sha256(submit_png).hexdigest(),
                        "data_base64": base64.b64encode(submit_png).decode("ascii")}],
    }
    status, payload = client.json("POST", IMAGE_SUBMIT_PATH, submit_body)
    assert status == 503 and payload["error"]["code"] == "PROVIDER_NOT_CONFIGURED"

    status, payload = client.json("POST", REVIEW_PATH, review_payload(png_1x1()))
    assert status == 503 and payload["error"]["code"] == "PROVIDER_NOT_CONFIGURED"

    status, payload = client.json("POST", SUITE_REVIEW_PATH, suite_payload(png_1x1()))
    assert status == 503 and payload["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


def test_broken_image_provider_capabilities_still_report_200(start_server) -> None:
    client = Client(start_server(image_provider_factory=broken_factory("图像")))
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200
    images = payload["images"]
    assert images["provider"]["configured"] is False
    assert (images.get("unavailable") or {}).get("kind") in ("registry", "dependency")


def test_broken_review_and_suite_capabilities_still_report_200(start_server) -> None:
    client = Client(start_server(review_provider_factory=broken_factory("复核"),
                                suite_review_provider_factory=broken_factory("整套复核")))
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200
    review = payload["review"]
    suite = payload["suite_review"]
    assert review["provider"]["configured"] is False
    assert (review.get("unavailable") or {}).get("kind") in ("registry", "dependency")
    assert suite["provider"]["configured"] is False
    assert (suite.get("unavailable") or {}).get("kind") in ("registry", "dependency")


def test_review_route_ok_binds_candidate_sha(client: Client) -> None:
    png = FakeImageProvider.bytes_for("self-check")
    status, payload = client.json("POST", REVIEW_PATH, review_payload(png))
    result = payload["result"]
    assert status == 200 and payload["ok"] is True and payload["unknown"] is False
    assert result["candidate_sha256"] == hashlib.sha256(png).hexdigest()
    assert len(result["findings"]) >= 1
    assert all(item["check"] for item in result["findings"])
    assert "accept" not in json.dumps(result, ensure_ascii=False).lower()


def test_suite_review_route_ok_scopes_findings_to_sent_set(client: Client) -> None:
    png = FakeImageProvider.bytes_for("self-check")
    sent = {"shot_a", "shot_b"}
    status, payload = client.json("POST", SUITE_REVIEW_PATH, suite_payload(png))
    result = payload["result"]
    assert status == 200 and payload["ok"] is True and payload["unknown"] is False
    assert result["checked_shot_ids"] == ["shot_a", "shot_b"]
    assert result["state"] == "checked"
    assert all(set(item["shot_ids"]) <= sent for item in result["findings"])
    assert "block" not in json.dumps(result, ensure_ascii=False).lower()


def test_review_and_suite_reject_sha_mismatch_before_model_call(client: Client) -> None:
    png = FakeImageProvider.bytes_for("self-check")
    bad_review = review_payload(png)
    bad_review["candidate"]["sha256"] = "0" * 64
    status, payload = client.json("POST", REVIEW_PATH, bad_review)
    assert status == 400 and payload["error"]["family"] == "input_rejected"

    bad_suite = suite_payload(png)
    bad_suite["images"][1]["image"]["sha256"] = "0" * 64
    status, payload = client.json("POST", SUITE_REVIEW_PATH, bad_suite)
    assert status == 400 and payload["error"]["family"] == "input_rejected"


def test_review_capabilities_expose_endpoint_and_reference_images(client: Client) -> None:
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200 and payload["ok"] is True
    review = payload["review"]
    assert review["provider"]["configured"] is True
    assert review["provider"]["model_id"] == "fake-qwen-vl-max"
    assert review["endpoint"] == REVIEW_PATH
    assert review["provider"]["capabilities"]["reference_images"] is True


def test_suite_review_capabilities_expose_endpoint_and_max_images(client: Client) -> None:
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200 and payload["ok"] is True
    suite = payload["suite_review"]
    assert suite["provider"]["configured"] is True
    assert suite["endpoint"] == SUITE_REVIEW_PATH
    assert suite["max_images"] == 8
    assert suite["provider"]["model_id"] == "fake-qwen-vl-max"


def test_undefined_write_route_stays_404(client: Client) -> None:
    status, _, _ = client.request(
        "POST", "/api/v2/semantic/unknown", b"{}",
        headers={"Content-Type": "application/json"})
    assert status == 404


def test_default_trial_matrix(start_server, monkeypatch: pytest.MonkeyPatch) -> None:
    """默认档三态：open 走注册表默认（dashscope-semantic）并 configured=true；
    closed/invalid 保持 configured=false 且不装默认档密钥；全部不触网、不付费。"""

    client = Client(start_server())
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200
    assert payload["images"]["default_trial"] == "closed"  # 显式注入接缝 + 未设 env

    monkeypatch.setenv("AMZ_V2_DEFAULT_TRIAL", "1")
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200
    assert payload["images"]["default_trial"] == "open"

    monkeypatch.setenv("AMZ_V2_DEFAULT_TRIAL", "bogus")
    status, payload = client.json("GET", CAPABILITIES_PATH)
    assert status == 200
    assert payload["images"]["default_trial"] == "invalid"


def test_secret_redaction_in_error_messages_and_logs(gateway, caplog: pytest.LogCaptureFixture) -> None:
    """秘密哨兵出现在错误响应或日志里即失败；密钥只在本次请求内存里。"""

    client = Client(gateway)
    payload = {"secret": SECRET_SENTINEL, "nonsense": "trailing"}  # 会被截成非法 JSON
    with caplog.at_level(logging.DEBUG):
        status, _headers, raw = client.request(
            "POST", ANALYZE_PATH, json.dumps(payload).encode("utf-8")[:60],
            headers={"X-AMZ-Listing-Key-Semantic": SECRET_SENTINEL + "-semantic",
                     "X-AMZ-Listing-Key-Image": SECRET_SENTINEL + "-image"})
    assert status == 400
    body = raw.decode("utf-8", "replace")
    assert SECRET_SENTINEL not in body
    assert SECRET_SENTINEL not in caplog.text


def test_connection_reuse_content_length_on_repeated_gets(gateway) -> None:
    """同一连接连续两次 GET：每条响应自带 Content-Length，HTTP/1.1 保序返回。"""

    connection = http.client.HTTPConnection("127.0.0.1", gateway.port, timeout=20)
    try:
        reused: list[tuple[int, str]] = []
        for _ in range(2):
            connection.request("GET", "/api/health")
            response = connection.getresponse()
            reused.append((response.status, response.getheader("Content-Length") or ""))
            response.read()
        assert all(status == 200 and length.isdigit() for status, length in reused), reused
    finally:
        connection.close()


def test_semantic_and_review_byok_accepts_request(gateway) -> None:
    """显式注入接缝 + BYOK 头：凭证走 apply_credentials 换上后照常成功。"""

    client = Client(gateway)
    semantic_key = SECRET_SENTINEL + "-semantic"
    status, payload = client.json(
        "POST", ANALYZE_PATH, analyze_payload(),
        headers={"X-AMZ-Listing-Key-Semantic": semantic_key})
    assert status == 200 and payload["ok"] is True

    png = FakeImageProvider.bytes_for("self-check")
    status, payload = client.json(
        "POST", REVIEW_PATH, review_payload(png),
        headers={"X-AMZ-Listing-Key-Review": SECRET_SENTINEL + "-review"})
    assert status == 200 and payload["ok"] is True


def test_unknown_provider_id_rejected_before_model_call(gateway) -> None:
    client = Client(gateway)
    status, payload = client.json(
        "POST", ANALYZE_PATH, analyze_payload(),
        headers={"X-AMZ-Listing-Provider-Semantic": "no-such-provider"})
    assert status == 400 and payload["error"]["family"] == "input_rejected"

    status, payload = client.json(
        "POST", IMAGE_SUBMIT_PATH,
        {"action_id": "self-check-unknown-02", "prompt": "x", "references": []},
        headers={"X-AMZ-Listing-Provider-Image": "no-such-provider"})
    assert status == 400 and payload["error"]["family"] == "input_rejected"
