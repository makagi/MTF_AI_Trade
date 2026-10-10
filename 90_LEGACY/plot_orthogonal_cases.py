import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def calculate_atr(df, p=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(p).mean()
    df['ATR_144'] = true_range.rolling(144).mean()
    return df

def get_fib_periods():
    return [21, 55, 144, 377, 610, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'SMA_{p}'] = sma
        df[f'BB_Lower_{p}'] = lower
        df[f'BW_{p}'] = (upper - lower) / df['close']
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
        
        pctb = (df['close'] - lower) / (upper - lower + 1e-8)
        slope = (sma - sma.shift(p)) / sma.shift(p) * 100
        avg_pctb = pctb.rolling(p).mean()
        
        phase = np.zeros(len(df))
        uptrend = (slope > 0.5) & (avg_pctb > 0.5)
        downtrend = (slope < -0.5) & (avg_pctb < 0.5)
        phase[uptrend] = 1
        phase[downtrend] = -1
        phase[:p*2] = np.nan 
        df[f'PHASE_{p}'] = phase
    return df

def plot_candlesticks(ax, df_slice, title):
    up = df_slice[df_slice['close'] >= df_slice['open']]
    down = df_slice[df_slice['close'] < df_slice['open']]
    
    # Plot wicks
    ax.vlines(up.index, up['low'], up['high'], color='lime', linewidth=1)
    ax.vlines(down.index, down['low'], down['high'], color='red', linewidth=1)
    
    # Plot bodies
    ax.vlines(up.index, up['open'], up['close'], color='lime', linewidth=4)
    ax.vlines(down.index, down['open'], down['close'], color='red', linewidth=4)
    
    ax.set_title(title, fontsize=14, color='white')
    ax.set_facecolor('black')
    ax.tick_params(colors='white')

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    # Base Conditions
    bw144_q = df['BW_144'].rolling(720).quantile(0.4)
    cond_macro_vol = (df['BW_144'] < bw144_q)
    cond_macro_phase = (df['PHASE_144'] <= 0)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55'])
    cond_micro_phase = (df['PHASE_21'] == 1) & (df['PHASE_21'].shift(1) <= 0)
    base_idx = df[cond_macro_vol & cond_macro_phase & cond_micro_mom & cond_micro_phase].index
    
    # Features for classification
    sma_cols = ['SMA_144', 'SMA_377', 'SMA_610', 'SMA_1597']
    def get_ceiling(row):
        smas = row[sma_cols]
        return smas[smas > row['close']].min()
    df['Ceiling'] = df.apply(get_ceiling, axis=1)
    df['Void_ATR'] = (df['Ceiling'] - df['close']) / df['ATR_144']
    df['Void_ATR'] = df['Void_ATR'].fillna(10)
    
    price_low = df['low'].rolling(24).min()
    price_prev_low = df['low'].shift(24).rolling(96).min()
    afs_curr = df['AFS_144'].rolling(24).min()
    afs_prev = df['AFS_144'].shift(24).rolling(96).min()
    bull_div = (price_low < price_prev_low) & (afs_curr > afs_prev)
    
    # Classify and pick one representative for each
    elite_target = None
    ceiling_target = None
    vshape_target = None
    
    for idx in base_idx:
        loc = df.index.get_loc(idx)
        if loc < 100 or loc + 48 >= len(df):
            continue
            
        entry_price = df['close'].iloc[loc]
        atr = df['ATR'].iloc[loc]
        trajectory = (df['close'].iloc[loc:loc+48].values - entry_price) / atr
        mfe = trajectory.max()
        
        if mfe >= 1.5:
            div = bull_div.iloc[loc]
            void = df['Void_ATR'].iloc[loc]
            
            if div and void >= 3.0 and elite_target is None:
                elite_target = idx
            elif div and void < 3.0 and ceiling_target is None:
                ceiling_target = idx
            elif not div and vshape_target is None:
                vshape_target = idx
                
        if elite_target and ceiling_target and vshape_target:
            break
            
    print(f"Found targets: Elite={elite_target}, Ceiling={ceiling_target}, VShape={vshape_target}")
    
    # Plotting
    plt.style.use('dark_background')
    fig, axes = plt.subplots(3, 1, figsize=(14, 18))
    
    def plot_panel(ax, target_idx, title, case_type):
        if target_idx is None:
            return
        loc = df.index.get_loc(target_idx)
        window = df.iloc[loc-72:loc+48]
        window = window.reset_index(drop=True)
        entry_x = 72
        
        plot_candlesticks(ax, window, title)
        
        # Plot Entry Line
        ax.axvline(entry_x, color='white', linestyle='--', alpha=0.7)
        ax.annotate("Entry", xy=(entry_x, window['low'].iloc[entry_x] - window['ATR'].iloc[entry_x]), 
                    color='white', ha='center', fontsize=12)
        
        if case_type == 'elite':
            ax.plot(window.index, window['SMA_144'], color='cyan', label='SMA_144 (Support)')
            ax.plot(window.index, window['SMA_610'], color='magenta', label='SMA_610 (Ceiling)')
            ax.fill_between(window.index, window['SMA_144'], window['SMA_610'], color='cyan', alpha=0.1, label='The Void')
            ax.annotate("W-Bottom\n(Divergence)", xy=(entry_x - 10, window['low'].iloc[entry_x-10]),
                        xytext=(entry_x - 30, window['low'].iloc[entry_x-10] - window['ATR'].iloc[entry_x]),
                        arrowprops=dict(facecolor='lime', shrink=0.05), color='lime', fontsize=12)
            
        elif case_type == 'ceiling':
            ax.plot(window.index, window['SMA_377'], color='magenta', label='SMA_377 (Ceiling Block)')
            ax.annotate("Micro-Absorption\n(Energy Build-up)", xy=(entry_x - 2, window['high'].iloc[entry_x-2]),
                        xytext=(entry_x - 20, window['high'].iloc[entry_x-2] + window['ATR'].iloc[entry_x]),
                        arrowprops=dict(facecolor='cyan', shrink=0.05), color='cyan', fontsize=12)
            ax.annotate("The Breach\n(Violent Smash)", xy=(entry_x + 5, window['high'].iloc[entry_x+5]),
                        xytext=(entry_x + 10, window['high'].iloc[entry_x+5] + window['ATR'].iloc[entry_x]*2),
                        arrowprops=dict(facecolor='magenta', shrink=0.05), color='magenta', fontsize=12)
                        
        elif case_type == 'vshape':
            ax.plot(window.index, window['BB_Lower_377'], color='yellow', linestyle='--', label='Macro Lower BB')
            # Find minimum point (the pinbar)
            min_x = window['low'].argmin()
            ax.annotate("Liquidity Pinbar\n(Capitulation / Stop Hunt)", xy=(min_x, window['low'].iloc[min_x]),
                        xytext=(min_x - 15, window['low'].iloc[min_x] - window['ATR'].iloc[min_x]*1.5),
                        arrowprops=dict(facecolor='yellow', shrink=0.05), color='yellow', fontsize=12)
            ax.annotate("V-Shape Recovery\n(No Divergence)", xy=(entry_x, window['close'].iloc[entry_x]),
                        xytext=(entry_x + 10, window['close'].iloc[entry_x] - window['ATR'].iloc[entry_x]*1.5),
                        color='white', fontsize=12)
        ax.legend(loc='upper left')

    plot_panel(axes[0], elite_target, "Case 1: The Elite 4 (Zero-Gravity Alpha)\nWide Void Space and W-Bottom Divergence", 'elite')
    plot_panel(axes[1], ceiling_target, "Case 2: The Ceiling Breaker (The Battering Ram)\nSmashing through Macro SMA after Micro-Absorption", 'ceiling')
    plot_panel(axes[2], vshape_target, "Case 3: V-Shape Capitulation (Liquidity Sweep)\nExtreme Pinbar dropping below Macro BB with immediate recovery", 'vshape')
    
    plt.tight_layout()
    plt.savefig("price_action_footprints.png", dpi=300)
    print("Saved price_action_footprints.png")

if __name__ == '__main__':
    main()
