import pickle
import json
from pathlib import Path
import typing as t

from src.dataset.dataset import Dataset
from src.config import CONFIG

# region DEV
COQGYM_DEV_SAMPLED_FILE = Path(CONFIG.ROOT_DIR) / "data/COQGYM_DEV_SAMPLED_DATASET.pkl"
COQGYM_DEV_SAMPLED_DATASET: Dataset = pickle.load(open(COQGYM_DEV_SAMPLED_FILE, "rb"))
# COQGYM_DEV_SAMPLED_DATASET: Dataset = []
COQGYM_DEV_COQHAMMER_RESULTS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQGYM_DEV_COQHAMMER_RESULTS.json"
)

COQGYM_DEV_PROVERBOT_RESULTS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQGYM_DEV_PROVERBOT_RESULTS.json"
)
COQGYM_DEV_ZERO_SHOT_RESULTS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQGYM_DEV_ZERO_SHOT_RESULTS.json"
)
COQGYM_DEV_COQHAMMER_RESULTS: t.Dict[str, bool] = json.load(
    open(COQGYM_DEV_COQHAMMER_RESULTS_FILE, "r")
)
COQGYM_DEV_PROVERBOT_RESULTS: t.Dict[str, bool] = json.load(
    open(COQGYM_DEV_PROVERBOT_RESULTS_FILE, "r")
)
COQGYM_DEV_ZERO_SHOT_RESULTS: t.Dict[str, bool] = json.load(
    open(COQGYM_DEV_ZERO_SHOT_RESULTS_FILE, "r")
)
COQGYM_DEV_SAMPLED_DATASET_BASELINES_FAIL = [
    example
    for example in COQGYM_DEV_SAMPLED_DATASET
    if (not COQGYM_DEV_COQHAMMER_RESULTS[example.name])
    # and (not COQGYM_DEV_PROVERBOT_RESULTS[example.name])
    and (not COQGYM_DEV_ZERO_SHOT_RESULTS[example.name])
]

COQGYM_DEV_SAMPLED_PERFECT_PREFIX: t.Dict[str, str] = {
    "UnifySL-SeparationLogic.v-falsep_sepcon": """intros.
  apply solve_andp_intros.""",
    "buchberger-Pcomb.v-ConfluentReduce_imp_Grobner": """""",
    "chinese-Zgcd.v-gcd_unicity_apart_sign": """""",
    "coquelicot-RInt.v-norm_RInt_le_const": """""",
    "fermat4-Diophantus20.v-multiple4_2": """""",
    "goedel-wConsistent.v-wCon2Con": """""",
    "huffman-HeightPred.v-height_pred_weight": """""",
    "huffman-PBTree.v-compute_pbcode_not_null": """""",
    "jordan-curve-theorem-Jordan10.v-between_bottom_B0_bis": """""",
    "jordan-curve-theorem-Jordan6.v-expf_L1_CNS": """intros.
split.""",
    "tree-automata-union.v-new_state_insd_0": """""",
    "tree-automata-union.v-union_pl_0": """""",
    "verdi-LockServ.v-locks_correct_locked_input_handlers_old": """set_up_input_handlers.
    destruct (pBody p) eqn:?.""",
    "verdi-LockServ.v-locks_correct_unlock_at_head": """""",
    "verdi-raft-CandidateEntriesProof.v-advanceCurrentTerm_same_or_type_follower": """""",
    "verdi-raft-CandidateEntriesProof.v-doGenericServer_spec": """""",
    "verdi-raft-LeadersHaveLeaderLogsStrongProof.v-handleRequestVoteReply_spec": """""",
    "verdi-raft-Linearizability.v-acknowledge_all_ops_func_correct": """""",
    "verdi-raft-LogMatchingProof.v-log_matching_reboot": """""",
    "verdi-raft-RefinedLogMatchingLemmasProof.v-entries_contiguous_nw_invariant": """""",
}

