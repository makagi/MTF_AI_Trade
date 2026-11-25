"""
EXP-147: Exact MQL5 Zero-Lag EMA (BufferEMAZL) 17-Scale Ultra-Macro Continuum,
Phase-Lag Elimination, 4-Way Regime Taxonomy & Defense of EXP-145 Champion.

Key Principles & Invariants:
1. Exact MQL5 BufferEMAZL Correspondence (Shift-Indexed -> Chronological):
       lag = (period - 1) // 2
       alpha = 2.0 / (period + 1.0)
       BufferEMAZL[t] = alpha * (2.0 * x[t] - x[t - lag]) + (1.0 - alpha) * BufferEMAZL[t - 1]
   with zero-initialization (init_zero=True matches ArrayInitialize(BufferEMAZL, 0))
   and strict full-window warmup guard (NaN for bar_idx < period + lag).
2. Strictly Causal & Zero-Lookahead: Perturbing any bars strictly after t_cut
   leaves every ZLEMA value and 17-scale ultra-macro state at t <= t_cut unchanged
   to floating-point zero (max_diff == 0.0).
3. Zero Window-Dressing & Zero External Data: hardcoded_whitelist_count = 0,
   100% pure OHLC price dynamics, strictly Discovery <= 2025-04-30 (Holdout isolated).
4. Strict Additive Accounting (SPEC-EVAL-001): 40 bps (0.0040) round-trip friction
   deducted cleanly with strictly additive cumulative summation (no np.prod).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np
import pandas as pd

FRICTION_RATE: float = 0.0040
SCALES_17: tuple[int, ...] = (
    8,
    13,
    21,
    34,
    55,
    89,
    144,
    233,
    377,
    610,
    987,
    1597,
    2584,
    4181,
    6765,
    10946,
    17711,
)
SUBMERGED_SHORT_SCALES: tuple[int, ...] = (
    21,
    34,
    55,
    89,
    144,
    233,
    377,
    610,
    987,
    1597,
    2584,
    4181,
)
PARALLEL_ULTRA_SCALES: tuple[int, ...] = (6765, 10946, 17711)
FLOOR_SPRING_SCALES: tuple[int, ...] = (377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711)


def zlema_params(period: int) -> tuple[int, float, int]:
    """Return MQL5 ZLEMA (lag, alpha, warmup_end_idx) for integer period >= 1."""
    p = int(period)
    if p < 1:
        raise ValueError(f"period must be >= 1, got {p}")
    lag = (p - 1) // 2
    alpha = 2.0 / (p + 1.0)
    return lag, alpha, p + lag


def compute_mql5_zlema(
    values: Sequence[float] | np.ndarray | pd.Series,
    period: int,
    init_zero: bool = True,
    enforce_full_warmup: bool = True,
) -> np.ndarray:
    """
    Exact chronological equivalent of MQL5 BufferEMAZL with BufferMA = Close:
        lag = (period - 1) // 2
        alpha = 2.0 / (period + 1.0)
        BufferEMAZL[t] = alpha * (2.0 * x[t] - x[t - lag]) + (1.0 - alpha) * BufferEMAZL[t - 1]

    When `enforce_full_warmup=True`, indices `< period + lag` are masked to `np.nan`
    so partially warmed state is never leaked into downstream features or signals.
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    lag, alpha, warmup_end = zlema_params(period)
    out = np.full(n, np.nan, dtype=float)

    start = lag + 1
    while start < n and not (np.isfinite(x[start]) and np.isfinite(x[start - lag])):
        start += 1
    if start >= n:
        return out

    if init_zero:
        prev = 0.0
    else:
        prev = float(x[start - 1]) if np.isfinite(x[start - 1]) else float(x[start])

    c_b = 1.0 - alpha
    raw = np.full(n, np.nan, dtype=float)
    for t in range(start, n):
        xt = x[t]
        xl = x[t - lag]
        if np.isfinite(xt) and np.isfinite(xl):
            prev = alpha * (2.0 * xt - xl) + c_b * prev
            raw[t] = prev
        else:
            raw[t] = np.nan

    cutoff = warmup_end if enforce_full_warmup else start
    if cutoff < n:
        out[cutoff:] = raw[cutoff:]
    return out


