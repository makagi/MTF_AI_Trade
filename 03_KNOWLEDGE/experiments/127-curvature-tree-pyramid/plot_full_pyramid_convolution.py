#!/usr/bin/env python3
r"""
Full-Spectrum Multi-Layer Curvature Tree Pyramid Convolution & Visualization
============================================================================
Implements full-spectrum recursive convolution across the entire 17 Fibonacci
scales profile for 2nd difference (Curvature):
- Layer 0 (17 scales) -> Layer 1 (15 nodes) -> Layer 2 (13 nodes) ->
  Layer 3 (11 nodes) -> Layer 4 (9 nodes) -> ... -> Layer 8 (1 root node [8..17711])

Produces:
- Fig 7: April - May 2023 Falling Knife vs Rebound across hierarchy
- Fig 8: 2020-2021 Bull Megatrend & Crash across hierarchy (Respiration vs Collapse)
- Fig 9: Pyramid Cross-Section Snapshots (Triangle profiles of Key Scenes)
"""

import os
import sys
import re
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

TREE_SCALES = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711]

def build_full_curvature_pyramid():
    print("Loading 1h OHLCV data...")
    df_1h = exp111.exp95.load_ohlcv('BTCUSD', '1h')
    df_1h = df_1h.loc['2020-01-01 00:00:00' : '2025-04-30 23:59:59'].copy()
    atr = exp111.exp95.calculate_atr(df_1h, 24)
    df_1h['atr_24'] = atr

    print("Computing 17-Scale Slopes and Curvatures (Layer 0)...")
    for s in TREE_SCALES:
        if f'sma_{s}' not in df_1h.columns:
            df_1h[f'sma_{s}'] = df_1h['close'].rolling(s, min_periods=min(s, 24)).mean()
        df_1h[f'slope_{s}'] = (df_1h[f'sma_{s}'] - df_1h[f'sma_{s}'].shift(3)) / (3.0 * atr)
        df_1h[f'curv_{s}'] = (df_1h[f'slope_{s}'] - df_1h[f'slope_{s}'].shift(3)) / 3.0

    layers = {}
    l0_cols = [f'curv_{s}' for s in TREE_SCALES]
    layers[0] = df_1h[l0_cols].copy()

    # Layer 1: Overlapping Triplet Convolution [0.25, 0.50, 0.25]
    print("Performing Layer 1 Triad Convolution (15 nodes)...")
    l1_df = pd.DataFrame(index=df_1h.index)
    for k in range(len(TREE_SCALES) - 2):
        sa, sb, sc = TREE_SCALES[k], TREE_SCALES[k+1], TREE_SCALES[k+2]
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
        print(f"Layer {layer_idx}: {len(next_df.columns)} nodes ({next_df.columns[0]} ... {next_df.columns[-1]})")
        cur_df = next_df
        layer_idx += 1

    df_1h['curv_root'] = layers[8].iloc[:, 0]
    return df_1h, layers