COQGYM_DEV_SAMPLED_PERFECT_PREMISE_NAMES: t.Dict[str, t.List[str]] = {
    "UnifySL-SeparationLogic.v-falsep_sepcon": [
        "solve_andp_intros",
        "falsep_sepcon_left",
        "falsep_sepcon_right",
    ],
    "buchberger-Pcomb.v-ConfluentReduce_imp_Grobner": [
        "Grobner0",
        "pO_reducestar",
        "inPolySet_imp_canonical",
        "CombLinear_canonical",
        "reducestar_in_pO",
        "reducestar_eqp_com",
        "reducestar_trans",
        "reducestar_trans",
        "canonical_reduceplus",
        "reduceplus_eqp_com",
        "eqp_sym",
        "eqp_trans",
        "eqp_trans",
        "eqp_trans",
        "eqp_trans",
        "canonical_reduceplus",
        "eqp_imp_canonical",
        "eqp_sym",
    ],
    "chinese-Zgcd.v-gcd_unicity_apart_sign": ["mult_IZ", "mult_mIZ"],
    "coquelicot-RInt.v-norm_RInt_le_const": [
        "norm_RInt_le",
        "is_RInt_const",
    ],
    "fermat4-Diophantus20.v-multiple4_2": [
        "Zmult_lt_0_reg_r",
        "Zmult_comm" "gcd2_rel_prime",
        "gcd2_relp_odd",
        "Zmult_lt_0_reg_r" "Zmult_comm",
        "gcd2_rel_prime",
        "Zis_gcd_sym",
        "gcd2_relp_odd",
    ],
    "goedel-wConsistent.v-wCon2Con": [
        "existSimp",
        "nnI",
        "eqRefl",
    ],
    "huffman-HeightPred.v-height_pred_weight": ["prod2list_app", "height_pred_length"],
    "huffman-PBTree.v-compute_pbcode_not_null": [],
    "jordan-curve-theorem-Jordan10.v-between_bottom_B0_bis": [
        "not_pred_bottom",
        "bottom_B0_bis",
        "exd_bottom",
        "expe_bottom_z",
        "bottom_B0_quad",
        "not_pred_bottom",
        "expe_bottom_z",
        "bottom_B0_ter",
        "not_pred_bottom",
        "bottom_bottom",
        "bottom_B0_quad",
        "not_pred_bottom",
    ],
    "jordan-curve-theorem-Jordan6.v-expf_L1_CNS": [
        "expf_L1_II_CN",
        "expf_L1_I_CN",
        "expf_L1_II_CS",
        "expf_L1_I_CS",
    ],
    "tree-automata-union.v-new_state_insd_0": [
        "rec_dta",
        "MapPut_semantics",
        "Neqb_complete",
    ],
    "tree-automata-union.v-union_pl_0": [],
    "verdi-LockServ.v-locks_correct_locked_input_handlers_old": [
        "update_nop_ext",
        "InputHandler_cases",
        "locked_in_flight_all_clients_false",
    ],
    "verdi-LockServ.v-locks_correct_unlock_at_head": ["at_head_of_queue_intro"],
    "verdi-raft-CandidateEntriesProof.v-advanceCurrentTerm_same_or_type_follower": [],
    "verdi-raft-CandidateEntriesProof.v-doGenericServer_spec": ["applyEntries_spec"],
    "verdi-raft-LeadersHaveLeaderLogsStrongProof.v-handleRequestVoteReply_spec": [],
    "verdi-raft-Linearizability.v-acknowledge_all_ops_func_correct": [],
    "verdi-raft-LogMatchingProof.v-log_matching_reboot": [
        "log_matching_state_same_packet_subset",
    ],
    "verdi-raft-RefinedLogMatchingLemmasProof.v-entries_contiguous_nw_invariant": [
        "log_matching_invariant",
        "lift_prop",
        "ghost_packet",
    ],
}
# endregion DEV

# region TEST

COQGYM_TEST_SAMPLED_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQGYM_TEST_SAMPLED_DATASET.pkl"
)

COQGYM_TEST_SAMPLED_DATASET: Dataset = pickle.load(open(COQGYM_TEST_SAMPLED_FILE, "rb"))
# COQGYM_TEST_SAMPLED_DATASET: Dataset = []


COQGYM_TEST_COQHAMMER_RESULTS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQGYM_TEST_COQHAMMER_RESULTS.json"
)
COQGYM_TEST_PROVERBOT_RESULTS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQGYM_TEST_PROVERBOT_RESULTS.json"
)
COQGYM_TEST_ZERO_SHOT_RESULTS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQGYM_TEST_ZERO_SHOT_RESULTS.json"
)

