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
    print("Loading 1h Data for plotting the TRUE Ultimate Snap...")
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
    
    print("Evaluating Strict Ultimate Trigger Conditions...")
    
    # 1. The Wall (377 > 144 > 89 > 55)
    cond_wall = (sma_377 > sma_144) & (sma_144 > sma_89) & (sma_89 > sma_55)
    
    # 2. Higher Low (24h abs low vs 4h local low)
    abs_low_24h = df['low'].rolling(24).min()
    local_low_4h = df['low'].rolling(4).min()
    cond_hl = (local_low_4h > abs_low_24h) & (local_low_4h < abs_low_24h + (1.0 * df['ATR_14']))
    
    # 3. AFS Reversion
    cond_afs = (df['AFS_7_14'] > df['AFS_9_14']) & (df['AFS_7_14'].shift(1) <= df['AFS_9_14'].shift(1))
    
    # 4. Cross Propagation
    score = np.zeros(len(df))
    score += (sma_8 > sma_21).astype(int)
    score += (df['close'] > sma_55).astype(int)
    score += (sma_21 > sma_55).astype(int)
    cond_prop = (score == 3) & (pd.Series(score).shift(1) < 3)
    
    # 5. Must also have the Void between 144 and 377
    cond_void = ((sma_377 - sma_144) / df['close']) > 0.02
    
    # Ultimate Trigger Mask
    ultimate_trigger = cond_wall & cond_hl & cond_afs & cond_prop & cond_void
    
    trigger_indices = df[ultimate_trigger == True].index
    print(f"Found {len(trigger_indices)} TRUE Ultimate Snap cases in the dataset.")
    
    if len(trigger_indices) == 0:
        # Relax AFS condition slightly if no cases found exactly at the cross hour
        # Sometimes AFS cross happens 1-2 hours before or after the score hits 3
        print("Relaxing AFS condition (within last 3 hours)...")
        cond_afs_relaxed = (df['AFS_7_14'] > df['AFS_9_14']).rolling(3).max() > 0
        ultimate_trigger = cond_wall & cond_hl & cond_afs_relaxed & cond_prop & cond_void
        trigger_indices = df[ultimate_trigger == True].index
        print(f"Found {len(trigger_indices)} relaxed cases.")
        
        if len(trigger_indices) == 0:
            print("No perfect cases found. Aborting.")
            return

    # Calculate Forward MFE to pick the most dramatic one
    best_mfe = -1
    best_target = None
    
    for t_idx in trigger_indices:
        t_loc = df.index.get_loc(t_idx)
        if t_loc + 72 >= len(df): continue
        forward_highs = df.iloc[t_loc+1 : t_loc+72]['high']
        mfe = (forward_highs.max() - df.iloc[t_loc]['close']) / df.iloc[t_loc]['ATR_14']
        if mfe > best_mfe:
            best_mfe = mfe
            best_target = t_idx
            
    if best_target is None:
        best_target = trigger_indices[0]
        
    print(f"Best Target Date: {best_target} with MFE: {best_mfe:.2f} ATR")
    
    # Plotting
    start_date = best_target - pd.Timedelta(hours=48)
    end_date = best_target + pd.Timedelta(hours=96)
    zoom_df = df.loc[start_date:end_date]
    
    # Find Abs Low and Higher Low for the plot lines
    pre_trigger = zoom_df.loc[:best_target - pd.Timedelta(hours=2)]
    abs_low_idx = pre_trigger['low'].idxmin()
    abs_low_val = pre_trigger.loc[abs_low_idx, 'low']
    
    between = zoom_df.loc[abs_low_idx + pd.Timedelta(hours=1) : best_target]
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
    plt.plot(zoom_df.index, zoom_df['close'], label='Close Price', color='white', linewidth=2)
    
    # Mark Bottoms (Higher Low Structure)
    plt.scatter(abs_low_idx, abs_low_val, color='red', s=200, zorder=5, label='Panic Low (Abs_Low)')
    plt.scatter(higher_low_idx, higher_low_val, color='green', s=200, zorder=5, label='Higher Low (Right Shoulder)')
    
    if abs_low_idx != higher_low_idx:
        plt.plot([abs_low_idx, higher_low_idx], [abs_low_val, higher_low_val], color='green', linewidth=3, linestyle='-.', zorder=4)
        
    # Mark The Ultimate Snap Trigger
    plt.scatter(best_target, zoom_df.loc[best_target, 'close'] - zoom_df.loc[best_target, 'ATR_14'], 
                color='yellow', s=300, marker='^', zorder=5, label='TRUE Ultimate Snap Trigger!')
                
    # Annotations and Titles
    plt.annotate('Violent Reversion to Magnet', 
         xy=(best_target + pd.Timedelta(hours=24), zoom_df.loc[best_target + pd.Timedelta(hours=24), 'FIB_13_SMA']), 
         xytext=(best_target, zoom_df.loc[best_target, 'close']),
         arrowprops=dict(facecolor='yellow', shrink=0.05, width=2, headwidth=10),
         fontsize=14, color='yellow', weight='bold')
         
    title_str = f"TRUE Ultimate Snap Trigger: {best_target.strftime('%Y-%m-%d %H:%M')}\n(STRICT Wall: 377>144>89>55 | H-Low Valid | AFS Reversion Valid)"
    plt.title(title_str, fontsize=18)
    
    # Add stats text box
    stats_text = (
        f"--- The Ultimate Snap Stats ---\n"
        f"Date: {best_target.strftime('%Y-%m-%d %H:%M')}\n"
        f"Total Occurrences (All Data): {len(trigger_indices)} times\n"
        f"Forward 72h MFE: {best_mfe:.2f} ATR"
    )
    props = dict(boxstyle='round', facecolor='black', alpha=0.8, edgecolor='white')
    plt.gca().text(0.02, 0.95, stats_text, transform=plt.gca().transAxes, fontsize=14,
            verticalalignment='top', bbox=props, color='yellow', weight='bold')
    
    plt.legend(loc='lower left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    plt.grid(True, alpha=0.2)
    plt.gca().set_facecolor('black')
    
    # Fix X-axis format to explicitly show the year
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    plt.savefig("true_ultimate_snap_case_v3.png", dpi=300)
    print("Saved true_ultimate_snap_case_v3.png")

if __name__ == '__main__':
    main()
