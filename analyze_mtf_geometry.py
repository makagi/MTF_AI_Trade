import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
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
    return df

def get_fib_periods():
    return [21, 55, 144, 233, 377, 610, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        df[f'SMA_{p}'] = sma
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
    return df

def plot_candlesticks(ax, df_slice, title):
    up = df_slice[df_slice['close'] >= df_slice['open']]
    down = df_slice[df_slice['close'] < df_slice['open']]
    ax.vlines(up.index, up['low'], up['high'], color='lime', linewidth=1)
    ax.vlines(down.index, down['low'], down['high'], color='red', linewidth=1)
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
    
    # Target 1 (Elite): 2022-08-11 01:00:00 (Horizontal S/R and Waning Momentum)
    # Target 2 (Ceiling): 2020-07-06 17:00:00 (Hugging 377, 233 catches up, Symmetry)
    # Target 3 (V-Shape): 2020-04-14 15:00:00 (Zoom out for Macro W-Bottom)
    
    # Map index names to integer locs (approximate if exact not found, but we know they exist)
    target1 = pd.to_datetime('2022-08-11 01:00:00')
    target2 = pd.to_datetime('2020-07-06 17:00:00')
    target3 = pd.to_datetime('2020-04-14 15:00:00')
    
    plt.style.use('dark_background')
    fig, axes = plt.subplots(3, 1, figsize=(16, 22))
    
    # --- Panel 1: Parallel SMAs & Horizontal S/R (2022-08-11) ---
    if target1 in df.index:
        loc1 = df.index.get_loc(target1)
        win1 = df.iloc[loc1-150:loc1+50].reset_index(drop=True)
        ax1 = axes[0]
        plot_candlesticks(ax1, win1, "Case 1: Parallel SMAs & Horizontal S/R\nExtrema act as walls until Short-Term Momentum (AFS) wanes")
        
        ax1.plot(win1.index, win1['SMA_144'], color='cyan', label='SMA 144')
        ax1.plot(win1.index, win1['SMA_377'], color='magenta', label='SMA 377')
        
        # Extrema Horizontal Lines
        past_max = win1['high'].iloc[0:100].max()
        past_min = win1['low'].iloc[0:100].min()
        ax1.axhline(past_max, color='yellow', linestyle='--', alpha=0.7, label='Previous Max (Resistance)')
        ax1.axhline(past_min, color='yellow', linestyle='--', alpha=0.7, label='Previous Min (Support)')
        
        # Subplot for AFS inside the main plot using twinx
        ax1_afs = ax1.twinx()
        ax1_afs.plot(win1.index, win1['AFS_21'], color='white', alpha=0.4, label='AFS 21 (Momentum)')
        ax1_afs.set_ylim(-20, 120)
        
        # Annotation
        ax1.annotate("Momentum Exhaustion\nParallel breaks, moving to Long-Term SMA", xy=(150, win1['low'].iloc[150]),
                     xytext=(150-30, win1['low'].iloc[150] - win1['ATR'].iloc[150]*3),
                     arrowprops=dict(facecolor='lime', shrink=0.05), color='lime', fontsize=12)
        ax1.legend(loc='upper left')
        
    # --- Panel 2: The Hugging, Catch-up & Symmetry (2020-07-06) ---
    if target2 in df.index:
        loc2 = df.index.get_loc(target2)
        # We need a wider view after entry to show the symmetry and 233 catching up
        win2 = df.iloc[loc2-100:loc2+250].reset_index(drop=True)
        ax2 = axes[1]
        plot_candlesticks(ax2, win2, "Case 2: The Hugging, 233x377 Cross & Spatial Symmetry\nPrice hugs 377 as support until 233 catches up, then explodes symmetrically")
        
        ax2.plot(win2.index, win2['SMA_233'], color='orange', label='SMA 233 (The Catalyst)')
        ax2.plot(win2.index, win2['SMA_377'], color='magenta', label='SMA 377 (The Base/Support)')
        ax2.plot(win2.index, win2['SMA_610'], color='cyan', label='SMA 610 (The Resistance/Symmetry Target)')
        
        entry_x = 100
        # Find exactly where 233 crosses 377 after entry
        cross_idx = None
        for i in range(entry_x, len(win2)):
            if win2['SMA_233'].iloc[i] > win2['SMA_377'].iloc[i]:
                cross_idx = i
                break
                
        if cross_idx:
            ax2.axvline(cross_idx, color='yellow', linestyle='--', alpha=0.7)
            ax2.annotate("233 catches up & crosses 377\n(Ignition Point)", xy=(cross_idx, win2['SMA_377'].iloc[cross_idx]),
                         xytext=(cross_idx+10, win2['SMA_377'].iloc[cross_idx] - 300),
                         arrowprops=dict(facecolor='yellow', shrink=0.05), color='yellow', fontsize=12)
                         
        # Highlight Hugging Zone
        ax2.axvspan(entry_x, cross_idx if cross_idx else entry_x+50, color='white', alpha=0.1, label='The Hugging Zone')
        
        # Spatial Symmetry
        min_before = win2['low'].iloc[0:entry_x].min()
        base_377 = win2['SMA_377'].iloc[entry_x]
        dist_down = base_377 - min_before
        target_up = base_377 + dist_down
        
        ax2.axhline(min_before, color='red', linestyle=':', label='Max Depth Below 377')
        ax2.axhline(target_up, color='lime', linestyle=':', label='Symmetric Target Above 377')
        
        ax2.annotate("Symmetry Law:\nDistance Below = Distance Above", xy=(cross_idx+30, target_up),
                     xytext=(cross_idx-50, target_up+100), color='lime', fontsize=12)
        ax2.legend(loc='upper left')

    # --- Panel 3: Zoom-out for Macro W-Bottom (2020-04-14) ---
    if target3 in df.index:
        loc3 = df.index.get_loc(target3)
        # We need a massive window to see the mid-March COVID crash (approx 30 days = 720 hours before)
        win3 = df.iloc[loc3-800:loc3+100].reset_index(drop=True)
        ax3 = axes[2]
        plot_candlesticks(ax3, win3, "Case 3: Zooming Out (Macro Horizon)\nThe isolated V-Shape is revealed as the right leg of a massive Macro W-Bottom")
        
        ax3.plot(win3.index, win3['SMA_377'], color='magenta', label='SMA 377')
        
        # Find the two bottoms
        bottom1_x = win3['low'].iloc[0:400].argmin()
        bottom1_y = win3['low'].iloc[bottom1_x]
        
        bottom2_x = 800
        bottom2_y = win3['low'].iloc[bottom2_x]
        
        ax3.annotate("Left Leg (Macro Bottom 1)\nCOVID Crash", xy=(bottom1_x, bottom1_y),
                     xytext=(bottom1_x-100, bottom1_y-500),
                     arrowprops=dict(facecolor='lime', shrink=0.05), color='lime', fontsize=12)
                     
        ax3.annotate("Right Leg (Macro Bottom 2)\nPreviously looked like a V-Shape", xy=(bottom2_x, bottom2_y),
                     xytext=(bottom2_x-100, bottom2_y-500),
                     arrowprops=dict(facecolor='lime', shrink=0.05), color='lime', fontsize=12)
                     
        # Draw macro W line
        ax3.plot([bottom1_x, bottom1_x+200, bottom2_x, bottom2_x+99], 
                 [bottom1_y, win3['high'].iloc[bottom1_x+200], bottom2_y, win3['high'].iloc[bottom2_x+99]], 
                 color='yellow', linestyle='--', alpha=0.5, linewidth=3, label='Macro W-Structure')
                 
        ax3.legend(loc='upper left')

    plt.tight_layout()
    plt.savefig("mtf_geometry_proven.png", dpi=300)
    print("Saved mtf_geometry_proven.png")

if __name__ == '__main__':
    main()
