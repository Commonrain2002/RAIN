#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Parcas + OpenCode + deepseek-v4-flash (variant=max). Same PARCAS_OPAM_SWITCH as ProofAgent Parcas batch.
../opencode/run_batch.sh \
  --testlist ../TestList.json \
  --workers 5 \
  --repeats 1 \
  --check-timeout-seconds 120 \
  --run-timeout-seconds 1800 
