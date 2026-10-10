import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def get_fib_periods():
    return [21, 55, 144, 377]

def calculate_afs(df, periods):
    for p in periods:
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
    return df

def add_bb_features(df, p):
    sma = df['close'].rolling(p).mean()
    std = df['close'].rolling(p).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    df[f'BB_U_{p}'] = upper
    df[f'BB_L_{p}'] = lower
    df[f'SMA_{p}'] = sma
    df[f'BW_{p}'] = (upper - lower) / df['close']
    df[f'VEL_BW_{p}'] = df[f'BW_{p}'].diff(24)
    return df

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    
    print("Calculating Features...")
    periods = get_fib_periods()
    df = calculate_afs(df, periods)
    df = add_bb_features(df, 144)
    
    # Calculate AFS Variance (Momentum Compression)
    afs_cols = [f'AFS_{p}' for p in periods]
    df['AFS_VARIANCE'] = df[afs_cols].var(axis=1)
    
    print("Finding Middle-Line Touch Events...")
    # Come from bottom: in the last 120h (5 days), price touched 144 lower band
    come_from_bottom = df['low'].rolling(120).min() <= df['BB_L_144']
    
    # Touch Middle: High crosses above 144 SMA today, but previous close was below
    touch_middle = (df['high'] >= df['SMA_144']) & (df['close'].shift(1) < df['SMA_144'].shift(1))
    
    # Combined Trigger
    events = come_from_bottom & touch_middle
    event_indices = df[events].index
    
    print(f"Total Touch Events Found: {len(event_indices)}")
    
    results = []
    
    for t_idx in event_indices:
        t_loc = df.index.get_loc(t_idx)
        if t_loc + 120 >= len(df): continue
        
        forward = df.iloc[t_loc+1 : t_loc+120]
        
        # Check which it hits first: Upper or Lower
        hit_upper = False
        hit_lower = False
        
        for i in range(len(forward)):
            if forward['high'].iloc[i] >= forward['BB_U_144'].iloc[i]:
                hit_upper = True
                break
            if forward['low'].iloc[i] <= forward['BB_L_144'].iloc[i]:
                hit_lower = True
                break
        
        # We classify as:
        # Breakout (Non-fit): Hit Upper first
        # Fit (Reflection): Hit Lower first
        if hit_upper:
            category = 'Breakout (Non-fit)'
        elif hit_lower:
            category = 'Fit (Reflection)'
        else:
            category = 'Unresolved'
            
        if category != 'Unresolved':
            results.append({
                'Date': t_idx,
                'Category': category,
                'AFS_Variance': df.iloc[t_loc]['AFS_VARIANCE'],
                'VEL_BW_144': df.iloc[t_loc]['VEL_BW_144']
            })
            
    res_df = pd.DataFrame(results)
    
    if len(res_df) == 0:
        print("No valid resolved events found.")
        return
        
    print("\nClassification Stats:")
    print(res_df['Category'].value_counts())
    
    # --- Visualization ---
    plt.figure(figsize=(16, 8))
    sns.set_style("darkgrid")
    plt.style.use('dark_background')
    
    # Plot 1: AFS Variance Boxplot
    plt.subplot(1, 2, 1)
    sns.boxplot(x='Category', y='AFS_Variance', data=res_df, palette=['#ff4444', '#44ff44'])
    plt.title("Momentum Compression (AFS Variance) at Touch\nLower is more compressed", fontsize=14, color='white')
    plt.ylabel("Variance of AFS (21, 55, 144, 377)")
    
    # Plot 2: BB Velocity Boxplot
    plt.subplot(1, 2, 2)
    sns.boxplot(x='Category', y='VEL_BW_144', data=res_df, palette=['#ff4444', '#44ff44'])
    plt.axhline(0, color='yellow', linestyle='--', alpha=0.5)
    plt.title("Time-to-Resolution (144-BB Velocity) at Touch\nNear 0 is optimal resolution", fontsize=14, color='white')
    plt.ylabel("Bandwidth Velocity (24h diff)")
    
    plt.tight_layout()
    plt.savefig("reflection_vs_breakout_stats.png", dpi=300)
    print("Saved reflection_vs_breakout_stats.png")

if __name__ == '__main__':
    main()
