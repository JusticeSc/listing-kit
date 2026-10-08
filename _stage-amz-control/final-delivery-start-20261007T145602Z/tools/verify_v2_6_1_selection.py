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
import v2_verify_shared as shared  # noqa: E402  （静态服/契约套件读取器已归共享模块）
server_module = v251.load_server_module()


def product_text(relative: str) -> str:
    return (PRODUCT_DIR / relative).read_text(encoding="utf-8")


def compare_section(text: str) -> str:
    """compare-view 的比较/采用装配块（文件开头 → 单图返工分区）。"""

    return text[:text.index("单图返工闭环（V2.5.4）")]


def rework_section(text: str) -> str:
    """compare-view 的单图返工那一整块（独立分区，不属于比较区，也不属于采用区）。"""

    start = text.index("单图返工闭环（V2.5.4）")
    return text[start:text.index("人工选择与失效（V2.6.1）", start)]


def selection_section(text: str) -> str:
    """compare-view 的人工选择视图装配块（分区注释 → 文件末尾）：只装配与转发。"""

    return text[text.index("人工选择与失效（V2.6.1）"):]


def selection_write_block(text: str) -> str:
    """采用写路径的唯一所有者：selection-adoption Module 的 select()（记录所有权在 Module）。"""

    start = text.index("async function select(")
    return text[start:text.index("async function acknowledge(", start)]


def section_guard(block: str) -> dict:
    """采用写路径（Module）：只经仓储追加记录、先落盘再更新内存、不直连存储、不复制图片。"""

    forbidden = [token for token in (
        "indexedDB", "fetch(", "assets.put", "assets.add", "storage.openStorage",
        "prompt_version", "generation_attempt",
    ) if token in block]
    save_at = block.find("repository.commitSelection(")
    set_at = block.find("selections.set(")
    return {
        "forbidden_tokens": forbidden,
        "saves_selection": save_at >= 0 and "buildSelectionRecord(" in block,
        "memory_after_save": save_at >= 0 and set_at > save_at,
        "no_auto_select": "newActionId()" in block and "deps.beginAction()" in block,
    }


def view_forward_guard(block: str) -> dict:
    """采用视图：只装配/转发与就地反馈，不直接读写业务记录（视图不是第二状态源）。"""

    direct = [token for token in (
        "documents.save", "selections.set", "indexedDB", "assets.put", "assets.add",
    ) if token in block]
    return {
        "direct_writes": direct,
        "forwards_to_module": "selectionAdoption.select(" in block,
        "error_path_kept": "showError(elements.adoptError" in block,
    }


def pure_compare_guard(block: str) -> list[str]:
    """比较区仍是纯投影：只放入口，不写业务记录、不产生选择。"""

    return [token for token in (
        "documents.save", "assets.put", "writeSelectionRecord", "handleAdoptSubmit",
        "handleAdoptClear", "selections.set", "fetch(",
    ) if token in block]


def pure_rework_guard(block: str) -> list[str]:
    """返工区不被采用逻辑污染：两张面板各自独立。"""

    return [token for token in (
        "writeSelectionRecord", "handleAdoptSubmit", "handleAdoptClear", "selections.set",
        "adoptSubmit", "adoptClear", "selectionAdoption.select(", "adoptCandidate(",
    ) if token in block]


