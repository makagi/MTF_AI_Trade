"""Unit tests for EXP-139: 1h x 1m Fractal MTF SMA Reciprocation, Cycle Rebound & DualSym Gating."""

import importlib.util
import json
import os
import numpy as np
import pytest

EXP139_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/139-fractal-mtf-cycle-reciprocation-rebound",
)
RUN_PATH = os.path.join(EXP139_DIR, "run.py")
METRICS_PATH = os.path.join(EXP139_DIR, "metrics.json")

spec = importlib.util.spec_from_file_location("exp139_mod", RUN_PATH)
exp139 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp139)


def test_zero_hardcoded_whitelists_and_additive_metrics_integrity():
    """
    Verifies EXP-139 contains zero hardcoded timestamp whitelists and enforces
    strict additive return accounting (never geometric compounding).
    """
    with open(RUN_PATH, "r", encoding="utf-8") as f:
        source_code = f.read()
    assert "MEGA_RUNNER_TIMESTAMPS = {" not in source_code
    assert "np.prod(" not in source_code

    sample_rets = [0.15, 0.05, -0.04]
    res = exp139.compute_additive_portfolio_metrics(sample_rets)
    assert res["executed_trades"] == 3
    np.testing.assert_allclose(res["total_opportunity_net_return_pct"], 16.0, atol=1e-6)
    np.testing.assert_allclose(res["profit_factor"], 0.20 / 0.04, atol=1e-6)


def test_causal_cycle_phase_quadrants_and_period_resonance():
    """
    Verifies causal 2D phase quadrant classification (Q1..Q4), 12-pt hysteresis
    realized period estimation, normal resonance (rho <= 1.3) vs over-aged cycle
    drift (rho > 2.0), and strict causal prefix invariance.
    """
    # Construct two clean 20-bar cycles between Stoch_d 15 and 85, then stall flat
    t_wave = np.arange(45, dtype=float)
    osc = 50.0 - 35.0 * np.cos(2.0 * np.pi * t_wave / 20.0)
    # Append 48 flat bars at Stoch_d = 50.0 to induce > 2.0x over-aged drift
    stalled = np.full(48, 50.0, dtype=float)
    series = np.concatenate([osc, stalled])

    # Normal resonant point right after 2nd cycle trough (around bar 43)
    res_normal = exp139.compute_causal_cycle_phase_and_period_resonance(
        series[:44], hysteresis_pt=12.0, default_period=21.0
    )
    assert res_normal["t_trough"] == pytest.approx(20.0, abs=1.0)
    assert res_normal["t_peak"] == pytest.approx(20.0, abs=1.0)
    assert res_normal["rho_trough"] <= 1.3
    assert res_normal["rho_peak"] <= 1.3
    assert res_normal["quadrant"] in ("Q4", "Q1")

    # Over-aged stalled endpoint -> rho_trough > 2.0 and rho_peak > 2.0
    res_drift = exp139.compute_causal_cycle_phase_and_period_resonance(
        series, hysteresis_pt=12.0, default_period=21.0
    )
    assert res_drift["rho_trough"] > 2.0
    assert res_drift["rho_peak"] > 2.0

    # Strict causality: prefix values must match identically regardless of future bars
    np.testing.assert_allclose(
        res_drift["rho_trough_series"][:44],
        res_normal["rho_trough_series"],
        atol=1e-12,
    )
    assert res_drift["quadrants"][:44] == res_normal["quadrants"]

    # Explicit Q1..Q4 quadrant checks via synthetic 4-bar trajectories
    assert exp139.compute_causal_cycle_phase_and_period_resonance([40, 45, 50, 65])["quadrant"] == "Q1"
    assert exp139.compute_causal_cycle_phase_and_period_resonance([80, 75, 70, 60])["quadrant"] == "Q2"
    assert exp139.compute_causal_cycle_phase_and_period_resonance([60, 50, 45, 30])["quadrant"] == "Q3"
    assert exp139.compute_causal_cycle_phase_and_period_resonance([20, 22, 25, 35])["quadrant"] == "Q4"


