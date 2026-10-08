#!/usr/bin/env python
"""V2 验证共享 helpers：正式 server/数据夹具与少数共同业务操作。

归属：tools/verify_v2_*.py 之间不再互相 load_module 当共享库；
真正共享的正式 server 装置、数据夹具（PNG/端口/读套件/静态 harness 服务/正式入口）
与少数共同 UI 业务操作（compile_all、confirm_and_submit 新增消费证明）集中在此。
数据探针（SEED_SLOTS / PROBE / HASH_ASSET / chain_of / candidate_of / row_of /
reviews_for / candidate_json / review_json）也只在此一份定义：验证器直接用
shared.<name>，不互相 import、不复制、不包一层同名壳。
产品语义唯一权威仍是 app/product_v2_* 与 domain/；本文件不复制整套 E2E，
不进产品入口，不新增 registry/CI 登记。

已有公共工具引导复用：
- 六阶段导航仍用 tools/v2_stage_nav.py（goto/reveal），本文件不另造导航；
- 无场景装置的静态走查仍用 tools/v2_test_server.py，本文件只补“可注场景”
  的正式 product server 装置（与 v2_test_server 同一 ProductV2Handler 路径）。
"""
from __future__ import annotations

import hashlib
import json
import time
import zipfile
import importlib.util
import socket
import struct
import sys
import threading
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402
from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider  # noqa: E402


def current_review_contract() -> str:
    """审核报告合同版本：唯一权威是产品 domain/review.js 的 REVIEW_CONTRACT_VERSION。

    为什么放共享里：V2.R5.1 切分（111711e）把 5_1 的本地 current_review_contract 删掉，
    5_3 的三处 shared.current_review_contract 调用当时就断了（AttributeError）；
    恢复时读产品常量，不写死字面量，断言仍对比展开后的报告文本。
    """
    import re as _re

    text = (ROOT / "app" / "product_v2" / "domain" / "review.js").read_text(encoding="utf-8")
    match = _re.search(r'REVIEW_CONTRACT_VERSION\s*=\s*"([^"]+)"', text)
    if match is None:
        raise SystemExit("review.js 里找不到 REVIEW_CONTRACT_VERSION。")
    return match.group(1)


ATTEMPT_ANY_JS = (
    "() => document.querySelectorAll("
    "'#attempt-list .attempt-row[data-attempt-state]').length > 0"
)


def png_bytes(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """不用第三方库生成一张真实 PNG（RGB，无压缩过滤）。"""
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def load_server_module(name: str = "product_v2_server_under_test"):
    """正式产品 server 模块（app/product_v2_server.py），与产品入口同一处理器。"""
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "app" / "product_v2_server.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def start_product_server(port: int, *, image_scenario: str = "ok",
                         semantic_scenario: str = "ok",
                         review_scenario: str = "ok",
                         suite_scenario: str = "ok",
                         image_size: int = 1200,
                         image_factory=None, semantic_factory=None,
                         review_factory=None, suite_factory=None,
                         module=None):
    """正式处理器 + 显式离线 Provider；自定义工厂只用于有状态场景装置。"""
    server_module = module or load_server_module()
    image = FakeImageProvider(scenario=image_scenario, size=image_size)
    semantic = FakeSemanticProvider(scenario=semantic_scenario)
    review = FakeReviewProvider(scenario=review_scenario)
    suite = FakeSuiteReviewProvider(scenario=suite_scenario)
    server = server_module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=semantic_factory or (lambda: semantic),
        image_provider_factory=image_factory or (lambda: image),
        review_provider_factory=review_factory or (lambda: review),
        suite_review_provider_factory=suite_factory or (lambda: suite))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, {"image": image, "semantic": semantic,
                    "review": review, "suite": suite}


def read_suite(browser, url: str, variable: str,
               console_errors: list | None = None,
               page_errors: list | None = None) -> dict:
    """读 harness 契约套件结果（行为判据：window 变量落定 passed/failed/crashed）。"""
    page = browser.new_page()
    try:
        if console_errors is not None:
            page.on("console", lambda message: console_errors.append("[suite] " + message.text)
                    if message.type == "error" else None)
        if page_errors is not None:
            page.on("pageerror", lambda error: page_errors.append("[suite] " + str(error)))
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function(
            f"() => window.{variable} && ['passed','failed','crashed']"
            f".includes(window.{variable}.status)",
            timeout=90_000)
        return page.evaluate(f"() => window.{variable}")
    finally:
        page.close()




MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def compile_all(page, shot_ids: list, wait_ms: int = 120, *, force: bool = False) -> None:
    """等待自动本地准备；只重准备过期图，显式版本前进案例用 force。"""
    import v2_stage_nav as stage_nav

    stage_nav.goto(page, "generate")
    stage_nav.reveal(page, "#prompt-editor")
    for shot_id in shot_ids:
        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
        page.wait_for_selector(card, timeout=30_000)
    page.wait_for_function(
        """(ids) => ids.every((id) => {
          const node = document.querySelector('#prompt-list .shot-spec[data-shot-id="' + id + '"]');
          return node && ['saved', 'stale'].includes(node.dataset.promptState);
        })""", arg=shot_ids, timeout=30_000)
    for shot_id in shot_ids:
        card = f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]'
        if force or page.get_attribute(card, "data-prompt-state") == "stale":
            page.locator(card + " .toolbar button").first.click()
            page.wait_for_selector(card + '[data-prompt-state="saved"]', timeout=30_000)
        page.wait_for_timeout(wait_ms)

def attempt_actions(probe_data: dict) -> dict[str, str]:
    """probe 的 attempt_chains → {shot_id: 最新 action_id}（无链时为空）。"""
    chains = (probe_data or {}).get("attempt_chains") or {}
    out: dict[str, str] = {}
    for shot_id, chain in chains.items():
        if chain:
            action = (chain[-1].get("payload") or {}).get("action_id")
            if action:
                out[shot_id] = action
    return out


