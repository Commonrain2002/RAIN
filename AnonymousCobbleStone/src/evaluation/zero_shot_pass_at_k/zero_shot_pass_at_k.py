from pathlib import Path
import typing as t
import tqdm
from tqdm_multiprocess import TqdmMultiProcessPool
from tqdm_multiprocess.logger import setup_logger_tqdm
import traceback
import json
from pythonjsonlogger import jsonlogger
import csv
import math

from .utils import DatasetName, LOGGER, SampleJSON, pass_at_k, RESULTS_DIR
from .collect_samples_for_example import (
    collect_samples_for_example_tuple,
    ProcessArg,
    ProcessFn,
)
from src.dataset import (
    Result,
    Example,
    Dataset,
    COQGYM_DEV_SAMPLED_DATASET,
    COQGYM_TEST_SAMPLED_DATASET,
    COQ_WIGDERSON_DEV_SAMPLED_DATASET,
    COQ_WIGDERSON_TEST_SAMPLED_DATASET,
    COQ_WIGDERSON_DEV_PERFECT_SUBGOALS_DATASET,
    COQ_WIGDERSON_TEST_PERFECT_SUBGOALS_DATASET,
    COQ_BB5_DEV_DATASET,
    COQ_BB5_TEST_DATASET,
    PNV_ROCQLIB_DEV_DATASET,
    PNV_ROCQLIB_TEST_DATASET,
)
from src.config import CONFIG
from src.environment import LemmaContext
from src.llm import Usage
from src.llm.model_names import OpenaiChatModelName
from src.utils import set_log_file


