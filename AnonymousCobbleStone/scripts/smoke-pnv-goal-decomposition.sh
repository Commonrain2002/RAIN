#!/usr/bin/env bash
# Smoke test: PnVRocqLib goal decomposition with DeepSeek-v4-flash.
#
# Chosen lemma: vec_to_trms_to_vec.
# In the existing PnVRocqLib run this was discharged directly by an LLM-generated
# structural induction proof, not hammer. This script also omits -t/--try-hammer
# so hammer is disabled.
#
# Usage (repo root, cobble env):
#   ./scripts/smoke-pnv-goal-decomposition.sh
#
# Required:
#   DEEPSEEK_API_KEY in .env or environment.

set -euo pipefail
cd "$(dirname "$0")/.."

if command -v opam >/dev/null 2>&1 && opam switch list 2>/dev/null | grep -qx 'coq-8.18'; then
  eval "$(opam env --switch=coq-8.18 --set-switch)"
fi

run_python() {
  if [ -x "${COBBLESTONE_PYTHON:-}" ]; then
    "$COBBLESTONE_PYTHON" "$@"
    return
  fi
  if command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | awk '{print $1}' | grep -qx cobble; then
    conda run -n cobble --no-capture-output python "$@"
    return
  fi
  python3 "$@"
}

LEMMA="${SMOKE_LEMMA:-vec_to_trms_to_vec}"
SMOKE_UUID="${SMOKE_UUID:-$(run_python -c 'import uuid; print(uuid.uuid4().hex)')}"
export SMOKE_UUID

echo "smoke lemma: $LEMMA"
echo "smoke uuid: $SMOKE_UUID"

if [ ! -f coq-projects/PnVRocqLib/theories/Prelude/Prelude.vo ]; then
  cat >&2 <<'EOF'
SMOKE FAILED: PnVRocqLib is not built.

Build it with:

  eval "$(opam env --switch=coq-8.18 --set-switch)"
  make -C coq-projects/PnVRocqLib -j"$(nproc)"

Then rerun ./scripts/smoke-pnv-goal-decomposition.sh.
EOF
  exit 1
fi

./scripts/goal-decomposition run \
  -d pnvrocqlib_test \
  -c preceding-lemmas-only \
  -m 5 \
  -x "${SMOKE_MAX_NODES:-1}" \
  -n 1 \
  -o deepseek-v4-flash \
  -l "$LEMMA" \
  --example-wall-timeout-sec "${SMOKE_TIMEOUT_SEC:-5400}" \
  -u "$SMOKE_UUID"

RUN_DIR="$(
  run_python << PY
from pathlib import Path
import sys

root = Path("data/evaluation/goal_decomposition")
uuid = "$SMOKE_UUID"
matches = sorted(
    p for p in root.iterdir()
    if p.is_dir() and uuid in p.name and p.name.startswith("pnvrocqlib_test_")
)
if not matches:
    sys.exit("no run directory found for uuid " + uuid)
print(matches[-1])
PY
)"

echo "run directory: $RUN_DIR"

run_python << PY
import csv
import json
import re
import sys
from pathlib import Path

run_dir = Path("$RUN_DIR")
lemma = "$LEMMA"
state_matches = list(run_dir.glob(f"*-{lemma}.json"))
if not state_matches:
    sys.exit(f"SMOKE FAILED: missing state file for {lemma}")

state_path = state_matches[0]
state = json.loads(state_path.read_text())
nodes = {node["uuid"]: node for node in state["nodes"]}
root = nodes[state["root_uuid"]]

def proof_exists(node):
    if node.get("proof") is not None:
        return True
    for _decomposition, child_uuids in zip(
        node.get("decompositions") or [], node.get("children_uuids") or []
    ):
        children = [nodes.get(uuid) for uuid in child_uuids]
        if children and all(child is not None and proof_exists(child) for child in children):
            return True
    return False

def proof_path_nodes(node):
    if node.get("proof") is not None:
        return [node]
    for _decomposition, child_uuids in zip(
        node.get("decompositions") or [], node.get("children_uuids") or []
    ):
        children = [nodes.get(uuid) for uuid in child_uuids]
        if children and all(child is not None and proof_exists(child) for child in children):
            path = [node]
            for child in children:
                path.extend(proof_path_nodes(child))
            return path
    return [node]

