#!/usr/bin/env python
"""远程真实链路 E2E 预演（真实模型；1 个项目、≤5 张图）。

对已部署的正式远程入口（默认 https://47.115.172.233:8080）用一个全新的浏览器配置文件
（等价陌生人空白态）走完整链路：空白首页 → 新建 → 资料（真实参考图）→ 真实语义分析
→ 确认槽位 → 推荐套图（可删到 ≤5 张）→ 逐张编译 Prompt → 确认 → 整套生成（真实出图）
→ 自动复核（VLM）→ 逐图采用 → 整套一致性（真实 VLM）→ 交付门禁与 Unknown 逐条确认
→ 交付包（真实字节，Python 独立核对）→ 项目包导出 → 刷新恢复。

边界（NOT-AUTHORITY）：单点时间证据；不替代产品发起人走查与陌生人验收，也不证明账户状态长期稳定。

用法：
    uv run --locked python tools/run_remote_real_e2e.py --base https://47.115.172.233:8080 \
        --image _working/amz-listing-kit-product-demo/real-run-01/workspace/inputs/originals/<file>.jpg
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"
# C14 要求非内置商品：默认落地灯（非内置品类），商品名/卖点与参考图保持一致。
DEFAULT_IMAGE = (ROOT / "_working" / "amz-listing-kit-product-demo" / "real-run-lamp"
                 / "lamp-3m.jpg")
MAX_SHOTS = 5
TERMINAL_STATES = {"succeeded", "failed", "unknown"}


def read_shots(page) -> list[dict]:
    return page.evaluate(
        """() => [...document.querySelectorAll('#shot-list .shot-row')].map((row) => ({
             id: row.getAttribute('data-shot-id'),
             label: (row.querySelector('.name') || {}).textContent || '',
             required: Boolean(row.querySelector('.badge.is-critical')),
             blocked: row.getAttribute('data-blocked') === 'true',
             reason: (row.querySelector('.meta') || {}).textContent || '',
           }))""")


def attempt_states(page) -> dict:
    return page.evaluate(
        """() => Object.fromEntries([...document.querySelectorAll(
             '#attempt-list .attempt-row[data-shot-id]')].map((row) => [
             row.getAttribute('data-shot-id'), row.getAttribute('data-attempt-state')]))""")


def inspect_delivery(path: Path) -> dict:
    """Python 独立核对交付包（不依赖产品代码）：条目集合、CRC 与 manifest 哈希。"""
    with zipfile.ZipFile(path) as archive:
        names = sorted(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        checks = json.loads(archive.read("checks.json").decode("utf-8"))
        entries = [item for item in names
                   if item.startswith("images/")]
        mismatches = []
        for item in manifest.get("images", []):
            digest = hashlib.sha256(archive.read(item["file"])).hexdigest()
            if digest != item["asset_sha256"]:
                mismatches.append(item["file"])
        return {
            "ok": archive.testzip() is None and not mismatches
                  and sorted(entries + ["README.txt", "checks.json", "manifest.json"]) == names
                  and len(manifest.get("images", [])) == len(entries)
                  and checks.get("gate_status") == "ready",
            "names": names, "images": len(entries), "mismatches": mismatches,
            "gate_status": checks.get("gate_status"),
            "acknowledgements": sorted({item.get("rule_id") for item in
                                        checks.get("acknowledgements", [])}),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="远程真实链路 E2E 预演（真实模型）")
    parser.add_argument("--base", default="https://47.115.172.233:8080")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE))
    parser.add_argument("--label", default="")
    parser.add_argument("--product-name", default="夹式 LED 阅读灯 · 远程真实链路预演")
    parser.add_argument("--intake-name", default="夹式 LED 阅读灯")
    parser.add_argument("--intake-description",
                        default="三档色温夹式 LED 阅读灯，USB-C 供电，关节臂可调，"
                                "哑光黑灯身，暖光柔和。")
    parser.add_argument("--selling-points",
                        default="3 档色温\n无级调光\nUSB-C 供电")
    parser.add_argument("--focus", default="夜读场景，突出灯头角度与暖光氛围")
    parser.add_argument("--generation-timeout", type=float, default=900.0)
    parser.add_argument("--suite-timeout", type=float, default=600.0)
    args = parser.parse_args()

    reference = Path(args.image)
    if not reference.is_file():
        print(f"参考图不存在：{reference}")
        return 2

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"-{args.label}" if args.label else ""
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    evidence_path = EVIDENCE_DIR / f"v2.7.2-remote-real-e2e-{stamp}{label}.txt"

    checks: list[dict] = []
    timings: dict[str, float] = {}
    console_errors: list[str] = []
    page_errors: list[str] = []
    http_errors: list[str] = []
    shots: list[dict] = []
    reviews: list[dict] = []
    adopted: list[dict] = []
    suite: dict = {}
    deliver: dict = {}
    delivered: dict = {}
    delivery_info: dict = {}
    package_info: dict = {}
    reload_state: dict = {}
    states: dict = {}
    home_blank: dict = {}
    slot_count = 0
    removed: list[str] = []
    screenshots: list[str] = []
    failure: str | None = None

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {check_id} {title}")
        if not ok:
            print("       " + json.dumps(detail, ensure_ascii=False, default=str)[:500])

    def shot(name: str):
        path = EVIDENCE_IMAGE_DIR / f"remote-real-e2e-{stamp}{label}-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(path.relative_to(ROOT).as_posix())
        return path

    def mark(step: str, start: float) -> None:
        timings[step] = round(time.monotonic() - start, 1)

    print("=" * 72)
    print(f"远程真实链路 E2E：{args.base}")
    print("=" * 72)

    profile_dir = tempfile.mkdtemp(prefix="amz-remote-e2e-")
    download_dir = Path(tempfile.mkdtemp(prefix="amz-remote-e2e-dl-"))

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            profile_dir, headless=True, viewport={"width": 1440, "height": 900},
            ignore_https_errors=True, accept_downloads=True)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(60_000)
        page.on("console", lambda message: console_errors.append(message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("response", lambda response: http_errors.append(
            f"{response.status} {response.url}") if response.status >= 400 else None)

        try:
            step = time.monotonic()
            page.goto(args.base + "/", wait_until="domcontentloaded")
            page.wait_for_selector("#empty-state:not([hidden])", timeout=90_000)
            home_blank = page.evaluate(
                """() => ({ projects: document.querySelectorAll('#project-list .project-row').length,
                     name_value: (document.getElementById('new-project-name') || {}).value || '' })""")
            shot("home")
            mark("blank_home", step)
            check("RR-01", "正式远程入口从空白浏览器配置文件启动：无项目、无预填商品",
                  home_blank["projects"] == 0 and home_blank["name_value"] == "",
                  {"home": home_blank, "base": args.base})

            step = time.monotonic()
            page.fill("#new-project-name", args.product_name)
            page.click("#create-project")
            expect(page.locator("#project-list .project-row")).to_have_count(1)
            page.click('#project-list .project-row button[data-action="open"]')
            expect(page.locator("#project-view")).to_be_visible()
            expect(page.locator('[data-stage-panel="intake"]')).to_be_visible()
            mark("create_open", step)

            step = time.monotonic()
            page.set_input_files("#ref-file", str(reference))
            expect(page.locator("#ref-list .ref-row")).to_have_count(1)
            page.fill("#intake-name", args.intake_name)
            page.fill("#intake-description", args.intake_description)
            page.fill("#intake-selling-points", args.selling_points)
            page.fill("#intake-focus", args.focus)
            expect(page.locator("#analyze-run")).to_be_enabled(timeout=30_000)
            shot("intake")
            mark("intake", step)

            step = time.monotonic()
            page.click("#analyze-run")
            # 成功（出现槽位）与明确失败（页面报错条）二者必居其一。旧实现只等槽位：
            # 上游欠费时界面已经把原因写清楚了，脚本却空等 300 秒，再报一个不含
            # 任何原因信息的 TimeoutError（2026-10-01 真实发生）。这里把「界面上的
            # 原因」直接变成失败原因与证据 —— 省下 5 分钟，也不丢信息。
            page.wait_for_selector(
                "#slot-list .slot-row, #analyze-error:not([hidden])", timeout=300_000)
            analyze_error = page.evaluate(
                """() => { const node = document.getElementById('analyze-error');
                     return node && !node.hidden ? (node.textContent || '').trim() : ''; }""")
            mark("analyze", step)
            if analyze_error:
                check("RR-02", "真实语义分析（deepseek-v4.1-flash）返回槽位并进入理解阶段",
                      False, {"error": analyze_error, "elapsed_s": timings["analyze"]})
                raise RuntimeError("语义分析未被受理：" + analyze_error[:300])
            page.wait_for_timeout(500)
            slot_count = page.locator("#slot-list .slot-row").count()
            shot("understand")
            check("RR-02", "真实语义分析（deepseek-v4.1-flash）返回槽位并进入理解阶段",
                  slot_count > 0
                  and page.locator('[data-stage-panel="understand"]').is_visible(),
                  {"slots": slot_count, "elapsed_s": timings["analyze"]})

            step = time.monotonic()
            guard = 0
            while (page.locator("#slot-list .slot-row")
                   .get_by_role("button", name="确认", exact=True).count() > 0
                   and guard < 30):
                (page.locator("#slot-list .slot-row")
                 .get_by_role("button", name="确认", exact=True).first.click())
                page.wait_for_timeout(250)
                guard += 1
            expect(page.locator("#stage-next-understand")).to_be_enabled(timeout=30_000)
            page.click("#stage-next-understand")
            expect(page.locator('[data-stage-panel="plan"]')).to_be_visible()
            mark("confirm_slots", step)

            step = time.monotonic()
            page.click("#suite-seed")
            page.wait_for_selector("#shot-list .shot-row", timeout=300_000)
            page.wait_for_timeout(500)
            shots = read_shots(page)
            removed: list[str] = []
            guard = 0
            while len(shots) > MAX_SHOTS and guard < 12:
                target = next((item for item in reversed(shots) if not item["required"]),
                              shots[-1])
                page.click(f'#shot-list .shot-row[data-shot-id="{target["id"]}"] '
                           'button:has-text("删除")')
                page.wait_for_timeout(500)
                removed.append(target["id"])
                shots = read_shots(page)
                guard += 1
            page.wait_for_timeout(300)
            mark("suite_plan", step)
            shot("plan")
            check("RR-03", f"推荐套图方案生成并收敛到 ≤{MAX_SHOTS} 张（真实依据驱动）",
                  len(shots) >= 1 and len(shots) <= MAX_SHOTS,
                  {"shots": shots, "removed": removed})

            step = time.monotonic()
            page.click("#stage-next-plan")
            expect(page.locator('[data-stage-panel="generate"]')).to_be_visible()
            for item in shots:
                card = f'#prompt-list .shot-spec[data-shot-id="{item["id"]}"]'
                page.click(card + " .toolbar button")
                page.wait_for_selector(card + '[data-prompt-state="saved"]', timeout=240_000)
                page.wait_for_timeout(200)
            mark("compile_prompts", step)

            step = time.monotonic()
            expect(page.locator("#confirm-action")).to_be_enabled(timeout=60_000)
            page.click("#confirm-action")
            expect(page.locator("#confirm-record")).to_contain_text("已确认 v", timeout=60_000)
            page.click("#batch-run")
            page.wait_for_function(
                """(ids) => ids.every((shotId) => {
                  const node = document.querySelector(
                    '#attempt-list .attempt-row[data-shot-id="' + shotId + '"]');
                  const state = node && node.getAttribute('data-attempt-state');
                  return state === 'succeeded' || state === 'failed' || state === 'unknown';
                })""", arg=[item["id"] for item in shots],
                timeout=args.generation_timeout * 1000)
            page.wait_for_timeout(800)
            states = attempt_states(page)
            mark("batch_generate", step)
            shot("generate")
            succeeded = [shot_id for shot_id, state in states.items() if state == "succeeded"]
            check("RR-04", "整套生成（真实 qwen-image-3.0 + 参考图）逐张到达终态",
                  len(states) == len(shots)
                  and all(state in TERMINAL_STATES for state in states.values()),
                  {"states": states, "elapsed_s": timings["batch_generate"]})

            step = time.monotonic()
            for item in shots:
                row = (f'#attempt-list .attempt-row[data-shot-id="{item["id"]}"]')
                if states.get(item["id"]) != "succeeded":
                    reviews.append({"shot_id": item["id"], "skipped": states.get(item["id"])})
                    continue
                before = page.get_attribute(row + " [data-review-summary]", "data-review-summary")
                page.click(row + " button[data-review-action]")
                try:
                    page.wait_for_function(
                        """(shotId) => {
                          const node = document.querySelector(
                            '#attempt-list .attempt-row[data-shot-id="' + shotId + '"] '
                            + '[data-review-summary]');
                          return Boolean(node
                            && !(node.getAttribute('data-review-summary') || '').includes('未检查'));
                        }""", arg=item["id"], timeout=180_000)
                    after = page.get_attribute(row + " [data-review-summary]", "data-review-summary")
                    reviews.append({"shot_id": item["id"], "before": before, "after": after})
                except Exception as error:  # noqa: BLE001
                    after = page.get_attribute(row + " [data-review-summary]", "data-review-summary")
                    reviews.append({"shot_id": item["id"], "before": before, "after": after,
                                    "timeout": str(error).splitlines()[0][:200]})
            mark("vlm_review", step)
            deterministic_ok = all(
                "自动检查" in (item.get("before") or "") and "未检查" in (item.get("before") or "")
                for item in reviews if not item.get("skipped"))
            terminal_ok = all(
                "未检查" not in (item.get("after") or "") for item in reviews
                if not item.get("skipped"))
            vlm_checked = [item["shot_id"] for item in reviews
                           if "已检查" in (item.get("after") or "")]
            check("RR-05a", "每个成功候选都有绑定当前规格的确定性检查摘要",
                  deterministic_ok, {"reviews": reviews})
            check("RR-05b", "VLM 复核对每个候选到达终态（已检查/未完成），无悬挂",
                  terminal_ok,
                  {"vlm_checked": vlm_checked, "elapsed_s": timings["vlm_review"],
                   "reviews": reviews})

            step = time.monotonic()
            page.click("#stage-next-review")
            expect(page.locator('[data-stage-panel="review"]')).to_be_visible()
            for item in shots:
                page.click(f'#review-list .review-card[data-shot-id="{item["id"]}"] '
                           'button:has-text("采用候选")')
                expect(page.locator("#adopt-panel")).to_be_visible(timeout=30_000)
                expect(page.locator("#adopt-submit")).to_be_enabled(timeout=30_000)
                page.click("#adopt-submit")
                page.wait_for_selector("#adopt-status:not([hidden])", timeout=60_000)
            adopted = page.evaluate(
                """() => [...document.querySelectorAll('#review-list .review-card')]
                   .map((node) => ({ shot_id: node.getAttribute('data-shot-id'),
                     state: node.getAttribute('data-selection-state'),
                     badge: (node.querySelector('.badge') || {}).textContent || '' }))""")
            mark("adopt", step)
            shot("review")
            check("RR-06", "逐图人工采用：每张图留下当前有效的选择",
                  len(adopted) == len(shots)
                  and all(item["state"] == "current" and "已采用" in item["badge"]
                          for item in adopted),
                  {"adopted": adopted})

            step = time.monotonic()
            page.click("#suite-review-run")
            page.wait_for_function(
                "() => document.getElementById('suite-review-status')"
                ".textContent.indexOf('整套检查 v') >= 0",
                timeout=args.suite_timeout * 1000)
            page.wait_for_timeout(400)
            suite = page.evaluate(
                """() => ({ status: (document.getElementById('suite-review-status') || {})
                     .textContent || '',
                   note: (document.getElementById('suite-review-note') || {}).textContent || '',
                   findings: [...document.querySelectorAll(
                     '#suite-review-findings .suite-finding')].map((node) => ({
                       rule: node.getAttribute('data-rule-id'),
                       severity: node.getAttribute('data-severity') })) })""")
            mark("suite_review", step)
            shot("suite-review")
            check("RR-07", "整套一致性（真实 qwen-vl-max）：报告对当前选择有效",
                  "整套检查 v2.5.5" in suite["status"] and "已过期" not in suite["status"],
                  {"suite": suite, "elapsed_s": timings["suite_review"]})

            step = time.monotonic()
            page.click("#stage-next-deliver")
            expect(page.locator('[data-stage-panel="deliver"]')).to_be_visible()
            page.wait_for_function(
                "() => document.querySelectorAll('#delivery-gate .gate-finding').length > 0",
                timeout=120_000)
            acked = 0
            guard = 0
            while guard < 20:
                pending = page.locator(
                    "#delivery-unknowns .gate-unknown button:not([disabled])")
                if pending.count() == 0:
                    break
                pending.first.click()
                page.wait_for_timeout(600)
                guard += 1
                acked += 1
            page.wait_for_timeout(600)
            deliver = page.evaluate(
                """() => ({ status: (document.getElementById('deliver-status') || {}).textContent || '',
                     export_disabled: (document.getElementById('deliver-export') || {}).disabled,
                     package_disabled: (document.getElementById('deliver-project-package') || {}).disabled,
                     findings: [...document.querySelectorAll('#delivery-gate .gate-finding')]
                       .map((node) => ({ rule: node.getAttribute('data-rule-id'),
                                         severity: node.getAttribute('data-severity') })),
                     gates: [...document.querySelectorAll('#delivery-gate .gate-row')].map((row) => ({
                       shot_id: row.getAttribute('data-shot-id'),
                       state: row.getAttribute('data-selection-state'),
                       badge: (row.querySelector('.badge') || {}).textContent || '' })) })""")
            mark("delivery_gate", step)
            shot("deliver")
            blocking = [item for item in deliver["findings"] if item["severity"] == "BLOCK"]
            check("RR-08", "交付门禁（真实链路）：逐图采用、无阻断、Unknown 已逐条确认后允许交付",
                  bool(deliver["gates"]) and not blocking
                  and deliver["export_disabled"] is False
                  and deliver["package_disabled"] in (False, None),
                  {"deliver": deliver, "acknowledged": acked})

            step = time.monotonic()
            with page.expect_download(timeout=300_000) as delivery_download:
                page.click("#deliver-export")
            zip_download = delivery_download.value
            delivery_path = download_dir / (zip_download.suggested_filename or "delivery.zip")
            zip_download.save_as(str(delivery_path))
            delivered = inspect_delivery(delivery_path)
            delivery_info = {
                "filename": zip_download.suggested_filename,
                "bytes": delivery_path.stat().st_size,
                "sha256": hashlib.sha256(delivery_path.read_bytes()).hexdigest(),
                "path": str(delivery_path),
            }
            mark("delivery_package", step)
            shot("delivery-package")
            check("RR-09", "交付包（真实字节）：Python 独立核对 ZIP 条目与 manifest 哈希逐条一致",
                  delivered["ok"] and len(delivered["images"]) == len(shots)
                  and delivery_info["bytes"] > 0,
                  {"delivered": delivered, "package": delivery_info})

            step = time.monotonic()
            with page.expect_download(timeout=300_000) as download_info:
                page.click("#deliver-project-package")
            download = download_info.value
            package_path = download_dir / (download.suggested_filename or "project.zip")
            download.save_as(str(package_path))
            package_info = {"filename": download.suggested_filename,
                            "bytes": package_path.stat().st_size,
                            "path": str(package_path)}
            mark("project_package", step)
            check("RR-10", "项目包（完整历史）可下载",
                  package_info.get("bytes", 0) > 0, {"package": package_info})

            step = time.monotonic()
            page.reload(wait_until="networkidle")
            expect(page.locator("#project-view")).to_be_visible(timeout=60_000)
            page.wait_for_timeout(800)
            reload_state = page.evaluate(
                """() => ({ stage: (document.querySelector('#stage-nav [data-stage-nav].is-current')
                       || {}).dataset ? document.querySelector('#stage-nav [data-stage-nav].is-current')
                       .dataset.stageNav : null,
                     gates: [...document.querySelectorAll('#delivery-gate .gate-row')].map((row) => ({
                       shot_id: row.getAttribute('data-shot-id'),
                       state: row.getAttribute('data-selection-state') })) })""")
            mark("reload", step)
            shot("after-reload")
            check("RR-11", "刷新后项目从 IndexedDB 恢复：阶段与逐图采用状态不变",
                  reload_state.get("stage") == "deliver"
                  and len(reload_state.get("gates") or []) == len(shots)
                  and all(item["state"] == "current" for item in reload_state.get("gates") or []),
                  {"reload": reload_state})
        except Exception as error:  # noqa: BLE001
            failure = f"{type(error).__name__}: {str(error).splitlines()[0][:400]}"
            print(f"!! 失败：{failure}")
            try:
                page.screenshot(path=str(EVIDENCE_IMAGE_DIR /
                                         f"remote-real-e2e-{stamp}{label}-failure.png"),
                                full_page=True)
                screenshots.append(f"evals/product-v2/evidence/"
                                   f"remote-real-e2e-{stamp}{label}-failure.png")
            except Exception:  # noqa: BLE001
                pass
        finally:
            context.close()

    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    ok_count = sum(1 for item in checks if item["ok"])
    status = "passed" if failure is None and ok_count == len(checks) else "failed"
    report = {
        "status": status,
        "finished_at": finished_at,
        "base": args.base,
        "product_name": args.product_name,
        "reference": str(reference),
        "shots": shots,
        "timings_s": timings,
        "checks": checks,
        "reviews": reviews,
        "adopted": adopted,
        "suite": suite,
        "deliver": deliver,
        "delivered": delivered,
        "delivery_package": delivery_info,
        "package": package_info,
        "reload": reload_state,
        "console_errors": console_errors[:40],
        "page_errors": page_errors[:20],
        "http_errors": sorted(set(http_errors))[:40],
        "screenshots": screenshots,
        "failure": failure,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    json_path = evidence_path.with_suffix(".json")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 远程真实链路 E2E 预演（真实模型）",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"finished_at: {finished_at}",
        f"status: {status}",
        f"base: {args.base}",
        f"product_name: {args.product_name}",
        f"reference: {reference}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: "
                         + json.dumps(item["detail"], ensure_ascii=False, default=str)[:800])
    lines += ["", "TIMINGS_S"]
    lines += [f"- {key}: {value}" for key, value in timings.items()]
    lines += ["", "SHOTS"]
    lines += [f"- {item['id']} | {item['label']} | required={item['required']} "
              f"| blocked={item['blocked']}" for item in shots]
    lines += ["", "ATTEMPT_STATES"]
    lines += [f"- {shot_id}: {state}" for shot_id, state in states.items()]
    lines += ["", "VLM_REVIEWS"]
    for item in reviews:
        lines.append(f"- {item['shot_id']}: before={item.get('before')}")
        lines.append(f"    after={item.get('after')}")
        if item.get("timeout"):
            lines.append(f"    hang_timeout={item['timeout']}")
    lines += ["", "DELIVERY"]
    lines.append(f"- suite: {json.dumps(suite, ensure_ascii=False)}")
    lines.append(f"- status: {deliver.get('status')}")
    lines.append(f"- export_button_disabled: {deliver.get('export_disabled')}")
    lines.append(f"- package_button_disabled: {deliver.get('package_disabled')}")
    lines.append(f"- delivery_package: {json.dumps(delivery_info, ensure_ascii=False)}")
    lines.append(f"- delivered: {json.dumps(delivered, ensure_ascii=False)}")
    lines.append(f"- package: {json.dumps(package_info, ensure_ascii=False)}")
    lines += ["", "ERRORS"]
    lines.append(f"- console_errors: {len(console_errors)}")
    for item in console_errors[:10]:
        lines.append(f"    {item[:200]}")
    lines.append(f"- http_errors: {sorted(set(http_errors))[:10]}")
    lines.append(f"- page_errors: {page_errors[:5]}")
    lines += ["", "SCREENSHOTS"]
    lines += [f"- {item}" for item in screenshots]
    lines += ["", "BOUNDARY",
              "单点时间证据；不替代产品发起人走查与陌生人验收；账户余额等外部前提可能随时变化。"]
    evidence_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"证据：{evidence_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{ok_count}/{len(checks)} 通过；耗时 " +
          " · ".join(f"{key}={value}s" for key, value in timings.items()))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
