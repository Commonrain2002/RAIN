import typing as t
import json
import coq_serapy as c

from .utils import (
    LOGGER,
    GoalDecompositionConfig,
    get_root_json,
    GoalDecomposition_Search_1JSON,
)
from .node import (
    GoalDecompositionNode,
    GoalDecompositionNode__Value,
)
from src.tree_search import TreeSearch, Node
from src.llm import Usage
from src.utils import JSON
from src.dataset import Example


class GoalDecomposition_Search_1(TreeSearch[GoalDecompositionNode__Value]):
    config: GoalDecompositionConfig
    example: Example

    def __init__(
        self,
        root: GoalDecompositionNode,
        config: GoalDecompositionConfig,
        example: Example,
    ):
        super().__init__(root, config)
        self.config = config
        self.example = example
        if self.config.state_file is not None:
            self.load_state()

    @classmethod
    def from_state_file(cls, config: GoalDecompositionConfig, example: Example):
        assert config.state_file is not None, "state_file must be specified"
        if config.state_file.exists():
            with open(config.state_file, "r") as f:
                state_json: t.Optional[GoalDecomposition_Search_1JSON] = json.load(f)
        else:
            state_json = None

        root_node = cls.__make_root_node(config, example, state_json)
        return cls(root_node, config, example)

    @classmethod
    def __make_root_node(
        cls,
        config: GoalDecompositionConfig,
        example: Example,
        state_json: t.Optional[GoalDecomposition_Search_1JSON],
    ) -> GoalDecompositionNode:
        root_json = None
        if state_json is not None:
            root_json = get_root_json(state_json)

        if root_json is not None:
            obligation = c.contexts.Obligation.from_dict(
                root_json["value"]["obligation"]
            )
            return GoalDecompositionNode(
                GoalDecompositionNode__Value(obligation, None, example, None),
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

        assert len(proof_context.fg_goals) == 1, f"expected exactly one fg goal, got {len(proof_context.fg_goals)}"

        obligation = proof_context.fg_goals[0]
        return GoalDecompositionNode(
            GoalDecompositionNode__Value(obligation, None, example, None),
            None,
            config,
        )

    def _write_state(self):
        LOGGER.info(
            f"writing search state to {self.config.state_file}",
            {
                "state_file": self.config.state_file,
            },
        )
        super()._write_state()
        root_node = t.cast(GoalDecompositionNode, self.nodes[self.root])
        with open(self.config.state_file, "w") as f:
            json.dump(
                self.to_json(),
                f,
                indent=2,
            )

    def to_json(self) -> GoalDecomposition_Search_1JSON:
        return {
            "config": self.config.to_json(),
            "nodes": t.cast(GoalDecompositionNode, self._get_node(self.root)).to_json(),
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

    def load_from_json(
        self,
        json: t.Dict[str, JSON],
        example: Example,
    ):
        self.root = t.cast(str, json["root_uuid"])

        self.nodes = t.cast(
            t.Dict[str, Node[GoalDecompositionNode__Value]],
            GoalDecompositionNode.from_json(
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

        old_config = GoalDecompositionConfig.from_json(
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

    def compute_usage(self) -> Usage:
        root_node = t.cast(GoalDecompositionNode, self.nodes[self.root])
        return root_node.usage

    def cost_so_far(self, node: GoalDecompositionNode) -> float:
        # can we get away with just the lifo cost instead of "deeper nodes are cheaper"?
        dfs_cost = -self.node_added_idx[node.uuid]  # LIFO. later nodes are cheaper
        # failed_attempt_cost = node.num_failed_attempts_to_generate_children

        return 0.1 * dfs_cost
        # + 0.5 * failed_attempt_cost

    def cost_to_go(self, node: GoalDecompositionNode) -> float:
        return 0

    def should_discard_children(self, node: GoalDecompositionNode) -> bool:
        return node.depth >= self.config.max_depth - 1

    def prune(self, node: GoalDecompositionNode) -> bool:
        if super().prune(node):
            return True

        if node.proven:
            return True

        current_parent = node.parent
        while current_parent is not None:
            if self.prune(current_parent):
                return True
            current_parent = current_parent.parent

        # don't prune matching goals if the proof contains assert
        if node.value.decomposition is not None and any(
            proof.has_assert for proof in node.value.decomposition.proofs
        ):
            return False

        if any(n.redundant_to_ancestor for n in node.decomposition_sibling_nodes()):
            return True

        return False
