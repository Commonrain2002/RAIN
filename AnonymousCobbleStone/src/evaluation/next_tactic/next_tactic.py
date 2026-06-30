import typing as t
import tqdm
from tqdm_multiprocess import TqdmMultiProcessPool
from tqdm_multiprocess.logger import setup_logger_tqdm
import traceback
import json
from pythonjsonlogger import jsonlogger

from .utils import LOGGER, RESULTS_DIR
from .task import run_tbt_for_example_tuple
from src.dataset import (
    DatasetName,
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
)
from src.environment import LemmaContext
from src.llm import Usage
from src.utils import JSON
from src.strategy.next_tactic import (
    NextTacticConfig,
    NextTacticStrategy,
    Search as NextTacticSearch,
    SearchJSON as NextTacticSearchJSON,
)
from src.coq_serapy_util import LemmaLocation
from src.agent import Agent
from src.environment import Environment


class NextTacticEval:
    uuid: str
    dataset_name: DatasetName
    lemma_context: LemmaContext
    try_hammer: bool
    max_depth: int

    dataset: Dataset
    lemmas: t.List[str]

    result: Result
    proofs: t.Dict[Example, t.Optional[str]]
    runners: t.Dict[Example, t.Optional[NextTacticStrategy]]

    def __init__(
        self,
        uuid: str,
        dataset_name: DatasetName,
        lemma_context: LemmaContext,
        try_hammer: bool,
        max_depth: int,
        lemmas: t.List[str] = [],
    ) -> None:
        self.uuid = uuid
        self.dataset_name = dataset_name
        self.lemma_context = lemma_context
        self.try_hammer = try_hammer
        self.max_depth = max_depth
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
        elif dataset_name == "wigderson_err":
            self.dataset = COQ_WIGDERSON_ERROR_ANALYSIS_DATASET
        elif dataset_name == "wigderson_test_perfect_subgoals":
            self.dataset = COQ_WIGDERSON_TEST_PERFECT_SUBGOALS_DATASET
        else:
            assert dataset_name == "wigderson_dev_perfect_subgoals"
            self.dataset = COQ_WIGDERSON_DEV_PERFECT_SUBGOALS_DATASET

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

    def run(self, num_processes: int, max_nodes_to_expand: int) -> None:
        LOGGER.info(
            f"expanding up to {max_nodes_to_expand} nodes for each of {len(self.filtered_dataset)} examples",
            extra={
                "num_examples": len(self.filtered_dataset),
                "max_nodes_to_expand": max_nodes_to_expand,
                "uuid": self.uuid,
            },
        )

        tasks = self.__get_multiprocessing_tasks(max_nodes_to_expand)

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
                "error while starting multiprocessing pool",
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

    def log_info(self, log_tree_states: bool = False) -> None:
        print("# tactic by tactic search")
        print(f"uuid: {self.uuid}")
        print(f"dataset: {self.dataset_name}")
        print(f"lemmas: {self.lemmas}")
        print(f"lemma context: {self.lemma_context}")
        print(f"try hammer: {self.try_hammer}")
        print(f"max depth: {self.max_depth}")
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
        print("duration_millis: ", self.result.usage.duration_millis)
        print()

        if log_tree_states:
            print("## tree states")
            for example in sorted(self.filtered_dataset, key=lambda x: x.name):
                runner = self.runners.get(example, None)
                if runner is None:
                    continue
                print(f"### {example.name}")
                print(runner.search.visualize())
                print()

    def __load_from_files(self) -> None:
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

        self.__update_result_based_on_samples()
        LOGGER.info("done loading from files", extra={"uuid": self.uuid})

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
                LOGGER.info(
                    f"no config found for {example.name}",
                    extra={"example": example.name},
                )
                continue

            runner = NextTacticStrategy(example, config)

            self.runners[example] = runner

            proof = runner.proof
            if proof is None:
                self.proofs[example] = None
            else:
                self.proofs[example] = proof
        LOGGER.info("done loading runners from files")

    def __get_config_from_file(self, example: Example) -> t.Optional[NextTacticConfig]:
        state_file = self.directory_path / f"{example.name}.json"
        if not state_file.exists():
            return None

        state_json: NextTacticSearchJSON = json.load(state_file.open("r"))
        return NextTacticConfig.from_json(
            t.cast(t.Dict[str, JSON], state_json["config"])
        )

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

    def __get_multiprocessing_tasks(self, max_nodes_to_expand: int):
        tasks = []
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
            task_argument = (
                example,
                max_nodes_to_expand,
                self.max_depth,
                self.try_hammer,
                self.directory_path,
                self.lemma_context,
            )
            tasks.append((run_tbt_for_example_tuple, (task_argument,)))
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
