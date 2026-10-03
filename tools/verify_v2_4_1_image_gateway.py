#!/usr/bin/env python
"""V2.4.1 证据：无状态图像网关（submit / status / result，0 次真实模型调用）。

检查：
  1) 正式入口 --check 通过，且 capabilities 暴露图像网关合同、端点与 provider 能力。
  2) 假 provider 全链路：提交得到任务身份 → 查询成功 → 取回 PNG 字节（结果地址不外发）。
  3) 无状态不变量：每次请求都新建 provider 实例；取回结果不依赖「之前查询过」。
  4) 确定性：同一 action_id + 同一提示词 → 同一 task id、同一图片 hash。
  5) 输入拒绝矩阵：目录/工作空间字段、0 张与 4 张参考图、sha 不符、格式不受支持、超长提示词、
     非法尺寸、超字节上限，全部 400 input_rejected 且不调用上游。
  6) Unknown 语义：提交未确认与查询未确认都是 504 + unknown=true + requires_review，且不伪造 task id。
  7) 明确失败：任务状态 FAILED 是数据（200 + status=FAILED + 错误说明），不是 HTTP 失败。
  8) 真实适配器（注入假 transport，不联网）：请求形状正确（异步头、模型、data URL 参考图、参数）；
     401→502 fatal、429→重试语义、500/超时→504 Unknown、任务编号不符→504、非阿里云结果地址不下载、
     非 PNG 结果进制失败。
  9) 未配置密钥时：capabilities 仍 200 且 configured=false，提交路由 503 PROVIDER_NOT_CONFIGURED。
 10) 磁盘不变量：整轮前后仓库文件 manifest 零差异；请求带 directory 字段不会读取该目录。

运行：
  uv run --locked python tools/verify_v2_4_1_image_gateway.py
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SUBMIT_PATH = "/api/v2/images/submit"
STATUS_PATH = "/api/v2/images/status"
RESULT_PATH = "/api/v2/images/result"
CAPABILITIES_PATH = "/api/v2/capabilities"

MANIFEST_SKIP = {"__pycache__", "node_modules", "dist", "build"}


def repo_manifest() -> dict[str, str]:
    """仓库文件清单（排除缓存与 .git）：用内容 hash 证明这轮没有改到别的文件。"""

    manifest: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.relative_to(ROOT).parts)
        # 跳过多点目录（.git / .venv / .uv-cache …）与缓存目录：它们不是产品状态，
        # 但对它们做整树哈希会让「磁盘零差异」这条判据慢到不可用。
        if parts & MANIFEST_SKIP or any(part.startswith(".") for part in parts):
            continue
        try:
            manifest[path.relative_to(ROOT).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
        except OSError:
            continue
    return manifest


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def load_server_module():
    spec = importlib.util.spec_from_file_location(
        "product_v2_server_under_test", ROOT / "app" / "product_v2_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png_bytes(seed: str) -> bytes:
    from src.providers.v2_fake_image import FakeImageProvider

    return FakeImageProvider.bytes_for(seed)


def submit_body(action_id: str, *, prompt: str = "商品居中，纯白背景。", references: list | None = None,
                **extra: Any) -> bytes:
    if references is None:
        payload = png_bytes("verifier-ref")
        references = [{"role": "primary", "media_type": "image/png",
                       "sha256": hashlib.sha256(payload).hexdigest(),
                       "data_base64": base64.b64encode(payload).decode("ascii")}]
    body: dict[str, Any] = {"action_id": action_id, "prompt": prompt, "references": references}
    body.update(extra)
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


class Response:
    """假 transport 的响应替身：只实现适配器真正读的四个面。"""

    def __init__(self, status_code: int, payload: Any = None, *, headers: dict | None = None,
                 content: bytes | None = None, json_error: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error
        self.headers = dict(headers or {})
        self.content = content if content is not None else b""

    def json(self) -> Any:
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class RecordingTransport:
    """记录每一次调用的假 transport；可以按队列返回响应或直接抛异常。"""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, *, headers, json, timeout, allow_redirects):  # noqa: A002
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "json": json, "timeout": timeout, "allow_redirects": allow_redirects})
        if not self.responses:
            raise AssertionError("transport 收到了预期之外的调用：" + url)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.4.1 图像网关验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    detail_log: dict[str, Any] = {}

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    before = repo_manifest()
    module = load_server_module()
    from src.providers.v2_dashscope_image import (DEFAULT_BASE_URL, DashScopeImageProvider,
                                                  create_default_image_provider)
    from src.providers.v2_fake_image import FakeImageProvider
    from src.providers.v2_fake_semantic import FakeSemanticProvider
    from src.providers.v2_image import (ImageFailure, SubmitRequest, TaskRequest,
                                        validate_size)

    def serve(image_factory) -> tuple[Any, str]:
        port = free_port()
        server = module.create_product_v2_server(
            "127.0.0.1", port,
            provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
            image_provider_factory=image_factory)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, f"http://127.0.0.1:{port}"

    def request(base: str, method: str, path: str, body: bytes | None = None, *,
                headers_extra: dict[str, str] | None = None):
        from urllib.parse import urlsplit

        parts = urlsplit(base)
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=30)
        try:
            headers = {"Content-Type": "application/json; charset=utf-8"} if body is not None else {}
            if headers_extra:
                headers.update(headers_extra)
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return (response.status, response.getheader("Content-Type") or "",
                    {name.lower(): value for name, value in response.getheaders()}, response.read())
        finally:
            connection.close()

    def json_of(raw: bytes) -> dict:
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        return value if isinstance(value, dict) else {}

    # ------------------------------------------------ 假 provider 全链路

    server, base = serve(lambda: FakeImageProvider("ok"))
    try:
        status, _, _, raw = request(base, "GET", CAPABILITIES_PATH)
        images = (json_of(raw).get("images") or {})
        capability = images.get("provider", {}).get("capabilities", {})
        check("V2.4.1-01", "capabilities 暴露图像网关：合同、端点、provider 与参考图能力",
              status == 200 and images.get("contract") == "v2.4.1"
              and images.get("provider", {}).get("configured") is True
              and images.get("provider", {}).get("model_id") == "qwen-image-3.0"
              and capability.get("reference_images") is True
              and SUBMIT_PATH in (images.get("endpoints") or [])
              and STATUS_PATH in (images.get("endpoints") or [])
              and RESULT_PATH in (images.get("endpoints") or []),
              {"provider": images.get("provider")})

        action = "verify-action-0001"
        status, _, _, raw = request(base, "POST", SUBMIT_PATH, submit_body(action))
        payload = json_of(raw)
        task = payload.get("task") or {}
        task_id = task.get("task_id")
        check("V2.4.1-02", "提交返回任务身份，且不把上游签名结果地址外发",
              status == 200 and payload.get("ok") is True and payload.get("unknown") is False
              and task_id == FakeImageProvider.task_id_for(action)
              and task.get("status") == "RUNNING"
              and "aliyuncs" not in raw.decode("utf-8", "replace"),
              {"task": task})

        status, ctype, headers, raw = request(
            base, "POST", RESULT_PATH, json.dumps({"task_id": task_id}).encode("utf-8"))
        expected = FakeImageProvider.bytes_for(task_id)
        check("V2.4.1-03", "取回结果不依赖先查询：PNG 字节与 hash / 身份响应头一致",
              status == 200 and "image/png" in ctype and raw == expected
              and headers.get("x-image-sha256") == hashlib.sha256(raw).hexdigest()
              and headers.get("x-provider-id") == "fake-qwen-image"
              and headers.get("x-model-id") == "qwen-image-3.0"
              and headers.get("x-task-id") == task_id,
              {"bytes": len(raw), "sha": (headers.get("x-image-sha256") or "")[:12]})

        status, _, _, raw = request(
            base, "POST", STATUS_PATH, json.dumps({"task_id": task_id}).encode("utf-8"))
        payload = json_of(raw)
        check("V2.4.1-04", "查询返回权威状态与结果数量（仍然只有身份，没有地址）",
              status == 200 and (payload.get("task") or {}).get("status") == "SUCCEEDED"
              and (payload.get("task") or {}).get("result_count") == 1
              and "aliyuncs" not in raw.decode("utf-8", "replace"),
              {"task": payload.get("task")})

        status, _, _, raw = request(base, "POST", SUBMIT_PATH, submit_body(action))
        check("V2.4.1-05", "确定性：同一 action_id 两次提交得到同一任务身份",
              status == 200 and (json_of(raw).get("task") or {}).get("task_id") == task_id,
              {"task_id": (json_of(raw).get("task") or {}).get("task_id")})

        sentinel_dir = Path(tempfile.mkdtemp(prefix="amz-v241-"))
        sentinel = sentinel_dir / "sentinel.txt"
        sentinel.write_text("untouched", encoding="utf-8")
        sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        reference = json.loads(submit_body("probe"))["references"][0]
        broken_sha = dict(reference)
        broken_sha["sha256"] = "0" * 64
        unsupported = dict(reference)
        unsupported["media_type"] = "image/heic"
        probes = [
            ("目录字段", submit_body("verify-action-dir", directory=str(sentinel_dir))),
            ("工作空间字段", submit_body("verify-action-ws", workspace=str(sentinel_dir))),
            ("空白提示词", submit_body("verify-action-blank", prompt="   ")),
            ("零参考图", submit_body("verify-action-none", references=[])),
            ("四张参考图", submit_body("verify-action-four", references=[reference] * 4)),
            ("sha 与字节不符", submit_body("verify-action-sha", references=[broken_sha])),
            ("媒体类型不受支持", submit_body("verify-action-media", references=[unsupported])),
            ("超长提示词", submit_body("verify-action-long", prompt="描" * 5000)),
            ("非法尺寸", submit_body("verify-action-size", size="100*100")),
            ("非法 action_id", submit_body("bad", prompt="提示词")),
        ]
        rejections = []
        for label, body in probes:
            status, _, _, raw = request(base, "POST", SUBMIT_PATH, body)
            payload = json_of(raw)
            rejections.append({"probe": label, "status": status,
                               "family": (payload.get("error") or {}).get("family"),
                               "unknown": payload.get("unknown"),
                               "paths": [item.get("path") for item in
                                         ((payload.get("error") or {}).get("details") or {}).get("problems") or []]})
        check("V2.4.1-06", "输入拒绝矩阵：十个非法提交全部 400 input_rejected 且 unknown=false",
              all(item["status"] == 400 and item["family"] == "input_rejected"
                  and item["unknown"] is False for item in rejections),
              rejections)
        check("V2.4.1-07", "目录 / 工作空间字段被拒，且哨兵目录未被读取或改写",
              sentinel_hash == hashlib.sha256(sentinel.read_bytes()).hexdigest()
              and sorted(item.name for item in sentinel_dir.iterdir()) == ["sentinel.txt"],
              {"sentinel_dir": str(sentinel_dir),
               "paths": next((item["paths"] for item in rejections
                              if item["probe"] == "目录字段"), [])})

        oversized = (b'{"action_id":"verify-action-oversize","prompt":"'
                     + b"x" * (module.MAX_IMAGE_BODY_BYTES + 64)
                     + b'","references":[]}')
        try:
            status, _, _, raw = request(base, "POST", SUBMIT_PATH, oversized)
            payload = json_of(raw)
            rejected = (status == 400
                        and (payload.get("error") or {}).get("family") == "input_rejected")
            detail = {"status": status, "bytes": len(oversized),
                      "code": (payload.get("error") or {}).get("code")}
        except Exception as error:  # noqa: BLE001 - 旧行为在提前断连时以异常呈现
            rejected = False
            detail = {"exception": type(error).__name__ + ": " + str(error)[:160],
                      "bytes": len(oversized)}
        check("V2.4.1-08", "超过图像提交字节上限的请求被拒（400 input_rejected，不调用上游）",
              rejected, detail)

        # 2026-10-01 走查预演发现：679KB 真实商品图被 256KB 上限挡下，且提前断连被客户端
        # 误判为「结果未知」。这条正例锁住修复：真实商品图量级的提交必须被受理。
        large_head = png_bytes("large-ref")  # 合法 PNG 前缀（签名校验只看开头）
        large_bytes = large_head + os.urandom(1024 * 1024 - len(large_head))
        large_reference = {"role": "primary", "media_type": "image/png",
                           "sha256": hashlib.sha256(large_bytes).hexdigest(),
                           "data_base64": base64.b64encode(large_bytes).decode("ascii")}
        large_body = submit_body("verify-action-large-ref", references=[large_reference])
        try:
            status, _, _, raw = request(base, "POST", SUBMIT_PATH, large_body)
            payload = json_of(raw)
            accepted = (status == 200 and payload.get("ok") is True
                        and payload.get("unknown") is False)
            detail = {"status": status, "bytes": len(large_body),
                      "task": (payload.get("task") or {}).get("task_id"),
                      "error": (payload.get("error") or {}).get("code")}
        except Exception as error:  # noqa: BLE001 - 旧行为红形态：服务器提前断连
            accepted = False
            detail = {"exception": type(error).__name__ + ": " + str(error)[:160],
                      "bytes": len(large_body)}
        check("V2.4.1-25",
              "1MB 真实字节的参考图（base64≈1.4MB，真实商品图量级）提交被受理，不触字节上限",
              accepted, detail)
    finally:
        server.shutdown()
        server.server_close()

    # ------------------------------------------------ Unknown 与明确失败

    server, base = serve(lambda: FakeImageProvider("submit_unknown"))
    try:
        status, _, _, raw = request(base, "POST", SUBMIT_PATH, submit_body("verify-action-unknown"))
        payload = json_of(raw)
        error = payload.get("error") or {}
        check("V2.4.1-09", "提交未确认：504 + unknown=true + requires_review，且不伪造任务身份",
              status == 504 and payload.get("unknown") is True
              and error.get("family") == "provider_unknown"
              and error.get("retry_policy") == "requires_review" and "task" not in payload,
              {"status": status, "error": error})
    finally:
        server.shutdown()
        server.server_close()

    server, base = serve(lambda: FakeImageProvider("status_unknown"))
    try:
        status, _, _, raw = request(base, "POST", STATUS_PATH,
                                    json.dumps({"task_id": "fake-0000000000000000"}).encode("utf-8"))
        payload = json_of(raw)
        error = payload.get("error") or {}
        check("V2.4.1-10", "查询未确认：504 + unknown=true（不猜结果、不落失败）",
              status == 504 and payload.get("unknown") is True
              and error.get("family") == "provider_unknown" and "task" not in payload,
              {"status": status, "error": error})
    finally:
        server.shutdown()
        server.server_close()

    failed_id = "fake-1111111111111111"
    server, base = serve(lambda: FakeImageProvider("failed"))
    try:
        status, _, _, raw = request(base, "POST", STATUS_PATH,
                                    json.dumps({"task_id": failed_id}).encode("utf-8"))
        task = json_of(raw).get("task") or {}
        check("V2.4.1-11", "上游明确失败是数据：200 + status=FAILED + 错误说明，仍不返回地址",
              status == 200 and task.get("status") == "FAILED" and bool(task.get("error"))
              and task.get("unknown") is False,
              {"task": task})
        status, _, _, raw = request(base, "POST", RESULT_PATH,
                                    json.dumps({"task_id": failed_id}).encode("utf-8"))
        error = json_of(raw).get("error") or {}
        check("V2.4.1-12", "没有成功结果时取回被拒：502 + provider_failed(fatal)",
              status == 502 and error.get("family") == "provider_failed"
              and error.get("retry_policy") == "fatal",
              {"status": status, "error": error})
    finally:
        server.shutdown()
        server.server_close()

    server, base = serve(lambda: FakeImageProvider("download_failed"))
    try:
        status, _, _, raw = request(base, "POST", RESULT_PATH,
                                    json.dumps({"task_id": failed_id}).encode("utf-8"))
        error = json_of(raw).get("error") or {}
        check("V2.4.1-13", "结果下载失败可重试：502 + provider_failed(retryable)",
              status == 502 and error.get("family") == "provider_failed"
              and error.get("retry_policy") == "retryable",
              {"status": status, "error": error})
    finally:
        server.shutdown()
        server.server_close()

    # ------------------------------------------------ 真实适配器（注入假 transport，不联网）

    ref_png = png_bytes("verifier-ref")
    adapter_request = SubmitRequest(
        action_id="verify-action-adapter", prompt="提示词",
        references=[{"role": "primary", "media_type": "image/png",
                     "sha256": hashlib.sha256(ref_png).hexdigest(),
                     "data_base64": base64.b64encode(ref_png).decode("ascii")}],
        size="1344*1344", seed=7)

    transport = RecordingTransport([Response(
        200, {"output": {"task_id": "task-abc", "task_status": "RUNNING"}, "request_id": "req-1"})])
    provider = DashScopeImageProvider(api_key="k" * 24, transport=transport)
    adapter_task = provider.submit(adapter_request)
    call = transport.calls[0]
    body = call["json"]
    content = body["input"]["messages"][0]["content"]
    check("V2.4.1-14", "真实适配器提交形状：异步头、模型、参考图 data URL、参数与任务身份",
          call["method"] == "POST"
          and call["url"] == DEFAULT_BASE_URL + "/services/aigc/image-generation/generation"
          and call["headers"].get("X-DashScope-Async") == "enable"
          and call["headers"].get("Authorization", "").startswith("Bearer ")
          and body["model"] == "qwen-image-3.0"
          and content[0]["image"].startswith("data:image/png;base64,")
          and content[-1]["text"] == "提示词"
          and body["parameters"] == {"size": "1344*1344", "n": 1, "prompt_extend": False,
                                     "watermark": False, "seed": 7}
          and adapter_task.task_id == "task-abc" and adapter_task.status == "RUNNING",
          {"url": call["url"], "parameters": body["parameters"]})

    def adapter_failure(responses: list, *, mode: str = "status"):
        transport_probe = RecordingTransport(responses)
        probe = DashScopeImageProvider(api_key="k" * 24, transport=transport_probe)
        try:
            if mode == "submit":
                probe.submit(adapter_request)
            elif mode == "result":
                probe.result(TaskRequest(task_id="task-abc"))
            else:
                probe.status(TaskRequest(task_id="task-abc"))
        except ImageFailure as failure:
            return failure, transport_probe
        raise AssertionError("期望分类失败，但适配器返回了结果")

    f401, _ = adapter_failure([Response(401, {"code": "InvalidApiKey"})])
    f429, _ = adapter_failure([Response(429, {"code": "Throttling"})], mode="submit")
    f500, _ = adapter_failure([Response(500, {"code": "InternalError"})])
    f_timeout, _ = adapter_failure([TimeoutError("boom")])
    f_mismatch, _ = adapter_failure([Response(
        200, {"output": {"task_id": "task-other", "task_status": "SUCCEEDED"}})])
    check("V2.4.1-15", "上游错误分类：401=fatal / 429 提交可重试 / 500 与超时=Unknown / 任务号不符=Unknown",
          f401.family == "provider_failed" and f401.retry_policy == "fatal"
          and f401.code == "UPSTREAM_REJECTED"
          and f429.family == "provider_failed" and f429.retry_policy == "retryable"
          and f429.code == "UPSTREAM_RATE_LIMITED"
          and f500.family == "provider_unknown" and f500.retry_policy == "requires_review"
          and f500.unknown is True and f500.http_status == 500
          and f_timeout.family == "provider_unknown" and f_timeout.unknown is True
          and f_mismatch.family == "provider_unknown" and f_mismatch.code == "PROVIDER_TASK_MISMATCH"
          and all("提示词" not in failure.message for failure in
                  (f401, f429, f500, f_timeout, f_mismatch)),
          {"f401": f401.to_dict(), "f429": f429.to_dict(), "f500": f500.to_dict(),
           "timeout": f_timeout.to_dict(), "mismatch": f_mismatch.to_dict()})

    f_host, transport_host = adapter_failure([Response(200, {"output": {
        "task_id": "task-abc", "task_status": "SUCCEEDED",
        "results": [{"url": "https://evil.example.com/a.png"}]}})], mode="result")
    check("V2.4.1-16", "非受信结果地址不下发下载请求（RESULT_URL_MISSING，只发生一次状态查询）",
          f_host.family == "provider_failed" and f_host.code == "RESULT_URL_MISSING"
          and len(transport_host.calls) == 1,
          {"calls": [item["url"] for item in transport_host.calls]})

    ok_url = "https://dashscope-result.aliyuncs.com/task/a.png"
    transport_ok = RecordingTransport([
        Response(200, {"output": {"task_id": "task-abc", "task_status": "SUCCEEDED",
                                  "results": [{"url": ok_url}]}}),
        Response(200, content=ref_png, headers={"Content-Type": "image/png"}),
    ])
    provider_ok = DashScopeImageProvider(api_key="k" * 24, transport=transport_ok)
    content_bytes, media_type = provider_ok.result(TaskRequest(task_id="task-abc"))
    check("V2.4.1-17", "结果取回：先查权威状态再下载受信地址，返回 PNG 字节",
          content_bytes == ref_png and media_type == "image/png"
          and [item["url"] for item in transport_ok.calls] == [
              DEFAULT_BASE_URL + "/tasks/task-abc", ok_url],
          {"calls": [item["url"] for item in transport_ok.calls]})

    transport_not_png = RecordingTransport([
        Response(200, {"output": {"task_id": "task-abc", "task_status": "SUCCEEDED",
                                  "results": [{"url": ok_url}]}}),
        Response(200, content=b"not-a-png", headers={"Content-Type": "image/png"}),
    ])
    invalid_provider = DashScopeImageProvider(api_key="k" * 24, transport=transport_not_png)
    try:
        invalid_provider.result(TaskRequest(task_id="task-abc"))
        non_png_rejected = False
    except ImageFailure as failure:
        non_png_rejected = (failure.code == "RESULT_IMAGE_INVALID"
                            and failure.family == "provider_failed")
    check("V2.4.1-18", "非 PNG 结果进制失败（不做“就当它是图片”的宽容）", non_png_rejected)

    # ------------------------------------------------ 未配置密钥与注册表选择

    server, base = serve(lambda: create_default_image_provider(environ={}))
    try:
        status, _, _, raw = request(base, "GET", CAPABILITIES_PATH)
        images = json_of(raw).get("images") or {}
        check("V2.4.1-19", "未配置密钥：capabilities 仍 200，图像 provider configured=false",
              status == 200 and images.get("provider", {}).get("configured") is False,
              {"provider": images.get("provider")})
        status, _, _, raw = request(base, "POST", SUBMIT_PATH, submit_body("verify-action-nokey"))
        payload = json_of(raw)
        error = payload.get("error") or {}
        check("V2.4.1-20", "未配置密钥时提交 503 PROVIDER_NOT_CONFIGURED（没有发图）",
              status == 503 and error.get("code") == "PROVIDER_NOT_CONFIGURED"
              and error.get("family") == "internal" and payload.get("unknown") is False,
              {"status": status, "error": error})
    finally:
        server.shutdown()
        server.server_close()

    from src.providers.v2_registry import create_image_provider, load_registry, resolve_image_provider_id

    registry = load_registry()
    default_choice = resolve_image_provider_id(registry, env={})
    env_choice = resolve_image_provider_id(registry, env={"AMZ_V2_IMAGE_PROVIDER": "fake-image"})
    real_provider = create_image_provider(registry=registry, env={})
    fake_provider = create_image_provider(registry=registry, env={"AMZ_V2_IMAGE_PROVIDER": "fake-image"})
    check("V2.4.1-21", "注册表选择：默认 dashscope-image、环境变量可切 fake-image，构造不联网",
          default_choice == "dashscope-image" and env_choice == "fake-image"
          and type(real_provider).__name__ == "DashScopeImageProvider"
          and type(fake_provider).__name__ == "FakeImageProvider",
          {"default": default_choice, "env": env_choice,
           "real_model": real_provider.model_id})

    entry = run_entry(["--check"])
    check("V2.4.1-22", "正式入口自检全过（包含图像路由：提交/查询/取回/拒绝/未配置）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    # 默认 transport 回归：真实装配用的是模块级「函数式」传输，必须被规范化成 Transport 协议，
    # 否则真实提交会在 _call 里 AttributeError 变成 500（V2.4.5 真实闭环首跑发现）。
    import src.providers.v2_dashscope_image as adapter_module

    class StubRequests:
        """只实现 request() 的 requests 替身：证明默认 transport 走的是真实 HTTP 包装。"""

        def __init__(self, responses: list) -> None:
            self.responses = list(responses)
            self.calls: list[dict] = []

        def request(self, method: str, url: str, **kwargs):  # noqa: A002
            self.calls.append({"method": method, "url": url})
            item = self.responses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

    default_stub = StubRequests([
        Response(200, {"output": {"task_id": "task-default-transport", "task_status": "RUNNING"}},
                 headers={"X-Request-Id": "req-default-1"}),
    ])
    original_requests = adapter_module.requests
    adapter_module.requests = default_stub
    try:
        default_provider = create_default_image_provider(
            environ={"DASHSCOPE_API_KEY": "test-key", "AMZ_V2_DEFAULT_TRIAL": "open"})
        reference = png_bytes("verifier-ref")
        default_task = default_provider.submit(SubmitRequest(
            action_id="verify-default-transport-1",
            prompt="默认传输规范化回归。",
            references=[{"role": "primary", "media_type": "image/png",
                         "sha256": hashlib.sha256(reference).hexdigest(),
                         "data_base64": base64.b64encode(reference).decode("ascii")}],
            size="1344*1344"))
    finally:
        adapter_module.requests = original_requests
    check("V2.4.1-24",
          "默认 HTTP 传输是函数也能工作（真实提交不再 AttributeError 变 500）",
          default_task.task_id == "task-default-transport"
          and default_task.status == "RUNNING"
          and len(default_stub.calls) == 1
          and default_stub.calls[0]["method"] == "POST",
          {"task": default_task.to_dict(), "calls": len(default_stub.calls)})

    # ------------------------------------------------ 默认档开关与 BYOK（V2.R4.3）

    from src.providers.v2_credentials import resolve_default_trial

    gate_cases = [
        ({"AMZ_V2_DEFAULT_TRIAL": "1"}, True),
        ({"AMZ_V2_DEFAULT_TRIAL": "OPEN"}, True),
        ({"AMZ_V2_DEFAULT_TRIAL": "closed"}, False),
        ({"AMZ_V2_DEFAULT_TRIAL": "0"}, False),
        ({}, False),
    ]
    gate_ok = True
    gate_detail = []
    for env_case, expected in gate_cases:
        try:
            gate_ok = gate_ok and resolve_default_trial(env_case) is expected
            gate_detail.append({"case": dict(env_case), "open": resolve_default_trial(env_case)})
        except ValueError:
            gate_ok = False
            gate_detail.append({"case": dict(env_case), "raised": True})
    try:
        resolve_default_trial({"AMZ_V2_DEFAULT_TRIAL": "重新表述一下"})
        invalid_rejected = False
    except ValueError:
        invalid_rejected = True
    check("V2.4.1-26", "默认档开关解析：合法值双向、非法值必须抛错（fail-closed）",
          gate_ok and invalid_rejected, gate_detail)

    blocked_provider = create_image_provider(registry=registry,
                                             env={"DASHSCOPE_API_KEY": "deploy-key"})
    opened_provider = create_image_provider(registry=registry,
                                            env={"DASHSCOPE_API_KEY": "deploy-key",
                                                 "AMZ_V2_DEFAULT_TRIAL": "open"})
    check("V2.4.1-27",
          "默认档开关在注册表构造生效：closed 时部署密钥不进适配器，open 恢复沿用",
          blocked_provider.api_key == "" and blocked_provider.credential_source == "none"
          and blocked_provider.capabilities().get("credential_source") == "none"
          and blocked_provider.capabilities().get("stateless") is True
          and opened_provider.api_key == "deploy-key"
          and opened_provider.credential_source == "default",
          {"blocked": blocked_provider.capabilities(), "opened": opened_provider.capabilities()})

    guard_probes = [
        ("非 https", "http://dashscope.aliyuncs.com/services/aigc/image-generation/generation"),
        ("非 443 端口", "https://dashscope.aliyuncs.com:8443/tasks/task-guard"),
        ("回环 IP", "https://127.0.0.1/tasks/task-guard"),
        ("云元数据地址", "https://169.254.169.254/latest/meta-data/"),
        ("私网 IPv6", "https://[fd00::1]/tasks/task-guard"),
        ("URL 内嵌凭据", "https://user:pw@dashscope.aliyuncs.com/tasks/task-guard"),
        ("白名单外主机", "https://evil.example.com/tasks/task-guard"),
        ("后缀伪装", "https://dashscope.aliyuncs.com.evil.io/tasks/task-guard"),
    ]
    rejections = []
    for label, url in guard_probes:
        transport_probe = RecordingTransport([])
        guarded = DashScopeImageProvider(api_key="k" * 24, transport=transport_probe)
        try:
            guarded._call("守卫探针", "GET", url, headers={}, json_body=None)  # noqa: SLF001
            rejections.append({"probe": label, "blocked": False})
        except ImageFailure as failure:
            rejections.append({"probe": label, "blocked": True,
                               "code": failure.code,
                               "status": failure.http_status,
                               "calls": len(transport_probe.calls)})
    check("V2.4.1-28",
          "出站白名单：八类非法目标全部在传输前拒绝（OUTBOUND_POLICY_REJECTED，0 次上游调用）",
          all(item.get("blocked") and item.get("code") == "OUTBOUND_POLICY_REJECTED"
              and item.get("status") == 503 and item.get("calls") == 0 for item in rejections),
          rejections)

    recorded = RecordingTransport([
        Response(200, {"output": {"task_id": "task-byok", "task_status": "RUNNING"},
                       "request_id": "req-byok-1"}),
        Response(200, {"output": {"task_id": "task-byok", "task_status": "SUCCEEDED"},
                       "request_id": "req-byok-2"}),
    ])
    server, base = serve(lambda: create_default_image_provider(environ={}, transport=recorded))
    try:
        status, _, _, raw = request(
            base, "POST", SUBMIT_PATH, submit_body("verify-action-byok"),
            headers_extra={"X-AMZ-Listing-Key-Image": "byok-owned-key-0001"})
        payload = json_of(raw)
        submit_call = recorded.calls[0] if recorded.calls else {}
        check("V2.4.1-29",
              "BYOK 请求头密钥随单次请求进入适配器 Authorization；响应里不回显",
              status == 200 and payload.get("ok") is True
              and (payload.get("task") or {}).get("task_id") == "task-byok"
              and submit_call.get("headers", {}).get("Authorization") == "Bearer byok-owned-key-0001"
              and "byok-owned-key-0001" not in raw.decode("utf-8", "replace"),
              {"auth": (submit_call.get("headers", {}).get("Authorization") or "")[:12],
               "status": status})
        status, ctype, headers, raw = request(
            base, "POST", STATUS_PATH,
            json.dumps({"task_id": "task-byok"}).encode("utf-8"),
            headers_extra={"X-AMZ-Listing-Key-Image": "byok-owned-key-0001"})
        body_text = raw.decode("utf-8", "replace")
        check("V2.4.1-30",
              "BYOK 密钥不出现在响应头、响应体或任何回显位置（status 路径二次校验）",
              status == 200 and (json_of(raw).get("task") or {}).get("status") == "SUCCEEDED"
              and "byok-owned-key-0001" not in body_text
              and all("byok-owned-key-0001" not in str(value)
                      for value in headers.values()),
              {"status": status, "headers": sorted(headers)})
    finally:
        server.shutdown()
        server.server_close()

    gate_recorded = RecordingTransport([])
    server, base = serve(lambda: create_default_image_provider(
        environ={"DASHSCOPE_API_KEY": "sk-deploy", "AMZ_V2_DEFAULT_TRIAL": "closed"},
        transport=gate_recorded))
    try:
        status, _, _, raw = request(base, "GET", CAPABILITIES_PATH)
        provider_block = (json_of(raw).get("images") or {}).get("provider") or {}
        status2, _, _, raw2 = request(base, "POST", SUBMIT_PATH,
                                      submit_body("verify-action-gate-closed"))
        payload2 = json_of(raw2)
        error2 = payload2.get("error") or {}
        check("V2.4.1-31",
              "默认档关闭 + 部署密钥存在：capabilities 仍 200 且 configured=false，提交 503 且 0 次上游调用",
              status == 200 and provider_block.get("configured") is False
              and provider_block.get("credential_source") == "none"
              and (json_of(raw).get("images") or {}).get("default_trial") == "closed"
              and status2 == 503 and error2.get("code") == "PROVIDER_NOT_CONFIGURED"
              and payload2.get("unknown") is False and len(gate_recorded.calls) == 0,
              {"provider": provider_block, "submit": {"status": status2, "error": error2},
               "calls": len(gate_recorded.calls)})
    finally:
        server.shutdown()
        server.server_close()

    byok_bypass = create_default_image_provider(environ={"DASHSCOPE_API_KEY": "deploy-key"})
    try:
        byok_bypass.apply_credentials(api_key="byok-owned-key-0002")
        applied = True
    except ImageFailure:
        applied = False
    check("V2.4.1-32",
          "BYOK 绕过默认档开关：部署密钥被关时 BYOK 仍可换入同一请求的适配器",
          applied and byok_bypass.credential_source == "byok"
          and byok_bypass.capabilities().get("credential_source") == "byok"
          and byok_bypass.api_key == "byok-owned-key-0002"
          and byok_bypass.api_key != "deploy-key",
          {"credential_source": byok_bypass.credential_source,
           "api_key": byok_bypass.api_key})

    server, base = serve(lambda: FakeImageProvider("ok"))
    try:
        status, _, _, raw = request(
            base, "POST", SUBMIT_PATH, submit_body("verify-action-fake-byok"),
            headers_extra={"X-AMZ-Listing-Key-Image": "byok-owned-key-0003"})
        fake_ok = status == 200 and json_of(raw).get("ok") is True
        status_blank, _, _, raw_blank = request(
            base, "POST", SUBMIT_PATH, submit_body("verify-action-byok-blank"),
            headers_extra={"X-AMZ-Listing-Key-Image": "   "})
        blank_error = (json_of(raw_blank).get("error") or {})
        check("V2.4.1-33",
              "BYOK 边界：测试替身显式 no-op；空白 BYOK 头无论 provider 是谁都 400 BYOK_HEADER_INVALID",
              fake_ok
              and status_blank == 400
              and blank_error.get("code") == "BYOK_HEADER_INVALID"
              and blank_error.get("family") == "input_rejected",
              {"fake_submit": status, "blank_submit": status_blank, "error": blank_error})
    finally:
        server.shutdown()
        server.server_close()

    after = repo_manifest()
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(name for name in set(before) & set(after) if before[name] != after[name])
    check("V2.4.1-23", "磁盘不变量：整轮前后仓库 manifest 零差异（服务不落任何用户状态）",
          not added and not removed and not changed,
          {"files": len(before), "added": added[:5], "removed": removed[:5], "changed": changed[:5]})

    # ------------------------------------------------ 证据落盘

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明图像网关在真实 HTTP 上可用且无状态：提交只返回任务身份（provider 与 model 身份、task id、"
        "状态、结果数量、错误与 request id），签名结果地址只在进程内使用；查询与取回各自独立，取回结果"
        "不依赖先前是否查询过；输入里的目录/工作空间字段、参考图数量与内容、尺寸、提示词长度与请求体上限"
        "都被拒绝且不调用上游；上游 4xx 是明确失败（429 与欠费可重试），5xx、连接中断、任务号不符与"
        "无法解析都归 Unknown 并要求人工核对，绝不自动重提；未配置密钥时 capabilities 仍 200 且明确"
        "configured=false，提交返回 503 PROVIDER_NOT_CONFIGURED。默认档开关未显式开启时部署密钥不进"
        "适配器（两级 fail-closed，capabilities 同时给出 credential_source 与 default_trial 状态）；"
        "出站白名单在任何传输生效之前拒绝非 https/非 443/私网与白名单外目标；BYOK 请求头只随单次"
        "请求进入内存并被本次提交使用，服务器不落盘、不在响应头/响应体/错误里回显。真实适配器的"
        "请求形状与错误分类由注入的假 transport 断言，整轮 0 次真实模型调用、0 次网络请求、"
        "仓库文件 manifest 零差异。"
        "不证明：真实出图质量、真实参考图是否被上游接受、候选 Blob、审核报告、返工与交付 ZIP——"
        "这些属于 V2.4.2 起的批次。"
    )
    report = {
        "task": "V2.4.1",
        "suite_id": "v2.4.1-image-gateway",
        "status": status,
        "finished_at": finished_at,
        "model_calls": 0,
        "network_calls": 0,
        "checks": checks,
        "console_errors": [],
        "page_errors": [],
        "screenshots": [],
        "boundary": boundary,
    }
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.4.1-image-gateway-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.4.1-image-gateway-{stamp}{label}.txt"
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.4.1 stateless image gateway",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 · network_calls: 0 (fake provider + injected transport)",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False)[:700])
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.4.1 无状态图像网关验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False)[:700])
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


def run_entry(args: list[str], timeout: int = 180) -> dict:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "app" / "server.py"), *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )
    return {"args": args, "rc": completed.returncode,
            "tail": (completed.stdout + completed.stderr).strip().splitlines()[-8:]}


if __name__ == "__main__":
    sys.exit(main())
