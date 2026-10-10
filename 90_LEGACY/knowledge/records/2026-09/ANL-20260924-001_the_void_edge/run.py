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
        print(f"Dataset not found at {data_path}. Please run tools/build_features.py first.")
        sys.exit(1)
        
    df = pd.read_parquet(data_path)
    
    # Target: 24h Forward Return
    df['fwd_return_24h'] = df['close'].shift(-24) / df['close'] - 1
    
    # 1. Base Signal: Short-term AFS Cross Up (FIB_7=21 crossing FIB_9=55)
    afs_short = df['FIB_7_stoch_d']
    afs_mid = df['FIB_9_stoch_d']
    
    cross_up = (afs_short > afs_mid) & (afs_short.shift(1) <= afs_mid.shift(1))
    df['base_signal'] = cross_up
    
    # 2. Void Detection: Distance to nearest overhead Macro SMA
    # Macro layers: FIB_11 (144) to FIB_16 (1597)
    macro_sma_cols = [f'FIB_{i}_SMA' for i in range(11, 17)]
    
    # Filter SMAs that are strictly above the current close
    # Create a DataFrame of overhead SMAs (NaN if below close)
    overhead_smas = df[macro_sma_cols].apply(lambda x: np.where(x > df['close'], x, np.nan))
    
    # Find the minimum value among overhead SMAs (the closest ceiling)
    df['nearest_overhead_sma'] = overhead_smas.min(axis=1)
    
    # Calculate distance in percentage
    df['void_distance_pct'] = (df['nearest_overhead_sma'] - df['close']) / df['close'] * 100
    # If no overhead SMA (all are below), distance is effectively infinity
    df['void_distance_pct'] = df['void_distance_pct'].fillna(999)
    
    # Define "The Void": Nearest ceiling is more than 3% away
    df['in_void'] = df['void_distance_pct'] > 3.0
    
    # 3. Evaluate Performance
    signals_all = df[df['base_signal']].dropna(subset=['fwd_return_24h'])
    signals_void = df[df['base_signal'] & df['in_void']].dropna(subset=['fwd_return_24h'])
    signals_blocked = df[df['base_signal'] & ~df['in_void']].dropna(subset=['fwd_return_24h'])
    
    win_rate_all = (signals_all['fwd_return_24h'] > 0).mean() * 100
    win_rate_void = (signals_void['fwd_return_24h'] > 0).mean() * 100
    win_rate_blocked = (signals_blocked['fwd_return_24h'] > 0).mean() * 100
    
    mean_ret_all = signals_all['fwd_return_24h'].mean() * 100
    mean_ret_void = signals_void['fwd_return_24h'].mean() * 100
    mean_ret_blocked = signals_blocked['fwd_return_24h'].mean() * 100
    
    print(f"--- Performance Comparison ---")
    print(f"All Signals      : N={len(signals_all)}, Win Rate: {win_rate_all:.2f}%, Mean Ret: {mean_ret_all:.2f}%")
    print(f"In The Void (>3%): N={len(signals_void)}, Win Rate: {win_rate_void:.2f}%, Mean Ret: {mean_ret_void:.2f}%")
    print(f"Blocked (<3%)    : N={len(signals_blocked)}, Win Rate: {win_rate_blocked:.2f}%, Mean Ret: {mean_ret_blocked:.2f}%")
    
    # 4. Plotting a representative case
    plot_start = '2023-01-01'
    plot_end = '2023-02-15'
    df_plot = df.loc[plot_start:plot_end]
    
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    
    ax1.plot(df_plot.index, df_plot['close'], color='white', label='Close')
    # Plot Macro SMAs
    colors = ['cyan', 'dodgerblue', 'lime', 'yellow', 'orange', 'red']
    for col, c in zip(macro_sma_cols, colors):
        ax1.plot(df_plot.index, df_plot[col], color=c, alpha=0.4, label=col.replace('_', ' '))
        
    # Mark Void Signals (Green) vs Blocked Signals (Red)
    plot_void = df_plot[df_plot['base_signal'] & df_plot['in_void']]
    plot_blocked = df_plot[df_plot['base_signal'] & ~df_plot['in_void']]
    
    ax1.scatter(plot_void.index, plot_void['close'] * 0.98, color='lime', marker='^', s=150, label='Void Signal (High ER)')
    ax1.scatter(plot_blocked.index, plot_blocked['close'] * 0.98, color='red', marker='x', s=100, label='Blocked Signal (Low ER)')
    
    ax1.set_title("The Void: Unresisted Airspace (Distance to Overhead Macro SMAs)")
    ax1.legend(loc='upper left', fontsize=8)
    
    # AFS subplot
    ax2.plot(df_plot.index, df_plot['FIB_7_stoch_d'], color='cyan', label='AFS 21')
    ax2.plot(df_plot.index, df_plot['FIB_9_stoch_d'], color='magenta', label='AFS 55')
    ax2.set_title("Base Signal (AFS Cross)")
    ax2.legend()
    
    plt.tight_layout()
    
    artifacts_dir = os.path.join(os.path.dirname(__file__), 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)
    plt.savefig(os.path.join(artifacts_dir, 'the_void_edge.png'))
    print("Saved artifact.")
    
    metrics = {
        "all_signals": {"count": int(len(signals_all)), "win_rate": float(round(win_rate_all, 2)), "mean_ret": float(round(mean_ret_all, 2))},
        "void_signals": {"count": int(len(signals_void)), "win_rate": float(round(win_rate_void, 2)), "mean_ret": float(round(mean_ret_void, 2))},
        "blocked_signals": {"count": int(len(signals_blocked)), "win_rate": float(round(win_rate_blocked, 2)), "mean_ret": float(round(mean_ret_blocked, 2))},
        "win_rate_improvement": float(round(win_rate_void - win_rate_all, 2)),
        "status": "completed"
    }
    with open(os.path.join(os.path.dirname(__file__), 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
    print("Saved metrics.json.")

if __name__ == '__main__':
    main()
