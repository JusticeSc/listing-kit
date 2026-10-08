#!/usr/bin/env python
"""V2.3.6 证据：Prompt 人工编辑版本（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 全部通过 node --check（ESM 语法门）。
  2) 契约套件 M01..M12 在真实 Chromium 全过（记录形状、逐字一致、hash 重算、版本链、
     语言降级提示、失效投影、过期与确认联动、篡改与非法输入反向探针）。
  3) 正式入口：套图就绪后 4 张图缺 Prompt 被阻断；编译全部后可确认，确认写 generation_confirm v1。
  4) 人工编辑主图：保存人工版本 v2，逐字生效、hash 与请求快照一致、失效投影只指向主图、
     旧版本保留、确认失效并回落 PLAN_REVIEW。
  5) 反向：空文本 / 未授权引用 / 主图新增文案都被拒，旧版本与草稿输入都保留。
  6) 编译另一张图触发重渲染时，未保存的编辑草稿仍然保留。
  7) 链式编辑 v3 可追溯（edited_from=v2、source_refs 含上一次编辑），重新确认写 v2 并回到 READY_TO_GENERATE。
  8) 刷新恢复：人工版本、理由、hash、失效提示与状态一致。
  9) 零 console error / page error；截图落盘；正式入口 --check 与既有套件仍全过。

运行：
  uv run --locked python tools/verify_v2_3_6_prompt_manual_edit.py
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
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/prompt-edit-contract.js",
]

EXPECTED_CASES = [f"M{index:02d}" for index in range(1, 13)]
NEGATIVE_CASES = ["M03", "M04", "M05", "M07", "M08", "M09", "M11", "M12"]

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
        evidence: [{ kind: "user", ref: "v236-seed" }], depends_on: [],
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
EDIT_PROBE = """
async () => {
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
  db.close();
  const rows = (kind) => documents.filter((item) => item.kind === kind);
  const latest = (kind, documentId) => rows(kind)
    .filter((item) => documentId === undefined || item.document_id === documentId)
    .sort((left, right) => right.version - left.version)[0] || null;
  const promptRows = (shotId) => rows("prompt_version").filter((item) => item.document_id === shotId)
    .sort((left, right) => left.version - right.version);
  const plan = latest("suite_plan", "suite");
  const slots = [...new Map(rows("fact_slot").map((item) => [item.document_id, item])).values()];
  const briefBasis = slots.map((item) => ({ slot_id: item.document_id, version: item.version }));
  const styleRow = latest("style_spec", "style");
  const intake = latest("product_input", "intake");
  const entries = [...new Map(rows("prompt_version").map((item) => [item.document_id, item]))
    .values()].map((item) => ({ shot_id: item.document_id, record: item.payload, version: item.version }));
  const basisByShot = {};
  for (const shot of (plan ? plan.payload.shots : [])) {
    const spec = latest("shot_spec", shot.shot_id);
    basisByShot[shot.shot_id] = {
      briefBasis: briefBasis,
      suite_version: plan ? plan.version : null,
      style_version: styleRow ? styleRow.version : null,
      shot_spec_version: spec ? spec.version : null,
      platform: { version: domain.PLATFORM_PROFILES.amazon_us.version },
      provider: imageProfile,
    };
  }
  let sheet = null;
  if (plan) {
    sheet = domain.buildConfirmationSheet({
      suitePlan: plan.payload,
      promptEntries: entries,
      context: {
        facts: slots.map((item) => ({ slot_id: item.document_id, status: item.payload.status, value: item.payload.value })),
        assets: ((intake && intake.payload.references) || []).map((item) => ({ role: item.role, sha256: item.asset_sha256 })),
      },
      currentBasisByShot: basisByShot,
      providerProfile: imageProfile,
    });
  }
  const confirmRows = rows("generation_confirm").sort((left, right) => left.version - right.version);
  const confirmRow = confirmRows.length > 0 ? confirmRows[confirmRows.length - 1] : null;
  const staleness = (confirmRow && sheet)
    ? domain.confirmationStaleness(confirmRow.payload, domain.confirmationSnapshot(sheet)) : null;
  const project = projects.slice().sort((left, right) =>
    String(right.updated_at || "").localeCompare(String(left.updated_at || "")))[0] || null;
  const mainRows = promptRows("shot_main_clean");
  const mainRow = mainRows.length > 0 ? mainRows[mainRows.length - 1] : null;
  const mainRecord = mainRow ? mainRow.payload : null;
  const recomputed = mainRecord
    ? await domain.promptHash(mainRecord.request_snapshot, { digest: storage.sha256Hex }) : null;
  const cards = [...document.querySelectorAll("#prompt-list .shot-spec")].map((node) => ({
    shot_id: node.getAttribute("data-shot-id"),
    state: node.getAttribute("data-prompt-state"),
    meta: node.querySelector(".shot-spec-head .meta") ? node.querySelector(".shot-spec-head .meta").textContent : null,
    badges: [...node.querySelectorAll(".badge")].map((badge) => badge.textContent),
    notes: [...node.querySelectorAll("p.meta")].map((item) => item.textContent).join(" | "),
    textarea: node.querySelector("textarea.prompt-edit-text")
      ? node.querySelector("textarea.prompt-edit-text").value : null,
    reason: node.querySelector("input.prompt-edit-reason")
      ? node.querySelector("input.prompt-edit-reason").value : null,
  }));
  const errorNode = document.getElementById("prompt-error");
  return {
    sheet: sheet,
    staleness: staleness,
    project_state: project ? project.state : null,
    confirm: confirmRow ? {
      version: confirmRow.version,
      hash: confirmRow.payload.fingerprint.hash,
      shots: confirmRow.payload.shots.map((item) => ({ shot_id: item.shot_id, prompt_version: item.prompt_version })),
    } : null,
    confirm_versions: confirmRows.map((item) => item.version),
    main: mainRecord ? {
      origin: mainRecord.origin || null,
      version: mainRow.version,
      hash: mainRecord.hash,
      recomputed: recomputed,
      reason: mainRecord.edit_reason || null,
      edited_from: mainRecord.edited_from || null,
      invalidation: mainRecord.invalidation || null,
      source_refs: mainRecord.compiled.source_refs,
      text: mainRecord.compiled.text,
      warnings: (mainRecord.compiled.warnings || []).map((item) => item.code),
      versions: mainRows.map((item) => ({
        version: item.version, origin: item.payload.origin || null, hash: item.payload.hash,
      })),
    } : null,
    prompt_counts: [...new Set(rows("prompt_version").map((item) => item.document_id))]
      .map((shotId) => ({ shot_id: shotId, count: promptRows(shotId).length })),
    ui: {
      status: document.getElementById("prompt-status").textContent,
      error: errorNode ? errorNode.textContent : "",
      error_hidden: errorNode ? errorNode.hidden : true,
      confirm_status: document.getElementById("confirm-status").textContent,
      confirm_record: document.getElementById("confirm-record").textContent,
      confirm_disabled: document.getElementById("confirm-action").disabled,
      cards: cards,
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
            self._send((HARNESS_DIR / "prompt-edit-contract.html").read_bytes(), MIME[".html"])
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


def compile_all(page, shot_ids: list, wait_ms: int = 200) -> None:
    stage_nav.reveal(page, "#prompt-editor")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.3.6 Prompt 人工编辑验证")
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
    check("V2.3.6-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"],
          {"failed": [item for item in node_result["files"] if item["rc"] != 0][:3]})

    static_server, static_url = start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["prompt_edit"] = read_suite(
                    browser, static_url + "/harness/prompt-edit-contract.html",
                    "__V2_PROMPT_EDIT_RESULTS__", console_errors, page_errors)
                suites["prompt"] = read_suite(
                    browser, static_url + "/harness/prompt-contract.html",
                    "__V2_PROMPT_RESULTS__", console_errors, page_errors)
                suites["confirm"] = read_suite(
                    browser, static_url + "/harness/confirm-contract.html",
                    "__V2_CONFIRM_RESULTS__", console_errors, page_errors)
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

    suite = suites["prompt_edit"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.3.6-01", "M01–M12 契约套件全过且用例齐全",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")} for item in failed_cases[:3]]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.3.6-02", "反向探针确实执行（非法输入 / 未授权引用 / 平台文字 / 篡改 / 失效）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "prompt_edit"}
    check("V2.3.6-02b", "既有契约套件回归：Prompt / 确认单 / 规格 / 套图编辑器全过",
          all(item["status"] == "passed" and not item["failed"] for item in regression.values()),
          regression)

    module = load_server_module()
    from src.providers.v2_fake_image import FakeImageProvider  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port, provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    ui: dict = {}
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v236-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))

    def card_of(snapshot: dict, shot_id: str) -> dict:
        return next(card for card in snapshot["ui"]["cards"] if card["shot_id"] == shot_id)

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品 · 人工编辑")
            page.click("#create-project")
            expect(page.locator("#project-view")).to_be_visible()
            # Prompt 区在生成阶段面板内：先切到生成区再判空态（阶段条始终可达）。
            stage_nav.goto(page, "generate")
            expect(page.locator("#prompt-editor")).to_be_hidden()
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
            expect(page.locator("#prompt-editor")).to_be_visible()
            expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
            locked = page.evaluate(EDIT_PROBE)
            check("V2.3.6-03", "套图就绪后 Prompt 区解锁：4 张图未编译、确认被阻断",
                   locked["sheet"]["blocked"] == 4 and locked["sheet"]["can_submit"] is False
                  and locked["ui"]["confirm_disabled"] is True
                  and all(card["state"] == "none" for card in locked["ui"]["cards"]),
                  {"blocked": locked["sheet"]["blocked"],
                   "confirm_status": locked["ui"]["confirm_status"][:120]})

            compile_all(page, [item["shot_id"] for item in locked["sheet"]["shots"]])
            ready = page.evaluate(EDIT_PROBE)
            check("V2.3.6-04", "编译全部 4 张：可提交、编辑区与理由输入出现、尚无人工编辑标记",
                  ready["sheet"]["can_submit"] is True and ready["ui"]["confirm_disabled"] is False
                  and all(card["state"] == "saved" for card in ready["ui"]["cards"])
                  and all(card["textarea"] for card in ready["ui"]["cards"])
                  and all(card["reason"] == "" for card in ready["ui"]["cards"])
                  and ready["main"]["origin"] is None and ready["main"]["version"] == 1,
                  {"state": ready["project_state"], "hash": ready["main"]["hash"][:12]})

            page.click("#confirm-action")
            confirmed = page.evaluate(EDIT_PROBE)
            check("V2.3.6-05", "点击确认写入 generation_confirm v1，状态前进 READY_TO_GENERATE",
                  confirmed["confirm"]["version"] == 1
                  and confirmed["project_state"] == "READY_TO_GENERATE"
                  and confirmed["staleness"]["stale"] is False
                  and len(confirmed["confirm"]["shots"]) == 4,
                  {"state": confirmed["project_state"], "hash": confirmed["confirm"]["hash"][:12]})

            edit_text = confirmed["main"]["text"] + "\n\n补充约束：商品标志必须位于正面中心，颜色与参考图保持逐字一致。"
            save_edit(page, "shot_main_clean", edit_text, "补充标志位置约束")
            edited = page.evaluate(EDIT_PROBE)
            main_card = card_of(edited, "shot_main_clean")
            fields = [reason["field"] for reason in edited["staleness"]["reasons"]]
            check("V2.3.6-06", "人工编辑保存为 v2：逐字生效、hash 重算一致、旧版本保留、确认失效回落",
                  edited["main"]["version"] == 2 and edited["main"]["origin"] == "manual_edit"
                  and edited["main"]["hash"] == edited["main"]["recomputed"]
                  and edited["main"]["hash"] != confirmed["main"]["hash"]
                  and edited["main"]["edited_from"]["version"] == 1
                  and edited["main"]["edited_from"]["hash"] == confirmed["main"]["hash"]
                  and edited["main"]["reason"] == "补充标志位置约束"
                  and edited["main"]["invalidation"]["scope"] == "shot"
                  and edited["main"]["invalidation"]["target_shot_id"] == "shot_main_clean"
                  and edited["main"]["text"] == edit_text
                  and len(edited["main"]["versions"]) == 2
                  and "人工编辑" in main_card["badges"]
                  and "补充标志位置约束" in main_card["notes"]
                  and edited["staleness"]["stale"] is True
                  and "shots.shot_main_clean" in fields
                  and edited["project_state"] == "PLAN_REVIEW"
                  and "已失效" in edited["ui"]["confirm_record"],
                  {"version": edited["main"]["version"], "fields": fields,
                   "hash": edited["main"]["hash"][:12], "state": edited["project_state"]})

            save_edit(page, "shot_main_clean", "", "空文本")
            empty = page.evaluate(EDIT_PROBE)
            check("V2.3.6-07", "空文本被拒：不产新版本、旧版本保留、错误可见",
                  empty["main"]["version"] == 2 and len(empty["main"]["versions"]) == 2
                  and empty["ui"]["error_hidden"] is False
                  and "不能为空" in empty["ui"]["error"]
                  and "旧版本与输入已保留" in empty["ui"]["error"],
                  {"error": empty["ui"]["error"][:160]})

            unknown_text = edit_text + "\n补充：画面里写「限时特惠」。"
            save_edit(page, "shot_main_clean", unknown_text, "越权引用")
            unknown = page.evaluate(EDIT_PROBE)
            check("V2.3.6-08", "未授权引用被拒：提示指回商品理解、旧版本保留",
                  unknown["main"]["version"] == 2 and len(unknown["main"]["versions"]) == 2
                  and "不是任何已确认事实值" in unknown["ui"]["error"]
                  and "旧版本与输入已保留" in unknown["ui"]["error"],
                  {"error": unknown["ui"]["error"][:200]})

            platform_text = edit_text + "\n补充：图中文字写「12小时保温」。"
            save_edit(page, "shot_main_clean", platform_text, "主图文案")
            platform = page.evaluate(EDIT_PROBE)
            check("V2.3.6-09", "主图新增文案被拒：平台文字规则、旧版本保留",
                  platform["main"]["version"] == 2 and len(platform["main"]["versions"]) == 2
                  and "不能新增叠加文案" in platform["ui"]["error"],
                  {"error": platform["ui"]["error"][:200]})

            compile_all(page, ["shot_infographic_benefits"], wait_ms=500)
            after_render = page.evaluate(EDIT_PROBE)
            main_card = card_of(after_render, "shot_main_clean")
            check("V2.3.6-10", "编译另一张图触发重渲染后，未保存的草稿与理由仍在",
                  main_card["textarea"] == platform_text and main_card["reason"] == "主图文案"
                  and after_render["main"]["version"] == 2,
                  {"draft_chars": len(main_card["textarea"] or ""), "reason": main_card["reason"]})

            chain_text = after_render["main"]["text"] + "\n补充：背景不得出现投影。"
            save_edit(page, "shot_main_clean", chain_text, "第二次编辑：投影")
            chained = page.evaluate(EDIT_PROBE)
            previous_hash = after_render["main"]["hash"]
            check("V2.3.6-11", "链式编辑 v3：指向 v2、来源可追溯、hash 再次变化",
                  chained["main"]["version"] == 3 and chained["main"]["origin"] == "manual_edit"
                  and chained["main"]["edited_from"]["version"] == 2
                  and chained["main"]["edited_from"]["hash"] == previous_hash
                  and chained["main"]["hash"] == chained["main"]["recomputed"]
                  and ("prompt_edit:" + previous_hash) in chained["main"]["source_refs"]
                  and chained["main"]["invalidation"]["target_shot_id"] == "shot_main_clean"
                  and len(chained["main"]["versions"]) == 3,
                  {"version": chained["main"]["version"], "hash": chained["main"]["hash"][:12]})

            page.click("#confirm-action")
            reconfirmed = page.evaluate(EDIT_PROBE)
            check("V2.3.6-12", "重新确认写 v2：指纹变化、逐图版本同步、状态回到 READY_TO_GENERATE",
                  reconfirmed["confirm"]["version"] == 2
                  and reconfirmed["confirm"]["hash"] != confirmed["confirm"]["hash"]
                  and reconfirmed["staleness"]["stale"] is False
                  and reconfirmed["project_state"] == "READY_TO_GENERATE"
                  and any(item["shot_id"] == "shot_main_clean" and item["prompt_version"] == 3
                          for item in reconfirmed["confirm"]["shots"]),
                  {"state": reconfirmed["project_state"], "hash": reconfirmed["confirm"]["hash"][:12]})

            screenshot_rel = f"evals/product-v2/v2.3.6-prompt-manual-edit-{stamp}.png"
            page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
            screenshots.append(screenshot_rel)

            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "generate")
            page.wait_for_selector(
                '#prompt-list .shot-spec[data-shot-id="shot_main_clean"] textarea.prompt-edit-text')
            reloaded = page.evaluate(EDIT_PROBE)
            main_card = card_of(reloaded, "shot_main_clean")
            check("V2.3.6-13", "刷新恢复：人工版本、理由、hash、状态与存储一致",
                  reloaded["main"]["version"] == 3 and reloaded["main"]["origin"] == "manual_edit"
                  and reloaded["main"]["reason"] == "第二次编辑：投影"
                  and reloaded["main"]["hash"] == reloaded["main"]["recomputed"]
                  and reloaded["project_state"] == "READY_TO_GENERATE"
                  and reloaded["staleness"]["stale"] is False
                  and "人工编辑" in main_card["badges"],
                  {"state": reloaded["project_state"], "hash": reloaded["main"]["hash"][:12]})
            ui["final"] = {
                "main_version": reloaded["main"]["version"],
                "main_origin": reloaded["main"]["origin"],
                "main_hash": reloaded["main"]["hash"],
                "edit_reason": reloaded["main"]["reason"],
                "confirm_version": reloaded["confirm"]["version"],
                "fingerprint": reloaded["confirm"]["hash"],
                "state": reloaded["project_state"],
                "prompt_counts": reloaded["prompt_counts"],
                "confirm_versions": reloaded["confirm_versions"],
            }
            context.close()
    finally:
        server.shutdown()
        server.server_close()

    check("V2.3.6-14", "契约会话与 UI 会话零 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:5], "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.3.6-15", "正式入口自检仍全过（V2.3.6 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明提示词人工编辑在真实浏览器里可用且可核对：编辑以新版本追加，不覆盖被编辑版本；文本逐字等于"
        "记录与请求快照，hash 由快照重算；basis 逐字继承，编辑本身不造成过期，上游前进才过期；失效投影只"
        "指向目标 Shot 的提示词、审核与选择，保留商品理解、套图计划、单图规格与其他图片；旧确认因指纹变化"
        "失效并回落 PLAN_REVIEW，重新确认写新版本。只有语言策略降级为提示（可见警告），空文本、超长、控制"
        "字符、无变化、未确认事实（含引用写法）、未授权新引用与主图新增文案仍然硬阻断。"
        "全程 0 次真实模型调用，不发图、不生成候选、不证明出图质量；真实生成属于 Phase 4，审核与返工属于 Phase 5。"
    )
    report = {
        "task": "V2.3.6",
        "suite_id": "v2.3.6-prompt-edit",
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
    json_path = EVIDENCE_DIR / f"v2.3.6-prompt-manual-edit-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.6-prompt-manual-edit-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.6 prompt manual edit",
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
    print("V2.3.6 Prompt 人工编辑验证")
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
