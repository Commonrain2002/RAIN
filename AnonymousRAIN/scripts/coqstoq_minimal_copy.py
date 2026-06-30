#!/usr/bin/env python3
"""
 Coq  CoqStoq 

CoqStoq ( coqstoq  + COQSTOQ_PATH,)::

  python3 coqstoq_minimal_copy.py 1 --split test -o /tmp/out

::

  python3 coqstoq_minimal_copy.py /path/to/project /path/to/project/foo/bar.v -o /tmp/out

 coqdep; Make/_CoqProject  .v (Proof. Admitted.)

CoqStoq  copy  stdout(stderr  ``--- standard-proof ---``)
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
    raise ValueError(f" split: {name!r}(: test, validation, cutoff)")


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
        raise ValueError(f"theorem_id : {theorem_id}( split  {n} )")
    thm = get_theorem(sp, theorem_id, coqstoq_loc)
    root = _coqstoq_workspace_root(coqstoq_loc, thm)
    vfile = (root / thm.path).resolve()
    if not root.is_dir():
        raise ValueError(f": {root}")
    if not vfile.is_file():
        raise ValueError(f" .v : {vfile}")
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


#  -o ;( -o DIR )
DEFAULT_OUTPUT_PARENT = Path(os.environ.get("RAIN_COPY_OUTPUT", ".rain-minimal-copies"))

ARTIFACT_SUFFIXES = (
    ".vo",
    ".vos",
    ".vok",
    ".glob",
    ".aux",
    ".vio",
    ".vioaux",
)

#  coqdep -f / coq_makefile -f ( .coqdeps.d: Makefile , coqdep  Require)
COQ_PATH_SPEC_FILENAMES = ("_CoqProject", "CoqProject", "Make")

# , make / dune / coq_makefile
ROOT_COQ_BUILD_NAMES = (
    "_CoqProject",
    "CoqProject",
    "_CoqProjectName",
    # coq_makefile -f Make(/ Make  _CoqProject)
    "Make",
    "CoqMakefile.in",
    "Makefile",
    "makefile",
    "GNUmakefile",
    # ( CompCert) Makefile  include VERSION
    "VERSION",
    "Makefile.config",
    #  Makefile.coq: coq_makefile  Make/_CoqProject 
    "Makefile.coq.conf",
    "Makefile.coq.local",
    "localMakefile",
    "dune",
    "dune-project",
    "extractedMakefile",
)

#  .v  coq_makefile ( _CoqProject )
PRUNE_COQ_INPUT_NAMES = frozenset(
    {"Make", "_CoqProject", "CoqProject", "CoqMakefile.in"}
)

# Makefile :NAME [:+]= VALUE
_MAKEFILE_ASSIGN_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*[:+]?=\s*)(.*)$")

# coqdep : "targets: prereqs"
_COQDEP_RULE_RE = re.compile(r"^([^:]+):\s*(.*)$")

# Makefile /  -R dir log / -Q dir log(:)
_RQ_FLAGS_RE = re.compile(
    r'(?:^|[\s=])(?P<flag>-[RQ])\s+(?P<dir>"[^"]+"|\'[^\']+\'|\S+)\s+(?P<log>\S+)'
)

# Require ( strip_comments )
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
# : [...]+  \.?, `.` 
# Coq  token( `Load hCoefStructure.` -> `hCoefStructure.`),
#  with_suffix(".v")  `hCoefStructure..v`,Load 
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
    """ (* ... *) , Require """
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
     Load (),:
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
     Load  .v 
    Coq  Load  loadpath ;:
     target , .v
    """
    t = target.strip()
    if not t:
        return None
    # :Coq ( _LOAD_RE )
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
    # 
    if not p.is_absolute():
        p = (current_file.parent / p).resolve()
    else:
        p = p.resolve()
    return p


