"""
EXP-145: Scale-Agnostic 11-Scale MTF Bollinger Band Dynamical State-Transition,
Dynamic Active-Scale k*(t) Derivation, WaitGuard Asymmetry & Cascade Exit.

Key Principles & Invariants:
1. Zero Fixed-Period Dependence: Models the 11-scale Fibonacci continuum
   S = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987] with scale-native
   lags `delta_k = max(2, int(round(0.15 * k)))` and strict full-window warmup.
2. Zero Window-Dressing & Zero External Data: `hardcoded_whitelist_count = 0`,
   100% pure OHLC price dynamics, strictly isolated to Discovery <= 2025-04-30.
3. Exact Hour-Boundary 1m Causality: Triggers 1h-level checks ONLY when
   `cur_hr = t_bar.floor("1h")` transitions (`cur_hr != prev_hr`), reading
   completed `t_1h = cur_hr - 1h` (never `k % 60 == 0` bar-count stepping).
4. Strict Additive Accounting: Sum of net trade returns after 40 bps RT friction
   (pro-rated on split exits), zero geometric compounding (`np.prod` prohibited).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np
import pandas as pd

FRICTION_RATE: float = 0.0040
SCALES: tuple[int, ...] = (8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987)


def scale_native_lag(k: int, ratio: float = 0.15) -> tuple[int, int]:
    """Return scale-native lookback lag (delta_k, fast_delta_k) for scale `k`."""
    dk = max(2, int(round(float(ratio) * int(k))))
    fdk = max(1, dk // 2)
    return dk, fdk


def compute_scale_native_bb_state_matrix(
    close: Sequence[float] | np.ndarray,
    high: Sequence[float] | np.ndarray,
    low: Sequence[float] | np.ndarray,
    atr: Sequence[float] | np.ndarray,
    sma_by_scale: Mapping[int, Sequence[float] | np.ndarray],
    bb_up_by_scale: Mapping[int, Sequence[float] | np.ndarray],
    bb_lo_by_scale: Mapping[int, Sequence[float] | np.ndarray],
    phi_by_scale: Mapping[int, Sequence[float] | np.ndarray] | None = None,
    scales: Sequence[int] = SCALES,
    lag_ratio: float = 0.15,
    enforce_full_warmup: bool = True,
) -> dict[str, Any]:
    """
    Strictly causal 100% scale-agnostic multi-scale BB state machine across `scales`.

    States per bar/scale:
      +3 UP_WALK, +2 TO_UPPER, +1 UP_WAIT_CONTRACT,
      -1 DN_WAIT_CONTRACT, -2 TO_LOWER, -3 DN_WALK, 0 WARMUP_NA.
    """
    cl = np.asarray(close, dtype=float)
    hi = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    at = np.asarray(atr, dtype=float)
    n = len(cl)
    if not (len(hi) == len(lo) == len(at) == n):
        raise ValueError("close, high, low, and atr arrays must have equal length")

    sc_tuple = tuple(int(s) for s in scales)
    m_cnt = len(sc_tuple)
    bar_idx = np.arange(n, dtype=int)
    atr_ok = np.isfinite(at) & (at > 1e-8)

    valid = np.zeros((n, m_cnt), dtype=bool)
    sma_mat = np.full((n, m_cnt), np.nan, dtype=float)
    std_mat = np.full((n, m_cnt), np.nan, dtype=float)
    bb_up_mat = np.full((n, m_cnt), np.nan, dtype=float)
    bb_lo_mat = np.full((n, m_cnt), np.nan, dtype=float)
    u_mat = np.full((n, m_cnt), np.nan, dtype=float)
    u_hi_mat = np.full((n, m_cnt), np.nan, dtype=float)
    u_lo_mat = np.full((n, m_cnt), np.nan, dtype=float)
    du_mat = np.full((n, m_cnt), np.nan, dtype=float)
    du_fast_mat = np.full((n, m_cnt), np.nan, dtype=float)
    exp_mat = np.full((n, m_cnt), np.nan, dtype=float)
    s_up_mat = np.full((n, m_cnt), np.nan, dtype=float)
    s_lo_mat = np.full((n, m_cnt), np.nan, dtype=float)
    sma_slp_mat = np.full((n, m_cnt), np.nan, dtype=float)
    phi_mat = np.full((n, m_cnt), np.nan, dtype=float)

    last_touch = np.zeros((n, m_cnt), dtype=np.int8)
    age_up = np.full((n, m_cnt), 1e9, dtype=float)
    age_lo = np.full((n, m_cnt), 1e9, dtype=float)
    sat_box = np.zeros((n, m_cnt), dtype=bool)
    sat_any = np.zeros((n, m_cnt), dtype=bool)
    wait_lo = np.zeros((n, m_cnt), dtype=bool)
    wait_up = np.zeros((n, m_cnt), dtype=bool)
    state = np.zeros((n, m_cnt), dtype=np.int8)

    delta_map: dict[int, int] = {}
    fast_delta_map: dict[int, int] = {}

    for m, k in enumerate(sc_tuple):
        dk, fdk = scale_native_lag(k, lag_ratio)
        delta_map[k] = dk
        fast_delta_map[k] = fdk

        sma_k = np.asarray(sma_by_scale[k], dtype=float)
        bb_up_k = np.asarray(bb_up_by_scale[k], dtype=float)
        bb_lo_k = np.asarray(bb_lo_by_scale[k], dtype=float)
        bb_w_k = bb_up_k - bb_lo_k
        std_k = bb_w_k / 4.0

        u_k = (cl - sma_k) / (2.0 * std_k + 1e-8)
        u_hi_k = (hi - sma_k) / (2.0 * std_k + 1e-8)
        u_lo_k = (lo - sma_k) / (2.0 * std_k + 1e-8)

        du_k = np.full(n, np.nan, dtype=float)
        du_fast_k = np.full(n, np.nan, dtype=float)
        e_k = np.full(n, np.nan, dtype=float)
        s_up_k = np.full(n, np.nan, dtype=float)
        s_lo_k = np.full(n, np.nan, dtype=float)
        slp_k = np.full(n, np.nan, dtype=float)

        if dk < n:
            du_k[dk:] = u_k[dk:] - u_k[:-dk]
            e_k[dk:] = (bb_w_k[dk:] - bb_w_k[:-dk]) / (bb_w_k[:-dk] + 1e-8)
            s_up_k[dk:] = (bb_up_k[dk:] - bb_up_k[:-dk]) / (std_k[dk:] + 1e-8)
            s_lo_k[dk:] = (bb_lo_k[dk:] - bb_lo_k[:-dk]) / (std_k[dk:] + 1e-8)
            slp_k[dk:] = (sma_k[dk:] - sma_k[:-dk]) / (at[dk:] * dk + 1e-8)
        if fdk < n:
            du_fast_k[fdk:] = u_k[fdk:] - u_k[:-fdk]

        warmup_ok = (bar_idx >= (k - 1 + dk)) if enforce_full_warmup else np.ones(n, dtype=bool)
        val_k = (
            warmup_ok
            & atr_ok
            & np.isfinite(sma_k)
            & np.isfinite(std_k)
            & (std_k > 1e-8)
            & np.isfinite(du_k)
            & np.isfinite(e_k)
        )

        if phi_by_scale is not None and k in phi_by_scale:
            phi_k = np.asarray(phi_by_scale[k], dtype=float)
        else:
            phi_k = np.tanh(8.0 * np.nan_to_num(slp_k, nan=0.0))

        # Causal extreme-touch tracker
        lt_arr = np.zeros(n, dtype=np.int8)
        au_arr = np.full(n, 1e9, dtype=float)
        al_arr = np.full(n, 1e9, dtype=float)
        last_u_idx = -1
        last_l_idx = -1
        cur_lt = 0
        for t in range(n):
            if not val_k[t]:
                continue
            hit_u = u_hi_k[t] >= 0.85
            hit_l = u_lo_k[t] <= -0.85
            if hit_u and hit_l:
                last_u_idx = t
                last_l_idx = t
                cur_lt = 1 if u_k[t] >= 0.0 else -1
            elif hit_u:
                last_u_idx = t
                cur_lt = 1
            elif hit_l:
                last_l_idx = t
                cur_lt = -1
            lt_arr[t] = cur_lt
            au_arr[t] = float(t - last_u_idx) if last_u_idx >= 0 else 1e9
            al_arr[t] = float(t - last_l_idx) if last_l_idx >= 0 else 1e9

        sb_k = val_k & (au_arr <= 1.25 * k) & (al_arr <= 1.25 * k)
        sa_k = val_k & (np.minimum(au_arr, al_arr) <= 0.5 * k)
        wl_k = val_k & (e_k < -0.01) & (s_lo_k > 0.0) & (u_k > -0.75) & (al_arr > 0.35 * k)
        wu_k = val_k & (e_k < -0.01) & (s_up_k < 0.0) & (u_k < 0.75) & (au_arr > 0.35 * k)

        st_k = np.zeros(n, dtype=np.int8)
        up_walk = val_k & (u_k >= 0.75) & ((e_k > 0.0) | (s_up_k > 0.05))
        dn_walk = val_k & (u_k <= -0.75) & ((e_k > 0.0) | (s_lo_k < -0.05))
        not_walk = val_k & (~up_walk) & (~dn_walk)
        up_wait = not_walk & (u_k >= 0.0) & (e_k <= -0.01)
        dn_wait = not_walk & (u_k < 0.0) & (e_k <= -0.01)
        rem = not_walk & (~up_wait) & (~dn_wait)

        hook_up = rem & (lt_arr == -1) & (du_fast_k > 0.0)
        hook_dn = rem & (lt_arr == 1) & (du_fast_k < 0.0)
        rem2 = rem & (~hook_up) & (~hook_dn)
        to_up = hook_up | (rem2 & ((du_k > 0.0) | ((lt_arr == -1) & (du_fast_k >= 0.0))))
        to_dn = hook_dn | (rem2 & (~to_up) & ((du_k < 0.0) | ((lt_arr == 1) & (du_fast_k <= 0.0))))
        rem3 = rem & (~to_up) & (~to_dn)
        tie_up = rem3 & ((du_fast_k > 0.0) | ((du_fast_k == 0.0) & (u_k >= 0.0)))
        tie_dn = rem3 & (~tie_up)

        st_k[up_walk] = 3
        st_k[dn_walk] = -3
        st_k[up_wait] = 1
        st_k[dn_wait] = -1
        st_k[to_up | tie_up] = 2
        st_k[to_dn | tie_dn] = -2

        valid[:, m] = val_k
        sma_mat[:, m] = sma_k
        std_mat[:, m] = std_k
        bb_up_mat[:, m] = bb_up_k
        bb_lo_mat[:, m] = bb_lo_k
        u_mat[:, m] = u_k
        u_hi_mat[:, m] = u_hi_k
        u_lo_mat[:, m] = u_lo_k
        du_mat[:, m] = du_k
        du_fast_mat[:, m] = du_fast_k
        exp_mat[:, m] = e_k
        s_up_mat[:, m] = s_up_k
        s_lo_mat[:, m] = s_lo_k
        sma_slp_mat[:, m] = slp_k
        phi_mat[:, m] = phi_k

        last_touch[:, m] = lt_arr
        age_up[:, m] = au_arr
        age_lo[:, m] = al_arr
        sat_box[:, m] = sb_k
        sat_any[:, m] = sa_k
        wait_lo[:, m] = wl_k
        wait_up[:, m] = wu_k
        state[:, m] = st_k

    return {
        "n": n,
        "scales": sc_tuple,
        "scale_to_m": {k: m for m, k in enumerate(sc_tuple)},
        "close": cl,
        "high": hi,
        "low": lo,
        "atr": at,
        "delta_map": delta_map,
        "fast_delta_map": fast_delta_map,
        "valid": valid,
        "sma_mat": sma_mat,
        "std_mat": std_mat,
        "bb_up_mat": bb_up_mat,
        "bb_lo_mat": bb_lo_mat,
        "u_mat": u_mat,
        "u_hi_mat": u_hi_mat,
        "u_lo_mat": u_lo_mat,
        "du_mat": du_mat,
        "du_fast_mat": du_fast_mat,
        "E_mat": exp_mat,
        "s_up_mat": s_up_mat,
        "s_lo_mat": s_lo_mat,
        "sma_slp_mat": sma_slp_mat,
        "phi_mat": phi_mat,
        "last_touch": last_touch,
        "age_up": age_up,
        "age_lo": age_lo,
        "sat_box": sat_box,
        "sat_any": sat_any,
        "wait_lo": wait_lo,
        "wait_up": wait_up,
        "state": state,
    }


def derive_dynamic_active_scale_and_range(state_mat: dict[str, Any]) -> dict[str, Any]:
    """
    Strictly causal bar-by-bar derivation of dynamic active scale k*(t),
    cross-scale pullback pairs (k+1 UP / k DOWN and k+1 DOWN / k UP),
    contraction wait-state trackers (k_wait_lo, k_wait_up), cascade depths,
    and dynamic active BB bounds [r_lo_dyn, r_hi_dyn] & [r_lo_dyn_pfloor, r_hi_dyn].
    """
    n = int(state_mat["n"])
    sc_tuple: tuple[int, ...] = state_mat["scales"]
    scale_to_m: dict[int, int] = state_mat["scale_to_m"]
    m_cnt = len(sc_tuple)

    valid = state_mat["valid"]
    state = state_mat["state"]
    sat_box = state_mat["sat_box"]
    wait_lo = state_mat["wait_lo"]
    wait_up = state_mat["wait_up"]
    u_mat = state_mat["u_mat"]
    phi_mat = state_mat["phi_mat"]
    sma_slp_mat = state_mat["sma_slp_mat"]
    sma_mat = state_mat["sma_mat"]
    std_mat = state_mat["std_mat"]
    bb_up_mat = state_mat["bb_up_mat"]
    bb_lo_mat = state_mat["bb_lo_mat"]
    close = state_mat["close"]
    atr = state_mat["atr"]

    k_box = np.zeros(n, dtype=int)
    k_wait_lo = np.zeros(n, dtype=int)
    d_wait_lo_std = np.full(n, np.nan, dtype=float)
    d_wait_lo_atr = np.full(n, np.nan, dtype=float)
    k_wait_up = np.zeros(n, dtype=int)
    d_wait_up_std = np.full(n, np.nan, dtype=float)
    d_wait_up_atr = np.full(n, np.nan, dtype=float)

    k_dn_depth = np.zeros(n, dtype=int)
    k_dn_frontier = np.zeros(n, dtype=int)
    k_up_depth = np.zeros(n, dtype=int)
    k_up_frontier = np.zeros(n, dtype=int)

    k_pb_dn = np.zeros(n, dtype=int)
    k_pb_dn_parent = np.zeros(n, dtype=int)
    k_pb_up = np.zeros(n, dtype=int)
    k_pb_up_parent = np.zeros(n, dtype=int)

    k_star = np.zeros(n, dtype=int)
    k_star_m = np.full(n, -1, dtype=int)
    k_star_reason = np.zeros(n, dtype=np.int8)
    r_lo_dyn = np.full(n, np.nan, dtype=float)
    r_hi_dyn = np.full(n, np.nan, dtype=float)
    r_lo_dyn_pfloor = np.full(n, np.nan, dtype=float)

    for t in range(n):
        if not valid[t, 0]:
            continue

        kb = 0
        for m in range(m_cnt):
            if valid[t, m] and sat_box[t, m] and (state[t, m] not in (3, -3)):
                kb = sc_tuple[m]
            else:
                break
        k_box[t] = kb

        for m in range(m_cnt):
            if valid[t, m] and sc_tuple[m] > kb and wait_lo[t, m]:
                k_wait_lo[t] = sc_tuple[m]
                d_wait_lo_std[t] = (close[t] - bb_lo_mat[t, m]) / (std_mat[t, m] + 1e-8)
                d_wait_lo_atr[t] = (close[t] - bb_lo_mat[t, m]) / (atr[t] + 1e-8)
                break
        for m in range(m_cnt):
            if valid[t, m] and sc_tuple[m] > kb and wait_up[t, m]:
                k_wait_up[t] = sc_tuple[m]
                d_wait_up_std[t] = (bb_up_mat[t, m] - close[t]) / (std_mat[t, m] + 1e-8)
                d_wait_up_atr[t] = (bb_up_mat[t, m] - close[t]) / (atr[t] + 1e-8)
                break

        dn_d, dn_f = 0, 0
        for m in range(m_cnt):
            if valid[t, m] and state[t, m] in (-2, -3):
                dn_d += 1
                dn_f = sc_tuple[m]
            else:
                break
        k_dn_depth[t] = dn_d
        k_dn_frontier[t] = dn_f

        up_d, up_f = 0, 0
        for m in range(m_cnt):
            if valid[t, m] and state[t, m] in (2, 3):
                up_d += 1
                up_f = sc_tuple[m]
            else:
                break
        k_up_depth[t] = up_d
        k_up_frontier[t] = up_f

        pb_dn_m = -1
        if 1 <= dn_d < m_cnt:
            mp = dn_d
            if valid[t, mp] and state[t, mp] in (1, 2, 3) and (phi_mat[t, mp] > 0.0 or sma_slp_mat[t, mp] > 0.0):
                pb_dn_m = dn_d - 1
                k_pb_dn[t] = sc_tuple[pb_dn_m]
                k_pb_dn_parent[t] = sc_tuple[mp]

        pb_up_m = -1
        if 1 <= up_d < m_cnt:
            mp = up_d
            if valid[t, mp] and state[t, mp] in (-1, -2, -3) and (phi_mat[t, mp] < 0.0 or sma_slp_mat[t, mp] < 0.0):
                pb_up_m = up_d - 1
                k_pb_up[t] = sc_tuple[pb_up_m]
                k_pb_up_parent[t] = sc_tuple[mp]

        chosen_m = -1
        reason = 0
        if pb_dn_m >= 0:
            chosen_m = pb_dn_m
            reason = 1
        elif pb_up_m >= 0:
            chosen_m = pb_up_m
            reason = 2
        elif (kb > 0) and (k_wait_lo[t] > 0 or k_wait_up[t] > 0):
            if k_wait_lo[t] > 0 and k_wait_up[t] > 0:
                chosen_m = scale_to_m[min(k_wait_lo[t], k_wait_up[t])]
            elif k_wait_lo[t] > 0:
                chosen_m = scale_to_m[k_wait_lo[t]]
            else:
                chosen_m = scale_to_m[k_wait_up[t]]
            reason = 3
        elif kb > 0:
            kb_m = scale_to_m[kb]
            for mc in range(kb_m + 1, m_cnt):
                if valid[t, mc]:
                    chosen_m = mc
                    reason = 4
                    break
            if chosen_m < 0:
                chosen_m = kb_m
                reason = 4
        else:
            walk_m = -1
            for m in range(m_cnt):
                if valid[t, m] and state[t, m] in (3, -3):
                    walk_m = m
                else:
                    break
            if walk_m >= 0:
                chosen_m = walk_m + 1 if (walk_m + 1 < m_cnt and valid[t, walk_m + 1]) else walk_m
            else:
                for m in range(min(1, m_cnt - 1), m_cnt):
                    if valid[t, m] and abs(u_mat[t, m]) < 0.90:
                        chosen_m = m
                        break
                if chosen_m < 0:
                    chosen_m = 1 if (m_cnt > 1 and valid[t, 1]) else 0
            reason = 5

        k_star_m[t] = chosen_m
        k_star[t] = sc_tuple[chosen_m]
        k_star_reason[t] = reason
        r_lo_dyn[t] = bb_lo_mat[t, chosen_m]
        r_hi_dyn[t] = bb_up_mat[t, chosen_m]

        if reason == 1 and chosen_m + 1 < m_cnt and valid[t, chosen_m + 1]:
            p_sma = sma_mat[t, chosen_m + 1]
            r_lo_dyn_pfloor[t] = (
                max(bb_lo_mat[t, chosen_m], p_sma)
                if (np.isfinite(p_sma) and p_sma < bb_up_mat[t, chosen_m])
                else bb_lo_mat[t, chosen_m]
            )
        else:
            r_lo_dyn_pfloor[t] = bb_lo_mat[t, chosen_m]

    out = dict(state_mat)
    out.update({
        "k_box": k_box,
        "k_wait_lo": k_wait_lo,
        "d_wait_lo_std": d_wait_lo_std,
        "d_wait_lo_atr": d_wait_lo_atr,
        "k_wait_up": k_wait_up,
        "d_wait_up_std": d_wait_up_std,
        "d_wait_up_atr": d_wait_up_atr,
        "k_dn_depth": k_dn_depth,
        "k_dn_frontier": k_dn_frontier,
        "k_up_depth": k_up_depth,
        "k_up_frontier": k_up_frontier,
        "k_pb_dn": k_pb_dn,
        "k_pb_dn_parent": k_pb_dn_parent,
        "k_pb_up": k_pb_up,
        "k_pb_up_parent": k_pb_up_parent,
        "k_star": k_star,
        "k_star_m": k_star_m,
        "k_star_reason": k_star_reason,
        "r_lo_dyn": r_lo_dyn,
        "r_hi_dyn": r_hi_dyn,
        "r_lo_dyn_pfloor": r_lo_dyn_pfloor,
    })
    return out


def detect_scale_free_pullback_hook(
    m_state: Mapping[str, Any],
    t: int,
    direction: str = "long",
    u_touch_thr: float = -0.70,
    phi_parent_thr: float = 0.10,
    min_k_star: int = 21,
) -> tuple[int, int]:
    """
    Strictly causal dynamic cross-scale pullback hook detector at bar `t`.
    Returns `(k_star_pb, k_parent)` or `(0, 0)` if no pair qualifies.
    """
    if t < 2:
        return 0, 0
    sc_tuple: Sequence[int] = m_state["scales"]
    m_cnt = len(sc_tuple)
    best_k, best_p = 0, 0
    side = direction.strip().lower()
    if side not in ("long", "short"):
        raise ValueError(f"Unsupported direction {direction!r}; expected 'long' or 'short'")

    for m in range(m_cnt - 1):
        k = int(sc_tuple[m])
        kp = int(sc_tuple[m + 1])
        if k < min_k_star:
            continue
        if not (m_state["valid"][t, m] and m_state["valid"][t, m + 1]):
            continue
        fdk = int(m_state["fast_delta_map"][k])
        if side == "long":
            par_ok = (m_state["state"][t, m + 1] in (1, 2, 3)) and (m_state["phi_mat"][t, m + 1] >= phi_parent_thr)
            if not par_ok:
                continue
            was_dn = (
                (m_state["state"][t, m] in (-1, -2, -3))
                or (m_state["state"][t - 1, m] in (-1, -2, -3))
                or (m_state["age_lo"][t, m] <= fdk)
            )
            at_lo = (m_state["u_lo_mat"][t, m] <= u_touch_thr) or (
                (m_state["age_lo"][t, m] <= 2) and (m_state["u_mat"][t, m] <= u_touch_thr + 0.35)
            )
            hook = (m_state["du_fast_mat"][t, m] > 0.0) and (m_state["u_mat"][t, m] < 0.15)
            if was_dn and at_lo and hook:
                best_k, best_p = k, kp
        else:
            par_ok = (m_state["state"][t, m + 1] in (-1, -2, -3)) and (m_state["phi_mat"][t, m + 1] <= -phi_parent_thr)
            if not par_ok:
                continue
            was_up = (
                (m_state["state"][t, m] in (1, 2, 3))
                or (m_state["state"][t - 1, m] in (1, 2, 3))
                or (m_state["age_up"][t, m] <= fdk)
            )
            at_hi = (m_state["u_hi_mat"][t, m] >= -u_touch_thr) or (
                (m_state["age_up"][t, m] <= 2) and (m_state["u_mat"][t, m] >= -u_touch_thr - 0.35)
            )
            hook = (m_state["du_fast_mat"][t, m] < 0.0) and (m_state["u_mat"][t, m] > -0.15)
            if was_up and at_hi and hook:
                best_k, best_p = k, kp
    return best_k, best_p


def evaluate_long_bb_wait_guard(
    k_pb: int,
    k_box: int,
    k_wait_lo: int,
    d_wait_lo_std: float,
    max_scale_gap: int = 2,
    d_std_thr: float = 0.50,
    scales: Sequence[int] = SCALES,
) -> bool:
    """
    Returns True when a pullback candidate is safe to take (NOT blocked by an un-met
    nearby outer Long-BB contraction wait state).
    Returns False when `k_wait_lo > k_pb`, `d_wait_lo_std > d_std_thr`, and either
    short-scale range saturation exists (`k_box > 0`) or `k_wait_lo` lies within
    `max_scale_gap` Fibonacci steps above `k_pb`.
    """
    if k_pb <= 0 or k_wait_lo <= k_pb:
        return True
    if not np.isfinite(float(d_wait_lo_std)) or float(d_wait_lo_std) <= float(d_std_thr):
        return True
    if k_box > 0:
        return False
    sc_tuple = tuple(int(s) for s in scales)
    smap = {s: idx for idx, s in enumerate(sc_tuple)}
    if k_wait_lo in smap and k_pb in smap and (smap[k_wait_lo] - smap[k_pb]) <= int(max_scale_gap):
        return False
    return True


def evaluate_scale_free_cascade_exit_signal(
    run_mfe_atr: float,
    active_anchor_ca: int,
    k_dn_depth: int,
    k_dn_frontier: int,
    phi_mid: float,
    state_at_ca: int,
    du_at_ca: float,
    is_ultra_bull: bool,
    d_thr: int = 4,
    phi_mid_thr: float = 0.25,
    mfe_thr: float = 4.0,
    require_not_ub: bool = True,
    require_ca_flip: bool = False,
) -> bool:
    """
    Causal decision function for EXP-145 dynamic cascade breakdown exit (HYP-145-2).
    """
    if float(run_mfe_atr) < float(mfe_thr):
        return False
    if bool(require_not_ub) and bool(is_ultra_bull):
        return False
    if not ((int(k_dn_depth) >= int(d_thr)) or (int(k_dn_frontier) >= int(active_anchor_ca))):
        return False
    if not np.isfinite(float(phi_mid)) or float(phi_mid) >= float(phi_mid_thr):
        return False
    if bool(require_ca_flip):
        return int(state_at_ca) in (-2, -3)
    return (int(state_at_ca) in (-1, -2, -3)) or (float(du_at_ca) < 0.0)


def simulate_causal_1m_cascade_exit(
    entry_price: float,
    atr0: float,
    timestamps_1m: Sequence[Any] | pd.DatetimeIndex,
    high_1m: Sequence[float] | np.ndarray,
    low_1m: Sequence[float] | np.ndarray,
    open_1m: Sequence[float] | np.ndarray,
    hourly_state_by_completed_1h: Mapping[pd.Timestamp, Mapping[str, Any]],
    mode: str = "full",
    orig_net_return: float | None = None,
    partial_w: float = 0.50,
    lock_frac: float = 0.50,
    d_thr: int = 4,
    phi_mid_thr: float = 0.25,
    mfe_thr: float = 4.0,
    require_not_ub: bool = True,
    require_ca_flip: bool = False,
    friction_rt: float = FRICTION_RATE,
) -> dict[str, Any]:
    """
    Strictly causal 1m cascade-exit simulator triggering ONLY at exact hour boundary
    changes (`cur_hr != prev_hr`) and reading ONLY the completed bar `t_1h = cur_hr - 1h`.
    """
    p0 = float(entry_price)
    a0 = max(float(atr0), 1e-8)
    ts = pd.DatetimeIndex(timestamps_1m)
    hi = np.asarray(high_1m, dtype=float)
    lo = np.asarray(low_1m, dtype=float)
    op = np.asarray(open_1m, dtype=float)
    if not (len(ts) == len(hi) == len(lo) == len(op)):
        raise ValueError("timestamps_1m, high_1m, low_1m, and open_1m must have equal length")

    run_m = 0.0
    prev_hr: pd.Timestamp | None = None
    trig_k: int | None = None
    trig_hr: pd.Timestamp | None = None
    trig_meta: Mapping[str, Any] | None = None
    trig_mfe0 = 0.0

    for k in range(len(ts)):
        run_m = max(run_m, (float(hi[k]) - p0) / a0)
        cur_hr = ts[k].floor("1h")
        if prev_hr is not None and cur_hr != prev_hr:
            t_1h = cur_hr - pd.Timedelta(hours=1)
            st_1h = hourly_state_by_completed_1h.get(t_1h)
            if st_1h is not None:
                fired = evaluate_scale_free_cascade_exit_signal(
                    run_mfe_atr=run_m,
                    active_anchor_ca=int(st_1h["ca"]),
                    k_dn_depth=int(st_1h["k_dn_depth"]),
                    k_dn_frontier=int(st_1h["k_dn_frontier"]),
                    phi_mid=float(st_1h["phi_mid"]),
                    state_at_ca=int(st_1h["state_at_ca"]),
                    du_at_ca=float(st_1h["du_at_ca"]),
                    is_ultra_bull=bool(st_1h["is_ultra_bull"]),
                    d_thr=d_thr,
                    phi_mid_thr=phi_mid_thr,
                    mfe_thr=mfe_thr,
                    require_not_ub=require_not_ub,
                    require_ca_flip=require_ca_flip,
                )
                if fired:
                    trig_k = k
                    trig_hr = cur_hr
                    trig_meta = st_1h
                    trig_mfe0 = run_m
                    break
        prev_hr = cur_hr

    if trig_k is None:
        return {"triggered": False, "mode": mode, "net_return": orig_net_return}

    if mode in ("full", "split50"):
        exit_px = float(op[trig_k])
        ret_early = (exit_px - p0) / p0 - float(friction_rt)
        if mode == "split50":
            if orig_net_return is None:
                raise ValueError("orig_net_return is required when mode='split50'")
            net_ret = float(partial_w) * ret_early + (1.0 - float(partial_w)) * float(orig_net_return)
            exit_reason = "cascade_exit_split50"
        else:
            net_ret = ret_early
            exit_reason = "cascade_exit_full"
        return {
            "triggered": True,
            "mode": mode,
            "exit_bar_index": int(trig_k),
            "exit_time": ts[trig_k],
            "completed_1h_bar": trig_hr - pd.Timedelta(hours=1),
            "exit_price": exit_px,
            "net_return": float(net_ret),
            "exit_reason": exit_reason,
            "trigger_state": dict(trig_meta),
        }

    if mode == "tighten":
        tight_stop = p0 + float(lock_frac) * trig_mfe0 * a0
        run_m = trig_mfe0
        cur_prev_hr = trig_hr
        for k in range(trig_k, len(ts)):
            run_m = max(run_m, (float(hi[k]) - p0) / a0)
            cur_hr = ts[k].floor("1h")
            if cur_hr != cur_prev_hr:
                tight_stop = max(tight_stop, p0 + float(lock_frac) * run_m * a0)
                cur_prev_hr = cur_hr
            if float(lo[k]) <= tight_stop:
                exit_px = min(float(op[k]), tight_stop)
                net_ret = (exit_px - p0) / p0 - float(friction_rt)
                return {
                    "triggered": True,
                    "mode": mode,
                    "exit_bar_index": int(k),
                    "exit_time": ts[k] + pd.Timedelta(minutes=1),
                    "completed_1h_bar": cur_hr - pd.Timedelta(hours=1),
                    "exit_price": float(exit_px),
                    "net_return": float(net_ret),
                    "exit_reason": f"cascade_tight_{int(round(lock_frac * 100))}",
                    "trigger_state": dict(trig_meta),
                }
        return {"triggered": False, "mode": mode, "net_return": orig_net_return}

    raise ValueError(f"Unsupported mode {mode!r}; expected 'full', 'split50', or 'tighten'")


def compute_additive_portfolio_metrics(
    net_returns_decimal: Sequence[float] | np.ndarray,
) -> dict[str, float | int]:
    """
    Computes strictly ADDITIVE portfolio metrics (zero compounding inflation).
    Each element in `net_returns_decimal` is net of 40 bps roundtrip friction.
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
        print("EXP-145 Scale-Free MTF BB State-Transition Summary:")
        print(json.dumps({
            "baseline_exp143_audited_std": data["baseline_exp143_audited"]["Std"],
            "champion_exp145_t1_cascade_exit_std": data["champion_exp145_t1_cascade_exit"]["Std"],
        }, indent=2, ensure_ascii=False))
