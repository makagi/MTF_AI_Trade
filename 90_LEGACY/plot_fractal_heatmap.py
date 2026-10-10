import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from src.data_loader import load_1h_data
from src.features import calculate_fib_features
from src.config import MAX_FIB_INDEX_1H

def run():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    
    fib_ks = [6, 7, 8, 9, 10, 11, 12]
    fib_labels = [21, 34, 55, 89, 144, 233, 377]
    
    heatmap_data = []
    
    for k, label in zip(fib_ks, fib_labels):
        # Calculate BB lower
        std = df['close'].rolling(label, min_periods=1).std().bfill()
        sma = df[f'FIB_{k}_SMA']
        bb_lower = sma - 2.0 * std
        
        # Calculate 1st derivative (momentum)
        momentum = bb_lower.diff(1)
        
        # Normalize with rolling Z-score
        momentum_z = momentum / momentum.rolling(window=100, min_periods=10).std().bfill()
        
        # Clip for stable colormap (-3 to +3)
        momentum_z = momentum_z.clip(-3, 3)
        heatmap_data.append(momentum_z)
    
    # Create target window
    target_date = pd.to_datetime('2025-11-21 08:00:00')
    entry_idx = df.index.get_loc(target_date)
    start_idx = max(0, entry_idx - 60)
    end_idx = min(len(df) - 1, entry_idx + 60)
    
    window_df = df.iloc[start_idx:end_idx]
    
    # Extract heatmap window (Reverse order so 377 is at top, 21 at bottom)
    heatmap_window = [series.iloc[start_idx:end_idx] for series in heatmap_data]
    df_heatmap = pd.DataFrame(heatmap_window, index=fib_labels).iloc[::-1]
    
    # Format x-axis labels
    x_labels = [dt.strftime('%m-%d %H') if i % 12 == 0 else '' for i, dt in enumerate(window_df.index)]
    
    # Plotting
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [1, 1.5]}, sharex=False)
    
    # 1. Price Panel
    ax1.vlines(range(len(window_df)), window_df['low'], window_df['high'], color='black', alpha=0.5)
    ax1.plot(range(len(window_df)), window_df['close'], color='black', label='Close')
    ax1.set_title(f"Price Action during Major Crash (Centered at {target_date})", fontsize=14)
    ax1.set_xticks(range(len(window_df)))
    ax1.set_xticklabels(x_labels, rotation=45)
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # 2. Fractal Momentum Heatmap
    sns.heatmap(
        df_heatmap, 
        ax=ax2, 
        cmap='RdYlGn', 
        center=0, 
        cbar_kws={'label': 'Normalized BB Momentum (Z-score)'},
        linewidths=0,
        xticklabels=x_labels
    )
    
    ax2.set_title("Fractal BB Lower Momentum: Diagonal Propagation of Bottoming Out (Lead/Lag)", fontsize=14)
    ax2.set_ylabel("Fibonacci Period (Hours)", fontsize=12)
    ax2.set_xlabel("Time", fontsize=12)
    
    # Draw an arrow showing the diagonal wave of bottoming out
    # Find the approximate x-index of the absolute bottom
    min_price_idx = np.argmin(window_df['low'].values)
    ax2.annotate('', xy=(min_price_idx + 24, 0.5), xytext=(min_price_idx + 2, 6.5),
                arrowprops=dict(facecolor='black', edgecolor='white', width=3, headwidth=10, alpha=0.7))
    ax2.text(min_price_idx + 13, 3, "Traction Pulling Up\n(Diagonal Wave)", color='black', fontsize=12, 
             fontweight='bold', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))
    
    plt.tight_layout()
    os.makedirs("results/fractal", exist_ok=True)
    filepath = "results/fractal/fractal_momentum_heatmap.png"
    plt.savefig(filepath)
    plt.close()
    print(f"Saved {filepath}")

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings('ignore')
    run()
