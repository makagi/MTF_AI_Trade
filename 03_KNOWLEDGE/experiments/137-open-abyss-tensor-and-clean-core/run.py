"""
EXP-137: Clean Core Plateau Audit (C1) & Role-Weighted Open-Abyss 2D Tensor
with Scale-Relative 8h Downward BB Expansion Short Rescue (S16).

Key Principles & Invariants:
1. Zero Window-Dressing: Zero hardcoded timestamp whitelists (MEGA_RUNNER_TIMESTAMPS = 0).
2. Strict Additive Net Return Accounting: sum(net_ret) * 100.0 with 40 bps roundtrip friction.
3. Clean Core (C1) Plateau-Audited Components:
   - H1a: Causal 1m Open-Sky friction-lock stop (MFE >= 4.5 ATR -> lock >= entry + 0.50 ATR).
   - H2a: Base0 counter-trend wall guard (reject phi_continuum < -0.05 and d_res_def_05 < 2.5 ATR).
   - H3a_clean: Unified Engine A floor clearance (d_def_05 >= 2.5 ATR).
   - H3b: Engine B non-bullish continuum guard (phi_continuum <= 0.0).
   - Rejected razor-edge thresholds: bb_L38 >= -0.018 and M1a-R1s (proj > 0.20).
4. Role-Weighted Open-Abyss 2D Tensor (Option 2, RR^{Phi,abyss}_{n, m}):
   - Fixes the macro_rr_2d == 0.00 zero-collapse when price drops below all SMAs in [55..2584].
   - Assigns 17-scale defended floor clearance d_def_05_17 (cap 15.0 ATR) to overhead scales
     m in [55..2584] when P < SMA_m, phi_bar_m < -0.15, and slope_m < 0.
5. Scale-Relative 8h Downward BB Expansion & 21h Non-Oversold Short Rescue (S16):
   - Unlocks early plunge ignitions inside macro BB coils and Open Abyss.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.ndimage import convolve1d

TREE_SCALES: list[int] = [
    8, 13, 21, 34, 55, 89, 144, 233, 377, 610,
    987, 1597, 2584, 4181, 6765, 10946, 17711,
]
PYRAMID_KERNEL_1D: np.ndarray = np.array([0.25, 0.50, 0.25], dtype=float)
FRICTION_RATE: float = 0.0040


def _get_finite(row_0: pd.Series | dict, key: str, default: float) -> float:
    """Safely extracts a float from row_0, returning default when missing or NaN."""
    val = row_0.get(key, default)
    if val is None or pd.isna(val):
        return float(default)
    return float(val)


def compute_cumulative_barrier_role_weighted_2d_tensor(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
    scales: list[int] = TREE_SCALES,
    barrier_scale: float = 0.20,
    min_micro_risk_atr: float = 0.80,
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    EXP-135 baseline Cumulative-Barrier Role-Weighted 2D Tensor RR^{Phi,eff}_{n, m}.
    Included as a baseline reference demonstrating zero-collapse when price is below [55..2584].
    """
    atr_safe = max(float(atr0), 1e-8)
    n_scales = len(scales)

    raw_voids = np.zeros(n_scales, dtype=float)
    weights = np.zeros(n_scales, dtype=float)
    risks = np.zeros(n_scales, dtype=float)
    is_below = np.zeros(n_scales, dtype=bool)

    for idx, s in enumerate(scales):
        sma_s = _get_finite(row_0, f"sma_{s}", p0)
        phi_s = _get_finite(row_0, f"phi_bar_{s}", 0.0)
        bb_up_s = _get_finite(row_0, f"bb_upper_{s}", sma_s + 2.0 * atr_safe)

        if sma_s < p0:
            is_below[idx] = True
            raw_voids[idx] = (p0 - sma_s) / atr_safe
        else:
            raw_voids[idx] = 0.0

        weights[idx] = np.clip(phi_s / max(barrier_scale, 1e-8), 0.0, 1.0)
        base_risk = max(min_micro_risk_atr, (bb_up_s - p0) / atr_safe)
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
                cand = wk * vk + (1.0 - wk) * vm
                if cand < v_eff:
                    v_eff = cand
        eff_voids[m_idx] = max(0.0, v_eff)

    rr_tensor = np.zeros((n_scales, n_scales), dtype=float)
    for n_idx in range(n_scales):
        for m_idx in range(n_idx + 1, n_scales):
            rr_tensor[n_idx, m_idx] = eff_voids[m_idx] / risks[n_idx]

    rr_conv = convolve1d(rr_tensor, PYRAMID_KERNEL_1D, axis=0, mode="reflect")
    rr_conv = convolve1d(rr_conv, PYRAMID_KERNEL_1D, axis=1, mode="reflect")
    rr_conv = np.triu(rr_conv, k=1)

    n_end = min(5, n_scales)
    m_start = min(4, n_scales - 1)
    m_end = min(13, n_scales)
    macro_rr_eff = float(np.max(rr_conv[0:n_end, m_start:m_end]))
    return rr_tensor, rr_conv, macro_rr_eff


