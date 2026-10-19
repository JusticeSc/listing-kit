#!/usr/bin/env python
"""V2.3.8 证据：规格保存的 OCC 冲突——保留草稿、精确报冲突、可恢复（0 次真实模型调用 / 0 付费）。

检查（正式页面，两个标签页共享同一 IndexedDB，不注入内部状态）：
  1) 准备：两个标签页读到同一项目；A 页改了这张图的规格草稿（目的/印字/版面），库里还没有该图规格；
  2) B 页保存同一张图 → v1 落库（另一标签页真实写入了新版本）；
  3) A 页再保存被 OCC 拦下：可见冲突条说清「已被保存为 v1、你的修改还在草稿里、没有覆盖它」，
     草稿原样保留，库里仍只有 v1（B 的值）——不静默覆盖、不假称保存成功；
  4) A 页「重新载入最新版本」：只换基版本（冲突条变状态行、草稿仍是 A、库里仍只有 v1）；
  5) A 页再保存 → 追加 v2（值=A）；v1 历史仍是 B（append-only 不改写）；冲突条消失；
  6) 无关图隔离：其它图没有规格记录、卡片仍是「默认（未保存）」；
  7) 零 console/page error；截图落盘。

运行：
  uv run --locked python tools/verify_v2_3_8_spec_save_occ.py
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
OTHER_SHOT = "shot_main_clean"
PURPOSE_A = "A 标签页的草稿说明（未保存）"
PURPOSE_B = "B 标签页保存的说明"

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
        evidence: [{ kind: "user", ref: "v238-seed" }], depends_on: [],
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

DB_ROWS = """
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


