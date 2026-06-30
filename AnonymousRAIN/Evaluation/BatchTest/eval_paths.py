"""Shared paths for Evaluation batch runners (under Evaluation/BatchTest)."""

from __future__ import annotations

from pathlib import Path

_EVAL_BATCHTEST_DIR = Path(__file__).resolve().parent
_EVAL_DIR = _EVAL_BATCHTEST_DIR.parent


def evaluation_batchtest_dir() -> Path:
    return _EVAL_BATCHTEST_DIR


def coqstoq_meta_script(proofagent_root: Path) -> Path:
    """Prefer Evaluation/BatchTest/coqstoq_meta.py."""
    under_eval = _EVAL_BATCHTEST_DIR / "coqstoq_meta.py"
    if under_eval.is_file():
        return under_eval.resolve()
    legacy = proofagent_root / "BatchTest" / "coqstoq_meta.py"
    return legacy.resolve()


def default_testlist_candidates(proofagent_root: Path) -> list[Path]:
    return [
        _EVAL_DIR / "proofagent" / "TestList.txt",
        _EVAL_BATCHTEST_DIR / "TestList.txt",
        proofagent_root / "TestList.txt",
    ]


def resolve_default_testlist(proofagent_root: Path) -> Path | None:
    for path in default_testlist_candidates(proofagent_root):
        if path.is_file():
            return path
    return None
