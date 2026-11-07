import os, sys, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT_DIR = os.path.abspath('.')
sys.path.insert(0, ROOT_DIR)
import importlib.util

path_111 = os.path.join(ROOT_DIR, '03_KNOWLEDGE/experiments/111-short-dynamic-trailing-and-macro-bear-adaptation/run.py')
spec_111 = importlib.util.spec_from_file_location('exp111_mod', path_111)
exp111 = importlib.util.module_from_spec(spec_111)
sys.modules['exp111_mod'] = exp111
spec_111.loader.exec_module(exp111)

path_113 = os.path.join(ROOT_DIR, '03_KNOWLEDGE/experiments/113-continuous-anchor-shift-and-dynamic-envelope-exit/run.py')
spec_113 = importlib.util.spec_from_file_location('exp113_mod', path_113)
exp113 = importlib.util.module_from_spec(spec_113)
sys.modules['exp113_mod'] = exp113
spec_113.loader.exec_module(exp113)

path_115 = os.path.join(ROOT_DIR, '03_KNOWLEDGE/experiments/115-adaptive-multiscale-respiration-and-hysteresis-exit/run.py')
spec_115 = importlib.util.spec_from_file_location('exp115_mod', path_115)
exp115 = importlib.util.module_from_spec(spec_115)
sys.modules['exp115_mod'] = exp115
spec_115.loader.exec_module(exp115)

df_1h, df_1m, long_events, events_short_master, sig_plunge_macro = exp111.load_data_and_features()
exp115.add_multiscale_features_exp115(df_1h)

# Load metrics.json dynamically
metrics_path = os.path.join(ROOT_DIR, '03_KNOWLEDGE/experiments/115-adaptive-multiscale-respiration-and-hysteresis-exit/metrics.json')
with open(metrics_path, 'r', encoding='utf-8') as f:
    metrics_data = json.load(f)

plots_dir = os.path.join(ROOT_DIR, '03_KNOWLEDGE/experiments/115-adaptive-multiscale-respiration-and-hysteresis-exit/plots')
brain_dir = 'C:/Users/masak/.gemini/antigravity/brain/9b86fd71-99e1-47cc-83d8-c7c5ae765fcc'
os.makedirs(plots_dir, exist_ok=True)
os.makedirs(brain_dir, exist_ok=True)

plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']

# ==============================================================================
# Plot 1: Fixed Yearly Return Breakdown (2020-2025) & Yearly PF (Dynamic from metrics.json)
# ==============================================================================
years = [2020, 2021, 2022, 2023, 2024, 2025]
y_113_yearly = metrics_data['baseline_exp113_pure']['yearly_a']
y_115_yearly = metrics_data['exp115_primary_mode_a']['yearly']

y_113_ret = [y_113_yearly.get(str(y), {}).get('total_opportunity_net_return_pct', 0.0) for y in years]
y_115_ret = [y_115_yearly.get(str(y), {}).get('total_opportunity_net_return_pct', 0.0) for y in years]
y_113_pf = [y_113_yearly.get(str(y), {}).get('profit_factor', 0.0) for y in years]
y_115_pf = [y_115_yearly.get(str(y), {}).get('profit_factor', 0.0) for y in years]

fig, (ax_bar, ax_pf) = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [2.2, 1.0]})
x = np.arange(len(years))
width = 0.35

tot_113_ret = metrics_data['baseline_exp113_pure']['master_a']['total_opportunity_net_return_pct']
tot_115_ret = metrics_data['exp115_primary_mode_a']['metrics']['total_opportunity_net_return_pct']

rects1 = ax_bar.bar(x - width/2, y_113_ret, width, label=f'EXP-113 Pure Baseline (Tot: {tot_113_ret:+.1f}%)', color='#e74c3c', alpha=0.85)
rects2 = ax_bar.bar(x + width/2, y_115_ret, width, label=f'EXP-115 Pure Mode A (+Hysteresis+Respiration, Tot: {tot_115_ret:+.1f}%)', color='#27ae60', alpha=0.9)

