#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parent

PALM_SWITCH = os.environ.get("PALM_OPAM_SWITCH", "coqstoq")
PROOF_START_MARKER = "### Proof Start @@@@"
PROOF_END_MARKER = "@@@ Proof End ####"

_COQPROJECT_NAMES = ("_CoqProject", "CoqProject", "Make")

_RQ_FLAGS_RE = re.compile(
    r'(?:^|[\s=])(?P<flag>-[RQ])\s+(?P<dir>"[^"]+"|\'[^\']+\'|\S+)\s+(?P<log>\S+)'
)


def parse_rq_flags_from_text(text: str) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for m in _RQ_FLAGS_RE.finditer(text):
        flag = m.group("flag")
        d = m.group("dir").strip()
        if (d.startswith('"') and d.endswith('"')) or (d.startswith("'") and d.endswith("'")):
            d = d[1:-1]
        log = m.group("log").strip()
        found.append((flag, d, log))
    return found


def make_batch_workspace_stamp() -> str:
    t = time.localtime()
    return f"{t.tm_mon}-{t.tm_mday}-{t.tm_hour:02d}-{t.tm_min:02d}_batch"


def trial_workspace_parent(workspace_batch_dir: Path, id_value: int, trial_index: int) -> Path:
    return (workspace_batch_dir / f"id_{id_value}" / f"trial_{trial_index:03d}").resolve()


def read_ids_from_testlist(path: Path) -> list[int]:
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [int(x) for x in v]
    except Exception:
        pass
    return [int(x) for x in re.findall(r"\d+", raw)]


def parse_last_json_line(stdout: str) -> dict[str, Any]:
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("{") and ln.endswith("}"):
            return json.loads(ln)
    raise ValueError("no JSON line found in meta output")


def batch_log(prefix: str, message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} {prefix} {message}", flush=True)


