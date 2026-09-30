#!/usr/bin/env python
"""V2.5.3 候选比较与审核清单面板验证：静态守卫 + 领域契约套件 + 真实工作台走查 + 视觉证据。

正向：异常优先排序、同档新到旧、默认目标、参考图栏与真实发送一致、键盘路径、
      完整报告按需展开、单候选回退与「下一个待处理」跳转。
反向：乱序/重复/状态不一致的行集合必须被领域自检抓住；面板不得写业务状态、
      不得长成采纳或导出入口（那是 V2.6.1 的边界）。

用法：
    uv run --locked python tools/verify_v2_5_3_compare_panel.py --label final
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402  （V2.UI.2 六阶段工作台导航）
from console import enable_utf8  # noqa: E402
enable_utf8()

from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402

PRODUCT_DIR = ROOT / "app" / "product_v2"
HARNESS_DIR = ROOT / "evals" / "product-v2" / "harness"
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"
COMPARE_CONTRACT_VERSION = "v2.5.3"
EXPECTED_COMPARE_CASES = [f"CP-{index:02d}" for index in range(1, 16)]
EXPECTED_REVIEW_CASES = [f"R{index}" for index in range(1, 14)]
EXPECTED_PROVIDER_CASES = [f"R{index}" for index in range(14, 22)]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v251 = load_module(ROOT / "tools" / "verify_v2_5_1_deterministic_review.py", "verify_v251")
server_module = v251.load_server_module()


def product_text(relative: str) -> str:
    return (PRODUCT_DIR / relative).read_text(encoding="utf-8")


def compare_section(text: str) -> str:
    """workspace.js 里比较面板那一整块（分区注释 → renderAttempts 之前）。"""

    start = text.index("候选比较与审核清单（V2.5.3）")
    end = text.index("function renderAttempts", start)
    return text[start:end]


def check_static_guards() -> list[dict]:
    checks: list[dict] = []
    syntax_targets = [
        PRODUCT_DIR / "domain" / "compare.js",
        PRODUCT_DIR / "domain" / "review.js",
        PRODUCT_DIR / "domain" / "index.js",
        PRODUCT_DIR / "workspace.js",
        HARNESS_DIR / "compare-panel.js",
        Path(__file__).resolve(),
    ]
    results = []
    for target in syntax_targets:
        if target.suffix == ".js":
            command = ["node", "--check", str(target)]
        else:
            command = [sys.executable, "-c",
                       "import ast,pathlib,sys;ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))",
                       str(target)]
        completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, check=False)
        results.append({"file": target.relative_to(ROOT).as_posix(), "rc": completed.returncode,
                        "stderr": completed.stderr.strip()[-160:]})
    checks.append({
        "id": "V2.5.3-01",
        "title": "语法门：compare / review / workspace / 契约套件与本工具全部可解析",
        "ok": all(item["rc"] == 0 for item in results),
        "detail": {"files": results},
    })

    review_text = product_text("domain/review.js")
    compare_text = product_text("domain/compare.js")
    workspace_text = product_text("workspace.js")
    canonical = '["BLOCK", "HIGH_RISK", "WARNING", "UNKNOWN"]'
    duplicates = [name for name, text in (("domain/compare.js", compare_text),
                                          ("workspace.js", workspace_text))
                  if re.search(r'\[\s*"BLOCK"\s*,\s*"HIGH_RISK"', text)]
    checks.append({
        "id": "V2.5.3-02",
        "title": "单一权威：先看顺序只在 domain/review.js 定义，比较模块与工作台只引用",
        "ok": canonical in review_text and not duplicates
              and "REVIEW_SEVERITY_ORDER" in compare_text
              and "compareSeverityRank" in compare_text,
        "detail": {"order_in_review": canonical in review_text, "duplicated_in": duplicates},
    })

    block = compare_section(workspace_text)
    forbidden = [token for token in ("documents.save", "assets.put", "REVIEW_KIND", "CANDIDATE_KIND",
                                     "selection", "SELECTION") if token in block]
    checks.append({
        "id": "V2.5.3-03",
        "title": "比较面板是纯投影：不写文档、不写资产、不产生选择",
        "ok": not forbidden,
        "detail": {"forbidden_tokens": forbidden, "section_chars": len(block)},
    })

    html = (PRODUCT_DIR / "index.html").read_text(encoding="utf-8")
    wiring = {
        "panel": 'id="compare-panel"' in html,
        "tablist": 'role="tablist"' in html,
        "tabpanel": 'role="tabpanel"' in html,
        "contract_constant": f'COMPARE_CONTRACT_VERSION = "{COMPARE_CONTRACT_VERSION}"' in compare_text,
        "contract_used": "COMPARE_CONTRACT_VERSION" in workspace_text,
        "default_projection": "defaultCompareTargetId" in workspace_text,
    }
    checks.append({
        "id": "V2.5.3-04",
        "title": "面板接线：HTML 的 tablist/tabpanel 与合同版本贯穿领域层与工作台",
        "ok": all(wiring.values()),
        "detail": wiring,
    })
    return checks


INJECT_FIXTURE_CANDIDATE = """
async ({ projectId, shotId, pngBase64, actionId, taskId }) => {
  const storage = await import("/storage/index.js");
  const domain = await import("/domain/index.js");
  const opened = await storage.openStorage();
  try {
    const binary = atob(pngBase64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    const plans = await opened.repository.documents.listLatest(
      projectId, domain.DOMAIN_DOCUMENT_KINDS.suite_plan);
    const plan = plans.length ? plans[0].payload : null;
    const shot = plan ? plan.shots.find((item) => item.shot_id === shotId) : null;
    const dimensions = domain.parsePngDimensions(bytes);
    const asset = await opened.repository.assets.put(projectId, {
      bytes: bytes.buffer,
      mediaType: "image/png",
      originalName: shotId + "-fixture-clean.png",
      role: "candidate",
      width: dimensions.width,
      height: dimensions.height,
    });
    const candidate = domain.buildCandidateRecord({
      shotId: shotId,
      attempt: { state: "succeeded", action_id: actionId, task_id: taskId },
      assetSha256: asset.sha256,
      byteSize: asset.byte_size,
      width: dimensions.width,
      height: dimensions.height,
      at: new Date().toISOString(),
    });
    const saved = await opened.repository.documents.save(projectId, {
      kind: domain.DOMAIN_DOCUMENT_KINDS.candidate,
      documentId: shotId,
      payload: candidate,
    });
    const findings = domain.evaluateCandidateFindings({
      candidate: candidate, bytes: bytes, roleId: shot ? shot.role_id : null,
    });
    const report = domain.buildReviewReport({
      candidate: candidate, findings: findings, at: new Date().toISOString(),
    });
    await opened.repository.documents.save(projectId, {
      kind: domain.DOMAIN_DOCUMENT_KINDS.review_report,
      documentId: candidate.candidate_id,
      payload: report,
    });
    return {
      candidate_id: candidate.candidate_id,
      version: saved.version,
      sha256: candidate.asset_sha256,
      role_id: shot ? shot.role_id : null,
      severities: findings.map((item) => item.severity),
    };
  } finally {
    opened.close();
  }
}
"""


PANEL_PROBE = """
() => {
  const panel = document.getElementById("compare-panel");
  if (!panel) return { missing: true };
  const checklist = panel.querySelector("#compare-checklist");
  const stateNode = checklist ? checklist.querySelector("[data-compare-state]") : null;
  const details = panel.querySelector("details.compare-report");
  const active = document.activeElement;
  return {
    visible: !panel.hidden,
    contract: panel.dataset.compareContract || null,
    shot_id: panel.dataset.shotId || null,
    subject: (document.getElementById("compare-subject") || {}).textContent || "",
    status: (document.getElementById("compare-status") || {}).textContent || "",
    selected_candidate_id: (panel.querySelector('#compare-candidates [role="tab"][aria-selected="true"]') || {}).dataset
      ? panel.querySelector('#compare-candidates [role="tab"][aria-selected="true"]').dataset.candidateId : null,
    focused_tab_id: active && active.getAttribute && active.getAttribute("role") === "tab"
      ? active.id : null,
    focused_compare_action: active && active.dataset ? (active.dataset.compareAction || null) : null,
    focus_shot: (() => {
      if (!active) return null;
      if (active.dataset && active.dataset.compareAction) return active.dataset.compareAction;
      const card = active.closest ? active.closest(".review-card[data-shot-id]") : null;
      return card ? card.getAttribute("data-shot-id") : null;
    })(),
    focus_visible: Boolean(active && active.offsetParent !== null),
    cards: [...panel.querySelectorAll('#compare-candidates [role="tab"]')].map((node) => ({
      candidate_id: node.dataset.candidateId,
      state: node.dataset.reviewState,
      selected: node.getAttribute("aria-selected") === "true",
      tabindex: node.tabIndex,
      version_text: (node.querySelector(".name") || {}).textContent || "",
      headline: (node.querySelector(".compare-headline") || {}).textContent || "",
      has_image: Boolean(node.querySelector("img[src]")),
    })),
    findings: [...panel.querySelectorAll("#compare-checklist .compare-finding")].map((node) => ({
      severity: node.dataset.severity, rule: node.dataset.ruleId,
      text: (node.textContent || "").slice(0, 120),
    })),
    checklist_state: checklist && checklist.dataset.compareState
      ? checklist.dataset.compareState
      : (stateNode ? stateNode.dataset.compareState : null),
    checklist_first_heading: checklist
      ? ((checklist.querySelector("h5") || {}).textContent || "") : "",
    checklist_labelled_by: checklist ? checklist.getAttribute("aria-labelledby") : null,
    report_open: details ? details.open : null,
    report_summary: details ? (details.querySelector("summary") || {}).textContent || "" : null,
    report_pass_rows: details
      ? details.querySelectorAll('.compare-finding[data-severity="PASS"]').length : 0,
    report_vlm: details ? ((details.querySelector("[data-compare-vlm]") || {}).textContent || "") : "",
    criteria: [...panel.querySelectorAll(".compare-basis-list li")].map((node) => node.textContent),
    references: [...panel.querySelectorAll("#compare-references li")].map((node) => ({
      sha256: node.dataset.referenceSha256,
      has_image: Boolean(node.querySelector("img[src]")),
      text: (node.textContent || "").slice(0, 80),
    })),
    reference_title: (document.getElementById("compare-basis-title") || {}).textContent || "",
    jump_disabled: document.getElementById("compare-jump").disabled,
    jump_target: document.getElementById("compare-jump").dataset.targetShot || "",
    buttons: [...panel.querySelectorAll("button")].map((node) => node.textContent),
  };
}
"""


def run_workbench_checks(stamp: str, console_errors: list[str],
                         page_errors: list[str]) -> tuple[list[dict], dict]:
    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    checks: list[dict] = []
    ui: dict = {}
    holder = {"scenario": "ok"}
    port = v251.free_port()
    server = server_module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"),
        review_provider_factory=lambda: FakeReviewProvider(holder["scenario"]))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    static_server, static_url = v251.start_static_server()
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v253-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(v251.png_bytes(1200, 1200, (36, 92, 160)))
    reference_sha = hashlib.sha256(reference.read_bytes()).hexdigest()
    compliant = temp_root / "compliant.png"
    compliant.write_bytes(v251.png_bytes(1600, 1600, (232, 236, 240)))
    base = f"http://127.0.0.1:{port}"
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(str(profile), headless=True)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.on("console", lambda message: console_errors.append("[workbench] " + message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append("[workbench] " + str(error)))

                def probe() -> dict:
                    return page.evaluate(v251.PROBE)

                def panel_probe() -> dict:
                    return page.evaluate(PANEL_PROBE)

                def row(shot_id: str):
                    return page.locator(f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 30_000) -> None:
                    expect(row(shot_id)).to_have_attribute("data-attempt-state", state, timeout=timeout)

                def wait_candidate_ui(shot_id: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(shot) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                            return Boolean(node && node.querySelector('.attempt-candidate'));
                        }""", arg=shot_id, timeout=timeout)

                def click_row_button(shot_id: str, text: str) -> None:
                    stage_nav.goto(page, "generate")
                    row(shot_id).locator(f'button:has-text("{text}")').first.click()

                def submit_once(shot_id: str, first: bool) -> None:
                    click_row_button(shot_id, "生成这张图" if first else "再生成一张")
                    wait_state(shot_id, "submitted")
                    click_row_button(shot_id, "核对任务")
                    wait_state(shot_id, "succeeded")
                    wait_candidate_ui(shot_id)

                def open_panel(shot_id: str, card_count: int, references: int | None = None) -> None:
                    stage_nav.goto(page, "generate")
                    row(shot_id).locator('button[data-compare-action]').first.click()
                    stage_nav.goto(page, "review")
                    expect(page.locator("#compare-panel")).to_be_visible()
                    expect(page.locator("#compare-panel")).to_have_attribute(
                        "data-compare-contract", COMPARE_CONTRACT_VERSION)
                    try:
                        page.wait_for_function(
                            """(payload) => {
                                const panel = document.getElementById("compare-panel");
                                if (!panel || panel.hidden) return false;
                                if (panel.dataset.shotId !== payload.shot) return false;
                                const cards = panel.querySelectorAll('#compare-candidates [role="tab"]');
                                if (cards.length !== payload.cards) return false;
                                if (payload.references === null
                                    || payload.references === undefined) return true;
                                return panel.querySelectorAll("#compare-references li").length
                                  === payload.references;
                            }""",
                            arg={"shot": shot_id, "cards": card_count, "references": references},
                            timeout=20_000)
                    except Exception as error:  # noqa: BLE001  (诊断信息优先于原始超时)
                        raise AssertionError(
                            "打开比较面板失败：" + json.dumps(panel_probe(), ensure_ascii=False)[:1200]
                        ) from error

                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · 候选比较")
                page.click("#create-project")
                page.click('#project-list .project-row button[data-action="open"]')
                expect(page.locator("#project-view")).to_be_visible()
                page.set_input_files("#ref-file", str(reference))
                expect(page.locator("#ref-list .ref-row")).to_have_count(1)
                page.fill("#intake-name", "便携保温杯")
                page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
                page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
                page.wait_for_timeout(1200)
                project_ids = page.evaluate(
                    "async () => { const db = await new Promise((resolve) => {"
                    " const request = indexedDB.open(\"amz-listing-kit-v2\");"
                    " request.onsuccess = () => resolve(request.result); });"
                    " const rows = await new Promise((resolve) => { const req ="
                    " db.transaction(\"projects\", \"readonly\").objectStore(\"projects\").getAll();"
                    " req.onsuccess = () => resolve(req.result); });"
                    " db.close(); return rows.map((item) => item.project_id); }")
                project_id = project_ids[0]
                page.evaluate(v251.SEED_SLOTS, project_id)
                page.reload(wait_until="networkidle")
                page.click("#suite-seed")
                expect(page.locator("#shot-list .shot-row")).to_have_count(4)
                initial = probe()
                shot_ids = initial["shot_ids"]
                first_shot, second_shot = shot_ids[0], shot_ids[1]
                v251.compile_all(page, shot_ids)
                expect(page.locator("#confirm-action")).to_be_enabled()
                page.click("#confirm-action")
                expect(page.locator("#confirm-record")).to_contain_text("已确认 v")
                submit_once(first_shot, True)
                submit_once(first_shot, False)
                submit_once(second_shot, True)
                injected = page.evaluate(INJECT_FIXTURE_CANDIDATE, {
                    "projectId": project_id, "shotId": first_shot,
                    "pngBase64": base64.b64encode(compliant.read_bytes()).decode("ascii"),
                    "actionId": "act-fixture-compliant", "taskId": "task-fixture-compliant",
                })
                ui["injected"] = injected
                page.reload(wait_until="networkidle")
                expect(page.locator("#project-view")).to_be_visible()
                wait_candidate_ui(first_shot)
                seeded = probe()
                candidates_first = seeded["candidate_chains"].get(first_shot, [])
                candidates_second = seeded["candidate_chains"].get(second_shot, [])

                open_panel(first_shot, 3, references=1)
                panel = panel_probe()
                ui["panel"] = panel
                checks.append({
                    "id": "V2.5.3-07",
                    "title": "入口：每张有候选的图都有「比较候选」，点开即投影该图（无第二套状态）",
                    "ok": panel["visible"] is True
                          and panel["contract"] == COMPARE_CONTRACT_VERSION
                          and panel["shot_id"] == first_shot
                          and page.locator(
                              f'#attempt-list .attempt-row[data-shot-id="{first_shot}"] '
                              'button[data-compare-action][aria-expanded]').count() == 1,
                    "detail": {"contract": panel["contract"], "shot": panel["shot_id"],
                               "subject": panel["subject"], "visible": panel["visible"]},
                })
                checks.append({
                    "id": "V2.5.3-08",
                    "title": "参考图栏 = 这张图实际发送的参考图（与提交选择一致，不是全部参考图）",
                    "ok": len(panel["references"]) == 1
                          and panel["references"][0]["sha256"] == reference_sha
                          and panel["references"][0]["has_image"] is True
                          and "实际发送" in panel["reference_title"],
                    "detail": {"references": panel["references"],
                               "title": panel["reference_title"],
                               "expected_sha256": reference_sha[:16]},
                })
                checks.append({
                    "id": "V2.5.3-09",
                    "title": "候选卡与 IndexedDB 一致：两次生成 + 一个合规夹具 = 三张，按版本可追溯",
                    "ok": len(panel["cards"]) == len(candidates_first) == 3
                          and all(card["has_image"] for card in panel["cards"])
                          and all(card["candidate_id"] for card in panel["cards"]),
                    "detail": {"cards": [(card["candidate_id"], card["version_text"],
                                          card["state"]) for card in panel["cards"]],
                               "db_versions": [entry["version"] for entry in candidates_first]},
                })
                checks.append({
                    "id": "V2.5.3-10",
                    "title": "异常优先：有阻断的两个候选排在无发现的夹具之前，默认看排在最前的那一个",
                    "ok": panel["cards"][0]["state"] == "pending"
                          and panel["cards"][0]["selected"] is True
                          and panel["selected_candidate_id"] == panel["cards"][0]["candidate_id"]
                          and panel["cards"][-1]["candidate_id"] == injected["candidate_id"]
                          and panel["cards"][-1]["state"] == "clean"
                          and "BLOCK" not in injected["severities"],
                    "detail": {"order": [card["candidate_id"] for card in panel["cards"]],
                               "states": [card["state"] for card in panel["cards"]],
                               "selected": panel["selected_candidate_id"],
                               "fixture_severities": injected["severities"]},
                })

                tabs = page.locator('#compare-candidates [role="tab"]')
                tabs.first.focus()
                page.keyboard.press("ArrowRight")
                after_right = panel_probe()
                page.keyboard.press("End")
                after_end = panel_probe()
                page.keyboard.press("Home")
                after_home = panel_probe()
                page.keyboard.press("Escape")
                after_escape = panel_probe()
                expected_ids = [card["candidate_id"] for card in panel["cards"]]
                checks.append({
                    "id": "V2.5.3-11",
                    "title": "键盘路径：方向键/Home/End 在候选间移动并保持焦点，Escape 回到该图当前可见的比较入口",
                    "ok": after_right["selected_candidate_id"] == expected_ids[1]
                          and after_right["focused_tab_id"] == "compare-tab-" + expected_ids[1]
                          and after_end["selected_candidate_id"] == expected_ids[-1]
                          and after_home["selected_candidate_id"] == expected_ids[0]
                          and after_escape["focus_shot"] == first_shot
                          and after_escape["focus_visible"] is True
                          and after_escape["visible"] is True,
                    "detail": {"right": after_right["selected_candidate_id"],
                               "end": after_end["selected_candidate_id"],
                               "home": after_home["selected_candidate_id"],
                               "escape_focus": after_escape["focused_compare_action"],
                               "expected": expected_ids},
                })

                expect(page.locator("#compare-checklist details.compare-report")).to_have_count(1)
                collapsed = panel_probe()
                page.locator("#compare-checklist details.compare-report summary").click()
                expanded = panel_probe()
                review_contract = v251.current_review_contract()
                checks.append({
                    "id": "V2.5.3-12",
                    "title": "完整报告按需展开：默认收起，展开后含合同版本、通过项与视觉复核状态",
                    "ok": collapsed["report_open"] is False
                          and expanded["report_open"] is True
                          and review_contract in expanded["report_summary"]
                          and expanded["report_pass_rows"] >= 1
                          and "视觉复核" in expanded["report_vlm"]
                          and len(expanded["findings"]) >= 1
                          and expanded["checklist_first_heading"].startswith("先看这些")
                          and expanded["checklist_state"] == "pending"
                          and expanded["checklist_labelled_by"] == "compare-tab-" + expected_ids[0],
                    "detail": {"collapsed": collapsed["report_open"],
                               "summary": expanded["report_summary"],
                               "pass_rows": expanded["report_pass_rows"],
                               "vlm": expanded["report_vlm"],
                               "findings": len(expanded["findings"]),
                               "criteria": expanded["criteria"][:2]},
                })

                after_panel = probe()
                checks.append({
                    "id": "V2.5.3-13",
                    "title": "面板不改业务状态：候选字节、Attempt 与审核报告在交互前后完全一致",
                    "ok": v251.candidate_json(after_panel, first_shot) == v251.candidate_json(seeded, first_shot)
                          and v251.candidate_json(after_panel, second_shot) == v251.candidate_json(seeded, second_shot)
                          and json.dumps(after_panel["attempt_chains"], sort_keys=True, default=str)
                          == json.dumps(seeded["attempt_chains"], sort_keys=True, default=str)
                          and len(after_panel["review_reports"]) == len(seeded["review_reports"]),
                    "detail": {"candidates_first": len(candidates_first),
                               "reports_before": len(seeded["review_reports"]),
                               "reports_after": len(after_panel["review_reports"])},
                })

                page.reload(wait_until="networkidle")
                expect(page.locator("#project-view")).to_be_visible()
                open_panel(first_shot, 3, references=1)
                reloaded = panel_probe()
                checks.append({
                    "id": "V2.5.3-14",
                    "title": "刷新后一致：候选、默认目标与清单来自 IndexedDB，不依赖内存状态",
                    "ok": [card["candidate_id"] for card in reloaded["cards"]] == expected_ids
                          and reloaded["selected_candidate_id"] == expected_ids[0]
                          and reloaded["contract"] == COMPARE_CONTRACT_VERSION
                          and len(reloaded["references"]) == 1,
                    "detail": {"order": [card["candidate_id"] for card in reloaded["cards"]],
                               "selected": reloaded["selected_candidate_id"],
                               "contract": reloaded["contract"],
                               "references": len(reloaded["references"])},
                })

                open_panel(second_shot, len(candidates_second))
                single = panel_probe()
                jump_enabled = not single["jump_disabled"]
                page.click("#compare-jump")
                page.wait_for_function(
                    """(shot) => {
                        const panel = document.getElementById("compare-panel");
                        return Boolean(panel && !panel.hidden && panel.dataset.shotId === shot);
                    }""", arg=first_shot, timeout=20_000)
                jumped = panel_probe()
                checks.append({
                    "id": "V2.5.3-15",
                    "title": "单候选回退与「下一个待处理」：一张图一个候选照常比较，跳转落到有问题的图",
                    "ok": len(single["cards"]) == len(candidates_second) == 1
                          and single["shot_id"] == second_shot
                          and jump_enabled
                          and single["jump_target"] == first_shot
                          and jumped["shot_id"] == first_shot
                          and jumped["focused_tab_id"] == "compare-tab-" + expected_ids[0],
                    "detail": {"second_shot": second_shot, "cards": len(single["cards"]),
                               "jump_target": single["jump_target"], "landed": jumped["shot_id"],
                               "focus": jumped["focused_tab_id"]},
                })

                all_buttons = sorted({text for payload in (panel, single, jumped, reloaded)
                                      for text in payload["buttons"]})
                forbidden_buttons = [text for text in all_buttons
                                     if any(token in text for token in ("采纳", "导出", "选择"))]
                checks.append({
                    "id": "V2.5.3-16",
                    "title": "边界：面板不承担采纳与导出，只有比较所需的动作",
                    "ok": not forbidden_buttons and "下一个待处理" in all_buttons,
                    "detail": {"buttons": all_buttons, "forbidden": forbidden_buttons},
                })

                screenshot_rel = (f"evals/product-v2/evidence/"
                                  f"v2.5.3-compare-panel-{stamp}.png")
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                detail_rel = (f"evals/product-v2/evidence/"
                              f"v2.5.3-compare-panel-{stamp}-detail.png")
                page.locator("#compare-panel").screenshot(path=str(ROOT / detail_rel))
                screenshot_paths = [ROOT / screenshot_rel, ROOT / detail_rel]
                checks.append({
                    "id": "V2.5.3-17",
                    "title": "视觉证据：面板在真实工作台里可见（整页 + 面板特写截图留档）",
                    "ok": all(path.is_file() and path.stat().st_size > 0 for path in screenshot_paths),
                    "detail": {path.relative_to(ROOT).as_posix():
                               (path.stat().st_size if path.is_file() else 0)
                               for path in screenshot_paths},
                })
                ui["panel_buttons"] = all_buttons
                ui["screenshot"] = screenshot_rel
                ui["screenshot_detail"] = detail_rel
            finally:
                context.close()
    finally:
        static_server.shutdown()
        server.shutdown()
        server.server_close()
    return checks, ui


