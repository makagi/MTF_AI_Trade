import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def get_fib_periods():
    # k=7 to 17
    return {
        'k=7 (21)': 21,
        'k=8 (34)': 34,
        'k=9 (55)': 55,
        'k=10 (89)': 89,
        'k=11 (144)': 144,
        'k=12 (233)': 233,
        'k=13 (377)': 377,
        'k=14 (610)': 610,
        'k=15 (987)': 987,
        'k=16 (1597)': 1597,
        'k=17 (2584)': 2584
    }

def add_bb_features(df, periods_dict):
    for label, p in periods_dict.items():
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'BW_{label}'] = (upper - lower) / df['close']
        df[f'PCTB_{label}'] = (df['close'] - lower) / (upper - lower + 1e-8)
    return df

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    
    fib_periods = get_fib_periods()
    print("Calculating Generalized BB Features across all k layers...")
    df = add_bb_features(df, fib_periods)
    
    # Target date: 2022-09-06 (The Struggle / Nested Wait)
    # Let's visualize 1 month before to 1 week after
    target_date = pd.to_datetime('2022-09-06 10:00:00')
    start_date = target_date - pd.Timedelta(days=45)
    end_date = target_date + pd.Timedelta(days=15)
    
    zoom = df.loc[start_date:end_date]
    
    # Extract matrices for Heatmap
    bw_cols = [f'BW_{label}' for label in fib_periods.keys()]
    pctb_cols = [f'PCTB_{label}' for label in fib_periods.keys()]
    
    # Reverse the order so k=17 is at the top, k=7 is at the bottom
    bw_cols.reverse()
    pctb_cols.reverse()
    
    # Downsample to 12h for cleaner heatmap display over 2 months
    zoom_resampled = zoom.resample('12h').mean()
    
    bw_matrix = zoom_resampled[bw_cols].T
    pctb_matrix = zoom_resampled[pctb_cols].T
    
    # Create the plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 12), sharex=True)
    
    # Subplot 1: Bandwidth Squeeze Heatmap
    # We normalize each row (each k) to its own min-max over this window to show relative squeeze
    bw_norm = bw_matrix.apply(lambda x: (x - x.min()) / (x.max() - x.min()), axis=1)
    
    sns.heatmap(bw_norm, cmap='magma', ax=ax1, cbar_kws={'label': 'Normalized Bandwidth (Dark=Squeezed)'})
    ax1.set_title("Generalized Nested Squeeze Heatmap (Bandwidth)\nDark = Squeezed, Light = Expanding. Notice how lower layers squeeze but upper layers remain wide.", fontsize=16)
    ax1.set_ylabel("Fractal Layer (k)")
    
    # Subplot 2: Gravity / %B Heatmap
    # %B is naturally 0 to 1. Red = Floor (0.0), Blue = Ceiling (1.0)
    sns.heatmap(pctb_matrix, cmap='coolwarm_r', vmin=0, vmax=1, center=0.5, ax=ax2, cbar_kws={'label': '%B (Red=0.0/Floor, Blue=1.0/Ceiling)'})
    ax2.set_title("Generalized Macro Gravity Heatmap (%B)\nRed = Floor (Oversold), Blue = Ceiling (Overbought). Notice how lower layers hit the floor while upper layers are still falling.", fontsize=16)
    ax2.set_ylabel("Fractal Layer (k)")
    
    # Format x-axis labels to dates
    x_dates = zoom_resampled.index.strftime('%Y-%m-%d')
    ax2.set_xticks(np.arange(len(x_dates))[::10])
    ax2.set_xticklabels(x_dates[::10], rotation=45)
    
    # Mark the trigger event
    try:
        t_loc = zoom_resampled.index.get_loc(target_date, method='nearest')
        ax1.axvline(t_loc, color='yellow', linestyle='--', linewidth=3, label='Ultimate Snap Trigger')
        ax2.axvline(t_loc, color='yellow', linestyle='--', linewidth=3, label='Ultimate Snap Trigger')
        ax1.legend()
        ax2.legend()
    except Exception as e:
        pass
        
    plt.tight_layout()
    plt.savefig("generalized_fractal_heatmap.png", dpi=300)
    print("Saved generalized_fractal_heatmap.png")

if __name__ == '__main__':
    main()
