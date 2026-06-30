#!/usr/bin/env python3
"""
Extract a minimal compilable dependency tree for one theorem from a Coq project
or from the CoqStoq benchmark.

CoqStoq mode (requires only the coqstoq package and COQSTOQ_PATH; it does not
depend on other modules in this repository)::

  python3 coqstoq_minimal_copy.py 1 --split test -o /tmp/out

Manual mode::

  python3 coqstoq_minimal_copy.py /path/to/project /path/to/project/foo/bar.v -o /tmp/out

The script prefers coqdep. The copied tree is pruned in Make/_CoqProject and
can trim the target .v file to the theorem statement followed by
Proof. Admitted.

In CoqStoq mode, after copying, the reference proof text is written to stdout.
stderr only receives the separator line ``--- standard-proof ---``.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Set, Tuple, List

from coqstoq import Split, get_theorem, num_theorems


def _coqstoq_split_from_arg(name: str) -> Split:
    n = name.strip().lower()
    if n in ("test",):
        return Split.TEST
    if n in ("val", "validation"):
        return Split.VAL
    if n in ("cutoff",):
        return Split.CUTOFF
    raise ValueError(f"unknown split: {name!r} (use: test, validation, cutoff)")


def _coqstoq_workspace_root(coqstoq_loc: Path, theorem) -> Path:
    p = theorem.project
    return coqstoq_loc / p.split.dir_name / p.dir_name


def _resolve_coqstoq_theorem(
    theorem_id: int,
    split_name: str,
    coqstoq_loc: Path,
) -> Tuple[Path, Path, int, int, int, int, int, int]:
    sp = _coqstoq_split_from_arg(split_name)
    n = num_theorems(sp, coqstoq_loc)
    if theorem_id < 0 or theorem_id >= n:
        raise ValueError(f"theorem_id out of range: {theorem_id} (split has {n} theorems)")
    thm = get_theorem(sp, theorem_id, coqstoq_loc)
    root = _coqstoq_workspace_root(coqstoq_loc, thm)
    vfile = (root / thm.path).resolve()
    if not root.is_dir():
        raise ValueError(f"project directory does not exist: {root}")
    if not vfile.is_file():
        raise ValueError(f"theorem .v file does not exist: {vfile}")
    ps = thm.proof_start_pos
    pe = thm.proof_end_pos
    return (
        root,
        vfile,
        int(thm.theorem_end_pos.line),
        int(thm.theorem_end_pos.column),
        int(ps.line),
        int(ps.column),
        int(pe.line),
        int(pe.column),
    )


# Default parent for copied projects; actual output is <parent>/<ProjectName>/.
DEFAULT_OUTPUT_PARENT = Path(
    os.environ.get("PALM_COPY_OUTPUT_ROOT", str(Path.cwd() / "coqstoq_copies"))
)

ARTIFACT_SUFFIXES = (
    ".vo",
    ".vos",
    ".vok",
    ".glob",
    ".aux",
    ".vio",
    ".vioaux",
)

# Project path specification files usable with coqdep -f / coq_makefile -f.
# Do not include .coqdeps.d: it is a Makefile dependency fragment and can make
# coqdep miss Require dependencies.
COQ_PATH_SPEC_FILENAMES = ("_CoqProject", "CoqProject", "Make")

# Root-level build files copied when present so the copied tree can run make,
# dune, or coq_makefile.
ROOT_COQ_BUILD_NAMES = (
    "_CoqProject",
    "CoqProject",
    "_CoqProjectName",
    # coq_makefile -f Make (many projects use Make instead of _CoqProject).
    "Make",
    "CoqMakefile.in",
    "Makefile",
    "makefile",
    "GNUmakefile",
    # Some projects, such as CompCert, include VERSION from the top-level Makefile.
    "VERSION",
    "Makefile.config",
    # Do not copy Makefile.coq. It is regenerated from the pruned Make/_CoqProject.
    "Makefile.coq.conf",
    "Makefile.coq.local",
    "localMakefile",
    "dune",
    "dune-project",
    "extractedMakefile",
)

# Prune these coq_makefile inputs in the copied tree according to kept .v files.
PRUNE_COQ_INPUT_NAMES = frozenset(
    {"Make", "_CoqProject", "CoqProject", "CoqMakefile.in"}
)

# Makefile variable assignment: NAME [:+]= VALUE
_MAKEFILE_ASSIGN_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*[:+]?=\s*)(.*)$")

# coqdep output: "targets: prereqs"
_COQDEP_RULE_RE = re.compile(r"^([^:]+):\s*(.*)$")

# -R dir log / -Q dir log in Makefiles or arbitrary text. Quoted paths are
# simplified by removing the outer quotes.
_RQ_FLAGS_RE = re.compile(
    r'(?:^|[\s=])(?P<flag>-[RQ])\s+(?P<dir>"[^"]+"|\'[^\']+\'|\S+)\s+(?P<log>\S+)'
)

# Require lines. strip_comments ensures matches are not taken from comments.
_REQUIRE_RE = re.compile(
    r"""
    ^\s*
    (?:From\s+(?P<from>[\w.]+)\s+)?
    Require\s+
    (?:Import|Export)?\s+
    (?P<mods>[\w.\s]+?)
    \s*\.?\s*$
    """,
    re.VERBOSE | re.MULTILINE,
)

# Load "Foo" / Load Foo.
# The unquoted branch must not use a greedy [...]+ followed by optional \.?.
# Otherwise the character class consumes the Coq sentence-ending dot, e.g.
# `Load hCoefStructure.` -> `hCoefStructure.`, and with_suffix(".v") would
# become `hCoefStructure..v`, causing Load dependencies to be missed.
_LOAD_RE = re.compile(
    r"""^\s*Load\s+(?P<q>"[^"]+"|'[^']+'|[A-Za-z0-9_./-]+?)\s*\.?\s*$""",
    re.MULTILINE,
)


