from abc import ABC, abstractmethod
import typing as t

from src.llm import Usage

Action = t.TypeVar("Action")
Observation = t.TypeVar("Observation")


class Agent(ABC, t.Generic[Action, Observation]):
    usage: Usage

    def __init__(self):
        self.usage = Usage(name=self.__class__.__name__)

    @abstractmethod
    def act(self, observation: Observation) -> t.Tuple[t.List[Action], Usage]:
        pass