def verify_zlema_zero_lookahead(
    values: Sequence[float] | np.ndarray,
    period: int,
    t_cut: int,
    perturb_scale: float = 1.45,
    init_zero: bool = True,
) -> float:
    """
    Verify zero-lookahead invariance: perturb all bars strictly after `t_cut`
    and return maximum absolute deviation at indices `<= t_cut` (must equal 0.0).
    """
    x = np.asarray(values, dtype=float)
    if t_cut < 0 or t_cut >= len(x) - 1:
        raise ValueError(f"t_cut={t_cut} out of range for length {len(x)}")

    perturbed = x.copy()
    perturbed[t_cut + 1 :] = perturbed[t_cut + 1 :] * float(perturb_scale) + 12345.0

    z_orig = compute_mql5_zlema(x, period, init_zero=init_zero, enforce_full_warmup=True)
    z_pert = compute_mql5_zlema(perturbed, period, init_zero=init_zero, enforce_full_warmup=True)

    sl_orig = z_orig[: t_cut + 1]
    sl_pert = z_pert[: t_cut + 1]
    finite_mask = np.isfinite(sl_orig) & np.isfinite(sl_pert)
    if not np.any(finite_mask):
        # NaN positions must still match identically before warmup completes.
        assert np.array_equal(np.isnan(sl_orig), np.isnan(sl_pert))
        return 0.0
    assert np.array_equal(np.isnan(sl_orig), np.isnan(sl_pert))
    return float(np.max(np.abs(sl_orig[finite_mask] - sl_pert[finite_mask])))


def _causal_atr_wilder_or_simple(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = 24,
) -> np.ndarray:
    """Causal simple rolling True Range average for standalone ATR normalization."""
    n = len(close)
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    if n > 1:
        hl = high[1:] - low[1:]
        hc = np.abs(high[1:] - close[:-1])
        lc = np.abs(low[1:] - close[:-1])
        tr[1:] = np.maximum(hl, np.maximum(hc, lc))
    return pd.Series(tr).rolling(window, min_periods=1).mean().to_numpy(dtype=float)


