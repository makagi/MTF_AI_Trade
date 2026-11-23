"""Unit tests for EXP-143: Forensically Audited Pre-Ignition Floor Guard, Wave-Distinct Pyramiding,
Scale-Free 1m Continuum, Weak-Macro Coherence & Opposite-Slope Intersection Ceiling Apex."""

import importlib.util
import json
import os
import numpy as np
import pandas as pd
import pytest

EXP143_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/143-preignition-floor-wave-pyramiding-and-ceiling-apex",
)
RUN_PATH = os.path.join(EXP143_DIR, "run.py")
METRICS_PATH = os.path.join(EXP143_DIR, "metrics.json")

spec = importlib.util.spec_from_file_location("exp143_mod", RUN_PATH)
exp143 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp143)


def test_zero_hardcoded_whitelists_and_additive_metrics_integrity():
    """
    Verifies EXP-143 contains zero hardcoded timestamp whitelists and enforces
    strict additive return accounting (never geometric compounding).
    """
    with open(RUN_PATH, "r", encoding="utf-8") as f:
        source_code = f.read()
    assert "MEGA_RUNNER_TIMESTAMPS = {" not in source_code
    assert "np.prod(" not in source_code

    sample_rets = [0.25, 0.10, -0.05]
    res = exp143.compute_additive_portfolio_metrics(sample_rets)
    assert res["executed_trades"] == 3
    np.testing.assert_allclose(res["total_opportunity_net_return_pct"], 30.0, atol=1e-6)
    np.testing.assert_allclose(res["profit_factor"], 0.35 / 0.05, atol=1e-6)


def test_opposite_slope_overhead_ceiling_apex_and_false_static_guard():
    """
    Verifies kinematic overhead opposite-slope intersection (tau*, P*, H*) and
    False-Static Headroom Roof Guard:
    - Reproduces descending roof collision apex P* < SMA_b(t0) (e.g. 2022-09-14 regime).
    - Blocks False-Static Headroom traps (d_res_def_05 >= 2.0 ATR with tau* <= 36h, H* < 2.0 ATR).
    - Ignores below-price golden crosses (L_high <= P0 + 0.5 ATR) so runners are never misclassified.
    """
    p0 = 20000.0
    atr0 = 300.0
    # 2022-09-14 style descending roof: static SMA_b is +2.5 ATR overhead, falling at -0.10 ATR/h,
    # while short SMA_a is -0.2 ATR below price, rising at +0.08 ATR/h.
    l_low = p0 - 0.2 * atr0
    v_low = 0.08
    l_high = p0 + 2.5 * atr0  # static headroom looks wide (> 2.0 ATR)
    v_high = -0.10

    valid, tau_star, p_star, h_star = exp143.compute_opposite_slope_overhead_ceiling_apex(
        p0=p0,
        atr0=atr0,
        l_low=l_low,
        v_low_per_hour=v_low,
        l_high=l_high,
        v_high_per_hour=v_high,
    )
    assert valid is True
    assert 0.0 < tau_star <= 36.0
    np.testing.assert_allclose(tau_star, 2.7 / 0.18, atol=1e-9)  # 15.0 hours
    assert p_star < l_high  # descending roof apex strictly below static SMA_b(t0)
    assert h_star < 2.0     # effective headroom compressed to +1.00 ATR

    # False-Static Headroom Trap -> blocked (False)
    assert exp143.evaluate_false_static_headroom_roof_guard(
        d_res_def_05=2.5,
        is_valid_collision=valid,
        tau_star_hours=tau_star,
        h_star_atr=h_star,
    ) is False

    # Spacious apex headroom (H* >= 2.0) or distant collision (tau* > 36h) -> allowed (True)
    assert exp143.evaluate_false_static_headroom_roof_guard(
        d_res_def_05=2.5,
        is_valid_collision=True,
        tau_star_hours=tau_star,
        h_star_atr=2.2,
    ) is True
    assert exp143.evaluate_false_static_headroom_roof_guard(
        d_res_def_05=2.5,
        is_valid_collision=True,
        tau_star_hours=40.0,
        h_star_atr=1.2,
    ) is True

    # Below-price golden cross (L_high <= P0) must NEVER be classified as an overhead ceiling
    gc_valid, gc_tau, _, _ = exp143.compute_opposite_slope_overhead_ceiling_apex(
        p0=p0,
        atr0=atr0,
        l_low=p0 - 0.8 * atr0,
        v_low_per_hour=0.06,
        l_high=p0 - 0.1 * atr0,
        v_high_per_hour=-0.04,
    )
    assert gc_valid is False
    assert np.isnan(gc_tau)
    # Even if L_high is slightly above p0 (+0.3 ATR <= 0.5 ATR threshold), strictly ignored
    low_ovh_valid, _, _, _ = exp143.compute_opposite_slope_overhead_ceiling_apex(
        p0=p0,
        atr0=atr0,
        l_low=p0 - 0.5 * atr0,
        v_low_per_hour=0.06,
        l_high=p0 + 0.3 * atr0,
        v_high_per_hour=-0.04,
    )
    assert low_ovh_valid is False


