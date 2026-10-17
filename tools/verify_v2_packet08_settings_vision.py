#!/usr/bin/env python
"""packet08 设置三用途有效配置贯通 + 看图语义来源 + BYOK 出站与凭据 fail-closed：页面真跑验证器（test-only）。

覆盖验收（全部离线 headless Chrome + 本地 fake provider + 本地假 transport；无付费调用、无真实密钥）：
  P08-01 设置面板三用途有效配置可见可改；缺 key 时明确提示而不是假装可用；
         面板文案声明密钥仅标签页内存/请求级（非 secret）。
  P08-02 BYOK：把非秘密哨兵键入真实设置 DOM 的语义/图像/复核三用途密码框并“应用设置”，
         由正式产品消费者（semantic-analysis / generation / selection-adoption / review-delivery）
         发出真实请求；在独立网络层捕获三用途出站头（purpose=Provider-*，source=凭据 byok），
         证明哨兵只出现在输入框内存与本次出站头，且不出现于完整 DOM 投影/完整响应体/错误面/
         服务器错误输出/完整 IDB 快照（文档与资产载荷 + 每个资产的原字节）/
         两包解压成员/完整控制台日志（扫描 DOM 前显式剔除密码输入本身）。
         较大资产（>8MiB 跳过线且在产品单图 10MiB 内）按原字节读齐；同一扫描器对故意含哨兵的
         有效大图必须判红，对无泄漏的最大资产不得误报。
  P08-03 一致性可证：页面所示配置与 fake-vision 替身实际收到的 provider/model/图片字节身份逐字一致。
  P08-04 旧格式包经正式 UI 导入被拒绝（不迁移、不半写，IDB 计数不变）；生产 provider 前置
         （凭据来源 none）下带着真实图片字节的合法看图请求被拒为凭据缺失（PROVIDER_NOT_CONFIGURED，
         不是 VISION_BYTES_REQUIRED）且零上游；默认档关闭时合法请求同样零上游。
         假 provider 绕过凭据，故凭据 fail-closed 一律用生产适配器 + 假 transport 证明。
  P08-05 原任务凭据隔离连接：原任务冻结在 fake-qwen-image/byok 后，清 key 被阻；把“当前设置”
         切到另一个图像 provider（与原目标不同）仍按冻结目标判凭据未就绪而不外发；
         经正式 DOM 补原目标凭据后恢复核对，状态请求头带原 Provider + 本次密钥原文、
         target 与冻结身份逐字段一致，task/action 不变、零新 submit、当前动作选择不被改变。
  P08-06 取消/关闭不应用草稿：草稿哨兵不进任何出站头；查看/应用设置与取消/关闭零供应商外呼。

运行（仓库根 amz-listing-kit 下）：
  uv run --locked python tools/verify_v2_packet08_settings_vision.py
  uv run --locked python tools/verify_v2_packet08_settings_vision.py --label <tag>

产物：控制台 PASS/FAIL 行；证据片段写入 evals/product-v2/refactor/<label>.json
（哨兵明文永不落盘：证据只记精确匹配布尔值、计数与长度）。
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import http.client
import io
import json
import os
import sys
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
from console import enable_utf8  # noqa: E402

enable_utf8()

import v2_verify_shared as shared  # noqa: E402
import v2_stage_nav as stage_nav  # noqa: E402
from src.providers.v2_fake_vision_semantic import (  # noqa: E402
    FAKE_VISION_MODEL_ID,
    FAKE_VISION_PROVIDER_ID,
    FakeVisionSemanticProvider,
)

EVIDENCE_DIR = ROOT / "evals" / "product-v2" / "refactor"
PACKAGE_FORMAT = "amz-listing-kit-project"
PACKAGE_FORMAT_VERSION = 2

# 非秘密哨兵：只在一次运行的输入框内存与本次出站头里出现，绝不作为真实密钥，也绝不写入证据。
SENTINELS = {
    "semantic": "pk-p08-sem-4f2a9c1d7e30",
    "image": "pk-p08-img-9b3e6a1c05d8",
    "review": "pk-p08-rev-7c1f4d2a8e60",
}
PURPOSE_ORDER = ("semantic", "image", "review")
PURPOSE_KEY_HEADER = {
    "semantic": "x-amz-listing-key-semantic",
    "image": "x-amz-listing-key-image",
    "review": "x-amz-listing-key-review",
}
PURPOSE_PROVIDER_HEADER = {
    "semantic": "x-amz-listing-provider-semantic",
    "image": "x-amz-listing-provider-image",
    "review": "x-amz-listing-provider-review",
}
# 只用于「取消/关闭不应用草稿」的草稿哨兵：与已应用的哨兵不同，必须在任何出站头里缺席。
DRAFT_SENTINELS = {
    "image": "pk-p08-draft-image-2a7c4e",
    "semantic": "pk-p08-draft-sem-6b1d9f",
}

# 在页面自己的 fetch 上做行为透明的观测：记录请求头（密钥头只记长度）与 JSON 端点完整响应体。
# 不参与业务逻辑，只被测产品消费者（semantic-analysis / generation / selection-adoption /
# review-delivery）发出的真实请求与收到的真实响应。
FETCH_SPY = """
(() => {
  window.__p08Net = [];
  const orig = window.fetch.bind(window);
  const JSON_PATHS = ["/api/v2/capabilities", "/api/v2/semantic/analyze",
    "/api/v2/images/submit", "/api/v2/images/status",
    "/api/v2/review/candidate", "/api/v2/review/suite"];
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : ((input && input.url) || "");
    const path = url.split("?")[0];
    const headers = {};
    const raw = (init && init.headers) || (input && input.headers) || {};
    try {
      new Headers(raw).forEach((value, key) => {
        const name = String(key).toLowerCase();
        headers[name] = (name.indexOf("-key-") >= 0 || name === "authorization"
          || name === "cookie") ? "<len:" + String(value).length + ">" : String(value);
      });
    } catch (error) { /* 观测失败不改行为 */ }
    const response = await orig(input, init);
    let requestBody = null;
    try {
      if (init && typeof init.body === "string") requestBody = init.body;
    } catch (error) { /* 观测失败不改行为 */ }
    const record = { path: path, method: (init && init.method) || "GET",
      headers: headers, body: null, request_body: requestBody };
    window.__p08Net.push(record);
    if (JSON_PATHS.some((item) => path.endsWith(item))) {
      try { record.body = await response.clone().text(); } catch (error) { record.body = null; }
    }
    return response;
  };
})();
"""

IDB_COUNTS = """
async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const counts = {};
  for (const store of ["projects", "documents", "assets"]) {
    counts[store] = await new Promise((resolve, reject) => {
      const tx = db.transaction(store, "readonly").objectStore(store).count();
      tx.onsuccess = () => resolve(tx.result);
      tx.onerror = () => reject(tx.error);
    });
  }
  db.close();
  return counts;
}
"""

IDB_DUMP = """
async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const out = {};
  for (const store of ["projects", "documents", "assets"]) {
    out[store] = await new Promise((resolve, reject) => {
      const tx = db.transaction(store, "readonly").objectStore(store).getAll();
      tx.onsuccess = () => resolve(tx.result);
      tx.onerror = () => reject(tx.error);
    });
  }
  db.close();
  return JSON.stringify(out, (key, value) => {
    if (value && typeof value === "object" && typeof value.size === "number"
        && typeof value.arrayBuffer === "function") { return "<blob:" + value.size + ">"; }
    return value;
  });
}
"""

STORAGE_SNAPSHOT = """
async () => {
  const snapshot = {
    local_storage: {}, session_storage: {},
    documents: [], document_payloads: [], asset_payloads: [],
    response_bodies: [], console_texts: [], blob_bytes: [], blob_byte_sizes: [],
    asset_total: 0,
  };
  for (const [store, out] of [[localStorage, snapshot.local_storage],
      [sessionStorage, snapshot.session_storage]]) {
    for (let index = 0; index < store.length; index += 1) {
      const key = store.key(index);
      snapshot[out === snapshot.local_storage ? "local_storage" : "session_storage"][key]
        = store.getItem(key);
    }
  }
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const readAll = (store) => new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
  const documents = await readAll("documents");
  const assets = await readAll("assets");
  db.close();
  const blobText = async (blob) => {
    if (!(blob instanceof Blob)) throw new Error("资产不是 Blob，无法证明字节缺席");
    const buffer = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    const chunk = 8192;
    for (let index = 0; index < buffer.length; index += chunk) {
      binary += String.fromCharCode.apply(null, buffer.slice(index, index + chunk));
    }
    return binary;
  };
  snapshot.documents = documents.map((row) => ({
    kind: row.kind, document_id: row.document_id, version: row.version,
  }));
  snapshot.document_payloads = documents.map((row) => JSON.stringify(row.payload || {}));
  snapshot.asset_total = assets.length;
  for (const asset of assets) {
    // 每个资产都必须读出真实字节：不是 Blob 就报错，不用大小占位冒充内容。
    snapshot.blob_byte_sizes.push(
      asset.blob instanceof Blob ? asset.blob.size : -1);
    snapshot.blob_bytes.push(await blobText(asset.blob));
    snapshot.asset_payloads.push(JSON.stringify({
      sha256: asset.sha256, role: asset.role, byte_size: asset.byte_size,
    }));
  }
  snapshot.response_bodies = (window.__p08Net || []).map((item) => String(item.body || ""));
  return JSON.stringify(snapshot);
}
"""

# 扫描 DOM 前显式移除密码输入本身：密钥允许停在输入框内存里，不把那个位置当泄漏。
DOM_TEXT_SANS_PASSWORD = """
() => {
  const clone = document.documentElement.cloneNode(true);
  clone.querySelectorAll("input[type=password]").forEach((node) => node.remove());
  return clone.innerHTML;
}
"""

ALERT_TEXT = """
() => [...document.querySelectorAll('[role="alert"]')].map((node) => node.textContent || "")
"""

EFFECTIVE_ROWS = """
() => [...document.querySelectorAll("#model-settings-rows [data-effective-config]")]
  .map((node) => ({ purpose: node.getAttribute("data-effective-config"), text: node.textContent }))
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def check(checks: list, code: str, title: str, ok: bool, detail: object = None) -> None:
    checks.append({"code": code, "title": title, "ok": bool(ok), "detail": detail})
    message = redact_test_lines(f"[{'PASS' if ok else 'FAIL'}] {code} {title}"
                                + ("" if ok else f" :: {detail}"))
    print(message, flush=True)


