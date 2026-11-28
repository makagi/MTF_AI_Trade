"""
EXP-156: ZLEMA-Native 4-Phase Reconstruction Program & Purified Track Z-B1 Independent Sleeve
=============================================================================================

Canonical Pure-ZLEMA engine implementing:
1. Exact MQL5 Zero-Lag EMA (`BufferEMAZL`) over the 17-scale Fibonacci continuum [8..17711]
   with strict full-window warmup (`bar_idx >= period + lag`, `lag = (period - 1) // 2`).
2. Adjacent 3-scale triplet geometry (`T1..T5`, 6 states: `PO_UP_EXPAND`, `PO_UP_COMPRESS`,
   `LEAD_PULLBACK_BULL`, `LEAD_TURN_BEAR`, `TANGLED_CHOP`, `PO_DN_CASCADE`).
3. NaN-aware 17-scale recursive triad pyramid convolution (`L0 -> L1 -> ... -> L8`) for:
   - Role Pyramid `Phi^Z` (exact Dual Sign-Flip Odd Symmetry: Phi^Z(-P) = -Phi^Z(P))
   - Curvature Pyramid `Curv^Z` (Odd Symmetry)
   - Residual Volatility Expansion Pyramid `Exp^Z` (Even Symmetry: Exp^Z(-P) = +Exp^Z(P))
   - Dynamic active period `k*_Z(t)` and causal `Z-BB` WaitGuard / Self-Overshoot (`N_ov_exhaust_Z`).
4. Causal Track Z-B1 purified entry mask (`L5`/`L7`) & `OR` pre-ignition invalidation helper.
5. Zero-Lookahead & Dual Sign-Flip invariance audit + SPEC-EVAL-001 strictly additive accounting.
"""

from __future__ import annotations

from typing import Sequence
import numpy as np
import pandas as pd

FRICTION_RATE: float = 0.0040
SCALES_17: tuple[int, ...] = (
    8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711,
)
SCALES_15_INT: tuple[int, ...] = SCALES_17[1:-1]  # 13..10946
SCALES_ACT: tuple[int, ...] = (13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584)
LAYER_WEIGHTS: tuple[float, ...] = (0.35, 0.25, 0.15, 0.10, 0.06, 0.04, 0.03, 0.02)
TRIPLETS_5: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("T1", (21, 55, 144)),
    ("T2", (55, 144, 377)),
    ("T3", (144, 377, 987)),
    ("T4", (377, 987, 2584)),
    ("T5", (987, 2584, 6765)),
)
Z_ANCHORS: tuple[int, ...] = (55, 89, 144, 233, 377)
Z_ANCHOR_NEXT: dict[int, int] = {55: 89, 89: 144, 144: 233, 233: 377}
Z_PROMO_MFE_ATR: dict[int, float] = {55: 3.0, 89: 6.0, 144: 10.0, 233: 16.0}

S17_TO_I: dict[int, int] = {s: i for i, s in enumerate(SCALES_17)}
INT_TO_I: dict[int, int] = {s: i for i, s in enumerate(SCALES_15_INT)}

ZST_WARM: int = 0
ZST_UP_WALK: int = 1
ZST_DN_WALK: int = 2
ZST_SELF_OV: int = 3
ZST_BULL_PB: int = 4
ZST_BEAR_PB: int = 5
ZST_SQZ_BOX: int = 6
ZST_TRANS: int = 7


def zlema_params(period: int) -> tuple[int, float, int]:
    """Return MQL5 ZLEMA `(lag, alpha, warmup_end_idx)` for integer `period >= 1`."""
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
    Exact chronological equivalent of MQL5 `BufferEMAZL` with `BufferMA = Close`:
        BufferEMAZL[t] = alpha * (2*x[t] - x[t-lag]) + (1-alpha) * BufferEMAZL[t-1]
    Strict full-window warmup masks indices `< period + lag` to `np.nan`.
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

    prev = 0.0 if init_zero else (float(x[start - 1]) if np.isfinite(x[start - 1]) else float(x[start]))
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


