"""Parcas catalog and fixed TestList.json helpers (no random sampling here)."""

from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
_EVAL_DIR = _REPO_ROOT / "Evaluation"

import sys

if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from BatchTest.coq_strip_comments import strip_coq_comments
from BatchTest.testlist_run_specs import IdRunSpec, read_run_specs_from_testlist

_ABORT_IN_FILE_RE = re.compile(r"\bAbort\b", re.MULTILINE)

DEFAULT_CATALOG_PATH = _EVAL_PARCAS_DIR / "parcas_catalog.json"
DEFAULT_TESTLIST_PATH = _EVAL_PARCAS_DIR / "TestList.json"


@dataclass(frozen=True)
class ParcasCatalogEntry:
    id: int
    v_rel_path: str
    theorem_name: str
    start_line: int
    step_count: int


def resolve_parcas_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    raw = os.environ.get("PARCAS_PATH")
    if not raw:
        raise ValueError("PARCAS_PATH is not set; pass --parcas-path or export PARCAS_PATH")
    path = Path(raw).resolve()
    if not path.is_dir():
        raise ValueError(f"PARCAS_PATH is not a directory: {path}")
    return path


def file_contains_abort(v_path: Path) -> bool:
    try:
        text = v_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    no_comments = strip_coq_comments(text)
    return _ABORT_IN_FILE_RE.search(no_comments) is not None


def collect_abort_file_rel_paths(project_root: Path) -> frozenset[str]:
    """Relative paths under project_root for .v files that contain Abort (comments stripped)."""
    root = project_root.resolve()
    src = root / "src"
    if not src.is_dir():
        return frozenset()
    rel_paths: set[str] = set()
    for v_path in src.rglob("*.v"):
        if file_contains_abort(v_path):
            rel_paths.add(v_path.relative_to(root).as_posix())
    return frozenset(rel_paths)


def load_catalog(catalog_path: Path | None = None) -> list[ParcasCatalogEntry]:
    path = (catalog_path or DEFAULT_CATALOG_PATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"catalog not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries_raw: list[Any]
    if isinstance(raw, dict) and "entries" in raw:
        entries_raw = raw["entries"]
    elif isinstance(raw, list):
        entries_raw = raw
    else:
        raise ValueError(f"unexpected catalog shape: {path}")

    out: list[ParcasCatalogEntry] = []
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        out.append(
            ParcasCatalogEntry(
                id=int(item["id"]),
                v_rel_path=str(item["v_rel_path"]),
                theorem_name=str(item["theorem_name"]),
                start_line=int(item.get("start_line") or 0),
                step_count=int(item.get("step_count") or 0),
            )
        )
    out.sort(key=lambda e: e.id)
    return out


def catalog_entry_by_id(catalog: list[ParcasCatalogEntry], id_value: int) -> ParcasCatalogEntry:
    for entry in catalog:
        if entry.id == id_value:
            return entry
    raise ValueError(f"catalog id not found: {id_value}")


def read_run_specs_from_testlist_file(
    testlist_path: Path | None = None,
    *,
    default_repeats: int = 1,
) -> list[IdRunSpec]:
    path = (testlist_path or DEFAULT_TESTLIST_PATH).resolve()
    return read_run_specs_from_testlist(path, default_repeats)


def assert_entries_not_in_abort_files(
    entries: list[ParcasCatalogEntry],
    project_root: Path,
) -> None:
    root = project_root.resolve()
    for entry in entries:
        v_abs = (root / entry.v_rel_path).resolve()
        if file_contains_abort(v_abs):
            raise ValueError(
                f"TestList id {entry.id} points to file with Abort: {entry.v_rel_path}"
            )


def catalog_excluding_abort_files(
    catalog: list[ParcasCatalogEntry],
    project_root: Path,
) -> list[ParcasCatalogEntry]:
    root = project_root.resolve()
    out: list[ParcasCatalogEntry] = []
    for entry in catalog:
        v_abs = (root / entry.v_rel_path).resolve()
        if file_contains_abort(v_abs):
            continue
        out.append(entry)
    return out


def sample_longest_and_random_entries(
    catalog: list[ParcasCatalogEntry],
    step_count_by_id: dict[int, int],
    *,
    long_count: int,
    random_count: int,
    seed: int,
) -> tuple[list[ParcasCatalogEntry], list[ParcasCatalogEntry]]:
    total = int(long_count) + int(random_count)
    if int(long_count) < 0 or int(random_count) < 0:
        raise ValueError("long_count and random_count must be >= 0")
    if total < 1:
        raise ValueError("long_count + random_count must be >= 1")
    if len(catalog) < total:
        raise ValueError(
            f"catalog has {len(catalog)} eligible entries, need {total} "
            f"({long_count} longest + {random_count} random)"
        )

    ranked = sorted(
        catalog,
        key=lambda entry: (-int(step_count_by_id.get(entry.id, 0)), entry.id),
    )
    longest = ranked[: int(long_count)] if int(long_count) > 0 else []
    remaining = ranked[int(long_count) :]
    rng = random.Random(int(seed))
    random_pick = rng.sample(remaining, int(random_count))
    return longest, random_pick


def _dict_entry_has_explicit_repeats(entry: dict[str, Any]) -> bool:
    return any(key in entry for key in ("repeats", "trials", "repeat"))


def _raw_value_configures_repeats(raw: Any) -> bool:
    if isinstance(raw, bool):
        return False
    if isinstance(raw, int):
        return True
    if isinstance(raw, str) and raw.strip().isdigit():
        return True
    if isinstance(raw, dict):
        return _dict_entry_has_explicit_repeats(raw)
    return False


def testlist_has_configured_repeats(testlist_path: Path) -> bool:
    raw_text = testlist_path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw_text:
        return False
    try:
        parsed = json.loads(raw_text)
    except Exception:
        return False

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and _dict_entry_has_explicit_repeats(item):
                return True
        return False

    if isinstance(parsed, dict):
        for val in parsed.values():
            if _raw_value_configures_repeats(val):
                return True
        return False

    return False


def cli_argv_includes_repeats_flag(argv: list[str] | None = None) -> bool:
    args = argv if argv is not None else sys.argv
    return any(part == "--repeats" or part.startswith("--repeats=") for part in args)
