from dataclasses import dataclass
import time
import typing as t
from pathlib import Path
import coq_serapy as c

from src.utils import get_logger, JSON
from src.tree_search import TreeSearchConfig
from src.environment import LemmaContext
from src.coq_serapy_util import LemmaLocation
from src.agent import Agent
from src.agent.zero_shot_tool import ZeroShotToolAgent, ZeroShotToolAgentConfig
from src.environment import Environment, EnvironmentConfig
from src.dataset import Example
from src.strategy.single_edit import single_edit, SingleEditConfig
from src.strategy import MakeAgentAndEnvironment
from src.llm import OpenaiChatPromptConfig
from src.llm.model_names import OpenaiChatModelName
from src.proof_script import CoqPartialSuccess, ProofScript


LOGGER = get_logger("goal_decomposition")


def mark_session_wall_budget_exhausted_if_past_deadline(
    config: "GoalDecompositionConfig",
) -> bool:
    deadline = config.session_wall_deadline_perf
    if deadline is None or time.perf_counter() < deadline:
        return False
    config.wall_budget_exhausted_signal = True
    return True


@dataclass
class GoalDecomposition:
    proofs: t.Set[ProofScript]
    goals: t.List[c.contexts.Obligation]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GoalDecomposition):
            return False
        return self.goals == other.goals

    def __hash__(self) -> int:
        return hash(tuple(self.goals))

    def to_json(self) -> "GoalDecompositionJSON":
        return {
            "proofs": list(proof.to_json() for proof in self.proofs),
            "goals": [goal.to_dict() for goal in self.goals],
        }

    @classmethod
    def from_json(cls, data: t.Dict[str, JSON]) -> "GoalDecomposition":
        return cls(
            proofs=set(
                ProofScript.from_json(proof)
                for proof in t.cast(t.List[str], data["proofs"])
            ),
            goals=[
                c.contexts.Obligation.from_dict(goal)
                for goal in t.cast(t.List[t.Any], data["goals"])
            ],
        )

    @classmethod
    def from_partial_success(
        cls, partial_success: CoqPartialSuccess
    ) -> "GoalDecomposition":
        return cls(
            proofs=set([partial_success.prefix]),
            goals=[
                obligation
                for obligation in partial_success.subgoal_obligations
                if obligation is not None
            ],
        )


class GoalDecompositionJSON(t.TypedDict):
    proofs: t.List[str]
    goals: t.List[t.Dict[str, JSON]]


