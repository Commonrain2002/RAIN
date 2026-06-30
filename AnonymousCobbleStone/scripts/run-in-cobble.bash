#!/bin/bash
# Run a cobblestone Python module from the repo root using the cobble conda env.
MODULE=$1
shift

if [ -z "$MODULE" ]; then
    echo "Usage: run-in-cobble.bash <module> [args...]" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGIN_DIR=$(pwd)
cd "$SCRIPT_DIR/.." || exit 1
trap 'cd "$ORIGIN_DIR"' EXIT

if [ -x "${COBBLESTONE_PYTHON:-}" ]; then
    exec "$COBBLESTONE_PYTHON" -m "$MODULE" "$@"
fi

if [ -n "${CONDA_PREFIX:-}" ] && [[ "$CONDA_PREFIX" == *"/envs/cobble" ]]; then
    exec python -m "$MODULE" "$@"
fi

if command -v conda >/dev/null 2>&1 && conda env list | awk '{print $1}' | grep -qx cobble; then
    exec conda run -n cobble --no-capture-output python -m "$MODULE" "$@"
fi

exec python -m "$MODULE" "$@"