def test_causal_1m_preignition_floor_guard():
    """
    Verifies Track 1 T1[AND] causal 1m pre-ignition floor guard:
    - Triggers when running_MFE < 1.5 ATR and BOTH 3.25 ATR and 4.3% are breached.
    - Uses conservative min(open_k, stop_px) gap-down fill.
    - Requires BOTH conditions under T1[AND] (does not trigger if only one is breached).
    - Disarms permanently once running_MFE >= 1.5 ATR has been reached.
    """
    p0 = 40000.0
    atr0 = 400.0  # 3.25 ATR = 1300 (3.25%), 4.3% = 1720 (4.30%) -> AND stop_px = 38280.0
    stop_expected = p0 * (1.0 - 0.043)

    # 1. Pre-ignition breach of BOTH 3.25 ATR and 4.3% (normal fill at stop_px)
    hi = [40100.0, 40200.0, 39500.0, 39000.0]
    lo = [39900.0, 39600.0, 38600.0, 38200.0]  # bar 2 breaches 3.25 ATR only; bar 3 breaches 4.3% too
    op = [40000.0, 40050.0, 39400.0, 38800.0]
    res = exp143.simulate_causal_1m_preignition_floor_guard(p0, atr0, hi, lo, op)
    assert res["triggered"] is True
    assert res["exit_bar_index"] == 3
    np.testing.assert_allclose(res["stop_price"], stop_expected, atol=1e-6)
    np.testing.assert_allclose(res["exit_price"], stop_expected, atol=1e-6)
    np.testing.assert_allclose(res["net_return"], -0.043 - 0.0040, atol=1e-9)

    # 2. Gap-down fill below stop_px -> fills conservatively at open_k
    op_gap = [40000.0, 40050.0, 39400.0, 38000.0]
    res_gap = exp143.simulate_causal_1m_preignition_floor_guard(p0, atr0, hi, lo, op_gap)
    assert res_gap["triggered"] is True
    assert res_gap["exit_bar_index"] == 3
    np.testing.assert_allclose(res_gap["exit_price"], 38000.0, atol=1e-6)
    np.testing.assert_allclose(res_gap["net_return"], (38000.0 - p0) / p0 - 0.0040, atol=1e-9)

    # 3. Single condition only (3.25 ATR breached, 4.3% NOT breached) -> does NOT trigger under AND
    lo_atr_only = [39900.0, 39600.0, 38600.0, 38500.0]  # 38500 > 38280 (4.3% level)
    res_atr_only = exp143.simulate_causal_1m_preignition_floor_guard(p0, atr0, hi, lo_atr_only, op)
    assert res_atr_only["triggered"] is False

    # 4. Once running_MFE >= 1.5 ATR (40600+) is reached, subsequent deep dip NEVER triggers Track 1
    hi_ig = [40100.0, 40650.0, 39500.0, 38000.0]  # bar 1 hits +1.625 ATR -> ignited
    lo_ig = [39900.0, 40000.0, 38800.0, 37500.0]
    res_ig = exp143.simulate_causal_1m_preignition_floor_guard(p0, atr0, hi_ig, lo_ig, op)
    assert res_ig["triggered"] is False
    assert res_ig["ignited"] is True