def test_cycle_adaptive_rebound_floor_height_estimator():
    """
    Verifies cycle-adaptive rebound floor height P_hat_reb(t) across:
    - Shallow pullback (alpha < 0.35, full stack) -> anchored near SMA(k)
    - Medium pullback (0.35 <= alpha < 0.70) -> blends SMA(k), P_sup(k), BB_lower(k)
    - Deep cycle pullback (alpha >= 0.70) -> blends BB_lower(k) & SMA(k+1)
    - Inverted below parent (d_{k, k+1} <= 0) -> blends BB_lower(k) & P_sup(k)
    """
    atr0 = 500.0
    base_row = {
        "sma_34": 61200.0,
        "sma_55": 60000.0,       # SMA(k)
        "sma_89": 58000.0,       # parent SMA(k+1) -> d_{k, k+1} = 4.0 ATR
        "sup_55": 59200.0,       # P_sup(k)
        "bb_lower_55": 58600.0,  # BB_lower(k)
        "bb_upper_55": 61400.0,
        "bb_lower_34": 60400.0,
    }

    # Shallow pullback: high stoch_d_34 (58) & high bb_pos_55 (0.80) -> alpha ~ 0.02
    shallow_row = dict(base_row, stoch_d_34=58.0, bb_pos_55=0.80)
    p_shallow = exp139.estimate_cycle_adaptive_rebound_floor_height(
        p0=60840.0, atr0=atr0, row_0=shallow_row, sup_scale=55, parent_scale=89
    )
    assert abs(p_shallow - base_row["sma_55"]) <= 200.0

    # Medium pullback: stoch_d_34=35 -> depth_stoch=0.50; bb_pos_55=0.25 -> depth_bb=0.417; alpha~0.46
    med_row = dict(base_row, stoch_d_34=35.0, bb_pos_55=0.25)
    p_med = exp139.estimate_cycle_adaptive_rebound_floor_height(
        p0=59300.0, atr0=atr0, row_0=med_row, sup_scale=55, parent_scale=89
    )
    assert base_row["bb_lower_55"] < p_med < base_row["sma_55"]

    # Deep oversold pullback: stoch_d_34=12 -> depth_stoch=0.96; bb_pos_55=0.05 -> depth_bb=0.75; alpha~0.86
    deep_row = dict(base_row, stoch_d_34=12.0, bb_pos_55=0.05)
    p_deep = exp139.estimate_cycle_adaptive_rebound_floor_height(
        p0=58740.0, atr0=atr0, row_0=deep_row, sup_scale=55, parent_scale=89
    )
    assert base_row["sma_89"] <= p_deep <= base_row["sup_55"]
    assert p_shallow > p_med > p_deep

    # Inverted below parent: sma_55 < sma_89 -> 0.5 * (BB_lower_55 + P_sup_55)
    inv_row = dict(base_row, sma_55=57500.0, sma_89=58000.0, stoch_d_34=25.0, bb_pos_55=0.10)
    p_inv = exp139.estimate_cycle_adaptive_rebound_floor_height(
        p0=58800.0, atr0=atr0, row_0=inv_row, sup_scale=55, parent_scale=89
    )
    np.testing.assert_allclose(p_inv, 0.5 * (58600.0 + 59200.0), atol=1e-6)


def test_1h_dual_symmetric_cycle_gate():
    """
    Verifies 1h DualSym Cycle Gate for Longs and Shorts:
    - Longs pass when rho <= 2.0 and not (Q1 and Stoch_d >= 65).
    - Longs fail on over-aged drift (rho > 2.0) or Q1 overbought (>= 65, dstoch >= 0).
    - Shorts pass when rho <= 2.0 and fail on over-aged peak drift (rho > 2.0).
    """
    # Long passes in resonant Q4 hook and Q2 rollover even if stoch_d >= 65
    assert exp139.evaluate_1h_dual_symmetric_cycle_gate("long", 1.10, 38.0, +4.5) is True
    assert exp139.evaluate_1h_dual_symmetric_cycle_gate("long", 1.25, 70.0, -3.0) is True

    # Long blocked on over-aged drift (rho > 2.0) or Q1 >= 65 overheated chase
    assert exp139.evaluate_1h_dual_symmetric_cycle_gate("long", 2.25, 42.0, +2.0) is False
    assert exp139.evaluate_1h_dual_symmetric_cycle_gate("long", 0.95, 65.0, 0.0) is False
    assert exp139.evaluate_1h_dual_symmetric_cycle_gate("long", 1.15, 74.0, +5.0) is False

    # Short passes when rho <= 2.0, blocked when rho > 2.0
    assert exp139.evaluate_1h_dual_symmetric_cycle_gate("short", 1.20, 62.0, -4.0) is True
    assert exp139.evaluate_1h_dual_symmetric_cycle_gate("short", 2.15, 62.0, -4.0) is False


