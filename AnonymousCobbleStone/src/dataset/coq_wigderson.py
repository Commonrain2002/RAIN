import pickle
import json
from pathlib import Path
import typing as t

from src.dataset.dataset import Dataset, Example, LemmaLocation
from src.config import CONFIG

# region TEST

COQ_WIGDERSON_TEST_SAMPLED_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_WIGDERSON_TEST_SAMPLED_DATASET.pkl"
)

COQ_WIGDERSON_TEST_SAMPLED_DATASET: Dataset = pickle.load(
    open(COQ_WIGDERSON_TEST_SAMPLED_FILE, "rb")
)

COQ_WIGDERSON_TEST_PERFECT_PREFIX: t.Dict[str, str] = {
    "coq-wigderson-coloring.v-barbar": """intros g g' i j ci cj f H H0 H1 H2 H3 H4.
  generalize dependent g'.
  generalize dependent f.
  (* revert H2. *)
  functional induction (phase2 g) using phase2_ind.""",
    "coq-wigderson-coloring.v-coloring_max_deg_complete": "",
    "coq-wigderson-coloring.v-constant_col_indep_set": """intros g s c H.
  split.""",
    "coq-wigderson-coloring.v-constant_color_colors": """intros i Hi.
  unfold constant_color.
  generalize dependent Hi.
  apply SP.fold_rec_bis.""",
    "coq-wigderson-coloring.v-constant_color_inv": """intros i.
  unfold constant_color.
  apply SP.fold_rec_bis.""",
    "coq-wigderson-coloring.v-constant_color_inv2": """intros i d.
  unfold constant_color.
  apply SP.fold_rec_bis.""",
    "coq-wigderson-coloring.v-in_two_set_inv": "",
    "coq-wigderson-coloring.v-indep_set_union": """intros g f s p c H H0 H1 H2.
  split.""",
    "coq-wigderson-coloring.v-map_o": "",
    "coq-wigderson-coloring.v-max_deg_0_constant_col": """intros g c H.
  split.""",
    "coq-wigderson-coloring.v-max_deg_remove_node": "",
    "coq-wigderson-coloring.v-n_coloring_missed": """  intros [p3 Hf] Hc Hcm.
  unfold n_coloring.
  split.""",
    "coq-wigderson-coloring.v-nbd_not_2_col_graph_not_3_col": """""",
    "coq-wigderson-coloring.v-ok_coloring_set_eq": """""",
    "coq-wigderson-coloring.v-ok_coloring_subset": """""",
    "coq-wigderson-coloring.v-phase2": """""",
    "coq-wigderson-coloring.v-phase2_ok": """intros g H H0.
  functional induction (phase2 g) using phase2_ind.""",
    "coq-wigderson-coloring.v-phase_2_example": """split.""",
    "coq-wigderson-coloring.v-restrict_coloring_ok": """""",
    "coq-wigderson-coloring.v-siota_spec": """intros n i.
  split; intros H.""",
    "coq-wigderson-coloring.v-siota_subset": """""",
    "coq-wigderson-coloring.v-two_color_step_colors_adj_c2": """""",
    "coq-wigderson-coloring.v-two_color_step_correct": """intros g v c1 c2 Hc H Hu magic H0.
  split.""",
    "coq-wigderson-coloring.v-two_color_step_inv": """intros g v c1 c2 f ci j H.
  unfold two_color_step in H.
  destruct (E.eq_dec j v).""",
    "coq-wigderson-coloring.v-two_coloring_from_three": """""",
    "coq-wigderson-coloring.v-undirected_adj_in": """""",
    "coq-wigderson-graph.v-InA_map_fst_key": """""",
    "coq-wigderson-graph.v-Mcardinal_Scardinal": """intros A m s H.
  rewrite WP.cardinal_fold.
  revert s H.
  apply WP.fold_rec_bis.""",
    "coq-wigderson-graph.v-Mremove_elements": """""",
    "coq-wigderson-graph.v-Sin_domain": """intros A n g.
  unfold Mdomain.
  split.""",
    "coq-wigderson-graph.v-Snot_in_empty": """""",
    "coq-wigderson-graph.v-Sremove_elements": """Proof.
intros.
apply eqlistA_Eeq_eq.
apply SortE_equivlistE_eqlistE.""",
    "coq-wigderson-graph.v-adj_ext": """""",
    "coq-wigderson-graph.v-adj_map": """""",
    "coq-wigderson-graph.v-cardinal_map": """""",
    "coq-wigderson-graph.v-color_correct": """""",
    "coq-wigderson-graph.v-domain_example_map": """""",
    "coq-wigderson-graph.v-eqlistA_Eeq_eq": """split; intro.""",
    "coq-wigderson-graph.v-filter_sortE": """""",
    "coq-wigderson-graph.v-find_in_adj": """""",
    "coq-wigderson-graph.v-in_adj_exists": """intros g i j H.
  unfold adj in *.
  destruct M.find eqn:E in *.""",
    "coq-wigderson-graph.v-in_adj_in_nodes": """intros g i j.
  unfold adj.
  destruct M.find eqn:E; intros H.""",
    "coq-wigderson-graph.v-lt_proper": """""",
    "coq-wigderson-graph.v-subset_nodes_sub": """""",
    "coq-wigderson-munion.v-Mdisjoint_test1": """""",
    "coq-wigderson-munion.v-Munion_in": """intros i m1 m2.
  split.""",
    "coq-wigderson-restrict.v-adj_restrict": """intros g s i j.
  split.""",
    "coq-wigderson-restrict.v-restrict_agree": """intros m s k v.
  unfold restrict.
  apply SP.fold_rec_bis.""",
    "coq-wigderson-restrict.v-restrict_full": """""",
    "coq-wigderson-restrict.v-restrict_in_set2": """""",
    "coq-wigderson-restrict.v-restrict_map_comm": """intros m f s.
  apply WF.Equal_mapsto_iff.
  unfold M.MapsTo.
  intros k e.
  split; intros H.""",
    "coq-wigderson-restrict.v-restrict_spec": """intros A m s k.
  split; intros H.""",
    "coq-wigderson-restrict.v-restrict_subset_keys": """intros m s.
  unfold restrict.
  apply SP.fold_rec_bis.""",
    "coq-wigderson-subgraph.v-InA_in_iff": """""",
    "coq-wigderson-subgraph.v-adj_remove_nodes_spec": """""",
    "coq-wigderson-subgraph.v-degree_remove": """""",
    "coq-wigderson-subgraph.v-degree_subgraph": """""",
    "coq-wigderson-subgraph.v-empty_subgraph_is_subgraph": """unfold is_subgraph.
  split.""",
    "coq-wigderson-subgraph.v-extract_deg_vert_dec": """intros g d.
  destruct (extract_deg_vert g d) eqn:E.""",
    "coq-wigderson-subgraph.v-extract_vertices_deg": """""",
    "coq-wigderson-subgraph.v-extract_vertices_deg0_empty": """unfold remove_deg_n_graph.
  intros g.
  remember 0 as d.
  functional induction (extract_vertices_deg g d) using extract_vertices_deg_ind.""",
    "coq-wigderson-subgraph.v-extract_vertices_deg_exhaust": """unfold remove_deg_n_graph.
  functional induction (extract_vertices_deg g n) using extract_vertices_deg_ind.""",
    "coq-wigderson-subgraph.v-extract_vertices_deg_subgraph": """unfold remove_deg_n_graph.
  functional induction (extract_vertices_deg g n) using extract_vertices_deg_ind.""",
    "coq-wigderson-subgraph.v-extract_vertices_deg_subgraph1": """""",
    "coq-wigderson-subgraph.v-extract_vertices_degs": """""",
    "coq-wigderson-subgraph.v-extract_vertices_degs_empty": """intros g g' g'' d v s H H0 e0 H2 H3.
  rewrite extract_vertices_degs_equation in e0.
  destruct (extract_deg_vert_dec _ _).""",
    "coq-wigderson-subgraph.v-extract_vertices_degs_undirected": """intros g g' n ns Hg.
  generalize dependent ns.
  functional induction (extract_vertices_degs g n) using extract_vertices_degs_ind.""",
    "coq-wigderson-subgraph.v-extract_vertices_remove": """intros g g' s n.
  generalize dependent s.
  generalize dependent g'.
  functional induction (extract_vertices_degs g n) using extract_vertices_degs_ind.""",
    "coq-wigderson-subgraph.v-independent_set_add": """intros H H0 H1 H2.
  intros a b Ha Hb contra.
  unfold independent_set in H2.
  destruct (E.eq_dec a i), (E.eq_dec b i).""",
    "coq-wigderson-subgraph.v-independent_set_subgraph": """""",
    "coq-wigderson-subgraph.v-list_max_witness": """  intros l n.
  induction l.""",
    "coq-wigderson-subgraph.v-max_deg_gt_not_empty": """""",
    "coq-wigderson-subgraph.v-max_deg_max": """""",
    "coq-wigderson-subgraph.v-max_deg_subgraph": """intros g g' H.
  unfold max_deg.
  unfold is_subgraph in H.
  pose proof incl_Forall_in_iff.
  (* let d be the max degree of the original graph *)
  remember (list_max (map (fun p : M.key * S.t => S.cardinal (snd p)) (M.elements g))) as d.
  (* let d' be the max degree of subgraph *)
  remember (list_max (map (fun p : M.key * S.t => S.cardinal (snd p)) (M.elements g'))) as d'.
  (* when d' = 0 this is immediate, otherwise it's non-zero *)
  destruct d'; [hauto l: on|].
  assert (map (fun p : M.key * S.t => S.cardinal (snd p)) (M.elements g') <> []) by sauto.
  pose proof (list_max_witness _ (S d') H1 (eq_sym Heqd')).
  destruct H2 as [x [Hx Hx2]].
  rewrite in_map_iff in Hx.
  destruct Hx as [x' [Hx' Hx'']].
  destruct x'.
  subst.
  simpl in Hx2.
  apply M.elements_complete in Hx''.
  assert (M.In k g).
  {
    hauto lq: on rew: off use: subgraph_vert_m unfold: PositiveMap.MapsTo, nodeset.
  }
  destruct H2 as [e He].
  pose proof (max_deg_max g k e He).
  (* hfcrush use: SP.subset_cardinal, le_trans unfold: adj. *)
  apply le_trans with (m := S.cardinal e).""",
    "coq-wigderson-subgraph.v-max_deg_subgraph_inv": """intros g' g v H H0.
  unfold degree in H0.
  destruct (M.find v g') eqn:E; [|scongruence].
  inversion H0; clear H0.
  unfold degree.
  destruct (M.find v g) eqn:E2.""",
    "coq-wigderson-subgraph.v-max_degree_extraction_disjoint": """""",
    "coq-wigderson-subgraph.v-nbd_adj": """intros g i j H.
  unfold neighborhood in H.
  unfold neighbors in H.
  remember (adj g i) as s.
  apply subgraph_of_nodes with (g := g).
  destruct (E.eq_dec j i).""",
    "coq-wigderson-subgraph.v-nbd_not_include_vertex": """""",
    "coq-wigderson-subgraph.v-not_adj_removes": """intros g n p s H H0 H1.
  rewrite adj_remove_nodes_spec in H1.
  apply not_and in H1.""",
    "coq-wigderson-subgraph.v-remove_max_deg_adj": """intros g i j H0 H1 H2 H3 H4.
  remember (max_deg g) as d.
  assert (degree j (remove_node i g) = Some (max_deg g)) by (scongruence use: vertex_removed_nbs_dec).
  destruct d eqn:E.""",
    "coq-wigderson-subgraph.v-remove_max_deg_adj'": """""",
    "coq-wigderson-subgraph.v-remove_node_neq": """intros g i j H.
  split; intros H'.""",
    "coq-wigderson-subgraph.v-remove_node_neq2": """intros g i j H.
  unfold remove_node in H.
  apply WF.map_in_iff in H.
  destruct (E.eq_dec i j).""",
    "coq-wigderson-subgraph.v-remove_node_nodes_adj": """""",
    "coq-wigderson-subgraph.v-remove_node_subgraph": """intros g v.
  split.""",
    "coq-wigderson-subgraph.v-remove_node_undirected": """""",
    "coq-wigderson-subgraph.v-remove_nodes_lt": """intros g s i H H0.
  pose proof (remove_nodes_sub g s i H H0).
  unfold remove_nodes.
  rewrite cardinal_map.
  assert (~ S.Empty s) by (hauto l: on).
  rewrite restrict_cardinal.
  rewrite SP.inter_sym.
  rewrite SP.inter_subset_equal by apply SP.diff_subset.
  rewrite Mcardinal_domain.
  apply SP.subset_cardinal_lt with (x := i).""",
    "coq-wigderson-subgraph.v-remove_nodes_singleton": """intros g v.
  split.""",
    "coq-wigderson-subgraph.v-remove_nodes_sub": """""",
    "coq-wigderson-subgraph.v-subgraph_edges": """intros g s v.
  unfold subgraph_of.
  apply WP.fold_rec_bis.""",
    "coq-wigderson-subgraph.v-subgraph_of_is_subgraph": """""",
    "coq-wigderson-subgraph.v-subgraph_of_nodes": """""",
    "coq-wigderson-subgraph.v-subgraph_trans": """""",
    "coq-wigderson-subgraph.v-subgraph_vert_m": """""",
    "coq-wigderson-subgraph.v-subgraph_vertices_adj": """intros g s i.
  unfold subgraph_of.
  apply WP.fold_rec_bis.""",
    "coq-wigderson-subgraph.v-subgraph_vertices_set": """intros g s.
  unfold subgraph_of.
  apply WP.fold_rec_bis.""",
    "coq-wigderson-subgraph.v-vertex_removed_nbs_dec": """intros g i j n Hl H1 H2.
  unfold degree, adj in *.
  ssimpl.""",
    "coq-wigderson-wigderson.v-cardinal_remove": """intros g v m.
  unfold adj.
  destruct (WF.In_dec g v).""",
    "coq-wigderson-wigderson.v-selectW_terminates": """""",
    "coq-wigderson-wigderson.v-select_hi_deg": """intros n g v.
  functional induction (selectW n g) using selectW_ind.""",
    "coq-wigderson-wigderson.v-three_color_up_inj": """intros Hm Ug Hf.
  exists (M.map inj f).
  intros v.
  split.""",
}

