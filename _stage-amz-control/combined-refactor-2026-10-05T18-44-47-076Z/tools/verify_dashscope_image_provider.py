"""Offline checks for the provider-neutral image contract and DashScope adapter."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import unittest
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers.dashscope_image import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER_ID,
    DashScopeImageProvider,
    create_default_image_provider,
)
from src.providers.image import ImageProviderError, ImageReference, ImageTask


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, headers=None, content=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content if content is not None else json.dumps(payload or {}).encode("utf-8")

    def json(self):
        return self._payload


class FakeTransport:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, *, headers, json, timeout, allow_redirects):
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "json": json, "timeout": timeout, "allow_redirects": allow_redirects})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def image(content=b"image-pixels", media_type="image/png"):
    return ImageReference(hashlib.sha256(content).hexdigest(), media_type, content)


def task_payload(task_id, status, urls=()):
    return {"request_id": "req-123", "output": {"task_id": task_id, "task_status": status,
            "choices": [{"message": {"content": [{"image": value, "type": "image"} for value in urls]}}]}}


class ImageProviderContractChecks(unittest.TestCase):
    def test_provider_neutral_records_and_safe_error_contract(self):
        reference = image(b"pixels")
        task = ImageTask("provider", "model", "task-1", "PENDING")
        error = ImageProviderError("SAFE_CODE", "safe message", status="UNKNOWN", request_id="req-1")
        self.assertEqual((reference.sha256, reference.media_type, reference.content),
                         (hashlib.sha256(b"pixels").hexdigest(), "image/png", b"pixels"))
        self.assertEqual((task.provider_id, task.model_id, task.task_id, task.status,
                          task.result_urls, task.error, task.request_id),
                         ("provider", "model", "task-1", "PENDING", (), None, None))
        self.assertEqual((error.code, error.message, error.status, error.request_id),
                         ("SAFE_CODE", "safe message", "UNKNOWN", "req-1"))
        with self.assertRaises(ValueError):
            ImageProviderError("BAD", "bad", status="PENDING")


class DashScopeImageProviderChecks(unittest.TestCase):
    def test_missing_key_bad_model_bad_reference_and_bad_size_never_call_transport(self):
        transport = FakeTransport()
        missing_key = DashScopeImageProvider(api_key=None, transport=transport)
        with self.assertRaises(ImageProviderError) as caught:
            missing_key.submit("prompt", [image()])
        self.assertEqual((caught.exception.code, caught.exception.status), ("PROVIDER_API_KEY_MISSING", "REJECTED"))
        self.assertEqual(transport.calls, [])

        provider = DashScopeImageProvider(api_key="secret-key", transport=transport)
        bad_hash = ImageReference("0" * 64, "image/png", b"private image")
        operations = [
            (lambda: provider.submit("prompt", []), "REFERENCE_IMAGE_REQUIRED"),
            (lambda: provider.submit("prompt", [image()] * 4), "REFERENCE_IMAGE_LIMIT"),
            (lambda: provider.submit("prompt", [bad_hash]), "REFERENCE_IMAGE_HASH_MISMATCH"),
            (lambda: provider.submit("prompt", [image()], model_id="other-model"), "MODEL_UNSUPPORTED"),
            (lambda: provider.submit("prompt", [image()], size="1*1"), "SIZE_INVALID"),
        ]
        for operation, code in operations:
            with self.subTest(code=code), self.assertRaises(ImageProviderError) as rejected:
                operation()
            self.assertEqual((rejected.exception.code, rejected.exception.status), (code, "REJECTED"))
        self.assertEqual(transport.calls, [])

        configured = create_default_image_provider(environ={"DASHSCOPE_API_KEY": "env-key"})
        self.assertEqual((configured.provider_id, configured.model_id, configured.api_key),
                         (DEFAULT_PROVIDER_ID, DEFAULT_MODEL_ID, "env-key"))

    def test_submit_sends_exact_prompt_and_ordered_image_bytes_once(self):
        first_bytes, second_bytes = b"first pixels", b"second pixels"
        refs = [image(first_bytes), image(second_bytes, "image/jpeg")]
        transport = FakeTransport(FakeResponse(task_payload("task-1", "PENDING")))
        provider = DashScopeImageProvider(api_key="secret-key", transport=transport)
        prompt = "  exact visible prompt  "
        task = provider.submit(prompt, refs, seed=7, idempotency_key="action-1")
        call = transport.calls[0]
        parts = call["json"]["input"]["messages"][0]["content"]
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(call["url"], DEFAULT_BASE_URL + "/services/aigc/image-generation/generation")
        self.assertEqual(call["headers"]["X-DashScope-Async"], "enable")
        self.assertEqual(call["json"]["model"], DEFAULT_MODEL_ID)
        self.assertEqual(base64.b64decode(parts[0]["image"].split(",", 1)[1]), first_bytes)
        self.assertEqual(base64.b64decode(parts[1]["image"].split(",", 1)[1]), second_bytes)
        self.assertEqual(parts[2], {"text": prompt})
        self.assertFalse(call["json"]["parameters"]["prompt_extend"])
        self.assertEqual((task.provider_id, task.model_id, task.task_id, task.status),
                         (DEFAULT_PROVIDER_ID, DEFAULT_MODEL_ID, "task-1", "PENDING"))

    def test_query_returns_task_and_result_urls(self):
        url = "https://dashscope-1.oss-accelerate.aliyuncs.com/result.png?sig=short-lived"
        transport = FakeTransport(FakeResponse(task_payload("task-2", "SUCCEEDED", [url])))
        provider = DashScopeImageProvider(api_key="secret-key", transport=transport)
        task = provider.query_task("task-2")
        self.assertEqual(transport.calls[0]["method"], "GET")
        self.assertEqual(transport.calls[0]["url"], DEFAULT_BASE_URL + "/tasks/task-2")
        self.assertEqual((task.status, task.task_id, task.result_urls), ("SUCCEEDED", "task-2", (url,)))

    def test_submit_timeout_is_unknown_with_no_id_and_no_retry(self):
        transport = FakeTransport(requests.Timeout("SECRET"))
        provider = DashScopeImageProvider(api_key="secret-key", transport=transport)
        task = provider.submit("PRIVATE_PROMPT", [image()])
        self.assertEqual((task.status, task.task_id), ("UNKNOWN", None))
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn("PRIVATE_PROMPT", task.error or "")

    def test_query_timeout_keeps_the_known_task_id_and_unknown_state(self):
        transport = FakeTransport(requests.Timeout("SECRET"))
        provider = DashScopeImageProvider(api_key="secret-key", transport=transport)
        task = provider.query_task("task-known")
        self.assertEqual((task.status, task.task_id), ("UNKNOWN", "task-known"))
        self.assertNotIn("SECRET", task.error or "")
        self.assertEqual(len(transport.calls), 1)

    def test_http_error_does_not_copy_sensitive_provider_message(self):
        response = FakeResponse(
            {"request_id": "req-safe", "code": "InvalidParameter", "message": "PRIVATE_PROMPT_SENTINEL"},
            status_code=400,
        )
        transport = FakeTransport(response)
        provider = DashScopeImageProvider(api_key="SECRET_API_KEY", transport=transport)
        with self.assertRaises(ImageProviderError) as caught:
            provider.submit("PRIVATE_PROMPT_SENTINEL", [image()])
        self.assertEqual(caught.exception.status, "REJECTED")
        self.assertEqual(caught.exception.request_id, "req-safe")
        self.assertIn("InvalidParameter", str(caught.exception))
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", str(caught.exception))
        self.assertNotIn("SECRET_API_KEY", str(caught.exception))

    def test_account_arrears_maps_to_actionable_failed_submit(self):
        response = FakeResponse(
            {"request_id": "req-arrears", "code": "Arrearage", "message": "PRIVATE_PROMPT_SENTINEL"},
            status_code=400,
        )
        transport = FakeTransport(response)
        provider = DashScopeImageProvider(api_key="SECRET_API_KEY", transport=transport)
        with self.assertRaises(ImageProviderError) as caught:
            provider.submit("PRIVATE_PROMPT_SENTINEL", [image()])
        error = caught.exception
        self.assertEqual(error.code, "UPSTREAM_ACCOUNT_ARREARS")
        self.assertEqual(error.status, "FAILED")
        self.assertEqual(error.request_id, "req-arrears")
        self.assertIn("欠费", str(error))
        self.assertIn("充值", str(error))
        self.assertIn("Arrearage", str(error))
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", str(error))
        self.assertNotIn("SECRET_API_KEY", str(error))

    def test_download_is_limited_to_signed_aliyun_png_and_maps_timeout_to_unknown(self):
        url = "https://dashscope-1.oss-accelerate.aliyuncs.com/result.png?sig=private"
        png = b"\x89PNG\r\n\x1a\nresult-bytes"
        transport = FakeTransport(FakeResponse(
            headers={"Content-Type": "image/png; charset=binary"}, content=png,
        ))
        provider = DashScopeImageProvider(api_key="SECRET_API_KEY", transport=transport)
        self.assertEqual(provider.download_result(url), (png, "image/png"))
        self.assertNotIn("Authorization", transport.calls[0]["headers"])
        self.assertFalse(transport.calls[0]["allow_redirects"])

        blocked_transport = FakeTransport()
        blocked = DashScopeImageProvider(api_key="SECRET_API_KEY", transport=blocked_transport)
        with self.assertRaises(ImageProviderError) as rejected:
            blocked.download_result("https://127.0.0.1/private")
        self.assertEqual(rejected.exception.status, "REJECTED")
        self.assertEqual(blocked_transport.calls, [])

        timeout_transport = FakeTransport(requests.Timeout("https://secret/?sig=private"))
        timed = DashScopeImageProvider(api_key="SECRET_API_KEY", transport=timeout_transport)
        with self.assertRaises(ImageProviderError) as unknown:
            timed.download_result(url)
        self.assertEqual(unknown.exception.status, "UNKNOWN")
        self.assertNotIn("sig=private", str(unknown.exception))


    def test_default_and_callable_transports_are_both_wired(self):
        # Regression: the provider used to default to a bare function and then
        # call .request(...) on it, so every real submit died with an
        # AttributeError that the service reported as a false UNKNOWN.
        default = DashScopeImageProvider(api_key="SECRET_API_KEY")
        self.assertTrue(callable(getattr(default._transport, "request", None)))

        calls = []

        def callable_transport(method, url, *, headers, json, timeout, allow_redirects):
            calls.append({"method": method, "url": url, "json": json})
            return FakeResponse(task_payload("task-callable", "PENDING"))

        provider = create_default_image_provider(
            environ={"DASHSCOPE_API_KEY": "SECRET_API_KEY"}, transport=callable_transport,
        )
        task = provider.submit("prompt", [image()])
        self.assertEqual((task.task_id, task.status), ("task-callable", "PENDING"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["method"], "POST")
        content = calls[0]["json"]["input"]["messages"][0]["content"]
        encoded = [part for part in content if "image" in part]
        self.assertEqual(len(encoded), 1)
        self.assertTrue(encoded[0]["image"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
