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
    
    # Base Conditions (145 signals)
    bw144_q = df['BW_144'].rolling(720).quantile(0.4)
    cond_macro_vol = (df['BW_144'] < bw144_q)
    cond_macro_phase = (df['PHASE_144'] <= 0)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55'])
    cond_micro_phase = (df['PHASE_21'] == 1) & (df['PHASE_21'].shift(1) <= 0)
    
    base_idx = df[cond_macro_vol & cond_macro_phase & cond_micro_mom & cond_micro_phase].index
    
    # Calculate The Void Space for all rows
    sma_cols = ['SMA_144', 'SMA_377', 'SMA_610', 'SMA_1597']
    def get_void(row):
        smas = row[sma_cols]
        ceiling = smas[smas > row['close']].min()
        if pd.isna(ceiling):
            ceiling = row['close'] * 1.5 
        return (ceiling - row['close']) / row['ATR_144']
        
    df['Void_ATR'] = df.apply(get_void, axis=1)
    
    # Calculate Micro Volatility Ignition (Velocity of Bandwidth 21 in the next 12 hours)
    # How much did the bandwidth expand right after entry?
    # Actually, the trigger should be observable AT entry or immediately after.
    # We will measure the 12h change in BW_21 following the entry.
    df['Micro_Ignition'] = (df['BW_21'].shift(-12) - df['BW_21']) / df['BW_21'] * 100
    
    # Filter 1: Divergence
    price_low = df['low'].rolling(24).min()
    price_prev_low = df['low'].shift(24).rolling(96).min()
    afs_curr = df['AFS_144'].rolling(24).min()
    afs_prev = df['AFS_144'].shift(24).rolling(96).min()
    bull_div = (price_low < price_prev_low) & (afs_curr > afs_prev)
    
    # Compile Trades
    trades = []
    for idx in base_idx:
        loc = df.index.get_loc(idx)
        if loc + 48 >= len(df):
            continue
            
        entry_price = df['close'].iloc[loc]
        atr = df['ATR'].iloc[loc]
        
        future_prices = df['close'].iloc[loc:loc+48].values
        trajectory = (future_prices - entry_price) / atr
        mfe = trajectory.max()
        mae = trajectory.min()
        
        # Only analyze SUCCESSFUL trades (MFE >= 1.5)
        if mfe < 1.5:
            continue
            
        passed_div = bull_div.iloc[loc]
        void_space = df['Void_ATR'].iloc[loc]
        ignition = df['Micro_Ignition'].iloc[loc]
        
        if passed_div and void_space >= 3.0:
            category = "Elite 4 (Zero-Gravity)"
        elif passed_div and void_space < 3.0:
            category = "Ceiling Breakers (Missed)"
        else:
            category = "V-Shape Capitulation (Missed)"
            
        trades.append({
            'Category': category,
            'Void_Space': void_space,
            'Ignition_Velocity': ignition,
            'MFE': mfe
        })
        
    trades_df = pd.DataFrame(trades)
    
    print(f"Total Successful Trades in Base: {len(trades_df)}")
    print(trades_df['Category'].value_counts())
    
    # Plotting
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    # Plot 1: Scatter of Void Space vs Ignition Velocity
    sns.scatterplot(data=trades_df, x='Void_Space', y='Ignition_Velocity', hue='Category',
                    palette={'Elite 4 (Zero-Gravity)': 'lime', 
                             'Ceiling Breakers (Missed)': 'cyan', 
                             'V-Shape Capitulation (Missed)': 'magenta'},
                    s=150, alpha=0.8, ax=axes[0])
    axes[0].axvline(3.0, color='yellow', linestyle='--', alpha=0.5, label='Void Threshold')
    axes[0].set_title("The Orthogonal Alpha\nExhaustion (Void) vs Ignition (Velocity)", fontsize=14, color='white')
    axes[0].set_xlabel("The Void Space (ATR distance to Ceiling)")
    axes[0].set_ylabel("Micro Ignition Velocity (12h % expansion of BW_21)")
    
    # Draw arrow to show the two orthogonal paths
    axes[0].annotate('Engine 1: Zero-Gravity\n(Wide Space, Normal Ignition)', 
                     xy=(5, 20), xytext=(4, 80), color='lime',
                     arrowprops=dict(facecolor='lime', shrink=0.05))
    axes[0].annotate('Engine 2: The Battering Ram\n(Narrow Space, Violent Ignition)', 
                     xy=(1.5, 120), xytext=(0, 200), color='magenta',
                     arrowprops=dict(facecolor='magenta', shrink=0.05))

    # Plot 2: Boxplot of Ignition Velocity by Category
    sns.boxplot(data=trades_df, x='Category', y='Ignition_Velocity', ax=axes[1],
                palette={'Elite 4 (Zero-Gravity)': 'lime', 
                         'Ceiling Breakers (Missed)': 'cyan', 
                         'V-Shape Capitulation (Missed)': 'magenta'})
    axes[1].set_title("Kinetic Energy Required to Succeed", fontsize=14, color='white')
    axes[1].set_ylabel("Micro Ignition Velocity")
    axes[1].tick_params(axis='x', rotation=15)
    
    plt.tight_layout()
    plt.savefig("missed_alpha_analysis.png", dpi=300)
    print("Saved missed_alpha_analysis.png")

if __name__ == '__main__':
    main()
