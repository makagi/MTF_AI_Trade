"""Canary Benchmark: Indicator Math Accuracy

Tests that worker-generated calculations of basic indicators (SMA, ATR, Bollinger Bands)
match the deterministic Gold Standard within strict numerical precision.
"""
import pytest
import numpy as np
import pandas as pd

def test_sma_calculation(synthetic_ohlcv, gold_standards):
    """Verify that rolling SMA matches expected values."""
    df = synthetic_ohlcv
    idx = gold_standards["spot_check_index"]
    
    # Calculate SMA 20 and SMA 50
    sma_20 = df["close"].rolling(20).mean()
    sma_50 = df["close"].rolling(50).mean()
    
    expected_sma_20 = gold_standards["sma_20_100"]
    expected_sma_50 = gold_standards["sma_50_100"]
    
    assert np.isclose(sma_20.loc[idx], expected_sma_20, atol=1e-4), (
        f"SMA 20 mismatch at index {idx}: got {sma_20.loc[idx]}, expected {expected_sma_20}"
    )
    assert np.isclose(sma_50.loc[idx], expected_sma_50, atol=1e-4), (
        f"SMA 50 mismatch at index {idx}: got {sma_50.loc[idx]}, expected {expected_sma_50}"
    )

def test_atr_calculation(synthetic_ohlcv, gold_standards):
    """Verify that True Range and ATR 14 match expected formula and values."""
    df = synthetic_ohlcv
    idx = gold_standards["spot_check_index"]
    
    # Standard True Range: max(H-L, |H-C_prev|, |L-C_prev|)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean()
    
    expected_atr = gold_standards["atr_14_100"]
    assert np.isclose(atr_14.loc[idx], expected_atr, atol=1e-4), (
        f"ATR 14 mismatch at index {idx}: got {atr_14.loc[idx]}, expected {expected_atr}"
    )

def test_bollinger_bands_calculation(synthetic_ohlcv, gold_standards):
    """Verify Bollinger Bands 20 (std=2.0) upper and lower bands."""
    df = synthetic_ohlcv
    idx = gold_standards["spot_check_index"]
    
    sma_20 = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std(ddof=0)
    bb_upper = sma_20 + 2.0 * bb_std
    bb_lower = sma_20 - 2.0 * bb_std
    
    expected_upper = gold_standards["bb_upper_100"]
    expected_lower = gold_standards["bb_lower_100"]
    
    assert np.isclose(bb_upper.loc[idx], expected_upper, atol=1e-4), (
        f"BB Upper mismatch at index {idx}: got {bb_upper.loc[idx]}, expected {expected_upper}"
    )
    assert np.isclose(bb_lower.loc[idx], expected_lower, atol=1e-4), (
        f"BB Lower mismatch at index {idx}: got {bb_lower.loc[idx]}, expected {expected_lower}"
    )
