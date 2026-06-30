import typing as t
import tqdm
from tqdm_multiprocess import TqdmMultiProcessPool
from tqdm_multiprocess.logger import setup_logger_tqdm
import traceback
import json
from pythonjsonlogger import jsonlogger


from .utils import LOGGER, RESULTS_DIR, DatasetName
from .example_wall_times import ExampleWallTime, record_example_wall_time
from .run_goal_decomposition_for_example import (
    ProcessArg,
    ProcessFn,
    run_goal_decomposition_for_example_tuple,
)
from .wall_time_budget import (
    load_cumulative_wall_seconds,
    session_wall_budget_seconds,
)
from src.dataset import (
    Result,
    Example,
    Dataset,
    COQGYM_DEV_SAMPLED_DATASET_BASELINES_FAIL,
    COQGYM_DEV_SAMPLED_DATASET,
    COQGYM_TEST_SAMPLED_DATASET_BASELINES_FAIL,
    COQGYM_TEST_SAMPLED_DATASET,
    COQ_WIGDERSON_DEV_SAMPLED_DATASET_BASELINES_FAIL,
    COQ_WIGDERSON_DEV_SAMPLED_DATASET,
    COQ_WIGDERSON_TEST_SAMPLED_DATASET_BASELINES_FAIL,
    COQ_WIGDERSON_TEST_SAMPLED_DATASET,
    COQ_WIGDERSON_ERROR_ANALYSIS_DATASET,
    COQ_WIGDERSON_DEV_PERFECT_SUBGOALS_DATASET,
    COQ_WIGDERSON_TEST_PERFECT_SUBGOALS_DATASET,
    COQGYM_TEST_PERFECT_SUBGOALS_DATASET,
    COQ_BB5_DEV_DATASET,
    COQ_BB5_TEST_DATASET,
    PNV_ROCQLIB_DEV_DATASET,
    PNV_ROCQLIB_TEST_DATASET,
    PNV_ROCQLIB_RETRYING_SAMPLED_DATASET
)
from src.llm.model_names import OpenaiChatModelName, OPENAI_CHAT_MODEL_NAMES
from src.environment import LemmaContext
from src.llm import Usage
from src.utils import JSON
from src.strategy.goal_decomposition import (
    GoalDecompositionConfig,
    GoalDecompositionStrategy,
    GoalDecomposition_Search_1JSON,
)
from src.coq_serapy_util import LemmaLocation
from src.agent import Agent
from src.environment import Environment


