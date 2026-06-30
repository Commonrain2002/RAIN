#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$ROOT/Sentence:$PATH"
python3 scripts/anonymity_check.py
python3 -m pytest   Evaluation/BatchTest/test_coq_strip_comments.py   Evaluation/BatchTest/test_proofagent_token_log.py   Evaluation/BatchTest/test_theorem_integrity.py   Evaluation/codex/test_codex_token_log.py
python3 Evaluation/proofagent/run_batch.py --help >/dev/null
python3 Evaluation/codex/run_batch.py --help >/dev/null
python3 Evaluation/opencode/run_batch.py --help >/dev/null
python3 Evaluation/claude/run_batch.py --help >/dev/null
python3 Evaluation/parcas/run_batch.py --help >/dev/null
python3 Evaluation/cobble/run_batch.py --help >/dev/null
