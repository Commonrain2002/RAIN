# Sentence Splitter

This directory contains the source for the VsRocq-based sentence splitter. Build it inside the same opam switch used by the target Coq or Rocq project.

```bash
opam install ./vsrocq-split-extras.opam --deps-only --no-upgrade
make
```

The artifact does not ship prebuilt wrapper scripts under `Sentence/`. After building, copy or symlink `_build/default/tools/vsrocq_split_sentences.exe` into a directory on `PATH` with the command name expected by the evaluation: `vsrocq_split_sentences_CoqStoq`, `vsrocq_split_sentences_CS2`, `vsrocq_split_sentences_PnV`, or `vsrocq_split_sentences_Parcas`. You can also pass the executable path explicitly with `--parse-sentence-script` where supported.