COQ_WIGDERSON_TEST_PERFECT_PREMISE_NAMES: t.Dict[str, t.List[str]] = {
    "coq-wigderson-coloring.v-barbar": [
        "phase2_ind",
        "max_deg_0_adj",
        "extract_vertices_degs_undirected",
        "extract_vertices_degs_subgraph",
        "subgraph_no_selfloop",
        "Munion_case",
        "constant_color_inv",
        "max_degree_extraction_independent_set",
        "of_nat_surj",
        "phase2_color_bound",
        "constant_color_inv2",
        "extract_vertices_max_degs",
        "of_nat_surj",
        "phase2_color_bound",
        "constant_color_inv2",
        "extract_vertices_max_degs",
        "asfadsf",
    ],
    "coq-wigderson-coloring.v-coloring_max_deg_complete": [
        "constant_col_indep_set",
        "max_degree_extraction_independent_set",
    ],
    "coq-wigderson-coloring.v-constant_col_indep_set": [
        "Sin_domain",
        "subgraph_of_nodes",
        "constant_color_colors",
        "subgraph_of_is_subgraph",
        "indep_set_ok",
        "Sin_domain",
        "constant_color_inv",
        "constant_color_inv2",
        "S.singleton_2.",
    ],
    "coq-wigderson-coloring.v-constant_color_colors": [
        "SP.fold_rec_bis",
        "WF.add_o",
        "PositiveSet.add_3",
        "PositiveMap.gss",
    ],
    "coq-wigderson-coloring.v-constant_color_inv": [
        "SP.fold_rec_bis",
        "E.eq_dec",
        "PositiveSet.add_1",
        "SP.Dec.F.add_iff",
        "PositiveMap.gso",
    ],
    "coq-wigderson-coloring.v-constant_color_inv2": [
        "SP.fold_rec_bis",
        "E.eq_dec",
        "PositiveMap.gss",
        "PositiveMap.gso",
    ],
    "coq-wigderson-coloring.v-in_two_set_inv": [
        "PositiveSet.singleton_1",
        "PositiveSet.add_spec",
        "PositiveSet.cardinal_1",
    ],
    "coq-wigderson-coloring.v-indep_set_union": [
        "S.add_spec",
        "Munion_case",
        "constant_color_inv2",
        "Munion_case",
        "constant_color_inv",
        "constant_color_inv2",
        "constant_color_inv2",
    ],
    "coq-wigderson-coloring.v-map_o": ["WF.map_o"],
    "coq-wigderson-coloring.v-max_deg_0_constant_col": [
        "constant_color_colors",
        "Sin_domain",
        "max_deg_0_adj",
    ],
    "coq-wigderson-coloring.v-max_deg_remove_node": [
        "Arith.PeanoNat.Nat.nlt_0_r",
        "Wigderson.subgraph.remove_node_subgraph",
        "Wigderson.subgraph.max_deg_subgraph",
        "remove_node_subgraph",
        "max_deg_subgraph",
        "le_lt_or_eq",
        "remove_node_neq",
        "SP.remove_cardinal_2",
        "remove_node_find",
        "Znat.Nat2Z.inj_le",
        "Znat.Nat2Z.inj_gt",
    ],
    "coq-wigderson-coloring.v-n_coloring_missed": [
        "SP.remove_cardinal_1",
        "S.remove_spec",
    ],
    "coq-wigderson-coloring.v-nbd_not_2_col_graph_not_3_col": ["nbd_2_colorable_3"],
    "coq-wigderson-coloring.v-ok_coloring_set_eq": [],
    "coq-wigderson-coloring.v-ok_coloring_subset": [],
    "coq-wigderson-coloring.v-phase2": [
        "extract_vertices_degs_equation",
        "extract_deg_vert_dec",
        "SP.Dec.F.add_iff",
        "max_degree_vert",
        "max_deg_gt_not_empty",
        "nlt_0_r",
        "PositiveSet.choose_1",
        "PositiveSet.choose_2",
        "extract_vertices_degs_subgraph",
        "extract_vertices_remove",
        "Sin_domain",
        "Sin_domain",
        "Mcardinal_domain",
        "SP.subset_cardinal_lt",
    ],
    "coq-wigderson-coloring.v-phase2_ok": [
        "phase2_ind",
        "max_deg_0_adj",
        "extract_vertices_degs_undirected",
        "extract_vertices_degs_subgraph",
        "subgraph_no_selfloop",
        "max_degree_extraction_independent_set",
        "extract_vertices_max_degs",
        "nlt_0_r",
        "siota_subset",
        "siota_miss",
        "SP.Dec.F.mem_iff",
        "SP.Dec.F.singleton_iff",
        "PositiveSet.inter_spec",
        "constant_color_inv2",
        "PositiveSet.singleton_2",
        "constant_color_inv",
        "constant_color_inv",
        "of_nat_surj",
        "siota_spec",
        "phase2_color_bound",
        "adfadsf",
        "indep_set_union",
        "S.add_spec",
        "siota_spec",
        "ok_coloring_subset",
    ],
    "coq-wigderson-coloring.v-phase_2_example": [
        "M.elements_correct",
        "M.elements_correct",
    ],
    "coq-wigderson-coloring.v-restrict_coloring_ok": ["restrict_agree"],
    "coq-wigderson-coloring.v-siota_spec": [
        "SP.of_list_1",
        "InA_iff",
        "in_map_iff",
        "in_seq",
        "SP.of_list_1",
        "InA_iff",
        "in_map_iff",
        "in_seq",
    ],
    "coq-wigderson-coloring.v-siota_subset": ["of_nat_surj", "siota_spec"],
    "coq-wigderson-coloring.v-two_color_step_colors_adj_c2": ["constant_color_colors"],
    "coq-wigderson-coloring.v-two_color_step_correct": [
        "PositiveMap.gss",
        "PositiveSet.add_1",
        "M.gso",
        "constant_color_inv",
        "constant_color_colors",
        "PositiveSet.add_2",
        "PositiveSet",
        "two_color_step_colors_v_c1",
        "two_color_step_colors_adj_c2",
        "two_color_step_colors_v_c1",
        "WF.empty_in_iff",
        "E.eq_dec",
        "two_color_step_inv",
        "two_color_step_inv",
        "two_color_step_colors_adj_c2",
        "two_color_step_colors_adj_c2",
        "two_color_step_colors_adj_c2",
        "undirected_adj_in",
        "undirected_adj_in",
        "undirected_adj_in",
        "in_two_set_inv",
        "in_two_set_inv",
        "in_two_set_inv",
    ],
    "coq-wigderson-coloring.v-two_color_step_inv": [
        "E.eq_dec",
        "M.gso",
        "WF.in_find_iff",
        "constant_color_inv",
    ],
    "coq-wigderson-coloring.v-two_coloring_from_three": [
        "n_coloring_missed",
    ],
    "coq-wigderson-coloring.v-undirected_adj_in": ["SP.Dec.F.empty_iff"],
    #
    "coq-wigderson-graph.v-InA_map_fst_key": [],
    "coq-wigderson-graph.v-Mcardinal_Scardinal": [
        "WP.cardinal_fold",
        "WP.fold_rec_bis",
        "WF.In_m",
        "SP.cardinal_1",
        "WF.empty_in_iff",
        "SP.add_remove",
        "WF.add_in_iff",
        "SP.add_cardinal_2",
        "S.remove_spec",
        "S.remove_spec",
        "WF.add_in_iff",
    ],
    "coq-wigderson-graph.v-Sin_domain": [
        "M.fold_1",
        "fold_right_rev_left",
        "WP.fold_spec_right",
        "WP.fold_rec_bis",
        "WF.In_m",
        "E.eq_dec",
        "WF.add_in_iff",
        "PositiveSet.add_3",
        "WF.add_neq_in_iff",
        "WP.fold_rec_bis",
        "WP.F.In_m",
        "WF.Equal_sym",
        "PositiveSet.add_spec",
        "diff_false_true",
        "WF.add_neq_in_iff",
        "PositiveSet.add_2",
    ],
    "coq-wigderson-graph.v-Snot_in_empty": [],
    "coq-wigderson-graph.v-Sremove_elements": [
        "eqlistA_Eeq_eq",
        "SortE_equivlistE_eqlistE",
        "PositiveSet.elements_3",
        "filter_sortE",
        "PositiveSet.elements_3",
        "filter_InA",
        "Proper_eq_eq",
        "S.remove_1",
        "S.remove_2",
        "S.remove_3",
        "S.elements_1",
        "S.elements_2",
    ],
    "coq-wigderson-graph.v-adj_ext": [],
    "coq-wigderson-graph.v-adj_map": [
        "WF.map_o",
    ],
    "coq-wigderson-graph.v-cardinal_map": [
        "M.elements_1",
        "M.elements_2",
        "M.elements_3",
        "map_length",
        "eqlistA_length",
        "SortE_equivlistE_eqlistE",
        "InA_map_fst_key",
        "WF.map_mapsto_iff",
        "Sorted_lt_key",
        "M.cardinal_1",
        "SortE_equivlistE_eqlistE",
    ],
    "coq-wigderson-graph.v-domain_example_map": [],
    "coq-wigderson-graph.v-eqlistA_Eeq_eq": [],
    "coq-wigderson-graph.v-filter_sortE": ["filter_sort"],
    "coq-wigderson-graph.v-find_in_adj": [],
    "coq-wigderson-graph.v-in_adj_exists": ["SP.FM.empty_iff"],
    "coq-wigderson-graph.v-in_adj_in_nodes": ["Sin_domain", "SP.FM.empty_iff"],
    "coq-wigderson-graph.v-lt_proper": ["M.ME.MO.IsTO.lt_compat"],
    "coq-wigderson-graph.v-subset_nodes_sub": ["WP.filter_iff", "Sin_domain"],
    "coq-wigderson-munion.v-Mdisjoint_test1": [],
    "coq-wigderson-munion.v-Munion_in": [
        "WP.F.not_find_mapsto_iff",
        "Munion_case",
        "WP.fold_rec_bis",
        "E.eq_dec",
        "PositiveMap.gss",
        "PositiveMap.gso",
        "WF.add_neq_in_iff",
        "WP.fold_rec_bis",
        "E.eq_dec",
        "PositiveMap.gss",
        "PositiveMap.gso",
        "WF.add_neq_in_iff",
    ],
    "coq-wigderson-restrict.v-adj_restrict": [
        "in_adj_exists",
        "restrict_in_set",
        "restrict_agree",
        "find_in_adj",
        "in_adj_exists",
        "find_in_adj",
        "restrict_agree_2",
    ],
    "coq-wigderson-restrict.v-restrict_agree": [
        "SP.fold_rec_bis",
        "E.eq_dec",
        "PositiveMap.gss",
        "PositiveMap.gso",
    ],
    "coq-wigderson-restrict.v-restrict_full": ["restrict_restricts", "Sin_domain"],
    "coq-wigderson-restrict.v-restrict_in_set2": ["restrict_in_set"],
    "coq-wigderson-restrict.v-restrict_map_comm": [
        "WF.Equal_mapsto_iff",
        "WF.map_o",
        "restrict_in_set",
        "restrict_agree",
        "restrict_agree_2",
        "restrict_agree_2",
        "WF.map_o",
        "WF.map_o",
        "restrict_in_set",
        "restrict_agree_2",
    ],
    "coq-wigderson-restrict.v-restrict_spec": [
        "restrict_incl",
        "restrict_in_set2",
        "restrict_restricts",
    ],
    "coq-wigderson-restrict.v-restrict_subset_keys": [
        "SP.fold_rec_bis",
        "E.eq_dec",
        "Sin_domain",
        "WF.add_neq_in_iff",
        "Sin_domain",
    ],
    "coq-wigderson-subgraph.v-InA_in_iff": [],
    "coq-wigderson-subgraph.v-adj_remove_nodes_spec": [
        "adj_map",
        "S.diff_spec",
        "adj_restrict",
        "S.diff_spec",
        "in_adj_in_nodes",
    ],
    "coq-wigderson-subgraph.v-degree_remove": ["degree_gt_0_in", "remove_node_neq2"],
    "coq-wigderson-subgraph.v-degree_subgraph": ["SP.subset_cardinal"],
    "coq-wigderson-subgraph.v-empty_subgraph_is_subgraph": ["PositiveMap.gempty"],
    "coq-wigderson-subgraph.v-extract_deg_vert_dec": [
        "find_some",
        "InA_in_iff",
        "WF.elements_mapsto_iff",
        "M.find",
        "InA_in_iff",
        "WF.elements_mapsto_iff",
        "find_none",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_deg": [
        "cardinal_map",
        "Mremove_cardinal_less",
        "degree_gt_0_in",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_deg0_empty": [
        "extract_vertices_deg_ind",
        "max_deg_subgraph",
        "remove_node_subgraph",
        "max_deg_0_all_0",
        "extract_vertices_deg_equation",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_deg_exhaust": [
        "extract_vertices_deg_ind",
        "degree_gt_0_in",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_deg_subgraph": [
        "extract_vertices_deg_ind",
        "remove_node_subgraph",
        "subgraph_trans",
        "subgraph_refl",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_deg_subgraph1": [
        "extract_vertices_deg_equation",
        "remove_node_subgraph",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_degs": [
        "cardinal_map",
        "Mremove_cardinal_less",
        "degree_gt_0_in",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_degs_empty": [
        "extract_vertices_degs_equation",
        "extract_deg_vert_dec",
        "degree_gt_0_in",
        "max_deg_subgraph_inv",
        "max_deg_max",
        "max_deg_max",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_degs_undirected": [
        "extract_vertices_degs_ind",
        "remove_node_undirected",
    ],
    "coq-wigderson-subgraph.v-extract_vertices_remove": [
        "extract_vertices_degs_ind",
        "S.add_spec",
        "extract_vertices_degs_subgraph",
        "degree_gt_0_in",
        "remove_node_not_in",
        "subgraph_vert_m",
        "remove_node_subgraph",
    ],
    "coq-wigderson-subgraph.v-independent_set_add": [
        "E.eq_dec",
        "E.eq_dec",
        "PositiveSet.add_3",
        "PositiveSet.add_3",
        "PositiveSet.add_3",
    ],
    "coq-wigderson-subgraph.v-independent_set_subgraph": [],
    "coq-wigderson-subgraph.v-list_max_witness": ["list_max_app", "max_dec"],
    "coq-wigderson-subgraph.v-max_deg_gt_not_empty": [
        "max_deg_empty",
        "WP.elements_Empty",
    ],
    "coq-wigderson-subgraph.v-max_deg_max": [
        "M.elements_correct",
        "list_max_le",
        "map_map",
        "in_map",
        "Forall_forall",
    ],
    "coq-wigderson-subgraph.v-max_deg_subgraph": [
        "incl_Forall_in_iff",
        "list_max_witness",
        "in_map_iff",
        "M.elements_complete",
        "subgraph_vert_m",
        "max_deg_max",
        "le_trans",
        "SP.subset_cardinal",
    ],
    "coq-wigderson-subgraph.v-max_deg_subgraph_inv": [
        "max_deg_max",
        "proj2",
        "SP.subset_cardinal",
        "subgraph_vert_m",
    ],
    "coq-wigderson-subgraph.v-max_degree_extraction_disjoint": [
        "extract_vertices_remove",
        "SP.Dec.F.inter_iff",
    ],
    "coq-wigderson-subgraph.v-nbd_adj": [
        "subgraph_of_nodes",
        "Sin_domain",
        "remove_node_neq2",
        "Sin_domain",
        "remove_node_neq",
    ],
    "coq-wigderson-subgraph.v-nbd_not_include_vertex": ["WF.map_o"],
    "coq-wigderson-subgraph.v-not_adj_removes": [
        "adj_remove_nodes_spec",
        "not_and",
        "SP.In_dec",
        "not_and",
        "SP.In_dec",
        "dec_not",
    ],
    "coq-wigderson-subgraph.v-remove_max_deg_adj": [
        "vertex_removed_nbs_dec",
        "max_deg_0_adj",
        "vertex_removed_nbs_dec",
        "n_Sn",
    ],
    "coq-wigderson-subgraph.v-remove_max_deg_adj'": [
        "vertex_removed_nbs_dec",
        "remove_max_deg_adj",
        "degree_remove",
    ],
    "coq-wigderson-subgraph.v-remove_node_neq": [
        "WF.map_in_iff",
        "WP.F.remove_neq_in_iff",
        "WF.map_in_iff",
        "WP.F.remove_neq_in_iff",
    ],
    "coq-wigderson-subgraph.v-remove_node_neq2": [
        "WF.map_in_iff",
        "E.eq_dec",
        "M.remove_1",
    ],
    "coq-wigderson-subgraph.v-remove_node_nodes_adj": [
        "remove_nodes_singleton",
    ],
    "coq-wigderson-subgraph.v-remove_node_subgraph": [
        "Sin_domain",
        "Sin_domain",
        "E.eq_dec",
        "WF.map_in_iff",
        "M.remove_1",
        "remove_node_neq",
        "remove_node_neq2",
        "remove_node_neq",
        "WF.map_o",
        "WF.map_o",
        "WF.map_o",
        "M.gro",
        "PositiveSet.remove_3",
    ],
    "coq-wigderson-subgraph.v-remove_node_undirected": ["adj_remove_node_spec"],
    "coq-wigderson-subgraph.v-remove_nodes_lt": [
        "remove_nodes_sub",
        "cardinal_map",
        "restrict_cardinal",
        "SP.inter_sym",
        "SP.inter_subset_equal",
        "Mcardinal_domain",
        "SP.subset_cardinal_lt",
        "SP.diff_subset",
        "Sin_domain",
        "S.diff_spec",
    ],
    "coq-wigderson-subgraph.v-remove_nodes_singleton": [
        "WF.map_in_iff",
        "restrict_spec",
        "S.diff_spec",
        "PositiveSet.singleton_2",
        "WF.remove_neq_in_iff",
        "WF.remove_in_iff",
        "WF.remove_neq_in_iff",
        "Sin_domain",
        "WF.remove_neq_in_iff",
        "SP.Dec.F.singleton_iff",
        "WF.map_o",
        "E.eq_dec",
        "M.grs",
        "M.gro",
        "restrict_agree_2",
        "SP.remove_diff_singleton",
        "S.diff_spec",
        "Sin_domain",
        "PositiveSet.singleton_1",
    ],
    "coq-wigderson-subgraph.v-remove_nodes_sub": [
        "WF.map_in_iff",
        "M.MapsTo",
        "restrict_in_set",
        "Sin_domain",
        "S.diff_spec",
    ],
    "coq-wigderson-subgraph.v-subgraph_edges": [
        "WP.fold_rec_bis",
        "PositiveMap.gss",
        "SP.Dec.F.inter_iff",
        "E.eq_dec",
        "PositiveMap.gso",
    ],
    "coq-wigderson-subgraph.v-subgraph_of_is_subgraph": [
        "subgraph_vertices",
        "subgraph_edges",
    ],
    "coq-wigderson-subgraph.v-subgraph_of_nodes": ["subgraph_vertices_set"],
    "coq-wigderson-subgraph.v-subgraph_trans": [],
    "coq-wigderson-subgraph.v-subgraph_vert_m": ["Sin_domain"],
    "coq-wigderson-subgraph.v-subgraph_vertices_adj": [
        "WP.fold_rec_bis",
        "SP.Dec.F.inter_iff",
        "PositiveMap.gss",
        "PositiveMap.gso",
    ],
    "coq-wigderson-subgraph.v-subgraph_vertices_set": [
        "WP.fold_rec_bis",
        "Sin_domain",
        "E.eq_dec",
        "WP.F.add_neq_in_iff",
        "Sin_domain",
    ],
    "coq-wigderson-subgraph.v-vertex_removed_nbs_dec": [
        "remove_node_find",
        "SP.remove_cardinal_1",
        "remove_node_neq",
    ],
    "coq-wigderson-wigderson.v-cardinal_remove": [
        "WF.In_dec",
        "E.eq_dec",
        "map_o",
        "M.grs" "map_o",
        "M.gro",
        "SP.subset_cardinal",
        "PositiveSet.remove_3",
        "remove_node_subgraph",
        "SP.subset_cardinal",
    ],
    "coq-wigderson-wigderson.v-selectW_terminates": [
        "remove_node_neq2",
        "S.choose_1",
        "subset_nodes_sub",
        "Sin_domain",
        "cardinal_map",
        "Mremove_cardinal_less",
    ],
    "coq-wigderson-wigderson.v-select_hi_deg": [
        "selectW_ind",
        "PositiveSet.choose_1",
        "subset_nodes_prop",
        "le_gt_trans",
        "cardinal_remove",
    ],
    "coq-wigderson-wigderson.v-three_color_up_inj": [
        "M.map_2",
        "map_o",
        "PositiveSet.add_2",
        "PositiveSet.add_1",
        "M.map_2",
        "M.map_2",
        "map_o",
        "map_o",
    ],
}