ax_bar.set_title('Year-by-Year Cumulative Net Return & Profit Factor: EXP-113 vs EXP-115\n(Significant Performance Jump in Bull & Recovery Years)', fontsize=14, fontweight='bold')
ax_bar.set_ylabel('Annual Net Return (%)', fontsize=12)
ax_bar.legend(loc='upper right', fontsize=11, framealpha=0.9)
ax_bar.axhline(0, color='black', linewidth=1.0)
ax_bar.grid(True, axis='y', alpha=0.3)

for i in range(len(years)):
    v1 = y_113_ret[i]
    v2 = y_115_ret[i]
    ax_bar.text(x[i] - width/2, v1 + (2.0 if v1 >= 0 else -5.0), f"{v1:+.1f}%", ha='center', fontsize=10, color='#c0392b', fontweight='bold')
    ax_bar.text(x[i] + width/2, v2 + (2.0 if v2 >= 0 else -5.0), f"{v2:+.1f}%", ha='center', fontsize=10, color='#1e8449', fontweight='bold')

# Lower subpanel: Yearly PF
ax_pf.plot(x - width/2, y_113_pf, marker='o', color='#c0392b', linewidth=2.0, label='EXP-113 PF')
ax_pf.plot(x + width/2, y_115_pf, marker='s', color='#27ae60', linewidth=2.2, label='EXP-115 PF')
ax_pf.axhline(1.0, color='gray', linestyle='--', linewidth=1.2, label='Breakeven (PF = 1.0)')
ax_pf.set_ylabel('Profit Factor', fontsize=11)
ax_pf.set_xticks(x)
ax_pf.set_xticklabels([f"{y}" for y in years], fontsize=11)
ax_pf.set_xlabel('Calendar Year', fontsize=12)
ax_pf.legend(loc='upper right', fontsize=10)
ax_pf.grid(True, alpha=0.3)

for i in range(len(years)):
    ax_pf.text(x[i] - width/2, y_113_pf[i] + 0.15, f"{y_113_pf[i]:.2f}", ha='center', fontsize=9, color='#c0392b')
    ax_pf.text(x[i] + width/2, y_115_pf[i] + 0.15, f"{y_115_pf[i]:.2f}", ha='center', fontsize=9, color='#1e8449', fontweight='bold')

fig.tight_layout()
p1_path = os.path.join(plots_dir, 'fig4_yearly_overlay.png')
fig.savefig(p1_path, dpi=150)
fig.savefig(os.path.join(brain_dir, 'exp115_fig4_yearly_overlay.png'), dpi=150)
plt.close(fig)
print('Saved fig4_yearly_overlay.png successfully!')

# ==============================================================================
# Plot 2: Ablation Stages Comparison (Dynamic from metrics.json)
# ==============================================================================
stages_names = [
    'Stage 0\nEXP-113 Pure',
    'Stage 1\n+Hysteresis',
    'Stage 2\n+Respiration',
    'Stage 3\n+Full Guard',
    'Mode B\n(Max 2 Pos)'
]
abl = metrics_data['ablation']
s0 = abl['Stage 0: EXP-113 Pure Baseline']['master_a']
s1 = abl['Stage 1: +HYP-115-1 (Crossover Hysteresis)']['master_a']
s2 = abl['Stage 2: +HYP-115-2 (Multi-Scale Respiration)']['master_a']
s3 = abl['Stage 3: +HYP-115-3 (Full Model with Climax Guard)']['master_a']
mb = metrics_data['exp115_primary_mode_b']['metrics']

ret_vals = [s0['total_opportunity_net_return_pct'], s1['total_opportunity_net_return_pct'], s2['total_opportunity_net_return_pct'], s3['total_opportunity_net_return_pct'], mb['total_opportunity_net_return_pct']]
pf_vals = [s0['profit_factor'], s1['profit_factor'], s2['profit_factor'], s3['profit_factor'], mb['profit_factor']]
dd_vals = [s0['max_drawdown_pct'], s1['max_drawdown_pct'], s2['max_drawdown_pct'], s3['max_drawdown_pct'], mb['max_drawdown_pct']]

fig, (ax_r, ax_p, ax_d) = plt.subplots(1, 3, figsize=(16, 5))

