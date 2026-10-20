"""
特徴量モジュールの単体テスト (Unit tests for src/features.py)
"""

import numpy as np
import pandas as pd
import pytest

from src.features import (
    calculate_sma,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_elasticity_index,
    calculate_squeeze_index,
    calculate_afs,
    calculate_topology,
    calculate_fanout_velocity,
    calculate_void_distance,
    calculate_regime_age,
    calculate_level_test_count,
)


@pytest.fixture
def sample_ohlcv_data():
    dates = pd.date_range("2024-01-01", periods=100, freq="1h", tz="UTC")
    np.random.seed(42)
    # トレンドを持つ合成価格
    base = 100.0 + np.cumsum(np.random.normal(0.1, 0.5, 100))
    df = pd.DataFrame(
        {
            "open": base - 0.2,
            "high": base + 0.5,
            "low": base - 0.5,
            "close": base,
            "volume": 1000.0,
        },
        index=dates,
    )
    return df


def test_calculate_sma(sample_ohlcv_data):
    sma = calculate_sma(sample_ohlcv_data["close"], period=10)
    assert len(sma) == 100
    assert pd.isna(sma.iloc[8])
    assert not pd.isna(sma.iloc[9])
    assert sma.iloc[9] == pytest.approx(sample_ohlcv_data["close"].iloc[0:10].mean())


def test_calculate_atr(sample_ohlcv_data):
    atr = calculate_atr(sample_ohlcv_data, period=14)
    assert len(atr) == 100
    assert pd.isna(atr.iloc[12])
    assert not pd.isna(atr.iloc[13])
    assert (atr.dropna() > 0).all()


def test_calculate_bollinger_bands(sample_ohlcv_data):
    up, mid, low = calculate_bollinger_bands(sample_ohlcv_data["close"], period=20, num_std=2.0)
    assert len(up) == 100
    valid_mask = ~up.isna()
    assert (up[valid_mask] >= mid[valid_mask]).all()
    assert (mid[valid_mask] >= low[valid_mask]).all()


def test_calculate_elasticity_index(sample_ohlcv_data):
    # 小さい期間でテスト
    elasticity = calculate_elasticity_index(
        sample_ohlcv_data, cluster_periods=[5, 10, 15], anchor_period=30
    )
    assert len(elasticity) == 100
    valid = elasticity.dropna()
    assert len(valid) > 0
    assert (valid >= 0).all()


def test_calculate_afs(sample_ohlcv_data):
    afs_df, order_score, compression = calculate_afs(
        sample_ohlcv_data, periods=[5, 8, 13]
    )
    assert len(afs_df) == 100
    assert "AFS_5" in afs_df.columns
    assert "AFS_8" in afs_df.columns
    assert "AFS_13" in afs_df.columns
    assert ((order_score >= 0) & (order_score <= 2)).all()
    assert (compression.dropna() >= 0).all()


def test_calculate_fanout_velocity(sample_ohlcv_data):
    velocity = calculate_fanout_velocity(
        sample_ohlcv_data, fast_period=5, slow_period=15, atr_period=10
    )
    assert len(velocity) == 100
    valid = velocity.dropna()
    assert len(valid) > 0


def test_calculate_topology(sample_ohlcv_data):
    sandwich, density = calculate_topology(sample_ohlcv_data, atr_period=10)
    assert len(sandwich) == 100
    assert len(density) == 100
    valid_s = sandwich.dropna()
    assert len(valid_s) > 0
    assert (valid_s >= 0.0).all()
    assert (density >= 0).all()


def test_calculate_void_distance(sample_ohlcv_data):
    void_dist = calculate_void_distance(
        sample_ohlcv_data, overhead_periods=[10, 20, 30], atr_period=10
    )
    assert len(void_dist) == 100
    valid_v = void_dist.dropna()
    assert len(valid_v) > 0
    assert (valid_v >= 0.0).all()


def test_calculate_regime_age(sample_ohlcv_data):
    regime_df = calculate_regime_age(
        sample_ohlcv_data,
        macro_periods=(10, 20, 30),
        meso_periods=(5, 10, 15),
        micro_periods=(3, 5, 8),
        median_durations={"macro": 20.0, "meso": 10.0, "micro": 5.0},
    )
    assert len(regime_df) == 100
    assert "macro_regime" in regime_df.columns
    assert "macro_age_bars" in regime_df.columns
    assert "macro_age_ratio" in regime_df.columns
    assert (regime_df["macro_age_bars"] >= 1).all()
    assert (regime_df["macro_age_ratio"] > 0).all()


def test_calculate_level_test_count(sample_ohlcv_data):
    # Construct a level near the middle
    level = calculate_sma(sample_ohlcv_data["close"], 10)
    test_count_default = calculate_level_test_count(
        sample_ohlcv_data, level=level, window_bars=20, tolerance_atr=0.5
    )
    assert len(test_count_default) == 100
    assert (test_count_default >= 0).all()

    # Verify min_departure_bars separates noisy touches
    test_count_strict = calculate_level_test_count(
        sample_ohlcv_data, level=level, window_bars=20, tolerance_atr=0.5, min_departure_bars=6
    )
    assert len(test_count_strict) == 100
    assert (test_count_strict <= test_count_default).all()

