#!/usr/bin/env python3
"""
Detect trials whose workspace after the agent has more unproven-intro constructs than the
fresh minimal copy baseline (same copy recipe as batch runners).

Counts (comment-stripped): Axiom, Parameter(s), Conjecture(s), Hypothesis(es), and tactic ``admit``.

Scans recent batch result trees for ProofAgent, OpenCode, Claude, Cobble, and Parcas.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_AXIOM_DETECTION_DIR = Path(__file__).resolve().parent
_EVAL_DIR = _AXIOM_DETECTION_DIR.parent
_REPO_ROOT = _EVAL_DIR.parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from BatchTest.coq_strip_comments import strip_coq_comments

_SCAN_VERSION = 2
_UNPROVEN_INTRO_VERNAC_KEYWORDS = (
    "Axiom",
    "Parameter",
    "Parameters",
    "Conjecture",
    "Conjectures",
    "Hypothesis",
    "Hypotheses",
)
_UNPROVEN_INTRO_KW_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _UNPROVEN_INTRO_VERNAC_KEYWORDS) + r")\b",
    re.MULTILINE,
)
_ADMIT_TACTIC_RE = re.compile(r"\badmit\b", re.MULTILINE)

_DEFAULT_DAYS = 4
_BATCH_DATE_RE = re.compile(r"^(?:merged_)?(\d+)-(\d+)-")


@dataclass(frozen=True)
class BackendSpec:
    name: str
    result_root: Path
    copy_kind: str  # coqstoq_id | project_root | cobble


@dataclass
class UnprovenIntroScan:
    per_file: dict[str, int] = field(default_factory=dict)
    per_file_by_kind: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.per_file.values())


@dataclass
class UnprovenIntroDelta:
    increased_files: list[tuple[str, int, int]]
    increased_kinds_by_file: dict[str, dict[str, int]]

    @property
    def has_new_unproven_intro(self) -> bool:
        return any(post > base for _, base, post in self.increased_files)

    @property
    def has_new_axioms(self) -> bool:
        return self.has_new_unproven_intro


@dataclass(frozen=True)
class TrialJob:
    backend_name: str
    copy_kind: str
    batch_name: str
    result_path: str
    rebuild_baseline: bool
    copy_timeout_seconds: int
    coqstoq_path: str
    baseline_cache_dir: str


@dataclass
class TrialRow:
    backend: str
    batch: str
    id_value: int
    trial: int
    repo_dir: str
    post_repo_present: bool
    baseline_built: bool
    baseline_error: str
    baseline_axiom_total: int
    post_axiom_total: int
    has_new_axioms: int
    has_new_unproven_intro: int
    increased_files_json: str
    increased_kinds_json: str
    success: str
    outcome: str
    skip_keyword_hits_json: str


_BACKENDS: list[BackendSpec] = [
    BackendSpec("proofagent", _REPO_ROOT / "Evaluation/proofagent/Result", "coqstoq_id"),
    BackendSpec("opencode", _REPO_ROOT / "Evaluation/opencode/Result", "coqstoq_id"),
    BackendSpec("claude", _REPO_ROOT / "Evaluation/claude/Result", "coqstoq_id"),
    BackendSpec("cobble", _REPO_ROOT / "Evaluation/cobble/proofagent/Result", "cobble"),
    BackendSpec("parcas", _REPO_ROOT / "Evaluation/parcas/Result", "project_root"),
    BackendSpec("parcas_opencode", _REPO_ROOT / "Evaluation/parcas/opencode/Result", "project_root"),
    BackendSpec("parcas_claude", _REPO_ROOT / "Evaluation/parcas/claude/Result", "project_root"),
]


def _count_unproven_intro_in_text(text: str) -> tuple[int, dict[str, int]]:
    no_comments = strip_coq_comments(text)
    by_kind: dict[str, int] = {}
    for match in _UNPROVEN_INTRO_KW_RE.finditer(no_comments):
        keyword = match.group(1)
        by_kind[keyword] = by_kind.get(keyword, 0) + 1
    admit_count = len(_ADMIT_TACTIC_RE.findall(no_comments))
    if admit_count:
        by_kind["admit"] = by_kind.get("admit", 0) + admit_count
    total = sum(by_kind.values())
    return total, by_kind


def scan_repo_unproven_intro(repo_dir: Path) -> UnprovenIntroScan:
    scan = UnprovenIntroScan()
    if not repo_dir.is_dir():
        return scan
    for root, _, files in os.walk(repo_dir):
        for fn in files:
            if not fn.endswith(".v"):
                continue
            fp = Path(root) / fn
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            count, by_kind = _count_unproven_intro_in_text(text)
            if count:
                rel = fp.relative_to(repo_dir).as_posix()
                scan.per_file[rel] = count
                scan.per_file_by_kind[rel] = by_kind
    return scan


def _kind_count_delta(
    baseline_kinds: dict[str, int],
    post_kinds: dict[str, int],
) -> dict[str, int]:
    increased: dict[str, int] = {}
    all_kinds = set(baseline_kinds) | set(post_kinds)
    for kind in sorted(all_kinds):
        delta = post_kinds.get(kind, 0) - baseline_kinds.get(kind, 0)
        if delta > 0:
            increased[kind] = delta
    return increased


def compare_unproven_intro_scans(
    baseline: UnprovenIntroScan,
    post: UnprovenIntroScan,
) -> UnprovenIntroDelta:
    increased: list[tuple[str, int, int]] = []
    increased_kinds_by_file: dict[str, dict[str, int]] = {}
    all_paths = set(baseline.per_file) | set(post.per_file)
    for rel in sorted(all_paths):
        base_c = baseline.per_file.get(rel, 0)
        post_c = post.per_file.get(rel, 0)
        if post_c > base_c:
            increased.append((rel, base_c, post_c))
            base_kinds = baseline.per_file_by_kind.get(rel, {})
            post_kinds = post.per_file_by_kind.get(rel, {})
            kind_delta = _kind_count_delta(base_kinds, post_kinds)
            if kind_delta:
                increased_kinds_by_file[rel] = kind_delta
    return UnprovenIntroDelta(
        increased_files=increased,
        increased_kinds_by_file=increased_kinds_by_file,
    )


def _batch_folder_calendar_date(batch_name: str, *, year: int) -> dt.date | None:
    match = _BATCH_DATE_RE.match(batch_name)
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _batch_dir_in_window(
    batch_dir: Path,
    *,
    earliest_inclusive: dt.date,
    latest_inclusive: dt.date,
    year: int,
) -> bool:
    if not batch_dir.is_dir():
        return False
    batch_date = _batch_folder_calendar_date(batch_dir.name, year=year)
    if batch_date is not None:
        return earliest_inclusive <= batch_date <= latest_inclusive
    return False


def iter_batch_dirs(
    result_root: Path,
    *,
    earliest_inclusive: dt.date,
    latest_inclusive: dt.date,
    year: int,
    include_merged: bool,
) -> Iterable[Path]:
    if not result_root.is_dir():
        return
    for child in sorted(result_root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith("merged_") and not include_merged:
            continue
        if not _batch_dir_in_window(
            child,
            earliest_inclusive=earliest_inclusive,
            latest_inclusive=latest_inclusive,
            year=year,
        ):
            continue
        yield child


def iter_trial_result_paths(batch_dir: Path) -> Iterable[Path]:
    for id_dir in sorted(batch_dir.glob("id_*")):
        for trial_dir in sorted(id_dir.glob("trial_*")):
            result_path = trial_dir / "result.json"
            if result_path.is_file():
                yield result_path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_post_repo_dir(trial_dir: Path, data: dict[str, Any]) -> Path | None:
    repo_raw = str(data.get("repo_dir") or "").strip()
    if repo_raw:
        repo = Path(repo_raw)
        if repo.is_dir():
            return repo.resolve()
    workspace = trial_dir / "workspace"
    if workspace.is_dir():
        return workspace.resolve()
    return None


def _run_copy(cmd: list[str], *, cwd: Path, timeout_seconds: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        err = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
        return 124, out, err


def _find_single_project_root(copy_parent: Path) -> Path | None:
    if not copy_parent.is_dir():
        return None
    children = [p for p in copy_parent.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if len(children) == 1:
        return children[0].resolve()
    for p in children:
        if (p / "Makefile").is_file() or (p / "_CoqProject").is_file() or (p / "dune-project").is_file():
            return p.resolve()
    return None


def _baseline_cache_key(copy_kind: str, meta: dict[str, Any]) -> tuple[Any, ...]:
    id_value = int(meta.get("id") or 0)
    split = str(meta.get("split") or "")
    workspace_root = str(meta.get("workspace_root") or "")
    v_rel = str(meta.get("v_rel_path") or "")
    end_line0 = int(meta.get("theorem_end_line0") or 0)
    end_col = int(meta.get("theorem_end_column_raw") or 0)
    return (copy_kind, id_value, split, workspace_root, v_rel, end_line0, end_col)


def _baseline_cache_slug(cache_key: tuple[Any, ...]) -> str:
    payload = json.dumps(cache_key, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    id_value = int(cache_key[1]) if len(cache_key) > 1 else 0
    copy_kind = str(cache_key[0]) if cache_key else "unknown"
    return f"{copy_kind}_{id_value}_{digest}"


def _baseline_cache_paths(cache_dir: Path, cache_key: tuple[Any, ...]) -> tuple[Path, Path]:
    slug = _baseline_cache_slug(cache_key)
    return cache_dir / f"{slug}.json", cache_dir / f"{slug}.lock"


def _load_unproven_scan_from_cache(cache_file: Path) -> tuple[UnprovenIntroScan, bool, str]:
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    if int(data.get("scan_version") or 0) != _SCAN_VERSION:
        return UnprovenIntroScan(), False, "stale baseline cache version"
    per_file_raw = data.get("per_file") or {}
    per_file = {str(k): int(v) for k, v in per_file_raw.items()}
    by_kind_raw = data.get("per_file_by_kind") or {}
    per_file_by_kind: dict[str, dict[str, int]] = {}
    for path, kinds in by_kind_raw.items():
        if isinstance(kinds, dict):
            per_file_by_kind[str(path)] = {str(k): int(v) for k, v in kinds.items()}
    scan = UnprovenIntroScan(per_file=per_file, per_file_by_kind=per_file_by_kind)
    built = bool(data.get("baseline_built"))
    error = str(data.get("baseline_error") or "")
    return scan, built, error


def _write_unproven_scan_cache(
    cache_file: Path,
    *,
    scan: UnprovenIntroScan,
    baseline_built: bool,
    baseline_error: str,
) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scan_version": _SCAN_VERSION,
        "per_file": scan.per_file,
        "per_file_by_kind": scan.per_file_by_kind,
        "baseline_built": baseline_built,
        "baseline_error": baseline_error,
    }
    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _acquire_baseline_lock(lock_file: Path) -> int | None:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, str(os.getpid()).encode("ascii"))
        return fd
    except FileExistsError:
        return None


def _release_baseline_lock(lock_file: Path, fd: int | None) -> None:
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        lock_file.unlink(missing_ok=True)
    except OSError:
        pass


def load_or_build_baseline_scan(
    *,
    copy_kind: str,
    meta: dict[str, Any],
    coqstoq_path: Path | None,
    cache_dir: Path,
    temp_parent: Path,
    copy_timeout_seconds: int,
    rebuild_baseline: bool,
) -> tuple[UnprovenIntroScan, bool, str]:
    cache_key = _baseline_cache_key(copy_kind, meta)
    cache_file, lock_file = _baseline_cache_paths(cache_dir, cache_key)
    if cache_file.is_file():
        scan, built, error = _load_unproven_scan_from_cache(cache_file)
        if error != "stale baseline cache version":
            return scan, built, error

    if not rebuild_baseline:
        return UnprovenIntroScan(), False, "baseline rebuild skipped"

    lock_fd = _acquire_baseline_lock(lock_file)
    if lock_fd is None:
        for _ in range(600):
            if cache_file.is_file():
                scan, built, error = _load_unproven_scan_from_cache(cache_file)
                if error != "stale baseline cache version":
                    return scan, built, error
            if not lock_file.is_file():
                break
            time.sleep(1.0)
        if cache_file.is_file():
            scan, built, error = _load_unproven_scan_from_cache(cache_file)
            if error != "stale baseline cache version":
                return scan, built, error
        return UnprovenIntroScan(), False, "baseline cache wait timeout"

    try:
        if cache_file.is_file():
            scan, built, error = _load_unproven_scan_from_cache(cache_file)
            if error != "stale baseline cache version":
                return scan, built, error
        worker_temp = temp_parent / _baseline_cache_slug(cache_key)
        repo, err = build_baseline_repo(
            copy_kind=copy_kind,
            meta=meta,
            coqstoq_path=coqstoq_path,
            temp_parent=worker_temp.parent,
            copy_timeout_seconds=copy_timeout_seconds,
        )
        if repo is not None:
            scan = scan_repo_unproven_intro(repo)
            _write_unproven_scan_cache(
                cache_file,
                scan=scan,
                baseline_built=True,
                baseline_error="",
            )
            shutil.rmtree(worker_temp, ignore_errors=True)
            return scan, True, ""
        _write_unproven_scan_cache(
            cache_file,
            scan=UnprovenIntroScan(),
            baseline_built=False,
            baseline_error=err,
        )
        return UnprovenIntroScan(), False, err
    finally:
        _release_baseline_lock(lock_file, lock_fd)


def build_baseline_repo(
    *,
    copy_kind: str,
    meta: dict[str, Any],
    coqstoq_path: Path | None,
    temp_parent: Path,
    copy_timeout_seconds: int,
) -> tuple[Path | None, str]:
    id_value = int(meta.get("id") or 0)
    v_rel_path = str(meta.get("v_rel_path") or "").strip()
    split = str(meta.get("split") or "test").strip() or "test"
    workspace_root = Path(str(meta.get("workspace_root") or "")).resolve()

    slug = _baseline_cache_slug(_baseline_cache_key(copy_kind, meta))
    copy_parent = temp_parent / slug
    if copy_parent.exists():
        shutil.rmtree(copy_parent, ignore_errors=True)
    copy_parent.mkdir(parents=True, exist_ok=True)

    if copy_kind == "coqstoq_id":
        copy_script = (_REPO_ROOT / "scripts" / "coqstoq_minimal_copy.py").resolve()
        cmd = [
            "python3",
            str(copy_script),
            str(id_value),
            "--split",
            split,
            "-o",
            str(copy_parent),
            "--force",
        ]
        if coqstoq_path is not None:
            cmd += ["--coqstoq-path", str(coqstoq_path.resolve())]
    elif copy_kind == "cobble":
        copy_script = (_REPO_ROOT / "Evaluation/cobble/cobble_minimal_copy.py").resolve()
        vfile_abs = (workspace_root / v_rel_path).resolve()
        cmd = [
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
            str(int(meta.get("theorem_end_line0") or 0)),
            "--theorem-end-column-raw",
            str(int(meta.get("theorem_end_column_raw") or 0)),
        ]
    elif copy_kind == "project_root":
        copy_script = (_REPO_ROOT / "scripts" / "coqstoq_minimal_copy.py").resolve()
        vfile_abs = (workspace_root / v_rel_path).resolve()
        cmd = [
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
            str(int(meta.get("theorem_end_line0") or 0)),
            "--theorem-end-column-raw",
            str(int(meta.get("theorem_end_column_raw") or 0)),
        ]
    else:
        return None, f"unknown copy_kind: {copy_kind}"

    rc, out, err = _run_copy(cmd, cwd=_REPO_ROOT, timeout_seconds=copy_timeout_seconds)
    if rc != 0:
        detail = (err or out).strip().replace("\n", " ")[:400]
        return None, f"copy_failed rc={rc} {detail}"

    project = _find_single_project_root(copy_parent)
    if project is None:
        return None, "copy_output_missing_project_root"
    return project, ""


def _coqstoq_path_from_str(raw: str) -> Path | None:
    text = raw.strip()
    if not text:
        return None
    return Path(text)


def process_trial_job(job: TrialJob) -> TrialRow:
    result_path = Path(job.result_path)
    trial_dir = result_path.parent
    id_dir = trial_dir.parent
    id_value = int(id_dir.name.removeprefix("id_") or "0")
    trial_index = int(trial_dir.name.removeprefix("trial_") or "0")

    data = _read_json(result_path)
    post_repo = _resolve_post_repo_dir(trial_dir, data)
    post_scan = scan_repo_unproven_intro(post_repo) if post_repo is not None else UnprovenIntroScan()

    meta_path = id_dir / "meta.json"
    baseline_scan = UnprovenIntroScan()
    baseline_built = False
    baseline_error = ""
    cache_dir = Path(job.baseline_cache_dir)
    temp_parent = cache_dir / "_build_temp"
    coqstoq_path = _coqstoq_path_from_str(job.coqstoq_path)

    if job.rebuild_baseline and meta_path.is_file():
        meta = _read_json(meta_path)
        baseline_scan, baseline_built, baseline_error = load_or_build_baseline_scan(
            copy_kind=job.copy_kind,
            meta=meta,
            coqstoq_path=coqstoq_path,
            cache_dir=cache_dir,
            temp_parent=temp_parent,
            copy_timeout_seconds=job.copy_timeout_seconds,
            rebuild_baseline=True,
        )
    elif not meta_path.is_file():
        baseline_error = "meta.json missing"
    else:
        baseline_error = "baseline rebuild skipped"

    delta = compare_unproven_intro_scans(baseline_scan, post_scan)
    skip_hits = data.get("skip_keyword_hits") or {}
    flag = 1 if delta.has_new_unproven_intro else 0

    return TrialRow(
        backend=job.backend_name,
        batch=job.batch_name,
        id_value=id_value,
        trial=trial_index,
        repo_dir=str(post_repo) if post_repo is not None else str(data.get("repo_dir") or ""),
        post_repo_present=post_repo is not None,
        baseline_built=baseline_built,
        baseline_error=baseline_error,
        baseline_axiom_total=baseline_scan.total,
        post_axiom_total=post_scan.total,
        has_new_axioms=flag,
        has_new_unproven_intro=flag,
        increased_files_json=json.dumps(delta.increased_files, ensure_ascii=False),
        increased_kinds_json=json.dumps(delta.increased_kinds_by_file, ensure_ascii=False),
        success=str(data.get("success", "")),
        outcome=str(data.get("outcome", "")),
        skip_keyword_hits_json=json.dumps(skip_hits, ensure_ascii=False),
    )


def _collect_trial_jobs(
    backends: list[BackendSpec],
    *,
    earliest_inclusive: dt.date,
    latest_inclusive: dt.date,
    year: int,
    include_merged: bool,
    rebuild_baseline: bool,
    copy_timeout_seconds: int,
    coqstoq_path: Path | None,
    baseline_cache_dir: Path,
    max_trials: int,
) -> list[TrialJob]:
    coqstoq_str = str(coqstoq_path.resolve()) if coqstoq_path is not None else ""
    jobs: list[TrialJob] = []
    for backend in backends:
        if not backend.result_root.is_dir():
            print(f"skip backend {backend.name}: missing {backend.result_root}", flush=True)
            continue
        for batch_dir in iter_batch_dirs(
            backend.result_root,
            earliest_inclusive=earliest_inclusive,
            latest_inclusive=latest_inclusive,
            year=year,
            include_merged=include_merged,
        ):
            batch_name = batch_dir.name
            print(f"queue {backend.name} / {batch_name}", flush=True)
            for result_path in iter_trial_result_paths(batch_dir):
                jobs.append(
                    TrialJob(
                        backend_name=backend.name,
                        copy_kind=backend.copy_kind,
                        batch_name=batch_name,
                        result_path=str(result_path.resolve()),
                        rebuild_baseline=rebuild_baseline,
                        copy_timeout_seconds=copy_timeout_seconds,
                        coqstoq_path=coqstoq_str,
                        baseline_cache_dir=str(baseline_cache_dir.resolve()),
                    )
                )
                if max_trials and len(jobs) >= max_trials:
                    return jobs
    return jobs


def _run_jobs_serial(jobs: list[TrialJob]) -> list[TrialRow]:
    rows: list[TrialRow] = []
    for index, job in enumerate(jobs, start=1):
        rows.append(process_trial_job(job))
        if index % 100 == 0:
            print(f"processed {index}/{len(jobs)} trials", flush=True)
    return rows


def _run_jobs_parallel(jobs: list[TrialJob], workers: int) -> list[TrialRow]:
    rows: list[TrialRow | None] = [None] * len(jobs)
    completed = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        future_to_index = {pool.submit(process_trial_job, job): i for i, job in enumerate(jobs)}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            rows[index] = future.result()
            completed += 1
            if completed % 100 == 0 or completed == len(jobs):
                print(f"processed {completed}/{len(jobs)} trials", flush=True)
    return [row for row in rows if row is not None]


def _write_csv(path: Path, rows: list[TrialRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "backend",
        "batch",
        "id",
        "trial",
        "repo_dir",
        "post_repo_present",
        "baseline_built",
        "baseline_error",
        "baseline_axiom_total",
        "post_axiom_total",
        "has_new_axioms",
        "has_new_unproven_intro",
        "increased_files_json",
        "increased_kinds_json",
        "success",
        "outcome",
        "skip_keyword_hits_json",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "backend": row.backend,
                    "batch": row.batch,
                    "id": row.id_value,
                    "trial": row.trial,
                    "repo_dir": row.repo_dir,
                    "post_repo_present": int(row.post_repo_present),
                    "baseline_built": int(row.baseline_built),
                    "baseline_error": row.baseline_error,
                    "baseline_axiom_total": row.baseline_axiom_total,
                    "post_axiom_total": row.post_axiom_total,
                    "has_new_axioms": row.has_new_axioms,
                    "has_new_unproven_intro": row.has_new_unproven_intro,
                    "increased_files_json": row.increased_files_json,
                    "increased_kinds_json": row.increased_kinds_json,
                    "success": row.success,
                    "outcome": row.outcome,
                    "skip_keyword_hits_json": row.skip_keyword_hits_json,
                }
            )


def _print_summary(rows: list[TrialRow]) -> None:
    by_backend: dict[str, list[TrialRow]] = {}
    for row in rows:
        by_backend.setdefault(row.backend, []).append(row)
    print("=== Unproven intro delta summary ===", flush=True)
    for backend_name in sorted(by_backend):
        backend_rows = by_backend[backend_name]
        total = len(backend_rows)
        with_post = sum(1 for r in backend_rows if r.post_repo_present)
        with_new = sum(1 for r in backend_rows if r.has_new_unproven_intro)
        baseline_ok = sum(1 for r in backend_rows if r.baseline_built)
        print(
            f"{backend_name}: trials={total} post_repo={with_post} baseline_ok={baseline_ok} "
            f"new_unproven_intro={with_new}",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect new Axiom declarations after agent runs.")
    parser.add_argument(
        "--days",
        type=int,
        default=_DEFAULT_DAYS,
        help=(
            f"Include batches whose folder name date (M-D-...) falls within the last N calendar days "
            f"(default {_DEFAULT_DAYS}, inclusive of today)."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        default=0,
        help="Calendar year for batch folder dates (default: local today.year).",
    )
    parser.add_argument(
        "--include-merged",
        action="store_true",
        help="Also scan merged_* batch folders (may duplicate trials).",
    )
    parser.add_argument(
        "--no-rebuild-baseline",
        action="store_true",
        help="Do not re-run minimal copy; only report post-repo axiom totals.",
    )
    parser.add_argument(
        "--coqstoq-path",
        type=Path,
        default=None,
        help="Override COQSTOQ_PATH for coqstoq_id copies (default: env COQSTOQ_PATH).",
    )
    parser.add_argument(
        "--copy-timeout-seconds",
        type=int,
        default=600,
        help="Timeout per baseline copy subprocess.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel worker processes (default 1 = serial). Baseline copies share a disk cache.",
    )
    parser.add_argument(
        "--baseline-cache-dir",
        type=Path,
        default=_AXIOM_DETECTION_DIR / "baseline_cache",
        help="On-disk cache for baseline Axiom scans (reused across runs).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_AXIOM_DETECTION_DIR / "axiom_delta_report.csv",
        help="CSV output path.",
    )
    parser.add_argument(
        "--backend",
        action="append",
        default=[],
        help="Limit to backend name (repeatable). Default: all.",
    )
    parser.add_argument(
        "--max-trials",
        type=int,
        default=0,
        help="Stop after N trials (0 = no limit). For debugging.",
    )
    args = parser.parse_args()

    coqstoq_path = args.coqstoq_path
    if coqstoq_path is None:
        env = os.environ.get("COQSTOQ_PATH", "").strip()
        if env:
            coqstoq_path = Path(env)

    today = dt.date.today()
    year = int(args.year) if int(args.year) > 0 else today.year
    latest_inclusive = today
    earliest_inclusive = today - dt.timedelta(days=max(0, int(args.days) - 1))
    selected = {b.strip() for b in args.backend if b.strip()}
    backends = [b for b in _BACKENDS if not selected or b.name in selected]

    print(
        f"batch date window: {earliest_inclusive.isoformat()} .. {latest_inclusive.isoformat()} (year={year})",
        flush=True,
    )

    baseline_cache_dir = args.baseline_cache_dir.resolve()
    baseline_cache_dir.mkdir(parents=True, exist_ok=True)
    jobs = _collect_trial_jobs(
        backends,
        earliest_inclusive=earliest_inclusive,
        latest_inclusive=latest_inclusive,
        year=year,
        include_merged=args.include_merged,
        rebuild_baseline=not args.no_rebuild_baseline,
        copy_timeout_seconds=args.copy_timeout_seconds,
        coqstoq_path=coqstoq_path,
        baseline_cache_dir=baseline_cache_dir,
        max_trials=int(args.max_trials or 0),
    )
    workers = max(1, int(args.workers))
    print(f"trials queued: {len(jobs)} | workers={workers}", flush=True)
    if workers == 1:
        rows = _run_jobs_serial(jobs)
    else:
        rows = _run_jobs_parallel(jobs, workers)
    build_temp = baseline_cache_dir / "_build_temp"
    shutil.rmtree(build_temp, ignore_errors=True)

    _write_csv(args.output.resolve(), rows)
    _print_summary(rows)
    print(f"wrote {args.output.resolve()} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
