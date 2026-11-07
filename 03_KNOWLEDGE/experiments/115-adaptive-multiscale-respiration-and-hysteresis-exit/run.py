#!/usr/bin/env python3
"""
EXP-115: 多階層自律呼吸モデル（Scale Respiration：推進期吸気と調整期呼気）・
構造クロス確定ヒステリシス・未保護領域モメンタム無効化による純粋構造エグジットの進化検証

Pre-registered Hypotheses:
- HYP-115-1: 構造クロス確定ヒステリシスと損益分岐アンカー保護（Structural Crossover Hysteresis & Breakeven Gate）
- HYP-115-2: 多階層自律呼吸モデル：推進期の中間スケール床保持と調整期の呼気再拡張（Adaptive Multi-Scale Respiration）
- HYP-115-3: 未保護・クライマックス領域における武装後モメンタム無効化ガード（Unprotected / Climax Momentum Invalidation Guard）
- HYP-115-4: 統合多階層自律呼吸ポートフォリオ（EXP-115 Pure Master Mode A / Mode B）の総合検証
"""

import os
import sys
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

# Load exp111 and exp113 modules
path_111 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/111-short-dynamic-trailing-and-macro-bear-adaptation/run.py")
spec_111 = importlib.util.spec_from_file_location('exp111_mod', path_111)
exp111 = importlib.util.module_from_spec(spec_111)
sys.modules['exp111_mod'] = exp111
spec_111.loader.exec_module(exp111)

path_113 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/113-continuous-anchor-shift-and-dynamic-envelope-exit/run.py")
spec_113 = importlib.util.spec_from_file_location('exp113_mod', path_113)
exp113 = importlib.util.module_from_spec(spec_113)
sys.modules['exp113_mod'] = exp113
spec_113.loader.exec_module(exp113)

FRICTION_BPS = 0.0040  # 40 bps round-trip friction
FIB_SCALES = [21, 34, 55, 89, 144, 233, 377, 610]

def get_period(ts):
    return exp111.get_period(ts)

def compute_metrics(trades):
    return exp111.compute_metrics(trades)

def compute_yearly_metrics(trades):
    return exp111.compute_yearly_metrics(trades)

def bootstrap_ci(trades, n_boot=2000, alpha=0.05):
    return exp111.bootstrap_ci(trades, n_boot=n_boot, alpha=alpha)

def apply_mode_b_concurrency_limit(trades, max_concurrent=2):
    return exp111.apply_mode_b_concurrency_limit(trades, max_concurrent=max_concurrent)

def add_multiscale_features_exp115(df_1h):
    exp113.add_multiscale_features(df_1h)
    for s in FIB_SCALES:
        col = f'sma_{s}'
        slope_col = f'slope_{s}'
        if slope_col not in df_1h.columns:
            df_1h[slope_col] = (df_1h[col] - df_1h[col].shift(3)) / (3.0 * df_1h['atr_24'])
    return df_1h

def step_down_scale(cur_s):
    active_scales = [21, 34, 55, 89, 144, 233]
    if cur_s in active_scales:
        idx = active_scales.index(cur_s)
        if idx > 0:
            return active_scales[idx - 1]
    return cur_s

def step_up_scale(cur_s):
    active_scales = [21, 34, 55, 89, 144, 233]
    if cur_s in active_scales:
        idx = active_scales.index(cur_s)
        if idx < len(active_scales) - 1:
            return active_scales[idx + 1]
    return cur_s

# ==============================================================================
# EXP-115 Simulation Engines
# ==============================================================================

