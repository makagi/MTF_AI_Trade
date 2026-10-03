import pandas as pd
import numpy as np
from scipy.stats import spearmanr
import os
from src.data_loader import load_1h_data
from src.features import calculate_fib_features

print("Loading data and calculating base features...")
df = load_1h_data(include_holdout=True)
df = calculate_fib_features(df, max_fib_index=16)

# Need ATR and BB Width for v3 features
high_low = df['high'] - df['low']
high_close = np.abs(df['high'] - df['close'].shift())
low_close = np.abs(df['low'] - df['close'].shift())
tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df['ATR_14'] = tr.rolling(window=14, min_periods=1).mean()
# Normalize ATR to percentage of price for AFS memory decay
df['ATR_pct'] = df['ATR_14'] / df['close'] * 100

df['SMA_20'] = df['close'].rolling(20).mean()
df['STD_20'] = df['close'].rolling(20).std()
df['BB_Width'] = (df['STD_20'] * 4) / df['close'] * 100 # percentage width

print("Calculating v3.0 Features...")
# 1. A_k cache
for k in range(1, 17):
    cols = [f'FIB_{i}_stoch_d' for i in range(k, 17)]
    df[f'A_{k}'] = df[cols].mean(axis=1)

# 2. Gated Cascade
beta = 5.0
gamma = 1.0
cascade_raw = pd.Series(0.0, index=df.index)
for k in range(1, 16):
    delta_k = df[f'A_{k}'] - df[f'A_{k+1}']
    w_k = k / 15.0 
    cascade_raw += w_k * np.tanh(delta_k / beta)

# Gating term: exp(- BB_Width / (gamma * ATR_pct))
# Note: BB_Width and ATR_pct are both in percentages
gating_term = np.exp(- df['BB_Width'] / (gamma * df['ATR_pct'].replace(0, 0.001)))
df['Cascade_Gated'] = cascade_raw * gating_term

# 3. Exponential Decay Memory (Proximity)
delta_decay = 0.5 # hyperparameter: how much memory decays relative to ATR%
m_max = np.zeros(len(df))
m_min = np.zeros(len(df))
m_max[0] = df['A_12'].iloc[0] if not np.isnan(df['A_12'].iloc[0]) else 100.0
m_min[0] = df['A_12'].iloc[0] if not np.isnan(df['A_12'].iloc[0]) else 0.0

a_12 = df['A_12'].values
atr_pct = df['ATR_pct'].fillna(0).values

for i in range(1, len(df)):
    if np.isnan(a_12[i]):
        m_max[i] = m_max[i-1]
        m_min[i] = m_min[i-1]
        continue
        
    decay_amount = delta_decay * atr_pct[i]
    m_max[i] = max(a_12[i], m_max[i-1] - decay_amount)
    m_min[i] = min(a_12[i], m_min[i-1] + decay_amount)

df['M_max'] = m_max
df['M_min'] = m_min
epsilon = 1.0
df['Proximity_Decay'] = (df['A_11'] - df['M_min']) / np.maximum(df['M_max'] - df['M_min'], epsilon)

# 4. Hierarchical Elasticity Force
fibs = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597]
elastic_force = pd.Series(0.0, index=df.index)
for k in range(1, 16):
    sma_k_minus_1 = df[f'FIB_{k}_SMA'] if k > 1 else df['close'] # FIB_1_SMA is just close (period 1)
    sma_k = df[f'FIB_{k+1}_SMA']
    diff_pct = (sma_k_minus_1 - sma_k) / sma_k * 100
    # tanh(diff_pct / ATR_pct)
    elastic_force += np.log(fibs[k]) * np.tanh(diff_pct / df['ATR_pct'].replace(0, 0.001))
    
df['Elasticity_Force'] = elastic_force
# Reversal signal: 1st derivative of Elasticity Force
df['Elasticity_Signal'] = elastic_force.diff()

# --- Evaluation ---
df['Fwd_Ret_24h'] = df['close'].shift(-24) / df['close'] - 1
df_clean = df.dropna(subset=['Cascade_Gated', 'Proximity_Decay', 'Elasticity_Signal', 'Fwd_Ret_24h'])

print("\n--- v3.0 Feature Evaluation (Information Coefficient) ---")
years = ['2021', '2022', '2023']
results = []
for y in years:
    df_y = df_clean.loc[f'{y}-01-01':f'{y}-12-31']
    if len(df_y) < 100: continue
    
    ic_cas_gated, _ = spearmanr(df_y['Cascade_Gated'], df_y['Fwd_Ret_24h'])
    ic_prox_decay, _ = spearmanr(df_y['Proximity_Decay'], df_y['Fwd_Ret_24h'])
    ic_elas_sig, _ = spearmanr(df_y['Elasticity_Signal'], df_y['Fwd_Ret_24h'])
    
    results.append({'Year': y, 
                    'Regime': 'Bull' if y=='2021' else 'Bear' if y=='2022' else 'Range',
                    'IC_Cascade_Gated': ic_cas_gated, 
                    'IC_Proximity_Decay': ic_prox_decay, 
                    'IC_Elasticity_Signal': ic_elas_sig})

res_df = pd.DataFrame(results)
print(res_df.to_string(index=False))
