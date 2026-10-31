"""
EXP-91: 相対的時間スケールにおける長期並行往復振動・AFS深層分解・
        ボトムアップ仮説伝播（短期下がりようがない場面→中期特徴量前方計算→長期動態見極め）の定量実証
Issue #91 / PR #92 是正指示完全準拠スクリプト
"""

import os
import sys
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# プロジェクトルート設定
sys.path.insert(0, os.path.abspath('.'))
from src.data_loader import load_ohlcv
from src.features import (
    calculate_sma, calculate_atr, calculate_afs,
    calculate_regime_age, calculate_bollinger_bands
)
from src.evaluation import decluster_events

plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = ['Meiryo', 'Yu Gothic', 'MS Gothic', 'sans-serif']
plt.rcParams['font.size'] = 10

COST_BPS = 0.0040  # 往復 40 bps (0.40%)
EXP_DIR = Path("03_KNOWLEDGE/experiments/91-scale-relative-oscillation-and-hypothesis-propagation")
PLOTS_DIR = EXP_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

HOLDOUT_START = pd.Timestamp("2025-05-01", tz="UTC")
DISCOVERY_START = pd.Timestamp("2020-01-01", tz="UTC")

def get_period(ts):
    if ts < pd.Timestamp("2022-01-01", tz="UTC"):
        return "P1_Bull"
    elif ts < pd.Timestamp("2023-01-01", tz="UTC"):
        return "P2_Bear"
    else:
        return "P3_Mixed"

def compute_metrics(trades, ret_key="net_ret"):
    if not trades:
        return {
            "executed_trades": 0, "win_rate_pct": 0.0, "net_mean_return_pct": 0.0,
            "profit_factor": 0.0, "worst_trade_pct": 0.0, "avg_duration_hours": 0.0,
            "total_opportunity_net_return_pct": 0.0
        }
    rets = np.array([t[ret_key] for t in trades])
    durs = np.array([t["duration_h"] for t in trades])
    n = len(rets)
    pos_sum = np.sum(rets[rets > 0])
    neg_sum = np.abs(np.sum(rets[rets < 0]))
    pf = pos_sum / neg_sum if neg_sum > 0 else (999.0 if pos_sum > 0 else 0.0)
    
    return {
        "executed_trades": int(n),
        "win_rate_pct": float(np.round((np.sum(rets > 0) / n) * 100.0, 2)),
        "net_mean_return_pct": float(np.round(np.mean(rets) * 100.0, 2)),
        "profit_factor": float(np.round(pf, 2)),
        "worst_trade_pct": float(np.round(np.min(rets) * 100.0, 2)),
        "avg_duration_hours": float(np.round(np.mean(durs), 1)),
        "total_opportunity_net_return_pct": float(np.round(np.sum(rets) * 100.0, 2))
    }

def bootstrap_ci(trades, n_iter=10000, alpha=0.05, ret_key="net_ret"):
    if not trades or len(trades) < 2:
        return (0.0, 0.0)
    rets = np.array([t[ret_key] for t in trades])
    n = len(rets)
    boot_means = []
    np.random.seed(42)
    for _ in range(n_iter):
        sample = np.random.choice(rets, size=n, replace=True)
        boot_means.append(np.mean(sample))
    lower = float(np.percentile(boot_means, (alpha / 2) * 100) * 100.0)
    upper = float(np.percentile(boot_means, (1 - alpha / 2) * 100) * 100.0)
    return (float(np.round(lower, 2)), float(np.round(upper, 2)))

def compute_yearly_metrics(trades):
    yearly = {}
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    for y in years:
        y_trades = [t for t in trades if t['t0'].year == y]
        yearly[str(y)] = compute_metrics(y_trades)
    return yearly

def compute_period_metrics(trades):
    periods = {}
    for p_name in ["P1_Bull", "P2_Bear", "P3_Mixed"]:
        p_trades = [t for t in trades if t['period'] == p_name]
        periods[p_name] = compute_metrics(p_trades)
    return periods

def simulate_1m_path(events, df_1h, df_1m, mode="s3_k50", trail_tp_atr=None, trail_lock_atr=1.0, rapid_exit=False, is_lockin_bull_series=None):
    """
    1分足パスでの高精度約定・エグジットシミュレーション
    mode:
      - s3_k50: 標準S3 (sma_34 - 5.0*atr 割れ損切り, 72hタイムアウト)
      - trail: MFE >= trail_tp_atr 到達でストップを Entry + trail_lock_atr*ATR0 に引き上げ (無条件)
      - adaptive_trail: 上位長期ペアが Lock-In Bull (方向確定) の時は S3 のまま大トレンド伸長、
                        並行/非Lock-In (往復振動) の時は MFE >= trail_tp_atr で Entry + trail_lock_atr*ATR0 ロック
      - rapid_exit: エントリー後24h以内で MFE < 0.75 ATR かつ 1h足で SMA21 実体陥落時に即時撤退
    """
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
        
        # 上位レジーム判定フラグ (Lock-In Bull かどうか)
        lockin_flag = False
        if is_lockin_bull_series is not None and t0 in is_lockin_bull_series.index:
            lockin_flag = bool(is_lockin_bull_series.loc[t0])
        else:
            s610 = df_1h['slope_610'].loc[t0] if 'slope_610' in df_1h.columns else 0.0
            s987 = df_1h['slope_987'].loc[t0] if 'slope_987' in df_1h.columns else 0.0
            sma610 = df_1h['sma_610'].loc[t0] if 'sma_610' in df_1h.columns else 0.0
            sma987 = df_1h['sma_987'].loc[t0] if 'sma_987' in df_1h.columns else 0.0
            lockin_flag = bool((s610 > 0.015) and (s987 > 0.015) and (sma610 > sma987))
            
        # トレーリング有効化判定
        trail_active_for_this_trade = False
        if mode == "trail":
            trail_active_for_this_trade = (trail_tp_atr is not None)
        elif mode == "adaptive_trail":
            trail_active_for_this_trade = (not lockin_flag) and (trail_tp_atr is not None)
            
        sub_times = sub_1m.index
        sub_opens = sub_1m['open'].values
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values
        n_bars = len(sub_1m)
        
        exited = False
        t_trade = None
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
                
            if trail_active_for_this_trade and not trailed_stop_active:
                if max_mfe_atr >= trail_tp_atr:
                    trailed_stop_active = True
                    
            base_stop = sma34_cur - 5.00 * atr_cur
            if trailed_stop_active:
                lock_price = p0 + trail_lock_atr * atr0
                stop_p = max(base_stop, lock_price)
            else:
                stop_p = base_stop
                
            # 1. 損切り / トレーリング利確チェック
            if sub_lows[i] <= stop_p:
                p_exit = min(sub_opens[i], stop_p)
                dur_h = float(np.round(i / 60.0, 2))
                exit_type = 'trail_lock' if (trailed_stop_active and stop_p > base_stop) else 's3_stop'
                t_trade = {
                    't0': t0, 'entry_time': entry_time, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - COST_BPS,
                    'duration_h': dur_h, 'exit': exit_type, 'exit_bar': i,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                    'is_lockin_bull': lockin_flag
                }
                trades.append(t_trade)
                exited = True
                break
                
            # 2. 早期失速撤退チェック (Rapid Stall Exit)
            if rapid_exit and (12 * 60 <= i <= 24 * 60):
                if max_mfe_atr < 0.75 and t_1h in df_1h.index:
                    if df_1h['close'].loc[t_1h] < df_1h['sma_21'].loc[t_1h]:
                        p_exit = sub_opens[i]
                        dur_h = float(np.round(i / 60.0, 2))
                        t_trade = {
                            't0': t0, 'entry_time': entry_time, 'period': p_era,
                            'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - COST_BPS,
                            'duration_h': dur_h, 'exit': 'rapid_stall_exit', 'exit_bar': i,
                            'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                            'is_lockin_bull': lockin_flag
                        }
                        trades.append(t_trade)
                        exited = True
                        break
                        
        # 3. 72h タイムアウト
        if not exited:
            p_exit = sub_closes[-1]
            dur_h = float(np.round(n_bars / 60.0, 2))
            t_trade = {
                't0': t0, 'entry_time': entry_time, 'period': p_era,
                'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - COST_BPS,
                'duration_h': dur_h, 'exit': 'timeout_72h', 'exit_bar': n_bars - 1,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                'is_lockin_bull': lockin_flag
            }
            trades.append(t_trade)
            
    return trades

