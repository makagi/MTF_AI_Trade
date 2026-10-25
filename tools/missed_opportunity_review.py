"""
Missed Opportunity Review (MOR) Tool
====================================
Analysis 実験完了時に「シグナルが出なかったのに大きく動いた場面（見逃しエントリー：M1）」と
対照群（C1: 似ているのに伸びなかった場面、C2: シグナル発生→負け）を抽出し、
ブラインド比較用の Stage A（判断時点）および Stage B（結末）チャートを生成する。

Usage:
  uv run python tools/missed_opportunity_review.py --experiment 77 --signal k038_mvc --seed 42
"""

import os
import sys
import json
import argparse
import random
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# プロジェクトルート設定
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.data_loader import load_ohlcv
from src.features import (
    calculate_sma, calculate_atr, calculate_afs,
    calculate_regime_age, calculate_bollinger_bands
)
from src.evaluation import decluster_events

plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = ['Meiryo', 'Yu Gothic', 'MS Gothic', 'sans-serif']
plt.rcParams['font.size'] = 9

HOLDOUT_START = pd.Timestamp("2025-05-01", tz="UTC")
DISCOVERY_START = pd.Timestamp("2020-01-01", tz="UTC")


def plot_candlesticks(ax, opens, highs, lows, closes, width=0.6, colorup='#26a69a', colordown='#ef5350'):
    """
    純粋な Matplotlib で高速・綺麗にローソク足を描画する。
    """
    x = np.arange(len(opens))
    up = closes >= opens
    down = ~up

    # ヒゲ (High-Low)
    ax.vlines(x, lows, highs, color='#888888', linewidth=0.8, alpha=0.9)
    # 実体 (Open-Close)
    if np.any(up):
        ax.bar(x[up], (closes - opens)[up], bottom=opens[up], width=width, color=colorup, edgecolor=colorup, linewidth=0.5)
    if np.any(down):
        ax.bar(x[down], (opens - closes)[down], bottom=closes[down], width=width, color=colordown, edgecolor=colordown, linewidth=0.5)


def calculate_features_1h(df_1h):
    """
    1h 足データに対して必要なテクニカル指標・特徴量を計算する。
    """
    close = df_1h['close']
    atr_24 = calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr_24

    for p in [21, 34, 55, 89, 144, 233, 377]:
        df_1h[f'sma_{p}'] = calculate_sma(close, p)
        df_1h[f'slope_{p}'] = (df_1h[f'sma_{p}'] - df_1h[f'sma_{p}'].shift(3)) / (3 * atr_24)
        df_1h[f'sma_diff_{p}'] = (close - df_1h[f'sma_{p}']) / atr_24

    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(close, 20, 2.0)
    df_1h['bb_upper'] = bb_upper
    df_1h['bb_mid'] = bb_mid
    df_1h['bb_lower'] = bb_lower
    df_1h['bb_width_atr'] = (bb_upper - bb_lower) / atr_24

    _, order_score, compression = calculate_afs(df_1h, periods=[7, 9, 11, 13])
    df_1h['afs_order_score'] = order_score
    df_1h['afs_compression'] = compression

    regime_df = calculate_regime_age(df_1h)
    df_1h['macro_age_ratio'] = regime_df['macro_age_ratio']

    return df_1h


def detect_k038_mvc(df_1h):
    """
    K-038 MVC シグナル（独立86件）を特定する。
    """
    close = df_1h['close']
    meso_raw = (close > df_1h['sma_34']) & (close.shift(1) <= df_1h['sma_34'].shift(1)) & (df_1h['slope_55'] > 0)
    meso_decl = decluster_events(meso_raw, cooldown_bars=24)
    gate_trap = ~(df_1h['macro_age_ratio'] > 2.0)
    gate_booster = (df_1h['afs_order_score'] == 3)
    mvc_mask = meso_decl & gate_trap & gate_booster
    return mvc_mask


