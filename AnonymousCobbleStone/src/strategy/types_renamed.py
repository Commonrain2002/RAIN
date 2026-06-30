import typing as t

from src.llm import Usage
from src.agent import Agent
from src.environment.environment import Environment
from src.dataset import Example
from src.coq_serapy_util import LemmaLocation

PropositionCommand = str
Hint = t.Optional[str]
ProofPrefix = str

MakeAgentAndEnvironment = t.Callable[
    [PropositionCommand, Hint, t.Optional[LemmaLocation], t.Optional[ProofPrefix]],
    t.Tuple[Agent, Environment],
]


Config = t.TypeVar("Config")


# takes an example, and returns whether the model successfully proved it
Strategy = t.Callable[
    [Example, MakeAgentAndEnvironment, t.Optional[Config]],
    t.Tuple[t.Optional[Environment], Usage],
]
