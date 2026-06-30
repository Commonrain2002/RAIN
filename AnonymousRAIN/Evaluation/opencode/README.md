# OpenCode batch evaluation

Batch CoqStoq problems with **OpenCode** (default **DeepSeek V4 Flash**, variant **max**; optional **GPT 5.4** via preset on **OpenAI/Codex OAuth** or **OpenRouter**). Same prompt and verify flow as `BatchTest/run_batch`, agent replaced by `opencode run`.

## Prerequisites

- `opencode` on `PATH` (`opencode providers` / DeepSeek credentials configured)
- `COQSTOQ_PATH` or `--coqstoq-path`
- Coq workspace tooling (`make`, `python3`, `scripts/coqstoq_minimal_copy.py` under ProofAgent root)

## Quick start

```bash
cd /path/to/ProofAgent
chmod +x Evaluation/opencode/run_batch.sh
./Evaluation/opencode/run_batch.sh
```

Default ids: `Evaluation/opencode/TestList.txt`, else `BatchTest/TestList.txt`.

## Common options

Same as `BatchTest/run_batch.sh` where applicable:

```bash
./Evaluation/opencode/run_batch.sh --ids 124 5156 --workers 2 --repeats 3
./Evaluation/opencode/run_batch.sh --testlist BatchTest/TestList.txt --workers 5
./Evaluation/opencode/run_batch.sh --out ${RAIN_EVAL_WORKSPACE}/AgentTest_opencode \
  --result-dir Evaluation/opencode/Result/my_run
```

OpenCode-specific:

| Flag | Default |
|------|---------|
| `--opencode-preset` | (none)  see presets below |
| `--opencode-model` | `deepseek/deepseek-v4-flash` |
| `--opencode-variant` | `max` |
| `--opencode-skip-permissions` | on (`--no-opencode-skip-permissions` to disable) |

**Model presets** (`--opencode-preset` / `OPENCODE_PRESET`):

| Preset | OpenCode model | Credentials |
|--------|----------------|-------------|
| `deepseek-v4-flash` | `deepseek/deepseek-v4-flash` | DeepSeek API |
| `openai-gpt-5.4`, `codex-gpt-5.4`, or `gpt-5.4` | `openai/gpt-5.4`, variant **`xhigh`** | `opencode providers login` (OpenAI OAuth, same path as Codex) |
| `openrouter-gpt-5.4` | `openrouter/openai/gpt-5.4`, variant **`xhigh`** | `OPENROUTER_API_KEY` or `opencode providers login -p openrouter` |
| `qwen3.5-flash` | `alibaba-cn/qwen3.5-flash`, variant **`xhigh`** | `DASHSCOPE_API_KEY` (built-in Alibaba China) |

```bash
# GPT 5.4 via OpenAI / Codex OAuth (openai/gpt-5.4)
./Evaluation/opencode/run_batch.sh --opencode-preset codex-gpt-5.4 --ids 4830
OPENCODE_PRESET=openai-gpt-5.4 ./Evaluation/opencode/run_batch.sh

# GPT 5.4 via OpenRouter
./Evaluation/opencode/run_batch.sh --opencode-preset openrouter-gpt-5.4 --ids 4830
OPENCODE_PRESET=openrouter-gpt-5.4 ./Evaluation/opencode/run_batch.sh

# Qwen 3.5 Flash
./Evaluation/opencode/run_batch.sh --opencode-preset qwen3.5-flash --ids 124
OPENCODE_PRESET=qwen3.5-flash ./Evaluation/opencode/run_batch.sh

# Or pass the model id directly (no preset)
./Evaluation/opencode/run_batch.sh --opencode-model openai/gpt-5.4 --opencode-variant xhigh
./Evaluation/opencode/run_batch.sh --opencode-model openrouter/openai/gpt-5.4 --opencode-variant xhigh
```

Environment overrides in `run_batch.sh`: `RUN_TIMEOUT_SECONDS`, `OPENCODE_PRESET`, `OPENCODE_MODEL`, `OPENCODE_VARIANT`.

## Outputs

Under `--result-dir` (default `Evaluation/opencode/Result/<M-D-H-M_batch>/`):

- `summary_trials.csv`, `summary_by_id.csv`, `summary.csv`, `summary.json` (same folder as per-id logs)
- `id_<n>/trial_*/`  copy logs, `run_stdout.log` (JSON events), verify `make`, `result.json`

Success criteria match BatchTest: final `make` succeeds and no forbidden keywords (e.g. `Admitted`) outside comments.

## Note

OpenCode does not run ProofAgents in-loop `make` check; only post-run verify `make` is used for scoring.

## Token stats

Aligned with **`opencode stats`** (same as the `session` row in `~/.local/share/opencode/opencode.db`):

- **Input**  `tokens_prompt_cache_miss` (ProofAgent-style cache miss)
- **Cache Read**  `tokens_prompt_cache_hit`
- **`tokens_prompt`**  input + cache read (ProofAgent-style total prompt)
- **Output + Reasoning**  `tokens_completion`
- **Reasoning**  `tokens_reasoning` (kept for inspection; already included in `tokens_completion`)
- **Session total**  `tokens_total` = input + output + reasoning + cache read + cache write

After each run, the batch script reads `sessionID` from JSON logs and queries the DB (`OPENCODE_DB_PATH` to override). It does **not** use `step_finish.tokens.total` (that value is per-step context size, often ~35K, not ~600K session usage).

Refresh existing trials: `python3 Evaluation/opencode/reparse_tokens.py`

Manual CLI test must include a prompt: `opencode run --format json "..."`.
