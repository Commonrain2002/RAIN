import typing as t
from dataclasses import dataclass, field
import re
import coq_serapy as c

from src.coq_serapy_util import (
    kill_comments,
    Coq,
    CoqResult,
    proof_context_to_str,
    CoqError,
)
from src.utils import get_logger

LOGGER = get_logger("proof_script")


@dataclass(frozen=True)
class Hypothesis:
    name: str
    value: str


@dataclass(frozen=True)
class ProofObligation:
    hypotheses: t.Dict[str, Hypothesis]
    goal: str

    @classmethod
    def from_obligation(cls, obligation: c.contexts.Obligation) -> "ProofObligation":
        hypotheses = obligation.hypotheses
        hyp_vars = [hyp.split(":")[0].strip() for hyp in hypotheses]
        hyp_values = [":".join(hyp.split(":")[1:]).strip() for hyp in hypotheses]

        hypotheses_dict: t.Dict[str, Hypothesis] = {}
        for vars_str, value in zip(hyp_vars, hyp_values):
            vars = [var.strip() for var in vars_str.split(",")]
            for var in vars:
                hypotheses_dict[var] = Hypothesis(var, value)
        return cls(
            hypotheses=hypotheses_dict,
            goal=obligation.goal,
        )

    # def subsumes(self, other: "ProofObligation") -> bool:
    #     """
    #     self subsumes other if their goals are the same, and all of self's hypotheses are in other's hypotheses
    #     """