def compute_open_abyss_role_weighted_2d_tensor(
    p0: float,
    atr0: float,
    row_0: pd.Series | dict,
    scales: list[int] = TREE_SCALES,
    barrier_scale: float = 0.20,
    min_micro_risk_atr: float = 0.80,
    max_abyss_cap_atr: float = 15.0,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """
    Computes the 17x17 Option-2 Role-Weighted Open-Abyss 2D Cross-Scale Tensor
    RR^{Phi,abyss}_{n, m}, its 2D separable pyramidal convolution, macro_rr_abyss,
    and 17-scale active defended floor clearance d_def_05_17.

    Fixes zero-collapse when price drops below all SMAs in [55..2584]:
    1. Scans all scales in [34..17711] below p0 with active support role (phi_bar_s > 0.05)
       to compute d_def_05_17 = min(max_abyss_cap_atr, min_dist_atr).
    2. For target scales m in [55..2584]:
       - If SMA_m < p0: uses cumulative-barrier effective downward void V^{Phi}_{eff}(m).
       - If SMA_m > p0 AND phi_bar_m < -0.15 AND slope_m < 0.0 (active bearish overhead regime):
         assigns Open-Abyss void V^{abyss}(m) = d_def_05_17.
       - Otherwise: 0.0.
    3. Role-weighted ceiling risk at entry scale n:
       Risk^{Phi}(n) = max(min_micro_risk_atr, (BB_upper_n - p0) / ATR)
                       * (1 + 2*phi_n if phi_n > 0.10 else 1 / (1 + 0.3 * clip(-phi_n, 0, 1)))
    4. Applies separable 2D pyramid convolution K = w (x) w^T and takes max over
       n in [8..55], m in [55..2584].
    """
    atr_safe = max(float(atr0), 1e-8)
    n_scales = len(scales)

    smas = np.full(n_scales, np.nan, dtype=float)
    phis = np.zeros(n_scales, dtype=float)
    slopes = np.zeros(n_scales, dtype=float)
    bb_uppers = np.zeros(n_scales, dtype=float)
    raw_voids = np.zeros(n_scales, dtype=float)
    is_below = np.zeros(n_scales, dtype=bool)
    weights = np.zeros(n_scales, dtype=float)
    risks = np.zeros(n_scales, dtype=float)

    defended_dists: list[float] = []

    for idx, s in enumerate(scales):
        raw_sma = row_0.get(f"sma_{s}", np.nan)
        sma_s = float(raw_sma) if raw_sma is not None and not pd.isna(raw_sma) else np.nan
        phi_s = _get_finite(row_0, f"phi_bar_{s}", 0.0)
        slope_s = _get_finite(row_0, f"slope_{s}", 0.0)
        default_bb = (sma_s if np.isfinite(sma_s) else p0) + 2.0 * atr_safe
        bb_up_s = _get_finite(row_0, f"bb_upper_{s}", default_bb)

        smas[idx] = sma_s
        phis[idx] = phi_s
        slopes[idx] = slope_s
        bb_uppers[idx] = bb_up_s

        if np.isfinite(sma_s) and sma_s < p0:
            is_below[idx] = True
            dist_atr = (p0 - sma_s) / atr_safe
            raw_voids[idx] = dist_atr
            if s >= 34 and phi_s > 0.05:
                defended_dists.append(dist_atr)

        weights[idx] = float(np.clip(phi_s / max(barrier_scale, 1e-8), 0.0, 1.0))
        base_risk = max(float(min_micro_risk_atr), (bb_up_s - p0) / atr_safe)
        if phi_s > 0.10:
            risk_mult = 1.0 + 2.0 * phi_s
        else:
            risk_mult = 1.0 / (1.0 + 0.3 * float(np.clip(-phi_s, 0.0, 1.0)))
        risks[idx] = base_risk * risk_mult

    d_def_05_17 = float(min(max_abyss_cap_atr, min(defended_dists))) if defended_dists else float(max_abyss_cap_atr)

    voids_eff = np.zeros(n_scales, dtype=float)
    for m_idx, s_m in enumerate(scales):
        sma_m = smas[m_idx]
        if not np.isfinite(sma_m):
            continue
        if sma_m < p0:
            vm = raw_voids[m_idx]
            v_eff = vm
            for k_idx in range(m_idx + 1):
                if scales[k_idx] >= 34 and is_below[k_idx]:
                    wk = weights[k_idx]
                    cand = wk * raw_voids[k_idx] + (1.0 - wk) * vm
                    if cand < v_eff:
                        v_eff = cand
            voids_eff[m_idx] = max(0.0, v_eff)
        elif 55 <= s_m <= 2584 and sma_m > p0 and phis[m_idx] < -0.15 and slopes[m_idx] < 0.0:
            voids_eff[m_idx] = d_def_05_17

    rr_tensor = voids_eff[None, :] / risks[:, None]
    rr_conv = convolve1d(rr_tensor, PYRAMID_KERNEL_1D, axis=0, mode="reflect")
    rr_conv = convolve1d(rr_conv, PYRAMID_KERNEL_1D, axis=1, mode="reflect")

    n_indices = [i for i, s in enumerate(scales) if s <= 55] or list(range(min(5, n_scales)))
    m_indices = [i for i, s in enumerate(scales) if 55 <= s <= 2584] or list(range(min(4, n_scales), min(13, n_scales)))
    macro_rr_abyss = float(np.max(rr_conv[np.ix_(n_indices, m_indices)]))
    return rr_tensor, rr_conv, macro_rr_abyss, d_def_05_17


def evaluate_scale_relative_downward_bb_short_rescue_gate(
    row_0: pd.Series | dict,
    macro_rr_abyss: float,
    d_def_05_17: float,
    min_rr_abyss: float = 2.0,
    min_d_def_05_17: float = 4.0,
    min_bb_exp_8: float = 0.0,
    min_stoch_z_21: float = -0.30,
    max_ceil_dphi_3h: float = 0.0,
    max_phi_continuum: float = 0.15,
) -> bool:
    """
    Evaluates the EXP-137 S16 Short Rescue Gate for early-ignition plunges inside
    Open Abyss or macro BB coils:
    1. Open-Abyss Role-Weighted 2D Tensor: macro_rr_abyss >= 2.0
    2. 17-Scale Defended Floor Void: d_def_05_17 >= 4.0 ATR
    3. Shortest-Scale 8h Downward BB Expansion: bb_slope_exp_8 > 0.0
    4. 21h Non-Oversold Early-Ignition Guard: stoch_z_21 >= -0.30
    5. Non-Eroding Overhead Ceiling: ceil_dphi3h <= 0.0
    6. Bearish/Neutral Continuum: phi_continuum <= 0.15
    """
    if macro_rr_abyss < min_rr_abyss:
        return False
    if d_def_05_17 < min_d_def_05_17:
        return False

    bb_exp_8 = row_0.get("bb_slope_exp_8", row_0.get("bb_exp_8", 0.0))
    bb_exp_8_f = 0.0 if bb_exp_8 is None or pd.isna(bb_exp_8) else float(bb_exp_8)
    if bb_exp_8_f <= min_bb_exp_8:
        return False

    stoch_z_21 = _get_finite(row_0, "stoch_z_21", -999.0)
    if stoch_z_21 < min_stoch_z_21:
        return False

    ceil_dphi3h = _get_finite(row_0, "ceil_dphi3h", +999.0)
    if ceil_dphi3h > max_ceil_dphi_3h:
        return False

    phi_cont = _get_finite(row_0, "phi_continuum", +999.0)
    if phi_cont > max_phi_continuum:
        return False

    return True


def evaluate_clean_core_base0_wall_guard(
    row_0: pd.Series | dict,
    d_res_def_05: float,
    phi_continuum_lt: float = -0.05,
    min_d_res_atr: float = 2.5,
) -> bool:
    """
    Evaluates Clean Core H2a Base0 counter-trend overhead wall guard:
    Blocks Base0 longs only when overall continuum is bearish (phi_continuum < -0.05)
    AND an active defended overhead resistance wall sits within 2.5 ATR (d_res_def_05 < 2.5).
    Returns True if entry is permitted, False if blocked.
    """
    phi_cont = _get_finite(row_0, "phi_continuum", 0.0)
    return not (phi_cont < phi_continuum_lt and float(d_res_def_05) < min_d_res_atr)


def compute_causal_1m_open_sky_friction_lock_stop(
    entry_price: float,
    atr0: float,
    running_mfe_atr: float,
    current_stop_price: float,
    mfe_trigger_atr: float = 4.5,
    lock_offset_atr: float = 0.50,
) -> float:
    """
    Evaluates Clean Core H1a causal 1m Open-Sky friction-clear profit lock for longs:
    Once causal running MFE reaches >= 4.5 ATR, raises stop floor to at least
    entry_price + 0.50 * atr0 (clearing 40 bps round-trip friction) without ever
    lowering an existing higher stop.
    """
    if float(running_mfe_atr) >= float(mfe_trigger_atr):
        atr_safe = max(float(atr0), 1e-8)
        locked_floor = float(entry_price) + float(lock_offset_atr) * atr_safe
        return float(max(float(current_stop_price), locked_floor))
    return float(current_stop_price)


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
        print("EXP-137 Audited Summary Metrics:")
        print(json.dumps(data["portfolio_comparison"], indent=2))
