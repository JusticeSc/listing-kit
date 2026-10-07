"""V2.5.5 证据：整套一致性报告（0 次真实模型调用）。

检查：
  1) 契约套件 S01–S06（真实 Chromium）：注册表、缺选择、重复与卖点、完整装配与过期、
     视觉漂移与越界拒绝、失败与超限只落 Unknown。
  2) 工作台走查（fake provider）：采用完成后运行整套检查；报告写入 IndexedDB（kind=suite_review）；
     发现可见、可跳到对应图；方案变化后报告过期并可重算；刷新后仍在。
  3) 视觉通道失败演练：只落 UNKNOWN，确定性部分照常。
  4) 正式入口 --check 全过；零意外 console/page/HTTP 错误。

运行：
  uv run --locked python tools/verify_v2_5_5_suite_review.py --label final
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
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

import v2_verify_shared as shared  # noqa: E402  （正式 server/夹具/共同业务操作）
from v2_verify_shared import walk_to_adoption  # noqa: E402
from v2_verify_shared import free_port, read_suite, start_product_server  # noqa: E402






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



    # ---------------- 契约套件 ----------------
    suites: dict = {}
    static_server, base = shared.start_static_server()
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
    reference.write_bytes(shared.png_bytes(900, 900, (36, 92, 160)))

    walkthrough: dict = {}
    with sync_playwright() as pw:
        port = free_port()
        server, _suite_instance = start_product_server(port, suite_scenario="drift")
        try:
            context = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-drift"), headless=True,
                viewport={"width": 1440, "height": 950})
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = shared.collect(page)
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                shots = walk_to_adoption(page, "V255 一致性品", reference)
                # 新流程本地检查与 AI 复核分开（§14.8 按需）：先跑 AI（drift 场景 fake），再跑本地确定性检查。
                page.click("#suite-ai-review-run")
                page.wait_for_function(
                    "() => document.getElementById('suite-review-status')"
                    ".textContent.indexOf('整套检查 v') >= 0",
                    timeout=60_000)
                page.click("#suite-review-run")
                page.wait_for_function(
                    "() => document.getElementById('suite-review-status')"
                    ".textContent.indexOf('整套检查 v') >= 0",
                    timeout=60_000)
                page.wait_for_timeout(300)
                status = page.evaluate(SUITE_STATUS)
                findings = page.evaluate(SUITE_FINDINGS)
                note = page.locator("#suite-review-note").inner_text()
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
                # AI 复核与本地检查各写一版（均为当前报告链）：断最新版存在且身份正确，不钉死版本号。
                check("V2.5.5-05", "报告以 suite_review 文档写入 IndexedDB",
                      len(stored) >= 1 and stored[-1]["document_id"] == "suite_review", stored)
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
        server2, _ = start_product_server(port2, suite_scenario="unknown")
        try:
            context2 = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-unknown"), headless=True,
                viewport={"width": 1440, "height": 950})
            page2 = context2.pages[0] if context2.pages else context2.new_page()
            page2.set_default_timeout(30_000)
            try:
                page2.goto(f"http://127.0.0.1:{port2}/", wait_until="domcontentloaded")
                walk_to_adoption(page2, "V255 失败演练品", reference)
                # unknown 场景同样先跑 AI（落 UNKNOWN），再跑本地确定性检查。
                page2.click("#suite-ai-review-run")
                page2.wait_for_function(
                    "() => document.getElementById('suite-review-status')"
                    ".textContent.indexOf('整套检查 v') >= 0",
                    timeout=60_000)
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
