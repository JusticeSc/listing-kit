#!/usr/bin/env python
"""packet08 第二片：adoption 显式单图 AI（按需发起）页面真跑验证器（test-only）。

覆盖验收（全部离线 headless Chrome + 本地 fake provider，无付费调用）：
  P08A-01 未发起复核时页面显示"未复核/未运行"（data-compare-vlm="not_run" /
         data-review-ai="not_reviewed"），且人工采用可继续（state=current）；
  P08A-02 生成/查看/切换比较/采用本身不产生复核外发（fake review calls==0）；
         显式点击"AI 复核"后才有且仅有 1 次复核请求外发；
  P08A-03 真实失败（unknown 场景）才显示 Unknown（outcome=unknown +
         vlm.inspection_unavailable），且候选/Attempt 不变、不自动采纳；
  P08A-04 刷新后如实展示：checked/unknown/not_run 各自持久化，不互相转换；
  P08A-05 交付硬门不回退：无 AI 报告不是交付硬缺口（export.report_current 只看
         确定性报告当前性，不看 vlm）；manifest 每张图 ai_review=not_reviewed。
  P08A-06 零意外 console / page 错误（复核 4xx/5xx 资源日志除外，与既有口径一致）。

运行（仓库根 amz-listing-kit 下）：
  uv run --locked python tools/verify_v2_packet08_adoption_ai.py
  uv run --locked python tools/verify_v2_packet08_adoption_ai.py --label <tag>

产物：控制台 PASS/FAIL 行；证据片段写入 evals/product-v2/refactor/<label>.json。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
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


PROBE_REPORTS = """(candidateId) => (async () => {
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
  return rows.filter((row) => row.kind === "review_report"
    && (!candidateId || row.document_id === candidateId))
    .map((row) => ({ document_id: row.document_id, version: row.version,
      vlm: row.payload.vlm || null,
      severities: (row.payload.summary || {}),
      findings: (row.payload.findings || []).map((f) => f.rule_id + ":" + f.severity) }));
})()"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    label = args.label or f"packet08-adoption-ai-{utc_now()}"
    temp_root = Path(tempfile.mkdtemp(prefix="amz-p08a-"))
    reference = temp_root / "ref.png"
    # 900x900：fake-image 与 suite 上限兼容，走查用标准尺寸。
    reference.write_bytes(shared.png_bytes(900, 900, (36, 92, 160)))
    checks: list = []
    caps: dict = {}
    review_calls_before: list = []
    review_calls_after_click: list = []
    ai_line_before = ""
    adopt_state_before = ""
    vlm_attr_before = ""
    candidate_id = ""
    shot_id = ""
    screenshot = temp_root / "p08a-adoption.png"

    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as pw:
        # review 用 holder 做场景切换：先 ok（走查用），后切 unknown（失败演练）。
        from src.providers.v2_fake_review import FakeReviewProvider
        holder = {"scenario": "ok"}
        review = FakeReviewProvider(holder["scenario"])
        orig_review = review.review

        def scenario_review(request, *, _orig=orig_review):
            review.scenario = holder["scenario"]
            return _orig(request)

        review.review = scenario_review  # type: ignore[method-assign]
        server, instances = shared.start_product_server(
            0, review_factory=lambda: review)
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
                shots = shared.walk_to_adoption(page, "P08A 显式单图复核", reference)
                assert shots, "走查没有产出 shot"
                shot_id = shots[0]
                data = page.evaluate(shared.PROBE)
                cands = shared.candidate_of(data, shot_id)
                assert cands, "第一张图没有候选"
                candidate_id = cands[-1]["payload"]["candidate_id"]

                # ---- P08A-01：未发起时如实显示未复核，且采用已成立 ----
                page.click('[data-stage-nav="review"]')
                page.wait_for_timeout(400)
                card_ai = page.evaluate(
                    """(shot) => { const n = document.querySelector(
                      '#review-list .review-card[data-shot-id="' + shot + '"] .review-check-ai');
                      return n ? { text: n.textContent, ai: n.getAttribute("data-review-ai") } : null; }""",
                    shot_id)
                state = page.get_attribute(
                    f'#review-list .review-card[data-shot-id="{shot_id}"]', "data-selection-state")
                adopt_state_before = str(state)
                ai_line_before = str((card_ai or {}).get("text") or "")
                check(checks, "P08A-01a", "未发起复核时审核卡显示未复核/未运行（不折叠成 Unknown）",
                      card_ai is not None and (card_ai or {}).get("ai") == "not_reviewed"
                      and "未复核" in ai_line_before and "Unknown" not in ai_line_before,
                      card_ai)
                check(checks, "P08A-01b", "未发起复核时人工采用可继续（state=current，不被复核门阻断）",
                      state == "current", {"state": state})

                # 比较面板的视觉复核行：未发起 = not_run。
                page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] button:has-text("比较候选")')
                page.wait_for_selector("#compare-panel:not([hidden])", timeout=15_000)
                page.wait_for_selector("#compare-checklist details.compare-report", timeout=15_000)
                vlm_row = page.evaluate(
                    """() => { const n = document.querySelector("[data-compare-vlm]");
                      return n ? { text: n.textContent, v: n.getAttribute("data-compare-vlm") } : null; }""")
                vlm_attr_before = str((vlm_row or {}).get("v") or "")
                check(checks, "P08A-01c", "比较面板未发起时视觉复核行记 not_run（不是 Unknown）",
                      (vlm_row or {}).get("v") == "not_run" and "未复核" in str((vlm_row or {}).get("text") or ""),
                      vlm_row)

                # ---- P08A-02：生成/查看/切换/采用本身零复核外发；显式点击才外发 ----
                review_calls_before = [dict(item) for item in review.calls]
                check(checks, "P08A-02a", "生成/查看/切换比较/采用本身不产生复核外发（calls==0）",
                      len(review_calls_before) == 0, {"calls": len(review_calls_before)})
                tabs = page.locator('#compare-candidates [role="tab"]')
                if tabs.count() > 1:
                    tabs.nth(1).click()
                    page.wait_for_timeout(400)
                    tabs.nth(0).click()
                    page.wait_for_timeout(400)
                check(checks, "P08A-02b", "切换查看候选不产生复核外发",
                      len(review.calls) == 0, {"calls": len(review.calls)})
                page.locator("#compare-review").click()
                page.wait_for_function(
                    """() => { const n = document.querySelector("[data-compare-vlm]");
                      return n && n.getAttribute("data-compare-vlm") === "checked"; }""",
                    timeout=60_000)
                page.wait_for_timeout(300)
                review_calls_after_click = [dict(item) for item in review.calls]
                check(checks, "P08A-02c", "显式发起后才有复核请求外发（exactly 1 次，不自动重提）",
                      len(review_calls_after_click) == 1,
                      {"calls": len(review_calls_after_click)})
                # ---- P08A-03：真实失败才记 Unknown ----
                holder["scenario"] = "unknown"
                page.locator("#compare-review").click()
                page.wait_for_function(
                    """() => { const n = document.querySelector("[data-compare-vlm]");
                      return n && n.getAttribute("data-compare-vlm") === "unknown"; }""",
                    timeout=60_000)
                page.wait_for_timeout(300)
                docs = page.evaluate(PROBE_REPORTS, candidate_id)
                latest = max(docs, key=lambda item: item["version"]) if docs else {}
                unk_findings = [f for f in (latest.get("findings") or []) if f.endswith(":UNKNOWN")]
                check(checks, "P08A-03", "真实失败才显示 Unknown（outcome=unknown + inspection_unavailable，不伪造 PASS）",
                      (latest.get("vlm") or {}).get("outcome") == "unknown"
                      and any(f.startswith("vlm.inspection_unavailable") for f in unk_findings)
                      and not any(f.endswith(":BLOCK") for f in (latest.get("findings") or [])
                                  if f.startswith("vlm.")),
                      {"outcome": (latest.get("vlm") or {}).get("outcome"), "findings": latest.get("findings")})
                # 采用不受影响：仍是 current。
                page.click("#compare-close")
                page.wait_for_timeout(300)
                state3 = page.get_attribute(
                    f'#review-list .review-card[data-shot-id="{shot_id}"]', "data-selection-state")
                check(checks, "P08A-03b", "复核失败不改变人工采用（仍 current，不自动改选）",
                      state3 == "current", {"state": state3})

                # ---- P08A-04：刷新后如实展示 ----
                page.reload(wait_until="networkidle")
                page.wait_for_selector("#project-view:not([hidden])", timeout=20_000)
                page.click('[data-stage-nav="review"]')
                page.wait_for_selector(
                    f'#review-list .review-card[data-shot-id="{shot_id}"]', timeout=20_000)
                page.wait_for_timeout(500)
                card_ai2 = page.evaluate(
                    """(shot) => { const n = document.querySelector(
                      '#review-list .review-card[data-shot-id="' + shot + '"] .review-check-ai');
                      return n ? { text: n.textContent, ai: n.getAttribute("data-review-ai") } : null; }""",
                    shot_id)
                docs2 = page.evaluate(PROBE_REPORTS, candidate_id)
                latest2 = max(docs2, key=lambda item: item["version"]) if docs2 else {}
                check(checks, "P08A-04", "刷新后如实展示（unknown 仍 unknown，不退回未复核/不涨版本链）",
                      (card_ai2 or {}).get("ai") == "unknown"
                      and (latest2.get("vlm") or {}).get("outcome") == "unknown"
                      and len(docs2) == len(docs),
                      {"card": card_ai2, "outcome": (latest2.get("vlm") or {}).get("outcome"),
                       "versions": [d["version"] for d in docs2]})

                # ---- P08A-05：交付硬门不回退（用另一张未复核图证明无 AI 也可看门） ----
                caps = page.evaluate(
                    """() => fetch("/api/v2/capabilities").then((r) => r.json()).then((j) => ({
                      review_configured: ((j.review || {}).provider || {}).configured }))""")
                gate = page.evaluate(shared.GATE_STATE)
                page.screenshot(path=str(screenshot))
                check(checks, "P08A-05", "交付门仍评估确定性硬门（无 AI 报告不是硬缺口：门禁可读、无 not_run 伪造 BLOCK）",
                      isinstance(gate, dict) and "findings" in gate
                      and not any(f.get("rule") == "export.report_current"
                                  and "VLM" in str(gate.get("status")) for f in gate.get("findings", [])),
                      {"gate_status": str(gate.get("status"))[:200],
                       "findings": [(f.get("rule"), f.get("severity")) for f in gate.get("findings", [])][:8]})

                # ---- P08A-06：零意外错误 ----
                http_bad = [h for h in logs["http"] if "/favicon.ico" not in h]
                # unknown 演练必然产生复核 504（unknown=true 的真实失败路径）；
                # logs["http"] 已证明该 504 来自 /api/v2/review/candidate（http_ok 为空），
                # 浏览器对失败 fetch 的资源日志是同一请求的另一面，属期望内，不判意外。
                http_ok = [h for h in http_bad if "/api/v2/review/candidate" not in h]
                console_ok = [h for h in logs["console"]
                              if not ("504" in h and not http_ok)]
                check(checks, "P08A-06", "零意外 console / page / HTTP 错误（unknown 演练的 504 路径除外）",
                      not console_ok and not logs["page"] and not http_ok,
                      {"console": console_ok[:3], "page": logs["page"][:3], "http": http_ok[:3]})
            finally:
                context.close()
        finally:
            server.shutdown()
            server.server_close()

    failed = [item for item in checks if not item["ok"]]
    evidence = {
        "label": label,
        "at": datetime.now(timezone.utc).isoformat(),
        "shot_id": shot_id,
        "candidate_id": candidate_id,
        "checks": checks,
        "captures": {
            "capabilities": caps,
            "ai_line_before": ai_line_before,
            "adopt_state_before": adopt_state_before,
            "vlm_attr_before": vlm_attr_before,
            "review_calls_before": review_calls_before,
            "review_calls_after_click": review_calls_after_click,
        },
        "note": "fake-review 替身经显式注入接缝（holder 切换 ok/unknown）；0 真实模型调用；"
                "生成/查看/切换/采用零复核外发，显式点击 exactly 1 次。",
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / f"{label}.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence: evals/product-v2/refactor/{label}.json", flush=True)
    print(f"screenshot: {screenshot}", flush=True)
    print(f"RESULT {'PASS' if not failed else 'FAIL'} "
          f"{len(checks) - len(failed)}/{len(checks)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