@dataclass
class GoalDecompositionConfig(TreeSearchConfig):
    lemma_context: LemmaContext
    state_file: Path
    session_wall_budget_seconds: t.Optional[float] = None
    session_wall_deadline_perf: t.Optional[float] = None
    wall_budget_exhausted_signal: bool = False
    max_depth: int = 5
    try_hammer: bool = True
    proof_prefix: t.Optional[str] = None
    premise_names: t.Optional[t.List[str]] = None
    model: OpenaiChatModelName = "gpt-4"

    def to_json(self) -> "GoalDecompositionConfigJSON":
        return {
            "max_nodes_to_expand": self.max_nodes_to_expand,
            "max_depth": self.max_depth,
            "try_hammer": self.try_hammer,
            "state_file": str(self.state_file),
            "lemma_context": self.lemma_context,
            "premise_names": self.premise_names,
            "model": self.model,
        }

    @classmethod
    def from_json(cls, data: t.Dict[str, JSON]) -> "GoalDecompositionConfig":
        return cls(
            max_nodes_to_expand=t.cast(int, data["max_nodes_to_expand"]),
            max_depth=t.cast(int, data["max_depth"]),
            try_hammer=t.cast(bool, data["try_hammer"]),
            state_file=Path(t.cast(str, data["state_file"])),
            lemma_context=t.cast(LemmaContext, data["lemma_context"]),
            premise_names=(
                t.cast(t.Optional[t.List[str]], data["premise_names"])
                if "premise_names" in data
                else None
            ),
            model=(
                t.cast(OpenaiChatModelName, data["model"])
                if "model" in data
                else "gpt-4"
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
                chat_config=OpenaiChatPromptConfig(model=self.model, n=1),
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

    def run_strategy(
        self, example: Example, make_agent_and_environment: MakeAgentAndEnvironment
    ):
        return single_edit(
            example,
            make_agent_and_environment,
            SingleEditConfig(n=1, bar=False),
        )


class GoalDecompositionConfigJSON(t.TypedDict):
    max_nodes_to_expand: int
    max_depth: int
    try_hammer: bool
    state_file: str
    lemma_context: LemmaContext
    premise_names: t.Optional[t.List[str]]
    model: OpenaiChatModelName


class GoalDecompositionNode__ValueJSON(t.TypedDict):
    obligation: t.Dict[str, JSON]
    decomposition: t.Optional[GoalDecompositionJSON]
    proof_prefix: t.Optional[str]


class GoalDecompositionNodeJSON(t.TypedDict):
    uuid: str
    parent_uuid: t.Optional[str]
    value: GoalDecompositionNode__ValueJSON
    depth: int
    num_failed_attempts_to_generate_children: int
    children_uuids: t.List[t.List[str]]
    decompositions: t.List[GoalDecompositionJSON]
    proof: t.Optional[str]
    lemmas: t.Optional[t.List[str]]
    attempts: t.List[str]
    failed_attempts: t.List[str]


class GoalDecomposition_Search_1JSON(t.TypedDict):
    config: GoalDecompositionConfigJSON
    nodes: t.List[GoalDecompositionNodeJSON]
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
    state: GoalDecomposition_Search_1JSON,
) -> t.Optional[GoalDecompositionNodeJSON]:
    root_uuid = state["root_uuid"]
    root_node = next(
        (node for node in state["nodes"] if node["uuid"] == root_uuid),
        None,
    )
    if root_node is None:
        return None

    return root_node


def get_num_expanded_nodes(
    state: GoalDecomposition_Search_1JSON,
) -> int:
    return state["config"]["max_nodes_to_expand"] - state["remaining_nodes_to_expand"]


def get_proof(
    state: GoalDecomposition_Search_1JSON,
) -> t.Optional[ProofScript]:
    root_node = get_root_json(state)
    if root_node is None:
        return None
    return get_proof_helper(root_node, state["nodes"])


def get_proof_helper(
    node: GoalDecompositionNodeJSON,
    nodes: t.List[GoalDecompositionNodeJSON],
) -> t.Optional[ProofScript]:
    if node["proof"] is not None:
        return ProofScript.from_json(node["proof"])

    for decomposition, children_uuids in zip(
        node["decompositions"], node["children_uuids"]
    ):
        children = [
            next(n for n in nodes if n["uuid"] == child_uuid)
            for child_uuid in children_uuids
        ]
        children_proofs = [get_proof_helper(child, nodes) for child in children]
        if all(child_proofs is not None for child_proofs in children_proofs):
            decomp_proof = ProofScript.from_json(decomposition["proofs"][0])
            return ProofScript(
                decomp_proof.contents
                + [
                    t.cast(ProofScript, child_proofs)
                    for child_proofs in children_proofs
                ]
            )

    return None


class SampleInfo(t.TypedDict):
    num_llm_samples: int
    num_hammer_calls: int


def add_sample_info(sample_info: SampleInfo, other: SampleInfo) -> SampleInfo:
    return SampleInfo(
        num_llm_samples=sample_info["num_llm_samples"] + other["num_llm_samples"],
        num_hammer_calls=sample_info["num_hammer_calls"] + other["num_hammer_calls"],
    )


def sum_sample_info(sample_infos: t.List[SampleInfo]) -> SampleInfo:
    ans = SampleInfo(num_llm_samples=0, num_hammer_calls=0)
    for sample_info in sample_infos:
        ans = add_sample_info(ans, sample_info)
    return ans


def get_proof_and_num_samples(
    state: GoalDecomposition_Search_1JSON,
) -> t.Tuple[t.Optional[ProofScript], SampleInfo]:
    root_node = get_root_json(state)
    if root_node is None:
        return None, {"num_llm_samples": 0, "num_hammer_calls": 0}
    proof = get_proof_helper(root_node, state["nodes"])
    return proof, get_proof_and_num_samples_helper(root_node, state["nodes"])


def get_proof_and_num_samples_helper(
    node: GoalDecompositionNodeJSON,
    nodes: t.List[GoalDecompositionNodeJSON],
) -> SampleInfo:
    if node["proof"] is not None:
        return (
            {"num_llm_samples": 0, "num_hammer_calls": 1}
            if node["proof"].strip() == "hammer."
            else {"num_llm_samples": 1, "num_hammer_calls": 0}
        )

    for decomposition, children_uuids in zip(
        node["decompositions"], node["children_uuids"]
    ):
        children = [
            next(n for n in nodes if n["uuid"] == child_uuid)
            for child_uuid in children_uuids
        ]
        children_num_samples = [
            get_proof_and_num_samples_helper(child, nodes) for child in children
        ]
        return add_sample_info(
            {"num_llm_samples": 1, "num_hammer_calls": 0},
            sum_sample_info(children_num_samples),
        )

    return {"num_llm_samples": 0, "num_hammer_calls": 0}
