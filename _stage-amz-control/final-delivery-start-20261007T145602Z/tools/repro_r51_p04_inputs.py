"""包04页面repro：输入owner保存恢复 + 无关shot不锁。

验收行（设计 §11.2 包04）：人工资料/事实/用途/规格从同一owner保存恢复；
消费尺寸的shot受阻而无关shot不锁；旧分析只记录原source不应用到新输入。

路径（独立Chrome无头临时profile，离线fake，不花钱）：
1. 新建项目 → 填资料 → 上传参考图 → 确认事实槽位 → 生成推荐方案
2. 刷新页面 → 断言：事实/方案/规格从同一owner恢复（IDB版本一致）
3. 控制：零模型外呼 + 零console错误
"""
from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from v2_test_server import start as start_server  # noqa: E402

spec = importlib.util.spec_from_file_location("stage_nav", TOOLS / "v2_stage_nav.py")
stage_nav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_nav)


def png_bytes():
    width, height, color = 16, 16, (36, 92, 160)
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


IDB_READ = """
async () => {
  const db = await new Promise((resolve) => {
    const q = indexedDB.open("amz-listing-kit-v2");
    q.onsuccess = () => resolve(q.result);
  });
  const getAll = (store) => new Promise((resolve, reject) => {
    const q = db.transaction(store, "readonly").objectStore(store).getAll();
    q.onsuccess = () => resolve(q.result);
    q.onerror = () => reject(q.error);
  });
  const projects = await getAll("projects");
  const documents = await getAll("documents");
  db.close();
  const byKind = {};
  for (const row of documents) {
    const key = row.kind + "/" + row.document_id;
    if (!byKind[key] || byKind[key].version < row.version) byKind[key] = { version: row.version, payload: row.payload };
  }
  return { projects: projects.map((p) => p.project_id), heads: byKind };
}
"""


def await_editor_dimension(editor) -> bool:
    try:
        editor.locator(".dimension-editor").wait_for(state="visible", timeout=2000)
        return True
    except Exception:
        return False


def fill_dimension(editor) -> None:
    editor.locator("button:has-text(\"添加测量\")").click(timeout=5000)
    row = editor.locator(".dimension-row").last
    row.locator("[data-dimension-field]").first.fill("测试对象")
    for field, value in (("value", "10"), ("unit", "cm"), ("source_basis", "人工填写")):
        try:
            row.locator(f'[data-dimension-field="{field}"]').fill(value, timeout=3000)
        except Exception:
            continue

def confirm_all_facts(page) -> tuple[int, str]:
    """填值并确认全部待处理事实；返回（点击次数，进度文案）。"""
    stage_nav.goto(page, "understand")
    print("STEP goto understand", flush=True)
    confirmed = 0
    for round in range(14):
        clicked = page.evaluate("""() => {
          const rows = [...document.querySelectorAll("#slot-list .slot-row")];
          const row = rows.find((r) => [...r.querySelectorAll(".slot-actions button")]
            .some((b) => b.offsetParent !== null && (b.textContent.trim() === "确认" || b.textContent.trim() === "填值并确认")));
          if (!row) return { done: true };
          [...row.querySelectorAll(".slot-actions button")]
            .find((b) => b.offsetParent !== null && (b.textContent.trim() === "确认" || b.textContent.trim() === "填值并确认")).click();
          return { done: false, slot: row.dataset.slotId || "" };
        }""")
        print(f"STEP round {round} {clicked}", flush=True)
        if clicked.get("done"):
            break
        page.wait_for_timeout(500)
        filled = page.evaluate("""() => {
          const editor = document.querySelector(".slot-editor");
          if (!editor) return "direct-confirm";
          const dim = editor.querySelector(".dimension-editor");
          if (dim) {
            const row = dim.querySelector(".dimension-row");
            if (!row) return "dimension-no-row";
            const set = (name, value) => {
              const el = row.querySelector(`[data-dimension-field="${name}"]`);
              if (!el) return;
              el.focus(); el.value = value;
              el.dispatchEvent(new Event("input", { bubbles: true }));
              el.dispatchEvent(new Event("change", { bubbles: true }));
            };
            set("object", "杯身"); set("axis", "height"); set("value", "10"); set("unit", "cm"); set("source_basis", "人工填写");
            const submit = [...editor.querySelectorAll("button")]
              .find((b) => b.textContent.trim() === "确认" || b.textContent.trim() === "保存");
            if (!submit) return "no-submit";
            submit.click();
            return "dimension-clicked";
          }
          const input = editor.querySelector("#slot-editor-value");
          if (input && (input.tagName === "INPUT" || input.tagName === "TEXTAREA")) {
            input.focus(); input.value = "测试值";
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
          }
          const submit2 = [...editor.querySelectorAll("button")]
            .find((b) => b.textContent.trim() === "确认" || b.textContent.trim() === "保存");
          if (!submit2) return "no-submit";
          submit2.click();
          return "clicked";
        }""")
        print(f"STEP fill {filled}", flush=True)
        page.wait_for_timeout(500)
        confirmed += 1
    return confirmed, page.locator("#slots-progress").inner_text()

