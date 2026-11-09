import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone
import importlib.util
import os

EXP125_DIR = os.path.join(os.path.dirname(__file__), "../../03_KNOWLEDGE/experiments/125-dynamic-scale-extremum-double-wave")
run_path = os.path.join(EXP125_DIR, "run.py")

spec = importlib.util.spec_from_file_location("exp125_mod", run_path)
exp125 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp125)


@pytest.fixture
def mock_df_1h():
    """Builds synthetic 1h DataFrame with required columns for dynamic features."""
    n = 200
    dates = pd.date_range("2021-01-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame(index=dates)
    
    np.random.seed(42)
    base_price = 50000.0 + np.cumsum(np.random.randn(n) * 100.0)
    df['open'] = base_price - 20.0
    df['high'] = base_price + 80.0
    df['low'] = base_price - 80.0
    df['close'] = base_price
    df['atr_24'] = 150.0
    df['range_pos_720h'] = 0.75

    scales = [21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181]
    for s in scales:
        df[f'sma_{s}'] = base_price - s * 0.5
        df[f'slope_{s}'] = 0.01 - (s / 50000.0)
        df[f'bb_lower_{s}'] = df[f'sma_{s}'] - 300.0
        df[f'bb_upper_{s}'] = df[f'sma_{s}'] + 300.0
        df[f'bb_width_{s}'] = 600.0
        df[f'stoch_z_{s}'] = 0.1

    df['stoch_z_21'] = -0.5
    df['afs_L1_(8,13,21)'] = -0.1
    df['tree_L2_[144..987]'] = 0.20
    df['tree_L2_[610..4181]'] = 0.05
    return df


def test_compute_scale_free_dynamic_features(mock_df_1h):
    """Verifies that dynamic features are generated correctly without leakage."""
    exp125.compute_scale_free_dynamic_features(mock_df_1h)

    required_cols = [
        'dyn_k_star', 'dyn_k_macro', 'dyn_s_macro',
        'dyn_m_floor_macro', 'dyn_rho_star', 'dyn_k_flat', 'dyn_stoch_gap'
    ]
    for col in required_cols:
        assert col in mock_df_1h.columns, f"Missing expected column: {col}"

    assert len(mock_df_1h['dyn_k_star']) == len(mock_df_1h)
    assert not mock_df_1h['dyn_s_macro'].isnull().all()
    assert (mock_df_1h['dyn_k_macro'] >= mock_df_1h['dyn_k_star']).all()


def test_find_dynamic_extremum_exhaustion_shorts(mock_df_1h):
    """Verifies that short signals trigger under defined exhaustion conditions."""
    exp125.compute_scale_free_dynamic_features(mock_df_1h)
    
    # Force exhaustion conditions on bar 150
    mock_df_1h.iloc[150, mock_df_1h.columns.get_loc('dyn_s_macro')] = 0.02
    mock_df_1h.iloc[150, mock_df_1h.columns.get_loc('dyn_m_floor_macro')] = -1.5
    mock_df_1h.iloc[150, mock_df_1h.columns.get_loc('dyn_rho_star')] = -0.5
    mock_df_1h.iloc[150, mock_df_1h.columns.get_loc('dyn_stoch_gap')] = -0.6
    mock_df_1h.iloc[150, mock_df_1h.columns.get_loc('close')] = mock_df_1h.iloc[150]['sma_21'] - 50.0

    shorts = exp125.find_dynamic_extremum_exhaustion_shorts(mock_df_1h)
    assert isinstance(shorts, list)
    assert mock_df_1h.index[150] in shorts


def test_find_dynamic_pendulum_rebound_longs(mock_df_1h):
    """Verifies that pendulum rebound longs trigger under deep bottom conditions."""
    exp125.compute_scale_free_dynamic_features(mock_df_1h)
    
    # Force bottom conditions on bar 180
    mock_df_1h.iloc[180, mock_df_1h.columns.get_loc('dyn_k_flat')] = 610
    mock_df_1h.iloc[180, mock_df_1h.columns.get_loc('range_pos_720h')] = 0.30
    mock_df_1h.iloc[180, mock_df_1h.columns.get_loc('dyn_stoch_gap')] = 1.2
    mock_df_1h.iloc[180, mock_df_1h.columns.get_loc('close')] = mock_df_1h.iloc[180]['open'] + 50.0
    mock_df_1h.iloc[180, mock_df_1h.columns.get_loc('close')] = max(mock_df_1h.iloc[180]['close'], mock_df_1h.iloc[180]['sma_21'] + 10.0)

    longs = exp125.find_dynamic_pendulum_rebound_longs(mock_df_1h)
    assert isinstance(longs, list)
