# original
```coq
Lemma iteres_dom_ok :
 forall (A : Set) (T : mEnsemble A) (f : Map A -> Map A) 
   (x : Map A) (n : nat),
 T x -> def_ok_app A T f -> prechain_dom_ok A T (iteres A f x n).
Proof.
	intros. induction  n as [| n Hrecn]. simpl in |- *. exact (domok_single A x T H). simpl in |- *.
	elim (prechain_sum A (iteres A f x n)); intro. elim H1. intros.
	rewrite H2. rewrite H2 in Hrecn. inversion Hrecn. exact (domok_concat A (f x0) T (single A x0) (H0 x0 H5) Hrecn). elim H1. intros. elim H2.
	intros. rewrite H3. rewrite H3 in Hrecn. inversion Hrecn. exact (domok_concat A (f x0) T (concat A x1 x0) (H0 x0 H7) Hrecn).
Qed.
```

# Cobblestone's
```coq
induction n as [| n IH].
- hammer.
- hammer.
```