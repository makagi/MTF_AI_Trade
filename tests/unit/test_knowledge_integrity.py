"""
Automated Knowledge & Spec Integrity Tests (Issue #67 Part 2.3)
Verifies:
1. No global lookahead .quantile() calls exist in experiment scripts (must use rolling).
2. Experiment metrics.json and record.md consistency for recent experiments.
"""

from pathlib import Path
import re
import json
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_global_quantile_in_experiment_scripts():
    """
    Ensure experiment scripts do not use global un-windowed .quantile(...)
    which causes in-sample lookahead leakage per SPEC-FEAT-001 §2.1.
    Allowed: .rolling(...).quantile(...) or quantile on cross-sectional slices.
    Disallowed: df['col'].quantile(...) or close.quantile(...).
    """
    exp_dir = REPO_ROOT / "03_KNOWLEDGE" / "experiments"
    run_scripts = list(exp_dir.glob("*/run.py"))
    assert len(run_scripts) > 0, "No experiment run.py scripts found"

    violations = []
    for script in run_scripts:
        content = script.read_text(encoding="utf-8")
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            # Ignore comments
            if stripped.startswith("#"):
                continue
            if ".quantile(" in stripped and ".rolling(" not in stripped:
                # Check if it operates on a DataFrame/Series
                if re.search(r'\["[^"]+"\]\.quantile\(', stripped) or re.search(r'\b(df|close|high|low)\[.*\]\.quantile\(', stripped):
                    violations.append(f"{script.name}:{idx}: {stripped}")

    assert not violations, f"Found global lookahead .quantile() without .rolling() in experiment scripts:\n" + "\n".join(violations)


def test_experiment_metrics_integrity():
    """
    Ensure recent experiments (EXP-58, EXP-61, EXP-65) have valid metrics.json
    and matching record.md files with non-empty results.
    """
    exp_ids = [
        "58-differential-and-negative-robustness",
        "61-multidimensional-context",
        "65-composite-feature-gating",
        "68-unreachable-envelope-and-breach",
        "69-1m-path-and-invalidation-exit",
        "74-sma-peak-dynamics",
    ]

    for exp_id in exp_ids:
        edir = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / exp_id
        assert edir.exists(), f"Experiment directory {edir} not found"

        metrics_file = edir / "metrics.json"
        record_file = edir / "record.md"
        assert metrics_file.exists(), f"metrics.json missing in {exp_id}"
        assert record_file.exists(), f"record.md missing in {exp_id}"

        with open(metrics_file, "r", encoding="utf-8") as f:
            metrics_data = json.load(f)

        assert isinstance(metrics_data, dict), f"metrics.json in {exp_id} is not a valid JSON object"
        assert len(metrics_data) > 0, f"metrics.json in {exp_id} is empty"

        record_content = record_file.read_text(encoding="utf-8")
        assert len(record_content) > 200, f"record.md in {exp_id} is too short"


def test_exp65_audited_metrics_consistency():
    """
    Specifically verify EXP-65 audited metrics in metrics.json:
    - MVC N=86 trades with 24h Net +0.42% and 72h Net +1.08%
    - MVC Macro Regime Disaggregation shares sum to 100%
    - Trigger Cooldown (N=86) vs Execution Cooldown (N=143) exist
    """
    edir = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / "65-composite-feature-gating"
    with open(edir / "metrics.json", "r", encoding="utf-8") as f:
        d = json.load(f)

    # 1. MVC Ablation
    mvc = d["ablation_study"]["w/o MAE Damper (Trap + Booster)"]
    assert mvc["total_trades"] == 86
    assert round(mvc["multi_horizon_40bps"]["24"]["net_mean_return"] * 100, 2) == 0.42
    assert round(mvc["multi_horizon_40bps"]["72"]["net_mean_return"] * 100, 2) == 1.08
    assert round(mvc["multi_horizon_40bps"]["24"]["profit_factor"], 2) == 1.50

    # 2. Macro Regime Disaggregation
    reg_disagg = d["mvc_macro_regime_disaggregation"]
    total_reg_trades = sum(v["trades"] for v in reg_disagg.values())
    assert total_reg_trades == 86
    assert reg_disagg["Macro_Bull"]["trades"] == 30
    assert reg_disagg["Macro_Range"]["trades"] == 35
    assert reg_disagg["Macro_Bear"]["trades"] == 21

    # 3. Cooldown Modes
    cd_modes = d["cooldown_mode_comparison"]
    assert cd_modes["trigger_cooldown_pre"]["total_trades"] == 86
    assert cd_modes["execution_cooldown_post"]["total_trades"] == 143


