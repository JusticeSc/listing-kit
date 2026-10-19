#!/usr/bin/env python
"""V2.2.3 证据：商品资料与异常驱动理解界面。

检查：
  1) `python app/server.py --check` 正式入口自检全过（含两个新的无状态 API 断言）。
  2) 真实正式入口 + fake-semantic provider + 真实 Chromium：空白起点、无预填商品。
  3) 上传参考图（真实 PNG 字节）：登记、去重、角色、资产记录与商品资料草稿同时落盘。
  4) 商品资料草稿：防抖写入后刷新页面原样恢复（document_id=intake，版本递增）。
  5) 分析：浏览器只发一次 POST，body 字段与 capabilities.analyze_fields 一致，existing_slot_ids 为空。
  6) 入库：核心槽位先物化为 missing，提案槽位只能变成 proposed（模型不能直接确认）。
  7) 异常优先：默认列表按 冲突 → 未知 → 缺失 → 未确认 排序，已确认事实默认折叠。
  8) 权限投影：系统固定槽位没有“删除”，自定义槽位有；派生权限不出现非法按钮。
  9) 重分析不静默覆盖：已确认值遇到不同提案变成 conflict，并保留两条以上证据。
 10) unknown 不自动重提：一次点击只产生一次 POST，等待期内不再发第二次。
 11) 状态派生：EMPTY → INTAKE_READY → UNDERSTANDING_REVIEW → PLAN_REVIEW，并如实说明当前边界。
 12) 390px 无横向溢出；关键控件在键盘 Tab 顺序内可达。
 13) 整个会话零 console error / page error；仓库与最近项目索引在会话前后零差异。

运行：
  uv run --locked python tools/verify_v2_2_3_intake_understanding.py
"""
from __future__ import annotations

import argparse
import hashlib
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
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
APP_NAME = "V2.2.3"
PY = sys.executable
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402  （B4 四段工作台导航）

SCAN_DIRS = ("app", "src", "config")
SKIP_PARTS = {"__pycache__", ".uv-cache", ".git"}

