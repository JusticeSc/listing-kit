"""OpenAI 兼容聊天通道的共享装配与响应读取（V2.5.2 提取；行为不变）。

语义（deepseek-v4.1-flash）与复核（VLM）两条链路共用同一套：
  - ``default_chat_model``：SEL-003 决定的 langchain-openai ChatOpenAI 构造（超时显式、max_retries=0）；
  - 响应读取：可见文本、finish_reason、request_id、usage —— 都是纯函数，不看业务状态。

提取动机：V2.5.2 复核 provider 必须复用 SEL-003 通道而不是另建 HTTP 客户端或第二份装配代码；
``tools/verify_v2_5_2_vlm_review.py`` 会断言复核模块没有自建传输。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def default_chat_model(*, model_id: str, base_url: str, api_key: str | None,
                       timeout: float) -> Any:
    from langchain_openai import ChatOpenAI  # 延迟导入：离线路径不需要 SDK

    return ChatOpenAI(model=model_id, base_url=base_url, api_key=api_key,
                      timeout=timeout, max_retries=0)


def visible_text(raw: Any) -> str:
    """AIMessage 的可见文本；推理型模型可能只有 reasoning、没有可见文本。"""

    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        parts: list[str] = []
        for block in content:
            if isinstance(block, Mapping):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def response_finish_reason(raw: Any) -> str | None:
    for holder in (getattr(raw, "response_metadata", None), getattr(raw, "additional_kwargs", None)):
        if isinstance(holder, Mapping):
            reason = holder.get("finish_reason")
            if isinstance(reason, str) and reason:
                return reason
    return None


def response_request_id(raw: Any) -> str | None:
    metadata = getattr(raw, "response_metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    for key in ("id", "request_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:160]
    headers = metadata.get("headers")
    if isinstance(headers, Mapping):
        for name, value in headers.items():
            if str(name).lower() in {"x-request-id", "request-id", "x-dashscope-request-id"}:
                if isinstance(value, str) and value.strip():
                    return value.strip()[:160]
    return None


def response_usage(raw: Any) -> dict[str, int]:
    usage: dict[str, int] = {}
    metadata = getattr(raw, "usage_metadata", None)
    if not isinstance(metadata, Mapping):
        return usage
    for source, target in (("input_tokens", "prompt_tokens"),
                           ("output_tokens", "completion_tokens"),
                           ("total_tokens", "total_tokens")):
        value = metadata.get(source)
        if isinstance(value, int) and not isinstance(value, bool):
            usage[target] = value
    details = metadata.get("output_token_details")
    if isinstance(details, Mapping):
        reasoning = details.get("reasoning")
        if isinstance(reasoning, int) and not isinstance(reasoning, bool):
            usage["reasoning_tokens"] = reasoning
    return usage
