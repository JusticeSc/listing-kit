#!/usr/bin/env python
"""V2.R5.2 证据：第二真实图片 Adapter（火山方舟 doubao-seedream-5-0-flash-260915，0 次真实模型调用）。

离线验收（真实状态/付费链分开交付；见计划 §12.3「协议 / R5.2」）：
  1) ESM/语法门：domain + generation + workspace + harness 全部 node --check。
  2) node --test 镜像域套件：预存失败点名保留（不许靠重跑掩盖）。
  3) Adapter 单元（注入 transport）：请求形状（model/prompt/size「WxH」/b64_json/png/
     watermark/参考图 data URL）、SUCCEEDED + task_id=null + sync 字节、request_id、
     429 / 欠费 / 4xx / 5xx / 超时 / 空数据 / 非 PNG、status/result 路由拒绝、fail-closed、
     出站白名单、BYOK 替换、注册表装配。
  4) Python HTTP 网关层：capabilities → volcengine-ark；提交 → 200 信封（字节 + sha 可复核、
     transport 恰一次调用）；status → 501；能力版本漂移 → 400 不转发。
  5) 浏览器 harness A01–A19 全过 + 3 个既有契约套件回归（真实 Chromium）。
  6) 浏览器 e2e（fake transport × 同步 Adapter）：整流到候选入库、刷新恢复、显式新建
     再成功、fresh module 缺字节明确补救、0 status 外呼、零 console error，截图落盘。
  7) 正式入口 --check 全过。

运行：
  uv run --locked python tools/verify_v2_r5_2_two_adapters.py
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
import v2_verify_shared as shared  # noqa: E402

from console import enable_utf8  # noqa: E402

enable_utf8()

PRODUCT_DIR = ROOT / "app" / "product_v2"
HARNESS_DIR = ROOT / "evals" / "product-v2" / "harness"
EVIDENCE_DIR = ROOT / "evals" / "product-v2"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

DOMAIN_FILES = [
    "app/product_v2/domain/errors.js",
    "app/product_v2/domain/slots.js",
    "app/product_v2/domain/intake.js",
    "app/product_v2/domain/brief.js",
    "app/product_v2/domain/invalidation.js",
    "app/product_v2/domain/suite-plan.js",
    "app/product_v2/domain/suite.js",
    "app/product_v2/domain/specs.js",
    "app/product_v2/domain/prompt.js",
    "app/product_v2/domain/confirm.js",
    "app/product_v2/domain/attempt.js",
    "app/product_v2/domain/candidate.js",
    "app/product_v2/domain/batch.js",
    "app/product_v2/domain/index.js",
    "app/product_v2/generation.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/attempt-contract.js",
    "evals/product-v2/harness/candidate-contract.js",
    "evals/product-v2/harness/batch-contract.js",
]

EXPECTED_CASES = [f"A{index:02d}" for index in range(1, 20)]
REGRESSION_SUITES = (
    ("confirm", "confirm-contract.html", "__V2_CONFIRM_RESULTS__"),
    ("prompt_edit", "prompt-edit-contract.html", "__V2_PROMPT_EDIT_RESULTS__"),
    ("suite_editor", "suite-editor-contract.html", "__V2_SUITE_EDITOR_RESULTS__"),
)

SEED_SLOTS = """
async (projectId) => {
  const domain = await import("/domain/index.js");
  const storage = await import("/storage/index.js");
  const opened = await storage.openStorage({});
  try {
    const repository = opened.repository;
    const slot = (slotId, value) => {
      const definition = domain.coreSlotDefinition(slotId);
      return {
        schema_version: 1, slot_id: slotId, label: definition.label,
        authority: "core_fixed", value_type: definition.value_type,
        critical: definition.critical, value: value, source: "user_input",
        status: "confirmed", confidence: null,
        evidence: [{ kind: "user", ref: "r52-sync-seed" }], depends_on: [],
      };
    };
    await repository.documents.save(projectId, {
      kind: "fact_slot", documentId: "product_name", payload: slot("product_name", "便携保温杯"),
    });
    await repository.documents.save(projectId, {
      kind: "fact_slot", documentId: "product_category", payload: slot("product_category", "保温杯"),
    });
    await repository.documents.save(projectId, {
      kind: "fact_slot", documentId: "signature_features",
      payload: slot("signature_features", ["304不锈钢内胆", "12小时保温"]),
    });
    return { slots: 3 };
  } finally {
    opened.close();
  }
}
"""

ID_PROJECTS_PROBE = """
async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const rows = await new Promise((resolve, reject) => {
    const request = db.transaction("projects", "readonly")
      .objectStore("projects").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  return rows.map((item) => item.project_id);
}
"""

ID_DB_PROBE = """
async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const read = (store) => new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await read("documents");
  const assets = await read("assets");
  db.close();
  const chains = {};
  for (const item of documents.filter((row) => row.kind === "generation_attempt")) {
    (chains[item.document_id] = chains[item.document_id] || []).push({
      version: item.version, payload: item.payload,
    });
  }
  for (const key of Object.keys(chains)) {
    chains[key].sort((left, right) => left.version - right.version);
  }
  const candidates = {};
  for (const item of documents.filter((row) => row.kind === "candidate")) {
    (candidates[item.document_id] = candidates[item.document_id] || []).push({
      version: item.version, payload: item.payload,
    });
  }
  const prompts = {};
  for (const item of documents.filter((row) => row.kind === "prompt_version")) {
    if (!prompts[item.document_id] || prompts[item.document_id].version < item.version) {
      prompts[item.document_id] = { version: item.version, payload: item.payload };
    }
  }
  const confirmations = documents.filter((row) => row.kind === "generation_confirm");
  for (const key of Object.keys(candidates)) {
    candidates[key].sort((left, right) => left.version - right.version);
  }
  const plans = documents.filter((item) => item.kind === "suite_plan")
    .sort((left, right) => left.version - right.version);
  const plan = plans.length ? plans[plans.length - 1] : null;
  const rows = [...document.querySelectorAll("#attempt-list .attempt-row")].map((node) => ({
    shot_id: node.getAttribute("data-shot-id"),
    state: node.getAttribute("data-attempt-state"),
    candidate_text: (node.querySelector(".attempt-candidate") || {}).textContent || null,
  }));
  return {
    shot_ids: plan ? plan.payload.shots.map((shot) => shot.shot_id) : [],
    attempt_chains: chains,
    candidates: candidates,
    prompts: prompts,
    confirmations: confirmations,
    assets: assets.map((item) => ({ sha256: item.sha256, byte_size: item.byte_size })),
    ui_rows: rows,
  };
}
"""

BYTES_MISSING_PROBE = """
async ({projectId}) => {
  const gen = await import("/generation.js");
  const storage = await import("/storage/index.js");
  const opened = await storage.openStorage({});
  try {
    const repository = opened.repository;
    const noop = () => {};
    const mod = gen.createGenerationModule({
      beginAction: () => ({ alive: () => true, projectId }),
      projectIdReader: () => projectId,
      environmentReader: () => null,
      requestHeaders: () => ({}),
      suitePlanReader: () => ({ shots: [{ shot_id: "shot_probe", role_id: "main" }] }),
      suiteSummaryReader: () => null,
      promptEntryReader: () => null,
      confirmationReader: () => null,
      promptBasisReader: () => null,
      referenceSourceReader: () => [],
      promptsSheet: () => null,
      imageEnvironment: () => null,
      renderAttempts: noop, renderBatch: noop, status: noop,
      attemptError: noop, clearAttemptError: noop,
      repository,
    });
    const now = "2026-10-03T00:00:00.000Z";
    const actionId = "act-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
    await repository.documents.save(projectId, { kind: "generation_attempt", documentId: "shot_probe", payload: {
        schema_version: 2, action_id: actionId, shot_id: "shot_probe",
        state: "succeeded", task_id: null, request_id: "req-probe",
        prompt: { version: 1, hash: "a".repeat(64) },
        references: [{ role: "primary", sha256: "a".repeat(64) }],
        provider: { provider_id: "volcengine-ark",
                    model_id: "doubao-seedream-5-0-flash-260915" },
        parameters: { size: "1344*1344" },
        execution_identity: { schema_version: 1, protocol: "v2.4.1",
          capability_version: 3, credential_reference: { source: "test_double" },
          sync: true },
        notes: [], created_at: now, updated_at: now,
      } });
    await mod.restore({ alive: () => true, projectId });
    const outcome = await mod.storeCandidate("shot_probe",
      { action: { alive: () => true, projectId } });
    return { failed: outcome.failed === true, reason: outcome.reason || null,
             message: outcome.message || null };
  } finally {
    opened.close();
  }
"""


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def png_bytes(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        head = len(payload).to_bytes(4, "big") + tag + payload
        return head + (zlib.crc32(tag + payload) & 0xFFFFFFFF).to_bytes(4, "big")

    ihdr = width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def load_server_module():
    spec = importlib.util.spec_from_file_location(
        "product_v2_server_under_test", ROOT / "app" / "product_v2_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def post_json(base: str, path: str, payload: dict) -> tuple[int, dict]:
    import urllib.error
    import urllib.request
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def get_json(base: str, path: str) -> tuple[int, dict]:
    import urllib.request
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def run_entry(args: list[str], timeout: int = 180) -> dict:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "app" / "server.py"), *args],
        capture_output=True, text=True, timeout=timeout, env=env)
    return {
        "rc": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def run_node_checks() -> dict:
    results = []
    for relative in DOMAIN_FILES:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)],
                                   capture_output=True, text=True)
        results.append({"file": relative, "rc": completed.returncode,
                        "error": (completed.stderr or "")[-200:]})
    return {"ok": all(item["rc"] == 0 for item in results), "files": results}


def run_node_domain_tests() -> dict:
    files = [str(item) for item in sorted((ROOT / "evals/product-v2/node").glob("*.test.mjs"))]
    completed = subprocess.run(["node", "--test", *files],
                               capture_output=True, text=True, cwd=str(ROOT))
    summary = [line.strip() for line in (completed.stdout or "").splitlines()
               if line.strip().startswith(("ℹ pass", "ℹ fail", "✖ "))]
    return {"rc": completed.returncode, "tail": summary[-6:]}


class HarnessHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        return

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path.startswith("/harness/"):
            candidate = (HARNESS_DIR / path[len("/harness/"):]).resolve()
            if str(candidate).startswith(str(HARNESS_DIR.resolve())) and candidate.is_file():
                body = candidate.read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type", MIME.get(candidate.suffix, "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
        candidate = (PRODUCT_DIR / path.lstrip("/")).resolve()
        if str(candidate).startswith(str(PRODUCT_DIR.resolve())) and candidate.is_file():
            body = candidate.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", MIME.get(candidate.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"not found")

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.end_headers()


def start_static_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), HarnessHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def read_suite(browser, url: str, variable: str, console_errors: list, page_errors: list) -> dict:
    page = browser.new_page()
    try:
        page.on("console", lambda message: console_errors.append("[suite] " + message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append("[suite] " + str(error)))
        page.goto(url, wait_until="networkidle")
        page.wait_for_function(
            f"() => {{ const r = window.{variable};"
            " return r && r.status && r.status !== 'running'; }", timeout=120_000)
        return page.evaluate(f"() => window.{variable}")
    finally:
        page.close()


class TransportRecorder:
    """可注入的假 HTTP 传输：记录调用、按脚本返回响应。"""

    class Response:
        def __init__(self, status_code: int, payload, headers=None) -> None:
            self.status_code = status_code
            self._payload = payload
            self.headers = headers or {}

        def json(self):
            return self._payload

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.calls: list[dict] = []
        self.responses = list(responses or [])

    def script_success(self, content: bytes, request_id: str = "req-ark-fixed") -> None:
        self.responses.append({
            "status": 200,
            "body": {"data": [{"b64_json": base64.b64encode(content).decode("ascii")}]},
            "headers": {"X-Request-Id": request_id},
        })

    def request(self, method, url, *, headers, json, timeout, allow_redirects):
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "json": json, "timeout": timeout})
        script = self.responses.pop(0) if self.responses else {"status": 200, "body": {}}
        body = script["body"]
        if callable(body):
            body = body(self.calls[-1])
        return self.Response(script["status"], body,
                             script.get("headers", {"X-Request-Id": "req-ark-001"}))


def _call_failure(callable_, image_contract):
    try:
        callable_()
        return None
    except image_contract.ImageFailure as failure:
        return failure


def adapter_unit_checks(check) -> None:
    from src.providers import v2_image as image_contract
    from src.providers import v2_registry
    from src.providers.v2_image import SubmitRequest, TaskRequest
    from src.providers.v2_volcengine_image import VOLCENGINE_MODEL_ID, VolcengineImageProvider

    check("R52-U01", "能力档常量：capability_version=3、契约 v2.4.1",
          image_contract.IMAGES_CAPABILITY_VERSION == 3
          and image_contract.IMAGE_CONTRACT_VERSION == "v2.4.1",
          {"capability": image_contract.IMAGES_CAPABILITY_VERSION})

    reference = png_bytes(8, 8, (20, 30, 40))
    expression = base64.b64encode(reference).decode("ascii")
    reference_digest = hashlib.sha256(reference).hexdigest()
    request = SubmitRequest.model_validate({
        "action_id": "act-11111111-2222-3333-4444-555555555555",
        "prompt": "参考图主图，白色背景，产品居中。",
        "references": [{"role": "primary", "media_type": "image/png",
                        "sha256": reference_digest, "data_base64": expression}],
        "size": "1344*1344",
        "target": {"provider_id": "volcengine-ark", "model_id": VOLCENGINE_MODEL_ID,
                   "protocol": "v2.4.1", "capability_version": 3},
    })

    def make_provider(script: list[dict], **kwargs) -> tuple:
        transport = TransportRecorder(script)
        provider = VolcengineImageProvider(
            api_key="test-key", credential_source="test_double", transport=transport, **kwargs)
        return provider, transport

    success_body = {"model": VOLCENGINE_MODEL_ID, "data": [{"b64_json": expression}]}
    provider, transport = make_provider([{"status": 200, "body": success_body,
                                          "headers": {"X-Request-Id": "req-ark-fixed"}}])
    result = provider.submit(request)
    call = transport.calls
    check("R52-U02", "提交成功：一次调用 + 请求形状（model/size/b64_json/png/watermark）",
          len(call) == 1 and call[0]["json"]["model"] == VOLCENGINE_MODEL_ID
          and call[0]["json"]["size"] == "1344x1344"
          and call[0]["json"]["response_format"] == "b64_json"
          and call[0]["json"]["output_format"] == "png"
          and call[0]["json"]["watermark"] is False
          and call[0]["json"]["prompt"] == request.prompt
          and call[0]["headers"]["Authorization"] == "Bearer test-key"
          and str(call[0]["json"]["image"][0]).startswith("data:image/png;base64,"),
          {"calls": len(call), "prompt_head": request.prompt[:18]})
    check("R52-U03", "成功结果：SUCCEEDED + task_id=null + 原样字节 + request_id",
          result.status == "SUCCEEDED" and result.task_id is None
          and result.sync_result[0] == reference and result.sync_result[1] == "image/png"
          and result.request_id == "req-ark-fixed" and result.unknown is False
          and result.result_count == 1,
          {"request_id": result.request_id, "sync_bytes": len(result.sync_result[0])})
    body = result.to_dict()
    check("R52-U04", "网关 dict 视图：task_id=null + sync=true，字节不进 dict",
          body["task_id"] is None and body["sync"] is True and "sync_result" not in body, body)
    capabilities = provider.capabilities()
    check("R52-U05", "能力块：sync_tasks=true、async_tasks=false、test_double=false",
          capabilities["sync_tasks"] is True and capabilities["async_tasks"] is False
          and capabilities["test_double"] is False
          and capabilities["max_reference_images"] <= 3
          and capabilities["contract"] == "v2.4.1", capabilities)

    provider, _ = make_provider([{"status": 429, "body": {"error": {"code": "Throttling"}}}])
    failure = _call_failure(lambda: provider.submit(request), image_contract)
    check("R52-U06", "429 → provider_failed / UPSTREAM_RATE_LIMITED / retryable",
          failure and failure.code == "UPSTREAM_RATE_LIMITED"
          and failure.family == "provider_failed" and failure.retry_policy == "retryable"
          and failure.http_status == 429,
          {"code": failure.code if failure else None})

    provider, _ = make_provider([{
        "status": 400, "body": {"error": {"code": "Arrearage", "message": "欠费"}}}])
    failure = _call_failure(lambda: provider.submit(request), image_contract)
    check("R52-U07", "欠费 → UPSTREAM_ACCOUNT_ARREARS（provider_failed）",
          failure and failure.code == "UPSTREAM_ACCOUNT_ARREARS"
          and failure.family == "provider_failed",
          {"code": failure.code if failure else None})

    provider, _ = make_provider([{"status": 400,
                                  "body": {"error": {"code": "InvalidImageSize"}}}])
    failure = _call_failure(lambda: provider.submit(request), image_contract)
    check("R52-U08", "4xx 非欠费 → UPSTREAM_REJECTED / fatal",
          failure and failure.code == "UPSTREAM_REJECTED" and failure.retry_policy == "fatal",
          {"code": failure.code if failure else None})

    provider, _ = make_provider([{"status": 502, "body": {}}])
    failure = _call_failure(lambda: provider.submit(request), image_contract)
    check("R52-U09", "5xx → provider_unknown / requires_review（不自动重提）",
          failure and failure.family == "provider_unknown"
          and failure.codec if False else failure and failure.retry_policy == "requires_review",
          {"code": getattr(failure, "code", None)})

    import requests.exceptions as requests_exceptions

    def timeout_transport(method, url, **kwargs):
        raise requests_exceptions.ConnectTimeout("simulated")

    slow = VolcengineImageProvider(api_key="test-key", credential_source="test_double",
                                   transport=timeout_transport)
    failure = _call_failure(lambda: slow.submit(request), image_contract)
    check("R52-U10", "超时 → provider_unknown（结果无法确认，显式新建 action）",
          failure and failure.family == "provider_unknown"
          and failure.retry_policy == "requires_review",
          {"code": failure.code if failure else None})

    provider, _ = make_provider([{"status": 200, "body": {"data": []}}])
    failure = _call_failure(lambda: provider.submit(request), image_contract)
    check("R52-U11", "空数据 → provider_failed / UPSTREAM_EMPTY_RESULT",
          failure and failure.code == "UPSTREAM_EMPTY_RESULT"
          and failure.family == "provider_failed",
          {"code": failure.code if failure else None})

    provider, _ = make_provider([{
        "status": 200,
        "body": {"data": [{"b64_json": base64.b64encode(b"not-png-bytes").decode("ascii")}]},
    }])
    failure = _call_failure(lambda: provider.submit(request), image_contract)
    check("R52-U12", "非 PNG → RESULT_IMAGE_INVALID（不伪造媒体类型）",
          failure and failure.code == "RESULT_IMAGE_INVALID"
          and failure.family == "provider_failed",
          {"code": failure.code if failure else None})

    task_request = TaskRequest.model_validate({
        "task_id": "task-anything",
        "target": {"provider_id": "volcengine-ark", "model_id": VOLCENGINE_MODEL_ID,
                   "protocol": "v2.4.1", "capability_version": 3},
    })
    provider, _ = make_provider([{"status": 200, "body": success_body}])
    failure = _call_failure(lambda: provider.status(task_request), image_contract)
    check("R52-U13", "status → SYNC_TASK_ID_REQUIRED（拒绝按假 task 核对）",
          failure and failure.code == "SYNC_TASK_ID_REQUIRED"
          and failure.family == "provider_unknown",
          {"code": failure.code if failure else None})
    failure = _call_failure(lambda: provider.result(task_request), image_contract)
    check("R52-U14", "result → SYNC_TASK_ID_REQUIRED（拒绝按假 task 重取）",
          failure and failure.code == "SYNC_TASK_ID_REQUIRED"
          and failure.family == "provider_unknown",
          {"code": failure.code if failure else None})

    closed = VolcengineImageProvider(credential_source="none", transport=TransportRecorder([]))
    closed.api_key = ""
    failure = _call_failure(lambda: closed.submit(request), image_contract)
    check("R52-U15", "默认档关闭 → fail-closed PROVIDER_NOT_CONFIGURED（不外呼）",
          failure and failure.code == "PROVIDER_NOT_CONFIGURED" and failure.http_status == 503,
          {"code": failure.code if failure else None})

    blocked = VolcengineImageProvider(
        api_key="test-key", credential_source="test_double",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        allowed_hosts=("aliyuncs.com",), transport=TransportRecorder([]))
    failure = _call_failure(lambda: blocked.submit(request), image_contract)
    check("R52-U16", "出站白名单收窄 → OUTBOUND_POLICY_REJECTED（不外呼）",
          failure and failure.code == "OUTBOUND_POLICY_REJECTED" and failure.http_status == 503,
          {"code": failure.code if failure else None})

    provider, _ = make_provider([{"status": 200, "body": success_body}])
    provider.apply_credentials(api_key="user-byok-key")
    check("R52-U17", "BYOK：credential_source 变 byok 且密钥生效",
          provider.credential_source == "byok" and provider.api_key == "user-byok-key",
          {"source": provider.credential_source})

    registry_data = json.load(open(ROOT / "config/product-v2/providers.json",
                                   encoding="utf-8"))
    entry = next((item for item in registry_data["providers"] if item["id"] == "volcengine-ark"),
                 None)
    check("R52-U18", "注册表：volcengine-ark 同步协议 entry 完整",
          bool(entry) and entry.get("adapter") == "v2_volcengine_image"
          and entry.get("api_key_env") == "ARK_API_KEY"
          and (entry.get("capabilities") or {}).get("sync_tasks") is True
          and (entry.get("capabilities") or {}).get("test_double") is False,
          (entry or {}).get("capabilities"))
    built = v2_registry.create_image_provider(
        registry=registry_data,
        env={"AMZ_V2_IMAGE_PROVIDER": "volcengine-ark", "ARK_API_KEY": "k",
             "AMZ_V2_DEFAULT_TRIAL": "open"})
    check("R52-U19", "注册表装配（默认档 open）→ configured / source=default",
          built.configured and built.credential_source == "default"
          and built.provider_id == "volcengine-ark", {"source": built.credential_source})
    trial_closed = v2_registry.create_image_provider(
        registry=registry_data,
        env={"AMZ_V2_IMAGE_PROVIDER": "volcengine-ark", "ARK_API_KEY": "k",
             "AMZ_V2_DEFAULT_TRIAL": "closed"})
    check("R52-U20", "默认档 closed → fail-closed（source=none）",
          trial_closed.credential_source == "none" and not trial_closed.configured,
          {"source": trial_closed.credential_source})


def gateway_e2e_checks(check) -> None:
    from src.providers.v2_fake_semantic import FakeSemanticProvider
    from src.providers.v2_image import IMAGES_CAPABILITY_VERSION
    from src.providers.v2_volcengine_image import VOLCENGINE_MODEL_ID, VolcengineImageProvider

    reference = png_bytes(16, 16, (10, 20, 30))
    expression = base64.b64encode(reference).decode("ascii")
    transport = TransportRecorder()
    transport.script_success(reference, request_id="req-ark-gateway")

    def image_factory():
        return VolcengineImageProvider(api_key="test-double-key",
                                       credential_source="test_double", transport=transport)

    module = load_server_module()
    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=image_factory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        status, caps = get_json(base, "/api/v2/capabilities")
        provider_block = caps.get("images", {}).get("provider", {})
        check("R52-G01", "capabilities 暴露火山目标与能力版本 3",
              status == 200 and provider_block.get("provider_id") == "volcengine-ark"
              and provider_block.get("model_id") == "doubao-seedream-5-0-flash-260915"
              and provider_block.get("capability_version") == IMAGES_CAPABILITY_VERSION,
              {"provider": provider_block})
        check("R52-G02", "能力块 sync_tasks 标志出现在 provider capabilities",
              (provider_block.get("capabilities") or {}).get("sync_tasks") is True,
              provider_block.get("capabilities"))

        submit_payload = {
            "action_id": "act-11111111-2222-3333-4444-555555555555",
            "prompt": "主图，产品居中。",
            "references": [{"role": "primary", "media_type": "image/png",
                            "sha256": hashlib.sha256(reference).hexdigest(),
                            "data_base64": expression}],
            "size": "1344*1344",
            "target": {"provider_id": "volcengine-ark", "model_id": VOLCENGINE_MODEL_ID,
                       "protocol": "v2.4.1", "capability_version": IMAGES_CAPABILITY_VERSION},
        }
        status, payload = post_json(base, "/api/v2/images/submit", submit_payload)
        task = payload.get("task") or {}
        digest = hashlib.sha256(reference).hexdigest()
        returned = base64.b64decode(payload.get("image_base64") or "")
        check("R52-G03", "提交 200；信封 task_id=null + sync=true + 媒体类型正确",
              status == 200 and task.get("task_id") is None and task.get("sync") is True
              and payload.get("image_media_type") == "image/png",
              {"task": task})
        check("R52-G04", "字节复核：image_base64 解码后 sha256 与 image_sha256 一致",
              returned == reference and payload.get("image_sha256") == digest,
              {"sha": payload.get("image_sha256")})
        check("R52-G05", "transport 恰好一次调用（同步协议没有后续 status/result 外呼）",
              len(transport.calls) == 1, {"calls": len(transport.calls)})

        bogus_status = {"task_id": "task-no-op",
                        "target": {"provider_id": "volcengine-ark",
                                   "model_id": VOLCENGINE_MODEL_ID,
                                   "protocol": "v2.4.1",
                                   "capability_version": IMAGES_CAPABILITY_VERSION}}
        status, payload2 = post_json(base, "/api/v2/images/status", bogus_status)
        check("R52-G06", "status 路由对同步协议 → provider_unknown / SYNC_TASK_ID_REQUIRED",
              status == 504
              and (payload2.get("error") or {}).get("code") == "SYNC_TASK_ID_REQUIRED"
              and len(transport.calls) == 1,
              {"status": status, "calls": len(transport.calls)})

        stale = submit_payload | {"target": {"provider_id": "volcengine-ark",
                                             "model_id": VOLCENGINE_MODEL_ID,
                                             "protocol": "v2.4.1", "capability_version": 2}}
        status, payload3 = post_json(base, "/api/v2/images/submit", stale)
        check("R52-G07", "能力版本漂移冻结身份：400 EXECUTION_IDENTITY_MISMATCH 且不转发",
              status == 400
              and (payload3.get("error") or {}).get("code") == "EXECUTION_IDENTITY_MISMATCH"
              and len(transport.calls) == 1,
              {"status": status, "calls": len(transport.calls)})

        invalid_target = submit_payload | {"target": {
            "provider_id": "volcengine-ark", "model_id": VOLCENGINE_MODEL_ID,
            "protocol": "http://bad", "capability_version": 3}}
        status4, payload4 = post_json(base, "/api/v2/images/submit", invalid_target)
        check("R52-G08", "非法协议 target → 400 input_rejected（不进入外呼）",
              status4 == 400 and payload4.get("ok") is False and len(transport.calls) == 1,
              {"status": status4})

        for case_id, changes in (
            ("R53-G01", {"size": "768*768"}),
            ("R53-G02", {"n": 2}),
            ("R53-G03", {"output_format": "jpeg"}),
        ):
            rejected_status, rejected = post_json(
                base, "/api/v2/images/submit", submit_payload | changes)
            check(case_id, "能力外请求提交前拒绝，供应商调用数不增加",
                  rejected_status == 400 and rejected.get("ok") is False
                  and (rejected.get("error") or {}).get("family") == "input_rejected"
                  and len(transport.calls) == 1,
                  {"parameters": changes, "status": rejected_status,
                   "calls": len(transport.calls)})
    finally:
        server.shutdown()
        server.server_close()


def compile_all(page, shot_ids: list) -> None:
    """按 shot 列表点每张图的编译按钮（V2.4.2 用的同一入口形状）。"""
    stage_nav.reveal(page, "#prompt-editor")
    for shot_id in shot_ids:
        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
        page.click(card + " .toolbar button")
    page.wait_for_timeout(400)


def browser_e2e_checks(check, screenshots: list[str], console_errors: list,
                       page_errors: list) -> None:
    from playwright.sync_api import expect, sync_playwright

    import v2_stage_nav as stage_nav
    from src.providers.v2_fake_semantic import FakeSemanticProvider
    from src.providers.v2_dashscope_image import DashScopeImageProvider
    from src.providers.v2_volcengine_image import (VOLCENGINE_MODEL_ID,
                                                   VolcengineImageProvider)

    reference = png_bytes(48, 48, (60, 120, 180))
    transport = TransportRecorder()
    module = load_server_module()
    port = free_port()

    mode = {"credential_source": "test_double", "provider": "volcengine"}
    def image_factory():
        if mode["provider"] == "dashscope":
            return DashScopeImageProvider(api_key="test-double-key",
                                          credential_source=mode["credential_source"],
                                          transport=transport)
        return VolcengineImageProvider(api_key="test-double-key",
                                       credential_source=mode["credential_source"],
                                       transport=transport)

    server = module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=image_factory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    temp_root = tempfile.mkdtemp(prefix="amz-r52-")
    profile = Path(temp_root) / "profile"
    reference_file = Path(temp_root) / "reference.png"
    reference_file.write_bytes(reference)

    def run_steps(page) -> None:
        transport.script_success(reference)

        page.goto(base + "/", wait_until="networkidle")
        page.fill("#new-project-name", "审计商品 · 同步任务流")
        page.click("#create-project")
        expect(page.locator("#project-view")).to_be_visible()
        stage_nav.goto(page, "intake")
        page.set_input_files("#ref-file", str(reference_file))
        expect(page.locator("#ref-list .ref-row")).to_have_count(1)
        page.fill("#intake-name", "便携保温杯")
        page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
        page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
        page.wait_for_timeout(1200)
        project_ids = page.evaluate(ID_PROJECTS_PROBE)
        project_id = project_ids[0]
        page.evaluate(SEED_SLOTS, project_id)
        page.reload(wait_until="networkidle")
        page.click("#suite-seed")
        expect(page.locator("#shot-list .shot-row")).to_have_count(4)
        stage_nav.goto(page, "generate")
        expect(page.locator("#prompt-editor")).to_be_visible()
        expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
        first_probe = page.evaluate(ID_DB_PROBE)
        shot_ids = first_probe["shot_ids"]
        compile_all(page, shot_ids)
        # 确认即提交：先备齐 4 次同步响应再点确认，确认后直接等 attempt 终态，不再点已删除的旧整套按钮。
        for _ in range(4):
            transport.script_success(reference)
        page.click("#confirm-action")
        for shot_id in shot_ids:
            page.wait_for_selector(
                f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]'
                '[data-attempt-state="succeeded"]', timeout=60_000)
        page.wait_for_timeout(1000)
        after = page.evaluate(ID_DB_PROBE)
        chains = after["attempt_chains"]
        check("R52-E01", "同步批次：恰好 4 次 transport 提交、0 次 status 外呼",
              len(transport.calls) == 4
              and all(call["url"].endswith("/images/generations")
                      for call in transport.calls),
              {"calls": [call["url"] for call in transport.calls]})
        latest_records = [chains[shot_id][-1]["payload"] for shot_id in shot_ids]
        check("R52-E02", "4 张图全部 succeeded 且 task_id=null、sync 身份冻结",
              len(latest_records) == 4
              and all(item["state"] == "succeeded" for item in latest_records)
              and all(item["task_id"] is None for item in latest_records)
              and all(item["execution_identity"]["sync"] is True for item in latest_records),
              [{"state": item["state"], "task_id": item["task_id"],
                "sync": item["execution_identity"]["sync"]} for item in latest_records])
        prompt_rows = after["prompts"]
        request_matches = []
        for shot_id, attempt, call in zip(shot_ids, latest_records, transport.calls):
            prompt = prompt_rows[shot_id]["payload"]
            snapshot = prompt["request_snapshot"]
            digest = hashlib.sha256(json.dumps(
                snapshot, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            external = call["json"]
            request_matches.append(
                prompt["compiled"]["provider"]["model_id"] == VOLCENGINE_MODEL_ID
                and snapshot["model"] == external["model"] == VOLCENGINE_MODEL_ID
                and snapshot["prompt"] == external["prompt"] == prompt["compiled"]["text"]
                and snapshot["size"].replace("*", "x") == external["size"]
                and snapshot["output_format"] == external["output_format"] == "png"
                and snapshot["watermark"] == external["watermark"] is False
                and digest == prompt["hash"] == attempt["prompt"]["hash"]
                and snapshot["target"]["provider_id"] == attempt["provider"]["provider_id"]
                and snapshot["target"]["capability_version"]
                    == attempt["execution_identity"]["capability_version"]
                and snapshot["references"] == attempt["references"]
                and hashlib.sha256(base64.b64decode(
                    external["image"][0].split(",", 1)[1])).hexdigest()
                    == snapshot["references"][0]["sha256"])
        check("R53-E01", "实际火山请求与 Prompt、hash、参考图和冻结执行身份一致（非 qwen 编译冒充）",
              all(request_matches), {"matches_by_shot": dict(zip(shot_ids, request_matches))})
        candidate_rows = after["candidates"]
        asset_shas = {row["sha256"] for row in after["assets"]}
        check("R52-E03", "每张图候选入库；asset sha256 与 transport 字节一致",
              all(len(candidate_rows.get(shot_id, [])) >= 1 for shot_id in shot_ids)
              and hashlib.sha256(reference).hexdigest() in asset_shas,
              {"candidates": {key: len(value) for key, value in candidate_rows.items()},
               "asset_shas": len(asset_shas)})
        check("R52-E04", "UI 行显示候选已保存（真实字节预览口径）",
              all(row["candidate_text"] and "候选已保存到本地" in row["candidate_text"]
                  for row in after["ui_rows"]),
              after["ui_rows"])
        first_actions = {record["action_id"] for record in latest_records}
        target_shot = shot_ids[1]
        target_index = shot_ids.index(target_shot)
        first_action = latest_records[target_index]["action_id"]
        screenshot_path = str(EVIDENCE_DIR / f"PRODUCT-V2-R5.2-batch-{stamp()}.png")
        page.screenshot(path=screenshot_path)
        screenshots.append(screenshot_path)

        # 刷新：字节面为空了，IndexedDB 仍是权威；记录与候选仍然可见。
        page.reload(wait_until="networkidle")
        stage_nav.goto(page, "generate")
        page.wait_for_selector("#attempt-list .attempt-row", timeout=30_000)
        refreshed = page.evaluate(ID_DB_PROBE)
        check("R52-E05", "刷新后：4 条 succeeded 记录 + 候选仍在（IndexedDB 权威）",
              len(refreshed["attempt_chains"]) == 4
              and all(refreshed["attempt_chains"][shot_id]
                      and refreshed["attempt_chains"][shot_id][-1]["payload"]["state"]
                      == "succeeded" for shot_id in shot_ids)
              and all(len(refreshed["candidates"].get(shot_id, [])) >= 1
                      for shot_id in shot_ids),
              {"candidates": {key: len(value) for key, value in refreshed["candidates"].items()}})

        # 显式新建 action：同步协议再成功一次（新的第五次 transport 提交）。
        transport.script_success(reference, request_id="req-ark-second")
        row_selector = f'#attempt-list .attempt-row[data-shot-id="{target_shot}"]'
        page.click(row_selector + ' button:has-text("再生成一张")')
        shared.confirm_and_submit(page, expect, shot_ids=[target_shot])
        page.wait_for_selector(row_selector + '[data-attempt-state="succeeded"]',
                               timeout=40_000)
        page.wait_for_timeout(1200)
        after_second = page.evaluate(ID_DB_PROBE)
        second_record = after_second["attempt_chains"][target_shot][-1]["payload"]
        check("R52-E06", "显式新建 action：又走同步协议成功（task_id=null）",
              second_record["action_id"] != first_action
              and second_record["state"] == "succeeded"
              and second_record["task_id"] is None
              and len(transport.calls) == 5,
              {"action": second_record["action_id"], "calls": len(transport.calls)})

        # fresh generation module（等价于刷新后的内存面）：succeeded sync 记录没候选、
        # 没有待取字节 → 明确失败并给补救，绝不静默轮询、不假成功。
        recovery = page.evaluate(BYTES_MISSING_PROBE, {"projectId": project_id})
        check("R52-E07", "fresh module 缺字节 → sync_bytes_missing（显式补救，不假成功）",
              recovery.get("failed") is True
              and recovery.get("reason") == "sync_bytes_missing"
              and "同步结果是一次性字节" in (recovery.get("message") or ""),
              recovery)
        screenshot_path = str(EVIDENCE_DIR / f"PRODUCT-V2-R5.2-refresh-{stamp()}.png")
        page.screenshot(path=screenshot_path)
        screenshots.append(screenshot_path)
        # 收尾：确认没有额外外呼（与 E01/E06 的 4+1 对齐）。
        check("R52-E08", "结束后 transport 总调用数恰为 5（4 批次 + 1 显式新建）",
              len(transport.calls) == 5, {"calls": len(transport.calls)})

        # 纯凭据来源轮换：请求相关 profile 不变，既有 Prompt/确认不应过期。
        prompts_before_rotation = after_second["prompts"]
        mode["credential_source"] = "env"
        page.reload(wait_until="networkidle")
        stage_nav.goto(page, "generate")
        expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
        rotated = page.evaluate(ID_DB_PROBE)
        check("R53-E02", "纯凭据轮换保留 Prompt/确认且零新增外呼",
              rotated["prompts"] == prompts_before_rotation
              and page.locator('#prompt-list [data-prompt-state="stale"]').count() == 0
              and len(transport.calls) == 5,
              {"stale_count": page.locator('#prompt-list [data-prompt-state="stale"]').count(),
               "calls": len(transport.calls)})

        # 正式协议切到另一模型：同能力版本也须精确失效，不暗改旧 Prompt/候选。
        mode["provider"] = "dashscope"
        page.reload(wait_until="networkidle")
        stage_nav.goto(page, "generate")
        expect(page.locator('#prompt-list [data-prompt-state="stale"]')).to_have_count(4)
        expect(page.locator("#confirm-action")).to_be_disabled()
        changed = page.evaluate(ID_DB_PROBE)
        check("R53-E03", "模型/协议目标改变使全部旧 Prompt 过期，历史保留且未调用新模型",
              changed["prompts"] == prompts_before_rotation
              and changed["attempt_chains"] == rotated["attempt_chains"]
              and changed["candidates"] == rotated["candidates"]
              and len(transport.calls) == 5,
              {"stale_count": page.locator('#prompt-list [data-prompt-state="stale"]').count(),
               "calls": len(transport.calls)})

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1440, "height": 1000})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                run_steps(page)
            finally:
                context.close()
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.R5.2 两 Adapter 离线证据")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    run_stamp = stamp()
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []

    def check(check_id: str, title: str, okvalue: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(okvalue), "detail": detail})

    node_result = run_node_checks()
    check("R52-00", "domain / generation / workspace / harness node --check 全过",
          node_result["ok"],
          {"failed": [item for item in node_result["files"] if item["rc"] != 0][:3]})

    node_tests = run_node_domain_tests()
    check("R52-01",
          "node --test 镜像域套件全部通过（不豁免既有失败）",
          node_tests["rc"] == 0,
          node_tests)

    adapter_unit_checks(check)
    gateway_e2e_checks(check)

    static_server, static_url = start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["attempt"] = read_suite(
                    browser, static_url + "/harness/attempt-contract.html",
                    "__V2_ATTEMPT_RESULTS__", console_errors, page_errors)
                for name, page_name, variable in REGRESSION_SUITES:
                    suites[name] = read_suite(
                        browser, static_url + "/harness/" + page_name, variable,
                        console_errors, page_errors)
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    suite = suites["attempt"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("R52-02", "A01–A19 契约套件全过（含 A19 同步协议合同）",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")}
                      for item in failed_cases[:3]]})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "attempt"}
    check("R52-03", "既有契约套件回归：确认单 / Prompt 编辑 / 套图编辑器全过",
          all(item["status"] == "passed" and not item["failed"]
              for item in regression.values()),
          regression)

    browser_e2e_checks(check, screenshots, console_errors, page_errors)

    entry = run_entry(["--check"])
    check("R52-98", "正式入口 --check 全过", entry["rc"] == 0, entry)
    clean = not console_errors and not page_errors
    check("R52-99", "零 console error / page error", clean,
          {"console": console_errors[:5], "pages": page_errors[:5]})

    failed = [item for item in checks if not item["ok"]]
    report = {
        "control": "NOT-AUTHORITY",
        "stamp": run_stamp, "label": args.label,
        "status": "passed" if not failed else "failed",
        "failed_ids": [item["id"] for item in failed],
        "checks": checks, "screenshots": screenshots,
        "network": "offline-transport-only; 0 real model calls",
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE_DIR / f"PRODUCT-V2-R5.2-offline-e2e-{run_stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "failed_ids": report["failed_ids"],
                      "report": str(out)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