def _convolve_triad_step(
    mat: np.ndarray,
    weights: tuple[float, float, float],
    min_w: float = 0.50,
) -> np.ndarray:
    """NaN-aware 3-node spatial triad convolution preserving linear odd/even symmetry."""
    w0, w1, w2 = weights
    a, b, c = mat[:, :-2], mat[:, 1:-1], mat[:, 2:]
    fa, fb, fc = np.isfinite(a), np.isfinite(b), np.isfinite(c)
    a0 = np.where(fa, a, 0.0)
    b0 = np.where(fb, b, 0.0)
    c0 = np.where(fc, c, 0.0)
    w_sum = w0 * fa + w1 * fb + w2 * fc
    val_num = w0 * a0 + w1 * b0 + w2 * c0
    valid = w_sum >= (min_w - 1e-12)
    return np.where(valid, val_num / np.where(valid, w_sum, 1.0), np.nan)


def compute_zlema_triplets(
    zl_mat: np.ndarray,
    vel_mat: np.ndarray,
    atr: np.ndarray,
) -> dict[str, np.ndarray]:
    """
    Classify adjacent 3-scale triplets T1..T5 into 6 mutually exclusive geometric states:
    `PO_UP_EXPAND`, `PO_UP_COMPRESS`, `LEAD_PULLBACK_BULL`, `LEAD_TURN_BEAR`,
    `TANGLED_CHOP`, `PO_DN_CASCADE` (or `WARMUP`).
    """
    n = zl_mat.shape[0]
    atr_v = np.isfinite(atr) & (atr > 1e-8)
    out: dict[str, np.ndarray] = {}

    for tname, (k1, k2, k3) in TRIPLETS_5:
        i1, i2, i3 = S17_TO_I[k1], S17_TO_I[k2], S17_TO_I[k3]
        dk2 = max(2, int(round(0.15 * k2)))
        z1, z2, z3 = zl_mat[:, i1], zl_mat[:, i2], zl_mat[:, i3]
        v1, v2, v3 = vel_mat[:, i1], vel_mat[:, i2], vel_mat[:, i3]

        jv = (
            atr_v
            & np.isfinite(z1) & np.isfinite(z2) & np.isfinite(z3)
            & np.isfinite(v1) & np.isfinite(v2) & np.isfinite(v3)
        )
        sp = np.full(n, np.nan, dtype=float)
        if jv.any():
            z_max = np.maximum(np.maximum(z1[jv], z2[jv]), z3[jv])
            z_min = np.minimum(np.minimum(z1[jv], z2[jv]), z3[jv])
            sp[jv] = (z_max - z_min) / atr[jv]

        st = np.full(n, "WARMUP", dtype=object)
        jv_prev = np.zeros(n, dtype=bool)
        sp_prev = np.full(n, np.nan, dtype=float)
        jv_prev[dk2:] = jv[:-dk2]
        sp_prev[dk2:] = sp[:-dk2]
        valid = jv & jv_prev

        po_up = valid & (z1 > z2) & (z2 > z3) & (v2 > 0.0) & (v3 > 0.0)
        po_up_exp = po_up & (v1 > 0.0) & (sp >= sp_prev)
        po_up_cmp = po_up & (~po_up_exp)
        po_dn = valid & (~po_up) & (z1 < z2) & (z2 < z3) & (v1 < 0.0) & (v2 < 0.0) & (v3 < 0.0)
        pb_bull = valid & (~po_up) & (~po_dn) & (z2 > z3) & (v3 > 0.0) & ((z1 <= z2) | (v1 <= 0.0))
        trn_bear = valid & (~po_up) & (~po_dn) & (~pb_bull) & (z2 < z3) & (v3 < 0.0) & ((z1 >= z2) | (v1 >= 0.0))

        st = np.where(valid, "TANGLED_CHOP", st)
        st = np.where(trn_bear, "LEAD_TURN_BEAR", st)
        st = np.where(pb_bull, "LEAD_PULLBACK_BULL", st)
        st = np.where(po_dn, "PO_DN_CASCADE", st)
        st = np.where(po_up_cmp, "PO_UP_COMPRESS", st)
        st = np.where(po_up_exp, "PO_UP_EXPAND", st)
        out[tname] = st
    return out


