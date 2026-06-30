"""Backfill agent_run_seconds on trial result.json (no summary flush)."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

AgentRunSecondsSource = Literal[
    "agent_subprocess_wall",
    "claude_duration_ms",
    "codex_session_jsonl_timestamps",
    "opencode_session_db",
    "opencode_stdout_timestamps",
    "proofagent_proof_run_log",
    "run_timeout_cap",
]


class AgentBackend(str, Enum):
    OpenCode = "opencode"
    Claude = "claude"
    ProofAgent = "proofagent"
    Codex = "codex"


@dataclass(frozen=True)
class AgentRunSecondsEstimate:
    seconds: int
    source: AgentRunSecondsSource


def iter_trial_dirs(result_base: Path) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in sorted(result_base.glob("**/id_*/trial_*")):
        if not path.is_dir():
            continue
        if not path.name.startswith("trial_"):
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return sorted(out, key=lambda p: str(p))


def measure_agent_subprocess_seconds(agent_t0: float) -> int:
    return max(0, int(time.monotonic() - agent_t0))


def apply_measured_agent_run_seconds(
    trial_result: dict[str, Any],
    *,
    agent_t0: float | None,
) -> None:
    """Record wall time of the agent ``timeout ...`` subprocess (copy/verify excluded)."""
    if agent_t0 is None:
        return
    trial_result["agent_run_seconds"] = measure_agent_subprocess_seconds(agent_t0)
    trial_result["agent_run_seconds_source"] = "agent_subprocess_wall"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _is_success_trial(data: dict[str, Any]) -> bool:
    return int(data.get("success", 0) or 0) == 1


def _is_agent_timeout_trial(data: dict[str, Any]) -> bool:
    if str(data.get("outcome") or "") != "agent_timeout":
        return False
    try:
        run_rc = int(data.get("run_rc", -1))
    except (TypeError, ValueError):
        run_rc = -1
    return run_rc == 124


def _hms_span_seconds(start_hms: str, end_hms: str) -> int:
    fmt = "%H:%M:%S"
    t0 = datetime.strptime(start_hms, fmt)
    t1 = datetime.strptime(end_hms, fmt)
    delta = (t1 - t0).total_seconds()
    if delta < 0:
        delta += 24 * 3600
    return int(round(delta))


def _parse_claude_duration(stdout: str) -> AgentRunSecondsEstimate | None:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        raw_ms = payload.get("duration_ms")
        if raw_ms is None:
            continue
        try:
            ms = int(raw_ms)
        except (TypeError, ValueError):
            continue
        if ms < 0:
            continue
        return AgentRunSecondsEstimate(int(round(ms / 1000)), "claude_duration_ms")
    return None


def _parse_opencode_stdout_timestamps(stdout: str) -> AgentRunSecondsEstimate | None:
    timestamps: list[int] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        raw = payload.get("timestamp")
        if isinstance(raw, int):
            timestamps.append(raw)
    if len(timestamps) < 2:
        return None
    span_ms = max(timestamps) - min(timestamps)
    if span_ms < 0:
        return None
    return AgentRunSecondsEstimate(int(round(span_ms / 1000)), "opencode_stdout_timestamps")


def _default_opencode_db_path() -> Path:
    return Path.home() / ".local/share/opencode/opencode.db"


def _parse_opencode_session_db(session_id: str, db_path: Path | None = None) -> AgentRunSecondsEstimate | None:
    sid = session_id.strip()
    if not sid.startswith("ses_"):
        return None
    path = db_path if db_path is not None else _default_opencode_db_path()
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            "SELECT time_created, time_updated FROM session WHERE id = ?",
            (sid,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None:
        return None
    created, updated = int(row[0] or 0), int(row[1] or 0)
    if updated < created:
        return None
    span_ms = updated - created
    if span_ms <= 0:
        return None
    return AgentRunSecondsEstimate(int(round(span_ms / 1000)), "opencode_session_db")


def _extract_session_id_from_opencode_stdout(stdout: str) -> str | None:
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        sid = payload.get("sessionID")
        if isinstance(sid, str) and sid.startswith("ses_"):
            return sid
    return None


def _parse_opencode_success(
    trial_dir: Path,
    data: dict[str, Any],
    db_path: Path | None,
) -> AgentRunSecondsEstimate | None:
    stdout_path = trial_dir / "run_stdout.log"
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.is_file() else ""
    session_id = str(data.get("opencode_session_id") or "").strip()
    if not session_id:
        session_id = _extract_session_id_from_opencode_stdout(stdout) or ""
    if session_id:
        from_db = _parse_opencode_session_db(session_id, db_path=db_path)
        if from_db is not None:
            return from_db
    if stdout.strip():
        return _parse_opencode_stdout_timestamps(stdout)
    return None


def _load_codex_token_log():
    eval_root = Path(__file__).resolve().parents[1]
    codex_dir = str(eval_root / "codex")
    if codex_dir not in sys.path:
        sys.path.insert(0, codex_dir)
    import codex_token_log

    return codex_token_log


def _read_codex_thread_id(trial_dir: Path, data: dict[str, Any]) -> str:
    thread_id = str(data.get("codex_thread_id") or "").strip()
    if thread_id:
        return thread_id
    thread_path = trial_dir / "codex_thread_id.txt"
    if thread_path.is_file():
        return thread_path.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _parse_codex_success(
    trial_dir: Path,
    data: dict[str, Any],
    codex_home: Path | None,
) -> AgentRunSecondsEstimate | None:
    stdout_path = trial_dir / "run_stdout.log"
    stderr_path = trial_dir / "run_stderr.log"
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.is_file() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.is_file() else ""
    thread_id = _read_codex_thread_id(trial_dir, data)
    codex_token_log = _load_codex_token_log()
    seconds = codex_token_log.resolve_codex_agent_run_seconds(
        stdout,
        stderr,
        thread_id=thread_id or None,
        codex_home=codex_home,
    )
    if seconds is None:
        return None
    return AgentRunSecondsEstimate(seconds, "codex_session_jsonl_timestamps")


def _parse_proofagent_proof_run_log(stdout: str) -> AgentRunSecondsEstimate | None:
    start_hms: str | None = None
    end_hms: str | None = None
    hms_re = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
    for line in stdout.splitlines():
        m = hms_re.match(line)
        if not m:
            continue
        hms = m.group(1)
        if "proof_run start" in line:
            start_hms = hms
        if "proof_run done:" in line:
            end_hms = hms
    if start_hms is None or end_hms is None:
        return None
    return AgentRunSecondsEstimate(_hms_span_seconds(start_hms, end_hms), "proofagent_proof_run_log")


def estimate_agent_run_seconds(
    backend: AgentBackend,
    trial_dir: Path,
    data: dict[str, Any],
    *,
    opencode_db_path: Path | None = None,
    codex_home: Path | None = None,
    run_timeout_seconds: int = 1800,
) -> AgentRunSecondsEstimate | None:
    if _is_agent_timeout_trial(data):
        return AgentRunSecondsEstimate(int(run_timeout_seconds), "run_timeout_cap")

    if not _is_success_trial(data):
        return None

    stdout_path = trial_dir / "run_stdout.log"
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.is_file() else ""

    if backend == AgentBackend.Claude:
        if not stdout.strip():
            return None
        return _parse_claude_duration(stdout)

    if backend == AgentBackend.OpenCode:
        return _parse_opencode_success(trial_dir, data, opencode_db_path)

    if backend == AgentBackend.ProofAgent:
        if not stdout.strip():
            return None
        return _parse_proofagent_proof_run_log(stdout)

    if backend == AgentBackend.Codex:
        return _parse_codex_success(trial_dir, data, codex_home)

    return None


def backfill_trial_result_json(
    trial_dir: Path,
    backend: AgentBackend,
    *,
    opencode_db_path: Path | None = None,
    codex_home: Path | None = None,
    run_timeout_seconds: int = 1800,
    dry_run: bool = False,
) -> AgentRunSecondsEstimate | None:
    result_path = trial_dir / "result.json"
    if not result_path.is_file():
        return None
    data = _read_json(result_path)
    estimate = estimate_agent_run_seconds(
        backend,
        trial_dir,
        data,
        opencode_db_path=opencode_db_path,
        codex_home=codex_home,
        run_timeout_seconds=run_timeout_seconds,
    )
    if estimate is None:
        return None
    if not dry_run:
        data["agent_run_seconds"] = estimate.seconds
        data["agent_run_seconds_source"] = estimate.source
        _write_json(result_path, data)
    return estimate


def backfill_result_tree(
    result_base: Path,
    backend: AgentBackend,
    *,
    opencode_db_path: Path | None = None,
    codex_home: Path | None = None,
    run_timeout_seconds: int = 1800,
    dry_run: bool = False,
) -> tuple[int, int]:
    trial_dirs = iter_trial_dirs(result_base)
    updated = 0
    skipped = 0
    for trial_dir in trial_dirs:
        estimate = backfill_trial_result_json(
            trial_dir,
            backend,
            opencode_db_path=opencode_db_path,
            codex_home=codex_home,
            run_timeout_seconds=run_timeout_seconds,
            dry_run=dry_run,
        )
        if estimate is None:
            skipped += 1
            continue
        updated += 1
        action = "would update" if dry_run else "updated"
        print(
            f"{action} {trial_dir.relative_to(result_base)} "
            f"agent_run_seconds={estimate.seconds} source={estimate.source}",
        )
    return updated, skipped