class GoalDecompositionEval:
    uuid: str
    dataset_name: DatasetName
    lemma_context: LemmaContext
    try_hammer: bool
    max_depth: int
    model: OpenaiChatModelName

    dataset: Dataset
    lemmas: t.List[str]

    result: Result
    # if proof is set to None, then we failed on that proof
    proofs: t.Dict[Example, t.Optional[str]]
    # tree searches loaded from files
    runners: t.Dict[Example, t.Optional[GoalDecompositionStrategy]]
    example_wall_timeout_sec: t.Optional[float] = None

    def __init__(
        self,
        uuid: str,
        dataset_name: DatasetName,
        lemma_context: LemmaContext,
        try_hammer: bool,
        max_depth: int,
        lemmas: t.List[str] = [],
        model: OpenaiChatModelName = "gpt-4"
    ):
        self.uuid = uuid
        self.dataset_name = dataset_name
        self.lemma_context = lemma_context
        self.try_hammer = try_hammer
        self.max_depth = max_depth
        self.model = model

        if dataset_name == "dev":
            self.dataset = COQGYM_DEV_SAMPLED_DATASET
            # self.dataset = COQGYM_DEV_SAMPLED_DATASET_BASELINES_FAIL
        elif dataset_name == "test":
            self.dataset = COQGYM_TEST_SAMPLED_DATASET
            # self.dataset = COQGYM_TEST_SAMPLED_DATASET_BASELINES_FAIL
        elif dataset_name == "wigderson_dev":
            self.dataset = COQ_WIGDERSON_DEV_SAMPLED_DATASET
            # self.dataset = COQ_WIGDERSON_DEV_SAMPLED_DATASET_BASELINES_FAIL
        elif dataset_name == "wigderson_test":
            self.dataset = COQ_WIGDERSON_TEST_SAMPLED_DATASET
            # self.dataset = COQ_WIGDERSON_TEST_SAMPLED_DATASET_BASELINES_FAIL
        elif dataset_name == "wigderson_err":
            self.dataset = COQ_WIGDERSON_ERROR_ANALYSIS_DATASET
        elif dataset_name == "wigderson_test_perfect_subgoals":
            self.dataset = COQ_WIGDERSON_TEST_PERFECT_SUBGOALS_DATASET
        elif dataset_name == "test_perfect_subgoals":
            self.dataset = COQGYM_TEST_PERFECT_SUBGOALS_DATASET
        elif dataset_name == "coq_bb5_dev":
            self.dataset = COQ_BB5_DEV_DATASET
        elif dataset_name == "coq_bb5_test":
            self.dataset = COQ_BB5_TEST_DATASET
        elif dataset_name == "pnvrocqlib_dev":
            self.dataset = PNV_ROCQLIB_DEV_DATASET
        elif dataset_name == "pnvrocqlib_test":
            self.dataset = PNV_ROCQLIB_TEST_DATASET
        elif dataset_name == "pnvrocqlib_retrying":
            self.dataset = PNV_ROCQLIB_RETRYING_SAMPLED_DATASET
        else:
            assert dataset_name == "wigderson_dev_perfect_subgoals"
            self.dataset = COQ_WIGDERSON_DEV_PERFECT_SUBGOALS_DATASET

        self.lemmas = lemmas

        self.__load_from_files()

    @property
    def name(self):
        return f"{self.dataset_name}_{'with_hammer' if self.try_hammer else 'no_hammer' }_max_depth_{self.max_depth}_{self.lemma_context}"

    @property
    def directory_path(self):
        return self.result.directory_path

    @property
    def total_nodes_expanded(self):
        runners = self.runners.values()
        num_nodes_expanded = [runner.num_nodes_expanded for runner in runners if runner]
        return sum(num_nodes_expanded)

    @property
    def filtered_dataset(self):
        if len(self.lemmas) == 0:
            return self.dataset
        return [
            example
            for example in self.dataset
            if example.location.lemma_name in self.lemmas
        ]

    def run(
        self,
        num_processes: int,
        max_nodes_to_expand: int,
        example_wall_timeout_sec: t.Optional[float] = None,
    ):
        if example_wall_timeout_sec is not None and example_wall_timeout_sec <= 0:
            example_wall_timeout_sec = None
        self.example_wall_timeout_sec = example_wall_timeout_sec
        LOGGER.info(
            f"expanding up to {max_nodes_to_expand} nodes for each of {len(self.filtered_dataset)} examples",
            extra={
                "num_examples": len(self.filtered_dataset),
                "max_nodes_to_expand": max_nodes_to_expand,
                "example_wall_timeout_sec": example_wall_timeout_sec,
                "uuid": self.uuid,
            },
        )

        tasks: t.List[t.Tuple[ProcessFn, ProcessArg]] = (
            self.__get_multiprocessing_tasks(max_nodes_to_expand)
        )

        if len(tasks) == 0:
            LOGGER.info("no examples to collect more data for")
            return

        pool = TqdmMultiProcessPool(num_processes)
        total_nodes_to_expand = max_nodes_to_expand * len(self.filtered_dataset)
        num_nodes_to_expand = total_nodes_to_expand - self.total_nodes_expanded

        try:
            with tqdm.tqdm(
                total=num_nodes_to_expand, dynamic_ncols=True
            ) as global_progress:
                global_progress.set_description("total progress")
                _proofs = pool.map(
                    global_progress, tasks, self.__error_callback, self.__done_callback
                )
        except Exception as e:
            LOGGER.error(
                "error while running goal decomposition",
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

    def log_info(self, log_tree_states: bool = False):
        print("# goal decomposition")
        print(f"uuid: {self.uuid}")
        print(f"dataset: {self.dataset_name}")
        print(f"lemmas: {self.lemmas}")
        print(f"lemma context: {self.lemma_context}")
        print(f"try hammer: {self.try_hammer}")
        print(f"max depth: {self.max_depth}")

        runner = next(
            (runner for runner in self.runners.values() if runner is not None),
            None
        )
        if runner is not None:
            print(f"model: {runner.config.model}")

        print()

        print("## results")
        print("example, correct, num_nodes_expanded")
        print(
            "all",
            sum(
                1
                for example in self.filtered_dataset
                if example in self.proofs and self.proofs[example] is not None
            ),
            self.total_nodes_expanded,
        )
        for example in sorted(self.filtered_dataset, key=lambda x: x.name):
            correct = self.proofs.get(example, "in progress")
            runner = self.runners.get(example, None)
            num_nodes_expanded = runner.num_nodes_expanded if runner is not None else 0
            print(f"{example.name}, {correct}, {num_nodes_expanded}")
        print()

        print("## usage")
        print("num_tokens: ", self.result.usage.num_tokens)
        print("num_input_tokens: ", self.result.usage.num_input_tokens)
        print("num_output_tokens: ", self.result.usage.num_output_tokens)
        print("num_requests: ", self.result.usage.num_requests)
        print("duration_milliseconds: ", self.result.usage.duration_millis)
        print()

        if log_tree_states:
            for example in sorted(self.filtered_dataset, key=lambda x: x.name):
                runner = self.runners.get(example, None)
                if runner is None:
                    continue
                print(f"## {example.name}")
                print(runner.search.visualize())
                print()

    def __get_multiprocessing_tasks(self, max_nodes_to_expand: int):
        tasks = []
        skipped_wall_timeout = False
        for example in self.filtered_dataset:
            runner = self.runners.get(example, None)
            num_nodes_expanded = runner.num_nodes_expanded if runner is not None else 0
            # recomputing this because we may have increased max_nodes_to_expand
            if max_nodes_to_expand - num_nodes_expanded <= 0:
                LOGGER.info(
                    "skipping example because we have already expanded enough nodes",
                    extra={"example": example.name},
                )
                continue

            proof = self.proofs.get(example)
            if proof is not None:
                continue

            cumulative_wall = load_cumulative_wall_seconds(
                self.directory_path, example.name
            )
            session_budget = session_wall_budget_seconds(
                self.example_wall_timeout_sec, cumulative_wall
            )
            if session_budget is not None and session_budget <= 0:
                LOGGER.info(
                    "skipping example: cumulative wall timeout reached",
                    extra={
                        "example": example.name,
                        "cumulative_wall_seconds": cumulative_wall,
                        "example_wall_timeout_sec": self.example_wall_timeout_sec,
                    },
                )
                self.proofs[example] = None
                self.result.failed_error_messages[
                    example.location.lemma_name
                ] = "wall_timeout"
                skipped_wall_timeout = True
                continue

            task_argument: ProcessArg = (
                example,
                max_nodes_to_expand,
                self.max_depth,
                self.try_hammer,
                self.directory_path,
                self.lemma_context,
                self.model,
                session_budget,
            )
            tasks.append((run_goal_decomposition_for_example_tuple, (task_argument,)))
        if skipped_wall_timeout:
            self.update_result_based_on_samples()
            self.result.write()
        return tasks

    def __error_callback(self, e):
        LOGGER.error(
            f"error in process pool: {e}",
            extra={
                "exception": str(e),
                "stacktrace": traceback.format_exc(),
            },
        )

    def __done_callback(
        self,
        fn_result: t.Tuple[
            Example, t.Optional[str], Usage, ExampleWallTime, bool
        ],
    ):
        example, proof, usage, wall_time, wall_budget_exhausted = fn_result
        LOGGER.info(
            f"done with process pool: {example.name}",
            extra={
                "proof": proof,
                "usage": usage,
                "example": example,
                "duration_seconds": wall_time.duration_seconds,
                "started_at": wall_time.started_at,
                "finished_at": wall_time.finished_at,
            },
        )
        record_example_wall_time(
            self.directory_path,
            example.name,
            wall_time,
        )
        self.proofs[example] = proof
        lemma_name = example.location.lemma_name
        if proof is not None:
            self.result.failed_error_messages.pop(lemma_name, None)
        elif wall_budget_exhausted:
            self.result.failed_error_messages[lemma_name] = "wall_timeout"
        self.result.usage.add_child(usage)
        self.update_result_based_on_samples()
        self.result.write()

    def __load_from_files(self):
        self.result = Result(
            self.name, containing_directory=str(RESULTS_DIR), uuid=self.uuid
        )
        self.__setup_logging()
        LOGGER.info("loading from files", extra={"uuid": self.uuid})

        self.__load_runners_from_files()
        usage = self.__load_usage_from_files()

        self.result = Result(
            self.name,
            containing_directory=str(RESULTS_DIR),
            uuid=self.uuid,
        )
        if usage is not None:
            self.result.usage = usage

        self.update_result_based_on_samples()
        LOGGER.info("done loading from files", extra={"uuid": self.uuid})

    def update_result_based_on_samples(self):
        samples: t.List[t.Tuple[Example, str, bool]] = []
        for example in self.filtered_dataset:
            if example not in self.proofs:
                continue
            proof = self.proofs[example]
            samples.append(
                (example, proof if proof is not None else "", proof is not None)
            )

        self.result.update_based_on_samples(samples)

    def __load_runners_from_files(self):
        LOGGER.info("loading runners from files")
        self.runners = {}
        self.proofs = {}

        if not self.result.directory_path.exists():
            return

        for example in self.filtered_dataset:
            LOGGER.info(f"loading {example.name}", extra={"example": example.name})
            config = self.__get_config_from_file(example)
            if config is None:
                continue

            runner = GoalDecompositionStrategy(
                example, config
            )

            self.runners[example] = runner

            proof = runner.root.proof
            if proof is None:
                self.proofs[example] = None
            else:
                self.proofs[example] = proof

        # override the model we were set with if this uuid was previously run with a different model
        if any(r is not None for r in self.runners.values()):
            runner = next(r for r in self.runners.values() if r is not None)
            self.model = runner.config.model

        LOGGER.info("done loading runners from files")

    def __load_usage_from_files(self) -> t.Optional[Usage]:
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

    def __get_config_from_file(
        self, example: Example
    ) -> t.Optional[GoalDecompositionConfig]:
        state_file = self.directory_path / f"{example.name}.json"
        if not state_file.exists():
            return None

        state_json: GoalDecomposition_Search_1JSON = json.load(state_file.open("r"))
        return GoalDecompositionConfig.from_json(
            t.cast(t.Dict[str, JSON], state_json["config"])
        )

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
