"""
EXP-141: 3D S/R Congestion Decomposition (Density x Vertical Ordering x Slope)
& Multi-Scale Circular Phase Coherence (R_1h, R_1m) Integration.

Key Principles & Invariants:
1. Zero Window-Dressing: Zero hardcoded timestamp whitelists (hardcoded_whitelist_count = 0).
2. Strict Causal Execution: Zero lookahead; 1h signal at t0 pairs with 1m window <= t0 + 59m.
3. Strict Additive Net Return Accounting: sum(net_ret) * 100.0 with 40 bps roundtrip friction.
4. Core EXP-141 Functional Primitives (building on EXP-139):
   - compute_circular_cycle_phase_coherence
   - compute_sr_congestion_3d_decomposition
   - evaluate_3d_sr_congestion_long_gate
   - evaluate_1m_multiscale_phase_coherence_short_gate
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence
import numpy as np
import pandas as pd

TREE_SCALES: list[int] = [
    8, 13, 21, 34, 55, 89, 144, 233, 377, 610,
    987, 1597, 2584, 4181, 6765, 10946, 17711,
]
CYCLE_SCALES_1H: list[int] = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610]
COHERENCE_SCALES_1M: list[int] = [13, 21, 34, 55, 89]
FRICTION_RATE: float = 0.0040


def _get_finite(row_0: pd.Series | dict[str, Any], key: str, default: float) -> float:
    """Safely extracts a finite float from row_0, returning default when missing or non-finite."""
    val = row_0.get(key, default)
    if val is None or pd.isna(val):
        return float(default)
    fval = float(val)
    return fval if np.isfinite(fval) else float(default)


def _get_optional_finite(row_0: pd.Series | dict[str, Any], key: str) -> float | None:
    """Safely extracts a finite float from row_0, returning None when missing or non-finite."""
    val = row_0.get(key, None)
    if val is None or pd.isna(val):
        return None
    fval = float(val)
    return fval if np.isfinite(fval) else None


def compute_circular_cycle_phase_coherence(
    phase_angles_rad: np.ndarray | Sequence[float] | pd.Series,
) -> float:
    """
    Computes the Kuramoto order parameter (circular phase coherence) R in [0, 1]
    across multi-scale cycle phase angles theta_m (in radians):
        R = |(1 / M) * sum_{m=1..M} exp(i * theta_m)|
    Values near 1.0 indicate synchronized phase alignment across scales; values near
    0.0 indicate anti-phase destructive interference / phase dissipation.
    """
    arr = np.asarray(phase_angles_rad, dtype=float)
    valid = arr[np.isfinite(arr)]
    if len(valid) == 0:
        raise ValueError("phase_angles_rad must contain at least one finite angle")
    coherence = float(np.abs(np.mean(np.exp(1j * valid))))
    return float(np.clip(coherence, 0.0, 1.0))


def compute_sr_congestion_3d_decomposition(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict[str, Any],
    sup_scale: int,
    parent_scale: int,
    scales: Sequence[int] = TREE_SCALES,
    max_dist_atr: float = 1.5,
) -> tuple[int, int, bool, bool, bool, str]:
    """
    Decomposes S/R congestion below p0 along three orthogonal physical axes:
    1. Density (lam_15): count of {SMA_j, BB_lower_j, P_sup_j} surfaces for scales >= 21
       lying within [-0.2, max_dist_atr] ATR below p0.
    2. Vertical Ordering:
       - triad_ordered: SMA(k-1) > SMA(k) > SMA(k+1) around the supporting scale.
       - inv_count: pairwise ordering inversions (SMA_i < SMA_j for i < j) among
         the congested scales contributing to lam_15.
    3. Slope Alignment:
       - slopes_rising: slope(k) > 0 and slope(k+1) > 0.
       - macro_slope_positive: slope(610) > 0 (defaults to slope(k+1) if omitted).

    Returns (lam_15, inv_count, triad_ordered, slopes_rising, macro_slope_positive, quad_label).
    """
    c0 = float(p0)
    atr_safe = max(float(atr0), 1e-8)
    s_k = int(sup_scale)
    s_p1 = int(parent_scale)
    scale_list = list(scales)

    if s_k in scale_list and scale_list.index(s_k) > 0:
        s_m1 = int(scale_list[scale_list.index(s_k) - 1])
    else:
        s_m1 = s_k

    # 1. Density & congested scale set (scales >= 21 matching EXP-141 protocol)
    lam_15 = 0
    lam_scales: list[int] = []
    scan_scales = [int(sc) for sc in scale_list if int(sc) >= 21]
    for sc in scan_scales:
        for pref in ("sma", "bb_lower", "sup"):
            val = _get_optional_finite(row_0, f"{pref}_{sc}")
            if val is None and pref == "sup":
                val = _get_optional_finite(row_0, f"p_sup_{sc}")
            if val is None:
                continue
            dist_atr = (c0 - val) / atr_safe
            if -0.2 <= dist_atr <= float(max_dist_atr):
                lam_15 += 1
                if sc not in lam_scales:
                    lam_scales.append(sc)

    # 2. Vertical Ordering (triad alignment + pairwise congestion inversions)
    sma_k = _get_finite(row_0, f"sma_{s_k}", c0)
    sma_m1 = _get_finite(row_0, f"sma_{s_m1}", c0)
    sma_p1 = _get_finite(row_0, f"sma_{s_p1}", sma_k)
    triad_ordered = bool(((sma_m1 - sma_k) > 0.0) and ((sma_k - sma_p1) > 0.0))

    lam_scales_sorted = sorted(lam_scales)
    inv_count = 0
    for i in range(len(lam_scales_sorted)):
        sma_i = _get_optional_finite(row_0, f"sma_{lam_scales_sorted[i]}")
        if sma_i is None:
            continue
        for j in range(i + 1, len(lam_scales_sorted)):
            sma_j = _get_optional_finite(row_0, f"sma_{lam_scales_sorted[j]}")
            if sma_j is not None and (sma_i - sma_j) < 0.0:
                inv_count += 1

    ordered_strict = bool(triad_ordered and (inv_count == 0))

    # 3. Slope Alignment
    slp_k = _get_finite(row_0, f"slope_{s_k}", 0.0)
    slp_p1 = _get_finite(row_0, f"slope_{s_p1}", 0.0)
    slp_610 = _get_finite(row_0, "slope_610", slp_p1)
    slopes_rising = bool((slp_k > 0.0) and (slp_p1 > 0.0))
    macro_slope_positive = bool(slp_610 > 0.0)

    if ordered_strict and slopes_rising:
        quad_label = "Q1_Ordered_Rising"
    elif ordered_strict:
        quad_label = "Q2_Ordered_FlatFall"
    elif slopes_rising:
        quad_label = "Q3_Inverted_Rising"
    else:
        quad_label = "Q4_Inverted_FlatFall"

    return (
        int(lam_15),
        int(inv_count),
        triad_ordered,
        slopes_rising,
        macro_slope_positive,
        quad_label,
    )


def evaluate_3d_sr_congestion_long_gate(
    lam_15: int,
    inv_count: int,
    triad_ordered: bool,
    slopes_rising: bool,
    macro_slope_positive: bool,
    r_mean_coherence: float,
    min_congestion_surfaces: int = 5,
    min_coherence_bypass: float = 0.80,
) -> bool:
    """
    Evaluates the Long 3D S/R Congestion Gate.
    Returns False ONLY on a true Spaghetti Congestion Trap:
      - High surface density: lam_15 >= min_congestion_surfaces (5)
      - Vertical inversion: inv_count > 0 or not triad_ordered
      - Degraded slope: not slopes_rising or not macro_slope_positive
      - Phase dissipation: r_mean_coherence < min_coherence_bypass (0.80)

    Preserves Ordered+Rising compressed launchpads (F2a = 0.0%) and
    High-Coherence macro V-bottom Mega-Runners (R_mean >= 0.80).
    """
    is_congested = int(lam_15) >= int(min_congestion_surfaces)
    is_inverted = (int(inv_count) > 0) or (not bool(triad_ordered))
    is_slope_degraded = (not bool(slopes_rising)) or (not bool(macro_slope_positive))
    is_incoherent = float(r_mean_coherence) < float(min_coherence_bypass)
    is_spaghetti_trap = is_congested and is_inverted and is_slope_degraded and is_incoherent
    return not is_spaghetti_trap


def evaluate_1m_multiscale_phase_coherence_short_gate(
    r_1m_coherence: float,
    min_r_1m: float = 0.75,
) -> bool:
    """
    Evaluates the Short 1m Multi-Scale Circular Phase Coherence Gate across
    [13, 21, 34, 55, 89]. Returns True when R_1m >= min_r_1m (default 0.75),
    rejecting phase-dissipated micro-stop traps.
    """
    val = float(r_1m_coherence)
    if not np.isfinite(val):
        return False
    return bool(val >= float(min_r_1m))


def compute_additive_portfolio_metrics(
    net_returns_decimal: Sequence[float] | np.ndarray,
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
        print("EXP-141 Audited Portfolio Ablation Progression:")
        print(json.dumps(data["portfolio_ablation_progression"], indent=2))
