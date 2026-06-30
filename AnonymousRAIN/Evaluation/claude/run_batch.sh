#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1800}"
CLAUDE_MODEL="${CLAUDE_MODEL:-deepseek-v4-flash[1m]}"
CLAUDE_EFFORT="${CLAUDE_EFFORT:-max}"

exec python3 "${ROOT}/Evaluation/claude/run_batch.py" \
  --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
  --claude-model "$CLAUDE_MODEL" \
  --claude-effort "$CLAUDE_EFFORT" \
  "$@"
