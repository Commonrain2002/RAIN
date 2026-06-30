#!/usr/bin/env python3
"""Parcas minimal copy: coqdep closure (-Q src parcas) + dune target build scripts.

Copies only the transitive .v closure of the catalog target (not full ``src/``), plus
``dune-project`` and ``src/dune``, then writes ``parcas_eval_build.sh`` / ``Makefile``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from coqstoq_minimal_copy import (  # noqa: E402
    _coqstoq_column_exclusive_end,
    _real,
    ensure_dest_tree_user_writable,
    prune_coq_file_to_theorem,
)

from parcas_coqdep_closure import parcas_transitive_closure_vfiles  # noqa: E402
from parcas_eval_build_files import write_parcas_eval_build_files  # noqa: E402
from parcas_batch_env import resolve_parcas_opam_switch  # noqa: E402


def _copy_dune_metadata(project_root: Path, dest_root: Path) -> None:
    for rel in ("dune-project", "src/dune"):
        src = project_root / rel
        if not src.is_file():
            raise FileNotFoundError(f"Parcas build metadata missing: {src}")
        dst = dest_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _copy_closure_vfiles(project_root: Path, dest_root: Path, copy_vfiles: set[Path]) -> None:
    root = _real(project_root)
    for v_path in sorted(copy_vfiles):
        rel = v_path.relative_to(root)
        dst = dest_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v_path, dst)


def _remove_auto_coqproject(dest_root: Path) -> None:
    for name in ("_CoqProject", "CoqProject", "Makefile.coq", "Makefile.coq.conf"):
        path = dest_root / name
        if path.is_file():
            path.unlink()


def _write_closure_manifest(dest_root: Path, rel_paths: list[str]) -> None:
    lines = ["# coqdep closure .v files (Parcas -Q src parcas)\n", * [f"{r}\n" for r in rel_paths]]
    (dest_root / "parcas_eval_coqdep_closure.txt").write_text("".join(lines), encoding="utf-8")


def parcas_minimal_copy(
    *,
    project_root: Path,
    vfile: Path,
    dest_parent: Path,
    opam_switch: str,
    theorem_end_line0: int | None,
    theorem_end_column_raw: int | None,
    force: bool,
) -> Path:
    project_root = _real(project_root)
    vfile = _real(vfile)
    if not vfile.is_file() or vfile.suffix != ".v":
        raise ValueError(f"not a .v file: {vfile}")
    if not vfile.resolve().is_relative_to(project_root.resolve()):
        raise ValueError(f"vfile not under project root: {vfile}")

    dest = dest_parent / project_root.name
    if dest.exists():
        if not dest.is_dir():
            raise ValueError(f"dest exists and is not a directory: {dest}")
        if any(dest.iterdir()):
            if not force:
                raise ValueError(f"dest non-empty (use force): {dest}")
            for entry in dest.iterdir():
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()

    rel_v = vfile.relative_to(project_root).as_posix()
    copy_vfiles, _compile_vfiles = parcas_transitive_closure_vfiles(project_root, rel_v)
    if vfile.resolve() not in {p.resolve() for p in copy_vfiles}:
        copy_vfiles.add(vfile.resolve())

    dest.mkdir(parents=True, exist_ok=True)
    _copy_closure_vfiles(project_root, dest, copy_vfiles)
    _copy_dune_metadata(project_root, dest)
    _remove_auto_coqproject(dest)

    rel_paths = sorted(p.relative_to(project_root).as_posix() for p in copy_vfiles)
    _write_closure_manifest(dest, rel_paths)
    write_parcas_eval_build_files(dest, opam_switch=opam_switch, v_rel_path=rel_v)

    if theorem_end_line0 is not None:
        dst_v = dest / rel_v
        te_l = int(theorem_end_line0)
        te_c = int(theorem_end_column_raw or 0)
        col = _coqstoq_column_exclusive_end(te_c)
        prune_coq_file_to_theorem(vfile, dst_v, te_l, col)

    ensure_dest_tree_user_writable(dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--vfile-path", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True, help="Parent dir; writes <name>/")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--theorem-end-line0", type=int, default=None)
    ap.add_argument("--theorem-end-column-raw", type=int, default=None)
    ap.add_argument(
        "--opam-switch",
        type=str,
        default=None,
        help="Default: env PARCAS_OPAM_SWITCH or parcas",
    )
    args = ap.parse_args()

    try:
        switch = resolve_parcas_opam_switch(args.opam_switch)
        dest = parcas_minimal_copy(
            project_root=args.project_root,
            vfile=args.vfile_path,
            dest_parent=args.output.resolve(),
            opam_switch=switch,
            theorem_end_line0=args.theorem_end_line0,
            theorem_end_column_raw=args.theorem_end_column_raw,
            force=bool(args.force),
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    rel = args.vfile_path.resolve().relative_to(args.project_root.resolve()).as_posix()
    closure_list = (dest / "parcas_eval_coqdep_closure.txt").read_text(encoding="utf-8")
    v_count = sum(1 for ln in closure_list.splitlines() if ln.endswith(".v"))

    print(f": {args.project_root.resolve()}")
    print(f":   {args.vfile_path.resolve()}")
    print(f":   {dest}")
    print(f": coqdep  ({v_count}  .v) + dune-project + src/dune + parcas_eval_build.sh")
    print(f"opam switch: {switch}")
    print(": parcas_eval_coqdep_closure.txt")
    for line in closure_list.splitlines():
        if line.strip() and not line.startswith("#"):
            print(f"  {line.strip()}")
    if args.theorem_end_line0 is not None:
        print(f" Proof. Admitted.: {rel}")
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
