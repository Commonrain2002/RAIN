import time
from dataclasses import dataclass
import typing as t
import coq_serapy as c
from tqdm import tqdm
from pathlib import Path
from uuid import uuid4

from src.proof_script import Tactic
from src.config import CONFIG
from src.utils import set_run_uuid, set_log_file, set_example_name
from src.coq_serapy_util import LemmaLocation, is_initial_goal_proven
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

LOGGER = get_logger("strategy.hammer")


class HammerNode__ValueJSON(t.TypedDict):
    proof_state: t.Dict[str, JSON]
    # decomposition: t.Optional[HammerJSON] # TODO
    tactic: t.Optional[str]


@dataclass(frozen=True)
class HammerNode__Value:
    proof_state: c.contexts.ProofContext
    example: Example  # item in the dataset
    tactic: t.Optional[str]
    # whether or not tactic is a hammer reconstruction tactic
    is_hammer: bool = False

    def to_json(self) -> HammerNode__ValueJSON:
        return {
            "proof_state": self.proof_state.to_dict(),
            "tactic": self.tactic,
        }

    @classmethod
    def from_json(
        cls, json: t.Dict[str, JSON], example: Example
    ) -> "HammerNode__Value":
        return cls(
            proof_state=c.contexts.ProofContext.from_dict(json["proof_state"]),
            example=example,
            tactic=t.cast(t.Optional[str], json["tactic"]),
        )

    def __hash__(self) -> int:
        # return hash(tuple(self.goals))
        return hash(
            (
                tuple(self.proof_state.fg_goals),
                tuple(self.proof_state.bg_goals),
                tuple(self.proof_state.shelved_goals),
                tuple(self.proof_state.given_up_goals),
                self.example,
                self.tactic,
            )
        )


class HammerNode(Node[HammerNode__Value]):
    """
    A node with a "hammer" value
    """

    parent: t.Optional["HammerNode"]
    children: t.List["HammerNode"]

    def __init__(
        self,
        value: HammerNode__Value,
        parent: Node | None,
        # config: ___,
        uuid: t.Optional[str] = None,
    ):
        super().__init__(value, parent, uuid)
        self.children = []

    def _generate_new_children(
        self, discard_children: bool
    ) -> t.Optional[t.List["HammerNode"]]:

        if (
            len(self.children) > 0 and self.children[0].value.is_hammer
        ):  # I've already generated a child that is hammer (check children)
            return []
        LOGGER.info("trying hammer")
        result = self.__try_hammer()
        LOGGER.info(
            "tried hammer",
            extra={"result": result},
        )
        if result is None:
            return None

        # make new value and new node to serve as child (if hammer is successful, then we want to add "hammer" as a child)
        proof_state = result[0]
        assert proof_state is not None, "proof state should not be None"
        val = HammerNode__Value(proof_state, self.value.example, result[1].text, True)
        new_child = HammerNode(val, self)
        self.children.append(new_child)
        return [new_child]

    @property
    def num_children(self) -> int:
        return len(self.children)

    @property
    def children_to_visualize(self) -> t.List["HammerNode"]:
        return self.children

    def is_goal(self) -> bool:
        return self.value.is_hammer

    @property
    def label(self) -> str:
        return str(self.value)

    def __try_hammer(self) -> t.Optional[t.Tuple[c.contexts.ProofContext, Tactic]]:
        """
        attempt to prove the goal with the hammer tactic
        If the tactic is successful, then this node is set to proven, and will be expanded no further. This method will return the successful environment.
        If the tactic fails, this method will return None.
        """

        LOGGER.info("making agent and environment")
        _, environment = make_agent_and_environment(
            self.value.example.proposition_command,
            self.value.example.hint,
            self.value.example.location,
            self.value.example.proof_prefix,
        )
        LOGGER.info("made agent and environment")

        try:
            LOGGER.info("running edit action")
            coq = environment.coq
            # tactic = Tactic(
            #     "hammer."
            # )
            # result = tactic.run(coq)

            hammer = Tactic("hammer.")
            result, reconstruction_tactic = (
                hammer.run_hammer_and_get_reconstruction_tactic(coq)
            )
            LOGGER.info(
                "hammer result",
                extra={"result": result, "reconstruction_tactic": reconstruction_tactic},
            )
            if isinstance(result, c.contexts.ProofContext) and is_initial_goal_proven(
                environment.initial_proof_context, result, None, False
            ) and reconstruction_tactic is not None:
                return result, reconstruction_tactic
            else:
                return None

        except Exception as e:

            return None
        # return environment


class HammerStrategy:
    example: Example
    search: Bfs[HammerNode__Value]

    def __init__(
        self,
        example: Example,
    ) -> None:
        self.example = example
        self.search = self.__make_search()

    def __make_root_node(
        self,
    ) -> HammerNode:
        _, environment = make_agent_and_environment(
            self.example.proposition_command,
            self.example.hint,
            self.example.location,
            self.example.proof_prefix,
        )
        proof_state = environment.proof_context
        assert proof_state is not None, "initial environment should have a proof state"
        return HammerNode(
            value=HammerNode__Value(
                proof_state=proof_state,
                example=self.example,
                tactic=None,
            ),
            parent=None,
        )

    def run(
        self, global_tqdm: Tqdm, tqdm_func: TqdmFunc
    ) -> t.Tuple[t.Optional[Environment], Usage]:
        for proven_node in self.search.search(
            global_tqdm,
            tqdm_func,
            progress_bar_desc=self.example.name[: len("total progress")],
        ):
            _, environment = make_agent_and_environment(
                self.example.proposition_command,
                self.example.hint,
                self.example.location,
                self.example.proof_prefix,
            )
            code = proven_node.value.tactic
            assert code is not None, "proven node should have a tactic"
            environment.step(EditAction(new_code=code))
            return environment, Usage("hammer_search")
        return None, Usage("hammer_search")

    def __make_search(self) -> Bfs:
        return Bfs(
            self.__make_root_node(),
            BfsConfig(max_nodes_to_expand=1, max_num_children_per_node=1),
        )


RESULTS_DIR = (Path(CONFIG.ROOT_DIR) / "data/evaluation/hammer").resolve().absolute()
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


class HammerEval:
    uuid: str
    dataset_name: DatasetName

    dataset: Dataset
    lemmas: t.List[str]

    result: Result
    # if proof is set to None, then we failed on that proof
    proofs: t.Dict[Example, t.Optional[str]]
    # tree searches loaded from files
    runners: t.Dict[Example, t.Optional[HammerStrategy]]  # TODO: define strategy

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

    def run_eval(self):
        with tqdm(total=len(self.filtered_dataset), dynamic_ncols=True) as global_tqdm:

            for example in self.filtered_dataset:
                # if ("indep_set_ok" not in example.name):
                #     continue
                set_example_name(example.name)
                strategy = HammerStrategy(example)
                tqdm_func = t.cast(TqdmFunc, tqdm)
                environment, usage = strategy.run(global_tqdm, tqdm_func)

                if environment is not None:  # and environment.is_initial_goal_proven:
                    self.result.successful_examples.append(example)
                    self.proofs[example] = "hammer."
                    tqdm.write("success")
                else:
                    self.result.failed_examples.append(example)
                    self.proofs[example] = None
                    tqdm.write("failure")
                self.result.usage.add_child(usage)

                self.result.write()


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

    dataset_name = "pnvrocqlib_test"
    hammer = HammerEval(uuid, dataset_name)

    hammer.run_eval()


if __name__ == "__main__":
    main()
