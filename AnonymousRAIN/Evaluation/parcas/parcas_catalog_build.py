"""Build Parcas theorem catalog entries from vsrocq split output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sys

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
_EVAL_DIR = _REPO_ROOT / "Evaluation"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from BatchTest.theorem_integrity import (
    proof_body_line_count,
    run_split_sentences,
    sentence_text_is_proof_start,
)

from parcas_testlist import ParcasCatalogEntry, file_contains_abort

_THEOREM_VERNAC_TYPES = frozenset({"theorem", "lemma", "fact", "corollary", "proposition"})


def list_eligible_v_files(project_root: Path) -> list[Path]:
    src = project_root / "src"
    if not src.is_dir():
        raise ValueError(f"missing src/ under project root: {project_root}")
    files: list[Path] = []
    for v_path in sorted(src.rglob("*.v")):
        if file_contains_abort(v_path):
            continue
        rel = v_path.relative_to(project_root).as_posix()
        files.append(project_root / rel)
    return files


def collect_theorems_from_vfile(
    project_root: Path,
    v_rel_path: str,
    parse_sentence_script: str,
    parse_sentence_timeout_seconds: int,
) -> list[dict[str, Any]]:
    vfile_abs = (project_root / v_rel_path).resolve()
    if not vfile_abs.is_file():
        raise FileNotFoundError(vfile_abs)

    split_rc, _, split_err, split_timed_out, sentences, split_err_msg = run_split_sentences(
        project_root,
        parse_sentence_script,
        vfile_abs,
        parse_sentence_timeout_seconds,
    )
    if split_timed_out:
        raise RuntimeError(f"parse_sentence_script timed out: {v_rel_path}")
    if split_rc != 0 or sentences is None:
        raise RuntimeError(
            split_err_msg or f"parse_sentence_script exit {split_rc} for {v_rel_path}: {split_err[:400]}"
        )

    rows: list[dict[str, Any]] = []
    for idx, sent in enumerate(sentences):
        vtype = str(sent.get("vernac_type") or "").strip().lower()
        name = str(sent.get("name") or "").strip()
        if vtype not in _THEOREM_VERNAC_TYPES or not name:
            continue
        if idx + 1 >= len(sentences):
            continue
        proof_sent = sentences[idx + 1]
        proof_text = str(proof_sent.get("text") or "")
        if not sentence_text_is_proof_start(proof_text):
            continue
        step_count = proof_body_line_count(sentences, idx + 1)
        start_line = int(sent.get("start_line") or 0)
        rows.append(
            {
                "v_rel_path": v_rel_path,
                "theorem_name": name,
                "start_line": start_line,
                "step_count": step_count,
            }
        )
    return rows


def _step_count_for_theorem_in_sentences(
    sentences: list[dict[str, Any]],
    theorem_name: str,
) -> int | None:
    name_matches: list[int] = []
    for idx, sent in enumerate(sentences):
        vtype = str(sent.get("vernac_type") or "").strip().lower()
        name = str(sent.get("name") or "").strip()
        if name == theorem_name and vtype in _THEOREM_VERNAC_TYPES:
            name_matches.append(idx)

    if len(name_matches) != 1:
        return None
    prop_idx = name_matches[0]
    if prop_idx + 1 >= len(sentences):
        return None
    proof_sent = sentences[prop_idx + 1]
    if not sentence_text_is_proof_start(str(proof_sent.get("text") or "")):
        return None
    return proof_body_line_count(sentences, prop_idx + 1)


def build_step_count_by_catalog_id(
    catalog: list[ParcasCatalogEntry],
    project_root: Path,
    parse_sentence_script: str,
    parse_sentence_timeout_seconds: int,
) -> dict[int, int]:
    """Map catalog id -> proof body line count (Proof through Qed/Defined/Admitted)."""
    by_vfile: dict[str, list[ParcasCatalogEntry]] = {}
    for entry in catalog:
        by_vfile.setdefault(entry.v_rel_path, []).append(entry)

    step_by_id: dict[int, int] = {}
    root = project_root.resolve()
    for v_rel_path, entries in sorted(by_vfile.items()):
        vfile_abs = (root / v_rel_path).resolve()
        if file_contains_abort(vfile_abs):
            continue
        split_rc, _, split_err, split_timed_out, sentences, split_err_msg = run_split_sentences(
            root,
            parse_sentence_script,
            vfile_abs,
            parse_sentence_timeout_seconds,
        )
        if split_timed_out or split_rc != 0 or sentences is None:
            raise RuntimeError(
                split_err_msg or f"parse_sentence_script exit {split_rc} for {v_rel_path}: {split_err[:400]}"
            )
        for entry in entries:
            steps = _step_count_for_theorem_in_sentences(sentences, entry.theorem_name)
            step_by_id[entry.id] = int(steps) if steps is not None else 0
    return step_by_id


def assign_stable_ids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        rows,
        key=lambda r: (str(r["v_rel_path"]), int(r["start_line"]), str(r["theorem_name"])),
    )
    out: list[dict[str, Any]] = []
    for index, row in enumerate(sorted_rows, start=1):
        out.append({**row, "id": index})
    return out
