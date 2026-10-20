"""
Reproducible Experiment Script for Issue #65 (EXP-65)
Composite Feature Role Gating and Multi-Horizon Context Integration
(Trap Gate x MAE Damper x MFE Booster)

Hypotheses:
1. HYP-GATE-1 (Sequential Role Gating):
   Combining Trap Gate (macro_age_exhausted / level_test_count >= 3)
   + MAE Damper (afs_compression_tight / macro_age_fresh)
   + MFE Booster (afs_order_full_bull)
   progressively improves 40 bps Net EV and E-Ratio from negative baseline to positive net edge.
2. HYP-GATE-2 (Horizon-Adaptive Fit):
   Trend-following breakout signals (Signal A) achieve positive net edge at 72h horizon,
   while dynamic S/R counter-trend bounces (Signal C) peak at 12h-24h and decay by 72h.
3. HYP-GATE-3 (Sample Starvation Boundary & Ablation):
   Identifies the minimal viable combination maintaining statistical validity (N >= 30, subperiod N >= 10)
   and quantifies the isolated marginal contribution of each role via ablation.
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
    multi_horizons = [int(h) for h in config["parameters"]["multi_horizons"]]
    cooldown = int(config["parameters"]["cooldown_bars"])
    periods_cfg = config["parameters"]["periods"]

    print(f"--- Running Experiment {config['experiment_id']} (Composite Feature Gating) ---")
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

    fib_periods = [8, 13, 21, 34, 55, 89, 233, 377, 610, 987]
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
    # 3. Context Dimensions (Regime Age & Retest Counts)
    # =========================================================================
    print("Calculating Regime Age and Level Retest Count...")
    regime_df = calculate_regime_age(df)
    df["macro_age_bars"] = regime_df["macro_age_bars"]
    df["macro_age_ratio"] = regime_df["macro_age_ratio"]
    df["meso_age_bars"] = regime_df["meso_age_bars"]
    df["meso_age_ratio"] = regime_df["meso_age_ratio"]
    df["macro_regime"] = regime_df["macro_regime"]

    df["retest_count_233"] = calculate_level_test_count(
        df, level=df["sma_233"], window_bars=72, tolerance_atr=0.5, atr_series=atr_24, min_departure_bars=3
    )

    # Calendar Era tagging
    df["period"] = "Other"
    for pname, pcfg in periods_cfg.items():
        df.loc[pcfg["start"]:pcfg["end"], "period"] = pname

    # Feature Role Masks
    afs_q25 = df["afs_compression"].quantile(0.25)
    df["is_afs_order_full_bull"] = df["afs_order_score"] == 3
    df["is_afs_compression_tight"] = df["afs_compression"] < afs_q25
    df["is_macro_age_fresh"] = df["macro_age_ratio"] <= 1.0
    df["is_macro_age_exhausted"] = df["macro_age_ratio"] > 2.0
    df["is_fanout_velocity_decel"] = df["fanout_velocity"] <= 0
    df["is_fresh_wall_233"] = df["retest_count_233"] <= 2
    df["is_exhausted_wall_233"] = df["retest_count_233"] >= 3

    # =========================================================================
    # 4. Signal Definitions & Pre-segmentation Declustering
    # =========================================================================
    print("Defining base signals and applying pre-segmentation declustering...")

    # Signal A: Macro Bull Breakout (K-031/K-036 basis)
    # Price crosses above SMA 34 in Macro Bull
    sig_a_raw = df["macro_alignment_bull"] & (close > df["sma_34"]) & (close.shift(1) <= df["sma_34"].shift(1))
    sig_a_decl = decluster_events(sig_a_raw, cooldown_bars=cooldown)

    # Extended breakout (high extension: dist > 5.0 or squeeze > 0.50)
    sig_a_ext_raw = sig_a_raw & ((df["dist_sma_610"] > 5.0) | (df["squeeze_index"] > 0.50))
    sig_a_ext_decl = decluster_events(sig_a_ext_raw, cooldown_bars=cooldown)

    # Meso Trend Breakout (General Long Trend: K-037 baseline)
    meso_breakout_raw = (close > df["sma_34"]) & (close.shift(1) <= df["sma_34"].shift(1)) & (df["slope_55"] > 0)
    meso_breakout_decl = decluster_events(meso_breakout_raw, cooldown_bars=cooldown)

    # Signal C: Macro Dynamic S/R Collision Short (K-032 / K-035 basis)
    sig_c_raw = (
        df["macro_alignment_bear"] &
        (df["dist_sma_233"].abs() < 0.5) &
        (df["slope_233"] < 0)
    )
    sig_c_decl = decluster_events(sig_c_raw, cooldown_bars=cooldown)

    print(f"Pre-segmentation declustered event counts:")
    print(f"  Signal A (Macro Bull Breakout): {sig_a_decl.sum()} events")
    print(f"  Signal A Extended (High Extension): {sig_a_ext_decl.sum()} events")
    print(f"  Meso Breakout Baseline: {meso_breakout_decl.sum()} events")
    print(f"  Signal C (Dynamic S/R Short): {sig_c_decl.sum()} events")

    # Helper function for period breakdown evaluation
    def evaluate_subperiods(mask: pd.Series, is_short: bool, cost: float, horizon_bars: int):
        p_res = {}
        for pname, pcfg in periods_cfg.items():
            p_mask = mask & (df["period"] == pname)
            n_trades = int(p_mask.sum())
            if n_trades == 0:
                p_res[pname] = {"trades": 0, "net_return": 0.0, "win_rate": 0.0, "profit_factor": 0.0, "e_ratio": 0.0}
            else:
                mh = evaluate_multi_horizon(df, p_mask, [horizon_bars], cost=cost, is_short=is_short)
                ev = mh[horizon_bars]
                p_res[pname] = {
                    "trades": n_trades,
                    "net_return": ev["net_mean_return"],
                    "win_rate": ev["win_rate"],
                    "profit_factor": ev["profit_factor"],
                    "e_ratio": ev["e_ratio"],
                }
        return p_res

    # =========================================================================
    # 5. HYP-GATE-1: Sequential Role Gating on Meso Trend Breakout (K-037 Baseline)
    # =========================================================================
    print("\n--- HYP-GATE-1: Sequential Role Gating Progression (Meso Breakout) ---")
    # Base: Meso Breakout (N=525)
    s0_a = meso_breakout_decl
    # Stage 1 (+ Trap Gate): Exclude Macro Age Exhausted (> 2.0)
    s1_a = s0_a & (~df["is_macro_age_exhausted"])
    # Stage 2 (+ MAE Damper): Stage 1 + (AFS Compression Tight OR Macro Age Fresh)
    s2_a = s1_a & (df["is_afs_compression_tight"] | df["is_macro_age_fresh"])
    # Stage 3 (+ MFE Booster): Stage 2 + AFS Order Full Bull
    s3_a = s2_a & df["is_afs_order_full_bull"]

    stages_meso = {
        "Stage 0 (Base Trigger)": s0_a,
        "Stage 1 (+ Trap Gate)": s1_a,
        "Stage 2 (+ MAE Damper)": s2_a,
        "Stage 3 (+ MFE Booster)": s3_a,
    }

    gating_results_meso = {}
    for sname, smask in stages_meso.items():
        print(f"Evaluating Meso {sname} (N={smask.sum()})...")
        mh_40 = evaluate_multi_horizon(df, smask, multi_horizons, cost=std_cost, is_short=False)
        mh_6 = evaluate_multi_horizon(df, smask, multi_horizons, cost=ref_cost, is_short=False)
        pb_24 = evaluate_subperiods(smask, is_short=False, cost=std_cost, horizon_bars=24)
        pb_72 = evaluate_subperiods(smask, is_short=False, cost=std_cost, horizon_bars=72)
        gating_results_meso[sname] = {
            "total_trades": int(smask.sum()),
            "multi_horizon_40bps": {str(k): v for k, v in mh_40.items()},
            "multi_horizon_6bps": {str(k): v for k, v in mh_6.items()},
            "period_breakdown_24h": pb_24,
            "period_breakdown_72h": pb_72,
        }

    # =========================================================================
    # 6. HYP-GATE-1: Sequential Role Gating on Signal A Extended (K-031/K-036)
    # =========================================================================
    print("\n--- HYP-GATE-1: Sequential Role Gating Progression (Signal A Extended) ---")
    # Base: Signal A Extended (N=335)
    s0_ext = sig_a_ext_decl
    # Stage 1 (+ Trap Gate): Exclude Macro Age Exhausted (> 2.0)
    s1_ext = s0_ext & (~df["is_macro_age_exhausted"])
    # Stage 2 (+ MAE Damper): Stage 1 + (AFS Compression Tight OR Macro Age Fresh)
    s2_ext = s1_ext & (df["is_afs_compression_tight"] | df["is_macro_age_fresh"])
    # Stage 3 (+ MFE Booster): Stage 2 + AFS Order Full Bull
    s3_ext = s2_ext & df["is_afs_order_full_bull"]

    stages_ext = {
        "Stage 0 (Base Trigger)": s0_ext,
        "Stage 1 (+ Trap Gate)": s1_ext,
        "Stage 2 (+ MAE Damper)": s2_ext,
        "Stage 3 (+ MFE Booster)": s3_ext,
    }

    gating_results_ext = {}
    for sname, smask in stages_ext.items():
        print(f"Evaluating Sig A Ext {sname} (N={smask.sum()})...")
        mh_40 = evaluate_multi_horizon(df, smask, multi_horizons, cost=std_cost, is_short=False)
        mh_6 = evaluate_multi_horizon(df, smask, multi_horizons, cost=ref_cost, is_short=False)
        pb_24 = evaluate_subperiods(smask, is_short=False, cost=std_cost, horizon_bars=24)
        pb_72 = evaluate_subperiods(smask, is_short=False, cost=std_cost, horizon_bars=72)
        gating_results_ext[sname] = {
            "total_trades": int(smask.sum()),
            "multi_horizon_40bps": {str(k): v for k, v in mh_40.items()},
            "multi_horizon_6bps": {str(k): v for k, v in mh_6.items()},
            "period_breakdown_24h": pb_24,
            "period_breakdown_72h": pb_72,
        }

    # =========================================================================
    # 7. HYP-GATE-1 & HYP-GATE-2: Sequential Role Gating on Signal C (Dynamic S/R Short)
    # =========================================================================
    print("\n--- HYP-GATE-1: Sequential Role Gating Progression (Signal C S/R Short) ---")
    # Base: Signal C (N=120)
    s0_c = sig_c_decl
    # Stage 1 (+ Trap Gate): Retest Count <= 2 (Fresh Wall)
    s1_c = s0_c & (df["retest_count_233"] <= 2)
    # Stage 2 (+ MAE Damper / Decel): Stage 1 + Fanout Velocity <= 0
    s2_c = s1_c & (df["fanout_velocity"] <= 0)
    # Stage 3 (+ Downside Void Space): Stage 2 + Void Distance >= 1.5 ATR
    s3_c = s2_c & (df["void_distance"] >= 1.5)

    stages_c = {
        "Stage 0 (Base Trigger)": s0_c,
        "Stage 1 (+ Trap Gate)": s1_c,
        "Stage 2 (+ MAE Damper)": s2_c,
        "Stage 3 (+ Downside Void)": s3_c,
    }

    gating_results_c = {}
    for sname, smask in stages_c.items():
        print(f"Evaluating Signal C {sname} (N={smask.sum()})...")
        mh_40 = evaluate_multi_horizon(df, smask, multi_horizons, cost=std_cost, is_short=True)
        mh_6 = evaluate_multi_horizon(df, smask, multi_horizons, cost=ref_cost, is_short=True)
        pb_24 = evaluate_subperiods(smask, is_short=True, cost=std_cost, horizon_bars=24)
        pb_12 = evaluate_subperiods(smask, is_short=True, cost=std_cost, horizon_bars=12)
        gating_results_c[sname] = {
            "total_trades": int(smask.sum()),
            "multi_horizon_40bps": {str(k): v for k, v in mh_40.items()},
            "multi_horizon_6bps": {str(k): v for k, v in mh_6.items()},
            "period_breakdown_24h": pb_24,
            "period_breakdown_12h": pb_12,
        }

    # =========================================================================
    # 8. HYP-GATE-3: Ablation Study (Component Contribution on Meso Breakout)
    # =========================================================================
    print("\n--- HYP-GATE-3: Ablation Study on Meso Breakout ---")
    gate_trap = ~df["is_macro_age_exhausted"]
    gate_damper = (df["is_afs_compression_tight"] | df["is_macro_age_fresh"])
    gate_booster = df["is_afs_order_full_bull"]

    ablation_masks = {
        "Full Model (Trap + Damper + Booster)": s0_a & gate_trap & gate_damper & gate_booster,
        "w/o Trap Gate (Damper + Booster)": s0_a & gate_damper & gate_booster,
        "w/o MAE Damper (Trap + Booster)": s0_a & gate_trap & gate_booster,
        "w/o MFE Booster (Trap + Damper)": s0_a & gate_trap & gate_damper,
        "Trap Gate Only": s0_a & gate_trap,
        "MAE Damper Only": s0_a & gate_damper,
        "MFE Booster Only": s0_a & gate_booster,
        "Baseline (None)": s0_a,
    }

    ablation_results = {}
    for aname, amask in ablation_masks.items():
        print(f"Evaluating Ablation: {aname} (N={amask.sum()})...")
        mh_40 = evaluate_multi_horizon(df, amask, multi_horizons, cost=std_cost, is_short=False)
        pb_24 = evaluate_subperiods(amask, is_short=False, cost=std_cost, horizon_bars=24)
        pb_72 = evaluate_subperiods(amask, is_short=False, cost=std_cost, horizon_bars=72)
        ablation_results[aname] = {
            "total_trades": int(amask.sum()),
            "multi_horizon_40bps": {str(k): v for k, v in mh_40.items()},
            "period_breakdown_24h": pb_24,
            "period_breakdown_72h": pb_72,
        }

    # =========================================================================
    # 9. Visualizations
    # =========================================================================
    print("\nGenerating visualizations...")
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="darkgrid")

    # Plot 1: Sequential Gating EV Progression
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1a. Meso Breakout Net EV Progression across Horizons
    stage_keys = list(gating_results_meso.keys())
    for h in ["4", "12", "24", "72"]:
        evs = [gating_results_meso[s]["multi_horizon_40bps"][h]["net_mean_return"] * 100 for s in stage_keys]
        axes[0, 0].plot(range(len(stage_keys)), evs, marker="o", linewidth=2.5, label=f"Horizon {h}h")
    axes[0, 0].axhline(0.0, color="gray", linestyle="--", alpha=0.7)
    axes[0, 0].set_xticks(range(len(stage_keys)))
    axes[0, 0].set_xticklabels([f"S{i}" for i in range(len(stage_keys))], fontsize=10)
    axes[0, 0].set_ylabel("Net EV (%, 40 bps)")
    axes[0, 0].set_title("Meso Breakout: Net EV Progression across Gating Stages", fontsize=12, fontweight="bold")
    axes[0, 0].legend()

    # 1b. Meso Breakout E-Ratio Progression (24h & 72h)
    for h in ["24", "72"]:
        ers = [gating_results_meso[s]["multi_horizon_40bps"][h]["e_ratio"] for s in stage_keys]
        axes[0, 1].plot(range(len(stage_keys)), ers, marker="s", linewidth=2.5, label=f"E-Ratio {h}h")
    axes[0, 1].axhline(1.0, color="red", linestyle="--", alpha=0.7, label="ER = 1.0 (Parity)")
    axes[0, 1].set_xticks(range(len(stage_keys)))
    axes[0, 1].set_xticklabels(stage_keys, rotation=15, ha="right", fontsize=9)
    axes[0, 1].set_ylabel("E-Ratio (MFE / MAE)")
    axes[0, 1].set_title("Meso Breakout: E-Ratio Progression across Gating Stages", fontsize=12, fontweight="bold")
    axes[0, 1].legend()

    # 1c. Signal C Net EV Progression (Counter-Trend Bounce: 4h, 12h, 24h, 72h)
    c_stage_keys = list(gating_results_c.keys())
    for h in ["4", "12", "24", "72"]:
        evs_c = [gating_results_c[s]["multi_horizon_40bps"][h]["net_mean_return"] * 100 for s in c_stage_keys]
        axes[1, 0].plot(range(len(c_stage_keys)), evs_c, marker="^", linewidth=2.5, label=f"Horizon {h}h")
    axes[1, 0].axhline(0.0, color="gray", linestyle="--", alpha=0.7)
    axes[1, 0].set_xticks(range(len(c_stage_keys)))
    axes[1, 0].set_xticklabels([f"S{i}" for i in range(len(c_stage_keys))], fontsize=10)
    axes[1, 0].set_ylabel("Net EV (%, 40 bps)")
    axes[1, 0].set_title("Signal C: Net EV Progression across Gating Stages", fontsize=12, fontweight="bold")
    axes[1, 0].legend()

    # 1d. Sample Size Retention across Stages
    ns_m = [gating_results_meso[s]["total_trades"] for s in stage_keys]
    ns_c = [gating_results_c[s]["total_trades"] for s in c_stage_keys]
    axes[1, 1].bar([i - 0.15 for i in range(4)], ns_m, width=0.3, label="Meso Breakout (Long)", alpha=0.8, color="steelblue")
    axes[1, 1].bar([i + 0.15 for i in range(4)], ns_c, width=0.3, label="Signal C Wall (Short)", alpha=0.8, color="coral")
    axes[1, 1].axhline(30, color="darkred", linestyle=":", linewidth=2, label="Starvation Boundary (N=30)")
    axes[1, 1].set_xticks(range(4))
    axes[1, 1].set_xticklabels([f"Stage {i}" for i in range(4)], fontsize=10)
    axes[1, 1].set_ylabel("Independent Sample Size (N)")
    axes[1, 1].set_title("Independent Sample Size Retention per Stage", fontsize=12, fontweight="bold")
    axes[1, 1].legend()

    plt.tight_layout()
    plt.savefig(plots_dir / "01_sequential_gating_ev_progression.png", dpi=300)
    plt.close()

    # Plot 2: Ablation Component Contribution (72h Net EV & E-Ratio)
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    abl_keys = list(ablation_results.keys())
    ev_72 = [ablation_results[m]["multi_horizon_40bps"]["72"]["net_mean_return"] * 100 for m in abl_keys]
    er_72 = [ablation_results[m]["multi_horizon_40bps"]["72"]["e_ratio"] for m in abl_keys]

    y_pos = np.arange(len(abl_keys))
    colors_ev = ["green" if v >= 0 else "crimson" for v in ev_72]
    axes[0].barh(y_pos, ev_72, color=colors_ev, alpha=0.7)
    axes[0].axvline(0.0, color="black", linestyle="--")
    axes[0].set_yticks(y_pos)
    axes[0].set_yticklabels(abl_keys, fontsize=9)
    axes[0].set_xlabel("72h Net EV (%, 40 bps)")
    axes[0].set_title("Ablation Study: 72h Net EV by Configuration", fontsize=12, fontweight="bold")

    axes[1].barh(y_pos, er_72, color="steelblue", alpha=0.7)
    axes[1].axvline(1.0, color="red", linestyle="--", label="ER = 1.0 (Parity)")
    axes[1].set_yticks(y_pos)
    axes[1].set_yticklabels(abl_keys, fontsize=9)
    axes[1].set_xlabel("72h E-Ratio (MFE / MAE)")
    axes[1].set_title("Ablation Study: 72h E-Ratio by Configuration", fontsize=12, fontweight="bold")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(plots_dir / "02_ablation_component_contribution.png", dpi=300)
    plt.close()

    # Plot 3: Sample Size vs Edge Trade-off (Pareto Frontier)
    plt.figure(figsize=(11, 7))
    for name, res in ablation_results.items():
        n = res["total_trades"]
        net_ev = res["multi_horizon_40bps"]["72"]["net_mean_return"] * 100
        er = res["multi_horizon_40bps"]["72"]["e_ratio"]
        plt.scatter(n, net_ev, s=max(er, 0.5) * 120, alpha=0.75, edgecolors="black")
        plt.annotate(
            f"{name}\n(N={n}, {net_ev:+.2f}%, ER={er:.2f})",
            (n, net_ev),
            textcoords="offset points",
            xytext=(6, 5),
            fontsize=8,
        )

    plt.axhline(0.0, color="gray", linestyle="--", alpha=0.7)
    plt.axvline(30, color="red", linestyle=":", label="N=30 Minimum Power Boundary")
    plt.xlabel("Independent Event Sample Size (N)")
    plt.ylabel("72h Net EV (%, 40 bps)")
    plt.title("Sample Size vs 72h Net Edge Trade-off (Bubble Size = 72h E-Ratio)", fontsize=12, fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.savefig(plots_dir / "03_sample_size_vs_edge_tradeoff.png", dpi=300)
    plt.close()

    # Plot 4: Cross-Period Composite Stability
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    periods = ["P1_Bull", "P2_Bear", "P3_Mixed"]

    # 4a. Meso Breakout Stages across Periods (72h Net EV)
    matrix_a = []
    for s in stage_keys:
        row = [gating_results_meso[s]["period_breakdown_72h"][p]["net_return"] * 100 for p in periods]
        matrix_a.append(row)
    df_matrix_a = pd.DataFrame(matrix_a, index=stage_keys, columns=["P1 (Bull)", "P2 (Bear)", "P3 (Mixed)"])
    sns.heatmap(df_matrix_a, annot=True, fmt="+.2f", cmap="vlag", center=0.0, ax=axes[0], cbar_kws={'label': '72h Net EV (%)'})
    axes[0].set_title("Meso Breakout: 72h Net EV Stability across Regimes", fontsize=12, fontweight="bold")

    # 4b. Signal C Stages across Periods (24h Net EV)
    matrix_c = []
    for s in c_stage_keys:
        row = [gating_results_c[s]["period_breakdown_24h"][p]["net_return"] * 100 for p in periods]
        matrix_c.append(row)
    df_matrix_c = pd.DataFrame(matrix_c, index=c_stage_keys, columns=["P1 (Bull)", "P2 (Bear)", "P3 (Mixed)"])
    sns.heatmap(df_matrix_c, annot=True, fmt="+.2f", cmap="vlag", center=0.0, ax=axes[1], cbar_kws={'label': '24h Net EV (%)'})
    axes[1].set_title("Signal C: 24h Net EV Stability across Regimes", fontsize=12, fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "04_cross_period_composite_stability.png", dpi=300)
    plt.close()

    # =========================================================================
    # 10. Output Metrics to JSON
    # =========================================================================
    print("Writing metrics to metrics.json...")

    def convert_types(obj):
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        elif isinstance(obj, (np.floating, float)):
            return float(obj)
        elif isinstance(obj, (np.ndarray, list)):
            return [convert_types(x) for x in obj]
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, dict):
            return {k: convert_types(v) for k, v in obj.items()}
        return obj

    metrics_output = {
        "experiment_id": config["experiment_id"],
        "date": config["date"],
        "author": config["author"],
        "issue": config["issue"],
        "dataset": {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "total_bars": len(df),
        },
        "parameters": {
            "standard_friction_cost": std_cost,
            "reference_friction_cost": ref_cost,
            "cooldown_bars": cooldown,
            "multi_horizons": multi_horizons,
        },
        "sample_counts": {
            "meso_breakout_decl": int(s0_a.sum()),
            "sig_a_ext_decl": int(s0_ext.sum()),
            "sig_c_decl": int(s0_c.sum()),
        },
        "meso_breakout_sequential_gating": gating_results_meso,
        "signal_a_extended_sequential_gating": gating_results_ext,
        "signal_c_sequential_gating": gating_results_c,
        "ablation_study": ablation_results,
    }

    metrics_clean = convert_types(metrics_output)
    with open(exp_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_clean, f, indent=2)

    print("Experiment EXP-65 run successfully completed!")
    return metrics_clean


if __name__ == "__main__":
    exp_directory = Path(__file__).resolve().parent
    run_experiment(exp_directory)
