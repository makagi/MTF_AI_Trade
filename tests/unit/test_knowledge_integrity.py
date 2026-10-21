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
