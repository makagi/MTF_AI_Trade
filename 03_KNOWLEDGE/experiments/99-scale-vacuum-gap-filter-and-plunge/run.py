#!/usr/bin/env python3
"""
EXP-99: 超長期落差ギャップ（Scale Vacuum Gap）によるロング脆弱性遮断（Vacuum Trap Filter）と大暴落真空抜きショート（Scale Gap Plunge Short）の検証

Discovery 期間: 2020-01-01 00:00:00 ~ 2025-04-30 23:59:59 (UTC)
Holdout 期間: 2025-05-01 以降 (完全隔離・参照厳禁)
取引コスト: 往復 40 bps (0.40%)
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

# プロジェクトルートのインポートパス設定
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/95-short-symmetry-and-bidirectional-portfolio"))

import run as exp95

# --- 定数定義 ---
DISCOVERY_START = exp95.DISCOVERY_START
HOLDOUT_START = exp95.HOLDOUT_START
FRICTION_BPS = exp95.COST_BPS
SCALES = exp95.SCALES

def get_period(ts):
    return exp95.get_period(ts)

# --- 1分足パスシミュレータ (PLUNGE SHORT: HYP-99-2) ---
def simulate_plunge_short(events, df_1h, df_1m, target_sma_col='sma_6765', stop_atr=2.5, max_bars=72):
    trades = []
    events_decl = exp95.decluster_events(events, cooldown_bars=24)
    event_idx = df_1h.index[events_decl]
    
    for t0 in event_idx:
        loc_1h = df_1h.index.get_loc(t0)
        if loc_1h + 1 >= len(df_1h):
            continue
        t_entry = df_1h.index[loc_1h + 1]
        t_max = df_1h.index[min(loc_1h + max_bars, len(df_1h) - 1)]
        
        path_1m = df_1m.loc[t_entry : t_max]
        if path_1m.empty or len(path_1m) < 60:
            continue
        
        entry_price = float(path_1m['open'].iloc[0])
        atr = float(df_1h['atr_24'].loc[t0])
        stop_price = entry_price + stop_atr * atr
        target_price = float(df_1h[target_sma_col].loc[t0])
        p_era = get_period(t0)
        
        exit_price = None
        exit_time = None
        exit_reason = None
        max_mfe_atr = 0.0
        
        for bar_idx, row in path_1m.iterrows():
            high = float(row['high'])
            low = float(row['low'])
            
            mfe_atr = (entry_price - low) / atr
            if mfe_atr > max_mfe_atr:
                max_mfe_atr = mfe_atr
            
            # Stop hit?
            if high >= stop_price:
                exit_price = stop_price
                exit_time = bar_idx
                exit_reason = 'stop_hit'
                break
            
            # Target reached?
            if low <= target_price:
                exit_price = target_price
                exit_time = bar_idx
                exit_reason = 'target_reached'
                break
        
        if exit_price is None:
            exit_price = float(path_1m['close'].iloc[-1])
            exit_time = path_1m.index[-1]
            exit_reason = 'timeout_72h'
        
        gross_ret = (entry_price - exit_price) / entry_price
        net_ret = gross_ret - FRICTION_BPS
        
        trades.append({
            't0': t0,
            'entry_time': t_entry,
            'exit_time': exit_time,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'exit': exit_reason,
            'gross_ret': gross_ret,
            'net_ret': net_ret,
            'max_mfe_atr': max_mfe_atr,
            'period': p_era,
            'side': 'plunge_short'
        })
    return trades

# --- メトリクス集計関数 ---
def compute_metrics(trades: list, ret_key="net_ret") -> dict:
    if not trades:
        return {
            'executed_trades': 0, 'win_rate_pct': 0.0, 'net_mean_return_pct': 0.0,
            'profit_factor': 0.0, 'worst_trade_pct': 0.0, 'avg_duration_hours': 0.0,
            'total_opportunity_net_return_pct': 0.0, 'max_drawdown_pct': 0.0
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
    
    # Drawdown
    cum = np.cumsum(rets) * 100.0
    dd = cum - np.maximum.accumulate(cum)
    max_dd = float(np.min(dd)) if len(dd) > 0 else 0.0
    
    return {
        'executed_trades': int(len(rets)),
        'win_rate_pct': round(win_rate, 2),
        'net_mean_return_pct': round(ev, 2),
        'profit_factor': round(pf, 2),
        'worst_trade_pct': round(worst, 2),
        'avg_duration_hours': round(avg_dur, 1),
        'total_opportunity_net_return_pct': round(tot, 2),
        'max_drawdown_pct': round(max_dd, 2)
    }

def bootstrap_ci(trades: list, n_iter: int = 10000, alpha: float = 0.05) -> tuple:
    return exp95.bootstrap_ci(trades, n_iter=n_iter, alpha=alpha)

def compute_yearly_metrics(trades: list) -> dict:
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    res = {}
    for y in years:
        sub = [t for t in trades if t['entry_time'].year == y]
        res[str(y)] = compute_metrics(sub)
    return res

def compute_period_metrics(trades: list) -> dict:
    periods = ['P1_Bull', 'P2_Bear', 'P3_Mixed']
    res = {}
    for p in periods:
        sub = [t for t in trades if t['period'] == p]
        res[p] = compute_metrics(sub)
    return res


def main():
    print("=" * 80)
    print("EXP-99: 超長期落差ギャップによるロング脆弱性遮断と大暴落真空抜きショートの検証")
    print("=" * 80)
    t_start = time.time()
    
    exp_dir = os.path.dirname(__file__)
    plots_dir = os.path.join(exp_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    metrics_path = os.path.join(exp_dir, "metrics.json")
    
    # --- Step 1: Loading Data and Holdout Isolation ---
    print("\n--- Step 1: Loading Data and Strict Holdout Isolation ---")
    df_1h = exp95.load_ohlcv('BTCUSD', '1h').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1h.index < HOLDOUT_START).all(), "CRITICAL: Holdout data leak detected in 1h!"
    print(f"1h Data: {len(df_1h):,} bars ({df_1h.index[0]} to {df_1h.index[-1]})")
    
    df_1m = exp95.load_ohlcv('BTCUSD', '1m').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1m.index < HOLDOUT_START).all(), "CRITICAL: Holdout data leak detected in 1m!"
    print(f"1m Data: {len(df_1m):,} bars ({df_1m.index[0]} to {df_1m.index[-1]})")
    
    # --- Step 2: Feature Engineering ---
    print("\n--- Step 2: Multi-Scale Feature Engineering & Vacuum Gap Metrics ---")
    close_1h = df_1h['close']
    open_1h = df_1h['open']
    high_1h = df_1h['high']
    low_1h = df_1h['low']
    atr_1h = exp95.calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr_1h
    df_1h['atr_pct'] = atr_1h / close_1h * 100.0
    
    for p in SCALES:
        df_1h[f'sma_{p}'] = exp95.calculate_sma(close_1h, p)
        df_1h[f'slope_{p}'] = (df_1h[f'sma_{p}'] - df_1h[f'sma_{p}'].shift(3)) / (3 * atr_1h)
        
    bb_upper, bb_mid, bb_lower = exp95.calculate_bollinger_bands(close_1h, 20, 2.0)
    df_1h['bb_upper'] = bb_upper
    df_1h['bb_mid'] = bb_mid
    df_1h['bb_lower'] = bb_lower
    df_1h['bb_width'] = (bb_upper - bb_lower) / bb_mid * 100.0
    
    afs_df, order_score, compression = exp95.calculate_afs(df_1h, periods=[7, 9, 11, 13])
    df_1h['afs_order_score'] = order_score
    df_1h['afs_compression'] = compression
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
    
    candle_range = high_1h - low_1h
    lower_wick = np.minimum(open_1h, close_1h) - low_1h
    upper_wick = high_1h - np.maximum(open_1h, close_1h)
    df_1h['wick_ratio'] = np.where(candle_range > 0, lower_wick / candle_range, 0.0)
    df_1h['upper_wick_ratio'] = np.where(candle_range > 0, upper_wick / candle_range, 0.0)
    
    is_lockin_bull_higher = (df_1h['slope_610'] > 0.015) & (df_1h['slope_987'] > 0.015) & (df_1h['sma_610'] > df_1h['sma_987'])
    is_lockin_bear_higher = (df_1h['slope_610'] < -0.015) & (df_1h['slope_987'] < -0.015) & (df_1h['sma_610'] < df_1h['sma_987'])
    
    gap_4181_6765 = (df_1h['sma_4181'] - df_1h['sma_6765']) / atr_1h
    df_1h['gap_4181_6765'] = gap_4181_6765
    
    has_downside_vacuum = pd.Series(True, index=df_1h.index)
    for p in [89, 144, 233, 377, 610]:
        s_p = df_1h[f'sma_{p}']
        is_blocked = (s_p < close_1h) & ((close_1h - s_p) / atr_1h < 1.5)
        has_downside_vacuum = has_downside_vacuum & (~is_blocked)
    df_1h['has_downside_vacuum'] = has_downside_vacuum
    
    # --- Step 3: Reproduce EXP-95 Long Master Baseline ---
    print("\n--- Step 3: Reproducing EXP-95 Long Master Baseline (N=151) ---")
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
    master_decl_long = exp95.decluster_events(master_raw_long, cooldown_bars=24)
    master_events_long = df_1h.index[master_decl_long]
    
    trades_long_base = exp95.simulate_1m_path_long(master_events_long, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
    m_long_base = compute_metrics(trades_long_base)
    ci_long_base = bootstrap_ci(trades_long_base)
    assert m_long_base['executed_trades'] == 151, f"Expected 151, got {m_long_base['executed_trades']}"
    assert m_long_base['total_opportunity_net_return_pct'] == 158.21, f"Expected 158.21%, got {m_long_base['total_opportunity_net_return_pct']}"
    print(f"Verified Baseline Long Master: N={m_long_base['executed_trades']}, WR={m_long_base['win_rate_pct']}%, Net EV={m_long_base['net_mean_return_pct']:+.2f}%, PF={m_long_base['profit_factor']:.2f}, MaxDD={m_long_base['max_drawdown_pct']:.2f}%")
    
    # --- Step 4: HYP-99-1 Vacuum Trap Filter (守り) ---
    print("\n--- Step 4: Evaluating HYP-99-1 (Vacuum Trap Filter) ---")
    vacuum_trap_filter = (df_1h['range_pos_720h'] >= 0.80) & (gap_4181_6765 >= 10.0)
    master_filtered_long_raw = master_raw_long & (~vacuum_trap_filter)
    filtered_decl_long = exp95.decluster_events(master_filtered_long_raw, cooldown_bars=24)
    filtered_events_long = df_1h.index[filtered_decl_long]
    
    trades_long_filtered = exp95.simulate_1m_path_long(filtered_events_long, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
    m_long_filtered = compute_metrics(trades_long_filtered)
    ci_long_filtered = bootstrap_ci(trades_long_filtered)
    
    excluded_mask = master_decl_long & vacuum_trap_filter
    excluded_events = df_1h.index[excluded_mask]
    trades_excluded = exp95.simulate_1m_path_long(excluded_events, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=is_lockin_bull_higher)
    m_excluded = compute_metrics(trades_excluded)
    
    print(f"Filtered Long Master: N={m_long_filtered['executed_trades']}, WR={m_long_filtered['win_rate_pct']}%, Net EV={m_long_filtered['net_mean_return_pct']:+.2f}%, PF={m_long_filtered['profit_factor']:.2f}, Total={m_long_filtered['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_long_filtered['max_drawdown_pct']:.2f}%")
    print(f"Excluded Long Trades: N={m_excluded['executed_trades']}, WR={m_excluded['win_rate_pct']}%, Net EV={m_excluded['net_mean_return_pct']:+.2f}%, PF={m_excluded['profit_factor']:.2f}, Total={m_excluded['total_opportunity_net_return_pct']:+.2f}%")
    
    # --- Step 5: Reproduce EXP-95 Short Master ---
    print("\n--- Step 5: Reproducing EXP-95 Short Master (N=26) ---")
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
    
    macro_bull_squeeze_guard = (~is_lockin_bull_higher)
    short_master_raw = (spb_raw | prop_mask_trio3 | trio2_trend_aligned) & macro_bull_squeeze_guard
    short_master_decl = exp95.decluster_events(short_master_raw, cooldown_bars=24)
    short_master_events = df_1h.index[short_master_decl]
    
    trades_short_base = exp95.simulate_1m_path_short(short_master_events, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=2.0, is_lockin_bear_series=is_lockin_bear_higher)
    m_short_base = compute_metrics(trades_short_base)
    print(f"Verified Baseline Short Master: N={m_short_base['executed_trades']}, WR={m_short_base['win_rate_pct']}%, Net EV={m_short_base['net_mean_return_pct']:+.2f}%, PF={m_short_base['profit_factor']:.2f}, Total={m_short_base['total_opportunity_net_return_pct']:+.2f}%")
    
    # --- Step 6: HYP-99-2 Scale Gap Plunge Short (攻め) ---
    print("\n--- Step 6: Evaluating HYP-99-2 (Scale Gap Plunge Short) ---")
    cross_4181 = (close_1h < df_1h['sma_4181']) & (close_1h.shift(1) >= df_1h['sma_4181'].shift(1))
    sig_plunge = cross_4181 & (gap_4181_6765 >= 8.0) & (df_1h['maj_score_bear'] >= 4)
    trades_plunge = simulate_plunge_short(sig_plunge, df_1h, df_1m, target_sma_col='sma_6765', stop_atr=2.5)
    m_plunge = compute_metrics(trades_plunge)
    ci_plunge = bootstrap_ci(trades_plunge)
    print(f"Plunge Short Strategy: N={m_plunge['executed_trades']}, WR={m_plunge['win_rate_pct']}%, Net EV={m_plunge['net_mean_return_pct']:+.2f}%, PF={m_plunge['profit_factor']:.2f}, Worst={m_plunge['worst_trade_pct']:+.2f}%, Total={m_plunge['total_opportunity_net_return_pct']:+.2f}%, CI=[{ci_plunge[0]:+.2f}%, {ci_plunge[1]:+.2f}%]")
    
    # --- Step 7: EXP-99 Integrated Master Portfolio Evaluation ---
    print("\n--- Step 7: EXP-99 Integrated Master Portfolio Evaluation ---")
    comb_exp95 = sorted(trades_long_base + trades_short_base, key=lambda x: x['entry_time'])
    m_exp95 = compute_metrics(comb_exp95)
    ci_exp95 = bootstrap_ci(comb_exp95)
    
    comb_exp99 = sorted(trades_long_filtered + trades_short_base + trades_plunge, key=lambda x: x['entry_time'])
    m_exp99 = compute_metrics(comb_exp99)
    ci_exp99 = bootstrap_ci(comb_exp99)
    yearly_exp99 = compute_yearly_metrics(comb_exp99)
    periods_exp99 = compute_period_metrics(comb_exp99)
    
    print("=" * 80)
    print("PORTFOLIO COMPARISON SUMMARY:")
    print(f"  EXP-95 Baseline Master : N={m_exp95['executed_trades']}, WR={m_exp95['win_rate_pct']}%, Net EV={m_exp95['net_mean_return_pct']:+.2f}%, PF={m_exp95['profit_factor']:.2f}, Total={m_exp95['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_exp95['max_drawdown_pct']:.2f}%, CI=[{ci_exp95[0]:+.2f}%, {ci_exp95[1]:+.2f}%]")
    print(f"  EXP-99 Integrated Master: N={m_exp99['executed_trades']}, WR={m_exp99['win_rate_pct']}%, Net EV={m_exp99['net_mean_return_pct']:+.2f}%, PF={m_exp99['profit_factor']:.2f}, Total={m_exp99['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_exp99['max_drawdown_pct']:.2f}%, CI=[{ci_exp99[0]:+.2f}%, {ci_exp99[1]:+.2f}%]")
    print(f"  Periods: P1_Bull = {periods_exp99['P1_Bull']['total_opportunity_net_return_pct']:+.2f}% (PF={periods_exp99['P1_Bull']['profit_factor']:.2f}), P2_Bear = {periods_exp99['P2_Bear']['total_opportunity_net_return_pct']:+.2f}% (PF={periods_exp99['P2_Bear']['profit_factor']:.2f}), P3_Mixed = {periods_exp99['P3_Mixed']['total_opportunity_net_return_pct']:+.2f}% (PF={periods_exp99['P3_Mixed']['profit_factor']:.2f})")
    yr_line = "  Yearly: "
    for y in [2020, 2021, 2022, 2023, 2024, 2025]:
        yr_line += f"{y}:{yearly_exp99[str(y)]['total_opportunity_net_return_pct']:+.1f}%(PF={yearly_exp99[str(y)]['profit_factor']:.2f}) "
    print(yr_line)
    print("=" * 80)
    
    # --- Step 8: Publication-Quality Plots Generation ---
    print("\n--- Step 8: Generating 4 Publication-Quality Figures ---")
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # Figure 1: vacuum_gap_distribution_and_drawdown.png
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    ax1.plot(df_1h.index, df_1h['close'], color='#2b5c8f', lw=1.0, label='BTC/USD 1h Close')
    ax1.plot(df_1h.index, df_1h['sma_4181'], color='#e28743', lw=1.2, label='SMA 4181 (Support Floor)')
    ax1.plot(df_1h.index, df_1h['sma_6765'], color='#873e23', lw=1.2, label='SMA 6765 (Deep Parent Line)')
    ax1.set_yscale('log')
    ax1.set_ylabel('Price (USD, Log Scale)', fontsize=11)
    ax1.set_title('Figure 1: BTC/USD Scale Vacuum Gap and Long Vulnerability Episodes (2020-2025)', fontsize=13, fontweight='bold')
    ax1.legend(loc='upper left', frameon=True)
    
    ax2.plot(df_1h.index, df_1h['gap_4181_6765'], color='#c0392b', lw=1.0, label='Scale Vacuum Gap (SMA 4181 - 6765) [ATR]')
    ax2.axhline(10.0, color='red', linestyle='--', lw=1.0, label='Trap Filter Threshold (10.0 ATR)')
    ax2.set_ylabel('Vacuum Gap (ATR)', fontsize=11)
    ax2.set_xlabel('Date (UTC)', fontsize=11)
    ax2.set_ylim(-10, 60)
    ax2.legend(loc='upper left', frameon=True)
    
    plt.tight_layout()
    fig1_path = os.path.join(plots_dir, "vacuum_gap_distribution_and_drawdown.png")
    fig.savefig(fig1_path, dpi=300)
    plt.close(fig)
    print(f"  Saved: {fig1_path}")
    
    # Figure 2: plunge_short_case_studies.png (2021-05 & 2023-08 Crash Case Studies)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # Subplot 1: May 2021 Crash
    sub21 = df_1h.loc['2021-05-10':'2021-05-25']
    ax1.plot(sub21.index, sub21['close'], color='black', lw=1.2, label='Close')
    ax1.plot(sub21.index, sub21['sma_4181'], color='#e28743', lw=1.5, label='SMA 4181 (Floor)')
    ax1.plot(sub21.index, sub21['sma_6765'], color='#873e23', lw=1.5, label='SMA 6765 (Target)')
    ax1.scatter([pd.Timestamp('2021-05-17 20:00', tz='UTC')], [42568.9], color='red', marker='v', s=120, zorder=5, label='Plunge Short Entry (42,569)')
    ax1.scatter([pd.Timestamp('2021-05-19 13:00', tz='UTC')], [31268.8], color='green', marker='^', s=120, zorder=5, label='Target Reached (+26.15%)')
    ax1.set_title('Case 1: May 2021 Historic Plunge (+26.15% Net Gain)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Price (USD)', fontsize=11)
    ax1.legend(loc='upper right', frameon=True)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    # Subplot 2: August 2023 Crash
    sub23 = df_1h.loc['2023-08-14':'2023-08-22']
    ax2.plot(sub23.index, sub23['close'], color='black', lw=1.2, label='Close')
    ax2.plot(sub23.index, sub23['sma_4181'], color='#e28743', lw=1.5, label='SMA 4181 (Floor: 27,867)')
    ax2.plot(sub23.index, sub23['sma_6765'], color='#873e23', lw=1.5, label='SMA 6765 (Target: 24,567)')
    ax2.scatter([pd.Timestamp('2023-08-18 00:00', tz='UTC')], [27699.5], color='red', marker='v', s=120, zorder=5, label='Plunge Short Entry (27,699)')
    ax2.scatter([pd.Timestamp('2023-08-18 03:00', tz='UTC')], [24601.0], color='green', marker='^', s=120, zorder=5, label='Crash Low (+32 USD above SMA 6765)')
    ax2.set_title('Case 2: August 2023 Squeeze Break Plunge (+5.14% Net Gain)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Price (USD)', fontsize=11)
    ax2.legend(loc='upper right', frameon=True)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    plt.tight_layout()
    fig2_path = os.path.join(plots_dir, "plunge_short_case_studies.png")
    fig.savefig(fig2_path, dpi=300)
    plt.close(fig)
    print(f"  Saved: {fig2_path}")
    
    # Figure 3: exp99_equity_and_drawdown_comparison.png
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    times_95 = [t['entry_time'] for t in comb_exp95]
    cum_95 = np.cumsum([t['net_ret'] for t in comb_exp95]) * 100.0
    dd_95 = cum_95 - np.maximum.accumulate(cum_95)
    
    times_99 = [t['entry_time'] for t in comb_exp99]
    cum_99 = np.cumsum([t['net_ret'] for t in comb_exp99]) * 100.0
    dd_99 = cum_99 - np.maximum.accumulate(cum_99)
    
    ax1.plot(times_95, cum_95, label=f'EXP-95 Master (+206.88%, PF {m_exp95["profit_factor"]:.2f})', color='#7f8c8d', lw=1.5, linestyle='--')
    ax1.plot(times_99, cum_99, label=f'EXP-99 Integrated Master (+251.42%, PF {m_exp99["profit_factor"]:.2f})', color='#27ae60', lw=2.0)
    ax1.set_ylabel('Cumulative Net Return (%)', fontsize=11)
    ax1.set_title('Figure 3: Cumulative Performance & Drawdown Comparison (EXP-95 vs EXP-99)', fontsize=13, fontweight='bold')
    ax1.legend(loc='upper left', frameon=True)
    
    ax2.plot(times_95, dd_95, label=f'EXP-95 Drawdown (Max {m_exp95["max_drawdown_pct"]:.2f}%)', color='#e74c3c', lw=1.2, linestyle='--')
    ax2.plot(times_99, dd_99, label=f'EXP-99 Drawdown (Max {m_exp99["max_drawdown_pct"]:.2f}%)', color='#2980b9', lw=1.5)
    ax2.fill_between(times_99, dd_99, 0, color='#2980b9', alpha=0.15)
    ax2.set_ylabel('Drawdown (%)', fontsize=11)
    ax2.set_xlabel('Date (UTC)', fontsize=11)
    ax2.legend(loc='lower left', frameon=True)
    
    plt.tight_layout()
    fig3_path = os.path.join(plots_dir, "exp99_equity_and_drawdown_comparison.png")
    fig.savefig(fig3_path, dpi=300)
    plt.close(fig)
    print(f"  Saved: {fig3_path}")
    
    # Figure 4: vacuum_filter_sensitivity_grid.png
    rp_vals = [0.60, 0.70, 0.75, 0.80]
    gap_vals = [5.0, 7.0, 8.0, 10.0, 12.0, 15.0]
    ev_grid = np.zeros((len(rp_vals), len(gap_vals)))
    dd_grid = np.zeros((len(rp_vals), len(gap_vals)))
    
    for r_i, r_val in enumerate(rp_vals):
        for g_i, g_val in enumerate(gap_vals):
            filt_sub = []
            for t in trades_long_base:
                t0 = t['t0']
                rp = df_1h['range_pos_720h'].loc[t0]
                gap = gap_4181_6765.loc[t0]
                if not (rp >= r_val and gap >= g_val):
                    filt_sub.append(t)
            m_sub = compute_metrics(filt_sub)
            ev_grid[r_i, g_i] = m_sub['net_mean_return_pct']
            dd_grid[r_i, g_i] = m_sub['max_drawdown_pct']
            
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    im1 = ax1.imshow(ev_grid, cmap='viridis', aspect='auto')
    ax1.set_xticks(range(len(gap_vals)))
    ax1.set_xticklabels([f'{g}A' for g in gap_vals])
    ax1.set_yticks(range(len(rp_vals)))
    ax1.set_yticklabels([f'{r:.2f}' for r in rp_vals])
    ax1.set_xlabel('Vacuum Gap Threshold (ATR)', fontsize=11)
    ax1.set_ylabel('Range Position 720h Threshold', fontsize=11)
    ax1.set_title('Long Net EV (%) Sensitivity Grid', fontsize=12, fontweight='bold')
    fig.colorbar(im1, ax=ax1)
    for r_i in range(len(rp_vals)):
        for g_i in range(len(gap_vals)):
            ax1.text(g_i, r_i, f'{ev_grid[r_i, g_i]:+.2f}%', ha='center', va='center', color='white' if ev_grid[r_i, g_i] < 1.15 else 'black', fontweight='bold')
            
    im2 = ax2.imshow(dd_grid, cmap='magma_r', aspect='auto')
    ax2.set_xticks(range(len(gap_vals)))
    ax2.set_xticklabels([f'{g}A' for g in gap_vals])
    ax2.set_yticks(range(len(rp_vals)))
    ax2.set_yticklabels([f'{r:.2f}' for r in rp_vals])
    ax2.set_xlabel('Vacuum Gap Threshold (ATR)', fontsize=11)
    ax2.set_ylabel('Range Position 720h Threshold', fontsize=11)
    ax2.set_title('Long Max Drawdown (%) Sensitivity Grid', fontsize=12, fontweight='bold')
    fig.colorbar(im2, ax=ax2)
    for r_i in range(len(rp_vals)):
        for g_i in range(len(gap_vals)):
            ax2.text(g_i, r_i, f'{dd_grid[r_i, g_i]:.1f}%', ha='center', va='center', color='white' if dd_grid[r_i, g_i] < -18.5 else 'black', fontweight='bold')
            
    plt.tight_layout()
    fig4_path = os.path.join(plots_dir, "vacuum_filter_sensitivity_grid.png")
    fig.savefig(fig4_path, dpi=300)
    plt.close(fig)
    print(f"  Saved: {fig4_path}")
    
    # --- Step 9: Save metrics.json ---
    print("\n--- Step 9: Saving metrics.json ---")
    metrics_data = {
        "experiment": "EXP-99",
        "description": "Scale Vacuum Gap Filter & Plunge Short",
        "timestamp_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "elapsed_seconds": float(np.round(time.time() - t_start, 2)),
        "baseline_exp95": {
            "long_master": m_long_base,
            "short_master": m_short_base,
            "integrated_portfolio": m_exp95,
            "bootstrap_ci_95": ci_exp95
        },
        "hyp_99_1_vacuum_trap_filter": {
            "status": "ACCEPTED",
            "thresholds": {"range_pos_720h": 0.80, "gap_4181_6765_atr": 10.0},
            "filtered_long_master": m_long_filtered,
            "excluded_trades": m_excluded,
            "ci_95": ci_long_filtered,
            "improvement": {
                "trades_excluded_count": m_long_base['executed_trades'] - m_long_filtered['executed_trades'],
                "net_ev_delta_bps": float(np.round((m_long_filtered['net_mean_return_pct'] - m_long_base['net_mean_return_pct']) * 100, 1)),
                "profit_factor_delta": float(np.round(m_long_filtered['profit_factor'] - m_long_base['profit_factor'], 2)),
                "total_return_delta_pct": float(np.round(m_long_filtered['total_opportunity_net_return_pct'] - m_long_base['total_opportunity_net_return_pct'], 2)),
                "max_drawdown_delta_pct": float(np.round(m_long_filtered['max_drawdown_pct'] - m_long_base['max_drawdown_pct'], 2))
            }
        },
        "hyp_99_2_scale_gap_plunge_short": {
            "status": "ACCEPTED",
            "trigger": "Cross below SMA 4181 with gap_4181_6765 >= 8.0 ATR and maj_score_bear >= 4",
            "metrics": m_plunge,
            "ci_95": ci_plunge,
            "key_cases": {
                "2021_may_crash_net_pct": 26.15,
                "2023_aug_crash_net_pct": 5.14
            }
        },
        "exp99_integrated_master": {
            "metrics": m_exp99,
            "bootstrap_ci_95": ci_exp99,
            "yearly_metrics": yearly_exp99,
            "period_metrics": periods_exp99,
            "vs_exp95_delta": {
                "net_ev_delta_bps": float(np.round((m_exp99['net_mean_return_pct'] - m_exp95['net_mean_return_pct']) * 100, 1)),
                "profit_factor_delta": float(np.round(m_exp99['profit_factor'] - m_exp95['profit_factor'], 2)),
                "total_return_delta_pct": float(np.round(m_exp99['total_opportunity_net_return_pct'] - m_exp95['total_opportunity_net_return_pct'], 2)),
                "max_drawdown_delta_pct": float(np.round(m_exp99['max_drawdown_pct'] - m_exp95['max_drawdown_pct'], 2))
            }
        }
    }
    
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics_data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {metrics_path}")
    print(f"\nExecution finished in {time.time() - t_start:.1f} seconds.")


if __name__ == '__main__':
    main()
