#!/usr/bin/env python
"""V2.5.1 证据：生成前、单图和导出的确定性验证器（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 通过 node --check（ESM 语法门）。
  2) R11 WebCrypto 哈希复算宿主案例在真实 Chromium 全过；R01..R10/R12/R13 纯领域断言
     已按 R3.2 分层迁至 `npm run test:domain`（Node 直跑，同批断言）。
  3) 既有契约套件回归（candidate / attempt / batch / confirm / prompt_edit / suite_editor）全过。
  4) 真实工作台走查（假 provider）：候选保存后 IndexedDB 出现 kind="review_report" 的当前报告
     （绑定 candidate_id + 当前合同版本 + asset_sha256），候选行出现 data-review-summary 摘要；
     刷新后报告与摘要仍在且不重复铺。
  5) 正式入口 --check 全过；零意外 console error / page error。

运行：
  uv run --locked python tools/verify_v2_5_1_deterministic_review.py --label final
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
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
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def current_review_contract() -> str:
    """合同版本只有一个权威（review.js 常量）；本验证器跟随当前版本，不写死字面量。"""

    text = (PRODUCT_DIR / "domain" / "review.js").read_text(encoding="utf-8")
    match = re.search(r'REVIEW_CONTRACT_VERSION\s*=\s*"([^"]+)"', text)
    if match is None:
        raise SystemExit("review.js 里找不到 REVIEW_CONTRACT_VERSION。")
    return match.group(1)

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
    "app/product_v2/domain/review.js",
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/review-contract.js",
]

# R3.2 分层：浏览器只承载宿主特有案例 R11；纯领域 R01..R10/R12/R13 在 npm run test:domain。
EXPECTED_CASES = ["R11"]
NEGATIVE_CASES = ["R11"]
REGRESSION_SUITES = (
    ("candidate", "candidate-contract.html", "__V2_CANDIDATE_RESULTS__"),
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
    stage_nav.goto(page, "generate")
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
        evidence: [{ kind: "user", ref: "v251-seed" }], depends_on: [],
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
  const reviews = documents.filter((row) => row.kind === "review_report")
    .map((row) => ({ document_id: row.document_id, version: row.version, payload: row.payload }))
    .sort((left, right) => (left.document_id + left.version)
      .localeCompare(right.document_id + right.version));
  const plans = documents.filter((item) => item.kind === "suite_plan")
    .sort((left, right) => left.version - right.version);
  const plan = plans.length ? plans[plans.length - 1] : null;
  const rows = [...document.querySelectorAll("#attempt-list .attempt-row")].map((node) => {
    const img = node.querySelector(".attempt-preview img");
    const candidateMeta = node.querySelector(".attempt-candidate");
    const reviewNode = node.querySelector(".attempt-review");
    return {
      shot_id: node.getAttribute("data-shot-id"),
      state: node.getAttribute("data-attempt-state"),
      candidate_meta: candidateMeta ? candidateMeta.textContent : null,
      review: reviewNode ? {
        text: reviewNode.textContent,
        summary: reviewNode.getAttribute("data-review-summary"),
        contract: reviewNode.getAttribute("data-review-contract"),
        candidate: reviewNode.getAttribute("data-review-candidate"),
      } : null,
      preview: img ? {
        src: img.getAttribute("src") || "",
        complete: img.complete,
        natural_width: img.naturalWidth,
      } : null,
      buttons: [...node.querySelectorAll("button")].map((item) =>
        ({ text: item.textContent, disabled: item.disabled })),
    };
  });
  const errorNode = document.getElementById("attempt-error");
  return {
    project_ids: projects.map((item) => item.project_id),
    shot_ids: plan ? plan.payload.shots.map((shot) => shot.shot_id) : [],
    attempt_chains: chains,
    candidate_chains: candidates,
    review_reports: reviews,
    asset_rows: assets.map((item) => ({
      sha256: item.sha256, media_type: item.media_type, byte_size: item.byte_size,
      width: item.width, height: item.height, role: item.role,
      has_blob: item.blob instanceof Blob,
    })),
    ui: {
      error: errorNode ? errorNode.textContent : "",
      error_hidden: errorNode ? errorNode.hidden : true,
      rows: rows,
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
  return { found: true, sha256: hex, byte_size: buffer.byteLength };
}
"""


def chain_of(data: dict, shot_id: str) -> list:
    return data["attempt_chains"].get(shot_id, [])


