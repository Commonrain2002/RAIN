import unittest

from src.coq_serapy_util import LemmaLocation
from src.environment.environment import (
    Environment,
)
from src.environment.config import EnvironmentConfig
from src.environment.actions import (
    EditAction,
    DefinitionsAction,
    SearchAction,
)
from src.utils import get_logger

"""
Tests for environment.py . Most of these tests are broken, and it's not really worth fixing them all. Fix them as you need to test new functionality.
"""

LOGGER = get_logger(__name__)

ONE_PLUS_N_COMMAND = "Example one_plus_n: forall n: nat, 1 + n > n."


class TestCode(unittest.TestCase):
    def test_one_plus_n_initial_code(self):
        env = Environment(ONE_PLUS_N_COMMAND)
        self.assertEqual(
            env.observation_code,
            """Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
Admitted.""",
        )


class TestObservation(unittest.TestCase):
    def test_one_plus_n_initial_code(self):
        """testing the theorem with an empty proof."""
        env = Environment(ONE_PLUS_N_COMMAND)

        observation = env.base_observation
        self.assertEqual(
            observation,
            """<<PROPOSITION>>
forall n : nat, gt (Nat.add (S O) n) n

<<CURRENT CODE>>
Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
Admitted.

<<CURRENT PROOF STATE>>

---

forall n : nat, gt (Nat.add (S O) n) n

""",
        )

    # TODO: this test is broken. either delete freeform edits or fix this test.
    def test_sum_tail_equivalent_fetches_definitions(self):
        self.maxDiff = None
        env = Environment(
            """Theorem sum_tail_correct: forall l,
    sum_tail l = sum l""",
            lemma_location=LemmaLocation(
                "basic",
                "SumTailEquivalent.v",
                "sum_tail_correct",
                [],
            ),
            include_lemmas_and_definitions=True,
        )

        observation = env.base_observation
        self.assertEqual(
            observation,
            """<<PROPOSITION>>
Theorem sum_tail_correct: forall l, sum_tail l = sum l

<<CURRENT CODE>>
Theorem sum_tail_correct: forall l,
    sum_tail l = sum l
Proof.
Admitted.

<<ERROR MESSAGE>>
observing a none context. this means we're not inside a proof.

""",
        )

    def test_one_plus_n_initial_code_with_Qed(self):
        """same as initial code, but with Qed instead of Admitted."""
        env = Environment(ONE_PLUS_N_COMMAND)
        env.step(
            EditAction(
                new_code="\n".join(
                    [
                        ONE_PLUS_N_COMMAND,
                        "Proof.",
                        "Qed.",
                    ]
                )
            )
        )

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "<<PROPOSITION>>",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "<<CURRENT CODE>>",
                    "Example one_plus_n: forall n: nat, 1 + n > n.",
                    "Proof.",
                    "Qed.",
                    "",
                    "<<ERROR AT>>",
                    "line 3: `Qed.`",
                    "",
                    "<<ERROR MESSAGE>>",
                    " (in proof one_plus_n): Attempt to save an incomplete proof",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "",
                ]
            ),
        )

    def test_one_plus_n_complete_solution(self):
        """testing the theorem with a complete proof."""
        env = Environment(ONE_PLUS_N_COMMAND)
        env.step(
            EditAction(
                new_code="\n".join(
                    [
                        "Theorem t: forall n: nat, 1 + n > n.",
                        "Proof.",
                        "intros.",
                        "induction n.",
                        "simpl.",
                        "auto.",
                        "simpl.",
                        "auto.",
                        "Qed.",
                    ]
                )
            )
        )

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "<<PROPOSITION>>",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "<<CURRENT CODE>>",
                    "Theorem t: forall n: nat, 1 + n > n.",
                    "Proof.",
                    "intros.",
                    "induction n.",
                    "simpl.",
                    "auto.",
                    "simpl.",
                    "auto.",
                    "Qed.",
                    "",
                    "<<CURRENT PROOF STATE>>",
                    "Proof finished.",
                    "",
                    "",
                ]
            ),
        )

    def test_one_plus_n_incomplete_solution_with_error(self):
        """testing the theorem with an incomplete proof with errors"""
        env = Environment(ONE_PLUS_N_COMMAND)
        env.step(
            EditAction(
                new_code="\n".join(
                    [
                        "Theorem t: forall n: nat, 1 + n > n.",
                        "Proof.",
                        "induction a.",
                        "Qed.",
                    ]
                )
            )
        )

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "<<PROPOSITION>>",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "<<CURRENT CODE>>",
                    "Theorem t: forall n: nat, 1 + n > n.",
                    "Proof.",
                    "induction a.",
                    "Qed.",
                    "",
                    "<<ERROR AT>>",
                    "line 3: `induction a.`",
                    "",
                    "<<ERROR MESSAGE>>",
                    "The reference a was not found in the current environment.",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "",
                ]
            ),
        )

    def test_span_delimited_errors(self):
        env = Environment(
            ONE_PLUS_N_COMMAND,
            use_error_span=True,
            tactics_only=True,
        )

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "The section of code that caused the error is delimited with the <ERROR> and </ERROR> tags.",
                    " These tags are not part of the code, they just indicate where the error is. Make sure you do not include them in any new code you emit.",
                    "",
                    "<<PROPOSITION>>",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "<<CURRENT CODE>>",
                    "",
                    "",
                    "<<ERROR MESSAGE>>",
                    " (in proof one_plus_n): Attempt to save an incomplete proof",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "",
                ]
            ),
        )

    def test_span_delimited_errors_2(self):
        self.maxDiff = None
        env = Environment(
            ONE_PLUS_N_COMMAND,
            use_error_span=True,
            tactics_only=True,
        )

        env.step(EditAction(new_code="intros n m."))

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "The section of code that caused the error is delimited with the <ERROR> and </ERROR> tags.",
                    " These tags are not part of the code, they just indicate where the error is. Make sure you do not include them in any new code you emit.",
                    "",
                    "<<PROPOSITION>>",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "<<CURRENT CODE>>",
                    "<ERROR> intros n m. </ERROR>",
                    "",
                    "<<ERROR MESSAGE>>",
                    "No product even after head-reduction.",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "",
                ]
            ),
        )

    def test_span_delimited_errors_Comp_mon(self):
        env = Environment(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            ),
            config=EnvironmentConfig(
                tactics_only=True,
                use_error_span=True,
                title_delimiter="[",
                include_lemmas_and_definitions_in_observation=False,
            ),
        )

        self.maxDiff = None

        env.step(
            EditAction(
                new_code="""unfold monotonic; intros.
split.
- apply Comp_increasing. apply HG. apply HF.
- intros. apply Comp_evolve_t.
  + apply HG.
  + apply HF.
  + assumption.
  + assumption.
- intros. apply Comp_evolve_a.
  + apply HG.
  + apply HF.
  + assumption.
  + assumption."""
            )
        )

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "The section of code that caused the error is delimited with the <ERROR> and </ERROR> tags.",
                    " These tags are not part of the code, they just indicate where the error is. Make sure you do not include them in any new code you emit.",
                    "",
                    "[PROPOSITION]",
                    "monotonic TX TY (Comp G F)",
                    "",
                    "[CURRENT CODE]",
                    "<ERROR> unfold monotonic; intros. </ERROR>",
                    "split.",
                    "- apply Comp_increasing. apply HG. apply HF.",
                    "- intros. apply Comp_evolve_t.",
                    "  + apply HG.",
                    "  + apply HF.",
                    "  + assumption.",
                    "  + assumption.",
                    "- intros. apply Comp_evolve_a.",
                    "  + apply HG.",
                    "  + apply HF.",
                    "  + assumption.",
                    "  + assumption.",
                    "",
                    "[ERROR MESSAGE]",
                    "Cannot coerce monotonic to an evaluable reference.",
                    "",
                    "[LAST WORKING PROOF STATE]",
                    "HG : monotonic TX TY G",
                    "HF : monotonic TX TY F",
                    "F,G : function X Y",
                    "TY : reduction_t A Y",
                    "TX : reduction_t A X",
                    "X,Y : Type",
                    "A : Type",
                    "",
                    "---",
                    "",
                    "monotonic TX TY (Comp G F)",
                    "",
                    "",
                ]
            ),
        )

    def test_proof_prefix_one_plus_n(self):
        env = Environment(
            ONE_PLUS_N_COMMAND,
            proof_prefix="intros.",
            tactics_only=True,
        )

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "<<PROPOSITION>>",
                    "gt (Nat.add (S O) n) n",
                    "",
                    "<<CURRENT CODE>>",
                    "",
                    "",
                    "<<ERROR AT>>",
                    "line 1: `Qed.`",
                    "",
                    "<<ERROR MESSAGE>>",
                    " (in proof one_plus_n): Attempt to save an incomplete proof",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "n : nat",
                    "",
                    "---",
                    "",
                    "gt (Nat.add (S O) n) n",
                    "",
                    "",
                ]
            ),
        )

    def test_proof_prefix_one_plus_n_subgoal(self):
        env = Environment(
            ONE_PLUS_N_COMMAND,
            proof_prefix="intros. induction n. -",
            tactics_only=True,
        )

        print(env.editor.runnable_code)

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "<<PROPOSITION>>",
                    "gt (Nat.add (S O) O) O",
                    "",
                    "<<CURRENT CODE>>",
                    "",
                    "",
                    "<<ERROR AT>>",
                    "line 1: `Qed.`",
                    "",
                    "<<ERROR MESSAGE>>",
                    " (in proof one_plus_n): Attempt to save an incomplete proof",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "gt (Nat.add (S O) O) O",
                    "",
                    "",
                ]
            ),
        )

    def test_proof_prefix_one_plus_n_unfocused_subgoals_assertion_error(self):
        self.assertRaises(
            AssertionError,
            lambda: Environment(
                ONE_PLUS_N_COMMAND,
                proof_prefix="intros. induction n.",
                tactics_only=True,
            ),
        )

    def test_proof_prefix_Comp_mon(self):
        env = Environment(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            ),
            proof_prefix="""apply mkmon.
- admit.
- admit.
- intros R S H1 H2. unfold evolve_a. intros a. unfold Comp. apply mon_a.
    + exact HG.
    + Check Lbl. Print Lbl. Check reduction_t. Print reduction_t.""",
            tactics_only=True,
            include_lemmas_and_definitions=True,
        )

        self.maxDiff = None

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "<<PROPOSITION>>",
                    "evolve TX TY (F R) (F S)",
                    "",
                    "<<CURRENT CODE>>",
                    "",
                    "",
                    "<<ERROR AT>>",
                    "line 1: `Qed.`",
                    "",
                    "<<ERROR MESSAGE>>",
                    " (in proof Comp_mon): Attempt to save an incomplete proof",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "a : A",
                    "H2 : incl R S",
                    "H1 : evolve TX TY R S",
                    "R,S : relation2 X Y",
                    "HG : monotonic TX TY G",
                    "HF : monotonic TX TY F",
                    "F,G : function X Y",
                    "TY : reduction_t A Y",
                    "TX : reduction_t A X",
                    "X,Y : Type",
                    "A : Type",
                    "",
                    "---",
                    "",
                    "evolve TX TY (F R) (F S)",
                    "",
                    "<<DEFINITIONS>>",
                    "Inductive Lbl (A : Type) : Type :=  T : Lbl A | L : forall _ : A, Lbl A",
                    "",
                    "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
                    "",
                    "evolve = ",
                    "fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)",
                    "  (R S : relation2 X Y) => forall l : Lbl A, evolve_1 TX TY l R S",
                    "     : forall (A X Y : Type) (_ : reduction_t A X) ",
                    "         (_ : reduction_t A Y) (_ : relation2 X Y) ",
                    "         (_ : relation2 X Y), Prop",
                    "",
                    "evolve_1 = ",
                    "fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y) ",
                    "  (l : Lbl A) (R S : relation2 X Y) => diagram (TX l) R (Weak TY l) S",
                    "     : forall (A X Y : Type) (_ : reduction_t A X) ",
                    "         (_ : reduction_t A Y) (_ : Lbl A) (_ : relation2 X Y)",
                    "         (_ : relation2 X Y), Prop",
                    "",
                    "evolve_a = ",
                    "fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)",
                    "  (R S : relation2 X Y) => forall a : A, evolve_1 TX TY (L a) R S",
                    "     : forall (A X Y : Type) (_ : reduction_t A X) ",
                    "         (_ : reduction_t A Y) (_ : relation2 X Y) ",
                    "         (_ : relation2 X Y), Prop",
                    "",
                    "evolve_t = ",
                    "fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)",
                    "  (R S : relation2 X Y) => evolve_1 TX TY (T A) R S",
                    "     : forall (A X Y : Type) (_ : reduction_t A X) ",
                    "         (_ : reduction_t A Y) (_ : relation2 X Y) ",
                    "         (_ : relation2 X Y), Prop",
                    "",
                    "function = ",
                    "fun X Y : Type => forall _ : relation2 X Y, relation2 X Y",
                    "     : forall (_ : Type) (_ : Type), Type",
                    "",
                    "incl = ",
                    "fun (X Y : Type) (R1 R2 : relation2 X Y) =>",
                    "forall (x : X) (y : Y) (_ : R1 x y), R2 x y",
                    "     : forall X Y : Type, relation (relation2 X Y)",
                    "",
                    "increasing = ",
                    "fun (X Y : Type) (F : function X Y) =>",
                    "forall (R S : relation2 X Y) (_ : incl R S), incl (F R) (F S)",
                    "     : forall (X Y : Type) (_ : function X Y), Prop",
                    "",
                    "Record monotonic (A X Y : Type) (TX : reduction_t A X) ",
                    "(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon",
                    "  { mon_m : increasing F;",
                    "    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)",
                    "              (_ : incl R S), evolve_t TX TY (F R) (F S);",
                    "    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)",
                    "              (_ : incl R S), evolve_a TX TY (F R) (F S) }",
                    "",
                    "Record monotonic (A X Y : Type) (TX : reduction_t A X) ",
                    "(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon",
                    "  { mon_m : increasing F;",
                    "    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)",
                    "              (_ : incl R S), evolve_t TX TY (F R) (F S);",
                    "    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)",
                    "              (_ : incl R S), evolve_a TX TY (F R) (F S) }",
                    "",
                    "reduction = ",
                    "fun A X : Type => forall _ : A, relation X",
                    "     : forall (_ : Type) (_ : Type), Type",
                    "",
                    "reduction_t = ",
                    "fun A : Type => reduction (Lbl A)",
                    "     : forall (_ : Type) (_ : Type), Type",
                    "",
                    "relation = fun X : Type => relation2 X X",
                    "     : forall _ : Type, Type",
                    "",
                    "relation2 = ",
                    "fun X Y : Type => forall (_ : X) (_ : Y), Prop",
                    "     : forall (_ : Type) (_ : Type), Type",
                    "",
                    "<<PROVEN THEOREMS/LEMMAS>>",
                    "Lemma chaining_l_mon: expansion1 TX TX E -> monotonic TX TY (chaining_l E).",
                    "",
                    "Lemma chaining_r_mon: simulation TY TY T -> monotonic TX TY (chaining_r T).",
                    "",
                    "Lemma constant_mon: simulation TX TY R -> monotonic TX TY (constant R).",
                    "",
                    "Lemma identity_mon: monotonic TX TY (identity (X:=X) (Y:=Y)).",
                    "",
                    "",
                ]
            ),
        )

    def test_sigma_gamma_1(self):
        env = Environment(
            "Lemma sigma_gamma1 A : sigma # (gamma1 A) = tau1 A ++ [#] ++ gamma A.",
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/coq-library-undecidability",
                coq_version="8.12",
                file_name="theories/CFG/Reductions/PCP_to_CFPI.v",
                section_names=["PCP_CFPI"],
                lemma_name="sigma_gamma1",
            ),
            tactics_only=True,
            include_lemmas_and_definitions=True,
        )

        self.maxDiff = None

        print(env.base_observation)
        # print env.base_observation to a file
        with open("sigma_gamma1_observation.txt", "w") as file:
            file.write(env.base_observation)

        self.assertEqual(env.base_observation, """""")