COQ_WIGDERSON_TEST_ZERO_SHOT_RESULTS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_WIGDERSON_TEST_ZERO_SHOT_RESULTS.json"
)

COQ_WIGDERSON_TEST_ZERO_SHOT_RESULTS: t.Dict[str, bool] = json.load(
    open(COQ_WIGDERSON_TEST_ZERO_SHOT_RESULTS_FILE, "r")
)

COQ_WIGDERSON_TEST_COQHAMMER_RESULTS_FILE: Path = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_WIGDERSON_TEST_COQHAMMER_RESULTS.json"
)
COQ_WIGDERSON_TEST_COQHAMMER_RESULTS: t.Dict[str, bool] = json.load(
    open(COQ_WIGDERSON_TEST_COQHAMMER_RESULTS_FILE, "r")
)

COQ_WIGDERSON_TEST_SAMPLED_DATASET_BASELINES_FAIL = [
    example
    for example in COQ_WIGDERSON_TEST_SAMPLED_DATASET
    if (not COQ_WIGDERSON_TEST_ZERO_SHOT_RESULTS.get(example.name, False))
    and (not COQ_WIGDERSON_TEST_COQHAMMER_RESULTS.get(example.name, False))
]

COQ_WIGDERSON_TEST_PERFECT_SUBGOALS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_WIGDERSON_TEST_PERFECT_SUBGOALS.pkl"
)
COQ_WIGDERSON_TEST_PERFECT_SUBGOALS_DATASET = [
    example
    for example in pickle.load(open(COQ_WIGDERSON_TEST_PERFECT_SUBGOALS_FILE, "rb"))
    if (not COQ_WIGDERSON_TEST_ZERO_SHOT_RESULTS.get(example.name, False))
    and (not COQ_WIGDERSON_TEST_COQHAMMER_RESULTS.get(example.name, False))
]
# endregion TEST