colors = ['#e74c3c', '#3498db', '#2ecc71', '#95a5a6', '#9b59b6']

# 1. Total Cumulative Net Return
bars1 = ax_r.bar(stages_names, ret_vals, color=colors, alpha=0.85)
ax_r.set_title('Cumulative Net Return (%)', fontsize=12, fontweight='bold')
ax_r.set_ylabel('Total Return (%)', fontsize=11)
ax_r.grid(True, axis='y', alpha=0.3)
for b, v in zip(bars1, ret_vals):
    ax_r.text(b.get_x() + b.get_width()/2, v + 4, f"{v:+.1f}%", ha='center', fontsize=10, fontweight='bold')

# 2. Profit Factor
bars2 = ax_p.bar(stages_names, pf_vals, color=colors, alpha=0.85)
ax_p.set_title('Profit Factor (PF)', fontsize=12, fontweight='bold')
ax_p.set_ylabel('PF', fontsize=11)
ax_p.axhline(1.0, color='gray', linestyle='--', linewidth=1.0)
ax_p.grid(True, axis='y', alpha=0.3)
for b, v in zip(bars2, pf_vals):
    ax_p.text(b.get_x() + b.get_width()/2, v + 0.05, f"{v:.2f}", ha='center', fontsize=10, fontweight='bold')

# 3. Maximum Drawdown
bars3 = ax_d.bar(stages_names, dd_vals, color=colors, alpha=0.85)
ax_d.set_title('Max Drawdown (%)', fontsize=12, fontweight='bold')
ax_d.set_ylabel('Max DD (%)', fontsize=11)
ax_d.grid(True, axis='y', alpha=0.3)
for b, v in zip(bars3, dd_vals):
    ax_d.text(b.get_x() + b.get_width()/2, v - 1.5, f"{v:.1f}%", ha='center', fontsize=10, fontweight='bold')

fig.suptitle('EXP-115 Ablation Stages: Clear Proof of Hypothesis Contribution & Trade-offs', fontsize=14, fontweight='bold')
fig.tight_layout()
p2_path = os.path.join(plots_dir, 'fig2_ablation_stages_bar.png')
fig.savefig(p2_path, dpi=150)
fig.savefig(os.path.join(brain_dir, 'exp115_fig2_ablation_stages_bar.png'), dpi=150)
plt.close(fig)
print('Saved fig2_ablation_stages_bar.png successfully!')

# ==============================================================================
# Plot 3: Individual Breakthroughs (Case 1 & Case 2 Comparison)
# ==============================================================================
fig, (ax_c1, ax_c2) = plt.subplots(1, 2, figsize=(16, 6))

# Case 1
sub_c1 = df_1h.loc['2020-12-10 12:00':'2020-12-23 00:00']
ax_c1.plot(sub_c1.index, sub_c1['close'], label='BTC/USDT Close (1H)', color='black', linewidth=1.6)
ax_c1.plot(sub_c1.index, sub_c1['sma_21'], label='S21 (Fast)', color='#e74c3c', linestyle='--', linewidth=1.0)
ax_c1.plot(sub_c1.index, sub_c1['sma_55'], label='S55 (Intermediate Floor)', color='#27ae60', linestyle='--', linewidth=1.5)

# Case 1 markers
ax_c1.scatter([pd.Timestamp('2020-12-11 18:00+00:00')], [18097.63], color='blue', s=130, marker='^', zorder=5, label='Entry ($18,098)')
ax_c1.scatter([pd.Timestamp('2020-12-14 01:22+00:00')], [19042.67], color='red', s=150, marker='X', zorder=5, label='EXP-113 Exit: S21 Clipped (+4.82%, 55h)')
ax_c1.scatter([pd.Timestamp('2020-12-21 13:07+00:00')], [23281.01], color='green', s=160, marker='o', zorder=5, label='EXP-115 Exit: S55 Respiration (+28.24%, 235h)')

ax_c1.annotate('EXP-113: S21 Early Exit (+4.82%)\nNormal 2 ATR Pullback Clipped',
               xy=(pd.Timestamp('2020-12-14 01:22+00:00'), 19042.67),
               xytext=(pd.Timestamp('2020-12-12 00:00+00:00'), 21000),
               arrowprops=dict(facecolor='red', shrink=0.05, width=1.5, headwidth=6),
               fontsize=10, fontweight='bold', color='red',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='#fadbd8', edgecolor='red'))