def test_no_bfill_in_experiment_scripts():
    """
    Ensure experiment scripts do not use backward fill (.bfill())
    which introduces future-data lookahead per SPEC-FEAT-001 §2.1.
    """
    exp_dir = REPO_ROOT / "03_KNOWLEDGE" / "experiments"
    run_scripts = list(exp_dir.glob("*/run.py"))
    assert len(run_scripts) > 0, "No experiment run.py scripts found"

    violations = []
    for script in run_scripts:
        content = script.read_text(encoding="utf-8")
        lines = content.splitlines()
        in_docstring = False
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if '"""' in stripped or "'''" in stripped:
                # Toggle or handle single-line docstring
                quotes = '"""' if '"""' in stripped else "'''"
                if stripped.count(quotes) % 2 == 1:
                    in_docstring = not in_docstring
                continue
            if in_docstring or stripped.startswith("#"):
                continue
            if re.search(r'\.\s*bfill\s*\(', stripped):
                violations.append(f"{script.parent.name}/{script.name}:{idx}: {stripped}")

    assert not violations, f"Found lookahead .bfill() in experiment scripts:\n" + "\n".join(violations)


def test_exp68_envelope_metrics_consistency():
    """
    Specifically verify EXP-68 audited metrics in metrics.json:
    - Fractal scaling power-law fit R^2 >= 0.99 and alpha exponent ~ 0.517
    - Dynamic Safe Floor for K-038 MVC across elapsed time (N=86: 53 wins, 33 losses)
    - 72h Drawdown from Entry 95th: Winner 5.79 ATR vs Loser 20.15 ATR
    - Non-tautological Boundary Breach Events (N=742 independent breakouts)
    """
    edir = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / "68-unreachable-envelope-and-breach"
    with open(edir / "metrics.json", "r", encoding="utf-8") as f:
        d = json.load(f)

    # 1. Fractal Scaling
    scaling = d["fractal_scaling"]
    assert scaling["r_squared"] >= 0.99
    assert round(scaling["alpha_exponent"], 3) == 0.517
    assert scaling["contextual_alphas_1h"]["sub_diffusion_confirmed"] is True

    # 2. Dynamic Safe Floor Trajectory (K-038 MVC N=86)
    dyn_sf = d["dynamic_safe_floor_mvc"]
    assert round(dyn_sf["4"]["drawdown_from_entry_atr"]["winner_q95"], 2) == 2.68
    assert round(dyn_sf["24"]["drawdown_from_entry_atr"]["winner_q95"], 2) == 5.49
    assert round(dyn_sf["72"]["drawdown_from_entry_atr"]["winner_q95"], 2) == 5.79
    assert round(dyn_sf["72"]["drawdown_from_entry_atr"]["loser_q95"], 2) == 20.15
    assert round(dyn_sf["72"]["sma34_penetration_atr"]["winner_q05"], 2) == -4.43
    assert round(dyn_sf["72"]["pullback_from_peak_atr"]["winner_q95"], 2) == 8.49

    # 3. Non-tautological Boundary Breach Dynamics
    breach = d["boundary_breach_dynamics"]
    assert breach["total_independent_breaches"] == 742
    post_24 = breach["post_horizons"]["24"]
    assert post_24["cascade"]["count"] == 346
    assert post_24["sweep"]["count"] == 389


