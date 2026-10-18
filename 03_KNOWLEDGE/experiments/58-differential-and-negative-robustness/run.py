"""
Reproducible Experiment Script for Issue #58
Contrastive Differential Analysis and Negative Edge Robustness Verification (EXP-58).
Evaluates both success and failure consistency across similar market regimes and identifies boundary conditions.
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
    calculate_bollinger_bands,
    calculate_squeeze_index,
)
from src.evaluation import evaluate_returns


def cohens_d(group1: np.ndarray, group2: np.ndarray) -> float:
    """Calculate Cohen's d effect size between two groups."""
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return 0.0
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_se = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_se == 0 or np.isnan(pooled_se):
        return 0.0
    return float((np.mean(group1) - np.mean(group2)) / pooled_se)


def run_experiment(exp_dir: Path):
    with open(exp_dir / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    symbol = config.get("symbol") or config["data"]["symbol"]
    timeframe = config.get("timeframe") or config["data"]["timeframe"]
    start_date = config["data"]["start_date"]
    end_date = config["data"]["end_date"]
    friction_cost = float(config["parameters"]["friction_cost"])
    horizon = int(config["parameters"]["forward_horizon_bars"])
    periods_cfg = config["parameters"]["periods"]

    print(f"--- Running Experiment {config['experiment_id']} ---")
    print(f"Loading {symbol} {timeframe} data...")

    df = load_ohlcv(symbol=symbol, timeframe=timeframe)
    df = df.loc[start_date:end_date].copy()
    print(f"Discovery dataset size: {len(df)} bars ({df.index[0]} to {df.index[-1]})")

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # =========================================================================
    # 1. Feature Calculations (SPEC-FEAT-001 Compliant)
    # =========================================================================
    print("Calculating multi-scale indicators and relational features...")
    atr_24 = calculate_atr(df, 24)
    df["atr_24"] = atr_24

    # Multi-scale SMAs
    fib_periods = [8, 13, 21, 34, 55, 89, 233, 377, 610]
    for p in fib_periods:
        df[f"sma_{p}"] = calculate_sma(close, p)
        # Slope (normalized by ATR)
        df[f"slope_{p}"] = (df[f"sma_{p}"] - df[f"sma_{p}"].shift(3)) / (3 * atr_24)

    # Super-Macro Weekly proxy SMA (168 bars = 1 week, 610 = ~25 days)
    df["sma_super_macro"] = calculate_sma(close, 168)
    df["slope_super_macro"] = (df["sma_super_macro"] - df["sma_super_macro"].shift(24)) / (24 * atr_24)
    df["dist_super_macro"] = (close - df["sma_super_macro"]) / atr_24
    df["dist_sma_610"] = (close - df["sma_610"]) / atr_24

    # Meso Triplet (34-55-89) geometry
    df["meso_range"] = df[["sma_34", "sma_55", "sma_89"]].max(axis=1) - df[["sma_34", "sma_55", "sma_89"]].min(axis=1)
    df["meso_bottleneck_ratio"] = df["meso_range"] / atr_24
    df["meso_alignment_bull"] = (df["sma_34"] > df["sma_55"]) & (df["sma_55"] > df["sma_89"])
    df["meso_deceleration"] = df["slope_34"] - df["slope_34"].shift(3)  # Second derivative (curvature change)
    df["meso_curvature_ratio"] = (df["sma_34"] - df["sma_55"]) / (df["sma_55"] - df["sma_89"] + 1e-6)

    # Macro Triplet (233-377-610) geometry
    df["macro_alignment_bull"] = (df["sma_233"] > df["sma_377"]) & (df["sma_377"] > df["sma_610"])
    df["macro_alignment_bear"] = (df["sma_233"] < df["sma_377"]) & (df["sma_377"] < df["sma_610"])
    df["macro_slope"] = df["slope_233"]
    df["dist_macro_233"] = (close - df["sma_233"]) / atr_24

    # SPEC-FEAT-001 Squeeze Index (Continuous 0.0 to 1.0)
    print("Calculating Squeeze Index (SPEC-FEAT-001)...")
    df["squeeze_index"] = calculate_squeeze_index(df)

    # Forward 24h evaluation metrics
    df["fwd_ret_24h"] = (close.shift(-horizon) - close) / close
    fwd_high_24h = high.shift(-1).rolling(horizon).max().shift(-(horizon - 1))
    fwd_low_24h = low.shift(-1).rolling(horizon).min().shift(-(horizon - 1))
    df["mfe_24h"] = (fwd_high_24h - close) / close
    df["mae_24h"] = (close - fwd_low_24h) / close

    # Calendar period assignment (External test sets)
    df["period"] = "Other"
    for pname, pcfg in periods_cfg.items():
        mask = (df.index >= pcfg["start"]) & (df.index <= pcfg["end"])
        df.loc[mask, "period"] = pname

    # =========================================================================
    # 2. SIGNAL A: Alignment Breakout (K-021 / K-017 / K-028)
    # =========================================================================
    print("\n--- Evaluating Signal A: Meso-Macro Alignment Breakout ---")
    sig_a_mask = (
        df["meso_alignment_bull"] &
        (close > df["sma_34"]) &
        (close.shift(1) <= df["sma_34"].shift(1)) &
        (df["slope_34"] > 0)
    )
    sig_a_events = df[sig_a_mask].dropna(subset=["fwd_ret_24h", "mfe_24h", "mae_24h", "squeeze_index"]).copy()
    print(f"Signal A total raw events: {len(sig_a_events)}")

    # Contrastive definitions
    sig_a_success = sig_a_events[sig_a_events["fwd_ret_24h"] > 0.015]
    sig_a_failure = sig_a_events[sig_a_events["fwd_ret_24h"] < -0.010]
    print(f"Signal A Success cases: {len(sig_a_success)}, Failure cases: {len(sig_a_failure)}")

    diff_features_a = [
        ("squeeze_index", "Squeeze Index (0=Tight, 1=Extended)", "squeeze_index"),
        ("dist_super_macro", "Super-Macro 168h Dist (ATR)", "dist_super_macro"),
        ("dist_sma_610", "Macro 610 Dist (ATR)", "dist_sma_610"),
        ("macro_slope", "Macro Slope (233h)", "slope_233"),
        ("super_macro_slope", "Super-Macro Slope (168h)", "slope_super_macro"),
        ("meso_curvature", "Meso Curvature Ratio", "meso_curvature_ratio"),
    ]

    stats_a = {}
    for feat_id, feat_label, col in diff_features_a:
        s_vals = sig_a_success[col].dropna().values
        f_vals = sig_a_failure[col].dropna().values
        d = cohens_d(s_vals, f_vals)
        t_stat, p_val = stats.ttest_ind(s_vals, f_vals, equal_var=False)
        stats_a[feat_id] = {
            "name": feat_label,
            "success_mean": float(np.mean(s_vals)),
            "success_std": float(np.std(s_vals)),
            "failure_mean": float(np.mean(f_vals)),
            "failure_std": float(np.std(f_vals)),
            "cohens_d": float(d),
            "p_value": float(p_val),
            "statistically_significant": bool(p_val < 0.05)
        }
        print(f"  Feature [{feat_label}]: Success={np.mean(s_vals):.3f}, Failure={np.mean(f_vals):.3f}, d={d:.2f}, p={p_val:.4f}")

    # Trap Hypothesis:
    # 1. Over-extended Volatility: squeeze_index > 0.50 (Breakout attempted after volatility expansion is already exhausted)
    # 2. Over-extended Macro Divergence: dist_sma_610 > 5.0 (Hyper-extended from macro baseline)
    sig_a_events["is_trap"] = (sig_a_events["squeeze_index"] > 0.50) | (sig_a_events["dist_sma_610"] > 5.0)
    sig_a_events["is_valid"] = ~sig_a_events["is_trap"]

    trap_a_cross_period = {}
    valid_a_cross_period = {}
    for p in ["P1_Bull", "P2_Bear", "P3_Mixed"]:
        trap_sub = sig_a_events[(sig_a_events["period"] == p) & sig_a_events["is_trap"]]
        valid_sub = sig_a_events[(sig_a_events["period"] == p) & sig_a_events["is_valid"]]

        trap_metrics = evaluate_returns(trap_sub["fwd_ret_24h"], cost=friction_cost) if len(trap_sub) >= 10 else None
        valid_metrics = evaluate_returns(valid_sub["fwd_ret_24h"], cost=friction_cost) if len(valid_sub) >= 10 else None

        trap_a_cross_period[p] = {
            "count": len(trap_sub),
            "net_ev": float(trap_metrics["net_mean_return"]) if trap_metrics else None,
            "win_rate": float(trap_metrics["win_rate"]) if trap_metrics else None,
            "mean_mae": float(trap_sub["mae_24h"].mean()) if len(trap_sub) > 0 else None,
            "mean_mfe": float(trap_sub["mfe_24h"].mean()) if len(trap_sub) > 0 else None,
        }
        valid_a_cross_period[p] = {
            "count": len(valid_sub),
            "net_ev": float(valid_metrics["net_mean_return"]) if valid_metrics else None,
            "win_rate": float(valid_metrics["win_rate"]) if valid_metrics else None,
            "mean_mae": float(valid_sub["mae_24h"].mean()) if len(valid_sub) > 0 else None,
            "mean_mfe": float(valid_sub["mfe_24h"].mean()) if len(valid_sub) > 0 else None,
        }

    print("Signal A Trap Performance across periods:")
    for p, met in trap_a_cross_period.items():
        print(f"  {p}: Count={met['count']}, Net EV={met['net_ev']}, WinRate={met['win_rate']}, Mean MAE={met['mean_mae']}")
    print("Signal A Valid Performance across periods:")
    for p, met in valid_a_cross_period.items():
        print(f"  {p}: Count={met['count']}, Net EV={met['net_ev']}, WinRate={met['win_rate']}, Mean MAE={met['mean_mae']}")

    # =========================================================================
    # 3. SIGNAL B: Bottleneck Expansion Breakout (K-022)
    # =========================================================================
    print("\n--- Evaluating Signal B: Bottleneck Expansion Breakout ---")
    bottleneck_cond = (df["meso_bottleneck_ratio"].shift(1) < 0.40) & (df["meso_range"] > df["meso_range"].shift(1))
    break_bull = bottleneck_cond & (close > df["sma_34"]) & (df["slope_34"] > 0)
    sig_b_events = df[break_bull].dropna(subset=["fwd_ret_24h", "mfe_24h", "mae_24h", "squeeze_index"]).copy()
    print(f"Signal B total raw events: {len(sig_b_events)}")

    sig_b_success = sig_b_events[sig_b_events["fwd_ret_24h"] > 0.015]
    sig_b_failure = sig_b_events[sig_b_events["fwd_ret_24h"] < -0.010]
    print(f"Signal B Success cases: {len(sig_b_success)}, Failure cases: {len(sig_b_failure)}")

    diff_features_b = [
        ("macro_alignment_bull", "Macro Bull Alignment", "macro_alignment_bull"),
        ("squeeze_index", "Squeeze Index", "squeeze_index"),
        ("macro_slope", "Macro Slope (233h)", "slope_233"),
        ("super_macro_slope", "Super-Macro Slope (168h)", "slope_super_macro"),
    ]

    stats_b = {}
    for feat_id, feat_label, col in diff_features_b:
        s_vals = sig_b_success[col].astype(float).dropna().values
        f_vals = sig_b_failure[col].astype(float).dropna().values
        d = cohens_d(s_vals, f_vals)
        t_stat, p_val = stats.ttest_ind(s_vals, f_vals, equal_var=False)
        stats_b[feat_id] = {
            "name": feat_label,
            "success_mean": float(np.mean(s_vals)),
            "failure_mean": float(np.mean(f_vals)),
            "cohens_d": float(d),
            "p_value": float(p_val),
            "statistically_significant": bool(p_val < 0.05)
        }
        print(f"  Feature [{feat_label}]: Success={np.mean(s_vals):.3f}, Failure={np.mean(f_vals):.3f}, d={d:.2f}, p={p_val:.4f}")

    # Trap condition for Signal B:
    # High Squeeze Index (> 0.40, lack of true pre-compression) OR Counter-Macro (slope_233 < -0.01)
    sig_b_events["is_trap"] = (sig_b_events["squeeze_index"] > 0.40) | (sig_b_events["slope_233"] < -0.01)
    sig_b_events["is_valid"] = ~sig_b_events["is_trap"]

    trap_b_cross_period = {}
    valid_b_cross_period = {}
    for p in ["P1_Bull", "P2_Bear", "P3_Mixed"]:
        trap_sub = sig_b_events[(sig_b_events["period"] == p) & sig_b_events["is_trap"]]
        valid_sub = sig_b_events[(sig_b_events["period"] == p) & sig_b_events["is_valid"]]

        trap_metrics = evaluate_returns(trap_sub["fwd_ret_24h"], cost=friction_cost) if len(trap_sub) >= 10 else None
        valid_metrics = evaluate_returns(valid_sub["fwd_ret_24h"], cost=friction_cost) if len(valid_sub) >= 10 else None

        trap_b_cross_period[p] = {
            "count": len(trap_sub),
            "net_ev": float(trap_metrics["net_mean_return"]) if trap_metrics else None,
            "win_rate": float(trap_metrics["win_rate"]) if trap_metrics else None,
            "mean_mae": float(trap_sub["mae_24h"].mean()) if len(trap_sub) > 0 else None,
            "mean_mfe": float(trap_sub["mfe_24h"].mean()) if len(trap_sub) > 0 else None,
        }
        valid_b_cross_period[p] = {
            "count": len(valid_sub),
            "net_ev": float(valid_metrics["net_mean_return"]) if valid_metrics else None,
            "win_rate": float(valid_metrics["win_rate"]) if valid_metrics else None,
            "mean_mae": float(valid_sub["mae_24h"].mean()) if len(valid_sub) > 0 else None,
            "mean_mfe": float(valid_sub["mfe_24h"].mean()) if len(valid_sub) > 0 else None,
        }

    # =========================================================================
    # 4. SIGNAL C: Bear Market Rally Collision with Macro Gravity Wall (K-027)
    # =========================================================================
    print("\n--- Evaluating Signal C: Bear Rally Macro Gravity Collision ---")
    wall_collision = (
        df["macro_alignment_bear"] &
        (df["dist_macro_233"].abs() < 0.5) &
        (df["slope_233"] < 0)
    )
    sig_c_events = df[wall_collision].dropna(subset=["fwd_ret_24h", "mfe_24h", "mae_24h"]).copy()
    sig_c_events["short_ret_24h"] = -sig_c_events["fwd_ret_24h"]
    sig_c_events["short_mae_24h"] = sig_c_events["mfe_24h"]
    sig_c_events["short_mfe_24h"] = sig_c_events["mae_24h"]
    print(f"Signal C total raw events: {len(sig_c_events)}")

    sig_c_success = sig_c_events[sig_c_events["short_ret_24h"] > 0.015]
    sig_c_failure = sig_c_events[sig_c_events["short_ret_24h"] < -0.015]
    print(f"Signal C Short Success: {len(sig_c_success)}, Failure (Breach): {len(sig_c_failure)}")

    diff_features_c = [
        ("meso_slope", "Meso Slope at Collision", "slope_34"),
        ("meso_deceleration", "Meso Deceleration before Wall", "meso_deceleration"),
        ("dist_super_macro", "Super-Macro Distance (ATR)", "dist_super_macro"),
        ("macro_slope", "Macro Slope (233h)", "slope_233"),
        ("squeeze_index", "Squeeze Index", "squeeze_index"),
    ]

    stats_c = {}
    for feat_id, feat_label, col in diff_features_c:
        s_vals = sig_c_success[col].dropna().values
        f_vals = sig_c_failure[col].dropna().values
        d = cohens_d(s_vals, f_vals)
        t_stat, p_val = stats.ttest_ind(s_vals, f_vals, equal_var=False)
        stats_c[feat_id] = {
            "name": feat_label,
            "success_mean": float(np.mean(s_vals)),
            "failure_mean": float(np.mean(f_vals)),
            "cohens_d": float(d),
            "p_value": float(p_val),
            "statistically_significant": bool(p_val < 0.05)
        }
        print(f"  Feature [{feat_label}]: Success={np.mean(s_vals):.3f}, Failure={np.mean(f_vals):.3f}, d={d:.2f}, p={p_val:.4f}")

    # Trap condition for Shorting at Wall (Breach Trap):
    # Shorting when meso slope is steep (> 0.035, accelerating momentum into wall)
    sig_c_events["is_trap"] = sig_c_events["slope_34"] > 0.035
    sig_c_events["is_valid"] = ~sig_c_events["is_trap"]

    trap_c_cross_period = {}
    valid_c_cross_period = {}
    for p in ["P1_Bull", "P2_Bear", "P3_Mixed"]:
        trap_sub = sig_c_events[(sig_c_events["period"] == p) & sig_c_events["is_trap"]]
        valid_sub = sig_c_events[(sig_c_events["period"] == p) & sig_c_events["is_valid"]]

        trap_metrics = evaluate_returns(trap_sub["short_ret_24h"], cost=friction_cost) if len(trap_sub) >= 10 else None
        valid_metrics = evaluate_returns(valid_sub["short_ret_24h"], cost=friction_cost) if len(valid_sub) >= 10 else None

        trap_c_cross_period[p] = {
            "count": len(trap_sub),
            "net_ev": float(trap_metrics["net_mean_return"]) if trap_metrics else None,
            "win_rate": float(trap_metrics["win_rate"]) if trap_metrics else None,
            "mean_mae": float(trap_sub["short_mae_24h"].mean()) if len(trap_sub) > 0 else None,
            "mean_mfe": float(trap_sub["short_mfe_24h"].mean()) if len(trap_sub) > 0 else None,
        }
        valid_c_cross_period[p] = {
            "count": len(valid_sub),
            "net_ev": float(valid_metrics["net_mean_return"]) if valid_metrics else None,
            "win_rate": float(valid_metrics["win_rate"]) if valid_metrics else None,
            "mean_mae": float(valid_sub["short_mae_24h"].mean()) if len(valid_sub) > 0 else None,
            "mean_mfe": float(valid_sub["short_mfe_24h"].mean()) if len(valid_sub) > 0 else None,
        }

    print("Signal C Trap Short Performance across periods:")
    for p, met in trap_c_cross_period.items():
        print(f"  {p}: Count={met['count']}, Net EV={met['net_ev']}, WinRate={met['win_rate']}, Mean MAE={met['mean_mae']}")
    print("Signal C Valid Short Performance across periods:")
    for p, met in valid_c_cross_period.items():
        print(f"  {p}: Count={met['count']}, Net EV={met['net_ev']}, WinRate={met['win_rate']}, Mean MAE={met['mean_mae']}")

    # =========================================================================
    # 5. Visualizations
    # =========================================================================
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="darkgrid")

    # Plot 1: Feature Differential Distributions
    print("\nGenerating Plot 1: Feature Differential Distributions...")
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    axes = axes.flatten()

    for idx, (feat_id, feat_label, col) in enumerate(diff_features_a):
        ax = axes[idx]
        s_data = sig_a_success[col].dropna()
        f_data = sig_a_failure[col].dropna()
        if len(s_data) > 0 and len(f_data) > 0 and s_data.std() > 0 and f_data.std() > 0:
            sns.kdeplot(s_data, ax=ax, label=f"Success (N={len(s_data)})", color="#2ecc71", fill=True, alpha=0.3)
            sns.kdeplot(f_data, ax=ax, label=f"Failure (N={len(f_data)})", color="#e74c3c", fill=True, alpha=0.3)
        d_val = stats_a[feat_id]["cohens_d"]
        p_val = stats_a[feat_id]["p_value"]
        sig_star = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "n.s."))
        ax.set_title(f"{feat_label}\nCohen's d = {d_val:.2f} ({sig_star})", fontsize=11, fontweight="bold")
        ax.legend(fontsize=9)

    plt.suptitle("Signal A (Breakout): Success vs Failure Feature Differential Distributions", fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(plots_dir / "01_success_vs_failure_feature_distributions.png", dpi=150)
    plt.close()

    # Plot 2: Negative Robustness of Invalidation Traps Across Eras
    print("Generating Plot 2: Negative Robustness Across Eras...")
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    eras = ["P1_Bull", "P2_Bear", "P3_Mixed"]

    # Subplot 1: Signal A Net EV
    ax = axes[0]
    valid_evs = [valid_a_cross_period[e]["net_ev"] if valid_a_cross_period[e]["net_ev"] is not None else 0 for e in eras]
    trap_evs = [trap_a_cross_period[e]["net_ev"] if trap_a_cross_period[e]["net_ev"] is not None else 0 for e in eras]
    x = np.arange(len(eras))
    width = 0.35
    ax.bar(x - width/2, valid_evs, width, label="Valid Filtered", color="#2ecc71", alpha=0.85)
    ax.bar(x + width/2, trap_evs, width, label="Trap Cases (Negative Edge)", color="#e74c3c", alpha=0.85)
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_title("Signal A (Breakout): Net EV Across Eras", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(eras)
    ax.set_ylabel("Net Mean Return (24h)")
    ax.legend()

    # Subplot 2: Signal B Net EV
    ax = axes[1]
    valid_evs_b = [valid_b_cross_period[e]["net_ev"] if valid_b_cross_period[e]["net_ev"] is not None else 0 for e in eras]
    trap_evs_b = [trap_b_cross_period[e]["net_ev"] if trap_b_cross_period[e]["net_ev"] is not None else 0 for e in eras]
    ax.bar(x - width/2, valid_evs_b, width, label="Valid Filtered", color="#3498db", alpha=0.85)
    ax.bar(x + width/2, trap_evs_b, width, label="Trap Cases (Negative Edge)", color="#e67e22", alpha=0.85)
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_title("Signal B (Bottleneck): Net EV Across Eras", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(eras)
    ax.legend()

    # Subplot 3: Signal C Short Net EV
    ax = axes[2]
    valid_evs_c = [valid_c_cross_period[e]["net_ev"] if valid_c_cross_period[e]["net_ev"] is not None else 0 for e in eras]
    trap_evs_c = [trap_c_cross_period[e]["net_ev"] if trap_c_cross_period[e]["net_ev"] is not None else 0 for e in eras]
    ax.bar(x - width/2, valid_evs_c, width, label="Valid Short (Meso Decel)", color="#9b59b6", alpha=0.85)
    ax.bar(x + width/2, trap_evs_c, width, label="Trap Short (Meso Accelerating)", color="#e74c3c", alpha=0.85)
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_title("Signal C (Gravity Short): Net EV Across Eras", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(eras)
    ax.legend()

    plt.suptitle("Negative Robustness Verification: Testing Consistency of Failure Traps Across Market Eras", fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(plots_dir / "02_negative_robustness_across_periods.png", dpi=150)
    plt.close()

    # Plot 3: Cumulative Return Impact of Invalidation Filter
    print("Generating Plot 3: Cumulative Return Impact of Invalidation Filter...")
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # Signal A
    ax = axes[0]
    sig_a_raw_curve = (1 + sig_a_events["fwd_ret_24h"] - friction_cost).cumprod()
    sig_a_valid_curve = (1 + sig_a_events[sig_a_events["is_valid"]]["fwd_ret_24h"] - friction_cost).cumprod()
    sig_a_trap_curve = (1 + sig_a_events[sig_a_events["is_trap"]]["fwd_ret_24h"] - friction_cost).cumprod()

    ax.plot(sig_a_raw_curve.index, sig_a_raw_curve.values, label=f"Unfiltered Raw (N={len(sig_a_raw_curve)})", color="gray", alpha=0.7)
    ax.plot(sig_a_valid_curve.index, sig_a_valid_curve.values, label=f"Valid Filtered (N={len(sig_a_valid_curve)})", color="#2ecc71", linewidth=2)
    ax.plot(sig_a_trap_curve.index, sig_a_trap_curve.values, label=f"Invalidation Trap Cases (N={len(sig_a_trap_curve)})", color="#e74c3c", linestyle="--")
    ax.set_title("Signal A: Cumulative Equity Curve with Invalidation Filter", fontweight="bold")
    ax.set_ylabel("Growth Factor (Base 1.0)")
    ax.legend()

    # Signal C
    ax = axes[1]
    sig_c_raw_curve = (1 + sig_c_events["short_ret_24h"] - friction_cost).cumprod()
    sig_c_valid_curve = (1 + sig_c_events[sig_c_events["is_valid"]]["short_ret_24h"] - friction_cost).cumprod()
    sig_c_trap_curve = (1 + sig_c_events[sig_c_events["is_trap"]]["short_ret_24h"] - friction_cost).cumprod()

    ax.plot(sig_c_raw_curve.index, sig_c_raw_curve.values, label=f"Unfiltered Short (N={len(sig_c_raw_curve)})", color="gray", alpha=0.7)
    ax.plot(sig_c_valid_curve.index, sig_c_valid_curve.values, label=f"Valid Filtered Short (N={len(sig_c_valid_curve)})", color="#9b59b6", linewidth=2)
    ax.plot(sig_c_trap_curve.index, sig_c_trap_curve.values, label=f"Trap Breached Short (N={len(sig_c_trap_curve)})", color="#e74c3c", linestyle="--")
    ax.set_title("Signal C: Gravity Wall Short Equity Curve", fontweight="bold")
    ax.set_ylabel("Growth Factor (Base 1.0)")
    ax.legend()

    plt.tight_layout()
    plt.savefig(plots_dir / "03_boundary_conditions_performance_impact.png", dpi=150)
    plt.close()

    # Plot 4: Decision Boundary Scatter in Relational Space
    print("Generating Plot 4: Decision Boundary Scatter in Relational Space...")
    fig, ax = plt.subplots(figsize=(10, 7))
    scatter = ax.scatter(
        sig_a_events["dist_sma_610"],
        sig_a_events["squeeze_index"],
        c=sig_a_events["fwd_ret_24h"],
        cmap="coolwarm_r",
        alpha=0.65,
        s=45,
        vmin=-0.04,
        vmax=0.04
    )
    plt.colorbar(scatter, label="24h Forward Return (Blue=Gain, Red=Loss)")
    ax.axvline(5.0, color="red", linestyle="--", alpha=0.8, label="Macro Extension Limit (+5.0 ATR)")
    ax.axhline(0.50, color="orange", linestyle="--", alpha=0.8, label="Squeeze Index Exhaustion Limit (0.50)")
    ax.fill_between([5.0, 15.0], 0, 1.0, color="red", alpha=0.1, label="Invalidation Trap Zone (Hyper-Extension)")
    ax.fill_between([-5.0, 15.0], 0.50, 1.0, color="orange", alpha=0.08, label="Invalidation Trap Zone (Exhausted Expansion)")
    ax.set_xlim(-2.0, 12.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Macro 610 Distance (ATR units)")
    ax.set_ylabel("Squeeze Index (0.0=Tight Compression, 1.0=Exhausted Expansion)")
    ax.set_title("Signal A State Space: Decision Boundaries for Valid Scope vs Invalidation Traps", fontweight="bold")
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(plots_dir / "04_differential_decision_space_scatter.png", dpi=150)
    plt.close()

    # =========================================================================
    # 6. Save Metrics JSON
    # =========================================================================
    metrics_output = {
        "experiment_id": config["experiment_id"],
        "signal_a_breakout": {
            "total_events": len(sig_a_events),
            "success_cases": len(sig_a_success),
            "failure_cases": len(sig_a_failure),
            "differential_feature_stats": stats_a,
            "trap_negative_robustness": trap_a_cross_period,
            "valid_positive_robustness": valid_a_cross_period,
            "invalidation_criteria": "squeeze_index > 0.50 OR dist_sma_610 > 5.0"
        },
        "signal_b_bottleneck": {
            "total_events": len(sig_b_events),
            "success_cases": len(sig_b_success),
            "failure_cases": len(sig_b_failure),
            "differential_feature_stats": stats_b,
            "trap_negative_robustness": trap_b_cross_period,
            "valid_positive_robustness": valid_b_cross_period,
            "invalidation_criteria": "squeeze_index > 0.40 OR slope_233 < -0.01"
        },
        "signal_c_gravity_short": {
            "total_events": len(sig_c_events),
            "success_cases": len(sig_c_success),
            "failure_cases": len(sig_c_failure),
            "differential_feature_stats": stats_c,
            "trap_negative_robustness": trap_c_cross_period,
            "valid_positive_robustness": valid_c_cross_period,
            "invalidation_criteria": "slope_34 > 0.035"
        }
    }

    with open(exp_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_output, f, indent=2)

    print(f"\nExperiment complete. Metrics saved to {exp_dir / 'metrics.json'}")
    return metrics_output


if __name__ == "__main__":
    exp_dir = Path(__file__).resolve().parent
    run_experiment(exp_dir)
