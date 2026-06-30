#!/usr/bin/env python3
"""Build OpenCode top-up list from merged batch summaries (valid trial rules)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_MIN_TIMEOUT_TOKENS = 3_000_000
DEFAULT_TARGET_VALID = 10


def _parse_tokens_total(row: dict[str, str]) -> int | None:
    raw = (row.get("tokens_total") or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def is_valid_trial_row(row: dict[str, str], *, min_timeout_tokens: int) -> bool:
    outcome = (row.get("outcome") or "").strip() or "unknown"
    if outcome in ("agent_error", "cheat"):
        return False
    if outcome == "agent_timeout":
        tokens = _parse_tokens_total(row)
        if tokens is None or tokens < min_timeout_tokens:
            return False
    return True


def load_summary_rows(summary_csv: Path) -> list[dict[str, str]]:
    with summary_csv.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_topup_specs(
    merged_rows: list[dict[str, str]],
    *,
    target_valid: int,
    min_timeout_tokens: int,
) -> tuple[list[dict[str, int]], dict[int, Counter[str]], dict[int, int]]:
    by_id: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in merged_rows:
        by_id[int(row["id"])].append(row)

    valid_counts: dict[int, int] = {}
    outcome_by_id: dict[int, Counter[str]] = {}
    specs: list[dict[str, int]] = []

    for id_value in sorted(by_id):
        rows = by_id[id_value]
        outcomes = Counter((r.get("outcome") or "unknown").strip() for r in rows)
        outcome_by_id[id_value] = outcomes
        valid = sum(1 for r in rows if is_valid_trial_row(r, min_timeout_tokens=min_timeout_tokens))
        valid_counts[id_value] = valid
        need = max(0, target_valid - valid)
        if need > 0:
            specs.append({"id": id_value, "repeats": need})

    return specs, outcome_by_id, valid_counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--summary-csv",
        type=Path,
        action="append",
        required=True,
        help="Repeatable; merged in order (later files add trials for same id).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        action="append",
        required=True,
        help="Output JSON path(s); same count as --summary-csv or single path for all.",
    )
    ap.add_argument("--target-valid", type=int, default=DEFAULT_TARGET_VALID)
    ap.add_argument("--min-timeout-tokens", type=int, default=DEFAULT_MIN_TIMEOUT_TOKENS)
    ap.add_argument("--manifest-csv", type=Path, default=None)
    args = ap.parse_args()

    summary_paths = [p.resolve() for p in args.summary_csv]
    for path in summary_paths:
        if not path.is_file():
            print(f"Missing summary.csv: {path}", file=sys.stderr)
            return 2

    merged: list[dict[str, str]] = []
    for path in summary_paths:
        merged.extend(load_summary_rows(path))

    specs, outcome_by_id, valid_counts = build_topup_specs(
        merged,
        target_valid=int(args.target_valid),
        min_timeout_tokens=int(args.min_timeout_tokens),
    )

    out_paths = [p.resolve() for p in args.out]
    if len(out_paths) == 1:
        targets = [out_paths[0]] * len(summary_paths)
    elif len(out_paths) == len(summary_paths):
        targets = out_paths
    else:
        print("Provide one --out or the same number as --summary-csv", file=sys.stderr)
        return 2

    for out_path in dict.fromkeys(targets + out_paths):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(specs, indent=2) + "\n", encoding="utf-8")

    total_repeats = sum(entry["repeats"] for entry in specs)
    print(
        f"Merged {len(summary_paths)} batches | {len(valid_counts)} ids | "
        f"top-up {len(specs)} ids, {total_repeats} trials",
        flush=True,
    )
    for out_path in dict.fromkeys(out_paths):
        print(f"  -> {out_path}", flush=True)

    if args.manifest_csv is not None:
        manifest_path = args.manifest_csv.resolve()
        lines = ["id,valid_count,repeats,outcome_breakdown"]
        for entry in specs:
            id_value = entry["id"]
            breakdown = ";".join(f"{k}:{v}" for k, v in sorted(outcome_by_id[id_value].items()))
            lines.append(f"{id_value},{valid_counts[id_value]},{entry['repeats']},{breakdown}")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Manifest -> {manifest_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
