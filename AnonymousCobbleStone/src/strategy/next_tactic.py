import time
import json
from dataclasses import dataclass
import typing as t
import coq_serapy as c
from tqdm import tqdm
from pathlib import Path
from uuid import uuid4
from itertools import product

from src.proof_script import Tactic
from src.config import CONFIG
from src.utils import set_run_uuid, set_log_file, set_example_name
from src.coq_serapy_util import (
    CoqError,
    LemmaLocation,
    is_initial_goal_proven,
    is_initial_goal_proven_multiple_fg_goals,
    Coq,
)
from src.agent import Agent
from src.tree_search import TreeSearchConfig, TreeSearch
from src.environment import LemmaContext

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
)

from src.utils import TqdmFunc, Tqdm
from src.environment import Environment, EditAction, EnvironmentConfig
from src.strategy import MakeAgentAndEnvironment
from src.dataset import Example
from src.llm import Usage, OpenaiChatPromptConfig
from src.utils import JSON, get_logger
from src.agent.zero_shot_tool import ZeroShotToolAgent, ZeroShotToolAgentConfig
from src.premise_selection import select_premises
from src.coq_serapy_util import proof_context_to_str


LOGGER = get_logger("next_tactic_search")


class NextTacticConfigJSON(t.TypedDict):
    lemma_context: LemmaContext
    state_file: str
    max_num_children_per_node: int
    max_depth: int
    try_hammer: bool
    max_nodes_to_expand: int
    premise_names: t.Optional[t.List[str]]
    proof_prefix: t.Optional[str]


@dataclass
class NextTacticConfig(TreeSearchConfig):
    lemma_context: LemmaContext
    state_file: Path
    max_depth: int = 5
    max_num_children_per_node: int = 3
    try_hammer: bool = True
    proof_prefix: t.Optional[str] = None
    premise_names: t.Optional[t.List[str]] = None

    def to_json(self) -> NextTacticConfigJSON:
        return {
            "lemma_context": self.lemma_context,
            "state_file": str(self.state_file),
            "max_depth": self.max_depth,
            "max_num_children_per_node": self.max_num_children_per_node,
            "try_hammer": self.try_hammer,
            "max_nodes_to_expand": self.max_nodes_to_expand,
            "proof_prefix": self.proof_prefix,
            "premise_names": self.premise_names,
        }

    @classmethod
    def from_json(cls, data: t.Dict[str, JSON]) -> "NextTacticConfig":
        return cls(
            max_nodes_to_expand=t.cast(int, data["max_nodes_to_expand"]),
            lemma_context=t.cast(LemmaContext, data["lemma_context"]),
            state_file=Path(t.cast(str, data["state_file"])),
            max_depth=t.cast(int, data["max_depth"]),
            max_num_children_per_node=t.cast(int, data["max_num_children_per_node"]),
            try_hammer=t.cast(bool, data["try_hammer"]),
            proof_prefix=t.cast(t.Optional[str], data["proof_prefix"]),
            premise_names=(
                t.cast(t.Optional[t.List[str]], data["premise_names"])
                if "premise_names" in data
                else None
            ),
        )

    def make_agent_and_environment(
        self,
        include_lemma_context: bool,
        include_reasoning: bool,
        # ---
        proposition_command: str,
        hint: t.Optional[str],
        location: t.Optional[LemmaLocation],
        proof_prefix: t.Optional[str],
    ) -> t.Tuple[Agent, Environment]:
        final_proof_prefix: t.Optional[str] = (
            "" if self.proof_prefix is None else self.proof_prefix
        )
        if proof_prefix is not None:
            final_proof_prefix += proof_prefix

        if final_proof_prefix.strip() == "":
            final_proof_prefix = None

        agent = ZeroShotToolAgent(
            proposition_command,
            config=ZeroShotToolAgentConfig(
                include_reasoning=include_reasoning,
                chat_config=OpenaiChatPromptConfig(model="gpt-4", n=1),
            ),
        )

        environment = Environment(
            proposition_command,
            lemma_location=location,
            proof_prefix=final_proof_prefix,
            config=EnvironmentConfig(
                done_condition="initial-goal-or-decomposition",
                lemma_context=(self.lemma_context if include_lemma_context else "none"),
            ),
        )
        return agent, environment


