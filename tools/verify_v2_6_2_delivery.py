"""V2.6.2 证据：浏览器交付 ZIP 与硬门禁（0 次真实模型调用）。

检查：
  1) 契约套件 D01–D06（真实 Chromium）：正反门禁（缺选择 / 报告缺失或过期 / 未确认 Unknown /
     哈希不符）与交付包往返（ZIP 解包逐文件核对 + 记录身份稳定）。
  2) 工作台走查（fake provider）：采用 + 整套检查 → 门禁全 PASS → 生成交付包下载成功；
     用 Python zipfile/hashlib 独立核对包内容（不依赖产品代码）；export_record 写入 IndexedDB；
     重复生成只追加；刷新后记录仍在；Unknown 未确认时不可导出、确认后可导出；
     候选字节缺失时门禁阻断且不产生新记录。
  3) 正式入口 --check 全过；主链零意外 console/page/HTTP 错误。

运行：
  uv run --locked python tools/verify_v2_6_2_delivery.py --label final
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"

import v2_verify_shared as shared  # noqa: E402  （正式 server/夹具/共同业务操作）
import v2_stage_nav as stage_nav  # noqa: E402  （既有公共导航）

from v2_verify_shared import (  # noqa: E402
    download_delivery, inspect_zip, wait_gate, walk_to_deliver, read_suite,
    free_port, start_product_server,
)



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
  // 有意破坏测试：直接改原生 IDB 演练字节缺失门禁（产品 API 不提供删资产入口）。
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

DROP_SUITE_REPORT = """async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('amz-listing-kit-v2');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const removed = await new Promise((resolve, reject) => {
    const tx = db.transaction('documents', 'readwrite');
    const store = tx.objectStore('documents');
    let count = 0;
    store.openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(count); return; }
      if (cursor.value.kind === 'suite_review') { cursor.delete(); count += 1; }
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  return removed;
}"""










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



    # ---------------- 契约套件 ----------------
    suites: dict = {}
    static_server, base = shared.start_static_server()
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
    reference.write_bytes(shared.png_bytes(900, 900, (36, 92, 160)))
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
            logs = shared.collect(page)
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                shots, walk_probes = walk_to_deliver(page, "V262 交付品", reference)
                state = wait_gate(page)
                shot(page, "gate-pass")
                blocking = [item for item in state["findings"] if item["severity"] == "BLOCK"]
                check("V2.6.2-03", "工作台交付门禁：无阻断、按钮可用、逐图行完整",
                      not blocking and state["disabled"] is False
                      and len(state["rows"]) == len(shots)
                      and all(row["state"] == "current" for row in state["rows"]),
                      {"status": state["status"], "blocking": blocking,
                       "rows": state["rows"][:3], "findings": state["findings"]})

                # V2.6.15：交付页把「整套检查结论」摆到导出按钮前面；可选 AI 缺席记 not_run，不阻断交付。
                suite_reports = page.evaluate(READ_DOCS, "suite_review")
                stored_findings = []
                if suite_reports:
                    payload = suite_reports[-1]["payload"] or {}
                    stored_findings = [{"rule": item.get("rule_id"), "severity": item.get("severity")}
                                       for item in payload.get("findings", [])
                                       if item.get("severity") != "PASS"]
                review_side = walk_probes.get("suite_review", {})
                deliver_side = walk_probes.get("suite_deliver", {})
                suite_vlm = ((suite_reports[-1]["payload"] or {}).get("vlm") or {}) if suite_reports else {}
                check("V2.6.2-13",
                      "交付页投影整套检查结论：摘要 + 非 PASS 发现（带定位）与存储报告逐条一致；"
                      "可选 AI 未跑记 not_run 不阻断",
                      "整套检查" in deliver_side.get("status", "")
                      and [(item["rule"], item["severity"]) for item in deliver_side.get("findings", [])]
                      == [(item["rule"], item["severity"]) for item in review_side.get("findings", [])]
                      and [(item["rule"], item["severity"]) for item in deliver_side.get("findings", [])]
                      == [(item["rule"], item["severity"]) for item in stored_findings]
                      and all(item["jumps"] >= 1 for item in deliver_side.get("findings", []))
                      and suite_vlm.get("outcome") == "not_run",
                      {"status": deliver_side.get("status"),
                       "deliver": deliver_side.get("findings"),
                       "review": review_side.get("findings"),
                       "stored": stored_findings, "vlm": suite_vlm})

                first = download_delivery(page, downloads / "delivery-1.zip")
                zoom = inspect_zip(downloads / "delivery-1.zip")
                digest_ok = all(item["sha256"] == item["declared"]
                                and item["byte_size"] == item["declared_size"]
                                for item in zoom["digests"].values())
                expected_names = sorted(zoom["images"] + ["README.txt", "checks.json", "manifest.json"])
                frozen_by_action = {item["action_id"]: item
                                    for item in walk_probes.get("b01_manifest_provenance", [])}
                provenance_ok = all(
                    item.get("prompt_version") == (frozen_by_action.get(item.get("attempt_action_id")) or {}).get("prompt_version")
                    and item.get("prompt_hash") == (frozen_by_action.get(item.get("attempt_action_id")) or {}).get("prompt_hash")
                    for item in zoom["manifest"]["images"])
                check("V2.6.2-04", "交付包下载成功，Python 独立核对 ZIP 内容与哈希",
                      first["bytes"] > 0 and zoom["broken"] is None
                      and zoom["names"] == expected_names and digest_ok
                      and len(zoom["manifest"]["images"]) == len(shots)
                      and all(item.get("attempt_state") == "succeeded"
                              for item in zoom["manifest"]["images"])
                      and provenance_ok
                      and zoom["checks"]["gate_status"] == "ready"
                      and isinstance(zoom["manifest"]["selection_fingerprint"], str)
                      and "shot_" in (zoom["manifest"]["selection_fingerprint"] or "")
                      and "V262 交付品" in zoom["readme"],
                      {"download": first, "names": zoom["names"],
                       "digests": {key: value["sha256"][:12] for key, value in zoom["digests"].items()},
                       "attempt_states": [item.get("attempt_state")
                                          for item in zoom["manifest"]["images"]],
                       "provenance": [(item.get("shot_id"), item.get("prompt_version"),
                                       str(item.get("prompt_hash"))[:12])
                                      for item in zoom["manifest"]["images"]],
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
                stage_nav.goto(page, "deliver")
                reload_state = wait_gate(page)
                shot(page, "after-reload")
                check("V2.6.2-07", "刷新后：记录仍在、门禁仍无阻断、最近交付包可见",
                      "最近一次交付包" in reload_state["result"]
                      and second["sha256"][:16] in reload_state["result"]
                      and reload_state["disabled"] is False
                      and not [item for item in reload_state["findings"] if item["severity"] == "BLOCK"],
                      {"result": reload_state["result"][:160], "status": reload_state["status"]})

                dropped = page.evaluate(DROP_ONE_ASSET)
                stage_nav.goto(page, "review")
                stage_nav.goto(page, "deliver")
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

                # 整套一致性报告缺失（删掉文档后刷新）：门禁必须给出非图级阻断的定位入口
                removed = page.evaluate(DROP_SUITE_REPORT)
                page.reload(wait_until="networkidle")
                page.wait_for_selector("#project-view:not([hidden])", timeout=30_000)
                stage_nav.goto(page, "deliver")
                suite_state = wait_gate(page)
                jump = page.locator('#delivery-gate button[data-suite-action="run"]')
                jump_text = jump.first.inner_text() if jump.count() else ""
                shot(page, "suite-missing")
                jump.click()
                page.wait_for_selector('[data-stage-panel="review"]:not([hidden])', timeout=10_000)
                focus_id = page.evaluate(
                    "() => (document.activeElement && document.activeElement.id) || ''")
                check("V2.6.2-12",
                      "整套一致性阻断（非图级）：带「去运行整套检查」定位入口并把焦点落到运行按钮",
                      removed >= 1
                      and any(item["rule"] == "export.suite_review_current"
                              and item["severity"] == "BLOCK" for item in suite_state["findings"])
                      and jump_text == "去运行整套检查"
                      and focus_id == "suite-review-run",
                      {"removed": removed, "jump": jump_text, "focus": focus_id,
                       "blocking": [item for item in suite_state["findings"]
                                    if item["severity"] == "BLOCK"]})

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

        # ---------------- Unknown 确认解锁（反向；可选 AI 缺席记 not_run 不阻断交付） ----------------
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
