#!/usr/bin/env python
"""V2.3.5 证据：生成前确认与外发资料摘要（0 次真实模型调用）。

检查：
  1) domain / workspace / harness 全部通过 node --check（ESM 语法门）。
  2) 契约套件 H01..H12 在真实 Chromium 全过（确定性、摘要一致、缺 Prompt / 过期 / 缺依赖 /
     Provider / 平台 / 参考图越界阻断、风险传播、确认记录与失效判定、反向探针）。
  3) 正式入口：套图就绪后「生成前确认」解锁，4 张图因缺 Prompt 全部阻断并定位到 Prompt 区。
  4) 缺依赖的对比图被精确阻断并定位到套图规划；删除后恢复。
  5) 编译全部图后可确认；点击确认写入 generation_confirm v1，界面、记录与重算指纹一致，状态前进。
  6) 改公共风格：确认失效、状态回落 PLAN_REVIEW，界面显示原因。
  7) 重编译后确认单恢复可提交形状，但摘要按不自动重提拒绝复发旧图：按钮禁用并标注
     “确认并生成 0 张”，确认记录保持 v1 单版本（无新授权即无新版本，不伪造 v2）。
     产品合同：generation-view.ts:565-567（状态文案声明不自动重提）、652-653（按 sending.total
     渲染计数）、649（can_submit 为假即禁用）；generation.ts:960-973（initial 模式下已有成功
     记录的图从确认队列剔除）、952-957（无冻结目标的授权无 pending）。
  8) 刷新恢复：确认记录 v1、指纹与存储一致，按钮保持禁用（仍无可发送的新任务）。
  9) 零 console error / page error；截图落盘；正式入口 --check 与既有套件仍全过。

运行：
  uv run --locked python tools/verify_v2_3_5_pre_generation_confirm.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
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
import v2_verify_shared as shared  # noqa: E402  （自动本地准备的等待口径与其它验证器一致）

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
    "app/product_v2/domain/shared.js",
    "app/product_v2/domain/errors.js",
    "app/product_v2/domain/slots.js",
    "app/product_v2/domain/intake.js",
    "app/product_v2/domain/brief.js",
    "app/product_v2/domain/invalidation.js",
    "app/product_v2/domain/suite-plan.js",
    "app/product_v2/domain/suite.js",
    "app/product_v2/domain/specs.js",
    "app/product_v2/domain/prompt.js",
    "app/product_v2/domain/confirm.js",
    "app/product_v2/domain/index.js",
    "app/product_v2/workspace.js",
    "evals/product-v2/harness/confirm-contract.js",
]

EXPECTED_CASES = [f"H{index:02d}" for index in range(1, 13)]
NEGATIVE_CASES = ["H03", "H04", "H05", "H06", "H07", "H08", "H11", "H12"]

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
        critical: definition.critical, value, source: "user_input",
        status: "confirmed", confidence: null,
        evidence: [{ kind: "user", ref: "v235-seed" }], depends_on: [],
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

CONFIRM_PROBE = """
async () => {
  const domain = await import("/domain/index.js");
  const storage = await import("/storage/db.js");
  // 有效图像 Prompt 档必须与服务端当前能力一致：直接从 capabilities 投影，不复制常量。
  const capabilities = await (await fetch("/api/v2/capabilities")).json();
  const imageProfile = domain.imagePromptProfile(capabilities.images);
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const readAll = (store) => new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await readAll("documents");
  const projects = await readAll("projects");
  db.close();
  const rows = (kind) => documents.filter((item) => item.kind === kind);
  const latest = (kind, documentId) => rows(kind)
    .filter((item) => documentId === undefined || item.document_id === documentId)
    .sort((left, right) => right.version - left.version)[0] || null;
  const plan = latest("suite_plan", "suite");
  if (!plan) return { plan: null };
  const slots = [...new Map(rows("fact_slot").map((item) => [item.document_id, item])).values()];
  const briefBasis = slots.map((item) => ({ slot_id: item.document_id, version: item.version }));
  const styleRow = latest("style_spec", "style");
  const confirmRows = rows("generation_confirm").sort((left, right) => left.version - right.version);
  const confirmRow = confirmRows.length > 0 ? confirmRows[confirmRows.length - 1] : null;
  const entries = [...new Map(rows("prompt_version").map((item) => [item.document_id, item])).values()]
    .map((item) => ({ shot_id: item.document_id, record: item.payload, version: item.version }));
  const intake = latest("product_input", "intake");
  const basisByShot = {};
  for (const shot of plan.payload.shots) {
    const spec = latest("shot_spec", shot.shot_id);
    basisByShot[shot.shot_id] = {
      briefBasis,
      suite_version: plan.version,
      style_version: styleRow ? styleRow.version : null,
      shot_spec_version: spec ? spec.version : null,
      platform: { version: domain.PLATFORM_PROFILES.amazon_us.version },
      provider: imageProfile,
    };
  }
  const sheet = domain.buildConfirmationSheet({
    suitePlan: plan.payload,
    promptEntries: entries,
    context: {
      facts: slots.map((item) => ({ slot_id: item.document_id, status: item.payload.status, value: item.payload.value })),
      assets: ((intake && intake.payload.references) || []).map((item) => ({ role: item.role, sha256: item.asset_sha256 })),
    },
    currentBasisByShot: basisByShot,
    providerProfile: imageProfile,
  });
  const snapshot = domain.confirmationSnapshot(sheet);
  const staleness = confirmRow ? domain.confirmationStaleness(confirmRow.payload, snapshot) : null;
  const recomputedHash = confirmRow ? await domain.promptHash(snapshot, { digest: storage.sha256Hex }) : null;
  const project = projects.slice().sort((left, right) =>
    String(right.updated_at || "").localeCompare(String(left.updated_at || "")))[0] || null;
  return {
    sheet: sheet,
    plan_shots: plan.payload.shots.map((shot) => ({ shot_id: shot.shot_id, role_id: shot.role_id })),
    text_roles: [...domain.PLATFORM_PROFILES.amazon_us.on_image_text_roles],
    staleness: staleness,
    recomputed_hash: recomputedHash,
    record: confirmRow ? { version: confirmRow.version, payload: confirmRow.payload } : null,
    confirm_rows: confirmRows.map((item) => ({ version: item.version,
      hash: item.payload.fingerprint ? item.payload.fingerprint.hash : null })),
    prompt_versions: entries.map((item) => ({ shot_id: item.shot_id, version: item.version, hash: item.record.hash })),
    project_state: project ? project.state : null,
    ui: {
      status: document.getElementById("confirm-status").textContent,
      record: document.getElementById("confirm-record").textContent,
      summary: document.getElementById("confirm-summary").textContent,
      blockers: document.getElementById("confirm-blockers").textContent,
      risks: document.getElementById("confirm-risks").textContent,
      action_disabled: document.getElementById("confirm-action").disabled,
      rows: [...document.querySelectorAll("#confirm-list .confirm-shot")].map((node) => ({
        shot_id: node.getAttribute("data-shot-id"),
        blocked: node.getAttribute("data-blocked"),
        text: node.textContent,
      })),
    },
  };
}
"""


def png_bytes(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def load_server_module():
    spec = importlib.util.spec_from_file_location(
        "product_v2_server_under_test", ROOT / "app" / "product_v2_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run_entry(args: list[str], timeout: int = 180) -> dict:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "app" / "server.py"), *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )
    return {"args": args, "rc": completed.returncode,
            "tail": (completed.stdout + completed.stderr).strip().splitlines()[-8:]}


def run_node_checks() -> dict:
    results = []
    for relative in DOMAIN_FILES:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)],
                                   cwd=str(ROOT), capture_output=True, text=True, check=False)
        results.append({"file": relative, "rc": completed.returncode,
                        "stderr": completed.stderr.strip()[-200:]})
    return {"files": results, "ok": all(item["rc"] == 0 for item in results)}


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
            self._send((HARNESS_DIR / "confirm-contract.html").read_bytes(), MIME[".html"])
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


def start_static_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), HarnessHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def read_suite(browser, url: str, variable: str, console_errors: list, page_errors: list) -> dict:
    page = browser.new_page()
    try:
        page.on("console", lambda message: console_errors.append("[suite] " + message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append("[suite] " + str(error)))
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function(
            f"() => window.{variable} && ['passed','failed','crashed'].includes(window.{variable}.status)",
            timeout=90_000,
        )
        return page.evaluate(f"() => window.{variable}")
    finally:
        page.close()


def compile_all(page, shot_ids: list, wait_ms: int = 200, *, force: bool = False) -> None:
    # 本地实现只保留“怎么到达”：真实等待与点击语义归 shared.compile_all
    # （等待自动本地准备落定、只重准备过期图；force=True 用于“改风格后必须出新版本”
    # 的显式重准备场景——此时 stable saved 可能是“新依据下仍有效但版本未前进”的旧版）。
    # 注意：shared.compile_all 以 click 返回（不 await 保存/重渲染/状态派生），而逐图编译的
    # 保存→renderPrompts/renderConfirm→deriveState 是异步链（generation-view.ts:458-463）：
    # 这里必须等到确认区按新版本重渲染后才返回，否则调用方读到的仍是旧 sheet（-05/-06 类红）。
    # 版本基线必须在点击前读取（点击后读到的已是新版本，“+1”就永远等不到）；
    # 只对“本次实际点了编译的图”期待版本前进（expect_bump），没点的图（已是最新 saved）
    # 保持原版本即可——否则会把“没必要重准备的正确跳过”判红。
    before = {item["shot_id"]: item["version"] for item in
              page.evaluate(CONFIRM_PROBE)["prompt_versions"]}
    states = {shot_id: page.get_attribute(
        f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]', "data-prompt-state")
        for shot_id in shot_ids}
    shared.compile_all(page, shot_ids, wait_ms=wait_ms, force=force)
    bump = [shot for shot in shot_ids if force or states.get(shot) == "stale"]
    page.wait_for_function(
        """(wanted) => {
          const rows = [...document.querySelectorAll('#confirm-list .confirm-shot')];
          if (rows.length !== wanted.total) return false;
          return wanted.bump.every((entry) => {
            const node = rows.find((item) => item.getAttribute('data-shot-id') === entry.id);
            if (!node) return false;
            const head = node.textContent || '';
            return head.includes('Prompt v' + entry.version);
          });
        }""",
        arg={"total": len(page.evaluate(CONFIRM_PROBE)["sheet"]["shots"]),
             "bump": [{"id": shot,
                       "version": (before.get(shot) or 0) + 1} for shot in bump]},
        timeout=60_000)



def main() -> int:
    parser = argparse.ArgumentParser(description="V2.3.5 生成前确认验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    node_result = run_node_checks()
    check("V2.3.5-00", "domain / workspace / harness 通过 node --check（ESM 语法门）",
          node_result["ok"],
          {"failed": [item for item in node_result["files"] if item["rc"] != 0][:3]})

    static_server, static_url = start_static_server()
    suites: dict = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                suites["confirm"] = read_suite(
                    browser, static_url + "/harness/confirm-contract.html",
                    "__V2_CONFIRM_RESULTS__", console_errors, page_errors)
                suites["prompt"] = read_suite(
                    browser, static_url + "/harness/prompt-contract.html",
                    "__V2_PROMPT_RESULTS__", console_errors, page_errors)
                suites["specs"] = read_suite(
                    browser, static_url + "/harness/specs-contract.html",
                    "__V2_SPECS_RESULTS__", console_errors, page_errors)
                suites["suite_editor"] = read_suite(
                    browser, static_url + "/harness/suite-editor-contract.html",
                    "__V2_SUITE_EDITOR_RESULTS__", console_errors, page_errors)
            finally:
                browser.close()
    finally:
        static_server.shutdown()
        static_server.server_close()

    suite = suites["confirm"]
    case_ids = [item["id"] for item in suite.get("cases", [])]
    missing = [case for case in EXPECTED_CASES if case not in case_ids]
    failed_cases = [item for item in suite.get("cases", []) if not item.get("ok")]
    check("V2.3.5-01", "H01–H12 契约套件全过且用例齐全",
          suite.get("status") == "passed" and not missing and not failed_cases,
          {"status": suite.get("status"), "missing": missing,
           "failed": [{"id": item["id"], "error": item.get("error")} for item in failed_cases[:3]]})
    negative_seen = [case for case in NEGATIVE_CASES if case in case_ids]
    check("V2.3.5-02", "反向探针确实执行（缺 Prompt / 过期 / 缺依赖 / 参数不符 / 越界 / 失效）",
          negative_seen == NEGATIVE_CASES and not failed_cases,
          {"expected": NEGATIVE_CASES, "seen": negative_seen})
    regression = {name: {"status": value.get("status"), "failed": value.get("failed_ids", [])}
                  for name, value in suites.items() if name != "confirm"}
    check("V2.3.5-02b", "既有契约套件回归：Prompt / 规格 / 套图编辑器全过",
          all(item["status"] == "passed" and not item["failed"] for item in regression.values()),
          regression)

    module = load_server_module()
    from src.providers.v2_fake_image import FakeImageProvider  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: PLC0415

    port = free_port()
    server = module.create_product_v2_server(
        "127.0.0.1", port, provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"))
    # 工厂只建服务器不启动；少了这一行页面拿不到响应，异常又会被下面 finally 的
    # server.shutdown() 永久阻塞吞掉（无输出、无证据、无 traceback）。与 3_6 同形。
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    submit_requests: list[dict] = []
    ui: dict = {}
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v235-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(png_bytes(16, 16, (36, 92, 160)))
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            def on_request(request) -> None:
                if request.method == "POST" and "/api/v2/images/submit" in request.url:
                    try:
                        body = json.loads(request.post_data or "{}")
                    except ValueError:
                        body = {}
                    submit_requests.append({"action_id": body.get("action_id"),
                                            "prompt": body.get("prompt")})

            page.on("request", on_request)

            page.goto(base + "/", wait_until="networkidle")
            page.fill("#new-project-name", "审计商品 · 生成前确认")
            page.click("#create-project")
            expect(page.locator("#project-view")).to_be_visible()
            # 确认区在生成阶段面板内：先切到生成区再判空态（阶段条始终可达）。
            stage_nav.goto(page, "generate")
            expect(page.locator("#confirm-editor")).to_be_hidden()
            # UI 合同§3导航规则:阶段条始终可达,不锁死;「未就绪」由区内空态表达。
            expect(page.locator('#stage-nav [data-stage-nav="generate"]')).to_be_enabled()
            expect(page.locator("#confirm-locked")).to_be_visible()
            # 参考图与商品资料在资料阶段面板内：切回资料区再操作。
            stage_nav.goto(page, "intake")
            page.set_input_files("#ref-file", str(reference))
            expect(page.locator("#ref-list .ref-row")).to_have_count(1)
            page.fill("#intake-name", "便携保温杯")
            page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
            page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
            page.wait_for_timeout(1200)
            opened = page.evaluate(
                "async () => { const db = await new Promise((resolve) => {"
                " const request = indexedDB.open(\"amz-listing-kit-v2\");"
                " request.onsuccess = () => resolve(request.result); });"
                " const rows = await new Promise((resolve) => { const req = db.transaction(\"projects\", \"readonly\")"
                " .objectStore(\"projects\").getAll(); req.onsuccess = () => resolve(req.result); });"
                " db.close(); return rows.map((item) => item.project_id); }")
            page.evaluate(SEED_SLOTS, opened[0])
            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "plan")
            page.click("#suite-seed")
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)
            stage_nav.goto(page, "generate")
            expect(page.locator("#confirm-editor")).to_be_visible()
            expect(page.locator("#confirm-locked")).to_be_hidden()
            expect(page.locator("#confirm-list .confirm-shot")).to_have_count(4)
            first = page.evaluate(CONFIRM_PROBE)
            sheet = first["sheet"]
            prompt_missing = [item for item in sheet["shots"]
                              if "PROMPT_MISSING" in [blocker["code"] for blocker in item["blockers"]]]
            prompt_fixes = [item["blockers"][0]["fix"] for item in prompt_missing]
            check("V2.3.5-03", "套图就绪后确认区解锁：4 张图因缺 Prompt 全部阻断并定位到 Prompt 区",
                  sheet["can_submit"] is False and sheet["blocked"] == 4 and len(prompt_missing) == 4
                  and all(fix["region"] == "prompt" and fix["shot_id"] for fix in prompt_fixes)
                  and first["ui"]["action_disabled"] is True
                  # 意图状态行只报本批可发送计数（generation-view.ts:566-567“本次明确发送 N 张”；
                  # 未编译时意图 sheet=None 即“发送 0 张”）。4 张阻断看 sheet.blocked 与逐图行徽标
                  # （“本次不发送：缺项／过期”，generation-view.ts:619），不看状态行计数。
                  and "发送 0 张" in first["ui"]["status"]
                  and all(row["blocked"] == "True" for row in first["ui"]["rows"])
                  and "参考" in first["ui"]["summary"],
                  {"status": first["ui"]["status"], "blocked": sheet["blocked"],
                   "summary": first["ui"]["summary"][:200]})

            stage_nav.goto(page, "plan")
            page.select_option("#suite-template", "comparison_competitor")
            page.click("#suite-add-template")
            expect(page.locator("#shot-list .shot-row")).to_have_count(5)
            expect(page.locator('#shot-list .shot-row[data-blocked="true"]')).to_have_count(1)
            blocked_probe = page.evaluate(CONFIRM_PROBE)
            blocked_sheet = blocked_probe["sheet"]
            comparison = next(item for item in blocked_sheet["shots"]
                              if item["shot_id"] == "shot_comparison_competitor")
            comparison_codes = [blocker["code"] for blocker in comparison["blockers"]]
            dependency_fix = next(blocker["fix"] for blocker in comparison["blockers"]
                                  if blocker["code"] == "DEPENDENCY_UNSATISFIED")
            check("V2.3.5-04", "缺依赖的对比图被精确阻断并定位到套图规划",
                  blocked_sheet["total"] == 5 and blocked_sheet["blocked"] == 5
                  and "DEPENDENCY_UNSATISFIED" in comparison_codes
                  and "PROMPT_MISSING" in comparison_codes
                  and dependency_fix["region"] == "suite"
                  and "套图规划" in blocked_probe["ui"]["blockers"],
                  {"codes": comparison_codes, "fix": dependency_fix})
            page.click('#shot-list .shot-row[data-shot-id="shot_comparison_competitor"] button:has-text("删除")')
            expect(page.locator("#shot-list .shot-row")).to_have_count(4)

            stage_nav.goto(page, "generate")
            stage_nav.reveal(page, "#prompt-editor")
            page.wait_for_selector("#prompt-editor:not([hidden])", timeout=15_000)
            page.locator('#prompt-list .shot-spec[data-shot-id="shot_main_clean"] .toolbar button').first.click()
            page.wait_for_selector(
                '#prompt-list .shot-spec[data-shot-id="shot_main_clean"][data-prompt-state="saved"]',
                timeout=30_000)
            partial = page.evaluate(CONFIRM_PROBE)
            main_item = next(item for item in partial["sheet"]["shots"] if item["shot_id"] == "shot_main_clean")
            main_record = next(item for item in partial["prompt_versions"] if item["shot_id"] == "shot_main_clean")
            check("V2.3.5-05", "编译主图后状态推进：就绪 1 / 阻断 3，外发摘要与记录一致",
                  partial["sheet"]["ready"] == 1 and partial["sheet"]["blocked"] == 3
                  and partial["sheet"]["can_submit"] is False
                  and main_item["prompt"]["chars"] == partial["sheet"]["external_summary"]["prompt_chars"]
                  and str(partial["sheet"]["external_summary"]["prompt_chars"]) in partial["ui"]["summary"]
                  and len(main_item["references"][0]["sha256_prefix"]) == 12
                  and partial["sheet"]["external_summary"]["model"] == "qwen-image-3.0",
                  {"summary": partial["sheet"]["external_summary"]["statement"][:200],
                   "hash": main_record["hash"][:12]})

            compile_all(page, [item["shot_id"] for item in partial["sheet"]["shots"]
                               if item["prompt"]["version"] is None])
            ready = page.evaluate(CONFIRM_PROBE)
            ready_risks = [risk["code"] for risk in ready["sheet"]["risks"]]
            check("V2.3.5-06", "全部编译后可确认：按钮可用、无阻断、风险仍可见",
                  ready["sheet"]["can_submit"] is True and ready["sheet"]["blocked"] == 0
                  and ready["ui"]["action_disabled"] is False
                  # 意图摘要计数 = 本批可发送张数（generation-view.ts:565-567“本次明确发送 N 张”；
                  # 4_3 的 -03 已按同一合同断言按钮标注“4 张”）。逐图行徽标“本次发送”（:619）。
                  and "发送 4 张" in ready["ui"]["status"]
                  and all(row["blocked"] == "False" for row in ready["ui"]["rows"])
                  and all("本次发送" in row["text"] for row in ready["ui"]["rows"])
                  and "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" in ready_risks
                  and ready["record"] is None,
                  {"status": ready["ui"]["status"], "risks": ready_risks})

            shot_texts = " ".join(row["text"] for row in ready["ui"]["rows"])
            prompt_warnings = page.evaluate(
                """() => [...document.querySelectorAll('#prompt-list .prompt-warning')]
                     .map((node) => node.textContent).join(" / ")""")
            check("V2.3.5-14",
                  "风险提示中文可读：逐图与 Prompt 卡不出现裸规则码，槽位 id 已本地化；"
                  "规则码只留在汇总区与悬浮标题",
                  "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" not in shot_texts
                  and "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE" not in prompt_warnings
                  and "product_category" not in shot_texts
                  and "product_category" not in prompt_warnings
                  and "product_category" not in ready["ui"]["risks"]
                  and ("请人工确认" in shot_texts or "文案不是" in shot_texts),
                  {"prompt": prompt_warnings[:200], "risks": ready["ui"]["risks"][:200]})

            language_messages: dict[str, list[str]] = {}
            for risk in ready["sheet"]["risks"]:
                if risk["code"] != "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE":
                    continue
                language_messages.setdefault(risk["shot_id"], []).append(risk["message"])
            duplicate_counts = {shot: len(items) - len(set(items))
                                for shot, items in language_messages.items()}
            signature_messages = [message for items in language_messages.values()
                                  for message in items if "signature_features" in message]
            check("V2.3.5-15",
                  "同一槽位的语言风险按槽位去重：逐图只出现一条，多值（夹具 2 条）时给出条数",
                  bool(signature_messages)
                  and all(count == 0 for count in duplicate_counts.values())
                  and all("2 条" in message for message in signature_messages),
                  {"messages": signature_messages[:4], "duplicates": duplicate_counts})

            # V2.6.17：语言风险只对「允许图中文字」的角色成立 —— 场景图/细节图不排文字，
            # 报「图中将逐字保留原文」是误报；同时有文字的角色要给可操作建议。
            role_by_shot = {item["shot_id"]: item["role_id"] for item in ready["plan_shots"]}
            text_roles = set(ready["text_roles"])
            language_risks = [risk for risk in ready["sheet"]["risks"]
                              if risk["code"] == "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE"]
            false_positive = [risk for risk in language_risks
                              if role_by_shot.get(risk["shot_id"]) not in text_roles]
            actionable = [risk for risk in language_risks if "建议" in risk["message"]]
            check("V2.3.5-16",
                  "语言风险只出现在允许图中文字的角色（文字角色带可操作建议，无文字角色不误报）",
                  bool(language_risks) and not false_positive
                  and len(actionable) == len(language_risks),
                  {"false_positive": [risk["shot_id"] for risk in false_positive],
                   "roles": role_by_shot, "text_roles": sorted(text_roles),
                   "messages": [risk["message"] for risk in language_risks][:3]})

            shot_ids = [item["shot_id"] for item in ready["sheet"]["shots"]]
            gate = shared.confirm_and_submit(page, expect, None, submit_requests,
                                             shot_ids=shot_ids)
            assert gate["ok"], f"确认必须产生本次授权的新消费：{gate['after_actions']}"
            submits = len(submit_requests)
            confirmed = page.evaluate(CONFIRM_PROBE)
            record = confirmed["record"]
            check("V2.3.5-07", "点击确认写入 generation_confirm v1 并整套提交：指纹一致、授权逐图消费、各提交一次",
                  record is not None and record["version"] == 1
                  and record["payload"]["fingerprint"]["hash"] == confirmed["recomputed_hash"]
                  and confirmed["staleness"]["stale"] is False
                  and confirmed["project_state"] == "READY_TO_GENERATE"
                  and len(record["payload"]["shots"]) == 4
                  and submits == 4,
                  {"state": confirmed["project_state"],
                   "hash": record["payload"]["fingerprint"]["hash"][:12] if record else None,
                   "submits": submits})

            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.fill("#style-background", "深灰无缝背景")
            page.click("#style-save")
            stage_nav.goto(page, "generate")
            stale = page.evaluate(CONFIRM_PROBE)
            stale_fields = [reason["field"] for reason in stale["staleness"]["reasons"]]
            check("V2.3.5-08", "改公共风格使确认失效并回落 PLAN_REVIEW，存储判失效",
                  stale["staleness"]["stale"] is True
                  and any(field.startswith("shots.") for field in stale_fields)
                  and stale["project_state"] == "PLAN_REVIEW"
                  and stale["sheet"]["can_submit"] is False
                  and stale["record"] is not None and stale["record"]["version"] == 1,
                  {"fields": stale_fields[:4], "state": stale["project_state"]})

            # 新语义下“改风格→重编译→再次确认”不产生任何外发：已提交授权仍登记在册，
            # 但第二批摘要是空集（旧批次队列已消费完），按钮按不自动重提保持禁用。
            # -10 因此不能再走“点击并期待 v2”的旧单批次流程；它现在证明三条新语义：
            # (1) UI 把空集诚实展示为“确认并生成 0 张”而不是静默无动作（generation-view.ts:652-653
            #     按 sending.total 渲染计数；565-567 行状态文案声明“已有成功、进行中或 Unknown 不自动重提”）；
            # (2) 确认记录保持 v1 单版本（append-only：无新授权即无新版本，不伪造 v2）；
            # (3) 要让按钮重新可用，唯一真实路径是显式另发新动作（不是第二次点击）。
            compile_all(page, [item["shot_id"] for item in stale["sheet"]["shots"]], force=True)
            reconfirm_ready = page.evaluate(CONFIRM_PROBE)
            check("V2.3.5-09", "重新编译后确认单恢复可提交形状（Prompt 版本全部前进），但摘要拒绝复发旧图",
                  reconfirm_ready["sheet"]["can_submit"] is True
                  # 只断言“各自相对初始 v1 前进”（不写死 v2）：改风格后自动本地准备 + 显式重准备
                  # 可能让同一张图前进不止一次，写死 v2 会把合法的新语义判红。
                  and all(item["version"] >= 2 for item in reconfirm_ready["prompt_versions"]),
                  {"versions": reconfirm_ready["prompt_versions"]})

            # 到达与断言都在同一条真实用户路径上：等自动本地准备落定后直接读按钮与摘要。
            page.wait_for_function(
                "() => document.getElementById('confirm-status').textContent.includes('本次明确发送')",
                timeout=60_000)
            stage_nav.goto(page, "generate")
            expect(page.locator("#confirm-editor")).to_be_visible()
            refused = {
                "disabled": page.locator("#confirm-action").is_disabled(),
                "text": page.locator("#confirm-action").inner_text(),
                "status": page.locator("#confirm-status").inner_text(),
            }
            second_record = page.evaluate(CONFIRM_PROBE)
            check("V2.3.5-10", "重编译后不自动重提：按钮禁用并标注发送 0 张，确认记录不伪造新版本",
                  refused["disabled"] is True
                  and "0 张" in refused["text"]
                  and "不自动重提" in refused["status"]
                  and second_record["record"] is not None
                  and second_record["record"]["version"] == 1
                  and len(second_record["confirm_rows"]) == 1,
                  {"refused": refused, "rows": second_record["confirm_rows"]})

            screenshot_rel = f"evals/product-v2/v2.3.5-pre-generation-confirm-{stamp}.png"
            page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
            screenshots.append(screenshot_rel)

            page.reload(wait_until="networkidle")
            stage_nav.goto(page, "generate")
            expect(page.locator("#confirm-editor")).to_be_visible()
            reloaded = page.evaluate(CONFIRM_PROBE)
            check("V2.3.5-11", "刷新恢复：确认记录、指纹与存储一致（v1 单版本，不自动重提故按钮保持禁用）",
                  reloaded["record"] is not None
                  and reloaded["record"]["version"] == 1
                  and len(reloaded["confirm_rows"]) == 1
                  and reloaded["record"]["payload"]["fingerprint"]["hash"] == reloaded["recomputed_hash"]
                  and reloaded["staleness"]["stale"] is False
                  and reloaded["project_state"] == "READY_TO_GENERATE"
                  and reloaded["ui"]["action_disabled"] is True
                  and "0 张" in reloaded["ui"]["status"]
                  and len(reloaded["ui"]["rows"]) == 4,
                  {"state": reloaded["project_state"],
                   "hash": reloaded["record"]["payload"]["fingerprint"]["hash"][:12] if reloaded["record"] else None})
            ui["final"] = {"record_version": reloaded["record"]["version"],
                           "fingerprint": reloaded["record"]["payload"]["fingerprint"]["hash"],
                           "state": reloaded["project_state"],
                           "external_summary": reloaded["sheet"]["external_summary"],
                           "prompt_versions": reloaded["prompt_versions"]}
            context.close()
    finally:
        server.shutdown()
        server.server_close()

    check("V2.3.5-12", "契约会话与 UI 会话零 console error / page error",
          not console_errors and not page_errors,
          {"console": console_errors[:5], "page": page_errors[:5]})

    entry = run_entry(["--check"])
    check("V2.3.5-13", "正式入口自检仍全过（V2.3.5 不破坏既有入口）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明生成前确认在真实浏览器里可核对、可定位、可失效：确认单由套图计划、每图 PromptVersion、参考图与"
        "平台/Provider 档确定性派生；缺 Prompt、记录非法、快照与文本不一致、平台/Provider 不符、参考图数量越界、"
        "依赖未满足与 Prompt 过期都会阻断并给出可操作位置（fix.region）；外发摘要只写真实会发送的模型参数与"
        "参考图角色 + sha256 前 12 位，不含图片字节；风险（语言不一致、平台覆盖、主图忽略文案）必须可见但允许确认；"
        "确认记录 append-only 并绑定指纹，上游或 Prompt 前进即失效、状态回落 PLAN_REVIEW，重新确认写新版本。"
        "全程 0 次真实模型调用，不发图、不生成候选、不证明出图质量；真实生成属于 Phase 4，审核与返工属于 Phase 5。"
    )
    report = {
        "task": "V2.3.5",
        "suite_id": "v2.3.5-confirm",
        "status": status,
        "finished_at": finished_at,
        "model_calls": 0,
        "checks": checks,
        "suites": suites,
        "ui_flow": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshots": screenshots,
        "boundary": boundary,
    }
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.3.5-pre-generation-confirm-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.3.5-pre-generation-confirm-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.3.5 pre-generation confirm",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        "model_calls: 0 (offline domain + UI flow)",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
    ]
    if screenshots:
        lines.append("screenshot: " + screenshots[0])
    lines += ["", "CHECKS"]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False)[:600])
    lines += ["", "SUITE CASES"]
    for item in suite.get("cases", []):
        lines.append(f"- [{'PASS' if item.get('ok') else 'FAIL'}] {item.get('id')} {item.get('title')}")
        if not item.get("ok"):
            lines.append("  error: " + json.dumps(item.get("error"), ensure_ascii=False))
    for name, value in regression.items():
        lines.append(f"- [{'PASS' if value['status'] == 'passed' else 'FAIL'}] 回归 {name} "
                     f"({value['status']}, failed={value['failed']})")
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.3.5 生成前确认验证")
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