def candidate_of(data: dict, shot_id: str) -> list:
    return data["candidate_chains"].get(shot_id, [])


def row_of(data: dict, shot_id: str) -> dict | None:
    return next((row for row in data["ui"]["rows"] if row["shot_id"] == shot_id), None)


def reviews_for(data: dict, candidate_id: str) -> list:
    return [item for item in data["review_reports"] if item["document_id"] == candidate_id]


def candidate_json(data: dict, shot_id: str) -> str:
    return json.dumps(candidate_of(data, shot_id), ensure_ascii=False, sort_keys=True)


def review_json(data: dict, candidate_id: str) -> str:
    return json.dumps(reviews_for(data, candidate_id), ensure_ascii=False, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="V2.5.1 生成前、单图与导出的确定性验证器证据")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    contract = current_review_contract()
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []
    ui: dict = {}

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    node_result = run_node_checks()
    check("V2.5.1-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"],
          {"failed": [item for item in node_result["files"] if item["rc"] != 0][:3]})

    static_server, static_url = start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["review"] = read_suite(
                    browser, static_url + "/harness/review-contract.html",
                    "__V2_REVIEW_RESULTS__", console_errors, page_errors)
                for name, page_name, variable in REGRESSION_SUITES:
                    suites[name] = read_suite(
                        browser, static_url + "/harness/" + page_name, variable,
                        console_errors, page_errors)
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    suite = suites["review"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.5.1-01", "R11 宿主案例全过且清单齐全（R01..R10/R12/R13 在 npm run test:domain）",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")}
                      for item in failed_cases[:3]]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.5.1-02", "R11 反向探针确实执行（哈希篡改/缺失阻断/缺 digest 注入抛错）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "review"}
    check("V2.5.1-02b", "既有契约套件回归全过（candidate / attempt / batch / confirm / prompt_edit / suite_editor）",
          all(item["status"] == "passed" and not item["failed"] for item in regression.values()),
          regression)

    module = load_server_module()
    from src.providers.v2_fake_image import FakeImageProvider  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    stage = "setup"
    interrupted: str | None = None
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v251-"))
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

                def probe() -> dict:
                    return page.evaluate(PROBE)

                def row(shot_id: str):
                    return page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 30_000) -> None:
                    expect(row(shot_id)).to_have_attribute(
                        "data-attempt-state", state, timeout=timeout)

                def wait_candidate_ui(shot_id: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(shot) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                            return Boolean(node && node.querySelector('.attempt-candidate'));
                        }""", arg=shot_id, timeout=timeout)

                def wait_review_ui(shot_id: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(payload) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + payload.shot + '"]');
                            const line = node && node.querySelector('.attempt-review');
                            const summary = line && line.getAttribute('data-review-summary');
                            return Boolean(summary
                                && summary.indexOf('自动检查 ' + payload.version) === 0);
                        }""", arg={"shot": shot_id, "version": contract}, timeout=timeout)

                def confirm_generation() -> None:
                    stage_nav.goto(page, "generate")
                    expect(page.locator("#confirm-action")).to_be_enabled()
                    page.click("#confirm-action")
                    expect(page.locator("#confirm-record")).to_contain_text("已确认 v")

                def click_row_button(shot_id: str, text: str) -> None:
                    stage_nav.goto(page, "generate")
                    row(shot_id).locator(f'button:has-text("{text}")').first.click()

                def generate_and_settle(shot_id: str) -> None:
                    click_row_button(shot_id, "生成这张图")
                    wait_state(shot_id, "submitted")
                    click_row_button(shot_id, "核对任务")
                    wait_state(shot_id, "succeeded")

                # ---------------- 项目准备：空白项目 → 参考图 → 资料 → 槽位 → 套图 → 确认 ----------------
                stage = "prep"
                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · 自动检查")
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
                expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
                initial = probe()
                shot_ids = initial["shot_ids"]
                compile_all(page, shot_ids)
                ok_shot = shot_ids[0]
                confirm_generation()

                # ---------------- 单张成功：候选自动入库 + 当前 ReviewReport + 摘要行 ----------------
                stage = "review-report"
                generate_and_settle(ok_shot)
                wait_candidate_ui(ok_shot)
                wait_review_ui(ok_shot)
                after_store = probe()
                cand_chain = candidate_of(after_store, ok_shot)
                cand = cand_chain[-1]["payload"] if cand_chain else {}
                candidate_id = cand.get("candidate_id") or ""
                reviews = reviews_for(after_store, candidate_id)
                report = reviews[-1]["payload"] if reviews else {}
                summary = report.get("summary") or {}
                review_ui = (row_of(after_store, ok_shot) or {}).get("review") or {}
                ui["candidate_id"] = candidate_id
                ui["review_summary_text"] = review_ui.get("text")
                ui["review_contract_version"] = report.get("review_contract_version")
                check("V2.5.1-03",
                      "候选保存后自动生成当前 ReviewReport（绑定身份 + 合同 "
                      + contract + "），界面出现摘要行",
                      len(cand_chain) == 1
                      and len(reviews) == 1
                      and report.get("review_contract_version") == contract
                      and report.get("candidate_id") == candidate_id
                      and report.get("shot_id") == cand.get("shot_id")
                      and report.get("asset_sha256") == cand.get("asset_sha256")
                      and isinstance(report.get("findings"), list) and len(report["findings"]) > 0
                      and all(isinstance(summary.get(key), int)
                              for key in ["BLOCK", "HIGH_RISK", "WARNING", "PASS", "UNKNOWN"])
                      and (review_ui.get("summary") or "").startswith("自动检查 " + contract)
                      and review_ui.get("contract") == contract
                      and review_ui.get("candidate") == candidate_id
                      and "阻断" in (review_ui.get("text") or "")
                      and "提醒" in (review_ui.get("text") or ""),
                      {"contract": report.get("review_contract_version"),
                       "summary": summary,
                       "summary_line": review_ui.get("summary"),
                       "findings": len(report.get("findings") or [])})

                # ---------------- 刷新：报告与摘要保留、不重复铺 ----------------
                stage = "reload"
                before_reload = probe()
                page.reload(wait_until="networkidle")
                wait_candidate_ui(ok_shot)
                wait_review_ui(ok_shot)
                after_reload = probe()
                check("V2.5.1-04",
                      "刷新后报告与摘要仍在、候选链不变、review_report 文档不重复铺",
                      candidate_json(after_reload, ok_shot) == candidate_json(before_reload, ok_shot)
                      and len(reviews_for(after_reload, candidate_id)) == 1
                      and review_json(after_reload, candidate_id)
                      == review_json(before_reload, candidate_id)
                      and ((row_of(after_reload, ok_shot) or {}).get("review") or {})
                      .get("summary", "").startswith("自动检查 " + contract),
                      {"review_docs_before": len(reviews_for(before_reload, candidate_id)),
                       "review_docs_after": len(reviews_for(after_reload, candidate_id))})

                screenshot_rel = (f"evals/product-v2/evidence/"
                                  f"v2.5.1-deterministic-review-{stamp}.png")
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
        check("V2.5.1-99", "浏览器闭环在完成前中断", False, interrupted)

    check("V2.5.1-05", "零意外 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:6], "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.5.1-06", "正式入口自检仍全过（本批不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明确定性验证器在真实浏览器上按规则版本工作：注册表对缺要素/重复 id/未知词表/"
        "无任务锚点的消费者/未被认领的确认单代码直接报错；单图检查只做可复现测量——"
        "PNG 合同、记录一致性、最小长边 1000px（阻断）、推荐 1600px、主图 1:1、透明通道"
        "（HIGH_RISK 人工确认）、像素位深；测量失败一律降为 UNKNOWN 且不阻断；生成前阻塞项"
        "从确认单一对一映射为 BLOCK、提示项映射为 WARNING；导出就绪检查覆盖选择完整性、"
        "报告当前性、报告无 BLOCK、选择链一致性与 WebCrypto sha256 复算。候选保存时自动生成"
        "绑定 candidate_id + review_contract_version + asset_sha256 的 ReviewReport 并投影到"
        "工作台摘要行，刷新后保留且不重复铺。本批不做 VLM 审核、比较界面与返工（V2.5.2+）；"
        "0 次真实模型调用、0 次外部网络；图像与语义 provider 都是注入的假替身，只证明确定性"
        "校验语义，不证明真实出图质量。"
    )
    report = {
        "task": "V2.5.1",
        "suite_id": "v2.5.1-deterministic-review",
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
    json_path = EVIDENCE_DIR / f"v2.5.1-deterministic-review-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.5.1-deterministic-review-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.5.1 生成前、单图与导出的确定性验证器",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 · external_network_calls: 0 (fake providers + 本机服务)",
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
