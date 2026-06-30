import logging
from pathlib import Path
from typing import cast
import unittest
import coq_serapy as c
import re

from src.config import CONFIG
from src.coq_serapy_util import (
    IGNORE_LINE_REGEX,
    INDUCTIVE_CONSTRUCTOR_REGEX,
    MATCH_INDUCTIVE_REGEX,
    MATCH_RECORD_REGEX,
    RECORD_ITEM_REGEX,
    Coq,
    Definition,
    LemmaLocation,
    code_lemmas,
    normalize_whitespace,
    parse_identifiers_in_definition,
    read_commands,
    kill_non_tactic_commands,
    is_redundant,
)

from src.dataset import (
    COQ_WIGDERSON_DEV_PERFECT_PREMISE_NAMES,
    COQ_WIGDERSON_DEV_SAMPLED_DATASET,
)


ONE_PLUS_N_DEFINITION = "Example one_plus_n: forall n: nat, 1 + n > n."
ONE_PLUS_N_TYPE = "Example"
ONE_PLUS_N_NAME = "one_plus_n"
ONE_PLUS_N_STATEMENT = "forall n: nat, 1 + n > n"


class TestPrelude(unittest.TestCase):
    """Test the prelude"""

    def test_weak_up_to_Applications_Modular_F_mon(self):
        """testing file commands for weak-up-to/Applications.v/Modular/F_mon"""
        lemma_location = LemmaLocation(
            project_name="weak-up-to",
            file_name="Applications.v",
            section_names=["Modular"],
            lemma_name="F_mon",
        )

        self.assertEqual(
            lemma_location.prelude,
            str(
                (
                    Path(CONFIG.ROOT_DIR)
                    / CONFIG.PROJECTS_ROOT
                    / "weak-up-to"
                ).resolve()
            ),
        )


class TestFileCommands(unittest.TestCase):
    """Test the helper function to get commands preceding a lemma"""

    def test_weak_up_to_Applications_Modular_F_mon(self):
        """testing file commands for weak-up-to/Applications.v/Modular/F_mon"""
        lemma_location = LemmaLocation(
            project_name="weak-up-to",
            file_name="Applications.v",
            section_names=["Modular"],
            lemma_name="F_mon",
        )

        self.assertEqual(
            lemma_location.file_commands,
            [
                "Require Export Settings.",
                "Require Import Theory.",
                "Set Implicit Arguments.",
                "Section Modular.",
                "Variables A X: Type.",
                "Variable TX: reduction_t A X.",
                "Let F  := Comp (chaining_l (expand TX TX)) (chaining_r (bisim TX TX)).",
                "Let G  := Comp (star (X:=X)) (Union2 (identity (X:=X) (Y:=X)) (constant (bisim TX TX))).",
            ],
        )

    def test_double_incr_bin(self):
        """testing file commands for basic/BinNat.v/double_incr_bin"""
        lemma_location = LemmaLocation(
            project_name="basic",
            file_name="BinNat.v",
            lemma_name="double_incr_bin",
            section_names=[],
        )

        self.assertEqual(
            lemma_location.file_commands,
            [
                "Require Import List.",
                "Require Import Nat.",
                "Import ListNotations.",
                "Require Import Lia.",
                "Require Import PeanoNat.",
                "Inductive bin : Type :=\n  | Z\n  | B0 (n : bin)\n  | B1 (n : bin).",
                "Fixpoint incr (m:bin) : bin :=\n  match m with\n  | Z => B1 Z\n  | B0 m' => B1 m'\n  | B1 m' => B0 (incr m')\n  end.",
                "Fixpoint bin_to_nat (m:bin) : nat :=\n  match m with\n  | Z => O\n  | B0 m' => 2 * (bin_to_nat m')\n  | B1 m' => 1 + 2 * (bin_to_nat m')\n  end.",
                "Theorem bin_to_nat_preserves_incr : forall b : bin,\n  bin_to_nat (incr b) = 1 + bin_to_nat b.",
                "Proof.",
                "intros.",
                "induction b as [|b' IHb'|b' IHb']; auto.",
                "-",
                "simpl.",
                "rewrite IHb'.",
                "lia.",
                "Qed.",
                "Fixpoint nat_to_bin (n:nat) : bin :=\n  match n with\n  | O => Z\n  | S n' => incr (nat_to_bin n')\n  end.",
                "Theorem nat_bin_nat : forall n, bin_to_nat (nat_to_bin n) = n.",
                "Proof.",
                "intros.",
                "induction n as [|n' IHn']; auto.",
                "simpl.",
                "rewrite bin_to_nat_preserves_incr.",
                "rewrite IHn'.",
                "reflexivity.",
                "Qed.",
                "Fixpoint double (n:nat) :=\n  match n with\n  | O => O\n  | S n' => S (S (double n'))\n  end.",
                "Lemma double_plus : forall n, double n = n + n .",
                "Proof.",
                "intros n.",
                "induction n as [| n' IHn']; auto.",
                "simpl.",
                "rewrite IHn'.",
                "rewrite plus_n_Sm.",
                "reflexivity.",
                "Qed.",
                "Lemma double_incr : forall n : nat, double (S n) = S (S (double n)).",
                "Proof.",
                "intros.",
                "destruct n as [|n'] eqn: N.",
                "-",
                "auto.",
                "-",
                "unfold double.",
                "lia.",
                "Qed.",
                "Definition double_bin (b:bin) : bin :=\n  match b with\n  | Z => Z\n  | _ => B0 b\n  end.",
            ],
        )

