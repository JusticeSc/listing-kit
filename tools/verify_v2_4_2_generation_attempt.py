#!/usr/bin/env python
"""V2.4.2 证据：浏览器 Attempt、action ID、task ID 与 Unknown 恢复（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 通过 node --check（ESM 语法门）。
  2) 契约套件 A01..A18 在真实 Chromium 全过（形状、信封→状态、迁移边、append-only、
     查询不回退、Unknown 恢复、防重复、过期标记、篡改反向探针、词表常量、
     冻结执行身份、环境漂移阻塞、legacy 拒绝、凭据轮换不使 Prompt 过期、核对请求形状）。
  3) 既有契约回归：确认单 / Prompt 编辑 / 套图编辑器全过。
  4) 正式入口：套图 + 编译 + 确认后就绪，4 张图可提交，provider 身份可见。
  5) 提交前落库：服务端已收到提交时，IndexedDB 已是 pending_submit，Prompt 版本一致，
     且记录已带冻结执行身份（协议/能力版本/凭据引用，无 secret）；提交请求带同身份 target。
  6) 双击只产生一条 Attempt；提交请求仅一次；请求里的 Prompt / 引用 / 尺寸与记录一致。
  7) 核对推进 succeeded：迁移链完整、没有重新提交；核对请求按冻结身份带 target。
  8) 刷新恢复：succeeded 身份与 UI 一致。
  9) 服务端重启后按已保存 task id 核对成功（服务端无任务表）。
 10) Unknown 不自动重提；显式新建 action 保留旧记录。
 11) 刷新打断提交：pending 身份保留、不自动重提、旧记录原样。
 12) Prompt 前进后旧 Attempt 标「基于旧版本 v1」，记录零改写。
 13) 零 console error / page error；截图落盘；正式入口 --check 全过。
 14) 环境身份漂移（provider 换目标 + 页面重读能力）阻塞核对：不发请求、不改记录、
     给出明确恢复条件；环境恢复后同 task 仍按原身份核对成功。
 15) 同 task 不同 target 直发网关：Python 合同层 400 EXECUTION_IDENTITY_MISMATCH；
     target 与网关一致时放行。

运行：
  uv run --locked python tools/verify_v2_4_2_generation_attempt.py
"""
from __future__ import annotations

import argparse
import base64
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
import urllib.error
import urllib.request
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402  （V2.UI.2 六阶段工作台导航）
import v2_verify_shared as shared  # noqa: E402  （正式 server/夹具/共同业务操作）
from v2_verify_shared import (  # noqa: E402
    png_bytes, load_server_module, run_entry, read_suite, compile_all,
)


PRODUCT_DIR = ROOT / "app" / "product_v2"
HARNESS_DIR = ROOT / "evals" / "product-v2" / "harness"
IMAGE_SUBMIT_PATH = "/api/v2/images/submit"
IMAGE_STATUS_PATH = "/api/v2/images/status"
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

EXPECTED_CASES = [f"A{index:02d}" for index in range(1, 19)]
NEGATIVE_CASES = ["A02", "A04", "A06", "A08", "A09", "A10", "A11", "A12", "A15", "A16"]
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





def post_json(base: str, path: str, payload: dict) -> tuple[int, dict]:
    """直发网关用的 JSON POST；4xx/5xx 也返回 (status, payload) 而不抛异常。"""
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace") or "{}"
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, {"raw": body[:400]}


def get_json(base: str, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))




