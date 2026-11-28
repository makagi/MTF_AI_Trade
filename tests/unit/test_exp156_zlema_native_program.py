"""Unit tests for EXP-156: ZLEMA-Native 4-Phase Reconstruction Program & Purified Track Z-B1."""

import importlib.util
import json
import os
import numpy as np
import yaml

EXP156_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/156-zlema-native-program-and-zb1-purification",
)
RUN_PATH = os.path.join(EXP156_DIR, "run.py")
CONFIG_PATH = os.path.join(EXP156_DIR, "config.yaml")
METRICS_PATH = os.path.join(EXP156_DIR, "metrics.json")
RECORD_PATH = os.path.join(EXP156_DIR, "record.md")

spec = importlib.util.spec_from_file_location("exp156_mod", RUN_PATH)
exp156 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp156)


def _reference_mql5_shift_zlema(close_chron: np.ndarray, period: int) -> np.ndarray:
    rates_total = len(close_chron)
    lag = (period - 1) // 2
    alpha = 2.0 / (period + 1.0)
    buf_ma = close_chron[::-1].copy()
    buf_zl = np.zeros(rates_total, dtype=float)
    for i in range(rates_total - lag - 2, -1, -1):
        buf_zl[i] = alpha * (2.0 * buf_ma[i] - buf_ma[i + lag]) + (1.0 - alpha) * buf_zl[i + 1]
    chron_zl = buf_zl[::-1].copy()
    chron_zl[: min(rates_total, period + lag)] = np.nan
    return chron_zl


def test_mql5_zlema_exact_parity():
    rng = np.random.default_rng(156)
    close = 50000.0 + np.cumsum(rng.normal(20.0, 250.0, size=320))
    for period in (8, 21, 55, 89, 144):
        ref = _reference_mql5_shift_zlema(close, period)
        got = exp156.compute_mql5_zlema(close, period, init_zero=True, enforce_full_warmup=True)
        np.testing.assert_array_equal(np.isnan(ref), np.isnan(got))
        valid = np.isfinite(ref)
        np.testing.assert_allclose(got[valid], ref[valid], rtol=1e-12, atol=1e-10)


def test_pyramid_zero_lookahead_and_dual_sign_flip_symmetry():
    rng = np.random.default_rng(2026)
    n = 1500
    close = 40000.0 + np.cumsum(rng.normal(10.0, 180.0, size=n))
    spread = np.abs(rng.normal(120.0, 40.0, size=n))
    high = close + spread
    low = close - spread
    atr = np.full(n, 220.0, dtype=float)

    inv = exp156.verify_zlema_native_invariants(close, high, low, atr, t_cut=1100)
    assert inv["passed"] is True
    assert inv["max_lookahead_diff"] == 0.0
    assert inv["max_dual_signflip_err"] < 1e-12
    assert inv["max_exp_even_err"] < 1e-12


def test_triplet_six_states_and_warmup():
    """Verify all 6 mutually exclusive adjacent-triplet states on T3=(144,377,987)."""
    n = 120
    zl = np.full((n, len(exp156.SCALES_17)), np.nan, dtype=float)
    vel = np.full((n, len(exp156.SCALES_17)), np.nan, dtype=float)
    atr = np.full(n, 100.0, dtype=float)

    i144, i377, i987 = exp156.S17_TO_I[144], exp156.S17_TO_I[377], exp156.S17_TO_I[987]
    dk2 = max(2, int(round(0.15 * 377)))  # 57
    t0 = 100

    cases = [
        ("PO_UP_EXPAND", (300.0, 200.0, 100.0), (5.0, 3.0, 1.0), (260.0, 190.0, 100.0)),
        ("PO_UP_COMPRESS", (300.0, 200.0, 100.0), (0.0, 3.0, 1.0), (350.0, 200.0, 100.0)),
        ("PO_DN_CASCADE", (100.0, 200.0, 300.0), (-5.0, -3.0, -1.0), (120.0, 200.0, 300.0)),
        ("LEAD_PULLBACK_BULL", (190.0, 200.0, 100.0), (-1.0, 1.0, 2.0), (190.0, 200.0, 100.0)),
        ("LEAD_TURN_BEAR", (210.0, 200.0, 300.0), (2.0, -1.0, -2.0), (180.0, 200.0, 300.0)),
        ("TANGLED_CHOP", (180.0, 190.0, 200.0), (1.0, -1.0, 1.0), (180.0, 190.0, 200.0)),
    ]

    for idx_case, (expected, cur_z, cur_v, prev_z) in enumerate(cases):
        zl[:] = 100.0
        vel[:] = 0.0
        t = t0 + idx_case
        zl[t, i144], zl[t, i377], zl[t, i987] = cur_z
        vel[t, i144], vel[t, i377], vel[t, i987] = cur_v
        zl[t - dk2, i144], zl[t - dk2, i377], zl[t - dk2, i987] = prev_z
        tri = exp156.compute_zlema_triplets(zl, vel, atr)
        assert tri["T3"][0] == "WARMUP"
        assert tri["T3"][t] == expected, f"Expected {expected}, got {tri['T3'][t]}"