# region DEv

COQ_WIGDERSON_DEV_SAMPLED_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_WIGDERSON_DEV_SAMPLED_DATASET.pkl"
)

COQ_WIGDERSON_DEV_SAMPLED_DATASET: Dataset = pickle.load(
    open(COQ_WIGDERSON_DEV_SAMPLED_FILE, "rb")
)


COQ_WIGDERSON_DEV_ZERO_SHOT_RESULTS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_WIGDERSON_DEV_ZERO_SHOT_RESULTS.json"
)

COQ_WIGDERSON_DEV_ZERO_SHOT_RESULTS: t.Dict[str, bool] = json.load(
    open(COQ_WIGDERSON_DEV_ZERO_SHOT_RESULTS_FILE, "r")
)

COQ_WIGDERSON_DEV_SAMPLED_DATASET_BASELINES_FAIL = [
    example
    for example in COQ_WIGDERSON_DEV_SAMPLED_DATASET
    if (not COQ_WIGDERSON_DEV_ZERO_SHOT_RESULTS[example.name])
]

COQ_WIGDERSON_DEV_PERFECT_SUBGOALS_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_WIGDERSON_DEV_PERFECT_SUBGOALS.pkl"
)
COQ_WIGDERSON_DEV_PERFECT_SUBGOALS_DATASET = [
    example
    for example in pickle.load(open(COQ_WIGDERSON_DEV_PERFECT_SUBGOALS_FILE, "rb"))
    if (not COQ_WIGDERSON_DEV_ZERO_SHOT_RESULTS.get(example.name, False))
]