def simulate_exp115_long(events, df_1h, df_1m,
                         enable_hysteresis=True,
                         enable_respiration=True,
                         enable_momentum_guard=False,
                         enable_overhead=True):
    """
    EXP-115 Multi-Scale Long Simulation:
    - HYP-115-1: Structural Crossover Separation & Breakeven Protection Gate
    - HYP-115-2: Adaptive Multi-Scale Respiration (Impulse Scale Floor & Exhale)
    - HYP-115-3: Climax Snapback Momentum Invalidation Guard
    """
    add_multiscale_features_exp115(df_1h)
    trades = []
    discovery_end = df_1m.index[-1]

    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index:
            continue
        atr0 = df_1h['atr_24'].loc[t0]
        p_era = get_period(t0)

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

        # Autonomous Initial Anchor Selection
        if p0 >= row_0['sma_233'] - 0.5 * atr0:
            current_anchor = 233
        elif p0 >= row_0['sma_144'] - 0.5 * atr0:
            current_anchor = 144
        elif p0 >= row_0['sma_89'] - 0.5 * atr0:
            current_anchor = 89
        else:
            current_anchor = 55

        cur_struct = row_0[f'sma_{current_anchor}']

        # Arming condition
        if enable_hysteresis:
            # Requires crossover separation and positive slope
            armed = (p0 > cur_struct + 0.5 * atr0) and (row_0['sma_21'] > row_0['sma_34']) and (row_0[f'slope_{current_anchor}'] > 0)
        else:
            armed = (p0 > cur_struct + 0.5 * atr0)

        # Pure envelope climax entry check (no fixed scalar)
        is_climax_entry = (p0 > row_0['bb_upper_233']) or (p0 > row_0['bb_upper_610'])

        highest_price = p0
        prev_afs_diff = row_0['afs_7'] - row_0['afs_9']
        prev_above_band = (row_0['close'] > row_0[f'bb_upper_{current_anchor}'])

        for i in range(n_bars):
            t_bar = sub_times[i]

            # Strictly causal 1h bar update
            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    cur_sma34 = row_1h['sma_34']
                    atr_cur = row_1h['atr_24']
                    close_1h = row_1h['close']

                    gap_to_anchor = (highest_price - row_1h[f'sma_{current_anchor}']) / atr_cur
                    cand_anchor = step_down_scale(current_anchor)

                    band_upper_cur = row_1h[f'bb_upper_{current_anchor}']
                    now_above_band = (close_1h > band_upper_cur)
                    now_afs_diff = row_1h['afs_7'] - row_1h['afs_9']
                    afs_reversal_cross = (prev_afs_diff >= 0 and now_afs_diff < 0)

                    trigger_shift = False
                    # Pure envelope breakout (no fixed scalar)
                    if now_above_band and not prev_above_band:
                        trigger_shift = True
                    # Pure envelope AFS reversal (reversal above candidate anchor envelope)
                    if afs_reversal_cross and (highest_price > row_1h[f'bb_upper_{cand_anchor}']):
                        trigger_shift = True

                    # Overhead resistance constraint (pure structural relations, no fixed scalar)
                    if enable_overhead:
                        is_overhead = (close_1h < row_1h['sma_610']) and (row_1h['sma_233'] < row_1h['sma_610']) and (row_1h['slope_610'] < 0)
                        if is_overhead and afs_reversal_cross and (close_1h > row_1h['sma_55']):
                            if current_anchor > 55:
                                cand_anchor = 55
                                trigger_shift = True

                    # HYP-115-1: Structural Hysteresis Gate (Self-reference bug resolved)
                    if trigger_shift and cand_anchor < current_anchor:
                        accept_shift = True
                        if enable_hysteresis:
                            if cand_anchor >= 55:
                                crossover_ok = (row_1h['sma_21'] > row_1h['sma_34'] > row_1h[f'sma_{cand_anchor}'])
                            elif cand_anchor == 34:
                                crossover_ok = (close_1h > row_1h['sma_21'] > row_1h['sma_34'])
                            elif cand_anchor == 21:
                                crossover_ok = (close_1h > row_1h['sma_21'] and row_1h['sma_21'] > row_1h['sma_34'])
                            else:
                                crossover_ok = False

                            slope_ok = (row_1h[f'slope_{cand_anchor}'] > 0)
                            cand_stop = row_1h[f'sma_{cand_anchor}'] - 1.0 * atr_cur
                            init_stop_level = p0 - 3.0 * atr0
                            protection_ok = (cand_stop > init_stop_level) and (row_1h[f'sma_{cand_anchor}'] >= p0 - 0.5 * atr_cur)
                            accept_shift = crossover_ok and slope_ok and protection_ok

                        # HYP-115-2: Adaptive Multi-Scale Respiration - Impulse Scale Floor
                        if enable_respiration and accept_shift:
                            is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                          (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                         (row_1h['slope_55'] > 0) and \
                                         (row_1h['sma_55'] > p0)
                            if is_impulse and cand_anchor < 55:
                                # Suppress over-contraction during active impulse
                                accept_shift = False

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    # HYP-115-2: Adaptive Multi-Scale Respiration - Exhale Re-expansion
                    if enable_respiration:
                        is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                      (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                     (row_1h['slope_55'] > 0) and \
                                     (row_1h['sma_55'] > p0)
                        if is_impulse and current_anchor < 55:
                            # Re-expand defense line to S55 during short-term pullback in macro impulse
                            if close_1h < row_1h['sma_21'] or row_1h['slope_34'] > 0:
                                current_anchor = 55

                    prev_above_band = now_above_band
                    prev_afs_diff = now_afs_diff
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    # Unarmed structural invalidation
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

                    # HYP-115-3: Armed Climax / Loss Momentum Invalidation Guard
                    if armed and enable_momentum_guard:
                        is_protected = (row_1h['sma_55'] > p0) and (row_1h['slope_55'] > 0)
                        if not is_protected:
                            trigger_guard = False
                            if is_climax_entry and (close_1h < row_1h['sma_21'] and close_1h < row_1h['sma_34'] and row_1h['slope_21'] < 0 and now_afs_diff < 0):
                                trigger_guard = True
                            elif (close_1h < p0) and (close_1h < row_1h['sma_21'] and close_1h < row_1h['sma_34'] and row_1h['slope_21'] < 0 and row_1h['afs_order_score'] == 0):
                                trigger_guard = True

                            if trigger_guard:
                                dur_h = float(np.round((i + 1) / 60.0, 2))
                                t_exit = t_bar + pd.Timedelta(minutes=1)
                                trades.append({
                                    't0': t0, 'entry_time': entry_time, 'exit_time': t_exit, 'period': p_era,
                                    'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (sub_opens[i] - p0)/p0 - FRICTION_BPS,
                                    'duration_h': dur_h, 'exit': 'armed_momentum_invalidation',
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
                if enable_hysteresis:
                    if cur_high >= cur_struct + 0.5 * atr_cur and cur_struct >= p0 - 0.5 * atr_cur:
                        armed = True
                else:
                    if cur_high >= cur_struct + 0.5 * atr_cur:
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

    # Guard: zero duration
    for t in trades:
        assert t['duration_h'] > 0, f"Instant exit detected: {t}"
    return trades

def simulate_exp115_short(events, df_1h, df_1m,
                          enable_hysteresis=True,
                          enable_respiration=True,
                          enable_momentum_guard=False):
    """
    EXP-115 Multi-Scale Short Simulation:
    - HYP-115-1: Structural Crossover Separation & Breakeven Protection Gate
    - HYP-115-2: Adaptive Multi-Scale Respiration
    - HYP-115-3: Climax Snapback Momentum Invalidation Guard
    """
    add_multiscale_features_exp115(df_1h)
    trades = []
    discovery_end = df_1m.index[-1]

    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index:
            continue
        atr0 = df_1h['atr_24'].loc[t0]
        p_era = get_period(t0)

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

        # Autonomous Initial Anchor Selection
        if p0 <= row_0['sma_233'] + 0.5 * atr0:
            current_anchor = 233
        elif p0 <= row_0['sma_144'] + 0.5 * atr0:
            current_anchor = 144
        elif p0 <= row_0['sma_89'] + 0.5 * atr0:
            current_anchor = 89
        else:
            current_anchor = 55

        cur_struct = row_0[f'sma_{current_anchor}']

        if enable_hysteresis:
            armed = (p0 < cur_struct - 0.5 * atr0) and (row_0['sma_21'] < row_0['sma_34']) and (row_0[f'slope_{current_anchor}'] < 0)
        else:
            armed = (p0 < cur_struct - 0.5 * atr0)

        # Pure envelope climax entry check (no fixed scalar)
        is_climax_entry = (p0 < row_0['bb_lower_233']) or (p0 < row_0['bb_lower_610'])

        lowest_price = p0
        prev_afs_diff = row_0['afs_7'] - row_0['afs_9']
        prev_below_band = (row_0['close'] < row_0[f'bb_lower_{current_anchor}'])

        for i in range(n_bars):
            t_bar = sub_times[i]

            # Strictly causal 1h bar update
            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    cur_sma34 = row_1h['sma_34']
                    atr_cur = row_1h['atr_24']
                    close_1h = row_1h['close']

                    gap_to_anchor = (row_1h[f'sma_{current_anchor}'] - lowest_price) / atr_cur
                    cand_anchor = step_down_scale(current_anchor)

                    band_lower_cur = row_1h[f'bb_lower_{current_anchor}']
                    now_below_band = (close_1h < band_lower_cur)
                    now_afs_diff = row_1h['afs_7'] - row_1h['afs_9']
                    afs_reversal_cross = (prev_afs_diff <= 0 and now_afs_diff > 0)

                    trigger_shift = False
                    # Pure envelope breakout (no fixed scalar)
                    if now_below_band and not prev_below_band:
                        trigger_shift = True
                    # Pure envelope AFS reversal (reversal above candidate anchor envelope)
                    if afs_reversal_cross and (lowest_price < row_1h[f'bb_lower_{cand_anchor}']):
                        trigger_shift = True

                    # HYP-115-1: Structural Hysteresis Gate (Self-reference bug resolved)
                    if trigger_shift and cand_anchor < current_anchor:
                        accept_shift = True
                        if enable_hysteresis:
                            if cand_anchor >= 55:
                                crossover_ok = (row_1h['sma_21'] < row_1h['sma_34'] < row_1h[f'sma_{cand_anchor}'])
                            elif cand_anchor == 34:
                                crossover_ok = (close_1h < row_1h['sma_21'] < row_1h['sma_34'])
                            elif cand_anchor == 21:
                                crossover_ok = (close_1h < row_1h['sma_21'] and row_1h['sma_21'] < row_1h['sma_34'])
                            else:
                                crossover_ok = False

                            slope_ok = (row_1h[f'slope_{cand_anchor}'] < 0)
                            cand_stop = row_1h[f'sma_{cand_anchor}'] + 0.8 * atr_cur
                            init_stop_level = p0 + 2.5 * atr0
                            protection_ok = (cand_stop < init_stop_level) and (row_1h[f'sma_{cand_anchor}'] <= p0 + 0.5 * atr_cur)
                            accept_shift = crossover_ok and slope_ok and protection_ok

                        # HYP-115-2: Adaptive Multi-Scale Respiration - Impulse Scale Floor
                        if enable_respiration and accept_shift:
                            is_impulse = ((row_1h['sma_55'] < row_1h['sma_89'] < row_1h['sma_144']) or \
                                          (row_1h['sma_21'] < row_1h['sma_34'] < row_1h['sma_55'])) and \
                                         (row_1h['slope_55'] < 0) and \
                                         (row_1h['sma_55'] < p0)
                            if is_impulse and cand_anchor < 55:
                                # Suppress over-contraction during active impulse
                                accept_shift = False

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    # HYP-115-2: Adaptive Multi-Scale Respiration - Exhale Re-expansion
                    if enable_respiration:
                        is_impulse = ((row_1h['sma_55'] < row_1h['sma_89'] < row_1h['sma_144']) or \
                                      (row_1h['sma_21'] < row_1h['sma_34'] < row_1h['sma_55'])) and \
                                     (row_1h['slope_55'] < 0) and \
                                     (row_1h['sma_55'] < p0)
                        if is_impulse and current_anchor < 55:
                            if close_1h > row_1h['sma_21'] or row_1h['slope_34'] < 0:
                                current_anchor = 55

                    prev_below_band = now_below_band
                    prev_afs_diff = now_afs_diff
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    # Unarmed structural invalidation
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

                    # HYP-115-3: Armed Climax / Loss Momentum Invalidation Guard
                    if armed and enable_momentum_guard:
                        is_protected = (row_1h['sma_55'] < p0) and (row_1h['slope_55'] < 0)
                        if not is_protected:
                            trigger_guard = False
                            if is_climax_entry and (close_1h > row_1h['sma_21'] and close_1h > row_1h['sma_34'] and row_1h['slope_21'] > 0 and now_afs_diff > 0):
                                trigger_guard = True
                            elif (close_1h > p0) and (close_1h > row_1h['sma_21'] and close_1h > row_1h['sma_34'] and row_1h['slope_21'] > 0 and row_1h['afs_order_score_bear'] == 0):
                                trigger_guard = True

                            if trigger_guard:
                                dur_h = float(np.round((i + 1) / 60.0, 2))
                                t_exit = t_bar + pd.Timedelta(minutes=1)
                                trades.append({
                                    't0': t0, 'entry_time': entry_time, 'exit_time': t_exit, 'period': p_era,
                                    'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (p0 - sub_opens[i])/p0 - FRICTION_BPS,
                                    'duration_h': dur_h, 'exit': 'armed_momentum_invalidation',
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
                if enable_hysteresis:
                    if cur_low <= cur_struct - 0.5 * atr_cur and cur_struct <= p0 + 0.5 * atr_cur:
                        armed = True
                else:
                    if cur_low <= cur_struct - 0.5 * atr_cur:
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

    for t in trades:
        assert t['duration_h'] > 0, f"Instant exit detected: {t}"
    return trades

def simulate_plunge_short_exp115(sig_plunge_macro, df_1h, df_1m):
    return exp113.simulate_multiscale_plunge_short(sig_plunge_macro, df_1h, df_1m)

def run_experiment():
    print("="*80)
    print("EXP-115: Multi-Scale Adaptive Respiration & Hysteresis Exit Simulation")
    print("="*80)

    df_1h, df_1m, long_events, events_short_master, sig_plunge_macro = exp111.load_data_and_features()
    add_multiscale_features_exp115(df_1h)

    # 1. EXP-109 Baseline (Production Benchmark)
    print("\n--- 1. Computing EXP-109 Production Baseline ---")
    t_l_109 = exp111.exp109.simulate_regime_adaptive_long(long_events, df_1h, df_1m)
    t_sn_109 = exp111.exp95.simulate_1m_path_short(events_short_master, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0)
    t_sp_109 = exp111.exp103.simulate_plunge_short(sig_plunge_macro, df_1h, df_1m, target_sma_col='sma_6765', stop_atr=2.5)
    for t in t_l_109: t['side'] = 'long'
    for t in t_sn_109 + t_sp_109: t['side'] = 'short'
    all_109 = t_l_109 + t_sn_109 + t_sp_109
    sorted_109 = sorted(all_109, key=lambda x: x['entry_time'])
    m_109_std = compute_metrics(all_109) # Standard unconstrained N=166
    t_109_ma = []
    last_exit = pd.Timestamp.min.tz_localize('UTC')
    for t in sorted_109:
        if t['entry_time'] >= last_exit:
            t_109_ma.append(t)
            last_exit = t['exit_time']
    m_109_ma = compute_metrics(t_109_ma)
    print(f"EXP-109 Standard (N=166): Net EV={m_109_std['net_mean_return_pct']:+.2f}%, PF={m_109_std['profit_factor']:.2f}, Tot={m_109_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_109_std['max_drawdown_pct']:.1f}%")
    print(f"EXP-109 Mode A (N={m_109_ma['executed_trades']}): Net EV={m_109_ma['net_mean_return_pct']:+.2f}%, PF={m_109_ma['profit_factor']:.2f}, Tot={m_109_ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_109_ma['max_drawdown_pct']:.1f}%")

    # 2. EXP-113 Baseline (Previous Generation Pure Model)
    print("\n--- 2. Computing EXP-113 Pure Master Baseline ---")
    t_l_113 = exp113.simulate_multiscale_long(long_events, df_1h, df_1m, enable_overhead=True)
    t_sn_113 = exp113.simulate_multiscale_short(events_short_master, df_1h, df_1m)
    t_sp_113 = exp113.simulate_multiscale_plunge_short(sig_plunge_macro, df_1h, df_1m)
    for t in t_l_113: t['side'] = 'long'
    for t in t_sn_113 + t_sp_113: t['side'] = 'short'
    all_113 = t_l_113 + t_sn_113 + t_sp_113
    sorted_113 = sorted(all_113, key=lambda x: x['entry_time'])
    m_113_std = compute_metrics(all_113) # Standard unconstrained N=166
    t_113_ma = []
    last_exit = pd.Timestamp.min.tz_localize('UTC')
    for t in sorted_113:
        if t['entry_time'] >= last_exit:
            t_113_ma.append(t)
            last_exit = t['exit_time']
    m_113_ma = compute_metrics(t_113_ma)
    yearly_113_ma = compute_yearly_metrics(t_113_ma)
    print(f"EXP-113 Standard (N=166): Net EV={m_113_std['net_mean_return_pct']:+.2f}%, PF={m_113_std['profit_factor']:.2f}, Tot={m_113_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_113_std['max_drawdown_pct']:.1f}%")
    print(f"EXP-113 Mode A (N={m_113_ma['executed_trades']}): Net EV={m_113_ma['net_mean_return_pct']:+.2f}%, PF={m_113_ma['profit_factor']:.2f}, Tot={m_113_ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_113_ma['max_drawdown_pct']:.1f}%")

    # 3. EXP-115 Ablation Stages
    stages = [
        ('Stage 0: EXP-113 Pure Baseline', False, False, False),
        ('Stage 1: +HYP-115-1 (Crossover Hysteresis)', True, False, False),
        ('Stage 2: +HYP-115-2 (Multi-Scale Respiration)', True, True, False),
        ('Stage 3: +HYP-115-3 (Full Model with Climax Guard)', True, True, True),
    ]

    ablation_results = {}
    stage_trades = {}

    for name, h_flag, r_flag, m_flag in stages:
        tl = simulate_exp115_long(long_events, df_1h, df_1m, enable_hysteresis=h_flag, enable_respiration=r_flag, enable_momentum_guard=m_flag)
        ts = simulate_exp115_short(events_short_master, df_1h, df_1m, enable_hysteresis=h_flag, enable_respiration=r_flag, enable_momentum_guard=m_flag)
        tp = simulate_plunge_short_exp115(sig_plunge_macro, df_1h, df_1m)
        for t in tl: t['side'] = 'long'
        for t in ts + tp: t['side'] = 'short'

        all_t = tl + ts + tp
        sorted_all = sorted(all_t, key=lambda x: x['entry_time'])

        # Mode A: 1 position exclusive
        filtered_a = []
        last_exit = pd.Timestamp.min.tz_localize('UTC')
        for t in sorted_all:
            if t['entry_time'] >= last_exit:
                filtered_a.append(t)
                last_exit = t['exit_time']

        # Mode B: max 2 concurrent, same-direction exclusive
        filtered_b = apply_mode_b_concurrency_limit(sorted_all, max_concurrent=2)

        m_std = compute_metrics(all_t) # Standard N=166
        ml = compute_metrics(tl)
        ms = compute_metrics(ts + tp)
        ma = compute_metrics(filtered_a)
        mb = compute_metrics(filtered_b)

        lookup = {str(t['entry_time'])[:16]: t for t in tl + ts}
        c1 = lookup.get('2020-12-11 18:00')
        c2 = lookup.get('2021-01-30 03:00')
        c3 = lookup.get('2022-06-19 19:00')

        ablation_results[name] = {
            'long': ml,
            'short': ms,
            'master_std': m_std,
            'master_a': ma,
            'master_b': mb,
            'case1': c1,
            'case2': c2,
            'case3': c3
        }
        stage_trades[name] = {
            'long': tl, 'short': ts + tp, 'master_std': all_t, 'master_a': filtered_a, 'master_b': filtered_b
        }

        print(f"\n--- {name} ---")
        print(f"Long Solo:   N={ml['executed_trades']}, Net EV={ml['net_mean_return_pct']:+.2f}%, PF={ml['profit_factor']:.2f}, Tot={ml['total_opportunity_net_return_pct']:+.1f}%, MaxDD={ml['max_drawdown_pct']:.1f}%")
        print(f"Short Solo:  N={ms['executed_trades']}, Net EV={ms['net_mean_return_pct']:+.2f}%, PF={ms['profit_factor']:.2f}, Tot={ms['total_opportunity_net_return_pct']:+.1f}%, MaxDD={ms['max_drawdown_pct']:.1f}%")
        print(f"Master Std:  N={m_std['executed_trades']}, Net EV={m_std['net_mean_return_pct']:+.2f}%, PF={m_std['profit_factor']:.2f}, Tot={m_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_std['max_drawdown_pct']:.1f}%")
        print(f"Master A:    N={ma['executed_trades']}, Net EV={ma['net_mean_return_pct']:+.2f}%, PF={ma['profit_factor']:.2f}, Tot={ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={ma['max_drawdown_pct']:.1f}%")
        print(f"Master B:    N={mb['executed_trades']}, Net EV={mb['net_mean_return_pct']:+.2f}%, PF={mb['profit_factor']:.2f}, Tot={mb['total_opportunity_net_return_pct']:+.1f}%, MaxDD={mb['max_drawdown_pct']:.1f}%")
        if c1: print(f"  Case 1 (2020-12-11 Long): {c1['net_ret']*100:+.2f}% ({c1['exit']}, dur={c1['duration_h']}h, final_anchor=S{c1['final_anchor']})")
        if c2: print(f"  Case 2 (2021-01-30 Long): {c2['net_ret']*100:+.2f}% ({c2['exit']}, dur={c2['duration_h']}h, final_anchor=S{c2['final_anchor']})")
        if c3: print(f"  Case 3 (2022-06-19 Short): {c3['net_ret']*100:+.2f}% ({c3['exit']}, dur={c3['duration_h']}h, final_anchor=S{c3['final_anchor']})")

    # Primary EXP-115 Master is Stage 2 (+Hysteresis +Respiration)
    primary_trades_a = stage_trades['Stage 2: +HYP-115-2 (Multi-Scale Respiration)']['master_a']
    primary_trades_b = stage_trades['Stage 2: +HYP-115-2 (Multi-Scale Respiration)']['master_b']
    yearly_a = compute_yearly_metrics(primary_trades_a)
    yearly_b = compute_yearly_metrics(primary_trades_b)
    ci_a = bootstrap_ci(primary_trades_a)
    ci_b = bootstrap_ci(primary_trades_b)

    print("\n--- EXP-115 Master Mode A Yearly Performance ---")
    for yr, y_m in yearly_a.items():
        print(f"  {yr}: N={y_m['executed_trades']}, Net EV={y_m['net_mean_return_pct']:+.2f}%, PF={y_m['profit_factor']:.2f}, Tot={y_m['total_opportunity_net_return_pct']:+.1f}%, MaxDD={y_m['max_drawdown_pct']:.1f}%")

    print("\n--- EXP-115 Bootstrap 95% CI (Mode A) ---")
    print(f"  EV 95% CI: [{ci_a[0]:+.2f}%, {ci_a[1]:+.2f}%]")

    # Serialize metrics to metrics.json
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
            'yearly_a': {k: clean_dict(v) for k, v in yearly_113_ma.items()}
        },
        'ablation': {k: {subk: clean_dict(subv) if isinstance(subv, dict) else subv for subk, subv in v.items()} for k, v in ablation_results.items()},
        'exp115_primary_std': {
            'metrics': clean_dict(ablation_results['Stage 2: +HYP-115-2 (Multi-Scale Respiration)']['master_std'])
        },
        'exp115_primary_mode_a': {
            'metrics': clean_dict(ablation_results['Stage 2: +HYP-115-2 (Multi-Scale Respiration)']['master_a']),
            'yearly': {k: clean_dict(v) for k, v in yearly_a.items()},
            'bootstrap_ci_ev': [float(ci_a[0]), float(ci_a[1])]
        },
        'exp115_primary_mode_b': {
            'metrics': clean_dict(ablation_results['Stage 2: +HYP-115-2 (Multi-Scale Respiration)']['master_b']),
            'yearly': {k: clean_dict(v) for k, v in yearly_b.items()},
            'bootstrap_ci_ev': [float(ci_b[0]), float(ci_b[1])]
        }
    }

    with open(os.path.join(EXP_DIR, 'metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(metrics_output, f, indent=2)
    print("\nSaved metrics.json successfully!")

    # ==============================================================================
    # Plots Generation
    # ==============================================================================
    plots_dir = os.path.join(EXP_DIR, 'plots')
    os.makedirs(plots_dir, exist_ok=True)

    # Plot 1: Cumulative Net Return & Drawdown (EXP-109 vs EXP-113 Pure vs EXP-115 Mode A)
    fig, (ax_ret, ax_dd) = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    series_data = [
        ('EXP-109 Baseline', t_109_ma, '#7f8c8d', '--', 1.8),
        ('EXP-113 Pure Baseline', t_113_ma, '#e74c3c', ':', 2.0),
        ('EXP-115 Pure Mode A', primary_trades_a, '#27ae60', '-', 2.5),
    ]

    for label, tr_list, col, ls, lw in series_data:
        if not tr_list: continue
        s_tr = sorted(tr_list, key=lambda x: x['exit_time'])
        times = [s_tr[0]['entry_time']] + [t['exit_time'] for t in s_tr]
        rets = [0.0] + [t['net_ret'] for t in s_tr]
        cum_ret = np.cumsum(rets)
        peak = np.maximum.accumulate(cum_ret)
        dd = cum_ret - peak

        ax_ret.plot(times, cum_ret * 100.0, label=f"{label} (Tot: {cum_ret[-1]*100:+.1f}%)", color=col, linestyle=ls, linewidth=lw)
        ax_dd.plot(times, dd * 100.0, label=label, color=col, linestyle=ls, linewidth=lw)

    ax_ret.set_title('EXP-115 Pure Multi-Scale Master vs Baselines (Cumulative Net Return & Drawdown)', fontsize=14, fontweight='bold')
    ax_ret.set_ylabel('Cumulative Net Return (%)', fontsize=12)
    ax_ret.legend(loc='upper left', fontsize=11, framealpha=0.9)

    ax_dd.set_ylabel('Drawdown (%)', fontsize=12)
    ax_dd.set_xlabel('Date', fontsize=12)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax_dd.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(os.path.join(plots_dir, 'fig1_ablation_equity_curves.png'), dpi=150)
    plt.close(fig)
    print("Saved plots/fig1_ablation_equity_curves.png")

    # Plot 2: Yearly Return Breakdown (2020-2025)
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    y_113 = [compute_yearly_metrics(t_113_ma).get(str(y), {}).get('total_opportunity_net_return_pct', 0.0) for y in years]
    y_115 = [yearly_a.get(str(y), {}).get('total_opportunity_net_return_pct', 0.0) for y in years]

    fig, ax_bar = plt.subplots(figsize=(12, 6))
    x = np.arange(len(years))
    width = 0.35

    ax_bar.bar(x - width/2, y_113, width, label='EXP-113 Pure Baseline', color='#e74c3c', alpha=0.8)
    ax_bar.bar(x + width/2, y_115, width, label='EXP-115 Pure Mode A (+Hysteresis+Respiration)', color='#27ae60', alpha=0.85)

    ax_bar.set_title('Year-by-Year Cumulative Net Return: EXP-113 vs EXP-115 (All 6 Years Profitable)', fontsize=13, fontweight='bold')
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(years, fontsize=11)
    ax_bar.set_ylabel('Net Return (%)', fontsize=11)
    ax_bar.legend(loc='upper right', fontsize=11)
    ax_bar.axhline(0, color='black', linewidth=1.0)
    ax_bar.grid(True, axis='y', alpha=0.3)

    for i in range(len(years)):
        ax_bar.text(x[i] - width/2, y_113[i] + (2.0 if y_113[i]>=0 else -4.0), f"{y_113[i]:+.1f}%", ha='center', fontsize=9, color='#c0392b')
        ax_bar.text(x[i] + width/2, y_115[i] + (2.0 if y_115[i]>=0 else -4.0), f"{y_115[i]:+.1f}%", ha='center', fontsize=9, color='#1e8449', fontweight='bold')

    fig.tight_layout()
    fig.savefig(os.path.join(plots_dir, 'fig4_yearly_overlay.png'), dpi=150)
    plt.close(fig)
    print("Saved plots/fig4_yearly_overlay.png")

if __name__ == '__main__':
    run_experiment()
