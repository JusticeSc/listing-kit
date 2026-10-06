"""V2.6.3 当前项目包合同与跨浏览器闭环（0 次真实模型调用）。

检查：
  1) 契约套件 P01–P08（真实 Chromium）：当前格式往返、身份拒绝、历史报告原样保留、
     格式/schema/完整性拒绝、旧包原子拒绝且已有库不变。
  2) 双浏览器闭环（fake provider）：浏览器 A 走完整链路并生成交付包 → 导出项目包；
     Python zipfile/hashlib 独立核对；浏览器 B（全新 profile）导入 → 逐文档 payload 哈希与
     资产 sha256 与 A 一致（浏览器 crypto 独立重算）；在 B 上完成一次按问题返工 + 重新采用 +
     整套检查 + 交付包生成；再导出项目包，A 的记录集合逐条保留且新增返工/交付记录。
  3) 正式入口 --check 全过；两个浏览器主链零意外 console/page/HTTP 错误。

运行：
  uv run --locked python tools/verify_v2_6_3_project_transfer.py --label final
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"


sys.path.insert(0, str(ROOT / "tools"))
import v2_verify_shared as shared  # noqa: E402
import v2_stage_nav as stage_nav  # noqa: E402


READ_LIBRARY = """async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('amz-listing-kit-v2');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const docs = await new Promise((resolve, reject) => {
    const tx = db.transaction('documents', 'readonly');
    const out = [];
    tx.objectStore('documents').openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(out); return; }
      const value = cursor.value;
      out.push({ kind: value.kind, document_id: value.document_id, version: value.version,
                 schema_version: value.schema_version, payload: value.payload });
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  const metas = await new Promise((resolve, reject) => {
    const tx = db.transaction('assets', 'readonly');
    const out = [];
    tx.objectStore('assets').openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(out); return; }
      const value = cursor.value;
      out.push({ sha256: value.sha256, byte_size: value.byte_size, blob: value.blob });
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  const assets = [];
  for (const meta of metas) {
    const buffer = await meta.blob.arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', buffer);
    const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
    assets.push({ sha256: meta.sha256, byte_size: meta.byte_size, digest: hex });
  }
  db.close();
  return { docs, assets };
}"""

READ_KIND_COUNT = """async (kind) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('amz-listing-kit-v2');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const count = await new Promise((resolve, reject) => {
    const tx = db.transaction('documents', 'readonly');
    let total = 0;
    tx.objectStore('documents').openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(total); return; }
      if (cursor.value.kind === kind) total += 1;
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  return count;
}"""

READ_LATEST_CANDIDATE = """async (shotId) => {
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
      const value = cursor.value;
      if (value.kind === 'candidate' && value.document_id === shotId && value.payload
          && typeof value.payload.candidate_id === 'string') {
        out.push({ candidate_id: value.payload.candidate_id, version: value.version });
      }
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  rows.sort((left, right) => right.version - left.version);
  return rows.length ? rows[0] : null;
}"""


def payload_digest(payload) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def inspect_project_package(path: Path) -> dict:
    """独立核对项目包（Python zipfile/hashlib，不依赖产品代码）。"""
    with zipfile.ZipFile(path) as archive:
        names = sorted(archive.namelist())
        broken = archive.testzip()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        documents = []
        for meta in manifest.get("documents", []):
            raw = json.loads(archive.read(meta["path"]).decode("utf-8"))
            documents.append({
                "path": meta["path"], "kind": meta["kind"], "document_id": meta["document_id"],
                "version": meta["version"],
                "self_described": (raw.get("kind") == meta["kind"]
                                   and raw.get("document_id") == meta["document_id"]
                                   and raw.get("version") == meta["version"]),
                "payload_sha256": payload_digest(raw.get("payload")),
            })
        assets = []
        for meta in manifest.get("assets", []):
            data = archive.read(meta["path"])
            assets.append({"sha256": meta["sha256"], "declared_size": meta.get("byte_size"),
                           "actual_size": len(data),
                           "digest": hashlib.sha256(data).hexdigest()})
        integrity = manifest.get("integrity") or {}
    return {"names": names, "broken": broken, "manifest": manifest, "documents": documents,
            "assets": assets, "integrity": integrity,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def downgrade_to_format_one(source: Path, target: Path) -> None:
    """把当前包重建成旧格式，验证 UI 在写入前拒绝且已有数据不变。"""
    with zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        manifest["format_version"] = 1
        manifest.pop("integrity", None)
        manifest.pop("record_schema_version", None)
        entries = []
        for name in archive.namelist():
            if name == "manifest.json":
                continue
            data = archive.read(name)
            if name.startswith("documents/"):
                raw = json.loads(data.decode("utf-8"))
                data = json.dumps({"payload": raw.get("payload")},
                                  ensure_ascii=False).encode("utf-8")
            entries.append((name, data))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("manifest.json",
                        json.dumps(manifest, ensure_ascii=False).encode("utf-8"))
        for name, data in entries:
            output.writestr(name, data)


def wait_candidate_count(page, minimum: int, timeout_s: int = 60) -> int:
    deadline = time.time() + timeout_s
    count = page.evaluate(READ_KIND_COUNT, "candidate")
    while count < minimum and time.time() < deadline:
        page.wait_for_timeout(400)
        count = page.evaluate(READ_KIND_COUNT, "candidate")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.6.3 当前项目包与跨浏览器验收")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"-{args.label}" if args.label else ""
    evidence_txt = EVIDENCE_DIR / f"v2.6.3-transfer-{stamp}{label}.txt"
    evidence_json = EVIDENCE_DIR / f"v2.6.3-transfer-{stamp}{label}.json"
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    checks: list[dict] = []

    def check(check_id: str, title: str, ok: bool, detail=None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {check_id} {title}" + (
            "" if ok else " :: " + json.dumps(detail, ensure_ascii=False, default=str)[:400]))

    screenshots: list[str] = []

    def shot(page, name: str) -> None:
        path = EVIDENCE_IMAGE_DIR / f"v2.6.3-transfer-{stamp}{label}-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(path.relative_to(ROOT).as_posix())

    # ---------------- 契约套件 P01–P08 ----------------
    suites: dict = {}
    static_server, base = shared.start_static_server()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["transfer"] = shared.read_suite(
                    browser, base + "/harness/project-package-contract.html",
                    "__V2_TRANSFER_RESULTS__")
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()
    suite = suites.get("transfer", {})
    case_ids = [item.get("id") for item in suite.get("cases", [])]
    failed = [item for item in suite.get("cases", []) if item.get("status") != "passed"]
    check("V2.6.3-03", "契约套件 P01–P08 全过（真实 Chromium）",
          suite.get("status") == "passed"
          and case_ids == [f"P0{index}" for index in range(1, 9)] and not failed,
          {"status": suite.get("status"), "cases": case_ids,
           "failed": [{"id": item.get("id"), "error": item.get("error")} for item in failed[:3]]})

    # ---------------- 双浏览器闭环 ----------------
    from playwright.sync_api import sync_playwright

    temp_root = Path(tempfile.mkdtemp(prefix="amz-v263-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(shared.png_bytes(900, 900, (36, 92, 160)))
    downloads = temp_root / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)

    walkthrough: dict = {}
    with sync_playwright() as pw:
        port = shared.free_port()
        server, _suite_instance = shared.start_product_server(port, review_scenario="ok")
        try:
            context_a = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-a"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            page_a = context_a.pages[0] if context_a.pages else context_a.new_page()
            page_a.set_default_timeout(30_000)
            logs_a = shared.collect(page_a)
            try:
                page_a.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                shots, _walk_probes = shared.walk_to_deliver(page_a, "V263 迁移品", reference)
                gate_a = shared.wait_gate(page_a)
                shot(page_a, "a-gate")
                delivery_a = shared.download_delivery(page_a, downloads / "delivery-a.zip")
                with page_a.expect_download(timeout=120_000) as info_a:
                    page_a.click("#deliver-project-package")
                project_a_path = downloads / "project-a.zip"
                info_a.value.save_as(str(project_a_path))
                shot(page_a, "a-exported")
                package_a = inspect_project_package(project_a_path)
                doc_kinds = sorted({item["kind"] for item in package_a["documents"]})
                # shot_spec / style_spec 是用户保存时才落库的文档；从模板直接生成的链路
                # 只投影 plan + prompt，因此这里断言「必需记录齐全 + 不出现未登记种类」。
                expected_kinds = {"candidate", "export_record", "generation_attempt",
                                  "generation_confirm", "product_input", "prompt_version",
                                  "review_report", "selection", "suite_plan", "suite_review",
                                  "fact_slot"}
                integrity_ok = (package_a["integrity"].get("documents")
                                == len(package_a["documents"])
                                and package_a["integrity"].get("assets")
                                == len(package_a["assets"]))
                assets_ok = all(item["digest"] == item["sha256"]
                                and item["declared_size"] == item["actual_size"]
                                for item in package_a["assets"])
                records_ok = all(item["self_described"] for item in package_a["documents"])
                check("V2.6.3-04", "A 导出项目包：格式 2、记录自描述、完整性计数与逐资产哈希（Python 独立核对）",
                      package_a["manifest"].get("format") == "amz-listing-kit-project"
                      and package_a["manifest"].get("format_version") == 2
                      and package_a["broken"] is None and records_ok and integrity_ok and assets_ok
                      and expected_kinds <= set(doc_kinds)
                      and package_a["manifest"].get("project", {}).get("name") == "V263 迁移品",
                      {"format_version": package_a["manifest"].get("format_version"),
                       "integrity": package_a["integrity"], "documents": len(package_a["documents"]),
                       "assets": len(package_a["assets"]), "kinds": doc_kinds,
                       "records_self_described": records_ok})
                walkthrough["a"] = {"shots": shots, "gate_blocking": [
                    item for item in gate_a["findings"] if item["severity"] == "BLOCK"],
                    "delivery": delivery_a, "package_bytes": package_a["bytes"]}

                # ---- 浏览器 B：全新 profile 导入 ----
                context_b = pw.chromium.launch_persistent_context(
                    str(temp_root / "profile-b"), headless=True,
                    viewport={"width": 1440, "height": 950}, accept_downloads=True)
                page_b = context_b.pages[0] if context_b.pages else context_b.new_page()
                page_b.set_default_timeout(30_000)
                logs_b = shared.collect(page_b)
                try:
                    page_b.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                    page_b.wait_for_function(
                        "() => { const node = document.getElementById('import-trigger');"
                        " return node && node.disabled === false; }",
                        timeout=15_000)
                    page_b.set_input_files("#import-file", str(project_a_path))
                    page_b.wait_for_function(
                        "() => { const node = document.getElementById('home-status');"
                        " return node && node.textContent.indexOf('已导入') >= 0; }",
                        timeout=30_000)
                    import_status = page_b.text_content("#home-status") or ""
                    shot(page_b, "b-imported")
                    page_b.click('#project-list .project-row button[data-action="open"]')
                    page_b.wait_for_selector("#project-view:not([hidden])", timeout=30_000)
                    page_b.wait_for_function(
                        "() => { const node = document.getElementById('project-title');"
                        " return node && node.textContent &&"
                        " node.textContent.indexOf('V263 迁移品') >= 0; }",
                        timeout=30_000)
                    library = page_b.evaluate(READ_LIBRARY)
                    index_a = {(item["kind"], item["document_id"], item["version"]):
                               item["payload_sha256"] for item in package_a["documents"]}
                    index_b = {(item["kind"], item["document_id"], item["version"]):
                               payload_digest(item["payload"]) for item in library["docs"]}
                    missing = [key for key in index_a if key not in index_b]
                    changed = [key for key in index_a
                               if key in index_b and index_a[key] != index_b[key]]
                    asset_set_a = {item["sha256"] for item in package_a["assets"]}
                    asset_set_b = {item["sha256"] for item in library["assets"]}
                    browser_digest_ok = all(item["digest"] == item["sha256"]
                                            for item in library["assets"])
                    check("V2.6.3-05", "B 全新 profile 导入：逐文档 payload 哈希与资产 sha256 与 A 包一致（crypto 独立重算）",
                          "已导入" in import_status and not missing and not changed
                          and asset_set_a <= asset_set_b
                          and len(asset_set_b) == len(asset_set_a) and browser_digest_ok,
                          {"status": import_status[:120], "missing": missing[:4],
                           "changed": changed[:4], "assets_a": len(asset_set_a),
                           "assets_b": len(asset_set_b), "digests_ok": browser_digest_ok})
                    shot(page_b, "b-opened")

                    # ---- B：按问题返工 → 新候选（当前一站式 reworkSubmit；禁止旧 #adopt-panel 假设） ----
                    stage_nav.goto(page_b, "review")
                    first_shot = shots[0]
                    candidate_before = page_b.evaluate(READ_KIND_COUNT, "candidate")
                    card = page_b.locator(
                        f'#review-list .review-card[data-shot-id="{first_shot}"]')
                    card.locator('button:has-text("按问题返工")').click()
                    page_b.wait_for_selector("#rework-panel:not([hidden])", timeout=15_000)
                    shot(page_b, "b-rework-form")
                    problems = page_b.locator(
                        '#rework-panel .rework-problem input[type="checkbox"]')
                    if problems.count() == 0:
                        raise RuntimeError("返工面板没有问题分类")
                    problems.first.check()
                    page_b.fill("#rework-direction", "背景换成干净的浅灰，商品与文字保持原样。")
                    page_b.click("#rework-preview")
                    page_b.wait_for_selector("#rework-submit:not([disabled])", timeout=20_000)
                    page_b.click("#rework-submit")
                    candidate_after = wait_candidate_count(page_b, candidate_before + 1)
                    attempt_count = page_b.evaluate(READ_KIND_COUNT, "generation_attempt")
                    check("V2.6.3-06", "B 导入后按问题返工：新增候选与 Attempt（迁移后的项目可继续生产）",
                          candidate_after == candidate_before + 1
                          and attempt_count >= len(shots) + 1,
                          {"candidate_before": candidate_before, "candidate_after": candidate_after,
                           "attempts": attempt_count, "shots": len(shots)})
                    # 新候选到达不自动改选：旧采用保持 current（不自动指向最新），仍需人工显式采用。
                    pre_adopt_state = page_b.evaluate(
                        f"() => (document.querySelector('#review-list .review-card[data-shot-id=\"{first_shot}\"]') || {{}}).getAttribute('data-selection-state')")
                    check("V2.6.3-06a", "新候选不自动改选：旧采用保持 current、仍需人工显式采用最新",
                          pre_adopt_state == "current",
                          {"pre_adopt_state": pre_adopt_state})

                    # ---- B：显式选中最新候选并一键采用（#adopt-open 单击，无二次确认面板） ----
                    card.locator('button:has-text("比较候选")').click()
                    page_b.wait_for_selector("#compare-panel:not([hidden])", timeout=15_000)
                    latest = page_b.evaluate(READ_LATEST_CANDIDATE, first_shot)
                    if not latest:
                        raise RuntimeError("B 项目里找不到最新候选")
                    page_b.click(
                        f'#compare-candidates [role="tab"][data-candidate-id="{latest["candidate_id"]}"]')
                    page_b.click("#adopt-open")
                    page_b.wait_for_function(
                        f"() => [...document.querySelectorAll('#review-list .review-card')].some((node) => node.getAttribute('data-shot-id') === '{first_shot}' && node.getAttribute('data-selection-state') === 'current')",
                        timeout=15_000)
                    page_b.wait_for_timeout(300)

                    # ---- B：整套检查 → 交付门禁 → 交付包（当前阶段显式导航；AI 复核按需可选不自动跑） ----
                    stage_nav.goto(page_b, "review")
                    page_b.click("#suite-review-run")
                    page_b.wait_for_function(
                        "() => { const node = document.getElementById('suite-review-status');"
                        " return node && node.textContent.indexOf('整套检查 ') >= 0; }",
                        timeout=60_000)
                    stage_nav.goto(page_b, "deliver")
                    gate_b = shared.wait_gate(page_b)
                    blocking_b = [item for item in gate_b["findings"] if item["severity"] == "BLOCK"]
                    shot(page_b, "b-deliver")
                    delivery_b = shared.download_delivery(page_b, downloads / "delivery-b.zip")
                    zoom_b = shared.inspect_zip(downloads / "delivery-b.zip")
                    digest_b_ok = all(item["sha256"] == item["declared"]
                                      and item["byte_size"] == item["declared_size"]
                                      for item in zoom_b["digests"].values())
                    delivered_first = next((item for item in zoom_b["manifest"]["images"]
                                          if item.get("shot_id") == first_shot), {})
                    check("V2.6.3-07", "B 返工后门禁重新就绪并生成交付包（迁移后的完整闭环）",
                          not blocking_b and gate_b["disabled"] is False
                          and delivery_b["bytes"] > 0 and zoom_b["broken"] is None
                          and digest_b_ok and len(zoom_b["manifest"]["images"]) == len(shots)
                          and delivered_first.get("candidate_id") == latest["candidate_id"]
                          and delivered_first.get("attempt_action_id")
                          and delivered_first.get("prompt_version")
                          and delivered_first.get("prompt_hash"),
                          {"blocking": blocking_b[:3], "status": gate_b["status"][:160],
                           "delivery": delivery_b,
                           "images": len(zoom_b["manifest"]["images"]),
                           "delivered": {key: delivered_first.get(key) for key in
                                         ("shot_id", "candidate_id", "attempt_action_id",
                                          "prompt_version")}})

                    # ---- B：再导出项目包，A 的记录逐条保留并可继续增长 ----
                    with page_b.expect_download(timeout=120_000) as info_b:
                        page_b.click("#deliver-project-package")
                    project_b_path = downloads / "project-b.zip"
                    info_b.value.save_as(str(project_b_path))
                    package_b = inspect_project_package(project_b_path)
                    index_b2 = {(item["kind"], item["document_id"], item["version"]):
                                item["payload_sha256"] for item in package_b["documents"]}
                    kept = all(index_b2.get(key) == value for key, value in index_a.items())
                    new_records = [key for key in index_b2 if key not in index_a]
                    new_kinds = sorted({key[0] for key in new_records})
                    asset_set_b2 = {item["sha256"] for item in package_b["assets"]}
                    b_integrity_ok = (package_b["integrity"].get("documents")
                                      == len(package_b["documents"])
                                      and package_b["integrity"].get("assets")
                                      == len(package_b["assets"]))
                    check("V2.6.3-08", "B 再导出项目包：A 的记录逐条原样保留，新增返工/交付记录",
                          package_b["manifest"].get("format_version") == 2
                          and package_b["broken"] is None and kept
                          and asset_set_a <= asset_set_b2
                          and {"candidate", "export_record", "selection", "suite_review"}
                          <= set(new_kinds)
                          and len(package_b["documents"]) > len(package_a["documents"])
                          and b_integrity_ok,
                          {"kept": kept, "new_records": len(new_records),
                           "new_kinds": new_kinds,
                           "documents": [len(package_a["documents"]), len(package_b["documents"])],
                           "assets": [len(package_a["assets"]), len(package_b["assets"])]})
                    # ---- 旧格式 UI 拒绝：保留已有项目及所有资产/版本 ----
                    candidates_before_v1 = page_b.evaluate(READ_KIND_COUNT, "candidate")
                    v1_path = downloads / "project-a-format1.zip"
                    downgrade_to_format_one(project_a_path, v1_path)
                    page_b.click("#back-home")
                    page_b.wait_for_selector("#home-view:not([hidden])", timeout=15_000)
                    page_b.wait_for_selector("#project-list .project-row", timeout=15_000)
                    rows_before = page_b.locator("#project-list .project-row").count()
                    page_b.set_input_files("#import-file", str(v1_path))
                    page_b.wait_for_function(
                        "() => { const node = document.getElementById('home-error');"
                        " return node && !node.hidden && node.textContent; }",
                        timeout=30_000)
                    rejection = page_b.text_content("#home-error") or ""
                    rows_after = page_b.locator("#project-list .project-row").count()
                    candidates_after_v1 = page_b.evaluate(READ_KIND_COUNT, "candidate")
                    check("V2.6.3-09", "旧格式 UI 导入拒绝，已有项目和候选不变",
                          bool(rejection) and rows_after == rows_before
                          and candidates_after_v1 == candidates_before_v1,
                          {"error": rejection[:200], "rows": [rows_before, rows_after],
                           "candidates": [candidates_before_v1, candidates_after_v1]})
                    walkthrough["b"] = {"latest_candidate": latest,
                                        "new_kinds": new_kinds,
                                        "delivery": delivery_b,
                                        "package_bytes": package_b["bytes"],
                                        "format1_rejected": rejection[:200]}
                finally:
                    context_b.close()

                unexpected_a = [item for item in logs_a["http"] if "/favicon.ico" not in item]
                check("V2.6.3-10", "浏览器 A 主链零意外 console / page / HTTP 错误",
                      not logs_a["console"] and not logs_a["page"] and not unexpected_a,
                      {"console": logs_a["console"][:4], "page": logs_a["page"][:3],
                       "http": unexpected_a[:4]})
                unexpected_b = [item for item in logs_b["http"] if "/favicon.ico" not in item]
                check("V2.6.3-11", "浏览器 B 主链零意外 console / page / HTTP 错误",
                      not logs_b["console"] and not logs_b["page"] and not unexpected_b,
                      {"console": logs_b["console"][:4], "page": logs_b["page"][:3],
                       "http": unexpected_b[:4]})
            finally:
                context_a.close()
        finally:
            server.shutdown()
            server.server_close()

    completed = subprocess.run([sys.executable, "app/server.py", "--check"], cwd=str(ROOT),
                               capture_output=True, text=True, check=False, encoding="utf-8",
                               errors="replace")
    tail = (completed.stdout or "").strip().splitlines()[-3:]
    check("V2.6.3-12", "正式入口自检全过",
          completed.returncode == 0, {"rc": completed.returncode, "tail": tail})

    passed = sum(1 for item in checks if item["ok"])
    lines = [f"V2.6.3 当前项目包与跨浏览器闭环验收 · {stamp}{label}",
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
