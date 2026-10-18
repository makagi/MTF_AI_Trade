"""
Reproducible Experiment Script for Issue #53
Geometric Relationships and State Classification of Adjacent Fibonacci Triplets (EXP-53-001).
"""

from pathlib import Path
import sys
import json
import yaml
import numpy as np
import pandas as pd

# Add repo root to sys.path
repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from src.data_loader import load_ohlcv
from src.features import calculate_sma, calculate_atr
from src.evaluation import evaluate_returns


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
    min_sample_size = int(config["thresholds"]["min_sample_size"])

    print(f"--- Running Experiment {config['experiment_id']} ---")
    print(f"Loading {symbol} {timeframe} data...")

    df = load_ohlcv(symbol=symbol, timeframe=timeframe)
    df = df.loc[start_date:end_date].copy()
    print(f"Discovery dataset size: {len(df)} bars ({df.index[0]} to {df.index[-1]})")

    close = df["close"]
    open_p = df["open"]
    high = df["high"]
    low = df["low"]

    # =========================================================================
    # 1. Fibonacci SMAs & ATR
    # =========================================================================
    print("Calculating Fibonacci SMAs and ATR...")
    atr_24 = calculate_atr(df, 24)
    df["atr_24"] = atr_24

    all_fibs = [8, 13, 21, 34, 55, 89, 233, 377, 610]
    for p in all_fibs:
        df[f"sma_{p}"] = calculate_sma(close, p)

    # Slopes (normalized by 12-bar delta / ATR)
    for p in all_fibs:
        df[f"slope_{p}"] = (df[f"sma_{p}"] - df[f"sma_{p}"].shift(12)) / (12 * atr_24)

    # Forward returns & MFE / MAE
    df["fwd_ret_24"] = (close.shift(-horizon) - close) / close
    df["fwd_short_ret_24"] = (close - close.shift(-horizon)) / close

    fwd_high = high.iloc[::-1].rolling(window=horizon, min_periods=1).max().iloc[::-1].shift(-1)
    fwd_low = low.iloc[::-1].rolling(window=horizon, min_periods=1).min().iloc[::-1].shift(-1)
    df["mfe_long"] = (fwd_high - close) / close
    df["mae_long"] = (close - fwd_low) / close
    df["mfe_short"] = (close - fwd_low) / close
    df["mae_short"] = (fwd_high - close) / close

    # =========================================================================
    # 2. Geometric Dimensions for Adjacent Triplets
    # =========================================================================
    print("Computing Geometric Dimensions (Order, Slopes, Curvature Spacing)...")

    # Macro Triplet: 233, 377, 610
    ma_A, ma_B, ma_C = df["sma_233"], df["sma_377"], df["sma_610"]
    df["macro_order_bull"] = (ma_A > ma_B) & (ma_B > ma_C)
    df["macro_order_bear"] = (ma_A < ma_B) & (ma_B < ma_C)
    df["macro_all_slopes_up"] = (df["slope_233"] > 0) & (df["slope_377"] > 0) & (df["slope_610"] > 0)
    df["macro_decel_brake"] = (df["slope_610"] > 0) & (df["slope_377"] > 0) & (df["slope_233"] < 0)
    
    macro_d_inner = (ma_A - ma_B).abs()
    macro_d_outer = (ma_B - ma_C).abs()
    df["macro_curvature_ratio"] = macro_d_inner / (macro_d_outer + 0.05 * atr_24)

    # Meso Triplet: 34, 55, 89
    me_A, me_B, me_C = df["sma_34"], df["sma_55"], df["sma_89"]
    df["meso_order_bull"] = (me_A > me_B) & (me_B > me_C)
    df["meso_order_bear"] = (me_A < me_B) & (me_B < me_C)
    df["meso_all_slopes_up"] = (df["slope_34"] > 0) & (df["slope_55"] > 0) & (df["slope_89"] > 0)
    df["meso_decel_brake"] = (df["slope_89"] > 0) & (df["slope_55"] > 0) & (df["slope_34"] < 0)
    
    meso_d_inner = (me_A - me_B).abs()
    meso_d_outer = (me_B - me_C).abs()
    df["meso_curvature_ratio"] = meso_d_inner / (meso_d_outer + 0.05 * atr_24)

    # Micro Triplet: 8, 13, 21
    mi_A, mi_B, mi_C = df["sma_8"], df["sma_13"], df["sma_21"]
    df["micro_order_bull"] = (mi_A > mi_B) & (mi_B > mi_C)
    df["micro_order_bear"] = (mi_A < mi_B) & (mi_B < mi_C)
    df["micro_all_slopes_up"] = (df["slope_8"] > 0) & (df["slope_13"] > 0) & (df["slope_21"] > 0)

    # =========================================================================
    # 3. Define Relational States
    # =========================================================================
    print("Classifying Relational States...")

    # State 1: Meso Re-acceleration (Relational Re-acceleration)
    # Meso had deceleration brake (slope_34 < 0), now slope_34 turns positive,
    # while Macro maintains Bull order & positive slope
    meso_reignite = (df["slope_34"] > 0) & (df["slope_34"].shift(1) <= 0) & df["macro_order_bull"] & (df["slope_377"] > 0)
    df["state_1_meso_reignite"] = meso_reignite

    # State 2: Inner Bottleneck Spring (Compression between 34 and 55)
    # Curvature ratio < 0.25 (34 & 55 pinched close together) under Macro Bull, then price bounces above 34
    inner_pinched = df["meso_curvature_ratio"] < float(config["thresholds"]["inner_bottleneck_ratio"])
    bounce_trigger = (close > me_A) & (close.shift(1) <= me_A.shift(1)) & df["macro_order_bull"]
    df["state_2_inner_bottleneck_spring"] = inner_pinched.shift(1) & bounce_trigger

    # State 3: Outer Climax Exhaustion (Over-extension of 34 vs 55/89)
    # Curvature ratio > 2.5 (34 blown far away from 55 while 55/89 are compressed) -> Mean Reversion Short
    outer_climax = df["meso_curvature_ratio"] > float(config["thresholds"]["outer_climax_ratio"])
    climax_exhaust = outer_climax & (close < close.shift(1)) & (df["slope_34"] < df["slope_34"].shift(1))
    df["state_3_outer_climax_short"] = climax_exhaust

    # State 4: Macro Triplet Twist Breakdown (233 crosses below 377)
    # Initial bear twist after established bull order
    macro_bull_prev = df["macro_order_bull"].rolling(48).min() == 1
    macro_twist = (ma_A < ma_B) & (ma_A.shift(1) >= ma_B.shift(1))
    df["state_4_macro_twist_short"] = macro_bull_prev.shift(1) & macro_twist

    # State 5: Triple Triplet Full Alignment (Micro + Meso + Macro all Bull Expand & All Slopes Up)
    df["state_5_triple_full_alignment"] = (
        df["micro_order_bull"] & df["micro_all_slopes_up"] &
        df["meso_order_bull"] & df["meso_all_slopes_up"] &
        df["macro_order_bull"] & df["macro_all_slopes_up"]
    )
    # Initial entry into full alignment
    df["state_5_triple_align_entry"] = df["state_5_triple_full_alignment"] & (~df["state_5_triple_full_alignment"].shift(1).fillna(False))

    # State 6: Meso Deceleration Brake (In-progress Pullback)
    # For context observation: Price in pull-back while Macro is Bull
    df["state_6_meso_pullback_brake"] = df["meso_decel_brake"] & df["macro_order_bull"]

    # Filter NaNs
    eval_df = df.dropna(subset=["fwd_ret_24", "fwd_short_ret_24", "sma_610"]).copy()

    # =========================================================================
    # 4. Quantitative Evaluation
    # =========================================================================
    print("Evaluating pattern metrics across Full Discovery and 3 periods...")

    states = {
        "State_1_Meso_Reacceleration_Long": {"col": "state_1_meso_reignite", "direction": "long"},
        "State_2_Inner_Bottleneck_Spring_Long": {"col": "state_2_inner_bottleneck_spring", "direction": "long"},
        "State_3_Outer_Climax_Short": {"col": "state_3_outer_climax_short", "direction": "short"},
        "State_4_Macro_Twist_Short": {"col": "state_4_macro_twist_short", "direction": "short"},
        "State_5_Triple_Alignment_Long": {"col": "state_5_triple_align_entry", "direction": "long"},
        "State_6_Meso_Pullback_Brake_Context": {"col": "state_6_meso_pullback_brake", "direction": "long"},
    }

    results = {}

    def calc_metrics(sub_df, state_name, meta):
        col = meta["col"]
        direction = meta["direction"]
        events = sub_df[sub_df[col] == True]
        n_samples = len(events)
        if n_samples == 0:
            return {
                "n_samples": 0,
                "gross_ev_pct": 0.0,
                "net_ev_pct": 0.0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "mean_mfe_pct": 0.0,
                "mean_mae_pct": 0.0,
                "sample_sufficient": False,
            }

        if direction == "long":
            raw_ret = events["fwd_ret_24"]
            mfe = events["mfe_long"] * 100
            mae = events["mae_long"] * 100
        else:
            raw_ret = events["fwd_short_ret_24"]
            mfe = events["mfe_short"] * 100
            mae = events["mae_short"] * 100

        net_ret = raw_ret - friction_cost
        wins = net_ret[net_ret > 0]
        losses = net_ret[net_ret < 0]

        gross_ev = float(raw_ret.mean() * 100)
        net_ev = float(net_ret.mean() * 100)
        win_rate = float((len(wins) / n_samples) * 100)
        
        sum_wins = float(wins.sum())
        sum_losses = float(abs(losses.sum()))
        pf = float(sum_wins / sum_losses) if sum_losses > 0 else (999.0 if sum_wins > 0 else 0.0)

        return {
            "n_samples": int(n_samples),
            "gross_ev_pct": round(gross_ev, 3),
            "net_ev_pct": round(net_ev, 3),
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(pf, 3),
            "mean_mfe_pct": round(float(mfe.mean()), 3),
            "mean_mae_pct": round(float(mae.mean()), 3),
            "sample_sufficient": bool(n_samples >= min_sample_size),
        }

    for s_name, meta in states.items():
        results[s_name] = {
            "direction": meta["direction"],
            "full_discovery": calc_metrics(eval_df, s_name, meta),
            "periods": {},
        }
        for p_key, p_val in periods_cfg.items():
            p_sub = eval_df.loc[p_val["start"]:p_val["end"]]
            results[s_name]["periods"][p_key] = calc_metrics(p_sub, s_name, meta)

    # Save metrics.json (SPEC-EVAL-001 compliant)
    # Primary evaluation: State 1 Meso Re-acceleration
    primary_events = eval_df[eval_df["state_1_meso_reignite"] == True]
    primary_eval = evaluate_returns(primary_events["fwd_ret_24"], cost=friction_cost)

    out_metrics = dict(primary_eval)
    out_metrics["pattern_name"] = "EXP-53: Meso Re-acceleration under Macro Bull"
    out_metrics["all_states"] = results

    metrics_path = exp_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(out_metrics, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to {metrics_path}")

    # =========================================================================
    # 5. Visual Evidence Plots
    # =========================================================================
    print("Generating visual evidence plots...")
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(exist_ok=True)
    sns.set_theme(style="whitegrid")

    labels = ["Full", "P1 (Bull)", "P2 (Bear)", "P3 (Recov)"]
    x = np.arange(len(labels))
    width = 0.35

    # Plot 1: Curvature Ratio Distribution & State 2 Bottleneck Spring
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Histogram of Meso Curvature Ratio
    valid_curv = eval_df["meso_curvature_ratio"].dropna()
    valid_curv = valid_curv[valid_curv < 5.0]
    sns.histplot(valid_curv, bins=50, kde=True, ax=axes[0], color="#1f77b4")
    axes[0].axvline(0.25, color="red", linestyle="--", label="Inner Bottleneck (<0.25)")
    axes[0].axvline(2.5, color="purple", linestyle="--", label="Outer Climax (>2.5)")
    axes[0].axvline(0.618, color="green", linestyle=":", label="Golden Mean (~0.618)")
    axes[0].set_title("Meso (34-55-89) Curvature Ratio Distribution", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("Curvature Ratio: |34-55| / (|55-89| + ε)")
    axes[0].legend()

    # Net EV of State 2 Inner Bottleneck Spring
    s2_evs = [results["State_2_Inner_Bottleneck_Spring_Long"]["full_discovery"]["net_ev_pct"]] + [
        results["State_2_Inner_Bottleneck_Spring_Long"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    axes[1].bar(labels, s2_evs, color=["#2ca02c" if v > 0 else "#d62728" for v in s2_evs])
    axes[1].axhline(0, color="black", linestyle="--")
    axes[1].set_ylabel("Net EV (%) after 0.40% friction")
    axes[1].set_title("State 2: Inner Bottleneck Spring Net EV Across Eras", fontsize=12, fontweight="bold")
    for i, v in enumerate(s2_evs):
        axes[1].text(i, v + (0.05 if v >= 0 else -0.15), f"{v:+.2f}%", ha="center", fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "01_curvature_distribution_and_effects.png", dpi=150)
    plt.close()

    # Plot 2: State 1 (Meso Re-acceleration) vs State 5 (Triple Alignment)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    s1_evs = [results["State_1_Meso_Reacceleration_Long"]["full_discovery"]["net_ev_pct"]] + [
        results["State_1_Meso_Reacceleration_Long"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    s5_evs = [results["State_5_Triple_Alignment_Long"]["full_discovery"]["net_ev_pct"]] + [
        results["State_5_Triple_Alignment_Long"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    axes[0].bar(x - width/2, s1_evs, width, label="State 1: Meso Re-acceleration", color="#2ca02c")
    axes[0].bar(x + width/2, s5_evs, width, label="State 5: Triple Alignment Entry", color="#1f77b4")
    axes[0].axhline(0, color="black", linestyle="--")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_ylabel("Net EV (%) after 0.40% friction")
    axes[0].set_title("Re-acceleration vs Full Alignment Net EV Comparison", fontsize=12, fontweight="bold")
    axes[0].legend()

    # MFE vs MAE profile
    mfe_s1 = results["State_1_Meso_Reacceleration_Long"]["full_discovery"]["mean_mfe_pct"]
    mae_s1 = results["State_1_Meso_Reacceleration_Long"]["full_discovery"]["mean_mae_pct"]
    mfe_s5 = results["State_5_Triple_Alignment_Long"]["full_discovery"]["mean_mfe_pct"]
    mae_s5 = results["State_5_Triple_Alignment_Long"]["full_discovery"]["mean_mae_pct"]

    bars_x = np.arange(2)
    axes[1].bar(bars_x - width/2, [mfe_s1, mfe_s5], width, label="Mean MFE (Upside)", color="#2ca02c")
    axes[1].bar(bars_x + width/2, [mae_s1, mae_s5], width, label="Mean MAE (Drawdown)", color="#d62728")
    axes[1].set_xticks(bars_x)
    axes[1].set_xticklabels(["State 1 (Re-accel)", "State 5 (Triple Align)"])
    axes[1].set_ylabel("Percentage (%)")
    axes[1].set_title("Risk-Reward Profile (Full Discovery)", fontsize=12, fontweight="bold")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(plots_dir / "02_reacceleration_vs_alignment.png", dpi=150)
    plt.close()

    # Plot 3: Cross-Period Consistency Heatmap for all Triplet States
    fig, ax = plt.subplots(figsize=(13, 6))
    matrix_rows = list(states.keys())
    matrix_data = []
    annot_data = []
    for r in matrix_rows:
        row_vals = [results[r]["full_discovery"]["net_ev_pct"]] + [
            results[r]["periods"][p]["net_ev_pct"] for p in periods_cfg
        ]
        row_samples = [results[r]["full_discovery"]["n_samples"]] + [
            results[r]["periods"][p]["n_samples"] for p in periods_cfg
        ]
        matrix_data.append(row_vals)
        annot_data.append([f"{v:+.2f}%\n(N={n})" for v, n in zip(row_vals, row_samples)])

    sns.heatmap(
        matrix_data,
        annot=np.array(annot_data),
        fmt="",
        cmap="RdYlGn",
        center=0,
        cbar_kws={"label": "Net EV (%) after 0.40% friction"},
        xticklabels=labels,
        yticklabels=[r.replace("_", " ") for r in matrix_rows],
        ax=ax,
    )
    ax.set_title("EXP-53: Fibonacci Adjacent Triplet Relational States - Consistency Matrix", fontsize=13, fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "03_triplet_cross_period_consistency_matrix.png", dpi=150)
    plt.close()

    print("All plots generated successfully.")
    print(f"--- Experiment {config['experiment_id']} Completed ---")


if __name__ == "__main__":
    exp_dir = Path(__file__).resolve().parent
    run_experiment(exp_dir)
