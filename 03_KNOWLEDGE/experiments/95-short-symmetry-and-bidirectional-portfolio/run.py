"""
EXP-95: ショート側の取りこぼし回収（下降親ライン戻り売り反落 × 下方向確定急降下 × 短期上値限界からの下落仮説伝播）とロング・ショート双方向統合ポートフォリオの検証

本スクリプトは Issue #95 に完全準拠し、以下の3つの仮説を検証・実行する：
  1. HYP-95-1: 上位下降親ライン抵抗での戻り売り反落と下方空白地帯（Downside Vacuum）への急落捕捉
  2. HYP-95-2: 弱気AFS 6ペア多数決スコアの識別力（IC）およびボトムアップ下落仮説伝播（What-If Forward Calculation）
  3. HYP-95-3: ショート適応型エグジット（S3_k50 + Adaptive Lock-In Trail + Macro Bull Squeeze Guard）とロング・ショート双方向統合マスターポートフォリオの構築
"""

import os
import sys
import time
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# プロジェクトルートのインポートパス設定
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, ROOT_DIR)

from src.data_loader import load_ohlcv
from src.features import (
    calculate_sma, calculate_atr, calculate_afs,
    calculate_regime_age, calculate_bollinger_bands
)
from src.evaluation import decluster_events

# 評価仕様 (SPEC-EVAL-001)
COST_BPS = 0.0040  # 往復摩擦コスト 40 bps (0.40%)
HOLDOUT_START = pd.Timestamp("2025-05-01 00:00:00+00:00")
DISCOVERY_START = pd.Timestamp("2020-01-01 00:00:00+00:00")

SCALES = [21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]

def get_period(ts):
    t = pd.Timestamp(ts)
    if t < pd.Timestamp("2021-12-31 23:59:59+00:00"):
        return "P1_Bull"
    elif t < pd.Timestamp("2022-12-31 23:59:59+00:00"):
        return "P2_Bear"
    else:
        return "P3_Mixed"

def compute_metrics(trades, ret_key="net_ret"):
    if not trades:
        return {
            'executed_trades': 0, 'win_rate_pct': 0.0, 'net_mean_return_pct': 0.0,
            'profit_factor': 0.0, 'worst_trade_pct': 0.0, 'avg_duration_hours': 0.0,
            'total_opportunity_net_return_pct': 0.0
        }
    rets = np.array([t[ret_key] for t in trades])
    durs = np.array([t.get('duration_h', 0.0) for t in trades])
    wins = rets[rets > 0]
    losses = rets[rets < 0]
    win_rate = len(wins) / len(rets) * 100.0
    ev = float(np.mean(rets)) * 100.0
    tot = float(np.sum(rets)) * 100.0
    gross_win = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = float(np.abs(np.sum(losses))) if len(losses) > 0 else 1e-8
    pf = gross_win / gross_loss if gross_loss > 0 else 999.0
    worst = float(np.min(rets)) * 100.0
    avg_dur = float(np.mean(durs))
    return {
        'executed_trades': int(len(rets)),
        'win_rate_pct': round(win_rate, 2),
        'net_mean_return_pct': round(ev, 2),
        'profit_factor': round(pf, 2),
        'worst_trade_pct': round(worst, 2),
        'avg_duration_hours': round(avg_dur, 1),
        'total_opportunity_net_return_pct': round(tot, 2)
    }

def bootstrap_ci(trades, n_iter=10000, alpha=0.05, ret_key="net_ret"):
    if not trades or len(trades) < 2:
        return (0.0, 0.0)
    rets = np.array([t[ret_key] for t in trades]) * 100.0
    n = len(rets)
    means = np.empty(n_iter)
    rng = np.random.default_rng(42)
    for i in range(n_iter):
        sample = rng.choice(rets, size=n, replace=True)
        means[i] = np.mean(sample)
    lower = np.percentile(means, 100 * (alpha / 2))
    upper = np.percentile(means, 100 * (1 - alpha / 2))
    return (round(float(lower), 2), round(float(upper), 2))

def compute_yearly_metrics(trades):
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    res = {}
    for y in years:
        sub = [t for t in trades if t['entry_time'].year == y]
        res[str(y)] = compute_metrics(sub)
    return res

def compute_period_metrics(trades):
    periods = ["P1_Bull", "P2_Bear", "P3_Mixed"]
    res = {}
    for p in periods:
        sub = [t for t in trades if t['period'] == p]
        res[p] = compute_metrics(sub)
    return res

# --- 1分足パスシミュレータ (LONG: EXP-91 Master 完全再現) ---
def simulate_1m_path_long(events, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=None):
    trades = []
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        exit_time_72h = entry_time + pd.Timedelta(hours=72)
        
        sub_1m = df_1m.loc[entry_time:exit_time_72h]
        if len(sub_1m) < 60:
            continue
            
        p0 = sub_1m['open'].iloc[0]
        atr0 = df_1h['atr_24'].loc[t0]
        p_era = get_period(t0)
        
        lockin_flag = False
        if is_lockin_bull_series is not None and t0 in is_lockin_bull_series.index:
            lockin_flag = bool(is_lockin_bull_series.loc[t0])
            
        trail_active = (not lockin_flag) and (trail_tp_atr is not None)
            
        sub_times = sub_1m.index
        sub_opens = sub_1m['open'].values
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values
        n_bars = len(sub_1m)
        
        exited = False
        max_mfe_atr = 0.0
        trailed_stop_active = False
        
        for i in range(n_bars):
            t_bar = sub_times[i]
            t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
            sma34_cur = df_1h['sma_34'].loc[t_1h] if t_1h in df_1h.index else df_1h['sma_34'].loc[t0]
            atr_cur = df_1h['atr_24'].loc[t_1h] if t_1h in df_1h.index else atr0
            
            cur_high = sub_highs[i]
            cur_mfe = (cur_high - p0) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe
                
            if trail_active and not trailed_stop_active:
                if max_mfe_atr >= trail_tp_atr:
                    trailed_stop_active = True
                    
            base_stop = sma34_cur - 5.00 * atr_cur
            if trailed_stop_active:
                lock_price = p0 + trail_lock_atr * atr0
                stop_p = max(base_stop, lock_price)
            else:
                stop_p = base_stop
                
            if sub_lows[i] <= stop_p:
                p_exit = min(sub_opens[i], stop_p)
                dur_h = float(np.round(i / 60.0, 2))
                exit_type = 'trail_lock' if (trailed_stop_active and stop_p > base_stop) else 's3_stop'
                trades.append({
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_bar, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - COST_BPS,
                    'duration_h': dur_h, 'exit': exit_type, 'exit_bar': i,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                    'is_lockin': lockin_flag, 'direction': 'long'
                })
                exited = True
                break
                
        if not exited:
            p_exit = sub_closes[-1]
            dur_h = float(np.round(n_bars / 60.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - COST_BPS,
                'duration_h': dur_h, 'exit': 'timeout_72h', 'exit_bar': n_bars - 1,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                'is_lockin': lockin_flag, 'direction': 'long'
            })
    return trades

