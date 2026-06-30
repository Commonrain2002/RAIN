from __future__ import annotations

from BatchTest.theorem_integrity import (
    collapse_whitespace_for_compare,
    extract_theorem_proposition_text,
    theorem_proposition_preserved,
)


def test_extract_last_proof_dot_preceding_sentence() -> None:
    sentences = [
        {"text": "Theorem t: True.", "index": 0},
        {"text": "Proof.", "index": 1},
        {"text": "  intros.", "index": 2},
        {"text": "Proof.", "index": 3},
        {"text": "  auto.", "index": 4},
    ]
    text, err = extract_theorem_proposition_text(sentences)
    assert err is None
    assert text == "  intros."


def test_extract_no_proof_dot() -> None:
    sentences = [{"text": "Definition x := 0.", "index": 0}]
    text, err = extract_theorem_proposition_text(sentences)
    assert text is None
    assert err is not None and "Proof" in err


def test_extract_proof_with_preceding_sentence() -> None:
    sentences = [
        {"text": "Lemma foo: True.", "index": 0},
        {"text": "Proof with eauto.", "index": 1},
        {"text": "  auto.", "index": 2},
    ]
    text, err = extract_theorem_proposition_text(sentences)
    assert err is None
    assert text == "Lemma foo: True."


def test_collapse_whitespace() -> None:
    assert collapse_whitespace_for_compare("a  \n\t b") == "a b"


def test_theorem_preserved_ignores_layout() -> None:
    prop = "Theorem foo:\n  forall x, x = x."
    file_text = "Theorem foo: forall x, x = x.\nProof.\n  reflexivity.\nQed."
    assert theorem_proposition_preserved(file_text, prop)


def test_theorem_modified_detected() -> None:
    prop = "Theorem foo: True."
    file_text = "Theorem foo: False.\nProof. auto. Qed."
    assert not theorem_proposition_preserved(file_text, prop)


def test_theorem_not_matched_inside_block_comment() -> None:
    prop = "Theorem foo: True."
    file_text = "Theorem foo: False.\n(* Theorem foo: True. *)\nProof. auto. Qed."
    assert not theorem_proposition_preserved(file_text, prop)


def test_theorem_preserved_with_surrounding_comments() -> None:
    prop = "Theorem foo: True."
    file_text = "(* header *)\nTheorem foo: True.\n(* between *)\nProof. auto. Qed."
    assert theorem_proposition_preserved(file_text, prop)