has_proof = proof_exists(root)
proof_path = proof_path_nodes(root)
proofs = [
    node.get("proof")
    for node in proof_path
    if node.get("proof") is not None
]
hammer_proofs = [
    proof for proof in proofs if isinstance(proof, str) and proof.strip() == "hammer."
]
llm_proofs = [
    proof for proof in proofs if not (isinstance(proof, str) and proof.strip() == "hammer.")
]

errors = []
if not has_proof:
    errors.append(f"{lemma}: recursive proof is missing")
if hammer_proofs:
    errors.append(f"{lemma}: proof path used hammer, expected LLM-only proof")
if not llm_proofs:
    errors.append(f"{lemma}: proof path has no LLM proof")
if state.get("config", {}).get("try_hammer") is not False:
    errors.append(f"{lemma}: state config has try_hammer enabled")

results_path = run_dir / "results.csv"
results_csv_status = None
if results_path.exists():
    with results_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    row = next((r for r in rows if r.get("lemma_name") == lemma), None)
    if row is not None:
        results_csv_status = row.get("successful")

usage_path = run_dir / "usage.json"
if usage_path.exists():
    usage = json.loads(usage_path.read_text())
    if usage.get("num_requests", 0) <= 0:
        errors.append(f"{lemma}: usage.json has no LLM requests")
else:
    errors.append("missing usage.json")

USAGE_FIELDS = (
    "num_tokens",
    "num_input_tokens",
    "num_output_tokens",
    "num_requests",
    "num_cache_hit_read_tokens",
    "num_cache_miss_read_tokens",
    "num_cache_write_tokens",
    "num_reasoning_tokens",
)

def parse_usage_text(usage_text):
    parsed = {}
    for field in USAGE_FIELDS:
        match = re.search(rf"{field}=(\d+)", usage_text)
        parsed[field] = int(match.group(1)) if match else 0
    return parsed

def parse_raw_llm_usage(log_path):
    totals = {field: 0 for field in USAGE_FIELDS}
    entries = 0
    if not log_path.exists():
        return {"entries": 0, "missing_log": True, **totals}

    with log_path.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("name") != "prompts-for-proofs.llm.gpt":
                continue
            usage_text = entry.get("usage")
            if not isinstance(usage_text, str) or "Usage(" not in usage_text:
                continue
            parsed = parse_usage_text(usage_text)
            entries += 1
            for field in USAGE_FIELDS:
                totals[field] += parsed[field]
    return {"entries": entries, "missing_log": False, **totals}

def add_usage_check(checks, name, ok, detail=""):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})

raw_llm_usage = parse_raw_llm_usage(run_dir / "output.log")
usage_integrity = {
    "raw_llm_usage": raw_llm_usage,
    "checks": [],
}
checks = usage_integrity["checks"]

add_usage_check(
    checks,
    "raw_llm_usage_present",
    raw_llm_usage["entries"] > 0,
    f"entries={raw_llm_usage['entries']}",
)
add_usage_check(
    checks,
    "raw_requests_match_entries",
    raw_llm_usage["num_requests"] == raw_llm_usage["entries"],
    f"num_requests={raw_llm_usage['num_requests']}, entries={raw_llm_usage['entries']}",
)
add_usage_check(
    checks,
    "raw_total_equals_input_plus_output",
    raw_llm_usage["num_tokens"]
    == raw_llm_usage["num_input_tokens"] + raw_llm_usage["num_output_tokens"],
    (
        f"total={raw_llm_usage['num_tokens']}, "
        f"input={raw_llm_usage['num_input_tokens']}, "
        f"output={raw_llm_usage['num_output_tokens']}"
    ),
)
add_usage_check(
    checks,
    "raw_cache_reads_equal_input",
    raw_llm_usage["num_input_tokens"]
    == raw_llm_usage["num_cache_hit_read_tokens"]
    + raw_llm_usage["num_cache_miss_read_tokens"],
    (
        f"input={raw_llm_usage['num_input_tokens']}, "
        f"hit={raw_llm_usage['num_cache_hit_read_tokens']}, "
        f"miss={raw_llm_usage['num_cache_miss_read_tokens']}"
    ),
)
add_usage_check(
    checks,
    "raw_reasoning_not_greater_than_output",
    raw_llm_usage["num_reasoning_tokens"] <= raw_llm_usage["num_output_tokens"],
    (
        f"reasoning={raw_llm_usage['num_reasoning_tokens']}, "
        f"output={raw_llm_usage['num_output_tokens']}"
    ),
)

