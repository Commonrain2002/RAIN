#!/usr/bin/env python3
"""Smoke-test `dune build <target>.vo` vs full theory build on a Parcas catalog id."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
if str(_EVAL_PARCAS_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_PARCAS_DIR))

from parcas_batch_env import build_check_shell, build_shell_make, target_v_rel_to_dune_vo
from parcas_meta import build_meta_payload
from parcas_testlist import DEFAULT_CATALOG_PATH, resolve_parcas_path


def _run_shell(
    shell_line: str,
    cwd: Path,
    timeout_seconds: int,
) -> tuple[int, str, str, float, bool]:
    cmd = ["timeout", str(timeout_seconds), "/bin/sh", "-c", shell_line]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 15,
            check=False,
        )
        elapsed = time.monotonic() - t0
        return proc.returncode, proc.stdout, proc.stderr, elapsed, False
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - t0
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = exc.stderr if isinstance(exc.stderr, str) else ""
        return 124, out, err, elapsed, True


def _count_coqc(combined: str) -> int:
    return len(re.findall(r"\bcoqc\b", combined))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog-id", type=int, default=239)
    ap.add_argument("--parcas-path", type=Path, default=None)
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    ap.add_argument("--opam-switch", type=str, default=None)
    ap.add_argument("--timeout-seconds", type=int, default=300)
    ap.add_argument(
        "--parse-sentence-script",
        type=str,
        default=str(_REPO_ROOT / "Sentence" / "vsrocq_split_sentences_Parcas"),
    )
    args = ap.parse_args()

    project_root = resolve_parcas_path(args.parcas_path)
    meta = build_meta_payload(
        catalog_id=int(args.catalog_id),
        project_root=project_root,
        catalog_path=args.catalog.resolve(),
        parse_sentence_script=args.parse_sentence_script,
        parse_sentence_timeout_seconds=120,
    )
    v_rel = str(meta["v_rel_path"])
    vo_rel = target_v_rel_to_dune_vo(v_rel)
    switch = args.opam_switch

    target_shell = build_check_shell(switch, v_rel, full_theory=False)
    full_shell = build_check_shell(switch, v_rel, full_theory=True)

    print(f"catalog id={args.catalog_id} v_rel={v_rel} vo={vo_rel}")
    print(f"target shell: {target_shell}")
    print(f"full shell:   {full_shell}")
    print(f"cwd: {project_root}")
    print()

    rc, out, err, elapsed, to = _run_shell(target_shell, project_root, int(args.timeout_seconds))
    combined = out + err
    print(f"=== target dune build | rc={rc} timed_out={int(to)} elapsed={elapsed:.2f}s coqc={_count_coqc(combined)} ===")
    if rc != 0:
        print(combined[-2000:])
        return 1

    rc2, out2, err2, elapsed2, to2 = _run_shell(full_shell, project_root, int(args.timeout_seconds))
    combined2 = out2 + err2
    print(
        f"=== full theory warm | rc={rc2} timed_out={int(to2)} elapsed={elapsed2:.2f}s coqc={_count_coqc(combined2)} ==="
    )

    # Incremental: tweak target .v and rebuild target only
    v_path = project_root / v_rel
    text = v_path.read_text(encoding="utf-8")
    marker = "(* verify_dune_target_check *)"
    if marker not in text:
        v_path.write_text(text.rstrip() + f"\n\n{marker}\n", encoding="utf-8")
    rc3, out3, err3, elapsed3, to3 = _run_shell(target_shell, project_root, int(args.timeout_seconds))
    combined3 = out3 + err3
    print(
        f"=== target incremental after .v touch | rc={rc3} timed_out={int(to3)} "
        f"elapsed={elapsed3:.2f}s coqc={_count_coqc(combined3)} ==="
    )
    if rc3 != 0:
        print((combined3)[-2000:])
        return 1

    print("OK: target vo build succeeded (cold/warm).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