def test_causal_wave_distinct_pyramiding_guard():
    """
    Verifies Track 2 Causal Wave-Distinct Pyramiding Guard:
    - Blocks same-wave un-ignited overlaps (dt = 3.9h, causal running MFE = 0.20R).
    - Passes true multi-wave pyramiding (causal running MFE = 2.5R or dt = 30h).
    - Respects propagated early exit_time (positions exited <= candidate_entry_time are ignored).
    """
    t0_open = pd.Timestamp("2024-01-07 16:00:00", tz="UTC")
    t_cand_close = t0_open + pd.Timedelta(hours=3, minutes=54)

    # Same-wave un-ignited overlap (dt = 3.9h, causal MFE = 0.20 ATR) -> blocked
    open_unignited = [{
        "entry_time": t0_open,
        "exit_time": t0_open + pd.Timedelta(hours=12),
        "side": "long",
        "running_mfe_at_candidate_entry": 0.20,
    }]
    assert exp143.evaluate_causal_wave_distinct_pyramiding_guard(
        t_cand_close, open_unignited, candidate_side="long"
    ) is False

    # True ignited pyramiding (causal MFE = 2.50 ATR >= 2.0 ATR, even with dt = 3.9h) -> allowed
    open_ignited = [{
        "entry_time": t0_open,
        "exit_time": t0_open + pd.Timedelta(hours=48),
        "side": "long",
        "running_mfe_at_candidate_entry": 2.50,
    }]
    assert exp143.evaluate_causal_wave_distinct_pyramiding_guard(
        t_cand_close, open_ignited, candidate_side="long"
    ) is True

    # Temporally separated new wave (dt = 30h >= 24h, even if MFE < 2.0 ATR) -> allowed
    t_cand_far = t0_open + pd.Timedelta(hours=30)
    assert exp143.evaluate_causal_wave_distinct_pyramiding_guard(
        t_cand_far, open_unignited, candidate_side="long"
    ) is True

    # Propagated early Track 1 exit before candidate entry -> slot is free -> allowed
    open_early_exited = [{
        "entry_time": t0_open,
        "exit_time": t0_open + pd.Timedelta(hours=3),  # exited before t_cand_close (3.9h)
        "side": "long",
        "running_mfe_at_candidate_entry": 0.10,
    }]
    assert exp143.evaluate_causal_wave_distinct_pyramiding_guard(
        t_cand_close, open_early_exited, candidate_side="long"
    ) is True


