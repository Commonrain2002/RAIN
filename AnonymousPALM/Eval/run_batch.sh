#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CONDA_ENV="${PALM_CONDA_ENV:-}"
OPAM_SWITCH="${PALM_OPAM_SWITCH:-coqstoq}"
export PALM_OPAM_SWITCH="$OPAM_SWITCH"
if [ -n "$CONDA_ENV" ] && command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
  conda activate "$CONDA_ENV"
fi
eval "$(opam env --switch="$OPAM_SWITCH" --set-switch)"
exec python Eval/run_batch.py "$@"
