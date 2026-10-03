import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import os

from src.data_loader import load_1h_data

def get_fib_periods():
    return [21, 55, 144, 233, 377, 610]

def add_afs_features(df):
    periods = get_fib_periods()
    for p in periods:
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        
        # Fast Stochastic (k)
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        
        # AFS (smoothed d)
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
    return df

def main():
    print("Loading data...")
    df = load_1h_data() # Discovery dataset (2020-2023)
    df = add_afs_features(df)
    
    # Calculate Forward Returns for baseline evaluation
    df['fwd_return_24h'] = df['close'].shift(-24) / df['close'] - 1
    
    # Define an AFS cross-up signal (Micro crossing Macro)
    # E.g., AFS_21 crossing above AFS_55
    df['afs_cross_up'] = (df['AFS_21'] > df['AFS_55']) & (df['AFS_21'].shift(1) <= df['AFS_55'].shift(1))
    
    signals = df[df['afs_cross_up']]
    
    win_rate = (signals['fwd_return_24h'] > 0).mean() * 100
    mean_return = signals['fwd_return_24h'].mean() * 100
    total_trades = len(signals)
    
    print(f"Total Signals: {total_trades}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Mean Fwd Return: {mean_return:.2f}%")
    
    # Plotting
    plot_start = '2022-01-01'
    plot_end = '2022-04-01'
    df_plot = df.loc[plot_start:plot_end]
    
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    # Price
    ax1.plot(df_plot.index, df_plot['close'], color='white', label='Close')
    # Mark signals
    sig_plot = df_plot[df_plot['afs_cross_up']]
    ax1.scatter(sig_plot.index, sig_plot['close'], color='lime', marker='^', s=100, label='AFS 21x55 Cross Up')
    ax1.set_title("Price Action and AFS Cross Signals")
    ax1.legend()
    
    # AFS
    ax2.plot(df_plot.index, df_plot['AFS_21'], color='cyan', label='AFS 21')
    ax2.plot(df_plot.index, df_plot['AFS_55'], color='magenta', label='AFS 55')
    ax2.plot(df_plot.index, df_plot['AFS_144'], color='orange', alpha=0.5, label='AFS 144')
    ax2.axhline(50, color='white', linestyle='--', alpha=0.3)
    ax2.set_title("Average Fibonacci Stochastics (AFS)")
    ax2.legend()
    
    plt.tight_layout()
    
    # Save artifacts
    artifacts_dir = os.path.join(os.path.dirname(__file__), 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)
    plt.savefig(os.path.join(artifacts_dir, 'afs_visualization.png'))
    print("Saved artifact.")
    
    # Save metrics
    metrics = {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "mean_return_pct": round(mean_return, 2),
        "status": "completed"
    }
    with open(os.path.join(os.path.dirname(__file__), 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
    print("Saved metrics.json.")

if __name__ == '__main__':
    main()
