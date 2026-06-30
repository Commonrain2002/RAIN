"""Parse OpenCode token usage (aligned with ``opencode stats`` / session DB)."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

TokenParseSource = Literal[
    "opencode_session_db",
    "opencode_step_finish",
    "opencode_message_updated",
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


def default_opencode_db_path() -> Path:
    override = os.environ.get("OPENCODE_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local/share/opencode/opencode.db"


def collect_run_capture_text(stdout: str, stderr: str) -> str:
    parts = [stdout or "", stderr or ""]
    return "\n".join(p for p in parts if p)


def _aligned_prompt_fields(
    raw_input: int,
    cache_read: int,
) -> tuple[int | None, int | None, int | None]:
    """Align CSV fields with ProofAgent: miss = input, prompt = hit + miss."""
    miss = raw_input if raw_input else None
    hit = cache_read if cache_read else None
    if miss is None and hit is None:
        return None, None, None
    return raw_input + cache_read, hit, miss


def extract_session_id_from_opencode_json_text(text: str) -> str | None:
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
        sid = ev.get("sessionID")
        if isinstance(sid, str) and sid.startswith("ses_"):
            return sid
    return None


def parse_session_tokens_from_db(session_id: str, db_path: Path | None = None) -> ParsedTokenUsage | None:
    """Read canonical session totals (same as ``opencode stats`` overview)."""
    path = db_path if db_path is not None else default_opencode_db_path()
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            """
            SELECT tokens_input, tokens_output, tokens_reasoning,
                   tokens_cache_read, tokens_cache_write
            FROM session WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None:
        return None
    inp, out, reasoning, cache_read, cache_write = (int(x or 0) for x in row)
    total = inp + out + reasoning + cache_read + cache_write
    prompt, hit, miss = _aligned_prompt_fields(inp, cache_read)
    return ParsedTokenUsage(
        prompt=prompt,
        prompt_cache_hit=hit,
        prompt_cache_miss=miss,
        completion=out,
        reasoning=reasoning if reasoning else None,
        total=total,
        source="opencode_session_db",
    )


def _tokens_dict(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return raw


def _parse_from_step_finish_events(text: str) -> ParsedTokenUsage:
    acc = {
        "input": 0,
        "output": 0,
        "reasoning": 0,
        "cache_read": 0,
        "cache_write": 0,
        "step_count": 0,
    }
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict) or ev.get("type") != "step_finish":
            continue
        part = ev.get("part")
        if not isinstance(part, dict):
            continue
        tok = _tokens_dict(part.get("tokens"))
        if tok is None:
            continue
        acc["step_count"] += 1
        try:
            acc["input"] += int(tok.get("input") or 0)
            acc["output"] += int(tok.get("output") or 0)
            acc["reasoning"] += int(tok.get("reasoning") or 0)
        except (TypeError, ValueError):
            continue
        cache = tok.get("cache")
        if isinstance(cache, dict):
            try:
                acc["cache_read"] += int(cache.get("read") or 0)
                acc["cache_write"] += int(cache.get("write") or 0)
            except (TypeError, ValueError):
                pass

    if acc["step_count"] == 0:
        return ParsedTokenUsage(None, None, None, None, None, None, "none")

    inp, out, reasoning = acc["input"], acc["output"], acc["reasoning"]
    cache_read, cache_write = acc["cache_read"], acc["cache_write"]
    total = inp + out + reasoning + cache_read + cache_write
    prompt, hit, miss = _aligned_prompt_fields(inp, cache_read)
    return ParsedTokenUsage(
        prompt=prompt,
        prompt_cache_hit=hit,
        prompt_cache_miss=miss,
        completion=out,
        reasoning=reasoning if reasoning else None,
        total=total,
        source="opencode_step_finish",
    )


def parse_token_usage_from_opencode_json_text(
    text: str,
    *,
    db_path: Path | None = None,
) -> ParsedTokenUsage:
    """Prefer session row in OpenCode DB; fallback to summing ``step_finish`` events.

    Do **not** use ``step_finish.tokens.total`` as session total  it is a per-step
    context metric, not the same as ``opencode stats`` (input + output + reasoning + cache).
    """
    if not text or not text.strip():
        return ParsedTokenUsage(None, None, None, None, None, None, "none")

    session_id = extract_session_id_from_opencode_json_text(text)
    if session_id:
        from_db = parse_session_tokens_from_db(session_id, db_path=db_path)
        if from_db is not None:
            return from_db

    return _parse_from_step_finish_events(text)


def resolve_opencode_token_usage(
    stdout: str,
    stderr: str,
    *,
    db_path: Path | None = None,
) -> tuple[ParsedTokenUsage, str | None]:
    combined = collect_run_capture_text(stdout, stderr)
    session_id = extract_session_id_from_opencode_json_text(combined)
    return parse_token_usage_from_opencode_json_text(combined, db_path=db_path), session_id
