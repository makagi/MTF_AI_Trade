"""
Reproducible Experiment Script for Issue #45
MTF 3-Tier State Classification & Regime Transition Analysis.
"""

from pathlib import Path
import json
import yaml
import numpy as np
import pandas as pd

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

    return eval_metrics


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
