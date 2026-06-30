#!/usr/bin/env python3
"""Parcas Claude Code batch evaluation (DeepSeek via Claude CLI)."""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_PARCAS_DIR = Path(__file__).resolve().parents[1]
if str(_EVAL_PARCAS_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_PARCAS_DIR))

from parcas_run_batch_external_agent import main


if __name__ == "__main__":
    raise SystemExit(main("claude"))
