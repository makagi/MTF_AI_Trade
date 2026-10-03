import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import os

from src.data_loader import load_1h_data

def get_fib_periods():
    return [21, 55, 144, 233, 377, 610]

def main():
    print("Loading data...")
    df = load_1h_data()
    periods = get_fib_periods()
    
    for p in periods:
        df[f'SMA_{p}'] = df['close'].rolling(p).mean()
        
    # Calculate Cluster Width (Convergence/Divergence)
    sma_cols = [f'SMA_{p}' for p in periods]
    df['SMA_Max'] = df[sma_cols].max(axis=1)
    df['SMA_Min'] = df[sma_cols].min(axis=1)
    df['Cluster_Width_Pct'] = (df['SMA_Max'] - df['SMA_Min']) / df['close'] * 100
    
    # Measure typical distance to 377 (Magnet Effect)
    df['Dist_to_377_Pct'] = (df['close'] - df['SMA_377']) / df['SMA_377'] * 100
    
    mean_cluster_width = df['Cluster_Width_Pct'].mean()
    max_cluster_width = df['Cluster_Width_Pct'].max()
    
    print(f"Mean SMA Cluster Width: {mean_cluster_width:.2f}%")
    print(f"Max SMA Cluster Width: {max_cluster_width:.2f}%")
    
    # Plotting
    plot_start = '2022-01-01'
    plot_end = '2022-06-01'
    df_plot = df.loc[plot_start:plot_end]
    
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    # Price & SMAs
    ax1.plot(df_plot.index, df_plot['close'], color='white', label='Close', alpha=0.8)
    colors = ['cyan', 'dodgerblue', 'lime', 'yellow', 'orange', 'red']
    for p, c in zip(periods, colors):
        ax1.plot(df_plot.index, df_plot[f'SMA_{p}'], color=c, label=f'SMA {p}')
        
    ax1.set_title("MTF Simple Moving Averages (Fanning & Clustering)")
    ax1.legend()
    
    # Cluster Width
    ax2.plot(df_plot.index, df_plot['Cluster_Width_Pct'], color='magenta', label='Cluster Width (%)')
    ax2.set_title("SMA Convergence / Divergence (Cluster Width)")
    ax2.set_ylabel("% of Price")
    ax2.legend()
    
    plt.tight_layout()
    
    # Save artifacts
    artifacts_dir = os.path.join(os.path.dirname(__file__), 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)
    plt.savefig(os.path.join(artifacts_dir, 'sma_clusters.png'))
    print("Saved artifact.")
    
    # Save metrics
    metrics = {
        "mean_cluster_width_pct": round(mean_cluster_width, 2),
        "max_cluster_width_pct": round(max_cluster_width, 2),
        "status": "completed"
    }
    with open(os.path.join(os.path.dirname(__file__), 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
    print("Saved metrics.json.")

if __name__ == '__main__':
    main()
