from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple
import csv
import json
import typing as t
from datetime import datetime
from serde import serde

from src.llm.usage import Usage
from src.coq_serapy_util import LemmaLocation
from src.config import CONFIG
from src.utils import RUN_UUID

Dataset = List["Example"]
DatasetName = t.Literal[
    "dev",
    "test",
    "wigderson_dev",
    "wigderson_err",
    "wigderson_dev_perfect_subgoals",
    "wigderson_test",
    "wigderson_test_perfect_subgoals",
]
DATASET_NAMES: t.List[DatasetName] = [
    "dev",
    "test",
    "wigderson_dev",
    "wigderson_err",
    "wigderson_dev_perfect_subgoals",
    "wigderson_test",
    "wigderson_test_perfect_subgoals",
]


lemma_hint_map = {
    "bin_to_nat_preserves_incr": "Try to induct on the binary number",
    "nat_bin_nat": "Try to induct on the natural number",
    "double_plus": "Try to induct on the natural number",
    "double_incr": "Try to destruct on the natural number",
    "double_incr_bin": "Try to destruct on the binary number",
    "double_bin_incr": "Try to destruct on the binary number",
    "nat_to_bin_double": "Try to induct on the natural number",
    "bin_nat_bin": "You will need to assert and prove a stronger lemma to use in this proof. Then induct on the binary number to complete the proof",
    "exists_min": "Try to destruct on the list",
    "fib_correct": "You will need to assert and prove a stronger lemma to use in this proof. Then reuse existing theorems to prove this theorem",
    "fib_tail'_correct_2": "Try to induct on the natural number",
    "fib_correct_2": "Reuse existing theorems to prove this theorem",
    # "one_plus_n": "This should be trivial",
    "sum_tail_correct": "You will need to assert and prove a stronger lemma to use in this proof. Then reuse existing theorems to prove this theorem",
    "len_rev_unchanged": "You will need to assert and prove a stronger lemma to use in this proof. Then reuse existing theorems to prove this theorem",
    "generalize": "This should be trivial",
    "list_forall2_app": "Try to induct on the hypothesis of the theorem",
    "rev_involutive": "You will need to assert and prove a stronger lemma to use in this proof. Then reuse existing theorems to prove this theorem",
}


@dataclass
class RunStatistics:
    num_inferences: int
    num_tokens: int
    wall_clock_time_sec: float

    # if the statistics are for a full dataset, components are for each proof
    # if the statistics are for a single proof, components are for each attempt
    # if the statistics are for a single attempt, components are for each inference
    components: List["RunStatistics"] = field(default_factory=list)

    @staticmethod
    def from_openai_response(
        response: Any, wall_clock_time_sec: float
    ) -> "RunStatistics":
        return RunStatistics(
            num_inferences=1,
            num_tokens=response["usage"]["total_tokens"],
            wall_clock_time_sec=wall_clock_time_sec,
        )

    def add_component(self, component: "RunStatistics") -> "RunStatistics":
        return RunStatistics(
            num_inferences=self.num_inferences + component.num_inferences,
            num_tokens=self.num_tokens + component.num_tokens,
            wall_clock_time_sec=self.wall_clock_time_sec
            + component.wall_clock_time_sec,
            components=self.components + [component],
        )

@serde
@dataclass(frozen=True)
class Example:
    """
    an example to evaluate the model on.
    because we have a verifier, we don't actually need the gold standard proof."""

    location: LemmaLocation
    proposition_command: str
    gold_standard_proof: str
    hint: Optional[str] = None
    proof_prefix: t.Optional[str] = None
    tag: t.Optional[str] = None

    @property
    def name(self) -> str:
        return (
            f"{self.location.project_name.split('/')[-1]}-{self.location.file_name.split('/')[-1]}-{self.location.lemma_name}"
            + ("" if self.tag is None else f"-{self.tag}")
        )


