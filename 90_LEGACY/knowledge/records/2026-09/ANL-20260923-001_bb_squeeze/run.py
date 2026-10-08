import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import os

from src.data_loader import load_1h_data

def get_fib_periods():
    return [21, 55, 144, 377]

def add_bb_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        
        df[f'BB_Upper_{p}'] = sma + 2 * std
        df[f'BB_Lower_{p}'] = sma - 2 * std
        
        # Bandwidth (Normalized by price)
        df[f'BW_{p}'] = (df[f'BB_Upper_{p}'] - df[f'BB_Lower_{p}']) / df['close']
        
        # Bandwidth Percentile (Rolling 30 days = 720 hours)
        df[f'BW_Pct_{p}'] = df[f'BW_{p}'].rolling(720).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if not pd.isna(x).any() else np.nan
        )
    return df

def main():
    print("Loading data...")
    df = load_1h_data()
    df = add_bb_features(df)
    
    # Calculate Forward Returns volatility (Absolute returns)
    df['fwd_vol_24h'] = np.abs(df['close'].shift(-24) / df['close'] - 1)
    
    # Define Squeeze (BW_Pct < 0.1) vs Expansion (BW_Pct > 0.9) for period 144
    squeeze_mask = df['BW_Pct_144'] < 0.1
    expansion_mask = df['BW_Pct_144'] > 0.9
    
    mean_vol_squeeze = df[squeeze_mask]['fwd_vol_24h'].mean() * 100
    mean_vol_expansion = df[expansion_mask]['fwd_vol_24h'].mean() * 100
    
    print(f"Mean 24h Volatility after Squeeze: {mean_vol_squeeze:.2f}%")
    print(f"Mean 24h Volatility after Expansion: {mean_vol_expansion:.2f}%")
    
    # Plotting
    plot_start = '2022-01-01'
    plot_end = '2022-06-01'
    df_plot = df.loc[plot_start:plot_end]
    
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    # Price & BB
    ax1.plot(df_plot.index, df_plot['close'], color='white', label='Close')
    ax1.plot(df_plot.index, df_plot['BB_Upper_144'], color='cyan', alpha=0.6, linestyle='--')
    ax1.plot(df_plot.index, df_plot['BB_Lower_144'], color='cyan', alpha=0.6, linestyle='--', label='BB 144')
    ax1.fill_between(df_plot.index, df_plot['BB_Upper_144'], df_plot['BB_Lower_144'], color='cyan', alpha=0.1)
    
    # Highlight Squeezes
    squeeze_plot = df_plot[df_plot['BW_Pct_144'] < 0.1]
    ax1.scatter(squeeze_plot.index, squeeze_plot['close'], color='yellow', s=20, label='Squeeze (BW Pct < 0.1)')
    
    ax1.set_title("Price and Bollinger Bands (144)")
    ax1.legend()
    
    # Bandwidth Percentile
    ax2.plot(df_plot.index, df_plot['BW_Pct_144'], color='magenta', label='BW Percentile 144')
    ax2.axhline(0.1, color='yellow', linestyle='--', label='Squeeze Threshold (0.1)')
    ax2.set_title("Bollinger Bandwidth Percentile (Volatility Cycle)")
    ax2.set_ylim(0, 1)
    ax2.legend()
    
    plt.tight_layout()
    
    # Save artifacts
    artifacts_dir = os.path.join(os.path.dirname(__file__), 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)
    plt.savefig(os.path.join(artifacts_dir, 'bb_squeeze_cycle.png'))
    print("Saved artifact.")
    
    # Save metrics
    metrics = {
        "mean_fwd_vol_after_squeeze_pct": round(mean_vol_squeeze, 2),
        "mean_fwd_vol_after_expansion_pct": round(mean_vol_expansion, 2),
        "volatility_ratio": round(mean_vol_squeeze / mean_vol_expansion, 2) if mean_vol_expansion > 0 else 0,
        "status": "completed"
    }
    with open(os.path.join(os.path.dirname(__file__), 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
    print("Saved metrics.json.")

if __name__ == '__main__':
    main()
