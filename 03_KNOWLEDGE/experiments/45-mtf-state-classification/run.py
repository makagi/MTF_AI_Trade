"""
Reproducible Experiment Script for Issue #45
MTF 3-Tier State Classification & Regime Transition Analysis.
"""

from pathlib import Path
import json
import yaml
import numpy as np
import pandas as pd

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
    calculate_afs,
    calculate_fanout_velocity,
)
from src.evaluation import evaluate_returns, evaluate_yearly_breakdown


def run_experiment(exp_dir: Path):
    with open(exp_dir / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    symbol = config.get("symbol") or config["data"]["symbol"]
    timeframe = config.get("timeframe") or config["data"]["timeframe"]
    start_date = config["data"]["start_date"]
    end_date = config["data"]["end_date"]
    friction_cost = float(config["parameters"]["friction_cost"])
    horizon = int(config["parameters"]["forward_horizon_bars"])

    print(f"--- Running Experiment {config['experiment_id']} ---")
    print(f"Loading {symbol} {timeframe} data...")

    df = load_ohlcv(symbol=symbol, timeframe=timeframe)
    df = df.loc[start_date:end_date].copy()
    print(f"Discovery dataset size: {len(df)} bars ({df.index[0]} to {df.index[-1]})")

    # =========================================================================
    # 1. Feature Calculations (MTF 3-Tier Architecture)
    # =========================================================================
    print("Calculating MTF 3-Tier features...")
    close = df["close"]

    # Tier 1: Macro (Long-term trend & Gravity)
    df["sma_377"] = calculate_sma(close, 377)
    df["sma_377_slope"] = (df["sma_377"] - df["sma_377"].shift(24)) / close
    df["macro_bull"] = (close > df["sma_377"]) & (df["sma_377_slope"] > 0)
    df["macro_bear"] = (close < df["sma_377"]) & (df["sma_377_slope"] < 0)

    # Tier 2: Meso (Volatility & Structure)
    df["sma_21"] = calculate_sma(close, 21)
    df["sma_89"] = calculate_sma(close, 89)
    df["atr"] = calculate_atr(df, period=14)
    df["squeeze_index"] = calculate_squeeze_index(df, periods=[21, 55, 144, 377], lookback_bars=720)
    df["dist_sma_89_atr"] = (close - df["sma_89"]) / (df["atr"] + 1e-8)

    # Tier 3: Micro (Momentum & Flow)
    afs_df, order_score, compression = calculate_afs(df, periods=[7, 9, 11, 13])
    df["afs_7"] = afs_df["AFS_7"]
    df["afs_order"] = order_score
    df["fanout_vel"] = calculate_fanout_velocity(df, fast_period=21, slow_period=89, atr_period=14)

    # =========================================================================
    # 2. State Classification (6 Mutually Exclusive Regimes)
    # =========================================================================
    print("Classifying market states into 6 MTF Regimes...")
    regimes = pd.Series(index=df.index, dtype=object)

    for i in range(len(df)):
        m_bull = df["macro_bull"].iloc[i]
        m_bear = df["macro_bear"].iloc[i]
        sq = df["squeeze_index"].iloc[i]
        d_89 = df["dist_sma_89_atr"].iloc[i]
        a_ord = df["afs_order"].iloc[i]
        a_7 = df["afs_7"].iloc[i]

        if pd.isna(m_bull) or pd.isna(sq) or pd.isna(d_89) or pd.isna(a_7):
            regimes.iloc[i] = "Unclassified"
            continue

        # Priority 1: Extreme Squeeze (Energy Coil)
        if sq < 0.15:
            regimes.iloc[i] = "Squeeze_Pre_Breakout"
        # Priority 2: Panic Exhaustion (Severe selloff)
        elif m_bear and d_89 < -2.5 and a_7 < 30:
            regimes.iloc[i] = "Bear_Panic_Exhaustion"
        # Priority 3: Healthy Bull Pullback
        elif m_bull and (-2.0 <= d_89 <= 0.5) and a_7 < 40:
            regimes.iloc[i] = "Bull_Healthy_Pullback"
        # Priority 4: Bull Continuation
        elif m_bull and a_ord >= 2:
            regimes.iloc[i] = "Bull_Trend_Continuation"
        # Priority 5: Bear Continuation
        elif m_bear and a_ord == 0:
            regimes.iloc[i] = "Bear_Trend_Continuation"
        # Default: Range / PingPong
        else:
            regimes.iloc[i] = "Range_PingPong"

    df["regime"] = regimes
    valid_df = df[df["regime"] != "Unclassified"].copy()

    # =========================================================================
    # 3. Frequency & Duration Analysis
    # =========================================================================
    print("\n=======================================================")
    print("--- MTF Regime Distribution & Duration Statistics ---")
    print("=======================================================")

    regime_names = [
        "Bull_Trend_Continuation",
        "Bull_Healthy_Pullback",
        "Squeeze_Pre_Breakout",
        "Bear_Trend_Continuation",
        "Bear_Panic_Exhaustion",
        "Range_PingPong",
    ]

    total_valid_bars = len(valid_df)
    regime_stats = []

    # Calculate streak durations
    streak_records = {r: [] for r in regime_names}
    curr_r = None
    curr_len = 0
    for r in valid_df["regime"]:
        if r == curr_r:
            curr_len += 1
        else:
            if curr_r in streak_records:
                streak_records[curr_r].append(curr_len)
            curr_r = r
            curr_len = 1
    if curr_r in streak_records:
        streak_records[curr_r].append(curr_len)

    for r in regime_names:
        bars_count = (valid_df["regime"] == r).sum()
        pct = (bars_count / total_valid_bars) * 100
        durations = streak_records[r]
        mean_dur = float(np.mean(durations)) if durations else 0.0
        med_dur = float(np.median(durations)) if durations else 0.0
        max_dur = int(np.max(durations)) if durations else 0

        stat_entry = {
            "regime": r,
            "total_bars": int(bars_count),
            "percentage": float(pct),
            "occurrences": len(durations),
            "mean_duration_hours": mean_dur,
            "median_duration_hours": med_dur,
            "max_duration_hours": max_dur,
        }
        regime_stats.append(stat_entry)
        print(f"[{r:<24}] Bars: {bars_count:>5} ({pct:>5.1f}%) | Occurrences: {len(durations):>4} | MeanDur: {mean_dur:>5.1f}h (Med: {med_dur:>4.1f}h, Max: {max_dur:>4}h)")

    # =========================================================================
    # 4. State Transition Probability Matrix
    # =========================================================================
    print("\n=======================================================")
    print("--- State Transition Probability Matrix (%) ---")
    print("=======================================================")

    trans_counts = pd.DataFrame(0, index=regime_names, columns=regime_names)
    r_series = valid_df["regime"].values
    for k in range(len(r_series) - 1):
        from_r = r_series[k]
        to_r = r_series[k + 1]
        if from_r in regime_names and to_r in regime_names and from_r != to_r:
            trans_counts.loc[from_r, to_r] += 1

    trans_prob = trans_counts.div(trans_counts.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * 100
    print(trans_prob.round(1).to_string())

    # =========================================================================
    # 5. Forward Performance & Behavior by Regime (24h Horizon)
    # =========================================================================
    print("\n=======================================================")
    print("--- Forward Performance & Risk Profile by Regime ---")
    print("=======================================================")

    fwd_returns_all = (valid_df["close"].shift(-horizon) - valid_df["close"]) / valid_df["close"]

    # Track Forward MFE / MAE
    fwd_mfe_all = []
    fwd_mae_all = []
    for idx_pos in range(len(valid_df) - horizon):
        entry_p = valid_df["close"].iloc[idx_pos]
        window = valid_df.iloc[idx_pos + 1 : idx_pos + 1 + horizon]
        fwd_mfe_all.append((window["high"].max() - entry_p) / entry_p)
        fwd_mae_all.append((window["low"].min() - entry_p) / entry_p)

    valid_subset = valid_df.iloc[:-horizon].copy()
    valid_subset["fwd_return"] = fwd_returns_all.iloc[:-horizon]
    valid_subset["fwd_mfe"] = fwd_mfe_all
    valid_subset["fwd_mae"] = fwd_mae_all

    regime_forward_profiles = []
    for r in regime_names:
        sub = valid_subset[valid_subset["regime"] == r]
        if len(sub) == 0:
            continue
        g_mean = float(sub["fwd_return"].mean())
        net_mean = float(g_mean - friction_cost)
        win_rate = float((sub["fwd_return"] > friction_cost).mean())
        mfe_mean = float(sub["fwd_mfe"].mean())
        mae_mean = float(sub["fwd_mae"].mean())

        profile = {
            "regime": r,
            "samples": len(sub),
            "gross_mean_return": g_mean,
            "net_mean_return": net_mean,
            "win_rate": win_rate,
            "mfe_mean": mfe_mean,
            "mae_mean": mae_mean,
        }
        regime_forward_profiles.append(profile)
        print(f"[{r:<24}] Samples: {len(sub):>5} | GrossMean: {g_mean*100:>+5.2f}% | NetMean: {net_mean*100:>+5.2f}% | WinRate: {win_rate*100:>4.1f}% | MFE: {mfe_mean*100:>+4.2f}% | MAE: {mae_mean*100:>+4.2f}%")

    # =========================================================================
    # 6. Overall Evaluation Metrics for Gate Contract
    # =========================================================================
    # Execute a baseline context-guided trade evaluation to satisfy SPEC-EVAL-001
    pullback_sub = valid_subset[valid_subset["regime"] == "Bull_Healthy_Pullback"]["fwd_return"]
    eval_metrics = evaluate_returns(pullback_sub, cost=friction_cost)

    eval_metrics["regime_distribution"] = regime_stats
    eval_metrics["transition_probabilities_percent"] = trans_prob.to_dict()
    eval_metrics["regime_forward_profiles"] = regime_forward_profiles

    # Save metrics.json
    out_metrics_path = exp_dir / "metrics.json"
    with open(out_metrics_path, "w", encoding="utf-8") as f:
        json.dump(eval_metrics, f, indent=2, ensure_ascii=False)
    print(f"\nSaved MTF state classification metrics to {out_metrics_path}")

    # =========================================================================
    # 7. Generate Visualizations (Plots)
    # =========================================================================
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    generate_visualizations(valid_df, regime_stats, trans_prob, regime_forward_profiles, plots_dir)

    return eval_metrics


def generate_visualizations(df: pd.DataFrame, regime_stats: list, trans_prob: pd.DataFrame, forward_profiles: list, plots_dir: Path):
    """Generate high-clarity visual evidence and profile plots for the MTF state classification."""
    print("\nGenerating visual artifacts and plots in:", plots_dir)
    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

    # Color palette for regimes
    regime_colors = {
        "Bull_Trend_Continuation": "#2ca02c",  # Green
        "Bull_Healthy_Pullback": "#1f77b4",    # Blue
        "Squeeze_Pre_Breakout": "#ff7f0e",     # Orange
        "Range_PingPong": "#7f7f7f",           # Gray
        "Bear_Trend_Continuation": "#d62728",  # Red
        "Bear_Panic_Exhaustion": "#9467bd",    # Purple
    }

    # -------------------------------------------------------------------------
    # Plot 1: Regime Distribution (Overall & Yearly Breakdown)
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [1, 1.3]})

    # 1A: Overall Percentage (Horizontal Bar)
    stat_df = pd.DataFrame(regime_stats)
    stat_df = stat_df.sort_values("percentage", ascending=True)
    colors = [regime_colors.get(r, "#333333") for r in stat_df["regime"]]
    bars = ax1.barh(stat_df["regime"], stat_df["percentage"], color=colors, height=0.6, edgecolor="black", linewidth=0.8)
    ax1.set_xlabel("Percentage of Time (%)", fontsize=11, fontweight="bold")
    ax1.set_title("Overall Market Time Distribution (4 Years, 35k Hours)", fontsize=12, fontweight="bold")
    for bar, pct, bars_cnt in zip(bars, stat_df["percentage"], stat_df["total_bars"]):
        ax1.text(pct + 0.8, bar.get_y() + bar.get_height()/2, f"{pct:.1f}% ({bars_cnt:,}h)", va="center", fontsize=10, fontweight="bold")
    ax1.set_xlim(0, max(stat_df["percentage"]) * 1.25)

    # 1B: Yearly Distribution Breakdown
    df_copy = df.copy()
    df_copy["year"] = df_copy.index.year
    yearly_dist = pd.crosstab(df_copy["year"], df_copy["regime"], normalize="index") * 100
    regime_order = [r for r in regime_colors.keys() if r in yearly_dist.columns]
    yearly_dist = yearly_dist[regime_order]

    yearly_dist.plot(
        kind="bar",
        stacked=True,
        ax=ax2,
        color=[regime_colors[r] for r in regime_order],
        edgecolor="black",
        linewidth=0.8,
        width=0.6,
    )
    ax2.set_title("Yearly Regime Composition (2021 - 2024)", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Year", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Share (%)", fontsize=11, fontweight="bold")
    ax2.set_xticklabels(yearly_dist.index, rotation=0, fontsize=10, fontweight="bold")
    ax2.legend(title="Regime", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=True)

    plt.tight_layout()
    plot1_path = plots_dir / "01_regime_distribution.png"
    plt.savefig(plot1_path, dpi=200)
    plt.close()
    print(f" -> Saved: {plot1_path.name}")

    # -------------------------------------------------------------------------
    # Plot 2: Regime Transition Probability Heatmap
    # -------------------------------------------------------------------------
    plt.figure(figsize=(10, 8))
    ax = sns.heatmap(
        trans_prob,
        annot=True,
        fmt=".1f",
        cmap="YlGnBu",
        cbar_kws={"label": "Transition Probability (%)"},
        linewidths=1.2,
        linecolor="white",
        annot_kws={"fontsize": 11, "fontweight": "bold"},
    )
    plt.title("Markov Regime Transition Probability Matrix (%)\n(From Current State -> To Next State)", fontsize=13, fontweight="bold", pad=15)
    plt.xlabel("Next Regime (To State)", fontsize=11, fontweight="bold", labelpad=10)
    plt.ylabel("Current Regime (From State)", fontsize=11, fontweight="bold", labelpad=10)
    plt.xticks(rotation=30, ha="right", fontsize=9, fontweight="bold")
    plt.yticks(rotation=0, fontsize=9, fontweight="bold")
    plt.tight_layout()
    plot2_path = plots_dir / "02_regime_transition_heatmap.png"
    plt.savefig(plot2_path, dpi=200)
    plt.close()
    print(f" -> Saved: {plot2_path.name}")

    # -------------------------------------------------------------------------
    # Plot 3: Forward Risk-Return Profile (MFE vs MAE and Net EV)
    # -------------------------------------------------------------------------
    prof_df = pd.DataFrame(forward_profiles)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # 3A: MFE vs MAE Horizontal Bar Chart
    y_pos = np.arange(len(prof_df))
    mfe_pct = prof_df["mfe_mean"] * 100
    mae_pct = prof_df["mae_mean"] * 100

    ax1.barh(y_pos, mfe_pct, color="#2ca02c", height=0.4, align="center", label="Mean 24h MFE (Upside Potential)")
    ax1.barh(y_pos, mae_pct, color="#d62728", height=0.4, align="center", label="Mean 24h MAE (Downside Drawdown)")
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(prof_df["regime"], fontsize=10, fontweight="bold")
    ax1.axvline(0, color="black", linestyle="--", linewidth=1)
    ax1.set_xlabel("Mean Return / Risk (%)", fontsize=11, fontweight="bold")
    ax1.set_title("24h Forward MFE (Favorable) vs MAE (Adverse)", fontsize=12, fontweight="bold")
    ax1.legend(loc="lower right", frameon=True)

    # 3B: Gross EV vs Net EV (Friction Deducted)
    gross_pct = prof_df["gross_mean_return"] * 100
    net_pct = prof_df["net_mean_return"] * 100
    width = 0.35

    ax2.bar(y_pos - width/2, gross_pct, width=width, color="#4a90e2", label="Gross Expected Value (%)")
    ax2.bar(y_pos + width/2, net_pct, width=width, color="#f5a623", label="Net Expected Value (-0.40% Cost)")
    ax2.set_xticks(y_pos)
    ax2.set_xticklabels(prof_df["regime"], rotation=35, ha="right", fontsize=9, fontweight="bold")
    ax2.axhline(0, color="black", linestyle="-", linewidth=0.8)
    ax2.set_ylabel("24h Forward Return (%)", fontsize=11, fontweight="bold")
    ax2.set_title("Gross EV vs Net EV by Regime (Unfiltered Baseline)", fontsize=12, fontweight="bold")
    ax2.legend(loc="upper right", frameon=True)

    plt.tight_layout()
    plot3_path = plots_dir / "03_regime_risk_return_profile.png"
    plt.savefig(plot3_path, dpi=200)
    plt.close()
    print(f" -> Saved: {plot3_path.name}")

    # -------------------------------------------------------------------------
    # Plot 4: Historical Timeline Case Study (2023 Q4 ETF Breakout Window)
    # -------------------------------------------------------------------------
    # Select high-interest window: 2023-10-15 to 2023-12-15 (approx 1,500 hours)
    sample_df = df.loc["2023-10-15":"2023-12-15"].copy()
    if len(sample_df) > 100:
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 9), sharex=True, gridspec_kw={"height_ratios": [2.5, 1, 1]})

        # Panel 1: Price and SMAs with Regime Background Highlights
        ax1.plot(sample_df.index, sample_df["close"], label="BTC Close", color="black", linewidth=1.2, zorder=5)
        ax1.plot(sample_df.index, sample_df["sma_21"], label="SMA 21 (Meso Short)", color="#3498db", linewidth=1.0, alpha=0.9, zorder=4)
        ax1.plot(sample_df.index, sample_df["sma_89"], label="SMA 89 (Meso Mid)", color="#e67e22", linewidth=1.1, alpha=0.9, zorder=4)
        ax1.plot(sample_df.index, sample_df["sma_377"], label="SMA 377 (Macro Gravity)", color="#9b59b6", linewidth=1.3, linestyle="--", zorder=4)

        # Background color shading by regime
        curr_reg = None
        start_idx = None
        for idx, reg in sample_df["regime"].items():
            if reg != curr_reg:
                if curr_reg is not None and start_idx is not None:
                    ax1.axvspan(start_idx, idx, color=regime_colors.get(curr_reg, "#cccccc"), alpha=0.22, lw=0)
                curr_reg = reg
                start_idx = idx
        if curr_reg is not None and start_idx is not None:
            ax1.axvspan(start_idx, sample_df.index[-1], color=regime_colors.get(curr_reg, "#cccccc"), alpha=0.22, lw=0)

        ax1.set_title("BTC Price, Fibonacci SMAs & MTF Regimes (2023 Q4 ETF Breakout Case Study)", fontsize=13, fontweight="bold")
        ax1.set_ylabel("Price (USD)", fontsize=10, fontweight="bold")
        ax1.legend(loc="upper left", frameon=True, fontsize=9)

        # Panel 2: Squeeze Index
        ax2.plot(sample_df.index, sample_df["squeeze_index"], label="Squeeze Index", color="#e67e22", linewidth=1.1)
        ax2.axhline(0.15, color="red", linestyle="--", linewidth=1.0, label="Squeeze Threshold (0.15)")
        ax2.set_ylabel("Squeeze Idx", fontsize=10, fontweight="bold")
        ax2.set_ylim(-0.05, 1.05)
        ax2.legend(loc="upper right", frameon=True, fontsize=9)

        # Panel 3: AFS Micro Momentum & Order Score
        ax3.plot(sample_df.index, sample_df["afs_7"], label="AFS 7 (Micro Momentum)", color="#2ecc71", linewidth=1.0)
        ax3.axhline(50, color="gray", linestyle=":", linewidth=0.8)
        ax3.axhline(30, color="blue", linestyle=":", linewidth=0.8)
        ax3.axhline(70, color="red", linestyle=":", linewidth=0.8)
        ax3.set_ylabel("AFS %", fontsize=10, fontweight="bold")
        ax3.set_xlabel("Time (Hourly)", fontsize=10, fontweight="bold")
        ax3.legend(loc="upper right", frameon=True, fontsize=9)

        plt.tight_layout()
        plot4_path = plots_dir / "04_regime_timeline_sample.png"
        plt.savefig(plot4_path, dpi=200)
        plt.close()
        print(f" -> Saved: {plot4_path.name}")


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
