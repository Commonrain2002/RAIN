#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLM_API_KEY="${LLM_API_KEY:-${DEEPSEEK_API_KEY:-}}"
export PATH="$SCRIPT_DIR/Sentence:$PATH"

usage() {
  cat <<'EOF'
Usage:
  ./run.sh [-h|--help]

Run RAIN from the current working directory. The current directory must contain
proofagent.config.json. Set LLM_API_KEY, or DEEPSEEK_API_KEY as a fallback.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: the main task does not accept command-line arguments; edit proofagent.config.json" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${LLM_API_KEY//[[:space:]]/}" ]]; then
  echo "error: set LLM_API_KEY or DEEPSEEK_API_KEY" >&2
  exit 1
fi

if [[ ! -f "${PWD}/proofagent.config.json" ]]; then
  echo "error: missing proofagent.config.json in the current directory" >&2
  exit 1
fi

export LLM_API_KEY
dotnet run --no-build --project "$SCRIPT_DIR/ProofAgent.csproj" --
