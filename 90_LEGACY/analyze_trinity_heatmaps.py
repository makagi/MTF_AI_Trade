import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
from matplotlib.colors import ListedColormap

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

def calculate_trinity_features(df, periods_dict):
    for label, p in periods_dict.items():
        # 1. Volatility (Bandwidth)
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        
        bw = (upper - lower) / df['close']
        df[f'BW_{p}'] = bw
        
        # 2. Momentum (AFS)
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
        
        # 3. Phase (Scale Invariant)
        pctb = (df['close'] - lower) / (upper - lower + 1e-8)
        slope = (sma - sma.shift(p)) / sma.shift(p) * 100
        avg_pctb = pctb.rolling(p).mean()
        
        phase = np.zeros(len(df))
        uptrend = (slope > 0.5) & (avg_pctb > 0.5)
        downtrend = (slope < -0.5) & (avg_pctb < 0.5)
        
        phase[uptrend] = 1
        phase[downtrend] = -1
        phase[:p*2] = np.nan 
        
        df[f'PHASE_{p}'] = phase
        
    return df

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    
    fib_periods = get_fib_periods()
    print("Calculating Trinity Features...")
    df = calculate_trinity_features(df, fib_periods)
    
    # Target window: A known massive breakout/resolution event
    target_date = pd.to_datetime('2022-09-06 10:00:00')
    start_date = target_date - pd.Timedelta(days=60)
    end_date = target_date + pd.Timedelta(days=30)
    
    zoom = df.loc[start_date:end_date]
    zoom_resampled = zoom.resample('12h').median()
    
    fig, axes = plt.subplots(3, 1, figsize=(18, 18), sharex=True)
    
    y_labels = list(fib_periods.keys())
    y_labels.reverse()  # 1597 at top, 21 at bottom
    
    x_dates = zoom_resampled.index.strftime('%m-%d')
    xticks_loc = np.arange(len(x_dates))[::14]
    xticks_labels = x_dates[::14]
    
    # === Heatmap 1: Momentum (AFS) ===
    afs_cols = [f'AFS_{p}' for p in fib_periods.values()]
    afs_cols.reverse()
    afs_matrix = zoom_resampled[afs_cols].T
    
    sns.heatmap(afs_matrix, cmap='coolwarm', ax=axes[0], cbar=True, vmin=0, vmax=100)
    axes[0].set_title("1. Momentum Engine Heatmap (AFS)\nObserve how momentum turns (Blue to Red) FIRST, starting from the bottom.", fontsize=14, color='white')
    axes[0].set_yticklabels(y_labels, rotation=0, color='white')
    
    # === Heatmap 2: Volatility (Bandwidth Compression) ===
    bw_cols = [f'BW_{p}' for p in fib_periods.values()]
    bw_cols.reverse()
    bw_matrix = zoom_resampled[bw_cols].T
    
    # Row-wise Min-Max normalization so squeeze is black (0) and expansion is yellow (1) for ALL layers
    bw_matrix_norm = bw_matrix.apply(lambda row: (row - row.min()) / (row.max() - row.min() + 1e-8), axis=1)
    
    sns.heatmap(bw_matrix_norm, cmap='inferno', ax=axes[1], cbar=True, vmin=0, vmax=1)
    axes[1].set_title("2. Volatility Engine Heatmap (Bandwidth Z-Score)\nBlack = Squeeze, Yellow = Expansion. Observe how all layers turn Black BEFORE the trend ignites.", fontsize=14, color='white')
    axes[1].set_yticklabels(y_labels, rotation=0, color='white')
    
    # === Heatmap 3: Trend Phase ===
    phase_cols = [f'PHASE_{p}' for p in fib_periods.values()]
    phase_cols.reverse()
    phase_matrix = zoom_resampled[phase_cols].T
    
    cmap_phase = ListedColormap(['#ff4444', '#888888', '#44ff44'])
    sns.heatmap(phase_matrix, cmap=cmap_phase, ax=axes[2], cbar=False, vmin=-1, vmax=1)
    axes[2].set_title("3. Trend Phase Heatmap (Direction)\nRed=Down, Gray=Range, Green=Up. The final confirmation. Enter when micro turns Green while macro is Gray.", fontsize=14, color='white')
    axes[2].set_yticklabels(y_labels, rotation=0, color='white')
    
    for ax in axes:
        ax.set_xticks(xticks_loc)
        ax.set_xticklabels(xticks_labels, rotation=0, color='white')
        ax.set_facecolor('#111111')
    
    fig.patch.set_facecolor('#111111')
    plt.tight_layout()
    plt.savefig("trinity_heatmaps.png", dpi=300, facecolor=fig.get_facecolor())
    print("Saved trinity_heatmaps.png")

if __name__ == '__main__':
    main()
