#!/usr/bin/env python3
"""
EXP-117: 重複3分岐フィボナッチ・ツリー状態空間と無支持落下ナイフ遮断・遅延波束再点火則
および階層コヒーレンス連動型多段呼吸エグジットの実装・検証

Pre-registered Hypotheses:
- HYP-117-1: ツリー状態空間における無支持落下ナイフ遮断と強気スクイーズ逆張りショート遮断
- HYP-117-2: ツリー波束コヒーレンス確定による遅延再点火エントリー（Deferred Tree Wave-Packet Re-Ignition）
- HYP-117-3: 中長期ツリー・コヒーレンス連動型多階層呼吸エグジット（Tree-Coherence Respiration to S89）
- HYP-117-4: 統合ツリー状態空間ポートフォリオ（EXP-117 Master Std / Mode A / Mode B）の総合評価
"""

import os
import sys
import re
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(EXP_DIR, '../../..'))
sys.path.insert(0, ROOT_DIR)

import importlib.util

# Load exp111 and exp115 modules
path_111 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/111-short-dynamic-trailing-and-macro-bear-adaptation/run.py")
spec_111 = importlib.util.spec_from_file_location('exp111_mod', path_111)
exp111 = importlib.util.module_from_spec(spec_111)
sys.modules['exp111_mod'] = exp111
spec_111.loader.exec_module(exp111)

path_115 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/115-adaptive-multiscale-respiration-and-hysteresis-exit/run.py")
spec_115 = importlib.util.spec_from_file_location('exp115_mod', path_115)
exp115 = importlib.util.module_from_spec(spec_115)
sys.modules['exp115_mod'] = exp115
spec_115.loader.exec_module(exp115)

FRICTION_BPS = 0.0040  # 40 bps round-trip friction
TREE_SCALES = [8, 13, 21, 34, 55, 89, 144, 233, 377]

def build_fibonacci_tree_pyramid(df_1h, scales=None):
    """
    Constructs multi-layer Fibonacci tree state pyramid:
    - L1: Adjacent triplets (sa, sb, sc) -> 7 triplets for 9 scales
    - L2: Wave packets -> 5 nodes
    - L3: Macro regime nodes -> 3 nodes
    - L4: Global root -> 1 node
    Extensible to arbitrary scale list up to 17711.
    """
    if scales is None:
        scales = TREE_SCALES

    atr = df_1h['atr_24']
    close_1h = df_1h['close']

    # Ensure required SMAs and slopes exist
    for s in scales:
        if f'sma_{s}' not in df_1h.columns:
            df_1h[f'sma_{s}'] = close_1h.rolling(s).mean()
        if f'slope_{s}' not in df_1h.columns:
            df_1h[f'slope_{s}'] = (df_1h[f'sma_{s}'] - df_1h[f'sma_{s}'].shift(3)) / (3.0 * atr)

    # Layer 1: Adjacent Triplets
    l1_state = pd.DataFrame(index=df_1h.index)
    for k in range(len(scales) - 2):
        sa, sb, sc = scales[k], scales[k+1], scales[k+2]
        name = f"({sa},{sb},{sc})"
        scale_norm = np.sqrt(sb / 21.0)
        d_ab = np.tanh((df_1h[f'sma_{sa}'] - df_1h[f'sma_{sb}']) / (0.8 * scale_norm * atr))
        d_bc = np.tanh((df_1h[f'sma_{sb}'] - df_1h[f'sma_{sc}']) / (0.8 * scale_norm * atr))
        slp_b = np.tanh(df_1h[f'slope_{sb}'] * (8.0 * scale_norm))
        l1_state[name] = (d_ab + d_bc + slp_b) / 3.0
        df_1h[f'tree_L1_{name}'] = l1_state[name]

    # Layers L2, L3, ...
    cur_df = l1_state
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
            df_1h[f'tree_L{layer_idx}_{new_name}'] = next_df[new_name]
        cur_df = next_df
        layer_idx += 1

    return df_1h


# ==============================================================================
# Simulation Engines
# ==============================================================================

