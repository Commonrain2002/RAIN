# Installation

These steps set up the anonymized PALM reproduction package and the CoqStoq evaluation workflow. The scripts use `COQSTOQ_PATH` as the CoqStoq root directory.

## 1. Use the CoqStoq Python Environment

Use CoqStoq's Python environment as the base environment, then install PALM's
Python-only dependencies into that same environment. Set `COQSTOQ_PATH` to the
CoqStoq root directory, the directory that contains `pyproject.toml` and
`coqstoq.opam`:

```bash
export COQSTOQ_PATH="/path/to/CoqStoq"
```

Activate CoqStoq's Python environment:

```bash
cd "$COQSTOQ_PATH"
poetry install
poetry shell
```

From the AnonymousPALM root directory, install PALM's dependencies into that
active environment:

```bash
python -m pip install \
  rank-bm25==0.2.2 \
  replicate==0.26.0 \
  openai==1.30.3 \
  httpx==0.27.2 \
  sexpdata==1.0.1 \
  pexpect==4.9.0 \
  tiktoken==0.5.2 \
  "tokenizers>=0.15.0" \
  chardet==5.2.0
```

Verify the Python dependencies:

```bash
python -c "import openai, sexpdata, pexpect, rank_bm25, tokenizers"
python -c "import coqstoq"
```

If CoqStoq is installed in an existing conda environment instead of Poetry,
activate that environment and run the same `python -m pip install ...` command
there. `palm.yml` is kept as a standalone dependency reference; it is not the
recommended setup for CoqStoq evaluation.

## 2. Configure the DeepSeek Endpoint

Use environment variables. Do not write API keys into source files.

```bash
read -rsp "DEEPSEEK_API_KEY: " DEEPSEEK_API_KEY
export OPENAI_API_KEY="$DEEPSEEK_API_KEY"
export OPENAI_BASE_URL="https://api.deepseek.com"
export PALM_MODEL="deepseek-v4-flash"
export PALM_REASONING_EFFORT="max"
```

PALM uses a generic tokenizer for prompt trimming unless
`deepseek_v3_tokenizer/tokenizer.json` is provided locally.

## 3. Extend the CoqStoq opam Switch

PALM talks to Coq through SerAPI and uses CoqHammer tactics during proof search.
For CoqStoq evaluation, set `PALM_OPAM_SWITCH=coqstoq` and install PALM's
additional Coq-side dependencies into that switch:

```bash
opam init --bare -y
opam repo add coq-released https://coq.inria.fr/opam/released || true

export PALM_OPAM_SWITCH="coqstoq"
opam switch import "$COQSTOQ_PATH/coqstoq.opam" \
  --switch="$PALM_OPAM_SWITCH" \
  --repos=default,coq-released=https://coq.inria.fr/opam/released || true
eval "$(opam env --switch="$PALM_OPAM_SWITCH")"
opam install -y coq-serapi coq-hammer coq-hammer-tactics
```

Keep `PALM_OPAM_SWITCH=coqstoq` in the environment when running PALM.

CoqHammer may also require external ATP binaries such as E prover, Vampire, Z3, or CVC. Install the ATPs supported by your platform and ensure they are on `PATH`.

## 4. Build the CoqStoq Projects

Build the Coq projects used by CoqStoq before running PALM. This step is
required because some CoqStoq projects generate build metadata during
configuration/build. For example, CompCert needs files such as `_CoqProject` and
`Makefile.config`; without them, PALM's minimal copy step may copy only the
target file and miss dependencies such as Flocq's `Core.v`, `Round.v`, and
`BinarySingleNaN.v`.

```bash
cd "$COQSTOQ_PATH"
eval "$(opam env --switch="$PALM_OPAM_SWITCH")"
python coqstoq/build_projects.py
```

For a quick CompCert sanity check:

```bash
test -f "$COQSTOQ_PATH/test-repos/compcert/_CoqProject"
test -f "$COQSTOQ_PATH/test-repos/compcert/Makefile.config"
```

## 5. Check the CoqStoq Path

After activating the CoqStoq Python environment from step 1, verify that
`COQSTOQ_PATH` points to the CoqStoq root directory:

```bash
test -f "$COQSTOQ_PATH/pyproject.toml"
test -f "$COQSTOQ_PATH/coqstoq.opam"
python -c "import coqstoq"
```

If `import coqstoq` fails and your CoqStoq checkout is a Python package, install
it into the active Python environment:

```bash
python -m pip install -e "$COQSTOQ_PATH"
```

If CoqStoq is installed in a different Python environment, set:

```bash
export COQSTOQ_PYTHON="/path/to/python-with-coqstoq"
```

## 6. Runtime Paths

Recommended runtime variables:

```bash
export OPAMROOT="${OPAMROOT:-$HOME/.opam}"
export PALM_OPAM_SWITCH="coqstoq"
export PALM_BATCH_WORKSPACE="$PWD/workspace/AgentTest_PALM"
export PALM_COPY_OUTPUT_ROOT="$PWD/coqstoq_copies"
```

For manual, non-batch runs, `PALM_PROJECTS_PATH` must point to a directory containing copied project directories:

```bash
export PALM_PROJECTS_PATH="$PWD/coqstoq_copies"
```

The batch runner sets `PALM_PROJECTS_PATH`, `PALM_DATA_PATH`, and `PALM_EVAL_PATH` per trial automatically.

## 7. Run a CoqStoq Batch Evaluation

Use `Eval/TestList.txt` or pass theorem ids directly:

```bash
bash Eval/run_batch.sh --workers 1 --repeats 1 --batch-stamp smoke_test
```

Run selected theorem ids:

```bash
bash Eval/run_batch.sh --ids 3079 --workers 1 --repeats 1 --batch-stamp smoke_3079
```

Outputs are written to:

```text
Eval/Result/<batch-stamp>/
workspace/AgentTest_PALM/<batch-stamp>/
```

These generated directories are ignored by `.gitignore`.

## 8. Run One CoqStoq Theorem Manually

Copy the minimal dependency tree:

```bash
python Eval/coqstoq_minimal_copy.py 3079 --split test -o "$PALM_COPY_OUTPUT_ROOT" --force
```

Set the copied project parent and extract PALM data:

```bash
export PALM_PROJECTS_PATH="$PALM_COPY_OUTPUT_ROOT"
python -m src.extract_data --proj=compcert --file=flocq/IEEE754/Binary.v
```

Run PALM:

```bash
python -m src.main \
  --proj=compcert \
  --file=flocq/IEEE754/Binary.v \
  --theorem=FLT_format_B2R \
  --exp_name=manual_test \
  --threads=1 \
  -backtrack
```

## 9. Optional CoqGym Setup

The `coq_projects/` directory contains the original PALM helper scripts for CoqGym-style projects:

```bash
cd coq_projects
./prepare.sh
./build.sh
```

For CoqGym-style runs, set:

```bash
export PALM_PROJECTS_PATH="/path/to/coq_projects"
```

Then run:

```bash
python -m src.main --proj=verdi --exp_name=test --threads=1 -skip -backtrack -intersect
```

## 10. Sanity Checks

```bash
python -m compileall src Eval
python Eval/coqstoq_meta.py --id 3079 --split test
opam exec --switch="$PALM_OPAM_SWITCH" -- which sertop
```

The second command requires `COQSTOQ_PATH` and the `coqstoq` Python package in
the active CoqStoq Python environment. The third command confirms that SerAPI is
available from the CoqStoq opam switch.
