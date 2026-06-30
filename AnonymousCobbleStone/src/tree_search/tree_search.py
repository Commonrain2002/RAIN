from abc import ABC, abstractmethod
from dataclasses import dataclass
import typing as t
import heapq
import time

from tqdm import tqdm

from src.tree_search.node import Node
from src.utils import get_logger, Tqdm, TqdmFunc

LOGGER = get_logger("tree_search")

V = t.TypeVar("V", bound=t.Hashable)


@dataclass
class TreeSearchConfig:
    max_nodes_to_expand: int


Uuid = str


class TreeSearch(ABC, t.Generic[V]):
    """
    performs cost-based search over nodes of type N
    """

    config: TreeSearchConfig

    nodes: t.Dict[Uuid, Node[V]]
    nodes_to_expand: t.List[t.Tuple[float, int, Uuid]]

    costs_so_far: t.Dict[Uuid, float]
    costs_to_go: t.Dict[Uuid, float]
    no_more_children: t.Dict[Uuid, bool]

    node_added_idx: t.Dict[Uuid, int]
    next_node_idx: int

    remaining_nodes_to_expand: int

    root: Uuid
    wall_budget_exhausted: bool

    def __init__(self, root: Node[V], config: TreeSearchConfig):
        self.root = root.uuid
        self.nodes = {}
        self._register_node(root)

        self.config = config
        self.wall_budget_exhausted = False
        self.__reset()

    @property
    def done_nodes(self):
        return [node for node in self.nodes.values() if node.is_goal()]

    def __reset(self):
        self.nodes = {
            node.uuid: node for node in self.nodes.values() if node.uuid == self.root
        }
        self.costs_so_far = {}
        self.costs_to_go = {}
        self.no_more_children = {}

        self.next_node_idx = 0
        self.node_added_idx = {}

        self.nodes_to_expand = []
        heapq.heapify(self.nodes_to_expand)

        self.remaining_nodes_to_expand = self.config.max_nodes_to_expand

    def _register_node(self, node: Node[V]):
        self.nodes[node.uuid] = node

    def _get_node(self, uuid: Uuid) -> Node[V]:
        return self.nodes[uuid]

    def __add_node(self, node: Node[V]):
        self._register_node(node)

        if node.uuid not in self.node_added_idx:
            self.node_added_idx[node.uuid] = self.next_node_idx
            self.next_node_idx += 1

        heapq.heappush(
            self.nodes_to_expand,
            (
                self.cost(node),
                id(node),
                node.uuid,
            ),
        )

    def __next_node(self):
        heap_value = heapq.heappop(self.nodes_to_expand)
        return (
            heap_value[0],
            heap_value[1],
            self._get_node(heap_value[2]),
        )

    def _write_state(self):
        """
        write state of the search to a file. Useful when resuming the search
        """
        pass

    @abstractmethod
    def cost_so_far(self, node: Node[V]) -> float:
        """
        cost of the path from the root to the node
        """
        pass

    @abstractmethod
    def cost_to_go(self, node: Node[V]) -> float:
        """
        estimated cost from the node to the goal (heuristic)
        """
        pass

    def cost(self, node: Node[V]) -> float:
        """
        total cost of the path from the root to the goal
        """
        self.costs_so_far[node.uuid] = self.cost_so_far(node)
        self.costs_to_go[node.uuid] = self.cost_to_go(node)

        return self.costs_so_far[node.uuid] + self.costs_to_go[node.uuid]

    def prune(self, node: Node[V]) -> bool:
        """
        determines whether a node should be pruned
        """
        return self.no_more_children.get(node.uuid, False)

    def should_discard_children(self, node: Node[V]) -> bool:
        """
        determines whether a node should be pruned
        """
        return False

    def __stop_for_session_wall_budget(
        self,
        session_start: float,
        wall_budget: t.Optional[float],
        phase: str,
    ) -> bool:
        if wall_budget is None:
            return False
        if time.perf_counter() - session_start < wall_budget:
            return False
        self.wall_budget_exhausted = True
        LOGGER.info(
            "example wall budget exhausted in search loop",
            extra={
                "phase": phase,
                "session_wall_budget_seconds": wall_budget,
                "session_elapsed_seconds": time.perf_counter() - session_start,
            },
        )
        return True

    def __sync_wall_budget_signal_from_config(self) -> bool:
        if not getattr(self.config, "wall_budget_exhausted_signal", False):
            return False
        self.wall_budget_exhausted = True
        return True

    def search(
        self,
        global_tqdm: Tqdm,
        tqdm_func: TqdmFunc,
        progress_bar_desc: t.Optional[str] = None,
    ) -> t.Generator[Node[V], t.Any, Node[V] | None]:
        """
        yields goal nodes, enumerating them as they are found
        """
        if len(self.nodes_to_expand) == 0:
            self.__add_node(self._get_node(self.root))

        if progress_bar_desc is None:
            progress_bar_desc = (
                f"tree_search({self.nodes_to_expand[0][2].__class__.__name__})"
            )
        with tqdm_func(
            total=self.remaining_nodes_to_expand,
            dynamic_ncols=True,
            desc=progress_bar_desc,
        ) as bar:
            self._write_state()
            session_start = time.perf_counter()
            wall_budget = getattr(self.config, "session_wall_budget_seconds", None)
            if hasattr(self.config, "session_wall_deadline_perf"):
                self.config.session_wall_deadline_perf = (
                    session_start + wall_budget
                    if wall_budget is not None
                    else None
                )
            if hasattr(self.config, "wall_budget_exhausted_signal"):
                self.config.wall_budget_exhausted_signal = False

            while len(self.nodes_to_expand) > 0 and self.remaining_nodes_to_expand > 0:
                if self.__stop_for_session_wall_budget(
                    session_start, wall_budget, "while_loop_start"
                ):
                    break

                current_score, _, current_node = self.__next_node()

                if self.prune(current_node):
                    if self.__stop_for_session_wall_budget(
                        session_start, wall_budget, "after_pruned_node"
                    ):
                        break
                    continue

                # attempt to expand the node if it is indeterminate
                if (
                    self.should_discard_children(current_node)
                    and current_node.is_goal() is not None
                ):
                    if self.__stop_for_session_wall_budget(
                        session_start, wall_budget, "after_discard_children_skip"
                    ):
                        break
                    continue

                if self.__stop_for_session_wall_budget(
                    session_start, wall_budget, "before_generate_new_children"
                ):
                    break

                LOGGER.info(
                    "expanding node",
                    extra={
                        "node": current_node.label,
                        "cost": self.cost(
                            current_node,
                        ),
                        "remaining_nodes_to_expand": self.remaining_nodes_to_expand,
                        "tree": self.visualize(),
                    },
                )

                new_nodes = current_node.generate_new_children(
                    self.should_discard_children(current_node)
                )

                if self.__sync_wall_budget_signal_from_config() or (
                    self.__stop_for_session_wall_budget(
                        session_start, wall_budget, "after_generate_new_children"
                    )
                ):
                    self._write_state()
                    break

                if new_nodes is not None:
                    for new_node in new_nodes:
                        if new_node in self.costs_so_far:
                            continue

                        self.__add_node(new_node)
                    for new_node in new_nodes:
                        if new_node.is_goal():
                            LOGGER.info(
                                "found a goal node",
                                extra={
                                    "tree": self.visualize(),
                                },
                            )
                            self._write_state()
                            yield new_node
                            continue

                if self.__stop_for_session_wall_budget(
                    session_start, wall_budget, "after_process_new_nodes"
                ):
                    self._write_state()
                    break

                if new_nodes is not None and len(new_nodes) == 0:
                    self.no_more_children[current_node.uuid] = True

                if self.__stop_for_session_wall_budget(
                    session_start, wall_budget, "before_node_budget_decrement"
                ):
                    self._write_state()
                    break

                # repush the current node to give it a chance to be expanded again
                self.__add_node(current_node)

                self.remaining_nodes_to_expand -= 1

                self._write_state()
                bar.update()
                global_tqdm.update()

            LOGGER.info(
                "search finished",
                extra={
                    "tree": self.visualize(),
                },
            )
            self._write_state()
            return None

    def visualize(self, include_idx=False) -> str:
        def get_node_attrs(node: Node[V]):
            # if self.prune(node):
            #     return ""
            attrs = {
                "done": node.is_goal(),
                "cost": self.cost(node),
                "n_fail": node.num_failed_attempts_to_generate_children,
            }
            if include_idx:
                attrs["idx"] = self.node_added_idx[node.uuid]
            return "; ".join([f"{k}:{v}" for k, v in attrs.items() if v is not None])

        def get_node_children(node: Node[V]):
            return node.children_to_visualize

        def get_node_label(node: Node[V]):
            ans = node.label
            if self.prune(node):
                ans += " (pruned)"
            return ans

        return "\n" + visualize_helper(
            self._get_node(self.root),
            get_node_children,
            get_node_attrs,
            get_node_label,
        )


