import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

from src.data_loader import load_1h_data

def investigate_2024_12_22():
    print("Loading data...")
    df = load_1h_data()
    
    # Calculate Standard Deviations for multiple timeframes
    lengths = [13, 21, 34, 55, 89, 144, 233, 377]
    for L in lengths:
        df[f'STD_{L}'] = df['close'].rolling(L).std()
        df[f'SMA_{L}'] = df['close'].rolling(L).mean()
        
    # Macro BB Ratio
    df['Macro_BB_Ratio'] = np.log(df['STD_233'] / df['STD_144'])
    
    # Micro BB Ratio
    df['Micro_BB_Ratio'] = np.log(df['STD_34'] / df['STD_21'])
    
    # Mid BB Ratio
    df['Mid_BB_Ratio'] = np.log(df['STD_89'] / df['STD_55'])
    
    # Extract the timeframe around 2024-12-22
    # Ensure index is datetime to slice easily
    # If the index is already datetime in data_loader, this will work.
    try:
        # Looking from 2024-12-15 to 2024-12-30
        target_df = df.loc['2024-12-15':'2024-12-30'].copy()
    except:
        # If not indexed by datetime string, fallback to finding the row
        print("Fallback index slicing...")
        target_df = df.iloc[-5000:].copy() # fallback
        
    if target_df.empty:
        print("Could not find date range, plotting last 1000 bars.")
        target_df = df.iloc[-1000:].copy()
        
    plt.figure(figsize=(15, 12))
    
    plt.subplot(3, 1, 1)
    plt.plot(target_df.index, target_df['close'], color='black', label='Close')
    plt.plot(target_df.index, target_df['SMA_34'], color='blue', alpha=0.5, label='SMA 34 (Micro)')
    plt.plot(target_df.index, target_df['SMA_233'], color='red', alpha=0.5, label='SMA 233 (Macro)')
    plt.title("Price Action around 2024-12-22")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.subplot(3, 1, 2)
    plt.plot(target_df.index, target_df['Macro_BB_Ratio'], color='red', label='Macro BB Ratio (233/144)')
    plt.axhline(0, color='black', linestyle='--')
    plt.title("Macro BB Ratio (Tension)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.subplot(3, 1, 3)
    plt.plot(target_df.index, target_df['Micro_BB_Ratio'], color='blue', label='Micro BB Ratio (34/21)')
    plt.plot(target_df.index, target_df['Mid_BB_Ratio'], color='green', label='Mid BB Ratio (89/55)')
    plt.axhline(0, color='black', linestyle='--')
    plt.title("Micro & Mid BB Ratios (Timing)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    os.makedirs("results/investigation", exist_ok=True)
    plt.savefig("results/investigation/2024_12_22_analysis.png")
    plt.close()
    print("Saved: results/investigation/2024_12_22_analysis.png")

if __name__ == "__main__":
    investigate_2024_12_22()
