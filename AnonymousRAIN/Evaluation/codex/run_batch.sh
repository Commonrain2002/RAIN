#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1800}"
CODEX_MODEL="${CODEX_MODEL:-gpt-5.4}"
CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-xhigh}"

exec python3 "${ROOT}/Evaluation/codex/run_batch.py" \
  --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
  --codex-model "$CODEX_MODEL" \
  --codex-reasoning-effort "$CODEX_REASONING_EFFORT" \
  "$@"
