"""
EXP-143: Pre-Ignition Floor Guard, Wave-Distinct Pyramiding, Scale-Free 1m Continuum
& Opposite-Slope Intersection Ceiling Apex Prediction (Forensically Audited).

Key Principles & Invariants:
1. Zero Window-Dressing: Zero hardcoded timestamp whitelists (hardcoded_whitelist_count = 0).
2. Zero External Data: 100% pure price (OHLC) multi-scale geometry.
3. Strict Causal Execution:
   - Opposite-slope velocities use backward 3h differences only.
   - Track 1 slices strictly `[entry_time : exit_time - 1m]` and exits at conservative `min(open_k, stop_px)`
     with `exit_time = ts_k + 1m` propagated to slot management.
   - Track 2 measures open position `running_MFE` strictly over completed 1m bars `<= t_new - 1m`.
   - Track 3a/3b use only `<= t0 + 59m` causal 1m/1h features with natural scale-free boundaries.
4. Strict Additive Net Return Accounting: sum(net_ret) * 100.0 with 40 bps roundtrip friction.
5. Core EXP-143 Functional Primitives (building on EXP-141):
   - compute_opposite_slope_overhead_ceiling_apex
   - evaluate_false_static_headroom_roof_guard
   - simulate_causal_1m_preignition_floor_guard
   - evaluate_causal_wave_distinct_pyramiding_guard
   - evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np
import pandas as pd

FRICTION_RATE: float = 0.0040


def _all_finite(*values: float) -> bool:
    """Returns True when every numeric argument is finite."""
    return all(np.isfinite(float(v)) for v in values)


def compute_opposite_slope_overhead_ceiling_apex(
    p0: float,
    atr0: float,
    l_low: float,
    v_low_per_hour: float,
    l_high: float,
    v_high_per_hour: float,
    min_overhead_atr: float = 0.50,
    min_vel_atr: float = 0.005,
    max_horizon_hours: float = 48.0,
    min_apex_atr: float = 0.25,
) -> tuple[bool, float, float, float]:
    """
    Computes the kinematic future intersection (tau*, P*, H*) between a rising
    short-scale line L_low (v_low > min_vel_atr) and a strictly overhead descending
    resistance line L_high > P0 + min_overhead_atr * ATR0 (v_high < -min_vel_atr).

    Returns:
        (is_valid_collision, tau_star_hours, p_star_price, h_star_atr)
    """
    if not _all_finite(p0, atr0, l_low, v_low_per_hour, l_high, v_high_per_hour):
        return (False, float("nan"), float("nan"), float("nan"))

    p0_f = float(p0)
    atr_f = float(atr0)
    if atr_f <= 0.0:
        return (False, float("nan"), float("nan"), float("nan"))

    l_lo = float(l_low)
    v_lo = float(v_low_per_hour)
    l_hi = float(l_high)
    v_hi = float(v_high_per_hour)

    # Strictly overhead descending roof prevents below-price golden crosses from masquerading as ceilings
    overhead_atr = (l_hi - p0_f) / atr_f
    gap_atr = (l_hi - l_lo) / atr_f
    if (
        overhead_atr <= float(min_overhead_atr)
        or gap_atr <= 0.0
        or v_lo <= float(min_vel_atr)
        or v_hi >= -float(min_vel_atr)
    ):
        return (False, float("nan"), float("nan"), float("nan"))

    v_rel = v_lo - v_hi
    if v_rel <= 1e-12:
        return (False, float("nan"), float("nan"), float("nan"))

    tau_star_hours = gap_atr / v_rel
    p_star_price = l_lo + v_lo * atr_f * tau_star_hours
    h_star_atr = (p_star_price - p0_f) / atr_f

    is_valid_collision = bool(
        (0.0 < tau_star_hours <= float(max_horizon_hours))
        and (h_star_atr > float(min_apex_atr))
    )
    return (
        is_valid_collision,
        float(tau_star_hours),
        float(p_star_price),
        float(h_star_atr),
    )


def evaluate_false_static_headroom_roof_guard(
    d_res_def_05: float,
    is_valid_collision: bool,
    tau_star_hours: float,
    h_star_atr: float,
    min_static_atr: float = 2.0,
    max_collision_tau_hours: float = 36.0,
    min_apex_headroom_atr: float = 2.0,
) -> bool:
    """
    Evaluates the Long False-Static Headroom Roof Guard.
    Returns False (blocks entry) ONLY when static resistance looks spacious
    (d_res_def_05 >= 2.0 ATR), yet an overhead opposite-slope Type-1 collision is
    imminent (0 < tau* <= 36h) with cramped effective apex headroom (H* < 2.0 ATR).
    """
    if not bool(is_valid_collision):
        return True
    if not _all_finite(d_res_def_05, tau_star_hours, h_star_atr):
        return True

    is_false_static_trap = (
        float(d_res_def_05) >= float(min_static_atr)
        and 0.0 < float(tau_star_hours) <= float(max_collision_tau_hours)
        and float(h_star_atr) < float(min_apex_headroom_atr)
    )
    return not is_false_static_trap


def simulate_causal_1m_preignition_floor_guard(
    entry_price: float,
    atr0: float,
    high_1m: Sequence[float] | np.ndarray,
    low_1m: Sequence[float] | np.ndarray,
    open_1m: Sequence[float] | np.ndarray,
    mfe_ignition_atr: float = 1.50,
    cap_atr: float = 3.25,
    cap_pct: float = 0.043,
    use_and_condition: bool = True,
    friction_rt: float = FRICTION_RATE,
) -> dict[str, Any]:
    """
    Forensically audited causal 1m simulation of Track 1 (Pre-Ignition Floor Guard).
    Evaluates strictly completed bars prior to exit (`[entry_time .. exit_time - 1m]`):
      - If `running_MFE < mfe_ignition_atr` at bar open and `low_1m[k] <= stop_px`,
        exits at conservative `min(open_1m[k], stop_px)` minus `friction_rt`.
      - Once `running_MFE >= mfe_ignition_atr` is reached, the guard permanently disarms.
      - `use_and_condition=True` requires breaching BOTH `cap_atr` and `cap_pct`
        (`stop_px = min(px_atr, px_pct)`).
    """
    p0 = float(entry_price)
    a0 = max(float(atr0), 1e-8)
    hi = np.asarray(high_1m, dtype=float)
    lo = np.asarray(low_1m, dtype=float)
    op = np.asarray(open_1m, dtype=float)
    if not (len(hi) == len(lo) == len(op)):
        raise ValueError("high_1m, low_1m, and open_1m must have equal lengths")

    px_atr = p0 - float(cap_atr) * a0
    px_pct = p0 * (1.0 - float(cap_pct))
    stop_px = float(min(px_atr, px_pct) if use_and_condition else max(px_atr, px_pct))

    run_mfe = 0.0
    for k in range(len(hi)):
        if run_mfe < float(mfe_ignition_atr) and float(lo[k]) <= stop_px:
            exit_px = min(float(op[k]), stop_px)
            net_ret = (exit_px - p0) / p0 - float(friction_rt)
            return {
                "triggered": True,
                "exit_bar_index": int(k),
                "exit_price": float(exit_px),
                "net_return": float(net_ret),
                "stop_price": stop_px,
                "max_preignition_mfe_atr": float(run_mfe),
                "ignited": False,
            }
        run_mfe = max(run_mfe, (float(hi[k]) - p0) / a0)
        if run_mfe >= float(mfe_ignition_atr):
            return {
                "triggered": False,
                "exit_bar_index": None,
                "exit_price": None,
                "net_return": None,
                "stop_price": stop_px,
                "max_preignition_mfe_atr": float(run_mfe),
                "ignited": True,
            }

    return {
        "triggered": False,
        "exit_bar_index": None,
        "exit_price": None,
        "net_return": None,
        "stop_price": stop_px,
        "max_preignition_mfe_atr": float(run_mfe),
        "ignited": False,
    }


def evaluate_causal_wave_distinct_pyramiding_guard(
    candidate_entry_time: Any,
    open_positions: Sequence[Mapping[str, Any]],
    min_open_mfe_atr: float = 2.0,
    min_wave_dt_hours: float = 24.0,
    candidate_side: str | None = None,
) -> bool:
    """
    Evaluates Track 2 (Causal Wave-Distinct Pyramiding Guard).
    When active same-side positions are open at `candidate_entry_time` (positions whose
    `exit_time` is strictly after `candidate_entry_time`, or omitted), requires EVERY
    active same-side position to have either:
      - strictly causal `running_mfe_at_candidate_entry >= min_open_mfe_atr` (2.0 ATR), OR
      - temporal wave separation `(candidate_entry_time - pos.entry_time) >= min_wave_dt_hours` (24h).
    """
    t_cand = pd.Timestamp(candidate_entry_time)
    for pos in open_positions:
        if candidate_side is not None and "side" in pos and pos["side"] != candidate_side:
            continue
        if "exit_time" in pos and pos["exit_time"] is not None:
            if pd.Timestamp(pos["exit_time"]) <= t_cand:
                continue

        t_open = pd.Timestamp(pos["entry_time"])
        dt_hours = (t_cand - t_open).total_seconds() / 3600.0
        causal_mfe = float(
            pos.get(
                "running_mfe_at_candidate_entry",
                pos.get("causal_running_mfe_atr", pos.get("running_mfe_atr", 0.0)),
            )
        )
        if not np.isfinite(causal_mfe):
            causal_mfe = 0.0
        if not ((causal_mfe >= float(min_open_mfe_atr)) or (dt_hours >= float(min_wave_dt_hours))):
            return False
    return True


def evaluate_scale_free_1m_continuum_and_weak_macro_coherence_gate(
    direction: str,
    sf1m_triad_mean_norm: float,
    sf1m_bb_exp_conv: float,
    sf1m_rho_pk_mean: float,
    phi_continuum: float,
    r_1h_local: float,
    triad_thr: float = 2.5,
    bb_exp_thr: float = 0.0,
    short_rho_thr: float = 2.0,
    weak_macro_phi_thr: float = 0.20,
    weak_macro_r1h_thr: float = 0.70,
) -> bool:
    """
    Evaluates Forensically Audited Track 3a (Scale-Free 1m Continuum with sqrt(b/55.0)
    normalization and natural 0.0 / 2.0 boundaries) + Track 3b (Weak-Macro Coherence Gate).
      - Long:
          * Rejects Track 3a exhaustion: `(sf1m_triad_mean_norm > 2.5) and (sf1m_bb_exp_conv <= 0.0)`
          * Rejects Track 3b weak-macro incoherence: `(phi_continuum < 0.20) and (r_1h_local < 0.70)`
      - Short:
          * Rejects Track 3a climax resonance drift: `sf1m_rho_pk_mean > 2.0`
            (Weak-macro Long filter does not block Shorts.)
    """
    side = direction.strip().lower()
    if side == "long":
        if not _all_finite(sf1m_triad_mean_norm, sf1m_bb_exp_conv, phi_continuum, r_1h_local):
            return False
        is_sf1m_exhausted = (
            float(sf1m_triad_mean_norm) > float(triad_thr)
            and float(sf1m_bb_exp_conv) <= float(bb_exp_thr)
        )
        is_weak_macro_incoherent = (
            float(phi_continuum) < float(weak_macro_phi_thr)
            and float(r_1h_local) < float(weak_macro_r1h_thr)
        )
        return not (is_sf1m_exhausted or is_weak_macro_incoherent)

    if side == "short":
        if not np.isfinite(float(sf1m_rho_pk_mean)):
            return False
        return bool(float(sf1m_rho_pk_mean) <= float(short_rho_thr))

    raise ValueError(f"Unsupported direction: {direction!r}. Expected 'long' or 'short'.")


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
        print("EXP-143 Forensically Audited Portfolio Ablation Progression:")
        print(json.dumps(data["portfolio_ablation_progression"], indent=2))
