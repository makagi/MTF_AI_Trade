"""Unit tests for EXP-137: Clean Core Plateau Audit (C1) & Role-Weighted Open-Abyss 2D Tensor."""

import importlib.util
import json
import os
import numpy as np

EXP137_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/137-open-abyss-tensor-and-clean-core",
)
RUN_PATH = os.path.join(EXP137_DIR, "run.py")
METRICS_PATH = os.path.join(EXP137_DIR, "metrics.json")

spec = importlib.util.spec_from_file_location("exp137_mod", RUN_PATH)
exp137 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp137)


def test_zero_hardcoded_whitelists_and_additive_metrics_integrity():
    """
    Verifies EXP-137 contains zero hardcoded timestamp whitelists and enforces
    strict additive return accounting (never geometric compounding).
    """
    with open(RUN_PATH, "r", encoding="utf-8") as f:
        source_code = f.read()
    assert "MEGA_RUNNER_TIMESTAMPS = {" not in source_code
    assert "np.prod(" not in source_code

    sample_rets = [0.12, 0.08, -0.04]
    res = exp137.compute_additive_portfolio_metrics(sample_rets)
    assert res["executed_trades"] == 3
    np.testing.assert_allclose(res["total_opportunity_net_return_pct"], 16.0, atol=1e-6)
    np.testing.assert_allclose(res["profit_factor"], 0.20 / 0.04, atol=1e-6)


def test_open_abyss_zero_collapse_vs_restoration():
    """
    Verifies COVID-crash Open-Abyss geometry where price is below ALL 17 SMAs:
    - Original 2D tensor (compute_cumulative_barrier_role_weighted_2d_tensor) collapses to 0.00.
    - Open-Abyss Role-Weighted 2D Tensor (Option 2) restores macro_rr_abyss >= 4.0x
      and d_def_05_17 == 15.0 ATR when overhead SMAs [55..2584] are active bearish resistance.
    """
    p0 = 5500.0
    atr0 = 200.0
    row = {}
    for s in exp137.TREE_SCALES:
        row[f"sma_{s}"] = 6500.0  # All 17 SMAs above price (5.0 ATR overhead)
        row[f"phi_bar_{s}"] = -0.35
        row[f"slope_{s}"] = -0.02
        row[f"bb_upper_{s}"] = 5900.0  # 2.0 ATR above price

    # Original 2D tensor collapses to 0.00
    _, _, orig_macro_rr = exp137.compute_cumulative_barrier_role_weighted_2d_tensor(p0, atr0, row)
    np.testing.assert_allclose(orig_macro_rr, 0.0, atol=1e-12)

    # Option 2 Open-Abyss 2D tensor restores RR >= 4.0x with d_def_05_17 == 15.0 ATR
    _, _, macro_rr_abyss, d_def_05_17 = exp137.compute_open_abyss_role_weighted_2d_tensor(
        p0, atr0, row
    )
    np.testing.assert_allclose(d_def_05_17, 15.0, atol=1e-6)
    assert macro_rr_abyss >= 4.0, f"Expected Open-Abyss RR >= 4.0, got {macro_rr_abyss}"


def test_open_abyss_filters_ultra_macro_defended_floor_traps():
    """
    Verifies automatic filtering of false zero-collapse traps:
    When S55..S2584 are all above price (causing original 2D tensor == 0.00),
    but an active ultra-macro defended floor (S4181, phi_bar_4181 = +0.25) sits only
    1.2 ATR below price, Option 2 detects d_def_05_17 == 1.2 ATR and suppresses macro_rr_abyss < 2.0.
    """
    p0 = 40000.0
    atr0 = 500.0
    row = {}
    for s in exp137.TREE_SCALES:
        row[f"sma_{s}"] = 41500.0  # above price
        row[f"phi_bar_{s}"] = -0.25
        row[f"slope_{s}"] = -0.01
        row[f"bb_upper_{s}"] = 40600.0  # 1.2 ATR overhead micro risk

    # Ultra-macro defended floor S4181 sits only 1.2 ATR below price
    row["sma_4181"] = p0 - 1.2 * atr0
    row["phi_bar_4181"] = 0.25
    row["slope_4181"] = 0.005

    orig_rr_tensor, _, orig_macro_rr = exp137.compute_cumulative_barrier_role_weighted_2d_tensor(
        p0, atr0, row
    )
    assert np.all(orig_rr_tensor[:, 4:13] == 0.0)
    assert orig_macro_rr < 1.0

    _, _, macro_rr_abyss, d_def_05_17 = exp137.compute_open_abyss_role_weighted_2d_tensor(
        p0, atr0, row
    )
    np.testing.assert_allclose(d_def_05_17, 1.2, atol=1e-6)
    assert macro_rr_abyss < 2.0, f"Expected ultra-macro floor trap RR < 2.0, got {macro_rr_abyss}"