def extract_mor_candidates(df_1h, mvc_mask, seed=42, mfe_th=4.0):
    """
    M1 (見逃し), C1 (伸びなかった対照群), C2 (MVC 負けトレード) を抽出する。
    """
    # Holdout ガード
    assert df_1h.index[-1] < HOLDOUT_START, f"Holdout period accessed: {df_1h.index[-1]} >= {HOLDOUT_START}"

    n = len(df_1h)
    highs = df_1h['high'].values
    opens = df_1h['open'].values
    closes = df_1h['close'].values
    atrs = df_1h['atr_24'].values

    # MFE 72h の計算
    mfes = np.full(n, np.nan)
    rets_72h = np.full(n, np.nan)
    for i in range(120, n - 73):
        entry_p = opens[i + 1]
        max_h = np.max(highs[i + 1 : i + 73])
        exit_p = closes[i + 72]
        a = atrs[i]
        if a > 0:
            mfes[i] = (max_h - entry_p) / a
            rets_72h[i] = (exit_p - entry_p) / entry_p - 0.0040  # 40bps摩擦コスト後

    df_1h['mfe_72h_atr'] = mfes
    df_1h['net_ret_72h'] = rets_72h

    mvc_events = set(df_1h.index[mvc_mask])

    # MVC シグナルの近傍マスク (t-24h 〜 t+12h)
    times = df_1h.index
    near_mvc = np.zeros(n, dtype=bool)
    for t_mvc in mvc_events:
        mask_win = (times >= t_mvc - pd.Timedelta(hours=24)) & (times <= t_mvc + pd.Timedelta(hours=12))
        near_mvc = near_mvc | mask_win

    # 1. M1: 見逃しエントリー (MFE >= 4.0 ATR & MVC近傍外 & 72hデクラスタ)
    m1_raw = (df_1h['mfe_72h_atr'] >= mfe_th) & (~near_mvc)
    m1_decl = decluster_events(m1_raw, cooldown_bars=72)
    m1_pool = df_1h.index[m1_decl]

    # 2. C1: 似ているのに伸びなかった場面 (MFE < 1.0 ATR & MVC近傍外 & 72hデクラスタ)
    c1_raw = (df_1h['mfe_72h_atr'] < 1.0) & (df_1h['mfe_72h_atr'] >= 0.0) & (~near_mvc)
    c1_decl = decluster_events(c1_raw, cooldown_bars=72)
    c1_pool = df_1h.index[c1_decl]

    # 3. C2: MVC シグナル発生 → 負けトレード
    c2_pool = []
    for t_mvc in sorted(mvc_events):
        loc = df_1h.index.get_loc(t_mvc)
        if loc + 72 < n and df_1h['net_ret_72h'].iloc[loc] < 0:
            c2_pool.append(t_mvc)
    c2_pool = pd.DatetimeIndex(c2_pool)

    # 特徴量ベクトルの標準化（最近傍マッチング用）
    feat_cols = [
        'sma_diff_21', 'sma_diff_34', 'sma_diff_55', 'sma_diff_89', 'sma_diff_233',
        'slope_34', 'slope_55', 'slope_233', 'bb_width_atr', 'afs_compression', 'macro_age_ratio'
    ]
    df_feat = df_1h[feat_cols].fillna(0.0)
    scaler_mean = df_feat.mean()
    scaler_std = df_feat.std().replace(0, 1.0)
    feat_scaled = (df_feat - scaler_mean) / scaler_std

    # サンプリング実行
    rng = np.random.RandomState(seed)

    # M1 から 5件
    m1_selected = list(rng.choice(m1_pool, size=5, replace=False))

    # C1 から 3件 (M1 のうち先頭3件の最近傍マッチング)
    c1_selected = []
    chosen_so_far = list(m1_selected)
    for m1_t in m1_selected[:3]:
        vec = feat_scaled.loc[m1_t].values
        cand_matrix = feat_scaled.loc[c1_pool].values
        dists = np.linalg.norm(cand_matrix - vec, axis=1)
        for idx in np.argsort(dists):
            cand_t = c1_pool[idx]
            if cand_t not in chosen_so_far and all(abs((cand_t - ex).total_seconds()) >= 72 * 3600 for ex in chosen_so_far):
                c1_selected.append(cand_t)
                chosen_so_far.append(cand_t)
                break

    # C2 から 2件 (MVC 負けトレード)
    c2_eligible = [t for t in c2_pool if t not in chosen_so_far and all(abs((t - ex).total_seconds()) >= 72 * 3600 for ex in chosen_so_far)]
    c2_selected = list(rng.choice(c2_eligible, size=2, replace=False))

    # 合計 10件のリスト
    all_cases = []
    for t in m1_selected:
        all_cases.append({'type': 'M1', 'timestamp': t})
    for t in c1_selected:
        all_cases.append({'type': 'C1', 'timestamp': t})
    for t in c2_selected:
        all_cases.append({'type': 'C2', 'timestamp': t})

    # シードでシャッフル
    rng.shuffle(all_cases)

    # Case 01 〜 Case 10 を付与
    cases_final = []
    for i, c in enumerate(all_cases):
        case_id = f"{i+1:02d}"
        c_copy = dict(c)
        c_copy['case_id'] = case_id
        cases_final.append(c_copy)

    return cases_final


