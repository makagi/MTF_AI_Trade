import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import os
import sys

def main():
    print("Loading exhaustive features dataset...")
    data_path = r"D:\work\AI-Trade\Data\processed\BTCUSD_1h_features_exhaustive.parquet"
    if not os.path.exists(data_path):
        print(f"Dataset not found at {data_path}")
        sys.exit(1)
        
    df = pd.read_parquet(data_path)
    
    # Analyze Hugging on FIB_13 (377)
    macro_sma = df['FIB_13_SMA']
    fast_sma = df['FIB_12_SMA'] # 233
    
    # Distance to Macro SMA in percentage
    df['dist_to_macro'] = np.abs((df['close'] - macro_sma) / macro_sma) * 100
    
    # Define Hugging State: Price is within 1.0% of the Macro SMA
    df['is_hugging'] = df['dist_to_macro'] < 1.0
    
    # Identify individual hugging events (clusters of consecutive hugging bars)
    # 1 if hugging started, -1 if hugging ended
    hugging_change = df['is_hugging'].astype(int).diff()
    
    hug_starts = df.index[hugging_change == 1]
    hug_ends = df.index[hugging_change == -1]
    
    # Clean up boundary conditions
    if len(hug_ends) > 0 and len(hug_starts) > 0:
        if hug_ends[0] < hug_starts[0]:
            hug_ends = hug_ends[1:]
        if len(hug_starts) > len(hug_ends):
            hug_starts = hug_starts[:len(hug_ends)]
            
    hugging_durations = (hug_ends - hug_starts).total_seconds() / 3600 # in hours
    
    valid_durations = hugging_durations[hugging_durations >= 3]
    valid_series = pd.Series(valid_durations)
    
    mean_hug_duration = valid_series.mean()
    median_hug_duration = valid_series.median()
    max_hug_duration = valid_series.max()
    
    print(f"--- Hugging Phenomenon (SMA 377) ---")
    print(f"Total Hugging Events (>3h): {len(valid_durations)}")
    print(f"Mean Hugging Duration: {mean_hug_duration:.2f} hours")
    print(f"Median Hugging Duration: {median_hug_duration:.2f} hours")
    print(f"Max Hugging Duration: {max_hug_duration:.2f} hours")
    
    # Plotting a classic hugging breakout case
    # Find a period where a long hug occurred
    plot_start = '2023-03-01'
    plot_end = '2023-03-31'
    df_plot = df.loc[plot_start:plot_end]
    
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    
    # Top Plot: Price and SMAs
    ax1.plot(df_plot.index, df_plot['close'], color='white', label='Close', alpha=0.9)
    ax1.plot(df_plot.index, df_plot['FIB_13_SMA'], color='red', linewidth=2, label='Macro SMA (377)')
    ax1.plot(df_plot.index, df_plot['FIB_12_SMA'], color='orange', linewidth=1.5, linestyle='--', label='Fast SMA (233)')
    
    # Highlight hugging zones
    ax1.fill_between(df_plot.index, df_plot['FIB_13_SMA']*1.01, df_plot['FIB_13_SMA']*0.99, color='red', alpha=0.1, label='1% Hugging Zone')
    
    ax1.set_title("The Hugging Phenomenon & Breakout Ignition")
    ax1.legend(loc='upper left')
    
    # Bottom Plot: Distance
    ax2.plot(df_plot.index, df_plot['dist_to_macro'], color='cyan', label='Abs Distance to SMA 377 (%)')
    ax2.axhline(1.0, color='yellow', linestyle='--', alpha=0.5, label='1.0% Threshold')
    ax2.fill_between(df_plot.index, 0, 1.0, where=(df_plot['dist_to_macro'] < 1.0), color='yellow', alpha=0.2)
    ax2.set_title("Distance to Macro SMA (Compression)")
    ax2.set_ylim(0, 5)
    ax2.legend(loc='upper left')
    
    plt.tight_layout()
    
    # Save artifacts
    artifacts_dir = os.path.join(os.path.dirname(__file__), 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)
    plt.savefig(os.path.join(artifacts_dir, 'sma_hugging.png'))
    print("Saved artifact.")
    
    # Metrics
    metrics = {
        "total_hugging_events": len(valid_durations),
        "mean_duration_hours": float(round(mean_hug_duration, 2)),
        "median_duration_hours": float(round(median_hug_duration, 2)),
        "max_duration_hours": float(round(max_hug_duration, 2)),
        "status": "completed"
    }
    with open(os.path.join(os.path.dirname(__file__), 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
    print("Saved metrics.json.")

if __name__ == '__main__':
    main()
