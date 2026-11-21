"""
EXP-135: Scale-Agnostic Dual Integrated Baseline (Stage 2) &
Role-Weighted 2D Cross-Scale Tensor MTF RR Architecture.

Key Principles & Invariants:
1. Zero Window-Dressing: Zero hardcoded timestamp whitelists (MEGA_RUNNER_TIMESTAMPS = 0).
2. Strict Additive Net Return Accounting: sum(net_ret) * 100.0 with 40 bps roundtrip friction.
3. Scale-Agnostic Dual Resistance Anchor Selection & Handover (S233 -> S144 -> S89 -> S55).
4. Role-Weighted & Cumulative-Barrier 2D Cross-Scale Tensor MTF RR:
   - Broken floors (phi_bar_s <= 0.0) are transparent (w_k = 0.0, 93.4% empirical shatter rate).
   - Active defended floors (phi_bar_s > 0.05..0.20) act as opaque barriers (71.0% empirical rebound rate).
5. Orthogonal Wave Synergy Gate:
   - Intersects 2D Tensor Void Clearance with Natural-Zero BB Non-Contraction (BB_exp >= 0.0)
     and Short-Scale Curvature Rollover (CurvL1 <= 0.0).
"""

from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.ndimage import convolve1d

TREE_SCALES: list[int] = [
    8, 13, 21, 34, 55, 89, 144, 233, 377, 610,
    987, 1597, 2584, 4181, 6765, 10946, 17711,
]
PYRAMID_KERNEL_1D: np.ndarray = np.array([0.25, 0.50, 0.25], dtype=float)
FRICTION_RATE: float = 0.0040


def select_initial_dynamic_resistance_anchor(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
) -> int:
    """
    Scale-agnostic dual initial resistance anchor selection for Macro Breakdown Shorts (Stage 2).
    Exact dual mirror of EXP-133 select_initial_dynamic_anchor:
    - Abolishes fixed S233 lock.
    - When S233 is overextended above price (dist_233 > 3.2 ATR) and S144 is an active overhead
      resistance ceiling (phi_bar_144 <= -0.15, slope_144 <= 0), steps down to S144.
    - When S233 is below price or its resistance role is invalid (phi_bar_233 > +0.10),
      steps down to the outermost valid overhead resistance scale among [144, 89, 55].
    """
    atr_safe = max(float(atr0), 1e-8)
    sma_233 = float(row_0.get("sma_233", p0 + atr_safe))
    slope_233 = float(row_0.get("slope_233", 0.0))
    phi_233 = float(row_0.get("phi_bar_233", 0.0))
    dist_233 = (sma_233 - p0) / atr_safe

    sma_144 = float(row_0.get("sma_144", p0 + atr_safe))
    slope_144 = float(row_0.get("slope_144", 0.0))
    phi_144 = float(row_0.get("phi_bar_144", 0.0))

    # 1. Overextension step-down to 144
    if dist_233 > 3.2 and sma_144 > p0 and slope_144 <= 0.0 and phi_144 <= -0.15:
        return 144

    # 2. Normal valid S233 overhead resistance
    if sma_233 > p0 and slope_233 <= 0.002 and phi_233 <= 0.10:
        return 233

    # 3. Step-down scan across inner scales [144, 89, 55]
    for s in (144, 89, 55):
        sma_s = float(row_0.get(f"sma_{s}", p0))
        phi_s = float(row_0.get(f"phi_bar_{s}", 0.0))
        slope_s = float(row_0.get(f"slope_{s}", 0.0))
        if sma_s > p0 and phi_s <= 0.05 and slope_s <= 0.005:
            return s

    return 233


