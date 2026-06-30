#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EVAL_OPENCODE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_OPENCODE_DIR.parents[1]
_EVAL_DIR = _EVAL_OPENCODE_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_EVAL_OPENCODE_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_OPENCODE_DIR))
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from BatchTest.agent_run_seconds_backfill import apply_measured_agent_run_seconds
from BatchTest.batch_workspace_layout import (
    AGENT_WORKSPACE_OPENCODE,
    make_batch_workspace_stamp,
    trial_workspace_parent,
)
from BatchTest.coq_strip_comments import find_skip_keywords, strip_coq_comments
from BatchTest.eval_paths import coqstoq_meta_script
from BatchTest.post_copy_make import run_post_copy_make_with_retries
from BatchTest.testlist_run_specs import (
    IdRunSpec,
    format_default_repeats_log,
    read_run_specs_from_testlist,
    repeats_for_id,
)
from BatchTest.theorem_integrity import (
    capture_theorem_baseline,
    check_theorem_modified_after_agent,
)
from opencode_model_presets import list_opencode_preset_keys, resolve_opencode_model_settings
from opencode_token_log import resolve_opencode_token_usage

_OPENCODE_BIN = "opencode"
_OPENCODE_MODEL = "deepseek/deepseek-v4-flash"
_OPENCODE_VARIANT = "max"

_BATCH_USER_MESSAGE_TEMPLATE = (
    "In {target_coq_file}, there is a theorem containing Admitted. Complete the theorem such that "
    "running make in the project root directory succeeds. Note that you must not modify the statements "
    "of the theorems, and you are not allowed to use Admitted, Abort, Axiom, or similar constructs to "
    "bypass the proofs. You may only access the current project; access to any other local files or "
    "external resources, including the internet, is strictly prohibited. I am testing your proving ability, "
    "so do not attempt to look for answers elsewhere. All responses must be in English. Finally, only "
    'output: whether it is successful. If successful, provide the generated proofs; if failed, only output '
    '"failed".'
)


def _format_batch_user_message(target_coq_file: str) -> str:
    return _BATCH_USER_MESSAGE_TEMPLATE.format(target_coq_file=target_coq_file)


def _batch_log(prefix: str, message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} {prefix} {message}", flush=True)


def _parse_last_json_line(stdout: str) -> dict[str, Any]:
    # coqstoq_meta may print diagnostics; JSON is the last line in our meta tool.
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("{") and ln.endswith("}"):
            return json.loads(ln)
    raise ValueError("no JSON line found in meta output")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


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


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sum_optional_tokens(*values: int | None) -> int | None:
    if all(v is None for v in values):
        return None
    return sum(int(v or 0) for v in values)


def _scan_repo_for_skip_keywords(repo_dir: Path, extra_keywords: list[str] | None) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for root, _, files in os.walk(repo_dir):
        for fn in files:
            if not fn.endswith(".v"):
                continue
            fp = Path(root) / fn
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            no_comments = strip_coq_comments(text)
            kws = find_skip_keywords(no_comments, extra_keywords=extra_keywords)
            if kws:
                rel = fp.relative_to(repo_dir).as_posix()
                hits[rel] = kws
    return hits


