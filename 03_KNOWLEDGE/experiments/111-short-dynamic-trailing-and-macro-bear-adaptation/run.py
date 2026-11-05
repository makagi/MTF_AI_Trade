#!/usr/bin/env python3
"""
EXP-111: ショート側エグジットの幾何学的脱ドグマ（72h固定枠完全撤廃・親構造線動的トレール）と大局ベア相場ロング適応制御の検証

Discovery 期間: 2020-01-01 00:00:00 ~ 2025-04-30 23:59:59 (UTC)
Holdout 期間: 2025-05-01 以降 (完全隔離)
摩擦コスト: 往復 40 bps (0.40%)
"""

import os
import sys
import time
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# プロジェクトルートの設定
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, ROOT_DIR)

import importlib.util

path_95 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/95-short-symmetry-and-bidirectional-portfolio/run.py")
spec_95 = importlib.util.spec_from_file_location('exp95_mod', path_95)
exp95 = importlib.util.module_from_spec(spec_95)
sys.modules['exp95_mod'] = exp95
spec_95.loader.exec_module(exp95)

path_103 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/103-mtf-bb-envelope-and-macro-alignment/run.py")
spec_103 = importlib.util.spec_from_file_location('exp103_mod', path_103)
exp103 = importlib.util.module_from_spec(spec_103)
sys.modules['exp103_mod'] = exp103
spec_103.loader.exec_module(exp103)

path_107 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/107-dynamic-mtf-range-exit-and-trend-riding/run.py")
spec_107 = importlib.util.spec_from_file_location('exp107_mod', path_107)
exp107 = importlib.util.module_from_spec(spec_107)
sys.modules['exp107_mod'] = exp107
spec_107.loader.exec_module(exp107)

path_109 = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/109-regime-adaptive-dynamic-exit/run.py")
spec_109 = importlib.util.spec_from_file_location('exp109_mod', path_109)
exp109 = importlib.util.module_from_spec(spec_109)
sys.modules['exp109_mod'] = exp109
spec_109.loader.exec_module(exp109)

# 定数定義
DISCOVERY_START = exp95.DISCOVERY_START
HOLDOUT_START = exp95.HOLDOUT_START
FRICTION_BPS = exp95.COST_BPS
SCALES = exp95.SCALES

def get_period(ts):
    return exp95.get_period(ts)

def compute_metrics(trades):
    return exp109.compute_metrics(trades)

def compute_yearly_metrics(trades):
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    ym = {}
    for y in years:
        sub = [t for t in trades if t['entry_time'].year == y]
        ym[str(y)] = compute_metrics(sub)
    return ym

def bootstrap_ci(trades, n_boot=2000, alpha=0.05):
    return exp109.bootstrap_ci(trades, n_boot=n_boot, alpha=alpha)

def apply_mode_b_concurrency_limit(trades, max_concurrent=2):
    return exp109.apply_mode_b_concurrency_limit(trades, max_concurrent=max_concurrent)