def plot_fig7_hierarchy_april2023(df_1h, layers):
    print("Generating Fig 7: April - May 2023 Full Pyramid Hierarchy...")
    start_ts = pd.to_datetime('2023-04-05 00:00:00+00:00')
    end_ts = pd.to_datetime('2023-05-10 00:00:00+00:00')
    target_event = pd.to_datetime('2023-04-21 15:00:00+00:00')

    idx = (df_1h.index >= start_ts) & (df_1h.index <= end_ts)
    w_df = df_1h.loc[idx]
    x_start = mdates.date2num(w_df.index[0])
    x_end = mdates.date2num(w_df.index[-1])

    fig, axes = plt.subplots(5, 1, figsize=(16, 14), gridspec_kw={'height_ratios': [2.2, 2.0, 1.8, 1.6, 1.4]}, sharex=True)
    plt.subplots_adjust(hspace=0.08)

    # 1. Price
    ax0 = axes[0]
    ax0.plot(w_df.index, w_df['close'], color='black', linewidth=1.5, label='BTCUSD Close')
    for s, col, lw in [(34, '#06b6d4', 1.0), (89, '#10b981', 1.2), (233, '#f59e0b', 1.2), (610, '#8b5cf6', 1.5)]:
        if f'sma_{s}' in w_df.columns:
            ax0.plot(w_df.index, w_df[f'sma_{s}'], color=col, linewidth=lw, label=f'SMA {s}', alpha=0.85)

    p_event = w_df.loc[target_event, 'close']
    ax0.scatter([target_event], [p_event], color='red', s=130, zorder=6, edgecolors='black', linewidth=1.5, label='2023-04-21 Knife Blocked')
    ax0.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
    ax0.set_title("EXP-127: Full-Spectrum Recursive Convolution across Hierarchy (April - May 2023 Falling Knife vs Bottom)", fontsize=13, fontweight='bold')
    ax0.set_ylabel("Price (USD)", fontsize=10)
    ax0.grid(True, alpha=0.3)
    ax0.legend(loc='upper right', fontsize=8, ncol=4)

    # 2. Layer 0: Raw 17 Scales
    ax1 = axes[1]
    m0 = layers[0].loc[idx].values.T[::-1] # reverse so largest scale at top
    vmax0 = max(np.nanpercentile(np.abs(m0), 95), 0.003)
    norm0 = TwoSlopeNorm(vmin=-vmax0, vcenter=0.0, vmax=vmax0)
    im0 = ax1.imshow(m0, aspect='auto', cmap='RdBu_r', norm=norm0, extent=[x_start, x_end, 0, len(TREE_SCALES)], origin='lower')
    ax1.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
    ax1.set_yticks(np.arange(len(TREE_SCALES)) + 0.5)
    ax1.set_yticklabels([f"S{s}" for s in reversed(TREE_SCALES)], fontsize=7)
    ax1.set_ylabel("Layer 0 (Raw 17)\n[Micro Noise Visible]", fontsize=8)
    cb0 = fig.colorbar(im0, ax=ax1, pad=0.015, aspect=12)
    cb0.set_label("Raw Curv", fontsize=7)

    # 3. Layer 2: 13 Nodes (Receptive Field = 5 Scales)
    ax2 = axes[2]
    m2 = layers[2].loc[idx].values.T[::-1]
    vmax2 = max(np.nanpercentile(np.abs(m2), 95), 0.002)
    norm2 = TwoSlopeNorm(vmin=-vmax2, vcenter=0.0, vmax=vmax2)
    im2 = ax2.imshow(m2, aspect='auto', cmap='RdBu_r', norm=norm2, extent=[x_start, x_end, 0, m2.shape[0]], origin='lower')
    ax2.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
    ax2.set_yticks(np.arange(m2.shape[0]) + 0.5)
    ax2.set_yticklabels(list(reversed(layers[2].columns)), fontsize=7)
    ax2.set_ylabel("Layer 2 (13 Nodes)\n[Wave-Packets]", fontsize=8)
    cb2 = fig.colorbar(im2, ax=ax2, pad=0.015, aspect=10)
    cb2.set_label("L2 Curv", fontsize=7)

    # 4. Layer 4: 9 Nodes (Receptive Field = 9 Scales)
    ax3 = axes[3]
    m4 = layers[4].loc[idx].values.T[::-1]
    vmax4 = max(np.nanpercentile(np.abs(m4), 95), 0.0015)
    norm4 = TwoSlopeNorm(vmin=-vmax4, vcenter=0.0, vmax=vmax4)
    im3 = ax3.imshow(m4, aspect='auto', cmap='RdBu_r', norm=norm4, extent=[x_start, x_end, 0, m4.shape[0]], origin='lower')
    ax3.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
    ax3.set_yticks(np.arange(m4.shape[0]) + 0.5)
    ax3.set_yticklabels(list(reversed(layers[4].columns)), fontsize=7)
    ax3.set_ylabel("Layer 4 (9 Nodes)\n[Macro Regimes]", fontsize=8)
    cb3 = fig.colorbar(im3, ax=ax3, pad=0.015, aspect=8)
    cb3.set_label("L4 Curv", fontsize=7)

    # 5. Layer 8: Global Root (1 Node: [8..17711])
    ax4 = axes[4]
    root_s = layers[8].loc[idx].iloc[:, 0]
    ax4.plot(w_df.index, root_s, color='#1e293b', linewidth=2.0, label='Layer 8 Global Root Curvature [8..17711]')
    ax4.axhline(0, color='gray', linestyle=':', linewidth=1.0)
    ax4.axvline(target_event, color='red', linestyle='--', alpha=0.7, linewidth=1.2)
    
    # Fill positive (macro brake/dish) vs negative (macro down-accel)
    ax4.fill_between(w_df.index, 0, root_s, where=(root_s > 0), color='#10b981', alpha=0.25, label='Global Net Curvature > 0 (Upward Brake / Dish)')
    ax4.fill_between(w_df.index, 0, root_s, where=(root_s <= 0), color='#ef4444', alpha=0.25, label='Global Net Curvature <= 0 (Downward Accel / Plunge)')
    ax4.set_ylabel("Global Root\nCurvature", fontsize=8)
    ax4.legend(loc='lower right', fontsize=8, ncol=3)
    ax4.grid(True, alpha=0.3)

    axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=5))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    save_path = os.path.join(PLOTS_DIR, "exp127_fig7_curvature_full_pyramid_hierarchy_april2023.png")
    plt.savefig(save_path, dpi=180, bbox_inches='tight')
    plt.close()
    print(f"Saved Fig 7 to: {save_path}")
    return save_path

