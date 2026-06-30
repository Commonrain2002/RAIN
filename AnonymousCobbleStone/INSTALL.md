# Installation and Reproduction Guide

This archive is an anonymized, runnable copy of the Cobblestone reproduction
code. It includes source code, configuration templates, Coq project files, and
dataset declaration files under `data/`. It intentionally does not include
large generated result directories such as `evaluations/` or `data/evaluation/`.

## 1. System Requirements

Recommended platform:

- Linux or WSL2
- Python 3.11
- Conda or another Python virtual environment manager
- opam 2.x
- Git, curl, make, gcc/g++, unzip
- Network access for Python packages, Git dependencies, opam packages, and LLM APIs

Optional but recommended for hammer-enabled runs:

- E prover
- Vampire
- CVC4
- Z3 with TPTP support

See `doc/installing_coqhammer.md` for solver installation notes.

## 2. Create the Python Environment

The simplest path is to use the helper script:

```bash
cd AnonymousCobbleStone
./scripts/setup-cobble-env.bash
```

This creates a Conda environment named `cobble` if needed and installs this
package in editable mode.

Manual equivalent:

```bash
cd AnonymousCobbleStone
conda create -y -n cobble python=3.11
conda activate cobble
pip install -e .
```

If you prefer not to use Conda:

```bash
cd AnonymousCobbleStone
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

`requirements.txt` is provided as a fallback for pip-based environments. The
Poetry configuration in `pyproject.toml` is the preferred dependency source.

## 3. Configure Environment Variables

Create a local `.env` file:

```bash
cp .env.example .env
```

Then edit `.env`.

Required for DeepSeek runs:

```bash
DEEPSEEK_API_KEY=<your key>
PROJECTS_ROOT=coq-projects
```

Required for OpenAI runs instead of DeepSeek:

```bash
OPENAI_SECRET=<your key>
PROJECTS_ROOT=coq-projects
```

Useful optional settings:

```bash
LOG_LEVEL=INFO
LOG_FILE=logs
LOG_LEVELS_FILE=log_levels.yaml
MAX_OBSERVATION_TOKENS=128000
MAX_CHAT_COMPLETION_TOKENS=300000
LLM_REQUEST_TIMEOUT_SEC=600
LLM_MAX_RETRIES=50
DEEPSEEK_REASONING_EFFORT=max
DEEPSEEK_TOKENIZER_DIR=deepseek_v3_tokenizer
```

The `.env` file is local configuration. Do not commit real API keys.

## 4. Set Up Coq and opam Switches

Different datasets require different Coq versions. The included dataset files
record the required version in each example.

The anonymized archive includes checked-out Coq sources for PnVRocqLib and
Wigderson. The `coq-projects/coqgym` and `coq-projects/coq-bb5` directories are
present as placeholders because those submodules were not checked out in the
source workspace. If you need to run CoqGym or BB5 experiments, fetch those
projects before running the corresponding commands:

```bash
git clone https://github.com/efirst/coqgym.git coq-projects/coqgym
(cd coq-projects/coqgym && git checkout d0c5e51bf846992b718ef45924bc8f48be7d6bdc)

git clone https://github.com/ccz181078/Coq-BB5.git coq-projects/coq-bb5
(cd coq-projects/coq-bb5 && git checkout 632ba68b03adb27f4f6faaa76b83db934d5ecbba)
```

For the default PnVRocqLib run in `run.sh`, create a `coq-8.18` switch:

```bash
opam init --disable-sandboxing --auto-setup
opam repo add coq-released https://coq.inria.fr/opam/released --all-switches --set-default
opam switch create coq-8.18 ocaml-base-compiler.5.1.0
eval "$(opam env --switch=coq-8.18 --set-switch)"
opam pin add -y coq 8.18.0
opam install -y coq-serapi coq-hammer coq-lsp
make -C coq-projects/PnVRocqLib -j"$(nproc)"
```

For Wigderson runs, create the `coq-8.13` switch:

```bash
./scripts/make-switch.bash 8.13
eval "$(opam env --switch=coq-8.13 --set-switch)"
make -C coq-projects/coq-wigderson -j"$(nproc)"
```

For CoqGym or older datasets, use the matching switch files under `switches/`
as references and create the corresponding switch:

```bash
./scripts/make-switch.bash 8.10
./scripts/make-switch.bash 8.11
./scripts/make-switch.bash 8.12
```

## 5. Verify the Installation

Check that the CLI starts:

```bash
conda activate cobble
./scripts/goal-decomposition --help
./scripts/zero-shot-pass-at-k --help
./scripts/next-tactic --help
```

Run the PnVRocqLib smoke test:

```bash
eval "$(opam env --switch=coq-8.18 --set-switch)"
./scripts/smoke-pnv-goal-decomposition.sh
```

The smoke test writes output under:

```text
data/evaluation/goal_decomposition/
```

That directory is generated output and is not included in this anonymized
archive.

## 6. Run the Default Reproduction Command

The provided `run.sh` runs the PnVRocqLib100 Cobblestone goal-decomposition
configuration with DeepSeek:

```bash
eval "$(opam env --switch=coq-8.18 --set-switch)"
conda activate cobble
./run.sh
```

Useful overrides:

```bash
UUID=<run-id> ./run.sh
NUM_PROCESSES=1 ./run.sh
MAX_NODES_TO_EXPAND=300 ./run.sh
EXAMPLE_WALL_TIMEOUT_SEC=10800 ./run.sh
```

Use fewer processes if Coq uses too much memory or the API returns rate-limit
errors.

## 7. Run Other Evaluation Modes

Zero-shot examples:

```bash
./scripts/zero-shot-pass-at-k run -d test -c preceding-lemmas-only
./scripts/zero-shot-pass-at-k run -d wigderson_test -c preceding-lemmas-only
```

Cobblestone goal decomposition examples:

```bash
./scripts/goal-decomposition run -d wigderson_test -t -c preceding-lemmas-only -m 5
./scripts/goal-decomposition run -d pnvrocqlib_test -t -c preceding-lemmas-only -m 5
```

Tactic-by-tactic search examples:

```bash
./scripts/next-tactic run -d wigderson_test -c preceding-lemmas-only -m 20 -x 20 -n 5
./scripts/next-tactic run -d test -c preceding-lemmas-only -t -m 20 -x 20 -n 5
```

Use `--help` on any command to inspect the full option set.

## 8. Notes About the Anonymized Package

- Real API keys are not included. `.env` and `.env.example` contain placeholders.
- Local virtual environments, logs, caches, `.git`, `evaluations/`, and
  `data/evaluation/` are intentionally omitted.
- `data/` contains dataset declarations and baseline result JSON files used by
  the evaluation code. Generated run outputs are written to `data/evaluation/`
  and are intentionally not bundled.
- Notebook execution outputs were stripped because they often contain absolute
  paths, kernel commands, and transient run metadata.
- The package is relocatable: paths are derived from the repository root and
  `PROJECTS_ROOT=coq-projects`.
- `CoqStoq` was not bundled as a local path dependency because the runnable
  code in this archive does not import it. If you need to rerun exploratory
  dataset-generation notebooks that reference it, install that dependency
  separately and document its source in your reproduction notes.

## 9. Troubleshooting

If Python cannot import a dependency, reinstall the package inside the active
environment:

```bash
pip install -e .
```

If Coq cannot find project libraries, check:

```bash
echo "$PROJECTS_ROOT"
opam switch show
which sertop
coqc -v
```

If hammer is enabled and proof search fails immediately, verify the external
solvers are on `PATH`:

```bash
eprover --version
vampire --version
cvc4 --version
z3 --version
```
