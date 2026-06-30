#!/bin/bash

SWITCH=$1

if [ -z "$SWITCH" ]; then
    echo "Usage: $0 <switch>" >&2
    exit 1
fi

# a switch statement mapping SWITCH to a Coq version
case $SWITCH in
    8.9) COQ_VERSION=8.9.1  ;;
    8.10) COQ_VERSION=8.10.2 ;;
    8.11) COQ_VERSION=8.11.2 ;;
    8.12) COQ_VERSION=8.12.2 ;;
    8.13) COQ_VERSION=8.13.2 ;;
    *) echo "Unknown switch $SWITCH" >&2; exit 1 ;;
esac

if [ "$SWITCH" == "8.13" ]; then
    OCAML_VERSION=4.08.1
else
    OCAML_VERSION=4.07.1
fi

if opam switch list | grep "$SWITCH"; then
    echo "Switch $SWITCH already exists" >&2
else
    echo "Creating switch $SWITCH" >&2
    opam switch create coq-$SWITCH $OCAML_VERSION
    if [ $? -ne 0 ]; then
        exit 1
    fi
fi

# eval $(opam env --switch=coq-$SWITCH --set-switch)

PREVIOUS_SWITCH=$(opam switch show)
echo "Switching from $PREVIOUS_SWITCH to coq-$SWITCH" >&2

opam switch set coq-$SWITCH
eval $(opam env)

opam pin add -y coq $COQ_VERSION
opam repo add coq-released https://coq.inria.fr/opam/released --all-switches --set-default

opam install -y coq-serapi
opam install -y coq-hammer

opam switch set $PREVIOUS_SWITCH
eval $(opam env)

# to install dependencies for coq-libarary-undecidability,
# opam repo add coq-released https://coq.inria.fr/opam/released
# opam update
# opam install . --deps-only

exit 0
