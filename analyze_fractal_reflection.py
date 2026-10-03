import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

def add_bb_features(df, periods):
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        df[f'BB_U_{p}'] = sma + 2 * std
        df[f'BB_L_{p}'] = sma - 2 * std
        df[f'BB_M_{p}'] = sma
        df[f'PCTB_{p}'] = (df['close'] - df[f'BB_L_{p}']) / (df[f'BB_U_{p}'] - df[f'BB_L_{p}'] + 1e-8)
    return df

def plot_reflection_state(df, state_mask, title, filename):
    # Find a contiguous block where the state is true
    state_indices = df[state_mask].index
    if len(state_indices) == 0:
        print(f"No data found for {title}")
        return
        
    # Find the longest contiguous block
    blocks = []
    current_block = [state_indices[0]]
    for idx in state_indices[1:]:
        if (idx - current_block[-1]) <= pd.Timedelta(hours=2):
            current_block.append(idx)
        else:
            blocks.append(current_block)
            current_block = [idx]
    blocks.append(current_block)
    
    longest_block = max(blocks, key=len)
    
    # Take a nice zoom window around the block
    start = longest_block[0] - pd.Timedelta(days=5)
    end = longest_block[-1] + pd.Timedelta(days=5)
    
    zoom = df.loc[start:end]
    
    plt.figure(figsize=(16, 10))
    # Plot price
    plt.plot(zoom.index, zoom['close'], color='white', linewidth=1.5, label='Close')
    
    # k=55 (Short) BB
    plt.plot(zoom.index, zoom['BB_U_55'], color='cyan', linewidth=1, linestyle='--', alpha=0.7, label='55-BB Upper')
    plt.plot(zoom.index, zoom['BB_L_55'], color='cyan', linewidth=1, linestyle='--', alpha=0.7, label='55-BB Lower')
    
    # k+1=144 (Medium) BB
    plt.plot(zoom.index, zoom['BB_U_144'], color='purple', linewidth=2, label='144-BB Upper')
    plt.plot(zoom.index, zoom['BB_M_144'], color='purple', linewidth=2, linestyle='-.', label='144-SMA (Middle)')
    plt.plot(zoom.index, zoom['BB_L_144'], color='purple', linewidth=2, label='144-BB Lower')
    
    # k+2=377 (Macro) BB bounds
    plt.plot(zoom.index, zoom['BB_U_377'], color='red', linewidth=3, alpha=0.5, label='377-BB Upper')
    plt.plot(zoom.index, zoom['BB_L_377'], color='red', linewidth=3, alpha=0.5, label='377-BB Lower')
    
    # Highlight the state
    plt.axvspan(longest_block[0], longest_block[-1], color='lime', alpha=0.1, label='State Active Zone')
    
    plt.title(f"{title}\nObserve how Price/55-BB bounces against 144-BB and 377-BB", fontsize=16)
    plt.legend(loc='upper left', frameon=True, facecolor='black', edgecolor='white')
    plt.grid(True, alpha=0.2)
    plt.gca().set_facecolor('black')
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    plt.close()
    print(f"Saved {filename}")

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    
    print("Calculating BBs (55, 144, 377)...")
    df = add_bb_features(df, [55, 144, 377])
    
    # Calculate Slopes
    df['SLOPE_144'] = df['BB_M_144'].diff(24)
    df['SLOPE_377'] = df['BB_M_377'].diff(48)
    
    # State 1: k+1 (144) is Trending UP
    state_1 = (df['SLOPE_144'] > 50) & (df['PCTB_144'] > 0.5)
    
    # State 2: k+1 (144) is Trending DOWN
    state_2 = (df['SLOPE_144'] < -50) & (df['PCTB_144'] < 0.5)
    
    # State 3: k+2 (377) is Ranging at Bottom
    state_3 = (df['SLOPE_377'].abs() < 20) & (df['PCTB_377'] < 0.2) & (df['PCTB_144'] < 0.5)
    
    # State 4: k+2 (377) is Ranging at Top
    state_4 = (df['SLOPE_377'].abs() < 20) & (df['PCTB_377'] > 0.8) & (df['PCTB_144'] > 0.5)
    
    plot_reflection_state(df, state_1, "State 1: k+1 (144) Uptrend Reflection", "fractal_state_1_uptrend.png")
    plot_reflection_state(df, state_2, "State 2: k+1 (144) Downtrend Reflection", "fractal_state_2_downtrend.png")
    plot_reflection_state(df, state_3, "State 3: k+2 (377) Floor Range Ping-Pong", "fractal_state_3_floor_range.png")
    plot_reflection_state(df, state_4, "State 4: k+2 (377) Ceiling Range Ping-Pong", "fractal_state_4_ceiling_range.png")

if __name__ == '__main__':
    main()
