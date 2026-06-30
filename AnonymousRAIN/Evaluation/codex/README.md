# Codex batch evaluation

Batch CoqStoq problems with **Codex CLI** (`codex exec`), default **GPT 5.4** and reasoning **`xhigh`**. Same copy / theorem baseline / verify `make` flow as `Evaluation/opencode/run_batch`.

## Prerequisites

- `codex` on `PATH`, authenticated (`codex login` or `CODEX_API_KEY` for `codex exec`)
- `COQSTOQ_PATH` or `--coqstoq-path`
- Coq workspace tooling (`make`, `python3`, `scripts/coqstoq_minimal_copy.py`)

## Quick start

```bash
cd /path/to/ProofAgent
chmod +x Evaluation/codex/run_batch.sh
./Evaluation/codex/run_batch.sh
```

Default ids: `Evaluation/codex/TestList.txt`, else `BatchTest/TestList.txt`.

### Per-id trial counts (`TestList.txt`)

`--repeats` is the default when a testlist entry does not specify a count.

| Format | Example |
|--------|---------|
| Plain id list (legacy) | `[65, 124, 175]`  each id runs `--repeats` times |
| Objects in a list | `[{"id": 65, "repeats": 9}, {"id": 124, "repeats": 1}]` |
| Id  count map | `{"65": 9, "124": 1, "175": 3}` |

`--ids` on the CLI always uses `--repeats` for every id.

## Defaults

| Item | Default |
|------|---------|
| Model | `gpt-5.4` (`CODEX_MODEL`) |
| Reasoning | `xhigh` (`CODEX_REASONING_EFFORT`  `model_reasoning_effort`) |
| Sandbox | `workspace-write` |
| Run timeout | 1800s (`RUN_TIMEOUT_SECONDS`) |
| Workspace | `<RAIN_EVAL_WORKSPACE>/AgentTest_codex` |
| Results | `Evaluation/codex/Result/<M-D-H-M_batch>/` |

```bash
./Evaluation/codex/run_batch.sh --ids 4830 --workers 1
CODEX_MODEL=gpt-5.4 CODEX_REASONING_EFFORT=xhigh ./Evaluation/codex/run_batch.sh
```

## Codex-specific flags

| Flag | Default |
|------|---------|
| `--codex-model` | `gpt-5.4` |
| `--codex-reasoning-effort` | `xhigh` |
| `--codex-sandbox` | `workspace-write` |
| `--codex-bypass-approvals` | on (`--no-codex-bypass-approvals` to disable) |
| `--codex-skip-git-repo-check` | on |

Agent invocation: `codex exec --json -C <repo> -m <model> -c model_reasoning_effort="..."`.

## Token stats

**Authoritative source:** Codex local session rollout under `$CODEX_HOME/sessions/**/rollout-*-<thread_id>.jsonl` (default `~/.codex`). Use the last `token_count` events `total_token_usage` (cumulative for the exec session). `thread_id` comes from `thread.started` in `run_stdout.log` or `codex_thread_id` in `result.json`.

Field alignment matches ProofAgent batch:

- `tokens_prompt`  `input_tokens` (total prompt)
- `tokens_prompt_cache_hit`  `cached_input_tokens`
- `tokens_prompt_cache_miss`  prompt  hit
- `tokens_completion`  `output_tokens` + `reasoning_output_tokens` (all model output; aligns with ProofAgent `completion_tokens`)
- `tokens_reasoning`  `reasoning_output_tokens` only (breakdown in `result.json` / `summary.json`; not added again to `tokens_completion`)
- `tokens_total`  `tokens_prompt` + `tokens_completion` (= prompt + all output)

When `input_tokens` is below 200k, some rollouts report uncached prompt in `input_tokens` and bill cache separately; the parser then uses `tokens_prompt = input_tokens + cached_input_tokens`.

If the session file is missing, falls back to summing `turn.completed` usage in `codex exec --json` stdout (`tokens_parse_source=codex_exec_jsonl`).

Refresh one batch:

```bash
python3 Evaluation/codex/run_batch.py flush-tokens --batch-dir Evaluation/codex/Result/<stamp>_batch
```

Or all batches under `Result/`:

```bash
python3 Evaluation/codex/run_batch.py flush-tokens --all-batches
```

Backfill pure agent wall time on trial `result.json` (session rollout JSONL timestamps; `agent_timeout` + `run_rc=124`  1800s). Does not rewrite `summary.csv`:

```bash
python3 Evaluation/codex/reparse_agent_seconds.py --dry-run
python3 Evaluation/codex/reparse_agent_seconds.py --result-dir Evaluation/codex/Result/<stamp>_batch
```

## Note

Codex does not run ProofAgents in-loop `make` check; only post-run verify `make` is used for scoring.
