import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

def main():
    print("Loading 1h Data and calculating up to FIB_17 (period 2584)...")
    df = load_1h_data(include_holdout=True)
    # Calculate up to index 17 (FIB_17 = 2584)
    df = calculate_fib_features(df, 17)
    
    # -------------------------------------------------------------
    # Hypothesis 1: 2024-01-20 (The Dud) - Macro Fall & Downward Slope
    # -------------------------------------------------------------
    print("Plotting Hypothesis 1 (2024-01-20)...")
    target_1 = pd.to_datetime('2024-01-20 23:00:00')
    start_1 = target_1 - pd.Timedelta(days=21) # 3 weeks before
    end_1 = target_1 + pd.Timedelta(days=7)   # 1 week after
    
    zoom_1 = df.loc[start_1:end_1]
    
    plt.figure(figsize=(16, 9))
    plt.plot(zoom_1.index, zoom_1['close'], label='Close Price', color='white', linewidth=1)
    plt.plot(zoom_1.index, zoom_1['FIB_11_SMA'], label='SMA 144', color='red', linestyle=':')
    plt.plot(zoom_1.index, zoom_1['FIB_13_SMA'], label='SMA 377 (Magnet)', color='magenta', linewidth=2)
    plt.plot(zoom_1.index, zoom_1['FIB_16_SMA'], label='SMA 1597 (Macro Ceiling)', color='orange', linewidth=3)
    
    plt.scatter(target_1, zoom_1.loc[target_1, 'close'], color='yellow', s=300, marker='v', zorder=5, label='The Failed Trigger')
    
    # Calculate Slopes using iloc
    t_loc_1 = zoom_1.index.get_loc(target_1)
    lookback_1 = max(0, t_loc_1 - 72) # Approx 3 days
    slope_377 = zoom_1['FIB_13_SMA'].iloc[t_loc_1] - zoom_1['FIB_13_SMA'].iloc[lookback_1]
    slope_afs_13 = zoom_1['AFS_13_17'].iloc[t_loc_1] - zoom_1['AFS_13_17'].iloc[lookback_1]
    
    stats_1 = (
        f"--- The Macro Fall (2024-01-20) ---\n"
        f"SMA 377 (Magnet) 3-Day Slope: {'Down' if slope_377 < 0 else 'Up'} ({slope_377:.2f} USD)\n"
        f"AFS 13 (Macro Momentum) 3-Day Slope: {'Down' if slope_afs_13 < 0 else 'Up'} ({slope_afs_13:.2f})\n"
        f"Price rejected from SMA 1597 and in free-fall."
    )
    props = dict(boxstyle='round', facecolor='black', alpha=0.8, edgecolor='white')
    plt.gca().text(0.02, 0.95, stats_1, transform=plt.gca().transAxes, fontsize=14,
            verticalalignment='top', bbox=props, color='yellow', weight='bold')
            
    plt.title("Hypothesis 1: The Macro Fall (Rejected by Ultra-Long Ceiling, Downward Slopes)", fontsize=18)
    plt.legend(loc='lower left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    plt.grid(True, alpha=0.2)
    plt.gca().set_facecolor('black')
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("snap_hypothesis_1_the_fall.png", dpi=300)
    print("Saved snap_hypothesis_1_the_fall.png")

    # -------------------------------------------------------------
    # Hypothesis 2: 2022-09-06 (The Average Joe) - Ultra-Long Support
    # -------------------------------------------------------------
    print("Plotting Hypothesis 2 (2022-09-06)...")
    target_2 = pd.to_datetime('2022-09-06 10:00:00')
    start_2 = target_2 - pd.Timedelta(days=3)
    end_2 = target_2 + pd.Timedelta(days=10) # Enough to see the -9 ATR dip and bounce
    
    zoom_2 = df.loc[start_2:end_2]
    
    plt.figure(figsize=(16, 9))
    plt.plot(zoom_2.index, zoom_2['close'], label='Close Price', color='white', linewidth=2)
    plt.plot(zoom_2.index, zoom_2['FIB_13_SMA'], label='SMA 377', color='magenta', linewidth=1)
    
    # Ultra-Long SMAs
    plt.plot(zoom_2.index, zoom_2['FIB_14_SMA'], label='SMA 610', color='cyan', linewidth=2, linestyle='--')
    plt.plot(zoom_2.index, zoom_2['FIB_15_SMA'], label='SMA 987', color='lime', linewidth=2, linestyle='--')
    plt.plot(zoom_2.index, zoom_2['FIB_16_SMA'], label='SMA 1597', color='orange', linewidth=2, linestyle='--')
    plt.plot(zoom_2.index, zoom_2['FIB_17_SMA'], label='SMA 2584 (God Tier)', color='red', linewidth=3)
    
    plt.scatter(target_2, zoom_2.loc[target_2, 'close'], color='yellow', s=200, marker='v', zorder=5, label='Trigger (Early, goes -9 ATR)')
    
    # Find the absolute bottom after trigger
    post_trigger = zoom_2.loc[target_2:target_2 + pd.Timedelta(days=5)]
    bottom_idx = post_trigger['low'].idxmin()
    bottom_val = post_trigger.loc[bottom_idx, 'low']
    plt.scatter(bottom_idx, bottom_val, color='lime', s=300, marker='^', zorder=6, label='Actual Bottom (Touched Ultra-Long SMA)')
    
    # Calculate Slope of SMA 2584 using iloc to avoid missing datetime keys
    bottom_loc = zoom_2.index.get_loc(bottom_idx)
    lookback_loc = max(0, bottom_loc - 120) # Approx 5 days * 24h
    slope_2584 = zoom_2['FIB_17_SMA'].iloc[bottom_loc] - zoom_2['FIB_17_SMA'].iloc[lookback_loc]
    
    stats_2 = (
        f"--- Ultra-Long Support (2022-09-06) ---\n"
        f"SMA 2584 5-Day Slope: {'Rising Support' if slope_2584 > 0 else 'Falling'} ({slope_2584:.2f} USD)\n"
        f"Price bottomed exactly at the Ultra-Long SMA."
    )
    plt.gca().text(0.02, 0.95, stats_2, transform=plt.gca().transAxes, fontsize=14,
            verticalalignment='top', bbox=props, color='yellow', weight='bold')
            
    plt.title("Hypothesis 2: Ultra-Long Structural Support (610, 987, 1597, 2584) Catching the Price", fontsize=18)
    plt.legend(loc='upper right', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    plt.grid(True, alpha=0.2)
    plt.gca().set_facecolor('black')
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("snap_hypothesis_2_ultra_support.png", dpi=300)
    print("Saved snap_hypothesis_2_ultra_support.png")

if __name__ == '__main__':
    main()