# initial decomposition from gold standard proof
COQ_WIGDERSON_DEV_PERFECT_PREFIX: t.Dict[str, str] = {
    "coq-wigderson-coloring.v-subgraph_coloring_ok": "",
    "coq-wigderson-coloring.v-nbd_2_colorable_3": "",
    "coq-wigderson-coloring.v-nbd_not_n_col_graph_not_Sn_col": "",
    "coq-wigderson-coloring.v-indep_set_ok": """intros g s p m H H0 H1.
  split.""",
    "coq-wigderson-coloring.v-phase2_color_bound": """intros g f g' i n H H0.
  generalize dependent g'.
  generalize dependent f.
  functional induction (phase2 g) using phase2_ind.""",
    "coq-wigderson-graph.v-Sremove_cardinal_less": "",
    "coq-wigderson-graph.v-Mremove_cardinal_less": """intros A i s H.
rewrite WP.cardinal_fold.
rewrite WP.cardinal_fold.
apply WP.fold_rec_bis.""",
    "coq-wigderson-munion.v-Munion_case": """  intros c d i.
  unfold Munion.
  apply WP.fold_rec_bis.""",
    "coq-wigderson-restrict.v-restrict_incl": "",
    "coq-wigderson-restrict.v-restrict_in_set": """  intros m s k v.
  unfold restrict.
  apply SP.fold_rec_bis.""",
    "coq-wigderson-subgraph.v-remove_node_not_in": "",
    # this one doesn't really have a meaningful decomposition. you just need to rewrite it in with the right lemmas
    "coq-wigderson-subgraph.v-adj_remove_node_spec": "",
    "coq-wigderson-subgraph.v-remove_nodes_undirected": "",
    "coq-wigderson-subgraph.v-nbd_subgraph": "",
    "coq-wigderson-subgraph.v-max_deg_empty": "",
    "coq-wigderson-subgraph.v-inl_in": "split.",
    "coq-wigderson-subgraph.v-extract_vertices_deg_series": """unfold remove_deg_n_trace.
  functional induction (extract_vertices_deg g n) using extract_vertices_deg_ind.""",
    # this one also basically proceeds in a straight line. no subgoals
    "coq-wigderson-wigderson.v-subset_nodes_prop": "",
    # this one is admitted
    "coq-wigderson-wigderson.v-two_color_nbd_fail_n3_col": "",
    "coq-wigderson-wigderson.v-two_color_up_inj": """intros Hm Ug Hf.
  exists (M.map inj f).
  intros v.
  split.""",
}