def render_case_charts(df_1h, df_1m, case, out_dir):
    """
    各ケースの Stage A (判断時点) および Stage B (結末) チャートを描画・保存する。
    """
    t0 = case['timestamp']
    case_id = case['case_id']
    loc0 = df_1h.index.get_loc(t0)

    # 1h データスライス
    sub_1h_past = df_1h.iloc[loc0 - 120 : loc0 + 1].copy()
    sub_1h_full = df_1h.iloc[loc0 - 120 : loc0 + 73].copy()
    
    # 1m データスライス (直近 60分)
    sub_1m_past = df_1m.loc[t0 - pd.Timedelta(minutes=59) : t0].copy()

    # --- 1. Stage A (判断時点: t0 以降は一切描画しない) ---
    fig_a = plt.figure(figsize=(15, 8.5))
    gs_a = fig_a.add_gridspec(3, 1, height_ratios=[4.5, 1.2, 1.2], hspace=0.15)
    ax_main_a = fig_a.add_subplot(gs_a[0, 0])
    ax_afs_a = fig_a.add_subplot(gs_a[1, 0], sharex=ax_main_a)
    ax_slope_a = fig_a.add_subplot(gs_a[2, 0], sharex=ax_main_a)

    x_past = np.arange(len(sub_1h_past))

    # メインローソク足
    plot_candlesticks(ax_main_a, sub_1h_past['open'].values, sub_1h_past['high'].values, sub_1h_past['low'].values, sub_1h_past['close'].values)

    # SMA & BB
    ax_main_a.plot(x_past, sub_1h_past['sma_21'], label='SMA 21', color='#00bcd4', lw=1.2)
    ax_main_a.plot(x_past, sub_1h_past['sma_34'], label='SMA 34', color='#ff9800', lw=1.4)
    ax_main_a.plot(x_past, sub_1h_past['sma_55'], label='SMA 55', color='#4caf50', lw=1.2)
    ax_main_a.plot(x_past, sub_1h_past['sma_89'], label='SMA 89', color='#9c27b0', lw=1.2)
    ax_main_a.plot(x_past, sub_1h_past['sma_144'], label='SMA 144', color='#795548', lw=1.2)
    ax_main_a.plot(x_past, sub_1h_past['sma_233'], label='SMA 233', color='#e91e63', lw=1.8)
    ax_main_a.plot(x_past, sub_1h_past['bb_upper'], color='#9e9e9e', ls='--', lw=1.0)
    ax_main_a.plot(x_past, sub_1h_past['bb_lower'], color='#9e9e9e', ls='--', lw=1.0)
    ax_main_a.fill_between(x_past, sub_1h_past['bb_lower'], sub_1h_past['bb_upper'], color='#eeeeee', alpha=0.4, label='BB(20, 2σ)')

    # 判断時点マーク (右端)
    ax_main_a.axvline(x_past[-1], color='#333333', ls=':', lw=2.0)
    ax_main_a.text(x_past[-1], ax_main_a.get_ylim()[1], '  Judgement Point $t$', color='#333333', fontweight='bold', va='top')

    ax_main_a.set_title(f"Case {case_id}: Stage A (Judgement Point: {t0.strftime('%Y-%m-%d %H:00')} UTC)\n"
                        f"Price: ${sub_1h_past['close'].iloc[-1]:,.1f} | ATR: ${sub_1h_past['atr_24'].iloc[-1]:,.1f} | "
                        f"BB Width: {sub_1h_past['bb_width_atr'].iloc[-1]:.2f} ATR | Macro Age Ratio: {sub_1h_past['macro_age_ratio'].iloc[-1]:.2f}",
                        fontsize=12, fontweight='bold', pad=10)
    ax_main_a.set_ylabel("BTC/USD Price ($)")
    ax_main_a.legend(loc='upper left', ncol=4, framealpha=0.9, fontsize=8)

    # 1m インセット描画 (左上または右上に配置)
    if len(sub_1m_past) > 0:
        ax_inset_a = ax_main_a.inset_axes([0.02, 0.48, 0.28, 0.35])
        plot_candlesticks(ax_inset_a, sub_1m_past['open'].values, sub_1m_past['high'].values, sub_1m_past['low'].values, sub_1m_past['close'].values, width=0.7)
        ax_inset_a.set_title(f"1m Intrabar (Past 60m)", fontsize=8, fontweight='bold')
        ax_inset_a.tick_params(labelsize=7)
        ax_inset_a.grid(True, alpha=0.3)

    # AFS サブパネル
    ax_afs_a.plot(x_past, sub_1h_past['afs_compression'], color='#2196f3', lw=1.3, label='AFS Compression')
    ax_afs_a.axhline(50, color='gray', ls=':', lw=0.8)
    ax_afs_a.axhline(100, color='orange', ls=':', lw=0.8)
    ax_afs_a.set_ylabel("AFS Comp")
    ax_afs_a.legend(loc='upper left', fontsize=8)

    ax_afs_twin = ax_afs_a.twinx()
    ax_afs_twin.step(x_past, sub_1h_past['afs_order_score'], where='mid', color='#e91e63', lw=1.2, ls='--', label='Order Score (0..3)')
    ax_afs_twin.set_ylabel("Score", color='#e91e63')
    ax_afs_twin.set_ylim(-0.5, 3.5)

    # Slope サブパネル
    ax_slope_a.plot(x_past, sub_1h_past['slope_34'], color='#ff9800', lw=1.2, label='Slope 34')
    ax_slope_a.plot(x_past, sub_1h_past['slope_55'], color='#4caf50', lw=1.2, label='Slope 55')
    ax_slope_a.plot(x_past, sub_1h_past['slope_233'], color='#e91e63', lw=1.5, label='Slope 233')
    ax_slope_a.axhline(0, color='black', lw=0.8, ls='--')
    ax_slope_a.set_ylabel("Slope / ATR")
    ax_slope_a.legend(loc='upper left', ncol=3, fontsize=8)

    # X軸フォーマット
    tick_locs = np.linspace(0, len(x_past)-1, 7, dtype=int)
    ax_slope_a.set_xticks(tick_locs)
    ax_slope_a.set_xticklabels([sub_1h_past.index[i].strftime('%m-%d %H:00') for i in tick_locs])

    fig_a.tight_layout()
    path_stage_a = out_dir / f"case_{case_id}_stageA.png"
    fig_a.savefig(path_stage_a, dpi=180)
    plt.close(fig_a)

    # --- 2. Stage B (結末: t0 以降 72h を展開) ---
    fig_b = plt.figure(figsize=(16, 9.0))
    gs_b = fig_b.add_gridspec(3, 1, height_ratios=[4.5, 1.2, 1.2], hspace=0.15)
    ax_main_b = fig_b.add_subplot(gs_b[0, 0])
    ax_afs_b = fig_b.add_subplot(gs_b[1, 0], sharex=ax_main_b)
    ax_slope_b = fig_b.add_subplot(gs_b[2, 0], sharex=ax_main_b)

    x_full = np.arange(len(sub_1h_full))
    split_idx = 120  # t0 のインデックス

    # メインローソク足
    plot_candlesticks(ax_main_b, sub_1h_full['open'].values, sub_1h_full['high'].values, sub_1h_full['low'].values, sub_1h_full['close'].values)

    # SMA & BB
    ax_main_b.plot(x_full, sub_1h_full['sma_21'], color='#00bcd4', lw=1.2)
    ax_main_b.plot(x_full, sub_1h_full['sma_34'], color='#ff9800', lw=1.4)
    ax_main_b.plot(x_full, sub_1h_full['sma_55'], color='#4caf50', lw=1.2)
    ax_main_b.plot(x_full, sub_1h_full['sma_89'], color='#9c27b0', lw=1.2)
    ax_main_b.plot(x_full, sub_1h_full['sma_144'], color='#795548', lw=1.2)
    ax_main_b.plot(x_full, sub_1h_full['sma_233'], color='#e91e63', lw=1.8)
    ax_main_b.plot(x_full, sub_1h_full['bb_upper'], color='#9e9e9e', ls='--', lw=1.0)
    ax_main_b.plot(x_full, sub_1h_full['bb_lower'], color='#9e9e9e', ls='--', lw=1.0)
    ax_main_b.fill_between(x_full, sub_1h_full['bb_lower'], sub_1h_full['bb_upper'], color='#eeeeee', alpha=0.3)

    # 判断時点の縦境界線
    ax_main_b.axvline(split_idx, color='red', ls='-', lw=2.0)
    ax_main_b.axvspan(split_idx, len(x_full)-1, color='yellow', alpha=0.08, label='Outcome Window (+72h)')

    # MFE 到達点の探索とアノテーション
    future_highs = sub_1h_full['high'].iloc[split_idx+1 : split_idx+73].values
    mfe_rel_idx = np.argmax(future_highs)
    mfe_abs_idx = split_idx + 1 + mfe_rel_idx
    mfe_price = future_highs[mfe_rel_idx]
    entry_p = sub_1h_full['open'].iloc[split_idx + 1]
    atr_val = sub_1h_full['atr_24'].iloc[split_idx]
    mfe_atr_val = (mfe_price - entry_p) / atr_val
    mfe_pct_val = (mfe_price - entry_p) / entry_p * 100.0

    ax_main_b.scatter([mfe_abs_idx], [mfe_price], color='gold', edgecolor='black', s=160, marker='*', zorder=10)
    ax_main_b.annotate(f"MFE: +{mfe_atr_val:.2f} ATR (+{mfe_pct_val:.2f}%)\nat +{mfe_rel_idx+1}h",
                       xy=(mfe_abs_idx, mfe_price),
                       xytext=(mfe_abs_idx, mfe_price + atr_val * 0.8),
                       arrowprops=dict(facecolor='black', shrink=0.08, width=1.2, headwidth=6),
                       bbox=dict(boxstyle='round,pad=0.4', facecolor='yellow', alpha=0.9),
                       fontweight='bold', fontsize=9)

    # 実際のラベルに応じたタイトル表示
    label_text = {
        'M1': 'M1 (見逃しエントリー: 4+ ATR 大幅順行)',
        'C1': 'C1 (対照群: 似ているのに伸びなかったダマシ/失速)',
        'C2': 'C2 (対照群: K-038 MVC シグナル発生 → 負けトレード)'
    }.get(case['type'], case['type'])

    net_ret = sub_1h_full['net_ret_72h'].iloc[split_idx] * 100.0

    ax_main_b.set_title(f"Case {case_id}: Stage B (Outcome & Revelation: {label_text})\n"
                        f"Entry @ ${entry_p:,.1f} | MFE: +{mfe_atr_val:.2f} ATR | 72h Net Ret: {net_ret:+.2f}%",
                        fontsize=12, fontweight='bold', color='darkred' if case['type'] == 'C2' else ('darkgreen' if case['type'] == 'M1' else 'navy'), pad=10)
    ax_main_b.set_ylabel("BTC/USD Price ($)")
    ax_main_b.legend(loc='upper left', ncol=3, framealpha=0.9, fontsize=8)

    # AFS サブパネル
    ax_afs_b.plot(x_full, sub_1h_full['afs_compression'], color='#2196f3', lw=1.3)
    ax_afs_b.axvline(split_idx, color='red', ls='-', lw=1.5)
    ax_afs_b.set_ylabel("AFS Comp")

    ax_afs_twin_b = ax_afs_b.twinx()
    ax_afs_twin_b.step(x_full, sub_1h_full['afs_order_score'], where='mid', color='#e91e63', lw=1.2, ls='--')
    ax_afs_twin_b.set_ylabel("Score", color='#e91e63')
    ax_afs_twin_b.set_ylim(-0.5, 3.5)

    # Slope サブパネル
    ax_slope_b.plot(x_full, sub_1h_full['slope_34'], color='#ff9800', lw=1.2)
    ax_slope_b.plot(x_full, sub_1h_full['slope_55'], color='#4caf50', lw=1.2)
    ax_slope_b.plot(x_full, sub_1h_full['slope_233'], color='#e91e63', lw=1.5)
    ax_slope_b.axvline(split_idx, color='red', ls='-', lw=1.5)
    ax_slope_b.axhline(0, color='black', lw=0.8, ls='--')
    ax_slope_b.set_ylabel("Slope / ATR")

    # X軸フォーマット
    tick_locs_b = np.linspace(0, len(x_full)-1, 9, dtype=int)
    ax_slope_b.set_xticks(tick_locs_b)
    ax_slope_b.set_xticklabels([sub_1h_full.index[i].strftime('%m-%d %H:00') for i in tick_locs_b])

    fig_b.tight_layout()
    path_stage_b = out_dir / f"case_{case_id}_stageB.png"
    fig_b.savefig(path_stage_b, dpi=180)
    plt.close(fig_b)

    return {
        'case_id': case_id,
        'type': case['type'],
        'timestamp': t0.isoformat(),
        'entry_price': float(np.round(entry_p, 2)),
        'atr_24': float(np.round(atr_val, 2)),
        'mfe_72h_atr': float(np.round(mfe_atr_val, 2)),
        'mfe_72h_pct': float(np.round(mfe_pct_val, 2)),
        'net_ret_72h_pct': float(np.round(net_ret, 2)),
        'bb_width_atr': float(np.round(sub_1h_past['bb_width_atr'].iloc[-1], 2)),
        'macro_age_ratio': float(np.round(sub_1h_past['macro_age_ratio'].iloc[-1], 2)),
        'afs_compression': float(np.round(sub_1h_past['afs_compression'].iloc[-1], 2)),
        'afs_order_score': int(sub_1h_past['afs_order_score'].iloc[-1])
    }


