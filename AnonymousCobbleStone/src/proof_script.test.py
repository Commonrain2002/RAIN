import unittest
import typing as t
import coq_serapy as c

from src.proof_script import (
    ProofScript,
    Skip,
    Tactic,
    process_braces,
    process_bullets,
    CoqPartialSuccess,
)
from src.coq_serapy_util import Coq, CoqError, LemmaLocation
from src.utils import run_generator_and_save_yields, get_logger

LOGGER = get_logger(__name__)

# region PROOF SCRIPT


class Test_ProofScript_Parse(unittest.TestCase):
    """
    This class is an end-to-end test of process_tactics, process_braces, and process_bullets.
    """

    def test_intros(self):
        script = ProofScript.parse("intros.")
        self.assertEqual(
            script.contents,
            [Tactic("intros.")],
        )
        self.assertEqual(
            [tactic.start_line_number for tactic in script.walk()],
            [1],
        )
        self.assertEqual(
            [tactic.end_line_number for tactic in script.walk()],
            [1],
        )

    def test_intros_split(self):
        script = ProofScript.parse(
            """intros.
(* and now we split *)
split."""
        )

        self.assertEqual(
            script.contents,
            [
                Tactic("intros."),
                Tactic(
                    "split.",
                ),
            ],
        )
        self.assertEqual(
            [tactic.start_line_number for tactic in script.walk()],
            [1, 2],
        )
        self.assertEqual(
            [tactic.end_line_number for tactic in script.walk()],
            [2, 3],
        )

    def test_intros_split_with_bullets(self):
        script = ProofScript.parse(
            """intros.
split.
- assumption.
- assumption."""
        )

        assert_script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
            ]
        )
        self.assertEqual(
            script.pretty_print(),
            assert_script.pretty_print(),
        )
        self.assertEqual(
            [tactic.start_line_number for tactic in script.walk()],
            [1, 2, 1, 3, 1, 4],
        )
        self.assertEqual(
            [tactic.end_line_number for tactic in script.walk()],
            [2, 3, 1, 4, 1, 4],
        )


class Test_ProofScript_FromTactics(unittest.TestCase):
    def test_hammer_trace(self):
        tactics = [
            Tactic(t)
            for t in [
                "split; unfold not; intros.",
                "-",
                "contradict H.",
                "hammer.",
                "-",
                "contradict H.",
                "hammer.",
            ]
        ]

        script = ProofScript.from_tactics(tactics)
        self.assertEqual(
            [tactic.text for tactic in script.walk()],
            [
                "split; unfold not; intros.",
                "-",
                "contradict H.",
                "hammer.",
                "-",
                "contradict H.",
                "hammer.",
            ],
        )


class Test_ProofScript_Eq(unittest.TestCase):
    def test_eq_no_bullets(self):
        script1 = ProofScript(
            [Tactic("intros."), Tactic("split.")],
        )

        script2 = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
            ],
        )

        self.assertEqual(script1, script2)

    def test_eq_with_bullets(self):
        script1 = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

        script2 = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

        self.assertEqual(script1, script2)

    def test_not_eq_with_bullets(self):
        script1 = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

        script2 = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("assumption."),
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

        self.assertNotEqual(script1, script2)

    def test_not_eq_no_bullets(self):
        script1 = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
            ],
        )

        script2 = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                Tactic("assumption."),
            ],
        )

        self.assertNotEqual(script1, script2)