# just the premise names from the first decomp
COQ_WIGDERSON_DEV_PERFECT_PREMISE_NAMES_FIRST_DECOMPOSITION = {
    "coq-wigderson-coloring.v-subgraph_coloring_ok": [],
    "coq-wigderson-coloring.v-nbd_2_colorable_3": [],
    "coq-wigderson-coloring.v-nbd_not_n_col_graph_not_Sn_col": [],
    "coq-wigderson-coloring.v-indep_set_ok": [],
    "coq-wigderson-coloring.v-phase2_color_bound": ["phase2_ind"],
    "coq-wigderson-graph.v-Sremove_cardinal_less": [],
    "coq-wigderson-graph.v-Mremove_cardinal_less": [
        "WP.cardinal_fold",
        "WP.fold_rec_bis",
    ],
    "coq-wigderson-munion.v-Munion_case": [
        "WP.fold_rec_bis",
    ],
    "coq-wigderson-restrict.v-restrict_incl": [],
    "coq-wigderson-restrict.v-restrict_in_set": [
        "SP.fold_rec_bis",
    ],
    "coq-wigderson-subgraph.v-remove_node_not_in": [],
    "coq-wigderson-subgraph.v-adj_remove_node_spec": [
        "remove_node_nodes_adj",
        "adj_remove_nodes_spec",
        "SP.Dec.F.singleton_iff",
        "PositiveSet.singleton_1",
    ],
    "coq-wigderson-subgraph.v-remove_nodes_undirected": [],
    "coq-wigderson-subgraph.v-nbd_subgraph": [],
    "coq-wigderson-subgraph.v-max_deg_empty": [],
    "coq-wigderson-subgraph.v-inl_in": [],
    "coq-wigderson-subgraph.v-extract_vertices_deg_series": [
        "extract_vertices_deg",
        "extract_vertices_deg_ind",
    ],
    "coq-wigderson-wigderson.v-subset_nodes_prop": [
        "Sin_domain",
        "WP.filter_iff",
    ],
    "coq-wigderson-wigderson.v-two_color_nbd_fail_n3_col": [],
    "coq-wigderson-wigderson.v-two_color_up_inj": [
        "M.map",
    ],
}

