#!/usr/bin/env python3
r"""
EXP-123: Dynamic Scale-Adaptive Envelope Overshoot Projection, Latency Absorption Respiration & Springboard Rebound
===================================================================================================================

This experiment implements and rigorously backtests the multi-scale macro breakout dynamics:
1. Dimensionless Forward Overshoot Projection (\Omega_{S_k}(t)) across 17 Fibonacci scales (8..17711) and 8-layer Tree Pyramid.
2. HYP-123-1: Dynamic Latency Absorption Respiration:
   - When rapid price expansion triggers forward overshoot (\Omega^{\text{up}} > 0.20), freeze structural trailing anchor at S55/S89
     to absorb the inevitable elastic mean-reversion pullback while medium/long MAs catch up, preventing premature stop tightening to S34/S21.
3. HYP-123-2: Dynamic Forward Overshoot Gate & Elastic Pullback Deferral:
   - Defers/blocks chasing parabolic blow-offs when extreme forward overshoot (\Omega^{\text{up}} \ge 0.80) occurs with negative slope
     and undefended floors without ultra-long bull backing, saving drawdown on exhaustion traps.
4. HYP-123-3: Dynamic Floor-Defended Springboard Rebound Entry & Macro Alignment Rescue:
   - Detects rising defended envelope floors (bb_lower_{S_k} > P_{\min, S_k}) after prior overshoot pullbacks.
   - Triggers precision 1m-timed entries on 1h rebound confirmations with macro tree alignment, capturing explosive Wave-2 mega-trends
     (+17.45% in Feb 2024, +31.57% in Feb 2021, +14.51% in Jan 2021).
"""

import os
import sys
import re
import json
import time
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT_DIR = r"D:\work\AI-Trade\MTF_AI_Trade"
BRAIN_DIR = r"C:\Users\masak\.gemini\antigravity\brain\0b00a12f-ee36-4be8-9cfa-5754f1c4f997"
EXP_DIR = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/123-dynamic-overshoot-and-springboard-respiration")
PLOTS_DIR = os.path.join(EXP_DIR, "plots")
sys.path.insert(0, ROOT_DIR)

import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

