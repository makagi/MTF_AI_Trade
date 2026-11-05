#!/usr/bin/env python3
"""
EXP-109: MTFボリンジャーバンド・レジーム適応型エグジット（トレンド無期限追随 × レンジ動的利確・トレール急加速）による往来相場リターン底上げの検証

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

# --- 定数定義 ---
DISCOVERY_START = exp95.DISCOVERY_START
HOLDOUT_START = exp95.HOLDOUT_START
FRICTION_BPS = exp95.COST_BPS
SCALES = exp95.SCALES

def get_period(ts):
    return exp95.get_period(ts)

def compute_metrics(trades):
    if not trades:
        return {
            'executed_trades': 0, 'win_rate_pct': 0.0, 'net_mean_return_pct': 0.0,
            'profit_factor': 0.0, 'total_opportunity_net_return_pct': 0.0, 'max_drawdown_pct': 0.0,
            'worst_trade_pct': 0.0, 'best_trade_pct': 0.0
        }
    rets = np.array([t['net_ret'] for t in trades])
    n = len(rets)
    wins = rets[rets > 0]
    losses = rets[rets < 0]
    wr = len(wins) / n * 100.0 if n > 0 else 0.0
    ev = float(np.mean(rets)) * 100.0
    tot = float(np.sum(rets)) * 100.0

    gross_win = np.sum(wins) if len(wins) > 0 else 0.0
    gross_loss = np.abs(np.sum(losses)) if len(losses) > 0 else 1e-8
    pf = float(gross_win / gross_loss) if gross_loss > 0 else 999.0

    cum = np.cumsum(rets)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = float(np.min(dd)) * 100.0 if len(dd) > 0 else 0.0

    worst = float(np.min(rets)) * 100.0 if n > 0 else 0.0
    best = float(np.max(rets)) * 100.0 if n > 0 else 0.0

    return {
        'executed_trades': n,
        'win_rate_pct': float(np.round(wr, 2)),
        'net_mean_return_pct': float(np.round(ev, 2)),
        'profit_factor': float(np.round(pf, 2)),
        'total_opportunity_net_return_pct': float(np.round(tot, 2)),
        'max_drawdown_pct': float(np.round(max_dd, 2)),
        'worst_trade_pct': float(np.round(worst, 2)),
        'best_trade_pct': float(np.round(best, 2))
    }

def bootstrap_ci(trades, n_boot=2000, alpha=0.05):
    if not trades:
        return [0.0, 0.0]
    rets = np.array([t['net_ret'] for t in trades]) * 100.0
    rng = np.random.default_rng(42)
    means = [np.mean(rng.choice(rets, size=len(rets), replace=True)) for _ in range(n_boot)]
    return [float(np.round(np.percentile(means, 100 * (alpha / 2)), 2)),
            float(np.round(np.percentile(means, 100 * (1 - alpha / 2)), 2))]

def compute_yearly_metrics(trades):
    df_t = pd.DataFrame(trades)
    if df_t.empty:
        return {}
    out = {}
    for y in [2020, 2021, 2022, 2023, 2024, 2025]:
        sub = [t for t in trades if t['entry_time'].year == y]
        out[str(y)] = compute_metrics(sub)
    return out

def simulate_regime_adaptive_long(events, df_1h, df_1m,
                                  parent_line_col='bb_mid_240h',
                                  parent_buf_atr=1.0,
                                  regime_mode='adaptive',
                                  enable_squeeze_4h_mid_esc=True,
                                  reclaim_timeout_h=48.0,
                                  initial_risk_atr=3.0):
    """
    EXP-109 レジーム適応型ロングシミュレータ (Scale Relativity, Reclaim Ignition & Dynamic Ratchet):
    - スケール相対的エスカレーション (Reclaim Ignition):
        エントリー建値 p0 が親構造線ストップ (cur_parent_line - 1.0 ATR) 以上の場合:
            即座に親構造線シームレス追随を有効化 (parent_armed = True)。
        エントリー建値 p0 が親構造線ストップ以下の場合 (親構造線より下で拾う深い押し目):
            初期防衛線 initial_stop (p0 - 3.0 ATR) と base_stop (sma_34 - 5.0 ATR) で防御。
            高値が親構造線 cur_parent_line を奪還・上抜け (cur_high >= cur_parent_line) したら、
            無期限親構造線追随へ昇格 (parent_armed = True)。
            48時間以内に親構造線を奪還できなければ timeout_reclaim_failed で早期成行撤退。
    - 単調非減少ラチェット (Monotonic Non-Decreasing Ratchet):
        ラチェットストップは後退・引き下げを許さず、max(current_ratchet_stop, cand_stop) で更新。
    - レジーム適応 (Regime Mode):
        'adaptive': Squeeze期 (bb_width_pct_2160 <= 0.45 かつ abs(bb_slope_240h) <= 0.04 かつ non-lockin)
                    では早期防衛ラチェット [(3.0, 1.0), (4.2, 2.2), (6.0, 3.5), (8.0, 5.0)] と
                    4H BB Mid急加速ストップ (MFE >= 2.5 ATR で bb_mid_80h - 0.5 ATR) を適用。
                    Expansion/Trend期では広域ラチェット [(3.5, 1.0), (5.5, 2.5), (8.0, 4.5)] を適用。
        'static_ratchet': レジーム判別を行わず、全期間一律に広域ラチェットのみを適用。
        'uniform_squeeze': 全期間一律にレンジ用早期引き締め・4H Mid急加速を適用 (反証用実験)。
    - 有効ストップ: max(base_stop, initial_stop, current_ratchet_stop, struct_stop, current_rapid_stop)
    - Discovery期間末 (2025-04-30 23:59) で強制決済 (Holdout完全隔離)
    """
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

        cur_sma34 = df_1h['sma_34'].loc[t0]
        cur_parent_line = df_1h[parent_line_col].loc[t0]
        cur_bb_mid_80 = df_1h['bb_mid_80h'].loc[t0]
        cur_lockin = bool(df_1h['is_mtf_lockin_bull'].loc[t0])
        cur_squeeze = bool(df_1h['is_true_squeeze'].loc[t0])
        atr_cur = atr0

        # 初期防衛線の設定
        parent_armed = (p0 > cur_parent_line - parent_buf_atr * atr0)

        # 単調非減少ストップのトラッカー
        current_ratchet_stop = -999999.0
        current_rapid_stop = -999999.0

        for i in range(n_bars):
            t_bar = sub_times[i]
            elapsed_h = i / 60.0

            if i % 60 == 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    cur_sma34 = df_1h['sma_34'].loc[t_1h]
                    cur_parent_line = df_1h[parent_line_col].loc[t_1h]
                    cur_bb_mid_80 = df_1h['bb_mid_80h'].loc[t_1h]
                    cur_lockin = bool(df_1h['is_mtf_lockin_bull'].loc[t_1h])
                    cur_squeeze = bool(df_1h['is_true_squeeze'].loc[t_1h])
                    atr_cur = df_1h['atr_24'].loc[t_1h]

            cur_high = sub_highs[i]
            cur_low = sub_lows[i]
            cur_open = sub_opens[i]

            cur_mfe = (cur_high - p0) / atr0
            if cur_mfe > max_mfe_atr:
                max_mfe_atr = cur_mfe

            # 親構造線の奪還・上抜けチェック (Promotion to Parent Structure Trailing)
            if not parent_armed and cur_high >= cur_parent_line:
                parent_armed = True

            # 1. ベースストップ (安全フロア: sma_34 - 5.0 ATR)
            base_stop = cur_sma34 - 5.0 * atr_cur

            # 2. 未奪還時の初期リスク防衛線 (Initial Risk Bound)
            if not parent_armed and initial_risk_atr is not None:
                initial_stop = p0 - initial_risk_atr * atr0
            else:
                initial_stop = -999999.0

            # 3. 多段階動的ラチェット (単調非減少)
            if regime_mode == 'static_ratchet':
                tiers = [(3.5, 1.0), (5.5, 2.5), (8.0, 4.5)]
                for trig_mfe, lock_atr in tiers:
                    if max_mfe_atr >= trig_mfe:
                        current_ratchet_stop = max(current_ratchet_stop, p0 + lock_atr * atr0)
            elif regime_mode == 'uniform_squeeze':
                tiers = [(3.0, 1.0), (4.2, 2.2), (6.0, 3.5), (8.0, 5.0)]
                for trig_mfe, lock_atr in tiers:
                    if max_mfe_atr >= trig_mfe:
                        current_ratchet_stop = max(current_ratchet_stop, p0 + lock_atr * atr0)
                if enable_squeeze_4h_mid_esc and max_mfe_atr >= 2.5:
                    current_rapid_stop = max(current_rapid_stop, cur_bb_mid_80 - 0.5 * atr_cur)
            elif regime_mode == 'adaptive':
                is_range_regime = cur_squeeze and (not cur_lockin)
                if is_range_regime:
                    tiers = [(3.0, 1.0), (4.2, 2.2), (6.0, 3.5), (8.0, 5.0)]
                    if enable_squeeze_4h_mid_esc and max_mfe_atr >= 2.5:
                        current_rapid_stop = max(current_rapid_stop, cur_bb_mid_80 - 0.5 * atr_cur)
                else:
                    tiers = [(3.5, 1.0), (5.5, 2.5), (8.0, 4.5)]

                for trig_mfe, lock_atr in tiers:
                    if max_mfe_atr >= trig_mfe:
                        current_ratchet_stop = max(current_ratchet_stop, p0 + lock_atr * atr0)

            # 4. 普遍的親階層動的構造線ストップ (Scale Relativity)
            if parent_armed:
                struct_stop = cur_parent_line - parent_buf_atr * atr_cur
            else:
                struct_stop = base_stop

            # 有効ストップライン
            effective_stop = max(base_stop, initial_stop, current_ratchet_stop, struct_stop, current_rapid_stop)

            # ストップアウト判定
            if cur_low <= effective_stop:
                p_exit = min(cur_open, effective_stop)
                dur_h = float(np.round(elapsed_h, 2))
                if effective_stop == current_rapid_stop and current_rapid_stop > max(base_stop, initial_stop, current_ratchet_stop, struct_stop):
                    exit_type = 'rapid_4h_mid_stop'
                elif effective_stop == current_ratchet_stop and current_ratchet_stop > max(base_stop, initial_stop, struct_stop):
                    exit_type = 'regime_ratchet_lock'
                elif effective_stop == struct_stop and struct_stop > max(base_stop, initial_stop):
                    exit_type = 'parent_scale_exit'
                elif effective_stop == initial_stop and initial_stop > base_stop:
                    exit_type = 'initial_risk_stop'
                else:
                    exit_type = 's3_stop'

                trades.append({
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_bar, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': exit_type,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'is_lockin': cur_lockin,
                    'is_squeeze': cur_squeeze, 'direction': 'long', 'side': 'long'
                })
                exited = True
                break

            # 奪還タイムアウト判定 (親構造線未奪還のまま timeout_h 到達で成行撤退)
            if not parent_armed and reclaim_timeout_h is not None and elapsed_h >= reclaim_timeout_h:
                p_exit = cur_open
                dur_h = float(np.round(elapsed_h, 2))
                trades.append({
                    't0': t0, 'entry_time': entry_time, 'exit_time': t_bar, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': 'timeout_reclaim_failed',
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'is_lockin': cur_lockin,
                    'is_squeeze': cur_squeeze, 'direction': 'long', 'side': 'long'
                })
                exited = True
                break

        if not exited:
            p_exit = sub_closes[-1]
            dur_h = float(np.round(n_bars / 60.0, 2))
            trades.append({
                't0': t0, 'entry_time': entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'is_lockin': cur_lockin,
                'is_squeeze': cur_squeeze, 'direction': 'long', 'side': 'long'
            })

    # 架空0秒決済の完全根絶を保証する厳格アサーション
    dur0_count = sum(1 for t in trades if t['duration_h'] == 0.0)
    assert dur0_count == 0, f"CRITICAL: Found {dur0_count} trades with duration_h == 0.0!"

    return trades

def apply_mode_b_concurrency_limit(trades, max_concurrent=2):
    trades_sorted = sorted(trades, key=lambda x: x['entry_time'])
    pos_active = []
    filtered_trades = []
    for t in trades_sorted:
        t_entry = t['entry_time']
        pos_active = [p for p in pos_active if p['exit_time'] > t_entry]
        if len(pos_active) < max_concurrent:
            filtered_trades.append(t)
            pos_active.append(t)
    return filtered_trades

def main():
    print("=" * 80)
    print("EXP-109: MTFボリンジャーバンド・レジーム適応型エグジットの検証")
    print("=" * 80)
    t_start = time.time()

    exp_dir = os.path.dirname(__file__)
    plots_dir = os.path.join(exp_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    metrics_path = os.path.join(exp_dir, "metrics.json")

    # --- Step 1: Loading Data and Strict Holdout Isolation ---
    print("\n--- Step 1: Loading Data and Strict Holdout Isolation ---")
    df_1h = exp95.load_ohlcv('BTCUSD', '1h').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1h.index < HOLDOUT_START).all(), "CRITICAL: Holdout leak in 1h!"
    print(f"1h Data: {len(df_1h):,} bars ({df_1h.index[0]} to {df_1h.index[-1]})")

    df_1m = exp95.load_ohlcv('BTCUSD', '1m').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert (df_1m.index < HOLDOUT_START).all(), "CRITICAL: Holdout leak in 1m!"
    print(f"1m Data: {len(df_1m):,} bars ({df_1m.index[0]} to {df_1m.index[-1]})")

    # --- Step 2: Multi-Scale Feature Engineering & BB Calculation ---
    print("\n--- Step 2: Multi-Scale Feature Engineering & BB Calculation ---")
    close_1h = df_1h['close']
    open_1h = df_1h['open']
    high_1h = df_1h['high']
    low_1h = df_1h['low']
    atr_1h = exp95.calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr_1h
    df_1h['atr_pct'] = atr_1h / close_1h * 100.0

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
    df_1h['bb_width'] = (bb_upper - bb_lower) / bb_mid * 100.0

    for p in [20, 80, 240, 480]:
        mid = close_1h.rolling(p).mean()
        std = close_1h.rolling(p).std()
        df_1h[f'bb_mid_{p}h'] = mid
        df_1h[f'bb_upper_{p}h'] = mid + 2.0 * std
        df_1h[f'bb_lower_{p}h'] = mid - 2.0 * std
        df_1h[f'bb_width_{p}h'] = (4.0 * std) / mid * 100.0
        df_1h[f'bb_slope_{p}h'] = (mid - mid.shift(3)) / (3 * atr_1h)

    df_4h = df_1h.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    df_4h_mid = df_4h['close'].rolling(20).mean()
    df_4h_std = df_4h['close'].rolling(20).std()
    df_4h['bb_mid_20_4h'] = df_4h_mid
    df_4h['bb_upper_20_4h'] = df_4h_mid + 2.0 * df_4h_std
    df_4h['bb_lower_20_4h'] = df_4h_mid - 2.0 * df_4h_std
    df_4h['bb_width_20_4h'] = (4.0 * df_4h_std) / df_4h_mid * 100.0

    df_1d = df_1h.resample('1D').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    df_1d_mid = df_1d['close'].rolling(20).mean()
    df_1d_std = df_1d['close'].rolling(20).std()
    df_1d['bb_mid_20d'] = df_1d_mid
    df_1d['bb_upper_20d'] = df_1d_mid + 2.0 * df_1d_std
    df_1d['bb_lower_20d'] = df_1d_mid - 2.0 * df_1d_std
    df_1d['bb_width_20d'] = (4.0 * df_1d_std) / df_1d_mid * 100.0
    for p in [50, 100, 200]:
        df_1d[f'sma_{p}d'] = df_1d['close'].rolling(p).mean()

    df_1h = df_1h.join(df_4h[['bb_mid_20_4h', 'bb_upper_20_4h', 'bb_lower_20_4h', 'bb_width_20_4h']].shift(1)).join(
        df_1d[['bb_mid_20d', 'bb_upper_20d', 'bb_lower_20d', 'bb_width_20d', 'sma_200d']].shift(1)
    ).ffill()

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

    df_1h['afs_peak'] = (df_1h['afs_7'].shift(1) >= 0.80) & (df_1h['afs_7'] < df_1h['afs_7'].shift(1))

    regime_df = exp95.calculate_regime_age(df_1h)
    df_1h['macro_age_ratio'] = regime_df['macro_age_ratio']
    roll_high_720h = high_1h.rolling(720, min_periods=72).max()
    roll_low_720h = low_1h.rolling(720, min_periods=72).min()
    df_1h['range_pos_720h'] = (close_1h - roll_low_720h) / (roll_high_720h - roll_low_720h + 1e-8)

    gap_4181_6765 = (df_1h['sma_4181'] - df_1h['sma_6765']) / atr_1h
    df_1h['gap_4181_6765'] = gap_4181_6765

    # 普遍的 MTF Directional Lock-In
    is_mtf_lockin_bull = (df_1h['bb_mid_20h'] > df_1h['bb_mid_80h']) & (df_1h['bb_mid_80h'] > df_1h['bb_mid_480h']) & (df_1h['bb_slope_480h'] > 0)
    df_1h['is_mtf_lockin_bull'] = is_mtf_lockin_bull
    df_1h['is_mtf_parallel'] = (~is_mtf_lockin_bull)

    # 幾何学的 Squeeze 判別器 (因果的ローリングパーセンタイル: 90日=2160h)
    df_1h['bb_width_pct_2160'] = df_1h['bb_width_240h'].rolling(2160, min_periods=120).rank(pct=True)
    df_1h['is_true_squeeze'] = (df_1h['bb_width_pct_2160'] <= 0.45) & (df_1h['bb_slope_240h'].abs() <= 0.04)

    has_downside_vacuum = pd.Series(True, index=df_1h.index)
    for p in [89, 144, 233, 377, 610]:
        s_p = df_1h[f'sma_{p}']
        is_blocked = (s_p < close_1h) & ((close_1h - s_p) / atr_1h < 1.5)
        has_downside_vacuum = has_downside_vacuum & (~is_blocked)
    df_1h['has_downside_vacuum'] = has_downside_vacuum

    # --- Step 3: Reproducing Baseline Trades ---
    print("\n--- Step 3: Reproducing Baseline Trades ---")
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

    # Shorts (Short Master 26 + Plunge Short 4)
    dist_to_sma200d = (close_1h - df_1h['sma_200d']) / close_1h
    is_support_blocked = (gap_4181_6765 < 15.0) & (dist_to_sma200d > 0.0) & (dist_to_sma200d < 0.045)
    cross_4181 = (close_1h < df_1h['sma_4181']) & (close_1h.shift(1) >= df_1h['sma_4181'].shift(1))
    macro_plunge_filter = (df_1h['close'] < df_1h['bb_mid_20d']) & ((df_1h['close'] - df_1h['bb_lower_20d']) / df_1h['bb_lower_20d'] <= 0.03)
    sig_plunge_macro = cross_4181 & (gap_4181_6765 >= 8.0) & (df_1h['maj_score_bear'] >= 4) & (close_1h < df_1h['sma_4181']) & macro_plunge_filter & (~is_support_blocked)
    trades_plunge_refined = exp103.simulate_plunge_short(sig_plunge_macro, df_1h, df_1m, target_sma_col='sma_6765', stop_atr=2.5)

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
    macro_bull_squeeze_guard = (~is_lockin_bull_higher)
    short_master_raw = (spb_raw | prop_mask_trio3 | trio2_trend_aligned) & macro_bull_squeeze_guard
    events_short_master = df_1h.index[exp95.decluster_events(short_master_raw, cooldown_bars=24)]
    trades_short_master = exp95.simulate_1m_path_short(events_short_master, df_1h, df_1m, trail_tp_atr=3.5, trail_lock_atr=1.0)

    # ショート取引辞書への属性付与 (ロングとの完全整合)
    for t in trades_short_master:
        t['side'] = 'short'
        t['direction'] = 'short'
        t_entry_1h = t['entry_time'].floor('1h')
        if t_entry_1h in df_1h.index:
            t['is_squeeze'] = bool(df_1h['is_true_squeeze'].loc[t_entry_1h])
            t['is_lockin'] = bool(df_1h['is_mtf_lockin_bull'].loc[t_entry_1h])
        else:
            t['is_squeeze'] = False
            t['is_lockin'] = False

    for t in trades_plunge_refined:
        t['side'] = 'short'
        t['direction'] = 'short'
        t_entry_1h = t['entry_time'].floor('1h')
        if t_entry_1h in df_1h.index:
            t['is_squeeze'] = bool(df_1h['is_true_squeeze'].loc[t_entry_1h])
            t['is_lockin'] = bool(df_1h['is_mtf_lockin_bull'].loc[t_entry_1h])
        else:
            t['is_squeeze'] = False
            t['is_lockin'] = False

    all_shorts = trades_short_master + trades_plunge_refined

    # --- Step 4: Ablation Studies (Issue #109 Hypotheses) ---
    print("\n--- Step 4: Ablation Studies ---")
    # 0. EXP-107 Baseline (Seamless 10-day line, Single Tier 3.5->1.0)
    trades_long_exp107 = exp107.simulate_seamless_dynamic_long(long_events, df_1h, df_1m, parent_line_col='bb_mid_240h', parent_buf_atr=1.0, range_tp=False)
    for t in trades_long_exp107:
        t['side'] = 'long'
    portfolio_exp107 = sorted(trades_long_exp107 + all_shorts, key=lambda x: x['entry_time'])
    m_exp107 = compute_metrics(portfolio_exp107)
    ym_exp107 = compute_yearly_metrics(portfolio_exp107)
    print(f"EXP-107 Baseline: N={m_exp107['executed_trades']}, Net EV={m_exp107['net_mean_return_pct']:+.2f}%, PF={m_exp107['profit_factor']:.2f}, Tot={m_exp107['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_exp107['max_drawdown_pct']:.2f}%")

    # 1. HYP-109-1: Static Multi-Tier Ratchet (Static across regimes with Reclaim Ignition)
    trades_long_static_ratchet = simulate_regime_adaptive_long(long_events, df_1h, df_1m, regime_mode='static_ratchet', enable_squeeze_4h_mid_esc=False)
    portfolio_static_ratchet = sorted(trades_long_static_ratchet + all_shorts, key=lambda x: x['entry_time'])
    m_static_ratchet = compute_metrics(portfolio_static_ratchet)
    ym_static_ratchet = compute_yearly_metrics(portfolio_static_ratchet)
    print(f"HYP-109-1 (Static Multi-Tier Ratchet): N={m_static_ratchet['executed_trades']}, Net EV={m_static_ratchet['net_mean_return_pct']:+.2f}%, PF={m_static_ratchet['profit_factor']:.2f}, Tot={m_static_ratchet['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_static_ratchet['max_drawdown_pct']:.2f}%")

    # 2. HYP-109-2 (Counter-Hypothesis): Uniform Squeeze across all regimes (No regime separation)
    trades_long_uniform_squeeze = simulate_regime_adaptive_long(long_events, df_1h, df_1m, regime_mode='uniform_squeeze', enable_squeeze_4h_mid_esc=True)
    portfolio_uniform_squeeze = sorted(trades_long_uniform_squeeze + all_shorts, key=lambda x: x['entry_time'])
    m_uniform_squeeze = compute_metrics(portfolio_uniform_squeeze)
    ym_uniform_squeeze = compute_yearly_metrics(portfolio_uniform_squeeze)
    print(f"HYP-109-2 (Uniform Squeeze Across All Regimes): N={m_uniform_squeeze['executed_trades']}, Net EV={m_uniform_squeeze['net_mean_return_pct']:+.2f}%, PF={m_uniform_squeeze['profit_factor']:.2f}, Tot={m_uniform_squeeze['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_uniform_squeeze['max_drawdown_pct']:.2f}%")

    # 3. HYP-109-3: Regime-Adaptive Dynamic Ratchet (Switching between Squeeze and Trend, without 4H Mid esc)
    trades_long_adaptive_no_4h = simulate_regime_adaptive_long(long_events, df_1h, df_1m, regime_mode='adaptive', enable_squeeze_4h_mid_esc=False)
    portfolio_adaptive_no_4h = sorted(trades_long_adaptive_no_4h + all_shorts, key=lambda x: x['entry_time'])
    m_adaptive_no_4h = compute_metrics(portfolio_adaptive_no_4h)
    ym_adaptive_no_4h = compute_yearly_metrics(portfolio_adaptive_no_4h)
    print(f"HYP-109-3 (Regime-Adaptive Ratchet w/o 4H Mid): N={m_adaptive_no_4h['executed_trades']}, Net EV={m_adaptive_no_4h['net_mean_return_pct']:+.2f}%, PF={m_adaptive_no_4h['profit_factor']:.2f}, Tot={m_adaptive_no_4h['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_adaptive_no_4h['max_drawdown_pct']:.2f}%")

    # 4. HYP-109-4 / EXP-109 Master: Regime-Adaptive Dynamic Ratchet + Squeeze 4H Mid Escalation (Full Master)
    trades_long_master = simulate_regime_adaptive_long(long_events, df_1h, df_1m, regime_mode='adaptive', enable_squeeze_4h_mid_esc=True)
    portfolio_exp109_master_a = sorted(trades_long_master + all_shorts, key=lambda x: x['entry_time'])
    m_exp109_master_a = compute_metrics(portfolio_exp109_master_a)
    ym_exp109_master_a = compute_yearly_metrics(portfolio_exp109_master_a)
    ci_a = bootstrap_ci(portfolio_exp109_master_a)
    print(f"EXP-109 Master (Mode A): N={m_exp109_master_a['executed_trades']}, Net EV={m_exp109_master_a['net_mean_return_pct']:+.2f}% 95% CI {ci_a}, PF={m_exp109_master_a['profit_factor']:.2f}, Tot={m_exp109_master_a['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_exp109_master_a['max_drawdown_pct']:.2f}%")

    # Mode B: Concurrency Limit (Max 2)
    portfolio_exp109_master_b = apply_mode_b_concurrency_limit(portfolio_exp109_master_a, max_concurrent=2)
    m_exp109_master_b = compute_metrics(portfolio_exp109_master_b)
    ym_exp109_master_b = compute_yearly_metrics(portfolio_exp109_master_b)
    ci_b = bootstrap_ci(portfolio_exp109_master_b)
    print(f"EXP-109 Master (Mode B Max 2): N={m_exp109_master_b['executed_trades']}, Net EV={m_exp109_master_b['net_mean_return_pct']:+.2f}% 95% CI {ci_b}, PF={m_exp109_master_b['profit_factor']:.2f}, Tot={m_exp109_master_b['total_opportunity_net_return_pct']:+.2f}%, MaxDD={m_exp109_master_b['max_drawdown_pct']:.2f}%")

    # 4H Mid Escalation の実際の発火件数プロファイリング
    n_rapid = sum(1 for t in trades_long_master if t['exit'] == 'rapid_4h_mid_stop')
    n_ratchet = sum(1 for t in trades_long_master if t['exit'] == 'regime_ratchet_lock')
    n_parent = sum(1 for t in trades_long_master if t['exit'] == 'parent_scale_exit')
    n_init_risk = sum(1 for t in trades_long_master if t['exit'] == 'initial_risk_stop')
    n_timeout = sum(1 for t in trades_long_master if t['exit'] == 'timeout_reclaim_failed')
    n_s3 = sum(1 for t in trades_long_master if t['exit'] == 's3_stop')
    print(f"\nLong Exit Type Profile: Total={len(trades_long_master)}, ParentScale={n_parent}, RatchetLock={n_ratchet}, Rapid4HMid={n_rapid}, InitialRiskStop={n_init_risk}, ReclaimTimeout={n_timeout}, S3={n_s3}")

    # --- Step 5: Generating Publication-Grade Visualizations ---
    print("\n--- Step 5: Generating Publication-Grade Visualizations ---")
    plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
    plt.rcParams['axes.edgecolor'] = '#CCCCCC'
    plt.rcParams['axes.linewidth'] = 0.8

    # Plot 1: Ablation Comparison Bar Chart
    fig, axes = plt.subplots(1, 3, figsize=(20, 5))
    labels = ['EXP-107\nBaseline', 'HYP-109-1\nStatic Ratchet', 'HYP-109-2\nUniform Squeeze', 'EXP-109 Master\n(Adaptive)']
    colors = ['#7f7f7f', '#3b82f6', '#ef4444', '#10b981']

    pfs = [m_exp107['profit_factor'], m_static_ratchet['profit_factor'], m_uniform_squeeze['profit_factor'], m_exp109_master_a['profit_factor']]
    evs = [m_exp107['net_mean_return_pct'], m_static_ratchet['net_mean_return_pct'], m_uniform_squeeze['net_mean_return_pct'], m_exp109_master_a['net_mean_return_pct']]
    dds = [m_exp107['max_drawdown_pct'], m_static_ratchet['max_drawdown_pct'], m_uniform_squeeze['max_drawdown_pct'], m_exp109_master_a['max_drawdown_pct']]

    axes[0].bar(labels, pfs, color=colors, alpha=0.85, edgecolor='black')
    axes[0].axhline(2.20, color='red', linestyle='--', linewidth=1.2, label='Target PF >= 2.20')
    axes[0].set_title('Profit Factor (PF)', fontsize=12, fontweight='bold')
    axes[0].grid(True, linestyle=':', alpha=0.6)
    axes[0].legend(loc='upper left')
    for i, v in enumerate(pfs):
        axes[0].text(i, v + 0.08, f"{v:.2f}", ha='center', fontweight='bold')

    axes[1].bar(labels, evs, color=colors, alpha=0.85, edgecolor='black')
    axes[1].axhline(2.10, color='red', linestyle='--', linewidth=1.2, label='Target EV >= +2.10%')
    axes[1].set_title('Net Mean Return (% / Trade)', fontsize=12, fontweight='bold')
    axes[1].grid(True, linestyle=':', alpha=0.6)
    axes[1].legend(loc='upper left')
    for i, v in enumerate(evs):
        axes[1].text(i, v + 0.05, f"{v:+.2f}%", ha='center', fontweight='bold')

    axes[2].bar(labels, dds, color=colors, alpha=0.85, edgecolor='black')
    axes[2].axhline(-15.0, color='red', linestyle='--', linewidth=1.2, label='Target MaxDD <= -15.0%')
    axes[2].set_title('Max Drawdown (%)', fontsize=12, fontweight='bold')
    axes[2].grid(True, linestyle=':', alpha=0.6)
    axes[2].legend(loc='lower left')
    for i, v in enumerate(dds):
        axes[2].text(i, v - 0.6, f"{v:.2f}%", ha='center', fontweight='bold')

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'regime_adaptive_ablation_comparison.png'), dpi=300)
    plt.close()
    print("Saved plots/regime_adaptive_ablation_comparison.png")

    # Plot 2: Cumulative Equity Curve & Drawdown vs EXP-107
    def get_equity_series(trades):
        df_tr = pd.DataFrame(trades).sort_values('exit_time')
        df_tr['cum_ret'] = df_tr['net_ret'].cumsum() * 100.0
        df_tr['peak'] = df_tr['cum_ret'].cummax()
        df_tr['dd'] = df_tr['cum_ret'] - df_tr['peak']
        return df_tr

    eq_107 = get_equity_series(portfolio_exp107)
    eq_109 = get_equity_series(portfolio_exp109_master_a)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})
    ax1.plot(eq_107['exit_time'], eq_107['cum_ret'], label=f"EXP-107 Baseline (PF {m_exp107['profit_factor']:.2f}, Tot {m_exp107['total_opportunity_net_return_pct']:+.1f}%)", color='#64748b', linewidth=1.5, linestyle='--')
    ax1.plot(eq_109['exit_time'], eq_109['cum_ret'], label=f"EXP-109 Master (PF {m_exp109_master_a['profit_factor']:.2f}, Tot {m_exp109_master_a['total_opportunity_net_return_pct']:+.1f}%)", color='#10b981', linewidth=2.0)
    ax1.set_title('EXP-109 Master vs EXP-107: Cumulative Opportunity Net Return (%)', fontsize=13, fontweight='bold')
    ax1.set_ylabel('Cumulative Return (%)', fontsize=11)
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='upper left', fontsize=11)

    ax2.plot(eq_107['exit_time'], eq_107['dd'], label=f"EXP-107 MaxDD {m_exp107['max_drawdown_pct']:.2f}%", color='#64748b', linewidth=1.2, linestyle='--')
    ax2.plot(eq_109['exit_time'], eq_109['dd'], label=f"EXP-109 MaxDD {m_exp109_master_a['max_drawdown_pct']:.2f}%", color='#ef4444', linewidth=1.5)
    ax2.set_ylabel('Drawdown (%)', fontsize=11)
    ax2.set_xlabel('Time (UTC)', fontsize=11)
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend(loc='lower left', fontsize=10)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'equity_and_drawdown_vs_exp107.png'), dpi=300)
    plt.close()
    print("Saved plots/equity_and_drawdown_vs_exp107.png")

    # Plot 3: Yearly and Mode Breakdown
    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    x = np.arange(len(years))
    width = 0.35

    y_107 = [ym_exp107[str(y)]['total_opportunity_net_return_pct'] for y in years]
    y_109 = [ym_exp109_master_a[str(y)]['total_opportunity_net_return_pct'] for y in years]

    axes[0].bar(x - width/2, y_107, width, label='EXP-107 Baseline', color='#94a3b8', edgecolor='black')
    axes[0].bar(x + width/2, y_109, width, label='EXP-109 Master', color='#10b981', edgecolor='black')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(years)
    axes[0].set_title('Yearly Total Net Return Comparison (%)', fontsize=12, fontweight='bold')
    axes[0].set_ylabel('Net Return (%)', fontsize=11)
    axes[0].grid(True, linestyle=':', alpha=0.6)
    axes[0].legend()
    for i in range(len(years)):
        axes[0].text(x[i] - width/2, y_107[i] + (2.0 if y_107[i] >= 0 else -6.0), f"{y_107[i]:+.1f}%", ha='center', fontsize=9)
        axes[0].text(x[i] + width/2, y_109[i] + (2.0 if y_109[i] >= 0 else -6.0), f"{y_109[i]:+.1f}%", ha='center', fontsize=9, fontweight='bold')

    # Mode A vs Mode B Yearly Return
    y_109_b = [ym_exp109_master_b[str(y)]['total_opportunity_net_return_pct'] for y in years]
    axes[1].bar(x - width/2, y_109, width, label='Mode A (Opportunity)', color='#10b981', edgecolor='black')
    axes[1].bar(x + width/2, y_109_b, width, label='Mode B (Max Concurrent 2)', color='#3b82f6', edgecolor='black')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(years)
    axes[1].set_title('EXP-109 Master: Mode A vs Mode B Yearly Net Return (%)', fontsize=12, fontweight='bold')
    axes[1].set_ylabel('Net Return (%)', fontsize=11)
    axes[1].grid(True, linestyle=':', alpha=0.6)
    axes[1].legend()
    for i in range(len(years)):
        axes[1].text(x[i] - width/2, y_109[i] + (2.0 if y_109[i] >= 0 else -6.0), f"{y_109[i]:+.1f}%", ha='center', fontsize=9)
        axes[1].text(x[i] + width/2, y_109_b[i] + (2.0 if y_109_b[i] >= 0 else -6.0), f"{y_109_b[i]:+.1f}%", ha='center', fontsize=9, fontweight='bold')

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'yearly_and_mode_breakdown.png'), dpi=300)
    plt.close()
    print("Saved plots/yearly_and_mode_breakdown.png")

    # Plot 4: MFE vs Duration Scatter Plot by Regime
    df_trades_109 = pd.DataFrame(portfolio_exp109_master_a)
    fig, ax = plt.subplots(figsize=(11, 6))

    # Longs
    long_squeeze = df_trades_109[(df_trades_109['side'] == 'long') & (df_trades_109['is_squeeze'] == True)]
    long_trend = df_trades_109[(df_trades_109['side'] == 'long') & (df_trades_109['is_squeeze'] == False)]

    # Shorts
    short_squeeze = df_trades_109[(df_trades_109['side'] == 'short') & (df_trades_109['is_squeeze'] == True)]
    short_trend = df_trades_109[(df_trades_109['side'] == 'short') & (df_trades_109['is_squeeze'] == False)]

    ax.scatter(long_trend['duration_h'], long_trend['max_mfe_atr'],
               color='#10b981', alpha=0.75, s=60, label=f"Long: Expansion/Trend (N={len(long_trend)})", marker='o', edgecolors='black', linewidth=0.5)
    ax.scatter(long_squeeze['duration_h'], long_squeeze['max_mfe_atr'],
               color='#f59e0b', alpha=0.85, s=60, label=f"Long: Squeeze/Range (N={len(long_squeeze)})", marker='^', edgecolors='black', linewidth=0.5)
    ax.scatter(short_trend['duration_h'], short_trend['max_mfe_atr'],
               color='#6366f1', alpha=0.75, s=60, label=f"Short: Expansion/Plunge (N={len(short_trend)})", marker='s', edgecolors='black', linewidth=0.5)
    ax.scatter(short_squeeze['duration_h'], short_squeeze['max_mfe_atr'],
               color='#ec4899', alpha=0.85, s=60, label=f"Short: Squeeze/Range (N={len(short_squeeze)})", marker='D', edgecolors='black', linewidth=0.5)

    ax.axhline(3.5, color='#10b981', linestyle='--', linewidth=1.0, label='Ratchet Tier 1 (3.5 ATR)')
    ax.axhline(5.5, color='#3b82f6', linestyle='--', linewidth=1.0, label='Ratchet Tier 2 (5.5 ATR)')
    ax.axhline(8.0, color='#8b5cf6', linestyle='--', linewidth=1.0, label='Ratchet Tier 3 (8.0 ATR)')
    ax.set_title('Holding Duration vs Maximum Favorable Excursion (MFE ATR) by Regime & Side (EXP-109 Master)', fontsize=12, fontweight='bold')
    ax.set_xlabel('Holding Duration (Hours)', fontsize=11)
    ax.set_ylabel('Max MFE (ATR)', fontsize=11)
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.legend(loc='upper right', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'mfe_vs_duration_regime_scatter.png'), dpi=300)
    plt.close()
    print("Saved plots/mfe_vs_duration_regime_scatter.png")

    # 100時間超トレンドポジションの平均MFE集計
    t_over_100h = [t for t in portfolio_exp109_master_a if t['duration_h'] >= 100.0]
    avg_mfe_over_100h = float(np.mean([t['max_mfe_atr'] for t in t_over_100h])) if t_over_100h else 0.0
    print(f"\nPositions >= 100h: Count={len(t_over_100h)}, Mean MFE={avg_mfe_over_100h:.2f} ATR")

    # ショート単独収支集計
    shorts_stats = compute_metrics(all_shorts)
    print(f"Shorts Standalone: N={shorts_stats['executed_trades']}, Net EV={shorts_stats['net_mean_return_pct']:+.2f}%, PF={shorts_stats['profit_factor']:.2f}, Tot={shorts_stats['total_opportunity_net_return_pct']:+.2f}%")

    # --- Step 6: Output Metrics JSON ---
    print("\n--- Step 6: Output Metrics JSON ---")
    metrics_payload = {
        'experiment': 'EXP-109',
        'hypothesis': 'MTFボリンジャーバンド・レジーム適応型エグジット（トレンド無期限追随 × レンジ動的利確・トレール急加速）による往来相場リターン底上げの検証',
        'discovery_period': {
            'start': str(DISCOVERY_START),
            'end': str(HOLDOUT_START - pd.Timedelta(seconds=1))
        },
        'friction_bps': FRICTION_BPS * 10000.0,
        'baseline_exp107': {
            'mode_a': m_exp107,
            'yearly_mode_a': ym_exp107
        },
        'ablations': {
            'hyp_109_1_static_ratchet': {
                'mode_a': m_static_ratchet,
                'yearly': ym_static_ratchet
            },
            'hyp_109_2_uniform_squeeze': {
                'mode_a': m_uniform_squeeze,
                'yearly': ym_uniform_squeeze
            },
            'hyp_109_3_adaptive_no_4h_mid': {
                'mode_a': m_adaptive_no_4h,
                'yearly': ym_adaptive_no_4h
            },
            'hyp_109_4_master_adaptive': {
                'mode_a': m_exp109_master_a,
                'ci_95': ci_a,
                'yearly_mode_a': ym_exp109_master_a,
                'mode_b_max_concurrent_2': m_exp109_master_b,
                'ci_95_mode_b': ci_b,
                'yearly_mode_b': ym_exp109_master_b,
                'exit_types_long': {
                    'total': len(trades_long_master),
                    'parent_scale_exit': n_parent,
                    'regime_ratchet_lock': n_ratchet,
                    'rapid_4h_mid_stop': n_rapid,
                    'initial_risk_stop': n_init_risk,
                    'timeout_reclaim_failed': n_timeout,
                    's3_stop': n_s3
                },
                'positions_over_100h': {
                    'count': len(t_over_100h),
                    'mean_mfe_atr': float(np.round(avg_mfe_over_100h, 2))
                },
                'shorts_standalone': shorts_stats
            }
        },
        'execution_time_sec': float(np.round(time.time() - t_start, 2))
    }

    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics_payload, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to {metrics_path}")

    print("\n" + "=" * 80)
    print("EXP-109 Verification Completed Successfully!")
    print("=" * 80)

if __name__ == '__main__':
    main()
