#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_DIR.parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from batch_utils import (  # noqa: E402
    batch_log,
    build_rq_options_string,
    detect_palm_runtime_error,
    ensure_hammer_import_first_line,
    make_batch_workspace_stamp,
    merge_opam_palm_env,
    parse_last_json_line,
    parse_palm_proof,
    parse_token_usage_from_stdout,
    read_ids_from_testlist,
    replace_admitted_in_vfile,
    resolve_coqstoq_theorem_name,
    run_capture,
    setup_trial_palm_workspace,
    trim_extract_json_to_theorem,
    trial_workspace_parent,
    update_local_path_json,
    write_json,
    write_text,
)

AGENT_WORKSPACE_PALM = Path(
    os.environ.get(
        "PALM_BATCH_WORKSPACE",
        str(_REPO_ROOT / "workspace" / "AgentTest_PALM"),
    )
)
DEFAULT_TESTLIST = _EVAL_DIR / "TestList.txt"


@dataclass(frozen=True)
class BatchConfig:
    repo_root: Path
    eval_dir: Path
    coqstoq_path: Path | None
    workspace_agent_root: Path
    workspace_batch_dir: Path
    result_dir: Path
    split: str
    make_timeout_seconds: int
    palm_run_timeout_seconds: int
    repeats: int
    python_executable: str
    coqstoq_python_executable: str
    llm_max_tokens: int


def _default_coqstoq_python() -> str:
    override = os.environ.get("COQSTOQ_PYTHON", "").strip()
    if override:
        return override
    return sys.executable


def _derive_outcome(r: dict[str, Any]) -> None:
    if int(r.get("success", 0) or 0) == 1:
        r["outcome"] = "success"
        r["outcome_detail"] = ""
        return
    if r.get("outcome"):
        return
    sr = r.get("skip_reason")
    if sr == "post_copy_make_failed":
        r["outcome"] = "post_copy_make_failed"
        r["outcome_detail"] = f"rc={r.get('post_copy_make_rc')}"
        return
    if sr == "copy_failed":
        r["outcome"] = "copy_failed"
        r["outcome_detail"] = f"rc={r.get('copy_rc')}"
        return
    if sr == "hammer_import_failed":
        r["outcome"] = "hammer_import_failed"
        r["outcome_detail"] = str(r.get("hammer_import_error") or "")[:400]
        return
    if sr == "path_json_failed":
        r["outcome"] = "path_json_failed"
        r["outcome_detail"] = str(r.get("path_json_error") or "")
        return
    if sr == "extract_failed":
        r["outcome"] = "extract_failed"
        return
    if sr == "verify_make_failed":
        r["outcome"] = "verify_make_failed"
        r["outcome_detail"] = f"rc={r.get('verify_make_rc')}"
        return
    if sr == "no_proof_parsed":
        r["outcome"] = "no_proof_parsed"
        return
    if sr == "runtime_error":
        r["outcome"] = "runtime_error"
        r["outcome_detail"] = str(r.get("palm_runtime_error") or "")[:800]
        return
    if sr == "patch_failed":
        r["outcome"] = "patch_failed"
        r["outcome_detail"] = str(r.get("patch_error") or "")
        return
    if int(r.get("palm_run_timed_out", 0) or 0) == 1:
        r["outcome"] = "palm_timeout"
        return
    if int(r.get("verify_make_timed_out", 0) or 0) == 1:
        r["outcome"] = "verify_make_timeout"
        return
    vm = r.get("verify_make_rc")
    try:
        vm_int = int(vm) if vm is not None else -1
    except (TypeError, ValueError):
        vm_int = -1
    if vm_int not in (-1, 0):
        r["outcome"] = "verify_make_failed"
        r["outcome_detail"] = f"rc={vm_int}"
        return
    r["outcome"] = "unknown_failure"
    r["outcome_detail"] = str(sr or "")


