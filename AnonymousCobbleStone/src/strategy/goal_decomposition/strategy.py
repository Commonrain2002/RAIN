import typing as t
import json
import coq_serapy as c

from .utils import GoalDecompositionConfig, LOGGER, get_root_json
from .node import GoalDecompositionNode, GoalDecompositionNode__Value
from .tree_search import GoalDecomposition_Search_1, GoalDecomposition_Search_1JSON
from src.utils import TqdmFunc, Tqdm
from src.environment import Environment, EditAction
from src.strategy import MakeAgentAndEnvironment
from src.dataset import Example
from src.llm import Usage


class GoalDecompositionStrategy:
    example: Example
    config: GoalDecompositionConfig
    state_json: t.Optional[GoalDecomposition_Search_1JSON]
    search: GoalDecomposition_Search_1

    def __init__(
        self,
        example: Example,
        config: GoalDecompositionConfig,
    ) -> None:
        self.example = example
        self.config = config
        self.__load_state()
        self.search = self.__make_search()

    @property
    def num_nodes_expanded(self):
        if self.state_json is None:
            return 0
        return (
            self.state_json["config"]["max_nodes_to_expand"]
            - self.state_json["remaining_nodes_to_expand"]
        )

    def run(
        self, global_tqdm: Tqdm, tqdm_func: TqdmFunc
    ) -> t.Tuple[t.Optional[Environment], Usage]:
        for proven_node in self.search.search(
            global_tqdm,
            tqdm_func,
            progress_bar_desc=self.example.name[: len("total progress")],
        ):
            LOGGER.info(
                f"proved goal: {proven_node.value.obligation.goal}",
                extra={"proof": t.cast(GoalDecompositionNode, proven_node).proof},
            )

        return self.compute_final_environment(), self.search.compute_usage()

    @property
    def root(self):
        return t.cast(GoalDecompositionNode, self.search.nodes[self.search.root])

    @property
    def root_json(self):
        if self.state_json is None:
            return None
        return get_root_json(self.state_json)

    def compute_final_environment(self) -> t.Optional[Environment]:
        root_json = self.root_json
        if root_json is None:
            return None
        proof = root_json["proof"]

        if proof is None:
            return None

        _, environment = self.config.make_agent_and_environment(
            False,
            False,
            # ---
            self.example.proposition_command,
            None,
            self.example.location,
            None,
        )
        environment.step(EditAction(new_code=proof))
        return environment

    def __make_search(self) -> GoalDecomposition_Search_1:
        return GoalDecomposition_Search_1.from_state_file(self.config, self.example)

    def __load_state(self):
        if self.config.state_file.exists():
            with self.config.state_file.open("r") as f:
                self.state_json = json.load(f)
        else:
            self.state_json = None
