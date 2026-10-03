import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from src.data_loader import load_1m_data
from src.features import calculate_fib_features, calculate_stoch_k

print("Loading 1m data (202312 and 202401)...")
# Load two months to ensure rolling windows for FIB(up to 21 = 17711 mins) are filled
df_1 = load_1m_data("202312")
df_2 = load_1m_data("202401")
df = pd.concat([df_1, df_2])
df = df[~df.index.duplicated(keep='last')]
df.sort_index(inplace=True)

print("Calculating base features on 1m data (max_fib=16 for speed/clarity)...")
# Using 16 (1597 mins = ~26 hours) to 18 (4181 mins = ~3 days)
# Let's use max_fib_index = 18 for 1m data to see short/mid macro
df = calculate_fib_features(df, max_fib_index=18)

# Calculate standard BB (20 period of something like FIB_11=144 or standard 20 period on close)
# Let's use BB on FIB_11 (144 min) to see the structure, or just standard 20 period on close
df['SMA_20'] = df['close'].rolling(20).mean()
df['STD_20'] = df['close'].rolling(20).std()
df['BB_Upper'] = df['SMA_20'] + 2 * df['STD_20']
df['BB_Lower'] = df['SMA_20'] - 2 * df['STD_20']

# Calculate A_k (AFS)
for k in range(1, 19):
    cols = [f'FIB_{i}_stoch_d' for i in range(k, 19)]
    df[f'A_{k}'] = df[cols].mean(axis=1)

# Slice a 2-day period in Jan 2024 for deep observation
# e.g., Jan 10 to Jan 12 where there's usually some volatility (ETF approval time)
df_period = df.loc['2024-01-10':'2024-01-11'].copy()

# Set up the plot with 4 subplots
fig, axes = plt.subplots(4, 1, figsize=(16, 20), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1, 1]})

# --- 1. Price, BB, and SMA Perfect Order ---
axes[0].plot(df_period.index, df_period['close'], color='black', label='Close (1m)', linewidth=1)
axes[0].plot(df_period.index, df_period['BB_Upper'], color='gray', linestyle='--', alpha=0.5)
axes[0].plot(df_period.index, df_period['BB_Lower'], color='gray', linestyle='--', alpha=0.5)
axes[0].fill_between(df_period.index, df_period['BB_Upper'], df_period['BB_Lower'], color='gray', alpha=0.1)

# Short-to-Mid SMAs to show Perfect Order (FIB 8(34), FIB 10(89), FIB 12(233))
axes[0].plot(df_period.index, df_period['FIB_8_SMA'], color='red', label='SMA(34)', linewidth=1.2)
axes[0].plot(df_period.index, df_period['FIB_10_SMA'], color='orange', label='SMA(89)', linewidth=1.2)
axes[0].plot(df_period.index, df_period['FIB_12_SMA'], color='blue', label='SMA(233)', linewidth=1.5)
axes[0].set_title('Price, Bollinger Bands, and SMA Perfect Order')
axes[0].legend(loc='upper left', ncol=4)
axes[0].grid(True, alpha=0.3)

# --- 2. Long-term Stoch_d (Readiness) ---
# FIB_14(610), FIB_16(1597), FIB_18(4181)
axes[1].plot(df_period.index, df_period['FIB_14_stoch_d'], color='purple', label='Stoch_d(610) ~10h', linewidth=1.5)
axes[1].plot(df_period.index, df_period['FIB_16_stoch_d'], color='brown', label='Stoch_d(1597) ~1 day', linewidth=2)
axes[1].plot(df_period.index, df_period['FIB_18_stoch_d'], color='black', label='Stoch_d(4181) ~3 days', linewidth=2.5)
axes[1].axhline(80, color='red', linestyle='--', alpha=0.5)
axes[1].axhline(20, color='green', linestyle='--', alpha=0.5)
axes[1].set_title('Long-Term Stoch_d (Is the macro context ready for reversal?)')
axes[1].legend(loc='upper left', ncol=3)
axes[1].grid(True, alpha=0.3)

# --- 3. AFS Order and Slope (Regression to Long-Term) ---
# A_5 (Short/Mid Macro), A_11 (Macro), A_15 (Deep Macro)
axes[2].plot(df_period.index, df_period['A_5'], color='dodgerblue', label='AFS(5) [Fast]', linewidth=1)
axes[2].plot(df_period.index, df_period['A_11'], color='blue', label='AFS(11) [Mid]', linewidth=2)
axes[2].plot(df_period.index, df_period['A_15'], color='darkblue', label='AFS(15) [Slow]', linewidth=3)
axes[2].set_title('AFS Order, Slope, and Reversion to Long-Term AFS')
axes[2].legend(loc='upper left', ncol=3)
axes[2].grid(True, alpha=0.3)

# --- 4. Short-Term Triggers (BB Touches + Short Stoch_d Cross) ---
axes[3].plot(df_period.index, df_period['FIB_5_stoch_d'], color='red', label='Short Stoch_d(8) Trigger', linewidth=1)
axes[3].plot(df_period.index, df_period['FIB_8_stoch_d'], color='darkorange', label='Short Stoch_d(34)', linewidth=1.5)
axes[3].axhline(80, color='red', linestyle='--', alpha=0.5)
axes[3].axhline(20, color='green', linestyle='--', alpha=0.5)
axes[3].set_title('Short-Term Triggers (Reacting to BB and Macro readiness)')
axes[3].legend(loc='upper left', ncol=2)
axes[3].grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/plot_1m_composite.png', dpi=150)
print("Saved plot_1m_composite.png")
