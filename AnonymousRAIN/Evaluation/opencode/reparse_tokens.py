#!/usr/bin/env python3
"""Backfill token fields in trial result.json from run_stdout.log (after parser fixes)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from opencode_token_log import resolve_opencode_token_usage


def _sum_optional_tokens(*values: int | None) -> int | None:
    if all(v is None for v in values):
        return None
    return sum(int(v or 0) for v in values)


def _iter_trial_dirs(result_base: Path) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for pattern in ("*_batch/id_*/trial_*", "_batch/id_*/trial_*", "id_*/trial_*"):
        for path in sorted(result_base.glob(pattern)):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
    return sorted(out, key=lambda p: str(p))


def main() -> int:
    result_base = _EVAL_DIR / "Result"
    if not result_base.is_dir():
        print(f"No directory: {result_base}", file=sys.stderr)
        return 2
    trial_dirs = _iter_trial_dirs(result_base)
    if not trial_dirs:
        print(f"No trial dirs under {result_base}", file=sys.stderr)
        return 2
    updated = 0
    for trial_dir in trial_dirs:
        stdout_path = trial_dir / "run_stdout.log"
        result_path = trial_dir / "result.json"
        if not stdout_path.is_file() or not result_path.is_file():
            continue
        out = stdout_path.read_text(encoding="utf-8", errors="replace")
        err_path = trial_dir / "run_stderr.log"
        err = err_path.read_text(encoding="utf-8", errors="replace") if err_path.is_file() else ""
        parsed, session_id = resolve_opencode_token_usage(out, err)
        if parsed.source == "none":
            continue
        data = json.loads(result_path.read_text(encoding="utf-8"))
        data["tokens_prompt"] = parsed.prompt
        data["tokens_prompt_cache_hit"] = parsed.prompt_cache_hit
        data["tokens_prompt_cache_miss"] = parsed.prompt_cache_miss
        data["tokens_completion"] = _sum_optional_tokens(parsed.completion, parsed.reasoning)
        data["tokens_reasoning"] = parsed.reasoning
        data["tokens_total"] = parsed.total
        data["tokens_parse_source"] = parsed.source
        data["opencode_session_id"] = session_id or ""
        result_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        updated += 1
        print(f"updated {trial_dir.relative_to(_EVAL_DIR)} total={parsed.total} source={parsed.source}")
    print(f"done | updated {updated} trial(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
