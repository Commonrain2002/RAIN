# Claude Code batch evaluation

Batch CoqStoq problems with **Claude Code** (`claude -p`), same pipeline as `Evaluation/opencode` (copy → make → agent → verify make → keyword scan).

## Prerequisites

- `claude` on `PATH`, authenticated (Anthropic API or configured provider)
- `COQSTOQ_PATH` or `--coqstoq-path`
- Coq / `make` / `scripts/coqstoq_minimal_copy.py`

For DeepSeek-backed Claude Code, add these environment variables before running the batch:

```bash
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_AUTH_TOKEN=$DEEPSEEK_API_KEY
export ANTHROPIC_MODEL=deepseek-v4-flash[1m]
export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-flash[1m]
export ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-flash[1m]
export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash[1m]
export CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash[1m]
export CLAUDE_CODE_EFFORT_LEVEL=max
```

## Quick start

```bash
cd /path/to/ProofAgent
chmod +x Evaluation/claude/run_batch.sh
./Evaluation/claude/run_batch.sh
```

Default ids: `Evaluation/claude/TestList.txt`, else `BatchTest/TestList.txt`.

## Defaults

| Item | Default |
|------|---------|
| Model | `deepseek-v4-flash[1m]` (`CLAUDE_MODEL`), 1M context variant (OpenCode batch still uses `deepseek/deepseek-v4-flash`) |
| Effort | `max` (`CLAUDE_EFFORT`), Claude Code’s `--effort` (reasoning effort, like OpenCode `--variant max`) |
| OpenCode-style run timeout | 1800s (`RUN_TIMEOUT_SECONDS`) |
| Verify `make` | 180s |
| Workspace | `<RAIN_EVAL_WORKSPACE>/AgentTest_claude` |
| Results | `Evaluation/claude/Result/` |

```bash
./Evaluation/claude/run_batch.sh --ids 4830 --workers 1
CLAUDE_MODEL=deepseek-v4-flash[1m] CLAUDE_EFFORT=max ./Evaluation/claude/run_batch.sh
# or another registered alias, e.g. CLAUDE_MODEL=sonnet
```

## Artifacts

Per trial under `Result/<M-D-H-M_batch>/id_<n>/trial_*/`: logs and `result.json`. Summaries sit in the same batch folder: `summary*.{csv,json}`.

The per-trial project workspace lives under `<agent-workspace>/AgentTest_claude/<batch>/id_<n>/trial_<k>/<project>/...` (see `workspace_trial_dir` and `repo_dir` in `result.json`).

## Time

- **`elapsed_seconds`** in `result.json`: wall-clock per trial (copy + post-copy make + `claude -p` + verify make + scan), same as OpenCode batch.

## Token stats

Aligned with Claude Code billing / **`/usage`** when possible:

1. Each trial uses a fresh **`--session-id`** (UUID), saved as `claude_session_id.txt`.
2. **First**: parse the final `claude -p --output-format json` line and sum all models in **`modelUsage`** (includes auxiliary models such as `deepseek-v4-flash[1m]`). This matches provider totals on the invoice.
3. **Else**: read `~/.claude/projects/<cwd-slug>/<session-id>.jsonl` (slug resolution tries `_` → `-` and a glob fallback; override home with `CLAUDE_HOME`). Per assistant **message id**, keep the fullest usage row (largest input + output + cache read + cache creation total) and sum those rows.
4. **Else**: top-level **`usage`** on the same JSON line (main model only; may be low by hundreds of tokens).
5. **`tokens_total`** = sum of `inputTokens` + `outputTokens` + `cacheReadInputTokens` + `cacheCreationInputTokens` across the chosen source.

**CSV alignment with ProofAgent batch:** provider non-cached input (`inputTokens` / `input_tokens`) → **`tokens_prompt_cache_miss`**; cache read → **`tokens_prompt_cache_hit`**; **`tokens_prompt`** = cache hit + cache miss (not raw input alone). Cache-creation tokens remain in `tokens_total` only.

Fields in `result.json`: `tokens_prompt`, `tokens_completion`, `tokens_prompt_cache_hit`, `tokens_prompt_cache_miss`, `tokens_total`, `tokens_parse_source`, `claude_session_id`.

Reparse after parser fixes:

```bash
python3 Evaluation/claude/reparse_tokens.py
```

## CLI flags

- `--claude-skip-permissions` / `--no-claude-skip-permissions` (default: on → `--dangerously-skip-permissions`)
- Other flags mirror `Evaluation/opencode/run_batch.py` (`--workers`, `--repeats`, `--out`, `--result-dir`, …)
