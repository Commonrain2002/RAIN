#!/usr/bin/env python3
"""Build parcas_catalog.json from PARCAS_PATH (excludes .v files containing Abort)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
if str(_EVAL_PARCAS_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_PARCAS_DIR))

from parcas_catalog_build import assign_stable_ids, collect_theorems_from_vfile, list_eligible_v_files
from parcas_testlist import DEFAULT_CATALOG_PATH, resolve_parcas_path


def main() -> int:
    default_parse = (_REPO_ROOT / "Sentence" / "vsrocq_split_sentences_Parcas").resolve()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parcas-path", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_CATALOG_PATH)
    ap.add_argument("--parse-sentence-script", type=str, default=str(default_parse))
    ap.add_argument("--parse-sentence-timeout-seconds", type=int, default=120)
    args = ap.parse_args()

    try:
        project_root = resolve_parcas_path(args.parcas_path)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    v_files = list_eligible_v_files(project_root)
    all_rows: list[dict] = []
    failures: list[str] = []

    for v_abs in v_files:
        v_rel = v_abs.relative_to(project_root).as_posix()
        try:
            rows = collect_theorems_from_vfile(
                project_root,
                v_rel,
                str(args.parse_sentence_script),
                int(args.parse_sentence_timeout_seconds),
            )
            all_rows.extend(rows)
            print(f"ok | {v_rel} | theorems={len(rows)}", flush=True)
        except (RuntimeError, OSError, ValueError) as e:
            failures.append(f"{v_rel}: {e}")
            print(f"skip | {v_rel} | {e}", flush=True)

    if not all_rows:
        print("ERROR: no theorems collected", file=sys.stderr)
        return 1

    entries = assign_stable_ids(all_rows)
    out_path = args.out.resolve()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parcas_path": str(project_root),
        "entry_count": len(entries),
        "entries": entries,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = out_path.with_suffix(".manifest.txt")
    lines = [
        f"generated_at={payload['generated_at']}",
        f"parcas_path={project_root}",
        f"entry_count={len(entries)}",
        f"skipped_files={len(failures)}",
        "",
    ]
    for entry in entries:
        lines.append(
            f"{entry['id']}\t{entry['v_rel_path']}\t{entry['theorem_name']}\tline={entry['start_line']}"
        )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(entries)} entries -> {out_path}", flush=True)
    print(f"Manifest -> {manifest}", flush=True)
    if failures:
        print(f"WARNING: {len(failures)} files failed split (see log above)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
