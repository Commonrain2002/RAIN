#!/usr/bin/env python3
"""
ProofAgent batch evaluation entrypoint.

This script reuses the existing BatchTest implementation but lives under Evaluation/
so all evaluations share a unified folder layout.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from BatchTest.run_batch import main


if __name__ == "__main__":
    raise SystemExit(main())

