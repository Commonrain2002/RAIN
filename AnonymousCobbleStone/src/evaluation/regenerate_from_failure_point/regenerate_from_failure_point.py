from pathlib import Path
import traceback
from serde.json import from_json
import typing as t
import json
from pythonjsonlogger import jsonlogger
import tqdm
from tqdm_multiprocess.logger import setup_logger_tqdm
from tqdm_multiprocess import TqdmMultiProcessPool

from src.evaluation.regenerate_from_failure_point.task import RegenerateFromFailurePoint
from src.dataset import (
    Dataset,
    Example,
    Result,
    COQGYM_DEV_SAMPLED_DATASET_BASELINES_FAIL,
    COQGYM_TEST_SAMPLED_DATASET,
    COQ_WIGDERSON_DEV_SAMPLED_DATASET_BASELINES_FAIL,
    COQ_WIGDERSON_TEST_SAMPLED_DATASET,
    PNV_ROCQLIB_TEST_DATASET,
    COQ_BB5_TEST_DATASET
)
from src.config import CONFIG
from src.llm.usage import Usage
from .utils import LOGGER, DatasetName, DATASET_NAMES

RESULTS_DIR = (
    (Path(CONFIG.ROOT_DIR) / "data/evaluation/regenerate_from_failure_point")
    .resolve()
    .absolute()
)