def load_data_and_features():
    df_1h = exp95.load_ohlcv('BTCUSD', '1h').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1h.index < HOLDOUT_START).all(), "CRITICAL: Holdout leak in 1h!"
    df_1m = exp95.load_ohlcv('BTCUSD', '1m').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1m.index < HOLDOUT_START).all(), "CRITICAL: Holdout leak in 1m!"

    atr_1h = exp95.calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr_1h
    close_1h = df_1h['close']
    open_1h = df_1h['open']
    high_1h = df_1h['high']
    low_1h = df_1h['low']

    candle_range = high_1h - low_1h
    lower_wick = np.minimum(open_1h, close_1h) - low_1h
    upper_wick = high_1h - np.maximum(open_1h, close_1h)
    df_1h['wick_ratio'] = np.where(candle_range > 0, lower_wick / candle_range, 0.0)
    df_1h['upper_wick_ratio'] = np.where(candle_range > 0, upper_wick / candle_range, 0.0)

    for p in SCALES:
        df_1h[f'sma_{p}'] = exp95.calculate_sma(close_1h, p)
        df_1h[f'slope_{p}'] = (df_1h[f'sma_{p}'] - df_1h[f'sma_{p}'].shift(3)) / (3 * atr_1h)

    bb_upper, bb_mid, bb_lower = exp95.calculate_bollinger_bands(close_1h, 20, 2.0)
    df_1h['bb_upper'] = bb_upper
    df_1h['bb_mid'] = bb_mid
    df_1h['bb_lower'] = bb_lower

    for p in [20, 80, 240, 480]:
        mid = close_1h.rolling(p).mean()
        std = close_1h.rolling(p).std()
        df_1h[f'bb_mid_{p}h'] = mid
        df_1h[f'bb_upper_{p}h'] = mid + 2.0 * std
        df_1h[f'bb_lower_{p}h'] = mid - 2.0 * std
        df_1h[f'bb_slope_{p}h'] = (mid - mid.shift(3)) / (3 * atr_1h)

    df_1d = df_1h.resample('1D').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    df_1d['sma_200d'] = df_1d['close'].rolling(200).mean()
    df_1d['bb_mid_20d'] = df_1d['close'].rolling(20).mean()
    df_1d['bb_lower_20d'] = df_1d['bb_mid_20d'] - 2.0 * df_1d['close'].rolling(20).std()
    df_1h = df_1h.join(df_1d[['sma_200d', 'bb_mid_20d', 'bb_lower_20d']].shift(1)).ffill()

    afs_df, order_score, compression = exp95.calculate_afs(df_1h, periods=[7, 9, 11, 13])
    df_1h['afs_order_score'] = order_score
    for p in [7, 9, 11, 13]:
        df_1h[f'afs_{p}'] = afs_df[f'AFS_{p}']

    df_1h['maj_score_bear'] = (
        (df_1h['afs_7'] < df_1h['afs_9']).astype(int) +
        (df_1h['afs_7'] < df_1h['afs_11']).astype(int) +
        (df_1h['afs_7'] < df_1h['afs_13']).astype(int) +
        (df_1h['afs_9'] < df_1h['afs_11']).astype(int) +
        (df_1h['afs_9'] < df_1h['afs_13']).astype(int) +
        (df_1h['afs_11'] < df_1h['afs_13']).astype(int)
    )
    df_1h['afs_order_score_bear'] = (
        (df_1h['afs_7'] < df_1h['afs_9']).astype(int) +
        (df_1h['afs_9'] < df_1h['afs_11']).astype(int) +
        (df_1h['afs_11'] < df_1h['afs_13']).astype(int)
    )

    regime_df = exp95.calculate_regime_age(df_1h)
    df_1h['macro_age_ratio'] = regime_df['macro_age_ratio']
    roll_high_720h = high_1h.rolling(720, min_periods=72).max()
    roll_low_720h = low_1h.rolling(720, min_periods=72).min()
    df_1h['range_pos_720h'] = (close_1h - roll_low_720h) / (roll_high_720h - roll_low_720h + 1e-8)

    gap_4181_6765 = (df_1h['sma_4181'] - df_1h['sma_6765']) / atr_1h
    df_1h['gap_4181_6765'] = gap_4181_6765

    is_mtf_lockin_bull = (df_1h['bb_mid_20h'] > df_1h['bb_mid_80h']) & (df_1h['bb_mid_80h'] > df_1h['bb_mid_480h']) & (df_1h['bb_slope_480h'] > 0)
    df_1h['is_mtf_lockin_bull'] = is_mtf_lockin_bull
    df_1h['bb_width_240h'] = (4.0 * close_1h.rolling(240).std()) / close_1h.rolling(240).mean() * 100.0
    df_1h['bb_width_pct_2160'] = df_1h['bb_width_240h'].rolling(2160, min_periods=120).rank(pct=True)
    df_1h['is_true_squeeze'] = (df_1h['bb_width_pct_2160'] <= 0.45) & (df_1h['bb_slope_240h'].abs() <= 0.04)

    # Directional Lock-In Bear
    is_mtf_lockin_bear = (df_1h['bb_mid_20h'] < df_1h['bb_mid_80h']) & (df_1h['bb_mid_80h'] < df_1h['bb_mid_480h']) & (df_1h['bb_slope_480h'] < 0)
    df_1h['is_mtf_lockin_bear'] = is_mtf_lockin_bear

    # Overhead Resistance Constraint (Directive 3)
    df_1h['is_overhead_blocked'] = (df_1h['bb_mid_240h'] < df_1h['bb_mid_480h']) & (df_1h['bb_slope_480h'] < 0) & (df_1h['close'] < df_1h['bb_mid_480h'])

    has_downside_vacuum = pd.Series(True, index=df_1h.index)
    for p in [89, 144, 233, 377, 610]:
        s_p = df_1h[f'sma_{p}']
        is_blocked = (s_p < close_1h) & ((close_1h - s_p) / atr_1h < 1.5)
        has_downside_vacuum = has_downside_vacuum & (~is_blocked)
    df_1h['has_downside_vacuum'] = has_downside_vacuum

    # Long Signals Generation
    meso_raw = (close_1h > df_1h['sma_34']) & (close_1h.shift(1) <= df_1h['sma_34'].shift(1)) & (df_1h['slope_55'] > 0)
    meso_decl = exp95.decluster_events(meso_raw, cooldown_bars=24)
    gate_trap = ~(df_1h['macro_age_ratio'] > 2.0)
    gate_booster = (df_1h['afs_order_score'] == 3)
    mvc_long = meso_decl & gate_trap & gate_booster

    cond_pb_adj = (close_1h < df_1h['sma_34']) & (close_1h < df_1h['sma_233'])
    cond_pb_higher = (df_1h['slope_610'] > 0) & (df_1h['slope_987'] > 0) & (close_1h > df_1h['sma_987'])
    cond_pb_range = (df_1h['range_pos_720h'] >= 0.35) & (df_1h['range_pos_720h'] <= 0.65)
    cond_pb_trigger = (close_1h > open_1h) & (close_1h > df_1h['sma_21']) & (close_1h.shift(1) <= df_1h['sma_21'].shift(1))
    pb_long = cond_pb_adj & cond_pb_higher & cond_pb_range & cond_pb_trigger & (df_1h['afs_order_score'] == 3)
    k043_selective_raw = mvc_long | pb_long

    prop_events_fast = exp95.evaluate_hypo_propagation(df_1h, 21, 55, 89, 144, 3, 1.0, 8, 2.0)
    prop_mask_fast = pd.Series(False, index=df_1h.index)
    prop_mask_fast.loc[prop_events_fast] = True
    master_raw_long = k043_selective_raw | prop_mask_fast
    vacuum_trap_filter = (df_1h['range_pos_720h'] >= 0.80) & (gap_4181_6765 >= 10.0)
    filtered_decl_long = exp95.decluster_events(master_raw_long & (~vacuum_trap_filter), cooldown_bars=24)
    long_events = df_1h.index[filtered_decl_long]

    # Short Signals Generation
    dist_to_sma200d = (close_1h - df_1h['sma_200d']) / close_1h
    is_support_blocked = (gap_4181_6765 < 15.0) & (dist_to_sma200d > 0.0) & (dist_to_sma200d < 0.045)
    cross_4181 = (close_1h < df_1h['sma_4181']) & (close_1h.shift(1) >= df_1h['sma_4181'].shift(1))
    macro_plunge_filter = (df_1h['close'] < df_1h['bb_mid_20d']) & ((df_1h['close'] - df_1h['bb_lower_20d']) / df_1h['bb_lower_20d'] <= 0.03)
    sig_plunge_macro = cross_4181 & (gap_4181_6765 >= 8.0) & (df_1h['maj_score_bear'] >= 4) & (close_1h < df_1h['sma_4181']) & macro_plunge_filter & (~is_support_blocked)

    cond_spb_adj = (close_1h > df_1h['sma_34']) & (close_1h > df_1h['sma_233']) & (close_1h < df_1h['sma_377'])
    cond_spb_higher = (df_1h['slope_610'] < 0) & (df_1h['slope_987'] < 0) & (close_1h < df_1h['sma_987'])
    cond_spb_range = (df_1h['range_pos_720h'] >= 0.35) & (df_1h['range_pos_720h'] <= 0.65)
    cond_spb_trigger = (close_1h < open_1h) & (close_1h < df_1h['sma_21']) & (close_1h.shift(1) >= df_1h['sma_21'].shift(1))
    spb_raw = cond_spb_adj & cond_spb_higher & cond_spb_range & cond_spb_trigger & (df_1h['afs_order_score_bear'] == 3) & df_1h['has_downside_vacuum']

    prop_events_trio3 = exp95.evaluate_hypo_propagation_bear(df_1h, 55, 144, 233, 377, 8, 1.5, 21, 3.5)
    prop_mask_trio3 = pd.Series(False, index=df_1h.index)
    prop_mask_trio3.loc[prop_events_trio3] = True

    prop_events_trio2 = exp95.evaluate_hypo_propagation_bear(df_1h, 34, 89, 144, 233, 5, 1.2, 13, 2.5)
    prop_mask_trio2 = pd.Series(False, index=df_1h.index)
    prop_mask_trio2.loc[prop_events_trio2] = True
    trio2_trend_aligned = prop_mask_trio2 & (close_1h < df_1h['sma_89']) & (df_1h['slope_610'] < 0) & (df_1h['slope_987'] < 0)

    is_lockin_bull_higher = (df_1h['slope_610'] > 0.015) & (df_1h['slope_987'] > 0.015) & (df_1h['sma_610'] > df_1h['sma_987'])
    short_master_raw = (spb_raw | prop_mask_trio3 | trio2_trend_aligned) & (~is_lockin_bull_higher)
    events_short_master = df_1h.index[exp95.decluster_events(short_master_raw, cooldown_bars=24)]

    return df_1h, df_1m, long_events, events_short_master, sig_plunge_macro

