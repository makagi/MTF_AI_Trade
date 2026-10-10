import matplotlib.pyplot as plt
import pandas as pd
from src.data_loader import load_1h_data
from src.features import calculate_fib_features
import os

print("Loading data...")
df = load_1h_data(include_holdout=True)

print("Calculating features up to index 16 (period 1597) on FULL data to prevent NaN discontinuities...")
# Calculate on the entire dataset first so rolling windows have enough history
df = calculate_fib_features(df, max_fib_index=16)

# Slice the period AFTER calculation
# Let's look at a slightly wider window to observe the slow macro reversal
df_period = df.loc['2024-01-01':'2024-03-01'].copy()

afs_11_16 = df_period['AFS_11_16']

# Set up the plot with 3 subplots
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 14), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1.5]})

# --- 1. Price ---
ax1.plot(df_period.index, df_period['close'], label='Close Price', color='black', linewidth=1.5)
ax1.plot(df_period.index, df_period['FIB_11_SMA'], label='SMA 144 (FIB_11)', color='blue', linewidth=1)
ax1.plot(df_period.index, df_period['FIB_16_SMA'], label='SMA 1597 (FIB_16)', color='darkblue', linewidth=2)
ax1.set_title('Price with Macro SMAs (144, 1597)')
ax1.set_ylabel('Price (USD)')
ax1.legend(loc='upper left')
ax1.grid(True, alpha=0.3)

# --- 2. Macro AFS (11 to 16) ---
ax2.plot(df_period.index, afs_11_16, label='AFS(11, 16) Overall Average', color='purple', linewidth=2.5)
ax2.axhline(80, color='gray', linestyle='--', alpha=0.5)
ax2.axhline(20, color='gray', linestyle='--', alpha=0.5)
ax2.set_title('Macro AFS(11, 16): Reversal Timing Indicator')
ax2.set_ylabel('Value (0-100)')
ax2.set_ylim(0, 100)
ax2.legend(loc='upper left')
ax2.grid(True, alpha=0.3)

# --- 3. Individual Components (FIB 11 to 16) ---
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
labels = [
    'FIB_11 (144)', 'FIB_12 (233)', 'FIB_13 (377)', 
    'FIB_14 (610)', 'FIB_15 (987)', 'FIB_16 (1597)'
]

for i, idx in enumerate(range(11, 17)):
    col_name = f'FIB_{idx}_stoch_d'
    ax3.plot(df_period.index, df_period[col_name], label=labels[i], color=colors[i], linewidth=1.5)

ax3.axhline(80, color='gray', linestyle='--', alpha=0.5)
ax3.axhline(20, color='gray', linestyle='--', alpha=0.5)
ax3.set_title('Individual Stoch_d Components (FIB 11 to 16) determining the Macro Reversal')
ax3.set_ylabel('Value (0-100)')
ax3.set_ylim(0, 100)
ax3.legend(loc='upper left', ncol=3)
ax3.grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/macro_components_observation.png', dpi=150)
print("Saved macro_components_observation.png")