class RegenerateFromFailurePointEval:
    uuid: str
    dataset_name: DatasetName
    try_hammer: bool
    max_num_attempts: int

    dataset: Dataset
    lemmas: t.List[str]

    result: Result
    # if proof is set to None, then we failed on that proof
    proofs: t.Dict[Example, t.Optional[str]]
    # tree searches loaded from files
    tasks: t.Dict[
        Example, t.Optional[RegenerateFromFailurePoint]
    ]  # TODO: define strategy

    def __init__(
        self,
        uuid: str,
        dataset_name: DatasetName,
        try_hammer: bool,
        max_num_attempts: int,
        lemmas: t.List[str] = [],
    ) -> None:
        self.uuid = uuid
        self.dataset_name = dataset_name
        self.try_hammer = try_hammer
        self.max_num_attempts = max_num_attempts
        self.lemmas = lemmas

        if dataset_name == "dev":
            self.dataset = COQGYM_DEV_SAMPLED_DATASET_BASELINES_FAIL
        elif dataset_name == "test":
            # self.dataset = COQGYM_TEST_SAMPLED_DATASET_BASELINES_FAIL
            self.dataset = COQGYM_TEST_SAMPLED_DATASET
        elif dataset_name == "wigderson_dev":
            self.dataset = COQ_WIGDERSON_DEV_SAMPLED_DATASET_BASELINES_FAIL
        elif dataset_name == "wigderson_test":
            # self.dataset = COQ_WIGDERSON_TEST_SAMPLED_DATASET_BASELINES_FAIL
            self.dataset = COQ_WIGDERSON_TEST_SAMPLED_DATASET
        elif dataset_name == "pnvrocqlib_test":
            self.dataset = PNV_ROCQLIB_TEST_DATASET
        elif dataset_name == "coq_bb5_test":
            self.dataset = COQ_BB5_TEST_DATASET
        else:
            raise ValueError(f"Unknown dataset name: {dataset_name}")

        self.__load_from_files()

    @property
    def name(self):
        return (
            f"{self.dataset_name}_{'with_hammer' if self.try_hammer else 'no_hammer'}"
        )

    @property
    def directory_path(self):
        return self.result.directory_path

    @property
    def filtered_dataset(self):
        if len(self.lemmas) == 0:
            return self.dataset
        return [
            example
            for example in self.dataset
            if example.location.lemma_name in self.lemmas
        ]

    @property
    def total_attempts(self):
        tasks = self.tasks.values()
        num_attempts = [len(task.attempts) for task in tasks if task]
        return sum(num_attempts)

    def run(self, num_processes: int) -> None:
        LOGGER.info(
            f"running {self.name} with {num_processes} processes",
            extra={"num_processes": num_processes, "uuid": self.uuid},
        )

        tasks = self.__get_multiprocessing_tasks()

        pool = TqdmMultiProcessPool(num_processes)
        total_attempts = self.max_num_attempts * len(self.filtered_dataset)
        num_attempts_left = total_attempts - self.total_attempts

        try:
            with tqdm.tqdm(
                total=num_attempts_left, dynamic_ncols=True
            ) as global_progress:
                global_progress.set_description("total progress")
                _proofs = pool.map(
                    global_progress, tasks, self.__error_callback, self.__done_callback
                )
        except Exception as e:
            LOGGER.error(
                "error while starting multiprocessing pool",
                extra={
                    "exception": str(e),
                    "stacktrace": traceback.format_exc(),
                },
            )

    def log_info(self, verbose: bool = False) -> None:
        print("# regenerate from failure point")
        print(f"uuid: {self.uuid}")
        print(f"dataset: {self.dataset_name}")
        print(f"lemmas: {self.lemmas}")
        print(f"try hammer: {self.try_hammer}")
        print(f"max num attempts: {self.max_num_attempts}")
        print()

        print("## results")
        print("example, correct, num_attempts")
        print(
            "all",
            sum(
                1
                for example in self.filtered_dataset
                if self.tasks.get(example, None) is not None
                and self.tasks[example].debug_success # type: ignore
            ),
            self.total_attempts,
        )
        for example in sorted(self.filtered_dataset, key=lambda x: x.name):
            task = self.tasks.get(example, None)
            if task is None:
                continue
            correct = (
                "in progress"
                if len(task.attempts) < task.max_num_attempts and not task.done
                else task.debug_success
            )
            num_attempts = len(task.attempts)
            print(f"{example.name}, {correct}, {num_attempts}")
        print()

        print("## usage")
        print("num_tokens: ", self.result.usage.num_tokens)
        print("num_input_tokens: ", self.result.usage.num_input_tokens)
        print("num_output_tokens: ", self.result.usage.num_output_tokens)
        print("num_requests: ", self.result.usage.num_requests)
        print("duration_millis: ", self.result.usage.duration_millis)
        print()

        if verbose:
            print("## task details")
            for example in sorted(self.filtered_dataset, key=lambda x: x.name):
                task = self.tasks.get(example, None)
                if task is None:
                    continue
                print(f"### {example.name}")
                print(f"Overall prefix without errors: {task.proof_in_progress}")
                print(f"Number of attempts: {len(task.attempts)}")
                print()

                for i, attempt in enumerate(task.attempts):
                    print(f"#### Attempt {i + 1}")
                    print(f"Success: {attempt.success}")
                    print(f"Prefix without errors: {attempt.prefix_without_errors}")
                    print(f"Full code: {attempt.tactics}")
                    print()
                print()

    def __load_from_files(self) -> None:
        self.result = Result(
            self.name, containing_directory=str(RESULTS_DIR), uuid=self.uuid
        )
        self.__setup_logging()
        LOGGER.info("loading from files", extra={"uuid": self.uuid})

        self.__load_tasks_from_files()
        usage = self.__load_usage_from_files()
        if usage is not None:
            self.result.usage = usage
        self.__update_result_based_on_samples()
        LOGGER.info("done loading from files", extra={"uuid": self.uuid})

    def __load_tasks_from_files(self):
        LOGGER.info("loading tasks from files")
        self.tasks = {}
        self.proofs = {}

        if not self.result.directory_path.exists():
            return

        for example in self.filtered_dataset:
            LOGGER.info(f"loading {example.name}", extra={"example": example.name})
            state_file = self.directory_path / f"{example.name}.json"
            try:
                with open(state_file, "r") as f:
                    task = from_json(RegenerateFromFailurePoint, f.read())
                self.tasks[example] = task
                self.proofs[example] = task.proof_in_progress
            except Exception as e:
                LOGGER.error(
                    f"error loading {example.name}",
                    extra={"example": example.name, "exception": str(e)},
                )
                print("\n\n")
                traceback.print_exc()
                print("\n")
                traceback.print_stack()
                print("\n\n")
                self.tasks[example] = RegenerateFromFailurePoint(
                    state_file=state_file,
                    example=example,
                    max_num_attempts=self.max_num_attempts,
                    try_hammer=self.try_hammer,
                )
                self.proofs[example] = None
        LOGGER.info("done loading tasks from files")

    def __load_usage_from_files(self) -> t.Optional[Usage]:
        usage_path = self.directory_path / "usage.json"
        if not usage_path.exists():
            return None
        with open(usage_path, "r") as f:
            return Usage.from_json(json.load(f))

    def __update_result_based_on_samples(self):
        """
        adapter for result.update_based_on_samples()
        """
        samples: t.List[t.Tuple[Example, str, bool]] = []
        for example in self.filtered_dataset:
            if example not in self.proofs:
                continue
            proof = self.proofs[example]
            samples.append(
                (example, proof if proof is not None else "", proof is not None)
            )

        self.result.update_based_on_samples(samples)

    def __setup_logging(self):
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

    def __get_multiprocessing_tasks(self):
        return [(task.task, ((),)) for task in self.tasks.values() if task]

    def __error_callback(self, e):
        LOGGER.error(
            f"error in process pool: {e}",
            extra={
                "exception": str(e),
                "stacktrace": traceback.format_exc(),
            },
        )

    def __done_callback(self, fn_result: t.Tuple[Example, t.Optional[str], Usage]):
        example, proof, usage = fn_result
        LOGGER.info(
            f"done with process pool: {example.name}",
            extra={"proof": proof, "usage": usage, "example": example},
        )
        self.proofs[example] = proof
        self.result.usage.add_child(usage)
        self.__update_result_based_on_samples()
        self.result.write()
