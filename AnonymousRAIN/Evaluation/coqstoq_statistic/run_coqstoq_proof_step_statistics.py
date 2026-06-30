#!/usr/bin/env python3
"""
Aggregate CoqStoq reference proof step counts (vsrocq sentences between Proof. and Qed./Defined.).

Uses ``Sentence/vsrocq_split_sentences_CS2`` first; on split/count failure retries with
``vsrocq_split_sentences_CoqStoq``. Counts are taken from the upstream project tree (read-only).

Outputs under --output-dir (default: Evaluation/coqstoq_statistic/out/<split>):
  id_step_count.csv
  step_distribution.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "Evaluation"
_COQSTOQ_STAT_DIR = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))
if str(_COQSTOQ_STAT_DIR) not in sys.path:
    sys.path.insert(0, str(_COQSTOQ_STAT_DIR))

from coqstoq import Split, get_theorem, num_theorems  # noqa: E402

from BatchTest.theorem_integrity import run_split_sentences  # noqa: E402
from coqstoq_step_count import count_coqstoq_proof_sentences  # noqa: E402


def _split_from_arg(name: str) -> Split:
    n = name.strip().lower()
    if n in ("test",):
        return Split.TEST
    if n in ("val", "validation"):
        return Split.VAL
    if n in ("cutoff",):
        return Split.CUTOFF
    raise ValueError(f"unknown split: {name!r} (use: test, validation, cutoff)")


def _workspace_root(coqstoq_loc: Path, theorem) -> Path:
    project = theorem.project
    return coqstoq_loc / project.split.dir_name / project.dir_name


def _sentence_split_binary(name: str) -> str:
    path = (_REPO_ROOT / "Sentence" / name).resolve()
    if path.is_file():
        return str(path)
    return name


def _default_parse_script() -> str:
    return _sentence_split_binary("vsrocq_split_sentences_CS2")


def _coqstoq_parse_script() -> str:
    return _sentence_split_binary("vsrocq_split_sentences_CoqStoq")


def _parse_script_chain(explicit_primary: str | None) -> list[str]:
    coqstoq_script = _coqstoq_parse_script()
    if explicit_primary is not None:
        primary = explicit_primary.strip()
        if primary == coqstoq_script:
            return [primary]
        return [primary, coqstoq_script]
    return [_default_parse_script(), coqstoq_script]


def _resolve_coqstoq_path(raw: Path | None) -> Path:
    if raw is not None:
        path = raw.expanduser().resolve()
    else:
        env = os.environ.get("COQSTOQ_PATH")
        if not env:
            raise ValueError("COQSTOQ_PATH is not set; pass --coqstoq-path or export COQSTOQ_PATH.")
        path = Path(env).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"CoqStoq root does not exist: {path}")
    return path


@dataclass(frozen=True)
class _WorkerConfig:
    coqstoq_path: str
    split_name: str
    parse_sentence_scripts: tuple[str, ...]
    parse_timeout_seconds: int


def _split_error_detail(
    split_rc: int,
    split_err: str,
    split_err_msg: str | None,
) -> str:
    detail = split_err_msg or f"exit {split_rc}"
    if split_err:
        detail = f"{detail}: {split_err[:200]}"
    return detail


def _count_theorem_steps(
    theorem,
    sentences: list[dict[str, Any]],
) -> tuple[int | None, str | None, str | None]:
    ts = theorem.theorem_start_pos
    te = theorem.theorem_end_pos
    ps = theorem.proof_start_pos
    return count_coqstoq_proof_sentences(
        sentences,
        theorem_start_line=int(ts.line),
        theorem_start_column=int(ts.column),
        theorem_end_line=int(te.line),
        theorem_end_column=int(te.column),
        proof_start_line=int(ps.line),
        proof_start_column=int(ps.column),
    )


def _worker_count_one(theorem_id: int, cfg: _WorkerConfig) -> dict[str, Any]:
    coqstoq_loc = Path(cfg.coqstoq_path)
    split = _split_from_arg(cfg.split_name)
    try:
        theorem = get_theorem(split, theorem_id, coqstoq_loc)
    except Exception as exc:
        return {
            "id": theorem_id,
            "step_count": None,
            "error": f"get_theorem: {exc}",
        }

    root = _workspace_root(coqstoq_loc, theorem)
    v_rel = str(theorem.path)
    v_abs = (root / v_rel).resolve()
    if not v_abs.is_file():
        return {
            "id": theorem_id,
            "step_count": None,
            "project": theorem.project.dir_name,
            "v_rel_path": v_rel,
            "theorem_name": None,
            "error": f"missing v file: {v_abs}",
        }

    last_error: str | None = None
    for script_index, parse_script in enumerate(cfg.parse_sentence_scripts):
        split_rc, _, split_err, timed_out, sentences, split_err_msg = run_split_sentences(
            root,
            parse_script,
            v_abs,
            cfg.parse_timeout_seconds,
        )
        if timed_out:
            last_error = f"parse_sentence_script timed out ({parse_script})"
            continue
        if split_err_msg or sentences is None or split_rc != 0:
            last_error = _split_error_detail(split_rc, split_err, split_err_msg)
            last_error = f"{last_error} [{parse_script}]"
            continue

        step_count, theorem_name, count_error = _count_theorem_steps(theorem, sentences)
        if count_error is None and step_count is not None:
            return {
                "id": theorem_id,
                "step_count": step_count,
                "project": theorem.project.dir_name,
                "v_rel_path": v_rel,
                "theorem_name": theorem_name,
                "error": None,
            }

        if count_error:
            last_error = count_error
            if script_index + 1 < len(cfg.parse_sentence_scripts):
                continue
            return {
                "id": theorem_id,
                "step_count": step_count,
                "project": theorem.project.dir_name,
                "v_rel_path": v_rel,
                "theorem_name": theorem_name,
                "error": count_error,
            }

    return {
        "id": theorem_id,
        "step_count": None,
        "project": theorem.project.dir_name,
        "v_rel_path": v_rel,
        "theorem_name": None,
        "error": last_error or "parse_sentence_script failed",
    }


def _write_id_table(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["id", "step_count", "project", "v_rel_path", "theorem_name", "error"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _write_distribution_table(path: Path, step_counts: list[int]) -> None:
    total = len(step_counts)
    hist = Counter(step_counts)
    cumulative = 0
    fieldnames = ["step_count", "problem_count", "fraction", "cumulative_count", "cumulative_fraction"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for step in sorted(hist.keys()):
            count = hist[step]
            cumulative += count
            fraction = count / total if total else 0.0
            cumulative_fraction = cumulative / total if total else 0.0
            writer.writerow(
                {
                    "step_count": step,
                    "problem_count": count,
                    "fraction": f"{fraction:.6f}",
                    "cumulative_count": cumulative,
                    "cumulative_fraction": f"{cumulative_fraction:.6f}",
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="CoqStoq proof-body sentence statistics.")
    ap.add_argument(
        "--split",
        type=str,
        default="test",
        help="CoqStoq split: test | validation | cutoff (default: test)",
    )
    ap.add_argument("--coqstoq-path", type=Path, default=None, help="Override COQSTOQ_PATH")
    ap.add_argument(
        "--parse-sentence-script",
        type=str,
        default=None,
        help=(
            "Primary vsrocq split command (default: CS2). "
            "On split/count failure, vsrocq_split_sentences_CoqStoq is tried next."
        ),
    )
    ap.add_argument("--parse-timeout-seconds", type=int, default=180)
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for CSV outputs (default: Evaluation/coqstoq_statistic/out/<split>)",
    )
    ap.add_argument("--workers", type=int, default=1, help="Parallel worker processes (default: 1)")
    ap.add_argument("--id-min", type=int, default=0, help="Inclusive minimum theorem id")
    ap.add_argument("--id-max", type=int, default=None, help="Exclusive maximum theorem id (default: split size)")
    ap.add_argument("--progress-every", type=int, default=50)
    args = ap.parse_args()

    try:
        coqstoq_path = _resolve_coqstoq_path(args.coqstoq_path)
        split = _split_from_arg(args.split)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    total_theorems = num_theorems(split, coqstoq_path)
    id_min = max(0, int(args.id_min))
    id_max = int(args.id_max) if args.id_max is not None else total_theorems
    id_max = min(id_max, total_theorems)
    if id_min >= id_max:
        print(f"ERROR: empty id range [{id_min}, {id_max})", file=sys.stderr)
        return 2

    script_chain = _parse_script_chain(
        args.parse_sentence_script.strip() if args.parse_sentence_script else None
    )
    out_dir = args.output_dir
    if out_dir is None:
        out_dir = _COQSTOQ_STAT_DIR / "out" / args.split.strip().lower()
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    worker_cfg = _WorkerConfig(
        coqstoq_path=str(coqstoq_path),
        split_name=args.split,
        parse_sentence_scripts=tuple(script_chain),
        parse_timeout_seconds=int(args.parse_timeout_seconds),
    )

    ids = list(range(id_min, id_max))
    results: list[dict[str, Any]] = []
    workers = max(1, int(args.workers))
    started = time.time()

    if workers == 1:
        for index, theorem_id in enumerate(ids):
            results.append(_worker_count_one(theorem_id, worker_cfg))
            if args.progress_every > 0 and (index + 1) % args.progress_every == 0:
                print(f"progress {index + 1}/{len(ids)}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_worker_count_one, tid, worker_cfg): tid for tid in ids}
            done = 0
            for future in as_completed(futures):
                results.append(future.result())
                done += 1
                if args.progress_every > 0 and done % args.progress_every == 0:
                    print(f"progress {done}/{len(ids)}", flush=True)

    results.sort(key=lambda row: int(row["id"]))
    ok_rows = [row for row in results if row.get("error") is None and row.get("step_count") is not None]
    step_counts = [int(row["step_count"]) for row in ok_rows]

    _write_id_table(out_dir / "id_step_count.csv", results)
    _write_distribution_table(out_dir / "step_distribution.csv", step_counts)

    errors = [row for row in results if row.get("error")]
    elapsed = time.time() - started
    print(
        f"done split={args.split} ids={id_min}..{id_max - 1} "
        f"ok={len(ok_rows)} errors={len(errors)} elapsed_s={elapsed:.1f} "
        f"out={out_dir}",
        flush=True,
    )
    if errors and len(errors) <= 20:
        for row in errors[:20]:
            print(f"  id={row['id']}: {row.get('error')}", flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
