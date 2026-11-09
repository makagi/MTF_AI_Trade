#!/usr/bin/env python3
r"""
EXP-125: Scale-Free Dynamic Extremum Exhaustion Short & Pendulum Double-Wave Capture
====================================================================================

This experiment implements and backtests:
1. Scale-Free Dynamic Focal Scales:
   - Dynamic Focal Scale k^*(t) from volatility front: argmax_s (BW_s / sqrt(s)) or cluster front.
   - Dynamic Macro Reference Scale k_{macro}(t) via phi^2 (~2.618) harmonic escalation.
   - Dynamic Ultra-Long Flat Scale k_{flat}(t) = max { s in S_ultra | |slope_s| <= 0.0025 }.
   - Triplet Scale Compression Ratio rho^*(t) = (SMA_{k^*-1} - SMA_{k^*}) / (SMA_{k^*} - SMA_{k^*+1} + eps).
2. HYP-125-1 (K-074): Scale-Free Dynamic Extremum Exhaustion Short:
   - Detects macro exhaustion tops (Scene 2: Nov 2021 $69k peak) without hardcoded scales.
   - Conditions: s_{macro} > 0, floor margin m_{floor}(k_{macro}) < -1.0 ATR, rho^* < 0, stoch_gap < 0.
3. HYP-125-2 (K-075): Ultra-Long Respiration & Bottom Pendulum Rebound Long:
   - Detects Wave-1 bottom reversals under flat macro regime (Scene 3: Dec 2022 FTX bottom).
   - Captures Wave-1 rebound to $21.6k (+28.8%) seamlessly connecting with EXP-123 Wave-2 Springboard ($22.2k).
4. HYP-125-3: Dynamic Multi-Wave Continuous Capture Master Integration:
   - Full bilateral long/short execution with 1m precision timing, friction 40 bps, 2020-2025 discovery period.
"""