DB_SNAPSHOT = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) {
    return { projects: [], documents: [], slots: [], assets: [] };
  }
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
  const projects = await read("projects");
  const documents = await read("documents");
  const assets = await read("assets");
  db.close();
  const latest = new Map();
  for (const record of documents) {
    const key = record.kind + "/" + record.document_id;
    const current = latest.get(key);
    if (!current || record.version > current.version) latest.set(key, record);
  }
  const slots = [...latest.values()].filter((item) => item.kind === "fact_slot").map((item) => ({
    slot_id: item.document_id, version: item.version, status: item.payload.status,
    value: item.payload.value, critical: item.payload.critical === true,
    authority: item.payload.authority, evidence: (item.payload.evidence || []).length,
    depends_on: item.payload.depends_on || [],
  }));
  return {
    projects: projects.map((item) => ({
      project_id: item.project_id, name: item.name, state: item.state, revision: item.revision,
    })),
    documents: [...latest.values()].map((item) => ({
      kind: item.kind, document_id: item.document_id, version: item.version,
    })),
    slots,
    assets: assets.map((item) => ({ sha256: item.sha256, byte_size: item.byte_size })),
  };
}
"""

INTAKE_SNAPSHOT = """
async (projectId) => {
  const opened = await (await import("/storage/index.js")).openStorage({});
  try {
    const doc = await opened.repository.documents.getLatest(projectId, "product_input", "intake");
    return doc ? { version: doc.version, payload: doc.payload } : null;
  } finally {
    opened.close();
  }
}
"""

# 文案提议只落 semantic_analysis 记录（disposition=stored），不写事实/规格；
# 这里读出每条记录的终态与回显的候选，验证「提议不动事实」这条边界。
COPY_RECORDS_SNAPSHOT = """
async () => {
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
  return docs.filter((row) => row.kind === "semantic_analysis")
    .map((row) => {
      const proposal = row.payload && row.payload.proposal ? row.payload.proposal : {};
      return {
        document_id: row.document_id, version: row.version,
        state: row.payload.state, disposition: row.payload.disposition,
        sent_reference_images: row.payload.reference_images_sent === true,
        copies: (proposal.copy_proposals || []).map((item) => ({
          text: item.text, source_slot_id: item.source_slot_id,
          source_slot_version: item.source_slot_version,
        })),
        slots: (proposal.slots || []).length,
      };
    });
}
"""


SLOT_TECH_PROBE = """() => [...document.querySelectorAll('#slot-list .slot-row')].map((row) => {
  const clone = row.cloneNode(true);
  clone.querySelectorAll('details').forEach((node) => node.remove());
  const tech = [...row.querySelectorAll('.tech-details')].map((node) => ({
    open: node.open === true,
    summary: (node.querySelector('summary') || {}).textContent || '',
    body: (node.querySelector('.tech-body') || {}).textContent || '',
  }));
  return { slot_id: row.getAttribute('data-slot-id'), status: row.getAttribute('data-status'),
           main_text: (clone.textContent || '').replace(/\\s+/g, ' ').trim(), tech: tech };
})"""

SLOT_PANEL_MAIN_TEXT = """() => {
  const panel = document.querySelector('[data-stage-panel="intake"]');
  if (!panel) return '';
  const clone = panel.cloneNode(true);
  clone.querySelectorAll('details').forEach((node) => node.remove());
  return (clone.textContent || '').replace(/\\s+/g, ' ');
}"""


def png_bytes(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """不用第三方库生成一张真实 PNG（RGB，无压缩过滤）。"""

    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint() -> dict:
    """受管文件 + 根条目 + 最近项目索引；只读。"""
    files: dict[str, dict] = {}
    for top in SCAN_DIRS:
        base = ROOT / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or SKIP_PARTS & set(path.parts) or path.suffix == ".pyc":
                continue
            stat = path.stat()
            files[path.relative_to(ROOT).as_posix()] = {
                "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            }
    index_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "AMZ Listing Kit"
    index: dict = {"exists": index_dir.is_dir(), "files": {}}
    if index_dir.is_dir():
        for path in sorted(index_dir.rglob("*")):
            if path.is_file():
                index["files"][path.relative_to(index_dir).as_posix()] = path.stat().st_size
    return {"files": files, "recent_index": index}


def diff_fingerprints(before: dict, after: dict) -> dict:
    added = sorted(set(after["files"]) - set(before["files"]))
    removed = sorted(set(before["files"]) - set(after["files"]))
    changed = sorted(name for name in set(before["files"]) & set(after["files"])
                     if before["files"][name] != after["files"][name])
    index_changed = before["recent_index"] != after["recent_index"]
    return {"added": added, "removed": removed, "changed": changed,
            "recent_index_changed": index_changed,
            "clean": not (added or removed or changed or index_changed)}




def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run_entry(args: list[str], timeout: int = 180) -> dict:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [PY, "-B", str(ROOT / "app" / "server.py"), *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )
    return {"args": args, "rc": completed.returncode,
            "tail": (completed.stdout + completed.stderr).strip().splitlines()[-8:]}
STATUS_ORDER = {"conflict": 0, "unknown": 1, "missing": 2, "proposed": 3, "confirmed": 4, "superseded": 5}


def wait_slot_version(page: Any, slot_id: str, previous: int,
                      attempts: int = 40) -> dict | None:
    """等到某个槽位在库里出现比 previous 更新的版本；超时返回最后一次读数。"""

    latest: dict | None = None
    for _ in range(attempts):
        snapshot = page.evaluate(DB_SNAPSHOT)
        latest = next((item for item in snapshot["slots"] if item["slot_id"] == slot_id), None)
        if latest and latest["version"] > previous:
            return latest
        page.wait_for_timeout(150)
    return latest


def review_rank(row: dict) -> int:
    """与 workspace.js `reviewRankOf` 同一条规则：必须确认（且未收尾）排在缺失之前。

    计划 §5 / V2.2.3 验收要求默认列表突出「冲突、未知、低置信和必确认项」，
    页面文案也承诺「先处理冲突、未知与必须确认的槽位」；只按 STATUS_ORDER 排会把
    不阻塞门禁的 missing 顶到必确认项前面。
    """
    status = row["status"]
    if status not in ("confirmed", "superseded") and row["critical"] == "1":
        return 2
    base = STATUS_ORDER[status]
    return base if base < 2 else base + 1


def eval_rows(page) -> list[dict]:
    return page.eval_on_selector_all(
        "#slot-list .slot-row",
        """nodes => nodes.map((node) => ({
             slot_id: node.dataset.slotId,
             status: node.dataset.status,
             critical: node.dataset.critical || "0",
             actions: [...node.querySelectorAll('.slot-actions button')]
               .map((button) => button.textContent.trim()),
           }))""",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.2.3 商品资料与异常驱动理解界面验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    analyze_posts: list[str] = []
    screenshots: list[str] = []

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})

    entry = run_entry(["--check"])
    check(f"{APP_NAME}-01", "正式入口自检全过（含 capabilities / analyze 与拒绝 V1 API、目录逃逸）",
          entry["rc"] == 0 and any("通过。" in line for line in entry["tail"]), entry)

    from app.product_v2_server import create_product_v2_server  # noqa: PLC0415
    from src.providers.v2_fake_semantic import FakeSemanticProvider
    from src.providers.v2_semantic import CORE_SLOT_REGISTRY

    scenario = {"value": "ok"}

    def provider_factory():
        return FakeSemanticProvider(scenario=scenario["value"])

    server = create_product_v2_server(
        "127.0.0.1", 0, provider_factory=provider_factory)
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    before_fp = fingerprint()
    try:
        with urllib.request.urlopen(base + "/api/v2/capabilities", timeout=10) as response:
            capabilities = json.loads(response.read().decode("utf-8"))
        check(f"{APP_NAME}-02", "capabilities 返回 provider 身份、analyze 字段与契约版本",
              capabilities.get("ok") is True
              and isinstance(capabilities.get("analyze_fields"), list)
              and capabilities.get("provider", {}).get("configured") is True
              and bool(capabilities.get("semantic_contract")), capabilities)

        temp_root = Path(tempfile.mkdtemp(prefix="amz-v223-"))
        profile = temp_root / "profile"
        ref_one = temp_root / "ref-one.png"
        ref_one.write_bytes(png_bytes(12, 12, (30, 90, 160)))
        ref_two = temp_root / "ref-two.png"
        ref_two.write_bytes(png_bytes(10, 10, (200, 120, 40)))

        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else context.new_page()
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("request", lambda request: analyze_posts.append(request.post_data or "")
                    if request.method == "POST" and "/api/v2/semantic/analyze" in request.url else None)

            page.goto(base + "/", wait_until="networkidle")
            expect(page.locator("#empty-state")).to_be_visible()
            blank = page.evaluate(DB_SNAPSHOT)
            check(f"{APP_NAME}-03", "空白起点：没有项目、没有预填商品或历史候选",
                  blank["projects"] == [] and blank["assets"] == [], blank)

            page.fill("#new-project-name", "审计商品 · 便携榨汁杯")
            page.click("#create-project")
            # R3.3：新建即打开，不再回列表行点 open。
            expect(page.locator("#project-view")).to_be_visible()
            expect(page.locator("#ref-empty")).to_be_visible()
            expect(page.locator("#intake-name")).to_have_value("")
            expect(page.locator("#slot-list .slot-row")).to_have_count(0)
            expect(page.locator("#analyze-run")).to_be_disabled()
            gate_text = page.locator("#analyze-gate").inner_text()
            opened = page.evaluate(DB_SNAPSHOT)
            project_id = opened["projects"][0]["project_id"]
            check(f"{APP_NAME}-04", "工作区空白形态：无参考图、资料为空、分析不可用并说明缺什么（EMPTY）",
                  opened["projects"][0]["state"] == "EMPTY" and "还缺" in gate_text
                  and opened["documents"] == [], {"gate": gate_text, "state": opened["projects"][0]["state"]})

            page.set_input_files("#ref-file", str(ref_one))
            expect(page.locator("#ref-list .ref-row")).to_have_count(1)
            page.set_input_files("#ref-file", str(ref_one))
            expect(page.locator("#ref-error")).to_contain_text("相同")
            duplicate_notice = page.locator("#ref-error").inner_text()
            page.set_input_files("#ref-file", str(ref_two))
            expect(page.locator("#ref-list .ref-row")).to_have_count(2)
            roles = [item.input_value() for item in page.locator("#ref-list select").all()]
            upload_db = page.evaluate(DB_SNAPSHOT)
            intake_doc = page.evaluate(INTAKE_SNAPSHOT, project_id)
            check(f"{APP_NAME}-05", "上传参考图：首张自动成为商品主图、同内容被跳过、资产与商品资料一起落盘",
                  roles == ["primary", "other"] and len(upload_db["assets"]) == 2
                  and "相同" in duplicate_notice and intake_doc is not None
                  and len(intake_doc["payload"]["references"]) == 2
                  and intake_doc["payload"]["references"][0]["role"] == "primary",
                  {"roles": roles, "assets": len(upload_db["assets"]),
                   "duplicate": duplicate_notice, "intake_version": intake_doc["version"] if intake_doc else None})

            page.fill("#intake-name", "便携榨汁杯")
            page.fill("#intake-description", "350ml 便携榨汁杯，USB-C 充电，可整杯冲洗。")
            page.fill("#intake-selling-points", "一键启动\n杯身可拆洗\n6 片不锈钢刀头")
            page.fill("#intake-focus", "突出便携与易清洗")
            page.wait_for_timeout(1200)
            saved_doc = page.evaluate(INTAKE_SNAPSHOT, project_id)
            page.reload(wait_until="networkidle")
            expect(page.locator("#project-view")).to_be_visible()
            expect(page.locator("#intake-name")).to_have_value("便携榨汁杯")
            expect(page.locator("#intake-selling-points")).to_have_value("一键启动\n杯身可拆洗\n6 片不锈钢刀头")
            expect(page.locator("#ref-list .ref-row")).to_have_count(2)
            expect(page.locator("#project-state")).to_have_text("资料已保存")
            expect(page.locator("#analyze-run")).to_be_enabled()
            check(f"{APP_NAME}-06", "商品资料防抖写入（版本递增）并在刷新后原样恢复；状态推进到 INTAKE_READY",
                  saved_doc is not None and saved_doc["version"] >= 2
                  and saved_doc["payload"]["selling_points"] == ["一键启动", "杯身可拆洗", "6 片不锈钢刀头"],
                  {"version": saved_doc["version"] if saved_doc else None,
                   "state": page.evaluate(DB_SNAPSHOT)["projects"][0]["state"]})

            posts_before = len(analyze_posts)
            page.click("#analyze-run")
            expect(page.locator("#slots-progress")).to_contain_text("必须确认的槽位")
            page.wait_for_timeout(500)
            # 四段工作台资料与事实同面板：分析完成后槽位行直接在资料与事实面板内就绪。
            stage_nav.goto(page, "intake")
            page.wait_for_selector("#slot-list .slot-row", timeout=30_000)
            analyzed = page.evaluate(DB_SNAPSHOT)
            body = json.loads(analyze_posts[-1]) if analyze_posts else {}
            # copy_targets 是「候选文案提议」专属字段（domain 侧事实理解会拒绝混装）：
            # 能力清单里它在，但事实理解请求不得携带；其余声明字段一个都不能少。
            declared = sorted(capabilities.get("analyze_fields") or [])
            expected_fields = sorted(item for item in declared if item != "copy_targets")
            check(f"{APP_NAME}-07", "分析：一次点击只发一次 POST，请求字段等于 capabilities.analyze_fields（不含文案提议专属 copy_targets），existing_slot_ids 为空",
                  len(analyze_posts) == posts_before + 1
                  and sorted(body) == expected_fields
                  and "copy_targets" not in body
                  and body.get("existing_slot_ids") == [],
                  {"posts": len(analyze_posts), "keys": sorted(body),
                   "expected": expected_fields, "declared": declared})

            slot_map = {item["slot_id"]: item for item in analyzed["slots"]}
            proposed = [item for item in analyzed["slots"] if item["status"] == "proposed"]
            check(f"{APP_NAME}-08", "入库：核心槽位先物化为 missing，模型提案只以 proposed 落库",
                  set(CORE_SLOT_REGISTRY) <= set(slot_map)
                  and len(proposed) >= 3
                  and all(item["status"] == "proposed" for item in proposed)
                  and all(item["status"] in ("missing", "proposed", "confirmed") for item in analyzed["slots"]),
                  {"core": len(CORE_SLOT_REGISTRY), "slots": len(analyzed["slots"]), "proposed": len(proposed)})

            rows_09 = eval_rows(page)
            statuses = [item["status"] for item in rows_09]
            ranks = [review_rank(item) for item in rows_09]
            critical_idx = [i for i, item in enumerate(rows_09) if item["critical"] == "1"]
            # 计划要求「必确认项」被突出；missing/proposed 里不阻塞门禁的普通项不得插到它们前面。
            blocking_idx = [i for i, item in enumerate(rows_09)
                            if item["critical"] != "1" and item["status"] in ("missing", "proposed")]
            critical_first = (not critical_idx or not blocking_idx
                              or max(critical_idx) < min(blocking_idx))
            check(f"{APP_NAME}-09",
                  "异常优先：默认列表按 冲突 → 未知 → 必须确认 → 缺失 → 未确认 排序，"
                  "必须确认项压在不阻塞门禁的缺失项之前，已确认事实默认折叠",
                  ranks == sorted(ranks) and critical_first
                  and "confirmed" not in statuses and "missing" in statuses,
                  {"statuses": statuses, "ranks": ranks, "critical_idx": critical_idx,
                   "blocking_idx": blocking_idx})

            # V2.6.16：事实卡片只把人话放主行；slot_id / 版本 / 证据来源（字段名、哈希、模型 id）
            # 一律收进该卡折叠的「技术详情」。判据用「删掉 details 后的可见文本」自证，不看样式。
            tech_rows = page.evaluate(SLOT_TECH_PROBE)
            panel_main = page.evaluate(SLOT_PANEL_MAIN_TEXT)
            hex_re = re.compile(r"\b[0-9a-f]{12,}\b")
            tech_ok = bool(tech_rows)
            tech_detail = {"rows": tech_rows[:4], "count": len(tech_rows)}
            for item in tech_rows:
                main_text = item["main_text"]
                if not item["tech"] or any(node["open"] for node in item["tech"]):
                    tech_ok = False
                if item["slot_id"] not in " ".join(node["body"] for node in item["tech"]):
                    tech_ok = False
                if item["slot_id"] in main_text or "版本 v" in main_text or "sha256" in main_text.lower():
                    tech_ok = False
                if hex_re.search(main_text):
                    tech_ok = False
            if "product_input" in panel_main or "fake-deepseek" in panel_main:
                tech_ok = False
            check(f"{APP_NAME}-22",
                  "事实卡片渐进披露：主行无 slot_id/版本/来源引用（字段名、哈希、模型 id），工程标识在技术详情里",
                  tech_ok, tech_detail)

            rows_default = {item["slot_id"]: item for item in eval_rows(page)}
            core_actions = rows_default.get("product_name", {}).get("actions", [])
            dynamic_actions = rows_default.get("usage_scene", {}).get("actions", [])
            check(f"{APP_NAME}-10", "权限投影：系统固定槽位没有删除按钮，品类动态槽位有删除按钮",
                  not any("删除" in item for item in core_actions)
                  and any("删除" in item for item in dynamic_actions)
                  and any("修改" in item for item in core_actions)
                  and "确认" in " ".join(core_actions),
                  {"core": core_actions, "dynamic": dynamic_actions})

            page.locator('#slot-list .slot-row[data-slot-id="product_name"]').get_by_role(
                "button", name="确认", exact=True).click()
            expect(page.locator('#slot-list .slot-row[data-slot-id="product_name"]')).to_have_count(0)
            page.click("#slots-toggle")
            confirmed_row = page.locator('#slot-list .slot-row[data-slot-id="product_name"]')
            expect(confirmed_row).to_have_count(1)
            check(f"{APP_NAME}-11", "确认后的槽位离开待处理列表，展开后可见且状态为已确认",
                  confirmed_row.get_attribute("data-status") == "confirmed", None)

            # 文案提议（AI 提议 + 人工确认）：明确点击才外发；一次点击一次 POST；
            # copy_targets 必须是「用户当初确认过的那一版」快照（槽位身份 + 版本 + 逐字值）。
            confirmed_before = page.evaluate(DB_SNAPSHOT)
            name_slot = next(item for item in confirmed_before["slots"]
                             if item["slot_id"] == "product_name")
            copy_posts_before = len(analyze_posts)
            page.click("#slot-copy-product_name")
            expect(page.locator("#slot-copy-result-product_name-0")).to_be_visible(timeout=20_000)
            copy_posts = len(analyze_posts)
            copy_body = json.loads(analyze_posts[-1]) if analyze_posts else {}
            copy_targets = copy_body.get("copy_targets") if isinstance(copy_body, dict) else None
            check(f"{APP_NAME}-23",
                  "文案提议：一次点击只发一次 POST，字段等于 capabilities.analyze_fields（含专属 copy_targets），"
                  "快照=当前已确认那一版的槽位身份/版本/逐字值，且不带参考图",
                  copy_posts == copy_posts_before + 1
                  and sorted(copy_body) == sorted(capabilities.get("analyze_fields") or [])
                  and isinstance(copy_targets, list) and len(copy_targets) == 1
                  and set(copy_targets[0]) == {"slot_id", "version", "label", "value_type", "value"}
                  and copy_targets[0]["slot_id"] == "product_name"
                  and copy_targets[0]["version"] == name_slot["version"]
                  and copy_targets[0]["value"] == name_slot["value"]
                  and copy_targets[0]["value_type"] == "text"
                  and isinstance(copy_targets[0]["label"], str) and bool(copy_targets[0]["label"])
                  and copy_body.get("existing_slot_ids") == []
                  and copy_body.get("references") == [],
                  {"posts": copy_posts - copy_posts_before, "keys": sorted(copy_body),
                   "copy_targets": copy_targets, "confirmed": name_slot})

            copy_row_text = (page.locator("#slot-copy-result-product_name-0").text_content()
                             or "").strip()
            copy_records = page.evaluate(COPY_RECORDS_SNAPSHOT)
            copy_record = next((item for item in copy_records if item["copies"]), {})
            copy_after = page.evaluate(DB_SNAPSHOT)
            check(f"{APP_NAME}-24",
                  "提议只是提议：候选行只回显不落事实（槽位与版本不变），分析记录 disposition=stored、"
                  "不发参考图也不应用槽位，来源版本未变时可采用",
                  "FAKE PRODUCT NAME" in copy_row_text
                  and copy_after["slots"] == confirmed_before["slots"]
                  and copy_record.get("state") == "succeeded"
                  and copy_record.get("disposition") == "stored"
                  and copy_record.get("sent_reference_images") is False
                  and copy_record.get("slots") == 0
                  and copy_record.get("copies") == [{"text": "FAKE PRODUCT NAME",
                                                     "source_slot_id": "product_name",
                                                     "source_slot_version": name_slot["version"]}]
                  and page.locator("#slot-copy-adopt-product_name-0").is_enabled(),
                  {"row": copy_row_text[:160], "record": copy_record,
                   "slots_unchanged": copy_after["slots"] == confirmed_before["slots"]})

            # 来源前进后旧提议必须过期：不可采用；重新提议按新版本快照发送，旧行仍标注过期。
            name_row = page.locator('#slot-list .slot-row[data-slot-id="product_name"]')
            name_row.get_by_role("button", name="修改", exact=True).click()
            page.fill("#slot-editor-value", "便携榨汁杯 二代")
            name_row.get_by_role("button", name="保存", exact=True).click()
            advanced = wait_slot_version(page, "product_name", name_slot["version"]) or {}
            stale_shown = page.locator("#slot-copy-stale-product_name-0").is_visible()
            stale_adopt_disabled = page.locator("#slot-copy-adopt-product_name-0").is_disabled()
            copy_posts_before = len(analyze_posts)
            page.click("#slot-copy-product_name")
            expect(page.locator("#slot-copy-result-product_name-1")).to_be_visible(timeout=20_000)
            refresh_body = json.loads(analyze_posts[-1]) if analyze_posts else {}
            refresh_targets = (refresh_body.get("copy_targets")
                               if isinstance(refresh_body, dict) else None) or []
            check(f"{APP_NAME}-25",
                  "来源前进后：旧提议标为过期且不可采用，重新提议只按新版本/新值快照发送一次，旧行保留过期标记",
                  advanced.get("version") == name_slot["version"] + 1
                  and advanced.get("value") == "便携榨汁杯 二代"
                  and advanced.get("status") == "confirmed"
                  and stale_shown and stale_adopt_disabled
                  and len(analyze_posts) == copy_posts_before + 1
                  and len(refresh_targets) == 1
                  and refresh_targets[0]["version"] == advanced.get("version")
                  and refresh_targets[0]["value"] == "便携榨汁杯 二代"
                  and page.locator("#slot-copy-adopt-product_name-1").is_enabled()
                  and page.locator("#slot-copy-stale-product_name-0").is_visible(),
                  {"advanced": advanced, "stale_shown": stale_shown,
                   "stale_adopt_disabled": stale_adopt_disabled,
                   "posts": len(analyze_posts) - copy_posts_before,
                   "refresh_targets": refresh_targets})

            # 复原这次实验改动的值：后续重分析会按原资料再提一次 product_name，
            # 值若与已确认值不同，按域规则会正确地变成 conflict（那是产品行为，不是本套件要测的路径）。
            name_row.get_by_role("button", name="修改", exact=True).click()
            page.fill("#slot-editor-value", str(name_slot["value"]))
            name_row.get_by_role("button", name="保存", exact=True).click()
            restored = wait_slot_version(page, "product_name", int(advanced.get("version") or 0)) or {}
            check(f"{APP_NAME}-26", "实验后复原：改回原确认值仍是同一份已确认事实（版本继续前进，不改变后续判定）",
                  restored.get("value") == name_slot["value"]
                  and restored.get("status") == "confirmed",
                  {"restored": restored, "original": name_slot})

            page.locator('#slot-list .slot-row[data-slot-id="product_category"]').get_by_role(
                "button", name="确认", exact=True).click()
            page.wait_for_timeout(300)
            pre_conflict = page.evaluate(DB_SNAPSHOT)
            category_before = next(item for item in pre_conflict["slots"]
                                   if item["slot_id"] == "product_category")
            page.click("#slots-toggle")
            scenario["value"] = "conflict"
            stage_nav.goto(page, "intake")
            page.click("#analyze-run")
            page.wait_for_timeout(900)
            conflicted = page.evaluate(DB_SNAPSHOT)
            category = next(item for item in conflicted["slots"] if item["slot_id"] == "product_category")
            check(f"{APP_NAME}-12", "重分析不静默覆盖：已确认值遇到不同提案变成 conflict，保留两条以上证据且不丢旧值",
                  category_before["status"] == "confirmed"
                  and category["status"] == "conflict" and category["value"] is None
                  and category["evidence"] >= 2,
                  {"before": category_before, "after": category})

            scenario["value"] = "timeout_after_send"
            unknown_before = len(analyze_posts)
            stage_nav.goto(page, "intake")
            page.click("#analyze-run")
            expect(page.locator("#analyze-error")).to_contain_text("结果未知")
            unknown_text = page.locator("#analyze-error").inner_text()
            page.wait_for_timeout(3000)
            check(f"{APP_NAME}-13", "Unknown 不自动重提：一次点击只产生一次 POST，等待期内没有第二次调用",
                  len(analyze_posts) == unknown_before + 1 and "不会自动重试" in unknown_text,
                  {"posts_before": unknown_before, "posts_after": len(analyze_posts),
                   "message": unknown_text[:200]})
            category_row = page.locator('#slot-list .slot-row[data-slot-id="product_category"]')
            stage_nav.goto(page, "intake")
            category_row.get_by_role("button", name="填值并确认", exact=True).click()
            category_row.locator('[data-role="value"]').fill("小家电 · 便携榨汁杯")
            category_row.get_by_role("button", name="确认", exact=True).click()
            page.wait_for_timeout(300)
            page.locator('#slot-list .slot-row[data-slot-id="signature_features"]').get_by_role(
                "button", name="确认", exact=True).click()
            page.wait_for_timeout(400)
            resolved = page.evaluate(DB_SNAPSHOT)
            state_now = resolved["projects"][0]["state"]
            # V2.UI.2 起项目元数据收进 <details>（渐进披露）；文本仍必须正确，只是默认不绘制。
            scope_text = page.locator("#project-scope").text_content() or ""
            state_badge = (page.locator("#project-state").text_content() or "").strip()
            check(f"{APP_NAME}-14", "状态派生到 PLAN_REVIEW，并如实说明套图可编辑、提交需确认",
                  state_now == "PLAN_REVIEW" and state_badge == "待确认套图"
                  and "套图规划" in scope_text and "通过确认后才能提交生成" in scope_text,
                  {"state": state_now, "badge": state_badge, "scope": scope_text,
                   "critical_confirmed": [item["slot_id"] for item in resolved["slots"]
                                          if item["critical"] and item["status"] == "confirmed"],
                   "critical_unresolved": [item for item in resolved["slots"]
                                           if item["critical"] and item["status"] != "confirmed"]})

            panel_png = EVIDENCE_DIR / f"v2.2.3-workspace-{stamp}.png"
            EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(panel_png), full_page=True)
            screenshots.append(panel_png.relative_to(ROOT).as_posix())

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(300)
            narrow_png = EVIDENCE_DIR / f"v2.2.3-narrow-{stamp}.png"
            page.screenshot(path=str(narrow_png), full_page=True)
            screenshots.append(narrow_png.relative_to(ROOT).as_posix())
            overflow = page.evaluate(
                "() => ({scroll: document.documentElement.scrollWidth,"
                " client: document.documentElement.clientWidth})")
            check(f"{APP_NAME}-15", "390px 视口无横向溢出", overflow["scroll"] <= overflow["client"] + 1, overflow)
            page.set_viewport_size({"width": 1280, "height": 900})

            stage_nav.goto(page, "intake")
            page.click("#slot-add summary")
            page.evaluate("() => { document.activeElement.blur(); }")
            seen: list[str] = []
            for _ in range(40):
                page.keyboard.press("Tab")
                seen.append(page.evaluate(
                    "() => { const node = document.activeElement;"
                    " return node ? (node.id || node.tagName) : null; }"))
            check(f"{APP_NAME}-16",
                  "键盘可达：资料与事实阶段的控件都在同一阶段的 Tab 顺序内（参考图/保存草稿/分析/槽位开关/新增槽位）",
                  {"slots-toggle", "slot-add-id", "ref-add", "intake-save", "analyze-run"} <= set(seen),
                  {"intake_stage": [item for item in seen if item][:80]})

            open_after = page.evaluate(DB_SNAPSHOT)
            # 唯一允许出现的是“故意触发的 Unknown 场景”那条 504：浏览器会把 5xx 记录到控制台。
            expected_console = [item for item in console_errors if "504" in item]
            unexpected_console = [item for item in console_errors if "504" not in item]
            check(f"{APP_NAME}-17", "除故意触发的 Unknown 504 外，浏览器会话零 console error / page error",
                  not unexpected_console and not page_errors and len(expected_console) == 1,
                  {"expected_504": expected_console, "unexpected": unexpected_console[:5],
                   "page": page_errors[:5], "slots": len(open_after["slots"])})
            context.close()
    finally:
        server.stop()

    after_fp = fingerprint()
    disk_diff = diff_fingerprints(before_fp, after_fp)
    check(f"{APP_NAME}-18", "磁盘审计：正式入口 + 浏览器会话前后仓库与最近项目索引零差异",
          disk_diff["clean"], disk_diff)

    # 19/20：这一版的运行时依赖（src/providers、config）必须真的进得了镜像与 CI 构建上下文，
    # 否则镜像会在 import 阶段崩溃而本机测试看不出来。
    build_inputs = ["Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock",
                    "app/server.py", "app/product_v2_server.py", "app/product_v2", "src", "config"]
    workflow_text = (ROOT / ".github" / "workflows" / "ci-cd.yml").read_text(encoding="utf-8")
    tar_command = re.search(r"tar -czf - .*?\n(?:.*?\n)*?.*?\| ssh", workflow_text)
    tar_declares = bool(tar_command) and all(
        token in tar_command.group(0)
        for token in ("pyproject.toml", "uv.lock", "src", "config"))
    listing: list[str] = []
    tar_error = ""
    try:
        with tempfile.TemporaryDirectory(prefix="amz-v223-context-") as tmp:
            archive = Path(tmp) / "context.tgz"
            subprocess.run(["tar", "-czf", str(archive), *build_inputs],
                           cwd=str(ROOT), check=True, capture_output=True)
            listing = subprocess.run(["tar", "-tzf", str(archive)], check=True,
                                     capture_output=True, text=True).stdout.splitlines()
    except Exception as error:  # noqa: BLE001 - tar 不可用也要如实记录
        tar_error = f"{type(error).__name__}: {error}"
    required = {"Dockerfile", "pyproject.toml", "uv.lock", "app/server.py",
                "app/product_v2_server.py", "app/product_v2/workspace.js",
                "src/providers/v2_registry.py", "src/providers/v2_semantic.py",
                "config/product-v2/providers.json"}
    leaked = [name for name in listing
              if name.startswith(("evals/", "_working/", "_stage-amz-control", ".git/"))]
    check(f"{APP_NAME}-19", "构建上下文（CI tar 列表）包含本版运行时依赖，且不含测试装置与工作记录",
          not tar_error and required <= set(listing) and tar_declares and not leaked,
          {"tar_error": tar_error, "entries": len(listing), "declares": tar_declares,
           "missing": sorted(required - set(listing)), "leaked": leaked[:5]})

    docker_text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    check(f"{APP_NAME}-20", "镜像按 uv.lock 安装运行时依赖并带上 src/config，入口与健康检查保持不变",
          "uv sync --locked --no-dev" in docker_text
          and "COPY src/ ./src/" in docker_text and "COPY config/ ./config/" in docker_text
          and 'CMD ["python", "app/server.py", "--host", "0.0.0.0", "--port", "8780"]' in docker_text
          and "/api/health" in docker_text,
          {"docker_lines": len(docker_text.splitlines())})

    # 21：上面的浏览器检查用的是注入 fake provider 的进程；这里再证明默认注册表（真实 provider）
    # 下正式进程也能启动，且 capabilities 不会因为缺密钥而把进程打崩。
    # 子进程端口无法 bind-0 读回；冲突时会健康检查失败，已记录为已知 flake 面
    entry_port = free_port()
    entry_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    entry_proc = subprocess.Popen(
        [PY, "-B", str(ROOT / "app" / "server.py"), "--port", str(entry_port)],
        cwd=str(ROOT), env=entry_env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    entry_health: dict | None = None
    entry_capabilities: dict | None = None
    entry_log = ""
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if entry_proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{entry_port}/api/health", timeout=2) as response:
                    entry_health = json.loads(response.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(0.3)
        if entry_health:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{entry_port}/api/v2/capabilities", timeout=5) as response:
                entry_capabilities = json.loads(response.read().decode("utf-8"))
    finally:
        entry_proc.terminate()
        try:
            entry_log = entry_proc.communicate(timeout=15)[0] or ""
        except subprocess.TimeoutExpired:
            entry_proc.kill()
            entry_log = entry_proc.communicate(timeout=10)[0] or ""
    check(f"{APP_NAME}-21", "默认 provider 下正式进程能起：health 与 capabilities 正常（缺密钥只表现为未配置）",
          entry_health is not None and entry_health.get("product") == "v2"
          and entry_capabilities is not None and entry_capabilities.get("ok") is True
          and "provider" in entry_capabilities,
          {"health": entry_health,
           "provider": (entry_capabilities or {}).get("provider"),
           "unavailable": (entry_capabilities or {}).get("unavailable"),
           "log_tail": entry_log.strip().splitlines()[-3:]})

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    boundary = (
        "证明在真实正式入口（app/server.py 的 V2 静态服务 + 两个无状态 API）与 fake-semantic provider 下，"
        "真实浏览器能从空白项目完成：上传参考图 → 填商品资料（草稿防抖落盘）→ 一次无状态分析 → "
        "槽位按领域契约入库 → 冲突/未知/缺失优先展示 → 人工确认推进到 PLAN_REVIEW；"
        "unknown 之后不自动重提，服务端与会话前后磁盘零差异。"
        "不证明：真实模型（deepseek-v4.1-flash / qwen-image）的理解与出图质量、套图规划与生成、"
        "审核与导出、跨机器迁移、以及未受训陌生试用者的可用性。"
    )
    report = {
        "task": APP_NAME,
        "suite": "v2.2.3-intake-understanding",
        "status": status,
        "finished_at": finished_at,
        "port": server.port,
        "checks": checks,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "analyze_posts": len(analyze_posts),
        "screenshots": screenshots,
        "disk_diff": disk_diff,
        "boundary": boundary,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.2.3-intake-understanding-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.2.3-intake-understanding-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.2.3 intake & exception-driven understanding (stateless server + fake provider)",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        f"port: {server.port}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False))
    lines += ["", "SCREENSHOTS"]
    lines += [f"- {item}" for item in screenshots]
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 72)
    print("V2.2.3 商品资料与异常驱动理解界面验证")
    print("=" * 72)
    for item in checks:
        print(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            print("       " + json.dumps(item["detail"], ensure_ascii=False)[:500])
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{'全过' if status == 'passed' else '有失败'}（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