@dataclass(frozen=True)
class OneRunConfig:
    proofagent_root: Path
    coqstoq_path: Path | None
    """Agent home under evaluation workspace, under RAIN_EVAL_WORKSPACE/AgentTest_opencode."""
    workspace_agent_root: Path
    """This run: ``<agent_root>/<M-D-H-M_batch>/id_<n>/trial_<k>/`` project copies."""
    workspace_batch_dir: Path
    """Summary CSV/JSON and per-id logs (stdout/stderr, result.json)."""
    result_dir: Path
    split: str
    check_timeout_seconds: int
    run_timeout_seconds: int
    verify_make_timeout_seconds: int
    extra_skip_keywords: list[str]
    repeats: int
    """Default trial count when a testlist entry omits repeats or --ids is used."""
    id_repeats: dict[int, int]
    opencode_bin: str
    opencode_model: str
    opencode_variant: str
    opencode_preset: str | None
    opencode_skip_permissions: bool
    parse_sentence_script: str
    parse_sentence_timeout_seconds: int


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
    user_message = _format_batch_user_message(v_rel_path or "(unknown target file)")
    _write_text(trial_artifacts_dir / "user_message.txt", user_message + "\n")

    copy_script = (cfg.proofagent_root / "scripts" / "coqstoq_minimal_copy.py").resolve()
    copy_cmd = [
        "python3",
        str(copy_script),
        str(id_value),
        "--split",
        cfg.split,
        "-o",
        str(copy_parent),
        "--force",
    ]
    if cfg.coqstoq_path is not None:
        copy_cmd += ["--coqstoq-path", str(cfg.coqstoq_path.resolve())]
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
        post_copy_result = run_post_copy_make_with_retries(repo_dir, cfg.verify_make_timeout_seconds)
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
        run_rc, run_out, run_err, run_timed_out = _run_capture(
            run_cmd, cwd=repo_dir, env=None, timeout_seconds=cfg.run_timeout_seconds + 30
        )
        _write_text(trial_artifacts_dir / "run_stdout.log", run_out)
        _write_text(trial_artifacts_dir / "run_stderr.log", run_err)
        _batch_log(tag, f"OpenCode end | rc={run_rc} | timed_out={int(run_timed_out)}")

        make_rc, make_out, make_err, make_timed_out = _run_capture(
            ["timeout", str(cfg.verify_make_timeout_seconds), "make", "-j1"],
            cwd=repo_dir if repo_dir.exists() else None,
            env=None,
            timeout_seconds=cfg.verify_make_timeout_seconds + 10,
        )
        _write_text(trial_artifacts_dir / "verify_make_stdout.log", make_out)
        _write_text(trial_artifacts_dir / "verify_make_stderr.log", make_err)
        _batch_log(tag, f"final verify make | rc={make_rc} | timed_out={int(make_timed_out)}")

        skip_hits = (
            _scan_repo_for_skip_keywords(repo_dir, extra_keywords=cfg.extra_skip_keywords)
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
        _batch_log(tag, f"skip OpenCode / verify | skip_reason={skip_reason}")
        note = (
            f"later steps skipped: {skip_reason}\n"
            f"copy_rc={copy_rc} copy_timed_out={int(copy_timed_out)}\n"
        )
        _write_text(trial_artifacts_dir / "run_stdout.log", note)
        _write_text(trial_artifacts_dir / "run_stderr.log", "")
        _write_text(trial_artifacts_dir / "verify_make_stdout.log", "")
        _write_text(trial_artifacts_dir / "verify_make_stderr.log", "verify_make skipped.\n")

    parsed_tokens, opencode_session_id = resolve_opencode_token_usage(run_out, run_err)
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
    completion_with_reasoning = _sum_optional_tokens(parsed_tokens.completion, parsed_tokens.reasoning)

    trial_result: dict[str, Any] = {
        "id": id_value,
        "trial": trial_index,
        "repeats": repeat_total,
        "target_coq_file": v_rel_path,
        "project": meta.get("project"),
        "steps": meta.get("step_count"),
        "opencode_model": cfg.opencode_model,
        "opencode_variant": cfg.opencode_variant,
        "opencode_preset": cfg.opencode_preset or "",
        "success": success,
        "elapsed_seconds": elapsed,
        "tokens_prompt": parsed_tokens.prompt,
        "tokens_prompt_cache_hit": parsed_tokens.prompt_cache_hit,
        "tokens_prompt_cache_miss": parsed_tokens.prompt_cache_miss,
        "tokens_completion": completion_with_reasoning,
        "tokens_reasoning": parsed_tokens.reasoning,
        "tokens_total": parsed_tokens.total,
        "tokens_parse_source": parsed_tokens.source,
        "opencode_session_id": opencode_session_id or "",
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
            f"tokens in/out/total={parsed_tokens.prompt}/{completion_with_reasoning}/"
            f"{parsed_tokens.total}{cache_part} source={parsed_tokens.source}"
        )
    else:
        tok = "tokens=(unparsed)"
    _batch_log(
        tag,
        f"trial end | success={success} | outcome={trial_result.get('outcome')} | {elapsed}s | {tok}",
    )
    return trial_result


def _aggregate_trial_stats(trials: list[dict[str, Any]]) -> dict[str, Any]:
    success_count = sum(1 for t in trials if int(t.get("success", 0) or 0) == 1)
    n = len(trials)
    totals = [t.get("tokens_total") for t in trials if t.get("tokens_total") is not None]
    elapsed = [int(t.get("elapsed_seconds", 0) or 0) for t in trials]
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


def _run_one(id_value: int, cfg: OneRunConfig) -> dict[str, Any]:
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
        str(coqstoq_meta_script(cfg.proofagent_root)),
        "--id",
        str(id_value),
        "--split",
        cfg.split,
    ]
    if cfg.coqstoq_path is not None:
        meta_cmd += ["--coqstoq-path", str(cfg.coqstoq_path.resolve())]

    meta_rc, meta_out, meta_err, meta_timed_out = _run_capture(meta_cmd, cwd=cfg.proofagent_root, env=None, timeout_seconds=120)
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

    id_repeats = repeats_for_id(
        default_repeats=cfg.repeats,
        id_repeats=cfg.id_repeats,
        id_value=id_value,
    )
    _batch_log(
        tag,
        f"meta done | project={project_name} | steps={meta.get('step_count')} | v={meta.get('v_rel_path')} | "
        f"repeats={id_repeats}",
    )

    trials: list[dict[str, Any]] = []
    for trial_index in range(1, id_repeats + 1):
        copy_parent = trial_workspace_parent(cfg.workspace_batch_dir, id_value, trial_index)
        repo_dir = (copy_parent / project_name).resolve()
        trial_artifacts_dir = (artifacts_dir / f"trial_{trial_index:03d}").resolve()
        trials.append(
            _run_one_trial(
                id_value,
                trial_index,
                id_repeats,
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
    all_trials_ok = stats["success_count"] == id_repeats and id_repeats > 0
    aggregate: dict[str, Any] = {
        "id": id_value,
        "project": meta.get("project"),
        "steps": meta.get("step_count"),
        "target_coq_file": meta.get("v_rel_path"),
        "repeats": id_repeats,
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
        f"end | repeats={id_repeats} | trial_ok={stats['success_count']}/{stats['trial_count']} | "
        f"success_rate={stats['success_rate']:.2f} | elapsed={elapsed}s | "
        f"tokens_total_sum={stats.get('tokens_total_sum')}",
    )
    return aggregate


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
    ap = argparse.ArgumentParser(
        description="Batch runner: OpenCode + DeepSeek on CoqStoq ids (same workflow as BatchTest/run_batch).",
    )
    ap.add_argument(
        "--ids",
        type=int,
        nargs="*",
        default=None,
        help="Explicit ids (each uses --repeats); if omitted, read TestList.txt.",
    )
    ap.add_argument(
        "--testlist",
        type=Path,
        default=None,
        help="Path to TestList.txt (default: Evaluation/opencode/TestList.txt; fallback: BatchTest/TestList.txt).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=AGENT_WORKSPACE_OPENCODE,
        help="evaluation workspace agent root; each run adds <M-D-H-M_batch>/id_<n>/trial_<k>/.",
    )
    ap.add_argument(
        "--result-dir",
        type=Path,
        default=None,
        help="Summary and logs. Default: Evaluation/opencode/Result/<M-D-H-M_batch>/",
    )
    ap.add_argument(
        "--batch-stamp",
        type=str,
        default=None,
        help="Override batch folder name (default: month-day-hour-minute_batch).",
    )
    ap.add_argument("--split", type=str, default="test", choices=("test", "validation"))
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument(
        "--repeats",
        type=int,
        default=1,
        help=(
            "Default trials per id (--ids or testlist entries without repeats). "
            "Per-id counts come from testlist {\"id\": repeats} or {\"id\": {\"repeats\": K}}."
        ),
    )
    ap.add_argument(
        "--check-timeout-seconds",
        type=int,
        default=60,
        help="Unused for OpenCode (kept for CLI compatibility with BatchTest/run_batch).",
    )
    ap.add_argument("--run-timeout-seconds", type=int, default=1800)
    ap.add_argument(
        "--verify-make-timeout-seconds",
        type=int,
        default=180,
        help="Timeout (seconds) for `make` after copy and for final verify `make` (default: 180).",
    )
    ap.add_argument(
        "--extra-skip-keyword",
        action="append",
        default=[],
        help="Extra keyword to forbid outside comments (repeatable).",
    )
    ap.add_argument(
        "--proofagent-root",
        type=Path,
        default=_REPO_ROOT,
    )
    ap.add_argument(
        "--coqstoq-path",
        type=Path,
        default=None,
        help="Override COQSTOQ_PATH (default: env COQSTOQ_PATH).",
    )
    ap.add_argument("--opencode-bin", type=str, default=_OPENCODE_BIN)
    ap.add_argument(
        "--opencode-preset",
        type=str,
        default=None,
        choices=list_opencode_preset_keys(),
        help=(
            "Named model profile (e.g. codex-gpt-5.4  openai/gpt-5.4, "
            "openrouter-gpt-5.4  openrouter/openai/gpt-5.4). "
            "Overridden by explicit --opencode-model / --opencode-variant when not left at defaults."
        ),
    )
    ap.add_argument("--opencode-model", type=str, default=_OPENCODE_MODEL)
    ap.add_argument(
        "--opencode-variant",
        type=str,
        default=_OPENCODE_VARIANT,
        help="Provider-specific reasoning effort (e.g. high, max).",
    )
    ap.add_argument(
        "--opencode-skip-permissions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass --dangerously-skip-permissions to opencode run (default: on).",
    )
    ap.add_argument(
        "--parse-sentence-script",
        type=str,
        default="vsrocq_split_sentences_CoqStoq",
        help="Shell command to split .v sentences (appended with quoted absolute path); empty disables check.",
    )
    ap.add_argument(
        "--parse-sentence-timeout-seconds",
        type=int,
        default=120,
        help="Timeout for parse sentence script per trial (default: 120).",
    )
    args = ap.parse_args()
    if int(args.repeats) < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return 2

    default_repeats = int(args.repeats)
    run_specs: list[IdRunSpec]
    if args.ids is not None and len(args.ids) > 0:
        run_specs = [IdRunSpec(int(i), default_repeats) for i in args.ids]
    else:
        testlist_path = args.testlist
        if testlist_path is None:
            testlist_path = _EVAL_OPENCODE_DIR / "TestList.txt"
            if not testlist_path.is_file():
                testlist_path = _EVAL_DIR / "BatchTest" / "TestList.txt"
            if not testlist_path.is_file():
                testlist_path = args.proofagent_root / "TestList.txt"
        run_specs = read_run_specs_from_testlist(testlist_path, default_repeats)
    if not run_specs:
        print("No ids to run.", file=sys.stderr)
        return 2
    for spec in run_specs:
        if spec.repeats < 1:
            print(f"Invalid repeats for id={spec.id_value}: {spec.repeats} (must be >= 1)", file=sys.stderr)
            return 2
    ids = [s.id_value for s in run_specs]
    id_repeats_map = {s.id_value: s.repeats for s in run_specs}

    proofagent_root = args.proofagent_root.resolve()
    batch_stamp = (args.batch_stamp or "").strip() or make_batch_workspace_stamp()
    workspace_agent_root = args.out.resolve()
    workspace_batch_dir = (workspace_agent_root / batch_stamp).resolve()
    result_dir = args.result_dir
    if result_dir is None:
        result_dir = _EVAL_OPENCODE_DIR / "Result" / batch_stamp
    result_dir = result_dir.resolve()

    try:
        resolved_model, resolved_variant, resolved_preset = resolve_opencode_model_settings(
            args.opencode_preset,
            str(args.opencode_model),
            str(args.opencode_variant),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    cfg = OneRunConfig(
        proofagent_root=proofagent_root,
        coqstoq_path=args.coqstoq_path.resolve() if args.coqstoq_path is not None else None,
        workspace_agent_root=workspace_agent_root,
        workspace_batch_dir=workspace_batch_dir,
        result_dir=result_dir,
        split=args.split,
        check_timeout_seconds=int(args.check_timeout_seconds),
        run_timeout_seconds=int(args.run_timeout_seconds),
        verify_make_timeout_seconds=int(args.verify_make_timeout_seconds),
        extra_skip_keywords=list(args.extra_skip_keyword or []),
        repeats=default_repeats,
        id_repeats=id_repeats_map,
        opencode_bin=str(args.opencode_bin),
        opencode_model=resolved_model,
        opencode_variant=resolved_variant,
        opencode_preset=resolved_preset,
        opencode_skip_permissions=bool(args.opencode_skip_permissions),
        parse_sentence_script=str(args.parse_sentence_script or ""),
        parse_sentence_timeout_seconds=int(args.parse_sentence_timeout_seconds),
    )

    cfg.workspace_batch_dir.mkdir(parents=True, exist_ok=True)
    cfg.result_dir.mkdir(parents=True, exist_ok=True)

    repeats_log = format_default_repeats_log(cfg.repeats, cfg.id_repeats)
    _batch_log(
        "[batch]",
        f"config | ids={len(ids)} workers={args.workers} {repeats_log} | split={args.split} | "
        f"preset={cfg.opencode_preset or '-'} | model={cfg.opencode_model} variant={cfg.opencode_variant} | "
        f"workspace_batch={cfg.workspace_batch_dir} | result_dir={cfg.result_dir} | "
        f"run_timeout={cfg.run_timeout_seconds}s | verify_make_timeout={cfg.verify_make_timeout_seconds}s",
    )
    _batch_log("[batch]", f"ids (first 20): {ids[:20]}{' ...' if len(ids) > 20 else ''}")

    results: list[dict[str, Any]] = []
    total_n = len(ids)
    interrupted = False
    try:
        if args.workers <= 1 or len(ids) == 1:
            for idx, i in enumerate(ids, start=1):
                _batch_log("[batch]", f"sequential progress {idx}/{len(ids)} | id={i}")
                results.append(_run_one(i, cfg))
                _flush_summary(cfg.result_dir, results, log_line=True, total_planned=total_n)
        else:
            with ProcessPoolExecutor(max_workers=int(args.workers)) as ex:
                futs = {ex.submit(_run_one, i, cfg): i for i in ids}
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
                            "repeats": repeats_for_id(
                                default_repeats=cfg.repeats,
                                id_repeats=cfg.id_repeats,
                                id_value=rid,
                            ),
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
