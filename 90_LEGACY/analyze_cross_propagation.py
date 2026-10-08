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
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, 14)
    
    # Calculate ATR for MFE scaling
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift())
    df['tr2'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['ATR_14'] = df['tr'].rolling(14).mean()
    
    # Define SMAs based on Fibonacci periods
    # FIB_5 = 8, FIB_7 = 21, FIB_9 = 55, FIB_11 = 144, FIB_13 = 377
    sma_8 = df['FIB_5_SMA']
    sma_21 = df['FIB_7_SMA']
    sma_55 = df['FIB_9_SMA']
    sma_144 = df['FIB_11_SMA']
    sma_377 = df['FIB_13_SMA']
    
    # 1. Is_Stretched (The Void and Order)
    # k+2 (377), k+1 (144), k (55)
    # Scenario: Deep Downtrend waiting for Snap Up
    order_down = (sma_377 > sma_144) & (sma_144 > sma_55)
    distance_magnet = (sma_377 - sma_144) / df['close']
    df['Is_Stretched_Down'] = order_down & (distance_magnet > 0.03) # 3% distance between 144 and 377
    
    # Scenario: Overextended Uptrend waiting for Snap Down
    order_up = (sma_377 < sma_144) & (sma_144 < sma_55)
    distance_magnet_up = (sma_144 - sma_377) / df['close']
    df['Is_Stretched_Up'] = order_up & (distance_magnet_up > 0.03)
    
    # 2. Cross Propagation Score (0 to 3) for Downtrend Reversal (Snap UP)
    # score += (SMA_8 > SMA_21)
    # score += (Close > SMA_55)
    # score += (SMA_21 > SMA_55)
    score_down = np.zeros(len(df))
    score_down += (sma_8 > sma_21).astype(int)
    score_down += (df['close'] > sma_55).astype(int)
    score_down += (sma_21 > sma_55).astype(int)
    df['Prop_Score_Down'] = score_down
    
    # Calculate MFE (Max Favorable Excursion) over next 72 hours (Upward)
    print("Calculating Forward MFE...")
    horizon = 72
    high_vals = df['high'].values
    atr_vals = df['ATR_14'].values
    c_vals = df['close'].values
    mfe_up = np.zeros(len(df))
    
    for i in tqdm(range(len(df) - horizon)):
        if atr_vals[i] == 0 or pd.isna(atr_vals[i]): continue
        max_h = np.max(high_vals[i+1 : i+horizon])
        mfe_up[i] = (max_h - c_vals[i]) / atr_vals[i]
    df['MFE_Up'] = mfe_up
    
    # Analyze Score vs MFE
    df_eval = df[df['Is_Stretched_Down'] == True].copy()
    print(f"\nTotal Stretched_Down periods found: {len(df_eval)}")
    
    if len(df_eval) > 0:
        plt.figure(figsize=(10, 6))
        sns.barplot(data=df_eval, x='Prop_Score_Down', y='MFE_Up', palette='YlOrRd')
        plt.title("Cross Propagation Score vs Forward MFE (When Stretched Down)")
        plt.xlabel("Propagation Score (0=No Cross -> 3=Full Cross to k)")
        plt.ylabel("Average Max Favorable Excursion (ATR)")
        plt.savefig("propagation_mfe_bar.png", dpi=300)
        print("Saved propagation_mfe_bar.png")
    
    # Find a specific perfect "Snap" case
    # Look for a moment where Score goes from 2 to 3 while Stretched
    df['Prop_Trigger'] = (df['Is_Stretched_Down'] == True) & (df['Prop_Score_Down'] == 3) & (df['Prop_Score_Down'].shift(1) < 3)
    trigger_indices = df[df['Prop_Trigger'] == True].index
    
    if len(trigger_indices) > 0:
        # Sort by MFE to show a great example
        best_trigger = df.loc[trigger_indices].sort_values('MFE_Up', ascending=False).index[0]
        print(f"Found perfect Snap Case around {best_trigger}")
        
        start_date = best_trigger - pd.Timedelta(hours=48)
        end_date = best_trigger + pd.Timedelta(hours=96)
        zoom_df = df.loc[start_date:end_date]
        
        plt.figure(figsize=(16, 8))
        plt.plot(zoom_df.index, zoom_df['close'], label='Close Price', color='white', linewidth=2)
        plt.plot(zoom_df.index, zoom_df['FIB_5_SMA'], label='Micro (8)', color='cyan', linestyle=':')
        plt.plot(zoom_df.index, zoom_df['FIB_7_SMA'], label='Short (21)', color='lime', linestyle='--')
        plt.plot(zoom_df.index, zoom_df['FIB_9_SMA'], label='k (55)', color='orange', linewidth=2)
        plt.plot(zoom_df.index, zoom_df['FIB_11_SMA'], label='k+1 (144)', color='red', linewidth=2)
        plt.plot(zoom_df.index, zoom_df['FIB_13_SMA'], label='k+2 (377)', color='magenta', linewidth=3)
        
        # Mark Trigger
        plt.scatter(best_trigger, df.loc[best_trigger, 'close'] - df.loc[best_trigger, 'ATR_14'], 
                    color='yellow', s=300, marker='^', zorder=5, label='Cross Propagation = 3 (The Snap)')
                    
        # Arrow pointing to 377
        plt.annotate('Violent Reversion to k+2', 
             xy=(best_trigger + pd.Timedelta(hours=24), df.loc[best_trigger + pd.Timedelta(hours=24), 'FIB_13_SMA']), 
             xytext=(best_trigger, df.loc[best_trigger, 'close']),
             arrowprops=dict(facecolor='yellow', shrink=0.05, width=2, headwidth=10),
             fontsize=12, color='yellow', weight='bold')
             
        plt.title(f"Rubber Band Snap Mechanics: Cross Propagation Complete\n(Order: 377 > 144 > 55 -> Micro Crosses Trigger Snap)", fontsize=16)
        plt.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
        plt.grid(True, alpha=0.2)
        plt.gca().set_facecolor('black')
        plt.tight_layout()
        plt.savefig("rubber_band_snap_case.png", dpi=300)
        print("Saved rubber_band_snap_case.png")
    else:
        print("No perfect trigger found in this dataset.")

if __name__ == '__main__':
    main()