def generate_review_documents(cases_meta, review_dir, experiment_id="77"):
    """
    gallery_stageA.md, gallery_stageB.md, answer_key.json, cases.json, observations.yaml を出力する。
    """
    # 1. answer_key.json (正解データ: 回答前には見せない)
    answer_key = {}
    for c in cases_meta:
        answer_key[f"case_{c['case_id']}"] = {
            'case_id': c['case_id'],
            'type': c['type'],
            'timestamp': c['timestamp'],
            'mfe_72h_atr': c['mfe_72h_atr'],
            'net_ret_72h_pct': c['net_ret_72h_pct']
        }
    with open(review_dir / "answer_key.json", "w", encoding="utf-8") as f:
        json.dump(answer_key, f, indent=2, ensure_ascii=False)

    # 2. cases.json (スナップショット)
    with open(review_dir / "cases.json", "w", encoding="utf-8") as f:
        json.dump(cases_meta, f, indent=2, ensure_ascii=False)

    # 3. gallery_stageA.md (ブラインド質問票: 正解ラベルは一切含まない)
    doc_a = [
        f"# Missed Opportunity Review: Stage A (判断質問票 - EXP-{experiment_id})",
        "",
        "**Review ID:** `MOR-77-01`  ",
        "**Experiment:** EXP-77 (K-038 MVC)  ",
        "**実施日:** 2026-10-25  ",
        "**レビュアー:** @makagi  ",
        "",
        "---",
        "",
        "## 1. 概要と回答手順 (Instructions)",
        "",
        "本レビューは、定量的バックテストでは拾いきれなかった「急騰の取りこぼし（見逃し）」と「対照群（伸びなかった場面・負けトレード）」をブラインドで混在させ、人間の視点を仮説生成のインプットとして取り込む工程（Human-in-the-Loop Review）です。",
        "",
        "### 回答ルール",
        "1. 各ケースの **Stage A チャート（判断時点 $t$ までの過去 120時間ローソク足および指標）** を観察してください（未来の情報は一切含まれていません）。",
        "2. あなた自身がこの瞬間にチャートの前に立っていたとして、以下の3択から直感・判断を選択してください：",
        "   - **`long`**: 買いでエントリーしたい（上値余地があり、勢い・構造が良好）",
        "   - **`skip`**: 見送り・見送るべき（頭上抵抗がある、ダマシっぽい、勢いが鈍い）",
        "   - **`unsure`**: 迷う・どちらとも言えない",
        "3. **判断の根拠（何を見てそう感じたか）** を簡潔に記入してください（例：「SMA 34 の下値支持が強固」「頭上 SMA 89 に抑え込まれそう」「直前で急伸しすぎていて過熱感」など）。",
        "4. 全 10 ケースの回答完了後、エージェントが Stage B（72時間の結末チャートと正解ラベル）を開示します。",
        "",
        "---",
        "",
        "## 2. ケース別 Stage A チャートと質問票",
        ""
    ]

    for c in cases_meta:
        cid = c['case_id']
        doc_a.append(f"### Case {cid}")
        doc_a.append(f"![Case {cid} Stage A](case_{cid}_stageA.png)")
        doc_a.append("")
        doc_a.append(f"- **観測時刻**: `{c['timestamp']}`")
        doc_a.append(f"- **客観状況**: 価格 `${c['entry_price']:,.1f}` | ATR `${c['atr_24']:,.1f}` | BB 幅 `{c['bb_width_atr']:.2f} ATR` | Macro Age Ratio `{c['macro_age_ratio']:.2f}` | AFS Comp `{c['afs_compression']:.1f}` (Score `{c['afs_order_score']}`)")
        doc_a.append("")
        doc_a.append(f"#### 【あなたの判断】")
        doc_a.append(f"- [ ] **`long`**（エントリー推奨）")
        doc_a.append(f"- [ ] **`skip`**（見送り推奨）")
        doc_a.append(f"- [ ] **`unsure`**（判断保留）")
        doc_a.append(f"- **判断理由・着目したポイント**:")
        doc_a.append(f"  > （ここに理由を記入）")
        doc_a.append("")
        doc_a.append("---")
        doc_a.append("")

    with open(review_dir / "gallery_stageA.md", "w", encoding="utf-8") as f:
        f.write("\n".join(doc_a))

    # 4. gallery_stageB.md (結末開示ギャラリー)
    doc_b = [
        f"# Missed Opportunity Review: Stage B (結末開示ギャラリー - EXP-{experiment_id})",
        "",
        "**Review ID:** `MOR-77-01`  ",
        "**Experiment:** EXP-77 (K-038 MVC)  ",
        "**開示日時:** 2026-10-25  ",
        "",
        "---",
        "",
        "## 1. 結末開示とケース解剖 (Revealed Outcomes)",
        ""
    ]

    for c in cases_meta:
        cid = c['case_id']
        label_desc = {
            'M1': '★ M1 (見逃しエントリー: 4+ ATR 大幅急伸)',
            'C1': '✕ C1 (対照群: 似ているのに伸びなかった失速・ダマシ)',
            'C2': '▲ C2 (対照群: K-038 MVC シグナル発生 → 負けトレード)'
        }.get(c['type'], c['type'])

        doc_b.append(f"### Case {cid}: {label_desc}")
        doc_b.append(f"![Case {cid} Stage B](case_{cid}_stageB.png)")
        doc_b.append("")
        doc_b.append(f"- **真のラベル**: **`{c['type']}`**")
        doc_b.append(f"- **判定時点価格**: `${c['entry_price']:,.1f}`")
        doc_b.append(f"- **72h 最大順行幅 (MFE)**: **`+{c['mfe_72h_atr']:.2f} ATR`** (`+{c['mfe_72h_pct']:.2f}%`)")
        doc_b.append(f"- **72h 最終 Net リターン**: **`{c['net_ret_72h_pct']:+.2f}%`**")
        doc_b.append("")
        doc_b.append(f"#### 結末の解説・考察")
        if c['type'] == 'M1':
            doc_b.append(f"> **見逃しの実態**: 判断時点以降、価格は勢いを増して急騰し、72時間以内に最大 `+{c['mfe_72h_atr']:.2f} ATR`（`+{c['mfe_72h_pct']:.2f}%`）に達しました。シグナル条件（AFS整流や傾き、ブレイクアウト定義）のどの要素がこの波を遮断してしまったのかを検証する重要な材料です。")
        elif c['type'] == 'C1':
            doc_b.append(f"> **失速・ダマシの実態**: 判断時点での指標の並びは M1 に酷似していましたが、その後は伸び悩み、MFE はわずか `+{c['mfe_72h_atr']:.2f} ATR` に留まりました。M1 との間で何が決定的に異なっていたのか（上位足の環境、直前の戻り方、出来高など）を比較観察してください。")
        else:
            doc_b.append(f"> **シグナル負けの実態**: K-038 MVC の基準を完全に満たしてエントリーしたものの、72時間の最終リターンは `{c['net_ret_72h_pct']:+.2f}%` と損失に終わりました。S3 動的不可侵撤退の作動有無や、エントリー直後の逆行兆候を確認してください。")
        doc_b.append("")
        doc_b.append("---")
        doc_b.append("")

    with open(review_dir / "gallery_stageB.md", "w", encoding="utf-8") as f:
        f.write("\n".join(doc_b))

    # 5. observations.yaml (回答用テンプレート)
    obs_template = {
        'review_id': f"MOR-{experiment_id}-01",
        'experiment': f"EXP-{experiment_id}",
        'date': "2026-10-25",
        'reviewer': "@makagi",
        'cases': [
            {
                'case_id': int(c['case_id']),
                'stage_a_call': "",
                'stage_a_rationale': "",
                'stage_b_comment': "",
                'tags': [],
                'revealed_label': c['type']
            } for c in cases_meta
        ],
        'summary': {
            'stage_a_accuracy_score': None,
            'candidate_hypotheses': []
        }
    }
    
    # 手動記入用YAMLを生成
    lines_yaml = [
        f"review_id: MOR-{experiment_id}-01",
        f"experiment: EXP-{experiment_id}",
        "date: '2026-10-25'",
        "reviewer: '@makagi'",
        "cases:"
    ]
    for c in cases_meta:
        cid = c['case_id']
        lines_yaml.extend([
            f"  - case_id: {int(cid)}",
            "    stage_a_call: ''        # 'long' / 'skip' / 'unsure'",
            "    stage_a_rationale: ''   # 判断の根拠",
            "    stage_b_comment: ''     # 結末開示後の所見",
            "    tags: []                # 例: [overhead_resistance, squeeze_release]",
            f"    revealed_label: {c['type']}     # 開示後の正解ラベル"
        ])
    lines_yaml.extend([
        "summary:",
        "  stage_a_accuracy_score: null  # 正答率 (M1=long, C1/C2=skip)",
        "  candidate_hypotheses: []       # 次期 Analysis Issue で事前登録する仮説候補"
    ])

    with open(review_dir / "observations.yaml", "w", encoding="utf-8") as f:
        f.write("\n".join(lines_yaml))


