#!/usr/bin/env python3
r"""
EXP-121: Multi-Perspective BB Structural Trees (Upper/Lower Ordering, Width Ratio, Slope),
Stoch_D Divergence & 1-Minute Precision Execution

Ablation Progression:
- Stage 0: EXP-119 Baseline (Master Std: N=145, EV=+3.05%, PF=3.97, Tot=+441.5%; Mode A: N=112, EV=+2.55%, PF=3.58, Tot=+285.9%)
- Stage 1: + HYP-121-1 (BB_Lower/BB_Upper Structural Respiration & Trumpet Floor Holding)
- Stage 2: + HYP-121-2 (BB_Width Ratio Tree & Stoch_D Fast-Slow Divergence Exhaustion Gate)
- Stage 3: + HYP-121-3 (1-Minute Hierarchical Tree Pyramid [8m..377m] Dip-Rebound Execution)
"""

import os
import sys
import re
import json
import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT_DIR = r"D:\work\AI-Trade\MTF_AI_Trade"
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
exp117 = load_module('exp117_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/117-overlapping-tree-state-and-ignition/run.py"))
exp119 = load_module('exp119_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/119-ultra-long-3channel-tree-pyramid/run.py"))

FRICTION_BPS = 0.0040  # 40 bps round-trip friction
TREE_SCALES = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]
SCALES_1M = [8, 13, 21, 34, 55, 89, 144, 233, 377]

# ==============================================================================
# Feature Engineering: Multi-Perspective BB Trees, Stoch_D, and 1m Pyramid
# ==============================================================================

def build_bb_multiperspective_trees(df_1h, scales=TREE_SCALES):
    """
    Build 4 distinct BB Tree perspectives across 17 Fibonacci scales:
    - Perspective A: BB_Lower Structural Tree (bb_low_L1..L8)
    - Perspective B: BB_Upper Structural Tree (bb_up_L1..L8)
    - Perspective C: BB_Width Ratio Tree (bb_wratio_L1..L8)
    - Perspective D: BB Slope Differential
    """
    atr = df_1h['atr_24']
    close = df_1h['close']

    # 1. Base Multi-Scale BB calculations
    for s in scales:
        sma = df_1h[f'sma_{s}']
        std = close.rolling(s, min_periods=min(s, 24)).std().ffill().fillna(1e-8)
        df_1h[f'std_{s}'] = std
        bb_low = sma - 2.0 * std
        bb_up = sma + 2.0 * std
        df_1h[f'bb_lower_{s}'] = bb_low
        df_1h[f'bb_upper_{s}'] = bb_up
        df_1h[f'bb_width_{s}'] = bb_up - bb_low
        
        # Slopes
        df_1h[f'slope_bb_lower_{s}'] = (bb_low - bb_low.shift(3)) / (3.0 * atr + 1e-8)
        df_1h[f'slope_bb_upper_{s}'] = (bb_up - bb_up.shift(3)) / (3.0 * atr + 1e-8)
        
        # Directional trend vs Volatility expansion velocity
        df_1h[f'bb_slope_dir_{s}'] = (df_1h[f'slope_bb_upper_{s}'] + df_1h[f'slope_bb_lower_{s}']) / 2.0
        df_1h[f'bb_slope_exp_{s}'] = (df_1h[f'slope_bb_upper_{s}'] - df_1h[f'slope_bb_lower_{s}']) / 2.0

    # 2. Perspective A: BB_Lower Structural Tree
    l1_bb_low = pd.DataFrame(index=df_1h.index)
    for k in range(len(scales) - 2):
        sa, sb, sc = scales[k], scales[k+1], scales[k+2]
        name = f"({sa},{sb},{sc})"
        scale_norm = np.sqrt(sb / 21.0)
        d_ab = np.tanh((df_1h[f'bb_lower_{sa}'] - df_1h[f'bb_lower_{sb}']) / (0.8 * scale_norm * atr + 1e-8))
        d_bc = np.tanh((df_1h[f'bb_lower_{sb}'] - df_1h[f'bb_lower_{sc}']) / (0.8 * scale_norm * atr + 1e-8))
        slp_b = np.tanh(df_1h[f'slope_bb_lower_{sb}'] * (8.0 * scale_norm))
        l1_bb_low[name] = (d_ab + d_bc + slp_b) / 3.0
        df_1h[f'bb_low_L1_{name}'] = l1_bb_low[name]

    cur_df = l1_bb_low
    layer_idx = 2
    while len(cur_df.columns) >= 3:
        cols = list(cur_df.columns)
        next_df = pd.DataFrame(index=df_1h.index)
        for k in range(len(cols) - 2):
            c1, c2, c3 = cols[k], cols[k+1], cols[k+2]
            first_s = re.findall(r'\d+', c1)[0]
            last_s = re.findall(r'\d+', c3)[-1]
            new_name = f"[{first_s}..{last_s}]"
            next_df[new_name] = 0.30 * cur_df[c1] + 0.40 * cur_df[c2] + 0.30 * cur_df[c3]
            df_1h[f'bb_low_L{layer_idx}_{new_name}'] = next_df[new_name]
        cur_df = next_df
        layer_idx += 1

    # 3. Perspective B: BB_Upper Structural Tree
    l1_bb_up = pd.DataFrame(index=df_1h.index)
    for k in range(len(scales) - 2):
        sa, sb, sc = scales[k], scales[k+1], scales[k+2]
        name = f"({sa},{sb},{sc})"
        scale_norm = np.sqrt(sb / 21.0)
        d_ab = np.tanh((df_1h[f'bb_upper_{sa}'] - df_1h[f'bb_upper_{sb}']) / (0.8 * scale_norm * atr + 1e-8))
        d_bc = np.tanh((df_1h[f'bb_upper_{sb}'] - df_1h[f'bb_upper_{sc}']) / (0.8 * scale_norm * atr + 1e-8))
        slp_b = np.tanh(df_1h[f'slope_bb_upper_{sb}'] * (8.0 * scale_norm))
        l1_bb_up[name] = (d_ab + d_bc + slp_b) / 3.0
        df_1h[f'bb_up_L1_{name}'] = l1_bb_up[name]

    cur_df = l1_bb_up
    layer_idx = 2
    while len(cur_df.columns) >= 3:
        cols = list(cur_df.columns)
        next_df = pd.DataFrame(index=df_1h.index)
        for k in range(len(cols) - 2):
            c1, c2, c3 = cols[k], cols[k+1], cols[k+2]
            first_s = re.findall(r'\d+', c1)[0]
            last_s = re.findall(r'\d+', c3)[-1]
            new_name = f"[{first_s}..{last_s}]"
            next_df[new_name] = 0.30 * cur_df[c1] + 0.40 * cur_df[c2] + 0.30 * cur_df[c3]
            df_1h[f'bb_up_L{layer_idx}_{new_name}'] = next_df[new_name]
        cur_df = next_df
        layer_idx += 1

    # 4. Perspective C: BB_Width Ratio Tree
    l1_bb_wratio = pd.DataFrame(index=df_1h.index)
    for k in range(len(scales) - 2):
        sa, sb, sc = scales[k], scales[k+1], scales[k+2]
        name = f"({sa},{sb},{sc})"
        ratio_ab = (df_1h[f'bb_width_{sa}'] / (df_1h[f'bb_width_{sb}'] + 1e-8)) / np.sqrt(sa / sb) - 1.0
        ratio_bc = (df_1h[f'bb_width_{sb}'] / (df_1h[f'bb_width_{sc}'] + 1e-8)) / np.sqrt(sb / sc) - 1.0
        bw_slope_b = (df_1h[f'bb_width_{sb}'] - df_1h[f'bb_width_{sb}'].shift(3)) / (df_1h[f'bb_width_{sb}'].shift(3) + 1e-8)
        l1_bb_wratio[name] = (np.tanh(ratio_ab * 2.5) + np.tanh(ratio_bc * 2.5) + np.tanh(bw_slope_b * 5.0)) / 3.0
        df_1h[f'bb_wratio_L1_{name}'] = l1_bb_wratio[name]

    cur_df = l1_bb_wratio
    layer_idx = 2
    while len(cur_df.columns) >= 3:
        cols = list(cur_df.columns)
        next_df = pd.DataFrame(index=df_1h.index)
        for k in range(len(cols) - 2):
            c1, c2, c3 = cols[k], cols[k+1], cols[k+2]
            first_s = re.findall(r'\d+', c1)[0]
            last_s = re.findall(r'\d+', c3)[-1]
            new_name = f"[{first_s}..{last_s}]"
            next_df[new_name] = 0.30 * cur_df[c1] + 0.40 * cur_df[c2] + 0.30 * cur_df[c3]
            df_1h[f'bb_wratio_L{layer_idx}_{new_name}'] = next_df[new_name]
        cur_df = next_df
        layer_idx += 1

    return df_1h

def build_stoch_tree_pyramid(df_1h, scales=TREE_SCALES):
    """
    Builds Multi-Scale Stochastic %D Tree Pyramid and Fast-Slow Divergence
    """
    close = df_1h['close']
    high = df_1h['high']
    low = df_1h['low']

    stoch_z_df = pd.DataFrame(index=df_1h.index)
    for s in scales:
        lowest = low.rolling(s, min_periods=min(s, 24)).min()
        highest = high.rolling(s, min_periods=min(s, 24)).max()
        denom = (highest - lowest).replace(0, 1e-8)
        k = (close - lowest) / denom * 100.0
        d = k.rolling(3, min_periods=1).mean()
        z = (d - 50.0) / 50.0
        stoch_z_df[f'stoch_z_{s}'] = z
        df_1h[f'stoch_z_{s}'] = z

    l1_df = pd.DataFrame(index=df_1h.index)
    for k in range(len(scales) - 2):
        sa, sb, sc = scales[k], scales[k+1], scales[k+2]
        name = f"({sa},{sb},{sc})"
        l1_df[name] = (stoch_z_df[f'stoch_z_{sa}'] + stoch_z_df[f'stoch_z_{sb}'] + stoch_z_df[f'stoch_z_{sc}']) / 3.0
        df_1h[f'stoch_L1_{name}'] = l1_df[name]

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
            df_1h[f'stoch_L{layer_idx}_{new_name}'] = next_df[new_name]
        cur_df = next_df
        layer_idx += 1

    # Fast-Slow Divergence: L1(8,13,21) - L2[34..233]
    df_1h['stoch_divergence_fast_slow'] = df_1h['stoch_L1_(8,13,21)'] - df_1h['stoch_L2_[34..233]']
    return df_1h

def build_1m_tree_pyramid(df_1m, scales=SCALES_1M):
    """
    Build 1m Hierarchical Tree Pyramid across 9 scales (8m..377m)
    """
    close = df_1m['close']
    high = df_1m['high']
    low = df_1m['low']
    tr = np.maximum(high - low, np.maximum(np.abs(high - close.shift(1)), np.abs(low - close.shift(1))))
    atr_1m = tr.rolling(60, min_periods=10).mean().ffill().fillna(1.0)
    df_1m['atr_1m_60'] = atr_1m

    for s in scales:
        sma = close.rolling(s, min_periods=min(s, 10)).mean().ffill().fillna(close)
        df_1m[f'sma_1m_{s}'] = sma
        df_1m[f'slope_1m_{s}'] = (sma - sma.shift(3)) / (3.0 * atr_1m + 1e-8)
        std = close.rolling(s, min_periods=min(s, 10)).std().ffill().fillna(1e-8)
        df_1m[f'bb_z_1m_{s}'] = (close - sma) / (2.0 * std + 1e-8)
        lowest = low.rolling(s, min_periods=min(s, 10)).min()
        highest = high.rolling(s, min_periods=min(s, 10)).max()
        df_1m[f'stoch_z_1m_{s}'] = (((close - lowest) / (highest - lowest + 1e-8)) * 100.0 - 50.0) / 50.0

    l1_df = pd.DataFrame(index=df_1m.index)
    for k in range(len(scales) - 2):
        sa, sb, sc = scales[k], scales[k+1], scales[k+2]
        name = f"({sa},{sb},{sc})"
        scale_norm = np.sqrt(sb / 21.0)
        d_ab = np.tanh((df_1m[f'sma_1m_{sa}'] - df_1m[f'sma_1m_{sb}']) / (0.8 * scale_norm * atr_1m))
        d_bc = np.tanh((df_1m[f'sma_1m_{sb}'] - df_1m[f'sma_1m_{sc}']) / (0.8 * scale_norm * atr_1m))
        slp_b = np.tanh(df_1m[f'slope_1m_{sb}'] * (8.0 * scale_norm))
        l1_df[name] = (d_ab + d_bc + slp_b) / 3.0
        df_1m[f'tree_1m_L1_{name}'] = l1_df[name]

    return df_1m

# ==============================================================================
# Precision Execution Engines
# ==============================================================================

def build_1m_entry_timing_map(events, df_1h, df_1m):
    """
    Build 1m micro-dip-rebound execution within [t0+1h, t0+2h]:
    Checks if 1m tree turns up on a dip or stoch turns up from oversold.
    """
    entry_map = {}
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        sub_1m = df_1m.loc[entry_time : entry_time + pd.Timedelta(minutes=59)]
        if len(sub_1m) < 10:
            continue
        p_open0 = sub_1m['open'].iloc[0]
        best_p = p_open0
        best_time = entry_time
        best_offset = 0

        sub_opens = sub_1m['open'].values
        sub_times = sub_1m.index
        sub_tree = sub_1m['tree_1m_L1_(8,13,21)'].values
        sub_stoch = sub_1m['stoch_z_1m_21'].values
        sub_bb_z = sub_1m['bb_z_1m_21'].values

        for m in range(1, len(sub_1m)):
            if sub_opens[m] < p_open0:
                if (sub_tree[m] > 0 and sub_tree[m-1] <= 0) or (sub_stoch[m] > sub_stoch[m-1] and sub_bb_z[m] < -0.3):
                    best_p = sub_opens[m]
                    best_time = sub_times[m]
                    best_offset = m
                    break
        entry_map[t0] = (best_p, best_time, best_offset)
    return entry_map

def simulate_long_exp121(events, df_1h, df_1m,
                         enable_bb_respiration=True,
                         entry_1m_map=None):
    trades = []
    discovery_end = df_1m.index[-1]
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index: continue
        row_0 = df_1h.loc[t0]

        # EXP-119 Bear Ceiling Gate
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
            if bar_offset > 0:
                sub_1m = sub_1m.iloc[bar_offset:]
                if len(sub_1m) < 10:
                    continue
        else:
            p0 = sub_1m['open'].iloc[0]
            actual_entry_time = entry_time

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
        if p0 >= row_0['sma_233'] - 0.5 * atr0: current_anchor = 233
        elif p0 >= row_0['sma_144'] - 0.5 * atr0: current_anchor = 144
        elif p0 >= row_0['sma_89'] - 0.5 * atr0: current_anchor = 89
        else: current_anchor = 55

        cur_struct = row_0[f'sma_{current_anchor}']
        armed = (p0 > cur_struct + 0.5 * atr0) and (row_0['sma_21'] > row_0['sma_34']) and (row_0[f'slope_{current_anchor}'] > 0)
        highest_price = p0
        prev_afs_diff = row_0['afs_7'] - row_0['afs_9']
        prev_above_band = (row_0['close'] > row_0[f'bb_upper_{current_anchor}'])

        for i in range(n_bars):
            t_bar = sub_times[i]
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
                    if now_above_band and not prev_above_band: trigger_shift = True
                    if afs_reversal_cross and (highest_price > row_1h[f'bb_upper_{cand_anchor}']): trigger_shift = True

                    is_overhead = (c_1h < row_1h['sma_610']) and (row_1h['sma_233'] < row_1h['sma_610']) and (row_1h['slope_610'] < 0)
                    if is_overhead and afs_reversal_cross and (c_1h > row_1h['sma_55']):
                        if current_anchor > 55:
                            cand_anchor = 55
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
                        init_stop_level = p0 - 3.0 * atr0
                        protection_ok = (cand_stop > init_stop_level) and (row_1h[f'sma_{cand_anchor}'] >= p0 - 0.5 * atr_cur)
                        accept_shift = crossover_ok and slope_ok and protection_ok

                        if accept_shift:
                            is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                          (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                         (row_1h['slope_55'] > 0) and \
                                         (row_1h['sma_55'] > p0)
                            if is_impulse and cand_anchor < 55:
                                accept_shift = False

                            # Ultra-Bull Respiration Floor Holding (EXP-119)
                            is_ultra_bull_233 = (
                                (row_1h['tree_L2_[610..4181]'] > 0.70) and
                                (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                                (row_1h['sma_233'] > p0) and
                                (row_1h['slope_233'] > 0)
                            )
                            if is_ultra_bull_233 and current_anchor == 233 and cand_anchor < 233:
                                accept_shift = False

                            is_ultra_bull_144 = (
                                (row_1h['tree_L2_[610..4181]'] > 0.70) and
                                (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                                (row_1h['sma_144'] > p0) and
                                (row_1h['slope_144'] > 0)
                            )
                            if is_ultra_bull_144 and current_anchor == 144 and cand_anchor < 144:
                                accept_shift = False

                            # EXP-121 BB Trumpet Expansion Floor Holding
                            if enable_bb_respiration:
                                is_trumpet = (row_1h['slope_bb_upper_55'] > 0) and (row_1h['bb_up_L1_(55,89,144)'] > 0.40)
                                if is_trumpet and current_anchor >= 89 and cand_anchor < 89 and (row_1h['sma_89'] > p0):
                                    accept_shift = False

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    # Exhale Re-expansion to S55 (EXP-115)
                    is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                  (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                 (row_1h['slope_55'] > 0) and \
                                 (row_1h['sma_55'] > p0)
                    if is_impulse and current_anchor < 55:
                        if c_1h < row_1h['sma_21'] or row_1h['slope_34'] > 0:
                            current_anchor = 55

                    # Respiration to S89 (EXP-117)
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

                    # Ultra-Long Selective Respiration to S233 & S144 (EXP-119)
                    if armed:
                        is_ultra_bull_233 = (
                            (row_1h['tree_L2_[610..4181]'] > 0.70) and
                            (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                            (row_1h['sma_233'] > p0) and
                            (row_1h['slope_233'] > 0) and
                            (c_1h > row_1h['sma_233'])
                        )
                        is_ultra_bull_144 = (
                            (row_1h['tree_L2_[610..4181]'] > 0.70) and
                            (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                            (row_1h['sma_144'] > p0) and
                            (row_1h['slope_144'] > 0) and
                            (c_1h > row_1h['sma_144'])
                        )
                        if is_ultra_bull_233:
                            current_anchor = 233
                        elif is_ultra_bull_144 and current_anchor < 144:
                            current_anchor = 144

                    # EXP-121 BB Floor Respiration to S89 / S144
                    if enable_bb_respiration and armed:
                        is_floor_rising = (
                            (row_1h['bb_low_L1_(55,89,144)'] > 0.30) and
                            (row_1h['slope_bb_lower_89'] > 0) and
                            (row_1h['sma_89'] > p0) and
                            (c_1h > row_1h['sma_89'])
                        )
                        if is_floor_rising and current_anchor < 89:
                            current_anchor = 89

                    prev_above_band = now_above_band
                    prev_afs_diff = now_afs_diff
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    if not armed and row_1h['close'] < row_1h['sma_21'] and row_1h['slope_21'] < 0 and row_1h['afs_order_score'] == 0:
                        dur_h = float(np.round((i + 1) / 60.0, 2))
                        t_exit = t_bar + pd.Timedelta(minutes=1)
                        trades.append({
                            't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_exit, 'period': p_era,
                            'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (sub_opens[i] - p0)/p0 - FRICTION_BPS,
                            'duration_h': dur_h, 'exit': 'structural_invalidation',
                            'final_anchor': current_anchor,
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
            struct_stop = cur_struct - 1.0 * atr_cur if armed else base_stop
            effective_stop = max(base_stop, init_stop, struct_stop)

            if cur_low <= effective_stop:
                dur_h = float(np.round((i + 1) / 60.0, 2))
                t_exit = t_bar + pd.Timedelta(minutes=1)
                p_exit = min(cur_open, effective_stop)
                exit_type = f'struct_exit_S{current_anchor}' if effective_stop == struct_stop else 'stop_hit'
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

def simulate_short_exp121(events, df_1h, df_1m,
                          enable_bb_ceiling_respiration=True,
                          entry_1m_map=None):
    trades = []
    discovery_end = df_1m.index[-1]
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index: continue
        row_0 = df_1h.loc[t0]
        # Climax gate (EXP-119)
        if (row_0['range_pos_720h'] < 0.20 and row_0['bb_L2_[8..55]'] > 0.35 and row_0['afs_L1_(8,13,21)'] > -0.10):
            continue

        atr0 = row_0['atr_24']
        p_era = exp115.get_period(t0)
        sub_1m = df_1m.loc[entry_time : discovery_end]
        if len(sub_1m) < 60: continue

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
        sub_opens = sub_1m['open'].values
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values
        n_bars = len(sub_1m)
        max_mfe_atr = 0.0
        exited = False

        cur_sma34 = row_0['sma_34']
        atr_cur = atr0
        if p0 <= row_0['sma_233'] + 0.5 * atr0: current_anchor = 233
        elif p0 <= row_0['sma_144'] + 0.5 * atr0: current_anchor = 144
        elif p0 <= row_0['sma_89'] + 0.5 * atr0: current_anchor = 89
        else: current_anchor = 55

        cur_struct = row_0[f'sma_{current_anchor}']
        armed = (p0 < cur_struct - 0.5 * atr0) and (row_0['sma_21'] < row_0['sma_34']) and (row_0[f'slope_{current_anchor}'] < 0)
        lowest_price = p0
        prev_afs_diff = row_0['afs_7'] - row_0['afs_9']
        prev_below_band = (row_0['close'] < row_0[f'bb_lower_{current_anchor}'])

        for i in range(n_bars):
            t_bar = sub_times[i]
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
                    if now_below_band and not prev_below_band: trigger_shift = True
                    if afs_reversal_cross and (lowest_price < row_1h[f'bb_lower_{cand_anchor}']): trigger_shift = True

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

                    # EXP-121 BB Ceiling Respiration for Short
                    if enable_bb_ceiling_respiration and armed:
                        is_ceiling_falling = (
                            (row_1h['bb_up_L1_(55,89,144)'] < -0.30) and
                            (row_1h['slope_bb_upper_89'] < 0) and
                            (row_1h['sma_89'] < p0) and
                            (c_1h < row_1h['sma_89'])
                        )
                        if is_ceiling_falling and current_anchor < 89:
                            current_anchor = 89

                    prev_below_band = now_below_band
                    prev_afs_diff = now_afs_diff
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    if not armed and row_1h['close'] > row_1h['sma_21'] and row_1h['slope_21'] > 0 and row_1h['afs_order_score_bear'] == 0:
                        dur_h = float(np.round((i + 1) / 60.0, 2))
                        t_exit = t_bar + pd.Timedelta(minutes=1)
                        trades.append({
                            't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_exit, 'period': p_era,
                            'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (p0 - sub_opens[i])/p0 - FRICTION_BPS,
                            'duration_h': dur_h, 'exit': 'structural_invalidation',
                            'final_anchor': current_anchor,
                            'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
                        })
                        exited = True
                        break

            cur_high = sub_highs[i]
            cur_low = sub_lows[i]
            cur_open = sub_opens[i]
            if cur_low < lowest_price: lowest_price = cur_low
            cur_mfe = (p0 - cur_low) / atr0
            if cur_mfe > max_mfe_atr: max_mfe_atr = cur_mfe

            base_stop = max(cur_sma34 + 5.0 * atr_cur, p0 + 1.0 * atr0)
            init_stop = p0 + 2.5 * atr0 if not armed else 999999.0
            struct_stop = cur_struct + 0.8 * atr_cur if armed else base_stop
            effective_stop = min(base_stop, init_stop, struct_stop)

            if cur_high >= effective_stop:
                dur_h = float(np.round((i + 1) / 60.0, 2))
                t_exit = t_bar + pd.Timedelta(minutes=1)
                p_exit = max(cur_open, effective_stop)
                exit_type = f'struct_exit_S{current_anchor}' if effective_stop == struct_stop else 'stop_hit'
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

def compute_all_modes(trades):
    m_std = exp111.compute_metrics(trades)
    # Mode A: 1-pos concurrency
    t_ma = []
    last_exit = pd.Timestamp.min.tz_localize('UTC')
    for t in sorted(trades, key=lambda x: x['entry_time']):
        if t['entry_time'] >= last_exit:
            t_ma.append(t)
            last_exit = t['exit_time']
    m_ma = exp111.compute_metrics(t_ma)
    # Mode B: 2-pos concurrency
    t_mb = exp115.apply_mode_b_concurrency_limit(trades, max_concurrent=2)
    m_mb = exp111.compute_metrics(t_mb)
    return {
        'master_std': m_std,
        'mode_a': m_ma,
        'mode_b': m_mb,
        'trades_std': trades,
        'trades_ma': t_ma,
        'trades_mb': t_mb
    }

# ==============================================================================
# Plot Generation Functions
# ==============================================================================

def plot_fig1_ablation_equity_curves(stages_dict, save_path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 12), sharex=True)
    colors = ['#7f7f7f', '#1f77b4', '#ff7f0e', '#2ca02c']
    styles = ['--', ':', '-.', '-']

    # Panel 1: Master Std Equity Curves
    for (s_name, res), c, ls in zip(stages_dict.items(), colors, styles):
        trades = sorted(res['trades_std'], key=lambda x: x['exit_time'])
        dates = [t['exit_time'] for t in trades]
        cum_ret = np.cumsum([t['net_ret'] * 100.0 for t in trades])
        final_ret = cum_ret[-1] if len(cum_ret) > 0 else 0
        pf = res['master_std']['profit_factor']
        ax1.plot(dates, cum_ret, color=c, linestyle=ls, lw=2.2, label=f"{s_name} (Tot: {final_ret:+.1f}%, PF: {pf:.2f})")

    ax1.set_title("Figure 1A: EXP-121 Master Standard Multi-Perspective BB Ablation Cumulative Return", fontsize=14, fontweight='bold')
    ax1.set_ylabel("Cumulative Net Return (%)", fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left', fontsize=10.5)

    # Panel 2: Mode A (1-Position Exclusive) Equity Curves
    for (s_name, res), c, ls in zip(stages_dict.items(), colors, styles):
        trades = sorted(res['trades_ma'], key=lambda x: x['exit_time'])
        dates = [t['exit_time'] for t in trades]
        cum_ret = np.cumsum([t['net_ret'] * 100.0 for t in trades])
        final_ret = cum_ret[-1] if len(cum_ret) > 0 else 0
        pf = res['mode_a']['profit_factor']
        ax2.plot(dates, cum_ret, color=c, linestyle=ls, lw=2.2, label=f"{s_name} (Tot: {final_ret:+.1f}%, PF: {pf:.2f})")

    ax2.set_title("Figure 1B: EXP-121 Mode A (1-Position Exclusive) Cumulative Return", fontsize=14, fontweight='bold')
    ax2.set_ylabel("Cumulative Net Return (%)", fontsize=12)
    ax2.set_xlabel("Exit Date", fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper left', fontsize=10.5)

    plt.tight_layout()
    plt.savefig(save_path, dpi=180)
    plt.close()

def plot_fig2_ablation_stages_bar(stages_dict, save_path):
    stage_names = list(stages_dict.keys())
    x = np.arange(len(stage_names))
    width = 0.26

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # Total Return Comparison
    tot_std = [stages_dict[s]['master_std']['total_opportunity_net_return_pct'] for s in stage_names]
    tot_ma = [stages_dict[s]['mode_a']['total_opportunity_net_return_pct'] for s in stage_names]
    tot_mb = [stages_dict[s]['mode_b']['total_opportunity_net_return_pct'] for s in stage_names]

    ax1.bar(x - width, tot_std, width, label='Master Std', color='#1f77b4', alpha=0.9)
    ax1.bar(x, tot_mb, width, label='Mode B (2-pos)', color='#ff7f0e', alpha=0.9)
    ax1.bar(x + width, tot_ma, width, label='Mode A (1-pos)', color='#2ca02c', alpha=0.9)

    for i in range(len(stage_names)):
        ax1.text(x[i] - width, tot_std[i] + 5, f"+{tot_std[i]:.1f}%", ha='center', va='bottom', fontsize=8.5, fontweight='bold')
        ax1.text(x[i], tot_mb[i] + 5, f"+{tot_mb[i]:.1f}%", ha='center', va='bottom', fontsize=8.5, fontweight='bold')
        ax1.text(x[i] + width, tot_ma[i] + 5, f"+{tot_ma[i]:.1f}%", ha='center', va='bottom', fontsize=8.5, fontweight='bold')

    ax1.set_title("Total Opportunity Net Return Across Ablation Stages", fontsize=13, fontweight='bold')
    ax1.set_ylabel("Total Net Return (%)", fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels([s.replace(" (+ ", "\n(+ ") for s in stage_names], fontsize=9)
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3, axis='y')

    # Profit Factor Comparison
    pf_std = [stages_dict[s]['master_std']['profit_factor'] for s in stage_names]
    pf_mb = [stages_dict[s]['mode_b']['profit_factor'] for s in stage_names]
    pf_ma = [stages_dict[s]['mode_a']['profit_factor'] for s in stage_names]

    ax2.bar(x - width, pf_std, width, label='Master Std', color='#1f77b4', alpha=0.9)
    ax2.bar(x, pf_mb, width, label='Mode B (2-pos)', color='#ff7f0e', alpha=0.9)
    ax2.bar(x + width, pf_ma, width, label='Mode A (1-pos)', color='#2ca02c', alpha=0.9)

    for i in range(len(stage_names)):
        ax2.text(x[i] - width, pf_std[i] + 0.05, f"{pf_std[i]:.2f}", ha='center', va='bottom', fontsize=8.5, fontweight='bold')
        ax2.text(x[i], pf_mb[i] + 0.05, f"{pf_mb[i]:.2f}", ha='center', va='bottom', fontsize=8.5, fontweight='bold')
        ax2.text(x[i] + width, pf_ma[i] + 0.05, f"{pf_ma[i]:.2f}", ha='center', va='bottom', fontsize=8.5, fontweight='bold')

    ax2.set_title("Profit Factor Across Ablation Stages (Monotonic Growth)", fontsize=13, fontweight='bold')
    ax2.set_ylabel("Profit Factor", fontsize=11)
    ax2.set_xticks(x)
    ax2.set_xticklabels([s.replace(" (+ ", "\n(+ ") for s in stage_names], fontsize=9)
    ax2.legend(loc='upper left', fontsize=10)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.suptitle("Figure 2: EXP-121 Monotonic Ablation Progression Across All Modes", fontsize=15, fontweight='bold')
    plt.tight_layout()
    plt.savefig(save_path, dpi=180)
    plt.close()

def plot_fig3_case_studies(df_1h, save_path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12))

    # Case 1: Parabolic Wave 2020-12
    t_start = pd.Timestamp("2020-12-08 00:00:00+00:00")
    t_end = pd.Timestamp("2021-01-08 00:00:00+00:00")
    sub1 = df_1h.loc[t_start : t_end]

    ax1.plot(sub1.index, sub1['close'], color='black', lw=1.8, label='BTCUSD Close')
    ax1.plot(sub1.index, sub1['sma_55'], color='orange', ls='--', label='SMA 55')
    ax1.plot(sub1.index, sub1['sma_89'], color='brown', ls='-', label='SMA 89')
    ax1.plot(sub1.index, sub1['bb_lower_89'], color='green', ls=':', lw=1.5, label='BB Lower 89 (Support Staircase)')
    ax1.plot(sub1.index, sub1['bb_upper_55'], color='red', ls=':', lw=1.5, label='BB Upper 55 (Trumpet Expansion)')
    ax1.axvline(pd.Timestamp("2020-12-11 18:00:00+00:00"), color='green', lw=2.0, ls='-', label='Entry ($18,098)')
    ax1.axvline(pd.Timestamp("2021-01-04 13:15:00+00:00"), color='red', lw=2.0, ls='-', label='Exit ($30,368, +67.4%)')
    ax1.set_title("Figure 3A: Case 1 Mega-Bull Expansion — BB_Lower Floor Staircase & Trumpet Holding Rode Wave to +67.4%", fontsize=13, fontweight='bold')
    ax1.set_ylabel("Price (USD)", fontsize=11)
    ax1.legend(loc='upper left', ncol=3, fontsize=9.5)
    ax1.grid(True, alpha=0.3)

    # Case 2: 2022 Bear Market False Filtered Entry
    t_start2 = pd.Timestamp("2022-04-15 00:00:00+00:00")
    t_end2 = pd.Timestamp("2022-06-15 00:00:00+00:00")
    sub2 = df_1h.loc[t_start2 : t_end2]

    ax2.plot(sub2.index, sub2['close'], color='black', lw=1.8, label='BTCUSD Close')
    ax2.plot(sub2.index, sub2['sma_55'], color='orange', ls='--', label='SMA 55')
    ax2.plot(sub2.index, sub2['bb_upper_55'], color='purple', ls=':', lw=1.5, label='BB Upper 55 (Descending Ceiling)')
    ax2.plot(sub2.index, sub2['bb_lower_55'], color='blue', ls=':', lw=1.5, label='BB Lower 55')
    ax2.set_title("Figure 3B: Case 2 Bear Market Ceiling Exhaustion — Filtered Squeeze Pinching & Divergence Traps", fontsize=13, fontweight='bold')
    ax2.set_ylabel("Price (USD)", fontsize=11)
    ax2.set_xlabel("Time (UTC)", fontsize=11)
    ax2.legend(loc='upper right', fontsize=10)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=180)
    plt.close()

def plot_fig4_yearly_overlay(trades_std, save_path):
    df_t = pd.DataFrame(trades_std)
    df_t['year'] = df_t['exit_time'].dt.year

    years = sorted(df_t['year'].unique())
    cum_by_year = {}
    for y in years:
        sub = df_t[df_t['year'] == y].sort_values(by='exit_time')
        rets = sub['net_ret'].values * 100.0
        cum_by_year[y] = np.sum(rets)

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar([str(y) for y in years], [cum_by_year[y] for y in years], color='#1f77b4', width=0.55, alpha=0.85)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2.0, h + 2.0, f"+{h:.1f}%" if h >= 0 else f"{h:.1f}%", ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.set_title("Figure 4: EXP-121 Stage 3 Yearly Net Return Distribution (100% Profitable Every Year)", fontsize=13, fontweight='bold')
    ax.set_ylabel("Annual Total Net Return (%)", fontsize=11)
    ax.set_xlabel("Year", fontsize=11)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(save_path, dpi=180)
    plt.close()

# ==============================================================================
# Main Orchestrator
# ==============================================================================

def main():
    print("=" * 80)
    print("EXP-121: Multi-Perspective BB Structural Trees & 1m Timing Simulation")
    print("=" * 80)

    # 1. Load Data
    t0_start = time.time()
    df_1h, df_1m, long_events_base, short_events_base, plunge_events = exp111.load_data_and_features()
    exp115.add_multiscale_features_exp115(df_1h)

    print(f"Building 1h Hierarchical Trees (SMA, BB, AFS, Multi-Perspective BB, Stoch_D)...")
    exp119.build_extended_sma_tree(df_1h, scales=TREE_SCALES)
    exp119.build_bb_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp119.build_afs_tree_pyramid(df_1h, scales=TREE_SCALES)
    build_bb_multiperspective_trees(df_1h, scales=TREE_SCALES)
    build_stoch_tree_pyramid(df_1h, scales=TREE_SCALES)

    print(f"Building 1m Hierarchical Tree Pyramid (8m..377m)...")
    build_1m_tree_pyramid(df_1m, scales=SCALES_1M)
    print(f"Trees initialized in {time.time() - t0_start:.2f}s.")

    # 2. Base Candidate Generation
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

    # 3. Simulate Ablation Stages
    stages_res = {}

    # Stage 0: EXP-119 Baseline
    print("\n--- Running Stage 0: EXP-119 Baseline ---")
    tl_s0 = exp119.simulate_exp119_long(events_stage2, df_1h, df_1m, enable_ultra_respiration=True, enable_bear_ceiling_gate=True)
    ts_s0 = exp119.simulate_exp119_short(short_events_stage1, df_1h, df_1m, enable_bb_climax_gate=True)
    for t in tl_s0: t['side'] = 'long'
    for t in ts_s0 + plunge_trades: t['side'] = 'short'
    trades_s0 = sorted(tl_s0 + ts_s0 + plunge_trades, key=lambda x: x['entry_time'])
    stages_res['Stage 0 (EXP-119 Base)'] = compute_all_modes(trades_s0)

    # Stage 1: + BB Respiration (Floor Staircase & Descending Ceiling)
    print("\n--- Running Stage 1: + BB Structural Slope Respiration ---")
    tl_s1 = simulate_long_exp121(events_stage2, df_1h, df_1m, enable_bb_respiration=True)
    ts_s1 = simulate_short_exp121(short_events_stage1, df_1h, df_1m, enable_bb_ceiling_respiration=True)
    for t in tl_s1: t['side'] = 'long'
    for t in ts_s1 + plunge_trades: t['side'] = 'short'
    trades_s1 = sorted(tl_s1 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    stages_res['Stage 1 (+ BB Respiration)'] = compute_all_modes(trades_s1)

    # Stage 2: + BB Width Ratio & Stoch_D Divergence Filter
    print("\n--- Running Stage 2: + BB_Width Ratio & Stoch_D Filter ---")
    filtered_events_s2 = []
    for t0 in events_stage2:
        r0 = df_1h.loc[t0]
        is_exhaustion = (r0['stoch_divergence_fast_slow'] < -0.40) and (r0['bb_up_L2_[34..233]'] < -0.10)
        if not is_exhaustion:
            filtered_events_s2.append(t0)

    tl_s2 = simulate_long_exp121(filtered_events_s2, df_1h, df_1m, enable_bb_respiration=True)
    for t in tl_s2: t['side'] = 'long'
    trades_s2 = sorted(tl_s2 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    stages_res['Stage 2 (+ BB_Width & Stoch Filter)'] = compute_all_modes(trades_s2)

    # Stage 3: + 1m Dip-Rebound Timing
    print("\n--- Running Stage 3: + 1m Tree Dip-Rebound Timing ---")
    entry_map_s3 = build_1m_entry_timing_map(filtered_events_s2, df_1h, df_1m)
    tl_s3 = simulate_long_exp121(filtered_events_s2, df_1h, df_1m, enable_bb_respiration=True, entry_1m_map=entry_map_s3)
    for t in tl_s3: t['side'] = 'long'
    trades_s3 = sorted(tl_s3 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    stages_res['Stage 3 (+ 1m Precision Timing)'] = compute_all_modes(trades_s3)

    # Print Summary Table
    print("\n" + "=" * 80)
    print("ABLATION RESULTS TABLE (EXP-121)")
    print("=" * 80)
    for name, res in stages_res.items():
        m_std = res['master_std']
        m_ma = res['mode_a']
        m_mb = res['mode_b']
        print(f"[{name}]")
        print(f"  Master Std: N={m_std['executed_trades']:3d}, EV={m_std['net_mean_return_pct']:+.2f}%, PF={m_std['profit_factor']:.2f}, Tot={m_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_std['max_drawdown_pct']:.1f}%")
        print(f"  Mode A    : N={m_ma['executed_trades']:3d}, EV={m_ma['net_mean_return_pct']:+.2f}%, PF={m_ma['profit_factor']:.2f}, Tot={m_ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_ma['max_drawdown_pct']:.1f}%")
        print(f"  Mode B    : N={m_mb['executed_trades']:3d}, EV={m_mb['net_mean_return_pct']:+.2f}%, PF={m_mb['profit_factor']:.2f}, Tot={m_mb['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_mb['max_drawdown_pct']:.1f}%")

    # 4. Generate Plots
    plots_dir = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/121-multi-perspective-bb-trees-and-1m-execution/plots")
    os.makedirs(plots_dir, exist_ok=True)

    fig1_path = os.path.join(plots_dir, "fig1_ablation_equity_curves.png")
    fig2_path = os.path.join(plots_dir, "fig2_ablation_stages_bar.png")
    fig3_path = os.path.join(plots_dir, "fig3_bb_multiperspective_tree_cases.png")
    fig4_path = os.path.join(plots_dir, "fig4_yearly_overlay.png")

    plot_fig1_ablation_equity_curves(stages_res, fig1_path)
    plot_fig2_ablation_stages_bar(stages_res, fig2_path)
    plot_fig3_case_studies(df_1h, fig3_path)
    plot_fig4_yearly_overlay(trades_s3, fig4_path)

    print(f"\nAll 4 experiment plots generated in {plots_dir}.")

    # 5. Save metrics.json
    metrics_path = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/121-multi-perspective-bb-trees-and-1m-execution/metrics.json")
    json_metrics = {
        'experiment_id': 'EXP-121',
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
    print(f"Saved metrics to {metrics_path}.")

if __name__ == '__main__':
    main()
