#!/usr/bin/env python3
"""Merge OpenCode batch summary.csv: replace invalid trials from later batches."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from opencode.gen_merged_testlist_topup import (
    DEFAULT_MIN_TIMEOUT_TOKENS,
    is_valid_trial_row,
)


def _load_by_id(summary_csv: Path) -> dict[int, list[dict[str, str]]]:
    by_id: dict[int, list[dict[str, str]]] = defaultdict(list)
    with summary_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            by_id[int(row["id"])].append(dict(row))
    for id_value in by_id:
        by_id[id_value].sort(key=lambda item: int(item["trial"]))
    return by_id


def _merge_id_rows(
    base_trials: list[dict[str, str]],
    replacement_pool: list[dict[str, str]],
    *,
    min_timeout_tokens: int,
) -> list[dict[str, str]]:
    pool = list(replacement_pool)
    merged: list[dict[str, str]] = []
    for row in base_trials:
        if is_valid_trial_row(row, min_timeout_tokens=min_timeout_tokens):
            merged.append(dict(row))
            continue
        chosen: dict[str, str] | None = None
        while pool:
            candidate = pool.pop(0)
            chosen = candidate
            if is_valid_trial_row(candidate, min_timeout_tokens=min_timeout_tokens):
                break
        merged.append(dict(chosen if chosen is not None else row))
    return merged


def merge_summaries(
    summary_paths: list[Path],
    *,
    min_timeout_tokens: int,
) -> tuple[list[str], list[dict[str, str]]]:
    if len(summary_paths) < 1:
        raise ValueError("At least one summary.csv path is required")

    fieldnames: list[str] | None = None
    loaded: list[dict[int, list[dict[str, str]]]] = []
    for path in summary_paths:
        rows_by_id = _load_by_id(path)
        loaded.append(rows_by_id)
        if fieldnames is None and rows_by_id:
            sample_id = next(iter(rows_by_id))
            fieldnames = list(rows_by_id[sample_id][0].keys())

    if fieldnames is None:
        raise ValueError("No rows in first summary")

    base_by_id = loaded[0]
    merged_rows: list[dict[str, str]] = []
    for id_value in sorted(base_by_id):
        pool: list[dict[str, str]] = []
        for extra in loaded[1:]:
            pool.extend(extra.get(id_value, []))
        id_merged = _merge_id_rows(
            base_by_id[id_value],
            pool,
            min_timeout_tokens=min_timeout_tokens,
        )
        repeats = base_by_id[id_value][0].get("repeats", "10")
        for trial_index, row in enumerate(id_merged, start=1):
            row["id"] = str(id_value)
            row["trial"] = str(trial_index)
            row["repeats"] = str(repeats)
            merged_rows.append(row)

    return fieldnames, merged_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--summary-csv",
        type=Path,
        action="append",
        required=True,
        help="Ordered base batch first, then top-up batches.",
    )
    ap.add_argument("--out", type=Path, required=True, help="Merged summary.csv path.")
    ap.add_argument(
        "--min-timeout-tokens",
        type=int,
        default=DEFAULT_MIN_TIMEOUT_TOKENS,
        help="agent_timeout trials below this tokens_total count as invalid slots.",
    )
    args = ap.parse_args()

    paths = [p.resolve() for p in args.summary_csv]
    for path in paths:
        if not path.is_file():
            print(f"Missing: {path}", file=sys.stderr)
            return 2

    min_timeout = int(args.min_timeout_tokens)
    fieldnames, merged_rows = merge_summaries(paths, min_timeout_tokens=min_timeout)
    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged_rows)

    invalid_left = sum(
        1
        for row in merged_rows
        if not is_valid_trial_row(row, min_timeout_tokens=min_timeout)
    )
    print(
        f"Merged {len(paths)} summaries | rows={len(merged_rows)} | "
        f"ids={len({r['id'] for r in merged_rows})} | invalid_remaining={invalid_left} | "
        f"min_timeout_tokens={min_timeout} | -> {out_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
