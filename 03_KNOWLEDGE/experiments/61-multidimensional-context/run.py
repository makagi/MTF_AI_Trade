"""
Reproducible Experiment Script for Issue #61 (EXP-61)
Multidimensional MTF Context and Feature Role Mapping (Declustered & SPEC Compliant)

Hypotheses:
1. HYP-CTX-1 (Time Maturity): Regime_Age_Ratio <= 1.2 (Early/Cruising) vs > 2.0 (Exhaustion)
   separates genuine 72h trend continuations from overextended fakeouts.
2. HYP-CTX-2 (Spatial Topology & Retest Count): Retest count (1-2 vs 3+) and Fanout Velocity
   differentiates dynamic support/resistance bounces from penetration/breakout traps.
3. HYP-CTX-3 (Feature Role Mapping): Maps SPEC-FEAT-001 core features into functional roles
   (Timing Trigger, MFE Booster, MAE Damper, Trap Gate) across 4h, 12h, 24h, 72h.
"""

from pathlib import Path
import sys
import json
import yaml
import numpy as np
import pandas as pd
from scipy import stats

# Add repo root to sys.path
repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from src.data_loader import load_ohlcv
from src.features import (
    calculate_sma,
    calculate_atr,
    calculate_squeeze_index,
    calculate_elasticity_index,
    calculate_afs,
    calculate_topology,
    calculate_fanout_velocity,
    calculate_void_distance,
    calculate_regime_age,
    calculate_level_test_count,
)
from src.evaluation import (
    evaluate_returns,
    decluster_events,
    calculate_cohens_d,
    evaluate_multi_horizon,
)


