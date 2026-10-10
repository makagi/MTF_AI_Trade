import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import matplotlib.pyplot as plt

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START
from src.labels import get_binary_barrier_labels
from train_lightgbm import build_v4_5_features

def run():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    
    df, feature_cols = build_v4_5_features(df)
    
    print("Generating labels...")
    tb_long = get_binary_barrier_labels(df, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    tb_short = get_binary_barrier_labels(df, pt_sl_ratio=[2.0, 1.0], time_barrier=72, direction='short')
    
    df['label_long'] = tb_long['label']
    df['tb_return_long'] = tb_long['tb_return']
    df['hit_period_long'] = tb_long['hit_period']
    
    df['label_short'] = tb_short['label']
    df['tb_return_short'] = tb_short['tb_return']
    df['hit_period_short'] = tb_short['hit_period']
    
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    X_holdout = df_holdout[feature_cols]
    
    model_long = lgb.Booster(model_file='models/lgbm_v4_5_long.txt')
    preds_long = model_long.predict(X_holdout)
    df_holdout['prob_long'] = preds_long
    
    # Extract Long Failures
    # Conditions: prob_long > 0.35, F_Reentry_Trigger_L > 0 (gating passed), but tb_return_long < 0 (SL hit or timeout)
    failures = df_holdout[
        (df_holdout['prob_long'] > 0.35) & 
        (df_holdout['F_Reentry_Trigger_L'] > 0) & 
        (df_holdout['tb_return_long'] <= 0)
    ].copy()
    
    # Sort by probability to find the most "confident" failures
    failures = failures.sort_values(by='prob_long', ascending=False)
    
    print(f"Found {len(failures)} Long failures.")
    
    os.makedirs("results/failures", exist_ok=True)
    
    # Plot top 3 failures
    for idx, (entry_date, row) in enumerate(failures.head(3).iterrows()):
        entry_idx = df_holdout.index.get_loc(entry_date)
        start_idx = max(0, entry_idx - 48)
        end_idx = min(len(df_holdout) - 1, entry_idx + 72)
        
        window = df_holdout.iloc[start_idx:end_idx].copy()
        
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [3, 1, 1]}, sharex=True)
        
        # 1. Price and Structure
        ax1.plot(window.index, window['close'], color='black', label='Close')
        
        # FIB_11 (144) BB
        std_144 = window['close'].rolling(144, min_periods=1).std().bfill()
        sma_144 = window['FIB_10_SMA']
        ax1.plot(window.index, sma_144, color='red', alpha=0.5, label='Macro SMA(144)')
        ax1.plot(window.index, sma_144 + 2*std_144, color='red', linestyle='--', alpha=0.3, label='Macro BB')
        ax1.plot(window.index, sma_144 - 2*std_144, color='red', linestyle='--', alpha=0.3)
        
        # FIB_6 (21) BB
        std_21 = window['close'].rolling(21, min_periods=1).std().bfill()
        sma_21 = window['FIB_6_SMA']
        ax1.plot(window.index, sma_21 + 2*std_21, color='blue', linestyle=':', alpha=0.3, label='Micro BB')
        ax1.plot(window.index, sma_21 - 2*std_21, color='blue', linestyle=':', alpha=0.3)
        
        # Entry point and Barriers
        entry_price = row['close']
        atr = row['ATR_14']
        tp_price = entry_price + 2.5 * atr
        sl_price = entry_price - 1.0 * atr
        
        ax1.scatter([entry_date], [entry_price], color='magenta', s=200, marker='^', label='LONG Entry')
        ax1.axhline(tp_price, color='green', linestyle='--', label='Take Profit (+2.5 ATR)')
        ax1.axhline(sl_price, color='red', linestyle='--', label='Stop Loss (-1.0 ATR)')
        
        ax1.set_title(f"Failure #{idx+1} ({entry_date}) | Prob: {row['prob_long']:.3f} | Ret: {row['tb_return_long']*100:.2f}%")
        ax1.legend(loc='best')
        ax1.grid(True, alpha=0.3)
        
        # 2. Flush Depth & Trigger
        ax2.bar(window.index, window['F_Flush_Depth_L'], color='orange', alpha=0.5, label='Flush Depth')
        trigger_dates = window[window['F_Reentry_Trigger_L'] > 0].index
        trigger_vals = window[window['F_Reentry_Trigger_L'] > 0]['F_Reentry_Trigger_L']
        ax2.stem(trigger_dates, trigger_vals, linefmt='r-', markerfmt='ro', basefmt=' ', label='Re-entry Trigger')
        ax2.set_title("Flush Depth & Sniper Trigger")
        ax2.legend(loc='best')
        ax2.grid(True, alpha=0.3)
        
        # 3. Volatility Spread
        ax3.plot(window.index, window['F_Fractal_Vol_Spread'], color='purple', label='Fractal Vol Spread (Log Ratio)')
        ax3.axhline(0, color='black', linestyle='--')
        ax3.set_title("Volatility Spread (Macro/Micro Squeeze)")
        ax3.legend(loc='best')
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        filepath = f"results/failures/long_fail_{idx+1}.png"
        plt.savefig(filepath)
        plt.close()
        print(f"Saved {filepath}")

if __name__ == "__main__":
    run()
