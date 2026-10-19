#!/usr/bin/env python
"""V2.3.7 证据：AI 提议文案 → 采用 → 保存规格 → 编译/预览逐字（0 次真实模型调用 / 0 付费）。

检查（全部在正式页面走用户真实路径，假 Provider 只替代外部模型响应）：
  1) 提议：明确点一次「提议英文上图候选」只发一次 POST，候选行可见且可采用；
  2) 采用只写规格草稿：规格区对该槽位显示「已采用候选文案」而不是「旧版」，勾选框已勾；
     持久化规格与 Prompt 记录都没变（采用≠保存）；
  3) 未保存不生效：生成区本地准备把该图拦在印字决定上，没有任何包含该文案的 Prompt；
     其余图（草稿里同样被写入候选）也不印这条；
  4) 保存规格：新版本 on_image_texts 逐字等于候选文案、来源=该槽位+当前版本、status=confirmed、origin=model；
  5) 刷新后仍是「已采用候选文案」：origin 往返不降级成用户原文（再保存也不会把 model 抹成 user）；
  6) 编译/预览逐字：界面文本 = 记录文本 = 请求快照 prompt，均逐字包含该候选；逐字条目的 source_ref
     指向该 text_id；非平台语言给警告且卡片可见（不翻译、不改写）；
  7) 来源前进：规格区改口为「旧版」提醒（与「已采用」区分）；编译被拦并给出精确原因；
     旧版本记录保留，不静默换成新值；
  8) 零 console/page error；截图落盘。

运行：
  uv run --locked python tools/verify_v2_3_7_copy_adoption_chain.py
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
import zlib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402  （V2.UI.2 六阶段工作台导航）
import v2_verify_shared as shared  # noqa: E402  （Issue #9 普通决定共用函数）

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
SHOT = "shot_infographic_benefits"
SLOT = "signature_features"
FAKE_TEXT = "FAKE SIGNATURE FEATURES"
TEXT_ID = "t_" + SLOT + "_1"
LITERAL_REF = "shot_spec.on_image_text:" + TEXT_ID

SEED_SLOTS = """
async (projectId) => {
  const domain = await import("/domain/index.js");
  const storage = await import("/storage/index.js");
  const opened = await storage.openStorage({});
  try {
    const repository = opened.repository;
    const slot = (slotId, value) => {
      const definition = domain.coreSlotDefinition(slotId);
      return {
        schema_version: 1, slot_id: slotId, label: definition.label,
        authority: "core_fixed", value_type: definition.value_type,
        critical: definition.critical, value, source: "user_input",
        status: "confirmed", confidence: null,
        evidence: [{ kind: "user", ref: "v237-seed" }], depends_on: [],
      };
    };
    await repository.documents.save(projectId, {
      kind: "fact_slot", documentId: "product_name", payload: slot("product_name", "便携保温杯"),
    });
    await repository.documents.save(projectId, {
      kind: "fact_slot", documentId: "product_category", payload: slot("product_category", "保温杯"),
    });
    await repository.documents.save(projectId, {
      kind: "fact_slot", documentId: "signature_features",
      payload: slot("signature_features", ["304不锈钢内胆", "12小时保温"]),
    });
    return { slots: 3 };
  } finally {
    opened.close();
  }
}
"""

DB_DOCUMENTS = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) return { documents: [] };
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await new Promise((resolve, reject) => {
    const request = db.transaction("documents", "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  return {
    documents: documents.map((item) => ({
      kind: item.kind, document_id: item.document_id,
      version: item.version, payload: item.payload,
    })),
  };
}
"""

