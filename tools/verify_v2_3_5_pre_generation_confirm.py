#!/usr/bin/env python
"""V2.3.5 证据：生成前确认与外发资料摘要（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 全部通过 node --check（ESM 语法门）。
  2) 契约套件 H01..H12 在真实 Chromium 全过（确定性、摘要一致、缺 Prompt / 过期 / 缺依赖 /
     Provider / 平台 / 参考图越界阻断、风险传播、确认记录与失效判定、反向探针）。
  3) 正式入口：套图就绪后「生成前确认」解锁，4 张图因缺 Prompt 全部阻断并定位到 Prompt 区。
  4) 缺依赖的对比图被精确阻断并定位到套图规划；删除后恢复。
  5) 编译全部图后可确认；点击确认写入 generation_confirm v1，界面、记录与重算指纹一致，状态前进。
  6) 改公共风格：确认失效、状态回落 PLAN_REVIEW，界面显示原因。
  7) 重编译后确认单恢复可提交形状，但摘要按不自动重提拒绝复发旧图：按钮禁用并标注
     “确认并生成 0 张”，确认记录保持 v1 单版本（无新授权即无新版本，不伪造 v2）。
     产品合同：generation-view.ts:565-567（状态文案声明不自动重提）、652-653（按 sending.total
     渲染计数）、649（can_submit 为假即禁用）；generation.ts:960-973（initial 模式下已有成功
     记录的图从确认队列剔除）、952-957（无冻结目标的授权无 pending）。
  8) 刷新恢复：确认记录 v1、指纹与存储一致，按钮保持禁用（仍无可发送的新任务）。
  9) 零 console error / page error；截图落盘；正式入口 --check 与既有套件仍全过。

运行：
  uv run --locked python tools/verify_v2_3_5_pre_generation_confirm.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
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
import v2_verify_shared as shared  # noqa: E402  （自动本地准备的等待口径与其它验证器一致）

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
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/confirm-contract.js",
]

EXPECTED_CASES = [f"H{index:02d}" for index in range(1, 13)]
NEGATIVE_CASES = ["H03", "H04", "H05", "H06", "H07", "H08", "H11", "H12"]

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
        critical: definition.critical, value, source: "user_input",
        status: "confirmed", confidence: null,
        evidence: [{ kind: "user", ref: "v235-seed" }], depends_on: [],
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
SEEN_SUMMARY_PROBE = """
async () => {
  // 所见摘要口径 = UI 意图口径（generation.ts:569-582 intentOf 按授权范围/批次队列过滤），
  // 不是 domain.buildConfirmationSheet 的全量口径：后者覆盖全部 promptEntries，
  // 进入 generate 自动准备（workspace.js:516 → generation-view.ts:374-408）后
  // 未编译时意图 sheet=None、全量 sheet 仍可阻塞 —— sheet 级断言不可靠，应断 UI DOM。
  const status = document.getElementById("confirm-status").textContent;
  const summary = document.getElementById("confirm-summary").textContent;
  const blockers = document.getElementById("confirm-blockers").textContent;
  const risks = document.getElementById("confirm-risks").textContent;
  const action = document.getElementById("confirm-action");
  const rows = [...document.querySelectorAll("#confirm-list .confirm-shot")].map((node) => ({
    shot_id: node.getAttribute("data-shot-id"),
    blocked: node.getAttribute("data-blocked"),
    text: node.textContent,
  }));
  // 意图摘要计数 = 本批可发送张数（generation-view.ts:565-567“本次明确发送 N 张”；
  // 652-653 按 sending.total 渲染按钮计数；649 can_submit 为假即禁用）。
  const sendingMatch = /本次明确发送\\s*(\\d+)\\s*张/.exec(status || "");
  const actionMatch = /([0-9]+)\\s*张/.exec((action || {}).textContent || "");
  return {
    status: status,
    summary: summary,
    blockers: blockers,
    risks: risks,
    action_disabled: action ? action.disabled : null,
    action_text: action ? action.textContent : "",
    sending_count: sendingMatch ? Number(sendingMatch[1]) : null,
    action_count: actionMatch ? Number(actionMatch[1]) : null,
    rows: rows,
    row_count: rows.length,
    sending_rows: rows.filter((row) => (row.text || "").includes("本次发送")).map((row) => row.shot_id),
    blocked_rows: rows.filter((row) => String(row.blocked || "").toLowerCase() === "true")
      .map((row) => row.shot_id),
    stale_rows: rows.filter((row) => (row.text || "").includes("本次不重复提交")).map((row) => row.shot_id),
  };
}
"""
CONFIRM_PROBE = """
async (input) => {
  const scope = input && Array.isArray(input.shotIds) && input.shotIds.length > 0
    ? [...input.shotIds] : null;
  const domain = await import("/domain/index.js");
  const storage = await import("/storage/db.js");
  // 有效图像 Prompt 档必须与服务端当前能力一致：直接从 capabilities 投影，不复制常量。
  const capabilities = await (await fetch("/api/v2/capabilities")).json();
  const imageProfile = domain.imagePromptProfile(capabilities.images);
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const readAll = (store) => new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await readAll("documents");
  const projects = await readAll("projects");
  const assets = await readAll("assets");
  db.close();
  const rows = (kind) => documents.filter((item) => item.kind === kind);
  const latest = (kind, documentId) => rows(kind)
    .filter((item) => documentId === undefined || item.document_id === documentId)
    .sort((left, right) => right.version - left.version)[0] || null;
  const plan = latest("suite_plan", "suite");
  if (!plan) return { plan: null };
  const slots = [...new Map(rows("fact_slot").map((item) => [item.document_id, item])).values()];
  const briefBasis = slots.map((item) => ({ slot_id: item.document_id, version: item.version }));
  const styleRow = latest("style_spec", "style");
  const confirmRows = rows("generation_confirm").sort((left, right) => left.version - right.version);
  const confirmRow = confirmRows.length > 0 ? confirmRows[confirmRows.length - 1] : null;
  const promptRows = rows("prompt_version");
  const entries = [...new Map(promptRows.map((item) => [item.document_id, item])).values()]
    .map((item) => ({ shot_id: item.document_id, record: item.payload, version: item.version }));
  const promptIdentityByShot = {};
  for (const item of promptRows) {
    const current = promptIdentityByShot[item.document_id];
    if (!current || item.version > current.version) {
      promptIdentityByShot[item.document_id] = {
        version: item.version, hash: item.payload ? item.payload.hash : null,
        text: item.payload && item.payload.compiled ? item.payload.compiled.text : null,
      };
    }
  }
  const attemptRows = rows("generation_attempt");
  const attemptsByShot = {};
  for (const item of attemptRows) {
    (attemptsByShot[item.document_id] = attemptsByShot[item.document_id] || []).push({
      version: item.version,
      action_id: item.payload ? item.payload.action_id : null,
      state: item.payload ? item.payload.state : null,
      task_id: item.payload ? (item.payload.task_id || null) : null,
      prompt_version: item.payload && item.payload.prompt ? item.payload.prompt.version : null,
      prompt_hash: item.payload && item.payload.prompt ? item.payload.prompt.hash : null,
      authorization: item.payload ? (item.payload.authorization || null) : null,
      references: item.payload ? (item.payload.references || []) : [],
    });
  }
  for (const key of Object.keys(attemptsByShot)) {
    attemptsByShot[key].sort((left, right) => left.version - right.version);
  }
  const intake = latest("product_input", "intake");
  const basisByShot = {};
  for (const shot of plan.payload.shots) {
    const spec = latest("shot_spec", shot.shot_id);
    basisByShot[shot.shot_id] = {
      briefBasis,
      // 这张图自己的签名必须一起给：prompt.js 的 promptStaleness 在调用方提供签名时只比
      // 签名 + style/spec（改别的图不让这张图过期）；漏掉它就会退回整份 suite_version 比较，
      // 把产品认为当前的 Prompt 假判成过期。
      shot_signature: domain.shotSignatureOf(shot),
      suite_version: plan.version,
      style_version: styleRow ? styleRow.version : null,
      shot_spec_version: spec ? spec.version : null,
      platform: { version: domain.PLATFORM_PROFILES.amazon_us.version },
      provider: imageProfile,
    };
  }
  const sheet = domain.buildConfirmationSheet({
    suitePlan: plan.payload,
    promptEntries: entries,
    context: {
      facts: slots.map((item) => ({ slot_id: item.document_id, status: item.payload.status, value: item.payload.value })),
      assets: ((intake && intake.payload.references) || []).map((item) => ({ role: item.role, sha256: item.asset_sha256 })),
    },
    currentBasisByShot: basisByShot,
    providerProfile: imageProfile,
    ...(scope ? { shotIds: scope } : {}),
  });
  // 指纹与失效判据都按产品同一构造：执行身份从服务端正式能力块现算
  // （attemptCurrentEnvironmentIdentity 只读非秘密身份），动作类型按本入口的 initial。
  const environmentIdentity = domain.attemptCurrentEnvironmentIdentity(capabilities.images);
  const snapshot = domain.confirmationSnapshot(sheet, {
    executionIdentity: environmentIdentity, submissionMode: "initial",
  });
  const staleness = confirmRow ? domain.confirmationStaleness(confirmRow.payload, snapshot) : null;
  const recomputedHash = confirmRow ? await domain.promptHash(snapshot, { digest: storage.sha256Hex }) : null;
  const project = projects.slice().sort((left, right) =>
    String(right.updated_at || "").localeCompare(String(left.updated_at || "")))[0] || null;
  return {
    sheet: sheet,
    plan_shots: plan.payload.shots.map((shot) => ({ shot_id: shot.shot_id, role_id: shot.role_id })),
    text_roles: [...domain.PLATFORM_PROFILES.amazon_us.on_image_text_roles],
    staleness: staleness,
    environment_identity: environmentIdentity,
    recorded_target: confirmRow ? (confirmRow.payload.fingerprint.snapshot.execution_target || null) : null,
    recomputed_hash: recomputedHash,
    record: confirmRow ? { version: confirmRow.version, payload: confirmRow.payload } : null,
    confirm_rows: confirmRows.map((item) => ({ version: item.version,
      hash: item.payload.fingerprint ? item.payload.fingerprint.hash : null,
      shots: Array.isArray(item.payload.shots)
        ? item.payload.shots.map((shot) => ({ shot_id: shot.shot_id, prompt_version: shot.prompt_version,
          prompt_hash: shot.prompt_hash })) : [] })),
    prompt_versions: entries.map((item) => ({ shot_id: item.shot_id, version: item.version, hash: item.record.hash })),
    prompt_identities: promptIdentityByShot,
    attempts_by_shot: attemptsByShot,
    reference_asset_shas: assets.map((item) => item.sha256),
    project_state: project ? project.state : null,
    ui: {
      status: document.getElementById("confirm-status").textContent,
      record: document.getElementById("confirm-record").textContent,
      summary: document.getElementById("confirm-summary").textContent,
      blockers: document.getElementById("confirm-blockers").textContent,
      risks: document.getElementById("confirm-risks").textContent,
      action_disabled: document.getElementById("confirm-action").disabled,
      action_text: document.getElementById("confirm-action").textContent,
      rows: [...document.querySelectorAll("#confirm-list .confirm-shot")].map((node) => ({
        shot_id: node.getAttribute("data-shot-id"),
        blocked: node.getAttribute("data-blocked"),
        text: node.textContent,
      })),
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




def run_entry(args: list[str], timeout: int = 180) -> dict:
    import os as _os
    env = {**_os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "app" / "server.py"), *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )
    return {"args": args, "rc": completed.returncode,
            "tail": (completed.stdout + completed.stderr).strip().splitlines()[-8:]}


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
        if path in ("/", "/index.html"):
            self._send((HARNESS_DIR / "confirm-contract.html").read_bytes(), MIME[".html"])
            return
        if path.startswith("/harness/"):
            candidate = (HARNESS_DIR / path[len("/harness/"):]).resolve()
            if str(candidate).startswith(str(HARNESS_DIR.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(), MIME.get(candidate.suffix, "application/octet-stream"))
                return
        else:
            candidate = (PRODUCT_DIR / path.lstrip("/")).resolve()
            if str(candidate).startswith(str(PRODUCT_DIR.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(), MIME.get(candidate.suffix, "application/octet-stream"))
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


def wait_prepare_settled(page, timeout: int = 60_000) -> None:
    # 到达等待：只等“自动本地准备落定 + 确认区按新版本重渲染”（行为状态门），
    # 不断言任何版本数字/源码位置：版本前进幅度由 prompts.prepare/compileAndSave 决定
    # （自动准备可能已前进多次；force 重准备可能再前进），写死 v2/+1 会把合法语义判红。
    # 保存→renderPrompts/renderConfirm→deriveState 是异步链（generation-view.ts:458-463），
    # 必须等到确认区重渲染后才返回，否则调用方读到的仍是旧 sheet。
    page.wait_for_function(
        """() => {
          const cards = [...document.querySelectorAll('#prompt-list .shot-spec[data-shot-id]')];
          if (!cards.length) return false;
          if (!cards.every((node) => ['saved', 'stale'].includes(node.dataset.promptState))) return false;
          const status = document.getElementById('confirm-status');
          return Boolean(status && status.textContent.includes('本次明确发送'));
        }""",
        timeout=timeout)


def compile_all(page, shot_ids: list, wait_ms: int = 200, *, force: bool = False) -> None:
    # 本地实现只保留“怎么到达”：真实等待与点击语义归 shared.compile_all
    # （等待自动本地准备落定、只重准备过期图；force=True 用于“改风格后必须出新版本”
    # 的显式重准备场景——此时 stable saved 可能是“新依据下仍有效但版本未前进”的旧版）。
    # 返回后统一等确认区重渲染落定；版本前进不断言具体数字（见 wait_prepare_settled）。
    shared.compile_all(page, shot_ids, wait_ms=wait_ms, force=force)
    wait_prepare_settled(page)



def main() -> int:
    parser = argparse.ArgumentParser(description="V2.3.5 生成前确认验证")
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
    check("V2.3.5-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"],
          {"failed": [item for item in node_result["files"] if item["rc"] != 0][:3]})

    static_server, static_url = start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["confirm"] = read_suite(
                    browser, static_url + "/harness/confirm-contract.html",
                    "__V2_CONFIRM_RESULTS__", console_errors, page_errors)
                suites["prompt"] = read_suite(
                    browser, static_url + "/harness/prompt-contract.html",
                    "__V2_PROMPT_RESULTS__", console_errors, page_errors)
                suites["specs"] = read_suite(
                    browser, static_url + "/harness/specs-contract.html",
                    "__V2_SPECS_RESULTS__", console_errors, page_errors)
                suites["suite_editor"] = read_suite(
                    browser, static_url + "/harness/suite-editor-contract.html",
                    "__V2_SUITE_EDITOR_RESULTS__", console_errors, page_errors)
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    suite = suites["confirm"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.3.5-01", "H01–H12 契约套件全过且用例齐全",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")} for item in failed_cases[:3]]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.3.5-02", "反向探针确实执行（缺 Prompt / 过期 / 缺依赖 / 参数不符 / 越界 / 失效）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "confirm"}
    check("V2.3.5-02b", "既有契约套件回归：Prompt / 规格 / 套图编辑器全过",
          all(item["status"] == "passed" and not item["failed"] for item in regression.values()),
          regression)

    module = load_server_module()
    from src.providers.v2_fake_image import FakeImageProvider  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    # TOCTOU 说明：产品服务器直接绑 0 号端口并从 server_address 读回实际端口，
    # 不用 free_port() 先探测（Windows 上已被抢占的端口仍可静默绑定成功，
    # 无人应答即 ERR_CONNECTION_REFUSED 假红；见 4_4 load_page/boot_retries 同源证据）。
    # Harness 静态服 start_static_server() 本就绑 0（见本文件 :282），不受影响。
    server = module.create_product_v2_server(
        "127.0.0.1", 0, provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"))
    # 工厂只建服务器不启动；少了这一行页面拿不到响应，异常又会被下面 finally 的
    # server.shutdown() 永久阻塞吞掉（无输出、无证据、无 traceback）。与 3_6 同形。
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    submit_requests: list[dict] = []
    ui: dict = {}
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v235-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            def on_request(request) -> None:
                if request.method == "POST" and "/api/v2/images/submit" in request.url:
                    try:
                        body = json.loads(request.post_data or "{}")
                    except ValueError:
                        body = {}
                    submit_requests.append({"action_id": body.get("action_id"),
                                            "prompt": body.get("prompt")})

            page.on("request", on_request)

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品 · 生成前确认")
            page.click("#create-project")
            expect(page.locator("#project-view")).to_be_visible()
            # 确认区在生成阶段面板内：先切到生成区再判空态（阶段条始终可达）。
            stage_nav.goto(page, "generate")
            expect(page.locator("#confirm-editor")).to_be_hidden()
            # UI 合同§3导航规则:阶段条始终可达,不锁死;「未就绪」由区内空态表达。
            expect(page.locator('#stage-nav [data-stage-nav="generate"]')).to_be_enabled()
            expect(page.locator("#confirm-locked")).to_be_visible()
            # 参考图与商品资料在资料阶段面板内：切回资料区再操作。
            stage_nav.goto(page, "intake")
            page.set_input_files("#ref-file", str(reference))
            expect(page.locator("#ref-list .ref-row")).to_have_count(1)
            page.fill("#intake-name", "便携保温杯")
            page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
            page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
            page.wait_for_timeout(1200)
            opened = page.evaluate(
                "async () => { const db = await new Promise((resolve) => {"
                " const request = indexedDB.open(\"amz-listing-kit-v2\");"
                " request.onsuccess = () => resolve(request.result); });"
                " const rows = await new Promise((resolve) => { const req = db.transaction(\"projects\", \"readonly\")"
                " .objectStore(\"projects\").getAll(); req.onsuccess = () => resolve(req.result); });"
                " db.close(); return rows.map((item) => item.project_id); }")
            page.evaluate(SEED_SLOTS, opened[0])
            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "plan")
            page.click("#suite-seed")
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            stage_nav.goto(page, "generate")
            wait_prepare_settled(page)
            expect(page.locator("#confirm-editor")).to_be_visible()
            expect(page.locator("#confirm-locked")).to_be_hidden()
            expect(page.locator("#confirm-list .confirm-shot")).to_have_count(4)
            first = page.evaluate(CONFIRM_PROBE, {"shotIds": None})
            seen = page.evaluate(SEEN_SUMMARY_PROBE)
            # 进入 generate 自动准备系统 Prompt（workspace.js:516 → generation-view.ts:374-408；
            # ui-contract §4.6“打开生成区仅对缺失/过期的系统文本准备版本”，人工文本不覆盖）：
            # 旧“4 张缺 Prompt 全部阻断”期望已过期。改为所见摘要口径（UI 意图口径）：
            # 实际 4 张已就绪 → 所见“本次明确发送 4 张”、按钮可用、逐图行“本次发送”。
            check("V2.3.5-03", "套图就绪后确认区解锁：所见摘要 4 张可发送（自动准备已就绪）",
                  seen["sending_count"] == 4 and seen["action_count"] == 4
                  and first["ui"]["action_disabled"] is False
                  and "本次明确发送 4 张" in seen["status"]
                  and seen["row_count"] == 4
                  and len(seen["sending_rows"]) == 4
                  and not seen["blocked_rows"]
                  and "参考" in seen["summary"],
                  {"status": seen["status"], "sending": seen["sending_rows"],
                   "summary": seen["summary"][:200]})

            stage_nav.goto(page, "plan")
            page.select_option("#suite-template", "comparison_competitor")
            page.click("#suite-add-template")
            expect(page.locator("#shot-list .shot-row")).to_have_count(5)
            expect(page.locator('#shot-list .shot-row[data-blocked="true"]')).to_have_count(1)
            blocked_probe = page.evaluate(CONFIRM_PROBE, {"shotIds": None})
            blocked_sheet = blocked_probe["sheet"]
            comparison = next(item for item in blocked_sheet["shots"]
                              if item["shot_id"] == "shot_comparison_competitor")
            comparison_codes = [blocker["code"] for blocker in comparison["blockers"]]
            dependency_fix = next(blocker["fix"] for blocker in comparison["blockers"]
                                  if blocker["code"] == "DEPENDENCY_UNSATISFIED")
            blocked_shots = [item["shot_id"] for item in blocked_sheet["shots"] if item["blockers"]]
            check("V2.3.5-04", "缺依赖的对比图被精确阻断并定位到套图规划",
                  blocked_sheet["total"] == 5
                  and blocked_shots == ["shot_comparison_competitor"]
                  and blocked_sheet["can_submit"] is False
                  and "DEPENDENCY_UNSATISFIED" in comparison_codes
                  and "PROMPT_MISSING" in comparison_codes
                  and dependency_fix["region"] == "suite"
                  and "套图规划" in blocked_probe["ui"]["blockers"],
                  {"codes": comparison_codes, "fix": dependency_fix,
                   "blocked_shots": blocked_shots,
                   "can_submit": blocked_sheet["can_submit"]})
            page.click('#shot-list .shot-row[data-shot-id="shot_comparison_competitor"] button:has-text("删除")')
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)

            stage_nav.goto(page, "generate")
            wait_prepare_settled(page)
            stage_nav.reveal(page, "#prompt-editor")
            page.wait_for_selector("#prompt-editor:not([hidden])", timeout=15_000)
            # 独立夹具身份：当前所见摘要的 4 张就是本轮授权集合（后续 -07 一一消费）。
            # 不再走“逐图编译推进 1/3”的旧假设（自动准备后已全部就绪，无需再编译）。
            ready_seen = page.evaluate(SEEN_SUMMARY_PROBE)
            authorized_scope = list(ready_seen["sending_rows"])
            # 重建单必须按本次授权范围（= 所见摘要的行集合）算，与产品记录指纹同一口径：
            # 全量口径会缺少 scope_shot_ids 且带上别的图，哈希与失效判据都对不上。
            ready_probe = page.evaluate(CONFIRM_PROBE, {"shotIds": authorized_scope})
            ready_rows = ready_probe["ui"]["rows"]
            ready_sheet = ready_probe["sheet"]
            blocked_problems = {item["shot_id"]: [b["code"] for b in item["blockers"]]
                                for item in ready_sheet["shots"] if item["blockers"]}
            blocked_messages = {item["shot_id"]: [b["message"] for b in item["blockers"]]
                                for item in ready_sheet["shots"] if item["blockers"]}
            check("V2.3.5-05", "所见摘要即本次授权集合：4 张就绪、外发摘要与所见一致",
                  ready_seen["sending_count"] == 4 and ready_seen["action_count"] == 4
                  and ready_seen["row_count"] == 4 and len(authorized_scope) == 4
                  and all((row["blocked"] or "").lower() == "false" for row in ready_rows)
                  and all("本次发送" in row["text"] for row in ready_rows)
                  and ready_sheet["can_submit"] is True
                  and ready_sheet["blocked"] == 0
                  and "参考" in ready_seen["summary"],
                  {"scope": authorized_scope, "status": ready_seen["status"],
                   "summary": ready_seen["summary"][:200],
                   "counts": [ready_seen["sending_count"], ready_seen["action_count"],
                              ready_seen["row_count"]],
                   "row_blocked": [row["shot_id"] for row in ready_rows
                                   if (row["blocked"] or "").lower() != "false"],
                   "row_text_ok": all("本次发送" in row["text"] for row in ready_rows),
                   "can_submit": ready_sheet["can_submit"],
                   "sheet_blocked": ready_sheet["blocked"],
                   "sheet_problems": blocked_problems,
                   "sheet_messages": blocked_messages,
                   "blockers_area": ready_probe["ui"]["blockers"][:300],
                   "row_texts": [row["text"][:120] for row in ready_rows]})

            ready = page.evaluate(CONFIRM_PROBE, {"shotIds": authorized_scope})
            ready_risks = [risk["code"] for risk in ready["sheet"]["risks"]]
            ready_seen2 = page.evaluate(SEEN_SUMMARY_PROBE)
            check("V2.3.5-06", "可确认态：所见 4 张可发送、无阻断、风险仍可见、无确认记录",
                  ready_seen2["sending_count"] == 4 and ready_seen2["action_count"] == 4
                  and ready["ui"]["action_disabled"] is False
                  and "发送 4 张" in ready_seen2["status"]
                  and "确认并生成 4 张" in ready_seen2["action_text"]
                  and all((row["blocked"] or "").lower() == "false" for row in ready["ui"]["rows"])
                  and all("本次发送" in row["text"] for row in ready["ui"]["rows"])
                  and "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" in ready_risks
                  and ready["record"] is None and ready["confirm_rows"] == [],
                  {"status": ready_seen2["status"], "risks": ready_risks,
                   "action_text": ready_seen2["action_text"],
                   "action_disabled": ready["ui"]["action_disabled"],
                   "counts": [ready_seen2["sending_count"], ready_seen2["action_count"]],
                   "row_blocked": [row["shot_id"] for row in ready["ui"]["rows"]
                                   if (row["blocked"] or "").lower() != "false"],
                   "row_text_ok": all("本次发送" in row["text"] for row in ready["ui"]["rows"]),
                   "record": None if ready["record"] is None else ready["record"]["version"],
                   "confirm_rows": len(ready["confirm_rows"])})

            shot_texts = " ".join(row["text"] for row in ready["ui"]["rows"])
            prompt_warnings = page.evaluate(
                """() => [...document.querySelectorAll('#prompt-list .prompt-warning')]
                     .map((node) => node.textContent).join(" / ")""")
            check("V2.3.5-14",
                  "风险提示中文可读：逐图与 Prompt 卡不出现裸规则码，槽位 id 已本地化；"
                  "规则码只留在汇总区与悬浮标题",
                  "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" not in shot_texts
                  and "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" not in prompt_warnings
                  and "product_category" not in shot_texts
                  and "product_category" not in prompt_warnings
                  and "product_category" not in ready["ui"]["risks"]
                  and ("请人工确认" in shot_texts or "文案不是" in shot_texts),
                  {"prompt": prompt_warnings[:200], "risks": ready["ui"]["risks"][:200]})

            language_messages: dict[str, list[str]] = {}
            for risk in ready["sheet"]["risks"]:
                if risk["code"] != "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE":
                    continue
                language_messages.setdefault(risk["shot_id"], []).append(risk["message"])
            duplicate_counts = {shot: len(items) - len(set(items))
                                for shot, items in language_messages.items()}
            signature_messages = [message for items in language_messages.values()
                                  for message in items if "signature_features" in message]
            check("V2.3.5-15",
                  "同一槽位的语言风险按槽位去重：逐图只出现一条，多值（夹具 2 条）时给出条数",
                  bool(signature_messages)
                  and all(count == 0 for count in duplicate_counts.values())
                  and all("2 条" in message for message in signature_messages),
                  {"messages": signature_messages[:4], "duplicates": duplicate_counts})

            # V2.6.17：语言风险只对「允许图中文字」的角色成立 —— 场景图/细节图不排文字，
            # 报「图中将逐字保留原文」是误报；同时有文字的角色要给可操作建议。
            role_by_shot = {item["shot_id"]: item["role_id"] for item in ready["plan_shots"]}
            text_roles = set(ready["text_roles"])
            language_risks = [risk for risk in ready["sheet"]["risks"]
                              if risk["code"] == "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE"]
            false_positive = [risk for risk in language_risks
                              if role_by_shot.get(risk["shot_id"]) not in text_roles]
            actionable = [risk for risk in language_risks if "建议" in risk["message"]]
            check("V2.3.5-16",
                  "语言风险只出现在允许图中文字的角色（文字角色带可操作建议，无文字角色不误报）",
                  bool(language_risks) and not false_positive
                  and len(actionable) == len(language_risks),
                  {"false_positive": [risk["shot_id"] for risk in false_positive],
                   "roles": role_by_shot, "text_roles": sorted(text_roles),
                   "messages": [risk["message"] for risk in language_risks][:3]})

            # 本次授权集合 = 所见摘要的 4 张（-05 独立固定，不从全量 sheet 或按钮回声推导）。
            # 消费证明 = 新确认文档(version 1) + 每张图的新 action + 捕获请求一一对应
            # （shared.confirm_and_submit 已按本次授权的新消费落定：新确认/新 action/请求绑定）。
            gate = shared.confirm_and_submit(page, expect, None, submit_requests,
                                             shot_ids=authorized_scope)
            assert gate["ok"], f"确认必须产生本次授权的新消费：{gate['after_actions']}"
            submits = len(submit_requests)
            confirmed = page.evaluate(CONFIRM_PROBE, {"shotIds": authorized_scope})
            record = confirmed["record"]
            record_shots = ({item["shot_id"]: item for item in record["payload"]["shots"]}
                            if record else {})
            prompt_ids = confirmed["prompt_identities"]
            per_shot_ok = True
            per_shot_detail: dict = {}
            for shot_id in authorized_scope:
                chain = confirmed["attempts_by_shot"].get(shot_id, [])
                saved = record_shots.get(shot_id)
                current = prompt_ids.get(shot_id)
                # 授权记录的 prompt 身份必须等于本次提交时该图的当前 Prompt 身份
                # （generation.ts:1029-1034 按精确版本/hash 消费，不用最新头替换已确认版本）。
                bound = (saved is not None and current is not None
                         and saved["prompt_version"] == current["version"]
                         and saved["prompt_hash"] == current["hash"])
                # 该图必须有且仅有一条绑定本次确认版本的新 action（旧尝试行不能计为新发送；
                # 同一 action 的多次观察会各留一条 attempt 记录，所以按 action_id 去重计数）。
                fresh_actions = {entry["action_id"] for entry in chain
                                 if entry["authorization"] is not None
                                 and entry["authorization"].get("version") == 1}
                sent = [item for item in submit_requests
                        if item.get("action_id") in fresh_actions]
                ok_shot = bound and len(fresh_actions) == 1 and len(sent) == 1
                per_shot_detail[shot_id] = {
                    "bound": bound, "fresh_actions": sorted(fresh_actions),
                    "sent": len(sent),
                }
                per_shot_ok = per_shot_ok and ok_shot
            check("V2.3.5-07", "点击确认写入 generation_confirm v1 并整套提交：授权逐图消费、各提交一次",
                  record is not None and record["version"] == 1
                  and len(confirmed["confirm_rows"]) == 1
                  and record["payload"]["fingerprint"]["hash"] == confirmed["recomputed_hash"]
                  and confirmed["staleness"]["stale"] is False
                  and confirmed["project_state"] == "READY_TO_GENERATE"
                  and len(record["payload"]["shots"]) == 4
                  and set(record_shots) == set(authorized_scope)
                  and submits == 4 and per_shot_ok,
                  {"state": confirmed["project_state"],
                   "hash": record["payload"]["fingerprint"]["hash"][:12] if record else None,
                   "submits": submits, "per_shot": per_shot_detail,
                   "record_version": None if record is None else record["version"],
                   "record_shots": sorted(record_shots),
                   "confirm_rows": len(confirmed["confirm_rows"]),
                   "stale": None if confirmed["staleness"] is None
                   else confirmed["staleness"]["stale"],
                   "hash_match": None if record is None
                   else record["payload"]["fingerprint"]["hash"]
                   == confirmed["recomputed_hash"],
                   "environment_identity": confirmed["environment_identity"],
                   "recorded_target": confirmed["recorded_target"],
                   "stale_fields": None if confirmed["staleness"] is None
                   else [reason["field"] for reason in confirmed["staleness"]["reasons"]][:6]})

            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.fill("#style-background", "深灰无缝背景")
            page.click("#style-save")
            stage_nav.goto(page, "generate")
            stale = page.evaluate(CONFIRM_PROBE, {"shotIds": authorized_scope})
            stale_fields = [reason["field"] for reason in stale["staleness"]["reasons"]]
            stale_seen = page.evaluate(SEEN_SUMMARY_PROBE)
            # 查看摘要后编辑（风格前进）→ 所见已变：必须阻断陈旧发送且零新 POST。
            # 不直接点击（按钮按不自动重提已禁用是产品正确行为），而是证明：
            # 存储判失效 + 所见 0 张 + 捕获请求计数不增加（-07 的 submits 基线）。
            check("V2.3.5-08", "改公共风格使确认失效并回落 PLAN_REVIEW：所见 0 张、零新外发",
                  stale["staleness"]["stale"] is True
                  and any(field.startswith("shots.") for field in stale_fields)
                  and stale["project_state"] == "PLAN_REVIEW"
                  and stale["record"] is not None and stale["record"]["version"] == 1
                  and stale_seen["sending_count"] == 0 and stale_seen["action_count"] == 0
                  and stale_seen["action_disabled"] is True
                  and "不自动重提" in stale_seen["status"]
                  and len(submit_requests) == submits,
                  {"fields": stale_fields[:4], "state": stale["project_state"],
                   "seen": stale_seen["status"], "submits": len(submit_requests)})

            # 新语义下“改风格→重编译→再次确认”不产生任何外发：已提交授权仍登记在册，
            # 但第二批摘要是空集（旧批次队列已消费完），按钮按不自动重提保持禁用。
            # -10 因此不能再走“点击并期待 v2”的旧单批次流程；它现在证明三条新语义：
            # (1) UI 把空集诚实展示为“确认并生成 0 张”而不是静默无动作（generation-view.ts:652-653
            #     按 sending.total 渲染计数；565-567 行状态文案声明“已有成功、进行中或 Unknown 不自动重提”）；
            # (2) 确认记录保持 v1 单版本（append-only：无新授权即无新版本，不伪造 v2）；
            # (3) 要让按钮重新可用，唯一真实路径是显式另发新动作（不是第二次点击）。
            compile_all(page, [item["shot_id"] for item in stale["sheet"]["shots"]], force=True)
            reconfirm_ready = page.evaluate(CONFIRM_PROBE, {"shotIds": authorized_scope})
            reconfirm_seen = page.evaluate(SEEN_SUMMARY_PROBE)
            # 重编译后全量单恢复可提交形状，但 UI 意图仍拒绝复发旧图（已有成功不自动重提）：
            # 版本只断“相对提交前各自前进”（不写死 v2：自动准备+显式重准备可能前进多次）。
            pre_versions = {shot: prompt_ids[shot]["version"] for shot, prompt_ids
                            in [(shot_id, confirmed["prompt_identities"]) for shot_id in authorized_scope]}
            check("V2.3.5-09", "重新编译后全量单恢复可提交形状，但所见摘要拒绝复发旧图",
                  reconfirm_ready["sheet"]["can_submit"] is True
                  and all(item["version"] > pre_versions[item["shot_id"]]
                          for item in reconfirm_ready["prompt_versions"]
                          if item["shot_id"] in pre_versions)
                  and reconfirm_seen["sending_count"] == 0 and reconfirm_seen["action_count"] == 0,
                  {"versions": reconfirm_ready["prompt_versions"],
                   "seen": reconfirm_seen["status"]})

            # 到达与断言都在同一条真实用户路径上：等自动本地准备落定后直接读按钮与摘要。
            wait_prepare_settled(page)
            stage_nav.goto(page, "generate")
            expect(page.locator("#confirm-editor")).to_be_visible()
            refused = {
                "disabled": page.locator("#confirm-action").is_disabled(),
                "text": page.locator("#confirm-action").inner_text(),
                "status": page.locator("#confirm-status").inner_text(),
            }
            second_record = page.evaluate(CONFIRM_PROBE, {"shotIds": authorized_scope})
            # 成功后不自动重提：按钮禁用 + 确认记录保持 v1 单版本（无新授权即无新版本）；
            # 且零新 POST（submit_requests 仍是 -07 的 submits）。
            check("V2.3.5-10", "重编译后不自动重提：按钮禁用并标注发送 0 张，确认记录不伪造新版本、零新外发",
                  refused["disabled"] is True
                  and "0 张" in refused["text"]
                  and "不自动重提" in refused["status"]
                  and second_record["record"] is not None
                  and second_record["record"]["version"] == 1
                  and len(second_record["confirm_rows"]) == 1
                  and len(submit_requests) == submits,
                  {"refused": refused, "rows": second_record["confirm_rows"],
                   "submits": len(submit_requests)})

            screenshot_rel = f"evals/product-v2/v2.3.5-pre-generation-confirm-{stamp}.png"
            page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
            screenshots.append(screenshot_rel)

            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "generate")
            wait_prepare_settled(page)
            expect(page.locator("#confirm-editor")).to_be_visible()
            reloaded = page.evaluate(CONFIRM_PROBE, {"shotIds": authorized_scope})
            reloaded_seen = page.evaluate(SEEN_SUMMARY_PROBE)
            # 刷新恢复：确认记录 v1 + 逐图授权身份 + attempt 链与刷新前一致（历史保留），
            # 所见仍 0 张且按钮禁用（仍无可发送的新任务）；项目状态以派生结论为准，
            # 不写死 READY_TO_GENERATE（风格前进后确认已失效，派生可为 PLAN_REVIEW）。
            history_ok = (
                reloaded["record"] is not None and reloaded["record"]["version"] == 1
                and len(reloaded["confirm_rows"]) == 1
                and reloaded["record"]["payload"]["fingerprint"]["hash"]
                == confirmed["record"]["payload"]["fingerprint"]["hash"]
                and {item["shot_id"]: (item["prompt_version"], item["prompt_hash"])
                     for item in reloaded["record"]["payload"]["shots"]}
                == {item["shot_id"]: (item["prompt_version"], item["prompt_hash"])
                    for item in confirmed["record"]["payload"]["shots"]}
                and {shot: [(entry["action_id"], entry["state"])
                            for entry in reloaded["attempts_by_shot"].get(shot, [])]
                     for shot in authorized_scope}
                == {shot: [(entry["action_id"], entry["state"])
                            for entry in confirmed["attempts_by_shot"].get(shot, [])]
                     for shot in authorized_scope})
            check("V2.3.5-11", "刷新恢复：确认记录 v1 与授权历史一致，所见 0 张、按钮禁用、零新外发",
                  history_ok
                  and reloaded_seen["sending_count"] == 0 and reloaded_seen["action_count"] == 0
                  and reloaded["ui"]["action_disabled"] is True
                  and "0 张" in reloaded_seen["status"]
                  and len(reloaded["ui"]["rows"]) == 4
                  and len(submit_requests) == submits,
                  {"state": reloaded["project_state"],
                   "hash": reloaded["record"]["payload"]["fingerprint"]["hash"][:12]
                   if reloaded["record"] else None,
                   "seen": reloaded_seen["status"], "submits": len(submit_requests)})
            ui["final"] = {"record_version": reloaded["record"]["version"],
                           "fingerprint": reloaded["record"]["payload"]["fingerprint"]["hash"],
                           "state": reloaded["project_state"],
                           "external_summary": reloaded["sheet"]["external_summary"],
                           "prompt_versions": reloaded["prompt_versions"]}
            context.close()
    finally:
        server.shutdown()
        server.server_close()

    check("V2.3.5-12", "契约会话与 UI 会话零 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:5], "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.3.5-13", "正式入口自检仍全过（V2.3.5 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明生成前确认在真实浏览器里可核对、可定位、可失效：确认单由套图计划、每图 PromptVersion、参考图与"
        "平台/Provider 档确定性派生；缺 Prompt、记录非法、快照与文本不一致、平台/Provider 不符、参考图数量越界、"
        "依赖未满足与 Prompt 过期都会阻断并给出可操作位置（fix.region）；外发摘要只写真实会发送的模型参数与"
        "参考图角色 + sha256 前 12 位，不含图片字节；风险（语言不一致、平台覆盖、主图忽略文案）必须可见但允许确认；"
        "确认记录 append-only 并绑定指纹，上游或 Prompt 前进即失效、状态回落 PLAN_REVIEW，重新确认写新版本。"
        "全程 0 次真实模型调用，不发图、不生成候选、不证明出图质量；真实生成属于 Phase 4，审核与返工属于 Phase 5。"
    )
    report = {
        "task": "V2.3.5",
        "suite_id": "v2.3.5-confirm",
        "status": status,
        "finished_at": finished_at,
        "model_calls": 0,
        "checks": checks,
        "suites": suites,
        "ui_flow": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshots": screenshots,
        "boundary": boundary,
    }
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.3.5-pre-generation-confirm-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.5-pre-generation-confirm-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.5 pre-generation confirm",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 (offline domain + UI flow)",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
    ]
    if screenshots:
        lines.append("screenshot: " + screenshots[0])
    lines += ["", "CHECKS"]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False)[:600])
    lines += ["", "SUITE CASES"]
    for item in suite.get("cases", []):
        lines.append(f"- [{'PASS' if item.get('ok') else 'FAIL'}] {item.get('id')} {item.get('title')}")
        if not item.get("ok"):
            lines.append("  error: " + json.dumps(item.get("error"), ensure_ascii=False))
    for name, value in regression.items():
        lines.append(f"- [{'PASS' if value['status'] == 'passed' else 'FAIL'}] 回归 {name} "
                     f"({value['status']}, failed={value['failed']})")
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.3.5 生成前确认验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False)[:600])
    print(f"套件用例：{len(suite.get('cases', []))} 条，失败 {len(suite.get('failed_ids', []) or [])} 条")
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