def compute_zlema_pyramid_system(
    close: Sequence[float] | np.ndarray,
    high: Sequence[float] | np.ndarray,
    low: Sequence[float] | np.ndarray,
    atr: Sequence[float] | np.ndarray,
) -> dict:
    """
    Build strictly causal 17-scale Pure-ZLEMA kinematics, residual RMS envelopes (Z-BB),
    3 recursive hierarchical pyramids (Phi^Z, Curv^Z, Exp^Z over L0..L8), and dynamic k*_Z(t).
    """
    c_arr = np.asarray(close, dtype=float)
    l_arr = np.asarray(low, dtype=float)
    a_arr = np.asarray(atr, dtype=float)
    n = len(c_arr)
    n17 = len(SCALES_17)
    n_int = len(SCALES_15_INT)
    atr_v = np.isfinite(a_arr) & (a_arr > 1e-8)

    zl_mat = np.full((n, n17), np.nan, dtype=float)
    vel_mat = np.full((n, n17), np.nan, dtype=float)
    acc_mat = np.full((n, n17), np.nan, dtype=float)
    sig_mat = np.full((n, n17), np.nan, dtype=float)
    uz_mat = np.full((n, n17), np.nan, dtype=float)
    exp_mat = np.full((n, n17), np.nan, dtype=float)
    curv_l0 = np.full((n, n17), np.nan, dtype=float)
    exp_l0 = np.full((n, n17), np.nan, dtype=float)
    dk_arr = np.zeros(n17, dtype=int)

    for idx_s, s in enumerate(SCALES_17):
        dk = max(2, int(round(0.15 * s)))
        dk_arr[idx_s] = dk

        z = compute_mql5_zlema(c_arr, s, init_zero=True, enforce_full_warmup=True)
        v = np.full(n, np.nan, dtype=float)
        v[dk:] = z[dk:] - z[:-dk]
        ac = np.full(n, np.nan, dtype=float)
        ac[2 * dk :] = v[2 * dk :] - v[dk:-dk]

        res = c_arr - z
        rms_sq = pd.Series(res * res).ewm(span=s, min_periods=min(s, 144), adjust=False).mean().to_numpy(dtype=float)
        sig = np.where(np.isfinite(z) & np.isfinite(rms_sq), np.sqrt(np.maximum(rms_sq, 0.0)), np.nan)

        ez = np.full(n, np.nan, dtype=float)
        ez[dk:] = (sig[dk:] - sig[:-dk]) / (sig[:-dk] + 1e-8)
        uz = np.where(np.isfinite(z) & np.isfinite(sig), res / (2.0 * sig + 1e-8), np.nan)

        slp_den = np.where(atr_v, a_arr * np.sqrt(dk / 3.0) + 1e-8, np.nan)
        curv0 = np.tanh(2.0 * ac / slp_den)
        exp0 = np.tanh(3.0 * ez)

        zl_mat[:, idx_s] = z
        vel_mat[:, idx_s] = v
        acc_mat[:, idx_s] = ac
        sig_mat[:, idx_s] = sig
        uz_mat[:, idx_s] = uz
        exp_mat[:, idx_s] = ez
        curv_l0[:, idx_s] = curv0
        exp_l0[:, idx_s] = exp0

    phi_l1 = np.full((n, n_int), np.nan, dtype=float)
    for k_int in range(n_int):
        i_prev, i_cur, i_next = k_int, k_int + 1, k_int + 2
        den_cur = np.where(atr_v, a_arr * np.sqrt(dk_arr[i_cur] / 3.0) + 1e-8, np.nan)
        den_prev = np.where(atr_v, a_arr * np.sqrt(dk_arr[i_prev] / 3.0) + 1e-8, np.nan)
        den_o = 2.0 * sig_mat[:, i_cur] + 1e-8

        v_k = np.tanh(1.8 * vel_mat[:, i_cur] / den_cur)
        o_t1 = np.tanh((zl_mat[:, i_prev] - zl_mat[:, i_cur]) / den_o)
        o_t2 = np.tanh((zl_mat[:, i_cur] - zl_mat[:, i_next]) / den_o)
        o_k = 0.5 * (o_t1 + o_t2)
        g_align = np.clip(0.5 * (1.0 + np.tanh(6.0 * v_k * o_k)), 0.0, 1.0)
        o_dyn = o_k * g_align
        m_k = np.tanh(1.5 * (vel_mat[:, i_prev] / den_prev - vel_mat[:, i_cur] / den_cur))
        q_k = np.tanh((c_arr - zl_mat[:, i_cur]) / den_o)
        phi_l1[:, k_int] = 0.35 * v_k + 0.25 * o_dyn + 0.20 * m_k + 0.20 * q_k

    def _build_l1_to_l8(l1_m: np.ndarray) -> dict[int, np.ndarray]:
        lays = {1: l1_m}
        for l in range(2, 9):
            lays[l] = _convolve_triad_step(lays[l - 1], (0.30, 0.40, 0.30), min_w=0.50)
        return lays

    phi_layers = _build_l1_to_l8(phi_l1)
    curv_layers = _build_l1_to_l8(_convolve_triad_step(curv_l0, (0.25, 0.50, 0.25), min_w=0.50))
    exp_layers = _build_l1_to_l8(_convolve_triad_step(exp_l0, (0.25, 0.50, 0.25), min_w=0.50))

    def _layer_stats(lays: dict[int, np.ndarray]) -> tuple[dict[int, np.ndarray], np.ndarray]:
        l_means = {}
        for l in range(1, 9):
            arr = lays[l]
            cnt = np.isfinite(arr).sum(axis=1)
            l_means[l] = np.where(cnt > 0, np.nansum(arr, axis=1) / np.maximum(cnt, 1), np.nan)
        l38 = np.hstack([lays[l] for l in range(3, 9)])
        c38_cnt = np.isfinite(l38).sum(axis=1)
        c38 = np.where(c38_cnt > 0, np.nansum(l38, axis=1) / np.maximum(c38_cnt, 1), np.nan)
        return l_means, c38

    phi_l_means, c_phi_38 = _layer_stats(phi_layers)
    curv_l_means, c_curv_38 = _layer_stats(curv_layers)
    exp_l_means, c_exp_38 = _layer_stats(exp_layers)

    phi_bar_mat = np.full((n, n_int), np.nan, dtype=float)
    for k_i in range(n_int):
        num = np.zeros(n, dtype=float)
        den = np.zeros(n, dtype=float)
        for l_idx, l in enumerate(range(1, 9)):
            df_l = phi_layers[l]
            j_l = int(np.clip(k_i - (l - 1), 0, df_l.shape[1] - 1))
            v_col = df_l[:, j_l]
            fv = np.isfinite(v_col)
            w = LAYER_WEIGHTS[l_idx]
            num += np.where(fv, v_col * w, 0.0)
            den += np.where(fv, w, 0.0)
        ok = den >= 0.35
        phi_bar_mat[:, k_i] = np.where(ok, num / np.where(ok, den, 1.0), np.nan)

    d3h_phi_bar_mat = np.full((n, n_int), np.nan, dtype=float)
    d3h_phi_bar_mat[3:, :] = phi_bar_mat[3:, :] - phi_bar_mat[:-3, :]

    act_s17_idx = np.array([S17_TO_I[s] for s in SCALES_ACT], dtype=int)
    act_int_idx = np.array([INT_TO_I[s] for s in SCALES_ACT], dtype=int)
    n_act = len(SCALES_ACT)
    u_act = uz_mat[:, act_s17_idx]
    e_act = exp_mat[:, act_s17_idx]
    v_act = vel_mat[:, act_s17_idx]
    a_act = acc_mat[:, act_s17_idx]
    z_act = zl_mat[:, act_s17_idx]
    sig_act = sig_mat[:, act_s17_idx]
    phi_act = phi_bar_mat[:, act_int_idx]

    val_act = np.isfinite(u_act) & np.isfinite(e_act) & np.isfinite(v_act) & np.isfinite(a_act) & np.isfinite(phi_act)
    s_arr = np.array(SCALES_ACT, dtype=int)[None, :]
    m_upw = val_act & (u_act >= 0.55) & (e_act > 0.0) & (v_act > 0.0)
    m_dnw = val_act & (u_act <= -0.55) & (e_act > 0.0) & (v_act < 0.0)
    m_ov = val_act & (s_arr >= 233) & (u_act < 0.0) & (v_act > 0.0) & (a_act > 0.0)
    m_bpb = val_act & (~m_ov) & (np.abs(u_act) < 0.55) & (phi_act > 0.15) & (e_act <= 0.0)
    m_rpb = val_act & (~m_ov) & (np.abs(u_act) < 0.55) & (phi_act < -0.15) & (e_act <= 0.0)
    m_sqz = val_act & (np.abs(u_act) <= 0.70) & (e_act <= 0.0) & (np.abs(phi_act) <= 0.15)

    zst_act = np.where(val_act, ZST_TRANS, ZST_WARM)
    zst_act = np.where(m_sqz, ZST_SQZ_BOX, zst_act)
    zst_act = np.where(m_rpb, ZST_BEAR_PB, zst_act)
    zst_act = np.where(m_bpb, ZST_BULL_PB, zst_act)
    zst_act = np.where(m_ov, ZST_SELF_OV, zst_act)
    zst_act = np.where(m_dnw, ZST_DN_WALK, zst_act)
    zst_act = np.where(m_upw, ZST_UP_WALK, zst_act)

    n_box = np.cumprod(m_sqz, axis=1).astype(bool).sum(axis=1)
    k_box_z = np.where(n_box > 0, np.array(SCALES_ACT)[np.clip(n_box - 1, 0, n_act - 1)], 0)
    par_phi = phi_bar_mat[:, act_int_idx + 1]
    above_box = (np.arange(n_act)[None, :] >= n_box[:, None]) & val_act
    cand1 = above_box & ((m_bpb & (par_phi > 0.10)) | (m_rpb & (par_phi < -0.10)))
    cand2 = above_box & (np.abs(phi_act) > 0.15) & (np.abs(u_act) <= 1.20)
    valid_ge21 = val_act & (s_arr >= 21)
    i1 = np.argmax(cand1, axis=1)
    i2 = np.argmax(cand2, axis=1)
    i3 = np.argmin(np.where(valid_ge21, np.abs(u_act), 1e9), axis=1)
    k_star_idx = np.where(cand1.any(axis=1), i1, np.where(cand2.any(axis=1), i2, np.where(valid_ge21.any(axis=1), i3, -1)))
    k_star_z = np.where(k_star_idx >= 0, np.array(SCALES_ACT)[np.clip(k_star_idx, 0, n_act - 1)], 0)
    k_star_state = np.where(k_star_idx >= 0, zst_act[np.arange(n), np.clip(k_star_idx, 0, n_act - 1)], ZST_WARM)

    # Indices 6,7,8,9 in SCALES_ACT correspond strictly to (233, 377, 610, 987)
    n_ov_exhaust_z = m_ov[:, 6:10].sum(axis=1).astype(int)

    wg_scales_mask = (s_arr >= 55) & (s_arr <= 987) & val_act & (phi_act > 0.15)
    at_touch_lo = (wg_scales_mask & ((l_arr[:, None] <= z_act - 1.5 * sig_act) | (u_act <= -0.60))).any(axis=1)
    wg_outer = wg_scales_mask & above_box
    min_u_outer = np.min(np.where(wg_outer, u_act, 99.0), axis=1)
    bull_cont = np.isfinite(c_phi_38) & (c_phi_38 > 0.10)
    z_wait_touch = np.full(n, "NONE", dtype=object)
    z_wait_touch = np.where(bull_cont & at_touch_lo, "AT_TOUCH_Z_LO", z_wait_touch)
    z_wait_touch = np.where(
        bull_cont & (~at_touch_lo) & (k_box_z >= 21) & wg_outer.any(axis=1) & (min_u_outer > -0.25),
        "PRE_TOUCH_Z_BULL",
        z_wait_touch,
    )

    return {
        "n": n,
        "zl_mat": zl_mat,
        "vel_mat": vel_mat,
        "acc_mat": acc_mat,
        "sig_mat": sig_mat,
        "uz_mat": uz_mat,
        "exp_mat": exp_mat,
        "phi_layers": phi_layers,
        "curv_layers": curv_layers,
        "exp_layers": exp_layers,
        "phi_l_means": phi_l_means,
        "curv_l_means": curv_l_means,
        "exp_l_means": exp_l_means,
        "c_phi_38": c_phi_38,
        "c_curv_38": c_curv_38,
        "c_exp_38": c_exp_38,
        "phi_bar_mat": phi_bar_mat,
        "d3h_phi_bar_mat": d3h_phi_bar_mat,
        "zst_act": zst_act,
        "k_box_z": k_box_z,
        "k_star_z": k_star_z,
        "k_star_state": k_star_state,
        "n_ov_exhaust_z": n_ov_exhaust_z,
        "z_wait_touch": z_wait_touch,
    }


