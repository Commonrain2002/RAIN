from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IdRunSpec:
    id_value: int
    repeats: int


def repeats_for_id(*, default_repeats: int, id_repeats: dict[int, int], id_value: int) -> int:
    if id_value in id_repeats:
        return int(id_repeats[id_value])
    return int(default_repeats)


def format_default_repeats_log(default_repeats: int, id_repeats: dict[int, int]) -> str:
    repeat_values = set(id_repeats.values())
    repeats_log = f"default_repeats={default_repeats}"
    if len(repeat_values) > 1:
        repeats_log += f" per_id_min={min(repeat_values)} per_id_max={max(repeat_values)}"
    elif len(repeat_values) == 1 and next(iter(repeat_values)) != default_repeats:
        repeats_log += f" (all ids use {next(iter(repeat_values))})"
    return repeats_log


def _parse_testlist_repeats(raw: Any, default_repeats: int) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return int(raw)
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    if isinstance(raw, dict):
        for key in ("repeats", "trials", "repeat"):
            if key in raw:
                return int(raw[key])
    return None


def _parse_one_testlist_entry(entry: Any, default_repeats: int) -> IdRunSpec | None:
    if isinstance(entry, bool):
        return None
    if isinstance(entry, int):
        return IdRunSpec(int(entry), default_repeats)
    if isinstance(entry, str):
        s = entry.strip()
        if s.isdigit():
            return IdRunSpec(int(s), default_repeats)
        return None
    if isinstance(entry, dict):
        id_raw = entry.get("id")
        if id_raw is None:
            return None
        rep = _parse_testlist_repeats(entry, default_repeats)
        if rep is None:
            rep = default_repeats
        return IdRunSpec(int(id_raw), int(rep))
    return None


def read_run_specs_from_testlist(path: Path, default_repeats: int) -> list[IdRunSpec]:
    raw_text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw_text:
        return []
    try:
        parsed = json.loads(raw_text)
    except Exception:
        parsed = None

    if isinstance(parsed, list):
        specs: list[IdRunSpec] = []
        for item in parsed:
            spec = _parse_one_testlist_entry(item, default_repeats)
            if spec is not None:
                specs.append(spec)
        if specs:
            return specs

    if isinstance(parsed, dict):
        specs = []
        for key, val in parsed.items():
            id_value = int(key)
            if isinstance(val, dict):
                rep = _parse_testlist_repeats(val, default_repeats)
                if rep is None:
                    rep = default_repeats
            else:
                rep = _parse_testlist_repeats(val, default_repeats)
                if rep is None:
                    rep = default_repeats
            specs.append(IdRunSpec(id_value, int(rep)))
        if specs:
            return specs

    ids = [int(x) for x in re.findall(r"\d+", raw_text)]
    return [IdRunSpec(i, default_repeats) for i in ids]


def read_ids_from_testlist(path: Path, *, default_repeats: int = 1) -> list[int]:
    return [s.id_value for s in read_run_specs_from_testlist(path, default_repeats)]
