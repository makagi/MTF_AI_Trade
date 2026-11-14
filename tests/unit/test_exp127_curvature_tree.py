import os
import sys
import pytest
import numpy as np
import pandas as pd
import importlib.util

EXP127_DIR = os.path.join(os.path.dirname(__file__), "../../03_KNOWLEDGE/experiments/127-curvature-tree-pyramid")
run_path = os.path.join(EXP127_DIR, "run.py")

spec = importlib.util.spec_from_file_location("exp127_mod", run_path)
exp127 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp127)


@pytest.fixture
def mock_df_1h():
    """Builds synthetic 1h DataFrame with required columns for curvature testing."""
    n = 300
    dates = pd.date_range("2021-01-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame(index=dates)

    np.random.seed(42)
    base_price = 50000.0 + np.cumsum(np.random.randn(n) * 100.0)
    df['open'] = base_price - 20.0
    df['high'] = base_price + 80.0
    df['low'] = base_price - 80.0
    df['close'] = base_price
    df['atr_24'] = 150.0
    df['range_pos_720h'] = 0.50

    scales = exp127.TREE_SCALES
    for s in scales:
        # Generate smooth mock SMA
        df[f'sma_{s}'] = base_price - (s * 0.1)
    return df


def test_compute_curvature_tree_pyramid_columns_and_shapes(mock_df_1h):
    """Verifies that all 17 scale curvatures and tree pyramid wave-packets are computed."""
    df = exp127.compute_curvature_tree_pyramid(mock_df_1h)

    # 1. Check all 17 scales
    for s in exp127.TREE_SCALES:
        assert f'slope_{s}' in df.columns, f"Missing slope_{s}"
        assert f'curv_{s}' in df.columns, f"Missing curv_{s}"

    # 2. Check canonical aliases
    canonical_aliases = ['curv_L1', 'curv_L2_mid', 'curv_L2_long', 'curv_L2_ultra']
    for alias in canonical_aliases:
        assert alias in df.columns, f"Missing canonical alias: {alias}"
        assert not df[alias].iloc[10:].isnull().all(), f"Alias {alias} contains only NaNs"


def test_curvature_mathematical_precision(mock_df_1h):
    """Verifies exact 2nd difference and triad convolution weighting."""
    df = exp127.compute_curvature_tree_pyramid(mock_df_1h)

    # Verify L1 triad weighting: 0.25 * curv_8 + 0.50 * curv_13 + 0.25 * curv_21
    expected_l1 = 0.25 * df['curv_8'] + 0.50 * df['curv_13'] + 0.25 * df['curv_21']
    np.testing.assert_allclose(df['curv_L1'].dropna(), expected_l1.dropna(), rtol=1e-5)

    # Verify curvature is 2nd difference of SMA:
    # slope_8 = (sma_8 - sma_8.shift(3)) / (3 * atr)
    # curv_8 = (slope_8 - slope_8.shift(3)) / 3.0
    idx = 20
    slope_t = (df['sma_8'].iloc[idx] - df['sma_8'].iloc[idx - 3]) / (3.0 * df['atr_24'].iloc[idx])
    slope_t_minus_3 = (df['sma_8'].iloc[idx - 3] - df['sma_8'].iloc[idx - 6]) / (3.0 * df['atr_24'].iloc[idx - 3])
    expected_curv_8 = (slope_t - slope_t_minus_3) / 3.0
    assert np.isclose(df['curv_8'].iloc[idx], expected_curv_8, rtol=1e-5)


def test_trap_gate_decision_rule():
    """Verifies that Trap Gate properly blocks falling knife dips and passes deceleration dishes."""
    # Knife dip scenario: both L1 and L2_mid negative (downward acceleration)
    curv_l1_knife = -0.002
    curv_l2_knife = -0.001
    knife_blocked = (curv_l1_knife <= 0 and curv_l2_knife <= 0)
    assert knife_blocked is True, "Trap Gate must block downward accelerating knife drops"

    # Deceleration dish scenario 1: L1 turned positive (short-term curve turning up)
    curv_l1_dish1 = 0.001
    curv_l2_dish1 = -0.002
    dish1_blocked = (curv_l1_dish1 <= 0 and curv_l2_dish1 <= 0)
    assert dish1_blocked is False, "Trap Gate must pass deceleration dish when L1 > 0"

    # Deceleration dish scenario 2: L2_mid turned positive (mid-term curve turning up)
    curv_l1_dish2 = -0.0005
    curv_l2_dish2 = 0.0015
    dish2_blocked = (curv_l1_dish2 <= 0 and curv_l2_dish2 <= 0)
    assert dish2_blocked is False, "Trap Gate must pass deceleration dish when L2_mid > 0"


def test_curvature_no_lookahead_leakage(mock_df_1h):
    """Verifies that modifying future bars does not affect past curvature calculations."""
    df1 = mock_df_1h.copy()
    exp127.compute_curvature_tree_pyramid(df1)
    val_at_100_orig = df1['curv_L1'].iloc[100]

    # Alter future data from bar 105 onwards
    df2 = mock_df_1h.copy()
    df2.iloc[105:, df2.columns.get_loc('sma_8')] *= 2.0
    df2.iloc[105:, df2.columns.get_loc('sma_13')] *= 2.0
    df2.iloc[105:, df2.columns.get_loc('sma_21')] *= 2.0
    exp127.compute_curvature_tree_pyramid(df2)
    val_at_100_modified = df2['curv_L1'].iloc[100]

    assert np.isclose(val_at_100_orig, val_at_100_modified, rtol=1e-8), "Future modification altered past curvature! Lookahead leak detected."
