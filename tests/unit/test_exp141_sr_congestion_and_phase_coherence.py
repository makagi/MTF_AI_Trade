"""Unit tests for EXP-141: 3D S/R Congestion Decomposition & Multi-Scale Circular Phase Coherence."""

import importlib.util
import json
import os
import numpy as np
import pytest

EXP141_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/141-sr-congestion-3d-and-phase-coherence",
)
RUN_PATH = os.path.join(EXP141_DIR, "run.py")
METRICS_PATH = os.path.join(EXP141_DIR, "metrics.json")

spec = importlib.util.spec_from_file_location("exp141_mod", RUN_PATH)
exp141 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp141)


def test_zero_hardcoded_whitelists_and_additive_metrics_integrity():
    """
    Verifies EXP-141 contains zero hardcoded timestamp whitelists and enforces
    strict additive return accounting (never geometric compounding).
    """
    with open(RUN_PATH, "r", encoding="utf-8") as f:
        source_code = f.read()
    assert "MEGA_RUNNER_TIMESTAMPS = {" not in source_code
    assert "np.prod(" not in source_code

    sample_rets = [0.20, 0.05, -0.05]
    res = exp141.compute_additive_portfolio_metrics(sample_rets)
    assert res["executed_trades"] == 3
    np.testing.assert_allclose(res["total_opportunity_net_return_pct"], 20.0, atol=1e-6)
    np.testing.assert_allclose(res["profit_factor"], 0.25 / 0.05, atol=1e-6)


def test_circular_cycle_phase_coherence():
    """
    Verifies Kuramoto order parameter R = |(1/M) * sum exp(i * theta_m)|:
    - Returns ~1.0 for tightly synchronized multi-scale phase angles.
    - Returns < 0.3 for anti-phase / destructively interfering angles.
    """
    r_sync = exp141.compute_circular_cycle_phase_coherence([0.40, 0.42, 0.39, 0.41, 0.40])
    assert r_sync > 0.99
    assert r_sync <= 1.0

    r_exact = exp141.compute_circular_cycle_phase_coherence([1.2, 1.2, 1.2, 1.2, 1.2])
    np.testing.assert_allclose(r_exact, 1.0, atol=1e-12)

    r_anti = exp141.compute_circular_cycle_phase_coherence([0.0, np.pi, 0.15, np.pi + 0.10, -np.pi / 2])
    assert 0.0 <= r_anti < 0.30

    with pytest.raises(ValueError):
        exp141.compute_circular_cycle_phase_coherence([])


def test_sr_congestion_3d_decomposition_and_long_gate():
    """
    Verifies 3D S/R Congestion Decomposition (Density x Vertical Ordering x Slope)
    and Long Gate:
    - Low-density (lam_15 < 5) passes.
    - High-density Ordered+Rising launchpad (lam_15 >= 5, inv=0, triad=True, slopes>0) passes.
    - High-density Coherent Macro V-Bottom (lam_15 >= 5, inv>0, slopes<=0, R_mean=0.93) passes.
    - True Spaghetti Trap (lam_15 >= 5, inv>0, slopes<=0, R_mean=0.65) is rejected.
    """
    atr0 = 500.0
    p0 = 60000.0

    # 1. Low-Density row (lam_15 = 2 < 5) -> passes regardless of coherence
    low_dens_row = {
        "sma_34": 60300.0,
        "sma_55": 59800.0,
        "sma_89": 59500.0,
        "slope_55": 0.05,
        "slope_89": 0.03,
        "slope_610": 0.02,
    }
    lam_low, inv_low, triad_low, slp_low, mac_low, quad_low = exp141.compute_sr_congestion_3d_decomposition(
        p0=p0, atr0=atr0, row_0=low_dens_row, sup_scale=55, parent_scale=89
    )
    assert lam_low < 5
    assert quad_low == "Q1_Ordered_Rising"
    assert exp141.evaluate_3d_sr_congestion_long_gate(
        lam_low, inv_low, triad_low, slp_low, mac_low, r_mean_coherence=0.55
    ) is True

    # 2. High-Density Ordered + Rising Launchpad (lam_15 = 6 >= 5, inv = 0, rising slopes)
    launchpad_row = {
        "sma_21": 59950.0,
        "sma_34": 59900.0,
        "sma_55": 59800.0,
        "bb_lower_55": 59600.0,
        "sup_55": 59700.0,
        "sma_89": 59500.0,
        "slope_55": 0.15,
        "slope_89": 0.12,
        "slope_610": 0.04,
    }
    lam_lp, inv_lp, triad_lp, slp_lp, mac_lp, quad_lp = exp141.compute_sr_congestion_3d_decomposition(
        p0=p0, atr0=atr0, row_0=launchpad_row, sup_scale=55, parent_scale=89
    )
    assert lam_lp >= 5
    assert inv_lp == 0
    assert triad_lp is True
    assert slp_lp is True
    assert mac_lp is True
    assert quad_lp == "Q1_Ordered_Rising"
    assert exp141.evaluate_3d_sr_congestion_long_gate(
        lam_lp, inv_lp, triad_lp, slp_lp, mac_lp, r_mean_coherence=0.65
    ) is True

    # 3. High-Density Inverted + Degraded Slopes (Macro V-Bottom vs Spaghetti Trap)
    spaghetti_row = {
        "sma_21": 59500.0,     # inverted below sma_34 / sma_55 / sma_89
        "sma_34": 59650.0,
        "sma_55": 59750.0,
        "bb_lower_55": 59450.0,
        "sup_55": 59550.0,
        "sma_89": 59850.0,
        "slope_55": -0.04,
        "slope_89": -0.06,
        "slope_610": -0.01,
    }
    lam_sp, inv_sp, triad_sp, slp_sp, mac_sp, quad_sp = exp141.compute_sr_congestion_3d_decomposition(
        p0=p0, atr0=atr0, row_0=spaghetti_row, sup_scale=55, parent_scale=89
    )
    assert lam_sp >= 5
    assert inv_sp > 0
    assert triad_sp is False
    assert slp_sp is False
    assert mac_sp is False
    assert quad_sp == "Q4_Inverted_FlatFall"

    # Coherent Macro V-Bottom bypasses (R_mean = 0.93 >= 0.80) -> True
    assert exp141.evaluate_3d_sr_congestion_long_gate(
        lam_sp, inv_sp, triad_sp, slp_sp, mac_sp, r_mean_coherence=0.93
    ) is True

    # True Spaghetti Congestion Trap (R_mean = 0.65 < 0.80) -> False
    assert exp141.evaluate_3d_sr_congestion_long_gate(
        lam_sp, inv_sp, triad_sp, slp_sp, mac_sp, r_mean_coherence=0.65
    ) is False


