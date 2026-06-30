Require Import Nat.
Require Import Lia.
Require Import Gt.
Require Import List.
Require Import PeanoNat.
Import ListNotations.

Theorem n_plus_1_r: forall n, n + 1 = S n.
Proof.
  lia.
Qed.

Fixpoint rev {A} (l : list A) : list A :=
  match l with
  | [] => []
  | x :: xs => rev xs ++ [x]
  end.

Fixpoint rev_tail' {A} (l : list A) (acc : list A) : list A :=
  match l with
  | [] => acc
  | x :: l' => rev_tail' l' (x :: acc)
  end.

Definition rev_tail {A} (l : list A) : list A := rev_tail' l [].

Theorem rev_tail_correct :
  forall A (l : list A),
    rev_tail l = rev l.
Proof.
    assert (forall A (l : list A) acc,
               rev_tail' l acc = rev l ++ acc) as H.
    { induction l; intros; simpl.
      - reflexivity.
      - rewrite IHl. rewrite <- app_assoc. reflexivity. }
    intros. unfold rev_tail. rewrite H. rewrite app_nil_r. reflexivity.
Qed.


Theorem negb_involutive : forall b : bool,
  negb (negb b) = b.
Proof.
  intros b. destruct b eqn:E.
  - reflexivity.
  - reflexivity.
Qed.