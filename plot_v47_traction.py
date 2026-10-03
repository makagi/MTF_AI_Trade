import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H

def run():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    
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
    
    # Feature A: Floor Proximity
    df['F_Floor_Proximity_L'] = (df['close'] - bb_lower_min) / (bb_lower_max - bb_lower_min + 1e-8)
    
    # Feature B: Bottom Traction (21 vs 55)
    # Using FIB_6 (21) and FIB_8 (55)
    df['F_Bottom_Traction_L'] = (df['FIB_6_BB_lower'] - df['FIB_8_BB_lower']) / atr
    
    # Traction Cross (Negative to Positive)
    traction_crossed = (df['F_Bottom_Traction_L'] > 0) & (df['F_Bottom_Traction_L'].shift(1) <= 0)
    
    # Recent extreme floor (Proximity < 0.2 within last 5 bars)
    recent_floor = (df['F_Floor_Proximity_L'] < 0.2).rolling(5).max().fillna(0)
    
    df['v47_Trigger'] = traction_crossed & (recent_floor > 0)
    
    # Target date from previous failure
    target_date = pd.to_datetime('2025-11-21 08:00:00')
    
    entry_idx = df.index.get_loc(target_date)
    start_idx = max(0, entry_idx - 72)
    end_idx = min(len(df) - 1, entry_idx + 72)
    window = df.iloc[start_idx:end_idx]
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [3, 1, 1]}, sharex=True)
    
    # 1. Price and Fractal Range
    ax1.vlines(window.index, window['low'], window['high'], color='black', alpha=0.5)
    ax1.plot(window.index, window['close'], color='black', label='Close')
    ax1.plot(window.index, window['FIB_6_BB_lower'], color='red', alpha=0.7, label='Short (21) BB Lower')
    ax1.plot(window.index, window['FIB_8_BB_lower'], color='blue', alpha=0.7, label='Mid (55) BB Lower')
    
    ax1.fill_between(window.index, window['FIB_12_BB_lower'], window['FIB_6_BB_lower'], color='purple', alpha=0.1, label='Fractal Range Limit')
    
    # Plot triggers
    trigger_points = window[window['v47_Trigger'] == True]
    ax1.scatter(trigger_points.index, trigger_points['close'], color='green', s=300, marker='^', zorder=5, label='v4.7 Traction Trigger')
    
    ax1.set_title(f"v4.7: Short-Mid Traction pulling Long (Centered at {target_date})")
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    # 2. Traction Cross
    ax2.plot(window.index, window['F_Bottom_Traction_L'], color='blue', label='Traction (21_BB - 55_BB)')
    ax2.axhline(0, color='red', linestyle='--')
    ax2.fill_between(window.index, 0, window['F_Bottom_Traction_L'], where=(window['F_Bottom_Traction_L'] > 0), color='green', alpha=0.3)
    ax2.fill_between(window.index, 0, window['F_Bottom_Traction_L'], where=(window['F_Bottom_Traction_L'] < 0), color='red', alpha=0.3)
    
    # Mark Crosses
    ax2.scatter(trigger_points.index, trigger_points['F_Bottom_Traction_L'], color='green', s=100, marker='^', zorder=5)
    
    ax2.set_title("Bottom Traction (Short BB pulling above Mid BB)")
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    # 3. Floor Proximity
    ax3.plot(window.index, window['F_Floor_Proximity_L'], color='purple', label='Floor Proximity (0 = Absolute Bottom)')
    ax3.axhline(0, color='black')
    ax3.axhline(0.2, color='red', linestyle='--', label='Extreme Zone (<0.2)')
    ax3.set_ylim(-0.5, 1.5)
    ax3.set_title("Floor Proximity (Close Position within Fractal BB Range)")
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    os.makedirs("results/traction", exist_ok=True)
    filepath = "results/traction/v47_traction_analysis.png"
    plt.savefig(filepath)
    plt.close()
    print(f"Saved {filepath}")

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings('ignore')
    run()
