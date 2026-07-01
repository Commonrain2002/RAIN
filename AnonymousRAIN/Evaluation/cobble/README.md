# Cobble / PnVRocqLib Evaluation

Batch ProofAgent on PnVRocqLib problems listed in `Evaluation/cobble/TestList`. IDs are 1-based line numbers in that file.

## Prerequisites

- `COBBLE_PROJECT_ROOT` or `--cobble-project-root`
- `LLM_API_KEY`, `DEEPSEEK_API_KEY`, or `OPENROUTER_API_KEY`
- CoqStoq-compatible Coq 8.18 environment active
- Original PnVRocqLib checkout compiled successfully before metadata extraction
- Sentence splitter built in the same environment and available as `vsrocq_split_sentences_PnV`, or passed with `--parse-sentence-script`

Compile the original project first:

```bash
eval "$(opam env --switch=coqstoq --set-switch)"
export COBBLE_PROJECT_ROOT=<PnVRocqLib-root>
cd "$COBBLE_PROJECT_ROOT"
coq_makefile -f _CoqProject -o Makefile
make -j1
```

## Quick Start

```bash
cd <artifact-root>
python3 Evaluation/cobble/cobble_meta.py --id 2 --project-root "$COBBLE_PROJECT_ROOT"
python3 Evaluation/cobble/run_batch.py --ids 2 --workers 1
```

If `--ids` is omitted, the runner reads all entries from `Evaluation/cobble/TestList`.

## Common Options

```bash
python3 Evaluation/cobble/run_batch.py --ids 2 5 9 --workers 2 --repeats 3
python3 Evaluation/cobble/run_batch.py --testlist Evaluation/cobble/TestList
python3 Evaluation/cobble/run_batch.py --out ${RAIN_EVAL_WORKSPACE}/AgentTest_cobble \
  --result-dir Evaluation/cobble/proofagent/Result/my_run
```

Defaults: `deepseek-v4-flash`, `reasoning_effort=max`, `repeats=1`.

Results are written under `Evaluation/cobble/proofagent/Result/<M-D-H-M_batch>/` unless `--result-dir` is provided.