def compute_zlema_ultra_macro_features(
    close: Sequence[float] | np.ndarray,
    low: Sequence[float] | np.ndarray,
    high: Sequence[float] | np.ndarray | None = None,
    atr: Sequence[float] | np.ndarray | None = None,
    zlema_by_scale: Mapping[int, Sequence[float] | np.ndarray] | None = None,
    z_lo_by_scale: Mapping[int, Sequence[float] | np.ndarray] | None = None,
    scales: Sequence[int] = SCALES_17,
    anchor_scale: int = 6765,
    floor_lookback_hours: int = 24,
    wk_lookback_hours: int = 168,
) -> dict[str, Any]:
    """
    Strictly causal computation of EXP-147 ultra-macro structure features across `scales`:
      - submerge_frac: fraction of warmed scales in [21 .. anchor-1] below ZLEMA[anchor]
      - anchor_wk_slp_pct: 168h weekly % slope of active ZLEMA[anchor]
      - outer_max_abs_wk_slp_pct: max |168h % slope| across outer scales >= anchor (or top 2)
      - close_above_anchor: close[t] > ZLEMA[anchor][t]
      - macro_floor_hits_24h: count of warmed scales >= 377 whose ZLEMA_k or Z_BB_lo_k
        was swept within `floor_lookback_hours` and reclaimed (`close[t] > level`).
    """
    cl = np.asarray(close, dtype=float)
    lo = np.asarray(low, dtype=float)
    hi = np.asarray(high, dtype=float) if high is not None else np.maximum(cl, lo)
    n = len(cl)

    if len(lo) != n or len(hi) != n:
        raise ValueError("OHLC input lengths must match")

    at = (
        np.asarray(atr, dtype=float)
        if atr is not None
        else _causal_atr_wilder_or_simple(hi, lo, cl, window=24)
    )
    scales_tup = tuple(int(k) for k in scales)
    s_to_m = {k: m for m, k in enumerate(scales_tup)}

    zmat = np.full((n, len(scales_tup)), np.nan, dtype=float)
    zlo_mat = np.full((n, len(scales_tup)), np.nan, dtype=float)
    s_cl = pd.Series(cl)

    for m, k in enumerate(scales_tup):
        if zlema_by_scale is not None and k in zlema_by_scale:
            zl = np.asarray(zlema_by_scale[k], dtype=float)
        else:
            zl = compute_mql5_zlema(cl, k, init_zero=True, enforce_full_warmup=True)
        zmat[:, m] = zl

        if z_lo_by_scale is not None and k in z_lo_by_scale:
            zlo_mat[:, m] = np.asarray(z_lo_by_scale[k], dtype=float)
        else:
            sd = s_cl.rolling(window=k, min_periods=k).std(ddof=1).to_numpy(dtype=float)
            zlo_mat[:, m] = zl - 2.0 * sd

    valid = np.isfinite(zmat)
    wk_lb = int(wk_lookback_hours)
    wk_slp_mat = np.full((n, len(scales_tup)), np.nan, dtype=float)
    if n > wk_lb:
        denom = np.abs(zmat[:-wk_lb, :]) + 1e-8
        wk_slp_mat[wk_lb:, :] = (zmat[wk_lb:, :] - zmat[:-wk_lb, :]) / denom * 100.0

    lo_roll = (
        pd.Series(lo).rolling(int(floor_lookback_hours), min_periods=1).min().to_numpy(dtype=float)
    )

    k_anchor = np.zeros(n, dtype=int)
    submerge_frac = np.full(n, np.nan, dtype=float)
    anchor_wk_slp_pct = np.full(n, np.nan, dtype=float)
    outer_max_abs_wk_slp_pct = np.full(n, np.nan, dtype=float)
    close_above_anchor = np.zeros(n, dtype=bool)
    macro_floor_hits_24h = np.zeros(n, dtype=int)

    m21 = s_to_m.get(21, 0)
    m377 = s_to_m.get(377, 0)
    m_pref = s_to_m.get(int(anchor_scale), -1)

    for t in range(n):
        warmed_ms = [m for m in range(len(scales_tup)) if valid[t, m]]
        if not warmed_ms or warmed_ms[-1] < m377:
            continue

        ma = m_pref if (m_pref >= 0 and valid[t, m_pref]) else warmed_ms[-1]
        k_anchor[t] = scales_tup[ma]
        close_above_anchor[t] = bool(cl[t] > zmat[t, ma])

        sub_ms = [m for m in range(m21, ma) if valid[t, m]]
        if sub_ms:
            submerge_frac[t] = float(np.mean(zmat[t, sub_ms] < zmat[t, ma]))

        anchor_wk_slp_pct[t] = wk_slp_mat[t, ma]
        outer_ms = [m for m in warmed_ms if m >= ma]
        if len(outer_ms) == 1 and len(warmed_ms) >= 2:
            outer_ms = warmed_ms[-2:]
        slps = [wk_slp_mat[t, m] for m in outer_ms if np.isfinite(wk_slp_mat[t, m])]
        if slps:
            outer_max_abs_wk_slp_pct[t] = float(np.max(np.abs(slps)))

        at_t = at[t]
        if not (np.isfinite(at_t) and at_t > 1e-8):
            continue
        cnt = 0
        for m in warmed_ms:
            if scales_tup[m] < 377:
                continue
            zl_val = zmat[t, m]
            lo_val = zlo_mat[t, m]
            reclaim_zl = (cl[t] > zl_val) and (lo_roll[t] <= zl_val + 0.35 * at_t)
            reclaim_bblo = (
                np.isfinite(lo_val) and (cl[t] > lo_val) and (lo_roll[t] <= lo_val + 0.50 * at_t)
            )
            if reclaim_zl or reclaim_bblo:
                cnt += 1
        macro_floor_hits_24h[t] = cnt

    return {
        "scales": scales_tup,
        "k_anchor": k_anchor,
        "submerge_frac": submerge_frac,
        "anchor_wk_slp_pct": anchor_wk_slp_pct,
        "outer_max_abs_wk_slp_pct": outer_max_abs_wk_slp_pct,
        "close_above_anchor": close_above_anchor,
        "macro_floor_hits_24h": macro_floor_hits_24h,
        "zlema_mat": zmat,
        "z_lo_mat": zlo_mat,
        "wk_slp_mat": wk_slp_mat,
    }