def png_bytes(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def all_rows(page) -> list[dict]:
    return page.evaluate(DB_ROWS).get("documents", [])


def spec_rows(page, shot_id: str) -> list[dict]:
    """该图的规格历史（全部版本，按版本升序）；只读投影，不注入内部状态。"""

    rows = [row for row in all_rows(page)
            if row.get("kind") == "shot_spec" and row.get("document_id") == shot_id]
    return sorted(rows, key=lambda row: int(row.get("version") or 0))


def wait_spec_versions(page, shot_id: str, versions: list[int], attempts: int = 80) -> list[dict]:
    rows: list[dict] = []
    for _ in range(attempts):
        rows = spec_rows(page, shot_id)
        if [int(row.get("version") or 0) for row in rows] == versions:
            return rows
        page.wait_for_timeout(150)
    return rows


def card(page, shot_id: str):
    return page.locator('#shot-spec-list .shot-spec[data-shot-id="' + shot_id + '"]')


def card_meta(page, shot_id: str) -> str:
    node = card(page, shot_id).locator(".shot-spec-head .meta")
    return (node.text_content() or "").strip() if node.count() else ""


def save_button(page, shot_id: str):
    return card(page, shot_id).locator('button:has-text("保存")').first


def open_second_tab(context, base: str, project_name: str, errors: list[str],
                    page_errors: list[str]):
    """在同一浏览器上下文开第二个页面并进入同一项目（共享 IndexedDB = 另一个标签页）。"""

    from playwright.sync_api import expect  # noqa: PLC0415

    page2 = context.new_page()
    page2.on("console", lambda message: errors.append(message.text)
             if message.type == "error" else None)
    page2.on("pageerror", lambda error: page_errors.append(str(error)))
    page2.goto(base + "/", wait_until="networkidle")
    view = page2.locator("#project-view")
    try:
        expect(view).to_be_visible(timeout=15_000)
    except Exception:  # noqa: BLE001 —— 指针没恢复项目时按项目名进入（仍是正式页面路径）
        page2.get_by_text(project_name, exact=False).first.click()
        expect(view).to_be_visible(timeout=15_000)
    return page2


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.3.8 规格保存 OCC 冲突验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_name = "审计商品 · 规格保存 OCC"
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []
    ui: dict = {}

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    from app.product_v2_server import create_product_v2_server  # noqa: PLC0415

    server = create_product_v2_server("127.0.0.1", 0)
    server.start()
    base = f"http://127.0.0.1:{server.port}"

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v238-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))
    crash: str | None = None
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", project_name)
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
            shared.decide_presentation(page)
            shared.open_specs(page)
            expect(page.locator("#shot-spec-list .shot-spec")).to_have_count(4)

            # ---------------------------------------------------------- 01 草稿准备
            page.fill("#spec-purpose-" + SHOT, PURPOSE_A)
            page.click("#spec-print-none-" + SHOT)
            page.click("#spec-layout-" + SHOT + "-product_only")
            ui["draft_value"] = page.input_value("#spec-purpose-" + SHOT)
            ui["meta_before"] = card_meta(page, SHOT)
            ui["rows_before"] = [int(row.get("version") or 0) for row in spec_rows(page, SHOT)]
            check("V2.3.8-01", "准备：A 页改好草稿（目的/印字/版面），该图还没有任何规格记录",
                  ui["draft_value"] == PURPOSE_A
                  and ui["meta_before"] == "默认（未保存）"
                  and ui["rows_before"] == [],
                  {"draft": ui["draft_value"], "meta": ui["meta_before"],
                   "versions": ui["rows_before"]})

            # ---------------------------------------------------------- 02 另一标签页写入 v1
            page2 = open_second_tab(context, base, project_name, console_errors, page_errors)
            stage_nav.goto(page2, "plan")
            shared.open_specs(page2)
            page2.fill("#spec-purpose-" + SHOT, PURPOSE_B)
            page2.click("#spec-layout-" + SHOT + "-product_only")
            shared.decide_shot_decision(page2, SHOT, print_intent="none")
            versioned = wait_spec_versions(page2, SHOT, [1])
            ui["v1"] = {"versions": [int(row.get("version") or 0) for row in versioned],
                        "purpose": (versioned[0].get("payload") or {}).get("purpose") if versioned else None}
            check("V2.3.8-02", "第二标签页保存同一张图：v1 落库，目的=B",
                  ui["v1"]["versions"] == [1] and ui["v1"]["purpose"] == PURPOSE_B,
                  ui["v1"])

            # ---------------------------------------------------------- 03 A 页保存被 OCC 拦下
            page.bring_to_front()
            expect(card(page, SHOT)).to_be_visible()
            save_button(page, SHOT).click()
            conflict = page.locator("#spec-save-conflict-" + SHOT)
            expect(conflict).to_be_visible(timeout=15_000)
            conflict_text = (conflict.text_content() or "").strip()
            conflict_role = conflict.get_attribute("role")
            page.wait_for_timeout(400)
            rows_after_conflict = spec_rows(page, SHOT)
            ui["conflict"] = {"text": conflict_text, "role": conflict_role,
                              "draft": page.input_value("#spec-purpose-" + SHOT),
                              "versions": [int(row.get("version") or 0) for row in rows_after_conflict],
                              "persisted_purpose": (rows_after_conflict[-1].get("payload") or {}).get("purpose")
                              if rows_after_conflict else None}
            check("V2.3.8-03", "A 页保存被版本冲突拦下：可见冲突说清「已保存为 v1、草稿还在、没有覆盖」，不静默覆盖",
                  "v1" in conflict_text and "草稿" in conflict_text
                  and ("没有覆盖" in conflict_text or "没有保存" in conflict_text)
                  and conflict_role == "alert"
                  and ui["conflict"]["draft"] == PURPOSE_A
                  and ui["conflict"]["versions"] == [1]
                  and ui["conflict"]["persisted_purpose"] == PURPOSE_B,
                  ui["conflict"])

            # ---------------------------------------------------------- 04 重载最新版本（只换基线）
            page.click("#spec-reload-latest-" + SHOT)
            expect(conflict).to_be_visible()
            page.wait_for_function(
                """(id) => {
                  const node = document.getElementById("spec-save-conflict-" + id);
                  return Boolean(node && node.textContent.includes("已按最新版本"));
                }""", arg=SHOT, timeout=15_000)
            reloaded_text = (conflict.text_content() or "").strip()
            rows_after_reload = spec_rows(page, SHOT)
            ui["reloaded"] = {"text": reloaded_text, "role": conflict.get_attribute("role"),
                              "draft": page.input_value("#spec-purpose-" + SHOT),
                              "versions": [int(row.get("version") or 0) for row in rows_after_reload]}
            check("V2.3.8-04", "重新载入最新版本：冲突条变状态行、草稿不动、重读不写库",
                  "已按最新版本 v1" in reloaded_text
                  and ui["reloaded"]["role"] == "status"
                  and ui["reloaded"]["draft"] == PURPOSE_A
                  and ui["reloaded"]["versions"] == [1],
                  ui["reloaded"])

            # ---------------------------------------------------------- 05 再保存 → v2（历史不改写）
            save_button(page, SHOT).click()
            saved = wait_spec_versions(page, SHOT, [1, 2])
            history = {int(row.get("version") or 0): (row.get("payload") or {}).get("purpose")
                       for row in saved}
            ui["history"] = history
            ui["meta_after_save"] = card_meta(page, SHOT)
            still_conflict = page.locator("#spec-save-conflict-" + SHOT).count()
            check("V2.3.8-05", "再保存按新版本追加 v2（值=A），v1 历史仍是 B，冲突条消失",
                  list(history.keys()) == [1, 2] and history.get(1) == PURPOSE_B
                  and history.get(2) == PURPOSE_A
                  and "规格 v2" in ui["meta_after_save"]
                  and still_conflict == 0,
                  {"history": history, "meta": ui["meta_after_save"], "conflict_nodes": still_conflict})

            # ---------------------------------------------------------- 06 无关图隔离
            other_rows = spec_rows(page, OTHER_SHOT)
            ui["other"] = {"versions": [int(row.get("version") or 0) for row in other_rows],
                           "meta": card_meta(page, OTHER_SHOT)}
            check("V2.3.8-06", "无关图隔离：另一张图没有规格记录、卡片仍是「默认（未保存）」",
                  ui["other"]["versions"] == [] and ui["other"]["meta"] == "默认（未保存）",
                  ui["other"])

            png_path = EVIDENCE_DIR / f"v2.3.8-spec-save-occ-{stamp}{'-' + args.label if args.label else ''}.png"
            page.screenshot(path=str(png_path), full_page=True)
            screenshots.append(png_path.relative_to(ROOT).as_posix())
            context.close()
    except Exception as error:  # noqa: BLE001 —— 验证器自己收口：异常也落证据
        crash = type(error).__name__ + ": " + str(error)
    finally:
        server.stop()

    check("V2.3.8-99", "整套流程未异常中断", crash is None, {"error": crash})
    check("V2.3.8-07", "整套流程零 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:5], "page": page_errors[:5]})

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明规格保存的 OCC 合同：两个标签页对同一张图并发保存时，后写者被稳定错误码拦下，"
        "界面说清「已被保存为哪一版」、用户的草稿原样保留、库里不被覆盖也不假称成功；"
        "「重新载入最新版本」只换基版本（不写库），再保存按新版本追加，旧版本历史不被改写，"
        "无关图的规格与卡片不受影响。全程 0 次真实模型调用、0 付费。"
        "不证明：公共风格的同一冲突路径（同一实现与文案，另有保存入口）、出图质量与交付验收。"
    )
    report = {
        "task": "V2.3.8",
        "suite_id": "v2.3.8-spec-save-occ",
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
    json_path = EVIDENCE_DIR / f"v2.3.8-spec-save-occ-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.8-spec-save-occ-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.8 spec save OCC conflict",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 (offline page flow, no provider call)",
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
    print("V2.3.8 规格保存 OCC 冲突验证")
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
