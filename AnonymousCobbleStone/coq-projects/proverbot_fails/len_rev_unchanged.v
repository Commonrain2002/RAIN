Require Import List.
Require Import PeanoNat.
Import ListNotations.

Theorem len_rev_unchanged: forall (A: Type) (l: list A), length (rev l) = length l.
Proof.
    induction l.
    - auto.
    - assert (H: rev (a :: l) = (rev l) ++ [a]) by auto.
      rewrite H.
      simpl.
      rewrite app_length.
      simpl.
      rewrite IHl.
      rewrite PeanoNat.Nat.add_1_r.
      reflexivity.
Qed.
    
