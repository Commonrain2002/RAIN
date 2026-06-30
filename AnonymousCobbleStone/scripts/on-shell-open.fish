#!/usr/local/bin/fish

echo "on-shell-open.fish"

set SCRIPT_DIR (dirname (status -f))

set -x PATH $SCRIPT_DIR $PATH

poetry shell

