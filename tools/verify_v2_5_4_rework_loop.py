#!/usr/bin/env python
"""V2.5.4 问题分类、改进方向与单图返工闭环验证：静态守卫 + 返工契约套件 + 真实工作台走查 + 视觉证据。

正向：入口交付候选身份、预览与真实请求逐字一致、单图确认隔离、重做只给目标图新增
      Prompt/Attempt/Candidate/Review、旧候选保留、刷新后来源链仍在。
反向：空理由/未知分类/跨图候选/hash 不符必须被领域拒绝；比较区不得写业务记录；
      双击只产生一条 Attempt；失败与 Unknown 不丢旧数据、不自动重提。

用法：
    uv run --locked python tools/verify_v2_5_4_rework_loop.py --label final
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
REWORK_CONTRACT_VERSION = "v2.5.4"
REWORK_PROBLEM_IDS = ["product_fidelity", "part_error", "scene", "composition",
                      "selling_point", "text", "style", "platform_risk", "other"]
EXPECTED_REWORK_CASES = [f"RW-{index:02d}" for index in range(1, 16)]
BUSINESS_KINDS = {"prompt_version", "generation_attempt", "candidate", "review_report",
                  "generation_confirm"}


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


def rework_section(text: str) -> str:
    """workspace.js 里单图返工那一整块（独立分区，不属于比较区）。"""

    start = text.index("单图返工闭环（V2.5.4）")
    end = text.index("整套批次执行", start)
    return text[start:end]


def check_static_guards() -> list[dict]:
    checks: list[dict] = []
    syntax_targets = [
        PRODUCT_DIR / "domain" / "rework.js",
        PRODUCT_DIR / "domain" / "prompt.js",
        PRODUCT_DIR / "domain" / "confirm.js",
        PRODUCT_DIR / "workspace.js",
        HARNESS_DIR / "rework-contract.js",
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
        "id": "V2.5.4-01",
        "title": "语法门：rework / prompt / confirm / workspace / 返工契约套件与本工具全部可解析",
        "ok": all(item["rc"] == 0 for item in results),
        "detail": {"files": results},
    })

    rework_text = product_text("domain/rework.js")
    workspace_text = product_text("workspace.js")
    html = (PRODUCT_DIR / "index.html").read_text(encoding="utf-8")
    # 只挑不会与普通词撞名的 id；普通词（text/other 等）在 JS 里到处都是，不能当判据。
    distinctive = ["product_fidelity", "part_error", "composition", "selling_point", "platform_risk"]
    duplicated = [problem for problem in distinctive
                  if f'"{problem}"' in workspace_text or f"'{problem}'" in workspace_text]
    local_definition = ("REWORK_PROBLEM_IDS =" in workspace_text
                        or "const REWORK_PROBLEMS" in workspace_text
                        or "商品失真" in workspace_text)
    checks.append({
        "id": "V2.5.4-02",
        "title": "单一权威：九类问题与返工合同版本只在 domain/rework.js 定义，工作台只引用",
        "ok": 'REWORK_PROBLEM_IDS' in rework_text and 'REWORK_CONTRACT_VERSION = "v2.5.4"' in rework_text
              and "REWORK_PROBLEMS," in workspace_text and "REWORK_CONTRACT_VERSION," in workspace_text
              and not duplicated and not local_definition,
        "detail": {"duplicated_in_workspace": duplicated,
                   "local_definition": local_definition,
                   "imports_problems": "REWORK_PROBLEMS," in workspace_text},
    })

    i_compare = html.index('id="compare-panel"')
    i_rework = html.index('id="rework-panel"')
    compare_html = html[i_compare:i_rework]
    sibling = compare_html.count("<section") == compare_html.count("</section>")
    wiring = {
        "entry_in_compare": 'id="rework-open"' in compare_html,
        "panel_sibling": sibling and i_rework > i_compare,
        "fieldset": "<fieldset id=\"rework-problems\"" in html,
        "preview_box": 'id="rework-preview-box"' in html,
        "buttons": all(f'id="{name}"' in html for name in
                       ("rework-preview", "rework-edit", "rework-submit", "rework-cancel")),
        "entry_hands_sha": "dataset.candidateSha256 = row.asset_sha256" in workspace_text,
    }
    checks.append({
        "id": "V2.5.4-03",
        "title": "界面责任：比较区只放入口，返工表单是相邻的独立 #rework-panel（fieldset + 预览框）",
        "ok": all(wiring.values()),
        "detail": wiring,
    })

    prompt_text = product_text("domain/prompt.js")
    section_text = rework_section(workspace_text)
    chain = {
        "prompt_section": '"rework_directive"' in prompt_text,
        "record_keeps_rework": "compiled.rework" in prompt_text,
        "compile_pure": "compileShotPrompt" in section_text,
        "save_then_confirm": "savePromptPayload" in section_text and "buildScopedSheet" in section_text,
        "reuses_attempt_channel": "handleSubmitAttempt" in section_text,
        "no_direct_gateway": "postImageJson" not in section_text and "fetch(" not in section_text,
        "scoped_confirm_prefix": 'REWORK_CONFIRM_PREFIX = "rework:"' in workspace_text,
    }
    checks.append({
        "id": "V2.5.4-04",
        "title": "追溯链唯一：返工要求进同一份 PromptVersion，确认用 rework:<shot>，复用既有提交通道",
        "ok": all(chain.values()),
        "detail": chain,
    })

    block = compare_section(workspace_text)
    forbidden = [token for token in ("documents.save", "assets.put", "REVIEW_KIND", "CANDIDATE_KIND",
                                     "selection", "SELECTION", "openReworkPanel")
                 if token in block]
    checks.append({
        "id": "V2.5.4-05",
        "title": "不回退：比较区仍是纯投影（V2.5.3 判据原样保持，返工逻辑不在其中）",
        "ok": not forbidden,
        "detail": {"forbidden_tokens": forbidden, "section_chars": len(block)},
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


REWORK_PROBE = """
() => {
  const panel = document.getElementById("rework-panel");
  const entry = document.getElementById("rework-open");
  const previewBox = document.getElementById("rework-preview-box");
  const comparePanel = document.getElementById("compare-panel");
  const active = document.activeElement;
  return {
    contract: panel.dataset.reworkContract || null,
    visible: !panel.hidden,
    shot_id: panel.dataset.shotId || null,
    candidate_id: panel.dataset.candidateId || null,
    basis: (document.getElementById("rework-basis") || {}).textContent || "",
    summary: (document.getElementById("rework-summary") || {}).textContent || "",
    status: (document.getElementById("rework-status") || {}).textContent || "",
    error: (document.getElementById("rework-error") || {}).textContent || "",
    error_hidden: (document.getElementById("rework-error") || {}).hidden,
    compare_status: (document.getElementById("compare-status") || {}).textContent || "",
    preview_visible: !previewBox.hidden,
    preview_meta: (document.getElementById("rework-preview-meta") || {}).textContent || "",
    preview_text: (document.getElementById("rework-preview-text") || {}).textContent || "",
    preview_disabled: document.getElementById("rework-preview").disabled,
    edit_disabled: document.getElementById("rework-edit").disabled,
    submit_disabled: document.getElementById("rework-submit").disabled,
    problems: [...panel.querySelectorAll("input[type=checkbox]")].map((node) =>
      ({ id: node.id, value: node.value, checked: node.checked })),
    direction: (document.getElementById("rework-direction") || {}).value || "",
    legend: (panel.querySelector("legend") || {}).textContent || "",
    direction_label: (document.querySelector('label[for="rework-direction"]') || {}).textContent || "",
    focus_id: active ? (active.id || null) : null,
    focus_is_checkbox: Boolean(active && active.type === "checkbox"),
    entry: {
      in_compare: Boolean(entry && comparePanel && comparePanel.contains(entry)),
      disabled: entry ? entry.disabled : null,
      shot_id: entry ? (entry.dataset.shotId || null) : null,
      candidate_id: entry ? (entry.dataset.candidateId || null) : null,
      candidate_sha256: entry ? (entry.dataset.candidateSha256 || null) : null,
    },
  };
}
"""


def digest_table(digest: dict) -> dict:
    return {(row["kind"], row["document_id"], row["version"]): row
            for row in digest["rows"]}


def digest_newest(digest: dict, kind: str, document_id: str):
    rows = sorted([row for row in digest["rows"]
                   if row["kind"] == kind and row["document_id"] == document_id],
                  key=lambda row: row["version"])
    return rows[-1] if rows else None


def digest_versions(digest: dict, kind: str, document_id: str) -> int:
    rows = [row for row in digest["rows"]
            if row["kind"] == kind and row["document_id"] == document_id]
    return len(rows)


def digest_untouched(before: dict, after: dict, document_ids: set[str]) -> bool:
    """这些 document_id 的所有行（含 payload 摘要）在前后完全一致。"""

    left = [row for row in before["rows"] if row["document_id"] in document_ids]
    right = [row for row in after["rows"] if row["document_id"] in document_ids]
    return left == right


def digest_kept_prefix(before: dict, after: dict) -> bool:
    """before 的每一行都在 after 里原样存在（旧版本只增不改）。"""

    table = digest_table(after)
    return all(table.get(key) == row for key, row in digest_table(before).items())


def digest_business(digest: dict) -> list:
    return [row for row in digest["rows"] if row["kind"] in BUSINESS_KINDS]


def action_ids(chain: list) -> list:
    """一次 Attempt = 一个 action_id；状态推进只是同一 action 的新版本。"""

    seen: list[str] = []
    for item in chain:
        action = item["payload"].get("action_id")
        if action and action not in seen:
            seen.append(action)
    return seen


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
    static_server, static_url = v251.start_static_server()
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v254-"))
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
                    return page.evaluate(v251.PROBE)

                def rework_probe() -> dict:
                    return page.evaluate(REWORK_PROBE)

                def storage() -> dict:
                    return page.evaluate(STORAGE_DIGEST)

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

                def submit_once(shot_id: str) -> None:
                    click_row_button(shot_id, "生成这张图")
                    wait_state(shot_id, "submitted")
                    click_row_button(shot_id, "核对任务")
                    wait_state(shot_id, "succeeded")
                    wait_candidate_ui(shot_id)

                def open_panel(shot_id: str, card_count: int, references: int = 1) -> None:
                    stage_nav.goto(page, "generate")
                    row(shot_id).locator('button[data-compare-action]').first.click()
                    stage_nav.goto(page, "review")
                    expect(page.locator("#compare-panel")).to_be_visible()
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

                def set_rework_inputs(problem_ids: list[str], direction: str) -> None:
                    page.evaluate(
                        """(payload) => {
                            const panel = document.getElementById("rework-panel");
                            for (const node of panel.querySelectorAll("input[type=checkbox]")) {
                                const want = payload.problems.includes(node.value);
                                if (node.checked !== want) {
                                    node.checked = want;
                                    node.dispatchEvent(new Event("change", { bubbles: true }));
                                }
                            }
                            const area = document.getElementById("rework-direction");
                            if (area.value !== payload.direction) {
                                area.value = payload.direction;
                                area.dispatchEvent(new Event("input", { bubbles: true }));
                            }
                        }""", {"problems": problem_ids, "direction": direction})

                def open_rework() -> dict:
                    page.click("#rework-open")
                    expect(page.locator("#rework-panel")).to_be_visible()
                    return rework_probe()

                def preview_rework(problem_ids: list[str], direction: str) -> dict:
                    open_rework()
                    set_rework_inputs(problem_ids, direction)
                    page.click("#rework-preview")
                    expect(page.locator("#rework-preview-box")).to_be_visible(timeout=20_000)
                    return rework_probe()

                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · 单图返工")
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
                shot_ids = probe()["shot_ids"]
                first_shot, second_shot = shot_ids[0], shot_ids[1]
                v251.compile_all(page, shot_ids)
                expect(page.locator("#confirm-action")).to_be_enabled()
                page.click("#confirm-action")
                expect(page.locator("#confirm-record")).to_contain_text("已确认 v")
                submit_once(first_shot)
                submit_once(second_shot)

                seeded = probe()
                seeded_storage = storage()
                candidates_first = seeded["candidate_chains"].get(first_shot, [])
                second_candidates_json = v251.candidate_json(seeded, second_shot)
                second_attempts_json = json.dumps(
                    seeded["attempt_chains"].get(second_shot, []), sort_keys=True, default=str)
                expected_candidate_id = candidates_first[0]["payload"]["candidate_id"]
                expected_candidate_sha = candidates_first[0]["payload"]["asset_sha256"]
                first_prompt_versions = digest_versions(seeded_storage, "prompt_version", first_shot)
                second_prompt_versions = digest_versions(seeded_storage, "prompt_version", second_shot)
                ui["seeded"] = {"shots": shot_ids, "first": first_shot, "second": second_shot,
                                "candidate_sha": expected_candidate_sha,
                                "prompt_versions_first": first_prompt_versions}

                open_panel(first_shot, 1, references=1)
                entry = rework_probe()
                checks.append({
                    "id": "V2.5.4-08",
                    "title": "入口：比较区把当前候选（candidate_id + sha256）交给相邻的独立返工区",
                    "ok": entry["entry"]["in_compare"] and entry["entry"]["disabled"] is False
                          and entry["entry"]["shot_id"] == first_shot
                          and entry["entry"]["candidate_id"] == expected_candidate_id
                          and entry["entry"]["candidate_sha256"] == expected_candidate_sha,
                    "detail": entry["entry"],
                })

                opened = open_rework()
                checks.append({
                    "id": "V2.5.4-09",
                    "title": "返工表单：独立面板、九类问题 fieldset、显式 label、焦点从入口进入第一个问题",
                    "ok": opened["visible"] and opened["contract"] == REWORK_CONTRACT_VERSION
                          and opened["shot_id"] == first_shot
                          and opened["candidate_id"] == expected_candidate_id
                          and opened["candidate_id"] == entry["entry"]["candidate_id"]
                          and len(opened["problems"]) == 9
                          and [item["value"] for item in opened["problems"]] == REWORK_PROBLEM_IDS
                          and "问题分类" in opened["legend"] and "改进方向" in opened["direction_label"]
                          and opened["focus_is_checkbox"],
                    "detail": {"contract": opened["contract"], "problems": len(opened["problems"]),
                               "legend": opened["legend"], "focus": opened["focus_id"]},
                })

                page.click('label[data-problem-id="product_fidelity"]')
                page.fill("#rework-direction", "先只把背景换成纯白，商品本身的颜色、材质和标识不要动。")
                toggled = rework_probe()
                page.click("#rework-cancel")
                cancelled = rework_probe()
                storage_after_cancel = storage()
                tab_focus = "compare-tab-" + expected_candidate_id
                checks.append({
                    "id": "V2.5.4-10",
                    "title": "比较区保持只读：勾选、填写、取消全程业务记录逐字不变，焦点回到原候选",
                    "ok": any(item["value"] == "product_fidelity" and item["checked"]
                              for item in toggled["problems"])
                          and toggled["preview_disabled"] is False
                          and cancelled["visible"] is False
                          and cancelled["focus_id"] == tab_focus
                          and storage_after_cancel == seeded_storage,
                    "detail": {"checked": [item["value"] for item in toggled["problems"]
                                            if item["checked"]],
                               "focus_after_cancel": cancelled["focus_id"],
                               "expected_focus": tab_focus,
                               "records_unchanged": storage_after_cancel == seeded_storage},
                })

                direction_text = "先只把背景换成纯白，商品本身的颜色、材质和标识不要动。"
                previewed = preview_rework(["product_fidelity"], direction_text)
                storage_after_preview = storage()
                page.fill("#rework-direction", direction_text + "另外把画面留白加大。")
                dirty = rework_probe()
                restored = preview_rework(["product_fidelity"], direction_text)
                checks.append({
                    "id": "V2.5.4-11",
                    "title": "预览：显示将发送的全文（参考图 1 张）且不写任何记录；改动输入后必须重新预览",
                    "ok": previewed["preview_visible"]
                          and "本次返工要求" in previewed["preview_text"]
                          and "纯白" in previewed["preview_text"]
                          and "参考图 1 张" in previewed["preview_meta"]
                          and previewed["submit_disabled"] is False
                          and previewed["edit_disabled"] is False
                          and storage_after_preview == seeded_storage
                          and dirty["preview_visible"] is False and dirty["submit_disabled"] is True
                          and dirty["edit_disabled"] is True
                          and restored["submit_disabled"] is False
                          and direction_text in restored["preview_text"],
                    "detail": {"preview_chars": len(previewed["preview_text"]),
                               "meta": previewed["preview_meta"],
                               "dirty": {"preview": dirty["preview_visible"],
                                         "submit_disabled": dirty["submit_disabled"]},
                               "records_unchanged": storage_after_preview == seeded_storage},
                })

                preview_text = restored["preview_text"]
                attempts_before = seeded["attempt_chains"].get(first_shot, [])
                digest_before_submit = storage()
                captured.clear()
                page.evaluate(
                    """() => {
                        const button = document.getElementById("rework-submit");
                        button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
                        button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
                    }""")
                expect(page.locator("#rework-panel")).to_be_hidden(timeout=40_000)
                succeeded = probe()
                digest_after_submit = storage()
                attempts_after = succeeded["attempt_chains"].get(first_shot, [])
                new_attempts = attempts_after[len(attempts_before):]
                new_attempt = new_attempts[-1]["payload"] if new_attempts else None
                new_action_id = new_attempt["action_id"] if new_attempt else None
                submit_requests = [item for item in captured if item["payload"]
                                   and item["payload"].get("action_id") == new_action_id]
                latest_prompt = digest_newest(digest_after_submit, "prompt_version", first_shot)
                rework_confirm = digest_newest(digest_after_submit, "generation_confirm",
                                               "rework:" + first_shot)
                suite_confirm_before = digest_newest(digest_before_submit, "generation_confirm",
                                                     "generation")
                suite_confirm_after = digest_newest(digest_after_submit, "generation_confirm",
                                                    "generation")
                new_candidates = succeeded["candidate_chains"].get(first_shot, [])
                new_candidate = new_candidates[-1]["payload"] if new_candidates else None
                new_reviews = [item for item in succeeded["review_reports"]
                               if item["document_id"] == (new_candidate or {}).get("candidate_id")]
                second_candidate_ids = {item["payload"]["candidate_id"]
                                        for item in seeded["candidate_chains"].get(second_shot, [])}
                second_docs = {second_shot} | second_candidate_ids

                checks.append({
                    "id": "V2.5.4-12",
                    "title": "确认隔离：返工只写 scope=[目标图] 的单图确认，整套确认与无关图逐字不变",
                    "ok": rework_confirm is not None and rework_confirm["scope"] == [first_shot]
                          and suite_confirm_before is not None
                          and suite_confirm_after == suite_confirm_before
                          and digest_untouched(digest_before_submit, digest_after_submit, second_docs),
                    "detail": {"rework_confirm_scope": rework_confirm["scope"] if rework_confirm else None,
                               "suite_confirm_same": suite_confirm_after == suite_confirm_before,
                               "second_untouched": digest_untouched(
                                   digest_before_submit, digest_after_submit, second_docs)},
                })

                checks.append({
                    "id": "V2.5.4-13",
                    "title": "成功链：入口预览的全文 == 真实发送的 prompt == 新 Prompt 版本；只给目标图新增 Attempt/Candidate/Review",
                    "ok": new_attempt is not None and new_attempt["state"] == "succeeded"
                          and len(new_candidates) == len(candidates_first) + 1
                          and new_candidate is not None and len(new_reviews) >= 1
                          and len(submit_requests) == 1
                          and submit_requests[0]["payload"]["prompt"] == preview_text
                          and len(submit_requests[0]["payload"]["references"]) == 1
                          and submit_requests[0]["payload"]["references"][0]["sha256"] == reference_sha
                          and latest_prompt is not None and latest_prompt["has_rework"] is True
                          and latest_prompt["prompt_hash"] == new_attempt["prompt"]["hash"]
                          and latest_prompt["text_chars"] == len(preview_text)
                          and latest_prompt["text_chars"] == len(submit_requests[0]["payload"]["prompt"])
                          and digest_versions(digest_after_submit, "prompt_version", first_shot)
                              == first_prompt_versions + 1,
                    "detail": {"attempt_state": new_attempt["state"] if new_attempt else None,
                               "prompt_version": latest_prompt["version"] if latest_prompt else None,
                               "prompt_hash_match": bool(new_attempt) and bool(latest_prompt)
                               and latest_prompt["prompt_hash"] == new_attempt["prompt"]["hash"],
                               "wire_prompt_chars": len(submit_requests[0]["payload"]["prompt"])
                               if submit_requests else 0,
                               "preview_chars": len(preview_text),
                               "candidates": len(new_candidates)},
                })

                old_blob = page.evaluate(v251.HASH_ASSET, {"sha256": expected_candidate_sha})
                after_assets = {item["sha256"]: item for item in digest_after_submit["assets"]}
                checks.append({
                    "id": "V2.5.4-14",
                    "title": "影响隔离：无关图的 Prompt/Attempt/Candidate/Blob 零变化；目标图的旧候选与旧 Blob 原样保留",
                    "ok": v251.candidate_json(succeeded, second_shot) == second_candidates_json
                          and json.dumps(succeeded["attempt_chains"].get(second_shot, []),
                                         sort_keys=True, default=str) == second_attempts_json
                          and digest_untouched(digest_before_submit, digest_after_submit, second_docs)
                          and digest_untouched(digest_before_submit, digest_after_submit, {"generation"})
                          and digest_kept_prefix(seeded_storage, digest_after_submit)
                          and any(item["payload"]["asset_sha256"] == expected_candidate_sha
                                  for item in new_candidates)
                          and old_blob.get("found") is True
                          and old_blob.get("sha256") == expected_candidate_sha
                          and all(after_assets.get(item["sha256"]) == item
                                  for item in seeded_storage["assets"])
                          and digest_versions(digest_after_submit, "prompt_version", second_shot)
                              == second_prompt_versions,
                    "detail": {"second_candidates_same":
                               v251.candidate_json(succeeded, second_shot) == second_candidates_json,
                               "old_candidate_kept": any(
                                   item["payload"]["asset_sha256"] == expected_candidate_sha
                                   for item in new_candidates),
                               "old_blob": {"found": old_blob.get("found"),
                                            "hash_match": old_blob.get("sha256") == expected_candidate_sha},
                               "second_prompt_versions": second_prompt_versions},
                })

                checks.append({
                    "id": "V2.5.4-15",
                    "title": "双击防护：连点「确认并生成这张图」只产生一条 Attempt、一次真实请求",
                    "ok": len(action_ids(new_attempts)) == 1 and len(submit_requests) == 1
                          and new_action_id in action_ids(new_attempts)
                          and len(action_ids(attempts_after)) == len(action_ids(attempts_before)) + 1,
                    "detail": {"new_actions": len(action_ids(new_attempts)),
                               "new_versions": len(new_attempts),
                               "requests": len(submit_requests), "action_id": new_action_id},
                })

                holder["scenario"] = "failed"
                failure_direction = "背景太杂：换成干净的浅灰背景，商品保持原样。"
                failure_preview = preview_rework(["scene"], failure_direction)
                failure_preview_text = failure_preview["preview_text"]
                captured.clear()
                page.click("#rework-submit")
                expect(page.locator("#rework-panel")).to_be_hidden(timeout=40_000)
                failed_probe = probe()
                failed_storage = storage()
                failed_panel = rework_probe()
                attempts_failed = failed_probe["attempt_chains"].get(first_shot, [])
                failed_attempt = attempts_failed[-1]["payload"]
                failed_row = next((item for item in failed_probe["ui"]["rows"]
                                   if item["shot_id"] == first_shot), None)
                failed_requests = [item for item in captured if item["payload"]
                                   and item["payload"].get("action_id") == failed_attempt["action_id"]]
                recovered = preview_rework(["scene"], failure_direction)
                checks.append({
                    "id": "V2.5.4-16",
                    "title": "失败可恢复：明确失败只留失败 Attempt（不产生候选），旧候选与旧 Blob 保留，可再次发起返工",
                    "ok": failed_attempt["state"] == "failed"
                          and len(action_ids(attempts_failed)) == len(action_ids(attempts_after)) + 1
                          and v251.candidate_json(failed_probe, first_shot)
                              == v251.candidate_json(succeeded, first_shot)
                          and len(failed_requests) == 1
                          and failed_requests[0]["payload"]["prompt"] == failure_preview_text
                          and digest_untouched(digest_after_submit, failed_storage, second_docs)
                          and bool(failed_row) and failed_row["state"] == "failed"
                          and "失败" in failed_panel["compare_status"]
                          and recovered["submit_disabled"] is False,
                    "detail": {"state": failed_attempt["state"],
                               "attempts": len(action_ids(attempts_failed)),
                               "candidates_same": v251.candidate_json(failed_probe, first_shot)
                               == v251.candidate_json(succeeded, first_shot),
                               "row_state": failed_row["state"] if failed_row else None,
                               "compare_status": failed_panel["compare_status"],
                               "recovered": recovered["submit_disabled"] is False},
                })

                holder["scenario"] = "submit_unknown"
                unknown_direction = "画面里的中文改成英文卖点，字数保持一致。"
                unknown_preview = preview_rework(["text"], unknown_direction)
                unknown_preview_text = unknown_preview["preview_text"]
                captured.clear()
                page.click("#rework-submit")
                expect(page.locator("#rework-panel")).to_be_hidden(timeout=40_000)
                unknown_probe = probe()
                unknown_storage = storage()
                attempts_unknown = unknown_probe["attempt_chains"].get(first_shot, [])
                unknown_attempt = attempts_unknown[-1]["payload"]
                unknown_row = next((item for item in unknown_probe["ui"]["rows"]
                                    if item["shot_id"] == first_shot), None)
                unknown_requests = [item for item in captured if item["payload"]
                                    and item["payload"].get("action_id")
                                    == unknown_attempt["action_id"]]
                checks.append({
                    "id": "V2.5.4-17",
                    "title": "Unknown 不自动重提：只留一条无 task id 的未知 Attempt，旧数据与候选不动，界面提示先不重提",
                    "ok": unknown_attempt["state"] == "unknown"
                          and not unknown_attempt.get("task_id")
                          and len(action_ids(attempts_unknown)) == len(action_ids(attempts_failed)) + 1
                          and len(unknown_requests) == 1
                          and unknown_requests[0]["payload"]["prompt"] == unknown_preview_text
                          and v251.candidate_json(unknown_probe, first_shot)
                              == v251.candidate_json(succeeded, first_shot)
                          and digest_untouched(failed_storage, unknown_storage, second_docs)
                          and bool(unknown_row) and unknown_row["state"] == "unknown"
                          and "没有任务编号" in unknown_probe["ui"]["error"],
                    "detail": {"state": unknown_attempt["state"],
                               "task_id": unknown_attempt.get("task_id"),
                               "attempts": len(action_ids(attempts_unknown)),
                               "requests": len(unknown_requests),
                               "row_state": unknown_row["state"] if unknown_row else None,
                               "error": unknown_probe["ui"]["error"][:120]},
                })

                page.reload(wait_until="networkidle")
                expect(page.locator("#project-view")).to_be_visible()
                expect(row(first_shot)).to_have_attribute("data-attempt-state", "unknown",
                                                          timeout=30_000)
                reloaded = probe()
                reloaded_storage = storage()
                open_panel(first_shot, 2, references=1)
                reloaded_panel = open_rework()
                screenshot_rel = f"evals/product-v2/evidence/v2.5.4-rework-loop-{stamp}.png"
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                detail_rel = f"evals/product-v2/evidence/v2.5.4-rework-loop-{stamp}-detail.png"
                page.locator("#rework-panel").screenshot(path=str(ROOT / detail_rel))
                screenshot_paths = [ROOT / screenshot_rel, ROOT / detail_rel]
                checks.append({
                    "id": "V2.5.4-18",
                    "title": "刷新恢复：候选/Attempt/返工确认从 IndexedDB 恢复，面板可重开（整页 + 返工区截图留档）",
                    "ok": v251.candidate_json(reloaded, first_shot)
                              == v251.candidate_json(unknown_probe, first_shot)
                          and json.dumps(reloaded["attempt_chains"].get(first_shot, []),
                                         sort_keys=True, default=str)
                              == json.dumps(unknown_probe["attempt_chains"].get(first_shot, []),
                                            sort_keys=True, default=str)
                          and digest_business(reloaded_storage) == digest_business(unknown_storage)
                          and digest_newest(reloaded_storage, "generation_confirm",
                                            "rework:" + first_shot) is not None
                          and reloaded_panel["visible"]
                          and reloaded_panel["contract"] == REWORK_CONTRACT_VERSION
                          and len(reloaded_panel["problems"]) == 9
                          and all(path.is_file() and path.stat().st_size > 0
                                  for path in screenshot_paths),
                    "detail": {"candidates": len(reloaded["candidate_chains"].get(first_shot, [])),
                               "attempts": len(reloaded["attempt_chains"].get(first_shot, [])),
                               "business_records_same":
                               digest_business(reloaded_storage) == digest_business(unknown_storage),
                               "screenshots": {path.relative_to(ROOT).as_posix():
                                               path.stat().st_size for path in screenshot_paths},
                               "prompt_chars": len(unknown_preview_text)},
                })
                ui["screenshot"] = screenshot_rel
                ui["screenshot_detail"] = detail_rel
                ui["preview_chars"] = len(preview_text)
                ui["checks"] = [item["id"] for item in checks]
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
        "id": "V2.5.4-06",
        "title": "RW-01–RW-15 返工契约套件：空理由、未知分类、跨图候选、hash 不符与正反路径全部守住",
        "ok": rework_suite.get("status") == "passed"
              and sorted(item["id"] for item in rework_suite.get("cases", []))
              == EXPECTED_REWORK_CASES,
        "detail": {"status": rework_suite.get("status"),
                   "failed": rework_suite.get("failed_ids"),
                   "cases": len(rework_suite.get("cases", []))},
    })
    checks.append({
        "id": "V2.5.4-07",
        "title": "既有套件回归：CP-01–CP-15、R01–R13、R14–R21 在返工闭环落地后仍全过",
        "ok": compare_suite.get("status") == "passed" and review_suite.get("status") == "passed"
              and provider_suite.get("status") == "passed",
        "detail": {"compare": compare_suite.get("status"), "review": review_suite.get("status"),
                   "provider": provider_suite.get("status")},
    })
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.5.4 单图返工闭环验证")
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
        "id": "V2.5.4-19",
        "title": "正式入口 --check 全过（返工闭环没有破坏既有自检）",
        # 自检条目会随批次增加：断言只看「全过」这一语义，不写死条数。
        "ok": entry["rc"] == 0 and any(
            re.search(r"V2 正式入口自检：\d+/\d+ 通过", line) for line in entry["tail"]),
        "detail": {"rc": entry["rc"], "tail": entry["tail"][-3:]},
    })
    expected_console = [item for item in console_errors if "status of 504" in item]
    unexpected_console = [item for item in console_errors if item not in expected_console]
    checks.append({
        "id": "V2.5.4-20",
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
    txt_path = EVIDENCE_DIR / f"v2.5.4-rework-loop-{stamp}{label}.txt"
    json_path = EVIDENCE_DIR / f"v2.5.4-rework-loop-{stamp}{label}.json"

    lines = [
        "V2.5.4 问题分类、改进方向与单图返工闭环验证（返工契约套件 + 真实工作台走查 + 视觉证据）",
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
        f"contract: {REWORK_CONTRACT_VERSION}（返工）· v2.5.3（比较面板）· v2.5.2（复核报告）",
        "model_calls: 0 · external_network_calls: 0（fake providers + 本地静态服务器）",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "边界：本套件 0 次真实模型调用；比较区保持只读，返工只在独立 #rework-panel 里写",
        "PromptVersion + scope=[目标图] 的确认 + Attempt；候选采纳（Selection）属 V2.6.1，",
        "导出 zip 属 V2.6.2，本批不宣称已经具备。",
        "「与真实请求一致」由浏览器侧捕获的 /api/v2/images/submit 请求体逐字比对得出，",
        "发送目标是本地 fake 图像网关（不是阿里云百炼）。",
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
        "suite_id": "v2.5.4-rework-loop",
        "status": "passed" if passed == len(checks) else "failed",
        "observed_at": observed_at,
        "contract": REWORK_CONTRACT_VERSION,
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
