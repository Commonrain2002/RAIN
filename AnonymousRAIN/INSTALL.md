# INSTALL

This file covers artifact setup, local validation, and the shared prerequisites for full evaluations. For suite-specific batch commands, see the README in the relevant `Evaluation/` subdirectory.

## 1. Base Tools

Install these first:

- .NET SDK 10.0 or newer preview compatible with `net10.0`
- Python 3.10 or newer
- `pytest` for smoke and full tests
- opam, OCaml, dune, and Coq or Rocq for proof checking
- `make`, `bash`, and standard Unix command-line tools

Then restore and build the .NET test project:

```bash
cd <artifact-root>
dotnet restore ProofAgent.Tests/ProofAgent.Tests.csproj
dotnet build ProofAgent.Tests/ProofAgent.Tests.csproj
python3 -m pip install pytest
```

## 2. Sentence Splitter

The artifact does not ship prebuilt sentence splitter commands under `Sentence/`. Build the splitter in the same opam switch as the target Coq or Rocq project. The binary is tied to the target Coq/Rocq runtime and library layout.

```bash
cd <artifact-root>/SentenceScript
opam install ./vsrocq-split-extras.opam --deps-only
make
```

Copy or symlink the built executable into a directory on `PATH` using the command name expected by the evaluation:

| Evaluation | Expected command name |
|------------|-----------------------|
| CoqStoq / ProofAgent / OpenCode / Claude / Codex | `vsrocq_split_sentences_CoqStoq` |
| CoqStoq step statistics primary splitter | `vsrocq_split_sentences_CS2` |
| Cobble / PnVRocqLib | `vsrocq_split_sentences_PnV` |
| Parcas | `vsrocq_split_sentences_Parcas` |

Example for CoqStoq-based evaluations:

```bash
mkdir -p <tool-bin>
cp <artifact-root>/SentenceScript/_build/default/tools/vsrocq_split_sentences.exe \
  <tool-bin>/vsrocq_split_sentences_CoqStoq
export PATH="<tool-bin>:$PATH"
```

Repeat the copy or symlink with the other command names needed by your selected evaluation. Alternatively, pass the executable path explicitly with `--parse-sentence-script` where the evaluation script exposes that option, or set `parseSentenceScript` in `proofagent.config.json`.

The sentence splitter uses Coq/VsRocq parsing, not plain text parsing. It reads the target project's `_CoqProject` or `_RocqProject` and needs imported libraries, notations, and grammar extensions to be available. Therefore the original target repository must already compile successfully and contain the required `.vo` files before metadata extraction, smoke tests, or batch evaluation.

## 3. ProofAgent Runtime

For a direct ProofAgent run, copy `proofagent.config.example.json` to `proofagent.config.json` in a run directory and edit these fields:

- `projectRoot`: target Coq or Rocq project root.
- `targetCoqFile`: target file relative to `projectRoot`.
- `checkCommand`: build command run in `projectRoot`.
- `parseSentenceScript`: sentence splitter command, for example `vsrocq_split_sentences_CoqStoq` after adding your splitter directory to `PATH`.
- `baseUrl`: OpenAI-compatible chat completions endpoint.
- `model` and `reasoningEffort`: backend model settings.
- `extraReadableRootPaths`: optional read-only roots, usually omitted unless the evaluation allows them.

Set the API key, then run:

```bash
export LLM_API_KEY=...

cd <run-directory>
<artifact-root>/run.sh
```

## 4. Shared Evaluation Variables

Full evaluation scripts need external benchmark repositories and agent CLIs. Set only the variables for the suites you run:

- `COQSTOQ_PATH`: CoqStoq checkout.
- `COBBLE_PROJECT_ROOT`: PnVRocqLib project root.
- `PARCAS_PATH`: Parcas project root.
- `PARCAS_OPAM_SWITCH`: opam switch for Parcas, default `parcas`.
- `COQ_LIB_ROOT`: optional Coq library root exposed to the agent when an evaluation enables extra reads.
- `RAIN_EVAL_WORKSPACE`: writable workspace for copied benchmark projects, default `.rain-eval-workspaces`.
- `RAIN_COPY_OUTPUT`: default parent for minimal copies, default `.rain-minimal-copies`.