def confirm_and_submit(page, expect, probe=None, submit_requests: list | None = None,
                       timeout: int = 120_000, *, shot_ids: list[str],
                       submitted_shots: list[str] | None = None,
                       settle: bool = True, click_count: int = 1) -> dict:
    """一次明确提交：证明新授权版本/指纹与每张图的新 action 一一消费。

    shot_ids 是本次授权的准确集合；停止案例可指定 submitted_shots 为已发送前缀。
    浏览器请求捕获始终启用，不以任意旧行或调用方未给捕获器作为通过条件。
    """
    if not shot_ids or len(set(shot_ids)) != len(shot_ids):
        raise AssertionError("本次授权必须明确指定非空且无重复的 shot_ids")
    wanted = shot_ids if submitted_shots is None else submitted_shots
    if not wanted or not set(wanted) <= set(shot_ids):
        raise AssertionError("已发送集合必须是本次授权的非空子集")
    before = probe() if probe else page.evaluate(PROBE)
    authority_before = page.evaluate(AUTHORIZATION_PROBE)
    known_confirmations = {(row["project_id"], row["document_id"], row["version"])
                           for row in authority_before["confirmations"]}
    known_actions = {row["payload"]["action_id"] for row in authority_before["attempts"]}
    requests: list[dict] = []
    capture_start = len(submit_requests) if submit_requests is not None else 0

    def capture(request) -> None:
        if request.method == "POST" and request.url.split("?", 1)[0].endswith("/api/v2/images/submit"):
            requests.append(json.loads(request.post_data or "{}"))

    page.on("request", capture)
    try:
        expect(page.locator("#confirm-action")).to_be_enabled()
        page.click("#confirm-action", click_count=click_count)
        deadline = time.monotonic() + timeout / 1000
        while True:
            authority_after = page.evaluate(AUTHORIZATION_PROBE)
            fresh = [row for row in authority_after["confirmations"]
                     if (row["project_id"], row["document_id"], row["version"])
                     not in known_confirmations]
            latest: dict[tuple[str, str], dict] = {}
            for row in authority_after["attempts"]:
                record = row["payload"]
                if record["action_id"] in known_actions:
                    continue
                key = (row["project_id"], record["action_id"])
                if key not in latest or row["version"] > latest[key]["version"]:
                    latest[key] = row
            actions = list(latest.values())
            new_shots = [row["payload"]["shot_id"] for row in actions]
            sent_actions = [request.get("action_id") for request in requests]
            if (set(wanted) <= set(new_shots)
                    and all(row["payload"]["action_id"] in sent_actions
                            for row in actions if row["payload"]["shot_id"] in wanted)):
                if not settle or all(row["payload"]["state"] in ("succeeded", "failed", "unknown")
                                     for row in actions):
                    break
            if time.monotonic() >= deadline:
                # 按钮/摘要区文案是判定「产品中止提交并展示变化」还是「静默无动作」的唯一现场证据。
                area = page.evaluate("""() => {
                  const el = (id) => document.getElementById(id);
                  return {
                    action: (el("confirm-action") || {}).textContent || "",
                    action_disabled: el("confirm-action") ? el("confirm-action").disabled : null,
                    status: (el("confirm-status") || {}).textContent || "",
                    record: (el("confirm-record") || {}).textContent || "",
                    error: (el("confirm-error") || {}).textContent || "",
                    attempt_status: (el("attempt-status") || {}).textContent || "",
                    progress: (el("batch-progress") || {}).textContent || "",
                    queues: (el("generation-queues") || {}).textContent || "",
                  };
                }""")
                raise AssertionError(f"本次授权消费未落定：fresh={fresh}, actions={actions}, "
                                     f"requests={requests}, confirm_area={area}")
            page.wait_for_timeout(50)
        confirmation = fresh[0] if len(fresh) == 1 else None
        payload = (confirmation or {}).get("payload") or {}
        authorized = {shot["shot_id"]: shot for shot in payload.get("shots", [])}
        auth_hash = (payload.get("fingerprint") or {}).get("hash")
        bindings_ok = bool(confirmation) and confirmation["hash_valid"]
        for row in actions:
            record = row["payload"]
            source = record.get("authorization") or {}
            prompt = record.get("prompt") or {}
            shot = authorized.get(record["shot_id"]) or {}
            bindings_ok = bindings_ok and (
                row["project_id"] == confirmation["project_id"]
                and source.get("document_id") == confirmation["document_id"]
                and source.get("version") == confirmation["version"]
                and source.get("hash") == auth_hash
                and prompt.get("version") == shot.get("prompt_version")
                and prompt.get("hash") == shot.get("prompt_hash"))
        action_ids = [row["payload"]["action_id"] for row in actions]
        captured = (submit_requests[capture_start:] if submit_requests is not None else requests)
        captured_actions = [request.get("action_id") for request in captured]
        ok = (bindings_ok and set(authorized) == set(shot_ids)
              and len(actions) == len(wanted) and set(new_shots) == set(wanted)
              and len(requests) == len(wanted) and len(set(action_ids)) == len(wanted)
              and set(sent_actions) == set(action_ids)
              and all(sent_actions.count(action_id) == 1 for action_id in action_ids)
              and captured_actions == sent_actions)
        after = probe() if probe else page.evaluate(PROBE)
        return {"before": before, "after": after, "captured": captured,
                "captured_actions": captured_actions, "new_shots": new_shots,
                "before_actions": attempt_actions(before), "after_actions": attempt_actions(after),
                "confirmation": confirmation, "consumed_actions": actions, "ok": bool(ok)}
    finally:
        page.remove_listener("request", capture)


AUTHORIZATION_PROBE = """
async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const documents = await new Promise((resolve, reject) => {
    const request = db.transaction("documents", "readonly").objectStore("documents").getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const canonical = (value) => Array.isArray(value) ? value.map(canonical)
    : value && typeof value === "object"
      ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]))
      : value;
  const confirmations = [];
  for (const row of documents.filter((item) => item.kind === "generation_confirm")) {
    const fingerprint = row.payload.fingerprint || {};
    const digest = await crypto.subtle.digest("SHA-256",
      new TextEncoder().encode(JSON.stringify(canonical(fingerprint.snapshot))));
    const hash = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
    confirmations.push({ ...row, hash_valid: hash === fingerprint.hash });
  }
  return { confirmations, attempts: documents.filter((item) => item.kind === "generation_attempt") };
}
"""


