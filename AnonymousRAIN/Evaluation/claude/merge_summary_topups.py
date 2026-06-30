#!/usr/bin/env python3
"""Merge Claude batch results: replace agent_error/cheat slots from later batches."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from copy import deepcopy
from collections import defaultdict
from pathlib import Path
from typing import Any

_EVAL_CLAUDE_DIR = Path(__file__).resolve().parent
if str(_EVAL_CLAUDE_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_CLAUDE_DIR))

from run_batch import _aggregate_trial_stats, _flush_summary

INVALID_OUTCOMES = frozenset({"agent_error", "cheat"})


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
) -> list[dict[str, str]]:
    pool = list(replacement_pool)
    merged: list[dict[str, str]] = []
    for row in base_trials:
        outcome = (row.get("outcome") or "").strip()
        if outcome not in INVALID_OUTCOMES:
            merged.append(dict(row))
            continue
        chosen: dict[str, str] | None = None
        while pool:
            candidate = pool.pop(0)
            chosen = candidate
            if (candidate.get("outcome") or "").strip() not in INVALID_OUTCOMES:
                break
        merged.append(dict(chosen if chosen is not None else row))
    return merged


def _is_invalid_outcome(row: dict[str, Any], invalid_outcomes: frozenset[str]) -> bool:
    return (str(row.get("outcome") or "").strip() in invalid_outcomes)


def _load_result_dir(result_dir: Path, source_index: int) -> dict[int, dict[str, Any]]:
    summary_json = result_dir / "summary.json"
    if not summary_json.is_file():
        raise FileNotFoundError(f"Missing {summary_json}")
    entries = json.loads(summary_json.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"{summary_json} is not a list")

    loaded: dict[int, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        id_value = int(entry["id"])
        copied = deepcopy(entry)
        trials = copied.get("trials")
        if isinstance(trials, list):
            for trial in trials:
                if not isinstance(trial, dict):
                    continue
                trial["_merge_source_dir"] = str(result_dir)
                trial["_merge_source_index"] = source_index
                trial["_merge_original_trial"] = trial.get("trial")
        loaded[id_value] = copied
    return loaded


def _merge_id_trial_dicts(
    *,
    id_value: int,
    base_trials: list[dict[str, Any]],
    replacement_pool: list[dict[str, Any]],
    repeats: int,
    invalid_outcomes: frozenset[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pool = [deepcopy(row) for row in replacement_pool]
    merged: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    for output_trial, row in enumerate(base_trials, start=1):
        base_row = deepcopy(row)
        base_outcome = str(base_row.get("outcome") or "").strip()
        if base_outcome not in invalid_outcomes:
            chosen = base_row
            chosen.setdefault("_merge_source_dir", str(chosen.get("artifacts_dir") or ""))
            chosen.setdefault("_merge_source_index", 0)
            chosen.setdefault("_merge_original_trial", row.get("trial"))
        else:
            chosen = None
            skipped_invalid: list[str] = []
            while pool:
                candidate = pool.pop(0)
                chosen = candidate
                if not _is_invalid_outcome(candidate, invalid_outcomes):
                    break
                skipped_invalid.append(str(candidate.get("outcome") or ""))
            if chosen is None:
                chosen = base_row
            chosen = deepcopy(chosen)
            chosen["merge_replaced_outcome"] = base_outcome
            chosen["merge_replaced_trial"] = row.get("trial")
            manifest.append(
                {
                    "id": id_value,
                    "merged_trial": output_trial,
                    "base_trial": row.get("trial"),
                    "base_outcome": base_outcome,
                    "base_tokens_total": row.get("tokens_total"),
                    "replacement_source_index": chosen.get("_merge_source_index", 0),
                    "replacement_source_dir": chosen.get("_merge_source_dir", ""),
                    "replacement_original_trial": chosen.get("_merge_original_trial", chosen.get("trial")),
                    "replacement_outcome": chosen.get("outcome", ""),
                    "replacement_tokens_total": chosen.get("tokens_total"),
                    "skipped_invalid_candidates": ";".join(skipped_invalid),
                }
            )

        chosen["id"] = id_value
        chosen["trial"] = output_trial
        chosen["repeats"] = repeats
        merged.append(chosen)
    return merged, manifest


def merge_result_dirs(
    result_dirs: list[Path],
    *,
    invalid_outcomes: frozenset[str] = INVALID_OUTCOMES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not result_dirs:
        raise ValueError("At least one result directory is required")
    loaded = [_load_result_dir(path, idx) for idx, path in enumerate(result_dirs)]
    base_by_id = loaded[0]
    merged_entries: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []

    for id_value in sorted(base_by_id):
        base_entry = deepcopy(base_by_id[id_value])
        base_trials = base_entry.get("trials")
        if not isinstance(base_trials, list):
            merged_entries.append(base_entry)
            continue
        base_trials = [row for row in base_trials if isinstance(row, dict)]
        base_trials.sort(key=lambda row: int(row.get("trial", 0) or 0))
        pool: list[dict[str, Any]] = []
        for extra in loaded[1:]:
            entry = extra.get(id_value)
            if not entry:
                continue
            trials = entry.get("trials")
            if not isinstance(trials, list):
                continue
            pool.extend(row for row in trials if isinstance(row, dict))
        pool.sort(key=lambda row: (int(row.get("_merge_source_index", 0) or 0), int(row.get("trial", 0) or 0)))

        repeats = int(base_entry.get("repeats") or len(base_trials) or 1)
        merged_trials, id_manifest = _merge_id_trial_dicts(
            id_value=id_value,
            base_trials=base_trials,
            replacement_pool=pool,
            repeats=repeats,
            invalid_outcomes=invalid_outcomes,
        )
        base_entry["trials"] = merged_trials
        base_entry["repeats"] = repeats
        stats = _aggregate_trial_stats(merged_trials)
        base_entry.update(stats)
        base_entry["elapsed_seconds"] = stats["elapsed_seconds_sum"]
        base_entry["any_trial_success"] = 1 if stats["success_count"] > 0 else 0
        base_entry["success"] = 1 if stats["success_count"] == repeats and repeats > 0 else 0
        merged_entries.append(base_entry)
        manifest_rows.extend(id_manifest)

    return merged_entries, manifest_rows


def _write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "merged_trial",
        "base_trial",
        "base_outcome",
        "base_tokens_total",
        "replacement_source_index",
        "replacement_source_dir",
        "replacement_original_trial",
        "replacement_outcome",
        "replacement_tokens_total",
        "skipped_invalid_candidates",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def merge_summaries(summary_paths: list[Path]) -> tuple[list[str], list[dict[str, str]]]:
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
        id_merged = _merge_id_rows(base_by_id[id_value], pool)
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
        help="Ordered base batch first, then top-up batches.",
    )
    ap.add_argument(
        "--result-dir",
        type=Path,
        action="append",
        help="Ordered base result directory first, then top-up result directories.",
    )
    ap.add_argument("--out", type=Path, default=None, help="Merged summary.csv path.")
    ap.add_argument("--out-dir", type=Path, default=None, help="Merged result directory path.")
    ap.add_argument("--manifest", type=Path, default=None, help="Replacement manifest CSV path.")
    args = ap.parse_args()

    if args.result_dir:
        result_dirs = [p.resolve() for p in args.result_dir]
        for path in result_dirs:
            if not path.is_dir():
                print(f"Missing: {path}", file=sys.stderr)
                return 2
        if args.out_dir is None:
            print("--out-dir is required with --result-dir", file=sys.stderr)
            return 2
        merged_entries, manifest_rows = merge_result_dirs(result_dirs)
        out_dir = args.out_dir.resolve()
        _flush_summary(out_dir, merged_entries, log_line=False, total_planned=len(merged_entries))
        manifest_path = (args.manifest or (out_dir / "merge_manifest.csv")).resolve()
        _write_manifest(manifest_path, manifest_rows)
        trial_count = sum(len(r.get("trials", [])) for r in merged_entries if isinstance(r.get("trials"), list))
        invalid_left = sum(
            1
            for entry in merged_entries
            for row in (entry.get("trials") or [])
            if isinstance(row, dict) and _is_invalid_outcome(row, INVALID_OUTCOMES)
        )
        print(
            f"Merged {len(result_dirs)} result dirs | ids={len(merged_entries)} | rows={trial_count} | "
            f"replacements={len(manifest_rows)} | invalid_remaining={invalid_left} | -> {out_dir}",
            flush=True,
        )
        print(f"Replacement manifest -> {manifest_path}", flush=True)
        return 0

    if not args.summary_csv or args.out is None:
        print("Use --result-dir ... --out-dir ... or --summary-csv ... --out ...", file=sys.stderr)
        return 2

    paths = [p.resolve() for p in args.summary_csv]
    for path in paths:
        if not path.is_file():
            print(f"Missing: {path}", file=sys.stderr)
            return 2

    fieldnames, merged_rows = merge_summaries(paths)
    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged_rows)

    invalid_left = sum(
        1 for row in merged_rows if (row.get("outcome") or "").strip() in INVALID_OUTCOMES
    )
    print(
        f"Merged {len(paths)} summaries | rows={len(merged_rows)} | "
        f"ids={len({r['id'] for r in merged_rows})} | invalid_remaining={invalid_left} | -> {out_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