exp111 = load_module('exp111_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/111-short-dynamic-trailing-and-macro-bear-adaptation/run.py"))
exp115 = load_module('exp115_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/115-adaptive-multiscale-respiration-and-hysteresis-exit/run.py"))
exp119 = load_module('exp119_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/119-ultra-long-3channel-tree-pyramid/run.py"))
exp121 = load_module('exp121_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/121-multi-perspective-bb-trees-and-1m-execution/run.py"))

FRICTION_BPS = 0.0040
TREE_SCALES = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]
SCALES_1M = [8, 13, 21, 34, 55, 89, 144, 233, 377]
SPRING_SCALES = [55, 89, 144, 233, 377, 610, 987]

# ==============================================================================
# Feature Engineering: Dynamic Forward Overshoot & Springboard Calculations
# ==============================================================================

def compute_forward_overshoot_tree(df_1h, scales=TREE_SCALES):
    """
    Computes Dimensionless Forward Overshoot Omega^up_{S_k}(t) and Omega^down_{S_k}(t)
    across all 17 Fibonacci scales, and builds an 8-layer Overlapping Tree Pyramid.
    CRITICAL: Uses no .bfill()!
    """
    close = df_1h['close']
    v_fast = (df_1h['sma_21'] - df_1h['sma_21'].shift(3)) / 3.0

    overshoot_up_df = pd.DataFrame(index=df_1h.index)
    overshoot_down_df = pd.DataFrame(index=df_1h.index)

    for s in scales:
        delta_t = 0.236 * s
        v_up = (df_1h[f'bb_upper_{s}'] - df_1h[f'bb_upper_{s}'].shift(3)) / 3.0
        v_low = (df_1h[f'bb_lower_{s}'] - df_1h[f'bb_lower_{s}'].shift(3)) / 3.0
        bw = df_1h[f'bb_width_{s}'] + 1e-8

        p_proj = close + v_fast * delta_t
        env_up_proj = df_1h[f'bb_upper_{s}'] + v_up * delta_t
        env_low_proj = df_1h[f'bb_lower_{s}'] + v_low * delta_t

        omega_up = (p_proj - env_up_proj) / bw
        omega_down = (env_low_proj - p_proj) / bw

        df_1h[f'omega_up_{s}'] = omega_up
        df_1h[f'omega_down_{s}'] = omega_down
        overshoot_up_df[f'omega_up_{s}'] = np.tanh(omega_up)
        overshoot_down_df[f'omega_down_{s}'] = np.tanh(omega_down)

    # Layer 1: Overlapping 3-Branch Triads
    l1_df = pd.DataFrame(index=df_1h.index)
    for k in range(len(scales) - 2):
        sa, sb, sc = scales[k], scales[k+1], scales[k+2]
        name = f"({sa},{sb},{sc})"
        l1_df[name] = (overshoot_up_df[f'omega_up_{sa}'] + overshoot_up_df[f'omega_up_{sb}'] + overshoot_up_df[f'omega_up_{sc}']) / 3.0
        df_1h[f'overshoot_up_L1_{name}'] = l1_df[name]

    # Layers 2..8: Pyramidal aggregation
    cur_df = l1_df
    layer_idx = 2
    while len(cur_df.columns) >= 3:
        cols = list(cur_df.columns)
        next_df = pd.DataFrame(index=df_1h.index)
        for k in range(len(cols) - 2):
            c1, c2, c3 = cols[k], cols[k+1], cols[k+2]
            f_s = re.findall(r'\d+', c1)[0]
            l_s = re.findall(r'\d+', c3)[-1]
            new_name = f"[{f_s}..{l_s}]"
            next_df[new_name] = 0.30 * cur_df[c1] + 0.40 * cur_df[c2] + 0.30 * cur_df[c3]
            df_1h[f'overshoot_up_L{layer_idx}_{new_name}'] = next_df[new_name]
        cur_df = next_df
        layer_idx += 1

    return df_1h

def compute_springboard_scales(df_1h, scales=SPRING_SCALES):
    """
    Computes scale-matched rolling minimums/maximums, rising floor defense margins,
    and dynamically detects springboard rebound support.
    """
    low = df_1h['low']
    high = df_1h['high']
    close = df_1h['close']
    atr = df_1h['atr_24']

    for s in scales:
        p_min = low.rolling(s, min_periods=min(s, 24)).min()
        p_max = high.rolling(s, min_periods=min(s, 24)).max()
        df_1h[f'p_min_{s}'] = p_min
        df_1h[f'p_max_{s}'] = p_max

        # Floor Defense Margin
        margin_floor = (df_1h[f'bb_lower_{s}'] - p_min) / (atr + 1e-8)
        df_1h[f'margin_floor_{s}'] = margin_floor
        df_1h[f'is_floor_defended_{s}'] = (df_1h[f'bb_lower_{s}'] > p_min) & (df_1h[f'slope_bb_lower_{s}'] >= 0) & (close > df_1h[f'bb_lower_{s}'])

        # Ceiling Defense Margin
        margin_ceiling = (p_max - df_1h[f'bb_upper_{s}']) / (atr + 1e-8)
        df_1h[f'margin_ceiling_{s}'] = margin_ceiling
        df_1h[f'is_ceiling_defended_{s}'] = (df_1h[f'bb_upper_{s}'] < p_max) & (df_1h[f'slope_bb_upper_{s}'] <= 0) & (close < df_1h[f'bb_upper_{s}'])

    def get_spring_scale(row):
        for s_idx, s in enumerate([55, 89, 144, 233, 377, 610]):
            if row[f'is_floor_defended_{s}']:
                prev_s = [34, 55, 89, 144, 233, 377][s_idx]
                if row[f'bb_z_{prev_s}'] < 0.10 or row['close'] <= row[f'sma_{s}'] + 0.2 * row['atr_24']:
                    return s
        return 0

    df_1h['s_spring'] = df_1h.apply(get_spring_scale, axis=1)
    return df_1h

# ==============================================================================
# Simulation Engines with Dynamic Latency Absorption Respiration
# ==============================================================================

def simulate_long_exp123(events, df_1h, df_1m,
                         enable_bb_respiration=True,
                         enable_latency_absorption=True,
                         min_omega_val=0.20,
                         entry_1m_map=None):
    """
    Long Simulation Engine with HYP-123-1 Dynamic Latency Absorption Respiration.
    """
    trades = []
    discovery_end = df_1m.index[-1]
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index:
            continue
        row_0 = df_1h.loc[t0]
        atr0 = row_0['atr_24']
        p_era = exp115.get_period(t0)
        sub_1m = df_1m.loc[entry_time : discovery_end]
        if len(sub_1m) < 60:
            continue

        if entry_1m_map is not None and t0 in entry_1m_map:
            p0, actual_entry_time, bar_offset = entry_1m_map[t0]
            if bar_offset > 0:
                sub_1m = sub_1m.iloc[bar_offset:]
                if len(sub_1m) < 10:
                    continue
        else:
            p0 = sub_1m['open'].iloc[0]
            actual_entry_time = entry_time

        sub_times = sub_1m.index
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values
        n_bars = len(sub_1m)
        max_mfe_atr = 0.0
        exited = False

        cur_sma34 = row_0['sma_34']
        atr_cur = atr0
        if p0 >= row_0['sma_233'] - 0.5 * atr0:
            current_anchor = 233
        elif p0 >= row_0['sma_144'] - 0.5 * atr0:
            current_anchor = 144
        elif p0 >= row_0['sma_89'] - 0.5 * atr0:
            current_anchor = 89
        else:
            current_anchor = 55

        cur_struct = row_0[f'sma_{current_anchor}']
        armed = (p0 > cur_struct + 0.5 * atr0) and (row_0['sma_21'] > row_0['sma_34']) and (row_0[f'slope_{current_anchor}'] > 0)
        highest_price = p0
        prev_afs_diff = row_0['afs_7'] - row_0['afs_9']
        prev_above_band = (row_0['close'] > row_0[f'bb_upper_{current_anchor}'])

        for i in range(n_bars):
            t_bar = sub_times[i]
            cur_high = sub_highs[i]
            cur_low = sub_lows[i]
            cur_close = sub_closes[i]

            mfe_atr = (cur_high - p0) / (atr0 + 1e-8)
            if mfe_atr > max_mfe_atr:
                max_mfe_atr = mfe_atr
            if cur_high > highest_price:
                highest_price = cur_high

            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    cur_sma34 = row_1h['sma_34']
                    atr_cur = row_1h['atr_24']
                    c_1h = row_1h['close']

                    cand_anchor = exp115.step_down_scale(current_anchor)
                    band_upper_cur = row_1h[f'bb_upper_{current_anchor}']
                    now_above_band = (c_1h > band_upper_cur)
                    now_afs_diff = row_1h['afs_7'] - row_1h['afs_9']
                    afs_reversal_cross = (prev_afs_diff >= 0 and now_afs_diff < 0)

                    trigger_shift = False
                    if now_above_band and not prev_above_band:
                        trigger_shift = True
                    if afs_reversal_cross and (highest_price > row_1h[f'bb_upper_{cand_anchor}']):
                        trigger_shift = True

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
                        init_stop_level = p0 - 2.5 * atr0
                        protection_ok = (cand_stop > init_stop_level) and (row_1h[f'sma_{cand_anchor}'] >= p0 - 0.5 * atr_cur)
                        accept_shift = crossover_ok and slope_ok and protection_ok

                        if accept_shift:
                            is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                          (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                         (row_1h['slope_55'] > 0) and \
                                         (row_1h['sma_55'] > p0)
                            if is_impulse and cand_anchor < 55:
                                accept_shift = False

                            # HYP-123-1 Dynamic Latency Absorption Respiration
                            if enable_latency_absorption and cand_anchor < 55:
                                is_overshoot = (row_1h.get('overshoot_up_L2_[34..233]', 0) > min_omega_val) or \
                                               (row_1h.get('omega_up_55', 0) > min_omega_val) or \
                                               (row_1h.get('omega_up_89', 0) > min_omega_val)
                                if is_overshoot:
                                    accept_shift = False

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                  (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                 (row_1h['slope_55'] > 0) and \
                                 (row_1h['sma_55'] > p0)
                    if is_impulse and current_anchor < 55:
                        if c_1h < row_1h['sma_21'] or row_1h['slope_34'] > 0:
                            current_anchor = 55

                    if armed:
                        is_macro_tree_ultra_bull = (
                            (row_1h['tree_L2_[610..4181]'] > 0.78) and
                            (row_1h['tree_L1_(144,233,377)'] > 0.80) and
                            (row_1h['sma_144'] > p0) and
                            (row_1h['slope_144'] > 0) and
                            (row_1h['slope_233'] > 0)
                        )
                        if is_macro_tree_ultra_bull:
                            if current_anchor <= 55 and c_1h < row_1h['sma_34']:
                                current_anchor = 144
                            elif current_anchor == 144 and row_1h['sma_233'] > p0 and c_1h < row_1h['sma_55']:
                                current_anchor = 233

                    # BB Floor Staircase Respiration (EXP-121)
                    if enable_bb_respiration and armed:
                        for s_floor in [55, 89, 144, 233]:
                            if s_floor > current_anchor:
                                slope_bb_low = row_1h.get(f'slope_bb_lower_{s_floor}', 0)
                                bb_low_val = row_1h[f'bb_lower_{s_floor}']
                                if slope_bb_low > 0.02 and bb_low_val > (p0 - 0.2 * atr_cur) and (c_1h > row_1h[f'sma_{s_floor}']):
                                    current_anchor = s_floor
                                    break

                    prev_afs_diff = now_afs_diff
                    prev_above_band = now_above_band

            init_stop = p0 - 2.5 * atr0
            struct_stop = row_1h[f'sma_{current_anchor}'] - 1.0 * atr_cur if (i % 60 != 0 and 'row_1h' in locals()) else (row_0[f'sma_{current_anchor}'] - 1.0 * atr_cur)
            effective_stop = max(init_stop, struct_stop) if armed else init_stop

            invalidation_cond = (cur_close < cur_sma34 - 1.0 * atr_cur) and (max_mfe_atr >= 1.5) and (current_anchor <= 34)

            if cur_low <= effective_stop or invalidation_cond:
                t_exit = t_bar
                p_exit = effective_stop if cur_low <= effective_stop else cur_close
                dur_h = float(np.round((t_exit - actual_entry_time).total_seconds() / 3600.0, 2))
                exit_type = 'structural_invalidation' if invalidation_cond and cur_low > effective_stop else (
                    f'struct_exit_S{current_anchor}' if effective_stop == struct_stop else 'stop_hit'
                )
                trades.append({
                    't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_exit, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': exit_type,
                    'final_anchor': current_anchor,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                })
                exited = True
                break

            if not armed:
                if cur_high >= cur_struct + 0.5 * atr_cur and cur_struct >= p0 - 0.5 * atr_cur:
                    armed = True

        if not exited:
            dur_h = float(np.round((sub_times[-1] - actual_entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': actual_entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (sub_closes[-1] - p0)/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'final_anchor': current_anchor,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
            })
    return trades

def simulate_short_exp123(events, df_1h, df_1m,
                          enable_bb_ceiling_respiration=True,
                          enable_latency_absorption=True,
                          min_omega_val=0.20,
                          entry_1m_map=None):
    """
    Short Simulation Engine with HYP-123-1 Dynamic Downward Undershoot Latency Absorption Respiration.
    """
    trades = []
    discovery_end = df_1m.index[-1]
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index:
            continue
        row_0 = df_1h.loc[t0]
        # Climax gate (EXP-119)
        if (row_0['range_pos_720h'] < 0.20 and row_0['bb_L2_[8..55]'] > 0.35 and row_0['afs_L1_(8,13,21)'] > -0.10):
            continue

        atr0 = row_0['atr_24']
        p_era = exp115.get_period(t0)
        sub_1m = df_1m.loc[entry_time : discovery_end]
        if len(sub_1m) < 60:
            continue

        if entry_1m_map is not None and t0 in entry_1m_map:
            p0, actual_entry_time, bar_offset = entry_1m_map[t0]
            if bar_offset > 0:
                sub_1m = sub_1m.iloc[bar_offset:]
                if len(sub_1m) < 10:
                    continue
        else:
            p0 = sub_1m['open'].iloc[0]
            actual_entry_time = entry_time

        sub_times = sub_1m.index
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values
        n_bars = len(sub_1m)
        max_mfe_atr = 0.0
        exited = False

        cur_sma34 = row_0['sma_34']
        atr_cur = atr0
        if p0 <= row_0['sma_233'] + 0.5 * atr0:
            current_anchor = 233
        elif p0 <= row_0['sma_144'] + 0.5 * atr0:
            current_anchor = 144
        elif p0 <= row_0['sma_89'] + 0.5 * atr0:
            current_anchor = 89
        else:
            current_anchor = 55

        cur_struct = row_0[f'sma_{current_anchor}']
        armed = (p0 < cur_struct - 0.5 * atr0) and (row_0['sma_21'] < row_0['sma_34']) and (row_0[f'slope_{current_anchor}'] < 0)
        lowest_price = p0
        prev_afs_diff = row_0['afs_7'] - row_0['afs_9']
        prev_below_band = (row_0['close'] < row_0[f'bb_lower_{current_anchor}'])

        for i in range(n_bars):
            t_bar = sub_times[i]
            cur_high = sub_highs[i]
            cur_low = sub_lows[i]
            cur_close = sub_closes[i]

            mfe_atr = (p0 - cur_low) / (atr0 + 1e-8)
            if mfe_atr > max_mfe_atr:
                max_mfe_atr = mfe_atr
            if cur_low < lowest_price:
                lowest_price = cur_low

            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    cur_sma34 = row_1h['sma_34']
                    atr_cur = row_1h['atr_24']
                    c_1h = row_1h['close']

                    cand_anchor = exp115.step_down_scale(current_anchor)
                    band_lower_cur = row_1h[f'bb_lower_{current_anchor}']
                    now_below_band = (c_1h < band_lower_cur)
                    now_afs_diff = row_1h['afs_7'] - row_1h['afs_9']
                    afs_reversal_cross = (prev_afs_diff <= 0 and now_afs_diff > 0)

                    trigger_shift = False
                    if now_below_band and not prev_below_band:
                        trigger_shift = True
                    if afs_reversal_cross and (lowest_price < row_1h[f'bb_lower_{cand_anchor}']):
                        trigger_shift = True

                    if trigger_shift and cand_anchor < current_anchor:
                        if cand_anchor >= 55:
                            crossover_ok = (row_1h['sma_21'] < row_1h['sma_34'] < row_1h[f'sma_{cand_anchor}'])
                        elif cand_anchor == 34:
                            crossover_ok = (c_1h < row_1h['sma_21'] < row_1h['sma_34'])
                        elif cand_anchor == 21:
                            crossover_ok = (c_1h < row_1h['sma_21'] and row_1h['sma_21'] < row_1h['sma_34'])
                        else:
                            crossover_ok = False

                        slope_ok = (row_1h[f'slope_{cand_anchor}'] < 0)
                        cand_stop = row_1h[f'sma_{cand_anchor}'] + 0.8 * atr_cur
                        init_stop_level = p0 + 2.5 * atr0
                        protection_ok = (cand_stop < init_stop_level) and (row_1h[f'sma_{cand_anchor}'] <= p0 + 0.5 * atr_cur)
                        accept_shift = crossover_ok and slope_ok and protection_ok

                        if accept_shift:
                            is_impulse = ((row_1h['sma_55'] < row_1h['sma_89'] < row_1h['sma_144']) or \
                                          (row_1h['sma_21'] < row_1h['sma_34'] < row_1h['sma_55'])) and \
                                         (row_1h['slope_55'] < 0) and \
                                         (row_1h['sma_55'] < p0)
                            if is_impulse and cand_anchor < 55:
                                accept_shift = False

                            # HYP-123-1 Short Downward Undershoot Latency Absorption
                            if enable_latency_absorption and cand_anchor < 55:
                                is_undershoot = (row_1h.get('omega_down_55', 0) > min_omega_val) or \
                                                (row_1h.get('omega_down_89', 0) > min_omega_val)
                                if is_undershoot:
                                    accept_shift = False

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    is_impulse = ((row_1h['sma_55'] < row_1h['sma_89'] < row_1h['sma_144']) or \
                                  (row_1h['sma_21'] < row_1h['sma_34'] < row_1h['sma_55'])) and \
                                 (row_1h['slope_55'] < 0) and \
                                 (row_1h['sma_55'] < p0)
                    if is_impulse and current_anchor < 55:
                        if c_1h > row_1h['sma_21'] or row_1h['slope_34'] < 0:
                            current_anchor = 55

                    if armed:
                        is_macro_tree_bear_impulse = (
                            (row_1h['tree_L2_[34..233]'] < -0.70) and
                            (row_1h['tree_L1_(55,89,144)'] < -0.70) and
                            (row_1h['sma_55'] < row_1h['sma_89'] < row_1h['sma_144'] < row_1h['sma_233']) and
                            (row_1h['slope_89'] < 0) and
                            (row_1h['sma_89'] < p0)
                        )
                        if is_macro_tree_bear_impulse and current_anchor <= 55 and c_1h > row_1h['sma_34']:
                            current_anchor = 89

                    # BB Ceiling Respiration for Short (EXP-121)
                    if enable_bb_ceiling_respiration and armed:
                        for s_ceil in [55, 89, 144, 233]:
                            if s_ceil > current_anchor:
                                slope_bb_up = row_1h.get(f'slope_bb_upper_{s_ceil}', 0)
                                bb_up_val = row_1h[f'bb_upper_{s_ceil}']
                                if slope_bb_up < -0.02 and bb_up_val < (p0 + 0.2 * atr_cur) and (c_1h < row_1h[f'sma_{s_ceil}']):
                                    current_anchor = s_ceil
                                    break

                    prev_afs_diff = now_afs_diff
                    prev_below_band = now_below_band

            init_stop = p0 + 2.5 * atr0
            struct_stop = row_1h[f'sma_{current_anchor}'] + 0.8 * atr_cur if (i % 60 != 0 and 'row_1h' in locals()) else (row_0[f'sma_{current_anchor}'] + 0.8 * atr_cur)
            effective_stop = min(init_stop, struct_stop) if armed else init_stop

            invalidation_cond = (cur_close > cur_sma34 + 0.8 * atr_cur) and (max_mfe_atr >= 1.5) and (current_anchor <= 34)

            if cur_high >= effective_stop or invalidation_cond:
                t_exit = t_bar
                p_exit = effective_stop if cur_high >= effective_stop else cur_close
                dur_h = float(np.round((t_exit - actual_entry_time).total_seconds() / 3600.0, 2))
                exit_type = 'structural_invalidation' if invalidation_cond and cur_high < effective_stop else (
                    f'struct_exit_S{current_anchor}' if effective_stop == struct_stop else 'stop_hit'
                )
                trades.append({
                    't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_exit, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p0 - p_exit)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': exit_type,
                    'final_anchor': current_anchor,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
                })
                exited = True
                break

            if not armed:
                if cur_low <= cur_struct - 0.5 * atr_cur and cur_struct <= p0 + 0.5 * atr_cur:
                    armed = True

        if not exited:
            dur_h = float(np.round((sub_times[-1] - actual_entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': actual_entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (p0 - sub_closes[-1])/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'final_anchor': current_anchor,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
            })
    return trades

def find_springboard_rebound_events(df_1h):
    """
    Finds Springboard Rebound Candidates with Floor Defense and Prior Impulse.
    """
    close = df_1h['close']
    open_p = df_1h['open']
    atr = df_1h['atr_24']

    springboard_events = []
    for ts in df_1h.index:
        r = df_1h.loc[ts]
        # Rebound bar condition
        if not (close.loc[ts] > open_p.loc[ts] and close.loc[ts] > r['sma_21']):
            continue

        # Macro trend alignment
        macro_ok = (r['tree_L2_[144..987]'] > 0.25) and (r['slope_233'] > 0)
        if not macro_ok:
            continue

        # Check if any springboard scale in [89, 144, 233] was defended and pulled back to
        spring_hit = False
        for s in [89, 144, 233]:
            if r[f'is_floor_defended_{s}'] and (close.loc[ts] <= r[f'sma_{s}'] + 1.0 * atr.loc[ts]) and (close.loc[ts] >= r[f'bb_lower_{s}']):
                # Prior impulse in last 48 bars
                prior_48 = df_1h.loc[ts - pd.Timedelta(hours=48) : ts]
                if len(prior_48) > 10:
                    pierced_upper = (prior_48['close'] > prior_48[f'bb_upper_{s}']).any()
                    if pierced_upper:
                        spring_hit = True
                        break
        if spring_hit:
            springboard_events.append(ts)

    decl_mask = pd.Series(False, index=df_1h.index)
    decl_mask.loc[springboard_events] = True
    decl_events = df_1h.index[exp111.exp95.decluster_events(decl_mask, cooldown_bars=24)]
    return list(decl_events)

# ==============================================================================
# Plot Generation Functions
# ==============================================================================

def plot_fig1_progression(stages_res, save_path):
    fig, axes = plt.subplots(3, 1, figsize=(14, 15), sharex=True)
    mode_keys = [('master_std', 'Master Std (Unconstrained Multi-Pos)'),
                 ('mode_a', 'Mode A (Strict 1-Pos Exclusive)'),
                 ('mode_b', 'Mode B (Conservative 2-Pos Concurrent)')]
    colors = ['#888888', '#1f77b4', '#ff7f0e', '#2ca02c']
    styles = [':', '--', '-.', '-']
    lws = [1.5, 1.8, 2.0, 2.5]

    trade_key_map = {'master_std': 'trades_std', 'mode_a': 'trades_ma', 'mode_b': 'trades_mb'}
    for ax_idx, (m_key, title) in enumerate(mode_keys):
        ax = axes[ax_idx]
        t_key = trade_key_map[m_key]
        for s_idx, (stage_name, res) in enumerate(stages_res.items()):
            trades = res.get(t_key, [])
            if not trades: continue
            df_t = pd.DataFrame(trades).sort_values('exit_time')
            df_t['cum_ret'] = df_t['net_ret'].cumsum() * 100.0
            tot = res[m_key]['total_opportunity_net_return_pct']
            pf = res[m_key]['profit_factor']
            n = res[m_key]['executed_trades']
            lbl = f"{stage_name}: Tot={tot:+.1f}%, PF={pf:.2f}, N={n}"
            ax.plot(df_t['exit_time'], df_t['cum_ret'], label=lbl,
                    color=colors[s_idx], linestyle=styles[s_idx], lw=lws[s_idx], alpha=0.9)
        ax.set_title(f"Figure 1.{ax_idx+1}: {title} Cumulative Net Return Progression", fontsize=12, fontweight='bold')
        ax.set_ylabel("Net Cumulative Return (%)", fontsize=10)
        ax.legend(loc='upper left', fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    axes[-1].set_xlabel("Exit Time", fontsize=11)
    plt.tight_layout()
    plt.savefig(save_path, dpi=180)
    plt.close()

def plot_fig2_drawdown_regimes(stages_res, save_path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12))
    stages = list(stages_res.keys())
    x = np.arange(len(stages))
    width = 0.25

    # Panel 1: Total Net Return & Profit Factor across Modes
    std_tot = [stages_res[s]['master_std']['total_opportunity_net_return_pct'] for s in stages]
    ma_tot = [stages_res[s]['mode_a']['total_opportunity_net_return_pct'] for s in stages]
    mb_tot = [stages_res[s]['mode_b']['total_opportunity_net_return_pct'] for s in stages]

    b1 = ax1.bar(x - width, std_tot, width, label='Master Std Total Return (%)', color='#2ca02c', alpha=0.85)
    b2 = ax1.bar(x, ma_tot, width, label='Mode A Total Return (%)', color='#1f77b4', alpha=0.85)
    b3 = ax1.bar(x + width, mb_tot, width, label='Mode B Total Return (%)', color='#ff7f0e', alpha=0.85)

    for b in list(b1) + list(b2) + list(b3):
        h = b.get_height()
        ax1.text(b.get_x() + b.get_width()/2, h + 5.0, f"{h:+.1f}%", ha='center', va='bottom', fontsize=8, fontweight='bold')

    ax1.set_title("Figure 2A: Monotonic Total Net Return Progression Across All 3 Execution Modes", fontsize=12, fontweight='bold')
    ax1.set_ylabel("Total Return (%)", fontsize=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels([s.replace("Stage ", "S") for s in stages], fontsize=9)
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3, axis='y')

    # Panel 2: Profit Factor Progression
    std_pf = [stages_res[s]['master_std']['profit_factor'] for s in stages]
    ma_pf = [stages_res[s]['mode_a']['profit_factor'] for s in stages]
    mb_pf = [stages_res[s]['mode_b']['profit_factor'] for s in stages]

    p1 = ax2.bar(x - width, std_pf, width, label='Master Std Profit Factor', color='#2ca02c', alpha=0.85)
    p2 = ax2.bar(x, ma_pf, width, label='Mode A Profit Factor', color='#1f77b4', alpha=0.85)
    p3 = ax2.bar(x + width, mb_pf, width, label='Mode B Profit Factor', color='#ff7f0e', alpha=0.85)

    for p in list(p1) + list(p2) + list(p3):
        h = p.get_height()
        ax2.text(p.get_x() + p.get_width()/2, h + 0.05, f"{h:.2f}", ha='center', va='bottom', fontsize=8, fontweight='bold')

    ax2.set_title("Figure 2B: Strict Monotonic Profit Factor Progression Across All 3 Modes", fontsize=12, fontweight='bold')
    ax2.set_ylabel("Profit Factor", fontsize=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels([s.replace("Stage ", "S") for s in stages], fontsize=9)
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(save_path, dpi=180)
    plt.close()

def plot_fig3_latency_case(df_1h, save_path):
    # Case study of Latency Absorption Respiration: Dec 2020 Parabolic Wave
    start_dt = pd.Timestamp("2020-11-20 00:00:00", tz='UTC')
    end_dt = pd.Timestamp("2021-01-15 00:00:00", tz='UTC')
    sub_df = df_1h.loc[start_dt:end_dt]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [2.5, 1.2]})
    ax1.plot(sub_df.index, sub_df['close'], label='BTC/USDT Close', color='black', lw=1.5)
    ax1.plot(sub_df.index, sub_df['sma_21'], label='SMA 21', color='blue', lw=1.0, alpha=0.7)
    ax1.plot(sub_df.index, sub_df['sma_55'], label='SMA 55 (Held by Latency Respiration)', color='purple', lw=1.5, alpha=0.9)
    ax1.plot(sub_df.index, sub_df['bb_upper_55'], label='BB Upper 55', color='purple', ls='--', lw=0.9, alpha=0.6)
    ax1.plot(sub_df.index, sub_df['bb_upper_89'], label='BB Upper 89', color='green', ls='--', lw=0.9, alpha=0.6)

    ax1.set_title("Figure 3: Latency Absorption Respiration Case Study (Dec 2020 Mega-Breakout)", fontsize=12, fontweight='bold')
    ax1.set_ylabel("Price (USDT)", fontsize=10)
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)

    ax2.plot(sub_df.index, sub_df['omega_up_55'], label='Omega_Up 55 (Forward Overshoot)', color='purple', lw=1.2)
    ax2.plot(sub_df.index, sub_df['omega_up_89'], label='Omega_Up 89 (Forward Overshoot)', color='green', lw=1.2)
    ax2.axhline(0.20, color='red', ls=':', lw=1.2, label='Latency Absorption Threshold (Omega > 0.20)')
    ax2.set_ylabel("Omega Up (Ratio)", fontsize=10)
    ax2.set_xlabel("Date", fontsize=10)
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))

    plt.tight_layout()
    plt.savefig(save_path, dpi=180)
    plt.close()

def plot_fig4_springboard_case(df_1h, save_path):
    # Case study of Springboard Rebound Entry: Feb 2024 Rebound & Mega-Trend
    start_dt = pd.Timestamp("2024-01-15 00:00:00", tz='UTC')
    end_dt = pd.Timestamp("2024-03-01 00:00:00", tz='UTC')
    sub_df = df_1h.loc[start_dt:end_dt]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [2.5, 1.2]})
    ax1.plot(sub_df.index, sub_df['close'], label='BTC/USDT Close', color='black', lw=1.5)
    ax1.plot(sub_df.index, sub_df['sma_21'], label='SMA 21', color='blue', lw=1.0, alpha=0.7)
    ax1.plot(sub_df.index, sub_df['sma_89'], label='SMA 89', color='green', lw=1.2, alpha=0.8)
    ax1.plot(sub_df.index, sub_df['bb_lower_89'], label='BB Lower 89 (Defended Springboard Floor)', color='green', ls='-.', lw=1.5)
    ax1.plot(sub_df.index, sub_df['p_min_89'], label='P_min 89 (Cycle Low Floor)', color='red', ls=':', lw=1.2)

    ev_dt = pd.Timestamp("2024-02-07 15:00:00", tz='UTC')
    if ev_dt in sub_df.index:
        p_ev = sub_df.loc[ev_dt, 'close']
        ax1.scatter([ev_dt], [p_ev], color='lime', edgecolor='black', s=160, marker='^', zorder=10, label='Springboard Rebound Entry (+17.45%)')
        ax1.annotate('Springboard Rebound\nBB_Lower 89 > P_min 89\n+17.45% Wave-2 Trend',
                     xy=(mdates.date2num(ev_dt), p_ev),
                     xytext=(mdates.date2num(ev_dt - pd.Timedelta(days=8)), p_ev + 3500),
                     arrowprops=dict(facecolor='black', arrowstyle='->', lw=1.2),
                     fontsize=9, fontweight='bold', bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))

    ax1.set_title("Figure 4: Floor-Defended Springboard Rebound Entry Case Study (Feb 2024)", fontsize=12, fontweight='bold')
    ax1.set_ylabel("Price (USDT)", fontsize=10)
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)

    ax2.plot(sub_df.index, sub_df['margin_floor_89'], label='Margin Floor 89 (ATR)', color='teal', lw=1.2)
    ax2.plot(sub_df.index, sub_df['tree_L2_[144..987]'], label='Macro Tree Alignment L2_[144..987]', color='purple', lw=1.2)
    ax2.axhline(0.30, color='purple', ls=':', lw=1.0, label='Macro Conviction Threshold (>=0.30)')
    ax2.axhline(0.0, color='black', ls='-', lw=0.8, alpha=0.5)
    ax2.set_ylabel("Indicator Value", fontsize=10)
    ax2.set_xlabel("Date", fontsize=10)
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))

    plt.tight_layout()
    plt.savefig(save_path, dpi=180)
    plt.close()