class HarnessHandler(__import__("http.server", fromlist=["BaseHTTPRequestHandler"]).BaseHTTPRequestHandler):
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
        product_dir = ROOT / "app" / "product_v2"
        harness_dir = ROOT / "evals" / "product-v2" / "harness"
        if path.startswith("/harness/"):
            candidate = (harness_dir / path[len("/harness/"):]).resolve()
            if str(candidate).startswith(str(harness_dir.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(),
                           MIME.get(candidate.suffix, "application/octet-stream"))
                return
        else:
            candidate = (product_dir / path.lstrip("/")).resolve()
            if str(candidate).startswith(str(product_dir.resolve())) and candidate.is_file():
                self._send(candidate.read_bytes(),
                           MIME.get(candidate.suffix, "application/octet-stream"))
                return
        self.send_error(404)


def start_static_server():
    import threading as _threading
    from http.server import ThreadingHTTPServer as _Server
    server = _Server(("127.0.0.1", 0), HarnessHandler)
    _threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def run_entry(args: list[str], timeout: int = 180) -> dict:
    import os as _os
    import subprocess as _subprocess
    import sys as _sys
    env = {**_os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    completed = _subprocess.run(
        [_sys.executable, "-B", str(ROOT / "app" / "server.py"), *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )
    return {"args": args, "rc": completed.returncode,
            "tail": (completed.stdout + completed.stderr).strip().splitlines()[-10:]}


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
        evidence: [{ kind: "user", ref: "v2-verify-seed" }], depends_on: [],
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
  const projects = await read("projects");
  const assets = await read("assets");
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
  const reviews = documents.filter((row) => row.kind === "review_report")
    .map((row) => ({ document_id: row.document_id, version: row.version, payload: row.payload }))
    .sort((left, right) => (left.document_id + left.version)
      .localeCompare(right.document_id + right.version));
  const plans = documents.filter((item) => item.kind === "suite_plan")
    .sort((left, right) => left.version - right.version);
  const plan = plans.length ? plans[plans.length - 1] : null;
  const rows = [...document.querySelectorAll("#attempt-list .attempt-row")].map((node) => {
    const img = node.querySelector(".attempt-preview img");
    const candidateMeta = node.querySelector(".attempt-candidate");
    const reviewNode = node.querySelector(".attempt-review");
    return {
      shot_id: node.getAttribute("data-shot-id"),
      state: node.getAttribute("data-attempt-state"),
      candidate_meta: candidateMeta ? candidateMeta.textContent : null,
      review: reviewNode ? {
        text: reviewNode.textContent,
        summary: reviewNode.getAttribute("data-review-summary"),
        contract: reviewNode.getAttribute("data-review-contract"),
        candidate: reviewNode.getAttribute("data-review-candidate"),
      } : null,
      preview: img ? {
        src: img.getAttribute("src") || "",
        complete: img.complete,
        natural_width: img.naturalWidth,
      } : null,
      buttons: [...node.querySelectorAll("button")].map((item) =>
        ({ text: item.textContent, disabled: item.disabled })),
    };
  });
  const errorNode = document.getElementById("attempt-error");
  return {
    project_ids: projects.map((item) => item.project_id),
    shot_ids: plan ? plan.payload.shots.map((shot) => shot.shot_id) : [],
    attempt_chains: chains,
    candidate_chains: candidates,
    review_reports: reviews,
    asset_rows: assets.map((item) => ({
      sha256: item.sha256, media_type: item.media_type, byte_size: item.byte_size,
      width: item.width, height: item.height, role: item.role,
      has_blob: item.blob instanceof Blob,
    })),
    ui: {
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
  return { found: true, sha256: hex, byte_size: buffer.byteLength };
}
"""


def chain_of(data: dict, shot_id: str) -> list:
    return data["attempt_chains"].get(shot_id, [])


def candidate_of(data: dict, shot_id: str) -> list:
    return data["candidate_chains"].get(shot_id, [])


def row_of(data: dict, shot_id: str) -> dict | None:
    return next((row for row in data["ui"]["rows"] if row["shot_id"] == shot_id), None)


def reviews_for(data: dict, candidate_id: str) -> list:
    return [item for item in data["review_reports"] if item["document_id"] == candidate_id]


def candidate_json(data: dict, shot_id: str) -> str:
    import json as _json
    return _json.dumps(candidate_of(data, shot_id), ensure_ascii=False, sort_keys=True)


def review_json(data: dict, candidate_id: str) -> str:
    import json as _json
    return _json.dumps(reviews_for(data, candidate_id), ensure_ascii=False, sort_keys=True)
OVERFLOW_PROBE = """() => ({
  scroll: document.documentElement.scrollWidth,
  client: document.documentElement.clientWidth,
  current_visible: (() => {
    const el = document.querySelector('#stage-nav [data-stage-nav].is-current');
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return rect.left >= -1 && rect.right <= window.innerWidth + 1;
  })(),
})"""

FOCUS_PROBE = """() => {
  const el = document.activeElement;
  if (!el) return null;
  return { id: el.id || null, cls: String(el.className || ""), shot: el.getAttribute
    ? el.getAttribute("data-shot-id") : null };
}"""

SHOT_IDS = """() => [...document.querySelectorAll('#shot-list .shot-row')]
  .map((row) => row.getAttribute('data-shot-id'))"""

ATTEMPT_STATES = """() => Object.fromEntries(
  [...document.querySelectorAll('#attempt-list .attempt-row[data-shot-id]')]
    .map((row) => [row.getAttribute('data-shot-id'),
                   row.getAttribute('data-attempt-state')]))"""

def confirm_slots(page) -> int:
    guard = 0
    while (page.locator("#slot-list .slot-row")
           .get_by_role("button", name="确认", exact=True).count() > 0 and guard < 30):
        (page.locator("#slot-list .slot-row")
         .get_by_role("button", name="确认", exact=True).first.click())
        page.wait_for_timeout(200)
        guard += 1
    # “填值并确认”是两步：先点开行内编辑器，再填确定性人工值提交。
    # 只为让走查继续，不代表产品自动填值。
    for _ in range(30):
        fill_open = page.locator("#slot-list .slot-row:not([hidden])").get_by_role(
            "button", name="填值并确认", exact=True)
        if fill_open.count() == 0:
            break
        fill_open.first.click()
        page.wait_for_timeout(200)
        guard += 1
    for _ in range(30):
        pending = page.locator("#slot-list .slot-row:not([hidden])")
        if pending.count() == 0:
            break
        row = pending.first
        fill = row.locator('[data-role="value"], #slot-editor-value')
        if fill.count():
            fill.first.fill("走查人工确认值")
        confirm = row.get_by_role("button", name="确认", exact=True)
        if confirm.count() == 0:
            break
        confirm.first.click()
        page.wait_for_timeout(200)
        guard += 1
    return guard




def wait_terminal(page, ids: list[str], timeout: int = 60_000) -> None:
    page.wait_for_function(
        """(ids) => ids.every((shotId) => {
             const node = document.querySelector(
               '#attempt-list .attempt-row[data-shot-id="' + shotId + '"]');
             const state = node && node.getAttribute('data-attempt-state');
             return state === 'succeeded' || state === 'failed' || state === 'unknown';
           })""", arg=ids, timeout=timeout)


def fill_intake(page, reference: Path, name: str = "UI3 验收商品") -> None:
    page.set_input_files("#ref-file", str(reference))
    page.wait_for_selector("#ref-list .ref-row", timeout=10_000)
    page.fill("#intake-name", name)
    page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封，杯身哑光。")
    page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
    try:
        page.wait_for_selector("#analyze-run:not([disabled])", timeout=15_000)
    except Exception as error:  # noqa: BLE001 - 把「分析按钮为何不可用」的现场一并留证
        gate = page.evaluate("""() => {
          const el = (id) => document.getElementById(id);
          const value = (id) => { const n = el(id); return n ? n.value : null; };
          const visible = (node) => Boolean(node && !node.hidden && node.offsetParent !== null);
          return {
            refs: document.querySelectorAll("#ref-list .ref-row").length,
            name: value("intake-name"),
            description: value("intake-description"),
            selling_points: value("intake-selling-points"),
            analyze_disabled: el("analyze-run") ? el("analyze-run").disabled : null,
            analyze_gate: (el("analyze-gate") || {}).textContent || "",
            analyze_gate_visible: visible(el("analyze-gate")),
            intake_locked_visible: visible(el("intake-locked")),
            home_error: (el("home-error") || {}).textContent || "",
            boot_error: (el("boot-error") || {}).textContent || "",
            capability_gap: el("capability-notice") ? (el("capability-notice").dataset.errorGap ?? null) : null,
            phase: window.__v2SessionProbe ? window.__v2SessionProbe.phase : "no-probe",
          };
        }""")
        raise AssertionError(f"分析按钮未就绪：{type(error).__name__}: {error}\ngate={gate}") from error


def create_project(page, name: str, reference: Path, *, keyboard: bool = False) -> None:
    if keyboard:
        page.focus("#new-project-name")
        page.keyboard.type(name)
        page.keyboard.press("Enter")
    else:
        page.fill("#new-project-name", name)
        page.click("#create-project")
    # R3.3：新建即打开——不再回列表行点 open；等待即等“工作台已完整装载”。
    page.wait_for_selector("#project-view:not([hidden])", timeout=15_000)
    page.wait_for_function(
        "() => (document.getElementById('project-view') || {}).dataset.ready === '1'",
        timeout=15_000)
    fill_intake(page, reference, name)
def collect(page) -> dict:
    logs = {"console": [], "page": [], "http": []}
    page.on("console", lambda message: logs["console"].append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: logs["page"].append(str(error)))
    page.on("response", lambda response: logs["http"].append(
        f"{response.status} {response.url}") if response.status >= 400 else None)
    return logs


def digest_untouched(before: dict, after: dict, document_ids: set[str]) -> bool:
    """这些 document_id 的所有行（含 payload 摘要）在前后完全一致。"""

    left = [row for row in before["rows"] if row["document_id"] in document_ids]
    right = [row for row in after["rows"] if row["document_id"] in document_ids]
    return left == right


def digest_kept_prefix(before: dict, after: dict) -> bool:
    """全部旧记录的身份、版本和 payload 摘要逐条保留。"""
    table = {(row["kind"], row["document_id"], row["version"]): row for row in after["rows"]}
    return all(table.get((row["kind"], row["document_id"], row["version"])) == row
               for row in before["rows"])


def walk_to_adoption(page, name: str, reference: Path, *, run_vlm: bool = False) -> list[str]:
    """用户资料→事实确认→方案→一次外发→逐图人工采用。"""
    import v2_stage_nav as stage_nav
    from playwright.sync_api import expect

    create_project(page, name, reference)
    page.click("#analyze-run")
    stage_nav.goto(page, "understand")
    page.wait_for_selector("#slot-list .slot-row:not([hidden])", timeout=30_000)
    confirm_slots(page)
    page.click("#stage-next-understand")
    page.click("#suite-seed")
    page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
    page.click("#stage-next-plan")
    shots = page.evaluate(SHOT_IDS)
    compile_all(page, shots)
    result = confirm_and_submit(page, expect, shot_ids=shots)
    assert result["ok"], f"新授权与逐图消费不一致：{result}"
    if run_vlm:
        for shot_id in shots:
            button = page.locator(
                f'#attempt-list .attempt-row[data-shot-id="{shot_id}"] button[data-review-action]')
            expect(button).to_be_enabled()
            button.click()
            page.wait_for_function(
                """async (id) => {
                  const db = await new Promise((resolve, reject) => {
                    const request = indexedDB.open("amz-listing-kit-v2");
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                  });
                  const docs = await new Promise((resolve, reject) => {
                    const request = db.transaction("documents", "readonly").objectStore("documents").getAll();
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                  });
                  db.close();
                  return docs.some((row) => row.kind === "review_report" && row.payload.shot_id === id
                    && row.payload.vlm && row.payload.vlm.outcome !== "not_run");
                }""", arg=shot_id, timeout=60_000)
    page.click("#stage-next-review")
    for shot_id in shots:
        page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] button:has-text("采用候选")')
        page.wait_for_selector(
            f'#review-list .review-card[data-shot-id="{shot_id}"][data-selection-state="current"]',
            timeout=15_000)
    return shots


GATE_STATE = """() => ({
  status: (document.getElementById('deliver-status') || {}).textContent || '',
  disabled: (document.getElementById('deliver-export') || {}).disabled,
  findings: [...document.querySelectorAll('#delivery-gate .gate-finding')].map((node) => ({
    rule: node.getAttribute('data-rule-id'),
    severity: node.getAttribute('data-severity'),
    jumps: node.querySelectorAll('button[data-shot-id]').length })),
  unknowns: [...document.querySelectorAll('#delivery-unknowns .gate-unknown')].map((node) => ({
    rule: node.getAttribute('data-rule-id'),
    label: (node.querySelector('button') || {}).textContent || '',
    disabled: (node.querySelector('button') || {}).disabled === true })),
  result: (document.getElementById('delivery-result') || {}).textContent || '',
  rows: [...document.querySelectorAll('#delivery-gate .gate-row')].map((row) => ({
    shot_id: row.getAttribute('data-shot-id'),
    state: row.getAttribute('data-selection-state') })) })"""


SUITE_FINDINGS_JS = """(scope) => ({
  status: ((document.getElementById(scope.status) || {}).textContent || '').trim(),
  findings: [...document.querySelectorAll(scope.list + ' .suite-finding')].map((node) => ({
    rule: node.getAttribute('data-rule-id'),
    severity: node.getAttribute('data-severity'),
    jumps: node.querySelectorAll('button[data-shot-id]').length })) })"""

SUITE_PROBE = ("() => (" + SUITE_FINDINGS_JS + ")({status: 'suite-review-status', "
               "list: '#suite-review-findings'})")
DELIVER_SUITE_PROBE = ("() => (" + SUITE_FINDINGS_JS + ")({status: 'delivery-suite-status', "
                       "list: '#delivery-suite-findings'})")


def wait_gate(page, timeout: int = 30_000) -> dict:
    page.wait_for_function(
        "() => document.querySelectorAll('#delivery-gate .gate-finding').length > 0",
        timeout=timeout)
    page.wait_for_timeout(250)
    return page.evaluate(GATE_STATE)


def walk_to_deliver(page, name: str, reference: Path, *,
                    run_vlm: bool = False) -> tuple[list[str], dict]:
    """走到交付阶段：资料 → 理解 → 方案 → 生成（可选逐个 VLM 复核）→ 采用 → 整套检查。"""
    shots = walk_to_adoption(page, name, reference, run_vlm=run_vlm)
    page.click("#suite-review-run")
    page.wait_for_function(
        "() => (document.getElementById('suite-review-status') || {}).textContent.indexOf('整套检查 ') >= 0",
        timeout=60_000)
    probes = {"suite_review": page.evaluate(SUITE_PROBE)}
    # B01/RC16 回归：交付前在生成阶段再次编译首张图（当前 Prompt 头前进），旧采用
    # 候选的原 action 冻结 Prompt 不变；交付 manifest 必须记旧冻结版本，不得跟随当前头。
    page.click('[data-stage-nav="generate"]')
    compile_all(page, shots[:1], force=True)
    page.click('[data-stage-nav="deliver"]')
    page.wait_for_timeout(400)
    probes["b01_manifest_provenance"] = page.evaluate("""() => {
      const read = (store) => new Promise((resolve, reject) => {
        const request = indexedDB.open("amz-listing-kit-v2");
        request.onsuccess = () => {
          const db = request.result;
          const tx = db.transaction(store, "readonly").objectStore(store).getAll();
          tx.onsuccess = () => { const rows = tx.result; db.close(); resolve(rows); };
          tx.onerror = () => reject(tx.error);
        };
        request.onerror = () => reject(request.error);
      });
      return (async () => {
        const documents = await read("documents");
        const attempts = documents.filter((row) => row.kind === "generation_attempt");
        const latestByAction = {};
        for (const row of attempts) latestByAction[row.payload.action_id] = row.payload;
        return Object.values(latestByAction).map((record) => ({
          action_id: record.action_id, prompt_version: record.prompt.version,
          prompt_hash: record.prompt.hash,
        }));
      })();
    }""")
    probes["suite_deliver"] = page.evaluate(DELIVER_SUITE_PROBE)
    return shots, probes


def download_delivery(page, path: Path) -> dict:
    with page.expect_download(timeout=120_000) as info:
        page.click("#deliver-export")
    download = info.value
    download.save_as(str(path))
    return {"filename": download.suggested_filename, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def inspect_zip(path: Path) -> dict:
    """独立核对（Python zipfile/hashlib，不依赖产品代码）。"""
    with zipfile.ZipFile(path) as archive:
        names = sorted(archive.namelist())
        broken = archive.testzip()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        checks = json.loads(archive.read("checks.json").decode("utf-8"))
        readme = archive.read("README.txt").decode("utf-8")
        images = [item for item in names if item.startswith("images/")]
        digests = {}
        for item in manifest.get("images", []):
            data = archive.read(item["file"])
            digests[item["file"]] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_size": len(data),
                "declared": item["asset_sha256"],
                "declared_size": item.get("byte_size"),
            }
    return {"names": names, "broken": broken, "manifest": manifest, "checks": checks,
            "readme": readme, "images": images, "digests": digests}