def main():
    parser = argparse.ArgumentParser(description="Missed Opportunity Review (MOR) Extraction & Chart Generation Tool")
    parser.add_argument("--experiment", type=str, default="77", help="Experiment ID number (e.g. 77)")
    parser.add_argument("--signal", type=str, default="k038_mvc", help="Signal type (default: k038_mvc)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for repeatable sampling (default: 42)")
    parser.add_argument("--mfe-threshold", type=float, default=4.0, help="M1 MFE threshold in ATR (default: 4.0)")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Missed Opportunity Review (MOR) Generator: EXP-{args.experiment}")
    print(f"Signal: {args.signal} | Seed: {args.seed} | M1 MFE Threshold: {args.mfe_threshold} ATR")
    print("=" * 70)

    # 実験ディレクトリの探索
    exp_pattern = f"{args.experiment}-*"
    exp_matches = list((REPO_ROOT / "03_KNOWLEDGE" / "experiments").glob(exp_pattern))
    if not exp_matches:
        raise FileNotFoundError(f"Experiment directory matching {exp_pattern} not found in 03_KNOWLEDGE/experiments")
    exp_dir = exp_matches[0]
    review_dir = exp_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    print(f"Target Review Directory: {review_dir}")

    # 1. データ読み込み (Holdout ガード厳守)
    print("\n--- Step 1: Loading Data (Discovery Only) ---")
    df_1h = load_ohlcv('BTCUSD', '1h').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    df_1m = load_ohlcv('BTCUSD', '1m').loc[DISCOVERY_START : HOLDOUT_START - pd.Timedelta(seconds=1)].copy()
    assert df_1h.index[-1] < HOLDOUT_START, f"Holdout leakage: {df_1h.index[-1]}"
    print(f"Loaded 1h data: {len(df_1h):,} bars ({df_1h.index[0]} to {df_1h.index[-1]})")
    print(f"Loaded 1m data: {len(df_1m):,} bars ({df_1m.index[0]} to {df_1m.index[-1]})")

    # 2. 特徴量計算
    print("\n--- Step 2: Calculating MTF Features ---")
    df_1h = calculate_features_1h(df_1h)

    # 3. シグナル特定
    print(f"\n--- Step 3: Detecting Base Signal ({args.signal}) ---")
    if args.signal.lower() == "k038_mvc":
        mvc_mask = detect_k038_mvc(df_1h)
        print(f"Identified {mvc_mask.sum()} K-038 MVC events.")
    else:
        raise NotImplementedError(f"Signal {args.signal} is not yet implemented.")

    # 4. M1 / C1 / C2 候補抽出とサンプリング
    print("\n--- Step 4: Extracting M1, C1, C2 Candidates and Sampling (Seed={}) ---".format(args.seed))
    cases = extract_mor_candidates(df_1h, mvc_mask, seed=args.seed, mfe_th=args.mfe_threshold)
    print(f"Sampled {len(cases)} blind cases (5 M1, 3 C1, 2 C2).")

    # 5. チャート描画 (Stage A / Stage B)
    print("\n--- Step 5: Rendering Stage A and Stage B Charts ---")
    cases_meta = []
    for c in cases:
        cid = c['case_id']
        t_str = c['timestamp'].strftime('%Y-%m-%d %H:00')
        print(f"  Rendering Case {cid}: {t_str} (Type: {c['type']})...")
        meta = render_case_charts(df_1h, df_1m, c, review_dir)
        cases_meta.append(meta)

    # 6. ドキュメント出力
    print("\n--- Step 6: Exporting Galleries and Documents ---")
    generate_review_documents(cases_meta, review_dir, experiment_id=args.experiment)
    print(f"  Exported: {review_dir / 'gallery_stageA.md'}")
    print(f"  Exported: {review_dir / 'gallery_stageB.md'}")
    print(f"  Exported: {review_dir / 'answer_key.json'}")
    print(f"  Exported: {review_dir / 'cases.json'}")
    print(f"  Exported: {review_dir / 'observations.yaml'}")

    print("\n" + "=" * 70)
    print(f"Missed Opportunity Review (MOR) Suite Successfully Generated for EXP-{args.experiment}!")
    print("=" * 70)


if __name__ == "__main__":
    main()
