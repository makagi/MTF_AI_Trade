"""
EXP-93: 動的支配スケール(k*, k*+1)と反転時期の3要素連動（空間サポレジ/真空地帯 × 時間振動周期 × ATR/BB極限収縮）による全スケール汎用・反転点火モデルの検証
Issue #93 完全準拠スクリプト
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
EXP_DIR = Path("03_KNOWLEDGE/experiments/93-dynamic-scale-3factor-ignition")
PLOTS_DIR = EXP_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

HOLDOUT_START = pd.Timestamp("2025-05-01", tz="UTC")
DISCOVERY_START = pd.Timestamp("2020-01-01", tz="UTC")

SCALES = [21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]

# 各スケール固有の理論・実測半周期中央値 (時間換算)
SCALE_T_HALF = {
    21: 12.0, 34: 18.0, 55: 25.0, 89: 45.0, 144: 71.0, 233: 110.0,
    377: 180.0, 610: 320.0, 987: 610.0, 1597: 1000.0, 2584: 1640.0,
    4181: 2700.0, 6765: 4900.0, 10946: 11900.0, 17711: 20000.0
}

SCALE_BANDS = {
    "Band 1 (Fast)": [21, 34, 55],
    "Band 2 (Standard)": [89, 144, 233],
    "Band 3 (Slow)": [377, 610, 987],
    "Band 4 (Super-Macro)": [1597, 2584, 4181, 6765, 10946]
}

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

def simulate_1m_path(events, df_1h, df_1m, mode="adaptive_trail", trail_tp_atr=3.5, trail_lock_atr=1.0, is_lockin_bull_series=None):
    """
    1分足パスでの高精度約定・エグジットシミュレーション
    (K-048 Scale-Relative Adaptive Exit 完全準拠)
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
        
        lockin_flag = False
        if is_lockin_bull_series is not None and t0 in is_lockin_bull_series.index:
            lockin_flag = bool(is_lockin_bull_series.loc[t0])
        else:
            s610 = df_1h['slope_610'].loc[t0] if 'slope_610' in df_1h.columns else 0.0
            s987 = df_1h['slope_987'].loc[t0] if 'slope_987' in df_1h.columns else 0.0
            sma610 = df_1h['sma_610'].loc[t0] if 'sma_610' in df_1h.columns else 0.0
            sma987 = df_1h['sma_987'].loc[t0] if 'sma_987' in df_1h.columns else 0.0
            lockin_flag = bool((s610 > 0.015) and (s987 > 0.015) and (sma610 > sma987))
            
        trail_active = False
        if mode == "trail":
            trail_active = (trail_tp_atr is not None)
        elif mode == "adaptive_trail":
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
                    't0': t0, 'entry_time': entry_time, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - COST_BPS,
                    'duration_h': dur_h, 'exit': exit_type, 'exit_bar': i,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                    'is_lockin_bull': lockin_flag
                })
                exited = True
                break
                
        if not exited:
            p_exit = sub_closes[-1]
            dur_h = float(np.round(n_bars / 60.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'period': p_era,
                'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - COST_BPS,
                'duration_h': dur_h, 'exit': 'timeout_72h', 'exit_bar': n_bars - 1,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)),
                'is_lockin_bull': lockin_flag
            })
            
    return trades

def evaluate_hypo_propagation_fast(df):
    """
    EXP-91 確定知見: Trio 1 (Fast: 21, 55, [89, 144]) ボトムアップ仮説伝播モデル
    """
    c = df['close']
    a = df['atr_24']
    dist_s = (c - df['sma_21']) / a
    dist_m = (c - df['sma_55']) / a
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
    sma55_vals = df['sma_55'].values
    sma89_vals = df['sma_89'].values
    s89_vals = df['slope_89'].values
    s144_vals = df['slope_144'].values
    
    tau_s = 3
    rise_s = 1.0
    tau_m = 8
    rise_m = 2.0
    
    for idx in cand_indices:
        if idx < 150 or idx >= len(df) - 72:
            continue
        cur_c = c_vals[idx]
        cur_a = a_vals[idx]
        if cur_a <= 0:
            continue
            
        p_hypo_s = cur_c + rise_s * cur_a
        old_sum_55 = sma55_vals[idx] * 55
        sub_old_55 = np.sum(c_vals[idx - 55 + 1 : idx - 55 + 1 + tau_s])
        add_hypo_55 = np.sum([cur_c + (k / tau_s) * rise_s * cur_a for k in range(1, tau_s + 1)])
        sma55_hypo = (old_sum_55 - sub_old_55 + add_hypo_55) / 55
        slope55_hypo = (sma55_hypo - sma55_vals[idx]) / (tau_s * cur_a)
        
        if not (p_hypo_s > sma55_hypo and slope55_hypo > 0.008):
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
            
        if s89_vals[idx] < -0.020 and s144_vals[idx] < -0.020:
            continue
            
        old_sum_89 = sma89_vals[idx] * 89
        sub_old_89 = np.sum(c_vals[idx - 89 + 1 : idx - 89 + 1 + tau_m])
        add_hypo_89 = np.sum([cur_c + rise_s * cur_a + (k / tau_m) * rise_m * cur_a for k in range(1, tau_m + 1)])
        sma89_hypo = (old_sum_89 - sub_old_89 + add_hypo_89) / 89
        slope89_hypo = (sma89_hypo - sma89_vals[idx]) / (tau_m * cur_a)
        
        if slope89_hypo > 0.005:
            prop_mask[idx] = True
            
    decl = decluster_events(pd.Series(prop_mask, index=df.index), cooldown_bars=24)
    return df.index[decl]

