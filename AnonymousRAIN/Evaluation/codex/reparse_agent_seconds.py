#!/usr/bin/env python3
"""Backfill agent_run_seconds on Codex trial result.json only (no summary flush)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from BatchTest.agent_run_seconds_backfill import AgentBackend, backfill_result_tree


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--result-dir",
        type=Path,
        default=None,
        help="Default: Evaluation/codex/Result/",
    )
    ap.add_argument(
        "--codex-home",
        type=Path,
        default=None,
        help="Override CODEX_HOME (default: ~/.codex)",
    )
    ap.add_argument(
        "--run-timeout-seconds",
        type=int,
        default=1800,
        help="Written for agent_timeout trials with run_rc=124",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    result_base = (args.result_dir or (Path(__file__).resolve().parent / "Result")).resolve()
    if not result_base.is_dir():
        print(f"No directory: {result_base}", file=sys.stderr)
        return 2

    updated, skipped = backfill_result_tree(
        result_base,
        AgentBackend.Codex,
        codex_home=args.codex_home,
        run_timeout_seconds=int(args.run_timeout_seconds),
        dry_run=bool(args.dry_run),
    )
    print(f"done | updated={updated} skipped={skipped} result_base={result_base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
