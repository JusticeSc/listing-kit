#!/usr/bin/env python
"""V2.6.1 人工选择与失效判断验证：静态守卫 + 选择契约套件 + 真实工作台走查 + 视觉证据。

正向：比较区把当前候选身份交给相邻的采用面板；采用/改选/取消只追加选择记录，记录绑定
      候选身份、候选版本与当时的审核指纹；行内摘要、候选徽标与整套进度同步；刷新后仍在。
反向：跨图候选、缺身份、非法 sha、非正整数版本、未知动作与过高 schema 版本必须被领域拒绝；
      新的成功候选只把旧选择标成过期（不覆盖、不自动改选）；选择写入失败不改旧选择；
      连点只追加一条记录；采用全程不动 Prompt/Attempt/Candidate/Review/Blob 与无关图。

用法：
    uv run --locked python tools/verify_v2_6_1_selection.py --label final
"""
from __future__ import annotations

import argparse
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
SELECTION_CONTRACT_VERSION = "v2.6.1"
SELECTION_KIND = "selection"
EXPECTED_SELECTION_CASES = [f"SL-{index:02d}" for index in range(1, 19)]
EXPECTED_REWORK_CASES = [f"RW-{index:02d}" for index in range(1, 16)]
BUSINESS_KINDS = {"prompt_version", "generation_attempt", "candidate", "review_report",
                  "generation_confirm", "selection"}
PROGRESS_PATTERN = re.compile(
    r"人工采用：必需图 (\d+)/(\d+) 张当前有效；过期 (\d+) 张；缺选 (\d+) 张。")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v251 = load_module(ROOT / "tools" / "verify_v2_5_1_deterministic_review.py", "verify_v251")
v254 = load_module(ROOT / "tools" / "verify_v2_5_4_rework_loop.py", "verify_v254")
server_module = v251.load_server_module()


def product_text(relative: str) -> str:
    return (PRODUCT_DIR / relative).read_text(encoding="utf-8")


def compare_section(text: str) -> str:
    """workspace.js 里比较面板那一整块（分区注释 → renderAttempts 之前）。"""

    start = text.index("候选比较与审核清单（V2.5.3）")
    end = text.index("function renderAttempts", start)
    return text[start:end]


def rework_section(text: str) -> str:
    """workspace.js 里单图返工那一整块（独立分区，不属于比较区，也不属于采用区）。"""

    start = text.index("单图返工闭环（V2.5.4）")
    end = text.index("人工选择与失效（V2.6.1）", start)
    return text[start:end]


def selection_section(text: str) -> str:
    """workspace.js 里人工选择那一整块（分区注释 → renderHeaderText 之前）。"""

    start = text.index("人工选择与失效（V2.6.1）")
    end = text.index("function renderHeaderText", start)
    return text[start:end]


def section_guard(block: str) -> dict:
    """采用写路径唯一：比较区只投影候选身份，直发 handleCandidateSelection 经仓储追加记录。"""

    forbidden = [token for token in (
        "indexedDB", "fetch(", "assets.put", "assets.add", "storage.openStorage",
        "prompt_version", "generation_attempt", "review_report",
    ) if token in block]
    save_at = block.find("repository.documents.save(")
    set_at = block.find("selections.set(")
    return {
        "forbidden_tokens": forbidden,
        "saves_selection": save_at >= 0 and "kind: SELECTION_KIND" in block,
        "memory_after_save": save_at >= 0 and set_at > save_at,
        "error_path_kept": "showError(elements.adoptError" in block,
        "no_auto_select": "handleCandidateSelection(" in block
                          and "handleCandidateSelection(\"select\")" in product_text("workspace.js")
                          and "handleCandidateSelection(\"clear\")" in product_text("workspace.js"),
    }


def pure_compare_guard(block: str) -> list[str]:
    """比较区不直接写业务记录：采用走选择区的 handleCandidateSelection，不在比较区落盘。"""

    return [token for token in (
        "documents.save", "assets.put", "selections.set", "fetch(",
    ) if token in block]


def pure_rework_guard(block: str) -> list[str]:
    """返工区不被采用逻辑污染：采用走 handleCandidateSelection，不进返工区。"""

    return [token for token in (
        "handleCandidateSelection", "selections.set",
        "adoptSubmit", "adoptClear",
    ) if token in block]


def negative_probe() -> dict:
    """新增守卫的判红能力：同一判据必须能被一处篡改造红。"""

    block = selection_section(product_text("workspace.js"))
    valid = section_guard(block)
    mutated = section_guard(block.replace("repository.documents.save(",
                                          "indexedDB.open(", 1))
    compare_block = compare_section(product_text("workspace.js"))
    compare_valid = pure_compare_guard(compare_block)
    compare_mutated = pure_compare_guard(compare_block + "\n  selections.set('x', {});\n")
    rework_block = rework_section(product_text("workspace.js"))
    rework_valid = pure_rework_guard(rework_block)
    rework_mutated = pure_rework_guard(rework_block + "\n  handleCandidateSelection();\n")
    red = (not mutated["saves_selection"] and not mutated["memory_after_save"]
           and bool(compare_mutated) and not compare_valid
           and bool(rework_mutated) and not rework_valid)
    return {
        "selections_save_guard_red": not mutated["saves_selection"],
        "compare_purity_guard_red": bool(compare_mutated) and not compare_valid,
        "rework_purity_guard_red": bool(rework_mutated) and not rework_valid,
        "ok": red and valid["saves_selection"] and valid["memory_after_save"]
              and valid["error_path_kept"] and not valid["forbidden_tokens"],
    }


