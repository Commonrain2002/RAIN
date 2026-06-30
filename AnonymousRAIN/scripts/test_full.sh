#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$ROOT/Sentence:$PATH"
python3 scripts/anonymity_check.py
dotnet test ProofAgent.Tests/ProofAgent.Tests.csproj
python3 -m pytest Evaluation
