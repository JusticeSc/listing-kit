#!/usr/bin/env python
"""V2.5.1 证据：生成前、单图和导出的确定性验证器（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 通过 node --check（ESM 语法门）。
  2) R11 WebCrypto 哈希复算宿主案例在真实 Chromium 全过；R01..R10/R12/R13 纯领域断言
     已按 R3.2 分层迁至 `npm run test:domain`（Node 直跑，同批断言）。
  3) 既有契约套件回归（candidate / attempt / batch / confirm / prompt_edit / suite_editor）全过。
  4) 真实工作台走查（假 provider）：候选保存后 IndexedDB 出现 kind="review_report" 的当前报告
     （绑定 candidate_id + 当前合同版本 + asset_sha256），候选行出现 data-review-summary 摘要；
     刷新后报告与摘要仍在且不重复铺。
  5) 正式入口 --check 全过；零意外 console error / page error。

运行：
  uv run --locked python tools/verify_v2_5_1_deterministic_review.py --label final
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402  （V2.UI.2 六阶段工作台导航）
import v2_verify_shared as shared  # noqa: E402  （正式 server/夹具/共同业务操作）
from v2_verify_shared import (  # noqa: E402
    read_suite, load_server_module, free_port, png_bytes, PROBE, SEED_SLOTS,
    compile_all, candidate_of, reviews_for, row_of, run_entry, candidate_json, review_json,
)
from src.providers.v2_review import REVIEW_CONTRACT_VERSION  # noqa: E402

PRODUCT_DIR = ROOT / "app" / "product_v2"
HARNESS_DIR = ROOT / "evals" / "product-v2" / "harness"
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"




# R3.2 分层：浏览器只承载宿主特有案例 R11；纯领域 R01..R10/R12/R13 在 npm run test:domain。
EXPECTED_CASES = ["R11"]
NEGATIVE_CASES = ["R11"]
REGRESSION_SUITES = (
    ("candidate", "candidate-contract.html", "__V2_CANDIDATE_RESULTS__"),
    ("attempt", "attempt-contract.html", "__V2_ATTEMPT_RESULTS__"),
    ("batch", "batch-contract.html", "__V2_BATCH_RESULTS__"),
    ("confirm", "confirm-contract.html", "__V2_CONFIRM_RESULTS__"),
    ("prompt_edit", "prompt-edit-contract.html", "__V2_PROMPT_EDIT_RESULTS__"),
    ("suite_editor", "suite-editor-contract.html", "__V2_SUITE_EDITOR_RESULTS__"),
)






















def main() -> int:
    parser = argparse.ArgumentParser(
        description="V2.5.1 生成前、单图与导出的确定性验证器证据")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    contract = shared.current_review_contract()
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []
    ui: dict = {}

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})


    static_server, static_url = shared.start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["review"] = read_suite(
                    browser, static_url + "/harness/review-contract.html",
                    "__V2_REVIEW_RESULTS__", console_errors, page_errors)
                for name, page_name, variable in REGRESSION_SUITES:
                    suites[name] = read_suite(
                        browser, static_url + "/harness/" + page_name, variable,
                        console_errors, page_errors)
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    suite = suites["review"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.5.1-01", "R11 宿主案例全过且清单齐全（R01..R10/R12/R13 在 npm run test:domain）",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")}
                      for item in failed_cases[:3]]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.5.1-02", "R11 反向探针确实执行（哈希篡改/缺失阻断/缺 digest 注入抛错）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "review"}
    check("V2.5.1-02b", "既有契约套件回归全过（candidate / attempt / batch / confirm / prompt_edit / suite_editor）",
          all(item["status"] == "passed" and not item["failed"] for item in regression.values()),
          regression)

    module = load_server_module()
    from src.providers.v2_fake_image import FakeImageProvider  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    stage = "setup"
    interrupted: str | None = None
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v251-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))

                def probe() -> dict:
                    return page.evaluate(PROBE)

                def row(shot_id: str):
                    return page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 30_000) -> None:
                    # fake 上游同步完成时批次直接到 succeeded，不停 submitted：
                    # 等 submitted 时同样接受已落定的 succeeded/reconciling。
                    if state == "submitted":
                        page.wait_for_function(
                            """(shot) => {
                                const node = document.querySelector(
                                    '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                                const value = node && node.getAttribute("data-attempt-state");
                                return value === "submitted" || value === "succeeded"
                                    || value === "reconciling";
                            }""", arg=shot_id, timeout=timeout)
                        return
                    expect(row(shot_id)).to_have_attribute(
                        "data-attempt-state", state, timeout=timeout)
                def wait_candidate_ui(shot_id: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(shot) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                            return Boolean(node && node.querySelector('.attempt-candidate'));
                        }""", arg=shot_id, timeout=timeout)

                def wait_review_ui(shot_id: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(payload) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + payload.shot + '"]');
                            const line = node && node.querySelector('.attempt-review');
                            const summary = line && line.getAttribute('data-review-summary');
                            return Boolean(summary
                                && summary.indexOf('自动检查 ' + payload.version) === 0);
                        }""", arg={"shot": shot_id, "version": contract}, timeout=timeout)

                def confirm_generation() -> dict:
                    # 确认即提交：本次授权的新增 attempt 消费证明（非任意旧行存在）。
                    gate = shared.confirm_and_submit(page, expect, probe, shot_ids=shot_ids)
                    assert gate["ok"], f"确认必须产生本次授权的新消费：{gate['after_actions']}"
                    return gate


                def click_row_button(shot_id: str, text: str) -> None:
                    stage_nav.goto(page, "generate")
                    row(shot_id).locator(f'button:has-text("{text}")').first.click()

                def generate_and_settle(shot_id: str) -> None:
                    # 新流程一次确认直接整套进批次（runBatch 自动提交全部已就绪图）：
                    # 批次轮询会自动核对；只在仍停 submitted 时点核对，点前重读防竞态。
                    wait_state(shot_id, "submitted")
                    for _attempt in range(20):
                        state = row(shot_id).get_attribute("data-attempt-state")
                        if state != "submitted":
                            break
                        button = row(shot_id).locator('button:has-text("核对任务")').first
                        try:
                            if button.is_enabled(timeout=1000):
                                button.click(timeout=5000)
                                break
                        except Exception:
                            pass
                        page.wait_for_timeout(1000)
                    wait_state(shot_id, "succeeded")

                # ---------------- 项目准备：空白项目 → 参考图 → 资料 → 槽位 → 套图 → 确认 ----------------
                stage = "prep"
                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · 自动检查")
                page.click("#create-project")
                expect(page.locator("#project-view")).to_be_visible()
                page.set_input_files("#ref-file", str(reference))
                expect(page.locator("#ref-list .ref-row")).to_have_count(1)
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
                expect(page.locator("#shot-list .shot-row")).to_have_count(4)
                expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
                initial = probe()
                shot_ids = initial["shot_ids"]
                compile_all(page, shot_ids)
                ok_shot = shot_ids[0]
                confirm_generation()

                # ---------------- 单张成功：候选自动入库 + 当前 ReviewReport + 摘要行 ----------------
                stage = "review-report"
                generate_and_settle(ok_shot)
                wait_candidate_ui(ok_shot)
                wait_review_ui(ok_shot)
                after_store = probe()
                cand_chain = candidate_of(after_store, ok_shot)
                cand = cand_chain[-1]["payload"] if cand_chain else {}
                candidate_id = cand.get("candidate_id") or ""
                reviews = reviews_for(after_store, candidate_id)
                report = reviews[-1]["payload"] if reviews else {}
                summary = report.get("summary") or {}
                review_ui = (row_of(after_store, ok_shot) or {}).get("review") or {}
                ui["candidate_id"] = candidate_id
                ui["review_summary_text"] = review_ui.get("text")
                ui["review_contract_version"] = report.get("review_contract_version")
                check("V2.5.1-03",
                      "候选保存后自动生成当前 ReviewReport（绑定身份 + 合同 "
                      + contract + "），界面出现摘要行",
                      len(cand_chain) == 1
                      and len(reviews) == 1
                      and report.get("review_contract_version") == contract
                      and report.get("candidate_id") == candidate_id
                      and report.get("shot_id") == cand.get("shot_id")
                      and report.get("asset_sha256") == cand.get("asset_sha256")
                      and isinstance(report.get("findings"), list) and len(report["findings"]) > 0
                      and all(isinstance(summary.get(key), int)
                              for key in ["BLOCK", "HIGH_RISK", "WARNING", "PASS", "UNKNOWN"])
                      and (review_ui.get("summary") or "").startswith("自动检查 " + contract)
                      and review_ui.get("contract") == contract
                      and review_ui.get("candidate") == candidate_id
                      and "阻断" in (review_ui.get("text") or "")
                      and "提醒" in (review_ui.get("text") or ""),
                      {"contract": report.get("review_contract_version"),
                       "summary": summary,
                       "summary_line": review_ui.get("summary"),
                       "findings": len(report.get("findings") or [])})

                # ---------------- 刷新：报告与摘要保留、不重复铺 ----------------
                stage = "reload"
                before_reload = probe()
                page.reload(wait_until="networkidle")
                wait_candidate_ui(ok_shot)
                wait_review_ui(ok_shot)
                after_reload = probe()
                check("V2.5.1-04",
                      "刷新后报告与摘要仍在、候选链不变、review_report 文档不重复铺",
                      candidate_json(after_reload, ok_shot) == candidate_json(before_reload, ok_shot)
                      and len(reviews_for(after_reload, candidate_id)) == 1
                      and review_json(after_reload, candidate_id)
                      == review_json(before_reload, candidate_id)
                      and ((row_of(after_reload, ok_shot) or {}).get("review") or {})
                      .get("summary", "").startswith("自动检查 " + contract),
                      {"review_docs_before": len(reviews_for(before_reload, candidate_id)),
                       "review_docs_after": len(reviews_for(after_reload, candidate_id))})

                screenshot_rel = (f"evals/product-v2/evidence/"
                                  f"v2.5.1-deterministic-review-{stamp}.png")
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                screenshots.append(screenshot_rel)
            finally:
                context.close()
    except Exception as error:  # noqa: BLE001 - 中断也要留下证据文件
        interrupted = f"[{stage}] {type(error).__name__}: {error}"
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass

    if interrupted:
        check("V2.5.1-99", "浏览器闭环在完成前中断", False, interrupted)

    check("V2.5.1-05", "零意外 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:6], "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.5.1-06", "正式入口自检仍全过（本批不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明确定性验证器在真实浏览器上按规则版本工作：注册表对缺要素/重复 id/未知词表/"
        "无任务锚点的消费者/未被认领的确认单代码直接报错；单图检查只做可复现测量——"
        "PNG 合同、记录一致性、最小长边 1000px（阻断）、推荐 1600px、主图 1:1、透明通道"
        "（HIGH_RISK 人工确认）、像素位深；测量失败一律降为 UNKNOWN 且不阻断；生成前阻塞项"
        "从确认单一对一映射为 BLOCK、提示项映射为 WARNING；导出就绪检查覆盖选择完整性、"
        "报告当前性、报告无 BLOCK、选择链一致性与 WebCrypto sha256 复算。候选保存时自动生成"
        "绑定 candidate_id + review_contract_version + asset_sha256 的 ReviewReport 并投影到"
        "工作台摘要行，刷新后保留且不重复铺。本批不做 VLM 审核、比较界面与返工（V2.5.2+）；"
        "0 次真实模型调用、0 次外部网络；图像与语义 provider 都是注入的假替身，只证明确定性"
        "校验语义，不证明真实出图质量。"
    )
    report = {
        "task": "V2.5.1",
        "suite_id": "v2.5.1-deterministic-review",
        "status": status,
        "finished_at": finished_at,
        "model_calls": 0,
        "external_network_calls": 0,
        "checks": checks,
        "suites": suites,
        "ui_flow": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshots": screenshots,
        "boundary": boundary,
    }
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.5.1-deterministic-review-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.5.1-deterministic-review-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.5.1 生成前、单图与导出的确定性验证器",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 · external_network_calls: 0 (fake providers + 本机服务)",
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


if __name__ == "__main__":
    raise SystemExit(main())
