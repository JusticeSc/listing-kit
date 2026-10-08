#!/usr/bin/env python
"""Offline contract tests for the Product V1 SemanticProvider adapter."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers.dashscope_semantic import (  # noqa: E402
    DEFAULT_ENDPOINT_ENV,
    DEFAULT_MODEL_ID,
    DashScopeSemanticProvider,
    create_default_semantic_provider,
)
from src.providers.fake_semantic import FakeSemanticProvider  # noqa: E402
from src.providers.semantic import SemanticImage, SemanticProviderError  # noqa: E402


def tiny_image(image_format: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (82, 123, 171)).save(buffer, format=image_format)
    return buffer.getvalue()


def brief_draft() -> dict:
    return {
        "category": {"label": "travel mug", "confidence": 0.94, "source": "reference_image"},
        "facts": [],
        "must_preserve": ["product silhouette"],
        "may_change": ["background"],
        "unknowns": [],
    }


def plan_draft() -> dict:
    return {
        "style_lock": {
            "direction": "quiet premium studio photography",
            "palette": ["warm white", "graphite"],
            "lighting": "soft side light",
            "background": "warm white",
            "continuity_notes": ["keep product identity consistent"],
        },
        "shots": [{
            "archetype_id": "hero", "title": "Main image", "purpose": "identify the product",
            "reason": "Required marketplace view",
            "preserve": ["shape", "logo"], "change": ["background"],
            "reference_asset_sha256": [], "supporting_fact_keys": [], "dependencies": [],
        }],
    }


def prompt_blocks_draft() -> dict:
    return {"blocks": [
        {"id": "style-lock", "kind": "style_lock",
         "text": "Use restrained soft-side lighting and a quiet warm-neutral palette.",
         "source_refs": ["plan.style_lock"]},
        {"id": "shot-task", "kind": "shot_task",
         "text": "Use a clean close framing that clearly communicates the approved image objective.",
         "source_refs": ["shot_spec.purpose"]},
        {"id": "negative", "kind": "negative",
         "text": "Do not add parts, props, or unsupported performance cues.",
         "source_refs": ["shot_spec.preserve"]},
    ]}


class FakeResponse:
    def __init__(self, payload: object, *, status_code: int = 200, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {"x-request-id": "req-test-001"}
        if isinstance(payload, bytes):
            self.content = payload
            self._payload = None
        else:
            self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._payload = payload
        self.text = self.content.decode("utf-8", errors="replace")

    def json(self):
        if self._payload is None:
            return json.loads(self.content)
        return self._payload


def completion(value: dict) -> FakeResponse:
    return FakeResponse({
        "id": "completion-id-1",
        "choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    })


class FakeTransport:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls: list[dict] = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": dict(headers), "body": dict(body), "timeout": timeout})
        return self.response


def capture_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.Logger("semantic-provider-test")
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler(stream))
    return logger, stream


class SemanticProviderChecks(unittest.TestCase):
    def provider(self, response: FakeResponse, *, api_key: str | None = "test-api-key", base_url: str | None = "https://dashscope.example/compatible-mode/v1"):
        transport = FakeTransport(response)
        logger, log = capture_logger()
        instance = DashScopeSemanticProvider(
            api_key=api_key, base_url=base_url, transport=transport, logger=logger,
        )
        return instance, transport, log

    def test_missing_key_blocks_before_transport_and_never_falls_back(self):
        instance, transport, _ = self.provider(completion(plan_draft()), api_key=None)
        with self.assertRaises(SemanticProviderError) as caught:
            instance.propose_plan({}, {}, {}, None)
        self.assertEqual(caught.exception.code, "PROVIDER_API_KEY_MISSING")
        self.assertIn("未调用模型", str(caught.exception))
        self.assertEqual(transport.calls, [])

    def test_missing_region_endpoint_blocks_before_transport(self):
        instance, transport, _ = self.provider(completion(plan_draft()), base_url=None)
        with self.assertRaises(SemanticProviderError) as caught:
            instance.propose_plan({}, {}, {}, None)
        self.assertEqual(caught.exception.code, "PROVIDER_ENDPOINT_MISSING")
        self.assertEqual(transport.calls, [])
        self.assertIn(DEFAULT_ENDPOINT_ENV, str(caught.exception))

    def test_multimodal_brief_uses_json_object_and_local_schema_validation(self):
        content = tiny_image()
        image = SemanticImage(hashlib.sha256(content).hexdigest(), "image/png", content)
        instance, transport, logs = self.provider(completion(brief_draft()))
        result = instance.analyze_product({
            "product_name": "PrivateProductName",
            "description": "User-owned product data",
            "selling_points": [],
            "platform": {"profile_id": "amazon-us", "version": 1},
            "reference_asset_sha256": [image.sha256],
        }, [image])

        call = transport.calls[0]
        self.assertEqual(call["url"], "https://dashscope.example/compatible-mode/v1/chat/completions")
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-api-key")
        self.assertEqual(call["body"]["model"], DEFAULT_MODEL_ID)
        self.assertEqual(call["body"]["response_format"], {"type": "json_object"})
        user_content = call["body"]["messages"][1]["content"]
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertTrue(user_content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(result.data, brief_draft())
        self.assertEqual(result.schema_mode, "json_object")
        self.assertEqual(result.request_id, "req-test-001")
        self.assertEqual(result.usage["total_tokens"], 30)
        self.assertNotIn("PrivateProductName", logs.getvalue())
        self.assertNotIn("test-api-key", logs.getvalue())
        self.assertNotIn("base64,", logs.getvalue())

    def test_text_only_plan_uses_strict_schema_and_registry_model(self):
        instance, transport, _ = self.provider(completion(plan_draft()))
        result = instance.propose_plan({"facts": []}, {"required_archetypes": ["hero"]}, {"archetypes": []}, None)
        response_format = transport.calls[0]["body"]["response_format"]
        self.assertEqual(transport.calls[0]["body"]["model"], DEFAULT_MODEL_ID)
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertNotIn(
            "required",
            response_format["json_schema"]["schema"]["properties"]["shots"]["items"]["properties"],
        )
        self.assertEqual(result.data, plan_draft())

    def test_prompt_blocks_contract_is_validated(self):
        instance, transport, _ = self.provider(completion(prompt_blocks_draft()))
        result = instance.propose_prompt_blocks({"facts": []}, {"title": "Hero"}, {"direction": "studio"})
        self.assertEqual(result.data, prompt_blocks_draft())
        self.assertEqual(transport.calls[0]["body"]["response_format"]["type"], "json_schema")

    def test_invalid_model_shape_is_rejected_without_exposing_response_text(self):
        instance, _, logs = self.provider(completion({"unexpected": "PRIVATE_RESPONSE_SENTINEL"}))
        with self.assertRaises(SemanticProviderError) as caught:
            instance.propose_plan({}, {}, {}, None)
        self.assertEqual(caught.exception.code, "OUTPUT_SCHEMA_INVALID")
        self.assertNotIn("PRIVATE_RESPONSE_SENTINEL", str(caught.exception))
        self.assertNotIn("PRIVATE_RESPONSE_SENTINEL", logs.getvalue())
        self.assertRegex(caught.exception.response_summary, r"response_sha256=[0-9a-f]{64}")

    def test_provider_error_keeps_only_redacted_summary(self):
        response = FakeResponse(
            {"error": {"code": "QuotaExceeded", "message": "PRIVATE_PROMPT_SENTINEL"}},
            status_code=429,
        )
        instance, _, logs = self.provider(response)
        with self.assertRaises(SemanticProviderError) as caught:
            instance.propose_plan({}, {}, {}, None)
        self.assertEqual(caught.exception.code, "UPSTREAM_REJECTED")
        self.assertTrue(caught.exception.recoverable)
        self.assertIn("QuotaExceeded", caught.exception.response_summary)
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", str(caught.exception))
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", logs.getvalue())

    def test_account_arrears_is_reported_with_an_actionable_message(self):
        response = FakeResponse(
            {"error": {"code": "Arrearage", "message": "PRIVATE_PROMPT_SENTINEL"}},
            status_code=400,
        )
        instance, _, logs = self.provider(response)
        with self.assertRaises(SemanticProviderError) as caught:
            instance.propose_plan({}, {}, {}, None)
        error = caught.exception
        self.assertEqual(error.code, "UPSTREAM_ACCOUNT_ARREARS")
        self.assertTrue(error.recoverable)
        self.assertEqual(error.http_status, 400)
        self.assertIn("欠费", str(error))
        self.assertIn("充值", str(error))
        self.assertIn("provider_code=Arrearage", error.response_summary)
        self.assertIn("UPSTREAM_ACCOUNT_ARREARS", logs.getvalue())
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", str(error))
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", logs.getvalue())

    def test_reference_hash_mismatch_blocks_external_request(self):
        content = tiny_image()
        image = SemanticImage(hashlib.sha256(content).hexdigest(), "image/png", content)
        instance, transport, _ = self.provider(completion(brief_draft()))
        with self.assertRaises(SemanticProviderError) as caught:
            instance.analyze_product({"reference_asset_sha256": ["0" * 64]}, [image])
        self.assertEqual(caught.exception.code, "REFERENCE_ASSET_MISMATCH")
        self.assertEqual(transport.calls, [])

    def test_configured_default_resolves_model_and_environment_names(self):
        instance = create_default_semantic_provider(environ={
            "DASHSCOPE_API_KEY": "test-api-key",
            DEFAULT_ENDPOINT_ENV: "https://dashscope.example/compatible-mode/v1",
        })
        self.assertEqual(instance.provider_id, "dashscope-qwen-semantic")
        self.assertEqual(instance.model_id, DEFAULT_MODEL_ID)
        self.assertEqual(instance.api_key, "test-api-key")

    def test_explicit_fake_provider_obeys_contract_without_defaulting_output(self):
        fake = FakeSemanticProvider({"propose_plan": plan_draft()})
        result = fake.propose_plan({}, {}, {}, None)
        self.assertEqual(result.data, plan_draft())
        self.assertEqual(fake.operations, ["propose_plan"])
        with self.assertRaisesRegex(KeyError, "no explicit analyze_product response"):
            fake.analyze_product({}, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
