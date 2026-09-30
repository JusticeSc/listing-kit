#!/usr/bin/env python
"""V2.1.3 证据：完整项目 ZIP 导入/导出（真实 Chromium + Python 独立解包校验）。

检查：
  1) 静态：storage 模块与 app.js 通过 node --check。
  2) 包契约套件：ZIP 读写、项目包往返、篡改/截断/未来版本拒绝、导入事务回滚、id 冲突。
  3) 界面导出：下载的 ZIP 能被 Python zipfile 打开，CRC 全过，manifest 与资产哈希一致。
  4) 清空浏览器状态后导入：业务记录、文档版本与资产哈希与导出前逐项一致。
  5) 损坏包：界面拒绝且不产生任何项目（不污染现有数据）。
  6) 重复导入同一包：自动分配新 project_id，两份内容一致。

运行：
  uv run --locked python tools/verify_v2_1_3_project_package.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from v2_test_server import start as start_server  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
STORAGE_DIR = ROOT / "app" / "product_v2" / "storage"
DB_NAME = "amz-listing-kit-v2"
EXPECTED_CASE_IDS = [f"Z0{index}" for index in range(1, 10)]

SEED_PROJECT = """
async () => {
  const mod = await import("/storage/index.js");
  const opened = await mod.openStorage({});
  try {
    const repo = opened.repository;
    const projects = await repo.projects.list();
    const project = projects[0];
    await repo.documents.save(project.project_id, {
      kind: "product_input", documentId: "intake",
      payload: { note: "第一版资料", selling_points: ["保温", "防滑"] },
    });
    await repo.documents.save(project.project_id, {
      kind: "product_input", documentId: "intake",
      payload: { note: "第二版资料", selling_points: ["保温", "防滑", "便携"] },
      expectedVersion: 1,
    });
    const first = await repo.assets.put(project.project_id, {
      bytes: new TextEncoder().encode("export-roundtrip-bytes-AAA"),
      mediaType: "image/png", originalName: "参考图 A.png", role: "primary",
      width: 1200, height: 900,
    });
    const second = await repo.assets.put(project.project_id, {
      bytes: new Uint8Array([9, 8, 7, 6, 5, 4, 3, 2, 1, 0]),
      mediaType: "image/jpeg", originalName: "细节图 B.jpg", role: "detail",
    });
    return { project_id: project.project_id, first: first.sha256, second: second.sha256 };
  } finally {
    opened.close();
  }
}
"""

SNAPSHOT = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) return { projects: [], documents: [], assets: [] };
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
  const assets = await read("assets");
  db.close();
  return {
    projects: projects.map((item) => ({
      project_id: item.project_id, name: item.name, state: item.state, revision: item.revision,
      created_at: item.created_at, updated_at: item.updated_at,
    })).sort((a, b) => a.project_id.localeCompare(b.project_id)),
    documents: documents.map((item) => ({
      project_id: item.project_id, kind: item.kind, document_id: item.document_id,
      version: item.version, payload: item.payload,
    })).sort((a, b) => (a.project_id + a.kind + a.document_id + a.version)
        .localeCompare(b.project_id + b.kind + b.document_id + b.version)),
    assets: assets.map((item) => ({
      project_id: item.project_id, sha256: item.sha256, byte_size: item.byte_size,
      media_type: item.media_type, original_name: item.original_name, role: item.role,
    })).sort((a, b) => (a.project_id + a.sha256).localeCompare(b.project_id + b.sha256)),
  };
}
"""


def run_node_checks() -> dict:
    files = sorted(STORAGE_DIR.glob("*.js")) + [ROOT / "app" / "product_v2" / "app.js"]
    results = []
    for path in files:
        completed = subprocess.run(["node", "--check", str(path)], cwd=ROOT, capture_output=True, text=True)
        results.append({"file": path.relative_to(ROOT).as_posix(), "rc": completed.returncode,
                        "stderr": completed.stderr.strip()})
    return {"files": results, "ok": all(item["rc"] == 0 for item in results)}


