from dataclasses import dataclass
import typing as t
from serde import serde

DoneCondition = t.Literal["initial-goal-only", "initial-goal-or-decomposition"]
LemmaContext = t.Literal[
    "preceding-lines",
    "preceding-lemmas-only",
    "preceding-lemmas-and-selected-premises",
    "perfect-premises",
    "none",
]


@serde
@dataclass
class EnvironmentConfig:
    done_condition: DoneCondition = "initial-goal-only"
    lemma_context: LemmaContext = "preceding-lemmas-and-selected-premises"

    def __post_init__(self):
        self.validate()

    def validate(self):
        """
        Raises an assertion error if the config is invalid.
        """
