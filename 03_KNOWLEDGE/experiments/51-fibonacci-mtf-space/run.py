"""
Reproducible Experiment Script for Issue #51
MTF Composite Space, Fibonacci Liquidity Voids & Hierarchical Synchronization (K-015 to K-020).
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
from src.features import (
    calculate_sma,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_squeeze_index,
    calculate_afs,
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
    # 1. Indicator Calculations
    # =========================================================================
    print("Calculating Fibonacci SMAs and MTF features...")
    atr_24 = calculate_atr(df, 24)
    df["atr_24"] = atr_24

    # Fibonacci SMAs
    fib_periods = [21, 55, 89, 144, 233, 377, 610]
    for p in fib_periods:
        df[f"sma_{p}"] = calculate_sma(close, p)

    # Macro 377 Slope (24-bar delta normalized by ATR)
    df["macro_slope_377"] = (df["sma_377"] - df["sma_377"].shift(24)) / (24 * atr_24)

    # Daily-scale Bollinger Bands & Squeeze (20 days = 480 hours)
    daily_up, daily_mid, daily_low = calculate_bollinger_bands(close, 480, 2.0)
    df["daily_squeeze_idx"] = calculate_squeeze_index(df, periods=[480], lookback_bars=480 * 2) * 100

    # Forward Returns & MFE/MAE
    df["fwd_ret_24"] = (close.shift(-horizon) - close) / close
    df["fwd_short_ret_24"] = (close - close.shift(-horizon)) / close

    # Rolling MFE / MAE
    fwd_high = high.iloc[::-1].rolling(window=horizon, min_periods=1).max().iloc[::-1].shift(-1)
    fwd_low = low.iloc[::-1].rolling(window=horizon, min_periods=1).min().iloc[::-1].shift(-1)
    df["mfe_long"] = (fwd_high - close) / close
    df["mae_long"] = (close - fwd_low) / close
    df["mfe_short"] = (close - fwd_low) / close
    df["mae_short"] = (fwd_high - close) / close

    # Hourly bar velocity
    df["bar_velocity_atr"] = (close - close.shift(1)).abs() / atr_24

    # =========================================================================
    # 2. Hypothesis Definition & Event Extraction
    # =========================================================================
    print("Extracting pattern events for K-015 to K-020...")

    # K-015: Fibonacci Void vs Dense Space
    # Gap between SMA 89 and SMA 233
    fib_gap_atr = (df["sma_89"] - df["sma_233"]).abs() / atr_24
    in_gap = (close > df[["sma_89", "sma_233"]].min(axis=1)) & (close < df[["sma_89", "sma_233"]].max(axis=1))
    
    # Void: gap >= 1.5 ATR, Dense: gap < 0.8 ATR
    df["k015_void_pass"] = in_gap & (fib_gap_atr >= 1.5)
    df["k015_dense_pass"] = in_gap & (fib_gap_atr < 0.8)

    # For K-015 trade: if in Void with positive momentum, trend follow
    trend_up = df["sma_89"] > df["sma_233"]
    df["k015_void_trend_long"] = df["k015_void_pass"] & trend_up & (close > close.shift(1))
    # Dense trend long
    df["k015_dense_trend_long"] = df["k015_dense_pass"] & trend_up & (close > close.shift(1))

    # K-016: Macro Gravity Pull (SMA 377 slope & pullback depth)
    # Pullback in Bull Trend: Macro slope > 0.02, price drops below SMA 55
    df["macro_bull"] = (close > df["sma_377"]) & (df["macro_slope_377"] > 0.02)
    # Trigger: Pullback entering SMA 55
    pullback_trigger = df["macro_bull"] & (close < df["sma_55"]) & (close.shift(1) >= df["sma_55"].shift(1))
    df["k016_pullback_entry"] = pullback_trigger

    # K-017: Daily Squeeze x 1h Breakout Hierarchy
    # 1h 24-bar High breakout
    high_24_prev = high.rolling(24).max().shift(1)
    breakout_1h = (close > high_24_prev) & (close.shift(1) <= high_24_prev)

    # Daily Squeeze (< 25 percentile) vs Daily Expansion (> 75 percentile)
    df["k017_breakout_daily_squeeze"] = breakout_1h & (df["daily_squeeze_idx"] < 25.0)
    df["k017_breakout_daily_expansion"] = breakout_1h & (df["daily_squeeze_idx"] > 75.0)

    # K-018: Fibonacci Confluence Zone Bounce
    # 4 Fibonacci SMAs: 21, 55, 89, 144
    conf_max = df[["sma_21", "sma_55", "sma_89", "sma_144"]].max(axis=1)
    conf_min = df[["sma_21", "sma_55", "sma_89", "sma_144"]].min(axis=1)
    conf_spread_atr = (conf_max - conf_min) / atr_24
    df["is_confluence"] = conf_spread_atr < 0.8

    # Bounce from Confluence in Uptrend (close tests confluence and bounces up)
    tested_conf = (low <= conf_max) & (high >= conf_min)
    df["k018_confluence_bounce_long"] = (
        df["is_confluence"] & tested_conf & (close > conf_max) & (close > open_p) & (close > df["sma_377"])
    )

    # K-019: Rolling 72h HH/LL Momentum Asymmetry
    high_72_prev = high.rolling(72).max().shift(1)
    low_72_prev = low.rolling(72).min().shift(1)
    df["k019_hh_breakout"] = (close > high_72_prev) & (close.shift(1) <= high_72_prev)
    df["k019_ll_breakdown"] = (close < low_72_prev) & (close.shift(1) >= low_72_prev)

    # K-020: Macro Bull Perfect Order Collapse Initial Momentum
    bull_po_3 = (df["sma_55"] > df["sma_89"]) & (df["sma_89"] > df["sma_233"])
    # PO established for at least 48 bars
    po_established = bull_po_3.rolling(48).min() == 1
    # Initial bear cross: SMA 55 crosses below SMA 89
    bear_cross = (df["sma_55"] < df["sma_89"]) & (df["sma_55"].shift(1) >= df["sma_89"].shift(1))
    df["k020_po_collapse_short"] = po_established.shift(1) & bear_cross

    # Drop NaNs
    eval_df = df.dropna(subset=["fwd_ret_24", "fwd_short_ret_24", "sma_610"]).copy()

    # =========================================================================
    # 3. Quantitative Evaluation (Full & Cross-Period)
    # =========================================================================
    print("Evaluating metrics across Discovery and 3 periods...")

    patterns = {
        "K-015_Void_Trend_Long": {"col": "k015_void_trend_long", "direction": "long"},
        "K-015_Dense_Trend_Long": {"col": "k015_dense_trend_long", "direction": "long"},
        "K-016_Macro_Pullback_Long": {"col": "k016_pullback_entry", "direction": "long"},
        "K-017_Breakout_Daily_Squeeze": {"col": "k017_breakout_daily_squeeze", "direction": "long"},
        "K-017_Breakout_Daily_Expansion": {"col": "k017_breakout_daily_expansion", "direction": "long"},
        "K-018_Confluence_Bounce_Long": {"col": "k018_confluence_bounce_long", "direction": "long"},
        "K-019_HH_Breakout_Long": {"col": "k019_hh_breakout", "direction": "long"},
        "K-019_LL_Breakdown_Short": {"col": "k019_ll_breakdown", "direction": "short"},
        "K-020_PO_Collapse_Short": {"col": "k020_po_collapse_short", "direction": "short"},
    }

    results = {}

    def calc_metrics(sub_df, pattern_name, meta):
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

    for pat_name, meta in patterns.items():
        results[pat_name] = {
            "direction": meta["direction"],
            "full_discovery": calc_metrics(eval_df, pat_name, meta),
            "periods": {},
        }
        for p_key, p_val in periods_cfg.items():
            p_sub = eval_df.loc[p_val["start"]:p_val["end"]]
            results[pat_name]["periods"][p_key] = calc_metrics(p_sub, pat_name, meta)

    # Velocity Comparison for K-015
    void_vel = eval_df.loc[eval_df["k015_void_pass"], "bar_velocity_atr"].mean()
    dense_vel = eval_df.loc[eval_df["k015_dense_pass"], "bar_velocity_atr"].mean()
    results["K-015_Velocity_Stats"] = {
        "void_velocity_mean_atr": round(float(void_vel), 3),
        "dense_velocity_mean_atr": round(float(dense_vel), 3),
        "velocity_ratio": round(float(void_vel / dense_vel), 2) if dense_vel > 0 else 0.0,
    }

    # Save metrics.json (SPEC-EVAL-001 compliant)
    # Primary evaluation: K-017 Breakout Daily Expansion
    primary_events = eval_df[eval_df["k017_breakout_daily_expansion"] == True]
    primary_eval = evaluate_returns(primary_events["fwd_ret_24"], cost=friction_cost)

    out_metrics = dict(primary_eval)
    out_metrics["pattern_name"] = "K-017: Daily Expansion x 1h Breakout"
    out_metrics["all_patterns"] = results

    metrics_path = exp_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(out_metrics, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to {metrics_path}")

    # =========================================================================
    # 4. Visualizations
    # =========================================================================
    print("Generating visual evidence plots...")
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(exist_ok=True)
    sns.set_theme(style="whitegrid")

    # Plot 1: K-015 Void vs Dense Velocity & EV
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Velocity comparison
    vel_data = pd.DataFrame({
        "Space Type": ["Dense Space (<0.8 ATR)", "Void Space (>=1.5 ATR)"],
        "Bar Velocity (ATR/hour)": [dense_vel, void_vel]
    })
    sns.barplot(data=vel_data, x="Space Type", y="Bar Velocity (ATR/hour)", ax=axes[0], palette=["#7f7f7f", "#1f77b4"])
    axes[0].set_title("K-015: Price Velocity in Void vs Dense Fibonacci Spaces", fontsize=12, fontweight="bold")
    for p in axes[0].patches:
        axes[0].annotate(f"{p.get_height():.3f} ATR/h", (p.get_x() + p.get_width() / 2., p.get_height() / 2),
                         ha='center', va='center', color='white', fontweight='bold')

    # Net EV Comparison across periods
    void_evs = [results["K-015_Void_Trend_Long"]["full_discovery"]["net_ev_pct"]] + [
        results["K-015_Void_Trend_Long"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    dense_evs = [results["K-015_Dense_Trend_Long"]["full_discovery"]["net_ev_pct"]] + [
        results["K-015_Dense_Trend_Long"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    labels = ["Full", "P1 (Bull)", "P2 (Bear)", "P3 (Recov)"]
    x = np.arange(len(labels))
    width = 0.35
    axes[1].bar(x - width/2, void_evs, width, label="Void Trend (>=1.5 ATR)", color="#2ca02c")
    axes[1].bar(x + width/2, dense_evs, width, label="Dense Trend (<0.8 ATR)", color="#d62728")
    axes[1].axhline(0, color="black", linestyle="--", alpha=0.7)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels)
    axes[1].set_ylabel("Net EV (%) after 0.40% friction")
    axes[1].set_title("K-015: Net EV Comparison Across Regimes", fontsize=12, fontweight="bold")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(plots_dir / "01_fib_void_vs_dense_velocity.png", dpi=150)
    plt.close()

    # Plot 2: K-016 Macro Slope & Pullback Risk-Reward
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Macro slope vs pullback MFE/MAE
    pb_evs = [results["K-016_Macro_Pullback_Long"]["full_discovery"]["net_ev_pct"]] + [
        results["K-016_Macro_Pullback_Long"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    axes[0].bar(labels, pb_evs, color=["#1f77b4" if v > 0 else "#d62728" for v in pb_evs])
    axes[0].axhline(0, color="black", linestyle="--")
    axes[0].set_ylabel("Net EV (%) after 0.40% friction")
    axes[0].set_title("K-016: Macro Trend Pullback Long Net EV", fontsize=12, fontweight="bold")
    for i, v in enumerate(pb_evs):
        axes[0].text(i, v + (0.05 if v >= 0 else -0.15), f"{v:+.2f}%", ha="center", fontweight="bold")

    # MFE vs MAE
    mfe_val = results["K-016_Macro_Pullback_Long"]["full_discovery"]["mean_mfe_pct"]
    mae_val = results["K-016_Macro_Pullback_Long"]["full_discovery"]["mean_mae_pct"]
    axes[1].bar(["Mean MFE (Upside)", "Mean MAE (Drawdown)"], [mfe_val, mae_val], color=["#2ca02c", "#d62728"])
    axes[1].set_ylabel("Percentage (%)")
    axes[1].set_title("K-016: Pullback Risk-Reward Profile (Full Discovery)", fontsize=12, fontweight="bold")
    axes[1].text(0, mfe_val / 2, f"+{mfe_val:.2f}%", ha="center", color="white", fontweight="bold")
    axes[1].text(1, mae_val / 2, f"-{mae_val:.2f}%", ha="center", color="white", fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "02_macro_slope_vs_pullback_depth.png", dpi=150)
    plt.close()

    # Plot 3: K-017 Daily Squeeze x 1h Breakout Hierarchy
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    sqz_evs = [results["K-017_Breakout_Daily_Squeeze"]["full_discovery"]["net_ev_pct"]] + [
        results["K-017_Breakout_Daily_Squeeze"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    exp_evs = [results["K-017_Breakout_Daily_Expansion"]["full_discovery"]["net_ev_pct"]] + [
        results["K-017_Breakout_Daily_Expansion"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    axes[0].bar(x - width/2, sqz_evs, width, label="Under Daily Squeeze (<25%)", color="#2ca02c")
    axes[0].bar(x + width/2, exp_evs, width, label="Under Daily Expansion (>75%)", color="#ff7f0e")
    axes[0].axhline(0, color="black", linestyle="--")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_ylabel("Net EV (%) after 0.40% friction")
    axes[0].set_title("K-017: 1h Breakout Net EV by Daily Macro Regime", fontsize=12, fontweight="bold")
    axes[0].legend()

    # Win rate comparison
    sqz_wr = results["K-017_Breakout_Daily_Squeeze"]["full_discovery"]["win_rate_pct"]
    exp_wr = results["K-017_Breakout_Daily_Expansion"]["full_discovery"]["win_rate_pct"]
    axes[1].bar(["Daily Squeeze", "Daily Expansion"], [sqz_wr, exp_wr], color=["#2ca02c", "#ff7f0e"])
    axes[1].axhline(50, color="gray", linestyle=":")
    axes[1].set_ylabel("Win Rate (%)")
    axes[1].set_title("K-017: Win Rate Comparison (Full Discovery)", fontsize=12, fontweight="bold")
    axes[1].text(0, sqz_wr / 2, f"{sqz_wr:.1f}%", ha="center", color="white", fontweight="bold")
    axes[1].text(1, exp_wr / 2, f"{exp_wr:.1f}%", ha="center", color="white", fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "03_daily_squeeze_hourly_breakout_matrix.png", dpi=150)
    plt.close()

    # Plot 4: K-018, K-019, K-020 Synthesis Heatmap / Summary
    fig, ax = plt.subplots(figsize=(12, 6))
    
    matrix_rows = [
        "K-015_Void_Trend_Long",
        "K-016_Macro_Pullback_Long",
        "K-017_Breakout_Daily_Squeeze",
        "K-018_Confluence_Bounce_Long",
        "K-019_HH_Breakout_Long",
        "K-019_LL_Breakdown_Short",
        "K-020_PO_Collapse_Short",
    ]
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
    ax.set_title("EXP-51: Cross-Period Net EV & Sample Size Consistency Matrix", fontsize=14, fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "04_batch2_cross_period_consistency_matrix.png", dpi=150)
    plt.close()

    print("All plots generated successfully.")
    print(f"--- Experiment {config['experiment_id']} Completed ---")


if __name__ == "__main__":
    exp_dir = Path(__file__).resolve().parent
    run_experiment(exp_dir)