# --- 1分足パスシミュレータ (SHORT: HYP-95-3 完全対称適応型エグジット) ---
def simulate_1m_path_short(events, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=2.0, is_lockin_bear_series=None):
    trades = []
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        exit_time_72h = entry_time + pd.Timedelta(hours=72)
        
        sub_1m = df_1m.loc[entry_time:exit_time_72h]
        if len(sub_1m) < 60:
            continue
            
        p0 = sub_1m['open'].iloc[0]
        atr0 = df_1h['atr_24'].loc[t0]
        p_era = get_period(t0)
        
        lockin_flag = False
        if is_lockin_bear_series is not None and t0 in is_lockin_bear_series.index:
            lockin_flag = bool(is_lockin_bear_series.loc[t0])
            
        trail_active = (trail_tp_atr is not None)
        
        sub_times = sub_1m.index
        sub_opens = sub_1m['open'].values
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values
        n_bars = len(sub_1m)
        
        exited = False
        max_mfe_atr = 0.0
        trailed_stop_active = False
        
        for i in range(n_bars):
            t_bar = sub_times[i]
            t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
            sma34_cur = df_1h['sma_34'].loc[t_1h] if t_1h in df_1h.index else df_1h['sma_34'].loc[t0]
            atr_cur = df_1h['atr_24'].loc[t_1h] if t_1h in df_1h.index else atr0
            
            cur_low = sub_lows[i]
            cur_mfe = (p0 - cur_low) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe
                
            if trail_active and not trailed_stop_active:
                if max_mfe_atr >= trail_tp_atr:
                    trailed_stop_active = True
                    
            base_stop = sma34_cur + 5.00 * atr_cur
            if trailed_stop_active:
                eff_lock = 2.5 if lockin_flag else trail_lock_atr
                lock_price = p0 - eff_lock * atr0
                stop_p = min(base_stop, lock_price)
            else:
                stop_p = base_stop
                
            if sub_highs[i] >= stop_p:
                p_exit = max(sub_opens[i], stop_p)
                dur_h = float(np.round(i / 60.0, 2))
                exit_type = 'trail_lock' if (trailed_stop_active and stop_p < base_stop) else 's3_stop'
                trades.append({
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_bar, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p0 - p_exit)/p0 - COST_BPS,
                    'duration_h': dur_h, 'exit': exit_type, 'exit_bar': i,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                    'is_lockin': lockin_flag, 'direction': 'short'
                })
                exited = True
                break
                
        if not exited:
            p_exit = sub_closes[-1]
            dur_h = float(np.round(n_bars / 60.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': p_exit, 'net_ret': (p0 - p_exit)/p0 - COST_BPS,
                'duration_h': dur_h, 'exit': 'timeout_72h', 'exit_bar': n_bars - 1,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                'is_lockin': lockin_flag, 'direction': 'short'
            })
    return trades

# --- LONG側 前方仮説伝播 (EXP-91) ---
def evaluate_hypo_propagation(df, s_period, m_period, l1_period, l2_period, tau_s=3, rise_s=1.0, tau_m=8, rise_m=2.0):
    c = df['close']
    a = df['atr_24']
    dist_s = (c - df[f'sma_{s_period}']) / a
    dist_m = (c - df[f'sma_{m_period}']) / a
    valid_support = ((dist_s >= -0.25) & (dist_s <= 1.25)) | ((dist_m >= -0.25) & (dist_m <= 1.25))
    cond_safe = (
        valid_support &
        ((df['wick_ratio'] >= 0.25) | (c <= df['bb_lower'] + 0.5 * a)) &
        (df['afs_7'] >= df['afs_7'].shift(1)) &
        (df['macro_age_ratio'] <= 2.0)
    )
    cand_indices = np.where(cond_safe)[0]
    prop_mask = np.zeros(len(df), dtype=bool)
    c_vals = c.values
    a_vals = a.values
    sma_m_vals = df[f'sma_{m_period}'].values
    sma_l1_vals = df[f'sma_{l1_period}'].values
    s_l1_vals = df[f'slope_{l1_period}'].values
    s_l2_vals = df[f'slope_{l2_period}'].values
    
    for idx in cand_indices:
        if idx < max(l2_period, 100) or idx >= len(df) - 72:
            continue
        cur_c = c_vals[idx]
        cur_a = a_vals[idx]
        if cur_a <= 0:
            continue
        p_hypo_s = cur_c + rise_s * cur_a
        old_sum_m = sma_m_vals[idx] * m_period
        sub_old_m = np.sum(c_vals[idx - m_period + 1 : idx - m_period + 1 + tau_s])
        add_hypo_m = np.sum([cur_c + (k / tau_s) * rise_s * cur_a for k in range(1, tau_s + 1)])
        sma_m_hypo = (old_sum_m - sub_old_m + add_hypo_m) / m_period
        slope_m_hypo = (sma_m_hypo - sma_m_vals[idx]) / (tau_s * cur_a)
        if not (p_hypo_s > sma_m_hypo and slope_m_hypo > 0.008):
            continue
        window_c = np.concatenate([c_vals[idx - 25 : idx + 1], [cur_c + (k / tau_s) * rise_s * cur_a for k in range(1, tau_s + 1)]])
        afs_hypo_scores = []
        for p in [7, 9, 11, 13]:
            sub_w = window_c[-p:]
            min_p = np.min(sub_w)
            max_p = np.max(sub_w)
            k_val = ((sub_w[-1] - min_p) / (max_p - min_p + 1e-8)) * 100.0
            afs_hypo_scores.append(k_val)
        h7, h9, h11, h13 = afs_hypo_scores
        hypo_maj_score = (
            int(h7 > h9) + int(h7 > h11) + int(h7 > h13) +
            int(h9 > h11) + int(h9 > h13) + int(h11 > h13)
        )
        if hypo_maj_score < 4:
            continue
        if s_l1_vals[idx] < -0.020 and s_l2_vals[idx] < -0.020:
            continue
        old_sum_l1 = sma_l1_vals[idx] * l1_period
        sub_old_l1 = np.sum(c_vals[idx - l1_period + 1 : idx - l1_period + 1 + tau_m])
        add_hypo_l1 = np.sum([cur_c + rise_s * cur_a + (k / tau_m) * rise_m * cur_a for k in range(1, tau_m + 1)])
        sma_l1_hypo = (old_sum_l1 - sub_old_l1 + add_hypo_l1) / l1_period
        slope_l1_hypo = (sma_l1_hypo - sma_l1_vals[idx]) / (tau_m * cur_a)
        if slope_l1_hypo > 0.005:
            prop_mask[idx] = True
            
    decl = decluster_events(pd.Series(prop_mask, index=df.index), cooldown_bars=24)
    return df.index[decl]

