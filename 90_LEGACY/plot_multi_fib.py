import matplotlib.pyplot as plt
import pandas as pd
from src.data_loader import load_1h_data
from src.features import calculate_fib_features
import os

# Load data and select a specific period
print("Loading data...")
df = load_1h_data(include_holdout=True)
# Jan to mid Feb 2024 gives a good mix of trend and reversal
df_period = df.loc['2024-01-01':'2024-02-15'].copy()

print("Calculating features up to index 12 (period 233)...")
df_period = calculate_fib_features(df_period, max_fib_index=12)

# Set up the plot with 3 subplots
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 14), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1]})

# --- 1. Price and SMAs ---
ax1.plot(df_period.index, df_period['close'], label='Close Price', color='black', linewidth=1.5, zorder=5)

# Short-term SMAs (5, 8, 13) corresponding to FIB_4, FIB_5, FIB_6
ax1.plot(df_period.index, df_period['FIB_4_SMA'], label='SMA 5', color='lightcoral', linewidth=1)
ax1.plot(df_period.index, df_period['FIB_5_SMA'], label='SMA 8', color='red', linewidth=1.2)
ax1.plot(df_period.index, df_period['FIB_6_SMA'], label='SMA 13', color='darkred', linewidth=1)

# Long-term SMAs (89, 144, 233) corresponding to FIB_10, FIB_11, FIB_12
ax1.plot(df_period.index, df_period['FIB_10_SMA'], label='SMA 89', color='lightblue', linewidth=1.5)
ax1.plot(df_period.index, df_period['FIB_11_SMA'], label='SMA 144', color='blue', linewidth=2)
ax1.plot(df_period.index, df_period['FIB_12_SMA'], label='SMA 233', color='darkblue', linewidth=1.5)

ax1.set_title('Price with Short-term (5, 8, 13) and Long-term (89, 144, 233) SMAs')
ax1.set_ylabel('Price (USD)')
ax1.legend(loc='upper left', ncol=2)
ax1.grid(True, alpha=0.3)

# --- 2. Short-term Stoch_d (5, 8, 13) ---
ax2.plot(df_period.index, df_period['FIB_4_stoch_d'], label='Stoch_d 5', color='lightcoral')
ax2.plot(df_period.index, df_period['FIB_5_stoch_d'], label='Stoch_d 8', color='red', linewidth=1.5)
ax2.plot(df_period.index, df_period['FIB_6_stoch_d'], label='Stoch_d 13', color='darkred')
ax2.axhline(80, color='gray', linestyle='--', alpha=0.5)
ax2.axhline(20, color='gray', linestyle='--', alpha=0.5)
ax2.set_title('Short-term Stoch_d Cluster (5, 8, 13)')
ax2.set_ylabel('Value (0-100)')
ax2.set_ylim(0, 100)
ax2.legend(loc='upper left')
ax2.grid(True, alpha=0.3)

# --- 3. Long-term Stoch_d (89, 144, 233) ---
ax3.plot(df_period.index, df_period['FIB_10_stoch_d'], label='Stoch_d 89', color='lightblue')
ax3.plot(df_period.index, df_period['FIB_11_stoch_d'], label='Stoch_d 144', color='blue', linewidth=1.5)
ax3.plot(df_period.index, df_period['FIB_12_stoch_d'], label='Stoch_d 233', color='darkblue')
ax3.axhline(80, color='gray', linestyle='--', alpha=0.5)
ax3.axhline(20, color='gray', linestyle='--', alpha=0.5)
ax3.set_title('Long-term Stoch_d Cluster (89, 144, 233)')
ax3.set_ylabel('Value (0-100)')
ax3.set_ylim(0, 100)
ax3.legend(loc='upper left')
ax3.grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/multi_fib_observation.png', dpi=150)
print("Saved multi_fib_observation.png")
