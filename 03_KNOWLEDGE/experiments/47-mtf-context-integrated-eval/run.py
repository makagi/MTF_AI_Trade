"""
Reproducible Experiment Script for Issue #47
MTF Context Integrated Evaluation: Conditional Edge Analysis of Features under K-007 Regimes.
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
    # 1. MTF 3-Tier Features & Regime Classification (K-007 Engine)
    # =========================================================================
    print("Calculating MTF 3-Tier features & K-007 Regimes...")
    close = df["close"]

    # Tier 1: Macro
    df["sma_377"] = calculate_sma(close, 377)
    df["sma_377_slope"] = (df["sma_377"] - df["sma_377"].shift(24)) / close
    df["macro_bull"] = (close > df["sma_377"]) & (df["sma_377_slope"] > 0)
    df["macro_bear"] = (close < df["sma_377"]) & (df["sma_377_slope"] < 0)

    # Tier 2: Meso
    df["sma_21"] = calculate_sma(close, 21)
    df["sma_89"] = calculate_sma(close, 89)
    df["atr"] = calculate_atr(df, period=14)
    df["squeeze_index"] = calculate_squeeze_index(df, periods=[21, 55, 144, 377], lookback_bars=720)
    df["dist_sma_89_atr"] = (close - df["sma_89"]) / (df["atr"] + 1e-8)

    # Tier 3: Micro
    afs_df, order_score, compression = calculate_afs(df, periods=[7, 9, 11, 13])
    df["afs_7"] = afs_df["AFS_7"]
    df["afs_order"] = order_score
    df["fanout_vel"] = calculate_fanout_velocity(df, fast_period=21, slow_period=89, atr_period=14)

    # Regimes
    regimes = pd.Series("Range_PingPong", index=df.index, dtype=object)
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

        if sq < 0.15:
            regimes.iloc[i] = "Squeeze_Pre_Breakout"
        elif m_bear and d_89 < -2.5 and a_7 < 30:
            regimes.iloc[i] = "Bear_Panic_Exhaustion"
        elif m_bull and (-2.0 <= d_89 <= 0.5) and a_7 < 40:
            regimes.iloc[i] = "Bull_Healthy_Pullback"
        elif m_bull and a_ord >= 2:
            regimes.iloc[i] = "Bull_Trend_Continuation"
        elif m_bear and a_ord == 0:
            regimes.iloc[i] = "Bear_Trend_Continuation"
        else:
            regimes.iloc[i] = "Range_PingPong"

    df["regime"] = regimes
    valid_df = df[df["regime"] != "Unclassified"].copy()

    # Forward 24h Return, MFE, MAE
    fwd_return = (valid_df["close"].shift(-horizon) - valid_df["close"]) / valid_df["close"]
    fwd_mfe = []
    fwd_mae = []
    for idx_pos in range(len(valid_df) - horizon):
        entry_p = valid_df["close"].iloc[idx_pos]
        window = valid_df.iloc[idx_pos + 1 : idx_pos + 1 + horizon]
        fwd_mfe.append((window["high"].max() - entry_p) / entry_p)
        fwd_mae.append((window["low"].min() - entry_p) / entry_p)

    analysis_df = valid_df.iloc[:-horizon].copy()
    analysis_df["fwd_return"] = fwd_return.iloc[:-horizon]
    analysis_df["fwd_mfe"] = fwd_mfe
    analysis_df["fwd_mae"] = fwd_mae

    # =========================================================================
    # 2. Define Features & Conditional Signals
    # =========================================================================
    print("Evaluating conditional signals under K-007 regimes...")

    # Signal Components
    # Soft Logic Trigger: AFS 7 turning up from oversold (<35) & fanout velocity deceleration
    soft_logic_trigger = (
        (analysis_df["afs_7"] > 30) &
        (analysis_df["afs_7"].shift(1) <= 30) &
        (analysis_df["fanout_vel"].abs() < 1.0)
    )

    # Squeeze Breakout Trigger: Squeeze was active (<0.15) and now breaking out
    sq_breakout_trigger = (
        (analysis_df["squeeze_index"].shift(1) < 0.15) &
        (analysis_df["squeeze_index"] >= 0.15)
    )

    # SMA Divergence Trigger: Extreme drop below SMA 89 (>2 ATR)
    sma_div_trigger = (analysis_df["dist_sma_89_atr"] < -2.0) & (analysis_df["dist_sma_89_atr"].shift(1) >= -2.0)

    # Signals to Compare
    signals = {
        "SoftLogic_Unfiltered (No Context)": soft_logic_trigger,
        "SoftLogic @ Bull_Healthy_Pullback": soft_logic_trigger & (analysis_df["regime"] == "Bull_Healthy_Pullback"),
        "SoftLogic @ Range_PingPong": soft_logic_trigger & (analysis_df["regime"] == "Range_PingPong"),
        "SoftLogic @ Bear_Regimes": soft_logic_trigger & analysis_df["regime"].isin(["Bear_Trend_Continuation", "Bear_Panic_Exhaustion"]),
        "Squeeze_Breakout_Unfiltered": sq_breakout_trigger,
        "Squeeze_Breakout @ Bull_Flow": sq_breakout_trigger & analysis_df["macro_bull"] & (analysis_df["close"] > analysis_df["sma_21"]),
        "SMA_Divergence @ Macro_Bull": sma_div_trigger & analysis_df["macro_bull"],
        "SMA_Divergence @ Macro_Bear": sma_div_trigger & analysis_df["macro_bear"],
    }

    signal_results = []
    print("\n=======================================================")
    print("--- Conditional Signal Performance Matrix (24h) ---")
    print("=======================================================")

    primary_eval = None

    for sig_name, sig_mask in signals.items():
        sub_returns = analysis_df.loc[sig_mask, "fwd_return"]
        cnt = len(sub_returns)
        if cnt == 0:
            continue

        eval_res = evaluate_returns(sub_returns, cost=friction_cost)
        sub_mfe = float(analysis_df.loc[sig_mask, "fwd_mfe"].mean())
        sub_mae = float(analysis_df.loc[sig_mask, "fwd_mae"].mean())

        eval_res["signal_name"] = sig_name
        eval_res["mean_mfe"] = sub_mfe
        eval_res["mean_mae"] = sub_mae
        yearly_df = evaluate_yearly_breakdown(sub_returns, cost=friction_cost)
        eval_res["yearly_breakdown"] = yearly_df.to_dict(orient="records")

        signal_results.append(eval_res)

        print(f"[{sig_name:<34}] Trades: {cnt:>4} | Gross: {eval_res['gross_mean_return']*100:>+5.2f}% | Net: {eval_res['net_mean_return']*100:>+5.2f}% | WinRate: {eval_res['win_rate']*100:>4.1f}% | PF: {eval_res['profit_factor']:>4.2f} | MFE: {sub_mfe*100:>+4.2f}% | MAE: {sub_mae*100:>+4.2f}%")

        if sig_name == "SoftLogic @ Bull_Healthy_Pullback":
            primary_eval = eval_res

    # =========================================================================
    # 3. Regime x Signal Matrix (Net EV Heatmap data)
    # =========================================================================
    regime_list = [
        "Bull_Trend_Continuation",
        "Bull_Healthy_Pullback",
        "Squeeze_Pre_Breakout",
        "Range_PingPong",
        "Bear_Trend_Continuation",
        "Bear_Panic_Exhaustion",
    ]
    core_features = {
        "Soft_Logic_Reversal": soft_logic_trigger,
        "SMA_89_Divergence": sma_div_trigger,
        "Squeeze_Breakout": sq_breakout_trigger,
    }

    matrix_net_ev = pd.DataFrame(np.nan, index=core_features.keys(), columns=regime_list)
    matrix_win_rate = pd.DataFrame(np.nan, index=core_features.keys(), columns=regime_list)
    matrix_counts = pd.DataFrame(0, index=core_features.keys(), columns=regime_list)

    for feat_name, feat_mask in core_features.items():
        for reg in regime_list:
            cond = feat_mask & (analysis_df["regime"] == reg)
            ret = analysis_df.loc[cond, "fwd_return"]
            cnt = len(ret)
            matrix_counts.loc[feat_name, reg] = cnt
            if cnt >= 5:
                ev = evaluate_returns(ret, cost=friction_cost)
                matrix_net_ev.loc[feat_name, reg] = ev["net_mean_return"] * 100
                matrix_win_rate.loc[feat_name, reg] = ev["win_rate"] * 100

    # Save metrics.json (SPEC-EVAL-001 compliant)
    out_metrics = dict(primary_eval)
    out_metrics["all_signal_comparisons"] = signal_results
    out_metrics["regime_signal_matrix_net_ev"] = matrix_net_ev.to_dict()
    out_metrics["regime_signal_matrix_counts"] = matrix_counts.to_dict()

    out_metrics_path = exp_dir / "metrics.json"
    with open(out_metrics_path, "w", encoding="utf-8") as f:
        json.dump(out_metrics, f, indent=2, ensure_ascii=False)
    print(f"\nSaved integrated evaluation metrics to {out_metrics_path}")

    # =========================================================================
    # 4. Generate Visualizations (Plots)
    # =========================================================================
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    generate_visualizations(
        analysis_df,
        signals,
        signal_results,
        matrix_net_ev,
        matrix_counts,
        plots_dir,
    )

    return out_metrics


def generate_visualizations(
    df: pd.DataFrame,
    signals: dict,
    signal_results: list,
    matrix_net_ev: pd.DataFrame,
    matrix_counts: pd.DataFrame,
    plots_dir: Path,
):
    """Generate high-clarity visual evidence for conditional edge evaluation."""
    print("\nGenerating visual artifacts in:", plots_dir)
    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

    # -------------------------------------------------------------------------
    # Plot 1: Conditional Net EV Comparison (Unfiltered vs Regimes)
    # -------------------------------------------------------------------------
    res_df = pd.DataFrame(signal_results)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # 1A: Net Expected Value Bar Chart
    colors = ["#2ca02c" if v > 0 else "#d62728" for v in res_df["net_mean_return"]]
    y_pos = np.arange(len(res_df))
    bars = ax1.barh(y_pos, res_df["net_mean_return"] * 100, color=colors, height=0.55, edgecolor="black", linewidth=0.8)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(res_df["signal_name"], fontsize=10, fontweight="bold")
    ax1.axvline(0, color="black", linestyle="--", linewidth=1.0)
    ax1.set_xlabel("Net Expected Return (%) after 0.40% Friction Cost", fontsize=11, fontweight="bold")
    ax1.set_title("Conditional Edge: Net EV by Market Context", fontsize=12, fontweight="bold")

    for bar, val, cnt in zip(bars, res_df["net_mean_return"], res_df["total_trades"]):
        offset = 0.05 if val >= 0 else -0.05
        ha = "left" if val >= 0 else "right"
        ax1.text(val * 100 + offset, bar.get_y() + bar.get_height()/2, f"{val*100:+.2f}% (N={cnt})", va="center", ha=ha, fontsize=9, fontweight="bold")

    # 1B: MFE vs MAE Risk-Reward Profile
    mfe_vals = res_df["mean_mfe"] * 100
    mae_vals = res_df["mean_mae"] * 100
    ax2.barh(y_pos, mfe_vals, color="#2ecc71", height=0.4, align="center", label="Mean 24h MFE (Upside)")
    ax2.barh(y_pos, mae_vals, color="#e74c3c", height=0.4, align="center", label="Mean 24h MAE (Downside)")
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(["" for _ in y_pos])
    ax2.axvline(0, color="black", linestyle="--", linewidth=1.0)
    ax2.set_xlabel("MFE vs MAE Potential (%)", fontsize=11, fontweight="bold")
    ax2.set_title("24h MFE vs MAE Balance (Risk Profile)", fontsize=12, fontweight="bold")
    ax2.legend(loc="lower right", frameon=True)

    plt.tight_layout()
    p1 = plots_dir / "01_conditional_ev_comparison.png"
    plt.savefig(p1, dpi=200)
    plt.close()
    print(f" -> Saved: {p1.name}")

    # -------------------------------------------------------------------------
    # Plot 2: Cumulative Return Curves (Unfiltered vs Context-Guided)
    # -------------------------------------------------------------------------
    plt.figure(figsize=(14, 7))

    # Compare SoftLogic Unfiltered vs BullPullback
    for sig_key, color, lw, ls in [
        ("SoftLogic_Unfiltered (No Context)", "#7f7f7f", 1.2, "--"),
        ("SoftLogic @ Range_PingPong", "#e74c3c", 1.2, ":"),
        ("SoftLogic @ Bull_Healthy_Pullback", "#1f77b4", 2.2, "-"),
        ("Squeeze_Breakout @ Bull_Flow", "#2ca02c", 2.2, "-"),
    ]:
        if sig_key in signals:
            mask = signals[sig_key]
            trade_df = df.loc[mask, ["close", "fwd_return"]].copy().sort_index()
            if len(trade_df) > 0:
                trade_df["net_ret"] = trade_df["fwd_return"] - 0.0040
                cum_ret = trade_df["net_ret"].cumsum()
                plt.plot(cum_ret.index, cum_ret * 100, label=f"{sig_key} (N={len(trade_df)})", color=color, linewidth=lw, linestyle=ls)

    plt.title("Cumulative Net Return Trajectory: Context Filtered vs Unfiltered Signals (2020 - 2025)", fontsize=13, fontweight="bold", pad=12)
    plt.xlabel("Date", fontsize=11, fontweight="bold")
    plt.ylabel("Cumulative Net Return (%) [0.40% Friction Cost Included]", fontsize=11, fontweight="bold")
    plt.axhline(0, color="black", linestyle="-", linewidth=0.8)
    plt.legend(loc="upper left", frameon=True, fontsize=10)
    plt.tight_layout()
    p2 = plots_dir / "02_cumulative_return_curves.png"
    plt.savefig(p2, dpi=200)
    plt.close()
    print(f" -> Saved: {p2.name}")

    # -------------------------------------------------------------------------
    # Plot 3: Regime x Signal Matrix Heatmap (Net EV)
    # -------------------------------------------------------------------------
    plt.figure(figsize=(12, 6))
    annot_matrix = matrix_net_ev.copy().astype(str)
    for col in matrix_net_ev.columns:
        for idx in matrix_net_ev.index:
            val = matrix_net_ev.loc[idx, col]
            cnt = matrix_counts.loc[idx, col]
            if pd.isna(val) or cnt < 5:
                annot_matrix.loc[idx, col] = f"N<5"
            else:
                annot_matrix.loc[idx, col] = f"{val:+.2f}%\n(N={cnt})"

    ax = sns.heatmap(
        matrix_net_ev,
        annot=annot_matrix.values,
        fmt="",
        cmap="RdYlGn",
        center=0.0,
        cbar_kws={"label": "Net Expected Value (%)"},
        linewidths=1.2,
        linecolor="white",
        annot_kws={"fontsize": 10, "fontweight": "bold"},
    )
    plt.title("Regime x Feature Matrix: Net Expected Value Heatmap (%)\n(Green = Viable Edge > 0, Red = Friction Drag)", fontsize=13, fontweight="bold", pad=15)
    plt.xlabel("Market Regime (K-007 Context)", fontsize=11, fontweight="bold", labelpad=10)
    plt.ylabel("Core Feature / Signal", fontsize=11, fontweight="bold", labelpad=10)
    plt.xticks(rotation=25, ha="right", fontsize=9, fontweight="bold")
    plt.yticks(rotation=0, fontsize=10, fontweight="bold")
    plt.tight_layout()
    p3 = plots_dir / "03_regime_signal_matrix_heatmap.png"
    plt.savefig(p3, dpi=200)
    plt.close()
    print(f" -> Saved: {p3.name}")

    # -------------------------------------------------------------------------
    # Plot 4: Integrated Trade Timeline Case Study (2023 Q4 - 2024 Q1)
    # -------------------------------------------------------------------------
    sample_df = df.loc["2023-10-15":"2024-01-15"].copy()
    if len(sample_df) > 100:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})

        # Panel 1: Price and Signal Markers
        ax1.plot(sample_df.index, sample_df["close"], label="BTC Close", color="black", linewidth=1.2, zorder=3)
        ax1.plot(sample_df.index, sample_df["sma_89"], label="SMA 89 (Meso Mid)", color="#e67e22", linewidth=1.1, alpha=0.9, zorder=2)
        ax1.plot(sample_df.index, sample_df["sma_377"], label="SMA 377 (Macro)", color="#9b59b6", linewidth=1.3, linestyle="--", zorder=2)

        # Plot signals
        bull_pullback_signals = sample_df[signals["SoftLogic @ Bull_Healthy_Pullback"].loc[sample_df.index]]
        sq_breakout_signals = sample_df[signals["Squeeze_Breakout @ Bull_Flow"].loc[sample_df.index]]
        range_signals = sample_df[signals["SoftLogic @ Range_PingPong"].loc[sample_df.index]]

        ax1.scatter(bull_pullback_signals.index, bull_pullback_signals["close"], color="#1f77b4", marker="^", s=110, label="SoftLogic @ Bull Pullback (Armed Buy)", zorder=6)
        ax1.scatter(sq_breakout_signals.index, sq_breakout_signals["close"], color="#2ca02c", marker="*", s=160, label="Squeeze Breakout @ Bull Flow (Breakout)", zorder=6)
        ax1.scatter(range_signals.index, range_signals["close"], color="#e74c3c", marker="x", s=60, alpha=0.6, label="Filtered Signals (Range PingPong noise)", zorder=5)

        ax1.set_title("Context Filtered Signals in Action: Bull Pullback Entry vs Range Noise Blocked", fontsize=13, fontweight="bold")
        ax1.set_ylabel("Price (USD)", fontsize=10, fontweight="bold")
        ax1.legend(loc="upper left", frameon=True, fontsize=9)

        # Panel 2: Fanout Velocity & Squeeze Index
        ax2.plot(sample_df.index, sample_df["fanout_vel"], label="Fanout Velocity", color="#3498db", linewidth=1.0)
        ax2.plot(sample_df.index, sample_df["squeeze_index"], label="Squeeze Index", color="#f39c12", linewidth=1.0)
        ax2.axhline(0, color="gray", linestyle=":", linewidth=0.8)
        ax2.axhline(0.15, color="red", linestyle="--", linewidth=0.8, label="Squeeze Threshold (0.15)")
        ax2.set_ylabel("Metrics", fontsize=10, fontweight="bold")
        ax2.set_xlabel("Time (Hourly)", fontsize=10, fontweight="bold")
        ax2.legend(loc="upper left", frameon=True, fontsize=9)

        plt.tight_layout()
        p4 = plots_dir / "04_integrated_trade_timeline.png"
        plt.savefig(p4, dpi=200)
        plt.close()
        print(f" -> Saved: {p4.name}")


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