def test_s16_scale_relative_downward_bb_short_rescue_gate():
    """
    Verifies S16 short rescue gate:
    - Passes on early 8h downward BB expansion (bb_slope_exp_8 > 0) and non-oversold 21h
      momentum (stoch_z_21 = -0.10), even when macro bb_slope_exp_continuum_L3_L8 < 0.
    - Rejects deeply oversold chasers (stoch_z_21 = -0.55) and eroding ceilings (ceil_dphi3h > 0).
    """
    early_coil_row = {
        "bb_slope_exp_continuum_L3_L8": -0.045,  # macro still coiling
        "bb_slope_exp_8": 0.032,
        "stoch_z_21": -0.10,
        "ceil_dphi3h": -0.012,
        "phi_continuum": -0.18,
    }
    assert exp137.evaluate_scale_relative_downward_bb_short_rescue_gate(
        early_coil_row, macro_rr_abyss=4.46, d_def_05_17=15.0
    ) is True

    # Rejects deeply oversold chaser
    oversold_row = dict(early_coil_row, stoch_z_21=-0.55)
    assert exp137.evaluate_scale_relative_downward_bb_short_rescue_gate(
        oversold_row, macro_rr_abyss=4.46, d_def_05_17=15.0
    ) is False

    # Rejects eroding overhead ceiling
    eroding_ceil_row = dict(early_coil_row, ceil_dphi3h=0.015)
    assert exp137.evaluate_scale_relative_downward_bb_short_rescue_gate(
        eroding_ceil_row, macro_rr_abyss=4.46, d_def_05_17=15.0
    ) is False

    # Rejects non-expanding 8h BB
    contracting_8h_row = dict(early_coil_row, bb_slope_exp_8=-0.010)
    assert exp137.evaluate_scale_relative_downward_bb_short_rescue_gate(
        contracting_8h_row, macro_rr_abyss=4.46, d_def_05_17=15.0
    ) is False

    # Rejects insufficient 17-scale floor clearance (< 4.0 ATR)
    assert exp137.evaluate_scale_relative_downward_bb_short_rescue_gate(
        early_coil_row, macro_rr_abyss=4.46, d_def_05_17=3.2
    ) is False


def test_causal_1m_open_sky_friction_lock_stop():
    """
    Verifies Clean Core H1a causal 1m friction-clear profit lock:
    - Does not trigger below 4.5 ATR running MFE.
    - At >= 4.5 ATR, raises stop to at least entry_price + 0.50 * atr0.
    - Never lowers an existing higher trailing stop.
    """
    entry_price = 50000.0
    atr0 = 1000.0

    # Below 4.5 ATR trigger -> unchanged
    s_below = exp137.compute_causal_1m_open_sky_friction_lock_stop(
        entry_price, atr0, running_mfe_atr=4.49, current_stop_price=49200.0
    )
    np.testing.assert_allclose(s_below, 49200.0, atol=1e-6)

    # At 4.50 ATR trigger -> locks entry + 0.50 * atr0 = 50500.0
    s_trigger = exp137.compute_causal_1m_open_sky_friction_lock_stop(
        entry_price, atr0, running_mfe_atr=4.50, current_stop_price=49800.0
    )
    np.testing.assert_allclose(s_trigger, 50500.0, atol=1e-6)

    # Existing higher structural stop (52000.0) is never lowered
    s_higher = exp137.compute_causal_1m_open_sky_friction_lock_stop(
        entry_price, atr0, running_mfe_atr=10.0, current_stop_price=52000.0
    )
    np.testing.assert_allclose(s_higher, 52000.0, atol=1e-6)


def test_clean_core_base0_wall_guard():
    """
    Verifies Clean Core H2a Base0 counter-trend overhead wall guard:
    Blocks only when phi_continuum < -0.05 AND d_res_def_05 < 2.5 ATR.
    """
    # Blocked: bearish continuum + close overhead resistance wall
    assert exp137.evaluate_clean_core_base0_wall_guard(
        {"phi_continuum": -0.10}, d_res_def_05=1.2
    ) is False

    # Allowed: bearish continuum, but overhead wall is >= 2.5 ATR away
    assert exp137.evaluate_clean_core_base0_wall_guard(
        {"phi_continuum": -0.10}, d_res_def_05=2.68
    ) is True

    # Allowed: close wall, but continuum is >= -0.05 (neutral/bullish)
    assert exp137.evaluate_clean_core_base0_wall_guard(
        {"phi_continuum": 0.02}, d_res_def_05=0.50
    ) is True


def test_metrics_json_consistency():
    """
    Verifies schema, additive accounting, Clean Core C1 improvements,
    rejected overfit audit findings, and Unified Engine B all-6-year profitability.
    """
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["experiment_id"] == "EXP-137"
    assert metrics["hardcoded_whitelist_count"] == 0
    assert metrics["return_accounting"] == "additive_sum_pct"

    audit = metrics["third_party_plateau_audit"]
    assert "bb_L38_ge_neg0018" in audit["rejected_overfit_candidates"]
    assert "M1a_R1s_proj_gt_020" in audit["rejected_overfit_candidates"]

    uni_eb = metrics["open_abyss_tensor_and_s16_short_rescue"]["unified_engine_b"]
    assert uni_eb["n"] == 46
    assert uni_eb["pf"] > 2.5
    assert uni_eb["tot_pct"] > 60.0
    for yr, yr_ret in uni_eb["yearly_pct"].items():
        assert yr_ret > 0.0, f"Expected Unified Engine B positive in {yr}, got {yr_ret}"

    pc = metrics["portfolio_comparison"]
    c1 = pc["Clean_Core_C1"]
    srd = pc["Scale_Rel_D_EXP135_Baseline"]
    assert c1["master_std"]["total_opportunity_net_return_pct"] > srd["master_std"]["total_opportunity_net_return_pct"]
    assert c1["master_std"]["profit_factor"] > srd["master_std"]["profit_factor"]
    assert c1["mode_b"]["total_opportunity_net_return_pct"] > srd["mode_b"]["total_opportunity_net_return_pct"]
    assert c1["mode_a"]["total_opportunity_net_return_pct"] > srd["mode_a"]["total_opportunity_net_return_pct"]

    c1_s16 = pc["C1_plus_S16_Full"]
    assert c1_s16["master_std"]["total_opportunity_net_return_pct"] > c1["master_std"]["total_opportunity_net_return_pct"]
    assert c1_s16["mode_b"]["total_opportunity_net_return_pct"] > c1["mode_b"]["total_opportunity_net_return_pct"]
