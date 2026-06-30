"""Parse token usage from Claude Code (session JSONL, aligned with CLI /usage)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

TokenParseSource = Literal[
    "claude_session_jsonl",
    "claude_stdout_model_usage",
    "claude_stdout_json",
    "none",
]


@dataclass(frozen=True)
class ParsedTokenUsage:
    prompt: int | None
    prompt_cache_hit: int | None
    prompt_cache_miss: int | None
    completion: int | None
    reasoning: int | None
    total: int | None
    source: TokenParseSource


def default_claude_home() -> Path:
    override = os.environ.get("CLAUDE_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def collect_run_capture_text(stdout: str, stderr: str) -> str:
    parts = [stdout or "", stderr or ""]
    return "\n".join(p for p in parts if p)


def claude_project_slug(repo_dir: Path) -> str:
    """Best-effort match for ``~/.claude/projects/<slug>/`` (see also ``resolve_session_jsonl_path``)."""
    resolved = str(repo_dir.resolve())
    return resolved.replace("/", "-")


def session_jsonl_path(repo_dir: Path, session_id: str, claude_home: Path | None = None) -> Path:
    home = claude_home if claude_home is not None else default_claude_home()
    slug = claude_project_slug(repo_dir)
    return home / "projects" / slug / f"{session_id}.jsonl"


def resolve_session_jsonl_path(
    repo_dir: Path,
    session_id: str,
    claude_home: Path | None = None,
) -> Path | None:
    """Locate session JSONL; Claude may encode ``_`` in path segments differently than ``/`` -> ``-``."""
    home = claude_home if claude_home is not None else default_claude_home()
    resolved = str(repo_dir.resolve())
    slug_candidates = [
        resolved.replace("/", "-"),
        resolved.replace("/", "-").replace("_", "-"),
    ]
    paths = [home / "projects" / slug / f"{session_id}.jsonl" for slug in slug_candidates]
    paths.append(session_jsonl_path(repo_dir, session_id, claude_home=home))
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return path
    matches = list((home / "projects").glob(f"**/{session_id}.jsonl"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        hint = resolved.replace("/", "-")
        for path in matches:
            if hint in str(path):
                return path
        return matches[0]
    return None


def _usage_int(usage: dict[str, Any], key: str) -> int:
    try:
        return int(usage.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _cache_creation_tokens(usage: dict[str, Any]) -> int:
    creation = usage.get("cache_creation")
    if isinstance(creation, dict):
        return _usage_int(creation, "ephemeral_5m_input_tokens") + _usage_int(
            creation, "ephemeral_1h_input_tokens"
        )
    return _usage_int(usage, "cache_creation_input_tokens")


def _usage_total(usage: dict[str, Any]) -> int:
    return (
        _usage_int(usage, "input_tokens")
        + _usage_int(usage, "output_tokens")
        + _usage_int(usage, "cache_read_input_tokens")
        + _cache_creation_tokens(usage)
    )


def _aligned_prompt_fields(
    raw_input: int,
    cache_read: int,
) -> tuple[int | None, int | None, int | None]:
    """Align CSV fields with ProofAgent: miss = non-cached input, prompt = hit + miss."""
    miss = raw_input if raw_input else None
    hit = cache_read if cache_read else None
    if miss is None and hit is None:
        return None, None, None
    return raw_input + cache_read, hit, miss


def parse_session_tokens_from_jsonl(
    jsonl_path: Path,
    *,
    session_id: str | None = None,
) -> ParsedTokenUsage | None:
    """Sum the fullest usage row once per assistant ``message.id``.

    Claude session JSONL can contain multiple rows for the same assistant message:
    early streaming/thinking rows often have only ``input_tokens`` and
    ``output_tokens=0``, while the later row carries cache read/creation and
    final output.  Keep the row with the largest usage total per message id.
    """
    if not jsonl_path.is_file():
        return None

    best_usage_by_message_id: dict[str, dict[str, Any]] = {}

    try:
        text = jsonl_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if session_id and rec.get("sessionId") not in (None, session_id):
            continue
        if rec.get("type") != "assistant":
            continue
        msg = rec.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        mid = msg.get("id")
        if not isinstance(mid, str):
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        previous = best_usage_by_message_id.get(mid)
        if previous is None or _usage_total(usage) >= _usage_total(previous):
            best_usage_by_message_id[mid] = usage

    if not best_usage_by_message_id:
        return None

    inp = 0
    out = 0
    cache_read = 0
    cache_create = 0
    for usage in best_usage_by_message_id.values():
        inp += _usage_int(usage, "input_tokens")
        out += _usage_int(usage, "output_tokens")
        cache_read += _usage_int(usage, "cache_read_input_tokens")
        cache_create += _cache_creation_tokens(usage)

    total = inp + out + cache_read + cache_create
    prompt, hit, miss = _aligned_prompt_fields(inp, cache_read)
    return ParsedTokenUsage(
        prompt=prompt,
        prompt_cache_hit=hit,
        prompt_cache_miss=miss,
        completion=out,
        reasoning=None,
        total=total,
        source="claude_session_jsonl",
    )


def _parse_model_usage_block(model_usage: dict[str, Any]) -> ParsedTokenUsage | None:
    inp = out = cache_read = cache_create = 0
    for value in model_usage.values():
        if not isinstance(value, dict):
            continue
        try:
            inp += int(value.get("inputTokens") or 0)
            out += int(value.get("outputTokens") or 0)
            cache_read += int(value.get("cacheReadInputTokens") or 0)
            cache_create += int(value.get("cacheCreationInputTokens") or 0)
        except (TypeError, ValueError):
            continue
    if inp == 0 and out == 0 and cache_read == 0 and cache_create == 0:
        return None
    total = inp + out + cache_read + cache_create
    prompt, hit, miss = _aligned_prompt_fields(inp, cache_read)
    return ParsedTokenUsage(
        prompt=prompt,
        prompt_cache_hit=hit,
        prompt_cache_miss=miss,
        completion=out,
        reasoning=None,
        total=total,
        source="claude_stdout_model_usage",
    )


def _parse_stdout_json_usage(text: str) -> ParsedTokenUsage | None:
    """Parse ``claude -p --output-format json`` (prefer ``modelUsage`` rollup = billing total)."""
    text = text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    model_usage = obj.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        parsed = _parse_model_usage_block(model_usage)
        if parsed is not None:
            return parsed

    usage = obj.get("usage")
    if not isinstance(usage, dict):
        for key in ("result", "message"):
            nested = obj.get(key)
            if isinstance(nested, dict) and isinstance(nested.get("usage"), dict):
                usage = nested["usage"]
                break
    if not isinstance(usage, dict):
        return None
    inp = _usage_int(usage, "input_tokens")
    out = _usage_int(usage, "output_tokens")
    cache_read = _usage_int(usage, "cache_read_input_tokens")
    cache_create = _cache_creation_tokens(usage)
    total = inp + out + cache_read + cache_create
    prompt, hit, miss = _aligned_prompt_fields(inp, cache_read)
    return ParsedTokenUsage(
        prompt=prompt,
        prompt_cache_hit=hit,
        prompt_cache_miss=miss,
        completion=out,
        reasoning=None,
        total=total,
        source="claude_stdout_json",
    )


def resolve_claude_token_usage(
    stdout: str,
    stderr: str,
    *,
    repo_dir: Path,
    session_id: str,
    claude_home: Path | None = None,
) -> ParsedTokenUsage:
    combined = collect_run_capture_text(stdout, stderr)
    from_stdout = _parse_stdout_json_usage(combined)
    if from_stdout is not None and from_stdout.source == "claude_stdout_model_usage":
        return from_stdout

    jsonl = resolve_session_jsonl_path(repo_dir, session_id, claude_home=claude_home)
    from_jsonl = (
        parse_session_tokens_from_jsonl(jsonl, session_id=session_id)
        if jsonl is not None
        else None
    )
    if from_jsonl is not None:
        return from_jsonl

    if from_stdout is not None:
        return from_stdout

    return ParsedTokenUsage(None, None, None, None, None, None, "none")
