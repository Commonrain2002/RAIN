"""Opam switch and build shell lines for Parcas evaluation batch runs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def resolve_parcas_opam_switch(explicit: str | None = None) -> str:
    raw = (explicit or os.environ.get("PARCAS_OPAM_SWITCH") or "parcas").strip()
    if not raw:
        raise ValueError("PARCAS_OPAM_SWITCH must not be empty")
    return raw


def target_v_rel_to_dune_vo(v_rel_path: str) -> str:
    normalized = v_rel_path.strip().replace("\\", "/")
    if not normalized or not normalized.endswith(".v"):
        raise ValueError(f"target Coq file must be a .v path: {v_rel_path!r}")
    return f"{normalized[:-2]}.vo"


def build_shell_dune(
    opam_switch: str,
    *,
    vo_target: str | None = None,
    jobs: int = 1,
) -> str:
    switch = resolve_parcas_opam_switch(opam_switch)
    j = max(1, int(jobs))
    if vo_target is not None:
        vo = vo_target.strip().replace("\\", "/")
        if not vo.endswith(".vo"):
            raise ValueError(f"dune vo target must end with .vo: {vo_target!r}")
        build_cmd = f"dune build -j{j} {vo}"
    else:
        build_cmd = f"dune build -j{j}"
    return f'eval "$(opam env --switch={switch})" && {build_cmd}'


def build_shell_make(opam_switch: str, *, jobs: int = 1) -> str:
    switch = resolve_parcas_opam_switch(opam_switch)
    j = max(1, int(jobs))
    return (
        f'eval "$(opam env --switch={switch})" && '
        f'make -j{j}'
    )


def build_check_shell(
    opam_switch: str,
    v_rel_path: str,
    *,
    full_theory: bool,
    jobs: int = 1,
) -> str:
    if full_theory:
        return build_shell_make(opam_switch, jobs=jobs)
    vo_target = target_v_rel_to_dune_vo(v_rel_path)
    return build_shell_dune(opam_switch, vo_target=vo_target, jobs=jobs)


def opam_coq_lib_dir(opam_switch: str) -> Path:
    switch = resolve_parcas_opam_switch(opam_switch)
    proc = subprocess.run(
        ["opam", "var", "--switch", switch, "lib"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"opam var lib failed for switch {switch}: {(proc.stderr or proc.stdout).strip()}"
        )
    lib_root = Path((proc.stdout or "").strip())
    coq_lib = lib_root / "coq"
    if not coq_lib.is_dir():
        raise RuntimeError(f"Coq lib dir not found under switch {switch}: {coq_lib}")
    return coq_lib.resolve()


def extra_readable_root_paths(opam_switch: str) -> list[str]:
    switch = resolve_parcas_opam_switch(opam_switch)
    coq_lib = opam_coq_lib_dir(switch)
    lib_posix = coq_lib.as_posix()
    if "/.opam/coqstoq/" in lib_posix:
        raise ValueError(
            "Parcas ProofAgent --extra-read must use the Parcas OPAM Coq library, not coqstoq; "
            f"set PARCAS_OPAM_SWITCH=parcas (current switch {switch!r} -> {lib_posix})"
        )
    return [lib_posix]
