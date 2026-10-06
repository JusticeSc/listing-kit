#!/usr/bin/env python
"""V2.3.1 证据：图片角色、Shot 模板与条件依赖注册表（纯领域，0 次模型调用）。

检查：
  1) domain 与 harness 模块全部通过 node --check（ESM 语法门）。
  2) 契约套件在真实 Chromium 里全部通过，且用例清单完整（R01..R13）。
  3) 反向探针确实存在并被执行：R04..R11，且 R10 守卫变红探针 >= 20 条、
     R11 改数据探针覆盖全部 16 个登记字段。
  4) 驱动侧独立走一遍推荐计划：与套件不同的上下文，独立校验必需阻断、逐图原因、
     自定义 Shot 草稿与注册表自检。
  5) 正式入口 `app/server.py --check` 仍然通过（V2.3.1 不得破坏 V2.1.4）。
  6) 全程零 console error / page error。

运行：
  uv run --locked python tools/verify_v2_3_1_suite_registry.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DIR = ROOT / "app" / "product_v2"
HARNESS_DIR = ROOT / "evals" / "product-v2" / "harness"
EVIDENCE_DIR = ROOT / "evals" / "product-v2"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

DOMAIN_FILES = [
    "app/product_v2/domain/errors.js",
    "app/product_v2/domain/shared.js",
    "app/product_v2/domain/slots.js",
    "app/product_v2/domain/intake.js",
    "app/product_v2/domain/brief.js",
    "app/product_v2/domain/invalidation.js",
    "app/product_v2/domain/suite-plan.js",
    "app/product_v2/domain/index.js",
    "evals/product-v2/harness/suite-plan-contract.js",
]

EXPECTED_CASES = [f"R{index:02d}" for index in range(1, 14)]

NEGATIVE_CASES = ["R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11"]

DRIVER_INTEGRATION = """
async () => {
  const domain = await import("/domain/index.js");
  const facts = [
    { slot_id: "signature_features", status: "confirmed", value: "304不锈钢，12小时保温" },
    { slot_id: "product_category", status: "confirmed", value: "保温杯" },
  ];
  const basePlan = domain.recommendPlan({ facts, assets: [{ role: "primary" }] });
  const byId = Object.fromEntries(basePlan.instances.map((item) => [item.template_id, item]));
  const withSize = domain.recommendPlan({
    facts: [...facts, { slot_id: "size_dimensions", status: "confirmed",
      value: [{ object: "杯身", axis: "volume", value: 500, unit: "ml", source_basis: "官方参数" }] }],
    assets: [{ role: "primary" }, { role: "competitor" }],
  });
  const customShot = domain.createCustomShot({ label: "赠品特写", factSlotIds: ["package_contents"] });
  const described = domain.describeRegistry();
  return {
    required_blocked: basePlan.required_blocked,
    satisfiable: basePlan.satisfiable,
    blocked: basePlan.blocked,
    size_blocked_reason: byId.size_dimensions.blocking.map((item) => item.reason),
    comparison_blocked_reason: byId.comparison_competitor.blocking.map((item) => item.reason),
    with_size_satisfiable: withSize.satisfiable,
    custom_draft_problems: domain.checkShotDraft(customShot).length,
    registry_problems: domain.validateSuiteRegistry().length,
    template_count: described.templates.length,
    role_count: described.roles.length,
    role_labels_unique: new Set(described.roles.map((item) => item.label)).size
      === described.roles.length,
  };
}
"""


class HarnessHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        return

    def _send(self, payload: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send((HARNESS_DIR / "suite-plan-contract.html").read_bytes(), MIME[".html"])
            return
        if path.startswith("/harness/"):
            candidate = (HARNESS_DIR / path[len("/harness/"):]).resolve()
            if str(candidate).startswith(str(HARNESS_DIR.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(), MIME.get(candidate.suffix, "application/octet-stream"))
                return
        else:
            candidate = (PRODUCT_DIR / path.lstrip("/")).resolve()
            if str(candidate).startswith(str(PRODUCT_DIR.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(), MIME.get(candidate.suffix, "application/octet-stream"))
                return
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"not found")


def start_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), HarnessHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def run_node_checks() -> dict:
    results = []
    for relative in DOMAIN_FILES:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)],
                                   cwd=str(ROOT), capture_output=True, text=True, check=False)
        results.append({"file": relative, "rc": completed.returncode,
                        "stderr": completed.stderr.strip()[-200:]})
    return {"files": results, "ok": all(item["rc"] == 0 for item in results)}


def run_entry_check() -> dict:
    completed = subprocess.run([sys.executable, "-B", str(ROOT / "app" / "server.py"), "--check"],
                               cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", check=False)
    tail = (completed.stdout + completed.stderr).strip().splitlines()[-4:]
    return {"rc": completed.returncode, "tail": tail,
            "ok": completed.returncode == 0 and any("通过。" in line for line in tail)
            and not any("FAIL" in line for line in tail)}


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.3.1 套图注册表验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    node_result = run_node_checks()
    check("V2.3.1-00", "domain 与 harness 模块通过 node --check（ESM 语法门）",
          node_result["ok"], node_result)

    server, base_url = start_server()
    suite: dict = {}
    driver: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(base_url + "/harness/suite-plan-contract.html",
                          wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.__V2_SUITE_RESULTS__ && "
                    "['passed','failed','crashed'].includes(window.__V2_SUITE_RESULTS__.status)",
                    timeout=60_000,
                )
                suite = page.evaluate("() => window.__V2_SUITE_RESULTS__")

                case_ids = [item["id"] for item in suite.get("cases", [])]
                missing = [case for case in EXPECTED_CASES if case not in case_ids]
                failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
                check("V2.3.1-01", "契约套件全部通过且用例清单完整（R01..R13）",
                      suite.get("status") == "passed" and not missing and not failed_cases,
                      {"status": suite.get("status"), "cases": len(case_ids), "missing": missing,
                       "failed": [item["id"] for item in failed_cases],
                       "errors": [item.get("error") for item in failed_cases][:3]})

                negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
                case_by_id = {item["id"]: item for item in suite.get("cases", [])}
                r10_detail = (case_by_id.get("R10") or {}).get("detail") or {}
                r11_detail = (case_by_id.get("R11") or {}).get("detail") or {}
                probes = r10_detail.get("probes") or []
                fields = r11_detail.get("fields")
                check("V2.3.1-02",
                      "反向探针与改数据探针确实被执行（R10 守卫变红 >= 20，R11 覆盖 16 个字段）",
                      negative_seen == NEGATIVE_CASES and not failed_cases
                      and len(probes) >= 20 and fields == 16
                      and r10_detail.get("boundary_depth") == 3,
                      {"negative_cases": len(negative_seen), "r10_probes": len(probes),
                       "r10_boundary_depth": r10_detail.get("boundary_depth"),
                       "r11_fields": fields,
                       "consumers": [item.get("consumer") for item in
                                     (r11_detail.get("consumers") or [])][:4]})

                driver = page.evaluate(DRIVER_INTEGRATION)
                check("V2.3.1-03",
                      "驱动侧独立集成：推荐计划阻断精确、补齐后解锁、自定义 Shot 合法",
                      json.dumps(driver.get("required_blocked")) == "[]"
                      and driver.get("satisfiable") == ["main_clean", "infographic_benefits",
                                                        "scene_lifestyle", "detail_material"]
                      and any("size_dimensions" in item for item in driver.get("size_blocked_reason", []))
                      and any("competitor" in item
                              for item in driver.get("comparison_blocked_reason", []))
                      and "size_dimensions" in driver.get("with_size_satisfiable", [])
                      and "comparison_competitor" in driver.get("with_size_satisfiable", [])
                      and driver.get("custom_draft_problems") == 0
                      and driver.get("registry_problems") == 0
                      and driver.get("template_count") == 8 and driver.get("role_count") == 9
                      and driver.get("role_labels_unique") is True,
                      driver)

                check("V2.3.1-04", "浏览器会话零 console error / page error",
                      not console_errors and not page_errors,
                      {"console": console_errors[:5], "page": page_errors[:5]})
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()

    entry = run_entry_check()
    check("V2.3.1-05", "正式入口自检仍全过（V2.3.1 不破坏 V2.1.4）", entry["ok"], entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明套图注册表（角色 / 模板 / 五类依赖谓词 / 推荐计划 / 自定义 Shot / 草稿校验）"
        "在真实 Chromium 里可机检：内置注册表零问题、事实依赖只认 confirmed、阻断原因精确到"
        "缺失对象、必需模板被阻断也不丢项、字段没有消费者就报红；R10 反向探针保证 25 条守卫"
        "都能变红，R11 逐字段变异保证 16 个登记字段都有真实消费者。全程 0 次模型调用。"
        "不证明推荐组合的审美质量、Prompt 编译、真实生成与审核（V2.3.2 起），也不证明服务器侧"
        "对不信任输入的独立阻断（按计划 §9.4 需重开）。"
    )
    report = {
        "task": "V2.3.1",
        "suite_id": "v2.3.1-suite-registry",
        "status": status,
        "finished_at": finished_at,
        "model_calls": 0,
        "checks": checks,
        "suite": suite,
        "driver_integration": driver,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "boundary": boundary,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.3.1-suite-registry-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.1-suite-registry-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.1 suite registry contracts",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 (offline domain contracts)",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False)[:600])
    lines += ["", "SUITE CASES"]
    for item in suite.get("cases", []):
        lines.append(f"- [{'PASS' if item.get('ok') else 'FAIL'}] {item.get('id')} {item.get('title')}")
        if not item.get("ok"):
            lines.append("  error: " + json.dumps(item.get("error"), ensure_ascii=False))
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.3.1 套图注册表验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False)[:600])
    print(f"套件用例：{len(suite.get('cases', []))} 条，失败 {len(suite.get('failed_ids', []) or [])} 条")
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
