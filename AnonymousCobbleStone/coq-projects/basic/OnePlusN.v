Require Import Nat.
Require Import Lia.
Require Import Gt.

Theorem one_plus_n: forall n, 1 + n > n.
Proof.
  lia.
Qed.
