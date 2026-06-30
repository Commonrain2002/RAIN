# original
```coq
Lemma requestVoteReply_term_sanity_client_request :
refined_raft_net_invariant_client_request requestVoteReply_term_sanity.
Proof using. 
    red. unfold requestVoteReply_term_sanity. intros. simpl in *.
    find_copy_apply_lem_hyp handleClientRequest_packets.
    subst. simpl in *.
    find_apply_hyp_hyp. intuition.
    repeat find_higher_order_rewrite.
    destruct_update; simpl in *; eauto.
    find_apply_lem_hyp handleClientRequest_term_votedFor.
    intuition; repeat find_rewrite; eauto.
Qed.
```
