"""Unit tests for EXP-162: Bear-Market Asymmetry, Extended Pyramids, ZL-BB, Z-AFS/Stoch_d & Track Z-B1 Defense."""

import importlib.util
import json
import os
import numpy as np
import yaml

EXP162_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/162-bear-asymmetry-extended-pyramids-and-zb1-defense",
)
RUN_PATH = os.path.join(EXP162_DIR, "run.py")
CONFIG_PATH = os.path.join(EXP162_DIR, "config.yaml")
METRICS_PATH = os.path.join(EXP162_DIR, "metrics.json")
RECORD_PATH = os.path.join(EXP162_DIR, "record.md")

spec = importlib.util.spec_from_file_location("exp162_mod", RUN_PATH)
exp162 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp162)


def test_zlema_nan_safe_leading_nan_and_affine_invariance():
    rng = np.random.default_rng(160)
    n = 600
    k_pos = np.full(n, np.nan, dtype=float)
    k_pos[80:] = np.clip(50.0 + np.cumsum(rng.normal(0.0, 6.0, size=n - 80)), 0.0, 100.0)
    k_neg = 100.0 - k_pos

    for period in (21, 55, 144):
        z_pos = exp162.zlema_nan_safe(k_pos, period, warmup_cap=144)
        z_neg = exp162.zlema_nan_safe(k_neg, period, warmup_cap=144)
        assert np.all(np.isnan(z_pos[: 80 + (period - 1) // 2 + 1 + min(period, 144)]))
        np.testing.assert_array_equal(np.isnan(z_pos), np.isnan(z_neg))
        fin = np.isfinite(z_pos)
        assert fin.any()
        np.testing.assert_allclose(z_pos[fin] + z_neg[fin], 100.0, rtol=1e-12, atol=1e-12)


def test_exp162_extended_pyramids_zlbb_and_zafs_invariants():
    rng = np.random.default_rng(162)
    n = 1500
    close = 42000.0 + np.cumsum(rng.normal(8.0, 210.0, size=n))
    spread = np.abs(rng.normal(135.0, 45.0, size=n))
    high = close + spread
    low = close - spread
    atr = np.full(n, 240.0, dtype=float)

    inv = exp162.verify_exp162_invariants(close, high, low, atr, t_cut=1100)
    assert inv["passed"] is True
    assert inv["max_lookahead_diff"] == 0.0
    assert inv["max_dual_signflip_err"] < 1e-12

    P = exp162.compute_base_zlema_pyramid(close, high, low, atr)
    anc_s, wk_slp = exp162.compute_bear_anchor_slope(P["zl_mat"])
    assert len(anc_s) == n and len(wk_slp) == n
    assert np.all(anc_s[740:910] == 377) and np.isfinite(wk_slp[740:910]).all()
    assert np.all(anc_s[915:1080] == 610) and np.isnan(wk_slp[915:1080]).all()
    assert np.all(anc_s[1085:1475] == 610) and np.isfinite(wk_slp[1085:1475]).all()


def test_zb1_bear_defense_gate_nan_safe_and_boundaries():
    t5 = np.array([
        "LEAD_TURN_BEAR",   # 0: wk=-2.0 -> block
        "LEAD_TURN_BEAR",   # 1: wk=-1.49 -> allow (thr -1.50)
        "LEAD_TURN_BEAR",   # 2: wk=NaN -> allow (NaN-safe)
        "TANGLED_CHOP",     # 3: wk=-3.0 -> allow (non-LEAD_TURN_BEAR)
        "PO_UP_EXPAND",     # 4: wk=-2.5, zlexp=0.15 -> block by zlexp_max
        "PO_UP_COMPRESS",   # 5: wk=1.0, zlexp=NaN -> block by zlexp_max NaN
    ], dtype=object)
    wk = np.array([-2.0, -1.49, np.nan, -3.0, -2.5, 1.0], dtype=float)
    zlexp = np.array([0.0, 0.05, 0.05, 0.05, 0.15, np.nan], dtype=float)

    g_t5 = exp162.compute_zb1_bear_defense_gate(t5, wk, wk_thr=-1.50, zlexp_max=None)
    assert list(g_t5) == [False, True, True, True, True, True]

    g_dual = exp162.compute_zb1_bear_defense_gate(t5, wk, c_zl_exp_38=zlexp, wk_thr=-1.50, zlexp_max=0.10)
    assert list(g_dual) == [False, True, True, True, False, False]


def test_exp162_artifacts_and_metrics_integrity():
    assert os.path.exists(RECORD_PATH)
    for rel_src in (RUN_PATH, CONFIG_PATH, METRICS_PATH, RECORD_PATH):
        txt = open(rel_src, "r", encoding="utf-8").read()
        assert "C:\\" not in txt and "D:\\" not in txt, f"Host path leaked in {rel_src}"

    run_src = open(RUN_PATH, "r", encoding="utf-8").read()
    assert "include_holdout=True" not in run_src
    assert "np.prod(" not in run_src

    expected_plots = [
        "obs_exp158_bear_regime_forensics.png",
        "obs_exp159_extended_pyramid_2d_surfaces.png",
        "obs_exp159_s2_s3_mfe_mae_and_trajectory_anatomy.png",
        "obs_exp160_zlbb_and_zafs_physics.png",
        "obs_exp160_multichannel_2d_surfaces.png",
        "obs_exp161_asymmetric_short_execution_matrix.png",
        "obs_exp162_zb1_bear_defense_and_plateau.png",
    ]
    for pname in expected_plots:
        assert os.path.exists(os.path.join(EXP162_DIR, "plots", pname)), f"Missing plot: {pname}"

    cfg = yaml.safe_load(open(CONFIG_PATH, "r", encoding="utf-8"))
    assert cfg["issue"] == 162
    assert cfg["related_issues"] == [158, 159, 160, 161, 162]
    assert cfg["parameters"]["hardcoded_whitelist_count"] == 0

    m = json.loads(open(METRICS_PATH, "r", encoding="utf-8").read())
    assert m["experiment_metadata"]["wl"] == 0
    assert m["experiment_metadata"]["holdout_isolated"] is True
    assert m["experiment_metadata"]["compounding"] is False
    np.testing.assert_allclose(m["baseline_exp145_champion"]["tot"], 752.07, atol=0.05)
    np.testing.assert_allclose(m["baseline_exp145_champion"]["mdd"], -9.30, atol=0.02)

    # Verify EXP-161 honest standalone result (0/50 Era2 PF > 1.0) & A4 CF-SA PF 1.12
    for pm in ("GlobalBD_24h", "Pocket_24h"):
        for _, styles in m["exp161_asymmetric_short_audit"]["results_40bps"][pm].items():
            for _, ms in styles.items():
                assert ms["e2_pf"] <= 1.0
    a4_cf = m["exp161_asymmetric_short_audit"]["integration_audit_vs_champ"]["A4_M4_BandShear__AX1_WideRoom_72hHarvest"]["cand_conflict_free_sa"]
    np.testing.assert_allclose(a4_cf["pf"], 1.12, atol=0.02)

    # Verify EXP-162 D3_L5_DualDef @0.75x Inc>6h 10/10 PASS and 4x4 plateau 0.75x=4/16
    d3 = next(v for v in m["exp162_zb1_bear_defense"]["variants"] if v["name"] == "D3_L5_DualDef")
    assert d3["weights_inc6h"]["0.75"]["checks_passed"] == 10
    np.testing.assert_allclose(d3["weights_inc6h"]["0.75"]["std_iso"]["tot"], 838.83, atol=0.05)
    np.testing.assert_allclose(d3["weights_inc6h"]["0.75"]["std_iso"]["mdd"], -9.30, atol=0.02)
    assert m["exp162_zb1_bear_defense"]["plateau_pass_counts"]["0.75x"] == 4