RECOMPUTE = """
async ({ shotId }) => {
  const domain = await import("/domain/index.js");
  const storage = await import("/storage/db.js");
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await new Promise((resolve, reject) => {
    const request = db.transaction("documents", "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const card = document.querySelector("#prompt-list .shot-spec[data-shot-id='" + shotId + "']");
  const record = documents.filter((item) => item.kind === "prompt_version" && item.document_id === shotId)
    .sort((left, right) => right.version - left.version)[0];
  if (!record) {
    // 没记录时把卡片的真实状态一起带出来：判红时要看得见「缺依据/编译失败」的原文，而不是只看 null。
    const error = card ? card.querySelector("#prompt-card-error-" + shotId) : null;
    return {
      found: false,
      ui_state: card ? card.getAttribute("data-prompt-state") : null,
      ui_meta: card ? card.textContent : null,
      ui_error: error ? error.textContent.trim() : null,
    };
  }
  const hash = await domain.promptHash(record.payload.request_snapshot, { digest: storage.sha256Hex });
  return {
    found: true,
    version: record.version,
    record_hash: record.payload.hash,
    recomputed_hash: hash,
    text: record.payload.compiled.text,
    snapshot_prompt: record.payload.request_snapshot.prompt,
    ui_text: card ? card.querySelector("pre.prompt-text").textContent : null,
    ui_meta: card ? card.textContent : null,
    ui_state: card ? card.getAttribute("data-prompt-state") : null,
    warnings: (record.payload.compiled.warnings || []).map((item) => item.code),
    literal_items: (record.payload.compiled.sections || [])
      .filter((item) => item.kind === "literal")
      .flatMap((item) => item.items.map((entry) => entry.text)),
    literal_refs: (record.payload.compiled.sections || [])
      .filter((item) => item.kind === "literal")
      .flatMap((item) => item.items.map((entry) => entry.source_ref)),
    basis: record.payload.basis,
  };
}"""


