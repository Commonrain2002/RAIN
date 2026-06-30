#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1800}"
CHAT_MODEL="${CHAT_MODEL:-deepseek-v4-flash}"
REASONING_EFFORT="${REASONING_EFFORT:-max}"
PARCAS_OPAM_SWITCH="${PARCAS_OPAM_SWITCH:-parcas}"
export PARCAS_OPAM_SWITCH

exec python3 "${ROOT}/Evaluation/parcas/run_batch.py" \
  --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
  --chat-model "$CHAT_MODEL" \
  --reasoning-effort "$REASONING_EFFORT" \
  "$@"
