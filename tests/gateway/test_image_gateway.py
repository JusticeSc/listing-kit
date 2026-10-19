"""V2.4.1 image gateway pytest port of tools/verify_v2_4_1_image_gateway.py.

P3 posture (same discipline as test_server_contract.py): real TCP via the
uvicorn+h11 host; fake providers and real adapters with injected fake
transports, zero real model calls. Where uvicorn/h11 differs from the old
stdlib gateway the test asserts the safe equivalent and says so in its
docstring: over-limit bodies are drained then answered 400 input_rejected
with a declared limit boundary instead of an early disconnect.

Original tool check IDs: V2.4.1-01..21, 23, 24, 25..33 (no -22 in the tool;
the old -22 entry --check is retired to run_self_check plus
tests/dev/test_selfcheck_matrix.py, not duplicated here).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging

import pytest

from app.product_v2_server import (
    CAPABILITIES_PATH,
    IMAGE_BYOK_HEADER,
    IMAGE_PROVIDER_HEADER,
    IMAGE_RESULT_PATH,
    IMAGE_STATUS_PATH,
    IMAGE_SUBMIT_PATH,
)
from tests.conftest import Client

BYOK_KEY = "byok-owned-key-0001"


def png_bytes(seed: str) -> bytes:
    from src.providers.v2_fake_image import FakeImageProvider

    return FakeImageProvider.bytes_for(seed)


def reference_png(seed: str = "verifier-ref") -> dict:
    payload = png_bytes(seed)
    return {"role": "primary", "media_type": "image/png",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "data_base64": base64.b64encode(payload).decode("ascii")}


def submit_body(action_id: str, *, prompt: str = "x" * 16,
                references: list | None = None, **extra) -> bytes:
    if references is None:
        references = [reference_png()]
    body: dict = {"action_id": action_id, "prompt": prompt, "references": references}
    body.update(extra)
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def task_body(task_id: str) -> bytes:
    return json.dumps({"task_id": task_id}, ensure_ascii=False).encode("utf-8")


# V2.4.1-01
def test_v241_01_capabilities_expose_image_gateway_contract(client: Client) -> None:
    status, payload = client.json("GET", CAPABILITIES_PATH)
    images = payload.get("images") or {}
    provider = images.get("provider") or {}
    capability = provider.get("capabilities") or {}
    assert status == 200
    assert images.get("contract") == "v2.4.1"
    assert provider.get("configured") is True
    assert provider.get("model_id") == "qwen-image-3.0"
    assert capability.get("reference_images") is True
    for endpoint in (IMAGE_SUBMIT_PATH, IMAGE_STATUS_PATH, IMAGE_RESULT_PATH):
        assert endpoint in (images.get("endpoints") or []), endpoint


# V2.4.1-02
def test_v241_02_submit_returns_task_identity_without_result_url(client: Client) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    action = "verify-action-0001"
    status, headers, raw = client.request("POST", IMAGE_SUBMIT_PATH, submit_body(action))
    payload = json.loads(raw)
    task = payload.get("task") or {}
    assert status == 200
    assert payload.get("ok") is True and payload.get("unknown") is False
    assert task.get("task_id") == FakeImageProvider.task_id_for(action)
    assert task.get("status") == "RUNNING"
    assert "aliyuncs" not in raw.decode("utf-8", "replace")


# V2.4.1-03
def test_v241_03_result_without_prior_status_returns_png_bytes(client: Client) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    status, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-0001"))
    payload = json.loads(raw)
    task_id = (payload.get("task") or {}).get("task_id")
    status, headers, raw = client.request("POST", IMAGE_RESULT_PATH, task_body(task_id))
    ctype = headers.get("content-type", "")
    expected = FakeImageProvider.bytes_for(task_id)
    assert status == 200 and "image/png" in ctype and raw == expected
    assert headers.get("x-image-sha256") == hashlib.sha256(raw).hexdigest()
    assert headers.get("x-provider-id") == "fake-qwen-image"
    assert headers.get("x-model-id") == "qwen-image-3.0"
    assert headers.get("x-task-id") == task_id


# V2.4.1-04
def test_v241_04_status_returns_authoritative_state(client: Client) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    task_id = FakeImageProvider.task_id_for("verify-action-0001")
    status, headers, raw = client.request("POST", IMAGE_STATUS_PATH, task_body(task_id))
    payload = json.loads(raw)
    task = payload.get("task") or {}
    assert status == 200
    assert task.get("status") == "SUCCEEDED"
    assert task.get("result_count") == 1
    assert "aliyuncs" not in raw.decode("utf-8", "replace")


# V2.4.1-05
def test_v241_05_same_action_id_is_deterministic(client: Client) -> None:
    status, _h1, raw1 = client.request("POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-0001"))
    first = json.loads(raw1)
    status, _h2, raw2 = client.request("POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-0001"))
    second = json.loads(raw2)
    assert status == 200
    assert (second.get("task") or {}).get("task_id") == (first.get("task") or {}).get("task_id")


# V2.4.1-06
def test_v241_06_input_rejection_matrix_never_calls_upstream(start_server) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    built: list = []

    def factory():
        provider = FakeImageProvider("ok")
        built.append(provider)
        return provider

    client = Client(start_server(image_provider_factory=factory))
    reference = reference_png()
    broken_sha = dict(reference, sha256="0" * 64)
    unsupported = dict(reference, media_type="image/heic")
    probes = [
        submit_body("verify-action-dir", directory="/tmp/probe"),
        submit_body("verify-action-ws", workspace="/tmp/probe"),
        submit_body("verify-action-blank", prompt="   "),
        submit_body("verify-action-none", references=[]),
        submit_body("verify-action-four", references=[reference] * 4),
        submit_body("verify-action-sha", references=[broken_sha]),
        submit_body("verify-action-media", references=[unsupported]),
        submit_body("verify-action-long", prompt="x" * 5000),
        submit_body("verify-action-size", size="100*100"),
        submit_body("bad", prompt="valid prompt text"),
    ]
    for body in probes:
        status, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH, body)
        payload = json.loads(raw)
        assert status == 400, body[:80]
        assert (payload.get("error") or {}).get("family") == "input_rejected", payload
        assert payload.get("unknown") is False, payload
    assert built == []  # contract rejection lands before any provider is constructed


# V2.4.1-07
def test_v241_07_directory_fields_rejected_and_sentinel_untouched(client, tmp_path) -> None:
    sentinel_dir = tmp_path / "probe"
    sentinel_dir.mkdir()
    sentinel = sentinel_dir / "sentinel.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    for body in (submit_body("verify-action-dir7", directory=str(sentinel_dir)),
                 submit_body("verify-action-ws7", workspace=str(sentinel_dir))):
        status, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH, body)
        assert status == 400
        assert json.loads(raw)["error"]["family"] == "input_rejected"
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == before
    assert sorted(item.name for item in sentinel_dir.iterdir()) == ["sentinel.txt"]


# V2.4.1-08
def test_v241_08_oversize_submit_rejected_with_declared_boundary(start_server) -> None:
    """Over-limit submits get 400 input_rejected with the declared limit boundary.

    Framework-safe equivalent of the old stdlib early-disconnect behaviour: uvicorn/h11
    drains the declared body, then the app answers 400 (fetch never mistakes it for
    an unknown outcome), without constructing any upstream provider.
    """
    from app.product_v2_server import MAX_IMAGE_BODY_BYTES
    from src.providers.v2_fake_image import FakeImageProvider

    built: list = []

    def factory():
        provider = FakeImageProvider("ok")
        built.append(provider)
        return provider

    client = Client(start_server(image_provider_factory=factory))
    oversized = (b'{"action_id":"verify-action-oversize","prompt":"'
                 + b"x" * (MAX_IMAGE_BODY_BYTES + 64)
                 + b'","references":[]}')
    status, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH, oversized)
    payload = json.loads(raw)
    assert status == 400
    assert payload["error"]["family"] == "input_rejected"
    assert payload["error"]["details"]["problems"]["limit"] == MAX_IMAGE_BODY_BYTES
    assert built == []


# V2.4.1-25
def test_v241_25_one_megabyte_reference_is_accepted(client: Client) -> None:
    import os as _os

    head = png_bytes("large-ref")
    large = head + _os.urandom(1024 * 1024 - len(head))
    reference = {"role": "primary", "media_type": "image/png",
                 "sha256": hashlib.sha256(large).hexdigest(),
                 "data_base64": base64.b64encode(large).decode("ascii")}
    body = submit_body("verify-action-large-ref", references=[reference])
    status, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH, body)
    payload = json.loads(raw)
    assert status == 200, payload
    assert payload.get("ok") is True and payload.get("unknown") is False


# V2.4.1-09
def test_v241_09_submit_unknown_is_504_requires_review(start_server) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    client = Client(start_server(image_provider_factory=lambda: FakeImageProvider("submit_unknown")))
    status, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH,
                                           submit_body("verify-action-unknown"))
    payload = json.loads(raw)
    error = payload.get("error") or {}
    assert status == 504
    assert payload.get("unknown") is True
    assert error.get("family") == "provider_unknown"
    assert error.get("retry_policy") == "requires_review"
    assert "task" not in payload


# V2.4.1-10
def test_v241_10_status_unknown_is_504_without_task(start_server) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    client = Client(start_server(image_provider_factory=lambda: FakeImageProvider("status_unknown")))
    status, _headers, raw = client.request("POST", IMAGE_STATUS_PATH,
                                           task_body("fake-0000000000000000"))
    payload = json.loads(raw)
    error = payload.get("error") or {}
    assert status == 504
    assert payload.get("unknown") is True
    assert error.get("family") == "provider_unknown"
    assert "task" not in payload


# V2.4.1-11
def test_v241_11_upstream_failure_is_data_not_http_error(start_server) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    failed_id = "fake-1111111111111111"
    client = Client(start_server(image_provider_factory=lambda: FakeImageProvider("failed")))
    status, _headers, raw = client.request("POST", IMAGE_STATUS_PATH, task_body(failed_id))
    task = json.loads(raw).get("task") or {}
    assert status == 200
    assert task.get("status") == "FAILED" and bool(task.get("error"))
    assert task.get("unknown") is False


# V2.4.1-12
def test_v241_12_failed_task_result_is_502_fatal(start_server) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    client = Client(start_server(image_provider_factory=lambda: FakeImageProvider("failed")))
    status, _headers, raw = client.request("POST", IMAGE_RESULT_PATH,
                                           task_body("fake-1111111111111111"))
    error = json.loads(raw).get("error") or {}
    assert status == 502
    assert error.get("family") == "provider_failed"
    assert error.get("retry_policy") == "fatal"


# V2.4.1-13
def test_v241_13_download_failure_is_502_retryable(start_server) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    client = Client(start_server(image_provider_factory=lambda: FakeImageProvider("download_failed")))
    status, _headers, raw = client.request("POST", IMAGE_RESULT_PATH,
                                           task_body("fake-1111111111111111"))
    error = json.loads(raw).get("error") or {}
    assert status == 502
    assert error.get("family") == "provider_failed"
    assert error.get("retry_policy") == "retryable"


class Response:
    def __init__(self, status_code, payload=None, *, headers=None, content=None,
                 json_error=False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error
        self.headers = dict(headers or {})
        self.content = content if content is not None else b""

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class RecordingTransport:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list = []

    def request(self, method, url, *, headers, json, timeout, allow_redirects):
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "json": json, "timeout": timeout,
                           "allow_redirects": allow_redirects})
        if not self.responses:
            raise AssertionError("transport got an unexpected call: " + url)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _adapter_request():
    from src.providers.v2_image import SubmitRequest

    ref = png_bytes("verifier-ref")
    return SubmitRequest(
        action_id="verify-action-adapter", prompt="PROMPT",
        references=[{"role": "primary", "media_type": "image/png",
                     "sha256": hashlib.sha256(ref).hexdigest(),
                     "data_base64": base64.b64encode(ref).decode("ascii")}],
        size="1344*1344", seed=7)


# V2.4.1-14
def test_v241_14_adapter_submit_shape() -> None:
    from src.providers.v2_dashscope_image import DEFAULT_BASE_URL, DashScopeImageProvider

    transport = RecordingTransport([Response(
        200, {"output": {"task_id": "task-abc", "task_status": "RUNNING"},
              "request_id": "req-1"})])
    provider = DashScopeImageProvider(api_key="k" * 24, transport=transport)
    task = provider.submit(_adapter_request())
    call = transport.calls[0]
    body = call["json"]
    content = body["input"]["messages"][0]["content"]
    assert call["method"] == "POST"
    assert call["url"] == DEFAULT_BASE_URL + "/services/aigc/image-generation/generation"
    assert call["headers"].get("X-DashScope-Async") == "enable"
    assert call["headers"].get("Authorization", "").startswith("Bearer ")
    assert body["model"] == "qwen-image-3.0"
    assert content[0]["image"].startswith("data:image/png;base64,")
    assert content[-1]["text"] == "PROMPT"
    assert body["parameters"] == {"size": "1344*1344", "n": 1, "prompt_extend": False,
                                  "watermark": False, "seed": 7}
    assert task.task_id == "task-abc" and task.status == "RUNNING"


def _adapter_failure(responses, *, mode="status"):
    from src.providers.v2_dashscope_image import DashScopeImageProvider
    from src.providers.v2_image import ImageFailure, TaskRequest

    transport = RecordingTransport(responses)
    probe = DashScopeImageProvider(api_key="k" * 24, transport=transport)
    try:
        if mode == "submit":
            probe.submit(_adapter_request())
        elif mode == "result":
            probe.result(TaskRequest(task_id="task-abc"))
        else:
            probe.status(TaskRequest(task_id="task-abc"))
    except ImageFailure as failure:
        return failure, transport
    raise AssertionError("expected a classified failure")


# V2.4.1-15
def test_v241_15_upstream_error_classification() -> None:
    f401, _t = _adapter_failure([Response(401, {"code": "InvalidApiKey"})])
    f429, _t = _adapter_failure([Response(429, {"code": "Throttling"})], mode="submit")
    f500, _t = _adapter_failure([Response(500, {"code": "InternalError"})])
    f_timeout, _t = _adapter_failure([TimeoutError("boom")])
    f_mismatch, _t = _adapter_failure([Response(
        200, {"output": {"task_id": "task-other", "task_status": "SUCCEEDED"}})])
    assert f401.family == "provider_failed" and f401.retry_policy == "fatal"
    assert f401.code == "UPSTREAM_REJECTED"
    assert f429.family == "provider_failed" and f429.retry_policy == "retryable"
    assert f429.code == "UPSTREAM_RATE_LIMITED"
    assert f500.family == "provider_unknown" and f500.retry_policy == "requires_review"
    assert f500.unknown is True and f500.http_status == 500
    assert f_timeout.family == "provider_unknown" and f_timeout.unknown is True
    assert f_mismatch.family == "provider_unknown"
    assert f_mismatch.code == "PROVIDER_TASK_MISMATCH"
    for failure in (f401, f429, f500, f_timeout, f_mismatch):
        assert "PROMPT" not in failure.message


# V2.4.1-16
def test_v241_16_untrusted_result_url_never_downloaded() -> None:
    failure, transport = _adapter_failure([Response(200, {"output": {
        "task_id": "task-abc", "task_status": "SUCCEEDED",
        "results": [{"url": "https://evil.example.com/a.png"}]}})], mode="result")
    assert failure.family == "provider_failed" and failure.code == "RESULT_URL_MISSING"
    assert len(transport.calls) == 1


# V2.4.1-17
def test_v241_17_result_downloads_trusted_url() -> None:
    from src.providers.v2_dashscope_image import DEFAULT_BASE_URL, DashScopeImageProvider
    from src.providers.v2_image import TaskRequest

    ref = png_bytes("verifier-ref")
    ok_url = "https://dashscope-result.aliyuncs.com/task/a.png"
    transport = RecordingTransport([
        Response(200, {"output": {"task_id": "task-abc", "task_status": "SUCCEEDED",
                                  "results": [{"url": ok_url}]}}),
        Response(200, content=ref, headers={"Content-Type": "image/png"}),
    ])
    provider = DashScopeImageProvider(api_key="k" * 24, transport=transport)
    content, media_type = provider.result(TaskRequest(task_id="task-abc"))
    assert content == ref and media_type == "image/png"
    assert [item["url"] for item in transport.calls] == [
        DEFAULT_BASE_URL + "/tasks/task-abc", ok_url]


# V2.4.1-18
def test_v241_18_non_png_result_is_rejected() -> None:
    from src.providers.v2_dashscope_image import DashScopeImageProvider
    from src.providers.v2_image import ImageFailure, TaskRequest

    ok_url = "https://dashscope-result.aliyuncs.com/task/a.png"
    transport = RecordingTransport([
        Response(200, {"output": {"task_id": "task-abc", "task_status": "SUCCEEDED",
                                  "results": [{"url": ok_url}]}}),
        Response(200, content=b"not-a-png", headers={"Content-Type": "image/png"}),
    ])
    provider = DashScopeImageProvider(api_key="k" * 24, transport=transport)
    try:
        provider.result(TaskRequest(task_id="task-abc"))
    except ImageFailure as failure:
        assert failure.code == "RESULT_IMAGE_INVALID"
        assert failure.family == "provider_failed"
    else:
        raise AssertionError("expected RESULT_IMAGE_INVALID")


# V2.4.1-19
def test_v241_19_unconfigured_capabilities_still_200(start_server) -> None:
    from src.providers.v2_dashscope_image import create_default_image_provider

    client = Client(start_server(
        image_provider_factory=lambda: create_default_image_provider(environ={})))
    status, payload = client.json("GET", CAPABILITIES_PATH)
    images = payload.get("images") or {}
    assert status == 200
    assert images.get("provider", {}).get("configured") is False


# V2.4.1-20
def test_v241_20_unconfigured_submit_is_503(start_server) -> None:
    from src.providers.v2_dashscope_image import create_default_image_provider

    client = Client(start_server(
        image_provider_factory=lambda: create_default_image_provider(environ={})))
    status, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH,
                                           submit_body("verify-action-nokey"))
    payload = json.loads(raw)
    error = payload.get("error") or {}
    assert status == 503
    assert error.get("code") == "PROVIDER_NOT_CONFIGURED"
    assert error.get("family") == "internal"
    assert payload.get("unknown") is False


# V2.4.1-21
def test_v241_21_registry_default_and_env_override_construct_offline() -> None:
    from src.providers.v2_registry import (create_image_provider, load_registry,
                                           resolve_image_provider_id)

    registry = load_registry()
    default_choice = resolve_image_provider_id(registry, env={})
    env_choice = resolve_image_provider_id(registry, env={"AMZ_V2_IMAGE_PROVIDER": "fake-qwen-image"})
    real_provider = create_image_provider(registry=registry, env={})
    fake_provider = create_image_provider(registry=registry,
                                          env={"AMZ_V2_IMAGE_PROVIDER": "fake-qwen-image"})
    assert default_choice == "dashscope-qwen-image"
    assert env_choice == "fake-qwen-image"
    assert type(real_provider).__name__ == "DashScopeImageProvider"
    assert type(fake_provider).__name__ == "FakeImageProvider"


# V2.4.1-24
def test_v241_24_default_function_transport_is_normalized(monkeypatch) -> None:
    import src.providers.v2_dashscope_image as adapter_module
    from src.providers.v2_dashscope_image import create_default_image_provider

    class StubRequests:
        def __init__(self, responses) -> None:
            self.responses = list(responses)
            self.calls: list = []

        def request(self, method, url, **kwargs):
            self.calls.append({"method": method, "url": url})
            item = self.responses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

    stub = StubRequests([Response(
        200, {"output": {"task_id": "task-default-transport", "task_status": "RUNNING"}},
        headers={"X-Request-Id": "req-default-1"})])
    monkeypatch.setattr(adapter_module, "requests", stub)
    provider = create_default_image_provider(
        environ={"DASHSCOPE_API_KEY": "test-key", "AMZ_V2_DEFAULT_TRIAL": "open"})
    task = provider.submit(_adapter_request())
    assert task.task_id == "task-default-transport" and task.status == "RUNNING"
    assert len(stub.calls) == 1 and stub.calls[0]["method"] == "POST"


# V2.4.1-26
def test_v241_26_default_trial_gate_parses_both_ways_and_rejects_invalid() -> None:
    from src.providers.v2_credentials import resolve_default_trial

    for env_case, expected in [
        ({"AMZ_V2_DEFAULT_TRIAL": "1"}, True),
        ({"AMZ_V2_DEFAULT_TRIAL": "OPEN"}, True),
        ({"AMZ_V2_DEFAULT_TRIAL": "closed"}, False),
        ({"AMZ_V2_DEFAULT_TRIAL": "0"}, False),
        ({}, False),
    ]:
        assert resolve_default_trial(env_case) is expected, env_case
    with pytest.raises(ValueError):
        resolve_default_trial({"AMZ_V2_DEFAULT_TRIAL": "maybe-someday"})


# V2.4.1-27
def test_v241_27_default_trial_gate_applies_at_registry_construction() -> None:
    from src.providers.v2_registry import create_image_provider, load_registry

    registry = load_registry()
    blocked = create_image_provider(registry=registry, env={"DASHSCOPE_API_KEY": "deploy-key"})
    opened = create_image_provider(registry=registry, env={"DASHSCOPE_API_KEY": "deploy-key",
                                                           "AMZ_V2_DEFAULT_TRIAL": "open"})
    assert blocked.api_key == "" and blocked.credential_source == "none"
    assert blocked.capabilities().get("credential_source") == "none"
    assert blocked.capabilities().get("stateless") is True
    assert opened.api_key == "deploy-key" and opened.credential_source == "default"


# V2.4.1-28
def test_v241_28_outbound_whitelist_rejects_before_any_call() -> None:
    from src.providers.v2_dashscope_image import DashScopeImageProvider
    from src.providers.v2_image import ImageFailure

    probes = [
        "http://dashscope.aliyuncs.com/services/aigc/image-generation/generation",
        "https://dashscope.aliyuncs.com:8443/tasks/task-guard",
        "https://127.0.0.1/tasks/task-guard",
        "https://169.254.169.254/latest/meta-data/",
        "https://[fd00::1]/tasks/task-guard",
        "https://user:pw@dashscope.aliyuncs.com/tasks/task-guard",
        "https://evil.example.com/tasks/task-guard",
        "https://dashscope.aliyuncs.com.evil.io/tasks/task-guard",
    ]
    for url in probes:
        transport = RecordingTransport([])
        guarded = DashScopeImageProvider(api_key="k" * 24, transport=transport)
        try:
            guarded._call("guard probe", "GET", url, headers={}, json_body=None)
        except ImageFailure as failure:
            assert failure.code == "OUTBOUND_POLICY_REJECTED", url
            assert failure.http_status == 503, url
            assert len(transport.calls) == 0, url
        else:
            raise AssertionError("expected OUTBOUND_POLICY_REJECTED: " + url)


# V2.4.1-29
def test_v241_29_byok_header_key_used_once_and_never_echoed(start_server) -> None:
    from src.providers.v2_dashscope_image import create_default_image_provider

    recorded = RecordingTransport([
        Response(200, {"output": {"task_id": "task-byok", "task_status": "RUNNING"},
                       "request_id": "req-byok-1"}),
    ])
    client = Client(start_server(image_provider_factory=lambda: create_default_image_provider(
        environ={}, transport=recorded)))
    status, _headers, raw = client.request(
        "POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-byok"),
        headers={IMAGE_BYOK_HEADER: BYOK_KEY})
    payload = json.loads(raw)
    assert status == 200 and payload.get("ok") is True
    assert (payload.get("task") or {}).get("task_id") == "task-byok"
    assert recorded.calls, "BYOK submit never reached the adapter"
    auth = recorded.calls[0]["headers"].get("Authorization")
    assert auth == "Bearer " + BYOK_KEY
    assert BYOK_KEY not in raw.decode("utf-8", "replace")


# V2.4.1-30
def test_v241_30_byok_key_absent_from_status_headers_body_and_logs(start_server, caplog) -> None:
    from src.providers.v2_dashscope_image import create_default_image_provider

    recorded = RecordingTransport([
        Response(200, {"output": {"task_id": "task-byok", "task_status": "RUNNING"},
                       "request_id": "req-byok-1"}),
        Response(200, {"output": {"task_id": "task-byok", "task_status": "SUCCEEDED"},
                       "request_id": "req-byok-2"}),
    ])
    client = Client(start_server(image_provider_factory=lambda: create_default_image_provider(
        environ={}, transport=recorded)))
    with caplog.at_level(logging.DEBUG):
        status, headers, raw = client.request(
            "POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-byok-log"),
            headers={IMAGE_BYOK_HEADER: BYOK_KEY})
        assert status == 200
        status, headers, raw = client.request(
            "POST", IMAGE_STATUS_PATH, task_body("task-byok"),
            headers={IMAGE_BYOK_HEADER: BYOK_KEY})
    body_text = raw.decode("utf-8", "replace")
    assert status == 200
    assert (json.loads(raw).get("task") or {}).get("status") == "SUCCEEDED"
    assert BYOK_KEY not in body_text
    for value in headers.values():
        assert BYOK_KEY not in str(value)
    assert BYOK_KEY not in caplog.text


# V2.4.1-31
def test_v241_31_closed_gate_blocks_deploy_key_with_zero_calls(start_server) -> None:
    from src.providers.v2_dashscope_image import create_default_image_provider

    recorded = RecordingTransport([])
    client = Client(start_server(image_provider_factory=lambda: create_default_image_provider(
        environ={"DASHSCOPE_API_KEY": "sk-deploy", "AMZ_V2_DEFAULT_TRIAL": "closed"},
        transport=recorded)))
    status, payload = client.json("GET", CAPABILITIES_PATH)
    images = payload.get("images") or {}
    provider = images.get("provider") or {}
    assert status == 200 and provider.get("configured") is False
    assert provider.get("credential_source") == "none"
    assert images.get("default_trial") == "closed"
    status, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH,
                                           submit_body("verify-action-gate-closed"))
    payload = json.loads(raw)
    error = payload.get("error") or {}
    assert status == 503 and error.get("code") == "PROVIDER_NOT_CONFIGURED"
    assert payload.get("unknown") is False
    assert len(recorded.calls) == 0


# V2.4.1-32
def test_v241_32_byok_bypasses_closed_default_trial() -> None:
    from src.providers.v2_dashscope_image import create_default_image_provider
    from src.providers.v2_image import ImageFailure

    provider = create_default_image_provider(environ={"DASHSCOPE_API_KEY": "deploy-key"})
    try:
        provider.apply_credentials(api_key="byok-owned-key-0002")
    except ImageFailure:
        raise AssertionError("BYOK must apply on a gate-closed adapter")
    assert provider.credential_source == "byok"
    assert provider.capabilities().get("credential_source") == "byok"
    assert provider.api_key == "byok-owned-key-0002" and provider.api_key != "deploy-key"


# V2.4.1-33
def test_v241_33_byok_edges_fake_noop_and_blank_rejected(start_server) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    client = Client(start_server(image_provider_factory=lambda: FakeImageProvider("ok")))
    status, _, _ = client.request(
        "POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-fake-byok"),
        headers={IMAGE_BYOK_HEADER: "byok-owned-key-0003"})
    assert status == 200
    status, _, raw = client.request(
        "POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-byok-blank"),
        headers={IMAGE_BYOK_HEADER: "   "})
    error = json.loads(raw).get("error") or {}
    assert status == 400
    assert error.get("code") == "BYOK_HEADER_INVALID"
    assert error.get("family") == "input_rejected"


# V2.4.1-23
def test_v241_23_serving_writes_nothing_outside_process(start_server, tmp_path, monkeypatch) -> None:
    """Serving image requests persists nothing: the temp cwd stays empty after traffic.

    Framework-era equivalent of the old repo-manifest-diff check: the old stdlib runner
    snapshotted a copied runtime root; here the gateway serves a submit/status/result
    round-trip from an empty temp cwd and that cwd must stay empty, and serving must
    not create stray business files (only interpreter __pycache__ is tolerated).
    """
    import os as _os

    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    client = Client(start_server())
    _s, _headers, raw = client.request("POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-nopersist"))
    payload = json.loads(raw)
    task_id = (payload.get("task") or {}).get("task_id")
    client.request("POST", IMAGE_STATUS_PATH, task_body(task_id))
    client.request("POST", IMAGE_RESULT_PATH, task_body(task_id))
    assert task_id is not None
    leftovers = [path for path in work.rglob("*")
                 if "__pycache__" not in path.parts and path.suffix != ".pyc"]
    assert leftovers == []


# V2.4.1 (provider header rejection; same observable semantics as the -06 family)
def test_v241_xx_unknown_provider_header_rejected_before_any_call(start_server) -> None:
    from src.providers.v2_fake_image import FakeImageProvider

    built: list = []

    def factory():
        provider = FakeImageProvider("ok")
        built.append(provider)
        return provider

    client = Client(start_server(image_provider_factory=factory))
    status, _headers, raw = client.request(
        "POST", IMAGE_SUBMIT_PATH, submit_body("verify-action-unknown-provider"),
        headers={IMAGE_PROVIDER_HEADER: "no-such-provider"})
    payload = json.loads(raw)
    assert status == 400
    assert payload["error"]["family"] == "input_rejected"
    assert built == []


# Batch13 image pricing: effective provider + exact request shape decide the quote.
def test_pricing_default_beijing_qwen_quotes_signed_official_units(start_server) -> None:
    """默认北京 Qwen 端点报出官方 2/18 分价，且零外呼、不发送提交。"""

    from src.providers.v2_dashscope_image import create_default_image_provider

    recorded = RecordingTransport([])
    client = Client(start_server(image_provider_factory=lambda: create_default_image_provider(
        environ={}, transport=recorded)))
    status, payload = client.json("GET", CAPABILITIES_PATH)
    images = payload.get("images") or {}
    pricing = images.get("pricing") or {}
    assert status == 200
    assert pricing.get("kind") == "official"
    assert pricing.get("provider_id") == "dashscope-qwen-image"
    assert pricing.get("model_id") == "qwen-image-3.0"
    assert pricing.get("size") == "1344*1344" and pricing.get("n") == 1
    assert pricing.get("output_format") == "png" and pricing.get("currency") == "CNY"
    assert pricing.get("input_image_fen") == 2 and pricing.get("output_image_fen") == 18
    assert pricing.get("region") == "cn-beijing"
    assert len(recorded.calls) == 0


def test_pricing_custom_endpoint_cannot_inherit_beijing_rates(start_server) -> None:
    """自定义端点即使模型名一致也不继承北京价，且零外呼。"""

    from src.providers.v2_dashscope_image import create_default_image_provider

    recorded = RecordingTransport([])
    client = Client(start_server(image_provider_factory=lambda: create_default_image_provider(
        environ={"AMZ_V2_IMAGE_BASE_URL": "https://custom.aliyuncs.com/api/v1"},
        transport=recorded)))
    status, payload = client.json("GET", CAPABILITIES_PATH)
    images = payload.get("images") or {}
    provider = images.get("provider") or {}
    assert status == 200
    assert provider.get("model_id") == "qwen-image-3.0"
    assert images.get("pricing") is None
    assert len(recorded.calls) == 0


def test_pricing_fake_seam_quotes_explicit_zero_only(start_server) -> None:
    """显式注入的图像替身只报本地零价，不冒充真实供应商计费。"""

    from src.providers.v2_fake_image import FakeImageProvider

    client = Client(start_server(image_provider_factory=lambda: FakeImageProvider("ok")))
    status, payload = client.json("GET", CAPABILITIES_PATH)
    images = payload.get("images") or {}
    pricing = images.get("pricing") or {}
    assert status == 200
    assert pricing.get("kind") == "test_double"
    assert pricing.get("provider_id") == "fake-qwen-image"
    assert pricing.get("input_image_fen") == 0 and pricing.get("output_image_fen") == 0
    assert pricing.get("verified_on") is None and pricing.get("source_url") is None
    assert pricing.get("region") == "local-test"
