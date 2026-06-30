Require Import List.
Import ListNotations.
Require Import Nat.

Fixpoint min (l : (list nat)) : option nat :=
    match l with
    | nil => None
    | h :: tl => match (min tl) with
        | None => Some h
        | Some m => if (h <? m) then (Some h) else (Some m)
        end
    end.

Lemma exists_min: forall (l : (list nat)), 
    (l <> nil) -> exists h, min(l) = Some(h).
Proof.
    (* gold standard *)
    destruct l as [| h tl] eqn:E_l.
    - intros. exfalso. apply H. reflexivity.
    - intros. simpl. destruct (min tl) eqn:E_min.
        + destruct (h <? n).
          * exists h. reflexivity.
          * exists n. reflexivity. 
        + exists h. reflexivity.
Qed.
