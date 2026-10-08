#!/usr/bin/env python
"""V2.2.2 证据：DeepSeek（百炼）语义 Provider 的契约、装配与错误分类。

离线检查（默认执行，不联网）：
  J1 跨语言合同：Python CORE_SLOT_REGISTRY 与 app/product_v2/domain/slots.js 完全一致。
  J2 输入合同：合法投影通过；越界输入全部 input_rejected / fatal，且不回显输入正文。
  J3 装配与真实请求体：真实 ChatOpenAI + httpx MockTransport 回放，断言 json_mode、
     max_tokens 走 extra_body、max_retries=0，且一次 analyze 只发一次请求。
  J4 禁止的静默清洗：缺 evidence / 非对象槽位 / 模型自称 confirmed / 超上限全部整包拒绝。
  J5 截断、内容策略拒绝与空可见文本（reasoning 耗尽）的分类。
  J6 SDK / 传输异常映射矩阵。
  J7 错误消息与 details 不回显密钥。
  J8 fake provider 全场景分类正确，且每次 analyze 只调用一次（无隐藏重提）。
  J9 归一化输出形状 + assert_proposal_legal 反向探针。
真实调用（--live，按计划 §12.2 计费纪律，只做 Q4 允许的 2 次）：
  L1 真实正例 1 次；L2 无效密钥负例 1 次。

运行：
  uv run --locked python tools/verify_v2_2_2_semantic_provider.py
  uv run --locked python tools/verify_v2_2_2_semantic_provider.py --live
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
from console import enable_utf8  # noqa: E402
enable_utf8()

from src.providers import v2_semantic as contract  # noqa: E402
from src.providers.v2_dashscope_semantic import (  # noqa: E402
    BASE_URL_ENV,
    DEFAULT_API_KEY_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL_ID,
    DEFAULT_TIMEOUT_SECONDS,
    DashScopeSemanticProvider,
    MAX_TOKENS_ENV,
    MODEL_ENV,
    TIMEOUT_ENV,
)
from src.providers.v2_fake_semantic import FAKE_SCENARIOS, FakeSemanticProvider  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
SLOTS_JS = ROOT / "app" / "product_v2" / "domain" / "slots.js"
PROVIDERS_JSON = ROOT / "config" / "product-v2" / "providers.json"
VERIFY_API_KEY = "sk-verify-only-0000"
REFERENCE = {"sha256": "a" * 64, "media_type": "image/png", "role": "primary"}


def base_input(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "product_name": "不锈钢真空保温杯 500ml",
        "description": "316 不锈钢内胆，24 小时保温，附赠杯刷。",
        "selling_points": ["24 小时保温", "316 不锈钢内胆"],
        "focus": "突出保温能力",
        "references": [dict(REFERENCE)],
        "platform": "amazon_us",
        "max_slots": 6,
    }
    payload.update(overrides)
    return payload


def model_slot(**overrides: Any) -> dict[str, Any]:
    slot: dict[str, Any] = {
        "slot_id": "key_material",
        "label": "主要材质",
        "authority": "core_fixed",
        "value_type": "text",
        "value": "316 不锈钢",
        "confidence": 0.8,
        "evidence": [{"kind": "user", "ref": "product_input", "note": "来自商品介绍"}],
    }
    slot.update(overrides)
    return slot


def model_proposal(slots: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"summary": "保温杯资料理解", "questions": [],
                               "slots": slots if slots is not None else [model_slot()]}
    payload.update(overrides)
    return payload


def expect_failure(call: Any, *, codes: tuple[str, ...] | None = None) -> dict[str, Any]:
    """执行 call，要求它抛 SemanticFailure；返回结构化结果，不做清理。"""

    try:
        call()
    except contract.SemanticFailure as failure:
        ok = codes is None or failure.code in codes
        return {"ok": ok, "codes": list(codes or ()), "failure": failure.to_dict()}
    except Exception as error:  # noqa: BLE001 - 未分类异常也必须判负并留证
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}
    return {"ok": False, "error": "没有抛出分类失败"}


JS_REGISTRY_ENTRY = re.compile(
    r'Object\.freeze\(\{\s*slot_id:\s*"([^"]+)",\s*label:\s*"([^"]+)",\s*'
    r'value_type:\s*"([^"]+)",\s*critical:\s*(true|false)\s*\}\)')


def read_js_registry() -> dict[str, tuple[str, str, bool]]:
    text = SLOTS_JS.read_text(encoding="utf-8")
    start = text.index("export const CORE_SLOT_REGISTRY")
    end = text.index("]);", start)
    entries: dict[str, tuple[str, str, bool]] = {}
    for slot_id, label, value_type, critical in JS_REGISTRY_ENTRY.findall(text[start:end]):
        entries[slot_id] = (label, value_type, critical == "true")
    return entries


def python_registry() -> dict[str, tuple[str, str, bool]]:
    return {slot_id: (label, value_type, bool(critical))
            for slot_id, (label, value_type, critical) in contract.CORE_SLOT_REGISTRY.items()}


class ReplayTransport:
    """真实 ChatOpenAI + httpx.MockTransport：走完整 SDK 路径，但不联网。

    它回放的是「真实请求体 + 真实响应解析」，所以能证明装配参数（json_mode、
    extra_body.max_tokens、max_retries=0）与解析/拒绝行为，而不是只证明我们的想象。
    httpx 是 langchain-openai→openai 的锁定传递依赖（uv.lock）；缺失时本入口判 FAIL。
    """

    def __init__(self) -> None:
        import httpx

        self.httpx = httpx
        self.requests: list[dict[str, Any]] = []
        self.canned: dict[str, Any] = {"content": json.dumps(model_proposal(), ensure_ascii=False),
                                       "finish_reason": "stop"}
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: Any) -> Any:
        self.requests.append(json.loads(request.content.decode("utf-8")))
        usage = self.canned.get("usage") or {"prompt_tokens": 120, "completion_tokens": 180,
                                             "total_tokens": 300}
        body = {
            "id": "rid-verify-1",
            "object": "chat.completion",
            "created": 0,
            "model": DEFAULT_MODEL_ID,
            "choices": [{"index": 0,
                         "finish_reason": self.canned.get("finish_reason") or "stop",
                         "message": {"role": "assistant",
                                     "content": self.canned.get("content") or ""}}],
            "usage": usage,
        }
        return self.httpx.Response(200, json=body, headers={"x-request-id": "rid-verify-1"})

    def provider(self, *, max_tokens: int | None = None) -> DashScopeSemanticProvider:
        def factory() -> Any:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=DEFAULT_MODEL_ID, base_url=DEFAULT_BASE_URL,
                              api_key=VERIFY_API_KEY, timeout=60, max_retries=0,
                              http_client=self.client)

        kwargs: dict[str, Any] = {"api_key": VERIFY_API_KEY, "llm_factory": factory}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return DashScopeSemanticProvider(**kwargs)

    def analyze(self, provider: DashScopeSemanticProvider,
                payload: dict[str, Any] | None = None) -> contract.SemanticProposal:
        return provider.analyze(contract.parse_request(payload or base_input()))


# ------------------------------------------------------------------ 离线检查

def check_registry(check: Any) -> None:
    js = read_js_registry()
    py = python_registry()
    diff = sorted(set(py.items()) ^ set(js.items()))
    check("V2.2.2-01", "跨语言核心槽位注册表一致（8 项：slot_id/label/value_type/critical）",
          len(py) == 8 and len(js) == 8 and py == js,
          {"python": len(py), "js": len(js), "diff": diff[:4]})


def check_request_contract(check: Any) -> None:
    marker = "MARKER" * 400
    cases = [
        ("空商品名", {"product_name": ""}),
        ("纯空白商品名", {"product_name": "   "}),
        ("没有参考图", {"references": []}),
        ("参考图超过上限", {"references": [dict(REFERENCE) for _ in range(21)]}),
        ("参考图角色不在词表", {"references": [dict(REFERENCE, role="主图")]}),
        ("介绍超过长度上限", {"description": marker}),
        ("max_slots 越界", {"max_slots": 0}),
    ]
    results = []
    ok = True
    for title, overrides in cases:
        payload = base_input(**overrides)
        outcome = expect_failure(lambda item=payload: contract.parse_request(item),
                                 codes=("INPUT_INVALID",))
        failure = outcome.get("failure") or {}
        blob = json.dumps(failure, ensure_ascii=False)
        good = (outcome["ok"] and failure.get("family") == "input_rejected"
                and failure.get("retry_policy") == "fatal"
                and bool(failure.get("details", {}).get("problems"))
                and "MARKER" not in blob)
        ok = ok and good
        results.append({"case": title, "ok": good, "failure": failure})
    valid = contract.parse_request(base_input())
    ok = ok and valid.max_slots == 6 and len(valid.references) == 1
    check("V2.2.2-02", "输入合同：合法投影通过；7 类越界全部 input_rejected / fatal 且不回显正文",
          ok, {"valid_slots": valid.max_slots, "cases": results})


def check_assembly(check: Any) -> None:
    transport = ReplayTransport()
    provider = transport.provider()
    proposal = transport.analyze(provider)
    body = transport.requests[0] if transport.requests else {}
    messages = body.get("messages") or []
    system_text = messages[0].get("content", "") if messages and isinstance(messages[0], dict) else ""
    llm = provider.build_llm()
    facts = list(proposal.slots)
    payload_keys = sorted(key for key in body if key != "messages")
    ok = (
        len(transport.requests) == 1
        and body.get("model") == DEFAULT_MODEL_ID
        and body.get("response_format") == {"type": "json_object"}
        and body.get("max_tokens") == DEFAULT_MAX_TOKENS
        and "max_completion_tokens" not in body
        and "JSON" in system_text and "slots" in system_text and "slot_id" in system_text
        and int(getattr(llm, "max_retries", -1)) == 0
        and float(getattr(llm, "request_timeout", 0)) == 60.0
        and getattr(llm, "openai_api_base", None) == DEFAULT_BASE_URL
        and len(facts) == 1 and facts[0]["slot_id"] == "key_material"
        and proposal.request_id == "rid-verify-1"
        and proposal.usage.get("completion_tokens") == 180
    )
    check("V2.2.2-03", "装配与真实请求体：json_mode + extra_body.max_tokens + max_retries=0，单次调用",
          ok, {"payload_keys": payload_keys, "requests": len(transport.requests),
               "max_tokens": body.get("max_tokens"),
               "max_completion_tokens": body.get("max_completion_tokens"),
               "response_format": body.get("response_format"),
               "system_has_schema": "slot_id" in system_text,
               "request_id": proposal.request_id, "usage": dict(proposal.usage),
               "slots": [slot["slot_id"] for slot in facts]})


def check_no_silent_cleansing(check: Any) -> None:
    cases = [
        ("缺 evidence（系统不代写）",
         model_proposal(slots=[dict(model_slot(), evidence=[])]), "evidence"),
        ("槽位不是对象（不丢弃）", {"summary": "x", "questions": [], "slots": [1]}, "slots"),
        ("模型把 status 标成 confirmed",
         model_proposal(slots=[dict(model_slot(), status="confirmed")]), "status"),
        ("超过本次 max_slots（不截断）",
         model_proposal(slots=[dict(model_slot()) for _ in range(7)]), None),
    ]
    results = []
    ok = True
    for title, payload, keyword in cases:
        transport = ReplayTransport()
        transport.canned["content"] = json.dumps(payload, ensure_ascii=False)
        provider = transport.provider()
        outcome = expect_failure(lambda item=provider: item.analyze(contract.parse_request(base_input())),
                                 codes=("INVALID_RESPONSE",))
        failure = outcome.get("failure") or {}
        details = failure.get("details") or {}
        over_limit = "max_slots" in title
        good = outcome["ok"]
        if over_limit:
            good = good and details.get("count") == 7 and details.get("max_slots") == 6
        else:
            problems = details.get("problems") or []
            blob = json.dumps(problems, ensure_ascii=False)
            good = good and bool(problems) and keyword in blob
        ok = ok and good
        results.append({"case": title, "ok": good, "failure": failure})
    check("V2.2.2-04", "禁止的静默清洗：缺证据 / 非对象槽位 / 模型自称 confirmed / 超上限全部整包拒绝",
          ok, results)


def check_truncation_refusal_empty(check: Any) -> None:
    cases = [
        ("输出被 length 截断",
         {"content": "{\"summary\": \"x\", \"slots\": [{\"slot_id\"", "finish_reason": "length"},
         "PROVIDER_OUTPUT_TRUNCATED", "requires_review"),
        ("内容策略拒绝", {"content": "", "finish_reason": "content_filter"},
         "PROVIDER_REFUSED", "fatal"),
        ("可见文本为空（reasoning 耗尽）",
         {"content": "", "finish_reason": "stop",
          "usage": {"prompt_tokens": 120, "completion_tokens": 64, "total_tokens": 184}},
         "INVALID_RESPONSE", "retryable"),
    ]
    results = []
    ok = True
    for title, canned, code, retry in cases:
        transport = ReplayTransport()
        transport.canned.update(canned)
        provider = transport.provider()
        outcome = expect_failure(lambda item=provider: item.analyze(contract.parse_request(base_input())),
                                 codes=(code,))
        failure = outcome.get("failure") or {}
        good = outcome["ok"] and failure.get("retry_policy") == retry
        if "空" in title:
            details = failure.get("details") or {}
            good = good and details.get("max_tokens") == DEFAULT_MAX_TOKENS and "reasoning" in failure.get("message", "")
        ok = ok and good
        results.append({"case": title, "ok": good, "failure": failure})
    check("V2.2.2-05", "截断 / 内容策略拒绝 / 空可见文本的归口与重试策略正确", ok, results)


def openai_error_cases() -> list[tuple[str, BaseException, str, str, str]]:
    import httpx
    import openai

    request = httpx.Request("POST", DEFAULT_BASE_URL + "/chat/completions")

    def status_error(cls: Any, status: int, message: str, code: str | None = None) -> Any:
        body: dict[str, Any] = {"error": {"message": message}}
        if code:
            body["error"]["code"] = code
        return cls(message, response=httpx.Response(status, request=request, json=body), body=body)

    completion = openai.types.chat.ChatCompletion.model_construct(
        id="x", choices=[], created=0, model="m", object="chat.completion")
    return [
        ("401 鉴权失败", status_error(openai.AuthenticationError, 401, "invalid api key sk-abc", "invalid_api_key"),
         "PROVIDER_AUTH_FAILED", "provider_failed", "fatal"),
        ("403 无权限", status_error(openai.PermissionDeniedError, 403, "no permission"),
         "PROVIDER_AUTH_FAILED", "provider_failed", "fatal"),
        ("429 限流", status_error(openai.RateLimitError, 429, "rate limited"),
         "PROVIDER_RATE_LIMITED", "provider_failed", "retryable"),
        ("400 请求被拒", status_error(openai.BadRequestError, 400, "bad request"),
         "INPUT_REJECTED", "input_rejected", "fatal"),
        ("400 账户欠费（Arrearage）",
         status_error(openai.BadRequestError, 400, "account in bad standing", "Arrearage"),
         "UPSTREAM_ACCOUNT_ARREARS", "provider_failed", "retryable"),
        ("422 请求被拒", status_error(openai.UnprocessableEntityError, 422, "unprocessable"),
         "INPUT_REJECTED", "input_rejected", "fatal"),
        ("500 服务错误", status_error(openai.InternalServerError, 500, "server error"),
         "PROVIDER_HTTP_ERROR", "provider_failed", "retryable"),
        ("超时（无法确认是否送达）", openai.APITimeoutError(request=request),
         "PROVIDER_TIMEOUT", "provider_unknown", "requires_review"),
        ("连接失败", openai.APIConnectionError(request=request),
         "PROVIDER_UNREACHABLE", "provider_failed", "retryable"),
        ("内容策略拒绝", openai.ContentFilterFinishReasonError(),
         "PROVIDER_REFUSED", "provider_failed", "fatal"),
        ("输出截断", openai.LengthFinishReasonError(completion=completion),
         "PROVIDER_OUTPUT_TRUNCATED", "provider_failed", "requires_review"),
        ("未分类异常", RuntimeError("boom"), "INTERNAL_ERROR", "internal", "requires_review"),
    ]


def check_exception_mapping(check: Any) -> None:
    provider = DashScopeSemanticProvider(api_key=VERIFY_API_KEY)
    results = []
    ok = True
    for title, error, code, family, retry in openai_error_cases():
        failure = provider._map_exception(error)
        good = (failure.code == code and failure.family == family
                and failure.retry_policy == retry)
        ok = ok and good
        results.append({"case": title, "ok": good, "code": failure.code,
                        "family": failure.family, "retry_policy": failure.retry_policy,
                        "http_status": failure.http_status})
    check("V2.2.2-06", "SDK / 传输异常映射矩阵（12 类）符合计划 §9.1 归口表", ok, results)


def check_redaction(check: Any) -> None:
    import httpx
    import openai

    key = "sk-secret-key-1234567890"
    leaked = "sk-leaked0001"
    message = f"Incorrect API key provided: {key}. identifier {leaked}"
    request = httpx.Request("POST", DEFAULT_BASE_URL + "/chat/completions")
    body = {"error": {"message": message, "code": "invalid_api_key"}}
    provider = DashScopeSemanticProvider(api_key=key)
    errors = [
        openai.InternalServerError(message, response=httpx.Response(500, request=request, json=body), body=body),
        openai.AuthenticationError(message, response=httpx.Response(401, request=request, json=body), body=body),
    ]
    blobs = [json.dumps(provider._map_exception(error).to_dict(), ensure_ascii=False) for error in errors]
    capabilities = json.dumps(provider.capabilities(), ensure_ascii=False)
    ok = (all(key not in blob and leaked not in blob for blob in blobs)
          and key not in capabilities and "sk-***" in blobs[0])
    check("V2.2.2-07", "错误消息与 capabilities 不回显密钥（按 *** 遮蔽）", ok,
          {"blobs": blobs, "capabilities": capabilities})


def check_fake_provider(check: Any) -> None:
    request = contract.parse_request(base_input())
    provider = FakeSemanticProvider()
    proposals = {"ok", "low_confidence", "conflict"}
    expected = {
        "refusal": ("PROVIDER_REFUSED", "fatal"),
        "invalid_json": ("INVALID_RESPONSE", "retryable"),
        "output_truncated": ("PROVIDER_OUTPUT_TRUNCATED", "requires_review"),
        "empty_output": ("INVALID_RESPONSE", "retryable"),
        "timeout_after_send": ("PROVIDER_TIMEOUT", "requires_review"),
        "timeout_before_send": ("PROVIDER_TIMEOUT", "retryable"),
        "unreachable": ("PROVIDER_UNREACHABLE", "retryable"),
        "rate_limited": ("PROVIDER_RATE_LIMITED", "retryable"),
        "http_error": ("PROVIDER_HTTP_ERROR", "retryable"),
        "auth_failed": ("PROVIDER_AUTH_FAILED", "fatal"),
        "internal_error": ("INTERNAL_ERROR", "requires_review"),
    }
    results = []
    ok = True
    for scenario in FAKE_SCENARIOS:
        before = len(provider.calls)
        outcome = ""
        good = False
        try:
            proposal = provider.analyze(request, scenario=scenario)
            if scenario in proposals:
                good = all(slot["status"] == "proposed" and slot["source"] == "model_inference"
                           for slot in proposal.slots)
                outcome = "proposal:" + str(len(proposal.slots))
            elif scenario == "schema_violation":
                rejected = expect_failure(
                    lambda: contract.assert_proposal_legal(proposal.slots, max_slots=request.max_slots),
                    codes=("INVALID_RESPONSE",))
                good = rejected["ok"]
                outcome = "caller-rejected" if rejected["ok"] else "claims-legal"
            else:
                outcome = "unexpected proposal"
        except contract.SemanticFailure as failure:
            want = expected.get(scenario)
            good = want is not None and failure.code == want[0] and failure.retry_policy == want[1]
            outcome = f"{failure.code}/{failure.retry_policy}"
        good = good and len(provider.calls) == before + 1
        ok = ok and good
        results.append({"scenario": scenario, "ok": good, "outcome": outcome})
    check("V2.2.2-08",
          "fake provider 全部场景分类正确，且每次 analyze 只调用一次（无隐藏重提，UNKNOWN 不自动重提）",
          ok, results)


def check_normalization(check: Any) -> None:
    transport = ReplayTransport()
    provider = transport.provider()
    proposal = transport.analyze(provider)
    fact = dict(proposal.slots[0])
    blob = proposal.to_dict()
    ok = (
        fact["schema_version"] == contract.FACT_SLOT_SCHEMA_VERSION
        and fact["source"] == "model_inference"
        and fact["status"] == "proposed"
        and fact["critical"] is False
        and fact["model_id"] == DEFAULT_MODEL_ID
        and fact["confidence"] == 0.8
        and fact["evidence"] == model_slot()["evidence"]
        and blob["semantic_contract"] == contract.SEMANTIC_CONTRACT_VERSION
        and blob["meta"]["provider_id"] == "dashscope-semantic"
        and blob["meta"]["attempts"] == 1
        and blob["questions"] == []
    )
    confirmed = dict(fact, status="confirmed")
    reverse = expect_failure(lambda: contract.assert_proposal_legal([confirmed], max_slots=6),
                             codes=("INVALID_RESPONSE",))
    check("V2.2.2-09", "归一化输出形状正确；反向探针：模型自称 confirmed 被消费侧拒绝",
          ok and reverse["ok"], {"fact": fact, "meta": blob["meta"], "reverse": reverse})


# ------------------------------------------------------------- 真实调用（--live）

def check_provider_registry(check: Any) -> None:
    """config/product-v2/providers.json 必须与代码一致：一处漂移即判负。"""

    registry = json.loads(PROVIDERS_JSON.read_text(encoding="utf-8"))
    providers = {item["id"]: item for item in registry.get("providers", [])}
    real = providers.get(DashScopeSemanticProvider.provider_id, {})
    fake = providers.get(FakeSemanticProvider.provider_id, {})
    capabilities = real.get("capabilities", {})
    observed = {
        "default": registry.get("default_semantic_provider_id"),
        "model_id": real.get("model_id"),
        "adapter": real.get("adapter"),
        "api_key_env": real.get("api_key_env"),
        "model_env": real.get("model_env"),
        "base_url_env": real.get("base_url_env"),
        "timeout_env": real.get("timeout_env"),
        "max_tokens_env": real.get("max_tokens_env"),
        "max_attempts": real.get("max_attempts"),
        "structured_output": capabilities.get("structured_output"),
        "stateless": capabilities.get("stateless"),
        "test_double": capabilities.get("test_double"),
        "fake_adapter": fake.get("adapter"),
        "fake_test_double": (fake.get("capabilities") or {}).get("test_double"),
        "families": (registry.get("error_contract") or {}).get("families"),
        "retry_policies": (registry.get("error_contract") or {}).get("retry_policies"),
    }
    ok = (
        registry.get("default_semantic_provider_id") == DashScopeSemanticProvider.provider_id
        and real.get("model_id") == DEFAULT_MODEL_ID
        and real.get("adapter") == "v2_dashscope_semantic"
        and real.get("api_key_env") == DEFAULT_API_KEY_ENV
        and real.get("model_env") == MODEL_ENV
        and real.get("base_url_env") == BASE_URL_ENV
        and real.get("timeout_env") == TIMEOUT_ENV
        and real.get("max_tokens_env") == MAX_TOKENS_ENV
        and real.get("max_attempts") == 1
        and capabilities.get("structured_output") == "json_mode"
        and capabilities.get("stateless") is True
        and capabilities.get("test_double") is False
        and fake.get("adapter") == "v2_fake_semantic"
        and (fake.get("capabilities") or {}).get("test_double") is True
        and list(contract.ERROR_FAMILIES) == (registry.get("error_contract") or {}).get("families")
        and list(contract.RETRY_POLICIES) == (registry.get("error_contract") or {}).get("retry_policies")
    )
    check("V2.2.2-10", "provider 注册表与代码一致（默认 provider、模型、环境变量、归口、test_double）",
          ok, {"observed": observed, "timeout_default": DEFAULT_TIMEOUT_SECONDS})

def check_live_positive(check: Any) -> None:
    provider = DashScopeSemanticProvider()
    if not provider.api_key:
        check("V2.2.2-L1", "真实正例：1 次调用返回合法提案", False,
              {"error": "缺少 DASHSCOPE_API_KEY，未发起真实调用"})
        return
    try:
        proposal = provider.analyze(contract.parse_request(base_input(max_slots=6)))
    except contract.SemanticFailure as failure:
        check("V2.2.2-L1", "真实正例：1 次调用返回合法提案", False, failure.to_dict())
        return
    ok = (bool(proposal.slots)
          and all(slot["status"] == "proposed" and slot["source"] == "model_inference"
                  and slot["evidence"] for slot in proposal.slots)
          and proposal.provider_id == "dashscope-semantic"
          and proposal.model_id == provider.model_id)
    check("V2.2.2-L1", "真实正例：1 次调用返回合法提案（全 proposed、带证据与置信度）", ok,
          {"slots": [{"slot_id": slot["slot_id"], "value_type": slot["value_type"],
                      "confidence": slot["confidence"], "evidence": len(slot["evidence"]),
                      "value": str(slot["value"])[:60]} for slot in proposal.slots],
           "summary": proposal.summary, "questions": list(proposal.questions),
           "usage": dict(proposal.usage), "latency_ms": proposal.latency_ms,
           "request_id": proposal.request_id})


def check_live_negative(check: Any) -> None:
    provider = DashScopeSemanticProvider(api_key="sk-invalid-verification-key-000000")
    outcome = expect_failure(
        lambda: provider.analyze(contract.parse_request(base_input())),
        codes=("PROVIDER_AUTH_FAILED",))
    failure = outcome.get("failure") or {}
    ok = (outcome["ok"] and failure.get("family") == "provider_failed"
          and failure.get("retry_policy") == "fatal")
    check("V2.2.2-L2", "真实负例：无效密钥被分类为 PROVIDER_AUTH_FAILED / fatal（不重试）",
          ok, failure or outcome)


# ------------------------------------------------------------------------ 入口

def main() -> int:
    parser = argparse.ArgumentParser(description="V2.2.2 语义 Provider 契约、装配与错误分类验证")
    parser.add_argument("--label", default="", help="证据文件名后缀")
    parser.add_argument("--live", action="store_true",
                        help="允许 Q4 的 2 次真实调用：正例 1 次 + 无效密钥 401 负例 1 次")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    print("=" * 72)
    print("V2.2.2 语义 Provider 契约、装配与错误分类验证")
    print("=" * 72)

    def check(check_id: str, title: str, ok: bool, detail: object = None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {check_id} {title}")
        if not ok:
            print("       " + json.dumps(detail, ensure_ascii=False)[:800])

    check_registry(check)
    check_request_contract(check)
    check_assembly(check)
    check_no_silent_cleansing(check)
    check_truncation_refusal_empty(check)
    check_exception_mapping(check)
    check_redaction(check)
    check_fake_provider(check)
    check_normalization(check)
    check_provider_registry(check)
    if args.live:
        check_live_positive(check)
        check_live_negative(check)

    failed = [item for item in checks if not item["ok"]]
    status = "passed" if not failed else "failed"
    finished_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    boundary = (
        "证明语义 Provider 的离线契约与装配：跨语言核心注册表一致、输入越界分类（input_rejected/fatal）、"
        "json_mode 与 extra_body.max_tokens 与 max_retries=0 的真实请求体、三条静默清洗负例"
        "（缺证据 / 非对象槽位 / 超上限不截断）、截断与内容策略拒绝与空可见文本的归口、SDK 异常映射矩阵、"
        "密钥遮蔽、fake 全场景与无隐藏重提、归一化形状与消费侧反向探针。--live 只证明 1 次真实正例与 "
        "1 次无效密钥负例；不证明模型输出质量、界面投影、套图规划、图片生成与交付闭环。"
    )
    report = {
        "task": "V2.2.2",
        "suite_id": "v2.2.2-semantic-provider",
        "status": status,
        "finished_at": finished_at,
        "live_requested": bool(args.live),
        "checks": checks,
        "boundary": boundary,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    label = f"-{args.label}" if args.label else ""
    json_path = EVIDENCE_DIR / f"v2.2.2-semantic-provider-{stamp}{label}.json"
    txt_path = EVIDENCE_DIR / f"v2.2.2-semantic-provider-{stamp}{label}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "amz-listing-kit Product V2 V2.2.2 semantic provider (deepseek-v4.1-flash)",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        f"observed_at: {finished_at}",
        f"status: {status}",
        f"live_requested: {bool(args.live)}",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "CHECKS",
    ]
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if not item["ok"]:
            lines.append("  detail: " + json.dumps(item["detail"], ensure_ascii=False)[:800])
    lines += ["", "BOUNDARY", boundary]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("-" * 72)
    print(f"证据：{txt_path.relative_to(ROOT).as_posix()}")
    print(f"结果：{len(checks) - len(failed)}/{len(checks)} 通过；{'全过' if status == 'passed' else '有失败'}"
          f"（退出码 {0 if status == 'passed' else 1}）")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
