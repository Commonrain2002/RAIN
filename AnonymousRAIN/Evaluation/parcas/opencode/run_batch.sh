#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1800}"
VERIFY_MAKE_TIMEOUT_SECONDS="${VERIFY_MAKE_TIMEOUT_SECONDS:-180}"
CHECK_TIMEOUT_SECONDS="${CHECK_TIMEOUT_SECONDS:-120}"
PARCAS_OPAM_SWITCH="${PARCAS_OPAM_SWITCH:-parcas}"
export PARCAS_OPAM_SWITCH

exec python3 "${ROOT}/Evaluation/parcas/opencode/run_batch.py" \
  --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
  --verify-make-timeout-seconds "$VERIFY_MAKE_TIMEOUT_SECONDS" \
  --check-timeout-seconds "$CHECK_TIMEOUT_SECONDS" \
  --opencode-preset deepseek-v4-flash \
  --opencode-variant max \
  "$@"
