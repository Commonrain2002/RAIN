#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Full Parcas batch. Omit --extra-read so the agent cannot read OPAM Coq lib sources.
../run_batch.sh \
  --testlist ../TestList.json \
  --workers 1 \
  --repeats 1 \
  --reasoning-effort max \
  --check-timeout-seconds 120 \
  --run-timeout-seconds 1800 \
  --extra-read \
  --ids 142