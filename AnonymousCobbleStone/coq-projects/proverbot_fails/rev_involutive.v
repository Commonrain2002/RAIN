Require Import List.
Import ListNotations.

Theorem rev_involutive: forall (A: Type) (l: list A), rev (rev l) = l.
Proof.
Admitted.
