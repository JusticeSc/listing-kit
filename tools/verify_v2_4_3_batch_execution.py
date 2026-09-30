#!/usr/bin/env python
"""V2.4.3 证据：整套批次执行、逐图进度、停止与部分失败（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 通过 node --check（ESM 语法门）。
  2) B01..B09 契约套件在真实 Chromium 全过；既有契约套件回归全过。
  3) 就绪：4 张图待提交，批次条可见，按钮文本「整套生成（4 张）」。
  4) 正常批次：按套图顺序各提交一次，自动核对到全部成功，进度文本一致。
  5) 部分失败：一张明确失败不阻塞批次；成功结果保留；已完成的图零改写。
  6) 失败重试：单张重试成功后旧失败记录逐字保留，无关记录零改写。
  7) 未知：无任务编号、不自动重提、观察窗口内零改写；显式新建 action 后成功。
  8) 停止：停止只停新增提交；已提交身份核对一次给出结论；剩余可继续生成。
  9) 刷新恢复：批次中途刷新，身份保留、不产生第二次提交；继续生成剩余后全部成功。
 10) 零意外 console error / page error；截图落盘；正式入口 --check 全过。

运行：
  uv run --locked python tools/verify_v2_4_3_batch_execution.py
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
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/batch-contract.js",
]

EXPECTED_CASES = [f"B{index:02d}" for index in range(1, 10)]
NEGATIVE_CASES = ["B04", "B06"]
REGRESSION_SUITES = (
    ("attempt", "attempt-contract.html", "__V2_ATTEMPT_RESULTS__"),
    ("confirm", "confirm-contract.html", "__V2_CONFIRM_RESULTS__"),
    ("prompt_edit", "prompt-edit-contract.html", "__V2_PROMPT_EDIT_RESULTS__"),
    ("suite_editor", "suite-editor-contract.html", "__V2_SUITE_EDITOR_RESULTS__"),
)

MARK_FAIL = "MARK-FAIL-V243"
MARK_UNKNOWN = "MARK-UNKNOWN-V243"

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
        evidence: [{ kind: "user", ref: "v243-seed" }], depends_on: [],
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

BATCH_PROBE = """
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
  const buttonInfo = (id) => {
    const node = document.getElementById(id);
    if (!node) return null;
    return { text: node.textContent, disabled: node.disabled, hidden: node.hidden };
  };
  const errorNode = document.getElementById("attempt-error");
  const statusNode = document.getElementById("attempt-status");
  const providerNode = document.getElementById("attempt-provider");
  const lockedNode = document.getElementById("attempt-locked");
  const editorNode = document.getElementById("attempt-editor");
  const batchNode = document.getElementById("attempt-batch");
  const progressNode = document.getElementById("batch-progress");
  const hintNode = document.getElementById("batch-hint");
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
      batch_visible: batchNode ? !batchNode.hidden : null,
      batch: {
        progress: progressNode ? progressNode.textContent : "",
        hint: hintNode ? hintNode.textContent : "",
        hint_hidden: hintNode ? hintNode.hidden : null,
        run: buttonInfo("batch-run"),
        stop: buttonInfo("batch-stop"),
        reconcile: buttonInfo("batch-reconcile"),
        retry: buttonInfo("batch-retry"),
      },
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
    stage_nav.goto(page, "generate")
    for shot_id in shot_ids:
        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
        page.click(card + " .toolbar button")
        page.wait_for_selector(card + '[data-prompt-state="saved"]', timeout=15_000)
        page.wait_for_timeout(wait_ms)


def save_edit(page, shot_id: str, text: str, reason: str, wait_ms: int = 600) -> None:
    stage_nav.goto(page, "generate")
    card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
    page.fill(card + " textarea.prompt-edit-text", text)
    page.fill(card + " input.prompt-edit-reason", reason)
    page.click(card + " .prompt-edit-block button")
    page.wait_for_timeout(wait_ms)


def chain_of(data: dict, shot_id: str) -> list:
    return data["attempt_chains"].get(shot_id, [])


