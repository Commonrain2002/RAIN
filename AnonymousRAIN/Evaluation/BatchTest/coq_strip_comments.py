from __future__ import annotations

import re


def strip_coq_comments(text: str) -> str:
    """
    Remove Coq comments to approximate "not in comment" scan.

    - Removes nested block comments: (* ... *)
    - Removes line comments after % (Coq's single-line comment marker)
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if i + 1 < n and text[i : i + 2] == "(*":
            depth = 1
            i += 2
            while i < n and depth:
                if i + 1 < n and text[i : i + 2] == "(*":
                    depth += 1
                    i += 2
                elif i + 1 < n and text[i : i + 2] == "*)":
                    depth -= 1
                    i += 2
                else:
                    i += 1
            continue
        out.append(text[i])
        i += 1

    s = "".join(out)
    lines: list[str] = []
    for line in s.splitlines():
        lines.append(_strip_line_percent_comment(line))
    return "\n".join(lines)


def _strip_line_percent_comment(line: str) -> str:
    """
    Remove Coq ``% ...`` line comments without stripping notation scopes ``%ident``
    (e.g. Iris ``(f i)%T``).
    """
    i = 0
    n = len(line)
    while i < n:
        if line[i] != "%":
            i += 1
            continue
        if i + 1 < n:
            nxt = line[i + 1]
            if nxt.isalpha() or nxt == "_":
                j = i + 2
                while j < n and (line[j].isalnum() or line[j] == "_"):
                    j += 1
                i = j
                continue
        return line[:i].rstrip()
    return line


_DEFAULT_SKIP_RE = re.compile(r"\b(Admitted|Admit|Abort)\b", re.MULTILINE)


def find_skip_keywords(text_no_comments: str, extra_keywords: list[str] | None = None) -> list[str]:
    """
    Return matched keywords (unique, stable order).
    """
    patterns = ["Admitted", "Admit", "Abort"]
    if extra_keywords:
        for k in extra_keywords:
            if k and k not in patterns:
                patterns.append(k)
    rx = re.compile(r"\b(" + "|".join(re.escape(p) for p in patterns) + r")\b", re.MULTILINE)
    seen: set[str] = set()
    hits: list[str] = []
    for m in rx.finditer(text_no_comments):
        kw = m.group(1)
        if kw not in seen:
            seen.add(kw)
            hits.append(kw)
    return hits

