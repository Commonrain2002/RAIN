#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SKIP_DIRS = {".git", "bin", "obj", "__pycache__", ".pytest_cache", "_build", "Result"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LOCAL_PATH_PARTS = [
    "/" + "home/",
    "/" + "Users/",
    "/" + "data2/",
    "C:" + "\\Users\\",
    "Desktop/" + "Research",
    "cobblestone" + "_test",
    "Coq" + "Test",
    "/" + "root/",
]
LOCAL_PATH_RE = re.compile("|".join(re.escape(part) for part in LOCAL_PATH_PARTS))
LOCAL_NAME_RE = re.compile(r"\b" + "z" + "j" + "y" + r"\b", re.IGNORECASE)


def is_text(path: Path) -> bool:
    try:
        data = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\0" not in data


def iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_dir() and path.name in SKIP_DIRS:
            continue
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if is_text(path):
            yield path


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan the artifact for anonymization regressions.")
    ap.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    root = args.root.resolve()
    findings: list[str] = []
    for path in iter_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root)
        checks = [
            ("han", HAN_RE),
            ("email", EMAIL_RE),
            ("local-path", LOCAL_PATH_RE),
            ("local-name", LOCAL_NAME_RE),
        ]
        for label, regex in checks:
            match = regex.search(text)
            if match:
                line_no = text[: match.start()].count("\n") + 1
                findings.append(f"{rel}:{line_no}: {label}: {match.group(0)!r}")
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"anonymity check passed: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