class TestIsInitialGoalProven(unittest.TestCase):
    def test_one_plus_n_initial_code(self):
        """testing the theorem with an empty proof."""
        env = Environment(ONE_PLUS_N_COMMAND)

        self.assertFalse(env.done)

    def test_one_plus_n_initial_code_with_Qed(self):
        """same as initial code, but with Qed instead of Admitted."""
        env = Environment(ONE_PLUS_N_COMMAND)

        _, done = env.step(
            EditAction(
                new_code="\n".join(
                    [
                        ONE_PLUS_N_COMMAND,
                        "Proof.",
                        "Qed.",
                    ]
                )
            )
        )

        self.assertFalse(done)

    def test_one_plus_n_complete_solution(self):
        """testing the theorem with a complete proof."""
        env = Environment("Theorem t: forall n: nat, 1 + n > n.")
        _, done = env.step(
            EditAction(
                new_code="\n".join(
                    [
                        "Theorem t: forall n: nat, 1 + n > n.",
                        "Proof.",
                        "intros.",
                        "induction n.",
                        "simpl.",
                        "auto.",
                        "simpl.",
                        "auto.",
                        "Qed.",
                    ]
                )
            )
        )

        self.assertTrue(done)

    def test_one_plus_n_incomplete_solution(self):
        """testing the theorem with an incomplete proof that has no errors"""
        env = Environment(ONE_PLUS_N_COMMAND)
        _, done = env.step(
            EditAction(
                new_code="\n".join(
                    [
                        "Theorem t: forall n: nat, 1 + n > n.",
                        "Proof.",
                        "intros.",
                        "Admitted.",
                    ]
                )
            )
        )

        self.assertFalse(done)

    def test_regression_one_plus_n_complete_solution_with_equivalent_proposition(self):
        env = Environment("Lemma one_plus_n: forall n, 1 + n > n.")
        _, done = env.step(
            EditAction(
                new_code="""Lemma one_plus_n: forall n : nat, 1 + n > n.
Proof.
  intros n.
  apply gt_Sn_n.
Qed."""
            )
        )

        self.assertTrue(done)

    def test_regression_double_plus(self):
        env = Environment(
            "Lemma double_plus: forall n, double n = n + n.",
            lemma_location=LemmaLocation("basic", "BinNat.v", "double_plus", []),
            include_lemmas_and_definitions=True,
            title_start_delimiter="[",
            title_end_delimiter="]",
            tactics_only=True,
            use_error_span=True,
        )

        self.assertFalse(env.done)

        observation, done, env = env.step_retrying_on_uncaught_error(
            EditAction(
                new_code="intros n.\ninduction n as [| n' IHn'].\n- simpl. reflexivity.\n- simpl. rewrite -> IHn'. rewrite -> plus_n_Sm. reflexivity."
            )
        )

        LOGGER.info(observation)

        self.assertTrue(done)

    def test_Comp_mon_with_prefix(self):
        env = Environment(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            ),
            proof_prefix="""apply mkmon.
- """,
            tactics_only=True,
            include_lemmas_and_definitions=True,
        )

        observation, _ = env.step(
            EditAction(new_code="intros R S HRS. apply (mon_m HG (mon_m HF HRS)).")
        )

        self.maxDiff = None

        self.assertEqual(
            observation,
            """<<PROPOSITION>>
increasing (Comp G F)

<<CURRENT CODE>>
intros R S HRS. apply (mon_m HG (mon_m HF HRS)).

<<ERROR AT>>
line 2: `Qed.`

<<ERROR MESSAGE>>
 (in proof Comp_mon): Attempt to save an incomplete proof

<<LAST WORKING PROOF STATE>>
Proof finished.

<<DEFINITIONS>>
Comp = 
fun (X Y X' Y' X'' Y'' : Type) (G : function2 X' Y' X'' Y'')
  (F : function2 X Y X' Y') (R : relation2 X Y) => 
G (F R)
     : forall (X Y X' Y' X'' Y'' : Type) (_ : function2 X' Y' X'' Y'')
         (_ : function2 X Y X' Y') (_ : relation2 X Y), 
       relation2 X'' Y''

Inductive Lbl (A : Type) : Type :=  T : Lbl A | L : forall _ : A, Lbl A

Inductive nat : Set :=  O : nat | S : forall _ : nat, nat

evolve = 
fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)
  (R S : relation2 X Y) => forall l : Lbl A, evolve_1 TX TY l R S
     : forall (A X Y : Type) (_ : reduction_t A X) 
         (_ : reduction_t A Y) (_ : relation2 X Y) 
         (_ : relation2 X Y), Prop

evolve_a = 
fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)
  (R S : relation2 X Y) => forall a : A, evolve_1 TX TY (L a) R S
     : forall (A X Y : Type) (_ : reduction_t A X) 
         (_ : reduction_t A Y) (_ : relation2 X Y) 
         (_ : relation2 X Y), Prop

evolve_t = 
fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)
  (R S : relation2 X Y) => evolve_1 TX TY (T A) R S
     : forall (A X Y : Type) (_ : reduction_t A X) 
         (_ : reduction_t A Y) (_ : relation2 X Y) 
         (_ : relation2 X Y), Prop

function = 
fun X Y : Type => forall _ : relation2 X Y, relation2 X Y
     : forall (_ : Type) (_ : Type), Type

function2 = 
fun X Y X' Y' : Type => forall _ : relation2 X Y, relation2 X' Y'
     : forall (_ : Type) (_ : Type) (_ : Type) (_ : Type), Type

incl = 
fun (X Y : Type) (R1 R2 : relation2 X Y) =>
forall (x : X) (y : Y) (_ : R1 x y), R2 x y
     : forall X Y : Type, relation (relation2 X Y)

increasing = 
fun (X Y : Type) (F : function X Y) =>
forall (R S : relation2 X Y) (_ : incl R S), incl (F R) (F S)
     : forall (X Y : Type) (_ : function X Y), Prop

Record monotonic (A X Y : Type) (TX : reduction_t A X) 
(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon
  { mon_m : increasing F;
    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)
              (_ : incl R S), evolve_t TX TY (F R) (F S);
    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)
              (_ : incl R S), evolve_a TX TY (F R) (F S) }

Record monotonic (A X Y : Type) (TX : reduction_t A X) 
(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon
  { mon_m : increasing F;
    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)
              (_ : incl R S), evolve_t TX TY (F R) (F S);
    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)
              (_ : incl R S), evolve_a TX TY (F R) (F S) }

reduction = 
fun A X : Type => forall _ : A, relation X
     : forall (_ : Type) (_ : Type), Type

reduction_t = 
fun A : Type => reduction (Lbl A)
     : forall (_ : Type) (_ : Type), Type

relation2 = 
fun X Y : Type => forall (_ : X) (_ : Y), Prop
     : forall (_ : Type) (_ : Type), Type

<<PROVEN THEOREMS/LEMMAS>>
Lemma chaining_l_mon: expansion1 TX TX E -> monotonic TX TY (chaining_l E).

Lemma chaining_r_mon: simulation TY TY T -> monotonic TX TY (chaining_r T).

Lemma constant_mon: simulation TX TY R -> monotonic TX TY (constant R).

Lemma identity_mon: monotonic TX TY (identity (X:=X) (Y:=Y)).

""",
        )

        self.assertTrue(env.is_initial_goal_proven)

    def test_Comp_mon_with_prefix_not_proven(self):
        env = Environment(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            ),
            proof_prefix="""apply mkmon.
- """,
            tactics_only=True,
            include_lemmas_and_definitions=True,
        )

        observation, _ = env.step(EditAction(new_code="intros R S HRS."))

        self.maxDiff = None

        self.assertEqual(
            observation,
            """<<PROPOSITION>>
increasing (Comp G F)

<<CURRENT CODE>>
intros R S HRS.

<<ERROR AT>>
line 2: `Qed.`

<<ERROR MESSAGE>>
 (in proof Comp_mon): Attempt to save an incomplete proof

<<LAST WORKING PROOF STATE>>
HRS : incl R S
R,S : relation2 X Y
HG : monotonic TX TY G
HF : monotonic TX TY F
F,G : function X Y
TY : reduction_t A Y
TX : reduction_t A X
X,Y : Type
A : Type

---

incl (Comp G F R) (Comp G F S)

<<DEFINITIONS>>
Comp = 
fun (X Y X' Y' X'' Y'' : Type) (G : function2 X' Y' X'' Y'')
  (F : function2 X Y X' Y') (R : relation2 X Y) => 
G (F R)
     : forall (X Y X' Y' X'' Y'' : Type) (_ : function2 X' Y' X'' Y'')
         (_ : function2 X Y X' Y') (_ : relation2 X Y), 
       relation2 X'' Y''

Inductive Lbl (A : Type) : Type :=  T : Lbl A | L : forall _ : A, Lbl A

Inductive nat : Set :=  O : nat | S : forall _ : nat, nat

evolve = 
fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)
  (R S : relation2 X Y) => forall l : Lbl A, evolve_1 TX TY l R S
     : forall (A X Y : Type) (_ : reduction_t A X) 
         (_ : reduction_t A Y) (_ : relation2 X Y) 
         (_ : relation2 X Y), Prop

evolve_a = 
fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)
  (R S : relation2 X Y) => forall a : A, evolve_1 TX TY (L a) R S
     : forall (A X Y : Type) (_ : reduction_t A X) 
         (_ : reduction_t A Y) (_ : relation2 X Y) 
         (_ : relation2 X Y), Prop

evolve_t = 
fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y)
  (R S : relation2 X Y) => evolve_1 TX TY (T A) R S
     : forall (A X Y : Type) (_ : reduction_t A X) 
         (_ : reduction_t A Y) (_ : relation2 X Y) 
         (_ : relation2 X Y), Prop

function = 
fun X Y : Type => forall _ : relation2 X Y, relation2 X Y
     : forall (_ : Type) (_ : Type), Type

function2 = 
fun X Y X' Y' : Type => forall _ : relation2 X Y, relation2 X' Y'
     : forall (_ : Type) (_ : Type) (_ : Type) (_ : Type), Type

incl = 
fun (X Y : Type) (R1 R2 : relation2 X Y) =>
forall (x : X) (y : Y) (_ : R1 x y), R2 x y
     : forall X Y : Type, relation (relation2 X Y)

increasing = 
fun (X Y : Type) (F : function X Y) =>
forall (R S : relation2 X Y) (_ : incl R S), incl (F R) (F S)
     : forall (X Y : Type) (_ : function X Y), Prop

Record monotonic (A X Y : Type) (TX : reduction_t A X) 
(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon
  { mon_m : increasing F;
    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)
              (_ : incl R S), evolve_t TX TY (F R) (F S);
    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)
              (_ : incl R S), evolve_a TX TY (F R) (F S) }

Record monotonic (A X Y : Type) (TX : reduction_t A X) 
(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon
  { mon_m : increasing F;
    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)
              (_ : incl R S), evolve_t TX TY (F R) (F S);
    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)
              (_ : incl R S), evolve_a TX TY (F R) (F S) }

reduction = 
fun A X : Type => forall _ : A, relation X
     : forall (_ : Type) (_ : Type), Type

reduction_t = 
fun A : Type => reduction (Lbl A)
     : forall (_ : Type) (_ : Type), Type

relation2 = 
fun X Y : Type => forall (_ : X) (_ : Y), Prop
     : forall (_ : Type) (_ : Type), Type

<<PROVEN THEOREMS/LEMMAS>>
Lemma chaining_l_mon: expansion1 TX TX E -> monotonic TX TY (chaining_l E).

Lemma chaining_r_mon: simulation TY TY T -> monotonic TX TY (chaining_r T).

Lemma constant_mon: simulation TX TY R -> monotonic TX TY (constant R).

Lemma identity_mon: monotonic TX TY (identity (X:=X) (Y:=Y)).

""",
        )

        self.assertFalse(env.is_initial_goal_proven)

    def test_Comp_mon_hammer_prefix_with_admits(self):
        env = Environment(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            ),
            proof_prefix="""apply mkmon; intros.
- admit.
- admit.
- eapply HG.
-- admit.
-- """,
            tactics_only=True,
            include_lemmas_and_definitions=True,
        )

        observation, _ = env.step(EditAction(new_code="hammer."))

        self.maxDiff = None

        self.assertTrue(
            observation.startswith(
                """<<PROPOSITION>>
incl (F R) (F S)

<<CURRENT CODE>>
hammer.

<<ERROR AT>>
line 2: `Qed.`

<<ERROR MESSAGE>>
 (in proof Comp_mon): Attempt to save a proof with given up goals. If this is
really what you want to do, use Admitted in place of Qed.

<<LAST WORKING PROOF STATE>>
Proof finished.

<<DEFINITIONS>>"""
            )
        )

        self.assertTrue(env.is_initial_goal_proven)


