"""
Reproducible Experiment Script for Issue #49
Shock Dynamics, Sudden Regimes & Cross-Period Robustness Analysis (K-009 to K-014).
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
    periods_cfg = config["parameters"]["periods"]

    print(f"--- Running Experiment {config['experiment_id']} ---")
    print(f"Loading {symbol} {timeframe} data...")

    df = load_ohlcv(symbol=symbol, timeframe=timeframe)
    df = df.loc[start_date:end_date].copy()
    print(f"Discovery dataset size: {len(df)} bars ({df.index[0]} to {df.index[-1]})")

    # =========================================================================
    # 1. Feature Calculations (Shock, Volume & MTF Geometry)
    # =========================================================================
    print("Calculating Shock & Volatility features...")
    close = df["close"]
    open_p = df["open"]
    high = df["high"]
    low = df["low"]

    # Price averages & ATR
    df["sma_21"] = calculate_sma(close, 21)
    df["sma_89"] = calculate_sma(close, 89)
    df["sma_377"] = calculate_sma(close, 377)
    df["sma_377_slope"] = (df["sma_377"] - df["sma_377"].shift(24)) / close
    df["atr"] = calculate_atr(df, period=14)
    df["dist_sma_89_atr"] = (close - df["sma_89"]) / (df["atr"] + 1e-8)
    df["dist_sma_377_atr"] = (close - df["sma_377"]) / (df["atr"] + 1e-8)

    # Squeeze & Volatility
    df["squeeze_index"] = calculate_squeeze_index(df, periods=[21, 55, 144, 377], lookback_bars=720)
    df["candle_range"] = high - low
    df["candle_range_atr"] = df["candle_range"] / (df["atr"] + 1e-8)
    df["lower_wick"] = (np.minimum(open_p, close) - low) / (df["candle_range"] + 1e-8)
    df["upper_wick"] = (high - np.maximum(open_p, close)) / (df["candle_range"] + 1e-8)

    # Activity Dynamics (Proxy for Volume/Liquidity Spikes)
    df["range_sma_24"] = df["candle_range"].rolling(24).mean()
    df["activity_ratio"] = df["candle_range"] / (df["range_sma_24"] + 1e-8)

    # Micro momentum & Fanout
    afs_df, order_score, compression = calculate_afs(df, periods=[7, 9, 11, 13])
    df["afs_7"] = afs_df["AFS_7"]
    df["afs_order"] = order_score
    df["fanout_vel"] = calculate_fanout_velocity(df, fast_period=21, slow_period=89, atr_period=14)

    # Forward 24h Return, MFE, MAE
    fwd_return = (df["close"].shift(-horizon) - df["close"]) / df["close"]
    fwd_mfe = []
    fwd_mae = []
    for idx_pos in range(len(df) - horizon):
        entry_p = df["close"].iloc[idx_pos]
        window = df.iloc[idx_pos + 1 : idx_pos + 1 + horizon]
        fwd_mfe.append((window["high"].max() - entry_p) / entry_p)
        fwd_mae.append((window["low"].min() - entry_p) / entry_p)

    valid_df = df.iloc[:-horizon].copy()
    valid_df["fwd_return"] = fwd_return.iloc[:-horizon]
    valid_df["fwd_mfe"] = fwd_mfe
    valid_df["fwd_mae"] = fwd_mae

    # =========================================================================
    # 2. Define Shock Patterns (K-009 to K-014)
    # =========================================================================
    print("Formulating 6 shock dynamic patterns (K-009 to K-014)...")

    # K-009: Extreme Squeeze (<0.08) + Activity Expansion Breakout
    k009_mask = (
        (valid_df["squeeze_index"].shift(1) < 0.08) &
        (valid_df["squeeze_index"] >= 0.08) &
        (valid_df["activity_ratio"] > 1.6) &
        (valid_df["close"] > valid_df["sma_21"])
    )

    # K-010: Flash Crash 1st Bottom vs 2nd Bottom
    # Flash Crash defined as drop > 3.0 ATR in 6 hours
    six_hour_drop = (valid_df["close"].shift(6) - valid_df["close"]) / (valid_df["atr"] + 1e-8)
    first_bottom_mask = (six_hour_drop > 3.0) & (valid_df["lower_wick"] > 0.35)

    # 2nd Bottom: 12-48h after first bottom, price tests low with higher AFS (Bullish Divergence)
    second_bottom_mask = pd.Series(False, index=valid_df.index)
    fb_indices = np.where(first_bottom_mask.values)[0]
    for idx in fb_indices:
        # Look ahead 12 to 48 bars
        end_w = min(idx + 48, len(valid_df) - 1)
        for cand in range(idx + 12, end_w):
            if (
                valid_df["low"].iloc[cand] >= valid_df["low"].iloc[idx] * 0.98 and
                valid_df["low"].iloc[cand] <= valid_df["low"].iloc[idx] * 1.02 and
                valid_df["afs_7"].iloc[cand] > valid_df["afs_7"].iloc[idx] + 15
            ):
                second_bottom_mask.iloc[cand] = True
                break

    # K-011: Activity Climax (> 2.8x Range) + Hammer/Pinbar
    k011_mask = (
        (valid_df["activity_ratio"] > 2.8) &
        (valid_df["lower_wick"] > 0.45) &
        (valid_df["dist_sma_89_atr"] < -1.5)
    )

    # K-012: Resistance Exhaustion Dump (Near SMA 377 + AFS > 80 + Velocity Stalling)
    k012_short_mask = (
        (valid_df["dist_sma_377_atr"].abs() < 1.0) &
        (valid_df["afs_7"] > 80) &
        (valid_df["fanout_vel"] < 0.2)
    )

    # K-013: Post-Liquidation Cascade (Large bar > 2.8 ATR) -> Consolidation Freeze
    # Measured by forward 24h absolute return being small (< 1.5%)
    k013_mask = valid_df["candle_range_atr"] > 2.8

    # K-014: Panic Divergence V-Shape Reversion (Panic < -2.5 ATR + AFS turning up + Activity Drying)
    k014_vshape_mask = (
        (valid_df["dist_sma_89_atr"] < -2.5) &
        (valid_df["afs_7"] > valid_df["afs_7"].shift(1)) &
        (valid_df["activity_ratio"] < 1.6)
    )
    # K-014 Acceleration (Falling knife continues: Activity spiking + Vel negative)
    k014_knife_mask = (
        (valid_df["dist_sma_89_atr"] < -2.5) &
        (valid_df["activity_ratio"] > 2.0) &
        (valid_df["fanout_vel"] < -0.8)
    )

    patterns = {
        "K-009: Extreme Squeeze Activity Breakout": k009_mask,
        "K-010A: Flash Crash 1st Bottom": first_bottom_mask,
        "K-010B: Flash Crash 2nd Bottom (Div)": second_bottom_mask,
        "K-011: Activity Climax Pinbar (>2.8x)": k011_mask,
        "K-012: Resistance Exhaustion Dump": k012_short_mask,
        "K-014A: Panic Divergence V-Reversion": k014_vshape_mask,
        "K-014B: Panic Knife Acceleration": k014_knife_mask,
    }

    # =========================================================================
    # 3. Overall Performance & Cross-Period Consistency Evaluation
    # =========================================================================
    print("\n=======================================================")
    print("--- Shock Dynamics Overall Performance (2020-2025) ---")
    print("=======================================================")

    pattern_eval_results = []
    primary_eval = None

    for pat_name, pat_mask in patterns.items():
        # For short pattern K-012, return is inverted
        if "Dump" in pat_name or "Knife" in pat_name:
            sub_ret = -valid_df.loc[pat_mask, "fwd_return"]
            sub_mfe = float(valid_df.loc[pat_mask, "fwd_mae"].abs().mean())
            sub_mae = -float(valid_df.loc[pat_mask, "fwd_mfe"].mean())
        else:
            sub_ret = valid_df.loc[pat_mask, "fwd_return"]
            sub_mfe = float(valid_df.loc[pat_mask, "fwd_mfe"].mean())
            sub_mae = float(valid_df.loc[pat_mask, "fwd_mae"].mean())

        cnt = len(sub_ret)
        if cnt == 0:
            continue

        ev = evaluate_returns(sub_ret, cost=friction_cost)
        ev["pattern_name"] = pat_name
        ev["mean_mfe"] = sub_mfe
        ev["mean_mae"] = sub_mae
        yearly_df = evaluate_yearly_breakdown(sub_ret, cost=friction_cost)
        ev["yearly_breakdown"] = yearly_df.to_dict(orient="records")
        pattern_eval_results.append(ev)

        print(f"[{pat_name:<38}] Trades: {cnt:>4} | Gross: {ev['gross_mean_return']*100:>+5.2f}% | Net: {ev['net_mean_return']*100:>+5.2f}% | WinRate: {ev['win_rate']*100:>4.1f}% | PF: {ev['profit_factor']:>4.2f} | MFE: {sub_mfe*100:>+4.2f}% | MAE: {sub_mae*100:>+4.2f}%")

        if "K-014A" in pat_name:
            primary_eval = ev

    # =========================================================================
    # 4. Cross-Period Breakdown (Period 1, 2, 3)
    # =========================================================================
    print("\n=======================================================")
    print("--- Cross-Period Robustness Matrix (Net EV %) ---")
    print("=======================================================")

    period_slices = {
        "Overall (2020-2025)": (start_date, end_date),
        "P1: Bull Bubble (2020-21)": (periods_cfg["period_1"]["start"], periods_cfg["period_1"]["end"]),
        "P2: Bear Crash (2022)": (periods_cfg["period_2"]["start"], periods_cfg["period_2"]["end"]),
        "P3: Recovery & ATH (2023-25)": (periods_cfg["period_3"]["start"], periods_cfg["period_3"]["end"]),
    }

    cross_period_net_ev = pd.DataFrame(index=patterns.keys(), columns=period_slices.keys(), dtype=float)
    cross_period_counts = pd.DataFrame(0, index=patterns.keys(), columns=period_slices.keys())

    for pat_name, pat_mask in patterns.items():
        is_short = ("Dump" in pat_name or "Knife" in pat_name)
        for p_label, (p_start, p_end) in period_slices.items():
            period_sub = valid_df.loc[p_start:p_end]
            sub_mask = pat_mask.loc[period_sub.index]
            if is_short:
                p_ret = -period_sub.loc[sub_mask, "fwd_return"]
            else:
                p_ret = period_sub.loc[sub_mask, "fwd_return"]

            cnt = len(p_ret)
            cross_period_counts.loc[pat_name, p_label] = cnt
            if cnt >= 3:
                p_ev = evaluate_returns(p_ret, cost=friction_cost)
                cross_period_net_ev.loc[pat_name, p_label] = p_ev["net_mean_return"] * 100
            else:
                cross_period_net_ev.loc[pat_name, p_label] = np.nan

    print(cross_period_net_ev.round(2).to_string())

    # Save metrics.json (SPEC-EVAL-001 compliant)
    out_metrics = dict(primary_eval)
    out_metrics["all_pattern_evaluations"] = pattern_eval_results
    out_metrics["cross_period_net_ev"] = cross_period_net_ev.to_dict()
    out_metrics["cross_period_counts"] = cross_period_counts.to_dict()

    out_metrics_path = exp_dir / "metrics.json"
    with open(out_metrics_path, "w", encoding="utf-8") as f:
        json.dump(out_metrics, f, indent=2, ensure_ascii=False)
    print(f"\nSaved shock dynamics metrics to {out_metrics_path}")

    # =========================================================================
    # 5. Generate Visual Evidence & Plots
    # =========================================================================
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    generate_visualizations(
        valid_df,
        patterns,
        pattern_eval_results,
        cross_period_net_ev,
        cross_period_counts,
        plots_dir,
    )

    return out_metrics


def generate_visualizations(
    df: pd.DataFrame,
    patterns: dict,
    eval_results: list,
    cross_matrix: pd.DataFrame,
    counts_matrix: pd.DataFrame,
    plots_dir: Path,
):
    """Generate visual artifacts for shock dynamics & cross-period evaluation."""
    print("\nGenerating visual artifacts in:", plots_dir)
    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

    # -------------------------------------------------------------------------
    # Plot 1: Shock Patterns Net EV & MFE/MAE Balance
    # -------------------------------------------------------------------------
    res_df = pd.DataFrame(eval_results)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    colors = ["#2ca02c" if v > 0 else "#d62728" for v in res_df["net_mean_return"]]
    y_pos = np.arange(len(res_df))
    bars = ax1.barh(y_pos, res_df["net_mean_return"] * 100, color=colors, height=0.55, edgecolor="black", linewidth=0.8)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(res_df["pattern_name"], fontsize=10, fontweight="bold")
    ax1.axvline(0, color="black", linestyle="--", linewidth=1.0)
    ax1.set_xlabel("Net Expected Return (%) after 0.40% Friction Cost", fontsize=11, fontweight="bold")
    ax1.set_title("Shock Dynamics: Net EV by Pattern (2020-2025)", fontsize=12, fontweight="bold")

    for bar, val, cnt in zip(bars, res_df["net_mean_return"], res_df["total_trades"]):
        offset = 0.05 if val >= 0 else -0.05
        ha = "left" if val >= 0 else "right"
        ax1.text(val * 100 + offset, bar.get_y() + bar.get_height()/2, f"{val*100:+.2f}% (N={cnt})", va="center", ha=ha, fontsize=9, fontweight="bold")

    mfe_vals = res_df["mean_mfe"] * 100
    mae_vals = res_df["mean_mae"] * 100
    ax2.barh(y_pos, mfe_vals, color="#2ecc71", height=0.4, align="center", label="Mean 24h MFE (Upside/Gain)")
    ax2.barh(y_pos, mae_vals, color="#e74c3c", height=0.4, align="center", label="Mean 24h MAE (Downside/Drawdown)")
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(["" for _ in y_pos])
    ax2.axvline(0, color="black", linestyle="--", linewidth=1.0)
    ax2.set_xlabel("MFE vs MAE Potential (%)", fontsize=11, fontweight="bold")
    ax2.set_title("24h MFE vs MAE Potential (Risk-Reward)", fontsize=12, fontweight="bold")
    ax2.legend(loc="lower right", frameon=True)

    plt.tight_layout()
    p1 = plots_dir / "01_shock_patterns_net_ev.png"
    plt.savefig(p1, dpi=200)
    plt.close()
    print(f" -> Saved: {p1.name}")

    # -------------------------------------------------------------------------
    # Plot 2: Cross-Period Robustness Heatmap
    # -------------------------------------------------------------------------
    plt.figure(figsize=(13, 7))
    annot_mat = cross_matrix.copy().astype(str)
    for col in cross_matrix.columns:
        for idx in cross_matrix.index:
            v = cross_matrix.loc[idx, col]
            c = counts_matrix.loc[idx, col]
            if pd.isna(v) or c < 3:
                annot_mat.loc[idx, col] = "N<3"
            else:
                annot_mat.loc[idx, col] = f"{v:+.2f}%\n(N={c})"

    ax = sns.heatmap(
        cross_matrix,
        annot=annot_mat.values,
        fmt="",
        cmap="RdYlGn",
        center=0.0,
        cbar_kws={"label": "Net Expected Value (%)"},
        linewidths=1.2,
        linecolor="white",
        annot_kws={"fontsize": 10, "fontweight": "bold"},
    )
    plt.title("Cross-Period Robustness Matrix: Net Expected Value across 3 Eras (%)\n(Green = Consistent Edge, Red = Fragile / Negative)", fontsize=13, fontweight="bold", pad=15)
    plt.xlabel("Historical Eras / Regimes", fontsize=11, fontweight="bold", labelpad=10)
    plt.ylabel("Shock Dynamic Pattern", fontsize=11, fontweight="bold", labelpad=10)
    plt.xticks(rotation=0, fontsize=10, fontweight="bold")
    plt.yticks(rotation=0, fontsize=10, fontweight="bold")
    plt.tight_layout()
    p2 = plots_dir / "02_cross_period_consistency_matrix.png"
    plt.savefig(p2, dpi=200)
    plt.close()
    print(f" -> Saved: {p2.name}")

    # -------------------------------------------------------------------------
    # Plot 3: 1st Bottom vs 2nd Bottom Head-to-Head Comparison
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    bottom_df = res_df[res_df["pattern_name"].str.contains("Flash Crash")].copy()

    if len(bottom_df) >= 2:
        names = ["1st Bottom (Immediate)", "2nd Bottom (Divergence)"]
        evs = [float(bottom_df.iloc[0]["net_mean_return"]*100), float(bottom_df.iloc[1]["net_mean_return"]*100)]
        mfes = [float(bottom_df.iloc[0]["mean_mfe"]*100), float(bottom_df.iloc[1]["mean_mfe"]*100)]
        maes = [float(bottom_df.iloc[0]["mean_mae"]*100), float(bottom_df.iloc[1]["mean_mae"]*100)]
        pfs = [float(bottom_df.iloc[0]["profit_factor"]), float(bottom_df.iloc[1]["profit_factor"])]

        # Bar 1: Net EV & PF
        x = np.arange(len(names))
        w = 0.35
        ax1.bar(x - w/2, evs, width=w, color=["#e74c3c", "#2ecc71"], edgecolor="black", label="Net EV (%)")
        ax1.set_xticks(x)
        ax1.set_xticklabels(names, fontsize=11, fontweight="bold")
        ax1.axhline(0, color="black", linestyle="--", linewidth=1.0)
        ax1.set_ylabel("Net EV (%)", fontsize=11, fontweight="bold")
        ax1.set_title("Net Return: 1st Bottom vs 2nd Bottom", fontsize=12, fontweight="bold")
        for i, (ev_val, pf_val) in enumerate(zip(evs, pfs)):
            ax1.text(i - w/2, ev_val + 0.1, f"{ev_val:+.2f}%\nPF: {pf_val:.2f}", ha="center", fontsize=10, fontweight="bold")

        # Bar 2: MFE vs MAE
        ax2.bar(x - w/2, mfes, width=w, color="#2ca02c", label="MFE (Upside)")
        ax2.bar(x + w/2, maes, width=w, color="#d62728", label="MAE (Drawdown)")
        ax2.set_xticks(x)
        ax2.set_xticklabels(names, fontsize=11, fontweight="bold")
        ax2.axhline(0, color="black", linestyle="--", linewidth=1.0)
        ax2.set_ylabel("Percentage (%)", fontsize=11, fontweight="bold")
        ax2.set_title("Drawdown Risk vs Profit Potential", fontsize=12, fontweight="bold")
        ax2.legend(loc="upper right", frameon=True)

    plt.tight_layout()
    p3 = plots_dir / "03_first_vs_second_bottom_mfe_mae.png"
    plt.savefig(p3, dpi=200)
    plt.close()
    print(f" -> Saved: {p3.name}")

    # -------------------------------------------------------------------------
    # Plot 4: Historical Shock Case Study (May 2021 Liquidation Crash)
    # -------------------------------------------------------------------------
    crash_sample = df.loc["2021-05-15":"2021-06-05"].copy()
    if len(crash_sample) > 50:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})

        ax1.plot(crash_sample.index, crash_sample["close"], color="black", linewidth=1.2, label="BTC Price (May 2021 Shock)")
        ax1.plot(crash_sample.index, crash_sample["sma_89"], color="#e67e22", linewidth=1.1, label="SMA 89")
        ax1.plot(crash_sample.index, crash_sample["sma_377"], color="#9b59b6", linewidth=1.3, linestyle="--", label="SMA 377")

        # Overlay patterns in this window
        p_sub = {k: v.loc[crash_sample.index] for k, v in patterns.items() if k in ["K-010A: Flash Crash 1st Bottom", "K-010B: Flash Crash 2nd Bottom (Div)", "K-011: Activity Climax Pinbar (>2.8x)"]}
        fb = crash_sample[p_sub["K-010A: Flash Crash 1st Bottom"]]
        sb = crash_sample[p_sub["K-010B: Flash Crash 2nd Bottom (Div)"]]
        vc = crash_sample[p_sub["K-011: Activity Climax Pinbar (>2.8x)"]]

        ax1.scatter(fb.index, fb["close"], color="#e74c3c", marker="v", s=130, label="1st Bottom (Knife Trap)", zorder=5)
        ax1.scatter(sb.index, sb["close"], color="#2ecc71", marker="^", s=150, label="2nd Bottom (Stabilized Reversal)", zorder=6)
        ax1.scatter(vc.index, vc["close"], color="#f39c12", marker="*", s=170, label="Activity Climax (>2.8x)", zorder=6)

        ax1.set_title("May 2021 Flash Crash Case Study: 1st Bottom Trap vs 2nd Bottom Stabilization", fontsize=13, fontweight="bold")
        ax1.set_ylabel("Price (USD)", fontsize=10, fontweight="bold")
        ax1.legend(loc="upper right", frameon=True, fontsize=9)

        # Panel 2: Activity Ratio
        ax2.bar(crash_sample.index, crash_sample["activity_ratio"], width=0.03, color="#3498db", label="Activity Range Ratio (vs 24h Avg)")
        ax2.axhline(1.0, color="gray", linestyle=":", linewidth=0.8)
        ax2.axhline(2.8, color="red", linestyle="--", linewidth=1.0, label="Climax Threshold (>2.8x)")
        ax2.set_ylabel("Activity Ratio", fontsize=10, fontweight="bold")
        ax2.set_xlabel("Time (Hourly)", fontsize=10, fontweight="bold")
        ax2.legend(loc="upper right", frameon=True, fontsize=9)

        plt.tight_layout()
        p4 = plots_dir / "04_shock_dynamics_case_studies.png"
        plt.savefig(p4, dpi=200)
        plt.close()
        print(f" -> Saved: {p4.name}")


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