def test_preign_or_vs_and_stop_and_zb1_mask():
    or_stop = exp156.compute_preign_stop(10000.0, 200.0, cap_atr=3.25, cap_pct=0.043, logic="OR")
    and_stop = exp156.compute_preign_stop(10000.0, 200.0, cap_atr=3.25, cap_pct=0.043, logic="AND")
    # 3.25 ATR = 9350, 4.3% = 9570 -> OR takes tighter max (9570), AND takes looser min (9350)
    assert or_stop == 9570.0
    assert and_stop == 9350.0

    # When ATR is narrow (e.g. 100 -> 9675), OR takes 9675
    assert exp156.compute_preign_stop(10000.0, 100.0, logic="OR") == 9675.0

    n = 10
    close = np.full(n, 50000.0)
    atr = np.full(n, 200.0)
    zl_mat = np.full((n, len(exp156.SCALES_17)), 49500.0)
    d3h = np.full((n, len(exp156.SCALES_15_INT)), 0.25)
    P = {
        "zl_mat": zl_mat,
        "k_star_z": np.full(n, 55, dtype=int),
        "d3h_phi_bar_mat": d3h,
        "c_phi_38": np.zeros(n),
        "c_exp_38": np.full(n, 0.05),
        "n_ov_exhaust_z": np.zeros(n, dtype=int),
        "z_wait_touch": np.full(n, "NONE", dtype=object),
    }
    T = {
        "T4": np.full(n, "LEAD_PULLBACK_BULL", dtype=object),
        "T3": np.full(n, "LEAD_TURN_BEAR", dtype=object),
    }
    # Index 0 passes; Index 1 blocked by TANGLED_CHOP; Index 2 by C_Exp>0.10;
    # Index 3 by r30>=85; Index 4 by r30<25; Index 5 by N_ov_exhaust>=1; Index 6 by C_Phi>0.12
    T["T3"][1] = "TANGLED_CHOP"
    P["c_exp_38"][2] = 0.15
    r30 = np.full(n, 55.0)
    r30[3] = 85.0
    r30[4] = 24.9
    P["n_ov_exhaust_z"][5] = 1
    P["c_phi_38"][6] = 0.20

    msk = exp156.build_zb1_purified_mask(
        close, atr, P, T, r30, np.full(n, 0.40), np.full(n, 0.5), np.full(n, 0.10)
    )
    assert msk[0] and not any(msk[1:7]) and all(msk[7:])


def test_additive_accounting_spec_eval_001():
    with open(RUN_PATH, "r", encoding="utf-8") as f:
        src = f.read()
    assert "include_holdout=True" not in src
    assert "np.prod(" not in src

    res = exp156.compute_additive_portfolio_metrics([0.204, -0.046, 0.154])
    np.testing.assert_allclose(res["friction_cost_applied"], 0.0040, atol=1e-12)
    np.testing.assert_allclose(res["total_net_return_pct"], 30.0, atol=1e-9)
    np.testing.assert_allclose(res["profit_factor"], 0.35 / 0.05, atol=1e-9)
    np.testing.assert_allclose(res["max_drawdown"], 0.05, atol=1e-9)


def test_exp156_artifacts_and_metrics_integrity():
    assert os.path.exists(RECORD_PATH)
    expected_plots = [
        "exp156_fig1_zlema_native_math_geometry_cheatsheet.png",
        "exp156_fig2_zlema_native_insights_field_guide.png",
        "exp156_fig3_zlema_native_master_summary.png",
        "exp156_fig4_zb1_purification_plateaus.png",
        "exp156_fig5_zb1_dd_anatomy_and_stress.png",
    ]
    for pname in expected_plots:
        assert os.path.exists(os.path.join(EXP156_DIR, "plots", pname)), f"Missing plot: {pname}"

    for rname in ("observations.yaml", "answer_key.json", "gallery_stageA.md", "gallery_stageB.md", "stageA2_higher_order.json"):
        rp = os.path.join(EXP156_DIR, "review", rname)
        assert os.path.exists(rp), f"Missing MOR artifact: {rname}"
        rtxt = open(rp, "r", encoding="utf-8").read()
        assert "C:\\" not in rtxt and "D:\\" not in rtxt, f"Host path leaked in {rname}"

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["issue"] == 156
    assert cfg["parameters"]["hardcoded_whitelist_count"] == 0
    assert cfg["parameters"]["external_data_count"] == 0
    assert cfg["parameters"]["pure_zlema_no_sma_inside_zb1"] is True

    raw_metrics = open(METRICS_PATH, "r", encoding="utf-8").read()
    assert "C:\\" not in raw_metrics and "D:\\" not in raw_metrics, "Host path leaked in metrics.json"
    m = json.loads(raw_metrics)

    assert m["experiment_metadata"]["wl"] == 0
    assert m["experiment_metadata"]["holdout_isolated"] is True
    assert m["experiment_metadata"]["compounding"] is False
    assert abs(m["experiment_metadata"]["friction_cost_applied"] - 0.0040) < 1e-9
    for _, inv_rec in m["experiment_metadata"]["invariants"].items():
        assert inv_rec.get("passed", inv_rec.get("lookahead_passed")) is True

    np.testing.assert_allclose(m["baseline_exp145_champion"]["tot"], 752.07, atol=0.05)
    np.testing.assert_allclose(m["baseline_exp145_champion"]["mdd"], -9.30, atol=0.02)

    l5_05 = next(
        r for r in m["exp156_zb1_purification"]["spec_eval_sizing"]
        if r["sleeve"] == "L5_Pur_d15_Full" and abs(r["weight_z"] - 0.5) < 1e-9
    )
    assert l5_05["checks_passed"] == 10
    np.testing.assert_allclose(l5_05["isolated"]["Std_Isolated"]["tot"], 834.52, atol=0.05)
    np.testing.assert_allclose(l5_05["isolated"]["Std_Isolated"]["mdd"], -9.30, atol=0.02)
