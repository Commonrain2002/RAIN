"""Detect obvious cheating in Claude batch trials (internet or external proof sources)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from claude.claude_token_log import resolve_session_jsonl_path

_EXTERNAL_ROOT_MARKERS = (
    "AgentTest",
    "evaluation workspace",
    "ProofAgent",
    "coqstoq",
)

_TMP_CHEAT_PATTERN = re.compile(
    r"/tmp/(?:original|codex|backup|.*proof|.*_backup|fix_proof|part\d|interp|split_backup)",
    re.I,
)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip("'\"")


def _path_allowed(path: str, repo_dir: str) -> bool:
    p = _normalize_path(path)
    if not p.startswith("/"):
        return True
    if "/.opam/" in p:
        return True
    repo = repo_dir.replace("\\", "/").rstrip("/")
    if repo and (p == repo or p.startswith(repo + "/")):
        return True
    return False


def _is_external_resource_path(path: str) -> bool:
    p = _normalize_path(path)
    if "/.opam/" in p:
        return False
    if "/.claude/projects/" in p:
        return False
    return any(marker in p for marker in _EXTERNAL_ROOT_MARKERS)


def _scan_stdout_transcript(result_text: str) -> list[str]:
    reasons: list[str] = []
    if re.search(
        r"earlier batch|already present in an earlier|correct version of .* was already",
        result_text,
        re.I,
    ):
        reasons.append("transcript_earlier_batch")
    if re.search(
        r"restored (?:to|from|the).*(?:original|complete proof)",
        result_text,
        re.I,
    ):
        reasons.append("transcript_restored_external")
    return reasons


def _scan_session_jsonl(jsonl_path: Path, repo_dir: Path) -> list[str]:
    reasons: list[str] = []
    if not jsonl_path.is_file():
        return reasons
    repo = str(repo_dir.resolve()).replace("\\", "/").rstrip("/")
    text = jsonl_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = rec.get("message") or rec
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name") or "")
            inp = block.get("input")
            if not isinstance(inp, dict):
                inp = {}
            if name in ("WebSearch", "WebFetch"):
                reasons.append(f"tool:{name}")
            if name == "Bash":
                cmd = str(inp.get("command") or "")
                if re.search(r"https?://", cmd) or re.search(r"\b(curl|wget)\b", cmd, re.I):
                    reasons.append("bash_network")
                for match in re.finditer(r"(?:cp|cat|mv|sed)\s+([^\s;|&]+)", cmd):
                    token = _normalize_path(match.group(1))
                    if not token.startswith("/"):
                        continue
                    if _path_allowed(token, repo):
                        continue
                    if _is_external_resource_path(token):
                        reasons.append(f"bash_external:{token[:120]}")
                    elif _TMP_CHEAT_PATTERN.search(token):
                        reasons.append(f"bash_tmp_copy:{token[:120]}")
            if name in ("Read", "Grep", "Glob"):
                for key in ("file_path", "path"):
                    val = inp.get(key)
                    if not isinstance(val, str) or not val.startswith("/"):
                        continue
                    vp = _normalize_path(val)
                    if _path_allowed(vp, repo):
                        continue
                    if _is_external_resource_path(vp):
                        reasons.append(f"read_external:{vp[:120]}")
    return reasons


def detect_cheat_reasons(
    *,
    trial_artifacts_dir: Path,
    repo_dir: Path,
    session_id: str,
    run_stdout_text: str | None = None,
) -> list[str]:
    """Return non-empty reason tags if the trial likely cheated; else []."""
    reasons: list[str] = []
    jsonl = resolve_session_jsonl_path(repo_dir, session_id)
    if jsonl is not None:
        reasons.extend(_scan_session_jsonl(jsonl, repo_dir))
    stdout_text = run_stdout_text
    stdout_path = trial_artifacts_dir / "run_stdout.log"
    if stdout_text is None and stdout_path.is_file():
        stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    if stdout_text:
        try:
            parsed = json.loads(stdout_text.strip())
            result_field = str(parsed.get("result") or "")
            reasons.extend(_scan_stdout_transcript(result_field))
            usage = parsed.get("usage") or {}
            server_tool = usage.get("server_tool_use") or {}
            if int(server_tool.get("web_search_requests") or 0) > 0:
                reasons.append("usage_web_search")
            if int(server_tool.get("web_fetch_requests") or 0) > 0:
                reasons.append("usage_web_fetch")
        except json.JSONDecodeError:
            pass
    deduped: list[str] = []
    seen: set[str] = set()
    for item in reasons:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return _filter_obvious_cheat_only(deduped)


def _filter_obvious_cheat_only(reasons: list[str]) -> list[str]:
    """Drop tmp-staging-only hits; keep internet or external evaluation workspace/AgentTest access."""
    if not reasons:
        return []
    hard_prefixes = (
        "bash_external:",
        "read_external:",
        "tool:Web",
        "bash_network",
        "usage_web",
        "transcript_",
    )
    if any(item.startswith(hard_prefixes) or item in ("bash_network",) for item in reasons):
        return reasons
    return []


def trial_dict_is_success(trial: dict[str, Any]) -> bool:
    return int(trial.get("success", 0) or 0) == 1 and str(trial.get("outcome") or "") == "success"


def recompute_trial_success_flag(trial: dict[str, Any]) -> int:
    """Same success bit as claude.run_batch trial finalization (before outcome override)."""
    copy_rc = trial.get("copy_rc")
    if copy_rc is not None and int(copy_rc) != 0:
        return 0
    if int(trial.get("copy_timed_out", 0) or 0):
        return 0
    if trial.get("skip_reason") is not None:
        return 0
    if int(trial.get("run_timed_out", 0) or 0):
        return 0
    skip_hits = trial.get("skip_keyword_hits")
    if skip_hits:
        return 0
    if int(trial.get("theorem_modified", 0) or 0):
        return 0
    if trial.get("skip_reason") is None:
        if int(trial.get("verify_make_timed_out", 0) or 0):
            return 0
        verify_rc = trial.get("verify_make_rc")
        if verify_rc is not None and int(verify_rc) != 0:
            return 0
    return 1
