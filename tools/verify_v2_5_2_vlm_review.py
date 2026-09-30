#!/usr/bin/env python
"""V2.5.2 证据：可替换 VLM 复核 Provider（fake 契约 + 已标样例 + 浏览器闭环；0 次真实模型调用）。

检查：
  1) ESM/语法门（domain / workspace / harness / 新 provider 模块）。
  2) 跨语言词表一致；复核 provider 复用 SEL-003 通道（不新建 HTTP 客户端/适配器）静态守卫。
  3) 已标样例（fixtures）：合法输出 → findings；未知 check / 越界置信度 / 截断 → 分类拒绝。
  4) fake provider 场景矩阵：ok/clean/unknown/timeout/非法输出/拒绝/限流/HTTP/鉴权/内部错误
     分类正确，且一次调用只调用一次（无隐藏重提）。
  5) 无状态端点契约：capabilities 暴露 review；哈希不一致 → input_rejected；超时 → 504 unknown；
     非法输出 → 502 INVALID_RESPONSE（浏览器侧投影为 Unknown，由 R17 与走查证明）。
  6) 浏览器契约套件 R14–R21 全过（真实 Chromium）；R01–R13 旧套件回归全过。
  7) 真实工作台走查（假 provider）：候选 → 点“自动复核（VLM）” → 报告出现 VLM 发现并保留确定性层；
     切到 unknown 场景再点 → 报告出现 UNKNOWN 且不伪造 PASS；刷新持久化；候选与 Attempt 不变（不自动采纳）。
  8) 正式入口 --check 全过；零意外 console error / page error。

运行：
  uv run --locked python tools/verify_v2_5_2_vlm_review.py --label final
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from http import client as http_client
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402  （V2.UI.2 六阶段工作台导航）
from console import enable_utf8  # noqa: E402
enable_utf8()

from src.providers.v2_dashscope_review import (  # noqa: E402
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL_ID,
    DEFAULT_TIMEOUT_SECONDS,
    DashScopeReviewProvider,
)
from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FAKE_SCENARIOS, FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402
from src.providers.v2_registry import create_review_provider, load_registry  # noqa: E402
from src.providers.v2_review import (  # noqa: E402
    REVIEW_CONTRACT_VERSION,
    VLM_CHECKS,
    DecodedImage,
    DecodedReviewRequest,
    ShotContext,
    parse_review_request,
)
from src.providers.v2_semantic import SemanticFailure  # noqa: E402

PRODUCT_DIR = ROOT / "app" / "product_v2"
HARNESS_DIR = ROOT / "evals" / "product-v2" / "harness"
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"
FIXTURE_DIR = EVIDENCE_DIR / "fixtures" / "v2.5.2"
PROVIDERS_JSON = ROOT / "config" / "product-v2" / "providers.json"

EXPECTED_CASES = [f"R{index}" for index in range(14, 22)]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v251 = load_module(ROOT / "tools" / "verify_v2_5_1_deterministic_review.py", "verify_v251")
server_module = v251.load_server_module()


def review_js_text() -> str:
    return (PRODUCT_DIR / "domain" / "review.js").read_text(encoding="utf-8")


def check_static_guards() -> list[dict]:
    checks: list[dict] = []
    review_text = review_js_text()
    checks.append({
        "id": "V2.5.2-01",
        "title": "综合语法门：新 provider / workspace / 两个 harness 通过 node --check 与 Python AST",
        "ok": False, "detail": None,
    })
    node_targets = [
        "app/product_v2/domain/review.js", "app/product_v2/workspace.js",
        "evals/product-v2/harness/review-contract.js",
        "evals/product-v2/harness/review-provider-contract.js",
    ]
    node_failed = []
    for relative in node_targets:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)], cwd=str(ROOT),
                                   capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            node_failed.append({"file": relative, "stderr": completed.stderr.strip()[-200:]})
    py_targets = [
        "src/providers/v2_review.py", "src/providers/v2_dashscope_review.py",
        "src/providers/v2_langchain_chat.py", "src/providers/v2_fake_review.py",
        "src/providers/v2_registry.py", "app/product_v2_server.py",
        "tools/verify_v2_5_2_vlm_review.py",
    ]
    py_failed = []
    for relative in py_targets:
        text = (ROOT / relative).read_text(encoding="utf-8")
        try:
            compile(text, relative, "exec")
        except SyntaxError as error:
            py_failed.append({"file": relative, "error": str(error)[:200]})
    first = checks[0]
    first["ok"] = not node_failed and not py_failed
    first["detail"] = {"node_failed": node_failed, "py_failed": py_failed}

    block = re.search(r"export const VLM_CHECK_TO_RULE = Object\.freeze\(\{(.*?)\}\);",
                      review_text, re.S)
    js_checks = re.findall(r"([a-z_]+):\s*\"vlm\.", block.group(1)) if block else []
    js_version = re.search(r'REVIEW_CONTRACT_VERSION = "([^"]+)"', review_text)
    checks.append({
        "id": "V2.5.2-02",
        "title": "跨语言一致：VLM check 词表与合同版本在服务端与浏览器侧完全一致",
        "ok": bool(block) and js_checks == list(VLM_CHECKS)
        and js_version and js_version.group(1) == REVIEW_CONTRACT_VERSION,
        "detail": {"js_checks": js_checks, "py_checks": list(VLM_CHECKS),
                   "js_version": js_version.group(1) if js_version else None,
                   "py_version": REVIEW_CONTRACT_VERSION},
    })

    review_provider = (ROOT / "src/providers/v2_dashscope_review.py").read_text(encoding="utf-8")
    forbidden = [pattern for pattern in (
        r"^\s*import requests", r"^\s*import httpx", r"^\s*from requests",
        r"urllib\.request", r"http\.client", r"^\s*import openai", r"^\s*from openai",
        r"def _default_chat_model",
    ) if re.search(pattern, review_provider, re.M)]
    checks.append({
        "id": "V2.5.2-03",
        "title": "不重复造轮子：复核 provider 复用 SEL-003 通道（ChatOpenAI + 共享错误映射），零自建传输",
        "ok": not forbidden
        and "default_chat_model" in review_provider
        and "map_openai_exception" in review_provider
        and "langchain-openai/ChatOpenAI" in review_provider
        and (ROOT / "src/providers/v2_langchain_chat.py").is_file(),
        "detail": {"forbidden_hits": forbidden,
                   "shared_model": "default_chat_model" in review_provider,
                   "shared_errors": "map_openai_exception" in review_provider},
    })

    registry = json.loads(PROVIDERS_JSON.read_text(encoding="utf-8"))
    entries = {item["id"]: item for item in registry.get("providers", [])}
    real = entries.get("dashscope-review", {})
    fake = entries.get("fake-review", {})
    checks.append({
        "id": "V2.5.2-04",
        "title": "注册表与代码一致：review 角色、真实/假 adapter、模型环境变量与默认选择",
        "ok": registry.get("default_review_provider_id") == "dashscope-review"
        and registry.get("review_provider_selection_env") == "AMZ_V2_REVIEW_PROVIDER"
        and real.get("role") == "review" and real.get("adapter") == "v2_dashscope_review"
        and real.get("model_env") == "REVIEW_MODEL"
        and real.get("capabilities", {}).get("reference_images") is True
        and fake.get("role") == "review" and fake.get("adapter") == "v2_fake_review"
        and fake.get("capabilities", {}).get("test_double") is True,
        "detail": {"default": registry.get("default_review_provider_id"),
                   "real": real.get("adapter"), "fake": fake.get("adapter")},
    })

    provider = create_review_provider(env={"AMZ_V2_REVIEW_PROVIDER": "fake-review",
                                           "AMZ_V2_FAKE_REVIEW_SCENARIO": "clean"})
    checks.append({
        "id": "V2.5.2-05",
        "title": "注册表构造：环境变量能选择 fake-review（场景 clean）且真实默认模型已登记",
        "ok": isinstance(provider, FakeReviewProvider) and provider.scenario == "clean"
        and bool(DEFAULT_MODEL_ID) and DEFAULT_TIMEOUT_SECONDS > 0 and DEFAULT_MAX_TOKENS > 0,
        "detail": {"provider": getattr(provider, "provider_id", None),
                   "scenario": getattr(provider, "scenario", None),
                   "model": DEFAULT_MODEL_ID},
    })
    return checks


def review_payload(png: bytes, **overrides) -> dict:
    payload = {
        "candidate": {
            "media_type": "image/png",
            "sha256": hashlib.sha256(png).hexdigest(),
            "data_base64": base64.b64encode(png).decode("ascii"),
        },
        "references": [],
        "shot": {"title": "主图", "purpose": "白底展示商品",
                 "keep_items": ["商品外观"], "allow_changes": ["背景"]},
        "platform": "amazon_us",
        "product_facts": [{"label": "材质", "value": "不锈钢"}],
        "locale": "zh-CN",
    }
    payload.update(overrides)
    return payload


class _StubRaw:
    def __init__(self, finish_reason: str | None = None) -> None:
        self.response_metadata = {"finish_reason": finish_reason} if finish_reason else {}
        self.additional_kwargs: dict = {}
        self.content = ""
        self.usage_metadata: dict = {}


class _StubStructured:
    def __init__(self, result: dict) -> None:
        self._result = result
        self.messages: list | None = None
        self.calls = 0

    def invoke(self, messages: list) -> dict:
        self.calls += 1
        self.messages = messages
        return self._result


class _StubLLM:
    def __init__(self, structured: _StubStructured) -> None:
        self._structured = structured

    def with_structured_output(self, *_args, **_kwargs) -> _StubStructured:
        return self._structured


def fixture_result_map(fixture: dict) -> dict:
    kind = fixture["kind"]
    if kind == "parsed":
        return {"raw": None, "parsed": fixture["output"], "parsing_error": None}
    if kind == "truncated":
        return {"raw": _StubRaw("length"), "parsed": None, "parsing_error": None}
    raise ValueError("未知样例类型：" + str(kind))


def run_fixture_checks(png: bytes) -> list[dict]:
    request = parse_review_request(review_payload(png))
    checks: list[dict] = []
    for index, path in enumerate(sorted(FIXTURE_DIR.glob("*.json")), start=1):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        structured = _StubStructured(fixture_result_map(fixture))
        provider = DashScopeReviewProvider(
            api_key="sk-fixture-only", model_id="fixture-vlm",
            llm_factory=lambda structured=structured: _StubLLM(structured))
        expected = fixture["expect"]
        detail: dict = {"name": fixture["name"], "kind": fixture["kind"]}
        ok = False
        try:
            result = provider.review(request)
            detail["state"] = "findings"
            detail["checks"] = [item["check"] for item in result.findings]
            detail["candidate_sha256"] = result.candidate_sha256[:12]
            messages = structured.messages or []
            content = messages[-1].content if messages else []
            image_blocks = [block for block in content
                            if isinstance(block, dict) and block.get("type") == "image_url"]
            detail["image_blocks"] = len(image_blocks)
            ok = expected.get("outcome") == "findings" \
                and detail["checks"] == expected.get("checks") \
                and len(image_blocks) == 1 + len(request.references)
            if fixture["name"] == "ok-two-findings" and image_blocks:
                url = image_blocks[0]["image_url"]["url"]
                ok = ok and url.startswith("data:image/png;base64,")
                detail["data_url_prefix"] = url[:30]
        except SemanticFailure as failure:
            detail["state"] = "rejected"
            detail["code"] = failure.code
            detail["family"] = failure.family
            detail["retry_policy"] = failure.retry_policy
            ok = expected.get("error_code") == failure.code \
                and expected.get("error_family") == failure.family
        checks.append({
            "id": f"V2.5.2-F{index:02d}",
            "title": "已标样例 " + fixture["name"] + "：" + fixture["note"].split("；")[0],
            "ok": ok, "detail": detail,
        })
    return checks


def run_fake_matrix_checks(png: bytes) -> list[dict]:
    request = parse_review_request(review_payload(png))
    expectations = {
        "unknown": ("provider_unknown", "PROVIDER_TIMEOUT", "requires_review"),
        "timeout_before_send": ("provider_failed", "PROVIDER_TIMEOUT", "retryable"),
        "invalid_output": ("provider_failed", "INVALID_RESPONSE", "retryable"),
        "refusal": ("provider_failed", "PROVIDER_REFUSED", "fatal"),
        "rate_limited": ("provider_failed", "PROVIDER_RATE_LIMITED", "retryable"),
        "http_error": ("provider_failed", "PROVIDER_HTTP_ERROR", "retryable"),
        "auth_failed": ("provider_failed", "PROVIDER_AUTH_FAILED", "fatal"),
        "internal_error": ("internal", "INTERNAL_ERROR", "requires_review"),
    }
    results = []
    fake_ok = FakeReviewProvider("ok")
    ok_result = fake_ok.review(request)
    results.append({"scenario": "ok", "family": None, "code": None, "retry_policy": None,
                    "findings": len(ok_result.findings), "calls": len(fake_ok.calls)})
    fake_clean = FakeReviewProvider("clean")
    clean_result = fake_clean.review(request)
    results.append({"scenario": "clean", "family": None, "code": None, "retry_policy": None,
                    "findings": len(clean_result.findings), "calls": len(fake_clean.calls)})
    for scenario in sorted(expectations):
        provider = FakeReviewProvider(scenario)
        try:
            provider.review(request)
            results.append({"scenario": scenario, "family": "NO_ERROR", "code": None,
                            "retry_policy": None, "findings": None,
                            "calls": len(provider.calls)})
        except SemanticFailure as failure:
            results.append({"scenario": scenario, "family": failure.family,
                            "code": failure.code, "retry_policy": failure.retry_policy,
                            "findings": None, "calls": len(provider.calls)})
    ok = (results[0]["findings"] == 2 and results[0]["calls"] == 1
          and results[1]["findings"] == 0 and results[1]["calls"] == 1)
    for item in results[2:]:
        expected = expectations[item["scenario"]]
        ok = ok and (item["family"], item["code"], item["retry_policy"]) == expected \
            and item["calls"] == 1
    return [{
        "id": "V2.5.2-06",
        "title": "fake provider 场景矩阵：ok/clean 返回，其余 8 类按四归口分类，且每次只调用一次",
        "ok": ok, "detail": {"scenarios": results, "declared": list(FAKE_SCENARIOS)},
    }]


def http_json(host: str, port: int, method: str, path: str,
              payload: dict | None = None) -> tuple[int, dict | None]:
    connection = http_client.HTTPConnection(host, port, timeout=30)
    try:
        body = None
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers = {"Content-Type": "application/json; charset=utf-8"}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        return response.status, parsed
    finally:
        connection.close()


def run_endpoint_checks(png: bytes) -> list[dict]:
    """无状态端点契约：用假复核 provider 走真实 HTTP；不触网、不落盘。"""

    holder = {"scenario": "ok"}
    port = v251.free_port()
    server = server_module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"),
        review_provider_factory=lambda: FakeReviewProvider(holder["scenario"]))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks: list[dict] = []
    payload = review_payload(png)
    try:
        _, caps = http_json("127.0.0.1", port, "GET", "/api/v2/capabilities")
        review_block = (caps or {}).get("review") or {}
        checks.append({
            "id": "V2.5.2-07",
            "title": "capabilities 暴露 review：合同、端点、provider 身份与参考图能力",
            "ok": (caps or {}).get("ok") is True
            and review_block.get("contract") == REVIEW_CONTRACT_VERSION
            and review_block.get("endpoint") == "/api/v2/review/candidate"
            and review_block.get("provider", {}).get("provider_id") == "fake-review"
            and review_block.get("provider", {}).get("capabilities", {})
            .get("reference_images") is True,
            "detail": review_block.get("provider"),
        })

        status, body = http_json("127.0.0.1", port, "POST", "/api/v2/review/candidate", payload)
        result = (body or {}).get("result") or {}
        checks.append({
            "id": "V2.5.2-08",
            "title": "复核路由（fake ok）：200 且发现绑定候选 sha256，不含任何采纳/选择字段",
            "ok": status == 200 and (body or {}).get("ok") is True
            and (body or {}).get("unknown") is False
            and result.get("candidate_sha256") == hashlib.sha256(png).hexdigest()
            and len(result.get("findings") or []) >= 1
            and all(item.get("check") for item in result.get("findings") or [])
            and "accept" not in json.dumps(result, ensure_ascii=False).lower()
            and "selection" not in json.dumps(result, ensure_ascii=False).lower(),
            "detail": {"status": status, "findings": len(result.get("findings") or [])},
        })

        bad = json.loads(json.dumps(payload))
        bad["candidate"]["sha256"] = "0" * 64
        status, body = http_json("127.0.0.1", port, "POST", "/api/v2/review/candidate", bad)
        checks.append({
            "id": "V2.5.2-09",
            "title": "图片哈希与字节不一致 → input_rejected/400（不调用模型）",
            "ok": status == 400 and (body or {}).get("error", {}).get("family") == "input_rejected"
            and (body or {}).get("unknown") is False,
            "detail": (body or {}).get("error"),
        })

        holder["scenario"] = "unknown"
        status, body = http_json("127.0.0.1", port, "POST", "/api/v2/review/candidate", payload)
        error = (body or {}).get("error") or {}
        checks.append({
            "id": "V2.5.2-10",
            "title": "超时/结果未知 → 504 + unknown=true + provider_unknown/requires_review",
            "ok": status == 504 and (body or {}).get("unknown") is True
            and error.get("family") == "provider_unknown"
            and error.get("retry_policy") == "requires_review",
            "detail": {"status": status, "error": error},
        })

        holder["scenario"] = "invalid_output"
        status, body = http_json("127.0.0.1", port, "POST", "/api/v2/review/candidate", payload)
        error = (body or {}).get("error") or {}
        checks.append({
            "id": "V2.5.2-11",
            "title": "非法模型输出 → 502 INVALID_RESPONSE（服务端 provider_failed，浏览器投影为 Unknown）",
            "ok": status == 502 and error.get("code") == "INVALID_RESPONSE"
            and error.get("family") == "provider_failed",
            "detail": {"status": status, "error": error},
        })
    finally:
        server.shutdown()
        server.server_close()
    return checks


def run_browser_checks(stamp: str, screenshots: list[str], console_errors: list[str],
                       page_errors: list[str], ui: dict) -> list[dict]:
    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    checks: list[dict] = []
    holder = {"scenario": "ok"}
    port = v251.free_port()
    server = server_module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"),
        review_provider_factory=lambda: FakeReviewProvider(holder["scenario"]))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    static_server, static_url = v251.start_static_server()
    temp_root = Path(tempfile.mkdtemp(prefix="amz-v252-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(v251.png_bytes(16, 16, (36, 92, 160)))
    base = f"http://127.0.0.1:{port}"
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            harness_browser = pw.chromium.launch(headless=True)
            try:
                regression = v251.read_suite(
                    harness_browser, static_url + "/harness/review-contract.html",
                    "__V2_REVIEW_RESULTS__", console_errors, page_errors)
                provider_suite = v251.read_suite(
                    harness_browser, static_url + "/harness/review-provider-contract.html",
                    "__V2_REVIEW_PROVIDER_RESULTS__", console_errors, page_errors)
            finally:
                harness_browser.close()
            checks.append({
                "id": "V2.5.2-12",
                "title": "R01–R13 旧套件回归：注册表升级到 v2.5.2 后全部通过",
                "ok": regression.get("status") == "passed",
                "detail": {"status": regression.get("status"),
                           "failed": regression.get("failed_ids")},
            })
            checks.append({
                "id": "V2.5.2-13",
                "title": "R14–R21 复核契约套件：词表/映射/合并/Unknown/反向探针全部通过",
                "ok": provider_suite.get("status") == "passed"
                and sorted(item["id"] for item in provider_suite.get("cases", []))
                == EXPECTED_CASES,
                "detail": {"status": provider_suite.get("status"),
                           "failed": provider_suite.get("failed_ids"),
                           "cases": len(provider_suite.get("cases", []))},
            })

            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 980})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))

                def probe() -> dict:
                    return page.evaluate(v251.PROBE)

                def row(shot_id: str):
                    return page.locator(
                        f'#attempt-list .attempt-row[data-shot-id="{shot_id}"]')

                def wait_state(shot_id: str, state: str, timeout: int = 30_000) -> None:
                    expect(row(shot_id)).to_have_attribute(
                        "data-attempt-state", state, timeout=timeout)

                def wait_candidate_ui(shot_id: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(shot) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + shot + '"]');
                            return Boolean(node && node.querySelector('.attempt-candidate'));
                        }""", arg=shot_id, timeout=timeout)

                def wait_review_text(shot_id: str, needle: str, timeout: int = 30_000) -> None:
                    page.wait_for_function(
                        """(payload) => {
                            const node = document.querySelector(
                                '#attempt-list .attempt-row[data-shot-id="' + payload.shot + '"]');
                            const line = node && node.querySelector('.attempt-review');
                            return Boolean(line && (line.textContent || '').indexOf(payload.needle) >= 0);
                        }""", arg={"shot": shot_id, "needle": needle}, timeout=timeout)

                def click_row_button(shot_id: str, text: str) -> None:
                    stage_nav.goto(page, "generate")
                    row(shot_id).locator(f'button:has-text("{text}")').first.click()

                def generate_and_settle(shot_id: str) -> None:
                    click_row_button(shot_id, "生成这张图")
                    wait_state(shot_id, "submitted")
                    click_row_button(shot_id, "核对任务")
                    wait_state(shot_id, "succeeded")

                page.goto(base + "/", wait_until="networkidle")
                page.fill("#new-project-name", "审计商品 · VLM 复核")
                page.click("#create-project")
                page.click('#project-list .project-row button[data-action="open"]')
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
                page.evaluate(v251.SEED_SLOTS, project_ids[0])
                page.reload(wait_until="networkidle")
                page.click("#suite-seed")
                expect(page.locator("#shot-list .shot-row")).to_have_count(4)
                expect(page.locator("#prompt-list .shot-spec")).to_have_count(4)
                initial = probe()
                shot_ids = initial["shot_ids"]
                v251.compile_all(page, shot_ids)
                ok_shot = shot_ids[0]
                stage_nav.goto(page, "generate")
                expect(page.locator("#confirm-action")).to_be_enabled()
                page.click("#confirm-action")
                expect(page.locator("#confirm-record")).to_contain_text("已确认 v")
                generate_and_settle(ok_shot)
                wait_candidate_ui(ok_shot)
                wait_review_text(ok_shot, "自动检查 " + REVIEW_CONTRACT_VERSION)
                before = probe()
                candidate_before = v251.candidate_json(before, ok_shot)
                row(ok_shot).locator("button[data-review-action]").click()
                wait_review_text(ok_shot, "VLM 已检查")
                after = probe()
                review_doc = max(after.get("review_reports") or [{"version": 0, "payload": {}}],
                                 key=lambda item: item["version"])["payload"]
                vlm_findings = [item for item in review_doc.get("findings", [])
                                if item.get("layer") == "vlm"]
                deterministic = [item for item in review_doc.get("findings", [])
                                 if item.get("layer") != "vlm"]
                checks.append({
                    "id": "V2.5.2-14",
                    "title": "工作台走查：点“自动复核（VLM）”后报告落 checked，VLM 发现与确定性层并存",
                    "ok": review_doc.get("vlm", {}).get("outcome") == "checked"
                    and len(vlm_findings) >= 1
                    and all(item.get("rule_id", "").startswith("vlm.") for item in vlm_findings)
                    and any(item.get("rule_id") == "vlm.deformity" for item in vlm_findings)
                    and len(deterministic) >= 1
                    and review_doc.get("asset_sha256")
                    == v251.candidate_of(after, ok_shot)[-1]["payload"]["asset_sha256"],
                    "detail": {"outcome": review_doc.get("vlm", {}).get("outcome"),
                               "vlm_findings": [item.get("rule_id") for item in vlm_findings],
                               "deterministic": len(deterministic)},
                })
                checks.append({
                    "id": "V2.5.2-15",
                    "title": "不自动采纳：复核不改变候选字节身份与 Attempt 状态",
                    "ok": v251.candidate_json(after, ok_shot) == candidate_before
                    and (after.get("attempt_chains", {}).get(ok_shot) or [])[-1]
                    ["payload"]["state"] == "succeeded",
                    "detail": {"candidate": v251.candidate_json(after, ok_shot)[:24],
                               "state": (after.get("attempt_chains", {}).get(ok_shot) or [{}])[-1]
                               .get("payload", {}).get("state")},
                })

                page.reload(wait_until="networkidle")
                wait_candidate_ui(ok_shot)
                wait_review_text(ok_shot, "VLM 已检查")
                reloaded = probe()
                docs_before_reload = len(v251.reviews_for(after, review_doc.get("candidate_id")))
                reloaded_docs = v251.reviews_for(reloaded, review_doc.get("candidate_id"))
                latest_reload = max(reloaded_docs, key=lambda item: item["version"]) \
                    if reloaded_docs else {"payload": {}}
                checks.append({
                    "id": "V2.5.2-16",
                    "title": "刷新持久化：复核块仍在、版本链不继续增长（重开项目不重复铺报告）",
                    "ok": len(reloaded_docs) == docs_before_reload
                    and latest_reload["payload"].get("vlm", {}).get("outcome") == "checked",
                    "detail": {"docs_before": docs_before_reload,
                               "docs_after": len(reloaded_docs)},
                })

                holder["scenario"] = "unknown"
                row(ok_shot).locator("button[data-review-action]").click()
                wait_review_text(ok_shot, "VLM 未完成")
                unknown = probe()
                unknown_doc = max(unknown.get("review_reports") or [{"version": 0, "payload": {}}],
                                  key=lambda item: item["version"])["payload"]
                unknown_findings = [item for item in unknown_doc.get("findings", [])
                                    if item.get("layer") == "vlm"]
                checks.append({
                    "id": "V2.5.2-17",
                    "title": "失败保留 Unknown：复核未完成不伪造 PASS，候选/Attempt 保持不变",
                    "ok": unknown_doc.get("vlm", {}).get("outcome") == "unknown"
                    and any(item.get("severity") == "UNKNOWN"
                            and item.get("rule_id") == "vlm.inspection_unavailable"
                            for item in unknown_findings)
                    and not any(item.get("severity") == "BLOCK" for item in unknown_findings)
                    and v251.candidate_json(unknown, ok_shot) == candidate_before,
                    "detail": {"outcome": unknown_doc.get("vlm", {}).get("outcome"),
                               "vlm_findings": [item.get("rule_id") + ":" + item.get("severity")
                                                for item in unknown_findings]},
                })
                ui["candidate_id"] = review_doc.get("candidate_id")
                ui["review_checked"] = {
                    "outcome": "checked", "findings": [item.get("rule_id") for item in vlm_findings],
                }
                ui["review_unknown"] = {
                    "outcome": "unknown",
                    "findings": [item.get("rule_id") for item in unknown_findings],
                }
                screenshot_rel = (f"evals/product-v2/evidence/"
                                  f"v2.5.2-vlm-review-{stamp}.png")
                page.screenshot(path=str(ROOT / screenshot_rel), full_page=True)
                screenshots.append(screenshot_rel)
            finally:
                context.close()
    finally:
        static_server.shutdown()
        server.shutdown()
        server.server_close()
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.5.2 可替换 VLM 复核 Provider 验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright  # noqa: F401, PLC0415  (依赖存在性门)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshots: list[str] = []
    ui: dict = {}
    png = v251.png_bytes(16, 16, (10, 20, 30))

    checks.extend(check_static_guards())
    checks.extend(run_fixture_checks(png))
    checks.extend(run_fake_matrix_checks(png))
    checks.extend(run_endpoint_checks(png))
    checks.extend(run_browser_checks(stamp, screenshots, console_errors, page_errors, ui))

    entry = v251.run_entry(["--check"])
    checks.append({
        "id": "V2.5.2-18",
        "title": "正式入口 --check 全过（含复核路由自检：路由、请求身份、provider 不可用分类）",
        # 自检条目会随批次增加（33 → 38 → …）：断言只看「全过」这一语义，不写死条数。
        "ok": entry["rc"] == 0 and any(
            re.search(r"V2 正式入口自检：\d+/\d+ 通过", line) for line in entry["tail"]),
        "detail": {"rc": entry["rc"], "tail": entry["tail"][-3:]},
    })
    expected_console = [item for item in console_errors if "status of 504" in item]
    unexpected_console = [item for item in console_errors if item not in expected_console]
    checks.append({
        "id": "V2.5.2-19",
        "title": "零意外 console error / page error（唯一允许项：Unknown 路径的 504 资源日志）",
        "ok": not unexpected_console and not page_errors,
        "detail": {"unexpected_console": unexpected_console[:3],
                   "expected_unknown_path_504": expected_console[:3],
                   "page": page_errors[:3]},
    })

    passed = sum(1 for item in checks if item["ok"])
    failed = [item["id"] for item in checks if not item["ok"]]
    observed_at = datetime.now().isoformat(timespec="seconds")
    label = args.label
    txt_path = EVIDENCE_DIR / f"v2.5.2-vlm-review-{stamp}{label}.txt"
    json_path = EVIDENCE_DIR / f"v2.5.2-vlm-review-{stamp}{label}.json"

    lines = [
        "V2.5.2 可替换 VLM 复核 Provider 验证（fake 契约 + 已标样例 + 浏览器闭环）",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        "=" * 76,
    ]
    for item in checks:
        lines.append(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if item.get("detail") is not None:
            lines.append("         " + json.dumps(item["detail"], ensure_ascii=False)[:360])
    lines.extend([
        "-" * 76,
        f"observed_at: {observed_at}",
        f"status: {'passed' if passed == len(checks) else 'failed'}",
        f"contract: {REVIEW_CONTRACT_VERSION}",
        "model_calls: 0 · external_network_calls: 0（fake providers + 本地静态服务器）",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "边界：本套件 0 次真实模型调用；fake provider 只证明契约、归因与工作台闭环，",
        "不证明真实 VLM 的检出质量。真实最小请求由 tools/probe_v2_5_2_review_live.py",
        "单独执行并把请求审计写进证据（计划 §12.2 的预算纪律）。",
        "",
        "CHECKS",
    ])
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
    if failed:
        lines.append("")
        lines.append("FAILED: " + ", ".join(failed))
    text = "\n".join(lines) + "\n"
    txt_path.write_text(text, encoding="utf-8")
    json_path.write_text(json.dumps({
        "suite_id": "v2.5.2-vlm-review-provider",
        "status": "passed" if passed == len(checks) else "failed",
        "observed_at": observed_at,
        "contract": REVIEW_CONTRACT_VERSION,
        "model_calls": 0,
        "external_network_calls": 0,
        "checks": checks,
        "screenshots": screenshots,
        "ui": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(text)
    print("证据文件：")
    print(" - " + txt_path.relative_to(ROOT).as_posix())
    print(" - " + json_path.relative_to(ROOT).as_posix())
    for item in screenshots:
        print(" - " + item)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
