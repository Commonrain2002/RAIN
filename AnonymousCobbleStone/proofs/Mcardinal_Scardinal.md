# original
```coq
Lemma Mcardinal_Scardinal: forall A (m : M.t A) s,
    (forall k, M.In k m <-> S.In k s) ->
    M.cardinal m = S.cardinal s.
Proof.
  intros A m s H.
  rewrite WP.cardinal_fold.
  revert s H.
  apply WP.fold_rec_bis.
  - intros m0 m' a H H0 s H1.
    apply H0. intros k. rewrite <- H1. apply WF.In_m; auto.
  - intros s H.
    rewrite SP.cardinal_1. auto.
    unfold S.Empty. intros k.
    specialize (H k).
    rewrite <- H.
    rewrite WF.empty_in_iff.
    scongruence.
  - intros k e a m' H H0 H1 s H2.
    rewrite <- SP.add_remove with (x := k) by (apply H2; rewrite WF.add_in_iff; auto).
    rewrite SP.add_cardinal_2 by (rewrite S.remove_spec; sfirstorder).
    f_equal.
    apply H1.
    intros k0.
    specialize (H2 k0).
    rewrite S.remove_spec.
    rewrite <- H2.
    rewrite WF.add_in_iff.
    sfirstorder.
Qed.
```

# Cobblestone's
```coq
Lemma Mcardinal_Scardinal: forall A (m : M.t A) s,
    (forall k, M.In k m <-> S.In k s) ->
    M.cardinal m = S.cardinal s.
Proof.
intros A m s H. rewrite WP.cardinal_fold. revert s H. 
apply WP.fold_rec_bis.
- hammer.
- hammer.
- intros. assert (Hs: S.In k s). { hammer.}
assert (H'a: eq a (S.cardinal (S.remove k s))).
{ apply H1. intros k0. rewrite S.remove_spec. hammer. }
hammer.
Qed.
```