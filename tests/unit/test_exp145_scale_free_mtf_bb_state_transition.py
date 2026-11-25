"""Unit tests for EXP-145: Scale-Agnostic 11-Scale MTF BB Dynamical State-Transition,
Dynamic Active Scale k*(t), Long-BB WaitGuard Asymmetry & Cascade Exit."""

import importlib.util
import json
import os
import numpy as np
import pandas as pd

EXP145_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/145-scale-free-mtf-bb-state-transition-and-dynamic-scale",
)
RUN_PATH = os.path.join(EXP145_DIR, "run.py")
METRICS_PATH = os.path.join(EXP145_DIR, "metrics.json")

spec = importlib.util.spec_from_file_location("exp145_mod", RUN_PATH)
exp145 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp145)


def _make_synthetic_ohlc_and_bands(n: int = 120, scales=(8, 13, 21), trend: float = 0.0):
    t = np.arange(n, dtype=float)
    close = 30000.0 + trend * t + 120.0 * np.sin(t / 4.0)
    high = close + 45.0
    low = close - 45.0
    atr = np.full(n, 200.0)
    sma_map, up_map, lo_map = {}, {}, {}
    s_close = pd.Series(close)
    for k in scales:
        sma = s_close.rolling(k, min_periods=k).mean().values
        std = s_close.rolling(k, min_periods=k).std().replace(0, 1e-8).values
        sma_map[k] = sma
        up_map[k] = sma + 2.0 * std
        lo_map[k] = sma - 2.0 * std
    return close, high, low, atr, sma_map, up_map, lo_map


def test_zero_whitelists_zero_holdout_leak_and_additive_accounting():
    """Verify zero timestamp whitelists, zero holdout leak flags, and strict additive returns."""
    with open(RUN_PATH, "r", encoding="utf-8") as f:
        src = f.read()
    assert "MEGA_RUNNER_TIMESTAMPS = {" not in src
    assert "include_holdout=True" not in src
    assert "np.prod(" not in src

    rets = [0.20, -0.05, 0.15]
    res = exp145.compute_additive_portfolio_metrics(rets)
    assert res["executed_trades"] == 3
    np.testing.assert_allclose(res["total_opportunity_net_return_pct"], 30.0, atol=1e-6)
    np.testing.assert_allclose(res["profit_factor"], 0.35 / 0.05, atol=1e-6)
    np.testing.assert_allclose(res["max_drawdown_pct"], -5.0, atol=1e-6)


def test_scale_native_lag_and_strict_warmup_guard():
    """Verify scale-native delta_k = max(2, round(0.15 * k)) and state == 0 prior to full window."""
    expected = {8: (2, 1), 13: (2, 1), 21: (3, 1), 55: (8, 4), 144: (22, 11), 987: (148, 74)}
    for k, pair in expected.items():
        assert exp145.scale_native_lag(k) == pair

    scales = (8, 13, 21)
    close, high, low, atr, sma_map, up_map, lo_map = _make_synthetic_ohlc_and_bands(80, scales=scales)
    mat = exp145.compute_scale_native_bb_state_matrix(
        close, high, low, atr, sma_map, up_map, lo_map, scales=scales, enforce_full_warmup=True
    )
    for m, k in enumerate(scales):
        dk, _ = exp145.scale_native_lag(k)
        cutoff = k - 1 + dk
        assert np.all(mat["state"][:cutoff, m] == 0)
        assert not np.any(mat["valid"][:cutoff, m])
        assert np.all(mat["state"][cutoff:, m] != 0)
        assert np.all(mat["valid"][cutoff:, m])


def test_strict_zero_lookahead_perturbation_invariance():
    """Verify mutating future OHLC/bands after bar t0 changes zero outputs at <= t0."""
    scales = (8, 13, 21)
    n = 90
    t0 = 60
    cl1, hi1, lo1, at1, sma1, up1, lo_b1 = _make_synthetic_ohlc_and_bands(n, scales=scales, trend=15.0)

    # Perturb everything strictly after t0
    cl2 = cl1.copy()
    hi2 = hi1.copy()
    lo2 = lo1.copy()
    cl2[t0 + 1 :] -= 4500.0
    hi2[t0 + 1 :] -= 4500.0
    lo2[t0 + 1 :] -= 4600.0
    s_cl2 = pd.Series(cl2)
    sma2, up2, lo_b2 = {}, {}, {}
    for k in scales:
        s_val = s_cl2.rolling(k, min_periods=k).mean().values
        sd_val = s_cl2.rolling(k, min_periods=k).std().replace(0, 1e-8).values
        sma2[k] = s_val
        up2[k] = s_val + 2.0 * sd_val
        lo_b2[k] = s_val - 2.0 * sd_val

    d1 = exp145.derive_dynamic_active_scale_and_range(
        exp145.compute_scale_native_bb_state_matrix(cl1, hi1, lo1, at1, sma1, up1, lo_b1, scales=scales)
    )
    d2 = exp145.derive_dynamic_active_scale_and_range(
        exp145.compute_scale_native_bb_state_matrix(cl2, hi2, lo2, at1, sma2, up2, lo_b2, scales=scales)
    )

    np.testing.assert_array_equal(d1["state"][: t0 + 1], d2["state"][: t0 + 1])
    np.testing.assert_array_equal(d1["k_star"][: t0 + 1], d2["k_star"][: t0 + 1])
    np.testing.assert_array_equal(d1["k_wait_lo"][: t0 + 1], d2["k_wait_lo"][: t0 + 1])
    np.testing.assert_array_equal(d1["k_dn_depth"][: t0 + 1], d2["k_dn_depth"][: t0 + 1])