# TODO: these tests are really complex integration tests
#   they are very brittle, so we should think about eliminating them
class TestRunCode(unittest.TestCase):
    def test_run_twice(self):
        """try running the same code twice, to confirm that reset is working"""
        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "Admitted.",
            ]
        )

        c = Coq()
        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(result.context)
        self.assertIsNone(result.error)
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 1)
        self.assertEqual(len(context.fg_goals), 1)
        self.assertEqual(len(context.bg_goals), 0)
        self.assertEqual(len(context.shelved_goals), 0)
        self.assertEqual(len(context.given_up_goals), 0)

        self.assertObligationEqual(
            [],
            "forall n : nat, gt (Nat.add (S O) n) n",
            context.fg_goals[0],
        )

        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(result.context)
        self.assertIsNone(result.error)
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 1)
        self.assertEqual(len(context.fg_goals), 1)
        self.assertEqual(len(context.bg_goals), 0)
        self.assertEqual(len(context.shelved_goals), 0)
        self.assertEqual(len(context.given_up_goals), 0)

        self.assertObligationEqual(
            [],
            "forall n : nat, gt (Nat.add (S O) n) n",
            context.fg_goals[0],
        )

    def test_one_plus_n_initial_code(self):
        """testing the theorem with an empty proof."""
        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "Admitted.",
            ]
        )

        c = Coq()
        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(result.context)
        self.assertIsNone(result.error)
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 1)
        self.assertEqual(len(context.fg_goals), 1)
        self.assertEqual(len(context.bg_goals), 0)
        self.assertEqual(len(context.shelved_goals), 0)
        self.assertEqual(len(context.given_up_goals), 0)

        self.assertObligationEqual(
            [],
            "forall n : nat, gt (Nat.add (S O) n) n",
            context.fg_goals[0],
        )

    def test_one_plus_n_initial_code_with_Qed(self):
        """same as initial code, but with Qed instead of Admitted."""
        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "Qed.",
            ]
        )

        c = Coq()
        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(context)
        self.assertEqual(
            result.error,
            (
                " (in proof one_plus_n): Attempt to save an incomplete proof",
                "Qed.",
                3,
            ),
        )
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 1)
        self.assertEqual(len(context.fg_goals), 1)
        self.assertEqual(len(context.bg_goals), 0)
        self.assertEqual(len(context.shelved_goals), 0)
        self.assertEqual(len(context.given_up_goals), 0)

        self.assertObligationEqual(
            [],
            "forall n : nat, gt (Nat.add (S O) n) n",
            context.fg_goals[0],
        )

    def test_one_plus_n_complete_solution(self):
        """testing the theorem with a complete proof."""
        code = "\n".join(
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

        c = Coq()
        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(context)
        self.assertIsNone(result.error)
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 0)

    def test_one_plus_n_complete_solution_with_bullets(self):
        """same as test_one_plus_n_complete_solution, but with bullets for subgoals"""
        code = "\n".join(
            [
                "Theorem t: forall n: nat, 1 + n > n.",
                "Proof.",
                "intros.",
                "induction n.",
                "  + simpl.",
                "    auto.",
                "  + simpl.",
                "    auto.",
                "Qed.",
            ]
        )

        c = Coq()
        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(context)
        self.assertIsNone(result.error)
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 0)

    def test_one_plus_n_incomplete_solution(self):
        """testing the theorem with an incomplete proof that has no errors"""
        code = "\n".join(
            ["Theorem t: forall n: nat, 1 + n > n.", "Proof.", "intros.", "Admitted."]
        )

        c = Coq()
        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(context)
        self.assertIsNone(result.error)
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 1)
        self.assertEqual(len(context.fg_goals), 1)
        self.assertEqual(len(context.bg_goals), 0)
        self.assertEqual(len(context.shelved_goals), 0)
        self.assertEqual(len(context.given_up_goals), 0)

        self.assertObligationEqual(
            ["n : nat"],
            "gt (Nat.add (S O) n) n",
            context.fg_goals[0],
        )

    def test_one_plus_n_incomplete_solution_with_error(self):
        """testing the theorem with an incomplete proof with errors"""
        code = "\n".join(
            ["Theorem t: forall n: nat, 1 + n > n.", "Proof.", "induction a.", "Qed."]
        )

        c = Coq()
        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(context)
        self.assertIsNotNone(result.error)
        self.assertEqual(
            result.error,
            (
                "The reference a was not found in the current environment.",
                "induction a.",
                3,
            ),
        )
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 1)
        self.assertEqual(len(context.fg_goals), 1)
        self.assertEqual(len(context.bg_goals), 0)
        self.assertEqual(len(context.shelved_goals), 0)
        self.assertEqual(len(context.given_up_goals), 0)

        self.assertObligationEqual(
            [],
            "forall n : nat, gt (Nat.add (S O) n) n",
            context.fg_goals[0],
        )

    def test_load_weak_up_to_Applications_Modular_F_mon(self):
        """testing being able to load weak_up_to/Applications.v/Modular/F_mon"""
        code = """Lemma F_mon: monotonic TX TX F.
Proof.
Admitted."""

        c = Coq(
            lemma_location=LemmaLocation(
                project_name="weak-up-to",
                file_name="Applications.v",
                section_names=["Modular"],
                lemma_name="F_mon",
            )
        )

        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(context)
        self.assertIsNone(result.error)
        if context is None:
            return

        self.assertEqual(len(context.all_goals), 1)
        self.assertEqual(len(context.fg_goals), 1)
        self.assertEqual(len(context.bg_goals), 0)
        self.assertEqual(len(context.shelved_goals), 0)
        self.assertEqual(len(context.given_up_goals), 0)

        self.assertObligationEqual(
            [
                "G : forall _ : relation2 X X, relation2 X X",
                "F : forall _ : relation2 X X, relation2 X X",
                "TX : reduction_t A X",
                "A,X : Type",
            ],
            "monotonic TX TX F",
            context.fg_goals[0],
        )

    def test_hammer_works_Comp_mon(self):
        code = """From Hammer Require Import Hammer.
From Hammer Require Import Tactics.
        
Lemma Comp_mon: monotonic TX TY (Comp G F).
Proof.
apply mkmon; intros.
- unfold increasing. intros. unfold Comp. apply HG. apply HF. assumption.
- apply HG.
-- hammer. 
-- hammer.
- apply HG.
-- hammer. 
-- """

        coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            ),
        )

        result = coq.run_code(code)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        context: c.contexts.ProofContext = result

        self.assertIsNotNone(context)

        self.assertEqual(len(context.all_goals), 1)
        self.assertEqual(len(context.fg_goals), 1)
        self.assertEqual(len(context.bg_goals), 0)
        self.assertEqual(len(context.shelved_goals), 0)
        self.assertEqual(len(context.given_up_goals), 0)

        self.assertObligationEqual(
            [
                "H0 : incl R S",
                "H : evolve TX TY R S",
                "R,S : relation2 X Y",
                "HG : monotonic TX TY G",
                "HF : monotonic TX TY F",
                "F,G : function X Y",
                "TY : reduction_t A Y",
                "TX : reduction_t A X",
                "X,Y : Type",
                "A : Type",
            ],
            "incl (F R) (F S)",
            context.fg_goals[0],
        )

        code += "hammer."

        coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            ),
        )

        result = coq.run_code(code)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        context = result

        self.assertEqual(len(context.all_goals), 0)

    def assertObligationEqual(
        self, hypotheses: list[str], goal: str, obligation: c.contexts.Obligation
    ):
        logging.info("obligation.hypotheses: " + str(obligation.hypotheses))
        logging.info("obligation.goal: " + str(obligation.goal))
        self.assertSequenceEqual(obligation.hypotheses, hypotheses)
        self.assertEqual(obligation.goal, goal)