def visualize_helper(
    node: Node[V],
    get_node_children: t.Callable[[Node[V]], t.List[t.Union[Node[V], str]]],
    get_node_attrs: t.Callable[[Node[V]], str],
    get_node_label: t.Callable[[Node[V]], str],
    indent: int = 0,
) -> str:
    indent_str = " " * indent
    label = get_node_label(node)
    attrs = get_node_attrs(node)

    node_str = f"{indent_str}* {label} ({attrs})"
    children_str = "\n".join(
        (
            visualize_helper(
                child,
                get_node_children,
                get_node_attrs,
                get_node_label,
                indent=indent + 2,
            )
            if isinstance(child, Node)
            else f"{indent_str}  {child}"
        )
        for child in get_node_children(node)
    )
    return f"{node_str}\n{children_str}"


@dataclass
class DfsConfig(TreeSearchConfig):
    max_depth: int


class Dfs(TreeSearch[V]):
    config: DfsConfig

    def __init__(self, root: Node[V], config: DfsConfig):
        super().__init__(root, config)
        self.config = config

    def cost_so_far(self, node: Node[V]) -> float:
        return -self.node_added_idx[node.uuid]  # LIFO. later nodes are cheaper

    def cost_to_go(self, node: Node[V]) -> float:
        return 0

    def should_discard_children(self, node: Node[V]) -> bool:
        return node.depth >= self.config.max_depth - 1


@dataclass
class BfsConfig(TreeSearchConfig):
    max_num_children_per_node: int


class Bfs(TreeSearch[V]):
    config: BfsConfig

    def __init__(self, root: Node[V], config: BfsConfig):
        super().__init__(root, config)
        self.config = config

    def cost_so_far(self, node: Node[V]) -> float:
        return self.node_added_idx[node.uuid]  # FIFO. earlier nodes are cheaper

    def cost_to_go(self, node: Node[V]) -> float:
        return 0

    def should_discard_children(self, node: Node[V]) -> bool:
        return node.num_children >= self.config.max_num_children_per_node
