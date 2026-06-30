#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Parcas + Claude Code + deepseek-v4-flash[1m] (effort=max). Same PARCAS_OPAM_SWITCH as ProofAgent Parcas batch.
../claude/run_batch.sh \
  --testlist ../TestList.json \
  --workers 20 \
  --repeats 10 \
  --check-timeout-seconds 120 \
  --run-timeout-seconds 1800