def build_zb1_purified_mask(
    close: np.ndarray,
    atr: np.ndarray,
    P: dict,
    T: dict[str, np.ndarray],
    range_30d_pos_pct: np.ndarray,
    subm_frac: np.ndarray,
    wk_slp_2584: np.ndarray,
    m1_u21: np.ndarray,
    d3_thr: float = 0.15,
    c_exp_max: float = 0.10,
    r30_lo: float = 25.0,
    r30_hi: float = 85.0,
) -> np.ndarray:
    """Strictly causal Purified Track Z-B1 (L5/L7) Pure-ZLEMA signal mask."""
    n = len(close)
    zl_21 = P["zl_mat"][:, S17_TO_I[21]]
    kstar_int_idx = np.array([INT_TO_I[int(s)] if int(s) in INT_TO_I else 1 for s in P["k_star_z"]], dtype=int)
    d3h_kstar = P["d3h_phi_bar_mat"][np.arange(n), kstar_int_idx]

    t4_bull = np.isin(T["T4"], ["PO_UP_EXPAND", "PO_UP_COMPRESS", "LEAD_PULLBACK_BULL"])
    t3_clean = ~np.isin(T["T3"], ["WARMUP", "TANGLED_CHOP", "PO_DN_CASCADE"])

    return (
        np.isfinite(atr) & (atr > 1e-8)
        & np.isfinite(zl_21)
        & np.isfinite(P["c_phi_38"]) & (P["c_phi_38"] >= -0.12) & (P["c_phi_38"] <= 0.12)
        & np.isfinite(wk_slp_2584) & (wk_slp_2584 > 0.0)
        & t4_bull
        & t3_clean
        & (close > zl_21)
        & np.isfinite(d3h_kstar) & (d3h_kstar >= float(d3_thr))
        & np.isfinite(P["c_exp_38"]) & (P["c_exp_38"] <= float(c_exp_max))
        & (P["n_ov_exhaust_z"] == 0)
        & (P["z_wait_touch"] != "AT_TOUCH_Z_LO")
        & np.isfinite(subm_frac) & (subm_frac <= 0.72)
        & np.isfinite(range_30d_pos_pct) & (range_30d_pos_pct >= float(r30_lo)) & (range_30d_pos_pct < float(r30_hi))
        & np.isfinite(m1_u21) & (m1_u21 > -0.20)
    )


