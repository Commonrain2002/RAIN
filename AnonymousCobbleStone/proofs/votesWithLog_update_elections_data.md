# original
```coq
Lemma votesWithLog_update_elections_data_timeout :
    forall h st out st' ps t' h' l',
      handleTimeout h (snd st) = (out, st', ps) ->
      In (t', h', l') (votesWithLog (update_elections_data_timeout h st)) ->
      In (t', h', l') (votesWithLog (fst st)) \/
      (t' = currentTerm st' /\ l' = log st').
Proof using. 
    unfold update_elections_data_timeout.
    intros. repeat break_match; simpl in *; intuition; repeat tuple_inversion; intuition.
Qed.
```

# Cobblestone's
```coq
Lemma votesWithLog_update_elections_data_timeout :
forall h st out st' ps t' h' l',
  handleTimeout h (snd st) = (out, st', ps) ->
  In (t', h', l') (votesWithLog (update_elections_data_timeout h st)) ->
  In (t', h', l') (votesWithLog (fst st)) \/
  (t' = currentTerm st' /\ l' = log st').
Proof.
intros h st out st' ps t' h' l' Htimeout Hupdate. simpl in *. remember (update_elections_data_timeout h st) as st_updated. unfold update_elections_data_timeout in Heqst_updated. destruct (handleTimeout h (snd st)) eqn:H1. destruct p. subst. destruct (RaftState.votedFor term name entry logIndex serverType data clientId output r) eqn:H2; simpl in *; [destruct (serverType_eq_dec (RaftState.type term name entry logIndex serverType data clientId output (snd st)) Leader) eqn:H3 | ].
- hammer.
- destruct Hupdate as [Hupdate1 | Hupdate2].
-- hammer.
-- hammer.
- hammer.
Qed.
```