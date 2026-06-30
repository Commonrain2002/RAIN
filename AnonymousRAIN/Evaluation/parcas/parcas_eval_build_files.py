"""Write ``parcas_eval_target.vo`` and ``parcas_eval_build.sh`` in a trial repo copy."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from parcas_batch_env import resolve_parcas_opam_switch, target_v_rel_to_dune_vo


def write_parcas_eval_build_files(
    dest_root: Path,
    *,
    opam_switch: str,
    v_rel_path: str,
) -> str:
    switch = resolve_parcas_opam_switch(opam_switch)
    vo_rel = target_v_rel_to_dune_vo(v_rel_path)
    dre = dest_root.resolve()
    dre.mkdir(parents=True, exist_ok=True)

    (dre / "parcas_eval_target.vo").write_text(vo_rel + "\n", encoding="utf-8")

    build_sh_text = f"""#!/usr/bin/env bash
# ProofAgent Parcas evaluation  build only the catalog target .vo (see parcas_eval_target.vo).
set -euo pipefail
ROOT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
cd "$ROOT"
TARGET="$(tr -d '\\r\\n' < parcas_eval_target.vo)"
if [ -z "$TARGET" ]; then
  echo "parcas_eval_target.vo is empty" >&2
  exit 1
fi
eval "$(opam env --switch={switch})"
exec dune build -j1 "$TARGET"
"""
    build_sh = dre / "parcas_eval_build.sh"
    build_sh.write_text(build_sh_text, encoding="utf-8")
    mode = build_sh.stat().st_mode
    build_sh.chmod(mode | stat.S_IXUSR | stat.S_IWUSR | stat.S_IRUSR)

    makefile_text = f"""# ProofAgent Parcas evaluation (coqdep closure copy)
PARCAS_OPAM_SWITCH ?= {switch}

.PHONY: all build clean
all: build

build:
\t@bash -eu ./parcas_eval_build.sh

clean:
\t@bash -eu -o pipefail -c 'eval "$$(opam env --switch=$${{PARCAS_OPAM_SWITCH}})" && dune clean' ; \\
\tfind . -name '*.lia.cache' -type f -delete 2>/dev/null || true ; \\
\tfind . -name '*.nia.cache' -type f -delete 2>/dev/null || true
"""
    (dre / "Makefile").write_text(makefile_text, encoding="utf-8")
    return vo_rel


def parcas_eval_build_shell_command(repo_dir: Path) -> str:
    script = (repo_dir.resolve() / "parcas_eval_build.sh")
    if not script.is_file():
        raise FileNotFoundError(f"parcas_eval_build.sh missing under {repo_dir}")
    return f"bash -eu {script}"