class NextTacticNode__ValueJSON(t.TypedDict):
    initial_proof_state: t.Dict[str, JSON]
    proof_state: t.Dict[str, JSON]
    tactic: t.Optional[str]


@dataclass(frozen=True)
class NextTacticNode__Value:
    initial_proof_state: c.contexts.ProofContext
    proof_state: c.contexts.ProofContext
    example: Example  # item in the dataset
    tactic: t.Optional[str]

    def to_json(self) -> NextTacticNode__ValueJSON:
        return {
            "initial_proof_state": self.initial_proof_state.to_dict(),
            "proof_state": self.proof_state.to_dict(),
            "tactic": self.tactic,
        }

    @classmethod
    def from_json(
        cls, json: t.Dict[str, JSON], example: Example
    ) -> "NextTacticNode__Value":
        return cls(
            initial_proof_state=c.contexts.ProofContext.from_dict(
                json["initial_proof_state"]
            ),
            proof_state=c.contexts.ProofContext.from_dict(json["proof_state"]),
            example=example,
            tactic=t.cast(t.Optional[str], json["tactic"]),
        )

    def __hash__(self) -> int:
        # return hash(tuple(self.goals))
        return hash(
            (
                tuple(self.initial_proof_state.fg_goals),
                tuple(self.initial_proof_state.bg_goals),
                tuple(self.initial_proof_state.shelved_goals),
                tuple(self.initial_proof_state.given_up_goals),
                tuple(self.proof_state.fg_goals),
                tuple(self.proof_state.bg_goals),
                tuple(self.proof_state.shelved_goals),
                tuple(self.proof_state.given_up_goals),
                self.example,
                self.tactic,
            )
        )


class NextTacticNodeJSON(t.TypedDict):
    uuid: str
    parent_uuid: t.Optional[str]
    value: NextTacticNode__ValueJSON
    depth: int
    num_failed_attempts_to_generate_children: int
    children_uuids: t.List[str]
    proof: t.Optional[str]
    lemmas: t.Optional[t.List[str]]
    attempts: t.List[str]
    failed_attempts: t.List[str]


