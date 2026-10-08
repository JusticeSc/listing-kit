#!/usr/bin/env python
"""V2.4.5 证据：一笔预算内的真实参考图闭环（1 次真实 qwen-image 提交）。

只在显式 ``--live`` 且环境里存在 ``DASHSCOPE_API_KEY`` 时运行；默认不执行、不产生证据、不接 CI。
预算（§12.2 成本纪律）：1 次 submit + 有界 status 轮询 + 1 次 result 取回；语义槽位由验证器直接
播种，0 次语义调用。真实参考图默认取 Product V1 真实运行里留下的商品原图（路径与 sha256 写进证据）。

检查：
  1) 图像 provider 是真实 dashscope-image 且 configured=true（fake-image 切替不算）。
  2) 只提交一次：请求含真实参考图（≥1 张、带 sha256）与非空 Prompt。
  3) 有界轮询到终态 succeeded，task id 出现在状态查询里。
  4) 候选非 Mock：字节从真实响应取回，sha256 三方一致（记录 = 重算 = 响应头），字节数 > 5KB，
     尺寸等于请求尺寸，浏览器里能预览。

运行：
  uv run --locked python tools/verify_v2_4_5_live_reference.py --live
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import tempfile
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
DEFAULT_REFERENCE = (ROOT / "_working" / "amz-listing-kit-product-demo" / "real-run-01"
                     / "workspace" / "inputs" / "originals"
                     / "5c5e0fdde80847dc140af37778678f3e9b3fb7962bba70360e62630501a85629.jpg")

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_server_module():
    spec = importlib.util.spec_from_file_location(
        "product_v2_server_live_under_test", ROOT / "app" / "product_v2_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


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
        evidence: [{ kind: "user", ref: "v245-seed" }], depends_on: [],
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


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.4.5 真实参考图最小闭环验证")
    parser.add_argument("--live", action="store_true",
                        help="确认执行真实调用；没有它只打印用途并退出")
    parser.add_argument("--label", default="")
    parser.add_argument("--reference", default="")
    parser.add_argument("--image-provider", default="",
                        help="覆盖图像 provider id（如 volcengine-ark）；默认走注册表默认")
    parser.add_argument("--shot-index", type=int, default=0)
    parser.add_argument("--poll-limit", type=int, default=40)
    parser.add_argument("--poll-interval", type=float, default=6.0)
    args = parser.parse_args()

    want_volc = args.image_provider.strip() == "volcengine-ark"
    need_key = "ARK_API_KEY" if want_volc else "DASHSCOPE_API_KEY"
    if not args.live or not os.environ.get(need_key, "").strip():
        print(f"未执行：需要 --live 且环境变量 {need_key} 存在。")
        print("本轮没有发出任何真实请求，也没有产生证据文件。")
        return 2
    reference = Path(args.reference) if args.reference else DEFAULT_REFERENCE
    if not reference.is_absolute():
        reference = (ROOT / reference).resolve()
    if not reference.is_file():
        print("参考图不存在：" + str(reference))
        return 2
    reference_sha = sha256_file(reference)
    reference_size = reference.stat().st_size

    import sys as _sys
    _sys.path.insert(0, str(ROOT / "tools"))
    import v2_stage_nav as stage_nav
    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []

    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    module = load_server_module()
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    # 图像 provider 选择：默认走注册表默认（dashscope-image）；
    # --image-provider volcengine-ark 时走火山同步链。这就是本次真实调用本身。
    if args.image_provider.strip():
        os.environ["AMZ_V2_IMAGE_PROVIDER"] = args.image_provider.strip()
    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=None)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    submit_requests: list[dict] = []
    status_requests: list[str] = []
    result_requests: list[dict] = []
    ui: dict = {}
    interrupted: str | None = None
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v245-"))
    profile = temp_root / "profile"

    def chain_of(data: dict, shot_id: str) -> list:
        return data["attempt_chains"].get(shot_id, [])

    def candidate_of(data: dict, shot_id: str) -> list:
        return data["candidate_chains"].get(shot_id, [])

    def row_of(data: dict, shot_id: str) -> dict | None:
        return next((row for row in data["ui"]["rows"] if row["shot_id"] == shot_id), None)

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))

                def payload_of(request) -> dict:
                    try:
                        return json.loads(request.post_data or "{}")
                    except ValueError:
                        return {}

                def on_request(request) -> None:
                    if request.method != "POST":
                        return
                    if "/api/v2/images/submit" in request.url:
                        body = payload_of(request)
                        references = body.get("references") or []
                        submit_requests.append({
                            "action_id": body.get("action_id"),
                            "prompt": body.get("prompt"),
                            "size": body.get("size"),
                            "reference_count": len(references),
                            "reference_sha256": [item.get("sha256") for item in references],
                            "reference_media": [item.get("media_type") for item in references],
                        })
                    elif "/api/v2/images/status" in request.url:
                        status_requests.append(str(payload_of(request).get("task_id")))
                    elif "/api/v2/images/result" in request.url:
                        result_requests.append({
                            "task_id": str(payload_of(request).get("task_id")),
                            "status": None, "declared_sha": "",
                            "provider_id": "", "model_id": "",
                        })

                def on_response(response) -> None:
                    if "/api/v2/images/result" not in response.url:
                        return
                    task_id = str(payload_of(response.request).get("task_id"))
                    for item in reversed(result_requests):
                        if item["task_id"] == task_id and item["status"] is None:
                            item["status"] = response.status
                            item["declared_sha"] = str(
                                response.headers.get("x-image-sha256") or "").lower()
                            item["provider_id"] = str(
                                response.headers.get("x-provider-id") or "")
                            item["model_id"] = str(response.headers.get("x-model-id") or "")
                            break

                page.on("request", on_request)
                page.on("response", on_response)

                def probe() -> dict:
                    return page.evaluate(PROBE)

                def row(shot_id: str):
                    return page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 30_000) -> None:
                    expect(row(shot_id)).to_have_attribute(
                        "data-attempt-state", state, timeout=timeout)

                def wait_preview(shot_id: str, timeout: int = 60_000) -> None:
                    page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]'
                        " .attempt-preview img"
                    ).scroll_into_view_if_needed(timeout=timeout)
                    page.wait_for_function(
                        """(shot) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                            const img = node && node.querySelector('.attempt-preview img');
                            return Boolean(img && img.complete && img.naturalWidth > 0);
                        }""", arg=shot_id, timeout=timeout)

                def confirm_generation() -> None:
                    expect(page.locator("#confirm-action")).to_be_enabled()
                    page.click("#confirm-action")
                    # 确认即提交（confirmAndRun 一次保存授权并直接整套提交）：
                    # 等 attempt 行出现（行为判据），不再钉 #confirm-record 实现文案。
                    page.wait_for_function(
                        """() => document.querySelectorAll(
                            '#attempt-list .attempt-row[data-attempt-state]').length > 0""",
                        timeout=30_000)

                def click_row_button(shot_id: str, text: str) -> None:
                    row(shot_id).locator(f'button:has-text("{text}")').first.click()

                def compile_all(shot_ids: list) -> None:
                    stage_nav.goto(page, "generate")
                    for shot_id in shot_ids:
                        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
                        page.locator(card + " .toolbar button").scroll_into_view_if_needed(timeout=10_000)
                        page.click(card + " .toolbar button")
                        page.wait_for_selector(card + '[data-prompt-state="saved"]',
                                               timeout=20_000)
                        page.wait_for_timeout(200)

                def results_for(task_id: str) -> list:
                    return [item for item in result_requests
                            if item["task_id"] == task_id]

                # ---------------- 项目准备（0 次语义调用：槽位直接播种） ----------------
                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "真实闭环 · 参考图")
                page.click("#create-project")
                expect(page.locator("#project-view")).to_be_visible()
                stage_nav.goto(page, "intake")
                page.set_input_files("#ref-file", str(reference))
                expect(page.locator("#ref-list .ref-row")).to_have_count(1, timeout=30_000)
                page.fill("#intake-name", "便携保温杯")
                page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
                page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
                page.wait_for_timeout(1500)
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
                stage_nav.goto(page, "plan")
                page.click("#suite-seed")
                expect(page.locator("#shot-list .shot-row")).to_have_count(4)
                stage_nav.goto(page, "generate")
                expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
                shot_ids = probe()["shot_ids"]
                compile_all(shot_ids)
                confirm_generation()
                ready = probe()
                provider_text = ready["ui"]["provider"]
                ui["provider"] = provider_text
                ui["image_provider_id"] = args.image_provider.strip() or "dashscope-image"
                configured = "未配置" not in provider_text
                if want_volc:
                    check("V2.4.5-01",
                          "图像 provider 是真实 volcengine-ark 且 configured=true（fake-image 切替不算）",
                          configured and "volcengine" in provider_text,
                          {"provider": provider_text})
                else:
                    check("V2.4.5-01",
                          "图像 provider 是真实 dashscope-image 且 configured=true（fake-image 切替不算）",
                          configured and "dashscope" in provider_text,
                          {"provider": provider_text})
                if not configured:
                    raise RuntimeError("图像 provider 未配置：不提交任何真实请求（预算未花）。")

                target = list(shot_ids)[args.shot_index]
                ui["target_shot"] = target
                click_row_button(target, "生成这张图")
                if want_volc:
                    # 同步协议：提交信封一步到终态，不经过 submitted 中间态；直接等 succeeded。
                    wait_state(target, "succeeded")
                else:
                    wait_state(target, "submitted")
                first_submit = submit_requests[0] if submit_requests else {}
                check("V2.4.5-02",
                      "本次只提交一次，且请求携带真实参考图（含 sha256）与非空 Prompt",
                      len(submit_requests) == 1
                      and int(first_submit.get("reference_count") or 0) >= 1
                      and reference_sha in (first_submit.get("reference_sha256") or [])
                      and bool(str(first_submit.get("prompt") or "").strip()),
                      {"submits": len(submit_requests),
                       "references": first_submit.get("reference_count"),
                       "reference_media": first_submit.get("reference_media"),
                       "size": first_submit.get("size")})

                terminal = "submitted"
                polls = 0
                if want_volc:
                    # 同步协议：提交信封一步到终态，无 task 链，不点“核对任务”。
                    for _ in range(args.poll_limit):
                        current = row_of(probe(), target) or {}
                        if current.get("state") in ("succeeded", "failed", "unknown"):
                            terminal = current.get("state")
                            break
                        polls += 1
                        page.wait_for_timeout(int(args.poll_interval * 1000))
                    else:
                        terminal = "timeout"
                else:
                    for _ in range(args.poll_limit):
                        current = row_of(probe(), target) or {}
                        if current.get("state") in ("succeeded", "failed", "unknown"):
                            terminal = current.get("state")
                            break
                        polls += 1
                        click_row_button(target, "核对任务")
                        page.wait_for_timeout(int(args.poll_interval * 1000))
                    else:
                        terminal = "timeout"
                settled = probe()
                latest = chain_of(settled, target)[-1]["payload"] if chain_of(settled, target) else {}
                ui["terminal"] = terminal
                ui["polls"] = polls
                if want_volc:
                    check("V2.4.5-03",
                          "同步提交一步到终态 succeeded，task_id 为空且 status 零外呼（伪造 task 算失败）",
                          terminal == "succeeded"
                          and latest.get("task_id") is None
                          and len(status_requests) == 0
                          and polls <= args.poll_limit,
                          {"terminal": terminal, "polls": polls,
                           "task_id": latest.get("task_id"),
                           "status_calls": len(status_requests)})
                else:
                    check("V2.4.5-03",
                          "有界轮询到终态 succeeded，task id 出现在状态查询里",
                          terminal == "succeeded"
                          and bool(latest.get("task_id"))
                          and latest.get("task_id") in status_requests
                          and polls <= args.poll_limit,
                          {"terminal": terminal, "polls": polls,
                           "task_id": latest.get("task_id"),
                           "status_calls": len(status_requests)})
                if terminal != "succeeded":
                    raise RuntimeError("真实任务没有落到 succeeded（terminal=" + str(terminal)
                                       + "）；记录保持原样，不做自动重提。")

                # ---------------- 候选非 Mock：真实字节入库并三方核对 ----------------
                wait_preview(target)
                final = probe()
                cands = candidate_of(final, target)
                rec = cands[-1]["payload"] if cands else {}
                asset = next((item for item in final["asset_rows"]
                              if item["sha256"] == rec.get("asset_sha256")), None)
                hashed = (page.evaluate(HASH_ASSET, {"sha256": rec.get("asset_sha256")})
                          if rec.get("asset_sha256") else {"found": False})
                resolved = results_for(latest.get("task_id") or "")
                ok_result = next((item for item in resolved if item["status"] == 200), {})
                requested = str(first_submit.get("size") or "")
                want = ([int(part) for part in requested.split("*")]
                        if "*" in requested else [])
                preview = (row_of(final, target) or {}).get("preview") or {}
                ui["result"] = {
                    "requested_size": requested,
                    "width": rec.get("width"), "height": rec.get("height"),
                    "byte_size": rec.get("byte_size"),
                    "media_type": rec.get("media_type"),
                    "provider_id": (ok_result.get("provider_id")
                                    or (latest.get("provider") or {}).get("provider_id") or ""),
                    "model_id": (ok_result.get("model_id")
                                 or (latest.get("provider") or {}).get("model_id") or ""),
                }
                if want_volc:
                    check("V2.4.5-04",
                          "候选非 Mock：同步信封字节入库、sha 双边一致（记录 = 本机重算）、尺寸等于请求尺寸、浏览器可预览",
                          bool(rec) and bool(asset) and asset["has_blob"]
                          and asset["role"] == "candidate"
                          and hashed.get("found") is True
                          and hashed.get("sha256") == rec.get("asset_sha256")
                          and rec.get("media_type") == "image/png"
                          and int(rec.get("byte_size") or 0) > 5120
                          and (not want or [rec.get("width"), rec.get("height")] == want)
                          and preview.get("natural_width", 0) > 0,
                          {"record": ui["result"],
                           "recomputed": str(hashed.get("sha256"))[:12],
                           "result_statuses": [item["status"] for item in resolved]})
                else:
                    check("V2.4.5-04",
                          "候选非 Mock：真实字节入库、sha 三方一致、尺寸等于请求尺寸、浏览器可预览",
                          bool(rec) and bool(asset) and asset["has_blob"]
                          and asset["role"] == "candidate"
                          and hashed.get("found") is True
                          and hashed.get("sha256") == rec.get("asset_sha256")
                          and ok_result.get("declared_sha") == rec.get("asset_sha256")
                          and rec.get("media_type") == "image/png"
                          and int(rec.get("byte_size") or 0) > 5120
                          and (not want or [rec.get("width"), rec.get("height")] == want)
                          and preview.get("natural_width", 0) > 0,
                          {"record": ui["result"],
                           "recomputed": str(hashed.get("sha256"))[:12],
                           "declared": str(ok_result.get("declared_sha"))[:12],
                           "result_statuses": [item["status"] for item in resolved]})

                screenshot_rel = f"evals/product-v2/v2.4.5-live-reference-{stamp}.png"
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                screenshots.append(screenshot_rel)
            finally:
                context.close()
    except Exception as error:  # noqa: BLE001 - 中断也要留下证据文件
        interrupted = f"{type(error).__name__}: {error}"
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass

    if interrupted:
        check("V2.4.5-99", "真实闭环在完成前中断（记录保持原样，不自动重提）", False, interrupted)

    expected_noise = ("Failed to load resource: the server responded with a status of 504",
                      "net::ERR_ABORTED")
    unexpected_console = [item for item in console_errors
                          if not any(noise in item for noise in expected_noise)]
    check("V2.4.5-05", "零意外 console error / page error",
          not unexpected_console and not page_errors,
          {"console": console_errors[:6], "unexpected": unexpected_console,
           "page": page_errors[:5]})

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    if want_volc:
        boundary = (
            "证明一笔预算内的真实参考图闭环：图像 provider 是 volcengine-ark（configured=true），"
            "一次真实同步 submit 携带真实商品参考图（sha256 " + reference_sha[:12] + "…，"
            + str(reference_size) + " 字节）与非空 Prompt；提交信封一步到 succeeded，task_id 为空且 status 零外呼；"
            "结果字节由提交信封一次性取回并存成浏览器 IndexedDB 里的 Blob，sha256 双边一致（候选记录 = 本机重算），"
            "尺寸等于请求尺寸。语义槽位由验证器直接播种（0 次语义调用），"
            "所以本证据不证明商品理解质量、出图审美质量、跨品类通用性、审核与返工（Phase 5）。"
        )
    else:
        boundary = (
            "证明一笔预算内的真实参考图闭环：图像 provider 是注册表默认的 dashscope-image（configured=true），"
            "一次真实 submit 携带真实商品参考图（sha256 " + reference_sha[:12] + "…，"
            + str(reference_size) + " 字节）与非空 Prompt；有界轮询到 succeeded 且 task id 出现在状态查询里；"
            "结果字节由真实响应取回并存成浏览器 IndexedDB 里的 Blob，sha256 三方一致（候选记录 = 本机重算 = "
            "服务端 X-Image-Sha256），尺寸等于请求尺寸。语义槽位由验证器直接播种（0 次语义调用），"
            "所以本证据不证明商品理解质量、出图审美质量、跨品类通用性、审核与返工（Phase 5）。"
        )
    report = {
        "task": "V2.4.5",
        "suite_id": "v2.4.5-live-reference",
        "status": status,
        "finished_at": finished_at,
        "reference": {"path": str(reference), "sha256": reference_sha,
                      "byte_size": reference_size},
        "model_calls": 1 if submit_requests else 0,
        "image_submit_requests": len(submit_requests),
        "image_status_requests": len(status_requests),
        "image_result_requests": len(result_requests),
        "checks": checks,
        "ui_flow": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshots": screenshots,
        "boundary": boundary,
    }
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.4.5-live-reference-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.4.5-live-reference-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        reference_display = reference.relative_to(ROOT).as_posix()
    except ValueError:
        reference_display = str(reference)
    title = ("amz-listing-kit Product V2 V2.4.5 真实参考图最小闭环（真实 volcengine seedream 调用）"
             if want_volc else
             "amz-listing-kit Product V2 V2.4.5 真实参考图最小闭环（真实 qwen-image 调用）")
    lines = [
        title,
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "image_submit_requests: " + str(len(submit_requests))
        + " · image_status_requests: " + str(len(status_requests))
        + " · image_result_requests: " + str(len(result_requests)),
        f"reference: {reference_display} sha256 {reference_sha}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        mark = "PASS" if item["ok"] else "FAIL"
        lines.append(f"- [{mark}] {item['id']} {item['title']}")
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for line in lines:
        print(line)
    print("")
    print("证据文件：")
    print(" -", json_path.relative_to(ROOT).as_posix())
    print(" -", txt_path.relative_to(ROOT).as_posix())
    for shot in screenshots:
        print(" -", shot)
    return 0 if status == "passed" else 1


# 浏览器内探针：模块级常量，在 main() 被调用前已经定义（先写主流程、再放探针，保持阅读顺序）。
PROBE = """
async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const read = (store) => new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await read("documents");
  const assets = await read("assets");
  const projects = await read("projects");
  db.close();
  const chains = {};
  for (const item of documents.filter((row) => row.kind === "generation_attempt")) {
    (chains[item.document_id] = chains[item.document_id] || []).push({
      version: item.version, payload: item.payload,
    });
  }
  for (const key of Object.keys(chains)) {
    chains[key].sort((left, right) => left.version - right.version);
  }
  const candidates = {};
  for (const item of documents.filter((row) => row.kind === "candidate")) {
    (candidates[item.document_id] = candidates[item.document_id] || []).push({
      version: item.version, payload: item.payload,
    });
  }
  for (const key of Object.keys(candidates)) {
    candidates[key].sort((left, right) => left.version - right.version);
  }
  const plans = documents.filter((item) => item.kind === "suite_plan")
    .sort((left, right) => left.version - right.version);
  const plan = plans.length ? plans[plans.length - 1] : null;
  const rows = [...document.querySelectorAll("#attempt-list .attempt-row")].map((node) => {
    const img = node.querySelector(".attempt-preview img");
    return {
      shot_id: node.getAttribute("data-shot-id"),
      state: node.getAttribute("data-attempt-state"),
      preview: img ? { complete: img.complete, natural_width: img.naturalWidth } : null,
    };
  });
  const providerNode = document.getElementById("attempt-provider");
  const errorNode = document.getElementById("attempt-error");
  const statusNode = document.getElementById("attempt-status");
  return {
    project_ids: projects.map((item) => item.project_id),
    shot_ids: plan ? plan.payload.shots.map((shot) => shot.shot_id) : [],
    attempt_chains: chains,
    candidate_chains: candidates,
    asset_rows: assets.map((item) => ({
      sha256: item.sha256, media_type: item.media_type, byte_size: item.byte_size,
      width: item.width, height: item.height, role: item.role,
      has_blob: item.blob instanceof Blob,
    })),
    ui: {
      provider: providerNode ? providerNode.textContent : "",
      status: statusNode ? statusNode.textContent : "",
      error: errorNode ? errorNode.textContent : "",
      error_hidden: errorNode ? errorNode.hidden : true,
      rows: rows,
    },
  };
}
"""


HASH_ASSET = """
async ({ sha256 }) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const rows = await new Promise((resolve, reject) => {
    const request = db.transaction("assets", "readonly").objectStore("assets").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const record = rows.find((item) => item.sha256 === sha256);
  if (!record || !(record.blob instanceof Blob)) return { found: false };
  const buffer = await record.blob.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  const hex = Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return {
    found: true, sha256: hex, byte_size: buffer.byteLength,
    media_type: record.media_type, width: record.width, height: record.height,
    role: record.role,
  };
}
"""


if __name__ == "__main__":
    raise SystemExit(main())
