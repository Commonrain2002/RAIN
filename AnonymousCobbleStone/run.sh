#!/usr/bin/env bash
# Full PnVRocqLib100: goal decomposition (Cobblestone), pnvrocqlib_test (100 lemmas).
# Non-oracle setup: hammer, max_depth 5, preceding-lemmas-only (not perfect-premises).
# Token / retry budgets: see .env (MAX_OBSERVATION_TOKENS, MAX_CHAT_COMPLETION_TOKENS, LLM_*).
# Requires opam switch coq-8.18 (see switches/coq-8.18) and DEEPSEEK_API_KEY in .env.
#
# Resume: UUID=<run-uuid> ./run.sh
# Parallelism: NUM_PROCESSES=1 ./run.sh  (default 1; lower if Coq OOM or API 429)
# Search budget: default 150 nodes/example; MAX_NODES_TO_EXPAND=300 ./run.sh
# Per-lemma cumulative wall clock: EXAMPLE_WALL_TIMEOUT_SEC=10800 ./run.sh (default 3h; unset in code = no limit)

set -euo pipefail
cd "$(dirname "$0")"

UUID="${UUID:-ds_max}"
NUM_PROCESSES="${NUM_PROCESSES:-6}"
MAX_NODES_TO_EXPAND="${MAX_NODES_TO_EXPAND:-150}"
EXAMPLE_WALL_TIMEOUT_SEC="${EXAMPLE_WALL_TIMEOUT_SEC:-5400}"

args=(
  ./scripts/goal-decomposition run
  -d pnvrocqlib_test
  -t
  -c preceding-lemmas-only
  -m 5
  -x "$MAX_NODES_TO_EXPAND"
  -n "$NUM_PROCESSES"
  -o deepseek-v4-flash
  --example-wall-timeout-sec "$EXAMPLE_WALL_TIMEOUT_SEC"
)

if [[ -n "$UUID" ]]; then
  args+=(-u "$UUID")
fi

exec "${args[@]}"
