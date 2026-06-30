#!/usr/bin/env bash
# Install only the OCaml libs missing from a typical Coq/Iris switch.
# Run inside the target project's opam switch (coqc must already work).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v coqc >/dev/null && ! command -v rocq >/dev/null; then
  echo "install-extras.sh: need coqc or rocq in PATH (eval \$(opam env))" >&2
  exit 1
fi

echo "install-extras.sh: dry-run (no changes)..."
opam install ./vsrocq-split-extras.opam --no-upgrade --dry-run

echo
read -r -p "Proceed with install? [y/N] " ans
case "$ans" in
  y|Y|yes|Yes) ;;
  *) echo "Aborted."; exit 0 ;;
esac

opam install ./vsrocq-split-extras.opam --no-upgrade
echo "Done. Run: make"