def _run_one_trial(
    id_value: int,
    trial_index: int,
    repeat_total: int,
    cfg: BatchConfig,
    meta: dict[str, Any],
    project_name: str,
    copy_parent: Path,
    trial_artifacts_dir: Path,
    parent_tag: str,
) -> dict[str, Any]:
    t0 = time.monotonic()
    tag = f"{parent_tag} trial={trial_index}/{repeat_total}"
    trial_artifacts_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = (copy_parent / project_name).resolve()
    v_rel_path = str(meta.get("v_rel_path") or "").strip()

    copy_script = (cfg.eval_dir / "coqstoq_minimal_copy.py").resolve()
    copy_cmd = [
        cfg.coqstoq_python_executable,
        str(copy_script),
        str(id_value),
        "--split",
        cfg.split,
        "-o",
        str(copy_parent),
        "--force",
    ]
    if cfg.coqstoq_path is not None:
        copy_cmd += ["--coqstoq-path", str(cfg.coqstoq_path)]
    copy_rc, copy_out, copy_err, copy_timed_out = run_capture(
        copy_cmd, cwd=cfg.repo_root, env=None, timeout_seconds=600
    )
    write_text(trial_artifacts_dir / "copy_stdout.log", copy_out)
    write_text(trial_artifacts_dir / "copy_stderr.log", copy_err)
    batch_log(tag, f"copy done | rc={copy_rc} | timed_out={int(copy_timed_out)}")

    skip_reason: str | None = None
    post_copy_make_rc: int | None = None
    post_copy_make_timed_out = False
    extract_rc = -1
    palm_rc = -1
    palm_out = ""
    palm_err = ""
    palm_timed_out = False
    verify_make_rc = -1
    verify_make_timed_out = False
    parsed_proof: str | None = None
    path_json_error: str | None = None
    patch_error: str | None = None
    hammer_import_error: str | None = None
    palm_runtime_error: str | None = None
    theorem_name = str(meta.get("theorem_name") or "").strip()

    if copy_rc != 0 or copy_timed_out:
        skip_reason = "copy_failed"
    elif not repo_dir.is_dir():
        skip_reason = "copy_failed"
    elif not v_rel_path:
        skip_reason = "copy_failed"
    else:
        target_v = repo_dir / v_rel_path
        if not target_v.is_file():
            skip_reason = "hammer_import_failed"
            hammer_import_error = f"target file not found: {v_rel_path}"
            batch_log(tag, hammer_import_error)
        else:
            try:
                ensure_hammer_import_first_line(target_v)
                batch_log(tag, f"hammer import ok | {v_rel_path}")
            except (OSError, RuntimeError) as e:
                skip_reason = "hammer_import_failed"
                hammer_import_error = str(e)
                batch_log(tag, f"hammer import failed, skip trial | {e}")

    if skip_reason is None:
        post_copy_make_rc, mk_out, mk_err, post_copy_make_timed_out = run_capture(
            ["timeout", str(cfg.make_timeout_seconds), "make", "-j1"],
            cwd=repo_dir,
            env=None,
            timeout_seconds=cfg.make_timeout_seconds + 10,
        )
        write_text(trial_artifacts_dir / "post_copy_make_stdout.log", mk_out)
        write_text(trial_artifacts_dir / "post_copy_make_stderr.log", mk_err)
        batch_log(
            tag,
            f"post-copy make | rc={post_copy_make_rc} | timed_out={int(post_copy_make_timed_out)}",
        )
        if post_copy_make_timed_out or post_copy_make_rc != 0:
            skip_reason = "post_copy_make_failed"

    if skip_reason is None:
        try:
            rq_string = build_rq_options_string(repo_dir)
            write_text(trial_artifacts_dir / "path_options.txt", rq_string + "\n")
        except ValueError as e:
            skip_reason = "path_json_failed"
            path_json_error = str(e)
            batch_log(tag, f"path options failed | {e}")

    if skip_reason is None:
        palm_env = merge_opam_palm_env()
        palm_env["PALM_PROJECTS_PATH"] = str(copy_parent.resolve())
        trial_data_dir, trial_eval_dir = setup_trial_palm_workspace(
            cfg.repo_root, trial_artifacts_dir
        )
        update_local_path_json(trial_data_dir / "path.json", project_name, rq_string)
        palm_env["PALM_DATA_PATH"] = str(trial_data_dir)
        palm_env["PALM_EVAL_PATH"] = str(trial_eval_dir)
        if cfg.coqstoq_path is not None:
            palm_env["COQSTOQ_PATH"] = str(cfg.coqstoq_path)

        extract_cmd = [
            cfg.python_executable,
            "-m",
            "src.extract_data",
            f"--proj={project_name}",
            f"--file={v_rel_path}",
        ]
        extract_rc, ex_out, ex_err, ex_to = run_capture(
            extract_cmd,
            cwd=cfg.repo_root,
            env=palm_env,
            timeout_seconds=600,
        )
        write_text(trial_artifacts_dir / "extract_stdout.log", ex_out)
        write_text(trial_artifacts_dir / "extract_stderr.log", ex_err)
        batch_log(tag, f"extract | rc={extract_rc} | timed_out={int(ex_to)}")
        if extract_rc != 0 or ex_to:
            skip_reason = "extract_failed"
        else:
            try:
                theorem = resolve_coqstoq_theorem_name(
                    meta, trial_data_dir, project_name, v_rel_path
                )
                if not theorem:
                    raise ValueError("missing theorem_name in CoqStoq meta and no Admitted fallback")
                trim_extract_json_to_theorem(
                    trial_data_dir, project_name, v_rel_path, theorem
                )
                write_text(trial_artifacts_dir / "coqstoq_theorem.txt", theorem + "\n")
            except ValueError as e:
                skip_reason = "extract_failed"
                write_text(
                    trial_artifacts_dir / "extract_stderr.log",
                    ex_err + f"\nresolve/trim theorem: {e}\n",
                )
                batch_log(tag, f"theorem resolve failed | {e}")
                theorem = ""
            else:
                main_cmd = [
                    cfg.python_executable,
                    "-m",
                    "src.main",
                    f"--proj={project_name}",
                    f"--file={v_rel_path}",
                    f"--theorem={theorem}",
                    "--exp_name",
                    f"batch_{cfg.workspace_batch_dir.name}",
                    "-backtrack",
                    f"--max-tokens={cfg.llm_max_tokens}",
                ]
                palm_rc, palm_out, palm_err, palm_timed_out = run_capture(
                    ["timeout", str(cfg.palm_run_timeout_seconds), *main_cmd],
                    cwd=cfg.repo_root,
                    env=palm_env,
                    timeout_seconds=cfg.palm_run_timeout_seconds + 30,
                )
                write_text(trial_artifacts_dir / "palm_stdout.log", palm_out)
                write_text(trial_artifacts_dir / "palm_stderr.log", palm_err)
                batch_log(
                    tag,
                    f"PALM | rc={palm_rc} | timed_out={int(palm_timed_out)} | theorem={theorem}",
                )

    if skip_reason is None:
        combined = palm_out + "\n" + palm_err
        runtime_detail = detect_palm_runtime_error(combined)
        if runtime_detail is not None:
            skip_reason = "runtime_error"
            palm_runtime_error = runtime_detail
            batch_log(tag, f"PALM runtime_error | {runtime_detail[:200]}")
        else:
            parsed_proof = parse_palm_proof(combined)
            if not parsed_proof:
                skip_reason = "no_proof_parsed"
                batch_log(tag, "no proof block in PALM output")
            else:
                target_v = repo_dir / v_rel_path
                try:
                    replace_admitted_in_vfile(target_v, parsed_proof)
                    write_text(trial_artifacts_dir / "patched_proof.v.snippet", parsed_proof + "\n")
                except ValueError as e:
                    skip_reason = "patch_failed"
                    patch_error = str(e)
                    batch_log(tag, f"patch failed | {e}")

    if skip_reason is None:
        verify_make_rc, vm_out, vm_err, verify_make_timed_out = run_capture(
            ["timeout", str(cfg.make_timeout_seconds), "make", "-j1"],
            cwd=repo_dir,
            env=None,
            timeout_seconds=cfg.make_timeout_seconds + 10,
        )
        write_text(trial_artifacts_dir / "verify_make_stdout.log", vm_out)
        write_text(trial_artifacts_dir / "verify_make_stderr.log", vm_err)
        batch_log(
            tag,
            f"verify make | rc={verify_make_rc} | timed_out={int(verify_make_timed_out)}",
        )
        if verify_make_timed_out or verify_make_rc != 0:
            skip_reason = "verify_make_failed"

    elapsed = int(time.monotonic() - t0)
    success = 1 if skip_reason is None else 0
    token_fields = parse_token_usage_from_stdout(palm_out)
    trial_result: dict[str, Any] = {
        "id": id_value,
        "trial": trial_index,
        "repeats": repeat_total,
        "project": project_name,
        "target_coq_file": v_rel_path,
        "theorem_name": theorem_name or None,
        "steps": meta.get("step_count"),
        "success": success,
        "elapsed_seconds": elapsed,
        "repo_dir": str(repo_dir),
        "artifacts_dir": str(trial_artifacts_dir),
        "copy_rc": copy_rc,
        "copy_timed_out": int(copy_timed_out),
        "skip_reason": skip_reason,
        "post_copy_make_rc": post_copy_make_rc,
        "post_copy_make_timed_out": int(post_copy_make_timed_out),
        "extract_rc": extract_rc,
        "palm_rc": palm_rc,
        "palm_run_timed_out": int(palm_timed_out),
        "verify_make_rc": verify_make_rc,
        "verify_make_timed_out": int(verify_make_timed_out),
        "path_json_error": path_json_error,
        "hammer_import_error": hammer_import_error,
        "patch_error": patch_error,
        "palm_runtime_error": palm_runtime_error,
        "had_parsed_proof": 1 if parsed_proof else 0,
        "llm_max_tokens": cfg.llm_max_tokens,
        **token_fields,
    }
    _derive_outcome(trial_result)
    write_json(trial_artifacts_dir / "result.json", trial_result)
    tok = token_fields.get("tokens_total")
    tok_s = f" tokens_total={tok}" if tok is not None else " tokens=(unparsed)"
    batch_log(
        tag,
        f"trial end | success={success} | outcome={trial_result.get('outcome')} | {elapsed}s{tok_s}",
    )
    return trial_result


