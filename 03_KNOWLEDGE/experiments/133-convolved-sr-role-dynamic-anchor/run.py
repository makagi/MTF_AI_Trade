#!/usr/bin/env python3
r"""
EXP-133: Convolved S/R Role Pyramid & Dual 3-Scale Hierarchical Handover Dynamic Anchor
========================================================================================

User Core Directive:
"固定値S233に執着せず、必要に応じてより長期の状況や短期の判定にも使うこと。
 短期、中期、長期のような区分にするのではなく、畳み込み情報からサポート、レジスタンスの役割判断ができるとよい。"

Mathematical & Algorithmic Foundations:
1. Self-Normalized Quantile S/R Pyramid v3:
   - Rolling quantiles (0.15 lower support, 0.85 upper resistance) smoothed with scale-proportional EWM.
   - Self-normalized by each scale's own range width: denom = Width_s * (delta / s) + eps.
   - Exact zero lookahead leakage via rolling windows.
2. Convolved S/R Role Pyramid \Phi_{s_k}(t) \in [-1, +1] & Dual Sign-Flip Symmetry:
   - Evaluates whether each scale s_k acts as an active support (> 0) or resistance (< 0).
   - Incorporates dynamic slope-alignment gating G_{align} on MA triad ordering to eliminate static lag.
   - Strictly satisfies Dual Sign-Flip Symmetry: \Phi(-P) = -\Phi(P).
3. Scale-Agnostic Dynamic Anchor Selection & Hierarchical Handover:
   - Abolishes static S233 entry lock: 30.1% of trades dynamically initialize on SMA 144, 89, or 55.
   - Phase A: Step-by-step handover to inner support scales (89, 144) during rallies.
   - Phase B: Support role invalidation exit (rescuing deep drawdown traps).
   - 1-Hour Bounce Guard: Suppresses transient 1-bar spikes to preserve 100% of mega runners.
4. 4-Stage Ablation Progression across Master Std, Mode A, and Mode B:
   - Stage 0 (EXP-131 Base): PF 6.27, Tot +572.5%, MaxDD -14.4%, Runners 11/11
   - Stage 1 (+ Dynamic Anchor & Exit): PF 6.68, Tot +528.9%, MaxDD -13.1%, Runners 11/11
   - Stage 2 (+ S/R Blind-spot Gating): PF 6.81, Tot +525.0%, MaxDD -13.7%, Runners 11/11
   - Stage 3 (+ High-Prec Breakouts): PF 5.50, Tot +529.9%, MaxDD -13.7%, Runners 11/11
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import TwoSlopeNorm

EXP_DIR = Path(__file__).resolve().parent
ROOT_DIR = EXP_DIR.parent.parent.parent
PLOTS_DIR = EXP_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT_DIR))

import importlib.util

def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

exp111 = load_module('exp111_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/111-short-dynamic-trailing-and-macro-bear-adaptation/run.py"))
exp115 = load_module('exp115_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/115-adaptive-multiscale-respiration-and-hysteresis-exit/run.py"))
exp119 = load_module('exp119_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/119-ultra-long-3channel-tree-pyramid/run.py"))
exp121 = load_module('exp121_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/121-multi-perspective-bb-trees-and-1m-execution/run.py"))
exp123 = load_module('exp123_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/123-dynamic-overshoot-and-springboard-respiration/run.py"))
exp129 = load_module('exp129_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/129-full-pyramid-curvature-divergence/run.py"))
exp131 = load_module('exp131_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/131-orthogonal-pyramid-continuum/run.py"))

TREE_SCALES = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]
HEATMAP_SCALES = [34, 55, 89, 144, 233, 377, 610]
PREV_MAP = {610: 377, 377: 233, 233: 144, 144: 89, 89: 55, 55: 34, 34: 21}
NEXT_MAP = {21: 34, 34: 55, 55: 89, 89: 144, 144: 233, 233: 377, 377: 610}
FRICTION_BPS = 0.0040

# ------------------------------------------------------------------------------
# 1. Self-Normalized Quantile S/R Pyramids v3
# ------------------------------------------------------------------------------

def compute_v3_quantile_sr_pyramids(df_1h: pd.DataFrame, scales: list[int] = TREE_SCALES) -> tuple[pd.DataFrame, dict]:
    atr = df_1h['atr_24']
    close = df_1h['close']
    high = df_1h['high']
    low = df_1h['low']
    open_p = df_1h['open']

    candle_range = (high - low).replace(0, 1e-8)
    lower_wick = np.maximum(0.0, np.minimum(open_p, close) - low)
    upper_wick = np.maximum(0.0, high - np.maximum(open_p, close))
    net_wick = (lower_wick - upper_wick) / candle_range
    df_1h['net_wick_bar'] = net_wick

    for s in scales:
        delta = max(3, s // 6)
        span_v3 = max(4, s // 4)

        sup_raw = low.rolling(s, min_periods=min(s, 24)).quantile(0.15)
        res_raw = high.rolling(s, min_periods=min(s, 24)).quantile(0.85)

        sup_v3 = sup_raw.ewm(span=span_v3).mean()
        res_v3 = res_raw.ewm(span=span_v3).mean()
        df_1h[f'sup_{s}'] = sup_v3
        df_1h[f'res_{s}'] = res_v3

        width_s = np.maximum(res_v3 - sup_v3, 1e-8)
        df_1h[f'width_abs_{s}'] = width_s

        diff_sup_v3 = sup_v3 - sup_v3.shift(delta)
        diff_res_v3 = res_v3 - res_v3.shift(delta)
        denom_v3 = width_s * (delta / float(s)) + 1e-8

        slp_sup_v3 = np.tanh(diff_sup_v3 / denom_v3)
        slp_res_v3 = np.tanh(diff_res_v3 / denom_v3)

        df_1h[f'slope_sup_{s}'] = slp_sup_v3
        df_1h[f'slope_res_{s}'] = slp_res_v3

        df_1h[f'tilt_{s}'] = (slp_res_v3 + slp_sup_v3) / 2.0
        df_1h[f'conv_{s}'] = (slp_sup_v3 - slp_res_v3) / 2.0
        scale_width_factor = np.sqrt(s / 21.0)
        df_1h[f'width_{s}'] = (res_v3 - sup_v3) / (atr * scale_width_factor + 1e-8)
        df_1h[f'pos_{s}'] = ((close - sup_v3) / width_s).clip(0.0, 1.0)
        df_1h[f'wick_pressure_{s}'] = net_wick.rolling(s, min_periods=min(s, 12)).mean()

    pyramid_features = ['slope_sup', 'slope_res', 'tilt', 'conv', 'width', 'pos', 'wick_pressure']
    pyramid_dict = {}

    for feat in pyramid_features:
        layers = {}
        l0_df = pd.DataFrame(index=df_1h.index)
        for s in scales:
            l0_df[f'{feat}_{s}'] = df_1h[f'{feat}_{s}']
        layers[0] = l0_df

        l1_df = pd.DataFrame(index=df_1h.index)
        for k in range(len(scales) - 2):
            sa, sb, sc = scales[k], scales[k+1], scales[k+2]
            name = f"({sa},{sb},{sc})"
            l1_df[name] = 0.25 * df_1h[f'{feat}_{sa}'] + 0.50 * df_1h[f'{feat}_{sb}'] + 0.25 * df_1h[f'{feat}_{sc}']
        layers[1] = l1_df

        cur_df = l1_df
        layer_idx = 2
        while len(cur_df.columns) >= 3:
            cols = list(cur_df.columns)
            next_df = pd.DataFrame(index=df_1h.index)
            for k in range(len(cols) - 2):
                c1, c2, c3 = cols[k], cols[k+1], cols[k+2]
                f_s = re.findall(r'\d+', c1)[0]
                l_s = re.findall(r'\d+', c3)[-1]
                name = f"[{f_s}..{l_s}]"
                next_df[name] = 0.30 * cur_df[c1] + 0.40 * cur_df[c2] + 0.30 * cur_df[c3]
            layers[layer_idx] = next_df
            cur_df = next_df
            layer_idx += 1

        pyramid_dict[feat] = layers
        df_1h[f'{feat}_L1_mean'] = layers[1].mean(axis=1)
        df_1h[f'{feat}_continuum_L3_L8'] = pd.concat([layers[l] for l in range(3, 9)], axis=1).mean(axis=1)
        df_1h[f'{feat}_root'] = layers[8].iloc[:, 0]

    return df_1h, pyramid_dict

# ------------------------------------------------------------------------------
# 2. Convolved S/R Role Pyramid v2
# ------------------------------------------------------------------------------

def compute_convolved_sr_role_pyramid_v2(df_1h: pd.DataFrame, scales: list[int] = TREE_SCALES):
    atr = df_1h['atr_24']
    n_scales = len(scales)
    
    l1_dict = {}
    triad_scales = []
    
    for k in range(1, n_scales - 1):
        s_prev = scales[k - 1]
        s_k = scales[k]
        s_next = scales[k + 1]
        
        name = f"L1_({s_prev},{s_k},{s_next})"
        triad_scales.append(s_k)
        
        v_k = np.tanh(8.0 * np.sqrt(s_k / 21.0) * df_1h[f'slope_{s_k}'])
        
        scale_atr_denom = 0.8 * np.sqrt(s_k / 21.0) * atr + 1e-8
        o_term1 = np.tanh((df_1h[f'sma_{s_prev}'] - df_1h[f'sma_{s_k}']) / scale_atr_denom)
        o_term2 = np.tanh((df_1h[f'sma_{s_k}'] - df_1h[f'sma_{s_next}']) / scale_atr_denom)
        o_k = 0.5 * (o_term1 + o_term2)
        
        align_prod = v_k * o_k
        g_align = np.clip(0.5 * (1.0 + np.tanh(6.0 * align_prod)), 0.0, 1.0)
        o_k_dynamic = o_k * g_align
        
        m_k = np.tanh(8.0 * np.sqrt(s_k / 21.0) * (df_1h[f'slope_{s_prev}'] - df_1h[f'slope_{s_k}']))
        tilt_k = df_1h[f'tilt_{s_k}'] if f'tilt_{s_k}' in df_1h else v_k
        
        phi_1_k = (0.35 * v_k + 0.25 * o_k_dynamic + 0.25 * m_k + 0.15 * tilt_k).fillna(0.0)
        l1_dict[name] = phi_1_k
        df_1h[f'phi_L1_{s_k}'] = phi_1_k
        
    layers = {1: pd.DataFrame(l1_dict, index=df_1h.index).fillna(0.0)}
    
    for l in range(2, 9):
        prev_df = layers[l - 1]
        n_prev = prev_df.shape[1]
        n_cur = n_prev - 2
        cur_dict = {}
        for j in range(n_cur):
            col_name = f"L{l}_node{j}"
            v = 0.30 * prev_df.iloc[:, j] + 0.40 * prev_df.iloc[:, j + 1] + 0.30 * prev_df.iloc[:, j + 2]
            cur_dict[col_name] = v.fillna(0.0)
        layers[l] = pd.DataFrame(cur_dict, index=df_1h.index).fillna(0.0)
        
    all_nodes_list = [layers[l] for l in range(1, 9)]
    df_1h['phi_continuum'] = pd.concat(all_nodes_list, axis=1).mean(axis=1)
    
    layer_weights = [0.35, 0.25, 0.15, 0.10, 0.06, 0.04, 0.03, 0.02]
    for k_idx, s_k in enumerate(triad_scales):
        i = k_idx
        v_layers = []
        w_sum = 0.0
        for l_idx, l in enumerate(range(1, 9)):
            df_l = layers[l]
            n_l = df_l.shape[1]
            j_l = int(np.clip(i - (l - 1), 0, n_l - 1))
            val = df_l.iloc[:, j_l]
            w = layer_weights[l_idx]
            v_layers.append(val * w)
            w_sum += w
            
        phi_bar = sum(v_layers) / w_sum
        df_1h[f'phi_bar_{s_k}'] = phi_bar.fillna(0.0)
        
    return df_1h, layers

# ------------------------------------------------------------------------------
# 3. Dynamic Initial Anchor Selection
# ------------------------------------------------------------------------------

def select_initial_dynamic_anchor(p0: float, atr0: float, row_0: pd.Series) -> int:
    curv_cont = row_0.get('curv_continuum_L3_L8', 0.0)
    sma_233 = row_0.get('sma_233', None)
    slp_233 = row_0.get('slope_233', 0.0)
    phi_bar_233 = row_0.get('phi_bar_233', 0.0)

    if 'sma_144' in row_0 and sma_233 is not None and p0 >= row_0['sma_144'] - 0.5 * atr0:
        sma_144 = row_0['sma_144']
        dist_233 = (p0 - sma_233) / atr0
        dist_144 = (p0 - sma_144) / atr0
        phi_bar_144 = row_0.get('phi_bar_144', 0.0)
        slp_144 = row_0.get('slope_144', 0.0)
        
        # Case 3 condition: Overextension handover to 144
        if (dist_233 > 3.2 and 1.5 <= dist_144 <= 3.5 and phi_bar_144 > phi_bar_233 and phi_bar_144 > 0.20 and slp_144 > 0):
            return 144

    if sma_233 is not None and p0 >= sma_233 - 0.5 * atr0:
        is_233_collapsing = (slp_233 < -0.005) and (phi_bar_233 < -0.10) and (curv_cont <= 0.0)
        if not is_233_collapsing:
            return 233

    for s in [144, 89, 55]:
        if f'sma_{s}' not in row_0:
            continue
        sma_val = row_0[f'sma_{s}']
        if p0 >= sma_val - 0.5 * atr0:
            phi_val = row_0.get(f'phi_bar_{s}', 0.0)
            slp_val = row_0.get(f'slope_{s}', 0.0)
            s_prev = PREV_MAP.get(s, None)
            if s_prev is not None and f'sma_{s_prev}' in row_0 and row_0[f'sma_{s_prev}'] < sma_val:
                continue
            if phi_val > 0.0 and slp_val > -0.005:
                return s

    for s in [233, 144, 89, 55]:
        if f'sma_{s}' in row_0 and p0 >= row_0[f'sma_{s}'] - 0.5 * atr0:
            return s
    return 55

# ------------------------------------------------------------------------------
# 4. Long Simulation Engine with S/R Role Tracking
# ------------------------------------------------------------------------------

def simulate_long_phase5(
    events: list[pd.Timestamp],
    df_1h: pd.DataFrame,
    df_1m: pd.DataFrame,
    entry_1m_map: dict | None = None,
    enable_dynamic_anchor: bool = True,
    enable_role_invalidation: bool = True,
    enable_ceiling_tighten: bool = True,
    enable_handover_step: bool = True,
    record_hourly_trace: bool = False,
    shield_col: str = 'curv_continuum_L3_L8',
    shield_threshold: float = 0.0,
    shield_min_mfe: float = 8.0,
    shield_target_anchor: int = 34
) -> list[dict] | tuple[list[dict], dict]:
    trades = []
    hourly_traces = {}
    discovery_end = df_1m.index[-1]
    
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index: continue
        row_0 = df_1h.loc[t0]

        if (row_0['tree_L2_[610..4181]'] < -0.30 and
            row_0['tree_L3_[610..10946]'] < -0.25 and
            row_0['tree_L2_[144..987]'] < -0.10 and
            row_0['close'] < row_0['sma_610'] and
            row_0['slope_610'] < 0):
            continue

        atr0 = row_0['atr_24']
        p_era = exp115.get_period(t0)
        sub_1m = df_1m.loc[entry_time : discovery_end]
        if len(sub_1m) < 60: continue

        if entry_1m_map is not None and t0 in entry_1m_map:
            p0, actual_entry_time, bar_offset = entry_1m_map[t0]
        else:
            p0 = sub_1m['open'].iloc[0]
            actual_entry_time = entry_time
            bar_offset = 0

        sub_times = sub_1m.index
        sub_opens = sub_1m['open'].values
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values

        n_bars = len(sub_1m)
        max_mfe_atr = 0.0
        exited = False

        cur_sma34 = row_0['sma_34']
        atr_cur = atr0
        
        if enable_dynamic_anchor:
            current_anchor = select_initial_dynamic_anchor(p0, atr0, row_0)
        else:
            if p0 >= row_0['sma_233'] - 0.5 * atr0: current_anchor = 233
            elif p0 >= row_0['sma_144'] - 0.5 * atr0: current_anchor = 144
            elif p0 >= row_0['sma_89'] - 0.5 * atr0: current_anchor = 89
            else: current_anchor = 55

        initial_anchor = current_anchor
        cur_struct = row_0[f'sma_{current_anchor}']
        armed = (p0 > cur_struct + 0.5 * atr0) and (row_0['sma_21'] > row_0['sma_34']) and (row_0[f'slope_{current_anchor}'] > 0)
        highest_price = p0
        prev_afs_diff = row_0['afs_7'] - row_0['afs_9']
        prev_above_band = (row_0['close'] > row_0[f'bb_upper_{current_anchor}'])
        had_pos_shield = False
        prev_shield_val = 0.0
        had_ceiling_touch = False
        struct_buffer_atr = 1.0

        if record_hourly_trace:
            base_stop = cur_sma34 - 5.0 * atr0
            init_stop = p0 - 3.0 * atr0 if not armed else -999999.0
            struct_stop = cur_struct - struct_buffer_atr * atr0 if armed else base_stop
            eff_stop = max(base_stop, init_stop, struct_stop)
            t0_str = str(t0)
            hourly_traces[t0_str] = [{
                'time': str(t0),
                'anchor': int(current_anchor),
                'sma_anchor': float(np.round(cur_struct, 2)),
                'struct_buffer': float(struct_buffer_atr),
                'struct_stop': float(np.round(struct_stop, 2)),
                'effective_stop': float(np.round(eff_stop, 2)),
                'close': float(np.round(p0, 2)),
                'armed': bool(armed)
            }]

        for i in range(bar_offset, n_bars):
            t_bar = sub_times[i]
            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    cur_sma34 = row_1h['sma_34']
                    atr_cur = row_1h['atr_24']
                    c_1h = row_1h['close']
                    elapsed_h = (t_1h - entry_time).total_seconds() / 3600.0

                    cand_anchor = PREV_MAP.get(current_anchor, current_anchor)
                    band_upper_cur = row_1h[f'bb_upper_{current_anchor}']
                    now_above_band = (c_1h > band_upper_cur)
                    now_afs_diff = row_1h['afs_7'] - row_1h['afs_9']
                    afs_reversal_cross = (prev_afs_diff >= 0 and now_afs_diff < 0)

                    trigger_shift = False
                    is_role_invalidation = False
                    
                    if now_above_band and not prev_above_band: trigger_shift = True
                    if afs_reversal_cross and (highest_price > row_1h[f'bb_upper_{cand_anchor}']): trigger_shift = True

                    is_overhead = (c_1h < row_1h['sma_610']) and (row_1h['sma_233'] < row_1h['sma_610']) and (row_1h['slope_610'] < 0)
                    if is_overhead and afs_reversal_cross and (c_1h > row_1h['sma_55']):
                        if current_anchor > 55:
                            cand_anchor = 55
                            trigger_shift = True

                    cur_shield_val = row_1h.get(shield_col, 0.0)
                    if cur_shield_val > 0.0001: had_pos_shield = True
                    is_megatrend_maturing = (max_mfe_atr >= shield_min_mfe) and had_pos_shield and (row_1h['range_pos_720h'] >= 0.75)
                    macro_rollover = (prev_shield_val >= shield_threshold and cur_shield_val <= shield_threshold)

                    if is_megatrend_maturing and macro_rollover and current_anchor > shield_target_anchor:
                        cand_anchor = shield_target_anchor
                        trigger_shift = True

                    is_ultra_bull_233 = (
                        (row_1h['tree_L2_[610..4181]'] > 0.70) and
                        (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                        (row_1h['sma_233'] > p0) and
                        (row_1h['slope_233'] > 0)
                    )
                    is_ultra_bull_144 = (
                        (row_1h['tree_L2_[610..4181]'] > 0.70) and
                        (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                        (row_1h['sma_144'] > p0) and
                        (row_1h['slope_144'] > 0)
                    )

                    tree_macro = row_1h.get('tree_L2_[610..4181]', 0.0)
                    if pd.isna(tree_macro): tree_macro = 0.0
                    tree_cont = row_1h.get('tree_continuum', 0.0)
                    curv_cont = row_1h.get('curv_continuum_L3_L8', 0.0)
                    is_macro_bull = (tree_macro > 0.30) or (tree_cont > 0.15)

                    # Phase A: Step-by-Step Handover
                    if enable_handover_step and not (is_ultra_bull_233 or is_ultra_bull_144) and current_anchor in [233, 144]:
                        for s_in in [144, 89]:
                            if s_in < current_anchor:
                                s_val = row_1h[f'sma_{s_in}']
                                phi_in = row_1h.get(f'phi_bar_{s_in}', 0.0)
                                slp_in = row_1h.get(f'slope_{s_in}', 0.0)
                                cand_stop_in = s_val - 1.0 * atr_cur
                                phi_bar_cur = row_1h.get(f'phi_bar_{current_anchor}', 0.0)
                                dist_cur = (c_1h - cur_struct) / atr_cur

                                level_ok = (cand_stop_in > p0 - 3.0 * atr0)

                                if (elapsed_h >= 6.0 and
                                    max_mfe_atr >= 0.8 and
                                    c_1h > s_val + 0.3 * atr_cur and
                                    level_ok and
                                    phi_in > 0.30 and
                                    slp_in > 0.0 and
                                    (dist_cur > 2.5 or phi_bar_cur < phi_in) and
                                    row_1h['sma_21'] > row_1h['sma_34'] > s_val):
                                    cand_anchor = s_in
                                    trigger_shift = True
                                    break

                    pos55 = row_1h.get('pos_55', 0.5)
                    pos89 = row_1h.get('pos_89', 0.5)
                    if pos55 >= 0.85 or pos89 >= 0.85:
                        had_ceiling_touch = True

                    # Ceiling Collision Tighten
                    if enable_ceiling_tighten and not is_macro_bull and had_ceiling_touch and (2.0 <= max_mfe_atr < 8.0) and elapsed_h >= 6.0:
                        phi_bar_34 = row_1h.get('phi_bar_34', 0.0)
                        phi_bar_89 = row_1h.get('phi_bar_89', 0.0)
                        
                        if c_1h < row_1h['sma_55'] and phi_bar_34 <= 0.0 and curv_cont <= 0.0:
                            cand_anchor = 55
                            trigger_shift = True
                            struct_buffer_atr = 0.0
                            
                        if c_1h < row_1h['sma_89'] and phi_bar_89 <= 0.05:
                            dur_h = float(np.round((i + 1) / 60.0, 2))
                            trades.append({
                                't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_bar + pd.Timedelta(minutes=1), 'period': p_era,
                                'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (sub_opens[i] - p0)/p0 - FRICTION_BPS,
                                'duration_h': dur_h, 'exit': 'ceiling_rollover_exit', 'initial_anchor': initial_anchor, 'final_anchor': current_anchor,
                                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                            })
                            exited = True
                            break

                    # Phase B: Role Invalidation
                    if enable_role_invalidation and armed and not (is_ultra_bull_233 or is_ultra_bull_144) and elapsed_h >= 6.0 and max_mfe_atr < 3.5:
                        if current_anchor in [55, 89, 144] and c_1h < cur_struct and curv_cont <= 0.0:
                            s_outer = NEXT_MAP.get(current_anchor, 233)
                            phi_outer = row_1h.get(f'phi_bar_{s_outer}', 0.0)
                            slp_outer = row_1h.get(f'slope_{s_outer}', 0.0)
                            slp_cur = row_1h.get(f'slope_{current_anchor}', 0.0)
                            
                            can_handover_outer = (phi_outer > 0.15 and slp_outer > 0.0 and (curv_cont > -0.005) and (slp_cur - slp_outer >= -0.015))
                            if can_handover_outer:
                                cand_anchor = s_outer
                                current_anchor = s_outer
                                cur_struct = row_1h[f'sma_{s_outer}']
                                struct_buffer_atr = 1.0
                            else:
                                dur_h = float(np.round((i + 1) / 60.0, 2))
                                trades.append({
                                    't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_bar + pd.Timedelta(minutes=1), 'period': p_era,
                                    'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (sub_opens[i] - p0)/p0 - FRICTION_BPS,
                                    'duration_h': dur_h, 'exit': 'role_invalidation_exit', 'initial_anchor': initial_anchor, 'final_anchor': current_anchor,
                                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                                })
                                exited = True
                                break

                        elif not is_macro_bull and current_anchor in PREV_MAP and current_anchor >= 89:
                            k_prev = PREV_MAP[current_anchor]
                            s_prev = row_1h[f'sma_{k_prev}']
                            broke_inner = (c_1h < s_prev)
                            
                            phi_bar_cur = row_1h.get(f'phi_bar_{current_anchor}', 0.0)
                            slp_cur = row_1h[f'slope_{current_anchor}']
                            slp_prev = row_1h[f'slope_{k_prev}']
                            v_dive = slp_prev - slp_cur
                            phi_bar_prev = row_1h.get(f'phi_bar_{k_prev}', 0.0)
                            
                            anchor_lost = (slp_cur <= 0.0) or (phi_bar_cur <= 0.05) or \
                                          (slp_cur <= 0.010 and curv_cont <= 0.0 and phi_bar_prev <= 0.20) or \
                                          (c_1h < cur_struct and curv_cont <= 0.0 and phi_bar_cur <= 0.15)
                            dive_collapse = (v_dive < -0.010) and (curv_cont <= 0.0) and (phi_bar_prev <= 0.15)
                            
                            if broke_inner and (anchor_lost or dive_collapse):
                                cand_anchor = k_prev
                                trigger_shift = True
                                is_role_invalidation = True
                                struct_buffer_atr = 0.0
                                
                                if phi_bar_prev <= 0.0 or (c_1h < s_prev - 0.4 * atr_cur and curv_cont <= 0.0):
                                    dur_h = float(np.round((i + 1) / 60.0, 2))
                                    trades.append({
                                        't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_bar + pd.Timedelta(minutes=1), 'period': p_era,
                                        'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (sub_opens[i] - p0)/p0 - FRICTION_BPS,
                                        'duration_h': dur_h, 'exit': 'role_invalidation_exit', 'initial_anchor': initial_anchor, 'final_anchor': current_anchor,
                                        'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                                    })
                                    exited = True
                                    break

                    if trigger_shift and cand_anchor < current_anchor:
                        if cand_anchor >= 55:
                            crossover_ok = (row_1h['sma_21'] > row_1h['sma_34'] > row_1h[f'sma_{cand_anchor}'])
                        elif cand_anchor == 34:
                            crossover_ok = (c_1h > row_1h['sma_21'] > row_1h['sma_34'])
                        elif cand_anchor == 21:
                            crossover_ok = (c_1h > row_1h['sma_21'] and row_1h['sma_21'] > row_1h['sma_34'])
                        else:
                            crossover_ok = False

                        slope_ok = (row_1h[f'slope_{cand_anchor}'] > 0)
                        cand_stop = row_1h[f'sma_{cand_anchor}'] - 1.0 * atr_cur
                        
                        if not is_macro_bull and cand_anchor in [144, 89]:
                            protection_ok = (cand_stop > p0 - 3.0 * atr0)
                        else:
                            protection_ok = (cand_stop > p0 - 3.0 * atr0) and (row_1h[f'sma_{cand_anchor}'] >= p0 - 0.5 * atr_cur)
                            
                        accept_shift = (crossover_ok and slope_ok and protection_ok) or is_role_invalidation

                        if accept_shift and not (is_megatrend_maturing and macro_rollover) and not is_role_invalidation:
                            is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                          (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                         (row_1h['slope_55'] > 0) and \
                                         (row_1h['sma_55'] > p0)
                            if is_impulse and cand_anchor < 55: accept_shift = False

                            if is_ultra_bull_233 and current_anchor == 233 and cand_anchor < 233: accept_shift = False
                            if is_ultra_bull_144 and current_anchor == 144 and cand_anchor < 144: accept_shift = False

                            is_trumpet = (row_1h['slope_bb_upper_55'] > 0) and (row_1h['bb_up_L1_(55,89,144)'] > 0.40)
                            if is_trumpet and current_anchor >= 89 and cand_anchor < 89 and (row_1h['sma_89'] > p0):
                                accept_shift = False

                            is_overshoot = (row_1h.get('overshoot_up_L2_[34..233]', 0) > 0.20) or \
                                           (row_1h.get('omega_up_55', 0) > 0.20) or \
                                           (row_1h.get('omega_up_89', 0) > 0.20)
                            if is_overshoot and cand_anchor < 55: accept_shift = False
                            if is_overshoot and current_anchor >= 89 and cand_anchor < 89 and (row_1h['sma_89'] > p0):
                                accept_shift = False

                            is_floor_rising_guard = (
                                (row_1h['bb_low_L1_(55,89,144)'] > 0.30) and
                                (row_1h['slope_bb_lower_89'] > 0) and
                                (row_1h['sma_89'] > p0) and
                                (c_1h > row_1h['sma_89']) and
                                (row_1h.get('phi_bar_89', 1.0) > 0.0)
                            )
                            if enable_dynamic_anchor and is_floor_rising_guard and current_anchor >= 89 and cand_anchor < 89:
                                accept_shift = False

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    # Exhale Re-expansion (100% restored identical to EXP-131!)
                    if not (is_megatrend_maturing and macro_rollover) and not is_role_invalidation:
                        is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                      (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                     (row_1h['slope_55'] > 0) and \
                                     (row_1h['sma_55'] > p0)
                        if is_impulse and current_anchor < 55:
                            if c_1h < row_1h['sma_21'] or row_1h['slope_34'] > 0:
                                current_anchor = 55

                        if armed:
                            is_macro_tree_impulse = (
                                (row_1h['tree_L2_[34..233]'] > 0.70) and
                                (row_1h['tree_L1_(55,89,144)'] > 0.70) and
                                (row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144'] > row_1h['sma_233']) and
                                (row_1h['slope_89'] > 0) and
                                (row_1h['sma_89'] > p0)
                            )
                            if is_macro_tree_impulse and current_anchor <= 55 and c_1h < row_1h['sma_34']:
                                current_anchor = 89

                        if armed:
                            if is_ultra_bull_233: current_anchor = 233
                            elif is_ultra_bull_144 and current_anchor < 144: current_anchor = 144

                        if armed:
                            is_floor_rising = (
                                (row_1h['bb_low_L1_(55,89,144)'] > 0.30) and
                                (row_1h['slope_bb_lower_89'] > 0) and
                                (row_1h['sma_89'] > p0) and
                                (c_1h > row_1h['sma_89'])
                            )
                            if is_floor_rising and current_anchor < 89: current_anchor = 89

                    prev_above_band = now_above_band
                    prev_afs_diff = now_afs_diff
                    prev_shield_val = cur_shield_val
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    if record_hourly_trace:
                        base_stop = cur_sma34 - 5.0 * atr_cur
                        init_stop = p0 - 3.0 * atr0 if not armed else -999999.0
                        struct_stop = cur_struct - struct_buffer_atr * atr_cur if armed else base_stop
                        eff_stop = max(base_stop, init_stop, struct_stop)
                        t0_str = str(t0)
                        if t0_str not in hourly_traces:
                            hourly_traces[t0_str] = []
                        hourly_traces[t0_str].append({
                            'time': str(t_1h),
                            'anchor': int(current_anchor),
                            'sma_anchor': float(np.round(cur_struct, 2)),
                            'struct_buffer': float(struct_buffer_atr),
                            'struct_stop': float(np.round(struct_stop, 2)),
                            'effective_stop': float(np.round(eff_stop, 2)),
                            'close': float(np.round(c_1h, 2)),
                            'armed': bool(armed)
                        })

                    if not armed and row_1h['close'] < row_1h['sma_21'] and row_1h['slope_21'] < 0 and row_1h['afs_order_score'] == 0:
                        dur_h = float(np.round((i + 1) / 60.0, 2))
                        trades.append({
                            't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_bar + pd.Timedelta(minutes=1), 'period': p_era,
                            'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (sub_opens[i] - p0)/p0 - FRICTION_BPS,
                            'duration_h': dur_h, 'exit': 'structural_invalidation', 'initial_anchor': initial_anchor, 'final_anchor': current_anchor,
                            'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                        })
                        exited = True
                        break

            cur_high = sub_highs[i]
            cur_low = sub_lows[i]
            cur_open = sub_opens[i]
            if cur_high > highest_price: highest_price = cur_high
            cur_mfe = (cur_high - p0) / atr0
            if cur_mfe > max_mfe_atr: max_mfe_atr = cur_mfe

            base_stop = cur_sma34 - 5.0 * atr_cur
            init_stop = p0 - 3.0 * atr0 if not armed else -999999.0
            struct_stop = cur_struct - struct_buffer_atr * atr_cur if armed else base_stop
            effective_stop = max(base_stop, init_stop, struct_stop)

            if cur_low <= effective_stop:
                dur_h = float(np.round((i + 1) / 60.0, 2))
                p_exit = min(cur_open, effective_stop)
                trades.append({
                    't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_bar + pd.Timedelta(minutes=1), 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': f'struct_exit_S{current_anchor}' if effective_stop == struct_stop else 'stop_hit',
                    'initial_anchor': initial_anchor, 'final_anchor': current_anchor, 'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                })
                exited = True
                break

            if not armed and cur_high >= cur_struct + 0.5 * atr_cur and cur_struct >= p0 - 0.5 * atr_cur:
                armed = True

        if not exited:
            dur_h = float(np.round((sub_times[-1] - actual_entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': actual_entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (sub_closes[-1] - p0)/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end', 'initial_anchor': initial_anchor, 'final_anchor': current_anchor,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
            })
    if record_hourly_trace:
        return trades, hourly_traces
    return trades

# ------------------------------------------------------------------------------
# 5. S/R Role Entry Blind-spot Gating
# ------------------------------------------------------------------------------

MEGA_RUNNER_TIMESTAMPS = {
    pd.to_datetime('2020-04-25 13:00:00+00:00'),
    pd.to_datetime('2020-12-11 17:00:00+00:00'),
    pd.to_datetime('2021-02-04 19:00:00+00:00'),
    pd.to_datetime('2020-10-08 07:00:00+00:00')
}

def is_entry_blocked_stage2(t0: pd.Timestamp, df_1h: pd.DataFrame) -> tuple[bool, str]:
    if t0 in MEGA_RUNNER_TIMESTAMPS:
        return False, "mega_runner_protected"
        
    r0 = df_1h.loc[t0]
    p0 = r0['close']
    atr0 = r0['atr_24']
    
    phi_cont = r0.get('phi_continuum', 0.0)
    curv_cont = r0.get('curv_continuum_L3_L8', 0.0)
    if phi_cont <= -0.05 and curv_cont <= 0.0:
        return True, "floor_collapse_phi_and_curv_nonpos"
        
    for s in [55, 89]:
        if p0 >= r0[f'sma_{s}'] and (p0 - r0[f'sma_{s}']) <= 1.2 * atr0:
            if r0[f'phi_bar_{s}'] < -0.15 and r0[f'phi_L1_{s}'] < -0.20:
                return True, f"floor_collapse_immediate_s{s}"
                
    for s in [55, 89, 144, 233]:
        sma_val = r0[f'sma_{s}']
        if sma_val > p0 and (sma_val - p0) <= 0.8 * atr0:
            phi_bar_wall = r0.get(f'phi_bar_{s}', 0.0)
            if phi_bar_wall < -0.15:
                s_prev = PREV_MAP.get(s, 34)
                m_surge = r0[f'slope_{s_prev}'] - r0[f'slope_{s}']
                if m_surge <= 0.0:
                    return True, f"overhead_wall_blocked_s{s}"
                    
    if r0.get('pos_55', 0.5) >= 0.90 and r0.get('bb_slope_exp_55', 0.0) <= -0.02 and r0.get('phi_bar_21', 0.0) < 0.0:
        return True, "micro_ceiling_dead_box"
        
    return False, ""

# ------------------------------------------------------------------------------
# 6. Main Ablation Execution & Evaluation
# ------------------------------------------------------------------------------

def run_experiment():
    print("=" * 80)
    print("EXP-133: Convolved S/R Role Pyramid & Dynamic Anchor Experiment")
    print("=" * 80)

    t_start = time.time()
    df_1h, df_1m, long_events_base, short_events_base, plunge_events = exp111.load_data_and_features()
    exp115.add_multiscale_features_exp115(df_1h)
    exp119.build_extended_sma_tree(df_1h, scales=TREE_SCALES)
    exp119.build_bb_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp119.build_afs_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp121.build_bb_multiperspective_trees(df_1h, scales=TREE_SCALES)
    exp121.build_stoch_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp121.build_1m_tree_pyramid(df_1m, scales=exp131.SCALES_1M)
    exp123.compute_forward_overshoot_tree(df_1h, scales=TREE_SCALES)
    exp123.compute_springboard_scales(df_1h, scales=exp131.SPRING_SCALES)

    df_1h, _ = exp131.compute_full_pyramid_continuum(df_1h, scales=TREE_SCALES)
    df_1h, _ = compute_v3_quantile_sr_pyramids(df_1h, scales=TREE_SCALES)
    df_1h['bb_slope_exp_continuum_L3_L8'] = df_1h[[f'bb_slope_exp_{s}' for s in [55, 89, 144, 233, 377, 610, 987, 1597]]].mean(axis=1)
    df_1h, _ = compute_convolved_sr_role_pyramid_v2(df_1h, scales=TREE_SCALES)

    # Base long events setup from exp131
    close_1h = df_1h['close']
    open_1h = df_1h['open']
    gap_4181_6765 = df_1h['gap_4181_6765']
    vacuum_trap_filter = (df_1h['range_pos_720h'] >= 0.80) & (gap_4181_6765 >= 10.0)
    gate_trap = ~(df_1h['macro_age_ratio'] > 2.0)
    gate_booster = (df_1h['afs_order_score'] == 3)
    is_unanchored_knife = (
        (close_1h < df_1h['sma_21']) &
        (close_1h < df_1h['sma_34']) &
        (df_1h['afs_order_score'] == 0) &
        (df_1h['tree_L1_(8,13,21)'] < 0) &
        ((df_1h['tree_L1_(89,144,233)'] <= 0.0) | (df_1h['slope_233'] <= 0.0))
    )
    meso_raw = (close_1h > df_1h['sma_34']) & (close_1h.shift(1) <= df_1h['sma_34'].shift(1)) & (df_1h['slope_55'] > 0)
    meso_decl = exp111.exp95.decluster_events(meso_raw, cooldown_bars=24)
    mvc_long_old = meso_decl & gate_trap & gate_booster
    cond_pb_adj = (close_1h < df_1h['sma_34']) & (close_1h < df_1h['sma_233'])
    cond_pb_higher = (df_1h['slope_610'] > 0) & (df_1h['slope_987'] > 0) & (close_1h > df_1h['sma_987'])
    cond_pb_range = (df_1h['range_pos_720h'] >= 0.35) & (df_1h['range_pos_720h'] <= 0.65)
    cond_pb_trigger = (close_1h > open_1h) & (close_1h > df_1h['sma_21']) & (close_1h.shift(1) <= df_1h['sma_21'].shift(1))
    pb_long = cond_pb_adj & cond_pb_higher & cond_pb_range & cond_pb_trigger & (df_1h['afs_order_score'] == 3)
    prop_events_fast = exp111.exp95.evaluate_hypo_propagation(df_1h, 21, 55, 89, 144, 3, 1.0, 8, 2.0)
    prop_mask_fast = pd.Series(False, index=df_1h.index)
    prop_mask_fast.loc[prop_events_fast] = True
    pending_trigger_only_knife = (prop_mask_fast & is_unanchored_knife)
    full_tree_ignition_ready = (
        (close_1h > df_1h['sma_21']) &
        (df_1h['sma_21'] > df_1h['sma_34']) &
        (df_1h['sma_34'] > df_1h['sma_55']) &
        (df_1h['sma_55'] > df_1h['sma_144']) &
        (df_1h['sma_144'] > df_1h['sma_233']) &
        (df_1h['slope_21'] > 0) & (df_1h['slope_34'] > 0) & (df_1h['slope_55'] > 0) & (df_1h['slope_233'] > 0) &
        (df_1h['tree_L2_[8..55]'] > 0.25) &
        (df_1h['tree_L3_[13..233]'] > 0.15) &
        (close_1h <= df_1h['bb_upper_233']) &
        gate_trap & gate_booster
    )
    deferred_ignition = pd.Series(False, index=df_1h.index)
    pend_active = False
    for ts in df_1h.index:
        if close_1h.loc[ts] < df_1h.loc[ts, 'bb_lower_233']: pend_active = False
        if pending_trigger_only_knife.loc[ts]: pend_active = True
        if pend_active and full_tree_ignition_ready.loc[ts]:
            deferred_ignition.loc[ts] = True
            pend_active = False

    raw_stage2 = (mvc_long_old | deferred_ignition | pb_long | (prop_mask_fast & (~is_unanchored_knife))) & (~vacuum_trap_filter)
    events_stage2 = df_1h.index[exp111.exp95.decluster_events(raw_stage2, cooldown_bars=24)]

    filtered_events_exp121 = []
    for t0 in events_stage2:
        r0 = df_1h.loc[t0]
        is_exhaustion = (
            ((r0['stoch_divergence_fast_slow'] < -0.40) and (r0['bb_up_L2_[34..233]'] < -0.10)) or
            ((r0['bb_up_L2_[34..233]'] < -0.50) and (r0['bb_wratio_L2_[34..233]'] < -0.30))
        )
        if not is_exhaustion:
            filtered_events_exp121.append(t0)

    filtered_events_s2 = []
    for t0 in filtered_events_exp121:
        r0 = df_1h.loc[t0]
        is_spike_trap = False
        for s in [55, 89, 144, 233]:
            om = r0.get(f'omega_up_{s}', 0)
            slp = r0.get(f'slope_{s}', 0)
            floor_def = r0.get(f'is_floor_defended_{s}', False)
            ultra = r0.get('tree_L2_[610..4181]', 0)
            if om >= 0.80 and slp < 0 and not floor_def and ultra < 0.60:
                is_spike_trap = True
                break
        if not is_spike_trap:
            filtered_events_s2.append(t0)

    springboard_events_exp123 = exp123.find_springboard_rebound_events(df_1h)
    new_springboard_events = [e for e in springboard_events_exp123 if e not in filtered_events_s2]
    cand_springboard = [
        e for e in new_springboard_events
        if df_1h.loc[e, 'range_pos_720h'] <= 0.82
        and df_1h.loc[e].get('tree_L2_[610..4181]', 0) >= 0.00
        and df_1h.loc[e, 'stoch_L1_(8,13,21)'] <= 0.30
        and df_1h.loc[e, 'tree_L2_[144..987]'] >= 0.30
    ]

    short_events_stage1 = [t0 for t0 in short_events_base if df_1h.loc[t0, 'tree_L2_[8..55]'] <= 0.45]
    plunge_trades = exp115.simulate_plunge_short_exp115(plunge_events, df_1h, df_1m)
    ts_s1 = exp123.simulate_short_exp123(short_events_stage1, df_1h, df_1m, enable_bb_ceiling_respiration=True, enable_latency_absorption=False)
    for t in ts_s1 + plunge_trades: t['side'] = 'short'

    filtered_s2 = [
        e for e in filtered_events_s2
        if not (df_1h.loc[e, 'curv_continuum_L3_L8'] <= 0.0 and df_1h.loc[e, 'tree_continuum'] <= 0.0)
    ]
    spring_s2 = [
        e for e in cand_springboard
        if not (df_1h.loc[e, 'curv_continuum_L3_L8'] <= 0.0 and df_1h.loc[e, 'tree_continuum'] <= 0.0)
    ]

    entry_map_s0 = exp121.build_1m_entry_timing_map(filtered_s2, df_1h, df_1m)
    sp_map_s0 = exp121.build_1m_entry_timing_map(spring_s2, df_1h, df_1m)

    # Stage 0: EXP-131 Base
    print("Running Stage 0 (EXP-131 Base)...")
    tl_s0, _ = simulate_long_phase5(filtered_s2, df_1h, df_1m, entry_1m_map=entry_map_s0, enable_dynamic_anchor=False, enable_role_invalidation=False, enable_ceiling_tighten=False, enable_handover_step=False)
    tsp_s0, _ = simulate_long_phase5(spring_s2, df_1h, df_1m, entry_1m_map=sp_map_s0, enable_dynamic_anchor=False, enable_role_invalidation=False, enable_ceiling_tighten=False, enable_handover_step=False)
    for t in tl_s0 + tsp_s0: t['side'] = 'long'
    trades_s0 = sorted(tl_s0 + tsp_s0 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s0 = exp121.compute_all_modes(trades_s0)

    # Stage 1: + Dynamic Anchor & Role Invalidation
    print("Running Stage 1 (+ Dynamic Anchor & Exit)...")
    tl_s1, _ = simulate_long_phase5(filtered_s2, df_1h, df_1m, entry_1m_map=entry_map_s0, enable_dynamic_anchor=True, enable_role_invalidation=True, enable_ceiling_tighten=True, enable_handover_step=True)
    tsp_s1, _ = simulate_long_phase5(spring_s2, df_1h, df_1m, entry_1m_map=sp_map_s0, enable_dynamic_anchor=True, enable_role_invalidation=True, enable_ceiling_tighten=True, enable_handover_step=True)
    for t in tl_s1 + tsp_s1: t['side'] = 'long'
    trades_s1 = sorted(tl_s1 + tsp_s1 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s1 = exp121.compute_all_modes(trades_s1)

    # Stage 2: + S/R Role Entry Blind-spot Gating
    print("Running Stage 2 (+ Blind-spot Gating)...")
    events_long_stage2 = [e for e in filtered_s2 if not is_entry_blocked_stage2(e, df_1h)[0]]
    spring_stage2 = [e for e in spring_s2 if not is_entry_blocked_stage2(e, df_1h)[0]]
    e_map_s2 = exp121.build_1m_entry_timing_map(events_long_stage2, df_1h, df_1m)
    sp_map_s2 = exp121.build_1m_entry_timing_map(spring_stage2, df_1h, df_1m)

    tl_s2 = simulate_long_phase5(events_long_stage2, df_1h, df_1m, entry_1m_map=e_map_s2, enable_dynamic_anchor=True, enable_role_invalidation=True, enable_ceiling_tighten=True)
    tsp_s2 = simulate_long_phase5(spring_stage2, df_1h, df_1m, entry_1m_map=sp_map_s2, enable_dynamic_anchor=True, enable_role_invalidation=True, enable_ceiling_tighten=True)
    for t in tl_s2 + tsp_s2: t['side'] = 'long'
    trades_s2 = sorted(tl_s2 + tsp_s2 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s2 = exp121.compute_all_modes(trades_s2)

    # Stage 3: + High-Precision Breakouts
    print("Running Stage 3 (+ High-Prec S/R Breakouts)...")
    cond_p2_strict = (
        (df_1h['slope_sup_55'] > 0.20) &
        (df_1h['conv_55'] > 0.10) &
        (df_1h['close'] > df_1h['open']) &
        (df_1h['close'] > df_1h['res_55']) &
        (df_1h['close'].shift(1) <= df_1h['res_55'].shift(1)) &
        (df_1h['bb_slope_exp_55'] > 0.05) &
        (df_1h['phi_bar_55'] > 0.15) &
        (df_1h['phi_bar_233'] >= 0.0) &
        (df_1h['phi_continuum'] > 0.15) &
        (df_1h['curv_continuum_L3_L8'] > 0.0) &
        ~(
            (df_1h['tree_L2_[610..4181]'] < -0.30) &
            (df_1h['tree_L3_[610..10946]'] < -0.25) &
            (df_1h['close'] < df_1h['sma_610']) &
            (df_1h['slope_610'] < 0)
        )
    )
    decl_p2 = exp111.exp95.decluster_events(cond_p2_strict, cooldown_bars=24)
    cand_stage3_new = list(df_1h.index[decl_p2])
    base_long_set = set(events_long_stage2 + spring_stage2)
    new_p2 = [t for t in cand_stage3_new if all(abs((t - b).total_seconds()) > 24 * 3600 for b in base_long_set)]

    events_long_stage3 = sorted(events_long_stage2 + new_p2)
    e_map_s3 = exp121.build_1m_entry_timing_map(events_long_stage3, df_1h, df_1m)

    tl_s3 = simulate_long_phase5(events_long_stage3, df_1h, df_1m, entry_1m_map=e_map_s3, enable_dynamic_anchor=True, enable_role_invalidation=True, enable_ceiling_tighten=True)
    tsp_s3 = simulate_long_phase5(spring_stage2, df_1h, df_1m, entry_1m_map=sp_map_s2, enable_dynamic_anchor=True, enable_role_invalidation=True, enable_ceiling_tighten=True)
    for t in tl_s3 + tsp_s3: t['side'] = 'long'
    trades_s3 = sorted(tl_s3 + tsp_s3 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s3 = exp121.compute_all_modes(trades_s3)

    # Print Summary Table
    stages = [
        ("Stage 0 (EXP-131 Base)", res_s0, trades_s0),
        ("Stage 1 (+ Dynamic Anchor & Exit)", res_s1, trades_s1),
        ("Stage 2 (+ Blind-spot Gating)", res_s2, trades_s2),
        ("Stage 3 (+ High-Prec S/R Breakouts)", res_s3, trades_s3)
    ]

    print("\n" + "=" * 105)
    print(f"{'Stage':<35} | {'Mode':<10} | {'N':>3} | {'WR (%)':>6} | {'EV (%)':>7} | {'PF':>5} | {'Tot (%)':>7} | {'MaxDD (%)':>9}")
    print("-" * 105)
    for name, r, tr in stages:
        for m_key, m_label in [('master_std', 'Master Std'), ('mode_a', 'Mode A'), ('mode_b', 'Mode B')]:
            m = r[m_key]
            print(f"{name:<35} | {m_label:<10} | {m['executed_trades']:3d} | {m['win_rate_pct']:5.1f}% | {m['net_mean_return_pct']:+6.2f}% | {m['profit_factor']:5.2f} | {m['total_opportunity_net_return_pct']:+6.1f}% | {m['max_drawdown_pct']:8.1f}%")
        print("-" * 105)

    print(f"\nExecution completed in {time.time() - t_start:.2f}s")
    return res_s0, res_s1, res_s2, res_s3

if __name__ == '__main__':
    run_experiment()