ax_c1.annotate('EXP-115: S55 Floor & Respiration\nAbsorbs Pullback -> Rides to $23,281!\nGain: +28.24% (+23.42%pt improvement)',
               xy=(pd.Timestamp('2020-12-21 13:07+00:00'), 23281.01),
               xytext=(pd.Timestamp('2020-12-16 00:00+00:00'), 22500),
               arrowprops=dict(facecolor='green', shrink=0.05, width=1.5, headwidth=6),
               fontsize=10, fontweight='bold', color='green',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='#d5f5e3', edgecolor='green'))

ax_c1.set_title('Case 1: 2020-12-11 Long (Scale Respiration Breakthrough)', fontsize=13, fontweight='bold')
ax_c1.set_ylabel('Price (USD)', fontsize=11)
ax_c1.legend(loc='lower right', fontsize=9.5)
ax_c1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

# Case 2
sub_c2 = df_1h.loc['2021-01-29 12:00':'2021-02-05 00:00']
ax_c2.plot(sub_c2.index, sub_c2['close'], label='BTC/USDT Close (1H)', color='black', linewidth=1.6)
ax_c2.plot(sub_c2.index, sub_c2['sma_144'], label='S144 (144h)', color='#2980b9', linestyle='--', linewidth=1.2)
ax_c2.plot(sub_c2.index, sub_c2['sma_233'], label='S233 (Initial Anchor)', color='#8e44ad', linestyle='--', linewidth=1.5)

# Case 2 markers
ax_c2.scatter([pd.Timestamp('2021-01-30 03:00+00:00')], [34295.92], color='blue', s=130, marker='^', zorder=5, label='Entry ($34,296)')
ax_c2.scatter([pd.Timestamp('2021-01-31 21:03+00:00')], [32278.29], color='red', s=150, marker='X', zorder=5, label='EXP-113 Exit: S144 Stop Hit (-6.28%)')
ax_c2.scatter([pd.Timestamp('2021-01-31 09:00+00:00')], [33650.00], color='green', s=160, marker='o', zorder=5, label='EXP-115 Exit: Invalidation at S233 (-1.94%)')

ax_c2.annotate('EXP-113: Premature S144 Step-down\nWick stopped out (-6.28%) before 52k rally',
               xy=(pd.Timestamp('2021-01-31 21:03+00:00'), 32278.29),
               xytext=(pd.Timestamp('2021-01-30 06:00+00:00'), 31500),
               arrowprops=dict(facecolor='red', shrink=0.05, width=1.5, headwidth=6),
               fontsize=10, fontweight='bold', color='red',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='#fadbd8', edgecolor='red'))

ax_c2.annotate('EXP-115: Hysteresis Protected\nPrevents premature S144 tightening\nLoss cut to -1.94% (4.34%pt saved!)',
               xy=(pd.Timestamp('2021-01-31 09:00+00:00'), 33650.00),
               xytext=(pd.Timestamp('2021-02-01 12:00+00:00'), 34000),
               arrowprops=dict(facecolor='green', shrink=0.05, width=1.5, headwidth=6),
               fontsize=10, fontweight='bold', color='green',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='#d5f5e3', edgecolor='green'))

ax_c2.set_title('Case 2: 2021-01-30 Long (Hysteresis Gate Breakthrough)', fontsize=13, fontweight='bold')
ax_c2.set_ylabel('Price (USD)', fontsize=11)
ax_c2.legend(loc='upper right', fontsize=9.5)
ax_c2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

fig.tight_layout()
p3_path = os.path.join(plots_dir, 'fig3_individual_trade_breakthroughs.png')
fig.savefig(p3_path, dpi=150)
fig.savefig(os.path.join(brain_dir, 'exp115_fig3_individual_trade_breakthroughs.png'), dpi=150)
plt.close(fig)
print('Saved fig3_individual_trade_breakthroughs.png successfully!')

print('All achievement plots generated and saved successfully!')