@dataclass
class Result:
    """
    the results of evaluating a model on a dataset
    """

    name: str
    # don't specify this. it'll be setup in __init__
    usage: Usage = field(init=False)
    timestamp: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    )
    successful_examples: List[Example] = field(default_factory=list)
    failed_examples: List[Example] = field(default_factory=list)
    failed_error_messages: t.Dict[str, str] = field(default_factory=dict)
    errored_examples: List[Tuple[Example, str]] = field(default_factory=list)
    uuid: str = field(default_factory=lambda: RUN_UUID)
    containing_directory: str = CONFIG.LOG_DIR

    def __post_init__(self):
        self.directory_path.mkdir(parents=True, exist_ok=True)
        if not hasattr(self, "usage") or self.usage is None:
            self.usage = Usage(name=self.uuid)

        # mkdir LOG_DIR/self.csv_filename
        self.directory_path.mkdir(parents=True, exist_ok=True)
        # (Path(CONFIG.LOG_DIR) / f"{self.name}-{self.uuid}").mkdir(exist_ok=True)

    @property
    def directory(self) -> str:
        return f"{self.name}-{self.uuid}"

    @property
    def directory_path(self) -> Path:
        return Path(self.containing_directory) / f"{self.directory}"

    @property
    def csv_path(self) -> Path:
        return (self.directory_path / f"results.csv").absolute()

    @property
    def log_file_path(self) -> Path:
        return (self.directory_path / f"output.log").absolute()
        return (Path(CONFIG.LOG_DIR) / f"{self.csv_filename}/results.csv").absolute()

    @property
    def num_successful_examples(self) -> int:
        return len(self.successful_examples)

    @property
    def num_failed_examples(self) -> int:
        return len(self.failed_examples)

    @property
    def num_errored_examples(self) -> int:
        return len(self.errored_examples)

    @property
    def num_examples(self) -> int:
        return (
            self.num_successful_examples
            + self.num_failed_examples
            + self.num_errored_examples
        )

    def update_based_on_samples(
        self, samples: t.List[t.Tuple[Example, str, bool]]
    ) -> None:
        for example, _, success in samples:
            if success:
                self.successful_examples.append(example)
            else:
                self.failed_examples.append(example)
        self.successful_examples = list(set(self.successful_examples))
        self.failed_examples = list(set(self.failed_examples))

    def write(self):
        self.write_usage()
        self.write_csv_examples()

    def write_usage(self):
        path = self.directory_path / "usage.json"
        with open(path, "w") as f:
            f.write(json.dumps(self.usage.to_json()))

        for property in [
            "num_tokens",
            "num_input_tokens",
            "num_output_tokens",
            "num_requests",
            "num_cache_hit_read_tokens",
            "num_cache_miss_read_tokens",
            "num_cache_write_tokens",
            "num_reasoning_tokens",
            "duration_millis",
        ]:
            path = self.directory_path / f"{property}-usage.treemap.txt"
            with open(path, "w") as f:
                f.write(self.usage.compute_treemap(property))  # type: ignore

    def write_csv_examples(self):
        """
        writes results for each example to a csv file

        columns:
        lemma_name, lemma, section_names, successful
        """
        path = self.directory_path / "results.csv"
        with open(path, "w") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["lemma_name", "lemma", "section_names", "successful", "error_message"]
            )
            for example in self.successful_examples:
                writer.writerow(
                    [
                        example.location.lemma_name,
                        example.proposition_command,
                        example.location.section_names,
                        "success",
                        "",
                    ]
                )
            for example in self.failed_examples:
                writer.writerow(
                    [
                        example.location.lemma_name,
                        example.proposition_command,
                        example.location.section_names,
                        "failure",
                        self.failed_error_messages.get(
                            example.location.lemma_name, ""
                        ),
                    ]
                )
            for example, error_message in self.errored_examples:
                writer.writerow(
                    [
                        example.location.lemma_name,
                        example.proposition_command,
                        example.location.section_names,
                        "error",
                        error_message,
                    ]
                )
