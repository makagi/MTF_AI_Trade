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

def add_bb_and_velocity(df, periods_dict):
    for label, p in periods_dict.items():
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'BB_U_{label}'] = upper
        df[f'BB_L_{label}'] = lower
        df[f'BW_{label}'] = (upper - lower) / df['close']
        df[f'VEL_BW_{label}'] = df[f'BW_{label}'].diff(24)
    return df

def calculate_afs(df, periods):
    # True Fractal AFS: %k=fib, %d=fib
    for p in periods:
        highest_high = df['high'].rolling(p).max()
        lowest_low = df['low'].rolling(p).min()
        k = 100 * ((df['close'] - lowest_low) / (highest_high - lowest_low + 1e-8))
        d = k.rolling(p).mean()  # FIXED: Smooth by the same Fibonacci period 'p'
        df[f'AFS_{p}'] = d
    return df

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, 16)
    
    fib_periods = get_fib_periods()
    df = add_bb_and_velocity(df, fib_periods)
    
    # AFS for k=7(21), k=9(55), k=11(144), k=13(377)
    df = calculate_afs(df, [21, 55, 144, 377])
    
    # Cross Prop Score
    score = (df['FIB_5_SMA'] > df['FIB_7_SMA']).astype(int) + \
            (df['close'] > df['FIB_9_SMA']).astype(int) + \
            (df['FIB_7_SMA'] > df['FIB_9_SMA']).astype(int)
    df['CROSS_PROP_SCORE'] = score
    
    # Target date: The legendary 2022-09-06 Nested Wait / Resolution Case
    target_date = pd.to_datetime('2022-09-06 10:00:00')
    start_date = target_date - pd.Timedelta(days=10)
    end_date = target_date + pd.Timedelta(days=5)
    zoom = df.loc[start_date:end_date]
    if zoom.empty or pd.isna(zoom.loc[target_date, 'close']):
        # Fallback to an available index
        target_date = df.index[len(df)//2] 
        # Actually let's just use 2022-09-06 if 2025 is missing
        target_date = pd.to_datetime('2022-09-06 10:00:00')
        start_date = target_date - pd.Timedelta(days=10)
        end_date = target_date + pd.Timedelta(days=5)
        zoom = df.loc[start_date:end_date]
    
    fig, axes = plt.subplots(4, 1, figsize=(20, 24), gridspec_kw={'height_ratios': [4, 2, 2, 1]}, sharex=True)
    
    # === Row 1: The Topology Map ===
    ax1 = axes[0]
    ax1.plot(zoom.index, zoom['close'], color='white', linewidth=1.5, label='Close')
    # The Wall Cloud (between 55 and 144)
    ax1.fill_between(zoom.index, zoom['FIB_9_SMA'], zoom['FIB_11_SMA'], color='purple', alpha=0.2, label='The Wall (55 to 144)')
    ax1.plot(zoom.index, zoom['FIB_13_SMA'], color='red', linewidth=2, label='Macro Floor (377 SMA)')
    ax1.plot(zoom.index, zoom['BB_L_k=13'], color='orange', linestyle='--', linewidth=2, label='Macro BB Lower (377)')
    
    ax1.scatter(target_date, zoom.loc[target_date, 'close'], color='lime', s=400, marker='^', zorder=10, label='Ultimate Resonance Ignition')
    
    ax1.set_title("Row 1: The Topology Map (Space & Trend)", fontsize=18, color='white')
    ax1.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax1.grid(True, alpha=0.2)
    ax1.set_facecolor('black')
    
    # === Row 2: The Momentum Engine (AFS) ===
    ax2 = axes[1]
    ax2.plot(zoom.index, zoom['AFS_21'], color='cyan', label='Micro AFS (21)', linewidth=1)
    ax2.plot(zoom.index, zoom['AFS_55'], color='lime', label='Short AFS (55)', linewidth=1)
    ax2.plot(zoom.index, zoom['AFS_144'], color='purple', label='Mid AFS (144)', linewidth=2)
    ax2.plot(zoom.index, zoom['AFS_377'], color='red', label='Macro AFS (377)', linewidth=2)
    ax2.axhline(20, color='yellow', linestyle='--', alpha=0.5)
    
    # Mark AFS Reversion
    ax2.scatter(target_date, zoom.loc[target_date, 'AFS_55'], color='lime', s=200, marker='^', zorder=10)
    
    ax2.set_title("Row 2: The Momentum Engine (MTF AFS Resonance)", fontsize=16, color='white')
    ax2.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax2.grid(True, alpha=0.2)
    ax2.set_facecolor('black')
    
    # === Row 3: The Volatility Engine (Time-to-Resolution) ===
    ax3 = axes[2]
    ax3.plot(zoom.index, zoom['BW_k=13'], color='magenta', linewidth=2, label='Macro Bandwidth (377)')
    ax3_twin = ax3.twinx()
    ax3_twin.plot(zoom.index, zoom['VEL_BW_k=13'], color='cyan', linestyle=':', linewidth=2, label='Velocity of Squeeze')
    ax3_twin.axhline(0, color='yellow', linestyle='-', alpha=0.5)
    
    # Highlight the squeeze apex zone
    apex_zone = (zoom['VEL_BW_k=13'] > -0.002) & (zoom['VEL_BW_k=13'] < 0.002)
    ax3.fill_between(zoom.index, ax3.get_ylim()[0], ax3.get_ylim()[1], where=apex_zone, color='lime', alpha=0.1, label='Resolution Apex Zone')
    
    ax3.set_title("Row 3: The Volatility Engine (Time-to-Resolution & Squeeze Apex)", fontsize=16, color='white')
    ax3.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax3_twin.legend(loc='upper right', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax3.grid(True, alpha=0.2)
    ax3.set_facecolor('black')
    
    # === Row 4: The Execution Engine (Cross Prop) ===
    ax4 = axes[3]
    ax4.step(zoom.index, zoom['CROSS_PROP_SCORE'], where='post', color='yellow', linewidth=2, label='Cross Prop Score (0-3)')
    ax4.fill_between(zoom.index, zoom['CROSS_PROP_SCORE'], 0, step='post', color='yellow', alpha=0.3)
    ax4.set_yticks([0, 1, 2, 3])
    ax4.axhline(2, color='white', linestyle='--', alpha=0.5)
    
    ax4.set_title("Row 4: The Execution Engine (Micro Propagation)", fontsize=16, color='white')
    ax4.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax4.grid(True, alpha=0.2)
    ax4.set_facecolor('black')
    
    # Vertical line connecting all rows at ignition
    for ax in axes:
        ax.axvline(target_date, color='lime', linestyle='-', linewidth=2, zorder=0)
        
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    
    plt.suptitle("THE GOD-MODE DASHBOARD: Multidimensional Resonance", fontsize=24, color='white', y=0.92)
    fig.patch.set_facecolor('#111111')
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig("ultimate_god_mode_dashboard.png", dpi=200, facecolor=fig.get_facecolor())
    print("Saved ultimate_god_mode_dashboard.png")

if __name__ == '__main__':
    main()
