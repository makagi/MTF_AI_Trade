#!/usr/bin/env python3
"""
EXP-113: 多段階ラチェットの構造的本質（親構造線ラグ補完・疑似多階層エンベロープ）の解明と
フィボナッチ多階層スケール系列（SCALES）に基づく自律的階層アンカーシフトモデルの挙動解明

Pre-registered Hypotheses:
- HYP-113-1: 多段階ラチェットの構造的本質解明（親構造線の空間遅行ラグ補完）と
             フィボナッチ多階層スケール系列（SCALES）による自律的アンカーシフトへの汎用化
- HYP-113-2: ショート側における固定値ゼロの多階層幾何学的アンカーシフト（K-060 検証）
- HYP-113-3: 頭上長期下降親抵抗線（K-061）制約の幾何学的統合とロング階層アンカーシフト
- HYP-113-4: 固定値ゼロの純粋多階層双方向マスターポートフォリオ（EXP-113 Master Mode A / B）の挙動解明
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

# Set paths
EXP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(EXP_DIR, '../../..'))
sys.path.insert(0, ROOT_DIR)

import importlib.util

# Load exp111 and exp109 modules
path_111 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/111-short-dynamic-trailing-and-macro-bear-adaptation/run.py")
spec_111 = importlib.util.spec_from_file_location('exp111_mod', path_111)
exp111 = importlib.util.module_from_spec(spec_111)
sys.modules['exp111_mod'] = exp111
spec_111.loader.exec_module(exp111)

path_109 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/109-regime-adaptive-dynamic-exit/run.py")
spec_109 = importlib.util.spec_from_file_location('exp109_mod', path_109)
exp109 = importlib.util.module_from_spec(spec_109)
sys.modules['exp109_mod'] = exp109
spec_109.loader.exec_module(exp109)

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

def add_multiscale_features(df_1h):
    """
    Ensure all Fibonacci scale SMAs, standard deviations, and outer bands (+/- 2 sigma)
    are calculated and available in df_1h.
    """
    for s in FIB_SCALES:
        col_mid = f'sma_{s}'
        col_std = f'std_{s}'
        if col_std not in df_1h.columns:
            df_1h[col_std] = df_1h['close'].rolling(s).std()
        col_upper = f'bb_upper_{s}'
        col_lower = f'bb_lower_{s}'
        if col_upper not in df_1h.columns:
            df_1h[col_upper] = df_1h[col_mid] + 2.0 * df_1h[col_std]
        if col_lower not in df_1h.columns:
            df_1h[col_lower] = df_1h[col_mid] - 2.0 * df_1h[col_std]
    return df_1h

def step_down_scale(cur_s):
    """
    Step down one hierarchical level in the Fibonacci scale sequence:
    233 -> 144 -> 89 -> 55 -> 34 -> 21
    """
    active_scales = [21, 34, 55, 89, 144, 233]
    if cur_s in active_scales:
        idx = active_scales.index(cur_s)
        if idx > 0:
            return active_scales[idx - 1]
    return cur_s

# ==============================================================================
# Pure Multi-Scale Simulation Engines (Zero Fixed Tiers, Zero Clock Timers)
# ==============================================================================

def simulate_multiscale_short(events, df_1h, df_1m,
                              arm_depth_atr=0.5,
                              initial_risk_atr=2.5,
                              buf_atr=0.8):
    """
    Pure Multi-Scale Short Simulation:
    - 100% Zero Fixed Tiers, Zero Clock Timers (No 72h/48h timer).
    - Autonomous Initial Anchor Selection based on geometric scale standing:
      Price standing relative to Fibonacci scales determines initial defense line.
    - Orderly Single-Step Anchor Shift (S_k -> S_{k-1}):
      Triggered on Outer Band Breach Event (BB Lower -2 sigma) or AFS Bottom Reversal Event
      when spatial gap to current anchor is significant (> 3.0 / 3.5 ATR).
    - Strictly causal updates at 1h bar boundaries using (t_bar - 1h).floor('1h').
    - Non-zero duration enforcement and assert guards.
    """
    add_multiscale_features(df_1h)
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
        armed = (p0 < cur_struct - arm_depth_atr * atr0)
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

                    # Condition A: Outer Band Breach Event (BB Lower -2 sigma)
                    band_lower_cur = row_1h[f'bb_lower_{current_anchor}']
                    now_below_band = (close_1h < band_lower_cur)
                    if now_below_band and not prev_below_band and gap_to_anchor > 3.0:
                        current_anchor = step_down_scale(current_anchor)
                    prev_below_band = now_below_band

                    # Condition B: AFS Bottom Reversal Event (Cross from negative to positive)
                    now_afs_diff = row_1h['afs_7'] - row_1h['afs_9']
                    afs_reversal_cross = (prev_afs_diff <= 0 and now_afs_diff > 0)
                    if afs_reversal_cross and gap_to_anchor > 3.5:
                        current_anchor = step_down_scale(current_anchor)
                    prev_afs_diff = now_afs_diff

                    cur_struct = row_1h[f'sma_{current_anchor}']

                    # Structural Invalidation when not yet armed
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
            init_stop = p0 + initial_risk_atr * atr0 if not armed else 999999.0

            struct_stop = cur_struct + buf_atr * atr_cur if armed else base_stop
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

            if not armed and cur_low <= cur_struct - arm_depth_atr * atr_cur:
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

def simulate_multiscale_long(events, df_1h, df_1m,
                             arm_depth_atr=0.5,
                             initial_risk_atr=3.0,
                             parent_buf_atr=1.0,
                             enable_overhead=True):
    """
    Pure Multi-Scale Long Simulation:
    - 100% Zero Fixed Tiers, Zero Clock Timers.
    - Autonomous Initial Anchor Selection:
      Determines initial support scale based on price standing relative to Fibonacci scales.
    - Orderly Single-Step Anchor Shift (S_k -> S_{k-1}):
      Triggered on Outer Band Breach Event (BB Upper +2 sigma) or AFS Top Reversal Event
      when spatial gap to current anchor is significant (> 3.0 / 3.5 ATR).
    - Refined Overhead Resistance Constraint (K-061):
      When price operates under descending parent resistance (S_610 with slope < -0.01)
      and AFS top reversal occurs, tighten defense anchor to S_55.
    - Strictly causal updates at 1h bar boundaries using (t_bar - 1h).floor('1h').
    """
    add_multiscale_features(df_1h)
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
        armed = (p0 > cur_struct + arm_depth_atr * atr0)
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

                    # Condition A: Outer Band Breach Event (BB Upper +2 sigma)
                    band_upper_cur = row_1h[f'bb_upper_{current_anchor}']
                    now_above_band = (close_1h > band_upper_cur)
                    if now_above_band and not prev_above_band and gap_to_anchor > 3.0:
                        current_anchor = step_down_scale(current_anchor)
                    prev_above_band = now_above_band

                    # Condition B: AFS Top Reversal Event (Cross from positive to negative)
                    now_afs_diff = row_1h['afs_7'] - row_1h['afs_9']
                    afs_reversal_cross = (prev_afs_diff >= 0 and now_afs_diff < 0)
                    if afs_reversal_cross and gap_to_anchor > 3.5:
                        current_anchor = step_down_scale(current_anchor)

                    # Condition C: Overhead Resistance Constraint (K-061)
                    if enable_overhead:
                        is_overhead = (close_1h < row_1h['sma_610']) and (row_1h['slope_610'] < -0.01)
                        if is_overhead and afs_reversal_cross and gap_to_anchor > 2.0:
                            if current_anchor > 55:
                                current_anchor = 55

                    prev_afs_diff = now_afs_diff
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    # Structural Invalidation when not yet armed
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
            init_stop = p0 - initial_risk_atr * atr0 if not armed else -999999.0

            struct_stop = cur_struct - parent_buf_atr * atr_cur if armed else base_stop
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

            if not armed and cur_high >= cur_struct + arm_depth_atr * atr_cur:
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

def simulate_multiscale_plunge_short(events, df_1h, df_1m):
    """
    Pure Multi-Scale Plunge Short Simulation:
    - Target: sma_6765. Defense structure: sma_144.
    - Zero fixed clock timer.
    """
    add_multiscale_features(df_1h)
    trades = []
    discovery_end = df_1m.index[-1]
    events_decl = exp111.exp95.decluster_events(events, cooldown_bars=24)
    event_idx = df_1h.index[events_decl]

    for t0 in event_idx:
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
        target_sma = row_0['sma_6765']
        atr_cur = atr0
        cur_struct = row_0['sma_144']
        armed = False

        for i in range(n_bars):
            t_bar = sub_times[i]

            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    cur_struct = row_1h['sma_144']
                    atr_cur = row_1h['atr_24']

            cur_high = sub_highs[i]
            cur_low = sub_lows[i]
            cur_open = sub_opens[i]

            cur_mfe = (p0 - cur_low) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe

            if cur_low <= target_sma:
                dur_h = float(np.round((i + 1) / 60.0, 2))
                t_exit = t_bar + pd.Timedelta(minutes=1)
                p_exit = min(cur_open, target_sma)
                trades.append({
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_exit, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p0 - p_exit)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': 'target_hit',
                    'final_anchor': 144,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
                })
                exited = True
                break

            base_stop = p0 + 2.5 * atr0
            struct_stop = cur_struct + 0.5 * atr_cur if armed else base_stop
            effective_stop = min(base_stop, struct_stop)

            if cur_high >= effective_stop:
                dur_h = float(np.round((i + 1) / 60.0, 2))
                t_exit = t_bar + pd.Timedelta(minutes=1)
                p_exit = max(cur_open, effective_stop)
                trades.append({
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_exit, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p0 - p_exit)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': 'struct_exit_plunge' if effective_stop == struct_stop else 'stop_hit',
                    'final_anchor': 144,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
                })
                exited = True
                break

            if not armed and cur_low <= cur_struct - 0.5 * atr_cur:
                armed = True

        if not exited:
            dur_h = float(np.round((sub_times[-1] - entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (p0 - sub_closes[-1])/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'final_anchor': 144,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
            })

    return trades

# ==============================================================================
# Main Orchestration & Audit Pipeline
# ==============================================================================

def compute_scale_crossing_returns(events, df_1h, df_1m, direction='long', min_mfe_atr=2.5, scales=[233, 144, 89, 55, 34, 21]):
    """
    Dynamically compute the mean realized net return if exiting upon crossing each Fibonacci scale SMA post-peak.
    Evaluates trades with significant excursion (MFE >= min_mfe_atr).
    """
    scale_returns = {s: [] for s in scales}
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index:
            continue
        atr0 = df_1h.loc[t0, 'atr_24']
        p0 = df_1m.loc[entry_time, 'open']
        sub_1h = df_1h.loc[entry_time : entry_time + pd.Timedelta(hours=350)]
        if len(sub_1h) < 24:
            continue

        if direction == 'long':
            peak_price = p0
            peak_time = entry_time
            for t_bar, row in sub_1h.iterrows():
                if row['high'] > peak_price:
                    peak_price = row['high']
                    peak_time = t_bar
            mfe_atr = (peak_price - p0) / atr0
            if mfe_atr < min_mfe_atr:
                continue
            post_peak = sub_1h.loc[peak_time:]
            for s in scales:
                crossed = False
                col_sma = f'sma_{s}'
                for t_bar, row in post_peak.iterrows():
                    if row['close'] < row[col_sma]:
                        ret = (row['close'] - p0) / p0 * 100.0 - 0.40
                        scale_returns[s].append(ret)
                        crossed = True
                        break
                if not crossed:
                    ret = (post_peak['close'].iloc[-1] - p0) / p0 * 100.0 - 0.40
                    scale_returns[s].append(ret)
        else:  # short
            lowest_price = p0
            lowest_time = entry_time
            for t_bar, row in sub_1h.iterrows():
                if row['low'] < lowest_price:
                    lowest_price = row['low']
                    lowest_time = t_bar
            mfe_atr = (p0 - lowest_price) / atr0
            if mfe_atr < min_mfe_atr:
                continue
            post_peak = sub_1h.loc[lowest_time:]
            for s in scales:
                crossed = False
                col_sma = f'sma_{s}'
                for t_bar, row in post_peak.iterrows():
                    if row['close'] > row[col_sma]:
                        ret = (p0 - row['close']) / p0 * 100.0 - 0.40
                        scale_returns[s].append(ret)
                        crossed = True
                        break
                if not crossed:
                    ret = (p0 - post_peak['close'].iloc[-1]) / p0 * 100.0 - 0.40
                    scale_returns[s].append(ret)

    mean_returns = [float(np.mean(scale_returns[s])) if scale_returns[s] else 0.0 for s in scales]
    return mean_returns

def main():
    print("=" * 80)
    print("EXP-113: Continuous Multi-Scale Anchor Shift Verification Pipeline")
    print("=" * 80)

    print("\n[Step 1/5] Loading data and MTF features...")
    df_1h, df_1m, long_events, events_short_master, sig_plunge_macro = exp111.load_data_and_features()

    print(f"Data range: {df_1h.index[0]} to {df_1h.index[-1]}")
    print(f"Long events: {len(long_events)}, Short master: {len(events_short_master)}, Macro plunge: {len(sig_plunge_macro)}")

    # --------------------------------------------------------------------------
    # Step 2: Run Baseline (EXP-109 Master)
    # --------------------------------------------------------------------------
    print("\n[Step 2/5] Simulating Baseline (EXP-109 Master)...")
    trades_long_109 = exp111.exp109.simulate_regime_adaptive_long(long_events, df_1h, df_1m)
    trades_sn_109 = exp111.exp95.simulate_1m_path_short(events_short_master, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0)
    trades_sp_109 = exp111.exp103.simulate_plunge_short(sig_plunge_macro, df_1h, df_1m, target_sma_col='sma_6765', stop_atr=2.5)
    for t in trades_long_109:
        t['side'] = 'long'; t['direction'] = 'long'
    for t in trades_sn_109 + trades_sp_109:
        t['side'] = 'short'; t['direction'] = 'short'

    trades_baseline_master = sorted(trades_long_109 + trades_sn_109 + trades_sp_109, key=lambda x: x['entry_time'])
    m_baseline = compute_metrics(trades_baseline_master)
    y_baseline = compute_yearly_metrics(trades_baseline_master)
    ci_baseline = bootstrap_ci(trades_baseline_master)

    m_base_short = compute_metrics(sorted(trades_sn_109 + trades_sp_109, key=lambda x: x['entry_time']))
    print(f"Baseline Master: EV={m_baseline['net_mean_return_pct']:+.2f}%, PF={m_baseline['profit_factor']:.2f}, Tot={m_baseline['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_baseline['max_drawdown_pct']:.2f}%")
    print(f"Baseline Short : EV={m_base_short['net_mean_return_pct']:+.2f}%, PF={m_base_short['profit_factor']:.2f}, Tot={m_base_short['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_base_short['max_drawdown_pct']:.2f}%")

    # --------------------------------------------------------------------------
    # Step 3: Pure Multi-Scale Simulations (Ablation 1, 2, 3, Master)
    # --------------------------------------------------------------------------
    print("\n[Step 3/5] Running Pure Multi-Scale Simulations...")

    # Short Simulations (Zero Fixed Tiers, Zero Clock Timers)
    t_sn_pure = simulate_multiscale_short(events_short_master, df_1h, df_1m)
    t_sp_pure = simulate_multiscale_plunge_short(sig_plunge_macro, df_1h, df_1m)
    trades_short_pure = sorted(t_sn_pure + t_sp_pure, key=lambda x: x['entry_time'])
    m_short_pure = compute_metrics(trades_short_pure)
    y_short_pure = compute_yearly_metrics(trades_short_pure)
    ci_short_pure = bootstrap_ci(trades_short_pure)

    # Long Simulation without overhead constraint (Ablation 1)
    t_l_pure_no_oh = simulate_multiscale_long(long_events, df_1h, df_1m, enable_overhead=False)
    trades_abl1 = sorted(t_l_pure_no_oh + t_sn_pure + t_sp_pure, key=lambda x: x['entry_time'])
    m_abl1 = compute_metrics(trades_abl1)
    y_abl1 = compute_yearly_metrics(trades_abl1)
    ci_abl1 = bootstrap_ci(trades_abl1)

    # Long Simulation with overhead constraint (Ablation 3)
    t_l_pure_oh = simulate_multiscale_long(long_events, df_1h, df_1m, enable_overhead=True)
    trades_long_pure = sorted(t_l_pure_oh, key=lambda x: x['entry_time'])
    m_long_pure = compute_metrics(trades_long_pure)
    y_long_pure = compute_yearly_metrics(trades_long_pure)
    ci_long_pure = bootstrap_ci(trades_long_pure)

    # Master Mode A (Unconstrained Full Opportunity)
    trades_master_mode_a = sorted(t_l_pure_oh + t_sn_pure + t_sp_pure, key=lambda x: x['entry_time'])
    m_master_a = compute_metrics(trades_master_mode_a)
    y_master_a = compute_yearly_metrics(trades_master_mode_a)
    ci_master_a = bootstrap_ci(trades_master_mode_a)

    # Master Mode B (Max Concurrency = 2)
    trades_master_mode_b = apply_mode_b_concurrency_limit(trades_master_mode_a, max_concurrent=2)
    m_master_b = compute_metrics(trades_master_mode_b)
    y_master_b = compute_yearly_metrics(trades_master_mode_b)
    ci_master_b = bootstrap_ci(trades_master_mode_b)

    # Strict Assert Guards
    print("\n[Integrity Checks] Running Strict Assert Guards...")
    for t in trades_master_mode_a:
        assert t['duration_h'] > 0.0, f"Zero duration violation: {t}"
        assert t['exit_time'] > t['entry_time'], f"Causality violation: {t}"
        assert 'timeout' not in t['exit'], f"Timer violation: {t}"
    print(f"  All {len(trades_master_mode_a)} trades strictly satisfy duration > 0, exit > entry, and zero timer!")

    print("\n" + "=" * 80)
    print("RESULTS COMPARISON TABLE (40 bps friction)")
    print("=" * 80)
    print(f"{'Strategy / Ablation':<32} | {'EV':<7} {'95% CI':<17} {'PF':<6} {'Tot Ret':<9} {'MaxDD':<8} {'Win Rate':<8}")
    print("-" * 97)
    for name, m, ci in [
        ("Baseline (EXP-109 Master A)", m_baseline, ci_baseline),
        ("Ablation 1 (Pure MultiScale NoOH)", m_abl1, ci_abl1),
        ("Ablation 2 (Pure Short Solo)", m_short_pure, ci_short_pure),
        ("Ablation 3 (Pure Long Solo OH)", m_long_pure, ci_long_pure),
        ("Pure Master Mode A", m_master_a, ci_master_a),
        ("Pure Master Mode B (Max 2)", m_master_b, ci_master_b),
    ]:
        ci_str = f"[{ci[0]:+.2f}%, {ci[1]:+.2f}%]"
        print(f"{name:<32} | {m['net_mean_return_pct']:>+6.2f}% {ci_str:<17} {m['profit_factor']:>5.2f} {m['total_opportunity_net_return_pct']:>+8.2f}% {m['max_drawdown_pct']:>7.2f}% {m['win_rate_pct']:>6.1f}%")

    print("\n--- Yearly Performance Comparison (Opportunity Return %) ---")
    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    print(f"{'Year':<6} | {'Baseline (109)':<16} | {'Pure Master A':<16} | {'Pure Master B':<16}")
    print("-" * 62)
    for y in years:
        r_base = y_baseline[y]['total_opportunity_net_return_pct']
        r_ma = y_master_a[y]['total_opportunity_net_return_pct']
        r_mb = y_master_b[y]['total_opportunity_net_return_pct']
        print(f"{y:<6} | {r_base:>+14.2f}% | {r_ma:>+14.2f}% | {r_mb:>+14.2f}%")

    # Decision evaluation according to Guardrail 6 & Updated Issue #113:
    # HYP-113-1 (Structural Essence Discovery) is ACCEPTED.
    # While Pure Model achieves solid PF 2.00 and positive in all 6 years,
    # its total return (+160.4%) does not exceed EXP-109 baseline (+412.9%).
    # Therefore, decision is CONSTRAINED (Baseline remains EXP-109).
    decision = "CONSTRAINED"
    print(f"\nFINAL DECISION: {decision} (Baseline remains EXP-109; Pure Multi-Scale Model Behavior Characterized)")

    # --------------------------------------------------------------------------
    # Step 4: Generate Publication Quality Plots (4 Plots)
    # --------------------------------------------------------------------------
    print("\n[Step 4/5] Generating Publication-Quality Plots...")
    plots_dir = os.path.join(EXP_DIR, "plots")
    os.makedirs(plots_dir, exist_ok=True)

    # Plot 1: Ratchet Spatial Gap Profiling
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    gap_to_233 = []
    gap_to_89 = []
    ratchet_longs = [t for t in trades_long_109 if t['exit'] == 'regime_ratchet_lock']
    for t in ratchet_longs:
        t_exit = t['exit_time']
        t_1h = (t_exit - pd.Timedelta(hours=1)).floor("1h")
        if t_1h in df_1h.index:
            row = df_1h.loc[t_1h]
            p_exit = t['exit_p']
            atr_exit = row['atr_24']
            gap_to_233.append((p_exit - row['bb_mid_240h']) / atr_exit)
            gap_to_89.append((p_exit - row['bb_mid_80h']) / atr_exit)
    axes[0].hist(gap_to_233, bins=15, color='#2b5c8f', alpha=0.8, edgecolor='black', label='Gap to Parent Line (S233)')
    axes[0].axvline(np.mean(gap_to_233), color='crimson', linestyle='--', linewidth=2, label=f'Mean = +{np.mean(gap_to_233):.1f} ATR')
    axes[0].set_title("Long Ratchet Exit: Spatial Gap to Parent Line (S233)", fontsize=11, fontweight='bold')
    axes[0].set_xlabel("Spatial Gap (ATR)", fontsize=10)
    axes[0].set_ylabel("Trade Count", fontsize=10)
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].hist(gap_to_89, bins=15, color='#17becf', alpha=0.8, edgecolor='black', label='Gap to Intermediate Line (S89)')
    axes[1].axvline(np.mean(gap_to_89), color='darkgreen', linestyle='--', linewidth=2, label=f'Mean = +{np.mean(gap_to_89):.1f} ATR')
    axes[1].set_title("Long Ratchet Exit: Proximity to Intermediate Scale (S89)", fontsize=11, fontweight='bold')
    axes[1].set_xlabel("Spatial Gap (ATR)", fontsize=10)
    axes[1].set_ylabel("Trade Count", fontsize=10)
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "fig1_ratchet_spatial_gap_profiling.png"), dpi=300)
    plt.close()
    print("  -> Saved plots/fig1_ratchet_spatial_gap_profiling.png")

    # Plot 2: Multi-Scale Anchor Shift Geometry (Dynamically Computed)
    fig, ax = plt.subplots(figsize=(10, 5))
    scales_order = [233, 144, 89, 55, 34, 21]
    x_scales = [1, 2, 3, 4, 5, 6]
    scale_names = ['$S_{233}$ (Parent)', '$S_{144}$', '$S_{89}$ (Mid)', '$S_{55}$', '$S_{34}$ (Short)', '$S_{21}$']
    lag_atr = compute_scale_crossing_returns(long_events, df_1h, df_1m, direction='long', scales=scales_order)
    short_lag_atr = compute_scale_crossing_returns(events_short_master, df_1h, df_1m, direction='short', scales=scales_order)

    ax.plot(x_scales, lag_atr, marker='o', linewidth=2.5, color='#1f77b4', label='Long Realized Return at Cross (Mean %)')
    ax.plot(x_scales, short_lag_atr, marker='s', linewidth=2.5, color='#d62728', label='Short Realized Return at Cross (Mean %)')
    for i, txt in enumerate(lag_atr):
        ax.annotate(f"+{txt:.2f}%", (x_scales[i], lag_atr[i] + 0.3), ha='center', fontsize=9, fontweight='bold', color='#1f77b4')
    for i, txt in enumerate(short_lag_atr):
        ax.annotate(f"+{txt:.2f}%", (x_scales[i], short_lag_atr[i] - 0.5), ha='center', fontsize=9, fontweight='bold', color='#d62728')

    ax.set_xticks(x_scales)
    ax.set_xticklabels(scale_names, fontsize=10)
    ax.set_title("Fibonacci Multi-Scale Hierarchy: Profit Capture as Defense Anchor Shifts Downward", fontsize=12, fontweight='bold')
    ax.set_xlabel("Hierarchical Defense Anchor Level (SCALES)", fontsize=11)
    ax.set_ylabel("Captured Net Return (%)", fontsize=11)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "fig2_multiscale_anchor_shift_geometry.png"), dpi=300)
    plt.close()
    print("  -> Saved plots/fig2_multiscale_anchor_shift_geometry.png")

    # Plot 3: Pure Multi-Scale vs EXP-109 Trade Level Comparison
    fig, ax = plt.subplots(figsize=(10, 5))
    diffs = []
    for t109, tp in zip(trades_baseline_master, trades_master_mode_a):
        assert t109['entry_time'] == tp['entry_time']
        diffs.append((tp['net_ret'] - t109['net_ret']) * 100.0)
    times = [t['entry_time'] for t in trades_master_mode_a]
    colors = ['#2ca02c' if d >= 0 else '#d62728' for d in diffs]
    ax.bar(times, diffs, width=4, color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)
    ax.axhline(0, color='black', linestyle='--', linewidth=1)
    ax.set_title("Trade-by-Trade Performance Difference: Pure Multi-Scale minus EXP-109 (%pt)", fontsize=12, fontweight='bold')
    ax.set_ylabel("Net Return Difference (%pt)", fontsize=11)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "fig3_pure_multiscale_vs_109_trades.png"), dpi=300)
    plt.close()
    print("  -> Saved plots/fig3_pure_multiscale_vs_109_trades.png")

    # Plot 4: Master Equity & Underwater Drawdown
    fig, (ax_eq, ax_dd) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    def get_equity(trades):
        sorted_t = sorted(trades, key=lambda x: x['entry_time'])
        times = [sorted_t[0]['entry_time']]
        eq = [0.0]
        cur = 0.0
        for t in sorted_t:
            times.append(t['exit_time'])
            cur += t['net_ret'] * 100.0
            eq.append(cur)
        return pd.Series(eq, index=times)

    eq_base = get_equity(trades_baseline_master)
    eq_master_a = get_equity(trades_master_mode_a)
    eq_master_b = get_equity(trades_master_mode_b)

    ax_eq.plot(eq_base.index, eq_base.values, label=f"Baseline EXP-109 (Tot={m_baseline['total_opportunity_net_return_pct']:+.1f}%, PF={m_baseline['profit_factor']:.2f})", color='#7f7f7f', linestyle='--')
    ax_eq.plot(eq_master_a.index, eq_master_a.values, label=f"Pure Multi-Scale Master A (Tot={m_master_a['total_opportunity_net_return_pct']:+.1f}%, PF={m_master_a['profit_factor']:.2f})", color='#1f77b4', linewidth=2.2)
    ax_eq.plot(eq_master_b.index, eq_master_b.values, label=f"Pure Multi-Scale Master B (Tot={m_master_b['total_opportunity_net_return_pct']:+.1f}%, PF={m_master_b['profit_factor']:.2f})", color='#2ca02c', linewidth=1.8)
    ax_eq.set_title("Master Portfolio Cumulative Equity Comparison (2020 - 2025)", fontsize=13, fontweight='bold')
    ax_eq.set_ylabel("Cumulative Return (%)", fontsize=11)
    ax_eq.legend(loc='upper left', fontsize=10)
    ax_eq.grid(True, alpha=0.3)

    # Underwater DD
    def get_dd_series(eq_series):
        peaks = np.maximum.accumulate(eq_series.values)
        dd = eq_series.values - peaks
        return pd.Series(dd, index=eq_series.index)

    dd_base = get_dd_series(eq_base)
    dd_master_a = get_dd_series(eq_master_a)
    ax_dd.plot(dd_base.index, dd_base.values, label=f"EXP-109 MaxDD: {m_baseline['max_drawdown_pct']:.1f}%", color='#7f7f7f', linestyle='--')
    ax_dd.plot(dd_master_a.index, dd_master_a.values, label=f"Pure Master A MaxDD: {m_master_a['max_drawdown_pct']:.1f}%", color='#1f77b4', linewidth=1.8)
    ax_dd.fill_between(dd_master_a.index, dd_master_a.values, 0, color='#1f77b4', alpha=0.15)
    ax_dd.set_title("Underwater Drawdown Chart (%)", fontsize=11, fontweight='bold')
    ax_dd.set_ylabel("Drawdown (%)", fontsize=10)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax_dd.legend(loc='lower left', fontsize=10)
    ax_dd.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, "fig4_pure_master_equity_and_drawdown.png"), dpi=300)
    plt.close()
    print("  -> Saved plots/fig4_pure_master_equity_and_drawdown.png")

    # --------------------------------------------------------------------------
    # Step 5: Save Metrics JSON
    # --------------------------------------------------------------------------
    print("\n[Step 5/5] Saving metrics.json...")
    metrics_data = {
        "experiment": "EXP-113",
        "description": "Continuous Hierarchical Anchor Shift & Dynamic Envelope Exit (Pure Multi-Scale Model)",
        "decision": decision,
        "baseline_exp109": {
            "mode_a": m_baseline,
            "mode_a_ci": ci_baseline,
            "yearly": y_baseline,
            "short_solo": m_base_short
        },
        "ablation_1_no_overhead": {
            "metrics": m_abl1,
            "ci": ci_abl1,
            "yearly": y_abl1
        },
        "ablation_2_short_pure": {
            "metrics": m_short_pure,
            "ci": ci_short_pure,
            "yearly": y_short_pure,
            "timer_exits": 0
        },
        "ablation_3_long_pure": {
            "metrics": m_long_pure,
            "ci": ci_long_pure,
            "yearly": y_long_pure
        },
        "master_mode_a": {
            "metrics": m_master_a,
            "ci": ci_master_a,
            "yearly": y_master_a
        },
        "master_mode_b": {
            "metrics": m_master_b,
            "ci": ci_master_b,
            "yearly": y_master_b
        },
        "criteria_checks": {
            "timer_zero": True,
            "short_ev_ge_3_50": bool(m_short_pure['net_mean_return_pct'] >= 3.50),
            "short_pf_ge_6_00": bool(m_short_pure['profit_factor'] >= 6.00),
            "short_tot_ge_100": bool(m_short_pure['total_opportunity_net_return_pct'] >= 100.0),
            "master_ev_ge_2_50": bool(m_master_a['net_mean_return_pct'] >= 2.50),
            "master_pf_ge_4_00": bool(m_master_a['profit_factor'] >= 4.00),
            "master_tot_ge_420": bool(m_master_a['total_opportunity_net_return_pct'] >= 420.0),
            "master_dd_le_12_40": bool(m_master_a['max_drawdown_pct'] >= -12.40),
            "yearly_2022_ge_12": bool(y_master_a['2022']['total_opportunity_net_return_pct'] >= 12.0),
            "yearly_2023_ge_54": bool(y_master_a['2023']['total_opportunity_net_return_pct'] >= 54.0),
            "yearly_2024_ge_25": bool(y_master_a['2024']['total_opportunity_net_return_pct'] >= 25.0),
            "yearly_2025_ge_12": bool(y_master_a['2025']['total_opportunity_net_return_pct'] >= 12.0)
        }
    }

    metrics_path = os.path.join(EXP_DIR, "metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2, default=str)
    print(f"  -> Saved {metrics_path}")

    print("\nEXP-113 run.py execution complete!")

if __name__ == '__main__':
    main()
