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
    return df

def plot_bb_case(df, target_date, title_prefix, filename, days_before=5, days_after=5):
    start_date = target_date - pd.Timedelta(days=days_before)
    end_date = target_date + pd.Timedelta(days=days_after)
    zoom_df = df.loc[start_date:end_date]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [3, 1]})
    
    # --- Main Chart ---
    ax1.plot(zoom_df.index, zoom_df['close'], label='Close Price', color='white', linewidth=2)
    
    # 21 BB (Tactical)
    ax1.plot(zoom_df.index, zoom_df['BB_U_21'], color='cyan', linestyle=':', alpha=0.6)
    ax1.plot(zoom_df.index, zoom_df['BB_L_21'], color='cyan', linestyle=':', alpha=0.6, label='21-BB (Tactical)')
    ax1.fill_between(zoom_df.index, zoom_df['BB_U_21'], zoom_df['BB_L_21'], color='cyan', alpha=0.05)
    
    # 144 BB (Structural)
    ax1.plot(zoom_df.index, zoom_df['BB_U_144'], color='purple', linestyle='--', alpha=0.8)
    ax1.plot(zoom_df.index, zoom_df['BB_L_144'], color='purple', linestyle='--', alpha=0.8, label='144-BB (Structural)')
    ax1.fill_between(zoom_df.index, zoom_df['BB_U_144'], zoom_df['BB_L_144'], color='purple', alpha=0.1)
    
    # 377 BB (Macro)
    ax1.plot(zoom_df.index, zoom_df['BB_U_377'], color='red', linewidth=2)
    ax1.plot(zoom_df.index, zoom_df['BB_L_377'], color='red', linewidth=2, label='377-BB (Macro absolute bound)')
    ax1.plot(zoom_df.index, zoom_df['BB_M_377'], color='red', linestyle='-.', alpha=0.5)
    
    ax1.scatter(target_date, zoom_df.loc[target_date, 'close'], color='yellow', s=300, marker='v', zorder=5, label='Ultimate Snap Trigger')
    
    # Find lowest post-trigger bottom if there's a dip (for Case 2)
    post_trigger = zoom_df.loc[target_date:target_date + pd.Timedelta(days=days_after//2)]
    bottom_idx = post_trigger['low'].idxmin()
    bottom_val = post_trigger.loc[bottom_idx, 'low']
    if bottom_idx != target_date:
        ax1.scatter(bottom_idx, bottom_val, color='lime', s=300, marker='^', zorder=6, label='Actual Bottom')
    
    ax1.set_title(f"{title_prefix}\nDate: {target_date.strftime('%Y-%m-%d %H:%M')}", fontsize=18)
    ax1.legend(loc='upper right', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax1.grid(True, alpha=0.2)
    ax1.set_facecolor('black')
    
    # Calculate Macro Lower BB Slope
    t_loc = zoom_df.index.get_loc(target_date)
    lookback = max(0, t_loc - 24)
    macro_lbb_slope = zoom_df['BB_L_377'].iloc[t_loc] - zoom_df['BB_L_377'].iloc[lookback]
    
    stats = (
        f"377-BB Lower Bound 24h Slope: {'Expanding Down' if macro_lbb_slope < 0 else 'Rising/Flat'} ({macro_lbb_slope:.2f})\n"
        f"144-BB %B at Trigger: {zoom_df.loc[target_date, 'BB_PCTB_144']:.3f}\n"
        f"377-BB %B at Trigger: {zoom_df.loc[target_date, 'BB_PCTB_377']:.3f}\n"
    )
    if bottom_idx != target_date:
        stats += f"377-BB %B at Bottom: {zoom_df.loc[bottom_idx, 'BB_PCTB_377']:.3f}"
        
    props = dict(boxstyle='round', facecolor='black', alpha=0.8, edgecolor='white')
    ax1.text(0.02, 0.95, stats, transform=ax1.transAxes, fontsize=14,
            verticalalignment='top', bbox=props, color='yellow', weight='bold')
    
    # --- Subplot (%B Oscillator) ---
    ax2.plot(zoom_df.index, zoom_df['BB_PCTB_144'], color='purple', label='144-BB %B')
    ax2.plot(zoom_df.index, zoom_df['BB_PCTB_377'], color='red', linewidth=2, label='377-BB %B')
    ax2.axhline(0.0, color='yellow', linestyle='--', linewidth=2, label='Lower Bound Touch (0.0)')
    ax2.axhline(1.0, color='yellow', linestyle='--', alpha=0.5)
    
    ax2.scatter(target_date, zoom_df.loc[target_date, 'BB_PCTB_377'], color='yellow', s=200, marker='v', zorder=5)
    if bottom_idx != target_date:
        ax2.scatter(bottom_idx, zoom_df.loc[bottom_idx, 'BB_PCTB_377'], color='lime', s=200, marker='^', zorder=6)
        
    ax2.set_title("MTF %B Oscillator", fontsize=14)
    ax2.legend(loc='upper right', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    ax2.grid(True, alpha=0.2)
    ax2.set_facecolor('black')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    print(f"Saved {filename}")

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    print("Calculating MTF Bollinger Bands...")
    df = add_bb_features(df, [21, 55, 144, 377])
    
    # Case 1: 2024-01-20 (The Dud)
    plot_bb_case(df, pd.to_datetime('2024-01-20 23:00:00'), 
                 "BB Hypothesis 1: The Dud (The Trapdoor Opening)", 
                 "snap_bb_hypothesis_1_dud.png", days_before=10, days_after=5)
                 
    # Case 2: 2022-09-06 (The Struggle / Average)
    plot_bb_case(df, pd.to_datetime('2022-09-06 10:00:00'), 
                 "BB Hypothesis 2: The Struggle (Reaching for Macro Bounds)", 
                 "snap_bb_hypothesis_2_struggle.png", days_before=5, days_after=5)

if __name__ == '__main__':
    main()
