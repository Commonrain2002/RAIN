#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PARCAS_OPAM_SWITCH="${PARCAS_OPAM_SWITCH:-parcas}"
eval "$(opam env --switch="${PARCAS_OPAM_SWITCH}" --set-switch)"

exec ../run_batch.sh \
  --ids "${SMOKE_ID:-239}" \
  --workers 1 \
  --repeats 1 \
  --batch-stamp "${BATCH_STAMP:-smoke_parcas_2}" \
  --opam-switch "${PARCAS_OPAM_SWITCH}" \
  "$@"