def run_capture(
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


def merge_opam_palm_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env["OPAMSWITCH"] = PALM_SWITCH
    opam_path = env.get("OPAMROOT") or str(Path.home() / ".opam")
    opam_bin = Path(opam_path) / "bin" / "opam"
    if opam_bin.is_file():
        rc2, out2, _, _ = run_capture(
            [str(opam_bin), "env", "--switch", PALM_SWITCH],
            cwd=None,
            env=env,
            timeout_seconds=60,
        )
        if rc2 == 0:
            for export_line in out2.splitlines():
                export_line = export_line.strip()
                if export_line.startswith("export "):
                    kv = export_line[len("export ") :]
                    if "=" in kv:
                        k, _, v = kv.partition("=")
                        v = v.strip().strip('"').strip("'")
                        env[k] = v
    palm_bin = Path(opam_path) / PALM_SWITCH / "bin"
    if palm_bin.is_dir():
        env["PATH"] = str(palm_bin) + os.pathsep + env.get("PATH", "")
    return env


def build_rq_options_string(repo_dir: Path) -> str:
    """Build the first path.json field: repo-relative -R/-Q options as space-separated tokens."""
    repo_dir = repo_dir.resolve()
    tokens: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for fname in _COQPROJECT_NAMES:
        p = repo_dir / fname
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for flag, d, log in parse_rq_flags_from_text(text):
            clean = d.strip().strip('"').strip("'")
            dir_path = Path(clean)
            if dir_path.is_absolute():
                try:
                    rel = dir_path.relative_to(repo_dir)
                    d_str = "." if rel.as_posix() in ("", ".") else rel.as_posix()
                except ValueError:
                    d_str = clean
            else:
                d_str = clean
            key = (flag, d_str, log)
            if key in seen:
                continue
            seen.add(key)
            tokens.extend([flag, d_str, log])
    if not tokens:
        raise ValueError(f"no -R/-Q found under {repo_dir}")
    return " ".join(tokens)


def setup_trial_palm_workspace(repo_root: Path, trial_artifacts_dir: Path) -> tuple[Path, Path]:
    """
    Copy text configuration from the repository data directory into the trial directory.
    Later PALM steps only read and write this directory to avoid multi-worker races.
    Return absolute (trial_data_dir, trial_eval_dir) paths.
    """
    trial_data = (trial_artifacts_dir / "data").resolve()
    trial_eval = (trial_artifacts_dir / "evaluation").resolve()
    trial_data.mkdir(parents=True, exist_ok=True)
    trial_eval.mkdir(parents=True, exist_ok=True)
    src_data = repo_root / "data"
    src_path_json = src_data / "path.json"
    if src_path_json.is_file():
        shutil.copy2(src_path_json, trial_data / "path.json")
    else:
        (trial_data / "path.json").write_text("{}\n", encoding="utf-8")
    for name in ("intersection.json",):
        extra = src_data / name
        if extra.is_file():
            shutil.copy2(extra, trial_data / name)
    return trial_data, trial_eval


def update_local_path_json(
    path_json: Path,
    project: str,
    rq_string: str,
    switch: str = PALM_SWITCH,
) -> None:
    """Write only the trial-local path.json; each trial owns its copy, so no flock is needed."""
    path_json = path_json.resolve()
    raw = path_json.read_text(encoding="utf-8") if path_json.is_file() else ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data[project] = [rq_string, switch]
    path_json.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


_PROOF_BLOCK_RE = re.compile(
    re.escape(PROOF_START_MARKER) + r"\s*(.*?)\s*" + re.escape(PROOF_END_MARKER),
    re.DOTALL,
)


def parse_palm_proof(combined_output: str) -> str | None:
    m = _PROOF_BLOCK_RE.search(combined_output)
    if not m:
        return None
    return m.group(1).strip()


PALM_RUNTIME_ERROR_MARKER = "Proof Error."


def detect_palm_runtime_error(combined_output: str) -> str | None:
    """src/main.py prints Proof Error. in except blocks; batch runs classify this as runtime_error."""
    if PALM_RUNTIME_ERROR_MARKER not in combined_output:
        return None
    for line in combined_output.splitlines():
        stripped = line.strip()
        if "prover err:" in stripped:
            return stripped[:800]
    return PALM_RUNTIME_ERROR_MARKER


# Keep this in sync with src/llm.py print_run_usage / format_usage_line.
_TOKEN_USAGE_LAST_LINE_RE = re.compile(
    r"calls=(?P<calls>\d+)\s+tokens:\s+total=(?P<total>\d+)\s+"
    r"cache_hit_read=(?P<cache_hit>\d+)\s+cache_miss_read=(?P<cache_miss>\d+)\s+"
    r"write=(?P<write>\d+)"
    r"(?:\s+reasoning=(?P<reasoning>\d+))?"
)


def parse_token_usage_from_stdout(stdout: str) -> dict[str, Any]:
    """
    Parse token usage from the last PALM stdout line.
    If the last line does not match, scan upward for the first parseable line.
    """
    empty: dict[str, Any] = {
        "tokens_api_calls": None,
        "tokens_total": None,
        "tokens_prompt_cache_hit": None,
        "tokens_prompt_cache_miss": None,
        "tokens_completion": None,
        "tokens_reasoning": None,
        "tokens_parse_source": None,
        "tokens_stdout_last_line": None,
    }
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        return dict(empty)
    candidates = [lines[-1]] + list(reversed(lines[:-1]))
    for idx, line in enumerate(candidates):
        m = _TOKEN_USAGE_LAST_LINE_RE.search(line)
        if not m:
            continue
        reasoning = m.group("reasoning")
        source = "stdout_last_line" if idx == 0 else "stdout_scan"
        return {
            "tokens_api_calls": int(m.group("calls")),
            "tokens_total": int(m.group("total")),
            "tokens_prompt_cache_hit": int(m.group("cache_hit")),
            "tokens_prompt_cache_miss": int(m.group("cache_miss")),
            "tokens_completion": int(m.group("write")),
            "tokens_reasoning": int(reasoning) if reasoning else None,
            "tokens_parse_source": source,
            "tokens_stdout_last_line": line[:500],
        }
    empty["tokens_stdout_last_line"] = lines[-1][:500]
    return empty


def normalize_proof_for_patch(proof: str) -> str:
    p = proof.strip()
    if p.endswith("Qed."):
        p = p[: -len("Qed.")].rstrip()
    elif p.endswith("Qed"):
        p = p[: -len("Qed")].rstrip()
    return p


def replace_admitted_in_vfile(vfile: Path, proof: str) -> None:
    text = vfile.read_text(encoding="utf-8", errors="replace")
    body = normalize_proof_for_patch(proof)
    replacement = f"{body}\nQed."
    new_text, n = re.subn(
        r"(?m)^(\s*)Admitted\.\s*$",
        lambda m: m.group(1) + replacement.replace("\n", "\n" + m.group(1)),
        text,
        count=1,
    )
    if n == 0:
        new_text, n = re.subn(
            r"Admitted\.",
            replacement,
            text,
            count=1,
        )
    if n == 0:
        raise ValueError(f"no Admitted. found in {vfile}")
    vfile.write_text(new_text, encoding="utf-8")


def infer_theorem_name_from_data(data_root: Path, project: str, v_rel_path: str) -> str:
    """Fallback: the only theorem name whose extracted proof ends with Admitted."""
    rel_json = v_rel_path[:-2] + ".json" if v_rel_path.endswith(".v") else v_rel_path
    data_file = data_root / project / rel_json
    if not data_file.is_file():
        return ""
    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    codes = data.get("code") or []
    theorems = data.get("theorems") or []
    admitted: list[str] = []
    for th in theorems:
        end = th.get("end", -1)
        if not isinstance(end, int) or end < 0 or end >= len(codes):
            continue
        tail = str(codes[end]).strip()
        if tail.startswith("Admitted"):
            name = str(th.get("name") or "")
            if name:
                admitted.append(name)
    if len(admitted) == 1:
        return admitted[0]
    return ""


def resolve_coqstoq_theorem_name(
    meta: dict[str, Any], data_root: Path, project: str, v_rel_path: str
) -> str:
    """Prefer theorem_name from CoqStoq meta, matching run.sh --theorem behavior."""
    name = str(meta.get("theorem_name") or "").strip()
    if name:
        return name
    return infer_theorem_name_from_data(data_root, project, v_rel_path)


def trim_extract_json_to_theorem(
    data_root: Path, project: str, v_rel_path: str, theorem_name: str
) -> None:
    """Keep only the CoqStoq target theorem entry in data JSON; leave code intact for SerAPI indexes."""
    rel_json = v_rel_path[:-2] + ".json" if v_rel_path.endswith(".v") else v_rel_path
    data_file = data_root / project / rel_json
    data = json.loads(data_file.read_text(encoding="utf-8"))
    theorems = data.get("theorems") or []
    kept = [t for t in theorems if str(t.get("name") or "") == theorem_name]
    if len(kept) != 1:
        raise ValueError(
            f"expected exactly one theorem {theorem_name!r} in {data_file}, got {len(kept)} matches"
        )
    data["theorems"] = kept
    data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


HAMMER_IMPORT_LINE = "From Hammer Require Import Hammer Tactics."


def ensure_hammer_import_first_line(vfile: Path) -> None:
    """Add Hammer to the first line after copying; raise so batch runs can skip failed trials."""
    if not vfile.is_file():
        raise FileNotFoundError(f"target .v missing: {vfile}")
    text = vfile.read_text(encoding="utf-8", errors="replace")
    if not text.lstrip().startswith(HAMMER_IMPORT_LINE):
        vfile.write_text(HAMMER_IMPORT_LINE + "\n" + text, encoding="utf-8")
    after = vfile.read_text(encoding="utf-8", errors="replace")
    first = after.lstrip().splitlines()[0].strip() if after.lstrip() else ""
    if first != HAMMER_IMPORT_LINE:
        raise RuntimeError(
            f"hammer import not on line 1 after write (first line: {first!r})"
        )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