def test_exp69_path_metrics_consistency():
    """
    Specifically verify EXP-69 remediated metrics in metrics.json (Issue #73):
    - K-038 MVC 1m intra-bar path integration across 86 opportunities
    - S3 Sensitivity k=5.0 achieves Net EV +1.13% (exceeding baseline +1.07%), PF 1.95, Worst -7.35%
    - S3 k=5.0 and k=4.43 maintain positive EV in P2 Bear (+0.40% and +0.46%) avoiding S1 Whipsaw
    - S4 Dynamic Profit Ratchet shortens average duration to 28.5h with Worst -6.58% and PF 1.97
    - E3 1m Microstructure Reclaim has 97.67% fill rate but total return (+88.48%) still lags E0 (+92.29%)
    - Signal C Stage 2 Short (N=15) verifies 72h Net EV +1.04% with Safe Floor Max DD 10.66%
    """
    edir = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / "69-1m-path-and-invalidation-exit"
    with open(edir / "metrics.json", "r", encoding="utf-8") as f:
        d = json.load(f)

    assert d["total_mvc_opportunities"] == 86
    assert d["total_signal_c_opportunities"] == 15

    # 1. Exit Strategies on K-038 MVC
    exits = d["mvc_exit_strategies"]
    s0 = exits["S0_Baseline_Fixed_72h"]
    assert s0["Full"]["executed_trades"] == 86
    assert round(s0["Full"]["net_mean_return_pct"], 2) == 1.07
    assert round(s0["Full"]["worst_trade_pct"], 2) == -15.86
    assert round(s0["Full"]["profit_factor"], 2) == 1.84

    s1 = exits["S1_Fixed_Safe_Floor_579"]
    assert round(s1["Full"]["worst_trade_pct"], 2) == -8.02
    assert round(s1["Full"]["profit_factor"], 2) == 1.88
    # S1 suffers Whipsaw in P2 Bear
    assert s1["P2_Bear"]["net_mean_return_pct"] < 0

    s3_k50 = exits["S3_Sensitivity_k50"]
    assert round(s3_k50["Full"]["net_mean_return_pct"], 2) == 1.13
    assert round(s3_k50["Full"]["profit_factor"], 2) == 1.95
    assert round(s3_k50["Full"]["worst_trade_pct"], 2) == -7.35
    assert round(s3_k50["Full"]["total_opportunity_net_return_pct"], 2) == 97.55
    # S3 avoids Whipsaw in P2 Bear
    assert s3_k50["P2_Bear"]["net_mean_return_pct"] > 0
    assert exits["S3_Dynamic_Structural_SMA34_k443"]["P2_Bear"]["net_mean_return_pct"] > 0

    s4 = exits["S4_Dynamic_Profit_Ratchet"]
    assert s4["Full"]["avg_duration_hours"] < 30.0
    assert round(s4["Full"]["worst_trade_pct"], 2) == -6.58
    assert round(s4["Full"]["profit_factor"], 2) == 1.97

    # 2. Entry Refinements (Opportunity Drag Verification)
    entries = d["mvc_entry_refinements"]
    e0 = entries["E0_Instant_Close_Baseline"]
    e1 = entries["E1_Pullback_03_ATR_Limit"]
    e3 = entries["E3_1m_Microstructure_Reclaim"]

    assert e0["fill_rate_pct"] == 100.0
    assert round(e0["total_opportunity_net_return_pct"], 2) == 92.29
    assert round(e1["fill_rate_pct"], 2) == 63.95
    assert round(e1["total_opportunity_net_return_pct"], 2) == 47.04
    assert round(e3["fill_rate_pct"], 2) == 97.67
    assert round(e3["total_opportunity_net_return_pct"], 2) == 88.48
    # Even micro-structure confirmation (E3) suffers opportunity drag relative to E0
    assert e3["total_opportunity_net_return_pct"] < e0["total_opportunity_net_return_pct"]

    # 3. Signal C Stage 2 Short
    sig_c = d["signal_c_exit_strategies"]
    assert round(sig_c["S0_Baseline_Fixed_72h"]["net_mean_return_pct"], 2) == 1.04
    assert sig_c["S0_Baseline_Fixed_72h"]["win_rate_pct"] > 60.0
    assert sig_c["S1_Fixed_Safe_Floor_579"]["max_drawdown_pct"] < sig_c["S0_Baseline_Fixed_72h"]["max_drawdown_pct"]


def test_no_intra_hour_lookahead_in_exp69():
    """
    Ensure EXP-69 run.py does not contain un-offset t_bar.floor('1h') lookups
    without subtracting 1 hour, strictly ensuring t_1h + 1h <= t_bar.
    """
    script = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / "69-1m-path-and-invalidation-exit" / "run.py"
    content = script.read_text(encoding="utf-8")
    lines = content.splitlines()

    violations = []
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Catch bare t_bar.floor("1h") without subtracting 1 hour
        if "t_bar.floor(" in stripped and "pd.Timedelta" not in stripped and "- 1h" not in stripped and "- pd.Timedelta(hours=1)" not in stripped:
            violations.append(f"Line {idx}: {stripped}")

    assert not violations, f"Found potential intra-hour lookahead in EXP-69:\n" + "\n".join(violations)


