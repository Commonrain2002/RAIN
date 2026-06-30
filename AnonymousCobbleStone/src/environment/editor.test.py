import unittest

from src.environment.editor import (
    TacticEditor,
)
from src.environment.actions import (
    AppendAction,
    EditAction,
    ReplaceAction,
)
from src.utils import get_logger
from src.coq_serapy_util import Coq, LemmaLocation

LOGGER = get_logger(__name__)

ONE_PLUS_N_COMMAND = "Example one_plus_n: forall n: nat, 1 + n > n."


class TestTacticEditor(unittest.TestCase):
    def test_one_plus_n_initial_code(self):
        editor = TacticEditor(ONE_PLUS_N_COMMAND)
        self.assertEqual(
            editor.runnable_code,
            """Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
Qed.""",
        )

    def test_one_plus_n_edit(self):
        editor = TacticEditor(ONE_PLUS_N_COMMAND)

        result = editor.step(EditAction(new_code="intros. Admitted."))
        self.assertEqual(
            result,
            """Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
intros.
Qed.""",
        )

    def test_one_plus_n_append(self):
        editor = TacticEditor(ONE_PLUS_N_COMMAND)

        result = editor.step(AppendAction(tactics_to_append="intros. Admitted."))
        self.assertEqual(
            result,
            """Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
intros.
Qed.""",
        )

    def test_one_plus_n_replace(self):
        editor = TacticEditor(ONE_PLUS_N_COMMAND)

        result = editor.step(
            EditAction(
                new_code="""intros.
induction n.
- auto.
- auto."""
            )
        )

        self.assertEqual(
            result,
            """Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
intros.
induction n.
- auto.
- auto.
Qed.""",
        )

        result = editor.step(ReplaceAction(new_tactics="lia."))
        self.assertEqual(
            result,
            """Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
lia.
Qed.""",
        )

    def test_one_plus_n_prefix_initial_code(self):
        editor = TacticEditor(
            ONE_PLUS_N_COMMAND,
            proof_prefix="intros.",
        )
        self.assertEqual(
            editor.runnable_code,
            """Example one_plus_n: forall n: nat, 1 + n > n.
Proof.
intros.
Qed.""",
        )
        self.assertEqual(
            editor.observation_code,
            "",
        )
        self.assertEqual(
            editor.runnable_line_number_to_observation_line_number(4),
            1,
        )


