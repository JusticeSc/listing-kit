"""复现 confirm 点击后的 confirm-error / confirm-record。"""
from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import zlib
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
        critical: definition.critical, value: value, source: "user_input",
        status: "confirmed", confidence: null,
        evidence: [{ kind: "user", ref: "v243-seed" }], depends_on: [],
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

PROBE = """
async () => {
  const db = await new Promise((resolve) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
  });
  const read = (store) => new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await read("documents");
  const prompts = {};
  for (const item of documents) {
    if (item.kind !== "prompt_version") continue;
    prompts[item.document_id] = { version: item.version, hash: item.payload.hash };
  }
  db.close();
  return { prompts };
}
"""


def main() -> int:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415
    server, base = start_server()
    try:
        with tempfile.TemporaryDirectory(prefix="amz-repro-") as workdir:
            profile = str(Path(workdir) / "profile")
            ref = Path(workdir) / "ref.png"
            ref.write_bytes(png_bytes())
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    profile, headless=True, viewport={"width": 1280, "height": 980})
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.on("console", lambda message: print("CONSOLE:", message.type, message.text[:200])
                            if message.type in ("error", "warning") else None)
                    page.goto(base + "/", wait_until="networkidle")
                    page.fill("#new-project-name", "复现 confirm")
                    page.click("#create-project")
                    page.wait_for_selector("#project-view:not([hidden])", timeout=15000)
                    page.set_input_files("#ref-file", str(ref))
                    page.wait_for_selector("#ref-list .ref-row", timeout=15000)
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
                    page.evaluate(SEED_SLOTS, project_ids[0])
                    page.reload(wait_until="networkidle")
                    page.click("#suite-seed")
                    page.wait_for_selector("#shot-list .shot-row", timeout=15000)
                    print("shots:", page.locator("#shot-list .shot-row").count())
                    stage_nav.goto(page, "generate")
                    stage_nav.reveal(page, "#prompt-editor")
                    shot_ids = page.evaluate(
                        "() => [...document.querySelectorAll('#prompt-list .shot-spec')]"
                        ".map((n) => n.getAttribute('data-shot-id'))")
                    print("specs:", shot_ids)
                    for shot_id in shot_ids:
                        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
                        page.click(card + " .toolbar button")
                        page.wait_for_selector(card + '[data-prompt-state="saved"]', timeout=15000)
                        page.wait_for_timeout(200)
                    print("compiled:", page.evaluate(PROBE))
                    print("confirm-enabled:", page.locator("#confirm-action").is_enabled())
                    print("confirm-record-before:", repr(page.locator("#confirm-record").inner_text()))
                    page.click("#confirm-action")
                    page.wait_for_timeout(3000)
                    print("confirm-record-after:", repr(page.locator("#confirm-record").inner_text()))
                    print("confirm-error:",
                          repr(page.locator("#confirm-error").inner_text()
                               if page.locator("#confirm-error").is_visible() else "<hidden>"))
                    print("generate-error:",
                          repr(page.locator("#generate-error").inner_text()
                               if page.locator("#generate-error").is_visible() else "<hidden>"))
                    print("confirm-docs:",
                          page.evaluate("async () => { const db = await new Promise((r) => {"
                                        " const q = indexedDB.open(\"amz-listing-kit-v2\");"
                                        " q.onsuccess = () => r(q.result); });"
                                        " const rows = await new Promise((r) => { const q = db"
                                        ".transaction(\"documents\", \"readonly\")"
                                        ".objectStore(\"documents\").getAll();"
                                        " q.onsuccess = () => r(q.result); });"
                                        " db.close(); return rows.filter((x) => x.kind === \"generation_confirm\")"
                                        ".map((x) => [x.document_id, x.version]); }"))
                finally:
                    context.close()
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