class NextTacticNode(Node[NextTacticNode__Value]):
    """
    A node with a "hammer" value
    """

    parent: t.Optional["NextTacticNode"]
    children: t.List["NextTacticNode"]
    config: NextTacticConfig
    usage: Usage

    attempts: t.List[str]
    failed_attempts: t.List[str]

    lemmas: t.Optional[t.List[str]]

    tried_hammer: bool

    def __init__(
        self,
        value: NextTacticNode__Value,
        parent: Node | None,
        config: NextTacticConfig,
        uuid: t.Optional[str] = None,
    ):
        super().__init__(value, parent, uuid)
        self.children = []
        self.config = config
        self.usage = Usage(name="next_tactic_node")

        self.attempts = []
        self.failed_attempts = []
        self.tried_hammer = False

        self.lemmas = None

    def proof(self):
        tactics: t.List[str] = []
        current_node = self
        while current_node is not None:
            if current_node.value.tactic is not None:
                tactics = [current_node.value.tactic] + tactics
            current_node = current_node.parent
        return tactics

    # the way this node is serialized, its children come after it in the list
    def to_json(self) -> t.List[NextTacticNodeJSON]:
        proof = " ".join(self.proof())
        self_json: NextTacticNodeJSON = {
            "uuid": self.uuid,
            "parent_uuid": self.parent.uuid if self.parent is not None else None,
            "value": self.value.to_json(),
            "depth": self.depth,
            "num_failed_attempts_to_generate_children": self.num_failed_attempts_to_generate_children,
            "children_uuids": [child.uuid for child in self.children],
            "proof": proof,
            "lemmas": self.lemmas,
            "attempts": self.attempts,
            "failed_attempts": self.failed_attempts,
        }

        children_json = [child.to_json() for child in self.children]

        flat_children_json = [
            child_json
            for children_json in children_json
            for child_json in children_json
        ]

        return [self_json] + flat_children_json

    # this from_json method requires children to be deserialized before parents
    @classmethod
    def from_json(
        cls,
        # a reversed version of the serialized list, with
        # children before parents
        jsons: t.List[t.Dict[str, JSON]],
        nodes: t.Dict[str, "NextTacticNode"],
        config: NextTacticConfig,
        example: Example,
    ) -> t.Dict[str, "NextTacticNode"]:
        json: t.Dict[str, JSON] = jsons.pop(0)

        value = NextTacticNode__Value.from_json(
            t.cast(t.Dict[str, JSON], json["value"]),
            example,
        )
        node = cls(
            value,
            None,
            config,
            t.cast(str, json["uuid"]),
        )
        node.depth = t.cast(int, json["depth"])
        node.num_failed_attempts_to_generate_children = t.cast(
            int, json["num_failed_attempts_to_generate_children"]
        )
        node.children = [
            nodes[uuid] for uuid in t.cast(t.List[str], json["children_uuids"])
        ]
        for child in node.children:
            child.parent = node

        node.lemmas = t.cast(t.Optional[t.List[str]], json["lemmas"])

        node.attempts = t.cast(t.List[str], json.get("attempts", []))
        node.failed_attempts = t.cast(t.List[str], json.get("failed_attempts", []))

        nodes = {**nodes, node.uuid: node}

        if len(jsons) > 0:
            return cls.from_json(jsons, nodes, config, example)
        else:
            return nodes

    def _generate_new_children(
        self, discard_children: bool
    ) -> t.Optional[t.List["NextTacticNode"]]:
        # prevents too many environments from being created
        Environment.teardown_all()

        # shorter than proverbot paper b/c we're using fewer inferences
        MAX_TREE_WIDTH = 3
        if (
            # don't prune a root
            self.parent is not None
            and len(self.children) + self.num_failed_attempts_to_generate_children
            >= MAX_TREE_WIDTH
        ):
            return []

        if self.is_goal():
            return None

        if (
            len(self.children) > 0
        ):  # I've already generated a child that is hammer (check children)
            for child in self.children:
                if child.value.tactic == "hammer.":
                    return []
        if self.config.try_hammer:
            child = self.__try_hammer_and_add_child()
            if child is not None:
                return [child]

        tactic = self.__generate_tactic()
        if tactic is None or tactic.strip() == "":
            LOGGER.info("generate_tactic returned No tactic/an empty tactic")
            return None

        LOGGER.info("generated tactic", extra={"tactic": tactic})
        self.attempts.append(tactic)

        if any(child.value.tactic == tactic for child in self.children):
            LOGGER.info(
                "tactic is already a child",
                extra={"tactic": tactic},
            )
            return None

        # setup a coq environment to run the tactic
        # TODO: make this also use the existing machinery to make agent/env
        coq = self.__get_coq_for_current_node()
        try:
            assert tactic is not None, "tactic should not be None"
            coq.run_command(tactic)
            proof_state = coq.proof_context
            assert proof_state is not None, "proof state should not be None"
            val = NextTacticNode__Value(
                self.value.initial_proof_state, proof_state, self.value.example, tactic
            )
            new_child = NextTacticNode(val, self, self.config)
            self.children.append(new_child)
            return [new_child]
        except Exception as e:
            self.failed_attempts.append(tactic)
            LOGGER.info(
                "failed to generate new children with tactic",
                extra={"error": str(e), "tactic": tactic},
            )
            return None
        finally:
            try:
                coq.teardown()
            except:
                # usually these are pid not found
                pass

    @property
    def num_children(self) -> int:
        return len(self.children)

    @property
    def children_to_visualize(self) -> t.List["NextTacticNode"]:
        return self.children

    def is_goal(self) -> bool | None:
        return is_initial_goal_proven(
            self.value.initial_proof_state, self.value.proof_state, None
        )

    @property
    def label(self) -> str:
        return f"{self.value.tactic} -> {len(self.value.proof_state.all_goals)} goals"

    def __try_hammer_and_add_child(self) -> t.Optional["NextTacticNode"]:
        """
        attempt to prove the goal with the hammer tactic
        if the hammer succeeds, then add a child with the reconstuction tactic
        """

        if self.tried_hammer:
            return None

        coq = self.__get_coq_for_current_node()

        initial_proof_context = coq.proof_context
        assert (
            initial_proof_context is not None
        ), "initial proof context should not be None"

        LOGGER.info(
            "trying hammer",
            extra={
                "node": self.label,
                "context": proof_context_to_str(initial_proof_context),
            },
        )

        hammer = Tactic("hammer.")

        try:
            result, reconstruction_tactic = (
                hammer.run_hammer_and_get_reconstruction_tactic(coq)
            )

            if isinstance(result, CoqError):
                LOGGER.info(
                    "hammer failed",
                    extra={
                        "node": self.label,
                        "error": result.message,
                    },
                )
                return None

            proof_context = coq.proof_context
            assert proof_context is not None, "proof context should not be None"

            if (
                is_initial_goal_proven_multiple_fg_goals(
                    initial_proof_context, proof_context, None, True
                )
                and reconstruction_tactic is not None
            ):
                LOGGER.info(
                    "hammer succeeded",
                    extra={
                        "node": self.label,
                        "reconstruction_tactic": reconstruction_tactic.text,
                    },
                )
                val = NextTacticNode__Value(
                    self.value.initial_proof_state,
                    proof_context,
                    self.value.example,
                    reconstruction_tactic.text,
                )
                new_child = NextTacticNode(val, self, self.config)
                self.children.append(new_child)
                return new_child
            else:
                LOGGER.info(
                    "hammer failed to prove the goal",
                    extra={"node": self.label},
                )
                return None
        except Exception as e:
            LOGGER.info(
                "exception while running hammer",
                extra={"error": str(e), "node": self.label},
            )
            return None
        finally:
            self.tried_hammer = True
            try:
                coq.teardown()
            except:
                # usually these are pid not found
                pass

    def __generate_tactic(self) -> str | None:
        """
        calls gpt-4 to get the next tactic
        Returns a str, which is the next tactic to try
        """
        try:
            agent, environment = self.__make_agent_and_environment(
                self.value.example.proposition_command,
                self.value.example.hint,
                self.value.example.location,
                self.value.example.proof_prefix,
            )

            LOGGER.info(
                "generating tactic with agent",
                extra={
                    "node": self.label,
                    "observation": environment.base_observation,
                },
            )

            actions, usage = agent.act(
                environment.base_observation
            )  # assume act gives a single tactic in the form of an editaction
            self.root.usage.add_child(usage)
            if type(actions[0]) is EditAction:
                LOGGER.info(
                    "got tactic from agent", extra={"tactic": actions[0].new_code}
                )
                return actions[0].new_code
            else:
                return None

        except Exception as e:
            return None

    def __add_lemmas(self, environment: Environment) -> None:
        if self.config.lemma_context not in [
            "preceding-lemmas-and-selected-premises",
            "perfect-premises",
        ]:
            return

        if self.lemmas is None:
            if self.config.premise_names is not None:
                self.lemmas = environment.coq.get_lemmas_for_identifiers(
                    self.config.premise_names
                )
                LOGGER.debug(
                    "perfect premise selection premises",
                    extra={
                        "lemmas": self.lemmas,
                        "premise_names": self.config.premise_names,
                    },
                )
            else:
                self.lemmas, premise_selection_usage = select_premises(
                    environment.base_observation,
                    environment.coq,
                    include_reasoning=True,
                    n_identifiers=5,
                )
                self.root.usage.add_child(premise_selection_usage)

        if self.config.premise_names is not None:
            environment.clear_lemmas()
        LOGGER.debug("adding lemmas", extra={"lemmas": self.lemmas})
        environment.add_lemmas(self.lemmas)

    def __get_coq_for_current_node(self):
        coq = Coq(lemma_location=self.value.example.location)

        coq.run_command("From Hammer Require Import Hammer.")
        coq.run_command("From Hammer Require Import Tactics.")
        coq.run_command("From Hammer Require Import Reflect.")
        coq.run_command(self.value.example.proposition_command)
        coq.run_command("Proof.")

        tactics = [t for t in self.proof() if t is not None]
        for t in tactics:
            coq.run_command(t)

        return coq

    def __make_agent_and_environment(
        self,
        proposition_command: str,
        hint: t.Optional[str],
        location: t.Optional[LemmaLocation],
        proof_prefix: t.Optional[str],
    ):
        """
        takes a generic environment for this example, and adapts it to
        match the current node's place in the search
        - makes the code match this node's proof
        - adds lemmas as necessary
        """
        agent, environment = make_agent_and_environment(
            self.config.lemma_context,
            #
            proposition_command,
            hint,
            location,
            proof_prefix,
        )

        tactics = self.proof()
        tactics = [t for t in tactics if t is not None]
        if len(tactics) > 0:
            environment.step(EditAction(new_code=" ".join(tactics)))

        self.__add_lemmas(environment)

        return agent, environment