class Test_ProofScript_PrettyPrint(unittest.TestCase):
    def test_intros(self):
        script = ProofScript(
            [
                Tactic("intros."),
            ],
        )

        self.assertEqual(script.pretty_print(), "intros.")

    def test_intros_split(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
            ],
        )

        self.assertEqual(script.pretty_print(), "intros. split.")

    def test_intros_split_with_bullets(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

        self.assertEqual(
            script.pretty_print(),
            """intros. split.
- assumption.
- assumption.""",
        )

    def test_multiple_levels_of_bullets(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("assumption."),
                        ProofScript(
                            [
                                Tactic(
                                    "assumption.",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )

        self.assertEqual(
            script.pretty_print(),
            """intros. split.
- assumption.
- assumption.
-- assumption.""",
        )


class Test_ProcessBraces(unittest.TestCase):
    def test_no_braces(self):
        tactics = [
            Tactic("intros."),
            Tactic("split."),
        ]

        processed = process_braces(tactics)
        self.assertEqual(processed.contents, tactics)

    def test_toplevel_brace(self):
        tactics = [
            Tactic("{"),
            Tactic("intros."),
            Tactic("split."),
            Tactic("}"),
        ]

        processed = process_braces(tactics)
        self.assertEqual(
            processed.contents,
            [
                ProofScript(
                    contents=[Tactic("intros."), Tactic("split.")],
                )
            ],
        )

    def test_toplevel_brace_2(self):
        tactics = [
            Tactic("{"),
            Tactic("{"),
            Tactic("intros."),
            Tactic("split."),
            Tactic("}"),
            Tactic("}"),
        ]

        processed = process_braces(tactics)
        self.assertEqual(
            processed.contents,
            [
                ProofScript(
                    contents=[
                        ProofScript(
                            contents=[
                                Tactic("intros."),
                                Tactic(
                                    "split.",
                                ),
                            ],
                        )
                    ],
                )
            ],
        )

    def test_intros_split(self):
        tactics = [
            Tactic("intros."),
            Tactic("split."),
            Tactic("{"),
            Tactic("assumption."),
            Tactic("}"),
            Tactic("{"),
            Tactic("assumption."),
            Tactic("}"),
        ]

        processed = process_braces(tactics)
        self.assertEqual(
            processed.contents,
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    contents=[
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    contents=[
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

    def test_intros_split_with_bullets(self):
        tactics = [
            Tactic("intros."),
            Tactic("split."),
            Tactic("-"),
            Tactic("assumption."),
            Tactic("-"),
            Tactic("assumption."),
        ]

        processed = process_braces(tactics)
        self.assertEqual(
            processed.contents,
            [
                Tactic("intros."),
                Tactic("split."),
                Tactic("-"),
                Tactic("assumption."),
                Tactic("-"),
                Tactic("assumption."),
            ],
        )

    def test_intros_split_with_bullets_and_braces(self):
        tactics = [
            Tactic("intros."),
            Tactic("split."),
            Tactic("-"),
            Tactic("{"),
            Tactic("assumption."),
            Tactic("}"),
            Tactic("-"),
            Tactic("{"),
            Tactic("assumption."),
            Tactic("}"),
        ]

        processed = process_braces(tactics)
        self.assertEqual(
            processed.contents,
            [
                Tactic("intros."),
                Tactic("split."),
                Tactic("-"),
                ProofScript(
                    contents=[
                        Tactic("assumption."),
                    ],
                ),
                Tactic("-"),
                ProofScript(
                    contents=[
                        Tactic("assumption."),
                    ],
                ),
            ],
        )


class Test_ProcessBullets(unittest.TestCase):
    def test_no_bullets(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
            ],
        )

        processed = process_bullets(script)
        self.assertEqual(processed.contents, script.contents)

    def test_single_level(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                Tactic("-"),
                Tactic("assumption."),
                Tactic("-"),
                Tactic("assumption."),
            ],
        )

        processed = process_bullets(script)
        self.assertEqual(
            processed.contents,
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    contents=[
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    contents=[
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

    def test_two_level(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                Tactic("-"),
                Tactic("intros."),
                Tactic("+"),
                Tactic("assumption."),
                Tactic("+"),
                Tactic("assumption."),
                Tactic("-"),
                Tactic("intros."),
                Tactic("--"),
                Tactic("assumption."),
            ],
        )

        processed = process_bullets(script)
        self.assertEqual(
            processed.contents,
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    contents=[
                        Tactic("intros."),
                        ProofScript(
                            contents=[
                                Tactic(
                                    "assumption.",
                                ),
                            ],
                        ),
                        ProofScript(
                            contents=[
                                Tactic(
                                    "assumption.",
                                ),
                            ],
                        ),
                    ],
                ),
                ProofScript(
                    contents=[
                        Tactic("intros."),
                        ProofScript(
                            contents=[
                                Tactic(
                                    "assumption.",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )

    def test_braces(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                Tactic("-"),
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("intros."),
                        Tactic("-"),
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

        self.maxDiff = None
        processed = process_bullets(script)
        self.assertEqual(
            processed.contents,
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    contents=[
                        Tactic("intros."),
                        Tactic("split."),
                        ProofScript(
                            contents=[
                                Tactic("intros."),
                                ProofScript(
                                    contents=[
                                        Tactic(
                                            "assumption.",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )


class Test_ProofScript_Walk(unittest.TestCase):
    def test_intros(self):
        script = ProofScript(
            [
                Tactic("intros."),
            ],
        )

        self.assertEqual(
            [tactic.text for tactic in script.walk()],
            ["intros."],
        )

    def test_intros_split(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
            ],
        )

        self.assertEqual(
            [tactic.text for tactic in script.walk()],
            ["intros.", "split."],
        )

    def test_intros_split_with_bullets(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

        self.assertEqual(
            [tactic.text for tactic in script.walk()],
            ["intros.", "split.", "-", "assumption.", "-", "assumption."],
        )

    def test_script_with_bullets(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("simpl."),
                        Tactic("assumption."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("simpl."),
                        Tactic("assumption."),
                    ],
                ),
            ],
        )

        self.assertEqual(
            [tactic.text for tactic in script.walk()],
            [
                "intros.",
                "split.",
                "-",
                "simpl.",
                "assumption.",
                "-",
                "simpl.",
                "assumption.",
            ],
        )

    def test_skipping(self):
        script = ProofScript(
            [
                Tactic("intros."),
                Tactic("split."),
                ProofScript(
                    [
                        Tactic("simpl1."),
                        Tactic("assumption1."),
                    ],
                ),
                ProofScript(
                    [
                        Tactic("simpl2."),
                        Tactic("assumption2."),
                    ],
                ),
            ],
        )

        generator = script.walk()
        self.assertEqual(next(generator).text, "intros.")
        self.assertEqual(next(generator).text, "split.")
        self.assertEqual(next(generator).text, "-")
        # skip straight to the next bullet
        self.assertEqual(generator.send("skip").text, "-")
        self.assertEqual(next(generator).text, "simpl2.")
        # skipping the second bullet goes straight to the end of the script
        self.assertRaises(StopIteration, lambda: generator.send("skip"))


class Test_ProofScript_RunUntilEndOrError(unittest.TestCase):
    coq: Coq

    def setUp(self):
        self.coq = Coq()
        preamble = """Require Import FSets.

Module S <: FSetInterface.S := PositiveSet.

Example set_equal_subset: forall s1 s2, S.Equal s1 s2 -> S.Subset s1 s2 /\\ S.Subset s2 s1.
Proof.
""".splitlines()

        for command in preamble:
            if command.strip() != "":
                self.coq.run_preamble(command)

    def tearDown(self):
        self.coq.teardown()

    def test_success(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. rewrite <- H. assumption.
  - intros a Ha. rewrite H. assumption."""
        )

        result = script.run_until_end_or_error(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        self.assertEqual(result.all_goals, [])

    def test_error(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - rewrite <- H. assumption.
  - intros a Ha. rewrite H. assumption."""
        )

        result = script.run_until_end_or_error(self.coq)
        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.assertEqual(
            result.message,
            'Found no subterm matching "S.In ?e s2" in the current goal.',
        )
        self.assertEqual(result.token, "rewrite <- H.")
        self.assertEqual(result.line_number, 4)

        self.assertIsNotNone(result.context)
        if result.context is None:
            return

        self.assertEqual(
            [obligation.goal for obligation in result.context.all_goals],
            [
                "forall (a : S.elt) (_ : S.In a s1), S.In a s2",
                "forall (a : S.elt) (_ : S.In a s2), S.In a s1",
            ],
        )
        self.assertEqual(
            [obligation.hypotheses for obligation in result.context.all_goals],
            [
                ("H : forall a : S.elt, iff (S.In a s1) (S.In a s2)", "s1,s2 : S.t"),
                ("H : forall a : S.elt, iff (S.In a s1) (S.In a s2)", "s1,s2 : S.t"),
            ],
        )


class Test_ProofScript_RunAdmittingFailedSubgoals(unittest.TestCase):
    coq: Coq

    def setUp(self):
        self.coq = Coq()
        preamble = """Require Import FSets.
From Hammer Require Import Hammer.

Module S <: FSetInterface.S := PositiveSet.

Example set_equal_subset: forall s1 s2, S.Equal s1 s2 -> S.Subset s1 s2 /\\ S.Subset s2 s1.
Proof.
""".splitlines()

        for command in preamble:
            if command.strip() != "":
                self.coq.run_preamble(command)

    def tearDown(self):
        self.coq.teardown()

    def test_success(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. rewrite <- H. assumption.
  - intros a Ha. rewrite H. assumption."""
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                tactics_run.append(next(generator))
            except StopIteration as e:
                result = e.value
                break

        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "rewrite <- H.",
                "assumption.",
                "-",
                "intros a Ha.",
                "rewrite H.",
                "assumption.",
            ],
        )

        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        self.assertEqual(result.all_goals, [])

    def test_prefix_proof_successful(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
assert (HT: True).
{ auto. }
split.
- intros a Ha. rewrite <- H. assumption.
- intros a Ha. rewrite H. assumption."""
        )

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq)
        )

        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "assert (HT: True).",
                "{",
                "auto.",
                "}",
                "split.",
                "-",
                "intros a Ha.",
                "rewrite <- H.",
                "assumption.",
                "-",
                "intros a Ha.",
                "rewrite H.",
                "assumption.",
            ],
        )

        self.assertIsInstance(result, c.contexts.ProofContext)

    def test_prefix_proof_error(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
assert (HT: True).
{ apply gt_n_O. }
split.
- intros a Ha. rewrite <- H. assumption.
- intros a Ha. rewrite H. assumption."""
        )

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq)
        )

        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "assert (HT: True).",
                "{",
            ],
        )

        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.assertEqual(
            result.message,
            "The reference gt_n_O was not found in the current environment.",
        )
        self.assertEqual(result.token, "apply gt_n_O.")

    def test_prefix_proof_repair(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
assert (HT: True). { apply gt_n_O. }
split.
- intros a Ha. rewrite <- H. assumption.
- intros a Ha. rewrite H. assumption."""
        )

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq, try_hammer_on_error=True)
        )

        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "assert (HT: True).",
                "{",
                "hammer.",
                "}",
                "split.",
                "-",
                "intros a Ha.",
                "rewrite <- H.",
                "assumption.",
                "-",
                "intros a Ha.",
                "rewrite H.",
                "assumption.",
            ],
        )

        self.assertIsInstance(result, c.contexts.ProofContext)

    def test_prefix_proof_repair_in_bullet(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
split.
- intros a Ha. 
assert (HT: True).
{ apply gt_n_O. }
rewrite <- H. assumption.
- intros a Ha. rewrite H. assumption."""
        )

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq, try_hammer_on_error=True)
        )

        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "assert (HT: True).",
                "{",
                "hammer.",
                "}",
                "rewrite <- H.",
                "assumption.",
                "-",
                "intros a Ha.",
                "rewrite H.",
                "assumption.",
            ],
        )

        self.assertIsInstance(result, c.contexts.ProofContext)

    def test_error_before_decomposition(self):
        script = ProofScript.parse(
            """intros. assumption. split.
  - intros a Ha. rewrite <- H. assumption.
  - intros a Ha. rewrite H. assumption."""
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                result = next(generator)
                tactics_run.append(result)
            except StopIteration as e:
                result = e.value
                break

        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "intros.",
            ],
        )

        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.assertEqual(
            result.message,
            "No such assumption.",
        )
        self.assertEqual(result.token, "assumption.")
        self.assertEqual(result.line_number, 1)

    def test_error_in_subgoal(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. rewrite H. assumption.
  - intros a Ha. rewrite H. assumption."""
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                result = next(generator)
                tactics_run.append(result)
            except StopIteration as e:
                result = e.value
                break
        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "admit.",
                "-",
                "intros a Ha.",
                "rewrite H.",
                "assumption.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        self.assertEqual(
            [t.cast(Tactic, tactic).text for tactic in result.prefix.contents],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
            ],
        )
        self.assertEqual(
            len(result.subgoal_obligations),
            2,
        )
        self.assertEqual(
            [
                obligation.goal if obligation is not None else None
                for obligation in result.subgoal_obligations
            ],
            [
                "forall (a : S.elt) (_ : S.In a s1), S.In a s2",
                "forall (a : S.elt) (_ : S.In a s2), S.In a s1",
            ],
        )
        self.assertEqual(
            [script.pretty_print() for script in result.subgoal_scripts],
            [
                "intros a Ha. rewrite H. assumption.",
                "intros a Ha. rewrite H. assumption.",
            ],
        )
        self.assertEqual(
            [script.pretty_print() for script in result.subgoal_executed_scripts],
            [
                "intros a Ha. admit.",
                "intros a Ha. rewrite H. assumption.",
            ],
        )

        self.assertEqual(len(result.subgoal_results), 2)
        self.assertIsInstance(result.subgoal_results[0], CoqError)
        self.assertIsInstance(result.subgoal_results[1], c.contexts.ProofContext)

    def test_nested_decomposition(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. replace (S.In a s2) with (S.In a s1).
    + assumption.
    + rewrite <- H. reflexivity.  
  - intros a Ha. replace (S.In a s1) with (S.In a s2).
    + assumption.
    + rewrite H. reflexivity."""
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                result = next(generator)
                tactics_run.append(result)
            except StopIteration as e:
                result = e.value
                break

        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "replace (S.In a s2) with (S.In a s1).",
                "--",
                "assumption.",
                "--",
                "admit.",
                "-",
                "intros a Ha.",
                "replace (S.In a s1) with (S.In a s2).",
                "--",
                "assumption.",
                "--",
                "admit.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        self.assertEqual(
            [t.cast(Tactic, tactic).text for tactic in result.prefix.contents],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
            ],
        )

        self.assertEqual(len(result.subgoal_obligations), 2)

        first_subgoal_result = result.subgoal_results[0]
        self.assertIsInstance(first_subgoal_result, CoqPartialSuccess)
        if not isinstance(first_subgoal_result, CoqPartialSuccess):
            return

        self.assertEqual(
            [
                t.cast(Tactic, tactic).text
                for tactic in first_subgoal_result.prefix.contents
            ],
            [
                "intros a Ha.",
                "replace (S.In a s2) with (S.In a s1).",
            ],
        )
        self.assertEqual(len(first_subgoal_result.subgoal_obligations), 2)
        self.assertIsInstance(
            first_subgoal_result.subgoal_results[0], c.contexts.ProofContext
        )
        self.assertIsInstance(first_subgoal_result.subgoal_results[1], CoqError)

        second_subgoal_result = result.subgoal_results[1]
        self.assertIsInstance(second_subgoal_result, CoqPartialSuccess)
        if not isinstance(second_subgoal_result, CoqPartialSuccess):
            return

        self.assertEqual(
            [
                t.cast(Tactic, tactic).text
                for tactic in second_subgoal_result.prefix.contents
            ],
            [
                "intros a Ha.",
                "replace (S.In a s1) with (S.In a s2).",
            ],
        )
        self.assertEqual(len(second_subgoal_result.subgoal_obligations), 2)
        self.assertIsInstance(
            second_subgoal_result.subgoal_results[0], c.contexts.ProofContext
        )

    def test_decomposition_no_bullets_not_enough_subgoals(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
split. 
intros a Ha. rewrite <- H. rewrite Hy.
"""
        )

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq, try_hammer_on_error=True)
        )
        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "intros a Ha.",
                "rewrite <- H.",
                "hammer.",
            ],
        )

        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.assertEqual(
            result.message,
            " (in proof set_equal_subset): Attempt to save an incomplete proof",
        )

    def test_decomposition_not_enough_subgoals(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
- intros a Ha. rewrite <- H. assumption.
"""
        )

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq)
        )
        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "rewrite <- H.",
                "assumption.",
                "-",
                "admit.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        self.assertEqual(len(result.subgoal_obligations), 2)
        self.assertIsInstance(result.subgoal_results[0], c.contexts.ProofContext)
        self.assertIsInstance(result.subgoal_results[1], Skip)

    def test_nested_decomposition_not_enough_subgoals_in_middle(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. replace (S.In a s2) with (S.In a s1).
    + assumption.
  - intros a Ha. replace (S.In a s1) with (S.In a s2).
    + assumption.
    + rewrite H. reflexivity."""
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                result = next(generator)
                tactics_run.append(result)
            except StopIteration as e:
                result = e.value
                break
        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "replace (S.In a s2) with (S.In a s1).",
                "--",
                "assumption.",
                "--",
                "admit.",
                "-",
                "intros a Ha.",
                "replace (S.In a s1) with (S.In a s2).",
                "--",
                "assumption.",
                "--",
                "admit.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        self.assertEqual(
            [t.cast(Tactic, tactic).text for tactic in result.prefix.contents],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
            ],
        )
        self.assertEqual(len(result.subgoal_obligations), 2)

        first_subgoal_result = result.subgoal_results[0]
        self.assertIsInstance(first_subgoal_result, CoqPartialSuccess)
        if not isinstance(first_subgoal_result, CoqPartialSuccess):
            return
        self.assertEqual(len(first_subgoal_result.subgoal_obligations), 2)
        self.assertIsInstance(
            first_subgoal_result.subgoal_results[0], c.contexts.ProofContext
        )
        self.assertIsInstance(first_subgoal_result.subgoal_results[1], Skip)

        second_subgoal_result = result.subgoal_results[1]
        self.assertIsInstance(second_subgoal_result, CoqPartialSuccess)
        if not isinstance(second_subgoal_result, CoqPartialSuccess):
            return

        self.assertEqual(
            [
                t.cast(Tactic, tactic).text
                for tactic in second_subgoal_result.prefix.contents
            ],
            [
                "intros a Ha.",
                "replace (S.In a s1) with (S.In a s2).",
            ],
        )
        self.assertEqual(len(second_subgoal_result.subgoal_obligations), 2)
        self.assertIsInstance(
            second_subgoal_result.subgoal_results[0], c.contexts.ProofContext
        )
        self.assertIsInstance(second_subgoal_result.subgoal_results[1], CoqError)

    def test_nested_decomposition_too_many_subgoals_in_middle(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. replace (S.In a s2) with (S.In a s1).
    + assumption.
    + assumption.
    + assumption.
  - intros a Ha. replace (S.In a s1) with (S.In a s2).
    + assumption.
    + rewrite H. reflexivity."""
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                result = next(generator)
                tactics_run.append(result)
            except StopIteration as e:
                result = e.value
                break
        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "replace (S.In a s2) with (S.In a s1).",
                "--",
                "assumption.",
                "--",
                "admit.",
                "-",
                "intros a Ha.",
                "replace (S.In a s1) with (S.In a s2).",
                "--",
                "assumption.",
                "--",
                "admit.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

    def test_nested_decomposition_too_few_subgoals_at_end(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. replace (S.In a s2) with (S.In a s1).
    + assumption.
    + rewrite <- H. reflexivity.  
  - intros a Ha. replace (S.In a s1) with (S.In a s2).
    + assumption."""
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                result = next(generator)
                tactics_run.append(result)
            except StopIteration as e:
                result = e.value
                break
        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "replace (S.In a s2) with (S.In a s1).",
                "--",
                "assumption.",
                "--",
                "admit.",
                "-",
                "intros a Ha.",
                "replace (S.In a s1) with (S.In a s2).",
                "--",
                "assumption.",
                "--",
                "admit.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        self.assertEqual(len(result.subgoal_obligations), 2)

        current_result = result.subgoal_results[0]
        self.assertIsInstance(current_result, CoqPartialSuccess)
        if not isinstance(current_result, CoqPartialSuccess):
            return

        current_result = result.subgoal_results[1]
        self.assertIsInstance(current_result, CoqPartialSuccess)
        if not isinstance(current_result, CoqPartialSuccess):
            return

        self.assertEqual(len(current_result.subgoal_obligations), 2)
        self.assertIsInstance(
            current_result.subgoal_results[0], c.contexts.ProofContext
        )
        self.assertIsInstance(current_result.subgoal_results[1], Skip)

    def test_nested_decomposition_too_many_subgoals_at_end(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. replace (S.In a s2) with (S.In a s1).
    + assumption.
    + rewrite <- H. reflexivity.  
  - intros a Ha. replace (S.In a s1) with (S.In a s2).
    + assumption.
    + assumption.
    + assumption. """
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                result = next(generator)
                tactics_run.append(result)
            except StopIteration as e:
                result = e.value
                break
        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
                "-",
                "intros a Ha.",
                "replace (S.In a s2) with (S.In a s1).",
                "--",
                "assumption.",
                "--",
                "admit.",
                "-",
                "intros a Ha.",
                "replace (S.In a s1) with (S.In a s2).",
                "--",
                "assumption.",
                "--",
                "admit.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return


class Test_ProofScript_RunAdmittingFailedSubgoals_InlIn(unittest.TestCase):
    coq: Coq

    def setUp(self):
        self.coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coq-wigderson",
                file_name="subgraph.v",
                lemma_name="inl_in",
                coq_version="8.13",
            )
        )

        preamble = """Lemma inl_in i l : S.InL i l <-> In i l.
Proof.""".splitlines()

        for command in preamble:
            if command.strip() != "":
                self.coq.run_preamble(command)

    def tearDown(self):
        self.coq.teardown()

    def test_gpt_completion_1(self):
        script = ProofScript.parse(
            "split; intros H1. \n- apply InA_alt in H1. destruct H1 as [x [H2 H3]]. apply In_alt in H3. assumption. \n- apply InA_alt. exists i. split. reflexivity. assumption."
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                tactics_run.append(next(generator))
            except StopIteration as e:
                result = e.value
                break

        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "split; intros H1.",
                "-",
                "apply InA_alt in H1.",
                "destruct H1 as [x [H2 H3]].",
                "admit.",
                "-",
                "apply InA_alt.",
                "exists i.",
                "split.",
                "reflexivity.",
                "assumption.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        self.assertEqual(
            len(result.subgoal_obligations),
            2,
        )
        self.assertIsInstance(result.subgoal_results[0], CoqError)
        self.assertIsInstance(result.subgoal_results[1], c.contexts.ProofContext)

    def test_gpt_completion_2(self):
        script = ProofScript.parse(
            "split.\n- intros H. induction l as [|x xs IH].\n  + inversion H.\n  + inversion H; subst; simpl; auto.\n- intros H. induction l as [|x xs IH].\n  + simpl in H. contradiction.\n  + simpl in H. destruct H as [H|H].\n    * left. assumption.\n    * right. apply IH. assumption."
        )

        generator = script.run_admitting_failed_subgoals(self.coq)
        tactics_run = []
        while True:
            try:
                tactics_run.append(next(generator))
            except StopIteration as e:
                result = e.value
                break

        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "split.",
                "-",
                "intros H.",
                "induction l as [|x xs IH].",
                "--",
                "inversion H.",
                "--",
                "inversion H; subst; simpl; auto.",
                "-",
                "intros H.",
                "induction l as [|x xs IH].",
                "--",
                "simpl in H.",
                "contradiction.",
                "--",
                "simpl in H.",
                "destruct H as [H|H].",
                "---",
                "left.",
                "admit.",
                "---",
                "right.",
                "apply IH.",
                "assumption.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        self.assertEqual(
            len(result.subgoal_obligations),
            2,
        )

        current_result = result.subgoal_results[0]
        self.assertIsInstance(current_result, c.contexts.ProofContext)

        current_result = result.subgoal_results[1]
        self.assertIsInstance(current_result, CoqPartialSuccess)
        if not isinstance(current_result, CoqPartialSuccess):
            return

        self.assertEqual(
            len(current_result.subgoal_obligations),
            2,
        )

        current_result = t.cast(
            CoqPartialSuccess, result.subgoal_results[1]
        ).subgoal_results[0]
        self.assertIsInstance(current_result, c.contexts.ProofContext)
        if not isinstance(current_result, c.contexts.ProofContext):
            return

        current_result = t.cast(
            CoqPartialSuccess, result.subgoal_results[1]
        ).subgoal_results[1]
        self.assertIsInstance(current_result, CoqPartialSuccess)
        if not isinstance(current_result, CoqPartialSuccess):
            return

        self.assertEqual(
            len(current_result.subgoal_obligations),
            2,
        )

        current_result = t.cast(
            CoqPartialSuccess,
            t.cast(CoqPartialSuccess, result.subgoal_results[1]).subgoal_results[1],
        ).subgoal_results[0]
        self.assertIsInstance(current_result, CoqError)
        if not isinstance(current_result, CoqError):
            return

        current_result = t.cast(
            CoqPartialSuccess,
            t.cast(CoqPartialSuccess, result.subgoal_results[1]).subgoal_results[1],
        ).subgoal_results[1]
        self.assertIsInstance(current_result, c.contexts.ProofContext)


class Test_ProofScript_RunAdmittingFailedSubgoals_AdjRemoveNodeSpec(unittest.TestCase):
    coq: Coq

    def setUp(self):
        self.coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coq-wigderson",
                file_name="subgraph.v",
                lemma_name="adj_remove_node_spec",
                coq_version="8.13",
            )
        )

        preamble = """Lemma adj_remove_node_spec : forall g v i j, S.In i (adj (remove_node v g) j) <-> S.In i (adj g j) /\\ i <> v /\\ j <> v.
Proof.""".splitlines()

        for command in preamble:
            if command.strip() != "":
                self.coq.run_preamble(command)

    def tearDown(self):
        self.coq.teardown()

    def test_gpt_completion_1(self):
        prefix = ProofScript.parse(
            """
split; intros H.
- split.
-- admit.
"""
        )
        result = prefix.run_until_end_or_error(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        result = Tactic("--").run(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        result = Tactic("{").run(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        script = ProofScript.parse(
            """
split; unfold not; intros. 
- contradict H. apply Logic.eq_sym; exact H. 
- contradict H. apply Logic.eq_sym; exact H.
"""
        )

        generator = script.run_admitting_failed_subgoals(
            self.coq, try_hammer_on_error=True
        )
        tactics_run = []
        while True:
            try:
                result = next(generator)
                tactics_run.append(result)
            except StopIteration as e:
                result = e.value
                break

        self.assertEqual(
            [tactic[0].text for tactic in tactics_run],
            [
                "split; unfold not; intros.",
                "-",
                "contradict H.",
                "hammer.",
                "-",
                "contradict H.",
                "hammer.",
            ],
        )

        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return


class Test_ProofScript_RunAdmittingFailedSubgoals_TwoColorUpInj(unittest.TestCase):
    coq: Coq

    def setUp(self):
        self.coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coq-wigderson",
                file_name="wigderson.v",
                lemma_name="two_color_up_inj",
                coq_version="8.13",
            )
        )

        preamble = """Lemma two_color_up_inj f g (inj : S.elt -> S.elt) : injective inj -> undirected g -> coloring_ok two_colors g f -> {h | coloring_ok (fold_right S.add S.empty [inj 1;inj 2]) g h}.
Proof.""".splitlines()

        for command in preamble:
            if command.strip() != "":
                self.coq.run_preamble(command)

    def test_not_enough_bullets(self):
        """
        In this proof, the "destruct ci.", tactic on line 1 produces three subgoals, but the script only has two bullets. The procedure should correct for this.
        """
        prefix = ProofScript.parse(
            """intros H_inj H_ungdirec H_color_ok. exists f. intros i j H_adj. destruct (H_color_ok i j H_adj) as [H1 H2]. split; try apply H1."""
        )
        script = ProofScript.parse(
            """intros ci Hci. apply H1 in Hci. destruct ci.
- apply S.add_spec; right. apply S.add_spec; left. reflexivity.
- destruct ci.
-- apply S.add_spec; right. apply S.add_spec; right. apply S.add_spec; left. reflexivity.
-- apply S.add_spec; left. reflexivity."""
        )

        result = prefix.run_until_end_or_error(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        result = Tactic("{").run(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq, try_hammer_on_error=True)
        )

        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            [
                "intros ci Hci.",
                "apply H1 in Hci.",
                "destruct ci.",
                "-",
                "apply S.add_spec; right.",
                "apply S.add_spec; left.",
                "hammer.",
                "-",
                "destruct ci.",
                "--",
                "apply S.add_spec; right.",
                "apply S.add_spec; right.",
                "hammer.",
                "--",
                "apply S.add_spec; left.",
                "hammer.",
                "--",
                "admit.",
                "-",
                "admit.",
            ],
        )

        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        LOGGER.info("result", extra={"result": result})

        self.assertEqual(len(result.subgoal_obligations), 3)


class Test_ProofScript_RunUntilGoalDecomposition(unittest.TestCase):
    coq: Coq

    def setUp(self):
        self.coq = Coq()
        preamble = """Require Import FSets.
From Hammer Require Import Hammer.

Module S <: FSetInterface.S := PositiveSet.

Example set_equal_subset: forall s1 s2, S.Equal s1 s2 -> S.Subset s1 s2 /\\ S.Subset s2 s1.
Proof.
""".splitlines()

        for command in preamble:
            if command.strip() != "":
                self.coq.run_preamble(command)

    def tearDown(self):
        self.coq.teardown()

    def test_successful_decomposition(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  split.
  - intros a Ha. rewrite <- H. assumption.
  - intros a Ha. rewrite H. assumption."""
        )

        result = script.run_until_goal_decomposition(self.coq)
        self.assertIsInstance(result, CoqPartialSuccess)
        if not isinstance(result, CoqPartialSuccess):
            return

        self.assertEqual(
            [t.cast(Tactic, tactic).text for tactic in result.prefix.contents],
            [
                "intros.",
                "unfold S.Equal in H.",
                "unfold S.Subset.",
                "split.",
            ],
        )

        self.assertEqual(
            len(result.subgoal_obligations),
            2,
        )

        self.assertEqual(result.subgoal_results, [Skip(), Skip()])

    def test_error_before_decomposition(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in HA. unfold S.Subset. 
  split.
  - intros a Ha. rewrite <- H. assumption.
  - intros a Ha. rewrite H. assumption."""
        )

        result = script.run_until_goal_decomposition(self.coq)
        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.assertEqual(
            result.message,
            "No such hypothesis: HA",
        )
        self.assertEqual(result.token, "unfold S.Equal in HA.")
        self.assertEqual(result.line_number, 2)
        self.assertIsNotNone(result.context)

    def test_no_decomposition_at_bullet(self):
        script = ProofScript.parse(
            """
intros. unfold S.Equal in H. unfold S.Subset. 
  - intros a Ha. rewrite <- H. assumption.
  - intros a Ha. rewrite H. assumption."""
        )

        result = script.run_until_goal_decomposition(self.coq)
        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.assertEqual(
            result.message,
            " (in proof set_equal_subset): Attempt to save an incomplete proof",
        )
        self.assertEqual(result.token, "Qed.")
        self.assertEqual(result.line_number, 0)
        self.assertIsNotNone(result.context)

    def test_empty_string(self):
        script = ProofScript.parse("""""")

        result = script.run_until_goal_decomposition(self.coq)
        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.assertEqual(
            result.message,
            " (in proof set_equal_subset): Attempt to save an incomplete proof",
        )
        self.assertEqual(result.token, "Qed.")
        self.assertEqual(result.line_number, 0)
        self.assertIsNotNone(result.context)


class Test_ProofScript_RunAdmittingFailedSubgoals_MunionCase(unittest.TestCase):
    coq: Coq

    def setUp(self):
        self.coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coq-wigderson",
                file_name="munion.v",
                lemma_name="Munion_case",
                coq_version="8.13",
            )
        )

        preamble = """Lemma Munion_case {A} : forall (c d : M.t A) i v, M.find i (Munion c d) = Some v -> M.find i c = Some v \/ M.find i d = Some v.
Proof.""".splitlines()

        for command in preamble:
            if command.strip() != "":
                self.coq.run_preamble(command)

    def test_hammer_failure(self):
        """
        this proof script seemed to succeed, even though running hammer failed
        """

        prefix = ProofScript.parse(
            """intros c d i.
  unfold Munion.
  apply WP.fold_rec_bis.
  admit. admit. -"""
        )
        script = ProofScript.parse(
            """intros. remember (M.find A i (M.add A k e a)) as u. rewrite <- H3 in Hequ. rewrite <- H2 in Hequ. destruct Hequ. left. assumption. right. assumption."""
        )

        result = prefix.run_until_end_or_error(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        result = Tactic("{").run(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq, try_hammer_on_error=True)
        )

        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            ["intros."],
        )

        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.assertEqual(
            result.message,
            """In environment
A : Type
c, d : M.t A
i, k : M.key
e : A
a, m' : M.t A
H : M.MapsTo k e c
H0 : not (M.In k m')
H1 : forall (v : A) (_ : Logic.eq (M.find i a) (Some v)),
     or (Logic.eq (M.find i m') (Some v)) (Logic.eq (M.find i d) (Some v))
v : A
H2 : Logic.eq (M.find i (M.add k e a)) (Some v)
The term "A" has type "Type" while it is expected to have type "M.key".""",
        )
        self.assertEqual(result.token, "remember (M.find A i (M.add A k e a)) as u.")

    def test_hammer_failure_2(self):
        """
        this also somehow results in a proof context. why?
        """

        prefix = ProofScript.parse(
            """intros c d i.
  unfold Munion.
  apply WP.fold_rec_bis.
  admit. admit. -"""
        )

        script = ProofScript.parse(
            """intros k e a m' c_mapto_k not_in_m' H v find_in_added_a. destruct (H v find_in_added_a) as [find_in_m' | find_in_d].
- left. apply (proof2 find_in_m' not_in_m').
- right. exact find_in_d."""
        )

        result = prefix.run_until_end_or_error(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        result = Tactic("{").run(self.coq)
        self.assertIsInstance(result, c.contexts.ProofContext)
        if not isinstance(result, c.contexts.ProofContext):
            return

        yields, result = run_generator_and_save_yields(
            script.run_admitting_failed_subgoals(self.coq, try_hammer_on_error=True)
        )

        self.assertEqual(
            [tactic.text for tactic, _ in yields],
            ["intros k e a m' c_mapto_k not_in_m' H v find_in_added_a."],
        )

        self.assertIsInstance(result, CoqError)
        if not isinstance(result, CoqError):
            return

        self.maxDiff = None

        self.assertEqual(
            result.message,
            """In environment
A : Type
c, d : M.t A
i, k : M.key
e : A
a, m' : M.t A
c_mapto_k : M.MapsTo k e c
not_in_m' : not (M.In k m')
H : forall (v : A) (_ : Logic.eq (M.find i a) (Some v)),
    or (Logic.eq (M.find i m') (Some v)) (Logic.eq (M.find i d) (Some v))
v : A
find_in_added_a : Logic.eq (M.find i (M.add k e a)) (Some v)
The term "find_in_added_a" has type
 "Logic.eq (M.find i (M.add k e a)) (Some v)"
while it is expected to have type "Logic.eq (M.find i a) (Some v)".""",
        )
        self.assertEqual(
            result.token, "destruct (H v find_in_added_a) as [find_in_m' | find_in_d]."
        )


# endregion PROOF SCRIPT

# region TACTIC


class Test_Tactic_Predicates(unittest.TestCase):
    def test_is_bullet(self):
        tactic = Tactic("-")
        self.assertTrue(tactic.is_bullet)

        tactic = Tactic("--")
        self.assertTrue(tactic.is_bullet)

        tactic = Tactic(" -")
        self.assertTrue(tactic.is_bullet)

        tactic = Tactic(" - ")
        self.assertTrue(tactic.is_bullet)

        tactic = Tactic(" *")
        self.assertTrue(tactic.is_bullet)

        tactic = Tactic(" + ")
        self.assertTrue(tactic.is_bullet)

        tactic = Tactic("intros.")
        self.assertFalse(tactic.is_bullet)

    def test_open_brace(self):
        tactic = Tactic("{")
        self.assertTrue(tactic.is_open_brace)

        tactic = Tactic("{\n")
        self.assertTrue(tactic.is_open_brace)

        tactic = Tactic("\n{")
        self.assertTrue(tactic.is_open_brace)

        tactic = Tactic("\n{\n")
        self.assertTrue(tactic.is_open_brace)

        tactic = Tactic("}")
        self.assertFalse(tactic.is_open_brace)

        tactic = Tactic("-")
        self.assertFalse(tactic.is_open_brace)

        tactic = Tactic("intros.")
        self.assertFalse(tactic.is_open_brace)

    def test_close_brace(self):
        tactic = Tactic("}")
        self.assertTrue(tactic.is_close_brace)

        tactic = Tactic("}\n")
        self.assertTrue(tactic.is_close_brace)

        tactic = Tactic("\n}")
        self.assertTrue(tactic.is_close_brace)

        tactic = Tactic("\n}\n")
        self.assertTrue(tactic.is_close_brace)

        tactic = Tactic("{")
        self.assertFalse(tactic.is_close_brace)

        tactic = Tactic("-")
        self.assertFalse(tactic.is_close_brace)

        tactic = Tactic("intros.")
        self.assertFalse(tactic.is_close_brace)


class Test_Tactic_Identifiers(unittest.TestCase):
    def test_identifiers(self):
        tactic = Tactic("-")
        self.assertEqual(tactic.identifiers, set([]))

        tactic = Tactic("intros.")
        self.assertEqual(tactic.identifiers, set([]))

        tactic = Tactic("intros ci cj H3 H4 contra.")
        self.assertEqual(tactic.identifiers, set(["ci", "cj", "H3", "H4", "contra"]))

        tactic = Tactic("assert (S.In cj p) by hauto l: on.")
        self.assertEqual(
            tactic.identifiers, set(["S.In", "cj", "p", "hauto", "on", "l"])
        )

        tactic = Tactic("apply indep_set_ok.")
        self.assertEqual(tactic.identifiers, set(["indep_set_ok"]))

        tactic = Tactic(
            "sauto lq: on rew: off use: constant_col_indep_set, max_degree_extraction_independent_set."
        )
        self.assertEqual(
            tactic.identifiers,
            set(
                [
                    "lq",
                    "on",
                    "rew",
                    "off",
                    "use",
                    "constant_col_indep_set",
                    "max_degree_extraction_independent_set",
                ]
            ),
        )

        tactic = Tactic("assert (S.In ci p1) by sfirstorder.")
        self.assertEqual(tactic.identifiers, set(["S.In", "ci", "p1", "sfirstorder"]))

        tactic = Tactic("rewrite <- Sin_domain in Hi.")
        self.assertEqual(tactic.identifiers, set(["Sin_domain", "Hi"]))

        tactic = Tactic("destruct H5, H6.")
        self.assertEqual(tactic.identifiers, set(["H5", "H6"]))

        tactic = Tactic(
            "pose proof (max_degree_vert g' (S n) ltac:(hauto use: max_deg_gt_not_empty, nlt_0_r unfold: Peano.lt inv: sumbool) teq)."
        )
        self.assertEqual(
            tactic.identifiers,
            set(
                [
                    "max_degree_vert",
                    "g'",
                    "n",
                    "hauto",
                    "use",
                    "max_deg_gt_not_empty",
                    "nlt_0_r",
                    "unfold",
                    "Peano.lt",
                    "inv",
                    "sumbool",
                    "teq",
                    "S",
                ]
            ),
        )

        tactic = Tactic("destruct l as [|a [|b [|c d]]].")
        self.assertEqual(tactic.identifiers, set(["l", "a", "b", "c", "d"]))

        tactic = Tactic("apply WP.fold_rec_bis.")
        self.assertEqual(tactic.identifiers, set(["WP.fold_rec_bis"]))


# endregion TACTIC

if __name__ == "__main__":
    unittest.main(verbosity=2)
