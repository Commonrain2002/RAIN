export PARCAS_OPAM_SWITCH=parcas
eval "$(opam env --switch=$PARCAS_OPAM_SWITCH)"

../opencode/run_batch.sh \
  --testlist ../opencode/Result/parcas_opencode_batch/TestList_retrial_agent_error_cheat_timeout_lt3m.json \
  --workers 5 \
  --check-timeout-seconds 120 \
  --run-timeout-seconds 1800