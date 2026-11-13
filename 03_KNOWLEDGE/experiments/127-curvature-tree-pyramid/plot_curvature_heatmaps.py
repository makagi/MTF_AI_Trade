#!/usr/bin/env python3
r"""
Generate Curvature Tree Pyramid Heatmap Plots for EXP-127
=========================================================
Visualizes the 17 Fibonacci scales curvature (2nd difference) and wave-packet
pyramid as 2D heatmaps across time, showcasing:
1. 2023-04 Falling Knife vs May Rebound (Trap Gate Deceleration Dish)
2. 2020-2021 Bull Megatrend & May Crash (Curvature Cascade & Respiration)
"""

import os
import sys
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import TwoSlopeNorm

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(EXP_DIR)))
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
exp119 = load_module('exp119_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/119-ultra-long-3channel-tree-pyramid/run.py"))
exp127 = load_module('exp127_mod', os.path.join(ROOT_DIR, "03_KNOWLEDGE/experiments/127-curvature-tree-pyramid/run.py"))

TREE_SCALES = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]

def build_features():
    print("Loading 1h data...")
    df_1h = exp111.exp95.load_ohlcv('BTCUSD', '1h')
    # Filter up to discovery end 2025-04-30
    df_1h = df_1h.loc['2020-01-01 00:00:00' : '2025-04-30 23:59:59'].copy()
    atr_1h = exp111.exp95.calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr_1h
    
    print("Building 17-scale SMAs...")
    exp119.build_extended_sma_tree(df_1h, scales=TREE_SCALES)
    
    print("Computing 17-scale Curvature & Wave-Packets...")
    exp127.compute_curvature_tree_pyramid(df_1h, scales=TREE_SCALES)
    return df_1h