class ZeroShotPassAtK:
    uuid: str
    dataset_name: DatasetName
    lemma_context: LemmaContext
    temperature: float
    model: OpenaiChatModelName

    dataset: Dataset
    lemmas: t.List[str]

    result: Result
    samples: t.Dict[Example, t.List[t.Tuple[str, bool]]]
    num_samples: t.Dict[Example, int]
    num_correct_samples: t.Dict[Example, int]

    def __init__(
        self,
        uuid: str,
        dataset_name: DatasetName,
        lemma_context: LemmaContext,
        temperature: float = 1,
        lemmas: t.List[str] = [],
        model: OpenaiChatModelName = "gpt-4",
    ):
        self.uuid = uuid
        self.dataset_name = dataset_name
        self.lemma_context = lemma_context
        self.temperature = temperature
        self.model = model

        if self.lemma_context == "perfect-premises" and self.dataset_name not in [
            "wigderson_test",
            "wigderson_dev",
            "test",
            "wigderson_test_perfect_subgoals",
            "wigderson_dev_perfect_subgoals",
        ]:
            raise ValueError("perfect-premises does not work with " + self.dataset_name)

        if dataset_name == "dev":
            self.dataset = COQGYM_DEV_SAMPLED_DATASET
        elif dataset_name == "test":
            self.dataset = COQGYM_TEST_SAMPLED_DATASET
        elif dataset_name == "wigderson_dev":
            self.dataset = COQ_WIGDERSON_DEV_SAMPLED_DATASET
        elif dataset_name == "wigderson_dev_perfect_subgoals":
            self.dataset = COQ_WIGDERSON_DEV_PERFECT_SUBGOALS_DATASET
        elif dataset_name == "wigderson_test_perfect_subgoals":
            self.dataset = COQ_WIGDERSON_TEST_PERFECT_SUBGOALS_DATASET
        elif dataset_name == "coq_bb5_dev":
            self.dataset = COQ_BB5_DEV_DATASET
        elif dataset_name == "coq_bb5_test":
            self.dataset = COQ_BB5_TEST_DATASET
        elif dataset_name == "pnvrocqlib_dev":
            self.dataset = PNV_ROCQLIB_DEV_DATASET
        elif dataset_name == "pnvrocqlib_test":
            self.dataset = PNV_ROCQLIB_TEST_DATASET
        else:
            assert dataset_name == "wigderson_test"
            self.dataset = COQ_WIGDERSON_TEST_SAMPLED_DATASET

        self.lemmas = lemmas

        self.__load_from_files()

    @property
    def name(self):
        ans = f"{self.dataset_name}_{self.lemma_context}"
        if self.temperature != 1:
            ans += f"_t{self.temperature}"
        return ans

    @property
    def directory_path(self) -> Path:
        return self.result.directory_path

    @property
    def total_samples_collected(self) -> int:
        return sum(self.num_samples.values())

    @property
    def filtered_dataset(self) -> Dataset:
        if len(self.lemmas) == 0:
            return self.dataset
        return [
            example
            for example in self.dataset
            if example.location.lemma_name in self.lemmas
        ]

    def collect_samples(self, num_samples_per_example: int, num_processes: int):
        self.__setup_logging()

        LOGGER.info(
            f"collecting {num_samples_per_example} samples for each of {len(self.filtered_dataset)} proofs",
            extra={
                "num_examples": len(self.filtered_dataset),
                "num_samples_per_example": num_samples_per_example,
                "uuid": self.uuid,
            },
        )

        pool = TqdmMultiProcessPool(num_processes)
        tasks: t.List[t.Tuple[ProcessFn, ProcessArg]] = (
            self.__get_multiprocessing_tasks(num_samples_per_example)
        )

        total_samples_to_collect = num_samples_per_example * len(self.filtered_dataset)
        num_samples_to_collect = total_samples_to_collect - self.total_samples_collected

        try:
            with tqdm.tqdm(
                total=num_samples_to_collect, dynamic_ncols=True
            ) as global_progress:
                global_progress.set_description(f"total progress")
                _sampleses: t.List[
                    t.Tuple[t.List[t.Tuple[Example, str, bool]], Usage]
                ] = pool.map(
                    global_progress, tasks, self.__error_callback, self.__done_callback
                )
        except Exception as e:
            LOGGER.error(
                "error while collecting samples",
                extra={
                    "exception": str(e),
                    "stacktrace": traceback.format_exc(),
                },
            )
        finally:
            LOGGER.info(
                "overall usage",
                extra={
                    "duration_millis": self.result.usage.duration_millis,
                    "num_input_tokens": self.result.usage.num_input_tokens,
                    "num_output_tokens": self.result.usage.num_output_tokens,
                    "num_tokens": self.result.usage.num_tokens,
                    "num_requests": self.result.usage.num_requests,
                },
            )
            self.result.write()

    def log_info(self):
        self.__setup_logging()

        print("# zero shot pass at k")
        print(f"uuid: {self.uuid}")
        print(f"dataset: {self.dataset_name}")
        print(f"lemmas: {self.lemmas}")
        print(f"lemma context: {self.lemma_context}")
        print(f"temperature: {self.temperature}")
        print(f"model: {self.model}")
        print()

        print("## samples")
        print("example, total, num_correct")
        print(
            "all",
            sum(self.num_samples.values()),
            sum(self.num_correct_samples.values()),
        )
        for example in sorted(self.filtered_dataset, key=lambda x: x.name):
            print(
                example.name,
                self.num_samples.get(example, 0),
                self.num_correct_samples.get(example, 0),
            )
        print()

        print("## usage")
        print("num_tokens: ", self.result.usage.num_tokens)
        print("num_input_tokens: ", self.result.usage.num_input_tokens)
        print("num_output_tokens: ", self.result.usage.num_output_tokens)
        print("num_requests: ", self.result.usage.num_requests)
        print("duration_millis: ", self.result.usage.duration_millis)
        print()

        LOGGER.info(
            "zero shot pass at k",
            extra={
                "uuid": self.uuid,
                "dataset": self.dataset_name,
                "lemma_context": self.lemma_context,
            },
        )
        LOGGER.info(
            "samples",
            extra={
                "all": (
                    sum(self.num_samples.values()),
                    sum(self.num_correct_samples.values()),
                ),
            },
        )
        LOGGER.info(
            "usage",
            extra={
                "num_tokens": self.result.usage.num_tokens,
                "num_input_tokens": self.result.usage.num_input_tokens,
                "num_output_tokens": self.result.usage.num_output_tokens,
                "num_requests": self.result.usage.num_requests,
                "duration_millis": self.result.usage.duration_millis,
            },
        )

    K_VALUES = [k for k in range(1, 21)]

    def output_evaluation(self):
        output_path = self.directory_path / "pass_at_k.csv"
        print(self.num_samples)
        max_num_samples = max(self.num_samples.values())
        max_k = max_num_samples # math.floor(max_num_samples * 0.7)
        k_values = [k for k in ZeroShotPassAtK.K_VALUES if k <= max_k]
        with open(output_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(
                [
                    "example",
                    "project_name",
                    "lemma_name",
                    "num samples",
                    "num correct",
                ]
                + [f"pass@{k}" for k in k_values]
            )

            examples = sorted(self.filtered_dataset, key=lambda e: e.name)
            for example in examples:
                num_samples = self.num_samples.get(example, 0)
                num_correct = self.num_correct_samples.get(example, 0)
                pass_at_ks = [pass_at_k(num_samples, num_correct, k) for k in k_values]
                writer.writerow(
                    [
                        example.name,
                        example.location.project_name,
                        example.location.lemma_name,
                        num_samples,
                        num_correct,
                    ]
                    + pass_at_ks,
                )
        print(
            f"wrote {len(self.filtered_dataset)} pass@k results to csv at {output_path}"
        )
        LOGGER.info(
            f"wrote {len(self.filtered_dataset)} pass@k results to csv at {output_path}",
            extra={
                "output_path": output_path,
                "num_examples": len(self.filtered_dataset),
            },
        )

        results: t.Dict[str, bool] = {
            example.name: self.num_correct_samples.get(example, 0) > 0
            for example in examples
        }
        output_path = self.directory_path / "results.json"
        with open(output_path, "w") as f:
            json.dump(results, f)
        print(f"wrote results to json at {output_path}")
        LOGGER.info(
            f"wrote results to json at {output_path}",
            extra={"output_path": output_path},
        )

    def __get_multiprocessing_tasks(
        self, num_samples_per_example: int
    ) -> t.List[t.Tuple[ProcessFn, ProcessArg]]:
        tasks = []
        for example in self.filtered_dataset:
            num_samples = self.num_samples.get(example, 0)
            if (num_samples_per_example - num_samples) <= 0:
                continue
            task_argument = (
                example,
                num_samples_per_example,
                self.samples.get(example, []),
                self.directory_path,
                self.lemma_context,
                self.temperature,
                self.model,
            )
            tasks.append((collect_samples_for_example_tuple, (task_argument,)))

        return tasks

    def __setup_logging(self):
        # set_log_file(self.result.log_file_path)
        setup_logger_tqdm(
            self.result.log_file_path,
            formatter=jsonlogger.JsonFormatter(  # type: ignore
                "%(asctime)s %(levelname)s %(name)s: %(message)s",
                "%Y-%m-%d %H:%M:%S",
                rename_fields={
                    "asctime": "timestamp",
                    "levelname": "level",
                },
            ),
        )

    def __error_callback(self, e):
        LOGGER.error(
            f"error in process pool: {e}",
            extra={
                "error": str(e),
            },
        )

    def __done_callback(
        self, fn_result: t.Tuple[t.List[t.Tuple[Example, str, bool]], Usage]
    ):
        LOGGER.info(f"done with process pool: {fn_result}")
        self.result.usage.add_child(fn_result[1])
        self.result.update_based_on_samples(fn_result[0])
        LOGGER.info("usage so far", extra={"usage": self.result.usage})
        self.result.write()

    def __load_from_files(self):
        self.result = Result(
            self.name, containing_directory=str(RESULTS_DIR), uuid=self.uuid
        )

        self.__load_samples_from_files()
        usage = self.__load_usage_from_files()

        self.result = Result(
            self.name, containing_directory=str(RESULTS_DIR), uuid=self.uuid
        )
        if usage is not None:
            self.result.usage = usage

        for example, samples in self.samples.items():
            self.result.update_based_on_samples(
                [(example, code, success) for code, success in samples]
            )

    def __load_samples_from_files(self):
        self.samples = {}
        self.num_samples = {}
        self.num_correct_samples = {}

        if not self.directory_path.exists():
            return

        for example in self.filtered_dataset:
            example_path = self.directory_path / f"{example.name}.samples.json"
            if not example_path.exists():
                continue
            try:
                with open(example_path, "r") as f:
                    samples_json: t.List[SampleJSON] = json.load(f)
                    self.samples[example] = [
                        (sample["code"], sample["success"]) for sample in samples_json
                    ]
                    self.num_samples[example] = len(samples_json)
                    self.num_correct_samples[example] = sum(
                        sample["success"] for sample in samples_json
                    )
            except Exception as e:
                LOGGER.error(
                    f"error while reading samples for {example}",
                    extra={
                        "exception": str(e),
                        "stacktrace": traceback.format_exc(),
                    },
                )

    def __load_usage_from_files(self):
        usage_path = self.directory_path / "usage.json"
        if not usage_path.exists():
            return None

        try:
            with open(usage_path, "r") as f:
                return Usage.from_json(json.load(f))
        except Exception as e:
            LOGGER.error(
                f"error while reading usage from {usage_path}",
                extra={
                    "exception": str(e),
                    "stacktrace": traceback.format_exc(),
                },
            )
            return None
