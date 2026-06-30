Require Import List.
Require Import Nat.
Import ListNotations.
Require Import Lia.

(* 
Proving that sum is equivalent to sum_tail 
This is a relatively easy version of a problem that requires introducing a 
more general lemma to solve
*)

Fixpoint sum (l: list nat) : nat :=
    match l with
    | [] => 0
    | x :: xs => x + sum xs
    end.

Fixpoint sum_tail' (l: list nat) (acc: nat) : nat :=
    match l with
    | [] => acc
    | x :: xs => sum_tail' xs (x + acc)
    end.

Definition sum_tail (l: list nat) : nat :=
    sum_tail' l 0.
  

Theorem sum_tail_correct :
  forall l,
    sum_tail l = sum l.
Proof.
    (* we need a more general helper to solve this theorem *)
    assert (forall l acc, sum_tail' l acc = acc + sum l) as sum_tail_correct_with_acc.
    {
    induction l.
    - intros. simpl. rewrite <- plus_n_O. reflexivity.
    - intros. simpl. rewrite IHl. lia.
    }

    intros. unfold sum_tail. rewrite sum_tail_correct_with_acc. lia.
Qed.
