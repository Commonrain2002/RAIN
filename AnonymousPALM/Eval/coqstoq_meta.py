#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from coqstoq import Split, get_theorem, num_theorems

_THEOREM_NAME_RE = re.compile(
    r"(?:Program\s+)?(?:Theorem|Lemma|Corollary|Fact|Remark|Proposition|Example)\s+"
    r"([A-Za-z_][A-Za-z0-9_']*)",
    re.IGNORECASE,
)


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
    p = theorem.project
    return coqstoq_loc / p.split.dir_name / p.dir_name


def _column_exclusive_end(column_raw: int) -> int | None:
    return None if column_raw <= 0 else column_raw + 1


def _extract_coq_text_span(
    lines: list[str],
    start_line0: int,
    start_col0: int,
    end_line0: int,
    end_col0_raw: int,
) -> str:
    if not lines or start_line0 < 0 or end_line0 < 0 or start_line0 > end_line0:
        return ""
    start_line0 = min(start_line0, len(lines) - 1)
    end_line0 = min(end_line0, len(lines) - 1)
    end_col_excl = _column_exclusive_end(end_col0_raw)
    parts: list[str] = []
    for line_index in range(start_line0, end_line0 + 1):
        line = lines[line_index]
        if line_index == start_line0 and line_index == end_line0:
            start_col = max(0, min(start_col0, len(line)))
            if end_col_excl is None:
                parts.append(line[start_col:])
            else:
                end_col = max(start_col, min(end_col_excl, len(line)))
                parts.append(line[start_col:end_col])
        elif line_index == start_line0:
            start_col = max(0, min(start_col0, len(line)))
            parts.append(line[start_col:])
        elif line_index == end_line0:
            if end_col_excl is None:
                parts.append(line)
            else:
                end_col = max(0, min(end_col_excl, len(line)))
                parts.append(line[:end_col])
        else:
            parts.append(line)
    return "\n".join(parts)


def _theorem_name_from_eval_thm(thm, workspace_root: Path) -> str | None:
    vfile = (workspace_root / thm.path).resolve()
    if not vfile.is_file():
        return None
    lines = vfile.read_text(encoding="utf-8", errors="replace").splitlines()
    ts = thm.theorem_start_pos
    te = thm.theorem_end_pos
    stmt = _extract_coq_text_span(lines, ts.line, ts.column, te.line, te.column)
    stmt_one_line = " ".join(stmt.split())
    m = _THEOREM_NAME_RE.search(stmt_one_line)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract CoqStoq meta for a theorem id as one-line JSON.")
    ap.add_argument("--id", type=int, required=True, help="CoqStoq theorem id")
    ap.add_argument(
        "--split",
        type=str,
        default="test",
        help="CoqStoq split: test | validation | cutoff (default: test)",
    )
    ap.add_argument(
        "--coqstoq-path",
        type=Path,
        default=None,
        help="COQSTOQ_PATH override (default: env COQSTOQ_PATH)",
    )
    args = ap.parse_args()

    coqstoq_path = args.coqstoq_path
    if coqstoq_path is None:
        raw = os.environ.get("COQSTOQ_PATH")
        if not raw:
            print("ERROR: COQSTOQ_PATH is not set; pass --coqstoq-path or export COQSTOQ_PATH.", file=sys.stderr)
            return 2
        coqstoq_path = Path(raw)
    coqstoq_path = coqstoq_path.resolve()
    if not coqstoq_path.is_dir():
        print(f"ERROR: CoqStoq root does not exist: {coqstoq_path}", file=sys.stderr)
        return 2

    try:
        sp = _split_from_arg(args.split)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    tid = int(args.id)
    n = num_theorems(sp, coqstoq_path)
    if tid < 0 or tid >= n:
        print(f"ERROR: theorem id out of range: {tid} (split has {n} entries)", file=sys.stderr)
        return 3

    thm = get_theorem(sp, tid, coqstoq_path)
    root = _workspace_root(coqstoq_path, thm)

    ts = thm.theorem_start_pos
    te = thm.theorem_end_pos
    ps = thm.proof_start_pos
    pe = thm.proof_end_pos
    theorem_name = _theorem_name_from_eval_thm(thm, root)

    payload = {
        "id": tid,
        "split": args.split.strip().lower(),
        "project": str(thm.project.dir_name),
        "step_count": max(0, int(pe.line) - int(ps.line)),
        "workspace_root": str(root),
        "v_rel_path": str(thm.path),
        "theorem_span": [int(ts.line), int(ts.column), int(te.line), int(te.column)],
        "proof_span": [int(ps.line), int(ps.column), int(pe.line), int(pe.column)],
        "theorem_name": theorem_name,
    }

    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