def read_docs(page, kind: str) -> list:
    return page.evaluate("""(kind) => (async () => {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open("amz-listing-kit-v2");
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const rows = await new Promise((resolve, reject) => {
        const tx = db.transaction("documents", "readonly").objectStore("documents").getAll();
        tx.onsuccess = () => resolve(tx.result);
        tx.onerror = () => reject(tx.error);
      });
      db.close();
      return rows.filter((row) => row.kind === kind);
    })()""", arg=kind)


def last_request(requests_log: list, suffix: str) -> dict | None:
    for item in reversed(requests_log):
        if item["path"].endswith(suffix):
            return item
    return None


def find_net_body(net: list, suffix: str, predicate) -> object:
    for item in net:
        if not str(item.get("path", "")).endswith(suffix) or not item.get("body"):
            continue
        try:
            body = json.loads(item["body"])
        except (ValueError, TypeError):
            continue
        if predicate(body):
            return body
    return None

def find_net_request_body(net: list, suffix: str, predicate) -> object:
    for item in net:
        if not str(item.get("path", "")).endswith(suffix) or not item.get("request_body"):
            continue
        try:
            body = json.loads(item["request_body"])
        except (ValueError, TypeError):
            continue
        if predicate(body):
            return body
    return None


def text_of(page, element_id: str) -> str:
    return page.evaluate("(id) => (document.getElementById(id) || {}).textContent || ''",
                         arg=element_id)


def downgrade_to_format_one(source: Path, target: Path) -> None:
    """把一份真实导出的当前项目包重建成旧格式（format_version=1）工件。"""
    with zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        manifest["format_version"] = 1
        manifest.pop("integrity", None)
        manifest.pop("record_schema_version", None)
        entries = []
        for name in archive.namelist():
            if name == "manifest.json":
                continue
            data = archive.read(name)
            if name.startswith("documents/"):
                raw = json.loads(data.decode("utf-8"))
                data = json.dumps({"payload": raw.get("payload")},
                                  ensure_ascii=False).encode("utf-8")
            entries.append((name, data))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("manifest.json",
                        json.dumps(manifest, ensure_ascii=False).encode("utf-8"))
        for name, data in entries:
            output.writestr(name, data)


def check_image_byok_exact(checks: list, captures: dict) -> None:
    """生产图像适配器精确接收：内存原文逐字节相等，且同长度错用途哨兵必须不等。"""
    try:
        from src.providers.v2_registry import create_image_provider
        image_decision_exact = create_image_provider(byok_api_key=SENTINELS["image"])
        image_decision_swapped = create_image_provider(byok_api_key=SENTINELS["semantic"])
        captures["image_byok_exact"] = {
            "expected_len": len(SENTINELS["image"]),
            "received_len": len(getattr(image_decision_exact, "api_key", "") or ""),
            "received_exact": getattr(image_decision_exact, "api_key", None)
            == SENTINELS["image"],
            "swapped_exact": getattr(image_decision_swapped, "api_key", None)
            == SENTINELS["image"],
            "received_source": getattr(image_decision_exact, "credential_source", None),
        }
        check(checks, "P08-02i",
              "生产图像适配器精确收到本次图像哨兵原文，同长度语义哨兵不等",
              captures["image_byok_exact"]["received_exact"] is True
              and captures["image_byok_exact"]["swapped_exact"] is False
              and captures["image_byok_exact"]["received_source"] == "byok",
              captures["image_byok_exact"])
    except Exception as error:  # noqa: BLE001
        captures["image_byok_exact"] = {"error": f"{type(error).__name__}: {error}"[:200]}
        check(checks, "P08-02i", "生产图像适配器精确接收本次哨兵原文", False,
              captures["image_byok_exact"])



def redact_test_lines(text: str) -> str:
    """为控制台/日志转述脱敏：只替换本次测试哨兵原文，不改其它诊断内容。"""
    safe = str(text)
    for sentinel in SENTINELS.values():
        safe = safe.replace(sentinel, "<redacted-test-sentinel>")
    return safe


def sentinel_hits(surfaces: dict[str, str]) -> dict[str, list[str]]:
    """扫描实际表面内容；返回用途而非哨兵原文。"""
    return {name: found for name, text in surfaces.items()
            if (found := [purpose for purpose, sentinel in SENTINELS.items()
                          if sentinel in text])}


def supplier_calls(vision, image_provider, review_provider, suite_provider) -> dict:
    """离线替身的调用计数：证明「查看/应用设置」「取消/关闭」零供应商外呼。"""
    return {"vision": len(vision.calls), "image": dict(image_provider.calls),
            "review": len(review_provider.calls), "suite": len(suite_provider.calls)}


def password_dialog_state(page) -> dict:
    """设置对话框状态：是否打开 + 是否还留着未应用的草稿（密码框值）。"""
    return page.evaluate("""() => {
      const dialog = document.getElementById("model-settings-dialog");
      const inputs = [...dialog.querySelectorAll("input[type=password]")];
      return { open: dialog.open, values: inputs.filter((node) => node.value !== "").length };
    }""")


def attempt_of(page, shot_id: str, project_id: str = "") -> dict:
    """该项目该 Shot 最新 Attempt 文档的 payload：冻结身份/动作/task 的只读入口。"""
    rows = [row for row in read_docs(page, "generation_attempt")
            if row.get("document_id") == shot_id
            and (not project_id or row.get("project_id") == project_id)]
    if not rows:
        return {}
    return max(rows, key=lambda row: row.get("version") or 0).get("payload") or {}


def project_id_of(page, name: str) -> str:
    """按项目名读项目 ID（只读存储）：同 Shot ID 在不同项目里合法重复，取 Attempt 必须按项目取。"""
    return page.evaluate("""(name) => (async () => {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open("amz-listing-kit-v2");
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const rows = await new Promise((resolve, reject) => {
        const tx = db.transaction("projects", "readonly").objectStore("projects").getAll();
        tx.onsuccess = () => resolve(tx.result);
        tx.onerror = () => reject(tx.error);
      });
      db.close();
      const hit = rows.find((row) => row.name === name);
      return hit ? String(hit.project_id || "") : "";
    })()""", arg=name)


def read_current_image_provider(page) -> str:
    """重新打开设置面板读「现有模型」的当前选择（纯查看，不外呼）。"""
    page.click("#model-settings-open")
    page.wait_for_selector("#model-settings-dialog[open]", timeout=10_000)
    value = page.evaluate(
        "() => (document.getElementById('model-provider-image') || {}).value || ''")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    return value


def blob_byte_facts(snapshot: dict) -> dict:
    """资产字节取证：每个资产都读了真实字节，最大那份是原字节（PNG 头）而非大小占位。"""
    sizes = list(snapshot.get("blob_byte_sizes") or [])
    texts = list(snapshot.get("blob_bytes") or [])
    total = int(snapshot.get("asset_total") or 0)
    largest = max(sizes) if sizes else 0
    index = sizes.index(largest) if largest > 0 else -1
    head = texts[index][:8] if 0 <= index < len(texts) else ""
    return {"assets": total, "viewed": len(sizes),
            "reads_every_asset": bool(sizes) and len(sizes) == total and -1 not in sizes,
            "largest_bytes": largest,
            "largest_head_is_png": head == "\x89PNG\r\n\x1a\n"}