def run_harness_suites(console_errors: list[str], page_errors: list[str]) -> list[dict]:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    checks: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        static_server, static_url = v251.start_static_server()
        try:
            compare_suite = v251.read_suite(
                browser, static_url + "/harness/compare-panel.html",
                "__V2_COMPARE_RESULTS__", console_errors, page_errors)
            review_suite = v251.read_suite(
                browser, static_url + "/harness/review-contract.html",
                "__V2_REVIEW_RESULTS__", console_errors, page_errors)
            provider_suite = v251.read_suite(
                browser, static_url + "/harness/review-provider-contract.html",
                "__V2_REVIEW_PROVIDER_RESULTS__", console_errors, page_errors)
        finally:
            static_server.shutdown()
            browser.close()

    checks.append({
        "id": "V2.5.3-05",
        "title": "CP-01–CP-15 比较契约套件：异常优先、默认目标、清单排序与反向探针全部通过",
        "ok": compare_suite.get("status") == "passed"
              and sorted(item["id"] for item in compare_suite.get("cases", []))
              == EXPECTED_COMPARE_CASES,
        "detail": {"status": compare_suite.get("status"),
                   "failed": compare_suite.get("failed_ids"),
                   "cases": len(compare_suite.get("cases", []))},
    })
    checks.append({
        "id": "V2.5.3-06",
        "title": "复核契约回归：R01–R13 与 R14–R21 在比较面板落地后仍全过",
        "ok": review_suite.get("status") == "passed" and provider_suite.get("status") == "passed",
        "detail": {"review": review_suite.get("status"), "provider": provider_suite.get("status"),
                   "review_failed": review_suite.get("failed_ids"),
                   "provider_failed": provider_suite.get("failed_ids")},
    })
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.5.3 候选比较与审核清单面板验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright  # noqa: F401, PLC0415  (依赖存在性门)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    checks.extend(check_static_guards())
    checks.extend(run_harness_suites(console_errors, page_errors))
    workbench_checks, ui = run_workbench_checks(stamp, console_errors, page_errors)
    checks.extend(workbench_checks)

    entry = v251.run_entry(["--check"])
    checks.append({
        "id": "V2.5.3-18",
        "title": "正式入口 --check 全过（比较面板没有破坏既有自检）",
        # 自检条目会随批次增加：断言只看「全过」这一语义，不写死条数。
        "ok": entry["rc"] == 0 and any(
            re.search(r"V2 正式入口自检：\d+/\d+ 通过", line) for line in entry["tail"]),
        "detail": {"rc": entry["rc"], "tail": entry["tail"][-3:]},
    })
    checks.append({
        "id": "V2.5.3-19",
        "title": "零意外 console error / page error",
        "ok": not console_errors and not page_errors,
        "detail": {"console_errors": console_errors[:3], "page_errors": page_errors[:3]},
    })

    passed = sum(1 for item in checks if item["ok"])
    failed = [item["id"] for item in checks if not item["ok"]]
    observed_at = datetime.now().isoformat(timespec="seconds")
    label = args.label
    txt_path = EVIDENCE_DIR / f"v2.5.3-compare-panel-{stamp}{label}.txt"
    json_path = EVIDENCE_DIR / f"v2.5.3-compare-panel-{stamp}{label}.json"

    lines = [
        "V2.5.3 候选比较与审核清单面板验证（比较契约套件 + 真实工作台走查 + 视觉证据）",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        "=" * 76,
    ]
    for item in checks:
        lines.append(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if item.get("detail") is not None:
            lines.append("         " + json.dumps(item["detail"], ensure_ascii=False)[:360])
    lines.extend([
        "-" * 76,
        f"observed_at: {observed_at}",
        f"status: {'passed' if passed == len(checks) else 'failed'}",
        f"contract: {COMPARE_CONTRACT_VERSION}（面板）· {v251.current_review_contract()}（审核报告）",
        "model_calls: 0 · external_network_calls: 0（fake providers + 本地静态服务器）",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "边界：本套件 0 次真实模型调用；比较面板只消费既有候选与审核报告，",
        "不产生采纳（Selection 属 V2.6.1）、不写入任何业务记录。",
        "工作台走查里有一个合规夹具候选（1600×1600 PNG）用来制造「有问题的候选 vs 无发现的候选」，",
        "它由验证器通过 storage 契约写入浏览器库，不是产品界面里的假状态。",
        "",
        "CHECKS",
    ])
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
    if failed:
        lines.append("")
        lines.append("FAILED: " + ", ".join(failed))
    text = "\n".join(lines) + "\n"
    txt_path.write_text(text, encoding="utf-8")
    json_path.write_text(json.dumps({
        "suite_id": "v2.5.3-compare-panel",
        "status": "passed" if passed == len(checks) else "failed",
        "observed_at": observed_at,
        "contract": COMPARE_CONTRACT_VERSION,
        "review_contract": v251.current_review_contract(),
        "model_calls": 0,
        "external_network_calls": 0,
        "checks": checks,
        "ui": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(text)
    print("证据文件：")
    print(" - " + txt_path.relative_to(ROOT).as_posix())
    print(" - " + json_path.relative_to(ROOT).as_posix())
    if ui.get("screenshot"):
        print(" - " + ui["screenshot"])
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
