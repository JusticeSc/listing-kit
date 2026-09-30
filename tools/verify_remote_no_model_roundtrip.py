#!/usr/bin/env python
"""远程正式入口的「不调模型」半程往返：空白 → 建项目 → 资料 → 导出项目包 → 换浏览器导入 → 打开核对。

为什么单有这个入口：V2.7.2（真实模型最小闭环）在账户/上游不可用时做不了，但
Goal 里与模型无关的那几条（空白启动、IndexedDB 恢复、项目包跨浏览器往返）仍然可以在
**真实 HTTPS 正式入口**上验证，而不是只在本机。它不产生任何模型调用，也不写服务器状态。

边界（NOT-AUTHORITY）：单点时间证据；不替代真实模型闭环（V2.7.2）、产品发起人走查与
陌生人验收（V2.7.3）；不证明账户余额或上游可用性。

用法：
    uv run --locked python tools/verify_remote_no_model_roundtrip.py \
        --base https://47.115.172.233:8080 \
        --image _working/amz-listing-kit-product-demo/real-run-lamp/lamp-3m.jpg
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
IMAGE_DIR = EVIDENCE_DIR / "evidence"
DEFAULT_IMAGE = (ROOT / "_working" / "amz-listing-kit-product-demo" / "real-run-lamp"
                 / "lamp-3m.jpg")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://47.115.172.233:8080")
    ap.add_argument("--image", default=str(DEFAULT_IMAGE))
    ap.add_argument("--label", default="")
    ap.add_argument("--name", default="远程半程往返（不调模型）")
    args = ap.parse_args()

    reference = Path(args.image)
    if not reference.exists():
        print(f"参考图不存在：{reference}")
        return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    evidence = EVIDENCE_DIR / f"remote-no-model-roundtrip-{stamp}{args.label}.txt"
    checks: list[dict] = []
    screenshots: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail=None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory(prefix="rr-nm-") as temp_root:
        temp = Path(temp_root)
        package_path = temp / "project-package.zip"
        with sync_playwright() as pw:
            # ---------- 浏览器 A：空白 → 建项目 → 资料 → 导出项目包 ----------
            ctx_a = pw.chromium.launch_persistent_context(
                str(temp / "profile-a"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            try:
                page = ctx_a.pages[0] if ctx_a.pages else ctx_a.new_page()
                page.set_default_timeout(30_000)
                page.goto(args.base + "/", wait_until="domcontentloaded")
                page.wait_for_selector("#empty-state:not([hidden])", timeout=60_000)
                blank = page.evaluate(
                    """() => ({ rows: document.querySelectorAll('#project-list .project-row').length,
                         name: (document.getElementById('new-project-name') || {}).value || '' })""")
                path = IMAGE_DIR / f"remote-no-model-roundtrip-{stamp}{args.label}-home.png"
                page.screenshot(path=str(path), full_page=True)
                screenshots.append(path.relative_to(ROOT).as_posix())
                check("RN-01", "远程正式入口空白启动：无项目、无预填名称",
                      blank["rows"] == 0 and blank["name"] == "", blank)

                page.fill("#new-project-name", args.name)
                page.click("#create-project")
                page.wait_for_selector("#project-list .project-row", timeout=30_000)
                page.click('#project-list .project-row button[data-action="open"]')
                page.wait_for_selector("#project-view:not([hidden])", timeout=30_000)
                check("RN-02", "远程入口可新建并打开项目（浏览器本地）", True, None)

                page.set_input_files("#ref-file", str(reference))
                page.wait_for_selector("#ref-list .ref-row", timeout=30_000)
                page.fill("#intake-name", "落地灯")
                page.fill("#intake-description", "金属灯身配浅色布艺灯罩；照片为实物参考")
                page.fill("#intake-selling-points", "布艺灯罩\n金属支架")
                page.fill("#intake-focus", "保持灯罩与支架形状颜色")
                page.wait_for_timeout(1200)   # 草稿自动保存（600ms 去抖）
                sha_in_a = page.get_attribute("#ref-list .ref-row", "data-sha")
                path = IMAGE_DIR / f"remote-no-model-roundtrip-{stamp}{args.label}-intake.png"
                page.screenshot(path=str(path), full_page=True)
                screenshots.append(path.relative_to(ROOT).as_posix())
                check("RN-03", "上传参考图并填写资料（技术详情默认收起、图已入库）",
                      bool(sha_in_a), {"asset_sha256": sha_in_a})

                page.click("#back-home")
                page.wait_for_selector("#home-view:not([hidden])", timeout=15_000)
                with page.expect_download(timeout=60_000) as download_info:
                    page.click('#project-list .project-row button[data-action="export"]')
                download_info.value.save_as(str(package_path))
                check("RN-04", "项目包可导出（真实下载字节）",
                      package_path.exists() and package_path.stat().st_size > 0,
                      {"bytes": package_path.stat().st_size,
                       "filename": download_info.value.suggested_filename})

                with zipfile.ZipFile(package_path) as zf:
                    names = zf.namelist()
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                    assets = manifest.get("assets") or []
                    rows = manifest.get("documents") or []
                    asset_ok = False
                    if assets:
                        blob = zf.read(assets[0]["path"])
                        asset_ok = hashlib.sha256(blob).hexdigest() == assets[0]["sha256"]
                    check("RN-05", "项目包结构自洽：manifest + 文档 + 资产，资产字节哈希与清单一致",
                          "manifest.json" in names and len(rows) > 0 and asset_ok
                          and manifest.get("project", {}).get("name") == args.name,
                          {"entries": len(names), "documents": len(rows),
                           "assets": len(assets), "asset_hash_ok": asset_ok,
                           "format_version": manifest.get("format_version")})
                    zip_asset_sha = assets[0]["sha256"] if assets else None
            finally:
                ctx_a.close()

            # ---------- 浏览器 B：全新配置文件导入同一项目包 ----------
            ctx_b = pw.chromium.launch_persistent_context(
                str(temp / "profile-b"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            try:
                page2 = ctx_b.pages[0] if ctx_b.pages else ctx_b.new_page()
                page2.set_default_timeout(30_000)
                page2.goto(args.base + "/", wait_until="domcontentloaded")
                page2.wait_for_selector("#empty-state:not([hidden])", timeout=60_000)
                empty_rows = page2.locator("#project-list .project-row").count()
                page2.set_input_files("#import-file", str(package_path))
                page2.wait_for_selector("#project-list .project-row", timeout=60_000)
                imported_name = page2.locator("#project-list .name").first.text_content()
                check("RN-06", "新浏览器配置文件初始为空，导入项目包后出现同名项目",
                      empty_rows == 0 and imported_name.strip() == args.name,
                      {"before": empty_rows, "imported": imported_name})

                page2.click('#project-list .project-row button[data-action="open"]')
                page2.wait_for_selector("#project-view:not([hidden])", timeout=30_000)
                page2.wait_for_selector("#ref-list .ref-row", timeout=30_000)
                restored = page2.evaluate(
                    """() => ({ name: (document.getElementById('intake-name') || {}).value || '',
                         description: (document.getElementById('intake-description') || {}).value || '',
                         focus: (document.getElementById('intake-focus') || {}).value || '',
                         refs: document.querySelectorAll('#ref-list .ref-row').length })""")
                sha_in_b = page2.get_attribute("#ref-list .ref-row", "data-sha")
                path = IMAGE_DIR / f"remote-no-model-roundtrip-{stamp}{args.label}-imported.png"
                page2.screenshot(path=str(path), full_page=True)
                screenshots.append(path.relative_to(ROOT).as_posix())
                check("RN-07", "导入后业务记录与参考图资产哈希一致（跨浏览器往返）",
                      restored["name"] == "落地灯" and restored["refs"] == 1
                      and sha_in_b == sha_in_a and sha_in_b == zip_asset_sha,
                      {"restored": restored, "sha_a": sha_in_a, "sha_b": sha_in_b,
                       "sha_zip": zip_asset_sha})

                page2.reload(wait_until="networkidle")
                page2.wait_for_selector("#project-view:not([hidden])", timeout=30_000)
                check("RN-08", "导入后的项目在刷新后仍从 IndexedDB 恢复",
                      page2.locator("#project-title").text_content().strip() == args.name,
                      {"title": page2.locator("#project-title").text_content()})
            finally:
                ctx_b.close()

    ok_count = sum(1 for item in checks if item["ok"])
    status = "passed" if ok_count == len(checks) and checks else "failed"
    finished = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    lines = [
        "amz-listing-kit 远程正式入口「不调模型」半程往返",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"finished_at: {finished}",
        f"status: {status}",
        f"base: {args.base}",
        f"reference: {reference}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if item["detail"] is not None:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False)[:600])
    lines += ["", "SCREENSHOTS"] + [f"- {item}" for item in screenshots]
    lines += ["", "BOUNDARY",
              "不含任何模型调用；不替代 V2.7.2 真实模型闭环、V2.7.3 人工走查；"
              "上游账户与网络条件可能随时变化。"]
    lines += ["", f"结果：{ok_count}/{len(checks)} 通过"]
    evidence.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    payload = {"status": status, "finished_at": finished, "base": args.base,
               "reference": str(reference), "checks": checks, "screenshots": screenshots}
    evidence.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines[:10]))
    print(f"证据：{evidence.relative_to(ROOT).as_posix()}")
    print(f"结果：{ok_count}/{len(checks)} 通过")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
