import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def get_fib_periods():
    # Adding a few more to see the full spectrum
    return [21, 55, 144, 233, 377, 610, 987, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        df[f'SMA_{p}'] = sma
        
        # Bandwidth calculation
        upper = sma + 2 * std
        lower = sma - 2 * std
        bw = (upper - lower) / df['close']
        df[f'BW_{p}'] = bw
        
        # Bandwidth percentile (relative to its own 720h history to normalize across scales)
        df[f'BW_Pct_{p}'] = bw.rolling(720).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] if not pd.isna(x).any() else np.nan)
        
    return df

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = add_features(df)
    
    # We want to identify "Significant Swings" to analyze this dynamically.
    # Let's use the Base signals from our V1 (macro squeezed + micro mom)
    # But to be more general, let's just find points where AFS_21 crosses AFS_55 upward
    
    # We need AFS for swing detection
    periods = get_fib_periods()
    for p in [21, 55]:
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
        
    swing_up = (df['AFS_21'] > df['AFS_55']) & (df['AFS_21'].shift(1) <= df['AFS_55'].shift(1))
    swing_indices = df[swing_up].index
    
    results = []
    
    for idx in swing_indices:
        loc = df.index.get_loc(idx)
        if loc < 720 or loc + 120 >= len(df):
            continue
            
        row = df.iloc[loc]
        
        # 1. Identify the Ignition Layer (k_ignite)
        # Which MTF period had the lowest Bandwidth Percentile?
        bw_pcts = {p: row[f'BW_Pct_{p}'] for p in periods}
        
        # Skip if na
        if any(pd.isna(v) for v in bw_pcts.values()):
            continue
            
        k_ignite = min(bw_pcts, key=bw_pcts.get)
        min_bw_pct = bw_pcts[k_ignite]
        
        # We only care if it was actually squeezed (e.g., < 20th percentile)
        if min_bw_pct > 0.2:
            continue
            
        # 2. Identify the Target Layer (k_target)
        # We look ahead 120 hours. What is the highest SMA period that the price touched from below?
        # A touch means price > SMA. 
        # We want the HIGHEST period SMA that was breached.
        window = df.iloc[loc:loc+120]
        max_price = window['high'].max()
        
        k_target = None
        # Check from largest to smallest
        for p in reversed(periods):
            # If the max price in the next 120 hours exceeded the SMA value AT entry
            # (or the max of the SMA in that window)
            sma_max_in_window = window[f'SMA_{p}'].max()
            # Ensure the SMA was actually ABOVE the price at entry (it was a ceiling)
            if row[f'SMA_{p}'] > row['close']:
                if max_price >= sma_max_in_window:
                    k_target = p
                    break # Found the highest period breached
                    
        if k_target is not None:
            results.append({
                'k_ignite': k_ignite,
                'k_target': k_target
            })
            
    res_df = pd.DataFrame(results)
    print(f"Analyzed {len(res_df)} significant squeezed swings.")
    
    if len(res_df) == 0:
        print("No valid swings found.")
        return
        
    # Create Cross Tabulation (Heatmap)
    heatmap_data = pd.crosstab(res_df['k_ignite'], res_df['k_target'], normalize='index') * 100
    
    # Ensure all periods are in index and columns for a square-ish matrix
    for p in periods:
        if p not in heatmap_data.index:
            heatmap_data.loc[p] = 0
        if p not in heatmap_data.columns:
            heatmap_data[p] = 0
            
    heatmap_data = heatmap_data.reindex(index=periods, columns=periods).fillna(0)
    
    # Plotting
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 8))
    
    sns.heatmap(heatmap_data, annot=True, fmt=".1f", cmap="magma", cbar_kws={'label': 'Probability (%)'}, ax=ax)
    
    ax.set_title("The Kinetic Hierarchy: Dynamic Target Resolution\nHow Squeeze Layer determines the Target Layer", color='white', fontsize=14)
    ax.set_xlabel("Target Layer ($k_{target}$ SMA breached)", fontsize=12)
    ax.set_ylabel("Ignition Layer ($k_{ignite}$ most squeezed MTF)", fontsize=12)
    
    # Draw a line showing the diagonal (Target = Ignition)
    ax.plot([0, len(periods)], [0, len(periods)], color='cyan', linestyle='--', alpha=0.5, label='1:1 Ratio')
    
    plt.tight_layout()
    plt.savefig("kinetic_hierarchy_heatmap.png", dpi=300)
    print("Saved kinetic_hierarchy_heatmap.png")

if __name__ == '__main__':
    main()