COQGYM_TEST_COQHAMMER_RESULTS: t.Dict[str, bool] = json.load(
    open(COQGYM_TEST_COQHAMMER_RESULTS_FILE, "r")
)
COQGYM_TEST_PROVERBOT_RESULTS: t.Dict[str, bool] = json.load(
    open(COQGYM_TEST_PROVERBOT_RESULTS_FILE, "r")
)
COQGYM_TEST_ZERO_SHOT_RESULTS: t.Dict[str, bool] = json.load(
    open(COQGYM_TEST_ZERO_SHOT_RESULTS_FILE, "r")
)


COQGYM_TEST_SAMPLED_DATASET_BASELINES_FAIL = [
    example
    for example in COQGYM_TEST_SAMPLED_DATASET
    if (not COQGYM_TEST_COQHAMMER_RESULTS[example.name])
    # and (not COQGYM_TEST_PROVERBOT_RESULTS[example.name])
    and (not COQGYM_TEST_ZERO_SHOT_RESULTS[example.name])
]

COQGYM_TEST_SAMPLED_PERFECT_PREFIX: t.Dict[str, str] = {
    "PolTac-PolAux.v-Rge_sign_pos_pos_rev": """""",
    "UnifySL-ContextProperty.v-sig_context_ext": """""",
    "buchberger-DivTerm.v-divTerm_eqT": """intros a b c; case a; case b; case c; simpl in |- *; auto.
intros a1 m1 a2 m2 a3 m3 H1 H2 H3 H4 H5; case H5; intros H6 H7; split; auto.""",
    "buchberger-POrder.v-ltp_not_refl": """intros x; elim x.
red in |- *; intros H'; inversion H'.
intros a l H'; red in |- *; intros H'0; simple inversion H'0.""",
    "buchberger-Pcomb.v-reduce_cb": """""",
    "buchberger-Pcomb.v-reduceplus_cb2_lem": """intros a b Q H'; elim H'; auto.""",
    "buchberger-Peq.v-seqp_dec": """""",
    "buchberger-Pminus.v-minusTerm_zeroP_r": """""",
    "buchberger-Pminus.v-minuspf_eq_inv1": """intros a p q; case q; simpl in |- *; auto.""",
    "buchberger-Pmults.v-mults_eqp_zpO": """""",
    "buchberger-Preduce.v-reduce_eqp_com": """intros Q p q r s H'; generalize r s; clear r s; elim H'; auto.""",
    "buchberger-Term.v-zeroP_multTerm_l": """""",
    #
    "chinese-Zmult.v-mult_oppZ_l": """simple destruct y.""",
    #
    "coquelicot-Derive.v-filterdiff_scal_r": """""",
    #
    "dblib-DeBruijn.v-closed_lift_invariant": """induction w.""",
    "dblib-DeBruijn.v-closed_monotonic": """""",
    "dblib-DemoLambda.v-red_closed": """induction 1.""",
    #
    "fermat4-Pythagorean.v-pytha_thm2": """unfold pytha_set, is_pytha, cond_pq, cond_pqb, pos_triple. intros. elim_hyps.""",
    #
    "fundamental-arithmetics-permutation.v-permutation_impl_Permutation": """induction 1.""",
    "goedel-LNT.v-cp2": """""",
    "goedel-cPair.v-codeNthIsPR": """""",
    "huffman-Frequency.v-in_frequency_map": """intros l; elim l; simpl in |- *; auto.
intros a l0 H a0 [H0| H0]; auto.""",
    #
    "jordan-curve-theorem-Jordan1.v-A_B_1_bis": """induction m.""",
    "jordan-curve-theorem-Jordan1.v-succ_pred_clos": """induction m.""",
    "jordan-curve-theorem-Jordan10.v-A_L_B_top_bot_ter": """intros.
induction k.""",
    "jordan-curve-theorem-Jordan3.v-eqc_exd_exd": """induction m.""",
    "jordan-curve-theorem-Jordan7.v-expf_B0_CS_2_a_II": """""",
    "jordan-curve-theorem-Jordan8.v-nf_L0L1_VB": """""",
    "tree-automata-empty_test.v-dta_app_ne_inc_3": """simple induction m0.""",
    "tree-automata-lattice_fixpoint.v-iteres_dom_ok": """intros. induction  n as [| n Hrecn].""",
    "tree-automata-signature.v-pl_compat_check_correct": """simple induction p. """,
    "tree-automata-union.v-mpl_compat_7_2": """unfold mpl_compat_7_def in |- *. intros. induction  c as [| p]. """,
    #
    "verdi-InverseTraceRelations.v-inverse_trace_relations_work": """intros. find_apply_lem_hyp refl_trans_1n_n1_trace.
    remember init as s'.
    induction H.""",
    "verdi-Net.v-refl_trans_1n_trace_trans": """""",
    "verdi-PartialMapExecutionSimulations.v-pt_map_onet_hd_step_ordered_failure_star": """""",
    "verdi-TotalMapSimulations.v-in_adjacent_exclude_in_exlude": """elim => [|n l IH] failed n' h; first by rewrite remove_all_nil.
have H_cn := remove_all_cons name_eq_dec failed n l.
break_or_hyp; break_and; find_rewrite; first exact: IH.
rewrite /=.
case (adjacent_to_dec _ _) => /= H_dec'.""",
    #
    "verdi-raft-AllEntriesLeaderSublogProof.v-allEntries_leader_sublog_append_entries": """red. unfold allEntries_leader_sublog. intros. simpl in *.
    subst. repeat find_higher_order_rewrite.
    destruct_update; simpl in *; eauto;
    do_in_map; subst;
    destruct x; simpl in *.""",
    "verdi-raft-AppliedEntriesMonotonicProof.v-entries_max_thing": """""",
    "verdi-raft-AppliedEntriesMonotonicProof.v-sorted_app": """induction l; simpl in *; intros; intuition eauto.""",
    "verdi-raft-AppliedImpliesInputProof.v-applied_implies_input_update_split": """""",
    "verdi-raft-InLogInAllEntriesProof.v-in_log_in_all_entries_append_entries_reply": """""",
    "verdi-raft-LeaderLogsSortedProof.v-leaderLogs_sorted_client_request": """unfold refined_raft_net_invariant_client_request, leaderLogs_sorted.
    intros. subst. simpl in *. find_higher_order_rewrite.
    update_destruct_simplify; simpl in *.""",
    "verdi-raft-RefinementSpecLemmas.v-votesWithLog_update_elections_data_timeout": """""",
    "verdi-raft-RefinementSpecLemmas.v-votes_update_elections_data_timeout_votedFor": """""",
    "verdi-raft-RequestVoteReplyTermSanityProof.v-requestVoteReply_term_sanity_client_request": """""",
    "verdi-raft-RequestVoteReplyTermSanityProof.v-requestVoteReply_term_sanity_request_vote_reply": """""",
    "verdi-raft-SpecLemmas.v-handleAppendEntries_currentTerm_leaderId": """""",
    "verdi-raft-StateMachineSafetyPrimeProof.v-sorted_app_in_gt": """""",
    "verdi-raft-StateMachineSafetyProof.v-lifted_maxIndex_sanity_do_generic_server": """unfold msg_refined_raft_net_invariant_do_generic_server,
           lifted_maxIndex_sanity, maxIndex_lastApplied, maxIndex_commitIndex.
    intuition; find_higher_order_rewrite; update_destruct_simplify; auto;
    erewrite doGenericServer_log by eauto.""",
    "verdi-raft-TermsAndIndicesFromOneProof.v-terms_and_indices_from_one_vwl_request_vote_reply": """""",
    "weak-up-to-Monotonic.v-Comp_mon": """unfold Comp; split.""",
    "zfc-Axioms.v-Union_IN": """simple induction E; unfold Union in |- *; simpl in |- *; intros A f r.
simple induction 1.
simple induction x.
intros a b; simpl in |- *.
intros.
exists (f a).
split.""",
    "zorns-lemma-Cardinals.v-cardinals_unbounded": """destruct kappa.
exists (cardinality (T->Prop)).
red; red; split.""",
    "zorns-lemma-FiniteTypes.v-True_finite": """apply bij_finite with (option False)
  (fun _ => I). 
constructor; constructor.
exists (True_rect None).""",
}

