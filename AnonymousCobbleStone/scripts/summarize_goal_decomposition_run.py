#!/usr/bin/env python3
"""
Summarize a goal-decomposition evaluation run from per-example *.json state files.

Official results.csv only reflects the final callback proof; search may succeed while
CSV still shows failure. This script uses the same proof extraction as the codebase
(get_proof_and_num_samples) for a consistent count.

Usage (from repo root, cobble env):
  python scripts/summarize_goal_decomposition_run.py PATH/to/run-dir
  python scripts/summarize_goal_decomposition_run.py PATH/to/run-dir --compare-csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategy.goal_decomposition.utils import (  # noqa: E402
    get_num_expanded_nodes,
    get_proof_and_num_samples,
)


@dataclass
class ExampleSummary:
    stem: str
    has_proof: bool
    proof_preview: str
    num_llm_samples: int
    num_hammer_calls: int
    nodes_expanded: Optional[int]
    csv_status: Optional[str]
    mismatch: bool


def load_csv_status(run_dir: Path) -> dict[str, str]:
    csv_path = run_dir / "results.csv"
    if not csv_path.exists():
        return {}
    out: dict[str, str] = {}
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("lemma_name", "").strip()
            status = row.get("successful", "").strip()
            if name:
                out[name] = status
    return out


def lemma_name_from_stem(stem: str) -> str:
    """buchberger-BuchAux.v-zerop_dec -> zerop_dec"""
    if "-" not in stem:
        return stem
    return stem.rsplit("-", 1)[-1]


RUN_METADATA_JSON = frozenset({"usage.json", "example_wall_times.json"})


def is_goal_decomposition_state(state: object) -> bool:
    if not isinstance(state, dict):
        return False
    return "root_uuid" in state and "config" in state and "nodes" in state


def summarize_run(run_dir: Path, compare_csv: bool) -> list[ExampleSummary]:
    if not run_dir.is_dir():
        raise FileNotFoundError(f"not a directory: {run_dir}")

    csv_by_lemma = load_csv_status(run_dir) if compare_csv else {}

    json_paths = sorted(
        p
        for p in run_dir.glob("*.json")
        if p.is_file() and p.name not in RUN_METADATA_JSON
    )

    summaries: list[ExampleSummary] = []
    for path in json_paths:
        if path.stat().st_size == 0:
            print(
                f"skip {path.name}: empty file (run may still be writing)",
                file=sys.stderr,
            )
            continue
        try:
            with path.open() as f:
                state = json.load(f)
        except json.JSONDecodeError as e:
            print(f"skip {path.name}: invalid JSON ({e})", file=sys.stderr)
            continue

        if not is_goal_decomposition_state(state):
            continue

        proof, sample_info = get_proof_and_num_samples(state)
        has_proof = proof is not None
        preview = ""
        if proof is not None:
            text = proof.pretty_print()
            preview = text if len(text) <= 120 else text[:117] + "..."

        try:
            expanded = get_num_expanded_nodes(state)
        except (KeyError, TypeError):
            expanded = None

        lemma = lemma_name_from_stem(path.stem)
        csv_status = csv_by_lemma.get(lemma)
        if csv_status is None and compare_csv:
            csv_status = csv_by_lemma.get(path.stem)

        mismatch = False
        if compare_csv and csv_status is not None:
            csv_ok = csv_status.lower() == "success"
            mismatch = has_proof != csv_ok

        summaries.append(
            ExampleSummary(
                stem=path.stem,
                has_proof=has_proof,
                proof_preview=preview,
                num_llm_samples=sample_info["num_llm_samples"],
                num_hammer_calls=sample_info["num_hammer_calls"],
                nodes_expanded=expanded,
                csv_status=csv_status,
                mismatch=mismatch,
            )
        )

    return summaries


def print_report(run_dir: Path, summaries: list[ExampleSummary], compare_csv: bool) -> None:
    proved = sum(1 for s in summaries if s.has_proof)
    total = len(summaries)
    print(f"run directory: {run_dir.resolve()}")
    print(f"json proof found: {proved} / {total}")
    if compare_csv:
        mismatches = [s for s in summaries if s.mismatch]
        print(f"csv vs json mismatches: {len(mismatches)}")
    print()

    if not summaries:
        print("(no per-example *.json files found)")
        return

    header = ["example", "json_proof", "expanded", "llm", "hammer", "proof_preview"]
    if compare_csv:
        header.extend(["csv", "mismatch"])
    widths = [max(len(h), 12) for h in header]

    def row(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths))

    print(row(header))
    print(row(["-" * w for w in widths]))

    for s in summaries:
        cells = [
            s.stem,
            "yes" if s.has_proof else "no",
            str(s.nodes_expanded if s.nodes_expanded is not None else "?"),
            str(s.num_llm_samples),
            str(s.num_hammer_calls),
            s.proof_preview.replace("\n", " "),
        ]
        if compare_csv:
            cells.append(s.csv_status or "-")
            cells.append("!" if s.mismatch else "")
        print(row(cells))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize goal decomposition run from *.json state files."
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Evaluation run directory (contains *.json and results.csv)",
    )
    parser.add_argument(
        "--compare-csv",
        action="store_true",
        help="Compare json proof vs results.csv and flag mismatches",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_out",
        help="Print machine-readable JSON summary on stdout",
    )
    args = parser.parse_args()

    summaries = summarize_run(args.run_dir, compare_csv=args.compare_csv)

    if args.json_out:
        payload = {
            "run_dir": str(args.run_dir.resolve()),
            "proved": sum(1 for s in summaries if s.has_proof),
            "total": len(summaries),
            "examples": [
                {
                    "stem": s.stem,
                    "has_proof": s.has_proof,
                    "proof_preview": s.proof_preview,
                    "num_llm_samples": s.num_llm_samples,
                    "num_hammer_calls": s.num_hammer_calls,
                    "nodes_expanded": s.nodes_expanded,
                    "csv_status": s.csv_status,
                    "mismatch": s.mismatch,
                }
                for s in summaries
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_report(args.run_dir, summaries, args.compare_csv)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