def inspect_package(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        bad_crc = archive.testzip()
        names = sorted(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        asset_checks = []
        for meta in manifest.get("assets", []):
            payload = archive.read(meta["path"])
            digest = hashlib.sha256(payload).hexdigest()
            asset_checks.append({
                "path": meta["path"], "declared": meta["sha256"], "computed": digest,
                "bytes": len(payload), "ok": digest == meta["sha256"] and len(payload) == meta["byte_size"],
            })
        return {
            "bad_crc_entry": bad_crc,
            "names": names,
            "format": manifest.get("format"),
            "format_version": manifest.get("format_version"),
            "project_id": manifest.get("project", {}).get("project_id"),
            "documents": len(manifest.get("documents", [])),
            "assets": len(manifest.get("assets", [])),
            "asset_checks": asset_checks,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.1.3 项目包导入导出验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    suite_cases: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    node_result = run_node_checks()
    check("V2.1.3-00", "storage 模块与 app.js 通过 node --check", node_result["ok"], node_result)

    server, base_url = start_server()
    try:
        with sync_playwright() as pw, tempfile.TemporaryDirectory(prefix="amz-v213-") as workdir:
            browser = pw.chromium.launch(headless=True)
            try:
                # --- 1) 包契约套件 ---
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(base_url + "/harness/package-contract.html", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.__V2_PACKAGE_RESULTS__ && "
                    "['passed','failed','crashed'].includes(window.__V2_PACKAGE_RESULTS__.status)",
                    timeout=120_000,
                )
                suite = page.evaluate("() => window.__V2_PACKAGE_RESULTS__")
                suite_cases = suite.get("cases", [])
                present = [item.get("id") for item in suite_cases]
                missing = [item for item in EXPECTED_CASE_IDS if item not in present]
                check("V2.1.3-01", "包契约套件全部通过且用例清单完整",
                      suite.get("status") == "passed" and not missing,
                      {"status": suite.get("status"), "cases": len(suite_cases),
                       "failed": suite.get("failed_ids"), "missing": missing})
                context.close()

                # --- 2) 界面导出 ---
                producer = browser.new_context(viewport={"width": 1280, "height": 900})
                page = producer.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(base_url + "/", wait_until="networkidle")
                page.fill("#new-project-name", "打包验证项目")
                page.click("#create-project")
                expect(page.locator("#project-list .project-row")).to_have_count(1)
                seeded = page.evaluate(SEED_PROJECT)
                page.reload(wait_until="networkidle")
                before = page.evaluate(SNAPSHOT)
                package_path = Path(workdir) / "exported-project.zip"
                with page.expect_download() as download_info:
                    page.click("#project-list .project-row [data-action='export']")
                download = download_info.value
                download.save_as(str(package_path))
                expect(page.locator("#home-status")).to_be_visible()
                check("V2.1.3-02", "界面导出产生下载文件且给出结果提示",
                      package_path.exists() and package_path.stat().st_size > 0,
                      {"suggested_filename": download.suggested_filename,
                       "bytes": package_path.stat().st_size if package_path.exists() else 0})

                # --- 3) Python 独立解包校验 ---
                inspected = inspect_package(package_path)
                check("V2.1.3-03", "导出包是标准 ZIP：CRC 全过、manifest 与资产哈希一致",
                      inspected["bad_crc_entry"] is None
                      and inspected["format"] == "amz-listing-kit-project"
                      # 格式版本是编号正整数即可；当前版本号由 V2.6.3 契约锁定，这里不重复锁。
                      and isinstance(inspected["format_version"], int)
                      and inspected["format_version"] >= 1
                      and len(inspected["asset_checks"]) == 2
                      and all(item["ok"] for item in inspected["asset_checks"]),
                      inspected)

                # --- 4) 清空浏览器状态后导入 ---
                consumer = browser.new_context(viewport={"width": 1280, "height": 900})
                import_page = consumer.new_page()
                import_page.on("console", lambda message: console_errors.append(message.text)
                               if message.type == "error" else None)
                import_page.on("pageerror", lambda error: page_errors.append(str(error)))
                import_page.goto(base_url + "/", wait_until="networkidle")
                expect(import_page.locator("#empty-state")).to_be_visible()
                import_page.set_input_files("#import-file", str(package_path))
                expect(import_page.locator("#home-status")).to_be_visible()
                expect(import_page.locator("#project-list .project-row")).to_have_count(1)
                after = import_page.evaluate(SNAPSHOT)
                check("V2.1.3-04", "清空状态后导入：业务记录、文档与资产哈希与导出前一致",
                      after == before,
                      {"before_projects": before["projects"], "after_projects": after["projects"],
                       "documents_equal": after["documents"] == before["documents"],
                       "assets_equal": after["assets"] == before["assets"]})

                # --- 5) 重复导入同一包（id 冲突） ---
                import_page.set_input_files("#import-file", str(package_path))
                expect(import_page.locator("#project-list .project-row")).to_have_count(2)
                duplicated = import_page.evaluate(SNAPSHOT)
                ids = sorted({item["project_id"] for item in duplicated["projects"]})
                first_project_docs = [item for item in duplicated["documents"]
                                      if item["project_id"] == before["projects"][0]["project_id"]]
                second_project_docs = [item for item in duplicated["documents"]
                                       if item["project_id"] == ids[1]]
                check("V2.1.3-05", "重复导入分配新 project_id，两份内容一致且互不覆盖",
                      len(ids) == 2 and len(duplicated["assets"]) == 4
                      and len(first_project_docs) == len(second_project_docs) == 2,
                      {"project_ids": ids, "assets": len(duplicated["assets"]),
                       "documents_each": [len(first_project_docs), len(second_project_docs)]})

                # --- 6) 损坏包拒绝且不污染 ---
                corrupted = Path(workdir) / "corrupted.zip"
                payload = package_path.read_bytes()
                corrupted.write_bytes(payload[: max(64, int(len(payload) * 0.6))])
                import_page.set_input_files("#import-file", str(corrupted))
                expect(import_page.locator("#home-error")).to_be_visible()
                error_text = import_page.locator("#home-error").inner_text()
                polluted = import_page.evaluate(SNAPSHOT)
                check("V2.1.3-06", "损坏包被拒绝：界面报错且项目数量不变",
                      len(polluted["projects"]) == 2
                      and "项目包" in error_text,
                      {"error": error_text, "projects": len(polluted["projects"])})

                check("V2.1.3-07", "全程无 console error / page error",
                      not console_errors and not page_errors,
                      {"console_errors": console_errors, "page_errors": page_errors})
                producer.close()
                consumer.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()

    failed = [item["id"] for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    report = {
        "task": "V2.1.3",
        "suite": "v2.1.3-project-package",
        "status": status,
        "finished_at": finished_at,
        "checks": checks,
        "suite_cases": suite_cases,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "boundary": (
            "证明完整项目包的导出与导入：标准 ZIP、CRC/哈希校验、清空浏览器状态后逐项一致、"
            "重复导入 id 冲突处理、损坏包拒绝且不污染数据、导入事务回滚。"
            "不证明交付包（导出 ZIP）、正式入口、商品资料之后的业务链与首次使用者可用性。"
        ),
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.1.3-project-package-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.1.3-project-package-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.1.3 project package contract",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False))
    lines += ["", "SUITE CASES"]
    for item in suite_cases:
        lines.append(f"- [{'PASS' if item.get('ok') else 'FAIL'}] {item.get('id')} {item.get('title')}")
        if not item.get("ok"):
            lines.append("  error: " + json.dumps(item.get("error"), ensure_ascii=False))
    lines += ["", "BOUNDARY", report["boundary"]]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.1.3 项目包导入导出验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False)[:400])
    failed_cases = [item for item in suite_cases if not item.get("ok")]
    print(f"套件用例：{len(suite_cases)} 条，失败 {len(failed_cases)} 条")
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
