"""
Reproducible Experiment Script for Issue #55
Multi-Scale MTF Relational States and Cross-Hierarchy Dynamics (K-025 to K-030).
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
from src.features import calculate_sma, calculate_atr, calculate_bollinger_bands, calculate_squeeze_index
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
    # 1. Feature Calculations
    # =========================================================================
    print("Calculating Multi-Scale Fibonacci SMAs, Slopes & Volatility...")
    atr_24 = calculate_atr(df, 24)
    df["atr_24"] = atr_24

    all_fibs = [8, 13, 21, 34, 55, 89, 233, 377, 610]
    for p in all_fibs:
        df[f"sma_{p}"] = calculate_sma(close, p)
        df[f"slope_{p}"] = (df[f"sma_{p}"] - df[f"sma_{p}"].shift(12)) / (12 * atr_24)

    # Daily-scale Bollinger Bands & Squeeze (480 hours)
    daily_up, daily_mid, daily_low = calculate_bollinger_bands(close, 480, 2.0)
    df["daily_squeeze_idx"] = calculate_squeeze_index(df, periods=[480], lookback_bars=480 * 2) * 100

    # 1h-scale Squeeze (21 hours)
    h1_up, h1_mid, h1_low = calculate_bollinger_bands(close, 21, 2.0)
    df["h1_squeeze_idx"] = calculate_squeeze_index(df, periods=[21], lookback_bars=24 * 30) * 100

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
    # 2. Mathematical Definition of Multi-Scale Real-time Regimes
    # =========================================================================
    print("Classifying Mathematical Regimes across Macro, Meso, and Micro scales...")

    # Macro Scale (233, 377, 610)
    ma_A, ma_B, ma_C = df["sma_233"], df["sma_377"], df["sma_610"]
    macro_bull = (ma_A > ma_B) & (ma_B > ma_C) & (df["slope_377"] > 0)
    macro_bear = (ma_A < ma_B) & (ma_B < ma_C) & (df["slope_377"] < 0)
    macro_range = ~(macro_bull | macro_bear)
    df["macro_regime"] = np.where(macro_bull, "Bull", np.where(macro_bear, "Bear", "Range"))

    # Meso Scale (34, 55, 89)
    me_A, me_B, me_C = df["sma_34"], df["sma_55"], df["sma_89"]
    meso_bull = (me_A > me_B) & (me_B > me_C) & (df["slope_55"] > 0)
    meso_bear = (me_A < me_B) & (me_B < me_C) & (df["slope_55"] < 0)
    meso_range = ~(meso_bull | meso_bear)
    df["meso_regime"] = np.where(meso_bull, "Bull", np.where(meso_bear, "Bear", "Range"))

    # Micro Scale (8, 13, 21)
    mi_A, mi_B, mi_C = df["sma_8"], df["sma_13"], df["sma_21"]
    micro_bull = (mi_A > mi_B) & (mi_B > mi_C)
    micro_bear = (mi_A < mi_B) & (mi_B < mi_C)
    df["micro_regime"] = np.where(micro_bull, "Bull", np.where(micro_bear, "Bear", "Range"))

    # =========================================================================
    # 3. Extract Patterns K-025 to K-030
    # =========================================================================
    print("Extracting pattern events for K-025 to K-030...")

    # K-025: Macro Bear Rally Exhaustion Short
    # Macro is Bear, Meso had a rally (Meso was Bull or test near SMA 233/377),
    # then Meso short-term slope (34) turns negative
    near_macro_res = (high >= (ma_A - 0.5 * atr_24))
    meso_rally_exhaust = macro_bear & near_macro_res & (df["slope_34"] < 0) & (df["slope_34"].shift(1) >= 0)
    df["k025_bear_rally_exhaust_short"] = meso_rally_exhaust

    # K-026: Macro Bull Gravity Pullback Bounce Long
    # Macro is Bull, Meso was dumping (price entered Gravity Zone between SMA 233 and 377),
    # then bounces back above SMA 34
    in_gravity_zone = (low <= (ma_A + 0.5 * atr_24)) & (high >= (ma_B - 0.5 * atr_24))
    gravity_bounce = macro_bull & in_gravity_zone & (close > me_A) & (close.shift(1) <= me_A.shift(1))
    df["k026_macro_gravity_bounce_long"] = gravity_bounce

    # K-028: Macro Range Drag on Lower-Timeframe Trend Following
    # Macro is Range, but Meso & Micro trigger a bullish breakout
    macro_range_bull_fake = macro_range & meso_bull & micro_bull & (close > close.shift(1))
    df["k028_range_drag_bull_long"] = macro_range_bull_fake

    # K-029: Hierarchical Volatility Compression Cascade Breakout
    # Daily Squeeze (< 25%) AND 1h Squeeze (< 15%), followed by activity expansion > 1.4x
    activity_ratio = (high - low) / (df["atr_24"] / 24)
    dual_squeeze = (df["daily_squeeze_idx"] < 25.0) & (df["h1_squeeze_idx"] < 15.0)
    vol_cascade_break = dual_squeeze.shift(1) & (activity_ratio > 1.4) & (close > me_A)
    df["k029_vol_cascade_break_long"] = vol_cascade_break

    # K-030: Multi-Scale Composite Alignment Score
    # Macro: Bull (+2), Bear (-2), Range (0)
    # Meso: Bull (+1.5), Bear (-1.5), Range (0)
    # Micro: Bull (+1), Bear (-1), Range (0)
    score_macro = np.where(macro_bull, 2.0, np.where(macro_bear, -2.0, 0.0))
    score_meso = np.where(meso_bull, 1.5, np.where(meso_bear, -1.5, 0.0))
    score_micro = np.where(micro_bull, 1.0, np.where(micro_bear, -1.0, 0.0))
    df["composite_score"] = score_macro + score_meso + score_micro

    # Strong Bull Composite Alignment (Score >= 3.5)
    df["k030_strong_bull_composite_long"] = (df["composite_score"] >= 3.5) & (df["composite_score"].shift(1) < 3.5)
    # Strong Bear Composite Alignment (Score <= -3.5)
    df["k030_strong_bear_composite_short"] = (df["composite_score"] <= -3.5) & (df["composite_score"].shift(1) > -3.5)
    # Conflicted / Neutral Range Churn (Score between -1.0 and +1.0)
    df["k030_neutral_range_churn_long"] = (df["composite_score"].abs() <= 1.0) & (close > me_A) & (close.shift(1) <= me_A.shift(1))

    # K-027: Fractal Regime Duration Scaling Analysis
    print("Computing K-027 Regime Duration Statistics...")
    def get_durations(series):
        # Count consecutive runs
        change = (series != series.shift(1)).astype(int)
        run_id = change.cumsum()
        durations = run_id.value_counts()
        return durations

    macro_dur = get_durations(df["macro_regime"])
    meso_dur = get_durations(df["meso_regime"])
    micro_dur = get_durations(df["micro_regime"])

    duration_stats = {
        "macro_median_hours": round(float(macro_dur.median()), 1),
        "macro_mean_hours": round(float(macro_dur.mean()), 1),
        "meso_median_hours": round(float(meso_dur.median()), 1),
        "meso_mean_hours": round(float(meso_dur.mean()), 1),
        "micro_median_hours": round(float(micro_dur.median()), 1),
        "micro_mean_hours": round(float(micro_dur.mean()), 1),
        "scale_ratio_macro_to_meso": round(float(macro_dur.median() / meso_dur.median()), 2),
        "scale_ratio_meso_to_micro": round(float(meso_dur.median() / micro_dur.median()), 2),
    }

    # Filter NaNs
    eval_df = df.dropna(subset=["fwd_ret_24", "fwd_short_ret_24", "sma_610"]).copy()

    # =========================================================================
    # 4. Quantitative Evaluation
    # =========================================================================
    print("Evaluating metrics across Full Discovery and 3 periods...")

    patterns = {
        "K-025_Bear_Rally_Exhaustion_Short": {"col": "k025_bear_rally_exhaust_short", "direction": "short"},
        "K-026_Macro_Gravity_Bounce_Long": {"col": "k026_macro_gravity_bounce_long", "direction": "long"},
        "K-028_Macro_Range_Drag_Long": {"col": "k028_range_drag_bull_long", "direction": "long"},
        "K-029_Vol_Cascade_Break_Long": {"col": "k029_vol_cascade_break_long", "direction": "long"},
        "K-030_Strong_Bull_Composite_Long": {"col": "k030_strong_bull_composite_long", "direction": "long"},
        "K-030_Strong_Bear_Composite_Short": {"col": "k030_strong_bear_composite_short", "direction": "short"},
        "K-030_Neutral_Range_Churn_Long": {"col": "k030_neutral_range_churn_long", "direction": "long"},
    }

    results = {}

    def calc_metrics(sub_df, p_name, meta):
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

    results["K-027_Duration_Scaling"] = duration_stats

    # Primary evaluation: K-030 Strong Bull Composite Long
    primary_events = eval_df[eval_df["k030_strong_bull_composite_long"] == True]
    primary_eval = evaluate_returns(primary_events["fwd_ret_24"], cost=friction_cost)

    out_metrics = dict(primary_eval)
    out_metrics["pattern_name"] = "K-030: Multi-Scale Strong Bull Composite Alignment"
    out_metrics["all_patterns"] = results

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

    # Plot 1: K-025 Bear Rally Exhaustion Short & K-026 Gravity Bounce Long
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    k025_evs = [results["K-025_Bear_Rally_Exhaustion_Short"]["full_discovery"]["net_ev_pct"]] + [
        results["K-025_Bear_Rally_Exhaustion_Short"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    axes[0].bar(labels, k025_evs, color=["#2ca02c" if v > 0 else "#d62728" for v in k025_evs])
    axes[0].axhline(0, color="black", linestyle="--")
    axes[0].set_ylabel("Net EV (%) after 0.40% friction")
    axes[0].set_title("K-025: Bear Rally Exhaustion Short Net EV", fontsize=12, fontweight="bold")
    for i, v in enumerate(k025_evs):
        axes[0].text(i, v + (0.05 if v >= 0 else -0.15), f"{v:+.2f}%", ha="center", fontweight="bold")

    k026_evs = [results["K-026_Macro_Gravity_Bounce_Long"]["full_discovery"]["net_ev_pct"]] + [
        results["K-026_Macro_Gravity_Bounce_Long"]["periods"][p]["net_ev_pct"] for p in periods_cfg
    ]
    axes[1].bar(labels, k026_evs, color=["#1f77b4" if v > 0 else "#d62728" for v in k026_evs])
    axes[1].axhline(0, color="black", linestyle="--")
    axes[1].set_ylabel("Net EV (%) after 0.40% friction")
    axes[1].set_title("K-026: Macro Bull Gravity Bounce Long Net EV", fontsize=12, fontweight="bold")
    for i, v in enumerate(k026_evs):
        axes[1].text(i, v + (0.05 if v >= 0 else -0.15), f"{v:+.2f}%", ha="center", fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "01_bear_rally_and_gravity_bounce.png", dpi=150)
    plt.close()

    # Plot 2: K-027 Fractal Regime Duration Scaling (Boxplot/Bar)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    scales = ["Micro (8-13-21)", "Meso (34-55-89)", "Macro (233-377-610)"]
    medians = [duration_stats["micro_median_hours"], duration_stats["meso_median_hours"], duration_stats["macro_median_hours"]]
    means = [duration_stats["micro_mean_hours"], duration_stats["meso_mean_hours"], duration_stats["macro_mean_hours"]]

    x_s = np.arange(len(scales))
    axes[0].bar(x_s - width/2, medians, width, label="Median Duration (Hours)", color="#1f77b4")
    axes[0].bar(x_s + width/2, means, width, label="Mean Duration (Hours)", color="#aec7e8")
    axes[0].set_xticks(x_s)
    axes[0].set_xticklabels(scales, fontsize=11, fontweight="bold")
    axes[0].set_ylabel("Hours in Regime")
    axes[0].set_title("K-027: Regime Duration Across Timeframe Scales", fontsize=12, fontweight="bold")
    axes[0].legend()
    for i, (med, mn) in enumerate(zip(medians, means)):
        axes[0].text(i - width/2, med + 5, f"{med:.0f}h", ha="center", fontweight="bold")
        axes[0].text(i + width/2, mn + 5, f"{mn:.0f}h", ha="center", fontweight="bold")

    # Ratio scaling
    ratios = [duration_stats["scale_ratio_meso_to_micro"], duration_stats["scale_ratio_macro_to_meso"]]
    axes[1].bar(["Meso / Micro Ratio", "Macro / Meso Ratio"], ratios, color=["#2ca02c", "#ff7f0e"])
    axes[1].axhline(2.618, color="purple", linestyle="--", label="Golden Power Phi^2 (~2.62)")
    axes[1].set_ylabel("Scaling Ratio")
    axes[1].set_title("K-027: Inter-Scale Duration Scaling Ratio", fontsize=12, fontweight="bold")
    axes[1].legend()
    for i, r in enumerate(ratios):
        axes[1].text(i, r / 2, f"{r:.2f}x", ha="center", color="white", fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "02_fractal_regime_duration_scaling.png", dpi=150)
    plt.close()

    # Plot 3: K-030 Multi-Scale Composite Score Performance Spectrum
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    score_bins = pd.cut(df["composite_score"], bins=[-5, -2.5, -0.5, 0.5, 2.5, 5],
                        labels=["Strong Bear (<= -3)", "Moderate Bear (-2)", "Neutral (0)", "Moderate Bull (+2)", "Strong Bull (>= +3)"])
    spec_df = pd.DataFrame({"Score Tier": score_bins, "fwd_ret": df["fwd_ret_24"] * 100 - (friction_cost * 100)}).dropna()
    mean_spec = spec_df.groupby("Score Tier", observed=False)["fwd_ret"].mean()

    colors = ["#d62728", "#ff9896", "#7f7f7f", "#98df8a", "#2ca02c"]
    axes[0].bar(mean_spec.index.astype(str), mean_spec.values, color=colors)
    axes[0].axhline(0, color="black", linestyle="--")
    axes[0].set_ylabel("Net EV (%) after 0.40% friction")
    axes[0].set_title("K-030: Forward Return Spectrum by Composite Alignment Score", fontsize=12, fontweight="bold")
    axes[0].tick_params(axis='x', rotation=15)
    for i, v in enumerate(mean_spec.values):
        axes[0].text(i, v + (0.05 if v >= 0 else -0.15), f"{v:+.2f}%", ha="center", fontweight="bold")

    # MFE vs MAE for Strong Bull vs Neutral
    sb_mfe = results["K-030_Strong_Bull_Composite_Long"]["full_discovery"]["mean_mfe_pct"]
    sb_mae = results["K-030_Strong_Bull_Composite_Long"]["full_discovery"]["mean_mae_pct"]
    neu_mfe = results["K-030_Neutral_Range_Churn_Long"]["full_discovery"]["mean_mfe_pct"]
    neu_mae = results["K-030_Neutral_Range_Churn_Long"]["full_discovery"]["mean_mae_pct"]

    bars_x = np.arange(2)
    axes[1].bar(bars_x - width/2, [sb_mfe, neu_mfe], width, label="Mean MFE (Upside)", color="#2ca02c")
    axes[1].bar(bars_x + width/2, [sb_mae, neu_mae], width, label="Mean MAE (Drawdown)", color="#d62728")
    axes[1].set_xticks(bars_x)
    axes[1].set_xticklabels(["Strong Bull (Score>=3.5)", "Neutral Churn (|Score|<=1)"], fontsize=10, fontweight="bold")
    axes[1].set_ylabel("Percentage (%)")
    axes[1].set_title("Risk-Reward Profile: Alignment vs Churn", fontsize=12, fontweight="bold")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(plots_dir / "03_composite_score_spectrum.png", dpi=150)
    plt.close()

    # Plot 4: Cross-Period Consistency Heatmap for all patterns in EXP-55
    fig, ax = plt.subplots(figsize=(13, 6))
    matrix_rows = list(patterns.keys())
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
    ax.set_title("EXP-55: Multi-Scale MTF Relational States - Consistency Matrix", fontsize=13, fontweight="bold")

    plt.tight_layout()
    plt.savefig(plots_dir / "04_batch4_cross_period_consistency_matrix.png", dpi=150)
    plt.close()

    print("All plots generated successfully.")
    print(f"--- Experiment {config['experiment_id']} Completed ---")


if __name__ == "__main__":
    exp_dir = Path(__file__).resolve().parent
    run_experiment(exp_dir)
