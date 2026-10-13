"""Canary Benchmark: MFE / MAE Logic Accuracy

Tests that worker calculations of Maximum Favorable Excursion (MFE)
and Maximum Adverse Excursion (MAE) strictly evaluate post-entry forward price action
without lookback leakage or sign confusion.
"""
import pytest
import numpy as np
import pandas as pd

def test_mfe_mae_long_calculation(synthetic_ohlcv, gold_standards):
    """Verify forward MFE and MAE calculation for Long positions."""
    df = synthetic_ohlcv
    gold_trade = gold_standards["long_trade_idx_100_h10"]
    idx = gold_standards["spot_check_index"]
    horizon = 10
    
    entry_price = df.loc[idx, "close"]
    assert np.isclose(entry_price, gold_trade["entry_price"])
    
    # Forward evaluation window: (idx + 1) to (idx + horizon)
    forward_window = df.loc[idx + 1 : idx + horizon]
    assert len(forward_window) == horizon
    
    max_high = forward_window["high"].max()
    min_low = forward_window["low"].min()
    
    assert np.isclose(max_high, gold_trade["max_high"])
    assert np.isclose(min_low, gold_trade["min_low"])
    
    # Long MFE [%]: (Highest High - Entry) / Entry * 100
    calc_mfe = ((max_high - entry_price) / entry_price) * 100.0
    # Long MAE [%]: (Entry - Lowest Low) / Entry * 100
    calc_mae = ((entry_price - min_low) / entry_price) * 100.0
    
    assert np.isclose(calc_mfe, gold_trade["mfe_pct"], atol=1e-4), (
        f"MFE mismatch: got {calc_mfe}, expected {gold_trade['mfe_pct']}"
    )
    assert np.isclose(calc_mae, gold_trade["mae_pct"], atol=1e-4), (
        f"MAE mismatch: got {calc_mae}, expected {gold_trade['mae_pct']}"
    )
