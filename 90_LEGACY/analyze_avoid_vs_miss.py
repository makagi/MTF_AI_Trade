import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import ks_2samp

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START
from src.labels import get_binary_barrier_labels

def get_analysis_features(df):
    fib_ks = [6, 7, 8, 9, 10, 11, 12]
    epsilon = 1e-8
    bb_lowers = []
    
    for k in fib_ks:
        period = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377][k]
        std = df['close'].rolling(period, min_periods=1).std().bfill()
        sma = df[f'FIB_{k}_SMA']
        lower = sma - 2.0 * std
        upper = sma + 2.0 * std
        df[f'FIB_{k}_BB_lower'] = lower
        df[f'FIB_{k}_BB_upper'] = upper
        bb_lowers.append(lower)
        
    bb_lower_min = pd.concat(bb_lowers, axis=1).min(axis=1)
    bb_lower_max = pd.concat(bb_lowers, axis=1).max(axis=1)
    df['F_Floor_Proximity'] = (df['close'] - bb_lower_min) / (bb_lower_max - bb_lower_min + epsilon)
    
    wave_L = np.zeros(len(df))
    weights = [0.40, 0.25, 0.15, 0.10, 0.05, 0.03, 0.02] 
    for i, k in enumerate(fib_ks):
        mom_L = df[f'FIB_{k}_BB_lower'].diff(1)
        z_L = mom_L / (mom_L.rolling(100).std() + epsilon)
        wave_L += z_L.clip(-3, 3) * weights[i]
    df['F_Wave_Propagation_L'] = wave_L
    
    df['recent_floor'] = df['F_Floor_Proximity'].rolling(24).min() < 0.1
    df['macro_despair'] = df['FIB_10_BB_lower'].diff(1) < 0
    micro_vel = df['FIB_6_BB_lower'].diff(1)
    df['micro_reversal'] = (micro_vel > 0) & (micro_vel.shift(1) <= 0)
    
    df['burnout_safe_L'] = df['F_Floor_Proximity'] < 0.50
    df['wave_despair_L'] = df['F_Wave_Propagation_L'] < -0.50
    df['F_Trigger_v4_L'] = (df['recent_floor'] & df['macro_despair'] & df['micro_reversal'] & df['burnout_safe_L'] & df['wave_despair_L']).astype(int)
    
    # 1. Wick Ratio
    df['Wick_Ratio'] = (np.minimum(df['open'], df['close']) - df['low']) / (df['high'] - df['low'] + epsilon)
    
    # 2. BB Thickness Velocity
    df['BB_Thickness'] = bb_lower_max - bb_lower_min
    df['Thickness_Vel'] = df['BB_Thickness'].diff(1)
    
    # 3. Wave Acceleration
    df['Wave_Accel'] = df['F_Wave_Propagation_L'].diff(1)
    
    return df

def analyze():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    df = get_analysis_features(df)
    
    tb_long = get_binary_barrier_labels(df, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    df['label_long'] = tb_long['label']
    
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    
    # Set A: Missed Opportunities (FN) - We wanted to trade this!
    set_a = df_holdout[(df_holdout['recent_floor'] == True) & 
                       (df_holdout['F_Trigger_v4_L'] == 0) & 
                       (df_holdout['label_long'] == 1)]
                       
    # Set B: Correctly Avoided (TN) - We are glad we avoided this!
    set_b = df_holdout[(df_holdout['recent_floor'] == True) & 
                       (df_holdout['F_Trigger_v4_L'] == 0) & 
                       (df_holdout['label_long'] == 0)]
    
    print(f"Set A (Missed Wins): {len(set_a)}")
    print(f"Set B (Avoided Losses): {len(set_b)}")
    
    features_to_test = df.select_dtypes(include=[np.number]).columns.tolist()
    # Remove obvious leaks or targets
    features_to_test = [f for f in features_to_test if 'tb_' not in f and 'label' not in f and 'hit_period' not in f and 'Trigger' not in f and 'blocked_' not in f and f != 'close' and f != 'open' and f != 'high' and f != 'low' and f != 'timestamp']
    
    os.makedirs('results', exist_ok=True)
    
    best_features = []
    
    for feat in features_to_test:
        a_vals = set_a[feat].dropna()
        b_vals = set_b[feat].dropna()
        if len(a_vals) < 10 or len(b_vals) < 10: continue
        
        stat, pval = ks_2samp(a_vals, b_vals)
        if pval < 0.05:
            print(f"Feature: {feat}, KS: {stat:.4f}, p-val: {pval:.4e}")
            best_features.append((pval, feat))
        
    best_features.sort()
    
    if len(best_features) >= 2:
        f1 = best_features[0][1]
        f2 = best_features[1][1]
        print(f"\nTop 2 Features: {f1}, {f2}")
        plt.figure(figsize=(12, 8))
        plt.scatter(set_b[f1], set_b[f2], color='red', alpha=0.3, label='Set B (Avoided Loss)', marker='x')
        plt.scatter(set_a[f1], set_a[f2], color='blue', alpha=0.5, label='Set A (Missed Win)', marker='o')
        plt.xlabel(f1)
        plt.ylabel(f2)
        plt.title(f'Edge Visualization: {f1} vs {f2}')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig('results/tn_vs_fn_scatter.png')
        plt.close()
    
    print("Done")

if __name__ == "__main__":
    analyze()