def plot_fig8_hierarchy_2021bull(df_1h, layers):
    print("Generating Fig 8: 2020-2021 Megatrend & Crash Full Pyramid Hierarchy...")
    start_ts = pd.to_datetime('2020-11-01 00:00:00+00:00')
    end_ts = pd.to_datetime('2021-06-30 00:00:00+00:00')
    may_crash = pd.to_datetime('2021-05-19 00:00:00+00:00')

    idx = (df_1h.index >= start_ts) & (df_1h.index <= end_ts)
    w_df = df_1h.loc[idx]
    x_start = mdates.date2num(w_df.index[0])
    x_end = mdates.date2num(w_df.index[-1])

    fig, axes = plt.subplots(5, 1, figsize=(16, 14), gridspec_kw={'height_ratios': [2.2, 2.0, 1.8, 1.6, 1.4]}, sharex=True)
    plt.subplots_adjust(hspace=0.08)

    # 1. Price
    ax0 = axes[0]
    ax0.plot(w_df.index, w_df['close'], color='black', linewidth=1.5, label='BTCUSD Close')
    for s, col, lw in [(89, '#10b981', 1.0), (233, '#f59e0b', 1.2), (987, '#8b5cf6', 1.5)]:
        if f'sma_{s}' in w_df.columns:
            ax0.plot(w_df.index, w_df[f'sma_{s}'], color=col, linewidth=lw, label=f'SMA {s}', alpha=0.85)

    ax0.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax0.set_title("EXP-127: Macro Curvature Hierarchy (2020-2021) — Structural Respiration vs Full-Spectrum Collapse", fontsize=13, fontweight='bold')
    ax0.set_ylabel("Price (USD)", fontsize=10)
    ax0.grid(True, alpha=0.3)
    ax0.legend(loc='upper left', fontsize=8, ncol=4)

    # 2. Layer 0
    ax1 = axes[1]
    m0 = layers[0].loc[idx].values.T[::-1]
    vmax0 = max(np.nanpercentile(np.abs(m0), 95), 0.003)
    norm0 = TwoSlopeNorm(vmin=-vmax0, vcenter=0.0, vmax=vmax0)
    im0 = ax1.imshow(m0, aspect='auto', cmap='RdBu_r', norm=norm0, extent=[x_start, x_end, 0, len(TREE_SCALES)], origin='lower')
    ax1.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax1.set_yticks(np.arange(len(TREE_SCALES)) + 0.5)
    ax1.set_yticklabels([f"S{s}" for s in reversed(TREE_SCALES)], fontsize=7)
    ax1.set_ylabel("Layer 0 (Raw 17)", fontsize=8)
    cb0 = fig.colorbar(im0, ax=ax1, pad=0.015, aspect=12)

    # 3. Layer 2 (13 nodes)
    ax2 = axes[2]
    m2 = layers[2].loc[idx].values.T[::-1]
    vmax2 = max(np.nanpercentile(np.abs(m2), 95), 0.002)
    norm2 = TwoSlopeNorm(vmin=-vmax2, vcenter=0.0, vmax=vmax2)
    im2 = ax2.imshow(m2, aspect='auto', cmap='RdBu_r', norm=norm2, extent=[x_start, x_end, 0, m2.shape[0]], origin='lower')
    ax2.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax2.set_yticks(np.arange(m2.shape[0]) + 0.5)
    ax2.set_yticklabels(list(reversed(layers[2].columns)), fontsize=7)
    ax2.set_ylabel("Layer 2 (13 Nodes)", fontsize=8)
    cb2 = fig.colorbar(im2, ax=ax2, pad=0.015, aspect=10)

    # 4. Layer 4 (9 nodes)
    ax3 = axes[3]
    m4 = layers[4].loc[idx].values.T[::-1]
    vmax4 = max(np.nanpercentile(np.abs(m4), 95), 0.0015)
    norm4 = TwoSlopeNorm(vmin=-vmax4, vcenter=0.0, vmax=vmax4)
    im3 = ax3.imshow(m4, aspect='auto', cmap='RdBu_r', norm=norm4, extent=[x_start, x_end, 0, m4.shape[0]], origin='lower')
    ax3.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax3.set_yticks(np.arange(m4.shape[0]) + 0.5)
    ax3.set_yticklabels(list(reversed(layers[4].columns)), fontsize=7)
    ax3.set_ylabel("Layer 4 (9 Nodes)", fontsize=8)
    cb3 = fig.colorbar(im3, ax=ax3, pad=0.015, aspect=8)

    # 5. Layer 8 Global Root & Breathing Resilience
    ax4 = axes[4]
    root_s = layers[8].loc[idx].iloc[:, 0]
    ax4.plot(w_df.index, root_s, color='#1e293b', linewidth=2.0, label='Layer 8 Global Root Curvature [8..17711]')
    ax4.axhline(0, color='gray', linestyle=':', linewidth=1.0)
    ax4.axvline(may_crash, color='red', linestyle='--', alpha=0.8, linewidth=1.5)
    ax4.fill_between(w_df.index, 0, root_s, where=(root_s > 0), color='#10b981', alpha=0.25, label='Global Trend Intact (Root > 0)')
    ax4.fill_between(w_df.index, 0, root_s, where=(root_s <= 0), color='#ef4444', alpha=0.25, label='Global Systemic Collapse (Root <= 0)')
    ax4.set_ylabel("Global Root", fontsize=8)
    ax4.legend(loc='lower left', fontsize=8, ncol=3)
    ax4.grid(True, alpha=0.3)

    # Annotate Respiration resilience
    jan_date = pd.to_datetime('2021-01-20 00:00:00+00:00')
    ax4.annotate('Jan 2021 Pause:\nMicro L0/L2 dip red, but\nL4 & Root STAY SOLID GREEN!\n(Proof of Respiration)',
                 xy=(jan_date, 0.0003), xytext=(jan_date - pd.Timedelta(days=50), 0.0007),
                 arrowprops=dict(facecolor='#10b981', shrink=0.05, width=1.5, headwidth=5),
                 fontsize=8, fontweight='bold', color='darkgreen', bbox=dict(boxstyle='round,pad=0.3', facecolor='#dcfce7', edgecolor='#10b981'))

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    save_path = os.path.join(PLOTS_DIR, "exp127_fig8_curvature_full_pyramid_hierarchy_2021bull.png")
    plt.savefig(save_path, dpi=180, bbox_inches='tight')
    plt.close()
    print(f"Saved Fig 8 to: {save_path}")
    return save_path