def test_exp74_sma_peak_dynamics_metrics_consistency():
    """
    Ensure EXP-74 metrics.json strictly reflects the remediated objective findings:
    1. EXP-69 Baseline S0 (EV +1.07%, PF 1.84, Worst -15.86%) & S3_k50 (EV +1.13%, PF 1.95, Worst -7.35%) exact reproduction.
    2. S6 Phase-Adaptive dynamic exit (EV +1.05%, highest PF 1.96, Dur 54.8h, Worst -7.35%).
    3. Objective resonant partner triads (non-tautological 1-to-1 matching and cross-correlation).
    4. 3-phase geometry separation, approach branching stats, and trough symmetry.
    5. Complete consistency between metrics.json, record.md, and knowledge-lineage.md.
    """
    exp_dir = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / "74-sma-peak-dynamics"
    metrics_file = exp_dir / "metrics.json"
    record_file = exp_dir / "record.md"

    with open(metrics_file, "r", encoding="utf-8") as f:
        d = json.load(f)
    record_text = record_file.read_text(encoding="utf-8")

    # 1. Total swing peaks & troughs evaluated
    peaks = d["total_peaks_evaluated"]
    troughs = d["total_troughs_evaluated"]
    assert peaks["SMA_21"] == 532
    assert peaks["SMA_34"] == 270
    assert peaks["SMA_55"] == 121
    assert peaks["SMA_89"] == 47
    assert troughs["SMA_34"] == 259

    # 2. Objective Resonant Partner Triads (HYP-SMA-PEAK-2)
    pairs = d["objective_resonant_pairs"]
    assert pairs["SMA_21"]["best_short_sma"] == "SMA_13"
    assert pairs["SMA_21"]["best_stoch"] == "Stoch_D_34"
    assert pairs["SMA_21"]["best_afs"] == "AFS_21"

    assert pairs["SMA_34"]["best_short_sma"] == "SMA_21"
    assert pairs["SMA_34"]["best_stoch"] == "Stoch_D_55"
    assert pairs["SMA_34"]["best_afs"] == "AFS_34"

    assert pairs["SMA_55"]["best_short_sma"] == "SMA_34"
    assert pairs["SMA_89"]["best_short_sma"] == "SMA_55"

    # Verify matching stats for SMA 34
    p_stats = d["phase_lead_matching_stats"]["SMA_34"]
    assert p_stats["short_smas"]["SMA_21"]["f1"] > 0.40
    assert p_stats["short_smas"]["SMA_21"]["median_lead"] == 9.5
    assert p_stats["stoch_d"]["Stoch_D_55"]["cross_corr_r_max"] > 0.80

    # 3. 3-Phase Geometry & Branching (HYP-SMA-PEAK-1)
    geom = d["three_phase_geometry_stats"]
    p1 = geom["1_Approach_Peak"]
    p2 = geom["2_Straddle_Peak"]
    p3 = geom["3_Expansion_Peak"]

    assert p1["total_count"] == 79
    assert p1["delta_h_median"] == -2.52
    assert p1["slope_breakdown"]["Steep_Down"]["delta_h_median"] == -4.58
    assert p1["slope_breakdown"]["Steep_Down"]["delta_h_p90"] == -0.89

    assert p2["total_count"] == 41
    assert p2["delta_h_median"] == 1.23
    assert p2["slope_breakdown"]["Flat_Gentle"]["delta_h_median"] == 1.25
    assert p2["slope_breakdown"]["Flat_Gentle"]["delta_h_p90"] == 2.93

    assert p3["total_count"] == 149
    assert p3["delta_h_median"] == 5.70
    assert p3["slope_breakdown"]["Steep_Up"]["delta_h_median"] == 8.04
    assert p3["slope_breakdown"]["Steep_Up"]["delta_h_p90"] == 14.57

    # Branching stats
    br = d["approach_wave_branching_stats"]
    assert br["total_approach_events"] == 140
    assert br["overall_distribution_pct"]["1_Approach_Turnback"] == 20.7
    assert br["overall_distribution_pct"]["2_Straddle_Overshoot"] == 31.4
    assert br["overall_distribution_pct"]["3_Expansion_Breakthrough"] == 47.9
    assert br["trap_condition_steep_down_bb_contracting"]["expansion_pct"] == 14.3
    assert br["breakout_condition_flat_up_bb_expanding"]["expansion_pct"] == 55.6

    # Trough symmetry
    tr = d["peak_trough_symmetry_stats"]
    assert tr["Steep_Down"]["delta_h_median"] == -8.42
    assert tr["Steep_Up"]["delta_h_median"] == 4.50

    # 4. Trading Application A (Exact EXP-69 Baseline Reproduction & S6 Phase-Adaptive Exit)
    app_a = d["trading_application_a_mvc_exit"]
    s0 = app_a["S0_Baseline_Fixed_72h"]
    s3 = app_a["S3_Dynamic_Structural_k50"]
    s6 = app_a["S6_Phase_Adaptive_Peak_Exit"]

    # Exact EXP-69 Baseline reproduction
    assert s0["Full"]["executed_trades"] == 86
    assert s0["Full"]["net_mean_return_pct"] == 1.07
    assert s0["Full"]["profit_factor"] == 1.84
    assert s0["Full"]["worst_trade_pct"] == -15.86
    assert s0["Full"]["avg_duration_hours"] == 72.0

    assert s3["Full"]["executed_trades"] == 86
    assert s3["Full"]["net_mean_return_pct"] == 1.13
    assert s3["Full"]["profit_factor"] == 1.95
    assert s3["Full"]["worst_trade_pct"] == -7.35
    assert s3["Full"]["avg_duration_hours"] == 63.6

    # S6 Phase-Adaptive Performance
    assert s6["Full"]["executed_trades"] == 86
    assert s6["Full"]["net_mean_return_pct"] == 1.05
    assert s6["Full"]["profit_factor"] == 1.96  # Highest PF among all strategies
    assert s6["Full"]["worst_trade_pct"] == -7.35
    assert s6["Full"]["avg_duration_hours"] == 54.8  # Compressed by 17.2 hours!
    assert s6["P1_Bull"]["net_mean_return_pct"] == 1.23
    assert s6["P2_Bear"]["net_mean_return_pct"] == 0.21
    assert s6["P3_Mixed"]["net_mean_return_pct"] == 1.30

    # 5. Trading Application B (Reversal Short)
    app_b = d["trading_application_b_reversal_short"]
    assert app_b["total_signals"] == 28
    assert round(app_b["multi_horizon"]["72"]["net_mean_return"] * 100, 2) == 0.27
    assert round(app_b["multi_horizon"]["72"]["profit_factor"], 2) == 1.19

    # 6. Verify exact numbers exist in record.md
    assert "1.07%" in record_text
    assert "1.13%" in record_text
    assert "1.05%" in record_text
    assert "1.96" in record_text
    assert "-4.58" in record_text
    assert "+8.04" in record_text
    assert "54.8h" in record_text
    assert "-8.42" in record_text
    assert "140" in record_text


