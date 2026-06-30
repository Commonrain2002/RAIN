#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$ROOT/Evaluation/coqstoq_statistic/run_coqstoq_proof_step_statistics.py" \
  --split "${SPLIT:-test}" \
  --workers "${WORKERS:-8}" \
  "$@"