def check_static_guards() -> list[dict]:
    checks: list[dict] = []
    syntax_targets = [
        PRODUCT_DIR / "domain" / "selection.js",
        PRODUCT_DIR / "domain" / "shared.js",
        PRODUCT_DIR / "workspace.js",
        HARNESS_DIR / "selection-contract.js",
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
        "id": "V2.6.1-01",
        "title": "语法门：selection / shared / workspace / 选择契约套件与本工具全部可解析",
        "ok": all(item["rc"] == 0 for item in results),
        "detail": {"files": results},
    })

    selection_text = product_text("domain/selection.js")
    workspace_text = product_text("workspace.js")
    html = (PRODUCT_DIR / "index.html").read_text(encoding="utf-8")
    duplicated = [token for token in ("SELECTION_CONTRACT_VERSION =", "SELECTION_SCHEMA_VERSION =",
                                      "SELECTION_ACTIONS =", "SELECTION_STATES =",
                                      "SELECTION_STATE_TEXT =", "function buildSelectionRecord")
                  if token in workspace_text]
    checks.append({
        "id": "V2.6.1-02",
        "title": "单一权威：选择记录形状、词表与合同版本只在 domain/selection.js 定义，工作台只引用",
        "ok": 'SELECTION_CONTRACT_VERSION = "v2.6.1"' in selection_text
              and 'DOMAIN_DOCUMENT_KINDS.selection' in selection_text
              and "SELECTION_CONTRACT_VERSION," in workspace_text
              and "buildSelectionRecord," in workspace_text
              and "deriveSelectionState," in workspace_text
              and not duplicated,
        "detail": {"duplicated_in_workspace": duplicated,
                   "imports_contract": "SELECTION_CONTRACT_VERSION," in workspace_text},
    })

    i_compare = html.index('<section id="compare-panel"')
    compare_html = html[i_compare:html.index('<section id="rework-panel"')]
    wiring = {
        "entry_in_compare_head": 'id="adopt-open"' in compare_html,
        "clear_in_compare_head": 'id="adopt-clear"' in compare_html,
        "no_separate_panel": '<section id="adopt-panel"' not in html,
        "status_lines": all(f'id="{name}"' in html for name in
                            ("adopt-status", "adopt-error", "adopt-progress")),
        "entry_binding": 'elements.adoptOpen.dataset.candidateSha256 = row.asset_sha256;'
                         in workspace_text,
        "direct_submit": 'elements.adoptOpen.addEventListener("click", () => { void handleCandidateSelection("select"); });'
                         in workspace_text
                         and 'elements.adoptClear.addEventListener("click", () => { void handleCandidateSelection("clear"); });'
                         in workspace_text,
    }
    checks.append({
        "id": "V2.6.1-03",
        "title": "界面责任：比较区头部直发采用/取消（无重复确认面板），按钮绑定当前候选身份",
        "ok": all(wiring.values()),
        "detail": wiring,
    })

    block = selection_section(workspace_text)
    guard = section_guard(block)
    probe = negative_probe()
    checks.append({
        "id": "V2.6.1-04",
        "title": "写路径唯一：采用只经仓储追加选择记录，先落盘再更新内存，失败走错误提示",
        "ok": guard["saves_selection"] and guard["memory_after_save"] and guard["error_path_kept"]
              and not guard["forbidden_tokens"] and probe["ok"],
        "detail": {**guard, "negative_probe": probe, "section_chars": len(block)},
    })

    compare_forbidden = pure_compare_guard(compare_section(workspace_text))
    rework_forbidden = pure_rework_guard(rework_section(workspace_text))
    checks.append({
        "id": "V2.6.1-05",
        "title": "不回退：比较区仍是纯投影、返工区未被采用逻辑污染（V2.5.3 / V2.5.4 判据保持）",
        "ok": not compare_forbidden and not rework_forbidden,
        "detail": {"compare_forbidden": compare_forbidden, "rework_forbidden": rework_forbidden},
    })
    return checks


STORAGE_DIGEST = """
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
  const assets = await read("assets");
  db.close();
  const encoder = new TextEncoder();
  const digest = async (text) => {
    const buffer = await crypto.subtle.digest("SHA-256", encoder.encode(text));
    return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
  };
  const rows = [];
  for (const row of documents) {
    const extra = {};
    if (row.kind === "prompt_version") {
      extra.prompt_hash = row.payload.hash;
      extra.text_chars = row.payload.compiled.text.length;
      extra.has_rework = Boolean(row.payload.compiled.rework);
    } else if (row.kind === "generation_confirm") {
      const snapshot = row.payload.fingerprint ? row.payload.fingerprint.snapshot : null;
      extra.scope = snapshot && Array.isArray(snapshot.scope_shot_ids)
        ? snapshot.scope_shot_ids : null;
    } else if (row.kind === "selection") {
      extra.action = row.payload.action;
      extra.candidate_id = row.payload.candidate_id;
      extra.candidate_version = row.payload.candidate_version;
      extra.candidate_sha256 = row.payload.candidate_sha256;
      extra.selection_id = row.payload.selection_id;
      extra.has_fingerprint = Boolean(row.payload.review_fingerprint);
      extra.payload_keys = Object.keys(row.payload).sort().join(",");
      extra.payload_chars = JSON.stringify(row.payload).length;
    }
    rows.push({
      kind: row.kind, document_id: row.document_id, version: row.version,
      payload_sha256: await digest(JSON.stringify(row.payload)), ...extra,
    });
  }
  rows.sort((left, right) => (left.kind + "|" + left.document_id + "|" + String(left.version))
    .localeCompare(right.kind + "|" + right.document_id + "|" + String(right.version)));
  return {
    rows: rows,
    assets: assets.map((item) => ({ sha256: item.sha256, role: item.role,
      byte_size: item.byte_size, has_blob: item.blob instanceof Blob }))
      .sort((left, right) => left.sha256.localeCompare(right.sha256)),
  };
}
"""


