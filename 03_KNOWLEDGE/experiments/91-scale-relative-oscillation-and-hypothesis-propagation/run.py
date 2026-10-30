"""
EXP-91: 相対的時間スケールにおける長期並行往復振動・AFS深層分解・
        ボトムアップ仮説伝播（短期下がりようがない場面→中期特徴量前方計算→長期動態見極め）の定量実証
Issue #91 完全準拠スクリプト
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

def simulate_1m_path(events, df_1h, df_1m, mode="s3_k50", trail_tp_atr=None, trail_lock_atr=1.0, rapid_exit=False):
    """
    1分足パスでの高精度約定・エグジットシミュレーション
    mode:
      - s3_k50: 標準S3 (sma_34 - 5.0*atr 割れ損切り, 72hタイムアウト)
      - trail: MFE >= trail_tp_atr (例: 3.5 ATR) 到達でストップを Entry + trail_lock_atr*ATR0 に引き上げ
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
            
            # MFE 更新
            cur_high = sub_highs[i]
            cur_mfe = (cur_high - p0) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe
                
            # トレーリングストップ引き上げチェック
            if trail_tp_atr is not None and not trailed_stop_active:
                if max_mfe_atr >= trail_tp_atr:
                    trailed_stop_active = True
                    
            # 基本ストップ価格
            base_stop = sma34_cur - 5.00 * atr_cur
            if trailed_stop_active:
                # 利益防衛ストップ: Entry + trail_lock_atr * ATR
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
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2))
                }
                trades.append(t_trade)
                exited = True
                break
                
            # 2. 早期失速撤退チェック (Rapid Stall Exit)
            if rapid_exit and (12 * 60 <= i <= 24 * 60):
                # エントリー後 12h〜24h の間で MFE < 0.75 ATR かつ 1h足で SMA 21 終値割れ
                if max_mfe_atr < 0.75 and t_1h in df_1h.index:
                    if df_1h['close'].loc[t_1h] < df_1h['sma_21'].loc[t_1h]:
                        p_exit = sub_opens[i]
                        dur_h = float(np.round(i / 60.0, 2))
                        t_trade = {
                            't0': t0, 'entry_time': entry_time, 'period': p_era,
                            'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - COST_BPS,
                            'duration_h': dur_h, 'exit': 'rapid_stall_exit', 'exit_bar': i,
                            'max_mfe_atr': float(np.round(max_mfe_atr, 2))
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
                'max_mfe_atr': float(np.round(max_mfe_atr, 2))
            }
            trades.append(t_trade)
            
    return trades

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
    print("\n--- Step 2: Calculating Multi-Scale Features (SMA 21~987, BB, AFS, Slopes) ---")
    close_1h = df_1h['close']
    open_1h = df_1h['open']
    high_1h = df_1h['high']
    low_1h = df_1h['low']
    atr_1h = calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr_1h
    
    for p in [21, 34, 55, 89, 144, 233, 377, 610, 987]:
        df_1h[f'sma_{p}'] = calculate_sma(close_1h, p)
        df_1h[f'slope_{p}'] = (df_1h[f'sma_{p}'] - df_1h[f'sma_{p}'].shift(3)) / (3 * atr_1h)
        
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(close_1h, 20, 2.0)
    df_1h['bb_upper'] = bb_upper
    df_1h['bb_mid'] = bb_mid
    df_1h['bb_lower'] = bb_lower
    df_1h['bb_width_atr'] = (bb_upper - bb_lower) / atr_1h
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
    
    trades_base_s3 = simulate_1m_path(k043_events, df_1h, df_1m, mode="s3_k50")
    m_base = compute_metrics(trades_base_s3)
    ci_base = bootstrap_ci(trades_base_s3)
    print(f"Baseline K-043 (N={m_base['executed_trades']}): Net Mean EV = {m_base['net_mean_return_pct']:+.2f}%, PF = {m_base['profit_factor']:.2f}, Worst = {m_base['worst_trade_pct']:+.2f}%, Total Net = {m_base['total_opportunity_net_return_pct']:+.2f}%, 95% CI = [{ci_base[0]:+.2f}%, {ci_base[1]:+.2f}%]")

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
        spread_atr = (df_1h[f'sma_{l1}'] - df_1h[f'sma_{l2}']).abs() / atr_1h
        
        # 定量判定
        is_parallel = (slope_diff <= 0.015) & (s_l1.abs() <= 0.020) & (s_l2.abs() <= 0.020)
        is_lockin_bull = (s_l1 > 0.020) & (s_l2 > 0.020) & (df_1h[f'sma_{l1}'] > df_1h[f'sma_{l2}'])
        is_lockin_bear = (s_l1 < -0.020) & (s_l2 < -0.020) & (df_1h[f'sma_{l1}'] < df_1h[f'sma_{l2}'])
        
        # 48h 往復回数 (SMA S 跨ぎ)
        cross_s = ((close_1h > df_1h[f'sma_{s}']).astype(int).diff().abs() > 0).astype(int)
        cross_48h = cross_s.rolling(48).sum().shift(-48)
        
        # 全戻し率 (+1.5 ATR 順行後にエントリー価格割れ) & MFE 10+ ATR 確率
        mfe_72h_arr = np.full(n_len, np.nan)
        reversal_arr = np.full(n_len, np.nan)
        
        for i in range(1000, n_len - 73, 5):  # 5時間刻みでサンプリング
            p_enter = close_vals[i]
            a_cur = atr_vals[i]
            if a_cur > 0:
                h_max = np.max(high_vals[i+1 : i+73])
                mfe_val = (h_max - p_enter) / a_cur
                mfe_72h_arr[i] = mfe_val
                
                # +1.5 ATR 順行後の全戻しチェック
                reach_15 = np.where(high_vals[i+1 : i+73] >= p_enter + 1.5 * a_cur)[0]
                if len(reach_15) > 0:
                    idx_reach = reach_15[0]
                    # その後に p_enter を割ったか
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
        
        print(f"  [{g_title}]")
        print(f"    Avg 72h MFE: Parallel = {p_mfe_mean} ATR vs Lock-In Bull = {l_mfe_mean} ATR")
        print(f"    Reversal Rate (+1.5 ATR -> Entry): Parallel = {p_rev_rate}% vs Lock-In Bull = {l_rev_rate}%")
        print(f"    MFE >= 10 ATR Prob: Parallel = {p_mfe10_prob}% vs Lock-In Bull = {l_mfe10_prob}%")

    # --- Step 5: HYP-91-2 Evaluation (AFS深層分解・重み付け多数決・SMA/BB多次元スコア) ---
    print("\n--- Step 5: Evaluating HYP-91-2 (AFS Structural Decomposition & Multi-Feature Scoring) ---")
    d_7_9 = df_1h['afs_7'] - df_1h['afs_9']
    d_9_11 = df_1h['afs_9'] - df_1h['afs_11']
    d_11_13 = df_1h['afs_11'] - df_1h['afs_13']
    d_7_13 = df_1h['afs_7'] - df_1h['afs_13']
    acc_7 = df_1h['afs_7'].diff()
    
    # 6ペア多数決スコア
    maj_score = (
        (df_1h['afs_7'] > df_1h['afs_9']).astype(int) +
        (df_1h['afs_7'] > df_1h['afs_11']).astype(int) +
        (df_1h['afs_7'] > df_1h['afs_13']).astype(int) +
        (df_1h['afs_9'] > df_1h['afs_11']).astype(int) +
        (df_1h['afs_9'] > df_1h['afs_13']).astype(int) +
        (df_1h['afs_11'] > df_1h['afs_13']).astype(int)
    )
    
    # 加速度・過熱ペナルティ付き重み付けAFSスコア (0.0 .. 5.0)
    overheat_penalty = (df_1h['afs_13'] > 80).astype(int)
    weighted_afs = (
        1.0 * (d_7_9 > 0).astype(int) +
        1.0 * (d_9_11 > 0).astype(int) +
        1.0 * (d_11_13 > 0).astype(int) +
        1.0 * (d_7_13 > 2.0).astype(int) +
        1.0 * (acc_7 > 0.5).astype(int)
    ) - 1.0 * overheat_penalty
    df_1h['weighted_afs_score'] = weighted_afs.clip(0, 5)
    
    # SMA/BB 多次元統合コンテキストスコア (S_MFC: 0.0 .. 10.0)
    # 1. AFS要素 (0..4)
    c_afs = df_1h['weighted_afs_score'] * (4.0 / 5.0)
    # 2. 中間SMA収縮度 (0..3): 21..144 の最大・最小幅が狭いほど高得点
    sma_mid_list = [df_1h['sma_21'], df_1h['sma_34'], df_1h['sma_55'], df_1h['sma_89'], df_1h['sma_144']]
    sma_mid_max = pd.concat(sma_mid_list, axis=1).max(axis=1)
    sma_mid_min = pd.concat(sma_mid_list, axis=1).min(axis=1)
    sma_spread_atr = (sma_mid_max - sma_mid_min) / atr_1h
    c_sma_squeeze = np.clip(3.0 * (1.0 - (sma_spread_atr - 0.5) / 2.0), 0.0, 3.0)
    # 3. BB幅収縮度 (0..3): BB幅が 2.0 ATR 以下で高得点
    c_bb_squeeze = np.clip(3.0 * (1.0 - (df_1h['bb_width_atr'] - 1.5) / 2.5), 0.0, 3.0)
    
    df_1h['mfc_score'] = c_afs + c_sma_squeeze + c_bb_squeeze
    
    # 識別力比較 (K-038 セットアップ候補バーにおける高スコア群の勝率・EV)
    setup_mask = (close_1h > df_1h['sma_34']) & (df_1h['slope_55'] > 0)
    fwd_ret_24h = (df_1h['close'].shift(-24) - close_1h) / close_1h - COST_BPS
    
    corr_std = float(np.round(order_score[setup_mask].corr(fwd_ret_24h[setup_mask]), 4))
    corr_maj = float(np.round(maj_score[setup_mask].corr(fwd_ret_24h[setup_mask]), 4))
    corr_w_afs = float(np.round(df_1h['weighted_afs_score'][setup_mask].corr(fwd_ret_24h[setup_mask]), 4))
    corr_mfc = float(np.round(df_1h['mfc_score'][setup_mask].corr(fwd_ret_24h[setup_mask]), 4))
    
    print(f"  Setup Conditional Information Coefficient (IC with 24h Net Return):")
    print(f"    Standard afs_order_score (0..3): IC = {corr_std:+.4f}")
    print(f"    Majority Voting Score (0..6):    IC = {corr_maj:+.4f}")
    print(f"    Weighted AFS Score (0..5):       IC = {corr_w_afs:+.4f}")
    print(f"    Multi-Feature Context (S_MFC):   IC = {corr_mfc:+.4f} (Criterion: higher than standard)")

    # --- Step 6: HYP-91-3 Evaluation (ボトムアップ仮説伝播モデル: What-If Forward Propagation) ---
    print("\n--- Step 6: Evaluating HYP-91-3 (Bottom-Up Hypothesis Propagation Model) ---")
    
    # Step 1: 相対的短期安全床検知 (Downside Exhaustion / Safe Floor)
    # 下方に主要支持線 (55, 89, 144, 233, 987) が 1.2 ATR 以内
    min_support_dist = pd.Series(999.0, index=df_1h.index)
    for p in [55, 89, 144, 233, 987]:
        dist_p = (close_1h - df_1h[f'sma_{p}']) / atr_1h
        valid_p = (dist_p >= -0.25) & (dist_p <= 1.25)
        min_support_dist = np.where(valid_p, np.minimum(min_support_dist, dist_p), min_support_dist)
        
    cond_safe_floor = (
        (min_support_dist <= 1.25) &
        ((df_1h['wick_ratio'] >= 0.30) | (close_1h <= df_1h['bb_lower'] + 0.5 * atr_1h)) &
        (df_1h['afs_7'] >= df_1h['afs_7'].shift(1)) &
        (df_1h['macro_age_ratio'] <= 2.0)
    )
    
    # Step 2: 短期仮説注入 (tau_S = 3 bars, +1.0 ATR) による中期特徴量前方計算
    # P_hypo(t+3) = close + 1.0 * atr
    # SMA_34, SMA_55 の前方傾き
    p_hypo_3 = close_1h + 1.0 * atr_1h
    sma34_hypo = (df_1h['sma_34'] * 34 - close_1h.shift(31).fillna(close_1h) - close_1h.shift(32).fillna(close_1h) - close_1h.shift(33).fillna(close_1h) + close_1h + 0.33*atr_1h + close_1h + 0.67*atr_1h + p_hypo_3) / 34
    sma55_hypo = (df_1h['sma_55'] * 55 - close_1h.shift(52).fillna(close_1h) - close_1h.shift(53).fillna(close_1h) - close_1h.shift(54).fillna(close_1h) + close_1h + 0.33*atr_1h + close_1h + 0.67*atr_1h + p_hypo_3) / 55
    slope55_hypo = (sma55_hypo - df_1h['sma_55']) / (3 * atr_1h)
    
    cond_step2_chain = (
        cond_safe_floor &
        (p_hypo_3 > sma34_hypo) &
        (slope55_hypo > 0.010) &
        (df_1h['weighted_afs_score'] >= 3)
    )
    
    # Step 3: 中期仮説注入 (tau_M = 12 bars, +2.5 ATR) による長期動態見極め
    # 15本後: P_hypo(t+15) = close + 3.5 * atr
    # 長期 SMA 144 の前方傾き転換および長期並行チャネルからの脱出
    sma144_hypo = df_1h['sma_144'] + (3.5 * atr_1h * 15) / (2 * 144)
    slope144_hypo = (sma144_hypo - df_1h['sma_144']) / (15 * atr_1h)
    
    # 長期ペア (610, 987) の壊滅的急降下（ベア相場）中でないこと (K-044 鉄則遵守)
    not_deep_bear = ~((df_1h['slope_610'] < -0.020) & (df_1h['slope_987'] < -0.020))
    
    cond_step3_prop = (
        cond_step2_chain &
        (slope144_hypo > 0.008) &
        not_deep_bear &
        (df_1h['mfc_score'] >= 5.5)
    )
    
    prop_decl = decluster_events(cond_step3_prop, cooldown_bars=24)
    prop_events = df_1h.index[prop_decl]
    print(f"HYP-91-3 Hypothesis Propagation Independent Events: {len(prop_events)}")
    
    # 1m パス執行シミュレーション (単独)
    trades_prop_s3 = simulate_1m_path(prop_events, df_1h, df_1m, mode="s3_k50")
    m_prop_s3 = compute_metrics(trades_prop_s3)
    ci_prop_s3 = bootstrap_ci(trades_prop_s3)
    print(f"  HYP-91-3 Standalone (S3_k50): N = {m_prop_s3['executed_trades']}, Net Mean EV = {m_prop_s3['net_mean_return_pct']:+.2f}%, PF = {m_prop_s3['profit_factor']:.2f}, Worst = {m_prop_s3['worst_trade_pct']:+.2f}%, Total Net = {m_prop_s3['total_opportunity_net_return_pct']:+.2f}%, 95% CI = [{ci_prop_s3[0]:+.2f}%, {ci_prop_s3[1]:+.2f}%]")

    # --- Step 7: C2 Remediation Strategy (MFE Trailing & Rapid Stall Exit) ---
    print("\n--- Step 7: Evaluating C2 Remediation Strategies on Baseline & Integrated Portfolios ---")
    
    # 7A: ベースラインに対する利確・利益防衛トレーリング (+3.5 ATR 到達でストップを Entry + 1.0 ATR にロック)
    trades_base_trail = simulate_1m_path(k043_events, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0)
    m_base_trail = compute_metrics(trades_base_trail)
    ci_base_trail = bootstrap_ci(trades_base_trail)
    print(f"  Baseline + MFE Trail (+3.5 ATR Lock): N = {m_base_trail['executed_trades']}, Net EV = {m_base_trail['net_mean_return_pct']:+.2f}%, PF = {m_base_trail['profit_factor']:.2f}, Worst = {m_base_trail['worst_trade_pct']:+.2f}%, Total Net = {m_base_trail['total_opportunity_net_return_pct']:+.2f}%")
    
    # 7B: ベースラインに対する利益防衛トレーリング ＋ 早期失速撤退 (Rapid Stall Exit)
    trades_base_remedy = simulate_1m_path(k043_events, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0, rapid_exit=True)
    m_base_remedy = compute_metrics(trades_base_remedy)
    ci_base_remedy = bootstrap_ci(trades_base_remedy)
    print(f"  Baseline + Trail + Rapid Stall Exit: N = {m_base_remedy['executed_trades']}, Net EV = {m_base_remedy['net_mean_return_pct']:+.2f}%, PF = {m_base_remedy['profit_factor']:.2f}, Worst = {m_base_remedy['worst_trade_pct']:+.2f}%, Total Net = {m_base_remedy['total_opportunity_net_return_pct']:+.2f}%")

    # --- Step 8: Integrated Master Portfolio Evaluation ---
    print("\n--- Step 8: Evaluating Integrated Master Portfolios ---")
    
    # 統合シグナル: Baseline (K-043 104件) OR HYP-91-3 (Prop 救出)
    master_raw = k043_selective_raw | cond_step3_prop
    master_decl = decluster_events(master_raw, cooldown_bars=24)
    master_events = df_1h.index[master_decl]
    print(f"Integrated Master Independent Events Identified: {len(master_events)}")
    
    # 8A: Master + S3_k50
    trades_master_s3 = simulate_1m_path(master_events, df_1h, df_1m, mode="s3_k50")
    m_master_s3 = compute_metrics(trades_master_s3)
    ci_master_s3 = bootstrap_ci(trades_master_s3)
    
    # 8B: Master + C2 Remediation (Trail 3.5 ATR Lock + Rapid Stall Exit)
    trades_master_remedy = simulate_1m_path(master_events, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0, rapid_exit=True)
    m_master_remedy = compute_metrics(trades_master_remedy)
    ci_master_remedy = bootstrap_ci(trades_master_remedy)
    
    print("=" * 80)
    print(f"1. BASELINE K-043 (N={m_base['executed_trades']}): Net EV = {m_base['net_mean_return_pct']:+.2f}%, PF = {m_base['profit_factor']:.2f}, Worst = {m_base['worst_trade_pct']:+.2f}%, Cumulative = {m_base['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_base[0]:+.2f}%, {ci_base[1]:+.2f}%]")
    print(f"2. MASTER S3 (N={m_master_s3['executed_trades']}):       Net EV = {m_master_s3['net_mean_return_pct']:+.2f}%, PF = {m_master_s3['profit_factor']:.2f}, Worst = {m_master_s3['worst_trade_pct']:+.2f}%, Cumulative = {m_master_s3['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_master_s3[0]:+.2f}%, {ci_master_s3[1]:+.2f}%]")
    print(f"★3. MASTER REMEDY (N={m_master_remedy['executed_trades']}):   Net EV = {m_master_remedy['net_mean_return_pct']:+.2f}%, PF = {m_master_remedy['profit_factor']:.2f}, Worst = {m_master_remedy['worst_trade_pct']:+.2f}%, Cumulative = {m_master_remedy['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_master_remedy[0]:+.2f}%, {ci_master_remedy[1]:+.2f}%]")
    print("=" * 80)
    
    # 年別・期間別内訳
    master_remedy_yearly = compute_yearly_metrics(trades_master_remedy)
    master_remedy_periods = compute_period_metrics(trades_master_remedy)
    
    print("\nMaster Remedy Period Breakdown:")
    for p_name, p_m in master_remedy_periods.items():
        print(f"  {p_name}: N={p_m['executed_trades']}, Net EV = {p_m['net_mean_return_pct']:+.2f}%, PF = {p_m['profit_factor']:.2f}, Worst = {p_m['worst_trade_pct']:+.2f}%")

    print("\nMaster Remedy Yearly Breakdown:")
    for y_str, y_m in master_remedy_yearly.items():
        print(f"  {y_str}: N={y_m['executed_trades']}, Net EV = {y_m['net_mean_return_pct']:+.2f}%, PF = {y_m['profit_factor']:.2f}, Total Net = {y_m['total_opportunity_net_return_pct']:+.2f}%")

    # --- Step 9: Robustness Sensitivity Grids ---
    print("\n--- Step 9: Generating Robustness Sensitivity Grids ---")
    
    # 9A: 並行チャネル傾き差閾値グリッド
    grid_slope_diff = {}
    for diff_th in [0.010, 0.015, 0.020, 0.025]:
        p_count = 0
        for _, _, _, l1, l2 in scale_groups:
            p_count += int(((df_1h[f'slope_{l1}'] - df_1h[f'slope_{l2}']).abs() <= diff_th).sum())
        grid_slope_diff[f"{diff_th:.3f}"] = {"total_parallel_observations": p_count}
        
    # 9B: 仮説注入 Step 1 上昇幅グリッド (+0.75, +1.00, +1.25, +1.50 ATR)
    grid_rise_results = {}
    for r_atr in [0.75, 1.00, 1.25, 1.50]:
        p_h3 = close_1h + r_atr * atr_1h
        s34_h = (df_1h['sma_34'] * 34 - close_1h.shift(31).fillna(close_1h) - close_1h.shift(32).fillna(close_1h) - close_1h.shift(33).fillna(close_1h) + close_1h + (r_atr/3)*atr_1h + close_1h + (2*r_atr/3)*atr_1h + p_h3) / 34
        s55_h = (df_1h['sma_55'] * 55 - close_1h.shift(52).fillna(close_1h) - close_1h.shift(53).fillna(close_1h) - close_1h.shift(54).fillna(close_1h) + close_1h + (r_atr/3)*atr_1h + close_1h + (2*r_atr/3)*atr_1h + p_h3) / 55
        sl55_h = (s55_h - df_1h['sma_55']) / (3 * atr_1h)
        
        c_step2 = cond_safe_floor & (p_h3 > s34_h) & (sl55_h > 0.010) & (df_1h['weighted_afs_score'] >= 3)
        c_step3 = c_step2 & (slope144_hypo > 0.008) & not_deep_bear & (df_1h['mfc_score'] >= 5.5)
        ev_decl = decluster_events(c_step3, cooldown_bars=24)
        evs = df_1h.index[ev_decl]
        tr = simulate_1m_path(evs, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0, rapid_exit=True)
        grid_rise_results[f"{r_atr:.2f}_ATR"] = compute_metrics(tr)
        print(f"  Hypo Rise {r_atr:.2f} ATR: N = {len(tr)}, Net EV = {grid_rise_results[f'{r_atr:.2f}_ATR']['net_mean_return_pct']:+.2f}%, PF = {grid_rise_results[f'{r_atr:.2f}_ATR']['profit_factor']:.2f}")

    # --- Step 10: Generating Publication Figures ---
    print("\n--- Step 10: Rendering Publication Figures ---")
    
    # Figure 1: 相対スケール別の並行度 vs 将来MFE・全戻し率分離図
    fig1, axes1 = plt.subplots(1, 3, figsize=(18, 5.5), sharey=True)
    for ax, (g_title, _, _, _, _) in zip(axes1, scale_groups):
        res = hyp_91_1_results[g_title]
        categories = ['Parallel\n(Channeling)', 'Lock-In Bull\n(Trend)']
        mfes = [res['avg_72h_mfe_atr']['parallel'], res['avg_72h_mfe_atr']['lockin_bull']]
        revs = [res['reversal_rate_pct']['parallel'], res['reversal_rate_pct']['lockin_bull']]
        
        x = np.arange(len(categories))
        width = 0.35
        
        rects1 = ax.bar(x - width/2, mfes, width, label='Avg 72h MFE (ATR)', color='#1976d2', alpha=0.85)
        ax2 = ax.twinx()
        rects2 = ax2.bar(x + width/2, revs, width, label='Reversal Rate (%)', color='#e53935', alpha=0.85)
        
        ax.set_xticks(x)
        ax.set_xticklabels(categories, fontweight='bold')
        ax.set_title(g_title, fontsize=11, fontweight='bold')
        ax.set_ylabel("MFE (ATR)")
        ax2.set_ylabel("Reversal Back to Entry (%)", color='#e53935')
        ax.set_ylim(0, 8.5)
        ax2.set_ylim(0, 65)
        
        for r in rects1:
            ax.annotate(f"{r.get_height():.2f}A", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
        for r in rects2:
            ax2.annotate(f"{r.get_height():.1f}%", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
            
    fig1.suptitle("EXP-91: 相対的長期SMAペアの並行チャネリング度と方向確定による幾何分離 (HYP-91-1)", fontsize=13, fontweight='bold')
    fig1.tight_layout()
    fig1.savefig(PLOTS_DIR / "parallel_oscillation_separation.png", dpi=180)
    plt.close(fig1)

    # Figure 2: AFS構造分解・SMA/BB多次元スコアと将来リターン情報係数
    fig2, ax2 = plt.subplots(figsize=(10, 5.5))
    score_names = ['Standard afs_order (0..3)', 'Majority Voting (0..6)', 'Weighted AFS (0..5)', 'Multi-Feature S_MFC (0..10)']
    ics = [corr_std, corr_maj, corr_w_afs, corr_mfc]
    colors = ['#757575', '#0288d1', '#00796b', '#388e3c']
    bars = ax2.bar(score_names, ics, color=colors, width=0.55, edgecolor='black', alpha=0.9)
    ax2.axhline(0, color='black', lw=0.8, ls='--')
    ax2.set_ylabel("Information Coefficient (IC with 24h Net Return)", fontweight='bold')
    ax2.set_title("EXP-91: AFS深層分解および多次元コンテキストスコアの識別力比較 (HYP-91-2)", fontsize=12, fontweight='bold')
    ax2.set_ylim(-0.002, max(ics) * 1.3)
    for b in bars:
        h = b.get_height()
        ax2.annotate(f"IC = {h:+.4f}", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 4), textcoords="offset points", ha='center', va='bottom', fontweight='bold', fontsize=10)
    fig2.tight_layout()
    fig2.savefig(PLOTS_DIR / "afs_multifeature_scoring.png", dpi=180)
    plt.close(fig2)

    # Figure 3: ポートフォリオ累積リターン推移比較 (Baseline vs Master vs Master Remedy)
    fig3, ax3 = plt.subplots(figsize=(14, 6.5))
    
    # 累積曲線作成
    all_trade_sets = [
        ("Baseline K-043 (N=104)", trades_base_s3, '#757575', '--'),
        ("Master S3 (N=138)", trades_master_s3, '#1976d2', '-.'),
        ("Master Remedy (Trail+Rapid) (N=138)", trades_master_remedy, '#d32f2f', '-')
    ]
    
    for label, tr_list, col, ls in all_trade_sets:
        sorted_tr = sorted(tr_list, key=lambda x: x['entry_time'])
        times = [t['entry_time'] for t in sorted_tr]
        cum_rets = np.cumsum([t['net_ret'] * 100.0 for t in sorted_tr])
        ax3.plot(times, cum_rets, label=f"{label} [Net = {cum_rets[-1]:+.1f}%]", color=col, ls=ls, lw=2.2)
        
    ax3.set_ylabel("Cumulative Opportunity Net Return (%)", fontweight='bold')
    ax3.set_title("EXP-91: ボトムアップ仮説伝播およびC2防衛エグジットによる累積リターン向上 (HYP-91-3)", fontsize=13, fontweight='bold')
    ax3.legend(loc='upper left', framealpha=0.9, fontsize=10)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    fig3.tight_layout()
    fig3.savefig(PLOTS_DIR / "hypothesis_propagation_portfolio.png", dpi=180)
    plt.close(fig3)
    print("  Publication plots successfully exported to plots/")

    # --- Step 11: Exporting metrics.json ---
    print("\n--- Step 11: Exporting Structured Metrics ---")
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
        "hyp_91_3_propagation_standalone": {
            "metrics": m_prop_s3,
            "ci_95": ci_prop_s3
        },
        "baseline_k043": {
            "s3_k50": {"metrics": m_base, "ci_95": ci_base},
            "trail_35_lock": {"metrics": m_base_trail, "ci_95": ci_base_trail},
            "remedy_trail_rapid": {"metrics": m_base_remedy, "ci_95": ci_base_remedy}
        },
        "integrated_master": {
            "s3_k50": {"metrics": m_master_s3, "ci_95": ci_master_s3},
            "remedy_trail_rapid": {
                "metrics": m_master_remedy,
                "ci_95": ci_master_remedy,
                "yearly": master_remedy_yearly,
                "periods": master_remedy_periods
            }
        },
        "robustness_grids": {
            "parallel_slope_diff": grid_slope_diff,
            "hypo_step1_rise": grid_rise_results
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
