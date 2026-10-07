#!/usr/bin/env python
"""V2.3.3 证据：StyleSpec / ShotSpec 的编辑、版本与失效传播（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 全部通过 node --check（ESM 语法门）。
  2) 契约套件 F01..F12 在真实 Chromium 全过（含反向探针、失效投影与版本选择）。
  3) 真实正式入口：商品理解 + 套图方案就绪后，「风格与单图规格」解锁并显示保存前影响提示。
  4) 保存公共风格 v1：版本号推进、审核清单立刻出现风格行。
  5) 保存单图规格 v1：只有目标图的版本变化，其他图仍是默认。
  6) 再次保存风格 v2：单图规格版本不受影响（公共风格不写单图文档）。
  7) 恢复风格上一版本：读 v1 内容、写成新版本 v3，历史三条只增不删。
  8) 单图规格第二次保存 v2 → 恢复 v1 内容为 v3，payload 与 v1 一致。
  9) 刷新：风格 v3、单图规格 v3、清单内容原样恢复。
 10) 零 console error / page error；截图落盘；正式入口 --check 仍全过。

运行：
  uv run --locked python tools/verify_v2_3_3_spec_versions.py
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
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/specs-contract.js",
]

EXPECTED_CASES = [f"F{index:02d}" for index in range(1, 13)]
NEGATIVE_CASES = ["F02", "F05", "F08", "F09"]

SPEC_SNAPSHOT = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) return { style: [], shot_specs: {} };
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
  db.close();
  const summarize = (records) => records
    .slice().sort((left, right) => right.version - left.version)
    .map((record) => ({ version: record.version, payload: record.payload }));
  const style = summarize(documents.filter((item) => item.kind === "style_spec"));
  const byShot = {};
  for (const record of documents.filter((item) => item.kind === "shot_spec")) {
    (byShot[record.document_id] = byShot[record.document_id] || []).push(record);
  }
  return {
    style,
    shot_specs: Object.fromEntries(Object.entries(byShot)
      .map(([key, value]) => [key, summarize(value)])),
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
        evidence: [{ kind: "user", ref: "v233-seed" }], depends_on: [],
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
      payload: slot("signature_features", ["304不锈钢", "12小时保温"]),
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
            self._send((HARNESS_DIR / "specs-contract.html").read_bytes(), MIME[".html"])
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


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.3.3 规格层验证")
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
    check("V2.3.3-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"], node_result)

    static_server, static_url = start_static_server()
    suite: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(static_url + "/harness/specs-contract.html",
                          wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.__V2_SPECS_RESULTS__ && "
                    "['passed','failed','crashed'].includes(window.__V2_SPECS_RESULTS__.status)",
                    timeout=60_000,
                )
                suite = page.evaluate("() => window.__V2_SPECS_RESULTS__")
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.3.3-01", "契约套件全部通过且用例清单完整（F01..F12）",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "cases": len(case_ids), "missing": missing,
           "failed": [item["id"] for item in failed_cases],
           "errors": [item.get("error") for item in failed_cases][:3]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.3.3-02", "反向探针确实被执行（风格/单图校验、缺失 shotId、非法版本号）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})

    module = load_server_module()
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port, provider_factory=lambda: FakeSemanticProvider(scenario="ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    ui: dict = {}
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v233-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))
    shot_card = '#shot-spec-list .shot-spec[data-shot-id="shot_main_clean"]'
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品 · 规格版本")
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
            page.click("#suite-seed")
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            # V2.UI.2：风格与单图规格收在「公共风格与单图规格」折叠区里，默认不展开。
            page.click("details:has(#specs-editor) > summary")
            expect(page.locator("#specs-editor")).to_be_visible()
            effect_text = page.locator("#style-effect").inner_text()
            check("V2.3.3-03", "套图方案就绪后规格区解锁；保存前就说明影响范围",
                  "全部 4 张图" in effect_text and "Prompt 版本" in effect_text
                  and "套图计划" in effect_text
                  and page.locator("#style-version").inner_text() == "尚未保存",
                  {"effect": effect_text,
                   "version": page.locator("#style-version").inner_text()})

            page.fill("#style-background", "浅灰无缝背景")
            page.fill("#style-lighting", "柔和顶光")
            page.fill("#style-color-tone", "自然")
            page.fill("#style-composition", "商品居中，留白充足")
            page.fill("#style-avoid", "文字水印")
            page.click("#style-save")
            expect(page.locator("#style-version")).to_have_text("版本 v1")
            expect(page.locator("#style-status")).to_contain_text("已保存 v1")
            checklist_text = page.eval_on_selector("#shot-spec-list", "node => node.textContent")
            shot_specs_texts = page.eval_on_selector_all(
                "#shot-spec-list .shot-spec .shot-spec-head .meta",
                "nodes => nodes.map((node) => node.textContent)")
            after_style = page.evaluate(SPEC_SNAPSHOT)
            check("V2.3.3-04", "保存公共风格 v1：版本推进，全部图片的审核清单出现风格行",
                  after_style["style"][0]["version"] == 1
                  and after_style["style"][0]["payload"]["background"] == "浅灰无缝背景"
                  and "浅灰无缝背景" in checklist_text
                  and "光线：柔和顶光" in checklist_text
                  and all(item == "默认（未保存）" for item in shot_specs_texts),
                  {"style_version": after_style["style"][0]["version"],
                   "shot_meta": shot_specs_texts})

            page.fill("#spec-purpose-shot_main_clean", "主图：完整展示保温杯")
            page.fill("#spec-keep-shot_main_clean", "商品外观与颜色\n标识与文字")
            page.fill("#spec-change-shot_main_clean", "背景")
            page.click(shot_card + ' button:has-text("保存")')
            expect(page.locator(shot_card + " .shot-spec-head .meta")).to_have_text("规格 v1")
            other_meta = page.locator(
                '#shot-spec-list .shot-spec[data-shot-id="shot_infographic_benefits"] '
                ".shot-spec-head .meta").inner_text()
            after_shot = page.evaluate(SPEC_SNAPSHOT)
            main_history = after_shot["shot_specs"]["shot_main_clean"]
            check("V2.3.3-05", "保存单图规格 v1：只有目标图变成 v1，其他图仍是默认",
                  main_history[0]["version"] == 1
                  and main_history[0]["payload"]["purpose"] == "主图：完整展示保温杯"
                  and other_meta == "默认（未保存）"
                  and set(after_shot["shot_specs"].keys()) == {"shot_main_clean"},
                  {"main": main_history[0]["version"], "other": other_meta})

            page.fill("#style-background", "深灰渐变背景")
            page.click("#style-save")
            expect(page.locator("#style-version")).to_have_text("版本 v2")
            after_style_v2 = page.evaluate(SPEC_SNAPSHOT)
            check("V2.3.3-06", "再次保存风格 v2：单图规格版本不受影响（两套文档彼此独立）",
                  after_style_v2["style"][0]["version"] == 2
                  and after_style_v2["shot_specs"]["shot_main_clean"][0]["version"] == 1,
                  {"style": after_style_v2["style"][0]["version"],
                   "shot": after_style_v2["shot_specs"]["shot_main_clean"][0]["version"]})

            page.click("#style-restore")
            expect(page.locator("#style-version")).to_have_text("版本 v3")
            expect(page.locator("#style-status")).to_contain_text("已恢复 v1 的内容")
            after_restore = page.evaluate(SPEC_SNAPSHOT)
            check("V2.3.3-07", "恢复风格上一版本：写为新版本 v3、内容回到 v1、历史只增不删",
                  len(after_restore["style"]) == 3
                  and after_restore["style"][0]["version"] == 3
                  and after_restore["style"][0]["payload"]["background"] == "浅灰无缝背景",
                  {"versions": [item["version"] for item in after_restore["style"]],
                   "background": after_restore["style"][0]["payload"]["background"]})

            page.fill("#spec-purpose-shot_main_clean", "主图：第二次修改")
            page.click(shot_card + ' button:has-text("保存")')
            expect(page.locator(shot_card + " .shot-spec-head .meta")).to_have_text("规格 v2")
            page.click(shot_card + ' button:has-text("恢复上一版本")')
            expect(page.locator(shot_card + " .shot-spec-head .meta")).to_have_text("规格 v3")
            after_shot_restore = page.evaluate(SPEC_SNAPSHOT)
            history = after_shot_restore["shot_specs"]["shot_main_clean"]
            check("V2.3.3-08", "单图规格恢复：v3 payload 等于 v1，历史三条",
                  len(history) == 3 and history[0]["version"] == 3
                  and history[0]["payload"]["purpose"] == history[2]["payload"]["purpose"]
                  and history[0]["payload"]["purpose"] == "主图：完整展示保温杯",
                  {"versions": [item["version"] for item in history],
                   "purpose": history[0]["payload"]["purpose"]})

            screenshot_rel = f"evals/product-v2/v2.3.3-spec-versions-{stamp}.png"
            page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
            screenshots.append(screenshot_rel)

            page.reload(wait_until="networkidle")
            expect(page.locator("#project-view")).to_be_visible()
            stage_nav.goto(page, "plan")
            page.click("details:has(#specs-editor) > summary")
            expect(page.locator("#style-version")).to_have_text("版本 v3")
            expect(page.locator(shot_card + " .shot-spec-head .meta")).to_have_text("规格 v3")
            reloaded_text = page.eval_on_selector("#shot-spec-list", "node => node.textContent")
            after_reload = page.evaluate(SPEC_SNAPSHOT)
            check("V2.3.3-09", "刷新恢复：风格 v3、单图规格 v3、清单与历史原样",
                  "浅灰无缝背景" in reloaded_text and "主图：完整展示保温杯" in reloaded_text
                  and len(after_reload["style"]) == 3
                  and len(after_reload["shot_specs"]["shot_main_clean"]) == 3,
                  {"style_versions": [item["version"] for item in after_reload["style"]],
                   "shot_versions": [item["version"] for item in after_reload["shot_specs"]["shot_main_clean"]]})
            ui["final"] = {
                "style_versions": [item["version"] for item in after_reload["style"]],
                "shot_versions": [item["version"] for item in
                                  after_reload["shot_specs"]["shot_main_clean"]],
            }
            context.close()
    finally:
        server.shutdown()
        server.server_close()

    check("V2.3.3-10", "契约会话与 UI 会话零 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:5], "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.3.3-11", "正式入口自检仍全过（V2.3.3 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明规格层在真实浏览器里可编辑、可回退、影响范围精确：StyleSpec 影响整套（Prompt 版本、审核报告、"
        "一致性报告失效；套图计划与商品理解保留），ShotSpec 只影响目标图（其他图片保留）；版本 append-only，"
        "恢复上一版本写成新版本；审核清单由规格确定性投影。F01–F12 覆盖默认值、两类校验反向探针、差异、"
        "失效投影与回退选版，UI 流覆盖保存 v1/v2、单图独立、回退成 v3 与刷新恢复。全程 0 次真实模型调用。"
        "不证明 Prompt 编译与请求一致性（V2.3.4）、生成前确认（V2.3.5）、真实生成与审核（Phase 4 起）。"
    )
    report = {
        "task": "V2.3.3",
        "suite_id": "v2.3.3-specs",
        "status": status,
        "finished_at": finished_at,
        "model_calls": 0,
        "checks": checks,
        "suite": suite,
        "ui_flow": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshots": screenshots,
        "boundary": boundary,
    }
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.3.3-spec-versions-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.3-spec-versions-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.3 spec versions",
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
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.3.3 规格版本验证")
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
