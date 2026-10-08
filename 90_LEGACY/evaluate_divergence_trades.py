import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def calculate_atr(df, p=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(p).mean()
    # Macro ATR for void distance
    df['ATR_144'] = true_range.rolling(144).mean()
    return df

def get_fib_periods():
    return [21, 55, 144, 377, 610, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'SMA_{p}'] = sma
        df[f'BW_{p}'] = (upper - lower) / df['close']
        df[f'VEL_BW_{p}'] = df[f'BW_{p}'].diff(24)
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
        
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
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    # 1. Base Strategy
    bw144_q = df['BW_144'].rolling(720).quantile(0.4)
    cond_macro_vol = (df['BW_144'] < bw144_q)
    cond_macro_phase = (df['PHASE_144'] <= 0)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55'])
    cond_micro_phase = (df['PHASE_21'] == 1) & (df['PHASE_21'].shift(1) <= 0)
    base_buy = cond_macro_vol & cond_macro_phase & cond_micro_mom & cond_micro_phase
    
    # 2. First Fix (Divergence)
    price_low = df['low'].rolling(24).min()
    price_prev_low = df['low'].shift(24).rolling(96).min()
    afs_curr = df['AFS_144'].rolling(24).min()
    afs_prev = df['AFS_144'].shift(24).rolling(96).min()
    bull_div = (price_low < price_prev_low) & (afs_curr > afs_prev)
    div_buy_idx = df[base_buy & bull_div].index
    
    # 3. Simulate Trades & Collect Trajectories
    trajectories = []
    trades = []
    
    # Calculate The Void Space for all rows beforehand
    sma_cols = ['SMA_144', 'SMA_377', 'SMA_610', 'SMA_1597']
    # For each row, find the minimum SMA that is > close
    def get_void(row):
        smas = row[sma_cols]
        ceiling = smas[smas > row['close']].min()
        if pd.isna(ceiling):
            ceiling = row['close'] * 1.5 # Arbitrary large space if no ceiling
        return (ceiling - row['close']) / row['ATR_144']
        
    df['Void_ATR'] = df.apply(get_void, axis=1)

    for idx in div_buy_idx:
        loc = df.index.get_loc(idx)
        if loc + 48 >= len(df):
            continue
            
        entry_price = df['close'].iloc[loc]
        atr = df['ATR'].iloc[loc]
        
        # Next 48 hours trajectory (in ATR units)
        future_prices = df['close'].iloc[loc:loc+48].values
        trajectory = (future_prices - entry_price) / atr
        trajectories.append(trajectory)
        
        # Max profit / Max Drawdown in first 48h
        mfe = trajectory.max()
        mae = trajectory.min()
        
        # Time in Drawdown (hours where price < entry)
        tid = np.sum(trajectory < 0)
        
        void_atr = df['Void_ATR'].iloc[loc]
        
        trades.append({
            'entry_time': idx,
            'mfe': mfe,
            'mae': mae,
            'tid': tid,
            'void_atr': void_atr
        })
        
    trades_df = pd.DataFrame(trades)
    
    print(f"Total Divergence Trades: {len(trades_df)}")
    if len(trades_df) == 0:
        return
        
    print(f"Average Time-in-Drawdown (48h window): {trades_df['tid'].mean():.1f} hours")
    print(f"Trades with Void >= 3 ATR: {sum(trades_df['void_atr'] >= 3.0)}")
    
    # Visualization
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    # Plot 1: Average Trajectory
    trajectories = np.array(trajectories)
    mean_traj = trajectories.mean(axis=0)
    std_traj = trajectories.std(axis=0)
    
    hours = np.arange(48)
    axes[0].plot(hours, mean_traj, color='lime', linewidth=3, label='Average Trajectory')
    axes[0].fill_between(hours, mean_traj - std_traj, mean_traj + std_traj, color='lime', alpha=0.2)
    
    # Plot individual trajectories faintly
    for traj in trajectories:
        axes[0].plot(hours, traj, color='gray', alpha=0.3, linewidth=1)
        
    axes[0].axhline(0, color='white', linestyle='--', alpha=0.5)
    axes[0].set_title("The Spark's Velocity\nAverage Trade Trajectory (Next 48h)", fontsize=14, color='white')
    axes[0].set_xlabel("Hours after Entry")
    axes[0].set_ylabel("Profit/Loss (ATR)")
    axes[0].legend()
    
    # Plot 2: Scatter of The Void vs MFE
    sns.scatterplot(data=trades_df, x='void_atr', y='mfe', s=100, color='cyan', alpha=0.8, ax=axes[1])
    axes[1].axvline(3.0, color='yellow', linestyle='--', label='Void Threshold (3.0 ATR)')
    axes[1].axhline(1.5, color='lime', linestyle='--', label='Target MFE (1.5 ATR)')
    axes[1].set_title("The Second Fix: The Void Filter\nPhysical Distance to Macro Ceiling vs Max Profit", fontsize=14, color='white')
    axes[1].set_xlabel("Distance to Nearest Macro SMA Ceiling (ATR)")
    axes[1].set_ylabel("Max Favorable Excursion (MFE) in ATR")
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig("divergence_evaluation.png", dpi=300)
    print("Saved divergence_evaluation.png")

if __name__ == '__main__':
    main()
