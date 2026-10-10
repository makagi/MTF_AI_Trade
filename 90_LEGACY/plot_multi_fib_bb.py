import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.cm as cm

from src.data_loader import load_1h_data
from src.features import calculate_fib_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START

def run():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    
    # Define target Fibonacci indices and periods
    # 6:21, 7:34, 8:55, 9:89, 10:144, 11:233, 12:377
    fib_map = {6: 21, 7: 34, 8: 55, 9: 89, 10: 144, 11: 233, 12: 377}
    
    bb_lowers = {}
    for idx, period in fib_map.items():
        std = df['close'].rolling(period, min_periods=1).std().bfill()
        sma = df[f'FIB_{idx}_SMA']
        bb_lower = sma - 2.0 * std
        bb_lowers[period] = bb_lower
        df[f'BB_Lower_{period}'] = bb_lower
    
    # Calculate Penetration Score (How many BB lowers did the Low pierce?)
    penetration_score = pd.Series(0, index=df.index)
    for period in fib_map.values():
        penetration_score += (df['low'] < df[f'BB_Lower_{period}']).astype(int)
    df['Penetration_Score'] = penetration_score
    
    # Calculate Band Thickness (Max BB_Lower - Min BB_Lower)
    all_bb_lowers = df[[f'BB_Lower_{p}' for p in fib_map.values()]]
    df['BB_Lower_Thickness'] = all_bb_lowers.max(axis=1) - all_bb_lowers.min(axis=1)
    
    # Filter to Holdout
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    
    # Find a highly penetrated moment (Max score)
    max_penetration_dates = df_holdout[df_holdout['Penetration_Score'] >= 6].index
    if len(max_penetration_dates) == 0:
        max_penetration_dates = df_holdout[df_holdout['Penetration_Score'] >= 4].index
        
    target_date = max_penetration_dates[0] if len(max_penetration_dates) > 0 else df_holdout.index[1000]
    
    # Create window
    entry_idx = df_holdout.index.get_loc(target_date)
    start_idx = max(0, entry_idx - 100)
    end_idx = min(len(df_holdout) - 1, entry_idx + 100)
    
    window = df_holdout.iloc[start_idx:end_idx].copy()
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [3, 1, 1]}, sharex=True)
    
    # 1. Price and Multi-Fib BBs
    # Plot High-Low bars
    ax1.vlines(window.index, window['low'], window['high'], color='black', alpha=0.5)
    ax1.plot(window.index, window['close'], color='black', label='Close')
    
    colors = cm.jet(np.linspace(0, 1, len(fib_map)))
    for i, period in enumerate(fib_map.values()):
        ax1.plot(window.index, window[f'BB_Lower_{period}'], color=colors[i], alpha=0.7, label=f'BB_Lower_{period}')
        
    ax1.set_title(f"Multi-Fibonacci BB Layers (Crash centered at {target_date})")
    ax1.legend(loc='upper right', bbox_to_anchor=(1.15, 1))
    ax1.grid(True, alpha=0.3)
    
    # 2. BB Thickness (Fan-out)
    ax2.plot(window.index, window['BB_Lower_Thickness'], color='purple', fillstyle='bottom')
    ax2.fill_between(window.index, 0, window['BB_Lower_Thickness'], color='purple', alpha=0.3)
    ax2.set_title("BB Lower Thickness (Fan-out Distance)")
    ax2.grid(True, alpha=0.3)
    
    # 3. Penetration Score
    ax3.bar(window.index, window['Penetration_Score'], color='orange', alpha=0.7)
    ax3.axhline(7, color='red', linestyle='--', alpha=0.5, label='Max Penetration (7 Layers)')
    ax3.set_title("Penetration Score (0-7 Layers)")
    ax3.set_ylim(0, 8)
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    os.makedirs("results/fib_bb", exist_ok=True)
    filepath = "results/fib_bb/multi_fib_bb_analysis.png"
    plt.savefig(filepath)
    plt.close()
    print(f"Saved {filepath}")

if __name__ == "__main__":
    run()
