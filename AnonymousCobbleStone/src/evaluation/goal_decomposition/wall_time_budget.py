import json
import time
import typing as t
from pathlib import Path


def load_cumulative_wall_seconds(
    run_directory: Path, example_name: str
) -> float:
    json_path = run_directory / "example_wall_times.json"
    if not json_path.exists():
        return 0.0
    with json_path.open() as f:
        entries: t.Dict[str, object] = json.load(f)
    row = entries.get(example_name)
    if not isinstance(row, dict):
        return 0.0
    return float(row.get("duration_seconds", 0.0))


def session_wall_deadline_exceeded(deadline_perf: t.Optional[float]) -> bool:
    return deadline_perf is not None and time.perf_counter() >= deadline_perf


def session_wall_budget_seconds(
    example_wall_timeout_sec: t.Optional[float],
    cumulative_wall_seconds: float,
) -> t.Optional[float]:
    if example_wall_timeout_sec is None:
        return None
    remaining = example_wall_timeout_sec - cumulative_wall_seconds
    if remaining <= 0:
        return 0.0
    return remaining
