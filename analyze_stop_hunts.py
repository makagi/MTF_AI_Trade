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
    return [7, 21, 55, 144, 233, 377, 610, 987, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        df[f'SMA_{p}'] = sma
        df[f'BB_Lower_{p}'] = sma - 2 * std
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
    return df

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    # Re-run Strategy V3 to get all signals
    # V1 (Base - required for Engine 1)
    bw144_q = ((df['SMA_144'] + 2*df['close'].rolling(144).std()) - (df['SMA_144'] - 2*df['close'].rolling(144).std())) / df['close']
    bw144_thresh = bw144_q.rolling(720).quantile(0.4)
    cond_macro_vol = (bw144_q < bw144_thresh)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55']) & (df['AFS_21'].shift(1) <= df['AFS_55'].shift(1))
    
    price_low = df['low'].rolling(24).min()
    price_prev_low = df['low'].shift(24).rolling(96).min()
    afs_curr = df['AFS_144'].rolling(24).min()
    afs_prev = df['AFS_144'].shift(24).rolling(96).min()
    bull_div = (price_low < price_prev_low) & (afs_curr > afs_prev)
    
    sma_cols = ['SMA_144', 'SMA_377', 'SMA_610', 'SMA_1597']
    def get_void(row):
        smas = row[sma_cols]
        ceiling = smas[smas > row['close']].min()
        if pd.isna(ceiling): return 10 
        return (ceiling - row['close']) / row['ATR_144']
    df['Void_ATR'] = df.apply(get_void, axis=1)
    
    engine1_signals = df[cond_macro_vol & cond_micro_mom & bull_div & (df['Void_ATR'] >= 3.0)].index
    
    cross_233_377 = (df['SMA_233'] > df['SMA_377']) & (df['SMA_233'].shift(1) <= df['SMA_377'].shift(1))
    is_hugging = (df['close'] > df['SMA_377']) & ((df['close'] - df['SMA_377']) / df['ATR_144'] < 1.5)
    engine2_signals = df[cross_233_377 & is_hugging].index
    
    macro_low = df['low'].shift(24).rolling(720).min()
    near_macro_bottom = (df['low'] <= macro_low * 1.01)
    v_shape_cross = (df['AFS_7'] > df['AFS_21']) & (df['AFS_7'].shift(1) <= df['AFS_21'].shift(1)) & (df['AFS_21'] < 20)
    engine3_signals = df[near_macro_bottom & v_shape_cross].index
    
    all_signals = engine1_signals.union(engine2_signals).union(engine3_signals).sort_values()
    
    # Classify Failures
    # We will look at a 96-hour forward window
    window_hours = 96
    sl_atr = -1.5
    target_atr = 1.5
    
    whipsaws = []
    directional_failures = []
    whipsaw_trajectories = []
    
    supports_to_check = ['SMA_610', 'SMA_987', 'SMA_1597', 'BB_Lower_377', 'BB_Lower_610']
    
    for idx in all_signals:
        loc = df.index.get_loc(idx)
        if loc + window_hours >= len(df): continue
        
        entry_price = df['close'].iloc[loc]
        atr = df['ATR'].iloc[loc]
        
        window_df = df.iloc[loc:loc+window_hours]
        trajectory = (window_df['close'].values - entry_price) / atr
        low_trajectory = (window_df['low'].values - entry_price) / atr
        high_trajectory = (window_df['high'].values - entry_price) / atr
        
        # Did it hit SL before hitting Target?
        hit_sl = False
        sl_idx = -1
        for i in range(window_hours):
            if high_trajectory[i] >= target_atr and not hit_sl:
                break # Hit target first -> Success
            if low_trajectory[i] <= sl_atr:
                hit_sl = True
                sl_idx = i
                break
                
        if hit_sl:
            # Check what happened AFTER SL
            max_after_sl = np.max(high_trajectory[sl_idx:])
            
            if max_after_sl >= target_atr:
                # Whipsaw / Stop Hunt
                
                # Find the absolute minimum point during this dip
                min_idx_relative = np.argmin(low_trajectory[:np.argmax(high_trajectory[sl_idx:])+sl_idx])
                whipsaw_low_price = window_df['low'].iloc[min_idx_relative]
                whipsaw_low_time = window_df.index[min_idx_relative]
                
                # Check distances to deeper supports at that exact time
                row_at_low = window_df.iloc[min_idx_relative]
                closest_support = None
                min_dist = float('inf')
                
                for sup in supports_to_check:
                    sup_val = row_at_low[sup]
                    dist_pct = abs(whipsaw_low_price - sup_val) / sup_val * 100
                    if dist_pct < min_dist:
                        min_dist = dist_pct
                        closest_support = sup
                
                whipsaws.append({
                    'entry_time': idx,
                    'whipsaw_low_time': whipsaw_low_time,
                    'closest_support': closest_support,
                    'dist_pct': min_dist
                })
                whipsaw_trajectories.append(trajectory)
            else:
                # Directional Failure
                directional_failures.append(idx)
                
    whipsaw_df = pd.DataFrame(whipsaws)
    
    print(f"Total Signals: {len(all_signals)}")
    print(f"Directional Failures (Wrong Guess): {len(directional_failures)}")
    print(f"Whipsaws (Liquidity Sweeps): {len(whipsaws)}")
    
    if len(whipsaws) == 0:
        print("No whipsaws found. Adjust conditions or stop loss.")
        return
        
    print("\nTrue Support Identification (Closest Support at Whipsaw Low):")
    print(whipsaw_df['closest_support'].value_counts())
    
    # Plotting
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    # Plot 1: Spaghetti Plot of Whipsaws
    for traj in whipsaw_trajectories:
        axes[0].plot(range(window_hours), traj, color='magenta', alpha=0.3)
    axes[0].axhline(0, color='white', linestyle='--', linewidth=2)
    axes[0].axhline(sl_atr, color='red', linestyle='--', linewidth=2, label='Stop Loss (-1.5 ATR)')
    axes[0].axhline(target_atr, color='lime', linestyle='--', linewidth=2, label='Target (+1.5 ATR)')
    axes[0].set_title("Whipsaw Trajectories (Liquidity Sweeps)\nPrice breaks SL, sweeps liquidity, then rockets to target", color='white', fontsize=14)
    axes[0].set_xlabel("Hours since Entry")
    axes[0].set_ylabel("PnL (ATR)")
    axes[0].legend()
    
    # Plot 2: Bar Chart of Closest Supports
    support_counts = whipsaw_df['closest_support'].value_counts()
    sns.barplot(x=support_counts.index, y=support_counts.values, ax=axes[1], palette='viridis')
    axes[1].set_title("The True Bottom of Liquidity Sweeps\nWhich macro level actually caught the falling knife?", color='white', fontsize=14)
    axes[1].set_ylabel("Number of Whipsaw Trades Bounced Here")
    
    plt.tight_layout()
    plt.savefig("whipsaw_analysis.png", dpi=300)
    print("Saved whipsaw_analysis.png")

if __name__ == '__main__':
    main()