class SearchJSON(t.TypedDict):
    config: NextTacticConfigJSON
    nodes: t.List[NextTacticNodeJSON]
    nodes_to_expand: t.List[JSON]
    costs_so_far: t.Dict[str, float]
    costs_to_go: t.Dict[str, float]
    no_more_children: t.Dict[str, bool]
    node_added_idx: t.Dict[str, int]
    next_node_idx: int
    remaining_nodes_to_expand: int
    root_uuid: str
    done: bool
    visualization: str


def get_root_json(
    state: SearchJSON,
) -> t.Optional[NextTacticNodeJSON]:
    root_uuid = state["root_uuid"]
    root_node = next(
        (node for node in state["nodes"] if node["uuid"] == root_uuid),
        None,
    )
    if root_node is None:
        return None

    return root_node


class Search(TreeSearch[NextTacticNode__Value]):
    config: NextTacticConfig
    example: Example

    def __init__(
        self, root: NextTacticNode, config: NextTacticConfig, example: Example
    ):
        super().__init__(root, config)
        self.config = config
        self.example = example
        if self.config.state_file is not None:
            self.load_state()

    @classmethod
    def from_state_file(cls, config: NextTacticConfig, example: Example):
        assert config.state_file is not None, "state_file must be specified"
        if config.state_file.exists():
            with open(config.state_file, "r") as f:
                state_json: t.Optional[SearchJSON] = json.load(f)
            LOGGER.info(
                "loaded search state from file", extra={"state_file": config.state_file}
            )
        else:
            state_json = None

        root_node = cls.__make_root_node(config, example, state_json)
        return cls(root_node, config, example)

    def cost_so_far(self, node: NextTacticNode) -> float:
        # we're doing a DFS like proverbot
        return -self.node_added_idx[node.uuid]

    def cost_to_go(self, node: NextTacticNode) -> float:
        return 0

    def should_discard_children(self, node: NextTacticNode) -> bool:
        return (
            node.num_children >= self.config.max_num_children_per_node
            or node.depth >= self.config.max_depth - 1
        )

    def _write_state(self):
        LOGGER.info(
            f"writing search state to {self.config.state_file}",
            {
                "state_file": self.config.state_file,
            },
        )
        super()._write_state()
        root_node = t.cast(NextTacticNode, self.nodes[self.root])
        with open(self.config.state_file, "w") as f:
            json.dump(
                self.to_json(),
                f,
                indent=2,
            )

    def compute_usage(self) -> Usage:
        ans = Usage(name=self.example.name)
        root_node = t.cast(NextTacticNode, self.nodes[self.root])
        ans.add_child(root_node.usage)
        return ans

    def load_state(self):
        if not self.config.state_file.exists():
            return
        with open(self.config.state_file, "r") as f:
            LOGGER.info(
                f"loading search state from {self.config.state_file}",
                extra={"state_file": self.config.state_file},
            )
            self.load_from_json(json.load(f), self.example)
            LOGGER.info("loaded search state")

    def to_json(self) -> SearchJSON:
        return {
            "config": self.config.to_json(),
            "nodes": t.cast(NextTacticNode, self._get_node(self.root)).to_json(),
            "nodes_to_expand": [
                {
                    "cost": cost,
                    "id": id,
                    "uuid": uuid,
                }
                for cost, id, uuid in self.nodes_to_expand
            ],
            "costs_so_far": {uuid: cost for uuid, cost in self.costs_so_far.items()},
            "costs_to_go": {uuid: cost for uuid, cost in self.costs_to_go.items()},
            "no_more_children": {
                uuid: no_more_children
                for uuid, no_more_children in self.no_more_children.items()
            },
            "node_added_idx": {uuid: idx for uuid, idx in self.node_added_idx.items()},
            "next_node_idx": self.next_node_idx,
            "remaining_nodes_to_expand": self.remaining_nodes_to_expand,
            "root_uuid": self.root,
            "done": self.remaining_nodes_to_expand == 0,
            "visualization": self.visualize(),
        }

    def load_from_json(
        self,
        json: t.Dict[str, JSON],
        example: Example,
    ):
        self.root = t.cast(str, json["root_uuid"])

        self.nodes = t.cast(
            t.Dict[str, Node[NextTacticNode__Value]],
            NextTacticNode.from_json(
                list(reversed(t.cast(t.List[t.Dict[str, JSON]], json["nodes"]))),
                {},
                self.config,
                example,
            ),
        )

        self.nodes_to_expand = [
            (
                t.cast(float, node["cost"]),
                t.cast(int, node["id"]),
                t.cast(str, node["uuid"]),
            )
            for node in t.cast(t.List[t.Dict[str, JSON]], json["nodes_to_expand"])
        ]
        self.remaining_nodes_to_expand = t.cast(int, json["remaining_nodes_to_expand"])

        self.costs_so_far = {
            uuid: cost
            for uuid, cost in t.cast(t.Dict[str, float], json["costs_so_far"]).items()
        }
        self.costs_to_go = {
            uuid: cost
            for uuid, cost in t.cast(t.Dict[str, float], json["costs_to_go"]).items()
        }
        self.no_more_children = {
            uuid: no_more_children
            for uuid, no_more_children in t.cast(
                t.Dict[str, bool], json["no_more_children"]
            ).items()
        }
        self.node_added_idx = {
            uuid: idx
            for uuid, idx in t.cast(t.Dict[str, int], json["node_added_idx"]).items()
        }
        self.next_node_idx = t.cast(int, json["next_node_idx"])

        old_config = NextTacticConfig.from_json(
            t.cast(t.Dict[str, JSON], json["config"])
        )
        # config's max nodes to expand can change, meaning we'd like to run the search for more inferences
        if self.config.max_nodes_to_expand != old_config.max_nodes_to_expand:
            num_nodes_expanded = (
                old_config.max_nodes_to_expand - self.remaining_nodes_to_expand
            )
            # save a copy of the state file
            new_state_file = self.config.state_file.with_suffix(
                f".{num_nodes_expanded}.json"
            )

            LOGGER.info(
                f"max_nodes_to_expand changed from {old_config.max_nodes_to_expand} to {self.config.max_nodes_to_expand}. Saving state to {new_state_file}",
                extra={
                    "old_max_nodes_to_expand": old_config.max_nodes_to_expand,
                    "new_max_nodes_to_expand": self.config.max_nodes_to_expand,
                    "num_nodes_expanded": num_nodes_expanded,
                },
            )

            new_max_nodes_to_expand = self.config.max_nodes_to_expand
            self.config = old_config
            self.config.max_nodes_to_expand = new_max_nodes_to_expand

            # recompute remaining nodes to expand
            self.remaining_nodes_to_expand = (
                self.config.max_nodes_to_expand - num_nodes_expanded
            )

    @classmethod
    def __make_root_node(
        cls,
        config: NextTacticConfig,
        example: Example,
        state_json: t.Optional[SearchJSON],
    ) -> NextTacticNode:
        root_json = None
        if state_json is not None:
            root_json = get_root_json(state_json)

        if root_json is not None:
            value: NextTacticNode__Value = NextTacticNode__Value(
                initial_proof_state=c.contexts.ProofContext.from_dict(
                    root_json["value"]["initial_proof_state"]
                ),
                proof_state=c.contexts.ProofContext.from_dict(
                    root_json["value"]["proof_state"]
                ),
                example=example,
                tactic=root_json["value"]["tactic"],
            )
            return NextTacticNode(
                value,
                None,
                config,
            )

        # if loading from state_json failed, execute the environment to obtain an obligation
        _, environment = config.make_agent_and_environment(
            False,
            False,
            # ---
            example.proposition_command,
            None,
            example.location,
            None,
        )

        if environment is None:
            raise ValueError("failed to create initial environment")

        proof_context = environment.proof_context
        if proof_context is None:
            raise ValueError("Proof context is None")

        return NextTacticNode(
            NextTacticNode__Value(proof_context, proof_context, example, None),
            None,
            config,
        )


