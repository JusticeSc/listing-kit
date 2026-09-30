"""Product V2 provider 注册表的读取与选择（V2.2.3）。

配置权威是 ``config/product-v2/providers.json``（登记在项目上下文 §4.1/§4.2 与依赖登记守卫里）。
本模块只做三件事：读配置、按环境变量选 provider、构造适配器实例。

边界：
  - 不缓存业务状态、不读工作空间、不写文件；一次调用只返回一个 provider 对象。
  - 错误消息里不含密钥；密钥只由适配器从环境变量读取（DASHSCOPE_API_KEY）。
  - 依赖缺失（例如镜像里没有 langchain）不在这里吞掉：调用方把它变成明确的分类错误。
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY_PATH = (Path(__file__).resolve().parents[2]
                         / "config" / "product-v2" / "providers.json")
FAKE_SCENARIO_ENV = "AMZ_V2_FAKE_SEMANTIC_SCENARIO"
FAKE_IMAGE_SCENARIO_ENV = "AMZ_V2_FAKE_IMAGE_SCENARIO"
IMAGE_SELECTION_ENV_FALLBACK = "AMZ_V2_IMAGE_PROVIDER"
FAKE_REVIEW_SCENARIO_ENV = "AMZ_V2_FAKE_REVIEW_SCENARIO"
REVIEW_SELECTION_ENV_FALLBACK = "AMZ_V2_REVIEW_PROVIDER"


class ProviderRegistryError(RuntimeError):
    """注册表读不出来、id 不存在，或适配器模块缺失。"""


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
                             provider_id: str | None = None) -> Any:
    """按注册表构造一个语义 provider 实例；构造失败抛 ProviderRegistryError。"""

    environment = os.environ if env is None else env
    data = dict(registry) if registry is not None else load_registry(registry_path)
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
        return DashScopeSemanticProvider(model_id=model_id or None)
    if adapter == "v2_fake_semantic":
        try:
            from src.providers.v2_fake_semantic import FakeSemanticProvider
        except Exception as error:
            raise ProviderRegistryError(
                f"假 provider 不可用（{type(error).__name__}）：{error}") from None
        scenario = environment.get(FAKE_SCENARIO_ENV) or "ok"
        return FakeSemanticProvider(scenario)
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
                          provider_id: str | None = None) -> Any:
    """按注册表构造一个图像 provider；构造过程不联网，失败抛 ProviderRegistryError。"""

    environment = os.environ if env is None else env
    data = dict(registry) if registry is not None else load_registry(registry_path)
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
            environ=environment,
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
                           provider_id: str | None = None) -> Any:
    """按注册表构造一个复核 provider；构造过程不联网，失败抛 ProviderRegistryError。"""

    environment = os.environ if env is None else env
    data = dict(registry) if registry is not None else load_registry(registry_path)
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
        return DashScopeReviewProvider(model_id=model_id or None)
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
                                 provider_id: str | None = None) -> Any:
    """整套复核 provider：复用复核 provider 的注册表条目与模型通道，只换适配器类。

    这样一来「选哪个复核模型」只有一个权威（review 条目 + AMZ_V2_REVIEW_PROVIDER），
    不会出现单图与整套各配一个模型而漂移的情况。
    """

    environment = os.environ if env is None else env
    data = dict(registry) if registry is not None else load_registry(registry_path)
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
        return DashScopeSuiteReviewProvider(model_id=model_id or None)
    if adapter == "v2_fake_review":
        try:
            from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider
        except Exception as error:
            raise ProviderRegistryError(
                f"假整套复核 provider 不可用（{type(error).__name__}）：{error}") from None
        scenario = environment.get(FAKE_REVIEW_SCENARIO_ENV) or "ok"
        return FakeSuiteReviewProvider(scenario)
    raise ProviderRegistryError(f"provider {chosen} 的整套复核 adapter 未登记：{adapter!r}。")
