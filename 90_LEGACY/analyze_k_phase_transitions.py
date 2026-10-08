import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
from matplotlib.colors import ListedColormap
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def get_fib_periods():
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
        'k=16 (1597)': 1597
    }

def add_scale_invariant_phases(df, periods_dict, slope_threshold=0.5):
    for label, p in periods_dict.items():
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        
        df[f'SMA_{p}'] = sma
        pctb = (df['close'] - lower) / (upper - lower + 1e-8)
        
        # Scale-Invariant Metrics: Shift and Roll by 'p' itself
        # % change over p hours
        slope = (sma - sma.shift(p)) / sma.shift(p) * 100
        avg_pctb = pctb.rolling(p).mean()
        
        # Phase Classification
        # 1 = Uptrend, -1 = Downtrend, 0 = Range
        phase = np.zeros(len(df))
        uptrend = (slope > slope_threshold) & (avg_pctb > 0.5)
        downtrend = (slope < -slope_threshold) & (avg_pctb < 0.5)
        
        phase[uptrend] = 1
        phase[downtrend] = -1
        # Everything else remains 0 (Range)
        
        # Set NaNs at the beginning to NaN
        phase[:p*2] = np.nan 
        
        df[f'PHASE_{p}'] = phase
        
    return df

def plot_colored_sma(ax, df, p, label):
    # Scatter plot approach for changing line color
    phase_col = df[f'PHASE_{p}']
    sma_col = df[f'SMA_{p}']
    
    # Uptrend
    mask_up = phase_col == 1
    ax.scatter(df.index[mask_up], sma_col[mask_up], color='lime', s=5, label=f'{p} (Up)' if not mask_up.empty else "")
    
    # Downtrend
    mask_down = phase_col == -1
    ax.scatter(df.index[mask_down], sma_col[mask_down], color='red', s=5, label=f'{p} (Down)' if not mask_down.empty else "")
    
    # Range
    mask_range = phase_col == 0
    ax.scatter(df.index[mask_range], sma_col[mask_range], color='gray', s=5, label=f'{p} (Range)' if not mask_range.empty else "")

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    
    fib_periods = get_fib_periods()
    print("Calculating Scale-Invariant Phases...")
    df = add_scale_invariant_phases(df, fib_periods, slope_threshold=0.5)
    
    # Let's take a massive 6-month window to see the ripple effect and phase shifts
    # Using the 2022-09-06 event as the center point (since we know it was a range resolution)
    target_date = pd.to_datetime('2022-09-06 10:00:00')
    start_date = target_date - pd.Timedelta(days=120)
    end_date = target_date + pd.Timedelta(days=30)
    
    zoom = df.loc[start_date:end_date]
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 16), gridspec_kw={'height_ratios': [2, 1]}, sharex=True)
    
    # === Subplot 1: Colored Topology Map ===
    ax1.plot(zoom.index, zoom['close'], color='white', linewidth=1, alpha=0.5, label='Close')
    
    # Plot 55, 144, 377 as colored SMAs
    plot_colored_sma(ax1, zoom, 55, "55")
    plot_colored_sma(ax1, zoom, 144, "144")
    plot_colored_sma(ax1, zoom, 377, "377")
    
    ax1.set_title("Row 1: The Colored Topology Map\nNotice how price bounces cleanly off Gray (Range) lines and respects Green/Red (Trend) lines.", fontsize=18, color='white')
    ax1.grid(True, alpha=0.2)
    ax1.set_facecolor('black')
    
    # === Subplot 2: Phase Transition Heatmap ===
    phase_cols = [f'PHASE_{p}' for p in fib_periods.values()]
    # Reverse to put 1597 at top, 21 at bottom
    phase_cols.reverse()
    
    # Downsample to 12h for cleaner heatmap
    zoom_resampled = zoom.resample('12h').median()
    phase_matrix = zoom_resampled[phase_cols].T
    
    # Custom colormap: -1=Red, 0=Gray, 1=Green
    cmap = ListedColormap(['#ff4444', '#888888', '#44ff44'])
    
    sns.heatmap(phase_matrix, cmap=cmap, ax=ax2, cbar=False, vmin=-1, vmax=1)
    
    ax2.set_title("Row 2: Phase Transition Heatmap (The Domino Effect)\nObserve how trend reversals (Green/Red) start at the bottom (k=7) and ripple diagonally upwards to macro levels.", fontsize=18, color='white')
    ax2.set_ylabel("Fractal Layer (k)", color='white')
    
    # Fix y-tick labels
    labels = list(fib_periods.keys())
    labels.reverse()
    ax2.set_yticklabels(labels, rotation=0, color='white')
    
    # Format x-axis
    x_dates = zoom_resampled.index.strftime('%Y-%m-%d')
    ax2.set_xticks(np.arange(len(x_dates))[::14])
    ax2.set_xticklabels(x_dates[::14], rotation=45, color='white')
    ax2.set_facecolor('black')
    
    fig.patch.set_facecolor('#111111')
    plt.tight_layout()
    plt.savefig("k_phase_transitions.png", dpi=300, facecolor=fig.get_facecolor())
    print("Saved k_phase_transitions.png")

if __name__ == '__main__':
    main()
