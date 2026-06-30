#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1800}"
OPENCODE_MODEL="${OPENCODE_MODEL:-deepseek/deepseek-v4-flash}"
OPENCODE_VARIANT="${OPENCODE_VARIANT:-max}"
OPENCODE_PRESET="${OPENCODE_PRESET:-}"

ARGS=(
  --run-timeout-seconds "$RUN_TIMEOUT_SECONDS"
)

if [[ -n "$OPENCODE_PRESET" ]]; then
  ARGS+=(--opencode-preset "$OPENCODE_PRESET")
fi

ARGS+=(
  --opencode-model "$OPENCODE_MODEL"
  --opencode-variant "$OPENCODE_VARIANT"
)

exec python3 "${ROOT}/Evaluation/opencode/run_batch.py" \
  "${ARGS[@]}" \
  "$@"