def _real(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p.absolute()


def strip_coq_comments(text: str) -> str:
    """Remove (* ... *) comments to reduce false Require matches."""
    out = []
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
    lines = []
    for line in s.splitlines():
        if "%" in line:
            line = line.split("%", 1)[0]
        lines.append(line)
    return "\n".join(lines)


def extract_loads_from_v(vfile: Path) -> list[str]:
    """
    Extract Load arguments without quotes, for example:
      Load "hCoefStructure".  -> hCoefStructure
      Load foo/bar.           -> foo/bar
    """
    try:
        text = vfile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    text = strip_coq_comments(text)
    out: list[str] = []
    for m in _LOAD_RE.finditer(text):
        q = m.group("q").strip()
        if (q.startswith('"') and q.endswith('"')) or (q.startswith("'") and q.endswith("'")):
            q = q[1:-1]
        if q:
            out.append(q)
    return out


def resolve_load_target(current_file: Path, target: str) -> Optional[Path]:
    """
    Resolve a Load target to a physical .v path.
    Coq searches Load through the loadpath; this implements the common
    in-project case: relative to the current file directory.
    If the target has no suffix, add .v.
    """
    t = target.strip()
    if not t:
        return None
    # Defensive cleanup: the Coq sentence-ending dot is not part of the path.
    if not (
        (t.startswith('"') and t.endswith('"'))
        or (t.startswith("'") and t.endswith("'"))
    ):
        t = t.rstrip(".")
    if not t:
        return None
    p = Path(t)
    if p.suffix == "":
        p = p.with_suffix(".v")
    # Relative to the current file directory.
    if not p.is_absolute():
        p = (current_file.parent / p).resolve()
    else:
        p = p.resolve()
    return p


def parse_rq_flags_from_text(text: str) -> list[Tuple[str, str, str]]:
    """Return [('-R', dir, logical), ...], with quotes removed from dir."""
    found = []
    for m in _RQ_FLAGS_RE.finditer(text):
        flag = m.group("flag")
        d = m.group("dir").strip()
        if (d.startswith('"') and d.endswith('"')) or (d.startswith("'") and d.endswith("'")):
            d = d[1:-1]
        log = m.group("log").strip()
        found.append((flag, d, log))
    return found


def collect_extra_loadpath_from_makefiles(project_root: Path) -> str:
    """Extract -R/-Q flags from Makefile-like files as _CoqProject fragments."""
    chunks: list[str] = []
    names = [
        "Makefile",
        "Makefile.coq",
        "Makefile.coq.conf",
        "localMakefile",
    ]
    for root, _, files in os.walk(project_root):
        # Avoid spending time in deep generated/vendor directories.
        depth = Path(root).relative_to(project_root).parts
        if len(depth) > 4:
            continue
        for fn in files:
            if fn in names or (fn.startswith("Makefile") and "coq" in fn.lower()):
                path = Path(root) / fn
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for flag, d, log in parse_rq_flags_from_text(text):
                    # coqdep -f input must not contain Make macro expansion.
                    # These strings are written literally and can trigger Sys_error.
                    if "$" in d or "$" in log:
                        continue
                    if "$(" in d or "$(" in log or "${" in d or "${" in log:
                        continue
                    phys = Path(d)
                    if not phys.is_absolute():
                        phys = (path.parent / phys).resolve()
                    chunks.append(f"{flag} {phys} {log}\n")
    return "".join(chunks)


def build_merged_coqproject(project_root: Path) -> Tuple[Path, bool]:
    """
    Return (path usable by coqdep -f, whether it should be deleted afterward).
    Existing COQ_PATH_SPEC_FILENAMES are concatenated in order, so _CoqProject
    -R flags and Make .v lists can both be preserved. Extra -R/-Q flags found
    in Makefile-like files are appended. The original file is reused only when
    there is exactly one spec file and no extra Makefile loadpath.
    """
    existing = [project_root / n for n in COQ_PATH_SPEC_FILENAMES if (project_root / n).is_file()]
    base_chunks: list[str] = []
    for p in existing:
        try:
            base_chunks.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    base = ("\n".join(base_chunks).strip() + "\n") if base_chunks else ""
    extra = collect_extra_loadpath_from_makefiles(project_root)
    extra_s = extra.strip()

    def sanitize_for_coqdep(text: str) -> Tuple[str, int]:
        """
        coqdep accepts a narrower _CoqProject syntax than coq_makefile.
        Some projects contain -install or COQDOCFLAGS=... lines that older
        coqdep versions reject as unknown options. Keep only:
        - lines starting with -I/-R/-Q/-arg (other -xxx options are kept
          conservatively, except -install)
        - plain .v file list lines
        """
        dropped = 0
        out: list[str] = []
        for raw in text.splitlines():
            line = raw.rstrip("\r\n")
            s = line.strip()
            if not s or s.startswith("#"):
                out.append(line)
                continue
            if "=" in s and not s.startswith("-"):
                # Makefile-style assignments, such as COQDOCFLAGS = ..., are not
                # accepted by coqdep.
                dropped += 1
                continue
            if s.startswith("-install"):
                dropped += 1
                continue
            # Allow -I/-R/-Q/-arg and other option lines. Unknown options will be
            # reported by coqdep later.
            if s.startswith("-"):
                out.append(line)
                continue
            # File lists: keep only .v entries.
            toks = s.split()
            if toks and all(t.endswith(".v") for t in toks):
                out.append(line)
            else:
                # Drop other non-empty lines to avoid coqdep parse failures.
                dropped += 1
        new_text = "\n".join(out).rstrip() + "\n"
        return new_text, dropped

    merged = (base.rstrip() + "\n" + extra).strip() + "\n"
    if not merged.strip():
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_CoqProject", delete=False, encoding="utf-8"
        )
        tmp.write("# empty: provide _CoqProject / Make or -R/-Q flags in a Makefile\n")
        tmp.close()
        return Path(tmp.name), True

    # First sanitize for coqdep compatibility.
    merged, dropped_lines = sanitize_for_coqdep(merged)

    # Important: when coqdep -f reads a _CoqProject file:
    # - relative physical directories in -I/-R/-Q are resolved relative to the
    #   _CoqProject file location;
    # - relative file-list entries such as `src/Foo.v` can be affected too.
    # Rewrite temporary-file content so:
    # - physical directory arguments to -I/-R/-Q are absolute under the project root;
    # - file-list tokens like `xxx.v` are absolute paths.
    # This keeps dependency resolution stable after the temporary file is created.
    root = _real(project_root)
    new_lines: list[str] = []
    for raw_line in merged.splitlines():
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" in stripped:
            new_lines.append(line)
            continue

        # Option lines: process each -I/-R/-Q token and make its physical
        # directory absolute. Projects such as CompCert often put multiple -R
        # flags on one line.
        if stripped.startswith("-"):
            parts = stripped.split()
            i = 0
            out_parts: list[str] = []
            while i < len(parts):
                tok = parts[i]
                if tok in ("-R", "-Q") and i + 2 < len(parts):
                    dir_tok = parts[i + 1]
                    log_tok = parts[i + 2]
                    clean_dir = dir_tok.strip().strip("\"").strip("'")
                    p = Path(clean_dir)
                    if p.is_absolute():
                        new_dir = str(p.resolve())
                    else:
                        new_dir = str((root / p).resolve())
                    out_parts.extend([tok, new_dir, log_tok])
                    i += 3
                    continue
                if tok == "-I" and i + 1 < len(parts):
                    dir_tok = parts[i + 1]
                    clean_dir = dir_tok.strip().strip("\"").strip("'")
                    p = Path(clean_dir)
                    if p.is_absolute():
                        new_dir = str(p.resolve())
                    else:
                        new_dir = str((root / p).resolve())
                    out_parts.extend([tok, new_dir])
                    i += 2
                    continue
                out_parts.append(tok)
                i += 1

            prefix_len = len(line) - len(line.lstrip())
            indent = line[:prefix_len]
            new_lines.append(indent + " ".join(out_parts))
            continue

        first = stripped.split()[0]
        if first.endswith(".v") and ("/" in first or "\\" in first or "." in first):
            p = Path(first)
            if p.is_absolute():
                new_token = str(p.resolve())
            else:
                new_token = (root / p).resolve()
            # Replace only the first token when possible.
            prefix_len = len(line) - len(line.lstrip())
            indent = line[:prefix_len]
            # Preserve any trailing tokens after the leading file token.
            rest = stripped[len(first) :].lstrip()
            new_line = indent + str(new_token) + ((" " + rest) if rest else "")
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    merged = "\n".join(new_lines).rstrip() + "\n"

    # If no merge/sanitize/absolute rewrite changed anything, reuse the original
    # file to avoid an unnecessary temporary file.
    if len(existing) == 1 and not extra_s and dropped_lines == 0:
        try:
            orig = existing[0].read_text(encoding="utf-8", errors="replace").rstrip() + "\n"
        except OSError:
            orig = ""
        if merged == orig:
            return existing[0], False

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_CoqProject", delete=False, encoding="utf-8"
    )
    tmp.write(merged)
    tmp.close()
    return Path(tmp.name), True


def vo_to_v(vo_path: str) -> Optional[str]:
    for suf in (".vo", ".vio"):
        if vo_path.endswith(suf):
            return vo_path[: -len(suf)] + ".v"
    return None


def run_coqdep(
    project_root: Path, coqproject_file: Path, rel_v: str, coqdep_bin: str
) -> Set[str]:
    """Return direct .vo/.vio dependencies for rel_v as relative .v paths."""
    rel_v = rel_v.replace(os.sep, "/")
    cmd = [coqdep_bin, "-f", str(coqproject_file), rel_v]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        raise RuntimeError(f"failed to execute coqdep: {e}") from e

    # coqdep may print rules for other files, especially when the -f file lists
    # many sources. Only read the rule for rel_v's .vo/.vio target; otherwise
    # unrelated files enter the dependency closure.
    rel_vo = rel_v[:-2] + ".vo" if rel_v.endswith(".v") else rel_v + ".vo"
    rel_vio = rel_v[:-2] + ".vio" if rel_v.endswith(".v") else rel_v + ".vio"

    deps: Set[str] = set()
    matched_any_rule = False
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("***"):
            continue
        m = _COQDEP_RULE_RE.match(line)
        if not m:
            continue
        lhs = m.group(1).split()
        if rel_vo not in lhs and rel_vio not in lhs:
            continue
        matched_any_rule = True
        rhs = m.group(2).split()
        for token in rhs:
            v = vo_to_v(token)
            if v:
                deps.add(v.replace(os.sep, "/"))

    # If no rule matched this file, include a more useful error. stderr usually
    # contains the key loadpath clue.
    if not matched_any_rule and proc.stderr.strip():
        raise RuntimeError(
            "coqdep did not output a dependency rule for the target file; "
            "the loadpath or coqdep input may be invalid.\n"
            + proc.stderr.strip().splitlines()[0]
        )
    return deps