import os
import sys
import json
import time
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT_DIR = r"D:\work\AI-Trade\MTF_AI_Trade"
EXP_DIR = os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/125-dynamic-scale-extremum-double-wave")
PLOTS_DIR = os.path.join(EXP_DIR, "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)
sys.path.insert(0, ROOT_DIR)

import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

exp111 = load_module('exp111_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/111-short-dynamic-trailing-and-macro-bear-adaptation/run.py"))
exp115 = load_module('exp115_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/115-adaptive-multiscale-respiration-and-hysteresis-exit/run.py"))
exp119 = load_module('exp119_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/119-ultra-long-3channel-tree-pyramid/run.py"))
exp121 = load_module('exp121_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/121-multi-perspective-bb-trees-and-1m-execution/run.py"))
exp123 = load_module('exp123_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/123-dynamic-overshoot-and-springboard-respiration/run.py"))

FRICTION_BPS = 0.0040
TREE_SCALES = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]
SCALES_1M = [8, 13, 21, 34, 55, 89, 144, 233, 377]
SPRING_SCALES = [55, 89, 144, 233, 377, 610, 987]

# ==============================================================================
# Feature Engineering: Scale-Free Dynamic Hierarchy
# ==============================================================================

def compute_scale_free_dynamic_features(df_1h, scales=TREE_SCALES):
    """
    Computes scale-free dynamic indicators:
    - k^*(t): focal scale from Cluster Inversion Depth (CID) or dominant volatility
    - k_{macro}(t): harmonic macro scale (2 steps up in Fibonacci ladder)
    - k_{flat}(t): flat ultra-long scale (|slope| <= 0.0025)
    - rho^*(t): triplet compression ratio around k^*
    - stoch_gap(t): dynamic stochastic oscillator divergence (stoch_z_21 - stoch_z_{k_macro})
    - m_floor_{k_macro}(t): dynamic floor defense margin
    """
    scales_fib = [21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181]
    ultra_scales = [610, 987, 1597, 2584, 4181]

    k_front_list = []
    k_macro_list = []
    k_flat_list = []
    rho_star_list = []
    stoch_gap_list = []
    m_floor_km_list = []
    s_macro_list = []

    close_vals = df_1h['close'].values
    atr_vals = df_1h['atr_24'].values
    slope_dict = {s: df_1h[f'slope_{s}'].values for s in scales_fib}
    sma_dict = {s: df_1h[f'sma_{s}'].values for s in scales_fib}
    bb_low_dict = {s: df_1h[f'bb_lower_{s}'].values for s in scales_fib}
    stoch_dict = {s: df_1h[f'stoch_z_{s}'].values if f'stoch_z_{s}' in df_1h.columns else np.zeros(len(df_1h)) for s in scales_fib}
    stoch_21_vals = df_1h['stoch_z_21'].values if 'stoch_z_21' in df_1h.columns else np.zeros(len(df_1h))

    # Precompute rolling min price for scales
    p_min_dict = {}
    for s in scales_fib:
        if s <= 987:
            p_min_dict[s] = df_1h['low'].rolling(s, min_periods=max(5, s//4)).min().values
        else:
            p_min_dict[s] = df_1h['low'].rolling(987, min_periods=50).min().values

    n = len(df_1h)
    for i in range(n):
        # 1. Cluster Inversion Depth (CID)
        cid_bear = 0
        for s in scales_fib:
            if slope_dict[s][i] < 0:
                cid_bear += 1
            else:
                break

        cid_bull = 0
        for s in scales_fib:
            if slope_dict[s][i] > 0:
                cid_bull += 1
            else:
                break

        if cid_bear >= 2:
            k_front = scales_fib[cid_bear - 1]
        elif cid_bull >= 2:
            k_front = scales_fib[cid_bull - 1]
        else:
            k_front = 55
        k_front_list.append(k_front)

        # 2. k_macro(t): step 2 indices up in Fibonacci ladder (~2.618 ratio)
        idx_kf = scales_fib.index(k_front) if k_front in scales_fib else 2
        idx_km = min(idx_kf + 2, len(scales_fib) - 1)
        k_macro = scales_fib[idx_km]
        k_macro_list.append(k_macro)

        # 3. Dynamic macro slope & floor margin
        s_macro = slope_dict[k_macro][i]
        s_macro_list.append(s_macro)
        p_min_km = p_min_dict[k_macro][i]
        atr_i = max(atr_vals[i], 1e-4)
        m_floor_km = (bb_low_dict[k_macro][i] - p_min_km) / atr_i if not np.isnan(p_min_km) else 0.0
        m_floor_km_list.append(m_floor_km)

        # 4. Triplet compression ratio rho^*(t) around k_front
        if 0 < idx_kf < len(scales_fib) - 1:
            s_prev = scales_fib[idx_kf - 1]
            s_next = scales_fib[idx_kf + 1]
            num = sma_dict[s_prev][i] - sma_dict[k_front][i]
            den = sma_dict[k_front][i] - sma_dict[s_next][i] + 1e-6
            rho_star = num / den if abs(den) > 1e-6 else 1.0
        else:
            rho_star = 1.0
        rho_star_list.append(rho_star)

        # 5. k_flat(t): max ultra scale with |slope| <= 0.0025
        k_flat = np.nan
        for s in reversed(ultra_scales):
            if abs(slope_dict[s][i]) <= 0.0025:
                k_flat = s
                break
        k_flat_list.append(k_flat)

        # 6. stoch_gap(t)
        stoch_km = stoch_dict[k_macro][i]
        stoch_gap = stoch_21_vals[i] - stoch_km
        stoch_gap_list.append(stoch_gap)

    df_1h['dyn_k_star'] = k_front_list
    df_1h['dyn_k_macro'] = k_macro_list
    df_1h['dyn_s_macro'] = s_macro_list
    df_1h['dyn_m_floor_macro'] = m_floor_km_list
    df_1h['dyn_rho_star'] = rho_star_list
    df_1h['dyn_k_flat'] = k_flat_list
    df_1h['dyn_stoch_gap'] = stoch_gap_list

# ==============================================================================
# Signal Detectors: Extremum Exhaustion Short & Bottom Pendulum Rebound Long
# ==============================================================================

def find_dynamic_extremum_exhaustion_shorts(df_1h):
    """
    Detects Scale-Free Dynamic Extremum Exhaustion Short (HYP-125-1, K-074).
    Target: Macro Exhaustion Tops (e.g. Nov 2021 $69k peak).
    Requires:
    1. Macro Exhaustion Top Zone: range_pos_720h >= 0.70
    2. Mature macro slope: s_macro > 0
    3. Macro floor defense collapse: m_floor_km < -1.0 ATR
    4. Triplet compression ratio inversion: rho^* < 0
    5. Oscillator divergence & momentum dead-cross: stoch_gap < -0.30
    6. Bearish rejection bar: close < sma_21
    7. Guard against strong bull continuation: tree_L2_[144..987] <= 0.40
    """
    short_events = []
    close = df_1h['close']
    sma_21 = df_1h['sma_21']
    range_pos = df_1h['range_pos_720h']

    for ts in df_1h.index:
        r = df_1h.loc[ts]
        # Condition 1: Macro Overbought / Upper Exhaustion zone
        if range_pos.loc[ts] < 0.70:
            continue
        # Condition 2: Macro slope is mature / positive
        if r['dyn_s_macro'] <= 0:
            continue
        # Condition 3: Macro floor defense collapsed (m_floor < -1.0 ATR)
        if r['dyn_m_floor_macro'] >= -1.0:
            continue
        # Condition 4: Triplet compression inverted (rho^* < 0)
        if r['dyn_rho_star'] >= 0:
            continue
        # Condition 5: Oscillator momentum gap negative (divergence/dead-cross)
        if r['dyn_stoch_gap'] >= -0.30:
            continue
        # Condition 6: Bearish price rejection bar
        if close.loc[ts] >= sma_21.loc[ts]:
            continue
        # Condition 7: Bull trend guard
        if r.get('tree_L2_[144..987]', 0) > 0.40:
            continue

        short_events.append(ts)

    decl_mask = pd.Series(False, index=df_1h.index)
    decl_mask.loc[short_events] = True
    decl_events = df_1h.index[exp111.exp95.decluster_events(decl_mask, cooldown_bars=24)]
    return list(decl_events)

def find_dynamic_pendulum_rebound_longs(df_1h):
    """
    Detects Ultra-Long Respiration & Bottom Pendulum Rebound Long (HYP-125-2, K-075).
    Target: Wave-1 Bottom Reversals (e.g. Dec 2022 FTX Bottom).
    Requires:
    1. Ultra-long flat respiration scale detected (k_flat exists)
    2. Rebound bar confirmation: close > open and close > sma_21
    3. Strong oscillator momentum surge: dyn_stoch_gap >= 1.0
    4. Price in lower-to-middle range: range_pos_720h <= 0.50, or within 4.0 ATR of recent 72h low
    """
    long_events = []
    close = df_1h['close']
    open_p = df_1h['open']
    sma_21 = df_1h['sma_21']
    range_pos = df_1h['range_pos_720h']

    for ts in df_1h.index:
        r = df_1h.loc[ts]
        # Condition 1: Ultra-long flat scale detected (macro horizontal respiration)
        if np.isnan(r['dyn_k_flat']):
            continue
        # Condition 2: Rebound bar confirmation
        if not (close.loc[ts] > open_p.loc[ts] and close.loc[ts] > sma_21.loc[ts]):
            continue
        # Condition 3: Strong oscillator momentum surge
        if r['dyn_stoch_gap'] < 1.0:
            continue
        # Condition 4: Bottom context
        is_bottom = (range_pos.loc[ts] <= 0.50)
        if not is_bottom:
            prior_72 = df_1h.loc[ts - pd.Timedelta(hours=72) : ts]
            if len(prior_72) > 10:
                is_bottom = (close.loc[ts] - prior_72['low'].min()) <= 4.0 * r['atr_24']
        if not is_bottom:
            continue

        long_events.append(ts)

    decl_mask = pd.Series(False, index=df_1h.index)
    decl_mask.loc[long_events] = True
    decl_events = df_1h.index[exp111.exp95.decluster_events(decl_mask, cooldown_bars=24)]
    return list(decl_events)

# ==============================================================================
# Simulation Engine: Integrated Long & Short with Respiration & Precision 1m Timing
# ==============================================================================

def simulate_long_exp125(events, df_1h, df_1m, entry_1m_map=None):
    """
    Simulates Long trades with Dynamic Latency Absorption Respiration (EXP-123 engine).
    """
    return exp123.simulate_long_exp123(
        events, df_1h, df_1m,
        enable_bb_respiration=True,
        enable_latency_absorption=True,
        min_omega_val=0.20,
        entry_1m_map=entry_1m_map
    )

def simulate_short_exp125(events, df_1h, df_1m, entry_1m_map=None):
    """
    Simulates Short trades with Macro Ceiling Respiration and Precision 1m Timing.
    """
    return exp123.simulate_short_exp123(
        events, df_1h, df_1m,
        enable_bb_ceiling_respiration=True,
        enable_latency_absorption=False,
        entry_1m_map=entry_1m_map
    )

# ==============================================================================
# Main Orchestrator
# ==============================================================================

def main():
    print("=" * 80)
    print("EXP-125: Scale-Free Dynamic Extremum Exhaustion Short & Double-Wave Capture")
    print("=" * 80)

    t0_start = time.time()
    df_1h, df_1m, long_events_base, short_events_base, plunge_events = exp111.load_data_and_features()
    exp115.add_multiscale_features_exp115(df_1h)

    print("Building Hierarchical Trees (SMA, BB, AFS, Multi-Perspective, Stoch, 1m)...")
    exp119.build_extended_sma_tree(df_1h, scales=TREE_SCALES)
    exp119.build_bb_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp119.build_afs_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp121.build_bb_multiperspective_trees(df_1h, scales=TREE_SCALES)
    exp121.build_stoch_tree_pyramid(df_1h, scales=TREE_SCALES)
    exp121.build_1m_tree_pyramid(df_1m, scales=SCALES_1M)

    print("Computing Forward Overshoot & Springboard Defense...")
    exp123.compute_forward_overshoot_tree(df_1h, scales=TREE_SCALES)
    exp123.compute_springboard_scales(df_1h, scales=SPRING_SCALES)

    print("Computing Scale-Free Dynamic Hierarchical Features...")
    compute_scale_free_dynamic_features(df_1h, scales=TREE_SCALES)
    print(f"Features loaded and constructed in {time.time() - t0_start:.2f}s.")

    # 1. Base Setup from EXP-123
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
        if close_1h.loc[ts] < df_1h.loc[ts, 'bb_lower_233']:
            pend_active = False
        if pending_trigger_only_knife.loc[ts]:
            pend_active = True
        if pend_active and full_tree_ignition_ready.loc[ts]:
            deferred_ignition.loc[ts] = True
            pend_active = False

    raw_stage2 = (mvc_long_old | deferred_ignition | pb_long | (prop_mask_fast & (~is_unanchored_knife))) & (~vacuum_trap_filter)
    events_stage2 = df_1h.index[exp111.exp95.decluster_events(raw_stage2, cooldown_bars=24)]

    # EXP-121 Filtered Events
    filtered_events_exp121 = []
    for t0 in events_stage2:
        r0 = df_1h.loc[t0]
        is_exhaustion = (
            ((r0['stoch_divergence_fast_slow'] < -0.40) and (r0['bb_up_L2_[34..233]'] < -0.10)) or
            ((r0['bb_up_L2_[34..233]'] < -0.50) and (r0['bb_wratio_L2_[34..233]'] < -0.30))
        )
        if not is_exhaustion:
            filtered_events_exp121.append(t0)

    # EXP-123 Forward Overshoot Gated Events
    filtered_events_exp123 = []
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
            filtered_events_exp123.append(t0)

    # EXP-123 Springboard Events (Wave-2)
    springboard_events_exp123 = exp123.find_springboard_rebound_events(df_1h)
    new_springboard_events = [e for e in springboard_events_exp123 if e not in filtered_events_exp123]
    long_events_exp123 = sorted(filtered_events_exp123 + new_springboard_events)

    short_events_stage1 = [t0 for t0 in short_events_base if df_1h.loc[t0, 'tree_L2_[8..55]'] <= 0.45]
    plunge_trades = exp115.simulate_plunge_short_exp115(plunge_events, df_1h, df_1m)

    # 2. Stage 0: EXP-123 Baseline
    print("\n--- Running Stage 0: EXP-123 Baseline ---")
    entry_map_exp123 = exp121.build_1m_entry_timing_map(long_events_exp123, df_1h, df_1m)
    tl_s0 = exp123.simulate_long_exp123(long_events_exp123, df_1h, df_1m, enable_bb_respiration=True, enable_latency_absorption=True, min_omega_val=0.20, entry_1m_map=entry_map_exp123)
    ts_s0 = exp123.simulate_short_exp123(short_events_stage1, df_1h, df_1m, enable_bb_ceiling_respiration=True, enable_latency_absorption=False)
    for t in tl_s0: t['side'] = 'long'
    for t in ts_s0 + plunge_trades: t['side'] = 'short'
    trades_s0 = sorted(tl_s0 + ts_s0 + plunge_trades, key=lambda x: x['entry_time'])
    res_s0 = exp121.compute_all_modes(trades_s0)

    # 3. Stage 1: + HYP-125-1 (K-074) Scale-Free Dynamic Extremum Exhaustion Short
    print("\n--- Running Stage 1: + Dynamic Extremum Exhaustion Short ---")
    dyn_short_events = find_dynamic_extremum_exhaustion_shorts(df_1h)
    print(f"Detected {len(dyn_short_events)} Dynamic Extremum Exhaustion Short events.")
    # Check Nov 2021 inclusion
    nov2021_shorts = [e for e in dyn_short_events if "2021-11" in str(e)]
    print(f"Nov 2021 Peak Shorts: {nov2021_shorts}")

    all_short_events_s1 = sorted(list(set(short_events_stage1 + dyn_short_events)))
    ts_s1 = exp123.simulate_short_exp123(all_short_events_s1, df_1h, df_1m, enable_bb_ceiling_respiration=True)
    for t in ts_s1 + plunge_trades: t['side'] = 'short'
    trades_s1 = sorted(tl_s0 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s1 = exp121.compute_all_modes(trades_s1)

    # 4. Stage 2: + HYP-125-2 (K-075) Bottom Pendulum Rebound Long
    print("\n--- Running Stage 2: + Bottom Pendulum Rebound Long ---")
    pendulum_long_events = find_dynamic_pendulum_rebound_longs(df_1h)
    print(f"Detected {len(pendulum_long_events)} Bottom Pendulum Rebound Long events.")
    # Check Dec 2022 inclusion
    dec2022_longs = [e for e in pendulum_long_events if "2022-12" in str(e)]
    print(f"Dec 2022 FTX Bottom Longs: {dec2022_longs}")

    all_long_events_s2 = sorted(list(set(long_events_exp123 + pendulum_long_events)))
    entry_map_s2 = exp121.build_1m_entry_timing_map(all_long_events_s2, df_1h, df_1m)
    tl_s2 = exp123.simulate_long_exp123(all_long_events_s2, df_1h, df_1m, enable_bb_respiration=True, enable_latency_absorption=True, min_omega_val=0.20, entry_1m_map=entry_map_s2)
    for t in tl_s2: t['side'] = 'long'
    trades_s2 = sorted(tl_s2 + ts_s0 + plunge_trades, key=lambda x: x['entry_time'])
    res_s2 = exp121.compute_all_modes(trades_s2)

    # 5. Stage 3: Dynamic Multi-Wave Continuous Capture Master Integration (EXP-125 Master)
    print("\n--- Running Stage 3: EXP-125 Dynamic Master (Full Integration) ---")
    trades_s3 = sorted(tl_s2 + ts_s1 + plunge_trades, key=lambda x: x['entry_time'])
    res_s3 = exp121.compute_all_modes(trades_s3)

    # Summary table output
    stages_res = {
        'Stage 0 (EXP-123 Base)': res_s0,
        'Stage 1 (+ Extremum Short)': res_s1,
        'Stage 2 (+ Pendulum Long)': res_s2,
        'Stage 3 (EXP-125 Dynamic Master)': res_s3
    }

    print("\n" + "=" * 90)
    print("ABLATION RESULTS TABLE (EXP-125)")
    print("=" * 90)
    for name, res in stages_res.items():
        m_std = res['master_std']
        m_ma = res['mode_a']
        m_mb = res['mode_b']
        print(f"[{name}]")
        print(f"  Master Std: N={m_std['executed_trades']:3d}, EV={m_std['net_mean_return_pct']:+.2f}%, PF={m_std['profit_factor']:.2f}, Tot={m_std['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_std['max_drawdown_pct']:.1f}%")
        print(f"  Mode A    : N={m_ma['executed_trades']:3d}, EV={m_ma['net_mean_return_pct']:+.2f}%, PF={m_ma['profit_factor']:.2f}, Tot={m_ma['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_ma['max_drawdown_pct']:.1f}%")
        print(f"  Mode B    : N={m_mb['executed_trades']:3d}, EV={m_mb['net_mean_return_pct']:+.2f}%, PF={m_mb['profit_factor']:.2f}, Tot={m_mb['total_opportunity_net_return_pct']:+.1f}%, MaxDD={m_mb['max_drawdown_pct']:.1f}%")
    print("=" * 90)

    # Save metrics JSON (clean scalar serialization)
    metrics_path = os.path.join(EXP_DIR, "metrics.json")
    json_metrics = {
        'experiment_id': 'EXP-125',
        'friction_bps': 40.0,
        'stages': {}
    }
    for name, res in stages_res.items():
        json_metrics['stages'][name] = {
            'master_std': {k: v for k, v in res['master_std'].items() if not isinstance(v, (list, pd.Series, np.ndarray))},
            'mode_a': {k: v for k, v in res['mode_a'].items() if not isinstance(v, (list, pd.Series, np.ndarray))},
            'mode_b': {k: v for k, v in res['mode_b'].items() if not isinstance(v, (list, pd.Series, np.ndarray))},
        }
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(json_metrics, f, indent=2, default=str)
    print(f"Saved metrics to {metrics_path}")

    # Plot 1: Cumulative Return Progression across stages
    fig, ax = plt.subplots(figsize=(14, 7))
    for s_name, color, ls in [
        ('Stage 0 (EXP-123 Base)', '#7f7f7f', '--'),
        ('Stage 1 (+ Extremum Short)', '#1f77b4', '-.'),
        ('Stage 2 (+ Pendulum Long)', '#ff7f0e', ':'),
        ('Stage 3 (EXP-125 Dynamic Master)', '#2ca02c', '-')
    ]:
        m_data = stages_res[s_name]['master_std']
        t_list = trades_s0 if s_name == 'Stage 0 (EXP-123 Base)' else (
            trades_s1 if s_name == 'Stage 1 (+ Extremum Short)' else (
                trades_s2 if s_name == 'Stage 2 (+ Pendulum Long)' else trades_s3
            )
        )
        dates = [t['exit_time'] for t in t_list]
        cum_ret = np.cumsum([t['net_ret'] for t in t_list])
        ax.plot(dates, cum_ret * 100, label=f"{s_name} (Tot: {m_data['total_opportunity_net_return_pct']:+.1f}%, PF: {m_data['profit_factor']:.2f})", color=color, ls=ls, lw=2.0)

    ax.set_title("EXP-125 Cumulative Net Return Progression (Master Std)", fontsize=13, fontweight='bold')
    ax.set_ylabel("Cumulative Net Return (%)", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "exp125_fig1_cumulative_return_progression.png"), dpi=180)
    plt.close()

    # Copy plots to brain dir for user viewing
    brain_dir = r"C:\Users\masak\.gemini\antigravity\brain\9b86fd71-99e1-47cc-83d8-c7c5ae765fcc"
    shutil.copy(os.path.join(PLOTS_DIR, "exp125_fig1_cumulative_return_progression.png"),
                os.path.join(brain_dir, "exp125_fig1_cumulative_return_progression.png"))

    print("Experiment completed successfully.")

if __name__ == '__main__':
    main()
