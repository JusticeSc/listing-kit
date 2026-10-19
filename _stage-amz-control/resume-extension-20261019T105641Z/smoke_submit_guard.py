"""Throwaway: exercise the actual live verifier route guard against a local HTTP receiver."""
from __future__ import annotations
import ast
import hashlib
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("single-submit-guard-smoke.json")
SOURCE = ROOT / "tools" / "verify_v2_4_5_live_reference.py"
source = SOURCE.read_bytes()
tree = ast.parse(source, filename=str(SOURCE))
names = {"payload_of", "guard_submit"}
functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names), "The actual verifier guard must have one implementation."
state = {"authorized": False, "forwarded": 0, "blocked": []}
namespace = {"json": json, "submit_gate": state}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
received: list[dict] = []

class Receiver(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<!doctype html><title>Local guard receiver</title>")

    def do_POST(self):
        received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"received":true}')

server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
result = {"actual_guard_source_sha256": hashlib.sha256(source).hexdigest(),
          "no_real_providers_constructed": True, "supplier_calls": 0, "checks": []}
fetch = """async (body) => {
  try {
    const response = await fetch('/api/v2/images/submit', {method:'POST',
      headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    return {received:response.ok,status:response.status};
  } catch (error) { return {received:false,error:String(error)}; }
}"""
try:
    with tempfile.TemporaryDirectory(prefix="amz-b13-guard-") as work:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(Path(work) / "profile"), headless=True,
                executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe")
            try:
                page = context.pages[0]
                page.route("**/api/v2/images/submit", namespace["guard_submit"])
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                rows = result["checks"]
                rows.append(page.evaluate(fetch, {"action_id":"act-before-confirm", "n":1}))
                state["authorized"] = True
                rows.append(page.evaluate(fetch, {"action_id":"act-two-images", "n":2}))
                rows.append(page.evaluate(fetch, {"action_id":"act-only-forwarded", "n":1}))
                rows.append(page.evaluate(fetch, {"action_id":"act-extra-submit", "n":1}))
                state["authorized"] = False
                rows.append(page.evaluate(fetch, {"action_id":"act-after-confirm", "n":1}))
                assert [row["received"] for row in rows] == [False, False, True, False, False]
                assert state["forwarded"] == 1 and len(state["blocked"]) == 4
                assert received == [{"action_id":"act-only-forwarded", "n":1}]
                result["passed"] = True
            finally:
                context.close()
except Exception as error:
    result["passed"] = False
    result["error"] = str(error)
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    result.update({"guard":state, "actual_http_received":received})
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False))
sys.exit(0 if result.get("passed") else 1)