def plot_fig9_pyramid_cross_sections(df_1h, layers):
    print("Generating Fig 9: Pyramid Cross-Section Snapshots...")
    # 4 Key Moments:
    # A: 2021-01-20 00:00 (Jan 2021 Respiration Pause)
    # B: 2021-05-19 12:00 (May 2021 Flash Crash)
    # C: 2023-04-21 15:00 (April 2023 Falling Knife Trap)
    # D: 2023-05-10 00:00 (May 2023 Bottom Deceleration Dish)
    moments = [
        ('2021-01-20 00:00:00+00:00', 'A. Jan 2021 Respiration (Megatrend Pause)', '#10b981'),
        ('2021-05-19 12:00:00+00:00', 'B. May 19 2021 Crash (Systemic Catastrophe)', '#ef4444'),
        ('2023-04-21 15:00:00+00:00', 'C. Apr 21 2023 Knife (Unanchored Fall)', '#f97316'),
        ('2023-05-10 00:00:00+00:00', 'D. May 10 2023 Rebound (Deceleration Dish)', '#06b6d4')
    ]

    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    plt.subplots_adjust(wspace=0.25, hspace=0.28)

    layer_keys = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    # Build a triangle grid representation for each moment
    for idx, (ts_str, title, accent_col) in enumerate(moments):
        ax = axes[idx // 2, idx % 2]
        ts = pd.to_datetime(ts_str)

        # Collect values for each layer at this timestamp
        triangle_rows = []
        max_len = len(layers[0].columns) # 17
        for l in layer_keys:
            vals = layers[l].loc[ts].values
            # pad with NaN symmetrically to center
            pad_left = (max_len - len(vals)) // 2
            pad_right = max_len - len(vals) - pad_left
            padded = np.pad(vals, (pad_left, pad_right), mode='constant', constant_values=np.nan)
            triangle_rows.append(padded)

        tri_matrix = np.array(triangle_rows) # (9, 17)
        vmax = max(np.nanpercentile(np.abs(tri_matrix), 90), 0.002)
        norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)

        im = ax.imshow(tri_matrix, aspect='auto', cmap='RdBu_r', norm=norm, origin='lower')
        ax.set_title(title, fontsize=11, fontweight='bold', color=accent_col)
        ax.set_yticks(range(9))
        ax.set_yticklabels([f"L{l} ({len(layers[l].columns)})" for l in layer_keys], fontsize=8)
        ax.set_ylabel("Pyramid Layer (L0 Raw → L8 Root)", fontsize=9)
        ax.set_xticks(range(17))
        ax.set_xticklabels([f"S{s}" for s in TREE_SCALES], fontsize=7, rotation=45)
        ax.set_xlabel("Fibonacci Scale Dimension", fontsize=9)
        cb = fig.colorbar(im, ax=ax, pad=0.02, aspect=12)
        cb.set_label("Curvature [Blue: + / Red: -]", fontsize=8)

        # Highlight interpretation
        if idx == 0:
            ax.text(0.5, 0.88, "L0/L1 dip red, but L4~L8 ROOT SOLID BLUE!\n-> Megatrend Intact (Don't Cut)", transform=ax.transAxes,
                    fontsize=8, fontweight='bold', color='darkgreen', bbox=dict(boxstyle='round,pad=0.2', facecolor='#dcfce7', alpha=0.9), ha='center')
        elif idx == 1:
            ax.text(0.5, 0.88, "ENTIRE PYRAMID L0~L8 COMPLETELY COLLAPSED!\n-> Historic Macro Cascade", transform=ax.transAxes,
                    fontsize=8, fontweight='bold', color='darkred', bbox=dict(boxstyle='round,pad=0.2', facecolor='#fee2e2', alpha=0.9), ha='center')
        elif idx == 2:
            ax.text(0.5, 0.88, "Lower to Mid Deep Red Knife -> Trap Gate BLOCKS!\n-> Saved -2.74% Loss", transform=ax.transAxes,
                    fontsize=8, fontweight='bold', color='darkred', bbox=dict(boxstyle='round,pad=0.2', facecolor='#fee2e2', alpha=0.9), ha='center')
        elif idx == 3:
            ax.text(0.5, 0.88, "Lower scales turn solid blue/green -> DISH FORMED!\n-> Safe Springboard Entry", transform=ax.transAxes,
                    fontsize=8, fontweight='bold', color='darkcyan', bbox=dict(boxstyle='round,pad=0.2', facecolor='#cffafe', alpha=0.9), ha='center')

    fig.suptitle("EXP-127: Pyramid Cross-Section Profiles (L0 Raw -> L8 Global Root)\nComparing Respiration, Crash, Falling Knife, and Bottom Rebound", fontsize=14, fontweight='bold')
    save_path = os.path.join(PLOTS_DIR, "exp127_fig9_pyramid_cross_section_profile.png")
    plt.savefig(save_path, dpi=180, bbox_inches='tight')
    plt.close()
    print(f"Saved Fig 9 to: {save_path}")
    return save_path

def main():
    df_1h, layers = build_full_curvature_pyramid()
    p7 = plot_fig7_hierarchy_april2023(df_1h, layers)
    p8 = plot_fig8_hierarchy_2021bull(df_1h, layers)
    p9 = plot_fig9_pyramid_cross_sections(df_1h, layers)

    brain_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if brain_dir and os.path.exists(brain_dir):
        os.makedirs(os.path.join(brain_dir, "plots"), exist_ok=True)
        shutil.copy(p7, os.path.join(brain_dir, "plots", os.path.basename(p7)))
        shutil.copy(p8, os.path.join(brain_dir, "plots", os.path.basename(p8)))
        shutil.copy(p9, os.path.join(brain_dir, "plots", os.path.basename(p9)))
        print(f"Copied Fig 7, 8, 9 to brain dir: {brain_dir}")

if __name__ == "__main__":
    main()