def _collect_directional_levels(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
    scales: list[int],
    below_price: bool = True,
    min_dist_atr: float = 0.0,
) -> list[tuple[float, int, float, float]]:
    """Collects (dist_atr, scale, sma_val, phi_val) sorted ascending by distance from p0."""
    atr_safe = max(float(atr0), 1e-8)
    levels: list[tuple[float, int, float, float]] = []
    for s in scales:
        sma_val = row_0.get(f"sma_{s}", np.nan)
        if pd.isna(sma_val):
            continue
        sma_f = float(sma_val)
        if below_price:
            if sma_f >= p0:
                continue
            dist = (p0 - sma_f) / atr_safe
        else:
            if sma_f <= p0:
                continue
            dist = (sma_f - p0) / atr_safe
        if dist > min_dist_atr:
            phi_val = float(row_0.get(f"phi_bar_{s}", 0.0))
            levels.append((float(dist), int(s), sma_f, phi_val))
    levels.sort(key=lambda x: (x[0], x[1]))
    return levels


def compute_nearest_defended_floor_clearance(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
    scales: list[int] = TREE_SCALES,
    phi_min: float = 0.05,
    max_cap_atr: float = 15.0,
) -> tuple[float, int | None, float]:
    """
    Scans all 17 Fibonacci scales below p0 for the nearest ACTIVE defended support floor
    satisfying phi_bar_s > phi_min.
    Returns: (distance_in_atr, floor_scale, floor_price).
    If no defended floor exists below p0, returns (max_cap_atr, None, p0 - max_cap_atr * atr0).
    """
    atr_safe = max(float(atr0), 1e-8)
    for dist, s, sma_f, phi_val in _collect_directional_levels(
        p0, atr_safe, row_0, scales, below_price=True, min_dist_atr=0.0
    ):
        if phi_val > phi_min and dist < max_cap_atr:
            return dist, s, sma_f

    return float(max_cap_atr), None, float(p0 - max_cap_atr * atr_safe)


def compute_multiscale_barrier_survival_s3(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
    scales: list[int] = TREE_SCALES,
    barrier_scale: float = 0.20,
    alpha: float = 0.50,
) -> tuple[float, float, list[int]]:
    """
    Computes multi-scale cumulative barrier survival probability across the top 3 nearest
    underfoot SMA floors (F1, F2, F3 in [21..2584] at distance > 0.2 ATR):
        w_j = clip(phi_bar_{F_j} / barrier_scale, 0.0, 1.0)
        S_3 = prod_{j=1..3} (1 - alpha * w_j)
    Returns: (s3_survival, phi_sup1, floor_scales).
    """
    cand_floors = [s for s in scales if 21 <= s <= 2584] or list(scales)
    floors = _collect_directional_levels(
        p0, atr0, row_0, cand_floors, below_price=True, min_dist_atr=0.2
    )
    if not floors:
        return 1.0, 0.0, []

    phi_sup1 = float(floors[0][3])
    top3 = floors[:3]
    s3 = 1.0
    b_scale = max(float(barrier_scale), 1e-8)
    for _, _, _, phi_j in top3:
        w_j = float(np.clip(phi_j / b_scale, 0.0, 1.0))
        s3 *= (1.0 - float(alpha) * w_j)

    return float(s3), phi_sup1, [f[1] for f in top3]


def compute_scale_relative_bb_contraction(
    row_0: pd.Series | dict,
    sup_scale: int,
    scales: list[int] = TREE_SCALES,
) -> tuple[float, float, float]:
    """
    Computes scale-relative Bollinger Band slope expansion relative to support scale `sup_scale`:
    - `bb_in_le`: mean(bb_slope_exp_s) across pullback scales 21 <= s <= sup_scale
    - `bb_outer_gt`: mean(bb_slope_exp_s) across parent macro scales sup_scale < s <= 1597
    - `delta_bb`: bb_in_le - bb_outer_gt (negative = pullback cooling inside expanding parent)
    Returns: (bb_in_le, bb_outer_gt, delta_bb).
    """
    bb_scales = [s for s in scales if s <= 1597] or list(scales)
    inner_scales = [s for s in bb_scales if 21 <= s <= sup_scale] or [sup_scale]
    outer_scales = [s for s in bb_scales if s > sup_scale] or [bb_scales[-1]]

    def _mean_bb_exp(target_scales: list[int]) -> float:
        vals = [
            float(row_0[f"bb_slope_exp_{s}"])
            for s in target_scales
            if f"bb_slope_exp_{s}" in row_0 and not pd.isna(row_0[f"bb_slope_exp_{s}"])
        ]
        return float(np.mean(vals)) if vals else 0.0

    bb_in_le = _mean_bb_exp(inner_scales)
    bb_outer_gt = _mean_bb_exp(outer_scales)
    return bb_in_le, bb_outer_gt, float(bb_in_le - bb_outer_gt)


