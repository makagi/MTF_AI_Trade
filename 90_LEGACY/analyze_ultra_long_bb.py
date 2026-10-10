import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

def add_bb_features(df, periods):
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        df[f'BB_U_{p}'] = sma + 2 * std
        df[f'BB_L_{p}'] = sma - 2 * std
        df[f'BB_M_{p}'] = sma
        df[f'BB_PCTB_{p}'] = (df['close'] - df[f'BB_L_{p}']) / (df[f'BB_U_{p}'] - df[f'BB_L_{p}'] + 1e-8)
        df[f'BB_BW_{p}'] = (df[f'BB_U_{p}'] - df[f'BB_L_{p}']) / df['close']
    return df

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    
    # We need ultra-long periods: 377, 610, 1597
    print("Calculating Ultra-Long BBs...")
    df = add_bb_features(df, [377, 610, 1597])
    
    # -------------------------------------------------------------
    # Case 1: 2024-01-20 (The Dud) - The Macro Gravity Cycle
    # -------------------------------------------------------------
    target_1 = pd.to_datetime('2024-01-20 23:00:00')
    start_1 = target_1 - pd.Timedelta(days=120) # Look back 4 months
    end_1 = target_1 + pd.Timedelta(days=10)
    
    zoom_1 = df.loc[start_1:end_1]
    
    fig1, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 16), gridspec_kw={'height_ratios': [2, 1, 1]})
    
    # Main Chart
    ax1.plot(zoom_1.index, zoom_1['close'], label='Close Price', color='white', linewidth=1)
    ax1.plot(zoom_1.index, zoom_1['BB_U_1597'], color='orange', linewidth=2, label='1597-BB Upper')
    ax1.plot(zoom_1.index, zoom_1['BB_L_1597'], color='orange', linewidth=2, linestyle='--', label='1597-BB Lower')
    ax1.fill_between(zoom_1.index, zoom_1['BB_U_1597'], zoom_1['BB_L_1597'], color='orange', alpha=0.1)
    
    # Find prior Upper Touch
    upper_touch_idx = zoom_1['BB_PCTB_1597'].idxmax()
    ax1.scatter(upper_touch_idx, zoom_1.loc[upper_touch_idx, 'close'], color='red', s=300, marker='X', zorder=5, label='Macro Ceiling Touch')
    
    ax1.scatter(target_1, zoom_1.loc[target_1, 'close'], color='yellow', s=300, marker='v', zorder=5, label='The Failed Trigger')
    
    ax1.set_title("Hypothesis 1: The Macro Gravity Cycle (1597-BB)\nFalling from Ceiling to Floor", fontsize=18)
    ax1.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax1.grid(True, alpha=0.2)
    ax1.set_facecolor('black')
    
    # Subplot: %B 1597
    ax2.plot(zoom_1.index, zoom_1['BB_PCTB_1597'], color='orange', linewidth=2, label='1597-BB %B')
    ax2.axhline(1.0, color='red', linestyle='--', linewidth=2)
    ax2.axhline(0.0, color='lime', linestyle='--', linewidth=2)
    ax2.scatter(upper_touch_idx, zoom_1.loc[upper_touch_idx, 'BB_PCTB_1597'], color='red', s=200, marker='X', zorder=5)
    ax2.scatter(target_1, zoom_1.loc[target_1, 'BB_PCTB_1597'], color='yellow', s=200, marker='v', zorder=5)
    ax2.set_title("Macro %B: Journey from 1.0 (Ceiling) to 0.0 (Floor)", fontsize=14)
    ax2.legend(loc='upper right', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax2.grid(True, alpha=0.2)
    ax2.set_facecolor('black')
    
    # Subplot: Bandwidth 1597
    ax3.plot(zoom_1.index, zoom_1['BB_BW_1597'], color='magenta', linewidth=2, label='1597-BB Bandwidth')
    ax3.axvline(upper_touch_idx, color='red', linestyle=':', alpha=0.5)
    ax3.axvline(target_1, color='yellow', linestyle=':', alpha=0.5)
    ax3.set_title("Macro Volatility Expansion (Expanding Downwards)", fontsize=14)
    ax3.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax3.grid(True, alpha=0.2)
    ax3.set_facecolor('black')
    
    plt.tight_layout()
    plt.savefig("snap_bb_hypothesis_3_macro_cycle.png", dpi=300)
    print("Saved snap_bb_hypothesis_3_macro_cycle.png")
    
    # -------------------------------------------------------------
    # Case 2: 2022-09-06 (The Struggle) - The Nested Wait
    # -------------------------------------------------------------
    target_2 = pd.to_datetime('2022-09-06 10:00:00')
    start_2 = target_2 - pd.Timedelta(days=60) # Look back 2 months
    end_2 = target_2 + pd.Timedelta(days=10)
    
    zoom_2 = df.loc[start_2:end_2]
    
    fig2, (ax4, ax5) = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [2, 1]})
    
    # Main Chart
    ax4.plot(zoom_2.index, zoom_2['close'], label='Close Price', color='white', linewidth=1)
    
    # 610-BB
    ax4.plot(zoom_2.index, zoom_2['BB_U_610'], color='cyan', linewidth=2, linestyle='--', label='610-BB Upper')
    ax4.plot(zoom_2.index, zoom_2['BB_L_610'], color='cyan', linewidth=2, linestyle='--', label='610-BB Lower')
    
    # 377-BB
    ax4.plot(zoom_2.index, zoom_2['BB_U_377'], color='red', linewidth=1, label='377-BB Upper')
    ax4.plot(zoom_2.index, zoom_2['BB_L_377'], color='red', linewidth=1, label='377-BB Lower')
    ax4.fill_between(zoom_2.index, zoom_2['BB_U_377'], zoom_2['BB_L_377'], color='red', alpha=0.1)
    
    ax4.scatter(target_2, zoom_2.loc[target_2, 'close'], color='yellow', s=300, marker='v', zorder=5, label='Trigger')
    
    ax4.set_title("Hypothesis 2: The Nested Squeeze Wait (377 vs 610)", fontsize=18)
    ax4.legend(loc='upper right', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax4.grid(True, alpha=0.2)
    ax4.set_facecolor('black')
    
    # Subplot: Bandwidths comparison
    ax5.plot(zoom_2.index, zoom_2['BB_BW_610'], color='cyan', linewidth=2, label='610-BB Bandwidth (Still Wide)')
    ax5.plot(zoom_2.index, zoom_2['BB_BW_377'], color='red', linewidth=2, label='377-BB Bandwidth (Squeezed)')
    ax5.scatter(target_2, zoom_2.loc[target_2, 'BB_BW_610'], color='yellow', s=200, marker='v', zorder=5)
    
    ax5.set_title("Nested Bandwidth Comparison (Waiting for the higher timeframe to contract)", fontsize=14)
    ax5.legend(loc='upper right', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax5.grid(True, alpha=0.2)
    ax5.set_facecolor('black')
    ax5.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    plt.savefig("snap_bb_hypothesis_4_nested_wait.png", dpi=300)
    print("Saved snap_bb_hypothesis_4_nested_wait.png")

if __name__ == '__main__':
    main()
