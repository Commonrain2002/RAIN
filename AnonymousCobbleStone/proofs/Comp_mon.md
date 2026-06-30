# original
```coq
Lemma Comp_mon: monotonic TX TY (Comp G F).
Proof.
    unfold Comp; split.
    intros R S HRS; apply (mon_m HG (mon_m HF HRS)).
    intros R S H H'; apply (mon_t HG (mon_t HF H H') (mon_m HF H')).
    intros R S H H'; apply (mon_a HG).
    intro l; destruct l.
    apply (mon_t HF (H _) H').
    apply (mon_a HF H H').
    apply (mon_m HF H').      
Qed.
```

# Cobblestone's
```coq
Lemma Comp_mon: monotonic TX TY (Comp G F).
Proof.
split.
- unfold increasing. intros R S HRS. unfold Comp. apply HG. apply HF. assumption.
- intros R S H_evol H_incl. apply HG.
-- hammer.
-- hammer.
- intros R S H H_inc a. apply HG.
-- hammer.
-- hammer.
Qed.
```