if "usage" in locals():
    usage_totals = {
        field: int(usage.get(field, 0) or 0)
        for field in USAGE_FIELDS
    }
    mismatches = {
        field: {
            "usage_json": usage_totals[field],
            "raw_llm_log": raw_llm_usage[field],
        }
        for field in USAGE_FIELDS
        if usage_totals[field] != raw_llm_usage[field]
    }
    usage_integrity["usage_json_totals"] = usage_totals
    usage_integrity["usage_json_vs_raw_mismatches"] = mismatches
    add_usage_check(
        checks,
        "usage_json_matches_raw_llm_log",
        not mismatches,
        json.dumps(mismatches, sort_keys=True),
    )

failed_usage_checks = [check for check in checks if not check["ok"]]
for check in failed_usage_checks:
    errors.append(f"{lemma}: usage integrity failed: {check['name']} ({check['detail']})")

summary = {
    "lemma": lemma,
    "run_dir": str(run_dir),
    "state_file": str(state_path),
    "success": not errors,
    "num_nodes": len(state.get("nodes", [])),
    "proof_path_length": len(proof_path),
    "num_llm_leaf_proofs": len(llm_proofs),
    "num_hammer_leaf_proofs": len(hammer_proofs),
    "leaf_proofs": [proof.strip() for proof in llm_proofs if isinstance(proof, str)],
    "results_csv_status": results_csv_status,
    "usage": {
        "num_tokens": usage.get("num_tokens", 0) if "usage" in locals() else 0,
        "num_input_tokens": usage.get("num_input_tokens", 0) if "usage" in locals() else 0,
        "num_output_tokens": usage.get("num_output_tokens", 0) if "usage" in locals() else 0,
        "num_requests": usage.get("num_requests", 0) if "usage" in locals() else 0,
        "num_cache_hit_read_tokens": usage.get("num_cache_hit_read_tokens", 0) if "usage" in locals() else 0,
        "num_cache_miss_read_tokens": usage.get("num_cache_miss_read_tokens", 0) if "usage" in locals() else 0,
        "num_cache_write_tokens": usage.get("num_cache_write_tokens", 0) if "usage" in locals() else 0,
        "num_reasoning_tokens": usage.get("num_reasoning_tokens", 0) if "usage" in locals() else 0,
        "duration_millis": usage.get("duration_millis", 0) if "usage" in locals() else 0,
    },
    "usage_integrity": usage_integrity,
    "errors": errors,
}
(run_dir / "smoke_summary.json").write_text(json.dumps(summary, indent=2))

if errors:
    print("SMOKE FAILED:")
    for error in errors:
        print(" ", error)
    sys.exit(1)

print("SMOKE OK")
print(f"  lemma: {lemma}")
print(f"  nodes: {summary['num_nodes']}")
print(f"  proof_path_length: {summary['proof_path_length']}")
print(f"  llm_leaf_proofs: {summary['leaf_proofs']}")
print(f"  results_csv_status: {summary['results_csv_status']}")
print(f"  requests: {summary['usage']['num_requests']}")
print(f"  tokens: {summary['usage']['num_tokens']}")
print(f"  cache_hit_read_tokens: {summary['usage']['num_cache_hit_read_tokens']}")
print(f"  cache_miss_read_tokens: {summary['usage']['num_cache_miss_read_tokens']}")
print("  usage_integrity: ok")
print(f"  summary: {run_dir / 'smoke_summary.json'}")
PY

run_python scripts/summarize_deepseek_usage.py "$RUN_DIR"
