#!/usr/bin/env python3
"""Build a per-id top-up testlist from a ProofAgent batch summary.csv.

Each entry repeats = agent_error trial count for that id, so a follow-up batch
can add non-agent_error trials toward 10 valid runs per id (merge with prior results).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path


def _load_outcomes(summary_csv: Path) -> dict[int, Counter[str]]:
    by_id: dict[int, Counter[str]] = {}
    with summary_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            id_value = int(row["id"])
            outcome = (row.get("outcome") or "").strip() or "unknown"
            by_id.setdefault(id_value, Counter())[outcome] += 1
    return by_id


def _build_retrial_specs_for_outcomes(
    by_id: dict[int, Counter[str]],
    outcomes: frozenset[str],
) -> list[dict[str, int]]:
    specs: list[dict[str, int]] = []
    for id_value in sorted(by_id):
        count = sum(int(by_id[id_value].get(outcome, 0)) for outcome in outcomes)
        if count > 0:
            specs.append({"id": id_value, "repeats": count})
    return specs


def _retrial_default_json_name(outcomes: frozenset[str]) -> str:
    ordered = sorted(outcomes)
    if len(ordered) == 1:
        return f"TestList_retrial_{ordered[0]}.json"
    return f"TestList_retrial_{'_and_'.join(ordered)}.json"


def _build_topup_specs(
    by_id: dict[int, Counter[str]],
    *,
    target_non_agent_error: int,
    invalid_outcomes: frozenset[str] | None = None,
) -> list[dict[str, int]]:
    invalid = invalid_outcomes if invalid_outcomes is not None else frozenset({"agent_error"})
    specs: list[dict[str, int]] = []
    for id_value in sorted(by_id):
        counts = by_id[id_value]
        valid = sum(count for key, count in counts.items() if key not in invalid)
        need = max(0, target_non_agent_error - valid)
        if need > 0:
            specs.append({"id": id_value, "repeats": need})
    return specs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--result-dir",
        type=Path,
        required=True,
        help="Batch folder containing summary.csv (e.g. Result/6-17-01-38_batch_ds_no_env_1).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: <result-dir>/TestList_topup.json).",
    )
    ap.add_argument(
        "--target-non-agent-error",
        type=int,
        default=10,
        help="Desired count of non-agent_error trials per id after merging batches (default: 10).",
    )
    ap.add_argument(
        "--invalid-outcomes",
        type=str,
        default="agent_error",
        help="Comma-separated outcomes that do not count toward valid trials (default: agent_error).",
    )
    ap.add_argument(
        "--manifest-csv",
        type=Path,
        default=None,
        help="Optional CSV: id,valid_count,invalid_breakdown,repeats.",
    )
    ap.add_argument(
        "--retrial-outcome",
        type=str,
        default=None,
        help=(
            "If set, each id repeats = trial rows with matching outcome(s). "
            "Comma-separated (e.g. agent_error or agent_error,cheat). "
            "Ignores --target-non-agent-error."
        ),
    )

    args = ap.parse_args()
    invalid_outcomes = frozenset(
        part.strip() for part in str(args.invalid_outcomes).split(",") if part.strip()
    )

    result_dir = args.result_dir.resolve()
    summary_csv = result_dir / "summary.csv"
    if not summary_csv.is_file():
        print(f"Missing summary.csv: {summary_csv}", file=sys.stderr)
        return 2

    by_id = _load_outcomes(summary_csv)
    retrial_parts = [
        part.strip()
        for part in str(args.retrial_outcome or "").split(",")
        if part.strip()
    ]
    if retrial_parts:
        retrial_outcomes = frozenset(retrial_parts)
        specs = _build_retrial_specs_for_outcomes(by_id, retrial_outcomes)
        default_name = _retrial_default_json_name(retrial_outcomes)
    else:
        specs = _build_topup_specs(
            by_id,
            target_non_agent_error=int(args.target_non_agent_error),
            invalid_outcomes=invalid_outcomes,
        )
        default_name = "TestList_topup.json"
    if not specs:
        print("No ids need top-up.", file=sys.stderr)
        return 0

    out_path = (args.out or (result_dir / default_name)).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(specs, indent=2) + "\n", encoding="utf-8")

    total_repeats = sum(entry["repeats"] for entry in specs)
    print(
        f"Wrote {len(specs)} ids, {total_repeats} trials -> {out_path}",
        flush=True,
    )

    manifest_path = args.manifest_csv
    if manifest_path is not None:
        manifest_path = manifest_path.resolve()
        lines = ["id,valid_count,invalid_outcomes,repeats"]
        for entry in specs:
            id_value = entry["id"]
            counts = by_id[id_value]
            valid = sum(c for k, c in counts.items() if k not in invalid_outcomes)
            invalid_parts = ";".join(f"{k}:{v}" for k, v in sorted(counts.items()) if k in invalid_outcomes)
            lines.append(f"{id_value},{valid},{invalid_parts},{entry['repeats']}")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Manifest -> {manifest_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