def negative_probe() -> dict:
    """新增守卫的判红能力：同一判据必须能被一处篡改造红。"""

    block = selection_write_block(product_text("selection-adoption.ts"))
    valid = section_guard(block)
    mutated = section_guard(block.replace("repository.commitSelection(",
                                          "indexedDB.open(", 1))
    view_text = product_text("ui/compare-view.ts")
    compare_block = compare_section(view_text)
    compare_valid = pure_compare_guard(compare_block)
    compare_mutated = pure_compare_guard(compare_block + "\n  selections.set('x', {});\n")
    rework_block = rework_section(view_text)
    rework_valid = pure_rework_guard(rework_block)
    rework_mutated = pure_rework_guard(rework_block + "\n  selectionAdoption.select('clear', 'x', null);\n")
    view_valid = view_forward_guard(selection_section(view_text))
    view_mutated = view_forward_guard(selection_section(view_text) + "\n  documents.save('p', {});\n")
    red = (not mutated["saves_selection"] and not mutated["memory_after_save"]
           and bool(compare_mutated) and not compare_valid
           and bool(rework_mutated) and not rework_valid
           and bool(view_mutated["direct_writes"]) and not view_valid["direct_writes"])
    return {
        "selections_save_guard_red": not mutated["saves_selection"],
        "compare_purity_guard_red": bool(compare_mutated) and not compare_valid,
        "rework_purity_guard_red": bool(rework_mutated) and not rework_valid,
        "view_forward_guard_red": bool(view_mutated["direct_writes"]) and not view_valid["direct_writes"],
        "ok": red and valid["saves_selection"] and valid["memory_after_save"]
              and valid["no_auto_select"] and not valid["forbidden_tokens"]
              and view_valid["forwards_to_module"] and view_valid["error_path_kept"],
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
    module_text = product_text("selection-adoption.ts")
    compare_text = product_text("ui/compare-view.ts")
    html = (PRODUCT_DIR / "index.html").read_text(encoding="utf-8")
    definition_tokens = ("SELECTION_CONTRACT_VERSION =", "SELECTION_SCHEMA_VERSION =",
                         "SELECTION_ACTIONS =", "SELECTION_STATES =",
                         "SELECTION_STATE_TEXT =", "function buildSelectionRecord")
    duplicated = [token for token in definition_tokens if token in workspace_text]
    defined_outside_domain = [name for name, text in (("selection-adoption.ts", module_text),
                                                     ("ui/compare-view.ts", compare_text))
                              if any(token in text for token in definition_tokens)]
    checks.append({
        "id": "V2.6.1-02",
        "title": "单一权威：选择记录形状、词表与合同版本只在 domain/selection.js 定义，消费者只引用",
        "ok": 'SELECTION_CONTRACT_VERSION = "v2.6.1"' in selection_text
              and 'DOMAIN_DOCUMENT_KINDS.selection' in selection_text
              # 消费者改为经 domain 的构造函数/断言使用：记录所有权在 selection-adoption Module。
              and "buildSelectionRecord(" in module_text
              and "assertSelectionRecord(" in module_text
              and "deriveSelectionState(" in module_text
              and not duplicated and not defined_outside_domain,
        "detail": {"duplicated_in_workspace": duplicated,
                   "defined_outside_domain": defined_outside_domain,
                   "module_uses_domain_builders": "buildSelectionRecord(" in module_text},
    })

    i_compare = html.index('<section id="compare-panel"')
    i_attempt_error = html.index('id="attempt-error"')
    compare_html = html[i_compare:i_attempt_error]
    wiring = {
        # 权威：ui-contract §4.9 / design §452「无第二个重复确认面板」——入口就地放在比较区。
        "no_duplicate_panel": '<section id="adopt-panel"' not in html,
        "entries_in_compare": all(f'id="{name}"' in compare_html for name in
                                  ("adopt-open", "adopt-clear")),
        "feedback_adjacent": all(f'id="{name}"' in html for name in
                                 ("adopt-status", "adopt-error")),
        "single_click_wiring":
            'elements.adoptOpen.addEventListener("click", () => { void compareView?.adoptCandidate("select"); })'
            in workspace_text
            and 'elements.adoptClear.addEventListener("click", () => { void compareView?.adoptCandidate("clear"); })'
            in workspace_text,
        "clear_secondary_in_compare": 'id="adopt-clear"' in compare_html
                                      and 'class="primary" type="button" disabled>采用当前候选' in compare_html,
    }
    checks.append({
        "id": "V2.6.1-03",
        "title": "界面责任：采用入口就地放在比较区（无第二个重复确认面板），主次按钮与反馈区就位",
        "ok": all(wiring.values()),
        "detail": wiring,
    })

    block = selection_write_block(product_text("selection-adoption.ts"))
    guard = section_guard(block)
    view_guard = view_forward_guard(selection_section(product_text("ui/compare-view.ts")))
    probe = negative_probe()
    checks.append({
        "id": "V2.6.1-04",
        "title": "写路径唯一：采用只经仓储追加选择记录（Module 拥有记录），视图只转发、失败走错误提示",
        "ok": guard["saves_selection"] and guard["memory_after_save"] and guard["no_auto_select"]
              and not guard["forbidden_tokens"]
              and not view_guard["direct_writes"] and view_guard["forwards_to_module"]
              and view_guard["error_path_kept"] and probe["ok"],
        "detail": {**guard, "view": view_guard, "negative_probe": probe, "section_chars": len(block)},
    })

    view_text = product_text("ui/compare-view.ts")
    compare_forbidden = pure_compare_guard(compare_section(view_text))
    rework_forbidden = pure_rework_guard(rework_section(view_text))
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
  const clearButton = document.getElementById("adopt-clear");
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
    status: (document.getElementById("adopt-status") || {}).textContent || "",
    status_hidden: isHidden(document.getElementById("adopt-status")),
    error: (document.getElementById("adopt-error") || {}).textContent || "",
    error_hidden: isHidden(document.getElementById("adopt-error")),
    open_disabled: entry.disabled,
    open_text: entry.textContent || "",
    clear_disabled: clearButton.disabled,
    progress: (document.getElementById("adopt-progress") || {}).textContent || "",
    compare_visible: !comparePanel.hidden,
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


                def wait_candidate_ui(shot_id: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(shot) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                            return Boolean(node && node.querySelector('.attempt-candidate'));
                        }""", arg=shot_id, timeout=timeout)

                def wait_terminal_all(shot_ids: list, timeout: int = 120_000) -> None:
                    # 一次点击 #confirm-action 会保存授权并外发全部已就绪任务（批次确认）：
                    # 逐图"生成这张图"在已提交后是 disabled（产品正确的不自动重提），
                    # 所以这里直接等全部图进入终态，不再逐图点按钮。
                    shared.wait_terminal(page, shot_ids, timeout=timeout)
                    for shot_id in shot_ids:
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

                def adopt_state(candidate_id: str) -> dict:
                    return page.evaluate(
                        """(wanted) => {
                            const open = document.getElementById("adopt-open");
                            const tab = document.querySelector(
                                '#compare-candidates [role="tab"][aria-selected="true"]');
                            return {
                                disabled: open ? open.disabled : null,
                                selected: tab ? tab.getAttribute("data-candidate-id") : null,
                            };
                        }""", arg=candidate_id)

                def adopt_ready(candidate_id: str) -> None:
                    # 采用入口只投影「正看着的候选」与已落库的内存状态：点卡片后
                    # 入口按需重算（selectCompareCandidate → updateAdoptEntry）。
                    # 若正看着的候选就是已采用的当前项，入口保持 disabled
                    # （updateAdoptEntry 的 already 分支：不重复提交），此时直接返回。
                    state = adopt_state(candidate_id)
                    if state["disabled"] is True and state["selected"] == candidate_id:
                        return
                    page.wait_for_function(
                        """(wanted) => {
                            const open = document.getElementById("adopt-open");
                            if (!open || open.disabled) return false;
                            const tab = document.querySelector(
                                '#compare-candidates [role="tab"][aria-selected="true"]');
                            return tab
                              && tab.getAttribute("data-candidate-id") === wanted;
                        }""", arg=candidate_id, timeout=20_000)


                def adopt_click() -> dict:
                    # 「无第二个重复确认面板」（ui-contract:225 / design §452）：一次点击就是明确的采用决定。
                    # Module.select 是异步落库：先写 status"正在保存"，落库完成后才重写
                    # "已采用候选/已取消采用"，所以等"正在保存"消失才算完成。
                    page.click("#adopt-open")
                    page.wait_for_selector("#adopt-status:not([hidden])", timeout=20_000)
                    page.wait_for_function(
                        """() => { const node = document.getElementById("adopt-status");
                            return node && !node.hidden
                              && node.textContent.indexOf("正在保存") < 0; }""",
                        timeout=20_000)
                    return probe()

                def adopt_clear() -> dict:
                    # clear 与 select 同一异步落库：等"正在保存"消失后再读行摘要，
                    # 否则读到旧 current 投影。
                    page.click("#adopt-clear")
                    page.wait_for_selector("#adopt-status:not([hidden])", timeout=20_000)
                    page.wait_for_function(
                        """() => { const node = document.getElementById("adopt-status");
                            return node && !node.hidden
                              && node.textContent.indexOf("正在保存") < 0; }""",
                        timeout=20_000)
                    return probe()


                def rework_once(shot_id: str, problem_id: str, direction: str,
                                known_candidates: int = 0) -> None:
                    # 返工经单图确认外发：面板关闭只代表提交返回，不代表新候选已落库。
                    # 用候选链长度增长（attempt_probe 的 candidate_chains）等新候选，
                    # 再等候选 UI 出现；否则会读到"返工前"的旧链并误判 current。
                    page.click("#rework-open")
                    expect(page.locator("#rework-panel")).to_be_visible()
                    page.click(f'label[data-problem-id="{problem_id}"]')
                    page.fill("#rework-direction", direction)
                    page.click("#rework-preview")
                    expect(page.locator("#rework-preview-box")).to_be_visible(timeout=20_000)
                    page.click("#rework-submit")
                    expect(page.locator("#rework-panel")).to_be_hidden(timeout=40_000)
                    if known_candidates:
                        before = len((attempt_probe()["candidate_chains"] or {}).get(shot_id, []))
                        page.wait_for_function(
                            """(payload) => {
                                const rows = document.querySelectorAll(
                                    '#attempt-list .attempt-row[data-shot-id="' + payload.shot + '"]'
                                    + ' .attempt-candidate');
                                return rows.length > 0;
                            }""", arg={"shot": shot_id}, timeout=40_000)
                        deadline = 40_000
                        while len((attempt_probe()["candidate_chains"] or {}).get(shot_id, [])) <= before:
                            page.wait_for_timeout(200)
                            deadline -= 200
                            if deadline <= 0:
                                break
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
                shared.compile_all(page, shot_ids)
                gate = shared.confirm_and_submit(
                    page, expect, lambda: attempt_probe(), shot_ids=shot_ids)
                assert gate["ok"], f"确认必须产生本次授权的新消费：{gate['after_actions']}"
                expect(page.locator("#confirm-record")).to_contain_text("不会要求第二次提交")
                # 「一次点击先保存这份授权」的真实可观察面：授权记录（单文档、版本递增）已落库。
                confirmed_rows = [item for item in storage()["rows"]
                                  if item["kind"] == "generation_confirm"
                                  and item["document_id"] == "generation"]
                if not confirmed_rows or confirmed_rows[-1]["version"] < 1:
                    raise AssertionError("一次点击没有先落授权记录：" + repr(confirmed_rows))
                wait_terminal_all(shot_ids)
                open_panel(first_shot, 1, references=1)
                rework_once(first_shot, "scene", "把背景换成纯白，商品保持不变，不要改标识。")

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
                    "title": "入口：采用主按钮始终绑定比较区「正看着的候选」，换卡后身份随之变化",
                    "ok": opened_compare["entry"]["in_compare"]
                          and opened_compare["entry"]["disabled"] is False
                          and opened_compare["selected_candidate_id"] == default_id
                          and followed["selected_candidate_id"] == other_id,
                    "detail": {"default": default_id, "switched": other_id,
                               "entry": followed["entry"],
                               "selected": followed["selected_candidate_id"]},
                })

                viewed = probe()
                checks.append({
                    "id": "V2.6.1-10",
                    "title": "采用入口：主按钮绑定「当前查看候选」且就地保存（无确认面板），次按钮状态与之相称",
                    "ok": viewed["selected_candidate_id"] == other_id
                          and viewed["open_disabled"] is False
                          and "采用当前候选" in viewed["open_text"]
                          and viewed["clear_disabled"] is True
                          and viewed["compare_visible"] is True,
                    "detail": {"selected_candidate": viewed["selected_candidate_id"],
                               "open_disabled": viewed["open_disabled"],
                               "clear_disabled": viewed["clear_disabled"],
                               "compare_visible": viewed["compare_visible"]},
                })

                switched_view = select_candidate(default_id)
                viewed_storage = storage()
                checks.append({
                    "id": "V2.6.1-11",
                    "title": "查看/切换候选不改写任何记录，焦点落在被切换的候选标签",
                    "ok": switched_view["selected_candidate_id"] == default_id
                          and switched_view["focus_id"] == "compare-tab-" + default_id
                          and viewed_storage == seeded_storage,
                    "detail": {"selected_candidate": switched_view["selected_candidate_id"],
                               "focus": switched_view["focus_id"],
                               "records_unchanged": viewed_storage == seeded_storage},
                })
                select_candidate(other_id)
                adopt_ready(other_id)
                adopted = adopt_click()
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
                          and "已采用候选" in adopted["status"]
                          and "旧候选和旧采用保留在历史中" in adopted["status"]
                          and adopted["status_hidden"] is False,
                    "detail": {"selection": first_selection, "progress": adopted_progress,
                               "badges": adopted["badges"], "status": adopted["status"]},
                })

                checks.append({
                    "id": "V2.6.1-13",
                    "title": "采用只写选择：Prompt/Attempt/Candidate/Review/确认与图片资产逐字不变，无关图零变化",
                    "ok": others_untouched(viewed_storage, adopted_storage)
                          and v254.digest_untouched(viewed_storage, adopted_storage, second_docs)
                          and len(adopted_storage["assets"]) == len(viewed_storage["assets"]),
                    "detail": {"others_untouched": others_untouched(viewed_storage, adopted_storage),
                               "second_shot_untouched": v254.digest_untouched(
                                   viewed_storage, adopted_storage, second_docs),
                               "assets": len(adopted_storage["assets"])},
                })
                switched = select_candidate(default_id)
                adopt_ready(default_id)
                reselected = adopt_click()
                reselected_storage = storage()
                second_selection = newest_selection(reselected_storage, first_shot)
                reselected_badges = {item["candidate_id"]: item for item in reselected["badges"]}
                reselected_progress = progress_of(reselected["progress"])
                kept_prefix = v254.digest_kept_prefix(adopted_storage, reselected_storage)
                checks.append({
                    "id": "V2.6.1-14",
                    "title": "改选：追加新版本而不是覆盖，旧记录逐字保留，徽标与摘要随之移动",
                    "ok": switched["selected_candidate_id"] == default_id
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

                rework_once(first_shot, "scene", "把背景换成纯白，商品保持不变，不要改标识。",
                            known_candidates=len(candidate_ids))
                wait_candidate_ui(first_shot)
                open_panel(first_shot, 3, references=1)
                after_rework = attempt_probe()
                chain_after = after_rework["candidate_chains"].get(first_shot, [])
                newest_candidate_id = chain_after[-1]["payload"]["candidate_id"]
                stale_rows = [item for item in probe()["rows"] if item["shot_id"] == first_shot]
                stale_progress = progress_of(probe()["progress"])
                stale_badges = {item["candidate_id"]: item for item in probe()["badges"]}
                stale_selection = newest_selection(storage(), first_shot)
                checks.append({
                    "id": "V2.6.1-15",
                    # 现产品语义（domain/selection.js:158-166）：新成功候选不再自动使采用过期
                    # （自动审核只提供依据，采用是人的决定）；只有它实际消费的来源/依据
                    # 真的变化（候选消失、字节变化、Prompt 依据过期）才 stale。
                    # 返工经单图确认外发后，旧采用保持 current，新候选只追加到链上。
                    "title": "返工后不自动失效：新候选追加到链上，旧采用保持 current（新候选≠人的决定失效）",
                    "ok": newest_candidate_id not in candidate_ids
                          and len(chain_after) == len(candidate_ids) + 1
                          and stale_rows and stale_rows[0]["selection_state"] == "current"
                          and stale_progress is not None and stale_progress["current"] == 1
                          and stale_progress["stale"] == 0
                          and stale_badges.get(default_id, {}).get("state") == "current"
                          and stale_badges.get(default_id, {}).get("text") == "已采用"
                          and stale_selection is not None
                          and stale_selection["candidate_id"] == default_id
                          and stale_selection["version"] == 2,
                    "detail": {"newest_candidate": newest_candidate_id,
                               "chain_grew": len(chain_after),
                               "row": stale_rows[0] if stale_rows else None,
                               "progress": stale_progress, "badges": stale_badges,
                               "selection_version": stale_selection["version"] if stale_selection else None},
                })

                select_candidate(other_id)
                adopt_ready(other_id)
                back_to_old = adopt_click()
                back_storage = storage()
                third_selection = newest_selection(back_storage, first_shot)
                back_progress = progress_of(back_to_old["progress"])
                back_badges = {item["candidate_id"]: item for item in back_to_old["badges"]}
                checks.append({
                    "id": "V2.6.1-16",
                    "title": "返工后改选：追加新版本指向所选候选，徽标随之移动，历史全部保留",
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
                adopt_ready(newest_candidate_id)
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
                page.click("#adopt-open")
                page.wait_for_selector("#adopt-error:not([hidden])", timeout=20_000)
                failed = probe()
                failed_storage = storage()
                failed_progress = progress_of(failed["progress"])
                failed_selection = newest_selection(failed_storage, first_shot)
                page.evaluate("() => { window.__v261FailSelectionWrite = false; }")
                recovered = adopt_click()
                recovered_storage = storage()
                recovered_selection = newest_selection(recovered_storage, first_shot)
                checks.append({
                    "id": "V2.6.1-17",
                    "title": "写入失败不改旧选择：明确报错、不新增记录、旧选择与进度不变；恢复后重试能追加",
                    "ok": "写入失败" in failed["error"] and failed["error_hidden"] is False
                          and "人工选择没有保存" in failed["status"]
                          and len(selection_rows(failed_storage)) == failed_rows_before
                          and failed_selection is not None
                          and failed_selection["candidate_id"] == other_id
                          and failed_selection["version"] == 3
                          and failed_progress == back_progress
                          and recovered_selection is not None
                          and recovered_selection["version"] == 4
                          and recovered_selection["candidate_id"] == newest_candidate_id
                          and "已采用候选" in recovered["status"],
                    "detail": {"error": failed["error"], "version_after_failure":
                               failed_selection["version"] if failed_selection else None,
                               "recovered_version": recovered_selection["version"]
                               if recovered_selection else None},
                })

                select_candidate(default_id)
                adopt_ready(default_id)
                page.evaluate(
                    """() => {
                        const button = document.getElementById("adopt-open");
                        button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
                        button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
                    }""")
                page.wait_for_selector("#adopt-status:not([hidden])", timeout=20_000)
                double_storage = storage()
                double_selection = newest_selection(double_storage, first_shot)
                checks.append({
                    "id": "V2.6.1-18",
                    "title": "双击防护：连点「采用当前候选」只追加一条记录、一次版本推进",
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

                if probe()["open_disabled"] is False:
                    adopt_click()
                screenshot_rel = f"evals/product-v2/evidence/v2.6.1-selection-{stamp}.png"
                detail_rel = f"evals/product-v2/evidence/v2.6.1-selection-{stamp}-detail.png"
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                page.locator("#compare-panel").screenshot(path=str(ROOT / detail_rel))
                screenshot_paths = [ROOT / screenshot_rel, ROOT / detail_rel]
                final_storage = storage()
                final_payloads = [{"keys": item["payload_keys"], "chars": item["payload_chars"]}
                                  for item in selection_rows(final_storage)]
                checks.append({
                    "id": "V2.6.1-21",
                    "title": "视觉证据：整页与比较区采用入口特写落盘；选择记录只引用内容寻址身份，不含图片字节",
                    "ok": all(path.is_file() and path.stat().st_size > 0 for path in screenshot_paths)
                          and bool(final_payloads)
                          and all(item["keys"] == SELECTION_PAYLOAD_KEYS for item in final_payloads)
                          and all(item["chars"] < 2000 for item in final_payloads),
                    "detail": {"screenshots": {path.relative_to(ROOT).as_posix(): path.stat().st_size
                                               for path in screenshot_paths},
                               "selection_payloads": final_payloads,
                               "selection_rows": len(selection_rows(final_storage)),
                               "adopt_status": probe()["status"]},
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
        static_server, static_url = shared.start_static_server()
        try:
            selection_suite = shared.read_suite(
                browser, static_url + "/harness/selection-contract.html",
                "__V2_SELECTION_RESULTS__", console_errors, page_errors)
            rework_suite = shared.read_suite(
                browser, static_url + "/harness/rework-contract.html",
                "__V2_REWORK_RESULTS__", console_errors, page_errors)
            compare_suite = shared.read_suite(
                browser, static_url + "/harness/compare-panel.html",
                "__V2_COMPARE_RESULTS__", console_errors, page_errors)
            review_suite = shared.read_suite(
                browser, static_url + "/harness/review-contract.html",
                "__V2_REVIEW_RESULTS__", console_errors, page_errors)
            provider_suite = shared.read_suite(
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
