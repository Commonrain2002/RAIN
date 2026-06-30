#!/usr/bin/env python3
"""Gate: minimal_copy + make on PnVRocqLib Cobble samples before full batch runs."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_EVAL_COBBLE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_COBBLE_DIR.parents[1]
_EVAL_DIR = _REPO_ROOT / "Evaluation"
if str(_EVAL_COBBLE_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_COBBLE_DIR))
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from BatchTest.coq_strip_comments import strip_coq_comments
from BatchTest.theorem_integrity import collapse_whitespace_for_compare, theorem_proposition_preserved
from cobble_meta import build_meta_payload

_DEFAULT_PROJECT = Path(os.environ.get("COBBLE_PROJECT_ROOT", "."))
_DEFAULT_TESTLIST = _EVAL_COBBLE_DIR / "TestList"
_DEFAULT_PARSE = _REPO_ROOT / "Sentence" / "vsrocq_split_sentences_PnV"
_COPY_SCRIPT = _EVAL_COBBLE_DIR / "cobble_minimal_copy.py"


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
    no_comments = strip_coq_comments(text)
    coll_prop = collapse_whitespace_for_compare(proposition_text)
    coll_file = collapse_whitespace_for_compare(no_comments)
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


def verify_one_id(
    line_id: int,
    *,
    project_root: Path,
    testlist: Path,
    parse_sentence_script: str,
    copy_parent: Path,
    make_timeout_seconds: int,
) -> tuple[bool, str]:
    try:
        meta = build_meta_payload(
            line_id=line_id,
            project_root=project_root,
            testlist=testlist,
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

    copy_cmd = [
        "python3",
        str(_COPY_SCRIPT.resolve()),
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

    make_rc, make_out, make_err = _run(
        ["timeout", str(make_timeout_seconds), "make", "-j1"],
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
        description="Verify cobble_minimal_copy + make for Cobble TestList ids (gate before batch)."
    )
    ap.add_argument("--ids", type=int, nargs="+", default=[2, 3, 10, 96])
    ap.add_argument("--project-root", type=Path, default=_DEFAULT_PROJECT)
    ap.add_argument("--testlist", type=Path, default=_DEFAULT_TESTLIST)
    ap.add_argument("--parse-sentence-script", type=str, default=str(_DEFAULT_PARSE))
    ap.add_argument("--output-parent", type=Path, default=None, help="Parent for copy -o (default: temp dir)")
    ap.add_argument("--make-timeout-seconds", type=int, default=300)
    args = ap.parse_args()

    out_parent = args.output_parent
    temp_ctx = None
    if out_parent is None:
        temp_ctx = tempfile.TemporaryDirectory(prefix="cobble_verify_copy_")
        out_parent = Path(temp_ctx.name)

    failed = 0
    for line_id in args.ids:
        id_parent = (out_parent / f"id_{line_id}").resolve()
        id_parent.mkdir(parents=True, exist_ok=True)
        ok, message = verify_one_id(
            line_id,
            project_root=args.project_root.resolve(),
            testlist=args.testlist.resolve(),
            parse_sentence_script=str(args.parse_sentence_script),
            copy_parent=id_parent,
            make_timeout_seconds=int(args.make_timeout_seconds),
        )
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] id={line_id} | {message}")
        if not ok:
            failed += 1

    if temp_ctx is not None:
        temp_ctx.cleanup()

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