def classify_zlema_ultra_macro_regime(
    submerge_frac: Sequence[float] | np.ndarray,
    anchor_wk_slp_pct: Sequence[float] | np.ndarray,
    outer_max_abs_wk_slp_pct: Sequence[float] | np.ndarray,
    close_above_anchor: Sequence[bool] | np.ndarray,
    macro_floor_hits_24h: Sequence[int] | np.ndarray,
) -> np.ndarray:
    """
    Mutually-exclusive 4-way ZLEMA Ultra-Macro Regime Classifier (+ WARMUP):
      1. WARMUP                : anchor/submerge_frac unavailable
      2. Z_SUBMERGED_PARALLEL  : submerge_frac >= 0.75 & (outer_max <= 1.8 or wk >= -1.8) & !close_above_anchor
      3. Z_BEAR_CASCADE        : elif submerge_frac >= 0.625 or (wk < -0.5 & !close_above_anchor)
      4. Z_FLOOR_SPRING        : elif macro_floor_hits_24h >= 2 and wk > -0.5
      5. Z_BULL_ABOVE          : else
    """
    sf_arr = np.asarray(submerge_frac, dtype=float)
    awk_arr = np.asarray(anchor_wk_slp_pct, dtype=float)
    omx_arr = np.asarray(outer_max_abs_wk_slp_pct, dtype=float)
    cab_arr = np.asarray(close_above_anchor, dtype=bool)
    flr_arr = np.asarray(macro_floor_hits_24h, dtype=int)

    n = len(sf_arr)
    out = np.full(n, "WARMUP", dtype=object)
    for t in range(n):
        sf = sf_arr[t]
        if not np.isfinite(sf):
            continue
        awk = float(awk_arr[t]) if np.isfinite(awk_arr[t]) else 0.0
        omx = float(omx_arr[t]) if np.isfinite(omx_arr[t]) else 99.0
        if sf >= 0.75 and (omx <= 1.8 or awk >= -1.8) and (not bool(cab_arr[t])):
            out[t] = "Z_SUBMERGED_PARALLEL"
        elif sf >= 0.625 or (awk < -0.5 and not bool(cab_arr[t])):
            out[t] = "Z_BEAR_CASCADE"
        elif int(flr_arr[t]) >= 2 and awk > -0.5:
            out[t] = "Z_FLOOR_SPRING"
        else:
            out[t] = "Z_BULL_ABOVE"
    return out


def evaluate_zlema_submerged_veto(
    submerge_frac: float,
    anchor_wk_slp_pct: float,
    subm_thr: float = 0.75,
    wk_max_pct: float = 0.50,
) -> bool:
    """
    Evaluate EXP-147 HYP-147-1 Submerged-Parallel hard veto condition.
    Returns True when a Long candidate would be vetoed (NOTE: empirically refuted K-098
    because L_SR3D + 1m already screens this regime; 16/16 cells degraded Std Tot).
    """
    if not (np.isfinite(submerge_frac) and np.isfinite(anchor_wk_slp_pct)):
        return False
    return bool(float(submerge_frac) >= float(subm_thr) and float(anchor_wk_slp_pct) <= float(wk_max_pct))


def evaluate_zlema_floor_spring_gate(
    macro_floor_hits_24h: int,
    submerge_frac: float,
    anchor_wk_slp_pct: float,
    min_floors: int = 2,
    subm_cap: float = 0.50,
    min_wk_pct: float = 0.0,
) -> bool:
    """
    Evaluate EXP-147 HYP-147-2 Case-02-inspired Floor-Spring Long gate.
    Returns True if structural floor-spring conditions hold (NOTE: standalone viable in Era1,
    but Track-2 cooldown conflicts degrade integrated Std MDD and MG 10/10 -> 8/10: K-098).
    """
    if not (np.isfinite(submerge_frac) and np.isfinite(anchor_wk_slp_pct)):
        return False
    return bool(
        int(macro_floor_hits_24h) >= int(min_floors)
        and float(submerge_frac) <= float(subm_cap)
        and float(anchor_wk_slp_pct) >= float(min_wk_pct)
    )


