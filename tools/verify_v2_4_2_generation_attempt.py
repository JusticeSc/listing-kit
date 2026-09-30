#!/usr/bin/env python
"""V2.4.2 证据：浏览器 Attempt、action ID、task ID 与 Unknown 恢复（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 通过 node --check（ESM 语法门）。
  2) 契约套件 A01..A13 在真实 Chromium 全过（形状、信封→状态、迁移边、append-only、
     查询不回退、Unknown 恢复、防重复、过期标记、篡改反向探针、词表常量）。
  3) 既有契约回归：确认单 / Prompt 编辑 / 套图编辑器全过。
  4) 正式入口：套图 + 编译 + 确认后就绪，4 张图可提交，provider 身份可见。
  5) 提交前落库：服务端已收到提交时，IndexedDB 已是 pending_submit，Prompt 版本一致。
  6) 双击只产生一条 Attempt；提交请求仅一次；请求里的 Prompt / 引用 / 尺寸与记录一致。
  7) 核对推进 succeeded：迁移链完整、没有重新提交。
  8) 刷新恢复：succeeded 身份与 UI 一致。
  9) 服务端重启后按已保存 task id 核对成功（服务端无任务表）。
 10) Unknown 不自动重提；显式新建 action 保留旧记录。
 11) 刷新打断提交：pending 身份保留、不自动重提、旧记录原样。
 12) Prompt 前进后旧 Attempt 标「基于旧版本 v1」，记录零改写。
 13) 零 console error / page error；截图落盘；正式入口 --check 全过。

运行：
  uv run --locked python tools/verify_v2_4_2_generation_attempt.py
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
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
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/attempt-contract.js",
]

EXPECTED_CASES = [f"A{index:02d}" for index in range(1, 14)]
NEGATIVE_CASES = ["A02", "A04", "A06", "A08", "A09", "A10", "A11", "A12"]
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
        evidence: [{ kind: "user", ref: "v242-seed" }], depends_on: [],
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

ATTEMPT_PROBE = """
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
  const prompts = {};
  for (const item of documents) {
    if (item.kind !== "prompt_version") continue;
    const current = prompts[item.document_id];
    if (!current || item.version > current.version) {
      prompts[item.document_id] = {
        version: item.version,
        hash: item.payload.hash,
        text: item.payload.compiled ? item.payload.compiled.text : null,
      };
    }
  }
  const plans = documents.filter((item) => item.kind === "suite_plan")
    .sort((left, right) => left.version - right.version);
  const plan = plans.length ? plans[plans.length - 1] : null;
  const project = projects.slice().sort((left, right) =>
    String(right.updated_at || "").localeCompare(String(left.updated_at || "")))[0] || null;
  const rows = [...document.querySelectorAll("#attempt-list .attempt-row")].map((node) => ({
    shot_id: node.getAttribute("data-shot-id"),
    state: node.getAttribute("data-attempt-state"),
    badges: [...node.querySelectorAll(".badge")].map((item) => item.textContent),
    meta: [...node.querySelectorAll("p.meta")].map((item) => item.textContent).join(" | "),
    buttons: [...node.querySelectorAll("button")].map((item) =>
      ({ text: item.textContent, disabled: item.disabled })),
  }));
  const errorNode = document.getElementById("attempt-error");
  const statusNode = document.getElementById("attempt-status");
  const providerNode = document.getElementById("attempt-provider");
  const lockedNode = document.getElementById("attempt-locked");
  const editorNode = document.getElementById("attempt-editor");
  return {
    project_state: project ? project.state : null,
    shot_ids: plan ? plan.payload.shots.map((shot) => shot.shot_id) : [],
    attempt_chains: chains,
    prompts: prompts,
    ui: {
      provider: providerNode ? providerNode.textContent : "",
      status: statusNode ? statusNode.textContent : "",
      error: errorNode ? errorNode.textContent : "",
      error_hidden: errorNode ? errorNode.hidden : true,
      locked_hidden: lockedNode ? lockedNode.hidden : null,
      editor_hidden: editorNode ? editorNode.hidden : null,
      rows: rows,
    },
  };
}
"""


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
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"not found")


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


def save_edit(page, shot_id: str, text: str, reason: str, wait_ms: int = 600) -> None:
    card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
    page.fill(card + " textarea.prompt-edit-text", text)
    page.fill(card + " input.prompt-edit-reason", reason)
    page.click(card + " .prompt-edit-block button")
    page.wait_for_timeout(wait_ms)


def chain_of(data: dict, shot_id: str) -> list:
    return data["attempt_chains"].get(shot_id, [])


def action_ids(chain: list) -> list:
    return sorted({entry["payload"]["action_id"] for entry in chain})


def row_of(data: dict, shot_id: str) -> dict | None:
    return next((row for row in data["ui"]["rows"] if row["shot_id"] == shot_id), None)


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.4.2 生成 Attempt 验证")
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
    check("V2.4.2-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"],
          {"failed": [item for item in node_result["files"] if item["rc"] != 0][:3]})

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
    check("V2.4.2-01", "A01–A13 契约套件全过且用例齐全",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")} for item in failed_cases[:3]]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.4.2-02", "反向探针确实执行（非法输入 / 非法迁移 / 篡改 / 回退 / 无身份恢复）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "attempt"}
    check("V2.4.2-02b", "既有契约套件回归：确认单 / Prompt 编辑 / 套图编辑器全过",
          all(item["status"] == "passed" and not item["failed"] for item in regression.values()),
          regression)

    module = load_server_module()
    from src.providers.v2_fake_image import FakeImageProvider  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    class GatedFakeImageProvider(FakeImageProvider):
        """真替身上加一个「服务端已收到提交」门 + 可选延迟，供验证器观察提交前落库。"""

        def __init__(self, scenario: str, gate: threading.Event | None = None,
                     delay: float = 0.0) -> None:
            super().__init__(scenario)
            self._gate = gate
            self._delay = delay

        def submit(self, request):
            if self._gate is not None:
                self._gate.set()
            if self._delay > 0:
                time.sleep(self._delay)
            return super().submit(request)

    mode: dict = {"image_scenario": "ok", "gate": None, "delay": 0.0}

    def image_factory():
        return GatedFakeImageProvider(mode["image_scenario"],
                                      gate=mode.get("gate"), delay=mode.get("delay") or 0.0)

    def make_server():
        return module.create_product_v2_server(
            "127.0.0.1", port,
            provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
            image_provider_factory=image_factory)

    port = free_port()
    server = make_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    submit_requests: list[dict] = []
    status_requests: list[str] = []
    restart_events: list[dict] = []
    ui: dict = {}
    interrupted: str | None = None
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v242-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))

    def restart_server() -> None:
        nonlocal server
        server.shutdown()
        server.server_close()
        server = make_server()
        threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))

                def on_request(request) -> None:
                    if request.method != "POST":
                        return
                    if "/api/v2/images/submit" in request.url:
                        try:
                            body = json.loads(request.post_data or "{}")
                        except ValueError:
                            body = {}
                        submit_requests.append({
                            "action_id": body.get("action_id"),
                            "prompt": body.get("prompt"),
                            "size": body.get("size"),
                            "references": [{key: ref.get(key) for key in ("role", "sha256")}
                                           for ref in body.get("references", [])],
                        })
                    elif "/api/v2/images/status" in request.url:
                        try:
                            body = json.loads(request.post_data or "{}")
                        except ValueError:
                            body = {}
                        status_requests.append(str(body.get("task_id")))

                page.on("request", on_request)

                def probe() -> dict:
                    return page.evaluate(ATTEMPT_PROBE)

                def row(shot_id: str):
                    return page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 20_000) -> None:
                    expect(row(shot_id)).to_have_attribute(
                        "data-attempt-state", state, timeout=timeout)

                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · 生成执行")
                page.click("#create-project")
                page.click('#project-list .project-row button[data-action="open"]')
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
                expect(page.locator("#prompt-editor")).to_be_visible()
                expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
                initial = probe()
                shot_ids = initial["shot_ids"]
                compile_all(page, shot_ids)
                page.click("#confirm-action")
                expect(page.locator("#confirm-record")).to_contain_text("已确认 v1")
                ready = probe()
                ui["provider"] = ready["ui"]["provider"]
                ui["shots"] = shot_ids
                check("V2.4.2-03", "生成执行区就绪：4 张图待生成、provider 身份可见、锁定提示收起",
                      len(ready["ui"]["rows"]) == 4
                      and all(item["state"] == "none" for item in ready["ui"]["rows"])
                      and "fake-qwen-image" in ready["ui"]["provider"]
                      and ready["ui"]["editor_hidden"] is False
                      and ready["ui"]["locked_hidden"] is True
                      and ready["project_state"] == "READY_TO_GENERATE",
                      {"provider": ready["ui"]["provider"], "state": ready["project_state"],
                       "shots": shot_ids})
                shot_main = shot_ids[0]
                shot_second = shot_ids[1]
                shot_third = shot_ids[2]
                shot_fourth = shot_ids[3]

                # ---- 04/05 提交前落库 + 双击单条 ----
                mode["image_scenario"] = "ok"
                gate_one = threading.Event()
                mode["gate"] = gate_one
                mode["delay"] = 2.0
                page.evaluate(
                    """(shotId) => {
                        const row = document.querySelector(
                            '#attempt-list .attempt-row[data-shot-id="' + shotId + '"]');
                        const button = row.querySelector('button.primary');
                        button.click();
                        button.click();
                    }""",
                    shot_main,
                )
                reached = gate_one.wait(15)
                inflight = probe()
                inflight_chain = chain_of(inflight, shot_main)
                last = inflight_chain[-1]["payload"] if inflight_chain else None
                expected_prompt = inflight["prompts"].get(shot_main, {})
                check("V2.4.2-04",
                      "提交前落库：服务端已收到提交时，IndexedDB 已是 pending_submit 且 Prompt 版本一致",
                      reached and last is not None and last["state"] == "pending_submit"
                      and last["task_id"] is None
                      and last["prompt"]["version"] == expected_prompt.get("version")
                      and last["prompt"]["hash"] == expected_prompt.get("hash")
                      and len(inflight_chain) == 1,
                      {"reached": reached, "state": last["state"] if last else None,
                       "action": last["action_id"] if last else None})
                wait_state(shot_main, "submitted", timeout=20_000)
                mode["gate"] = None
                mode["delay"] = 0.0
                submitted = probe()
                chain = chain_of(submitted, shot_main)
                final = chain[-1]["payload"]
                captured = [item for item in submit_requests
                            if item["action_id"] == final["action_id"]]
                check("V2.4.2-05", "双击只产生一条 Attempt：只发生一次提交，且迁移链只有一个 action id",
                      len(action_ids(chain)) == 1 and len(captured) == 1
                      and chain[0]["payload"]["state"] == "pending_submit",
                      {"actions": action_ids(chain), "submit_requests": len(captured)})
                expected_task = "fake-" + hashlib.sha256(
                    final["action_id"].encode("utf-8")).hexdigest()[:16]
                prompt_text = submitted["prompts"][shot_main]["text"]
                request_ok = bool(captured) and (
                    captured[0]["prompt"] == prompt_text
                    and captured[0]["references"] == final["references"]
                    and captured[0]["size"] == final["parameters"]["size"])
                check("V2.4.2-06",
                      "提交信封 → submitted：task id 保存；请求里的 Prompt / 引用 / 尺寸与记录一致",
                      final["state"] == "submitted" and final["task_id"] == expected_task
                      and final["provider"]["provider_id"] == "fake-qwen-image"
                      and final["error"] is None and request_ok,
                      {"task": final["task_id"], "expected": expected_task,
                       "request_ok": request_ok, "references": final["references"]})

                # ---- 07/08 核对推进 + 刷新恢复 ----
                status_before = len(status_requests)
                row(shot_main).locator('button:has-text("核对任务")').click()
                wait_state(shot_main, "succeeded", timeout=20_000)
                reconciled = probe()
                chain_r = chain_of(reconciled, shot_main)
                final_r = chain_r[-1]["payload"]
                new_status = status_requests[status_before:]
                check("V2.4.2-07", "按 task id 核对推进 succeeded：迁移链完整、没有重新提交",
                      final_r["state"] == "succeeded"
                      and [entry["to"] for entry in final_r["change_log"]]
                      == ["pending_submit", "submitted", "succeeded"]
                      and new_status == [expected_task]
                      and len([item for item in submit_requests
                               if item["action_id"] == final["action_id"]]) == 1,
                      {"chain": [entry["to"] for entry in final_r["change_log"]],
                       "status_requests": new_status})

                page.reload(wait_until="networkidle")
                stage_nav.goto(page, "generate")
                expect(page.locator("#attempt-editor")).to_be_visible()
                wait_state(shot_main, "succeeded", timeout=20_000)
                reloaded = probe()
                reload_final = chain_of(reloaded, shot_main)[-1]["payload"]
                row_main = row_of(reloaded, shot_main) or {}
                check("V2.4.2-08", "刷新恢复：succeeded 身份、task id 与 UI 徽标一致",
                      reload_final["state"] == "succeeded"
                      and reload_final["task_id"] == expected_task
                      and reload_final["action_id"] == final_r["action_id"]
                      and "已成功" in (row_main.get("badges") or []),
                      {"task": reload_final["task_id"], "badges": row_main.get("badges")})

                # ---- 09 服务端重启后按 task id 核对 ----
                mode["image_scenario"] = "ok"
                row(shot_second).locator('button:has-text("生成这张图")').click()
                wait_state(shot_second, "submitted", timeout=20_000)
                second = probe()
                chain_s = chain_of(second, shot_second)
                record_s = chain_s[-1]["payload"]
                status_count_before = len(
                    [item for item in status_requests if item == record_s["task_id"]])
                restart_events.append(
                    {"at": datetime.now().isoformat(timespec="seconds"),
                     "task": record_s["task_id"],
                     "status_requests_before_restart": status_count_before})
                restart_server()
                row(shot_second).locator('button:has-text("核对任务")').click()
                wait_state(shot_second, "succeeded", timeout=20_000)
                after_restart = probe()
                final_s = chain_of(after_restart, shot_second)[-1]["payload"]
                status_count_after = len(
                    [item for item in status_requests if item == record_s["task_id"]])
                check("V2.4.2-09",
                      "服务端重启后按已保存 task id 核对成功（服务端无任务表）",
                      final_s["state"] == "succeeded"
                      and final_s["task_id"] == record_s["task_id"]
                      and status_count_before == 0 and status_count_after == 1,
                      {"task": record_s["task_id"], "state": final_s["state"],
                       "status_before": status_count_before,
                       "status_after": status_count_after})

                # ---- 10 Unknown 不自动重提 ----
                mode["image_scenario"] = "submit_unknown"
                row(shot_third).locator('button:has-text("生成这张图")').click()
                wait_state(shot_third, "unknown", timeout=20_000)
                mode["image_scenario"] = "ok"
                unknown = probe()
                chain_u = chain_of(unknown, shot_third)
                record_u = chain_u[-1]["payload"]
                unknown_requests = [item for item in submit_requests
                                    if item["action_id"] == record_u["action_id"]]
                row_u = row_of(unknown, shot_third) or {}
                buttons_u = [item["text"] for item in row_u.get("buttons", [])]
                check("V2.4.2-10",
                      "Unknown 不自动重提：unknown / 无 task id / requires_review，界面只给显式新建",
                      record_u["state"] == "unknown" and record_u["task_id"] is None
                      and (record_u["error"] or {}).get("family") == "provider_unknown"
                      and (record_u["error"] or {}).get("code") == "PROVIDER_OUTCOME_UNKNOWN"
                      and (record_u["error"] or {}).get("retry_policy") == "requires_review"
                      and len(unknown_requests) == 1
                      and any("新建 action" in text for text in buttons_u)
                      and not any("核对任务" in text for text in buttons_u)
                      and "结果未知" in " ".join(row_u.get("badges") or []),
                      {"state": record_u["state"], "requests": len(unknown_requests),
                       "buttons": buttons_u})

                # ---- 11 显式新建 action 保留旧 unknown 记录 ----
                def versions_of(chain: list, action_id: str) -> list:
                    return [(entry["version"],
                             json.dumps(entry["payload"], ensure_ascii=False, sort_keys=True))
                            for entry in chain
                            if entry["payload"]["action_id"] == action_id]

                before_unknown = versions_of(chain_u, record_u["action_id"])
                row(shot_third).locator('button:has-text("新建 action")').click()
                wait_state(shot_third, "submitted", timeout=20_000)
                renewed = probe()
                chain_r2 = chain_of(renewed, shot_third)
                check("V2.4.2-11", "显式新建 action：新身份生效，旧 unknown 记录逐字保留",
                      len(action_ids(chain_r2)) == 2
                      and chain_r2[-1]["payload"]["state"] == "submitted"
                      and versions_of(chain_r2, record_u["action_id"]) == before_unknown,
                      {"actions": action_ids(chain_r2),
                       "state": chain_r2[-1]["payload"]["state"],
                       "old_versions": [item[0] for item in before_unknown]})

                # ---- 12 刷新打断提交：pending 保留、不自动重提 ----
                gate_two = threading.Event()
                mode["gate"] = gate_two
                mode["delay"] = 2.0
                row(shot_fourth).locator('button:has-text("生成这张图")').click()
                reached_two = gate_two.wait(15)
                midflight = probe()
                mid_chain = chain_of(midflight, shot_fourth)
                mid_record = mid_chain[-1]["payload"] if mid_chain else None
                page.reload(wait_until="networkidle")
                mode["gate"] = None
                mode["delay"] = 0.0
                stage_nav.goto(page, "generate")
                expect(page.locator("#attempt-editor")).to_be_visible()
                wait_state(shot_fourth, "pending_submit", timeout=20_000)
                recovered = probe()
                chain_f = chain_of(recovered, shot_fourth)
                record_f = chain_f[-1]["payload"]
                row_f = row_of(recovered, shot_fourth) or {}
                buttons_f = [item["text"] for item in row_f.get("buttons", [])]
                submit_f = [item for item in submit_requests
                            if item["action_id"] == record_f["action_id"]]
                check("V2.4.2-12",
                      "刷新打断提交：pending 身份保留、不自动重提、界面可显式新建 action",
                      reached_two and mid_record is not None
                      and mid_record["state"] == "pending_submit"
                      and record_f["state"] == "pending_submit"
                      and record_f["task_id"] is None
                      and len(submit_f) == 1
                      and any("新建 action" in text for text in buttons_f)
                      and "没有留下任务编号" in (row_f.get("meta") or ""),
                      {"state": record_f["state"], "requests": len(submit_f),
                       "buttons": buttons_f})

                # ---- 13 刷新后显式新建 action，旧 pending 原样 ----
                before_pending = versions_of(chain_f, record_f["action_id"])
                row(shot_fourth).locator('button:has-text("新建 action")').click()
                wait_state(shot_fourth, "submitted", timeout=20_000)
                renewed_f = probe()
                chain_f2 = chain_of(renewed_f, shot_fourth)
                check("V2.4.2-13",
                      "刷新后显式新建 action：旧 pending 记录原样保留、新身份可提交",
                      len(action_ids(chain_f2)) == 2
                      and chain_f2[-1]["payload"]["state"] == "submitted"
                      and versions_of(chain_f2, record_f["action_id"]) == before_pending,
                      {"actions": action_ids(chain_f2),
                       "state": chain_f2[-1]["payload"]["state"],
                       "old_versions": [item[0] for item in before_pending]})

                # ---- 14 Prompt 前进后过期标记 ----
                before_stale = probe()
                chain_before = json.dumps(chain_of(before_stale, shot_main),
                                          ensure_ascii=False, sort_keys=True)
                prompt_text = before_stale["prompts"][shot_main]["text"]
                save_edit(
                    page, shot_main,
                    prompt_text + "\n\n补充约束：商品标志必须位于正面中心，颜色与参考图保持逐字一致。",
                    "验证过期标记")
                after_stale = probe()
                row_stale = row_of(after_stale, shot_main) or {}
                chain_after = json.dumps(chain_of(after_stale, shot_main),
                                         ensure_ascii=False, sort_keys=True)
                badges = " ".join(row_stale.get("badges") or [])
                check("V2.4.2-14",
                      "Prompt 前进后旧 Attempt 标「基于旧版本 v1」，记录零改写",
                      after_stale["prompts"][shot_main]["version"]
                      == before_stale["prompts"][shot_main]["version"] + 1
                      and "基于旧版本 v1" in badges
                      and chain_after == chain_before
                      and after_stale["project_state"] == "PLAN_REVIEW",
                      {"prompt_version": after_stale["prompts"][shot_main]["version"],
                       "badges": row_stale.get("badges"),
                       "state": after_stale["project_state"]})

                screenshot_rel = f"evals/product-v2/v2.4.2-generation-attempt-{stamp}.png"
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                screenshots.append(screenshot_rel)
                ui["final"] = {
                    "project_state": after_stale["project_state"],
                    "attempt_states": {row["shot_id"]: row["state"]
                                       for row in after_stale["ui"]["rows"]},
                    "submit_requests": len(submit_requests),
                    "status_requests": len(status_requests),
                    "restart_events": restart_events,
                }
            finally:
                context.close()
    except Exception as error:  # noqa: BLE001 - 中断也要留下证据文件
        interrupted = f"{type(error).__name__}: {error}"
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass

    if interrupted:
        check("V2.4.2-99", "浏览器闭环在完成前中断", False, interrupted)

    expected_noise = ("Failed to load resource: the server responded with a status of 504",
                      "net::ERR_ABORTED")
    unexpected_console = [item for item in console_errors
                          if not any(noise in item for noise in expected_noise)]
    check("V2.4.2-15", "零意外 console error / page error（预期内的 504 与刷新中断除外）",
          not unexpected_console and not page_errors,
          {"console": console_errors[:6], "unexpected": unexpected_console,
           "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.4.2-16", "正式入口自检仍全过（V2.4.2 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明「一次生成」在真实浏览器与真实 HTTP 上可核对：发起提交之前先把 pending_submit 身份写进 "
        "IndexedDB（服务端已收到请求时记录已在库里），双击与重入只产生一条 Attempt；提交信封按网关四类"
        "归口推进状态，task id / request id / 错误语义原样保存；核对只按已保存的 task id 查询，服务端重启"
        "（无任务表）后结论不变；没有 task id 的 Unknown 不允许自动重提，界面只提供显式新建 action，"
        "且旧记录逐字保留；刷新打断提交时 pending 身份仍在、不产生第二次提交；Prompt 前进后旧 Attempt "
        "标「基于旧版本 v1」且记录零改写。请求体里的 Prompt 文本、参考图与尺寸与记录和页面一致。"
        "本批不保存候选字节（V2.4.4）、不做整套批量与部分失败（V2.4.3）、不做审核与返工（Phase 5）；"
        "全程 0 次真实模型调用、0 次外部网络；图像 provider 是注入的假替身，只证明身份与状态机，"
        "不证明真实出图质量。"
    )
    report = {
        "task": "V2.4.2",
        "suite_id": "v2.4.2-generation-attempt",
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
    json_path = EVIDENCE_DIR / f"v2.4.2-generation-attempt-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.4.2-generation-attempt-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.4.2 浏览器 Attempt、action ID、task ID 与 Unknown 恢复",
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
