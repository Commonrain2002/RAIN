#!/usr/bin/env bash
set -euo pipefail

log() {
    printf '[%(%Y-%m-%d %H:%M:%S)T] %s\n' -1 "$*" >&2
}

on_error() {
    local status=$?
    log "Failed at line ${BASH_LINENO[0]}: ${BASH_COMMAND} (exit ${status})"
    exit "$status"
}

trap on_error ERR

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log "Using repository root: ${ROOT}"

if ! command -v conda >/dev/null 2>&1; then
    echo "conda not found" >&2
    exit 1
fi

if ! conda env list | awk '{print $1}' | grep -qx cobble; then
    log "Creating conda env cobble (Python 3.11)..."
    conda create -y -n cobble python=3.11
else
    log "Conda env cobble already exists."
fi

pip_in_cobble() {
    conda run --no-capture-output -n cobble \
        env \
        GIT_CONFIG_COUNT=1 \
        GIT_CONFIG_KEY_0=http.version \
        GIT_CONFIG_VALUE_0="${COBBLE_GIT_HTTP_VERSION:-HTTP/1.1}" \
        python -m pip "$@"
}

pip_in_cobble_with_retries() {
    local attempt
    local max_attempts="${COBBLE_PIP_INSTALL_ATTEMPTS:-4}"
    local retry_delay_sec="${COBBLE_PIP_INSTALL_RETRY_DELAY_SEC:-10}"

    for ((attempt = 1; attempt <= max_attempts; attempt++)); do
        if pip_in_cobble "$@"; then
            return 0
        fi

        if ((attempt == max_attempts)); then
            echo "pip failed after ${max_attempts} attempts." >&2
            return 1
        fi

        echo "pip failed on attempt ${attempt}/${max_attempts}; retrying in ${retry_delay_sec}s..." >&2
        sleep "$retry_delay_sec"
    done
}

log "Installing Python dependencies into cobble with pip..."
pip_in_cobble_with_retries install --progress-bar on -e .
log "Python dependencies installed."

if [ ! -f .env ]; then
    cp .env.example .env
    log "Created .env from .env.example - fill in API keys before running evaluations."
else
    log ".env already exists."
fi

log "Initializing coq-wigderson submodule (if needed)..."
git submodule update --init coq-projects/coq-wigderson
log "coq-wigderson submodule is ready."

log "Building PnVRocqLib with opam switch coq-8.18..."
(
    eval "$(opam env --switch=coq-8.18 --set-switch)"
    make -C coq-projects/PnVRocqLib -j"$(nproc)"
)
log "PnVRocqLib built."

log "Building coq-wigderson with opam switch coq-8.13..."
(
    eval "$(opam env --switch=coq-8.13 --set-switch)"
    make -C coq-projects/coq-wigderson -j"$(nproc)"
)
log "coq-wigderson built."

log "Done. Activate with: conda activate cobble"
log "Run Cobblestone: ./scripts/goal-decomposition run --help"
