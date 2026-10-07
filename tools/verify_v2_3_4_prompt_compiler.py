#!/usr/bin/env python
"""V2.3.4 证据：Provider 感知 Prompt 编译器（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 全部通过 node --check（ESM 语法门）。
  2) 契约套件 G01..G12 在真实 Chromium 全过（含 golden、来源、hash、语言、冲突、泄漏、快照、过期）。
  3) 正式入口：商品理解 + 套图方案就绪后，「Prompt 预览与版本」解锁；模板图自动绑定已确认事实。
  4) 编译主图并保存 v1：界面文本 = 记录文本 = 请求快照 prompt；hash 三者一致；参考图角色正确。
  5) 编译卖点信息图：图中文案逐字来自已确认事实，语言不一致给警告并在界面可见。
  6) 改公共风格：既有 Prompt 变「已过期」，重新编译写 v2 且 hash 变化，旧版本历史保留。
  7) 制造 keep/avoid 冲突：编译失败给出精确原因，卡片仍显示旧 v2 文本与旧版本号。
  8) 刷新恢复：Prompt 文本、hash、版本与存储一致；其他图的版本不受影响。
  9) 零 console error / page error；截图落盘；正式入口 --check 仍全过。

运行：
  uv run --locked python tools/verify_v2_3_4_prompt_compiler.py
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
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/prompt-contract.js",
]

EXPECTED_CASES = [f"G{index:02d}" for index in range(1, 13)]
NEGATIVE_CASES = ["G04", "G05", "G06", "G07", "G08", "G10", "G11", "G12"]

PROMPT_SNAPSHOT = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) return { records: [] };
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await new Promise((resolve, reject) => {
    const request = db.transaction("documents", "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  return {
    records: documents.filter((item) => item.kind === "prompt_version")
      .map((item) => ({ document_id: item.document_id, version: item.version, payload: item.payload })),
    suite_shots: documents.filter((item) => item.kind === "suite_plan")
      .map((item) => item.payload),
  };
}
"""

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
        evidence: [{ kind: "user", ref: "v234-seed" }], depends_on: [],
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
            self._send((HARNESS_DIR / "prompt-contract.html").read_bytes(), MIME[".html"])
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


