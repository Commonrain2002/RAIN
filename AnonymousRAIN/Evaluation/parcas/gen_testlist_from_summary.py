#!/usr/bin/env python3
"""Build a fixed TestList.json from a Parcas batch summary.csv (e.g. retry agent_error ids)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent


def _collect_ids_from_summary(
    summary_path: Path,
    outcomes: frozenset[str],
) -> list[tuple[int, int]]:
    """Return sorted (id, repeats) from rows whose outcome is in ``outcomes``."""
    by_id: dict[int, int] = {}
    with summary_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "id" not in reader.fieldnames or "outcome" not in reader.fieldnames:
            raise ValueError(f"summary.csv missing id/outcome columns: {summary_path}")
        for row in reader:
            outcome = str(row.get("outcome") or "").strip()
            if outcome not in outcomes:
                continue
            id_value = int(row["id"])
            repeats_raw = str(row.get("repeats") or "1").strip()
            repeats = int(repeats_raw) if repeats_raw else 1
            if repeats < 1:
                repeats = 1
            by_id[id_value] = repeats
    return sorted(by_id.items(), key=lambda pair: pair[0])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--summary",
        type=Path,
        required=True,
        help="Path to batch Result/summary.csv.",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output TestList.json (default: <summary_dir>/TestList.<outcomes>.json).",
    )
    ap.add_argument(
        "--outcome",
        action="append",
        default=[],
        help="Outcome to include (repeatable). Default: agent_error.",
    )
    ap.add_argument(
        "--repeats",
        type=int,
        default=None,
        help="Override repeats for every id (default: use repeats column from summary).",
    )
    ap.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest path (default: <out>.manifest.json).",
    )
    args = ap.parse_args()

    summary_path = args.summary.resolve()
    if not summary_path.is_file():
        print(f"ERROR: summary not found: {summary_path}", file=sys.stderr)
        return 2

    outcome_set = frozenset(str(o).strip() for o in args.outcome if str(o).strip())
    if not outcome_set:
        outcome_set = frozenset({"agent_error"})

    try:
        id_repeats = _collect_ids_from_summary(summary_path, outcome_set)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not id_repeats:
        print(f"ERROR: no rows with outcome in {sorted(outcome_set)!r}", file=sys.stderr)
        return 1

    outcome_slug = "_".join(sorted(outcome_set))
    out_path = args.out
    if out_path is None:
        out_path = summary_path.parent / f"TestList.{outcome_slug}.json"
    out_path = out_path.resolve()

    override_repeats = args.repeats
    if override_repeats is not None and int(override_repeats) < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return 2

    testlist_specs = [
        {"id": id_value, "repeats": int(override_repeats) if override_repeats is not None else repeats}
        for id_value, repeats in id_repeats
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(testlist_specs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest_path = args.manifest.resolve() if args.manifest else out_path.with_suffix(".manifest.json")
    manifest_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "from_batch_summary",
        "source_summary": str(summary_path),
        "outcomes": sorted(outcome_set),
        "count": len(testlist_specs),
        "ids": [spec["id"] for spec in testlist_specs],
        "testlist": str(out_path),
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(testlist_specs)} ids -> {out_path}", flush=True)
    print(f"Manifest -> {manifest_path}", flush=True)
    print(f"ids: {[spec['id'] for spec in testlist_specs]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
