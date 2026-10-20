#!/usr/bin/env python
"""发布后线上真实交互：在既有 HTTPS origin 上完成一次新的人工采用、整套检查与两包导出。

独立临时 Chrome profile，零 BYOK、零模型调用。只写该 profile 的 IndexedDB，
不改服务器；用于补足「线上真实项目的查看/采用/五图/两包下载」中的采用动作。

检查：
  AD-01 导入上一版项目包并打开：五用途均已采用
  AD-02 选择该图另一条候选并在正式页面采用：新 selection 版本、candidate 改写
  AD-03 选择变化使整套检查过期：门禁阻断交付，重跑整套检查后恢复可导出
  AD-04 交付包含 5 图，该图身份等于刚采用的候选；逐图哈希与 manifest 相等
  AD-05 项目包导出后由独立第二 profile 导入：文档/资产快照相等，刷新仍在
  AD-06 全程零 console/page error
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))

_spec = importlib.util.spec_from_file_location("online_release_probe", HERE / "online_release_probe.py")
_rel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rel)

SNAPSHOT = _rel.SNAPSHOT
inspect_zip = _rel.inspect_zip

CANDIDATES = """
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
  return {
    selections: documents.filter((item) => item.kind === "selection").map((item) => ({
      shot_id: item.document_id, version: item.version,
      candidate_id: item.payload.candidate_id, action: item.payload.action,
      candidate_sha256: item.payload.candidate_sha256 })),
    candidates: documents.filter((item) => item.kind === "candidate").map((item) => ({
      shot_id: item.payload.shot_id, candidate_id: item.document_id,
      asset_sha256: item.payload.asset_sha256, version: item.version })),
  };
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="线上采用/整套检查/两包导出")
    parser.add_argument("--base", default="https://47.115.172.233:8080")
    parser.add_argument("--package", required=True)
    parser.add_argument("--label", default="online-adoption")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415
    import v2_stage_nav as stage_nav  # noqa: PLC0415
    from v2_verify_shared import download_delivery, wait_gate  # noqa: PLC0415

    source = Path(args.package).resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    evidence = HERE / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="amz-adopt-"))
    checks: list[dict] = []
    console: list[str] = []
    page_errors: list[str] = []

    def check(cid: str, title: str, ok: bool, detail) -> None:
        checks.append({"id": cid, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid} {title}")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-first-run"])
            try:
                context_a = browser.new_context(viewport={"width": 1280, "height": 900},
                                                ignore_https_errors=True)
                page = context_a.new_page()
                page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.goto(args.base + "/", wait_until="networkidle", timeout=60_000)
                page.set_input_files("#import-file", str(source))
                expect(page.locator("#home-status")).to_be_visible(timeout=60_000)
                expect(page.locator("#project-list .project-row")).to_have_count(1, timeout=60_000)
                page.click("#project-list .project-row [data-action='open']")
                expect(page.locator("#project-view:not([hidden])")).to_be_visible(timeout=60_000)

                before = page.evaluate(SNAPSHOT)
                adopted = [s for s in page.evaluate(CANDIDATES)["selections"] if s["action"] == "select"]
                check("AD-01", "导入项目五用途均已采用",
                      len(adopted) >= 5, {"adopted": len(adopted)})

                data = page.evaluate(CANDIDATES)
                current = {s["shot_id"]: s for s in data["selections"]}
                by_shot: dict[str, list[dict]] = {}
                for candidate in data["candidates"]:
                    by_shot.setdefault(candidate["shot_id"], []).append(candidate)
                target = next((shot for shot, rows in by_shot.items()
                               if len(rows) > 1 and current.get(shot, {}).get("action") == "select"), None)
                if target is None:
                    raise AssertionError("没有可切换候选的已采用图，无法执行线上采用")

                stage_nav.goto(page, "make")
                page.evaluate("""(shot) => {
                  const row = document.querySelector('#task-list-mount [data-task-shot="' + shot + '"] [data-view-shot]');
                  if (row) row.click();
                }""", target)
                expect(page.locator("#compare-panel")).to_be_visible(timeout=30_000)
                tabs = page.locator('#compare-panel #compare-candidates [role="tab"]')
                expect(tabs.first).to_be_visible(timeout=30_000)

                chosen = None
                for index in range(tabs.count()):
                    tab = tabs.nth(index)
                    candidate_id = tab.get_attribute("data-candidate-id") or ""
                    if candidate_id == current[target]["candidate_id"]:
                        continue
                    tab.click()
                    page.wait_for_timeout(120)
                    if page.locator("#compare-panel #adopt-open").is_enabled():
                        chosen = candidate_id
                        break
                if not chosen:
                    raise AssertionError("没有可采用的其它候选（按钮全部不可用）")

                page.click("#compare-panel #adopt-open")
                page.wait_for_function(
                    """(shot) => {
                      const row = document.querySelector('#task-list-mount [data-task-shot="' + shot + '"]');
                      return row && row.getAttribute('data-selection-state') === 'current';
                    }""", arg=target, timeout=60_000)
                after_adopt = {s["shot_id"]: s for s in page.evaluate(CANDIDATES)["selections"]}
                selection = after_adopt[target]
                check("AD-02", "线上采用另一候选并写新 selection 版本",
                      selection["candidate_id"] == chosen
                      and selection["version"] > current[target]["version"],
                      {"shot": target, "candidate": chosen,
                       "version": [current[target]["version"], selection["version"]]})
                page.screenshot(path=str(evidence / f"{stamp}-{args.label}-adopted.png"))

                stage_nav.goto(page, "deliver")
                blocked = wait_gate(page)
                stale_rules = [item["rule"] for item in blocked["findings"]
                               if item["rule"] == "export.suite_review_current"]
                check("AD-03a", "选择变化后整套检查过期并阻断交付",
                      blocked["disabled"] is True and bool(stale_rules),
                      {"status": blocked.get("status"), "rules": stale_rules})
                page.click("#suite-review-run")
                page.wait_for_function(
                    """() => ((document.getElementById('suite-review-status') || {}).textContent || '')
                        .indexOf('整套检查 ') >= 0""", timeout=180_000)
                cleared = wait_gate(page)
                blocking = [item for item in cleared["findings"] if item["severity"] == "BLOCK"]
                check("AD-03b", "重跑整套检查后门禁放行",
                      cleared["disabled"] is False and not blocking,
                      {"status": cleared.get("status"), "blocking": blocking[:3]})

                delivery_path = workdir / "delivery.zip"
                delivery = download_delivery(page, delivery_path)
                zoom = inspect_zip(delivery_path)
                manifest = json.loads(zipfile_read(delivery_path, "manifest.json"))
                row = next((item for item in manifest["images"] if item["shot_id"] == target), None)
                expected_sha = selection.get("candidate_sha256") or ""
                check("AD-04", "交付包含 5 图且该图等于刚采用的候选",
                      zoom["bad_crc_entry"] is None and zoom["images"] == 5
                      and all(item["ok"] for item in zoom["asset_checks"])
                      and row is not None and row["candidate_id"] == chosen
                      and row["asset_sha256"] == expected_sha,
                      {"download": delivery, "shot": target, "candidate": chosen,
                       "expected_sha": expected_sha[:12]})

                project_path = workdir / "project.zip"
                with page.expect_download(timeout=120_000) as info:
                    page.click("#deliver-project-package")
                info.value.save_as(str(project_path))
                exported = inspect_zip(project_path)
                after = page.evaluate(SNAPSHOT)
                page.reload(wait_until="networkidle", timeout=60_000)
                reloaded = page.evaluate(SNAPSHOT)

                context_b = browser.new_context(viewport={"width": 1280, "height": 900},
                                                ignore_https_errors=True)
                page2 = context_b.new_page()
                page2.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
                page2.on("pageerror", lambda e: page_errors.append(str(e)))
                page2.goto(args.base + "/", wait_until="networkidle", timeout=60_000)
                page2.set_input_files("#import-file", str(project_path))
                expect(page2.locator("#home-status")).to_be_visible(timeout=60_000)
                expect(page2.locator("#project-list .project-row")).to_have_count(1, timeout=60_000)
                reimported = page2.evaluate(SNAPSHOT)
                check("AD-05", "项目包再导入与刷新后文档/资产相等",
                      reimported["documents"] == after["documents"]
                      and reimported["assets"] == after["assets"]
                      and reloaded["documents"] == after["documents"]
                      and exported["format"] == "amz-listing-kit-project"
                      and all(item["ok"] for item in exported["asset_checks"]),
                      {"documents": len(reimported["documents"]),
                       "assets": len(reimported["assets"])})
                page2.screenshot(path=str(evidence / f"{stamp}-{args.label}-reimport.png"))
                check("AD-06", "全程零 console/page error",
                      not console and not page_errors,
                      {"console": console[:5], "page": page_errors[:5]})
                context_a.close()
                context_b.close()
            finally:
                browser.close()
    except Exception as error:  # noqa: BLE001
        checks.append({"id": "AD-EXC", "title": "执行异常", "ok": False,
                       "detail": f"{type(error).__name__}: {error}"})
        print(f"  [FAIL] AD-EXC {type(error).__name__}: {error}")

    passed = sum(1 for item in checks if item["ok"])
    payload = {
        "schema": "amz-release-online-adoption/v1",
        "status": "passed" if passed == len(checks) and checks else "failed",
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "base": args.base, "source_package": str(source),
        "passed": passed, "total": len(checks), "checks": checks,
        "console_errors": console[:20], "page_errors": page_errors[:20],
    }
    (evidence / f"{stamp}-{args.label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("=" * 72)
    print(f"{passed}/{len(checks)} 通过")
    return 0 if payload["status"] == "passed" else 1


def zipfile_read(path: Path, member: str) -> bytes:
    import zipfile  # noqa: PLC0415
    with zipfile.ZipFile(path) as archive:
        return archive.read(member)


if __name__ == "__main__":
    raise SystemExit(main())