def test_dynamic_active_scale_and_cross_scale_pullback_waitguard():
    """Verify k+1 UP / k DOWN pullback hook and Long-BB contraction WaitGuard filtering."""
    # Synthetic state dict at bar t=5 for WaitGuard & Pullback Hook check
    scales = (8, 13, 21, 34)
    n = 8
    m_cnt = len(scales)
    m_state = {
        "n": n,
        "scales": scales,
        "scale_to_m": {k: m for m, k in enumerate(scales)},
        "fast_delta_map": {k: exp145.scale_native_lag(k)[1] for k in scales},
        "valid": np.ones((n, m_cnt), dtype=bool),
        "state": np.full((n, m_cnt), 2, dtype=np.int8),
        "phi_mat": np.full((n, m_cnt), 0.30, dtype=float),
        "age_lo": np.full((n, m_cnt), 50.0, dtype=float),
        "age_up": np.full((n, m_cnt), 50.0, dtype=float),
        "u_mat": np.zeros((n, m_cnt), dtype=float),
        "u_lo_mat": np.zeros((n, m_cnt), dtype=float),
        "u_hi_mat": np.zeros((n, m_cnt), dtype=float),
        "du_fast_mat": np.zeros((n, m_cnt), dtype=float),
    }
    t = 5
    # Construct k=21 (idx 2) dipping to lower BB and hooking up while k+1=34 (idx 3) stays UP
    m_state["state"][t - 1, 2] = -2
    m_state["state"][t, 2] = 2
    m_state["u_lo_mat"][t, 2] = -0.85
    m_state["u_mat"][t, 2] = -0.45
    m_state["du_fast_mat"][t, 2] = +0.20
    m_state["age_lo"][t, 2] = 1.0
    m_state["state"][t, 3] = 2
    m_state["phi_mat"][t, 3] = 0.25

    k_pb, k_par = exp145.detect_scale_free_pullback_hook(
        m_state, t, direction="long", u_touch_thr=-0.70, phi_parent_thr=0.10, min_k_star=21
    )
    assert (k_pb, k_par) == (21, 34)

    # WaitGuard blocks premature entry when nearby outer k_wait_lo=34 > 21 is pre-touch (d > 0.50 std)
    assert exp145.evaluate_long_bb_wait_guard(k_pb=21, k_box=8, k_wait_lo=34, d_wait_lo_std=0.80, scales=scales) is False
    # WaitGuard permits entry once outer k_wait_lo touches lower BB (d <= 0.50 std) or no outer wait exists
    assert exp145.evaluate_long_bb_wait_guard(k_pb=21, k_box=8, k_wait_lo=34, d_wait_lo_std=0.30, scales=scales) is True
    assert exp145.evaluate_long_bb_wait_guard(k_pb=21, k_box=0, k_wait_lo=0, d_wait_lo_std=0.0, scales=scales) is True


