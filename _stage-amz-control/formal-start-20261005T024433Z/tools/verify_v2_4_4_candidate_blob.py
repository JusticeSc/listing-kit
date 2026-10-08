#!/usr/bin/env python
"""V2.4.4 证据：候选字节流、Blob 持久化与容量管理（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 通过 node --check（ESM 语法门）。
  2) C01..C10 契约套件在真实 Chromium 全过；既有契约套件回归全过。
  3) 单张生成到成功时自动取回字节：候选记录绑定来源 action/task；asset 里同 sha 的
     Blob 存在；界面出现预览与 sha256/尺寸元信息。
  4) Blob hash：IndexedDB 字节重算 sha256 == 候选记录 == 响应头 X-Image-Sha256；
     媒体信息（64×64 PNG、字节数）与字节本身一致。
  5) 刷新预览：刷新后候选不重复、不重新下载，预览从 IndexedDB 恢复（naturalWidth>0）。
  6) 取回失败一次：候选未保存、错误可见、不产生半份记录；重试后成功且 sha 稳定。
  7) 配额异常：asset 写入 QUOTA_EXCEEDED 时没有半份记录，界面给可恢复指引；
     清出空间（解除注入）后重试成功。
  8) 整套批次：剩余图片自动保存候选，进度含「已成功 4」且无「待保存候选」残留。
  9) 零意外 console error / page error；截图落盘；正式入口 --check 全过。

运行：
  uv run --locked python tools/verify_v2_4_4_candidate_blob.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402  （V2.UI.2 六阶段工作台导航）

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
    "app/product_v2/domain/shared.js",
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
    "app/product_v2/domain/batch.js",
    "app/product_v2/domain/candidate.js",
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/candidate-contract.js",
]

EXPECTED_CASES = [f"C{index:02d}" for index in range(1, 11)]
NEGATIVE_CASES = ["C02", "C04", "C10"]
REGRESSION_SUITES = (
    ("attempt", "attempt-contract.html", "__V2_ATTEMPT_RESULTS__"),
    ("batch", "batch-contract.html", "__V2_BATCH_RESULTS__"),
    ("confirm", "confirm-contract.html", "__V2_CONFIRM_RESULTS__"),
    ("prompt_edit", "prompt-edit-contract.html", "__V2_PROMPT_EDIT_RESULTS__"),
    ("suite_editor", "suite-editor-contract.html", "__V2_SUITE_EDITOR_RESULTS__"),
)


def png_bytes(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
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


def run_entry(args: list[str], timeout: int = 180) -> dict:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "app" / "server.py"), *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )
    return {"args": args, "rc": completed.returncode,
            "tail": (completed.stdout + completed.stderr).strip().splitlines()[-10:]}


def run_node_checks() -> dict:
    results = []
    for relative in DOMAIN_FILES:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)],
                                   cwd=str(ROOT), capture_output=True, text=True, check=False)
        results.append({"file": relative, "rc": completed.returncode,
                        "stderr": completed.stderr.strip()[-200:]})
    return {"files": results, "ok": all(item["rc"] == 0 for item in results)}


class HarnessHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        return

    def _send(self, payload: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path.startswith("/harness/"):
            candidate = (HARNESS_DIR / path[len("/harness/"):]).resolve()
            if str(candidate).startswith(str(HARNESS_DIR.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(),
                           MIME.get(candidate.suffix, "application/octet-stream"))
                return
        else:
            candidate = (PRODUCT_DIR / path.lstrip("/")).resolve()
            if str(candidate).startswith(str(PRODUCT_DIR.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(),
                           MIME.get(candidate.suffix, "application/octet-stream"))
                return
        self.send_error(404)


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
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function(
            f"() => window.{variable} && ['passed','failed','crashed'].includes(window.{variable}.status)",
            timeout=90_000,
        )
        return page.evaluate(f"() => window.{variable}")
    finally:
        page.close()


def compile_all(page, shot_ids: list, wait_ms: int = 200) -> None:
    for shot_id in shot_ids:
        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
        page.click(card + " .toolbar button")
        page.wait_for_selector(card + '[data-prompt-state="saved"]', timeout=15_000)
        page.wait_for_timeout(wait_ms)


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
        evidence: [{ kind: "user", ref: "v244-seed" }], depends_on: [],
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

PROBE = """
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
  const projects = await read("projects");
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
  for (const key of Object.keys(candidates)) {
    candidates[key].sort((left, right) => left.version - right.version);
  }
  const plans = documents.filter((item) => item.kind === "suite_plan")
    .sort((left, right) => left.version - right.version);
  const plan = plans.length ? plans[plans.length - 1] : null;
  const rows = [...document.querySelectorAll("#attempt-list .attempt-row")].map((node) => {
    const img = node.querySelector(".attempt-preview img");
    const candidateMeta = node.querySelector(".attempt-candidate");
    return {
      shot_id: node.getAttribute("data-shot-id"),
      state: node.getAttribute("data-attempt-state"),
      badges: [...node.querySelectorAll(".badge")].map((item) => item.textContent),
      meta: [...node.querySelectorAll("p.meta")].map((item) => item.textContent).join(" | "),
      candidate_meta: candidateMeta ? candidateMeta.textContent : null,
      preview: img ? {
        src: img.getAttribute("src") || "",
        complete: img.complete,
        natural_width: img.naturalWidth,
      } : null,
      buttons: [...node.querySelectorAll("button")].map((item) =>
        ({ text: item.textContent, disabled: item.disabled })),
    };
  });
  const buttonInfo = (id) => {
    const node = document.getElementById(id);
    if (!node) return null;
    return { text: node.textContent, disabled: node.disabled, hidden: node.hidden };
  };
  const errorNode = document.getElementById("attempt-error");
  const progressNode = document.getElementById("batch-progress");
  const hintNode = document.getElementById("batch-hint");
  return {
    project_ids: projects.map((item) => item.project_id),
    shot_ids: plan ? plan.payload.shots.map((shot) => shot.shot_id) : [],
    attempt_chains: chains,
    candidate_chains: candidates,
    asset_rows: assets.map((item) => ({
      sha256: item.sha256, media_type: item.media_type, byte_size: item.byte_size,
      width: item.width, height: item.height, role: item.role,
      has_blob: item.blob instanceof Blob,
    })),
    ui: {
      error: errorNode ? errorNode.textContent : "",
      error_hidden: errorNode ? errorNode.hidden : true,
      rows: rows,
      batch: {
        progress: progressNode ? progressNode.textContent : "",
        hint: hintNode ? hintNode.textContent : "",
        run: buttonInfo("batch-run"),
      },
    },
  };
}
"""

HASH_ASSET = """
async ({ sha256 }) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const rows = await new Promise((resolve, reject) => {
    const request = db.transaction("assets", "readonly").objectStore("assets").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const record = rows.find((item) => item.sha256 === sha256);
  if (!record || !(record.blob instanceof Blob)) return { found: false };
  const buffer = await record.blob.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  const hex = Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return {
    found: true, sha256: hex, byte_size: buffer.byteLength,
    media_type: record.media_type, width: record.width, height: record.height,
    role: record.role,
  };
}
"""

# 配额故障注入：只拦 assets 仓的 add，把 DOMException 伪装成浏览器配额耗尽。
# 产品代码不需要任何测试钩子——故障发生在 IndexedDB 协议层，走真实错误转译路径。
INSTALL_IDB_FAULT = """
() => {
  if (window.__v244Patched) return true;
  const original = IDBObjectStore.prototype.add;
  IDBObjectStore.prototype.add = function (...args) {
    if (window.__v244FailAssetWrites && this.name === "assets") {
      throw new DOMException("simulated quota", "QuotaExceededError");
    }
    return original.apply(this, args);
  };
  window.__v244Patched = true;
  return true;
}
"""

SET_IDB_FAULT = """
(fail) => {
  window.__v244FailAssetWrites = Boolean(fail);
  return window.__v244FailAssetWrites;
}
"""

MARK_FETCH_FAIL = "MARK-FETCH-FAIL-V244"


def save_edit(page, shot_id: str, text: str, reason: str, wait_ms: int = 600) -> None:
    card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
    page.fill(card + " textarea.prompt-edit-text", text)
    page.fill(card + " input.prompt-edit-reason", reason)
    page.click(card + " .prompt-edit-block button")
    page.wait_for_timeout(wait_ms)


def append_prompt_mark(page, shot_id: str, mark: str, reason: str) -> None:
    card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
    current = page.input_value(card + " textarea.prompt-edit-text")
    save_edit(page, shot_id, current + "\n\n" + mark + "：这张图的取回场景由验证器决定。", reason)


def chain_of(data: dict, shot_id: str) -> list:
    return data["attempt_chains"].get(shot_id, [])


def candidate_of(data: dict, shot_id: str) -> list:
    return data["candidate_chains"].get(shot_id, [])


def row_of(data: dict, shot_id: str) -> dict | None:
    return next((row for row in data["ui"]["rows"] if row["shot_id"] == shot_id), None)


def chain_json(data: dict, shot_id: str) -> str:
    return json.dumps(chain_of(data, shot_id), ensure_ascii=False, sort_keys=True)


def candidate_json(data: dict, shot_id: str) -> str:
    return json.dumps(candidate_of(data, shot_id), ensure_ascii=False, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="V2.4.4 候选字节流、Blob 持久化与容量管理验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    node_result = run_node_checks()
    check("V2.4.4-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"],
          {"failed": [item for item in node_result["files"] if item["rc"] != 0][:3]})

    static_server, static_url = start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["candidate"] = read_suite(
                    browser, static_url + "/harness/candidate-contract.html",
                    "__V2_CANDIDATE_RESULTS__", console_errors, page_errors)
                for name, page_name, variable in REGRESSION_SUITES:
                    suites[name] = read_suite(
                        browser, static_url + "/harness/" + page_name, variable,
                        console_errors, page_errors)
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    suite = suites["candidate"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.4.4-01", "C01–C10 契约套件全过且用例齐全",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")} for item in failed_cases[:3]]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.4.4-02", "反向探针确实执行（坏 PNG / 非法身份 / 兼容性参数）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "candidate"}
    check("V2.4.4-02b", "既有契约套件回归：Attempt / 批次 / 确认单 / Prompt 编辑 / 套图编辑器全过",
          all(item["status"] == "passed" and not item["failed"] for item in regression.values()),
          regression)

    module = load_server_module()
    from src.providers.v2_fake_image import FakeImageProvider  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415
    from src.providers.v2_image import ImageFailure, ImageTaskResult  # noqa: PLC0415

    mode: dict = {"tasks": {}, "failed_once": set()}

    class MarkerImageProvider(FakeImageProvider):
        """按 Prompt 标记决定这张图的取回场景；替身保持无状态：场景表放在验证器里。"""

        def submit(self, request):
            self.calls["submit"] += 1
            prompt = request.prompt or ""
            task_id = FakeImageProvider.task_id_for(request.action_id)
            if MARK_FETCH_FAIL in prompt:
                mode["tasks"][task_id] = "fetch_fail_once"
            return ImageTaskResult(
                provider_id=self.provider_id, model_id=self.model_id,
                task_id=task_id, status="RUNNING")

        def result(self, request):
            self.calls["result"] += 1
            if (mode["tasks"].get(request.task_id) == "fetch_fail_once"
                    and request.task_id not in mode["failed_once"]):
                mode["failed_once"].add(request.task_id)
                raise ImageFailure(
                    "provider_failed", "RESULT_DOWNLOAD_FAILED",
                    "结果图片下载失败；没有产生可用的候选字节。",
                    retry_policy="retryable")
            return FakeImageProvider.result(self, request)

    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: MarkerImageProvider(scenario="ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    submit_requests: list[dict] = []
    status_requests: list[str] = []
    result_requests: list[dict] = []
    ui: dict = {}
    stage = "setup"
    interrupted: str | None = None
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v244-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))

                def payload_of(request) -> dict:
                    try:
                        return json.loads(request.post_data or "{}")
                    except ValueError:
                        return {}

                def on_request(request) -> None:
                    if request.method != "POST":
                        return
                    if "/api/v2/images/submit" in request.url:
                        body = payload_of(request)
                        submit_requests.append({
                            "action_id": body.get("action_id"),
                            "prompt": body.get("prompt"),
                            "size": body.get("size"),
                        })
                    elif "/api/v2/images/status" in request.url:
                        status_requests.append(str(payload_of(request).get("task_id")))
                    elif "/api/v2/images/result" in request.url:
                        result_requests.append({
                            "task_id": str(payload_of(request).get("task_id")),
                            "status": None, "declared_sha": "",
                        })

                def on_response(response) -> None:
                    if "/api/v2/images/result" not in response.url:
                        return
                    task_id = str(payload_of(response.request).get("task_id"))
                    for item in reversed(result_requests):
                        if item["task_id"] == task_id and item["status"] is None:
                            item["status"] = response.status
                            item["declared_sha"] = str(
                                response.headers.get("x-image-sha256") or "").lower()
                            break

                page.on("request", on_request)
                page.on("response", on_response)

                def probe() -> dict:
                    return page.evaluate(PROBE)

                def row(shot_id: str):
                    return page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 30_000) -> None:
                    expect(row(shot_id)).to_have_attribute(
                        "data-attempt-state", state, timeout=timeout)

                def wait_states(expectations: dict, timeout: int = 90_000) -> None:
                    page.wait_for_function(
                        """(wanted) => {
                            const rows = [...document.querySelectorAll('#attempt-list .attempt-row')];
                            return Object.entries(wanted).every(([id, state]) => {
                                const node = rows.find((item) =>
                                    item.getAttribute('data-shot-id') === id);
                                return node && node.getAttribute('data-attempt-state') === state;
                            });
                        }""",
                        arg=expectations, timeout=timeout)

                def wait_preview(shot_id: str, timeout: int = 30_000) -> None:
                    # 预览图带 loading="lazy"：先滚动到这一行（用户也会这样做），
                    # 否则刷新后页面停在顶部，图片永远不进入加载队列。
                    page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]'
                        " .attempt-preview img"
                    ).scroll_into_view_if_needed(timeout=timeout)
                    page.wait_for_function(
                        """(shot) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                            const img = node && node.querySelector('.attempt-preview img');
                            return Boolean(img && img.complete && img.naturalWidth > 0);
                        }""",
                        arg=shot_id, timeout=timeout)

                def wait_candidate_ui(shot_id: str, timeout: int = 30_000) -> None:
                    # 只等界面上的候选标记（同步谓词）；字节与身份仍由 probe 重新读 IndexedDB 核对。
                    # 注意：wait_for_function 不会等待 async 谓词（Promise 恒为真值），这里必须同步。
                    page.wait_for_function(
                        """(shot) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                            return Boolean(node && node.querySelector('.attempt-candidate'));
                        }""", arg=shot_id, timeout=timeout)

                def wait_error_contains(text: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(wanted) => {
                            const node = document.getElementById('attempt-error');
                            return Boolean(node && !node.hidden
                                && node.textContent.includes(wanted));
                        }""", arg=text, timeout=timeout)

                def confirm_generation() -> None:
                    expect(page.locator("#confirm-action")).to_be_enabled()
                    page.click("#confirm-action")
                    expect(page.locator("#confirm-record")).to_contain_text("已确认 v")

                def click_row_button(shot_id: str, text: str) -> None:
                    row(shot_id).locator(f'button:has-text("{text}")').first.click()

                def submits_for(action_id: str) -> int:
                    return len([item for item in submit_requests
                                if item["action_id"] == action_id])

                def results_for(task_id: str) -> list:
                    return [item for item in result_requests
                            if item["task_id"] == task_id]

                def generate_and_settle(shot_id: str) -> None:
                    click_row_button(shot_id, "生成这张图")
                    wait_state(shot_id, "submitted")
                    click_row_button(shot_id, "核对任务")
                    wait_state(shot_id, "succeeded")

                # ---------------- 项目准备：空白项目 → 参考图 → 资料 → 槽位 → 套图 → 确认 ----------------
                stage = "prep"
                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · 候选字节")
                page.click("#create-project")
                expect(page.locator("#project-view")).to_be_visible()
                page.set_input_files("#ref-file", str(reference))
                expect(page.locator("#ref-list .ref-row")).to_have_count(1)
                page.fill("#intake-name", "便携保温杯")
                page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
                page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
                page.wait_for_timeout(1200)
                project_ids = page.evaluate(
                    "async () => { const db = await new Promise((resolve) => {"
                    " const request = indexedDB.open(\"amz-listing-kit-v2\");"
                    " request.onsuccess = () => resolve(request.result); });"
                    " const rows = await new Promise((resolve) => { const req ="
                    " db.transaction(\"projects\", \"readonly\").objectStore(\"projects\").getAll();"
                    " req.onsuccess = () => resolve(req.result); });"
                    " db.close(); return rows.map((item) => item.project_id); }")
                page.evaluate(SEED_SLOTS, project_ids[0])
                page.reload(wait_until="networkidle")
                page.click("#suite-seed")
                expect(page.locator("#shot-list .shot-row")).to_have_count(4)
                stage_nav.goto(page, "generate")
                expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
                initial = probe()
                shot_ids = initial["shot_ids"]
                compile_all(page, shot_ids)
                ok_shot, fail_shot, quota_shot, batch_shot = shot_ids
                append_prompt_mark(page, fail_shot, MARK_FETCH_FAIL, "验证取回失败一次")
                confirm_generation()
                ready = probe()
                ui["base_shots"] = shot_ids
                check("V2.4.4-03",
                      "就绪：4 张待提交、整套生成按钮可见、候选栏为空且只有参考图字节",
                      len(ready["ui"]["rows"]) == 4
                      and all(item["state"] == "none" for item in ready["ui"]["rows"])
                      and all(item["preview"] is None for item in ready["ui"]["rows"])
                      and "整套生成（4 张）" in (ready["ui"]["batch"]["run"] or {}).get("text", "")
                      and len(ready["asset_rows"]) == 1
                      and ready["candidate_chains"] == {},
                      {"run": (ready["ui"]["batch"]["run"] or {}).get("text"),
                       "assets": len(ready["asset_rows"])})

                # ---------------- 单张成功：候选自动入库，三方 sha256 一致 ----------------
                stage = "check04-single"
                generate_and_settle(ok_shot)
                wait_preview(ok_shot)
                single = probe()
                att4_chain = chain_of(single, ok_shot)
                att4 = att4_chain[-1]["payload"] if att4_chain else {}
                cand4 = candidate_of(single, ok_shot)
                rec4 = cand4[-1]["payload"] if cand4 else {}
                asset4 = next((item for item in single["asset_rows"]
                               if item["sha256"] == rec4.get("asset_sha256")), None)
                hashed4 = (page.evaluate(HASH_ASSET, {"sha256": rec4.get("asset_sha256")})
                           if rec4.get("asset_sha256") else {"found": False})
                resolved4 = results_for(att4.get("task_id") or "")
                declared4 = next((item["declared_sha"] for item in resolved4
                                  if item["status"] == 200 and item["declared_sha"]), "")
                row4 = row_of(single, ok_shot) or {}
                preview4 = row4.get("preview") or {}
                meta4 = row4.get("candidate_meta") or ""
                check("V2.4.4-04",
                      "单张成功：候选自动入库；记录 sha = 重算 sha = 响应头 sha；64×64 预览可见",
                      len(cand4) == 1
                      and rec4.get("action_id") == att4["action_id"]
                      and rec4.get("task_id") == att4["task_id"]
                      and rec4.get("media_type") == "image/png"
                      and rec4.get("width") == 64 and rec4.get("height") == 64
                      and bool(asset4) and asset4["has_blob"] and asset4["role"] == "candidate"
                      and hashed4.get("found") is True
                      and hashed4.get("sha256") == rec4.get("asset_sha256")
                      and hashed4.get("byte_size") == rec4.get("byte_size")
                      and declared4 == rec4.get("asset_sha256")
                      and preview4.get("natural_width", 0) > 0
                      and "候选已保存到本地" in meta4
                      and len(resolved4) == 1,
                      {"chain": len(cand4), "declared": declared4[:12],
                       "recomputed": str(hashed4.get("sha256"))[:12],
                       "record": str(rec4.get("asset_sha256"))[:12],
                       "result_requests": len(resolved4)})

                # ---------------- 刷新：候选不重复、零新增取回请求、预览恢复 ----------------
                stage = "check05-reload"
                requests_before_reload = len(result_requests)
                before_reload = probe()
                page.reload(wait_until="networkidle")
                stage_nav.goto(page, "generate")
                wait_preview(ok_shot)
                after_reload = probe()
                check("V2.4.4-05",
                      "刷新恢复：候选记录与字节保留、不重复保存、零新增取回请求、预览仍可见",
                      candidate_json(after_reload, ok_shot) == candidate_json(before_reload, ok_shot)
                      and len(result_requests) == requests_before_reload
                      and len(after_reload["asset_rows"]) == len(before_reload["asset_rows"])
                      and ((row_of(after_reload, ok_shot) or {}).get("preview") or {})
                      .get("natural_width", 0) > 0,
                      {"result_requests_before": requests_before_reload,
                       "result_requests_after": len(result_requests)})

                # ---------------- 取回失败一次：无半份记录、可恢复、重试后 sha 一致 ----------------
                stage = "check06-fetch-fail"
                before6 = probe()
                assets6_before = len(before6["asset_rows"])
                generate_and_settle(fail_shot)
                wait_error_contains("RESULT_DOWNLOAD_FAILED")
                failed_try = probe()
                att6_chain = chain_of(failed_try, fail_shot)
                att6 = att6_chain[-1]["payload"] if att6_chain else {}
                err6 = failed_try["ui"]["error"]
                no_half6 = (candidate_of(failed_try, fail_shot) == []
                            and len(failed_try["asset_rows"]) == assets6_before)
                click_row_button(fail_shot, "保存候选图片")
                wait_candidate_ui(fail_shot)
                recovered6 = probe()
                rec6_chain = candidate_of(recovered6, fail_shot)
                rec6 = rec6_chain[-1]["payload"] if rec6_chain else {}
                hashed6 = (page.evaluate(HASH_ASSET, {"sha256": rec6["asset_sha256"]})
                           if rec6 else {"found": False})
                resolved6 = results_for(att6.get("task_id") or "")
                declared6 = next((item["declared_sha"] for item in resolved6
                                  if item["status"] == 200 and item["declared_sha"]), "")
                check("V2.4.4-06",
                      "取回失败一次：不产生半份记录、错误可恢复、重试成功且 sha 与响应头一致",
                      bool(att6) and bool(rec6)
                      and no_half6
                      and "取回候选失败" in err6 and "RESULT_DOWNLOAD_FAILED" in err6
                      and len(candidate_of(recovered6, fail_shot)) == 1
                      and rec6.get("action_id") == att6["action_id"]
                      and hashed6.get("found") is True
                      and hashed6.get("sha256") == rec6.get("asset_sha256")
                      and declared6 == rec6.get("asset_sha256")
                      and submits_for(att6["action_id"]) == 1
                      and [item["status"] for item in resolved6] == [502, 200],
                      {"error": err6[:120], "statuses": [item["status"] for item in resolved6],
                       "attempt_chain": len(att6_chain), "candidate_chain": len(rec6_chain),
                       "half_record": not no_half6, "rec6": bool(rec6)})

                # ---------------- 配额异常：无半份记录、指引可恢复、解除后保存成功 ----------------
                stage = "check07-quota"
                before7 = probe()
                assets7_before = len(before7["asset_rows"])
                page.evaluate(INSTALL_IDB_FAULT)
                page.evaluate(SET_IDB_FAULT, True)
                generate_and_settle(quota_shot)
                wait_error_contains("浏览器存储空间不足")
                quota_failed = probe()
                quota_no_half = (candidate_of(quota_failed, quota_shot) == []
                                 and len(quota_failed["asset_rows"]) == assets7_before)
                page.evaluate(SET_IDB_FAULT, False)
                click_row_button(quota_shot, "保存候选图片")
                wait_candidate_ui(quota_shot)
                quota_ok = probe()
                rec7_chain = candidate_of(quota_ok, quota_shot)
                rec7 = rec7_chain[-1]["payload"] if rec7_chain else {}
                hashed7 = (page.evaluate(HASH_ASSET, {"sha256": rec7["asset_sha256"]})
                           if rec7 else {"found": False})
                check("V2.4.4-07",
                      "配额异常：不留半份记录、错误给出可恢复指引；解除后同一 action 保存成功",
                      bool(rec7) and hashed7.get("found") is True
                      and quota_no_half
                      and "浏览器存储空间不足" in quota_failed["ui"]["error"]
                      and "重试" in quota_failed["ui"]["error"]
                      and len(candidate_of(quota_ok, quota_shot)) == 1
                      and hashed7.get("sha256") == rec7.get("asset_sha256"),
                      {"error": quota_failed["ui"]["error"][:120],
                       "candidate_chain": len(rec7_chain),
                       "half_record": not quota_no_half})

                # ---------------- 整套批次：只提交剩余图一次；全部成功且候选全部入库 ----------------
                stage = "check08-batch"
                submits_before8 = len(submit_requests)
                page.click("#batch-run")
                wait_states({shot: "succeeded" for shot in shot_ids})
                wait_candidate_ui(batch_shot)
                finished = probe()
                final_rows = finished["ui"]["rows"]
                all_stored = all(candidate_of(finished, shot) for shot in shot_ids)
                chains_ok = all(
                    bool(chain_of(finished, shot))
                    and chain_of(finished, shot)[-1]["payload"]["state"] == "succeeded"
                    and bool(candidate_of(finished, shot))
                    and candidate_of(finished, shot)[-1]["payload"]["action_id"]
                    == chain_of(finished, shot)[-1]["payload"]["action_id"]
                    for shot in shot_ids)
                captured8 = submit_requests[submits_before8:]
                attempt8_chain = chain_of(finished, batch_shot)
                attempt8 = attempt8_chain[-1]["payload"] if attempt8_chain else {}
                check("V2.4.4-08",
                      "整套批次：只提交剩余图一次；全部成功且候选全部入库；进度与提示一致",
                      len(captured8) == 1
                      and bool(attempt8)
                      and captured8[0]["action_id"] == attempt8.get("action_id")
                      and len(final_rows) == 4
                      and all(item["state"] == "succeeded" for item in final_rows)
                      and all_stored and chains_ok
                      and "已成功 4" in finished["ui"]["batch"]["progress"]
                      and "待保存候选" not in finished["ui"]["batch"]["progress"]
                      and "候选还没保存" not in finished["ui"]["batch"]["hint"]
                      and "已全部生成" in (finished["ui"]["batch"]["run"] or {}).get("text", ""),
                      {"captured": len(captured8),
                       "progress": finished["ui"]["batch"]["progress"],
                       "hint": finished["ui"]["batch"]["hint"]})
                ui["final"] = {
                    "attempt_states": {item["shot_id"]: item["state"] for item in final_rows},
                    "candidate_versions": {shot: len(candidate_of(finished, shot))
                                           for shot in shot_ids},
                    "result_requests": len(result_requests),
                    "submit_requests": len(submit_requests),
                }
                screenshot_rel = f"evals/product-v2/v2.4.4-candidate-blob-{stamp}.png"
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                screenshots.append(screenshot_rel)
            finally:
                context.close()
    except Exception as error:  # noqa: BLE001 - 中断也要留下证据文件
        interrupted = f"[{stage}] {type(error).__name__}: {error}"
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass

    if interrupted:
        check("V2.4.4-99", "浏览器闭环在完成前中断", False, interrupted)

    expected_noise = ("Failed to load resource: the server responded with a status of 504",
                      "Failed to load resource: the server responded with a status of 502",
                      "net::ERR_ABORTED")
    unexpected_console = [item for item in console_errors
                          if not any(noise in item for noise in expected_noise)]
    check("V2.4.4-09", "零意外 console error / page error（预期内的取回 502 与刷新中断除外）",
          not unexpected_console and not page_errors,
          {"console": console_errors[:6], "unexpected": unexpected_console,
           "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.4.4-10", "正式入口自检仍全过（V2.4.4 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明候选字节在真实浏览器与真实 IndexedDB 上是可持久、可校验、可恢复的：成功结论在同一步"
        "把结果字节存进内容寻址的 assets 仓，候选记录的 sha256 与重算值、服务端 X-Image-Sha256 "
        "响应头三方一致；刷新后预览来自本地字节、零新增取回请求且不重复保存；取回失败一次不产生"
        "半份记录、错误可恢复、重试成功；IndexedDB 配额异常在协议层注入（产品代码无测试钩子），"
        "失败不留半份记录并给出「清理后重试」指引；整套批次只提交剩余图一次、全部成功且候选全部"
        "入库，进度不再显示待保存候选。本批不做审核、单图返工与导出（Phase 5）；0 次真实模型调用、"
        "0 次外部网络；图像 provider 是注入的假替身（按 Prompt 标记决定取回场景），只证明候选"
        "持久化语义，不证明真实出图质量。"
    )
    report = {
        "task": "V2.4.4",
        "suite_id": "v2.4.4-candidate-blob",
        "status": status,
        "finished_at": finished_at,
        "model_calls": 0,
        "external_network_calls": 0,
        "checks": checks,
        "suites": suites,
        "ui_flow": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshots": screenshots,
        "boundary": boundary,
    }
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.4.4-candidate-blob-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.4.4-candidate-blob-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.4.4 候选字节流、Blob 持久化与容量管理",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 · external_network_calls: 0 (fake image provider + 本机服务)",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        mark = "PASS" if item["ok"] else "FAIL"
        lines.append(f"- [{mark}] {item['id']} {item['title']}")
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for line in lines:
        print(line)
    print("")
    print("证据文件：")
    print(" -", json_path.relative_to(ROOT).as_posix())
    print(" -", txt_path.relative_to(ROOT).as_posix())
    for shot in screenshots:
        print(" -", shot)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
