import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import os

from src.data_loader import load_1h_data

def main():
    print("Loading data...")
    df = load_1h_data()
    
    # Calculate Standard Stochastics (14, 3)
    p = 14
    rolling_min = df['low'].rolling(window=p).min()
    rolling_max = df['high'].rolling(window=p).max()
    
    # %K (Fast)
    df['stoch_k'] = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
    
    # %D (Slow / stoch_d)
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
    
    # Identify whipsaws (Crossing > 80 then dropping below 80 quickly)
    df['overbought'] = df['stoch_d'] > 80
    df['oversold'] = df['stoch_d'] < 20
    
    # Count frequency of crossings
    cross_up_80 = (df['stoch_d'] > 80) & (df['stoch_d'].shift(1) <= 80)
    cross_down_20 = (df['stoch_d'] < 20) & (df['stoch_d'].shift(1) >= 20)
    total_false_signals = cross_up_80.sum() + cross_down_20.sum()
    
    print(f"Total overbought/oversold crossings (potential whipsaws): {total_false_signals}")
    
    # Plotting a noisy segment
    plot_start = '2022-01-01'
    plot_end = '2022-02-15'
    df_plot = df.loc[plot_start:plot_end]
    
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    # Price
    ax1.plot(df_plot.index, df_plot['close'], color='white', label='Close')
    ax1.set_title("Price Action vs Raw Stochastics Noise")
    ax1.legend()
    
    # Stochastics
    ax2.plot(df_plot.index, df_plot['stoch_k'], color='cyan', alpha=0.5, label='%K (Fast)')
    ax2.plot(df_plot.index, df_plot['stoch_d'], color='magenta', linewidth=1.5, label='%D (stoch_d)')
    ax2.axhline(80, color='red', linestyle='--', alpha=0.5)
    ax2.axhline(20, color='green', linestyle='--', alpha=0.5)
    
    # Highlight whipsaws visually
    cross_up_plot = df_plot[cross_up_80.loc[plot_start:plot_end]]
    cross_dn_plot = df_plot[cross_down_20.loc[plot_start:plot_end]]
    ax2.scatter(cross_up_plot.index, cross_up_plot['stoch_d'], color='red', marker='x', label='Cross 80')
    ax2.scatter(cross_dn_plot.index, cross_dn_plot['stoch_d'], color='green', marker='x', label='Cross 20')
    
    ax2.set_title("Stochastic %D (Noisy Crossings in Trend)")
    ax2.legend()
    
    plt.tight_layout()
    
    # Save artifacts
    artifacts_dir = os.path.join(os.path.dirname(__file__), 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)
    plt.savefig(os.path.join(artifacts_dir, 'stoch_d_noise.png'))
    print("Saved artifact.")
    
    # Save metrics
    metrics = {
        "total_crossings": int(total_false_signals),
        "avg_crossings_per_month": round(total_false_signals / (len(df)/24/30), 2),
        "status": "completed"
    }
    with open(os.path.join(os.path.dirname(__file__), 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
    print("Saved metrics.json.")

if __name__ == '__main__':
    main()
