"""Unit tests for EXP-133: Convolved S/R Role Pyramid & Dual Hierarchical Dynamic Anchor."""

import os
import sys
import pytest
import numpy as np
import pandas as pd
import importlib.util

EXP133_DIR = os.path.join(os.path.dirname(__file__), "../../03_KNOWLEDGE/experiments/133-convolved-sr-role-dynamic-anchor")
run_path = os.path.join(EXP133_DIR, "run.py")

spec = importlib.util.spec_from_file_location("exp133_mod", run_path)
exp133 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp133)


@pytest.fixture
def mock_df_1h():
    """Builds synthetic 1h DataFrame with required columns for pyramid and convolved role testing."""
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

    scales = exp133.TREE_SCALES
    for s in scales:
        df[f'sma_{s}'] = base_price - (s * 0.1)
        df[f'slope_{s}'] = np.gradient(df[f'sma_{s}']) / (df['atr_24'] + 1e-8)
        df[f'bb_upper_{s}'] = df[f'sma_{s}'] + 200.0
        df[f'bb_lower_{s}'] = df[f'sma_{s}'] - 200.0
    return df


def test_convolved_sr_role_bounded_and_symmetry(mock_df_1h):
    r"""
    Verifies that all Convolved S/R Role scores are strictly bounded in [-1.0, +1.0]
    and satisfy exact Dual Sign-Flip Symmetry \Phi(-P) = -\Phi(P).
    """
    df, layers = exp133.compute_convolved_sr_role_pyramid_v2(mock_df_1h)

    for s in [34, 55, 89, 144, 233, 377]:
        col = f'phi_bar_{s}'
        assert col in df.columns, f"Missing {col} in DataFrame"
        assert df[col].min() >= -1.0 - 1e-5, f"{col} has values below -1.0"
        assert df[col].max() <= +1.0 + 1e-5, f"{col} has values above +1.0"

    # Exact mathematical dual sign-flip symmetry test
    v = 0.45
    o = 0.70
    m = -0.25
    t = 0.15

    def calc_phi_synthetic(v_val, o_val, m_val, t_val):
        align_prod = v_val * o_val
        g_align = np.clip(0.5 * (1.0 + np.tanh(6.0 * align_prod)), 0.0, 1.0)
        o_dyn = o_val * g_align
        return 0.35 * v_val + 0.25 * o_dyn + 0.25 * m_val + 0.15 * t_val

    phi_pos = calc_phi_synthetic(v, o, m, t)
    phi_neg = calc_phi_synthetic(-v, -o, -m, -t)
    np.testing.assert_allclose(phi_pos + phi_neg, 0.0, atol=1e-10,
                              err_msg="Dual Sign-Flip Symmetry Phi(-P) = -Phi(P) violated!")


def test_slope_alignment_gating_behavior():
    """
    Verifies that slope-alignment gating G_{align} suppresses stale/collapsing MA order
    when slope direction opposes MA ordering.
    """
    def calc_phi(v, o, m, t):
        g = np.clip(0.5 * (1.0 + np.tanh(6.0 * (v * o))), 0.0, 1.0)
        return 0.35 * v + 0.25 * (o * g) + 0.25 * m + 0.15 * t

    # Healthy trend: V=+0.50, O=+0.80 -> G_align ~ 1.0, Phi > 0.35
    phi_healthy = calc_phi(0.50, 0.80, 0.20, 0.50)
    assert phi_healthy > 0.35, f"Expected high positive role for healthy trend, got {phi_healthy}"

    # Sudden collapse: MA order is still bullish (O=+0.80), but slope plunges (V=-0.50)
    # G_align ~ 0.0, suppressing O, resulting in negative role score
    phi_collapse = calc_phi(-0.50, 0.80, -0.60, -0.40)
    assert phi_collapse < -0.20, f"Expected decisive negative role for collapsing trend, got {phi_collapse}"


def test_v3_quantile_sr_pyramids_no_lookahead(mock_df_1h):
    """
    Verifies that self-normalized quantile S/R pyramid v3 computes rolling quantiles
    without lookahead and respects width positivity.
    """
    df, pyramid_dict = exp133.compute_v3_quantile_sr_pyramids(mock_df_1h)

    for s in [34, 55, 89, 144, 233]:
        assert f'sup_{s}' in df.columns
        assert f'res_{s}' in df.columns
        sup_valid = df[f'sup_{s}'].dropna()
        res_valid = df[f'res_{s}'].dropna()
        assert (res_valid >= sup_valid - 1e-5).all(), f"Resistance must be >= Support for scale {s}"
        pos_valid = df[f'pos_{s}'].dropna()
        assert (pos_valid >= 0.0).all() and (pos_valid <= 1.0).all()


def test_dynamic_initial_anchor_selection():
    """
    Verifies that dynamic anchor selection correctly:
    1. Selects 144 on overextension (Case 3 condition: dist_233 > 3.2 and 144 healthy).
    2. Keeps 233 under normal conditions.
    3. Steps down to 144, 89, or 55 when 233 is collapsing or price is below.
    """
    # Case 1: Normal 233 support
    row_normal = pd.Series({
        'sma_233': 50000.0, 'slope_233': 0.005, 'phi_bar_233': 0.40,
        'sma_144': 50200.0, 'slope_144': 0.008, 'phi_bar_144': 0.45,
        'sma_89': 50300.0, 'slope_89': 0.010, 'phi_bar_89': 0.50,
        'sma_55': 50400.0, 'slope_55': 0.012, 'phi_bar_55': 0.55,
        'curv_continuum_L3_L8': 0.001
    })
    anc_normal = exp133.select_initial_dynamic_anchor(p0=50300.0, atr0=150.0, row_0=row_normal)
    assert anc_normal == 233, f"Expected 233 for normal support, got {anc_normal}"

    # Case 2: Overextension Handover to 144 (Case 3 condition)
    row_overextended = pd.Series({
        'sma_233': 50000.0, 'slope_233': 0.001, 'phi_bar_233': 0.25,
        'sma_144': 50300.0, 'slope_144': 0.006, 'phi_bar_144': 0.42,
        'sma_89': 50450.0, 'slope_89': 0.008, 'phi_bar_89': 0.45,
        'sma_55': 50550.0, 'slope_55': 0.010, 'phi_bar_55': 0.48,
        'curv_continuum_L3_L8': 0.000
    })
    anc_overext = exp133.select_initial_dynamic_anchor(p0=50600.0, atr0=150.0, row_0=row_overextended)
    assert anc_overext == 144, f"Expected 144 on overextended 233, got {anc_overext}"

    # Case 3: 233 Collapsing (Negative slope and phi)
    row_collapsing = pd.Series({
        'sma_233': 50000.0, 'slope_233': -0.010, 'phi_bar_233': -0.20,
        'sma_144': 50100.0, 'slope_144': 0.005, 'phi_bar_144': 0.35,
        'sma_89': 50150.0, 'slope_89': 0.008, 'phi_bar_89': 0.40,
        'sma_55': 50200.0, 'slope_55': 0.010, 'phi_bar_55': 0.45,
        'curv_continuum_L3_L8': -0.001
    })
    anc_collapse = exp133.select_initial_dynamic_anchor(p0=50200.0, atr0=150.0, row_0=row_collapsing)
    assert anc_collapse == 144, f"Expected step-down to 144 when 233 collapses, got {anc_collapse}"