COQ_WIGDERSON_DEV_PERFECT_PREMISE_NAMES: t.Dict[str, t.List[str]] = {
    "coq-wigderson-coloring.v-subgraph_coloring_ok": [
        "PositiveSet.Subset",
        "coloring_ok",
        "is_subgraph",
    ],
    "coq-wigderson-coloring.v-nbd_2_colorable_3": [
        "SP.remove_cardinal_1",
        "nbd_Sn_colorable_n",
    ],
    "coq-wigderson-coloring.v-nbd_not_n_col_graph_not_Sn_col": [
        "nbd_Sn_colorable_n",
    ],
    "coq-wigderson-coloring.v-indep_set_ok": [
        "subgraph_edges",
        "WF.in_find_iff",
        "PositiveSet.Subset",
    ],
    "coq-wigderson-coloring.v-phase2_color_bound": [
        "phase2_ind",
        "constant_color_inv2",
        "extract_vertices_degs_subgraph",
        "max_deg_subgraph",
    ],
    "coq-wigderson-graph.v-Sremove_cardinal_less": [
        "SP.remove_cardinal_1",
        "le_n",
        "lt",
    ],
    "coq-wigderson-graph.v-Mremove_cardinal_less": [
        "WP.cardinal_fold",
        "WP.fold_rec_bis",
        "WP.cardinal_Empty",
        "neq_0_lt",
        "PositiveMap.Empty",
        "PositiveMap.In",
    ],
    "coq-wigderson-munion.v-Munion_case": [
        "WP.fold_rec_bis",
        "PositiveMap.MapsTo",
        "PositiveMap.In",
        "PositiveMap.Equal",
        "PositiveMap.gss",
        "E.eq_dec",
        "PositiveMapAdditionalFacts.gsident",
        "WF.add_neq_o",
    ],
    "coq-wigderson-restrict.v-restrict_incl": [
        "restrict_subset_keys",
        "Sin_domain",
        "PositiveSet.Subset",
        "PositiveSet.elt",
        "PositiveMap.key",
    ],
    "coq-wigderson-restrict.v-restrict_in_set": [
        "SP.fold_rec_bis",
        "E.eq_dec",
        "PositiveSet.add_1",
        "PositiveSet.add_2",
        "PositiveMap.gso",
        "PositiveMap.key",
        "PositiveSet.elt",
    ],
    "coq-wigderson-subgraph.v-remove_node_not_in": [
        "remove_node_neq2",
        "subgraph_vert_m",
    ],
    "coq-wigderson-subgraph.v-adj_remove_node_spec": [
        "remove_node_nodes_adj",
        "adj_remove_nodes_spec",
        "SP.Dec.F.singleton_iff",
        "PositiveSet.singleton_1",
        "PositiveOrderedTypeBits.t",
        "PositiveSet.elt",
    ],
    "coq-wigderson-subgraph.v-remove_nodes_undirected": [
        "adj_remove_nodes_spec",
    ],
    "coq-wigderson-subgraph.v-nbd_subgraph": [
        "subgraph_of_is_subgraph",
        "remove_node_subgraph",
        "subgraph_trans",
    ],
    "coq-wigderson-subgraph.v-max_deg_empty": [],
    "coq-wigderson-subgraph.v-inl_in": [],
    "coq-wigderson-subgraph.v-extract_vertices_deg_series": [
        "extract_vertices_deg",
        "extract_vertices_deg_ind",
        "sg_cons",
        "extract_vertices_deg_subgraph1",
    ],
    "coq-wigderson-wigderson.v-subset_nodes_prop": [
        "Sin_domain",
        "WP.filter_iff",
    ],
    "coq-wigderson-wigderson.v-two_color_nbd_fail_n3_col": [],
    "coq-wigderson-wigderson.v-two_color_up_inj": [
        "M.map",
        "M.In",
        "M.map_2",
        "M.MapsTo",
        "coloring_ok",
        "map_o",
        "option_map",
        "M.find",
        "PositiveSet.add_2",
        "PositiveSet.add_1",
        "PositiveSet.elt",
    ],
}

