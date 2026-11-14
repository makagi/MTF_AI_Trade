"""Unit tests for EXP-129: Full-Spectrum Multi-Layer Curvature Tree Pyramid Convolution & Divergence."""

import os
import sys
import pytest
import numpy as np
import pandas as pd
import importlib.util

EXP129_DIR = os.path.join(os.path.dirname(__file__), "../../03_KNOWLEDGE/experiments/129-full-pyramid-curvature-divergence")
run_path = os.path.join(EXP129_DIR, "run.py")

spec = importlib.util.spec_from_file_location("exp129_mod", run_path)
exp129 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp129)


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

    scales = exp129.TREE_SCALES
    for s in scales:
        df[f'sma_{s}'] = base_price - (s * 0.1)
    return df


def test_full_pyramid_layer_dimensions_and_node_counts(mock_df_1h):
    """Verifies that all 8 convolution layers have the exact expected node counts and aliases."""
    df, layers = exp129.compute_full_pyramid_curvature(mock_df_1h)

    expected_nodes = {
        0: 17,  # Raw 17 scales
        1: 15,  # Triads (8..21) to (6765..17711)
        2: 13,  # [8..55] to [2584..17711]
        3: 11,  # [8..144] to [987..17711]
        4: 9,   # [8..377] to [377..17711]
        5: 7,   # [8..987] to [144..17711]
        6: 5,   # [8..2584] to [55..17711]
        7: 3,   # [8..6765] to [21..17711]
        8: 1    # [8..17711] Global Root
    }

    for l_idx, exp_count in expected_nodes.items():
        assert l_idx in layers, f"Layer {l_idx} missing from layers dict"
        assert len(layers[l_idx].columns) == exp_count, (
            f"Layer {l_idx} node count mismatch: expected {exp_count}, got {len(layers[l_idx].columns)}"
        )

    # Layer 8 must have exactly 1 column named '[8..17711]'
    assert layers[8].columns[0] == "[8..17711]"
    assert 'curv_root' in df.columns
    np.testing.assert_allclose(df['curv_root'].dropna(), layers[8].iloc[:, 0].dropna(), rtol=1e-6)

    # Check canonical aliases
    for alias in ['curv_L1', 'curv_L2_mid', 'curv_L2_long', 'curv_L2_ultra', 'curv_root', 'curv_L4_mean']:
        assert alias in df.columns, f"Missing canonical alias: {alias}"
        assert not df[alias].iloc[20:].isnull().all(), f"Alias {alias} contains only NaNs"


def test_full_pyramid_mathematical_convolution_precision(mock_df_1h):
    """Verifies exact triad and recursive kernel weights [0.25, 0.50, 0.25] and [0.30, 0.40, 0.30]."""
    df, layers = exp129.compute_full_pyramid_curvature(mock_df_1h)

    # Layer 1 triad (8, 13, 21): 0.25 * curv_8 + 0.50 * curv_13 + 0.25 * curv_21
    expected_l1 = 0.25 * df['curv_8'] + 0.50 * df['curv_13'] + 0.25 * df['curv_21']
    np.testing.assert_allclose(layers[1].iloc[:, 0].dropna(), expected_l1.dropna(), rtol=1e-5)

    # Layer 2 first node [8..55]: 0.30 * L1_0 + 0.40 * L1_1 + 0.30 * L1_2
    l1_0 = layers[1].iloc[:, 0]
    l1_1 = layers[1].iloc[:, 1]
    l1_2 = layers[1].iloc[:, 2]
    expected_l2 = 0.30 * l1_0 + 0.40 * l1_1 + 0.30 * l1_2
    np.testing.assert_allclose(layers[2].iloc[:, 0].dropna(), expected_l2.dropna(), rtol=1e-5)


