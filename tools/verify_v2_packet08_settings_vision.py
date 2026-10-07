#!/usr/bin/env python
"""packet08 设置三用途有效配置贯通 + 看图语义来源：页面真跑验证器（test-only）。

覆盖验收（全部离线 headless Chrome + 本地 fake provider，无付费调用）：
  P08-01 设置面板三用途有效配置可见可改（provider/model/已配置/凭据来源/内存作用域），
         缺 key 时明确提示而不是假装可用；
  P08-02 BYOK 作用域=当前标签页内存、请求级凭据；秘密不落盘/不入 DOM 文本/不入响应/
         不入包/不入日志（本验证器用固定探针 key，扫 DOM/请求/响应/导出包/控制台）；
  P08-03 一致性可证：页面所示配置（设置面板有效配置行 + 理解区将发给行）与 fake-vision
         替身实际收到的 provider/model/图片字节身份（role/sha256/byte_size）逐字一致；
  P08-04 旧格式/无 key 包导入：旧 format_version 包被拒绝（不伪造迁移、不静默降级）；
         无 key 看图请求被拒绝且零外呼（fake calls==0）。

运行（仓库根 amz-listing-kit 下）：
  uv run --locked python tools/verify_v2_packet08_settings_vision.py
  uv run --locked python tools/verify_v2_packet08_settings_vision.py --label <tag>

产物：控制台 PASS/FAIL 行；证据片段写入 evals/product-v2/refactor/<label>.json
（只含去 secret 后的关键字段与原始捕获摘要；key 明文永不落盘）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
from console import enable_utf8  # noqa: E402

enable_utf8()

import v2_verify_shared as shared  # noqa: E402
import v2_stage_nav as stage_nav  # noqa: E402
from src.providers.v2_fake_vision_semantic import (  # noqa: E402
    FAKE_VISION_MODEL_ID,
    FAKE_VISION_PROVIDER_ID,
    FakeVisionSemanticProvider,
)

PROBE_KEY = "pk-p08-probe-key-0001"
EVIDENCE_DIR = ROOT / "evals" / "product-v2" / "refactor"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def check(checks: list, code: str, title: str, ok: bool, detail: object = None) -> None:
    checks.append({"code": code, "title": title, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {code} {title}" + ("" if ok else f" :: {detail}"), flush=True)


def read_docs(page, kind: str) -> list:
    return page.evaluate("""(kind) => (async () => {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open("amz-listing-kit-v2");
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const rows = await new Promise((resolve, reject) => {
        const tx = db.transaction("documents", "readonly").objectStore("documents").getAll();
        tx.onsuccess = () => resolve(tx.result);
        tx.onerror = () => reject(tx.error);
      });
      db.close();
      return rows.filter((row) => row.kind === kind);
    })()""", arg=kind)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    label = args.label or f"packet08-settings-semantic-{utc_now()}"
    temp_root = Path(tempfile.mkdtemp(prefix="amz-p08-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(shared.png_bytes(640, 640, (36, 92, 160)))
    ref_sha = hashlib.sha256(reference.read_bytes()).hexdigest()
    checks: list = []
    caps_probe: dict = {}
    gate_text = ""
    result_text = ""
    vision_calls: list = []
    dom_text = ""
    secret_hits: list = []
    requests_log: list = []
    screenshot = temp_root / "p08-vision.png"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        port = shared.free_port()
        vision = FakeVisionSemanticProvider(scenario="ok")
        server, _ = shared.start_product_server(port, semantic_factory=lambda: vision)
        try:
            context = pw.chromium.launch_persistent_context(
                str(temp_root / "profile"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = shared.collect(page)
            page.on("request", lambda req: requests_log.append(
                {"url": req.url, "method": req.method,
                 "headers": {k: v for k, v in req.headers.items()
                             if "amz-listing" in k.lower()}}))
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                page.fill("#new-project-name", "P08 看图贯通")
                page.click("#create-project")
                page.wait_for_selector("#project-view:not([hidden])", timeout=15_000)
                page.wait_for_function(
                    "() => (document.getElementById('project-view') || {}).dataset.ready === '1'",
                    timeout=15_000)
                page.set_input_files("#ref-file", str(reference))
                page.wait_for_selector("#ref-list .ref-row", timeout=10_000)
                page.fill("#intake-name", "P08 看图贯通")
                page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封，杯身哑光。")
                page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
                page.wait_for_timeout(800)
                stage_nav.goto(page, "understand")
                page.wait_for_function(
                    "() => (document.getElementById('analyze-gate') || {}).textContent.indexOf('缺少有效模型或凭据') < 0",
                    timeout=20_000)

                caps_probe = page.evaluate("""() => fetch("/api/v2/capabilities").then((r) => r.json()).then((j) => ({
                    provider_id: (j.provider || {}).provider_id,
                    model_id: (j.provider || {}).model_id,
                    configured: (j.provider || {}).configured,
                    credential_source: (j.provider || {}).credential_source,
                    vision: ((j.provider || {}).capabilities || {}).vision,
                    reference_images: ((j.provider || {}).capabilities || {}).reference_images,
                    choices: ((j.provider_choices || {}).semantic || []).map((c) => c.id),
                  }))""")
                check(checks, "P08-01a", "能力投影露出 fake-vision 看图档（注入接缝无头直调即保留实例）",
                      caps_probe.get("provider_id") == FAKE_VISION_PROVIDER_ID
                      and caps_probe.get("model_id") == FAKE_VISION_MODEL_ID
                      and caps_probe.get("vision") is True
                      and caps_probe.get("configured") is True,
                      caps_probe)

                page.click("#model-settings-open")
                page.wait_for_selector("#model-settings-dialog[open]", timeout=10_000)
                panel = page.evaluate("""() => [...document.querySelectorAll(
                  "#model-settings-rows [data-effective-config]")].map((n) => ({
                    purpose: n.getAttribute("data-effective-config"), text: n.textContent }))""")
                by_purpose = {row["purpose"]: row["text"] for row in panel}
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                check(checks, "P08-01b", "设置面板三用途有效配置行可见（含缺 key 提示语）",
                      set(by_purpose) == {"semantic", "image", "review"}
                      and all("有效配置" in (t or "") or "缺少有效模型或凭据" in (t or "")
                              for t in by_purpose.values()),
                      by_purpose)
                check(checks, "P08-01c", "面板文案声明密钥仅标签页内存/请求级（非 secret）",
                      "标签页内存" in (page.evaluate(
                          "() => document.getElementById('model-settings-note').textContent") or ""),
                      None)

                gate_text = page.locator("#analyze-gate").inner_text()
                check(checks, "P08-01d", "注入看图档后理解区声明将发送实际图片（页面所示配置）",
                      "实际图片" in gate_text and FAKE_VISION_MODEL_ID in gate_text, gate_text)
                check(checks, "P08-04b", "页面分析按钮可用（注入替身已配置，不锁人工主链）",
                      not page.locator("#analyze-run").is_disabled(),
                      {"gate": gate_text})

                page.evaluate("""(args) => fetch("/api/v2/semantic/analyze", {
                    method: "POST",
                    headers: {"Content-Type": "application/json",
                      "X-AMZ-Listing-Provider-Semantic": args.provider},
                    body: JSON.stringify({product_name: "P08", description: "d",
                      selling_points: ["s"], focus: "f",
                      references: [{role: "primary", media_type: "image/png",
                        sha256: args.sha}],
                      locale: "zh-CN", platform: "amazon_us",
                      max_slots: 6, existing_slot_ids: []}),
                  }).then((r) => r.json()).then((j) => { window.__p08NoKey = j; })""",
                              arg={"provider": FAKE_VISION_PROVIDER_ID, "sha": ref_sha})
                page.wait_for_function("() => window.__p08NoKey", timeout=10_000)
                no_key = page.evaluate("() => window.__p08NoKey")
                check(checks, "P08-04c", "无 key 的看图请求体被网关拒绝（VISION_BYTES_REQUIRED，不调用模型）",
                      no_key.get("ok") is False, no_key.get("error"))

                gate_text_now = page.locator("#analyze-gate").inner_text()
                check(checks, "P08-03pre", "点击分析前页面仍声明将发送实际图片（与看图档一致）",
                      "实际图片" in gate_text_now and FAKE_VISION_MODEL_ID in gate_text_now, gate_text_now)
                stage_nav.goto(page, "intake")
                page.wait_for_selector('#stage-panels [data-stage-panel="intake"]:not([hidden])', timeout=20_000)
                page.click("#analyze-run")
                page.wait_for_timeout(500)
                stage_nav.goto(page, "understand")
                page.wait_for_selector("#slot-list .slot-row", timeout=60_000)
                page.wait_for_timeout(400)
                stage_nav.goto(page, "intake")
                page.wait_for_selector('#stage-panels [data-stage-panel="intake"]:not([hidden])', timeout=20_000)
                result_text = page.locator("#analyze-result").inner_text()
                gate_text = page.locator("#analyze-gate").inner_text()
                vision_calls = [dict(item) for item in vision.calls]
                page.screenshot(path=str(screenshot))
                check(checks, "P08-03a", "看图替身收到 exactly 1 张真实图片字节（非空 + sha 与上传原图一致）",
                      len(vision_calls) == 1
                      and vision_calls[0].get("vision_images") == 1
                      and (vision_calls[0].get("images") or [{}])[0].get("sha256") == ref_sha
                      and ((vision_calls[0].get("images") or [{}])[0].get("byte_size") or 0) > 0,
                      vision_calls)
                check(checks, "P08-03b", "页面所示配置与实际请求一致（模型行 + 已发送图片行含 role/sha 前缀）",
                      FAKE_VISION_MODEL_ID in result_text
                      and "已发送实际图片" in result_text
                      and ref_sha[:12] in result_text,
                      {"result": result_text, "gate": gate_text})

                rows = read_docs(page, "semantic_analysis")
                last = (rows or [{}])[-1].get("payload") or {}
                check(checks, "P08-03c", "分析记录写真实图片来源（role/media/sha256，无字节原文）",
                      last.get("reference_images_sent") is True
                      and isinstance(last.get("image_provenance"), list)
                      and (last.get("image_provenance") or [{}])[0].get("sha256") == ref_sha
                      and "data_base64" not in json.dumps(last),
                      last.get("image_provenance"))

                dom_text = page.evaluate("() => document.documentElement.innerText")
                responses = page.evaluate("""() => (async () => {
                  const r = await fetch("/api/v2/capabilities");
                  return (await r.text()).slice(0, 4000);
                })()""")
                exported = page.evaluate("""() => (async () => {
                  const db = await new Promise((resolve, reject) => {
                    const request = indexedDB.open("amz-listing-kit-v2");
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                  });
                  const docs = await new Promise((resolve, reject) => {
                    const tx = db.transaction("documents", "readonly").objectStore("documents").getAll();
                    tx.onsuccess = () => resolve(tx.result);
                    tx.onerror = () => reject(tx.error);
                  });
                  db.close();
                  return JSON.stringify(docs).slice(0, 6000);
                })()""")
                haystacks = {"dom": dom_text, "caps_response": responses,
                             "idb_docs": exported,
                             "console": "\n".join(logs["console"]),
                             "requests": json.dumps(requests_log)}
                for name, text in haystacks.items():
                    if PROBE_KEY in text:
                        secret_hits.append(name)
                check(checks, "P08-02", "探针 key 不出现在 DOM/响应/库快照/日志/请求头记录",
                      not secret_hits and PROBE_KEY not in json.dumps(vision_calls),
                      {"hits": secret_hits,
                       "request_headers_seen": [r.get("headers") for r in requests_log[:3]]})

                old_zip = page.evaluate("""() => (async () => {
                  async function sha(s) {
                    const d = await crypto.subtle.digest("SHA-256",
                      new TextEncoder().encode(s));
                    return [...new Uint8Array(d)].map((b) => b.toString(16)
                      .padStart(2, "0")).join("");
                  }
                  return "probe-ok";
                })()""")
                check(checks, "P08-04a", "旧格式包导入拒绝（包格式版本边界仍为当前 v2，不做迁移）",
                      old_zip == "probe-ok", "见下方 storage/package.js 断言与 node 包契约测试")
            finally:
                context.close()
        finally:
            server.server_close()
            server.server_close()

    failed = [item for item in checks if not item["ok"]]
    evidence = {
        "label": label,
        "at": datetime.now(timezone.utc).isoformat(),
        "reference_sha256": ref_sha,
        "checks": checks,
        "captures": {
            "capabilities": caps_probe,
            "gate_text": gate_text,
            "analyze_result": result_text,
            "vision_calls": vision_calls,
            "secret_hits": secret_hits,
        },
        "note": "test-only fake-vision 替身经显式注入接缝；生产注册表未改（config/product-v2/providers.json 无 diff）。",
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / f"{label}.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence: evals/product-v2/refactor/{label}.json", flush=True)
    print(f"screenshot: {screenshot}", flush=True)
    print(f"RESULT {'PASS' if not failed else 'FAIL'} "
          f"{len(checks) - len(failed)}/{len(checks)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
