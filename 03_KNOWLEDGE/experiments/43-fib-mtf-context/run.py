"""
Reproducible Experiment Script for Issue #43
Fibonacci Scale Invariance, MTF Context Recognition & Cross-Timeframe Equivalence.
"""

from pathlib import Path
import json
import yaml
import numpy as np
import pandas as pd

from src.data_loader import load_ohlcv
from src.features import calculate_sma, calculate_atr
from src.evaluation import evaluate_returns, evaluate_yearly_breakdown


def run_experiment(exp_dir: Path):
    with open(exp_dir / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    symbol = config.get("symbol") or config["data"]["symbol"]
    start_date = config["data"]["start_date"]
    end_date = config["data"]["end_date"]
    friction_cost = float(config["parameters"]["friction_cost"])
    fib_1m = config["parameters"]["fib_series_1m"]
    fib_1h = config["parameters"]["fib_series_1h"]

    print(f"--- Running Experiment {config['experiment_id']} ---")
    print(f"Loading {symbol} 1h and 1m data...")

    df_1h = load_ohlcv(symbol=symbol, timeframe="1h")
    df_1h = df_1h.loc[start_date:end_date].copy()
    print(f"1h data size: {len(df_1h)} bars ({df_1h.index[0]} to {df_1h.index[-1]})")

    df_1m = load_ohlcv(symbol=symbol, timeframe="1m")
    df_1m = df_1m.loc[start_date:end_date].copy()
    print(f"1m data size: {len(df_1m)} bars ({df_1m.index[0]} to {df_1m.index[-1]})")

    # =========================================================================
    # 1. Calculate Fibonacci SMAs on 1h and 1m
    # =========================================================================
    print("\nCalculating Fibonacci SMAs on 1h...")
    for p in fib_1h:
        df_1h[f"SMA_1h_{p}"] = calculate_sma(df_1h["close"], p)

    print("Calculating Fibonacci SMAs on 1m...")
    for p in fib_1m:
        df_1m[f"SMA_1m_{p}"] = calculate_sma(df_1m["close"], p)

    # =========================================================================
    # 2. Synchronize and Align at 1h timestamps
    # =========================================================================
    print("Aligning 1m and 1h timestamps for exact cross-timeframe comparison...")
    # Resample or match 1m data exactly at each 1h timestamp
    common_idx = df_1h.index.intersection(df_1m.index)
    aligned_1h = df_1h.loc[common_idx]
    aligned_1m = df_1m.loc[common_idx]

    # =========================================================================
    # 3. Cross-Timeframe Equivalence & Correlation Matrix
    # =========================================================================
    print("\n=======================================================")
    print("--- Cross-Timeframe Fibonacci Equivalence Analysis ---")
    print("=======================================================")

    # Hypothesized mapping pairs (1m period / 60 minutes approx 1h period)
    # 6765 / 60 = 112.75 -> between 89 and 144
    # 4181 / 60 = 69.68  -> between 55 and 89
    # 2584 / 60 = 43.07  -> between 34 and 55
    # 1597 / 60 = 26.62  -> between 21 and 34
    # 987  / 60 = 16.45  -> between 13 and 21
    # 610  / 60 = 10.17  -> between 8 and 13
    # 377  / 60 = 6.28   -> between 5 and 8

    mapping_targets = [
        ("SMA_1m_6765", ["SMA_1h_89", "SMA_1h_144"]),
        ("SMA_1m_4181", ["SMA_1h_55", "SMA_1h_89"]),
        ("SMA_1m_2584", ["SMA_1h_34", "SMA_1h_55"]),
        ("SMA_1m_1597", ["SMA_1h_21", "SMA_1h_34"]),
        ("SMA_1m_987",  ["SMA_1h_13", "SMA_1h_21"]),
        ("SMA_1m_610",  ["SMA_1h_8",  "SMA_1h_13"]),
    ]

    equivalence_results = []
    for m1_col, h1_candidates in mapping_targets:
        s_1m = aligned_1m[m1_col]
        for h1_col in h1_candidates:
            s_1h = aligned_1h[h1_col]
            valid_mask = (~s_1m.isna()) & (~s_1h.isna())
            if valid_mask.sum() < 1000:
                continue

            v_1m = s_1m[valid_mask]
            v_1h = s_1h[valid_mask]

            corr = float(v_1m.corr(v_1h))
            mape = float(((v_1m - v_1h).abs() / v_1h).mean() * 100)
            max_dev = float(((v_1m - v_1h).abs() / v_1h).max() * 100)

            # Directional alignment (Slope agreement)
            slope_1m = np.sign(v_1m.diff())
            slope_1h = np.sign(v_1h.diff())
            dir_agreement = float((slope_1m == slope_1h).mean() * 100)

            result_entry = {
                "1m_indicator": m1_col,
                "1h_indicator": h1_col,
                "correlation": corr,
                "mape_percent": mape,
                "max_deviation_percent": max_dev,
                "directional_agreement_percent": dir_agreement,
            }
            equivalence_results.append(result_entry)

            print(
                f"{m1_col:<12} vs {h1_col:<10} | Corr: {corr:.5f} | MAPE: {mape:5.2f}% | "
                f"MaxDev: {max_dev:5.2f}% | DirMatch: {dir_agreement:5.1f}%"
            )

    # Also compute theoretical linear interpolation between Fib(k) and Fib(k+1)
    # For 6765 / 60 = 112.75: weight = (112.75 - 89) / (144 - 89) = 23.75 / 55 = 0.4318
    w = (112.75 - 89) / (144 - 89)
    interp_1h = (1 - w) * aligned_1h["SMA_1h_89"] + w * aligned_1h["SMA_1h_144"]
    valid_m = (~aligned_1m["SMA_1m_6765"].isna()) & (~interp_1h.isna())
    corr_interp = float(aligned_1m.loc[valid_m, "SMA_1m_6765"].corr(interp_1h[valid_m]))
    mape_interp = float(((aligned_1m.loc[valid_m, "SMA_1m_6765"] - interp_1h[valid_m]).abs() / interp_1h[valid_m]).mean() * 100)
    print(f"\n[Theoretical Interpolation] 1m_6765 vs (0.57*1h_89 + 0.43*1h_144):")
    print(f"  Corr: {corr_interp:.5f} | MAPE: {mape_interp:.2f}%")

    # =========================================================================
    # 4. Downsampling & Context-Aware Execution Simulation
    # =========================================================================
    print("\n=======================================================")
    print("--- Downsampling & MTF Context Synergy Simulation ---")
    print("=======================================================")
    # Concept:
    # 1. 1h Macro Context: Check if price is above SMA_1h_144 (Bull context)
    # 2. 1h Meso Squeeze / Pullback: SMA_1h_21 vs SMA_1h_55
    # 3. 1m Micro Execution: Only monitor 1m when 1h signals 'Armed' condition.
    # We compare full 1m continuous simulation vs 1h-guided selective 1m simulation.

    # 1h Guided Pullback Strategy:
    df_1h["atr"] = calculate_atr(df_1h, period=14)
    df_1h["macro_bull"] = df_1h["close"] > df_1h["SMA_1h_144"]
    df_1h["meso_pullback"] = (df_1h["SMA_1h_21"] < df_1h["SMA_1h_55"]) & (df_1h["close"] < df_1h["SMA_1h_21"])
    df_1h["armed"] = df_1h["macro_bull"] & df_1h["meso_pullback"]

    print(f"1h Total bars: {len(df_1h)}")
    print(f"1h Armed bars (Trigger for 1m monitoring): {df_1h['armed'].sum()} ({df_1h['armed'].mean()*100:.1f}%)")
    print(f"Downsampling computation saving: ~{100 - df_1h['armed'].mean()*100:.1f}%")

    # Micro Trigger on 1m during Armed windows
    # Map 1h armed flag to 1m
    df_1m["armed_1h"] = df_1h["armed"].reindex(df_1m.index, method="ffill").fillna(False)

    # 1m local micro hook (fast recovery)
    df_1m["sma_micro_fast"] = calculate_sma(df_1m["close"], 55)
    df_1m["sma_micro_slow"] = calculate_sma(df_1m["close"], 233)
    df_1m["micro_cross"] = (
        (df_1m["sma_micro_fast"] > df_1m["sma_micro_slow"])
        & (df_1m["sma_micro_fast"].shift(1) <= df_1m["sma_micro_slow"].shift(1))
    )

    mtf_signal = df_1m["armed_1h"] & df_1m["micro_cross"]
    print(f"Total MTF signals generated on 1m: {mtf_signal.sum()}")

    # Trade simulation on 1m (Sample trades)
    entry_indices = []
    last_bar = -9999
    horizon_1m = 1440  # 24 hours in 1m bars
    indices_1m = df_1m.index

    # Subsample to keep memory reasonable
    m_sig_idx = np.where(mtf_signal.values)[0]
    for idx_pos in m_sig_idx:
        if idx_pos - last_bar >= horizon_1m // 2 and idx_pos + horizon_1m < len(df_1m):
            entry_indices.append(idx_pos)
            last_bar = idx_pos

    print(f"Executed MTF trades: {len(entry_indices)}")

    trade_returns = []
    trade_mfe = []
    trade_mae = []
    trade_times = []

    for idx_pos in entry_indices:
        p_entry = df_1m["close"].iloc[idx_pos]
        entry_time = indices_1m[idx_pos]
        # Approximate 1h ATR at this time
        c_1h_atr = df_1h["atr"].asof(entry_time)
        if pd.isna(c_1h_atr) or c_1h_atr <= 0:
            c_1h_atr = p_entry * 0.015

        sl = p_entry - 2.0 * c_1h_atr
        tp = p_entry + 3.0 * c_1h_atr

        fwd = df_1m.iloc[idx_pos + 1 : idx_pos + 1 + horizon_1m]
        p_exit = fwd["close"].iloc[-1]

        for step in range(len(fwd)):
            b_low = fwd["low"].iloc[step]
            b_high = fwd["high"].iloc[step]
            if b_low <= sl:
                p_exit = sl
                break
            elif b_high >= tp:
                p_exit = tp
                break

        ret = (p_exit - p_entry) / p_entry
        trade_returns.append(ret)
        trade_times.append(entry_time)
        trade_mfe.append((fwd["high"].max() - p_entry) / p_entry)
        trade_mae.append((fwd["low"].min() - p_entry) / p_entry)

    ret_series = pd.Series(trade_returns, index=trade_times)
    mfe_series = pd.Series(trade_mfe, index=trade_times)
    mae_series = pd.Series(trade_mae, index=trade_times)

    metrics = evaluate_returns(ret_series, cost=friction_cost, mfe=mfe_series, mae=mae_series)
    if len(ret_series) > 0:
        yearly_df = evaluate_yearly_breakdown(ret_series, cost=friction_cost)
        print("\n--- MTF Execution Yearly Breakdown ---")
        print(yearly_df.to_string())
        metrics["yearly_breakdown"] = yearly_df.to_dict(orient="records")

    print("\n--- MTF Execution Overall Metrics ---")
    for k, v in metrics.items():
        if k != "yearly_breakdown":
            print(f"  {k}: {v}")

    metrics["fibonacci_equivalence"] = equivalence_results
    metrics["interpolation_test"] = {
        "formula": "1m_6765 vs (0.57*1h_89 + 0.43*1h_144)",
        "correlation": corr_interp,
        "mape_percent": mape_interp,
    }
    metrics["downsampling_saving_percent"] = float(100 - df_1h["armed"].mean() * 100)

    # Save metrics.json
    out_metrics_path = exp_dir / "metrics.json"
    with open(out_metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"\nSaved metrics to {out_metrics_path}")

    return metrics


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
