"""Cobble TestList parsing (PnVRocqLib example names, line-number ids)."""

from __future__ import annotations

import re
from pathlib import Path

_COBBLE_EXAMPLE_RE = re.compile(r"^PnVRocqLib-.+\.v-.+$")


def read_line_at(testlist: Path, line_number_one_based: int) -> str:
    lines = testlist.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_number_one_based < 1 or line_number_one_based > len(lines):
        raise ValueError(f"line id out of range: {line_number_one_based} (file has {len(lines)} lines)")
    return lines[line_number_one_based - 1].strip()


def is_cobble_data_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped == "example_name":
        return False
    return _COBBLE_EXAMPLE_RE.match(stripped) is not None


def read_cobble_ids(testlist: Path) -> list[int]:
    lines = testlist.read_text(encoding="utf-8", errors="replace").splitlines()
    ids: list[int] = []
    for index, line in enumerate(lines, start=1):
        if is_cobble_data_line(line):
            ids.append(index)
    return ids


def parse_example_name(line: str, *, project_prefix: str = "PnVRocqLib") -> tuple[str, str]:
    stripped = line.strip()
    prefix = f"{project_prefix}-"
    if not stripped.startswith(prefix):
        raise ValueError(f"example does not start with {prefix!r}: {stripped!r}")
    rest = stripped[len(prefix) :]
    if ".v-" not in rest:
        raise ValueError(f"cannot split .v- in example name: {stripped!r}")
    v_part, theorem_name = rest.rsplit(".v-", 1)
    v_basename = f"{v_part}.v"
    if not theorem_name:
        raise ValueError(f"empty theorem name in example: {stripped!r}")
    return v_basename, theorem_name


def resolve_vfile(project_root: Path, v_basename: str) -> Path:
    matches = sorted(project_root.rglob(v_basename))
    if not matches:
        raise ValueError(f"no {v_basename!r} under {project_root}")
    if len(matches) > 1:
        rels = ", ".join(m.relative_to(project_root).as_posix() for m in matches[:8])
        suffix = " ..." if len(matches) > 8 else ""
        raise ValueError(f"ambiguous {v_basename!r}: {len(matches)} matches ({rels}{suffix})")
    return matches[0].resolve()
