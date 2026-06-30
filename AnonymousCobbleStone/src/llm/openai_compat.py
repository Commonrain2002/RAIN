"""Helpers for OpenAI-compatible APIs (OpenAI, DeepSeek, etc.)."""

from __future__ import annotations

import typing as t

from src.config import CONFIG
from src.llm.model_names import is_deepseek_model
from src.llm.types import AssistantMessage


def deepseek_thinking_mode_request_kwargs(model: str) -> t.Dict[str, t.Any]:
    """
    DeepSeek thinking mode (OpenAI-compatible).
    See https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
    """
    if not is_deepseek_model(model):
        return {}
    return {
        "reasoning_effort": CONFIG.DEEPSEEK_REASONING_EFFORT,
        "thinking": {"type": "enabled"},
    }


def assistant_message_from_openai(message: t.Any) -> AssistantMessage:
    """
    Build AssistantMessage from an API choice.message.

    DeepSeek thinking models (e.g. deepseek-v4-flash) often put chain-of-thought in
    ``reasoning_content`` and may leave ``content`` empty. Preserve ``reasoning_content``
    for follow-up requests; use visible ``content`` when present, else reasoning text
    for downstream string consumers.
    """
    content = message.content or ""
    reasoning_content = getattr(message, "reasoning_content", None) or None
    if not content.strip() and reasoning_content:
        content = reasoning_content
    return AssistantMessage(content=content, reasoning_content=reasoning_content)
