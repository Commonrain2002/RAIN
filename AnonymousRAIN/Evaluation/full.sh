#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$ROOT/Sentence:$PATH"

if [[ "${RAIN_RUN_FULL_EVAL:-}" != "1" ]]; then
  echo "Set RAIN_RUN_FULL_EVAL=1 to launch full evaluations." >&2
  exit 2
fi

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "missing required environment variable: $name" >&2
    exit 2
  fi
}

run_suite() {
  case "$1" in
    proofagent)
      require_env COQSTOQ_PATH
      require_env LLM_API_KEY
      python3 Evaluation/proofagent/run_batch.py
      ;;
    codex)
      require_env COQSTOQ_PATH
      python3 Evaluation/codex/run_batch.py
      ;;
    opencode)
      require_env COQSTOQ_PATH
      python3 Evaluation/opencode/run_batch.py
      ;;
    claude)
      require_env COQSTOQ_PATH
      python3 Evaluation/claude/run_batch.py
      ;;
    parcas)
      require_env PARCAS_PATH
      require_env LLM_API_KEY
      python3 Evaluation/parcas/run_batch.py
      ;;
    cobble)
      require_env COBBLE_PROJECT_ROOT
      require_env LLM_API_KEY
      python3 Evaluation/cobble/run_batch.py
      ;;
    *)
      echo "unknown suite: $1" >&2
      exit 2
      ;;
  esac
}

if [[ "$#" -eq 0 ]]; then
  set -- proofagent codex opencode claude parcas cobble
fi

for suite in "$@"; do
  run_suite "$suite"
done
