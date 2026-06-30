# tips on using vscoq

To manually interact with a file from coqgym:
1. set `coq.coqProjectRoot` to the root of the project
2. set `coqtop.binPath` to the path of the `bin` directory of the switch you'd like to use (e.g. `$HOME/.opam/coq-8.10/bin/`).

If you get an error about the package path when importing files of the same package, you may need to create an `_CoqProject` file in the root of the project.
```
... contains library
Goedel.folProof and not library folProof
```
