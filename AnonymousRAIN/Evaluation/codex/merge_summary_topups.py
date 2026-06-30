#!/usr/bin/env python3
"""Merge Codex batch summary.csv files chronologically into one wide summary_trials table.

Only ``agent_error`` slots are replaced from later batches; other outcomes are kept.
The first partial batch (one trial per id) is prepended when present. Remaining slots
are filled from later trials up to ``--target-trials`` (default 10).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_EVAL_CODEX_DIR = Path(__file__).resolve().parent
_EVAL_CLAUDE_DIR = _EVAL_CODEX_DIR.parent / "claude"
if str(_EVAL_CLAUDE_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_CLAUDE_DIR))

from merge_summary_topups import _load_by_id  # noqa: E402

AGENT_ERROR_OUTCOME = "agent_error"

_SUMMARY_TRIALS_WIDE_ID_COLS = [
    "id",
    "project",
    "target_coq_file",
    "repeats",
    "steps",
]

_SUMMARY_TRIALS_WIDE_AGG_COLS = [
    "success_count",
    "success_rate",
    "any_trial_success",
    "success",
    "elapsed_seconds",
    "elapsed_seconds_sum",
    "tokens_total_sum",
    "tokens_total_min",
    "tokens_total_max",
]

_SUMMARY_TRIALS_WIDE_TRIAL_METRICS = [
    "success",
    "outcome",
    "outcome_detail",
    "elapsed_seconds",
    "agent_run_seconds",
    "tokens_prompt",
    "tokens_prompt_cache_hit",
    "tokens_prompt_cache_miss",
    "tokens_completion",
    "tokens_total",
    "post_copy_make_ok",
    "theorem_baseline_ok",
    "theorem_modified",
    "run_rc",
    "run_timed_out",
]


def _trial_fingerprint(row: dict[str, str]) -> tuple[str, ...]:
    return (
        (row.get("elapsed_seconds") or "").strip(),
        (row.get("tokens_total") or "").strip(),
        (row.get("outcome") or "").strip(),
        (row.get("agent_run_seconds") or "").strip(),
    )


def _aggregate_trial_stats(trials: list[dict[str, Any]]) -> dict[str, Any]:
    success_count = sum(1 for t in trials if int(t.get("success", 0) or 0) == 1)
    n = len(trials)
    totals = [t.get("tokens_total") for t in trials if t.get("tokens_total") not in (None, "")]
    elapsed = [int(t.get("elapsed_seconds", 0) or 0) for t in trials]
    return {
        "trial_count": n,
        "success_count": success_count,
        "success_rate": (success_count / n) if n else 0.0,
        "elapsed_seconds_sum": sum(elapsed),
        "elapsed_seconds_min": min(elapsed) if elapsed else None,
        "elapsed_seconds_max": max(elapsed) if elapsed else None,
        "tokens_total_sum": sum(int(x) for x in totals) if totals else None,
        "tokens_total_min": min(int(x) for x in totals) if totals else None,
        "tokens_total_max": max(int(x) for x in totals) if totals else None,
    }


def _csv_detail_cell(value: Any, max_len: int = 220) -> str:
    s = "" if value is None else str(value)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _format_csv_cell(value: Any, *, detail: bool = False) -> str:
    if detail:
        s = _csv_detail_cell(value)
    else:
        s = "" if value is None else str(value)
    s = s.replace('"', '""')
    if "," in s or "\n" in s or '"' in s:
        s = '"' + s + '"'
    return s


def _merge_id_rows_agent_error_only(
    base_trials: list[dict[str, str]],
    replacement_pool: list[dict[str, str]],
) -> list[dict[str, str]]:
    pool = list(replacement_pool)
    merged: list[dict[str, str]] = []
    for row in base_trials:
        outcome = (row.get("outcome") or "").strip()
        if outcome != AGENT_ERROR_OUTCOME:
            merged.append(dict(row))
            continue
        chosen: dict[str, str] | None = None
        while pool:
            candidate = pool.pop(0)
            chosen = candidate
            if (candidate.get("outcome") or "").strip() != AGENT_ERROR_OUTCOME:
                break
        merged.append(dict(chosen if chosen is not None else row))
    return merged


def _merge_summary_csv_layers(summary_paths: list[Path]) -> tuple[list[str], list[dict[str, str]]]:
    if not summary_paths:
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
        id_merged = _merge_id_rows_agent_error_only(base_by_id[id_value], pool)
        repeats = base_by_id[id_value][0].get("repeats", "10")
        for trial_index, row in enumerate(id_merged, start=1):
            row["id"] = str(id_value)
            row["trial"] = str(trial_index)
            row["repeats"] = str(repeats)
            merged_rows.append(row)

    return fieldnames, merged_rows


def merge_codex_batch_summaries(
    summary_paths: list[Path],
    *,
    target_trials: int,
) -> tuple[list[str], list[dict[str, str]]]:
    """Merge ordered batch summaries (earliest first) into one trial list per id."""
    if len(summary_paths) < 2:
        raise ValueError("At least two summary.csv paths are required")

    loaded = [_load_by_id(path) for path in summary_paths]
    primary_idx = max(range(len(loaded)), key=lambda index: len(loaded[index]))
    primary_path = summary_paths[primary_idx]
    later_paths = [summary_paths[index] for index in range(primary_idx + 1, len(summary_paths))]
    if later_paths:
        _, merged_primary_rows = _merge_summary_csv_layers([primary_path, *later_paths])
    else:
        _, merged_primary_rows = _merge_summary_csv_layers([primary_path])

    merged_by_id: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in merged_primary_rows:
        merged_by_id[int(row["id"])].append(dict(row))
    for id_value in merged_by_id:
        merged_by_id[id_value].sort(key=lambda item: int(item["trial"]))

    all_ids = sorted(set().union(*(data.keys() for data in loaded)))
    earliest = loaded[0]

    fieldnames: list[str] | None = None
    for data in loaded:
        if data:
            sample_id = next(iter(data))
            fieldnames = list(data[sample_id][0].keys())
            break
    if fieldnames is None:
        raise ValueError("No trial rows found in summaries")

    out_rows: list[dict[str, str]] = []
    for id_value in all_ids:
        trials = list(merged_by_id.get(id_value, []))
        prefix = list(earliest.get(id_value, [])) if primary_idx > 0 else []
        if prefix:
            trials = prefix + trials

        seen = {_trial_fingerprint(row) for row in trials}
        topup_pool: list[dict[str, str]] = []
        for index, data in enumerate(loaded):
            if index == primary_idx:
                continue
            for row in data.get(id_value, []):
                outcome = (row.get("outcome") or "").strip()
                if outcome == AGENT_ERROR_OUTCOME:
                    continue
                if index == 0 and prefix:
                    continue
                topup_pool.append(dict(row))

        for candidate in topup_pool:
            if len(trials) >= target_trials:
                break
            fp = _trial_fingerprint(candidate)
            if fp in seen:
                continue
            trials.append(candidate)
            seen.add(fp)

        trials = trials[:target_trials]
        for trial_index, row in enumerate(trials, start=1):
            row["id"] = str(id_value)
            row["trial"] = str(trial_index)
            row["repeats"] = str(target_trials)
            out_rows.append(row)

    return fieldnames, out_rows


def _build_id_results(trial_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_id: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in trial_rows:
        by_id[int(row["id"])].append(dict(row))

    id_results: list[dict[str, Any]] = []
    for id_value in sorted(by_id):
        trials = by_id[id_value]
        trials.sort(key=lambda item: int(item["trial"]))
        first = trials[0]
        stats = _aggregate_trial_stats(trials)
        id_repeats = len(trials)
        all_trials_ok = stats["success_count"] == id_repeats and id_repeats > 0
        id_results.append(
            {
                "id": id_value,
                "project": first.get("project"),
                "steps": first.get("steps"),
                "target_coq_file": first.get("target_coq_file"),
                "repeats": id_repeats,
                "trials": trials,
                **stats,
                "elapsed_seconds": stats["elapsed_seconds_max"],
                "any_trial_success": 1 if stats["success_count"] > 0 else 0,
                "success": 1 if all_trials_ok else 0,
            }
        )
    return id_results


def _write_summary_csv(path: Path, trial_rows: list[dict[str, str]]) -> None:
    cols = [
        "id",
        "trial",
        "repeats",
        "target_coq_file",
        "project",
        "steps",
        "success",
        "outcome",
        "outcome_detail",
        "post_copy_make_ok",
        "theorem_baseline_ok",
        "theorem_modified",
        "post_make_note",
        "elapsed_seconds",
        "agent_run_seconds",
        "tokens_prompt",
        "tokens_prompt_cache_hit",
        "tokens_prompt_cache_miss",
        "tokens_completion",
        "tokens_total",
    ]
    lines = [",".join(cols)]
    for row in trial_rows:
        cells = []
        for col in cols:
            value = row.get(col, "")
            if col == "outcome_detail":
                cells.append(_format_csv_cell(value, detail=True))
            else:
                cells.append(_format_csv_cell(value))
        lines.append(",".join(cells))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_by_id_csv(path: Path, id_results: list[dict[str, Any]]) -> None:
    cols = [
        "id",
        "project",
        "target_coq_file",
        "repeats",
        "trial_count",
        "success_count",
        "success_rate",
        "any_trial_success",
        "elapsed_seconds",
        "elapsed_seconds_sum",
        "tokens_total_sum",
        "tokens_total_min",
        "tokens_total_max",
        "success",
    ]
    lines = [",".join(cols)]
    for row in id_results:
        cells = [_format_csv_cell(row.get(col, "")) for col in cols]
        lines.append(",".join(cells))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_trials_wide_csv(path: Path, id_results: list[dict[str, Any]]) -> None:
    max_repeats = max(int(r.get("repeats") or 0) for r in id_results) if id_results else 1
    trial_cols: list[str] = []
    for trial_index in range(1, max_repeats + 1):
        prefix = f"trial_{trial_index}_"
        for metric in _SUMMARY_TRIALS_WIDE_TRIAL_METRICS:
            trial_cols.append(prefix + metric)

    cols = list(_SUMMARY_TRIALS_WIDE_ID_COLS) + list(_SUMMARY_TRIALS_WIDE_AGG_COLS) + trial_cols
    lines = [",".join(cols)]
    for row in id_results:
        cells: list[str] = []
        for col in _SUMMARY_TRIALS_WIDE_ID_COLS:
            cells.append(_format_csv_cell(row.get(col)))
        for col in _SUMMARY_TRIALS_WIDE_AGG_COLS:
            cells.append(_format_csv_cell(row.get(col)))

        trials_by_index: dict[int, dict[str, Any]] = {}
        trials = row.get("trials")
        if isinstance(trials, list):
            for trial in trials:
                if not isinstance(trial, dict):
                    continue
                try:
                    index = int(trial.get("trial", 0))
                except (TypeError, ValueError):
                    continue
                if index > 0:
                    trials_by_index[index] = trial

        for trial_index in range(1, max_repeats + 1):
            trial = trials_by_index.get(trial_index, {})
            for metric in _SUMMARY_TRIALS_WIDE_TRIAL_METRICS:
                cells.append(
                    _format_csv_cell(trial.get(metric), detail=(metric == "outcome_detail"))
                )
        lines.append(",".join(cells))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--result-dir",
        type=Path,
        action="append",
        required=True,
        help="Ordered batch folders (earliest first), each containing summary.csv.",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Output folder for merged summary.csv and summary_trials.csv.",
    )
    ap.add_argument(
        "--target-trials",
        type=int,
        default=10,
        help="Trials per theorem id after merge (default: 10).",
    )
    args = ap.parse_args()

    summary_paths = [(directory.resolve() / "summary.csv") for directory in args.result_dir]
    for path in summary_paths:
        if not path.is_file():
            print(f"Missing: {path}", file=sys.stderr)
            return 2

    fieldnames, trial_rows = merge_codex_batch_summaries(
        summary_paths,
        target_trials=int(args.target_trials),
    )
    id_results = _build_id_results(trial_rows)

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_summary_csv(out_dir / "summary.csv", trial_rows)
    _write_summary_by_id_csv(out_dir / "summary_by_id.csv", id_results)
    _write_summary_trials_wide_csv(out_dir / "summary_trials.csv", id_results)
    (out_dir / "summary.json").write_text(
        json.dumps(id_results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    invalid_left = sum(
        1 for row in trial_rows if (row.get("outcome") or "").strip() == AGENT_ERROR_OUTCOME
    )
    ids = {row["id"] for row in trial_rows}
    trials_per_id = len(trial_rows) // len(ids) if ids else 0
    print(
        f"Merged {len(summary_paths)} batches | ids={len(ids)} | "
        f"trial_rows={len(trial_rows)} (~{trials_per_id}/id) | "
        f"invalid_remaining={invalid_left} | -> {out_dir / 'summary_trials.csv'}",
        flush=True,
    )
    return 0 if invalid_left == 0 and len(ids) == 100 and len(trial_rows) == 1000 else 0


if __name__ == "__main__":
    raise SystemExit(main())
