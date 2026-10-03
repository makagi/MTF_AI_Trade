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
    return df

def get_fib_periods():
    return [21, 55, 144, 377, 610]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
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

def run_backtest_and_get_trades(df):
    bw144_q = df['BW_144'].rolling(720).quantile(0.4)
    cond_macro_vol = (df['BW_144'] < bw144_q)
    cond_macro_phase = (df['PHASE_144'] <= 0)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55'])
    cond_micro_phase = (df['PHASE_21'] == 1) & (df['PHASE_21'].shift(1) <= 0)
    
    buy_signals = df[cond_macro_vol & cond_macro_phase & cond_micro_mom & cond_micro_phase].index
    
    trades = []
    in_trade = False
    entry_idx = None
    entry_price = 0
    sl_price = 0
    atr = 0
    
    for i in range(len(df)):
        idx = df.index[i]
        row = df.iloc[i]
        
        if not in_trade:
            if idx in buy_signals:
                in_trade = True
                entry_idx = idx
                entry_price = row['close']
                atr = row['ATR']
                sl_price = entry_price - (atr * 1.5)
        else:
            if row['low'] < sl_price:
                trades.append({
                    'entry': entry_idx, 'exit': idx, 
                    'atr_pnl': (sl_price - entry_price)/atr, 
                    'afs_377': df.loc[entry_idx, 'AFS_377'],
                    'afs_610': df.loc[entry_idx, 'AFS_610'],
                    'vel_bw_144': df.loc[entry_idx, 'VEL_BW_144']
                })
                in_trade = False
            elif row['PHASE_21'] == -1:
                exit_price = row['close']
                trades.append({
                    'entry': entry_idx, 'exit': idx, 
                    'atr_pnl': (exit_price - entry_price)/atr,
                    'afs_377': df.loc[entry_idx, 'AFS_377'],
                    'afs_610': df.loc[entry_idx, 'AFS_610'],
                    'vel_bw_144': df.loc[entry_idx, 'VEL_BW_144']
                })
                in_trade = False
                
    return pd.DataFrame(trades)

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    print("Running Backtest to extract features at entry...")
    trades = run_backtest_and_get_trades(df)
    
    if len(trades) == 0:
        print("No trades found.")
        return
        
    # Classify trades
    trades['Category'] = 'Neutral'
    trades.loc[trades['atr_pnl'] >= 1.0, 'Category'] = 'Success'
    trades.loc[trades['atr_pnl'] < -0.5, 'Category'] = 'Failure'
    
    filtered_trades = trades[trades['Category'].isin(['Success', 'Failure'])]
    
    print(f"Total Trades: {len(trades)}")
    print(f"Success: {len(filtered_trades[filtered_trades['Category']=='Success'])}")
    print(f"Failure: {len(filtered_trades[filtered_trades['Category']=='Failure'])}")
    
    # Plotting
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    # Plot 1: Histogram of AFS_610 (Macro Momentum)
    sns.histplot(data=filtered_trades, x='afs_610', hue='Category', bins=20, 
                 palette={'Success': 'lime', 'Failure': 'red'}, alpha=0.6, ax=axes[0], multiple="stack")
    axes[0].set_title("Weakness A: Counter-Trend Traps\nDistribution of Macro Momentum (AFS 610) at Entry", fontsize=14, color='white')
    axes[0].set_xlabel("AFS 610 (0 = Extreme Down, 100 = Extreme Up)")
    axes[0].axvline(50, color='white', linestyle='--', alpha=0.5)
    
    # Plot 2: Scatter of Bandwidth Velocity vs PNL
    sns.scatterplot(data=filtered_trades, x='vel_bw_144', y='atr_pnl', hue='Category', 
                    palette={'Success': 'lime', 'Failure': 'red'}, s=100, alpha=0.8, ax=axes[1])
    axes[1].set_title("Weakness B: Directionless Squeeze Fails\nBandwidth Velocity vs Outcome", fontsize=14, color='white')
    axes[1].set_xlabel("Bandwidth Squeeze Velocity (Near 0 = Fully Squeezed)")
    axes[1].set_ylabel("Profit / Loss (ATR)")
    axes[1].axhline(0, color='white', linestyle='--', alpha=0.5)
    axes[1].axvline(0, color='yellow', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig("system_weakness_analysis.png", dpi=300)
    print("Saved system_weakness_analysis.png")

if __name__ == '__main__':
    main()