SELECTION_PROBE = """
() => {
  const entry = document.getElementById("adopt-open");
  const clearBtn = document.getElementById("adopt-clear");
  const comparePanel = document.getElementById("compare-panel");
  const active = document.activeElement;
  const rows = [...document.querySelectorAll("#attempt-list .attempt-row")].map((node) => {
    const summary = node.querySelector(".attempt-selection");
    return {
      shot_id: node.getAttribute("data-shot-id"),
      attempt_state: node.getAttribute("data-attempt-state"),
      selection_state: summary ? summary.getAttribute("data-selection-state") : null,
      selection_text: summary ? summary.textContent : null,
    };
  });
  const badges = [...document.querySelectorAll("#compare-candidates [data-adopted]")].map((node) => {
    const host = node.closest("[data-candidate-id]");
    return {
      state: node.getAttribute("data-adopted"),
      text: node.textContent,
      candidate_id: host ? host.getAttribute("data-candidate-id") : null,
    };
  });
  const selectedTab = document.querySelector(
    '#compare-candidates [role="tab"][aria-selected="true"]');
  const isHidden = (node) => Boolean(node && (node.hidden || node.offsetParent === null));
  return {
    contract: "v2.6.1",
    visible: Boolean(entry && !entry.disabled),
    panel_shot_id: entry ? (entry.dataset.shotId || null) : null,
    panel_candidate_id: entry ? (entry.dataset.candidateId || null) : null,
    title: "",
    basis: (document.getElementById("compare-basis-title") || {}).textContent || "",
    current: "",
    fingerprint: "",
    readiness: "",
    status: (document.getElementById("adopt-status") || {}).textContent || "",
    status_hidden: isHidden(document.getElementById("adopt-status")),
    error: (document.getElementById("adopt-error") || {}).textContent || "",
    error_hidden: isHidden(document.getElementById("adopt-error")),
    submit_disabled: entry ? entry.disabled : true,
    submit_text: (entry || {}).textContent || "",
    clear_disabled: clearBtn ? clearBtn.disabled : true,
    progress: (document.getElementById("adopt-progress") || {}).textContent || "",
    compare_visible: Boolean(comparePanel && !comparePanel.hidden),
    compare_status: (document.getElementById("compare-status") || {}).textContent || "",
    focus_id: active ? (active.id || null) : null,
    entry: {
      in_compare: Boolean(entry && comparePanel && comparePanel.contains(entry)),
      disabled: entry ? entry.disabled : null,
      shot_id: entry ? (entry.dataset.shotId || null) : null,
      candidate_id: entry ? (entry.dataset.candidateId || null) : null,
      candidate_sha256: entry ? (entry.dataset.candidateSha256 || null) : null,
    },
    selected_candidate_id: selectedTab ? selectedTab.getAttribute("data-candidate-id") : null,
    badges: badges,
    rows: rows,
  };
}
"""

def digest_business(digest: dict) -> list:
    return [row for row in digest["rows"] if row["kind"] in BUSINESS_KINDS]


def selection_rows(digest: dict) -> list:
    return [row for row in digest["rows"] if row["kind"] == SELECTION_KIND]


def newest_selection(digest: dict, shot_id: str):
    rows = sorted([row for row in selection_rows(digest) if row["document_id"] == shot_id],
                  key=lambda row: row["version"])
    return rows[-1] if rows else None


def progress_of(text: str):
    match = PROGRESS_PATTERN.search(text or "")
    if not match:
        return None
    return {"current": int(match.group(1)), "required": int(match.group(2)),
            "stale": int(match.group(3)), "missing": int(match.group(4))}


NON_SELECTION_KINDS = ("prompt_version", "generation_attempt", "candidate", "review_report",
                       "generation_confirm")
SELECTION_PAYLOAD_KEYS = ("action,candidate_id,candidate_sha256,candidate_version,"
                          "contract_version,created_at,review_fingerprint,schema_version,"
                          "selection_id,shot_id")


def others_untouched(before: dict, after: dict) -> bool:
    """除选择记录外的一切（含图片资产）逐字不变。"""

    left = [row for row in before["rows"] if row["kind"] in NON_SELECTION_KINDS]
    right = [row for row in after["rows"] if row["kind"] in NON_SELECTION_KINDS]
    return left == right and before["assets"] == after["assets"]


