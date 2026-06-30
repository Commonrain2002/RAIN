#!/usr/bin/env python3
"""
Cobble ProofAgent batch evaluation entrypoint.

Implementation lives in Evaluation/cobble/run_batch.py.
Use --extra-read to include extraReadableRootPaths in proofagent.config.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_COBBLE_PROOFAGENT_DIR = Path(__file__).resolve().parent
_EVAL_COBBLE_DIR = _EVAL_COBBLE_PROOFAGENT_DIR.parent

if str(_EVAL_COBBLE_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_COBBLE_DIR))

from run_batch import main


if __name__ == "__main__":
    raise SystemExit(main())
