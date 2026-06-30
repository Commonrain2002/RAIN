"""Parse Codex token usage from local session JSONL (authoritative) or exec stdout fallback."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

TokenParseSource = Literal["codex_session_jsonl", "codex_exec_jsonl", "none"]


@dataclass(frozen=True)
class ParsedTokenUsage:
    prompt: int | None
    prompt_cache_hit: int | None
    prompt_cache_miss: int | None
    completion: int | None
    reasoning: int | None
    total: int | None
    source: TokenParseSource
    session_rollout_path: str | None = None


def collect_run_capture_text(stdout: str, stderr: str) -> str:
    parts = [stdout or "", stderr or ""]
    return "\n".join(p for p in parts if p)


def codex_home_dir() -> Path:
    override = os.environ.get("CODEX_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex"


def _aligned_prompt_fields(
    input_total: int,
    cache_hit: int,
) -> tuple[int | None, int | None, int | None]:
    """``input_tokens`` is total prompt; ``cached_input_tokens`` is cache hit."""
    if input_total <= 0 and cache_hit <= 0:
        return None, None, None
    prompt = input_total
    hit = min(cache_hit, input_total) if input_total > 0 else cache_hit
    miss = max(0, input_total - hit)
    return prompt, hit, miss


def _prompt_fields_from_codex_usage(
    input_tokens: int,
    cache_read: int,
) -> tuple[int | None, int | None, int | None]:
    """Resolve prompt totals from Codex ``input_tokens`` / ``cached_input_tokens``.

    Rollouts use either cumulative total prompt in ``input_tokens``, or uncached-only
    prompt with cache reported separately (full prompt = uncached + cached).
    """
    if input_tokens <= 0 and cache_read <= 0:
        return None, None, None
    if input_tokens >= 200_000:
        return _aligned_prompt_fields(input_tokens, cache_read)
    combined = input_tokens + cache_read
    if input_tokens > 0 and combined <= int(input_tokens * 1.5):
        return _aligned_prompt_fields(input_tokens, cache_read)
    prompt = combined
    hit = cache_read
    miss = input_tokens
    return prompt, hit, miss


def _usage_int(usage: dict[str, Any], key: str) -> int:
    try:
        return int(usage.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _parsed_from_usage_block(
    usage: dict[str, Any],
    *,
    source: TokenParseSource,
    session_rollout_path: str | None = None,
) -> ParsedTokenUsage:
    inp = _usage_int(usage, "input_tokens")
    cache_read = _usage_int(usage, "cached_input_tokens")
    out = _usage_int(usage, "output_tokens")
    reasoning = _usage_int(usage, "reasoning_output_tokens")
    if inp == 0 and cache_read == 0 and out == 0 and reasoning == 0:
        return ParsedTokenUsage(None, None, None, None, None, None, "none", session_rollout_path)

    prompt, hit, miss = _prompt_fields_from_codex_usage(inp, cache_read)
    reasoning_only = reasoning if reasoning else None
    completion_all = out + reasoning
    completion = completion_all if completion_all else None
    prompt_total = prompt if prompt is not None else 0
    total = prompt_total + completion_all
    return ParsedTokenUsage(
        prompt=prompt,
        prompt_cache_hit=hit,
        prompt_cache_miss=miss,
        completion=completion,
        reasoning=reasoning_only,
        total=total,
        source=source,
        session_rollout_path=session_rollout_path,
    )


def extract_thread_id_from_codex_json_text(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "thread.started":
            thread_id = ev.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                return thread_id
        if ev.get("type") == "session_meta":
            payload = ev.get("payload")
            if isinstance(payload, dict):
                session_id = payload.get("id")
                if isinstance(session_id, str) and session_id:
                    return session_id
    return None


def find_session_rollout_path(
    thread_id: str,
    *,
    codex_home: Path | None = None,
) -> Path | None:
    if not thread_id:
        return None
    root = (codex_home or codex_home_dir()) / "sessions"
    if not root.is_dir():
        return None
    matches = list(root.glob(f"**/rollout-*-{thread_id}.jsonl"))
    if not matches:
        matches = [p for p in root.glob("**/rollout-*.jsonl") if thread_id in p.name]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def parse_token_usage_from_session_json_text(
    text: str,
    *,
    session_rollout_path: str | None = None,
) -> ParsedTokenUsage:
    """Use the last ``token_count`` event's ``total_token_usage`` (session cumulative)."""
    if not text or not text.strip():
        return ParsedTokenUsage(None, None, None, None, None, None, "none", session_rollout_path)

    last_usage: dict[str, Any] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict) or ev.get("type") != "event_msg":
            continue
        payload = ev.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue
        total_usage = info.get("total_token_usage")
        if isinstance(total_usage, dict):
            last_usage = total_usage

    if last_usage is None:
        return ParsedTokenUsage(None, None, None, None, None, None, "none", session_rollout_path)

    return _parsed_from_usage_block(
        last_usage,
        source="codex_session_jsonl",
        session_rollout_path=session_rollout_path,
    )


