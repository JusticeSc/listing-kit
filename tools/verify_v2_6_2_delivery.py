"""V2.6.2 证据：浏览器交付 ZIP 与硬门禁（0 次真实模型调用）。

检查：
  1) 静态：ESM 语法门；交付门禁唯一权威（只复用既有测量，不自带第二套哈希/ZIP）；
     界面落点（#delivery-gate / #delivery-unknowns / #deliver-export / #delivery-result）与
     新文档种类 export_record / review_acknowledgement 已登记；无重复 id / 元素键撞车。
  2) 契约套件 D01–D06（真实 Chromium）：正反门禁（缺选择 / 报告缺失或过期 / 未确认 Unknown /
     哈希不符）与交付包往返（ZIP 解包逐文件核对 + 记录身份稳定）。
  3) 工作台走查（fake provider）：采用 + 整套检查 → 门禁全 PASS → 生成交付包下载成功；
     用 Python zipfile/hashlib 独立核对包内容（不依赖产品代码）；export_record 写入 IndexedDB；
     重复生成只追加；刷新后记录仍在；Unknown 未确认时不可导出、确认后可导出；
     候选字节缺失时门禁阻断且不产生新记录。
  4) 正式入口 --check 全过；主链零意外 console/page/HTTP 错误。

运行：
  uv run --locked python tools/verify_v2_6_2_delivery.py --label final
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import zipfile
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


server_module = load_module(ROOT / "app" / "product_v2_server.py", "v262_server")
ui3 = load_module(ROOT / "tools" / "verify_v2_ui_3_frontend.py", "v262_ui3")
v255 = load_module(ROOT / "tools" / "verify_v2_5_5_suite_review.py", "v262_v255")
fake_image = load_module(ROOT / "src" / "providers" / "v2_fake_image.py", "v262_fake_image")
fake_review = load_module(ROOT / "src" / "providers" / "v2_fake_review.py", "v262_fake_review")
fake_semantic = load_module(ROOT / "src" / "providers" / "v2_fake_semantic.py", "v262_fake_semantic")
fake_suite = load_module(ROOT / "src" / "providers" / "v2_fake_suite_review.py", "v262_fake_suite")

EXPORT_GATE_JS = (PRODUCT_DIR / "domain" / "export-gate.js").read_text(encoding="utf-8")
WORKSPACE_JS = (PRODUCT_DIR / "workspace.js").read_text(encoding="utf-8")
INDEX_HTML = (PRODUCT_DIR / "index.html").read_text(encoding="utf-8")
SHARED_JS = (PRODUCT_DIR / "domain" / "shared.js").read_text(encoding="utf-8")
ZIP_JS = (PRODUCT_DIR / "storage" / "zip.js").read_text(encoding="utf-8")
REVIEW_JS = (PRODUCT_DIR / "domain" / "review.js").read_text(encoding="utf-8")

GATE_STATE = """() => ({
  status: (document.getElementById('deliver-status') || {}).textContent || '',
  disabled: (document.getElementById('deliver-export') || {}).disabled,
  findings: [...document.querySelectorAll('#delivery-gate .gate-finding')].map((node) => ({
    rule: node.getAttribute('data-rule-id'),
    severity: node.getAttribute('data-severity'),
    jumps: node.querySelectorAll('button[data-shot-id]').length })),
  unknowns: [...document.querySelectorAll('#delivery-unknowns .gate-unknown')].map((node) => ({
    rule: node.getAttribute('data-rule-id'),
    label: (node.querySelector('button') || {}).textContent || '',
    disabled: (node.querySelector('button') || {}).disabled === true })),
  result: (document.getElementById('delivery-result') || {}).textContent || '',
  rows: [...document.querySelectorAll('#delivery-gate .gate-row')].map((row) => ({
    shot_id: row.getAttribute('data-shot-id'),
    state: row.getAttribute('data-selection-state') })) })"""

READ_DOCS = """async (kind) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('amz-listing-kit-v2');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const rows = await new Promise((resolve, reject) => {
    const tx = db.transaction('documents', 'readonly');
    const out = [];
    tx.objectStore('documents').openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(out); return; }
      if (cursor.value.kind === kind) {
        out.push({ document_id: cursor.value.document_id, version: cursor.value.version,
                   payload: cursor.value.payload });
      }
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  return rows;
}"""

DROP_ONE_ASSET = """async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('amz-listing-kit-v2');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const candidateSha = await new Promise((resolve, reject) => {
    const tx = db.transaction('documents', 'readonly');
    tx.objectStore('documents').openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(null); return; }
      const value = cursor.value;
      if (value.kind === 'candidate' && value.payload && value.payload.asset_sha256) {
        resolve(value.payload.asset_sha256);
        return;
      }
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  if (!candidateSha) { db.close(); return null; }
  const dropped = await new Promise((resolve, reject) => {
    const tx = db.transaction('assets', 'readwrite');
    const store = tx.objectStore('assets');
    store.openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(null); return; }
      if (cursor.value.sha256 === candidateSha) {
        const key = cursor.primaryKey;
        cursor.delete();
        resolve(key);
        return;
      }
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  return dropped;
}"""


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
        try:
            page.wait_for_function(
                f"() => window.{variable} && ['passed','failed','crashed'].includes(window.{variable}.status)",
                timeout=90_000)
        except Exception as error:  # noqa: BLE001 - 套件加载失败也要给出可读证据
            return {"status": "crashed", "cases": [],
                    "error": f"{type(error).__name__}: {str(error).splitlines()[0][:200]}"}
        return page.evaluate(f"() => window.{variable}")
    finally:
        page.close()


def start_product_server(port: int, *, review_scenario: str = "ok", suite_scenario: str = "drift"):
    suite = fake_suite.FakeSuiteReviewProvider(scenario=suite_scenario)
    # 平台有长边下限（platform.min_long_side = 1000px）：交付走查必须用达标尺寸的假图，
    # 否则门禁会被平台下限合法阻断，无法验证「门禁通过后交付」这条路径。
    server = server_module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: fake_semantic.FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: fake_image.FakeImageProvider(scenario="ok", size=1200),
        review_provider_factory=lambda: fake_review.FakeReviewProvider(scenario=review_scenario),
        suite_review_provider_factory=lambda: suite)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, suite


def wait_gate(page, timeout: int = 30_000) -> dict:
    page.wait_for_function(
        "() => document.querySelectorAll('#delivery-gate .gate-finding').length > 0",
        timeout=timeout)
    page.wait_for_timeout(250)
    return page.evaluate(GATE_STATE)


def walk_to_deliver(page, name: str, reference: Path, *, run_vlm: bool = False) -> list[str]:
    """走到交付阶段：资料 → 理解 → 方案 → 生成（可选逐个 VLM 复核）→ 采用 → 整套检查。"""
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
    ui3.wait_terminal(page, shots, timeout=120_000)
    if run_vlm:
        for shot_id in shots:
            button = page.locator(
                f'#attempt-list .attempt-row[data-shot-id="{shot_id}"] button[data-review-action]')
            if button.count() == 0:
                continue
            button.first.click()
            page.wait_for_timeout(700)
    page.click("#stage-next-review")
    for shot_id in shots:
        page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] '
                   'button:has-text("采用候选")')
        page.wait_for_selector("#adopt-submit:not([disabled])", timeout=15_000)
        page.click("#adopt-submit")
        page.wait_for_selector("#adopt-status:not([hidden])", timeout=15_000)
        page.wait_for_timeout(120)
    page.click("#suite-review-run")
    page.wait_for_function(
        "() => document.getElementById('suite-review-status')"
        ".textContent.indexOf('整套检查 v') >= 0",
        timeout=60_000)
    page.click('[data-stage-nav="deliver"]')
    return shots


def download_delivery(page, path: Path) -> dict:
    with page.expect_download(timeout=120_000) as info:
        page.click("#deliver-export")
    download = info.value
    download.save_as(str(path))
    return {"filename": download.suggested_filename, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def inspect_zip(path: Path) -> dict:
    """独立核对（Python zipfile/hashlib，不依赖产品代码）。"""
    with zipfile.ZipFile(path) as archive:
        names = sorted(archive.namelist())
        broken = archive.testzip()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        checks = json.loads(archive.read("checks.json").decode("utf-8"))
        readme = archive.read("README.txt").decode("utf-8")
        images = [item for item in names if item.startswith("images/")]
        digests = {}
        for item in manifest.get("images", []):
            data = archive.read(item["file"])
            digests[item["file"]] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_size": len(data),
                "declared": item["asset_sha256"],
                "declared_size": item.get("byte_size"),
            }
    return {"names": names, "broken": broken, "manifest": manifest, "checks": checks,
            "readme": readme, "images": images, "digests": digests}


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.6.2 交付包与硬门禁验收")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"-{args.label}" if args.label else ""
    evidence_txt = EVIDENCE_DIR / f"v2.6.2-delivery-{stamp}{label}.txt"
    evidence_json = EVIDENCE_DIR / f"v2.6.2-delivery-{stamp}{label}.json"
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    checks: list[dict] = []

    def check(check_id: str, title: str, ok: bool, detail=None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {check_id} {title}" + (
            "" if ok else " :: " + json.dumps(detail, ensure_ascii=False, default=str)[:400]))

    screenshots: list[str] = []

    def shot(page, name: str) -> None:
        path = EVIDENCE_IMAGE_DIR / f"v2.6.2-delivery-{stamp}{label}-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(path.relative_to(ROOT).as_posix())

    # ---------------- 静态守卫 ----------------
    node_files = ["app/product_v2/domain/export-gate.js", "app/product_v2/workspace.js",
                  "app/product_v2/domain/index.js",
                  "evals/product-v2/harness/delivery-gate-contract.js"]
    node_results = []
    for relative in node_files:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)],
                                   cwd=str(ROOT), capture_output=True, text=True, check=False)
        node_results.append({"file": relative, "rc": completed.returncode,
                             "stderr": completed.stderr.strip()[-160:]})
    check("V2.6.2-00", "ESM 语法门（domain / workspace / 契约套件）",
          all(item["rc"] == 0 for item in node_results), node_results)

    html_ids = re.findall(r'id="([^"]+)"', INDEX_HTML)
    duplicate_ids = sorted({item for item in html_ids if html_ids.count(item) > 1})
    element_keys = re.findall(
        r"^\s*([A-Za-z_$][A-Za-z0-9_$]*):\s*document\.getElementById", WORKSPACE_JS, re.M)
    duplicate_keys = sorted({item for item in element_keys if element_keys.count(item) > 1})
    single_authority = (
        'from "./review.js"' in EXPORT_GATE_JS
        and "evaluateExportReadiness" in EXPORT_GATE_JS and "verifyAssetHashes" in EXPORT_GATE_JS
        and "from \"./suite-review.js\"" in EXPORT_GATE_JS
        and "suiteReviewIsCurrent" in EXPORT_GATE_JS and "checkSuiteReviewReport" in EXPORT_GATE_JS
        and "zipSync" not in WORKSPACE_JS and "crc32" not in WORKSPACE_JS
        and "buildZip" in WORKSPACE_JS and "readZip" in ZIP_JS
        and 'export * from "./export-gate.js"' in (PRODUCT_DIR / "domain" / "index.js").read_text(encoding="utf-8")
        and 'export_record: "export_record"' in SHARED_JS
        and 'review_acknowledgement: "review_acknowledgement"' in SHARED_JS
        and 'id="deliver-export"' in INDEX_HTML and 'id="delivery-unknowns"' in INDEX_HTML
        and 'id="delivery-result"' in INDEX_HTML and 'id="delivery-gate"' in INDEX_HTML
        and 'registeredRule' in REVIEW_JS
        and 'rule_id: "export.suite_review_current"' in REVIEW_JS
        and 'rule_id: "export.unknown_acknowledged"' in REVIEW_JS)
    check("V2.6.2-01", "单一权威：复用既有测量；界面落点与新文档种类已登记",
          single_authority and not duplicate_ids and not duplicate_keys,
          {"single_authority": single_authority, "duplicate_ids": duplicate_ids,
           "duplicate_element_keys": duplicate_keys})

    # ---------------- 契约套件 ----------------
    suites: dict = {}
    static_server, base = static_url()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["delivery"] = read_suite(
                    browser, base + "/harness/delivery-gate-contract.html",
                    "__V2_DELIVERY_RESULTS__")
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()
    suite = suites.get("delivery", {})
    case_ids = [item.get("id") for item in suite.get("cases", [])]
    failed = [item for item in suite.get("cases", []) if item.get("status") != "passed"]
    check("V2.6.2-02", "契约套件 D01–D06 全过",
          suite.get("status") == "passed"
          and case_ids == ["D01", "D02", "D03", "D04", "D05", "D06"] and not failed,
          {"status": suite.get("status"), "cases": case_ids,
           "failed": [{"id": item.get("id"), "error": item.get("error")} for item in failed[:3]]})

    # ---------------- 工作台走查（正向） ----------------
    from playwright.sync_api import sync_playwright

    temp_root = Path(tempfile.mkdtemp(prefix="amz-v262-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(ui3.v251.png_bytes(900, 900, (36, 92, 160)))
    downloads = temp_root / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)

    walkthrough: dict = {}
    with sync_playwright() as pw:
        port = free_port()
        server, _suite_instance = start_product_server(port, review_scenario="ok")
        try:
            context = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-main"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = ui3.collect(page)
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                shots = walk_to_deliver(page, "V262 交付品", reference)
                state = wait_gate(page)
                shot(page, "gate-pass")
                blocking = [item for item in state["findings"] if item["severity"] == "BLOCK"]
                check("V2.6.2-03", "工作台交付门禁：无阻断、按钮可用、逐图行完整",
                      not blocking and state["disabled"] is False
                      and len(state["rows"]) == len(shots)
                      and all(row["state"] == "current" for row in state["rows"]),
                      {"status": state["status"], "blocking": blocking,
                       "rows": state["rows"][:3], "findings": state["findings"]})

                first = download_delivery(page, downloads / "delivery-1.zip")
                zoom = inspect_zip(downloads / "delivery-1.zip")
                digest_ok = all(item["sha256"] == item["declared"]
                                and item["byte_size"] == item["declared_size"]
                                for item in zoom["digests"].values())
                expected_names = sorted(zoom["images"] + ["README.txt", "checks.json", "manifest.json"])
                check("V2.6.2-04", "交付包下载成功，Python 独立核对 ZIP 内容与哈希",
                      first["bytes"] > 0 and zoom["broken"] is None
                      and zoom["names"] == expected_names and digest_ok
                      and len(zoom["manifest"]["images"]) == len(shots)
                      and zoom["checks"]["gate_status"] == "ready"
                      and isinstance(zoom["manifest"]["selection_fingerprint"], str)
                      and "shot_" in (zoom["manifest"]["selection_fingerprint"] or "")
                      and "V262 交付品" in zoom["readme"],
                      {"download": first, "names": zoom["names"],
                       "digests": {key: value["sha256"][:12] for key, value in zoom["digests"].items()},
                       "readme_head": zoom["readme"].splitlines()[:4]})

                records = page.evaluate(READ_DOCS, "export_record")
                check("V2.6.2-05", "export_record 以 append-only 文档写入 IndexedDB",
                      len(records) == 1
                      and records[0]["payload"]["zip_sha256"] == first["sha256"]
                      and records[0]["payload"]["zip_bytes"] == first["bytes"]
                      and sorted(records[0]["payload"]["included_shot_ids"]) == sorted(shots),
                      {"records": [{k: item[k] for k in ("document_id", "version")} for item in records]}
                      if len(records) <= 3 else {"count": len(records)})

                second = download_delivery(page, downloads / "delivery-2.zip")
                records2 = page.evaluate(READ_DOCS, "export_record")
                check("V2.6.2-06", "重复生成只追加：两条记录、document_id 与包哈希各自独立",
                      len(records2) == 2
                      and len({item["document_id"] for item in records2}) == 2
                      and sorted(item["payload"]["zip_sha256"] for item in records2)
                      == sorted([first["sha256"], second["sha256"]]),
                      {"ids": [item["document_id"] for item in records2],
                       "sha": [first["sha256"][:12], second["sha256"][:12]]})

                page.reload(wait_until="networkidle")
                page.wait_for_selector("#project-view:not([hidden])", timeout=30_000)
                page.click('[data-stage-nav="deliver"]')
                reload_state = wait_gate(page)
                shot(page, "after-reload")
                check("V2.6.2-07", "刷新后：记录仍在、门禁仍无阻断、最近交付包可见",
                      "最近一次交付包" in reload_state["result"]
                      and second["sha256"][:16] in reload_state["result"]
                      and reload_state["disabled"] is False
                      and not [item for item in reload_state["findings"] if item["severity"] == "BLOCK"],
                      {"result": reload_state["result"][:160], "status": reload_state["status"]})

                dropped = page.evaluate(DROP_ONE_ASSET)
                page.click('[data-stage-nav="review"]')
                page.click('[data-stage-nav="deliver"]')
                broken_state = wait_gate(page)
                records3 = page.evaluate(READ_DOCS, "export_record")
                shot(page, "hash-missing")
                check("V2.6.2-08", "候选字节缺失：门禁阻断、按钮禁用、不产生新记录",
                      broken_state["disabled"] is True
                      and any(item["rule"] == "export.asset_hash_matches" and item["severity"] == "BLOCK"
                              for item in broken_state["findings"])
                      and len(records3) == 2,
                      {"dropped": str(dropped)[:40], "status": broken_state["status"],
                       "findings": broken_state["findings"]})

                unexpected = [item for item in logs["http"] if "/favicon.ico" not in item]
                check("V2.6.2-09", "主链零意外 console / page / HTTP 错误",
                      not logs["console"] and not logs["page"] and not unexpected,
                      {"console": logs["console"][:4], "page": logs["page"][:3],
                       "http": unexpected[:4]})
                walkthrough = {"shots": shots, "first": first, "second": second,
                               "names": zoom["names"]}
            finally:
                context.close()
        finally:
            server.shutdown()
            server.server_close()

        # ---------------- Unknown 确认解锁（反向） ----------------
        port2 = free_port()
        server2, _ = start_product_server(port2, review_scenario="unknown")
        try:
            context2 = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-unknown"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            page2 = context2.pages[0] if context2.pages else context2.new_page()
            page2.set_default_timeout(30_000)
            try:
                page2.goto(f"http://127.0.0.1:{port2}/", wait_until="domcontentloaded")
                walk_to_deliver(page2, "V262 未知品", reference, run_vlm=True)
                blocked = wait_gate(page2)
                shot(page2, "unknown-blocked")
                unlocked = None
                guard = 0
                while guard < 20:
                    pending = page2.locator("#delivery-unknowns .gate-unknown button:not([disabled])")
                    if pending.count() == 0:
                        break
                    pending.first.click()
                    page2.wait_for_timeout(400)
                    guard += 1
                unlocked = wait_gate(page2)
                shot(page2, "unknown-confirmed")
                third = download_delivery(page2, downloads / "delivery-unknown.zip")
                records4 = page2.evaluate(READ_DOCS, "export_record")
                zoom2 = inspect_zip(downloads / "delivery-unknown.zip")
                acked = {item["rule_id"] for item in zoom2["checks"]["acknowledgements"]}
                check("V2.6.2-10", "Unknown 未确认不可导出；逐条确认后门禁通过并可交付",
                      blocked["disabled"] is True
                      and any(item["rule"] == "export.unknown_acknowledged" and item["severity"] == "BLOCK"
                              for item in blocked["findings"])
                      and len(blocked["unknowns"]) >= 1
                      and unlocked["disabled"] is False
                      and not [item for item in unlocked["findings"] if item["severity"] == "BLOCK"]
                      and len(records4) == 1
                      and "vlm.inspection_unavailable" in acked,
                      {"blocked": {"status": blocked["status"][:120], "unknowns": blocked["unknowns"][:3]},
                       "unlocked": {"status": unlocked["status"][:120], "guards": guard},
                       "acked": sorted(acked), "download": third["bytes"]})
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
    check("V2.6.2-11", "正式入口自检全过",
          completed.returncode == 0, {"rc": completed.returncode, "tail": tail})

    passed = sum(1 for item in checks if item["ok"])
    lines = [f"V2.6.2 交付包与硬门禁验收 · {stamp}{label}",
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
