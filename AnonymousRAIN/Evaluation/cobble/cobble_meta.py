#!/usr/bin/env python3
"""Extract Cobble / PnVRocqLib meta for a TestList line id as one-line JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_EVAL_COBBLE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_COBBLE_DIR.parents[1]
_EVAL_DIR = _REPO_ROOT / "Evaluation"
if str(_EVAL_COBBLE_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_COBBLE_DIR))
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from BatchTest.theorem_integrity import run_split_sentences, sentence_text_is_proof_start

from cobble_testlist import parse_example_name, read_line_at, resolve_vfile

_THEOREM_VERNAC_TYPES = frozenset({"theorem", "lemma", "fact", "corollary", "proposition"})


def _sentence_end_to_minimal_copy_columns(end_column_exclusive: int) -> int:
    """Map split JSON end_column (0-based exclusive) to cobble_minimal_copy --theorem-end-column-raw."""
    if end_column_exclusive <= 0:
        return 0
    return end_column_exclusive - 1


def _find_target_proposition_sentence(
    sentences: list[dict[str, Any]],
    theorem_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    name_matches: list[int] = []
    for idx, sent in enumerate(sentences):
        vtype = str(sent.get("vernac_type") or "").strip().lower()
        name = str(sent.get("name") or "").strip()
        if name == theorem_name and vtype in _THEOREM_VERNAC_TYPES:
            name_matches.append(idx)

    if len(name_matches) == 1:
        prop_idx = name_matches[0]
    elif len(name_matches) == 0:
        raise ValueError(f"no sentence with name={theorem_name!r} and vernac_type in {_THEOREM_VERNAC_TYPES}")
    else:
        raise ValueError(f"ambiguous theorem name {theorem_name!r}: indices {name_matches}")

    if prop_idx + 1 >= len(sentences):
        raise ValueError(f"no sentence after theorem {theorem_name!r}")
    proof_sent = sentences[prop_idx + 1]
    proof_text = str(proof_sent.get("text") or "")
    if not sentence_text_is_proof_start(proof_text):
        raise ValueError(
            f"expected sentence starting with Proof after {theorem_name!r}, got: {proof_text!r}"
        )
    return sentences[prop_idx], proof_sent


def build_meta_payload(
    *,
    line_id: int,
    project_root: Path,
    testlist: Path,
    parse_sentence_script: str,
    parse_sentence_timeout_seconds: int,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    example_line = read_line_at(testlist, line_id)
    v_basename, theorem_name = parse_example_name(example_line)
    vfile_abs = resolve_vfile(project_root, v_basename)
    v_rel_path = vfile_abs.relative_to(project_root).as_posix()

    split_rc, _, split_err, split_timed_out, sentences, split_err_msg = run_split_sentences(
        project_root,
        parse_sentence_script,
        vfile_abs,
        parse_sentence_timeout_seconds,
    )
    if split_timed_out:
        raise RuntimeError("parse_sentence_script timed out")
    if split_rc != 0 or sentences is None:
        raise RuntimeError(split_err_msg or f"parse_sentence_script exit {split_rc}: {split_err[:500]}")

    prop_sent, proof_sent = _find_target_proposition_sentence(sentences, theorem_name)
    prop_text = str(prop_sent.get("text") or "").strip()
    if not prop_text:
        raise RuntimeError(f"empty proposition text for theorem {theorem_name!r}")

    end_line_one_based = int(prop_sent["end_line"])
    end_column_exclusive = int(prop_sent.get("end_column") or 0)
    theorem_end_line0 = end_line_one_based - 1
    theorem_end_column_raw = _sentence_end_to_minimal_copy_columns(end_column_exclusive)

    proof_start_line = int(proof_sent.get("start_line") or 0)
    proof_end_line = int(proof_sent.get("end_line") or 0)
    step_count = max(0, proof_end_line - proof_start_line)

    ts_line = int(prop_sent.get("start_line") or 0)
    ts_col = int(prop_sent.get("start_column") or 0)
    te_line = end_line_one_based
    te_col = end_column_exclusive

    return {
        "id": line_id,
        "split": "cobble",
        "project": project_root.name,
        "step_count": step_count,
        "workspace_root": str(project_root),
        "v_rel_path": v_rel_path,
        "theorem_span": [ts_line, ts_col, te_line, te_col],
        "proof_span": [
            int(proof_sent.get("start_line") or 0),
            int(proof_sent.get("start_column") or 0),
            int(proof_sent.get("end_line") or 0),
            int(proof_sent.get("end_column") or 0),
        ],
        "theorem_name": theorem_name,
        "example_name": example_line.strip(),
        "theorem_end_line0": theorem_end_line0,
        "theorem_end_column_raw": theorem_end_column_raw,
        "theorem_proposition_text": prop_text,
    }


def main() -> int:
    default_testlist = _EVAL_COBBLE_DIR / "TestList"
    default_parse = _REPO_ROOT / "Sentence" / "vsrocq_split_sentences_PnV"

    ap = argparse.ArgumentParser(description="Extract Cobble meta for a TestList line id as one-line JSON.")
    ap.add_argument("--id", type=int, required=True, help="1-based line number in TestList")
    ap.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("COBBLE_PROJECT_ROOT", ".")),
        help="PnVRocqLib repository root (Cobblestone coq-projects copy)",
    )
    ap.add_argument("--testlist", type=Path, default=default_testlist)
    ap.add_argument("--parse-sentence-script", type=str, default=str(default_parse))
    ap.add_argument("--parse-sentence-timeout-seconds", type=int, default=120)
    args = ap.parse_args()

    try:
        payload = build_meta_payload(
            line_id=int(args.id),
            project_root=args.project_root,
            testlist=args.testlist.resolve(),
            parse_sentence_script=str(args.parse_sentence_script),
            parse_sentence_timeout_seconds=int(args.parse_sentence_timeout_seconds),
        )
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
