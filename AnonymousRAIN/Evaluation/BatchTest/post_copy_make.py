"""Post-copy ``make`` with retries; used by evaluation batch runners."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PostCopyMakeRunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    attempts_summary: str


def run_post_copy_make_with_retries(
    repo_dir: Path,
    verify_make_timeout_seconds: int,
    *,
    build_shell_line: str | None = None,
) -> PostCopyMakeRunResult:
    subprocess_timeout_seconds = verify_make_timeout_seconds + 10
    if build_shell_line is not None:
        build_cmd = [
            "timeout",
            str(verify_make_timeout_seconds),
            "/bin/sh",
            "-c",
            build_shell_line,
        ]
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        summary_parts: list[str] = []
        for attempt_index in range(1, 4):
            returncode, out, err, timed_out = _run_capture(
                build_cmd,
                repo_dir,
                subprocess_timeout_seconds,
            )
            _append_attempt_log(
                stdout_parts, stderr_parts, "build", attempt_index, returncode, timed_out, out, err
            )
            summary_parts.append(f"build{attempt_index}:rc={returncode},timed_out={int(timed_out)}")
            if not timed_out and returncode == 0:
                return PostCopyMakeRunResult(
                    0,
                    "".join(stdout_parts),
                    "".join(stderr_parts),
                    False,
                    ";".join(summary_parts),
                )
        return PostCopyMakeRunResult(
            returncode,
            "".join(stdout_parts),
            "".join(stderr_parts),
            timed_out,
            ";".join(summary_parts),
        )

    make_cmd = ["timeout", str(verify_make_timeout_seconds), "make", "-j1"]
    clean_cmd = ["timeout", str(verify_make_timeout_seconds), "make", "clean"]

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    summary_parts: list[str] = []

    for attempt_index in range(1, 4):
        returncode, out, err, timed_out = _run_capture(
            make_cmd,
            repo_dir,
            subprocess_timeout_seconds,
        )
        _append_attempt_log(stdout_parts, stderr_parts, "make", attempt_index, returncode, timed_out, out, err)
        summary_parts.append(f"make{attempt_index}:rc={returncode},timed_out={int(timed_out)}")
        if not timed_out and returncode == 0:
            return PostCopyMakeRunResult(
                0,
                "".join(stdout_parts),
                "".join(stderr_parts),
                False,
                ";".join(summary_parts),
            )

    clean_returncode, clean_out, clean_err, clean_timed_out = _run_capture(
        clean_cmd,
        repo_dir,
        subprocess_timeout_seconds,
    )
    _append_attempt_log(
        stdout_parts,
        stderr_parts,
        "make_clean",
        0,
        clean_returncode,
        clean_timed_out,
        clean_out,
        clean_err,
    )
    summary_parts.append(f"make_clean:rc={clean_returncode},timed_out={int(clean_timed_out)}")

    returncode, out, err, timed_out = _run_capture(
        make_cmd,
        repo_dir,
        subprocess_timeout_seconds,
    )
    _append_attempt_log(stdout_parts, stderr_parts, "make_after_clean", 0, returncode, timed_out, out, err)
    summary_parts.append(f"make_after_clean:rc={returncode},timed_out={int(timed_out)}")

    return PostCopyMakeRunResult(
        returncode,
        "".join(stdout_parts),
        "".join(stderr_parts),
        timed_out,
        ";".join(summary_parts),
    )


def _append_attempt_log(
    stdout_parts: list[str],
    stderr_parts: list[str],
    label: str,
    attempt_index: int,
    returncode: int,
    timed_out: bool,
    stdout: str,
    stderr: str,
) -> None:
    if attempt_index > 0:
        header = (
            f"=== post_copy {label} attempt {attempt_index} "
            f"(rc={returncode} timed_out={int(timed_out)}) ===\n"
        )
    else:
        header = f"=== post_copy {label} (rc={returncode} timed_out={int(timed_out)}) ===\n"
    stdout_parts.append(header + stdout)
    stderr_parts.append(header + stderr)


def _run_capture(
    cmd: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> tuple[int, str, str, bool]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=None,
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
