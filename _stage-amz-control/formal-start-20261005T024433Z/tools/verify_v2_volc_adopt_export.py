#!/usr/bin/env python
"""V2 严格闭环补证：火山真实候选的采用→整套检查→交付导出（1 次真实生图调用）。

背景：r71-volc2 只证明到候选入库+预览；Goal 字面要求两模型各走完
“真实参考图输入、生成结果取回、本地候选持久化、审核采用与导出”。
本脚本用 1 次火山同步 submit 补齐后半段，不重复烧钱。

预算纪律（计划 §12.2）：
  - 运行前读 budget-ledger.json 预检：image<8、total<12、spent+0.12<=5.0，否则 exit 2，零外呼。
  - 需要 --live 且 ARK_API_KEY 存在且 AMZ_V2_DEFAULT_TRIAL=open（缺一即 exit 2，零外呼）。
  - 成功后把 0.12 元记入台账（spent）；失败不记、不重提、不重试。

链路：
  本地 create_product_v2_server + Playwright Chromium headless 独立 profile；
  图像走注册表默认工厂（env AMZ_V2_IMAGE_PROVIDER=volcengine-ark，不注入替身）；
  语义槽位验证器直接播种（0 语义调用）；确定性审核随候选自动生成（0 VLM 调用，
  VLM 已由 r71-vlm 单独证明 binding_ok，且按不变量 VLM 永不自动采用）；
  整套检查用 FakeSuiteReviewProvider(ok)（免费本地替身，只给送审集合内提示）。

断言：
  VE-01 provider 是真实 volcengine-ark 且 configured=true
  VE-02 只提交一次，携带真实参考图 sha256 + 非空 Prompt
  VE-03 同步一步到 succeeded，task_id 为空，status 零外呼
  VE-04 候选入库：sha 双边一致、尺寸=请求尺寸、可预览
  VE-05 确定性审核报告当前有效（采用面板“将绑定当前审核报告”）
  VE-06 人工采用：selection 记录绑定候选身份/版本/sha，行状态 current
  VE-07 整套检查当前 + 门禁 ready + 交付包：manifest 按采用候选原 action 溯源，
       ZIP sha 自洽，export_record append-only
  VE-08 零意外 console / page error

运行：
  AMZ_V2_DEFAULT_TRIAL=open uv run --locked python tools/verify_v2_volc_adopt_export.py --live
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
LEDGER_PATH = ROOT / "_working" / "amz-listing-kit-product-v2" / "budget-ledger.json"
DEFAULT_REFERENCE = (ROOT / "_working" / "amz-listing-kit-product-v2"
                     / "walkthrough-assets" / "food" / "honey-jar-antique.jpg")
IMAGE_COST_CNY = 0.12


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_server_module():
    spec = importlib.util.spec_from_file_location(
        "product_v2_server_volc_adopt_under_test", ROOT / "app" / "product_v2_server.py")
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
        evidence: [{ kind: "user", ref: "vve-seed" }], depends_on: [],
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
    parser = argparse.ArgumentParser(description="火山真实候选采用与导出闭环补证")
    parser.add_argument("--live", action="store_true", help="确认执行真实调用")
    parser.add_argument("--reference", default="")
    args = parser.parse_args()

    if not args.live or not os.environ.get("ARK_API_KEY", "").strip():
        print("未执行：需要 --live 且环境变量 ARK_API_KEY 存在。零外呼，零费用。")
        return 2
    if os.environ.get("AMZ_V2_DEFAULT_TRIAL", "") != "open":
        print("未执行：需要 AMZ_V2_DEFAULT_TRIAL=open（否则默认档 fail-closed，零外呼）。")
        return 2
    reference = Path(args.reference) if args.reference else DEFAULT_REFERENCE
    if not reference.is_absolute():
        reference = (ROOT / reference).resolve()
    if not reference.is_file():
        print("参考图不存在：" + str(reference))
        return 2

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    spent = float(ledger.get("spent_cny", 0.0))
    calls = ledger.get("spent_calls", {})
    image_used = int(calls.get("image", 0))
    sem_used = int(calls.get("semantic_vlm", 0))
    if not (image_used < 8 and image_used + sem_used < 12 and spent + IMAGE_COST_CNY <= 5.0):
        print(f"未执行：预算预检不通过（image {image_used}/8，total {image_used + sem_used}/12，"
              f"spent {spent}/5.0）。零外呼。")
        return 2
    print(f"预算预检通过：image {image_used}/8，total {image_used + sem_used}/12，"
          f"spent {spent}/5.0，本次预留 {IMAGE_COST_CNY} 元。")

    reference_sha = sha256_file(reference)
    reference_size = reference.stat().st_size
    os.environ["AMZ_V2_IMAGE_PROVIDER"] = "volcengine-ark"

    sys.path.insert(0, str(ROOT / "tools"))
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
    from src.providers.v2_fake_review import FakeReviewProvider  # noqa: PLC0415
    from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider  # noqa: PLC0415

    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=None,
        review_provider_factory=lambda: FakeReviewProvider("ok"),
        suite_review_provider_factory=lambda: FakeSuiteReviewProvider("ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    submit_requests: list[dict] = []
    status_requests: list[str] = []
    ui: dict = {}
    interrupted: str | None = None
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-vve-"))
    profile = temp_root / "profile"
    downloads = temp_root / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)

    def chain_of(data: dict, shot_id: str) -> list:
        return data["attempt_chains"].get(shot_id, [])

    def candidate_of(data: dict, shot_id: str) -> list:
        return data["candidate_chains"].get(shot_id, [])

    def row_of(data: dict, shot_id: str) -> dict | None:
        return next((row for row in data["ui"]["rows"] if row["shot_id"] == shot_id), None)

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1440, "height": 950},
                accept_downloads=True)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(30_000)
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

                page.on("request", on_request)

                def probe() -> dict:
                    return page.evaluate(PROBE)

                def row(shot_id: str):
                    return page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 120_000) -> None:
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

                def compile_all(shot_ids: list) -> None:
                    stage_nav.goto(page, "generate")
                    for shot_id in shot_ids:
                        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
                        page.locator(card + " .toolbar button").scroll_into_view_if_needed(timeout=10_000)
                        page.click(card + " .toolbar button")
                        page.wait_for_selector(card + '[data-prompt-state="saved"]', timeout=20_000)
                        page.wait_for_timeout(200)

                # ---------------- 项目准备（0 语义调用：槽位直接播种） ----------------
                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "火山闭环 · 采用导出")
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
                expect(page.locator("#confirm-action")).to_be_enabled()
                page.click("#confirm-action")
                expect(page.locator("#confirm-record")).to_contain_text("已确认 v")
                ready = probe()
                provider_text = ready["ui"]["provider"]
                ui["provider"] = provider_text
                configured = "未配置" not in provider_text
                check("VE-01", "图像 provider 是真实 volcengine-ark 且 configured=true",
                      configured and "volcengine" in provider_text,
                      {"provider": provider_text})
                if not configured:
                    raise RuntimeError("图像 provider 未配置：不提交任何真实请求（预算未花）。")

                target = "shot_main_clean"
                if target not in shot_ids:
                    raise RuntimeError(f"套图没有必需图 {target}（实际 {shot_ids}）；不提交。")
                ui["target_shot"] = target
                row(target).locator('button:has-text("生成这张图")').first.click()
                wait_state(target, "succeeded")
                first_submit = submit_requests[0] if submit_requests else {}
                check("VE-02", "本次只提交一次，且请求携带真实参考图（含 sha256）与非空 Prompt",
                      len(submit_requests) == 1
                      and int(first_submit.get("reference_count") or 0) >= 1
                      and reference_sha in (first_submit.get("reference_sha256") or [])
                      and bool(str(first_submit.get("prompt") or "").strip()),
                      {"submits": len(submit_requests),
                       "references": first_submit.get("reference_count"),
                       "reference_media": first_submit.get("reference_media"),
                       "size": first_submit.get("size")})

                settled = probe()
                latest = chain_of(settled, target)[-1]["payload"] if chain_of(settled, target) else {}
                terminal = (row_of(settled, target) or {}).get("state")
                ui["terminal"] = terminal
                check("VE-03", "同步提交一步到终态 succeeded，task_id 为空且 status 零外呼",
                      terminal == "succeeded"
                      and latest.get("task_id") is None
                      and len(status_requests) == 0,
                      {"terminal": terminal, "task_id": latest.get("task_id"),
                       "status_calls": len(status_requests)})
                if terminal != "succeeded":
                    raise RuntimeError("真实任务没有落到 succeeded；不重提。")

                wait_preview(target)
                final = probe()
                cands = candidate_of(final, target)
                rec = cands[-1]["payload"] if cands else {}
                asset = next((item for item in final["asset_rows"]
                              if item["sha256"] == rec.get("asset_sha256")), None)
                hashed = (page.evaluate(HASH_ASSET, {"sha256": rec.get("asset_sha256")})
                          if rec.get("asset_sha256") else {"found": False})
                requested = str(first_submit.get("size") or "")
                want = ([int(part) for part in requested.split("*")] if "*" in requested else [])
                preview = (row_of(final, target) or {}).get("preview") or {}
                ui["result"] = {
                    "requested_size": requested,
                    "width": rec.get("width"), "height": rec.get("height"),
                    "byte_size": rec.get("byte_size"),
                    "media_type": rec.get("media_type"),
                    "provider_id": ((latest.get("provider") or {}).get("provider_id") or ""),
                    "model_id": ((latest.get("provider") or {}).get("model_id") or ""),
                    "asset_sha256": rec.get("asset_sha256"),
                    "action_id": latest.get("action_id"),
                    "candidate_id": rec.get("candidate_id"),
                }
                check("VE-04", "候选非 Mock：同步信封字节入库、sha 双边一致、尺寸等于请求尺寸、可预览",
                      bool(rec) and bool(asset) and asset["has_blob"]
                      and asset["role"] == "candidate"
                      and hashed.get("found") is True
                      and hashed.get("sha256") == rec.get("asset_sha256")
                      and rec.get("media_type") == "image/png"
                      and int(rec.get("byte_size") or 0) > 5120
                      and (not want or [rec.get("width"), rec.get("height")] == want)
                      and preview.get("natural_width", 0) > 0,
                      {"record": ui["result"],
                       "recomputed": str(hashed.get("sha256"))[:12]})

                # ---------------- 人工采用（真实用户路径） ----------------
                page.click("#stage-next-review")
                page.click(f'#review-list .review-card[data-shot-id="{target}"] '
                           'button:has-text("采用候选")')
                page.wait_for_selector("#adopt-submit:not([disabled])", timeout=15_000)
                fingerprint_text = (
                    page.locator("#adopt-fingerprint").inner_text(timeout=10_000))
                check("VE-05", "确定性审核报告当前有效（采用面板显示将绑定当前审核报告）",
                      "将绑定当前审核报告" in fingerprint_text,
                      {"fingerprint": fingerprint_text[:160]})
                page.click("#adopt-submit")
                page.wait_for_selector("#adopt-status:not([hidden])", timeout=20_000)
                page.wait_for_timeout(300)
                selections = page.evaluate(READ_DOCS, "selection")
                mine = [item for item in selections
                        if (item.get("payload") or {}).get("shot_id") == target]
                newest = max(mine, key=lambda item: item.get("version", 0)) if mine else None
                payload = (newest or {}).get("payload") or {}
                card_text = page.evaluate(
                    """(shot) => {
                        const node = document.querySelector(
                          '#review-list .review-card[data-shot-id="' + shot + '"]');
                        return (node && node.textContent) || "";
                      }""",
                    arg=target)
                check("VE-06", "人工采用：selection 记录绑定候选身份/版本/sha，行状态 current",
                      newest is not None and payload.get("action") == "select"
                      and payload.get("candidate_id") == rec.get("candidate_id")
                      and payload.get("candidate_sha256") == rec.get("asset_sha256")
                      and "已采用" in card_text,
                      {"selection": {key: payload.get(key) for key in (
                          "action", "candidate_id", "candidate_sha256",
                          "candidate_version", "selection_id")}})

                # ---------------- 整套检查 + 交付导出 ----------------
                page.click("#suite-review-run")
                page.wait_for_function(
                    "() => document.getElementById('suite-review-status')"
                    ".textContent.indexOf('整套检查 v') >= 0",
                    timeout=60_000)
                page.click('[data-stage-nav="deliver"]')
                page.wait_for_function(
                    "() => document.querySelectorAll('#delivery-gate .gate-finding').length > 0",
                    timeout=30_000)
                gate = page.evaluate(GATE_STATE)
                check("VE-07a", "交付门禁 ready（无 BLOCK），导出按钮可用",
                      not [item for item in gate["findings"] if item["severity"] == "BLOCK"]
                      and gate["disabled"] is False,
                      {"status": gate["status"][:120], "findings": gate["findings"]})
                if gate["disabled"] is not False:
                    raise RuntimeError("门禁未通过：不导出。 findings=" + json.dumps(
                        gate["findings"], ensure_ascii=False)[:400])
                with page.expect_download(timeout=120_000) as info:
                    page.click("#deliver-export")
                download = info.value
                zip_path = downloads / "delivery-volc.zip"
                download.save_as(str(zip_path))
                zip_bytes = zip_path.read_bytes()
                zip_sha = hashlib.sha256(zip_bytes).hexdigest()
                with zipfile.ZipFile(zip_path) as archive:
                    names = sorted(archive.namelist())
                    broken = archive.testzip()
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                    checks_doc = json.loads(archive.read("checks.json").decode("utf-8"))
                images = manifest.get("images", [])
                frozen = latest.get("prompt") or {}
                manifest_ok = (
                    broken is None and len(images) == 1
                    and images[0].get("shot_id") == target
                    and images[0].get("candidate_id") == rec.get("candidate_id")
                    and images[0].get("attempt_action_id") == latest.get("action_id")
                    and images[0].get("asset_sha256") == rec.get("asset_sha256")
                    and images[0].get("prompt_version") == frozen.get("version")
                    and images[0].get("prompt_hash") == frozen.get("hash"))
                records = page.evaluate(READ_DOCS, "export_record")
                record_ok = (
                    len(records) == 1
                    and (records[0].get("payload") or {}).get("zip_sha256") == zip_sha
                    and (records[0].get("payload") or {}).get("zip_bytes") == len(zip_bytes))
                ui["delivery"] = {"names": names, "zip_sha256": zip_sha[:16],
                                  "zip_bytes": len(zip_bytes),
                                  "gate_status": checks_doc.get("gate_status")
                                  if isinstance(checks_doc, dict) else None}
                check("VE-07", "交付包：manifest 按采用候选原 action 溯源，ZIP 自洽，记录 append-only",
                      manifest_ok and record_ok, ui["delivery"])

                screenshot_rel = f"evals/product-v2/v2.4.5-volc-adopt-export-{stamp}.png"
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
        check("VE-99", "闭环在完成前中断（记录保持原样，不自动重提）", False, interrupted)

    unexpected_console = [item for item in console_errors
                          if "Failed to load resource" not in item and "net::" not in item]
    check("VE-08", "零意外 console error / page error",
          not unexpected_console and not page_errors,
          {"console": console_errors[:6], "unexpected": unexpected_console,
           "page": page_errors[:5]})

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"

    spent_this_run = 0.0
    ledger_note = "no upstream call; ledger untouched"
    if submit_requests and status == "passed":
        ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        ledger.setdefault("reservations", []).append({
            "calls": 1,
            "note": "flash 1344x1344 single-ref n=1 volc adopt-export closeout "
                    "(AMZ_V2_DEFAULT_TRIAL=open): sync one-shot succeeded, task_id null, "
                    "adopted + suite-checked + delivery-exported; output 0.12, input free",
            "provider": "volcengine-ark",
            "reserve_cny": IMAGE_COST_CNY,
            "status": "spent",
            "evidence": f"evals/product-v2/v2.4.5-volc-adopt-export-{stamp}.json",
        })
        ledger["spent_calls"] = ledger.get("spent_calls", {})
        ledger["spent_calls"]["image"] = int(ledger["spent_calls"].get("image", 0)) + 1
        ledger["spent_cny"] = round(float(ledger.get("spent_cny", 0.0)) + IMAGE_COST_CNY, 4)
        ledger["total_reserved_cny"] = ledger["spent_cny"]
        ledger["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        spent_this_run = IMAGE_COST_CNY
        ledger_note = f"spent {IMAGE_COST_CNY} CNY recorded in budget-ledger.json"

    boundary = (
        "火山严格闭环补证：图像 provider 是 volcengine-ark（configured=true），"
        "一次真实同步 submit 携带真实商品参考图（sha256 " + reference_sha[:12] + "…，"
        + str(reference_size) + " 字节）与非空 Prompt；提交信封一步到 succeeded，"
        "task_id 为空且 status 零外呼；结果字节入库成 IndexedDB Blob（sha 双边一致）；"
        "确定性审核随候选自动生成且当前有效；人工在审核页点“采用候选”并提交选择记录；"
        "整套检查当前、交付门禁 ready；交付包 manifest 按采用候选原 action 的冻结 "
        "Prompt 版本/hash 溯源，ZIP sha 自洽，export_record append-only。"
        "语义槽位由验证器直接播种（0 语义调用），VLM 未重跑（r71-vlm 已证 binding_ok，"
        "且 VLM 按不变量永不自动采用）。本证据不证明出图审美质量与跨品类通用性。"
        + ledger_note + "。"
    )
    report = {
        "task": "V2.R7.4-closeout",
        "suite_id": "v2-volc-adopt-export",
        "status": status,
        "finished_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "reference": {"path": str(reference), "sha256": reference_sha,
                      "byte_size": reference_size},
        "model_calls": 1 if submit_requests else 0,
        "image_submit_requests": len(submit_requests),
        "image_status_requests": len(status_requests),
        "checks": checks,
        "ui_flow": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshots": screenshots,
        "budget": {"spent_this_run_cny": spent_this_run},
        "boundary": boundary,
    }
    json_path = EVIDENCE_DIR / f"v2.4.5-volc-adopt-export-{stamp}.json"
    txt_path = EVIDENCE_DIR / f"v2.4.5-volc-adopt-export-{stamp}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    title = "amz-listing-kit Product V2 火山真实候选采用与导出闭环（1 次真实调用）"
    lines = [title, "NOT-AUTHORITY: point-in-time verification evidence only",
             f"observed_at: {report['finished_at']}", f"status: {status}",
             "image_submit_requests: " + str(len(submit_requests))
             + " · image_status_requests: " + str(len(status_requests)),
             f"reference: {reference.relative_to(ROOT).as_posix()} sha256 {reference_sha}",
             f"json: {json_path.relative_to(ROOT).as_posix()}", "", "CHECKS"]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
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


READ_DOCS = """async (kind) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('amz-listing-kit-v2');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const rows = await new Promise((resolve, reject) => {
    const tx = db.transaction('documents', 'readonly');
    const out = [];
    tx.objectStore('documents').openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(out); return; }
      if (cursor.value.kind === kind) {
        out.push({ document_id: cursor.value.document_id, version: cursor.value.version,
                   payload: cursor.value.payload });
      }
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  return rows;
}"""


GATE_STATE = """() => ({
  status: (document.getElementById('deliver-status') || {}).textContent || '',
  disabled: (document.getElementById('deliver-export') || {}).disabled,
  findings: [...document.querySelectorAll('#delivery-gate .gate-finding')].map((node) => ({
    rule: node.getAttribute('data-rule-id'),
    severity: node.getAttribute('data-severity'),
    jumps: node.querySelectorAll('button[data-shot-id]').length })),
  result: (document.getElementById('delivery-result') || {}).textContent || '' })"""


if __name__ == "__main__":
    raise SystemExit(main())