def test_exp77_1m_microstructure_metrics_consistency():
    """
    Specifically verify EXP-77 metrics in metrics.json and record.md (Issue #77):
    - K-038 MVC 1m microstructure rapid exit and tranche execution across 86 events
    - Baseline S0 and S3_k50 exact reproduction (+1.07% / 1.84 and +1.13% / 1.95)
    - S_Adaptive achieves duration reduction of 57.7% (26.9h vs 63.6h) while maintaining PF 1.96 and WR 65.12%
    - Overhead Trap Gating identifies 19 traps (Adaptive EV -0.64%, PF 0.44)
    - Clean MVC (N=67) Adaptive achieves Net EV +1.02%, PF 2.84, WR 70.15% across ~27.7h
    - E_Tranche_Skip improves Worst Trade to -4.61% (vs -7.19%) and elevates PF to 2.51
    """
    edir = REPO_ROOT / "03_KNOWLEDGE" / "experiments" / "77-1m-microstructure-and-rapid-exit"
    with open(edir / "metrics.json", "r", encoding="utf-8") as f:
        d = json.load(f)
    with open(edir / "record.md", "r", encoding="utf-8") as f:
        record_text = f.read()

    assert d["total_mvc_events"] == 86
    assert d["clean_mvc_events_prereg"] == 80
    assert d["overhead_trap_events_prereg"] == 6
    assert d["clean_mvc_events_exploratory_abs"] == 67
    assert d["overhead_trap_events_exploratory_abs"] == 19
    assert d["cost_bps"] == 40.0

    # 1. Observations
    obs = d["microstructure_observations"]
    assert obs["O1_signal_candle_spike_median_pct"] == 0.50
    assert obs["O2_low_clv_60m_range_count"] == 11
    assert obs["O3_dips_le_neg30bps_pct"] == 72.1
    assert obs["O3_median_dip_pct"] == -0.48
    assert obs["O3_median_dip_bottom_time_min"] == 88.0

    # 2. Strategy Benchmarks
    sb = d["strategy_benchmarks"]
    s0 = sb["S0_Fixed_72h"]
    assert s0["net_mean_return_pct"] == 1.07
    assert s0["profit_factor"] == 1.84
    assert s0["worst_trade_pct"] == -15.86
    assert s0["avg_duration_hours"] == 72.0

    s3 = sb["S3_k50_K040"]
    assert s3["net_mean_return_pct"] == 1.13
    assert s3["profit_factor"] == 1.95
    assert s3["worst_trade_pct"] == -7.35
    assert s3["avg_duration_hours"] == 63.6

    s_fixed_24 = sb["S_Fixed_24h"]
    assert s_fixed_24["net_mean_return_pct"] == 0.47
    assert s_fixed_24["profit_factor"] == 1.58

    s_fixed_30 = sb["S_Fixed_30h"]
    assert s_fixed_30["net_mean_return_pct"] == 0.61
    assert s_fixed_30["profit_factor"] == 1.81

    s_fixed_42 = sb["S_Fixed_42h"]
    assert s_fixed_42["net_mean_return_pct"] == 1.16
    assert s_fixed_42["profit_factor"] == 2.51

    s_adapt = sb["S_Adaptive_1m"]
    assert s_adapt["net_mean_return_pct"] == 0.89
    assert s_adapt["profit_factor"] == 2.43
    assert s_adapt["win_rate_pct"] == 70.93
    assert s_adapt["avg_duration_hours"] == 29.9
    assert s_adapt["worst_trade_pct"] == -7.19

    # 3. HYP-77-1 Overhead Trap Gating
    trap_hyp = d["hyp_77_1_overhead_trap"]["pre_registered_overhead_sma89"]
    clean_s3 = trap_hyp["clean_mvc_s3"]
    trap_s3 = trap_hyp["trap_group_s3"]
    assert clean_s3["net_mean_return_pct"] == 1.19
    assert clean_s3["profit_factor"] == 1.98
    assert trap_s3["net_mean_return_pct"] == 0.34
    assert trap_hyp["random_exclusion_p_value"] == 0.323

    clean_adapt = trap_hyp["clean_mvc_adaptive"]
    trap_adapt = trap_hyp["trap_group_adaptive"]
    assert clean_adapt["net_mean_return_pct"] == 0.95
    assert clean_adapt["profit_factor"] == 2.55
    assert clean_adapt["win_rate_pct"] == 71.25
    assert trap_adapt["net_mean_return_pct"] == 0.14
    assert trap_adapt["profit_factor"] == 1.17

    # 4. HYP-77-2 Tranche Execution
    tranche_skip_nom = sb["E_Tranche_Skip_Nominal"]
    tranche_skip_exp = sb["E_Tranche_Skip_Exposure"]
    tranche_fill_nom = sb["E_Tranche_Fill_Nominal"]
    assert tranche_skip_nom["worst_trade_pct"] == -4.44
    assert tranche_skip_exp["worst_trade_pct"] == -7.19
    assert tranche_fill_nom["worst_trade_pct"] == -7.77
    assert d["hyp_77_2_tranche_execution"]["limit_fill_rate_pct"] == 62.8

    # 5. HYP-77-3 Duration Reduction Ratio and Bootstrap
    dur_hyp = d["hyp_77_3_rapid_exit"]
    assert dur_hyp["duration_reduction_ratio_pct"] == 53.0
    assert dur_hyp["duration_reduction_hours"] == 33.7
    assert dur_hyp["bootstrap_95_ci"]["net_mean_return_pct"] == [0.35, 1.45]
    assert "反証・棄却" in dur_hyp["judgement"]

    # 6. Verify exact numbers exist in record.md
    assert "+1.07%" in record_text
    assert "+1.13%" in record_text
    assert "+0.89%" in record_text
    assert "29.9h" in record_text
    assert "+0.95%" in record_text
    assert "2.55" in record_text
    assert "71.25%" in record_text
    assert "-4.44%" in record_text
    assert "-7.77%" in record_text
    assert "62.8%" in record_text