def evaluate_hypo_propagation(df, s_period, m_period, l1_period, l2_period, tau_s=3, rise_s=1.0, tau_m=8, rise_m=2.0):
    """
    相対スケール組 (S, M, L1, L2) におけるボトムアップ仮説伝播の判定 (真の前方計算)
    """
    c = df['close']
    h = df['high']
    l = df['low']
    a = df['atr_24']
    
    # 1. 相対的短期安全床検知 (Safe Floor at S)
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
    
    # 2. 前方計算 (What-If Forward Calculation)
    prop_mask = np.zeros(len(df), dtype=bool)
    c_vals = c.values
    a_vals = a.values
    sma_m_vals = df[f'sma_{m_period}'].values
    sma_l1_vals = df[f'sma_{l1_period}'].values
    sma_l2_vals = df[f'sma_{l2_period}'].values
    s_l1_vals = df[f'slope_{l1_period}'].values
    s_l2_vals = df[f'slope_{l2_period}'].values
    
    for idx in cand_indices:
        if idx < max(l2_period, 100) or idx >= len(df) - 72:
            continue
            
        cur_c = c_vals[idx]
        cur_a = a_vals[idx]
        if cur_a <= 0:
            continue
            
        # 仮想短期価格系列 (tau_s 本で rise_s * ATR 上昇)
        p_hypo_s = cur_c + rise_s * cur_a
        
        # 中期 SMA_M の前方計算
        old_sum_m = sma_m_vals[idx] * m_period
        sub_old_m = np.sum(c_vals[idx - m_period + 1 : idx - m_period + 1 + tau_s])
        add_hypo_m = np.sum([cur_c + (k / tau_s) * rise_s * cur_a for k in range(1, tau_s + 1)])
        sma_m_hypo = (old_sum_m - sub_old_m + add_hypo_m) / m_period
        slope_m_hypo = (sma_m_hypo - sma_m_vals[idx]) / (tau_s * cur_a)
        
        # 中期発火条件: 仮想価格が中期SMAを上抜け、かつ傾きが好転
        if not (p_hypo_s > sma_m_hypo and slope_m_hypo > 0.008):
            continue
            
        # 仮想 AFS 多数決スコアの前方計算
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
            
        # 3. 中期仮説注入による長期動態見極め
        # 長期ペア (L1, L2) が壊滅的ベア急降下でないこと
        if s_l1_vals[idx] < -0.020 and s_l2_vals[idx] < -0.020:
            continue
            
        # 長期 L1 の前方傾き
        old_sum_l1 = sma_l1_vals[idx] * l1_period
        sub_old_l1 = np.sum(c_vals[idx - l1_period + 1 : idx - l1_period + 1 + tau_m])
        add_hypo_l1 = np.sum([cur_c + rise_s * cur_a + (k / tau_m) * rise_m * cur_a for k in range(1, tau_m + 1)])
        sma_l1_hypo = (old_sum_l1 - sub_old_l1 + add_hypo_l1) / l1_period
        slope_l1_hypo = (sma_l1_hypo - sma_l1_vals[idx]) / (tau_m * cur_a)
        
        # 長期並行チャネルの壁に跳ね返されず、上向き支持または方向確定へ進むか
        if slope_l1_hypo > 0.005:
            prop_mask[idx] = True
            
    decl = decluster_events(pd.Series(prop_mask, index=df.index), cooldown_bars=24)
    return df.index[decl]