class TestStep(unittest.TestCase):
    def setUp(self) -> None:
        self.maxDiff = None
        return super().setUp()

    def test_one_plus_n_adding_working_tactic(self):
        """testing the theorem with an empty proof, then adding intros."""
        env = Environment(ONE_PLUS_N_COMMAND)

        env.step(
            EditAction(
                new_code="\n".join(
                    [
                        ONE_PLUS_N_COMMAND,
                        "Proof.",
                        "intros.",
                        "Admitted.",
                    ]
                )
            )
        )

        self.assertEqual(
            env.observation_code,
            "\n".join(
                [
                    ONE_PLUS_N_COMMAND,
                    "Proof.",
                    "intros.",
                    "Admitted.",
                ]
            ),
        )

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "<<CURRENT CODE>>",
                    "Example one_plus_n: forall n: nat, 1 + n > n.",
                    "Proof.",
                    "intros.",
                    "Admitted.",
                    "",
                    "<<CURRENT PROOF STATE>>",
                    "n : nat",
                    "",
                    "---",
                    "",
                    "gt (Nat.add (S O) n) n",
                    "",
                    "",
                ]
            ),
        )

        self.assertFalse(env.done)

    def test_one_plus_n_adding_error_tactic(self):
        """testing the theorem with an empty proof, then adding induction a."""
        env = Environment(ONE_PLUS_N_COMMAND)

        env.step(
            EditAction(
                new_code="\n".join(
                    [
                        ONE_PLUS_N_COMMAND,
                        "Proof.",
                        "induction a.",
                        "Admitted.",
                    ]
                )
            )
        )

        self.assertEqual(
            env.observation_code,
            "\n".join(
                [
                    ONE_PLUS_N_COMMAND,
                    "Proof.",
                    "induction a.",
                    "Admitted.",
                ]
            ),
        )

        self.assertEqual(
            env.base_observation,
            "\n".join(
                [
                    "<<CURRENT CODE>>",
                    "Example one_plus_n: forall n: nat, 1 + n > n.",
                    "Proof.",
                    "induction a.",
                    "Admitted.",
                    "",
                    "<<ERROR AT>>",
                    "line 3: `induction a.`",
                    "",
                    "<<ERROR MESSAGE>>",
                    "The reference a was not found in the current environment.",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "",
                ]
            ),
        )

        self.assertFalse(env.done)

    def test_one_plus_n_lia(self):
        """testing whether the lia tactic works in environment"""
        env = Environment(ONE_PLUS_N_COMMAND)

        observation, done = env.step(
            EditAction(
                new_code="""Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
lia.
Qed."""
            )
        )

        self.assertEqual(
            observation,
            """<<CURRENT CODE>>
Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
lia.
Qed.

<<CURRENT PROOF STATE>>
Proof finished.


""",
        )

        self.assertTrue(done)

    def test_definitions_working(self):
        """testing an action to get definitions with a working proof"""
        env = Environment(ONE_PLUS_N_COMMAND)

        observation, done = env.step(
            EditAction(
                new_code="\n".join(
                    [
                        ONE_PLUS_N_COMMAND,
                        "Proof.",
                        "intros.",
                        "Admitted.",
                    ]
                )
            )
        )

        self.assertEqual(
            observation,
            "\n".join(
                [
                    "<<CURRENT CODE>>",
                    ONE_PLUS_N_COMMAND,
                    "Proof.",
                    "intros.",
                    "Admitted.",
                    "",
                    "<<CURRENT PROOF STATE>>",
                    "n : nat",
                    "",
                    "---",
                    "",
                    "gt (Nat.add (S O) n) n",
                    "",
                    "",
                    "",
                ]
            ),
        )

        self.assertFalse(done)

        observation, done = env.step(
            DefinitionsAction(identifiers=["gt", "Nat.add", "S", "O"])
        )

        self.assertEqual(
            observation,
            "\n".join(
                [
                    "<<CURRENT CODE>>",
                    ONE_PLUS_N_COMMAND,
                    "Proof.",
                    "intros.",
                    "Admitted.",
                    "",
                    "<<CURRENT PROOF STATE>>",
                    "n : nat",
                    "",
                    "---",
                    "",
                    "gt (Nat.add (S O) n) n",
                    "",
                    "",
                    "<<DEFINITIONS>>",
                    "gt = fun n m : nat => lt m n",
                    "     : forall (_ : nat) (_ : nat), Prop",
                    "",
                    "Arguments gt (_ _)%nat_scope",
                    "Nat.add = ",
                    "fix add (n m : nat) {struct n} : nat :=",
                    "  match n with",
                    "  | O => m",
                    "  | S p => S (add p m)",
                    "  end",
                    "     : forall (_ : nat) (_ : nat), nat",
                    "",
                    "Arguments Nat.add (_ _)%nat_scope",
                    "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
                    "",
                    "Arguments S _%nat_scope",
                    "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
                    "",
                    "Arguments S _%nat_scope",
                    "gt",
                    "     : forall (_ : nat) (_ : nat), Prop",
                    "Nat.add",
                    "     : forall (_ : nat) (_ : nat), nat",
                    "S",
                    "     : forall _ : nat, nat",
                    "O",
                    "     : nat",
                    "",
                    "",
                ]
            ),
        )

        self.assertFalse(done)

    def test_definitions_error(self):
        """testing an action to get definitions with an error state"""

        env = Environment(ONE_PLUS_N_COMMAND)

        observation, done = env.step(
            EditAction(
                new_code="\n".join(
                    [
                        ONE_PLUS_N_COMMAND,
                        "Proof.",
                        "induction a.",
                        "Admitted.",
                    ]
                )
            )
        )

        self.assertEqual(
            observation,
            "\n".join(
                [
                    "<<CURRENT CODE>>",
                    "Example one_plus_n: forall n: nat, 1 + n > n.",
                    "Proof.",
                    "induction a.",
                    "Admitted.",
                    "",
                    "<<ERROR AT>>",
                    "line 3: `induction a.`",
                    "",
                    "<<ERROR MESSAGE>>",
                    "The reference a was not found in the current environment.",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "",
                    "",
                ]
            ),
        )

        self.assertFalse(done)

        observation, done = env.step(
            DefinitionsAction(identifiers=["gt", "Nat.add", "S", "O"])
        )

        self.assertEqual(
            observation,
            "\n".join(
                [
                    "<<CURRENT CODE>>",
                    "Example one_plus_n: forall n: nat, 1 + n > n.",
                    "Proof.",
                    "induction a.",
                    "Admitted.",
                    "",
                    "<<ERROR AT>>",
                    "line 3: `induction a.`",
                    "",
                    "<<ERROR MESSAGE>>",
                    "The reference a was not found in the current environment.",
                    "",
                    "<<LAST WORKING PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "",
                    "<<DEFINITIONS>>",
                    "gt = fun n m : nat => lt m n",
                    "     : forall (_ : nat) (_ : nat), Prop",
                    "",
                    "Arguments gt (_ _)%nat_scope",
                    "Nat.add = ",
                    "fix add (n m : nat) {struct n} : nat :=",
                    "  match n with",
                    "  | O => m",
                    "  | S p => S (add p m)",
                    "  end",
                    "     : forall (_ : nat) (_ : nat), nat",
                    "",
                    "Arguments Nat.add (_ _)%nat_scope",
                    "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
                    "",
                    "Arguments S _%nat_scope",
                    "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
                    "",
                    "Arguments S _%nat_scope",
                    "gt",
                    "     : forall (_ : nat) (_ : nat), Prop",
                    "Nat.add",
                    "     : forall (_ : nat) (_ : nat), nat",
                    "S",
                    "     : forall _ : nat, nat",
                    "O",
                    "     : nat",
                    "",
                    "",
                ]
            ),
        )

        self.assertFalse(done)

    def test_search_for_non_identifier(self):
        env = Environment(ONE_PLUS_N_COMMAND)

        observation, done = env.step(SearchAction(identifiers=["O n"]))

        self.assertEqual(
            observation,
            "\n".join(
                [
                    "<<PROPOSITION>>",
                    "Example one_plus_n: forall n: nat, 1 + n > n.",
                    "",
                    "<<CURRENT CODE>>",
                    "Example one_plus_n: forall n: nat, 1 + n > n.",
                    "Proof.",
                    "Admitted.",
                    "",
                    "<<CURRENT PROOF STATE>>",
                    "",
                    "---",
                    "",
                    "forall n : nat, gt (Nat.add (S O) n) n",
                    "",
                    "",
                    "<<PROVEN THEOREMS/LEMMAS>>",
                    "",
                    "",
                    "",
                ]
            ),
        )

        self.assertFalse(done)

    # this test is broken right now, as the search returns too many results.
    # this causes the recursion depth to go too deep


class TestRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.maxDiff = None
        return super().setUp()

    def test_insert_n_zeros_before_normalize(self):
        env = Environment(
            "Theorem insert_n_zeros_before_normalize: forall b n, b = normalize (insert_n_zeros_before b n).",
        )

        self.assertRaises(
            Exception,
            lambda: env.step(
                EditAction(
                    new_code=""" Theorem insert_n_zeros_before_normalize :  forall b n, b = normalize (insert_n_zeros_before b n).
Proof.
  intros.
  unfold insert_n_zeros_before, normalize.
  rewrite <- app_nil_end.
  induction n.
  - simpl. reflexivity.
  - simpl. rewrite IHn. reflexivity.
Qed."""
                )
            ),
        )

    def test_proving_different_theorem_not_done(self) -> None:
        env = Environment(
            """Lemma exists_min: forall (l : (list nat)),
(l <> nil) -> exists h, min(l) = Some(h).""",
            lemma_location=LemmaLocation(
                project_name="basic",
                file_name="ExistsMin.v",
                lemma_name="exists_min",
                section_names=[],
            ),
        )

        env.step(
            EditAction(
                new_code="""Lemma add_commutes : forall a b c, a + b + c = a + c + b.
Proof.
  intros a b c.
  rewrite <- PeanoNat.Nat.add_assoc.
  rewrite (PeanoNat.Nat.add_comm b c).
  rewrite -> PeanoNat.Nat.add_assoc.
  reflexivity.
Qed."""
            )
        )

        self.assertFalse(env.done)

    def test_proving_helper_lemma_not_done(self) -> None:
        env = Environment(
            """Lemma sum_tail_correct:
  forall l,
    sum_tail l = sum l.""",
            lemma_location=LemmaLocation(
                project_name="basic",
                file_name="SumTailEquivalent.v",
                lemma_name="sum_tail_correct",
                section_names=[],
            ),
        )

        env.step(
            EditAction(
                new_code="""Lemma sum_tail'_behaviour : forall l n acc,
  sum_tail' (cons n l) acc = sum_tail' l (n + acc).
Proof.
  intros.
  simpl. reflexivity.
Qed.

Lemma sum_tail_correct:
  forall l,
    sum_tail l = sum l.
Proof.
  induction l as [| n l' IHl'].
  - reflexivity.
  - simpl. rewrite <- plus_n_O. rewrite <- sum_tail'_behaviour. rewrite IHl'. reflexivity.
Qed."""
            )
        )

        self.assertFalse(env.done)


if __name__ == "__main__":
    unittest.main(verbosity=2)
