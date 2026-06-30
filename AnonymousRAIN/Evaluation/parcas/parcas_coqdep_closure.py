"""Parcas coqdep closure: ``-Q <project>/src parcas`` + transitive_deps_coqdep."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Set, Tuple

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from coqstoq_minimal_copy import (  # noqa: E402
    _real,
    find_coqdep,
    transitive_deps_coqdep,
)

PARCAS_LOGICAL_PREFIX = "parcas"


def parcas_src_dir(project_root: Path) -> Path:
    src = (_real(project_root) / "src").resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"Parcas src/ missing: {src}")
    return src


def write_parcas_coqdep_project_file(project_root: Path) -> tuple[Path, bool]:
    src = parcas_src_dir(project_root)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_CoqProject",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(f"# Parcas coqdep loadpath (auto)\n-Q {src} {PARCAS_LOGICAL_PREFIX}\n")
    tmp.close()
    return Path(tmp.name), True


def parcas_transitive_closure_vfiles(
    project_root: Path,
    v_rel_path: str,
) -> tuple[Set[Path], Set[Path]]:
    coqdep_bin = find_coqdep()
    if not coqdep_bin:
        raise RuntimeError("coqdep not found in PATH; install Coq or activate opam switch parcas")

    root = _real(project_root)
    rel = v_rel_path.strip().replace("\\", "/")
    v_abs = (root / rel).resolve()
    if not v_abs.is_file():
        raise FileNotFoundError(f"target .v not under project root: {rel}")

    proj_file, delete_after = write_parcas_coqdep_project_file(root)
    try:
        return transitive_deps_coqdep(root, proj_file, rel, coqdep_bin)
    finally:
        if delete_after and proj_file.is_file():
            try:
                proj_file.unlink()
            except OSError:
                pass


def closure_v_rel_paths(project_root: Path, v_rel_path: str) -> list[str]:
    copy_set, _ = parcas_transitive_closure_vfiles(project_root, v_rel_path)
    root = _real(project_root)
    rels: list[str] = []
    for path in sorted(copy_set):
        rels.append(path.relative_to(root).as_posix())
    return rels
