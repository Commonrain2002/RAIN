#!/usr/bin/env python3
"""Backfill token fields in trial result.json and flush batch summary CSV."""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from run_batch import main_flush_tokens

if __name__ == "__main__":
    raise SystemExit(main_flush_tokens())