def compute_preign_stop(
    entry_price: float,
    atr0: float,
    cap_atr: float = 3.25,
    cap_pct: float = 0.043,
    logic: str = "OR",
) -> float:
    """Compute pre-ignition invalidation stop level (`OR` takes tighter max vs `AND` looser min)."""
    atr_stop = entry_price - cap_atr * atr0
    pct_stop = entry_price * (1.0 - cap_pct)
    if logic.upper() == "OR":
        return float(max(atr_stop, pct_stop))
    if logic.upper() == "AND":
        return float(min(atr_stop, pct_stop))
    raise ValueError(f"Unknown preign logic: {logic}")


def verify_zlema_native_invariants(
    close: Sequence[float] | np.ndarray,
    high: Sequence[float] | np.ndarray,
    low: Sequence[float] | np.ndarray,
    atr: Sequence[float] | np.ndarray,
    t_cut: int | None = None,
) -> dict[str, float | int | bool]:
    """
    Verify both:
      1. Exact Zero-Lookahead invariance when mutating OHLC+ATR strictly after `t_cut`.
      2. Exact Dual Sign-Flip Symmetry under `(C, H, L) -> (-C, -L, -H)`:
         `Phi^Z(-P) == -Phi^Z(P)`, `Curv^Z(-P) == -Curv^Z(P)`, `Exp^Z(-P) == +Exp^Z(P)`.
    """
    c = np.asarray(close, dtype=float)
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    a = np.asarray(atr, dtype=float)
    n = len(c)
    if t_cut is None:
        t_cut = max(50, int(0.80 * n))

    P = compute_zlema_pyramid_system(c, h, l, a)
    T = compute_zlema_triplets(P["zl_mat"], P["vel_mat"], a)

    c_p, h_p, l_p, a_p = c.copy(), h.copy(), l.copy(), a.copy()
    c_p[t_cut + 1 :] = c_p[t_cut + 1 :] * 1.45 + 12345.0
    h_p[t_cut + 1 :] = h_p[t_cut + 1 :] * 1.45 + 12500.0
    l_p[t_cut + 1 :] = l_p[t_cut + 1 :] * 1.45 + 12100.0
    a_p[t_cut + 1 :] = a_p[t_cut + 1 :] * 1.65 + 30.0
    P_p = compute_zlema_pyramid_system(c_p, h_p, l_p, a_p)
    T_p = compute_zlema_triplets(P_p["zl_mat"], P_p["vel_mat"], a_p)

    max_lookahead_diff = 0.0
    for key in ("zl_mat", "phi_bar_mat", "d3h_phi_bar_mat", "c_phi_38", "c_curv_38", "c_exp_38"):
        x1 = np.asarray(P[key][: t_cut + 1], dtype=float)
        x2 = np.asarray(P_p[key][: t_cut + 1], dtype=float)
        if not np.array_equal(np.isnan(x1), np.isnan(x2)):
            max_lookahead_diff = float("inf")
        else:
            fin = np.isfinite(x1)
            if fin.any():
                max_lookahead_diff = max(max_lookahead_diff, float(np.max(np.abs(x1[fin] - x2[fin]))))
    for tk in T:
        if not np.array_equal(T[tk][: t_cut + 1], T_p[tk][: t_cut + 1]):
            max_lookahead_diff = float("inf")

    P_neg = compute_zlema_pyramid_system(-c, -l, -h, a)
    max_signflip_err = 0.0
    for key in ("phi_bar_mat", "c_phi_38", "c_curv_38"):
        v1 = np.asarray(P[key], dtype=float)
        v2 = np.asarray(P_neg[key], dtype=float)
        fin = np.isfinite(v1) & np.isfinite(v2)
        if fin.any():
            max_signflip_err = max(max_signflip_err, float(np.max(np.abs(v1[fin] + v2[fin]))))

    e1 = np.asarray(P["c_exp_38"], dtype=float)
    e2 = np.asarray(P_neg["c_exp_38"], dtype=float)
    fin_e = np.isfinite(e1) & np.isfinite(e2)
    max_exp_even_err = float(np.max(np.abs(e1[fin_e] - e2[fin_e]))) if fin_e.any() else 0.0

    passed = (max_lookahead_diff == 0.0) and (max_signflip_err < 1e-12) and (max_exp_even_err < 1e-12)
    return {
        "t_cut": int(t_cut),
        "max_lookahead_diff": float(max_lookahead_diff),
        "max_dual_signflip_err": float(max_signflip_err),
        "max_exp_even_err": float(max_exp_even_err),
        "passed": bool(passed),
    }


