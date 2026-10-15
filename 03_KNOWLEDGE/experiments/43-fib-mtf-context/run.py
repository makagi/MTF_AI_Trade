"""
Reproducible Experiment Script for Issue #43
Fibonacci Scale Invariance, MTF Context Recognition & Cross-Timeframe Equivalence.
Comprehensive Multi-Feature Analysis: SMA, BB Width, Rolling Extremes, Stochastics, and ATR.
"""

from pathlib import Path
import json
import yaml
import numpy as np
import pandas as pd

from src.data_loader import load_ohlcv
from src.features import calculate_sma, calculate_atr, calculate_bollinger_bands
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
    # 1. Feature Calculations on 1h and 1m (SMA, BB Width, Extremes, Stoch, ATR)
    # =========================================================================
    print("\nCalculating 1h Multi-Features across Fibonacci series...")
    for p in fib_1h:
        # SMA
        df_1h[f"SMA_1h_{p}"] = calculate_sma(df_1h["close"], p)
        # BB Width
        up, _, low = calculate_bollinger_bands(df_1h["close"], period=p)
        df_1h[f"BBW_1h_{p}"] = (up - low) / df_1h["close"]
        # Extremes
        hh = df_1h["high"].rolling(window=p, min_periods=p).max()
        ll = df_1h["low"].rolling(window=p, min_periods=p).min()
        df_1h[f"HH_1h_{p}"] = hh
        df_1h[f"LL_1h_{p}"] = ll
        # Stoch %K
        df_1h[f"STOCH_1h_{p}"] = ((df_1h["close"] - ll) / (hh - ll + 1e-8)) * 100
        # ATR
        df_1h[f"ATR_1h_{p}"] = calculate_atr(df_1h, period=p)

    print("Calculating 1m Multi-Features across Fibonacci series...")
    for p in fib_1m:
        # SMA
        df_1m[f"SMA_1m_{p}"] = calculate_sma(df_1m["close"], p)
        # BB Width
        up, _, low = calculate_bollinger_bands(df_1m["close"], period=p)
        df_1m[f"BBW_1m_{p}"] = (up - low) / df_1m["close"]
        # Extremes
        hh = df_1m["high"].rolling(window=p, min_periods=p).max()
        ll = df_1m["low"].rolling(window=p, min_periods=p).min()
        df_1m[f"HH_1m_{p}"] = hh
        df_1m[f"LL_1m_{p}"] = ll
        # Stoch %K
        df_1m[f"STOCH_1m_{p}"] = ((df_1m["close"] - ll) / (hh - ll + 1e-8)) * 100
        # ATR
        df_1m[f"ATR_1m_{p}"] = calculate_atr(df_1m, period=p)

    # =========================================================================
    # 2. Synchronize and Align at 1h timestamps
    # =========================================================================
    print("Aligning 1m and 1h timestamps for exact cross-timeframe comparison...")
    common_idx = df_1h.index.intersection(df_1m.index)
    aligned_1h = df_1h.loc[common_idx]
    aligned_1m = df_1m.loc[common_idx]

    # =========================================================================
    # 3. Comprehensive Multi-Feature Equivalence Analysis
    # =========================================================================
    print("\n===========================================================================")
    print("--- Cross-Timeframe Multi-Feature Equivalence Analysis (1m vs 1h) ---")
    print("===========================================================================")

    mapping_targets = [
        (6765, [89, 144]),
        (4181, [55, 89]),
        (2584, [34, 55]),
        (1597, [21, 34]),
        (987,  [13, 21]),
        (610,  [8,  13]),
    ]

    all_feature_results = {}

    for feature_type in ["SMA", "BBW", "HH", "LL", "STOCH", "ATR"]:
        print(f"\n>>> Feature Type: {feature_type}")
        feat_entries = []
        for p_1m, p_1h_list in mapping_targets:
            col_1m = f"{feature_type}_1m_{p_1m}"
            s_1m = aligned_1m[col_1m]
            for p_1h in p_1h_list:
                col_1h = f"{feature_type}_1h_{p_1h}"
                s_1h = aligned_1h[col_1h]

                valid_mask = (~s_1m.isna()) & (~s_1h.isna())
                if valid_mask.sum() < 1000:
                    continue

                v_1m = s_1m[valid_mask]
                v_1h = s_1h[valid_mask]

                corr = float(v_1m.corr(v_1h))
                # For zero or bounded indicators
                base_denom = v_1h.replace(0, np.nan)
                mape = float(((v_1m - v_1h).abs() / base_denom.abs()).mean() * 100) if feature_type != "STOCH" else float((v_1m - v_1h).abs().mean())
                ratio_mean = float((v_1m / base_denom).mean())

                entry = {
                    "1m_col": col_1m,
                    "1h_col": col_1h,
                    "correlation": corr,
                    "diff_metric": mape,
                    "ratio_mean": ratio_mean,
                }
                feat_entries.append(entry)

                metric_label = "MAE(pts)" if feature_type == "STOCH" else "MAPE(%)"
                print(f"  {col_1m:<14} vs {col_1h:<12} | Corr: {corr:.5f} | {metric_label}: {mape:6.2f} | Ratio(1m/1h): {ratio_mean:.3f}")

        all_feature_results[feature_type] = feat_entries

    # =========================================================================
    # 4. Downsampling & MTF Armed-Execution Simulation
    # =========================================================================
    print("\n=======================================================")
    print("--- Downsampling & MTF Context Synergy Simulation ---")
    print("=======================================================")

    # 1h Guided Pullback Strategy:
    df_1h["macro_bull"] = df_1h["close"] > df_1h["SMA_1h_144"]
    df_1h["meso_pullback"] = (df_1h["SMA_1h_21"] < df_1h["SMA_1h_55"]) & (df_1h["close"] < df_1h["SMA_1h_21"])
    df_1h["armed"] = df_1h["macro_bull"] & df_1h["meso_pullback"]

    print(f"1h Total bars: {len(df_1h)}")
    print(f"1h Armed bars (Trigger for 1m monitoring): {df_1h['armed'].sum()} ({df_1h['armed'].mean()*100:.1f}%)")
    print(f"Downsampling computation saving: ~{100 - df_1h['armed'].mean()*100:.1f}%")

    # Map 1h armed flag to 1m
    df_1m["armed_1h"] = df_1h["armed"].reindex(df_1m.index, method="ffill").fillna(False)

    # 1m local micro hook
    df_1m["sma_micro_fast"] = calculate_sma(df_1m["close"], 55)
    df_1m["sma_micro_slow"] = calculate_sma(df_1m["close"], 233)
    df_1m["micro_cross"] = (
        (df_1m["sma_micro_fast"] > df_1m["sma_micro_slow"])
        & (df_1m["sma_micro_fast"].shift(1) <= df_1m["sma_micro_slow"].shift(1))
    )

    mtf_signal = df_1m["armed_1h"] & df_1m["micro_cross"]
    print(f"Total MTF signals generated on 1m: {mtf_signal.sum()}")

    # Trade simulation
    entry_indices = []
    last_bar = -9999
    horizon_1m = 1440
    indices_1m = df_1m.index

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
        c_1h_atr = df_1h["ATR_1h_13"].asof(entry_time)
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

    metrics["multi_feature_equivalence"] = all_feature_results
    metrics["downsampling_saving_percent"] = float(100 - df_1h["armed"].mean() * 100)

    # Save metrics.json
    out_metrics_path = exp_dir / "metrics.json"
    with open(out_metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"\nSaved multi-feature metrics to {out_metrics_path}")

    return metrics


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    run_experiment(current_dir)
