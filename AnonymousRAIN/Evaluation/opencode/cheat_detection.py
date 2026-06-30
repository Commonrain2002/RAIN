"""Detect obvious cheating in OpenCode batch trials (internet or external proof sources)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_EXTERNAL_ROOT_MARKERS = (
    "AgentTest",
    "evaluation workspace",
    "ProofAgent",
    "coqstoq",
)

_TMP_CHEAT_PATTERN = re.compile(
    r"/tmp/(?:original|codex|backup|.*proof|.*_backup|fix_proof|part\d|interp|split_backup|new_|clean_|temporary_path)",
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
    return any(marker in p for marker in _EXTERNAL_ROOT_MARKERS)


def _scan_bash_command(cmd: str, repo: str, reasons: list[str]) -> None:
    if re.search(r"https?://", cmd) or re.search(r"\b(curl|wget)\b", cmd, re.I):
        reasons.append("bash_network")
    if re.search(r"\bfind\b[^\n|]*evaluation workspace", cmd) or re.search(
        r"xargs\s+grep[^\n]*evaluation workspace|grep[^\n]*<RAIN_EVAL_WORKSPACE>",
        cmd,
    ):
        if _is_external_resource_path(cmd) and not _path_allowed(cmd, repo):
            reasons.append("bash_scan_coqtest")
    for match in re.finditer(r"(?:cp|cat|mv|sed|head|tail|wc)\s+([^\s;|&]+)", cmd):
        token = _normalize_path(match.group(1))
        if not token.startswith("/"):
            continue
        if _path_allowed(token, repo):
            continue
        if _is_external_resource_path(token):
            reasons.append(f"bash_external:{token[:120]}")
        elif _TMP_CHEAT_PATTERN.search(token):
            reasons.append(f"bash_tmp_copy:{token[:120]}")


def _scan_run_stdout_log(stdout_path: Path, repo_dir: Path) -> list[str]:
    reasons: list[str] = []
    if not stdout_path.is_file():
        return reasons
    repo = str(repo_dir.resolve()).replace("\\", "/").rstrip("/")
    text = stdout_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") != "tool_use":
            continue
        part = rec.get("part")
        if not isinstance(part, dict):
            continue
        tool = str(part.get("tool") or "").lower()
        state = part.get("state")
        if not isinstance(state, dict):
            continue
        inp = state.get("input")
        if not isinstance(inp, dict):
            inp = {}
        if tool in ("webfetch", "websearch"):
            reasons.append(f"tool:{tool}")
        if tool == "bash":
            _scan_bash_command(str(inp.get("command") or ""), repo, reasons)
        if tool in ("read", "grep", "glob", "list"):
            for key in ("filePath", "file_path", "path"):
                val = inp.get(key)
                if not isinstance(val, str) or not val.startswith("/"):
                    continue
                vp = _normalize_path(val)
                if _path_allowed(vp, repo):
                    continue
                if _is_external_resource_path(vp):
                    reasons.append(f"read_external:{vp[:120]}")
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
        "tool:web",
        "bash_network",
        "bash_scan_coqtest",
    )
    if any(item.startswith(hard_prefixes) for item in reasons):
        return reasons
    return []


def detect_cheat_reasons(
    *,
    trial_artifacts_dir: Path,
    repo_dir: Path,
) -> list[str]:
    stdout_path = trial_artifacts_dir / "run_stdout.log"
    if not repo_dir.is_dir():
        repo_text = ""
        result_path = trial_artifacts_dir / "result.json"
        if result_path.is_file():
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
                repo_text = str(data.get("repo_dir") or "")
            except json.JSONDecodeError:
                repo_text = ""
        if repo_text:
            repo_dir = Path(repo_text)
    return _scan_run_stdout_log(stdout_path, repo_dir)


def trial_dict_is_success(trial: dict[str, Any]) -> bool:
    return int(trial.get("success", 0) or 0) == 1 and str(trial.get("outcome") or "") == "success"


def recompute_trial_success_flag(trial: dict[str, Any]) -> int:
    """Same success bit as opencode.run_batch trial finalization (before outcome override)."""
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