def evaluate_scale_relative_springboard_long_gate(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
    sup_scale: int,
    require_upside_wall_clearance: bool = True,
) -> bool:
    """
    Evaluates the Proposal A + Scale-Relative BB Pullback Gate for Extra Springboard Longs:
    1. Resilient Bedrock Nearest Floor: phi_sup1 > 0.20
    2. Multi-Scale Barrier Survival Cap: S_3 <= 0.25
    3. Scale-Relative Pullback Coiling: mean bb_slope_exp([21..sup_scale]) < 0.0
    4. Optional Defended Overhead Wall Clearance (Scale-Rel D/E): nearest overhead wall
       with phi_bar_s < -0.05 in [34..2584] sits at d_res_def_05 >= 2.0 ATR.
    """
    s3, phi_sup1, _ = compute_multiscale_barrier_survival_s3(p0, atr0, row_0)
    if phi_sup1 <= 0.20 or s3 > 0.25:
        return False

    bb_in_le, _, _ = compute_scale_relative_bb_contraction(row_0, sup_scale)
    if bb_in_le >= 0.0:
        return False

    if require_upside_wall_clearance:
        cand_walls = [s for s in TREE_SCALES if 34 <= s <= 2584]
        walls = _collect_directional_levels(
            p0, atr0, row_0, cand_walls, below_price=False, min_dist_atr=0.0
        )
        defended_walls = [w[0] for w in walls if w[3] < -0.05]
        d_res_def_05 = min(defended_walls) if defended_walls else 99.0
        if d_res_def_05 < 2.0:
            return False

    return True


