"""Product V2 跨 provider 的错误词表（唯一权威，计划 §9）。

语义 provider 与图像网关共用同一套归口与重试语义；任何一侧都不许自带第二份词表，
否则「失败」在不同路由里会变成不同的意思：

  - ``input_rejected``：请求本身不合法，没有调用上游，重试无用（fatal）。
  - ``provider_failed``：上游明确拒绝或明确失败，结果不存在。
  - ``provider_unknown``：请求可能已被受理而结果未知，绝不自动重提（requires_review）。
  - ``internal``：本进程的问题（配置缺失、依赖缺失、未分类异常）。

本模块只放词表与合法性断言：不联网、不读配置、不写任何状态。
"""
from __future__ import annotations

ERROR_FAMILIES = ("input_rejected", "provider_failed", "provider_unknown", "internal")
RETRY_POLICIES = ("retryable", "requires_review", "fatal")

UNKNOWN_FAMILY = "provider_unknown"


def assert_vocabulary(family: str, retry_policy: str) -> None:
    """词表外的取值是程序员错误，必须当场炸掉而不是悄悄降级。"""

    if family not in ERROR_FAMILIES:
        raise ValueError(f"unknown error family: {family}")
    if retry_policy not in RETRY_POLICIES:
        raise ValueError(f"unknown retry policy: {retry_policy}")
