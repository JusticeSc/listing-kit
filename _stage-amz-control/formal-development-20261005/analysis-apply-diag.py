from pathlib import Path
import importlib.util
import json
import socket
import sys
import tempfile
import threading
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402

spec = importlib.util.spec_from_file_location("diag_server", ROOT / "app" / "product_v2_server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
scenario = {"value": "ok"}
server = module.create_product_v2_server("127.0.0.1", port,
    provider_factory=lambda: FakeSemanticProvider(scenario=scenario["value"]))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"
DB_SNAPSHOT = """async () => {
  const db = await new Promise((resolve, reject) => {
    const req = indexedDB.open('amz-listing-kit-v2');
    req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
  });
  const read = (store) => new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readonly');
    const req = tx.objectStore(store).getAll();
    req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
  });
  const result = { documents: await read('documents') };
  db.close();
  return result;
}"""
with tempfile.TemporaryDirectory(prefix="amz-diag-") as tmp:
    profile = Path(tmp) / "profile"
    ref = Path(tmp) / "ref-one.png"
    import struct, zlib
    def png(size, rgb):
        def chunk(t, d):
            c = t + d
            return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    ref.write_bytes(png(12, (30, 90, 160)))
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(profile), headless=True,
            viewport={"width": 1280, "height": 900})
        try:
            page = context.pages[0]
            posts = []
            page.on("request", lambda r: posts.append(r.post_data or "")
                    if r.method == "POST" and "/api/v2/semantic/analyze" in r.url else None)
            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品")
            page.click("#create-project")
            expect(page.locator("#project-view")).to_be_visible()
            page.set_input_files("#ref-file", str(ref))
            expect(page.locator("#ref-list .ref-row")).to_have_count(1)
            page.fill("#intake-name", "便携榨汁杯")
            page.fill("#intake-description", "350ml 便携榨汁杯。")
            page.fill("#intake-selling-points", "一键启动\n可拆洗")
            page.wait_for_timeout(1200)
            page.reload(wait_until="networkidle")
            expect(page.locator("#analyze-run")).to_be_enabled()
            page.click("#analyze-run")
            rows_probe = """() => [...document.querySelectorAll('#slot-list .slot-row')]
                .map((row) => ({ id: row.dataset.slotId, status: row.dataset.status,
                    actions: [...row.querySelectorAll('button')].map((b) => b.textContent) }))"""
            page.wait_for_timeout(500)
            at500 = {"rows": page.evaluate(rows_probe),
                     "result": page.locator("#analyze-result").inner_text()}
            page.wait_for_timeout(2000)
            snapshot = page.evaluate(DB_SNAPSHOT)
            role_probe = {
                "role_exact": page.locator('#slot-list .slot-row[data-slot-id="product_name"]')
                    .get_by_role("button", name="确认", exact=True).count(),
                "role_plain": page.locator('#slot-list .slot-row[data-slot-id="product_name"]')
                    .get_by_role("button", name="确认").count(),
                "buttons": page.evaluate("""() => {
                    const row = document.querySelector('#slot-list .slot-row[data-slot-id="product_name"]');
                    if (!row) return null;
                    return {
                        offsetParentNull: row.offsetParent === null,
                        display: getComputedStyle(row).display,
                        ariaHiddenAncestor: row.closest('[aria-hidden="true"]') !== null,
                        hiddenAncestor: row.closest('[hidden]') !== null,
                        buttons: [...row.querySelectorAll('button')].map((b) => ({
                            text: b.textContent, aria: b.getAttribute('aria-label'),
                            title: b.title, type: b.type,
                            offsetParentNull: b.offsetParent === null,
                        })),
                        ancestors: (() => {
                            const chain = [];
                            let node = row.parentElement;
                            while (node && node !== document.documentElement) {
                                chain.push({
                                    tag: node.tagName, id: node.id, cls: node.className,
                                    hiddenAttr: node.hasAttribute('hidden'),
                                    display: getComputedStyle(node).display,
                                    editable: node.getAttribute('contenteditable'),
                                });
                                node = node.parentElement;
                            }
                            return chain;
                        })(),
                    };
                }"""),
            }
            print(json.dumps({
                "at500": at500,
                "role_probe": role_probe,
                "posts": len(posts),
                "result": page.locator("#analyze-result").inner_text(),
                "error": page.locator("#analyze-error").inner_text(),
                "gate": page.locator("#analyze-gate").inner_text(),
                "rows": page.evaluate(rows_probe),
                "slots": [(d["document_id"], d["payload"].get("status")) for d in snapshot["documents"]
                          if d["kind"] == "fact_slot"],
                "analyses": [(d["payload"].get("state"), d["payload"].get("disposition"),
                              d["payload"].get("error"))
                             for d in snapshot["documents"] if d["kind"] == "semantic_analysis"],
                "page_errors": [],
            }, ensure_ascii=False, indent=2))
        finally:
            context.close()
server.server_close()