def main():
    print("=" * 80)
    print("EXP-93: 動的支配スケール(k*, k*+1)と反転時期の3要素連動による全スケール汎用・反転点火モデルの検証")
    print("=" * 80)
    t_start = time.time()
    
    # --- Step 1: Loading Data and Strict Holdout Isolation ---
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
    
    for p in SCALES:
        df_1h[f'sma_{p}'] = calculate_sma(close_1h, p)
        df_1h[f'slope_{p}'] = (df_1h[f'sma_{p}'] - df_1h[f'sma_{p}'].shift(3)) / (3 * atr_1h)
        
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(close_1h, 20, 2.0)
    df_1h['bb_upper'] = bb_upper
    df_1h['bb_mid'] = bb_mid
    df_1h['bb_lower'] = bb_lower
    df_1h['bb_width_atr'] = (bb_upper - bb_lower) / atr_1h
    df_1h['bb_width_pct'] = (bb_upper - bb_lower) / close_1h * 100.0
    
    # 因果的ローリング BB幅パーセンタイル (過去 720h / 30日 窓におけるパーセンタイル、未来参照ゼロ)
    # ベクトル化高速ローリングパーセンタイル
    bb_w_vals = df_1h['bb_width_pct'].values
    bb_pctile_arr = np.full(len(df_1h), np.nan)
    w_len = 720
    for i in range(w_len, len(df_1h)):
        window = bb_w_vals[i - w_len : i + 1]
        bb_pctile_arr[i] = (window <= bb_w_vals[i]).mean()
    df_1h['bb_pctile_720h'] = bb_pctile_arr
    df_1h['bb_pctile_720h'] = df_1h['bb_pctile_720h'].fillna(0.50)
    
    afs_df, _, _ = calculate_afs(df_1h, periods=[7, 9, 11, 13])
    df_1h['afs_7'] = afs_df['AFS_7']
    df_1h['afs_9'] = afs_df['AFS_9']
    df_1h['afs_11'] = afs_df['AFS_11']
    df_1h['afs_13'] = afs_df['AFS_13']
    
    # 6ペア Majority Voting Score (K-047 準拠: IC +0.0096)
    maj_score = (
        (df_1h['afs_7'] > df_1h['afs_9']).astype(int) +
        (df_1h['afs_7'] > df_1h['afs_11']).astype(int) +
        (df_1h['afs_7'] > df_1h['afs_13']).astype(int) +
        (df_1h['afs_9'] > df_1h['afs_11']).astype(int) +
        (df_1h['afs_9'] > df_1h['afs_13']).astype(int) +
        (df_1h['afs_11'] > df_1h['afs_13']).astype(int)
    )
    df_1h['maj_score'] = maj_score
    
    regime_df = calculate_regime_age(df_1h)
    df_1h['macro_age_ratio'] = regime_df['macro_age_ratio']
    
    df_1h['roll_high_720h'] = df_1h['high'].rolling(720).max()
    df_1h['roll_low_720h'] = df_1h['low'].rolling(720).min()
    df_1h['range_pos_720h'] = (close_1h - df_1h['roll_low_720h']) / (df_1h['roll_high_720h'] - df_1h['roll_low_720h'] + 1e-8)
    
    candle_range = high_1h - low_1h
    lower_wick = np.minimum(open_1h, close_1h) - low_1h
    df_1h['wick_ratio'] = np.where(candle_range > 0, lower_wick / candle_range, 0.0)
    
    # 上位長期ペア (SMA 610, 987) の Lock-In Bull 判定 (K-048 準拠)
    is_lockin_bull_higher = (df_1h['slope_610'] > 0.015) & (df_1h['slope_987'] > 0.015) & (df_1h['sma_610'] > df_1h['sma_987'])
    df_1h['is_lockin_bull_higher'] = is_lockin_bull_higher
    
    # --- Step 3: Reproducing Baseline Master Portfolio (EXP-91: N=151) ---
    print("\n--- Step 3: Reproducing Baseline Master Portfolio (EXP-91: N=151) ---")
    meso_raw = (close_1h > df_1h['sma_34']) & (close_1h.shift(1) <= df_1h['sma_34'].shift(1)) & (df_1h['slope_55'] > 0)
    meso_decl = decluster_events(meso_raw, cooldown_bars=24)
    gate_trap = ~(df_1h['macro_age_ratio'] > 2.0)
    gate_booster = (df_1h['afs_7'] > df_1h['afs_9']) & (df_1h['afs_9'] > df_1h['afs_11']) & (df_1h['afs_11'] > df_1h['afs_13'])
    mvc = meso_decl & gate_trap & gate_booster
    
    cond_pb_adj = (close_1h < df_1h['sma_34']) & (close_1h < df_1h['sma_233'])
    cond_pb_higher = (df_1h['slope_610'] > 0) & (df_1h['slope_987'] > 0) & (close_1h > df_1h['sma_987'])
    cond_pb_range = (df_1h['range_pos_720h'] >= 0.35) & (df_1h['range_pos_720h'] <= 0.65)
    cond_pb_trigger = (close_1h > open_1h) & (close_1h > df_1h['sma_21']) & (close_1h.shift(1) <= df_1h['sma_21'].shift(1))
    cond_pb_afs = gate_booster
    pb_raw = cond_pb_adj & cond_pb_higher & cond_pb_range & cond_pb_trigger & cond_pb_afs
    k043_selective_raw = mvc | pb_raw
    
    prop_fast_events = evaluate_hypo_propagation_fast(df_1h)
    mask_fast = pd.Series(False, index=df_1h.index)
    mask_fast.loc[prop_fast_events] = True
    
    master_raw = k043_selective_raw | mask_fast
    master_decl = decluster_events(master_raw, cooldown_bars=24)
    master_base_events = df_1h.index[master_decl]
    assert len(master_base_events) == 151, f"Expected 151 events, got {len(master_base_events)}"
    
    trades_master_base = simulate_1m_path(master_base_events, df_1h, df_1m, mode="adaptive_trail", is_lockin_bull_series=is_lockin_bull_higher)
    m_base = compute_metrics(trades_master_base)
    ci_base = bootstrap_ci(trades_master_base)
    print(f"EXP-91 Master Baseline (N={m_base['executed_trades']}): Net EV = {m_base['net_mean_return_pct']:+.2f}%, PF = {m_base['profit_factor']:.2f}, Worst = {m_base['worst_trade_pct']:+.2f}%, Total Net = {m_base['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_base[0]:+.2f}%, {ci_base[1]:+.2f}%]")

    # --- Step 4: Evaluating HYP-93-1 (空間要素: 由来スケール k* と親 k*+1 真空地帯の普遍性) ---
    print("\n--- Step 4: Evaluating HYP-93-1 (Space: Origin Governing Scale k* & Vacuum Space) ---")
    
    # 4つの代表スケール帯における真空地帯 (Vacuum >= 2.0 ATR) vs 並行重なり (Vacuum < 1.0 ATR)
    # 反転後の将来 72h MFE および 親ライン到達率 (Hit Rate) の検証
    hyp_93_1_results = {}
    high_vals = high_1h.values
    close_vals = close_1h.values
    atr_vals = atr_1h.values
    n_len = len(df_1h)
    
    for band_name, band_scales in SCALE_BANDS.items():
        band_stats = {"vacuum_open": {"mfes": [], "hit_parent": []}, "vacuum_narrow": {"mfes": [], "hit_parent": []}}
        
        for k in band_scales:
            idx_k = SCALES.index(k)
            if idx_k >= len(SCALES) - 1:
                continue
            k_parent = SCALES[idx_k + 1]
            
            sma_k = df_1h[f'sma_{k}']
            sma_parent = df_1h[f'sma_{k_parent}']
            vacuum_atr = (sma_parent - sma_k).abs() / atr_1h
            
            # 直近サポレジ接触: |close - sma_k| <= 1.25 ATR からの反転初動 (SMA_21 奪還)
            contact_reversal = (abs(close_1h - sma_k) / atr_1h <= 1.25) & (close_1h > df_1h['sma_21']) & (close_1h.shift(1) <= df_1h['sma_21'].shift(1))
            cand_indices = np.where(contact_reversal)[0]
            
            for idx in cand_indices:
                if idx < 200 or idx >= n_len - 73:
                    continue
                p_enter = close_vals[idx]
                a_cur = atr_vals[idx]
                if a_cur <= 0:
                    continue
                    
                v_cur = vacuum_atr.iloc[idx]
                h_max = np.max(high_vals[idx+1 : idx+73])
                mfe = (h_max - p_enter) / a_cur
                
                # 親ライン到達判定 (72h 以内に High が親 SMA 水準にタッチしたか)
                parent_val = sma_parent.iloc[idx]
                hit_p = 1.0 if h_max >= parent_val else 0.0
                
                if v_cur >= 2.0:
                    band_stats["vacuum_open"]["mfes"].append(mfe)
                    band_stats["vacuum_open"]["hit_parent"].append(hit_p)
                elif v_cur < 1.0:
                    band_stats["vacuum_narrow"]["mfes"].append(mfe)
                    band_stats["vacuum_narrow"]["hit_parent"].append(hit_p)
                    
        mfe_open = float(np.round(np.mean(band_stats["vacuum_open"]["mfes"]), 2)) if band_stats["vacuum_open"]["mfes"] else 0.0
        mfe_narrow = float(np.round(np.mean(band_stats["vacuum_narrow"]["mfes"]), 2)) if band_stats["vacuum_narrow"]["mfes"] else 0.0
        hit_open = float(np.round(np.mean(band_stats["vacuum_open"]["hit_parent"]) * 100.0, 2)) if band_stats["vacuum_open"]["hit_parent"] else 0.0
        hit_narrow = float(np.round(np.mean(band_stats["vacuum_narrow"]["hit_parent"]) * 100.0, 2)) if band_stats["vacuum_narrow"]["hit_parent"] else 0.0
        n_open = len(band_stats["vacuum_open"]["mfes"])
        n_narrow = len(band_stats["vacuum_narrow"]["mfes"])
        
        hyp_93_1_results[band_name] = {
            "vacuum_open_samples": n_open,
            "vacuum_narrow_samples": n_narrow,
            "avg_mfe_atr": {"vacuum_open": mfe_open, "vacuum_narrow": mfe_narrow},
            "parent_reach_rate_pct": {"vacuum_open": hit_open, "vacuum_narrow": hit_narrow}
        }
        print(f"  [{band_name}]: Vacuum >= 2.0 ATR (N={n_open}): MFE = {mfe_open} ATR, Hit Parent = {hit_open}% vs Narrow < 1.0 ATR (N={n_narrow}): MFE = {mfe_narrow} ATR, Hit Parent = {hit_narrow}%")

    # --- Step 5: Evaluating HYP-93-2 (時間×ボラティリティ同期則) ---
    print("\n--- Step 5: Evaluating HYP-93-2 (Time Cycle Phase vs Squeeze / Parallel Synchronization) ---")
    
    # 各スケール帯において、転換点からの経過時間率 tau_phase が
    # 周期終盤 [0.70, 1.30] にある時と、周期途中 (< 0.60) にある時での
    # BB幅パーセンタイル <= 25% (極限スクイーズ) および 平行束化率の比較
    hyp_93_2_results = {}
    
    # 各スケール k に対する直近サポレジ接触からの経過時間 (バー数) を計算
    for band_name, band_scales in SCALE_BANDS.items():
        late_phase_squeezes = []
        mid_phase_squeezes = []
        late_phase_parallels = []
        mid_phase_parallels = []
        
        for k in band_scales:
            idx_k = SCALES.index(k)
            if idx_k >= len(SCALES) - 1:
                continue
            k_parent = SCALES[idx_k + 1]
            
            t_half = SCALE_T_HALF[k]
            is_contact = (abs(close_1h - df_1h[f'sma_{k}']) / atr_1h) <= 1.25
            
            # 直近接触からの経過バー数を前方累積
            contact_idx = np.where(is_contact)[0]
            if len(contact_idx) == 0:
                continue
                
            # 簡易計算: 接触後の各バーにおける経過時間率
            bars_since = np.full(n_len, np.nan)
            last_c = -999999
            for i in range(n_len):
                if is_contact.iloc[i]:
                    last_c = i
                if last_c >= 0:
                    bars_since[i] = i - last_c
                    
            phase = bars_since / t_half
            
            # 並行度 (SMA_k と SMA_parent の傾き差)
            slope_diff = (df_1h[f'slope_{k}'] - df_1h[f'slope_{k_parent}']).abs()
            is_parallel = slope_diff <= 0.015
            is_squeeze = df_1h['bb_pctile_720h'] <= 0.25
            
            valid_mask = ~np.isnan(phase)
            mask_late = valid_mask & (phase >= 0.70) & (phase <= 1.30)
            mask_mid = valid_mask & (phase >= 0.10) & (phase < 0.60)
            
            if mask_late.sum() > 0:
                late_phase_squeezes.append(is_squeeze[mask_late].mean())
                late_phase_parallels.append(is_parallel[mask_late].mean())
            if mask_mid.sum() > 0:
                mid_phase_squeezes.append(is_squeeze[mask_mid].mean())
                mid_phase_parallels.append(is_parallel[mask_mid].mean())
                
        squeeze_rate_late = float(np.round(np.mean(late_phase_squeezes) * 100.0, 2)) if late_phase_squeezes else 0.0
        squeeze_rate_mid = float(np.round(np.mean(mid_phase_squeezes) * 100.0, 2)) if mid_phase_squeezes else 0.0
        parallel_rate_late = float(np.round(np.mean(late_phase_parallels) * 100.0, 2)) if late_phase_parallels else 0.0
        parallel_rate_mid = float(np.round(np.mean(mid_phase_parallels) * 100.0, 2)) if mid_phase_parallels else 0.0
        
        hyp_93_2_results[band_name] = {
            "squeeze_rate_pct": {"late_phase": squeeze_rate_late, "mid_phase": squeeze_rate_mid},
            "parallel_bundle_rate_pct": {"late_phase": parallel_rate_late, "mid_phase": parallel_rate_mid}
        }
        print(f"  [{band_name}]: Late Phase (tau in [0.7, 1.3]): Squeeze Rate = {squeeze_rate_late}% vs Mid Phase: {squeeze_rate_mid}% | Parallel Rate = {parallel_rate_late}% vs Mid Phase: {parallel_rate_mid}%")

    # --- Step 6: Evaluating HYP-93-3 (3要素連動売買モデル: Gate A 膠着遮断 ＆ Trigger B 真空点火) ---
    print("\n--- Step 6: Evaluating HYP-93-3 (Gate A Parallel Premature Veto & Trigger B Vacuum Ignition) ---")
    
    # 1. Gate A: 平行束・未ブレイク膠着の遮断 (Parallel Premature Entry Veto)
    # 下位〜中位SMA (21, 34, 55, 89, 144) の最大スプレッドが 1.25 ATR 未満 (密集並行束)
    # かつ BB幅パーセンタイル <= 25% (極限スクイーズ中)
    # かつ 価格がまだ束の最高値 SMA を終値で上抜けていない (未点火)
    sma_bundle = pd.concat([df_1h[f'sma_{p}'] for p in [21, 34, 55, 89, 144]], axis=1)
    bundle_max = sma_bundle.max(axis=1)
    bundle_min = sma_bundle.min(axis=1)
    bundle_spread_atr = (bundle_max - bundle_min) / atr_1h
    
    is_parallel_bundle = (bundle_spread_atr <= 1.25)
    is_squeeze_now = (df_1h['bb_pctile_720h'] <= 0.25)
    is_unbroken = (close_1h <= bundle_max)
    
    # 遮断対象: Case 10 型の未点火膠着バー
    veto_gate_a = is_parallel_bundle & is_squeeze_now & is_unbroken
    print(f"Gate A (Premature Parallel Veto) Active Bars: {int(veto_gate_a.sum())} ({veto_gate_a.mean()*100:.2f}%)")
    
    # 2. Trigger B: 3要素同期・真空回帰点火シグナル (3-Factor Vacuum Ignition)
    # ① 空間: 中長期ペア (144/233, 233/377, 377/610) のいずれかに Vacuum >= 2.0 ATR が存在
    has_vacuum_space = (
        ((df_1h['sma_233'] - df_1h['sma_144']).abs() / atr_1h >= 2.0) |
        ((df_1h['sma_377'] - df_1h['sma_233']).abs() / atr_1h >= 2.0) |
        ((df_1h['sma_610'] - df_1h['sma_377']).abs() / atr_1h >= 2.0) |
        ((df_1h['sma_987'] - df_1h['sma_610']).abs() / atr_1h >= 2.0)
    )
    # ② 時間 & ボラ収縮: 直近 48h 以内に極限スクイーズ (BB幅パーセンタイル <= 25%) を通過
    had_squeeze_recent = is_squeeze_now.rolling(48).max().astype(bool)
    
    # ③ 点火ブレイク: 価格が平行束上限を明確に上抜け、かつ Majority Voting AFS >= 5 (整流点火)
    ignition_trigger_b = (
        has_vacuum_space &
        had_squeeze_recent &
        (close_1h > bundle_max + 0.10 * atr_1h) &
        (close_1h.shift(1) <= bundle_max.shift(1) + 0.10 * atr_1h.shift(1)) &
        (df_1h['maj_score'] >= 5) &
        (df_1h['macro_age_ratio'] <= 2.0)
    )
    
    # 3. 各モデルのシミュレーション比較
    # Model 1: EXP-91 Master Baseline (N=151)
    # Model 2: Master + Gate A (早すぎる未ブレイク膠着を除外)
    master_vetoed_mask = master_raw & (~veto_gate_a)
    master_vetoed_decl = decluster_events(master_vetoed_mask, cooldown_bars=24)
    master_vetoed_events = df_1h.index[master_vetoed_decl]
    
    trades_model2 = simulate_1m_path(master_vetoed_events, df_1h, df_1m, mode="adaptive_trail", is_lockin_bull_series=is_lockin_bull_higher)
    m_model2 = compute_metrics(trades_model2)
    ci_model2 = bootstrap_ci(trades_model2)
    
    # Model 3: 3-Factor Synchronized Ignition (Trigger B 単独)
    ign_decl = decluster_events(ignition_trigger_b, cooldown_bars=24)
    ign_events = df_1h.index[ign_decl]
    trades_trigger_b = simulate_1m_path(ign_events, df_1h, df_1m, mode="adaptive_trail", is_lockin_bull_series=is_lockin_bull_higher)
    m_trigger_b = compute_metrics(trades_trigger_b)
    ci_trigger_b = bootstrap_ci(trades_trigger_b)
    
    # Model 4: 統合マスター ＋ Gate A ＋ Trigger B (最上位統合ポートフォリオ)
    master_full_raw = master_vetoed_mask | ignition_trigger_b
    master_full_decl = decluster_events(master_full_raw, cooldown_bars=24)
    master_full_events = df_1h.index[master_full_decl]
    
    trades_full = simulate_1m_path(master_full_events, df_1h, df_1m, mode="adaptive_trail", is_lockin_bull_series=is_lockin_bull_higher)
    m_full = compute_metrics(trades_full)
    ci_full = bootstrap_ci(trades_full)
    
    print("=" * 80)
    print(f"1. BASELINE MASTER (EXP-91) (N={m_base['executed_trades']}): Net EV = {m_base['net_mean_return_pct']:+.2f}%, PF = {m_base['profit_factor']:.2f}, Worst = {m_base['worst_trade_pct']:+.2f}%, Total = {m_base['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_base[0]:+.2f}%, {ci_base[1]:+.2f}%]")
    print(f"2. MASTER + GATE A (VETO) (N={m_model2['executed_trades']}):   Net EV = {m_model2['net_mean_return_pct']:+.2f}%, PF = {m_model2['profit_factor']:.2f}, Worst = {m_model2['worst_trade_pct']:+.2f}%, Total = {m_model2['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_model2[0]:+.2f}%, {ci_model2[1]:+.2f}%]")
    print(f"3. TRIGGER B (STANDALONE) (N={m_trigger_b['executed_trades']}): Net EV = {m_trigger_b['net_mean_return_pct']:+.2f}%, PF = {m_trigger_b['profit_factor']:.2f}, Worst = {m_trigger_b['worst_trade_pct']:+.2f}%, Total = {m_trigger_b['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_trigger_b[0]:+.2f}%, {ci_trigger_b[1]:+.2f}%]")
    print(f"★4. FULL INTEGRATED MASTER (N={m_full['executed_trades']}):     Net EV = {m_full['net_mean_return_pct']:+.2f}%, PF = {m_full['profit_factor']:.2f}, Worst = {m_full['worst_trade_pct']:+.2f}%, Total = {m_full['total_opportunity_net_return_pct']:+.2f}%, CI = [{ci_full[0]:+.2f}%, {ci_full[1]:+.2f}%]")
    print("=" * 80)
    
    full_yearly = compute_yearly_metrics(trades_full)
    full_periods = compute_period_metrics(trades_full)
    
    print("\nFull Integrated Master Period Breakdown:")
    for p_name, p_m in full_periods.items():
        print(f"  {p_name}: N={p_m['executed_trades']}, Net EV = {p_m['net_mean_return_pct']:+.2f}%, PF = {p_m['profit_factor']:.2f}, Worst = {p_m['worst_trade_pct']:+.2f}%")
        
    print("\nFull Integrated Master Yearly Breakdown:")
    for y_str, y_m in full_yearly.items():
        print(f"  {y_str}: N={y_m['executed_trades']}, Net EV = {y_m['net_mean_return_pct']:+.2f}%, PF = {y_m['profit_factor']:.2f}, Total Net = {y_m['total_opportunity_net_return_pct']:+.2f}%")

    # --- Step 7: Generating Publication Figures ---
    print("\n--- Step 7: Rendering Publication Figures ---")
    
    # Figure 1: 4スケール帯における空間×時間周期×ATR/BB収縮の同期分布図
    fig1, (ax1_1, ax1_2) = plt.subplots(1, 2, figsize=(16, 6))
    band_names = list(SCALE_BANDS.keys())
    x = np.arange(len(band_names))
    width = 0.35
    
    sq_late = [hyp_93_2_results[b]["squeeze_rate_pct"]["late_phase"] for b in band_names]
    sq_mid = [hyp_93_2_results[b]["squeeze_rate_pct"]["mid_phase"] for b in band_names]
    r1 = ax1_1.bar(x - width/2, sq_late, width, label='Late Phase (tau in [0.7, 1.3])', color='#1976d2', alpha=0.85)
    r2 = ax1_1.bar(x + width/2, sq_mid, width, label='Mid Phase (tau < 0.6)', color='#757575', alpha=0.7)
    ax1_1.set_xticks(x)
    ax1_1.set_xticklabels(band_names, fontweight='bold')
    ax1_1.set_ylabel("Extreme Squeeze Occurrence Rate (%)", fontweight='bold')
    ax1_1.set_title("Extreme Squeeze Rate: Late Cycle vs Mid Cycle", fontsize=11, fontweight='bold')
    ax1_1.legend(loc='upper right', framealpha=0.9)
    for r in r1:
        ax1_1.annotate(f"{r.get_height():.1f}%", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
    for r in r2:
        ax1_1.annotate(f"{r.get_height():.1f}%", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9)
        
    pl_late = [hyp_93_2_results[b]["parallel_bundle_rate_pct"]["late_phase"] for b in band_names]
    pl_mid = [hyp_93_2_results[b]["parallel_bundle_rate_pct"]["mid_phase"] for b in band_names]
    r3 = ax1_2.bar(x - width/2, pl_late, width, label='Late Phase (tau in [0.7, 1.3])', color='#388e3c', alpha=0.85)
    r4 = ax1_2.bar(x + width/2, pl_mid, width, label='Mid Phase (tau < 0.6)', color='#757575', alpha=0.7)
    ax1_2.set_xticks(x)
    ax1_2.set_xticklabels(band_names, fontweight='bold')
    ax1_2.set_ylabel("Parallel Bundle Formation Rate (%)", fontweight='bold')
    ax1_2.set_title("Parallel Bundle Formation: Late Cycle vs Mid Cycle", fontsize=11, fontweight='bold')
    ax1_2.legend(loc='upper right', framealpha=0.9)
    for r in r3:
        ax1_2.annotate(f"{r.get_height():.1f}%", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
    for r in r4:
        ax1_2.annotate(f"{r.get_height():.1f}%", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9)
        
    fig1.suptitle("EXP-93: 支配スケール周期終盤における極限スクイーズおよび平行束化の統計的同期 (HYP-93-2)", fontsize=13, fontweight='bold')
    fig1.tight_layout()
    fig1.savefig(PLOTS_DIR / "dynamic_scale_3factors_alignment.png", dpi=180)
    plt.close(fig1)

    # Figure 2: 真空地帯幅と将来 MFE・親ライン到達率の相関図
    fig2, (ax2_1, ax2_2) = plt.subplots(1, 2, figsize=(16, 6))
    mfe_op = [hyp_93_1_results[b]["avg_mfe_atr"]["vacuum_open"] for b in band_names]
    mfe_na = [hyp_93_1_results[b]["avg_mfe_atr"]["vacuum_narrow"] for b in band_names]
    b1 = ax2_1.bar(x - width/2, mfe_op, width, label='Vacuum Open (>= 2.0 ATR)', color='#0288d1', alpha=0.85)
    b2 = ax2_1.bar(x + width/2, mfe_na, width, label='Vacuum Narrow (< 1.0 ATR)', color='#d32f2f', alpha=0.7)
    ax2_1.set_xticks(x)
    ax2_1.set_xticklabels(band_names, fontweight='bold')
    ax2_1.set_ylabel("72h MFE (ATR)", fontweight='bold')
    ax2_1.set_title("72h MFE: Open Vacuum vs Narrow Parallel", fontsize=11, fontweight='bold')
    ax2_1.legend(loc='upper right', framealpha=0.9)
    for b in b1:
        ax2_1.annotate(f"{b.get_height():.2f}A", xy=(b.get_x() + b.get_width()/2, b.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
    for b in b2:
        ax2_1.annotate(f"{b.get_height():.2f}A", xy=(b.get_x() + b.get_width()/2, b.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9)
        
    hit_op = [hyp_93_1_results[b]["parent_reach_rate_pct"]["vacuum_open"] for b in band_names]
    hit_na = [hyp_93_1_results[b]["parent_reach_rate_pct"]["vacuum_narrow"] for b in band_names]
    b3 = ax2_2.bar(x - width/2, hit_op, width, label='Vacuum Open (>= 2.0 ATR)', color='#00897b', alpha=0.85)
    b4 = ax2_2.bar(x + width/2, hit_na, width, label='Vacuum Narrow (< 1.0 ATR)', color='#e64a19', alpha=0.7)
    ax2_2.set_xticks(x)
    ax2_2.set_xticklabels(band_names, fontweight='bold')
    ax2_2.set_ylabel("Parent Scale Reach Rate (%)", fontweight='bold')
    ax2_2.set_title("Reach Rate to Parent Scale k*+1", fontsize=11, fontweight='bold')
    ax2_2.legend(loc='upper right', framealpha=0.9)
    for b in b3:
        ax2_2.annotate(f"{b.get_height():.1f}%", xy=(b.get_x() + b.get_width()/2, b.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9, fontweight='bold')
    for b in b4:
        ax2_2.annotate(f"{b.get_height():.1f}%", xy=(b.get_x() + b.get_width()/2, b.get_height()), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9)
        
    fig2.suptitle("EXP-93: 由来スケール k* と親ライン k*+1 真空地帯による上値余地・回帰到達率の拡大 (HYP-93-1)", fontsize=13, fontweight='bold')
    fig2.tight_layout()
    fig2.savefig(PLOTS_DIR / "vacuum_space_mfe_distribution.png", dpi=180)
    plt.close(fig2)

    # Figure 3: 3要素ブレイク点火の実例チャート (2022年冬大底〜2023年新春点火)
    fig3, (ax3_1, ax3_2, ax3_3) = plt.subplots(3, 1, figsize=(15, 11), sharex=True, height_ratios=[2.2, 1.0, 1.0])
    sub_zoom = df_1h.loc['2022-12-15':'2023-01-25']
    ax3_1.plot(sub_zoom.index, sub_zoom['close'], label='BTC/USD Price', color='black', lw=1.5)
    ax3_1.plot(sub_zoom.index, sub_zoom['sma_21'], label='SMA 21', color='#e91e63', lw=1.1)
    ax3_1.plot(sub_zoom.index, sub_zoom['sma_55'], label='SMA 55', color='#9c27b0', lw=1.1)
    ax3_1.plot(sub_zoom.index, sub_zoom['sma_144'], label='SMA 144', color='#3f51b5', lw=1.2)
    ax3_1.plot(sub_zoom.index, sub_zoom['sma_233'], label='SMA 233', color='#00bcd4', lw=1.3)
    ax3_1.plot(sub_zoom.index, sub_zoom['sma_377'], label='SMA 377', color='#4caf50', lw=1.4)
    
    # 点火イベントのマーキング
    ign_in_zoom = [ev for ev in ign_events if ev in sub_zoom.index]
    for ev in ign_in_zoom:
        ax3_1.axvline(ev, color='#d32f2f', ls='--', lw=1.8)
        ax3_1.annotate("3-Factor Ignition!", xy=(ev, sub_zoom.loc[ev, 'close']), xytext=(ev - pd.Timedelta(days=2), sub_zoom.loc[ev, 'close'] + 1500), arrowprops=dict(facecolor='#d32f2f', shrink=0.08, width=1.5, headwidth=6), fontsize=9, fontweight='bold')
        
    ax3_1.set_ylabel("Price ($)", fontweight='bold')
    ax3_1.set_title("EXP-93: 3-Factor Synchronized Vacuum Ignition Case Study (Winter 2022 - Jan 2023)", fontsize=12, fontweight='bold')
    ax3_1.legend(loc='upper left', framealpha=0.9, fontsize=8.5)
    
    # 中段: BB幅パーセンタイル
    ax3_2.plot(sub_zoom.index, sub_zoom['bb_pctile_720h'] * 100.0, color='#673ab7', lw=1.3, label='BB Width Rolling Percentile (%)')
    ax3_2.axhline(25.0, color='#e53935', ls='--', label='Extreme Squeeze Threshold (25%)')
    ax3_2.set_ylabel("BB Squeeze (%)", fontweight='bold')
    ax3_2.legend(loc='upper right', framealpha=0.9, fontsize=8.5)
    
    # 下段: Majority Voting AFS Score
    ax3_3.plot(sub_zoom.index, sub_zoom['maj_score'], color='#0288d1', lw=1.3, label='Majority Voting AFS Score (0..6)')
    ax3_3.axhline(5.0, color='#4caf50', ls='--', label='Ignition Threshold (Score >= 5)')
    ax3_3.set_ylabel("AFS Score", fontweight='bold')
    ax3_3.set_xlabel("Date (UTC)", fontweight='bold')
    ax3_3.legend(loc='upper left', framealpha=0.9, fontsize=8.5)
    
    fig3.tight_layout()
    fig3.savefig(PLOTS_DIR / "multi_scale_ignition_case_study.png", dpi=180)
    plt.close(fig3)

    # Figure 4: ポートフォリオ累積リターン比較
    fig4, ax4 = plt.subplots(figsize=(14, 6.5))
    trade_sets = [
        (f"Baseline Master (EXP-91) (N={len(trades_master_base)})", trades_master_base, '#757575', '--'),
        (f"Master + Gate A (N={len(trades_model2)})", trades_model2, '#1976d2', '-.'),
        (f"Trigger B Standalone (N={len(trades_trigger_b)})", trades_trigger_b, '#ff9800', ':'),
        (f"★ Full Integrated Master (N={len(trades_full)})", trades_full, '#d32f2f', '-')
    ]
    for label, tr_list, col, ls in trade_sets:
        sorted_tr = sorted(tr_list, key=lambda x: x['entry_time'])
        times = [t['entry_time'] for t in sorted_tr]
        cum_rets = np.cumsum([t['net_ret'] * 100.0 for t in sorted_tr])
        ax4.plot(times, cum_rets, label=f"{label} [Net = {cum_rets[-1]:+.1f}%]", color=col, ls=ls, lw=2.2)
        
    ax4.set_ylabel("Cumulative Opportunity Net Return (%)", fontweight='bold')
    ax4.set_title("EXP-93: 3要素連動モデル（膠着遮断 Gate A ＋ 真空点火 Trigger B）による累積リターン向上 (HYP-93-3)", fontsize=13, fontweight='bold')
    ax4.legend(loc='upper left', framealpha=0.9, fontsize=10)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    fig4.tight_layout()
    fig4.savefig(PLOTS_DIR / "portfolio_cumulative_comparison.png", dpi=180)
    plt.close(fig4)

    # Figure 5: パラメータ感度グリッド (真空閾値 x スクイーズパーセンタイル閾値)
    fig5, ax5 = plt.subplots(figsize=(9, 6.5))
    vac_grid = [1.5, 2.0, 2.5, 3.0]
    sq_grid = [0.15, 0.20, 0.25, 0.30]
    pf_matrix = np.zeros((len(vac_grid), len(sq_grid)))
    
    for r_i, v_th in enumerate(vac_grid):
        for c_j, sq_th in enumerate(sq_grid):
            # 簡易感度テスト
            cond_vac_g = (
                ((df_1h['sma_233'] - df_1h['sma_144']).abs() / atr_1h >= v_th) |
                ((df_1h['sma_377'] - df_1h['sma_233']).abs() / atr_1h >= v_th) |
                ((df_1h['sma_610'] - df_1h['sma_377']).abs() / atr_1h >= v_th)
            )
            sq_recent_g = (df_1h['bb_pctile_720h'] <= sq_th).rolling(48).max().astype(bool)
            ign_g = cond_vac_g & sq_recent_g & (close_1h > bundle_max) & (df_1h['maj_score'] >= 5) & (df_1h['macro_age_ratio'] <= 2.0)
            g_raw = master_vetoed_mask | ign_g
            g_decl = decluster_events(g_raw, cooldown_bars=24)
            tr_g = simulate_1m_path(df_1h.index[g_decl], df_1h, df_1m, mode="adaptive_trail", is_lockin_bull_series=is_lockin_bull_higher)
            m_g = compute_metrics(tr_g)
            pf_matrix[r_i, c_j] = m_g['profit_factor']
            
    im = ax5.imshow(pf_matrix, cmap='YlGn', origin='lower')
    ax5.set_xticks(np.arange(len(sq_grid)))
    ax5.set_yticks(np.arange(len(vac_grid)))
    ax5.set_xticklabels([f"{int(s*100)}%" for s in sq_grid], fontweight='bold')
    ax5.set_yticklabels([f"{v:.1f} ATR" for v in vac_grid], fontweight='bold')
    ax5.set_xlabel("Squeeze Percentile Threshold", fontweight='bold')
    ax5.set_ylabel("Vacuum Space Threshold", fontweight='bold')
    ax5.set_title("EXP-93: Sensitivity Grid of Profit Factor (PF)", fontsize=12, fontweight='bold')
    plt.colorbar(im, ax=ax5, label='Profit Factor')
    for i in range(len(vac_grid)):
        for j in range(len(sq_grid)):
            ax5.text(j, i, f"{pf_matrix[i, j]:.2f}", ha='center', va='center', color='black', fontweight='bold')
    fig5.tight_layout()
    fig5.savefig(PLOTS_DIR / "robustness_sensitivity_grid.png", dpi=180)
    plt.close(fig5)
    print("  All 5 publication plots successfully exported to plots/")

    # --- Step 8: Exporting metrics.json ---
    print("\n--- Step 8: Exporting Structured Metrics ---")
    out_metrics = {
        "experiment_id": "EXP-93",
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "dataset": {"symbol": "BTCUSD", "discovery_bars": len(df_1h), "discovery_range": f"{df_1h.index[0]} to {df_1h.index[-1]}"},
        "hyp_93_1_vacuum_space": hyp_93_1_results,
        "hyp_93_2_phase_squeeze_sync": hyp_93_2_results,
        "models_comparison": {
            "model_1_baseline_master": {"metrics": m_base, "ci_95": ci_base},
            "model_2_master_gate_a_veto": {"metrics": m_model2, "ci_95": ci_model2},
            "model_3_trigger_b_standalone": {"metrics": m_trigger_b, "ci_95": ci_trigger_b},
            "model_4_full_integrated_master": {
                "metrics": m_full,
                "ci_95": ci_full,
                "yearly": full_yearly,
                "periods": full_periods
            }
        },
        "robustness_sensitivity": {
            "vacuum_thresholds": vac_grid,
            "squeeze_percentiles": sq_grid,
            "pf_matrix": pf_matrix.tolist()
        }
    }
    
    with open(EXP_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(out_metrics, f, indent=2, ensure_ascii=False)
    print(f"  Exported metrics to {EXP_DIR / 'metrics.json'}")
    
    print("\n" + "=" * 80)
    print(f"EXP-93 Execution Completed in {time.time() - t_start:.1f} seconds!")
    print("=" * 80)

if __name__ == "__main__":
    main()