class StopTransport:
    """只记录调用再中止的假 transport：用于证明「凭据缺失路径根本不外呼」。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request(self, method, url, *, headers, json, timeout, allow_redirects):  # noqa: A002
        self.calls.append({"method": method, "url": url,
                           "authorization": str((headers or {}).get("Authorization", "")),
                           "header_names": sorted(str(name) for name in (headers or {}))})
        raise ConnectionError("p08 stop: 假 transport 不发起真实请求")


def run_production_credential_checks(checks: list, ref_bytes: bytes) -> dict:
    """Part B：不用浏览器，直接对生产适配器/注册表/网关证明凭据 fail-closed 与零上游。"""
    from src.providers.v2_credentials import resolve_credentials
    from src.providers.v2_dashscope_image import DashScopeImageProvider, create_default_image_provider
    from src.providers.v2_dashscope_vision_semantic import DashScopeVisionSemanticProvider
    from src.providers.v2_image import ImageFailure, SubmitRequest
    from src.providers.v2_semantic import SemanticFailure, SemanticRequest, decode_vision_images

    captures: dict = {}
    ref_sha = hashlib.sha256(ref_bytes).hexdigest()
    ref_b64 = base64.b64encode(ref_bytes).decode("ascii")
    entry = {"api_key_env": "DASHSCOPE_API_KEY"}

    # ---- P08-04d：解析器与构造前置（默认档关闭时环境里的部署密钥不得进入适配器）----
    try:
        closed = resolve_credentials(entry, {"DASHSCOPE_API_KEY": "sk-p08-deploy-dummy",
                                             "AMZ_V2_DEFAULT_TRIAL": "closed"})
        byok_decision = resolve_credentials(entry, {}, byok_api_key=SENTINELS["image"])
        image_transport = StopTransport()
        closed_image = create_default_image_provider(
            environ={"DASHSCOPE_API_KEY": "sk-p08-deploy-dummy",
                     "AMZ_V2_DEFAULT_TRIAL": "closed"}, transport=image_transport)
        submit = SubmitRequest.model_validate({
            "action_id": "p08-prec-closed-0001", "prompt": "白底商品图，商品居中。",
            "references": [{"role": "primary", "media_type": "image/png",
                            "sha256": ref_sha, "data_base64": ref_b64}],
        })
        denied_code = None
        try:
            closed_image.submit(submit)
        except ImageFailure as failure:
            denied_code = failure.code
        captures["resolver_closed"] = {"source": closed.source, "has_key": bool(closed.api_key)}
        captures["resolver_byok"] = {"source": byok_decision.source,
                                     "key_len": len(byok_decision.api_key or "")}
        captures["closed_image"] = {"credential_source": closed_image.credential_source,
                                    "configured": bool(closed_image.configured),
                                    "denied_code": denied_code,
                                    "upstream_calls": len(image_transport.calls)}
        check(checks, "P08-04d",
              "默认档关闭且环境存在部署密钥：解析 source=none、适配器不持密钥、合法提交被拒且零上游",
              closed.source == "none" and not closed.api_key
              and byok_decision.source == "byok"
              and byok_decision.api_key == SENTINELS["image"]
              and closed_image.credential_source == "none"
              and closed_image.configured is False
              and denied_code == "PROVIDER_NOT_CONFIGURED"
              and len(image_transport.calls) == 0,
              captures["resolver_closed"] | captures["resolver_byok"] | captures["closed_image"])
    except Exception as error:  # noqa: BLE001 - 环境问题如实报 FAIL
        captures["resolver_closed"] = {"error": f"{type(error).__name__}: {error}"[:200]}
        check(checks, "P08-04d", "默认档关闭前置解析与合法提交零上游", False,
              captures["resolver_closed"])
    check_image_byok_exact(checks, captures)


    # ---- P08-04c：看图 + 真实图片字节 + 无凭据 → 凭据拒绝（不是 VISION_BYTES_REQUIRED），零上游 ----
    try:
        llm_builds = {"n": 0}

        def _no_llm():
            llm_builds["n"] += 1
            raise AssertionError("凭据缺失路径不得装配 LLM")

        vision = DashScopeVisionSemanticProvider(api_key=None, credential_source="none",
                                                llm_factory=_no_llm)
        request = SemanticRequest.model_validate({
            "product_name": "P08 凭据前置保温杯", "description": "看图请求体合法。",
            "selling_points": ["真实字节"], "focus": "验证凭据 fail-closed",
            "references": [{"sha256": ref_sha, "media_type": "image/png", "role": "primary"}],
            "locale": "zh-CN", "platform": "amazon_us", "max_slots": 6, "existing_slot_ids": [],
        })
        images = decode_vision_images([{"role": "primary", "media_type": "image/png",
                                        "sha256": ref_sha, "data_base64": ref_b64}])
        vision_code = None
        try:
            vision.analyze(request, images)
        except SemanticFailure as failure:
            vision_code = failure.code
        captures["vision_denied"] = {"code": vision_code, "images": len(images),
                                     "llm_builds": llm_builds["n"]}
        check(checks, "P08-04c",
              "生产看图适配器收到真实图片字节但无凭据 → PROVIDER_NOT_CONFIGURED（不是 VISION_BYTES_REQUIRED）且零上游",
              vision_code == "PROVIDER_NOT_CONFIGURED" and vision_code != "VISION_BYTES_REQUIRED"
              and len(images) == 1 and llm_builds["n"] == 0,
              captures["vision_denied"])
    except Exception as error:  # noqa: BLE001
        captures["vision_denied"] = {"error": f"{type(error).__name__}: {error}"[:200]}
        check(checks, "P08-04c", "生产看图适配器凭据 fail-closed", False, captures["vision_denied"])

    # ---- P08-02g：图像适配器 BYOK 来源身份 + 出站鉴权只用本次密钥 + 不回显 ----
    try:
        byok_transport = StopTransport()
        byok_image = DashScopeImageProvider(api_key=SENTINELS["image"], credential_source="byok",
                                            transport=byok_transport)
        failure_text = ""
        try:
            byok_image.submit(SubmitRequest.model_validate({
                "action_id": "p08-byok-outbound-0001", "prompt": "白底商品图，商品居中。",
                "references": [{"role": "primary", "media_type": "image/png",
                                "sha256": ref_sha, "data_base64": ref_b64}],
            }))
        except Exception as error:  # noqa: BLE001 - 假 transport 记录后中止，这里只取证据
            failure_text = str(error)
        first = byok_transport.calls[0] if byok_transport.calls else {}
        authorization = first.get("authorization", "")
        # 语义（看图）档同源身份：apply_credentials 之后实例只持有本次密钥，来源标 byok。
        vision_byok = DashScopeVisionSemanticProvider(api_key=None, credential_source="none")
        vision_byok.apply_credentials(api_key=SENTINELS["semantic"])
        captures["image_byok"] = {
            "credential_source": byok_image.credential_source,
            "upstream_calls": len(byok_transport.calls),
            "authorization_len": len(authorization),
            "expected_len": len("Bearer ") + len(SENTINELS["image"]),
            "has_authorization": "Authorization" in (first.get("header_names") or []),
            "vision_credential_source": vision_byok.credential_source,
            "vision_key_len": len(vision_byok.api_key or ""),
            "vision_expected_len": len(SENTINELS["semantic"]),
        }
        check(checks, "P08-02g",
              "生产适配器 BYOK：图像出站鉴权只带本次密钥、语义档来源身份 byok 且错误面不回显密钥",
              byok_image.credential_source == "byok"
              and len(byok_transport.calls) >= 1
              and authorization == "Bearer " + SENTINELS["image"]
              and SENTINELS["image"] not in failure_text
              and vision_byok.credential_source == "byok"
              and vision_byok.api_key == SENTINELS["semantic"],
              captures["image_byok"])
    except Exception as error:  # noqa: BLE001
        captures["image_byok"] = {"error": f"{type(error).__name__}: {error}"[:200]}
        check(checks, "P08-02g", "生产适配器 BYOK 来源身份与出站鉴权", False, captures["image_byok"])

    # ---- P08-04e：生产网关（默认注册表装配 + 看图档 + 默认档关闭）合法看图体 → 503 凭据拒绝 ----
    saved_env = {key: os.environ.get(key) for key in
                 ("AMZ_V2_SEMANTIC_PROVIDER", "DASHSCOPE_API_KEY", "AMZ_V2_DEFAULT_TRIAL")}
    server = None
    try:
        os.environ["AMZ_V2_SEMANTIC_PROVIDER"] = "dashscope-vision"
        os.environ["DASHSCOPE_API_KEY"] = "sk-p08-deploy-dummy"
        os.environ["AMZ_V2_DEFAULT_TRIAL"] = "closed"
        from app import product_v2_server as module
        server = module.create_product_v2_server("127.0.0.1", 0)
        serve_in_background(server)
        host, port = "127.0.0.1", server_port(server)
        analyze_body = json.dumps({
            "product_name": "P08 生产前置", "description": "看图请求体合法、字节为真实 PNG。",
            "selling_points": ["真实字节"], "focus": "验证凭据 fail-closed",
            "references": [{"role": "primary", "media_type": "image/png", "sha256": ref_sha}],
            "reference_images": [{"role": "primary", "media_type": "image/png",
                                  "sha256": ref_sha, "data_base64": ref_b64}],
            "locale": "zh-CN", "platform": "amazon_us", "max_slots": 6, "existing_slot_ids": [],
        }, ensure_ascii=False).encode("utf-8")
        status, raw = http_post(host, port, "/api/v2/semantic/analyze", analyze_body,
                                {"X-AMZ-Listing-Provider-Semantic": "dashscope-vision"})
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        error = payload.get("error") or {}
        caps_status, caps_raw = http_get(host, port, "/api/v2/capabilities")
        caps = json.loads(caps_raw.decode("utf-8")) if caps_raw else {}
        provider_block = caps.get("provider") or {}
        captures["gateway_denied"] = {"status": status, "code": error.get("code"),
                                      "unknown": payload.get("unknown"),
                                      "configured": provider_block.get("configured"),
                                      "credential_source": provider_block.get("credential_source")}
        check(checks, "P08-04e",
              "生产网关合法看图请求（真实字节、无 BYOK）→ 503 PROVIDER_NOT_CONFIGURED，非校验短路",
              status == 503 and error.get("code") == "PROVIDER_NOT_CONFIGURED"
              and error.get("code") != "VISION_BYTES_REQUIRED"
              and payload.get("unknown") is False
              and caps_status == 200 and provider_block.get("configured") is False,
              captures["gateway_denied"])
    except Exception as error:  # noqa: BLE001
        captures["gateway_denied"] = {"error": f"{type(error).__name__}: {error}"[:200]}
        check(checks, "P08-04e", "生产网关看图凭据 fail-closed", False, captures["gateway_denied"])
    finally:
        if server is not None:
            try:
                stop_server(server)
            except Exception:  # noqa: BLE001
                pass
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return captures


def http_post(host: str, port: int, path: str, body: bytes,
              extra_headers: dict | None = None) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        headers.update(extra_headers or {})
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def http_get(host: str, port: int, path: str) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


# 外形稳定的服务器生命周期：P3 后产品网关是 ASGI 句柄（start/stop/.port），
# 不再是 ThreadingHTTPServer（serve_forever/shutdown/server_close/server_address）。
# 本工具只用这几个包装，宿主实现仍由产品拥有。
def serve_in_background(server):
    """后台启动服务器句柄：新句柄 start()，旧句柄 serve_forever。"""

    starter = getattr(server, "start", None)
    if callable(starter):
        starter()
        return
    serve_forever = getattr(server, "serve_forever", None)
    if not callable(serve_forever):
        raise RuntimeError("不支持的服务器句柄（无 start/serve_forever）。")
    threading.Thread(target=serve_forever, daemon=True).start()

def server_port(server) -> int:
    """读服务器真实监听端口：优先 .port，退回 .server_address。"""

    port = getattr(server, "port", None)
    if isinstance(port, int) and port > 0:
        return port
    address = getattr(server, "server_address", None)
    if address:
        return int(address[1])
    raise RuntimeError("不支持的服务器句柄（无 port/server_address）。")

def stop_server(server) -> None:
    """停止服务器句柄：新句柄 stop()，旧句柄 shutdown()/server_close()。"""

    stopper = getattr(server, "stop", None)
    if callable(stopper):
        stopper()
        return
    shutdown = getattr(server, "shutdown", None)
    if callable(shutdown):
        shutdown()
    closer = getattr(server, "server_close", None)
    if callable(closer):
        closer()

def main(*, server_logs: tuple[io.StringIO, io.StringIO]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    label = args.label or f"packet08-settings-semantic-{utc_now()}"
    temp_root = Path(tempfile.mkdtemp(prefix="amz-p08-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(shared.png_bytes(640, 640, (36, 92, 160)))
    ref_bytes = reference.read_bytes()
    ref_sha = hashlib.sha256(ref_bytes).hexdigest()
    # 有效 PNG、原字节超过旧扫描器的 8MiB 跳过线，但仍在产品单图 10MiB 内。
    from PIL import Image, PngImagePlugin
    large_reference = temp_root / "large-reference.png"
    large_image = Image.new("RGB", (1800, 1800), (36, 92, 160))
    large_image.save(large_reference, compress_level=0)
    large_bytes = large_reference.stat().st_size
    leak_reference = temp_root / "intentional-leak-probe.png"
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("p08-deliberate-negative", SENTINELS["image"])
    large_image.save(leak_reference, compress_level=0, pnginfo=metadata)
    checks: list = []
    captures: dict = {}
    # 夹具本身必须先成立：真实有效 PNG、超过旧跳过线、在产品单图上限内，负例确实含哨兵字节。
    check(checks, "P08-08a",
          "较大资产与负例夹具是真实有效 PNG、超过旧扫掠跳过线且在产品单图上限内",
          8 * 1024 * 1024 < large_bytes < 10 * 1024 * 1024
          and Image.open(large_reference).size == (1800, 1800)
          and leak_reference.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
          and SENTINELS["image"].encode("latin-1") in leak_reference.read_bytes(),
          {"large_bytes": large_bytes, "leak_bytes": leak_reference.stat().st_size,
           "skip_line": 8 * 1024 * 1024, "product_limit": 10 * 1024 * 1024})
    vision_calls: list = []
    requests_log: list = []
    console_all: list = []
    net: list = []
    project_zip = temp_root / "project.zip"
    v1_zip = temp_root / "project-format1.zip"
    screenshot = temp_root / "p08-vision.png"
    evidence: dict = {}

    from playwright.sync_api import sync_playwright, expect

    from src.providers.v2_fake_image import FakeImageProvider
    from src.providers.v2_fake_review import FakeReviewProvider
    from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider

    with sync_playwright() as pw:
        vision = FakeVisionSemanticProvider(scenario="ok")
        image_provider = FakeImageProvider("ok", size=1200)
        review_provider = FakeReviewProvider("ok")
        suite_provider = FakeSuiteReviewProvider("ok")
        server, _ = shared.start_product_server(
            0, semantic_factory=lambda: vision, image_factory=lambda: image_provider,
            review_factory=lambda: review_provider, suite_factory=lambda: suite_provider)
        port = server_port(server)
        try:
            context = pw.chromium.launch_persistent_context(
                str(temp_root / "profile"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = shared.collect(page)
            page.on("console", lambda message: console_all.append(message.text))

            def _on_request(request):
                try:
                    url = request.url
                    if "/api/v2/" not in url:
                        return
                    captured = {}
                    for name, value in request.headers.items():
                        lower = name.lower()
                        if not lower.startswith("x-amz-listing-") and lower != "content-type":
                            continue
                        captured[lower] = ("<len:%d>" % len(value or "")) if "-key-" in lower else value
                    key_matches = {
                        purpose: request.headers.get(header) == SENTINELS[purpose]
                        for purpose, header in PURPOSE_KEY_HEADER.items()
                    }
                    image_matches_semantic = (
                        request.headers.get(PURPOSE_KEY_HEADER["image"]) == SENTINELS["semantic"])
                    # 取消/关闭时的草稿哨兵若被应用，任何一次出站都会带着它：只记用途，不记原文。
                    draft_headers = sorted({
                        purpose for purpose, sentinel in DRAFT_SENTINELS.items()
                        for name, value in request.headers.items()
                        if "-key-" in name.lower() and value == sentinel})
                    requests_log.append({"path": url.split("?")[0], "method": request.method,
                                         "headers": captured, "key_matches": key_matches,
                                         "image_matches_semantic": image_matches_semantic,
                                         "draft_headers": draft_headers})
                except Exception:  # noqa: BLE001 - 观测失败不改行为
                    pass

            page.on("request", _on_request)
            page.add_init_script(FETCH_SPY)
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                spa_probe = page.evaluate("""() => fetch("/pages/定义-不存在-p08", { headers: { Accept: "text/html" } })
                  .then((response) => response.text().then((text) => ({
                    status: response.status, looks_like_app: text.indexOf("model-settings-open") >= 0,
                  }))).catch((error) => ({ status: -1, looks_like_app: false,
                    error: String(error && error.message || error) }))""")
                check(checks, "P08-08b",
                      "非 API 未知路由明确 404（不猜测业务、不回退应用入口）",
                      spa_probe.get("status") == 404 and spa_probe.get("looks_like_app") is False,
                      spa_probe)
                shared.create_project(page, "P08 设置贯通", reference)

                caps_probe = page.evaluate("""() => fetch("/api/v2/capabilities").then((r) => r.json()).then((j) => ({
                    provider_id: (j.provider || {}).provider_id,
                    model_id: (j.provider || {}).model_id,
                    configured: (j.provider || {}).configured,
                    credential_source: (j.provider || {}).credential_source,
                    vision: ((j.provider || {}).capabilities || {}).vision,
                    reference_images: ((j.provider || {}).capabilities || {}).reference_images,
                    choices: ((j.provider_choices || {}).semantic || []).map((c) => c.id),
                  }))""")
                check(checks, "P08-01a", "能力投影露出 fake-vision 看图档（注入接缝无头直调即保留实例）",
                      caps_probe.get("provider_id") == FAKE_VISION_PROVIDER_ID
                      and caps_probe.get("model_id") == FAKE_VISION_MODEL_ID
                      and caps_probe.get("vision") is True
                      and caps_probe.get("configured") is True,
                      caps_probe)
                captures["capabilities"] = caps_probe

                # ---------------- 设置 DOM：三用途有效配置 + 键入非秘密哨兵 ----------------
                page.click("#model-settings-open")
                page.wait_for_selector("#model-settings-dialog[open]", timeout=10_000)
                panel = page.evaluate(EFFECTIVE_ROWS)
                by_purpose = {row["purpose"]: row["text"] for row in panel}
                check(checks, "P08-01b", "设置面板三用途有效配置行可见（含缺 key 提示语）",
                      set(by_purpose) == {"semantic", "image", "review"}
                      and all("有效配置" in (t or "") or "缺少有效模型或凭据" in (t or "")
                              for t in by_purpose.values()),
                      by_purpose)
                check(checks, "P08-01c", "面板文案声明密钥仅标签页内存/请求级（非 secret）",
                      "标签页内存" in (page.evaluate(
                          "() => document.getElementById('model-settings-note').textContent") or ""),
                      None)

                typed: dict = {}
                for purpose in PURPOSE_ORDER:
                    selector = "#model-key-" + purpose
                    page.fill(selector, SENTINELS[purpose])
                    typed[purpose] = page.input_value(selector)
                check(checks, "P08-02in",
                      "非秘密哨兵确实键入设置 DOM 的三用途密码框（值只在输入框内存里，未落盘）",
                      all(typed.get(purpose) == SENTINELS[purpose] for purpose in PURPOSE_ORDER),
                      {purpose: len(typed.get(purpose) or "") for purpose in PURPOSE_ORDER})
                page.click("#model-settings-apply")
                page.wait_for_function(
                    "() => !document.getElementById('model-settings-dialog').open", timeout=10_000)
                # 应用后 refresh() 会用携带三用途密钥头的请求重读能力；等它落进页面自己的 fetch 观测里。
                page.wait_for_function(
                    "() => window.__p08Net.some((r) => r.path.endsWith('/api/v2/capabilities')"
                    " && r.body && r.body.indexOf('\"byok\"') >= 0)", timeout=60_000)

                page.click("#model-settings-open")
                page.wait_for_selector("#model-settings-dialog[open]", timeout=10_000)
                panel_after = page.evaluate(EFFECTIVE_ROWS)
                by_purpose_after = {row["purpose"]: row["text"] for row in panel_after}
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                net = page.evaluate("() => window.__p08Net")
                caps_body = find_net_body(
                    net, "/api/v2/capabilities",
                    lambda body: (body.get("provider") or {}).get("credential_source") == "byok") or {}
                source_by_projection = {
                    "panel": {purpose: ("凭据 byok" in (by_purpose_after.get(purpose) or ""))
                              for purpose in PURPOSE_ORDER},
                    "semantic": (caps_body.get("provider") or {}).get("credential_source"),
                    "image": ((caps_body.get("images") or {}).get("provider") or {}).get("credential_source"),
                    "review": ((caps_body.get("review") or {}).get("provider") or {}).get("credential_source"),
                }
                check(checks, "P08-02a",
                      "应用设置后正式消费者投影出三用途来源身份 byok（面板文案 + capabilities 响应同源）",
                      all(source_by_projection["panel"].values())
                      and source_by_projection["semantic"] == "byok"
                      and source_by_projection["image"] == "byok"
                      and source_by_projection["review"] == "byok",
                      source_by_projection)
                captures["byok_sources"] = source_by_projection

                # 应用设置会整体重渲染（含商品资料输入框）：还在防抖里的草稿必须先落盘再渲染，
                # 否则用户刚输入、尚未到落盘时点的文本会被按存储值重画掉——静默丢输入。
                # 这里同时核对“DOM 值没丢”与“确实落了盘”（名称是项目名，故用只属于资料的介绍文本）。
                persisted = ""
                for _ in range(20):
                    persisted = page.evaluate(IDB_DUMP)
                    if "316ml" in persisted:
                        break
                    page.wait_for_timeout(150)
                draft_now = page.evaluate("""() => {
                  const value = (id) => (document.getElementById(id) || {}).value || "";
                  return {name: value("intake-name"), description: value("intake-description"),
                          points: value("intake-selling-points"),
                          disabled: Boolean((document.getElementById("analyze-run") || {}).disabled)};
                }""")
                draft_gate = text_of(page, "analyze-gate")
                check(checks, "P08-01e",
                      "应用设置不丢未落盘的商品资料草稿：DOM 保留、已落盘、分析入口未锁",
                      draft_now["name"].strip() != "" and draft_now["description"].strip() != ""
                      and draft_now["points"].strip() != "" and draft_now["disabled"] is False
                      and "还缺" not in draft_gate and "316ml" in persisted,
                      {"gate": draft_gate, "draft": draft_now,
                       "description_persisted": "316ml" in persisted})

                # ---------------- 正式消费者跑真实请求链 ----------------
                gate_text = text_of(page, "analyze-gate")
                check(checks, "P08-01d", "注入看图档后理解区声明将发送实际图片（页面所示配置）",
                      "实际图片" in gate_text and FAKE_VISION_MODEL_ID in gate_text, gate_text)
                check(checks, "P08-04b", "页面分析按钮可用（注入替身已配置，不锁人工主链）",
                      not page.locator("#analyze-run").is_disabled(), {"gate": gate_text})
                gate_text_now = text_of(page, "analyze-gate")
                check(checks, "P08-03pre", "点击分析前页面仍声明将发送实际图片（与看图档一致）",
                      "实际图片" in gate_text_now and FAKE_VISION_MODEL_ID in gate_text_now, gate_text_now)

                stage_nav.goto(page, "intake")
                page.wait_for_selector('#stage-panels [data-stage-panel="intake"]:not([hidden])',
                                       timeout=20_000)
                page.click("#analyze-run")
                page.wait_for_timeout(400)
                stage_nav.goto(page, "understand")
                page.wait_for_selector("#slot-list .slot-row", timeout=60_000)
                page.wait_for_timeout(300)
                stage_nav.goto(page, "intake")
                page.wait_for_selector('#stage-panels [data-stage-panel="intake"]:not([hidden])',
                                       timeout=20_000)
                result_text = text_of(page, "analyze-result")
                gate_text = text_of(page, "analyze-gate")
                vision_calls = [dict(item) for item in vision.calls]
                check(checks, "P08-03a", "看图替身收到 exactly 1 张真实图片字节（非空 + sha 与上传原图一致）",
                      len(vision_calls) == 1
                      and vision_calls[0].get("vision_images") == 1
                      and (vision_calls[0].get("images") or [{}])[0].get("sha256") == ref_sha
                      and ((vision_calls[0].get("images") or [{}])[0].get("byte_size") or 0) > 0,
                      vision_calls)

                analyze_request = last_request(requests_log, "/api/v2/semantic/analyze")
                analyze_headers = (analyze_request or {}).get("headers") or {}
                check(checks, "P08-02b",
                      "正式语义消费者的用途、Provider与本次密钥原文精确一致",
                      bool(analyze_request)
                      and analyze_headers.get(PURPOSE_PROVIDER_HEADER["semantic"]) == FAKE_VISION_PROVIDER_ID
                      and (analyze_request or {}).get("key_matches", {}).get("semantic") is True,
                      {"path": (analyze_request or {}).get("path"), "headers": analyze_headers})
                check(checks, "P08-03b", "页面所示配置与实际请求一致（模型行 + 已发送图片行含 role/sha 前缀）",
                      FAKE_VISION_MODEL_ID in result_text
                      and "已发送实际图片" in result_text
                      and ref_sha[:12] in result_text,
                      {"result": result_text, "gate": gate_text})

                rows = read_docs(page, "semantic_analysis")
                last = (rows or [{}])[-1].get("payload") or {}
                check(checks, "P08-03c", "分析记录写真实图片来源（role/media/sha256，无字节原文）",
                      last.get("reference_images_sent") is True
                      and isinstance(last.get("image_provenance"), list)
                      and (last.get("image_provenance") or [{}])[0].get("sha256") == ref_sha
                      and "data_base64" not in json.dumps(last),
                      last.get("image_provenance"))

                # 事实确认在「理解」阶段进行，先回到该阶段（槽位行只在该面板可见）。
                stage_nav.goto(page, "understand")
                page.wait_for_selector("#slot-list .slot-row", timeout=30_000)
                shared.confirm_slots(page)
                page.click("#stage-next-understand")
                page.click("#suite-seed")
                page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
                page.click("#stage-next-plan")
                shots = page.evaluate(shared.SHOT_IDS)
                assert shots, "走查没有产出 shot"
                shared.compile_all(page, shots)
                submitted = shared.confirm_and_submit(page, expect, shot_ids=shots)
                assert submitted["ok"], f"提交与逐图消费不一致：{submitted}"
                stage_nav.goto(page, "review")
                for shot_id in shots:
                    page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] '
                               'button:has-text("采用候选")')
                    page.wait_for_selector(
                        f'#review-list .review-card[data-shot-id="{shot_id}"][data-selection-state="current"]',
                        timeout=15_000)


                image_request = last_request(requests_log, "/api/v2/images/submit")
                image_headers = (image_request or {}).get("headers") or {}
                check(checks, "P08-02c",
                      "正式生成消费者的用途、Provider与本次密钥原文精确一致",
                      bool(image_request)
                      and image_headers.get(PURPOSE_PROVIDER_HEADER["image"]) == "fake-qwen-image"
                      and (image_request or {}).get("key_matches", {}).get("image") is True,
                      {"path": (image_request or {}).get("path"), "headers": image_headers,
                       "exact_key": (image_request or {}).get("key_matches", {}).get("image")})
                check(checks, "P08-02c-swap",
                      "实际图像请求的密钥不能被同长度语义密钥冒充",
                      (image_request or {}).get("key_matches", {}).get("image") is True
                      and (image_request or {}).get("image_matches_semantic") is False,
                      {"actual_image_equals_semantic":
                       (image_request or {}).get("image_matches_semantic")})


                # 单图 AI 复核（按需显式发起）
                first_shot = shots[0]
                page.click(f'#review-list .review-card[data-shot-id="{first_shot}"] '
                           'button:has-text("比较候选")')
                page.wait_for_selector("#compare-panel:not([hidden])", timeout=15_000)
                page.wait_for_selector("#compare-checklist details.compare-report", timeout=15_000)
                page.locator("#compare-review").click()
                page.wait_for_function(
                    "() => { const node = document.querySelector('[data-compare-vlm]');"
                    " return node && node.getAttribute('data-compare-vlm') === 'checked'; }",
                    timeout=60_000)
                page.wait_for_timeout(300)
                page.click("#compare-close")
                page.wait_for_timeout(200)
                review_request = last_request(requests_log, "/api/v2/review/candidate")
                review_headers = (review_request or {}).get("headers") or {}
                check(checks, "P08-02d",
                      "正式单图复核消费者的用途、Provider与本次密钥原文精确一致",
                      bool(review_request)
                      and review_headers.get(PURPOSE_PROVIDER_HEADER["review"]) == "fake-review"
                      and (review_request or {}).get("key_matches", {}).get("review") is True,
                      {"path": (review_request or {}).get("path"), "headers": review_headers})

                # 整套确定性检查 + 整套 AI 复核（按需显式发起）
                page.click("#suite-review-run")
                page.wait_for_function(
                    "() => (document.getElementById('suite-review-status') || {})"
                    ".textContent.indexOf('整套检查 ') >= 0", timeout=60_000)
                page.click("#suite-ai-review-run")
                page.wait_for_function(
                    "() => (document.getElementById('suite-review-note') || {})"
                    ".textContent.indexOf('fake-qwen-vl-max') >= 0", timeout=60_000)
                page.wait_for_timeout(300)
                suite_request = last_request(requests_log, "/api/v2/review/suite")
                suite_headers = (suite_request or {}).get("headers") or {}
                check(checks, "P08-02e",
                      "正式整套复核消费者的用途、Provider与本次密钥原文精确一致",
                      bool(suite_request)
                      and suite_headers.get(PURPOSE_PROVIDER_HEADER["review"]) == "fake-review"
                      and (suite_request or {}).get("key_matches", {}).get("review") is True,
                      {"path": (suite_request or {}).get("path"), "headers": suite_headers})

                # 交付阶段导出原生项目包（完整历史 ZIP）
                stage_nav.goto(page, "deliver")
                shared.wait_gate(page)
                with page.expect_download(timeout=120_000) as info:
                    page.click("#deliver-project-package")
                info.value.save_as(str(project_zip))
                project_zip_bytes = project_zip.read_bytes()
                delivery_zip = temp_root / "delivery.zip"
                with page.expect_download(timeout=120_000) as delivery_info:
                    page.click("#deliver-export")
                delivery_info.value.save_as(str(delivery_zip))
                delivery_entries = {}
                with zipfile.ZipFile(delivery_zip) as archive:
                    for name in archive.namelist():
                        delivery_entries[name] = archive.read(name).decode("utf-8", "replace")

                # ---------------- P08-06：取消/关闭不应用草稿；查看与设置不供应商外呼 ----------------
                # 此刻三用途 already 各真跑过一次上游调用，计数才有意义（0 → 0 不能证明任何事）。
                idb_before_cancel = page.evaluate(IDB_COUNTS)
                suppliers_before = supplier_calls(vision, image_provider, review_provider, suite_provider)
                page.click("#model-settings-open")
                page.wait_for_selector("#model-settings-dialog[open]", timeout=10_000)
                page.fill("#model-key-image", DRAFT_SENTINELS["image"])
                page.click("#model-settings-cancel")
                page.wait_for_timeout(200)
                cancel_state = password_dialog_state(page)
                page.click("#model-settings-open")
                page.wait_for_selector("#model-settings-dialog[open]", timeout=10_000)
                page.fill("#model-key-semantic", DRAFT_SENTINELS["semantic"])
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                close_state = password_dialog_state(page)
                suppliers_after = supplier_calls(vision, image_provider, review_provider, suite_provider)
                idb_after_cancel = page.evaluate(IDB_COUNTS)
                check(checks, "P08-06a",
                      "取消/关闭不应用草稿：对话框关闭、输入清空、供应商零外呼、存储与文档不变",
                      cancel_state == {"open": False, "values": 0}
                      and close_state == {"open": False, "values": 0}
                      and suppliers_before == suppliers_after
                      and idb_before_cancel == idb_after_cancel,
                      {"cancel": cancel_state, "close": close_state,
                       "suppliers_before": suppliers_before, "suppliers_after": suppliers_after,
                       "idb_unchanged": idb_before_cancel == idb_after_cancel})

                # ---------------- P5：原任务凭据隔离连接（第二项目单链） ----------------
                page.click("#back-home")
                page.wait_for_selector("#new-project-name:not([disabled])", timeout=20_000)

                # 主项目已终态；切 status_unknown 建第二项目，把单任务停在 unknown 在途态：
                # 清 key → 核对被阻 → 补原凭据 → 可核对 → 切回 ok 达终态。
                # 批次自动 poll 的 status 与用户点击不做归因硬断言。
                image_provider.scenario = "status_unknown"
                shared.create_project(page, "P08 P5 隔离连接", reference)
                stage_nav.goto(page, "intake")
                page.wait_for_selector('#stage-panels [data-stage-panel="intake"]:not([hidden])',
                                       timeout=20_000)
                page.click("#analyze-run")
                stage_nav.goto(page, "understand")
                page.wait_for_selector("#slot-list .slot-row", timeout=60_000)
                shared.confirm_slots(page)
                page.click("#stage-next-understand")
                page.click("#suite-seed")
                page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
                page.click("#stage-next-plan")
                p5_shots = page.evaluate(shared.SHOT_IDS)
                assert p5_shots, "P5 走查没有产出 shot"
                shared.compile_all(page, p5_shots)
                p5_submitted = shared.confirm_and_submit(
                    page, expect, shot_ids=p5_shots, submitted_shots=[p5_shots[0]], settle=False)
                assert p5_submitted["ok"], f"P5 提交未落定：{p5_submitted}"
                stage_nav.goto(page, "generate")
                page.click("#batch-stop")
                page.wait_for_timeout(400)
                p5_shot = p5_shots[0]
                p5_row = f'#attempt-list .attempt-row[data-shot-id="{p5_shot}"]'
                # 冻结身份：原任务真正提交时的 provider/target/task 与动作，后面逐步核对不变。
                p5_project = project_id_of(page, "P08 P5 隔离连接")
                frozen_attempt = attempt_of(page, p5_shot, p5_project)
                frozen_provider = (frozen_attempt.get("provider") or {}).get("provider_id")
                frozen_source = (((frozen_attempt.get("execution_identity") or {})
                                  .get("credential_reference") or {}).get("source"))
                frozen_target = {"provider_id": frozen_provider,
                                 "model_id": (frozen_attempt.get("provider") or {}).get("model_id"),
                                 "task_id": frozen_attempt.get("task_id"),
                                 "action_id": frozen_attempt.get("action_id"),
                                 "credential_source": frozen_source}
                captures["p5_frozen_target"] = frozen_target
                submit_before_p5 = len([r for r in requests_log if r["path"].endswith("/api/v2/images/submit")])
                page.click("#model-settings-open")
                page.wait_for_selector("#model-settings-dialog[open]", timeout=10_000)
                cleared = page.evaluate("""() => {
                  const dialog = document.getElementById("model-settings-dialog");
                  const sections = [...dialog.querySelectorAll("fieldset")];
                  const imageSection = sections.find((s) =>
                    ((s.querySelector("legend") || {}).textContent || "").includes("图片生成"));
                  if (!imageSection) return "no-image-section";
                  const clear = [...imageSection.querySelectorAll("button")]
                    .find((b) => (b.textContent || "").includes("清除此模型密钥"));
                  if (!clear) return "no-clear";
                  clear.click();
                  const apply = document.getElementById("model-settings-apply");
                  if (!apply) return "no-apply";
                  apply.click();
                  return "image-section:true";
                }""")



                page.wait_for_timeout(400)

                check(checks, "P08-05a",
                      "image 用途 key 已清除（面板清除入口真实可用）",
                      cleared == "image-section:true", {"cleared": cleared})
                stage_nav.goto(page, "generate")
                page.wait_for_selector(p5_row, timeout=20_000)
                page.wait_for_timeout(500)
                cred_visible = page.locator(f"{p5_row} button[data-original-credentials]").is_visible()
                reconcile_btn = page.locator(f"{p5_row} button:has-text('核对任务')")
                reconcile_disabled = (not reconcile_btn.count()) or reconcile_btn.is_disabled()
                check(checks, "P08-05b",
                      "凭据缺失时核对被阻：出现补原凭据入口、核对按钮禁用",
                      cred_visible is True and reconcile_disabled,
                      {"cred_visible": cred_visible, "reconcile_disabled": reconcile_disabled})

                # 让「当前设置」与原任务目标不同：改用另一个图像 provider 后再补原凭据，
                # 若客户端偷用当前模型/Provider 去核对旧任务，状态请求头与目标核对都会暴露。
                suppliers_before_switch = supplier_calls(
                    vision, image_provider, review_provider, suite_provider)
                page.click("#model-settings-open")
                page.wait_for_selector("#model-provider-image", timeout=10_000)
                switched = page.evaluate("""() => {
                  const select = document.getElementById("model-provider-image");
                  if (!select) return { ok: false, reason: "no-select" };
                  const before = select.value;
                  const other = [...select.options].map((node) => node.value)
                    .find((value) => value && value !== before);
                  if (!other) return { ok: false, reason: "no-other", before: before };
                  select.value = other;
                  select.dispatchEvent(new Event("change", { bubbles: true }));
                  document.getElementById("model-settings-apply").click();
                  return { ok: true, before: before, chosen: other };
                }""")
                page.wait_for_function(
                    "() => !document.getElementById('model-settings-dialog').open", timeout=10_000)
                page.wait_for_timeout(500)
                current_provider = read_current_image_provider(page)
                suppliers_after_switch = supplier_calls(
                    vision, image_provider, review_provider, suite_provider)
                stage_nav.goto(page, "generate")
                page.wait_for_selector(f"{p5_row} button[data-original-credentials]", timeout=20_000)
                page.wait_for_timeout(500)
                cred_visible_after = page.locator(
                    f"{p5_row} button[data-original-credentials]").is_visible()
                reconcile_now = page.locator(f"{p5_row} button:has-text('核对任务')")
                reconcile_blocked_after = (not reconcile_now.count()) or reconcile_now.is_disabled()
                submit_after_switch = len(
                    [r for r in requests_log if r["path"].endswith("/api/v2/images/submit")])
                check(checks, "P08-05e",
                      "当前设置已切到另一个图像 provider，原任务仍按冻结目标判「凭据未就绪」而不外发",
                      switched.get("ok") is True
                      and bool(current_provider) and current_provider != frozen_provider
                      and bool(frozen_provider) and frozen_source == "byok"
                      and cred_visible_after is True and reconcile_blocked_after
                      and suppliers_before_switch == suppliers_after_switch
                      and submit_after_switch == submit_before_p5,
                      {"switch": switched, "current_provider": current_provider,
                       "frozen_provider": frozen_provider, "frozen_source": frozen_source,
                       "reconcile_blocked": reconcile_blocked_after,
                       "suppliers_unchanged": suppliers_before_switch == suppliers_after_switch,
                       "submit_delta": submit_after_switch - submit_before_p5})

                submit_before_p5b = len([r for r in requests_log if r["path"].endswith("/api/v2/images/submit")])
                page.click(f"{p5_row} button[data-original-credentials]")
                page.wait_for_selector("#model-key-original", timeout=10_000)
                page.fill("#model-key-original", SENTINELS["image"])
                page.evaluate("""() => {
                  const apply = document.getElementById("model-settings-apply");
                  if (apply) apply.click();
                }""")

                page.wait_for_timeout(400)
                for _ in range(30):
                    probe_btn = page.locator(f"{p5_row} button:has-text('核对任务')")
                    if probe_btn.count() > 0 and probe_btn.is_enabled():
                        break
                    page.wait_for_timeout(200)
                reconcile_btn2 = page.locator(f"{p5_row} button:has-text('核对任务')")
                reconcile_enabled = reconcile_btn2.count() > 0 and reconcile_btn2.is_enabled()
                check(checks, "P08-05c",
                      "补原凭据后核对恢复可用",
                      reconcile_enabled is True, {"reconcile_enabled": reconcile_enabled})
                page.click(f"{p5_row} button:has-text('核对任务')")
                page.wait_for_timeout(1500)
                submit_after_p5 = len([r for r in requests_log if r["path"].endswith("/api/v2/images/submit")])
                check(checks, "P08-05c2",
                      "用户核对不重提：零新 submit",
                      submit_after_p5 == submit_before_p5b,
                      {"submit_delta": submit_after_p5 - submit_before_p5b})

                # 冻结目标/用途的精确核：状态请求带原 Provider、原用途的本次凭据原文，目标体与
                # 冻结身份逐字段一致；当前动作选择与冻结 action/task 都不被改变。
                frozen_identity = frozen_attempt.get("execution_identity") or {}
                status_request = last_request(requests_log, "/api/v2/images/status")
                status_headers = (status_request or {}).get("headers") or {}
                status_body = find_net_request_body(
                    list(reversed(page.evaluate("() => window.__p08Net"))),
                    "/api/v2/images/status",
                    lambda body: bool((body.get("target") or {}).get("provider_id"))) or {}
                status_target = status_body.get("target") or {}
                frozen_now = attempt_of(page, p5_shot, p5_project)
                current_provider_after = read_current_image_provider(page)
                check(checks, "P08-05f",
                      "原任务核对只按冻结目标/来源外发：Provider=原目标、密钥原文精确、target 逐字段一致；"
                      "当前动作选择与冻结 action/task 不变",
                      bool(status_request)
                      and bool(frozen_provider) and frozen_provider != current_provider_after
                      and status_headers.get(PURPOSE_PROVIDER_HEADER["image"]) == frozen_provider
                      and (status_request or {}).get("key_matches", {}).get("image") is True
                      and status_target.get("provider_id") == frozen_provider
                      and status_target.get("model_id") == frozen_target.get("model_id")
                      and status_target.get("protocol") == frozen_identity.get("protocol")
                      and status_target.get("capability_version") == frozen_identity.get("capability_version")
                      and status_target.get("credential_source") == frozen_source
                      and status_body.get("task_id") == frozen_target.get("task_id")
                      and (frozen_now.get("action_id"), frozen_now.get("task_id")) == (
                          frozen_target.get("action_id"), frozen_target.get("task_id"))
                      and current_provider_after == current_provider,
                      {"status_headers": status_headers, "status_target": status_target,
                       "status_task_id": status_body.get("task_id"), "frozen_target": frozen_target,
                       "current_provider": current_provider,
                       "current_provider_after": current_provider_after,
                       "frozen_now": {"action_id": frozen_now.get("action_id"),
                                      "task_id": frozen_now.get("task_id")}})
                image_provider.scenario = "ok"
                page.click(f"{p5_row} button:has-text('核对任务')")
                page.wait_for_function(
                    f"() => (document.querySelector('{p5_row}') || {{}})"
                    ".getAttribute('data-attempt-state') === 'succeeded'", timeout=60_000)
                shared.wait_terminal(page, [p5_shot])
                p5_state = page.evaluate(
                    f"() => (document.querySelector('{p5_row}') || {{}})"
                    ".getAttribute('data-attempt-state')")
                submit_after_ok = len([r for r in requests_log if r["path"].endswith("/api/v2/images/submit")])
                check(checks, "P08-05d",
                      "切回 ok 后同 task 达终态 succeeded 且零新 submit",
                      p5_state == "succeeded" and submit_after_ok == submit_before_p5,
                      {"state": p5_state, "submit_delta": submit_after_ok - submit_before_p5})
                current_provider_final = read_current_image_provider(page)
                check(checks, "P08-05g",
                      "原任务达终态后当前动作模型选择仍未被切回（新动作照旧用当前设置）",
                      current_provider_final == current_provider
                      and current_provider != frozen_provider,
                      {"current_provider": current_provider, "after": current_provider_final,
                       "frozen_provider": frozen_provider})

                stage_nav.goto(page, "intake")
                page.set_input_files("#ref-file", str(large_reference))
                page.wait_for_selector("#ref-list .ref-row:has-text('large-reference.png')")

                # 服务器正常/失败输出走同一进程流（产品处理器不打印请求日志，异常才写 stderr）；
                # 另发一个契约非法的图像提交体，取回正式处理器真实生成的 400 错误面一起进扫描。
                server_error_status, server_error_raw = http_post(
                    "127.0.0.1", port, "/api/v2/images/submit", b'{"action_id":"short"}',
                    {"Content-Type": "application/json"})

                # ---------------- 完整内容缺席证明（此刻三用途密钥仍在标签页内存里，取证最有意义） ----------------
                page.click("#model-settings-open")
                storage_snapshot = json.loads(page.evaluate(STORAGE_SNAPSHOT))
                storage_texts = {
                    "local_storage": json.dumps(storage_snapshot.get("local_storage") or {},
                                              ensure_ascii=False),
                    "session_storage": json.dumps(storage_snapshot.get("session_storage") or {},
                                                ensure_ascii=False),
                    "document_payloads": "\n".join(storage_snapshot.get("document_payloads") or []),
                    "asset_payloads": "\n".join(storage_snapshot.get("asset_payloads") or []),
                    "asset_blobs": "\n".join(storage_snapshot.get("blob_bytes") or []),
                    "response_bodies": "\n".join(storage_snapshot.get("response_bodies") or []),
                }
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                page.click("#model-settings-open")
                with zipfile.ZipFile(project_zip) as archive:
                    project_entries = {name: archive.read(name).decode("utf-8", "replace")
                                     for name in archive.namelist()}
                page.wait_for_selector("#model-settings-dialog[open]", timeout=10_000)
                dom_html = page.evaluate(DOM_TEXT_SANS_PASSWORD)
                alert_texts = page.evaluate(ALERT_TEXT)
                idb_dump = page.evaluate(IDB_DUMP)
                net = page.evaluate("() => window.__p08Net")
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                haystacks = {
                    "dom": dom_html,
                    "response_bodies": json.dumps(net, ensure_ascii=False),
                    "server_error_response": server_error_raw.decode("utf-8", "replace"),
                    "error_surfaces": "\n".join(alert_texts),
                    "idb_dump": idb_dump,
                    "local_storage": storage_texts["local_storage"],
                    "session_storage": storage_texts["session_storage"],
                    "document_payloads": storage_texts["document_payloads"],
                    "asset_payloads": storage_texts["asset_payloads"],
                    "asset_blobs": storage_texts["asset_blobs"],
                    "delivery_entries": json.dumps(delivery_entries, ensure_ascii=False),
                    "project_entries": json.dumps(project_entries, ensure_ascii=False),
                    "console_logs": "\n".join(console_all + logs["page"]),
                    "server_stdout": server_logs[0].getvalue(),
                    "server_stderr": server_logs[1].getvalue(),
                }
                hits = sentinel_hits(haystacks)
                endpoints = {"semantic": "/api/v2/semantic/analyze", "image": "/api/v2/images/submit",
                             "review": "/api/v2/review/candidate"}
                transmitted = {
                    purpose: (last_request(requests_log, endpoints[purpose]) or {})
                    .get("key_matches", {}).get(purpose) is True
                    for purpose in PURPOSE_ORDER}
                blob_facts = blob_byte_facts(storage_snapshot)
                draft_requests = [item for item in requests_log if item.get("draft_headers")]
                sentinel_sweep = {"hits": hits,
                                  "lengths": {name: len(text) for name, text in haystacks.items()},
                                  "transmitted_keys_exact": transmitted,
                                  "largest_reference_bytes": large_reference.stat().st_size,
                                  "asset_bytes": blob_facts,
                                  "server_error_status": server_error_status,
                                  "draft_headers_seen": len(draft_requests),
                                  "zip_members": {"project": len(project_entries),
                                                  "delivery": len(delivery_entries)}}
                captures["sentinel_sweep"] = sentinel_sweep
                check(checks, "P08-02f",
                      "哨兵不出现在 DOM/响应体/服务器错误面/文档与资产payload/资产原字节/"
                      "local/session/两包解压成员/控制台与服务器输出，且三用途出站密钥原文精确",
                      not hits
                      and all(transmitted.values())
                      and server_error_status == 400
                      and '"INPUT_INVALID"' in haystacks["server_error_response"]
                      and blob_facts["reads_every_asset"] is True
                      and blob_facts["largest_bytes"] == large_bytes
                      and blob_facts["largest_head_is_png"] is True,
                      sentinel_sweep)
                check(checks, "P08-06b",
                      "本次运行没有任何出站请求携带取消/关闭时的草稿哨兵",
                      not draft_requests, {"draft_requests": len(draft_requests)})

                # 正式上传一个故意含非秘密哨兵的有效大图；同一扫描器必须在真实 Blob 中报出。
                page.set_input_files("#ref-file", str(leak_reference))
                page.wait_for_selector("#ref-list .ref-row:has-text('intentional-leak-probe.png')")
                negative_snapshot = json.loads(page.evaluate(STORAGE_SNAPSHOT))
                leak_facts = blob_byte_facts(negative_snapshot)
                clean_blobs = [text for text in (storage_snapshot.get("blob_bytes") or [])
                               if len(text) == large_bytes]
                negative_hits = sentinel_hits({
                    "asset_blobs": "\n".join(negative_snapshot.get("blob_bytes") or []),
                })
                check(checks, "P08-02f-negative",
                      "正式上传的故意泄漏大图使同一字节扫描器判红（非秘密负例），"
                      "且同一扫描器对无泄漏的最大资产不报",
                      negative_hits.get("asset_blobs") == ["image"]
                      and leak_facts["largest_bytes"] == leak_reference.stat().st_size
                      and bool(clean_blobs) and not sentinel_hits({"asset_blobs": "\n".join(clean_blobs)}),
                      {"detected": negative_hits, "fixture_bytes": leak_reference.stat().st_size,
                       "read_bytes": leak_facts["largest_bytes"],
                       "clean_large_blobs": len(clean_blobs)})

                # ---------------- P08-04a：旧格式包经正式 UI 导入被拒绝（不半写） ----------------
                before = page.evaluate(IDB_COUNTS)
                page.click("#back-home")
                page.wait_for_selector("#home-view:not([hidden])", timeout=15_000)
                page.wait_for_selector("#project-list .project-row", timeout=15_000)
                page.wait_for_function(
                    "() => { const node = document.getElementById('import-trigger');"
                    " return node && node.disabled === false; }", timeout=15_000)
                rows_before = page.locator("#project-list .project-row").count()
                downgrade_to_format_one(project_zip, v1_zip)
                with zipfile.ZipFile(v1_zip) as archive:
                    v1_manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                check(checks, "P08-04f", "旧包工件是真实旧格式（format 不变、format_version=1）",
                      v1_manifest.get("format") == PACKAGE_FORMAT
                      and v1_manifest.get("format_version") == 1
                      and v1_manifest.get("format_version") != PACKAGE_FORMAT_VERSION,
                      {"format": v1_manifest.get("format"),
                       "format_version": v1_manifest.get("format_version")})
                page.set_input_files("#import-file", str(v1_zip))
                page.wait_for_function(
                    "() => { const node = document.getElementById('home-error');"
                    " return node && !node.hidden && node.textContent; }", timeout=30_000)
                rejection = page.text_content("#home-error") or ""
                after = page.evaluate(IDB_COUNTS)
                rows_after = page.locator("#project-list .project-row").count()
                check(checks, "P08-04a",
                      "旧格式包经正式 UI 导入被拒绝，且无半份项目/文档/资产新增",
                      bool(rejection) and "版本" in rejection
                      and before == after and rows_before == rows_after,
                      {"rejection": rejection[:200], "before": before, "after": after,
                       "rows": [rows_before, rows_after]})
                captures["import_rejection"] = rejection[:200]
                page.screenshot(path=str(screenshot))
            finally:
                context.close()
        finally:
            stop_server(server)

    captures["production"] = run_production_credential_checks(checks, ref_bytes)

    failed = [item for item in checks if not item["ok"]]
    evidence = {
        "label": label,
        "at": datetime.now(timezone.utc).isoformat(),
        "reference_sha256": ref_sha,
        "checks": checks,
        "captures": {
            "capabilities": captures.get("capabilities"),
            "byok_sources": captures.get("byok_sources"),
            "sentinel_sweep": captures.get("sentinel_sweep"),
            "production": captures.get("production"),
            "import_rejection": captures.get("import_rejection"),
            "vision_calls": vision_calls,
            "request_headers_observed": [
                {"path": item["path"], "headers": item["headers"]} for item in requests_log[-8:]],
        },
        "note": "test-only：fake-vision/fake-image/fake-review 替身经显式注入接缝；生产凭据 fail-closed "
                "用生产适配器 + 假 transport（零上游）证明。非秘密哨兵只出现在输入框内存与本次出站头，"
                "证据只记精确匹配布尔值、计数与长度；服务器正常/失败输出与验证器共用同一进程流。"
                "生产注册表未改（config/product-v2/providers.json 无 diff）。",
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / f"{label}.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence: evals/product-v2/refactor/{label}.json", flush=True)
    print(f"screenshot: {screenshot}", flush=True)
    print(f"RESULT {'PASS' if not failed else 'FAIL'} "
          f"{len(checks) - len(failed)}/{len(checks)}", flush=True)
    return 0 if not failed else 1
if __name__ == "__main__":
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = main(server_logs=(stdout, stderr))
    for stream, target in ((stdout, sys.stdout), (stderr, sys.stderr)):
        target.write(redact_test_lines(stream.getvalue()))
    raise SystemExit(result)


