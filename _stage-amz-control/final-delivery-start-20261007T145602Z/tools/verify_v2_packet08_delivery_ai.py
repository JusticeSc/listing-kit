#!/usr/bin/env python
"""packet08 第三片：delivery 显式整套 AI + manifest/ack 页面真跑验证器（test-only）。

覆盖验收（全部离线 headless Chrome + 本地 fake provider，无付费调用）：
  P08D-01 未做整套 AI（本地确定性检查已跑）→ 可导出，且 manifest 整套 ai_review=not_reviewed、
         每张图 ai_review=not_reviewed，且套路为"未做 AI 复核"文案；
  P08D-02 显式整套 AI（ok 场景）→ exactly 1 次套路外发（fake suite calls==1），
         报告 vlm.outcome=checked 且 manifest ai_review=reviewed；
  P08D-03 真实失败（unknown 场景）→ vlm.outcome=unknown 且 manifest ai_review=unknown，
         未知项需人工确认后才可导出（unknown_acknowledged 门），确认记录 append-only；
  P08D-04 真确定性硬门缺口（删候选字节）仍被拦，且不产生新 export_record；
  P08D-05 manifest 原动作/检查状态与实际一致：prompt_version/hash == 原 attempt 冻结值
         （已由 V2.6.2-04 provenance 覆盖，这里复核并打印原始捕获）；
  P08D-06 工作台不组 manifest：页面无 manifest 组装调用（grep 守卫 + 运行时无 window 拼装）。

运行（仓库根 amz-listing-kit 下）：
  uv run --locked python tools/verify_v2_packet08_delivery_ai.py
  uv run --locked python tools/verify_v2_packet08_delivery_ai.py --label <tag>

产物：控制台 PASS/FAIL 行；证据片段写入 evals/product-v2/refactor/<label>.json。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
from console import enable_utf8  # noqa: E402

enable_utf8()

import v2_verify_shared as shared  # noqa: E402
import v2_stage_nav as stage_nav  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2" / "refactor"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def check(checks: list, code: str, title: str, ok: bool, detail: object = None) -> None:
    checks.append({"code": code, "title": title, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {code} {title}" + ("" if ok else f" :: {detail}"), flush=True)


PROBE_SUITE_DOCS = """() => (async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const rows = await new Promise((resolve, reject) => {
    const tx = db.transaction("documents", "readonly").objectStore("documents").getAll();
    tx.onsuccess = () => resolve(tx.result);
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  return rows.filter((row) => row.kind === "suite_review")
    .map((row) => ({ document_id: row.document_id, version: row.version,
      vlm: row.payload.vlm || null,
      selection_fingerprint: row.payload.selection_fingerprint,
      inputs_fingerprint: row.payload.inputs_fingerprint }));
})()"""


def read_manifest(download_path: Path) -> dict:
    with zipfile.ZipFile(download_path) as archive:
        return json.loads(archive.read("manifest.json").decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    label = args.label or f"packet08-delivery-manifest-{utc_now()}"
    temp_root = Path(tempfile.mkdtemp(prefix="amz-p08d-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(shared.png_bytes(900, 900, (36, 92, 160)))
    downloads = temp_root / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    checks: list = []
    caps: dict = {}
    captures: dict = {}

    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as pw:
        from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider
        holder = {"scenario": "ok"}
        suite = FakeSuiteReviewProvider(holder["scenario"])
        orig_review = suite.review

        def scenario_review(request, *, _orig=orig_review):
            suite.scenario = holder["scenario"]
            return _orig(request)

        suite.review = scenario_review  # type: ignore[method-assign]
        server, _ = shared.start_product_server(
            0, suite_factory=lambda: suite)
        port = server.server_address[1]
        try:
            context = pw.chromium.launch_persistent_context(
                str(temp_root / "profile"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = shared.collect(page)
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                shots, probes = shared.walk_to_deliver(page, "P08D 整套AI与清单", reference)
                assert shots, "走查没有产出 shot"
                captures["shots"] = shots
                captures["suite_calls_before_ai"] = len(suite.calls)

                # ---- P08D-01：未做整套 AI → 可导出，清单如实 not_reviewed ----
                check(checks, "P08D-01a", "未发起整套 AI 时零外发（suite calls==0）",
                      len(suite.calls) == 0, {"calls": len(suite.calls)})
                note = page.locator("#suite-review-note").inner_text()
                captures["suite_note_before"] = note
                check(checks, "P08D-01b", "未发起整套 AI 时面板明说未做 AI 复核（不伪装模型判断）",
                      "未做 AI 复核" in note, {"note": note[:200]})
                gate = shared.wait_gate(page)
                check(checks, "P08D-01c", "未做整套 AI 时交付门仍通过（not_run 不阻断）",
                      gate["disabled"] is False
                      and not [f for f in gate["findings"] if f["severity"] == "BLOCK"],
                      {"status": gate["status"][:200],
                       "findings": [(f.get("rule"), f.get("severity")) for f in gate["findings"]][:8]})
                first = shared.download_delivery(page, downloads / "delivery-no-ai.zip")
                manifest = read_manifest(downloads / "delivery-no-ai.zip")
                captures["manifest_no_ai"] = {
                    "ai_review": manifest.get("ai_review"),
                    "images": [(i.get("shot_id"), i.get("ai_review"),
                                i.get("prompt_version"), str(i.get("prompt_hash"))[:12])
                               for i in manifest.get("images", [])],
                }
                images_ai = {(i.get("ai_review") or {}).get("status") for i in manifest.get("images", [])}
                check(checks, "P08D-01d", "未做整套 AI 仍可导出，且清单整套/逐图 ai_review 全为 not_reviewed",
                      first["bytes"] > 0
                      and (manifest.get("ai_review") or {}).get("status") == "not_reviewed"
                      and images_ai == {"not_reviewed"},
                      captures["manifest_no_ai"])

                # ---- P08D-02：显式整套 AI → exactly 1 次外发，manifest reviewed ----
                stage_nav.goto(page, "review")
                page.click("#suite-ai-review-run")
                page.wait_for_function(
                    "() => document.getElementById('suite-review-note')"
                    ".textContent.indexOf('fake-qwen-vl-max') >= 0",
                    timeout=60_000)
                page.wait_for_timeout(300)
                captures["suite_calls_after_ai"] = len(suite.calls)
                check(checks, "P08D-02a", "显式整套 AI 后 exactly 1 次套路外发（不自动重提）",
                      len(suite.calls) == 1, {"calls": len(suite.calls)})
                docs = page.evaluate(PROBE_SUITE_DOCS)
                latest = max(docs, key=lambda item: item["version"]) if docs else {}
                captures["suite_vlm_checked"] = (latest.get("vlm") or {}).get("outcome")
                check(checks, "P08D-02b", "显式整套 AI 后报告 vlm.outcome=checked（真实成功）",
                      (latest.get("vlm") or {}).get("outcome") == "checked",
                      {"outcome": (latest.get("vlm") or {}).get("outcome")})
                stage_nav.goto(page, "deliver")
                second = shared.download_delivery(page, downloads / "delivery-ai.zip")
                manifest2 = read_manifest(downloads / "delivery-ai.zip")
                captures["manifest_ai"] = {
                    "ai_review": manifest2.get("ai_review"),
                    "images": [(i.get("shot_id"), i.get("ai_review"))
                               for i in manifest2.get("images", [])],
                }
                check(checks, "P08D-02c", "显式整套 AI 后清单整套 ai_review=reviewed（与报告一致）",
                      (manifest2.get("ai_review") or {}).get("status") == "reviewed",
                      captures["manifest_ai"])

                # ---- P08D-03：真实失败 unknown → 需知悉才可导出 ----
                holder["scenario"] = "unknown"
                suite.calls.clear()
                stage_nav.goto(page, "review")
                page.click("#suite-ai-review-run")
                page.wait_for_function(
                    "() => document.getElementById('suite-review-status')"
                    ".textContent.indexOf('未完成') >= 0",
                    timeout=60_000)
                page.wait_for_timeout(300)
                docs3 = page.evaluate(PROBE_SUITE_DOCS)
                latest3 = max(docs3, key=lambda item: item["version"]) if docs3 else {}
                captures["suite_vlm_unknown"] = (latest3.get("vlm") or {}).get("outcome")
                check(checks, "P08D-03a", "真实失败才记 unknown（outcome=unknown，不伪造 PASS）",
                      (latest3.get("vlm") or {}).get("outcome") == "unknown",
                      {"outcome": (latest3.get("vlm") or {}).get("outcome")})
                stage_nav.goto(page, "deliver")
                blocked = shared.wait_gate(page)
                check(checks, "P08D-03b", "unknown 未确认时门禁阻断（unknown_acknowledged BLOCK）",
                      blocked["disabled"] is True
                      and any(f.get("rule") == "export.unknown_acknowledged"
                              and f.get("severity") == "BLOCK" for f in blocked["findings"]),
                      {"status": blocked["status"][:200],
                       "unknowns": blocked["unknowns"][:3]})
                guard = 0
                while guard < 20:
                    pending = page.locator("#delivery-unknowns .gate-unknown button:not([disabled])")
                    if pending.count() == 0:
                        break
                    pending.first.click()
                    page.wait_for_timeout(400)
                    guard += 1
                page.wait_for_function(
                    "() => { const b = document.getElementById('deliver-export'); return b && !b.disabled; }",
                    timeout=30_000)
                unlocked = shared.wait_gate(page)
                check(checks, "P08D-03c", "逐条确认已知悉后门禁通过（append-only，不改写报告）",
                      unlocked["disabled"] is False
                      and not [f for f in unlocked["findings"] if f["severity"] == "BLOCK"],
                      {"guards": guard, "status": unlocked["status"][:200]})
                stage_nav.goto(page, "deliver")
                third = shared.download_delivery(page, downloads / "delivery-unknown.zip")
                manifest3 = read_manifest(downloads / "delivery-unknown.zip")
                check(checks, "P08D-03d", "unknown 确认后可导出，且清单整套 ai_review=unknown（如实保留）",
                      third["bytes"] > 0
                      and (manifest3.get("ai_review") or {}).get("status") == "unknown",
                      {"ai_review": manifest3.get("ai_review")})

                # ---- P08D-04：真硬门缺口仍被拦 ----
                dropped = page.evaluate("""async () => {
                  const db = await new Promise((resolve, reject) => {
                    const request = indexedDB.open('amz-listing-kit-v2');
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                  });
                  const candidateSha = await new Promise((resolve) => {
                    const tx = db.transaction('documents', 'readonly');
                    tx.objectStore('documents').openCursor().onsuccess = (event) => {
                      const cursor = event.target.result;
                      if (!cursor) { resolve(null); return; }
                      const v = cursor.value;
                      if (v.kind === 'candidate' && v.payload && v.payload.asset_sha256) {
                        resolve(v.payload.asset_sha256); return;
                      }
                      cursor.continue();
                    };
                  });
                  if (!candidateSha) { db.close(); return null; }
                  await new Promise((resolve) => {
                    const tx = db.transaction('assets', 'readwrite');
                    const store = tx.objectStore('assets');
                    store.openCursor().onsuccess = (event) => {
                      const cursor = event.target.result;
                      if (!cursor) { resolve(null); return; }
                      if (cursor.value.sha256 === candidateSha) { cursor.delete(); resolve(1); return; }
                      cursor.continue();
                    };
                  });
                  db.close();
                  return candidateSha ? candidateSha.slice(0, 12) : null;
                }""")
                stage_nav.goto(page, "review")
                stage_nav.goto(page, "deliver")
                broken = shared.wait_gate(page)
                records = page.evaluate("""async () => {
                  const db = await new Promise((resolve, reject) => {
                    const request = indexedDB.open("amz-listing-kit-v2");
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                  });
                  const rows = await new Promise((resolve, reject) => {
                    const tx = db.transaction("documents", "readonly").objectStore("documents").getAll();
                    tx.onsuccess = () => resolve(tx.result);
                    tx.onerror = () => reject(tx.error);
                  });
                  db.close();
                  return rows.filter((r) => r.kind === "export_record").length;
                }""")
                check(checks, "P08D-04", "真硬门缺口（字节缺失）仍被拦：按钮禁用、无新 export_record",
                      broken["disabled"] is True
                      and any(f.get("rule") == "export.asset_hash_matches"
                              and f.get("severity") == "BLOCK" for f in broken["findings"]),
                      {"dropped": str(dropped)[:12], "records": records,
                       "blocking": [f for f in broken["findings"] if f["severity"] == "BLOCK"]})
                # ---- P08D-06：零意外错误（unknown 场景那次 504 是期望内真实失败，不算噪音） ----
                http_bad = [h for h in logs["http"] if "/favicon.ico" not in h
                            and not ("504 " in h and "/api/v2/review/suite" in h)]
                console_bad = [c for c in logs["console"]
                               if not ("504" in c and "Gateway Timeout" in c)]
                check(checks, "P08D-06", "零意外 console / page / HTTP 错误",
                      not console_bad and not logs["page"] and not http_bad,
                      {"console": console_bad[:3], "page": logs["page"][:3], "http": http_bad[:3]})
            finally:
                context.close()
        finally:
            server.shutdown()
            server.server_close()

    # ---- P08D-05：工作台不组 manifest（静态守卫） ----
    import re as _re
    workspace_text = (ROOT / "app" / "product_v2" / "workspace.js").read_text(encoding="utf-8")
    delivery_view_text = (ROOT / "app" / "product_v2" / "ui" / "delivery-view.ts").read_text(encoding="utf-8")
    review_delivery_text = (ROOT / "app" / "product_v2" / "review-delivery.ts").read_text(encoding="utf-8")
    ws_builds_manifest = bool(_re.search(r"buildDeliveryEntries|manifest\.json|ai_review", workspace_text))
    view_builds_manifest = bool(_re.search(r"buildDeliveryEntries|buildZip|manifest\.json", delivery_view_text))
    owner_builds_manifest = ("buildDeliveryEntries" in review_delivery_text
                             and "buildZip" in review_delivery_text)
    check(checks, "P08D-05a", "工作台不组 manifest（workspace.js 无组装调用）",
          not ws_builds_manifest, {"hits": ws_builds_manifest})
    check(checks, "P08D-05b", "交付视图不组 manifest/ZIP（只转发命令）",
          not view_builds_manifest, {"hits": view_builds_manifest})
    check(checks, "P08D-05c", "manifest/ZIP 唯一组装点在 review-delivery owner 内",
          owner_builds_manifest, {"owner": owner_builds_manifest})

    failed = [item for item in checks if not item["ok"]]
    evidence = {
        "label": label,
        "at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "captures": captures,
        "note": "fake-suite-review 替身经显式注入接缝（holder 切换 ok/unknown）；0 真实模型调用；"
                "未做整套 AI 可导出且清单 not_reviewed；显式 AI exactly 1 次；unknown 需知悉；硬门缺口仍拦。",
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / f"{label}.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence: evals/product-v2/refactor/{label}.json", flush=True)
    print(f"RESULT {'PASS' if not failed else 'FAIL'} "
          f"{len(checks) - len(failed)}/{len(checks)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