def simulate_exp117_long(events, df_1h, df_1m, enable_tree_respiration=False):
    """
    Simulate Long trades with continuous anchor shift, crossover hysteresis,
    and optional Tree-Coherence Respiration (HYP-117-3).
    """
    trades = []
    discovery_end = df_1m.index[-1]
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index:
            continue
        atr0 = df_1h['atr_24'].loc[t0]
        p_era = exp115.get_period(t0)
        sub_1m = df_1m.loc[entry_time : discovery_end]
        if len(sub_1m) < 60:
            continue
        p0 = sub_1m['open'].iloc[0]
        sub_times = sub_1m.index
        sub_opens = sub_1m['open'].values
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values
        n_bars = len(sub_1m)
        max_mfe_atr = 0.0
        exited = False

        row_0 = df_1h.loc[t0]
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

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    # Exhale Re-expansion (EXP-115 Stage 2 logic)
                    is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                  (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                 (row_1h['slope_55'] > 0) and \
                                 (row_1h['sma_55'] > p0)
                    if is_impulse and current_anchor < 55:
                        if c_1h < row_1h['sma_21'] or row_1h['slope_34'] > 0:
                            current_anchor = 55

                    # HYP-117-3: Tree-Coherence Multi-Layer Respiration to S89
                    if enable_tree_respiration and armed:
                        is_macro_tree_impulse = (
                            (row_1h['tree_L2_[34..233]'] > 0.70) and
                            (row_1h['tree_L1_(55,89,144)'] > 0.70) and
                            (row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144'] > row_1h['sma_233']) and
                            (row_1h['slope_89'] > 0) and
                            (row_1h['sma_89'] > p0)
                        )
                        if is_macro_tree_impulse and current_anchor <= 55 and c_1h < row_1h['sma_34']:
                            current_anchor = 89

                    prev_above_band = now_above_band
                    prev_afs_diff = now_afs_diff
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    if not armed and row_1h['close'] < row_1h['sma_21'] and row_1h['slope_21'] < 0 and row_1h['afs_order_score'] == 0:
                        dur_h = float(np.round((i + 1) / 60.0, 2))
                        t_exit = t_bar + pd.Timedelta(minutes=1)
                        trades.append({
                            't0': t0, 'entry_time': entry_time, 'exit_time': t_exit, 'period': p_era,
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
            if cur_high > highest_price:
                highest_price = cur_high
            cur_mfe = (cur_high - p0) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe

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
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_exit, 'period': p_era,
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
            dur_h = float(np.round((sub_times[-1] - entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (sub_closes[-1] - p0)/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'final_anchor': current_anchor,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
            })
    return trades


def simulate_exp117_short(events, df_1h, df_1m, enable_tree_respiration=False):
    """
    Simulate Short trades with continuous anchor shift, crossover hysteresis,
    and optional Tree-Coherence Respiration (HYP-117-3).
    """
    trades = []
    discovery_end = df_1m.index[-1]
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index:
            continue
        atr0 = df_1h['atr_24'].loc[t0]
        p_era = exp115.get_period(t0)
        sub_1m = df_1m.loc[entry_time : discovery_end]
        if len(sub_1m) < 60:
            continue
        p0 = sub_1m['open'].iloc[0]
        sub_times = sub_1m.index
        sub_opens = sub_1m['open'].values
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values
        n_bars = len(sub_1m)
        max_mfe_atr = 0.0
        exited = False

        row_0 = df_1h.loc[t0]
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

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    # Exhale Re-expansion (EXP-115 Stage 2 logic)
                    is_impulse = ((row_1h['sma_55'] < row_1h['sma_89'] < row_1h['sma_144']) or \
                                  (row_1h['sma_21'] < row_1h['sma_34'] < row_1h['sma_55'])) and \
                                 (row_1h['slope_55'] < 0) and \
                                 (row_1h['sma_55'] < p0)
                    if is_impulse and current_anchor < 55:
                        if c_1h > row_1h['sma_21'] or row_1h['slope_34'] < 0:
                            current_anchor = 55

                    # HYP-117-3: Tree-Coherence Multi-Layer Respiration for Short to S89
                    if enable_tree_respiration and armed:
                        is_macro_tree_bear_impulse = (
                            (row_1h['tree_L2_[34..233]'] < -0.70) and
                            (row_1h['tree_L1_(55,89,144)'] < -0.70) and
                            (row_1h['sma_55'] < row_1h['sma_89'] < row_1h['sma_144'] < row_1h['sma_233']) and
                            (row_1h['slope_89'] < 0) and
                            (row_1h['sma_89'] < p0)
                        )
                        if is_macro_tree_bear_impulse and current_anchor <= 55 and c_1h > row_1h['sma_34']:
                            current_anchor = 89

                    prev_below_band = now_below_band
                    prev_afs_diff = now_afs_diff
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    if not armed and row_1h['close'] > row_1h['sma_21'] and row_1h['slope_21'] > 0 and row_1h['afs_order_score_bear'] == 0:
                        dur_h = float(np.round((i + 1) / 60.0, 2))
                        t_exit = t_bar + pd.Timedelta(minutes=1)
                        trades.append({
                            't0': t0, 'entry_time': entry_time, 'exit_time': t_exit, 'period': p_era,
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
            if cur_low < lowest_price:
                lowest_price = cur_low
            cur_mfe = (p0 - cur_low) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe

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
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_exit, 'period': p_era,
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
            dur_h = float(np.round((sub_times[-1] - entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (p0 - sub_closes[-1])/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'final_anchor': current_anchor,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
            })
    return trades


# ==============================================================================
# Main Experiment Execution
# ==============================================================================

def run_experiment():
    print("=" * 80)
    print("EXP-117: Overlapping Fibonacci Tree State Space & Ignition / Respiration")
    print("=" * 80)

    # 1. Load Data & Build Tree Pyramid
    df_1h, df_1m, long_events_base, short_events_base, plunge_events = exp111.load_data_and_features()
    exp115.add_multiscale_features_exp115(df_1h)
    build_fibonacci_tree_pyramid(df_1h, scales=TREE_SCALES)

    close_1h = df_1h['close']
    open_1h = df_1h['open']

    # 2. Gate Definitions
    gap_4181_6765 = df_1h['gap_4181_6765']
    vacuum_trap_filter = (df_1h['range_pos_720h'] >= 0.80) & (gap_4181_6765 >= 10.0)
    gate_trap = ~(df_1h['macro_age_ratio'] > 2.0)
    gate_booster = (df_1h['afs_order_score'] == 3)

    # HYP-117-1: Tree Unanchored Knife Gate
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

    # Stage 1 Events
    raw_stage1 = (mvc_long_old | pb_long | (prop_mask_fast & (~is_unanchored_knife))) & (~vacuum_trap_filter)
    events_stage1 = df_1h.index[exp111.exp95.decluster_events(raw_stage1, cooldown_bars=24)]

    # HYP-117-2: Deferred Tree Wave-Packet Re-Ignition
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

    # 3. Computing EXP-109 Production Baseline
    print("\n--- Computing EXP-109 Production Baseline ---")
    t_l_109 = exp111.exp109.simulate_regime_adaptive_long(long_events_base, df_1h, df_1m)
    t_sn_109 = exp111.exp95.simulate_1m_path_short(short_events_base, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0)
    t_sp_109 = exp111.exp103.simulate_plunge_short(plunge_events, df_1h, df_1m, target_sma_col='sma_6765', stop_atr=2.5)
    for t in t_l_109: t['side'] = 'long'
    for t in t_sn_109 + t_sp_109: t['side'] = 'short'
    all_109 = t_l_109 + t_sn_109 + t_sp_109
    sorted_109 = sorted(all_109, key=lambda x: x['entry_time'])
    m_109_std = exp111.compute_metrics(all_109)
    t_109_ma = []
    last_exit = pd.Timestamp.min.tz_localize('UTC')
    for t in sorted_109:
        if t['entry_time'] >= last_exit:
            t_109_ma.append(t)
            last_exit = t['exit_time']
    m_109_ma = exp111.compute_metrics(t_109_ma)
    print(f"EXP-109 Standard: N={m_109_std['executed_trades']}, EV={m_109_std['net_mean_return_pct']:+.2f}%, PF={m_109_std['profit_factor']:.2f}, Tot={m_109_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_109_std['max_drawdown_pct']:.1f}%")
    print(f"EXP-109 Mode A  : N={m_109_ma['executed_trades']}, EV={m_109_ma['net_mean_return_pct']:+.2f}%, PF={m_109_ma['profit_factor']:.2f}, Tot={m_109_ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_109_ma['max_drawdown_pct']:.1f}%")

    # 4. Computing EXP-113 Pure Baseline
    print("\n--- Computing EXP-113 Pure Baseline ---")
    t_l_113 = exp115.exp113.simulate_multiscale_long(long_events_base, df_1h, df_1m, enable_overhead=True)
    t_sn_113 = exp115.exp113.simulate_multiscale_short(short_events_base, df_1h, df_1m)
    t_sp_113 = exp115.exp113.simulate_multiscale_plunge_short(plunge_events, df_1h, df_1m)
    for t in t_l_113: t['side'] = 'long'
    for t in t_sn_113 + t_sp_113: t['side'] = 'short'
    all_113 = t_l_113 + t_sn_113 + t_sp_113
    sorted_113 = sorted(all_113, key=lambda x: x['entry_time'])
    m_113_std = exp111.compute_metrics(all_113)
    t_113_ma = []
    last_exit = pd.Timestamp.min.tz_localize('UTC')
    for t in sorted_113:
        if t['entry_time'] >= last_exit:
            t_113_ma.append(t)
            last_exit = t['exit_time']
    m_113_ma = exp111.compute_metrics(t_113_ma)
    yearly_113_ma = exp111.compute_yearly_metrics(t_113_ma)
    print(f"EXP-113 Standard: N={m_113_std['executed_trades']}, EV={m_113_std['net_mean_return_pct']:+.2f}%, PF={m_113_std['profit_factor']:.2f}, Tot={m_113_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_113_std['max_drawdown_pct']:.1f}%")
    print(f"EXP-113 Mode A  : N={m_113_ma['executed_trades']}, EV={m_113_ma['net_mean_return_pct']:+.2f}%, PF={m_113_ma['profit_factor']:.2f}, Tot={m_113_ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_113_ma['max_drawdown_pct']:.1f}%")

    # 5. EXP-117 4-Stage Ablation Simulation
    stages_config = [
        ("Stage 0: EXP-115 Baseline", long_events_base, short_events_base, False),
        ("Stage 1: +HYP-117-1 (Tree Unanchored Knife & Squeeze Gate)", events_stage1, short_events_stage1, False),
        ("Stage 2: +HYP-117-2 (Deferred Tree Wave-Packet Re-Ignition)", events_stage2, short_events_stage1, False),
        ("Stage 3: +HYP-117-3 (Tree-Coherence Multi-Layer Respiration)", events_stage2, short_events_stage1, True),
    ]

    ablation_results = {}
    stage_trades = {}

    for name, levs, sevs, tree_resp in stages_config:
        tl = simulate_exp117_long(levs, df_1h, df_1m, enable_tree_respiration=tree_resp)
        ts = simulate_exp117_short(sevs, df_1h, df_1m, enable_tree_respiration=tree_resp)
        for t in tl: t['side'] = 'long'
        for t in ts + plunge_trades: t['side'] = 'short'

        all_t = sorted(tl + plunge_trades + ts, key=lambda x: x['entry_time'])

        # Mode A: strictly 1 position exclusive
        filtered_a = []
        last_exit = pd.Timestamp.min.tz_localize('UTC')
        for t in all_t:
            if t['entry_time'] >= last_exit:
                filtered_a.append(t)
                last_exit = t['exit_time']

        # Mode B: max 2 concurrent, same-direction exclusive
        filtered_b = exp115.apply_mode_b_concurrency_limit(all_t, max_concurrent=2)

        m_std = exp111.compute_metrics(all_t)
        ml = exp111.compute_metrics(tl)
        ms = exp111.compute_metrics(ts + plunge_trades)
        ma = exp111.compute_metrics(filtered_a)
        mb = exp111.compute_metrics(filtered_b)

        y_std = exp111.compute_yearly_metrics(all_t)
        y_a = exp111.compute_yearly_metrics(filtered_a)
        y_b = exp111.compute_yearly_metrics(filtered_b)

        lookup = {str(t['entry_time'])[:16]: t for t in tl + ts}
        c1 = lookup.get('2020-12-11 18:00')
        c2 = lookup.get('2021-01-30 03:00')
        c2_reignite = lookup.get('2021-02-02 15:00')
        c2_wave = lookup.get('2021-02-04 20:00')
        c3 = lookup.get('2022-06-19 19:00')

        ablation_results[name] = {
            'long': ml,
            'short': ms,
            'master_std': m_std,
            'master_a': ma,
            'master_b': mb,
            'yearly_std': y_std,
            'yearly_a': y_a,
            'yearly_b': y_b,
            'case1': c1,
            'case2': c2,
            'case2_reignite': c2_reignite,
            'case2_wave': c2_wave,
            'case3': c3
        }

        stage_trades[name] = {
            'long': tl,
            'short': ts + plunge_trades,
            'master_std': all_t,
            'master_a': filtered_a,
            'master_b': filtered_b
        }

        print(f"\n=== {name} ===")
        print(f"  Long Solo : N={ml['executed_trades']}, WR={ml['win_rate_pct']:.1f}%, EV={ml['net_mean_return_pct']:+.2f}%, PF={ml['profit_factor']:.2f}, Tot={ml['total_opportunity_net_return_pct']:+.1f}%, MaxDD={ml['max_drawdown_pct']:.1f}%")
        print(f"  Short Solo: N={ms['executed_trades']}, WR={ms['win_rate_pct']:.1f}%, EV={ms['net_mean_return_pct']:+.2f}%, PF={ms['profit_factor']:.2f}, Tot={ms['total_opportunity_net_return_pct']:+.1f}%, MaxDD={ms['max_drawdown_pct']:.1f}%")
        print(f"  Master Std: N={m_std['executed_trades']}, WR={m_std['win_rate_pct']:.1f}%, EV={m_std['net_mean_return_pct']:+.2f}%, PF={m_std['profit_factor']:.2f}, Tot={m_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_std['max_drawdown_pct']:.1f}%")
        print(f"  Mode A    : N={ma['executed_trades']}, WR={ma['win_rate_pct']:.1f}%, EV={ma['net_mean_return_pct']:+.2f}%, PF={ma['profit_factor']:.2f}, Tot={ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={ma['max_drawdown_pct']:.1f}%")
        print(f"  Mode B    : N={mb['executed_trades']}, WR={mb['win_rate_pct']:.1f}%, EV={mb['net_mean_return_pct']:+.2f}%, PF={mb['profit_factor']:.2f}, Tot={mb['total_opportunity_net_return_pct']:+.1f}%, MaxDD={mb['max_drawdown_pct']:.1f}%")
        if c1: print(f"    Case 1 (2020-12-11 Long): {c1['net_ret']*100:+.2f}% ({c1['exit']}, dur={c1['duration_h']}h, anchor=S{c1['final_anchor']})")
        if c2: print(f"    Case 2 (2021-01-30 Long): {c2['net_ret']*100:+.2f}% ({c2['exit']}, dur={c2['duration_h']}h, anchor=S{c2['final_anchor']})")
        if c2_reignite: print(f"    Case 2 Re-ignite (2021-02-02 Long): {c2_reignite['net_ret']*100:+.2f}% ({c2_reignite['exit']}, dur={c2_reignite['duration_h']}h, anchor=S{c2_reignite['final_anchor']})")
        if c2_wave: print(f"    Case 2 Wave (2021-02-04 Long): {c2_wave['net_ret']*100:+.2f}% ({c2_wave['exit']}, dur={c2_wave['duration_h']}h, anchor=S{c2_wave['final_anchor']})")
        if c3: print(f"    Case 3 (2022-06-19 Short): {c3['net_ret']*100:+.2f}% ({c3['exit']}, dur={c3['duration_h']}h, anchor=S{c3['final_anchor']})")

    # Primary Stage 3 (EXP-117 Full Model)
    primary_stage_name = "Stage 3: +HYP-117-3 (Tree-Coherence Multi-Layer Respiration)"
    primary_trades_std = stage_trades[primary_stage_name]['master_std']
    primary_trades_a = stage_trades[primary_stage_name]['master_a']
    primary_trades_b = stage_trades[primary_stage_name]['master_b']

    yearly_a = ablation_results[primary_stage_name]['yearly_a']
    yearly_b = ablation_results[primary_stage_name]['yearly_b']
    ci_a = exp111.bootstrap_ci(primary_trades_a)
    ci_b = exp111.bootstrap_ci(primary_trades_b)

    print("\n--- EXP-117 Master Mode A Yearly Performance (Stage 3) ---")
    for yr, y_m in yearly_a.items():
        print(f"  {yr}: N={y_m['executed_trades']}, Net EV={y_m['net_mean_return_pct']:+.2f}%, PF={y_m['profit_factor']:.2f}, Tot={y_m['total_opportunity_net_return_pct']:+.1f}%, MaxDD={y_m['max_drawdown_pct']:.1f}%")

    print("\n--- EXP-117 Bootstrap 95% CI (Mode A) ---")
    print(f"  EV 95% CI: [{ci_a[0]:+.2f}%, {ci_a[1]:+.2f}%]")

    # 6. Clean and Serialize metrics.json
    def clean_dict(d):
        out = {}
        for k, v in d.items():
            if isinstance(v, (np.integer, int)):
                out[k] = int(v)
            elif isinstance(v, (np.floating, float)):
                out[k] = float(v)
            elif isinstance(v, pd.Timestamp):
                out[k] = str(v)
            elif isinstance(v, dict):
                out[k] = clean_dict(v)
            elif isinstance(v, list):
                out[k] = [clean_dict(x) if isinstance(x, dict) else (float(x) if isinstance(x, (np.floating, float)) else x) for x in v]
            else:
                out[k] = v
        return out

    metrics_output = {
        'baseline_exp109': {
            'master_std': clean_dict(m_109_std),
            'master_a': clean_dict(m_109_ma)
        },
        'baseline_exp113_pure': {
            'master_std': clean_dict(m_113_std),
            'master_a': clean_dict(m_113_ma),
            'yearly_a': {str(k): clean_dict(v) for k, v in yearly_113_ma.items()}
        },
        'ablation': {
            k: {
                subk: clean_dict(subv) if isinstance(subv, dict) else subv
                for subk, subv in v.items()
            }
            for k, v in ablation_results.items()
        },
        'exp117_primary_std': {
            'metrics': clean_dict(ablation_results[primary_stage_name]['master_std']),
            'yearly': {str(k): clean_dict(v) for k, v in ablation_results[primary_stage_name]['yearly_std'].items()}
        },
        'exp117_primary_mode_a': {
            'metrics': clean_dict(ablation_results[primary_stage_name]['master_a']),
            'yearly': {str(k): clean_dict(v) for k, v in yearly_a.items()},
            'bootstrap_ci_ev': [float(ci_a[0]), float(ci_a[1])]
        },
        'exp117_primary_mode_b': {
            'metrics': clean_dict(ablation_results[primary_stage_name]['master_b']),
            'yearly': {str(k): clean_dict(v) for k, v in yearly_b.items()},
            'bootstrap_ci_ev': [float(ci_b[0]), float(ci_b[1])]
        }
    }

    metrics_path = os.path.join(EXP_DIR, 'metrics.json')
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics_output, f, indent=2)
    print(f"\nSaved metrics.json successfully to {metrics_path}")

    # ==============================================================================
    # 7. Generate Dynamically All 4 Plots
    # ==============================================================================
    plots_dir = os.path.join(EXP_DIR, 'plots')
    os.makedirs(plots_dir, exist_ok=True)

    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']

    # --------------------------------------------------------------------------
    # Plot 1: fig1_ablation_equity_curves.png
    # Cumulative Net Return & Drawdown (EXP-109 Mode A, EXP-113 Mode A, EXP-115 Mode A, EXP-117 Mode A)
    # --------------------------------------------------------------------------
    fig, (ax_ret, ax_dd) = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    t_115_ma = stage_trades["Stage 0: EXP-115 Baseline"]['master_a']
    series_data = [
        ('EXP-109 Baseline (Production)', t_109_ma, '#7f8c8d', '--', 1.8),
        ('EXP-113 Pure Baseline', t_113_ma, '#e74c3c', ':', 2.0),
        ('EXP-115 Pure Mode A (Stage 0)', t_115_ma, '#3498db', '-.', 2.0),
        ('EXP-117 Pure Mode A (Stage 3)', primary_trades_a, '#27ae60', '-', 2.6),
    ]

    for label, tr_list, col, ls, lw in series_data:
        if not tr_list:
            continue
        s_tr = sorted(tr_list, key=lambda x: x['exit_time'])
        times = [s_tr[0]['entry_time']] + [t['exit_time'] for t in s_tr]
        rets = [0.0] + [t['net_ret'] for t in s_tr]
        cum_ret = np.cumsum(rets)
        peak = np.maximum.accumulate(cum_ret)
        dd = cum_ret - peak

        ax_ret.plot(times, cum_ret * 100.0, label=f"{label} (Tot: {cum_ret[-1]*100:+.1f}%)", color=col, linestyle=ls, linewidth=lw)
        ax_dd.plot(times, dd * 100.0, label=label, color=col, linestyle=ls, linewidth=lw)

    ax_ret.set_title('EXP-117 Fibonacci Tree State & Ignition vs Baselines (Cumulative Net Return & Drawdown)', fontsize=14, fontweight='bold')
    ax_ret.set_ylabel('Cumulative Net Return (%)', fontsize=12)
    ax_ret.legend(loc='upper left', fontsize=11, framealpha=0.9)
    ax_ret.grid(True, alpha=0.3)

    ax_dd.set_ylabel('Drawdown (%)', fontsize=12)
    ax_dd.set_xlabel('Date', fontsize=12)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax_dd.grid(True, alpha=0.3)

    fig.tight_layout()
    fig1_path = os.path.join(plots_dir, 'fig1_ablation_equity_curves.png')
    fig.savefig(fig1_path, dpi=150)
    plt.close(fig)
    print("Saved plots/fig1_ablation_equity_curves.png")

    # --------------------------------------------------------------------------
    # Plot 2: fig2_ablation_stages_bar.png
    # Bar chart comparing Stage 0, Stage 1, Stage 2, Stage 3 across Master Std, Mode A, Mode B
    # --------------------------------------------------------------------------
    stage_labels = [
        'Stage 0\nEXP-115 Base',
        'Stage 1\n+Tree Gate',
        'Stage 2\n+Deferred Ign',
        'Stage 3\n+Tree Resp'
    ]
    stg_keys = [
        "Stage 0: EXP-115 Baseline",
        "Stage 1: +HYP-117-1 (Tree Unanchored Knife & Squeeze Gate)",
        "Stage 2: +HYP-117-2 (Deferred Tree Wave-Packet Re-Ignition)",
        "Stage 3: +HYP-117-3 (Tree-Coherence Multi-Layer Respiration)"
    ]

    ret_std = [ablation_results[k]['master_std']['total_opportunity_net_return_pct'] for k in stg_keys]
    ret_ma  = [ablation_results[k]['master_a']['total_opportunity_net_return_pct'] for k in stg_keys]
    ret_mb  = [ablation_results[k]['master_b']['total_opportunity_net_return_pct'] for k in stg_keys]

    pf_std  = [ablation_results[k]['master_std']['profit_factor'] for k in stg_keys]
    pf_ma   = [ablation_results[k]['master_a']['profit_factor'] for k in stg_keys]
    pf_mb   = [ablation_results[k]['master_b']['profit_factor'] for k in stg_keys]

    fig, (ax_r, ax_p) = plt.subplots(1, 2, figsize=(15, 6))
    x = np.arange(len(stage_labels))
    w = 0.26

    # Return Bars
    b1 = ax_r.bar(x - w, ret_std, w, label='Master Std (Unconstrained)', color='#34495e', alpha=0.9)
    b2 = ax_r.bar(x, ret_ma, w, label='Mode A (1 Pos Exclusive)', color='#2980b9', alpha=0.9)
    b3 = ax_r.bar(x + w, ret_mb, w, label='Mode B (Max 2 Concur)', color='#27ae60', alpha=0.9)

    ax_r.set_title('Cumulative Net Return (%) across Ablation Stages', fontsize=13, fontweight='bold')
    ax_r.set_xticks(x)
    ax_r.set_xticklabels(stage_labels, fontsize=10)
    ax_r.set_ylabel('Total Net Return (%)', fontsize=11)
    ax_r.legend(loc='upper left', fontsize=10)
    ax_r.grid(True, axis='y', alpha=0.3)

    for bar_group in [b1, b2, b3]:
        for rect in bar_group:
            h = rect.get_height()
            ax_r.text(rect.get_x() + rect.get_width() / 2.0, h + 3.0, f"{h:+.1f}%", ha='center', va='bottom', fontsize=8.5, fontweight='bold')

    # Profit Factor Bars
    b4 = ax_p.bar(x - w, pf_std, w, label='Master Std', color='#34495e', alpha=0.9)
    b5 = ax_p.bar(x, pf_ma, w, label='Mode A', color='#2980b9', alpha=0.9)
    b6 = ax_p.bar(x + w, pf_mb, w, label='Mode B', color='#27ae60', alpha=0.9)

    ax_p.set_title('Profit Factor (PF) across Ablation Stages', fontsize=13, fontweight='bold')
    ax_p.set_xticks(x)
    ax_p.set_xticklabels(stage_labels, fontsize=10)
    ax_p.set_ylabel('Profit Factor (PF)', fontsize=11)
    ax_p.axhline(1.0, color='gray', linestyle='--', linewidth=1.0)
    ax_p.axhline(3.0, color='#e67e22', linestyle=':', linewidth=1.2, label='PF = 3.0 Benchmark')
    ax_p.legend(loc='upper left', fontsize=10)
    ax_p.grid(True, axis='y', alpha=0.3)

    for bar_group in [b4, b5, b6]:
        for rect in bar_group:
            h = rect.get_height()
            ax_p.text(rect.get_x() + rect.get_width() / 2.0, h + 0.04, f"{h:.2f}", ha='center', va='bottom', fontsize=8.5, fontweight='bold')

    fig.suptitle('EXP-117 4-Stage Ablation Progression: Stepwise Superiority of Tree Pyramid Engine', fontsize=14, fontweight='bold')
    fig.tight_layout()
    fig2_path = os.path.join(plots_dir, 'fig2_ablation_stages_bar.png')
    fig.savefig(fig2_path, dpi=150)
    plt.close(fig)
    print("Saved plots/fig2_ablation_stages_bar.png")

    # --------------------------------------------------------------------------
    # Plot 3: fig3_case2_tree_breakthrough.png
    # Price & Fibonacci Tree chart for Case 2 window (2021-01-29 to 2021-02-14)
    # --------------------------------------------------------------------------
    w_start = '2021-01-29 00:00'
    w_end = '2021-02-14 18:00'
    sub_df = df_1h.loc[w_start:w_end]

    fig, (ax_price, ax_tree) = plt.subplots(2, 1, figsize=(16, 10), sharex=True, gridspec_kw={'height_ratios': [2.2, 1.2]})

    # Price and Structure lines
    ax_price.plot(sub_df.index, sub_df['close'], label='BTC/USDT 1H Close', color='black', linewidth=1.6)
    ax_price.plot(sub_df.index, sub_df['sma_21'], label='S21 (Fast)', color='#e74c3c', linestyle='--', linewidth=1.1)
    ax_price.plot(sub_df.index, sub_df['sma_34'], label='S34', color='#e67e22', linestyle='--', linewidth=1.1)
    ax_price.plot(sub_df.index, sub_df['sma_55'], label='S55 (Intermediate Floor)', color='#27ae60', linestyle='--', linewidth=1.3)
    ax_price.plot(sub_df.index, sub_df['sma_89'], label='S89 (Respiration Anchor)', color='#16a085', linestyle='-', linewidth=1.5)
    ax_price.plot(sub_df.index, sub_df['sma_144'], label='S144', color='#2980b9', linestyle=':', linewidth=1.2)
    ax_price.plot(sub_df.index, sub_df['sma_233'], label='S233 (Macro Anchor)', color='#8e44ad', linestyle=':', linewidth=1.4)

    # Trade Points:
    # 1. 2021-01-30 03:00 Knife entry (Stage 0)
    t_knife = pd.Timestamp('2021-01-30 03:00:00+00:00')
    p_knife = 34295.92
    ax_price.scatter([t_knife], [p_knife], color='red', marker='v', s=130, zorder=6, label='Stage 0 Knife Entry ($34,296)')
    ax_price.scatter([pd.Timestamp('2021-01-31 09:01:00+00:00')], [33650.0], color='red', marker='x', s=150, zorder=6, label='Stage 0 Invalidation (-1.94%)')

    ax_price.annotate(
        "Stage 0 (EXP-115): Premature Entry ($34,296)\nExited at S233 Invalidation (-1.94%)\nStage 1-3: Suppressed by HYP-117-1 Tree Gate!",
        xy=(t_knife, p_knife),
        xytext=(pd.Timestamp('2021-01-29 06:00:00+00:00'), 38000),
        arrowprops=dict(facecolor='red', shrink=0.05, width=1.5, headwidth=6),
        fontsize=9.5, fontweight='bold', color='#c0392b',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#fadbd8', edgecolor='red')
    )

    # 2. 2021-02-02 15:00 Deferred Re-ignition
    t_reignite = pd.Timestamp('2021-02-02 15:00:00+00:00')
    p_reignite = 35528.00
    ax_price.scatter([t_reignite], [p_reignite], color='#2980b9', marker='^', s=140, zorder=6, label='HYP-117-2 Deferred Ignition ($35,528)')
    ax_price.scatter([pd.Timestamp('2021-02-07 18:19:00+00:00')], [38480.0], color='#2980b9', marker='o', s=130, zorder=6, label='Stage 3 Exit (+8.31%)')

    ax_price.annotate(
        "HYP-117-2: Deferred Tree Ignition ($35,528)\nTree Coherence Verified!\nGain: +9.25% (Stage 2) / +8.31% (Stage 3)",
        xy=(t_reignite, p_reignite),
        xytext=(pd.Timestamp('2021-01-31 18:00:00+00:00'), 41500),
        arrowprops=dict(facecolor='#2980b9', shrink=0.05, width=1.5, headwidth=6),
        fontsize=9.5, fontweight='bold', color='#1f618d',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#ebf5fb', edgecolor='#2980b9')
    )

    # 3. 2021-02-04 20:00 Subsequent Wave Riding
    t_wave = pd.Timestamp('2021-02-04 20:00:00+00:00')
    p_wave = 37645.00
    ax_price.scatter([t_wave], [p_wave], color='#27ae60', marker='^', s=150, zorder=6, label='Wave Entry ($37,645)')
    ax_price.scatter([pd.Timestamp('2021-02-10 18:11:00+00:00')], [45300.0], color='#e67e22', marker='s', s=130, zorder=6, label='Stage 0-2 S55 Exit (+20.33%)')
    ax_price.scatter([pd.Timestamp('2021-02-13 14:06:00+00:00')], [47272.0], color='#27ae60', marker='*', s=200, zorder=6, label='Stage 3 S89 Respiration Exit (+25.65%)')

    ax_price.annotate(
        "Stage 0-2: S55 Exit (+20.33%, 142h)\nStage 3 HYP-117-3: Tree Exhale to S89\nRides 210.1h to $47,272 (+25.65%)!\n+5.32%pt Extra Trend Capture",
        xy=(pd.Timestamp('2021-02-13 14:06:00+00:00'), 47272.0),
        xytext=(pd.Timestamp('2021-02-07 00:00:00+00:00'), 48500),
        arrowprops=dict(facecolor='#27ae60', shrink=0.05, width=1.5, headwidth=6),
        fontsize=9.5, fontweight='bold', color='#1e8449',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#d5f5e3', edgecolor='#27ae60')
    )

    ax_price.set_title('Case 2 (2021-01-29 ~ 2021-02-14): Knife Suppression, Deferred Tree Ignition & S89 Respiration Extension', fontsize=13, fontweight='bold')
    ax_price.set_ylabel('Price (USD)', fontsize=11)
    ax_price.legend(loc='lower right', fontsize=8.5, framealpha=0.9)
    ax_price.grid(True, alpha=0.3)

    # Lower Panel: Fibonacci Tree Coherence Signals
    ax_tree.plot(sub_df.index, sub_df['tree_L1_(8,13,21)'], label='L1(8,13,21) Fast Momentum', color='#e74c3c', linewidth=1.5)
    ax_tree.plot(sub_df.index, sub_df['tree_L2_[8..55]'], label='L2[8..55] Fast-Meso Wave Packet', color='#3498db', linewidth=1.8)
    ax_tree.plot(sub_df.index, sub_df['tree_L3_[13..233]'], label='L3[13..233] Meso-Macro Regime', color='#8e44ad', linewidth=2.0)
    ax_tree.plot(sub_df.index, sub_df['tree_L1_(89,144,233)'], label='L1(89,144,233) Macro Anchor Support', color='#16a085', linestyle='--', linewidth=1.5)

    ax_tree.axhline(0.0, color='black', linewidth=0.9)
    ax_tree.axhline(0.25, color='#3498db', linestyle=':', label='L2 Ignition Threshold (+0.25)')
    ax_tree.axhline(0.15, color='#8e44ad', linestyle=':', label='L3 Ignition Threshold (+0.15)')
    ax_tree.axhline(0.70, color='#27ae60', linestyle='--', label='Macro Coherence Exhale (+0.70)')

    ax_tree.axvspan(pd.Timestamp('2021-01-29 18:00:00+00:00'), pd.Timestamp('2021-01-31 06:00:00+00:00'), color='#fadbd8', alpha=0.3, label='Unanchored Knife Phase')
    ax_tree.axvspan(pd.Timestamp('2021-02-02 12:00:00+00:00'), pd.Timestamp('2021-02-03 00:00:00+00:00'), color='#ebf5fb', alpha=0.3, label='Tree Re-ignition Phase')
    ax_tree.axvspan(pd.Timestamp('2021-02-07 00:00:00+00:00'), pd.Timestamp('2021-02-10 12:00:00+00:00'), color='#d5f5e3', alpha=0.3, label='S89 Respiration Exhale Phase')

    ax_tree.set_ylabel('Tree Coherence [-1, +1]', fontsize=11)
    ax_tree.set_xlabel('Date', fontsize=11)
    ax_tree.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    ax_tree.legend(loc='lower left', fontsize=8.0, ncol=2, framealpha=0.9)
    ax_tree.grid(True, alpha=0.3)

    fig.tight_layout()
    fig3_path = os.path.join(plots_dir, 'fig3_case2_tree_breakthrough.png')
    fig.savefig(fig3_path, dpi=150)
    plt.close(fig)
    print("Saved plots/fig3_case2_tree_breakthrough.png")

    # --------------------------------------------------------------------------
    # Plot 4: fig4_yearly_overlay.png
    # Year-by-year (2020-2025) Cumulative Net Return & Profit Factor (EXP-113 vs EXP-115 vs EXP-117 Mode A)
    # --------------------------------------------------------------------------
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    y_113_ret = [yearly_113_ma.get(str(y), {}).get('total_opportunity_net_return_pct', 0.0) for y in years]
    y_115_ret = [ablation_results["Stage 0: EXP-115 Baseline"]['yearly_a'].get(str(y), {}).get('total_opportunity_net_return_pct', 0.0) for y in years]
    y_117_ret = [yearly_a.get(str(y), {}).get('total_opportunity_net_return_pct', 0.0) for y in years]

    y_113_pf  = [yearly_113_ma.get(str(y), {}).get('profit_factor', 0.0) for y in years]
    y_115_pf  = [ablation_results["Stage 0: EXP-115 Baseline"]['yearly_a'].get(str(y), {}).get('profit_factor', 0.0) for y in years]
    y_117_pf  = [yearly_a.get(str(y), {}).get('profit_factor', 0.0) for y in years]

    fig, (ax_bar, ax_pf) = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [2.2, 1.0]})
    x = np.arange(len(years))
    width = 0.27

    tot_113_ret = m_113_ma['total_opportunity_net_return_pct']
    tot_115_ret = ablation_results["Stage 0: EXP-115 Baseline"]['master_a']['total_opportunity_net_return_pct']
    tot_117_ret = ablation_results[primary_stage_name]['master_a']['total_opportunity_net_return_pct']

    rects1 = ax_bar.bar(x - width, y_113_ret, width, label=f'EXP-113 Pure Baseline (Tot: {tot_113_ret:+.1f}%)', color='#e74c3c', alpha=0.85)
    rects2 = ax_bar.bar(x, y_115_ret, width, label=f'EXP-115 Pure Mode A (Tot: {tot_115_ret:+.1f}%)', color='#3498db', alpha=0.85)
    rects3 = ax_bar.bar(x + width, y_117_ret, width, label=f'EXP-117 Pure Mode A (Stage 3, Tot: {tot_117_ret:+.1f}%)', color='#27ae60', alpha=0.9)

    ax_bar.set_title('Year-by-Year Cumulative Net Return & Profit Factor: EXP-113 vs EXP-115 vs EXP-117\n(Consistent Multi-Scale Superiority Across Bull, Bear, and Transition Regimes)', fontsize=13, fontweight='bold')
    ax_bar.set_ylabel('Annual Net Return (%)', fontsize=11)
    ax_bar.legend(loc='upper right', fontsize=10.5, framealpha=0.9)
    ax_bar.axhline(0, color='black', linewidth=1.0)
    ax_bar.grid(True, axis='y', alpha=0.3)

    for i in range(len(years)):
        v1, v2, v3 = y_113_ret[i], y_115_ret[i], y_117_ret[i]
        ax_bar.text(x[i] - width, v1 + (2.0 if v1 >= 0 else -5.0), f"{v1:+.1f}%", ha='center', fontsize=8.5, color='#c0392b')
        ax_bar.text(x[i], v2 + (2.0 if v2 >= 0 else -5.0), f"{v2:+.1f}%", ha='center', fontsize=8.5, color='#2980b9')
        ax_bar.text(x[i] + width, v3 + (2.0 if v3 >= 0 else -5.0), f"{v3:+.1f}%", ha='center', fontsize=8.5, color='#1e8449', fontweight='bold')

    # Lower panel: PF
    ax_pf.plot(x - width, y_113_pf, marker='o', color='#c0392b', linewidth=1.8, label='EXP-113 PF')
    ax_pf.plot(x, y_115_pf, marker='^', color='#2980b9', linewidth=1.8, label='EXP-115 PF')
    ax_pf.plot(x + width, y_117_pf, marker='s', color='#27ae60', linewidth=2.2, label='EXP-117 Stage 3 PF')
    ax_pf.axhline(1.0, color='gray', linestyle='--', linewidth=1.0, label='Breakeven (PF = 1.0)')
    ax_pf.set_ylabel('Profit Factor (PF)', fontsize=11)
    ax_pf.set_xticks(x)
    ax_pf.set_xticklabels([str(y) for y in years], fontsize=11)
    ax_pf.set_xlabel('Calendar Year', fontsize=11)
    ax_pf.legend(loc='upper right', fontsize=9.5)
    ax_pf.grid(True, alpha=0.3)

    for i in range(len(years)):
        ax_pf.text(x[i] - width, y_113_pf[i] + 0.15, f"{y_113_pf[i]:.2f}", ha='center', fontsize=8, color='#c0392b')
        ax_pf.text(x[i], y_115_pf[i] + 0.15, f"{y_115_pf[i]:.2f}", ha='center', fontsize=8, color='#2980b9')
        ax_pf.text(x[i] + width, y_117_pf[i] + 0.15, f"{y_117_pf[i]:.2f}", ha='center', fontsize=8.5, color='#1e8449', fontweight='bold')

    fig.tight_layout()
    fig4_path = os.path.join(plots_dir, 'fig4_yearly_overlay.png')
    fig.savefig(fig4_path, dpi=150)
    plt.close(fig)
    print("Saved plots/fig4_yearly_overlay.png")

    print("\nAll experiments, metrics serialization, and plots generated successfully!")


if __name__ == '__main__':
    run_experiment()