Detailed commands are documented in:

- `Evaluation/proofagent/README.md`
- `Evaluation/cobble/README.md`
- `Evaluation/claude/README.md`
- `Evaluation/codex/README.md`
- `Evaluation/opencode/README.md`
- `Evaluation/parcas/README.md`

## 5. Benchmark Environments

### CoqStoq-Based Evaluations

ProofAgent, OpenCode, Claude, and Codex CoqStoq evaluations need:

- `COQSTOQ_PATH=<CoqStoq-root>`
- the CoqStoq opam switch active
- `vsrocq_split_sentences_CoqStoq` on `PATH`

### Cobble / PnVRocqLib

Cobble uses PnVRocqLib and can run in the same CoqStoq Coq 8.18 environment. Before testing Cobble, compile the original PnVRocqLib checkout pointed to by `COBBLE_PROJECT_ROOT`; the batch runner extracts metadata from this original repository before creating minimal copies.

```bash
eval "$(opam env --switch=coqstoq --set-switch)"
export COBBLE_PROJECT_ROOT=<PnVRocqLib-root>
cd "$COBBLE_PROJECT_ROOT"
coq_makefile -f _CoqProject -o Makefile
make -j1
```

Cobble's splitter command is `vsrocq_split_sentences_PnV`. Build the splitter in the same CoqStoq environment and put it on `PATH` with that name.

Before launching a batch, check the metadata path:

```bash
cd <artifact-root>
vsrocq_split_sentences_PnV "$COBBLE_PROJECT_ROOT/theories/Data/Aczel.v" | grep extenesionality
python3 Evaluation/cobble/cobble_meta.py --id 2 --project-root "$COBBLE_PROJECT_ROOT"
```

### Parcas

Parcas evaluation needs the Coq opam repository in addition to the default opam repository. Add it to the switch before importing the exported Parcas environment; otherwise packages such as `coq-stdpp`, `coq-iris`, and `coq-equations` may be skipped as unavailable.

```bash
opam switch create parcas-artifact --empty
opam repo add coq-released https://coq.inria.fr/opam/released --switch=parcas-artifact
opam update --switch=parcas-artifact
opam switch import --switch=parcas-artifact <path-to-parcas-sentence.switch>
eval "$(opam env --switch=parcas-artifact --set-switch)"
```

Check that the required Parcas packages are present:

```bash
opam list --installed | grep -E 'coq-stdpp|coq-iris|coq-equations|coq '
```

For Parcas batch runs, use the same switch and build the Parcas splitter as `vsrocq_split_sentences_Parcas`:

```bash
export PARCAS_OPAM_SWITCH=parcas-artifact
export PARCAS_PATH=<parcas-root>
eval "$(opam env --switch=$PARCAS_OPAM_SWITCH --set-switch)"
```

## 6. Agent-Specific Notes

### Claude Code With DeepSeek

Claude Code evaluation uses DeepSeek through the Anthropic-compatible endpoint. Set `DEEPSEEK_API_KEY` first, then export these variables in the shell that launches Claude batches:

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

Other DeepSeek-based runners use their own provider configuration and do not add the Claude-only `[1m]` model suffix.

## 7. Final Artifact Tests

These checks validate the packaged artifact itself. They do not launch full benchmark evaluations or call paid agent APIs unless your local environment does so through customized configuration.

```bash
./scripts/test_smoke.sh
./scripts/test_full.sh
./Evaluation/smoke.sh
```

## 8. Full Evaluations

The real benchmark launchers are under `Evaluation/`. They can be expensive and require benchmark repositories, compiled target projects, Coq/Rocq switches, API keys, sentence splitter commands on `PATH`, and any external agent CLIs used by the selected suites.

After the suite-specific prerequisites are ready, `Evaluation/full.sh` is the guarded entry point for launching one or more real evaluations:

```bash
RAIN_RUN_FULL_EVAL=1 ./Evaluation/full.sh proofagent parcas cobble
```
