#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$ROOT/Sentence:$PATH"
python3 scripts/anonymity_check.py
dotnet build ProofAgent.Tests/ProofAgent.Tests.csproj
dotnet test ProofAgent.Tests/ProofAgent.Tests.csproj --no-restore --filter "FullyQualifiedName~PathTests|FullyQualifiedName~ToolRegistryTests|FullyQualifiedName~RunCheckToolResultFormatterTests"
python3 -m pytest   Evaluation/BatchTest/test_coq_strip_comments.py   Evaluation/BatchTest/test_proofagent_token_log.py   Evaluation/BatchTest/test_theorem_integrity.py   Evaluation/codex/test_codex_token_log.py