class TestCheck(unittest.TestCase):
    """Test check vernacular after working code"""

    coq: Coq

    def setUp(self) -> None:
        super().setUp()

        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "intros.",
                "Admitted.",
            ]
        )

        self.coq = Coq()
        _ = self.coq.run_code(code)

    def test_check_n(self):
        """check the type of the variable n"""
        self.assertEqual(self.coq.check("n"), "\n".join(["n", "     : nat"]))

    def test_check_plus_O_n(self):
        """check the type of the plus_O_n theorem"""
        self.assertEqual(
            self.coq.check("plus_O_n"),
            "\n".join(["plus_O_n", "     : forall n : nat, eq (Nat.add O n) n"]),
        )

    def test_check_plus(self):
        """check the type of the plus alias for the add function"""
        self.assertEqual(
            self.coq.check("plus"),
            "\n".join(["Nat.add", "     : forall (_ : nat) (_ : nat), nat"]),
        )

    def test_check_add(self):
        """check the type of the add function"""
        self.assertEqual(
            self.coq.check("Nat.add"),
            "\n".join(["Nat.add", "     : forall (_ : nat) (_ : nat), nat"]),
        )

    def test_check_nat(self):
        """check the type of the nat inductive definition"""
        self.assertEqual(
            self.coq.check("nat"),
            "\n".join(["nat", "     : Set"]),
        )


class TestPrint(unittest.TestCase):
    """Test print vernacular after working code"""

    coq: Coq

    def setUp(self) -> None:
        super().setUp()

        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "intros.",
                "Admitted.",
            ]
        )

        self.coq = Coq()
        _ = self.coq.run_code(code)

    def test_print_n(self):
        """print the type of n"""
        self.assertIsNone(self.coq.print("n"))

    def test_print_plus_O_n(self):
        """print the type of plus_O_n"""
        self.assertIsNone(self.coq.print("plus_O_n"))

    def test_print_plus(self):
        """print the type of plus alias for the add function"""
        self.assertEqual(self.coq.print("plus"), "Notation plus := Nat.add")

    def test_print_add(self):
        """print the type of add function"""
        self.assertEqual(
            self.coq.print("Nat.add"),
            "\n".join(
                [
                    "Nat.add = ",
                    "fix add (n m : nat) {struct n} : nat :=",
                    "  match n with",
                    "  | O => m",
                    "  | S p => S (add p m)",
                    "  end",
                    "     : forall (_ : nat) (_ : nat), nat",
                    "",
                    "Arguments Nat.add (_ _)%nat_scope",
                ]
            ),
        )

    def test_print_nat(self):
        """print the type of nat"""
        self.assertEqual(
            self.coq.print("nat"),
            "\n".join(
                [
                    "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
                    "",
                    "Arguments S _%nat_scope",
                ]
            ),
        )


