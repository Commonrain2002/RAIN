"""
This module contains different strategies to use an agent and
its actions to solve a coq proof.
Examples of strategies include:
- zero-shot
- rollout
- dfs
- bfs
"""

from src.strategy.rollout import rollout, RolloutConfig
from src.strategy.single_edit import single_edit, SingleEditConfig
from src.strategy.types_renamed import (
    MakeAgentAndEnvironment,
    Strategy,
)
