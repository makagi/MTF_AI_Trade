"""EXP-162: Bear-Market Asymmetry, Extended Hierarchical Pyramids, ZL-BB, Z-AFS/Stoch_d,
and Track Z-B1 Bear-Defense Verification Reference Implementation.

Consolidates EXP-158..162 strictly causal primitives into a repo-portable module:
  1. NaN-safe causal zero-lag EMA (`zlema_nan_safe`) preserving exact affine invariance.
  2. Extended hierarchical pyramid convolutions (`Shear_Phi`, `E_dn_14`/`E_up_14`,
     `Persist_dn_14`, continuous macro self-overshoot `C_Ov_macro`, observable S/R
     ceiling/floor density `Ceil_Z`/`Floor_Z`/`SR_Asym`).
  3. Zero-Lag Bollinger Bands (`Log-ZL-BB`, `Z-MAD-BB`, `Vol_Ov`) & 3-perspective
     `ZL-BB` hierarchical pyramids (`L1..L8`).
  4. 17-scale `Stoch_d`, classic `SMA-AFS`, zero-lag `Z-AFS` hierarchical pyramids,
     plus `SPEC-FEAT-001` micro `AFS[7,9,11,13]`.
  5. Track Z-B1 Bear-Defense causal gate (`T5 == LEAD_TURN_BEAR & wk_slp_anchor < thr`
     and `Log-ZL-BB` expansion cap `C_zl_exp_38 <= zlexp_max`) + invariant verifier.

Strictly Discovery partition only. No holdout data or compounding math.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

EXP_DIR = Path(__file__).resolve().parent
_EXP156_RUN = EXP_DIR.parent / "156-zlema-native-program-and-zb1-purification" / "run.py"

_spec156 = importlib.util.spec_from_file_location("exp156_base_mod", str(_EXP156_RUN))
if _spec156 is None or _spec156.loader is None:
    raise ImportError(f"Unable to load EXP-156 reference module at {_EXP156_RUN}")
_exp156 = importlib.util.module_from_spec(_spec156)
_spec156.loader.exec_module(_exp156)

SCALES_17 = _exp156.SCALES_17
S17_TO_I = _exp156.S17_TO_I
SCALES_15_INT = _exp156.SCALES_15_INT
LAYER_WEIGHTS = np.array([0.35, 0.25, 0.15, 0.10, 0.06, 0.04, 0.03, 0.02], dtype=float)
compute_mql5_zlema = _exp156.compute_mql5_zlema
compute_zlema_triplets = _exp156.compute_zlema_triplets


def _nan_row_mean(mat: np.ndarray) -> np.ndarray:
    """Compute strictly NaN-aware row mean returning NaN when all entries in row are NaN."""
    cnt = np.isfinite(mat).sum(axis=1)
    return np.where(cnt > 0, np.nansum(mat, axis=1) / np.where(cnt > 0, cnt, 1), np.nan)


def _nan_row_max(mat: np.ndarray) -> np.ndarray:
    """Compute NaN-safe row maximum without all-NaN warnings."""
    fin = np.isfinite(mat)
    cnt = fin.sum(axis=1)
    mx = np.max(np.where(fin, mat, -np.inf), axis=1)
    return np.where(cnt > 0, mx, np.nan)


def convolve_triad_step(
    mat: np.ndarray, weights: tuple[float, float, float] = (0.30, 0.40, 0.30), min_w: float = 0.50
) -> np.ndarray:
    """NaN-aware 3-node spatial pyramid convolution preserving exact odd/even sign symmetry."""
    w0, w1, w2 = weights
    a, b, c = mat[:, :-2], mat[:, 1:-1], mat[:, 2:]
    fa, fb, fc = np.isfinite(a), np.isfinite(b), np.isfinite(c)
    w_sum = w0 * fa + w1 * fb + w2 * fc
    val_num = w0 * np.where(fa, a, 0.0) + w1 * np.where(fb, b, 0.0) + w2 * np.where(fc, c, 0.0)
    valid = w_sum >= (min_w - 1e-12)
    return np.where(valid, val_num / np.where(valid, w_sum, 1.0), np.nan)


def _convolve_l1_to_l8(l1_mat: np.ndarray) -> tuple[dict[int, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    """Recursively convolve L1 -> L8 and return layers plus L1..2, L3..8, L5..8 continuums."""
    lays = {1: l1_mat}
    for layer in range(2, 9):
        lays[layer] = convolve_triad_step(lays[layer - 1], (0.30, 0.40, 0.30), min_w=0.50)
    c12 = _nan_row_mean(np.hstack([lays[l] for l in (1, 2)]))
    c38 = _nan_row_mean(np.hstack([lays[l] for l in range(3, 9)]))
    c58 = _nan_row_mean(np.hstack([lays[l] for l in range(5, 9)]))
    return lays, c12, c38, c58


def _integrate_bar_mat(lays: dict[int, np.ndarray]) -> np.ndarray:
    """Layer-weighted per-scale score matching Phi_bar^Z geometry across interior scales."""
    n, n_int = lays[1].shape
    out = np.full((n, n_int), np.nan, dtype=float)
    for k_i in range(n_int):
        num = np.zeros(n, dtype=float)
        den = np.zeros(n, dtype=float)
        for l_idx, layer in enumerate(range(1, 9)):
            df_l = lays[layer]
            j_l = int(np.clip(k_i - (layer - 1), 0, df_l.shape[1] - 1))
            col = df_l[:, j_l]
            fv = np.isfinite(col)
            w = LAYER_WEIGHTS[l_idx]
            num += np.where(fv, col * w, 0.0)
            den += np.where(fv, w, 0.0)
        ok = den >= 0.35
        out[:, k_i] = np.where(ok, num / np.where(ok, den, 1.0), np.nan)
    return out


def zlema_nan_safe(x: np.ndarray, period: int, warmup_cap: int = 144) -> np.ndarray:
    """
    Strictly causal MQL5-equivalent ZLEMA on inputs containing leading NaNs.
    Uses `init_zero=False` (seeding at `x[start-1]`) so affine maps like `100 - K`
    retain exact sign-flip complementarity (< 1e-12).
    """
    arr = np.asarray(x, dtype=float)
    n = len(arr)
    out = np.full(n, np.nan, dtype=float)
    p = int(period)
    lag = (p - 1) // 2
    fin = np.isfinite(arr)
    if not fin.any():
        return out

    start = int(np.argmax(fin)) + lag + 1
    while start < n and not (np.isfinite(arr[start]) and np.isfinite(arr[start - lag])):
        start += 1
    if start >= n:
        return out

    inp = 2.0 * arr[start:] - arr[start - lag : n - lag]
    seed_val = float(arr[start - 1]) if np.isfinite(arr[start - 1]) else float(arr[start])
    seq = np.empty(len(inp) + 1, dtype=float)
    seq[0] = seed_val
    seq[1:] = inp

    raw = pd.Series(seq).ewm(alpha=2.0 / (p + 1.0), adjust=False).mean().to_numpy(dtype=float, copy=True)
    skip = min(p, int(warmup_cap))
    out_start = start + skip
    if out_start < n:
        out[out_start:] = raw[1 + skip :]
    return out


def compute_base_zlema_pyramid(
    close: np.ndarray, high: np.ndarray, low: np.ndarray, atr: np.ndarray
) -> dict:
    """Compute core 17-scale Pure-ZLEMA kinematics, residual EWM-RMS, and Phi^Z pyramid."""
    n = len(close)
    n17 = len(SCALES_17)
    n_int = len(SCALES_15_INT)
    atr_v = np.isfinite(atr) & (atr > 1e-8)

    zl_mat = np.full((n, n17), np.nan, dtype=float)
    vel_mat = np.full((n, n17), np.nan, dtype=float)
    acc_mat = np.full((n, n17), np.nan, dtype=float)
    sig_mat = np.full((n, n17), np.nan, dtype=float)
    uz_mat = np.full((n, n17), np.nan, dtype=float)
    exp_mat = np.full((n, n17), np.nan, dtype=float)
    dk_arr = np.zeros(n17, dtype=int)

    for idx_s, s in enumerate(SCALES_17):
        dk = max(2, int(round(0.15 * s)))
        dk_arr[idx_s] = dk
        z = compute_mql5_zlema(close, s, init_zero=True, enforce_full_warmup=True)
        v = np.full(n, np.nan, dtype=float)
        v[dk:] = z[dk:] - z[:-dk]
        a = np.full(n, np.nan, dtype=float)
        a[2 * dk :] = v[2 * dk :] - v[dk:-dk]

        res = close - z
        rms_sq = pd.Series(res * res).ewm(span=s, min_periods=min(s, 144), adjust=False).mean().to_numpy(dtype=float, copy=True)
        sig = np.where(np.isfinite(z) & np.isfinite(rms_sq), np.sqrt(np.maximum(rms_sq, 0.0)), np.nan)
        ez = np.full(n, np.nan, dtype=float)
        ez[dk:] = (sig[dk:] - sig[:-dk]) / (sig[:-dk] + 1e-8)
        uz = np.where(np.isfinite(z) & np.isfinite(sig), res / (2.0 * sig + 1e-8), np.nan)

        zl_mat[:, idx_s] = z
        vel_mat[:, idx_s] = v
        acc_mat[:, idx_s] = a
        sig_mat[:, idx_s] = sig
        uz_mat[:, idx_s] = uz
        exp_mat[:, idx_s] = ez

    phi_l1 = np.full((n, n_int), np.nan, dtype=float)
    for k_int, _ in enumerate(SCALES_15_INT):
        i_prev, i_cur, i_next = k_int, k_int + 1, k_int + 2
        den_cur = np.where(atr_v, atr * np.sqrt(dk_arr[i_cur] / 3.0) + 1e-8, np.nan)
        den_prev = np.where(atr_v, atr * np.sqrt(dk_arr[i_prev] / 3.0) + 1e-8, np.nan)
        den_o = 2.0 * sig_mat[:, i_cur] + 1e-8

        v_k = np.tanh(1.8 * vel_mat[:, i_cur] / den_cur)
        o_k = 0.5 * (
            np.tanh((zl_mat[:, i_prev] - zl_mat[:, i_cur]) / den_o)
            + np.tanh((zl_mat[:, i_cur] - zl_mat[:, i_next]) / den_o)
        )
        g_align = np.clip(0.5 * (1.0 + np.tanh(6.0 * v_k * o_k)), 0.0, 1.0)
        m_k = np.tanh(1.5 * (vel_mat[:, i_prev] / den_prev - vel_mat[:, i_cur] / den_cur))
        q_k = np.tanh((close - zl_mat[:, i_cur]) / den_o)
        phi_l1[:, k_int] = 0.35 * v_k + 0.25 * (o_k * g_align) + 0.20 * m_k + 0.20 * q_k

    phi_layers, c_phi_12, c_phi_38, _ = _convolve_l1_to_l8(phi_l1)
    phi_bar_mat = _integrate_bar_mat(phi_layers)
    return {
        "n": n, "zl_mat": zl_mat, "vel_mat": vel_mat, "acc_mat": acc_mat,
        "sig_mat": sig_mat, "uz_mat": uz_mat, "exp_mat": exp_mat,
        "phi_layers": phi_layers, "c_phi_12": c_phi_12, "c_phi_38": c_phi_38,
        "phi_bar_mat": phi_bar_mat, "high": high, "low": low,
    }


def compute_extended_pyramid_features(P: dict, close: np.ndarray, atr: np.ndarray) -> dict:
    """Compute EXP-159 extended pyramid features (Shear, Coupled Energy, Self-Ov, SR Asym)."""
    n = P["n"]
    atr_v = np.isfinite(atr) & (atr > 1e-8)

    c_phi_58 = _nan_row_mean(np.hstack([P["phi_layers"][l] for l in range(5, 9)]))
    shear_phi = P["c_phi_12"] - c_phi_58
    d6h_shear = np.full(n, np.nan, dtype=float)
    d6h_shear[6:] = shear_phi[6:] - shear_phi[:-6]

    red_flag = np.isfinite(P["phi_bar_mat"]) & (P["phi_bar_mat"] < -0.15)
    green_flag = np.isfinite(P["phi_bar_mat"]) & (P["phi_bar_mat"] > 0.15)
    d_red_depth = np.cumprod(red_flag, axis=1).sum(axis=1).astype(int)
    d_green_depth = np.cumprod(green_flag, axis=1).sum(axis=1).astype(int)

    dk_arr = np.array([max(2, int(round(0.15 * s))) for s in SCALES_17], dtype=int)
    slp_den = np.where(atr_v[:, None], atr[:, None] * np.sqrt(dk_arr[None, :] / 3.0) + 1e-8, np.nan)
    curv_l0 = np.tanh(2.0 * P["acc_mat"] / slp_den)
    exp_l0 = np.tanh(3.0 * P["exp_mat"])

    curv_l1 = convolve_triad_step(curv_l0, (0.25, 0.50, 0.25), min_w=0.50)
    exp_l1 = convolve_triad_step(exp_l0, (0.25, 0.50, 0.25), min_w=0.50)
    phi_l1 = P["phi_layers"][1]
    v_l1 = np.isfinite(phi_l1) & np.isfinite(curv_l1) & np.isfinite(exp_l1)

    gamma_dn_l1 = np.where(v_l1, np.maximum(0.0, -phi_l1) * np.maximum(0.0, -curv_l1) * (1.0 + np.maximum(0.0, exp_l1)), np.nan)
    gamma_up_l1 = np.where(v_l1, np.maximum(0.0, +phi_l1) * np.maximum(0.0, +curv_l1) * (1.0 + np.maximum(0.0, exp_l1)), np.nan)
    lays_dn, _, _, _ = _convolve_l1_to_l8(gamma_dn_l1)
    lays_up, _, _, _ = _convolve_l1_to_l8(gamma_up_l1)

    e_dn_14 = _nan_row_mean(np.hstack([lays_dn[l] for l in range(1, 5)]))
    e_up_14 = _nan_row_mean(np.hstack([lays_up[l] for l in range(1, 5)]))
    net_energy_14 = e_up_14 - e_dn_14
    persist_dn_14 = (
        pd.Series(e_dn_14).ewm(span=6, min_periods=1, adjust=False).mean().to_numpy(dtype=float, copy=True)
        - pd.Series(e_dn_14).ewm(span=24, min_periods=1, adjust=False).mean().to_numpy(dtype=float, copy=True)
    )

    v_norm = np.tanh(1.8 * P["vel_mat"] / slp_den)
    v_ov = np.isfinite(P["uz_mat"]) & np.isfinite(v_norm) & np.isfinite(curv_l0)
    ov_l0 = np.where(v_ov, np.maximum(0.0, -P["uz_mat"]) * np.maximum(0.0, v_norm) * np.maximum(0.0, curv_l0), np.nan)
    ov_bull_l0 = np.where(v_ov, np.maximum(0.0, +P["uz_mat"]) * np.maximum(0.0, -v_norm) * np.maximum(0.0, -curv_l0), np.nan)
    c_ov_macro = _nan_row_mean(convolve_triad_step(ov_l0[:, 6:], (0.25, 0.50, 0.25), min_w=0.50)[:, 0:4])
    c_ov_bull_macro = _nan_row_mean(convolve_triad_step(ov_bull_l0[:, 6:], (0.25, 0.50, 0.25), min_w=0.50)[:, 0:4])

    z_sr = P["zl_mat"][:, 2:15]
    p_sr = P["phi_bar_mat"][:, 1:14]
    fin_sr = np.isfinite(z_sr) & np.isfinite(p_sr) & atr_v[:, None]
    cnt_sr = fin_sr.sum(axis=1)
    safe_atr = np.where(atr_v[:, None], atr[:, None], 1.0)
    ceil_mat = np.where(fin_sr & (z_sr > close[:, None]), np.maximum(0.0, -p_sr) * np.exp(-np.maximum(0.0, (z_sr - close[:, None]) / safe_atr) / 4.0), 0.0)
    floor_mat = np.where(fin_sr & (z_sr < close[:, None]), np.maximum(0.0, +p_sr) * np.exp(-np.maximum(0.0, (close[:, None] - z_sr) / safe_atr) / 4.0), 0.0)
    ceil_z = np.where(cnt_sr > 0, ceil_mat.sum(axis=1) / np.where(cnt_sr > 0, cnt_sr, 1), np.nan)
    floor_z = np.where(cnt_sr > 0, floor_mat.sum(axis=1) / np.where(cnt_sr > 0, cnt_sr, 1), np.nan)
    sr_asym = ceil_z - floor_z

    return {
        "shear_phi": shear_phi, "d6h_shear": d6h_shear, "d_red_depth": d_red_depth, "d_green_depth": d_green_depth,
        "e_dn_14": e_dn_14, "e_up_14": e_up_14, "net_energy_14": net_energy_14, "persist_dn_14": persist_dn_14,
        "c_ov_macro": c_ov_macro, "c_ov_bull_macro": c_ov_bull_macro,
        "ceil_z": ceil_z, "floor_z": floor_z, "sr_asym": sr_asym,
    }


def compute_zlbb_system(P: dict, close: np.ndarray, atr: np.ndarray) -> dict:
    """Compute Log-ZL-BB, Z-MAD-BB, Vol_Ov, and 3-Perspective ZL-BB Pyramids."""
    n = len(close)
    n17 = len(SCALES_17)
    n_int = len(SCALES_15_INT)
    atr_v = np.isfinite(atr) & (atr > 1e-8)

    sig_logzl_mat = np.full((n, n17), np.nan, dtype=float)
    sig_zmad_mat = np.full((n, n17), np.nan, dtype=float)
    vol_ov_mat = np.full((n, n17), np.nan, dtype=float)
    bb_up_mat = np.full((n, n17), np.nan, dtype=float)
    bb_lo_mat = np.full((n, n17), np.nan, dtype=float)
    bb_w_mat = np.full((n, n17), np.nan, dtype=float)
    ez_zl_mat = np.full((n, n17), np.nan, dtype=float)
    exp_zl_l0 = np.full((n, n17), np.nan, dtype=float)

    for idx_s, s in enumerate(SCALES_17):
        z = P["zl_mat"][:, idx_s]
        sig_ewm = P["sig_mat"][:, idx_s]
        dk = max(2, int(round(0.15 * s)))
        r = close - z
        r2_loc = pd.Series(r * r).ewm(span=3, min_periods=1, adjust=False).mean().to_numpy(dtype=float, copy=True)
        eps_flr = np.where(atr_v, 0.15 * atr, np.nan)
        log_in = np.where(np.isfinite(r2_loc) & np.isfinite(eps_flr), 0.5 * np.log(r2_loc + eps_flr * eps_flr), np.nan)
        log_zl = zlema_nan_safe(log_in, s, warmup_cap=144)
        sig_logzl = np.where(np.isfinite(log_zl), np.exp(np.clip(log_zl, -20.0, 20.0)), np.nan)

        zmad_raw = np.sqrt(np.pi / 2.0) * zlema_nan_safe(np.where(np.isfinite(r), np.abs(r), np.nan), s, warmup_cap=144)
        sig_zmad = np.where(np.isfinite(zmad_raw) & np.isfinite(sig_ewm), np.maximum(zmad_raw, 0.15 * sig_ewm), np.nan)
        vol_ov = np.where(np.isfinite(zmad_raw) & np.isfinite(sig_ewm), np.maximum(0.0, -zmad_raw) / (sig_ewm + 1e-8), np.nan)

        sig_logzl_mat[:, idx_s] = sig_logzl
        sig_zmad_mat[:, idx_s] = sig_zmad
        vol_ov_mat[:, idx_s] = vol_ov
        bb_up_mat[:, idx_s] = z + 2.0 * sig_logzl
        bb_lo_mat[:, idx_s] = z - 2.0 * sig_logzl
        bb_w_mat[:, idx_s] = 4.0 * sig_logzl

        ez_zl = np.full(n, np.nan, dtype=float)
        ez_zl[dk:] = (sig_logzl[dk:] - sig_logzl[:-dk]) / (sig_logzl[:-dk] + 1e-8)
        ez_zl_mat[:, idx_s] = ez_zl
        exp_zl_l0[:, idx_s] = np.tanh(3.0 * ez_zl)

    bb_up_l1 = np.full((n, n_int), np.nan, dtype=float)
    bb_lo_l1 = np.full((n, n_int), np.nan, dtype=float)
    zl_wratio_l1 = np.full((n, n_int), np.nan, dtype=float)
    for k_int, sb in enumerate(SCALES_15_INT):
        ia, ib, ic = k_int, k_int + 1, k_int + 2
        sa, sc = SCALES_17[ia], SCALES_17[ic]
        scale_norm = np.sqrt(sb / 21.0)
        dk_b = max(2, int(round(0.15 * sb)))
        den_dist = np.where(atr_v, 0.8 * scale_norm * atr + 1e-8, np.nan)
        den_slp = np.where(atr_v, atr * np.sqrt(dk_b / 3.0) + 1e-8, np.nan)
        for dst, mat in ((bb_up_l1, bb_up_mat), (bb_lo_l1, bb_lo_mat)):
            d_ab = np.tanh((mat[:, ia] - mat[:, ib]) / den_dist)
            d_bc = np.tanh((mat[:, ib] - mat[:, ic]) / den_dist)
            slp_b = np.full(n, np.nan, dtype=float)
            slp_b[dk_b:] = np.tanh(1.8 * (mat[dk_b:, ib] - mat[:-dk_b, ib]) / den_slp[dk_b:])
            dst[:, k_int] = (d_ab + d_bc + slp_b) / 3.0
        r_ab = (bb_w_mat[:, ia] / (bb_w_mat[:, ib] + 1e-8)) / np.sqrt(sa / sb) - 1.0
        r_bc = (bb_w_mat[:, ib] / (bb_w_mat[:, ic] + 1e-8)) / np.sqrt(sb / sc) - 1.0
        zl_wratio_l1[:, k_int] = (np.tanh(2.5 * r_ab) + np.tanh(2.5 * r_bc) + np.tanh(3.0 * ez_zl_mat[:, ib])) / 3.0

    _, c_bb_up_12, c_bb_up_38, _ = _convolve_l1_to_l8(bb_up_l1)
    _, c_bb_lo_12, c_bb_lo_38, _ = _convolve_l1_to_l8(bb_lo_l1)
    _, c_zl_wratio_12, c_zl_wratio_38, _ = _convolve_l1_to_l8(zl_wratio_l1)
    _, c_zl_exp_12, c_zl_exp_38, _ = _convolve_l1_to_l8(convolve_triad_step(exp_zl_l0, (0.25, 0.50, 0.25), min_w=0.50))

    return {
        "sig_logzl_mat": sig_logzl_mat, "sig_zmad_mat": sig_zmad_mat, "vol_ov_mat": vol_ov_mat,
        "bb_up_mat": bb_up_mat, "bb_lo_mat": bb_lo_mat,
        "c_bb_up_12": c_bb_up_12, "c_bb_up_38": c_bb_up_38,
        "c_bb_lo_12": c_bb_lo_12, "c_bb_lo_38": c_bb_lo_38,
        "c_bb_dir_38": 0.5 * (c_bb_up_38 + c_bb_lo_38),
        "c_bb_exp_struct_38": 0.5 * (c_bb_up_38 - c_bb_lo_38),
        "c_zl_wratio_12": c_zl_wratio_12, "c_zl_wratio_38": c_zl_wratio_38,
        "c_zl_exp_12": c_zl_exp_12, "c_zl_exp_38": c_zl_exp_38,
    }


def compute_oscillator_pyramids(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> dict:
    """Compute 17-scale Stoch_d, SMA-AFS, & Zero-Lag Z-AFS Pyramids + SPEC-FEAT-001 micro AFS[7..13]."""
    n = len(close)
    n17 = len(SCALES_17)
    n_int = len(SCALES_15_INT)
    hi_s_pd, lo_s_pd = pd.Series(high), pd.Series(low)

    z_stoch_mat = np.full((n, n17), np.nan, dtype=float)
    c_afs_mat = np.full((n, n17), np.nan, dtype=float)
    c_zafs_mat = np.full((n, n17), np.nan, dtype=float)

    for idx_s, s in enumerate(SCALES_17):
        min_p = min(s, 24)
        lo_s = lo_s_pd.rolling(s, min_periods=min_p).min().to_numpy(dtype=float, copy=True)
        hi_s = hi_s_pd.rolling(s, min_periods=min_p).max().to_numpy(dtype=float, copy=True)
        rng = hi_s - lo_s
        k_s = np.where(
            np.isfinite(close) & np.isfinite(rng),
            np.where(rng > 1e-8, (close - lo_s) / np.where(rng > 1e-8, rng, 1.0) * 100.0, 50.0),
            np.nan,
        )
        d_s = np.where(np.isfinite(k_s), pd.Series(k_s).rolling(3, min_periods=1).mean().to_numpy(dtype=float, copy=True), np.nan)
        afs_s = pd.Series(k_s).rolling(s, min_periods=min_p).mean().to_numpy(dtype=float, copy=True)
        zafs_s = zlema_nan_safe(k_s, s, warmup_cap=144)

        z_stoch_mat[:, idx_s] = (d_s - 50.0) / 50.0
        c_afs_mat[:, idx_s] = (afs_s - 50.0) / 50.0
        c_zafs_mat[:, idx_s] = (zafs_s - 50.0) / 50.0

    _, c_stoch_12, c_stoch_38, c_stoch_58 = _convolve_l1_to_l8(
        convolve_triad_step(z_stoch_mat, (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0), min_w=0.50)
    )
    stoch_shear = c_stoch_12 - c_stoch_58

    def _afs_pyr(c_mat: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        l1 = np.full((n, n_int), np.nan, dtype=float)
        for k_int in range(n_int):
            ia, ib, ic = k_int, k_int + 1, k_int + 2
            slp_b = np.full(n, np.nan, dtype=float)
            slp_b[3:] = np.tanh(10.0 * (c_mat[3:, ib] - c_mat[:-3, ib]) / 3.0)
            l1[:, k_int] = 0.25 * (np.tanh(c_mat[:, ia] - c_mat[:, ib]) + np.tanh(c_mat[:, ib] - c_mat[:, ic]) + slp_b + c_mat[:, ib])
        _, c12, c38, c58 = _convolve_l1_to_l8(l1)
        return c12, c38, c58

    c_afs_12, c_afs_38, _ = _afs_pyr(c_afs_mat)
    c_zafs_12, c_zafs_38, c_zafs_58 = _afs_pyr(c_zafs_mat)
    zafs_shear = c_zafs_12 - c_zafs_58
    zafs_ov_dn = (np.isfinite(c_zafs_mat[:, 2:10]) & (c_zafs_mat[:, 2:10] < -1.0)).sum(axis=1).astype(int)
    zafs_ov_up = (np.isfinite(c_zafs_mat[:, 2:10]) & (c_zafs_mat[:, 2:10] > 1.0)).sum(axis=1).astype(int)

    afs_micro = []
    for p in (7, 9, 11, 13):
        lo_m = lo_s_pd.rolling(p, min_periods=p).min().to_numpy(dtype=float, copy=True)
        hi_m = hi_s_pd.rolling(p, min_periods=p).max().to_numpy(dtype=float, copy=True)
        rng_m = hi_m - lo_m
        k_m = np.where(
            np.isfinite(close) & np.isfinite(rng_m),
            np.where(rng_m > 1e-8, (close - lo_m) / np.where(rng_m > 1e-8, rng_m, 1.0) * 100.0, 50.0),
            np.nan,
        )
        afs_micro.append(pd.Series(k_m).rolling(p, min_periods=p).mean().to_numpy(dtype=float, copy=True))
    afs_m = np.column_stack(afs_micro)
    val_m = np.isfinite(afs_m).all(axis=1)
    afs_order_score = np.where(
        val_m,
        (afs_m[:, 0] > afs_m[:, 1]).astype(int) + (afs_m[:, 1] > afs_m[:, 2]).astype(int) + (afs_m[:, 2] > afs_m[:, 3]).astype(int),
        -1,
    )
    afs_compression = np.where(val_m, np.var(afs_m, axis=1, ddof=1), np.nan)

    return {
        "c_stoch_12": c_stoch_12, "c_stoch_38": c_stoch_38, "stoch_shear": stoch_shear,
        "c_afs_12": c_afs_12, "c_afs_38": c_afs_38,
        "c_zafs_12": c_zafs_12, "c_zafs_38": c_zafs_38, "zafs_shear": zafs_shear,
        "zafs_ov_dn": zafs_ov_dn, "zafs_ov_up": zafs_ov_up,
        "afs_order_score": afs_order_score, "afs_compression": afs_compression,
    }


def compute_bear_anchor_slope(zl_mat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute highest finite macro ZLEMA anchor scale and its causal 1-week % slope."""
    n = zl_mat.shape[0]
    anchor_s = np.full(n, 377, dtype=int)
    wk_slp = np.full(n, np.nan, dtype=float)
    for t in range(n):
        sc_a = 377
        for sc in (6765, 4181, 2584, 1597, 987, 610, 377):
            if np.isfinite(zl_mat[t, S17_TO_I[sc]]):
                sc_a = sc
                break
        anchor_s[t] = sc_a
        if t >= 168:
            z_now = zl_mat[t, S17_TO_I[sc_a]]
            z_prev = zl_mat[t - 168, S17_TO_I[sc_a]]
            if np.isfinite(z_now) and np.isfinite(z_prev) and z_prev > 1e-8:
                wk_slp[t] = (z_now - z_prev) / z_prev * 100.0
    return anchor_s, wk_slp


