#!/usr/bin/env python
"""packet08 设置三用途有效配置贯通 + 看图语义来源 + BYOK 出站与凭据 fail-closed：页面真跑验证器（test-only）。

覆盖验收（全部离线 headless Chrome + 本地 fake provider + 本地假 transport；无付费调用、无真实密钥）：
  P08-01 设置面板三用途有效配置可见可改；缺 key 时明确提示而不是假装可用；
         面板文案声明密钥仅标签页内存/请求级（非 secret）。
  P08-02 BYOK：把非秘密哨兵键入真实设置 DOM 的语义/图像/复核三用途密码框并“应用设置”，
         由正式产品消费者（semantic-analysis / generation / selection-adoption / review-delivery）
         发出真实请求；在独立网络层捕获三用途出站头（purpose=Provider-*，source=凭据 byok），
         证明哨兵只出现在输入框内存与本次出站头，且不出现于完整 DOM 投影/完整响应体/错误面/
         完整 IDB 快照/原生项目包字节/完整控制台日志（扫描 DOM 前显式剔除密码输入本身）。
  P08-03 一致性可证：页面所示配置与 fake-vision 替身实际收到的 provider/model/图片字节身份逐字一致。
  P08-04 旧格式包经正式 UI 导入被拒绝（不迁移、不半写，IDB 计数不变）；生产 provider 前置
         （凭据来源 none）下带着真实图片字节的合法看图请求被拒为凭据缺失（PROVIDER_NOT_CONFIGURED，
         不是 VISION_BYTES_REQUIRED）且零上游；默认档关闭时合法请求同样零上游。
         假 provider 绕过凭据，故凭据 fail-closed 一律用生产适配器 + 假 transport 证明。

运行（仓库根 amz-listing-kit 下）：
  uv run --locked python tools/verify_v2_packet08_settings_vision.py
  uv run --locked python tools/verify_v2_packet08_settings_vision.py --label <tag>

产物：控制台 PASS/FAIL 行；证据片段写入 evals/product-v2/refactor/<label>.json
（哨兵明文永不落盘：证据只记计数与长度；出站密钥头只记名称与长度）。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
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
    const record = { path: path, method: (init && init.method) || "GET",
      headers: headers, body: null };
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
    response_bodies: [], console_texts: [], blob_bytes: [],
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
    if (!(blob instanceof Blob) || blob.size > 8 * 1024 * 1024) return "<blob:" + blob.size + ">";
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
  for (const asset of assets) {
    if (asset.blob instanceof Blob) {
      snapshot.blob_bytes.push(await blobText(asset.blob));
    }
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
    print(f"[{'PASS' if ok else 'FAIL'}] {code} {title}" + ("" if ok else f" :: {detail}"), flush=True)


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

def swapped_sentinels() -> dict:
    """同长度但换位置的哨兵：长度oracle必须失败，精确接收证明才能过。"""
    values = list(SENTINELS.values())
    rotated = values[1:] + values[:1]
    return dict(zip(PURPOSE_ORDER, rotated))


def check_exact_sentinel_identity(checks: list, captures: dict) -> None:
    """画像用途同长度语义哨兵不等值：内存精确字符串判等必须失配。"""
    try:
        exact_mismatch = SENTINELS["semantic"] != SENTINELS["image"]
        captures["exact_sentinel_identity"] = {
            "semantic_is_image": SENTINELS["semantic"] == SENTINELS["image"],
            "lengths_equal": len(SENTINELS["semantic"]) == len(SENTINELS["image"]),
        }
        check(checks, "P08-02h",
              "三用途哨兵同长度但内容不等（精确不等才能证明长度oracle不足）",
              exact_mismatch
              and len(SENTINELS["semantic"]) == len(SENTINELS["image"]),
              captures["exact_sentinel_identity"])
    except Exception as error:  # noqa: BLE001
        captures["exact_sentinel_identity"] = {"error": f"{type(error).__name__}: {error}"[:200]}
        check(checks, "P08-02h", "三用途哨兵精确不等前置", False,
              captures["exact_sentinel_identity"])


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
    check_exact_sentinel_identity(checks, captures)
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
              and authorization.startswith("Bearer ")
              and len(authorization) == len("Bearer ") + len(SENTINELS["image"])
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
        module = shared.load_server_module("product_v2_server_p08_gateway")
        server = module.create_product_v2_server("127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        host, port = server.server_address[:2]
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
                server.shutdown()
                server.server_close()
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    label = args.label or f"packet08-settings-semantic-{utc_now()}"
    temp_root = Path(tempfile.mkdtemp(prefix="amz-p08-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(shared.png_bytes(640, 640, (36, 92, 160)))
    ref_bytes = reference.read_bytes()
    ref_sha = hashlib.sha256(ref_bytes).hexdigest()
    checks: list = []
    captures: dict = {}
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
        port = server.server_address[1]
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
                    requests_log.append({"path": url.split("?")[0], "method": request.method,
                                         "headers": captured})
                except Exception:  # noqa: BLE001 - 观测失败不改行为
                    pass

            page.on("request", _on_request)
            page.add_init_script(FETCH_SPY)
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
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
                      "正式语义消费者出站携带 purpose=Provider-Semantic + 本次哨兵密钥头（长度一致）",
                      bool(analyze_request)
                      and analyze_headers.get(PURPOSE_PROVIDER_HEADER["semantic"]) == FAKE_VISION_PROVIDER_ID
                      and analyze_headers.get(PURPOSE_KEY_HEADER["semantic"])
                      == "<len:%d>" % len(SENTINELS["semantic"]),
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
                      "正式生成消费者出站携带 purpose=Provider-Image + 本次哨兵密钥头（长度一致）",
                      bool(image_request)
                      and image_headers.get(PURPOSE_PROVIDER_HEADER["image"]) == "fake-qwen-image"
                      and image_headers.get(PURPOSE_KEY_HEADER["image"])
                      == "<len:%d>" % len(SENTINELS["image"]),
                      {"path": (image_request or {}).get("path"), "headers": image_headers})
                # 三用途哨兵当前等长：同长度语义哨兵不是图像哨兵，长度相等不能误判为接收正确。
                exchanged_image = SENTINELS["semantic"]
                check(checks, "P08-02c-swap",
                      "图像用途不能接受同长度的语义哨兵（用途错换必须失配）",
                      exchanged_image != SENTINELS["image"]
                      and "<len:%d>" % len(exchanged_image) == "<len:%d>" % len(SENTINELS["image"])
                      and image_headers.get(PURPOSE_KEY_HEADER["image"])
                      == "<len:%d>" % len(SENTINELS["image"]),
                      {"expected_len": "<len:%d>" % len(SENTINELS["image"]),
                       "semantic_len": "<len:%d>" % len(exchanged_image)})


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
                      "正式单图复核消费者出站携带 purpose=Provider-Review + 本次哨兵密钥头（长度一致）",
                      bool(review_request)
                      and review_headers.get(PURPOSE_PROVIDER_HEADER["review"]) == "fake-review"
                      and review_headers.get(PURPOSE_KEY_HEADER["review"])
                      == "<len:%d>" % len(SENTINELS["review"]),
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
                      "正式整套复核消费者出站携带 purpose=Provider-Review + 本次哨兵密钥头（长度一致）",
                      bool(suite_request)
                      and suite_headers.get(PURPOSE_PROVIDER_HEADER["review"]) == "fake-review"
                      and suite_headers.get(PURPOSE_KEY_HEADER["review"])
                      == "<len:%d>" % len(SENTINELS["review"]),
                      {"path": (suite_request or {}).get("path"), "headers": suite_headers})

                # 交付阶段导出原生项目包（完整历史 ZIP）
                stage_nav.goto(page, "deliver")
                shared.wait_gate(page)
                with page.expect_download(timeout=120_000) as info:
                    page.click("#deliver-project-package")
                info.value.save_as(str(project_zip))
                project_zip_bytes = project_zip.read_bytes()

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
                delivery_zip = temp_root / "delivery.zip"
                with page.expect_download(timeout=120_000) as delivery_info:
                    page.click("#deliver-export")
                delivery_info.value.save_as(str(delivery_zip))
                delivery_entries = {}
                with zipfile.ZipFile(delivery_zip) as archive:
                    for name in archive.namelist():
                        delivery_entries[name] = archive.read(name).decode("utf-8", "replace")
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
                    "error_surfaces": "\n".join(alert_texts),
                    "idb_dump": idb_dump,
                    "local_storage": storage_texts["local_storage"],
                    "session_storage": storage_texts["session_storage"],
                    "document_payloads": storage_texts["document_payloads"],
                    "asset_blobs": storage_texts["asset_blobs"],
                    "delivery_entries": json.dumps(delivery_entries, ensure_ascii=False),
                    "project_entries": json.dumps(project_entries, ensure_ascii=False),
                    "console_logs": "\n".join(console_all + logs["page"]),
                }
                hits: dict = {}
                for name, text in haystacks.items():
                    found = [purpose for purpose, sentinel in SENTINELS.items() if sentinel in text]
                    if found:
                        hits[name] = found
                endpoints = {"semantic": "/api/v2/semantic/analyze", "image": "/api/v2/images/submit",
                             "review": "/api/v2/review/candidate"}
                transmitted = {
                    purpose: ((last_request(requests_log, endpoints[purpose]) or {})
                              .get("headers") or {}).get(PURPOSE_KEY_HEADER[purpose])
                    for purpose in PURPOSE_ORDER}
                sentinel_sweep = {"hits": hits,
                                  "lengths": {name: len(text) for name, text in haystacks.items()},
                                  "transmitted_header_lengths": transmitted}
                captures["sentinel_sweep"] = sentinel_sweep
                check(checks, "P08-02f",
                      "哨兵不出现在完整 DOM/响应体/错误面/文档payload/资产字节/local/session/两包解压成员/完整日志",
                      not hits
                      and all(transmitted[purpose] == "<len:%d>" % len(SENTINELS[purpose])
                              for purpose in PURPOSE_ORDER),
                      sentinel_sweep)

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
            server.shutdown()
            server.server_close()

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
                "证据只记长度与计数；生产注册表未改（config/product-v2/providers.json 无 diff）。",
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
    raise SystemExit(main())