def main() -> int:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415
    server, base = start_server()
    checks: list[dict] = []
    console_errors: list[str] = []
    network_posts: list[str] = []

    def record(check_id: str, title: str, ok: bool, detail="") -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + check_id + " " + title
              + ("" if ok else " :: " + str(detail)[:300]))

    try:
        with tempfile.TemporaryDirectory(prefix="amz-r51p04-") as workdir:
            profile = str(Path(workdir) / "profile")
            ref = Path(workdir) / "ref.png"
            ref.write_bytes(png_bytes())
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    profile, headless=True, viewport={"width": 1280, "height": 980})
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.on("console", lambda m: console_errors.append(m.text[:200])
                            if m.type == "error" else None)
                    page.on("request", lambda r: network_posts.append(r.url)
                            if r.method == "POST" and "/api/v2/" in r.url else None)
                    page.goto(base + "/", wait_until="networkidle")
                    page.fill("#new-project-name", "包04输入owner")
                    page.click("#create-project")
                    page.wait_for_selector("#project-view:not([hidden])", timeout=15000)
                    page.set_input_files("#ref-file", str(ref))
                    page.wait_for_selector("#ref-list .ref-row", timeout=15000)
                    page.fill("#intake-name", "便携保温杯")
                    page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
                    page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
                    page.wait_for_timeout(1500)
                    # “自己填写商品事实”在资料阶段（intake），点后切理解阶段确认
                    stage_nav.goto(page, "intake")
                    page.click("#manual-facts")
                    confirmed, progress = confirm_all_facts(page)
                    record("R51P04-01", "事实槽位确认保存", "待处理 0 项" in progress,
                           {"confirmed_clicks": confirmed, "progress": progress})
                    stage_nav.goto(page, "plan")
                    page.click("#suite-seed")
                    page.wait_for_selector("#shot-list .shot-row", timeout=15000)
                    shot_count = page.locator("#shot-list .shot-row").count()
                    record("R51P04-02", "推荐方案生成shot行", shot_count >= 1, shot_count)
                    before = page.evaluate(IDB_READ)
                    page.reload(wait_until="networkidle")
                    page.wait_for_selector("#project-view:not([hidden])", timeout=15000)
                    stage_nav.goto(page, "plan")
                    page.wait_for_selector("#shot-list .shot-row", timeout=15000)
                    after = page.evaluate(IDB_READ)
                    same = True
                    for key, head in before["heads"].items():
                        if key.startswith("fact_slot/") or key in ("suite_plan/suite", "product_input/intake"):
                            if after["heads"].get(key, {}).get("version") != head["version"]:
                                same = False
                    record("R51P04-03", "刷新后输入owner恢复一致",
                           same and page.locator("#shot-list .shot-row").count() == shot_count,
                           {"shots_before": shot_count,
                            "shots_after": page.locator("#shot-list .shot-row").count()})
                    record("R51P04-04", "无模型外呼（离线fake）", len(network_posts) == 0, network_posts[:5])
                    record("R51P04-05", "零console错误", len(console_errors) == 0, console_errors[:5])
                    # R51P04-06：尺寸缺位只锁尺寸图，主图不受影响
                    stage_nav.goto(page, "understand")
                    page.click("#slots-toggle")
                    page.wait_for_selector('#slot-list .slot-row[data-slot-id="size_dimensions"]', timeout=15000)
                    marked = page.evaluate("""() => {
                      const row = [...document.querySelectorAll("#slot-list .slot-row")]
                        .find((r) => r.dataset.slotId === "size_dimensions");
                      if (!row) return "no-row";
                      const btn = [...row.querySelectorAll("button")].find((b) => b.textContent.trim() === "标记未知");
                      if (!btn) return "no-btn";
                      btn.click();
                      return "clicked";
                    }""")
                    page.wait_for_timeout(800)
                    stage_nav.goto(page, "plan")
                    page.wait_for_selector("#shot-list .shot-row", timeout=15000)
                    states = page.evaluate("""() => [...document.querySelectorAll("#shot-list .shot-row")].map((r) => ({
                      id: r.dataset.shotId || "", blocked: r.dataset.blocked || "",
                    }))""")
                    size_rows = [s for s in states if "size" in s["id"]]
                    main_rows = [s for s in states if "main" in s["id"]]
                    iso_ok = (marked == "clicked" and len(size_rows) == 1 and size_rows[0]["blocked"] == "true"
                              and len(main_rows) == 1 and main_rows[0]["blocked"] == "false")
                    record("R51P04-06", "尺寸缺位只锁尺寸图", iso_ok,
                           {"marked": marked, "states": states})
                finally:
                    context.close()
    finally:
        server.shutdown()
        server.server_close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "evals" / "product-v2"
    txt_path = out_dir / f"v2.r51p04-input-owner-{stamp}.txt"
    json_path = out_dir / f"v2.r51p04-input-owner-{stamp}.json"
    ok = all(c["ok"] for c in checks)
    report = {"task": "V2.R5.1 packet 04", "suite": "r51p04-input-owner",
              "status": "pass" if ok else "fail", "checks": checks,
              "console_errors": console_errors, "network_posts": network_posts[:10]}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text("\n".join(
        [f"R51P04 输入owner页面repro {stamp} status={report['status']}"]
        + [f"{c['id']} {'PASS' if c['ok'] else 'FAIL'} {c['title']} {c['detail']}" for c in checks]),
        encoding="utf-8")
    print("证据：" + str(txt_path))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
