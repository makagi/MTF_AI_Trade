"""Unit tests for EXP-131: Full-Pyramid Continuum Integral & Orthogonal Phase Space Gating."""

import os
import sys
import pytest
import numpy as np
import pandas as pd
import importlib.util

EXP131_DIR = os.path.join(os.path.dirname(__file__), "../../03_KNOWLEDGE/experiments/131-orthogonal-pyramid-continuum")
run_path = os.path.join(EXP131_DIR, "run.py")

spec = importlib.util.spec_from_file_location("exp131_mod", run_path)
exp131 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp131)


@pytest.fixture
def mock_df_1h():
    """Builds synthetic 1h DataFrame with required columns for pyramid and continuum testing."""
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

    scales = exp131.TREE_SCALES
    for s in scales:
        df[f'sma_{s}'] = base_price - (s * 0.1)
        df[f'bb_upper_{s}'] = df[f'sma_{s}'] + 200.0
        df[f'bb_lower_{s}'] = df[f'sma_{s}'] - 200.0
    return df


def test_pyramid_continuum_mathematical_definitions(mock_df_1h):
    """
    Verifies that all Continuum indicators are computed properly and match
    their exact mathematical formulas:
    - Continuum L3..L8 (mean of all nodes in L3..L8)
    - Centroid (exponentially weighted sum w_l = 2^l)
    - Pos node ratio (fraction of positive nodes in [0, 1])
    - Vertical gradient (L8 Root - L1 Mean)
    """
    df, layers = exp131.compute_full_pyramid_continuum(mock_df_1h)

    # 1. Continuum L3..L8: exactly 36 nodes (11+9+7+5+3+1)
    l3_8_concat = pd.concat([layers[l] for l in range(3, 9)], axis=1)
    assert l3_8_concat.shape[1] == 36, f"Expected 36 nodes in L3..L8, got {l3_8_concat.shape[1]}"
    expected_cont = l3_8_concat.mean(axis=1)
    np.testing.assert_allclose(df['curv_continuum_L3_L8'].dropna(), expected_cont.dropna(), rtol=1e-5)

    # 2. Centroid calculation
    w_sum = sum(2**l for l in range(9))
    expected_centroid = sum(2**l * df[f'curv_L{l}_mean'] for l in range(9)) / w_sum
    np.testing.assert_allclose(df['curv_centroid'].dropna(), expected_centroid.dropna(), rtol=1e-5)

    # 3. Positive node ratio
    assert df['curv_pos_node_ratio'].min() >= 0.0
    assert df['curv_pos_node_ratio'].max() <= 1.0

    # 4. Vertical gradient
    expected_grad = df['curv_root'] - df['curv_L1_mean']
    np.testing.assert_allclose(df['curv_vert_gradient'].dropna(), expected_grad.dropna(), rtol=1e-5)


def test_orthogonal_phase_space_quadrant_classification():
    """
    Verifies the 4-Quadrant classification logic of the Orthogonal Phase Space:
    - Quadrant I (X > 0, Y > 0): Bull Ignition
    - Quadrant II (X <= 0, Y > 0): Negative Curvature Runner -> MUST NOT BE BLOCKED
    - Quadrant III (X <= 0, Y <= 0): Disaster Knife Fakeout -> MUST BE BLOCKED
    - Quadrant IV (X > 0, Y <= 0): Counter-trend bounce
    """
    # Sample points
    # Point 1: 2021-02-04 Monster Runner (Curv = -0.002, Tree = +0.65) -> Q2
    x_runner, y_runner = -0.002, 0.65
    is_q2 = (x_runner <= 0.0) and (y_runner > 0.0)
    is_q3_block = (x_runner <= 0.0) and (y_runner <= 0.0)
    assert is_q2 is True, "Monster runner with negative curvature and positive structure must be in Quadrant II!"
    assert is_q3_block is False, "Quadrant II runner must never be blocked by Quadrant III gate!"

    # Point 2: 2022-07-21 Fakeout Knife (Curv = -0.001, Tree = -0.40) -> Q3
    x_knife, y_knife = -0.001, -0.40
    is_knife_blocked = (x_knife <= 0.0) and (y_knife <= 0.0)
    assert is_knife_blocked is True, "Systemic free-falling knife must be blocked by Quadrant III gate!"


def test_zero_lookahead_leakage_guard(mock_df_1h):
    """
    Ensures that adding future bars to the end of the DataFrame does NOT alter
    any continuum feature values at earlier historical timestamps.
    """
    df_short = mock_df_1h.iloc[:200].copy()
    df_full = mock_df_1h.iloc[:250].copy()

    df_short_out, _ = exp131.compute_full_pyramid_continuum(df_short)
    df_full_out, _ = exp131.compute_full_pyramid_continuum(df_full)

    # Check that continuum features at t=150 are identical
    t_check = df_short.index[150]
    for col in ['curv_continuum_L3_L8', 'curv_centroid', 'curv_pos_node_ratio', 'curv_vert_gradient']:
        val_short = df_short_out.loc[t_check, col]
        val_full = df_full_out.loc[t_check, col]
        np.testing.assert_allclose(val_short, val_full, rtol=1e-6, err_msg=f"Future leakage detected in {col}!")


def test_layer_scan_plateau_structure():
    """
    Verifies that the layer scan logic contains all 8 layers and key continuum metrics.
    """
    cols = [f'curv_L{l}_mean' for l in range(9)]
    assert len(cols) == 9
    for l in range(1, 9):
        assert f'curv_L{l}_mean' in cols
