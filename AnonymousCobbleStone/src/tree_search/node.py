import typing as t
from abc import ABC, abstractmethod
from uuid import uuid4

Value = t.TypeVar("Value", bound=t.Hashable)


class Node(ABC, t.Generic[Value]):
    """
    This class is an arbitrary node in a tree search
    """

    uuid: str
    parent: t.Optional["Node"]
    value: Value
    depth: int

    num_failed_attempts_to_generate_children: int = 0

    def __init__(
        self,
        value: Value,
        parent: t.Optional["Node"] = None,
        uuid: t.Optional[str] = None,
    ):
        self.parent = parent
        self.depth = 0 if parent is None else parent.depth + 1
        self.value = value
        if uuid is None:
            self.uuid = uuid4().hex
        else:
            self.uuid = uuid

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, Node):
            return False
        return self.value == __value.value

    def __hash__(self) -> int:
        return hash(self.value)

    @property
    def root(self):
        """
        the root of this node
        """
        if self.parent is None:
            return self
        return self.parent.root

    def generate_new_children(
        self, discard_children: bool
    ) -> t.Optional[t.List["Node[Value]"]]:
        """
        generates new children of this node
        returns None if we failed to generate children
        returns [] if we have no more children to generate

        we discard children if we'd like to evaluate this node, but not expand it, for example because we're at our depth limit
        """
        new_children = self._generate_new_children(discard_children=discard_children)

        if new_children is None:
            self.num_failed_attempts_to_generate_children += 1
            return None

        if discard_children:
            return None

        return new_children

    @abstractmethod
    def _generate_new_children(
        self, discard_children: bool
    ) -> t.Optional[t.List["Node[Value]"]]:
        """
        generates new children of this node
        returns None if we failed to generate children
        returns [] if we have no more children to generate
        """
        pass

    @property
    @abstractmethod
    def num_children(self) -> int:
        """
        the number of children at this node. may be used in the search procedure to determine if we should expand this node
        """
        pass

    @abstractmethod
    def is_goal(self) -> t.Optional[bool]:
        """
        whether this node is a goal.
        returns None if we don't know yet
        """
        pass

    @property
    @abstractmethod
    def children_to_visualize(self) -> t.List[t.Union["Node[Value]", str]]:
        """
        a list of child nodes. Only used for visualization, not for search
        """
        pass

    @property
    @abstractmethod
    def label(self) -> str:
        """
        label of the node. Used for visualization
        """
        pass


# TODO: goal decomp node
