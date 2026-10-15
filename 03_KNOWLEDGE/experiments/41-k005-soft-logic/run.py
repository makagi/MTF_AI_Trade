"""
Reproducible Experiment Script for Issue #41
K-005 Soft Logic & Fan-out Velocity Quantitative Re-evaluation.
Dual Analysis: Counter-Trend vs Trend Pullback Synergy & Regime Slicing.
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
    calculate_afs,
    calculate_fanout_velocity,
)
from src.evaluation import evaluate_returns, evaluate_yearly_breakdown


def simulate_strategy(df: pd.DataFrame, signal: pd.Series, horizon: int, sl_mult: float, tp_mult: float, cost: float):
    """Simulate trade execution given a causal boolean signal."""
    entry_indices = []
    last_entry_bar = -9999
    indices = df.index

    for i in range(len(df) - horizon):
        if signal.iloc[i]:
            if i - last_entry_bar >= horizon // 2:
                entry_indices.append(i)
                last_entry_bar = i

    trade_records = []
    for idx_pos in entry_indices:
        entry_time = indices[idx_pos]
        entry_price = df["close"].iloc[idx_pos]
        current_atr = df["atr"].iloc[idx_pos]

        if pd.isna(entry_price) or pd.isna(current_atr) or current_atr <= 0:
            continue

        stop_loss = entry_price - sl_mult * current_atr
        take_profit = entry_price + tp_mult * current_atr

        fwd_window = df.iloc[idx_pos + 1 : idx_pos + 1 + horizon]
        if len(fwd_window) == 0:
            continue

        highs = fwd_window["high"]
        lows = fwd_window["low"]
        closes = fwd_window["close"]

        exit_price = closes.iloc[-1]
        exit_time = fwd_window.index[-1]
        reason = "time_horizon"

        for step in range(len(fwd_window)):
            bar_low = lows.iloc[step]
            bar_high = highs.iloc[step]

            if bar_low <= stop_loss:
                exit_price = stop_loss
                exit_time = fwd_window.index[step]
                reason = "stop_loss"
                break
            elif bar_high >= take_profit:
                exit_price = take_profit
                exit_time = fwd_window.index[step]
                reason = "take_profit"
                break

        gross_return = (exit_price - entry_price) / entry_price
        net_return = gross_return - cost
        max_high = highs.max()
        min_low = lows.min()
        mfe = (max_high - entry_price) / entry_price
        mae = (min_low - entry_price) / entry_price

        trade_records.append(
            {
                "entry_time": entry_time,
                "exit_time": exit_time,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return": gross_return,
                "net_return": net_return,
                "is_win": net_return > 0,
                "mfe": mfe,
                "mae": mae,
                "exit_reason": reason,
                "macro_bull": df["macro_bull"].iloc[idx_pos],
                "dist_sma_89_atr": df["dist_sma_89_atr"].iloc[idx_pos],
                "dist_sma_377_atr": df["dist_sma_377_atr"].iloc[idx_pos],
                "sma_377_slope": df["sma_377_slope"].iloc[idx_pos],
                "atr_ratio": df["atr_ratio"].iloc[idx_pos],
                "afs_compression": df["afs_compression"].iloc[idx_pos],
                "void_overhead_atr": df["void_overhead_atr"].iloc[idx_pos],
            }
        )

    trades_df = pd.DataFrame(trade_records)
    if len(trades_df) > 0:
        trades_df.set_index("entry_time", inplace=True)
    return trades_df


def run_experiment(exp_dir: Path):
    with open(exp_dir / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    symbol = config.get("symbol") or config["data"]["symbol"]
    timeframe = config.get("timeframe") or config["data"]["timeframe"]
    start_date = config["data"]["start_date"]
    end_date = config["data"]["end_date"]
    friction_cost = float(config["parameters"]["friction_cost"])
    horizon = int(config["parameters"]["holding_horizon_bars"])
    sl_mult = float(config["parameters"]["stop_loss_atr"])
    tp_mult = float(config["parameters"]["take_profit_atr"])

    print(f"--- Running Experiment {config['experiment_id']} ---")
    print(f"Loading {symbol} {timeframe} data...")
    df = load_ohlcv(symbol=symbol, timeframe=timeframe)

    # Filter to Discovery partition strictly
    df = df.loc[start_date:end_date].copy()
    print(f"Discovery dataset size: {len(df)} bars ({df.index[0]} to {df.index[-1]})")

    # 1. Feature Engineering
    fast_p = config["parameters"]["fast_sma"]
    slow_p = config["parameters"]["slow_sma"]
    atr_p = config["parameters"]["atr_period"]
    afs_ps = config["parameters"]["afs_periods"]

    df["sma_fast"] = calculate_sma(df["close"], fast_p)
    df["sma_slow"] = calculate_sma(df["close"], slow_p)
    df["sma_144"] = calculate_sma(df["close"], 144)
    df["sma_377"] = calculate_sma(df["close"], 377)
    df["sma_377_slope"] = (df["sma_377"] - df["sma_377"].shift(24)) / df["close"]
    df["atr"] = calculate_atr(df, period=atr_p)
    df["atr_ratio"] = df["atr"] / df["close"]
    df["fanout_vel"] = calculate_fanout_velocity(df, fast_period=fast_p, slow_period=slow_p, atr_period=atr_p)

    afs_df, _, compression = calculate_afs(df, periods=afs_ps)
    for col in afs_df.columns:
        df[col] = afs_df[col]
    df["afs_compression"] = compression

    df["dist_sma_89_atr"] = (df["close"] - df["sma_slow"]) / (df["atr"] + 1e-8)
    df["dist_sma_377_atr"] = (df["close"] - df["sma_377"]) / (df["atr"] + 1e-8)
    df["macro_bull"] = (df["close"] > df["sma_377"]) & (df["sma_377_slope"] > 0)

    # The Void Calculation
    overhead_levels = []
    for t, c in df["close"].items():
        s144 = df.loc[t, "sma_144"]
        s377 = df.loc[t, "sma_377"]
        current_atr = df.loc[t, "atr"]
        ovs = [s for s in [s144, s377] if not pd.isna(s) and s > c]
        if ovs and not pd.isna(current_atr) and current_atr > 0:
            overhead_levels.append((min(ovs) - c) / current_atr)
        else:
            overhead_levels.append(5.0)
    df["void_overhead_atr"] = overhead_levels

    # =========================================================================
    # Strategy 1: Counter-Trend Reversion (Original K-005 Hypothesis)
    # =========================================================================
    print("\n>>> Strategy 1: Counter-Trend Reversion (Original K-005)")
    ct_fanout_decel = (df["sma_fast"] < df["sma_slow"]) & (df["fanout_vel"] < 0) & (df["fanout_vel"].diff() > 0)
    ct_afs_cross = (
        (df["AFS_7"] < 35)
        & (df["AFS_7"] > df["AFS_9"])
        & (df["AFS_7"].shift(1) <= df["AFS_9"].shift(1))
    )
    ct_signal = ct_fanout_decel & ct_afs_cross
    ct_trades = simulate_strategy(df, ct_signal, horizon, sl_mult, tp_mult, friction_cost)

    ct_returns = ct_trades["gross_return"] if len(ct_trades) > 0 else pd.Series(dtype=float)
    ct_mfe = ct_trades["mfe"] if len(ct_trades) > 0 else pd.Series(dtype=float)
    ct_mae = ct_trades["mae"] if len(ct_trades) > 0 else pd.Series(dtype=float)

    metrics = evaluate_returns(ct_returns, cost=friction_cost, mfe=ct_mfe, mae=ct_mae)
    if len(ct_returns) > 0:
        ct_yearly = evaluate_yearly_breakdown(ct_returns, cost=friction_cost)
        print("\n--- Counter-Trend Yearly Performance ---")
        print(ct_yearly.to_string())
        metrics["yearly_breakdown"] = ct_yearly.to_dict(orient="records")

    print("\n--- Counter-Trend Overall Metrics ---")
    for k, v in metrics.items():
        if k != "yearly_breakdown":
            print(f"  {k}: {v}")

    # Feature Separation in Counter-Trend
    if len(ct_trades) > 0:
        w_df = ct_trades[ct_trades["is_win"]]
        l_df = ct_trades[~ct_trades["is_win"]]
        sep = []
        for feat in ["dist_sma_89_atr", "dist_sma_377_atr", "sma_377_slope", "void_overhead_atr", "atr_ratio"]:
            sep.append({
                "feature": feat,
                "win_mean": float(w_df[feat].mean()),
                "win_med": float(w_df[feat].median()),
                "loss_mean": float(l_df[feat].mean()),
                "loss_med": float(l_df[feat].median()),
            })
        metrics["counter_trend_feature_separation"] = sep

    # =========================================================================
    # Strategy 2: Trend Pullback Synergy (Macro Bull + Soft Logic Dip Buy)
    # =========================================================================
    print("\n>>> Strategy 2: Trend Pullback Synergy (Macro Bull + Soft Logic Dip Buy)")
    trend_fanout_dip = (
        (df["sma_fast"] > df["sma_slow"])
        & (df["close"] > df["sma_377"])  # Macro Bull context
        & (df["fanout_vel"] < 0)         # Pullback spread contraction
        & (df["fanout_vel"].diff() > 0)  # Contraction bottoming & re-expansion
        & (df["AFS_7"] < 45)             # AFS Pullback territory
        & (df["AFS_7"] > df["AFS_9"])
        & (df["AFS_7"].shift(1) <= df["AFS_9"].shift(1))
    )
    tp_trades = simulate_strategy(df, trend_fanout_dip, horizon, sl_mult, tp_mult, friction_cost)
    tp_returns = tp_trades["gross_return"] if len(tp_trades) > 0 else pd.Series(dtype=float)
    tp_mfe = tp_trades["mfe"] if len(tp_trades) > 0 else pd.Series(dtype=float)
    tp_mae = tp_trades["mae"] if len(tp_trades) > 0 else pd.Series(dtype=float)

    tp_eval = evaluate_returns(tp_returns, cost=friction_cost, mfe=tp_mfe, mae=tp_mae)
    if len(tp_returns) > 0:
        tp_yearly = evaluate_yearly_breakdown(tp_returns, cost=friction_cost)
        print("\n--- Trend Pullback Yearly Performance ---")
        print(tp_yearly.to_string())
        tp_eval["yearly_breakdown"] = tp_yearly.to_dict(orient="records")

    print("\n--- Trend Pullback Overall Metrics ---")
    for k, v in tp_eval.items():
        if k != "yearly_breakdown":
            print(f"  {k}: {v}")

    metrics["trend_pullback_synergy"] = tp_eval

    # =========================================================================
    # 3. Contextual Slices Comparison
    # =========================================================================
    if len(ct_trades) > 0:
        shallow_mask = ct_trades["dist_sma_89_atr"] >= -2.0
        deep_mask = ct_trades["dist_sma_89_atr"] < -2.0
        metrics["counter_trend_slices"] = {
            "shallow_pullback": evaluate_returns(ct_trades.loc[shallow_mask, "gross_return"], cost=friction_cost),
            "deep_reversion": evaluate_returns(ct_trades.loc[deep_mask, "gross_return"], cost=friction_cost),
        }

    # Save metrics.json
    out_metrics_path = exp_dir / "metrics.json"
    with open(out_metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"\nSaved enriched metrics to {out_metrics_path}")

    return metrics


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
