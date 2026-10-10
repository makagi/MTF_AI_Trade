import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

def get_fib_periods():
    return { 'k=7': 21, 'k=9': 55, 'k=10': 89, 'k=11': 144, 'k=13': 377, 'k=14': 610, 'k=16': 1597 }

def add_bb_features(df, periods_dict):
    for label, p in periods_dict.items():
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'BB_U_{label}'] = upper
        df[f'BB_L_{label}'] = lower
        df[f'BW_{label}'] = (upper - lower) / df['close']
        df[f'PCTB_{label}'] = (df['close'] - lower) / (upper - lower + 1e-8)
        
        # Velocity and Acceleration of Bandwidth (N=24 hours)
        df[f'VEL_BW_{label}'] = df[f'BW_{label}'].diff(24)
        df[f'ACC_BW_{label}'] = df[f'VEL_BW_{label}'].diff(24)
    return df

def simulate_trades(df, armed_indices, stop_loss_atr=1.0, take_profit_atr=2.5, max_hold=72):
    successes = []
    failures = []
    
    for t_idx in armed_indices:
        t_loc = df.index.get_loc(t_idx)
        if t_loc + max_hold >= len(df): continue
        forward = df.iloc[t_loc+1 : t_loc+max_hold]
        entry = df.iloc[t_loc]['close']
        atr = df.iloc[t_loc]['ATR']
        
        hit_tp = False
        hit_sl = False
        hold_time = 0
        mae_val = 0
        
        for i in range(len(forward)):
            curr_high = forward['high'].iloc[i]
            curr_low = forward['low'].iloc[i]
            
            # Track MAE step by step
            mae_val = min(mae_val, (curr_low - entry) / atr)
            
            if curr_high >= entry + (take_profit_atr * atr):
                hit_tp = True
                hold_time = i + 1
                break
            if curr_low <= entry - (stop_loss_atr * atr):
                hit_sl = True
                hold_time = i + 1
                break
                
        if hit_tp:
            successes.append({'Date': t_idx, 'Hold_Time': hold_time, 'MAE': mae_val})
        else:
            failures.append({'Date': t_idx, 'Hold_Time': hold_time if hit_sl else max_hold, 'MAE': mae_val})
            
    return successes, failures

