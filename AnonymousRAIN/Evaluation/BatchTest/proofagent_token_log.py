"""Parse ProofAgent token usage from console / log text (Serilog output)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

TokenParseSource = Literal[
    "run_cumulative_http",
    "cumulative",
    "llm_usage_run_cumulative",
    "none",
]


@dataclass(frozen=True)
class ParsedTokenUsage:
    prompt: int | None
    prompt_cache_hit: int | None
    prompt_cache_miss: int | None
    completion: int | None
    total: int | None
    source: TokenParseSource


# Program.cs final summary (preferred when process exits normally).
_RUN_CUMULATIVE_HTTP_RE = re.compile(
    r"Run cumulative tokens \(all HTTP\):\s*prompt=(\d+)"
    r"(?:\s+promptCacheHitTokens=(\d+)\s+promptCacheMissTokens=(\d+))?"
    r"\s+completion=(\d+)\s+total=(\d+)",
    re.MULTILINE,
)

_CUMULATIVE_LOOP_RE = re.compile(
    r"Cumulative tokens(?: \(loop ChatAsync sum\))?:\s*prompt=(\d+)"
    r"(?:\s+promptCacheHitTokens=(\d+)\s+promptCacheMissTokens=(\d+))?"
    r"\s+completion=(\d+)\s+total=(\d+)",
    re.MULTILINE,
)

_RUN_CUMULATIVE_MULTILINE_RE = re.compile(
    r"runCumulativePromptTokens=(\d+)\s*\n"
    r"runCumulativePromptCacheHitTokens=(\d+)\s*\n"
    r"runCumulativePromptCacheMissTokens=(\d+)\s*\n"
    r"runCumulativeCompletionTokens=(\d+)\s*\n"
    r"runCumulativeTotalTokens=(\d+)",
    re.MULTILINE,
)


def parse_token_usage_from_text(text: str) -> ParsedTokenUsage:
    """Extract run token totals from a **single** ProofAgent run capture (stdout/stderr only).

    Do not pass the shared ``Log/proofagent*.log`` (multiple runs); batch uses
    :func:`collect_run_capture_text` only.

    Priority:
    1. Last ``Run cumulative tokens (all HTTP):`` (Program.cs, normal exit).
    2. Last ``Cumulative tokens (loop ChatAsync sum):`` or legacy ``Cumulative tokens:``.
    3. Last multiline ``runCumulative*`` in ``LLM usage:`` blocks (process-wide; all sessions).

    ``sessionCumulative*`` is intentionally ignored (single-session only; misreports multi-session runs).
    """
    if not text or not text.strip():
        return ParsedTokenUsage(None, None, None, None, None, "none")

    run_http_matches = list(_RUN_CUMULATIVE_HTTP_RE.finditer(text))
    if run_http_matches:
        return _from_cumulative_match(run_http_matches[-1], source="run_cumulative_http")

    cumulative_matches = list(_CUMULATIVE_LOOP_RE.finditer(text))
    if cumulative_matches:
        return _from_cumulative_match(cumulative_matches[-1], source="cumulative")

    run_usage = _parse_last_run_cumulative_from_llm_usage(text)
    if run_usage is not None:
        return run_usage

    return ParsedTokenUsage(None, None, None, None, None, "none")


def _parse_last_run_cumulative_from_llm_usage(text: str) -> ParsedTokenUsage | None:
    last_match: re.Match[str] | None = None
    for match in _RUN_CUMULATIVE_MULTILINE_RE.finditer(text):
        last_match = match
    if last_match is None:
        return None
    g = last_match.groups()
    return ParsedTokenUsage(
        prompt=int(g[0]),
        prompt_cache_hit=int(g[1]),
        prompt_cache_miss=int(g[2]),
        completion=int(g[3]),
        total=int(g[4]),
        source="llm_usage_run_cumulative",
    )


def _from_cumulative_match(
    match: re.Match[str],
    *,
    source: TokenParseSource = "cumulative",
) -> ParsedTokenUsage:
    g = match.groups()
    hit = int(g[1]) if g[1] is not None else None
    miss = int(g[2]) if g[2] is not None else None
    return ParsedTokenUsage(
        prompt=int(g[0]),
        prompt_cache_hit=hit,
        prompt_cache_miss=miss,
        completion=int(g[3]),
        total=int(g[4]),
        source=source,
    )


def collect_run_capture_text(run_out: str, run_err: str) -> str:
    """Stdout/stderr from one ``run.sh`` invocation only (no shared Serilog file)."""
    parts: list[str] = []
    if run_out:
        parts.append(run_out)
    if run_err:
        parts.append(run_err)
    return "\n".join(parts)
