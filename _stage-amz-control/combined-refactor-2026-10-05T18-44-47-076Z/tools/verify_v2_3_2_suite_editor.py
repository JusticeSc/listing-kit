#!/usr/bin/env python
"""V2.3.2 证据：可增删复排的套图编辑器（纯浏览器状态，0 次真实模型调用）。

检查：
  1) domain / workspace / harness 全部通过 node --check（ESM 语法门）。
  2) 契约套件 E01..E12 在真实 Chromium 全过（含反向探针与失败原子）。
  3) 真实正式入口 + 真实 Chromium：空白建项目 → 上传主参考图 → 商品资料 → 关键事实确认
     → 套图规划卡片解锁。
  4) 生成推荐方案：张数、顺序、状态行与存储版本一致。
  5) 复制 / 下移 / 删除副本：界面与存储版本同步推进。
  6) 删除最后一张必需图被拒：错误可见、行数不变、存储版本不变（事务失败不改旧计划）。
  7) 添加自定义图与「被阻断模板」（对比图缺竞品图），逐行显示精确原因。
  8) 刷新后：行顺序、数量与存储版本原样恢复。
  9) 整个会话零 console error / page error；截图落盘。
 10) 正式入口 app/server.py --check 仍全过。

运行：
  uv run --locked python tools/verify_v2_3_2_suite_editor.py
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
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/suite-editor-contract.js",
]

EXPECTED_CASES = [f"E{index:02d}" for index in range(1, 13)]
NEGATIVE_CASES = ["E02", "E04", "E06", "E07", "E08", "E09"]

DB_SNAPSHOT = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) return { projects: [], documents: [] };
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
  const projects = await read("projects");
  const documents = await read("documents");
  db.close();
  const latest = new Map();
  for (const record of documents) {
    const key = record.kind + "/" + record.document_id;
    const current = latest.get(key);
    if (!current || record.version > current.version) latest.set(key, record);
  }
  return {
    projects: projects.map((item) => ({
      project_id: item.project_id, name: item.name, state: item.state,
    })),
    documents: [...latest.values()].map((item) => ({
      kind: item.kind, document_id: item.document_id, version: item.version,
      shots: item.kind === "suite_plan" && item.payload && Array.isArray(item.payload.shots)
        ? item.payload.shots.map((shot) => shot.shot_id) : null,
    })),
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
        evidence: [{ kind: "user", ref: "v232-seed" }], depends_on: [],
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
    return { slots: ["product_name", "product_category", "signature_features"] };
  } finally {
    opened.close();
  }
}
"""

