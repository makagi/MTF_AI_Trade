#!/usr/bin/env python3
r"""
EXP-129 Hierarchical Pyramid Deep Dive Visualization
====================================================
Generates:
1. exp129_fig5_pyramid_layers_progression.png:
   Multi-tier comparison across layers (Layer 0, Layer 2, Layer 4, Layer 6, Layer 8)
   showing progressive compression from 17 raw scales down to the single Global Root.
2. exp129_fig6_pyramid_geometric_triangles.png:
   Actual 2D triangular pyramid heatmaps at 4 critical market phases:
   - Phase A: 2021-01-22 Bull Megatrend Pullback (Respiration: Red bottom, Blue Apex)
   - Phase B: 2023-04-21 Falling Knife (Systemic Plunge: 100% Red Pyramid)
   - Phase C: 2020-10-21 Megatrend Ignition (Full Bull: 100% Blue Pyramid)
   - Phase D: 2021-05-19 Macro Rollover / Crash (Red Apex & Macro Breakdown)
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Polygon
import shutil

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
exp129_run = load_module('exp129_run_mod', os.path.join(EXP_DIR, "run.py"))

def main():
    print("Loading 1h data & computing full pyramid...")
    df_1h, df_1m, long_events_base, short_events_base, plunge_events = exp111.load_data_and_features()
    if 'atr_24' not in df_1h.columns:
        df_1h['atr_24'] = exp111.exp95.calculate_atr(df_1h, 24)

    df_1h, layers = exp129_run.compute_full_pyramid_curvature(df_1h)

    # =========================================================================
    # 1. Figure 5: Multi-Tier Compression Across Hierarchy (2020-2021 Megatrend)
    # =========================================================================
    print("Generating exp129_fig5_pyramid_layers_progression.png...")
    start_ts = pd.to_datetime('2020-11-01 00:00:00+00:00')
    end_ts = pd.to_datetime('2021-06-30 00:00:00+00:00')
    idx = (df_1h.index >= start_ts) & (df_1h.index <= end_ts)
    w_df = df_1h.loc[idx]
    x_start = mdates.date2num(w_df.index[0])
    x_end = mdates.date2num(w_df.index[-1])

    fig, axes = plt.subplots(6, 1, figsize=(16, 15), gridspec_kw={'height_ratios': [2.2, 1.8, 1.6, 1.4, 1.2, 1.2]}, sharex=True)
    plt.subplots_adjust(hspace=0.08)

    # Panel 0: Price
    ax0 = axes[0]
    ax0.plot(w_df.index, w_df['close'], color='black', lw=1.5, label='BTCUSD Close')
    for s, col, lw in [(34, '#f59e0b', 1.0), (89, '#10b981', 1.2), (233, '#3b82f6', 1.4), (987, '#8b5cf6', 1.6)]:
        ax0.plot(w_df.index, w_df[f'sma_{s}'], color=col, lw=lw, label=f'SMA {s}', alpha=0.8)
    ax0.axvline(pd.to_datetime('2021-01-22 00:00:00+00:00'), color='blue', ls='--', lw=1.2, label='Healthy Respiration Dip (Jan 2021)')
    ax0.axvline(pd.to_datetime('2021-05-19 00:00:00+00:00'), color='red', ls='--', lw=1.5, label='Full Collapse Crash (May 19, 2021)')
    ax0.set_title("EXP-129 Full Pyramid Convolution Progression (Noise Elimination & Macro Energy Extraction)", fontsize=13, fontweight='bold')
    ax0.set_ylabel("Price (USD)", fontsize=10)
    ax0.grid(True, alpha=0.3)
    ax0.legend(loc='upper left', fontsize=8, ncol=4)

    # Panel 1: Layer 0 (Raw 17 Scales)
    ax1 = axes[1]
    m0 = layers[0].loc[idx].values.T[::-1]
    vmax0 = max(np.nanpercentile(np.abs(m0), 95), 0.003)
    norm0 = TwoSlopeNorm(vmin=-vmax0, vcenter=0.0, vmax=vmax0)
    im0 = ax1.imshow(m0, aspect='auto', cmap='RdBu_r', norm=norm0, extent=[x_start, x_end, 0, 17], origin='lower')
    ax1.set_yticks(np.arange(17) + 0.5)
    ax1.set_yticklabels([f"S{s}" for s in reversed(exp129_run.TREE_SCALES)], fontsize=6.5)
    ax1.set_ylabel("Layer 0 (Raw 17)\n[Micro Jitter Visible]", fontsize=8)
    cb0 = fig.colorbar(im0, ax=ax1, pad=0.015, aspect=10)
    cb0.set_label("Curv", fontsize=7)

    # Panel 2: Layer 2 (13 Nodes)
    ax2 = axes[2]
    m2 = layers[2].loc[idx].values.T[::-1]
    vmax2 = max(np.nanpercentile(np.abs(m2), 95), 0.002)
    norm2 = TwoSlopeNorm(vmin=-vmax2, vcenter=0.0, vmax=vmax2)
    im2 = ax2.imshow(m2, aspect='auto', cmap='RdBu_r', norm=norm2, extent=[x_start, x_end, 0, m2.shape[0]], origin='lower')
    ax2.set_yticks(np.arange(m2.shape[0]) + 0.5)
    ax2.set_yticklabels(list(reversed(layers[2].columns)), fontsize=6.5)
    ax2.set_ylabel("Layer 2 (13 Nodes)\n[Emergent Wavepackets]", fontsize=8)
    cb2 = fig.colorbar(im2, ax=ax2, pad=0.015, aspect=8)
    cb2.set_label("L2 Curv", fontsize=7)

    # Panel 3: Layer 4 (9 Nodes)
    ax3 = axes[3]
    m4 = layers[4].loc[idx].values.T[::-1]
    vmax4 = max(np.nanpercentile(np.abs(m4), 95), 0.0015)
    norm4 = TwoSlopeNorm(vmin=-vmax4, vcenter=0.0, vmax=vmax4)
    im3 = ax3.imshow(m4, aspect='auto', cmap='RdBu_r', norm=norm4, extent=[x_start, x_end, 0, m4.shape[0]], origin='lower')
    ax3.set_yticks(np.arange(m4.shape[0]) + 0.5)
    ax3.set_yticklabels(list(reversed(layers[4].columns)), fontsize=6.5)
    ax3.set_ylabel("Layer 4 (9 Nodes)\n[Macro Structural Regimes]", fontsize=8)
    cb3 = fig.colorbar(im3, ax=ax3, pad=0.015, aspect=7)
    cb3.set_label("L4 Curv", fontsize=7)

    # Panel 4: Layer 6 (5 Nodes)
    ax4 = axes[4]
    m6 = layers[6].loc[idx].values.T[::-1]
    vmax6 = max(np.nanpercentile(np.abs(m6), 95), 0.0010)
    norm6 = TwoSlopeNorm(vmin=-vmax6, vcenter=0.0, vmax=vmax6)
    im4 = ax4.imshow(m6, aspect='auto', cmap='RdBu_r', norm=norm6, extent=[x_start, x_end, 0, m6.shape[0]], origin='lower')
    ax4.set_yticks(np.arange(m6.shape[0]) + 0.5)
    ax4.set_yticklabels(list(reversed(layers[6].columns)), fontsize=6.5)
    ax4.set_ylabel("Layer 6 (5 Nodes)\n[Ultra-Macro Field]", fontsize=8)
    cb4 = fig.colorbar(im4, ax=ax4, pad=0.015, aspect=6)
    cb4.set_label("L6 Curv", fontsize=7)

    # Panel 5: Layer 8 Global Root (1 Node)
    ax5 = axes[5]
    root_s = layers[8].loc[idx].iloc[:, 0]
    ax5.plot(w_df.index, root_s, color='#1e293b', lw=2.0, label='Layer 8 Global Root [8..17711]')
    ax5.axhline(0, color='gray', ls='--', lw=0.8)
    ax5.fill_between(w_df.index, 0, root_s, where=(root_s > 0), color='#10b981', alpha=0.3, label='Macro Shield Active (Respiration Protected)')
    ax5.fill_between(w_df.index, 0, root_s, where=(root_s <= 0), color='#ef4444', alpha=0.3, label='Macro Collapse (True Rollover Exit)')
    ax5.set_ylabel("Layer 8 Root\n[Single Apex]", fontsize=8)
    ax5.legend(loc='lower left', fontsize=8, ncol=3)
    ax5.grid(True, alpha=0.3)
    ax5.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

    p5 = os.path.join(PLOTS_DIR, "exp129_fig5_pyramid_layers_progression.png")
    fig.savefig(p5, dpi=180, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {p5}")

    # =========================================================================
    # 2. Figure 6: The 2D Triangular Pyramid Snapshots (4 Critical Market Phases)
    # =========================================================================
    print("Generating exp129_fig6_pyramid_geometric_triangles.png...")
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
        ax.set_xticklabels([f"S{s}" for s in exp129_run.TREE_SCALES], fontsize=7, rotation=45)
        ax.set_title(scene['name'], fontsize=11, fontweight='bold')
        ax.grid(True, ls=':', alpha=0.4)

        ax.text(0.02, 0.96, scene['desc'], transform=ax.transAxes, ha='left', va='top', fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.35", fc="#f8fafc", ec="#94a3b8", lw=1.0))

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm_snap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes.ravel().tolist(), orientation='horizontal', fraction=0.03, pad=0.06, aspect=40)
    cbar.set_label("Curvature: Deep Red (Negative / Dome / Accel Down)  <--- 0 (Flat) --->  Deep Blue (Positive / Bowl / Dish / Accel Up)", fontsize=9.5)

    p6 = os.path.join(PLOTS_DIR, "exp129_fig6_pyramid_geometric_triangles.png")
    fig.savefig(p6, dpi=180, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {p6}")

    # Copy to brain artifact directory
    brain_dir = r"C:\Users\masak\.gemini\antigravity\brain\ab873584-bcb2-48e1-8148-ffcb61e22622\plots"
    os.makedirs(brain_dir, exist_ok=True)
    shutil.copy(p5, os.path.join(brain_dir, "exp129_fig5_pyramid_layers_progression.png"))
    shutil.copy(p6, os.path.join(brain_dir, "exp129_fig6_pyramid_geometric_triangles.png"))
    print("Copied plots to artifact dir.")

if __name__ == '__main__':
    main()
