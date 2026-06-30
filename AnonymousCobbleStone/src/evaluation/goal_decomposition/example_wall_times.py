import csv
import json
import typing as t
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ExampleWallTime:
    duration_seconds: float
    started_at: str
    finished_at: str
    successful: bool


class ExampleWallTimeJSON(t.TypedDict):
    duration_seconds: float
    started_at: str
    finished_at: str
    successful: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_example_wall_time(
    run_directory: Path,
    example_name: str,
    timing: ExampleWallTime,
) -> None:
    run_directory.mkdir(parents=True, exist_ok=True)
    json_path = run_directory / "example_wall_times.json"

    entries: t.Dict[str, ExampleWallTimeJSON] = {}
    if json_path.exists():
        with json_path.open() as f:
            entries = json.load(f)

    duration_seconds = round(timing.duration_seconds, 3)
    started_at = timing.started_at
    if example_name in entries:
        prev = entries[example_name]
        duration_seconds = round(prev["duration_seconds"] + duration_seconds, 3)
        started_at = prev["started_at"]

    entries[example_name] = {
        "duration_seconds": duration_seconds,
        "started_at": started_at,
        "finished_at": timing.finished_at,
        "successful": timing.successful,
    }

    with json_path.open("w") as f:
        json.dump(entries, f, indent=2, sort_keys=True)

    csv_path = run_directory / "example_wall_times.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "example_name",
                "lemma_name",
                "duration_seconds",
                "started_at",
                "finished_at",
                "successful",
            ]
        )
        for name in sorted(entries):
            row = entries[name]
            lemma_name = name.rsplit("-", 1)[-1] if "-" in name else name
            writer.writerow(
                [
                    name,
                    lemma_name,
                    row["duration_seconds"],
                    row["started_at"],
                    row["finished_at"],
                    row["successful"],
                ]
            )
