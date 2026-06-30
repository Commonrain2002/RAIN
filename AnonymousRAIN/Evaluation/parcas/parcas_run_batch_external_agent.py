#!/usr/bin/env python3
"""Parcas batch runner for OpenCode or Claude Code (same copy/build/meta as ProofAgent Parcas)."""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_EVAL_PARCAS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_PARCAS_DIR.parents[1]
_EVAL_DIR = _REPO_ROOT / "Evaluation"
_EVAL_OPENCODE_DIR = _EVAL_DIR / "opencode"
_EVAL_CLAUDE_DIR = _EVAL_DIR / "claude"
for path in (_EVAL_PARCAS_DIR, _EVAL_DIR, _EVAL_OPENCODE_DIR, _EVAL_CLAUDE_DIR, _REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import importlib.util

def _load_parcas_proofagent_run_batch_module():
    module_path = _EVAL_PARCAS_DIR / "run_batch.py"
    module_name = "parcas_proofagent_run_batch"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Parcas ProofAgent batch module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_parcas_proofagent_batch = _load_parcas_proofagent_run_batch_module()
from batch_workspace_layout import (
    AGENT_WORKSPACE_PARCAS_CLAUDE,
    AGENT_WORKSPACE_PARCAS_OPENCODE,
    make_batch_workspace_stamp,
    trial_workspace_parent,
)
from opencode_model_presets import resolve_opencode_model_settings
from opencode_token_log import resolve_opencode_token_usage
from claude_token_log import resolve_claude_token_usage

from BatchTest.agent_run_seconds_backfill import apply_measured_agent_run_seconds
from BatchTest.post_copy_make import run_post_copy_make_with_retries
from BatchTest.testlist_run_specs import IdRunSpec, repeats_for_id
from BatchTest.theorem_integrity import capture_theorem_baseline, check_theorem_modified_after_agent
from parcas_batch_env import resolve_parcas_opam_switch
from parcas_batch_user_message import format_parcas_batch_user_message
from parcas_eval_build_files import parcas_eval_build_shell_command
from parcas_testlist import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_TESTLIST_PATH,
    cli_argv_includes_repeats_flag,
    collect_abort_file_rel_paths,
    read_run_specs_from_testlist_file,
    resolve_parcas_path,
    testlist_has_configured_repeats,
)

AgentKind = Literal["opencode", "claude"]

_DEFAULT_OPENCODE_MODEL = "deepseek/deepseek-v4-flash"
_DEFAULT_OPENCODE_VARIANT = "max"
_DEFAULT_CLAUDE_MODEL = "deepseek-v4-flash[1m]"
_DEFAULT_CLAUDE_EFFORT = "max"


@dataclass(frozen=True)
class ExternalAgentRunConfig:
    agent_kind: AgentKind
    proofagent_root: Path
    parcas_project_root: Path
    parcas_catalog: Path
    workspace_agent_root: Path
    workspace_batch_dir: Path
    result_dir: Path
    check_timeout_seconds: int
    run_timeout_seconds: int
    verify_make_timeout_seconds: int
    extra_skip_keywords: list[str]
    skip_keyword_scan_exclude_v_relpaths: frozenset[str]
    repeats: int
    id_repeats: dict[int, int]
    parse_sentence_script: str
    parse_sentence_timeout_seconds: int
    parcas_opam_switch: str
    parcas_dune_check_full_theory: bool
    opencode_bin: str
    opencode_model: str
    opencode_variant: str
    opencode_preset: str | None
    opencode_skip_permissions: bool
    claude_bin: str
    claude_model: str
    claude_effort: str
    claude_skip_permissions: bool


def _sum_optional_tokens(*values: int | None) -> int | None:
    if all(v is None for v in values):
        return None
    return sum(int(v) for v in values if v is not None)


