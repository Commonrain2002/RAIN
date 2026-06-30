Require Import List.
Require Import Nat.
Import ListNotations.
Require Import Lia.

(* 
Proving that fib is equivalent to fib_tail 
This is a difficult version of a problem that requires introducing a 
more general lemma to solve
*)

Fixpoint fib (n: nat) : nat :=
    match n with
    | 0 => 1
    | S n' => match n' with
              | 0 => 1
              | S n'' => fib n' + fib n''
              end
    end.

Fixpoint fib_tail' (n a b: nat) : nat :=
    match n with
    | 0 => a
    | S n' => fib_tail' n' b (a + b)
    end.


Definition fib_tail (n: nat) : nat :=
    fib_tail' n 1 1.


Theorem fib_correct :
  forall n,
    fib_tail n = fib n.
Proof.
    assert (forall n k a b,
        a = fib k ->
        b = fib (k + 1) ->
        fib_tail' n a b = fib (k + n)) as fib_tail'_correct.
    {
        induction n.
        - intros. simpl. rewrite <- plus_n_O. auto.
        - intros. simpl. 
            rewrite H. rewrite H0. 
            replace (fib k + fib (k + 1)) with (fib (k + 2)).
            replace (k + S n) with (k + 1 + n) by lia.
            rewrite IHn with (k := k + 1); try reflexivity.
            + replace (k + 1 + 1) with (k + 2) by lia. reflexivity.
            + replace (k + 2) with (S (S k)) by lia. 
            replace (k + 1) with (S k) by lia.
            simpl. lia. 
    }

    intros. unfold fib_tail. rewrite fib_tail'_correct with (k := 0); auto.
Qed.
