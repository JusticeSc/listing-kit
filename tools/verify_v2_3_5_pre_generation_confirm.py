#!/usr/bin/env python
"""V2.3.5 证据：生成前确认与外发资料摘要（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 全部通过 node --check（ESM 语法门）。
  2) 契约套件 H01..H12 在真实 Chromium 全过（确定性、摘要一致、缺 Prompt / 过期 / 缺依赖 /
     Provider / 平台 / 参考图越界阻断、风险传播、确认记录与失效判定、反向探针）。
  3) 正式入口：套图就绪后「生成前确认」解锁，4 张图因缺 Prompt 全部阻断并定位到 Prompt 区。
  4) 缺依赖的对比图被精确阻断并定位到套图规划；删除后恢复。
  5) 编译全部图后可确认；点击确认写入 generation_confirm，界面、记录与重算指纹一致，状态前进。
  6) 改公共风格：确认失效、状态回落 PLAN_REVIEW，界面显示原因。
  7) 重新编译并再次确认：写新版本，旧确认记录保留（append-only）。
  8) 刷新恢复：确认记录、指纹、状态与存储一致。
  9) 零 console error / page error；截图落盘；正式入口 --check 与既有套件仍全过。

运行：
  uv run --locked python tools/verify_v2_3_5_pre_generation_confirm.py
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

CONFIRM_PROBE = """
async () => {
  const domain = await import("/domain/index.js");
  const storage = await import("/storage/db.js");
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
  const plan = latest("suite_plan", "suite");
  if (!plan) return { plan: null };
  const slots = [...new Map(rows("fact_slot").map((item) => [item.document_id, item])).values()];
  const briefBasis = slots.map((item) => ({ slot_id: item.document_id, version: item.version }));
  const styleRow = latest("style_spec", "style");
  const confirmRows = rows("generation_confirm").sort((left, right) => left.version - right.version);
  const confirmRow = confirmRows.length > 0 ? confirmRows[confirmRows.length - 1] : null;
  const entries = [...new Map(rows("prompt_version").map((item) => [item.document_id, item])).values()]
    .map((item) => ({ shot_id: item.document_id, record: item.payload, version: item.version }));
  const intake = latest("product_input", "intake");
  const basisByShot = {};
  for (const shot of plan.payload.shots) {
    const spec = latest("shot_spec", shot.shot_id);
    basisByShot[shot.shot_id] = {
      briefBasis,
      suite_version: plan.version,
      style_version: styleRow ? styleRow.version : null,
      shot_spec_version: spec ? spec.version : null,
      platform: { version: domain.PLATFORM_PROFILES.amazon_us.version },
      provider: { version: domain.PROVIDER_PROFILES["qwen-image-3.0"].version },
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
  });
  const snapshot = domain.confirmationSnapshot(sheet);
  const staleness = confirmRow ? domain.confirmationStaleness(confirmRow.payload, snapshot) : null;
  const recomputedHash = confirmRow ? await domain.promptHash(snapshot, { digest: storage.sha256Hex }) : null;
  const project = projects.slice().sort((left, right) =>
    String(right.updated_at || "").localeCompare(String(left.updated_at || "")))[0] || null;
  return {
    sheet: sheet,
    staleness: staleness,
    recomputed_hash: recomputedHash,
    record: confirmRow ? { version: confirmRow.version, payload: confirmRow.payload } : null,
    confirm_rows: confirmRows.map((item) => ({ version: item.version,
      hash: item.payload.fingerprint ? item.payload.fingerprint.hash : null })),
    prompt_versions: entries.map((item) => ({ shot_id: item.shot_id, version: item.version, hash: item.record.hash })),
    project_state: project ? project.state : null,
    ui: {
      status: document.getElementById("confirm-status").textContent,
      record: document.getElementById("confirm-record").textContent,
      summary: document.getElementById("confirm-summary").textContent,
      blockers: document.getElementById("confirm-blockers").textContent,
      risks: document.getElementById("confirm-risks").textContent,
      action_disabled: document.getElementById("confirm-action").disabled,
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


def compile_all(page, shot_ids: list, wait_ms: int = 200) -> None:
    for shot_id in shot_ids:
        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
        page.click(card + " button")
        page.wait_for_selector(card + '[data-prompt-state="saved"]', timeout=15_000)
        page.wait_for_timeout(wait_ms)


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
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port, provider_factory=lambda: FakeSemanticProvider(scenario="ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    ui: dict = {}
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v235-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品 · 生成前确认")
            page.click("#create-project")
            page.click('#project-list .project-row button[data-action="open"]')
            expect(page.locator("#project-view")).to_be_visible()
            expect(page.locator("#confirm-editor")).to_be_hidden()
            expect(page.locator("#confirm-locked")).to_be_visible()
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
            page.click("#suite-seed")
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            expect(page.locator("#confirm-editor")).to_be_visible()
            expect(page.locator("#confirm-list .confirm-shot")).to_have_count(4)
            first = page.evaluate(CONFIRM_PROBE)
            sheet = first["sheet"]
            prompt_missing = [item for item in sheet["shots"]
                              if "PROMPT_MISSING" in [blocker["code"] for blocker in item["blockers"]]]
            prompt_fixes = [item["blockers"][0]["fix"] for item in prompt_missing]
            check("V2.3.5-03", "套图就绪后确认区解锁：4 张图因缺 Prompt 全部阻断并定位到 Prompt 区",
                  sheet["can_submit"] is False and sheet["blocked"] == 4 and len(prompt_missing) == 4
                  and all(fix["region"] == "prompt" and fix["shot_id"] for fix in prompt_fixes)
                  and first["ui"]["action_disabled"] is True
                  and "阻断 4 张" in first["ui"]["status"]
                  and "参考" in first["ui"]["summary"],
                  {"status": first["ui"]["status"], "blocked": sheet["blocked"],
                   "summary": first["ui"]["summary"][:200]})

            page.select_option("#suite-template", "comparison_competitor")
            page.click("#suite-add-template")
            expect(page.locator("#shot-list .shot-row")).to_have_count(5)
            expect(page.locator('#shot-list .shot-row[data-blocked="true"]')).to_have_count(1)
            blocked_probe = page.evaluate(CONFIRM_PROBE)
            blocked_sheet = blocked_probe["sheet"]
            comparison = next(item for item in blocked_sheet["shots"]
                              if item["shot_id"] == "shot_comparison_competitor")
            comparison_codes = [blocker["code"] for blocker in comparison["blockers"]]
            dependency_fix = next(blocker["fix"] for blocker in comparison["blockers"]
                                  if blocker["code"] == "DEPENDENCY_UNSATISFIED")
            check("V2.3.5-04", "缺依赖的对比图被精确阻断并定位到套图规划",
                  blocked_sheet["total"] == 5 and blocked_sheet["blocked"] == 5
                  and "DEPENDENCY_UNSATISFIED" in comparison_codes
                  and "PROMPT_MISSING" in comparison_codes
                  and dependency_fix["region"] == "suite"
                  and "套图规划" in blocked_probe["ui"]["blockers"],
                  {"codes": comparison_codes, "fix": dependency_fix})
            page.click('#shot-list .shot-row[data-shot-id="shot_comparison_competitor"] button:has-text("删除")')
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)

            page.click('#prompt-list .shot-spec[data-shot-id="shot_main_clean"] button')
            page.wait_for_selector('#prompt-list .shot-spec[data-shot-id="shot_main_clean"][data-prompt-state="saved"]')
            partial = page.evaluate(CONFIRM_PROBE)
            main_item = next(item for item in partial["sheet"]["shots"] if item["shot_id"] == "shot_main_clean")
            main_record = next(item for item in partial["prompt_versions"] if item["shot_id"] == "shot_main_clean")
            check("V2.3.5-05", "编译主图后状态推进：就绪 1 / 阻断 3，外发摘要与记录一致",
                  partial["sheet"]["ready"] == 1 and partial["sheet"]["blocked"] == 3
                  and partial["sheet"]["can_submit"] is False
                  and main_item["prompt"]["chars"] == partial["sheet"]["external_summary"]["prompt_chars"]
                  and str(partial["sheet"]["external_summary"]["prompt_chars"]) in partial["ui"]["summary"]
                  and len(main_item["references"][0]["sha256_prefix"]) == 12
                  and partial["sheet"]["external_summary"]["model"] == "qwen-image-3.0",
                  {"summary": partial["sheet"]["external_summary"]["statement"][:200],
                   "hash": main_record["hash"][:12]})

            compile_all(page, [item["shot_id"] for item in partial["sheet"]["shots"]
                               if item["prompt"]["version"] is None])
            ready = page.evaluate(CONFIRM_PROBE)
            ready_risks = [risk["code"] for risk in ready["sheet"]["risks"]]
            check("V2.3.5-06", "全部编译后可确认：按钮可用、无阻断、风险仍可见",
                  ready["sheet"]["can_submit"] is True and ready["sheet"]["blocked"] == 0
                  and ready["ui"]["action_disabled"] is False
                  and "可以确认" in ready["ui"]["status"]
                  and "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" in ready_risks
                  and ready["record"] is None,
                  {"status": ready["ui"]["status"], "risks": ready_risks})

            page.click("#confirm-action")
            expect(page.locator("#confirm-record")).to_contain_text("已确认 v1")
            confirmed = page.evaluate(CONFIRM_PROBE)
            record = confirmed["record"]
            check("V2.3.5-07", "点击确认写入 generation_confirm：指纹、记录与界面一致，状态前进",
                  record is not None and record["version"] == 1
                  and record["payload"]["fingerprint"]["hash"] == confirmed["recomputed_hash"]
                  and confirmed["staleness"]["stale"] is False
                  and confirmed["project_state"] == "READY_TO_GENERATE"
                  and "尚未调用图片模型" in confirmed["ui"]["record"]
                  and len(record["payload"]["shots"]) == 4,
                  {"state": confirmed["project_state"],
                   "hash": record["payload"]["fingerprint"]["hash"][:12] if record else None})

            page.fill("#style-background", "深灰无缝背景")
            page.click("#style-save")
            expect(page.locator("#style-version")).to_have_text("版本 v1")
            expect(page.locator("#confirm-record")).to_contain_text("已失效")
            stale = page.evaluate(CONFIRM_PROBE)
            stale_fields = [reason["field"] for reason in stale["staleness"]["reasons"]]
            check("V2.3.5-08", "改公共风格使确认失效并回落 PLAN_REVIEW，界面给出原因",
                  stale["staleness"]["stale"] is True
                  and any(field.startswith("shots.") for field in stale_fields)
                  and stale["project_state"] == "PLAN_REVIEW"
                  and stale["sheet"]["can_submit"] is False
                  and "已失效" in stale["ui"]["record"],
                  {"fields": stale_fields[:4], "state": stale["project_state"]})

            compile_all(page, [item["shot_id"] for item in stale["sheet"]["shots"]])
            reconfirm_ready = page.evaluate(CONFIRM_PROBE)
            check("V2.3.5-09", "重新编译后再次可确认，Prompt 版本全部前进",
                  reconfirm_ready["sheet"]["can_submit"] is True
                  and all(item["version"] == 2 for item in reconfirm_ready["prompt_versions"]),
                  {"versions": reconfirm_ready["prompt_versions"]})

            page.click("#confirm-action")
            expect(page.locator("#confirm-record")).to_contain_text("已确认 v2")
            second_record = page.evaluate(CONFIRM_PROBE)
            check("V2.3.5-10", "再次确认写新版本且旧记录保留（append-only）",
                  second_record["record"]["version"] == 2
                  and len(second_record["confirm_rows"]) == 2
                  and second_record["confirm_rows"][0]["hash"] != second_record["confirm_rows"][1]["hash"]
                  and second_record["staleness"]["stale"] is False
                  and second_record["project_state"] == "READY_TO_GENERATE",
                  {"rows": second_record["confirm_rows"]})

            screenshot_rel = f"evals/product-v2/v2.3.5-pre-generation-confirm-{stamp}.png"
            page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
            screenshots.append(screenshot_rel)

            page.reload(wait_until="networkidle")
            expect(page.locator("#confirm-editor")).to_be_visible()
            expect(page.locator("#confirm-record")).to_contain_text("已确认 v2")
            reloaded = page.evaluate(CONFIRM_PROBE)
            check("V2.3.5-11", "刷新恢复：确认记录、指纹、状态与存储一致",
                  reloaded["record"]["version"] == 2
                  and reloaded["record"]["payload"]["fingerprint"]["hash"] == reloaded["recomputed_hash"]
                  and reloaded["staleness"]["stale"] is False
                  and reloaded["project_state"] == "READY_TO_GENERATE"
                  and reloaded["ui"]["action_disabled"] is False
                  and len(reloaded["ui"]["rows"]) == 4,
                  {"state": reloaded["project_state"],
                   "hash": reloaded["record"]["payload"]["fingerprint"]["hash"][:12]})
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
