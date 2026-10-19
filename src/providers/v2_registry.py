"""Product V2 provider 注册表的读取与选择（V2.2.3）。

配置权威是 ``config/product-v2/providers.json``（登记在项目上下文 §4.1/§4.2 与依赖登记守卫里）。
本模块只做三件事：读配置、按环境变量选 provider、构造适配器实例。

边界：
  - 不缓存业务状态、不读工作空间、不写文件；一次调用只返回一个 provider 对象。
  - 错误消息里不含密钥；密钥解析统一走 ``v2_credentials.resolve_credentials``：
    默认档受 ``AMZ_V2_DEFAULT_TRIAL`` 约束（缺省 fail-closed），BYOK 只在单次请求内出现。
  - 依赖缺失（例如镜像里没有 langchain）不在这里吞掉：调用方把它变成明确的分类错误。
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SEMANTIC_PROVIDER_HEADER = "X-AMZ-Listing-Provider-Semantic"
IMAGE_PROVIDER_HEADER = "X-AMZ-Listing-Provider-Image"
REVIEW_PROVIDER_HEADER = "X-AMZ-Listing-Provider-Review"
SEMANTIC_KEY_HEADER = "X-AMZ-Listing-Key-Semantic"
IMAGE_KEY_HEADER = "X-AMZ-Listing-Key-Image"
REVIEW_KEY_HEADER = "X-AMZ-Listing-Key-Review"
MAX_BYOK_LENGTH = 512
# 有限用途目录：注册表 role → 客户端 purpose。fake 条目只在显式注入测试接缝里可见，
# 由 provider_choices() 按 active 身份决定是否附带（生产目录永不含 fake）。
ROLE_PURPOSES = {"semantic": "semantic", "image": "image", "review": "review"}

from src.providers.v2_credentials import resolve_credentials

DEFAULT_REGISTRY_PATH = (Path(__file__).resolve().parents[2]
                         / "config" / "product-v2" / "providers.json")
FAKE_SCENARIO_ENV = "AMZ_V2_FAKE_SEMANTIC_SCENARIO"
FAKE_IMAGE_SCENARIO_ENV = "AMZ_V2_FAKE_IMAGE_SCENARIO"
IMAGE_SELECTION_ENV_FALLBACK = "AMZ_V2_IMAGE_PROVIDER"
FAKE_REVIEW_SCENARIO_ENV = "AMZ_V2_FAKE_REVIEW_SCENARIO"
REVIEW_SELECTION_ENV_FALLBACK = "AMZ_V2_REVIEW_PROVIDER"


class ProviderRegistryError(RuntimeError):
    """注册表读不出来、id 不存在，或适配器模块缺失。"""


class ByokHeaderError(ProviderRegistryError):
    """BYOK 请求头非法（空白/超长/控制字符）；调用方归 400 BYOK_HEADER_INVALID，不含密钥原文。"""

def load_registry(path: Path | str | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProviderRegistryError(f"provider 注册表不存在：{target}") from None
    except ValueError as error:
        raise ProviderRegistryError(
            f"provider 注册表不是合法 JSON（{target}）：{type(error).__name__}") from None
    if not isinstance(data, Mapping) or not isinstance(data.get("providers"), list):
        raise ProviderRegistryError("provider 注册表缺少 providers 列表。")
    return dict(data)


def provider_entry(registry: Mapping[str, Any], provider_id: str) -> dict[str, Any]:
    for item in registry.get("providers", []):
        if isinstance(item, Mapping) and item.get("id") == provider_id:
            return dict(item)
    known = [str(item.get("id")) for item in registry.get("providers", [])
             if isinstance(item, Mapping)]
    raise ProviderRegistryError(f"注册表里没有 provider {provider_id!r}；已知：{', '.join(known)}。")


def resolve_provider_id(registry: Mapping[str, Any], *, env: Mapping[str, str] | None = None,
                        requested: str | None = None) -> str:
    if requested:
        return requested
    environment = os.environ if env is None else env
    env_name = registry.get("provider_selection_env") or ""
    chosen = environment.get(env_name) if env_name else None
    if chosen:
        return str(chosen)
    default = registry.get("default_semantic_provider_id")
    if not default:
        raise ProviderRegistryError("注册表没有 default_semantic_provider_id。")
    return str(default)


def create_semantic_provider(*, registry: Mapping[str, Any] | None = None,
                             registry_path: Path | str | None = None,
                             env: Mapping[str, str] | None = None,
                             provider_id: str | None = None,
                             byok_api_key: str | None = None) -> Any:
    """按注册表构造一个语义 provider 实例；构造失败抛 ProviderRegistryError。"""

    environment = os.environ if env is None else env
    data = registry if registry is not None else load_registry(registry_path)
    chosen = resolve_provider_id(data, env=environment, requested=provider_id)
    entry = provider_entry(data, chosen)
    adapter = entry.get("adapter")
    if adapter == "v2_dashscope_semantic":
        try:
            from src.providers.v2_dashscope_semantic import DashScopeSemanticProvider
        except Exception as error:  # 依赖缺失：说清是哪一个模块，不含密钥
            raise ProviderRegistryError(
                f"语义适配器不可用（{type(error).__name__}）：{error}") from None
        model_env = entry.get("model_env") or ""
        model_id = (environment.get(model_env) if model_env else None) or entry.get("model_id")
        decision = resolve_credentials(entry, environment, byok_api_key=byok_api_key)
        return DashScopeSemanticProvider(model_id=model_id or None,
                                         api_key=decision.api_key,
                                         credential_source=decision.source)
    if adapter == "v2_dashscope_vision_semantic":
        try:
            from src.providers.v2_dashscope_vision_semantic import DashScopeVisionSemanticProvider
        except Exception as error:  # 依赖缺失：说清是哪一个模块，不含密钥
            raise ProviderRegistryError(
                f"语义适配器不可用（{type(error).__name__}）：{error}") from None
        model_env = entry.get("model_env") or ""
        model_id = (environment.get(model_env) if model_env else None) or entry.get("model_id")
        decision = resolve_credentials(entry, environment, byok_api_key=byok_api_key)
        return DashScopeVisionSemanticProvider(model_id=model_id or None,
                                              api_key=decision.api_key,
                                              credential_source=decision.source)
    if adapter == "v2_fake_semantic":
        try:
            from src.providers.v2_fake_semantic import FakeSemanticProvider
        except Exception as error:
            raise ProviderRegistryError(
                f"假 provider 不可用（{type(error).__name__}）：{error}") from None
        scenario = environment.get(FAKE_SCENARIO_ENV) or "ok"
        return FakeSemanticProvider(scenario)
    if adapter == "v2_fake_vision_semantic":
        try:
            from src.providers.v2_fake_vision_semantic import FakeVisionSemanticProvider
        except Exception as error:
            raise ProviderRegistryError(
                f"假看图 provider 不可用（{type(error).__name__}）：{error}") from None
        scenario = environment.get(FAKE_SCENARIO_ENV) or "ok"
        return FakeVisionSemanticProvider(scenario)
    raise ProviderRegistryError(f"provider {chosen} 的 adapter 未登记：{adapter!r}。")


def resolve_image_provider_id(registry: Mapping[str, Any], *,
                              env: Mapping[str, str] | None = None,
                              requested: str | None = None) -> str:
    """图像 provider 的选择：显式指定 > 环境变量 > 注册表默认。"""

    if requested:
        return requested
    environment = os.environ if env is None else env
    env_name = registry.get("image_provider_selection_env") or IMAGE_SELECTION_ENV_FALLBACK
    chosen = environment.get(env_name) if env_name else None
    if chosen:
        return str(chosen)
    default = registry.get("default_image_provider_id")
    if not default:
        raise ProviderRegistryError("注册表没有 default_image_provider_id。")
    return str(default)


def create_image_provider(*, registry: Mapping[str, Any] | None = None,
                          registry_path: Path | str | None = None,
                          env: Mapping[str, str] | None = None,
                          provider_id: str | None = None,
                          byok_api_key: str | None = None) -> Any:
    """按注册表构造一个图像 provider；构造过程不联网，失败抛 ProviderRegistryError。"""

    environment = os.environ if env is None else env
    data = registry if registry is not None else load_registry(registry_path)
    chosen = resolve_image_provider_id(data, env=environment, requested=provider_id)
    entry = provider_entry(data, chosen)
    if entry.get("role") not in (None, "image"):
        raise ProviderRegistryError(f"provider {chosen} 的角色不是 image：{entry.get('role')!r}。")
    adapter = entry.get("adapter")
    if adapter == "v2_dashscope_image":
        try:
            from src.providers.v2_dashscope_image import create_default_image_provider
        except Exception as error:  # 依赖缺失：说清是哪一个模块，不含密钥
            raise ProviderRegistryError(
                f"图像适配器不可用（{type(error).__name__}）：{error}") from None
        base_url_env = entry.get("base_url_env") or ""
        return create_default_image_provider(
            environ=environment, byok_api_key=byok_api_key,
            base_url=(environment.get(base_url_env) if base_url_env else None) or None)
    if adapter == "v2_volcengine_image":
        try:
            from src.providers.v2_volcengine_image import (
                create_default_volcengine_image_provider)
        except Exception as error:  # 依赖缺失：说清是哪一个模块，不含密钥
            raise ProviderRegistryError(
                f"图像适配器不可用（{type(error).__name__}）：{error}") from None
        base_url_env = entry.get("base_url_env") or ""
        return create_default_volcengine_image_provider(
            environ=environment, byok_api_key=byok_api_key,
            base_url=(environment.get(base_url_env) if base_url_env else None) or None)
    if adapter == "v2_fake_image":
        try:
            from src.providers.v2_fake_image import FakeImageProvider
        except Exception as error:
            raise ProviderRegistryError(
                f"假图像 provider 不可用（{type(error).__name__}）：{error}") from None
        scenario = environment.get(FAKE_IMAGE_SCENARIO_ENV) or "ok"
        return FakeImageProvider(scenario)
    raise ProviderRegistryError(f"provider {chosen} 的图像 adapter 未登记：{adapter!r}。")


def _normalized_base_url(value: object) -> str:
    """注册表 pricing.base_url 与实例 base_url 的同一归一：去空白与末尾斜杠，不猜默认。"""

    return str(value or "").strip().rstrip("/")


_PRICING_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PRICING_SOURCE_HOSTS = frozenset({"help.aliyun.com", "docs.bailian.console.aliyun.com",
                                   "www.volcengine.com", "docs.volcengine.com"})


def _pricing_source_allowed(value: str) -> bool:
    """官方定价来源只允许 https 无凭据无端口的官方文档主机（与确认单白名单一致）。"""

    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return (parsed.scheme == "https" and host in _PRICING_SOURCE_HOSTS
            and parsed.username is None and parsed.password is None and parsed.port is None)


def resolve_image_pricing(*, entry: Mapping[str, Any], provider: Any) -> dict[str, Any] | None:
    """有效图像 provider 的公开定价；只有注册表条目与当前实例精确一致才返回。

    匹配条件（官方条目）：实例 provider_id/model_id/base_url 与条目 id/model_id/
    pricing.base_url 逐字相等，且实例 request_profile 的 size/n/output_format 与
    pricing 的 1344*1344/1/png 逐字相等。替身条目（test_double）：同样核对实例
    身份与 profile，base_url 不参与匹配（替身没有真实端点）。任一不符、缺
    request_profile、或条目没有 pricing 都返回 None，不猜其他地区/模型的价格。
    返回值是新字典，只含确认单需要的公开白名单字段（不含 base_url 推导细节之
    外的任何秘密；凭据来源不改变它）。
    """

    provider_id = str(getattr(provider, "provider_id", "") or "")
    model_id = str(getattr(provider, "model_id", "") or "")
    if not provider_id or provider_id != str(entry.get("id") or ""):
        return None
    if not model_id or model_id != str(entry.get("model_id") or ""):
        return None
    pricing = entry.get("pricing")
    if not isinstance(pricing, Mapping):
        return None
    if str(pricing.get("provider_id") or "") != provider_id:
        return None
    if str(pricing.get("model_id") or "") != model_id:
        return None
    kind = pricing.get("kind")
    if kind not in ("official", "test_double"):
        return None
    if kind == "test_double":
        if not _entry_is_fake(entry) or not provider_id.startswith("fake-"):
            return None
    elif _normalized_base_url(getattr(provider, "base_url", "")) != _normalized_base_url(
            pricing.get("base_url")) or not _normalized_base_url(pricing.get("base_url")):
        return None
    capabilities = getattr(provider, "capabilities", None)
    try:
        declared = capabilities() if callable(capabilities) else None
    except Exception:  # noqa: BLE001 - 能力查询失败就不报价
        return None
    profile = declared.get("request_profile") if isinstance(declared, Mapping) else None
    if not isinstance(profile, Mapping):
        return None
    if (profile.get("size") != pricing.get("size")
            or profile.get("n") != pricing.get("n")
            or profile.get("output_format") != pricing.get("output_format")):
        return None
    input_fen = pricing.get("input_image_fen")
    output_fen = pricing.get("output_image_fen")
    if (not isinstance(input_fen, int) or isinstance(input_fen, bool) or input_fen < 0
            or not isinstance(output_fen, int) or isinstance(output_fen, bool) or output_fen < 0):
        return None
    if pricing.get("version") != 1 or pricing.get("currency") != "CNY":
        return None
    if kind == "test_double":
        if (input_fen != 0 or output_fen != 0 or pricing.get("verified_on") is not None
                or pricing.get("source_url") is not None or pricing.get("region") != "local-test"):
            return None
    elif (output_fen <= 0 or pricing.get("region") != "cn-beijing"):
        return None
    verified_on = pricing.get("verified_on")
    source_url = pricing.get("source_url")
    if kind == "official":
        if not isinstance(verified_on, str) or not _PRICING_DATE_RE.fullmatch(verified_on):
            return None
        if not isinstance(source_url, str) or not _pricing_source_allowed(source_url):
            return None
    return {
        "version": 1,
        "kind": kind,
        "provider_id": provider_id,
        "model_id": model_id,
        "size": pricing.get("size"),
        "n": pricing.get("n"),
        "output_format": pricing.get("output_format"),
        "currency": "CNY",
        "input_image_fen": input_fen,
        "output_image_fen": output_fen,
        "verified_on": verified_on,
        "source_url": source_url,
        "region": pricing.get("region"),
    }


def resolve_review_provider_id(registry: Mapping[str, Any], *,
                               env: Mapping[str, str] | None = None,
                               requested: str | None = None) -> str:
    """复核 provider 的选择：显式指定 > 环境变量 > 注册表默认。"""

    if requested:
        return requested
    environment = os.environ if env is None else env
    env_name = registry.get("review_provider_selection_env") or REVIEW_SELECTION_ENV_FALLBACK
    chosen = environment.get(env_name) if env_name else None
    if chosen:
        return str(chosen)
    default = registry.get("default_review_provider_id")
    if not default:
        raise ProviderRegistryError("注册表没有 default_review_provider_id。")
    return str(default)


def create_review_provider(*, registry: Mapping[str, Any] | None = None,
                           registry_path: Path | str | None = None,
                           env: Mapping[str, str] | None = None,
                           provider_id: str | None = None,
                           byok_api_key: str | None = None) -> Any:
    """按注册表构造一个复核 provider；构造过程不联网，失败抛 ProviderRegistryError。"""

    environment = os.environ if env is None else env
    data = registry if registry is not None else load_registry(registry_path)
    chosen = resolve_review_provider_id(data, env=environment, requested=provider_id)
    entry = provider_entry(data, chosen)
    if entry.get("role") not in (None, "review"):
        raise ProviderRegistryError(f"provider {chosen} 的角色不是 review：{entry.get('role')!r}。")
    adapter = entry.get("adapter")
    if adapter == "v2_dashscope_review":
        try:
            from src.providers.v2_dashscope_review import DashScopeReviewProvider
        except Exception as error:  # 依赖缺失：说清是哪一个模块，不含密钥
            raise ProviderRegistryError(
                f"复核适配器不可用（{type(error).__name__}）：{error}") from None
        model_env = entry.get("model_env") or ""
        model_id = (environment.get(model_env) if model_env else None) or entry.get("model_id")
        decision = resolve_credentials(entry, environment, byok_api_key=byok_api_key)
        return DashScopeReviewProvider(model_id=model_id or None,
                                       api_key=decision.api_key,
                                       credential_source=decision.source)
    if adapter == "v2_fake_review":
        try:
            from src.providers.v2_fake_review import FakeReviewProvider
        except Exception as error:
            raise ProviderRegistryError(
                f"假复核 provider 不可用（{type(error).__name__}）：{error}") from None
        scenario = environment.get(FAKE_REVIEW_SCENARIO_ENV) or "ok"
        return FakeReviewProvider(scenario)
    raise ProviderRegistryError(f"provider {chosen} 的复核 adapter 未登记：{adapter!r}。")


def create_suite_review_provider(*, registry: Mapping[str, Any] | None = None,
                                 registry_path: Path | str | None = None,
                                 env: Mapping[str, str] | None = None,
                                 provider_id: str | None = None,
                                 byok_api_key: str | None = None) -> Any:
    """整套复核 provider：复用复核 provider 的注册表条目与模型通道，只换适配器类。

    这样一来「选哪个复核模型」只有一个权威（review 条目 + AMZ_V2_REVIEW_PROVIDER），
    不会出现单图与整套各配一个模型而漂移的情况。
    """

    environment = os.environ if env is None else env
    data = registry if registry is not None else load_registry(registry_path)
    chosen = resolve_review_provider_id(data, env=environment, requested=provider_id)
    entry = provider_entry(data, chosen)
    if entry.get("role") not in (None, "review"):
        raise ProviderRegistryError(f"provider {chosen} 的角色不是 review：{entry.get('role')!r}。")
    adapter = entry.get("adapter")
    if adapter == "v2_dashscope_review":
        try:
            from src.providers.v2_dashscope_suite_review import DashScopeSuiteReviewProvider
        except Exception as error:  # 依赖缺失：说清是哪一个模块，不含密钥
            raise ProviderRegistryError(
                f"整套复核适配器不可用（{type(error).__name__}）：{error}") from None
        model_env = entry.get("model_env") or ""
        model_id = (environment.get(model_env) if model_env else None) or entry.get("model_id")
        decision = resolve_credentials(entry, environment, byok_api_key=byok_api_key)
        return DashScopeSuiteReviewProvider(model_id=model_id or None,
                                            api_key=decision.api_key,
                                            credential_source=decision.source)
    if adapter == "v2_fake_review":
        try:
            from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider
        except Exception as error:
            raise ProviderRegistryError(
                f"假整套复核 provider 不可用（{type(error).__name__}）：{error}") from None
        scenario = environment.get(FAKE_REVIEW_SCENARIO_ENV) or "ok"
        return FakeSuiteReviewProvider(scenario)
    raise ProviderRegistryError(f"provider {chosen} 的整套复核 adapter 未登记：{adapter!r}。")


def _header_value(headers: Mapping[str, str] | None, name: str) -> str | None:
    """取请求头并 strip；缺席返回 None（调用方按缺省处理），空白返回 ""（调用方按非法拒绝）。"""

    if headers is None:
        return None
    for key, value in headers.items():
        if str(key).lower() == name.lower():
            return value.strip() if isinstance(value, str) else ""
    return None


def _validate_byok(raw: str | None, *, purpose: str) -> str | None:
    """校验 BYOK 请求头值；空白/超长/控制字符抛 ByokHeaderError（调用方归 400，不含密钥原文）。"""

    if raw is None:
        return None
    if not raw or len(raw) > MAX_BYOK_LENGTH or any(ord(char) < 32 for char in raw):
        raise ByokHeaderError(f"{purpose} 的 BYOK 请求头为空、超长或含控制字符；这次请求没有调用模型。")
    return raw


def _entry_is_fake(entry: Mapping[str, Any]) -> bool:
    capabilities = entry.get("capabilities")
    if isinstance(capabilities, Mapping) and capabilities.get("test_double") is True:
        return True
    return str(entry.get("adapter") or "").startswith("v2_fake_")


def _validate_requested(entry: Mapping[str, Any], *, purpose: str, role: str) -> None:
    """客户端显式 id 必须存在、角色一致；fake id 在生产注册表路径上直接拒绝。"""

    if entry.get("role") not in (None, role):
        raise ProviderRegistryError(
            f"{purpose} 选择的 provider {entry.get('id')!r} 角色不是 {role}：{entry.get('role')!r}。")
    if _entry_is_fake(entry):
        raise ProviderRegistryError(
            f"{purpose} 选择的 provider {entry.get('id')!r} 是测试替身；生产网关不提供。")


def provider_choices(registry: Mapping[str, Any], *,
                     active_ids: set[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    """有限用途目录：直接从注册表派生，不手写第二份模型真相。

    fake 条目只在显式注入测试接缝里可见：active_ids 含某 fake id 时才附带该条；
    生产目录永不含 fake。vision 键只出现在 semantic 选择上。
    """

    active = set(active_ids or ())
    catalog: dict[str, list[dict[str, Any]]] = {"semantic": [], "image": [], "review": []}
    for item in registry.get("providers", []):
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "")
        purpose = ROLE_PURPOSES.get(role)
        if purpose is None:
            continue
        provider_id = str(item.get("id") or "")
        if _entry_is_fake(item) and provider_id not in active:
            continue
        choice: dict[str, Any] = {
            "id": provider_id,
            "label": str(item.get("label") or provider_id),
            "model_id": str(item.get("model_id") or ""),
        }
        if purpose == "semantic":
            capabilities = item.get("capabilities")
            vision = (isinstance(capabilities, Mapping)
                      and capabilities.get("reference_images") is True)
            choice["vision"] = bool(vision)
        catalog[purpose].append(choice)
    for purpose in catalog:
        catalog[purpose].sort(key=lambda item: item["id"])
    return catalog


def _seam_provider_id(instance: Any) -> str | None:
    """读已注入实例的能力声明里的 provider_id；读不到返回 None（不按接缝处理）。"""

    try:
        capabilities = instance.capabilities() if callable(getattr(instance, "capabilities", None)) else None
    except Exception:  # noqa: BLE001 - 能力查询失败就不按接缝处理
        return None
    if isinstance(capabilities, Mapping):
        value = capabilities.get("provider_id")
        if isinstance(value, str) and value:
            return value
    value = getattr(instance, "provider_id", None)
    return value if isinstance(value, str) and value else None


def resolve_effective(*, purpose: str, role: str, provider_header: str, key_header: str,
                      default_resolver: Any, create: Any,
                      registry: Mapping[str, Any] | None = None,
                      registry_path: object = None,
                      env: Mapping[str, str] | None = None,
                      headers: Mapping[str, str] | None = None,
                      factory: Any | None = None,
                      is_default_factory: bool = True) -> tuple[Any, dict[str, Any]]:
    """一次请求的有效 provider + 非秘密 effective 摘要（能力投影与执行共用同一元组）。

     offline 安全（R5.2 接缝）：显式注入的 factory（非默认）造出的实例若其
    capabilities().provider_id == 客户端请求 id，则保留该实例（含注入的 fake
    transport），只把请求级 BYOK 经 apply_credentials 换上；id 不同才走注册表。
    生产默认 factory 不做 fake 覆盖：请求了 fake id 直接 400。
    能力读取与执行走同一解析，不做外部调用、不落盘、不记日志。
    """

    data = registry if registry is not None else load_registry(registry_path)
    environment = os.environ if env is None else env
    requested = _header_value(headers, provider_header)
    if requested == "":
        raise ProviderRegistryError(f"{purpose} 的 provider 请求头为空；这次请求没有调用模型。")
    byok = _validate_byok(_header_value(headers, key_header), purpose=purpose)
    seam = factory is not None and not is_default_factory
    chosen_id: str
    if requested is not None:
        entry = provider_entry(data, requested)
        if _entry_is_fake(entry) and seam:
            # 测试接缝：注入实例身份与请求 id 一致时保留该实例（含注入的 fake
            # transport）；生产默认 factory 落到 _validate_requested 直接 400。
            seam_instance = factory()
            if _seam_provider_id(seam_instance) == str(entry.get("id")):
                if byok is not None:
                    apply = getattr(seam_instance, "apply_credentials", None)
                    if not callable(apply):
                        raise ProviderRegistryError(
                            f"{purpose} 的当前 provider 不支持 BYOK 凭据；这次请求没有调用模型。")
                    apply(api_key=byok)
                return seam_instance, _effective_summary(
                    seam_instance, data, str(entry.get("id")), byok is not None)
        _validate_requested(entry, purpose=purpose, role=role)
        chosen_id = str(entry.get("id"))
    elif seam:
        # 无显式选择 + 显式注入 factory：沿用注入实例（既有自检/验证器不带选择头
        # 直调）；请求级 BYOK 照样经 apply_credentials 换上。
        seam_instance = factory()
        chosen_id = _seam_provider_id(seam_instance) or default_resolver(data, env=environment)
        if byok is not None:
            apply = getattr(seam_instance, "apply_credentials", None)
            if not callable(apply):
                raise ProviderRegistryError(
                    f"{purpose} 的当前 provider 不支持 BYOK 凭据；这次请求没有调用模型。")
            apply(api_key=byok)
        return seam_instance, _effective_summary(seam_instance, data, chosen_id, byok is not None)
    else:
        chosen_id = default_resolver(data, env=environment)
    if seam:
        seam_instance = factory()
        if _seam_provider_id(seam_instance) == chosen_id:
            if byok is not None:
                apply = getattr(seam_instance, "apply_credentials", None)
                if not callable(apply):
                    raise ProviderRegistryError(
                        f"{purpose} 的当前 provider 不支持 BYOK 凭据；这次请求没有调用模型。")
                apply(api_key=byok)
            return seam_instance, _effective_summary(seam_instance, data, chosen_id, byok is not None)
    provider = create(registry=data, env=environment, provider_id=chosen_id, byok_api_key=byok)
    return provider, _effective_summary(provider, data, chosen_id, byok is not None)


def _effective_summary(provider: Any, registry: Mapping[str, Any], chosen_id: str,
                       byok_present: bool) -> dict[str, Any]:
    """非秘密 effective 摘要：身份/协议/凭据来源/配置态/能力版本；绝不含密钥。"""

    try:
        entry = provider_entry(registry, chosen_id)
    except ProviderRegistryError:
        entry = {}
    capabilities = {}
    method = getattr(provider, "capabilities", None)
    if callable(method):
        try:
            result = method()
        except Exception:  # noqa: BLE001 - 摘要失败不掩盖 provider 本体
            result = None
        if isinstance(result, Mapping):
            capabilities = dict(result)
    source = getattr(provider, "credential_source", None)
    if byok_present:
        source = "byok"
    configured = capabilities.get("configured")
    if configured is None:
        configured = bool(getattr(provider, "configured", True))
    return {
        "provider_id": getattr(provider, "provider_id", chosen_id),
        "model_id": getattr(provider, "model_id", entry.get("model_id")),
        "protocol": capabilities.get("semantic_contract") or capabilities.get("contract")
        or capabilities.get("review_contract") or capabilities.get("suite_review_contract"),
        "capability_version": capabilities.get("capability_version"),
        "credential_source": source,
        "configured": bool(configured),
    }