SHOT_IDS = """
() => [...document.querySelectorAll("#shot-list .shot-row")].map((node) => node.dataset.shotId)
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
            self._send((HARNESS_DIR / "suite-editor-contract.html").read_bytes(), MIME[".html"])
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
    parser = argparse.ArgumentParser(description="V2.3.2 套图编辑器验证")
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

    def suite_doc(snapshot: dict) -> dict | None:
        return next((item for item in snapshot.get("documents", [])
                     if item.get("kind") == "suite_plan"), None)

    node_result = run_node_checks()
    check("V2.3.2-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
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
                page.goto(static_url + "/harness/suite-editor-contract.html",
                          wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.__V2_SUITE_EDITOR_RESULTS__ && "
                    "['passed','failed','crashed'].includes(window.__V2_SUITE_EDITOR_RESULTS__.status)",
                    timeout=60_000,
                )
                suite = page.evaluate("() => window.__V2_SUITE_EDITOR_RESULTS__")
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.3.2-01", "契约套件全部通过且用例清单完整（E01..E12）",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "cases": len(case_ids), "missing": missing,
           "failed": [item["id"] for item in failed_cases],
           "errors": [item.get("error") for item in failed_cases][:3]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.3.2-02",
          "反向探针确实被执行（空计划 / 越界 / 最后必需图 / 边界排序 / 不变量 / 失败原子）",
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
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v232-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品 · 套图编辑器")
            page.click("#create-project")
            # R3.3：新建即打开。
            expect(page.locator("#project-view")).to_be_visible()

            page.set_input_files("#ref-file", str(reference))
            expect(page.locator("#ref-list .ref-row")).to_have_count(1)
            page.fill("#intake-name", "便携保温杯")
            page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
            page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
            page.wait_for_timeout(1200)
            opened = page.evaluate(DB_SNAPSHOT)
            project_id = opened["projects"][0]["project_id"]
            ui["seeded_slots"] = page.evaluate(SEED_SLOTS, project_id)
            page.reload(wait_until="networkidle")
            expect(page.locator("#project-view")).to_be_visible()
            expect(page.locator("#suite-editor")).to_be_visible()
            expect(page.locator("#suite-locked")).to_be_hidden()
            expect(page.locator("#suite-empty")).to_be_visible()
            after_open = page.evaluate(DB_SNAPSHOT)
            check("V2.3.2-03", "商品理解就绪后套图编辑器解锁，空方案状态明确",
                  after_open["projects"][0]["state"] == "PLAN_REVIEW"
                  and page.locator("#shot-list .shot-row").count() == 0
                  and "还没有套图方案" in page.locator("#suite-empty").inner_text(),
                  {"state": after_open["projects"][0]["state"],
                   "empty": page.locator("#suite-empty").inner_text()})

            page.click("#suite-seed")
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            ids_seeded = page.evaluate(SHOT_IDS)
            status_text = page.locator("#suite-status").inner_text()
            doc_after_seed = suite_doc(page.evaluate(DB_SNAPSHOT))
            check("V2.3.2-04", "生成推荐方案：4 张按模板 order 落库，状态行与存储一致",
                  ids_seeded == ["shot_main_clean", "shot_infographic_benefits",
                                 "shot_scene_lifestyle", "shot_detail_material"]
                  and doc_after_seed is not None and doc_after_seed["version"] == 1
                  and doc_after_seed["shots"] == ids_seeded and "共 4 张" in status_text,
                  {"ids": ids_seeded, "status": status_text,
                   "version": doc_after_seed["version"] if doc_after_seed else None})

            page.click('#shot-list .shot-row[data-shot-id="shot_infographic_benefits"] '
                       'button:has-text("复制")')
            expect(page.locator("#shot-list .shot-row")).to_have_count(5)
            copy_id = "shot_infographic_benefits_copy"
            page.click('#shot-list .shot-row[data-shot-id="shot_main_clean"] button:has-text("下移")')
            expect(page.locator("#shot-list .shot-row").first).to_have_attribute(
                "data-shot-id", "shot_infographic_benefits")
            page.click(f'#shot-list .shot-row[data-shot-id="{copy_id}"] button:has-text("删除")')
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            ids_after_ops = page.evaluate(SHOT_IDS)
            doc_after_ops = suite_doc(page.evaluate(DB_SNAPSHOT))
            check("V2.3.2-05", "复制 / 下移 / 删除副本：界面顺序与存储版本同步推进",
                  ids_after_ops == ["shot_infographic_benefits", "shot_main_clean",
                                    "shot_scene_lifestyle", "shot_detail_material"]
                  and doc_after_ops is not None and doc_after_ops["version"] >= 4
                  and doc_after_ops["shots"] == ids_after_ops,
                  {"ids": ids_after_ops,
                   "version": doc_after_ops["version"] if doc_after_ops else None})

            version_before_refusal = doc_after_ops["version"]
            page.click('#shot-list .shot-row[data-shot-id="shot_main_clean"] button:has-text("删除")')
            expect(page.locator("#suite-error")).to_be_visible()
            error_text = page.locator("#suite-error").inner_text()
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            doc_after_refusal = suite_doc(page.evaluate(DB_SNAPSHOT))
            check("V2.3.2-06", "删除最后一张必需图被拒：错误可见、行数与存储版本都不变",
                  "必需图" in error_text
                  and doc_after_refusal is not None
                  and doc_after_refusal["version"] == version_before_refusal,
                  {"error": error_text, "version": version_before_refusal})

            page.click("#suite-custom-toggle")
            page.fill("#suite-custom-label", "赠品特写")
            page.fill("#suite-custom-intent", "展示随附杯刷")
            page.click("#suite-custom-save")
            expect(page.locator("#shot-list .shot-row")).to_have_count(5)
            page.select_option("#suite-template", "comparison_competitor")
            hint_text = page.locator("#suite-template-hint").inner_text()
            page.click("#suite-add-template")
            expect(page.locator("#shot-list .shot-row")).to_have_count(6)
            blocked_row = page.locator(
                '#shot-list .shot-row[data-shot-id="shot_comparison_competitor"]')
            blocked_text = blocked_row.inner_text()
            check("V2.3.2-07", "自定义图与「被阻断模板」都可以加入，阻断原因逐行可见",
                  "competitor" in hint_text
                  and blocked_row.get_attribute("data-blocked") == "true"
                  and "competitor" in blocked_text
                  and "赠品特写" in page.locator("#shot-list").inner_text(),
                  {"hint": hint_text, "blocked": blocked_text[:160]})

            ids_before_reload = page.evaluate(SHOT_IDS)
            doc_before_reload = suite_doc(page.evaluate(DB_SNAPSHOT))
            version_before_reload = doc_before_reload["version"]
            screenshot_rel = f"evals/product-v2/v2.3.2-suite-editor-{stamp}.png"
            page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
            screenshots.append(screenshot_rel)

            page.reload(wait_until="networkidle")
            expect(page.locator("#project-view")).to_be_visible()
            expect(page.locator("#shot-list .shot-row")).to_have_count(6)
            ids_after_reload = page.evaluate(SHOT_IDS)
            doc_after_reload = suite_doc(page.evaluate(DB_SNAPSHOT))
            check("V2.3.2-08", "刷新恢复：行顺序、数量与存储版本原样恢复",
                  ids_after_reload == ids_before_reload
                  and doc_after_reload is not None
                  and doc_after_reload["version"] == version_before_reload,
                  {"ids": ids_after_reload,
                   "version": doc_after_reload["version"] if doc_after_reload else None})
            ui["ids_before_reload"] = ids_before_reload
            ui["version"] = version_before_reload
            context.close()
    finally:
        server.shutdown()
        server.server_close()

    check("V2.3.2-09", "契约会话与 UI 会话零 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:5], "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.3.2-10", "正式入口自检仍全过（V2.3.2 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明套图计划在真实浏览器里可增删复排并原样恢复：shots 数组即顺序、至少保留 1 张必需图、"
        "自定义图可选、失败操作不改旧计划与存储版本；E01–E12 覆盖操作语义、不变量反向探针与事务原子性，"
        "UI 流覆盖解锁、推荐播种、复制、下移、删除、被拒删除、自定义图、被阻断模板与刷新恢复。"
        "全程 0 次真实模型调用。不证明 StyleSpec/ShotSpec 版本与失效传播（V2.3.3）、Prompt 编译与真实请求"
        "（V2.3.4）、生成前确认（V2.3.5），也不证明陌生试用者的可理解性。"
    )
    report = {
        "task": "V2.3.2",
        "suite_id": "v2.3.2-suite-editor",
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
    json_path = EVIDENCE_DIR / f"v2.3.2-suite-editor-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.2-suite-editor-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.2 suite editor",
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
    print("V2.3.2 套图编辑器验证")
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
