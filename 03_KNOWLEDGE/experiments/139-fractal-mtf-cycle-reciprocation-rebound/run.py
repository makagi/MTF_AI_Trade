"""
EXP-139: 1h x 1m Fractal MTF SMA Reciprocation, BB, AFS/Stoch_d Cycle Rebound
Point Judgment, Cycle-Adaptive S/R Floor Height Estimation, and Dual-Symmetric
Period Drift Gating.

Key Principles & Invariants:
1. Zero Window-Dressing: Zero hardcoded timestamp whitelists (hardcoded_whitelist_count = 0).
2. Strict Causal Execution: Zero lookahead; 1h signal at t0 pairs with 1m window <= t0 + 59m.
3. Strict Additive Net Return Accounting: sum(net_ret) * 100.0 with 40 bps roundtrip friction.
4. Four Core EXP-139 Functional Primitives (building on EXP-137):
   - compute_causal_cycle_phase_and_period_resonance
   - estimate_cycle_adaptive_rebound_floor_height
   - evaluate_1h_dual_symmetric_cycle_gate
   - evaluate_1m_fractal_reciprocation_and_cycle_gate
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

TREE_SCALES: list[int] = [
    8, 13, 21, 34, 55, 89, 144, 233, 377, 610,
    987, 1597, 2584, 4181, 6765, 10946, 17711,
]
CYCLE_SCALES_1H: list[int] = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610]
TREE_SCALES_1M: list[int] = [8, 13, 21, 34, 55, 89, 144, 233, 377]
FRICTION_RATE: float = 0.0040


def _get_finite(row_0: pd.Series | dict, key: str, default: float) -> float:
    """Safely extracts a float from row_0, returning default when missing or NaN."""
    val = row_0.get(key, default)
    if val is None or pd.isna(val):
        return float(default)
    return float(val)


def _classify_quadrant(stoch_d: float, dstoch_d: float) -> str:
    """Maps (Stoch_d, dStoch_d) into 2D cycle phase quadrant Q1..Q4."""
    if stoch_d >= 50.0:
        return "Q1" if dstoch_d >= 0.0 else "Q2"
    return "Q4" if dstoch_d >= 0.0 else "Q3"


def compute_causal_cycle_phase_and_period_resonance(
    stoch_d_series: np.ndarray | list[float] | pd.Series,
    hysteresis_pt: float = 12.0,
    default_period: float = 21.0,
) -> dict[str, Any]:
    """
    Strictly causal swing-cycle state machine and 2D phase quadrant analyzer
    on Stoch_d in [0, 100]. Zero lookahead: bar t uses only stoch_d[0..t].

    Computes:
    - 3-bar velocity dStoch_d and 2D phase angle theta = atan2(dStoch_d, Stoch_d - 50).
    - Phase quadrant labels Q1 (UpperExp), Q2 (TopRoll), Q3 (MidDive), Q4 (TroughHook).
    - Confirmed trough-to-trough period T_trough and peak-to-peak period T_peak via
      hysteresis_pt reversal confirmation (default 12.0 pt) or 50-line crossover after
      reaching >= 60 (peak) / <= 40 (trough).
    - Period resonance ratios rho_trough = tau_trough / T_trough and
      rho_peak = tau_peak / T_peak.
    """
    arr = np.asarray(stoch_d_series, dtype=float)
    n = int(len(arr))
    if n == 0:
        raise ValueError("stoch_d_series must be non-empty")

    velocities = np.zeros(n, dtype=float)
    if n > 3:
        velocities[3:] = arr[3:] - arr[:-3]
    thetas = np.arctan2(velocities, arr - 50.0)
    quadrants = [_classify_quadrant(float(arr[i]), float(velocities[i])) for i in range(n)]

    base_period = float(max(4.0, default_period))
    max_valid_period = float(max(150.0, 6.0 * base_period))

    tau_trough_arr = np.zeros(n, dtype=float)
    tau_peak_arr = np.zeros(n, dtype=float)
    t_trough_arr = np.full(n, base_period, dtype=float)
    t_peak_arr = np.full(n, base_period, dtype=float)
    rho_trough_arr = np.zeros(n, dtype=float)
    rho_peak_arr = np.zeros(n, dtype=float)

    swing = 1
    cur_peak_val = -1.0
    cur_peak_i = 0
    cur_trough_val = 101.0
    cur_trough_i = 0

    conf_troughs: list[tuple[int, float]] = []
    conf_peaks: list[tuple[int, float]] = []
    cur_t_tr = base_period
    cur_t_pk = base_period

    for t in range(n):
        v = float(arr[t])
        if np.isnan(v):
            t_trough_arr[t] = cur_t_tr
            t_peak_arr[t] = cur_t_pk
            continue

        if swing == 1:
            if v >= cur_peak_val:
                cur_peak_val = v
                cur_peak_i = t
            if (cur_peak_val - v >= hysteresis_pt) or (cur_peak_val >= 60.0 and v < 50.0):
                conf_peaks.append((cur_peak_i, cur_peak_val))
                if len(conf_peaks) >= 2:
                    dt_pk = float(conf_peaks[-1][0] - conf_peaks[-2][0])
                    if 4.0 <= dt_pk <= max_valid_period:
                        cur_t_pk = dt_pk
                swing = -1
                cur_trough_val = v
                cur_trough_i = t
        else:
            if v <= cur_trough_val:
                cur_trough_val = v
                cur_trough_i = t
            if (v - cur_trough_val >= hysteresis_pt) or (cur_trough_val <= 40.0 and v > 50.0):
                conf_troughs.append((cur_trough_i, cur_trough_val))
                if len(conf_troughs) >= 2:
                    dt_tr = float(conf_troughs[-1][0] - conf_troughs[-2][0])
                    if 4.0 <= dt_tr <= max_valid_period:
                        cur_t_tr = dt_tr
                swing = 1
                cur_peak_val = v
                cur_peak_i = t

        t_trough_arr[t] = cur_t_tr
        t_peak_arr[t] = cur_t_pk
        tau_tr = float(t - conf_troughs[-1][0]) if conf_troughs else float(t)
        tau_pk = float(t - conf_peaks[-1][0]) if conf_peaks else float(t)
        tau_trough_arr[t] = tau_tr
        tau_peak_arr[t] = tau_pk
        rho_trough_arr[t] = tau_tr / max(cur_t_tr, 1e-8)
        rho_peak_arr[t] = tau_pk / max(cur_t_pk, 1e-8)

    return {
        "quadrant": quadrants[-1],
        "velocity": float(velocities[-1]),
        "theta": float(thetas[-1]),
        "tau_trough": float(tau_trough_arr[-1]),
        "tau_peak": float(tau_peak_arr[-1]),
        "t_trough": float(t_trough_arr[-1]),
        "t_peak": float(t_peak_arr[-1]),
        "rho_trough": float(rho_trough_arr[-1]),
        "rho_peak": float(rho_peak_arr[-1]),
        "quadrants": quadrants,
        "velocities": velocities,
        "thetas": thetas,
        "tau_trough_series": tau_trough_arr,
        "tau_peak_series": tau_peak_arr,
        "t_trough_series": t_trough_arr,
        "t_peak_series": t_peak_arr,
        "rho_trough_series": rho_trough_arr,
        "rho_peak_series": rho_peak_arr,
        "conf_trough_indices": np.array([x[0] for x in conf_troughs], dtype=int),
        "conf_peak_indices": np.array([x[0] for x in conf_peaks], dtype=int),
    }


def estimate_cycle_adaptive_rebound_floor_height(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
    sup_scale: int,
    parent_scale: int,
) -> float:
    """
    Computes the cycle-adaptive rebound floor height estimator P_hat_reb(t) for
    long pullbacks by blending SMA(k), P_sup(k), BB_lower(k), and parent SMA(k+1)
    based on child Stoch_d(k-1) / BB_pos(k) cycle depth and parent-child separation d_{k, k+1}.

    - Inverted below parent (d_{k, k+1} <= 0): 0.50 * BB_lower(k) + 0.50 * P_sup(k).
    - Shallow pullback (alpha_depth < 0.35): anchors near SMA(k) (0.75 * SMA(k) + 0.25 * BB_lower(k-1)).
    - Medium pullback (0.35 <= alpha_depth < 0.70): blends SMA(k), P_sup(k), and BB_lower(k).
    - Deep oversold cycle (alpha_depth >= 0.70): blends BB_lower(k), SMA(k+1), and deep floor
      (max(SMA(k+1), P_sup(k)) when d_{k, k+1} > 0.5 else min(BB_lower(k), SMA(k+1))).
    """
    atr_safe = max(float(atr0), 1e-8)
    s_k = int(sup_scale)
    s_p1 = int(parent_scale)
    if s_k in TREE_SCALES and TREE_SCALES.index(s_k) > 0:
        s_m1 = TREE_SCALES[TREE_SCALES.index(s_k) - 1]
    else:
        s_m1 = s_k

    sma_k = _get_finite(row_0, f"sma_{s_k}", p0)
    sma_p1 = _get_finite(row_0, f"sma_{s_p1}", sma_k)
    sma_m1 = _get_finite(row_0, f"sma_{s_m1}", p0)
    bb_low_k = _get_finite(row_0, f"bb_lower_{s_k}", sma_k - 2.0 * atr_safe)
    bb_low_m1 = _get_finite(row_0, f"bb_lower_{s_m1}", sma_k)
    p_sup_k = _get_finite(row_0, f"sup_{s_k}", _get_finite(row_0, f"p_sup_{s_k}", bb_low_k))

    if f"stoch_d_{s_m1}" in row_0 and row_0.get(f"stoch_d_{s_m1}") is not None:
        stoch_m1 = _get_finite(row_0, f"stoch_d_{s_m1}", 50.0)
    elif "stoch_d_child" in row_0 and row_0.get("stoch_d_child") is not None:
        stoch_m1 = _get_finite(row_0, "stoch_d_child", 50.0)
    else:
        stoch_m1 = 50.0 + 50.0 * _get_finite(row_0, f"stoch_z_{s_m1}", 0.0)

    if f"bb_pos_{s_k}" in row_0 and row_0.get(f"bb_pos_{s_k}") is not None:
        bb_pos_k = _get_finite(row_0, f"bb_pos_{s_k}", 0.5)
    else:
        bb_up_k = _get_finite(row_0, f"bb_upper_{s_k}", sma_k + (sma_k - bb_low_k))
        bb_pos_k = (float(p0) - bb_low_k) / max(bb_up_k - bb_low_k, 1e-8)

    d_k_p1 = (sma_k - sma_p1) / atr_safe
    depth_stoch = float(np.clip((60.0 - stoch_m1) / 50.0, 0.0, 1.0))
    depth_bb = float(np.clip((0.50 - bb_pos_k) / 0.60, 0.0, 1.0))
    alpha_depth = 0.5 * depth_stoch + 0.5 * depth_bb

    is_full_stack = (sma_m1 >= sma_k) and (sma_k > sma_p1)
    if d_k_p1 <= 0.0:
        return float(0.50 * bb_low_k + 0.50 * p_sup_k)
    if alpha_depth < 0.35 and is_full_stack:
        return float(0.75 * sma_k + 0.25 * bb_low_m1)
    if alpha_depth < 0.70:
        return float(0.45 * sma_k + 0.30 * p_sup_k + 0.25 * bb_low_k)

    deep_floor = max(sma_p1, p_sup_k) if d_k_p1 > 0.5 else min(bb_low_k, sma_p1)
    return float(0.45 * bb_low_k + 0.35 * sma_p1 + 0.20 * deep_floor)


def evaluate_1h_dual_symmetric_cycle_gate(
    direction: str,
    rho_cycle_child: float,
    stoch_d_child: float,
    dstoch_d_child: float,
    max_rho_long: float = 2.0,
    max_q1_stoch_long: float = 65.0,
    max_rho_short: float = 2.0,
) -> bool:
    """
    Evaluates the 1h Dual-Symmetric Cycle Drift Gate:
    - Long (springboards): rejects over-aged trough drift (rho_cycle_child > max_rho_long)
      and overheated Q1 upper expansion chases (stoch_d_child >= max_q1_stoch_long and dstoch_d_child >= 0).
    - Short (Engine B): rejects over-aged peak drift (rho_cycle_child > max_rho_short).
    Returns True if entry is permitted, False if blocked.
    """
    side = direction.strip().lower()
    rho = float(rho_cycle_child)
    st = float(stoch_d_child)
    dst = float(dstoch_d_child)

    if side in ("long", "l", "buy"):
        if rho > float(max_rho_long):
            return False
        if st >= float(max_q1_stoch_long) and dst >= 0.0:
            return False
        return True
    if side in ("short", "s", "sell"):
        return rho <= float(max_rho_short)
    raise ValueError(f"Unsupported direction: {direction!r}")


def evaluate_1m_fractal_reciprocation_and_cycle_gate(
    direction: str,
    m1_d_21_55: float,
    m1_bb_exp_55: float,
    m1_rho_pk_21: float,
    max_m1_stretch: float = 3.0,
    max_m1_bb_pinch: float = 0.0,
    max_m1_rho_short: float = 2.0,
) -> bool:
    """
    Evaluates the 1m Fractal Discernment Gate (at causal bar t0 + 59m):
    - Long: rejects 1m Climax Pinch traps where m1_d_21_55 > max_m1_stretch (3.0 1m-ATR)
      AND m1_bb_exp_55 <= max_m1_bb_pinch (0.0).
    - Short: rejects 1m over-aged peak drift where m1_rho_pk_21 > max_m1_rho_short (2.0).
    Returns True if entry is permitted, False if blocked.
    """
    side = direction.strip().lower()
    if side in ("long", "l", "buy"):
        return not (float(m1_d_21_55) > float(max_m1_stretch) and float(m1_bb_exp_55) <= float(max_m1_bb_pinch))
    if side in ("short", "s", "sell"):
        return float(m1_rho_pk_21) <= float(max_m1_rho_short)
    raise ValueError(f"Unsupported direction: {direction!r}")


def compute_additive_portfolio_metrics(
    net_returns_decimal: list[float] | np.ndarray,
) -> dict[str, float | int]:
    """
    Computes project-standard strictly ADDITIVE portfolio metrics (zero compounding inflation).
    Each element in net_returns_decimal is a trade net return after 40 bps friction.
    """
    arr = np.asarray(net_returns_decimal, dtype=float)
    n = int(len(arr))
    if n == 0:
        return {
            "executed_trades": 0,
            "win_rate_pct": 0.0,
            "net_mean_return_pct": 0.0,
            "profit_factor": 0.0,
            "total_opportunity_net_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }

    wins = arr[arr > 0.0]
    losses = arr[arr < 0.0]
    win_rate_pct = float((arr > 0.0).mean() * 100.0)
    total_net_pct = float(np.sum(arr) * 100.0)
    mean_net_pct = float(np.mean(arr) * 100.0)

    gross_profit = float(np.sum(wins))
    gross_loss = float(np.abs(np.sum(losses)))
    pf = float(gross_profit / gross_loss) if gross_loss > 1e-12 else (99.9 if gross_profit > 0 else 0.0)

    cum_curve_pct = np.cumsum(arr) * 100.0
    running_peak = np.maximum.accumulate(np.insert(cum_curve_pct, 0, 0.0))[1:]
    dd_series = cum_curve_pct - running_peak
    max_dd_pct = float(np.min(dd_series)) if len(dd_series) > 0 else 0.0

    return {
        "executed_trades": n,
        "win_rate_pct": round(win_rate_pct, 2),
        "net_mean_return_pct": round(mean_net_pct, 2),
        "profit_factor": round(pf, 2),
        "total_opportunity_net_return_pct": round(total_net_pct, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
    }


if __name__ == "__main__":
    metrics_path = Path(__file__).parent / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print("EXP-139 Audited Portfolio Ablation Progression:")
        print(json.dumps(data["portfolio_ablation_progression"], indent=2))