class TestTacticEditor__compute_goal_decomposition(unittest.TestCase):
    def test_Comp_mon_compute_goal_decomposition(self):
        editor = TacticEditor(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
        )

        coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            )
        )

        initial_result = coq.run_code(editor.runnable_code)

        initial_proof_context = initial_result.context
        self.assertIsNotNone(initial_proof_context)
        if initial_proof_context is None:
            return

        self.assertEqual(len(initial_proof_context.fg_goals), 1)
        self.assertEqual(
            initial_proof_context.fg_goals[0].goal, "monotonic TX TY (Comp G F)"
        )

        editor.step(
            EditAction(
                new_code="""apply mkmon.
- admit.
- admit.
- intros R S H1 H2. unfold evolve_a. intros a. unfold Comp. apply mon_a.
    + exact HG.
    + Check Lbl. Print Lbl. Check reduction_t. Print reduction_t."""
            )
        )

        self.assertEqual(
            editor.runnable_code,
            """Lemma Comp_mon: monotonic TX TY (Comp G F).
Proof.
apply mkmon.
- admit.
- admit.
- intros R S H1 H2. unfold evolve_a. intros a. unfold Comp. apply mon_a.
    + exact HG.
    + Check Lbl. Print Lbl. Check reduction_t. Print reduction_t.
Qed.""",
        )

        goal_decomposition = editor.compute_goal_decomposition(
            initial_proof_context, coq
        )

        self.assertIsNotNone(goal_decomposition)
        if goal_decomposition is None:
            return

        self.assertEqual(goal_decomposition[0], "apply mkmon.")
        self.assertEqual(len(goal_decomposition[1]), 3)
        self.assertEqual(
            [observation.goal for observation in goal_decomposition[1]],
            [
                "increasing (Comp G F)",
                "forall (R S : relation2 X Y) (_ : evolve_t TX TY R S) (_ : incl R S),\nevolve_t TX TY (Comp G F R) (Comp G F S)",
                "forall (R S : relation2 X Y) (_ : evolve TX TY R S) (_ : incl R S),\nevolve_a TX TY (Comp G F R) (Comp G F S)",
            ],
        )

    def test_Comp_mon_compute_goal_decomposition_with_error(self):
        editor = TacticEditor(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
        )

        coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            )
        )

        initial_result = coq.run_code(editor.runnable_code)
        initial_proof_context = initial_result.context

        self.assertIsNotNone(initial_proof_context)
        if initial_proof_context is None:
            return

        self.assertEqual(len(initial_proof_context.fg_goals), 1)
        self.assertEqual(
            initial_proof_context.fg_goals[0].goal, "monotonic TX TY (Comp G F)"
        )

        editor.step(EditAction(new_code="unfold monotonic."))

        self.assertEqual(
            editor.runnable_code,
            """Lemma Comp_mon: monotonic TX TY (Comp G F).
Proof.
unfold monotonic.
Qed.""",
        )

        goal_decomposition = editor.compute_goal_decomposition(
            initial_proof_context, coq
        )

        self.assertIsNone(goal_decomposition)

    def test_Comp_mon_compute_goal_decomposition_with_error_2(self):
        self.maxDiff = None
        editor = TacticEditor(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
        )

        coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            )
        )

        initial_result = coq.run_code(editor.runnable_code)
        initial_proof_context = initial_result.context

        self.assertIsNotNone(initial_proof_context)
        if initial_proof_context is None:
            return

        self.assertEqual(len(initial_proof_context.fg_goals), 1)
        self.assertEqual(
            initial_proof_context.fg_goals[0].goal, "monotonic TX TY (Comp G F)"
        )

        editor.step(
            EditAction(
                new_code="""intros A X Y TX TY F G HF HG.
unfold monotonic.
split.
- intros R S HRS. apply mon_m in HF. apply mon_m in HG. 
  apply HF in HRS. apply HG in HRS. unfold Comp. assumption.
- split; intros R S HRS HRS'.
  + apply mon_t in HF. apply mon_t in HG. 
    unfold Comp in HF, HG. apply HF in HRS. 
    apply HG in HRS. assumption.
  + apply mon_a in HF. apply mon_a in HG.
    unfold Comp in HF, HG. apply HF in HRS. 
    apply HG in HRS. assumption."""
            )
        )

        #         self.assertEqual(
        #             editor.runnable_code,
        #             """Lemma Comp_mon: monotonic TX TY (Comp G F).
        # Proof.
        # intros A X Y TX TY F G HF HG.
        # unfold monotonic.
        # split.
        # - intros R S HRS. apply mon_m in HF. apply mon_m in HG.
        #   apply HF in HRS. apply HG in HRS. unfold Comp. assumption.
        # - split; intros R S HRS HRS'.
        #   + apply mon_t in HF. apply mon_t in HG.
        #     unfold Comp in HF, HG. apply HF in HRS.
        #     apply HG in HRS. assumption.
        #   + apply mon_a in HF. apply mon_a in HG.
        #     unfold Comp in HF, HG. apply HF in HRS.
        #     apply HG in HRS. assumption.""",
        #         )

        goal_decomposition = editor.compute_goal_decomposition(
            initial_proof_context, coq
        )

        self.assertIsNone(goal_decomposition)

    def test_Comp_mon_compute_goal_decomposition_with_prefix(self):
        editor = TacticEditor(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
            proof_prefix="""apply mkmon.
            - admit. (* skipping this subgoal to focus on the main one *)
            
            
            - admit.
            - """,
        )

        coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            )
        )

        initial_result = coq.run_code(editor.runnable_code)

        initial_proof_context = initial_result.context
        self.assertIsNotNone(initial_proof_context)
        if initial_proof_context is None:
            return

        self.assertEqual(len(initial_proof_context.fg_goals), 1)
        self.assertEqual(
            initial_proof_context.fg_goals[0].goal,
            "forall (R S : relation2 X Y) (_ : evolve TX TY R S) (_ : incl R S),\nevolve_a TX TY (Comp G F R) (Comp G F S)",
        )

        editor.step(
            EditAction(
                new_code="""intros R S H1 H2. unfold evolve_a. intros a. unfold Comp. apply mon_a.
+ exact HG.
+ Check Lbl. Print Lbl. Check reduction_t. Print reduction_t."""
            )
        )

        self.assertEqual(
            editor.runnable_code,
            """Lemma Comp_mon: monotonic TX TY (Comp G F).
Proof.
apply mkmon.
            - admit. (* skipping this subgoal to focus on the main one *)
            
            
            - admit.
            - 
intros R S H1 H2. unfold evolve_a. intros a. unfold Comp. apply mon_a.
+ exact HG.
+ Check Lbl. Print Lbl. Check reduction_t. Print reduction_t.
Qed.""",
        )

        goal_decomposition = editor.compute_goal_decomposition(
            initial_proof_context, coq
        )

        self.assertIsNotNone(goal_decomposition)
        if goal_decomposition is None:
            return

        self.assertEqual(
            goal_decomposition[0],
            """intros R S H1 H2.
unfold evolve_a.
intros a.
unfold Comp.
apply mon_a.""",
        )
        self.assertEqual(len(goal_decomposition[1]), 3)
        self.assertEqual(
            [observation.goal for observation in goal_decomposition[1]],
            [
                "monotonic TX TY G",
                "evolve TX TY (F R) (F S)",
                "incl (F R) (F S)",
            ],
        )

    def test_Comp_mon_3(self):
        self.maxDiff = None
        editor = TacticEditor(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
        )

        coq = Coq(
            lemma_location=LemmaLocation(
                project_name="coqgym/coq-projects/weak-up-to",
                file_name="Monotonic.v",
                section_names=["Global"],
                lemma_name="Comp_mon",
                coq_version="8.10",
            )
        )

        initial_result = coq.run_code(editor.runnable_code)
        initial_proof_context = initial_result.context

        self.assertIsNotNone(initial_proof_context)
        if initial_proof_context is None:
            return

        self.assertEqual(len(initial_proof_context.fg_goals), 1)
        self.assertEqual(
            initial_proof_context.fg_goals[0].goal, "monotonic TX TY (Comp G F)"
        )

        editor.step(
            EditAction(
                new_code="""destruct HG as [HG_m [HG_t HG_a]]; destruct HF as [HF_m [HF_t HF_a]].
split.
  - intros R S incl_RS.
    unfold Comp; simpl.
    apply HG_m; apply HF_m; assumption.
  - split; intros R S evo_RS incl_RS.
    + unfold Comp.
      apply (HG_t); apply HF_t; assumption.
    + apply (HG_a).
      apply (HF_a) with R; assumption."""
            )
        )

        goal_decomposition = editor.compute_goal_decomposition(
            initial_proof_context, coq
        )

        self.assertIsNotNone(goal_decomposition)
        if goal_decomposition is None:
            return

        self.assertEqual(
            goal_decomposition[0],
            """destruct HG as [HG_m [HG_t HG_a]]; destruct HF as [HF_m [HF_t HF_a]].""",
        )
        self.assertEqual(len(goal_decomposition[1]), 25)


class TestTacticEditor__runnable_line_number_to_observation_line_number(
    unittest.TestCase
):
    def test_Comp_mon(self):
        self.maxDiff = None

        editor = TacticEditor(
            "Lemma Comp_mon: monotonic TX TY (Comp G F).",
        )

        editor.step(
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
            editor.runnable_code,
            """Lemma Comp_mon: monotonic TX TY (Comp G F).
Proof.
unfold monotonic; intros.
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
  + assumption.
Qed.""",
        )

        self.assertEqual(
            editor.observation_code,
            """unfold monotonic; intros.
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
  + assumption.""",
        )

        self.assertEqual(
            editor.runnable_line_number_to_observation_line_number(3),
            1,
        )


if __name__ == "__main__":
    unittest.main()
