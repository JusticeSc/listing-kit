#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""凭据解析与默认档开关：把「这次调用用谁的密钥」归到一处（V2.R4.3）。

来源结构（SEL-014/SEL-015）：
  - 注册表条目给出 ``api_key_env``（部署在谁服务器上的默认档密钥）；
  - 环境变量提供默认档密钥的值（不落到任何证据、日志或排查报告里）；
  - BYOK：浏览器进程内存里的用户密钥，只会经 HTTP 头跟随单次请求进入服务端，
    用一次就消失；不进注册表、不进环境变量、不进任何持久化文件。

默认档开关（``AMZ_V2_DEFAULT_TRIAL``），缺省 fail-closed（closed）：
  - 未设置 / "" "0" "false" "closed" "off" → closed：默认档密钥一律不得出网；
  - "1" "true" "open" "on" → open：沿用部署密钥（受 ``entry.api_key_env`` 绑定）；
  - 其他任何值 → ValueError：解析不了就必须断，不许把未知值当 open。

解析结果是唯一权威口径：构造 provider 的工厂只采纳这里给到的值，
不允许在适配器或者业务路由里再各自读一遍环境变量。
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

DEFAULT_TRIAL_ENV = "AMZ_V2_DEFAULT_TRIAL"
CLOSED_VALUES = frozenset({"", "0", "false", "closed", "off"})
OPEN_VALUES = frozenset({"1", "true", "open", "on"})
SOURCE_BYOK = "byok"
SOURCE_DEFAULT = "default"
SOURCE_NONE = "none"


def resolve_default_trial(env: Mapping[str, str] | None) -> bool:
    """返回默认档是否放行；解析失败直接抛错（fail-closed）。"""

    source = {} if env is None else env
    value = (source.get(DEFAULT_TRIAL_ENV) or "").strip().lower()
    if value in OPEN_VALUES:
        return True
    if value in CLOSED_VALUES:
        return False
    raise ValueError(
        f"{DEFAULT_TRIAL_ENV} 只接受 0/1、false/true、closed/open、off/on"
        "；解析不了的任何值都按断开处理，请先核对配置。")


@dataclass(frozen=True)
class CredentialDecision:
    """一次构造要用的密钥与其来源标签；密钥值不进任何对外 payload。"""

    api_key: str | None
    source: str


def resolve_credentials(entry: Mapping[str, Any], env: Mapping[str, str] | None, *,
                        byok_api_key: str | None = None) -> CredentialDecision:
    """按优先级解析：BYOK 请求头 > 默认档（受开关约束）> 未配置。

    - BYOK：调用者明确给了这边的密钥就直接用；与开关无关（用户自己的额度）。
    - 默认档密钥存在但开关关闭：api_key=None 且 source=none（保持 configured=false
      的口径，没有任何密钥会被带进适配器或传到网上）。
    - 默认档密钥存在且开关打开：source=default。
    """

    value = byok_api_key.strip() if isinstance(byok_api_key, str) else ""
    if value:
        return CredentialDecision(api_key=value, source=SOURCE_BYOK)
    key_env = entry.get("api_key_env")
    raw_key = env.get(key_env) if key_env and env is not None else None
    key = raw_key.strip() if isinstance(raw_key, str) else ""
    if key and resolve_default_trial(env):
        return CredentialDecision(api_key=key, source=SOURCE_DEFAULT)
    return CredentialDecision(api_key=None, source=SOURCE_NONE)
