#!/bin/bash

# echo "on-shell-open.bash"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
ORIGINAL_DIR="$(pwd)"

export PATH="$SCRIPT_DIR:$PATH"

poetry shell
