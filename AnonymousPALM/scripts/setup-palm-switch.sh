#!/usr/bin/env bash
set -euo pipefail

SWITCH="${PALM_OPAM_SWITCH:-coqstoq_palm}"
OCAML="${PALM_OCAML_VERSION:-ocaml-base-compiler.4.14.1}"
COQ="${PALM_COQ_VERSION:-8.16.1}"

opam repo add coq-released https://coq.inria.fr/opam/released || true

if opam switch list --short | grep -qx "$SWITCH"; then
  echo "Switch $SWITCH already exists."
else
  opam switch create "$SWITCH" "$OCAML"
fi

eval "$(opam env --switch="$SWITCH")"
opam install -y "coq=$COQ" coq-serapi coq-hammer coq-hammer-tactics

echo "Done. Active switch: $SWITCH"
echo "Run: eval \"\$(opam env --switch=$SWITCH)\""
