"""Resolve and normalize LLM chat-completions URL for evaluation batch runs."""

from __future__ import annotations

import os
from urllib.parse import urlunparse, urlparse

DEFAULT_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/v1/chat/completions"


def _normalize_chat_completions_url(raw: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError("LLM base URL is empty after trim.")

    candidate = trimmed
    if not candidate.startswith(("http://", "https://")):
        candidate = "https://" + candidate

    parsed = urlparse(candidate)
    if not parsed.netloc:
        raise ValueError(f"LLM base URL has no host: {raw!r}")

    path = (parsed.path or "").rstrip("/")
    if not path:
        path = "/v1/chat/completions"
    elif path in ("/v1", "/v1/"):
        path = "/v1/chat/completions"
    elif "chat/completions" not in path:
        if path.endswith("/v1"):
            path = path + "/chat/completions"
        else:
            path = path + "/v1/chat/completions"

    return urlunparse((parsed.scheme or "https", parsed.netloc, path, "", parsed.query, ""))


def resolve_llm_base_url(explicit: str | None) -> str:
    """Full POST URL for chat completions (never host-only)."""
    if explicit is not None and explicit.strip():
        return _normalize_chat_completions_url(explicit)

    for env_name in ("BASE_URL", "DEEPSEEK_BASE_URL", "OPENROUTER_BASE_URL"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return _normalize_chat_completions_url(value)

    return DEFAULT_CHAT_COMPLETIONS_URL


def resolve_llm_api_key(explicit: str | None) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()

    for env_name in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value

    return ""
