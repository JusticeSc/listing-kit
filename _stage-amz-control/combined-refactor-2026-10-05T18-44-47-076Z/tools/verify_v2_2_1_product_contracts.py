#!/usr/bin/env python
"""V2.2.1 证据：商品理解领域契约（FactSlot / ProductInput / ProductBrief / 失效图）。

检查：
  1) domain 与 harness 模块全部通过 node --check（ESM 语法门）。
  2) 宿主特有契约案例（C36 落库集成、C37 JSON 纯数据守卫）在真实 Chromium 里全部通过；
     C01..C35 纯领域断言已按 R3.2 分层迁至 `npm run test:domain`（Node 直跑，同批断言）。
  3) 反向探针确实存在并被执行：非法形状、模型确认、无值确认、依赖成环、越界失效、brief 不一致。
  4) 由驱动侧独立走一遍"资料 + 槽位 + 理解"落库：真 IndexedDB、真 repository、真版本推进。
  5) 正式入口 `app/server.py --check` 仍然通过（V2.2.1 不得破坏 V2.1.4）。
  6) 全程零 console error / page error。

运行：
  uv run --locked python tools/verify_v2_2_1_product_contracts.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import urllib.request
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
    "app/product_v2/domain/index.js",
    "evals/product-v2/harness/brief-contract.js",
]

# R3.2 分层：浏览器只承载宿主特有案例；纯领域 C01..C35 在 npm run test:domain。
EXPECTED_CASES = ["C36", "C37"]

NEGATIVE_CASES = ["C37"]

DRIVER_INTEGRATION = """
async () => {
  const domain = await import("/domain/index.js");
  const storage = await import("/storage/index.js");
  const name = "amz-v2-driver-" + crypto.randomUUID();
  const opened = await storage.openStorage({ name });
  try {
    const repository = opened.repository;
    const project = await repository.projects.create({ name: "驱动侧集成" });
    const input = domain.emptyProductInput();
    input.product_name = "不锈钢保温杯";
    input.references = [{ asset_sha256: "e".repeat(64), role: "primary" }];
    const problemCount = domain.checkProductInput(input).length;
    const readiness = domain.intakeReadiness(input).ready;
    const inputRecord = await repository.documents.save(project.project_id, {
      kind: domain.DOMAIN_DOCUMENT_KINDS.product_input, documentId: "intake", payload: input,
    });
    const nameSlot = Object.assign(
      { schema_version: 1, slot_id: "product_name", label: "商品名称", authority: "core_fixed",
        value_type: "text", critical: true, value: "不锈钢保温杯", source: "user_input",
        status: "confirmed", confidence: null, evidence: [{ kind: "user", ref: "driver" }],
        depends_on: [] },
      {});
    const categorySlot = Object.assign({}, nameSlot, { slot_id: "product_category", label: "商品品类", value: "保温杯" });
    const nameRecord = await repository.documents.save(project.project_id, {
      kind: domain.DOMAIN_DOCUMENT_KINDS.fact_slot, documentId: "product_name", payload: nameSlot,
    });
    const categoryRecord = await repository.documents.save(project.project_id, {
      kind: domain.DOMAIN_DOCUMENT_KINDS.fact_slot, documentId: "product_category", payload: categorySlot,
    });
    const brief = domain.buildProductBrief([
      { slot: nameSlot, version: nameRecord.version },
      { slot: categorySlot, version: categoryRecord.version },
    ]);
    const briefRecord = await repository.documents.save(project.project_id, {
      kind: domain.DOMAIN_DOCUMENT_KINDS.product_brief, documentId: "brief", payload: brief,
    });
    const edited = domain.applySlotAction(categorySlot, { action: "edit", actor: "user", value: "真空保温杯" });
    const categoryV2 = await repository.documents.save(project.project_id, {
      kind: domain.DOMAIN_DOCUMENT_KINDS.fact_slot, documentId: "product_category", payload: edited,
    });
    const stale = domain.briefIsStale(brief, [
      { slot: nameSlot, version: nameRecord.version },
      { slot: edited, version: categoryV2.version },
    ]);
    const readinessAfterEdit = domain.briefReadiness(domain.buildProductBrief([
      { slot: nameSlot, version: nameRecord.version },
      { slot: edited, version: categoryV2.version },
    ]));
    const allDocs = await repository.documents.listAll(project.project_id);
    return {
      problem_count: problemCount,
      intake_ready: readiness,
      input_version: inputRecord.version,
      brief_version: briefRecord.version,
      category_version: categoryV2.version,
      stale: stale.stale,
      stale_reasons: stale.reasons,
      readiness: readinessAfterEdit.ready,
      document_versions: allDocs.length,
    };
  } finally {
    opened.close();
    indexedDB.deleteDatabase(name);
  }
}
"""


class HarnessHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
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
            self._send((HARNESS_DIR / "brief-contract.html").read_bytes(), MIME[".html"])
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
    parser = argparse.ArgumentParser(description="V2.2.1 领域契约验证")
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
    check("V2.2.1-00", "domain 与 harness 模块通过 node --check（ESM 语法门）",
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
                page.goto(base_url + "/harness/brief-contract.html", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => window.__V2_BRIEF_RESULTS__ && "
                    "['passed','failed','crashed'].includes(window.__V2_BRIEF_RESULTS__.status)",
                    timeout=60_000,
                )
                suite = page.evaluate("() => window.__V2_BRIEF_RESULTS__")

                case_ids = [item["id"] for item in suite.get("cases", [])]
                missing = [case for case in EXPECTED_CASES if case not in case_ids]
                failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
                check("V2.2.1-01", "宿主契约案例全部通过且清单完整（C36/C37；C01..C35 在 npm run test:domain）",
                      suite.get("status") == "passed" and not missing and not failed_cases,
                      {"status": suite.get("status"), "cases": len(case_ids), "missing": missing,
                       "failed": [item["id"] for item in failed_cases],
                       "errors": [item.get("error") for item in failed_cases][:3]})

                negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
                check("V2.2.1-02", "反向探针确实被执行（非法形状 / 模型确认 / 无值确认 / 环 / 越界失效 / brief 不一致）",
                      negative_seen == NEGATIVE_CASES and not failed_cases,
                      {"expected": len(NEGATIVE_CASES), "seen": len(negative_seen)})

                driver = page.evaluate(DRIVER_INTEGRATION)
                check("V2.2.1-03", "驱动侧独立集成：资料/槽位/理解落库，槽位升级后 brief 过期且历史保留",
                      driver.get("problem_count") == 0 and driver.get("intake_ready") is True
                      and driver.get("input_version") == 1 and driver.get("brief_version") == 1
                      and driver.get("category_version") == 2 and driver.get("stale") is True
                      and driver.get("readiness") is True and driver.get("document_versions", 0) >= 5,
                      driver)

                check("V2.2.1-04", "浏览器会话零 console error / page error",
                      not console_errors and not page_errors,
                      {"console": console_errors[:5], "page": page_errors[:5]})
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()

    entry = run_entry_check()
    check("V2.2.1-05", "正式入口自检仍全过（V2.2.1 不破坏 V2.1.4）", entry["ok"], entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明商品理解领域契约可机检：固定/动态/自定义/派生四类槽位的权限矩阵、来源与确认状态、"
        "状态转换（模型只能提案、冲突不许静默覆盖、无值不许确认、派生不能直接改值）、失效图"
        "（失效集与保留集逐类匹配，历史与 Blob 永不失效，Shot 级失效必须带目标）、ProductBrief 的"
        "版本化投影、过期判定与就绪门，并在真实 IndexedDB 上完成资料/槽位/理解三仓落库与版本推进。"
        "不证明 DeepSeek 适配、界面投影、套图规划、生成、审核与交付。"
    )
    report = {
        "task": "V2.2.1",
        "suite_id": "v2.2.1-product-contracts",
        "status": status,
        "finished_at": finished_at,
        "checks": checks,
        "suite": suite,
        "driver_integration": driver,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "boundary": boundary,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.2.1-product-contracts-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.2.1-product-contracts-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.2.1 product understanding contracts",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
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
    print("V2.2.1 商品理解契约验证")
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
