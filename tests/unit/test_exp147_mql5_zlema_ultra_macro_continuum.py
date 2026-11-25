"""Unit tests for EXP-147: Exact MQL5 Zero-Lag EMA (BufferEMAZL) 17-Scale Ultra-Macro
Continuum, 4-Way Regime Classification, Lookahead Audits & Defense of EXP-145 Champion."""

import importlib.util
import json
import os
import numpy as np
import yaml

EXP147_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../03_KNOWLEDGE/experiments/147-mql5-zlema-17scale-ultra-macro-continuum",
)
RUN_PATH = os.path.join(EXP147_DIR, "run.py")
CONFIG_PATH = os.path.join(EXP147_DIR, "config.yaml")
METRICS_PATH = os.path.join(EXP147_DIR, "metrics.json")
PLOT_PATH = os.path.join(EXP147_DIR, "plots", "exp147_fig1_zlema_ultra_macro_continuum.png")

spec = importlib.util.spec_from_file_location("exp147_mod", RUN_PATH)
exp147 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp147)


def _reference_mql5_shift_zlema(close_chron: np.ndarray, period: int) -> np.ndarray:
    """
    Verbatim MQL5 OnCalculate shift-indexed BufferEMAZL (index 0 = newest, N-1 = oldest)
    converted cleanly from array initialization for ground-truth comparison.
    """
    rates_total = len(close_chron)
    lag = (period - 1) // 2
    alpha = 2.0 / (period + 1.0)
    buf_ma = close_chron[::-1].copy()
    buf_zl = np.zeros(rates_total, dtype=float)
    limit = rates_total - lag - 2
    for i in range(limit, -1, -1):
        buf_zl[i] = alpha * (2.0 * buf_ma[i] - buf_ma[i + lag]) + (1.0 - alpha) * buf_zl[i + 1]
    chron_zl = buf_zl[::-1].copy()
    chron_zl[: min(rates_total, period + lag)] = np.nan
    return chron_zl


def test_mql5_zlema_exact_recursion_and_zero_lookahead():
    """Verify exact equivalence to MQL5 BufferEMAZL shift loop & zero-lookahead invariance."""
    rng = np.random.default_rng(147)
    close = 50000.0 + np.cumsum(rng.normal(25.0, 300.0, size=320))
    for period in (5, 21, 55, 89):
        ref = _reference_mql5_shift_zlema(close, period)
        got = exp147.compute_mql5_zlema(close, period, init_zero=True, enforce_full_warmup=True)
        np.testing.assert_array_equal(np.isnan(ref), np.isnan(got))
        valid = np.isfinite(ref)
        np.testing.assert_allclose(got[valid], ref[valid], rtol=1e-12, atol=1e-10)
        assert exp147.verify_zlema_zero_lookahead(close, period=period, t_cut=240) == 0.0


def test_mql5_zlema_strict_full_window_warmup():
    """Verify strict full-window warmup mask excludes indices < period + lag."""
    close = np.linspace(10000.0, 20000.0, 250)
    for period in (8, 13, 21, 55, 89):
        lag, _, warmup_end = exp147.zlema_params(period)
        assert lag == (period - 1) // 2
        z_masked = exp147.compute_mql5_zlema(close, period, enforce_full_warmup=True)
        assert np.all(np.isnan(z_masked[:warmup_end]))
        assert np.all(np.isfinite(z_masked[warmup_end:]))


def test_mql5_zlema_init_zero_vs_init_close_convergence():
    """Verify init_zero=True and init_zero=False converge closely after >10*period bars."""
    n = 600
    t = np.arange(n, dtype=float)
    close = 60000.0 + 1500.0 * np.sin(t / 15.0) + 12.0 * t
    period = 21
    z0 = exp147.compute_mql5_zlema(close, period, init_zero=True, enforce_full_warmup=True)
    zc = exp147.compute_mql5_zlema(close, period, init_zero=False, enforce_full_warmup=True)
    rel_end_diff = abs(z0[-1] - zc[-1]) / close[-1]
    assert rel_end_diff < 1e-6


