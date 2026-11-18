"""Unit tests for EXP-135: Scale-Agnostic Dual Baseline & Role-Weighted 2D Cross-Scale Tensor."""

import os
import json
import pytest
import numpy as np
import pandas as pd
import importlib.util

EXP135_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/135-scale-agnostic-dual-integrated-baseline",
)
RUN_PATH = os.path.join(EXP135_DIR, "run.py")
METRICS_PATH = os.path.join(EXP135_DIR, "metrics.json")

spec = importlib.util.spec_from_file_location("exp135_mod", RUN_PATH)
exp135 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp135)


def test_zero_hardcoded_whitelists_and_additive_metrics_integrity():
    """
    Verifies that EXP-135 contains zero hardcoded timestamp whitelists and
    strictly enforces additive return accounting (never geometric compounding).
    """
    with open(RUN_PATH, "r", encoding="utf-8") as f:
        source_code = f.read()
    assert "MEGA_RUNNER_TIMESTAMPS = {" not in source_code
    assert "np.prod(" not in source_code

    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    assert metrics["hardcoded_whitelist_count"] == 0
    assert metrics["return_accounting"] == "additive_sum_pct"

    # Verify additive sum calculation vs compounding
    sample_rets = [0.10, 0.10, -0.05]
    res = exp135.compute_additive_portfolio_metrics(sample_rets)
    assert res["executed_trades"] == 3
    # Additive sum = (0.10 + 0.10 - 0.05) * 100 = 15.0% (NOT compounded 14.95%)
    np.testing.assert_allclose(res["total_opportunity_net_return_pct"], 15.0, atol=1e-6)
    np.testing.assert_allclose(res["profit_factor"], 0.20 / 0.05, atol=1e-6)


def test_dynamic_resistance_anchor_selection():
    """
    Verifies scale-agnostic dynamic resistance anchor selection for Stage 2 Macro Shorts:
    1. Selects 144 when S233 is overextended (> 3.2 ATR above price) and S144 is active resistance.
    2. Selects 233 under normal valid overhead resistance.
    3. Steps down to 144 or 89 when S233 is below price or supportive.
    """
    p0 = 50000.0
    atr0 = 500.0

    # 1. Overextended S233 (dist = 4.0 ATR > 3.2) with active S144 resistance
    row_overext = {
        "sma_233": 52000.0, "slope_233": -0.002, "phi_bar_233": -0.25,
        "sma_144": 50800.0, "slope_144": -0.005, "phi_bar_144": -0.35,
        "sma_89": 50400.0, "slope_89": -0.006, "phi_bar_89": -0.40,
    }
    assert exp135.select_initial_dynamic_resistance_anchor(p0, atr0, row_overext) == 144

    # 2. Normal S233 resistance (dist = 2.0 ATR <= 3.2)
    row_normal = {
        "sma_233": 51000.0, "slope_233": -0.003, "phi_bar_233": -0.30,
        "sma_144": 50600.0, "slope_144": -0.004, "phi_bar_144": -0.35,
    }
    assert exp135.select_initial_dynamic_resistance_anchor(p0, atr0, row_normal) == 233

    # 3. S233 below price (broken/lagging) -> steps down to overhead S89
    row_stepdown = {
        "sma_233": 49000.0, "slope_233": 0.005, "phi_bar_233": 0.30,
        "sma_144": 49500.0, "slope_144": 0.003, "phi_bar_144": 0.20,
        "sma_89": 50500.0, "slope_89": -0.004, "phi_bar_89": -0.25,
    }
    assert exp135.select_initial_dynamic_resistance_anchor(p0, atr0, row_stepdown) == 89


def test_nearest_defended_floor_ignores_broken_smas():
    """
    Verifies physical law K-084:
    An SMA below price with broken support role (phi_bar_s <= 0.0) is transparent (93.4% shatter rate)
    and must NOT be treated as a defended support floor bottleneck.
    """
    p0 = 50000.0
    atr0 = 500.0
    row = {}
    for s in exp135.TREE_SCALES:
        row[f"sma_{s}"] = 51000.0  # above price by default
        row[f"phi_bar_{s}"] = -0.20

    # Place S55 only 0.6 ATR below price, BUT with broken role (phi_bar_55 = -0.30 <= 0)
    row["sma_55"] = 49700.0
    row["phi_bar_55"] = -0.30

    # Place S233 at 4.0 ATR below price WITH active defended support role (phi_bar_233 = +0.25 > 0.05)
    row["sma_233"] = 48000.0
    row["phi_bar_233"] = 0.25

    dist_atr, floor_scale, floor_price = exp135.compute_nearest_defended_floor_clearance(
        p0, atr0, row, phi_min=0.05
    )
    assert floor_scale == 233
    np.testing.assert_allclose(dist_atr, 4.0, atol=1e-6)
    np.testing.assert_allclose(floor_price, 48000.0, atol=1e-6)


