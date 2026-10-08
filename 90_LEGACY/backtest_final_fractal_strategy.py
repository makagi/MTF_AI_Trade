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
    return df

def plot_case(df, target_date, case_type, mfe, mae):
    start = target_date - pd.Timedelta(days=5)
    end = target_date + pd.Timedelta(days=5)
    zoom = df.loc[start:end]
    
    plt.figure(figsize=(12, 8))
    plt.plot(zoom.index, zoom['close'], color='white', label='Close')
    plt.plot(zoom.index, zoom['FIB_11_SMA'], color='purple', linestyle='--', label='144')
    plt.plot(zoom.index, zoom['FIB_13_SMA'], color='red', label='377')
    
    color = 'lime' if case_type == 'Success' else 'red' if case_type == 'Failure' else 'cyan'
    plt.scatter(target_date, zoom.loc[target_date, 'close'], color=color, s=300, marker='^', zorder=5, label=case_type)
    
    title = f"{case_type} Case: {target_date.strftime('%Y-%m-%d %H:%M')}\nMFE: {mfe:.2f} ATR, MAE: {mae:.2f} ATR"
    plt.title(title, fontsize=16)
    plt.legend(loc='upper left', frameon=True, facecolor='black')
    plt.grid(True, alpha=0.2)
    plt.gca().set_facecolor('black')
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"final_{case_type.lower()}_case.png", dpi=300)
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
    
    # Base Macro Trigger
    wall = (df['FIB_13_SMA'] > df['FIB_11_SMA']) & (df['FIB_11_SMA'] > df['FIB_10_SMA']) & (df['FIB_10_SMA'] > df['FIB_9_SMA'])
    void = ((df['FIB_13_SMA'] - df['FIB_11_SMA']) / df['close']) > 0.02
    local_low = df['low'].rolling(4).min()
    abs_low = df['low'].rolling(24).min()
    hl = (local_low > abs_low) & (local_low < abs_low + df['ATR'])
    
    # Cross Prop
    score = (df['FIB_5_SMA'] > df['FIB_7_SMA']).astype(int) + (df['close'] > df['FIB_9_SMA']).astype(int) + (df['FIB_7_SMA'] > df['FIB_9_SMA']).astype(int)
    prop = (score >= 2) & (score.shift(1) < 2)
    
    base_trigger = wall & void & hl & prop
    
    # Generalized Veto: k=13 Trapdoor
    # BW of k=13 is expanding (diff > 0 over 24h) and PCTB is falling
    bw_expanding = df['BW_k=13'].diff(24) > 0
    pctb_falling = df['PCTB_k=13'].diff(24) < 0
    trapdoor_veto = bw_expanding & pctb_falling
    
    armed = base_trigger & ~trapdoor_veto
    missed_trigger = base_trigger & trapdoor_veto
    
    armed_indices = df[armed].index
    missed_indices = df[missed_trigger].index
    
    print(f"Base Triggers: {base_trigger.sum()}")
    print(f"Vetoed Triggers: {trapdoor_veto.sum()}")
    print(f"Final Armed: {len(armed_indices)}")
    print(f"Missed/Vetoed: {len(missed_indices)}")
    
    successes = []
    failures = []
    missed_list = []
    
    # Simulate Trades for Armed
    for t_idx in armed_indices:
        t_loc = df.index.get_loc(t_idx)
        if t_loc + 72 >= len(df): continue
        forward = df.iloc[t_loc+1 : t_loc+72]
        entry = df.iloc[t_loc]['close']
        atr = df.iloc[t_loc]['ATR']
        
        mfe = (forward['high'].max() - entry) / atr
        mae = (entry - forward['low'].min()) / atr
        
        # Simple TP/SL logic for proxy (Assuming micro sniper entered precisely)
        # We check path.
        hit_tp = False
        hit_sl = False
        for i in range(len(forward)):
            if forward['high'].iloc[i] >= entry + (2.5 * atr):
                hit_tp = True
                break
            if forward['low'].iloc[i] <= entry - (1.0 * atr):
                hit_sl = True
                break
                
        if hit_tp:
            successes.append((t_idx, mfe, mae))
        else:
            failures.append((t_idx, mfe, mae))
            
    # Simulate Trades for Missed (to find The Ghost Ship)
    for t_idx in missed_indices:
        t_loc = df.index.get_loc(t_idx)
        if t_loc + 72 >= len(df): continue
        forward = df.iloc[t_loc+1 : t_loc+72]
        entry = df.iloc[t_loc]['close']
        atr = df.iloc[t_loc]['ATR']
        mfe = (forward['high'].max() - entry) / atr
        mae = (entry - forward['low'].min()) / atr
        
        if mfe > 5.0: # The massive runs we missed
            missed_list.append((t_idx, mfe, mae))
            
    print(f"\nResults:")
    print(f"Successes (Hit +2.5 ATR TP): {len(successes)}")
    print(f"Failures (Hit -1.0 ATR SL): {len(failures)}")
    if (len(successes) + len(failures)) > 0:
        print(f"Win Rate: {len(successes) / (len(successes) + len(failures)) * 100:.1f}%")
    
    print(f"Missed Massive Runs (MFE > 5 ATR but Vetoed): {len(missed_list)}")
    
    # Save examples
    if successes: plot_case(df, successes[0][0], 'Success', successes[0][1], successes[0][2])
    if failures: plot_case(df, failures[0][0], 'Failure', failures[0][1], failures[0][2])
    if missed_list: plot_case(df, missed_list[0][0], 'Missed', missed_list[0][1], missed_list[0][2])

if __name__ == '__main__':
    main()