def png_bytes(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def documents_of(page) -> dict:
    """按 kind/document_id 归并最新文档：{(kind, document_id): 行}。"""
    payload = page.evaluate(DB_DOCUMENTS)
    out: dict[tuple, dict] = {}
    for row in payload.get("documents", []):
        key = (row.get("kind"), row.get("document_id"))
        current = out.get(key)
        if current is None or int(row.get("version") or 0) > int(current.get("version") or 0):
            out[key] = row
    return out


def prompt_json_of(page, shot_id: str) -> str:
    rows = [row for (kind, document_id), row in documents_of(page).items()
            if kind == "prompt_version" and document_id == shot_id]
    return json.dumps(rows, ensure_ascii=False, sort_keys=True)


def wait_documents(page, predicate, attempts: int = 60):
    """等文档快照满足断言；返回最后一次快照（调用方自己判定，不在这里判红）。"""

    documents: dict = {}
    for _ in range(attempts):
        documents = documents_of(page)
        if predicate(documents):
            return documents
        page.wait_for_timeout(150)
    return documents


def settle_local_preparation(page, timeout_ms: int = 20_000) -> None:
    """等生成区的异步本地准备落定（避免把准备中的瞬态当断言）。

    状态文案只在真的跑过准备时才出现；已经落定的会话可能什么都不显示，所以超时不判红——
    是否准备好由后面的断言按记录/卡片状态自己判定，这里只负责「别读到半途」。
    """

    try:
        page.wait_for_function(
            """() => (document.getElementById("local-preparation-status") || {}).textContent
                && (document.getElementById("local-preparation-status").textContent.includes("本地准备完成")
                    || document.getElementById("local-preparation-status").textContent.includes("部分任务尚未准备"))""",
            timeout=timeout_ms,
        )
    except Exception:  # noqa: BLE001 —— 状态文案不是判据：落空的准备由断言判红
        pass
    page.wait_for_timeout(300)


def prompt_card_error(page, shot_id: str) -> str:
    node = page.locator("#prompt-card-error-" + shot_id)
    return (node.text_content() or "").strip() if node.count() else ""


def attempt_compile(page, shot_id: str) -> None:
    """显式点一次该图的准备/编译按钮（用户真实路径），无论此前有没有记录。

    按钮被禁用（例如同一张图正在准备时）不硬点：状态文本仍会落定，断言自己判红。
    """

    button = page.locator('#prompt-list .shot-spec[data-shot-id="' + shot_id + '"] button').first
    if button.count() and button.is_enabled():
        button.click()
    page.wait_for_timeout(400)
    settle_local_preparation(page)


def compile_if_needed(page, shot_id: str) -> None:
    """进入生成区后若还没有记录，显式点一次该图的准备按钮（用户真实路径）。"""

    result = page.evaluate(RECOMPUTE, {"shotId": shot_id})
    if result.get("found"):
        return
    attempt_compile(page, shot_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.3.7 文案提议采用链验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []
    ui: dict = {}

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    from app.product_v2_server import create_product_v2_server  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    server = create_product_v2_server(
        "127.0.0.1", 0, provider_factory=lambda: FakeSemanticProvider(scenario="ok"))
    server.start()
    base = f"http://127.0.0.1:{server.port}"

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v237-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))
    spec_card = '#shot-spec-list .shot-spec[data-shot-id="' + SHOT + '"]'
    print_card = '#prompt-list .shot-spec[data-shot-id="' + SHOT + '"]'
    analyze_posts: list[str] = []
    image_posts: list[str] = []
    crash: str | None = None
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            def capture(request) -> None:
                if request.method != "POST":
                    return
                if "/api/v2/semantic/analyze" in request.url:
                    analyze_posts.append(request.post_data or "")
                elif "/api/v2/images" in request.url:
                    image_posts.append(request.url)

            page.on("request", capture)

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品 · 文案采用链")
            page.click("#create-project")
            expect(page.locator("#project-view")).to_be_visible()
            page.set_input_files("#ref-file", str(reference))
            expect(page.locator("#ref-list .ref-row")).to_have_count(1)
            page.fill("#intake-name", "便携保温杯")
            page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
            page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
            page.wait_for_timeout(1200)
            opened = page.evaluate(
                "async () => { const db = await new Promise((resolve) => {"
                " const request = indexedDB.open(\"amz-listing-kit-v2\");"
                " request.onsuccess = () => resolve(request.result); });"
                " const rows = await new Promise((resolve) => { const req = db.transaction(\"projects\", \"readonly\")"
                " .objectStore(\"projects\").getAll(); req.onsuccess = () => resolve(req.result); });"
                " db.close(); return rows.map((item) => item.project_id); }")
            page.evaluate(SEED_SLOTS, opened[0])
            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "plan")
            page.click("#suite-seed")
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            # 共用展示决定 + 展开规格区：四张图的规格草稿都在此时建立，采用才会写进「所有单图草稿」。
            ui["presentation"] = shared.decide_presentation(page)
            shared.open_specs(page)
            expect(page.locator("#shot-spec-list .shot-spec")).to_have_count(4)

            # ---------------------------------------------------------- 提议 + 采用
            stage_nav.goto(page, "understand")
            page.click("#slots-toggle")
            slot_row = page.locator('#slot-list .slot-row[data-slot-id="' + SLOT + '"]')
            expect(slot_row).to_be_visible()
            posts_before = len(analyze_posts)
            page.click("#slot-copy-" + SLOT)
            expect(page.locator("#slot-copy-result-" + SLOT + "-0")).to_be_visible(timeout=20_000)
            copy_row_text = (page.locator("#slot-copy-result-" + SLOT + "-0").text_content() or "").strip()
            check("V2.3.7-01", "提议：明确点一次只发一次请求（零图片外发），候选行可见且可采用",
                  len(analyze_posts) == posts_before + 1 and not image_posts
                  and FAKE_TEXT in copy_row_text
                  and page.locator("#slot-copy-adopt-" + SLOT + "-0").is_enabled(),
                  {"posts": len(analyze_posts) - posts_before, "image_posts": image_posts[:3],
                   "row": copy_row_text[:200]})

            page.click("#slot-copy-adopt-" + SLOT + "-0")
            before_save = documents_of(page)
            spec_key = ("shot_spec", SHOT)
            prompt_before = prompt_json_of(page, SHOT)
            stage_nav.goto(page, "plan")
            shared.open_specs(page)
            page.click("#spec-print-selected-" + SHOT)
            adopted_note = page.locator("#spec-text-adopted-" + SHOT + "-" + SLOT)
            advanced_note = page.locator("#spec-text-advanced-" + SHOT + "-" + SLOT)
            checkbox = page.locator("#spec-text-" + SHOT + "-" + SLOT)
            expect(adopted_note).to_be_visible()
            ui["adopted_note"] = (adopted_note.text_content() or "").strip()
            check("V2.3.7-02", "采用只写规格草稿：卡片显示「已采用候选文案」（不是「旧版」）且已勾选，持久化规格未变",
                  FAKE_TEXT in ui["adopted_note"] and "旧版" not in ui["adopted_note"]
                  and checkbox.is_checked() and advanced_note.count() == 0
                  and spec_key not in before_save,
                  {"note": ui["adopted_note"], "checked": checkbox.is_checked(),
                   "advanced_present": advanced_note.count(),
                   "persisted_spec": before_save.get(spec_key)})

            # ---------------------------------------------------------- 未保存不生效
            stage_nav.goto(page, "generate")
            stage_nav.reveal(page, "#prompt-editor")
            settle_local_preparation(page)
            compile_if_needed(page, SHOT)
            unsaved_record = page.evaluate(RECOMPUTE, {"shotId": SHOT})
            unsaved_error = prompt_card_error(page, SHOT)
            unsaved_other = {shot: prompt_json_of(page, shot) for shot in
                             ("shot_main_clean", "shot_scene_lifestyle", "shot_detail_material")}
            check("V2.3.7-03", "未保存不生效：该图仍被印字决定拦下，没有任何包含该文案的 Prompt；其余图也不印",
                  unsaved_record.get("found") is False
                  and "还没有决定要不要印文字" in unsaved_error
                  and prompt_before == prompt_json_of(page, SHOT)
                  and all(FAKE_TEXT not in payload for payload in unsaved_other.values()),
                  {"found": unsaved_record.get("found"), "error": unsaved_error[:200],
                   "others_contain": [shot for shot, payload in unsaved_other.items() if FAKE_TEXT in payload]})

            # ---------------------------------------------------------- 保存规格
            stage_nav.goto(page, "plan")
            shared.open_specs(page)
            page.click("#spec-layout-" + SHOT + "-product_left_text_right")
            page.click(spec_card + ' button:has-text("保存")')
            saved = wait_documents(page, lambda docs: ("shot_spec", SHOT) in docs)
            spec = (saved.get(("shot_spec", SHOT)) or {}).get("payload") or {}
            texts = spec.get("on_image_texts") if isinstance(spec.get("on_image_texts"), list) else []
            first = texts[0] if texts else {}
            slot_row_saved = (saved.get(("fact_slot", SLOT)) or {}).get("payload") or {}
            ui["saved_spec"] = {"version": (saved.get(("shot_spec", SHOT)) or {}).get("version"),
                                "print_intent": spec.get("print_intent"), "layout": spec.get("layout"),
                                "texts": texts}
            check("V2.3.7-04", "保存规格：条目逐字等于候选文案、来源=该槽位+当前版本、status=confirmed、origin=model",
                  spec.get("print_intent") == "selected"
                  and spec.get("layout") == "product_left_text_right"
                  and len(texts) == 1
                  and first.get("text") == FAKE_TEXT and first.get("text_id") == TEXT_ID
                  and first.get("status") == "confirmed" and first.get("origin") == "model"
                  and isinstance(first.get("source"), dict)
                  and first["source"].get("kind") == "fact_slot"
                  and first["source"].get("document_id") == SLOT
                  and first["source"].get("version") == (saved.get(("fact_slot", SLOT)) or {}).get("version")
                  and slot_row_saved.get("value") == ["304不锈钢内胆", "12小时保温"],
                  ui["saved_spec"])

            # ---------------------------------------------------------- 刷新往返：origin 不降级
            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "plan")
            shared.open_specs(page)
            after_reload_note = page.locator("#spec-text-adopted-" + SHOT + "-" + SLOT)
            after_reload_advanced = page.locator("#spec-text-advanced-" + SHOT + "-" + SLOT)
            expect(after_reload_note).to_be_visible()
            reloaded = documents_of(page)
            reloaded_first = (((reloaded.get(("shot_spec", SHOT)) or {}).get("payload") or {})
                              .get("on_image_texts") or [{}])[0]
            check("V2.3.7-05", "刷新后仍是「已采用候选文案」：origin 往返不降级成 user",
                  FAKE_TEXT in (after_reload_note.text_content() or "")
                  and after_reload_advanced.count() == 0
                  and reloaded_first.get("origin") == "model"
                  and page.locator("#spec-text-" + SHOT + "-" + SLOT).is_checked(),
                  {"note": (after_reload_note.text_content() or "").strip()[:200],
                   "origin": reloaded_first.get("origin")})

            # ---------------------------------------------------------- 编译/预览逐字
            stage_nav.goto(page, "generate")
            stage_nav.reveal(page, "#prompt-editor")
            settle_local_preparation(page)
            compile_if_needed(page, SHOT)
            compiled = page.evaluate(RECOMPUTE, {"shotId": SHOT})
            ui["compiled"] = {"version": compiled.get("version"), "warnings": compiled.get("warnings"),
                              "refs": compiled.get("literal_refs"),
                              "literal_items": compiled.get("literal_items"),
                              "text": compiled.get("text")}
            # 平台语言是 en：英文候选与平台一致，正确行为是「没有语言警告」；正文仍要声明只逐字使用、不翻译不改写。
            check("V2.3.7-06", "编译/预览逐字：界面=记录=快照且含该候选，source_ref 指向该 text_id，正文声明不翻译不改写",
                  compiled.get("found") is True
                  and compiled.get("text") == compiled.get("snapshot_prompt") == compiled.get("ui_text")
                  and FAKE_TEXT in (compiled.get("text") or "")
                  and LITERAL_REF in (compiled.get("literal_refs") or [])
                  and "不翻译、不改写、不新增" in (compiled.get("text") or "")
                  and "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" not in (compiled.get("warnings") or [])
                  and compiled.get("record_hash") == compiled.get("recomputed_hash"),
                  {key: value for key, value in ui["compiled"].items() if key not in ("text", "literal_items")}
                  | {"text_len": len(compiled.get("text") or ""),
                     "found": compiled.get("found"),
                     "error": prompt_card_error(page, SHOT)[:300],
                     "state": compiled.get("ui_state")})

            # ---------------------------------------------------------- 来源前进
            version_before = compiled.get("version")
            stage_nav.goto(page, "understand")
            page.click("#slots-toggle")
            slot_row_saved_edit = page.locator('#slot-list .slot-row[data-slot-id="' + SLOT + '"]')
            slot_row_saved_edit.get_by_role("button", name="修改", exact=True).click()
            page.fill("#slot-editor-value", "316不锈钢内胆\n12小时保温")
            slot_row_saved_edit.get_by_role("button", name="保存", exact=True).click()
            advanced_slot = wait_documents(
                page,
                lambda docs: int(((docs.get(("fact_slot", SLOT)) or {}).get("version") or 0))
                > int(slot_row_saved.get("version") or 0))
            advanced_version = (advanced_slot.get(("fact_slot", SLOT)) or {}).get("version")

            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "plan")
            shared.open_specs(page)
            advanced_note_2 = page.locator("#spec-text-advanced-" + SHOT + "-" + SLOT)
            expect(advanced_note_2).to_be_visible()
            stage_nav.goto(page, "generate")
            stage_nav.reveal(page, "#prompt-editor")
            settle_local_preparation(page)
            attempt_compile(page, SHOT)
            after_advance = page.evaluate(RECOMPUTE, {"shotId": SHOT})
            advance_error = prompt_card_error(page, SHOT)
            check("V2.3.7-07", "来源前进：卡片改口为「旧版」提醒，编译被拦且给精确原因，旧记录保留不换值",
                  advanced_version == int((saved.get(("fact_slot", SLOT)) or {}).get("version") or 0) + 1
                  and "旧版" in (advanced_note_2.text_content() or "")
                  and after_advance.get("version") == version_before
                  and FAKE_TEXT in (after_advance.get("text") or "")
                  and "的来源已改变" in advance_error
                  and "重新确认" in advance_error,
                  {"advanced_version": advanced_version,
                   "advance_ok": advanced_version == int((saved.get(("fact_slot", SLOT)) or {}).get("version") or 0) + 1,
                   "note": (advanced_note_2.text_content() or "").strip()[:200],
                   "note_ok": "旧版" in (advanced_note_2.text_content() or ""),
                   "version_kept": after_advance.get("version"), "expected_version": version_before,
                   "version_ok": after_advance.get("version") == version_before,
                   "text_ok": FAKE_TEXT in (after_advance.get("text") or ""),
                   "error": advance_error[:240],
                   "error_ok": "的来源已改变" in advance_error and "重新确认" in advance_error})

            panel_png = EVIDENCE_DIR / f"v2.3.7-copy-adoption-chain-{stamp}{'-' + args.label if args.label else ''}.png"
            page.screenshot(path=str(panel_png), full_page=True)
            screenshots.append(panel_png.relative_to(ROOT).as_posix())
            context.close()
    except Exception as error:  # noqa: BLE001 —— 验证器自己收口：异常也落证据，不留半个不落盘
        crash = type(error).__name__ + ": " + str(error)
    finally:
        server.stop()

    check("V2.3.7-99", "整套流程未异常中断", crash is None, {"error": crash})

    check("V2.3.7-08", "整套流程零 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:5], "page": page_errors[:5]})

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明「AI 提议文案 → 采用 → 保存规格 → 编译/预览」在正式页面是同一份合同：提议只在明确点击后外发一次；"
        "采用只写规格草稿（记忆态的「已采用候选文案」与来源前进的「旧版」提醒分开），未保存不进任何 Prompt；"
        "保存后 on_image_texts 逐字等于候选文案、来源指向该槽位当时版本、来源标记为 model，刷新不降级；"
        "编译产物界面文本=记录文本=请求快照正文，逐字包含该候选且 source_ref 指向该条目，非平台语言只警告不翻译；"
        "来源事实前进后编译被精确拦下，旧版本记录保留、不静默换值。假 Provider 只替代外部模型响应，"
        "全程 0 次真实模型调用、0 付费；不证明文案质量、翻译质量或出图效果，人工采用与最终交付验收仍在产品门内。"
    )
    report = {
        "task": "V2.3.7",
        "suite_id": "v2.3.7-copy-adoption-chain",
        "status": status,
        "finished_at": finished_at,
        "model_calls": 0,
        "checks": checks,
        "ui_flow": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshots": screenshots,
        "boundary": boundary,
    }
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.3.7-copy-adoption-chain-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.7-copy-adoption-chain-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.7 copy adoption chain",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 (offline page flow with fake provider)",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
    ]
    if screenshots:
        lines.append("screenshot: " + screenshots[0])
    lines += ["", "CHECKS"]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False)[:800])
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.3.7 文案提议采用链验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False)[:800])
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
