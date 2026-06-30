import time
import typing as t
from tqdm import tqdm

from src.tree_search import (
    TreeSearch,
    TreeSearchConfig,
    Node,
    Dfs,
    DfsConfig,
    Bfs,
    BfsConfig,
)
from src.utils import TqdmFunc


def main():
    root = IntNode("")
    bfs = Bfs(root, BfsConfig(max_num_children_per_node=10, max_nodes_to_expand=200))

    search_iterator = bfs.search(
        tqdm(total=bfs.config.max_nodes_to_expand),
        t.cast(TqdmFunc, tqdm),
        progress_bar_desc="searching",
    )
    for pretty_state in search_iterator:
        print("state")
        print(pretty_state)
        print("visualization")
        print(bfs.visualize(True))
        time.sleep(1)


class NumAStar(TreeSearch[str]):
    goal: str

    def __init__(self, root: Node[str], config: TreeSearchConfig, goal: str):
        super().__init__(root, config)
        self.config = config
        self.goal = goal

    def cost_so_far(self, node: Node[str]) -> float:
        cost = 0
        seen_chars = set()
        for i in node.value:
            if i in seen_chars or i not in self.goal:
                cost += 1
            else:
                seen_chars.add(i)
        return cost

    def cost_to_go(self, node: Node[str]) -> float:
        cost = len(self.goal)
        for i in self.goal:
            if i in node.value:
                cost -= 1
        return cost


class IntNode(Node[str]):
    """
    A node with an integer value.
    used to test search algorithms
    """

    next_child_digit: int = 0
    __children: t.List["IntNode"]

    def __init__(self, value: str, parent: t.Optional["IntNode"] = None):
        super().__init__(value, parent)
        self.next_child_digit = 0
        self.__children = []

    def _generate_new_children(
        self, discard_children: bool
    ) -> t.Optional[t.List["IntNode"]]:
        if discard_children:
            return None

        if self.next_child_digit == 10:
            return []
        new_child = IntNode(self.value + str(self.next_child_digit), self)

        self.next_child_digit += 1
        self.__children.append(new_child)

        return [new_child]

    @property
    def num_children(self) -> int:
        return len(self.__children)

    @property
    def children_to_visualize(self) -> t.List["IntNode"]:
        return self.__children

    def is_goal(self) -> bool:
        return self.value == "69"

    @property
    def label(self) -> str:
        return str(self.value)


if __name__ == "__main__":
    main()
