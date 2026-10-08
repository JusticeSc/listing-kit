from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.product_v2_server import create_product_v2_server
from playwright.sync_api import expect, sync_playwright
import httpx2 as httpx

ARTIFACTS = Path(__file__).parent
ASSET = ROOT / "_working/amz-listing-kit-product-v2/walkthrough-assets/food/honey-jar-antique.jpg"
ASSET_HASH = "c024b7cf2b04d39601a5146664879a5aff8d3fe4cb98b4990bda4c3ae6594461"
RESERVATION_ID = "vision-ui-20261005-single-call"
LIVE = "--send" in sys.argv
REPLAY = "--offline-send" in sys.argv
EXECUTE = LIVE or REPLAY
key = "sk-offline-vision-body-smoke" if REPLAY else os.environ.get("DASHSCOPE_API_KEY", "")
if not key:
    raise SystemExit("missing_prereq: approved process credential absent; no model request")
assert hashlib.sha256(ASSET.read_bytes()).hexdigest() == ASSET_HASH, "licensed asset hash mismatch"
os.environ["AMZ_V2_DEFAULT_TRIAL"] = "closed"
ledger = json.loads((ROOT / "_working/amz-listing-kit-product-v2/budget-ledger.json").read_text(encoding="utf-8"))
if LIVE:
    reservation = next((r for r in ledger["reservations"] if r.get("id") == RESERVATION_ID), None)
    assert reservation and reservation["status"] == "reserved" and reservation["calls"] == 1
    assert reservation["reserve_cny"] >= 0.23 and ledger["total_reserved_cny"] <= ledger["budget_cap_cny"]
    assert ledger["spent_calls"]["image"] == 8
    assert ledger["spent_calls"]["semantic_vlm"] + 1 <= ledger["count_cap"]["semantic_vlm_max"]

result = {"NOT-AUTHORITY": "point-in-time UI and outbound evidence", "mode": "offline-replay" if REPLAY else ("live" if LIVE else "preflight"), "observed_at": datetime.now(timezone.utc).isoformat(), "model_calls": 0, "status": "started", "asset_sha256": ASSET_HASH, "upstream": [], "local_posts": [], "page_errors": []}
original_send = httpx.Client.send
if REPLAY:
    from tools.verify_v2_2_2_semantic_provider import ReplayTransport
    replay = ReplayTransport()