def compute_additive_portfolio_metrics(
    gross_returns: Sequence[float],
    friction_rate: float = FRICTION_RATE,
) -> dict[str, float | int]:
    """Evaluate trade list under strictly additive SPEC-EVAL-001 accounting (zero compounding)."""
    if len(gross_returns) == 0:
        return {
            "total_trades": 0,
            "friction_cost_applied": float(friction_rate),
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "net_ev_pct": 0.0,
            "total_net_return_pct": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
        }

    net_rets = np.asarray(gross_returns, dtype=float) - float(friction_rate)
    wins = net_rets[net_rets > 0.0]
    losses = net_rets[net_rets <= 0.0]
    gp = float(wins.sum())
    gl = float(abs(losses.sum()))
    pf = gp / gl if gl > 1e-12 else (99.99 if gp > 0.0 else 0.0)
    tot = float(net_rets.sum())
    eq = np.cumsum(net_rets)
    pk = np.maximum.accumulate(np.insert(eq, 0, 0.0))[1:]
    mdd = float(np.max(pk - eq)) if len(eq) else 0.0
    calmar = (tot / mdd) if mdd > 1e-12 else (99.99 if tot > 0.0 else 0.0)
    return {
        "total_trades": int(len(net_rets)),
        "friction_cost_applied": float(friction_rate),
        "win_rate_pct": float((net_rets > 0.0).mean() * 100.0),
        "profit_factor": float(pf),
        "net_ev_pct": float(net_rets.mean() * 100.0),
        "total_net_return_pct": float(tot * 100.0),
        "max_drawdown": float(mdd),
        "calmar": float(calmar),
    }