def plot_heatmap_scene1(df_1h):
    """
    Scene 1: April 2023 Falling Knife vs Rebound (2023-04-01 to 2023-05-15)
    """
    print("Generating Heatmap Scene 1: April 2023 Knife Prevention...")
    start_ts = pd.to_datetime('2023-04-05 00:00:00+00:00')
    end_ts = pd.to_datetime('2023-05-10 00:00:00+00:00')
    w_df = df_1h.loc[start_ts : end_ts].copy()
    
    # 17 Scales Curvature Matrix (Scales x Time)
    # Put largest scale at top (reversed)
    scales_rev = list(reversed(TREE_SCALES))
    curv_matrix = np.array([w_df[f'curv_{s}'].values for s in scales_rev])
    
    # Wave-packet matrix
    wp_names = ['curv_L2_ultra', 'curv_L2_long', 'curv_L2_mid', 'curv_L1']
    wp_labels = ['L2_ultra [610..4181]', 'L2_long [144..987]', 'L2_mid [34..233]', 'L1 [8,13,21]']
    wp_matrix = np.array([w_df[col].values for col in wp_names])
    
    fig, axes = plt.subplots(4, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [2.2, 2.5, 1.2, 1.2]}, sharex=True)
    plt.subplots_adjust(hspace=0.08)
    
    # 1. Price Panel
    ax_price = axes[0]
    ax_price.plot(w_df.index, w_df['close'], color='black', linewidth=1.5, label='BTCUSD Close')
    for s, col, lw, ls in [(34, '#06b6d4', 1.0, '-'), (89, '#10b981', 1.2, '-'), (233, '#f59e0b', 1.2, '--'), (610, '#8b5cf6', 1.5, ':')]:
        if f'sma_{s}' in w_df.columns:
            ax_price.plot(w_df.index, w_df[f'sma_{s}'], color=col, linewidth=lw, linestyle=ls, label=f'SMA {s}', alpha=0.85)
            
    # Mark the 2023-04-21 event
    target_event = pd.to_datetime('2023-04-21 15:00:00+00:00')
    if target_event in w_df.index:
        p_event = w_df.loc[target_event, 'close']
        ax_price.scatter([target_event], [p_event], color='red', s=120, zorder=6, edgecolors='black', linewidth=1.5, label='2023-04-21 Knife Blocked (-2.74% saved)')
        ax_price.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
        ax_price.annotate('TRAP GATE BLOCKED!\ncurv_L1 < 0 & curv_L2_mid < 0\n(Falling Knife)',
                          xy=(target_event, p_event), xytext=(target_event + pd.Timedelta(days=2), p_event + 1200),
                          arrowprops=dict(facecolor='red', shrink=0.05, width=1.5, headwidth=6),
                          fontsize=9, fontweight='bold', bbox=dict(boxstyle='round,pad=0.4', facecolor='#fee2e2', edgecolor='red'))
                          
    ax_price.set_title("EXP-127: 17-Scale Curvature Tree Pyramid Heatmap — Falling Knife vs Deceleration Dish (April - May 2023)", fontsize=13, fontweight='bold')
    ax_price.set_ylabel("Price (USD)", fontsize=10)
    ax_price.grid(True, alpha=0.3)
    ax_price.legend(loc='upper right', fontsize=8, ncol=3)
    
    # 2. 17-Scale Curvature Heatmap
    ax_heat17 = axes[1]
    vmax = np.nanpercentile(np.abs(curv_matrix), 95)
    vmax = max(vmax, 0.003)
    norm17 = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    x_start = mdates.date2num(w_df.index[0])
    x_end = mdates.date2num(w_df.index[-1])
    
    im17 = ax_heat17.imshow(curv_matrix, aspect='auto', cmap='RdBu_r', norm=norm17,
                            extent=[x_start, x_end, 0, len(scales_rev)], origin='lower')
    ax_heat17.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
    ax_heat17.set_yticks(np.arange(len(scales_rev)) + 0.5)
    ax_heat17.set_yticklabels([f"S{s}" for s in scales_rev], fontsize=8)
    ax_heat17.set_ylabel("17 Fibonacci Scales\n(S17711 → S8)", fontsize=9)
    cbar17 = fig.colorbar(im17, ax=ax_heat17, pad=0.015, aspect=15)
    cbar17.set_label("Curvature (2nd Diff)\n[Blue/Red: + / -]", fontsize=8)
    
    # Annotate on Heatmap
    ax_heat17.annotate('Full Pyramid Deep Red (Down-Accel Knife)', xy=(target_event, 5), xytext=(target_event + pd.Timedelta(days=2), 7),
                       arrowprops=dict(facecolor='red', shrink=0.05, width=1, headwidth=4),
                       fontsize=8, fontweight='bold', color='darkred', bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.85))
                       
    # 3. Wave-Packet Pyramid Heatmap
    ax_wp = axes[2]
    wp_vmax = np.nanpercentile(np.abs(wp_matrix), 95)
    wp_vmax = max(wp_vmax, 0.002)
    norm_wp = TwoSlopeNorm(vmin=-wp_vmax, vcenter=0.0, vmax=wp_vmax)
    
    im_wp = ax_wp.imshow(wp_matrix, aspect='auto', cmap='RdBu_r', norm=norm_wp,
                         extent=[x_start, x_end, 0, len(wp_names)], origin='lower')
    ax_wp.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
    ax_wp.set_yticks(np.arange(len(wp_names)) + 0.5)
    ax_wp.set_yticklabels(wp_labels, fontsize=8)
    ax_wp.set_ylabel("Wave-Packets", fontsize=9)
    cbar_wp = fig.colorbar(im_wp, ax=ax_wp, pad=0.015, aspect=8)
    cbar_wp.set_label("Packet Curv", fontsize=8)
    
    # 4. Gate Indicator Curves
    ax_gate = axes[3]
    ax_gate.plot(w_df.index, w_df['curv_L1'], color='#10b981', linewidth=1.3, label='curv_L1 (Short)')
    ax_gate.plot(w_df.index, w_df['curv_L2_mid'], color='#06b6d4', linewidth=1.3, label='curv_L2_mid (Mid)')
    ax_gate.axhline(0, color='gray', linestyle=':', linewidth=1.0)
    ax_gate.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
    
    # Fill Gate condition
    gate_open = (w_df['curv_L1'] > 0) | (w_df['curv_L2_mid'] > 0)
    ax_gate.fill_between(w_df.index, -0.005, 0.005, where=gate_open, color='#10b981', alpha=0.15, label='Trap Gate OPEN (Dish)')
    ax_gate.fill_between(w_df.index, -0.005, 0.005, where=~gate_open, color='#ef4444', alpha=0.20, label='Trap Gate BLOCKED (Knife)')
    
    ax_gate.set_ylim(-0.004, 0.004)
    ax_gate.set_ylabel("Gate Curv", fontsize=9)
    ax_gate.legend(loc='lower right', fontsize=8, ncol=4)
    ax_gate.grid(True, alpha=0.3)
    
    # Date formatting
    axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=5))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    plt.xticks(rotation=0)
    
    save_path = os.path.join(PLOTS_DIR, "exp127_fig5_curvature_tree_pyramid_heatmap_april2023.png")
    plt.savefig(save_path, dpi=180, bbox_inches='tight')
    plt.close()
    print(f"Saved Scene 1 Heatmap to: {save_path}")
    return save_path