COQGYM_TEST_SAMPLED_PERFECT_PREMISE_NAMES: t.Dict[str, t.List[str]] = {
    "PolTac-PolAux.v-Rge_sign_pos_pos_rev": [
        "Rle_ge",
        "Rle_sign_pos_pos_rev",
    ],
    "PolTac-PolAux.v-Rmult_gt_compat_l_rev": ["Rmult_lt_compat_l_rev"],
    "PolTac-PolAux.v-eq_Rgt_trans_r": [],
    "UnifySL-Complete_Kripke.v-AL_DC": [
        "at_least_self",
        "at_least_left",
        "at_least_right",
    ],
    "UnifySL-Complete_Kripke.v-complete_Classical_Kripke_identity": [
        "general_completeness",
        "denote_monotonic",
        "po_R",
        "classical_canonical_ident",
    ],
    "UnifySL-ContextProperty.v-sig_context_ext": [
        "Extensionality_Ensembles",
        "proof_irrelevance",
    ],
    "UnifySL-Ensembles_ext.v-Full_set_spec": [],
    "buchberger-Buch.v-buch_reds": ["pbuchf_Inv"],
    "buchberger-BuchAux.v-zerop_dec": [],
    "buchberger-Dickson.v-monO_n0": ["jjProp2", "jjProp1"],
    "buchberger-DivTerm.v-divTerm_eqT": ["divA_is_multA"],
    "buchberger-POrder.v-ltp_not_refl": [
        "ltT_not_refl",
    ],
    "buchberger-Pcomb.v-reduce_cb": [
        "canonical_reduce",
        "reduce_inv2",
        "CombLinear_comp",
        "eqp_sym",
    ],
    "buchberger-Pcomb.v-reduceplus_cb2_lem": [
        "CombLinear_comp",
        "CombLinear_id",
        "incons",
        "eqp_sym",
        "reduce_cb2",
        "CombLinear_trans_cons_lem",
        "CombLinear_incl",
        "Incl_inp_inPolySet",
        "canonical_reduce",
        "canonical_reduce",
    ],
    "buchberger-Peq.v-seqp_dec": ["eqPf"],
    "buchberger-Pminus.v-minusTerm_zeroP_r": [
        "eqTerm_trans",
        "eqTerm_sym",
        "zeroP_plusTerml",
        "eqT_trans",
    ],
    "buchberger-Pminus.v-minuspf_eq_inv1": [
        "minuspf_pO_refl_eq",
        "minuspf_pO_refl_eq",
        "canonical_pX_order",
    ],
    "buchberger-Pmults.v-mults_eqp_zpO": [],
    "buchberger-Preduce.v-reduce_eqp_com": [
        "reducetop",
        "divP_eqTerm_comp",
        "eqp_trans",
        "canonical_imp_canonical",
        "eqp_spminusf_com",
        "eqp_imp_canonical",
        "canonical_imp_canonical",
        "inPolySet_imp_canonical",
        "eqp_sym",
        "eqTerm_sym",
        "divP_eqTerm_comp",
        "eqp_trans",
        "reduceskip",
        "canonical_imp_canonical",
        "eqTerm_trans",
        "eqTerm_sym",
        "eqTerm_trans",
    ],
    "buchberger-Term.v-zeroP_multTerm_l": ["eqA_trans"],
    "chinese-Z_succ_pred.v-succ_pred_pred_succZ": ["pred_succZ", "succ_predZ"],
    "chinese-Zmult.v-mult_oppZ_l": [
        "mult_OZ",
        "mult_OZ",
        "multZ_commutativity",
        "multZ_commutativity",
        "tech_mult_posZ",
        "opp_add",
        "Z_group",
        "addZ_commutativity",
        "multZ_commutativity",
        "multZ_commutativity",
        "tech_mult_negZ",
        "opp_add",
        "Z_group",
        "addZ_commutativity",
    ],
    "coquelicot-Complex.v-Cmod_2Rmax": [
        "Rmax_case_strong",
        "sqrt_Rsqr_abs",
        "sqrt_mult",
        "Rle_0_sqr",
        "Rlt_le",
        "Rlt_0_2",
        "sqrt_le_1_alt",
        "Rplus_comm",
        "Rsqr",
        "Rle_minus_r",
        "Rsqr_le_abs_1",
        "pow",
        "Rmult_1_r",
    ],
    "coquelicot-Derive.v-filterdiff_scal_r": ["filterdiff_linear", "is_linear_scal_r"],
    "coquelicot-Lim_seq.v-ex_lim_seq_INR": ["is_lim_seq_INR"],
    "dblib-DeBruijn.v-closed_lift_invariant": [
        "lift_zero",
        "lift_lift_fuse",
        "closed_monotonic",
    ],
    "dblib-DeBruijn.v-closed_monotonic": [
        "lift_lift",
    ],
    "dblib-DemoLambda.v-red_closed": [
        "subst_preserves_closed",
    ],
    "dblib-Environments.v-lookup_beyond_length": [
        "lookup_empty_None",
    ],
    "fermat4-ArithCompl.v-Zodd_sqr1": ["Zodd_def2"],
    "fermat4-ArithCompl.v-divide_0": [],
    "fermat4-ArithCompl.v-relp_neq": [],
    "fermat4-Pythagorean.v-pytha_thm2": [
        "Z.le_ge",
        "Z.ge_le",
        "Z.gt_lt",
        "Zlt_le_weak",
        "Zmult_le_0_compat",
    ],
    "fundamental-arithmetics-permutation.v-permutation_impl_Permutation": [
        "perm_nil",
        "insertion_append_decompose",
        "Permutation_cons_app",
    ],
    "goedel-LNN.v-iffSym": ["iffSym"],
    "goedel-LNN.v-sysExtend": ["sysExtend"],
    "goedel-LNT.v-cp2": ["cp2"],
    "goedel-cPair.v-codeNthIsPR": [
        "compose2_1IsPR",
        "ind1ParamIsPR",
        "filter010IsPR",
        "compose1_1IsPR",
        "predIsPR",
        "cPairPi2IsPR",
        "idIsPR",
        "compose1_1IsPR",
        "predIsPR",
        "cPairPi1IsPR",
    ],
    "goedel-checkPrf.v-checkPrfEQ2IsPR": ["checkPrfEQnIsPR"],
    "goedel-codeSubFormula.v-makeTraceImpNice": [],
    "goedel-folProp.v-subTermVar1": [],
    "goedel-primRec.v-gtIsPR": ["swapIsPR", "ltIsPR"],
    "huffman-Frequency.v-frequency_list_unique": ["add_frequency_list_unique_key"],
    "huffman-Frequency.v-in_frequency_map": ["eqA_dec", "eqA_dec"],
    "huffman-PBTree.v-pbleaf_or_not": [],
    "huffman-Restrict.v-restrict_code_pbbuild": [
        "frequency_list_restric_code_map",
        "all_pbleaves_pbbuild",
        "restrict_not_null",
        "restrict_unique_prefix",
    ],
    "jordan-curve-theorem-Jordan1.v-A_B_1_bis": [
        "eq_dim_dec",
        "eq_dart_dec",
        "eq_dart_dec",
        "eq_dim_dec",
        "eq_dart_dec",
        "eq_dim_dec",
    ],
    "jordan-curve-theorem-Jordan1.v-succ_pred_clos": [
        "eq_dart_dec",
        "eq_dim_dec",
        "eq_dart_dec",
        "eq_dart_dec",
        "not_exd_nil",
        "not_exd_nil",
        "not_exd_nil",
        "eq_dart_dec",
        "eq_dart_dec",
        "eq_dart_dec",
        "not_exd_nil",
        "eq_dart_dec",
        "eq_dart_dec",
        "not_exd_nil",
        "eq_dart_dec",
    ],
    "jordan-curve-theorem-Jordan10.v-A_L_B_top_bot_ter": ["A_B_ter", "A_B_ter"],
    "jordan-curve-theorem-Jordan10.v-eqc_bottom": [],
    "jordan-curve-theorem-Jordan3.v-eqc_exd_exd": [],
    "jordan-curve-theorem-Jordan7.v-expf_B0_CS_2_a_II": [
        "MF.expo_expo1",
        "MF.expo_expo1",
        "between_expf_B0_2",
        "between_expf_B0_2",
        "expf_trans",
        "expf_symm",
    ],
    "jordan-curve-theorem-Jordan7.v-inv_hmap_L0L1": [],
    "jordan-curve-theorem-Jordan8.v-nf_L0L1_VB": [
        "inv_hmap_L0L1",
        "exd_cA",
        "exd_cA_1",
        "expf_L1_CNS",
        "expf_dec",
        "expf_L0_CNS",
        "expf_dec",
        "eq_dart_dec",
        "eq_dart_dec",
        "eq_nat_dec",
        "eq_dart_dec",
        "eq_dart_dec",
        "cA_cA_1",
        "exd_cA",
        "cA_1_cA",
        "exd_cA_1",
        "exd_cA_1",
        "exd_cA_1",
        "expf_symm",
        "eq_dart_dec",
        "eq_dart_dec",
    ],
    "tree-automata-empty_test.v-dta_app_ne_inc_3": [
        "bool_is_tru_or_false",
        "Neqb_complete",
        "bool_is_true_or_false",
        "Neqb_correct",
    ],
    "tree-automata-empty_test.v-pl_non_empty_path_true_0": [],
    "tree-automata-lattice_fixpoint.v-iteres_dom_ok": [
        "prechain_sum",
        "domok_concat",
        "domok_concat",
    ],
    "tree-automata-lattice_fixpoint.v-iteres_last": [
        "prechain_sum",
    ],
    "tree-automata-semantics.v-invar_1_0": [
        "semantic_equiv_0_2",
        "semantic_equiv_0_4",
        "semantic_equiv_0_3",
    ],
    "tree-automata-signature.v-pl_compat_check_correct": ["pl_sum", "beq_nat_correct"],
    "tree-automata-signature.v-pl_tl_length_pl_compat": [],
    "tree-automata-union.v-mpl_compat_7_2": [],
    "tree-automata-union.v-u_conv0_4": [],
    "tree-automata-union.v-u_merge_2_4": [],
    "tree-automata-union.v-union_s0d_3": ["union_s0d_0"],
    "verdi-DupDropReordering.v-dup_drop_step_star_step_1": [
        "clos_rt_rtn1_iff",
        "clos_rt_rt1n_iff",
        "clos_rt_rt1n_iff",
        "clos_rt_rtn1_iff",
    ],
    "verdi-InverseTraceRelations.v-inverse_trace_relations_work": [
        "refl_trans_1n_n1_trace",
        "T_monotonic",
        "refl_trans_n1_1n_trace",
        "R_implies_T",
    ],
    "verdi-Net.v-refl_trans_1n_trace_trans": ["app_ass"],
    "verdi-PartialMapExecutionSimulations.v-pt_map_onet_hd_step_ordered_failure_star": [
        "step_ordered_failure_pt_mapped_simulation_star_1"
    ],
    "verdi-TotalMapSimulations.v-in_adjacent_exclude_in_exlude": [
        "remove_all_nil",
        "remove_all_cons",
        "adjacent_to_dec",
    ],
    #
    "verdi-raft-AllEntriesLeaderLogsProof.v-leaderLogs_leader_invariant": [
        "leaders_have_leaderLogs_strong_invariant"
    ],
    "verdi-raft-AllEntriesLeaderSublogProof.v-allEntries_leader_sublog_append_entries": [
        "update_elections_data_appendEntries_log_allEntries_leader",
        "update_elections_data_appendEntries_log_allEntries_leader",
        "update_elections_data_appendEntries_allEntries_term'",
        "lifted_leader_sublog_nw",
    ],
    "verdi-raft-AllEntriesLogProof.v-handleTimeout_currentTerm_leaderId": [],
    "verdi-raft-AppliedEntriesMonotonicProof.v-entries_max_thing": [
        "maxIndex_non_empty",
        "log_matching_invariant",
    ],
    "verdi-raft-AppliedEntriesMonotonicProof.v-sorted_app": [],
    "verdi-raft-AppliedImpliesInputProof.v-applied_implies_input_update_split": [],
    "verdi-raft-GhostLogsLogPropertiesProof.v-log_properties_hold_on_ghost_logs_do_leader": [
        "msg_log_property",
        "msg_log_property",
    ],
    "verdi-raft-InLogInAllEntriesProof.v-in_log_in_all_entries_append_entries_reply": [
        "handleAppendEntriesReply_log",
    ],
    "verdi-raft-LeaderLogsSortedProof.v-leaderLogs_sorted_client_request": [
        "leaderLogs_update_elections_data_client_request"
    ],
    "verdi-raft-NextIndexSafetyProof.v-nextIndex_safety_invariant": [
        "raft_net_invariant",
        "nextIndex_safety_init",
        "nextIndex_safety_client_request",
        "nextIndex_safety_timeout",
        "nextIndex_safety_append_entries",
        "nextIndex_safety_append_entries_reply",
        "nextIndex_safety_request_vote",
        "nextIndex_safety_request_vote_reply",
        "nextIndex_safety_do_leader",
        "nextIndex_safety_do_generic_server",
        "nextIndex_safety_state_same_packet_subset",
        "nextIndex_safety_reboot",
    ],
    "verdi-raft-OutputCorrectProof.v-getLastId_Some_In": [
        "assoc_Some_In",
    ],
    "verdi-raft-OutputCorrectProof.v-in_output_trace_inp_inv": [],
    "verdi-raft-PrevLogLeaderSublogProof.v-deghost_packet_exists": [],
    "verdi-raft-RefinementSpecLemmas.v-votesWithLog_update_elections_data_timeout": [],
    "verdi-raft-RefinementSpecLemmas.v-votes_same_append_entries": [],
    "verdi-raft-RefinementSpecLemmas.v-votes_update_elections_data_timeout_votedFor": [],
    "verdi-raft-RequestVoteReplyTermSanityProof.v-requestVoteReply_term_sanity_client_request": [
        "handleClientRequest_packets",
        "handleClientRequest_term_votedFor",
    ],
    "verdi-raft-RequestVoteReplyTermSanityProof.v-requestVoteReply_term_sanity_request_vote_reply": [
        "handleRequestVoteReply_currentTerm"
    ],
    "verdi-raft-SpecLemmas.v-handleAppendEntries_currentTerm_leaderId": [
        "advanceCurrentTerm_currentTerm"
    ],
    "verdi-raft-StateMachineSafetyPrimeProof.v-sorted_app_in_gt": [],
    "verdi-raft-StateMachineSafetyProof.v-lifted_maxIndex_sanity_do_generic_server": [
        "doGenericServer_log",
        "doGenericServer_lastApplied",
        "doGenericServer_commitIndex",
    ],
    "verdi-raft-TermsAndIndicesFromOneProof.v-terms_and_indices_from_one_vwl_request_vote_reply": [
        "votesWithLog_update_elections_data_request_vote_reply"
    ],
    "verdi-raft-VarDRaftSerializedCorrect.v-input_correct_filterMap_trace_non_empty_out": [
        "In_filterMap",
        "In_filterMap",
    ],
    "weak-up-to-Monotonic.v-Comp_mon": [
        "mon_m",
        "mon_m",
        "mon_t",
        "mon_t",
        "mon_m",
        "mon_a",
        "mon_t",
        "mon_a",
        "mon_m",
    ],
    "weak-up-to-Relations.v-comp_star_star": ["star_trans"],
    "zfc-Axioms.v-Union_IN": [
        "IN_sound_left",
    ],
    "zfc-zfc.v-CIN_EXType": [],
    "zorns-lemma-Cardinals.v-cardinals_unbounded": ["cantor_diag2"],
    "zorns-lemma-CountableTypes.v-positive_countable": ["nat_of_P_inj"],
    "zorns-lemma-FiniteTypes.v-True_finite": [
        "bij_finite",
        "True_rect",
        "True_rect",
        "refl_equal",
    ],
}

COQGYM_TEST_PERFECT_SUBGOALS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQGYM_TEST_PERFECT_SUBGOALS.pkl"
)
COQGYM_TEST_PERFECT_SUBGOALS_DATASET = [
    example
    for example in pickle.load(open(COQGYM_TEST_PERFECT_SUBGOALS_FILE, "rb"))
    if (not COQGYM_TEST_ZERO_SHOT_RESULTS.get(example.name, False))
    and (not COQGYM_TEST_COQHAMMER_RESULTS.get(example.name, False))
]
# endregion TEST
