#!/usr/bin/env python3
"""ProofAgent batch runner for Parcas evaluation (fixed TestList.json catalog ids)."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
_EVAL_DIR = _REPO_ROOT / "Evaluation"
if str(_EVAL_PARCAS_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_PARCAS_DIR))
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from batch_workspace_layout import (
    AGENT_WORKSPACE_PARCAS,
    make_batch_workspace_stamp,
    trial_workspace_parent,
)
from parcas_testlist import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_TESTLIST_PATH,
    cli_argv_includes_repeats_flag,
    collect_abort_file_rel_paths,
    read_run_specs_from_testlist_file,
    testlist_has_configured_repeats,
)
from BatchTest.testlist_run_specs import IdRunSpec, repeats_for_id
from BatchTest.coq_strip_comments import find_skip_keywords, strip_coq_comments
from BatchTest.batch_llm_endpoint import resolve_llm_api_key, resolve_llm_base_url
from BatchTest.agent_run_seconds_backfill import apply_measured_agent_run_seconds
from BatchTest.post_copy_make import run_post_copy_make_with_retries
from BatchTest.proofagent_token_log import collect_run_capture_text, parse_token_usage_from_text
from BatchTest.theorem_integrity import (
    capture_theorem_baseline,
    check_theorem_modified_after_agent,
)
from parcas_batch_env import (
    build_check_shell,
    extra_readable_root_paths,
    resolve_parcas_opam_switch,
)
from parcas_eval_build_files import parcas_eval_build_shell_command
from parcas_batch_user_message import format_parcas_proofagent_batch_user_message

_BATCH_CHAT_MODEL = "deepseek-v4-flash"
_BATCH_REASONING_EFFORT = "max"
_ALLOWED_REASONING_EFFORTS = frozenset({"high", "max", "low", "medium", "xhigh"})


def _format_batch_user_message(target_coq_file: str, *, extra_read: bool) -> str:
    return format_parcas_proofagent_batch_user_message(target_coq_file, extra_read=extra_read)


def _batch_log(prefix: str, message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} {prefix} {message}", flush=True)


def _parcas_meta_script() -> Path:
    return (_EVAL_PARCAS_DIR / "parcas_meta.py").resolve()


def _normalize_reasoning_effort(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized not in _ALLOWED_REASONING_EFFORTS:
        allowed = ", ".join(sorted(_ALLOWED_REASONING_EFFORTS))
        raise ValueError(f"reasoning effort must be one of: {allowed}; got: {raw!r}")
    return normalized


def _parcas_minimal_copy_script() -> Path:
    return (_EVAL_PARCAS_DIR / "parcas_minimal_copy.py").resolve()


def _stoq_minimal_copy_script() -> Path:
    return (_REPO_ROOT / "scripts" / "coqstoq_minimal_copy.py").resolve()


def _parse_last_json_line(stdout: str) -> dict[str, Any]:
    # coqstoq_meta may print diagnostics; JSON is the last line in our meta tool.
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("{") and ln.endswith("}"):
            return json.loads(ln)
    raise ValueError("no JSON line found in meta output")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_proofagent_run_config(
    run_directory: Path,
    *,
    project_root: Path,
    target_coq_file: str,
    user_message: str,
    check_timeout_seconds: int,
    check_command: str,
    parse_sentence_script: str,
    base_url: str,
    model: str,
    reasoning_effort: str,
    extra_readable_root_paths: list[str],
) -> Path:
    run_directory.mkdir(parents=True, exist_ok=True)
    config_path = run_directory / "proofagent.config.json"
    payload = {
        "projectRoot": str(project_root.resolve()),
        "targetCoqFile": target_coq_file,
        "userMessage": user_message,
        "checkTimeoutSeconds": check_timeout_seconds,
        "checkCommand": check_command,
        "parseSentenceScript": parse_sentence_script,
        "baseUrl": base_url,
        "model": model,
        "reasoningEffort": reasoning_effort,
    }
    if extra_readable_root_paths:
        payload["extraReadableRootPaths"] = list(extra_readable_root_paths)
    config_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return config_path


def _run_capture(
    cmd: list[str],
    cwd: Path | None,
    env: dict[str, str] | None,
    timeout_seconds: int | None,
) -> tuple[int, str, str, bool]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return 124, out, err, True


def _ensure_proofagent_built(proofagent_root: Path) -> None:
    csproj = (proofagent_root / "ProofAgent.csproj").resolve()
    if not csproj.is_file():
        raise FileNotFoundError(f"ProofAgent.csproj not found: {csproj}")
    build_cmd = ["dotnet", "build", str(csproj), "-c", "Debug", "-v", "q", "-nologo"]
    rc, out, err, timed_out = _run_capture(build_cmd, cwd=proofagent_root, env=None, timeout_seconds=600)
    if timed_out or rc != 0:
        detail = (err or out or "").strip()[:800]
        raise RuntimeError(f"dotnet build failed rc={rc} timed_out={int(timed_out)}: {detail}")


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _skip_keyword_rel_excluded(rel: str, excluded: frozenset[str]) -> bool:
    if rel in excluded:
        return True
    for prefix in ("_build/default/", "_build/install/default/"):
        if rel.startswith(prefix):
            src_rel = rel[len(prefix) :]
            if src_rel in excluded:
                return True
    return False


def _scan_repo_for_skip_keywords(
    repo_dir: Path,
    extra_keywords: list[str] | None,
    exclude_v_rel_paths: frozenset[str] | None = None,
) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    excluded = exclude_v_rel_paths or frozenset()
    skip_dir_names = frozenset({"_build", ".git"})
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in skip_dir_names]
        for fn in files:
            if not fn.endswith(".v"):
                continue
            fp = Path(root) / fn
            rel = fp.relative_to(repo_dir).as_posix()
            if _skip_keyword_rel_excluded(rel, excluded):
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            no_comments = strip_coq_comments(text)
            kws = find_skip_keywords(no_comments, extra_keywords=extra_keywords)
            if kws:
                hits[rel] = kws
    return hits


@dataclass(frozen=True)
class OneRunConfig:
    proofagent_root: Path
    parcas_project_root: Path
    parcas_catalog: Path
    """Agent home under evaluation workspace, under RAIN_EVAL_WORKSPACE/AgentTest_parcas."""
    workspace_agent_root: Path
    """This run: ``<agent_root>/<M-D-H-M_batch>/id_<n>/trial_<k>/`` project copies."""
    workspace_batch_dir: Path
    """Summary CSV/JSON and per-id logs (stdout/stderr, result.json)."""
    result_dir: Path
    check_timeout_seconds: int
    run_timeout_seconds: int
    verify_make_timeout_seconds: int
    extra_skip_keywords: list[str]
    skip_keyword_scan_exclude_v_relpaths: frozenset[str]
    repeats: int
    id_repeats: dict[int, int]
    chat_model: str
    reasoning_effort: str
    parse_sentence_script: str
    parse_sentence_timeout_seconds: int
    llm_base_url: str
    llm_api_key: str
    parcas_opam_switch: str
    parcas_dune_check_full_theory: bool
    extra_readable_root_paths: list[str]


def _run_build_shell(
    shell_line: str,
    cwd: Path | None,
    timeout_seconds: int,
) -> tuple[int, str, str, bool]:
    cmd = [
        "timeout",
        str(timeout_seconds),
        "/bin/sh",
        "-c",
        shell_line,
    ]
    return _run_capture(cmd, cwd=cwd, env=None, timeout_seconds=timeout_seconds + 10)


def _run_one_trial(
    id_value: int,
    trial_index: int,
    repeat_total: int,
    cfg: OneRunConfig,
    meta: dict[str, Any],
    project_name: str,
    repo_dir: Path,
    copy_parent: Path,
    trial_artifacts_dir: Path,
    parent_tag: str,
) -> dict[str, Any]:
    t0 = time.monotonic()
    tag = f"{parent_tag} trial={trial_index}/{repeat_total}"
    _ensure_dir(trial_artifacts_dir)

    v_rel_path = str(meta.get("v_rel_path") or "").strip()
    trial_check_shell = ""
    user_message = _format_batch_user_message(
        v_rel_path or "(unknown target file)",
        extra_read=bool(cfg.extra_readable_root_paths),
    )
    _write_text(trial_artifacts_dir / "user_message.txt", user_message + "\n")

    copy_script = _parcas_minimal_copy_script()
    workspace_root = Path(str(meta.get("workspace_root") or "")).resolve()
    vfile_abs = (workspace_root / v_rel_path).resolve()
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
        "--opam-switch",
        cfg.parcas_opam_switch,
        "--theorem-end-line0",
        str(int(meta.get("theorem_end_line0"))),
        "--theorem-end-column-raw",
        str(int(meta.get("theorem_end_column_raw") or 0)),
    ]
    copy_rc, copy_out, copy_err, copy_timed_out = _run_capture(
        copy_cmd, cwd=cfg.proofagent_root, env=None, timeout_seconds=600
    )
    _write_text(trial_artifacts_dir / "copy_stdout.log", copy_out)
    _write_text(trial_artifacts_dir / "copy_stderr.log", copy_err)
    _batch_log(tag, f"copy done | rc={copy_rc} | timed_out={int(copy_timed_out)}")

    post_copy_make_rc: int | None = None
    post_copy_make_timed_out = False
    post_copy_make_ok: int | None = None
    post_make_note = ""
    skip_reason: str | None = None
    theorem_baseline_ok = 0
    theorem_baseline_error: str | None = None
    theorem_proposition_text: str | None = None
    theorem_modified = 0

    if copy_rc != 0 or copy_timed_out:
        skip_reason = "copy_failed"
    elif not repo_dir.exists():
        skip_reason = "copy_output_missing"
    elif not v_rel_path:
        skip_reason = "theorem_baseline_failed"
        theorem_baseline_error = "missing v_rel_path in meta"
    elif not cfg.parse_sentence_script.strip():
        skip_reason = "theorem_baseline_failed"
        theorem_baseline_error = "parse sentence script is empty"
    else:
        try:
            if cfg.parcas_dune_check_full_theory:
                trial_check_shell = build_check_shell(
                    cfg.parcas_opam_switch,
                    v_rel_path,
                    full_theory=True,
                )
            else:
                trial_check_shell = parcas_eval_build_shell_command(repo_dir)
            _batch_log(tag, f"check build shell | {trial_check_shell}")
        except (ValueError, FileNotFoundError) as exc:
            skip_reason = "copy_failed"
            theorem_baseline_error = f"check build shell: {exc}"
            _batch_log(tag, f"check build shell failed | {exc}")

    if skip_reason is None:
        target_coq_abs = (repo_dir / v_rel_path).resolve()
        if not target_coq_abs.is_file():
            skip_reason = "theorem_baseline_failed"
            theorem_baseline_error = f"target file not found: {v_rel_path}"
        else:
            baseline = capture_theorem_baseline(
                repo_dir,
                target_coq_abs,
                cfg.parse_sentence_script,
                cfg.parse_sentence_timeout_seconds,
                trial_artifacts_dir,
            )
            if baseline.ok and baseline.proposition_text:
                theorem_baseline_ok = 1
                theorem_proposition_text = baseline.proposition_text
                _batch_log(
                    tag,
                    f"theorem baseline ok | len={baseline.proposition_len} | "
                    f"hash={baseline.collapsed_hash_prefix}",
                )
            else:
                skip_reason = "theorem_baseline_failed"
                theorem_baseline_error = baseline.error or "theorem baseline capture failed"
                _batch_log(tag, f"theorem baseline failed | {theorem_baseline_error}")

    if skip_reason is None:
        post_copy_result = run_post_copy_make_with_retries(
            repo_dir,
            cfg.verify_make_timeout_seconds,
            build_shell_line=trial_check_shell,
        )
        post_copy_make_rc = post_copy_result.returncode
        post_copy_make_out = post_copy_result.stdout
        post_copy_make_err = post_copy_result.stderr
        post_copy_make_timed_out = post_copy_result.timed_out
        _write_text(trial_artifacts_dir / "post_copy_make_stdout.log", post_copy_make_out)
        _write_text(trial_artifacts_dir / "post_copy_make_stderr.log", post_copy_make_err)
        post_copy_make_ok = 1 if (not post_copy_make_timed_out and post_copy_make_rc == 0) else 0
        if post_copy_make_ok == 0:
            post_make_note = "post_make_nonzero"
            _batch_log(
                tag,
                f"post-copy make failed (continuing ProofAgent) | rc={post_copy_make_rc} | "
                f"timed_out={int(post_copy_make_timed_out)} | attempts={post_copy_result.attempts_summary}",
            )
        else:
            _batch_log(
                tag,
                f"post-copy make done | rc={post_copy_make_rc} | timed_out={int(post_copy_make_timed_out)} | "
                f"attempts={post_copy_result.attempts_summary}",
            )

    run_rc = -1
    run_out = ""
    run_err = ""
    run_timed_out = False
    make_rc = -1
    make_out = ""
    make_err = ""
    make_timed_out = False
    skip_hits: dict[str, list[str]] = {}
    agent_t0: float | None = None

    if skip_reason is None:
        _batch_log(
            tag,
            f"ProofAgent start | model={cfg.chat_model} reasoning_effort={cfg.reasoning_effort} | "
            f"run_timeout={cfg.run_timeout_seconds}s",
        )
        _write_proofagent_run_config(
            trial_artifacts_dir,
            project_root=repo_dir,
            target_coq_file=v_rel_path,
            user_message=user_message,
            check_timeout_seconds=cfg.check_timeout_seconds,
            check_command=trial_check_shell,
            parse_sentence_script=cfg.parse_sentence_script,
            base_url=cfg.llm_base_url,
            model=cfg.chat_model,
            reasoning_effort=cfg.reasoning_effort,
            extra_readable_root_paths=cfg.extra_readable_root_paths,
        )
        run_cmd = [
            "timeout",
            str(cfg.run_timeout_seconds),
            str((cfg.proofagent_root / "run.sh").resolve()),
        ]
        run_env = os.environ.copy()
        run_env["LLM_API_KEY"] = cfg.llm_api_key
        agent_t0 = time.monotonic()
        run_rc, run_out, run_err, run_timed_out = _run_capture(
            run_cmd,
            cwd=trial_artifacts_dir,
            env=run_env,
            timeout_seconds=cfg.run_timeout_seconds + 30,
        )
        _write_text(trial_artifacts_dir / "run_stdout.log", run_out)
        _write_text(trial_artifacts_dir / "run_stderr.log", run_err)
        _batch_log(tag, f"ProofAgent end | rc={run_rc} | timed_out={int(run_timed_out)}")

        make_rc, make_out, make_err, make_timed_out = _run_build_shell(
            trial_check_shell,
            repo_dir if repo_dir.exists() else None,
            cfg.verify_make_timeout_seconds,
        )
        _write_text(trial_artifacts_dir / "verify_make_stdout.log", make_out)
        _write_text(trial_artifacts_dir / "verify_make_stderr.log", make_err)
        _batch_log(tag, f"final verify make | rc={make_rc} | timed_out={int(make_timed_out)}")

        skip_hits = (
            _scan_repo_for_skip_keywords(
                repo_dir,
                extra_keywords=cfg.extra_skip_keywords,
                exclude_v_rel_paths=cfg.skip_keyword_scan_exclude_v_relpaths,
            )
            if repo_dir.exists()
            else {}
        )
        if skip_hits:
            _batch_log(tag, f"skip-keyword hits | files={len(skip_hits)}")
        else:
            _batch_log(tag, "skip-keyword scan | no hits")

        if theorem_proposition_text and skip_reason is None:
            preserved, integrity_err = check_theorem_modified_after_agent(
                repo_dir,
                v_rel_path,
                theorem_proposition_text,
            )
            if not preserved:
                theorem_modified = 1
                _batch_log(tag, f"theorem integrity fail | {integrity_err or 'theorem modified'}")
            else:
                _batch_log(tag, "theorem integrity ok")
    else:
        _batch_log(tag, f"skip ProofAgent / verify | skip_reason={skip_reason}")
        note = (
            f"later steps skipped: {skip_reason}\n"
            f"copy_rc={copy_rc} copy_timed_out={int(copy_timed_out)}\n"
        )
        _write_text(trial_artifacts_dir / "run_stdout.log", note)
        _write_text(trial_artifacts_dir / "run_stderr.log", "")
        _write_text(trial_artifacts_dir / "verify_make_stdout.log", "")
        _write_text(trial_artifacts_dir / "verify_make_stderr.log", "verify_make skipped.\n")

    combined = collect_run_capture_text(run_out, run_err)
    parsed_tokens = parse_token_usage_from_text(combined)
    elapsed = int(time.monotonic() - t0)
    success = 1
    if copy_rc != 0 or copy_timed_out:
        success = 0
    if skip_reason is not None:
        success = 0
    if run_timed_out:
        success = 0
    if skip_reason is None and (make_timed_out or make_rc != 0):
        success = 0
    if skip_hits:
        success = 0
    if theorem_modified:
        success = 0

    workspace_snapshot_dir = str(repo_dir.resolve()) if repo_dir.is_dir() else None
    workspace_trial_dir = str(copy_parent.resolve())

    trial_result: dict[str, Any] = {
        "id": id_value,
        "trial": trial_index,
        "repeats": repeat_total,
        "target_coq_file": v_rel_path,
        "project": meta.get("project"),
        "steps": meta.get("step_count"),
        "chat_model": cfg.chat_model,
        "reasoning_effort": cfg.reasoning_effort,
        "success": success,
        "elapsed_seconds": elapsed,
        "tokens_prompt": parsed_tokens.prompt,
        "tokens_prompt_cache_hit": parsed_tokens.prompt_cache_hit,
        "tokens_prompt_cache_miss": parsed_tokens.prompt_cache_miss,
        "tokens_completion": parsed_tokens.completion,
        "tokens_total": parsed_tokens.total,
        "tokens_parse_source": parsed_tokens.source,
        "repo_dir": str(repo_dir),
        "workspace_trial_dir": workspace_trial_dir,
        "workspace_snapshot_dir": workspace_snapshot_dir,
        "artifacts_dir": str(trial_artifacts_dir),
        "copy_rc": copy_rc,
        "copy_timed_out": int(copy_timed_out),
        "skip_reason": skip_reason,
        "post_copy_make_rc": post_copy_make_rc,
        "post_copy_make_timed_out": int(post_copy_make_timed_out),
        "post_copy_make_ok": post_copy_make_ok,
        "post_make_note": post_make_note,
        "run_rc": run_rc,
        "run_timed_out": int(run_timed_out),
        "verify_make_rc": make_rc,
        "verify_make_timed_out": int(make_timed_out),
        "skip_keyword_hits": skip_hits,
        "theorem_baseline_ok": theorem_baseline_ok,
        "theorem_baseline_error": theorem_baseline_error,
        "theorem_modified": theorem_modified,
        "theorem_proposition_len": len(theorem_proposition_text) if theorem_proposition_text else None,
        "run_stderr_nonempty": _run_stderr_nonempty_flag(run_err, skip_reason),
        "run_stderr_preview": _run_stderr_preview(run_err, skip_reason),
    }
    apply_measured_agent_run_seconds(trial_result, agent_t0=agent_t0)
    _derive_outcome(trial_result)
    _write_json(trial_artifacts_dir / "result.json", trial_result)
    if parsed_tokens.total is not None:
        cache_part = ""
        if parsed_tokens.prompt_cache_hit is not None and parsed_tokens.prompt_cache_miss is not None:
            cache_part = (
                f" cache_hit/miss={parsed_tokens.prompt_cache_hit}/{parsed_tokens.prompt_cache_miss}"
            )
        tok = (
            f"tokens in/out/total={parsed_tokens.prompt}/{parsed_tokens.completion}/"
            f"{parsed_tokens.total}{cache_part} source={parsed_tokens.source}"
        )
    else:
        tok = "tokens=(unparsed)"
    agent_s = trial_result.get("agent_run_seconds")
    agent_part = f" agent_run={agent_s}s" if agent_s is not None else ""
    _batch_log(
        tag,
        f"trial end | success={success} | outcome={trial_result.get('outcome')} | "
        f"elapsed={elapsed}s{agent_part} | {tok}",
    )
    return trial_result


def _aggregate_trial_stats(trials: list[dict[str, Any]]) -> dict[str, Any]:
    success_count = sum(1 for t in trials if int(t.get("success", 0) or 0) == 1)
    n = len(trials)
    totals = [t.get("tokens_total") for t in trials if t.get("tokens_total") is not None]
    elapsed = [int(t.get("elapsed_seconds", 0) or 0) for t in trials]
    agent_runs = [
        int(t.get("agent_run_seconds"))
        for t in trials
        if t.get("agent_run_seconds") is not None
    ]
    return {
        "trial_count": n,
        "success_count": success_count,
        "success_rate": (success_count / n) if n else 0.0,
        "elapsed_seconds_sum": sum(elapsed),
        "elapsed_seconds_min": min(elapsed) if elapsed else None,
        "elapsed_seconds_max": max(elapsed) if elapsed else None,
        "agent_run_seconds_sum": sum(agent_runs) if agent_runs else None,
        "agent_run_seconds_min": min(agent_runs) if agent_runs else None,
        "agent_run_seconds_max": max(agent_runs) if agent_runs else None,
        "tokens_total_sum": sum(int(x) for x in totals) if totals else None,
        "tokens_total_min": min(int(x) for x in totals) if totals else None,
        "tokens_total_max": max(int(x) for x in totals) if totals else None,
    }


def _run_one(id_value: int, cfg: OneRunConfig, *, repeat_total: int) -> dict[str, Any]:
    t0 = time.monotonic()
    tag = f"[id={id_value}]"

    artifacts_dir = (cfg.result_dir / f"id_{id_value}").resolve()
    _ensure_dir(artifacts_dir)

    _batch_log(
        tag,
        f"start | workspace_batch={cfg.workspace_batch_dir} | logs={artifacts_dir}",
    )

    meta_cmd = [
        "python3",
        str(_parcas_meta_script()),
        "--id",
        str(id_value),
        "--parcas-path",
        str(cfg.parcas_project_root.resolve()),
        "--catalog",
        str(cfg.parcas_catalog.resolve()),
        "--parse-sentence-script",
        cfg.parse_sentence_script,
        "--parse-sentence-timeout-seconds",
        str(cfg.parse_sentence_timeout_seconds),
    ]

    meta_rc, meta_out, meta_err, meta_timed_out = _run_capture(
        meta_cmd, cwd=cfg.proofagent_root, env=None, timeout_seconds=180
    )
    _write_text(artifacts_dir / "meta_stdout.log", meta_out)
    _write_text(artifacts_dir / "meta_stderr.log", meta_err)

    meta: dict[str, Any] | None = None
    meta_error: str | None = None
    if meta_rc == 0 and not meta_timed_out:
        try:
            meta = _parse_last_json_line(meta_out)
        except Exception as e:
            meta_error = f"failed to parse meta json: {e}"
    else:
        meta_error = f"meta failed rc={meta_rc} timed_out={int(meta_timed_out)}"

    if meta is None:
        elapsed = int(time.monotonic() - t0)
        result = {
            "id": id_value,
            "success": 0,
            "elapsed_seconds": elapsed,
            "error": meta_error,
            "repo_dir": "",
            "artifacts_dir": str(artifacts_dir),
            "outcome": "meta_failed",
            "outcome_detail": (meta_error or "")[:800],
        }
        _write_json(artifacts_dir / "result.json", result)
        _batch_log(tag, f"end | success=0 | outcome=meta_failed | {meta_error} | {elapsed}s")
        return result

    _write_json(artifacts_dir / "meta.json", meta)
    project_name = str(meta.get("project") or "").strip()
    if not project_name:
        elapsed = int(time.monotonic() - t0)
        result = {
            "id": id_value,
            "success": 0,
            "elapsed_seconds": elapsed,
            "error": "meta missing project name",
            "repo_dir": "",
            "artifacts_dir": str(artifacts_dir),
            "outcome": "meta_failed",
            "outcome_detail": "meta missing project",
        }
        _write_json(artifacts_dir / "result.json", result)
        _batch_log(tag, f"end | success=0 | outcome=meta_failed | missing project | {elapsed}s")
        return result

    _batch_log(
        tag,
        f"meta done | project={project_name} | steps={meta.get('step_count')} | v={meta.get('v_rel_path')} | "
        f"repeats={repeat_total}",
    )

    trials: list[dict[str, Any]] = []
    for trial_index in range(1, repeat_total + 1):
        copy_parent = trial_workspace_parent(cfg.workspace_batch_dir, id_value, trial_index)
        repo_dir = (copy_parent / project_name).resolve()
        trial_artifacts_dir = (artifacts_dir / f"trial_{trial_index:03d}").resolve()
        trials.append(
            _run_one_trial(
                id_value,
                trial_index,
                repeat_total,
                cfg,
                meta,
                project_name,
                repo_dir,
                copy_parent,
                trial_artifacts_dir,
                tag,
            )
        )

    stats = _aggregate_trial_stats(trials)
    elapsed = int(time.monotonic() - t0)
    all_trials_ok = stats["success_count"] == repeat_total and repeat_total > 0
    aggregate: dict[str, Any] = {
        "id": id_value,
        "project": meta.get("project"),
        "steps": meta.get("step_count"),
        "target_coq_file": meta.get("v_rel_path"),
        "repeats": repeat_total,
        "trials": trials,
        "repo_dir": str(repo_dir),
        "artifacts_dir": str(artifacts_dir),
        "elapsed_seconds": elapsed,
        **stats,
        "any_trial_success": 1 if stats["success_count"] > 0 else 0,
        "success": 1 if all_trials_ok else 0,
    }
    _write_json(artifacts_dir / "aggregate.json", aggregate)
    _write_json(artifacts_dir / "result.json", aggregate)
    _batch_log(
        tag,
        f"end | repeats={repeat_total} | trial_ok={stats['success_count']}/{stats['trial_count']} | "
        f"success_rate={stats['success_rate']:.2f} | elapsed={elapsed}s | "
        f"tokens_total_sum={stats.get('tokens_total_sum')}",
    )
    return aggregate


def _run_one_with_cfg(id_value: int, cfg: OneRunConfig) -> dict[str, Any]:
    repeat_total = repeats_for_id(
        default_repeats=cfg.repeats,
        id_repeats=cfg.id_repeats,
        id_value=id_value,
    )
    return _run_one(id_value, cfg, repeat_total=repeat_total)


def _run_stderr_nonempty_flag(run_err: str, skip_reason: str | None) -> int:
    if skip_reason is not None:
        return 0
    return 1 if (run_err or "").strip() else 0


def _run_stderr_preview(run_err: str, skip_reason: str | None) -> str:
    if skip_reason is not None:
        return ""
    if not (run_err or "").strip():
        return ""
    return _csv_detail_cell(run_err, 400)


def _csv_detail_cell(value: Any, max_len: int = 220) -> str:
    s = "" if value is None else str(value)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _derive_outcome(r: dict[str, Any]) -> None:
    """Set outcome / outcome_detail for one row (machine-readable failure tag)."""
    if int(r.get("success", 0) or 0) == 1:
        p_ok = r.get("post_copy_make_ok")
        try:
            p_ok_int = int(p_ok) if p_ok is not None else 1
        except (TypeError, ValueError):
            p_ok_int = 1
        if p_ok_int == 0:
            r["outcome"] = "success_post_make_nonzero"
            r["outcome_detail"] = (r.get("post_make_note") or "post_make_nonzero") + (
                f";rc={r.get('post_copy_make_rc')}" if r.get("post_copy_make_rc") is not None else ""
            )
        else:
            r["outcome"] = "success"
            r["outcome_detail"] = ""
        return
    if r.get("outcome"):
        return

    sr = r.get("skip_reason")

    if int(r.get("theorem_modified", 0) or 0) == 1:
        r["outcome"] = "theorem_modified"
        r["outcome_detail"] = "theorem modified"
        return

    if sr == "theorem_baseline_failed":
        r["outcome"] = "theorem_baseline_failed"
        r["outcome_detail"] = _csv_detail_cell(r.get("theorem_baseline_error") or "", 400)
        return

    if int(r.get("copy_timed_out", 0) or 0) == 1:
        r["outcome"] = "copy_timeout"
        r["outcome_detail"] = f"copy_rc={r.get('copy_rc', '')}"
        return

    cr = r.get("copy_rc")
    if cr is not None and int(cr) != 0:
        r["outcome"] = "copy_failed"
        r["outcome_detail"] = f"rc={cr}"
        return

    if sr == "copy_output_missing":
        r["outcome"] = "copy_output_missing"
        r["outcome_detail"] = ""
        return

    run_timed = int(r.get("run_timed_out", 0) or 0) == 1
    run_raw = r.get("run_rc", -1)
    try:
        run_rc_int = int(run_raw) if run_raw is not None else -1
    except (TypeError, ValueError):
        run_rc_int = -1

    if run_timed or run_rc_int == 124:
        r["outcome"] = "agent_timeout"
        r["outcome_detail"] = f"run_timed_out={int(run_timed)} run_rc={run_rc_int}"
        return

    if sr is None and int(r.get("run_stderr_nonempty", 0) or 0) == 1:
        r["outcome"] = "agent_error"
        detail_parts: list[str] = []
        if run_rc_int not in (-1, 0):
            detail_parts.append(f"run_rc={run_rc_int}")
        preview = (r.get("run_stderr_preview") or "").strip()
        if preview:
            detail_parts.append(preview)
        else:
            detail_parts.append("stderr_non_empty")
        r["outcome_detail"] = _csv_detail_cell("; ".join(detail_parts), 400)
        return

    if sr is None and run_rc_int not in (-1, 0):
        r["outcome"] = "agent_error"
        r["outcome_detail"] = f"run_rc={run_rc_int}"
        return

    if int(r.get("verify_make_timed_out", 0) or 0) == 1:
        r["outcome"] = "verify_make_timeout"
        r["outcome_detail"] = ""
        return

    vm = r.get("verify_make_rc")
    try:
        vm_int = int(vm) if vm is not None else -1
    except (TypeError, ValueError):
        vm_int = -1
    if sr is None and vm_int not in (-1, 0):
        r["outcome"] = "verify_make_failed"
        r["outcome_detail"] = f"rc={vm_int}"
        return

    hits = r.get("skip_keyword_hits") or {}
    if isinstance(hits, dict) and hits:
        r["outcome"] = "skip_keyword"
        r["outcome_detail"] = ";".join(list(hits.keys())[:10])
        return

    r["outcome"] = "unknown_failure"
    r["outcome_detail"] = _csv_detail_cell(str(sr) if sr else "", 400)


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


_SUMMARY_TRIALS_WIDE_ID_COLS = [
    "id",
    "project",
    "target_coq_file",
    "repeats",
    "steps",
]

_SUMMARY_TRIALS_WIDE_AGG_COLS = [
    "success_count",
    "success_rate",
    "any_trial_success",
    "success",
    "elapsed_seconds",
    "elapsed_seconds_sum",
    "tokens_total_sum",
    "tokens_total_min",
    "tokens_total_max",
]

_SUMMARY_TRIALS_WIDE_TRIAL_METRICS = [
    "success",
    "outcome",
    "outcome_detail",
    "elapsed_seconds",
    "agent_run_seconds",
    "tokens_prompt",
    "tokens_prompt_cache_hit",
    "tokens_prompt_cache_miss",
    "tokens_completion",
    "tokens_total",
    "post_copy_make_ok",
    "theorem_baseline_ok",
    "theorem_modified",
    "run_rc",
    "run_timed_out",
]


def _max_repeats_in_batch_results(id_results: list[dict[str, Any]]) -> int:
    n = 1
    for r in id_results:
        repeats = int(r.get("repeats") or 0)
        trials = r.get("trials")
        trial_len = len(trials) if isinstance(trials, list) else 0
        n = max(n, repeats, trial_len)
    return n


def _format_csv_cell(value: Any, *, detail: bool = False) -> str:
    if detail:
        s = _csv_detail_cell(value)
    else:
        s = "" if value is None else str(value)
    s = s.replace('"', '""')
    if "," in s or "\n" in s or '"' in s:
        s = '"' + s + '"'
    return s


def _write_summary_trials_wide_csv(path: Path, id_results: list[dict[str, Any]]) -> None:
    """One row per theorem id; ``trial_<k>_<metric>`` columns for each repeat."""
    max_repeats = _max_repeats_in_batch_results(id_results)
    trial_cols: list[str] = []
    for trial_index in range(1, max_repeats + 1):
        prefix = f"trial_{trial_index}_"
        for metric in _SUMMARY_TRIALS_WIDE_TRIAL_METRICS:
            trial_cols.append(prefix + metric)

    cols = list(_SUMMARY_TRIALS_WIDE_ID_COLS) + list(_SUMMARY_TRIALS_WIDE_AGG_COLS) + trial_cols
    lines = [",".join(cols)]
    for r in id_results:
        row_cells: list[str] = []
        for c in _SUMMARY_TRIALS_WIDE_ID_COLS:
            row_cells.append(_format_csv_cell(r.get(c)))
        for c in _SUMMARY_TRIALS_WIDE_AGG_COLS:
            row_cells.append(_format_csv_cell(r.get(c)))

        trials_by_index: dict[int, dict[str, Any]] = {}
        trials = r.get("trials")
        if isinstance(trials, list):
            for tr in trials:
                if not isinstance(tr, dict):
                    continue
                try:
                    idx = int(tr.get("trial", 0))
                except (TypeError, ValueError):
                    continue
                if idx > 0:
                    trials_by_index[idx] = tr

        for trial_index in range(1, max_repeats + 1):
            tr = trials_by_index.get(trial_index, {})
            for metric in _SUMMARY_TRIALS_WIDE_TRIAL_METRICS:
                row_cells.append(_format_csv_cell(tr.get(metric), detail=(metric == "outcome_detail")))

        lines.append(",".join(row_cells))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _flush_summary(result_dir: Path, results: list[dict[str, Any]], *, log_line: bool, total_planned: int | None) -> None:
    if not results:
        return
    result_dir.mkdir(parents=True, exist_ok=True)
    sorted_r = sorted(results, key=lambda r: int(r.get("id", 0)))
    trial_rows = _flatten_trial_rows(sorted_r)
    _write_json(result_dir / "summary.json", sorted_r)
    _write_summary_csv(result_dir / "summary.csv", trial_rows)
    _write_summary_trials_wide_csv(result_dir / "summary_trials.csv", sorted_r)
    _write_summary_by_id_csv(result_dir / "summary_by_id.csv", sorted_r)
    if log_line:
        ok_trials = sum(1 for x in trial_rows if int(x.get("success", 0) or 0) == 1)
        ok_ids = sum(1 for x in sorted_r if int(x.get("success", 0) or 0) == 1)
        dist = Counter(str(x.get("outcome", "")) for x in trial_rows)
        dist_s = ", ".join(f"{k}={v}" for k, v in sorted(dist.items()))
        tail = f"planned_ids={total_planned}" if total_planned is not None else ""
        _batch_log(
            "[batch]",
            f"summary flushed | ids={len(sorted_r)} trial_rows={len(trial_rows)} | "
            f"trial_ok={ok_trials}/{len(trial_rows)} id_all_ok={ok_ids}/{len(sorted_r)} | {tail} | outcome: {dist_s}",
        )


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
        "elapsed_seconds",
        "elapsed_seconds_sum",
        "tokens_total_sum",
        "tokens_total_min",
        "tokens_total_max",
        "success",
    ]
    lines = [",".join(cols)]
    for r in results:
        row = []
        for c in cols:
            v = r.get(c, "")
            s = "" if v is None else str(v)
            s = s.replace('"', '""')
            if "," in s or "\n" in s:
                s = '"' + s + '"'
            row.append(s)
        lines.append(",".join(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_csv(path: Path, results: list[dict[str, Any]]) -> None:
    cols = [
        "id",
        "trial",
        "repeats",
        "target_coq_file",
        "project",
        "steps",
        "success",
        "outcome",
        "outcome_detail",
        "post_copy_make_ok",
        "theorem_baseline_ok",
        "theorem_modified",
        "post_make_note",
        "elapsed_seconds",
        "agent_run_seconds",
        "tokens_prompt",
        "tokens_prompt_cache_hit",
        "tokens_prompt_cache_miss",
        "tokens_completion",
        "tokens_total",
    ]
    lines = [",".join(cols)]
    for r in results:
        row = []
        for c in cols:
            v = r.get(c, "")
            if c == "outcome_detail":
                s = _csv_detail_cell(v)
            else:
                s = "" if v is None else str(v)
            s = s.replace('"', '""')
            if "," in s or "\n" in s:
                s = '"' + s + '"'
            row.append(s)
        lines.append(",".join(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    default_testlist = DEFAULT_TESTLIST_PATH.resolve()
    default_parse = (_REPO_ROOT / "Sentence" / "vsrocq_split_sentences_Parcas").resolve()

    ap = argparse.ArgumentParser(description="Batch runner for ProofAgent on Evaluation/parcas TestList.json ids.")
    ap.add_argument(
        "--ids",
        type=int,
        nargs="*",
        default=None,
        help="Explicit catalog ids; if omitted, read Evaluation/parcas/TestList.json.",
    )
    ap.add_argument(
        "--testlist",
        type=Path,
        default=default_testlist,
        help="Path to fixed Evaluation/parcas/TestList.json (no random sampling).",
    )
    ap.add_argument(
        "--parcas-path",
        type=Path,
        default=None,
        help="Parcas repo root (default: env PARCAS_PATH).",
    )
    ap.add_argument(
        "--opam-switch",
        type=str,
        default=None,
        help="Opam switch for dune build / coqc (default: env PARCAS_OPAM_SWITCH or parcas).",
    )
    ap.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="parcas_catalog.json path.",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=AGENT_WORKSPACE_PARCAS,
        help="evaluation workspace agent root; each run adds <M-D-H-M_batch>/id_<n>/trial_<k>/.",
    )
    ap.add_argument(
        "--result-dir",
        type=Path,
        default=None,
        help="Batch result root: summary*.{csv,json} and id_<n>/trial_* logs. "
        "Default: Evaluation/parcas/Result/<M-D-H-M_batch>/",
    )
    ap.add_argument(
        "--batch-stamp",
        type=str,
        default=None,
        help="Override batch folder name (default: month-day-hour-minute_batch).",
    )
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Repeat each theorem this many times; each trial re-runs copy --force and a fresh ProofAgent run.",
    )
    ap.add_argument("--check-timeout-seconds", type=int, default=60)
    ap.add_argument("--run-timeout-seconds", type=int, default=1800)
    ap.add_argument(
        "--verify-make-timeout-seconds",
        type=int,
        default=180,
        help="Timeout (seconds) for post-copy build and final verify build (default: 180).",
    )
    ap.add_argument(
        "--dune-check-full-theory",
        action="store_true",
        help="Use full `make` / `dune build` for post-copy, agent check, and verify "
        "(default: `dune build <target>.vo` from catalog v_rel_path).",
    )
    ap.add_argument(
        "--extra-skip-keyword",
        action="append",
        default=[],
        help="Extra keyword to forbid outside comments (repeatable).",
    )
    ap.add_argument(
        "--extra-read",
        action="store_true",
        help="If set, write extraReadableRootPaths (OPAM Coq lib for the Parcas switch) into proofagent.config.json.",
    )
    ap.add_argument(
        "--proofagent-root",
        type=Path,
        default=_REPO_ROOT,
    )
    ap.add_argument(
        "--parse-sentence-script",
        type=str,
        default=str(default_parse),
        help="Shell command to split .v sentences (appended with quoted absolute path); empty disables check.",
    )
    ap.add_argument(
        "--parse-sentence-timeout-seconds",
        type=int,
        default=120,
        help="Timeout for parse sentence script per trial (default: 120).",
    )
    ap.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Full chat completions POST URL (host-only values are expanded to .../v1/chat/completions). "
        "Default: env BASE_URL / DEEPSEEK_BASE_URL / OPENROUTER_BASE_URL, else DeepSeek default.",
    )
    ap.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="LLM API key for run.sh (default: env LLM_API_KEY / DEEPSEEK_API_KEY / OPENROUTER_API_KEY).",
    )
    ap.add_argument(
        "--chat-model",
        type=str,
        default=_BATCH_CHAT_MODEL,
        help=f"Model id written to proofagent.config.json (default: {_BATCH_CHAT_MODEL}).",
    )
    ap.add_argument(
        "--reasoning-effort",
        type=str,
        default=_BATCH_REASONING_EFFORT,
        help="DeepSeek thinking.reasoning_effort written to proofagent.config.json "
        f"(default: {_BATCH_REASONING_EFFORT}).",
    )
    args = ap.parse_args()
    if int(args.repeats) < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return 2
    try:
        reasoning_effort = _normalize_reasoning_effort(str(args.reasoning_effort))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    testlist_path = args.testlist.resolve()
    default_repeats = int(args.repeats)
    run_specs: list[IdRunSpec]
    if args.ids is not None and len(args.ids) > 0:
        run_specs = [IdRunSpec(int(i), default_repeats) for i in args.ids]
    else:
        run_specs = read_run_specs_from_testlist_file(testlist_path, default_repeats=default_repeats)
    if not run_specs:
        print("No ids to run.", file=sys.stderr)
        return 2

    id_repeats = {spec.id_value: spec.repeats for spec in run_specs}
    ids = [spec.id_value for spec in run_specs]

    if (
        args.ids is None
        and cli_argv_includes_repeats_flag()
        and testlist_has_configured_repeats(testlist_path)
    ):
        _batch_log(
            "[batch]",
            "WARNING: testlist configures per-id repeats and CLI --repeats was also set; "
            "values from the testlist take precedence over --repeats.",
        )

    try:
        from parcas_testlist import resolve_parcas_path

        parcas_project_root = resolve_parcas_path(args.parcas_path)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    skip_keyword_scan_exclude_v_relpaths = collect_abort_file_rel_paths(parcas_project_root)

    proofagent_root = args.proofagent_root.resolve()
    try:
        llm_base_url = resolve_llm_base_url(args.base_url)
    except ValueError as exc:
        print(f"Invalid --base-url: {exc}", file=sys.stderr)
        return 2
    llm_api_key = resolve_llm_api_key(args.api_key)
    if not llm_api_key:
        print(
            "Missing LLM API key: set --api-key or LLM_API_KEY / DEEPSEEK_API_KEY / OPENROUTER_API_KEY.",
            file=sys.stderr,
        )
        return 2

    batch_stamp = (args.batch_stamp or "").strip() or make_batch_workspace_stamp()
    workspace_agent_root = args.out.resolve()
    workspace_batch_dir = (workspace_agent_root / batch_stamp).resolve()
    result_dir = args.result_dir
    if result_dir is None:
        result_dir = _EVAL_PARCAS_DIR / "Result" / batch_stamp
    result_dir = result_dir.resolve()

    try:
        parcas_opam_switch = resolve_parcas_opam_switch(args.opam_switch)
        readable_roots: list[str] = []
        if bool(args.extra_read):
            readable_roots = extra_readable_root_paths(parcas_opam_switch)
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    cfg = OneRunConfig(
        proofagent_root=proofagent_root,
        parcas_project_root=parcas_project_root,
        parcas_catalog=args.catalog.resolve(),
        workspace_agent_root=workspace_agent_root,
        workspace_batch_dir=workspace_batch_dir,
        result_dir=result_dir,
        check_timeout_seconds=int(args.check_timeout_seconds),
        run_timeout_seconds=int(args.run_timeout_seconds),
        verify_make_timeout_seconds=int(args.verify_make_timeout_seconds),
        extra_skip_keywords=list(args.extra_skip_keyword or []),
        skip_keyword_scan_exclude_v_relpaths=skip_keyword_scan_exclude_v_relpaths,
        repeats=default_repeats,
        id_repeats=id_repeats,
        chat_model=str(args.chat_model),
        reasoning_effort=reasoning_effort,
        parse_sentence_script=str(args.parse_sentence_script or ""),
        parse_sentence_timeout_seconds=int(args.parse_sentence_timeout_seconds),
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        parcas_opam_switch=parcas_opam_switch,
        parcas_dune_check_full_theory=bool(args.dune_check_full_theory),
        extra_readable_root_paths=readable_roots,
    )

    cfg.workspace_batch_dir.mkdir(parents=True, exist_ok=True)
    cfg.result_dir.mkdir(parents=True, exist_ok=True)

    if skip_keyword_scan_exclude_v_relpaths:
        _batch_log(
            "[batch]",
            "skip-keyword scan excludes Parcas .v files with upstream Abort: "
            + ", ".join(sorted(skip_keyword_scan_exclude_v_relpaths)),
        )

    try:
        _ensure_proofagent_built(proofagent_root)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    _batch_log("[batch]", "ProofAgent dotnet build ok (workers use run.sh --no-build)")

    _batch_log(
        "[batch]",
        f"config | parcas | ids={len(ids)} workers={args.workers} default_repeats={cfg.repeats} | "
        f"opam_switch={cfg.parcas_opam_switch} | "
        f"model={cfg.chat_model} reasoning_effort={cfg.reasoning_effort} extra_read={int(bool(args.extra_read))} | "
        f"base_url={cfg.llm_base_url} | "
        f"workspace_batch={cfg.workspace_batch_dir} | result_dir={cfg.result_dir} | "
        f"run_timeout={cfg.run_timeout_seconds}s | verify_make_timeout={cfg.verify_make_timeout_seconds}s | "
        f"dune_check={'full_theory' if cfg.parcas_dune_check_full_theory else 'target_vo'}",
    )
    _batch_log("[batch]", f"ids (first 20): {ids[:20]}{' ...' if len(ids) > 20 else ''}")
    if cfg.extra_readable_root_paths:
        _batch_log(
            "[batch]",
            "extra_readable_root_paths: " + ", ".join(cfg.extra_readable_root_paths),
        )

    results: list[dict[str, Any]] = []
    total_n = len(ids)
    interrupted = False

    try:
        if args.workers <= 1 or len(ids) == 1:
            for idx, i in enumerate(ids, start=1):
                _batch_log("[batch]", f"sequential progress {idx}/{len(ids)} | id={i}")
                results.append(_run_one_with_cfg(i, cfg))
                _flush_summary(cfg.result_dir, results, log_line=True, total_planned=total_n)
        else:
            with ProcessPoolExecutor(max_workers=int(args.workers)) as ex:
                futs = {ex.submit(_run_one_with_cfg, i, cfg): i for i in ids}
                _batch_log("[batch]", f"submitted {len(futs)} tasks (process pool); summary updates per completion")
                done_n = 0
                for fut in as_completed(futs):
                    rid = futs[fut]
                    try:
                        r = fut.result()
                    except Exception as e:
                        art = (cfg.result_dir / f"id_{rid}").resolve()
                        _ensure_dir(art)
                        r = {
                            "id": rid,
                            "repeats": cfg.repeats,
                            "trials": [],
                            "success": 0,
                            "success_count": 0,
                            "success_rate": 0.0,
                            "elapsed_seconds": 0,
                            "error": f"worker_exception: {e}",
                            "repo_dir": "",
                            "artifacts_dir": str(art),
                            "outcome": "worker_crash",
                            "outcome_detail": repr(e)[:800],
                        }
                        _write_json(art / "result.json", r)
                        _batch_log("[batch]", f"worker exception id={rid}: {e}")
                    results.append(r)
                    done_n += 1
                    _batch_log(
                        "[batch]",
                        f"progress {done_n}/{len(ids)} | done id={r.get('id')} | success={r.get('success')} | "
                        f"outcome={r.get('outcome', '')} | elapsed={r.get('elapsed_seconds')}s | project={r.get('project', '')}",
                    )
                    _flush_summary(cfg.result_dir, results, log_line=True, total_planned=total_n)
    except KeyboardInterrupt:
        interrupted = True
        _batch_log("[batch]", "KeyboardInterrupt: flushing summary for completed rows...")
    finally:
        if results:
            _flush_summary(cfg.result_dir, results, log_line=interrupted, total_planned=total_n)

    trial_rows = _flatten_trial_rows(results)
    ok_trials = sum(1 for r in trial_rows if int(r.get("success", 0) or 0) == 1)
    ok_ids = sum(1 for r in results if int(r.get("success", 0) or 0) == 1)
    _batch_log(
        "[batch]",
        f"{'interrupted, ' if interrupted else ''}done | trial_ok={ok_trials}/{len(trial_rows)} | "
        f"id_all_ok={ok_ids}/{len(results)} | summary: {cfg.result_dir / 'summary_trials.csv'}",
    )
    print(f"Wrote: {cfg.result_dir / 'summary_trials.csv'}")
    print(f"Wrote: {cfg.result_dir / 'summary_by_id.csv'}")
    return 0 if not interrupted else 130


if __name__ == "__main__":
    raise SystemExit(main())
