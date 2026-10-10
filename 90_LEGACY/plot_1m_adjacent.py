import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from src.data_loader import load_1m_data
from src.features import calculate_fib_features

print("Loading 1m data (202305 and 202306)...")
# Load two months to ensure rolling windows are filled
df_1 = load_1m_data("202305")
df_2 = load_1m_data("202306")
df = pd.concat([df_1, df_2])
df = df[~df.index.duplicated(keep='last')]
df.sort_index(inplace=True)

print("Calculating base features on 1m data (max_fib=16)...")
df = calculate_fib_features(df, max_fib_index=16)

# Calculate A_k (AFS)
for k in range(1, 17):
    cols = [f'FIB_{i}_stoch_d' for i in range(k, 17)]
    df[f'A_{k}'] = df[cols].mean(axis=1)

# Pick a highly volatile 3-day period in June 2023 (e.g., June 14 to June 16, SEC news era)
df_period = df.loc['2023-06-14':'2023-06-16'].copy()

fig, axes = plt.subplots(4, 1, figsize=(16, 20), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1, 1]})

# --- 1. Adjacent SMAs (Micro wave propagation) ---
axes[0].plot(df_period.index, df_period['close'], color='black', label='Close (1m)', linewidth=1, alpha=0.5)

# Fast Adjacent: 5,6,7 (8, 13, 21 mins) -> Too fast to see clearly, let's use Mid Adjacent
# Mid Adjacent: 10,11,12 (89, 144, 233 mins)
axes[0].plot(df_period.index, df_period['FIB_10_SMA'], color='lightcoral', label='SMA 10 (89)')
axes[0].plot(df_period.index, df_period['FIB_11_SMA'], color='red', label='SMA 11 (144)')
axes[0].plot(df_period.index, df_period['FIB_12_SMA'], color='darkred', label='SMA 12 (233)')

axes[0].set_title('Price & Adjacent SMAs (10, 11, 12) - Observing the "Peeling" Effect')
axes[0].legend(loc='upper left', ncol=4)
axes[0].grid(True, alpha=0.3)

# --- 2. Adjacent Stoch_d (10, 11, 12) ---
axes[1].plot(df_period.index, df_period['FIB_10_stoch_d'], color='lightgreen', label='Stoch_d 10 (89)')
axes[1].plot(df_period.index, df_period['FIB_11_stoch_d'], color='forestgreen', label='Stoch_d 11 (144)')
axes[1].plot(df_period.index, df_period['FIB_12_stoch_d'], color='darkgreen', label='Stoch_d 12 (233)')

axes[1].axhline(80, color='gray', linestyle='--', alpha=0.5)
axes[1].axhline(20, color='gray', linestyle='--', alpha=0.5)
axes[1].set_title('Adjacent Stoch_d (10, 11, 12) - Observing the Momentum Cascade')
axes[1].legend(loc='upper left', ncol=3)
axes[1].grid(True, alpha=0.3)

# --- 3. Adjacent AFS (10, 11, 12) ---
axes[2].plot(df_period.index, df_period['A_10'], color='cornflowerblue', label='AFS 10')
axes[2].plot(df_period.index, df_period['A_11'], color='blue', label='AFS 11')
axes[2].plot(df_period.index, df_period['A_12'], color='navy', label='AFS 12')

axes[2].axhline(80, color='gray', linestyle='--', alpha=0.5)
axes[2].axhline(20, color='gray', linestyle='--', alpha=0.5)
axes[2].set_title('Adjacent AFS (10, 11, 12) - Macro Smooth Convergence')
axes[2].legend(loc='upper left', ncol=3)
axes[2].grid(True, alpha=0.3)

# --- 4. Deep Macro Adjacent AFS (14, 15, 16) ---
axes[3].plot(df_period.index, df_period['A_14'], color='plum', label='AFS 14 (610)')
axes[3].plot(df_period.index, df_period['A_15'], color='purple', label='AFS 15 (987)')
axes[3].plot(df_period.index, df_period['A_16'], color='indigo', label='AFS 16 (1597)')

axes[3].axhline(80, color='gray', linestyle='--', alpha=0.5)
axes[3].axhline(20, color='gray', linestyle='--', alpha=0.5)
axes[3].set_title('Deep Macro Adjacent AFS (14, 15, 16) - Absolute Structural Gravity')
axes[3].legend(loc='upper left', ncol=3)
axes[3].grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/plot_1m_adjacent.png', dpi=150)
print("Saved plot_1m_adjacent.png")