def _aggregate_trial_stats(trials: list[dict[str, Any]]) -> dict[str, Any]:
    success_count = sum(1 for t in trials if int(t.get("success", 0) or 0) == 1)
    n = len(trials)
    elapsed = [int(t.get("elapsed_seconds", 0) or 0) for t in trials]
    totals = [t.get("tokens_total") for t in trials if t.get("tokens_total") is not None]
    return {
        "trial_count": n,
        "success_count": success_count,
        "success_rate": (success_count / n) if n else 0.0,
        "elapsed_seconds_sum": sum(elapsed),
        "elapsed_seconds_min": min(elapsed) if elapsed else None,
        "elapsed_seconds_max": max(elapsed) if elapsed else None,
        "tokens_total_sum": sum(int(x) for x in totals) if totals else None,
        "tokens_total_min": min(int(x) for x in totals) if totals else None,
        "tokens_total_max": max(int(x) for x in totals) if totals else None,
    }


def _run_one(id_value: int, cfg: BatchConfig) -> dict[str, Any]:
    t0 = time.monotonic()
    tag = f"[id={id_value}]"
    artifacts_dir = (cfg.result_dir / f"id_{id_value}").resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    meta_script = (cfg.eval_dir / "coqstoq_meta.py").resolve()
    meta_cmd = [
        cfg.coqstoq_python_executable,
        str(meta_script),
        "--id",
        str(id_value),
        "--split",
        cfg.split,
    ]
    if cfg.coqstoq_path is not None:
        meta_cmd += ["--coqstoq-path", str(cfg.coqstoq_path)]
    meta_rc, meta_out, meta_err, meta_timed_out = run_capture(
        meta_cmd, cwd=cfg.repo_root, env=None, timeout_seconds=120
    )
    write_text(artifacts_dir / "meta_stdout.log", meta_out)
    write_text(artifacts_dir / "meta_stderr.log", meta_err)

    meta: dict[str, Any] | None = None
    meta_error: str | None = None
    if meta_rc == 0 and not meta_timed_out:
        try:
            meta = parse_last_json_line(meta_out)
        except Exception as e:
            meta_error = f"parse meta json: {e}"
    else:
        meta_error = f"meta rc={meta_rc} timed_out={int(meta_timed_out)}"

    if meta is None:
        elapsed = int(time.monotonic() - t0)
        result = {
            "id": id_value,
            "success": 0,
            "elapsed_seconds": elapsed,
            "error": meta_error,
            "outcome": "meta_failed",
            "outcome_detail": (meta_error or "")[:800],
            "artifacts_dir": str(artifacts_dir),
        }
        write_json(artifacts_dir / "result.json", result)
        batch_log(tag, f"end | meta_failed | {meta_error}")
        return result

    write_json(artifacts_dir / "meta.json", meta)
    project_name = str(meta.get("project") or "").strip()
    if not project_name:
        elapsed = int(time.monotonic() - t0)
        result = {
            "id": id_value,
            "success": 0,
            "elapsed_seconds": elapsed,
            "outcome": "meta_failed",
            "artifacts_dir": str(artifacts_dir),
        }
        write_json(artifacts_dir / "result.json", result)
        return result

    batch_log(
        tag,
        f"meta | project={project_name} | file={meta.get('v_rel_path')} | repeats={cfg.repeats}",
    )

    trials: list[dict[str, Any]] = []
    repo_dir = Path()
    for trial_index in range(1, cfg.repeats + 1):
        copy_parent = trial_workspace_parent(cfg.workspace_batch_dir, id_value, trial_index)
        trial_artifacts_dir = (artifacts_dir / f"trial_{trial_index:03d}").resolve()
        trial_result = _run_one_trial(
            id_value,
            trial_index,
            cfg.repeats,
            cfg,
            meta,
            project_name,
            copy_parent,
            trial_artifacts_dir,
            tag,
        )
        trials.append(trial_result)
        repo_dir = (copy_parent / project_name).resolve()
        if int(trial_result.get("success", 0) or 0) == 1:
            if trial_index < cfg.repeats:
                batch_log(
                    tag,
                    f"early stop | trial {trial_index} succeeded, skip remaining "
                    f"{cfg.repeats - trial_index} repeat(s)",
                )
            break

    stats = _aggregate_trial_stats(trials)
    elapsed = int(time.monotonic() - t0)
    any_ok = stats["success_count"] > 0
    aggregate: dict[str, Any] = {
        "id": id_value,
        "project": meta.get("project"),
        "target_coq_file": meta.get("v_rel_path"),
        "repeats": cfg.repeats,
        "trials": trials,
        "repo_dir": str(repo_dir),
        "artifacts_dir": str(artifacts_dir),
        "elapsed_seconds": elapsed,
        **stats,
        "any_trial_success": 1 if any_ok else 0,
        "success": 1 if any_ok else 0,
    }
    write_json(artifacts_dir / "aggregate.json", aggregate)
    write_json(artifacts_dir / "result.json", aggregate)
    batch_log(
        tag,
        f"end | trial_ok={stats['success_count']}/{stats['trial_count']} | elapsed={elapsed}s",
    )
    return aggregate


