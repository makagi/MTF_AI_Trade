import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from src.config import MAX_FIB_INDEX_1H
from src.data_loader import load_discovery_data
from src.features import calculate_fib_features

OUTPUT_DIR = r"D:\work\AI-Trade\SakanaAISystemTrade\reports\EDA\02_feature_observation_stoch_AFS"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def plot_stoch_afs(df, title, start_date, end_date, filename):
    subset = df.loc[start_date:end_date]
    if subset.empty:
        print(f"No data for {title} ({start_date} - {end_date})")
        return
        
    fig, axes = plt.subplots(3, 1, figsize=(16, 15), gridspec_kw={'height_ratios': [2, 1.5, 1.5]})
    
    # 1. Price for context
    axes[0].plot(subset.index, subset['close'], label='Close Price', color='black', linewidth=1.5)
    if 'FIB_8_SMA' in subset.columns: # SMA 34
        axes[0].plot(subset.index, subset['FIB_8_SMA'], label='SMA(34)', color='blue', alpha=0.5)
    if 'FIB_11_SMA' in subset.columns: # SMA 144
        axes[0].plot(subset.index, subset['FIB_11_SMA'], label='SMA(144)', color='red', alpha=0.5)
    axes[0].set_title(f"{title} - Price Context")
    axes[0].legend(loc='upper left')
    axes[0].grid(True, alpha=0.3)
    
    # 2. stoch_d (短期〜長期)
    # FIB_3=3, FIB_6=13, FIB_9=55, FIB_12=233
    stoch_cols = {
        'FIB_3_stoch_d': 'stoch_d(3) Short',
        'FIB_6_stoch_d': 'stoch_d(13) Mid-Short',
        'FIB_9_stoch_d': 'stoch_d(55) Mid',
        'FIB_12_stoch_d': 'stoch_d(233) Long'
    }
    colors = sns.color_palette("husl", len(stoch_cols))
    for (col, label), color in zip(stoch_cols.items(), colors):
        if col in subset.columns:
            axes[1].plot(subset.index, subset[col], label=label, color=color, linewidth=1.2)
            
    axes[1].axhline(80, color='red', linestyle='--', alpha=0.5)
    axes[1].axhline(20, color='green', linestyle='--', alpha=0.5)
    axes[1].set_title("stoch_d (Hierarchy & Reversals)")
    axes[1].legend(loc='upper left')
    axes[1].grid(True, alpha=0.3)
    axes[1].set_ylim(0, 100)
    
    # 3. AFS (Average Fibonacci Stoch_d)
    # n=1 (all terms), n=5 (from 8 onwards), n=10 (from 89 onwards)
    afs_cols = {
        f'AFS_1_{MAX_FIB_INDEX_1H}': 'AFS(1~19) All-term Avg',
        f'AFS_5_{MAX_FIB_INDEX_1H}': 'AFS(5~19) Mid-Long Avg',
        f'AFS_10_{MAX_FIB_INDEX_1H}': 'AFS(10~19) Long Avg'
    }
    colors_afs = ['purple', 'orange', 'teal']
    for (col, label), color in zip(afs_cols.items(), colors_afs):
        if col in subset.columns:
            axes[2].plot(subset.index, subset[col], label=label, color=color, linewidth=1.5)
            
    axes[2].axhline(80, color='red', linestyle='--', alpha=0.5)
    axes[2].axhline(20, color='green', linestyle='--', alpha=0.5)
    axes[2].set_title("AFS (Rhythm & Correlation)")
    axes[2].legend(loc='upper left')
    axes[2].grid(True, alpha=0.3)
    axes[2].set_ylim(0, 100)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, filename))
    plt.close()
    print(f"Saved {filename}")

def main():
    print("Loading data for EDA...")
    df_1h = load_discovery_data()
    print("Calculating features...")
    df_features = calculate_fib_features(df_1h, MAX_FIB_INDEX_1H)
    
    print("Generating plots for specific regimes (stoch_d & AFS)...")
    
    # 1. 強い上昇トレンドの押し目
    plot_stoch_afs(df_features, "Strong Uptrend Pullbacks (2020-10 to 2021-02)", "2020-10-01", "2021-02-01", "01_uptrend_pullbacks.png")
    
    # 2. 強い下降トレンドの戻り
    plot_stoch_afs(df_features, "Strong Downtrend Rallies (2022-04 to 2022-08)", "2022-04-01", "2022-08-01", "02_downtrend_rallies.png")
    
    # 3. レンジ・もみ合い
    plot_stoch_afs(df_features, "Range / Choppy (2023-05 to 2023-09)", "2023-05-01", "2023-09-01", "03_range.png")
    
    # 4. 大きな底打ち・反転局面 (2022末)
    plot_stoch_afs(df_features, "Major Reversal / Bottoming (2022-10 to 2023-02)", "2022-10-01", "2023-02-01", "04_major_reversal.png")
    
    print("EDA for stoch_d/AFS completed.")

if __name__ == "__main__":
    main()
