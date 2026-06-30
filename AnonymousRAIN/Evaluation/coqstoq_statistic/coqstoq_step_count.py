"""Proof-body sentence counts for CoqStoq theorems (vsrocq + coqstoq spans)."""

from __future__ import annotations

from typing import Any

from BatchTest.theorem_integrity import (
    proof_body_sentence_count,
    sentence_text_is_proof_end,
    sentence_text_is_proof_start,
    sentence_text_is_proof_terminal,
)

# CoqStoq stored positions can differ from vsrocq 1-based lines by several lines.
_THEOREM_LINE_SLACK = 8

_THEOREM_VERNAC_TYPES = frozenset({
    "theorem",
    "lemma",
    "fact",
    "corollary",
    "proposition",
    "definition",
    "instance",
    "fixpoint",
})

_BLOCKING_INTERLUDE_VERNAC = frozenset({
    "notation",
    "require",
    "import",
    "module",
    "section",
    "end",
    "comment",
    "inductive",
    "record",
    "variant",
    "coercion",
    "hint",
    "export",
    "local",
    "global",
    "arguments",
})

_PROPOSITION_PREFIXES = (
    "Lemma",
    "Theorem",
    "Fact",
    "Corollary",
    "Proposition",
    "Example",
    "Definition",
    "Fixpoint",
    "Instance",
)


def _vernac_is_proposition(sent: dict[str, Any]) -> bool:
    vtype = str(sent.get("vernac_type") or "").strip().lower()
    if vtype in _THEOREM_VERNAC_TYPES:
        return True
    if vtype != "parse_error":
        return False
    text = str(sent.get("text") or "").lstrip()
    return any(text.startswith(prefix) for prefix in _PROPOSITION_PREFIXES)


def _is_new_declaration_after_prop(sent: dict[str, Any], prop_name: str) -> bool:
    vtype = str(sent.get("vernac_type") or "").strip().lower()
    if vtype in _BLOCKING_INTERLUDE_VERNAC:
        return True
    if vtype in _THEOREM_VERNAC_TYPES:
        name = str(sent.get("name") or "").strip()
        if name and name != prop_name:
            return True
    return False


def _resolve_proof_start_index(
    sentences: list[dict[str, Any]],
    prop_idx: int,
    theorem_name: str,
) -> int | None:
    if prop_idx + 1 >= len(sentences):
        return None
    next_text = str(sentences[prop_idx + 1].get("text") or "")
    if sentence_text_is_proof_start(next_text):
        return prop_idx + 1
    for j in range(prop_idx + 1, len(sentences)):
        sent = sentences[j]
        text = str(sent.get("text") or "")
        if _is_new_declaration_after_prop(sent, theorem_name):
            return None
        if sentence_text_is_proof_end(text):
            return j
        return j
    return None


def _proposition_type_rank(sent: dict[str, Any]) -> int:
    vtype = str(sent.get("vernac_type") or "").strip().lower()
    text = str(sent.get("text") or "").lstrip()
    if vtype in {"lemma", "theorem", "fact", "corollary", "proposition", "example"}:
        return 0
    if text.startswith(("Lemma", "Theorem", "Fact", "Corollary", "Proposition", "Example")):
        return 0
    if vtype in {"definition", "fixpoint", "instance"}:
        return 1
    if text.startswith(("Definition", "Fixpoint", "Instance")):
        return 1
    return 2


def find_coqstoq_proposition_index(
    sentences: list[dict[str, Any]],
    *,
    theorem_start_line: int,
    theorem_start_column: int,
    theorem_end_line: int,
    theorem_end_column: int,
    proof_start_line: int,
) -> int | None:
    del theorem_end_column
    candidates: list[int] = []
    for idx, sent in enumerate(sentences):
        if not _vernac_is_proposition(sent):
            continue
        start_line = int(sent.get("start_line") or 0)
        end_line = int(sent.get("end_line") or 0)
        if start_line > theorem_end_line + _THEOREM_LINE_SLACK:
            continue
        if end_line < theorem_start_line - _THEOREM_LINE_SLACK:
            continue
        candidates.append(idx)
    if not candidates:
        return None

    before_proof = [
        idx
        for idx in candidates
        if int(sentences[idx].get("start_line") or 0) <= proof_start_line + _THEOREM_LINE_SLACK
    ]
    if before_proof:
        candidates = before_proof

    if len(candidates) == 1:
        return candidates[0]
    return min(
        candidates,
        key=lambda i: (
            _proposition_type_rank(sentences[i]),
            abs(int(sentences[i].get("start_line") or 0) - theorem_start_line),
            abs(int(sentences[i].get("start_column") or 0) - theorem_start_column),
        ),
    )


def count_coqstoq_proof_sentences(
    sentences: list[dict[str, Any]],
    *,
    theorem_start_line: int,
    theorem_start_column: int,
    theorem_end_line: int,
    theorem_end_column: int,
    proof_start_line: int,
    proof_start_column: int,
) -> tuple[int | None, str | None, str | None]:
    """
    Returns (sentence_count, theorem_name, error).
    Counts vsrocq sentences after optional ``Proof.`` up to but not including ``Qed.``/``Defined.``.
    """
    del proof_start_column

    prop_idx = find_coqstoq_proposition_index(
        sentences,
        theorem_start_line=theorem_start_line,
        theorem_start_column=theorem_start_column,
        theorem_end_line=theorem_end_line,
        theorem_end_column=theorem_end_column,
        proof_start_line=proof_start_line,
    )
    if prop_idx is None:
        return None, None, "no proposition sentence matching coqstoq theorem span"

    theorem_name = str(sentences[prop_idx].get("name") or "").strip() or None
    proof_start_idx = _resolve_proof_start_index(sentences, prop_idx, theorem_name or "")
    if proof_start_idx is None:
        for offset in range(prop_idx + 1, len(sentences)):
            sent = sentences[offset]
            text = str(sent.get("text") or "")
            if sentence_text_is_proof_start(text):
                proof_start_idx = offset
                break
            if sentence_text_is_proof_terminal(text):
                break
            if _vernac_is_proposition(sent) and offset > prop_idx + 1:
                break
        if proof_start_idx is None:
            return None, theorem_name, "no proof start (Proof. or inline body)"

    if not sentence_text_is_proof_start(str(sentences[proof_start_idx].get("text") or "")):
        if proof_start_idx > 0 and sentence_text_is_proof_start(
            str(sentences[proof_start_idx - 1].get("text") or "")
        ):
            proof_start_idx -= 1

    return proof_body_sentence_count(sentences, proof_start_idx), theorem_name, None
