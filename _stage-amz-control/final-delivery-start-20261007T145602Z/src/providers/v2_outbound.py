#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""出站联网守卫：把「这次请求允许发到哪里」收敛成一个可判定函数（V2.R4.3）。

「零信任外呼」的落法：不是让 SDK/传输自己判断，而是在真实外呼前统一调用
``validate_outbound_url``，任何不满足策略的地址都会在打开发请求之前被拒绝
（fail-closed，先拒绝再放行）。这样图像网关（或以后的其他真实适配器）只需要
一处扣点，保证所有请求（提交/查询/下载）都走同一个白名单。

三层判定，从宽到严：
  1. https 才能出网（DashScope 是 https，没有 http 流量）；
  2. 主机必须在白名单（后缀匹配：``aliyuncs.com`` 或 ``.aliyuncs.com``，不使用通配符）；
  3. 私网/回环/链路本地/多播/未指定/保留段一律拒绝，IP 字面量按 ``ipaddress``
     分析（``is_global`` 判定）；DNS 重绑定残余风险不能被这一层消除，在计划与
     验收报告里单独记录，不因守卫生效而声称已解决。

允许写 ``port``（默认 443 或省略），但不允许 ``user:pass`` 形式的 URL 凭据内嵌。

只依赖标准库（``ipaddress`` + ``urllib.parse``），不引入任何新依赖。
"""
from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import urlsplit

# DashScope 端点与签名结果地址（OSS）都以 ``aliyuncs.com`` 结尾；火山方舟（Ark）端点
# （ark.cn-beijing.volces.com）以 ``volces.com`` 结尾（V2.R5.2）。这两类是当前唯一
# 允许的真实外呼后缀，别的域一律拒绝。字节级白名单不留在客户端，在服务端判定。
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = ("aliyuncs.com", "volces.com")
_CARE_FOR_PRIVATE = frozenset({"localhost"})


class OutboundPolicyError(ValueError):
    """出站目标不满足白名单策略；``reason`` 只写主机/端口号级事实，不带密钥。"""

    def __init__(self, reason: str) -> None:
        super().__init__(f"出站目标不满足白名单策略：{reason}。")
        self.reason = reason


def is_private_host(hostname: object) -> bool:
    """IP 字面量与已知内部地址判为不可出站；域名不做 DNS 判定（白名单兜底）。"""

    host = (str(hostname or "")).strip().strip(".").lower()
    if not host:
        return True
    if host in _CARE_FOR_PRIVATE:
        return True
    if host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False  # 不是 IP 字面量：交给白名单判定，DNS 查询不在这一层做
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return not address.ipv4_mapped.is_global
    if getattr(address, "scope_id", None):
        return True  # 带作用域（zone id）的 IPv6 通常是链路本地
    return not address.is_global


def host_allowed(hostname: object, allowed_hosts: Iterable[str] = DEFAULT_ALLOWED_HOSTS) -> bool:
    host = (str(hostname or "")).strip().strip(".").lower()
    if not host:
        return False
    for candidate in allowed_hosts:
        pattern = str(candidate).strip().strip(".").lower()
        if pattern and (host == pattern or host.endswith("." + pattern)):
            return True
    return False


def validate_outbound_url(value: object, *,
                          allowed_hosts: Iterable[str] = DEFAULT_ALLOWED_HOSTS,
                          label: str = "") -> str:
    """一个地址要么合法（原样返回），要么抛 ``OutboundPolicyError``；判定不发请求。"""

    text = value if isinstance(value, str) else None
    if text is None or not text.strip():
        raise OutboundPolicyError("目标是空字符串")
    raw = text.strip()
    if len(raw) > 4096 or any(ord(ch) < 32 for ch in raw):
        raise OutboundPolicyError("目标里包含控制字符或长度异常")
    prefix = f"{label} " if label else ""
    try:
        parts = urlsplit(raw)
        port = parts.port
    except (ValueError, UnicodeError):
        raise OutboundPolicyError(f"{prefix}URL 不能解析") from None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").strip().strip(".").lower()
    if scheme != "https":
        raise OutboundPolicyError(f"{prefix}必须是 https（实际 {scheme or '缺省'}）")
    if parts.username or parts.password:
        raise OutboundPolicyError(f"{prefix}不允许在 URL 内嵌凭据")
    if not host:
        raise OutboundPolicyError(f"{prefix}没有主机名")
    if port not in (None, 443):
        raise OutboundPolicyError(f"{prefix}端口必须是 443 或省略（实际 {port}）")
    if is_private_host(host):
        raise OutboundPolicyError(f"{prefix}主机 {host} 是私网/回环/链路本地地址，禁止出站")
    if not host_allowed(host, allowed_hosts):
        raise OutboundPolicyError(f"{prefix}主机 {host} 不在白名单内")
    return raw