class NextTacticStrategy:
    example: Example
    search: Search
    state_json: t.Optional[SearchJSON]
    config: NextTacticConfig

    def __init__(
        self,
        example: Example,
        config,
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

    def __make_root_node(
        self,
    ) -> NextTacticNode:
        _, environment = make_agent_and_environment(
            self.config.lemma_context,
            #
            self.example.proposition_command,
            self.example.hint,
            self.example.location,
            self.example.proof_prefix,
        )
        proof_state = environment.proof_context
        assert proof_state is not None, "initial environment should have a proof state"

        return NextTacticNode(
            value=NextTacticNode__Value(
                initial_proof_state=proof_state,
                proof_state=proof_state,
                example=self.example,
                tactic=None,
            ),
            parent=None,
            config=self.config,
        )

    def run(
        self, global_tqdm: Tqdm, tqdm_func: TqdmFunc
    ) -> t.Tuple[t.Optional[Environment], Usage]:
        LOGGER.info(
            "running next tactic search",
            extra={"config": self.config},
        )
        for proven_node in self.search.search(
            global_tqdm,
            tqdm_func,
            progress_bar_desc=self.example.name[: len("total progress")],
        ):
            LOGGER.info("got a proven node", extra={"node": proven_node})
            _, environment = make_agent_and_environment(
                self.config.lemma_context,
                #
                self.example.proposition_command,
                self.example.hint,
                self.example.location,
                self.example.proof_prefix,
            )
            code = proven_node.value.tactic
            assert code is not None, "proven node should have a tactic"
            environment.step(EditAction(new_code=code))
            return environment, self.search.compute_usage()
        return None, self.search.compute_usage()

    def __make_search(self):
        return Search.from_state_file(self.config, self.example)

    @property
    def proof(self):
        done_nodes = self.search.done_nodes
        if len(done_nodes) == 0:
            return None

        proof = t.cast(NextTacticNode, done_nodes[0]).proof()

        if proof is None:
            return None

        return " ".join(proof)

    def __load_state(self):
        if self.config.state_file.exists():
            with self.config.state_file.open("r") as f:
                self.state_json = json.load(f)
            LOGGER.info(
                "loaded state from file", extra={"state_file": self.config.state_file}
            )
        else:
            self.state_json = None


# TODO: rm eval. it will live in evaluations


RESULTS_DIR = (
    (Path(CONFIG.ROOT_DIR) / "data/evaluation/next_tactic").resolve().absolute()
)
DatasetName = t.Literal[
    "dev", "test", "wigderson_dev", "wigderson_err", "wigderson_dev_perfect_subgoals"
]
DATASET_NAMES: t.List[DatasetName] = [
    "dev",
    "test",
    "wigderson_dev",
    "wigderson_err",
    "wigderson_dev_perfect_subgoals",
]


class NextTacticEval:
    uuid: str
    dataset_name: DatasetName

    dataset: Dataset
    lemmas: t.List[str]

    result: Result
    # if proof is set to None, then we failed on that proof
    proofs: t.Dict[Example, t.Optional[str]]
    # tree searches loaded from files
    runners: t.Dict[Example, t.Optional[NextTacticStrategy]]  # TODO: define strategy
    config: NextTacticConfig

    def __init__(
        self,
        uuid: str,
        dataset_name: DatasetName,
        config: NextTacticConfig,
        lemmas: t.List[str] = [],
    ):
        self.uuid = uuid
        self.dataset_name = dataset_name

        self.dataset = (
            COQGYM_DEV_SAMPLED_DATASET
            if dataset_name == "dev"
            else (
                COQGYM_TEST_SAMPLED_DATASET
                if dataset_name == "test"
                else (
                    COQ_WIGDERSON_DEV_SAMPLED_DATASET
                    if dataset_name == "wigderson_dev"
                    else (COQ_WIGDERSON_TEST_SAMPLED_DATASET)
                )
            )
        )
        self.lemmas = lemmas

        self.result = Result(
            self.name, containing_directory=str(RESULTS_DIR), uuid=self.uuid
        )
        self.proofs = {}

        self.config = config

        set_log_file(self.result.log_file_path)

    @property
    def name(self):
        return f"{self.dataset_name}"

    @property
    def directory_path(self):
        return self.result.directory_path

    def run_eval(self):
        with tqdm(total=len(self.dataset), dynamic_ncols=True) as global_tqdm:

            for example in self.dataset:
                # if ("indep_set_ok" not in example.name):
                #     continue
                set_example_name(example.name)
                strategy = NextTacticStrategy(example, self.config)
                tqdm_func = t.cast(TqdmFunc, tqdm)
                environment, usage = strategy.run(global_tqdm, tqdm_func)

                if environment is not None and environment.is_initial_goal_proven:  # ??
                    self.result.successful_examples.append(example)
                    self.proofs[example] = ""  # todo
                    tqdm.write("success")
                else:
                    self.result.failed_examples.append(example)
                    self.proofs[example] = None
                    tqdm.write("failure")
                self.result.usage.add_child(usage)

                self.result.write()


def make_agent_and_environment(
    lemma_context: LemmaContext,
    # --- above are extra arguments that should be curried away
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
            done_condition="initial-goal-or-decomposition", lemma_context=lemma_context
        ),
    )
    return agent, environment


def main():
    # configure_logger()
    uuid = uuid4().hex

    set_run_uuid(uuid)

    # set_log_file(self.result.log_file_path)

    s_file = Path("state_file.json")
    nt_config = NextTacticConfig(
        max_nodes_to_expand=1,
        lemma_context="preceding-lemmas-only",
        state_file=s_file,
    )

    dataset_name = "wigderson_dev"
    next_tactic = NextTacticEval(
        uuid,
        dataset_name,
        nt_config,
    )

    next_tactic.run_eval()


if __name__ == "__main__":
    main()
