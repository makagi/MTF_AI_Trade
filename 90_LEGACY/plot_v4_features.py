import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from src.data_loader import load_1m_data
from src.features import calculate_fib_features

print("Loading 1m data (202401)...")
# Loading a volatile period, e.g. early Jan 2024
df_1 = load_1m_data("202312")
df_2 = load_1m_data("202401")
df = pd.concat([df_1, df_2])
df = df[~df.index.duplicated(keep='last')]
df.sort_index(inplace=True)

print("Calculating base features...")
df = calculate_fib_features(df, max_fib_index=16)

for k in range(1, 17):
    cols = [f'FIB_{i}_stoch_d' for i in range(k, 17)]
    df[f'A_{k}'] = df[cols].mean(axis=1)

# Calculate ATR (approximate for 1m using 14 periods)
high_low = df['high'] - df['low']
high_close = np.abs(df['high'] - df['close'].shift())
low_close = np.abs(df['low'] - df['close'].shift())
tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df['ATR'] = tr.rolling(window=14, min_periods=1).mean().replace(0, 0.001)

print("Calculating v4.0 Robust Features...")
# 1. Hierarchical Sync Score (Short vs Long)
w = 60 # Momentum window (e.g., 60 minutes)
alpha = 0.1 # scaling factor for tanh

sync_short = pd.Series(0.0, index=df.index)
for k in range(1, 6):
    sync_short += np.tanh(alpha * (df[f'A_{k}'] - df[f'A_{k}'].shift(w)))
df['Sync_Short'] = sync_short / 5.0

sync_long = pd.Series(0.0, index=df.index)
for k in range(14, 17):
    sync_long += np.tanh(alpha * (df[f'A_{k}'] - df[f'A_{k}'].shift(w)))
df['Sync_Long'] = sync_long / 3.0

# 2. Macro Gravity Defiance
df['Gravity_Defy'] = df['Sync_Short'] - df['Sync_Long']

# 3. ATR Normalized Fan-out Peeling Velocity
m = 30 # Momentum window for peeling (30 minutes)
d_10 = (df['FIB_10_SMA'] - df['FIB_11_SMA']) / df['ATR']
d_11 = (df['FIB_11_SMA'] - df['FIB_12_SMA']) / df['ATR']
df['V_fan'] = (d_10 - d_10.shift(m)) + (d_11 - d_11.shift(m))

print("Plotting...")
# Focus on the Jan 10-11 period we looked at before
df_period = df.loc['2024-01-10':'2024-01-11'].copy()

fig, axes = plt.subplots(4, 1, figsize=(16, 20), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1, 1]})

# --- 1. Price and Adjacent SMAs ---
axes[0].plot(df_period.index, df_period['close'], color='black', label='Close (1m)', linewidth=1, alpha=0.5)
axes[0].plot(df_period.index, df_period['FIB_10_SMA'], color='lightcoral', label='SMA 10 (89)')
axes[0].plot(df_period.index, df_period['FIB_11_SMA'], color='red', label='SMA 11 (144)')
axes[0].plot(df_period.index, df_period['FIB_12_SMA'], color='darkred', label='SMA 12 (233)')
axes[0].set_title('Price & SMAs (Observing the Fan-out/Peeling)')
axes[0].legend(loc='upper left', ncol=4)
axes[0].grid(True, alpha=0.3)

# --- 2. Hierarchical Sync Score ---
axes[1].plot(df_period.index, df_period['Sync_Short'], color='dodgerblue', label='Sync Short (1-5)', linewidth=1.5)
axes[1].plot(df_period.index, df_period['Sync_Long'], color='navy', label='Sync Long (14-16)', linewidth=2.5)
axes[1].axhline(0, color='gray', linestyle='--', alpha=0.5)
axes[1].axhline(1, color='red', linestyle=':', alpha=0.3)
axes[1].axhline(-1, color='green', linestyle=':', alpha=0.3)
axes[1].set_title('Hierarchical Sync Score (Short vs Long Momentum)')
axes[1].legend(loc='upper left', ncol=2)
axes[1].grid(True, alpha=0.3)

# --- 3. Macro Gravity Defiance ---
# Fill area based on whether it's positive (defying up) or negative (defying down)
axes[2].plot(df_period.index, df_period['Gravity_Defy'], color='purple', label='Gravity Defiance (Short - Long)', linewidth=2)
axes[2].fill_between(df_period.index, df_period['Gravity_Defy'], 0, where=(df_period['Gravity_Defy'] > 0), color='red', alpha=0.3, label='Defying Downward Gravity (Fake Rally)')
axes[2].fill_between(df_period.index, df_period['Gravity_Defy'], 0, where=(df_period['Gravity_Defy'] < 0), color='green', alpha=0.3, label='Defying Upward Gravity (Fake Drop)')
axes[2].axhline(0, color='gray', linestyle='--', alpha=0.5)
axes[2].set_title('Macro Gravity Defiance (Mapping to [-2, +2])')
axes[2].legend(loc='upper left', ncol=3)
axes[2].grid(True, alpha=0.3)

# --- 4. Fan-out Peeling Velocity ---
axes[3].plot(df_period.index, df_period['V_fan'], color='darkorange', label='Fan-out Velocity (V_fan)', linewidth=2)
axes[3].axhline(0, color='gray', linestyle='--', alpha=0.5)
axes[3].set_title('ATR Normalized Peeling Velocity (SMA expansion rate)')
axes[3].legend(loc='upper left')
axes[3].grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/plot_v4_features.png', dpi=150)
print("Saved plot_v4_features.png")
