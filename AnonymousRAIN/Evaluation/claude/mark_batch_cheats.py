#!/usr/bin/env python3
"""Mark cheating success trials as outcome=cheat and refresh batch summaries + top-up list."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from claude.cheat_detection import (
    detect_cheat_reasons,
    recompute_trial_success_flag,
    trial_dict_is_success,
)
from claude.run_batch import _aggregate_trial_stats, _derive_outcome, _flush_summary


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _should_revert_cheat_trial(trial: dict[str, Any]) -> bool:
    return str(trial.get("outcome") or "") == "cheat" and recompute_trial_success_flag(trial) != 1


def _revert_cheat_if_not_success(trial: dict[str, Any], *, apply: bool) -> bool:
    if not _should_revert_cheat_trial(trial):
        return False
    if not apply:
        return True
    trial["success"] = 0
    trial["outcome"] = ""
    trial["outcome_detail"] = ""
    _derive_outcome(trial)
    return True


def _mark_trial_cheat(trial: dict[str, Any], reasons: list[str]) -> None:
    trial["success"] = 0
    trial["outcome"] = "cheat"
    trial["outcome_detail"] = ";".join(reasons)[:400]


def _rebuild_topup_cheat_only(
    marked_rows: list[tuple[int, int, str]],
    out_json: Path,
) -> None:
    """One new trial per formerly-successful cheat row (replaces invalidated success)."""
    per_id: Counter[int] = Counter()
    for id_value, _trial_index, _detail in marked_rows:
        per_id[id_value] += 1
    specs = [{"id": id_value, "repeats": per_id[id_value]} for id_value in sorted(per_id)]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(specs, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result-dir", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--cheat-report",
        type=Path,
        default=None,
        help="CSV of marked trials (default: <result-dir>/cheat_marked.csv).",
    )
    args = ap.parse_args()

    result_dir = args.result_dir.resolve()
    summary_path = result_dir / "summary.json"
    if not summary_path.is_file():
        print(f"Missing {summary_path}", file=sys.stderr)
        return 2

    id_results: list[dict[str, Any]] = json.loads(summary_path.read_text(encoding="utf-8"))
    marked_rows: list[tuple[int, int, str]] = []
    reverted_rows: list[tuple[int, int]] = []

    for id_entry in id_results:
        trials = id_entry.get("trials")
        if not isinstance(trials, list):
            continue
        for trial in trials:
            if not isinstance(trial, dict):
                continue
            if _revert_cheat_if_not_success(trial, apply=not args.dry_run):
                id_value = int(trial.get("id", 0))
                trial_index = int(trial.get("trial", 0))
                reverted_rows.append((id_value, trial_index))
                if not args.dry_run:
                    artifacts = Path(str(trial.get("artifacts_dir") or ""))
                    if not artifacts.is_dir():
                        candidate = result_dir / f"id_{id_value}" / f"trial_{trial_index:03d}"
                        if candidate.is_dir():
                            artifacts = candidate
                    trial_json = artifacts / "result.json"
                    if trial_json.is_file():
                        _write_json(trial_json, trial)
        for trial in trials:
            if not isinstance(trial, dict):
                continue
            if str(trial.get("outcome") or "") == "cheat":
                continue
            if not trial_dict_is_success(trial):
                continue
            artifacts = Path(str(trial.get("artifacts_dir") or ""))
            if not artifacts.is_dir():
                id_value = int(trial.get("id", 0))
                trial_index = int(trial.get("trial", 0))
                candidate = result_dir / f"id_{id_value}" / f"trial_{trial_index:03d}"
                if candidate.is_dir():
                    artifacts = candidate
            repo_dir = Path(str(trial.get("repo_dir") or ""))
            session_id = str(trial.get("claude_session_id") or "").strip()
            if not session_id:
                sid_file = artifacts / "claude_session_id.txt"
                if sid_file.is_file():
                    session_id = sid_file.read_text(encoding="utf-8").strip()
            reasons = detect_cheat_reasons(
                trial_artifacts_dir=artifacts,
                repo_dir=repo_dir,
                session_id=session_id,
            )
            if not reasons:
                continue
            id_value = int(trial.get("id", 0))
            trial_index = int(trial.get("trial", 0))
            marked_rows.append((id_value, trial_index, ";".join(reasons)))
            if args.dry_run:
                continue
            _mark_trial_cheat(trial, reasons)
            trial_json = artifacts / "result.json"
            if trial_json.is_file():
                _write_json(trial_json, trial)

        if args.dry_run:
            continue
        stats = _aggregate_trial_stats(trials)
        id_repeats = int(id_entry.get("repeats", len(trials)) or len(trials))
        id_entry["success"] = int(stats["success_count"] == id_repeats and id_repeats > 0)
        id_entry.update(stats)
        id_artifacts = result_dir / f"id_{id_entry['id']}"
        for path in (id_artifacts / "aggregate.json", id_artifacts / "result.json"):
            if path.is_file():
                _write_json(path, id_entry)

    report_path = (args.cheat_report or (result_dir / "cheat_marked.csv")).resolve()
    lines = ["id,trial,reasons"]
    for id_value, trial_index, detail in sorted(marked_rows):
        detail_escaped = detail.replace('"', '""')
        if "," in detail_escaped:
            detail_escaped = f'"{detail_escaped}"'
        lines.append(f"{id_value},{trial_index},{detail_escaped}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"cheat candidates: {len(marked_rows)} | report -> {report_path}")
    if reverted_rows:
        print(f"reverted cheat (non-success): {len(reverted_rows)}")
        for id_value, trial_index in sorted(reverted_rows):
            print(f"  id={id_value} trial={trial_index}")
    for id_value, trial_index, detail in marked_rows:
        print(f"  id={id_value} trial={trial_index} | {detail[:160]}")

    if args.dry_run or (not marked_rows and not reverted_rows):
        return 0

    if not marked_rows:
        _flush_summary(result_dir, id_results, log_line=True, total_planned=len(id_results))
        return 0

    _flush_summary(result_dir, id_results, log_line=True, total_planned=len(id_results))
    _rebuild_topup_cheat_only(marked_rows, result_dir / "TestList_topup.json")
    trial_total = len(marked_rows)
    id_total = len({row[0] for row in marked_rows})
    print(
        f"Refreshed TestList topup (cheat replacements only: {trial_total} trials, {id_total} ids)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