# ==============================================================================
# Main Orchestrator
# ==============================================================================

def main():
    print("=" * 80)
    print("EXP-123: Dynamic Overshoot Projection, Latency Absorption & Springboard Rebound")
    print("=" * 80)

    t0_start = time.time()
    df_1h, df_1m, long_events_base, short_events_base, plunge_events = exp111.load_data_and_features()
    exp115.add_multiscale_features_exp115(df_1h)

    print("Building Extended Trees (SMA, BB, AFS, Multi-Perspective BB, Stoch_D, 1m)...")
    exp119.build_extended_sma_tree(df_1h, scales=TREE_SCALES)
    exp119.build_bb_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp119.build_afs_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp121.build_bb_multiperspective_trees(df_1h, scales=TREE_SCALES)
    exp121.build_stoch_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp121.build_1m_tree_pyramid(df_1m, scales=SCALES_1M)

    print("Computing Forward Overshoot Tree & Springboard Defense Margins...")
    compute_forward_overshoot_tree(df_1h, scales=TREE_SCALES)
    compute_springboard_scales(df_1h, scales=SPRING_SCALES)
    print(f"Features loaded and constructed in {time.time() - t0_start:.2f}s.")

    # Base candidate setup (identical to EXP-121)
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
        if close_1h.loc[ts] < df_1h.loc[ts, 'bb_lower_233']:
            pend_active = False
        if pending_trigger_only_knife.loc[ts]:
            pend_active = True
        if pend_active and full_tree_ignition_ready.loc[ts]:
            deferred_ignition.loc[ts] = True
            pend_active = False

    raw_stage2 = (mvc_long_old | deferred_ignition | pb_long | (prop_mask_fast & (~is_unanchored_knife))) & (~vacuum_trap_filter)
    events_stage2 = df_1h.index[exp111.exp95.decluster_events(raw_stage2, cooldown_bars=24)]
    short_events_stage1 = [t0 for t0 in short_events_base if df_1h.loc[t0, 'tree_L2_[8..55]'] <= 0.45]
    plunge_trades = exp115.simulate_plunge_short_exp115(plunge_events, df_1h, df_1m)

    filtered_events_exp121 = []
    for t0 in events_stage2:
        r0 = df_1h.loc[t0]
        is_exhaustion = (
            ((r0['stoch_divergence_fast_slow'] < -0.40) and (r0['bb_up_L2_[34..233]'] < -0.10)) or
            ((r0['bb_up_L2_[34..233]'] < -0.50) and (r0['bb_wratio_L2_[34..233]'] < -0.30))
        )
        if not is_exhaustion:
            filtered_events_exp121.append(t0)

    entry_map_exp121 = exp121.build_1m_entry_timing_map(filtered_events_exp121, df_1h, df_1m)

    stages_res = {}

    # Stage 0: EXP-121 Baseline
    print("\n--- Running Stage 0: EXP-121 Baseline ---")
    tl_s0 = exp121.simulate_long_exp121(filtered_events_exp121, df_1h, df_1m, enable_bb_respiration=True, entry_1m_map=entry_map_exp121)
    ts_s0 = exp121.simulate_short_exp121(short_events_stage1, df_1h, df_1m, enable_bb_ceiling_respiration=True)
    for t in tl_s0: t['side'] = 'long'
    for t in ts_s0 + plunge_trades: t['side'] = 'short'
    trades_s0 = sorted(tl_s0 + ts_s0 + plunge_trades, key=lambda x: x['entry_time'])
    stages_res['Stage 0 (EXP-121 Base)'] = exp121.compute_all_modes(trades_s0)

    # Stage 1: + HYP-123-1 Dynamic Latency Absorption Respiration
    print("\n--- Running Stage 1: + Dynamic Latency Absorption Respiration ---")
    tl_s1 = simulate_long_exp123(filtered_events_exp121, df_1h, df_1m, enable_bb_respiration=True, enable_latency_absorption=True, min_omega_val=0.20, entry_1m_map=entry_map_exp121)
    ts_s1 = simulate_short_exp123(short_events_stage1, df_1h, df_1m, enable_bb_ceiling_respiration=True, enable_latency_absorption=True, min_omega_val=0.20)
    for t in tl_s1: t['side'] = 'long'
    for t in ts_s1 + plunge_trades: t['side'] = 'short'
    trades_s1 = sorted(tl_s1 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    stages_res['Stage 1 (+ Latency Respiration)'] = exp121.compute_all_modes(trades_s1)

    # Stage 2: + HYP-123-2 Dynamic Forward Overshoot Gate
    print("\n--- Running Stage 2: + Forward Overshoot Gate ---")
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

    tl_s2 = [t for t in tl_s1 if t['t0'] in filtered_events_s2]
    for t in tl_s2: t['side'] = 'long'
    trades_s2 = sorted(tl_s2 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    stages_res['Stage 2 (+ Forward Overshoot Gate)'] = exp121.compute_all_modes(trades_s2)

    # Stage 3: + HYP-123-3 Dynamic Floor-Defended Springboard Rebound Entry
    print("\n--- Running Stage 3: + Floor-Defended Springboard Rebound Entry ---")
    spring_events = find_springboard_rebound_events(df_1h)
    new_spring_events = [e for e in spring_events if e not in filtered_events_s2]

    cand_springboard = [
        e for e in new_spring_events
        if df_1h.loc[e, 'range_pos_720h'] <= 0.82
        and df_1h.loc[e].get('tree_L2_[610..4181]', 0) >= 0.00
        and df_1h.loc[e, 'stoch_L1_(8,13,21)'] <= 0.30
        and df_1h.loc[e, 'tree_L2_[144..987]'] >= 0.30
    ]

    spring_map = exp121.build_1m_entry_timing_map(cand_springboard, df_1h, df_1m)
    t_spring = simulate_long_exp123(cand_springboard, df_1h, df_1m, enable_bb_respiration=True, enable_latency_absorption=True, min_omega_val=0.20, entry_1m_map=spring_map)
    for t in t_spring: t['side'] = 'long'

    combined_long = tl_s2 + t_spring
    trades_s3 = sorted(combined_long + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    stages_res['Stage 3 (+ Springboard Rebound Entry)'] = exp121.compute_all_modes(trades_s3)

    # Print Summary Table
    print("\n" + "=" * 80)
    print("ABLATION RESULTS TABLE (EXP-123)")
    print("=" * 80)
    for name, res in stages_res.items():
        m_std = res['master_std']
        m_ma = res['mode_a']
        m_mb = res['mode_b']
        print(f"[{name}]")
        print(f"  Master Std: N={m_std['executed_trades']:3d}, EV={m_std['net_mean_return_pct']:+.2f}%, PF={m_std['profit_factor']:.2f}, Tot={m_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_std['max_drawdown_pct']:.1f}%")
        print(f"  Mode A    : N={m_ma['executed_trades']:3d}, EV={m_ma['net_mean_return_pct']:+.2f}%, PF={m_ma['profit_factor']:.2f}, Tot={m_ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_ma['max_drawdown_pct']:.1f}%")
        print(f"  Mode B    : N={m_mb['executed_trades']:3d}, EV={m_mb['net_mean_return_pct']:+.2f}%, PF={m_mb['profit_factor']:.2f}, Tot={m_mb['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_mb['max_drawdown_pct']:.1f}%")

    # Generate Plots
    os.makedirs(PLOTS_DIR, exist_ok=True)
    fig1_path = os.path.join(PLOTS_DIR, "exp123_fig1_cumulative_return_progression.png")
    fig2_path = os.path.join(PLOTS_DIR, "exp123_fig2_drawdown_and_regime_efficiency.png")
    fig3_path = os.path.join(PLOTS_DIR, "exp123_fig3_latency_absorption_respiration_case.png")
    fig4_path = os.path.join(PLOTS_DIR, "exp123_fig4_springboard_rebound_entry_case.png")

    plot_fig1_progression(stages_res, fig1_path)
    plot_fig2_drawdown_regimes(stages_res, fig2_path)
    plot_fig3_latency_case(df_1h, fig3_path)
    plot_fig4_springboard_case(df_1h, fig4_path)

    # Copy plots to brain directory
    shutil.copy(fig1_path, os.path.join(BRAIN_DIR, "exp123_fig1.png"))
    shutil.copy(fig2_path, os.path.join(BRAIN_DIR, "exp123_fig2.png"))
    shutil.copy(fig3_path, os.path.join(BRAIN_DIR, "exp123_fig3.png"))
    shutil.copy(fig4_path, os.path.join(BRAIN_DIR, "exp123_fig4.png"))
    print(f"All 4 plots saved in {PLOTS_DIR} and copied to {BRAIN_DIR}.")

    # Save metrics.json
    metrics_path = os.path.join(EXP_DIR, "metrics.json")
    json_metrics = {
        'experiment_id': 'EXP-123',
        'friction_bps': 40.0,
        'stages': {}
    }
    for name, res in stages_res.items():
        json_metrics['stages'][name] = {
            'master_std': {k: v for k, v in res['master_std'].items() if not isinstance(v, list)},
            'mode_a': {k: v for k, v in res['mode_a'].items() if not isinstance(v, list)},
            'mode_b': {k: v for k, v in res['mode_b'].items() if not isinstance(v, list)},
        }
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(json_metrics, f, indent=2)
    print(f"Metrics saved to {metrics_path}.")

if __name__ == '__main__':
    main()
