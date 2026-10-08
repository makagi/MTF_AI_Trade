import matplotlib.pyplot as plt
import pandas as pd
from src.data_loader import load_1h_data
from src.features import calculate_fib_features
import os
import numpy as np

print("Loading data...")
df = load_1h_data(include_holdout=True)

print("Calculating features up to index 16 (period 1597)...")
df = calculate_fib_features(df, max_fib_index=16)

# Calculate custom AFS
# AFS(13, 16) is the average of FIB 13, 14, 15, 16
df['AFS_13_16'] = df[['FIB_13_stoch_d', 'FIB_14_stoch_d', 'FIB_15_stoch_d', 'FIB_16_stoch_d']].mean(axis=1)

# The user mentioned historical MIN/MAX of AFS(1, 16) to AFS(10, 16).
# Let's use AFS_1_16 as the benchmark for "overall system energy".
# Calculate expanding MIN and MAX (historical extremes) of AFS_1_16
# We'll use a 1-year rolling window (365 * 24 = 8760 hours) to represent "historical extremes"
df['AFS_1_16_MAX'] = df['AFS_1_16'].rolling(window=8760, min_periods=1000).max()
df['AFS_1_16_MIN'] = df['AFS_1_16'].rolling(window=8760, min_periods=1000).min()

# Slice for observation
df_period = df.loc['2024-01-01':'2024-04-01'].copy()

# Set up the plot with 3 subplots
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 14), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1.5]})

# --- 1. Price ---
ax1.plot(df_period.index, df_period['close'], label='Close Price', color='black', linewidth=1.5)
ax1.set_title('Price')
ax1.set_ylabel('Price (USD)')
ax1.legend(loc='upper left')
ax1.grid(True, alpha=0.3)

# --- 2. AFS(11, 16) vs AFS(13, 16) (Relationship and Slope) ---
ax2.plot(df_period.index, df_period['AFS_11_16'], label='AFS(11, 16) [Faster Macro]', color='blue', linewidth=2)
ax2.plot(df_period.index, df_period['AFS_13_16'], label='AFS(13, 16) [Slower Macro]', color='darkorange', linewidth=2)
# Fill between to show momentum/trend direction
ax2.fill_between(df_period.index, df_period['AFS_11_16'], df_period['AFS_13_16'], 
                 where=(df_period['AFS_11_16'] >= df_period['AFS_13_16']), color='blue', alpha=0.1)
ax2.fill_between(df_period.index, df_period['AFS_11_16'], df_period['AFS_13_16'], 
                 where=(df_period['AFS_11_16'] < df_period['AFS_13_16']), color='darkorange', alpha=0.1)
ax2.set_title('Relationship and Crossings between AFS(11,16) and AFS(13,16)')
ax2.set_ylabel('Value (0-100)')
ax2.legend(loc='upper left')
ax2.grid(True, alpha=0.3)

# --- 3. AFS(11, 16) reaching Historical Extremes ---
ax3.plot(df_period.index, df_period['AFS_1_16'], label='AFS(1, 16) [Overall System Energy]', color='gray', alpha=0.4, linewidth=1)
ax3.plot(df_period.index, df_period['AFS_1_16_MAX'], label='Historical MAX of AFS(1, 16)', color='red', linestyle='--', linewidth=1.5)
ax3.plot(df_period.index, df_period['AFS_1_16_MIN'], label='Historical MIN of AFS(1, 16)', color='green', linestyle='--', linewidth=1.5)
ax3.plot(df_period.index, df_period['AFS_11_16'], label='AFS(11, 16) [Macro Trend]', color='blue', linewidth=2.5)

ax3.set_title('AFS(11, 16) testing Historical Extremes of AFS(1, 16)')
ax3.set_ylabel('Value (0-100)')
ax3.set_ylim(10, 90)
ax3.legend(loc='upper left')
ax3.grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/afs_topology_observation.png', dpi=150)
print("Saved afs_topology_observation.png")