def guarded_send(client, request, *args, **kwargs):
    if not EXECUTE or result["upstream"]:
        raise RuntimeError("Outbound denied: no authorized single-call slot")
    assert str(request.url) == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert request.method == "POST"
    body = json.loads(request.content)
    assert body["model"] == "qwen-vl-max" and body["max_tokens"] == 5000
    images = []
    for message in body["messages"]:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") == "image_url":
                uri = part["image_url"]["url"]
                assert uri.startswith("data:image/jpeg;base64,")
                raw = base64.b64decode(uri.split(",", 1)[1], validate=True)
                images.append({"media_type": "image/jpeg", "byte_size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    assert len(images) == 1 and images[0]["sha256"] == ASSET_HASH
    result["upstream"].append({"url": str(request.url), "method": request.method, "model": body["model"], "max_tokens": body["max_tokens"], "images": images, "response_format": body.get("response_format")})
    if REPLAY:
        payload = replay._handle(request).json()
        payload["model"] = "qwen-vl-max"
        response = httpx.Response(200, json=payload, request=request)
        result["upstream"][-1]["transport"] = "offline-replay-no-network"
    else:
        result["model_calls"] += 1
        response = original_send(client, request, *args, **kwargs)
    result["upstream"][-1]["http_status"] = response.status_code
    return response

httpx.Client.send = guarded_send
from src.providers import v2_dashscope_vision_semantic as vision_adapter
original_chat_factory = vision_adapter.default_chat_model
def checked_chat_factory(**kwargs):
    model = original_chat_factory(**kwargs)
    assert model.root_client._client.send.__func__ is guarded_send, "SDK transport is not under the single-call guard"
    result["sdk_dispatch"] = "httpx2.Client.send guarded before invocation"
    return model
vision_adapter.default_chat_model = checked_chat_factory
server = create_product_v2_server("127.0.0.1", 0)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{server.server_address[1]}"
result["origin"] = base
snapshot_js = """async () => {
  const db = await new Promise((resolve,reject) => { const r=indexedDB.open('amz-listing-kit-v2'); r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error); });
  try { const tx=db.transaction(['projects','documents','assets'],'readonly'); const rows=await Promise.all(['projects','documents','assets'].map(name=>new Promise((resolve,reject)=>{const r=tx.objectStore(name).getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);}))); return {projects:rows[0],documents:rows[1],assets:rows[2].map(({blob,...meta})=>meta),localStorage:{...localStorage}}; } finally {db.close();}
}"""
try:
    with tempfile.TemporaryDirectory(prefix="amz-vision-ui-headless-") as profile, sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(profile, channel="chrome", headless=True, viewport={"width": 1440, "height": 900}, accept_downloads=True)
        try:
            page = context.pages[0]
            page.on("pageerror", lambda error: result["page_errors"].append(type(error).__name__))
            def local_request(request):
                if request.method == "POST":
                    headers = request.all_headers()
                    entry = {"path": request.url.removeprefix(base), "semantic_provider": headers.get("x-amz-listing-provider-semantic"), "byok_supplied": bool(headers.get("x-amz-listing-key-semantic"))}
                    if entry["path"] == "/api/v2/semantic/analyze":
                        body = request.post_data_json
                        entry["body_keys"] = sorted(body)
                        entry["product_name"] = body.get("product_name")
                    result["local_posts"].append(entry)
            page.on("request", local_request)
            page.goto(base, wait_until="networkidle")
            expect(page.locator("#create-project")).to_be_enabled()
            page.fill("#new-project-name", "公开许可蜂蜜罐图文辅助")
            page.click("#create-project")
            expect(page.locator("#project-view")).to_be_visible()
            page.click("#model-settings-open")
            page.select_option("#model-provider-semantic", "dashscope-vision")
            page.locator("#model-settings-form input[type=password]").first.fill(key)
            page.click("#model-settings-apply")
            expect(page.locator("#model-settings-dialog")).not_to_be_visible()
            page.set_input_files("#ref-file", ASSET)
            expect(page.locator("#ref-list .ref-row")).to_have_count(1)
            page.fill("#intake-name", "带金属盖的玻璃蜂蜜罐")
            page.fill("#intake-description", "请结合商品图片识别可见外观。品牌、精确尺寸、容量未提供，不猜测。最多提出六个可追溯槽位，由人工确认。")
            page.locator("#intake-description").press("Tab")
            expect(page.locator("#analyze-run")).to_be_enabled(timeout=20000)
            expect(page.locator("#intake-draft")).to_contain_text("已保存", timeout=20000)
            result["capabilities"] = page.evaluate("async () => {const headers={'X-AMZ-Listing-Provider-Semantic':'dashscope-vision'}; const r=await fetch('/api/v2/capabilities',{headers});const v=await r.json();return {default_trial:v.default_trial,semantic:v.semantic,provider:v.provider,analyze_fields:v.analyze_fields};}")
            result["password_inputs_cleared"] = page.locator("#model-settings-form input[type=password]").evaluate_all("inputs=>inputs.every(i=>i.value==='')")
            assert result["password_inputs_cleared"]
            if not EXECUTE:
                assert not result["local_posts"] and result["model_calls"] == 0
                result["status"] = "preflight_ready_no_model_call"
                page.screenshot(path=str(ARTIFACTS / "vision-ui-preflight.png"), full_page=True)
            else:
                with page.expect_response(lambda response: response.url == base + "/api/v2/semantic/analyze", timeout=90000) as response_info:
                    page.click("#analyze-run")
                response = response_info.value
                result["gateway_status"] = response.status
                result["envelope"] = response.json()
                page.wait_for_function("() => !document.getElementById('analyze-run').disabled", timeout=20000)
                page.click('[data-stage-nav="understand"]')
                snapshot = page.evaluate(snapshot_js)
                encoded = json.dumps(snapshot, ensure_ascii=False)
                assert key not in encoded, "secret detected in persistent projection"
                result["snapshot"] = snapshot
                result["result_text"] = page.locator("#analyze-result").text_content()
                result["error_text"] = page.locator("#analyze-error").text_content()
                assert key not in page.locator("body").inner_text(), "secret detected in visible UI"
                assert result["model_calls"] == (1 if LIVE else 0) and len(result["upstream"]) == 1 and len(result["local_posts"]) == 1
                assert response.status == 200 and result["envelope"]["ok"] is True, "proposal failed; no retry"
                proposal = result["envelope"]["proposal"]
                assert proposal["meta"]["provider_id"] == "dashscope-vision" and proposal["meta"]["reference_images_sent"] is True
                assert proposal["slots"] and all(slot["status"] == "proposed" and slot["source"] == "model_inference" and slot["evidence"] for slot in proposal["slots"])
                records = [doc for doc in snapshot["documents"] if doc["kind"] == "semantic_analysis"]
                assert records and records[-1]["payload"]["state"] == "succeeded" and records[-1]["payload"]["disposition"] == "applied"
                assert not result["page_errors"]
                result["status"] = "offline_body_limit_ui_smoke" if REPLAY else "live_legal_proposal_saved_no_auto_confirmation"
                page.screenshot(path=str(ARTIFACTS / ("vision-ui-offline.png" if REPLAY else "vision-ui-live.png")), full_page=True)
        finally:
            if result["status"] == "started":
                result["failure_ui"] = page.evaluate("() => ({bootError:document.getElementById('boot-error').textContent,bootPending:document.getElementById('boot-pending').hidden,homeError:document.getElementById('home-error').textContent,homeReadError:document.getElementById('home-read-error').textContent,createDisabled:document.getElementById('create-project').disabled})")
            context.close()
except Exception as error:
    result["status"] = "failed"
    result["error_kind"] = type(error).__name__
    trace = error.__traceback__
    while trace is not None:
        if Path(trace.tb_frame.f_code.co_filename).resolve() == Path(__file__).resolve():
            result["error_line"] = trace.tb_lineno
        trace = trace.tb_next
finally:
    server.shutdown()
    server.server_close()
    httpx.Client.send = original_send
    vision_adapter.default_chat_model = original_chat_factory
    if REPLAY:
        replay.client.close()
    label = "offline" if REPLAY else ("live" if LIVE else "preflight")
    (ARTIFACTS / f"vision-ui-{label}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "model_calls": result["model_calls"], "upstream_status": [r.get("http_status") for r in result["upstream"]], "error_kind": result.get("error_kind"), "evidence": f"_stage-amz-control/formal-development-20261005/vision-ui-{label}.json"}, ensure_ascii=False))
raise SystemExit(1 if result["status"] == "failed" else 0)