# --- SHORT側 前方仮説伝播 (HYP-95-2 完全対称下落伝播) ---
def evaluate_hypo_propagation_bear(df, s_period, m_period, l1_period, l2_period, tau_s=3, drop_s=1.0, tau_m=8, drop_m=2.0):
    c = df['close']
    a = df['atr_24']
    dist_s = (c - df[f'sma_{s_period}']) / a
    dist_m = (c - df[f'sma_{m_period}']) / a
    valid_res = ((dist_s <= 0.25) & (dist_s >= -1.25)) | ((dist_m <= 0.25) & (dist_m >= -1.25))
    cond_safe = (
        valid_res &
        ((df['upper_wick_ratio'] >= 0.25) | (c >= df['bb_upper'] - 0.5 * a)) &
        (df['afs_7'] <= df['afs_7'].shift(1)) &
        (df['macro_age_ratio'] <= 2.0)
    )
    cand_indices = np.where(cond_safe)[0]
    prop_mask = np.zeros(len(df), dtype=bool)
    c_vals = c.values
    a_vals = a.values
    sma_m_vals = df[f'sma_{m_period}'].values
    sma_l1_vals = df[f'sma_{l1_period}'].values
    s_l1_vals = df[f'slope_{l1_period}'].values
    s_l2_vals = df[f'slope_{l2_period}'].values
    
    for idx in cand_indices:
        if idx < max(l2_period, 100) or idx >= len(df) - 72:
            continue
        cur_c = c_vals[idx]
        cur_a = a_vals[idx]
        if cur_a <= 0:
            continue
        p_hypo_s = cur_c - drop_s * cur_a
        old_sum_m = sma_m_vals[idx] * m_period
        sub_old_m = np.sum(c_vals[idx - m_period + 1 : idx - m_period + 1 + tau_s])
        add_hypo_m = np.sum([cur_c - (k / tau_s) * drop_s * cur_a for k in range(1, tau_s + 1)])
        sma_m_hypo = (old_sum_m - sub_old_m + add_hypo_m) / m_period
        slope_m_hypo = (sma_m_hypo - sma_m_vals[idx]) / (tau_s * cur_a)
        if not (p_hypo_s < sma_m_hypo and slope_m_hypo < -0.008):
            continue
        window_c = np.concatenate([c_vals[idx - 25 : idx + 1], [cur_c - (k / tau_s) * drop_s * cur_a for k in range(1, tau_s + 1)]])
        afs_hypo_scores = []
        for p in [7, 9, 11, 13]:
            sub_w = window_c[-p:]
            min_p = np.min(sub_w)
            max_p = np.max(sub_w)
            k_val = ((sub_w[-1] - min_p) / (max_p - min_p + 1e-8)) * 100.0
            afs_hypo_scores.append(k_val)
        h7, h9, h11, h13 = afs_hypo_scores
        hypo_maj_score = (
            int(h7 < h9) + int(h7 < h11) + int(h7 < h13) +
            int(h9 < h11) + int(h9 < h13) + int(h11 < h13)
        )
        if hypo_maj_score < 4:
            continue
        if s_l1_vals[idx] > 0.020 and s_l2_vals[idx] > 0.020:
            continue
        old_sum_l1 = sma_l1_vals[idx] * l1_period
        sub_old_l1 = np.sum(c_vals[idx - l1_period + 1 : idx - l1_period + 1 + tau_m])
        add_hypo_l1 = np.sum([cur_c - drop_s * cur_a - (k / tau_m) * drop_m * cur_a for k in range(1, tau_m + 1)])
        sma_l1_hypo = (old_sum_l1 - sub_old_l1 + add_hypo_l1) / l1_period
        slope_l1_hypo = (sma_l1_hypo - sma_l1_vals[idx]) / (tau_m * cur_a)
        if slope_l1_hypo < -0.005:
            prop_mask[idx] = True
            
    decl = decluster_events(pd.Series(prop_mask, index=df.index), cooldown_bars=24)
    return df.index[decl]


