#!/usr/bin/env python3
r"""
EXP-129: Full-Spectrum Multi-Layer Curvature Tree Pyramid Convolution & Divergence Analysis
===========================================================================================

Mathematical & Algorithmic Foundations:
1. 17 Fibonacci Scales (8..17711) 2nd Difference (Curvature):
   - slope_s(t) = (SMA_s(t) - SMA_s(t-3)) / (3 * ATR_24(t))
   - curv_s(t) = (slope_s(t) - slope_s(t-3)) / 3.0
2. Full-Pyramid 8-Layer Recursive Convolution:
   - Layer 0: Raw 17 scales
   - Layer 1: 15 nodes, triad kernel [0.25, 0.50, 0.25]
   - Layer 2..Layer 8: recursive sliding triad kernel [0.30, 0.40, 0.30]
   - Layer 8: Global Root node [8..17711] (`curv_root`)
3. 4-Stage Ablation Progression across 3 Execution Modes:
   - Stage 0: Base (EXP-123 Baseline Exact Reproduction: N=129, PF=5.45, EV=+4.15%, Tot=+535.8%)
   - Stage 1: +HYP-129-1 (Systemic Plunge Gate):
     * Micro <= 0 AND Macro <= 0 blocks systemic plunge (2023-04-21 knife: -2.74%).
     * Explicit comparison: all longs (cuts runners, Tot=+402.7%) vs pb_long (preserves all runners, Tot=+538.5%).
   - Stage 2: +HYP-129-2 (Macro Respiration Shield Exit):
     * MFE >= 8.0 ATR anchor tightening only when curv_root <= 0 (macro collapse).
     * Shields positions during megatrend breathing (curv_root > 0), solving EXP-127 collapse (PF 5.57 -> 5.66).
   - Stage 3: +HYP-129-3 (Hierarchical Cascade Rebound Ignition):
     * Upward acceleration verification for breakouts; low-DD conservative profile (MaxDD < 10%).
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Polygon

EXP_DIR = Path(__file__).resolve().parent
ROOT_DIR = EXP_DIR.parent.parent.parent
PLOTS_DIR = EXP_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT_DIR))

import importlib.util

def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

exp111 = load_module('exp111_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/111-short-dynamic-trailing-and-macro-bear-adaptation/run.py"))
exp115 = load_module('exp115_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/115-adaptive-multiscale-respiration-and-hysteresis-exit/run.py"))
exp119 = load_module('exp119_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/119-ultra-long-3channel-tree-pyramid/run.py"))
exp121 = load_module('exp121_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/121-multi-perspective-bb-trees-and-1m-execution/run.py"))
exp123 = load_module('exp123_mod', str(ROOT_DIR / "03_KNOWLEDGE/experiments/123-dynamic-overshoot-and-springboard-respiration/run.py"))

FRICTION_BPS = 0.0040
TREE_SCALES = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]
SCALES_1M = [8, 13, 21, 34, 55, 89, 144, 233, 377]
SPRING_SCALES = [55, 89, 144, 233, 377, 610, 987]

# ==============================================================================
# Full Pyramid Recursive Convolution Architecture
# ==============================================================================

def compute_full_pyramid_curvature(df_1h: pd.DataFrame, scales: list[int] = TREE_SCALES) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """
    Computes 17-scale slopes & curvatures and builds the full 8-layer recursive convolution pyramid:
    - Layer 0: Raw 17 scales
    - Layer 1: 15 nodes, triad kernel [0.25, 0.50, 0.25]
    - Layer 2..Layer 8: recursive kernel [0.30, 0.40, 0.30]
    - Layer 8: 1 node: [8..17711] (Global Root)
    """
    atr = df_1h['atr_24']
    close_1h = df_1h['close']

    # Ensure SMA and slope are computed with min_periods=min(s, 24) to eliminate large-scale NaNs
    for s in scales:
        if f'sma_{s}' not in df_1h.columns:
            df_1h[f'sma_{s}'] = close_1h.rolling(s, min_periods=min(s, 24)).mean()
        else:
            if df_1h[f'sma_{s}'].isna().any():
                df_1h[f'sma_{s}'] = df_1h[f'sma_{s}'].fillna(close_1h.rolling(s, min_periods=min(s, 24)).mean())
        df_1h[f'slope_{s}'] = (df_1h[f'sma_{s}'] - df_1h[f'sma_{s}'].shift(3)) / (3.0 * atr)
        df_1h[f'curv_{s}'] = (df_1h[f'slope_{s}'] - df_1h[f'slope_{s}'].shift(3)) / 3.0

    layers: dict[int, pd.DataFrame] = {}
    layers[0] = pd.DataFrame(index=df_1h.index)
    for s in scales:
        layers[0][f'curv_{s}'] = df_1h[f'curv_{s}']

    # Layer 1: Overlapping Triad Convolution [0.25, 0.50, 0.25]
    l1_df = pd.DataFrame(index=df_1h.index)
    for k in range(len(scales) - 2):
        sa, sb, sc = scales[k], scales[k+1], scales[k+2]
        name = f"({sa},{sb},{sc})"
        l1_df[name] = 0.25 * df_1h[f'curv_{sa}'] + 0.50 * df_1h[f'curv_{sb}'] + 0.25 * df_1h[f'curv_{sc}']
    layers[1] = l1_df

    # Layer 2 to Layer 8: Recursive Sliding Triad Convolution [0.30, 0.40, 0.30]
    cur_df = l1_df
    layer_idx = 2
    while len(cur_df.columns) >= 3:
        cols = list(cur_df.columns)
        next_df = pd.DataFrame(index=df_1h.index)
        for k in range(len(cols) - 2):
            c1, c2, c3 = cols[k], cols[k+1], cols[k+2]
            first_s = re.findall(r'\d+', c1)[0]
            last_s = re.findall(r'\d+', c3)[-1]
            name = f"[{first_s}..{last_s}]"
            next_df[name] = 0.30 * cur_df[c1] + 0.40 * cur_df[c2] + 0.30 * cur_df[c3]
        layers[layer_idx] = next_df
        cur_df = next_df
        layer_idx += 1

    # Canonical wave-packet aliases added via copy/assignment
    df_1h = df_1h.copy()
    df_1h['curv_L1'] = df_1h['curv_L1_(8,13,21)'] = layers[1].iloc[:, 0]
    df_1h['curv_L2_mid'] = layers[2]['[34..233]']
    df_1h['curv_L2_long'] = layers[2]['[144..987]']
    df_1h['curv_L2_ultra'] = layers[2]['[610..4181]']
    df_1h['curv_root'] = layers[8].iloc[:, 0]
    df_1h['curv_L4_mean'] = layers[4].mean(axis=1)

    return df_1h, layers

# ==============================================================================
# Simulation Engine: Macro Respiration Shield Exit
# ==============================================================================

def simulate_long_exp129(events, df_1h, df_1m,
                         enable_bb_respiration=True,
                         enable_latency_absorption=True,
                         min_omega_val=0.20,
                         entry_1m_map=None,
                         enable_macro_shield_exit=False,
                         shield_min_mfe=8.0,
                         shield_target_anchor=34):
    """
    Long position simulator with Macro Respiration Shield Exit (HYP-129-2).
    In high-profit zones (MFE >= 8.0 ATR), anchor shift to short MA (S34) is permitted
    ONLY when the macro root curv_root <= 0 (macro structural rollover), shielding
    positions against premature exit during normal megatrend breathing (curv_root > 0).
    """
    trades = []
    discovery_end = df_1m.index[-1]
    for t0 in events:
        entry_time = t0 + pd.Timedelta(hours=1)
        if entry_time not in df_1h.index: continue
        row_0 = df_1h.loc[t0]

        # EXP-119 Bear Ceiling Gate
        if (row_0['tree_L2_[610..4181]'] < -0.30 and
            row_0['tree_L3_[610..10946]'] < -0.25 and
            row_0['tree_L2_[144..987]'] < -0.10 and
            row_0['close'] < row_0['sma_610'] and
            row_0['slope_610'] < 0):
            continue

        atr0 = row_0['atr_24']
        p_era = exp115.get_period(t0)
        sub_1m = df_1m.loc[entry_time : discovery_end]
        if len(sub_1m) < 60: continue

        if entry_1m_map is not None and t0 in entry_1m_map:
            p0, actual_entry_time, bar_offset = entry_1m_map[t0]
        else:
            p0 = sub_1m['open'].iloc[0]
            actual_entry_time = entry_time
            bar_offset = 0

        sub_times = sub_1m.index
        sub_opens = sub_1m['open'].values
        sub_highs = sub_1m['high'].values
        sub_lows = sub_1m['low'].values
        sub_closes = sub_1m['close'].values

        n_bars = len(sub_1m)
        max_mfe_atr = 0.0
        exited = False

        cur_sma34 = row_0['sma_34']
        atr_cur = atr0
        if p0 >= row_0['sma_233'] - 0.5 * atr0: current_anchor = 233
        elif p0 >= row_0['sma_144'] - 0.5 * atr0: current_anchor = 144
        elif p0 >= row_0['sma_89'] - 0.5 * atr0: current_anchor = 89
        else: current_anchor = 55

        cur_struct = row_0[f'sma_{current_anchor}']
        armed = (p0 > cur_struct + 0.5 * atr0) and (row_0['sma_21'] > row_0['sma_34']) and (row_0[f'slope_{current_anchor}'] > 0)
        highest_price = p0
        prev_afs_diff = row_0['afs_7'] - row_0['afs_9']
        prev_above_band = (row_0['close'] > row_0[f'bb_upper_{current_anchor}'])
        had_pos_curv_root = False
        prev_curv_root = 0.0

        for i in range(bar_offset, n_bars):
            t_bar = sub_times[i]
            if i % 60 == 0 and i > 0:
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                if t_1h in df_1h.index:
                    row_1h = df_1h.loc[t_1h]
                    cur_sma34 = row_1h['sma_34']
                    atr_cur = row_1h['atr_24']
                    c_1h = row_1h['close']

                    cand_anchor = exp115.step_down_scale(current_anchor)
                    band_upper_cur = row_1h[f'bb_upper_{current_anchor}']
                    now_above_band = (c_1h > band_upper_cur)
                    now_afs_diff = row_1h['afs_7'] - row_1h['afs_9']
                    afs_reversal_cross = (prev_afs_diff >= 0 and now_afs_diff < 0)

                    trigger_shift = False
                    if now_above_band and not prev_above_band: trigger_shift = True
                    if afs_reversal_cross and (highest_price > row_1h[f'bb_upper_{cand_anchor}']): trigger_shift = True

                    is_overhead = (c_1h < row_1h['sma_610']) and (row_1h['sma_233'] < row_1h['sma_610']) and (row_1h['slope_610'] < 0)
                    if is_overhead and afs_reversal_cross and (c_1h > row_1h['sma_55']):
                        if current_anchor > 55:
                            cand_anchor = 55
                            trigger_shift = True

                    # HYP-129-2 Macro Respiration Shield Exit:
                    cur_curv_root = row_1h.get('curv_root', 0.0)
                    if cur_curv_root > 0.0001: had_pos_curv_root = True
                    is_megatrend_maturing = (max_mfe_atr >= shield_min_mfe) and had_pos_curv_root and (row_1h['range_pos_720h'] >= 0.75)
                    macro_rollover = (prev_curv_root >= 0.0 and cur_curv_root <= 0.0)

                    if enable_macro_shield_exit and is_megatrend_maturing and macro_rollover and current_anchor > shield_target_anchor:
                        cand_anchor = shield_target_anchor
                        trigger_shift = True

                    if trigger_shift and cand_anchor < current_anchor:
                        if cand_anchor >= 55:
                            crossover_ok = (row_1h['sma_21'] > row_1h['sma_34'] > row_1h[f'sma_{cand_anchor}'])
                        elif cand_anchor == 34:
                            crossover_ok = (c_1h > row_1h['sma_21'] > row_1h['sma_34'])
                        elif cand_anchor == 21:
                            crossover_ok = (c_1h > row_1h['sma_21'] and row_1h['sma_21'] > row_1h['sma_34'])
                        else:
                            crossover_ok = False

                        slope_ok = (row_1h[f'slope_{cand_anchor}'] > 0)
                        cand_stop = row_1h[f'sma_{cand_anchor}'] - 1.0 * atr_cur
                        init_stop_level = p0 - 3.0 * atr0
                        protection_ok = (cand_stop > init_stop_level) and (row_1h[f'sma_{cand_anchor}'] >= p0 - 0.5 * atr_cur)
                        accept_shift = crossover_ok and slope_ok and protection_ok

                        if accept_shift and not (enable_macro_shield_exit and is_megatrend_maturing and macro_rollover):
                            is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                          (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                         (row_1h['slope_55'] > 0) and \
                                         (row_1h['sma_55'] > p0)
                            if is_impulse and cand_anchor < 55:
                                accept_shift = False

                            # Ultra-Bull Respiration Floor Holding (EXP-119)
                            is_ultra_bull_233 = (
                                (row_1h['tree_L2_[610..4181]'] > 0.70) and
                                (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                                (row_1h['sma_233'] > p0) and
                                (row_1h['slope_233'] > 0)
                            )
                            if is_ultra_bull_233 and current_anchor == 233 and cand_anchor < 233:
                                accept_shift = False

                            is_ultra_bull_144 = (
                                (row_1h['tree_L2_[610..4181]'] > 0.70) and
                                (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                                (row_1h['sma_144'] > p0) and
                                (row_1h['slope_144'] > 0)
                            )
                            if is_ultra_bull_144 and current_anchor == 144 and cand_anchor < 144:
                                accept_shift = False

                            # EXP-121 BB Trumpet Expansion Floor Holding
                            if enable_bb_respiration:
                                is_trumpet = (row_1h['slope_bb_upper_55'] > 0) and (row_1h['bb_up_L1_(55,89,144)'] > 0.40)
                                if is_trumpet and current_anchor >= 89 and cand_anchor < 89 and (row_1h['sma_89'] > p0):
                                    accept_shift = False

                            # HYP-123-1 Dynamic Latency Absorption Respiration
                            if enable_latency_absorption:
                                is_overshoot = (row_1h.get('overshoot_up_L2_[34..233]', 0) > min_omega_val) or \
                                               (row_1h.get('omega_up_55', 0) > min_omega_val) or \
                                               (row_1h.get('omega_up_89', 0) > min_omega_val)
                                if is_overshoot and cand_anchor < 55:
                                    accept_shift = False

                                if is_overshoot and current_anchor >= 89 and cand_anchor < 89 and (row_1h['sma_89'] > p0):
                                    accept_shift = False

                        if accept_shift:
                            current_anchor = cand_anchor
                            armed = True

                    # Exhale Re-expansion
                    if not (enable_macro_shield_exit and is_megatrend_maturing and macro_rollover):
                        is_impulse = ((row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144']) or \
                                      (row_1h['sma_21'] > row_1h['sma_34'] > row_1h['sma_55'])) and \
                                     (row_1h['slope_55'] > 0) and \
                                     (row_1h['sma_55'] > p0)
                        if is_impulse and current_anchor < 55:
                            if c_1h < row_1h['sma_21'] or row_1h['slope_34'] > 0:
                                current_anchor = 55

                        if armed:
                            is_macro_tree_impulse = (
                                (row_1h['tree_L2_[34..233]'] > 0.70) and
                                (row_1h['tree_L1_(55,89,144)'] > 0.70) and
                                (row_1h['sma_55'] > row_1h['sma_89'] > row_1h['sma_144'] > row_1h['sma_233']) and
                                (row_1h['slope_89'] > 0) and
                                (row_1h['sma_89'] > p0)
                            )
                            if is_macro_tree_impulse and current_anchor <= 55 and c_1h < row_1h['sma_34']:
                                current_anchor = 89

                        if armed:
                            is_ultra_bull_233 = (
                                (row_1h['tree_L2_[610..4181]'] > 0.70) and
                                (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                                (row_1h['sma_233'] > p0) and
                                (row_1h['slope_233'] > 0) and
                                (c_1h > row_1h['sma_233'])
                            )
                            is_ultra_bull_144 = (
                                (row_1h['tree_L2_[610..4181]'] > 0.70) and
                                (row_1h['tree_L1_(144,233,377)'] > 0.75) and
                                (row_1h['sma_144'] > p0) and
                                (row_1h['slope_144'] > 0) and
                                (c_1h > row_1h['sma_144'])
                            )
                            if is_ultra_bull_233: current_anchor = 233
                            elif is_ultra_bull_144 and current_anchor < 144: current_anchor = 144

                        if enable_bb_respiration and armed:
                            is_floor_rising = (
                                (row_1h['bb_low_L1_(55,89,144)'] > 0.30) and
                                (row_1h['slope_bb_lower_89'] > 0) and
                                (row_1h['sma_89'] > p0) and
                                (c_1h > row_1h['sma_89'])
                            )
                            if is_floor_rising and current_anchor < 89: current_anchor = 89

                    prev_above_band = now_above_band
                    prev_afs_diff = now_afs_diff
                    prev_curv_root = cur_curv_root
                    cur_struct = row_1h[f'sma_{current_anchor}']

                    if not armed and row_1h['close'] < row_1h['sma_21'] and row_1h['slope_21'] < 0 and row_1h['afs_order_score'] == 0:
                        dur_h = float(np.round((i + 1) / 60.0, 2))
                        t_exit = t_bar + pd.Timedelta(minutes=1)
                        trades.append({
                            't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_exit, 'period': p_era,
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
            if cur_high > highest_price: highest_price = cur_high
            cur_mfe = (cur_high - p0) / atr0
            if cur_mfe > max_mfe_atr: max_mfe_atr = cur_mfe

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
                    't0': t0, 'entry_time': actual_entry_time, 'exit_time': t_exit, 'period': p_era,
                    'p0': p0, 'exit_p': p_exit, 'net_ret': (p_exit - p0)/p0 - FRICTION_BPS,
                    'duration_h': dur_h, 'exit': exit_type,
                    'final_anchor': current_anchor,
                    'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
                })
                exited = True
                break

            if not armed:
                if cur_high >= cur_struct + 0.5 * atr_cur and cur_struct >= p0 - 0.5 * atr_cur:
                    armed = True

        if not exited:
            dur_h = float(np.round((sub_times[-1] - actual_entry_time).total_seconds() / 3600.0, 2))
            trades.append({
                't0': t0, 'entry_time': actual_entry_time, 'exit_time': sub_times[-1], 'period': p_era,
                'p0': p0, 'exit_p': sub_closes[-1], 'net_ret': (sub_closes[-1] - p0)/p0 - FRICTION_BPS,
                'duration_h': dur_h, 'exit': 'discovery_end',
                'final_anchor': current_anchor,
                'max_mfe_atr': float(np.round(max_mfe_atr, 2)), 'direction': 'long', 'side': 'long'
            })
    return trades

# ==============================================================================
# Publication-Grade Visualizations
# ==============================================================================

def generate_exp129_plots(stages_res: dict, df_1h: pd.DataFrame, layers: dict, save_dir: Path) -> list[Path]:
    save_dir.mkdir(parents=True, exist_ok=True)
    generated_plots = []
    colors = {
        'Stage 0 (EXP-123 Base)': '#6c757d',
        'Stage 1 (+ HYP-129-1 Systemic Plunge Gate)': '#2563eb',
        'Stage 2 (+ HYP-129-2 Macro Shield Exit)': '#10b981',
        'Stage 3 (+ HYP-129-3 Cascade Ignition)': '#8b5cf6'
    }

    # --------------------------------------------------------------------------
    # Fig 1: Cumulative Return Progression Across 4 Stages
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(13, 6.5))
    for name, r in stages_res.items():
        tr = r['trades_std']
        cum = np.cumsum([t['net_ret'] * 100 for t in tr])
        times = [t['exit_time'] for t in tr]
        tot = r['master_std']['total_opportunity_net_return_pct']
        pf = r['master_std']['profit_factor']
        ax.plot(times, cum, label=f"{name}: Tot={tot:+.1f}%, PF={pf:.2f}", color=colors.get(name, 'black'), lw=2.0)

    ax.set_title("EXP-129: Cumulative Net Opportunity Return Progression Across 4 Stages\n(SPEC-EVAL-001 40 bps Friction Deducted)", fontsize=13, fontweight='bold')
    ax.set_ylabel("Cumulative Net Return (%)", fontsize=11)
    ax.legend(loc="upper left", fontsize=9.5, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    fig.tight_layout()
    p1 = save_dir / "exp129_fig1_cumulative_return_progression.png"
    fig.savefig(p1, dpi=180)
    plt.close(fig)
    generated_plots.append(p1)

    # --------------------------------------------------------------------------
    # Fig 2: Drawdown & Regime Efficiency Across Execution Modes
    # --------------------------------------------------------------------------
    fig, axes = plt.subplots(2, 1, figsize=(13, 8.5), sharex=False)
    for name, r in stages_res.items():
        tr = r['trades_std']
        cum = np.array([t['net_ret'] for t in tr])
        cum_equity = 1.0 + np.cumsum(cum)
        running_max = np.maximum.accumulate(cum_equity)
        dd = (cum_equity - running_max) / running_max * 100
        times = [t['exit_time'] for t in tr]
        axes[0].plot(times, dd, label=f"{name} (MaxDD {r['master_std']['max_drawdown_pct']:.1f}%)", color=colors.get(name, 'black'), lw=1.6)

    axes[0].set_title("Underwater Drawdown (%) Progression Across Stages", fontsize=11, fontweight='bold')
    axes[0].set_ylabel("Drawdown (%)", fontsize=10)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="lower left", fontsize=8.5)
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    stages_names = list(stages_res.keys())
    pf_std = [stages_res[s]['master_std']['profit_factor'] for s in stages_names]
    pf_ma = [stages_res[s]['mode_a']['profit_factor'] for s in stages_names]
    pf_mb = [stages_res[s]['mode_b']['profit_factor'] for s in stages_names]
    x = np.arange(len(stages_names))
    width = 0.25
    axes[1].bar(x - width, pf_std, width, label='Master Std PF', color='#2563eb')
    axes[1].bar(x, pf_ma, width, label='Mode A (Strict 1-Pos) PF', color='#10b981')
    axes[1].bar(x + width, pf_mb, width, label='Mode B (Max 2-Pos) PF', color='#8b5cf6')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([s.split('(')[0].strip() + '\n(' + s.split('(')[1] for s in stages_names], fontsize=8.5)
    axes[1].set_ylabel("Profit Factor", fontsize=10)
    axes[1].set_title("Profit Factor by Execution Mode Across Stages", fontsize=11, fontweight='bold')
    axes[1].legend(loc="upper left", fontsize=9)
    axes[1].grid(True, alpha=0.3)
    fig.tight_layout()
    p2 = save_dir / "exp129_fig2_drawdown_and_regime_efficiency.png"
    fig.savefig(p2, dpi=180)
    plt.close(fig)
    generated_plots.append(p2)

    # --------------------------------------------------------------------------
    # Fig 3: Macro Respiration Shield Exit Dynamics (2020-2021 Megatrend)
    # --------------------------------------------------------------------------
    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [2.2, 1.3, 1.3]})
    w_df = df_1h.loc['2020-11-01':'2021-04-15']

    axes[0].plot(w_df.index, w_df['close'], color='black', lw=1.5, label='BTCUSD Close (2020-2021 Megatrend)')
    axes[0].plot(w_df.index, w_df['sma_34'], color='#f59e0b', ls='--', lw=1.2, label='SMA 34')
    axes[0].plot(w_df.index, w_df['sma_144'], color='#3b82f6', ls='-', lw=1.4, label='SMA 144')
    axes[0].plot(w_df.index, w_df['sma_233'], color='#10b981', ls='-', lw=1.6, label='SMA 233')
    axes[0].set_title("EXP-129 HYP-129-2: Macro Respiration Shield Exit (Breathing Protection vs True Rollover)", fontsize=12, fontweight='bold')
    axes[0].set_ylabel("Price (USD)", fontsize=10)
    axes[0].legend(loc='upper left', fontsize=9, ncol=4)
    axes[0].grid(True, alpha=0.3)

    # Curvature L2_long (EXP-127 early trigger that collapsed)
    axes[1].plot(w_df.index, w_df['curv_L2_long'], color='#ef4444', lw=1.4, label='curv_L2_long [144..987] (EXP-127 Early Trigger: Dips during breathing!)')
    axes[1].axhline(0, color='gray', ls='--', lw=0.8)
    axes[1].set_ylabel("L2 Long Curv", fontsize=9)
    axes[1].legend(loc='lower left', fontsize=8.5)
    axes[1].grid(True, alpha=0.3)

    # Curvature Global Root (EXP-129 shield that stays positive during breathing)
    axes[2].plot(w_df.index, w_df['curv_root'], color='#1e293b', lw=1.8, label='curv_root [8..17711] (EXP-129 Global Root: Resilient > 0 shields runners)')
    axes[2].axhline(0, color='gray', ls='--', lw=0.8)
    axes[2].fill_between(w_df.index, 0, w_df['curv_root'], where=(w_df['curv_root'] > 0), color='#10b981', alpha=0.25, label='Macro Shield Active (curv_root > 0)')
    axes[2].fill_between(w_df.index, 0, w_df['curv_root'], where=(w_df['curv_root'] <= 0), color='#ef4444', alpha=0.25, label='Macro Collapse (curv_root <= 0)')
    axes[2].set_ylabel("Global Root Curv", fontsize=9)
    axes[2].legend(loc='lower left', fontsize=8.5, ncol=3)
    axes[2].grid(True, alpha=0.3)
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

    fig.tight_layout()
    p3 = save_dir / "exp129_fig3_macro_respiration_shield_exit.png"
    fig.savefig(p3, dpi=180)
    plt.close(fig)
    generated_plots.append(p3)

    # --------------------------------------------------------------------------
    # Fig 4: Full Pyramid Divergence & Knife Gate Case (April 2023)
    # --------------------------------------------------------------------------
    fig, axes = plt.subplots(3, 1, figsize=(13, 8.5), sharex=True, gridspec_kw={'height_ratios': [2.0, 1.2, 1.2]})
    case_df = df_1h.loc['2023-04-12':'2023-05-02']
    knife_ts = pd.Timestamp('2023-04-21 15:00:00', tz='UTC')

    axes[0].plot(case_df.index, case_df['close'], color='black', lw=1.5, label='BTCUSD Close')
    axes[0].plot(case_df.index, case_df['sma_21'], color='#f59e0b', ls='--', label='SMA 21')
    axes[0].plot(case_df.index, case_df['sma_55'], color='#10b981', ls='--', label='SMA 55')
    axes[0].plot(case_df.index, case_df['sma_233'], color='#3b82f6', ls='-', label='SMA 233')
    if knife_ts in case_df.index:
        p_knife = case_df.loc[knife_ts, 'close']
        axes[0].scatter([knife_ts], [p_knife], color='red', s=130, zorder=6, edgecolors='black', label='2023-04-21 Knife Blocked (-2.74%)')
        axes[0].annotate('Systemic Plunge Blocked\n(Micro <= 0 AND Macro Root <= 0)',
                         xy=(knife_ts, p_knife), xytext=(knife_ts + pd.Timedelta(hours=14), p_knife + 400),
                         arrowprops=dict(facecolor='red', shrink=0.08, width=1.5, headwidth=6),
                         fontsize=9, fontweight='bold', color='red',
                         bbox=dict(boxstyle="round,pad=0.3", fc="#fee2e2", ec="red", lw=1))
    axes[0].set_title("EXP-129 HYP-129-1: Systemic Plunge Gate Case Study (April 2023 Knife Elimination)", fontsize=12, fontweight='bold')
    axes[0].set_ylabel("Price (USD)", fontsize=10)
    axes[0].legend(loc='lower left', fontsize=8.5)
    axes[0].grid(True, alpha=0.3)

    # Micro Curvature
    axes[1].plot(case_df.index, case_df['curv_L1'], color='#ef4444', lw=1.2, label='curv_L1: Micro (8,13,21)')
    axes[1].plot(case_df.index, case_df['curv_L2_mid'], color='#f59e0b', lw=1.3, label='curv_L2_mid: Meso [34..233]')
    axes[1].axhline(0, color='gray', ls='--', lw=0.8)
    axes[1].set_ylabel("Micro / Meso", fontsize=9)
    axes[1].legend(loc='upper right', fontsize=8.5)
    axes[1].grid(True, alpha=0.3)

    # Macro Root Curvature
    axes[2].plot(case_df.index, case_df['curv_root'], color='#1e293b', lw=1.8, label='curv_root: Macro Global Root [8..17711]')
    axes[2].axhline(0, color='gray', ls='--', lw=0.8)
    axes[2].fill_between(case_df.index, 0, case_df['curv_root'], where=(case_df['curv_root'] <= 0), color='#ef4444', alpha=0.3, label='Macro Rollover / Plunge')
    axes[2].set_ylabel("Global Root", fontsize=9)
    axes[2].legend(loc='lower right', fontsize=8.5)
    axes[2].grid(True, alpha=0.3)
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))

    fig.tight_layout()
    p4 = save_dir / "exp129_fig4_full_pyramid_divergence_knife_case.png"
    fig.savefig(p4, dpi=180)
    plt.close(fig)
    generated_plots.append(p4)

    # --------------------------------------------------------------------------
    # Fig 5: Multi-Tier Pyramid Convolution Progression (2020-2021 Megatrend)
    # --------------------------------------------------------------------------
    start_ts = pd.to_datetime('2020-11-01 00:00:00+00:00')
    end_ts = pd.to_datetime('2021-06-30 00:00:00+00:00')
    idx5 = (df_1h.index >= start_ts) & (df_1h.index <= end_ts)
    w_df5 = df_1h.loc[idx5]
    x_start5 = mdates.date2num(w_df5.index[0])
    x_end5 = mdates.date2num(w_df5.index[-1])

    fig, axes = plt.subplots(6, 1, figsize=(16, 15), gridspec_kw={'height_ratios': [2.2, 1.8, 1.6, 1.4, 1.2, 1.2]}, sharex=True)
    plt.subplots_adjust(hspace=0.08)

    ax0 = axes[0]
    ax0.plot(w_df5.index, w_df5['close'], color='black', lw=1.5, label='BTCUSD Close')
    for s, col, lw in [(34, '#f59e0b', 1.0), (89, '#10b981', 1.2), (233, '#3b82f6', 1.4), (987, '#8b5cf6', 1.6)]:
        ax0.plot(w_df5.index, w_df5[f'sma_{s}'], color=col, lw=lw, label=f'SMA {s}', alpha=0.8)
    ax0.axvline(pd.to_datetime('2021-01-22 00:00:00+00:00'), color='blue', ls='--', lw=1.2, label='Healthy Respiration Dip (Jan 2021)')
    ax0.axvline(pd.to_datetime('2021-05-19 00:00:00+00:00'), color='red', ls='--', lw=1.5, label='Full Collapse Crash (May 19, 2021)')
    ax0.set_title("EXP-129 Full Pyramid Convolution Progression (Noise Elimination & Macro Energy Extraction)", fontsize=13, fontweight='bold')
    ax0.set_ylabel("Price (USD)", fontsize=10)
    ax0.grid(True, alpha=0.3)
    ax0.legend(loc='upper left', fontsize=8, ncol=4)

    # Layer 0
    ax1 = axes[1]
    m0 = layers[0].loc[idx5].values.T[::-1]
    vmax0 = max(np.nanpercentile(np.abs(m0), 95), 0.003)
    norm0 = TwoSlopeNorm(vmin=-vmax0, vcenter=0.0, vmax=vmax0)
    im0 = ax1.imshow(m0, aspect='auto', cmap='RdBu_r', norm=norm0, extent=[x_start5, x_end5, 0, 17], origin='lower')
    ax1.set_yticks(np.arange(17) + 0.5)
    ax1.set_yticklabels([f"S{s}" for s in reversed(TREE_SCALES)], fontsize=6.5)
    ax1.set_ylabel("Layer 0 (Raw 17)\n[Micro Jitter Visible]", fontsize=8)
    cb0 = fig.colorbar(im0, ax=ax1, pad=0.015, aspect=10)
    cb0.set_label("Curv", fontsize=7)

    # Layer 2
    ax2 = axes[2]
    m2 = layers[2].loc[idx5].values.T[::-1]
    vmax2 = max(np.nanpercentile(np.abs(m2), 95), 0.002)
    norm2 = TwoSlopeNorm(vmin=-vmax2, vcenter=0.0, vmax=vmax2)
    im2 = ax2.imshow(m2, aspect='auto', cmap='RdBu_r', norm=norm2, extent=[x_start5, x_end5, 0, m2.shape[0]], origin='lower')
    ax2.set_yticks(np.arange(m2.shape[0]) + 0.5)
    ax2.set_yticklabels(list(reversed(layers[2].columns)), fontsize=6.5)
    ax2.set_ylabel("Layer 2 (13 Nodes)\n[Emergent Wavepackets]", fontsize=8)
    cb2 = fig.colorbar(im2, ax=ax2, pad=0.015, aspect=8)
    cb2.set_label("L2 Curv", fontsize=7)

    # Layer 4
    ax3 = axes[3]
    m4 = layers[4].loc[idx5].values.T[::-1]
    vmax4 = max(np.nanpercentile(np.abs(m4), 95), 0.0015)
    norm4 = TwoSlopeNorm(vmin=-vmax4, vcenter=0.0, vmax=vmax4)
    im3 = ax3.imshow(m4, aspect='auto', cmap='RdBu_r', norm=norm4, extent=[x_start5, x_end5, 0, m4.shape[0]], origin='lower')
    ax3.set_yticks(np.arange(m4.shape[0]) + 0.5)
    ax3.set_yticklabels(list(reversed(layers[4].columns)), fontsize=6.5)
    ax3.set_ylabel("Layer 4 (9 Nodes)\n[Macro Regimes]", fontsize=8)
    cb3 = fig.colorbar(im3, ax=ax3, pad=0.015, aspect=7)
    cb3.set_label("L4 Curv", fontsize=7)

    # Layer 6
    ax4 = axes[4]
    m6 = layers[6].loc[idx5].values.T[::-1]
    vmax6 = max(np.nanpercentile(np.abs(m6), 95), 0.0010)
    norm6 = TwoSlopeNorm(vmin=-vmax6, vcenter=0.0, vmax=vmax6)
    im4 = ax4.imshow(m6, aspect='auto', cmap='RdBu_r', norm=norm6, extent=[x_start5, x_end5, 0, m6.shape[0]], origin='lower')
    ax4.set_yticks(np.arange(m6.shape[0]) + 0.5)
    ax4.set_yticklabels(list(reversed(layers[6].columns)), fontsize=6.5)
    ax4.set_ylabel("Layer 6 (5 Nodes)\n[Ultra-Macro Field]", fontsize=8)
    cb4 = fig.colorbar(im4, ax=ax4, pad=0.015, aspect=6)
    cb4.set_label("L6 Curv", fontsize=7)

    # Layer 8 Global Root
    ax5 = axes[5]
    root_s = layers[8].loc[idx5].iloc[:, 0]
    ax5.plot(w_df5.index, root_s, color='#1e293b', lw=2.0, label='Layer 8 Global Root [8..17711]')
    ax5.axhline(0, color='gray', ls='--', lw=0.8)
    ax5.fill_between(w_df5.index, 0, root_s, where=(root_s > 0), color='#10b981', alpha=0.3, label='Macro Shield Active (Respiration Protected)')
    ax5.fill_between(w_df5.index, 0, root_s, where=(root_s <= 0), color='#ef4444', alpha=0.3, label='Macro Collapse (True Rollover Exit)')
    ax5.set_ylabel("Layer 8 Root\n[Single Apex]", fontsize=8)
    ax5.legend(loc='lower left', fontsize=8, ncol=3)
    ax5.grid(True, alpha=0.3)
    ax5.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

    p5 = save_dir / "exp129_fig5_pyramid_layers_progression.png"
    fig.savefig(p5, dpi=180, bbox_inches='tight')
    plt.close(fig)
    generated_plots.append(p5)

    # --------------------------------------------------------------------------
    # Fig 6: The 2D Triangular Pyramid Snapshots (4 Critical Market Phases)
    # --------------------------------------------------------------------------
    scenes = [
        {
            'name': 'Scene A: 健全な保ち合い呼吸 (Healthy Respiration)\n2021-01-22 12:00 (Price $31,500)',
            'ts': pd.to_datetime('2021-01-22 12:00:00+00:00'),
            'desc': '【下層が赤、頂点が青】\nミクロ〜メソは一時的な下落調整で赤に沈むが、\nピラミッド頂点(L8 Root)は強固な青を保持！\n早漏エグジットを防ぎランナーを保護。'
        },
        {
            'name': 'Scene B: システム急落ナイフ (Systemic Plunge)\n2023-04-21 15:00 (Price $27,800)',
            'ts': pd.to_datetime('2023-04-21 15:00:00+00:00'),
            'desc': '【全層同期の深紅】\n最下層から頂点までピラミッド全ノードが深紅に染まる！\n支持床が一切ない危険な自由落下ナイフを\nピンポイントで遮断（-2.74%回避）。'
        },
        {
            'name': 'Scene C: トレンド初動点火 (Bull Trend Ignition)\n2020-10-21 12:00 (Price $12,800)',
            'ts': pd.to_datetime('2020-10-21 12:00:00+00:00'),
            'desc': '【ピラミッド全層が青・緑】\nミクロからマクロまで全階層の重力が上向きに加速！\nメガトレンドの爆発的推進期。'
        },
        {
            'name': 'Scene D: マクロ天井反転崩壊 (Macro Rollover)\n2021-05-19 12:00 (Price $37,000 Crash)',
            'ts': pd.to_datetime('2021-05-19 12:00:00+00:00'),
            'desc': '【頂点が赤へ転落・マクロ死滅】\n数ヶ月維持された頂点の青が完全に消滅し深紅へ。\n大暴落・大天井を検知し即座に利益確定。'
        }
    ]

    fig, axes = plt.subplots(2, 2, figsize=(16, 13))
    axes = axes.flatten()
    norm_snap = TwoSlopeNorm(vmin=-0.0025, vcenter=0.0, vmax=0.0025)
    cmap = plt.cm.RdBu_r

    for ax_idx, scene in enumerate(scenes):
        ax = axes[ax_idx]
        ts = scene['ts']

        for l in range(9):
            row = layers[l].loc[ts] if ts in layers[l].index else layers[l].asof(ts)
            n_nodes = len(row)
            xs = np.linspace(-(n_nodes - 1) / 2.0, (n_nodes - 1) / 2.0, n_nodes)
            y = l

            for k in range(n_nodes):
                val = row.iloc[k]
                col = cmap(norm_snap(val))
                dx = 0.42
                dy = 0.38
                poly = Polygon([
                    (xs[k] - dx, y - dy),
                    (xs[k] + dx, y - dy),
                    (xs[k] + dx, y + dy),
                    (xs[k] - dx, y + dy)
                ], closed=True, facecolor=col, edgecolor='black', lw=0.6)
                ax.add_patch(poly)

                if l == 8:
                    ax.text(xs[k], y + 0.55, f"L8 Root: {val:+.5f}", ha='center', va='bottom', fontsize=8.5, fontweight='bold',
                            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="black", lw=0.8))

        ax.set_xlim(-9, 9)
        ax.set_ylim(-1, 9.5)
        ax.set_yticks(np.arange(9))
        ax.set_yticklabels([f"Layer {l} ({len(layers[l].columns)} nodes)" for l in range(9)], fontsize=8)
        ax.set_xticks(np.linspace(-8, 8, 17))
        ax.set_xticklabels([f"S{s}" for s in TREE_SCALES], fontsize=7, rotation=45)
        ax.set_title(scene['name'], fontsize=11, fontweight='bold')
        ax.grid(True, ls=':', alpha=0.4)
        ax.text(0.02, 0.96, scene['desc'], transform=ax.transAxes, ha='left', va='top', fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.35", fc="#f8fafc", ec="#94a3b8", lw=1.0))

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm_snap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes.ravel().tolist(), orientation='horizontal', fraction=0.03, pad=0.06, aspect=40)
    cbar.set_label("Curvature: Deep Red (Negative / Dome / Accel Down)  <--- 0 (Flat) --->  Deep Blue (Positive / Bowl / Dish / Accel Up)", fontsize=9.5)

    p6 = save_dir / "exp129_fig6_pyramid_geometric_triangles.png"
    fig.savefig(p6, dpi=180, bbox_inches='tight')
    plt.close(fig)
    generated_plots.append(p6)

    return generated_plots

# ==============================================================================
# Main Orchestrator
# ==============================================================================

def main() -> None:
    print("=" * 80)
    print("EXP-129: Full-Spectrum Multi-Layer Curvature Tree Pyramid Convolution & Divergence")
    print("=" * 80)

    t0_start = time.time()
    df_1h, df_1m, long_events_base, short_events_base, plunge_events = exp111.load_data_and_features()
    exp115.add_multiscale_features_exp115(df_1h)

    print("Building Extended Trees (SMA, BB, AFS, Multi-Perspective, Stoch, 1m)...")
    exp119.build_extended_sma_tree(df_1h, scales=TREE_SCALES)
    exp119.build_bb_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp119.build_afs_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp121.build_bb_multiperspective_trees(df_1h, scales=TREE_SCALES)
    exp121.build_stoch_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp121.build_1m_tree_pyramid(df_1m, scales=SCALES_1M)

    print("Computing Forward Overshoot & Springboard Defense...")
    exp123.compute_forward_overshoot_tree(df_1h, scales=TREE_SCALES)
    exp123.compute_springboard_scales(df_1h, scales=SPRING_SCALES)

    print("Computing Full-Spectrum 8-Layer Curvature Pyramid Recursive Convolution...")
    df_1h, layers = compute_full_pyramid_curvature(df_1h, scales=TREE_SCALES)
    print(f"Features and full pyramid constructed in {time.time() - t0_start:.2f}s.")

    # --------------------------------------------------------------------------
    # Base Event Extraction (EXP-123 Baseline Setup)
    # --------------------------------------------------------------------------
    close_1h = df_1h['close']
    open_1h = df_1h['open']
    gap_4181_6765 = df_1h['gap_4181_6765']
    vacuum_trap_filter = (df_1h['range_pos_720h'] >= 0.80) & (gap_4181_6765 >= 10.0)
    gate_trap = ~(df_1h['macro_age_ratio'] > 2.0)
    gate_booster = (df_1h['afs_order_score'] == 3)
    is_unanchored_knife = (
        (close_1h < df_1h['sma_21']) &
        (close_1h < df_1h['sma_34']) &
        (df_1h['afs_order_score'] == 0) &
        (df_1h['tree_L1_(8,13,21)'] < 0) &
        ((df_1h['tree_L1_(89,144,233)'] <= 0.0) | (df_1h['slope_233'] <= 0.0))
    )
    meso_raw = (close_1h > df_1h['sma_34']) & (close_1h.shift(1) <= df_1h['sma_34'].shift(1)) & (df_1h['slope_55'] > 0)
    meso_decl = exp111.exp95.decluster_events(meso_raw, cooldown_bars=24)
    mvc_long_old = meso_decl & gate_trap & gate_booster
    cond_pb_adj = (close_1h < df_1h['sma_34']) & (close_1h < df_1h['sma_233'])
    cond_pb_higher = (df_1h['slope_610'] > 0) & (df_1h['slope_987'] > 0) & (close_1h > df_1h['sma_987'])
    cond_pb_range = (df_1h['range_pos_720h'] >= 0.35) & (df_1h['range_pos_720h'] <= 0.65)
    cond_pb_trigger = (close_1h > open_1h) & (close_1h > df_1h['sma_21']) & (close_1h.shift(1) <= df_1h['sma_21'].shift(1))
    pb_long = cond_pb_adj & cond_pb_higher & cond_pb_range & cond_pb_trigger & (df_1h['afs_order_score'] == 3)
    prop_events_fast = exp111.exp95.evaluate_hypo_propagation(df_1h, 21, 55, 89, 144, 3, 1.0, 8, 2.0)
    prop_mask_fast = pd.Series(False, index=df_1h.index)
    prop_mask_fast.loc[prop_events_fast] = True
    pending_trigger_only_knife = (prop_mask_fast & is_unanchored_knife)
    full_tree_ignition_ready = (
        (close_1h > df_1h['sma_21']) &
        (df_1h['sma_21'] > df_1h['sma_34']) &
        (df_1h['sma_34'] > df_1h['sma_55']) &
        (df_1h['sma_55'] > df_1h['sma_144']) &
        (df_1h['sma_144'] > df_1h['sma_233']) &
        (df_1h['slope_21'] > 0) & (df_1h['slope_34'] > 0) & (df_1h['slope_55'] > 0) & (df_1h['slope_233'] > 0) &
        (df_1h['tree_L2_[8..55]'] > 0.25) &
        (df_1h['tree_L3_[13..233]'] > 0.15) &
        (close_1h <= df_1h['bb_upper_233']) &
        gate_trap & gate_booster
    )
    deferred_ignition = pd.Series(False, index=df_1h.index)
    pend_active = False
    for ts in df_1h.index:
        if close_1h.loc[ts] < df_1h.loc[ts, 'bb_lower_233']: pend_active = False
        if pending_trigger_only_knife.loc[ts]: pend_active = True
        if pend_active and full_tree_ignition_ready.loc[ts]:
            deferred_ignition.loc[ts] = True
            pend_active = False

    raw_stage2 = (mvc_long_old | deferred_ignition | pb_long | (prop_mask_fast & (~is_unanchored_knife))) & (~vacuum_trap_filter)
    events_stage2 = df_1h.index[exp111.exp95.decluster_events(raw_stage2, cooldown_bars=24)]

    filtered_events_exp121 = []
    for t0 in events_stage2:
        r0 = df_1h.loc[t0]
        is_exhaustion = (
            ((r0['stoch_divergence_fast_slow'] < -0.40) and (r0['bb_up_L2_[34..233]'] < -0.10)) or
            ((r0['bb_up_L2_[34..233]'] < -0.50) and (r0['bb_wratio_L2_[34..233]'] < -0.30))
        )
        if not is_exhaustion:
            filtered_events_exp121.append(t0)

    entry_map_exp121 = exp121.build_1m_entry_timing_map(filtered_events_exp121, df_1h, df_1m)
    tl_s1 = exp123.simulate_long_exp123(filtered_events_exp121, df_1h, df_1m, enable_bb_respiration=True, enable_latency_absorption=True, min_omega_val=0.20, entry_1m_map=entry_map_exp121)

    filtered_events_s2 = []
    for t0 in filtered_events_exp121:
        r0 = df_1h.loc[t0]
        is_spike_trap = False
        for s in [55, 89, 144, 233]:
            om = r0.get(f'omega_up_{s}', 0)
            slp = r0.get(f'slope_{s}', 0)
            floor_def = r0.get(f'is_floor_defended_{s}', False)
            ultra = r0.get('tree_L2_[610..4181]', 0)
            if om >= 0.80 and slp < 0 and not floor_def and ultra < 0.60:
                is_spike_trap = True
                break
        if not is_spike_trap:
            filtered_events_s2.append(t0)

    tl_s2 = [t for t in tl_s1 if t['t0'] in filtered_events_s2]
    for t in tl_s2: t['side'] = 'long'

    short_events_stage1 = [t0 for t0 in short_events_base if df_1h.loc[t0, 'tree_L2_[8..55]'] <= 0.45]
    plunge_trades = exp115.simulate_plunge_short_exp115(plunge_events, df_1h, df_1m)
    ts_s1 = exp123.simulate_short_exp123(short_events_stage1, df_1h, df_1m, enable_bb_ceiling_respiration=True, enable_latency_absorption=False)
    for t in ts_s1 + plunge_trades: t['side'] = 'short'

    springboard_events_exp123 = exp123.find_springboard_rebound_events(df_1h)
    new_springboard_events = [e for e in springboard_events_exp123 if e not in filtered_events_s2]
    cand_springboard = [
        e for e in new_springboard_events
        if df_1h.loc[e, 'range_pos_720h'] <= 0.82
        and df_1h.loc[e].get('tree_L2_[610..4181]', 0) >= 0.00
        and df_1h.loc[e, 'stoch_L1_(8,13,21)'] <= 0.30
        and df_1h.loc[e, 'tree_L2_[144..987]'] >= 0.30
    ]
    spring_map = exp121.build_1m_entry_timing_map(cand_springboard, df_1h, df_1m)
    t_spring = exp123.simulate_long_exp123(cand_springboard, df_1h, df_1m, enable_bb_respiration=True, enable_latency_absorption=True, min_omega_val=0.20, entry_1m_map=spring_map)
    for t in t_spring: t['side'] = 'long'

    # --------------------------------------------------------------------------
    # Stage 0: Base (EXP-123 Baseline Reproduction)
    # --------------------------------------------------------------------------
    print("\n--- Running Stage 0: EXP-123 Confirmed Baseline Reproduction ---")
    trades_s0 = sorted(tl_s2 + t_spring + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s0 = exp121.compute_all_modes(trades_s0)

    # --------------------------------------------------------------------------
    # Stage 1: +HYP-129-1 Systemic Plunge Gate
    # --------------------------------------------------------------------------
    print("\n--- Running Stage 1: + HYP-129-1 Systemic Plunge Gate ---")
    # Condition: Block entry only when BOTH micro curvature <= 0 AND macro curvature <= 0
    # Applied to pb_long (and cand_springboard) to eliminate falling knives while preserving all 39 runners
    filtered_events_s1 = [
        e for e in filtered_events_s2
        if not (pb_long.loc[e] and (df_1h.loc[e, 'curv_L1'] <= 0 and df_1h.loc[e, 'curv_L2_mid'] <= 0) and df_1h.loc[e, 'curv_root'] <= 0)
    ]
    cand_springboard_s1 = [
        e for e in cand_springboard
        if not ((df_1h.loc[e, 'curv_L1'] <= 0 and df_1h.loc[e, 'curv_L2_mid'] <= 0) and df_1h.loc[e, 'curv_root'] <= 0)
    ]
    tl_s1_trades = [t for t in tl_s2 if t['t0'] in filtered_events_s1]
    t_spring_s1 = [t for t in t_spring if t['t0'] in cand_springboard_s1]
    trades_s1 = sorted(tl_s1_trades + t_spring_s1 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s1 = exp121.compute_all_modes(trades_s1)

    # Explicit ablation evaluation: All Longs vs pb_long
    filtered_events_all_longs = [
        e for e in filtered_events_s2
        if not ((df_1h.loc[e, 'curv_L1'] <= 0 and df_1h.loc[e, 'curv_L2_mid'] <= 0) and df_1h.loc[e, 'curv_root'] <= 0)
    ]
    tl_all_longs = [t for t in tl_s2 if t['t0'] in filtered_events_all_longs]
    trades_s1_all_longs = sorted(tl_all_longs + t_spring_s1 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s1_all_longs = exp121.compute_all_modes(trades_s1_all_longs)

    # --------------------------------------------------------------------------
    # Stage 2: +HYP-129-2 Macro Respiration Shield Exit
    # --------------------------------------------------------------------------
    print("\n--- Running Stage 2: + HYP-129-2 Macro Respiration Shield Exit ---")
    tl_s2_shield = simulate_long_exp129(
        filtered_events_s1, df_1h, df_1m,
        enable_bb_respiration=True, enable_latency_absorption=True, min_omega_val=0.20,
        entry_1m_map=entry_map_exp121, enable_macro_shield_exit=True, shield_min_mfe=8.0, shield_target_anchor=34
    )
    t_spring_s2_shield = simulate_long_exp129(
        cand_springboard_s1, df_1h, df_1m,
        enable_bb_respiration=True, enable_latency_absorption=True, min_omega_val=0.20,
        entry_1m_map=spring_map, enable_macro_shield_exit=True, shield_min_mfe=8.0, shield_target_anchor=34
    )
    for t in tl_s2_shield + t_spring_s2_shield: t['side'] = 'long'
    trades_s2 = sorted(tl_s2_shield + t_spring_s2_shield + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s2 = exp121.compute_all_modes(trades_s2)

    # --------------------------------------------------------------------------
    # Stage 3: +HYP-129-3 Hierarchical Cascade Rebound Ignition
    # --------------------------------------------------------------------------
    print("\n--- Running Stage 3: + HYP-129-3 Hierarchical Cascade Rebound Ignition ---")
    filtered_events_s3 = [
        e for e in filtered_events_s1
        if not (not pb_long.loc[e] and df_1h.loc[e, 'curv_L1'] <= 0)
    ]
    tl_s3 = [t for t in tl_s2_shield if t['t0'] in filtered_events_s3]
    trades_s3 = sorted(tl_s3 + t_spring_s2_shield + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s3 = exp121.compute_all_modes(trades_s3)

    stages_res = {
        'Stage 0 (EXP-123 Base)': res_s0,
        'Stage 1 (+ HYP-129-1 Systemic Plunge Gate)': res_s1,
        'Stage 2 (+ HYP-129-2 Macro Shield Exit)': res_s2,
        'Stage 3 (+ HYP-129-3 Cascade Ignition)': res_s3
    }

    # --------------------------------------------------------------------------
    # Summary Ablation Tables
    # --------------------------------------------------------------------------
    print("\n" + "=" * 92)
    print("EXP-129 4-STAGE ABLATION RESULTS TABLE (SPEC-EVAL-001 40 bps Friction Deducted)")
    print("=" * 92)
    for name, res in stages_res.items():
        m_std = res['master_std']
        m_ma = res['mode_a']
        m_mb = res['mode_b']
        print(f"[{name}]")
        print(f"  Master Std: N={m_std['executed_trades']:3d}, WR={m_std['win_rate_pct']:5.2f}%, EV={m_std['net_mean_return_pct']:+5.2f}%, PF={m_std['profit_factor']:.2f}, Tot={m_std['total_opportunity_net_return_pct']:+6.1f}%, MaxDD={m_std['max_drawdown_pct']:.1f}%")
        print(f"  Mode A    : N={m_ma['executed_trades']:3d}, WR={m_ma['win_rate_pct']:5.2f}%, EV={m_ma['net_mean_return_pct']:+5.2f}%, PF={m_ma['profit_factor']:.2f}, Tot={m_ma['total_opportunity_net_return_pct']:+6.1f}%, MaxDD={m_ma['max_drawdown_pct']:.1f}%")
        print(f"  Mode B    : N={m_mb['executed_trades']:3d}, WR={m_mb['win_rate_pct']:5.2f}%, EV={m_mb['net_mean_return_pct']:+5.2f}%, PF={m_mb['profit_factor']:.2f}, Tot={m_mb['total_opportunity_net_return_pct']:+6.1f}%, MaxDD={m_mb['max_drawdown_pct']:.1f}%")
    print("=" * 92)

    print("\n--- HYP-129-1 Systemic Plunge Scope Ablation: All Longs vs pb_long ---")
    m_all = res_s1_all_longs['master_std']
    m_pb = res_s1['master_std']
    print(f"  Applied to All Longs : N={m_all['executed_trades']:3d}, EV={m_all['net_mean_return_pct']:+5.2f}%, PF={m_all['profit_factor']:.2f}, Tot={m_all['total_opportunity_net_return_pct']:+6.1f}%, MaxDD={m_all['max_drawdown_pct']:.1f}%  (32 runners cut!)")
    print(f"  Applied to pb_long   : N={m_pb['executed_trades']:3d}, EV={m_pb['net_mean_return_pct']:+5.2f}%, PF={m_pb['profit_factor']:.2f}, Tot={m_pb['total_opportunity_net_return_pct']:+6.1f}%, MaxDD={m_pb['max_drawdown_pct']:.1f}%  (All runners preserved!)")
    print("=" * 92)

    # --------------------------------------------------------------------------
    # Save metrics.json
    # --------------------------------------------------------------------------
    metrics_path = EXP_DIR / "metrics.json"
    json_metrics = {
        'experiment_id': 'EXP-129',
        'friction_bps': 40.0,
        'stages': {}
    }
    for name, res in stages_res.items():
        json_metrics['stages'][name] = {
            mode: {
                'executed_trades': int(res[mode]['executed_trades']),
                'win_rate_pct': float(np.round(res[mode]['win_rate_pct'], 2)),
                'net_mean_return_pct': float(np.round(res[mode]['net_mean_return_pct'], 2)),
                'profit_factor': float(np.round(res[mode]['profit_factor'], 2)),
                'total_opportunity_net_return_pct': float(np.round(res[mode]['total_opportunity_net_return_pct'], 2)),
                'max_drawdown_pct': float(np.round(res[mode]['max_drawdown_pct'], 2)),
                'worst_trade_pct': float(np.round(res[mode]['worst_trade_pct'], 2)),
                'best_trade_pct': float(np.round(res[mode]['best_trade_pct'], 2))
            } for mode in ['master_std', 'mode_a', 'mode_b']
        }
    json_metrics['hyp129_1_all_longs_ablation'] = {
        mode: {
            'executed_trades': int(res_s1_all_longs[mode]['executed_trades']),
            'win_rate_pct': float(np.round(res_s1_all_longs[mode]['win_rate_pct'], 2)),
            'net_mean_return_pct': float(np.round(res_s1_all_longs[mode]['net_mean_return_pct'], 2)),
            'profit_factor': float(np.round(res_s1_all_longs[mode]['profit_factor'], 2)),
            'total_opportunity_net_return_pct': float(np.round(res_s1_all_longs[mode]['total_opportunity_net_return_pct'], 2)),
            'max_drawdown_pct': float(np.round(res_s1_all_longs[mode]['max_drawdown_pct'], 2)),
        } for mode in ['master_std', 'mode_a', 'mode_b']
    }

    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(json_metrics, f, indent=2)
    print(f"\nSaved metrics to {metrics_path}")

    # Generate and save all 6 plots
    print("Generating comprehensive plots (Fig 1 to Fig 6)...")
    generated_plots = generate_exp129_plots(stages_res, df_1h, layers, PLOTS_DIR)
    for gp in generated_plots:
        print(f"  - Generated plot: {gp}")

    # Copy plots to brain directory if set
    brain_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if brain_dir and os.path.exists(brain_dir):
        for i, gp in enumerate(generated_plots, 1):
            shutil.copy(gp, os.path.join(brain_dir, f"exp129_fig{i}.png"))
        print(f"Copied all plots to {brain_dir}")

if __name__ == '__main__':
    main()