def test_zlema_ultra_macro_features_and_regime_causality():
    """Verify causal feature calculation, 4-way classification & future-perturbation invariance."""
    # Direct unit test of mutually-exclusive 4-way classifier
    labels = exp147.classify_zlema_ultra_macro_regime(
        submerge_frac=[np.nan, 0.92, 0.90, 0.00, 0.10],
        anchor_wk_slp_pct=[np.nan, -1.55, -4.13, 2.25, 3.50],
        outer_max_abs_wk_slp_pct=[np.nan, 1.60, 4.13, 2.25, 3.50],
        close_above_anchor=[False, False, False, True, True],
        macro_floor_hits_24h=[0, 0, 1, 5, 0],
    )
    assert list(labels) == [
        "WARMUP",
        "Z_SUBMERGED_PARALLEL",
        "Z_BEAR_CASCADE",
        "Z_FLOOR_SPRING",
        "Z_BULL_ABOVE",
    ]

    # Causal invariance of compute_zlema_ultra_macro_features
    rng = np.random.default_rng(99)
    n = 420
    close = 80000.0 + np.cumsum(rng.normal(5.0, 200.0, size=n))
    low = close - 120.0
    high = close + 120.0
    t_cut = 350

    scales = (8, 13, 21, 34, 55, 89, 144)
    f1 = exp147.compute_zlema_ultra_macro_features(
        close, low, high=high, scales=scales, anchor_scale=144
    )
    close2 = close.copy()
    low2 = low.copy()
    high2 = high.copy()
    close2[t_cut + 1 :] *= 1.8
    low2[t_cut + 1 :] *= 1.7
    high2[t_cut + 1 :] *= 1.9
    f2 = exp147.compute_zlema_ultra_macro_features(
        close2, low2, high=high2, scales=scales, anchor_scale=144
    )

    for key in (
        "k_anchor",
        "close_above_anchor",
        "macro_floor_hits_24h",
        "submerge_frac",
        "anchor_wk_slp_pct",
    ):
        a1 = f1[key][: t_cut + 1]
        a2 = f2[key][: t_cut + 1]
        if np.issubdtype(a1.dtype, np.floating):
            np.testing.assert_allclose(a1, a2, rtol=0.0, atol=0.0, equal_nan=True)
        else:
            np.testing.assert_array_equal(a1, a2)


def test_veto_and_floor_spring_gates():
    """Verify boundary behavior of Submerged-Parallel veto & Floor-Spring gate helpers."""
    assert exp147.evaluate_zlema_submerged_veto(1.0, -1.55) is True
    assert exp147.evaluate_zlema_submerged_veto(0.917, 1.82, wk_max_pct=0.50) is False
    assert exp147.evaluate_zlema_submerged_veto(np.nan, 0.0) is False

    assert exp147.evaluate_zlema_floor_spring_gate(5, 0.0, 2.25) is True
    assert exp147.evaluate_zlema_floor_spring_gate(1, 0.0, 2.25, min_floors=2) is False
    assert exp147.evaluate_zlema_floor_spring_gate(4, 0.75, 2.25, subm_cap=0.50) is False


def test_additive_portfolio_accounting_spec_eval_001():
    """Verify strictly additive SPEC-EVAL-001 accounting (zero compounding, no np.prod)."""
    with open(RUN_PATH, "r", encoding="utf-8") as f:
        src = f.read()
    assert "include_holdout=True" not in src
    assert "np.prod(" not in src

    res = exp147.compute_additive_portfolio_metrics([0.204, -0.046, 0.154])
    # net = [0.20, -0.05, 0.15] -> sum = 0.30 (+30.0%)
    assert res["total_trades"] == 3
    np.testing.assert_allclose(res["friction_cost_applied"], 0.0040, atol=1e-12)
    np.testing.assert_allclose(res["total_net_return_pct"], 30.0, atol=1e-9)
    np.testing.assert_allclose(res["profit_factor"], 0.35 / 0.05, atol=1e-9)
    np.testing.assert_allclose(res["max_drawdown"], 0.05, atol=1e-9)
    compounded_differs = (1.20 * 0.95 * 1.15 - 1.0) * 100.0
    assert abs(res["total_net_return_pct"] - compounded_differs) > 1.0


def test_exp147_metrics_json_and_config_integrity():
    """Verify EXP-147 metrics.json, config.yaml, and figure artifacts adhere to SPEC-EVAL-001."""
    assert os.path.exists(PLOT_PATH), f"Missing plot: {PLOT_PATH}"

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["issue"] == 147
    assert cfg["parameters"]["hardcoded_whitelist_count"] == 0
    assert cfg["parameters"]["external_data_count"] == 0
    assert cfg["parameters"]["friction_bps"] == 0.0040

    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        raw_text = f.read()
    assert "C:\\" not in raw_text, "Host-specific absolute path leaked into metrics.json"
    m = json.loads(raw_text)

    assert m["total_trades"] == 179
    assert abs(m["friction_cost_applied"] - 0.004) < 1e-9
    assert m["experiment_metadata"]["wl"] == 0
    assert m["experiment_metadata"]["holdout_isolated"] is True
    assert m["experiment_metadata"]["pure_ohlc_only"] is True
    assert m["experiment_metadata"]["compounding"] is False
    assert m["experiment_metadata"]["zlema_lookahead_audit"]["passed_zero_lookahead"] is True
    assert m["experiment_metadata"]["zlema_lookahead_audit"]["max_lookahead_diff"] == 0.0
    assert m["part4_hyp147_3_t1_and_shorts"]["short_n_positive_cells"] == 0
    np.testing.assert_allclose(m["baseline_exp145_champion"]["Std"]["tot"], 752.0711843718212, atol=1e-4)