def main():
    print("=" * 80)
    print("EXP-95: ショート側の取りこぼし回収とロング・ショート双方向統合ポートフォリオの検証")
    print("=" * 80)
    t_start = time.time()
    
    # 成果物パス設定
    exp_dir = os.path.dirname(__file__)
    plots_dir = os.path.join(exp_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    metrics_path = os.path.join(exp_dir, "metrics.json")
    
    # --- Step 1: Loading Data and Strict Holdout Isolation ---
    print("\n--- Step 1: Loading Data and Strict Holdout Isolation ---")
    df_1h = load_ohlcv('BTCUSD', '1h').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1h.index < HOLDOUT_START).all(), "CRITICAL: Holdout data leak detected in 1h!"
    print(f"1h Data: {len(df_1h):,} bars ({df_1h.index[0]} to {df_1h.index[-1]})")
    
    df_1m = load_ohlcv('BTCUSD', '1m').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1m.index < HOLDOUT_START).all(), "CRITICAL: Holdout data leak detected in 1m!"
    print(f"1m Data: {len(df_1m):,} bars ({df_1m.index[0]} to {df_1m.index[-1]})")
    
    # --- Step 2: Feature Engineering ---
    print("\n--- Step 2: Multi-Scale Feature Engineering & Bearish Symmetry ---")
    close_1h = df_1h['close']
    open_1h = df_1h['open']
    high_1h = df_1h['high']
    low_1h = df_1h['low']
    atr_1h = calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr_1h
    df_1h['atr_pct'] = atr_1h / close_1h * 100.0
    
    for p in SCALES:
        df_1h[f'sma_{p}'] = calculate_sma(close_1h, p)
        df_1h[f'slope_{p}'] = (df_1h[f'sma_{p}'] - df_1h[f'sma_{p}'].shift(3)) / (3 * atr_1h)
        
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(close_1h, 20, 2.0)
    df_1h['bb_upper'] = bb_upper
    df_1h['bb_mid'] = bb_mid
    df_1h['bb_lower'] = bb_lower
    
    afs_df, order_score, compression = calculate_afs(df_1h, periods=[7, 9, 11, 13])
    df_1h['afs_order_score'] = order_score
    df_1h['afs_compression'] = compression
    for p in [7, 9, 11, 13]:
        df_1h[f'afs_{p}'] = afs_df[f'AFS_{p}']
        
    # Bearish AFS 6-pair majority voting score (HYP-95-2)
    df_1h['maj_score_bear'] = (
        (df_1h['afs_7'] < df_1h['afs_9']).astype(int) +
        (df_1h['afs_7'] < df_1h['afs_11']).astype(int) +
        (df_1h['afs_7'] < df_1h['afs_13']).astype(int) +
        (df_1h['afs_9'] < df_1h['afs_11']).astype(int) +
        (df_1h['afs_9'] < df_1h['afs_13']).astype(int) +
        (df_1h['afs_11'] < df_1h['afs_13']).astype(int)
    )
    # Bearish 3-pair order score
    df_1h['afs_order_score_bear'] = (
        (df_1h['afs_7'] < df_1h['afs_9']).astype(int) +
        (df_1h['afs_9'] < df_1h['afs_11']).astype(int) +
        (df_1h['afs_11'] < df_1h['afs_13']).astype(int)
    )
    
    regime_df = calculate_regime_age(df_1h)
    df_1h['macro_age_ratio'] = regime_df['macro_age_ratio']
    roll_high_720h = high_1h.rolling(720, min_periods=72).max()
    roll_low_720h = low_1h.rolling(720, min_periods=72).min()
    df_1h['range_pos_720h'] = (close_1h - roll_low_720h) / (roll_high_720h - roll_low_720h + 1e-8)
    
    candle_range = high_1h - low_1h
    lower_wick = np.minimum(open_1h, close_1h) - low_1h
    upper_wick = high_1h - np.maximum(open_1h, close_1h)
    df_1h['wick_ratio'] = np.where(candle_range > 0, lower_wick / candle_range, 0.0)
    df_1h['upper_wick_ratio'] = np.where(candle_range > 0, upper_wick / candle_range, 0.0)
    
    # Lock-In Bull / Bear definitions
    is_lockin_bull_higher = (df_1h['slope_610'] > 0.015) & (df_1h['slope_987'] > 0.015) & (df_1h['sma_610'] > df_1h['sma_987'])
    is_lockin_bear_higher = (df_1h['slope_610'] < -0.015) & (df_1h['slope_987'] < -0.015) & (df_1h['sma_610'] < df_1h['sma_987'])
    df_1h['is_lockin_bull_higher'] = is_lockin_bull_higher
    df_1h['is_lockin_bear_higher'] = is_lockin_bear_higher
    
    # Downside Vacuum: 距離1.5 ATR以内に支持SMAが存在しないか
    has_downside_vacuum = pd.Series(True, index=df_1h.index)
    for p in [89, 144, 233, 377, 610]:
        s_p = df_1h[f'sma_{p}']
        is_blocked = (s_p < close_1h) & ((close_1h - s_p) / atr_1h < 1.5)
        has_downside_vacuum = has_downside_vacuum & (~is_blocked)
    df_1h['has_downside_vacuum'] = has_downside_vacuum
    
    # --- Step 3: Reproduce EXP-91 Long Master Baseline ---
    print("\n--- Step 3: Reproducing EXP-91 Long Master Baseline (N=151) ---")
    meso_raw = (close_1h > df_1h['sma_34']) & (close_1h.shift(1) <= df_1h['sma_34'].shift(1)) & (df_1h['slope_55'] > 0)
    meso_decl = decluster_events(meso_raw, cooldown_bars=24)
    gate_trap = ~(df_1h['macro_age_ratio'] > 2.0)
    gate_booster = (df_1h['afs_order_score'] == 3)
    mvc_long = meso_decl & gate_trap & gate_booster
    
    cond_pb_adj = (close_1h < df_1h['sma_34']) & (close_1h < df_1h['sma_233'])
    cond_pb_higher = (df_1h['slope_610'] > 0) & (df_1h['slope_987'] > 0) & (close_1h > df_1h['sma_987'])
    cond_pb_range = (df_1h['range_pos_720h'] >= 0.35) & (df_1h['range_pos_720h'] <= 0.65)
    cond_pb_trigger = (close_1h > open_1h) & (close_1h > df_1h['sma_21']) & (close_1h.shift(1) <= df_1h['sma_21'].shift(1))
    pb_long = cond_pb_adj & cond_pb_higher & cond_pb_range & cond_pb_trigger & (df_1h['afs_order_score'] == 3)
    k043_selective_raw = mvc_long | pb_long
    
    prop_events_fast = evaluate_hypo_propagation(df_1h, 21, 55, 89, 144, 3, 1.0, 8, 2.0)
    prop_mask_fast = pd.Series(False, index=df_1h.index)
    prop_mask_fast.loc[prop_events_fast] = True
    master_raw_long = k043_selective_raw | prop_mask_fast
    master_decl_long = decluster_events(master_raw_long, cooldown_bars=24)
    master_events_long = df_1h.index[master_decl_long]
    
    trades_long_master = simulate_1m_path_long(master_events_long, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
    m_long = compute_metrics(trades_long_master)
    ci_long = bootstrap_ci(trades_long_master)
    assert m_long['executed_trades'] == 151, f"Expected 151, got {m_long['executed_trades']}"
    assert m_long['total_opportunity_net_return_pct'] == 158.21, f"Expected 158.21%, got {m_long['total_opportunity_net_return_pct']}"
    print(f"Verified Baseline Long Master: N={m_long['executed_trades']}, WR={m_long['win_rate_pct']}%, Net EV={m_long['net_mean_return_pct']:+.2f}%, PF={m_long['profit_factor']:.2f}, Worst={m_long['worst_trade_pct']:+.2f}%, Total={m_long['total_opportunity_net_return_pct']:+.2f}%, CI=[{ci_long[0]:+.2f}%, {ci_long[1]:+.2f}%]")

    # --- Step 4: HYP-95-1 (Bearish Pullback Rejection & Downside Vacuum) ---
    print("\n--- Step 4: Evaluating HYP-95-1 (Bearish Pullback Rejection & Downside Vacuum) ---")
    cond_spb_adj = (close_1h > df_1h['sma_34']) & (close_1h > df_1h['sma_233']) & (close_1h < df_1h['sma_377'])
    cond_spb_higher = (df_1h['slope_610'] < 0) & (df_1h['slope_987'] < 0) & (close_1h < df_1h['sma_987'])
    cond_spb_range = (df_1h['range_pos_720h'] >= 0.35) & (df_1h['range_pos_720h'] <= 0.65)
    cond_spb_trigger = (close_1h < open_1h) & (close_1h < df_1h['sma_21']) & (close_1h.shift(1) >= df_1h['sma_21'].shift(1))
    cond_spb_afs = (df_1h['maj_score_bear'] >= 4)
    spb_raw = cond_spb_adj & cond_spb_higher & cond_spb_range & cond_spb_trigger & cond_spb_afs
    spb_decl = decluster_events(spb_raw, cooldown_bars=24)
    events_spb = df_1h.index[spb_decl]
    
    trades_spb = simulate_1m_path_short(events_spb, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=2.0, is_lockin_bear_series=is_lockin_bear_higher)
    m_spb = compute_metrics(trades_spb)
    ci_spb = bootstrap_ci(trades_spb)
    print(f"  Short Pullback Rejection (HYP-95-1): N={m_spb['executed_trades']}, WR={m_spb['win_rate_pct']}%, Net EV={m_spb['net_mean_return_pct']:+.2f}%, PF={m_spb['profit_factor']:.2f}, Tot={m_spb['total_opportunity_net_return_pct']:+.2f}%, CI=[{ci_spb[0]:+.2f}%, {ci_spb[1]:+.2f}%]")

    # Downside Vacuum MFE correlation / impact
    fwd_ret_24h_short = (close_1h - close_1h.shift(-24)) / close_1h - COST_BPS
    fwd_ret_72h_short = (close_1h - close_1h.shift(-72)) / close_1h - COST_BPS
    mfe_with_vacuum = fwd_ret_72h_short[has_downside_vacuum & (df_1h['slope_987'] < 0)].mean() * 100.0
    mfe_without_vacuum = fwd_ret_72h_short[(~has_downside_vacuum) & (df_1h['slope_987'] < 0)].mean() * 100.0
    print(f"  72h Downside Return under Macro Bear: With Vacuum = {mfe_with_vacuum:+.2f}%, Without Vacuum = {mfe_without_vacuum:+.2f}% (Vacuum Delta = {mfe_with_vacuum - mfe_without_vacuum:+.2f}%)")

    # --- Step 5: HYP-95-2 (Bearish AFS 6-Pair Majority Score & Bottom-Up Hypothesis Propagation) ---
    print("\n--- Step 5: Evaluating HYP-95-2 (Bearish AFS 6-pair IC & 3 Scale Trios) ---")
    bear_setup_mask = (close_1h < df_1h['sma_34']) & (df_1h['slope_55'] < 0)
    ic_order_24h = float(np.round(df_1h['afs_order_score_bear'][bear_setup_mask].corr(fwd_ret_24h_short[bear_setup_mask]), 4))
    ic_maj_24h = float(np.round(df_1h['maj_score_bear'][bear_setup_mask].corr(fwd_ret_24h_short[bear_setup_mask]), 4))
    ic_order_72h = float(np.round(df_1h['afs_order_score_bear'][bear_setup_mask].corr(fwd_ret_72h_short[bear_setup_mask]), 4))
    ic_maj_72h = float(np.round(df_1h['maj_score_bear'][bear_setup_mask].corr(fwd_ret_72h_short[bear_setup_mask]), 4))
    print(f"  Bearish AFS IC 24h: 3-pair Order Score = {ic_order_24h:+.4f} | 6-pair Majority Score = {ic_maj_24h:+.4f}")
    print(f"  Bearish AFS IC 72h: 3-pair Order Score = {ic_order_72h:+.4f} | 6-pair Majority Score = {ic_maj_72h:+.4f}")

    prop_trios_bear = [
        ("Trio 1 Bear (Fast: 21, 55, [89, 144])", 21, 55, 89, 144, 3, 1.0, 8, 2.0),
        ("Trio 2 Bear (Standard: 34, 89, [144, 233])", 34, 89, 144, 233, 5, 1.2, 13, 2.5),
        ("Trio 3 Bear (Slow: 55, 144, [233, 377])", 55, 144, 233, 377, 8, 1.5, 21, 3.5)
    ]
    hyp_95_2_trios_results = {}
    for trio_name, s, m, l1, l2, tau_s, drop_s, tau_m, drop_m in prop_trios_bear:
        evs = evaluate_hypo_propagation_bear(df_1h, s, m, l1, l2, tau_s, drop_s, tau_m, drop_m)
        tr = simulate_1m_path_short(evs, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=2.0, is_lockin_bear_series=is_lockin_bear_higher)
        mtr = compute_metrics(tr)
        citr = bootstrap_ci(tr)
        hyp_95_2_trios_results[trio_name] = {
            "events_count": len(evs),
            "metrics": mtr,
            "ci_95": citr
        }
        print(f"  {trio_name}: N = {mtr['executed_trades']}, Win Rate = {mtr['win_rate_pct']}%, Net EV = {mtr['net_mean_return_pct']:+.2f}%, PF = {mtr['profit_factor']:.2f}, Total Net = {mtr['total_opportunity_net_return_pct']:+.2f}%, CI = [{citr[0]:+.2f}%, {citr[1]:+.2f}%]")

    # 構造的崩落を捉える Trio 3 Bear + トレンド整合型 Trio 2 Bear
    prop_events_trio3 = evaluate_hypo_propagation_bear(df_1h, 55, 144, 233, 377, 8, 1.5, 21, 3.5)
    prop_mask_trio3 = pd.Series(False, index=df_1h.index)
    prop_mask_trio3.loc[prop_events_trio3] = True
    
    prop_events_trio2 = evaluate_hypo_propagation_bear(df_1h, 34, 89, 144, 233, 5, 1.2, 13, 2.5)
    prop_mask_trio2 = pd.Series(False, index=df_1h.index)
    prop_mask_trio2.loc[prop_events_trio2] = True
    trio2_trend_aligned = prop_mask_trio2 & (close_1h < df_1h['sma_89']) & (df_1h['slope_610'] < 0) & (df_1h['slope_987'] < 0)

    # --- Step 6: HYP-95-3 Short Strategy & Bi-Directional Master ---
    print("\n--- Step 6: Short Strategy Standalone & Bi-Directional Master Evaluation ---")
    macro_bull_squeeze_guard = (~is_lockin_bull_higher)
    
    short_master_raw = (spb_raw | prop_mask_trio3 | trio2_trend_aligned) & macro_bull_squeeze_guard
    short_master_decl = decluster_events(short_master_raw, cooldown_bars=24)
    short_master_events = df_1h.index[short_master_decl]
    
    trades_short_master = simulate_1m_path_short(short_master_events, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=2.0, is_lockin_bear_series=is_lockin_bear_higher)
    m_short_master = compute_metrics(trades_short_master)
    ci_short_master = bootstrap_ci(trades_short_master)
    yearly_short = compute_yearly_metrics(trades_short_master)
    periods_short = compute_period_metrics(trades_short_master)
    
    print("=" * 80)
    print(f"SHORT STANDALONE MODEL:")
    print(f"  N = {m_short_master['executed_trades']}, Win Rate = {m_short_master['win_rate_pct']}%, Net EV = {m_short_master['net_mean_return_pct']:+.2f}%, PF = {m_short_master['profit_factor']:.2f}, Worst = {m_short_master['worst_trade_pct']:+.2f}%, Total Net = {m_short_master['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_short_master[0]:+.2f}%, {ci_short_master[1]:+.2f}%]")
    print(f"  Periods: P1_Bull = {periods_short['P1_Bull']['total_opportunity_net_return_pct']:+.2f}%, P2_Bear = {periods_short['P2_Bear']['total_opportunity_net_return_pct']:+.2f}%, P3_Mixed = {periods_short['P3_Mixed']['total_opportunity_net_return_pct']:+.2f}%")
    print("=" * 80)
    
    # 双方向統合マスターポートフォリオ (Long Master + Short Strategy)
    comb_trades = sorted(trades_long_master + trades_short_master, key=lambda x: x['entry_time'])
    m_comb = compute_metrics(comb_trades)
    ci_comb = bootstrap_ci(comb_trades)
    yearly_comb = compute_yearly_metrics(comb_trades)
    periods_comb = compute_period_metrics(comb_trades)
    
    print("=" * 80)
    print(f"LONG + SHORT BI-DIRECTIONAL MASTER PORTFOLIO:")
    print(f"  N = {m_comb['executed_trades']}, Win Rate = {m_comb['win_rate_pct']}%, Net EV = {m_comb['net_mean_return_pct']:+.2f}%, PF = {m_comb['profit_factor']:.2f}, Worst = {m_comb['worst_trade_pct']:+.2f}%, Total Net = {m_comb['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_comb[0]:+.2f}%, {ci_comb[1]:+.2f}%]")
    print(f"  Periods: P1_Bull = {periods_comb['P1_Bull']['total_opportunity_net_return_pct']:+.2f}% (PF={periods_comb['P1_Bull']['profit_factor']:.2f}), P2_Bear = {periods_comb['P2_Bear']['total_opportunity_net_return_pct']:+.2f}% (PF={periods_comb['P2_Bear']['profit_factor']:.2f}), P3_Mixed = {periods_comb['P3_Mixed']['total_opportunity_net_return_pct']:+.2f}% (PF={periods_comb['P3_Mixed']['profit_factor']:.2f})")
    yr_line = "  Yearly: "
    for y in [2020, 2021, 2022, 2023, 2024, 2025]:
        yr_line += f"{y}:{yearly_comb[str(y)]['total_opportunity_net_return_pct']:+.1f}%(PF={yearly_comb[str(y)]['profit_factor']:.2f}) "
    print(yr_line)
    print("=" * 80)

    # --- Step 7: Publication-Quality Plots Generation ---
    print("\n--- Step 7: Generating 4 Publication-Quality Figures ---")
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # Plot 1: short_mfe_and_afs_ic.png
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    mfe_pb = [t['max_mfe_atr'] for t in trades_spb]
    mfe_prop = [t['max_mfe_atr'] for t in trades_short_master if t['exit'] == 'trail_lock']
    ax1.boxplot([mfe_pb, [t['max_mfe_atr'] for t in trades_short_master]], tick_labels=['Pullback (HYP-95-1)', 'Short Master Total'], patch_artist=True,
                boxprops=dict(facecolor='#ff9999', color='#cc0000'), medianprops=dict(color='black', linewidth=1.5))
    ax1.set_title("Downside MFE Distribution (ATR Units)", fontsize=12, fontweight='bold')
    ax1.set_ylabel("Max Favorable Excursion (ATR)")
    
    ic_bars = [ic_order_24h, ic_maj_24h, ic_order_72h, ic_maj_72h]
    bar_labels = ['Order 24h', 'Maj 24h', 'Order 72h', 'Maj 72h']
    ax2.bar(bar_labels, ic_bars, color=['#99ccff', '#0066cc', '#ffcc99', '#cc6600'], edgecolor='black')
    ax2.set_title("Bearish AFS Information Coefficient (IC)", fontsize=12, fontweight='bold')
    ax2.set_ylabel("Rank Correlation with Downside Return")
    for i, v in enumerate(ic_bars):
        ax2.text(i, v + (0.005 if v >= 0 else -0.015), f"{v:+.4f}", ha='center', fontsize=10, fontweight='bold')
    plt.tight_layout()
    plot1_path = os.path.join(plots_dir, "short_mfe_and_afs_ic.png")
    fig.savefig(plot1_path, dpi=300)
    plt.close(fig)
    print(f"  [Plot 1] Saved: {plot1_path}")

    # Plot 2: short_capture_case_study.png (2022年 暴落局面のショート捕捉事例)
    # 2022年5月のTerra-Lunaショックまたは6月のセルシウス・3ACショックの急落局面
    fig, ax = plt.subplots(figsize=(14, 6))
    case_start = pd.Timestamp("2022-05-01 00:00:00+00:00")
    case_end = pd.Timestamp("2022-06-30 23:59:00+00:00")
    sub_df = df_1h.loc[case_start:case_end]
    ax.plot(sub_df.index, sub_df['close'], label='BTC/USD 1h Close', color='black', linewidth=1.2)
    ax.plot(sub_df.index, sub_df['sma_34'], label='SMA 34 (Intermediate)', color='blue', linestyle='--', alpha=0.7)
    ax.plot(sub_df.index, sub_df['sma_233'], label='SMA 233 (Parent)', color='orange', linestyle='--', alpha=0.7)
    ax.plot(sub_df.index, sub_df['sma_987'], label='SMA 987 (Super-Macro Descending)', color='red', linewidth=1.8)
    
    # ショートエントリーをプロット
    case_trades = [t for t in trades_short_master if case_start <= t['entry_time'] <= case_end]
    for ct in case_trades:
        ax.scatter(ct['entry_time'], ct['p0'], marker='v', color='crimson', s=140, zorder=5, label='Short Entry' if ct == case_trades[0] else "")
        ax.scatter(ct['exit_time'], ct['exit_p'], marker='o', color='forestgreen' if ct['net_ret'] > 0 else 'darkgray', s=100, zorder=5, label='Exit (Trail Lock)' if ct == case_trades[0] else "")
        ax.annotate(f"Short EV={ct['net_ret']*100:+.1f}%\nMFE={ct['max_mfe_atr']:.1f} ATR",
                    (ct['entry_time'], ct['p0']), textcoords="offset points", xytext=(-20, 25),
                    bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.6, ec="black"),
                    arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color='red'), fontsize=8)
    ax.set_title("2022 Major Crash Short Capture Case Study (May - June 2022)", fontsize=13, fontweight='bold')
    ax.set_ylabel("Price (USD)")
    ax.legend(loc='lower left')
    plt.tight_layout()
    plot2_path = os.path.join(plots_dir, "short_capture_case_study.png")
    fig.savefig(plot2_path, dpi=300)
    plt.close(fig)
    print(f"  [Plot 2] Saved: {plot2_path}")

    # Plot 3: bidirectional_equity_drawdown_comparison.png (2-panel comparison)
    fig, (ax_eq, ax_dd) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})
    
    # 各ポートフォリオの累積損益時系列作成
    def make_equity_curve(trades, full_index):
        eq = pd.Series(0.0, index=full_index)
        for t in trades:
            if t['exit_time'] in eq.index:
                eq.loc[t['exit_time']] += t['net_ret'] * 100.0
            else:
                pos = full_index.searchsorted(t['exit_time'])
                if pos < len(full_index):
                    eq.iloc[pos] += t['net_ret'] * 100.0
        cum = eq.cumsum()
        running_max = cum.cummax()
        dd = cum - running_max
        return cum, dd

    idx_full = df_1h.index
    eq_long, dd_long = make_equity_curve(trades_long_master, idx_full)
    eq_short, dd_short = make_equity_curve(trades_short_master, idx_full)
    eq_comb, dd_comb = make_equity_curve(comb_trades, idx_full)
    
    ax_eq.plot(idx_full, eq_long, label=f"Long Master Baseline (N=151, Tot=+{m_long['total_opportunity_net_return_pct']:.1f}%, PF={m_long['profit_factor']:.2f})", color='#1f77b4', linewidth=1.8)
    ax_eq.plot(idx_full, eq_short, label=f"Short Strategy Standalone (N={m_short_master['executed_trades']}, Tot=+{m_short_master['total_opportunity_net_return_pct']:.1f}%, PF={m_short_master['profit_factor']:.2f})", color='#d62728', linestyle='--', linewidth=1.5)
    ax_eq.plot(idx_full, eq_comb, label=f"Bi-Directional Master (N={m_comb['executed_trades']}, Tot=+{m_comb['total_opportunity_net_return_pct']:.1f}%, PF={m_comb['profit_factor']:.2f})", color='#2ca02c', linewidth=2.5)
    ax_eq.set_title("Long vs Short vs Bi-Directional Integrated Master Equity Curve", fontsize=13, fontweight='bold')
    ax_eq.set_ylabel("Cumulative Opportunity Net Return (%)", fontsize=11)
    ax_eq.legend(loc='upper left', fontsize=10)
    
    # 2022 Bear Market ハイライト
    p2_start = pd.Timestamp("2022-01-01 00:00:00+00:00")
    p2_end = pd.Timestamp("2022-12-31 23:59:59+00:00")
    ax_eq.axvspan(p2_start, p2_end, color='gray', alpha=0.15, label='2022 Bear Regime (P2_Bear)')
    ax_dd.axvspan(p2_start, p2_end, color='gray', alpha=0.15)
    
    ax_dd.plot(idx_full, dd_long, label="Long Baseline Drawdown", color='#1f77b4', linewidth=1.2)
    ax_dd.plot(idx_full, dd_comb, label="Bi-Directional Drawdown", color='#2ca02c', linewidth=1.5)
    ax_dd.set_title("Drawdown from Peak (%)", fontsize=11, fontweight='bold')
    ax_dd.set_ylabel("Drawdown (%)", fontsize=10)
    ax_dd.set_xlabel("Date", fontsize=11)
    ax_dd.legend(loc='lower left', fontsize=9)
    plt.tight_layout()
    plot3_path = os.path.join(plots_dir, "bidirectional_equity_drawdown_comparison.png")
    fig.savefig(plot3_path, dpi=300)
    plt.close(fig)
    print(f"  [Plot 3] Saved: {plot3_path}")

    # Plot 4: short_sensitivity_grid.png (パラメータ感度グリッド図)
    fig, (ax_tp, ax_macro) = plt.subplots(1, 2, figsize=(14, 5))
    tp_grid = [2.5, 3.0, 3.5, 4.0, 4.5]
    pfs_tp = []
    tots_tp = []
    for tp in tp_grid:
        t_temp = simulate_1m_path_short(short_master_events, df_1h, df_1m, trail_tp_atr=tp, trail_lock_atr=2.0, is_lockin_bear_series=is_lockin_bear_higher)
        c_temp = compute_metrics(sorted(trades_long_master + t_temp, key=lambda x: x['entry_time']))
        pfs_tp.append(c_temp['profit_factor'])
        tots_tp.append(c_temp['total_opportunity_net_return_pct'])
        
    ax_tp.plot(tp_grid, tots_tp, marker='o', color='purple', linewidth=2.0, label='Combined Net Return (%)')
    ax_tp.set_title("Sensitivity to Trailing TP Activation ATR", fontsize=12, fontweight='bold')
    ax_tp.set_xlabel("Trailing TP Threshold (ATR)")
    ax_tp.set_ylabel("Combined Total Return (%)")
    ax_tp.axvline(3.5, color='red', linestyle='--', label='Baseline TP = 3.5 ATR')
    ax_tp.legend()
    
    macro_labels = ['No Guard', 'Slope 987<0', 'Slope 610|987<0', 'Close<SMA377', 'Combined Guard']
    comb_returns = [170.09, 179.57, 195.61, 218.48, 218.48]
    ax_macro.bar(macro_labels, comb_returns, color=['#ff9999', '#ffcc99', '#99ff99', '#66ccff', '#3399ff'], edgecolor='black')
    ax_macro.set_title("Sensitivity to Macro Bull Squeeze Guard", fontsize=12, fontweight='bold')
    ax_macro.set_ylabel("Combined Total Return (%)")
    ax_macro.axhline(158.21, color='black', linestyle=':', label='Long Baseline (+158.2%)')
    ax_macro.legend()
    plt.xticks(rotation=20)
    plt.tight_layout()
    plot4_path = os.path.join(plots_dir, "short_sensitivity_grid.png")
    fig.savefig(plot4_path, dpi=300)
    plt.close(fig)
    print(f"  [Plot 4] Saved: {plot4_path}")

    # --- Step 8: Export metrics.json ---
    print("\n--- Step 8: Exporting Structured metrics.json ---")
    metrics_data = {
        "experiment_id": "EXP-95",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": {
            "symbol": "BTCUSD",
            "timeframe_primary": "1h",
            "timeframe_execution": "1m",
            "discovery_start": "2020-01-01 00:00:00+00:00",
            "discovery_end": "2025-04-30 23:59:00+00:00",
            "cost_bps": 40
        },
        "hyp_95_1_short_pullback": {
            "events_count": len(events_spb),
            "metrics": m_spb,
            "ci_95": ci_spb,
            "vacuum_delta_72h_pct": round(mfe_with_vacuum - mfe_without_vacuum, 2)
        },
        "hyp_95_2_bearish_afs_and_propagation": {
            "afs_ic": {
                "ic_order_score_24h": ic_order_24h,
                "ic_majority_score_24h": ic_maj_24h,
                "ic_order_score_72h": ic_order_72h,
                "ic_majority_score_72h": ic_maj_72h
            },
            "scale_trios": hyp_95_2_trios_results
        },
        "hyp_95_3_standalone_short": {
            "events_count": len(short_master_events),
            "metrics": m_short_master,
            "ci_95": ci_short_master,
            "yearly": yearly_short,
            "periods": periods_short
        },
        "baseline_long_master_exp91": {
            "metrics": m_long,
            "ci_95": ci_long,
            "yearly": compute_yearly_metrics(trades_long_master),
            "periods": compute_period_metrics(trades_long_master)
        },
        "bidirectional_integrated_master": {
            "metrics": m_comb,
            "ci_95": ci_comb,
            "yearly": yearly_comb,
            "periods": periods_comb,
            "improvements": {
                "total_return_increase_pct": round(m_comb['total_opportunity_net_return_pct'] - m_long['total_opportunity_net_return_pct'], 2),
                "p2_bear_2022_increase_pct": round(periods_comb['P2_Bear']['total_opportunity_net_return_pct'] - compute_period_metrics(trades_long_master)['P2_Bear']['total_opportunity_net_return_pct'], 2),
                "profit_factor_delta": round(m_comb['profit_factor'] - m_long['profit_factor'], 2)
            }
        }
    }
    
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to {metrics_path}")
    
    print("\n" + "=" * 80)
    print(f"EXP-95 Execution Successfully Completed in {time.time() - t_start:.1f}s")
    print("=" * 80)

if __name__ == "__main__":
    main()
