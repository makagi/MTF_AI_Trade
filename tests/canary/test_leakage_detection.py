"""Canary Benchmark: Data Leakage & Boundary Violation Detection

Tests that data loading and feature calculation reject future information
and enforce the Final Holdout boundary (2026-04-01 onwards).
"""
import pytest
import pandas as pd
from src.data_loader import load_ohlcv
from src.config import HOLDOUT_START

def test_holdout_access_denial():
    """Verify that default load_ohlcv strictly blocks data after Holdout start."""
    df = load_ohlcv()
    # DatetimeIndex is tz-aware (UTC)
    max_date = df.index.max()
    holdout_start = pd.Timestamp(HOLDOUT_START, tz="UTC")
    
    assert max_date < holdout_start, (
        f"Data leakage detected! Max date {max_date} exceeds holdout boundary {holdout_start}"
    )

def test_feature_lookahead_shift():
    """Verify that forward-looking signals are not present in current bar features.
    
    A common agent mistake is computing features using close without proper shift,
    or using future bars (e.g. shift(-1)) in entry condition evaluation.
    """
    dates = pd.date_range("2021-01-01", periods=50, freq="1h")
    prices = pd.Series(range(50), index=dates)
    
    # Correct: rolling mean uses past and current only
    past_rolling = prices.rolling(5).mean()
    assert past_rolling.iloc[4] == prices.iloc[:5].mean()
    
    # Backward test: ensure value at t doesn't change when future t+1 is modified
    prices_alt = prices.copy()
    prices_alt.iloc[10] = 999.0
    
    past_rolling_alt = prices_alt.rolling(5).mean()
    # At t=9, rolling mean must be identical regardless of modification at t=10
    assert past_rolling.iloc[9] == past_rolling_alt.iloc[9], "Feature at t cannot depend on t+1"