class TestCheckAfterError(unittest.TestCase):
    """Test print vernacular after code with an error"""

    coq: Coq

    def setUp(self) -> None:
        super().setUp()

        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "intros.",
                "intros a.",
                "Admitted.",
            ]
        )

        self.coq = Coq()
        _ = self.coq.run_code(code)

    def test_check_n_after_error(self):
        """check the type of the variable n"""
        self.assertEqual(self.coq.check("n"), "\n".join(["n", "     : nat"]))

    def test_check_plus_O_n_after_error(self):
        """check the type of the plus_O_n theorem"""
        self.assertEqual(
            self.coq.check("plus_O_n"),
            "\n".join(["plus_O_n", "     : forall n : nat, eq (Nat.add O n) n"]),
        )

    def test_check_plus_after_error(self):
        """check the type of the plus alias for the add function"""
        self.assertEqual(
            self.coq.check("plus"),
            "\n".join(["Nat.add", "     : forall (_ : nat) (_ : nat), nat"]),
        )

    def test_check_add_after_error(self):
        """check the type of the add function"""
        self.assertEqual(
            self.coq.check("Nat.add"),
            "\n".join(["Nat.add", "     : forall (_ : nat) (_ : nat), nat"]),
        )

    def test_check_nat_after_error(self):
        """check the type of the nat inductive definition"""
        self.assertEqual(
            self.coq.check("nat"),
            "\n".join(["nat", "     : Set"]),
        )


class TestPrintAfterError(unittest.TestCase):
    """Test print vernacular after working code"""

    coq: Coq

    def setUp(self) -> None:
        super().setUp()

        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "intros.",
                "Admitted.",
            ]
        )

        self.coq = Coq()
        _ = self.coq.run_code(code)

    def test_print_n_after_error(self):
        """print the type of n"""
        self.assertIsNone(self.coq.print("n"))

    def test_print_plus_O_n_after_error(self):
        """print the type of plus_O_n"""
        self.assertIsNone(self.coq.print("plus_O_n"))

    def test_print_plus_after_error(self):
        """print the type of plus alias for the add function"""
        self.assertEqual(self.coq.print("plus"), "Notation plus := Nat.add")

    def test_print_add_after_error(self):
        """print the type of add function"""
        self.assertEqual(
            self.coq.print("Nat.add"),
            "\n".join(
                [
                    "Nat.add = ",
                    "fix add (n m : nat) {struct n} : nat :=",
                    "  match n with",
                    "  | O => m",
                    "  | S p => S (add p m)",
                    "  end",
                    "     : forall (_ : nat) (_ : nat), nat",
                    "",
                    "Arguments Nat.add (_ _)%nat_scope",
                ]
            ),
        )

    def test_print_nat_after_error(self):
        """print the type of nat"""
        self.assertEqual(
            self.coq.print("nat"),
            "\n".join(
                [
                    "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
                    "",
                    "Arguments S _%nat_scope",
                ]
            ),
        )


class TestSearch(unittest.TestCase):
    """Test search vernacular after working code"""

    coq: Coq

    def setUp(self) -> None:
        super().setUp()

        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "intros.",
                "Admitted.",
            ]
        )

        self.coq = Coq()
        _ = self.coq.run_code(code)

    def test_search_O(self):
        """search for the string O"""
        search_result = self.coq.search("O")
        search_result.sort()
        self.assertEqual(
            search_result,
            [
                "CompOpp_iff:\n  forall c c' : comparison, iff (eq (CompOpp c) c') (eq c (CompOpp c'))",
                "CompOpp_inj:\n  forall (c c' : comparison) (_ : eq (CompOpp c) (CompOpp c')), eq c c'",
                "CompOpp_involutive: forall c : comparison, eq (CompOpp (CompOpp c)) c",
                "O_S: forall n : nat, not (eq O (S n))",
                "dependent_choice:\n  forall [X : Set] [R : forall (_ : X) (_ : X), Prop]\n    (_ : forall x : X, sig (fun y : X => R x y)) (x0 : X),\n  sig\n    (fun f : forall _ : nat, X =>\n     and (eq (f O) x0) (forall n : nat, R (f n) (f (S n))))",
                "le_0_n: forall n : nat, le O n",
                "mult_n_O: forall n : nat, eq O (Nat.mul n O)",
                "nat_case:\n  forall (n : nat) (P : forall _ : nat, Prop) (_ : P O)\n    (_ : forall m : nat, P (S m)), P n",
                "nat_double_ind:\n  forall (R : forall (_ : nat) (_ : nat), Prop) (_ : forall n : nat, R O n)\n    (_ : forall n : nat, R (S n) O)\n    (_ : forall (n m : nat) (_ : R n m), R (S n) (S m)) \n    (n m : nat), R n m",
                "plus_O_n: forall n : nat, eq (Nat.add O n) n",
                "plus_n_O: forall n : nat, eq n (Nat.add n O)",
            ],
        )

    def test_search_add(self):
        """search for the string add"""
        search_result = self.coq.search("add")
        self.assertEqual(
            search_result,
            [],
        )

    def test_search_does_not_exist(self):
        """search for a string that does not exist"""
        search_result = self.coq.search("does_not_exist")
        self.assertEqual(
            search_result,
            [],
        )

    def test_search_Nat_add(self):
        """search for the string Nat.add"""
        search_result = self.coq.search("Nat.add")
        search_result.sort()
        self.assertEqual(
            search_result,
            [
                "mult_n_Sm: forall n m : nat, eq (Nat.add (Nat.mul n m) n) (Nat.mul n (S m))",
                "nat_rect_plus:\n  forall (n m : nat) {A : Type} (f : forall _ : A, A) (x : A),\n  eq (nat_rect (fun _ : nat => A) x (fun _ : nat => f) (Nat.add n m))\n    (nat_rect (fun _ : nat => A)\n       (nat_rect (fun _ : nat => A) x (fun _ : nat => f) m)\n       (fun _ : nat => f) n)",
                "plus_O_n: forall n : nat, eq (Nat.add O n) n",
                "plus_Sn_m: forall n m : nat, eq (Nat.add (S n) m) (S (Nat.add n m))",
                "plus_n_O: forall n : nat, eq n (Nat.add n O)",
                "plus_n_Sm: forall n m : nat, eq (S (Nat.add n m)) (Nat.add n (S m))",
            ],
        )