def plot_resolution_timing(df, target_date, filename):
    start = target_date - pd.Timedelta(days=10)
    end = target_date + pd.Timedelta(days=5)
    zoom = df.loc[start:end]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [2, 1]})
    
    ax1.plot(zoom.index, zoom['close'], color='white', label='Close')
    ax1.plot(zoom.index, zoom['FIB_11_SMA'], color='purple', linestyle='--', label='144')
    ax1.plot(zoom.index, zoom['FIB_13_SMA'], color='red', label='377')
    ax1.scatter(target_date, zoom.loc[target_date, 'close'], color='lime', s=300, marker='^', zorder=5, label='Resolution Trigger (Perfect Timing)')
    
    ax1.set_title(f"Time-to-Resolution: {target_date.strftime('%Y-%m-%d %H:%M')}", fontsize=18)
    ax1.legend(loc='upper left', frameon=True, facecolor='black')
    ax1.grid(True, alpha=0.2)
    ax1.set_facecolor('black')
    
    ax2.plot(zoom.index, zoom['BW_k=13'], color='magenta', label='377 Bandwidth')
    # Plot Velocity on a secondary y-axis to show it crossing 0
    ax2_twin = ax2.twinx()
    ax2_twin.plot(zoom.index, zoom['VEL_BW_k=13'], color='cyan', linestyle=':', label='Velocity (Rate of Squeeze)')
    ax2_twin.axhline(0, color='yellow', linestyle='-', alpha=0.5)
    
    ax2.axvline(target_date, color='lime', linestyle='--', linewidth=2)
    
    ax2.set_title("Bandwidth Squeeze Apex (Velocity approaching 0, Acceleration positive)", fontsize=14)
    ax2.legend(loc='upper left', frameon=True, facecolor='black')
    ax2_twin.legend(loc='upper right', frameon=True, facecolor='black')
    ax2.grid(True, alpha=0.2)
    ax2.set_facecolor('black')
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    plt.close()

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, 16)
    df = add_bb_features(df, get_fib_periods())
    
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift())
    df['tr2'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['ATR'] = df['tr'].rolling(14).mean()
    
    # 1. Base Macro Trigger (Wall, Void, Higher Low, Cross Prop)
    wall = (df['FIB_13_SMA'] > df['FIB_11_SMA']) & (df['FIB_11_SMA'] > df['FIB_10_SMA']) & (df['FIB_10_SMA'] > df['FIB_9_SMA'])
    void = ((df['FIB_13_SMA'] - df['FIB_11_SMA']) / df['close']) > 0.02
    local_low = df['low'].rolling(4).min()
    abs_low = df['low'].rolling(24).min()
    hl = (local_low > abs_low) & (local_low < abs_low + df['ATR'])
    score = (df['FIB_5_SMA'] > df['FIB_7_SMA']).astype(int) + (df['close'] > df['FIB_9_SMA']).astype(int) + (df['FIB_7_SMA'] > df['FIB_9_SMA']).astype(int)
    prop = (score >= 2) & (score.shift(1) < 2)
    
    base_trigger = wall & void & hl & prop
    
    # 2. Trapdoor Veto (k=13 expanding down)
    bw_expanding = df['BW_k=13'].diff(24) > 0
    pctb_falling = df['PCTB_k=13'].diff(24) < 0
    trapdoor_veto = bw_expanding & pctb_falling
    
    armed_old = base_trigger & ~trapdoor_veto
    
    # 3. New Filter: Time-to-Resolution
    # Wait until k=13 (377) bandwidth velocity is >= -0.005 (squeeze slowing down) and accel is > 0
    # or it is already expanding upwards.
    # To keep it generalized without breaking entirely, we look for Vel_BW >= -0.002
    resolution_ready = (df['VEL_BW_k=13'] >= -0.002) & (df['ACC_BW_k=13'] > 0)
    
    # Since prop might happen *before* resolution, we create a rolling window. If armed_old happened within the last 48 hours, 
    # and NOW resolution is ready, we trigger.
    armed_window = armed_old.rolling(48).max() > 0
    armed_new = armed_window & resolution_ready & (resolution_ready.shift(1) == False) & ~trapdoor_veto
    
    armed_old_indices = df[armed_old].index
    armed_new_indices = df[armed_new].index
    
    print(f"\n--- Old Strategy (No Resolution Timing) ---")
    succ_old, fail_old = simulate_trades(df, armed_old_indices)
    total_old = len(succ_old) + len(fail_old)
    if total_old > 0:
        print(f"Total Trades: {total_old}")
        print(f"Successes: {len(succ_old)} (Win Rate: {len(succ_old)/total_old*100:.1f}%)")
        if succ_old:
            avg_hold_old = np.mean([s['Hold_Time'] for s in succ_old])
            avg_mae_old = np.mean([s['MAE'] for s in succ_old])
            print(f"Avg Hold Time (Success): {avg_hold_old:.1f} hours")
            print(f"Avg MAE (Drawdown before Success): {avg_mae_old:.2f} ATR")
            
    print(f"\n--- New Strategy (With Time-to-Resolution) ---")
    succ_new, fail_new = simulate_trades(df, armed_new_indices)
    total_new = len(succ_new) + len(fail_new)
    if total_new > 0:
        print(f"Total Trades: {total_new}")
        print(f"Successes: {len(succ_new)} (Win Rate: {len(succ_new)/total_new*100:.1f}%)")
        if succ_new:
            avg_hold_new = np.mean([s['Hold_Time'] for s in succ_new])
            avg_mae_new = np.mean([s['MAE'] for s in succ_new])
            print(f"Avg Hold Time (Success): {avg_hold_new:.1f} hours")
            print(f"Avg MAE (Drawdown before Success): {avg_mae_new:.2f} ATR")
            
            # Plot the best timing one
            best_timing = min(succ_new, key=lambda x: x['Hold_Time'])
            plot_resolution_timing(df, best_timing['Date'], "perfect_resolution_timing.png")
            print(f"Saved perfect_resolution_timing.png")

if __name__ == '__main__':
    main()
