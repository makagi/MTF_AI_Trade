import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
from src.data_loader import load_1h_data
from src.features import calculate_fib_features

print("Loading data...")
df = load_1h_data(include_holdout=True)

print("Calculating base Fibonacci features up to index 16...")
df = calculate_fib_features(df, max_fib_index=16)

# We need to calculate individual AFS_k (which is just FIB_k_stoch_d for this specific cascade calculation)
# Wait, the user's AFS definition was AFS(k, 16). 
# Let's calculate A_k(t) = AFS(k, 16) for k=1 to 16
for k in range(1, 17):
    cols = [f'FIB_{i}_stoch_d' for i in range(k, 17)]
    df[f'A_{k}'] = df[cols].mean(axis=1)

print("Calculating Feature 1: Cascade Score C(t)...")
beta = 5.0
df['Cascade_Score'] = 0.0
for k in range(1, 16):
    delta_k = df[f'A_{k}'] - df[f'A_{k+1}']
    # Weight increases for longer term (macro) crossings
    w_k = k / 15.0 
    df['Cascade_Score'] += w_k * np.tanh(delta_k / beta)

print("Calculating Feature 2: Proximity Score P_k(t) for k=11...")
# k=11, k+1=12. Window W_k = FIB_12 = 233
W_k = 233
epsilon = 1.0 # Minimum range for 0-100 oscillator
rolling_min = df['A_12'].rolling(window=W_k, min_periods=W_k//4).min()
rolling_max = df['A_12'].rolling(window=W_k, min_periods=W_k//4).max()
denominator = np.maximum(rolling_max - rolling_min, epsilon)
df['Proximity_11'] = (df['A_11'] - rolling_min) / denominator

print("Calculating Feature 3: Synchronization Score Sync(t)...")
m = 4 # 4-hour momentum
S_s = df['FIB_5_SMA']  # Short: 8
S_l = df['FIB_11_SMA'] # Long: 144

v_s = (S_s - S_s.shift(m)) / S_s.shift(m)
v_l = (S_l - S_l.shift(m)) / S_l.shift(m)
d = (S_s - S_l) / S_l

# Historical standard deviation of distance (over 144 periods)
sigma_d = d.rolling(window=144, min_periods=144//4).std()
sigma_d = sigma_d.fillna(method='bfill').replace(0, 0.001)

sync_score = np.sign(v_s) * np.sign(v_l) * np.exp(- (d**2) / (2 * sigma_d**2))
df['Sync_Score'] = sync_score

# --- Plotting ---
df_period = df.loc['2024-01-01':'2024-03-01'].copy()

fig, axes = plt.subplots(4, 1, figsize=(16, 18), sharex=True, gridspec_kw={'height_ratios': [2, 1, 1, 1]})

# 1. Price
axes[0].plot(df_period.index, df_period['close'], color='black', label='Close Price')
axes[0].plot(df_period.index, df_period['FIB_11_SMA'], color='blue', label='Long SMA (144)', alpha=0.6)
axes[0].plot(df_period.index, df_period['FIB_5_SMA'], color='red', label='Short SMA (8)', alpha=0.6)
axes[0].set_title('Price & SMAs')
axes[0].legend(loc='upper left')
axes[0].grid(True, alpha=0.3)

# 2. Cascade Score
axes[1].plot(df_period.index, df_period['Cascade_Score'], color='purple', linewidth=2)
axes[1].axhline(0, color='black', linestyle='--', alpha=0.5)
axes[1].set_title('Feature 1: Cascade Score (Momentum Wave Propagation)')
axes[1].legend(['Cascade Score (Higher = Upward Momentum)'], loc='upper left')
axes[1].grid(True, alpha=0.3)

# 3. Proximity Score (Memory / Extremum)
axes[2].plot(df_period.index, df_period['Proximity_11'], color='green', linewidth=2)
axes[2].axhline(1.0, color='red', linestyle='--', alpha=0.3)
axes[2].axhline(0.0, color='blue', linestyle='--', alpha=0.3)
axes[2].set_title('Feature 2: Proximity Score P_11 (Approaching Macro Extremes)')
axes[2].legend(['Proximity Score (0 = Macro Support, 1 = Macro Resistance)'], loc='upper left')
axes[2].grid(True, alpha=0.3)

# 4. Synchronization Score (Alignment)
axes[3].plot(df_period.index, df_period['Sync_Score'], color='darkorange', linewidth=2)
axes[3].axhline(0, color='black', linestyle='--', alpha=0.5)
axes[3].set_title('Feature 3: Synchronization Score (Perfect Order Initiation)')
axes[3].legend(['Sync Score (+1 = Upward Alignment, -1 = Downward Alignment)'], loc='upper left')
axes[3].grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/quant_features_plot.png', dpi=150)
print("Saved quant_features_plot.png")