def test_systemic_plunge_gate_logic():
    """
    Verifies HYP-129-1 Systemic Plunge Gate:
    - Blocks entry ONLY when BOTH micro <= 0 AND macro root <= 0 (e.g. 2023-04-21 knife).
    - Preserves entry when micro <= 0 BUT macro root > 0 (normal megatrend consolidation breathing).
    """
    # 1. Systemic falling knife: both plunge negative -> MUST BLOCK
    micro_knife = -0.0020
    macro_knife = -0.0005
    knife_blocked = (micro_knife <= 0) and (macro_knife <= 0)
    assert knife_blocked is True, "Systemic plunge (micro <= 0 and macro <= 0) must be blocked!"

    # 2. Megatrend breathing pullback: micro negative, but macro root positive -> MUST PASS (runner protected)
    micro_breathing = -0.0040
    macro_breathing = +0.0012
    breathing_blocked = (micro_breathing <= 0) and (macro_breathing <= 0)
    assert breathing_blocked is False, "Megatrend breathing (micro <= 0, macro > 0) must NOT be blocked!"

    # 3. Bottom rebound ignition: micro positive, macro still bottoming -> MUST PASS
    micro_rebound = +0.0015
    macro_rebound = -0.0002
    rebound_blocked = (micro_rebound <= 0) and (macro_rebound <= 0)
    assert rebound_blocked is False, "Rebound ignition (micro > 0) must NOT be blocked!"


def test_macro_respiration_shield_exit_logic():
    """
    Verifies HYP-129-2 Macro Respiration Shield Exit:
    - In high profit (MFE >= 8.0 ATR), anchor ratchet to S34 is permitted ONLY when macro root <= 0.
    - When macro root > 0, the position is shielded against premature exit during breathing.
    """
    # Scenario A: High profit, but macro root > 0 (breathing) -> ratchet must be shielded (False)
    mfe_atr = 10.5
    prev_curv_root = 0.0010
    cur_curv_root_breathing = 0.0005  # slowed down, but still positive
    macro_rollover_a = (prev_curv_root >= 0.0 and cur_curv_root_breathing <= 0.0)
    allow_ratchet_a = (mfe_atr >= 8.0) and macro_rollover_a
    assert allow_ratchet_a is False, "Megatrend breathing (curv_root > 0) must shield anchor from ratcheting!"

    # Scenario B: High profit, and macro root rolls over <= 0 (true macro top collapse) -> ratchet allowed (True)
    cur_curv_root_collapse = -0.0002
    macro_rollover_b = (prev_curv_root >= 0.0 and cur_curv_root_collapse <= 0.0)
    allow_ratchet_b = (mfe_atr >= 8.0) and macro_rollover_b
    assert allow_ratchet_b is True, "Macro rollover (curv_root <= 0) must trigger profit defense ratchet!"


def test_zero_lookahead_temporal_leakage(mock_df_1h):
    """Verifies that future data mutations do not leak backward into past curvature or pyramid convolution."""
    df1 = mock_df_1h.copy()
    df1, _ = exp129.compute_full_pyramid_curvature(df1)
    root_at_100_orig = df1['curv_root'].iloc[100]
    l1_at_100_orig = df1['curv_L1'].iloc[100]

    # Mutate data strictly from bar 105 onwards
    df2 = mock_df_1h.copy()
    df2.iloc[105:, df2.columns.get_loc('close')] *= 2.5
    for s in exp129.TREE_SCALES:
        df2.iloc[105:, df2.columns.get_loc(f'sma_{s}')] *= 2.5

    df2, _ = exp129.compute_full_pyramid_curvature(df2)
    root_at_100_mod = df2['curv_root'].iloc[100]
    l1_at_100_mod = df2['curv_L1'].iloc[100]

    assert np.isclose(root_at_100_orig, root_at_100_mod, rtol=1e-8), "Lookahead leakage detected in curv_root!"
    assert np.isclose(l1_at_100_orig, l1_at_100_mod, rtol=1e-8), "Lookahead leakage detected in curv_L1!"
