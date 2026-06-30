"""Theorem proposition baseline and post-agent integrity checks for batch evaluation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from BatchTest.coq_strip_comments import strip_coq_comments


PROOF_DOT_SENTENCE_TEXT = "Proof."


def sentence_text_is_proof_start(text: str) -> bool:
    return str(text or "").strip().startswith("Proof")


def sentence_text_is_proof_end(text: str) -> bool:
    stripped = str(text or "").strip()
    return (
        stripped.startswith("Qed")
        or stripped.startswith("Defined")
        or stripped.startswith("Admitted")
        or stripped.startswith("Abort")
    )


def sentence_text_is_proof_terminal(text: str) -> bool:
    stripped = str(text or "").strip()
    return stripped.startswith("Qed") or stripped.startswith("Defined")


def proof_body_sentence_count(sentences: list[dict[str, Any]], proof_start_index: int) -> int:
    """Count vsrocq sentences strictly between ``Proof.`` and ``Qed.``/``Defined.``."""
    if proof_start_index < 0 or proof_start_index >= len(sentences):
        return 0
    index = proof_start_index
    if sentence_text_is_proof_start(str(sentences[index].get("text") or "")):
        index += 1
    count = 0
    for offset in range(index, len(sentences)):
        text = str(sentences[offset].get("text") or "")
        if sentence_text_is_proof_terminal(text):
            break
        count += 1
    return count


def proof_body_line_count(sentences: list[dict[str, Any]], proof_start_index: int) -> int:
    if proof_start_index < 0 or proof_start_index >= len(sentences):
        return 0
    proof_start_line = int(sentences[proof_start_index].get("start_line") or 0)
    proof_end_line = int(sentences[proof_start_index].get("end_line") or 0)
    for idx in range(proof_start_index, len(sentences)):
        sent = sentences[idx]
        end_line = int(sent.get("end_line") or 0)
        if end_line > proof_end_line:
            proof_end_line = end_line
        if sentence_text_is_proof_end(str(sent.get("text") or "")):
            break
    return max(0, proof_end_line - proof_start_line)


def shell_quote_path(path: str) -> str:
    return "'" + path.replace("'", "'\\''") + "'"


def collapse_whitespace_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_theorem_proposition_text(sentences: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not sentences:
        return None, "no sentences in split output"

    proof_start_index: int | None = None
    for idx in range(len(sentences) - 1, -1, -1):
        raw_text = sentences[idx].get("text")
        if raw_text is None:
            continue
        if sentence_text_is_proof_start(str(raw_text)):
            proof_start_index = idx
            break

    if proof_start_index is None:
        return None, "no sentence starting with Proof"

    if proof_start_index == 0:
        return None, "Proof is first sentence; no preceding proposition sentence"

    prev = sentences[proof_start_index - 1]
    prev_text = prev.get("text")
    if prev_text is None or not str(prev_text).strip():
        return None, "sentence before Proof has empty text"

    return str(prev_text), None


def normalize_theorem_text_for_compare(text: str) -> str:
    """Strip Coq comments then collapse whitespace for theorem substring comparison."""
    no_comments = strip_coq_comments(text)
    return collapse_whitespace_for_compare(no_comments)


def _text_for_theorem_substring_match(text: str) -> str:
    return normalize_theorem_text_for_compare(text)


def theorem_proposition_preserved(file_text: str, proposition_text: str) -> bool:
    collapsed_prop = normalize_theorem_text_for_compare(proposition_text)
    if not collapsed_prop:
        return False
    collapsed_file = normalize_theorem_text_for_compare(file_text)
    return collapsed_prop in collapsed_file


def _parse_split_json_output(combined: str) -> dict[str, Any] | None:
    trimmed = combined.strip()
    if not trimmed:
        return None

    try:
        obj = json.loads(trimmed)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    lines = [ln.strip() for ln in trimmed.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("{") and ln.endswith("}"):
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def run_split_sentences(
    repo_dir: Path,
    script_line: str,
    coq_abs: Path,
    timeout_seconds: int,
) -> tuple[int, str, str, bool, list[dict[str, Any]] | None, str | None]:
    if not script_line.strip():
        return -1, "", "", False, None, "parse sentence script is empty"

    shell_cmd = f"{script_line.strip()} {shell_quote_path(str(coq_abs.resolve()))}"
    try:
        proc = subprocess.run(
            ["/bin/sh", "-c", shell_cmd],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return 124, out, err, True, None, "parse_sentence_script timed out"

    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        detail_suffix = f": {detail[:500]}" if detail else ""
        return proc.returncode, proc.stdout or "", proc.stderr or "", False, None, (
            f"parse_sentence_script exit {proc.returncode}{detail_suffix}"
        )

    envelope = _parse_split_json_output(combined)
    if envelope is None:
        return proc.returncode, proc.stdout or "", proc.stderr or "", False, None, "no JSON envelope in split output"

    raw_sentences = envelope.get("sentences")
    if not isinstance(raw_sentences, list):
        return proc.returncode, proc.stdout or "", proc.stderr or "", False, None, "JSON has no sentences array"

    sentences: list[dict[str, Any]] = [s for s in raw_sentences if isinstance(s, dict)]
    if not sentences:
        return proc.returncode, proc.stdout or "", proc.stderr or "", False, None, "sentences array is empty"

    return proc.returncode, proc.stdout or "", proc.stderr or "", False, sentences, None


@dataclass(frozen=True)
class TheoremBaselineCapture:
    ok: bool
    proposition_text: str | None
    error: str | None
    split_returncode: int | None
    split_timed_out: bool
    proposition_len: int | None
    collapsed_preview: str | None
    collapsed_hash_prefix: str | None


def capture_theorem_baseline(
    repo_dir: Path,
    target_coq_abs: Path,
    script_line: str,
    timeout_seconds: int,
    artifacts_dir: Path,
) -> TheoremBaselineCapture:
    split_rc, split_out, split_err, split_timed_out, sentences, split_err_msg = run_split_sentences(
        repo_dir,
        script_line,
        target_coq_abs,
        timeout_seconds,
    )

    artifact: dict[str, Any] = {
        "target_coq_file": str(target_coq_abs),
        "parse_sentence_script": script_line,
        "split_returncode": split_rc,
        "split_timed_out": int(split_timed_out),
        "split_error": split_err_msg,
    }
    if split_out:
        artifact["split_stdout_preview"] = split_out[:8000]
    if split_err:
        artifact["split_stderr_preview"] = split_err[:8000]

    if split_timed_out:
        artifact["ok"] = False
        artifact["error"] = split_err_msg or "split timed out"
        _write_baseline_artifact(artifacts_dir, artifact)
        return TheoremBaselineCapture(
            ok=False,
            proposition_text=None,
            error=artifact["error"],
            split_returncode=split_rc,
            split_timed_out=True,
            proposition_len=None,
            collapsed_preview=None,
            collapsed_hash_prefix=None,
        )

    if split_err_msg or sentences is None:
        artifact["ok"] = False
        artifact["error"] = split_err_msg or "split failed"
        _write_baseline_artifact(artifacts_dir, artifact)
        return TheoremBaselineCapture(
            ok=False,
            proposition_text=None,
            error=artifact["error"],
            split_returncode=split_rc,
            split_timed_out=False,
            proposition_len=None,
            collapsed_preview=None,
            collapsed_hash_prefix=None,
        )

    proposition_text, extract_error = extract_theorem_proposition_text(sentences)
    if extract_error or proposition_text is None:
        artifact["ok"] = False
        artifact["error"] = extract_error or "extract failed"
        _write_baseline_artifact(artifacts_dir, artifact)
        return TheoremBaselineCapture(
            ok=False,
            proposition_text=None,
            error=artifact["error"],
            split_returncode=split_rc,
            split_timed_out=False,
            proposition_len=None,
            collapsed_preview=None,
            collapsed_hash_prefix=None,
        )

    collapsed = collapse_whitespace_for_compare(proposition_text)
    preview = collapsed[:200] + ("..." if len(collapsed) > 200 else "")
    hash_prefix = hashlib.sha256(collapsed.encode("utf-8")).hexdigest()[:16]

    artifact["ok"] = True
    artifact["theorem_proposition_text"] = proposition_text
    artifact["theorem_proposition_len"] = len(proposition_text)
    artifact["collapsed_preview"] = preview
    artifact["collapsed_hash_prefix"] = hash_prefix
    _write_baseline_artifact(artifacts_dir, artifact)

    return TheoremBaselineCapture(
        ok=True,
        proposition_text=proposition_text,
        error=None,
        split_returncode=split_rc,
        split_timed_out=False,
        proposition_len=len(proposition_text),
        collapsed_preview=preview,
        collapsed_hash_prefix=hash_prefix,
    )


def _write_baseline_artifact(artifacts_dir: Path, obj: dict[str, Any]) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / "theorem_baseline.json"
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_theorem_modified_after_agent(
    repo_dir: Path,
    target_rel: str,
    proposition_text: str,
) -> tuple[bool, str | None]:
    target_path = repo_dir / target_rel
    if not target_path.is_file():
        return False, "target coq file missing after agent"

    try:
        file_text = target_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"read target failed: {exc}"

    if theorem_proposition_preserved(file_text, proposition_text):
        return True, None
    return False, "theorem modified"
