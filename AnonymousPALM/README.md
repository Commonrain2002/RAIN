# Anonymous PALM Reproduction

This repository contains an anonymized reproduction package for PALM-style proof automation with large language models. It includes the PALM source code, CoqStoq batch evaluation scripts, and lightweight configuration files.

No API keys, local machine paths, local user names, institution details, email addresses, generated evaluation logs, or CoqStoq dataset files from this reproduction are included. Upstream license and attribution text is preserved.

## Repository Layout

```text
AnonymousPALM/
  src/                         PALM source code
  Eval/                        CoqStoq evaluation scripts
  data/path.json               Coq project load-path and opam switch mapping
  data/intersection.json       PALM/CoqGym evaluation theorem list
  deepseek_v3_tokenizer/       Optional DeepSeek tokenizer helper files
  coq_projects/                Optional CoqGym build scripts from PALM
  palm.yml                     Conda environment specification
  INSTALL.md                   Environment setup and run instructions
```

`Eval/Result/` and `evaluation/` are intentionally excluded because they contain generated experiment artifacts.

## Configuration

Runtime configuration is environment-variable based. The most important variables are:

```bash
read -rsp "OPENAI_API_KEY: " OPENAI_API_KEY
export OPENAI_API_KEY
export PALM_MODEL="gpt-4o-mini"
export OPENAI_BASE_URL=""                 # set for OpenAI-compatible providers
export COQSTOQ_PATH="/path/to/CoqStoq"
export PALM_PROJECTS_PATH="/path/to/copied/projects"
export OPAMROOT="$HOME/.opam"
```

For CoqStoq batch evaluation, `COQSTOQ_PATH` must point to the CoqStoq dataset root. If you use a separate Python environment for the `coqstoq` package, also set `COQSTOQ_PYTHON`.

See [INSTALL.md](INSTALL.md) for the complete setup.