def _run_one_trial(
    id_value: int,
    trial_index: int,
    repeat_total: int,
    cfg: ExternalAgentRunConfig,
    meta: dict[str, Any],
    project_name: str,
    repo_dir: Path,
    copy_parent: Path,
    trial_artifacts_dir: Path,
    parent_tag: str,
) -> dict[str, Any]:
    t0 = time.monotonic()
    tag = f"{parent_tag} trial={trial_index}/{repeat_total}"
    _parcas_proofagent_batch._ensure_dir(trial_artifacts_dir)

    v_rel_path = str(meta.get("v_rel_path") or "").strip()
    user_message = format_parcas_batch_user_message(v_rel_path or "(unknown target file)")
    _parcas_proofagent_batch._write_text(trial_artifacts_dir / "user_message.txt", user_message + "\n")

    copy_script = _parcas_proofagent_batch._parcas_minimal_copy_script()
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
    copy_rc, copy_out, copy_err, copy_timed_out = _parcas_proofagent_batch._run_capture(
        copy_cmd, cwd=cfg.proofagent_root, env=None, timeout_seconds=600
    )
    _parcas_proofagent_batch._write_text(trial_artifacts_dir / "copy_stdout.log", copy_out)
    _parcas_proofagent_batch._write_text(trial_artifacts_dir / "copy_stderr.log", copy_err)
    _parcas_proofagent_batch._batch_log(tag, f"copy done | rc={copy_rc} | timed_out={int(copy_timed_out)}")

    post_copy_make_rc: int | None = None
    post_copy_make_timed_out = False
    post_copy_make_ok: int | None = None
    post_make_note = ""
    skip_reason: str | None = None
    theorem_baseline_ok = 0
    theorem_baseline_error: str | None = None
    theorem_proposition_text: str | None = None
    theorem_modified = 0
    trial_check_shell = ""

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
                from parcas_batch_env import build_check_shell

                trial_check_shell = build_check_shell(
                    cfg.parcas_opam_switch,
                    v_rel_path,
                    full_theory=True,
                )
            else:
                trial_check_shell = parcas_eval_build_shell_command(repo_dir)
            _parcas_proofagent_batch._batch_log(tag, f"check build shell | {trial_check_shell}")
        except (ValueError, FileNotFoundError) as exc:
            skip_reason = "copy_failed"
            theorem_baseline_error = f"check build shell: {exc}"
            _parcas_proofagent_batch._batch_log(tag, f"check build shell failed | {exc}")

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
                _parcas_proofagent_batch._batch_log(
                    tag,
                    f"theorem baseline ok | len={baseline.proposition_len} | "
                    f"hash={baseline.collapsed_hash_prefix}",
                )
            else:
                skip_reason = "theorem_baseline_failed"
                theorem_baseline_error = baseline.error or "theorem baseline capture failed"
                _parcas_proofagent_batch._batch_log(tag, f"theorem baseline failed | {theorem_baseline_error}")

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
        _parcas_proofagent_batch._write_text(
            trial_artifacts_dir / "post_copy_make_stdout.log", post_copy_make_out
        )
        _parcas_proofagent_batch._write_text(
            trial_artifacts_dir / "post_copy_make_stderr.log", post_copy_make_err
        )
        post_copy_make_ok = 1 if (not post_copy_make_timed_out and post_copy_make_rc == 0) else 0
        if post_copy_make_ok == 0:
            post_make_note = "post_make_nonzero"
            _parcas_proofagent_batch._batch_log(
                tag,
                f"post-copy make failed (continuing agent) | rc={post_copy_make_rc} | "
                f"timed_out={int(post_copy_make_timed_out)} | attempts={post_copy_result.attempts_summary}",
            )
        else:
            _parcas_proofagent_batch._batch_log(
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
    claude_session_id = ""

    if skip_reason is None:
        if cfg.agent_kind == "opencode":
            _parcas_proofagent_batch._batch_log(
                tag,
                f"OpenCode start | model={cfg.opencode_model} variant={cfg.opencode_variant} | "
                f"run_timeout={cfg.run_timeout_seconds}s",
            )
            run_cmd = [
                "timeout",
                str(cfg.run_timeout_seconds),
                cfg.opencode_bin,
                "run",
                "--dir",
                str(repo_dir),
                "-m",
                cfg.opencode_model,
                "--variant",
                cfg.opencode_variant,
                "--format",
                "json",
            ]
            if cfg.opencode_skip_permissions:
                run_cmd.append("--dangerously-skip-permissions")
            run_cmd.append(user_message)
            agent_t0 = time.monotonic()
            run_rc, run_out, run_err, run_timed_out = _parcas_proofagent_batch._run_capture(
                run_cmd, cwd=repo_dir, env=None, timeout_seconds=cfg.run_timeout_seconds + 30
            )
            _parcas_proofagent_batch._batch_log(
                tag, f"OpenCode end | rc={run_rc} | timed_out={int(run_timed_out)}"
            )
        else:
            claude_session_id = str(uuid.uuid4())
            _parcas_proofagent_batch._write_text(
                trial_artifacts_dir / "claude_session_id.txt", claude_session_id + "\n"
            )
            _parcas_proofagent_batch._batch_log(
                tag,
                f"Claude start | model={cfg.claude_model} effort={cfg.claude_effort} | "
                f"session={claude_session_id} | run_timeout={cfg.run_timeout_seconds}s",
            )
            run_cmd = [
                "timeout",
                str(cfg.run_timeout_seconds),
                cfg.claude_bin,
                "-p",
                "--output-format",
                "json",
                "--session-id",
                claude_session_id,
                "--model",
                cfg.claude_model,
                "--effort",
                cfg.claude_effort,
            ]
            if cfg.claude_skip_permissions:
                run_cmd.append("--dangerously-skip-permissions")
            run_cmd.append(user_message)
            agent_t0 = time.monotonic()
            run_rc, run_out, run_err, run_timed_out = _parcas_proofagent_batch._run_capture(
                run_cmd, cwd=repo_dir, env=None, timeout_seconds=cfg.run_timeout_seconds + 30
            )
            _parcas_proofagent_batch._batch_log(
                tag, f"Claude end | rc={run_rc} | timed_out={int(run_timed_out)}"
            )

        _parcas_proofagent_batch._write_text(trial_artifacts_dir / "run_stdout.log", run_out)
        _parcas_proofagent_batch._write_text(trial_artifacts_dir / "run_stderr.log", run_err)

        make_rc, make_out, make_err, make_timed_out = _parcas_proofagent_batch._run_build_shell(
            trial_check_shell,
            repo_dir if repo_dir.exists() else None,
            cfg.verify_make_timeout_seconds,
        )
        _parcas_proofagent_batch._write_text(trial_artifacts_dir / "verify_make_stdout.log", make_out)
        _parcas_proofagent_batch._write_text(trial_artifacts_dir / "verify_make_stderr.log", make_err)
        _parcas_proofagent_batch._batch_log(
            tag, f"final verify build | rc={make_rc} | timed_out={int(make_timed_out)}"
        )

        skip_hits = (
            _parcas_proofagent_batch._scan_repo_for_skip_keywords(
                repo_dir,
                extra_keywords=cfg.extra_skip_keywords,
                exclude_v_rel_paths=cfg.skip_keyword_scan_exclude_v_relpaths,
            )
            if repo_dir.exists()
            else {}
        )
        if skip_hits:
            _parcas_proofagent_batch._batch_log(tag, f"skip-keyword hits | files={len(skip_hits)}")
        else:
            _parcas_proofagent_batch._batch_log(tag, "skip-keyword scan | no hits")

        if theorem_proposition_text:
            preserved, integrity_err = check_theorem_modified_after_agent(
                repo_dir,
                v_rel_path,
                theorem_proposition_text,
            )
            if not preserved:
                theorem_modified = 1
                _parcas_proofagent_batch._batch_log(
                    tag, f"theorem integrity fail | {integrity_err or 'theorem modified'}"
                )
            else:
                _parcas_proofagent_batch._batch_log(tag, "theorem integrity ok")
    else:
        agent_label = "OpenCode" if cfg.agent_kind == "opencode" else "Claude"
        _parcas_proofagent_batch._batch_log(tag, f"skip {agent_label} / verify | skip_reason={skip_reason}")
        note = (
            f"later steps skipped: {skip_reason}\n"
            f"copy_rc={copy_rc} copy_timed_out={int(copy_timed_out)}\n"
        )
        _parcas_proofagent_batch._write_text(trial_artifacts_dir / "run_stdout.log", note)
        _parcas_proofagent_batch._write_text(trial_artifacts_dir / "run_stderr.log", "")
        _parcas_proofagent_batch._write_text(trial_artifacts_dir / "verify_make_stdout.log", "")
        _parcas_proofagent_batch._write_text(
            trial_artifacts_dir / "verify_make_stderr.log", "verify_make skipped.\n"
        )

    parsed_tokens: Any = None
    opencode_session_id = ""
    if cfg.agent_kind == "opencode":
        parsed_tokens, opencode_session_id = resolve_opencode_token_usage(run_out, run_err)
    else:
        if not claude_session_id:
            sid_path = trial_artifacts_dir / "claude_session_id.txt"
            if sid_path.is_file():
                claude_session_id = sid_path.read_text(encoding="utf-8").strip()
        parsed_tokens = resolve_claude_token_usage(
            run_out,
            run_err,
            repo_dir=repo_dir,
            session_id=claude_session_id,
        )

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

    completion_tokens = (
        _sum_optional_tokens(parsed_tokens.completion, getattr(parsed_tokens, "reasoning", None))
        if parsed_tokens is not None
        else None
    )

    trial_result: dict[str, Any] = {
        "id": id_value,
        "trial": trial_index,
        "repeats": repeat_total,
        "target_coq_file": v_rel_path,
        "project": meta.get("project"),
        "steps": meta.get("step_count"),
        "agent_backend": cfg.agent_kind,
        "success": success,
        "elapsed_seconds": elapsed,
        "tokens_prompt": parsed_tokens.prompt if parsed_tokens else None,
        "tokens_prompt_cache_hit": parsed_tokens.prompt_cache_hit if parsed_tokens else None,
        "tokens_prompt_cache_miss": parsed_tokens.prompt_cache_miss if parsed_tokens else None,
        "tokens_completion": completion_tokens,
        "tokens_total": parsed_tokens.total if parsed_tokens else None,
        "tokens_parse_source": parsed_tokens.source if parsed_tokens else None,
        "repo_dir": str(repo_dir),
        "workspace_trial_dir": str(copy_parent.resolve()),
        "workspace_snapshot_dir": str(repo_dir.resolve()) if repo_dir.is_dir() else None,
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
        "run_stderr_nonempty": _parcas_proofagent_batch._run_stderr_nonempty_flag(run_err, skip_reason),
        "run_stderr_preview": _parcas_proofagent_batch._run_stderr_preview(run_err, skip_reason),
        "verify_make_rc": make_rc,
        "verify_make_timed_out": int(make_timed_out),
        "skip_keyword_hits": skip_hits,
        "theorem_baseline_ok": theorem_baseline_ok,
        "theorem_baseline_error": theorem_baseline_error,
        "theorem_modified": theorem_modified,
        "theorem_proposition_len": len(theorem_proposition_text) if theorem_proposition_text else None,
        "parcas_opam_switch": cfg.parcas_opam_switch,
    }
    if cfg.agent_kind == "opencode":
        trial_result["opencode_model"] = cfg.opencode_model
        trial_result["opencode_variant"] = cfg.opencode_variant
        trial_result["opencode_preset"] = cfg.opencode_preset or ""
        trial_result["opencode_session_id"] = opencode_session_id or ""
        if parsed_tokens and getattr(parsed_tokens, "reasoning", None) is not None:
            trial_result["tokens_reasoning"] = parsed_tokens.reasoning
    else:
        trial_result["claude_model"] = cfg.claude_model
        trial_result["claude_effort"] = cfg.claude_effort
        trial_result["claude_session_id"] = claude_session_id

    apply_measured_agent_run_seconds(trial_result, agent_t0=agent_t0)
    _parcas_proofagent_batch._derive_outcome(trial_result)
    _parcas_proofagent_batch._write_json(trial_artifacts_dir / "result.json", trial_result)
    _parcas_proofagent_batch._batch_log(
        tag,
        f"trial end | success={success} | outcome={trial_result.get('outcome')} | elapsed={elapsed}s",
    )
    return trial_result


def _run_one(id_value: int, cfg: ExternalAgentRunConfig, *, repeat_total: int) -> dict[str, Any]:
    t0 = time.monotonic()
    tag = f"[id={id_value}]"
    artifacts_dir = (cfg.result_dir / f"id_{id_value}").resolve()
    _parcas_proofagent_batch._ensure_dir(artifacts_dir)
    _parcas_proofagent_batch._batch_log(
        tag,
        f"start | workspace_batch={cfg.workspace_batch_dir} | logs={artifacts_dir}",
    )

    meta_cmd = [
        "python3",
        str(_parcas_proofagent_batch._parcas_meta_script()),
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
    meta_rc, meta_out, meta_err, meta_timed_out = _parcas_proofagent_batch._run_capture(
        meta_cmd, cwd=cfg.proofagent_root, env=None, timeout_seconds=180
    )
    _parcas_proofagent_batch._write_text(artifacts_dir / "meta_stdout.log", meta_out)
    _parcas_proofagent_batch._write_text(artifacts_dir / "meta_stderr.log", meta_err)

    meta: dict[str, Any] | None = None
    meta_error: str | None = None
    if meta_rc == 0 and not meta_timed_out:
        try:
            meta = _parcas_proofagent_batch._parse_last_json_line(meta_out)
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
        _parcas_proofagent_batch._write_json(artifacts_dir / "result.json", result)
        _parcas_proofagent_batch._batch_log(
            tag, f"end | success=0 | outcome=meta_failed | {meta_error} | {elapsed}s"
        )
        return result

    _parcas_proofagent_batch._write_json(artifacts_dir / "meta.json", meta)
    project_name = str(meta.get("project") or "").strip()
    if not project_name:
        elapsed = int(time.monotonic() - t0)
        result = {
            "id": id_value,
            "success": 0,
            "elapsed_seconds": elapsed,
            "error": "meta missing project name",
            "artifacts_dir": str(artifacts_dir),
            "outcome": "meta_failed",
            "outcome_detail": "meta missing project",
        }
        _parcas_proofagent_batch._write_json(artifacts_dir / "result.json", result)
        _parcas_proofagent_batch._batch_log(
            tag, f"end | success=0 | outcome=meta_failed | missing project | {elapsed}s"
        )
        return result

    _parcas_proofagent_batch._batch_log(
        tag,
        f"meta done | project={project_name} | steps={meta.get('step_count')} | "
        f"v={meta.get('v_rel_path')} | opam_switch={cfg.parcas_opam_switch}",
    )

    trials: list[dict[str, Any]] = []
    repo_dir = Path()
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

    stats = _parcas_proofagent_batch._aggregate_trial_stats(trials)
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
    _parcas_proofagent_batch._write_json(artifacts_dir / "aggregate.json", aggregate)
    _parcas_proofagent_batch._write_json(artifacts_dir / "result.json", aggregate)
    _parcas_proofagent_batch._batch_log(
        tag,
        f"end | repeats={repeat_total} | trial_ok={stats['success_count']}/{stats['trial_count']} | "
        f"success_rate={stats['success_rate']:.2f} | elapsed={elapsed}s",
    )
    return aggregate


def _run_one_with_cfg(id_value: int, cfg: ExternalAgentRunConfig) -> dict[str, Any]:
    repeat_total = repeats_for_id(
        default_repeats=cfg.repeats,
        id_repeats=cfg.id_repeats,
        id_value=id_value,
    )
    return _run_one(id_value, cfg, repeat_total=repeat_total)


def main(agent_kind: AgentKind) -> int:
    default_testlist = DEFAULT_TESTLIST_PATH.resolve()
    default_parse = (_REPO_ROOT / "Sentence" / "vsrocq_split_sentences_Parcas").resolve()
    agent_label = "OpenCode" if agent_kind == "opencode" else "Claude"
    default_workspace = (
        AGENT_WORKSPACE_PARCAS_OPENCODE if agent_kind == "opencode" else AGENT_WORKSPACE_PARCAS_CLAUDE
    )
    default_result_parent = _EVAL_PARCAS_DIR / agent_kind / "Result"

    ap = argparse.ArgumentParser(
        description=f"Parcas batch runner ({agent_label} + DeepSeek, same opam switch as Evaluation/parcas)."
    )
    ap.add_argument("--ids", type=int, nargs="*", default=None)
    ap.add_argument("--testlist", type=Path, default=default_testlist)
    ap.add_argument("--parcas-path", type=Path, default=None)
    ap.add_argument("--opam-switch", type=str, default=None)
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    ap.add_argument("--out", type=Path, default=default_workspace)
    ap.add_argument("--result-dir", type=Path, default=None)
    ap.add_argument("--batch-stamp", type=str, default=None)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--check-timeout-seconds", type=int, default=60)
    ap.add_argument("--run-timeout-seconds", type=int, default=1800)
    ap.add_argument("--verify-make-timeout-seconds", type=int, default=180)
    ap.add_argument(
        "--dune-check-full-theory",
        action="store_true",
        help="Full dune build for post-copy and verify (default: target .vo).",
    )
    ap.add_argument("--extra-skip-keyword", action="append", default=[])
    ap.add_argument("--proofagent-root", type=Path, default=_REPO_ROOT)
    ap.add_argument("--parse-sentence-script", type=str, default=str(default_parse))
    ap.add_argument("--parse-sentence-timeout-seconds", type=int, default=120)
    if agent_kind == "opencode":
        ap.add_argument("--opencode-bin", type=str, default="opencode")
        ap.add_argument(
            "--opencode-preset",
            type=str,
            default="deepseek-v4-flash",
            help="Named preset (overridden by explicit --opencode-model / --opencode-variant).",
        )
        ap.add_argument("--opencode-model", type=str, default=_DEFAULT_OPENCODE_MODEL)
        ap.add_argument("--opencode-variant", type=str, default=_DEFAULT_OPENCODE_VARIANT)
        ap.add_argument(
            "--opencode-skip-permissions",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
    else:
        ap.add_argument("--claude-bin", type=str, default="claude")
        ap.add_argument("--claude-model", type=str, default=_DEFAULT_CLAUDE_MODEL)
        ap.add_argument("--claude-effort", type=str, default=_DEFAULT_CLAUDE_EFFORT)
        ap.add_argument(
            "--claude-skip-permissions",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
    args = ap.parse_args()

    if int(args.repeats) < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return 2

    try:
        parcas_project_root = resolve_parcas_path(args.parcas_path)
        parcas_opam_switch = resolve_parcas_opam_switch(args.opam_switch)
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    skip_keyword_scan_exclude_v_relpaths = collect_abort_file_rel_paths(parcas_project_root)

    default_repeats = int(args.repeats)
    if args.ids is not None and len(args.ids) > 0:
        run_specs = [IdRunSpec(int(i), default_repeats) for i in args.ids]
    else:
        run_specs = read_run_specs_from_testlist_file(
            args.testlist.resolve(),
            default_repeats=default_repeats,
        )
    if not run_specs:
        print("No ids to run.", file=sys.stderr)
        return 2
    ids = [s.id_value for s in run_specs]
    id_repeats = {s.id_value: s.repeats for s in run_specs}

    if (
        args.ids is None
        and cli_argv_includes_repeats_flag()
        and testlist_has_configured_repeats(args.testlist.resolve())
    ):
        _parcas_proofagent_batch._batch_log(
            "[batch]",
            "WARNING: testlist configures per-id repeats and CLI --repeats was also set; "
            "values from the testlist take precedence over --repeats.",
        )

    proofagent_root = args.proofagent_root.resolve()
    batch_stamp = (args.batch_stamp or "").strip() or make_batch_workspace_stamp()
    workspace_batch_dir = (args.out.resolve() / batch_stamp).resolve()
    result_dir = args.result_dir
    if result_dir is None:
        result_dir = (default_result_parent / batch_stamp).resolve()
    else:
        result_dir = result_dir.resolve()

    opencode_model = _DEFAULT_OPENCODE_MODEL
    opencode_variant = _DEFAULT_OPENCODE_VARIANT
    opencode_preset: str | None = None
    if agent_kind == "opencode":
        try:
            opencode_model, opencode_variant, opencode_preset = resolve_opencode_model_settings(
                str(args.opencode_preset),
                str(args.opencode_model),
                str(args.opencode_variant),
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    cfg = ExternalAgentRunConfig(
        agent_kind=agent_kind,
        proofagent_root=proofagent_root,
        parcas_project_root=parcas_project_root,
        parcas_catalog=args.catalog.resolve(),
        workspace_agent_root=args.out.resolve(),
        workspace_batch_dir=workspace_batch_dir,
        result_dir=result_dir,
        check_timeout_seconds=int(args.check_timeout_seconds),
        run_timeout_seconds=int(args.run_timeout_seconds),
        verify_make_timeout_seconds=int(args.verify_make_timeout_seconds),
        extra_skip_keywords=list(args.extra_skip_keyword or []),
        skip_keyword_scan_exclude_v_relpaths=skip_keyword_scan_exclude_v_relpaths,
        repeats=default_repeats,
        id_repeats=id_repeats,
        parse_sentence_script=str(args.parse_sentence_script or ""),
        parse_sentence_timeout_seconds=int(args.parse_sentence_timeout_seconds),
        parcas_opam_switch=parcas_opam_switch,
        parcas_dune_check_full_theory=bool(args.dune_check_full_theory),
        opencode_bin=str(args.opencode_bin) if agent_kind == "opencode" else "opencode",
        opencode_model=opencode_model,
        opencode_variant=opencode_variant,
        opencode_preset=opencode_preset,
        opencode_skip_permissions=bool(args.opencode_skip_permissions) if agent_kind == "opencode" else True,
        claude_bin=str(args.claude_bin) if agent_kind == "claude" else "claude",
        claude_model=str(args.claude_model) if agent_kind == "claude" else _DEFAULT_CLAUDE_MODEL,
        claude_effort=str(args.claude_effort) if agent_kind == "claude" else _DEFAULT_CLAUDE_EFFORT,
        claude_skip_permissions=bool(args.claude_skip_permissions) if agent_kind == "claude" else True,
    )

    cfg.workspace_batch_dir.mkdir(parents=True, exist_ok=True)
    cfg.result_dir.mkdir(parents=True, exist_ok=True)

    if skip_keyword_scan_exclude_v_relpaths:
        _parcas_proofagent_batch._batch_log(
            "[batch]",
            "skip-keyword scan excludes Parcas .v files with upstream Abort: "
            + ", ".join(sorted(skip_keyword_scan_exclude_v_relpaths)),
        )

    model_line = (
        f"preset={cfg.opencode_preset or '-'} model={cfg.opencode_model} variant={cfg.opencode_variant}"
        if agent_kind == "opencode"
        else f"model={cfg.claude_model} effort={cfg.claude_effort}"
    )
    _parcas_proofagent_batch._batch_log(
        "[batch]",
        f"config | parcas-{agent_kind} | ids={len(ids)} workers={args.workers} repeats={cfg.repeats} | "
        f"opam_switch={cfg.parcas_opam_switch} | {model_line} | "
        f"workspace_batch={cfg.workspace_batch_dir} | result_dir={cfg.result_dir} | "
        f"run_timeout={cfg.run_timeout_seconds}s | verify_timeout={cfg.verify_make_timeout_seconds}s | "
        f"dune_check={'full_theory' if cfg.parcas_dune_check_full_theory else 'target_vo'}",
    )
    _parcas_proofagent_batch._batch_log(
        "[batch]", f"ids (first 20): {ids[:20]}{' ...' if len(ids) > 20 else ''}"
    )

    results: list[dict[str, Any]] = []
    total_n = len(ids)
    interrupted = False
    try:
        if args.workers <= 1 or len(ids) == 1:
            for idx, id_value in enumerate(ids, start=1):
                _parcas_proofagent_batch._batch_log(
                    "[batch]", f"sequential progress {idx}/{len(ids)} | id={id_value}"
                )
                results.append(_run_one_with_cfg(id_value, cfg))
                _parcas_proofagent_batch._flush_summary(
                    cfg.result_dir, results, log_line=True, total_planned=total_n
                )
        else:
            with ProcessPoolExecutor(max_workers=int(args.workers)) as executor:
                futures = {executor.submit(_run_one_with_cfg, i, cfg): i for i in ids}
                _parcas_proofagent_batch._batch_log(
                    "[batch]",
                    f"submitted {len(futures)} tasks (process pool); summary updates per completion",
                )
                done_n = 0
                for future in as_completed(futures):
                    rid = futures[future]
                    try:
                        row = future.result()
                    except Exception as exc:
                        art = (cfg.result_dir / f"id_{rid}").resolve()
                        _parcas_proofagent_batch._ensure_dir(art)
                        row = {
                            "id": rid,
                            "success": 0,
                            "error": str(exc),
                            "outcome": "worker_exception",
                            "outcome_detail": str(exc)[:400],
                        }
                        _parcas_proofagent_batch._write_json(art / "result.json", row)
                    results.append(row)
                    done_n += 1
                    _parcas_proofagent_batch._batch_log("[batch]", f"completed {done_n}/{total_n} | id={rid}")
                    _parcas_proofagent_batch._flush_summary(
                        cfg.result_dir, results, log_line=False, total_planned=total_n
                    )
    except KeyboardInterrupt:
        interrupted = True
        _parcas_proofagent_batch._batch_log("[batch]", "interrupted (KeyboardInterrupt)")

    _parcas_proofagent_batch._flush_summary(cfg.result_dir, results, log_line=True, total_planned=total_n)
    ok = sum(1 for r in results if int(r.get("success", 0) or 0) == 1)
    _parcas_proofagent_batch._batch_log(
        "[batch]",
        f"done | ids={len(results)} id_success={ok}/{len(results)} | interrupted={int(interrupted)} | "
        f"result_dir={cfg.result_dir}",
    )
    return 130 if interrupted else 0