class TestSearchAfterError(unittest.TestCase):
    """Test search vernacular after erroring code"""

    coq: Coq

    def setUp(self) -> None:
        super().setUp()

        code = "\n".join(
            [
                ONE_PLUS_N_DEFINITION,
                "Proof.",
                "intros.",
                "Admitted.",
            ]
        )

        self.coq = Coq()
        _ = self.coq.run_code(code)

    def test_search_O_after_error(self):
        """search for the string O"""
        search_result = self.coq.search("O")
        search_result.sort()
        self.assertEqual(
            search_result,
            [
                "CompOpp_iff:\n  forall c c' : comparison, iff (eq (CompOpp c) c') (eq c (CompOpp c'))",
                "CompOpp_inj:\n  forall (c c' : comparison) (_ : eq (CompOpp c) (CompOpp c')), eq c c'",
                "CompOpp_involutive: forall c : comparison, eq (CompOpp (CompOpp c)) c",
                "O_S: forall n : nat, not (eq O (S n))",
                "dependent_choice:\n  forall [X : Set] [R : forall (_ : X) (_ : X), Prop]\n    (_ : forall x : X, sig (fun y : X => R x y)) (x0 : X),\n  sig\n    (fun f : forall _ : nat, X =>\n     and (eq (f O) x0) (forall n : nat, R (f n) (f (S n))))",
                "le_0_n: forall n : nat, le O n",
                "mult_n_O: forall n : nat, eq O (Nat.mul n O)",
                "nat_case:\n  forall (n : nat) (P : forall _ : nat, Prop) (_ : P O)\n    (_ : forall m : nat, P (S m)), P n",
                "nat_double_ind:\n  forall (R : forall (_ : nat) (_ : nat), Prop) (_ : forall n : nat, R O n)\n    (_ : forall n : nat, R (S n) O)\n    (_ : forall (n m : nat) (_ : R n m), R (S n) (S m)) \n    (n m : nat), R n m",
                "plus_O_n: forall n : nat, eq (Nat.add O n) n",
                "plus_n_O: forall n : nat, eq n (Nat.add n O)",
            ],
        )

    def test_search_add_after_error(self):
        """search for the string add"""
        search_result = self.coq.search("add")
        self.assertEqual(
            search_result,
            [],
        )

    def test_search_does_not_exist_after_error(self):
        """search for a string that does not exist"""
        search_result = self.coq.search("does_not_exist")
        self.assertEqual(
            search_result,
            [],
        )

    def test_search_Nat_add_after_error(self):
        """search for the string Nat.add"""
        search_result = self.coq.search("Nat.add")
        search_result.sort()
        self.assertEqual(
            search_result,
            [
                "mult_n_Sm: forall n m : nat, eq (Nat.add (Nat.mul n m) n) (Nat.mul n (S m))",
                "nat_rect_plus:\n  forall (n m : nat) {A : Type} (f : forall _ : A, A) (x : A),\n  eq (nat_rect (fun _ : nat => A) x (fun _ : nat => f) (Nat.add n m))\n    (nat_rect (fun _ : nat => A)\n       (nat_rect (fun _ : nat => A) x (fun _ : nat => f) m)\n       (fun _ : nat => f) n)",
                "plus_O_n: forall n : nat, eq (Nat.add O n) n",
                "plus_Sn_m: forall n m : nat, eq (Nat.add (S n) m) (S (Nat.add n m))",
                "plus_n_O: forall n : nat, eq n (Nat.add n O)",
                "plus_n_Sm: forall n m : nat, eq (S (Nat.add n m)) (Nat.add n (S m))",
            ],
        )