WIGDERSON_ADJ_REMOVE_NODE_SPEC_SECOND_GOAL = Example(
    LemmaLocation(
        project_name="coq-wigderson",
        file_name="subgraph.v",
        lemma_name="adj_remove_node_spec",
        section_names=[],
        coq_version="8.13",
    ),
    proposition_command="""Lemma adj_remove_node_spec : forall g v i j,
    S.In i (adj (remove_node v g) j) <-> S.In i (adj g j) /\ i <> v /\ j <> v.""",
    gold_standard_proof="""  intros g s i j.
  rewrite <- remove_node_nodes_adj.
  rewrite adj_remove_nodes_spec.
  sfirstorder use: SP.Dec.F.singleton_iff, PositiveSet.singleton_1 unfold: PositiveOrderedTypeBits.t, PositiveSet.elt, node.""",
    proof_prefix="""split; intros H.
- split.
-- strivial use: remove_node_subgraph unfold: is_subgraph, PositiveSet.Subset.
-- split.
--- qauto use: adj_remove_nodes_spec, PositiveSet.singleton_2, remove_node_nodes_adj unfold: PositiveSet.Equal, nodeset.
--- qauto use: in_adj_exists, remove_node_neq2 unfold: PositiveSet.mem, PositiveSet.In, nodeset, PositiveMap.MapsTo, PositiveSet.t, PositiveOrderedTypeBits.t, adj, PositiveSet.empty, PositiveMap.In, PositiveMap.key, node.
- """,
)

COQ_WIGDERSON_ERROR_ANALYSIS_DATASET = [
    WIGDERSON_ADJ_REMOVE_NODE_SPEC_SECOND_GOAL,
]

# endregion DEV
