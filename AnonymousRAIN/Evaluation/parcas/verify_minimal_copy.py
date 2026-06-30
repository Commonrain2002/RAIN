#!/usr/bin/env python3
"""Gate: minimal_copy + make on Parcas catalog samples before full batch runs."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
_EVAL_DIR = _REPO_ROOT / "Evaluation"
if str(_EVAL_PARCAS_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_PARCAS_DIR))
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))


from BatchTest.theorem_integrity import (
    collapse_whitespace_for_compare,
    normalize_theorem_text_for_compare,
    theorem_proposition_preserved,
)
from parcas_meta import build_meta_payload
from parcas_batch_env import resolve_parcas_opam_switch
from parcas_eval_build_files import parcas_eval_build_shell_command
from parcas_testlist import DEFAULT_CATALOG_PATH, resolve_parcas_path

_DEFAULT_PARSE = _REPO_ROOT / "Sentence" / "vsrocq_split_sentences_Parcas"
_STOQ_COPY_SCRIPT = _REPO_ROOT / "scripts" / "coqstoq_minimal_copy.py"
_PARCAS_COPY_SCRIPT = _EVAL_PARCAS_DIR / "parcas_minimal_copy.py"


def _run(cmd: list[str], *, cwd: Path | None, timeout_seconds: int) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _check_pruned_target_file(
    target_v: Path,
    proposition_text: str,
) -> str | None:
    if not target_v.is_file():
        return f"target file missing: {target_v}"
    text = target_v.read_text(encoding="utf-8", errors="replace")
    if not theorem_proposition_preserved(text, proposition_text):
        return "theorem proposition not preserved after copy prune"
    coll_prop = normalize_theorem_text_for_compare(proposition_text)
    coll_file = normalize_theorem_text_for_compare(text)
    pos = coll_file.find(coll_prop)
    if pos < 0:
        return "collapsed proposition not found in target file"
    after = coll_file[pos + len(coll_prop) :].lstrip()
    if not after.startswith("Proof. Admitted."):
        if not re.match(r"Proof\.\s*Admitted\.", after):
            return f"expected Proof. Admitted. after proposition, got: {after[:80]!r}"
    before_admitted = after.split("Proof. Admitted.", 1)[0]
    if re.search(r"\bQed\.", before_admitted):
        return "Qed found between proposition and Proof. Admitted."
    return None


def _resolve_copy_script(use_parcas_copy: bool) -> Path:
    if use_parcas_copy:
        return _PARCAS_COPY_SCRIPT.resolve()
    return _STOQ_COPY_SCRIPT.resolve()


def verify_one_id(
    catalog_id: int,
    *,
    project_root: Path,
    catalog_path: Path,
    parse_sentence_script: str,
    copy_parent: Path,
    make_timeout_seconds: int,
    use_parcas_copy: bool,
    opam_switch: str,
) -> tuple[bool, str]:
    try:
        meta = build_meta_payload(
            catalog_id=catalog_id,
            project_root=project_root,
            catalog_path=catalog_path,
            parse_sentence_script=parse_sentence_script,
            parse_sentence_timeout_seconds=120,
        )
    except (ValueError, RuntimeError) as e:
        return False, f"meta failed: {e}"

    workspace_root = Path(str(meta["workspace_root"])).resolve()
    v_rel = str(meta["v_rel_path"])
    vfile_abs = (workspace_root / v_rel).resolve()
    project_name = str(meta["project"])
    proposition_text = str(meta.get("theorem_proposition_text") or "")

    copy_script = _resolve_copy_script(use_parcas_copy)
    copy_cmd = [
        "python3",
        str(copy_script),
        "--project-root",
        str(workspace_root),
        "--vfile-path",
        str(vfile_abs),
        "-o",
        str(copy_parent),
        "--force",
        "--theorem-end-line0",
        str(int(meta["theorem_end_line0"])),
        "--theorem-end-column-raw",
        str(int(meta.get("theorem_end_column_raw") or 0)),
    ]
    if use_parcas_copy:
        copy_cmd.extend(["--opam-switch", opam_switch])
    copy_rc, copy_out, copy_err = _run(copy_cmd, cwd=_REPO_ROOT, timeout_seconds=600)
    if copy_rc != 0:
        return False, f"copy failed rc={copy_rc}\nstdout:\n{copy_out[-2000:]}\nstderr:\n{copy_err[-2000:]}"

    repo_dir = (copy_parent / project_name).resolve()
    if not repo_dir.is_dir():
        return False, f"copy output missing repo dir: {repo_dir}"

    target_v = (repo_dir / v_rel).resolve()
    content_err = _check_pruned_target_file(target_v, proposition_text)
    if content_err:
        preview = target_v.read_text(encoding="utf-8", errors="replace")[-800:] if target_v.is_file() else ""
        return False, f"{content_err}\n--- tail of target .v ---\n{preview}"

    build_shell = parcas_eval_build_shell_command(repo_dir)
    make_rc, make_out, make_err = _run(
        ["timeout", str(make_timeout_seconds), "/bin/sh", "-c", build_shell],
        cwd=repo_dir,
        timeout_seconds=make_timeout_seconds + 15,
    )
    if make_rc != 0:
        return False, (
            f"make failed rc={make_rc}\nstdout:\n{make_out[-3000:]}\nstderr:\n{make_err[-3000:]}"
        )

    collapsed = collapse_whitespace_for_compare(proposition_text)[:80]
    return True, f"ok | project={project_name} | v={v_rel} | prop_prefix={collapsed!r}..."


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify minimal_copy + make for Parcas catalog ids (gate before batch)."
    )
    ap.add_argument("--ids", type=int, nargs="+", default=[11, 250, 400])
    ap.add_argument("--parcas-path", type=Path, default=None)
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    ap.add_argument("--parse-sentence-script", type=str, default=str(_DEFAULT_PARSE))
    ap.add_argument("--output-parent", type=Path, default=None)
    ap.add_argument("--make-timeout-seconds", type=int, default=600)
    ap.add_argument(
        "--opam-switch",
        type=str,
        default=None,
        help="Opam switch for make/dune (default: PARCAS_OPAM_SWITCH or parcas).",
    )
    ap.add_argument(
        "--use-coqstoq-copy",
        action="store_true",
        help="Use scripts/coqstoq_minimal_copy.py (legacy; default is parcas_minimal_copy.py).",
    )
    args = ap.parse_args()

    try:
        project_root = resolve_parcas_path(args.parcas_path)
        opam_switch = resolve_parcas_opam_switch(args.opam_switch)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    out_parent = args.output_parent
    temp_ctx = None
    if out_parent is None:
        temp_ctx = tempfile.TemporaryDirectory(prefix="parcas_verify_copy_")
        out_parent = Path(temp_ctx.name)

    failed = 0
    for catalog_id in args.ids:
        id_parent = (out_parent / f"id_{catalog_id}").resolve()
        id_parent.mkdir(parents=True, exist_ok=True)
        ok, message = verify_one_id(
            catalog_id,
            project_root=project_root,
            catalog_path=args.catalog.resolve(),
            parse_sentence_script=str(args.parse_sentence_script),
            copy_parent=id_parent,
            make_timeout_seconds=int(args.make_timeout_seconds),
            use_parcas_copy=not bool(args.use_coqstoq_copy),
            opam_switch=opam_switch,
        )
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] id={catalog_id} | {message}")
        if not ok:
            failed += 1

    if temp_ctx is not None:
        temp_ctx.cleanup()

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
