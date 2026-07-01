#!/usr/bin/env python3
"""Recompute the numeric results reported in the Evaluation section.

The script reads the checked-in CSV/XLSX/JSON artifacts under Result/,
CoqStoqStep/, and CoqGymStep/.  It intentionally mirrors the paper's accounting:

* DeepSeek-v4-flash cost:
  cache-hit input / cache-miss input / output =
  0.0028 / 0.14 / 0.28 USD per million tokens.
* GPT-5.4 cost:
  cache-hit input / cache-miss input / output =
  0.25 / 2.50 / 15.00 USD per million tokens.
* Qwen3.5-Flash comparisons use total tokens, reported in million tokens.
* Shared-solved cost/time tables select theorems where both systems solve the
  theorem at least once, average all 10 trials within each theorem, then
  average those theorem-level values.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

DEEPSEEK_PRICES = {
    "cache_hit": 0.0028,
    "cache_miss": 0.14,
    "output": 0.28,
}

GPT_PRICES = {
    "cache_hit": 0.25,
    "cache_miss": 2.50,
    "output": 15.00,
}

COBBLESTONE_INTERSECTION_TARGETS = tuple(
    line.strip()
    for line in """
PnVRocqLib-Aczel.v-extenesionality
PnVRocqLib-Aczel.v-fromAcc_member_fromAcc_intro
PnVRocqLib-Aczel.v-indexed_union_isOrdinal
PnVRocqLib-Aczel.v-intersection_spec
PnVRocqLib-Aczel.v-rLe_eqTree_rLe
PnVRocqLib-Aczel.v-succ_isOrdinal
PnVRocqLib-Aczel.v-unions_isOrdinal
PnVRocqLib-Aczel.v-upair_spec
PnVRocqLib-BasicFol.v-frm_is_fresh_in_subst_iff
PnVRocqLib-BasicFol.v-fvs_frm_compat_similarity
PnVRocqLib-BasicFol.v-interpret_frm_ext_upto
PnVRocqLib-BasicFol.v-not_free_no_effect_on_interpret_frm
PnVRocqLib-BasicFol.v-one_subst_cons_subst
PnVRocqLib-BasicFol.v-vec_to_trms_to_vec
PnVRocqLib-BasicFol2.v-Henkin_axiom_is_of_form
PnVRocqLib-BasicFol2.v-Henkin_constant_does_not_occur_in_any_former_Henkin_axioms
PnVRocqLib-BasicFol2.v-cons_hsubst_hsubst_frm
PnVRocqLib-BasicFol2.v-distr_hcompose_one
PnVRocqLib-BasicFol2.v-last_HC_gt_frm
PnVRocqLib-BasicFol2.v-restrict_structure_frm
PnVRocqLib-BasicFol2.v-twilight_frm_spec
PnVRocqLib-BasicFol2.v-untwilight_frm
PnVRocqLib-BooleanAlgebra.v-andB_le_intro_l
PnVRocqLib-BooleanAlgebra.v-andsB_zero
PnVRocqLib-BooleanAlgebra.v-fact1_of_1_2_8
PnVRocqLib-BooleanAlgebra.v-isFilter_intro
PnVRocqLib-BooleanAlgebra.v-lemma1_of_1_2_11
PnVRocqLib-ClassicalDomainTheory.v-isMonotonic_if_preserves_supremum
PnVRocqLib-ClassicalDomainTheory.v-scottApp1_isMonotonic
PnVRocqLib-ClassicalDomainTheory.v-scottLam3_isContinuous
PnVRocqLib-ClassicalDomainTheory.v-seperately_continuous_iff
PnVRocqLib-ClassicalDomainTheory.v-supOfScottContinuousMaps_F_sup_X_is_supremum_of_unions_i_image_f_i_X_F
PnVRocqLib-ClassicalDomainTheory.v-supOfScottContinuousMaps_isWellDefined
PnVRocqLib-ClassicalDomainTheory.v-sup_Y_is_supremum_of_image_f_X_iff_f_sup_X_eq_sup_Y
PnVRocqLib-ClassicalFacts.v-minimisation_lemma
PnVRocqLib-ClassicalPropositionalLogic.v-ConjunctionE1_preserves
PnVRocqLib-ClassicalPropositionalLogic.v-ContradictionE_preserves
PnVRocqLib-ClassicalPropositionalLogic.v-ContradictionI_preserves
PnVRocqLib-DomainTheory.v-G0_isMonotonic1
PnVRocqLib-DomainTheory.v-G_aux0_isMonotionicMap
PnVRocqLib-DomainTheory.v-empty_bot_lattice_spec
PnVRocqLib-DomainTheory.v-initPaco
PnVRocqLib-DomainTheory.v-inv_paco'
PnVRocqLib-DomainTheory.v-paco_unfold
PnVRocqLib-Graph.v-walk_finds_path
PnVRocqLib-HilbertFol.v-Deduction_theorem
PnVRocqLib-HilbertFol.v-Rel_eqAxm_free_vars
PnVRocqLib-HilbertFol.v-cut
PnVRocqLib-HilbertFol.v-for_Imp_I
PnVRocqLib-HilbertFol.v-proof_compose
PnVRocqLib-HilbertFol.v-proof_flip
PnVRocqLib-HilbertFol.v-proves_eqn_rel
PnVRocqLib-HilbertFol2.v-ByAssumption
PnVRocqLib-HilbertFol2.v-DisjunctionI1
PnVRocqLib-HilbertFol2.v-Fun_eqAxm_HC_free
PnVRocqLib-HilbertFol2.v-NegationE
PnVRocqLib-HilbertFol2.v-cl_isSubsetOf_Th
PnVRocqLib-HilbertFol2.v-subset_union_f
PnVRocqLib-HilbertFol2.v-union_f_proves_iff
PnVRocqLib-MuRec.v-MuRecGraph_correct
PnVRocqLib-OrderTheory.v-isDirected_iff
PnVRocqLib-OrderTheory.v-nat_compare_gt
PnVRocqLib-OrderTheory.v-postfixedpointsOf_increasing
PnVRocqLib-OrderTheory.v-preservesDirectedness_if_isMonotonic
PnVRocqLib-OrderTheory.v-supremum_monotonic
PnVRocqLib-OrderTheory.v-supremum_unique
PnVRocqLib-Prelude.v-eqb_eq
PnVRocqLib-Prelude.v-in_image_iff
PnVRocqLib-Prelude.v-in_union_iff
PnVRocqLib-PropositionalLogic.v-finite_entails_monotonic
PnVRocqLib-PropositionalLogic.v-infers_dec
PnVRocqLib-SfLib.v-eqimpl
PnVRocqLib-SfLib.v-sflib__negb_rewrite
PnVRocqLib-ThN.v-cpInv_leftInv
PnVRocqLib-ThN.v-div_mod_uniqueness
PnVRocqLib-ThN.v-positive_odd
PnVRocqLib-ThN.v-sum_from_0_to_spec
PnVRocqLib-Vector.v-diagonal_spec
PnVRocqLib-Vector.v-replicate_spec
PnVRocqLib-Vector.v-to_list_rev
PnVRocqLib-BasicFol.v-closed_frm_is_sentence
PnVRocqLib-BasicFol2.v-embed_frm_inj
PnVRocqLib-BasicFol2.v-replace_constant_with_fresh_ivar_in_frm
PnVRocqLib-Vector.v-zipWith_spec
PnVRocqLib-BasicFol.v-subst_frm_similarity
PnVRocqLib-HilbertFol.v-for_MP
PnVRocqLib-HilbertFol2.v-extend_alpha_proves
PnVRocqLib-DomainTheory.v-paco_init
PnVRocqLib-OrderTheory.v-infimum_unique
PnVRocqLib-OrderTheory.v-le_iff_lt_eq
PnVRocqLib-HilbertFol2.v-ImplicationE
PnVRocqLib-Aczel.v-singlton_inj
PnVRocqLib-Vector.v-to_list_inj
PnVRocqLib-ThN.v-mod_eq_elim
PnVRocqLib-HilbertFol.v-for_All_I
PnVRocqLib-ClassicalFacts.v-projT2_eq
PnVRocqLib-Prelude.v-eqb_spec
PnVRocqLib-BasicFol.v-trm_is_enumerable
PnVRocqLib-HilbertFol.v-for_CP1
PnVRocqLib-BasicFol.v-fresh_var_is_not_free_in_frm
""".splitlines()
    if line.strip()
)


def rel(path: str) -> Path:
    return ROOT / path


def read_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(rel(path))


def ncol(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        return pd.Series([0.0] * len(df), index=df.index)
    return pd.to_numeric(df[name], errors="coerce").fillna(0.0)


def deepseek_cost(df: pd.DataFrame) -> pd.Series:
    return (
        ncol(df, "tokens_prompt_cache_hit") * DEEPSEEK_PRICES["cache_hit"]
        + ncol(df, "tokens_prompt_cache_miss") * DEEPSEEK_PRICES["cache_miss"]
        + ncol(df, "tokens_completion") * DEEPSEEK_PRICES["output"]
    ) / 1_000_000


def gpt_cost(df: pd.DataFrame) -> pd.Series:
    hit = ncol(df, "tokens_prompt_cache_hit")
    miss = ncol(df, "tokens_prompt_cache_miss")
    return (
        hit * GPT_PRICES["cache_hit"]
        + miss * GPT_PRICES["cache_miss"]
        + ncol(df, "tokens_completion") * GPT_PRICES["output"]
    ) / 1_000_000


def qwen_mtok(df: pd.DataFrame) -> pd.Series:
    return ncol(df, "tokens_total") / 1_000_000


def time_seconds(df: pd.DataFrame) -> pd.Series:
    if "agent_run_seconds" in df.columns:
        values = ncol(df, "agent_run_seconds")
        if values.sum() > 0:
            return values
    return ncol(df, "elapsed_seconds")


def ensure_success_int(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["success"] = ncol(out, "success").astype(int)
    return out


def overall_success(df: pd.DataFrame) -> tuple[int, int, float, int, float]:
    df = ensure_success_int(df)
    theorem_count = df["id"].nunique()
    solved = int(df.groupby("id")["success"].max().sum())
    trials = len(df)
    trial_successes = int(df["success"].sum())
    return (
        theorem_count,
        solved,
        solved / theorem_count * 100,
        trial_successes,
        trial_successes / trials * 100,
    )


def successful_theorem_means(
    df: pd.DataFrame, value_fn: Callable[[pd.DataFrame], pd.Series]
) -> tuple[int, float, float]:
    df = ensure_success_int(df)
    work = df.copy()
    work["value"] = value_fn(work)
    work["seconds"] = time_seconds(work)
    successful = work[work["success"] == 1]
    by_theorem = successful.groupby("id").agg(
        value=("value", "mean"), seconds=("seconds", "mean")
    )
    return len(by_theorem), float(by_theorem["value"].mean()), float(by_theorem["seconds"].mean())


def theorem_all_trial_table(
    df: pd.DataFrame, value_fn: Callable[[pd.DataFrame], pd.Series]
) -> pd.DataFrame:
    df = ensure_success_int(df)
    work = df.copy()
    work["value"] = value_fn(work)
    work["seconds"] = time_seconds(work)
    return work.groupby("id").agg(
        solved=("success", "max"),
        trial_success=("success", "mean"),
        value=("value", "mean"),
        seconds=("seconds", "mean"),
    )


def shared_solved_all_trials(
    rain_path: str,
    baseline_path: str,
    value_fn: Callable[[pd.DataFrame], pd.Series],
) -> dict[str, float]:
    rain_by = theorem_all_trial_table(read_csv(rain_path), value_fn)
    base_by = theorem_all_trial_table(read_csv(baseline_path), value_fn)
    ids = sorted(
        set(rain_by[rain_by["solved"] >= 1].index)
        & set(base_by[base_by["solved"] >= 1].index)
    )
    rain_shared = rain_by.loc[ids]
    base_shared = base_by.loc[ids]
    rain_value = float(rain_shared["value"].mean())
    base_value = float(base_shared["value"].mean())
    rain_time = float(rain_shared["seconds"].mean())
    base_time = float(base_shared["seconds"].mean())
    return {
        "theorems": len(ids),
        "rain_trial_success": float(rain_shared["trial_success"].mean() * 100),
        "base_trial_success": float(base_shared["trial_success"].mean() * 100),
        "rain_value": rain_value,
        "base_value": base_value,
        "value_reduction": (base_value - rain_value) / base_value * 100,
        "rain_time": rain_time,
        "base_time": base_time,
        "time_reduction": (base_time - rain_time) / base_time * 100,
    }


def shared_stability(
    rain_path: str,
    baseline_path: str,
    value_fn: Callable[[pd.DataFrame], pd.Series],
    threshold: int,
) -> dict[str, float]:
    rain = ensure_success_int(read_csv(rain_path))
    base = ensure_success_int(read_csv(baseline_path))
    rain_counts = rain.groupby("id")["success"].sum()
    base_counts = base.groupby("id")["success"].sum()
    ids = sorted(
        set(rain_counts[rain_counts >= threshold].index)
        & set(base_counts[base_counts >= threshold].index)
    )

    def stats(df: pd.DataFrame) -> tuple[float, float, float]:
        subset = df[df["id"].isin(ids)].copy()
        subset["value"] = value_fn(subset)
        subset["seconds"] = time_seconds(subset)
        succ = subset[subset["success"] == 1]
        by_theorem = succ.groupby("id").agg(
            value=("value", "mean"), seconds=("seconds", "mean")
        )
        return (
            len(succ) / len(subset) * 100,
            float(by_theorem["value"].mean()),
            float(by_theorem["seconds"].mean()),
        )

    rain_success, rain_value, rain_time = stats(rain)
    base_success, base_value, base_time = stats(base)
    return {
        "threshold": threshold,
        "theorems": len(ids),
        "rain_success": rain_success,
        "base_success": base_success,
        "rain_value": rain_value,
        "base_value": base_value,
        "value_reduction": (base_value - rain_value) / base_value * 100,
        "rain_time": rain_time,
        "base_time": base_time,
        "time_reduction": (base_time - rain_time) / base_time * 100,
    }


def budget_curves(
    path: str, value_fn: Callable[[pd.DataFrame], pd.Series], budgets: Iterable[float]
) -> list[tuple[float | str, float, float]]:
    df = ensure_success_int(read_csv(path))
    df["value"] = value_fn(df)
    theorem_count = df["id"].nunique()
    trial_count = len(df)
    out: list[tuple[float | str, float, float]] = []
    for budget in budgets:
        ok = df[(df["success"] == 1) & (df["value"] <= budget)]
        out.append((budget, ok["id"].nunique() / theorem_count * 100, len(ok) / trial_count * 100))
    ok = df[df["success"] == 1]
    out.append(("max", ok["id"].nunique() / theorem_count * 100, len(ok) / trial_count * 100))
    return out


def cobble_has_complete_proof(state: dict) -> bool:
    nodes = state.get("nodes", [])
    nodes_by_uuid = {node.get("uuid"): node for node in nodes}
    root_uuid = state.get("root_uuid")
    root = nodes_by_uuid.get(root_uuid)
    if root is None:
        return False

    def rec(node: dict) -> bool:
        if node.get("proof") is not None:
            return True
        for _decomp, child_uuids in zip(
            node.get("decompositions", []), node.get("children_uuids", [])
        ):
            children = [nodes_by_uuid.get(uuid) for uuid in child_uuids]
            if children and all(child is not None and rec(child) for child in children):
                return True
        return False

    return rec(root)


def parse_cobble_output_usage(run_dir: Path) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    usage_csv = run_dir / "output_usage.csv"
    if usage_csv.exists():
        for row in pd.read_csv(usage_csv).to_dict("records"):
            name = str(row["example_name"])
            output[name] = {
                "cache_hit": float(row["cache_hit"]),
                "cache_miss": float(row["cache_miss"]),
                "output": float(row["output"]),
                "duration_millis": float(row["duration_millis"]),
                "seconds": float(row["seconds"]),
                "cost": float(row["cost"]),
            }
        return output

    output_log = run_dir / "output.log"
    pattern_cache = {
        "cache_hit": r"\bnum_cache_hit_read_tokens=(\d+)",
        "cache_miss": r"\bnum_cache_miss_read_tokens=(\d+)",
        "output": r"\bnum_output_tokens=(\d+)",
        "duration_millis": r"\bduration_millis=(\d+)",
    }
    with output_log.open() as f:
        for line in f:
            if '"done with process pool:' not in line:
                continue
            row = json.loads(line)
            name = row.get("example_name") or row.get("message", "").split(": ", 1)[-1]
            usage = row.get("usage", "")
            values = {
                key: int(re.search(regex, usage).group(1)) if re.search(regex, usage) else 0
                for key, regex in pattern_cache.items()
            }
            values["seconds"] = float(row.get("duration_seconds") or values["duration_millis"] / 1000)
            values["cost"] = (
                values["cache_hit"] * DEEPSEEK_PRICES["cache_hit"]
                + values["cache_miss"] * DEEPSEEK_PRICES["cache_miss"]
                + values["output"] * DEEPSEEK_PRICES["output"]
            ) / 1_000_000
            output[name] = values
    return output


def cobblestone_numbers() -> dict[str, object]:
    rain = ensure_success_int(read_csv("Result/CobbleStone/summary_mine.csv"))
    rain_valid = rain[rain["outcome"] != "meta_failed"]
    rain_success = rain_valid[rain_valid["success"] == 1].copy()
    rain_success["cost"] = deepseek_cost(rain_success)

    run_dir = rel("Result/CobbleStone/pnvrocqlib_test_with_hammer_max_depth_5_preceding-lemmas-only-ds_max")
    valid: list[str] = []
    solved: list[str] = []
    for path in sorted(run_dir.glob("PnVRocqLib-*.json")):
        state = json.loads(path.read_text())
        valid.append(path.stem)
        if cobble_has_complete_proof(state):
            solved.append(path.stem)
    cobble_targets = COBBLESTONE_INTERSECTION_TARGETS
    if len(cobble_targets) != len(rain):
        raise ValueError(
            "CobbleStone target mapping length does not match "
            f"RAIN summary length: {len(cobble_targets)} != {len(rain)}"
        )
    rain_by_target: dict[str, dict[str, bool]] = {}
    for target, (_, row) in zip(cobble_targets, rain.sort_values("id").iterrows()):
        rain_by_target[target] = {
            "valid": row["outcome"] != "meta_failed",
            "success": int(row["success"]) == 1,
        }
    intersection = [
        target
        for target in valid
        if target in rain_by_target and rain_by_target[target]["valid"]
    ]
    failures = sorted(set(valid) - set(solved))
    usage = parse_cobble_output_usage(run_dir)
    failure_costs = [usage[name]["cost"] for name in failures]
    failure_times = [usage[name]["seconds"] for name in failures]
    rain_max = float(rain_success["cost"].max())
    return {
        "rain_valid": len(rain_valid),
        "rain_solved": int(rain_success["success"].sum()),
        "cobble_valid": len(valid),
        "cobble_solved": len(solved),
        "cobble_success_rate": len(solved) / len(valid) * 100,
        "cobble_failures": len(failures),
        "intersection_valid": len(intersection),
        "intersection_rain_solved": sum(
            1 for target in intersection if rain_by_target[target]["success"]
        ),
        "intersection_cobble_solved": sum(1 for target in intersection if target in solved),
        "rain_max_success_cost": rain_max,
        "failure_costs": (
            min(failure_costs),
            statistics.median(failure_costs),
            statistics.mean(failure_costs),
            max(failure_costs),
        ),
        "failure_cost_ratios": tuple(x / rain_max for x in (
            min(failure_costs),
            statistics.median(failure_costs),
            statistics.mean(failure_costs),
            max(failure_costs),
        )),
        "min_failure_seconds": min(failure_times),
    }


def palm_numbers() -> dict[str, object]:
    first = ensure_success_int(read_csv("Result/Palm/summary_Palm_first.csv"))
    second = ensure_success_int(read_csv("Result/Palm/summary_Palm_second.csv"))
    rain = ensure_success_int(read_csv("Result/Palm/summary_mine.csv"))
    invalid_outcomes = {"post_copy_make_failed", "extract_failed"}
    invalid_ids = set(first[first["outcome"].isin(invalid_outcomes)]["id"].unique())
    invalid_ids |= set(second[second["outcome"].isin(invalid_outcomes)]["id"].unique())
    valid_ids = sorted(set(first["id"].unique()) - invalid_ids)
    first_solved = set(first[(first["id"].isin(valid_ids)) & (first["success"] == 1)]["id"].unique())
    second_solved = set(second[(second["id"].isin(valid_ids)) & (second["success"] == 1)]["id"].unique())
    overall_solved = first_solved | second_solved
    failed_ids = sorted(set(valid_ids) - overall_solved)

    first["cost"] = deepseek_cost(first)
    second["cost"] = deepseek_cost(second)
    failure_costs = [
        float(first[first["id"] == theorem_id]["cost"].sum() + second[second["id"] == theorem_id]["cost"].sum())
        for theorem_id in failed_ids
    ]

    rain_first = rain[rain["trial"] == 1].copy()
    rain_first["cost"] = deepseek_cost(rain_first)
    rain_first_valid = rain_first[rain_first["id"].isin(valid_ids)]
    rain_first_valid_success = rain_first_valid[rain_first_valid["success"] == 1]

    return {
        "invalid": len(invalid_ids),
        "valid": len(valid_ids),
        "rain_pass1_full": int(rain_first["success"].sum()),
        "rain_pass1_full_den": rain_first["id"].nunique(),
        "rain_pass1_valid": int(rain_first_valid["success"].sum()),
        "rain_pass1_valid_den": len(valid_ids),
        "palm_first_solved": len(first_solved),
        "palm_overall_solved": len(overall_solved),
        "palm_failures": len(failed_ids),
        "rain_max_first_success_valid": float(rain_first_valid_success["cost"].max()),
        "palm_failure_costs": (
            min(failure_costs),
            statistics.median(failure_costs),
            statistics.mean(failure_costs),
            max(failure_costs),
        ),
    }


def recent_prover_numbers() -> dict[str, object]:
    full = ensure_success_int(read_csv("Result/Ablation/summary_full.csv"))
    first = full[full["trial"] == 1].drop_duplicates("id", keep="first")
    return {
        "recent_solved": 138,
        "recent_total": 200,
        "recent_success_rate": 69.0,
        "recent_avg_online_tokens": 66_700,
        "rain_solved": int(first["success"].sum()),
        "rain_total": first["id"].nunique(),
        "rain_mean_tokens": float(ncol(first, "tokens_total").mean()),
        "rain_median_tokens": float(ncol(first, "tokens_total").median()),
    }


def rq2_numbers() -> dict[str, object]:
    overall_paths = [
        ("DeepSeek-v4-flash", "RAIN", "Result/DeepSeek/summary_mine.csv"),
        ("DeepSeek-v4-flash", "Claude Code", "Result/DeepSeek/summary_claude.csv"),
        ("DeepSeek-v4-flash", "OpenCode", "Result/DeepSeek/summary_opencode.csv"),
        ("Qwen3.5-Flash", "RAIN", "Result/Qwen/summary_mine.csv"),
        ("Qwen3.5-Flash", "Claude Code", "Result/Qwen/summary_claude.csv"),
        ("Qwen3.5-Flash", "OpenCode", "Result/Qwen/summary_opencode.csv"),
        ("GPT-5.4", "RAIN", "Result/GPT/summary_mine.csv"),
        ("GPT-5.4", "Codex", "Result/GPT/summary_codex.csv"),
    ]
    overall = [(backend, system, overall_success(read_csv(path))) for backend, system, path in overall_paths]
    shared_specs = [
        ("DeepSeek-v4-flash", "RAIN--Claude", "Result/DeepSeek/summary_mine.csv", "Result/DeepSeek/summary_claude.csv", deepseek_cost),
        ("DeepSeek-v4-flash", "RAIN--OpenCode", "Result/DeepSeek/summary_mine.csv", "Result/DeepSeek/summary_opencode.csv", deepseek_cost),
        ("Qwen3.5-Flash", "RAIN--Claude", "Result/Qwen/summary_mine.csv", "Result/Qwen/summary_claude.csv", qwen_mtok),
        ("Qwen3.5-Flash", "RAIN--OpenCode", "Result/Qwen/summary_mine.csv", "Result/Qwen/summary_opencode.csv", qwen_mtok),
        ("GPT-5.4", "RAIN--Codex", "Result/GPT/summary_mine.csv", "Result/GPT/summary_codex.csv", gpt_cost),
    ]
    shared = []
    for backend, pair, rain_path, base_path, value_fn in shared_specs:
        row = shared_solved_all_trials(rain_path, base_path, value_fn)
        row["backend"] = backend
        row["pair"] = pair
        shared.append(row)

    budget = {
        "DeepSeek-v4-flash RAIN": budget_curves("Result/DeepSeek/summary_mine.csv", deepseek_cost, [0.0025, 0.005, 0.01, 0.02, 0.05]),
        "DeepSeek-v4-flash Claude Code": budget_curves("Result/DeepSeek/summary_claude.csv", deepseek_cost, [0.0025, 0.005, 0.01, 0.02, 0.05]),
        "DeepSeek-v4-flash OpenCode": budget_curves("Result/DeepSeek/summary_opencode.csv", deepseek_cost, [0.0025, 0.005, 0.01, 0.02, 0.05]),
        "Qwen3.5-Flash RAIN": budget_curves("Result/Qwen/summary_mine.csv", qwen_mtok, [0.1, 0.3, 0.5, 1.0, 2.0]),
        "Qwen3.5-Flash Claude Code": budget_curves("Result/Qwen/summary_claude.csv", qwen_mtok, [0.1, 0.3, 0.5, 1.0, 2.0]),
        "Qwen3.5-Flash OpenCode": budget_curves("Result/Qwen/summary_opencode.csv", qwen_mtok, [0.1, 0.3, 0.5, 1.0, 2.0]),
        "GPT-5.4 RAIN": budget_curves("Result/GPT/summary_mine.csv", gpt_cost, [0.05, 0.10, 0.25, 0.50, 1.00]),
        "GPT-5.4 Codex": budget_curves("Result/GPT/summary_codex.csv", gpt_cost, [0.05, 0.10, 0.25, 0.50, 1.00]),
    }
    return {"overall": overall, "shared": shared, "budget": budget}


def cluster_bootstrap_ci(full: pd.DataFrame, variant: pd.DataFrame, seed: int = 0) -> tuple[float, float]:
    full_rate = full.groupby("id")["success"].mean()
    variant_rate = variant.groupby("id")["success"].mean()
    ids = np.array(sorted(set(full_rate.index) & set(variant_rate.index)))
    diffs = (variant_rate.loc[ids] - full_rate.loc[ids]).to_numpy() * 100
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(10_000):
        samples.append(float(diffs[rng.integers(0, len(diffs), len(diffs))].mean()))
    lo, hi = np.percentile(samples, [2.5, 97.5])
    return float(lo), float(hi)


def ablation_numbers() -> dict[str, object]:
    full = ensure_success_int(read_csv("Result/Ablation/summary_full.csv"))
    variants = [
        ("Full RAIN", full),
        ("w/o local-state", ensure_success_int(read_csv("Result/Ablation/summary_no_env.csv"))),
        ("w/o multi-error", ensure_success_int(read_csv("Result/Ablation/summary_no_multi_error.csv"))),
        ("w/o both", ensure_success_int(read_csv("Result/Ablation/summary_no_env_no_multi_error.csv"))),
    ]
    aggregate = []
    for name, df in variants:
        solved, cost, seconds = successful_theorem_means(df, deepseek_cost)
        aggregate.append(
            {
                "variant": name,
                "solved": solved,
                "pass10": solved / df["id"].nunique() * 100,
                "trial": df["success"].sum() / len(df) * 100,
                "cost": cost,
                "time": seconds,
            }
        )

    by_variant = {
        name: theorem_all_trial_table(df, deepseek_cost) for name, df in variants
    }
    pairs = [
        ("Full vs. w/o local-state", "Full RAIN", "w/o local-state"),
        ("Full vs. w/o multi-error", "Full RAIN", "w/o multi-error"),
        ("Full vs. w/o both", "Full RAIN", "w/o both"),
        ("w/o local-state vs. w/o both", "w/o local-state", "w/o both"),
        ("w/o multi-error vs. w/o both", "w/o multi-error", "w/o both"),
    ]
    pairwise = []
    for label, left, right in pairs:
        left_by = by_variant[left]
        right_by = by_variant[right]
        shared_ids = sorted(
            set(left_by[left_by["solved"] >= 1].index)
            & set(right_by[right_by["solved"] >= 1].index)
        )
        left_shared = left_by.loc[shared_ids]
        right_shared = right_by.loc[shared_ids]
        pairwise.append(
            {
                "pair": label,
                "shared": len(shared_ids),
                "left_success": float(left_shared["trial_success"].mean() * 100),
                "right_success": float(right_shared["trial_success"].mean() * 100),
                "cost_reduction": (right_shared["value"].mean() - left_shared["value"].mean()) / right_shared["value"].mean() * 100,
                "time_reduction": (right_shared["seconds"].mean() - left_shared["seconds"].mean()) / right_shared["seconds"].mean() * 100,
            }
        )
    return {"aggregate": aggregate, "pairwise": pairwise}


def solved_theorem_table(
    df: pd.DataFrame, value_fn: Callable[[pd.DataFrame], pd.Series]
) -> pd.DataFrame:
    df = ensure_success_int(df)
    work = df.copy()
    work["value"] = value_fn(work)
    work["seconds"] = time_seconds(work)
    return work[work["success"] == 1].groupby("id").agg(
        value=("value", "mean"), seconds=("seconds", "mean")
    )


def parcas_numbers() -> dict[str, object]:
    rain = ensure_success_int(read_csv("Result/Parcas/summary_mine.csv"))
    claude = ensure_success_int(read_csv("Result/Parcas/summary_claude.csv"))
    opencode = ensure_success_int(read_csv("Result/Parcas/summary_opencode.csv"))
    rain_solved, rain_cost, rain_time = successful_theorem_means(rain, deepseek_cost)
    claude_solved, claude_cost, claude_time = successful_theorem_means(claude, deepseek_cost)
    opencode_solved, opencode_cost, opencode_time = successful_theorem_means(opencode, deepseek_cost)
    shared = [
        shared_solved_all_trials(
            "Result/Parcas/summary_mine.csv",
            "Result/Parcas/summary_claude.csv",
            deepseek_cost,
        )
    ]
    shared[0]["pair"] = "RAIN vs. Claude Code"
    shared.append(
        shared_solved_all_trials(
            "Result/Parcas/summary_mine.csv",
            "Result/Parcas/summary_opencode.csv",
            deepseek_cost,
        )
    )
    shared[1]["pair"] = "RAIN vs. OpenCode"
    return {
        "rain": overall_success(rain),
        "claude": overall_success(claude),
        "opencode": overall_success(opencode),
        "rain_cost": rain_cost,
        "rain_time": rain_time,
        "claude_cost": claude_cost,
        "claude_time": claude_time,
        "opencode_cost": opencode_cost,
        "opencode_time": opencode_time,
        "shared": shared,
    }


def expand_counts(df: pd.DataFrame, step_col: str, count_col: str) -> list[int]:
    out: list[int] = []
    for _, row in df.iterrows():
        out.extend([int(row[step_col])] * int(row[count_col]))
    return out


def pct_le(values: Iterable[int], threshold: int) -> float:
    values = list(values)
    return sum(v <= threshold for v in values) / len(values) * 100


def step_numbers() -> dict[str, object]:
    coqgym = expand_counts(read_csv("CoqGymStep/steps_test_num_steps.csv"), "num_steps", "count")
    coqstoq = expand_counts(read_csv("CoqStoqStep/step_distribution.csv"), "step_count", "problem_count")
    full = ensure_success_int(read_csv("Result/Ablation/summary_full.csv"))
    coqstoq_steps = read_csv("CoqStoqStep/id_step_count.csv")[["id", "step_count"]]
    by = full.groupby("id").agg(
        successes=("success", "sum"),
        trials=("success", "size"),
        any_success=("success", "max"),
    ).reset_index().merge(coqstoq_steps, on="id", how="left")
    if by["step_count"].isna().any():
        missing = by[by["step_count"].isna()]["id"].tolist()
        raise ValueError(f"missing CoqStoq step counts for ids: {missing}")
    sample_steps = by["step_count"].astype(int).tolist()
    solved_steps = by[by["any_success"] == 1]["step_count"].astype(int).tolist()
    long_50 = by[by["step_count"] > 50]
    long_30 = by[by["step_count"] > 30]
    le30 = by[by["step_count"] <= 30]
    return {
        "coqgym_le20": pct_le(coqgym, 20),
        "coqgym_le30": pct_le(coqgym, 30),
        "coqgym_le50": pct_le(coqgym, 50),
        "coqstoq_le20": pct_le(coqstoq, 20),
        "coqstoq_le30": pct_le(coqstoq, 30),
        "coqstoq_le50": pct_le(coqstoq, 50),
        "sample_le20": sum(v <= 20 for v in sample_steps),
        "sample_le30": sum(v <= 30 for v in sample_steps),
        "sample_le50": sum(v <= 50 for v in sample_steps),
        "sample_gt50": sum(v > 50 for v in sample_steps),
        "solved_gt50": sum(v > 50 for v in solved_steps),
        "sample_gt30": sum(v > 30 for v in sample_steps),
        "solved_gt30": sum(v > 30 for v in solved_steps),
        "trial_le30": float(le30["successes"].sum() / le30["trials"].sum() * 100),
        "trial_gt30": float(long_30["successes"].sum() / long_30["trials"].sum() * 100),
        "trial_gt50": float(long_50["successes"].sum() / long_50["trials"].sum() * 100),
    }


def fmt_pct(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}%"


def fmt_usd(value: float, digits: int = 5) -> str:
    return f"${value:.{digits}f}"


def fmt_table_value(backend: str, value: float) -> str:
    if backend == "Qwen3.5-Flash":
        return f"{value:.2f} M tok"
    if backend == "GPT-5.4":
        return f"${value:.3f}"
    return f"${value:.4f}"


def print_report() -> None:
    print("RQ1: Cobblestone")
    cobble = cobblestone_numbers()
    print(
        f"  RAIN: {cobble['rain_solved']}/{cobble['rain_valid']} valid; "
        f"Cobblestone: {cobble['cobble_solved']}/{cobble['cobble_valid']} "
        f"({fmt_pct(cobble['cobble_success_rate'])})"
    )
    if cobble["intersection_valid"]:
        print(
            f"  Intersection valid set: RAIN "
            f"{cobble['intersection_rain_solved']}/{cobble['intersection_valid']}; "
            f"Cobblestone {cobble['intersection_cobble_solved']}/"
            f"{cobble['intersection_valid']}"
        )
    print(
        "  Cobblestone timeout-failure costs min/median/mean/max:",
        ", ".join(fmt_usd(x) for x in cobble["failure_costs"]),
    )
    print(
        "  Relative to RAIN max successful cost",
        fmt_usd(cobble["rain_max_success_cost"]),
        ":",
        ", ".join(f"{x:.2f}x" for x in cobble["failure_cost_ratios"]),
    )

    print("\nRQ1: PALM")
    palm = palm_numbers()
    print(
        f"  invalid={palm['invalid']}; valid={palm['valid']}; "
        f"RAIN pass@1 full={palm['rain_pass1_full']}/{palm['rain_pass1_full_den']}; "
        f"RAIN PALM-valid={palm['rain_pass1_valid']}/{palm['rain_pass1_valid_den']}"
    )
    print(
        f"  PALM first pass@20={palm['palm_first_solved']}/{palm['valid']}; "
        f"PALM two rounds={palm['palm_overall_solved']}/{palm['valid']}; "
        f"failures={palm['palm_failures']}"
    )
    print(
        "  PALM 40-trial failure costs min/median/mean/max:",
        ", ".join(fmt_usd(x) for x in palm["palm_failure_costs"]),
    )
    print("  RAIN max first-trial success on PALM-valid subset:", fmt_usd(palm["rain_max_first_success_valid"]))

    print("\nRQ1: ReCent-Prover")
    recent = recent_prover_numbers()
    print(
        f"  ReCent-Prover reported {recent['recent_solved']}/{recent['recent_total']} "
        f"({fmt_pct(recent['recent_success_rate'])}) and "
        f"{recent['recent_avg_online_tokens']/1000:.1f}K online tokens/theorem"
    )
    print(
        f"  RAIN one-run result {recent['rain_solved']}/{recent['rain_total']} "
        f"({fmt_pct(recent['rain_solved']/recent['rain_total']*100)}), "
        f"mean tokens={recent['rain_mean_tokens']/1_000_000:.2f}M, "
        f"median tokens={recent['rain_median_tokens']/1000:.0f}K"
    )

    print("\nRQ2: Overall success")
    rq2 = rq2_numbers()
    for backend, system, (tasks, solved, pass10, trial_successes, trial_rate) in rq2["overall"]:
        print(f"  {backend:18s} {system:11s} pass@10={fmt_pct(pass10)} trial={fmt_pct(trial_rate)} ({trial_successes}/{tasks*10})")

    print("\nRQ2: Shared-solved rows (Table V)")
    for row in rq2["shared"]:
        print(
            f"  {row['backend']:18s} {row['pair']:12s} "
            f"n={row['theorems']:2d} "
            f"value={fmt_table_value(row['backend'], row['rain_value'])}/"
            f"{fmt_table_value(row['backend'], row['base_value'])} "
            f"red={fmt_pct(row['value_reduction'])} "
            f"time={row['rain_time']:.1f}s/{row['base_time']:.1f}s red={fmt_pct(row['time_reduction'])}"
        )

    print("\nRQ3: Ablation")
    ablation = ablation_numbers()
    for row in ablation["aggregate"]:
        print(
            f"  {row['variant']:14s} solved={row['solved']} pass@10={fmt_pct(row['pass10'])} "
            f"trial={fmt_pct(row['trial'])} cost=${row['cost']:.4f} time={row['time']:.1f}s"
        )
    print("  Pairwise shared-solved rows (Table VIb)")
    for row in ablation["pairwise"]:
        print(
            f"  {row['pair']:31s} n={row['shared']:2d} "
            f"cost red={fmt_pct(row['cost_reduction'])} "
            f"time red={fmt_pct(row['time_reduction'])}"
        )

    print("\nRQ4: Parcas")
    parcas = parcas_numbers()
    print(
        f"  RAIN {parcas['rain'][1]}/{parcas['rain'][0]} pass@10={fmt_pct(parcas['rain'][2])}, "
        f"trial={fmt_pct(parcas['rain'][4])}, cost=${parcas['rain_cost']:.4f}, time={parcas['rain_time']:.0f}s"
    )
    print(
        f"  Claude {parcas['claude'][1]}/{parcas['claude'][0]} pass@10={fmt_pct(parcas['claude'][2])}, "
        f"trial={fmt_pct(parcas['claude'][4])}, cost=${parcas['claude_cost']:.4f}, time={parcas['claude_time']:.0f}s"
    )
    print(
        f"  OpenCode {parcas['opencode'][1]}/{parcas['opencode'][0]} pass@10={fmt_pct(parcas['opencode'][2])}, "
        f"trial={fmt_pct(parcas['opencode'][4])}, cost=${parcas['opencode_cost']:.4f}, time={parcas['opencode_time']:.0f}s"
    )
    print("  Shared-solved rows (Table VIIb)")
    for row in parcas["shared"]:
        print(
            f"  {row['pair']:22s} n={row['theorems']:2d} "
            f"cost red={fmt_pct(row['value_reduction'])} "
            f"time red={fmt_pct(row['time_reduction'])}"
        )
    reductions = [(row["value_reduction"], row["time_reduction"]) for row in parcas["shared"]]
    print(
        "  shared-solved reductions cost="
        f"{min(r[0] for r in reductions):.1f}%--{max(r[0] for r in reductions):.1f}%, "
        "time="
        f"{min(r[1] for r in reductions):.1f}%--{max(r[1] for r in reductions):.1f}%"
    )

    print("\nResult analysis: proof-step distribution")
    steps = step_numbers()
    print(
        f"  CoqGym <=30={fmt_pct(steps['coqgym_le30'])}, <=50={fmt_pct(steps['coqgym_le50'])}; "
        f"CoqStoq <=30={fmt_pct(steps['coqstoq_le30'])}, <=50={fmt_pct(steps['coqstoq_le50'])}"
    )
    print(
        f"  sample <=30={steps['sample_le30']}, <=50={steps['sample_le50']}, >50={steps['sample_gt50']}; "
        f"RAIN solved >50={steps['solved_gt50']}/{steps['sample_gt50']}; "
        f">30={steps['sample_gt30']}, solved >30={steps['solved_gt30']}/{steps['sample_gt30']}; "
        f"trial <=30={fmt_pct(steps['trial_le30'])}, >30={fmt_pct(steps['trial_gt30'])}, "
        f">50={fmt_pct(steps['trial_gt50'])}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()
    if args.json:
        payload = {
            "cobblestone": cobblestone_numbers(),
            "palm": palm_numbers(),
            "recent": recent_prover_numbers(),
            "rq2": rq2_numbers(),
            "ablation": ablation_numbers(),
            "parcas": parcas_numbers(),
            "steps": step_numbers(),
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        print_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
