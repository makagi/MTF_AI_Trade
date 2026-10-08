import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import lightgbm as lgb

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START
from src.labels import get_binary_barrier_labels

def build_v4_5_triggers(df):
    atr = df['ATR_14'].replace(0, np.nan).fillna(method='bfill')
    std_144 = df['close'].rolling(144).std().replace(0, np.nan)
    sma_144 = df['FIB_10_SMA']
    bb_lower_144 = sma_144 - 2.0 * std_144
    
    flush_depth = np.maximum(0, (bb_lower_144 - df['low']) / atr)
    recent_flush = flush_depth.rolling(3).max().shift(1)
    returned_inside = (df['close'] > bb_lower_144).astype(int)
    exhaustion = (df['low'] > df['low'].shift(1)).astype(int)
    
    trigger = recent_flush * returned_inside * exhaustion
    return trigger, bb_lower_144

def build_v4_6_features(df):
    atr = df['ATR_14'].replace(0, np.nan).fillna(method='bfill')
    fib_ks = [6, 7, 8, 9, 10, 11, 12] # 21, 34, 55, 89, 144, 233, 377
    
    bb_lowers = []
    for k in fib_ks:
        period = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377][k]
        std = df['close'].rolling(period, min_periods=1).std().bfill()
        sma = df[f'FIB_{k}_SMA']
        bb_lower = sma - 2.0 * std
        bb_lowers.append(bb_lower)
        df[f'FIB_{k}_BB_lower'] = bb_lower
        
    bb_lower_max = pd.concat(bb_lowers, axis=1).max(axis=1)
    bb_lower_min = pd.concat(bb_lowers, axis=1).min(axis=1)
    
    thickness = (bb_lower_max - bb_lower_min) / atr
    penetration = sum((df['low'] < df[f'FIB_{k}_BB_lower']).astype(int) for k in fib_ks)
    
    recent_panic = penetration.rolling(3).max().shift(1).fillna(0)
    full_return = (df['close'] > bb_lower_max).astype(int)
    exhaustion = (df['low'] > df['low'].shift(1)).astype(int)
    
    trigger_v2 = np.where(recent_panic >= 5, recent_panic * full_return * exhaustion, 0)
    
    return trigger_v2, penetration, thickness, bb_lower_max

def run():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    
    # Calculate v4.5 and v4.6 triggers
    t_v45, bb_lower_144 = build_v4_5_triggers(df)
    t_v46, penetration, thickness, bb_lower_max = build_v4_6_features(df)
    
    df['v45_Trigger'] = t_v45
    df['v46_Trigger'] = t_v46
    df['v45_wall'] = bb_lower_144
    df['v46_wall'] = bb_lower_max
    df['Penetration'] = penetration
    df['Thickness'] = thickness
    
    # Generate labels to find actual failures
    tb = get_binary_barrier_labels(df, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    df['label'] = tb['label']
    df['tb_return'] = tb['tb_return']
    
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    
    # Load v4.5 model to find its confident false positives
    model_v45 = lgb.Booster(model_file='models/lgbm_v4_5_long.txt')
    
    # We need to recreate v4.5 features exactly to get preds
    from train_lightgbm import build_v4_5_features
    df_v45, f_cols_v45 = build_v4_5_features(df.copy())
    X_holdout_v45 = df_v45[df_v45.index >= HOLDOUT_START][f_cols_v45]
    preds_v45 = model_v45.predict(X_holdout_v45)
    df_holdout['prob_v45'] = preds_v45
    
    # Find moments where v4.5 fired confidently (>0.35 threshold) but LOST (label == 0)
    # AND v4.6 successfully blocked it (v46_Trigger == 0)
    failures = df_holdout[
        (df_holdout['prob_v45'] > 0.35) & 
        (df_holdout['v45_Trigger'] > 0) & 
        (df_holdout['label'] == 0) &
        (df_holdout['v46_Trigger'] == 0)
    ]
    
    # Sort by how bad the loss was (or how confident v4.5 was)
    failures = failures.sort_values(by='prob_v45', ascending=False)
    
    print("\n=========================================================")
    print("定量化比較: v4.5の誤認エントリーとv4.6による防御")
    print("=========================================================")
    print(f"{'Date':<20} | {'v4.5 Trigger':<12} | {'v4.6 Trigger':<12} | {'Penetration':<12} | {'Thickness':<10}")
    print("-" * 75)
    
    os.makedirs("results/defense", exist_ok=True)
    
    for i in range(min(3, len(failures))):
        target_date = failures.index[i]
        row = failures.loc[target_date]
        
        print(f"{str(target_date)[:19]:<20} | {row['v45_Trigger']:<12.2f} | {row['v46_Trigger']:<12.2f} | {row['Penetration']:<12.0f} | {row['Thickness']:<10.2f}")
        
        # Plotting
        entry_idx = df_holdout.index.get_loc(target_date)
        start_idx = max(0, entry_idx - 72)
        end_idx = min(len(df_holdout) - 1, entry_idx + 72)
        window = df_holdout.iloc[start_idx:end_idx]
        
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [3, 1, 1]}, sharex=True)
        
        # 1. Price and Walls
        ax1.vlines(window.index, window['low'], window['high'], color='black', alpha=0.5)
        ax1.plot(window.index, window['close'], color='black', label='Close')
        ax1.plot(window.index, window['v45_wall'], color='red', linestyle='--', alpha=0.7, label='v4.5 Wall (FIB_10)')
        ax1.plot(window.index, window['v46_wall'], color='green', linewidth=2, alpha=0.9, label='v4.6 Safe Wall (Max Lower)')
        
        # Mark v4.5 entry
        ax1.scatter(target_date, row['close'], color='red', s=200, marker='X', zorder=5, label='v4.5 False Entry')
        
        ax1.set_title(f"v4.6 Defense against False Positive #{i+1} (Centered at {target_date})")
        ax1.legend(loc='upper right')
        ax1.grid(True, alpha=0.3)
        
        # 2. Triggers and Penetration
        ax2.fill_between(window.index, 0, window['Penetration'], color='blue', alpha=0.2, label='Penetration Score')
        ax2.axhline(5, color='orange', linestyle=':', label='v4.6 Min Required (5)')
        
        ax2.stem(window.index, window['v45_Trigger'] > 0, linefmt='r-', markerfmt='ro', basefmt=' ', label='v4.5 Fired')
        # Add v4.6 trigger as green, but it should be zero here
        ax2.stem(window.index, window['v46_Trigger'] > 0, linefmt='g-', markerfmt='go', basefmt=' ', label='v4.6 Fired')
        
        ax2.set_title("Trigger Activation & Penetration Score")
        ax2.legend(loc='upper right')
        ax2.set_ylim(0, 8)
        ax2.grid(True, alpha=0.3)
        
        # 3. Thickness (Fan-out)
        ax3.plot(window.index, window['Thickness'], color='purple')
        ax3.fill_between(window.index, 0, window['Thickness'], color='purple', alpha=0.3)
        ax3.set_title("BB Layer Thickness (Fan-out distance in ATR)")
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        filepath = f"results/defense/v46_defense_{i+1}.png"
        plt.savefig(filepath)
        plt.close()
        # print(f"Saved {filepath}")

    print("=========================================================")
    print("画像の保存が完了しました (results/defense/v46_defense_*.png)")

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings('ignore')
    run()
