import time
from dataclasses import dataclass
import typing as t
import coq_serapy as c
from tqdm import tqdm
from pathlib import Path
from uuid import uuid4
import traceback
from tqdm_multiprocess import TqdmMultiProcessPool
from tqdm_multiprocess.logger import setup_logger_tqdm
from pythonjsonlogger import jsonlogger


from src.proof_script import Tactic
from src.config import CONFIG
from src.utils import set_run_uuid, set_log_file, set_example_name
from src.coq_serapy_util import CoqError, LemmaLocation, is_initial_goal_proven
from src.agent import Agent
from src.agent.next_tactic import NextTacticAgent, NextTacticAgentConfig
from src.tree_search import (
    Node,
    Bfs,
    BfsConfig,
)
from src.dataset import (
    Result,
    Example,
    Dataset,
    COQGYM_DEV_SAMPLED_DATASET,
    COQGYM_TEST_SAMPLED_DATASET,
    COQ_WIGDERSON_DEV_SAMPLED_DATASET,
    COQ_WIGDERSON_TEST_SAMPLED_DATASET,
    PNV_ROCQLIB_DEV_DATASET,
    PNV_ROCQLIB_TEST_DATASET,
    COQ_BB5_DEV_DATASET,
    COQ_BB5_TEST_DATASET,
)

from src.utils import TqdmFunc, Tqdm, get_logger
from src.environment import Environment, EditAction, EnvironmentConfig
from src.strategy import MakeAgentAndEnvironment
from src.dataset import Example
from src.llm import Usage, OpenaiChatPromptConfig
from src.utils import JSON  # get_logger

LOGGER = get_logger("strategy.tactician")


class TacticianStrategy:
    example: Example

    def __init__(
        self,
        example: Example,
    ) -> None:
        self.example = example

    def run(
        self, global_tqdm: Tqdm, tqdm_func: TqdmFunc
    ) -> t.Tuple[bool, Usage]:
        try:
            result = self.__try_synth()
            global_tqdm.update()
            return result, Usage("Tactician")
        except Exception as e:
            LOGGER.error("error in try_synth", extra={"error": e, "stacktrace": traceback.format_exc()})
            global_tqdm.update()
            return False, Usage("Tactician")

    def __try_synth(self) -> bool:
        _, environment = make_agent_and_environment(
            self.example.proposition_command,
            self.example.hint,
            self.example.location,
            self.example.proof_prefix,
        )

        try:
            LOGGER.info("running synth")
            synth = Tactic("synth.")
            result = synth.run(environment.coq, timeout_seconds=200)
            feedbacks = environment.coq.get_feedbacks()
            LOGGER.info("ran synth", extra={"result": result, "feedbacks": feedbacks})
            if isinstance(result, CoqError):
                LOGGER.error("error in try_synth", extra={"error": result})
                return False
            if not any(f.level == "Info" and "Tactician found a proof!" in f.message for f in feedbacks):
                LOGGER.error("no proof found")
                return False
            LOGGER.info("ran synth successfully")
            return True
        except Exception as e:
            LOGGER.error("error in try_synth", extra={"error": e})
            return False


RESULTS_DIR = (Path(CONFIG.ROOT_DIR) / "data/evaluation/tactician").resolve().absolute()
DatasetName = t.Literal[
    "dev",
    "test",
    "wigderson_dev",
    "wigderson_test",
    "wigderson_dev_perfect_subgoals",
    "pnvrocqlib_dev",
    "pnvrocqlib_test",
    "coq_bb5_dev",
    "coq_bb5_test",
]
DATASET_NAMES: t.List[DatasetName] = [
    "dev",
    "test",
    "wigderson_dev",
    "wigderson_test",
    "wigderson_dev_perfect_subgoals",
    "pnvrocqlib_dev",
    "pnvrocqlib_test",
    "coq_bb5_dev",
    "coq_bb5_test",
]

ProcessArg = Example
ProcessFn = t.Callable[
    [ProcessArg, t.Any, t.Any], t.Tuple[t.List[t.Tuple[Example, str, bool]], Usage]
]

