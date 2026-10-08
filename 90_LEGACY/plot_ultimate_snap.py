import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
from tqdm import tqdm
import warnings
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

def main():
    print("Loading 1h Data for plotting...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, 14)
    
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift())
    df['tr2'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['ATR_14'] = df['tr'].rolling(14).mean()
    
    sma_8 = df['FIB_5_SMA']
    sma_21 = df['FIB_7_SMA']
    sma_55 = df['FIB_9_SMA']
    sma_89 = df['FIB_10_SMA']
    sma_144 = df['FIB_11_SMA']
    sma_377 = df['FIB_13_SMA']
    
    # We already know a great case is around 2023-08-27 13:00:00
    target_date = pd.to_datetime('2023-08-27 13:00:00')
    start_date = target_date - pd.Timedelta(hours=48)
    end_date = target_date + pd.Timedelta(hours=96)
    zoom_df = df.loc[start_date:end_date]
    
    # Find Absolute Low (Left Shoulder)
    # The panic low should be before the target date
    pre_trigger = zoom_df.loc[:target_date - pd.Timedelta(hours=4)]
    abs_low_idx = pre_trigger['low'].idxmin()
    abs_low_val = pre_trigger.loc[abs_low_idx, 'low']
    
    # Find Higher Low (Right Shoulder)
    # Between abs_low and target_date
    between = zoom_df.loc[abs_low_idx + pd.Timedelta(hours=1) : target_date]
    if len(between) > 0:
        higher_low_idx = between['low'].idxmin()
        higher_low_val = between.loc[higher_low_idx, 'low']
    else:
        higher_low_idx = abs_low_idx
        higher_low_val = abs_low_val
        
    plt.figure(figsize=(16, 9))
    
    # Fill "The Wall" Clouds
    plt.fill_between(zoom_df.index, zoom_df['FIB_9_SMA'], zoom_df['FIB_10_SMA'], color='pink', alpha=0.15, label='Inner Wall (55-89)')
    plt.fill_between(zoom_df.index, zoom_df['FIB_10_SMA'], zoom_df['FIB_11_SMA'], color='red', alpha=0.15, label='Outer Wall (89-144)')
    
    # Plot SMAs
    plt.plot(zoom_df.index, zoom_df['FIB_5_SMA'], label='Micro (8)', color='cyan', linestyle=':')
    plt.plot(zoom_df.index, zoom_df['FIB_7_SMA'], label='Short (21)', color='lime', linestyle='--')
    plt.plot(zoom_df.index, zoom_df['FIB_9_SMA'], label='Tension (55)', color='orange', linewidth=2)
    plt.plot(zoom_df.index, zoom_df['FIB_10_SMA'], label='Sub-Anchor (89)', color='purple', linewidth=2)
    plt.plot(zoom_df.index, zoom_df['FIB_11_SMA'], label='Anchor (144)', color='red', linewidth=2)
    plt.plot(zoom_df.index, zoom_df['FIB_13_SMA'], label='Magnet (377)', color='magenta', linewidth=3)
    
    # Plot Price
    # using close for smooth line, but could use OHLC
    plt.plot(zoom_df.index, zoom_df['close'], label='Close Price', color='white', linewidth=2)
    
    # Mark Bottoms (Higher Low Structure)
    plt.scatter(abs_low_idx, abs_low_val, color='red', s=200, zorder=5, label='Panic Low (Abs_Low)')
    plt.scatter(higher_low_idx, higher_low_val, color='green', s=200, zorder=5, label='Higher Low (Right Shoulder)')
    
    # Connect the bottoms
    if abs_low_idx != higher_low_idx:
        plt.plot([abs_low_idx, higher_low_idx], [abs_low_val, higher_low_val], color='green', linewidth=3, linestyle='-.', zorder=4)
        
    # Find a false signal near absolute low
    false_trigger = pre_trigger[(pre_trigger['FIB_5_SMA'] > pre_trigger['FIB_7_SMA'])].index
    if len(false_trigger) > 0:
        ft_idx = false_trigger[0]
        plt.scatter(ft_idx, zoom_df.loc[ft_idx, 'close'], color='grey', marker='x', s=150, zorder=6, label='Ignored (No Higher Low)')
        
    # Mark The Ultimate Snap Trigger
    plt.scatter(target_date, zoom_df.loc[target_date, 'close'] - zoom_df.loc[target_date, 'ATR_14'], 
                color='yellow', s=300, marker='^', zorder=5, label='Ultimate Snap Trigger!')
                
    # Arrow pointing to 377
    plt.annotate('Violent Reversion to Magnet', 
         xy=(target_date + pd.Timedelta(hours=24), zoom_df.loc[target_date + pd.Timedelta(hours=24), 'FIB_13_SMA']), 
         xytext=(target_date, zoom_df.loc[target_date, 'close']),
         arrowprops=dict(facecolor='yellow', shrink=0.05, width=2, headwidth=10),
         fontsize=14, color='yellow', weight='bold')
         
    plt.title(f"The Ultimate Snap Trigger: Wall Cloud & Higher Low Mechanics\n(377 > 144 > 89 > 55 with Inverse H&S Validation)", fontsize=18)
    plt.legend(loc='lower left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    plt.grid(True, alpha=0.2)
    plt.gca().set_facecolor('black')
    
    # Format x axis dates
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    
    plt.tight_layout()
    plt.savefig("ultimate_snap_case.png", dpi=300)
    print("Saved ultimate_snap_case.png")

if __name__ == '__main__':
    main()