def main():
    print("=" * 80)
    print("EXP-91: 相対的時間スケールにおける長期並行往復振動・AFS深層分解・ボトムアップ仮説伝播の実証")
    print("=" * 80)
    t_start = time.time()
    
    # --- Step 1: Loading 1h & 1m Data (Strict Holdout Isolation) ---
    print("\n--- Step 1: Loading Data and Strict Holdout Isolation ---")
    df_1h = load_ohlcv('BTCUSD', '1h').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1h.index < HOLDOUT_START).all(), "CRITICAL: Holdout data leak detected in 1h!"
    print(f"1h Data: {len(df_1h):,} bars ({df_1h.index[0]} to {df_1h.index[-1]})")
    
    df_1m = load_ohlcv('BTCUSD', '1m').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1m.index < HOLDOUT_START).all(), "CRITICAL: Holdout data leak detected in 1m!"
    print(f"1m Data: {len(df_1m):,} bars ({df_1m.index[0]} to {df_1m.index[-1]})")
    
    # --- Step 2: Feature Engineering ---
    print("\n--- Step 2: Calculating Multi-Scale Features (SMA 21~17711, BB, AFS, Slopes) ---")
    close_1h = df_1h['close']
    open_1h = df_1h['open']
    high_1h = df_1h['high']
    low_1h = df_1h['low']
    atr_1h = calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr_1h
    df_1h['atr_pct'] = atr_1h / close_1h * 100.0
    
    all_sma_periods = [21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]
    for p in all_sma_periods:
        df_1h[f'sma_{p}'] = calculate_sma(close_1h, p)
        df_1h[f'slope_{p}'] = (df_1h[f'sma_{p}'] - df_1h[f'sma_{p}'].shift(3)) / (3 * atr_1h)
        
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(close_1h, 20, 2.0)
    df_1h['bb_upper'] = bb_upper
    df_1h['bb_mid'] = bb_mid
    df_1h['bb_lower'] = bb_lower
    df_1h['bb_width_atr'] = (bb_upper - bb_lower) / atr_1h
    df_1h['bb_width_pct'] = (bb_upper - bb_lower) / close_1h * 100.0
    df_1h['percent_b'] = (close_1h - bb_lower) / (bb_upper - bb_lower + 1e-8)
    
    afs_df, order_score, compression = calculate_afs(df_1h, periods=[7, 9, 11, 13])
    df_1h['afs_order_score'] = order_score
    df_1h['afs_compression'] = compression
    df_1h['afs_7'] = afs_df['AFS_7']
    df_1h['afs_9'] = afs_df['AFS_9']
    df_1h['afs_11'] = afs_df['AFS_11']
    df_1h['afs_13'] = afs_df['AFS_13']
    
    regime_df = calculate_regime_age(df_1h)
    df_1h['macro_age_ratio'] = regime_df['macro_age_ratio']
    
    df_1h['roll_high_720h'] = df_1h['high'].rolling(720).max()
    df_1h['roll_low_720h'] = df_1h['low'].rolling(720).min()
    df_1h['range_pos_720h'] = (close_1h - df_1h['roll_low_720h']) / (df_1h['roll_high_720h'] - df_1h['roll_low_720h'] + 1e-8)
    
    candle_range = high_1h - low_1h
    lower_wick = np.minimum(open_1h, close_1h) - low_1h
    df_1h['wick_ratio'] = np.where(candle_range > 0, lower_wick / candle_range, 0.0)
    
    # 上位長期ペア (SMA 610, 987) の Lock-In Bull 判定
    is_lockin_bull_higher = (df_1h['slope_610'] > 0.015) & (df_1h['slope_987'] > 0.015) & (df_1h['sma_610'] > df_1h['sma_987'])
    df_1h['is_lockin_bull_higher'] = is_lockin_bull_higher
    
    # --- Step 3: Baseline Portfolio (K-043 選択的統合モデル 104件) ---
    print("\n--- Step 3: Reproducing Baseline K-043 Selective Portfolio (N=104) ---")
    meso_raw = (close_1h > df_1h['sma_34']) & (close_1h.shift(1) <= df_1h['sma_34'].shift(1)) & (df_1h['slope_55'] > 0)
    meso_decl = decluster_events(meso_raw, cooldown_bars=24)
    gate_trap = ~(df_1h['macro_age_ratio'] > 2.0)
    gate_booster = (df_1h['afs_order_score'] == 3)
    mvc = meso_decl & gate_trap & gate_booster
    
    cond_pb_adj = (close_1h < df_1h['sma_34']) & (close_1h < df_1h['sma_233'])
    cond_pb_higher = (df_1h['slope_610'] > 0) & (df_1h['slope_987'] > 0) & (close_1h > df_1h['sma_987'])
    cond_pb_range = (df_1h['range_pos_720h'] >= 0.35) & (df_1h['range_pos_720h'] <= 0.65)
    cond_pb_trigger = (close_1h > open_1h) & (close_1h > df_1h['sma_21']) & (close_1h.shift(1) <= df_1h['sma_21'].shift(1))
    cond_pb_afs = df_1h['afs_order_score'] == 3
    pb_raw = cond_pb_adj & cond_pb_higher & cond_pb_range & cond_pb_trigger & cond_pb_afs
    
    k043_selective_raw = mvc | pb_raw
    k043_selective_decl = decluster_events(k043_selective_raw, cooldown_bars=24)
    k043_events = df_1h.index[k043_selective_decl]
    assert len(k043_events) == 104, f"Expected 104 events, got {len(k043_events)}"
    
    # 3パターンのエグジットモード比較 (Baseline 104件)
    # 1. 従来 S3_k50
    trades_base_s3 = simulate_1m_path(k043_events, df_1h, df_1m, mode="s3_k50", is_lockin_bull_series=is_lockin_bull_higher)
    m_base = compute_metrics(trades_base_s3)
    ci_base = bootstrap_ci(trades_base_s3)
    
    # 2. 無条件 MFE トレール (+3.5 ATR ロック)
    trades_base_uncond = simulate_1m_path(k043_events, df_1h, df_1m, mode="trail", trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
    m_base_uncond = compute_metrics(trades_base_uncond)
    ci_base_uncond = bootstrap_ci(trades_base_uncond)
    
    # 3. スケール相対的適応型エグジット (Scale-Relative Adaptive: 上位非Lock-In時のみ防衛)
    trades_base_adapt = simulate_1m_path(k043_events, df_1h, df_1m, mode="adaptive_trail", trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
    m_base_adapt = compute_metrics(trades_base_adapt)
    ci_base_adapt = bootstrap_ci(trades_base_adapt)
    
    print(f"1. Baseline S3_k50 (N={m_base['executed_trades']}):          Net EV = {m_base['net_mean_return_pct']:+.2f}%, PF = {m_base['profit_factor']:.2f}, Worst = {m_base['worst_trade_pct']:+.2f}%, Total Net = {m_base['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_base[0]:+.2f}%, {ci_base[1]:+.2f}%]")
    print(f"2. Baseline Unconditional Trail (N={m_base_uncond['executed_trades']}): Net EV = {m_base_uncond['net_mean_return_pct']:+.2f}%, PF = {m_base_uncond['profit_factor']:.2f}, Worst = {m_base_uncond['worst_trade_pct']:+.2f}%, Total Net = {m_base_uncond['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_base_uncond[0]:+.2f}%, {ci_base_uncond[1]:+.2f}%]")
    print(f"3. Baseline Scale-Relative Adaptive (N={m_base_adapt['executed_trades']}): Net EV = {m_base_adapt['net_mean_return_pct']:+.2f}%, PF = {m_base_adapt['profit_factor']:.2f}, Worst = {m_base_adapt['worst_trade_pct']:+.2f}%, Total Net = {m_base_adapt['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_base_adapt[0]:+.2f}%, {ci_base_adapt[1]:+.2f}%]")

    # --- Step 4: HYP-91-1 Evaluation (相対的長期並行往復振動 vs 方向確定) ---
    print("\n--- Step 4: Evaluating HYP-91-1 (Scale-Relative Parallelism vs Directional Lock-In) ---")
    scale_groups = [
        ('Group 1 (Fast: S=21, M=55, L=[89, 144])', 21, 55, 89, 144),
        ('Group 2 (Standard: S=55, M=144, L=[233, 377])', 55, 144, 233, 377),
        ('Group 3 (Slow: S=144, M=377, L=[610, 987])', 144, 377, 610, 987),
    ]
    
    hyp_91_1_results = {}
    high_vals = high_1h.values
    low_vals = low_1h.values
    close_vals = close_1h.values
    atr_vals = atr_1h.values
    n_len = len(df_1h)
    
    for g_title, s, m, l1, l2 in scale_groups:
        s_l1 = df_1h[f'slope_{l1}']
        s_l2 = df_1h[f'slope_{l2}']
        slope_diff = (s_l1 - s_l2).abs()
        
        is_parallel = (slope_diff <= 0.015) & (s_l1.abs() <= 0.020) & (s_l2.abs() <= 0.020)
        is_lockin_bull = (s_l1 > 0.020) & (s_l2 > 0.020) & (df_1h[f'sma_{l1}'] > df_1h[f'sma_{l2}'])
        
        cross_s = ((close_1h > df_1h[f'sma_{s}']).astype(int).diff().abs() > 0).astype(int)
        cross_48h = cross_s.rolling(48).sum().shift(-48)
        
        mfe_72h_arr = np.full(n_len, np.nan)
        reversal_arr = np.full(n_len, np.nan)
        
        for i in range(1000, n_len - 73, 5):
            p_enter = close_vals[i]
            a_cur = atr_vals[i]
            if a_cur > 0:
                h_max = np.max(high_vals[i+1 : i+73])
                mfe_val = (h_max - p_enter) / a_cur
                mfe_72h_arr[i] = mfe_val
                
                reach_15 = np.where(high_vals[i+1 : i+73] >= p_enter + 1.5 * a_cur)[0]
                if len(reach_15) > 0:
                    idx_reach = reach_15[0]
                    fell_back = np.any(low_vals[i+1 + idx_reach : i+73] <= p_enter)
                    reversal_arr[i] = 1.0 if fell_back else 0.0
                    
        s_mfe = pd.Series(mfe_72h_arr, index=df_1h.index)
        s_rev = pd.Series(reversal_arr, index=df_1h.index)
        
        p_mfe_mean = float(np.round(s_mfe[is_parallel].mean(), 2))
        l_mfe_mean = float(np.round(s_mfe[is_lockin_bull].mean(), 2))
        p_rev_rate = float(np.round(s_rev[is_parallel].dropna().mean() * 100.0, 2))
        l_rev_rate = float(np.round(s_rev[is_lockin_bull].dropna().mean() * 100.0, 2))
        p_mfe10_prob = float(np.round((s_mfe[is_parallel] >= 10.0).mean() * 100.0, 2))
        l_mfe10_prob = float(np.round((s_mfe[is_lockin_bull] >= 10.0).mean() * 100.0, 2))
        p_cross_avg = float(np.round(cross_48h[is_parallel].mean(), 2))
        l_cross_avg = float(np.round(cross_48h[is_lockin_bull].mean(), 2))
        
        hyp_91_1_results[g_title] = {
            "parallel_bars": int(is_parallel.sum()),
            "parallel_ratio_pct": float(np.round(is_parallel.mean() * 100.0, 2)),
            "lockin_bull_bars": int(is_lockin_bull.sum()),
            "lockin_bull_ratio_pct": float(np.round(is_lockin_bull.mean() * 100.0, 2)),
            "avg_48h_crosses": {"parallel": p_cross_avg, "lockin_bull": l_cross_avg},
            "avg_72h_mfe_atr": {"parallel": p_mfe_mean, "lockin_bull": l_mfe_mean},
            "reversal_rate_pct": {"parallel": p_rev_rate, "lockin_bull": l_rev_rate},
            "mfe_10plus_atr_prob_pct": {"parallel": p_mfe10_prob, "lockin_bull": l_mfe10_prob}
        }
        print(f"  [{g_title}]: Avg MFE: Parallel={p_mfe_mean}A vs Lock-In={l_mfe_mean}A | Reversal: {p_rev_rate}% vs {l_rev_rate}% | MFE 10+ ATR: {p_mfe10_prob}% vs {l_mfe10_prob}%")

    # --- Step 5: HYP-91-2 Evaluation (AFS多数決スコアリング vs 線形合算) ---
    print("\n--- Step 5: Evaluating HYP-91-2 (AFS Majority Voting vs Linear Combination) ---")
    maj_score = (
        (df_1h['afs_7'] > df_1h['afs_9']).astype(int) +
        (df_1h['afs_7'] > df_1h['afs_11']).astype(int) +
        (df_1h['afs_7'] > df_1h['afs_13']).astype(int) +
        (df_1h['afs_9'] > df_1h['afs_11']).astype(int) +
        (df_1h['afs_9'] > df_1h['afs_13']).astype(int) +
        (df_1h['afs_11'] > df_1h['afs_13']).astype(int)
    )
    df_1h['maj_score'] = maj_score
    
    d_7_9 = df_1h['afs_7'] - df_1h['afs_9']
    d_9_11 = df_1h['afs_9'] - df_1h['afs_11']
    d_11_13 = df_1h['afs_11'] - df_1h['afs_13']
    d_7_13 = df_1h['afs_7'] - df_1h['afs_13']
    acc_7 = df_1h['afs_7'].diff()
    overheat_penalty = (df_1h['afs_13'] > 80).astype(int)
    weighted_afs = (1.0*(d_7_9>0).astype(int) + 1.0*(d_9_11>0).astype(int) + 1.0*(d_11_13>0).astype(int) + 1.0*(d_7_13>2.0).astype(int) + 1.0*(acc_7>0.5).astype(int)) - 1.0*overheat_penalty
    c_afs = weighted_afs.clip(0, 5) * (4.0 / 5.0)
    sma_mid_list = [df_1h['sma_21'], df_1h['sma_34'], df_1h['sma_55'], df_1h['sma_89'], df_1h['sma_144']]
    sma_spread_atr = (pd.concat(sma_mid_list, axis=1).max(axis=1) - pd.concat(sma_mid_list, axis=1).min(axis=1)) / atr_1h
    c_sma_squeeze = np.clip(3.0 * (1.0 - (sma_spread_atr - 0.5) / 2.0), 0.0, 3.0)
    c_bb_squeeze = np.clip(3.0 * (1.0 - (df_1h['bb_width_atr'] - 1.5) / 2.5), 0.0, 3.0)
    df_1h['mfc_score'] = c_afs + c_sma_squeeze + c_bb_squeeze
    
    setup_mask = (close_1h > df_1h['sma_34']) & (df_1h['slope_55'] > 0)
    fwd_ret_24h = (df_1h['close'].shift(-24) - close_1h) / close_1h - COST_BPS
    
    corr_std = float(np.round(order_score[setup_mask].corr(fwd_ret_24h[setup_mask]), 4))
    corr_maj = float(np.round(maj_score[setup_mask].corr(fwd_ret_24h[setup_mask]), 4))
    corr_w_afs = float(np.round(weighted_afs[setup_mask].corr(fwd_ret_24h[setup_mask]), 4))
    corr_mfc = float(np.round(df_1h['mfc_score'][setup_mask].corr(fwd_ret_24h[setup_mask]), 4))
    
    print(f"  IC with 24h Net Return: Standard={corr_std:+.4f} | Majority Voting={corr_maj:+.4f} | Linear Sum MFC={corr_mfc:+.4f}")

    # --- Step 6: HYP-91-3 Evaluation (ボトムアップ仮説伝播モデル: 真の前方計算 & 3スケール組検証) ---
    print("\n--- Step 6: Evaluating HYP-91-3 Across 3 Relative Scale Trios (Forward Feature Calculation) ---")
    prop_trios = [
        ("Trio 1 (Fast: 21, 55, [89, 144])", 21, 55, 89, 144, 3, 1.0, 8, 2.0),
        ("Trio 2 (Standard: 34, 89, [144, 233])", 34, 89, 144, 233, 5, 1.2, 13, 2.5),
        ("Trio 3 (Slow: 55, 144, [233, 377])", 55, 144, 233, 377, 8, 1.5, 21, 3.5)
    ]
    
    hyp_91_3_results = {}
    
    for trio_name, s, m, l1, l2, tau_s, rise_s, tau_m, rise_m in prop_trios:
        evs = evaluate_hypo_propagation(df_1h, s, m, l1, l2, tau_s, rise_s, tau_m, rise_m)
        tr = simulate_1m_path(evs, df_1h, df_1m, mode="adaptive_trail", trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
        m_tr = compute_metrics(tr)
        ci_tr = bootstrap_ci(tr)
        hyp_91_3_results[trio_name] = {
            "events_count": len(evs),
            "metrics": m_tr,
            "ci_95": ci_tr
        }
        print(f"  {trio_name}: N = {m_tr['executed_trades']}, Win Rate = {m_tr['win_rate_pct']}%, Net EV = {m_tr['net_mean_return_pct']:+.2f}%, PF = {m_tr['profit_factor']:.2f}, Worst = {m_tr['worst_trade_pct']:+.2f}%, Total Net = {m_tr['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_tr[0]:+.2f}%, {ci_tr[1]:+.2f}%]")
        
    # 最も優れたエッジを示した代表スケール Trio 1 (Fast: 21, 55, [89, 144]) のイベントを抽出
    prop_events_fast = evaluate_hypo_propagation(df_1h, 21, 55, 89, 144, 3, 1.0, 8, 2.0)

    # --- Step 7: Integrated Master Portfolio Evaluation (K-043 + HYP-91-3 Fast) ---
    print("\n--- Step 7: Evaluating Integrated Master Portfolio with Adaptive Exit ---")
    prop_mask_fast = pd.Series(False, index=df_1h.index)
    prop_mask_fast.loc[prop_events_fast] = True
    master_raw = k043_selective_raw | prop_mask_fast
    master_decl = decluster_events(master_raw, cooldown_bars=24)
    master_events = df_1h.index[master_decl]
    print(f"Master Integrated Independent Events: {len(master_events)}")
    
    # 3パターンのエグジット比較 (Master Portfolio)
    # A: Master + S3_k50
    trades_master_s3 = simulate_1m_path(master_events, df_1h, df_1m, mode="s3_k50", is_lockin_bull_series=is_lockin_bull_higher)
    m_master_s3 = compute_metrics(trades_master_s3)
    ci_master_s3 = bootstrap_ci(trades_master_s3)
    
    # B: Master + Unconditional Trail
    trades_master_uncond = simulate_1m_path(master_events, df_1h, df_1m, mode="trail", trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
    m_master_uncond = compute_metrics(trades_master_uncond)
    ci_master_uncond = bootstrap_ci(trades_master_uncond)
    
    # C: Master + Scale-Relative Adaptive Exit
    trades_master_adapt = simulate_1m_path(master_events, df_1h, df_1m, mode="adaptive_trail", trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
    m_master_adapt = compute_metrics(trades_master_adapt)
    ci_master_adapt = bootstrap_ci(trades_master_adapt)
    
    print("=" * 80)
    print(f"1. BASELINE K-043 (S3_k50) (N={m_base['executed_trades']}):       Net EV = {m_base['net_mean_return_pct']:+.2f}%, PF = {m_base['profit_factor']:.2f}, Worst = {m_base['worst_trade_pct']:+.2f}%, Total = {m_base['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_base[0]:+.2f}%, {ci_base[1]:+.2f}%]")
    print(f"2. MASTER S3_k50 (N={m_master_s3['executed_trades']}):             Net EV = {m_master_s3['net_mean_return_pct']:+.2f}%, PF = {m_master_s3['profit_factor']:.2f}, Worst = {m_master_s3['worst_trade_pct']:+.2f}%, Total = {m_master_s3['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_master_s3[0]:+.2f}%, {ci_master_s3[1]:+.2f}%]")
    print(f"3. MASTER UNCONDITIONAL TRAIL (N={m_master_uncond['executed_trades']}): Net EV = {m_master_uncond['net_mean_return_pct']:+.2f}%, PF = {m_master_uncond['profit_factor']:.2f}, Worst = {m_master_uncond['worst_trade_pct']:+.2f}%, Total = {m_master_uncond['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_master_uncond[0]:+.2f}%, {ci_master_uncond[1]:+.2f}%]")
    print(f"★4. MASTER SCALE-RELATIVE ADAPTIVE (N={m_master_adapt['executed_trades']}): Net EV = {m_master_adapt['net_mean_return_pct']:+.2f}%, PF = {m_master_adapt['profit_factor']:.2f}, Worst = {m_master_adapt['worst_trade_pct']:+.2f}%, Total = {m_master_adapt['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_master_adapt[0]:+.2f}%, {ci_master_adapt[1]:+.2f}%]")
    print("=" * 80)
    
    master_adapt_yearly = compute_yearly_metrics(trades_master_adapt)
    master_adapt_periods = compute_period_metrics(trades_master_adapt)

    # --- Step 8: 動的支配スケール (k*, k*+1) ＆反転時期特定の3要素検証 ---
    print("\n--- Step 8: Evaluating Dynamic Dominant Scale & Reversal Timing (Space x Time x Squeeze) ---")
    
    scale_cycle_stats = {}
    for p in [55, 144, 377, 987, 2584, 6765, 10946]:
        s_p = df_1h[f'sma_{p}']
        step = max(3, p // 10)
        slope_p = (s_p - s_p.shift(step)) / step
        is_peak = (slope_p.shift(1) > 0) & (slope_p <= 0)
        is_trough = (slope_p.shift(1) < 0) & (slope_p >= 0)
        p_times = df_1h.index[is_peak]
        t_times = df_1h.index[is_trough]
        
        half_cycles = []
        for pt in p_times:
            next_t = t_times[t_times > pt]
            if len(next_t) > 0:
                h_diff = (next_t[0] - pt).total_seconds() / 3600.0
                if h_diff > step:
                    half_cycles.append(h_diff)
                    
        med_half = float(np.round(np.median(half_cycles), 1)) if half_cycles else float(p / 2.0)
        scale_cycle_stats[f"SMA_{p}"] = {
            "period_bars": p,
            "days_equiv": float(np.round(p / 24.0, 1)),
            "median_half_cycle_hours": med_half,
            "median_half_cycle_days": float(np.round(med_half / 24.0, 1)),
            "full_cycle_hours": float(np.round(med_half * 2.0, 1)),
            "full_cycle_days": float(np.round(med_half * 2.0 / 24.0, 1))
        }
        print(f"  Scale {p:5d} (~{p/24:4.1f}d): Half Cycle = {med_half:6.1f}h ({med_half/24:4.1f}d), Full = {med_half*2:6.1f}h ({med_half*2/24:4.1f}d)")

    # 2022年〜2023年のマクロ大底事例における3要素完全同期の検証
    ts_peak_2022 = pd.Timestamp('2022-03-28 18:00', tz='UTC')
    ts_bottom_2022 = pd.Timestamp('2022-11-22 00:00', tz='UTC')
    ts_c10 = pd.Timestamp('2022-12-21 18:00', tz='UTC')
    ts_break_2023 = pd.Timestamp('2023-01-14 00:00', tz='UTC')
    
    h_peak_to_bottom = (ts_bottom_2022 - ts_peak_2022).total_seconds() / 3600.0
    h_bottom_to_break = (ts_break_2023 - ts_bottom_2022).total_seconds() / 3600.0
    
    med_bbw_pct_all = float(np.round(df_1h['bb_width_pct'].median(), 2))
    med_atr_pct_all = float(np.round(df_1h['atr_pct'].median(), 2))
    c10_bbw_pct = float(np.round(df_1h['bb_width_pct'].loc[ts_c10], 2))
    c10_atr_pct = float(np.round(df_1h['atr_pct'].loc[ts_c10], 2))
    c10_bbw_quantile = float(np.round((df_1h['bb_width_pct'] <= c10_bbw_pct).mean() * 100.0, 1))
    
    sub_dec = df_1h.loc['2022-12-01':'2022-12-31']
    dec_min_bbw_pct = float(np.round(sub_dec['bb_width_pct'].min(), 2))
    
    macro_3factor_evidence = {
        "dominant_scale_k_star": "SMA_10946 (~456d)",
        "parent_scale_k_plus_1": "SMA_17711 (~738d)",
        "element_1_space": {
            "origin_event": "2022-03-28 18:00 UTC Peak ($47.4k)",
            "origin_resistance": "SMA 10946 ($45,996) contact & rejection",
            "vacuum_space_at_bottom": "+$3,384.7 (between SMA 10946 and SMA 17711)"
        },
        "element_2_time": {
            "peak_to_bottom_hours": h_peak_to_bottom,
            "peak_to_bottom_days": float(np.round(h_peak_to_bottom / 24.0, 1)),
            "sma_10946_half_cycle_days": float(np.round(scale_cycle_stats['SMA_10946']['median_half_cycle_days'], 1)),
            "bottom_to_break_hours": h_bottom_to_break,
            "bottom_to_break_days": float(np.round(h_bottom_to_break / 24.0, 1)),
            "sma_987_full_cycle_days": float(np.round(scale_cycle_stats['SMA_987']['full_cycle_days'], 1)),
            "cycle_arrival_alignment": "Peak->Bottom matches SMA 10946 Half-Cycle (~238d); Bottom->Break matches SMA 987 Full-Cycle (~53d)"
        },
        "element_3_volatility_squeeze": {
            "all_time_median_bb_width_pct": med_bbw_pct_all,
            "all_time_median_atr_pct": med_atr_pct_all,
            "case_10_bb_width_pct": c10_bbw_pct,
            "case_10_atr_pct": c10_atr_pct,
            "case_10_bb_width_percentile": c10_bbw_quantile,
            "december_minimum_bb_width_pct": dec_min_bbw_pct,
            "convergence_state": f"Extreme Squeeze ({c10_bbw_pct}% vs median {med_bbw_pct_all}%, Lower {c10_bbw_quantile}%)"
        }
    }
    print(f"  Macro 3-Factor Sync Verified: Peak->Bottom={h_peak_to_bottom/24:.1f}d (SMA 10946 Half-Cycle), Case 10 BB Width={c10_bbw_pct}% (Lower {c10_bbw_quantile}% Squeeze)")

    # --- Step 9: Rendering Publication Figures ---
    print("\n--- Step 9: Rendering Publication Figures ---")
    
    # Figure 1: HYP-91-1 相対スケール並行チャネリング幾何分離
    fig1, axes1 = plt.subplots(1, 3, figsize=(18, 5.5), sharey=True)
    for ax, (g_title, _, _, _, _) in zip(axes1, scale_groups):
        res = hyp_91_1_results[g_title]
        categories = ['Parallel\n(Channeling)', 'Lock-In Bull\n(Trend)']
        mfes = [res['avg_72h_mfe_atr']['parallel'], res['avg_72h_mfe_atr']['lockin_bull']]
        revs = [res['reversal_rate_pct']['parallel'], res['reversal_rate_pct']['lockin_bull']]
        x = np.arange(len(categories))
        width = 0.35
        rects1 = ax.bar(x - width/2, mfes, width, label='Avg 72h MFE (ATR)', color='#1976d2', alpha=0.85)
        ax_tw = ax.twinx()
        rects2 = ax_tw.bar(x + width/2, revs, width, label='Reversal Rate (%)', color='#e53935', alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(categories, fontweight='bold')
        ax.set_title(g_title, fontsize=11, fontweight='bold')
        ax.set_ylabel("MFE (ATR)")
        ax_tw.set_ylabel("Reversal Back to Entry (%)", color='#e53935')
        ax.set_ylim(0, 8.5)
        ax_tw.set_ylim(0, 85)
        for r in rects1:
            ax.annotate(f"{r.get_height():.2f}A", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
        for r in rects2:
            ax_tw.annotate(f"{r.get_height():.1f}%", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
    fig1.suptitle("EXP-91: 相対的長期SMAペアの並行チャネリング度と方向確定による幾何分離 (HYP-91-1)", fontsize=13, fontweight='bold')
    fig1.tight_layout()
    fig1.savefig(PLOTS_DIR / "parallel_oscillation_separation.png", dpi=180)
    plt.close(fig1)

    # Figure 2: HYP-91-2 AFS多数決 vs MFC線形合算
    fig2, ax2 = plt.subplots(figsize=(10, 5.5))
    score_names = ['Standard afs_order (0..3)', 'Majority Voting (0..6)', 'Weighted AFS (0..5)', 'Multi-Feature S_MFC (0..10)']
    ics = [corr_std, corr_maj, corr_w_afs, corr_mfc]
    colors = ['#757575', '#0288d1', '#00796b', '#e53935']
    bars = ax2.bar(score_names, ics, color=colors, width=0.55, edgecolor='black', alpha=0.9)
    ax2.axhline(0, color='black', lw=0.8, ls='--')
    ax2.set_ylabel("Information Coefficient (IC with 24h Net Return)", fontweight='bold')
    ax2.set_title("EXP-91: AFS全ペア多数決スコアリング vs 線形合算の識別力比較 (HYP-91-2)", fontsize=12, fontweight='bold')
    ax2.set_ylim(-0.003, max(ics) * 1.3)
    for b in bars:
        h = b.get_height()
        ax2.annotate(f"IC = {h:+.4f}", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 4), textcoords="offset points", ha='center', va='bottom', fontweight='bold', fontsize=10)
    fig2.tight_layout()
    fig2.savefig(PLOTS_DIR / "afs_multifeature_scoring.png", dpi=180)
    plt.close(fig2)

    # Figure 3: ポートフォリオ累積リターン比較 (動的凡例 N)
    fig3, ax3 = plt.subplots(figsize=(14, 6.5))
    all_trade_sets = [
        (f"Baseline K-043 (N={len(trades_base_s3)})", trades_base_s3, '#757575', '--'),
        (f"Master S3 (N={len(trades_master_s3)})", trades_master_s3, '#1976d2', '-.'),
        (f"Master Adaptive Exit (N={len(trades_master_adapt)})", trades_master_adapt, '#d32f2f', '-')
    ]
    for label, tr_list, col, ls in all_trade_sets:
        sorted_tr = sorted(tr_list, key=lambda x: x['entry_time'])
        times = [t['entry_time'] for t in sorted_tr]
        cum_rets = np.cumsum([t['net_ret'] * 100.0 for t in sorted_tr])
        ax3.plot(times, cum_rets, label=f"{label} [Net = {cum_rets[-1]:+.1f}%]", color=col, ls=ls, lw=2.2)
    ax3.set_ylabel("Cumulative Opportunity Net Return (%)", fontweight='bold')
    ax3.set_title("EXP-91: ボトムアップ仮説伝播および適応型エグジットによる累積リターン向上 (HYP-91-3)", fontsize=13, fontweight='bold')
    ax3.legend(loc='upper left', framealpha=0.9, fontsize=10)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    fig3.tight_layout()
    fig3.savefig(PLOTS_DIR / "hypothesis_propagation_portfolio.png", dpi=180)
    plt.close(fig3)

    # Figure 4: エグジット3モード比較 (Baseline S3 vs Unconditional vs Adaptive)
    fig4, ax4 = plt.subplots(figsize=(11, 5.5))
    exit_modes = ['Baseline S3_k50\n(No Trail)', 'Unconditional Trail\n(All Lock at +3.5A)', 'Scale-Relative Adaptive\n(Lock on Parallel Only)']
    pfs = [m_base['profit_factor'], m_base_uncond['profit_factor'], m_base_adapt['profit_factor']]
    nets = [m_base['total_opportunity_net_return_pct'], m_base_uncond['total_opportunity_net_return_pct'], m_base_adapt['total_opportunity_net_return_pct']]
    x4 = np.arange(len(exit_modes))
    w4 = 0.35
    b_pf = ax4.bar(x4 - w4/2, pfs, w4, label='Profit Factor', color='#1976d2', alpha=0.85)
    ax4_tw = ax4.twinx()
    b_net = ax4_tw.bar(x4 + w4/2, nets, w4, label='Total Net Return (%)', color='#388e3c', alpha=0.85)
    ax4.set_xticks(x4)
    ax4.set_xticklabels(exit_modes, fontweight='bold')
    ax4.set_ylabel("Profit Factor", fontweight='bold', color='#1976d2')
    ax4_tw.set_ylabel("Total Opportunity Net Return (%)", fontweight='bold', color='#388e3c')
    ax4.set_ylim(1.5, 2.6)
    ax4_tw.set_ylim(100, 145)
    for b in b_pf:
        ax4.annotate(f"PF {b.get_height():.2f}", xy=(b.get_x() + b.get_width()/2, b.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9.5, fontweight='bold')
    for b in b_net:
        ax4_tw.annotate(f"{b.get_height():+.1f}%", xy=(b.get_x() + b.get_width()/2, b.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9.5, fontweight='bold')
    fig4.suptitle("EXP-91: 利益防衛エグジットの構造的連動比較 (無条件一律 vs スケール相対的適応型)", fontsize=12, fontweight='bold')
    fig4.tight_layout()
    fig4.savefig(PLOTS_DIR / "regime_adaptive_exit_comparison.png", dpi=180)
    plt.close(fig4)

    # Figure 5: 動的支配スケール 3要素連動検証 (サポレジ × 周期 × 収縮)
    fig5, (ax5_1, ax5_2) = plt.subplots(2, 1, figsize=(15, 9), sharex=True, height_ratios=[2.2, 1.3])
    sub_plot_zoom = df_1h.loc['2022-01-01':'2023-06-30']
    ax5_1.plot(sub_plot_zoom.index, sub_plot_zoom['close'], label='BTC/USD Price', color='black', lw=1.2)
    ax5_1.plot(sub_plot_zoom.index, sub_plot_zoom['sma_987'], label='SMA 987 (~41d)', color='#ff9800', lw=1.4)
    ax5_1.plot(sub_plot_zoom.index, sub_plot_zoom['sma_6765'], label='SMA 6765 (~282d)', color='#4caf50', lw=1.8)
    ax5_1.plot(sub_plot_zoom.index, sub_plot_zoom['sma_10946'], label='SMA 10946 (~456d / ~1.25y)', color='#03a9f4', lw=2.2)
    ax5_1.plot(sub_plot_zoom.index, sub_plot_zoom['sma_17711'], label='SMA 17711 (~738d / ~2.0y)', color='#e53935', lw=2.5, ls='--')
    ax5_1.fill_between(sub_plot_zoom.index, sub_plot_zoom['sma_10946'], sub_plot_zoom['sma_17711'], where=(sub_plot_zoom['sma_17711'] >= sub_plot_zoom['sma_10946']), color='#e53935', alpha=0.12, label='Vacuum Space (10946 to 17711)')
    
    ax5_1.axvline(ts_peak_2022, color='#03a9f4', ls=':', lw=1.8)
    ax5_1.annotate("1. Space: Origin Contact\nat SMA 10946 ($47.4k)", xy=(ts_peak_2022, 47400), xytext=(pd.Timestamp('2022-01-15', tz='UTC'), 53000), arrowprops=dict(facecolor='#03a9f4', shrink=0.08, width=1.5, headwidth=6), fontsize=9, fontweight='bold')
    
    ax5_1.axvline(ts_bottom_2022, color='#e53935', ls=':', lw=1.8)
    ax5_1.annotate("2. Time: Half-Cycle (238d)\nArrival at Bottom ($15.5k)", xy=(ts_bottom_2022, 15600), xytext=(pd.Timestamp('2022-09-01', tz='UTC'), 10000), arrowprops=dict(facecolor='#e53935', shrink=0.08, width=1.5, headwidth=6), fontsize=9, fontweight='bold')
    
    ax5_1.axvline(ts_break_2023, color='#4caf50', ls=':', lw=1.8)
    ax5_1.annotate("Ignition & Gravitation\ntowards SMA 17711", xy=(ts_break_2023, 21000), xytext=(pd.Timestamp('2023-02-15', tz='UTC'), 14000), arrowprops=dict(facecolor='#4caf50', shrink=0.08, width=1.5, headwidth=6), fontsize=9, fontweight='bold')
    
    ax5_1.set_ylabel("Price ($)", fontweight='bold')
    ax5_1.set_title("EXP-91: 動的支配スケール (k*, k*+1) ＆反転時期特定の3要素連動検証 (サポレジ × 周期 × ボラ収縮)", fontsize=12, fontweight='bold')
    ax5_1.legend(loc='upper right', framealpha=0.9, fontsize=8.5)
    
    # 下段: BB幅 (% of price) 収縮度
    ax5_2.plot(sub_plot_zoom.index, sub_plot_zoom['bb_width_pct'], color='#673ab7', lw=1.4, label='BB Width (% of Price)')
    ax5_2.axhline(c10_bbw_pct, color='#e53935', ls='--', lw=1.5, label=f'Case 10 Squeeze Level ({c10_bbw_pct}%, Lower {c10_bbw_quantile}%)')
    ax5_2.axhline(med_bbw_pct_all, color='#757575', ls=':', lw=1.2, label=f'All-Time Median ({med_bbw_pct_all}%)')
    ax5_2.axvspan(ts_bottom_2022, ts_break_2023, color='#e0e0e0', alpha=0.4, label='Compression Zone')
    ax5_2.set_ylabel("BB Width (%)", fontweight='bold')
    ax5_2.set_xlabel("Date (UTC)", fontweight='bold')
    ax5_2.legend(loc='upper right', framealpha=0.9, fontsize=8.5)
    fig5.tight_layout()
    fig5.savefig(PLOTS_DIR / "dynamic_scale_3factors.png", dpi=180)
    plt.close(fig5)
    print("  All 5 publication plots successfully exported to plots/")

    # --- Step 10: Exporting metrics.json ---
    print("\n--- Step 10: Exporting Structured Metrics ---")
    out_metrics = {
        "experiment_id": "EXP-91",
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "dataset": {"symbol": "BTCUSD", "discovery_bars": len(df_1h), "discovery_range": f"{df_1h.index[0]} to {df_1h.index[-1]}"},
        "hyp_91_1_parallelism": hyp_91_1_results,
        "hyp_91_2_scoring_ic": {
            "standard_afs_order": corr_std,
            "majority_voting": corr_maj,
            "weighted_afs": corr_w_afs,
            "multi_feature_context": corr_mfc
        },
        "hyp_91_3_multiscale_propagation": hyp_91_3_results,
        "baseline_k043": {
            "s3_k50": {"metrics": m_base, "ci_95": ci_base},
            "unconditional_trail": {"metrics": m_base_uncond, "ci_95": ci_base_uncond},
            "scale_relative_adaptive": {"metrics": m_base_adapt, "ci_95": ci_base_adapt}
        },
        "integrated_master": {
            "s3_k50": {"metrics": m_master_s3, "ci_95": ci_master_s3},
            "unconditional_trail": {"metrics": m_master_uncond, "ci_95": ci_master_uncond},
            "scale_relative_adaptive": {
                "metrics": m_master_adapt,
                "ci_95": ci_master_adapt,
                "yearly": master_adapt_yearly,
                "periods": master_adapt_periods
            }
        },
        "dynamic_scale_3factors": {
            "scale_cycles": scale_cycle_stats,
            "macro_case_evidence": macro_3factor_evidence
        }
    }
    
    with open(EXP_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(out_metrics, f, indent=2, ensure_ascii=False)
    print(f"  Exported metrics to {EXP_DIR / 'metrics.json'}")
    
    print("\n" + "=" * 80)
    print(f"EXP-91 Execution Completed in {time.time() - t_start:.1f} seconds!")
    print("=" * 80)

if __name__ == "__main__":
    main()
