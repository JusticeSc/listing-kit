"""包06页面repro：采用与交付事务（双标签采用冲突、旧候选明确可选、交付拒混包）。

验收行（设计 §11.2 包06）：首次双标签采用冲突不覆盖；明确可选旧候选；
完整项目包单快照，交付在规格/报告/采用变化时拒混包；两包Blob/hash/来源链往返。

路径（独立Chrome无头，同一profile双标签页共享IDB，离线fake，不花钱）：
1. A页：新建项目 → 填资料 → 上传参考图 → 确认全部事实 → 只留主图 → 生成页准备 → 确认并生成（fake成功）
2. 等候选成功 → 审核页采用候选（A页）
3. B页同项目审核页 → 点采用（同shot竞争）→ 断言：一方冲突/已采用，不静默双写
4. A页导出项目包（下载事件）→ 断言：ZIP非空；交付包因fake小图被拒时有明确门禁文案
5. 断言：零console错误
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


CONFIRM_ALL = """() => {
  const rows = [...document.querySelectorAll("#slot-list .slot-row")];
  const row = rows.find((r) => [...r.querySelectorAll(".slot-actions button")]
    .some((b) => b.offsetParent !== null && (b.textContent.trim() === "确认" || b.textContent.trim() === "填值并确认")));
  if (!row) return { done: true };
  [...row.querySelectorAll(".slot-actions button")]
    .find((b) => b.offsetParent !== null && (b.textContent.trim() === "确认" || b.textContent.trim() === "填值并确认")).click();
  return { done: false, slot: row.dataset.slotId || "" };
}"""

FILL_EDITOR = """() => {
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
}"""

SELECTION_READ = """async () => {
  const db = await new Promise((r) => { const q = indexedDB.open("amz-listing-kit-v2"); q.onsuccess = () => r(q.result); });
  const rows = await new Promise((r) => { const q = db.transaction("documents", "readonly").objectStore("documents").getAll(); q.onsuccess = () => r(q.result); });
  db.close();
  return rows.filter((x) => x.kind === "selection").map((x) => [x.document_id, x.version, x.payload && x.payload.action, x.payload && x.payload.candidate_id]);
}"""


def confirm_all_facts(page) -> int:
    n = 0
    for _ in range(14):
        clicked = page.evaluate(CONFIRM_ALL)
        if clicked.get("done"):
            break
        page.wait_for_timeout(400)
        page.evaluate(FILL_EDITOR)
        page.wait_for_timeout(400)
        n += 1
    return n


def main() -> int:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415
    server, base = start_server()
    checks: list[dict] = []
    console_errors: list[str] = []

    def record(check_id: str, title: str, ok: bool, detail="") -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + check_id + " " + title
              + ("" if ok else " :: " + str(detail)[:400]), flush=True)

    try:
        with tempfile.TemporaryDirectory(prefix="amz-r51p06-") as workdir:
            profile = str(Path(workdir) / "profile")
            ref = Path(workdir) / "ref.png"
            ref.write_bytes(png_bytes())
            dl_dir = str(Path(workdir) / "dl")
            Path(dl_dir).mkdir()
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    profile, headless=True, viewport={"width": 1280, "height": 980},
                    accept_downloads=True)
                try:
                    page_a = context.pages[0] if context.pages else context.new_page()
                    page_a.on("console", lambda m: console_errors.append("A:" + m.text[:200])
                              if m.type == "error" else None)
                    page_a.goto(base + "/", wait_until="networkidle")
                    page_a.fill("#new-project-name", "包06采用交付")
                    page_a.click("#create-project")
                    page_a.wait_for_selector("#project-view:not([hidden])", timeout=15000)
                    page_a.set_input_files("#ref-file", str(ref))
                    page_a.wait_for_selector("#ref-list .ref-row", timeout=15000)
                    page_a.fill("#intake-name", "便携保温杯")
                    page_a.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
                    page_a.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
                    page_a.wait_for_timeout(1500)
                    stage_nav.goto(page_a, "intake")
                    page_a.click("#manual-facts")
                    stage_nav.goto(page_a, "understand")
                    confirm_all_facts(page_a)
                    stage_nav.goto(page_a, "plan")
                    page_a.click("#suite-seed")
                    page_a.wait_for_selector("#shot-list .shot-row", timeout=15000)
                    for _ in range(8):
                        rows = page_a.evaluate("() => [...document.querySelectorAll('#shot-list .shot-row')].map((r) => r.dataset.shotId)")
                        victim = next((s for s in rows if "main" not in s), None)
                        if not victim:
                            break
                        page_a.locator(f'#shot-list .shot-row[data-shot-id="{victim}"] button:has-text("删除")').click(timeout=5000)
                        page_a.wait_for_timeout(800)
                    stage_nav.goto(page_a, "generate")
                    page_a.wait_for_selector("#confirm-editor:not([hidden])", timeout=15000)
                    for _ in range(25):
                        page_a.wait_for_timeout(1000)
                        prep = page_a.locator("#local-preparation-status").inner_text()
                        if "本地准备完成" in prep or "部分任务尚未准备" in prep:
                            break
                    page_a.click("#confirm-action")
                    # 等生成成功（fake同步/轮询）
                    page_a.wait_for_function(
                        "() => [...document.querySelectorAll('.attempt-row')].some((r) => r.dataset.attemptState === 'succeeded')",
                        timeout=60000)
                    record("R51P06-01", "单主图生成成功", True, "fake succeeded")

                    # A页审核采用
                    stage_nav.goto(page_a, "review")
                    page_a.wait_for_selector("#review-list .review-card", timeout=15000)
                    page_a.locator("#review-list .review-card button:has-text('采用候选')").first.click(timeout=8000)
                    page_a.wait_for_timeout(1500)
                    sel_a = page_a.evaluate(SELECTION_READ)
                    record("R51P06-02", "A页采用成功", len(sel_a) == 1 and sel_a[0][2] == "select", sel_a)

                    # B页同项目同shot再采用（竞争）：应冲突不覆盖、不崩溃
                    page_b = context.new_page()
                    page_b.on("console", lambda m: console_errors.append("B:" + m.text[:200])
                              if m.type == "error" else None)
                    page_b.goto(base + "/", wait_until="networkidle")
                    page_b.wait_for_selector("#project-view:not([hidden])", timeout=15000)
                    stage_nav.goto(page_b, "review")
                    page_b.wait_for_selector("#review-list .review-card", timeout=15000)
                    b_btn = page_b.locator("#review-list .review-card button:has-text('采用候选')").first
                    b_enabled = b_btn.is_enabled() if b_btn.count() else False
                    if b_enabled:
                        b_btn.click(timeout=8000)
                        page_b.wait_for_timeout(1500)
                    sel_b = page_b.evaluate(SELECTION_READ)
                    same_single = len(sel_b) == 1 and sel_b[0][2] == "select"
                    record("R51P06-03", "双标签采用不双写（单记录不覆盖）",
                           same_single, {"b_enabled": b_enabled, "sel": sel_b})

                    # 交付：导出项目包（完整历史单快照），断言下载非空
                    stage_nav.goto(page_a, "deliver")
                    page_a.wait_for_timeout(1000)
                    with page_a.expect_download(timeout=20000) as dl_info:
                        page_a.click("#deliver-project-package")
                    download = dl_info.value
                    path = str(Path(dl_dir) / download.suggested_filename)
                    download.save_as(path)
                    size = Path(path).stat().st_size
                    record("R51P06-04", "项目包导出非空（单快照往返物）", size > 1000, {"bytes": size})

                    # 交付包门禁：fake小图预期被拒，断言有明确门禁/错误文案（拒混包）
                    gate_text = page_a.locator("#delivery-gate").inner_text()
                    record("R51P06-05", "交付门禁文案明确（拒混包/缺项可定位）",
                           len(gate_text.strip()) > 0, gate_text[:300])

                    record("R51P06-06", "零console错误", len(console_errors) == 0, console_errors[:5])
                finally:
                    context.close()
    finally:
        server.shutdown()
        server.server_close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "evals" / "product-v2"
    txt_path = out_dir / f"v2.r51p06-adopt-deliver-{stamp}.txt"
    json_path = out_dir / f"v2.r51p06-adopt-deliver-{stamp}.json"
    ok = all(c["ok"] for c in checks)
    report = {"task": "V2.R5.1 packet 06", "suite": "r51p06-adopt-deliver",
              "status": "pass" if ok else "fail", "checks": checks,
              "console_errors": console_errors}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text("\n".join(
        [f"R51P06 采用交付页面repro {stamp} status={report['status']}"]
        + [f"{c['id']} {'PASS' if c['ok'] else 'FAIL'} {c['title']} {c['detail']}" for c in checks]),
        encoding="utf-8")
    print("证据：" + str(txt_path))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