def compute_zb1_bear_defense_gate(
    t5_states: np.ndarray,
    wk_slp_anchor: np.ndarray,
    c_zl_exp_38: Optional[np.ndarray] = None,
    wk_thr: float = -1.50,
    zlexp_max: Optional[float] = None,
) -> np.ndarray:
    """
    Strictly causal Track Z-B1 Bear-Defense boolean allow mask:
      - Blocks entries only when T5 == 'LEAD_TURN_BEAR' AND finite `wk_slp_anchor < wk_thr`.
      - When `zlexp_max` is provided, also requires finite `c_zl_exp_38 <= zlexp_max`.
    """
    n = len(t5_states)
    allow = np.ones(n, dtype=bool)
    t5_bear = (np.asarray(t5_states, dtype=object) == "LEAD_TURN_BEAR")
    wk_bad = np.isfinite(wk_slp_anchor) & (wk_slp_anchor < float(wk_thr))
    allow &= ~(t5_bear & wk_bad)
    if zlexp_max is not None:
        if c_zl_exp_38 is None:
            raise ValueError("c_zl_exp_38 must be provided when zlexp_max is set")
        allow &= np.isfinite(c_zl_exp_38) & (c_zl_exp_38 <= float(zlexp_max))
    return allow


def verify_exp162_invariants(
    close: np.ndarray, high: np.ndarray, low: np.ndarray, atr: np.ndarray, t_cut: int = 1100
) -> dict:
    """Verify positivity, dual sign-flip symmetry (< 1e-12), and zero-lookahead (== 0.0)."""
    P = compute_base_zlema_pyramid(close, high, low, atr)
    EX = compute_extended_pyramid_features(P, close, atr)
    ZLBB = compute_zlbb_system(P, close, atr)
    OSC = compute_oscillator_pyramids(close, high, low)

    assert np.all(ZLBB["sig_logzl_mat"][np.isfinite(ZLBB["sig_logzl_mat"])] > 0.0)
    assert np.all(ZLBB["sig_zmad_mat"][np.isfinite(ZLBB["sig_zmad_mat"])] > 0.0)

    # Dual Sign-Flip Symmetry
    Pn = compute_base_zlema_pyramid(-close, -low, -high, atr)
    EX_n = compute_extended_pyramid_features(Pn, -close, atr)
    ZLBB_n = compute_zlbb_system(Pn, -close, atr)
    OSC_n = compute_oscillator_pyramids(-close, -low, -high)

    max_sym_err = 0.0
    for a, b, sgn in [
        (EX["shear_phi"], EX_n["shear_phi"], -1.0),
        (EX["net_energy_14"], EX_n["net_energy_14"], -1.0),
        (EX["sr_asym"], EX_n["sr_asym"], -1.0),
        (ZLBB["c_bb_dir_38"], ZLBB_n["c_bb_dir_38"], -1.0),
        (OSC["c_stoch_12"], OSC_n["c_stoch_12"], -1.0),
        (OSC["c_zafs_12"], OSC_n["c_zafs_12"], -1.0),
        (ZLBB["c_zl_exp_38"], ZLBB_n["c_zl_exp_38"], +1.0),
        (ZLBB["sig_logzl_mat"], ZLBB_n["sig_logzl_mat"], +1.0),
        (OSC["afs_compression"], OSC_n["afs_compression"], +1.0),
        (EX["e_dn_14"], EX_n["e_up_14"], +1.0),
        (ZLBB["c_bb_lo_38"], ZLBB_n["c_bb_up_38"], -1.0),
    ]:
        fin = np.isfinite(a)
        assert np.array_equal(np.isnan(a), np.isnan(b))
        err = float(np.max(np.abs(a[fin] - sgn * b[fin]))) if fin.any() else 0.0
        max_sym_err = max(max_sym_err, err)
        assert err < 1e-12, f"Symmetry error {err}"

    # Zero-Lookahead Perturbation
    c_p, h_p, l_p, a_p = close.copy(), high.copy(), low.copy(), atr.copy()
    c_p[t_cut + 1 :] = c_p[t_cut + 1 :] * 1.45 + 12345.0
    h_p[t_cut + 1 :] = h_p[t_cut + 1 :] * 1.45 + 12345.0
    l_p[t_cut + 1 :] = l_p[t_cut + 1 :] * 1.45 + 12345.0
    a_p[t_cut + 1 :] = a_p[t_cut + 1 :] * 1.65 + 30.0
    Pp = compute_base_zlema_pyramid(c_p, h_p, l_p, a_p)
    EX_p = compute_extended_pyramid_features(Pp, c_p, a_p)
    ZLBB_p = compute_zlbb_system(Pp, c_p, a_p)
    OSC_p = compute_oscillator_pyramids(c_p, h_p, l_p)

    max_la = 0.0
    for o_arr, p_arr in (
        (EX["e_dn_14"], EX_p["e_dn_14"]),
        (ZLBB["c_zl_exp_38"], ZLBB_p["c_zl_exp_38"]),
        (ZLBB["c_bb_up_38"], ZLBB_p["c_bb_up_38"]),
        (OSC["c_zafs_12"], OSC_p["c_zafs_12"]),
        (OSC["c_stoch_12"], OSC_p["c_stoch_12"]),
    ):
        a1 = o_arr[: t_cut + 1]
        a2 = p_arr[: t_cut + 1]
        assert np.array_equal(np.isnan(a1), np.isnan(a2))
        fin = np.isfinite(a1)
        if fin.any():
            d = float(np.max(np.abs(a1[fin] - a2[fin])))
            max_la = max(max_la, d)
            assert d == 0.0, f"Lookahead error {d}"

    return {
        "passed": True,
        "t_cut": int(t_cut),
        "max_lookahead_diff": float(max_la),
        "max_dual_signflip_err": float(max_sym_err),
    }