def run_workbench_checks(stamp: str, console_errors: list[str],
                         page_errors: list[str]) -> tuple[list[dict], dict]:
    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    checks: list[dict] = []
    ui: dict = {}
    holder = {"scenario": "ok"}
    captured: list[dict] = []
    port = v251.free_port()
    server = server_module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario=holder["scenario"]),
        review_provider_factory=lambda: FakeReviewProvider("ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v261-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(v251.png_bytes(1200, 1200, (36, 92, 160)))
    reference_sha = hashlib.sha256(reference.read_bytes()).hexdigest()
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

                def on_request(request) -> None:
                    if "/api/v2/images/submit" not in request.url:
                        return
                    try:
                        payload = json.loads(request.post_data or "null")
                    except ValueError:
                        payload = None
                    captured.append({"url": request.url, "payload": payload})
                page.on("request", on_request)

                def probe() -> dict:
                    return page.evaluate(SELECTION_PROBE)

                def storage() -> dict:
                    return page.evaluate(STORAGE_DIGEST)

                def attempt_probe() -> dict:
                    return page.evaluate(v251.PROBE)

                def row(shot_id: str):
                    return page.locator(f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 30_000) -> None:
                    expect(row(shot_id)).to_have_attribute("data-attempt-state", state,
                                                           timeout=timeout)

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

                def submit_once(shot_id: str) -> None:
                    click_row_button(shot_id, "生成这张图")
                    wait_state(shot_id, "submitted")
                    click_row_button(shot_id, "核对任务")
                    wait_state(shot_id, "succeeded")
                    wait_candidate_ui(shot_id)

                def compare_state() -> dict:
                    return page.evaluate(
                        """() => {
                            const panel = document.getElementById("compare-panel");
                            return {
                                visible: Boolean(panel && !panel.hidden),
                                shot: panel ? (panel.dataset.shotId || null) : null,
                                cards: panel ? panel.querySelectorAll('#compare-candidates [role="tab"]').length : 0,
                                references: panel ? panel.querySelectorAll("#compare-references li").length : 0,
                            };
                        }""")

                def open_panel(shot_id: str, card_count: int, references: int = 1) -> None:
                    state = compare_state()
                    if not (state["visible"] and state["shot"] == shot_id):
                        stage_nav.goto(page, "generate")
                        row(shot_id).locator('button[data-compare-action]').first.click()
                    stage_nav.goto(page, "review")
                    page.wait_for_function(
                        """(payload) => {
                            const panel = document.getElementById("compare-panel");
                            if (!panel || panel.hidden) return false;
                            if (panel.dataset.shotId !== payload.shot) return false;
                            const cards = panel.querySelectorAll('#compare-candidates [role="tab"]');
                            if (cards.length !== payload.cards) return false;
                            return panel.querySelectorAll("#compare-references li").length
                              === payload.references;
                        }""",
                        arg={"shot": shot_id, "cards": card_count, "references": references},
                        timeout=20_000)

                def select_candidate(candidate_id: str) -> dict:
                    page.click('#compare-candidates [role="tab"][data-candidate-id="'
                               + candidate_id + '"]')
                    page.wait_for_timeout(120)
                    return probe()

                def open_adopt() -> dict:
                    page.click("#adopt-open")
                    expect(page.locator("#adopt-panel")).to_be_visible()
                    return probe()

                def adopt_submit() -> dict:
                    page.click("#adopt-submit")
                    page.wait_for_selector("#adopt-status:not([hidden])", timeout=20_000)
                    return probe()

                def adopt_clear() -> dict:
                    page.click("#adopt-clear")
                    page.wait_for_selector("#adopt-status:not([hidden])", timeout=20_000)
                    return probe()

                def rework_once(shot_id: str, problem_id: str, direction: str) -> None:
                    page.click("#rework-open")
                    expect(page.locator("#rework-panel")).to_be_visible()
                    page.click(f'label[data-problem-id="{problem_id}"]')
                    page.fill("#rework-direction", direction)
                    page.click("#rework-preview")
                    expect(page.locator("#rework-preview-box")).to_be_visible(timeout=20_000)
                    page.click("#rework-submit")
                    expect(page.locator("#rework-panel")).to_be_hidden(timeout=40_000)
                    wait_candidate_ui(shot_id)

                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_selector("#empty-state:not([hidden])", timeout=60_000)
                page.fill("#new-project-name", "审计商品 · 人工选择")
                page.click("#create-project")
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
                shot_ids = attempt_probe()["shot_ids"]
                first_shot, second_shot = shot_ids[0], shot_ids[1]
                v251.compile_all(page, shot_ids)
                expect(page.locator("#confirm-action")).to_be_enabled()
                page.click("#confirm-action")
                stage_nav.goto(page, "generate")
                page.wait_for_function(
                     """() => {
                        const row = document.querySelector(
                            '#attempt-list .attempt-row[data-shot-id="shot_main_clean"]');
                        const btn = row && [...row.querySelectorAll("button")]
                            .find((b) => b.textContent.includes("生成这张图"));
                        return Boolean(btn && !btn.disabled);
                    }""",
                    timeout=20_000)
                submit_once(first_shot)
                submit_once(second_shot)
                open_panel(first_shot, 1, references=1)

                seeded = attempt_probe()
                seeded_storage = storage()
                chain = seeded["candidate_chains"].get(first_shot, [])
                candidate_ids = [item["payload"]["candidate_id"] for item in chain]
                candidate_versions = {item["payload"]["candidate_id"]: item["version"]
                                      for item in chain}
                candidate_shas = {item["payload"]["candidate_id"]: item["payload"]["asset_sha256"]
                                  for item in chain}
                second_candidates_json = v251.candidate_json(seeded, second_shot)
                second_docs = {second_shot} | {item["payload"]["candidate_id"]
                                               for item in seeded["candidate_chains"].get(second_shot, [])}
                initial_rows = [item for item in probe()["rows"] if item["shot_id"] == first_shot]
                initial_progress = progress_of(probe()["progress"])
                ui["seeded"] = {"shots": shot_ids, "first": first_shot, "second": second_shot,
                                "candidates": candidate_ids, "reference_sha": reference_sha}

                checks.append({
                    "id": "V2.6.1-08",
                    "title": "自动审核只提供依据：种子阶段已有候选与报告，但没有任何选择记录，行内摘要仍是「尚未采用」",
                    "ok": len(selection_rows(seeded_storage)) == 0 and initial_progress is not None
                          and initial_progress["current"] == 0
                          and initial_progress["stale"] == 0
                          and initial_progress["missing"] == initial_progress["required"]
                          and len(candidate_ids) == 2
                          and initial_rows and initial_rows[0]["selection_state"] == "none"
                          and "尚未采用" in (initial_rows[0]["selection_text"] or ""),
                    "detail": {"selection_rows": len(selection_rows(seeded_storage)),
                               "progress": initial_progress,
                               "candidates": candidate_ids,
                               "row": initial_rows[0] if initial_rows else None},
                })

                open_panel(first_shot, 2, references=1)
                opened_compare = probe()
                default_id = opened_compare["selected_candidate_id"]
                other_id = [item for item in candidate_ids if item != default_id][0]
                followed = select_candidate(other_id)
                checks.append({
                    "id": "V2.6.1-09",
                    "title": "入口：比较区把「正看着的候选」交给采用面板，换卡后入口同步换身份",
                    "ok": opened_compare["entry"]["in_compare"]
                          and opened_compare["entry"]["disabled"] is False
                          and opened_compare["entry"]["shot_id"] == first_shot
                          and opened_compare["entry"]["candidate_id"] == default_id
                          and opened_compare["entry"]["candidate_sha256"] == candidate_shas[default_id]
                          and followed["entry"]["candidate_id"] == other_id
                          and followed["entry"]["candidate_sha256"] == candidate_shas[other_id],
                    "detail": {"default": default_id, "switched": other_id,
                               "entry": followed["entry"],
                               "selected": followed["selected_candidate_id"]},
                })

                adopt_panel = open_adopt()
                checks.append({
                    "id": "V2.6.1-10",
                    "title": "采用面板：独立面板绑定候选身份与合同版本，显示将绑定的当前审核报告与这套图的采用要求",
                    "ok": adopt_panel["visible"]
                          and adopt_panel["contract"] == SELECTION_CONTRACT_VERSION
                          and adopt_panel["panel_shot_id"] == first_shot
                          and adopt_panel["panel_candidate_id"] == other_id
                          and "采用候选（人工选择）" in adopt_panel["title"]
                          and "当前尚未采用" in adopt_panel["basis"]
                          and ("候选 v" + str(candidate_versions[other_id])) in adopt_panel["basis"]
                          and "将绑定当前审核报告" in adopt_panel["fingerprint"]
                          and "这张图是" in adopt_panel["readiness"]
                          and adopt_panel["submit_disabled"] is False
                          and adopt_panel["submit_text"] == "采用这条候选"
                          and adopt_panel["clear_disabled"] is True
                          and adopt_panel["focus_id"] == "adopt-submit",
                    "detail": {"contract": adopt_panel["contract"],
                               "basis": adopt_panel["basis"],
                               "fingerprint": adopt_panel["fingerprint"],
                               "readiness": adopt_panel["readiness"],
                               "focus": adopt_panel["focus_id"]},
                })

                page.click("#adopt-cancel")
                closed = probe()
                closed_storage = storage()
                checks.append({
                    "id": "V2.6.1-11",
                    "title": "打开与关闭采用面板不写任何记录，关闭后焦点回到原候选卡",
                    "ok": closed["visible"] is False
                          and closed["focus_id"] == "compare-tab-" + other_id
                          and closed_storage == seeded_storage,
                    "detail": {"focus_after_close": closed["focus_id"],
                               "expected_focus": "compare-tab-" + other_id,
                               "records_unchanged": closed_storage == seeded_storage},
                })

                open_adopt()
                adopted = adopt_submit()
                adopted_storage = storage()
                first_selection = newest_selection(adopted_storage, first_shot)
                adopted_rows = [item for item in adopted["rows"] if item["shot_id"] == first_shot]
                adopted_badges = {item["candidate_id"]: item for item in adopted["badges"]}
                adopted_progress = progress_of(adopted["progress"])
                checks.append({
                    "id": "V2.6.1-12",
                    "title": "采用：追加一条选择记录（绑定候选身份/版本/审核指纹），行摘要、候选徽标与整套进度同步更新",
                    "ok": first_selection is not None and first_selection["version"] == 1
                          and first_selection["action"] == "select"
                          and first_selection["candidate_id"] == other_id
                          and first_selection["candidate_version"] == candidate_versions[other_id]
                          and first_selection["candidate_sha256"] == candidate_shas[other_id]
                          and first_selection["has_fingerprint"] is True
                          and first_selection["selection_id"]
                          and adopted_rows and adopted_rows[0]["selection_state"] == "current"
                          and "已采用" in (adopted_rows[0]["selection_text"] or "")
                          and adopted_badges.get(other_id, {}).get("state") == "current"
                          and adopted_badges.get(other_id, {}).get("text") == "已采用"
                          and adopted_progress is not None
                          and adopted_progress["current"] == initial_progress["current"] + 1
                          and adopted_progress["stale"] == 0
                          and "已采用候选 v" in adopted["status"]
                          and adopted["status_hidden"] is False,
                    "detail": {"selection": first_selection, "progress": adopted_progress,
                               "badges": adopted["badges"], "status": adopted["status"]},
                })

                checks.append({
                    "id": "V2.6.1-13",
                    "title": "采用只写选择：Prompt/Attempt/Candidate/Review/确认与图片资产逐字不变，无关图零变化",
                    "ok": others_untouched(closed_storage, adopted_storage)
                          and v254.digest_untouched(closed_storage, adopted_storage, second_docs)
                          and len(adopted_storage["assets"]) == len(closed_storage["assets"]),
                    "detail": {"others_untouched": others_untouched(closed_storage, adopted_storage),
                               "second_shot_untouched": v254.digest_untouched(
                                   closed_storage, adopted_storage, second_docs),
                               "assets": len(adopted_storage["assets"])},
                })
                switched = select_candidate(default_id)
                open_adopt()
                reselected = adopt_submit()
                reselected_storage = storage()
                second_selection = newest_selection(reselected_storage, first_shot)
                reselected_badges = {item["candidate_id"]: item for item in reselected["badges"]}
                reselected_progress = progress_of(reselected["progress"])
                kept_prefix = v254.digest_kept_prefix(adopted_storage, reselected_storage)
                checks.append({
                    "id": "V2.6.1-14",
                    "title": "改选：追加新版本而不是覆盖，旧记录逐字保留，徽标与摘要随之移动",
                    "ok": switched["entry"]["candidate_id"] == default_id
                          and second_selection is not None and second_selection["version"] == 2
                          and second_selection["candidate_id"] == default_id
                          and kept_prefix
                          and reselected_badges.get(default_id, {}).get("state") == "current"
                          and "已采用" in reselected["status"]
                          and reselected_progress is not None
                          and reselected_progress["current"] == 1
                          and reselected_progress["stale"] == 0,
                    "detail": {"version": second_selection["version"] if second_selection else None,
                               "kept_prefix": kept_prefix,
                               "badges": reselected["badges"],
                               "progress": reselected_progress},
                })

                rework_once(first_shot, "scene", "把背景换成纯白，商品保持不变，不要改标识。")
                after_rework = attempt_probe()
                chain_after = after_rework["candidate_chains"].get(first_shot, [])
                newest_candidate_id = chain_after[-1]["payload"]["candidate_id"]
                stale_rows = [item for item in probe()["rows"] if item["shot_id"] == first_shot]
                stale_progress = progress_of(probe()["progress"])
                open_panel(first_shot, 3, references=1)
                stale_badges = {item["candidate_id"]: item for item in probe()["badges"]}
                stale_selection = newest_selection(storage(), first_shot)
                checks.append({
                    "id": "V2.6.1-15",
                    "title": "返工后失效：新的成功候选只把旧选择标成过期，不覆盖、不自动改选、不自动取消",
                    "ok": newest_candidate_id not in candidate_ids
                          and stale_rows and stale_rows[0]["selection_state"] == "stale"
                          and "过期" in (stale_rows[0]["selection_text"] or "")
                          and stale_progress is not None and stale_progress["stale"] == 1
                          and stale_progress["current"] == 0
                          and stale_badges.get(default_id, {}).get("state") == "stale"
                          and stale_badges.get(default_id, {}).get("text") == "已采用（已过期）"
                          and stale_selection is not None
                          and stale_selection["candidate_id"] == default_id
                          and stale_selection["version"] == 2,
                    "detail": {"newest_candidate": newest_candidate_id,
                               "row": stale_rows[0] if stale_rows else None,
                               "progress": stale_progress, "badges": stale_badges,
                               "selection_version": stale_selection["version"] if stale_selection else None},
                })

                select_candidate(other_id)
                open_adopt()
                back_to_old = adopt_submit()
                back_storage = storage()
                third_selection = newest_selection(back_storage, first_shot)
                back_progress = progress_of(back_to_old["progress"])
                back_badges = {item["candidate_id"]: item for item in back_to_old["badges"]}
                checks.append({
                    "id": "V2.6.1-16",
                    "title": "返工后重选旧候选：过期选择重新变 current，徽标回到旧候选，历史全部保留",
                    "ok": third_selection is not None and third_selection["version"] == 3
                          and third_selection["candidate_id"] == other_id
                          and v254.digest_kept_prefix(reselected_storage, back_storage)
                          and back_progress is not None and back_progress["stale"] == 0
                          and back_progress["current"] == 1
                          and back_badges.get(other_id, {}).get("state") == "current",
                    "detail": {"selection": third_selection, "progress": back_progress,
                               "badges": back_to_old["badges"]},
                })

                select_candidate(newest_candidate_id)
                open_adopt()
                failed_rows_before = len(selection_rows(back_storage))
                page.evaluate(
                    """() => {
                        if (!window.__v261OriginalAdd) {
                            window.__v261OriginalAdd = IDBObjectStore.prototype.add;
                        }
                        IDBObjectStore.prototype.add = function (value, key) {
                            if (window.__v261FailSelectionWrite && value
                                && value.kind === "selection") {
                                throw new DOMException("注入的写入失败", "UnknownError");
                            }
                            return window.__v261OriginalAdd.call(this, value, key);
                        };
                        window.__v261FailSelectionWrite = true;
                    }""")
                page.click("#adopt-submit")
                page.wait_for_selector("#adopt-error:not([hidden])", timeout=20_000)
                failed = probe()
                failed_storage = storage()
                failed_progress = progress_of(failed["progress"])
                failed_selection = newest_selection(failed_storage, first_shot)
                page.evaluate("() => { window.__v261FailSelectionWrite = false; }")
                recovered = adopt_submit()
                recovered_storage = storage()
                recovered_selection = newest_selection(recovered_storage, first_shot)
                checks.append({
                    "id": "V2.6.1-17",
                    "title": "写入失败不改旧选择：明确报错、不新增记录、旧选择与进度不变；恢复后重试能追加",
                    "ok": "写入失败" in failed["error"] and failed["status_hidden"] is True
                          and len(selection_rows(failed_storage)) == failed_rows_before
                          and failed_selection is not None
                          and failed_selection["candidate_id"] == other_id
                          and failed_selection["version"] == 3
                          and failed_progress == back_progress
                          and recovered_selection is not None
                          and recovered_selection["version"] == 4
                          and recovered_selection["candidate_id"] == newest_candidate_id
                          and "已采用候选 v" in recovered["status"],
                    "detail": {"error": failed["error"], "version_after_failure":
                               failed_selection["version"] if failed_selection else None,
                               "recovered_version": recovered_selection["version"]
                               if recovered_selection else None},
                })

                select_candidate(default_id)
                open_adopt()
                page.evaluate(
                    """() => {
                        const button = document.getElementById("adopt-submit");
                        button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
                        button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
                    }""")
                page.wait_for_selector("#adopt-status:not([hidden])", timeout=20_000)
                double_storage = storage()
                double_selection = newest_selection(double_storage, first_shot)
                checks.append({
                    "id": "V2.6.1-18",
                    "title": "双击防护：连点「采用这条候选」只追加一条记录、一次版本推进",
                    "ok": len(selection_rows(double_storage)) == failed_rows_before + 2
                          and double_selection is not None and double_selection["version"] == 5
                          and double_selection["candidate_id"] == default_id,
                    "detail": {"selection_rows": len(selection_rows(double_storage)),
                               "version": double_selection["version"] if double_selection else None},
                })

                cleared = adopt_clear()
                cleared_storage = storage()
                clear_selection = newest_selection(cleared_storage, first_shot)
                cleared_rows = [item for item in cleared["rows"] if item["shot_id"] == first_shot]
                cleared_progress = progress_of(cleared["progress"])
                history_kept = v254.digest_kept_prefix(double_storage, cleared_storage)
                checks.append({
                    "id": "V2.6.1-19",
                    "title": "取消采用：追加一条不带候选身份的 clear 记录，摘要与进度回到缺选，历史 select 记录保留",
                    "ok": clear_selection is not None and clear_selection["version"] == 6
                          and clear_selection["action"] == "clear"
                          and clear_selection["candidate_id"] is None
                          and clear_selection["candidate_sha256"] is None
                          and clear_selection["candidate_version"] is None
                          and cleared_rows and cleared_rows[0]["selection_state"] == "cleared"
                          and "已取消采用" in (cleared_rows[0]["selection_text"] or "")
                          and cleared_progress is not None
                          and cleared_progress["current"] == 0
                          and cleared_progress["stale"] == 0
                          and cleared_progress["missing"] == initial_progress["missing"]
                          and history_kept
                          and "已取消采用" in cleared["status"],
                    "detail": {"selection": clear_selection, "progress": cleared_progress,
                               "history_kept": history_kept,
                               "row": cleared_rows[0] if cleared_rows else None},
                })

                before_reload = probe()
                before_reload_storage = storage()
                page.reload(wait_until="networkidle")
                expect(page.locator("#project-view")).to_be_visible()
                reloaded = probe()
                reloaded_storage = storage()
                open_panel(first_shot, 3, references=1)
                reloaded_open = probe()
                reloaded_rows = [item for item in reloaded["rows"] if item["shot_id"] == first_shot]
                checks.append({
                    "id": "V2.6.1-20",
                    "title": "刷新恢复：选择状态、行摘要、整套进度与候选徽标从 IndexedDB 恢复，刷新不写任何记录",
                    "ok": reloaded_storage == before_reload_storage
                          and reloaded_rows and reloaded_rows[0]["selection_state"] == "cleared"
                          and reloaded["progress"] == before_reload["progress"]
                          and reloaded_open["entry"]["disabled"] is False
                          and v251.candidate_json(attempt_probe(), second_shot) == second_candidates_json,
                    "detail": {"records_same": reloaded_storage == before_reload_storage,
                               "row": reloaded_rows[0] if reloaded_rows else None,
                               "progress": progress_of(reloaded["progress"])},
                })

                open_adopt()
                if probe()["submit_disabled"] is False:
                    adopt_submit()
                screenshot_rel = f"evals/product-v2/evidence/v2.6.1-selection-{stamp}.png"
                detail_rel = f"evals/product-v2/evidence/v2.6.1-selection-{stamp}-detail.png"
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                page.locator("#adopt-panel").screenshot(path=str(ROOT / detail_rel))
                screenshot_paths = [ROOT / screenshot_rel, ROOT / detail_rel]
                final_storage = storage()
                final_payloads = [{"keys": item["payload_keys"], "chars": item["payload_chars"]}
                                  for item in selection_rows(final_storage)]
                checks.append({
                    "id": "V2.6.1-21",
                    "title": "视觉证据：整页与采用面板特写落盘；选择记录只引用内容寻址身份，不含图片字节",
                    "ok": all(path.is_file() and path.stat().st_size > 0 for path in screenshot_paths)
                          and bool(final_payloads)
                          and all(item["keys"] == SELECTION_PAYLOAD_KEYS for item in final_payloads)
                          and all(item["chars"] < 2000 for item in final_payloads),
                    "detail": {"screenshots": {path.relative_to(ROOT).as_posix(): path.stat().st_size
                                               for path in screenshot_paths},
                               "selection_payloads": final_payloads,
                               "selection_rows": len(selection_rows(final_storage)),
                               "adopt_panel": probe()["title"]},
                })
                ui["screenshot"] = screenshot_rel
                ui["screenshot_detail"] = detail_rel
                ui["selection_rows"] = len(selection_rows(final_storage))
                ui["progress"] = progress_of(probe()["progress"])
                ui["checks"] = [item["id"] for item in checks]
            finally:
                context.close()
    finally:
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
            selection_suite = v251.read_suite(
                browser, static_url + "/harness/selection-contract.html",
                "__V2_SELECTION_RESULTS__", console_errors, page_errors)
            rework_suite = v251.read_suite(
                browser, static_url + "/harness/rework-contract.html",
                "__V2_REWORK_RESULTS__", console_errors, page_errors)
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
        "id": "V2.6.1-06",
        "title": "SL-01–SL-18 选择契约套件：跨图候选、缺身份、非法 sha、过高 schema 版本、过期投影全部守住",
        "ok": selection_suite.get("status") == "passed"
              and sorted(item["id"] for item in selection_suite.get("cases", []))
              == EXPECTED_SELECTION_CASES,
        "detail": {"status": selection_suite.get("status"),
                   "failed": selection_suite.get("failed_ids"),
                   "cases": len(selection_suite.get("cases", []))},
    })
    checks.append({
        "id": "V2.6.1-07",
        "title": "既有套件回归：RW-01–RW-15、CP-01–CP-15、R01–R13 与复核 provider 在采用落地后仍全过",
        "ok": rework_suite.get("status") == "passed" and compare_suite.get("status") == "passed"
              and review_suite.get("status") == "passed"
              and provider_suite.get("status") == "passed"
              and sorted(item["id"] for item in rework_suite.get("cases", []))
              == EXPECTED_REWORK_CASES,
        "detail": {"rework": rework_suite.get("status"), "compare": compare_suite.get("status"),
                   "review": review_suite.get("status"), "provider": provider_suite.get("status")},
    })
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.6.1 人工选择与失效判断验证")
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
        "id": "V2.6.1-22",
        "title": "正式入口 --check 全过（采用闭环没有破坏既有自检）",
        "ok": entry["rc"] == 0 and any("PASS" in line for line in entry["tail"]),
        "detail": {"rc": entry["rc"], "tail": entry["tail"][-3:]},
    })
    expected_console = [item for item in console_errors if "status of 504" in item]
    unexpected_console = [item for item in console_errors if item not in expected_console]
    checks.append({
        "id": "V2.6.1-23",
        "title": "零意外 console error / page error（唯一允许项：Unknown 路径的 504 资源日志）",
        "ok": not unexpected_console and not page_errors,
        "detail": {"unexpected_console": unexpected_console[:3],
                   "expected_unknown_path_504": expected_console[:3],
                   "page_errors": page_errors[:3]},
    })

    passed = sum(1 for item in checks if item["ok"])
    failed = [item["id"] for item in checks if not item["ok"]]
    observed_at = datetime.now().isoformat(timespec="seconds")
    label = args.label
    txt_path = EVIDENCE_DIR / f"v2.6.1-selection-{stamp}{label}.txt"
    json_path = EVIDENCE_DIR / f"v2.6.1-selection-{stamp}{label}.json"

    lines = [
        "V2.6.1 人工 Selection 与失效判断验证（选择契约套件 + 真实工作台走查 + 视觉证据）",
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
        f"contract: {SELECTION_CONTRACT_VERSION}（人工选择）· v2.5.4（返工）· v2.5.3（比较）· v2.5.2（复核）",
        "model_calls: 0 · external_network_calls: 0（fake providers + 本地静态服务器）",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "边界：本套件 0 次真实模型调用，采用过程不调用任何模型；写入失败用例是在浏览器侧",
        "对 IDBObjectStore.add 注入一次失败，验证「写失败不改旧 Selection」的错误路径，不代表",
        "真实磁盘写满或事务冲突下的表现。整套一致性报告属 V2.5.5、导出阻断与交付 zip 属 V2.6.2，",
        "本批不宣称已经具备；采用也不代表候选已通过导出硬门。",
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
        "suite_id": "v2.6.1-selection",
        "status": "passed" if passed == len(checks) else "failed",
        "observed_at": observed_at,
        "contract": SELECTION_CONTRACT_VERSION,
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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
