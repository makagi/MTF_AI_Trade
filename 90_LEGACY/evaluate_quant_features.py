import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
import os
from src.data_loader import load_1h_data
from src.features import calculate_fib_features

print("Loading data...")
df = load_1h_data(include_holdout=True)

print("Calculating base Fibonacci features up to index 16...")
df = calculate_fib_features(df, max_fib_index=16)

# 1. Calculate Features
for k in range(1, 17):
    cols = [f'FIB_{i}_stoch_d' for i in range(k, 17)]
    df[f'A_{k}'] = df[cols].mean(axis=1)

beta = 5.0
df['Cascade_Score'] = 0.0
for k in range(1, 16):
    delta_k = df[f'A_{k}'] - df[f'A_{k+1}']
    w_k = k / 15.0 
    df['Cascade_Score'] += w_k * np.tanh(delta_k / beta)

W_k = 233
epsilon = 1.0
rolling_min = df['A_12'].rolling(window=W_k, min_periods=W_k//4).min()
rolling_max = df['A_12'].rolling(window=W_k, min_periods=W_k//4).max()
denominator = np.maximum(rolling_max - rolling_min, epsilon)
df['Proximity_11'] = (df['A_11'] - rolling_min) / denominator

m = 4
S_s = df['FIB_5_SMA']
S_l = df['FIB_11_SMA']
v_s = (S_s - S_s.shift(m)) / S_s.shift(m)
v_l = (S_l - S_l.shift(m)) / S_l.shift(m)
d = (S_s - S_l) / S_l
sigma_d = d.rolling(window=144, min_periods=144//4).std()
sigma_d = sigma_d.fillna(method='bfill').replace(0, 0.001)
df['Sync_Score'] = np.sign(v_s) * np.sign(v_l) * np.exp(- (d**2) / (2 * sigma_d**2))

# Forward Returns for objective evaluation
df['Fwd_Ret_24h'] = df['close'].shift(-24) / df['close'] - 1
df['Fwd_Ret_48h'] = df['close'].shift(-48) / df['close'] - 1

df_clean = df.dropna(subset=['Cascade_Score', 'Proximity_11', 'Sync_Score', 'Fwd_Ret_24h', 'Fwd_Ret_48h'])

# 2. Objective Evaluation (Information Coefficient - IC) by Year
years = ['2021', '2022', '2023', '2024']
results = []
for y in years:
    df_y = df_clean.loc[f'{y}-01-01':f'{y}-12-31']
    if len(df_y) < 100: continue
    
    # Calculate Spearman Rank Correlation (IC)
    # Proximity is 0 (bottom) to 1 (top). So we expect NEGATIVE correlation with forward returns.
    ic_cascade, _ = spearmanr(df_y['Cascade_Score'], df_y['Fwd_Ret_24h'])
    ic_prox, _ = spearmanr(df_y['Proximity_11'], df_y['Fwd_Ret_24h'])
    ic_sync, _ = spearmanr(df_y['Sync_Score'], df_y['Fwd_Ret_24h'])
    
    results.append({'Year': y, 'Regime': 'Bull' if y=='2021' else 'Bear' if y=='2022' else 'Range',
                    'IC_Cascade_24h': ic_cascade, 'IC_Proximity_24h': ic_prox, 'IC_Sync_24h': ic_sync})

res_df = pd.DataFrame(results)
print("\n--- Objective Evaluation: Information Coefficient (IC) by Regime ---")
print(res_df.to_string(index=False))

# 3. Plotting Different Regimes
periods = [
    ('2021-10-01', '2021-11-30', 'Bull Market (Late 2021)'),
    ('2022-05-01', '2022-06-30', 'Bear Market (Mid 2022)'),
    ('2023-06-01', '2023-07-31', 'Range Market (Mid 2023)')
]

fig, axes = plt.subplots(3, 3, figsize=(20, 15), sharex=False)

for i, (start, end, title) in enumerate(periods):
    d_sub = df_clean.loc[start:end]
    
    # Price vs Proximity
    ax1 = axes[i, 0]
    ax1.plot(d_sub.index, d_sub['close'], color='black')
    ax1.set_title(f'{title}\nPrice')
    ax1.grid(True, alpha=0.3)
    
    ax2 = ax1.twinx()
    ax2.plot(d_sub.index, d_sub['Proximity_11'], color='green', alpha=0.5)
    ax2.set_ylabel('Proximity', color='green')
    
    # Cascade
    ax3 = axes[i, 1]
    ax3.plot(d_sub.index, d_sub['Cascade_Score'], color='purple')
    ax3.axhline(0, color='gray', linestyle='--')
    ax3.set_title('Cascade Score')
    ax3.grid(True, alpha=0.3)
    
    # Sync
    ax4 = axes[i, 2]
    ax4.plot(d_sub.index, d_sub['Sync_Score'], color='orange')
    ax4.axhline(0, color='gray', linestyle='--')
    ax4.set_title('Sync Score')
    ax4.grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs("results", exist_ok=True)
plt.savefig('results/regime_quant_evaluation.png', dpi=150)
print("\nSaved regime_quant_evaluation.png")
