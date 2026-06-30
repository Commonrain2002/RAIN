"""Copy agent project workspace into per-trial result artifacts."""

from __future__ import annotations

import shutil
from pathlib import Path

WORKSPACE_SNAPSHOT_DIRNAME = "workspace"


def snapshot_repo_workspace(repo_dir: Path, trial_artifacts_dir: Path) -> tuple[Path | None, str | None]:
    """
    Copy ``repo_dir`` (project root after agent) to ``trial_artifacts_dir/workspace/``.

    Returns ``(destination, error_message)``; on success ``error_message`` is None.
    """
    if not repo_dir.is_dir():
        return None, f"repo_dir missing: {repo_dir}"
    dest = (trial_artifacts_dir / WORKSPACE_SNAPSHOT_DIRNAME).resolve()
    try:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(repo_dir, dest, symlinks=True)
        return dest, None
    except OSError as exc:
        return None, str(exc)
