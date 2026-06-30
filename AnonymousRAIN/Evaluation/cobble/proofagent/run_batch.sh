#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1800}"
exec python3 "${ROOT}/Evaluation/cobble/proofagent/run_batch.py" \
  --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
  "$@"
