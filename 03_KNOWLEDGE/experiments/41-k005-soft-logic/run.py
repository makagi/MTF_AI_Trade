"""
Reproducible Experiment Script for Issue #41
K-005 Soft Logic & Fan-out Velocity Quantitative Re-evaluation.
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


def run_experiment(exp_dir: Path):
    with open(exp_dir / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    symbol = config["data"]["symbol"]
    timeframe = config["data"]["timeframe"]
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

    # 1. Calculate features
    print("Calculating MTF features according to SPEC-FEAT-001...")
    fast_p = config["parameters"]["fast_sma"]
    slow_p = config["parameters"]["slow_sma"]
    atr_p = config["parameters"]["atr_period"]
    afs_ps = config["parameters"]["afs_periods"]

    df["sma_fast"] = calculate_sma(df["close"], fast_p)
    df["sma_slow"] = calculate_sma(df["close"], slow_p)
    df["atr"] = calculate_atr(df, period=atr_p)
    df["fanout_vel"] = calculate_fanout_velocity(df, fast_period=fast_p, slow_period=slow_p, atr_period=atr_p)

    afs_df, order_score, compression = calculate_afs(df, periods=afs_ps)
    for col in afs_df.columns:
        df[col] = afs_df[col]

    # 2. Define Signal Logic (Causality: signal evaluated at close of bar t)
    # Fanout is negative (downtrend spread), but velocity is decelerating (turning up)
    fanout_deceleration = (df["sma_fast"] < df["sma_slow"]) & (df["fanout_vel"] < 0) & (df["fanout_vel"].diff() > 0)

    # AFS 7 crosses over AFS 9 in oversold territory (< 30)
    afs_cross = (
        (df["AFS_7"] < 35)
        & (df["AFS_7"] > df["AFS_9"])
        & (df["AFS_7"].shift(1) <= df["AFS_9"].shift(1))
    )

    signal = fanout_deceleration & afs_cross

    # Avoid duplicate consecutive entries within horizon
    entry_indices = []
    last_entry_bar = -9999
    indices = df.index

    for i in range(len(df) - horizon):
        if signal.iloc[i]:
            if i - last_entry_bar >= horizon // 2:  # allow staggered entries
                entry_indices.append(i)
                last_entry_bar = i

    print(f"Total potential signals generated: {signal.sum()}")
    print(f"Executed trade entries (filtered): {len(entry_indices)}")

    # 3. Simulate Trades & Calculate MFE / MAE
    trade_records = []
    for idx_pos in entry_indices:
        entry_time = indices[idx_pos]
        entry_price = df["close"].iloc[idx_pos]
        current_atr = df["atr"].iloc[idx_pos]

        if pd.isna(entry_price) or pd.isna(current_atr) or current_atr <= 0:
            continue

        stop_loss = entry_price - sl_mult * current_atr
        take_profit = entry_price + tp_mult * current_atr

        # Forward window
        fwd_window = df.iloc[idx_pos + 1 : idx_pos + 1 + horizon]
        if len(fwd_window) == 0:
            continue

        highs = fwd_window["high"]
        lows = fwd_window["low"]
        closes = fwd_window["close"]

        # Track exit
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
                "mfe": mfe,
                "mae": mae,
                "exit_reason": reason,
            }
        )

    trades_df = pd.DataFrame(trade_records)
    if len(trades_df) > 0:
        trades_df.set_index("entry_time", inplace=True)
        returns = trades_df["gross_return"]
        mfe_series = trades_df["mfe"]
        mae_series = trades_df["mae"]
    else:
        returns = pd.Series(dtype=float)
        mfe_series = pd.Series(dtype=float)
        mae_series = pd.Series(dtype=float)

    # 4. Mandatory Metrics Calculation
    metrics = evaluate_returns(returns, cost=friction_cost, mfe=mfe_series, mae=mae_series)

    # Yearly breakdown
    if len(returns) > 0:
        yearly_df = evaluate_yearly_breakdown(returns, cost=friction_cost)
        print("\n--- Yearly Performance Breakdown ---")
        print(yearly_df.to_string())
        metrics["yearly_breakdown"] = yearly_df.to_dict(orient="records")

    print("\n--- Overall Performance Metrics ---")
    for k, v in metrics.items():
        if k != "yearly_breakdown":
            print(f"  {k}: {v}")

    # 5. Save metrics.json
    out_metrics_path = exp_dir / "metrics.json"
    with open(out_metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"\nSaved metrics to {out_metrics_path}")

    return metrics


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