def compute_cumulative_barrier_role_weighted_2d_tensor(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
    scales: list[int] = TREE_SCALES,
    barrier_scale: float = 0.20,
    min_micro_risk_atr: float = 0.8,
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Computes the 17x17 Cumulative-Barrier Role-Weighted 2D Cross-Scale Tensor RR^{Phi,eff}_{n, m}
    and its 2D separable pyramidal convolution (K = w (x) w^T, w = [0.25, 0.50, 0.25]).

    Mathematical Formulation:
    - Raw downward distance to scale m: V_m = max(0, (p0 - SMA_m) / ATR)
    - Barrier opacity weight at scale k: w_k = clip(phi_bar_k / barrier_scale, 0.0, 1.0)
      (If phi_bar_k <= 0, w_k = 0: broken floor is transparent;
       If phi_bar_k >= barrier_scale, w_k = 1: active bedrock floor blocks deeper void.)
    - Effective cumulative void to scale m:
      V^{Phi}_{eff}(m) = min_{k <= m, SMA_k < p0} [ w_k * V_k + (1 - w_k) * V_m ]
    - Effective ceiling risk at scale n:
      Risk^{Phi}(n) = max(min_micro_risk_atr, (BB_upper_n - p0) / ATR) * (1 + max(0, phi_bar_n))
    - Cross-Scale Tensor:
      RR^{Phi,eff}_{n, m} = V^{Phi}_{eff}(m) / Risk^{Phi}(n)  for m > n, else 0.0.
    """
    atr_safe = max(float(atr0), 1e-8)
    n_scales = len(scales)

    raw_voids = np.zeros(n_scales, dtype=float)
    weights = np.zeros(n_scales, dtype=float)
    risks = np.zeros(n_scales, dtype=float)
    is_below = np.zeros(n_scales, dtype=bool)

    for idx, s in enumerate(scales):
        sma_s = float(row_0.get(f"sma_{s}", p0))
        phi_s = float(row_0.get(f"phi_bar_{s}", 0.0))
        bb_up_s = float(row_0.get(f"bb_upper_{s}", sma_s + 2.0 * atr_safe))

        if sma_s < p0:
            is_below[idx] = True
            raw_voids[idx] = (p0 - sma_s) / atr_safe
        else:
            raw_voids[idx] = 0.0

        weights[idx] = np.clip(phi_s / max(barrier_scale, 1e-8), 0.0, 1.0)
        base_risk = max(min_micro_risk_atr, (bb_up_s - p0) / atr_safe)
        # Penalize entry scale n if scale n itself is strongly bullish/supportive
        risks[idx] = base_risk * (1.0 + max(0.0, phi_s))

    eff_voids = np.zeros(n_scales, dtype=float)
    for m_idx in range(n_scales):
        vm = raw_voids[m_idx]
        if vm <= 0.0:
            eff_voids[m_idx] = 0.0
            continue
        v_eff = vm
        for k_idx in range(m_idx + 1):
            if is_below[k_idx]:
                vk = raw_voids[k_idx]
                wk = weights[k_idx]
                candidate_v = wk * vk + (1.0 - wk) * vm
                if candidate_v < v_eff:
                    v_eff = candidate_v
        eff_voids[m_idx] = max(0.0, v_eff)

    rr_tensor = np.zeros((n_scales, n_scales), dtype=float)
    for n_idx in range(n_scales):
        for m_idx in range(n_idx + 1, n_scales):
            rr_tensor[n_idx, m_idx] = eff_voids[m_idx] / risks[n_idx]

    # 2D Separable Pyramidal Convolution: K = w (x) w^T
    rr_conv = convolve1d(rr_tensor, PYRAMID_KERNEL_1D, axis=0, mode="reflect")
    rr_conv = convolve1d(rr_conv, PYRAMID_KERNEL_1D, axis=1, mode="reflect")
    # Enforce upper-triangular causality after smoothing
    rr_conv = np.triu(rr_conv, k=1)

    # Operational macro box: n in S8..S55 (0..4), m in S55..S2584 (4..12)
    macro_rr_eff = float(np.max(rr_conv[0:5, 4:13]))
    return rr_tensor, rr_conv, macro_rr_eff


def evaluate_orthogonal_role_2d_short_gate(
    row_0: pd.Series | dict,
    macro_rr_eff: float,
    d_def_05: float,
    min_rr: float = 2.0,
    min_void_atr: float = 2.5,
    min_bb_exp: float = 0.0,
    max_curv_l1: float = 0.0,
) -> bool:
    """
    Evaluates the Orthogonal Role-Weighted 2D Tensor Short Gate:
    1. Spatial Defended Void Clearance: d_def_05 >= min_void_atr (2.5 ATR)
    2. Convolved 2D Cross-Scale RR: macro_rr_eff >= min_rr (2.0x)
    3. Volatility Non-Contraction (Natural Zero): bb_slope_exp_continuum_L3_L8 >= min_bb_exp (0.0)
    4. Short-Scale Curvature Rollover (Natural Zero): curv_L1_mean <= max_curv_l1 (0.0)
    """
    if d_def_05 < min_void_atr:
        return False
    if macro_rr_eff < min_rr:
        return False

    bb_exp = float(row_0.get("bb_slope_exp_continuum_L3_L8", 0.0))
    curv_l1 = float(row_0.get("curv_L1_mean", row_0.get("curv_L1", 0.0)))

    if bb_exp < min_bb_exp:
        return False
    if curv_l1 > max_curv_l1:
        return False

    return True


def compute_additive_portfolio_metrics(
    net_returns_decimal: list[float] | np.ndarray,
) -> dict[str, float | int]:
    """
    Computes project-standard strictly ADDITIVE portfolio metrics (zero compounding inflation).
    Each element in net_returns_decimal is a trade net return after 40 bps friction (e.g. +0.05 = +5%).
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
        print("EXP-135 Audited Summary Metrics:")
        print(json.dumps(data["production_master_stages"], indent=2))
