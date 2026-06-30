#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PROJ="${PALM_PROJECT:-compcert}"
FILE="${PALM_FILE:-flocq/IEEE754/Binary.v}"
THEOREM="${PALM_THEOREM:-FLT_format_B2R}"
EXP_NAME="${PALM_EXP_NAME:-test}"

python -m src.main \
  --proj="$PROJ" \
  --file="$FILE" \
  --theorem="$THEOREM" \
  --exp_name="$EXP_NAME" \
  --threads=1 \
  -backtrack
