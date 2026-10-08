import pandas as pd
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns
import lightgbm as lgb
import os

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from train_lightgbm import build_v5_0_features

def get_binary_barrier_labels(df: pd.DataFrame, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long') -> pd.DataFrame:
    df_labels = pd.DataFrame(index=df.index)
    returns = np.zeros(len(df))
    hit_periods = np.zeros(len(df))
    
    close_vals = df['close'].values
    high_vals = df['high'].values
    low_vals = df['low'].values
    atr_vals = df['ATR_14'].values
    
    for i in tqdm(range(len(df)), desc=f'Labeling {direction}'):
        if i + 1 >= len(df):
            break
            
        c = close_vals[i]
        atr = atr_vals[i]
        
        if pd.isna(atr) or atr == 0:
            continue
            
        if direction == 'long':
            tp = c + atr * pt_sl_ratio[0]
            sl = c - atr * pt_sl_ratio[1]
        else:
            tp = c - atr * pt_sl_ratio[0]
            sl = c + atr * pt_sl_ratio[1]
            
        future_highs = high_vals[i+1 : i+1+time_barrier]
        future_lows = low_vals[i+1 : i+1+time_barrier]
        
        hit_val = 0
        hit_period = 0
        
        for j in range(len(future_highs)):
            if direction == 'long':
                if future_lows[j] <= sl:
                    hit_val = -1
                    hit_period = j + 1
                    break
                elif future_highs[j] >= tp:
                    hit_val = 1
                    hit_period = j + 1
                    break
            else:
                if future_highs[j] >= sl:
                    hit_val = -1
                    hit_period = j + 1
                    break
                elif future_lows[j] <= tp:
                    hit_val = 1
                    hit_period = j + 1
                    break
                    
        returns[i] = hit_val
        hit_periods[i] = hit_period
        
    df_labels['tb_return'] = returns
    df_labels['hit_period'] = hit_periods
    return df_labels

def extract_oracle_pivots(df, labels, direction='long'):
    df['hit_val'] = labels['tb_return']
    
    zones = []
    current_zone = []
    for idx, row in df.iterrows():
        if row['hit_val'] == 1:
            current_zone.append(idx)
        else:
            if len(current_zone) > 0:
                zones.append(current_zone)
                current_zone = []
    if len(current_zone) > 0:
        zones.append(current_zone)
        
    oracle_pivots = []
    for zone in zones:
        zone_df = df.loc[zone]
        if direction == 'long':
            pivot_idx = zone_df['low'].idxmin()
        else:
            pivot_idx = zone_df['high'].idxmax()
        oracle_pivots.append(pivot_idx)
        
    return oracle_pivots

def main():
    print("Loading 1h data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, 19)
    df = calculate_diverse_features(df)
    df, feature_cols = build_v5_0_features(df)
    
    df_2025 = df[df.index >= '2025-01-01'].copy()
    
    print("Labeling true success for LONG and SHORT...")
    labels_L = get_binary_barrier_labels(df_2025, pt_sl_ratio=[2.5, 1.0], direction='long')
    labels_S = get_binary_barrier_labels(df_2025, pt_sl_ratio=[1.5, 1.0], direction='short')
    
    print("Extracting Oracle Pivots...")
    oracle_L = extract_oracle_pivots(df_2025, labels_L, direction='long')
    oracle_S = extract_oracle_pivots(df_2025, labels_S, direction='short')
    
    print(f"Found {len(oracle_L)} Oracle Longs and {len(oracle_S)} Oracle Shorts in 2025.")
    
    df_2025['is_oracle_L'] = df_2025.index.isin(oracle_L)
    df_2025['is_oracle_S'] = df_2025.index.isin(oracle_S)
    
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    model_short = lgb.Booster(model_file='models/lgbm_v5_0_short.txt')
    df_2025['pred_L'] = model_long.predict(df_2025[feature_cols])
    df_2025['pred_S'] = model_short.predict(df_2025[feature_cols])
    
    print("\n--- Oracle Gap Analysis (LONG) ---")
    oracle_df_L = df_2025[df_2025['is_oracle_L']].copy()
    
    caught_L = oracle_df_L[oracle_df_L['pred_L'] >= 0.25]
    missed_L = oracle_df_L[oracle_df_L['pred_L'] < 0.25]
    print(f"Total Oracle Longs: {len(oracle_df_L)}")
    print(f"Caught by v5.0 (pred >= 0.25): {len(caught_L)}")
    print(f"Missed by v5.0 (pred < 0.25): {len(missed_L)}")
    
    print("\n--- Oracle Gap Analysis (SHORT) ---")
    oracle_df_S = df_2025[df_2025['is_oracle_S']].copy()
    caught_S = oracle_df_S[oracle_df_S['pred_S'] >= 0.25]
    missed_S = oracle_df_S[oracle_df_S['pred_S'] < 0.25]
    print(f"Total Oracle Shorts: {len(oracle_df_S)}")
    print(f"Caught by v5.0 (pred >= 0.25): {len(caught_S)}")
    print(f"Missed by v5.0 (pred < 0.25): {len(missed_S)}")
    
    plt.figure(figsize=(12, 6))
    sns.histplot(data=oracle_df_L, x='F_Floor_Proximity', bins=50, color='blue', alpha=0.5, label='Missed Oracles')
    sns.histplot(data=caught_L, x='F_Floor_Proximity', bins=50, color='red', alpha=0.8, label='Caught Oracles')
    plt.title("Distribution of F_Floor_Proximity for Oracle Longs")
    plt.legend()
    plt.savefig("oracle_floor_proximity_long.png")
    
    plt.figure(figsize=(12, 6))
    sns.histplot(data=oracle_df_S, x='F_Ceiling_Proximity', bins=50, color='blue', alpha=0.5, label='Missed Oracles')
    sns.histplot(data=caught_S, x='F_Ceiling_Proximity', bins=50, color='red', alpha=0.8, label='Caught Oracles')
    plt.title("Distribution of F_Ceiling_Proximity for Oracle Shorts")
    plt.legend()
    plt.savefig("oracle_ceiling_proximity_short.png")
    
    print("\nAnalysis complete. Visualizations saved.")
    
if __name__ == "__main__":
    main()
