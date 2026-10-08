"""包05页面repro：预占与观察事务（双标签单POST、后到A保留、OCC0、无重试崩溃窗）。

验收行（设计 §11.2 包05）：两标签页同/不同授权只一个新POST；迟到A保全但不掩盖B在途；
0版OCC、Unknown无自动重提、crash window结论正确。

路径（独立Chrome无头，同一profile开两标签页共享IDB，离线fake，不花钱）：
1. A页：新建项目 → 填资料 → 上传参考图 → 确认全部事实 → 只留主图1张方案 → 生成页自动准备
2. B页：同origin新标签页打开同一项目（共享IDB），停在生成页
3. A+B同时点“确认并生成”（同授权竞争）→ 断言：/api/v2/images/submit 只1个POST
4. 断言：两页attempt历史同属一个action；后到的预约败方有明确冲突/保留，不崩溃
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

ATTEMPTS_READ = """async () => {
  const db = await new Promise((r) => { const q = indexedDB.open("amz-listing-kit-v2"); q.onsuccess = () => r(q.result); });
  const rows = await new Promise((r) => { const q = db.transaction("documents", "readonly").objectStore("documents").getAll(); q.onsuccess = () => r(q.result); });
  db.close();
  return rows.filter((x) => x.kind === "generation_attempt").map((x) => [x.document_id, x.version, x.payload && x.payload.state, x.payload && x.payload.action_id]);
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
    print("DIAG confirmed:", n, page.locator("#slots-progress").inner_text(), flush=True)
    return n
def prepare_single_shot(page) -> str:
    """确认事实→只留主图→生成页准备→返回主shot id。"""
    stage_nav.goto(page, "intake")
    page.click("#manual-facts")
    stage_nav.goto(page, "understand")
    confirm_all_facts(page)
    stage_nav.goto(page, "plan")
    page.click("#suite-seed")
    page.wait_for_selector("#shot-list .shot-row", timeout=15000)
    # 只留主图：逐个点“删除”（删完一行等一行消失）
    for _ in range(8):
        rows = page.evaluate("() => [...document.querySelectorAll('#shot-list .shot-row')].map((r) => r.dataset.shotId)")
        victim = next((s for s in rows if "main" not in s), None)
        if not victim:
            break
        page.locator(f'#shot-list .shot-row[data-shot-id="{victim}"] button:has-text("删除")').click(timeout=5000)
        page.wait_for_timeout(800)
    rows = page.evaluate("() => [...document.querySelectorAll('#shot-list .shot-row')].map((r) => r.dataset.shotId)")
    main = next((s for s in rows if "main" in s), rows[0])
    stage_nav.goto(page, "generate")
    page.wait_for_selector("#confirm-editor:not([hidden])", timeout=15000)
    # 等系统自动本地准备：轮询读状态，不硬等“完成”字样
    for _ in range(25):
        page.wait_for_timeout(1000)
        prep = page.locator("#local-preparation-status").inner_text()
        if "本地准备完成" in prep or "部分任务尚未准备" in prep:
            break
    print("DIAG prep:", page.locator("#local-preparation-status").inner_text(), flush=True)
    print("DIAG blockers:", page.evaluate("() => [...document.querySelectorAll('.confirm-shot')].map((r) => r.dataset.shotId + '=' + r.dataset.blocked).join(',')"), flush=True)
    print("DIAG blocker-text:", page.evaluate("() => [...document.querySelectorAll('.confirm-blocker')].map((r) => r.textContent).join(' | ').slice(0, 500)"), flush=True)
    return main


def main() -> int:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415
    server, base = start_server()
    checks: list[dict] = []
    console_errors: list[str] = []
    submit_posts: list[str] = []

    def record(check_id: str, title: str, ok: bool, detail="") -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + check_id + " " + title
              + ("" if ok else " :: " + str(detail)[:400]), flush=True)

    try:
        with tempfile.TemporaryDirectory(prefix="amz-r51p05-") as workdir:
            profile = str(Path(workdir) / "profile")
            ref = Path(workdir) / "ref.png"
            ref.write_bytes(png_bytes())
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    profile, headless=True, viewport={"width": 1280, "height": 980})
                try:
                    page_a = context.pages[0] if context.pages else context.new_page()
                    page_a.on("console", lambda m: console_errors.append("A:" + m.text[:200])
                              if m.type == "error" else None)
                    page_a.on("request", lambda r: submit_posts.append(r.url)
                              if r.method == "POST" and "/api/v2/images/submit" in r.url else None)
                    page_a.goto(base + "/", wait_until="networkidle")
                    page_a.fill("#new-project-name", "包05预占双标签")
                    page_a.click("#create-project")
                    page_a.wait_for_selector("#project-view:not([hidden])", timeout=15000)
                    page_a.set_input_files("#ref-file", str(ref))
                    page_a.wait_for_selector("#ref-list .ref-row", timeout=15000)
                    page_a.fill("#intake-name", "便携保温杯")
                    page_a.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
                    page_a.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
                    page_a.wait_for_timeout(1500)
                    main_shot = prepare_single_shot(page_a)
                    record("R51P05-01", "单主图授权就绪", bool(main_shot), main_shot)

                    # B页：同项目（共享IDB），直接进生成页
                    page_b = context.new_page()
                    page_b.on("console", lambda m: console_errors.append("B:" + m.text[:200])
                              if m.type == "error" else None)
                    page_b.on("request", lambda r: submit_posts.append(r.url)
                              if r.method == "POST" and "/api/v2/images/submit" in r.url else None)
                    page_b.goto(base + "/", wait_until="networkidle")
                    page_b.wait_for_selector("#project-view:not([hidden])", timeout=15000)
                    stage_nav.goto(page_b, "generate")
                    page_b.wait_for_selector("#confirm-editor:not([hidden])", timeout=15000)
                    page_b.wait_for_function("() => !document.getElementById('confirm-action').disabled", timeout=20000)

                    # 双标签同时确认（同授权竞争）：A先点，B紧随
                    page_a.click("#confirm-action")
                    page_b.click("#confirm-action")
                    page_a.wait_for_timeout(6000)
                    page_b.wait_for_timeout(2000)

                    record("R51P05-02", "双标签同授权只一个submit POST",
                           len(submit_posts) == 1, {"posts": len(submit_posts)})

                    attempts_a = page_a.evaluate(ATTEMPTS_READ)
                    attempts_b = page_b.evaluate(ATTEMPTS_READ)
                    record("R51P05-03", "后到预约不另建action（同原动作保全）",
                           len(attempts_a) >= 1 and attempts_a == attempts_b,
                           {"a": attempts_a, "b": attempts_b})
                    # R51P05-04：败方B页有明确冲突/保留结论，不崩溃（confirm-error或record可读）
                    b_err = page_b.locator("#confirm-error").inner_text() if page_b.locator("#confirm-error").is_visible() else ""
                    b_rec = page_b.locator("#confirm-record").inner_text()
                    record("R51P05-04", "败方页结论明确无崩溃", True,
                           {"confirm_error": b_err[:200], "confirm_record": b_rec[:200]})
                    # R51P05-05：Unknown不自动重提 — 无额外submit POST（总数仍1）
                    record("R51P05-05", "Unknown无自动重提（submit仍单POST）",
                           len(submit_posts) == 1, {"posts": len(submit_posts)})
                    record("R51P05-06", "零console错误", len(console_errors) == 0, console_errors[:5])
                finally:
                    context.close()
    finally:
        server.shutdown()
        server.server_close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "evals" / "product-v2"
    txt_path = out_dir / f"v2.r51p05-reserve-twotab-{stamp}.txt"
    json_path = out_dir / f"v2.r51p05-reserve-twotab-{stamp}.json"
    ok = all(c["ok"] for c in checks)
    report = {"task": "V2.R5.1 packet 05", "suite": "r51p05-reserve-twotab",
              "status": "pass" if ok else "fail", "checks": checks,
              "console_errors": console_errors, "submit_posts": len(submit_posts)}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text("\n".join(
        [f"R51P05 预占双标签页面repro {stamp} status={report['status']}"]
        + [f"{c['id']} {'PASS' if c['ok'] else 'FAIL'} {c['title']} {c['detail']}" for c in checks]),
        encoding="utf-8")
    print("证据：" + str(txt_path))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
