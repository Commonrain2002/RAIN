#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1800}"
EXTRA_ERROR_COUNT="${EXTRA_ERROR_COUNT:-2}"
exec python3 "${ROOT}/BatchTest/run_batch.py" \
  --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
  --extra-error-count "$EXTRA_ERROR_COUNT" \
  "$@"
