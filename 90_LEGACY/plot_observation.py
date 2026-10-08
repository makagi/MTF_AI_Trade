import matplotlib.pyplot as plt
import pandas as pd
from src.data_loader import load_1h_data
from src.features import calculate_fib_features
import os

# Load data and select a specific period (e.g., Jan-Feb 2024)
print("Loading data...")
df = load_1h_data(include_holdout=True)
df_period = df.loc['2024-01-01':'2024-02-15'].copy()

print("Calculating features...")
df_period = calculate_fib_features(df_period, max_fib_index=11)

# Set up the plot with 3 subplots: Price+SMA+BB, AFS, Stoch_d
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1]})

# 1. Price, SMA, BB (Using FIB_11 which is period 144)
ax1.plot(df_period.index, df_period['close'], label='Close Price', color='black', linewidth=1)
ax1.plot(df_period.index, df_period['FIB_11_SMA'], label='SMA (144)', color='blue', linewidth=1.5)
ax1.plot(df_period.index, df_period['FIB_11_BB_up'], label='BB Up (144)', color='blue', linestyle='--', alpha=0.5)
ax1.plot(df_period.index, df_period['FIB_11_BB_down'], label='BB Down (144)', color='blue', linestyle='--', alpha=0.5)
ax1.plot(df_period.index, df_period['FIB_5_SMA'], label='SMA (8)', color='orange', linewidth=1)
ax1.set_title('BTCUSD Price with Long-term (FIB_11=144) and Short-term (FIB_5=8) SMA/BB')
ax1.set_ylabel('Price (USD)')
ax1.legend(loc='upper left')
ax1.grid(True, alpha=0.3)

# 2. AFS (Average Fibonacci Stoch_d)
# We plot AFS_1_11 (Average of all Stoch_d from index 1 to 11) and maybe AFS_8_11 for mid/long
ax2.plot(df_period.index, df_period['AFS_1_11'], label='AFS_1_11 (Overall Avg)', color='purple')
ax2.plot(df_period.index, df_period['AFS_8_11'], label='AFS_8_11 (Long-term Avg)', color='green')
ax2.axhline(80, color='red', linestyle='--', alpha=0.5)
ax2.axhline(20, color='red', linestyle='--', alpha=0.5)
ax2.set_title('AFS (Average Fibonacci Stoch_d)')
ax2.set_ylabel('Value (0-100)')
ax2.set_ylim(0, 100)
ax2.legend(loc='upper left')
ax2.grid(True, alpha=0.3)

# 3. Stoch_d (Short-term vs Long-term)
ax3.plot(df_period.index, df_period['FIB_5_stoch_d'], label='Stoch_d (8 - Short)', color='orange')
ax3.plot(df_period.index, df_period['FIB_11_stoch_d'], label='Stoch_d (144 - Long)', color='blue')
ax3.axhline(80, color='red', linestyle='--', alpha=0.5)
ax3.axhline(20, color='red', linestyle='--', alpha=0.5)
ax3.set_title('Stoch_d Comparison (Short vs Long)')
ax3.set_ylabel('Value (0-100)')
ax3.set_ylim(0, 100)
ax3.legend(loc='upper left')
ax3.grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/observation_graph.png', dpi=150)
print("Saved observation_graph.png")