def _flatten_trial_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in results:
        trials = r.get("trials")
        if isinstance(trials, list) and trials:
            rows.extend(trials)
            continue
        row = dict(r)
        row.setdefault("trial", "")
        rows.append(row)
    return rows


def _format_csv_cell(value: Any) -> str:
    s = "" if value is None else str(value)
    s = s.replace('"', '""')
    if "," in s or "\n" in s or '"' in s:
        s = '"' + s + '"'
    return s


def _write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    cols = [
        "id",
        "trial",
        "repeats",
        "project",
        "target_coq_file",
        "success",
        "outcome",
        "outcome_detail",
        "elapsed_seconds",
        "post_copy_make_rc",
        "verify_make_rc",
        "skip_reason",
        "tokens_api_calls",
        "tokens_total",
        "tokens_prompt_cache_hit",
        "tokens_prompt_cache_miss",
        "tokens_completion",
        "tokens_reasoning",
        "tokens_parse_source",
    ]
    lines = [",".join(cols)]
    for r in rows:
        lines.append(",".join(_format_csv_cell(r.get(c)) for c in cols))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_by_id_csv(path: Path, results: list[dict[str, Any]]) -> None:
    cols = [
        "id",
        "project",
        "target_coq_file",
        "repeats",
        "trial_count",
        "success_count",
        "success_rate",
        "any_trial_success",
        "success",
        "elapsed_seconds",
        "tokens_total_sum",
        "tokens_total_min",
        "tokens_total_max",
    ]
    lines = [",".join(cols)]
    for r in results:
        lines.append(",".join(_format_csv_cell(r.get(c)) for c in cols))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _flush_summary(result_dir: Path, results: list[dict[str, Any]], total_planned: int | None) -> None:
    if not results:
        return
    sorted_r = sorted(results, key=lambda r: int(r.get("id", 0)))
    trial_rows = _flatten_trial_rows(sorted_r)
    write_json(result_dir / "summary.json", sorted_r)
    _write_summary_csv(result_dir / "summary.csv", trial_rows)
    _write_summary_by_id_csv(result_dir / "summary_by_id.csv", sorted_r)
    ok_trials = sum(1 for x in trial_rows if int(x.get("success", 0) or 0) == 1)
    dist = Counter(str(x.get("outcome", "")) for x in trial_rows)
    dist_s = ", ".join(f"{k}={v}" for k, v in sorted(dist.items()))
    tail = f"planned={total_planned}" if total_planned is not None else ""
    batch_log(
        "[batch]",
        f"summary | ids={len(sorted_r)} trial_ok={ok_trials}/{len(trial_rows)} | {tail} | {dist_s}",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="PALM batch evaluation on CoqStoq ids.")
    ap.add_argument("--ids", type=int, nargs="*", default=None)
    ap.add_argument("--testlist", type=Path, default=DEFAULT_TESTLIST)
    ap.add_argument("--out", type=Path, default=AGENT_WORKSPACE_PALM)
    ap.add_argument("--result-dir", type=Path, default=None)
    ap.add_argument("--batch-stamp", type=str, default=None)
    ap.add_argument("--split", type=str, default="test", choices=("test", "validation", "cutoff"))
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--make-timeout-seconds", type=int, default=180)
    ap.add_argument("--palm-run-timeout-seconds", type=int, default=1800)
    ap.add_argument("--coqstoq-path", type=Path, default=None)
    ap.add_argument(
        "--coqstoq-python",
        type=str,
        default=None,
        help="Python for coqstoq_meta / coqstoq_minimal_copy (default: COQSTOQ_PYTHON or CoqProver env).",
    )
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="PALM LLM prompt budget passed to src.main (default 200000).",
    )
    args = ap.parse_args()

    if int(args.repeats) < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return 2
    if args.max_tokens is not None and int(args.max_tokens) < 1:
        print("--max-tokens must be >= 1", file=sys.stderr)
        return 2

    ids = args.ids
    if not ids:
        if not args.testlist.is_file():
            print(f"TestList not found: {args.testlist}", file=sys.stderr)
            return 2
        ids = read_ids_from_testlist(args.testlist)
    if not ids:
        print("No ids to run.", file=sys.stderr)
        return 2

    batch_stamp = (args.batch_stamp or "").strip() or make_batch_workspace_stamp()
    workspace_batch_dir = (args.out.resolve() / batch_stamp).resolve()
    result_dir = args.result_dir
    if result_dir is None:
        result_dir = _EVAL_DIR / "Result" / batch_stamp
    result_dir = result_dir.resolve()

    coqstoq_path = args.coqstoq_path.resolve() if args.coqstoq_path else None
    if coqstoq_path is None:
        raw = os.environ.get("COQSTOQ_PATH")
        if raw:
            coqstoq_path = Path(raw).resolve()

    if args.max_tokens is not None:
        llm_max_tokens = int(args.max_tokens)
    else:
        env_mt = os.environ.get("PALM_MAX_TOKENS", "").strip()
        llm_max_tokens = int(env_mt) if env_mt else 200_000

    cfg = BatchConfig(
        repo_root=_REPO_ROOT.resolve(),
        eval_dir=_EVAL_DIR.resolve(),
        coqstoq_path=coqstoq_path,
        workspace_agent_root=args.out.resolve(),
        workspace_batch_dir=workspace_batch_dir,
        result_dir=result_dir,
        split=args.split,
        make_timeout_seconds=int(args.make_timeout_seconds),
        palm_run_timeout_seconds=int(args.palm_run_timeout_seconds),
        repeats=int(args.repeats),
        python_executable=sys.executable,
        coqstoq_python_executable=(
            args.coqstoq_python.strip()
            if args.coqstoq_python
            else _default_coqstoq_python()
        ),
        llm_max_tokens=llm_max_tokens,
    )

    workspace_batch_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    batch_log(
        "[batch]",
        f"ids={len(ids)} workers={args.workers} repeats={cfg.repeats} max_tokens={cfg.llm_max_tokens} | "
        f"workspace={workspace_batch_dir} | result={result_dir}",
    )

    results: list[dict[str, Any]] = []
    total_n = len(ids)
    interrupted = False
    try:
        if args.workers <= 1 or len(ids) == 1:
            for idx, i in enumerate(ids, start=1):
                batch_log("[batch]", f"progress {idx}/{len(ids)} | id={i}")
                results.append(_run_one(i, cfg))
                _flush_summary(result_dir, results, total_planned=total_n)
        else:
            with ProcessPoolExecutor(max_workers=int(args.workers)) as ex:
                futs = {ex.submit(_run_one, i, cfg): i for i in ids}
                for fut in as_completed(futs):
                    rid = futs[fut]
                    try:
                        r = fut.result()
                    except Exception as e:
                        art = (result_dir / f"id_{rid}").resolve()
                        r = {
                            "id": rid,
                            "success": 0,
                            "outcome": "worker_crash",
                            "outcome_detail": repr(e)[:800],
                            "artifacts_dir": str(art),
                        }
                        write_json(art / "result.json", r)
                        batch_log("[batch]", f"worker exception id={rid}: {e}")
                    results.append(r)
                    _flush_summary(result_dir, results, total_planned=total_n)
    except KeyboardInterrupt:
        interrupted = True
        batch_log("[batch]", "KeyboardInterrupt: flushing partial summary")
    finally:
        if results:
            _flush_summary(result_dir, results, total_planned=total_n)

    trial_rows = _flatten_trial_rows(results)
    ok_trials = sum(1 for r in trial_rows if int(r.get("success", 0) or 0) == 1)
    batch_log(
        "[batch]",
        f"{'interrupted, ' if interrupted else ''}done | trial_ok={ok_trials}/{len(trial_rows)} | "
        f"summary={result_dir / 'summary.csv'}",
    )
    return 0 if not interrupted else 130


if __name__ == "__main__":
    raise SystemExit(main())