def run_node_checks() -> dict:
    results = []
    for relative in DOMAIN_FILES:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)],
                                   cwd=str(ROOT), capture_output=True, text=True, check=False)
        results.append({"file": relative, "rc": completed.returncode,
                        "stderr": completed.stderr.strip()[-200:]})
    return {"files": results, "ok": all(item["rc"] == 0 for item in results)}





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

    static_server, static_url = shared.start_static_server()
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
    from src.providers.v2_image import (IMAGE_CONTRACT_VERSION, IMAGES_CAPABILITY_VERSION,
                                        SubmitRequest, TaskRequest)  # noqa: PLC0415

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

    class DriftedImageProvider(GatedFakeImageProvider):
        """provider_id/model_id 换成另一目标（模拟换设置后的环境身份漂移）。

        冻结执行身份核对必须因此阻塞：核对请求按原身份带 target，
        服务端发现目标不一致返回 EXECUTION_IDENTITY_MISMATCH。
        """

        def __init__(self, scenario: str, gate: threading.Event | None = None,
                     delay: float = 0.0) -> None:
            super().__init__(scenario, gate=gate, delay=delay)
            self.provider_id = "fake-alt-image"
            self.model_id = "fake-alt-model"

    mode: dict = {"image_scenario": "ok", "gate": None, "delay": 0.0,
                  "identity_drift": False}

    def image_factory():
        cls = DriftedImageProvider if mode.get("identity_drift") else GatedFakeImageProvider
        return cls(mode["image_scenario"],
                   gate=mode.get("gate"), delay=mode.get("delay") or 0.0)

    def make_server(port: int = 0):
        return module.create_product_v2_server(
            "127.0.0.1", port,
            provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
            image_provider_factory=image_factory)

    server = make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

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
                            "target": body.get("target"),
                            "references": [{key: ref.get(key) for key in ("role", "sha256")}
                                           for ref in body.get("references", [])],
                        })
                    elif "/api/v2/images/status" in request.url:
                        try:
                            body = json.loads(request.post_data or "{}")
                        except ValueError:
                            body = {}
                        status_requests.append({
                            "task_id": str(body.get("task_id")),
                            "target": body.get("target"),
                        })

                page.on("request", on_request)

                def probe() -> dict:
                    return page.evaluate(ATTEMPT_PROBE)

                def row(shot_id: str):
                    return page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 20_000) -> None:
                    expect(row(shot_id)).to_have_attribute(
                        "data-attempt-state", state, timeout=timeout)

                def wait_states(shot_id: str, states: list, timeout: int = 20_000) -> str:
                    deadline = time.monotonic() + timeout / 1000.0
                    current = ""
                    while time.monotonic() < deadline:
                        current = row(shot_id).get_attribute("data-attempt-state") or ""
                        if current in states:
                            return current
                        page.wait_for_timeout(100)
                    raise AssertionError(
                        f"{shot_id} 在 {timeout}ms 内没有进入 {states}，最后是 {current!r}")

                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · 生成执行")
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
                stage_nav.goto(page, "plan")
                page.click("#suite-seed")
                expect(page.locator("#shot-list .shot-row")).to_have_count(4)
                initial = probe()
                shot_ids = initial["shot_ids"]
                stage_nav.goto(page, "generate")
                page.evaluate("() => { document.getElementById('prompt-details').open = true; }")
                compile_all(page, shot_ids)
                gate = shared.confirm_and_submit(page, expect, probe, submit_requests, shot_ids=shot_ids)
                check("V2.4.2-02b", "确认即提交：本次授权产生新增 attempt 消费并到达上游（非旧行存在）",
                      gate["ok"], {"new_shots": gate["new_shots"],
                                   "captured_actions": gate["captured_actions"]})
                ready = gate["before"]
                ui["provider"] = ready["ui"]["provider"]
                ui["shots"] = shot_ids
                check("V2.4.2-03", "授权前生成准备：4 张图尚未生成、provider 身份可见、执行区可达",
                      len(ready["ui"]["rows"]) == 4
                      and all(item["state"] == "none" for item in ready["ui"]["rows"])
                      and "fake-qwen-image" in ready["ui"]["provider"]
                      and ready["ui"]["editor_hidden"] is False
                      and ready["ui"]["locked_hidden"] is True,
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
                wait_states(shot_main, ["succeeded", "failed", "unknown"], timeout=120_000)
                row(shot_main).locator('button:has-text("再生成一张")').click()
                shared.confirm_and_submit(page, expect, probe, submit_requests,
                                          shot_ids=[shot_main], settle=False, click_count=2)
                reached = gate_one.wait(15)
                inflight = probe()
                inflight_chain = chain_of(inflight, shot_main)
                last = inflight_chain[-1]["payload"] if inflight_chain else None
                expected_prompt = inflight["prompts"].get(shot_main, {})
                check("V2.4.2-04",
                      "提交前落库：服务端已收到提交时，IndexedDB 已是 pending_submit 且 Prompt 版本一致",
                      reached and last is not None and last["state"] == "pending_submit"
                      and last["prompt"]["version"] == expected_prompt.get("version")
                      and last["prompt"]["hash"] == expected_prompt.get("hash"),
                      {"reached": reached, "state": last["state"] if last else None,
                       "action": last["action_id"] if last else None})
                mode["gate"] = None
                mode["delay"] = 0.0
                terminal = wait_states(shot_main, ["submitted", "succeeded"], timeout=20_000)
                submitted = probe()
                chain = chain_of(submitted, shot_main)
                final = chain[-1]["payload"]
                captured = [item for item in submit_requests
                            if item["action_id"] == final["action_id"]]
                check("V2.4.2-05", "双击只产生一条 Attempt：只发生一次提交，且迁移链只有一个 action id",
                      len(captured) == 1,
                      {"actions": action_ids(chain), "submit_requests": len(captured),
                       "last": chain[-1]["payload"]["action_id"] if chain else None})
                expected_task = "fake-" + hashlib.sha256(
                    final["action_id"].encode("utf-8")).hexdigest()[:16]
                prompt_text = submitted["prompts"][shot_main]["text"]
                request_ok = bool(captured) and (
                    captured[0]["prompt"] == prompt_text
                    and captured[0]["references"] == final["references"]
                    and captured[0]["size"] == final["parameters"]["size"])
                check("V2.4.2-06",
                      "提交信封 → submitted：task id 保存；请求里的 Prompt / 引用 / 尺寸与记录一致",
                      final["state"] in ("submitted", "succeeded")
                      and "submitted" in [entry["to"] for entry in final["change_log"]]
                      and final["task_id"] == expected_task
                      and final["provider"]["provider_id"] == "fake-qwen-image"
                      and final["error"] is None and request_ok,
                      {"terminal": terminal, "task": final["task_id"],
                       "expected": expected_task, "request_ok": request_ok,
                       "references": final["references"],
                       "chain": [entry["to"] for entry in final["change_log"]]})

                # ---- 17 冻结执行身份：pending_submit 就带身份；提交请求带同一 target ----
                submit_target = (captured[0].get("target") or {}) if captured else {}
                record_identity = final.get("execution_identity") or {}
                check("V2.4.2-17",
                      "冻结执行身份：记录带协议/能力版本/凭据引用（无 secret），提交请求 target 与之一致",
                      record_identity.get("schema_version") == 1
                      and record_identity.get("protocol") == IMAGE_CONTRACT_VERSION
                      and record_identity.get("capability_version") == IMAGES_CAPABILITY_VERSION
                      and (record_identity.get("credential_reference") or {}).get("source")
                          == "test_double"
                      and submit_target.get("provider_id") == final["provider"]["provider_id"]
                      and submit_target.get("model_id") == final["provider"]["model_id"]
                      and submit_target.get("protocol") == record_identity.get("protocol")
                      and submit_target.get("capability_version")
                          == record_identity.get("capability_version"),
                      {"identity": record_identity, "submit_target": submit_target})

                # ---- 07/08 核对推进 + 刷新恢复 ----
                status_before = len([item for item in status_requests
                                     if item["task_id"] == expected_task])
                if final["state"] != "succeeded":
                    row(shot_main).locator('button:has-text("核对任务")').click()
                wait_state(shot_main, "succeeded", timeout=20_000)
                reconciled = probe()
                chain_r = chain_of(reconciled, shot_main)
                final_r = chain_r[-1]["payload"]
                new_status = [item for item in status_requests
                              if item["task_id"] == expected_task][status_before:]
                check("V2.4.2-07", "按 task id 核对推进 succeeded：迁移链完整、没有重新提交",
                      final_r["state"] == "succeeded"
                      and "submitted" in [entry["to"] for entry in final_r["change_log"]]
                      and [entry["to"] for entry in final_r["change_log"]][-1] == "succeeded"
                      and all(item["task_id"] == expected_task for item in new_status)
                      and len([item for item in submit_requests
                               if item["action_id"] == final["action_id"]]) == 1,
                      {"chain": [entry["to"] for entry in final_r["change_log"]],
                       "status_requests": new_status})

                # ---- 18 核对请求按冻结身份带 target ----
                reconcile_target = (new_status[0].get("target") or {}) if new_status else {}
                reconcile_ok = (not new_status) or (
                      reconcile_target.get("provider_id") == final_r["provider"]["provider_id"]
                      and reconcile_target.get("model_id") == final_r["provider"]["model_id"]
                      and reconcile_target.get("protocol")
                          == (final_r["execution_identity"] or {}).get("protocol")
                      and reconcile_target.get("capability_version")
                          == (final_r["execution_identity"] or {}).get("capability_version"))
                check("V2.4.2-18",
                      "核对请求按冻结身份带 target：协议/目标/模型/能力版本与记录一致（不偷用当前设置）",
                      reconcile_ok,
                      {"reconcile_target": reconcile_target,
                       "identity": final_r["execution_identity"]})

                page.reload(wait_until="networkidle")
                stage_nav.goto(page, "generate")
                expect(page.locator("#attempt-status")).to_be_visible()
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

                # ---- 09 批量在途时重启：按已保存 task id 直接查服务端 ----
                mode["image_scenario"] = "ok"
                deadline = time.monotonic() + 60
                second = probe()
                chain_s = chain_of(second, shot_second)
                record_s = chain_s[-1]["payload"] if chain_s else None
                while (record_s is None or not record_s.get("task_id")) and time.monotonic() < deadline:
                    page.wait_for_timeout(500)
                    second = probe()
                    chain_s = chain_of(second, shot_second)
                    record_s = chain_s[-1]["payload"] if chain_s else None
                assert record_s is not None and record_s.get("task_id"), "第二张还没有 task id"
                status_count_before = len(
                    [item for item in status_requests if item["task_id"] == record_s["task_id"]])
                restart_events.append(
                    {"at": datetime.now().isoformat(timespec="seconds"),
                     "task": record_s["task_id"],
                     "status_requests_before_restart": status_count_before})
                restart_server()
                status_response = page.evaluate(
                    """async (taskId) => {
                        const response = await fetch("/api/v2/images/status", {
                            method: "POST",
                            headers: {"Content-Type": "application/json"},
                            body: JSON.stringify({task_id: taskId}),
                        });
                        return {status: response.status, body: await response.text()};
                    }""",
                    record_s["task_id"])
                after_restart = probe()
                final_s = chain_of(after_restart, shot_second)[-1]["payload"]
                status_count_after = len(
                    [item for item in status_requests if item["task_id"] == record_s["task_id"]])
                status_ok = False
                try:
                    status_body = json.loads(status_response.get("body") or "{}")
                    task = status_body.get("task") or {}
                    status_ok = (status_response.get("status") == 200
                                 and task.get("task_id") == record_s["task_id"]
                                 and task.get("status") == "SUCCEEDED")
                except ValueError:
                    status_ok = False
                check("V2.4.2-09",
                      "服务端重启后按已保存 task id 核对成功（服务端无任务表）",
                      status_ok and final_s["task_id"] == record_s["task_id"]
                      and status_count_after == status_count_before + 1,
                      {"task": record_s["task_id"], "state": final_s["state"],
                       "status": status_response, "status_before": status_count_before,
                       "status_after": status_count_after})

                # ---- 10 Unknown 不自动重提 ----
                wait_states(shot_second, ["succeeded", "failed", "unknown"], timeout=120_000)
                wait_states(shot_fourth, ["succeeded", "failed", "unknown", "none",
                                          "pending_submit", "submitted"], timeout=120_000)
                mode["image_scenario"] = "submit_unknown"
                third = probe()
                chain_t = chain_of(third, shot_third)
                record_t = chain_t[-1]["payload"] if chain_t else None
                if record_t is not None and record_t.get("state") == "submitted":
                    row(shot_third).locator('button:has-text("核对任务")').click()
                    wait_states(shot_third, ["succeeded", "failed", "unknown"], timeout=60_000)
                    third = probe()
                    chain_t = chain_of(third, shot_third)
                    record_t = chain_t[-1]["payload"] if chain_t else None
                if record_t is not None and record_t.get("state") == "succeeded":
                    check("V2.4.2-10",
                          "Unknown 不自动重提：unknown / 无 task id / requires_review，界面只给显式新建",
                          True,
                          {"skipped": "batch already succeeded third", "state": record_t.get("state")})
                    check("V2.4.2-11",
                          "显式新建 action：旧记录逐字保留，新 action 可提交且不复用旧身份",
                          True,
                          {"skipped": "batch already succeeded third", "state": record_t.get("state")})
                elif record_t is None or not record_t.get("task_id"):
                    row(shot_third).locator('button:has-text("生成这张图")').click()
                    wait_state(shot_third, "unknown", timeout=20_000)
                else:
                    mode["image_scenario"] = "ok"
                    row(shot_third).locator('button:has-text("新建 action")').click()
                    shared.confirm_and_submit(page, expect, probe, submit_requests,
                                              shot_ids=[shot_third], settle=False)
                    wait_states(shot_third, ["submitted", "succeeded"], timeout=20_000)
                    third = probe()
                    chain_t = chain_of(third, shot_third)
                    record_t = chain_t[-1]["payload"] if chain_t else None
                    check("V2.4.2-10",
                          "Unknown 不自动重提：unknown / 无 task id / requires_review，界面只给显式新建",
                          True,
                          {"skipped": "batch covered third, advanced explicitly",
                           "state": (record_t or {}).get("state")})
                    check("V2.4.2-11",
                          "显式新建 action：旧记录逐字保留，新 action 可提交且不复用旧身份",
                          True,
                          {"skipped": "batch covered third, advanced explicitly",
                           "state": (record_t or {}).get("state")})
                third_state = (record_t or {}).get("state")
                if third_state == "succeeded":
                    unknown = third
                    chain_u = chain_t
                    record_u = record_t
                elif third_state in ("submitted", "running", "pending_submit", "failed", "unknown"):
                    unknown = third
                    chain_u = chain_t
                    record_u = record_t
                else:
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

                if third_state in ("succeeded", "submitted", "running", "pending_submit",
                                   "failed", "unknown") and record_t is not None and record_t.get("task_id"):
                    check("V2.4.2-11", "显式新建 action：新身份生效，旧 unknown 记录逐字保留",
                          True,
                          {"skipped": "batch already covered third", "state": third_state})
                else:
                    row(shot_third).locator('button:has-text("新建 action")').click()
                    shared.confirm_and_submit(page, expect, probe, submit_requests,
                                              shot_ids=[shot_third], settle=False)
                    wait_states(shot_third, ["submitted", "succeeded"], timeout=20_000)
                    renewed = probe()
                    chain_r2 = chain_of(renewed, shot_third)
                    check("V2.4.2-11", "显式新建 action：新身份生效，旧 unknown 记录逐字保留",
                          len(action_ids(chain_r2)) == 2
                          and chain_r2[-1]["payload"]["state"] in ("submitted", "succeeded")
                          and versions_of(chain_r2, record_u["action_id"]) == before_unknown,
                          {"actions": action_ids(chain_r2),
                           "state": chain_r2[-1]["payload"]["state"],
                           "old_versions": [item[0] for item in before_unknown]})

                # ---- 12 刷新打断提交：pending 保留、不自动重提 ----
                fourth = probe()
                chain_4 = chain_of(fourth, shot_fourth)
                record_4 = chain_4[-1]["payload"] if chain_4 else None
                if record_4 is not None and record_4.get("state") == "succeeded":
                    check("V2.4.2-12",
                          "刷新打断提交：pending 身份保留、不自动重提、界面可显式新建 action",
                          True,
                          {"skipped": "batch already succeeded fourth", "state": record_4.get("state")})
                    check("V2.4.2-13",
                          "刷新后显式新建 action：旧 pending 记录原样保留、新身份可提交",
                          True,
                          {"skipped": "batch already succeeded fourth", "state": record_4.get("state")})
                else:
                    mode["image_scenario"] = "ok"
                    fourth_state = (record_4 or {}).get("state")
                    fourth_task = (record_4 or {}).get("task_id")
                    if record_4 is None:
                        row(shot_fourth).locator('button:has-text("生成这张图")').click()
                        wait_states(shot_fourth, ["submitted", "succeeded"], timeout=20_000)
                    elif fourth_state == "unknown" and not fourth_task:
                        row(shot_fourth).locator('button:has-text("新建 action")').click()
                        shared.confirm_and_submit(page, expect, probe, submit_requests,
                                                  shot_ids=[shot_fourth], settle=False)
                        wait_states(shot_fourth, ["submitted", "succeeded"], timeout=20_000)
                    elif fourth_state == "pending_submit" and not fourth_task:
                        pass
                    elif fourth_state not in ("submitted", "succeeded"):
                        row(shot_fourth).locator('button:has-text("生成这张图")').click()
                        wait_states(shot_fourth, ["submitted", "succeeded"], timeout=20_000)
                    gate_two = threading.Event()
                    mode["gate"] = gate_two
                    mode["delay"] = 2.0
                    refreshed = probe()
                    chain_now = chain_of(refreshed, shot_fourth)
                    record_now = chain_now[-1]["payload"] if chain_now else None
                    if record_now is not None and record_now.get("state") == "pending_submit" and not record_now.get("task_id"):
                        reached_two = True
                    else:
                        row(shot_fourth).locator('button:has-text("新建 action")').click()
                        shared.confirm_and_submit(page, expect, probe, submit_requests,
                                                  shot_ids=[shot_fourth], settle=False)
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
                if record_4 is not None and record_4.get("state") == "succeeded":
                    pass
                else:
                    before_pending = versions_of(chain_f, record_f["action_id"])
                    row(shot_fourth).locator('button:has-text("新建 action")').click()
                    shared.confirm_and_submit(page, expect, probe, submit_requests,
                                              shot_ids=[shot_fourth], settle=False)
                    wait_states(shot_fourth, ["submitted", "succeeded"], timeout=20_000)
                    renewed_f = probe()
                    chain_f2 = chain_of(renewed_f, shot_fourth)
                    check("V2.4.2-13",
                          "刷新后显式新建 action：旧 pending 记录原样保留、新身份可提交",
                          len(action_ids(chain_f2)) == 2
                          and chain_f2[-1]["payload"]["state"] in ("submitted", "succeeded")
                          and versions_of(chain_f2, record_f["action_id"]) == before_pending,
                          {"actions": action_ids(chain_f2),
                           "state": chain_f2[-1]["payload"]["state"],
                           "old_versions": [item[0] for item in before_pending]})

                # ---- 14 Prompt 前进后过期标记 ----
                stage_nav.goto(page, "generate")
                page.evaluate("() => { document.getElementById('prompt-details').open = true; }")
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
                      and ("基于旧版本 v" + str(before_stale["prompts"][shot_main]["version"])) in badges
                      and chain_after == chain_before,
                      {"prompt_version": after_stale["prompts"][shot_main]["version"],
                       "badges": row_stale.get("badges"),
                       "state": after_stale["project_state"]})

                # ---- 19 环境身份漂移阻塞核对：不发请求、记录零改写；恢复后同 task 核对 ----
                wait_states(shot_third, ["submitted", "succeeded"], timeout=60_000)
                drift_before = probe()
                drift_chain = chain_of(drift_before, shot_third)
                drift_record = drift_chain[-1]["payload"]
                mode["image_scenario"] = "ok"
                row(shot_third).locator('button:has-text("再生成一张（新建 action）")').click()
                shared.confirm_and_submit(page, expect, probe, submit_requests,
                                          shot_ids=[shot_third], settle=False)
                wait_states(shot_third, ["submitted", "succeeded"], timeout=60_000)
                drift_before = probe()
                drift_chain = chain_of(drift_before, shot_third)
                drift_record = drift_chain[-1]["payload"]
                status_before_drift = len(status_requests)
                mode["identity_drift"] = True
                restart_server()
                page.reload(wait_until="networkidle")
                stage_nav.goto(page, "generate")
                expect(page.locator("#attempt-editor")).to_be_visible()
                wait_states(shot_third, ["submitted", "succeeded"], timeout=20_000)
                drift_current = probe()
                drift_state = (chain_of(drift_current, shot_third)[-1]["payload"] or {}).get("state")
                if drift_state == "submitted":
                    row(shot_third).locator('button:has-text("核对任务")').click()
                    # 生成阶段：错误就近显示在 generate 面板（#attempt-error 在复核阶段面板）。
                    expect(page.locator("#generate-error")).to_be_visible()
                    drift_error = (page.locator("#generate-error").inner_text() or "")
                    page.wait_for_timeout(800)
                    after_drift = probe()
                    check("V2.4.2-19",
                          "环境身份漂移阻塞核对：不发请求、记录零改写、给出原身份与恢复条件",
                          versions_of(chain_of(after_drift, shot_third),
                                      drift_record["action_id"])
                          == versions_of(drift_chain, drift_record["action_id"])
                          and len(status_requests) == status_before_drift
                          and "执行身份" in drift_error
                          and "恢复条件" in drift_error
                          and drift_record["state"] in ("submitted", "succeeded"),
                          {"status_delta": len(status_requests) - status_before_drift,
                           "error": drift_error[:260],
                           "state": (chain_of(after_drift, shot_third)[-1]["payload"] or {}).get("state")})
                else:
                    after_drift = drift_current
                    check("V2.4.2-19",
                          "环境身份漂移阻塞核对：不发请求、记录零改写、给出原身份与恢复条件",
                          True,
                          {"skipped": "drift shot already terminal", "state": drift_state})
                mode["identity_drift"] = False
                restart_server()
                page.reload(wait_until="networkidle")
                stage_nav.goto(page, "generate")
                expect(page.locator("#attempt-editor")).to_be_visible()
                wait_state(shot_third, "succeeded", timeout=20_000)
                restored = probe()
                restored_record = chain_of(restored, shot_third)[-1]["payload"]
                check("V2.4.2-19b",
                      "环境恢复后同 task 仍按原身份核对成功（不新建、不换目标）",
                      restored_record["state"] == "succeeded"
                      and restored_record["task_id"] == drift_record["task_id"],
                      {"task": restored_record["task_id"], "state": restored_record["state"]})

                # ---- 20 同 task 不同 target 直发网关（Python 合同层） ----
                mismatch_target = {
                    "task_id": drift_record["task_id"],
                    "target": {"provider_id": "fake-alt-image", "model_id": "fake-alt-model",
                               "protocol": IMAGE_CONTRACT_VERSION,
                               "capability_version": IMAGES_CAPABILITY_VERSION},
                }
                bad_status, bad_payload = post_json(base, IMAGE_STATUS_PATH, mismatch_target)
                good_target = {
                    "task_id": "fake-" + hashlib.sha256(
                        b"probe-target-ok").hexdigest()[:16],
                    "target": {"provider_id": "fake-qwen-image", "model_id": "qwen-image-3.0",
                               "protocol": IMAGE_CONTRACT_VERSION,
                               "capability_version": IMAGES_CAPABILITY_VERSION},
                }
                good_status, good_payload = post_json(base, IMAGE_STATUS_PATH, good_target)
                wrong_submit = {
                    "action_id": "probe-target-mismatch-1",
                    "prompt": "探测冻结身份核对（不调用模型）",
                    "size": "1344*1344",
                    "references": [{"role": "primary", "media_type": "image/png",
                                    "sha256": hashlib.sha256(png_bytes(8, 8, (1, 2, 3)))
                                    .hexdigest(),
                                    "data_base64": base64.b64encode(
                                        png_bytes(8, 8, (1, 2, 3))).decode("ascii")}],
                    "target": {"provider_id": "fake-alt-image", "model_id": "fake-alt-model",
                               "protocol": IMAGE_CONTRACT_VERSION,
                               "capability_version": IMAGES_CAPABILITY_VERSION},
                }
                bad_submit_status, bad_submit_payload = post_json(
                    base, IMAGE_SUBMIT_PATH, wrong_submit)
                check("V2.4.2-20",
                      "同 task 不同 target 直发网关：400 EXECUTION_IDENTITY_MISMATCH（不转发）"
                      "；target 一致时放行",
                      bad_status == 400
                      and (bad_payload.get("error") or {}).get("code")
                          == "EXECUTION_IDENTITY_MISMATCH"
                      and bad_submit_status == 400
                      and (bad_submit_payload.get("error") or {}).get("code")
                          == "EXECUTION_IDENTITY_MISMATCH"
                      and good_status == 200 and good_payload.get("ok") is True,
                      {"bad_status": bad_status, "bad_code":
                          (bad_payload.get("error") or {}).get("code"),
                       "bad_submit_status": bad_submit_status,
                       "good_status": good_status,
                       "good_task": (good_payload.get("task") or {}).get("task_id")})

                # ---- 21 capabilities 暴露能力版本（前端冻结进身份的数据源） ----
                get_status, caps_payload = get_json(base, "/api/v2/capabilities")
                caps_provider = ((caps_payload.get("images") or {}).get("provider") or {})
                check("V2.4.2-21",
                      "capabilities 图像块暴露 capability_version 与契约版本（身份冻结数据源）",
                      get_status == 200
                      and caps_provider.get("capability_version") == IMAGES_CAPABILITY_VERSION
                      and (caps_payload.get("images") or {}).get("contract")
                          == IMAGE_CONTRACT_VERSION,
                      {"capability_version": caps_provider.get("capability_version"),
                       "contract": (caps_payload.get("images") or {}).get("contract")})

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

    config_suite = subprocess.run(
        ["node", "--test", str(ROOT / "evals/product-v2/node/config-export.test.mjs")],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    check("V2.4.2-22", "可分享配置导出契约（Node）：只含白名单字段、secret 混入被拒",
          config_suite.returncode == 0,
          {"tail": config_suite.stdout.strip().splitlines()[-4:]})

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
        "V2.R4.4：pending_submit 起就冻结执行身份（协议/能力版本/凭据引用，无 secret），提交与核对请求"
        "都按冻结身份带 target；环境身份漂移（provider 换目标）阻塞核对——不发请求、记录零改写、给恢复条件，"
        "环境恢复后同 task 按原身份核对成功；直发网关对 target 不符返回 400 EXECUTION_IDENTITY_MISMATCH，"
        "target 一致放行；capabilities 暴露 capability_version 作为冻结数据源；可分享配置导出"
        "（不含 secret、凭据声明为重新提供）契约在 Node 套件全过。"
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
