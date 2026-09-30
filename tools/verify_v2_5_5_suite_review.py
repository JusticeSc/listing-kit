"""V2.5.5 证据：基于 SelectionSet 的整套一致性报告（0 次真实模型调用）。

检查：
  1) 静态：ESM/Python 语法门；服务端词表与浏览器 SUITE_VLM_CHECK_TO_RULE 互为镜像；
     合同版本与送审张数上限一致；端点常量一致。
  2) 单一权威：suite-review.js 只复用 review.js 的导出就绪与哈希复算，不自带 PNG 解析/散列；
     index.html 有整套分区；shared.js 登记 suite_review 文档种类。
  3) 契约套件 S01–S06（真实 Chromium）：注册表、缺选择、重复与卖点、完整装配与过期、
     视觉漂移与越界拒绝、失败与超限只落 Unknown。
  4) 工作台走查（fake provider）：采用完成后运行整套检查；报告写入 IndexedDB（kind=suite_review）；
     发现可见、可跳到对应图；方案变化后报告过期并可重算；刷新后仍在。
  5) 视觉通道失败演练：只落 UNKNOWN，确定性部分照常。
  6) 正式入口 --check 全过；零意外 console/page/HTTP 错误。

运行：
  uv run --locked python tools/verify_v2_5_5_suite_review.py --label final
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


server_module = load_module(ROOT / "app" / "product_v2_server.py", "v255_server")
ui3 = load_module(ROOT / "tools" / "verify_v2_ui_3_frontend.py", "v255_ui3")
suite_provider = load_module(ROOT / "src" / "providers" / "v2_fake_suite_review.py", "v255_fake_suite")
fake_image = load_module(ROOT / "src" / "providers" / "v2_fake_image.py", "v255_fake_image")
fake_review = load_module(ROOT / "src" / "providers" / "v2_fake_review.py", "v255_fake_review")
fake_semantic = load_module(ROOT / "src" / "providers" / "v2_fake_semantic.py", "v255_fake_semantic")

SUITE_PY = (ROOT / "src" / "providers" / "v2_suite_review.py").read_text(encoding="utf-8")
SUITE_JS = (PRODUCT_DIR / "domain" / "suite-review.js").read_text(encoding="utf-8")
WORKSPACE_JS = (PRODUCT_DIR / "workspace.js").read_text(encoding="utf-8")
INDEX_HTML = (PRODUCT_DIR / "index.html").read_text(encoding="utf-8")
SHARED_JS = (PRODUCT_DIR / "domain" / "shared.js").read_text(encoding="utf-8")
SERVER_PY = (ROOT / "app" / "product_v2_server.py").read_text(encoding="utf-8")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


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
                self._send(candidate.read_bytes(), MIME.get(candidate.suffix, "application/octet-stream"))
                return
        else:
            candidate = (PRODUCT_DIR / path.lstrip("/")).resolve()
            if str(candidate).startswith(str(PRODUCT_DIR.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(), MIME.get(candidate.suffix, "application/octet-stream"))
                return
        self.send_error(404)


def static_url() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), HarnessHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def read_suite(browser, url: str, variable: str) -> dict:
    page = browser.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function(
            f"() => window.{variable} && ['passed','failed','crashed'].includes(window.{variable}.status)",
            timeout=90_000)
        return page.evaluate(f"() => window.{variable}")
    finally:
        page.close()


def start_product_server(port: int, suite_scenario: str):
    suite = suite_provider.FakeSuiteReviewProvider(scenario=suite_scenario)
    server = server_module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: fake_semantic.FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: fake_image.FakeImageProvider(scenario="ok"),
        review_provider_factory=lambda: fake_review.FakeReviewProvider(scenario="ok"),
        suite_review_provider_factory=lambda: suite)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, suite


def walk_to_adoption(page, name: str, reference: Path) -> list[str]:
    ui3.create_project(page, name, reference)
    page.click("#analyze-run")
    page.wait_for_selector("#slot-list .slot-row", timeout=30_000)
    ui3.confirm_slots(page)
    page.click("#stage-next-understand")
    page.click("#suite-seed")
    page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
    page.click("#stage-next-plan")
    shots = page.evaluate(ui3.SHOT_IDS)
    ui3.compile_all(page, shots)
    page.click("#confirm-action")
    page.wait_for_selector("#confirm-record", timeout=15_000)
    page.click("#batch-run")
    ui3.wait_terminal(page, shots, timeout=90_000)
    page.click("#stage-next-review")
    for shot_id in shots:
        page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] '
                   'button:has-text("采用候选")')
        page.wait_for_selector("#adopt-submit:not([disabled])", timeout=15_000)
        page.click("#adopt-submit")
        page.wait_for_selector("#adopt-status:not([hidden])", timeout=15_000)
        page.wait_for_timeout(120)
    return shots


SUITE_STATUS = "() => document.getElementById('suite-review-status').textContent"
SUITE_FINDINGS = """() => [...document.querySelectorAll('#suite-review-findings .suite-finding')]
  .map((node) => ({ rule: node.getAttribute('data-rule-id'),
                    severity: node.getAttribute('data-severity'),
                    jumps: node.querySelectorAll('button[data-shot-id]').length }))"""


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.5.5 整套一致性验收")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"-{args.label}" if args.label else ""
    evidence_txt = EVIDENCE_DIR / f"v2.5.5-suite-review-{stamp}{label}.txt"
    evidence_json = EVIDENCE_DIR / f"v2.5.5-suite-review-{stamp}{label}.json"
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    checks: list[dict] = []

    def check(check_id: str, title: str, ok: bool, detail=None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {check_id} {title}" + (
            "" if ok else " :: " + json.dumps(detail, ensure_ascii=False, default=str)[:400]))

    screenshots: list[str] = []

    def shot(page, name: str) -> None:
        path = EVIDENCE_IMAGE_DIR / f"v2.5.5-suite-review-{stamp}{label}-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(path.relative_to(ROOT).as_posix())

    # ---------------- 静态守卫 ----------------
    node_files = ["app/product_v2/domain/suite-review.js", "app/product_v2/workspace.js",
                  "app/product_v2/app.js", "evals/product-v2/harness/suite-review-contract.js"]
    node_results = []
    for relative in node_files:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)],
                                   cwd=str(ROOT), capture_output=True, text=True, check=False)
        node_results.append({"file": relative, "rc": completed.returncode,
                             "stderr": completed.stderr.strip()[-160:]})
    check("V2.5.5-00", "ESM 语法门（domain / workspace / harness）",
          all(item["rc"] == 0 for item in node_results), node_results)

    py_checks = re.search(r"SUITE_VLM_CHECKS = \(([^)]+)\)", SUITE_PY)
    js_checks = re.search(r"SUITE_VLM_CHECK_TO_RULE = Object\.freeze\(\{([^}]+)\}",
                          SUITE_JS, re.S)
    py_keys = sorted(re.findall(r'"([a-z_]+)"', py_checks.group(1))) if py_checks else []
    js_keys = sorted(re.findall(r"^\s*([a-z_]+):", js_checks.group(1), re.M)) if js_checks else []
    py_contract = re.search(r'SUITE_REVIEW_CONTRACT_VERSION = "([^"]+)"', SUITE_PY)
    js_contract = re.search(r'SUITE_REVIEW_CONTRACT_VERSION = "([^"]+)"', SUITE_JS)
    js_max = re.search(r"SUITE_MAX_IMAGES = (\d+)", SUITE_JS)
    py_max = re.search(r"MAX_SUITE_IMAGES = (\d+)", SUITE_PY)
    mirror_ok = (py_keys == js_keys and bool(py_keys) and py_contract and js_contract
                 and py_contract.group(1) == js_contract.group(1)
                 and js_max and py_max and js_max.group(1) == py_max.group(1)
                 and 'SUITE_REVIEW_PATH = "/api/v2/review/suite"' in WORKSPACE_JS
                 and 'SUITE_REVIEW_PATH = "/api/v2/review/suite"' in SERVER_PY)
    check("V2.5.5-01", "服务端词表/合同版本/张数上限/端点与浏览器互为镜像",
          mirror_ok, {"py": py_keys, "js": js_keys,
                      "contract": [py_contract and py_contract.group(1),
                                   js_contract and js_contract.group(1)],
                      "max": [py_max and py_max.group(1), js_max and js_max.group(1)]})

    reuse_ok = ('from "./review.js"' in SUITE_JS
                and "evaluateExportReadiness" in SUITE_JS and "verifyAssetHashes" in SUITE_JS
                and "parsePngHeader" not in SUITE_JS and "crc32" not in SUITE_JS
                and "assembleSuiteReview(" in WORKSPACE_JS
                and 'id="suite-review-status"' in INDEX_HTML and 'id="suite-review-run"' in INDEX_HTML
                and 'id="suite-review-findings"' in INDEX_HTML
                and 'suite_review: "suite_review"' in SHARED_JS)
    html_ids = re.findall(r'id="([^"]+)"', INDEX_HTML)
    duplicate_ids = sorted({item for item in html_ids if html_ids.count(item) > 1})
    # 元素表键名撞车曾让方案阶段的错误提示写进审核阶段的节点（真实缺陷，2026-10-01）。
    element_keys = re.findall(
        r"^\s*([A-Za-z_$][A-Za-z0-9_$]*):\s*document\.getElementById", WORKSPACE_JS, re.M)
    duplicate_keys = sorted({item for item in element_keys if element_keys.count(item) > 1})
    check("V2.5.5-02", "单一权威：复用既有测量；界面落点与文档种类已登记",
          reuse_ok and not duplicate_ids and not duplicate_keys, {"len_suite_js": len(SUITE_JS),
                                           "duplicate_ids": duplicate_ids,
                                           "duplicate_element_keys": duplicate_keys})

    # ---------------- 契约套件 ----------------
    suites: dict = {}
    static_server, base = static_url()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["suite"] = read_suite(
                    browser, base + "/harness/suite-review-contract.html", "__V2_SUITE_RESULTS__")
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()
    suite = suites.get("suite", {})
    case_ids = [item.get("id") for item in suite.get("cases", [])]
    failed = [item for item in suite.get("cases", []) if item.get("status") != "passed"]
    check("V2.5.5-03", "契约套件 S01–S06 全过",
          suite.get("status") == "passed"
          and case_ids == ["S01", "S02", "S03", "S04", "S05", "S06"] and not failed,
          {"status": suite.get("status"), "cases": case_ids,
           "failed": [{"id": item.get("id"), "error": item.get("error")} for item in failed[:3]]})

    # ---------------- 工作台走查 ----------------
    from playwright.sync_api import sync_playwright

    temp_root = Path(tempfile.mkdtemp(prefix="amz-v255-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(ui3.v251.png_bytes(900, 900, (36, 92, 160)))

    walkthrough: dict = {}
    with sync_playwright() as pw:
        port = free_port()
        server, _suite_instance = start_product_server(port, "drift")
        try:
            context = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-drift"), headless=True,
                viewport={"width": 1440, "height": 950})
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = ui3.collect(page)
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                shots = walk_to_adoption(page, "V255 一致性品", reference)
                page.click("#suite-review-run")
                page.wait_for_function(
                    "() => document.getElementById('suite-review-status')"
                    ".textContent.indexOf('整套检查 v') >= 0",
                    timeout=60_000)
                page.wait_for_timeout(300)
                status = page.evaluate(SUITE_STATUS)
                findings = page.evaluate(SUITE_FINDINGS)
                note = page.locator("#suite-review-note").inner_text()
                shot(page, "current")
                check("V2.5.5-04", "工作台整套检查：报告当前、视觉已核对、发现可见",
                      "整套检查 v2.5.5" in status and "视觉复核已完成" in status
                      and any(item["severity"] == "HIGH_RISK" for item in findings)
                      and any(item["severity"] == "WARNING" for item in findings)
                      and all(item["jumps"] >= 1 for item in findings)
                      and "fake-qwen-vl-max" in note,
                      {"status": status, "findings": findings, "note": note})
                stored = page.evaluate(
                    """async () => {
                         const db = await new Promise((resolve, reject) => {
                           const request = indexedDB.open('amz-listing-kit-v2');
                           request.onsuccess = () => resolve(request.result);
                           request.onerror = () => reject(request.error);
                         });
                         const docs = await new Promise((resolve, reject) => {
                           const tx = db.transaction('documents', 'readonly');
                           const rows = [];
                           tx.objectStore('documents').openCursor().onsuccess = (event) => {
                             const cursor = event.target.result;
                             if (!cursor) { resolve(rows); return; }
                             rows.push({ kind: cursor.value.kind, document_id: cursor.value.document_id,
                                         version: cursor.value.version });
                             cursor.continue();
                           };
                           tx.onerror = () => reject(tx.error);
                         });
                         db.close();
                         return docs.filter((row) => row.kind === 'suite_review');
                       }""")
                check("V2.5.5-05", "报告以 suite_review 文档写入 IndexedDB",
                      len(stored) == 1 and stored[0]["document_id"] == "suite_review", stored)
                localized = page.evaluate(
                    """() => {
                         const box = document.getElementById('suite-review-findings');
                         const buttons = [...box.querySelectorAll('button[data-shot-id]')]
                           .map((node) => ({ text: (node.textContent || '').trim(),
                                             shot: node.dataset.shotId }));
                         return { text: (box.textContent || ''), buttons: buttons };
                       }""")
                check("V2.5.5-12",
                      "整套发现「定位」按钮本地化：按钮带图名、界面不出现裸 shot_id",
                      len(localized["buttons"]) >= 1
                      and "shot_" not in localized["text"]
                      and all(item["text"].startswith("定位：")
                              and item["shot"] not in item["text"]
                              for item in localized["buttons"]),
                      {"buttons": localized["buttons"][:6],
                       "has_raw_shot_id": "shot_" in localized["text"]})
                jump = page.locator('#suite-review-findings .suite-finding '
                                    'button[data-shot-id]').first
                target_shot = jump.get_attribute("data-shot-id")
                jump.click()
                page.wait_for_timeout(250)
                focused = page.evaluate(
                    """(shotId) => ({
                         stage: (document.querySelector('#stage-nav [data-stage-nav].is-current')
                           || {dataset:{}}).dataset.stageNav,
                         visible: !!document.querySelector(
                           '#review-list .review-card[data-shot-id="' + shotId + '"]') })""",
                    target_shot)
                check("V2.5.5-06", "发现可跳转到对应图行",
                      focused["stage"] == "review" and focused["visible"] is True,
                      {"shot": target_shot, "focused": focused})
                page.click('[data-stage-nav="plan"]')
                first_shot = shots[0]
                page.click(f'#shot-list .shot-row[data-shot-id="{first_shot}"] button:has-text("复制")')
                page.wait_for_timeout(300)
                page.click('[data-stage-nav="review"]')
                page.wait_for_timeout(300)
                stale_status = page.evaluate(SUITE_STATUS)
                page.click("#suite-review-run")
                page.wait_for_function(
                    "() => document.getElementById('suite-review-status')"
                    ".textContent.indexOf('整套检查 v') >= 0",
                    timeout=60_000)
                page.wait_for_timeout(300)
                rerun_status = page.evaluate(SUITE_STATUS)
                shot(page, "rerun")
                check("V2.5.5-07", "方案变化后报告过期并可重算为当前",
                      "已过期" in stale_status and "整套检查 v2.5.5" in rerun_status
                      and "已过期" not in rerun_status,
                      {"stale": stale_status, "rerun": rerun_status})
                page.reload(wait_until="networkidle")
                page.wait_for_selector("#project-view:not([hidden])", timeout=20_000)
                page.click('[data-stage-nav="review"]')
                page.wait_for_timeout(500)
                reload_status = page.evaluate(SUITE_STATUS)
                reload_findings = page.evaluate(SUITE_FINDINGS)
                check("V2.5.5-08", "刷新后报告仍在且仍是当前",
                      "整套检查 v2.5.5" in reload_status and "已过期" not in reload_status,
                      {"status": reload_status, "findings": len(reload_findings)})
                unexpected = [item for item in logs["http"] if "/favicon.ico" not in item]
                check("V2.5.5-09", "主链零意外 console / page / HTTP 错误",
                      not logs["console"] and not logs["page"] and not unexpected,
                      {"console": logs["console"][:4], "page": logs["page"][:3],
                       "http": unexpected[:4]})
                walkthrough = {"findings": findings}
            finally:
                context.close()
        finally:
            server.shutdown()
            server.server_close()

        port2 = free_port()
        server2, _ = start_product_server(port2, "unknown")
        try:
            context2 = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-unknown"), headless=True,
                viewport={"width": 1440, "height": 950})
            page2 = context2.pages[0] if context2.pages else context2.new_page()
            page2.set_default_timeout(30_000)
            try:
                page2.goto(f"http://127.0.0.1:{port2}/", wait_until="domcontentloaded")
                walk_to_adoption(page2, "V255 失败演练品", reference)
                page2.click("#suite-review-run")
                page2.wait_for_function(
                    "() => document.getElementById('suite-review-status')"
                    ".textContent.indexOf('整套检查 v') >= 0",
                    timeout=60_000)
                page2.wait_for_timeout(300)
                status2 = page2.evaluate(SUITE_STATUS)
                findings2 = page2.evaluate(SUITE_FINDINGS)
                shot(page2, "unknown")
                check("V2.5.5-10", "视觉通道失败：只落 UNKNOWN，确定性部分照常",
                      "视觉复核未完成（Unknown）" in status2
                      and any(item["rule"] == "vlm.suite_inspection_unavailable" for item in findings2),
                      {"status": status2, "findings": findings2})
            finally:
                context2.close()
        finally:
            server2.shutdown()
            server2.server_close()

    # ---------------- 正式入口自检 ----------------
    completed = subprocess.run([sys.executable, "app/server.py", "--check"], cwd=str(ROOT),
                               capture_output=True, text=True, check=False, encoding="utf-8",
                               errors="replace")
    tail = (completed.stdout or "").strip().splitlines()[-3:]
    check("V2.5.5-11", "正式入口自检全过且含整套复核路由",
          completed.returncode == 0 and any("整套复核" in line for line in tail),
          {"rc": completed.returncode, "tail": tail})

    passed = sum(1 for item in checks if item["ok"])
    lines = [f"V2.5.5 整套一致性验收 · {stamp}{label}",
             f"结果：{passed}/{len(checks)} 通过", ""]
    for item in checks:
        lines.append(f"[{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if item["detail"] is not None:
            lines.append("       " + json.dumps(item["detail"], ensure_ascii=False, default=str)[:600])
    lines += ["", "SCREENSHOTS", *[f"- {path}" for path in screenshots]]
    evidence_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    evidence_json.write_text(json.dumps(
        {"stamp": stamp, "label": args.label, "checks": checks, "screenshots": screenshots,
         "suite": suite, "walkthrough": walkthrough},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines[-6:]))
    print(f"证据：{evidence_txt.relative_to(ROOT).as_posix()}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