class TestReadCommands(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(read_commands("a. b."), [("a. ", 1), ("b.", 1)])

    def test_newline(self):
        self.assertEqual(read_commands("a.\nb."), [("a.\n", 1), ("b.", 2)])

    def test_multiple_newlines(self):
        self.assertEqual(read_commands("a.\n\nb."), [("a.\n", 1), ("\nb.", 2)])

    def test_one_plus_n_with_focused_goal(self):
        self.assertEqual(
            read_commands(
                """Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
intros. induction n. -
Qed."""
            ),
            [
                ("Example one_plus_n: forall n: nat, 1 + n > n.\n", 1),
                ("Proof.\n", 2),
                ("intros. ", 3),
                ("induction n. ", 3),
                ("-\n", 3),
                ("Qed.", 4),
            ],
        )


class TestRegression(unittest.TestCase):
    def test_including_import(self):
        """code that includes an import should still execute correctly"""
        code = """Require Import Nat.

Lemma double_plus:  forall n, double n = n + n .
Proof.
  intro n.
Admitted."""

        c = Coq(lemma_location=LemmaLocation("basic", "BinNat.v", "double_plus", []))
        result = c.run_code(code)
        context = result.context

        self.assertIsNotNone(result.context)
        self.assertIsNone(result.error)

    def assertObligationEqual(
        self, hypotheses: list[str], goal: str, obligation: c.Obligation
    ):
        logging.info("obligation.hypotheses: " + str(obligation.hypotheses))
        logging.info("obligation.goal: " + str(obligation.goal))
        self.assertSequenceEqual(obligation.hypotheses, hypotheses)
        self.assertEqual(obligation.goal, goal)

    def test_working_proof_with_qed(self):
        code = """Lemma double_plus:  forall n, double n = n + n .
Proof.
  induction n.
  - (* base case: n = 0 *)
    reflexivity.
  - (* inductive case: n = S n' *)
    simpl.
    rewrite Nat.add_succ_r.
    rewrite IHn.
    reflexivity.
Qed."""

        coq = Coq(lemma_location=LemmaLocation("basic", "BinNat.v", "double_plus", []))
        result = coq.run_code(code)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

    def test_search_max_recursion_depth(self):
        """this search should not trigger max recursion depth"""
        code = """Lemma nat_to_bin_double:  forall n:nat, nat_to_bin (double n) = double_bin (nat_to_bin n).
Proof.
  intro n.
  induction n.
  - simpl. reflexivity.
  - simpl. 
Admitted."""
        coq = Coq(
            lemma_location=LemmaLocation("basic", "BinNat.v", "nat_to_bin_double", [])
        )
        coq.run_code(code)

        search_result = coq.search("eq")
        search_result.sort()
        self.assertEqual(
            search_result,
            [],
        )

    def test_definitions_index_out_of_bounds(self):
        """these definiotions calls should not trigger index out of bounds"""

        code = """Lemma fib_correct: 
   forall n, fib_tail n = fib n.
Proof.
  induction n as [|n IH].
  - simpl. reflexivity.
  - simpl. rewrite IH. rewrite fib_tail'_correct.
    + simpl. reflexivity.
    + reflexivity.
    + reflexivity.
Qed."""
        coq = Coq(
            lemma_location=LemmaLocation(
                "basic", "FibTailEquivalent.v", "fib_correct", []
            )
        )
        coq.run_code(code)

        try:
            coq.check("strongind")
        except Exception as e:
            self.fail("check failed with exception: " + str(e))

        try:
            coq.print("strongind")
        except Exception as e:
            self.fail("print failed with exception: " + str(e))

    def test_running_code_max_recursion(self):
        """this code should not trigger max recursion depth"""
        code = """Lemma bin_to_nat_preserves_incr:  forall b : bin,
  bin_to_nat (incr b) = 1 + bin_to_nat b.
Proof.
  induction b as [| b | b IHB].
  - simpl. reflexivity.
  - reflexivity. 
  - simpl. rewrite IHB.
      rewrite <- plus_n_O.
      rewrite <- plus_n_O.
      reflexivity.
Qed."""

        coq = Coq(
            lemma_location=LemmaLocation(
                "basic", "BinNat.v", "bin_to_nat_preserves_incr", []
            )
        )

        try:
            coq.run_code(code)
        except Exception as e:
            self.fail("run_code failed with exception: " + str(e))

    def test_definitions_for_theorem_doesnt_error(self):
        """this code should not cause an error"""
        code = """Lemma bin_nat_bin:  forall b, nat_to_bin (bin_to_nat b) = normalize b.
Proof.
  induction b.
  - simpl. reflexivity.
  - simpl. rewrite IHb. reflexivity.
  - simpl. rewrite IHb. reflexivity.
Admitted."""
        coq = Coq(lemma_location=LemmaLocation("basic", "BinNat.v", "bin_nat_bin", []))

        coq.run_code(code)

        try:
            coq.check("Theorem")
        except Exception as e:
            self.fail("check failed with exception: " + str(e))

        try:
            coq.print("Theorem")
        except Exception as e:
            self.fail("print failed with exception: " + str(e))


class TestNormalizeWhitespace(unittest.TestCase):
    def test_n_plus_one(self):
        self.assertEqual(
            normalize_whitespace(
                """forall n,  
    n + 1 >   n"""
            ),
            "forall n, n + 1 > n",
        )

    def test_lemma(self):
        self.assertEqual(
            normalize_whitespace(
                """Lemma n_plus_one: forall n,
    n + 1 >   n."""
            ),
            "Lemma n_plus_one: forall n, n + 1 > n.",
        )


class TestCodeLemmas(unittest.TestCase):
    def test_two_lemmas(self):
        code = """Lemma n_plus_one: forall n,
    n + 1 >   n.
Proof.
    lia.
Qed.
    
Lemma n_plus_two: forall n,
    n + 2 >   n.
Proof.
    lia.
Qed."""
        self.assertEqual(
            code_lemmas(code),
            [
                "n_plus_one : forall n,\n    n + 1 >   n.\n",
                "n_plus_two : forall n,\n    n + 2 >   n.\n",
            ],
        )


class TestKillNonTacticCommands(unittest.TestCase):
    def test_kill_lemma(self):
        code = """Lemma one_plus_n_gt_n: forall n,
    1+n > n.
Proof.
intros.
induction n.
- auto.
- simpl. apply gt_n_S. assumption.
Qed."""
        formatted_code = kill_non_tactic_commands(code)
        self.assertEqual(
            formatted_code,
            """intros.
induction n.
- auto.
- simpl. apply gt_n_S. assumption.""",
        )

    def test_kill_non_tactic_commands_preserves_spaces(self):
        code = """intros.
induction n.
- auto.
- simpl. apply gt_n_S. assumption."""
        formatted_code = kill_non_tactic_commands(code)
        self.assertEqual(formatted_code, code)

    def test_kill_non_tactic_commands_preserves_spaces_2(self):
        code = """intros.
induction n.
- auto.
- apply gt_trans with (m:=S n).
  + simpl. apply gt_n_Sn.
  + simpl. apply gt_S. assumption."""
        formatted_code = kill_non_tactic_commands(code)
        self.assertEqual(formatted_code, code)


class TestDefinition(unittest.TestCase):
    def test_parse_hypotheses(self):
        self.maxDiff = None
        self.assertEqual(
            Definition.parse_hypotheses(
                [
                    "A: Type",
                    "X, Y: Type",
                    "TX: reduction_t A X",
                    "TY: reduction_t A Y",
                    "F, G: function X Y",
                    "HF: monotonic TX TY F",
                    "HG: monotonic TX TY G",
                    "R, S: relation2 X Y",
                    "H1: evolve TX TY R S",
                    "H2: incl R S",
                    "a: A",
                ]
            ),
            [
                Definition("A", "Type"),
                Definition("X, Y", "Type"),
                Definition("TX", "reduction_t A X"),
                Definition("TY", "reduction_t A Y"),
                Definition("F, G", "function X Y"),
                Definition("HF", "monotonic TX TY F"),
                Definition("HG", "monotonic TX TY G"),
                Definition("R, S", "relation2 X Y"),
                Definition("H1", "evolve TX TY R S"),
                Definition("H2", "incl R S"),
                Definition("a", "A"),
            ],
        )

    def test_parse_check_and_print_results(self):
        self.assertEqual(
            Definition.parse("A: Type"),
            Definition("A", "Type"),
        )

        self.assertEqual(
            Definition.parse("*** [TY : reduction_t A Y]"),
            Definition("TY", "reduction_t A Y"),
        )

        self.assertEqual(
            Definition.parse(
                """TY
     : reduction_t A Y"""
            ),
            Definition("TY", "reduction_t A Y"),
        )

        self.assertIsNone(
            Definition.parse(
                """Comp = 
fun (X Y X' Y' X'' Y'' : Type) (G : function2 X' Y' X'' Y'')
  (F : function2 X Y X' Y') (R : relation2 X Y) => 
G (F R)
     : forall (X Y X' Y' X'' Y'' : Type) (_ : function2 X' Y' X'' Y'')
         (_ : function2 X Y X' Y') (_ : relation2 X Y), 
       relation2 X'' Y''"""
            )
        )

        self.assertIsNone(
            Definition.parse(
                """Record monotonic (A X Y : Type) (TX : reduction_t A X) 
(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon
  { mon_m : increasing F;
    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)
              (_ : incl R S), evolve_t TX TY (F R) (F S);
    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)
              (_ : incl R S), evolve_a TX TY (F R) (F S) }"""
            )
        )

    def test_match(self):
        self.assertTrue(
            Definition.matches(
                cast(Definition, Definition.parse("TY: reduction_t A Y")),
                cast(Definition, Definition.parse("*** [TY : reduction_t A Y]")),
            )
        )

        self.assertTrue(
            Definition.matches(
                cast(Definition, Definition.parse("*** [G : function X Y]")),
                cast(Definition, Definition.parse("F, G: function X Y")),
            )
        )

        self.assertTrue(
            Definition.matches(
                cast(Definition, Definition.parse("*** [F : function X Y]")),
                cast(Definition, Definition.parse("F, G: function X Y")),
            )
        )

        self.assertTrue(
            Definition.matches(
                cast(Definition, Definition.parse("F, G: function X Y")),
                cast(Definition, Definition.parse("*** [G : function X Y]")),
            )
        )

        self.assertTrue(
            Definition.matches(
                cast(Definition, Definition.parse("F, G: function X Y")),
                cast(Definition, Definition.parse("*** [F : function X Y]")),
            )
        )

        self.assertFalse(
            Definition.matches(
                cast(Definition, Definition.parse("F, G: function X Y")),
                cast(Definition, Definition.parse("*** [X : function X Y]")),
            )
        )

        self.assertFalse(
            Definition.matches(
                cast(Definition, Definition.parse("F, G: function X Y")),
                cast(Definition, Definition.parse("*** [TY : reduction_t A Y]")),
            )
        )


class TestParseIdentifiers(unittest.TestCase):
    def test_parse_identifiers_in_definition(self):
        self.assertEqual(
            parse_identifiers_in_definition(
                """Comp = 
fun (X Y X' Y' X'' Y'' : Type) (G : function2 X' Y' X'' Y'')
  (F : function2 X Y X' Y') (R : relation2 X Y) => 
G (F R)
     : forall (X Y X' Y' X'' Y'' : Type) (_ : function2 X' Y' X'' Y'')
         (_ : function2 X Y X' Y') (_ : relation2 X Y), 
       relation2 X'' Y''
  
Arguments X, Y, X', Y', X'', Y'' are implicit
Argument scopes are [type_scope type_scope type_scope type_scope type_scope  type_scope _ _ _]""",
            ),
            set(
                [
                    "Comp",
                    "X",
                    "Y",
                    "X'",
                    "Y'",
                    "X''",
                    "Y''",
                    "F",
                    "G",
                    "R",
                    "function2",
                    "relation2",
                ]
            ),
        )

        self.assertEqual(
            parse_identifiers_in_definition(
                """evolve_1 = 
fun (A X Y : Type) (TX : reduction_t A X) (TY : reduction_t A Y) 
  (l : Lbl A) (R S : relation2 X Y) => diagram (TX l) R (Weak TY l) S
	 : forall A X Y : Type,
       reduction_t A X ->
       reduction_t A Y -> Lbl A -> relation2 X Y -> relation2 X Y -> Prop

Arguments evolve_1 [A X Y]%type_scope""",
            ),
            set(
                [
                    "evolve_1",
                    "A",
                    "X",
                    "Y",
                    "TX",
                    "TY",
                    "l",
                    "R",
                    "S",
                    "Lbl",
                    "Weak",
                    "diagram",
                    "relation2",
                    "reduction_t",
                ]
            ),
        )

        self.assertEqual(
            parse_identifiers_in_definition(
                """evolve_a
	 : forall A X Y : Type,
       reduction_t A X ->
       reduction_t A Y -> relation2 X Y -> relation2 X Y -> Prop"""
            ),
            set(
                [
                    "evolve_a",
                    "A",
                    "X",
                    "Y",
                    "reduction_t",
                    "relation2",
                ]
            ),
        )


class TestRegex(unittest.TestCase):
    def test_match_inductive_regex(self):
        self.assertIsNotNone(
            re.match(
                MATCH_INDUCTIVE_REGEX,
                "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
            )
        )

    def test_inductive_constructor_regex(self):
        self.assertEqual(
            re.findall(
                INDUCTIVE_CONSTRUCTOR_REGEX,
                "Inductive nat : Set :=  O : nat | S : forall _ : nat, nat",
            ),
            ["O", "S"],
        )

    def test_match_record_regex(self):
        self.assertIsNotNone(
            re.match(
                MATCH_RECORD_REGEX,
                """Record monotonic (A X Y : Type) (TX : reduction_t A X) 
(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon
  { mon_m : increasing F;
    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)
              (_ : incl R S), evolve_t TX TY (F R) (F S);
    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)
              (_ : incl R S), evolve_a TX TY (F R) (F S) }""",
            )
        )

    def test_record_item_regex(self):
        self.assertEqual(
            re.findall(
                RECORD_ITEM_REGEX,
                """Record monotonic (A X Y : Type) (TX : reduction_t A X) 
(TY : reduction_t A Y) (F : function X Y) : Prop := mkmon
  { mon_m : increasing F;
    mon_t : forall (R S : relation2 X Y) (_ : evolve_t TX TY R S)
              (_ : incl R S), evolve_t TX TY (F R) (F S);
    mon_a : forall (R S : relation2 X Y) (_ : evolve TX TY R S)
              (_ : incl R S), evolve_a TX TY (F R) (F S) }""",
            ),
            ["mon_m", "mon_t", "mon_a"],
        )

    def test_ignore_line_regex(self):
        self.assertIsNotNone(
            re.match(
                IGNORE_LINE_REGEX,
                "             function_scope function_scope] ",
            )
        )


class TestGetLemmasForIdentifiers_Mremove_cardinal_less(unittest.TestCase):

    c: Coq
    example_name = "coq-wigderson-graph.v-Mremove_cardinal_less"

    @classmethod
    def setUpClass(cls):
        example = next(
            example
            for example in COQ_WIGDERSON_DEV_SAMPLED_DATASET
            if example.name == cls.example_name
        )
        cls.c = Coq(example.location)

    def test_all_premises(self):
        perfect_premises = COQ_WIGDERSON_DEV_PERFECT_PREMISE_NAMES[self.example_name]
        lemmas = self.c.get_lemmas_for_identifiers(perfect_premises)

        self.assertEqual(len(lemmas), len(perfect_premises))
        self.assertFalse(None in lemmas)

    def test_PositiveMap_Empty(self):
        premise = ["PositiveMap.Empty"]
        lemmas = self.c.get_lemmas_for_identifiers(premise)

        self.assertEqual(len(lemmas), 1)
        self.assertNotEqual(lemmas[0], None)
        self.assertEqual(
            lemmas[0],
            """PositiveMap.Empty
     : forall (A : Type) (_ : PositiveMap.t A), Prop""",
        )

    def test_neq_0_lt(self):
        premise = ["neq_0_lt"]
        lemmas = self.c.get_lemmas_for_identifiers(premise)

        self.assertEqual(len(lemmas), 1)
        self.assertNotEqual(lemmas[0], None)
        self.assertEqual(
            lemmas[0],
            """neq_0_lt
     : forall (n : nat) (_ : not (eq O n)), lt O n""",
        )


class TestIsRedundant(unittest.TestCase):

    def test_multiple_copies_of_same_hypothesis(self):
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
                "\n"
            ),
            goal="S.In k (S.add x s')",
        )

        o_prime = c.contexts.Obligation(
            hypotheses="""e,e0 : Logic.eq k x
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
                "\n"
            ),
            goal="S.In k (S.add x s')",
        )

        self.assertTrue(is_redundant(o_prime, o))


if __name__ == "__main__":
    unittest.main(verbosity=2)
