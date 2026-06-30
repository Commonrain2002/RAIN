#!/usr/bin/env python3
"""Build fixed TestList.json from parcas_catalog.json (not used by run_batch).

Default: 50 longest + 50 random. Use --all for every eligible catalog entry (Abort .v excluded).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
if str(_EVAL_PARCAS_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_PARCAS_DIR))

from parcas_catalog_build import build_step_count_by_catalog_id
from parcas_testlist import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_TESTLIST_PATH,
    ParcasCatalogEntry,
    assert_entries_not_in_abort_files,
    catalog_excluding_abort_files,
    load_catalog,
    resolve_parcas_path,
    sample_longest_and_random_entries,
)


def _merge_sampled(
    longest: list[ParcasCatalogEntry],
    random_pick: list[ParcasCatalogEntry],
) -> list[ParcasCatalogEntry]:
    by_id: dict[int, ParcasCatalogEntry] = {}
    for entry in longest + random_pick:
        by_id[entry.id] = entry
    return [by_id[k] for k in sorted(by_id)]


def main() -> int:
    default_parse = (_REPO_ROOT / "Sentence" / "vsrocq_split_sentences_Parcas").resolve()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    ap.add_argument("--out", type=Path, default=DEFAULT_TESTLIST_PATH)
    ap.add_argument(
        "--long-count",
        type=int,
        default=50,
        help="Theorems with longest proof bodies (by line count Proof..Qed).",
    )
    ap.add_argument(
        "--random-count",
        type=int,
        default=50,
        help="Random sample from remaining eligible catalog entries.",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Include every eligible catalog entry (ignores --long-count, --random-count, --seed).",
    )
    ap.add_argument("--seed", type=int, default=20260620)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--parcas-path", type=Path, default=None)
    ap.add_argument("--parse-sentence-script", type=str, default=str(default_parse))
    ap.add_argument("--parse-sentence-timeout-seconds", type=int, default=120)
    ap.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Default: <out>.manifest.json next to TestList.json",
    )
    args = ap.parse_args()

    use_all = bool(args.all)
    long_count = int(args.long_count)
    random_count = int(args.random_count)
    total_count = long_count + random_count
    if not use_all:
        if long_count < 0 or random_count < 1 or total_count < 1:
            print(
                "--long-count must be >= 0, --random-count must be >= 1, "
                "and their sum must be >= 1 (or pass --all)",
                file=sys.stderr,
            )
            return 2
    if int(args.repeats) < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return 2

    try:
        project_root = resolve_parcas_path(args.parcas_path)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    catalog = catalog_excluding_abort_files(load_catalog(args.catalog), project_root)
    if not use_all and len(catalog) < total_count:
        print(
            f"ERROR: eligible catalog has {len(catalog)} entries (Abort .v excluded), "
            f"need {total_count}",
            file=sys.stderr,
        )
        return 1

    longest: list[ParcasCatalogEntry] = []
    random_pick: list[ParcasCatalogEntry] = []
    step_count_by_id: dict[int, int]

    if use_all:
        sampled = list(catalog)
        step_count_by_id = {entry.id: int(entry.step_count) for entry in catalog}
    elif long_count == 0:
        step_count_by_id = {entry.id: int(entry.step_count) for entry in catalog}
        rng = random.Random(int(args.seed))
        if len(catalog) < random_count:
            print(
                f"ERROR: eligible catalog has {len(catalog)} entries, need {random_count}",
                file=sys.stderr,
            )
            return 1
        random_pick = rng.sample(catalog, random_count)
        longest = []
        sampled = sorted(random_pick, key=lambda entry: entry.id)
    else:
        try:
            step_count_by_id = build_step_count_by_catalog_id(
                catalog,
                project_root,
                str(args.parse_sentence_script),
                int(args.parse_sentence_timeout_seconds),
            )
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        try:
            longest, random_pick = sample_longest_and_random_entries(
                catalog,
                step_count_by_id,
                long_count=long_count,
                random_count=random_count,
                seed=int(args.seed),
            )
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        sampled = _merge_sampled(longest, random_pick)

    try:
        assert_entries_not_in_abort_files(sampled, project_root)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    testlist_specs = [{"id": e.id} for e in sampled]
    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(testlist_specs, indent=2) + "\n", encoding="utf-8")

    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else out_path.with_name(out_path.stem + ".manifest.json")
    )
    longest_id_set = {x.id for x in longest}
    manifest_payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": (
            "all_eligible"
            if use_all
            else ("random_only" if long_count == 0 else "longest_then_random")
        ),
        "count": len(sampled),
        "repeats": int(args.repeats),
        "catalog": str(args.catalog.resolve()),
        "testlist": str(out_path),
        "entries": [
            {
                "id": e.id,
                "v_rel_path": e.v_rel_path,
                "theorem_name": e.theorem_name,
                "start_line": e.start_line,
                "step_count": int(step_count_by_id.get(e.id, 0)),
                **(
                    {}
                    if use_all
                    else {
                        "bucket": "longest" if e.id in longest_id_set else "random",
                    }
                ),
            }
            for e in sampled
        ],
    }
    if use_all:
        manifest_payload["eligible_catalog_count"] = len(catalog)
    else:
        manifest_payload["seed"] = int(args.seed)
        manifest_payload["long_count"] = long_count
        manifest_payload["random_count"] = random_count
        manifest_payload["longest_ids"] = [e.id for e in sorted(longest, key=lambda x: x.id)]
        manifest_payload["random_ids"] = [e.id for e in sorted(random_pick, key=lambda x: x.id)]
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(testlist_specs)} ids -> {out_path}", flush=True)
    print(f"Manifest -> {manifest_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