def test_1m_multiscale_phase_coherence_short_gate():
    """
    Verifies Short 1m Multi-Scale Circular Phase Coherence Gate (R_1m >= 0.75):
    - Passes coherent 1m short waves (R_1m = 0.88) and exact boundary (0.75).
    - Rejects phase-incoherent short waves (R_1m = 0.62) and NaN.
    """
    assert exp141.evaluate_1m_multiscale_phase_coherence_short_gate(0.88) is True
    assert exp141.evaluate_1m_multiscale_phase_coherence_short_gate(0.75) is True
    assert exp141.evaluate_1m_multiscale_phase_coherence_short_gate(0.62) is False
    assert exp141.evaluate_1m_multiscale_phase_coherence_short_gate(float("nan")) is False


def test_metrics_json_consistency():
    """
    Verifies EXP-141 metrics.json schema, additive accounting, zero whitelists,
    20/20 plateau mega-runner preservation, rejected rel_effort cap negative finding,
    and full-mode improvement over EXP-139.
    """
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["experiment_id"] == "EXP-141"
    assert metrics["issue"] == 141
    assert metrics["hardcoded_whitelist_count"] == 0
    assert metrics["return_accounting"] == "additive_sum_pct"

    coh_audit = metrics["circular_phase_coherence_audit"]
    assert coh_audit["2d_plateau_audit"]["grid_cells_total"] == 20
    assert coh_audit["2d_plateau_audit"]["grid_cells_mega_runners_10_of_10"] == 20
    assert coh_audit["rejected_negative_finding_long_rel_effort_cap_1_40"]["mega_runners"] == "8/10"

    prog = metrics["portfolio_ablation_progression"]
    exp139 = prog["EXP139_1h_x_1m_Fractal_Master"]
    exp141_m = prog["EXP141_SR3D_and_Phase_Coherence_Master"]

    assert exp141_m["mega_runners"] == "10/10"
    assert exp141_m["master_std"]["win_rate_pct"] > 50.0
    assert exp141_m["mode_b"]["win_rate_pct"] > 50.0
    assert exp141_m["mode_a"]["max_drawdown_pct"] > -10.0

    for mode in ("master_std", "mode_b", "mode_a"):
        assert exp141_m[mode]["profit_factor"] > exp139[mode]["profit_factor"]
        assert exp141_m[mode]["total_opportunity_net_return_pct"] > exp139[mode]["total_opportunity_net_return_pct"]
        assert exp141_m[mode]["max_drawdown_pct"] >= exp139[mode]["max_drawdown_pct"]