def parse_rq_flags_from_text(text: str) -> list[Tuple[str, str, str]]:
    """ [('-R', dir, logical), ...],dir """
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
    """ Makefile / Makefile.coq.conf  -R/-Q , _CoqProject """
    chunks: list[str] = []
    names = [
        "Makefile",
        "Makefile.coq",
        "Makefile.coq.conf",
        "localMakefile",
    ]
    for root, _, files in os.walk(project_root):
        #  node_modules 
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
                    # coqdep -f  Make ; _CoqProject 
                    # ( $(shell dirname ...)  Sys_error)
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
     ( coqdep -f , )
     COQ_PATH_SPEC_FILENAMES ( _CoqProject  -R  Make  .v);
     Makefile  -R/-Q
     Makefile 
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
        coqdep  _CoqProject  coq_makefile :
        -  -install / COQDOCFLAGS=... ,coqdep  Unknown option
         coqdep ,:
        -  -I/-R/-Q/-arg ( -xxx , -install)
        -  .v 
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
                # Makefile ( COQDOCFLAGS = ...),coqdep 
                dropped += 1
                continue
            if s.startswith("-install"):
                dropped += 1
                continue
            #  -I/-R/-Q/-arg ( coqdep )
            if s.startswith("-"):
                out.append(line)
                continue
            # : .v
            toks = s.split()
            if toks and all(t.endswith(".v") for t in toks):
                out.append(line)
            else:
                # ( coqdep )
                dropped += 1
        new_text = "\n".join(out).rstrip() + "\n"
        return new_text, dropped

    merged = (base.rstrip() + "\n" + extra).strip() + "\n"
    if not merged.strip():
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_CoqProject", delete=False, encoding="utf-8"
        )
        tmp.write("# empty   _CoqProject / Make  Makefile  -R/-Q\n")
        tmp.close()
        return Path(tmp.name), True

    #  coqdep ( -install / )
    merged, dropped_lines = sanitize_for_coqdep(merged)

    # :coqdep -f  _CoqProject :
    # -  -I/-R/-Q , _CoqProject ;
    # - ( '-'  `src/Foo.v`)
    # :
    # - -I/-R/-Q 
    # -  `xxx.v`  token 
    #  _CoqProject 
    root = _real(project_root)
    new_lines: list[str] = []
    for raw_line in merged.splitlines():
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" in stripped:
            new_lines.append(line)
            continue

        #  '-' : token  -I/-R/-Q,
        # : CompCert  -R 
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
            #  token
            prefix_len = len(line) - len(line.lstrip())
            indent = line[:prefix_len]
            #  token  token,
            rest = stripped[len(first) :].lstrip()
            new_line = indent + str(new_token) + ((" " + rest) if rest else "")
            new_lines.append(new_line)
        else:
            new_lines.append(line)
    merged = "\n".join(new_lines).rstrip() + "\n"

    # /,,
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
    """ .v  .vo/.vio ( .v )"""
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
        raise RuntimeError(f" coqdep: {e}") from e

    # coqdep ( -f )
    #  rel_v  .vo/.vio  ,
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

    # ,(stderr )
    if not matched_any_rule and proc.stderr.strip():
        raise RuntimeError(
            "coqdep , loadpath  coqdep \n"
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
    #  Make/_CoqProject : coqdep ( Load )
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

        #  Load (coqdep )
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
     -R / -Q: (, ,  -R)
     coq_makefile / _CoqProject 
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
    """ .v ( coqdep )"""
    mod = mod.strip()
    if not mod:
        return None

    if from_prefix:
        full = f"{from_prefix}.{mod}"
    else:
        full = mod

    # (Coq  load path )
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

    #  -R/-Q :
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
     coq_makefile (Make / _CoqProject )
     None ;()
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
    # -R/-Q/-arg : .v  Require , .v
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
    : -R/-Q/-I()
     -R/-Q( CompCert  _CoqProject)
     (,  flag )
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
            #  loadpath flags
            continue
        prefix_len = len(line) - len(line.lstrip())
        indent = line[:prefix_len]
        out_lines.append(indent + " ".join(kept_parts) + ending)

    return "".join(out_lines), removed


def collect_v_paths_listed_in_coq_input(text: str, root: Path) -> Set[str]:
    """Make/_CoqProject  .v(,posix)"""
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
    coq_makefile  .v ;,
     *.vo  *.v  kept  .v 
     Make  _CoqProject( .v )
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
     Makefile (# ) .v , .v
    bare_line  \\r\\n
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
    """ `[ -d ... ]` """
    return "'" + s.replace("'", "'\"'\"'") + "'"


def rewrite_makefile_optional_make_c_recipes(text: str) -> Tuple[str, int]:
    """
     ``$(MAKE) -C dir ...`` / ``make -C dir ...``(dir  Makefile )
     ``if [ -d dir ]; then ...; fi``, ``make`` 

    : ``if [ -d`` dir  ``$`` ``-C`` 
     (, )
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
            # :, shell
            out.append(line)
            continue

        qdir = _shell_single_quote_for_cond(dir_arg)
        new_bare = f"{tabs}@if [ -d {qdir} ]; then {body}; fi"
        changed += 1
        out.append(new_bare + ending)

    return "".join(out), changed


def filter_root_makefile_text(text: str, root: Path, kept: Set[str]) -> Tuple[str, int]:
    """ Makefile  .v  (, )"""
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
    """ Coq ()"""
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
     _CoqProject/Make/Makefile ,:
    - _CoqProject: .v( -Q/-R)
    - Makefile: coq_makefile  Makefile.coq  include

     make, coqc/Makefile.coq 
    """
    dre = _real(dest_root)
    dre.mkdir(parents=True, exist_ok=True)

    has_path_spec = any((dre / n).is_file() for n in ("_CoqProject", "CoqProject", "Make"))
    has_makefile = any((dre / n).is_file() for n in ("Makefile", "makefile", "GNUmakefile"))

    def _looks_complex_makefile(text: str) -> bool:
        s = text
        #  Makefile :extractiondepend.dependMakefile.extr 
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

    #  Makefile ( CompCert), Coq Makefile 
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
            print(" Makefile, Coq ( Makefile.orig)")

    if has_path_spec and has_makefile:
        return

    #  _CoqProject()
    if not (dre / "_CoqProject").is_file():
        #  .v ( theories/),,
        #  `Require Import Foo.` ()
        def infer_single_subdir_qflag(vrels: Set[str]) -> Optional[str]:
            comps: Set[str] = set()
            for r in vrels:
                p = Path(r)
                if len(p.parts) >= 2:
                    comps.add(p.parts[0])
                else:
                    comps.add("")  # 
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
        print(" _CoqProject()")

    #  Makefile()
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
        print(" Makefile()")


def prune_dest_build_files(
    dest_root: Path,
    compile_vfiles: Set[Path],
    project_root: Path,
    enabled: bool,
) -> None:
    """
    : Make / _CoqProject  .v ;
     Makefile  .v;
     Makefile.coq, make  coq_makefile 
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
        #  -R/-Q/-I, coqdep/coqc 
        text2, nrm = prune_missing_loadpath_flags(text, dre)
        if nrm > 0:
            text = text2
            print(f" {name}  {nrm}  -R/-Q/-I")
        new_text, dropped = filter_coq_make_input_text(text, dre, kept)
        nadd = 0
        if name in ("Make", "_CoqProject", "CoqProject"):
            new_text, nadd = augment_make_input_with_closure(new_text, dre, kept)
        if dropped > 0 or nadd > 0 or new_text != text:
            p.write_text(new_text, encoding="utf-8")
            if dropped > 0:
                print(f" {name}: {dropped}  .v ")
            if nadd > 0:
                print(
                    f" {name}  {nadd}  .v(;coq_makefile )"
                )

    mconf = dre / "Makefile.coq.conf"
    if mconf.is_file():
        text = mconf.read_text(encoding="utf-8", errors="replace")
        new_text, nch = filter_root_makefile_text(text, dre, kept)
        if new_text != text:
            mconf.write_text(new_text, encoding="utf-8")
            if nch > 0:
                print(f" Makefile.coq.conf: {nch}  .v ")

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
            print(f" {mf}: {nch}  .v ")
        if nwrap > 0:
            print(
                f" {mf}: {nwrap}  ``$(MAKE) -C ...`` ()"
            )

    stale_coq = dre / "Makefile.coq"
    if stale_coq.is_file():
        stale_coq.unlink()
        print(" Makefile.coq( make  Make/_CoqProject )")

    stale_deps = dre / ".coqdeps.d"
    if stale_deps.is_file():
        stale_deps.unlink()
        print(" .coqdeps.d( coqdep , make  .v)")

    # Makefile.coq.local  include ( Makefile.ml-files), make 
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
                # 
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
                print(" Makefile.coq.local( include , make )")
            else:
                local.write_text("".join(kept_lines), encoding="utf-8")
                print(f" Makefile.coq.local  {removed}  include")


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
        # 
        dst_v = dest_root / rel
        dst_v.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v, dst_v)

        # :(, Coq  .vo )
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
    # ,
    ensure_minimal_build_files(
        dest_root, _real(project_root).name, kept_v_rel_posix(project_root, compile_vfiles)
    )
    ensure_dest_tree_user_writable(dest_root)


def ensure_dest_tree_user_writable(dest_root: Path) -> None:
    """
    test-repos  0444;shutil.copy2 , Agent replace 
    ,()
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
            print(f":  chmod {path}: {e}", file=sys.stderr)
            continue
        if path.is_dir():
            os.chmod(path, mode | stat.S_IWUSR | stat.S_IXUSR)
        else:
            os.chmod(path, mode | stat.S_IWUSR)


def find_coqdep() -> Optional[str]:
    return shutil.which("coqdep")


def build_fallback_coqdep_projectfile(project_root: Path, vfile: Path) -> Tuple[Path, bool]:
    """
     _CoqProject/Make , coqdep  -f 
     `Require Import Foo.` , coqdep 
    """
    root = _real(project_root)
    rel = vfile.resolve().relative_to(root.resolve()).as_posix()
    first = Path(rel).parts[0] if len(Path(rel).parts) >= 2 else ""
    lines: list[str] = ["# Auto-generated for coqdep\n"]
    if first and (root / first).is_dir():
        # coqdep  -Q  project file ,
        lines.append(f'-Q {(root / first).resolve()} ""\n')
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_CoqProject", delete=False, encoding="utf-8")
    tmp.write("".join(lines))
    tmp.close()
    return Path(tmp.name), True


def parse_input_to_project_and_vfile(input_path: Path) -> Tuple[Path, Path]:
    """
    ():
    1) CoqStoq: .v 
        input: $COQSTOQ_PATH/test-repos/<project>/.../<file>.v
       : project_root=$COQSTOQ_PATH/test-repos/<project>, vfile=input_path

    2) CoqGym: .json 
        input: $COQGYM_PATH/data/<project>/.../<file>.json
       : project_root=$COQGYM_PATH/coq_projects/<project>
              vfile= input  data -> coq_projects, json -> v
    """
    inp = _real(input_path)
    if not inp.is_file():
        raise RuntimeError(f": {inp}")

    if inp.suffix == ".v":
        stoq_root = os.environ.get("COQSTOQ_PATH")
        if stoq_root:
            base = _real(Path(stoq_root) / "test-repos")
        else:
            #  sudo:sudo , .../test-repos/<project>/...
            parts = inp.parts
            if "test-repos" not in parts:
                raise RuntimeError(
                    " COQSTOQ_PATH, test-repos, .v "
                )
            idx = parts.index("test-repos")
            base = _real(Path(*parts[: idx + 1]))
        try:
            rel = inp.relative_to(base)
        except ValueError as e:
            raise RuntimeError(
                f".v  {base} ,: {inp}"
            ) from e
        if len(rel.parts) < 2:
            raise RuntimeError(f" .v  project : {inp}")
        project_name = rel.parts[0]
        project_root = base / project_name
        vfile = inp
        if not project_root.is_dir():
            raise RuntimeError(f": {project_root}")
        if not vfile.is_file():
            raise RuntimeError(f" v : {vfile}")
        return project_root, vfile

    if inp.suffix == ".json":
        gym_root = os.environ.get("COQGYM_PATH")
        if gym_root:
            data_base = _real(Path(gym_root) / "data")
            projects_base = _real(Path(gym_root) / "coq_projects")
        else:
            #  sudo: .../data/<project>/...
            parts = inp.parts
            if "data" not in parts:
                raise RuntimeError(
                    " COQGYM_PATH, data, .json "
                )
            idx = parts.index("data")
            inferred_root = _real(Path(*parts[:idx]))
            data_base = _real(inferred_root / "data")
            projects_base = _real(inferred_root / "coq_projects")
        try:
            rel = inp.relative_to(data_base)
        except ValueError as e:
            raise RuntimeError(
                f".json  {data_base} ,: {inp}"
            ) from e
        if len(rel.parts) < 2:
            raise RuntimeError(f" .json  project : {inp}")
        project_name = rel.parts[0]
        project_root = projects_base / project_name

        v_rel = Path(*rel.parts[1:]).with_suffix(".v")
        vfile = project_root / v_rel
        if not project_root.is_dir():
            raise RuntimeError(f": {project_root}")
        if not vfile.is_file():
            raise RuntimeError(
                f" .v \n"
                f"  : {inp}\n"
                f"   vfile: {vfile}\n"
                f"   data -> coq_projectsjson -> v "
            )
        return project_root, vfile

    raise RuntimeError(
        f": {inp.suffix}( .v(CoqStoq) .json(CoqGym))"
    )


_OPEN_SECTION_RE = re.compile(r"^\s*Section\s+([A-Za-z_][A-Za-z0-9_']*)\s*\.\s*$")
_MODULE_TYPE_HEAD_RE = re.compile(r"^Module\s+Type\s+([A-Za-z_][A-Za-z0-9_']*)\s*")
_MODULE_HEAD_RE = re.compile(r"^Module\s+(?!Import\b)([A-Za-z_][A-Za-z0-9_']*)\s*")
_END_NAMED_RE = re.compile(r"^\s*End\s+([A-Za-z_][A-Za-z0-9_']*)\s*\.\s*$")


def _coq_fragment_has_top_level_sentence_dot(fragment: str) -> bool:
    """
    ,// 0  `.`
     ``Module M := Expr.``( functor / ,) ``Module M :=``
    ( ``End M``)

     fragment  Coq ( prune )
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
    """ ``s``  ``opener`` , ``closer`` ; ``None``"""
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
    """ ``Module M``  ``(...)`` / ``{...}``  binder """
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
     ``Module Type ...`` / ``Module ...`` ,
    ``(kind, name, rest_after_name)``; ``None``
    ``rest_after_name`` ( binder)
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
     ``Module`` / ``Module Type``  ``End M`` 

    - ``Module M := Expr.`` / ``Module M : S := Expr.`` 
    - ``Module M.`` / ``Module M <: S.`` / ``Module M : S.`` / ``Module M (x:T).`` 
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
    """CoqStoq Position.column :>0  exclusive()"""
    return None if column_raw <= 0 else column_raw + 1


def extract_coq_text_span(
    lines: List[str],
    start_line0: int,
    start_col0: int,
    end_line0: int,
    end_col0_raw: int,
) -> str:
    """ 0-based ( CoqStoq / prune )"""
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
        raise RuntimeError(f" .v : {vfile}: {e}") from e
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
    0-based end_line/end_col;() end_col0  None 
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
     dst_v :(theorem_end_pos,),
     ``Proof. Admitted.`` ; Section/Module
    :``Module M := Expr.`` / ``Module Type M := Expr.``  functor  ``End``,
    
    ``Module M <: S.`` / ``Module M : S.`` / ``Module M (binders).``  ``End M``
    """
    try:
        raw_lines = src_v.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        raise RuntimeError(f" .v : {src_v}: {e}") from e

    kept = _trim_lines_with_col(raw_lines, theorem_end_line0, theorem_end_col0)
    kept_text = "\n".join(kept).rstrip() + "\nProof. Admitted.\n"

    # ( Section/End )
    scan_text = strip_coq_comments(kept_text)
    stack: List[Tuple[str, str]] = []  # (kind, name)
    for line in scan_text.splitlines():
        s = line.strip()
        if not s:
            continue
        m_end = _END_NAMED_RE.match(s)
        if m_end:
            name = m_end.group(1)
            #  opening
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

    # :
    if stack:
        kept_text = kept_text.rstrip("\n") + "\n\n"
        for _, name in reversed(stack):
            kept_text += f"End {name}.\n"

    try:
        dst_v.write_text(kept_text, encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f" .v : {dst_v}: {e}") from e


def main() -> int:
    ap = argparse.ArgumentParser(
        description=" Coq .v () <>/<>/"
    )
    ap.add_argument(
        "theorem_id",
        type=int,
        nargs="?",
        default=None,
        help="(CoqStoq )shuffle ; project/vfile/--input  1",
    )
    ap.add_argument(
        "--coqstoq-path",
        type=Path,
        default=None,
        help="CoqStoq ( COQSTOQ_PATH)",
    )
    ap.add_argument(
        "--split",
        type=str,
        default="test",
        help="CoqStoq :test | validation | cutoff( test)",
    )
    ap.add_argument(
        "--input",
        type=Path,
        default=None,
        help=":CoqStoq  .v;CoqGym  .json( COQSTOQ_PATH / COQGYM_PATH )",
    )
    ap.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="(); --vfile-path , CoqStoq  theorem_id ",
    )
    ap.add_argument(
        "--vfile-path",
        type=Path,
        default=None,
        help="() .v ; --project-root ",
    )
    ap.add_argument(
        "--theorem-end-line0",
        type=int,
        default=None,
        help="()(0-based );CoqStoq  get_theorem ",
    )
    ap.add_argument(
        "--theorem-end-column-raw",
        type=int,
        default=None,
        help=" --theorem-end-line0 :EvalTheorem.theorem_end_pos.column ",
    )
    ap.add_argument(
        "project",
        type=Path,
        nargs="?",
        default=None,
        help="()( _CoqProject  Makefile)",
    )
    ap.add_argument(
        "vfile",
        type=Path,
        nargs="?",
        default=None,
        help="() .v ",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            ": DIR/<ProjectName>/ "
            f"{DEFAULT_OUTPUT_PARENT}( {DEFAULT_OUTPUT_PARENT}/<ProjectName>/)"
        ),
    )
    ap.add_argument(
        "--no-coqdep",
        action="store_true",
        help=" coqdep, Require ()",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help=" .v ,",
    )
    ap.add_argument(
        "--no-prune-makefiles",
        action="store_true",
        help=" Make/_CoqProject/Makefile  .v, Makefile.coq",
    )
    ap.add_argument(
        "--copy-artifacts",
        action="store_true",
        help="(.vo/.glob/...), Coq  .vo ",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help=",,()",
    )
    ap.add_argument(
        "--no-emit-reference-proof",
        action="store_true",
        help="(CoqStoq )copy  stdout ",
    )
    args = ap.parse_args()

    if args.theorem_end_column_raw is not None and args.theorem_end_line0 is None:
        ap.error("--theorem-end-column-raw  --theorem-end-line0 ")

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
                ap.error(" --project-root  --vfile-path")
            project_root = _real(args.project_root)
            vfile = _real(args.vfile_path)
        elif args.input is not None:
            project_root, vfile = parse_input_to_project_and_vfile(args.input)
        else:
            if args.project is None or args.vfile is None:
                ap.error(" project  vfile, --input / --project-root --vfile-path")
            project_root = _real(args.project)
            vfile = _real(args.vfile)
    else:
        stoq = args.coqstoq_path or Path(os.environ.get("COQSTOQ_PATH", ""))
        if not str(stoq):
            ap.error("CoqStoq  COQSTOQ_PATH  --coqstoq-path")
        stoq = stoq.resolve()
        if not stoq.is_dir():
            print(f"CoqStoq : {stoq}", file=sys.stderr)
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
        print(f": {project_root}", file=sys.stderr)
        return 1
    if not vfile.is_file() or vfile.suffix != ".v":
        print(f" .v : {vfile}", file=sys.stderr)
        return 1
    if not is_under_root(vfile, project_root):
        print(f":\n  : {project_root}\n  : {vfile}", file=sys.stderr)
        return 1

    parent = DEFAULT_OUTPUT_PARENT if args.output is None else _real(args.output)
    dest = parent / project_root.name

    # :
    if dest.exists():
        if not dest.is_dir():
            print(f": {dest}", file=sys.stderr)
            return 1
        # 
        try:
            non_empty = any(dest.iterdir())
        except OSError:
            non_empty = True
        if non_empty:
            if not args.force:
                print(f": ,:{dest}")
                ans = input("? yes ,: ").strip().lower()
                if ans != "yes":
                    print("", file=sys.stderr)
                    return 1
            # ()
            for entry in list(dest.iterdir()):
                try:
                    if entry.is_dir() and not entry.is_symlink():
                        shutil.rmtree(entry)
                    else:
                        entry.unlink()
                except OSError as e:
                    print(f": {entry}: {e}", file=sys.stderr)
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
            # (_CoqProject/CoqProject/Make), coqdep  -Q 
            if not any((project_root / n).is_file() for n in COQ_PATH_SPEC_FILENAMES):
                fb, fb_del = build_fallback_coqdep_projectfile(project_root, vfile)
                #  coqdep  project file(,)
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
                print(":  coqdep, Require ", file=sys.stderr)
            merged_text = coqproject_text
            if not merged_text.strip():
                print(
                    ":  _CoqProject/Makefile  -R/-Q,",
                    file=sys.stderr,
                )
                return 1
            vfiles_copy = transitive_deps_manual(project_root, merged_text, vfile)
            vfiles_compile = set(vfiles_copy)

        print(f": {project_root}")
        print(f":   {vfile}")
        print(f":   {dest}")
        print(f" {len(vfiles_copy)}  .v ():")
        for p in sorted(vfiles_copy):
            print(" ", p.relative_to(project_root))

        build_files = list_root_build_files(project_root)
        if build_files:
            print("/():")
            for p in build_files:
                print(" ", p.name)
        else:
            print(":  _CoqProject / Makefile / dune ", file=sys.stderr)

        if args.dry_run:
            if not args.no_prune_makefiles:
                print("(dry-run: Make/_CoqProject  .v  Makefile.coq)")
            else:
                print("(dry-run:)")
        elif not args.no_prune_makefiles:
            print(
                " Make / _CoqProject  .v , Makefile.coq  make "
            )
        else:
            print(" --no-prune-makefiles: .v ")

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

        # :()
        if args.theorem_end_line0 is not None:
            rel_v = vfile.relative_to(project_root)
            dst_v = dest / rel_v
            te_l = int(args.theorem_end_line0)
            te_c = int(args.theorem_end_column_raw or 0)
            col = _coqstoq_column_exclusive_end(te_c)
            prune_coq_file_to_theorem(vfile, dst_v, te_l, col)
            print(f"( theorem_end_pos, Admitted):{rel_v}")
            ensure_dest_tree_user_writable(dest)

        print("")

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
