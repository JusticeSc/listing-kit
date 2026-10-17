"""网关协议组：静态产物策略、路由形态、正文上限、连接语义、并发与秘密不外泄。

P3 迁移：原 `app/product_v2_server.py::run_self_check()` 的静态/路由/传输断言与
`tools/verify_v2_4_1_image_gateway.py` 的路由级拒绝矩阵在此按 pytest 真实跑。
只走真实 TCP，不开工作线程以外的任何替身；假 provider 由 conftest 显式注入。
"""
from __future__ import annotations

import base64
import concurrent.futures
import json
import logging
import socket
import threading
from pathlib import Path

import pytest

from app.product_v2_http import StaticRootMissing, resolve_static_root
from app.product_v2_server import (
    ANALYZE_PATH,
    IMAGE_RESULT_PATH,
    IMAGE_STATUS_PATH,
    IMAGE_SUBMIT_PATH,
    REVIEW_PATH,
    SUITE_REVIEW_PATH,
)
from tests.conftest import Client, http_head, raw_exchange

SECRET_SENTINEL = "sk-pytest-secret-9f2c4d6e8a10b12c"
ROOT = Path(__file__).resolve().parents[2]


def analyze_payload(**overrides) -> dict:
    payload = {
        "product_name": "测试商品",
        "description": "测试用的商品资料。",
        "selling_points": ["测试卖点"],
        "focus": "测试重点",
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

    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    raw = zlib.compress(b"\x00\x80")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def test_static_build_artifact_is_served_and_typescript_is_denied(client: Client) -> None:
    status, headers, body = client.request("GET", "/")
    assert status == 200 and "text/html" in headers["content-type"]
    assert b"Product V2" in body
    assert headers["cache-control"] == "no-store"

    status, headers, _ = client.request("GET", "/app.js")
    assert status == 200 and "javascript" in headers["content-type"]

    status, headers, _ = client.request("GET", "/styles.css")
    assert status == 200 and "css" in headers["content-type"]

    for denied in ("/domain/attempt.ts", "/domain/type-contracts.d.ts"):
        status, _, _ = client.request("GET", denied)
        assert status == 404, denied


@pytest.mark.parametrize("path", [
    "/../README.md",
    "/%2e%2e/README.md",
    "/storage/../../app/server.py",
    "/..%2f..%2fapp/server.py",
])
def test_path_traversal_is_denied(client: Client, path: str) -> None:
    status, _, _ = client.request("GET", path)
    assert status == 404, path


def test_missing_build_artifact_is_explicit_and_never_falls_back(
        static_root, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """没有构建产物时必须显式失败；源码目录存在也不构成回退理由。"""

    import app.product_v2_http as http_host

    missing = tmp_path / "dist" / "product-v2"
    monkeypatch.setattr(http_host, "PRODUCTION_STATIC_DIR", missing)
    assert (ROOT_SOURCE := ROOT / "app" / "product_v2").is_dir()  # 源码在，仍不回退
    with pytest.raises(StaticRootMissing):
        resolve_static_root(None)

    with pytest.raises(StaticRootMissing):
        resolve_static_root(tmp_path / "not-built")

    # 显式给了真实构建产物目录时才放行。
    assert resolve_static_root(static_root) == static_root.resolve()


def test_unknown_routes_have_product_shaped_404(client: Client) -> None:
    status, headers, body = client.request("GET", "/api/v2/nope")
    assert status == 404 and "application/json" in headers["content-type"]
    assert json.loads(body) == {"ok": False, "error": "NOT_FOUND", "path": "/api/v2/nope"}

    status, _, body = client.request("POST", "/api/v2/not-a-route", b"{}")
    assert status == 404 and json.loads(body)["error"] == "NOT_FOUND"

    status, headers, body = client.request("GET", "/no-such-page.html")
    assert status == 404 and "text/plain" in headers["content-type"]
    assert body == b"not found"

    # 旧 V1/目录式 API 一律不存在（无兼容层）。
    for legacy in ("/api/workspaces/recent", "/api/workspace", "/harness/storage-contract.html"):
        status, _, _ = client.request("GET", legacy)
        assert status == 404, legacy


def test_health_reports_stateless_server(client: Client) -> None:
    status, payload = client.json("GET", "/api/health")
    assert status == 200 and payload["product"] == "v2"
    assert payload["server_state"] == "none"
    assert payload["app"] == "amz-listing-kit"


def test_capabilities_expose_contracts_without_fake_entries(client: Client) -> None:
    status, payload = client.json("GET", "/api/v2/capabilities")
    assert status == 200 and payload["ok"] is True
    assert payload["analyze_fields"]
    assert payload["semantic_contract"]
    images = payload["images"]
    assert IMAGE_SUBMIT_PATH in images["endpoints"]
    assert IMAGE_STATUS_PATH in images["endpoints"] and IMAGE_RESULT_PATH in images["endpoints"]
    assert images["contract"] and images["submit_fields"]
    assert images["provider"]["capabilities"]["reference_images"] is True
    assert payload["review"]["endpoint"] == REVIEW_PATH
    assert payload["suite_review"]["endpoint"] == SUITE_REVIEW_PATH
    # 显式注入的替身只在本装配的接缝里可见（目录仍只列有限用途条目）。
    choices = payload.get("provider_choices") or {}
    assert set(choices) == {"semantic", "image", "review"}, choices
    assert any(item["id"].startswith("fake-") for item in choices["image"]), choices


def test_production_catalog_never_lists_fake_entries(plain_server) -> None:
    """不注入替身时（真实注册表默认 + 默认档 fail-closed）目录里没有 fake 条目。"""

    status, payload = Client(plain_server).json("GET", "/api/v2/capabilities")
    assert status == 200
    choices = payload.get("provider_choices") or {}
    assert choices, payload
    assert "fake" not in json.dumps(choices, ensure_ascii=False).lower()
    images = payload["images"]
    assert images["provider"]["configured"] is False, images["provider"]
    assert images["default_trial"] == "closed"


def test_per_route_body_limit_rejects_with_declared_boundary(client: Client) -> None:
    from app.product_v2_server import MAX_IMAGE_BODY_BYTES, analyze_body_limit

    limit = analyze_body_limit()
    oversized = json.dumps({"product_name": "x" * (limit + 512)}).encode("utf-8")
    status, headers, body = client.request("POST", ANALYZE_PATH, oversized)
    payload = json.loads(body)
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    assert payload["error"]["details"]["problems"] == {
        "content_length": len(oversized), "limit": limit}

    huge = json.dumps({"action_id": "verify-action-oversize", "prompt": "x" * (MAX_IMAGE_BODY_BYTES + 64),
                       "references": []}).encode("utf-8")
    status, _, body = client.request("POST", IMAGE_SUBMIT_PATH, huge)
    payload = json.loads(body)
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    assert payload["error"]["details"]["problems"]["limit"] == MAX_IMAGE_BODY_BYTES


def test_transfer_encoding_and_bad_length_are_rejected(client: Client) -> None:
    status, _, body = client.request(
        "POST", ANALYZE_PATH, b"{}", headers={"Transfer-Encoding": "chunked"})
    assert status == 400 and "Transfer-Encoding" in json.dumps(json.loads(body), ensure_ascii=False)

    status, _, body = client.request("POST", ANALYZE_PATH, b"", headers={"Content-Length": "0"})
    assert status == 400 and json.loads(body)["error"]["family"] == "input_rejected"

    payload = client.json("POST", ANALYZE_PATH, analyze_payload())
    assert payload[0] == 200, payload


def test_unread_body_frames_never_smuggle_a_second_request_body(gateway) -> None:
    """带未读正文的请求必须只产生有界响应；残留字节要么被关闭，要么被当成下一条请求。

    P3 换框架后这条契约由 h11 负责实现：不再断言“必定 Connection: close”，而是断言
    每份响应的正文长度都等于自己声明的 Content-Length，且后续字节只能解析成下一条
    合法请求的响应——这正是旧检查要防的“残留正文字节被错解”场景。
    """

    for method, path, framing, expect in (
        ("POST", ANALYZE_PATH, "Transfer-Encoding: chunked", b"HTTP/1.1 400 "),
        ("POST", ANALYZE_PATH, "Transfer-Encoding: chunked\r\nContent-Length: 0", b"HTTP/1.1 400 "),
        ("POST", ANALYZE_PATH, "", b"HTTP/1.1 400 "),
        ("GET", "/api/health", "Transfer-Encoding: chunked", b"HTTP/1.1 200 "),
    ):
        wire = (f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                + (f"{framing}\r\n" if framing else "")
                + "Connection: keep-alive\r\n\r\n2\r\n{}\r\n0\r\n\r\n"
                + "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        received = raw_exchange(gateway, wire.encode("ascii"))
        responses: list[tuple[bytes, bytes]] = []
        remainder = received
        while remainder:
            status_line, body, headers = http_head(remainder)
            if not status_line.startswith(b"HTTP/1.1 "):
                break
            if headers.get(b"transfer-encoding") == b"chunked":
                # 框架在应用之前直接拒绝畸形帧：连接关闭，不再有后续响应。
                assert headers.get(b"connection") == b"close", (method, path, framing)
                responses.append((status_line, body))
                remainder = b""
                break
            declared = headers.get(b"content-length", b"")
            assert declared.isdigit(), (method, path, framing, status_line, headers)
            length = int(declared)
            head_end = remainder.index(b"\r\n\r\n") + 4
            responses.append((status_line, remainder[head_end:head_end + length]))
            remainder = remainder[head_end + length:]
        assert responses, (method, path, framing, received)
        assert responses[0][0].startswith(expect), (method, path, framing, responses[0][0])
        for status_line, body in responses[1:]:
            # 后续字节要么是完整送出的下一条合法请求的响应（health JSON），
            # 要么是框架对畸形字节的明确 400；两者都不允许 5xx 与正文错解。
            assert not status_line.startswith(b"HTTP/1.1 5"), (method, path, framing, status_line)
            if status_line.startswith(b"HTTP/1.1 200 "):
                assert json.loads(body.decode("utf-8"))["server_state"] == "none"
            else:
                assert status_line.startswith(b"HTTP/1.1 400 "), (method, path, framing, status_line)
        assert remainder == b"", (method, path, framing, received)


def test_truncated_body_is_rejected_and_server_survives(gateway) -> None:
    with socket.create_connection(("127.0.0.1", gateway.port), timeout=5) as connection:
        connection.settimeout(5)
        connection.sendall(
            f"POST {ANALYZE_PATH} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n".encode("ascii"))
        connection.sendall('{"product_name": "半截'.encode("utf-8"))
        connection.shutdown(socket.SHUT_WR)
        received = connection.recv(4096)

    status_line = received.split(b"\r\n", 1)[0]
    # 换框架后由 h11 在应用之前判定“正文读不满”：要么明确 400，要么直接断开连接；
    # 两者都不允许出现 5xx，也不允许把半截正文当成一次成功请求。
    assert received == b"" or status_line.startswith(b"HTTP/1.1 400 "), received[:200]
    assert b"500" not in status_line
    assert Client(gateway).request("GET", "/api/health")[0] == 200


def test_abrupt_disconnect_does_not_break_the_gateway(gateway) -> None:
    for _ in range(3):
        connection = socket.create_connection(("127.0.0.1", gateway.port), timeout=5)
        connection.sendall(b"POST " + ANALYZE_PATH.encode("ascii") + b" HTTP/1.1\r\nHost: x\r\n")
        connection.close()  # 头都没发完就断开
    assert Client(gateway).request("GET", "/api/health")[0] == 200
    status, payload = Client(gateway).json("POST", ANALYZE_PATH, analyze_payload())
    assert status == 200 and payload["ok"] is True


def test_concurrent_real_tcp_requests_all_succeed(gateway) -> None:
    payload = analyze_payload()
    barrier = threading.Barrier(8)
    errors: list[str] = []

    def worker(index: int) -> None:
        client = Client(gateway)
        barrier.wait(timeout=10)
        for _ in range(3):
            status, decoded = client.json("POST", ANALYZE_PATH, payload)
            if status != 200 or decoded.get("ok") is not True:
                errors.append(f"analyze {index} status={status} body={decoded}")
            status, decoded = client.json("GET", "/api/health")
            if status != 200 or decoded.get("server_state") != "none":
                errors.append(f"health {index} status={status}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(8)))
    assert errors == []


def test_request_level_secrets_never_echo_or_log(gateway, caplog: pytest.LogCaptureFixture) -> None:
    """三用途请求头只在本次请求内存里；长度非法报 400，响应与日志都不含密钥原文。"""

    client = Client(gateway)
    too_long = SECRET_SENTINEL + "x" * 600
    image_key = SECRET_SENTINEL + "-image"
    semantic_key = SECRET_SENTINEL + "-semantic"

    with caplog.at_level(logging.DEBUG):
        status, _headers, raw = client.request(
            "POST", ANALYZE_PATH, json.dumps(analyze_payload()).encode("utf-8"),
            headers={"X-AMZ-Listing-Key-Semantic": too_long,
                     "X-AMZ-Listing-Key-Image": image_key})
    body = raw.decode("utf-8", "replace")
    assert status == 400 and json.loads(body)["error"]["code"] == "BYOK_HEADER_INVALID"
    assert SECRET_SENTINEL not in body
    assert SECRET_SENTINEL not in caplog.text

    # 非法 JSON 的错误消息不回显正文里的疑似密钥。
    with caplog.at_level(logging.DEBUG):
        status, _headers, raw = client.request(
            "POST", ANALYZE_PATH,
            json.dumps({"api_key": SECRET_SENTINEL, "note": "not json"}).encode("utf-8")[:40],
            headers={"X-AMZ-Listing-Key-Semantic": semantic_key})
    assert status == 400 and SECRET_SENTINEL not in raw.decode("utf-8", "replace")
    assert SECRET_SENTINEL not in caplog.text

    # 正常请求携带 BYOK 头也不把它写进任何响应头。
    status, headers, raw = client.request(
        "POST", ANALYZE_PATH, json.dumps(analyze_payload()).encode("utf-8"),
        headers={"X-AMZ-Listing-Key-Semantic": semantic_key})
    assert status == 200
    assert SECRET_SENTINEL not in json.dumps(headers, ensure_ascii=False)
    assert SECRET_SENTINEL not in raw.decode("utf-8", "replace")


def test_reference_image_bytes_are_validated_before_any_model_call(start_server) -> None:
    from src.providers.v2_fake_semantic import FakeSemanticProvider

    calls = {"analyze": 0}

    class VisionFakeSemantic(FakeSemanticProvider):
        supports_images = True

        def analyze(self, request, images):  # noqa: ANN001, ARG002
            calls["analyze"] += 1
            return super().analyze(request)

    client = Client(start_server(provider_factory=lambda: VisionFakeSemantic(scenario="ok")))
    image = png_1x1()
    metadata = {"sha256": __import__("hashlib").sha256(image).hexdigest(),
                "media_type": "image/png", "role": "primary"}
    good = analyze_payload(references=[metadata], reference_images=[
        {**metadata, "data_base64": base64.b64encode(image).decode("ascii")}])
    status, payload = client.json("POST", ANALYZE_PATH, good)
    assert status == 200 and payload["ok"] is True and calls["analyze"] == 1

    bad = json.loads(json.dumps(good))
    bad["reference_images"][0]["sha256"] = "b" * 64
    status, payload = client.json("POST", ANALYZE_PATH, bad)
    assert status == 400 and payload["error"]["family"] == "input_rejected"
    assert calls["analyze"] == 1, calls  # 身份不符在调用模型前就被拒


def test_image_routes_reject_unknown_provider_header_before_calling_out(gateway) -> None:
    client = Client(gateway)
    body = {"action_id": "verify-action-unknown-provider", "prompt": "一张白色马克杯",
            "references": []}
    status, payload = client.json("POST", IMAGE_SUBMIT_PATH, body,
                                  headers={"X-AMZ-Listing-Provider-Image": "no-such-provider"})
    assert status == 400 and payload["error"]["family"] == "input_rejected"

    # 三条图像路由与两条复核路由都只认自己的契约字段；缺字段一律 400，不进 provider。
    for path in (IMAGE_SUBMIT_PATH, IMAGE_STATUS_PATH, IMAGE_RESULT_PATH,
                 REVIEW_PATH, SUITE_REVIEW_PATH):
        status, payload = client.json("POST", path, {"unexpected": True})
        assert status == 400 and payload["error"]["family"] == "input_rejected", (path, status)