# ==============================================================================
# Structural Scale Shift Dynamic Short Simulation (Directive 1 & 2)
# ==============================================================================
def simulate_dynamic_short(events, df_1h, df_1m,
                           struct_mode='regime_adaptive',  # 'uniform_intermediate' or 'regime_adaptive'
                           initial_risk_atr=2.0):
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

        # Directive 1: Safety stop floor outside p0
        std_80_0 = (df_1h['bb_upper_80h'].loc[t0] - df_1h['bb_mid_80h'].loc[t0]) / 2.0
        base_stop = max(df_1h['bb_upper_80h'].loc[t0], df_1h['sma_34'].loc[t0] + 2.0 * std_80_0, p0 + initial_risk_atr * atr0)

        armed = False
        reached_env_240 = False
        reached_env_480 = False
        trail_stop = 999999.0
        max_mfe_atr = 0.0
        exited = False

        for i in range(n_bars):
            t_bar = sub_times[i]
            elapsed_h = (t_bar - entry_time).total_seconds() / 3600.0

            # Directive 1: Structural Invalidation on 1h bar update when un-armed
            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    if not armed:
                        if row_1h['close'] > row_1h['bb_mid_20h'] and row_1h['bb_slope_20h'] > 0 and row_1h['afs_order_score_bear'] == 0:
                            dur_h = float(np.round(elapsed_h, 2))
                            trades.append({
                                't0': t0, 'entry_time': entry_time, 'exit_time': t_bar, 'period': p_era,
                                'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (p0 - sub_opens[i])/p0 - FRICTION_BPS,
                                'duration_h': dur_h, 'exit': 'structural_invalidation',
                                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short',
                                'struct_mode': struct_mode
                            })
                            exited = True
                            break

            cur_high = sub_highs[i]
            cur_low = sub_lows[i]
            cur_open = sub_opens[i]

            cur_mfe = (p0 - cur_low) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe

            t_1h_cur = t_bar.floor('1h')
            row_cur = df_1h.loc[t_1h_cur] if t_1h_cur in df_1h.index else df_1h.loc[t0]

            std_20 = (row_cur['bb_upper_20h'] - row_cur['bb_mid_20h']) / 2.0
            std_80 = (row_cur['bb_upper_80h'] - row_cur['bb_mid_80h']) / 2.0
            std_240 = (row_cur['bb_upper_240h'] - row_cur['bb_mid_240h']) / 2.0

            if not armed and cur_low <= row_cur['bb_mid_240h'] - 0.5 * std_240:
                armed = True

            if armed:
                if cur_low <= row_cur['bb_lower_240h']:
                    reached_env_240 = True
                if cur_low <= row_cur['bb_lower_480h']:
                    reached_env_480 = True

                afs_reversal = (row_cur['afs_7'] > row_cur['afs_9'])

                # Directive 2: Dynamic Scale Shift (Parent 240h -> Intermediate 80h -> Short 20h)
                if struct_mode == 'regime_adaptive':
                    if reached_env_480 and afs_reversal:
                        cand_stop = row_cur['bb_mid_20h'] + 0.5 * std_20
                    elif reached_env_240 and afs_reversal:
                        cand_stop = row_cur['bb_mid_80h'] + 0.5 * std_80
                    else:
                        cand_stop = row_cur['bb_mid_240h'] + 0.5 * std_240
                else: # uniform_intermediate
                    if reached_env_240 and afs_reversal:
                        cand_stop = row_cur['bb_mid_80h'] + 0.5 * std_80
                    else:
                        cand_stop = row_cur['bb_mid_80h'] + 0.5 * std_80

                if cand_stop > cur_high:
                    trail_stop = min(trail_stop, cand_stop)

            effective_stop = min(base_stop, trail_stop)

            # Direct stop hit verification without if i > 0
            if cur_high >= effective_stop:
                dur_h = float(np.round(elapsed_h, 2))
                p_exit = max(cur_open, effective_stop)
                exit_type = 'struct_exit' if effective_stop == trail_stop else 'stop_hit'
                trades.append({
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_bar, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p0 - p_exit)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': exit_type,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short',
                    'struct_mode': struct_mode
                })
                exited = True
                break

        if not exited:
            dur_h = float(np.round((sub_times[-1] - entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (p0 - sub_closes[-1])/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short',
                'struct_mode': struct_mode
            })

    return trades

# ==============================================================================
# Plunge Short Simulation with Unified Scale Shift (Directive 2)
# ==============================================================================
def simulate_plunge_short_dynamic(events, df_1h, df_1m, target_sma_col='sma_6765', initial_risk_atr=2.0):
    trades = []
    events_decl = exp95.decluster_events(events, cooldown_bars=24)
    event_idx = df_1h.index[events_decl]
    discovery_end = df_1m.index[-1]

    for t0 in event_idx:
        loc_1h = df_1h.index.get_loc(t0)
        if loc_1h + 1 >= len(df_1h):
            continue
        t_entry = df_1h.index[loc_1h + 1]
        path_1m = df_1m.loc[t_entry : discovery_end]
        if path_1m.empty or len(path_1m) < 60:
            continue
        entry_price = float(path_1m['open'].iloc[0])
        atr = float(df_1h['atr_24'].loc[t0])
        target_price = float(df_1h[target_sma_col].loc[t0])
        p_era = exp95.get_period(t0)
        exited = False
        max_mfe_atr = 0.0

        base_stop = max(df_1h['bb_upper_80h'].loc[t0], entry_price + initial_risk_atr * atr)

        reached_env_240 = False
        reached_env_480 = False
        trail_stop = 999999.0

        for bar_idx, row in path_1m.iterrows():
            high = float(row['high'])
            low = float(row['low'])
            cur_open = float(row['open'])
            elapsed_h = (bar_idx - t_entry).total_seconds() / 3600.0

            mfe_atr = (entry_price - low) / atr
            if mfe_atr > max_mfe_atr:
                max_mfe_atr = mfe_atr

            t_1h = bar_idx.floor('1h')
            row_cur = df_1h.loc[t_1h] if t_1h in df_1h.index else df_1h.loc[t0]

            std_20 = (row_cur['bb_upper_20h'] - row_cur['bb_mid_20h']) / 2.0
            std_80 = (row_cur['bb_upper_80h'] - row_cur['bb_mid_80h']) / 2.0
            std_240 = (row_cur['bb_upper_240h'] - row_cur['bb_mid_240h']) / 2.0

            if low <= target_price:
                dur_h = float(np.round(elapsed_h, 2))
                trades.append({
                    't0': t0, 'entry_time': t_entry, 'exit_time': bar_idx, 'period': p_era,
                    'p0': entry_price, 'exit_p': target_price,
                    'net_ret': (entry_price - target_price)/entry_price - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': 'target_hit',
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
                })
                exited = True
                break

            if low <= row_cur['bb_lower_240h']:
                reached_env_240 = True
            if low <= row_cur['bb_lower_480h']:
                reached_env_480 = True

            afs_reversal = (row_cur['afs_7'] > row_cur['afs_9'])

            # Unified Scale Shift for Plunge Short
            if reached_env_480 and afs_reversal:
                cand_stop = row_cur['bb_mid_20h'] + 0.5 * std_20
            elif reached_env_240 and afs_reversal:
                cand_stop = row_cur['bb_mid_80h'] + 0.5 * std_80
            else:
                cand_stop = row_cur['bb_mid_240h'] + 0.5 * std_240

            if cand_stop > high:
                trail_stop = min(trail_stop, cand_stop)

            effective_stop = min(base_stop, trail_stop)

            if high >= effective_stop:
                dur_h = float(np.round(elapsed_h, 2))
                p_exit = max(cur_open, effective_stop)
                exit_type = 'struct_exit' if effective_stop == trail_stop else 'stop_hit'
                trades.append({
                    't0': t0, 'entry_time': t_entry, 'exit_time': bar_idx, 'period': p_era,
                    'p0': entry_price, 'exit_p': p_exit,
                    'net_ret': (entry_price - p_exit)/entry_price - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': exit_type,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
                })
                exited = True
                break

        if not exited:
            p_exit = float(path_1m['close'].iloc[-1])
            dur_h = float(np.round((path_1m.index[-1] - t_entry).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': t_entry, 'exit_time': path_1m.index[-1], 'period': p_era,
                'p0': entry_price, 'exit_p': p_exit,
                'net_ret': (entry_price - p_exit)/entry_price - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'short', 'side': 'short'
            })
    return trades

# ==============================================================================
# Structural Long Simulation with Dynamic Overhead Resistance (Directive 1 & 3)
# ==============================================================================
def simulate_adaptive_long(events, df_1h, df_1m,
                           enable_overhead_resistance_adaptation=True,
                           initial_risk_atr=2.0):
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

        # Directive 1: Safety stop floor outside p0
        std_80_0 = (df_1h['bb_upper_80h'].loc[t0] - df_1h['bb_mid_80h'].loc[t0]) / 2.0
        base_stop = min(df_1h['bb_lower_80h'].loc[t0], df_1h['sma_34'].loc[t0] - 2.0 * std_80_0, p0 - initial_risk_atr * atr0)

        parent_armed = False
        reached_env_240 = False
        trail_stop = -999999.0
        max_mfe_atr = 0.0
        exited = False

        for i in range(n_bars):
            t_bar = sub_times[i]
            elapsed_h = (t_bar - entry_time).total_seconds() / 3600.0

            # Directive 1: Structural Invalidation on 1h bar update when un-armed
            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    if not parent_armed:
                        if row_1h['close'] < row_1h['bb_mid_20h'] and row_1h['bb_slope_20h'] < 0 and row_1h['afs_order_score'] == 0:
                            dur_h = float(np.round(elapsed_h, 2))
                            trades.append({
                                't0': t0, 'entry_time': entry_time, 'exit_time': t_bar, 'period': p_era,
                                'p0': p0, 'exit_p': sub_opens[i], 'net_ret': (sub_opens[i] - p0)/p0 - FRICTION_BPS,
                                'duration_h': dur_h, 'exit': 'structural_invalidation',
                                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                            })
                            exited = True
                            break

            cur_high = sub_highs[i]
            cur_low = sub_lows[i]
            cur_open = sub_opens[i]

            cur_mfe = (cur_high - p0) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe

            t_1h_cur = t_bar.floor('1h')
            row_cur = df_1h.loc[t_1h_cur] if t_1h_cur in df_1h.index else df_1h.loc[t0]

            std_20 = (row_cur['bb_upper_20h'] - row_cur['bb_mid_20h']) / 2.0
            std_80 = (row_cur['bb_upper_80h'] - row_cur['bb_mid_80h']) / 2.0
            std_240 = (row_cur['bb_upper_240h'] - row_cur['bb_mid_240h']) / 2.0

            # Arming condition: price reclaims parent line
            if not parent_armed and cur_high >= row_cur['bb_mid_240h'] - 0.5 * std_240:
                parent_armed = True

            if parent_armed:
                # Directive 3: Dynamic Overhead Resistance Constraint
                is_overhead_blocked = (row_cur['bb_mid_240h'] < row_cur['bb_mid_480h']) and (row_cur['bb_slope_480h'] < 0) and (row_cur['close'] < row_cur['bb_mid_480h'])
                afs_peak = (row_cur['afs_7'] < row_cur['afs_9'])

                if enable_overhead_resistance_adaptation and is_overhead_blocked:
                    # Constrained by overhead descending parent line (Mean Reversion mode)
                    hit_overhead_res = (cur_high >= row_cur['bb_mid_240h'] or cur_high >= row_cur['bb_upper_80h'])
                    if hit_overhead_res and afs_peak:
                        cand_stop = row_cur['bb_mid_20h'] - 0.5 * std_20
                    else:
                        cand_stop = row_cur['bb_mid_80h'] - 0.5 * std_80
                else:
                    # Vacuum open (Trend riding mode, e.g. 2023 breakout)
                    if cur_high >= row_cur['bb_upper_240h']:
                        reached_env_240 = True

                    if reached_env_240 and afs_peak:
                        cand_stop = row_cur['bb_mid_80h'] - 0.5 * std_80
                    else:
                        cand_stop = row_cur['bb_mid_240h'] - 0.5 * std_240

                if cand_stop < cur_low:
                    trail_stop = max(trail_stop, cand_stop)

            effective_stop = max(base_stop, trail_stop)

            # Direct stop hit verification without if i > 0
            if cur_low <= effective_stop:
                dur_h = float(np.round(elapsed_h, 2))
                p_exit = min(cur_open, effective_stop)
                exit_type = 'struct_exit' if effective_stop == trail_stop else 'stop_hit'
                trades.append({
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_bar, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': exit_type,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                })
                exited = True
                break

        if not exited:
            dur_h = float(np.round((sub_times[-1] - entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (sub_closes[-1] - p0)/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
            })

    return trades

# ==============================================================================
# Main Orchestration & Verification Pipeline
# ==============================================================================
def main():
    t_start = time.time()
    print("=" * 80)
    print("Starting EXP-111 Execution: Short Dynamic Trailing & Macro Bear Adaptation")
    print("=" * 80)

    # Output directory setup
    exp_dir = os.path.dirname(os.path.abspath(__file__))
    plots_dir = os.path.join(exp_dir, 'plots')
    metrics_path = os.path.join(exp_dir, 'metrics.json')
    os.makedirs(plots_dir, exist_ok=True)

    # --- Step 1: Load Data & Precompute Signals ---
    print("\n--- Step 1: Loading Data & Indicators ---")
    df_1h, df_1m, long_events, events_short_master, sig_plunge_macro = load_data_and_features()

    print(f"Overhead Blocked Proportion (2022): {df_1h.loc['2022']['is_overhead_blocked'].mean()*100:.1f}%")
    print(f"Overhead Blocked Proportion (2023): {df_1h.loc['2023']['is_overhead_blocked'].mean()*100:.1f}%")
    print(f"Short Entry Candidates: Pullback/Propagation={len(events_short_master)}, Plunge={len(df_1h.index[sig_plunge_macro])}")
    print(f"Long Entry Candidates: {len(long_events)}")

    # Plunge short dynamic trade execution
    trades_plunge_dyn = simulate_plunge_short_dynamic(sig_plunge_macro, df_1h, df_1m)

    # --- Step 2: Simulate Longs and Shorts Across Ablations ---
    print("\n--- Step 2: Simulating Longs & Shorts ---")

    # 1. Longs Baseline (EXP-109 Master Longs)
    print("  Simulating EXP-109 Baseline Longs...")
    trades_long_exp109 = exp109.simulate_regime_adaptive_long(
        long_events, df_1h, df_1m,
        regime_mode='adaptive',
        enable_squeeze_4h_mid_esc=True
    )

    # 2. Longs Macro-Bear Adapted (EXP-111 Master Longs: with Dynamic Overhead Resistance adaptation)
    print("  Simulating EXP-111 Master Longs (Overhead Resistance Constraint)...")
    trades_long_mb_adapted = simulate_adaptive_long(
        long_events, df_1h, df_1m,
        enable_overhead_resistance_adaptation=True
    )

    # 3. Shorts Baseline (EXP-109 Shorts with 72h fixed timer)
    print("  Simulating EXP-109 Baseline Shorts...")
    trades_short_exp109_sym = exp95.simulate_1m_path_short(events_short_master, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0)
    for t in trades_short_exp109_sym:
        t['side'] = 'short'
        t['direction'] = 'short'
    trades_plunge_exp109 = exp103.simulate_plunge_short(sig_plunge_macro, df_1h, df_1m, target_sma_col='sma_6765', stop_atr=2.5)
    for t in trades_plunge_exp109:
        t['side'] = 'short'
        t['direction'] = 'short'
    trades_short_exp109_all = sorted(trades_short_exp109_sym + trades_plunge_exp109, key=lambda x: x['entry_time'])

    # 4. Shorts HYP-111-1 (Uniform Intermediate, bb_mid_80h, Zero 72h)
    print("  Simulating HYP-111-1 Shorts (Uniform Intermediate)...")
    trades_short_hyp111_1_sym = simulate_dynamic_short(
        events_short_master, df_1h, df_1m,
        struct_mode='uniform_intermediate'
    )
    trades_short_hyp111_1_all = sorted(trades_short_hyp111_1_sym + trades_plunge_dyn, key=lambda x: x['entry_time'])

    # 5. Shorts HYP-111-2 & Master (Multi-Scale Shift, Zero 72h)
    print("  Simulating EXP-111 Master Shorts (Multi-Scale Shift)...")
    trades_short_master_sym = simulate_dynamic_short(
        events_short_master, df_1h, df_1m,
        struct_mode='regime_adaptive'
    )
    trades_short_master_all = sorted(trades_short_master_sym + trades_plunge_dyn, key=lambda x: x['entry_time'])

    # Assert genuine positive duration and causal validity on all trades (Directive 1)
    assert all(t['duration_h'] > 0 for t in trades_short_master_all), "Error: Non-positive duration short trade detected!"
    assert all(t['exit_time'] > t['entry_time'] for t in trades_short_master_all), "Error: Short exit_time <= entry_time detected!"
    assert all(t['duration_h'] > 0 for t in trades_long_mb_adapted), "Error: Non-positive duration long trade detected!"
    assert all(t['exit_time'] > t['entry_time'] for t in trades_long_mb_adapted), "Error: Long exit_time <= entry_time detected!"

    # Assert 100% elimination of 72h fixed timer in short trades
    assert not any(t.get('exit') == 'timeout_72h' for t in trades_short_master_all), "Error: 72h fixed timeout present in Master Shorts!"

    print("All duration and causal checks passed: 0 trades with duration <= 0; 0 trades with exit_time <= entry_time; 0 trades with 72h timeout.")

    # --- Step 3: Compose Combined Portfolios & Metrics ---
    print("\n--- Step 3: Computing Portfolio Metrics ---")

    # Baseline EXP-109
    port_exp109 = sorted(trades_long_exp109 + trades_short_exp109_all, key=lambda x: x['entry_time'])
    m_exp109 = compute_metrics(port_exp109)
    ym_exp109 = compute_yearly_metrics(port_exp109)

    # Ablation 1: Short Uniform Intermediate (No 72h) + EXP-109 Longs
    port_ab1 = sorted(trades_long_exp109 + trades_short_hyp111_1_all, key=lambda x: x['entry_time'])
    m_ab1 = compute_metrics(port_ab1)
    ym_ab1 = compute_yearly_metrics(port_ab1)

    # Ablation 2: Short Regime Adaptive (Zero 72h) + EXP-109 Longs
    port_ab2 = sorted(trades_long_exp109 + trades_short_master_all, key=lambda x: x['entry_time'])
    m_ab2 = compute_metrics(port_ab2)
    ym_ab2 = compute_yearly_metrics(port_ab2)

    # Ablation 3: EXP-109 Shorts (with 72h) + Macro-Bear Adapted Longs
    port_ab3 = sorted(trades_long_mb_adapted + trades_short_exp109_all, key=lambda x: x['entry_time'])
    m_ab3 = compute_metrics(port_ab3)
    ym_ab3 = compute_yearly_metrics(port_ab3)

    # Master: EXP-111 Master Mode A (All Trades)
    port_master_a = sorted(trades_long_mb_adapted + trades_short_master_all, key=lambda x: x['entry_time'])
    assert all(t['duration_h'] > 0 for t in port_master_a), "Error: Non-positive duration detected in Master Mode A!"
    assert all(t['exit_time'] > t['entry_time'] for t in port_master_a), "Error: exit_time <= entry_time detected in Master Mode A!"
    m_master_a = compute_metrics(port_master_a)
    ym_master_a = compute_yearly_metrics(port_master_a)
    ci_master_a = bootstrap_ci(port_master_a)

    # Master: EXP-111 Master Mode B (Max Concurrent 2)
    port_master_b = apply_mode_b_concurrency_limit(port_master_a, max_concurrent=2)
    m_master_b = compute_metrics(port_master_b)
    ym_master_b = compute_yearly_metrics(port_master_b)
    ci_master_b = bootstrap_ci(port_master_b)

    # Shorts standalone stats
    m_shorts_exp109 = compute_metrics(trades_short_exp109_all)
    ym_shorts_exp109 = compute_yearly_metrics(trades_short_exp109_all)

    m_shorts_master = compute_metrics(trades_short_master_all)
    ym_shorts_master = compute_yearly_metrics(trades_short_master_all)

    # Longs standalone stats
    m_longs_exp109 = compute_metrics(trades_long_exp109)
    ym_longs_exp109 = compute_yearly_metrics(trades_long_exp109)

    m_longs_master = compute_metrics(trades_long_mb_adapted)
    ym_longs_master = compute_yearly_metrics(trades_long_mb_adapted)

    print("\n" + "=" * 70)
    print(f"EXP-109 Baseline: N={m_exp109['executed_trades']}, EV={m_exp109['net_mean_return_pct']:+.2f}%, PF={m_exp109['profit_factor']:.2f}, Tot={m_exp109['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_exp109['max_drawdown_pct']:.2f}%")
    print(f"Ablation 1 (Shorts Uniform 4H Mid): EV={m_ab1['net_mean_return_pct']:+.2f}%, PF={m_ab1['profit_factor']:.2f}, Tot={m_ab1['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_ab1['max_drawdown_pct']:.2f}%")
    print(f"Ablation 2 (Shorts Regime-Adaptive): EV={m_ab2['net_mean_return_pct']:+.2f}%, PF={m_ab2['profit_factor']:.2f}, Tot={m_ab2['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_ab2['max_drawdown_pct']:.2f}%")
    print(f"Ablation 3 (Longs Macro-Bear Adapted): EV={m_ab3['net_mean_return_pct']:+.2f}%, PF={m_ab3['profit_factor']:.2f}, Tot={m_ab3['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_ab3['max_drawdown_pct']:.2f}%")
    print(f"EXP-111 Master Mode A: N={m_master_a['executed_trades']}, EV={m_master_a['net_mean_return_pct']:+.2f}%, PF={m_master_a['profit_factor']:.2f}, Tot={m_master_a['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_master_a['max_drawdown_pct']:.2f}%")
    print(f"EXP-111 Master Mode B: N={m_master_b['executed_trades']}, EV={m_master_b['net_mean_return_pct']:+.2f}%, PF={m_master_b['profit_factor']:.2f}, Tot={m_master_b['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_master_b['max_drawdown_pct']:.2f}%")
    print("=" * 70)

    print("\nYearly Breakdown Comparison:")
    for y in [2020, 2021, 2022, 2023, 2024, 2025]:
        p109 = ym_exp109[str(y)]['total_opportunity_net_return_pct']
        p111_a = ym_master_a[str(y)]['total_opportunity_net_return_pct']
        p111_b = ym_master_b[str(y)]['total_opportunity_net_return_pct']
        pf_a = ym_master_a[str(y)]['profit_factor']
        print(f"  {y}: EXP-109={p109:+.2f}% -> EXP-111 Mode A={p111_a:+.2f}% (PF {pf_a:.2f}) | Mode B={p111_b:+.2f}%")

    # --- Step 4: Generate Publication-Grade Plots ---
    print("\n--- Step 4: Generating Publication-Grade Plots ---")

    # Plot 1: Short Trailing Architecture Comparison
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    dur_109 = [t['duration_h'] for t in trades_short_exp109_all]
    dur_master = [t['duration_h'] for t in trades_short_master_all]

    axes[0].boxplot([dur_109, dur_master], tick_labels=['EXP-109 (72h Cap)', 'EXP-111 (Scale Shift)'], patch_artist=True,
                    boxprops=dict(facecolor='#93c5fd', color='#1d4ed8'),
                    medianprops=dict(color='#b91c1c', linewidth=2))
    axes[0].set_title('Short Holding Duration Distribution (Hours)', fontsize=12, fontweight='bold')
    axes[0].set_ylabel('Duration (Hours)', fontsize=11)
    axes[0].grid(True, linestyle=':', alpha=0.6)

    cum_s109 = np.cumsum([t['net_ret'] * 100.0 for t in trades_short_exp109_all])
    cum_s_ab1 = np.cumsum([t['net_ret'] * 100.0 for t in trades_short_hyp111_1_all])
    cum_s_master = np.cumsum([t['net_ret'] * 100.0 for t in trades_short_master_all])
    t_s_master = [t['exit_time'] for t in trades_short_master_all]
    t_s_109 = [t['exit_time'] for t in trades_short_exp109_all]
    t_s_ab1 = [t['exit_time'] for t in trades_short_hyp111_1_all]

    axes[1].plot(t_s_109, cum_s109, label=f"EXP-109 (72h Fixed) [Tot {cum_s109[-1]:+.1f}%, PF {m_shorts_exp109['profit_factor']:.2f}]", color='#94a3b8', linestyle='--', linewidth=1.5)
    axes[1].plot(t_s_ab1, cum_s_ab1, label=f"HYP-111-1 (Uniform 4H Mid) [Tot {cum_s_ab1[-1]:+.1f}%]", color='#3b82f6', linestyle='-.', linewidth=1.5)
    axes[1].plot(t_s_master, cum_s_master, label=f"EXP-111 Master (Scale Shift) [Tot {cum_s_master[-1]:+.1f}%, PF {m_shorts_master['profit_factor']:.2f}]", color='#10b981', linewidth=2.2)
    axes[1].set_title('Cumulative Net Return: Shorts Standalone (%)', fontsize=12, fontweight='bold')
    axes[1].set_ylabel('Net Return (%)', fontsize=11)
    axes[1].grid(True, linestyle=':', alpha=0.6)
    axes[1].legend(fontsize=9)

    years = [2020, 2021, 2022, 2023, 2024, 2025]
    x_pos = np.arange(len(years))
    w = 0.35
    s109_y = [ym_shorts_exp109[str(y)]['total_opportunity_net_return_pct'] for y in years]
    smast_y = [ym_shorts_master[str(y)]['total_opportunity_net_return_pct'] for y in years]

    axes[2].bar(x_pos - w/2, s109_y, w, label='EXP-109 Baseline', color='#94a3b8', edgecolor='black')
    axes[2].bar(x_pos + w/2, smast_y, w, label='EXP-111 Scale Shift', color='#10b981', edgecolor='black')
    axes[2].set_xticks(x_pos)
    axes[2].set_xticklabels(years)
    axes[2].set_title('Yearly Net Return: Shorts Standalone (%)', fontsize=12, fontweight='bold')
    axes[2].set_ylabel('Net Return (%)', fontsize=11)
    axes[2].grid(True, linestyle=':', alpha=0.6)
    axes[2].legend(fontsize=9)
    for i in range(len(years)):
        axes[2].text(x_pos[i] - w/2, s109_y[i] + (1.5 if s109_y[i] >= 0 else -4.0), f"{s109_y[i]:+.1f}%", ha='center', fontsize=8)
        axes[2].text(x_pos[i] + w/2, smast_y[i] + (1.5 if smast_y[i] >= 0 else -4.0), f"{smast_y[i]:+.1f}%", ha='center', fontsize=8, fontweight='bold')

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'short_trailing_architecture_comparison.png'), dpi=300)
    plt.close()
    print("Saved plots/short_trailing_architecture_comparison.png")

    # Plot 2: Macro Bear Long Adaptation Profile
    fig, axes = plt.subplots(1, 2, figsize=(16, 5))

    trades_long_22_109 = [t for t in trades_long_exp109 if t['entry_time'].year == 2022]
    trades_long_22_master = [t for t in trades_long_mb_adapted if t['entry_time'].year == 2022]

    cum_l22_109 = np.cumsum([t['net_ret'] * 100.0 for t in trades_long_22_109])
    cum_l22_master = np.cumsum([t['net_ret'] * 100.0 for t in trades_long_22_master])
    t_l22_109 = [t['exit_time'] for t in trades_long_22_109]
    t_l22_master = [t['exit_time'] for t in trades_long_22_master]

    axes[0].plot(t_l22_109, cum_l22_109, label=f"EXP-109 Baseline [Tot {cum_l22_109[-1]:+.1f}%]", color='#ef4444', linestyle='--', linewidth=1.8, marker='o')
    axes[0].plot(t_l22_master, cum_l22_master, label=f"EXP-111 Overhead Resistance Constraint [Tot {cum_l22_master[-1]:+.1f}%]", color='#3b82f6', linewidth=2.2, marker='s')
    axes[0].set_title('2022 Bear Market Long Cumulative Net Return (%)', fontsize=12, fontweight='bold')
    axes[0].set_ylabel('Net Return (%)', fontsize=11)
    axes[0].grid(True, linestyle=':', alpha=0.6)
    axes[0].legend(fontsize=10)

    p22_109 = ym_exp109['2022']['total_opportunity_net_return_pct']
    p22_master = ym_master_a['2022']['total_opportunity_net_return_pct']
    dd22_109 = ym_exp109['2022']['max_drawdown_pct']
    dd22_master = ym_master_a['2022']['max_drawdown_pct']

    bar_cats = ['2022 Total Return (%)', '2022 Max Drawdown (%)']
    x_b = np.arange(len(bar_cats))
    w_b = 0.35
    v_109 = [p22_109, dd22_109]
    v_mast = [p22_master, dd22_master]

    axes[1].bar(x_b - w_b/2, v_109, w_b, label=f'EXP-109 (+{p22_109:.1f}%, DD {dd22_109:.1f}%)', color='#94a3b8', edgecolor='black')
    axes[1].bar(x_b + w_b/2, v_mast, w_b, label=f'EXP-111 Master (+{p22_master:.1f}%, DD {dd22_master:.1f}%)', color='#10b981', edgecolor='black')
    axes[1].set_xticks(x_b)
    axes[1].set_xticklabels(bar_cats, fontsize=11)
    axes[1].set_title('2022 Resilience: Return & DD Profile', fontsize=12, fontweight='bold')
    axes[1].grid(True, linestyle=':', alpha=0.6)
    axes[1].legend(fontsize=10)
    for i in range(len(bar_cats)):
        axes[1].text(x_b[i] - w_b/2, v_109[i] + (0.5 if v_109[i] >= 0 else -1.2), f"{v_109[i]:+.1f}%", ha='center', fontsize=10)
        axes[1].text(x_b[i] + w_b/2, v_mast[i] + (0.5 if v_mast[i] >= 0 else -1.2), f"{v_mast[i]:+.1f}%", ha='center', fontsize=10, fontweight='bold')

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'macro_bear_long_adaptation_profile.png'), dpi=300)
    plt.close()
    print("Saved plots/macro_bear_long_adaptation_profile.png")

    # Plot 3: Equity and Drawdown vs EXP-109
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    times_109 = [t['exit_time'] for t in port_exp109]
    cum_109 = np.cumsum([t['net_ret'] * 100.0 for t in port_exp109])
    dd_109 = cum_109 - np.maximum.accumulate(cum_109)

    times_mast = [t['exit_time'] for t in port_master_a]
    cum_mast = np.cumsum([t['net_ret'] * 100.0 for t in port_master_a])
    dd_mast = cum_mast - np.maximum.accumulate(cum_mast)

    times_mast_b = [t['exit_time'] for t in port_master_b]
    cum_mast_b = np.cumsum([t['net_ret'] * 100.0 for t in port_master_b])
    dd_mast_b = cum_mast_b - np.maximum.accumulate(cum_mast_b)

    # Equity curves
    axes[0].plot(times_109, cum_109, label=f"EXP-109 Baseline [Tot: {m_exp109['total_opportunity_net_return_pct']:+.1f}%, PF: {m_exp109['profit_factor']:.2f}, MaxDD: {m_exp109['max_drawdown_pct']:.1f}%]", color='#94a3b8', linestyle='--', linewidth=1.5)
    axes[0].plot(times_mast_b, cum_mast_b, label=f"EXP-111 Master Mode B (Max Conc 2) [Tot: {m_master_b['total_opportunity_net_return_pct']:+.1f}%, PF: {m_master_b['profit_factor']:.2f}, MaxDD: {m_master_b['max_drawdown_pct']:.1f}%]", color='#3b82f6', linewidth=1.8)
    axes[0].plot(times_mast, cum_mast, label=f"EXP-111 Master Mode A (Unconstrained) [Tot: {m_master_a['total_opportunity_net_return_pct']:+.1f}%, PF: {m_master_a['profit_factor']:.2f}, MaxDD: {m_master_a['max_drawdown_pct']:.1f}%]", color='#10b981', linewidth=2.3)
    axes[0].set_title('Cumulative Opportunity Net Return (%) - Full 2020-2025 Period (Net of 40 bps Friction)', fontsize=13, fontweight='bold')
    axes[0].set_ylabel('Cumulative Net Return (%)', fontsize=11)
    axes[0].grid(True, linestyle=':', alpha=0.6)
    axes[0].legend(loc='upper left', fontsize=10)
    axes[0].axvline(pd.Timestamp(HOLDOUT_START), color='purple', linestyle=':', linewidth=1.5, label='Holdout Boundary (2025-05-01)')

    # Drawdown curves
    axes[1].plot(times_109, dd_109, label='EXP-109 DD', color='#94a3b8', linestyle='--', linewidth=1.2)
    axes[1].plot(times_mast_b, dd_mast_b, label='EXP-111 Mode B DD', color='#3b82f6', linewidth=1.4)
    axes[1].plot(times_mast, dd_mast, label='EXP-111 Master Mode A DD', color='#10b981', linewidth=1.8)
    axes[1].fill_between(times_mast, dd_mast, 0, color='#10b981', alpha=0.15)
    axes[1].set_title('Drawdown Profile (%)', fontsize=11, fontweight='bold')
    axes[1].set_ylabel('Drawdown (%)', fontsize=11)
    axes[1].set_xlabel('Date', fontsize=11)
    axes[1].grid(True, linestyle=':', alpha=0.6)
    axes[1].legend(loc='lower left', fontsize=9)
    axes[1].axvline(pd.Timestamp(HOLDOUT_START), color='purple', linestyle=':', linewidth=1.5)

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'equity_and_drawdown_vs_exp109.png'), dpi=300)
    plt.close()
    print("Saved plots/equity_and_drawdown_vs_exp109.png")

    # Plot 4: Yearly and Mode Breakdown
    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    x = np.arange(len(years))
    width = 0.35

    y_109 = [ym_exp109[str(y)]['total_opportunity_net_return_pct'] for y in years]
    y_111 = [ym_master_a[str(y)]['total_opportunity_net_return_pct'] for y in years]

    axes[0].bar(x - width/2, y_109, width, label='EXP-109 Baseline', color='#94a3b8', edgecolor='black')
    axes[0].bar(x + width/2, y_111, width, label='EXP-111 Master (Mode A)', color='#10b981', edgecolor='black')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(years)
    axes[0].set_title('Yearly Total Net Return: EXP-109 vs EXP-111 (%)', fontsize=12, fontweight='bold')
    axes[0].set_ylabel('Net Return (%)', fontsize=11)
    axes[0].grid(True, linestyle=':', alpha=0.6)
    axes[0].legend()
    for i in range(len(years)):
        axes[0].text(x[i] - width/2, y_109[i] + (2.0 if y_109[i] >= 0 else -6.0), f"{y_109[i]:+.1f}%", ha='center', fontsize=9)
        axes[0].text(x[i] + width/2, y_111[i] + (2.0 if y_111[i] >= 0 else -6.0), f"{y_111[i]:+.1f}%", ha='center', fontsize=9, fontweight='bold')

    # Mode A vs Mode B Yearly Return
    y_111_b = [ym_master_b[str(y)]['total_opportunity_net_return_pct'] for y in years]
    axes[1].bar(x - width/2, y_111, width, label='Mode A (Opportunity)', color='#10b981', edgecolor='black')
    axes[1].bar(x + width/2, y_111_b, width, label='Mode B (Max Concurrent 2)', color='#3b82f6', edgecolor='black')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(years)
    axes[1].set_title('EXP-111 Master: Mode A vs Mode B Yearly Net Return (%)', fontsize=12, fontweight='bold')
    axes[1].set_ylabel('Net Return (%)', fontsize=11)
    axes[1].grid(True, linestyle=':', alpha=0.6)
    axes[1].legend()
    for i in range(len(years)):
        axes[1].text(x[i] - width/2, y_111[i] + (2.0 if y_111[i] >= 0 else -6.0), f"{y_111[i]:+.1f}%", ha='center', fontsize=9)
        axes[1].text(x[i] + width/2, y_111_b[i] + (2.0 if y_111_b[i] >= 0 else -6.0), f"{y_111_b[i]:+.1f}%", ha='center', fontsize=9, fontweight='bold')

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'yearly_and_mode_breakdown.png'), dpi=300)
    plt.close()
    print("Saved plots/yearly_and_mode_breakdown.png")

    # --- Step 5: Output Metrics JSON ---
    print("\n--- Step 5: Output Metrics JSON ---")

    # Breakdown of exit types in Master Shorts & Longs
    short_exit_types = {}
    for t in trades_short_master_all:
        ext = t.get('exit', 'other')
        short_exit_types[ext] = short_exit_types.get(ext, 0) + 1

    long_exit_types = {}
    for t in trades_long_mb_adapted:
        ext = t.get('exit', 'other')
        long_exit_types[ext] = long_exit_types.get(ext, 0) + 1

    metrics_payload = {
        'experiment': 'EXP-111',
        'hypothesis': 'ショート側エグジットの幾何学的脱ドグマ（72h固定枠完全撤廃・親構造線動的トレール）と大局ベア相場ロング適応制御の検証',
        'discovery_period': {
            'start': str(DISCOVERY_START),
            'end': str(HOLDOUT_START - pd.Timedelta(seconds=1))
        },
        'friction_bps': FRICTION_BPS * 10000.0,
        'baseline_exp109': {
            'mode_a': m_exp109,
            'yearly_mode_a': ym_exp109,
            'shorts': m_shorts_exp109,
            'longs': m_longs_exp109
        },
        'ablations': {
            'hyp_111_1_short_no_regime': {
                'portfolio_mode_a': m_ab1,
                'yearly': ym_ab1,
                'shorts': compute_metrics(trades_short_hyp111_1_all)
            },
            'hyp_111_2_short_regime_adaptive': {
                'portfolio_mode_a': m_ab2,
                'yearly': ym_ab2,
                'shorts': m_shorts_master
            },
            'hyp_111_3_macro_bear_long_only': {
                'portfolio_mode_a': m_ab3,
                'yearly': ym_ab3,
                'longs': m_longs_master
            },
            'hyp_111_4_exp111_master': {
                'mode_a': m_master_a,
                'ci_95_mode_a': ci_master_a,
                'yearly_mode_a': ym_master_a,
                'mode_b_max_concurrent_2': m_master_b,
                'ci_95_mode_b': ci_master_b,
                'yearly_mode_b': ym_master_b,
                'exit_types_short': short_exit_types,
                'exit_types_long': long_exit_types,
                'shorts_standalone': m_shorts_master,
                'longs_standalone': m_longs_master
            }
        },
        'execution_time_sec': float(np.round(time.time() - t_start, 2))
    }

    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics_payload, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to {metrics_path}")

    print("\n" + "=" * 80)
    print("EXP-111 Verification Completed Successfully!")
    print("=" * 80)

if __name__ == '__main__':
    main()
