#!/usr/bin/env python
"""发布后线上真实验收：既有 HTTPS origin 上的旧/新项目包往返。

只用独立临时浏览器 profile、无 BYOK、零模型调用；对线上服务只做
导入/查看/采用状态核对/两类包导出与再导入，不改动服务器文件。

检查：
  ONL-01 线上 /api/health：product=v2、无 server_state、runtime 指纹存在
  ONL-02 新 profile 打开首页：零 console/page error
  ONL-03 导入上一版 image 产出的项目包（旧包）成功，首页出现该项目
  ONL-04 打开项目：五用途均已有采用结果（读取存储快照，不看提示文案）
  ONL-05 交付门禁无 BLOCK，可导出交付包；Python 独立核对 ZIP 与哈希
  ONL-06 可再导出项目包；独立解包核对 manifest/资产哈希
  ONL-07 独立第二 profile 导入该新导出的项目包：文档/资产快照一致
  ONL-08 刷新后项目仍在（IndexedDB 持久化）

运行：
  uv run --locked python _stage-amz-control/release-online-20261020/online_release_probe.py \
      --base https://47.115.172.233:8080 --package _stage-amz-control/staleness-diagnosis-20261020/b19-exports/b19-project-post-suite.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

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

ADOPTED = """
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
  db.close();
  const selections = documents.filter((item) => item.kind === "selection");
  return selections.map((item) => ({
    shot_id: item.payload.shot_id,
    action: item.payload.action,
    candidate_id: item.payload.candidate_id,
  }));
}
"""


def inspect_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        bad_crc = archive.testzip()
        names = sorted(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        checks = []
        if manifest.get("format") == "amz-listing-kit-project":
            for meta in manifest.get("assets", []):
                payload = archive.read(meta["path"])
                digest = hashlib.sha256(payload).hexdigest()
                checks.append({"path": meta["path"], "ok": digest == meta["sha256"]
                               and len(payload) == meta["byte_size"]})
        for meta in manifest.get("images", []):
            payload = archive.read(meta["file"])
            digest = hashlib.sha256(payload).hexdigest()
            checks.append({"path": meta["file"], "ok": digest == meta["asset_sha256"]
                           and len(payload) == meta.get("byte_size")})
        return {
            "bad_crc_entry": bad_crc,
            "format": manifest.get("format"),
            "format_version": manifest.get("format_version"),
            "names": names,
            "documents": len(manifest.get("documents", [])),
            "assets": len(manifest.get("assets", [])),
            "images": sum(1 for name in names if name.startswith("images/")),
            "asset_checks": checks,
        }


def health(base: str) -> dict:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(base + "/api/health", timeout=15, context=context) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="发布后线上真实验收")
    parser.add_argument("--base", default="https://47.115.172.233:8080")
    parser.add_argument("--package", required=True)
    parser.add_argument("--label", default="release-online")
    parser.add_argument("--expect-delivery", default="",
                        help="可选：本地既有交付包；比对线上导出包的五图身份是否一致")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    source_zip = Path(args.package).resolve()
    if not source_zip.exists():
        print(f"旧项目包不存在：{source_zip}")
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    evidence = Path(__file__).resolve().parent / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="amz-online-"))
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    def check(cid: str, title: str, ok: bool, detail) -> None:
        checks.append({"id": cid, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid} {title}")

    try:
        body = health(args.base)
        check("ONL-01", "线上健康且版本可读",
              body.get("app") == "amz-listing-kit" and body.get("product") == "v2"
              and body.get("server_state") == "none"
              and body.get("user_data") == "browser-indexeddb",
              body)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-features=Translate", "--no-first-run"])
            try:
                context_a = browser.new_context(
                    viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
                page = context_a.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(args.base + "/", wait_until="networkidle", timeout=60_000)
                page.screenshot(path=str(evidence / f"{stamp}-{args.label}-home.png"))

                page.set_input_files("#import-file", str(source_zip))
                expect(page.locator("#home-status")).to_be_visible(timeout=60_000)
                expect(page.locator("#project-list .project-row")).to_have_count(1, timeout=60_000)
                check("ONL-03", "上一版 image 产出的项目包可在线导入",
                      True, {"package": source_zip.name, "bytes": source_zip.stat().st_size})

                page.click("#project-list .project-row [data-action='open']")
                expect(page.locator("#project-view:not([hidden])")).to_be_visible(timeout=60_000)
                adopted = page.evaluate(ADOPTED)
                check("ONL-04", "导入项目保留五用途采用结果",
                      len(adopted) >= 5
                      and all(item["action"] == "select" and item["candidate_id"] for item in adopted),
                      {"adopted": len(adopted)})
                page.screenshot(path=str(evidence / f"{stamp}-{args.label}-project.png"),
                                full_page=False)

                import v2_stage_nav as stage_nav  # noqa: PLC0415
                from v2_verify_shared import download_delivery, wait_gate  # noqa: PLC0415

                stage_nav.goto(page, "deliver")
                gate = wait_gate(page)
                blocking = [item for item in gate["findings"] if item["severity"] == "BLOCK"]
                gate_states = page.eval_on_selector_all(
                    "#delivery-gate .gate-row",
                    "nodes => nodes.map(node => node.dataset.selectionState)")
                delivery_path = workdir / "delivery.zip"
                if not blocking and gate["disabled"] is False:
                    delivery = download_delivery(page, delivery_path)
                    zoom = inspect_zip(delivery_path)
                    expect_ok, expect_detail = True, None
                    if args.expect_delivery:
                        with zipfile.ZipFile(Path(args.expect_delivery)) as expected_zip:
                            expected = json.loads(
                                expected_zip.read("manifest.json").decode("utf-8"))
                            produced = zipfile.ZipFile(delivery_path).read("manifest.json")
                        produced_shas = sorted(item["asset_sha256"]
                                               for item in json.loads(produced)["images"])
                        expected_shas = sorted(item["asset_sha256"]
                                               for item in expected["images"])
                        expect_ok = produced_shas == expected_shas
                        expect_detail = {"produced": produced_shas, "expected": expected_shas}
                    check("ONL-05", "线上交付门禁可导出且 ZIP 独立核对",
                          zoom["bad_crc_entry"] is None and zoom["images"] == 5
                          and all(state == "current" for state in gate_states)
                          and all(item["ok"] for item in zoom["asset_checks"])
                          and expect_ok,
                          {"download": delivery, "images": zoom["images"],
                           "gate_states": gate_states,
                           "checks": len(zoom["asset_checks"]),
                           "expected_delivery": expect_detail})
                else:
                    check("ONL-05", "线上交付门禁可导出且 ZIP 独立核对", False,
                          {"status": gate.get("status"), "findings": blocking[:4]})

                stage_nav.goto(page, "deliver")
                project_path = workdir / "project.zip"
                with page.expect_download(timeout=120_000) as download_info:
                    page.click("#deliver-project-package")
                download_info.value.save_as(str(project_path))
                exported = inspect_zip(project_path)
                check("ONL-06", "线上可再导出项目包且 manifest/资产一致",
                      exported["format"] == "amz-listing-kit-project"
                      and exported["bad_crc_entry"] is None
                      and all(item["ok"] for item in exported["asset_checks"]),
                      {"documents": exported["documents"], "assets": exported["assets"]})

                before = page.evaluate(SNAPSHOT)
                page.reload(wait_until="networkidle", timeout=60_000)
                after = page.evaluate(SNAPSHOT)
                check("ONL-08", "刷新后项目与记录仍在",
                      before["projects"] == after["projects"]
                      and before["documents"] == after["documents"]
                      and before["assets"] == after["assets"],
                      {"projects": len(after["projects"])})

                context_b = browser.new_context(
                    viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
                page2 = context_b.new_page()
                page2.on("console", lambda message: console_errors.append(message.text)
                         if message.type == "error" else None)
                page2.on("pageerror", lambda error: page_errors.append(str(error)))
                page2.goto(args.base + "/", wait_until="networkidle", timeout=60_000)
                page2.set_input_files("#import-file", str(project_path))
                expect(page2.locator("#home-status")).to_be_visible(timeout=60_000)
                expect(page2.locator("#project-list .project-row")).to_have_count(1, timeout=60_000)
                reimported = page2.evaluate(SNAPSHOT)
                check("ONL-07", "独立 profile 导入新导出包：文档/资产快照一致",
                      reimported["documents"] == after["documents"]
                      and reimported["assets"] == after["assets"],
                      {"documents": len(reimported["documents"]),
                       "assets": len(reimported["assets"])})
                page2.screenshot(path=str(evidence / f"{stamp}-{args.label}-reimport.png"))
                context_a.close()
                context_b.close()
            finally:
                browser.close()

        check("ONL-02", "线上页面零 console/page error",
              not console_errors and not page_errors,
              {"console": console_errors[:5], "page": page_errors[:5]})
    except Exception as error:  # noqa: BLE001 - 证据必须保留失败现场
        checks.append({"id": "ONL-EXC", "title": "执行异常", "ok": False,
                       "detail": f"{type(error).__name__}: {error}"})
        print(f"  [FAIL] ONL-EXC {type(error).__name__}: {error}")

    passed = sum(1 for item in checks if item["ok"])
    payload = {
        "schema": "amz-release-online/v1",
        "status": "passed" if passed == len(checks) and checks else "failed",
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "base": args.base,
        "source_package": str(source_zip),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "console_errors": console_errors[:20],
        "page_errors": page_errors[:20],
    }
    (evidence / f"{stamp}-{args.label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("=" * 72)
    print(f"{passed}/{len(checks)} 通过")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