def is_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def transitive_deps_coqdep(
    project_root: Path,
    coqproject_file: Path,
    start_rel: str,
    coqdep_bin: str,
) -> Tuple[Set[Path], Set[Path]]:
    root = _real(project_root)
    rel_queue = [start_rel.replace(os.sep, "/")]
    seen_rel: Set[str] = set()
    copy_result: Set[Path] = set()
    # Used only to generate the Make/_CoqProject compile list: the coqdep
    # closure, excluding files reached only through Load.
    compile_rel: Set[str] = {start_rel.replace(os.sep, "/")}

    while rel_queue:
        rel = rel_queue.pop()
        if rel in seen_rel:
            continue
        seen_rel.add(rel)
        abs_v = (root / rel).resolve()
        if not abs_v.is_file():
            continue
        if not is_under_root(abs_v, root):
            continue
        copy_result.add(abs_v)

        # Handle Load dependencies as an extra pass; coqdep may not cover them.
        for t in extract_loads_from_v(abs_v):
            lp = resolve_load_target(abs_v, t)
            if lp and lp.is_file() and is_under_root(lp, root):
                try:
                    lrel = lp.relative_to(root).as_posix()
                except ValueError:
                    lrel = os.path.relpath(lp, root).replace(os.sep, "/")
                if lrel not in seen_rel:
                    rel_queue.append(lrel)

        for d in run_coqdep(project_root, coqproject_file, rel, coqdep_bin):
            av = (root / d).resolve()
            if av.is_file() and is_under_root(av, root):
                if d not in seen_rel:
                    rel_queue.append(d)
                compile_rel.add(d)
    compile_result: Set[Path] = set()
    for r in compile_rel:
        p = (root / r).resolve()
        if p.is_file() and is_under_root(p, root):
            compile_result.add(p)
    return copy_result, compile_result


def parse_loadpath_entries(
    project_root: Path, coqproject_text: str
) -> list[Tuple[Path, str, bool]]:
    """
    Parse -R / -Q entries and return
    (absolute physical directory, logical prefix, whether it is -R).
    Lines follow the usual coq_makefile / _CoqProject convention.
    """
    entries: list[Tuple[Path, str, bool]] = []
    tokens: list[str] = []
    for raw_line in coqproject_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        tokens.extend(parts)

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-R", "-Q") and i + 2 < len(tokens):
            phys = Path(tokens[i + 1])
            logical = tokens[i + 2]
            if not phys.is_absolute():
                phys = (project_root / phys).resolve()
            else:
                phys = phys.resolve()
            entries.append((phys, logical, t == "-R"))
            i += 3
            continue
        i += 1
    return entries


def resolve_require_module(
    mod: str,
    from_prefix: Optional[str],
    entries: list[Tuple[Path, str, bool]],
    current_file: Path,
    project_root: Path,
) -> Optional[Path]:
    """Best-effort resolution of a module path to a .v file without coqdep."""
    mod = mod.strip()
    if not mod:
        return None

    if from_prefix:
        full = f"{from_prefix}.{mod}"
    else:
        full = mod

    # Current file directory; Coq normally includes it in the loadpath.
    candidates: list[Path] = []
    cur_dir = current_file.parent.resolve()
    parts = mod.split(".")
    candidates.append(cur_dir.joinpath(*parts).with_suffix(".v"))
    if from_prefix:
        fparts = from_prefix.split(".") + parts
        candidates.append(cur_dir.joinpath(*fparts).with_suffix(".v"))

    for c in candidates:
        if c.is_file() and is_under_root(c, project_root):
            return c

    # Resolve through -R/-Q entries using the longest logical-prefix match.
    best: Optional[Tuple[int, Path]] = None
    for phys, logical, _ in entries:
        if full == logical or full.startswith(logical + "."):
            suffix = full[len(logical) :].lstrip(".")
            if suffix:
                rel = suffix.split(".")
                p = phys.joinpath(*rel).with_suffix(".v")
            else:
                last = logical.split(".")[-1]
                p = (phys / f"{last}.v") if phys.is_dir() else phys.with_suffix(".v")
            if p.is_file():
                score = len(logical)
                if best is None or score > best[0]:
                    best = (score, p)

    if best:
        p = best[1]
        if is_under_root(p, project_root):
            return p
    return None


def extract_requires_from_v(vfile: Path) -> list[Tuple[Optional[str], list[str]]]:
    text = strip_coq_comments(vfile.read_text(encoding="utf-8", errors="replace"))
    out: list[Tuple[Optional[str], list[str]]] = []
    for m in _REQUIRE_RE.finditer(text):
        fr = m.group("from")
        mods_raw = m.group("mods")
        mods = [x for x in re.split(r"\s+", mods_raw.strip()) if x]
        out.append((fr, mods))
    return out


def transitive_deps_manual(
    project_root: Path,
    coqproject_text: str,
    start: Path,
) -> Set[Path]:
    entries = parse_loadpath_entries(project_root, coqproject_text)
    root = _real(project_root)
    queue = [start.resolve()]
    seen: Set[Path] = set()
    while queue:
        v = queue.pop()
        if v in seen:
            continue
        if not v.is_file() or not is_under_root(v, root):
            continue
        seen.add(v)
        for fr, mods in extract_requires_from_v(v):
            for mod in mods:
                dep = resolve_require_module(mod, fr, entries, v, root)
                if dep and dep not in seen:
                    queue.append(dep)
    return seen


def kept_v_rel_posix(project_root: Path, vfiles: Set[Path]) -> Set[str]:
    root = _real(project_root)
    return {vf.resolve().relative_to(root).as_posix() for vf in vfiles}


def _v_path_in_kept(path_str: str, root: Path, kept: Set[str]) -> bool:
    try:
        rel = (root / path_str).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    return rel in kept


def filter_coq_make_input_line(line: str, root: Path, kept: Set[str]) -> Optional[str]:
    """
    Process one coq_makefile input line in Make / _CoqProject style.
    Return None to drop the line; otherwise return the line without a newline.
    """
    raw = line.replace("\r", "")
    if "#" in raw:
        main, cpart = raw.split("#", 1)
        comment = "#" + cpart
    else:
        main, comment = raw, ""

    body = main.strip()
    if not body:
        return raw.rstrip("\n")
    # Keep -R/-Q/-arg options. A root .v may Require a logical library in a
    # subdirectory, so loadpath mappings cannot be dropped based only on whether
    # the mapped directory contains copied .v files.
    if body.startswith("-"):
        return raw.rstrip("\n")

    tokens = body.split()
    if tokens and all(t.endswith(".v") for t in tokens):
        kt = [t for t in tokens if _v_path_in_kept(t, root, kept)]
        if not kt:
            return None
        indent = raw[: len(raw) - len(raw.lstrip())]
        new_main = indent + " ".join(kt)
        if comment.strip():
            pad = " " if new_main.strip() else ""
            return (new_main.rstrip() + pad + comment).rstrip()
        return new_main.rstrip()

    return raw.rstrip("\n")


def filter_coq_make_input_text(text: str, root: Path, kept: Set[str]) -> Tuple[str, int]:
    out: list[str] = []
    dropped = 0
    for line in text.splitlines():
        res = filter_coq_make_input_line(line, root, kept)
        if res is None:
            dropped += 1
            continue
        out.append(res)
    new_text = "\n".join(out)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text, dropped


def _dir_token_exists_in_root(root: Path, dir_tok: str) -> bool:
    t = dir_tok.strip().strip('"').strip("'")
    p = Path(t)
    if p.is_absolute():
        return p.is_dir()
    return (root / p).is_dir()


