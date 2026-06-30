#!/usr/bin/env python3
"""Backfill token fields in trial result.json from Claude session JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from claude_token_log import resolve_claude_token_usage
from run_batch import _aggregate_trial_stats, _flush_summary


def _iter_trial_dirs(result_base: Path) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for pattern in ("id_*/trial_*", "*/id_*/trial_*"):
        for path in sorted(result_base.glob(pattern)):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
    return sorted(out, key=lambda p: str(p))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_trial_results(id_dir: Path) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    for trial_json in sorted(id_dir.glob("trial_*/result.json")):
        try:
            data = json.loads(trial_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            trials.append(data)
    trials.sort(key=lambda item: int(item.get("trial", 0) or 0))
    return trials


def refresh_result_dir_summaries(result_dir: Path) -> int:
    """Refresh per-id aggregate files and batch summaries from trial result.json files."""
    id_results: list[dict[str, Any]] = []
    for id_dir in sorted(result_dir.glob("id_*"), key=lambda p: p.name):
        if not id_dir.is_dir():
            continue
        trials = _load_trial_results(id_dir)
        if not trials:
            result_path = id_dir / "result.json"
            if result_path.is_file():
                try:
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(result, dict):
                    id_results.append(result)
            continue

        aggregate_path = id_dir / "aggregate.json"
        result_path = id_dir / "result.json"
        aggregate: dict[str, Any] = {}
        for path in (aggregate_path, result_path):
            if not path.is_file():
                continue
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(loaded, dict):
                aggregate = loaded
                break

        first = trials[0]
        aggregate.setdefault("id", first.get("id"))
        aggregate.setdefault("project", first.get("project"))
        aggregate.setdefault("steps", first.get("steps"))
        aggregate.setdefault("target_coq_file", first.get("target_coq_file"))
        aggregate["trials"] = trials
        repeats = int(aggregate.get("repeats") or first.get("repeats") or len(trials))
        aggregate["repeats"] = repeats
        aggregate.update(_aggregate_trial_stats(trials))
        aggregate["any_trial_success"] = 1 if aggregate["success_count"] > 0 else 0
        aggregate["success"] = 1 if aggregate["success_count"] == repeats and repeats > 0 else 0

        _write_json(aggregate_path, aggregate)
        _write_json(result_path, aggregate)
        id_results.append(aggregate)

    if id_results:
        _flush_summary(result_dir, id_results, log_line=False, total_planned=len(id_results))
    return len(id_results)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--result-dir",
        type=Path,
        action="append",
        help="Result directory to reparse. May be repeated. Defaults to Evaluation/claude/Result.",
    )
    ap.add_argument(
        "--refresh-summary",
        action="store_true",
        help="Refresh aggregate.json/result.json and summary files after reparsing trial tokens.",
    )
    args = ap.parse_args()

    result_bases = [p.resolve() for p in args.result_dir] if args.result_dir else [_EVAL_DIR / "Result"]
    missing = [p for p in result_bases if not p.is_dir()]
    if missing:
        for path in missing:
            print(f"No directory: {path}", file=sys.stderr)
        return 2

    trial_dirs: list[Path] = []
    for result_base in result_bases:
        trial_dirs.extend(_iter_trial_dirs(result_base))
    if not trial_dirs:
        print(f"No trial dirs under: {', '.join(str(p) for p in result_bases)}", file=sys.stderr)
        return 2
    updated = 0
    for trial_dir in trial_dirs:
        stdout_path = trial_dir / "run_stdout.log"
        result_path = trial_dir / "result.json"
        sid_path = trial_dir / "claude_session_id.txt"
        if not result_path.is_file():
            continue
        data = json.loads(result_path.read_text(encoding="utf-8"))
        repo_dir_raw = str(data.get("repo_dir") or "").strip()
        repo_dir = Path(repo_dir_raw)
        session_id = ""
        if sid_path.is_file():
            session_id = sid_path.read_text(encoding="utf-8").strip()
        if not session_id:
            session_id = str(data.get("claude_session_id") or "").strip()
        if not session_id or not repo_dir_raw:
            continue
        err_path = trial_dir / "run_stderr.log"
        err = err_path.read_text(encoding="utf-8", errors="replace") if err_path.is_file() else ""
        out = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.is_file() else ""
        parsed = resolve_claude_token_usage(
            out,
            err,
            repo_dir=repo_dir,
            session_id=session_id,
        )
        if parsed.source == "none":
            continue
        data["tokens_prompt"] = parsed.prompt
        data["tokens_prompt_cache_hit"] = parsed.prompt_cache_hit
        data["tokens_prompt_cache_miss"] = parsed.prompt_cache_miss
        data["tokens_completion"] = parsed.completion
        data["tokens_reasoning"] = parsed.reasoning
        data["tokens_total"] = parsed.total
        data["tokens_parse_source"] = parsed.source
        data["claude_session_id"] = session_id
        result_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        updated += 1
        print(
            f"updated {trial_dir.relative_to(_EVAL_DIR)} total={parsed.total} source={parsed.source}",
        )
    if args.refresh_summary:
        for result_base in result_bases:
            n = refresh_result_dir_summaries(result_base)
            print(f"refreshed summaries {result_base} | ids={n}")
    print(f"done | updated {updated} trial(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
