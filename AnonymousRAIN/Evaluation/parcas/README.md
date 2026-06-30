# Parcas Evaluation

ProofAgent batch evaluation on a **fixed** set of Parcas theorems (`TestList.json`). Catalog ids are stable; batch runs never re-sample. The default benchmark is **all eligible catalog entries** (~600, Abort `.v` excluded).

## Prerequisites

- `export PARCAS_PATH`  Parcas repository root (Rocq/dune project).
- `export PARCAS_OPAM_SWITCH=parcas` (or your global Parcas switch name).
- `eval "$(opam env --switch=$PARCAS_OPAM_SWITCH)"`  same switch as `packages.switch` / `vsrocq_split_sentences_Parcas`.
- LLM: `LLM_API_KEY` (or `DEEPSEEK_API_KEY` / `OPENROUTER_API_KEY`).
- Coq workspace copies: default under `<RAIN_EVAL_WORKSPACE>/AgentTest_parcas/` (override with `--out`).

## One-time setup (or when refreshing catalog / benchmark)

```bash
export PARCAS_PATH=/path/to/parcas
export PARCAS_OPAM_SWITCH=parcas
eval "$(opam env --switch=$PARCAS_OPAM_SWITCH)"

python3 Evaluation/parcas/gen_parcas_catalog.py
python3 Evaluation/parcas/gen_testlist_random.py --all   # all eligible ids (Abort .v excluded)
# optional subset benchmark: omit --all (default 50 longest + 50 random)
python3 Evaluation/parcas/verify_minimal_copy.py --ids 11 250 400
```

Smoke (one id): `./Evaluation/parcas/scripts/parcas_smoke.sh` or `SMOKE_ID=11 ./Evaluation/parcas/scripts/parcas_smoke.sh`

Commit `parcas_catalog.json`, `TestList.json`, and `TestList.manifest.json` after review. Re-run `gen_testlist_random.py --all` when refreshing the full benchmark.

**Abort rule:** any `src/**/*.v` whose text (comments stripped) contains `Abort` is excluded from the catalog (e.g. `src/logic/wp_logatom.v`). TestList ids are taken only from the remaining entries. After each trial, skip-keyword scan (`Admitted` / `Abort` / ...) **does not** apply to those upstream Abort files if they appear in a minimal copy as dependencies.

## Every batch run (same TestList ids)

```bash
export PARCAS_PATH=/path/to/parcas
export PARCAS_OPAM_SWITCH=parcas
eval "$(opam env --switch=$PARCAS_OPAM_SWITCH)"

./Evaluation/parcas/run_batch.sh
# optional: --testlist Evaluation/parcas/TestList.json --workers 5
```

Defaults: `deepseek-v4-flash`, `reasoning_effort=max`, `repeats=1` per TestList entry.

Results: `Evaluation/parcas/Result/<M-D-H-M_batch>/` (`summary.csv`, `summary_trials.csv`, `id_*/trial_*/`).

### OpenCode and Claude Code (same Parcas opam switch)

Same `TestList.json`, `parcas_meta.py`, and `parcas_minimal_copy.py` as ProofAgent; agent runs in the copied repo with `parcas_eval_build.sh` verify.
For Claude Code with DeepSeek, also set the `ANTHROPIC_*` / `CLAUDE_CODE_*` environment variables listed in `INSTALL.md`.

```bash
export PARCAS_OPAM_SWITCH=parcas
export PARCAS_PATH=/path/to/parcas

./Evaluation/parcas/opencode/run_batch.sh   # OpenCode: deepseek/deepseek-v4-flash, variant=max
./Evaluation/parcas/claude/run_batch.sh     # Claude CLI: deepseek-v4-flash[1m], effort=max
```

Workspaces: `<RAIN_EVAL_WORKSPACE>/AgentTest_parcas_opencode/` and `AgentTest_parcas_claude/`.  
Results: `Evaluation/parcas/opencode/Result/` and `Evaluation/parcas/claude/Result/`.

## Minimal copy

Batch and verify use [`parcas_minimal_copy.py`](parcas_minimal_copy.py) (full `src/` + dune `make` under `PARCAS_OPAM_SWITCH`). Legacy `scripts/coqstoq_minimal_copy.py` is only via `verify_minimal_copy.py --use-coqstoq-copy`.

## Layout

| File | Role |
|------|------|
| `parcas_catalog.json` | All eligible theorems with stable ids |
| `TestList.json` | Fixed `{id, repeats}` list for batch |
| `parcas_meta.py` | Meta JSON per catalog id |
| `run_batch.py` / `run_batch.sh` | Batch driver |
| `verify_minimal_copy.py` | Gate: copy + `make -j1` on sample ids |
