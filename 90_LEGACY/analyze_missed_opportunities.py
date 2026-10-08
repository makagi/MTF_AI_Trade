import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START
from src.labels import get_binary_barrier_labels

def get_v4_components(df):
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
    
    return df

def analyze():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    df = get_v4_components(df)
    
    tb_long = get_binary_barrier_labels(df, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    df['label_long'] = tb_long['label']
    
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    
    # 1. FN (Missed Opportunities) Analysis
    # Condition: label == 1 AND recent_floor == True
    # But F_Trigger_v4_10 was 0 because one of the other 4 conditions failed.
    df_fn = df_holdout[(df_holdout['label_long'] == 1) & (df_holdout['recent_floor'])].copy()
    
    # Calculate blocking conditions (inverse of v4.10 criteria)
    df_fn['blocked_by_macro'] = ~df_fn['macro_despair']
    df_fn['blocked_by_micro'] = ~df_fn['micro_reversal']
    df_fn['blocked_by_burnout'] = df_fn['F_Floor_Proximity'] >= 0.50
    df_fn['blocked_by_wave'] = df_fn['F_Wave_Propagation_L'] >= -0.50
    
    print(f"Total Missed Opportunities (Recent Floor & Label=1): {len(df_fn)}")
    
    block_counts = {
        'Macro Despair (<0)': df_fn['blocked_by_macro'].sum(),
        'Micro Reversal': df_fn['blocked_by_micro'].sum(),
        'Burnout (Prox >= 0.5)': df_fn['blocked_by_burnout'].sum(),
        'Wave (>= -0.5)': df_fn['blocked_by_wave'].sum()
    }
    
    plt.figure(figsize=(10, 6))
    plt.bar(block_counts.keys(), block_counts.values(), color=['salmon', 'lightblue', 'lightgreen', 'orange'])
    plt.title('Constraint Attribution: Why did we miss the trade?')
    plt.ylabel('Number of Missed Trades')
    os.makedirs('results', exist_ok=True)
    plt.savefig('results/missed_opportunities_blocks.png')
    print("Saved results/missed_opportunities_blocks.png")
    
    # 2. Scatter Plot (Proximity vs Wave)
    # Reconstruct v4.8 Trigger
    v48_trigger = (df_holdout['recent_floor'] & 
                   df_holdout['macro_despair'] & 
                   df_holdout['micro_reversal'] & 
                   (df_holdout['F_Floor_Proximity'] < 0.8))
                   
    # Reconstruct v4.10 Trigger
    v410_trigger = (v48_trigger & 
                    (df_holdout['F_Floor_Proximity'] < 0.50) & 
                    (df_holdout['F_Wave_Propagation_L'] < -0.50))
                    
    wins_v410 = df_holdout[v410_trigger & (df_holdout['label_long'] == 1)]
    losses_v48 = df_holdout[v48_trigger & (df_holdout['label_long'] == 0) & ~v410_trigger] # Losses that v4.10 filtered out
    
    plt.figure(figsize=(12, 8))
    plt.scatter(df_fn['F_Floor_Proximity'], df_fn['F_Wave_Propagation_L'], color='blue', alpha=0.3, label='Missed Opportunities (FN)', marker='.')
    plt.scatter(losses_v48['F_Floor_Proximity'], losses_v48['F_Wave_Propagation_L'], color='red', s=100, label='v4.8 Losses (Filtered by v4.10)', marker='x')
    plt.scatter(wins_v410['F_Floor_Proximity'], wins_v410['F_Wave_Propagation_L'], color='green', s=150, label='v4.10 Wins (Sniper Hits)', marker='*')
    
    plt.axvline(x=0.5, color='gray', linestyle='--', label='v4.10 Proximity Limit (0.5)')
    plt.axhline(y=-0.5, color='gray', linestyle=':', label='v4.10 Wave Limit (-0.5)')
    
    plt.xlabel('F_Floor_Proximity (Lower is closer to absolute bottom)')
    plt.ylabel('F_Wave_Propagation_L (Lower is deeper despair)')
    plt.title('Sweet Spot Analysis: Proximity vs Wave (LONG)')
    plt.legend()
    plt.grid(True, alpha=0.2)
    plt.savefig('results/sweet_spot_scatter.png')
    print("Saved results/sweet_spot_scatter.png")

if __name__ == "__main__":
    analyze()