def plot_heatmap_scene2(df_1h):
    """
    Scene 2: 2020-2021 Bull Megatrend & May Crash (2020-11-01 to 2021-06-30)
    """
    print("Generating Heatmap Scene 2: 2021 Megatrend & Crash...")
    start_ts = pd.to_datetime('2020-11-01 00:00:00+00:00')
    end_ts = pd.to_datetime('2021-06-30 00:00:00+00:00')
    w_df = df_1h.loc[start_ts : end_ts].copy()
    
    scales_rev = list(reversed(TREE_SCALES))
    curv_matrix = np.array([w_df[f'curv_{s}'].values for s in scales_rev])
    slope_matrix = np.array([w_df[f'slope_{s}'].values for s in scales_rev])
    
    wp_names = ['curv_L2_ultra', 'curv_L2_long', 'curv_L2_mid', 'curv_L1']
    wp_labels = ['L2_ultra', 'L2_long', 'L2_mid', 'L1']
    wp_matrix = np.array([w_df[col].values for col in wp_names])
    
    fig, axes = plt.subplots(4, 1, figsize=(16, 13), gridspec_kw={'height_ratios': [2.2, 2.5, 2.5, 1.5]}, sharex=True)
    plt.subplots_adjust(hspace=0.08)
    
    # 1. Price Panel
    ax_price = axes[0]
    ax_price.plot(w_df.index, w_df['close'], color='black', linewidth=1.5, label='BTCUSD Close')
    for s, col, lw, ls in [(89, '#10b981', 1.0, '-'), (233, '#f59e0b', 1.2, '--'), (987, '#8b5cf6', 1.5, ':')]:
        if f'sma_{s}' in w_df.columns:
            ax_price.plot(w_df.index, w_df[f'sma_{s}'], color=col, linewidth=lw, linestyle=ls, label=f'SMA {s}', alpha=0.85)
            
    # Mark May 19 Crash
    may_crash = pd.to_datetime('2021-05-19 00:00:00+00:00')
    ax_price.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax_price.annotate('May 2021 Crash (China Mining Ban)\nFull Tree Pyramid Cascades Red',
                      xy=(may_crash, 40000), xytext=(may_crash - pd.Timedelta(days=55), 58000),
                      arrowprops=dict(facecolor='red', shrink=0.05, width=1.5, headwidth=6),
                      fontsize=9, fontweight='bold', bbox=dict(boxstyle='round,pad=0.4', facecolor='#fee2e2', edgecolor='red'))
                      
    ax_price.set_title("EXP-127: Macro Curvature Cascade & Respiration Heatmap — 2020-2021 Bull Megatrend to Crash", fontsize=13, fontweight='bold')
    ax_price.set_ylabel("Price (USD)", fontsize=10)
    ax_price.grid(True, alpha=0.3)
    ax_price.legend(loc='upper left', fontsize=8, ncol=4)
    
    # 2. 17-Scale Curvature Heatmap (2nd Difference)
    ax_heat17 = axes[1]
    vmax = np.nanpercentile(np.abs(curv_matrix), 95)
    vmax = max(vmax, 0.003)
    norm17 = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    x_start = mdates.date2num(w_df.index[0])
    x_end = mdates.date2num(w_df.index[-1])
    
    im17 = ax_heat17.imshow(curv_matrix, aspect='auto', cmap='RdBu_r', norm=norm17,
                            extent=[x_start, x_end, 0, len(scales_rev)], origin='lower')
    ax_heat17.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax_heat17.set_yticks(np.arange(len(scales_rev)) + 0.5)
    ax_heat17.set_yticklabels([f"S{s}" for s in scales_rev], fontsize=8)
    ax_heat17.set_ylabel("Curvature (2nd Diff)\n17 Scales (S17711 → S8)", fontsize=9)
    cbar17 = fig.colorbar(im17, ax=ax_heat17, pad=0.015, aspect=15)
    cbar17.set_label("Curvature\n[Blue: + / Red: -]", fontsize=8)
    
    # Annotate Respiration in Jan & Feb 2021
    jan_resp = pd.to_datetime('2021-01-20 00:00:00+00:00')
    ax_heat17.annotate('Structural Respiration\n(Mid/Long Red Pause)\nDO NOT CUT RUNNERS!',
                       xy=(jan_resp, 12), xytext=(jan_resp - pd.Timedelta(days=40), 14),
                       arrowprops=dict(facecolor='#f59e0b', shrink=0.05, width=1.2, headwidth=5),
                       fontsize=8, fontweight='bold', color='darkorange', bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.9))
                       
    # 3. 17-Scale Velocity Heatmap (1st Difference / Slope) for Direct Comparison!
    ax_slope = axes[2]
    svmax = np.nanpercentile(np.abs(slope_matrix), 95)
    norm_slope = TwoSlopeNorm(vmin=-svmax, vcenter=0.0, vmax=svmax)
    im_slope = ax_slope.imshow(slope_matrix, aspect='auto', cmap='PuOr_r', norm=norm_slope,
                               extent=[x_start, x_end, 0, len(scales_rev)], origin='lower')
    ax_slope.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax_slope.set_yticks(np.arange(len(scales_rev)) + 0.5)
    ax_slope.set_yticklabels([f"S{s}" for s in scales_rev], fontsize=8)
    ax_slope.set_ylabel("Velocity (1st Diff / Slope)\n17 Scales (S17711 → S8)", fontsize=9)
    cbar_s = fig.colorbar(im_slope, ax=ax_slope, pad=0.015, aspect=15)
    cbar_s.set_label("Slope (Velocity)\n[Purple: + / Orange: -]", fontsize=8)
    
    # 4. Wave-Packets Heatmap
    ax_wp = axes[3]
    wp_vmax = np.nanpercentile(np.abs(wp_matrix), 95)
    norm_wp = TwoSlopeNorm(vmin=-wp_vmax, vcenter=0.0, vmax=wp_vmax)
    im_wp = ax_wp.imshow(wp_matrix, aspect='auto', cmap='RdBu_r', norm=norm_wp,
                         extent=[x_start, x_end, 0, len(wp_names)], origin='lower')
    ax_wp.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax_wp.set_yticks(np.arange(len(wp_names)) + 0.5)
    ax_wp.set_yticklabels(wp_labels, fontsize=8)
    ax_wp.set_ylabel("Wave-Packets", fontsize=9)
    cbar_wp = fig.colorbar(im_wp, ax=ax_wp, pad=0.015, aspect=8)
    cbar_wp.set_label("Packet Curv", fontsize=8)
    
    # Date formatting
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.xticks(rotation=0)
    
    save_path = os.path.join(PLOTS_DIR, "exp127_fig6_curvature_tree_pyramid_heatmap_2021bull.png")
    plt.savefig(save_path, dpi=180, bbox_inches='tight')
    plt.close()
    print(f"Saved Scene 2 Heatmap to: {save_path}")
    return save_path

def main():
    df_1h = build_features()
    p1 = plot_heatmap_scene1(df_1h)
    p2 = plot_heatmap_scene2(df_1h)
    
    # Copy to brain dir
    brain_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if brain_dir and os.path.exists(brain_dir):
        shutil.copy(p1, os.path.join(brain_dir, "plots", os.path.basename(p1)))
        shutil.copy(p2, os.path.join(brain_dir, "plots", os.path.basename(p2)))
        print(f"Copied both heatmaps to brain dir: {brain_dir}")

if __name__ == "__main__":
    main()
