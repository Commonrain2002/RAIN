#!/usr/bin/env python3
"""Build per-id retrial testlist from an OpenCode batch summary.csv.

Retrial rows: agent_error, cheat, and agent_timeout with tokens_total below threshold.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_MIN_TIMEOUT_TOKENS = 3_000_000
DEFAULT_OUT_NAME = "TestList_retrial_agent_error_cheat_timeout_lt3m.json"


def _parse_tokens_total(row: dict[str, str]) -> int | None:
    raw = (row.get("tokens_total") or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def should_retrial_row(row: dict[str, str], *, min_timeout_tokens: int) -> bool:
    outcome = (row.get("outcome") or "").strip() or "unknown"
    if outcome in ("agent_error", "cheat"):
        return True
    if outcome == "agent_timeout":
        tokens = _parse_tokens_total(row)
        return tokens is None or tokens < min_timeout_tokens
    return False


def build_retrial_specs_from_rows(
    rows: list[dict[str, str]],
    *,
    min_timeout_tokens: int,
) -> tuple[list[dict[str, int]], Counter[str]]:
    per_id: Counter[int] = Counter()
    reason_counter: Counter[str] = Counter()
    for row in rows:
        if not should_retrial_row(row, min_timeout_tokens=min_timeout_tokens):
            continue
        id_value = int(row["id"])
        per_id[id_value] += 1
        outcome = (row.get("outcome") or "").strip()
        if outcome == "agent_timeout":
            reason_counter["agent_timeout_lt_tokens"] += 1
        else:
            reason_counter[outcome] += 1
    specs = [{"id": id_value, "repeats": count} for id_value, count in sorted(per_id.items())]
    return specs, reason_counter


def build_retrial_specs(
    summary_csv: Path,
    *,
    min_timeout_tokens: int,
) -> tuple[list[dict[str, int]], Counter[str]]:
    with summary_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return build_retrial_specs_from_rows(rows, min_timeout_tokens=min_timeout_tokens)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--result-dir",
        type=Path,
        default=None,
        help="Batch folder containing summary.csv (unless --merge-summary-csv is set).",
    )
    ap.add_argument(
        "--merge-summary-csv",
        type=Path,
        action="append",
        default=None,
        help="Repeatable; merge batches in order, then count retrial rows on merged trials.",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output JSON (default: <result-dir>/{DEFAULT_OUT_NAME}).",
    )
    ap.add_argument(
        "--min-timeout-tokens",
        type=int,
        default=DEFAULT_MIN_TIMEOUT_TOKENS,
        help="agent_timeout trials below this tokens_total count as retrial (default: 3000000).",
    )
    args = ap.parse_args()
    merge_paths = [p.resolve() for p in (args.merge_summary_csv or [])]
    min_timeout = int(args.min_timeout_tokens)

    if merge_paths:
        _eval_dir = Path(__file__).resolve().parents[1]
        if str(_eval_dir) not in sys.path:
            sys.path.insert(0, str(_eval_dir))
        from opencode.merge_summary_topups import merge_summaries

        for path in merge_paths:
            if not path.is_file():
                print(f"Missing summary.csv: {path}", file=sys.stderr)
                return 2
        _fieldnames, merged_rows = merge_summaries(merge_paths, min_timeout_tokens=min_timeout)
        specs, reasons = build_retrial_specs_from_rows(merged_rows, min_timeout_tokens=min_timeout)
        default_out_dir = merge_paths[-1].parent
    else:
        if args.result_dir is None:
            print("Provide --result-dir or --merge-summary-csv.", file=sys.stderr)
            return 2
        result_dir = args.result_dir.resolve()
        summary_csv = result_dir / "summary.csv"
        if not summary_csv.is_file():
            print(f"Missing summary.csv: {summary_csv}", file=sys.stderr)
            return 2
        specs, reasons = build_retrial_specs(summary_csv, min_timeout_tokens=min_timeout)
        default_out_dir = result_dir

    if not specs:
        print("No trials need retrial.", file=sys.stderr)
        return 0

    out_path = (args.out or (default_out_dir / DEFAULT_OUT_NAME)).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(specs, indent=2) + "\n", encoding="utf-8")

    total_repeats = sum(entry["repeats"] for entry in specs)
    reason_text = ", ".join(f"{key}={value}" for key, value in sorted(reasons.items()))
    print(
        f"Wrote {len(specs)} ids, {total_repeats} trials ({reason_text}) -> {out_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