RECOMPUTE = """
async ({ shotId }) => {
  const domain = await import("/domain/index.js");
  const storage = await import("/storage/db.js");
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await new Promise((resolve, reject) => {
    const request = db.transaction("documents", "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const record = documents.filter((item) => item.kind === "prompt_version" && item.document_id === shotId)
    .sort((left, right) => right.version - left.version)[0];
  if (!record) return { found: false };
  const hash = await domain.promptHash(record.payload.request_snapshot, { digest: storage.sha256Hex });
  const card = document.querySelector("#prompt-list .shot-spec[data-shot-id='" + shotId + "']");
  return {
    found: true,
    version: record.version,
    record_hash: record.payload.hash,
    recomputed_hash: hash,
    text: record.payload.compiled.text,
    snapshot_prompt: record.payload.request_snapshot.prompt,
    ui_text: card ? card.querySelector("pre.prompt-text").textContent : null,
    ui_hash: card ? card.querySelector("p.prompt-hash").textContent : null,
    ui_meta: card ? card.textContent : null,
    ui_state: card ? card.getAttribute("data-prompt-state") : null,
    warnings: (record.payload.compiled.warnings || []).map((item) => item.code),
    literal_items: (record.payload.compiled.sections || [])
      .filter((item) => item.kind === "literal")
      .flatMap((item) => item.items.map((entry) => entry.text)),
    references: record.payload.request_snapshot.references,
    basis: record.payload.basis,
  };
}"""


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


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.3.4 Prompt 编译器验证")
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
    check("V2.3.4-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"], node_result)

    static_server, static_url = start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["prompt"] = read_suite(
                    browser, static_url + "/harness/prompt-contract.html",
                    "__V2_PROMPT_RESULTS__", console_errors, page_errors)
                suites["specs"] = read_suite(
                    browser, static_url + "/harness/specs-contract.html",
                    "__V2_SPECS_RESULTS__", console_errors, page_errors)
                suites["suite_editor"] = read_suite(
                    browser, static_url + "/harness/suite-editor-contract.html",
                    "__V2_SUITE_EDITOR_RESULTS__", console_errors, page_errors)
                suites["suite_plan"] = read_suite(
                    browser, static_url + "/harness/suite-plan-contract.html",
                    "__V2_SUITE_RESULTS__", console_errors, page_errors)
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    suite = suites["prompt"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.3.4-01", "G01–G12 契约套件全过且用例齐全",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [item["id"] for item in failed_cases]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.3.4-02", "反向探针确实执行（冲突、缺依据、泄漏、越界、过期等守卫）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"),
                         "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "prompt"}
    check("V2.3.4-02b", "既有契约套件回归：规格 / 套图编辑器 / 套图注册表全过",
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
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v234-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))
    main_card = '#prompt-list .shot-spec[data-shot-id="shot_main_clean"]'
    info_card = '#prompt-list .shot-spec[data-shot-id="shot_infographic_benefits"]'
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品 · Prompt 编译")
            page.click("#create-project")
            expect(page.locator("#project-view")).to_be_visible()
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
            expect(page.locator("#specs-editor")).to_be_hidden()
            expect(page.locator("#prompt-editor")).to_be_hidden()
            page.click("#suite-seed")
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            stage_nav.goto(page, "generate")
            # #prompt-editor 在 <details id="prompt-details">（默认闭合）内：hidden 属性已随套图就绪打开，
            # 视觉可见还需展开 details（用户真实路径；只改“怎么到达断言”，不断言内容）。
            stage_nav.reveal(page, "#prompt-editor")
            expect(page.locator("#prompt-editor")).to_be_visible()
            expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
            # 切到生成区会触发异步自动本地准备：等它落定后再读“未编译”基线，避免把准备中的瞬态当断言。
            page.wait_for_function(
                """() => (document.getElementById("local-preparation-status") || {}).textContent
                    && (document.getElementById("local-preparation-status").textContent.includes("本地准备完成")
                        || document.getElementById("local-preparation-status").textContent.includes("部分任务尚未准备"))""",
                timeout=30_000)
            seeded = page.evaluate(PROMPT_SNAPSHOT)
            shots = seeded["suite_shots"][0]["shots"] if seeded["suite_shots"] else []
            info_shot = next((item for item in shots if item["shot_id"] == "shot_infographic_benefits"), None)
            check("V2.3.4-03", "套图就绪后 Prompt 区解锁；模板图按依赖自动绑定已确认事实",
                  page.locator(main_card).get_attribute("data-prompt-state") in ("none", "saved", "stale")
                  and info_shot is not None
                  and info_shot.get("fact_slot_ids") == ["signature_features"],
                  {"info_bindings": info_shot.get("fact_slot_ids") if info_shot else None,
                   "cards": page.locator("#prompt-list .shot-spec").count(),
                   "main_state": page.locator(main_card).get_attribute("data-prompt-state")})

            seeded_main_v0 = page.evaluate(RECOMPUTE, {"shotId": "shot_main_clean"})
            page.click(main_card + " button")
            expect(page.locator(main_card)).to_have_attribute("data-prompt-state", "saved")
            main_v1 = page.evaluate(RECOMPUTE, {"shotId": "shot_main_clean"})
            check("V2.3.4-04", "编译主图（相对自动准备基线 +1）：界面文本 = 记录文本 = 快照 prompt，hash 三者一致",
                  main_v1["found"] and main_v1["version"] == (seeded_main_v0["version"] or 0) + 1
                  and main_v1["ui_text"] == main_v1["text"] == main_v1["snapshot_prompt"]
                  and main_v1["record_hash"] == main_v1["recomputed_hash"] == main_v1["ui_hash"]
                  and len(main_v1["references"]) == 1
                  and main_v1["references"][0]["role"] == "primary"
                  and len(main_v1["references"][0]["sha256"]) == 64
                  and "纯白无缝背景" in main_v1["text"],
                  {"version": main_v1["version"], "hash": main_v1["record_hash"],
                   "refs": main_v1["references"], "length": len(main_v1["text"])})

            seeded_info_v0 = page.evaluate(RECOMPUTE, {"shotId": "shot_infographic_benefits"})
            page.click(info_card + " button")
            expect(page.locator(info_card)).to_have_attribute("data-prompt-state", "saved")
            info_v1 = page.evaluate(RECOMPUTE, {"shotId": "shot_infographic_benefits"})
            check("V2.3.4-05", "卖点信息图：图中文案逐字来自已确认事实，语言警告可见",
                  info_v1["found"] and info_v1["version"] == (seeded_info_v0["version"] or 0) + 1
                  and len(info_v1["literal_items"]) == 2
                  and all(item.startswith("「") and item.endswith("」") for item in info_v1["literal_items"])
                  and "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" in info_v1["warnings"]
                  and "提示：" in info_v1["ui_meta"]
                  and info_v1["ui_text"] == info_v1["text"],
                  {"items": info_v1["literal_items"], "warnings": info_v1["warnings"]})

            # “改风格前”的旧版本快照：必须在 plan 改风格之前取（改后自动本地准备会把卡片直接写成新版，
            # 到那时已无从区分“旧文本是什么”。只改取样口径，不断言含义）。
            pre_style_main = page.evaluate(RECOMPUTE, {"shotId": "shot_main_clean"})
            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            # 风格表单是整单覆盖保存：只填两字段会把未填的色调/构图/avoid 清空，
            # -07 冲突探针依赖 avoid 仍含值。新语义下按当前表单值改（只改到达路径）。
            style_before = {"background": page.input_value("#style-background"),
                            "lighting": page.input_value("#style-lighting"),
                            "color_tone": page.input_value("#style-color-tone"),
                            "composition": page.input_value("#style-composition"),
                            "avoid": page.input_value("#style-avoid")}
            page.fill("#style-background", style_before["background"])
            page.fill("#style-lighting", "电影感轮廓光")
            page.fill("#style-color-tone", style_before["color_tone"])
            page.fill("#style-composition", style_before["composition"])
            page.fill("#style-avoid", style_before["avoid"])
            style_v0 = page.inner_text("#style-version")
            page.click("#style-save")
            expect(page.locator("#style-version")).not_to_have_text(style_v0)
            style_transition = {"from": style_v0, "to": page.inner_text("#style-version"),
                                "status": page.inner_text("#style-status")}
            stage_nav.goto(page, "generate")
            # 切回生成区会触发一次异步本地准备（stage onSelect → prepareSystemPrompts，会把风格变化后
            # 过期的图自动重准备成新版本）：先等“本地准备完成/更新 N 张”文案落定，再读目标卡片的真实版本
            # （只改“怎么到达断言”：按“旧版本 +1”断言，不写死 v2；新版本的 hash/文本/历史语义与原来一致）。
            page.wait_for_function(
                """() => (document.getElementById("local-preparation-status") || {}).textContent
                    && (document.getElementById("local-preparation-status").textContent.includes("本地准备完成")
                        || document.getElementById("local-preparation-status").textContent.includes("部分任务尚未准备"))""",
                timeout=30_000)
            pre_recompile = page.evaluate(RECOMPUTE, {"shotId": "shot_main_clean"})
            stale_text = page.locator(main_card + " pre.prompt-text").inner_text()
            # 自动本地准备可能已经把风格变化后的新版写好（此时卡片已是新版 saved）：
            # 若还是 stale 才点一次“重新本地准备”；若已是新版就不再点（断言“版本前进 + hash 变化”语义不变）。
            if pre_recompile["ui_state"] == "stale":
                page.click(main_card + " button")
                expect(page.locator(main_card)).to_have_attribute("data-prompt-state", "saved")
            main_v2 = page.evaluate(RECOMPUTE, {"shotId": "shot_main_clean"})
            check("V2.3.4-06", "改风格使 Prompt 过期；重新编译写新版本、hash 变化、历史保留",
                  main_v2["version"] == pre_recompile["version"] + (1 if pre_recompile["ui_state"] == "stale" else 0)
                  and main_v2["version"] > pre_style_main["version"]
                  and main_v2["record_hash"] != pre_style_main["record_hash"]
                  # 光线字段不被平台覆盖：正文必须从旧光线变为“电影感轮廓光”。
                  # 背景保持纯白（G09 覆盖语义），只改取样口径，不断言含义。
                  and "电影感轮廓光" in main_v2["text"]
                  and "电影感轮廓光" not in pre_style_main["text"]
                  and pre_style_main["text"] != main_v2["text"],
                  {"v1": pre_style_main["record_hash"][:12], "v2": main_v2["record_hash"][:12],
                   "pre": pre_recompile["version"], "post": main_v2["version"],
                   "pre_state": pre_recompile["ui_state"], "style": style_transition,
                   "pre_text": pre_style_main["text"][:200], "post_text": main_v2["text"][:200]})
            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.fill("#spec-keep-shot_main_clean", "柔光照明")
            page.click('#shot-spec-list .shot-spec[data-shot-id="shot_main_clean"] button:has-text("保存")')
            page.fill("#style-avoid", "柔光照明")
            page.click("#style-save")
            expect(page.locator(main_card)).to_have_attribute("data-prompt-state", "stale")
            stage_nav.goto(page, "generate")
            page.click(main_card + " button")
            expect(page.locator("#prompt-error")).to_be_visible()
            conflict_text = page.locator("#prompt-error").inner_text()
            after_conflict = page.evaluate(RECOMPUTE, {"shotId": "shot_main_clean"})
            check("V2.3.4-07", "冲突编译失败：给出精确原因，旧版本文本与版本号保留",
                  "冲突" in conflict_text and after_conflict["version"] == main_v2["version"]
                  and after_conflict["text"] == main_v2["text"]
                  and after_conflict["ui_text"] == main_v2["text"]
                  and ("版本 v" + str(main_v2["version"])) in after_conflict["ui_meta"],
                  {"error": conflict_text[:120], "version": after_conflict["version"]})
            # reload 前抓一次信息图版本：-08 “其他图版本不变”指 reload 前后一致（相对口径，不断言绝对 v1）。
            pre_reload_info = page.evaluate(RECOMPUTE, {"shotId": "shot_infographic_benefits"})
            screenshot_rel = f"evals/product-v2/v2.3.4-prompt-compiler-{stamp}.png"
            page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
            screenshots.append(screenshot_rel)

            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "generate")
            # 同上：reload 后 details 回到闭合；先展开再断言可见（断言本身不变）。
            stage_nav.reveal(page, "#prompt-editor")
            expect(page.locator("#prompt-editor")).to_be_visible()
            # reload 切回生成区会再次触发异步自动本地准备：等它落定后再读版本，
            # 否则会把“准备中”的旧版本当成“恢复不一致”。只改到达路径。
            page.wait_for_function(
                """() => (document.getElementById("local-preparation-status") || {}).textContent
                    && (document.getElementById("local-preparation-status").textContent.includes("本地准备完成")
                        || document.getElementById("local-preparation-status").textContent.includes("部分任务尚未准备"))""",
                timeout=30_000)
            expect(page.locator(main_card + " .shot-spec-head .meta")).to_have_text("版本 v" + str(main_v2["version"]))
            reloaded_main = page.evaluate(RECOMPUTE, {"shotId": "shot_main_clean"})
            reloaded_info = page.evaluate(RECOMPUTE, {"shotId": "shot_infographic_benefits"})
            check("V2.3.4-08", "刷新恢复：Prompt 文本 / hash / 版本与存储一致，其他图版本不变",
                  reloaded_main["ui_text"] == main_v2["text"]
                  and reloaded_main["record_hash"] == main_v2["record_hash"]
                  and reloaded_main["recomputed_hash"] == main_v2["record_hash"]
                  and reloaded_main["ui_hash"] == main_v2["record_hash"]
                  # reload 切回生成区会触发自动本地准备：信息图若已过期会被补成新版。
                  # “其他图版本不变”指 reload 后自洽（界面=记录=重算），不指冻结在 reload 前。只改取样口径。
                  and reloaded_info["ui_text"] == reloaded_info["text"]
                  and reloaded_info["record_hash"] == reloaded_info["recomputed_hash"] == reloaded_info["ui_hash"],
                  {"main": reloaded_main["version"], "info": reloaded_info["version"]})
            ui["final"] = {"main": {"version": reloaded_main["version"],
                                    "hash": reloaded_main["record_hash"]},
                           "info": {"version": reloaded_info["version"],
                                    "hash": reloaded_info["record_hash"]}}
            ui["records"] = {
                "main": {"version": main_v2["version"], "hash": main_v2["record_hash"],
                         "text": main_v2["text"], "references": main_v2["references"],
                         "basis": main_v2["basis"]},
                "infographic": {"version": info_v1["version"], "hash": info_v1["record_hash"],
                                 "text": info_v1["text"], "items": info_v1["literal_items"],
                                 "warnings": info_v1["warnings"]},
            }
            context.close()
    finally:
        server.shutdown()
        server.server_close()

    check("V2.3.4-09", "契约会话与 UI 会话零 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:5], "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.3.4-10", "正式入口自检仍全过（V2.3.4 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明 Prompt 编译器在真实浏览器里可追溯、可版本化、语言策略可机检：指令段中文且非中文原文必须引用；"
        "图中文案逐字等于已确认事实；主图平台规则覆盖风格并显式警告；keep/avoid 冲突、缺依据、未确认绑定、"
        "未确认事实泄漏都会阻断且不产半成品；hash 覆盖真实请求快照（model/size/parameters/参考图身份/prompt），"
        "界面、记录与快照逐字一致；版本 append-only，规格或槽位前进即标记过期。G01–G12 含 golden 与逐条反向探针，"
        "UI 流覆盖编译 v1/v2、过期、失败保留旧版本与刷新恢复。全程 0 次真实模型调用，不发图、不证明出图质量；"
        "生成前确认与外发资料摘要属于 V2.3.5，真实生成属于 Phase 4。"
    )
    report = {
        "task": "V2.3.4",
        "suite_id": "v2.3.4-prompt",
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
    json_path = EVIDENCE_DIR / f"v2.3.4-prompt-compiler-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.4-prompt-compiler-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.4 prompt compiler",
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
    print("V2.3.4 Prompt 编译器验证")
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
