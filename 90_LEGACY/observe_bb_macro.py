import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

from src.data_loader import load_1h_data

def run_observation():
    print("Loading data for observation...")
    df = load_1h_data()
    df = df.iloc[-10000:].copy() # Use the last 10000 bars for clear observation
    
    # Fibonacci lengths
    L_k = 144  # k=11
    L_k1 = 233 # k=12
    L_k2 = 377 # k=13
    
    # 1. Calculate SMA and Volatility (StdDev)
    df['SMA_144'] = df['close'].rolling(L_k).mean()
    df['STD_144'] = df['close'].rolling(L_k).std()
    
    df['SMA_233'] = df['close'].rolling(L_k1).mean()
    df['STD_233'] = df['close'].rolling(L_k1).std()
    
    df['SMA_377'] = df['close'].rolling(L_k2).mean()
    df['STD_377'] = df['close'].rolling(L_k2).std()
    
    # ATR for normalization
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(14).mean()
    
    # 2. Long SMA Distance (Normalized by ATR)
    df['Long_SMA_Dist'] = (df['SMA_144'] - df['SMA_233']).abs() / df['ATR_14']
    
    # 3. BB Width Ratio (Log Volatility Ratio)
    # log( sigma_k+1 / sigma_k )
    df['BB_Ratio_Log'] = np.log(df['STD_233'] / df['STD_144'])
    
    # 4. Reverting vs Diverging states
    # Distance from price to macro SMA (233)
    df['Dist_to_Macro'] = (df['close'] - df['SMA_233']).abs()
    # Rate of change of distance
    df['d_Dist'] = df['Dist_to_Macro'] - df['Dist_to_Macro'].shift(3) # 3-hour momentum of distance
    
    df['State'] = np.where(df['d_Dist'] < 0, 'Reverting (回帰)', np.where(df['d_Dist'] > 0, 'Diverging (乖離)', 'Neutral'))
    
    df.dropna(inplace=True)
    
    os.makedirs("results/observations", exist_ok=True)
    
    # --- PLOT 1: Long SMA Distance vs Volatility ---
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df, x='Long_SMA_Dist', y='ATR_14', alpha=0.3, s=10)
    plt.title("Relationship: Long SMA Distance (144 vs 233) vs Volatility (ATR 14)")
    plt.xlabel("Distance between SMA(144) and SMA(233) [Normalized by ATR]")
    plt.ylabel("Volatility (ATR 14)")
    plt.grid(True, alpha=0.3)
    plt.savefig("results/observations/sma_dist_vs_volatility.png")
    plt.close()
    print("Saved: results/observations/sma_dist_vs_volatility.png")
    
    # --- PLOT 2: BB Ratio Distribution in Reverting vs Diverging States ---
    plt.figure(figsize=(10, 6))
    sns.kdeplot(data=df[df['State'] == 'Reverting (回帰)'], x='BB_Ratio_Log', label='Reverting (回帰)', fill=True, alpha=0.4, color='blue')
    sns.kdeplot(data=df[df['State'] == 'Diverging (乖離)'], x='BB_Ratio_Log', label='Diverging (乖離)', fill=True, alpha=0.4, color='red')
    plt.axvline(0, color='black', linestyle='--', alpha=0.5, label='Equilibrium (Ratio=1)')
    plt.title("BB Width Ratio (Log) Distribution by Macro State")
    plt.xlabel("Log( Std(233) / Std(144) )  [ +: Short-term Squeeze, -: Short-term Expand ]")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig("results/observations/bb_ratio_kde.png")
    plt.close()
    print("Saved: results/observations/bb_ratio_kde.png")
    
    # --- PLOT 3: Time Series Analysis of BB Ratio and Squeeze/Expand ---
    plot_df = df.iloc[-500:].copy() # Last 500 hours
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]})
    
    # Price and BBs
    ax1.plot(plot_df.index, plot_df['close'], color='black', label='Close')
    ax1.plot(plot_df.index, plot_df['SMA_144'], color='blue', label='SMA 144')
    ax1.fill_between(plot_df.index, plot_df['SMA_144'] - 2*plot_df['STD_144'], plot_df['SMA_144'] + 2*plot_df['STD_144'], color='blue', alpha=0.1, label='BB 144')
    
    ax1.plot(plot_df.index, plot_df['SMA_233'], color='red', label='SMA 233')
    ax1.fill_between(plot_df.index, plot_df['SMA_233'] - 2*plot_df['STD_233'], plot_df['SMA_233'] + 2*plot_df['STD_233'], color='red', alpha=0.1, label='BB 233')
    
    ax1.set_title("Price vs Multi-Timeframe Bollinger Bands (144 & 233)")
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # BB Ratio Log
    ax2.plot(plot_df.index, plot_df['BB_Ratio_Log'], color='purple', label='BB Ratio Log: log(Std233 / Std144)')
    ax2.axhline(0, color='black', linestyle='--')
    ax2.fill_between(plot_df.index, 0, plot_df['BB_Ratio_Log'], where=(plot_df['BB_Ratio_Log'] > 0), color='green', alpha=0.3, label='Macro > Micro (SQUEEZE)')
    ax2.fill_between(plot_df.index, 0, plot_df['BB_Ratio_Log'], where=(plot_df['BB_Ratio_Log'] < 0), color='orange', alpha=0.3, label='Micro > Macro (EXPAND)')
    ax2.set_title("Multi-Timeframe Squeeze/Expand Oscillator")
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig("results/observations/bb_time_series.png")
    plt.close()
    print("Saved: results/observations/bb_time_series.png")

    # --- PLOT 4: Phase Space Plot (Tension vs Velocity) ---
    plt.figure(figsize=(10, 8))
    # Distance: SMA_144 - SMA_233 (normalized)
    df['SMA_Dist_Signed'] = (df['SMA_144'] - df['SMA_233']) / df['ATR_14']
    # Velocity: derivative of distance
    df['SMA_Dist_Velocity'] = df['SMA_Dist_Signed'] - df['SMA_Dist_Signed'].shift(3)
    
    # Filter for the last 1000 points to make it readable
    phase_df = df.iloc[-1000:].copy()
    
    # Scatter plot mapped by Log Vol Ratio
    sc = plt.scatter(phase_df['SMA_Dist_Signed'], phase_df['SMA_Dist_Velocity'], 
                     c=phase_df['BB_Ratio_Log'], cmap='coolwarm', alpha=0.7, s=20)
    
    # Connect consecutive points to show the orbit
    plt.plot(phase_df['SMA_Dist_Signed'], phase_df['SMA_Dist_Velocity'], color='black', alpha=0.1, linewidth=0.5)
    
    plt.axhline(0, color='black', linestyle='--', alpha=0.5)
    plt.axvline(0, color='black', linestyle='--', alpha=0.5)
    plt.colorbar(sc, label="Log( Vol_233 / Vol_144 )  [Red=Squeeze, Blue=Expand]")
    plt.title("Phase Space: Macro Tension vs Velocity")
    plt.xlabel("X (Tension): Distance (SMA 144 - SMA 233) [in ATR]")
    plt.ylabel("Y (Velocity): 3H Change in Distance")
    plt.grid(True, alpha=0.3)
    
    plt.savefig("results/observations/phase_space.png")
    plt.close()
    print("Saved: results/observations/phase_space.png")

if __name__ == "__main__":
    run_observation()