def prune_missing_loadpath_flags(text: str, root: Path) -> Tuple[str, int]:
    """
    In the copied tree, drop -R/-Q/-I flags pointing to missing directories.
    Such directories may have been omitted by minimal dependency pruning.
    Supports multiple -R/-Q flags on one line, as in CompCert _CoqProject.
    Return (new text, number of removed flags).
    """
    removed = 0
    out_lines: list[str] = []
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        ending = raw[len(line) :]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out_lines.append(raw)
            continue
        if not stripped.startswith("-"):
            out_lines.append(raw)
            continue

        parts = stripped.split()
        i = 0
        kept_parts: list[str] = []
        while i < len(parts):
            tok = parts[i]
            if tok in ("-R", "-Q") and i + 2 < len(parts):
                d, log = parts[i + 1], parts[i + 2]
                if _dir_token_exists_in_root(root, d):
                    kept_parts.extend([tok, d, log])
                else:
                    removed += 1
                i += 3
                continue
            if tok == "-I" and i + 1 < len(parts):
                d = parts[i + 1]
                if _dir_token_exists_in_root(root, d):
                    kept_parts.extend([tok, d])
                else:
                    removed += 1
                i += 2
                continue
            kept_parts.append(tok)
            i += 1

        if not kept_parts:
            # The whole line consisted of removed loadpath flags.
            continue
        prefix_len = len(line) - len(line.lstrip())
        indent = line[:prefix_len]
        out_lines.append(indent + " ".join(kept_parts) + ending)

    return "".join(out_lines), removed


def collect_v_paths_listed_in_coq_input(text: str, root: Path) -> Set[str]:
    """Return .v files already listed in Make/_CoqProject, relative to root."""
    listed: Set[str] = set()
    for line in text.splitlines():
        main = line.split("#", 1)[0]
        body = main.strip()
        if not body or body.startswith("-"):
            continue
        tokens = body.split()
        if not tokens or not all(t.endswith(".v") for t in tokens):
            continue
        for t in tokens:
            try:
                rel = (root / t).resolve().relative_to(root.resolve()).as_posix()
                listed.add(rel)
            except (ValueError, OSError):
                pass
    return listed


def augment_make_input_with_closure(text: str, root: Path, kept: Set[str]) -> Tuple[str, int]:
    """
    coq_makefile generates build rules only for .v files listed in its input.
    If transitive dependencies are not listed, make can need *.v files without
    having rules for them. Append kept .v files that are not already listed.
    This applies to Make and _CoqProject when they list .v files directly.
    """
    listed = collect_v_paths_listed_in_coq_input(text, root)
    missing = sorted(kept - listed)
    if not missing:
        return text, 0
    sep = "\n" if text.strip() else ""
    new_text = text.rstrip() + sep + "\n".join(missing) + "\n"
    return new_text, len(missing)


def filter_makefile_vvar_line(bare_line: str, root: Path, kept: Set[str]) -> str:
    """
    If a line is a Makefile variable assignment and the right side before '#'
    is only whitespace-separated .v paths, drop paths not copied.
    bare_line has no trailing \\r\\n.
    """
    if "#" in bare_line:
        main, cpart = bare_line.split("#", 1)
        comment = "#" + cpart
    else:
        main, comment = bare_line, ""

    m = _MAKEFILE_ASSIGN_RE.match(main)
    if not m:
        return bare_line
    indent, name, op, rhs_mid = m.group(1), m.group(2), m.group(3), m.group(4)
    rhs_clean = rhs_mid.strip()
    if not rhs_clean or ".v" not in rhs_clean:
        return bare_line
    tokens = rhs_clean.split()
    if not tokens or not all(t.endswith(".v") for t in tokens):
        return bare_line
    kt = [t for t in tokens if _v_path_in_kept(t, root, kept)]
    if len(kt) == len(tokens):
        return bare_line
    if not kt:
        rebuilt = f"{indent}{name}{op}{comment}".rstrip()
        return rebuilt
    rhs_new = " ".join(kt)
    pad = " " if comment.strip() and rhs_new else ""
    return f"{indent}{name}{op}{rhs_new}{pad}{comment}".rstrip()


