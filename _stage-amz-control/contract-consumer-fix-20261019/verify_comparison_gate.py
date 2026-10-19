#!/usr/bin/env python
"""第 5 批独立审查 P1（对比图提交门/确认单依赖口径）的页面级差分验证（零收费）。

被验证的修复（本工作树未提交差量）：
  - app/product_v2/domain/prompt.js::dependencyAssetsOf —— 依赖求值只看真正会外发的
    商品依据（product_truth / style_reference 用途）；编辑源候选与未发送的图不算依据。
  - app/product_v2/domain/confirm.js —— 确认单按每张图的实际冻结选择判依赖
    （product 侧 referencesByShot 来自与编译同一 selectReferences）。
  - app/product_v2/storage/repository.js::reserveGenerationAttempt —— 提交门用同一投影。

场景（真实页面 / 隔离临时 profile / Fake 三件套 / 0 次真实模型调用）：
  资料：商品原照(primary) + 竞品参考(competitor) → 理解确认事实 → 方案加「对比图·竞品同框」
       → 普通决定 → 本图参考选择（显式）。
  negative：本图只选商品原照（不含竞品）→ 修复后确认单把该图标为阻断
       （DEPENDENCY_UNSATISFIED，修复定位 suite）并把它排除出本次发送批：
       其余图照常确认外发，对比图没有任何外发请求/attempt。
  positive：本图选商品原照 + 竞品 → 确认单无该阻断、随批次外发；实际外发请求按所选顺序
       携带竞品字节（role=competitor），Fake 提交终态 succeeded。

差分用法（对照「未修复行为」时，用旧源重建 dist 后以同一断言跑 negative）：
  uv run --locked python _stage-amz-control/contract-consumer-fix-20261019/verify_comparison_gate.py \
      --phase negative --expect blocked --label <标识>
  uv run --locked python _stage-amz-control/contract-consumer-fix-20261019/verify_comparison_gate.py \
      --phase positive --expect allowed --label <标识>

证据落在同目录：p1-gate-<phase>-<label>.json / .png。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402
import v2_verify_shared as shared  # noqa: E402

STAGE_DIR = Path(__file__).resolve().parent
COMPARISON_SHOT = "shot_comparison_competitor"
SUBMIT_SUFFIX = "/api/v2/images/submit"

PROBE_INTAKE_HAS_COMPETITOR = """
async (sha) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const all = await new Promise((resolve, reject) => {
    const request = db.transaction(["documents"], "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const latest = all.filter((item) => item.kind === "product_input")
    .sort((left, right) => right.version - left.version)[0] || null;
  if (!latest) return false;
  const references = (latest.payload && Array.isArray(latest.payload.references))
    ? latest.payload.references : [];
  return references.some((item) => item.asset_sha256 === sha && item.role === "competitor");
}
"""

PROBE_SHOT_SPEC = """
async (input) => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const all = await new Promise((resolve, reject) => {
    const request = db.transaction(["documents"], "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const latest = all.filter((item) => item.kind === "shot_spec" && item.document_id === input.shotId)
    .sort((left, right) => right.version - left.version)[0] || null;
  if (!latest) return null;
  const payload = latest.payload || {};
  return { version: latest.version,
    reference_sha256s: Object.prototype.hasOwnProperty.call(payload, "reference_sha256s")
      ? payload.reference_sha256s : null };
}
"""

CONFIRM_DOM = """
() => {
  const el = (id) => document.getElementById(id);
  const rows = [...document.querySelectorAll("#confirm-list .confirm-shot")].map((node) => ({
    shot_id: node.getAttribute("data-shot-id"),
    blocked: node.getAttribute("data-blocked"),
    state: (node.querySelector(".badge") || {}).textContent || "",
    text: node.textContent.trim(),
    blockers: [...node.querySelectorAll(".confirm-shot-blocker")].map((line) => ({
      text: (line.textContent || "").trim(),
      code: (line.textContent || "").split("：")[0].trim(),
      region: line.getAttribute("data-region") })),
  }));
  const action = el("confirm-action");
  return {
    editor_hidden: el("confirm-editor") ? el("confirm-editor").hidden : null,
    status: (el("confirm-status") || {}).textContent || "",
    action_text: action ? action.textContent : "",
    action_disabled: action ? action.disabled : null,
    rows: rows,
  };
}
"""


def log(message: str) -> None:
    print(message, flush=True)


def wait_for(page, script: str, arg, timeout: float = 30.0, step_ms: int = 200):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = page.evaluate(script, arg)
        if last:
            return last
        page.wait_for_timeout(step_ms)
    raise AssertionError(f"等待超时（{timeout}s）：{last}")


def set_shot_refs(page, shot_id: str, wanted: list[str]) -> dict:
    """显式勾选本图参考（顺序即用户所选），保存并等落库形状一致。"""
    shared.open_specs(page)
    card = f'#shot-spec-list .shot-spec[data-shot-id="{shot_id}"]'
    page.wait_for_selector(card, timeout=15_000)
    radio = f"#spec-refs-select-{shot_id}"
    if not page.locator(radio).is_checked():
        page.click(radio)
    page.wait_for_selector(f"#spec-references-{shot_id} input[type='checkbox']", timeout=15_000)
    for sha in wanted:
        box = f"#spec-ref-{sha[:12]}-{shot_id}"
        if page.locator(box).count() == 0:
            raise AssertionError(f"参考勾选控件缺失：{box}")
        if not page.locator(box).is_checked():
            page.click(box)
            page.wait_for_timeout(150)
    page.click(card + ' button:has-text("保存")')
    deadline = time.monotonic() + 30
    spec = None
    while time.monotonic() < deadline:
        spec = page.evaluate(PROBE_SHOT_SPEC, {"shotId": shot_id})
        if spec and spec["reference_sha256s"] == wanted:
            return spec
        page.wait_for_timeout(200)
    raise AssertionError(f"规格保存未落定为所选参考：{spec}（期望 {wanted}）")


def confirm_ready(page):
    dom = page.evaluate(CONFIRM_DOM)
    if dom["editor_hidden"] or dom["action_disabled"] is None:
        return None
    if not any(row["shot_id"] == COMPARISON_SHOT for row in dom["rows"]):
        return None
    return dom


def run_phase(phase: str, expect_blocked: bool, label: str, keep: bool) -> int:
    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    port = shared.free_port()
    server, _providers = shared.start_product_server(port)
    base = f"http://127.0.0.1:{port}/"
    requests: list[dict] = []
    workdir = Path(tempfile.mkdtemp(prefix=f"p1-gate-{phase}-"))
    observed: dict = {
        "phase": phase, "expect": "blocked" if expect_blocked else "allowed",
        "label": label, "base": base,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    exit_code = 1
    try:
        primary_path = workdir / "p1-primary.png"
        competitor_path = workdir / "p1-competitor.png"
        primary_path.write_bytes(shared.png_bytes(1200, 1200, (206, 192, 170)))
        competitor_path.write_bytes(shared.png_bytes(1200, 1200, (110, 148, 205)))
        primary_sha = hashlib.sha256(primary_path.read_bytes()).hexdigest()
        competitor_sha = hashlib.sha256(competitor_path.read_bytes()).hexdigest()
        observed["fixture"] = {"primary_sha256": primary_sha, "competitor_sha256": competitor_sha}

        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(workdir / "profile"), headless=True,
                viewport={"width": 1440, "height": 900})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                logs = shared.collect(page)

                def capture(request) -> None:
                    if request.method == "POST" and request.url.split("?", 1)[0].endswith(SUBMIT_SUFFIX):
                        try:
                            body = json.loads(request.post_data or "{}")
                        except Exception:  # noqa: BLE001
                            body = {"parse_error": True}
                        requests.append({"action_id": body.get("action_id"),
                                         "references": body.get("references"),
                                         "model_id": body.get("model_id"),
                                         "parameters": body.get("parameters")})

                page.on("request", capture)
                page.goto(base, wait_until="networkidle")
                shared.create_project(page, "P1对比图提交门验证", primary_path)

                # 竞品参考：上传第二张并把角色改为 competitor（真实控件路径）。
                page.set_input_files("#ref-file", str(competitor_path))
                page.wait_for_function(
                    "() => document.querySelectorAll('#ref-list .ref-row').length === 2",
                    timeout=15_000)
                row_shas = page.evaluate(
                    "() => [...document.querySelectorAll('#ref-list .ref-row')]"
                    ".map((node) => node.getAttribute('data-sha'))")
                if competitor_sha not in row_shas:
                    raise AssertionError(f"竞品参考行缺失：{row_shas}")
                page.select_option(
                    f'#ref-list .ref-row[data-sha="{competitor_sha}"] select', "competitor")
                wait_for(page, PROBE_INTAKE_HAS_COMPETITOR, competitor_sha)
                observed["intake_rows"] = row_shas

                # 理解：外发一次语义分析（Fake），人工确认事实（含 signature_features）。
                page.click("#analyze-run")
                stage_nav.goto(page, "understand")
                page.wait_for_selector("#slot-list .slot-row:not([hidden])", timeout=30_000)
                shared.confirm_slots(page)

                # 方案：种子（intake 已有竞品时，推荐方案本身就含对比图）；只有缺这张图才显式加模板。
                stage_nav.goto(page, "plan")
                page.click("#suite-seed")
                page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
                shot_ids = page.evaluate(shared.SHOT_IDS)
                if COMPARISON_SHOT not in shot_ids:
                    page.select_option("#suite-template", "comparison_competitor")
                    page.click("#suite-add-template")
                    page.wait_for_function(
                        "() => [...document.querySelectorAll('#shot-list .shot-row[data-shot-id]')]"
                        ".some((node) => node.getAttribute('data-shot-id') === '"
                        + COMPARISON_SHOT + "')", timeout=20_000)
                    shot_ids = page.evaluate(shared.SHOT_IDS)
                if shot_ids.count(COMPARISON_SHOT) != 1:
                    raise AssertionError(f"对比图应恰好一张，实际：{shot_ids}")
                observed["shot_ids"] = shot_ids
                observed["plan_row"] = page.evaluate(
                    "() => { const node = document.querySelector("
                    "'#shot-list .shot-row[data-shot-id=\"" + COMPARISON_SHOT + "\"]');"
                    " return node ? { blocked: node.getAttribute('data-blocked'),"
                    " text: node.textContent.trim().slice(0, 300) } : null; }")

                # 编译前置普通决定（Issue #9 决定门）：展示 + 逐图印字。
                observed["decisions"] = shared.decide_for_compile(page, shot_ids)

                # 本图参考选择：negative 只选商品原照；positive 选商品原照 + 竞品。
                wanted = [primary_sha] if phase == "negative" else [primary_sha, competitor_sha]
                observed["shot_spec"] = set_shot_refs(page, COMPARISON_SHOT, wanted)

                # 编译全部图（stale 自动重编译），等确认区渲染出逐图行。
                shared.compile_all(page, shot_ids)
                stage_nav.goto(page, "generate")
                deadline = time.monotonic() + 60
                dom = None
                while time.monotonic() < deadline and dom is None:
                    dom = confirm_ready(page)
                    if dom is None:
                        page.wait_for_timeout(300)
                if dom is None:
                    raise AssertionError("确认区未渲染出对比图逐图行")
                observed["confirm"] = dom
                comparison = next(row for row in dom["rows"]
                                  if row["shot_id"] == COMPARISON_SHOT)
                codes = [blocker["code"] for blocker in comparison["blockers"]]
                observed["comparison_codes"] = codes

                # 视觉证据：确认区滚动入视口后整页截图。
                editor = page.locator("#confirm-editor")
                editor.scroll_into_view_if_needed()
                page.wait_for_timeout(250)
                screenshot = STAGE_DIR / f"p1-gate-{phase}-{label}.png"
                page.screenshot(path=str(screenshot))
                observed["screenshot"] = screenshot.name

                # 发送批口径：阻断图被排除（本次不发送），其余图照常提交；这是产品意图语义。
                match = re.search(r"本次明确发送\s*(\d+)\s*张", dom["status"] or "")
                sending_total = int(match.group(1)) if match else None
                observed["sending_total"] = sending_total

                def requests_for(shot_id: str, action_to_shot: dict) -> list[dict]:
                    return [request for request in requests
                            if request.get("action_id")
                            and action_to_shot.get(request["action_id"]) == shot_id]

                if phase == "negative" and expect_blocked:
                    # 修复后：对比图被排除出授权与发送批；授权恰好覆盖其余 4 张并逐图消费。
                    others = [shot_id for shot_id in shot_ids if shot_id != COMPARISON_SHOT]
                    result = shared.confirm_and_submit(
                        page, expect, submit_requests=requests,
                        shot_ids=others, submitted_shots=others)
                    action_to_shot = {row["payload"]["action_id"]: row["payload"]["shot_id"]
                                      for row in result["consumed_actions"]}
                    authorized_ids = [shot.get("shot_id")
                                      for shot in ((result["confirmation"] or {}).get("payload")
                                                   or {}).get("shots", [])]
                    observed["submit"] = {
                        "ok": result["ok"], "new_shots": result["new_shots"],
                        "captured_actions": result["captured_actions"],
                        "action_to_shot": action_to_shot,
                        "authorized_ids": authorized_ids,
                    }
                    checks = [
                        ("对比图逐图行被阻断", comparison["blocked"] == "true"),
                        ("阻断码含 DEPENDENCY_UNSATISFIED",
                         "DEPENDENCY_UNSATISFIED" in codes),
                        ("修复定位指向套图规划(suite)",
                         any(blocker["region"] == "suite" for blocker in comparison["blockers"])),
                        ("发送批不含对比图", sending_total == len(shot_ids) - 1),
                        ("确认授权不包含被阻断的对比图",
                         COMPARISON_SHOT not in (authorized_ids or [])),
                        ("其余图按授权逐图消费", result["ok"]),
                        ("对比图没有任何外发请求",
                         len(requests_for(COMPARISON_SHOT, action_to_shot)) == 0),
                    ]
                elif phase == "negative" and not expect_blocked:
                    # 未修复差分对照：对比图不被排除，随批次外发且请求不含竞品字节（缺陷现场）。
                    result = shared.confirm_and_submit(
                        page, expect, submit_requests=requests, shot_ids=shot_ids)
                    action_to_shot = {row["payload"]["action_id"]: row["payload"]["shot_id"]
                                      for row in result["consumed_actions"]}
                    observed["submit"] = {
                        "ok": result["ok"], "new_shots": result["new_shots"],
                        "captured_actions": result["captured_actions"],
                        "action_to_shot": action_to_shot,
                    }
                    comparison_requests = requests_for(COMPARISON_SHOT, action_to_shot)
                    observed["comparison_requests"] = comparison_requests
                    competitor_leak = any(
                        any(item.get("sha256") == competitor_sha
                            for item in (request.get("references") or []))
                        for request in comparison_requests)
                    checks = [
                        ("对比图逐图行未阻断（缺陷现场）", comparison["blocked"] != "true"),
                        ("发送批包含全部图（含对比图）", sending_total == len(shot_ids)),
                        ("对比图随批次外发", len(comparison_requests) == 1),
                        ("对比图请求不含竞品字节（缺陷现场）",
                         len(comparison_requests) == 1 and not competitor_leak),
                        ("本次授权与逐图消费一致", result["ok"]),
                    ]
                else:
                    # positive（修复后）：本图选商品原照 + 竞品 → 对比图随批次外发且带竞品字节。
                    result = shared.confirm_and_submit(
                        page, expect, submit_requests=requests, shot_ids=shot_ids)
                    action_to_shot = {row["payload"]["action_id"]: row["payload"]["shot_id"]
                                      for row in result["consumed_actions"]}
                    observed["submit"] = {
                        "ok": result["ok"], "new_shots": result["new_shots"],
                        "captured_actions": result["captured_actions"],
                        "action_to_shot": action_to_shot,
                    }
                    comparison_requests = requests_for(COMPARISON_SHOT, action_to_shot)
                    observed["comparison_requests"] = comparison_requests
                    checks = [
                        ("对比图逐图行未阻断", comparison["blocked"] != "true"),
                        ("发送批包含全部图（含对比图）", sending_total == len(shot_ids)),
                        ("本次授权与逐图消费一致", result["ok"]),
                        ("对比图请求已外发", len(comparison_requests) == 1),
                    ]
                    if comparison_requests:
                        refs = comparison_requests[0].get("references") or []
                        ref_pairs = [(item.get("sha256"), item.get("role")) for item in refs]
                        observed["comparison_request_refs"] = ref_pairs
                        checks.append((
                            "对比图请求按所选顺序携带竞品字节(role=competitor)",
                            ref_pairs == [(primary_sha, "primary"),
                                          (competitor_sha, "competitor")]))

                observed["checks"] = [{"title": title, "ok": bool(ok)} for title, ok in checks]
                observed["console_errors"] = logs["console"]
                observed["page_errors"] = logs["page"]
                observed["finished_at"] = datetime.now(timezone.utc).isoformat()
                observed["boundary"] = (
                    "Fake 三件套替身成功只证请求/记录/门行为，不证明真实出图品质；"
                    "本验证不替代 C15/C17 真人门。")
                for title, ok in checks:
                    log(("PASS " if ok else "FAIL ") + title)
                exit_code = 0 if all(ok for _title, ok in checks) else 1
            finally:
                context.close()
    finally:
        server.stop()
        if not keep:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            observed["kept_workdir"] = str(workdir)
    evidence = STAGE_DIR / f"p1-gate-{phase}-{label}.json"
    evidence.write_text(json.dumps(observed, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    log(f"证据：{evidence}")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["negative", "positive"], required=True)
    parser.add_argument("--expect", choices=["blocked", "allowed"], required=True,
                        help="negative 期望建阻断；positive/未修复差分对照期望可提交")
    parser.add_argument("--label", required=True)
    parser.add_argument("--keep-profile", action="store_true",
                        help="保留临时 profile/夹具目录以便排查（默认用后即删）")
    args = parser.parse_args()
    if args.phase == "positive" and args.expect != "allowed":
        raise SystemExit("positive 阶段只能期望 allowed")
    return run_phase(args.phase, args.expect == "blocked", args.label, args.keep_profile)


if __name__ == "__main__":
    raise SystemExit(main())
