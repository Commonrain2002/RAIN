"""Evaluation workspace paths."""

from __future__ import annotations

import os
import time
from pathlib import Path


def _workspace_root() -> Path:
    raw = os.environ.get("RAIN_EVAL_WORKSPACE", ".rain-eval-workspaces").strip()
    return Path(raw or ".rain-eval-workspaces").expanduser()


COQ_TEST_ROOT = _workspace_root()
AGENT_WORKSPACE_PROOFAGENT = COQ_TEST_ROOT / "AgentTest"
AGENT_WORKSPACE_OPENCODE = COQ_TEST_ROOT / "AgentTest_opencode"
AGENT_WORKSPACE_CLAUDE = COQ_TEST_ROOT / "AgentTest_claude"
AGENT_WORKSPACE_CODEX = COQ_TEST_ROOT / "AgentTest_codex"


def make_batch_workspace_stamp() -> str:
    """Return a month-day-hour-minute batch stamp."""
    t = time.localtime()
    return f"{t.tm_mon}-{t.tm_mday}-{t.tm_hour:02d}-{t.tm_min:02d}_batch"


def trial_workspace_parent(workspace_batch_dir: Path, id_value: int, trial_index: int) -> Path:
    return (workspace_batch_dir / f"id_{id_value}" / f"trial_{trial_index:03d}").resolve()