def _shell_single_quote_for_cond(s: str) -> str:
    """Return a single-quoted literal suitable for `[ -d ... ]`."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def rewrite_makefile_optional_make_c_recipes(text: str) -> Tuple[str, int]:
    """
    Rewrite recipe lines such as ``$(MAKE) -C dir ...`` / ``make -C dir ...``
    where dir is a literal path without Makefile variables into
    ``if [ -d dir ]; then ...; fi``. This lets make complete when a minimal copy
    intentionally omits a subproject directory.

    Skip lines already guarded with ``if [ -d``, dirs containing ``$``, and
    lines with multiple ``-C`` occurrences.
    Return (new text, number of rewritten lines).
    """
    changed = 0
    out: list[str] = []

    _make_c_body_re = re.compile(
        r"^(\s*)(@?\s*)(\$\{MAKE\}|\$\(MAKE\)|make)\s+-C\s+(\S+)\s*(.*)$",
        re.IGNORECASE | re.DOTALL,
    )

    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        ending = line[len(bare) :]

        m_tab = re.match(r"^(\t+)(.*)$", bare)
        if not m_tab:
            out.append(line)
            continue
        tabs, body = m_tab.group(1), m_tab.group(2)
        body_ls = body.lstrip()
        if body_ls.startswith("if [ -d ") and "; then" in body_ls:
            out.append(line)
            continue

        m2 = _make_c_body_re.match(body)
        if not m2:
            out.append(line)
            continue

        dir_arg = m2.group(4)
        rest = (m2.group(5) or "").strip()
        if "$" in dir_arg:
            out.append(line)
            continue
        if "-C" in rest:
            # Multiple recursive subdirectories on one line: skip conservatively.
            out.append(line)
            continue

        qdir = _shell_single_quote_for_cond(dir_arg)
        new_bare = f"{tabs}@if [ -d {qdir} ]; then {body}; fi"
        changed += 1
        out.append(new_bare + ending)

    return "".join(out), changed


def filter_root_makefile_text(text: str, root: Path, kept: Set[str]) -> Tuple[str, int]:
    """Conservatively prune .v lists in the root Makefile."""
    changed = 0
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if ".v" not in line:
            out.append(line)
            continue
        bare = line.rstrip("\r\n")
        ending = line[len(bare) :]
        nb = filter_makefile_vvar_line(bare, root, kept)
        if nb != bare:
            changed += 1
        out.append(nb + ending)
    return "".join(out), changed


def list_root_build_files(project_root: Path) -> list[Path]:
    """Return root-level Coq build files that exist."""
    root = _real(project_root)
    found: list[Path] = []
    for name in ROOT_COQ_BUILD_NAMES:
        p = root / name
        if p.is_file():
            found.append(p)
    for p in sorted(root.glob("*.opam")):
        if p.is_file():
            found.append(p)
    seen: Set[Path] = set()
    uniq: list[Path] = []
    for p in found:
        k = p.resolve()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def copy_root_build_files(project_root: Path, dest_root: Path) -> None:
    for src in list_root_build_files(project_root):
        shutil.copy2(src, dest_root / src.name)


def ensure_minimal_build_files(dest_root: Path, project_name: str, kept_v_rel: Set[str]) -> None:
    """
    If the source project has no _CoqProject/Make/Makefile build entry point,
    generate minimal versions in the copied tree:
    - _CoqProject: list only copied .v files, without guessing -Q/-R
    - Makefile: generate and include Makefile.coq through coq_makefile

    The goal is to make `make` work in the copied tree and let coqc/Makefile.coq
    drive compilation of the target file.
    """
    dre = _real(dest_root)
    dre.mkdir(parents=True, exist_ok=True)

    has_path_spec = any((dre / n).is_file() for n in ("_CoqProject", "CoqProject", "Make"))
    has_makefile = any((dre / n).is_file() for n in ("Makefile", "makefile", "GNUmakefile"))

    def _looks_complex_makefile(text: str) -> bool:
        s = text
        # Typical large-project Makefile markers: generated files, extraction,
        # depend, .depend, Makefile.extr, and similar.
        markers = [
            "Makefile.extr",
            ".depend",
            "depend:",
            "extraction",
            "Parser.v",
            "SelectOp.v",
            "ConstpropOp.v",
            "include VERSION",
            "include Makefile.config",
        ]
        return any(m in s for m in markers)

    # If a Makefile exists but is a complex top-level build, such as CompCert,
    # replace it with a minimal Coq Makefile driver.
    mf_path = dre / "Makefile"
    if mf_path.is_file():
        try:
            mf_text = mf_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            mf_text = ""
        if _looks_complex_makefile(mf_text):
            backup = dre / "Makefile.orig"
            if not backup.exists():
                shutil.copy2(mf_path, backup)
            mf_path.write_text(
                "\n".join(
                    [
                        "# Auto-generated Makefile (minimal Coq build wrapper)",
                        f"# Original Makefile saved as {backup.name}",
                        "",
                        "all: Makefile.coq",
                        "\t$(MAKE) -f Makefile.coq all",
                        "",
                        "Makefile.coq: _CoqProject",
                        "\tcoq_makefile -f _CoqProject -o Makefile.coq",
                        "",
                        "clean: Makefile.coq",
                        "\t$(MAKE) -f Makefile.coq clean",
                        "",
                        ".PHONY: all clean",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            has_makefile = True
            print("Detected a complex top-level Makefile; replaced it with a minimal Coq build wrapper and saved Makefile.orig.")

    if has_path_spec and has_makefile:
        return

    # Generate _CoqProject if missing.
    if not (dre / "_CoqProject").is_file():
        # If all .v files are under a single subdirectory, such as theories/,
        # map that directory to an empty logical prefix. This supports unprefixed
        # imports such as `Require Import Foo.` when compiling from the root.
        def infer_single_subdir_qflag(vrels: Set[str]) -> Optional[str]:
            comps: Set[str] = set()
            for r in vrels:
                p = Path(r)
                if len(p.parts) >= 2:
                    comps.add(p.parts[0])
                else:
                    comps.add("")  # There is a file at the root.
            if len(comps) == 1:
                only = next(iter(comps))
                return only if only else None
            return None

        lines: list[str] = []
        lines.append(f"# Auto-generated minimal _CoqProject for {project_name}\n")
        qdir = infer_single_subdir_qflag(kept_v_rel)
        if qdir:
            lines.append(f'-Q {qdir} ""\n')
            lines.append("\n")
        for rel in sorted(kept_v_rel):
            lines.append(f"{rel}\n")
        (dre / "_CoqProject").write_text("".join(lines), encoding="utf-8")
        print("Generated a minimal _CoqProject in the copied root because the source project did not provide one.")

    # Generate Makefile if missing.
    if not has_makefile:
        mf = dre / "Makefile"
        mf.write_text(
            "\n".join(
                [
                    "# Auto-generated Makefile (minimal)",
                    "all: Makefile.coq",
                    "\t$(MAKE) -f Makefile.coq all",
                    "",
                    "Makefile.coq: _CoqProject",
                    "\tcoq_makefile -f _CoqProject -o Makefile.coq",
                    "",
                    "clean: Makefile.coq",
                    "\t$(MAKE) -f Makefile.coq clean",
                    "",
                    ".PHONY: all clean",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print("Generated a minimal Makefile in the copied root because the source project did not provide one.")


def prune_dest_build_files(
    dest_root: Path,
    compile_vfiles: Set[Path],
    project_root: Path,
    enabled: bool,
) -> None:
    """
    In the copied root, remove non-copied .v lines from Make / _CoqProject and
    similar files. Conservatively rewrite root Makefile variable assignments
    whose right side is only .v paths. Delete Makefile.coq so the next make
    regenerates it from the pruned input through coq_makefile.
    """
    if not enabled:
        return
    kept = kept_v_rel_posix(project_root, compile_vfiles)
    dre = _real(dest_root)

    for name in sorted(PRUNE_COQ_INPUT_NAMES):
        p = dre / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # Drop -R/-Q/-I entries pointing to missing directories in the copied
        # tree so coqdep/coqc do not fail before compiling.
        text2, nrm = prune_missing_loadpath_flags(text, dre)
        if nrm > 0:
            text = text2
            print(f"Removed {nrm} -R/-Q/-I entries pointing to missing directories from {name}")
        new_text, dropped = filter_coq_make_input_text(text, dre, kept)
        nadd = 0
        if name in ("Make", "_CoqProject", "CoqProject"):
            new_text, nadd = augment_make_input_with_closure(new_text, dre, kept)
        if dropped > 0 or nadd > 0 or new_text != text:
            p.write_text(new_text, encoding="utf-8")
            if dropped > 0:
                print(f"Pruned {name}: removed {dropped} lines for .v files that were not copied")
            if nadd > 0:
                print(
                    f"Appended {nadd} .v files to {name} for transitive dependencies; coq_makefile needs every source to compile listed"
                )

    mconf = dre / "Makefile.coq.conf"
    if mconf.is_file():
        text = mconf.read_text(encoding="utf-8", errors="replace")
        new_text, nch = filter_root_makefile_text(text, dre, kept)
        if new_text != text:
            mconf.write_text(new_text, encoding="utf-8")
            if nch > 0:
                print(f"Pruned Makefile.coq.conf: rewrote {nch} variable lines containing .v files")

    for mf in ("Makefile", "makefile", "GNUmakefile"):
        p = dre / mf
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        filtered, nch = filter_root_makefile_text(text, dre, kept)
        wrapped, nwrap = rewrite_makefile_optional_make_c_recipes(filtered)
        if wrapped != text:
            p.write_text(wrapped, encoding="utf-8")
        if nch > 0:
            print(f"Pruned {mf}: rewrote {nch} variable assignments containing only .v files")
        if nwrap > 0:
            print(
                f"Hardened {mf}: added missing-subdirectory guards to {nwrap} ``$(MAKE) -C ...`` recipe lines"
            )

    stale_coq = dre / "Makefile.coq"
    if stale_coq.is_file():
        stale_coq.unlink()
        print("Removed stale Makefile.coq from the copied tree; run make to regenerate it from the current Make/_CoqProject")

    stale_deps = dre / ".coqdeps.d"
    if stale_deps.is_file():
        stale_deps.unlink()
        print("Removed stale .coqdeps.d from the copied tree; old coqdep caches can reference missing or uncopied .v files")

    # Makefile.coq.local may include files that do not exist, such as
    # Makefile.ml-files, which makes make fail immediately.
    local = dre / "Makefile.coq.local"
    if local.is_file():
        try:
            lines = local.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except OSError:
            lines = []
        kept_lines: list[str] = []
        removed = 0
        for raw in lines:
            s = raw.strip()
            if s.startswith("include ") or s.startswith("-include "):
                inc = s.split(None, 1)[1].strip() if len(s.split(None, 1)) > 1 else ""
                # Remove simple quotes.
                inc2 = inc.strip().strip('"').strip("'")
                p = (dre / inc2) if not Path(inc2).is_absolute() else Path(inc2)
                if not p.exists():
                    removed += 1
                    continue
            kept_lines.append(raw)
        if removed > 0:
            new_text = "".join(kept_lines).strip()
            if not new_text:
                local.unlink()
                print("Removed Makefile.coq.local because it only included files that do not exist")
            else:
                local.write_text("".join(kept_lines), encoding="utf-8")
                print(f"Removed {removed} include lines pointing to missing files from Makefile.coq.local")


def copy_minimal_tree(
    project_root: Path,
    copy_vfiles: Set[Path],
    compile_vfiles: Set[Path],
    dest_root: Path,
    prune_make_inputs: bool = True,
    copy_artifacts: bool = False,
) -> None:
    root = _real(project_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    for v in sorted(copy_vfiles):
        rel = v.relative_to(root)
        # Always copy source files.
        dst_v = dest_root / rel
        dst_v.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v, dst_v)

        # Optionally copy build artifacts. Disabled by default because .vo files
        # can fail to load across Coq versions.
        if copy_artifacts:
            for suffix in ARTIFACT_SUFFIXES:
                src = v.with_suffix(suffix)
                if not src.is_file():
                    continue
                dst = dest_root / rel.parent / src.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    copy_root_build_files(project_root, dest_root)
    prune_dest_build_files(dest_root, compile_vfiles, project_root, prune_make_inputs)
    # Generate minimal build entry points if the source project did not provide them.
    ensure_minimal_build_files(
        dest_root, _real(project_root).name, kept_v_rel_posix(project_root, compile_vfiles)
    )
    ensure_dest_tree_user_writable(dest_root)


def ensure_dest_tree_user_writable(dest_root: Path) -> None:
    """
    Source trees such as test-repos are often 0444. shutil.copy2 preserves
    read-only bits, which prevents later file replacement. After copying and
    generating build files, add owner-write permission to all non-symlink paths;
    directories also get owner-execute permission.
    """
    dre = _real(dest_root)
    if not dre.is_dir():
        return
    for path in dre.rglob("*"):
        if path.is_symlink():
            continue
        try:
            mode = path.stat().st_mode
        except OSError as e:
            print(f"WARNING: failed to chmod {path}: {e}", file=sys.stderr)
            continue
        if path.is_dir():
            os.chmod(path, mode | stat.S_IWUSR | stat.S_IXUSR)
        else:
            os.chmod(path, mode | stat.S_IWUSR)


def find_coqdep() -> Optional[str]:
    return shutil.which("coqdep")


def build_fallback_coqdep_projectfile(project_root: Path, vfile: Path) -> Tuple[Path, bool]:
    """
    Generate a minimal -f file for coqdep when the project has no path spec
    files such as _CoqProject or Make. This primarily supports unprefixed
    same-directory imports such as `Require Import Foo.`.
    """
    root = _real(project_root)
    rel = vfile.resolve().relative_to(root.resolve()).as_posix()
    first = Path(rel).parts[0] if len(Path(rel).parts) >= 2 else ""
    lines: list[str] = ["# Auto-generated for coqdep\n"]
    if first and (root / first).is_dir():
        # coqdep resolves the physical directory in -Q relative to the project
        # file location, so use an absolute path.
        lines.append(f'-Q {(root / first).resolve()} ""\n')
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_CoqProject", delete=False, encoding="utf-8")
    tmp.write("".join(lines))
    tmp.close()
    return Path(tmp.name), True


def parse_input_to_project_and_vfile(input_path: Path) -> Tuple[Path, Path]:
    """
    Support two input forms, with mappings determined by environment variables:
    1) CoqStoq: input is a .v file
       Example input: $COQSTOQ_PATH/test-repos/<project>/.../<file>.v
       Output: project_root=$COQSTOQ_PATH/test-repos/<project>, vfile=input_path

    2) CoqGym: input is a .json file
       Example input: $COQGYM_PATH/data/<project>/.../<file>.json
       Output: project_root=$COQGYM_PATH/coq_projects/<project>
               vfile is derived by replacing data with coq_projects and
               changing the suffix from .json to .v
    """
    inp = _real(input_path)
    if not inp.is_file():
        raise RuntimeError(f"input path does not exist or is not a file: {inp}")

    if inp.suffix == ".v":
        stoq_root = os.environ.get("COQSTOQ_PATH")
        if stoq_root:
            base = _real(Path(stoq_root) / "test-repos")
        else:
            # sudo does not inherit environment variables by default; infer
            # .../test-repos/<project>/... from the path when possible.
            parts = inp.parts
            if "test-repos" not in parts:
                raise RuntimeError(
                    "COQSTOQ_PATH is not set and the input path does not contain test-repos; cannot resolve .v input."
                )
            idx = parts.index("test-repos")
            base = _real(Path(*parts[: idx + 1]))
        try:
            rel = inp.relative_to(base)
        except ValueError as e:
            raise RuntimeError(
                f".v input is not under {base}; actual input: {inp}"
            ) from e
        if len(rel.parts) < 2:
            raise RuntimeError(f"cannot extract project name from .v input: {inp}")
        project_name = rel.parts[0]
        project_root = base / project_name
        vfile = inp
        if not project_root.is_dir():
            raise RuntimeError(f"resolved project directory does not exist: {project_root}")
        if not vfile.is_file():
            raise RuntimeError(f"resolved .v file does not exist: {vfile}")
        return project_root, vfile

    if inp.suffix == ".json":
        gym_root = os.environ.get("COQGYM_PATH")
        if gym_root:
            data_base = _real(Path(gym_root) / "data")
            projects_base = _real(Path(gym_root) / "coq_projects")
        else:
            # sudo may drop environment variables; infer .../data/<project>/...
            # from the path when possible.
            parts = inp.parts
            if "data" not in parts:
                raise RuntimeError(
                    "COQGYM_PATH is not set and the input path does not contain data; cannot resolve .json input."
                )
            idx = parts.index("data")
            inferred_root = _real(Path(*parts[:idx]))
            data_base = _real(inferred_root / "data")
            projects_base = _real(inferred_root / "coq_projects")
        try:
            rel = inp.relative_to(data_base)
        except ValueError as e:
            raise RuntimeError(
                f".json input is not under {data_base}; actual input: {inp}"
            ) from e
        if len(rel.parts) < 2:
            raise RuntimeError(f"cannot extract project name from .json input: {inp}")
        project_name = rel.parts[0]
        project_root = projects_base / project_name

        v_rel = Path(*rel.parts[1:]).with_suffix(".v")
        vfile = project_root / v_rel
        if not project_root.is_dir():
            raise RuntimeError(f"resolved project directory does not exist: {project_root}")
        if not vfile.is_file():
            raise RuntimeError(
                f"could not find the mapped .v file.\n"
                f"  input: {inp}\n"
                f"  derived vfile: {vfile}\n"
                f"  check that data -> coq_projects and .json -> .v match your dataset."
            )
        return project_root, vfile

    raise RuntimeError(
        f"unsupported input suffix: {inp.suffix} (only .v for CoqStoq or .json for CoqGym are supported)"
    )


_OPEN_SECTION_RE = re.compile(r"^\s*Section\s+([A-Za-z_][A-Za-z0-9_']*)\s*\.\s*$")
_MODULE_TYPE_HEAD_RE = re.compile(r"^Module\s+Type\s+([A-Za-z_][A-Za-z0-9_']*)\s*")
_MODULE_HEAD_RE = re.compile(r"^Module\s+(?!Import\b)([A-Za-z_][A-Za-z0-9_']*)\s*")
_END_NAMED_RE = re.compile(r"^\s*End\s+([A-Za-z_][A-Za-z0-9_']*)\s*\.\s*$")


def _coq_fragment_has_top_level_sentence_dot(fragment: str) -> bool:
    """
    Return whether the remaining fragment of this line contains a sentence dot
    at nesting depth 0 for parentheses, brackets, and braces. This distinguishes
    ``Module M := Expr.`` (single-line functor/alias, already implicitly closed)
    from a multi-line definition starting with ``Module M :=`` that still needs
    ``End M``.

    Assumes the text containing fragment has already had Coq comments removed,
    matching the prune scan.
    """
    depth = 0
    i = 0
    n = len(fragment)
    while i < n:
        c = fragment[i]
        if c == '"':
            i += 1
            while i < n:
                if fragment[i] == '"' and fragment[i - 1 : i] != "\\":
                    i += 1
                    break
                i += 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        elif c == "." and depth == 0:
            return True
        i += 1
    return False


def _consume_balanced_group(s: str, opener: str, closer: str) -> Optional[str]:
    """If ``s`` starts with ``opener``, return the tail after its matching closer."""
    if not s.startswith(opener):
        return None
    depth = 0
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '"':
            i += 1
            while i < n:
                if s[i] == '"' and s[i - 1 : i] != "\\":
                    i += 1
                    break
                i += 1
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return s[i + 1 :]
        i += 1
    return None


def _strip_leading_binders(s: str) -> str:
    """Strip ``(...)`` / ``{...}`` binder blocks after ``Module M``."""
    s = s.lstrip()
    while True:
        tail = _consume_balanced_group(s, "(", ")")
        if tail is not None:
            s = tail.lstrip()
            continue
        tail = _consume_balanced_group(s, "{", "}")
        if tail is not None:
            s = tail.lstrip()
            continue
        break
    return s


def _parse_module_opener(stripped_line: str) -> Optional[Tuple[str, str, str]]:
    """
    If this line starts with ``Module Type ...`` or ``Module ...``, return
    ``(kind, name, rest_after_name)``; otherwise return ``None``.
    ``rest_after_name`` is the fragment after the module name and following
    whitespace, before stripping binders.
    """
    m = _MODULE_TYPE_HEAD_RE.match(stripped_line)
    if m:
        return ("Module Type", m.group(1), stripped_line[m.end() :])
    m = _MODULE_HEAD_RE.match(stripped_line)
    if m:
        return ("Module", m.group(1), stripped_line[m.end() :])
    return None


def _should_stack_open_module(rest_after_name: str) -> bool:
    """
    Return whether a ``Module`` / ``Module Type`` opener introduces a block that
    needs ``End M``.

    - ``Module M := Expr.`` / ``Module M : S := Expr.`` are closed on the same
      line and are not pushed.
    - ``Module M.`` / ``Module M <: S.`` / ``Module M : S.`` /
      ``Module M (x:T).`` are pushed.
    """
    rest = _strip_leading_binders(rest_after_name)
    if not rest:
        return True
    if rest.startswith(":="):
        return not _coq_fragment_has_top_level_sentence_dot(rest)
    if rest.startswith("."):
        return True
    if rest.startswith("<:"):
        idx = rest.find(":=")
        if idx != -1:
            return not _coq_fragment_has_top_level_sentence_dot(rest[idx:])
        return True
    if rest.startswith(":"):
        idx = rest.find(":=")
        if idx != -1:
            return not _coq_fragment_has_top_level_sentence_dot(rest[idx:])
        return True
    return False


def _coqstoq_column_exclusive_end(column_raw: int) -> Optional[int]:
    """Treat CoqStoq Position.column as an exclusive end column when > 0."""
    return None if column_raw <= 0 else column_raw + 1


def extract_coq_text_span(
    lines: List[str],
    start_line0: int,
    start_col0: int,
    end_line0: int,
    end_col0_raw: int,
) -> str:
    """Slice source text by 0-based line/column positions."""
    if not lines or start_line0 < 0 or end_line0 < 0:
        return ""
    if start_line0 > end_line0:
        return ""
    start_line0 = min(start_line0, len(lines) - 1)
    end_line0 = min(end_line0, len(lines) - 1)
    end_col_excl = _coqstoq_column_exclusive_end(end_col0_raw)
    parts: List[str] = []
    for line_index in range(start_line0, end_line0 + 1):
        line = lines[line_index]
        if line_index == start_line0 and line_index == end_line0:
            start_col = max(0, min(start_col0, len(line)))
            if end_col_excl is None:
                parts.append(line[start_col:])
            else:
                end_col = max(start_col, min(end_col_excl, len(line)))
                parts.append(line[start_col:end_col])
        elif line_index == start_line0:
            start_col = max(0, min(start_col0, len(line)))
            parts.append(line[start_col:])
        elif line_index == end_line0:
            if end_col_excl is None:
                parts.append(line)
            else:
                end_col = max(0, min(end_col_excl, len(line)))
                parts.append(line[:end_col])
        else:
            parts.append(line)
    return "\n".join(parts)


def read_reference_proof_text(
    vfile: Path,
    start_line0: int,
    start_col0: int,
    end_line0: int,
    end_col0_raw: int,
) -> str:
    try:
        raw_lines = vfile.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        raise RuntimeError(f"failed to read source .v file: {vfile}: {e}") from e
    return extract_coq_text_span(
        raw_lines, start_line0, start_col0, end_line0, end_col0_raw
    )


def emit_reference_proof_to_stdout(
    vfile: Path,
    start_line0: int,
    start_col0: int,
    end_line0: int,
    end_col0_raw: int,
) -> None:
    proof_text = read_reference_proof_text(
        vfile, start_line0, start_col0, end_line0, end_col0_raw
    )
    print("--- standard-proof ---", file=sys.stderr)
    sys.stdout.write(proof_text)
    if proof_text and not proof_text.endswith("\n"):
        sys.stdout.write("\n")


def _trim_lines_with_col(lines: List[str], end_line0: int, end_col0: Optional[int]) -> List[str]:
    """
    0-based end_line/end_col. Keep text through that position. If end_col0 is
    None, keep the full end line.
    """
    if end_line0 < 0:
        return []
    end_line0 = min(end_line0, len(lines) - 1)
    out = lines[: end_line0 + 1]
    if end_col0 is not None and out:
        last = out[-1]
        if end_col0 < 0:
            out[-1] = ""
        else:
            out[-1] = last[: end_col0]
    return out


def prune_coq_file_to_theorem(
    src_v: Path,
    dst_v: Path,
    theorem_end_line0: int,
    theorem_end_col0: Optional[int],
) -> None:
    """
    Trim dst_v to the start of the source through the target theorem statement
    end position, then write ``Proof. Admitted.`` in place of the original proof.
    Close any unclosed Section/Module blocks needed for compilation.

    Single-line functors such as ``Module M := Expr.`` or
    ``Module Type M := Expr.`` do not use an explicit ``End`` and are not
    treated as open blocks. Openers such as ``Module M <: S.``,
    ``Module M : S.``, and ``Module M (binders).`` are pushed and closed later.
    """
    try:
        raw_lines = src_v.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        raise RuntimeError(f"failed to read source .v file: {src_v}: {e}") from e

    kept = _trim_lines_with_col(raw_lines, theorem_end_line0, theorem_end_col0)
    kept_text = "\n".join(kept).rstrip() + "\nProof. Admitted.\n"

    # Analyze the comment-stripped text to avoid matching Section/End in comments.
    scan_text = strip_coq_comments(kept_text)
    stack: List[Tuple[str, str]] = []  # (kind, name)
    for line in scan_text.splitlines():
        s = line.strip()
        if not s:
            continue
        m_end = _END_NAMED_RE.match(s)
        if m_end:
            name = m_end.group(1)
            # Best-effort pop of the nearest same-name opening.
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][1] == name:
                    stack = stack[:i]
                    break
            continue
        m_sec = _OPEN_SECTION_RE.match(s)
        if m_sec:
            stack.append(("Section", m_sec.group(1)))
            continue
        mod_open = _parse_module_opener(s)
        if mod_open:
            kind_m, name_m, rest_m = mod_open
            if _should_stack_open_module(rest_m):
                stack.append((kind_m, name_m))
            continue

    # Close unclosed blocks in reverse order, just enough for the target to compile.
    if stack:
        kept_text = kept_text.rstrip("\n") + "\n\n"
        for _, name in reversed(stack):
            kept_text += f"End {name}.\n"

    try:
        dst_v.write_text(kept_text, encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"failed to write trimmed .v file: {dst_v}: {e}") from e


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Copy the minimal in-project dependency tree for one Coq .v file to <output-parent>/<project-name>/"
    )
    ap.add_argument(
        "theorem_id",
        type=int,
        nargs="?",
        default=None,
        help="CoqStoq mode: theorem index in the shuffled list; defaults to 1 when project/vfile/--input are omitted",
    )
    ap.add_argument(
        "--coqstoq-path",
        type=Path,
        default=None,
        help="CoqStoq root directory; defaults to COQSTOQ_PATH",
    )
    ap.add_argument(
        "--split",
        type=str,
        default="test",
        help="CoqStoq split: test | validation | cutoff (default: test)",
    )
    ap.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Input path: .v inside CoqStoq, or .json for CoqGym; requires COQSTOQ_PATH / COQGYM_PATH",
    )
    ap.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Manual mode: project root directory; use with --vfile-path to avoid conflict with CoqStoq theorem_id",
    )
    ap.add_argument(
        "--vfile-path",
        type=Path,
        default=None,
        help="Manual mode: absolute path to the target .v file; use with --project-root",
    )
    ap.add_argument(
        "--theorem-end-line0",
        type=int,
        default=None,
        help="Manual mode: trim the copied target to the theorem statement end line (0-based); CoqStoq mode sets this automatically",
    )
    ap.add_argument(
        "--theorem-end-column-raw",
        type=int,
        default=None,
        help="Use with --theorem-end-line0: raw EvalTheorem.theorem_end_pos.column value",
    )
    ap.add_argument(
        "project",
        type=Path,
        nargs="?",
        default=None,
        help="Manual mode: project root directory containing _CoqProject or Makefile",
    )
    ap.add_argument(
        "vfile",
        type=Path,
        nargs="?",
        default=None,
        help="Legacy manual mode: absolute or relative path to the target .v file",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Output parent directory; the copy is written to DIR/<ProjectName>/. "
            f"Default parent: {DEFAULT_OUTPUT_PARENT} (that is, {DEFAULT_OUTPUT_PARENT}/<ProjectName>/)"
        ),
    )
    ap.add_argument(
        "--no-coqdep",
        action="store_true",
        help="Do not use coqdep; parse Require statements only (less precise)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the .v files that would be copied; do not write to disk",
    )
    ap.add_argument(
        "--no-prune-makefiles",
        action="store_true",
        help="Do not prune .v entries in Make/_CoqProject/Makefile and do not remove copied Makefile.coq",
    )
    ap.add_argument(
        "--copy-artifacts",
        action="store_true",
        help="Copy existing build artifacts (.vo/.glob/...). Disabled by default to avoid Coq-version .vo load failures",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="If the output directory exists, clear and overwrite it without prompting (dangerous)",
    )
    ap.add_argument(
        "--no-emit-reference-proof",
        action="store_true",
        help="CoqStoq mode: do not emit the reference proof text to stdout after copying",
    )
    args = ap.parse_args()

    if args.theorem_end_column_raw is not None and args.theorem_end_line0 is None:
        ap.error("--theorem-end-column-raw must be used together with --theorem-end-line0")

    reference_proof_span: Optional[Tuple[int, int, int, int]] = None

    manual = (
        args.input is not None
        or args.project_root is not None
        or args.vfile_path is not None
        or args.project is not None
        or args.vfile is not None
    )
    if manual:
        if args.project_root is not None or args.vfile_path is not None:
            if args.project_root is None or args.vfile_path is None:
                ap.error("manual mode requires both --project-root and --vfile-path")
            project_root = _real(args.project_root)
            vfile = _real(args.vfile_path)
        elif args.input is not None:
            project_root, vfile = parse_input_to_project_and_vfile(args.input)
        else:
            if args.project is None or args.vfile is None:
                ap.error("manual mode requires project and vfile, or --input, or --project-root with --vfile-path")
            project_root = _real(args.project)
            vfile = _real(args.vfile)
    else:
        stoq = args.coqstoq_path or Path(os.environ.get("COQSTOQ_PATH", ""))
        if not str(stoq):
            ap.error("CoqStoq mode requires COQSTOQ_PATH or --coqstoq-path")
        stoq = stoq.resolve()
        if not stoq.is_dir():
            print(f"CoqStoq root directory does not exist: {stoq}", file=sys.stderr)
            return 1
        tid = int(args.theorem_id) if args.theorem_id is not None else 1
        try:
            project_root, vfile, te_l, te_c, ps_l, ps_c, pe_l, pe_c = _resolve_coqstoq_theorem(
                tid, args.split, stoq
            )
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        args.theorem_end_line0 = te_l
        args.theorem_end_column_raw = te_c
        reference_proof_span = (ps_l, ps_c, pe_l, pe_c)

    if not project_root.is_dir():
        print(f"project directory does not exist: {project_root}", file=sys.stderr)
        return 1
    if not vfile.is_file() or vfile.suffix != ".v":
        print(f"not a valid .v file: {vfile}", file=sys.stderr)
        return 1
    if not is_under_root(vfile, project_root):
        print(f"target file is not under the project directory:\n  project: {project_root}\n  file: {vfile}", file=sys.stderr)
        return 1

    parent = DEFAULT_OUTPUT_PARENT if args.output is None else _real(args.output)
    dest = parent / project_root.name

    # If the target directory already exists, prompt before clearing it.
    if dest.exists():
        if not dest.is_dir():
            print(f"output path exists but is not a directory: {dest}", file=sys.stderr)
            return 1
        # Prompt only when the directory is non-empty.
        try:
            non_empty = any(dest.iterdir())
        except OSError:
            non_empty = True
        if non_empty:
            if not args.force:
                print(f"WARNING: output directory exists and is non-empty; all contents will be removed before writing: {dest}")
                ans = input("Confirm clearing and continuing? Type yes to continue; anything else cancels: ").strip().lower()
                if ans != "yes":
                    print("cancelled.", file=sys.stderr)
                    return 1
            # Clear directory contents while preserving the directory itself.
            for entry in list(dest.iterdir()):
                try:
                    if entry.is_dir() and not entry.is_symlink():
                        shutil.rmtree(entry)
                    else:
                        entry.unlink()
                except OSError as e:
                    print(f"failed to clear output entry: {entry}: {e}", file=sys.stderr)
                    return 1

    tmp_coqproject: Optional[Path] = None
    tmp_delete = False
    try:
        tmp_coqproject, tmp_delete = build_merged_coqproject(project_root)
        coqproject_text = tmp_coqproject.read_text(encoding="utf-8", errors="replace")

        vfiles_copy: Set[Path]
        vfiles_compile: Set[Path]
        coqdep_bin = find_coqdep()
        if not args.no_coqdep and coqdep_bin:
            # If the project has no path spec files, generate a fallback -Q
            # mapping for coqdep.
            if not any((project_root / n).is_file() for n in COQ_PATH_SPEC_FILENAMES):
                fb, fb_del = build_fallback_coqdep_projectfile(project_root, vfile)
                # Override the project file used for coqdep only; this affects
                # dependency calculation, not the copied build files.
                if tmp_delete and tmp_coqproject and tmp_coqproject.is_file():
                    try:
                        tmp_coqproject.unlink()
                    except OSError:
                        pass
                tmp_coqproject, tmp_delete = fb, fb_del
            try:
                rel_start = vfile.relative_to(project_root).as_posix()
            except ValueError:
                rel_start = os.path.relpath(vfile, project_root).replace(os.sep, "/")
            vfiles_copy, vfiles_compile = transitive_deps_coqdep(
                project_root, tmp_coqproject, rel_start, coqdep_bin
            )
        else:
            if not args.no_coqdep and not coqdep_bin:
                print("WARNING: coqdep not found; falling back to Require parsing.", file=sys.stderr)
            merged_text = coqproject_text
            if not merged_text.strip():
                print(
                    "ERROR: no -R/-Q entries found in _CoqProject/Makefile; cannot resolve dependencies.",
                    file=sys.stderr,
                )
                return 1
            vfiles_copy = transitive_deps_manual(project_root, merged_text, vfile)
            vfiles_compile = set(vfiles_copy)

        print(f"Project root: {project_root}")
        print(f"Target:       {vfile}")
        print(f"Output:       {dest}")
        print(f"{len(vfiles_copy)} in-project .v files will be copied:")
        for p in sorted(vfiles_copy):
            print(" ", p.relative_to(project_root))

        build_files = list_root_build_files(project_root)
        if build_files:
            print("Root build/metadata files to copy:")
            for p in build_files:
                print(" ", p.name)
        else:
            print("WARNING: no root _CoqProject / Makefile / dune build files found.", file=sys.stderr)

        if args.dry_run:
            if not args.no_prune_makefiles:
                print("(dry-run: actual copy will prune .v entries in Make/_CoqProject and remove Makefile.coq)")
            else:
                print("(dry-run: build-file pruning is disabled)")
        elif not args.no_prune_makefiles:
            print(
                "After writing the copy, .v entries in Make/_CoqProject and similar files will be pruned, and Makefile.coq will be removed so make can regenerate it."
            )
        else:
            print("--no-prune-makefiles was specified; .v lists in build files will not be modified.")

        if args.dry_run:
            if reference_proof_span and not args.no_emit_reference_proof:
                ps_l, ps_c, pe_l, pe_c = reference_proof_span
                emit_reference_proof_to_stdout(vfile, ps_l, ps_c, pe_l, pe_c)
            return 0

        copy_minimal_tree(
            project_root,
            vfiles_copy,
            vfiles_compile,
            dest,
            prune_make_inputs=not args.no_prune_makefiles,
            copy_artifacts=bool(args.copy_artifacts),
        )

        # Theorem-level trimming: only trim the target file; dependencies remain complete.
        if args.theorem_end_line0 is not None:
            rel_v = vfile.relative_to(project_root)
            dst_v = dest / rel_v
            te_l = int(args.theorem_end_line0)
            te_c = int(args.theorem_end_column_raw or 0)
            col = _coqstoq_column_exclusive_end(te_c)
            prune_coq_file_to_theorem(vfile, dst_v, te_l, col)
            print(f"Trimmed target file to theorem_end_pos and replaced the proof with Admitted: {rel_v}")
            ensure_dest_tree_user_writable(dest)

        print("Done.")

        if reference_proof_span and not args.no_emit_reference_proof:
            ps_l, ps_c, pe_l, pe_c = reference_proof_span
            emit_reference_proof_to_stdout(vfile, ps_l, ps_c, pe_l, pe_c)

        return 0
    finally:
        if tmp_delete and tmp_coqproject and tmp_coqproject.is_file():
            try:
                tmp_coqproject.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
