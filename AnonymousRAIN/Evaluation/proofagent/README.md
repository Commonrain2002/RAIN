# ProofAgent CoqStoq Evaluation

Batch CoqStoq problems with ProofAgent. The runner creates a minimal copy, writes `proofagent.config.json`, runs `run.sh`, verifies `make`, and scans for forbidden proof-bypass keywords.

## Prerequisites

- `COQSTOQ_PATH` or `--coqstoq-path`
- `LLM_API_KEY`, `DEEPSEEK_API_KEY`, or `OPENROUTER_API_KEY`
- CoqStoq opam environment active
- Sentence splitter built in the same CoqStoq environment and available as `vsrocq_split_sentences_CoqStoq`, or passed with `--parse-sentence-script`

## Quick Start

```bash
cd <artifact-root>
export COQSTOQ_PATH=<CoqStoq-root>
export LLM_API_KEY=...

./Evaluation/proofagent/run_batch.sh --ids 4830 --workers 1
```

If `--ids` is omitted, the runner reads `Evaluation/proofagent/TestList.txt`, then falls back to `Evaluation/BatchTest/TestList.txt`.

## Common Options

```bash
./Evaluation/proofagent/run_batch.sh --ids 124 5156 --workers 2 --repeats 3
./Evaluation/proofagent/run_batch.sh --testlist Evaluation/proofagent/TestList.txt
./Evaluation/proofagent/run_batch.sh --out ${RAIN_EVAL_WORKSPACE}/AgentTest_proofagent \
  --result-dir Evaluation/proofagent/Result/my_run
```

Defaults: `deepseek-v4-flash`, `reasoning_effort=max`, `repeats=1`.

Results are written under `Evaluation/proofagent/Result/<M-D-H-M_batch>/` unless `--result-dir` is provided.