def parse_token_usage_from_session_path(path: Path) -> ParsedTokenUsage:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_token_usage_from_session_json_text(text, session_rollout_path=str(path.resolve()))


def parse_token_usage_from_codex_exec_json_text(text: str) -> ParsedTokenUsage:
    """Fallback: sum ``usage`` on each ``turn.completed`` line in ``codex exec --json`` stdout."""
    if not text or not text.strip():
        return ParsedTokenUsage(None, None, None, None, None, None, "none")

    prompt_sum = cache_read_sum = out = reasoning = 0
    turn_count = 0
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict) or ev.get("type") != "turn.completed":
            continue
        usage = ev.get("usage")
        if not isinstance(usage, dict):
            continue
        turn_count += 1
        turn_inp = _usage_int(usage, "input_tokens")
        turn_cache = _usage_int(usage, "cached_input_tokens")
        turn_prompt, turn_hit, turn_miss = _prompt_fields_from_codex_usage(turn_inp, turn_cache)
        prompt_sum += int(turn_prompt or 0)
        cache_read_sum += int(turn_hit or 0)
        out += _usage_int(usage, "output_tokens")
        reasoning += _usage_int(usage, "reasoning_output_tokens")

    if turn_count == 0:
        return ParsedTokenUsage(None, None, None, None, None, None, "none")

    completion_all = out + reasoning
    return ParsedTokenUsage(
        prompt=prompt_sum if prompt_sum else None,
        prompt_cache_hit=cache_read_sum if cache_read_sum else None,
        prompt_cache_miss=(prompt_sum - cache_read_sum) if prompt_sum else None,
        completion=completion_all if completion_all else None,
        reasoning=reasoning if reasoning else None,
        total=(prompt_sum + completion_all) if prompt_sum or completion_all else None,
        source="codex_exec_jsonl",
    )


def _parse_iso_timestamp(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_agent_run_seconds_from_session_json_text(text: str) -> int | None:
    """Wall-clock span from first to last ``timestamp`` field in session rollout JSONL."""
    if not text or not text.strip():
        return None
    timestamps: list[datetime] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        raw_ts = ev.get("timestamp")
        if not isinstance(raw_ts, str):
            continue
        parsed = _parse_iso_timestamp(raw_ts)
        if parsed is not None:
            timestamps.append(parsed)
    if not timestamps:
        return None
    if len(timestamps) == 1:
        return 0
    span = (max(timestamps) - min(timestamps)).total_seconds()
    if span < 0:
        return None
    return int(round(span))


def parse_agent_run_seconds_from_session_path(path: Path) -> int | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_agent_run_seconds_from_session_json_text(text)


def resolve_codex_agent_run_seconds(
    stdout: str,
    stderr: str,
    *,
    thread_id: str | None = None,
    codex_home: Path | None = None,
) -> int | None:
    resolved_thread = thread_id or extract_thread_id_from_codex_json_text(
        collect_run_capture_text(stdout, stderr),
    )
    if not resolved_thread:
        return None
    session_path = find_session_rollout_path(resolved_thread, codex_home=codex_home)
    if session_path is None or not session_path.is_file():
        return None
    return parse_agent_run_seconds_from_session_path(session_path)


def resolve_codex_token_usage(
    stdout: str,
    stderr: str,
    *,
    thread_id: str | None = None,
    codex_home: Path | None = None,
) -> tuple[ParsedTokenUsage, str | None]:
    resolved_thread = thread_id or extract_thread_id_from_codex_json_text(stdout)
    if resolved_thread:
        session_path = find_session_rollout_path(resolved_thread, codex_home=codex_home)
        if session_path is not None and session_path.is_file():
            parsed = parse_token_usage_from_session_path(session_path)
            if parsed.source != "none":
                return parsed, resolved_thread

    parsed = parse_token_usage_from_codex_exec_json_text(stdout)
    return parsed, resolved_thread


# Backward-compatible alias used in tests.
parse_token_usage_from_codex_json_text = parse_token_usage_from_codex_exec_json_text