def test_causal_1m_exact_hour_boundary_cascade_exit_and_ultra_bull_immunity():
    """
    Verify exact cur_hr != prev_hr execution (immune to missing 1m bars),
    Ultra-Bull Mega-Runner immunity, and proportional 40 bps RT split50 accounting.
    """
    # Build 4 hours of 1m timestamps WITH a missing 12m gap in hour 1 (01:10..01:21 missing)
    t_h0 = pd.date_range("2024-03-01 00:00:00+00:00", periods=60, freq="1min")
    t_h1 = pd.date_range("2024-03-01 01:00:00+00:00", periods=60, freq="1min")
    t_h1 = t_h1[(t_h1 < "2024-03-01 01:10:00+00:00") | (t_h1 >= "2024-03-01 01:22:00+00:00")]
    t_h2 = pd.date_range("2024-03-01 02:00:00+00:00", periods=60, freq="1min")
    ts = t_h0.append(t_h1).append(t_h2)

    n = len(ts)
    op = np.full(n, 50500.0)
    hi = np.full(n, 50550.0)
    lo = np.full(n, 50450.0)
    # Run MFE reaches 5.0 ATR during hour 0 (ATR=200 -> 50000 + 1000 = 51000)
    hi[30] = 51000.0
    # At exact 02:00 open bar, set exit open = 50700.0
    idx_0200 = int(np.where(ts == pd.Timestamp("2024-03-01 02:00:00+00:00"))[0][0])
    op[idx_0200] = 50700.0

    # Completed bar 01:00 (read at exact 02:00 boundary) has D=4 cascade breakdown
    hourly_safe = {
        pd.Timestamp("2024-03-01 00:00:00+00:00"): {
            "ca": 55, "k_dn_depth": 2, "k_dn_frontier": 13, "phi_mid": 0.30,
            "state_at_ca": 2, "du_at_ca": 0.05, "is_ultra_bull": False,
        },
        pd.Timestamp("2024-03-01 01:00:00+00:00"): {
            "ca": 55, "k_dn_depth": 4, "k_dn_frontier": 34, "phi_mid": 0.15,
            "state_at_ca": -1, "du_at_ca": -0.05, "is_ultra_bull": False,
        },
    }

    res_full = exp145.simulate_causal_1m_cascade_exit(
        entry_price=50000.0, atr0=200.0, timestamps_1m=ts,
        high_1m=hi, low_1m=lo, open_1m=op,
        hourly_state_by_completed_1h=hourly_safe, mode="full",
    )
    assert res_full["triggered"] is True
    assert res_full["exit_time"] == pd.Timestamp("2024-03-01 02:00:00+00:00")
    assert res_full["completed_1h_bar"] == pd.Timestamp("2024-03-01 01:00:00+00:00")
    np.testing.assert_allclose(res_full["net_return"], (50700.0 - 50000.0) / 50000.0 - 0.0040, atol=1e-9)

    # Split50 preserves proportional 40 bps RT friction
    orig_ret = 0.0020
    res_split = exp145.simulate_causal_1m_cascade_exit(
        entry_price=50000.0, atr0=200.0, timestamps_1m=ts,
        high_1m=hi, low_1m=lo, open_1m=op,
        hourly_state_by_completed_1h=hourly_safe, mode="split50", orig_net_return=orig_ret,
    )
    np.testing.assert_allclose(res_split["net_return"], 0.5 * res_full["net_return"] + 0.5 * orig_ret, atol=1e-9)

    # Ultra-Bull Mega-Runner immunity: setting is_ultra_bull=True at 01:00 suppresses exit
    hourly_ub = dict(hourly_safe)
    hourly_ub[pd.Timestamp("2024-03-01 01:00:00+00:00")] = {
        **hourly_safe[pd.Timestamp("2024-03-01 01:00:00+00:00")],
        "is_ultra_bull": True,
    }
    res_ub = exp145.simulate_causal_1m_cascade_exit(
        entry_price=50000.0, atr0=200.0, timestamps_1m=ts,
        high_1m=hi, low_1m=lo, open_1m=op,
        hourly_state_by_completed_1h=hourly_ub, mode="full", orig_net_return=orig_ret,
    )
    assert res_ub["triggered"] is False
    assert res_ub["net_return"] == orig_ret


def test_metrics_json_spec_eval_contract_and_verified_parity():
    """Verify SPEC-EVAL-001 mandatory keys, exact EXP-143 baseline & EXP-145 Champion parity, and Test 3b refutation."""
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)

    for key in ["total_trades", "friction_cost_applied", "gross_mean_return", "net_mean_return", "win_rate", "profit_factor", "max_drawdown"]:
        assert key in m, f"Missing mandatory key: {key}"
    assert m["total_trades"] == 179
    np.testing.assert_allclose(m["friction_cost_applied"], 0.0040, atol=1e-6)

    base_std = m["baseline_exp143_audited"]["Std"]
    assert base_std["n"] == 179
    np.testing.assert_allclose(base_std["tot"], 741.42316, atol=0.05)
    np.testing.assert_allclose(base_std["mdd"], -9.29765, atol=0.05)
    assert base_std["mg"] == 10

    champ = m["champion_exp145_t1_cascade_exit"]
    assert champ["info"]["n_trig"] == 4
    assert champ["info"]["mg_untouched"] == 10
    np.testing.assert_allclose(champ["Std"]["tot"], 752.07118, atol=0.05)
    np.testing.assert_allclose(champ["ModeB"]["tot"], 604.33676, atol=0.05)
    np.testing.assert_allclose(champ["ModeA"]["tot"], 404.51096, atol=0.05)
    np.testing.assert_allclose(champ["Std"]["mdd"], -9.29765, atol=0.05)

    # All 6 calendar years profitable in all 3 modes
    for mode_k in ("Std", "ModeB", "ModeA"):
        for yr in ("2020", "2021", "2022", "2023", "2024", "2025"):
            assert champ[mode_k]["yearly"][yr]["tot"] > 0.0

    # Verify Test 3b refutation integrity (0/16 positive cells preserved honestly)
    grid_3b = m["part2_test3_negative_ev_short_audit"]["test3b_bear_pullback_short"]["grid_2d"]
    assert len(grid_3b) == 16
    assert all(cell["standalone"]["tot"] < 0.0 for cell in grid_3b)