def row_of(data: dict, shot_id: str) -> dict | None:
    return next((row for row in data["ui"]["rows"] if row["shot_id"] == shot_id), None)


def chain_json(data: dict, shot_id: str) -> str:
    return json.dumps(chain_of(data, shot_id), ensure_ascii=False, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.4.3 整套批次执行验证")
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
    check("V2.4.3-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"],
          {"failed": [item for item in node_result["files"] if item["rc"] != 0][:3]})

    static_server, static_url = start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["batch"] = read_suite(
                    browser, static_url + "/harness/batch-contract.html",
                    "__V2_BATCH_RESULTS__", console_errors, page_errors)
                for name, page_name, variable in REGRESSION_SUITES:
                    suites[name] = read_suite(
                        browser, static_url + "/harness/" + page_name, variable,
                        console_errors, page_errors)
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    suite = suites["batch"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.4.3-01", "B01–B09 契约套件全过且用例齐全",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")} for item in failed_cases[:3]]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.4.3-02", "反向探针确实执行（非法输入 / 无身份记录不许自动重提）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "batch"}
    check("V2.4.3-02b", "既有契约套件回归：Attempt / 确认单 / Prompt 编辑 / 套图编辑器全过",
          all(item["status"] == "passed" and not item["failed"] for item in regression.values()),
          regression)

    module = load_server_module()
    from src.providers.v2_fake_image import FakeImageProvider  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415
    from src.providers.v2_image import ImageFailure, ImageTaskResult  # noqa: PLC0415

    mode: dict = {"tasks": {}, "hold": None, "arrived": None}

    class MarkerImageProvider(FakeImageProvider):
        """按 Prompt 里的标记决定这一张图的场景；替身保持无状态：场景表放在验证器里。"""

        def submit(self, request):
            self.calls["submit"] += 1
            hold = mode.get("hold")
            if hold is not None:
                arrived = mode.get("arrived")
                if arrived is not None:
                    arrived.set()
                hold.wait(30)
            prompt = request.prompt or ""
            scenario = "ok"
            if MARK_FAIL in prompt:
                scenario = "fail"
            elif MARK_UNKNOWN in prompt:
                scenario = "unknown"
            task_id = FakeImageProvider.task_id_for(request.action_id)
            mode["tasks"][task_id] = scenario
            if scenario == "unknown":
                raise ImageFailure(
                    "provider_unknown", "PROVIDER_OUTCOME_UNKNOWN",
                    "提交响应未能确认，服务端是否受理无法判断；先核对，不要自动重提。",
                    retry_policy="requires_review")
            return ImageTaskResult(
                provider_id=self.provider_id, model_id=self.model_id,
                task_id=task_id, status="RUNNING")

        def status(self, request):
            self.calls["status"] += 1
            scenario = mode["tasks"].get(request.task_id, "ok")
            if scenario == "fail":
                return ImageTaskResult(
                    provider_id=self.provider_id, model_id=self.model_id,
                    task_id=request.task_id, status="FAILED",
                    error="图像生成任务失败（错误码 FAKE_CONTENT_REJECTED）。")
            return FakeImageProvider.status(self, request)

    def image_factory():
        return MarkerImageProvider(scenario="ok")

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
    ui: dict = {}
    interrupted: str | None = None
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v243-"))
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
                        })
                    elif "/api/v2/images/status" in request.url:
                        try:
                            body = json.loads(request.post_data or "{}")
                        except ValueError:
                            body = {}
                        status_requests.append(str(body.get("task_id")))

                page.on("request", on_request)

                def probe() -> dict:
                    return page.evaluate(BATCH_PROBE)

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

                def confirm_generation() -> None:
                    stage_nav.goto(page, "generate")
                    expect(page.locator("#confirm-action")).to_be_enabled()
                    page.click("#confirm-action")
                    expect(page.locator("#confirm-record")).to_contain_text("已确认 v")

                def add_shots(template_id: str, count: int = 1) -> list:
                    stage_nav.goto(page, "plan")
                    before = list(probe()["shot_ids"])
                    for _ in range(count):
                        page.select_option("#suite-template", template_id)
                        page.click("#suite-add-template")
                        page.wait_for_timeout(250)
                    after = list(probe()["shot_ids"])
                    return [shot for shot in after if shot not in before]

                def click_row_button(shot_id: str, text: str) -> None:
                    stage_nav.goto(page, "generate")
                    row(shot_id).locator(f'button:has-text("{text}")').first.click()

                def submits_for(action_id: str) -> int:
                    return len([item for item in submit_requests
                                if item["action_id"] == action_id])

                # ---------------- 项目准备：空白项目 → 参考图 → 资料 → 槽位 → 套图 ----------------
                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · 整套批次")
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
                confirm_generation()
                ready = probe()
                ui["base_shots"] = shot_ids
                check("V2.4.3-03", "批次条就绪：4 张待提交、整套生成按钮可见",
                      len(ready["ui"]["rows"]) == 4
                      and all(item["state"] == "none" for item in ready["ui"]["rows"])
                      and ready["ui"]["batch_visible"] is True
                      and "整套生成（4 张）" in (ready["ui"]["batch"]["run"] or {}).get("text", "")
                      and (ready["ui"]["batch"]["stop"] or {}).get("hidden") is True
                      and ready["project_state"] == "READY_TO_GENERATE",
                      {"run": (ready["ui"]["batch"]["run"] or {}).get("text"),
                       "progress": ready["ui"]["batch"]["progress"]})

                # ---------------- 正常批次：4 张按顺序各一次，自动核对全部成功 ----------------
                submits_before = len(submit_requests)
                status_before = len(status_requests)
                page.click("#batch-run")
                wait_states({shot: "succeeded" for shot in shot_ids})
                done = probe()
                captured = submit_requests[submits_before:]
                captured_actions = [item["action_id"] for item in captured]
                latest_actions = [chain_of(done, shot)[-1]["payload"]["action_id"]
                                  for shot in shot_ids]
                order_ok = captured_actions == latest_actions
                per_action_once = all(submits_for(action) == 1 for action in captured_actions)
                polled_tasks = [chain_of(done, shot)[-1]["payload"]["task_id"]
                                for shot in shot_ids]
                polled_ok = all(task and task in status_requests[status_before:]
                                for task in polled_tasks)
                final_states_ok = all(
                    chain_of(done, shot)[-1]["payload"]["state"] == "succeeded"
                    and chain_of(done, shot)[-1]["payload"]["error"] is None
                    for shot in shot_ids)
                check("V2.4.3-04",
                      "正常批次：按套图顺序各提交一次，自动核对到全部成功，进度文本一致",
                      len(captured) == 4 and per_action_once and order_ok
                      and polled_ok and final_states_ok
                      and "已成功 4" in done["ui"]["batch"]["progress"],
                      {"captured": len(captured), "order_ok": order_ok,
                       "per_action_once": per_action_once, "polled_ok": polled_ok,
                       "progress": done["ui"]["batch"]["progress"]})
                phase_a_records = {shot: chain_json(done, shot) for shot in shot_ids}

                # ---------------- 部分失败：一张失败不阻塞，其余成功 ----------------
                added = add_shots("detail_material", 1) + add_shots("infographic_benefits", 1)
                compile_all(page, probe()["shot_ids"])
                fail_shot = added[0]
                ok_shot = added[1]
                fail_base_text = probe()["prompts"][fail_shot]["text"]
                save_edit(page, fail_shot,
                          fail_base_text + "\n\n" + MARK_FAIL
                          + "：这张图在正式批次的提交必须失败（验证部分失败隔离）。",
                          "验证部分失败")
                confirm_generation()
                submits_before = len(submit_requests)
                page.click("#batch-run")
                wait_states({fail_shot: "failed", ok_shot: "succeeded"})
                partial = probe()
                captured = submit_requests[submits_before:]
                captured_actions = [item["action_id"] for item in captured]
                expected_actions = [chain_of(partial, shot)[-1]["payload"]["action_id"]
                                    for shot in [fail_shot, ok_shot]]
                failed_entry = chain_of(partial, fail_shot)[-1]["payload"]
                ok_entry = chain_of(partial, ok_shot)[-1]["payload"]
                untouched = all(chain_json(partial, shot) == phase_a_records[shot]
                                for shot in shot_ids)
                check("V2.4.3-05",
                      "部分失败：失败不阻塞批次（两张都提交）、成功结果保留、已完成的图零改写",
                      captured_actions == expected_actions
                      and failed_entry["state"] == "failed"
                      and failed_entry["error"]["family"] == "provider_failed"
                      and "FAKE_CONTENT_REJECTED" in failed_entry["error"]["message"]
                      and ok_entry["state"] == "succeeded"
                      and untouched
                      and "失败 1" in partial["ui"]["batch"]["progress"],
                      {"captured": captured_actions, "expected": expected_actions,
                       "error": failed_entry["error"]["message"],
                       "progress": partial["ui"]["batch"]["progress"]})

                # ---------------- 失败重试：旧记录零改写、无关记录零改写 ----------------
                challenge = probe()["prompts"][fail_shot]["text"]
                save_edit(page, fail_shot, challenge.replace(MARK_FAIL, ""), "移除验证标记")
                confirm_generation()
                before_retry = probe()
                failed_prefix = chain_json(before_retry, fail_shot)
                failed_prefix_len = len(chain_of(before_retry, fail_shot))
                ok_before = chain_json(before_retry, ok_shot)
                failed_action = chain_of(before_retry, fail_shot)[-1]["payload"]["action_id"]
                click_row_button(fail_shot, "重试")
                wait_state(fail_shot, "submitted")
                click_row_button(fail_shot, "核对任务")
                wait_state(fail_shot, "succeeded")
                after_retry = probe()
                retry_chain = chain_of(after_retry, fail_shot)
                retry_prefix = json.dumps(retry_chain[:failed_prefix_len],
                                          ensure_ascii=False, sort_keys=True)
                new_action = retry_chain[-1]["payload"]["action_id"]
                check("V2.4.3-06",
                      "失败重试：单张重试成功；旧失败记录与无关记录逐字保留；新 action 是新身份",
                      retry_prefix == failed_prefix
                      and chain_json(after_retry, ok_shot) == ok_before
                      and new_action != failed_action
                      and submits_for(new_action) == 1
                      and submits_for(failed_action) == 1,
                      {"new_action": new_action, "old_action": failed_action,
                       "submits_old": submits_for(failed_action)})

                # ---------------- 未知：不自动重提；显式新建 action 后成功 ----------------
                unknown_shot = add_shots("detail_material", 1)[0]
                compile_all(page, probe()["shot_ids"])
                unknown_base_text = probe()["prompts"][unknown_shot]["text"]
                save_edit(page, unknown_shot,
                          unknown_base_text + "\n\n" + MARK_UNKNOWN
                          + "：这次提交的结果必须未知（验证不自动重提）。",
                          "验证未知")
                confirm_generation()
                page.click("#batch-run")
                wait_state(unknown_shot, "unknown")
                unknown_after = probe()
                unknown_chain = chain_of(unknown_after, unknown_shot)
                unknown_action = unknown_chain[-1]["payload"]["action_id"]
                unknown_task = unknown_chain[-1]["payload"]["task_id"]
                unknown_submits = submits_for(unknown_action)
                unknown_row = row_of(unknown_after, unknown_shot) or {}
                buttons = [item["text"] for item in unknown_row.get("buttons") or []]
                page.wait_for_timeout(5000)
                observed = probe()
                check("V2.4.3-07",
                      "未知：无任务编号、只提交一次、观察窗口内零改写、只提供显式新建 action",
                      unknown_chain[-1]["payload"]["state"] == "unknown"
                      and unknown_task is None
                      and unknown_submits == 1
                      and chain_json(observed, unknown_shot) == chain_json(unknown_after, unknown_shot)
                      and any("新建 action" in text for text in buttons)
                      and not any("核对任务" in text for text in buttons)
                      and "结果未知 1" in unknown_after["ui"]["batch"]["progress"],
                      {"submits": unknown_submits, "task": unknown_task,
                       "buttons": buttons,
                       "progress": unknown_after["ui"]["batch"]["progress"]})
                unknown_record_before = chain_json(observed, unknown_shot)
                unknown_prefix_len = len(chain_of(observed, unknown_shot))

                unknown_text = probe()["prompts"][unknown_shot]["text"]
                save_edit(page, unknown_shot, unknown_text.replace(MARK_UNKNOWN, ""), "移除未知标记")
                confirm_generation()
                click_row_button(unknown_shot, "新建 action")
                wait_state(unknown_shot, "submitted")
                click_row_button(unknown_shot, "核对任务")
                wait_state(unknown_shot, "succeeded")
                unknown_fixed = probe()
                fixed_chain = chain_of(unknown_fixed, unknown_shot)
                fixed_prefix = json.dumps(fixed_chain[:unknown_prefix_len],
                                          ensure_ascii=False, sort_keys=True)
                check("V2.4.3-08",
                      "未知显式新建 action 后成功；旧未知记录逐字保留",
                      fixed_prefix == unknown_record_before
                      and fixed_chain[-1]["payload"]["state"] == "succeeded"
                      and fixed_chain[-1]["payload"]["action_id"] != unknown_action
                      and len(fixed_chain) > unknown_prefix_len,
                      {"chain": [entry["payload"]["state"] for entry in fixed_chain]})

                # ---------------- 停止：只停新增提交，已提交身份核对一次 ----------------
                added = add_shots("detail_material", 1) + add_shots("infographic_benefits", 1) \
                    + add_shots("detail_material", 1)
                compile_all(page, probe()["shot_ids"])
                confirm_generation()
                stop_first, stop_second, stop_third = added[0], added[1], added[2]
                mode["arrived"] = threading.Event()
                mode["hold"] = threading.Event()
                submits_before = len(submit_requests)
                page.click("#batch-run")
                arrived = mode["arrived"].wait(20)
                page.click("#batch-stop")
                mode["hold"].set()
                mode["hold"] = None
                wait_state(stop_first, "succeeded")
                stopped = probe()
                stop_window = list(submit_requests[submits_before:])
                check("V2.4.3-09",
                      "停止：只提交了已开始的一张；停止后不再新增提交；已提交身份仍核对出结论",
                      arrived
                      and len(stop_window) == 1
                      and chain_of(stopped, stop_second) == []
                      and chain_of(stopped, stop_third) == []
                      and chain_of(stopped, stop_first)[-1]["payload"]["state"] == "succeeded"
                      and "批次已停止" in stopped["ui"]["status"],
                      {"arrived": arrived, "window": stop_window,
                       "status": stopped["ui"]["status"]})

                # ---------------- 刷新恢复：身份保留、无第二次提交；继续生成剩余 ----------------
                mode["arrived"] = threading.Event()
                mode["hold"] = threading.Event()
                submits_before = len(submit_requests)
                page.click("#batch-run")
                arrived = mode["arrived"].wait(20)
                pre_reload = probe()
                pending_chain = chain_of(pre_reload, stop_second)
                page.reload(wait_until="networkidle")
                mode["hold"].set()
                mode["hold"] = None
                page.wait_for_timeout(800)
                stage_nav.goto(page, "generate")
                restored = probe()
                restored_chain = chain_of(restored, stop_second)
                restored_row = row_of(restored, stop_second) or {}
                restored_buttons = [item["text"] for item in restored_row.get("buttons") or []]
                check("V2.4.3-10",
                      "刷新恢复：被中断的提交保留身份、不自动重提；批次条按记录重算剩余",
                      arrived
                      and len(pending_chain) == 1
                      and pending_chain[0]["payload"]["state"] == "pending_submit"
                      and len(restored_chain) == 1
                      and restored_chain[0]["payload"]["state"] == "pending_submit"
                      and restored_chain[0]["payload"]["task_id"] is None
                      and submits_for(restored_chain[0]["payload"]["action_id"]) == 1
                      and chain_of(restored, stop_third) == []
                      and any("新建 action" in text for text in restored_buttons)
                      and "继续生成剩余（1 张）" in (restored["ui"]["batch"]["run"] or {}).get("text", "")
                      and "没有任务编号" in restored["ui"]["batch"]["hint"],
                      {"restored_state": restored_chain[0]["payload"]["state"],
                       "run": (restored["ui"]["batch"]["run"] or {}).get("text"),
                       "hint": restored["ui"]["batch"]["hint"]})

                stuck_action = restored_chain[0]["payload"]["action_id"]
                click_row_button(stop_second, "新建 action")
                wait_state(stop_second, "submitted")
                page.click("#batch-run")
                wait_states({stop_second: "succeeded", stop_third: "succeeded"})
                finished = probe()
                final_rows = finished["ui"]["rows"]
                all_succeeded = all(item["state"] == "succeeded" for item in final_rows)
                check("V2.4.3-11",
                      "继续生成剩余：补交剩余图并核对在途身份，全部图（10 张）最终成功",
                      all_succeeded and len(final_rows) == 10
                      and submits_for(stuck_action) == 1
                      and "已成功 10" in finished["ui"]["batch"]["progress"],
                      {"rows": len(final_rows), "progress": finished["ui"]["batch"]["progress"],
                       "stuck_submits": submits_for(stuck_action)})

                screenshot_rel = f"evals/product-v2/v2.4.3-batch-suite-{stamp}.png"
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                screenshots.append(screenshot_rel)
                ui["final"] = {
                    "project_state": finished["project_state"],
                    "attempt_states": {item["shot_id"]: item["state"] for item in final_rows},
                    "submit_requests": len(submit_requests),
                    "status_requests": len(status_requests),
                    "shot_count": len(final_rows),
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
        check("V2.4.3-99", "浏览器闭环在完成前中断", False, interrupted)

    expected_noise = ("Failed to load resource: the server responded with a status of 504",
                      "net::ERR_ABORTED")
    unexpected_console = [item for item in console_errors
                          if not any(noise in item for noise in expected_noise)]
    check("V2.4.3-12", "零意外 console error / page error（预期内的 504 与刷新中断除外）",
          not unexpected_console and not page_errors,
          {"console": console_errors[:6], "unexpected": unexpected_console,
           "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.4.3-13", "正式入口自检仍全过（V2.4.3 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明「整套生成」在真实浏览器与真实 HTTP 上是可停止、可恢复、可隔离的：批次按套图顺序"
        "逐张提交，每张先落 pending_submit、只提交一次；批次自动按已保存 task id 核对到终态；"
        "一张明确失败不阻塞其余图片，成功记录逐字保留；失败图可单独重试，旧失败记录与无关记录"
        "零改写；结果未知（无任务编号）不自动重提，只提供显式新建 action；停止只停新增提交，"
        "已提交身份仍核对出结论；批次中途刷新后身份保留、不产生第二次提交，剩余图片可继续生成。"
        "本批不保存候选字节（V2.4.4）、不做审核与返工（Phase 5）；全程 0 次真实模型调用、"
        "0 次外部网络；图像 provider 是注入的假替身（按 Prompt 标记决定场景），只证明批次与状态"
        "语义，不证明真实出图质量。"
    )
    report = {
        "task": "V2.4.3",
        "suite_id": "v2.4.3-batch-suite",
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
    json_path = EVIDENCE_DIR / f"v2.4.3-batch-suite-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.4.3-batch-suite-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.4.3 整套批次执行、逐图进度与部分失败",
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