def test_scale_free_1m_continuum_and_weak_macro_coherence_gate():
    """
    Verifies Forensically Audited Track 3a (natural 0.0 / 2.0 boundaries) and Track 3b
    Weak-Macro Coherence Gate:
    - Long: blocks exhausted SF-1m (triad > 2.5 & bb_exp <= 0.0), but allows expanding bb_exp = +0.02.
    - Long: blocks weak-macro incoherence (phi_continuum < 0.20 & R_1h_local < 0.70), allows coherent R_1h >= 0.70.
    - Short: allows natural rho_pk <= 2.0 (e.g. 1.77 winner), blocks rho_pk > 2.0; never blocked by weak-macro Long rule.
    """
    # Healthy Long -> True
    assert exp143.evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
        direction="long",
        sf1m_triad_mean_norm=1.8,
        sf1m_bb_exp_conv=-0.05,
        sf1m_rho_pk_mean=1.0,
        phi_continuum=0.45,
        r_1h_local=0.85,
    ) is True

    # Track 3a Long exhausted (triad > 2.5 and natural bb_exp <= 0.0) -> False
    assert exp143.evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
        direction="long",
        sf1m_triad_mean_norm=2.8,
        sf1m_bb_exp_conv=0.0,
        sf1m_rho_pk_mean=1.0,
        phi_continuum=0.45,
        r_1h_local=0.85,
    ) is False

    # Natural boundary restoration: bb_exp = +0.02 > 0.0 must PASS (previously over-tightened bug)
    assert exp143.evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
        direction="long",
        sf1m_triad_mean_norm=2.8,
        sf1m_bb_exp_conv=0.02,
        sf1m_rho_pk_mean=1.0,
        phi_continuum=0.45,
        r_1h_local=0.85,
    ) is True

    # Track 3b Long Weak-Macro Incoherent (phi < 0.20 & R_1h < 0.70) -> False
    assert exp143.evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
        direction="long",
        sf1m_triad_mean_norm=1.2,
        sf1m_bb_exp_conv=0.05,
        sf1m_rho_pk_mean=1.0,
        phi_continuum=0.12,
        r_1h_local=0.62,
    ) is False

    # Weak-Macro but high 1h coherence (R_1h = 0.75 >= 0.70) -> True
    assert exp143.evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
        direction="long",
        sf1m_triad_mean_norm=1.2,
        sf1m_bb_exp_conv=0.05,
        sf1m_rho_pk_mean=1.0,
        phi_continuum=0.12,
        r_1h_local=0.75,
    ) is True

    # Short natural boundary restoration: rho_pk = 1.77 (<= 2.0) must PASS even when phi < 0.20
    assert exp143.evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
        direction="short",
        sf1m_triad_mean_norm=0.0,
        sf1m_bb_exp_conv=0.0,
        sf1m_rho_pk_mean=1.77,
        phi_continuum=-0.40,
        r_1h_local=0.55,
    ) is True

    # Short climax resonance drift (rho_pk = 2.25 > 2.0) -> False
    assert exp143.evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
        direction="short",
        sf1m_triad_mean_norm=0.0,
        sf1m_bb_exp_conv=0.0,
        sf1m_rho_pk_mean=2.25,
        phi_continuum=-0.40,
        r_1h_local=0.85,
    ) is False

    with pytest.raises(ValueError):
        exp143.evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
            direction="flat",
            sf1m_triad_mean_norm=1.0,
            sf1m_bb_exp_conv=0.0,
            sf1m_rho_pk_mean=1.0,
            phi_continuum=0.0,
            r_1h_local=0.8,
        )


def test_metrics_json_consistency():
    """
    Verifies EXP-143 metrics.json schema, additive accounting, zero whitelists/external data,
    all-6-year positive returns across all 3 modes, single-digit MaxDD (-9.30%), and
    strict superiority over EXP-141 across all 3 modes.
    """
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics["experiment_id"] == "EXP-143"
    assert metrics["issue"] == 143
    assert metrics["hardcoded_whitelist_count"] == 0
    assert metrics["external_data_count"] == 0
    assert metrics["return_accounting"] == "additive_sum_pct"
    assert metrics["all_6_years_positive"] == {"Std": True, "ModeB": True, "ModeA": True}

    forensic = metrics["forensic_audit_checks"]
    assert forensic["check1_track2_causal_vs_lookahead"]["seq_vs_simul_mode_b_identical"] is True
    assert forensic["check2_track1_preignition_floor"]["and_same_bar_hits"] == 0
    assert forensic["check2_track1_preignition_floor"]["and_2d_plateau_mg10_0loss_cells"] == 21
    assert forensic["check3_track3a_sf1m_natural_restoration"]["chart2_parity_2025_pct"] > 0.0

    prog = metrics["portfolio_ablation_progression"]
    exp141_m = prog["EXP141_SR3D_and_Phase_Coherence_Master"]
    exp143_m = prog["EXP143_Audited_Master"]

    assert exp143_m["mega_runners"] == "10/10"
    for mode in ("master_std", "mode_b", "mode_a"):
        assert exp143_m[mode]["win_rate_pct"] > 50.0
        assert exp143_m[mode]["max_drawdown_pct"] > -10.0
        assert exp143_m[mode]["profit_factor"] > exp141_m[mode]["profit_factor"]
        assert exp143_m[mode]["total_opportunity_net_return_pct"] > exp141_m[mode]["total_opportunity_net_return_pct"]
        assert exp143_m[mode]["max_drawdown_pct"] > exp141_m[mode]["max_drawdown_pct"]

    yearly = metrics["yearly_performance_exp143_audited"]
    for mode in ("master_std", "mode_b", "mode_a"):
        for yr in ("2020", "2021", "2022", "2023", "2024", "2025"):
            assert yearly[mode][yr]["total_opportunity_net_return_pct"] > 0.0