def test_1m_fractal_reciprocation_and_cycle_gate():
    """
    Verifies 1m Fractal Discernment Gate:
    - Rejects 1m climax pinch (m1_d_21_55 = 4.2 > 3.0 and m1_bb_exp_55 = -0.03 <= 0.0).
    - Passes resonant 1m launches (m1_d_21_55 = 1.0, m1_bb_exp_55 = +0.15) and active
      expanding breakouts even with stretch (m1_d_21_55 = 3.5, m1_bb_exp_55 = +0.10).
    - Rejects 1m short cycle drift (m1_rho_pk_21 = 2.6 > 2.0) while passing resonant
      1m short ignitions (m1_rho_pk_21 = 1.1 <= 2.0).
    """
    # Long: reject 1m climax pinch
    assert exp139.evaluate_1m_fractal_reciprocation_and_cycle_gate(
        "long", m1_d_21_55=4.2, m1_bb_exp_55=-0.03, m1_rho_pk_21=1.0
    ) is False

    # Long: pass resonant 1m launch
    assert exp139.evaluate_1m_fractal_reciprocation_and_cycle_gate(
        "long", m1_d_21_55=1.0, m1_bb_exp_55=0.15, m1_rho_pk_21=1.0
    ) is True

    # Long: pass stretched launch if 1m BB(55) is actively expanding (> 0.0)
    assert exp139.evaluate_1m_fractal_reciprocation_and_cycle_gate(
        "long", m1_d_21_55=3.5, m1_bb_exp_55=0.10, m1_rho_pk_21=1.0
    ) is True

    # Short: reject 1m over-aged peak drift (m1_rho_pk_21 = 2.6)
    assert exp139.evaluate_1m_fractal_reciprocation_and_cycle_gate(
        "short", m1_d_21_55=-1.0, m1_bb_exp_55=0.05, m1_rho_pk_21=2.6
    ) is False

    # Short: pass resonant 1m peak cycle (m1_rho_pk_21 = 1.1)
    assert exp139.evaluate_1m_fractal_reciprocation_and_cycle_gate(
        "short", m1_d_21_55=-1.0, m1_bb_exp_55=0.05, m1_rho_pk_21=1.1
    ) is True


def test_metrics_json_consistency():
    """
    Verifies EXP-139 metrics.json schema, additive accounting, zero whitelists,
    1h/1m orthogonality (0/6 overlap), 10/10 mega-runner plateau preservation,
    and full-mode improvement over EXP-137 Clean Core C1 & C1 + S16.
    """
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["experiment_id"] == "EXP-139"
    assert metrics["issue"] == 139
    assert metrics["hardcoded_whitelist_count"] == 0
    assert metrics["return_accounting"] == "additive_sum_pct"

    heights = metrics["adaptive_rebound_height_estimators"]["springboards_n319"]
    assert heights["Cycle_Adaptive_P_hat_reb"]["med_ae_atr"] < heights["Composite_Mid_Q_SMA"]["med_ae_atr"]
    assert heights["Cycle_Adaptive_P_hat_reb"]["med_ae_atr"] < heights["Static_SMA_k"]["med_ae_atr"]

    orth = metrics["1m_fractal_anatomy_and_orthogonality"]
    assert orth["short_unified_eb_n46_1m_cycle_drift"]["overlap_with_1h_short_drift_count"] == 0
    assert orth["1m_2d_plateau_audit"]["grid_b_cells_mega_runners_10_of_10"] == 30

    prog = metrics["portfolio_ablation_progression"]
    c1 = prog["EXP137_Clean_Core_C1"]
    c1_s16 = prog["EXP137_C1_plus_S16"]
    dual_1h = prog["C1_S16_plus_1h_DualSym_Cycle"]
    master_139 = prog["EXP139_1h_x_1m_Fractal_Master"]

    assert master_139["mega_runners"] == "10/10"
    for mode in ("master_std", "mode_b", "mode_a"):
        assert master_139[mode]["total_opportunity_net_return_pct"] > dual_1h[mode]["total_opportunity_net_return_pct"]
        assert master_139[mode]["profit_factor"] > dual_1h[mode]["profit_factor"]
        assert master_139[mode]["total_opportunity_net_return_pct"] > c1_s16[mode]["total_opportunity_net_return_pct"]
        assert master_139[mode]["total_opportunity_net_return_pct"] > c1[mode]["total_opportunity_net_return_pct"]
        assert master_139[mode]["y2020_2022_pct"] > c1_s16[mode]["y2020_2022_pct"]
        assert master_139[mode]["y2023_2025_pct"] > c1_s16[mode]["y2023_2025_pct"]