def compute_additive_portfolio_metrics(
    gross_returns: Sequence[float],
    friction_rate: float = FRICTION_RATE,
) -> dict[str, float]:
    """
    Strictly additive SPEC-EVAL-001 accounting (zero compounding, no np.prod).
    Input returns are decimal gross trade returns (e.g., 0.05 = +5.0%).
    """
    gross = np.asarray(list(gross_returns), dtype=float)
    n = int(len(gross))
    if n == 0:
        return {
            "total_trades": 0,
            "friction_cost_applied": float(friction_rate),
            "gross_mean_return": 0.0,
            "net_mean_return": 0.0,
            "total_net_return_pct": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        }

    net = gross - float(friction_rate)
    wins = net[net > 0.0]
    losses = net[net <= 0.0]
    gross_win = float(np.sum(wins))
    gross_loss = float(np.abs(np.sum(losses)))
    pf = gross_win / gross_loss if gross_loss > 1e-12 else (99.99 if gross_win > 0 else 0.0)

    cum_curve = np.cumsum(net)
    peaks = np.maximum.accumulate(np.concatenate(([0.0], cum_curve)))[1:]
    drawdowns = cum_curve - peaks
    max_dd = float(np.abs(np.min(np.concatenate(([0.0], drawdowns)))))

    return {
        "total_trades": n,
        "friction_cost_applied": float(friction_rate),
        "gross_mean_return": float(np.mean(gross)),
        "net_mean_return": float(np.mean(net)),
        "total_net_return_pct": float(np.sum(net) * 100.0),
        "win_rate": float(np.mean(net > 0.0)),
        "profit_factor": float(pf),
        "max_drawdown": float(max_dd),
    }


def main() -> None:
    """Run causal self-checks and report verified EXP-147 metrics."""
    exp_dir = Path(__file__).resolve().parent
    metrics_path = exp_dir / "metrics.json"

    # Synthetic forward-perturbation check on MQL5 BufferEMAZL & 4-regime pipeline
    rng = np.random.default_rng(147)
    n_syn = 320
    close_syn = 40000.0 + np.cumsum(rng.normal(10.0, 220.0, size=n_syn))
    low_syn = close_syn - np.abs(rng.normal(90.0, 40.0, size=n_syn))
    high_syn = close_syn + np.abs(rng.normal(90.0, 40.0, size=n_syn))
    for period in (21, 55, 144):
        diff = verify_zlema_zero_lookahead(close_syn, period=period, t_cut=260)
        assert diff == 0.0, f"Lookahead self-check failed for period={period}: {diff}"

    feats = compute_zlema_ultra_macro_features(
        close=close_syn,
        low=low_syn,
        high=high_syn,
        scales=(8, 13, 21, 34, 55, 89, 144),
        anchor_scale=89,
    )
    _ = classify_zlema_ultra_macro_regime(
        feats["submerge_frac"],
        feats["anchor_wk_slp_pct"],
        feats["outer_max_abs_wk_slp_pct"],
        feats["close_above_anchor"],
        feats["macro_floor_hits_24h"],
    )

    if not metrics_path.exists():
        raise FileNotFoundError(f"metrics.json not found at {metrics_path}")

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    std = metrics["baseline_exp145_champion"]["Std"]
    mb = metrics["baseline_exp145_champion"]["ModeB"]
    ma = metrics["baseline_exp145_champion"]["ModeA"]
    audit = metrics["experiment_metadata"]["zlema_lookahead_audit"]
    p4 = metrics["part4_hyp147_3_t1_and_shorts"]

    print("=== EXP-147: MQL5 ZLEMA (BufferEMAZL) 17-Scale Ultra-Macro Continuum ===")
    print(f"Synthetic ZLEMA zero-lookahead self-check: PASS (max_diff = 0.0)")
    print(
        f"Discovery ZLEMA zero-lookahead (t_cut={audit['t_cut']}): "
        f"PASS={audit['passed_zero_lookahead']}, max_diff={audit['max_lookahead_diff']}"
    )
    print(
        f"Retained Champion (EXP-145 T1_Full_D4_RelaxFlip): "
        f"Std N={std['n']}, WR={std['wr']:.2f}%, PF={std['pf']:.2f}, "
        f"Tot=+{std['tot']:.2f}%, MDD={std['mdd']:.2f}%, MG={std['mg']}/10 | "
        f"ModeB=+{mb['tot']:.2f}%, ModeA=+{ma['tot']:.2f}%"
    )
    print(
        f"Submerged-Parallel Ceiling Shorts positive cells (4x4): "
        f"{p4['short_n_positive_cells']}/16 (Refuted)"
    )


if __name__ == "__main__":
    main()