class TacticianEval:
    uuid: str
    dataset_name: DatasetName

    dataset: Dataset
    lemmas: t.List[str]

    result: Result
    # if proof is set to None, then we failed on that proof
    proofs: t.Dict[Example, t.Optional[str]]
    # tree searches loaded from files
    runners: t.Dict[Example, t.Optional[TacticianStrategy]]  # TODO: define strategy

    def __init__(
        self,
        uuid: str,
        dataset_name: DatasetName,
        lemmas: t.List[str] = [],
    ):
        self.uuid = uuid
        self.dataset_name = dataset_name

        if dataset_name == "dev":
            self.dataset = COQGYM_DEV_SAMPLED_DATASET
        elif dataset_name == "test":
            self.dataset = COQGYM_TEST_SAMPLED_DATASET
        elif dataset_name == "wigderson_dev":
            self.dataset = COQ_WIGDERSON_DEV_SAMPLED_DATASET
        elif dataset_name == "wigderson_test":
            self.dataset = COQ_WIGDERSON_TEST_SAMPLED_DATASET
        elif dataset_name == "pnvrocqlib_dev":
            self.dataset = PNV_ROCQLIB_DEV_DATASET
        elif dataset_name == "pnvrocqlib_test":
            self.dataset = PNV_ROCQLIB_TEST_DATASET
        elif dataset_name == "coq_bb5_dev":
            self.dataset = COQ_BB5_DEV_DATASET
        elif dataset_name == "coq_bb5_test":
            self.dataset = COQ_BB5_TEST_DATASET
        else:
            raise ValueError(f"unknown dataset name: {dataset_name}")

        self.lemmas = lemmas

        self.result = Result(
            self.name, containing_directory=str(RESULTS_DIR), uuid=self.uuid
        )
        self.proofs = {}

        set_log_file(self.result.log_file_path)

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
    def name(self):
        return f"{self.dataset_name}"

    @property
    def directory_path(self):
        return self.result.directory_path

    def run_eval(self, num_processes: int):
        self.__setup_logging()

        LOGGER.info(
            f"running tactician for each of {len(self.filtered_dataset)} proofs",
            extra={
                "num_examples": len(self.filtered_dataset),
                "uuid": self.uuid,
            },
        )

        pool = TqdmMultiProcessPool(num_processes)
        tasks: t.List[t.Tuple[ProcessFn, ProcessArg]] = (
            self.__get_multiprocessing_tasks()
        )

        try:
            with tqdm(total=len(self.filtered_dataset), dynamic_ncols=True) as global_tqdm:
                global_tqdm.set_description("total progress")
                _sampleses: t.List[
                    t.Tuple[t.List[t.Tuple[Example, str, bool]], Usage]
                ]  = pool.map(
                    global_tqdm, tasks, self.__error_callback, self.__done_callback
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

                # for example in self.filtered_dataset:
                # # if ("indep_set_ok" not in example.name):
                # #     continue
                # set_example_name(example.name)
                # strategy = TacticianStrategy(example)
                # tqdm_func = t.cast(TqdmFunc, tqdm)
                # success, usage = strategy.run(global_tqdm, tqdm_func)

                # if success:  # and environment.is_initial_goal_proven:
                #     self.result.successful_examples.append(example)
                #     self.proofs[example] = "hammer."
                #     tqdm.write("success")
                # else:
                #     self.result.failed_examples.append(example)
                #     self.proofs[example] = None
                #     tqdm.write("failure")
                # self.result.usage.add_child(usage)

                # self.result.write()
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

    def __get_multiprocessing_tasks(
        self, 
    ) -> t.List[t.Tuple[ProcessFn, ProcessArg]]:
        tasks = []
        for example in self.filtered_dataset:
            tasks.append((run_tactician_for_example, (example,))) 

        return tasks



def run_tactician_for_example(
    example: Example,
    tqdm_func: TqdmFunc,
    global_tqdm: Tqdm,
) -> t.Tuple[t.List[t.Tuple[Example, str, bool]], Usage]:
    set_example_name(example.name)
    strategy = TacticianStrategy(example)
    result, usage = strategy.run(global_tqdm, tqdm_func)
    return [(example, "", result)], usage


def make_agent_and_environment(
    proposition_command: str,
    hint: t.Optional[str],
    location: t.Optional[LemmaLocation],
    proof_prefix: t.Optional[str],
):
    # PropositionCommand, Hint, t.Optional[LemmaLocation], t.Optional[ProofPrefix]

    # not going to be used right now
    agent = NextTacticAgent(
        proposition_command,
        config=NextTacticAgentConfig(
            include_reasoning=True, chat_config=OpenaiChatPromptConfig()
        ),
    )

    environment = Environment(
        proposition_command,
        lemma_location=location,
        proof_prefix=proof_prefix,
        config=EnvironmentConfig(
            done_condition="initial-goal-or-decomposition",
            lemma_context="none",
        ),
    )
    return agent, environment


def main():
    # configure_logger()
    uuid = uuid4().hex

    set_run_uuid(uuid)

    # set_log_file(self.result.log_file_path)

    dataset_name = "wigderson_test"
    tactician = TacticianEval(uuid, dataset_name, [
        "phase2_ok",
        "max_deg_gt_not_empty",
        "max_deg_subgraph_inv",
        "remove_max_deg_adj'",
        "indep_set_union"
    ])

    tactician.run_eval(num_processes=5)


if __name__ == "__main__":
    main()
