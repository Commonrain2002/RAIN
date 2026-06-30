import unittest
import typing as t
import coq_serapy as c

from src.proof_obligation import ProofObligation, Hypothesis
from src.coq_serapy_util import Coq, CoqError


class Test_ProofObligation_FromObligation(unittest.TestCase):
    def test_basic(self) -> None:
        o = c.contexts.Obligation(
            hypotheses="""e : Logic.eq k x

Hk_map : Logic.eq
  (M.find A k
     match M.find A x m with
     | Some v => M.add A x v a
     | None => a
     end) (Some v)

Hk_a : forall _ : Logic.eq (M.find A k a) (Some v), S.In k s'

Hx_s' : not (S.In x s')

Hx_s : S.In x s

s' : S.t

a : M.t A

x : S.elt

v : A

k : M.key

s : S.t

m : M.t A

A : Type""".split(
                "\n\n"
            ),
            goal="S.In k (S.add x s')",
        )

        obligation = ProofObligation.from_obligation(o)

        self.assertEqual(
            [h.name for h in obligation.hypotheses.values()],
            [
                "e",
                "Hk_map",
                "Hk_a",
                "Hx_s'",
                "Hx_s",
                "s'",
                "a",
                "x",
                "v",
                "k",
                "s",
                "m",
                "A",
            ],
        )
        self.assertEqual(
            [h.value for h in obligation.hypotheses.values()],
            [
                "Logic.eq k x",
                "Logic.eq\n  (M.find A k\n     match M.find A x m with\n     | Some v => M.add A x v a\n     | None => a\n     end) (Some v)",
                "forall _ : Logic.eq (M.find A k a) (Some v), S.In k s'",
                "not (S.In x s')",
                "S.In x s",
                "S.t",
                "M.t A",
                "S.elt",
                "A",
                "M.key",
                "S.t",
                "M.t A",
                "Type",
            ],
        )
        self.assertEqual(obligation.goal, "S.In k (S.add x s')")

    def test_multiple_vars(self) -> None:
        o = c.contexts.Obligation(
            hypotheses="""e, f : Logic.eq k x""".split("\n"),
            goal="S.In k (S.add x s')",
        )

        obligation = ProofObligation.from_obligation(o)

        self.assertEqual([h.name for h in obligation.hypotheses.values()], ["e", "f"])
        self.assertEqual(
            [h.value for h in obligation.hypotheses.values()], ["Logic.eq k x"] * 2
        )
        self.assertEqual(obligation.goal, "S.In k (S.add x s')")


if __name__ == "__main__":
    unittest.main()