def run_experiment(exp_dir: Path):
    with open(exp_dir / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    symbol = config["data"]["symbol"]
    timeframe = config["data"]["timeframe"]
    start_date = config["data"]["start_date"]
    end_date = config["data"]["end_date"]
    std_cost = float(config["parameters"]["standard_friction_cost"])
    ref_cost = float(config["parameters"]["reference_friction_cost"])
    horizon = int(config["parameters"]["forward_horizon_bars"])
    multi_horizons = [int(h) for h in config["parameters"]["multi_horizons"]]
    cooldown = int(config["parameters"]["cooldown_bars"])
    periods_cfg = config["parameters"]["periods"]

    print(f"--- Running Experiment {config['experiment_id']} (Declustered & SPEC Compliant) ---")
    print(f"Loading {symbol} {timeframe} data ({start_date} to {end_date})...")

    df = load_ohlcv(symbol=symbol, timeframe=timeframe)
    df = df.loc[start_date:end_date].copy()
    print(f"Discovery dataset size: {len(df)} bars ({df.index[0]} to {df.index[-1]})")

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # =========================================================================
    # 1. Multi-Scale Hierarchy & Indicators
    # =========================================================================
    print("Calculating multi-scale indicators and relational features...")
    atr_24 = calculate_atr(df, 24)
    df["atr_24"] = atr_24

    fib_periods = [8, 13, 21, 34, 55, 89, 233, 377, 610, 987, 1597]
    for p in fib_periods:
        df[f"sma_{p}"] = calculate_sma(close, p)
        df[f"slope_{p}"] = (df[f"sma_{p}"] - df[f"sma_{p}"].shift(3)) / (3 * atr_24)

    # Super-Macro (987) & Macro (233, 377, 610)
    df["dist_sma_610"] = (close - df["sma_610"]) / atr_24
    df["dist_sma_233"] = (close - df["sma_233"]) / atr_24
    df["macro_alignment_bull"] = (df["sma_233"] > df["sma_377"]) & (df["sma_377"] > df["sma_610"]) & (df["slope_377"] > 0)
    df["macro_alignment_bear"] = (df["sma_233"] < df["sma_377"]) & (df["sma_377"] < df["sma_610"]) & (df["slope_377"] < 0)

    # Meso Triplet (34-55-89)
    df["meso_alignment_bull"] = (df["sma_34"] > df["sma_55"]) & (df["sma_55"] > df["sma_89"]) & (df["slope_55"] > 0)
    df["meso_alignment_bear"] = (df["sma_34"] < df["sma_55"]) & (df["sma_55"] < df["sma_89"]) & (df["slope_55"] < 0)

    # =========================================================================
    # 2. SPEC-FEAT-001 Core Features
    # =========================================================================
    print("Calculating SPEC-FEAT-001 core features...")
    df["squeeze_index"] = calculate_squeeze_index(df)
    df["elasticity_index"] = calculate_elasticity_index(df, cluster_periods=[21, 55, 89], anchor_period=377)
    
    afs_df, order_score, compression = calculate_afs(df, periods=[7, 9, 11, 13])
    df["afs_order_score"] = order_score
    df["afs_compression"] = compression
    
    sandwich_ratio, wall_density = calculate_topology(df, atr_period=14)
    df["sandwich_ratio"] = sandwich_ratio
    df["wall_density"] = wall_density
    
    df["fanout_velocity"] = calculate_fanout_velocity(df, fast_period=21, slow_period=89, atr_period=14)
    df["void_distance"] = calculate_void_distance(df, overhead_periods=[55, 89, 144, 377], atr_period=14)

    # =========================================================================
    # 3. Process & Topology Dimensions (HYP-CTX-1 & HYP-CTX-2)
    # =========================================================================
    print("Calculating Regime Age and Level Retest Count...")
    regime_df = calculate_regime_age(df)
    df["macro_age_bars"] = regime_df["macro_age_bars"]
    df["macro_age_ratio"] = regime_df["macro_age_ratio"]
    df["meso_age_bars"] = regime_df["meso_age_bars"]
    df["meso_age_ratio"] = regime_df["meso_age_ratio"]
    df["macro_regime"] = regime_df["macro_regime"]

    # Retest counts for SMA 233 and SMA 610
    df["retest_count_233"] = calculate_level_test_count(df, level=df["sma_233"], window_bars=72, tolerance_atr=0.5, atr_series=atr_24)
    df["retest_count_610"] = calculate_level_test_count(df, level=df["sma_610"], window_bars=72, tolerance_atr=0.5, atr_series=atr_24)

    # Calendar Era tagging
    df["period"] = "Other"
    for pname, pcfg in periods_cfg.items():
        df.loc[pcfg["start"]:pcfg["end"], "period"] = pname

    # =========================================================================
    # 4. Signal Definitions
    # =========================================================================
    # Signal A: Macro Bull Breakout (K-031 basis)
    # Price breaks above SMA 34 while Macro is Bull
    sig_a_raw = df["macro_alignment_bull"] & (close > df["sma_34"]) & (close.shift(1) <= df["sma_34"].shift(1))
    
    # High-extension condition (EXP-58 K-031 Trap definition: dist > 5.0 ATR or squeeze > 0.50)
    sig_a_extended_raw = sig_a_raw & ((df["dist_sma_610"] > 5.0) | (df["squeeze_index"] > 0.50))
    
    # HYP-CTX-1 Separation of High-extension Breakouts:
    # 1. Early/Cruising Stage: Macro_Age_Ratio <= 1.2
    # 2. Late/Exhaustion Stage: Macro_Age_Ratio > 2.0
    sig_a_early_raw = sig_a_extended_raw & (df["macro_age_ratio"] <= 1.2)
    sig_a_exhaust_raw = sig_a_extended_raw & (df["macro_age_ratio"] > 2.0)
    sig_a_mid_raw = sig_a_extended_raw & (df["macro_age_ratio"] > 1.2) & (df["macro_age_ratio"] <= 2.0)

    # Signal C: Macro Gravity Reversal Short (K-032 / EXP-58 canonical basis)
    # Macro Bear, price collides with SMA 233 gravity wall, Macro slope negative
    sig_c_raw = (
        df["macro_alignment_bear"] &
        (df["dist_sma_233"].abs() < 0.5) &
        (df["slope_233"] < 0)
    )

    # HYP-CTX-2 Separation of Signal C:
    # 1. Retest Count 1-2 (Fresh wall defence): retest_count_233 <= 2
    # 2. Retest Count 3+ (Exhausted wall / penetration risk): retest_count_233 >= 3
    # Sub-condition: Fanout Velocity decelerating (< 0) vs accelerating (>= 0)
    sig_c_defend_raw = sig_c_raw & (df["retest_count_233"] <= 2)
    sig_c_penetrate_raw = sig_c_raw & (df["retest_count_233"] >= 3)
    sig_c_defend_decel_raw = sig_c_defend_raw & (df["fanout_velocity"] < 0)

    # General Long Trend Benchmark for Feature Role Mapping
    # Any Meso breakout in direction of Meso Bull
    meso_breakout_raw = (close > df["sma_34"]) & (close.shift(1) <= df["sma_34"].shift(1)) & (df["slope_55"] > 0)

    # =========================================================================
    # 5. Event Declustering (24h cooldown)
    # =========================================================================
    print(f"Applying decluster_events(cooldown_bars={cooldown})...")
    sig_a_decl = decluster_events(sig_a_raw, cooldown)
    sig_a_extended_decl = decluster_events(sig_a_extended_raw, cooldown)
    sig_a_early_decl = decluster_events(sig_a_early_raw, cooldown)
    sig_a_exhaust_decl = decluster_events(sig_a_exhaust_raw, cooldown)
    sig_a_mid_decl = decluster_events(sig_a_mid_raw, cooldown)

    sig_c_decl = decluster_events(sig_c_raw, cooldown)
    sig_c_defend_decl = decluster_events(sig_c_defend_raw, cooldown)
    sig_c_penetrate_decl = decluster_events(sig_c_penetrate_raw, cooldown)
    sig_c_defend_decel_decl = decluster_events(sig_c_defend_decel_raw, cooldown)

    meso_breakout_decl = decluster_events(meso_breakout_raw, cooldown)

    print(f"Sample counts (Declustered):")
    print(f"  Signal A Extended: {sig_a_extended_decl.sum()} (Early: {sig_a_early_decl.sum()}, Mid: {sig_a_mid_decl.sum()}, Exhaust: {sig_a_exhaust_decl.sum()})")
    print(f"  Signal C Wall Short: {sig_c_decl.sum()} (Defend <=2: {sig_c_defend_decl.sum()}, Penetrate >=3: {sig_c_penetrate_decl.sum()}, Defend+Decel: {sig_c_defend_decel_decl.sum()})")
    print(f"  Meso Breakout Baseline: {meso_breakout_decl.sum()}")

    # =========================================================================
    # 6. Evaluation Execution
    # =========================================================================
    metrics_output = {
        "metadata": {
            "experiment_id": config["experiment_id"],
            "title": config["title"],
            "date": config["date"],
            "discovery_bars": len(df),
            "cooldown_bars": cooldown,
            "standard_friction_cost": std_cost,
            "reference_friction_cost": ref_cost,
            "sample_counts": {
                "sig_a_extended_decl": int(sig_a_extended_decl.sum()),
                "sig_a_early_decl": int(sig_a_early_decl.sum()),
                "sig_a_mid_decl": int(sig_a_mid_decl.sum()),
                "sig_a_exhaust_decl": int(sig_a_exhaust_decl.sum()),
                "sig_c_decl": int(sig_c_decl.sum()),
                "sig_c_defend_decl": int(sig_c_defend_decl.sum()),
                "sig_c_penetrate_decl": int(sig_c_penetrate_decl.sum()),
                "sig_c_defend_decel_decl": int(sig_c_defend_decel_decl.sum()),
                "meso_breakout_baseline": int(meso_breakout_decl.sum()),
            }
        }
    }

    # -------------------------------------------------------------------------
    # HYP-CTX-1 Evaluation: Multi-Horizon & Cross-Period for Signal A Age Groups
    # -------------------------------------------------------------------------
    print("\n--- Evaluating HYP-CTX-1 (Time Maturity Axis) ---")
    hyp1_results = {}
    for name, mask in [
        ("extended_all", sig_a_extended_decl),
        ("early_cruising", sig_a_early_decl),
        ("mid_stage", sig_a_mid_decl),
        ("exhaustion_late", sig_a_exhaust_decl),
    ]:
        mh_std = evaluate_multi_horizon(df, mask, multi_horizons, cost=std_cost, is_short=False)
        mh_ref = evaluate_multi_horizon(df, mask, multi_horizons, cost=ref_cost, is_short=False)

        # Era breakdown at 72h (macro horizon) and 24h
        era_perf = {}
        for pname, pcfg in periods_cfg.items():
            p_mask = mask & (df["period"] == pname)
            mh_p = evaluate_multi_horizon(df, p_mask, [24, 72], cost=std_cost, is_short=False)
            era_perf[pname] = {
                "trades": int(p_mask.sum()),
                "net_24h": mh_p[24]["net_mean_return"] if 24 in mh_p and mh_p[24]["total_trades"] > 0 else 0.0,
                "net_72h": mh_p[72]["net_mean_return"] if 72 in mh_p and mh_p[72]["total_trades"] > 0 else 0.0,
                "e_ratio_72h": mh_p[72]["e_ratio"] if 72 in mh_p and mh_p[72]["total_trades"] > 0 else 0.0,
            }

        hyp1_results[name] = {
            "total_trades": int(mask.sum()),
            "multi_horizon_std_40bps": {str(k): v for k, v in mh_std.items()},
            "multi_horizon_ref_6bps": {str(k): v for k, v in mh_ref.items()},
            "period_breakdown": era_perf,
        }

    # Statistical test: Macro Age Ratio difference between 72h Successes vs Failures for extended breakout
    entries_72h = df[sig_a_extended_decl.fillna(False)].copy()
    fwd_ret_72h = (close.shift(-72) - close) / close
    entries_72h["ret_72h"] = fwd_ret_72h.loc[entries_72h.index]
    entries_72h["net_ret_72h"] = entries_72h["ret_72h"] - std_cost
    clean_entries_72h = entries_72h.dropna(subset=["net_ret_72h", "macro_age_ratio"])
    
    succ_72h = clean_entries_72h[clean_entries_72h["net_ret_72h"] > 0]["macro_age_ratio"]
    fail_72h = clean_entries_72h[clean_entries_72h["net_ret_72h"] <= 0]["macro_age_ratio"]
    t_stat_age, p_val_age = stats.ttest_ind(succ_72h, fail_72h, equal_var=False)
    d_age = calculate_cohens_d(succ_72h, fail_72h)

    hyp1_results["statistical_test_72h_age"] = {
        "success_mean_age_ratio": float(succ_72h.mean()) if len(succ_72h) > 0 else 0.0,
        "failure_mean_age_ratio": float(fail_72h.mean()) if len(fail_72h) > 0 else 0.0,
        "cohens_d": round(float(d_age), 4),
        "p_value": round(float(p_val_age), 4),
        "statistically_significant": bool(p_val_age < 0.05),
    }
    metrics_output["hyp_ctx_1_time_maturity"] = hyp1_results

    # -------------------------------------------------------------------------
    # HYP-CTX-2 Evaluation: Spatial Topology & Level Retest Count for Signal C
    # -------------------------------------------------------------------------
    print("\n--- Evaluating HYP-CTX-2 (Retest Count & Spatial Topology) ---")
    hyp2_results = {}
    for name, mask in [
        ("wall_short_all", sig_c_decl),
        ("defend_fresh_count_1_2", sig_c_defend_decl),
        ("penetrate_exhausted_count_3_plus", sig_c_penetrate_decl),
        ("defend_with_deceleration", sig_c_defend_decel_decl),
    ]:
        mh_std = evaluate_multi_horizon(df, mask, multi_horizons, cost=std_cost, is_short=True)
        mh_ref = evaluate_multi_horizon(df, mask, multi_horizons, cost=ref_cost, is_short=True)

        era_perf = {}
        for pname, pcfg in periods_cfg.items():
            p_mask = mask & (df["period"] == pname)
            mh_p = evaluate_multi_horizon(df, p_mask, [24], cost=std_cost, is_short=True)
            era_perf[pname] = {
                "trades": int(p_mask.sum()),
                "net_24h": mh_p[24]["net_mean_return"] if 24 in mh_p and mh_p[24]["total_trades"] > 0 else 0.0,
                "e_ratio_24h": mh_p[24]["e_ratio"] if 24 in mh_p and mh_p[24]["total_trades"] > 0 else 0.0,
            }

        hyp2_results[name] = {
            "total_trades": int(mask.sum()),
            "multi_horizon_std_40bps": {str(k): v for k, v in mh_std.items()},
            "multi_horizon_ref_6bps": {str(k): v for k, v in mh_ref.items()},
            "period_breakdown": era_perf,
        }

    # Statistical test: Retest Count difference between 24h Short Success vs Failure
    entries_c_24h = df[sig_c_decl.fillna(False)].copy()
    fwd_short_24h = -(close.shift(-24) - close) / close
    entries_c_24h["net_ret_24h"] = fwd_short_24h.loc[entries_c_24h.index] - std_cost
    clean_c_24h = entries_c_24h.dropna(subset=["net_ret_24h", "retest_count_233"])

    succ_c = clean_c_24h[clean_c_24h["net_ret_24h"] > 0]["retest_count_233"]
    fail_c = clean_c_24h[clean_c_24h["net_ret_24h"] <= 0]["retest_count_233"]
    t_stat_retest, p_val_retest = stats.ttest_ind(succ_c, fail_c, equal_var=False)
    d_retest = calculate_cohens_d(succ_c, fail_c)

    hyp2_results["statistical_test_24h_retest_count"] = {
        "success_mean_retests": float(succ_c.mean()) if len(succ_c) > 0 else 0.0,
        "failure_mean_retests": float(fail_c.mean()) if len(fail_c) > 0 else 0.0,
        "cohens_d": round(float(d_retest), 4),
        "p_value": round(float(p_val_retest), 4),
        "statistically_significant": bool(p_val_retest < 0.05),
    }
    metrics_output["hyp_ctx_2_spatial_topology"] = hyp2_results

    # -------------------------------------------------------------------------
    # HYP-CTX-3 Evaluation: SPEC-FEAT-001 Feature Role Mapping
    # -------------------------------------------------------------------------
    print("\n--- Evaluating HYP-CTX-3 (SPEC-FEAT-001 Feature Role Mapping) ---")
    base_mask = meso_breakout_decl
    base_mh = evaluate_multi_horizon(df, base_mask, multi_horizons, cost=std_cost, is_short=False)

    feature_conditions = {
        "elasticity_high": df["elasticity_index"] > 1.5,
        "elasticity_low": df["elasticity_index"] <= 1.0,
        "afs_order_full_bull": df["afs_order_score"] == 3,
        "afs_compression_tight": df["afs_compression"] < df["afs_compression"].quantile(0.25),
        "sandwich_near_floor": df["sandwich_ratio"] <= 0.25,
        "sandwich_near_ceiling": df["sandwich_ratio"] >= 0.75,
        "wall_density_high": df["wall_density"] >= 2,
        "fanout_velocity_accel": df["fanout_velocity"] > 0,
        "fanout_velocity_decel": df["fanout_velocity"] <= 0,
        "void_distance_large": df["void_distance"] >= 2.0,
        "void_distance_small": df["void_distance"] < 1.0,
        "squeeze_index_compressed": df["squeeze_index"] < 0.25,
        "squeeze_index_extended": df["squeeze_index"] > 0.50,
        "macro_age_fresh": df["macro_age_ratio"] <= 1.0,
        "macro_age_exhausted": df["macro_age_ratio"] > 2.0,
    }

    feature_eval_results = {}
    role_classification_table = []

    for feat_name, feat_cond in feature_conditions.items():
        cond_mask = base_mask & feat_cond
        n_trades = int(cond_mask.sum())
        if n_trades < 15:
            continue

        cond_mh = evaluate_multi_horizon(df, cond_mask, multi_horizons, cost=std_cost, is_short=False)
        
        # Calculate Delta against baseline across horizons
        deltas = {}
        for h in multi_horizons:
            base_net = base_mh[h].get("net_mean_return", 0.0)
            cond_net = cond_mh[h].get("net_mean_return", 0.0)
            base_er = base_mh[h].get("e_ratio", 0.0)
            cond_er = cond_mh[h].get("e_ratio", 0.0)
            base_mfe = base_mh[h].get("mfe_mean", 0.0)
            cond_mfe = cond_mh[h].get("mfe_mean", 0.0)
            base_mae = base_mh[h].get("mae_mean", 0.0)
            cond_mae = cond_mh[h].get("mae_mean", 0.0)

            deltas[str(h)] = {
                "delta_net_return": round(float(cond_net - base_net), 5),
                "delta_e_ratio": round(float(cond_er - base_er), 4),
                "delta_mfe": round(float(cond_mfe - base_mfe), 5),
                "delta_mae": round(float(cond_mae - base_mae), 5),
                "cond_net_return": round(float(cond_net), 5),
                "cond_e_ratio": round(float(cond_er), 4),
                "win_rate": round(float(cond_mh[h].get("win_rate", 0.0)), 4),
            }

        # Check Period Consistency at 24h
        period_consistency = {}
        for pname, pcfg in periods_cfg.items():
            p_mask = cond_mask & (df["period"] == pname)
            p_eval = evaluate_returns((close.shift(-24) - close).loc[df[p_mask].index] / close.loc[df[p_mask].index], cost=std_cost)
            period_consistency[pname] = round(float(p_eval.get("net_mean_return", 0.0)), 5)

        # Role Assignment Logic
        # 1. Timing Trigger: Strong positive Delta Net Return at 4h or 12h
        # 2. MFE Booster: Increases MFE significantly at 24h/72h without proportional MAE expansion
        # 3. MAE Damper: Reduces MAE significantly at 24h
        # 4. Trap Gate: Negative return across periods when inverted or triggers loss
        delta_net_24 = deltas["24"]["delta_net_return"]
        delta_er_24 = deltas["24"]["delta_e_ratio"]
        delta_mae_24 = deltas["24"]["delta_mae"]
        delta_mfe_24 = deltas["24"]["delta_mfe"]
        delta_net_4 = deltas["4"]["delta_net_return"]

        assigned_role = "Neutral / Context-Dependent"
        primary_horizon = 24
        if delta_net_4 > 0.0020 and deltas["4"]["win_rate"] > 0.52:
            assigned_role = "Timing Trigger"
            primary_horizon = 4
        elif delta_mfe_24 > 0.0030 and delta_er_24 > 0.15:
            assigned_role = "MFE Booster"
            primary_horizon = 72 if deltas["72"]["delta_net_return"] > delta_net_24 else 24
        elif delta_mae_24 < -0.0025 and delta_net_24 > 0:
            assigned_role = "MAE Damper (Risk Filter)"
            primary_horizon = 24
        elif all(v < 0 for v in period_consistency.values()) or (delta_net_24 < -0.0040):
            assigned_role = "Trap Gate (Invalidation Filter)"
            primary_horizon = 24

        feature_eval_results[feat_name] = {
            "trades": n_trades,
            "assigned_role": assigned_role,
            "primary_horizon": primary_horizon,
            "deltas_across_horizons": deltas,
            "period_net_24h": period_consistency,
        }

        role_classification_table.append({
            "feature": feat_name,
            "role": assigned_role,
            "trades": n_trades,
            "primary_horizon": primary_horizon,
            "delta_net_24h": delta_net_24,
            "delta_er_24h": delta_er_24,
            "p1_net": period_consistency.get("P1_Bull", 0.0),
            "p2_net": period_consistency.get("P2_Bear", 0.0),
            "p3_net": period_consistency.get("P3_Mixed", 0.0),
        })

    metrics_output["hyp_ctx_3_feature_role_mapping"] = {
        "baseline_meso_breakout": {str(k): v for k, v in base_mh.items()},
        "feature_evaluations": feature_eval_results,
        "classification_summary": role_classification_table,
    }

    # =========================================================================
    # 7. Save Metrics JSON
    # =========================================================================
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    with open(exp_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_output, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to {exp_dir / 'metrics.json'}")

    # =========================================================================
    # 8. Publication-Grade Visualizations
    # =========================================================================
    print("Generating 4 publication-grade visualization plots...")
    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

    # -------------------------------------------------------------------------
    # Plot 1: HYP-CTX-1 Multi-Horizon Decay by Regime Age Ratio
    # -------------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    
    # 1. Net Expected Return Decay (4h, 12h, 24h, 72h)
    horizons_str = [str(h) for h in multi_horizons]
    for key, label, color, marker in [
        ("early_cruising", "Early/Cruising (Age Ratio <= 1.2)", "darkgreen", "o"),
        ("mid_stage", "Mid-Stage (1.2 < Age Ratio <= 2.0)", "royalblue", "s"),
        ("exhaustion_late", "Exhaustion/Late (Age Ratio > 2.0)", "crimson", "^"),
    ]:
        mh_data = hyp1_results[key]["multi_horizon_std_40bps"]
        net_returns = [mh_data[h]["net_mean_return"] * 100 for h in horizons_str]
        axes[0].plot(multi_horizons, net_returns, label=f"{label} [n={hyp1_results[key]['total_trades']}]",
                     color=color, marker=marker, linewidth=2.5, markersize=8)

    axes[0].axhline(0, color="black", linestyle="--", alpha=0.6)
    axes[0].set_title("HYP-CTX-1: Net EV Decay by Macro Age Ratio (40 bps cost)", fontsize=13, fontweight="bold")
    axes[0].set_xlabel("Holding Horizon (Hours)", fontsize=11)
    axes[0].set_ylabel("Net Mean Return (%)", fontsize=11)
    axes[0].set_xticks(multi_horizons)
    axes[0].legend(loc="upper left", frameon=True)

    # 2. E-Ratio across Horizons
    for key, label, color, marker in [
        ("early_cruising", "Early/Cruising (Age Ratio <= 1.2)", "darkgreen", "o"),
        ("mid_stage", "Mid-Stage (1.2 < Age Ratio <= 2.0)", "royalblue", "s"),
        ("exhaustion_late", "Exhaustion/Late (Age Ratio > 2.0)", "crimson", "^"),
    ]:
        mh_data = hyp1_results[key]["multi_horizon_std_40bps"]
        e_ratios = [mh_data[h]["e_ratio"] for h in horizons_str]
        axes[1].plot(multi_horizons, e_ratios, label=label, color=color, marker=marker, linewidth=2.5, markersize=8)

    axes[1].axhline(1.0, color="crimson", linestyle=":", label="E-Ratio = 1.0 (Fair Edge)")
    axes[1].set_title("E-Ratio (MFE / MAE) Horizon Profile", fontsize=13, fontweight="bold")
    axes[1].set_xlabel("Holding Horizon (Hours)", fontsize=11)
    axes[1].set_ylabel("E-Ratio", fontsize=11)
    axes[1].set_xticks(multi_horizons)
    axes[1].legend(loc="upper left", frameon=True)

    plt.tight_layout()
    fig.savefig(plots_dir / "01_regime_age_horizon_decay.png", dpi=200)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # Plot 2: HYP-CTX-2 Level Retest Count and Penetration (Signal C)
    # -------------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    retest_groups = [
        ("defend_fresh_count_1_2", "Fresh Wall (Retests <= 2)", "royalblue"),
        ("defend_with_deceleration", "Fresh + Deceleration", "darkgreen"),
        ("penetrate_exhausted_count_3_plus", "Exhausted Wall (Retests >= 3)", "crimson"),
    ]

    # Bar chart of 24h Net Return across Retest Groups
    names = [g[1] for g in retest_groups]
    trades_counts = [hyp2_results[g[0]]["total_trades"] for g in retest_groups]
    net_24h = [hyp2_results[g[0]]["multi_horizon_std_40bps"]["24"]["net_mean_return"] * 100 for g in retest_groups]
    colors = [g[2] for g in retest_groups]

    bars = axes[0].bar(names, net_24h, color=colors, alpha=0.85, width=0.55)
    axes[0].axhline(0, color="black", linestyle="--", alpha=0.6)
    axes[0].set_title("HYP-CTX-2: Signal C 24h Net Return by Retest Count (40 bps)", fontsize=13, fontweight="bold")
    axes[0].set_ylabel("24h Net Mean Return (%)", fontsize=11)
    axes[0].set_xticks(range(len(names)))
    axes[0].set_xticklabels(names, rotation=15, ha="right", fontsize=10)

    for bar, n in zip(bars, trades_counts):
        yval = bar.get_height()
        va = "bottom" if yval >= 0 else "top"
        axes[0].annotate(f"{yval:+.2f}%\n(n={n})", (bar.get_x() + bar.get_width() / 2, yval),
                         ha="center", va=va, xytext=(0, 3 if yval >= 0 else -3),
                         textcoords="offset points", fontsize=9, fontweight="bold")

    # Multi-Horizon E-Ratio for Fresh vs Exhausted
    for key, label, color in [
        ("defend_fresh_count_1_2", "Fresh Wall (Retests <= 2)", "royalblue"),
        ("defend_with_deceleration", "Fresh + Deceleration", "darkgreen"),
        ("penetrate_exhausted_count_3_plus", "Exhausted Wall (Retests >= 3)", "crimson"),
    ]:
        mh_data = hyp2_results[key]["multi_horizon_std_40bps"]
        ers = [mh_data[str(h)]["e_ratio"] for h in multi_horizons]
        axes[1].plot(multi_horizons, ers, label=label, color=color, linewidth=2.5, marker="o")

    axes[1].axhline(1.0, color="gray", linestyle=":", label="E-Ratio = 1.0 (Neutral)")
    axes[1].set_title("Signal C E-Ratio Profile Across Horizons", fontsize=13, fontweight="bold")
    axes[1].set_xlabel("Holding Horizon (Hours)", fontsize=11)
    axes[1].set_ylabel("E-Ratio (MFE / MAE)", fontsize=11)
    axes[1].set_xticks(multi_horizons)
    axes[1].legend(loc="lower left", frameon=True)

    plt.tight_layout()
    fig.savefig(plots_dir / "02_retest_count_and_penetration.png", dpi=200)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # Plot 3: HYP-CTX-3 Feature Role Spectrum Matrix
    # -------------------------------------------------------------------------
    df_role = pd.DataFrame(role_classification_table)
    df_role_sorted = df_role.sort_values(by="delta_net_24h", ascending=False)

    fig, ax = plt.subplots(figsize=(14, 8))
    role_color_map = {
        "Timing Trigger": "forestgreen",
        "MFE Booster": "dodgerblue",
        "MAE Damper (Risk Filter)": "mediumseagreen",
        "Trap Gate (Invalidation Filter)": "crimson",
        "Neutral / Context-Dependent": "slategray",
    }

    y_pos = np.arange(len(df_role_sorted))
    bar_colors = [role_color_map.get(r, "gray") for r in df_role_sorted["role"]]

    bars = ax.barh(y_pos, df_role_sorted["delta_net_24h"] * 100, color=bar_colors, alpha=0.85, height=0.65)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([f"{row['feature']} [{row['role']}]" for _, row in df_role_sorted.iterrows()], fontsize=10)
    ax.invert_yaxis()
    ax.axvline(0, color="black", linestyle="--", alpha=0.7)
    ax.set_xlabel("Delta 24h Net Return vs Baseline (%)", fontsize=11, fontweight="bold")
    ax.set_title("HYP-CTX-3: SPEC-FEAT-001 Feature Impact on 24h Net Return & Assigned Functional Roles", fontsize=13, fontweight="bold")

    # Add custom legend
    from matplotlib.patches import Patch
    legend_patches = [Patch(facecolor=col, label=role) for role, col in role_color_map.items()]
    ax.legend(handles=legend_patches, loc="lower right", frameon=True, fontsize=10)

    for bar, (_, row) in zip(bars, df_role_sorted.iterrows()):
        xval = bar.get_width()
        ha = "left" if xval >= 0 else "right"
        offset = (4, 0) if xval >= 0 else (-4, 0)
        ax.annotate(f"{xval:+.2f}% (dER={row['delta_er_24h']:+.2f}, n={row['trades']})",
                    (xval, bar.get_y() + bar.get_height() / 2),
                    xytext=offset, textcoords="offset points",
                    ha=ha, va="center", fontsize=8.5, fontweight="bold")

    plt.tight_layout()
    fig.savefig(plots_dir / "03_feature_role_spectrum_matrix.png", dpi=200)
    plt.close(fig)

    # -------------------------------------------------------------------------
    # Plot 4: Cross-Period Consistency of Key Feature Roles
    # -------------------------------------------------------------------------
    key_features = [
        "macro_age_fresh",
        "macro_age_exhausted",
        "wall_density_high",
        "fanout_velocity_accel",
        "fanout_velocity_decel",
        "void_distance_large",
        "squeeze_index_compressed",
    ]
    df_key = df_role[df_role["feature"].isin(key_features)].set_index("feature")

    periods = ["p1_net", "p2_net", "p3_net"]
    period_labels = ["P1 (Bull 2020-21)", "P2 (Bear 2022)", "P3 (Mixed 2023-25)"]

    heatmap_data = df_key[periods] * 100
    heatmap_data.columns = period_labels

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(heatmap_data, annot=True, fmt="+.2f", cmap="RdYlGn", center=0, cbar=True,
                linewidths=1.0, ax=ax, cbar_kws={"label": "Net Return (%) @ 40 bps"})
    ax.set_title("Cross-Period Performance Consistency across Eras (P1 / P2 / P3)", fontsize=13, fontweight="bold")
    ax.set_ylabel("Core Feature / Context", fontsize=11)

    plt.tight_layout()
    fig.savefig(plots_dir / "04_cross_period_role_consistency.png", dpi=200)
    plt.close(fig)

    print("Experiment run completed successfully!")
    return metrics_output


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
