import matplotlib.pyplot as plt
import pandas as pd
from src.data_loader import load_1h_data
from src.features import calculate_fib_features
import os

print("Loading data...")
df = load_1h_data(include_holdout=True)
df_period = df.loc['2024-01-01':'2024-02-15'].copy()

print("Calculating features up to index 16 (period 1597)...")
df_period = calculate_fib_features(df_period, max_fib_index=16)

# The user's specific AFS definition: AFS(11, 16)
# FIB_11 = 144, FIB_16 = 1597
afs_11_16 = df_period['AFS_11_16']

# Set up the plot with 3 subplots
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 12), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1]})

# --- 1. Price ---
ax1.plot(df_period.index, df_period['close'], label='Close Price', color='black', linewidth=1.5)
ax1.plot(df_period.index, df_period['FIB_11_SMA'], label='SMA 144 (FIB_11)', color='blue', linewidth=1.5)
ax1.plot(df_period.index, df_period['FIB_16_SMA'], label='SMA 1597 (FIB_16)', color='darkblue', linewidth=2)
ax1.set_title('Price with Macro SMAs (144, 1597)')
ax1.set_ylabel('Price (USD)')
ax1.legend(loc='upper left')
ax1.grid(True, alpha=0.3)

# --- 2. Macro AFS (11 to 16) ---
ax2.plot(df_period.index, afs_11_16, label='AFS (11 to 16) - [144 to 1597]', color='purple', linewidth=2)
ax2.axhline(80, color='gray', linestyle='--', alpha=0.5)
ax2.axhline(20, color='gray', linestyle='--', alpha=0.5)
ax2.set_title('Macro AFS: Average of Stoch_d from index 11(144) to 16(1597)')
ax2.set_ylabel('Value (0-100)')
ax2.set_ylim(0, 100)
ax2.legend(loc='upper left')
ax2.grid(True, alpha=0.3)

# --- 3. Short-term Trigger for context ---
ax3.plot(df_period.index, df_period['FIB_5_stoch_d'], label='Stoch_d 8 (Short-term Trigger)', color='red', linewidth=1.5)
ax3.axhline(80, color='gray', linestyle='--', alpha=0.5)
ax3.axhline(20, color='gray', linestyle='--', alpha=0.5)
ax3.set_title('Short-term Stoch_d (FIB_5=8) for Trigger Context')
ax3.set_ylabel('Value (0-100)')
ax3.set_ylim(0, 100)
ax3.legend(loc='upper left')
ax3.grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/macro_afs_observation.png', dpi=150)
print("Saved macro_afs_observation.png")