def test_cumulative_barrier_role_weighted_2d_tensor_opacity():
    """
    Verifies that in the Cumulative-Barrier Role-Weighted 2D Tensor:
    - When an intermediate floor (e.g. S55 at 0.6 ATR) has broken support (phi_bar_55 = -0.20 -> w=0),
      the effective void to a deeper floor (S233 at 5.0 ATR) passes right through (5.0 ATR).
    - When S55 becomes an active bedrock floor (phi_bar_55 = +0.35 -> w=1.0),
      it acts as an opaque barrier and caps the effective void to 0.6 ATR!
    """
    p0 = 50000.0
    atr0 = 500.0

    base_row = {}
    for s in exp135.TREE_SCALES:
        base_row[f"sma_{s}"] = 50500.0
        base_row[f"phi_bar_{s}"] = -0.10
        base_row[f"bb_upper_{s}"] = 50400.0  # 0.8 ATR micro risk

    # S55 is 0.6 ATR below; S233..S2584 are 5.0 ATR below
    base_row["sma_55"] = 49700.0  # 0.6 ATR
    for s in (144, 233, 377, 610, 987, 1597, 2584):
        base_row[f"sma_{s}"] = 47500.0  # 5.0 ATR
        base_row[f"phi_bar_{s}"] = 0.25

    # Case A: S55 is broken (phi_bar_55 = -0.25 -> transparent w_55 = 0.0)
    row_transparent = dict(base_row)
    row_transparent["phi_bar_55"] = -0.25
    rr_raw_open, _, macro_rr_open = exp135.compute_cumulative_barrier_role_weighted_2d_tensor(
        p0, atr0, row_transparent
    )

    # Case B: S55 is solid bedrock (phi_bar_55 = +0.35 -> opaque w_55 = 1.0)
    row_blocked = dict(base_row)
    row_blocked["phi_bar_55"] = +0.35
    rr_raw_blocked, _, macro_rr_blocked = exp135.compute_cumulative_barrier_role_weighted_2d_tensor(
        p0, atr0, row_blocked
    )

    assert macro_rr_open > 4.0, f"Expected open cascade void RR > 4.0, got {macro_rr_open}"
    assert macro_rr_blocked < 1.0, f"Expected opaque barrier to cap RR < 1.0, got {macro_rr_blocked}"


def test_orthogonal_role_2d_short_gate():
    """
    Verifies that the Orthogonal Role-Weighted 2D Tensor Short Gate requires BOTH:
    1. Spatial Void (d_def_05 >= 2.5 and macro_rr_eff >= 2.0)
    2. Wave Alignment (bb_slope_exp_continuum_L3_L8 >= 0.0 and curv_L1_mean <= 0.0)
    """
    good_row = {"bb_slope_exp_continuum_L3_L8": 0.015, "curv_L1_mean": -0.002}
    assert exp135.evaluate_orthogonal_role_2d_short_gate(good_row, macro_rr_eff=3.5, d_def_05=3.2) is True

    # Fails when BB is contracting (< 0.0)
    squeeze_row = {"bb_slope_exp_continuum_L3_L8": -0.020, "curv_L1_mean": -0.002}
    assert exp135.evaluate_orthogonal_role_2d_short_gate(squeeze_row, macro_rr_eff=3.5, d_def_05=3.2) is False

    # Fails when short-term curvature is still accelerating upward (> 0.0)
    accel_up_row = {"bb_slope_exp_continuum_L3_L8": 0.015, "curv_L1_mean": +0.003}
    assert exp135.evaluate_orthogonal_role_2d_short_gate(accel_up_row, macro_rr_eff=3.5, d_def_05=3.2) is False

    # Fails when defended support floor is too close (< 2.5 ATR)
    floor_trap_row = {"bb_slope_exp_continuum_L3_L8": 0.015, "curv_L1_mean": -0.002}
    assert exp135.evaluate_orthogonal_role_2d_short_gate(floor_trap_row, macro_rr_eff=3.5, d_def_05=1.2) is False
