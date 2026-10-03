import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from src.config import MAX_FIB_INDEX_1H
from src.data_loader import load_discovery_data
from src.features import calculate_fib_features

OUTPUT_DIR = r"D:\work\AI-Trade\SakanaAISystemTrade\reports\EDA\01_feature_observation_SMA_BB"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def plot_regime(df, title, start_date, end_date, filename):
    subset = df.loc[start_date:end_date]
    if subset.empty:
        print(f"No data for {title} ({start_date} - {end_date})")
        return
        
    fig, axes = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [3, 1]})
    
    # 1. Price and SMAs
    axes[0].plot(subset.index, subset['close'], label='Close Price', color='black', linewidth=1.5)
    
    # 選択したSMAのプロット (短期〜長期の代表を抽出してグラフの散らかりを防ぐ)
    # FIB_5=8, FIB_8=34, FIB_11=144, FIB_14=610, FIB_17=2584
    sma_cols = {
        'FIB_5_SMA': 'SMA(8) Short',
        'FIB_8_SMA': 'SMA(34) Mid-Short',
        'FIB_11_SMA': 'SMA(144) Mid',
        'FIB_14_SMA': 'SMA(610) Long',
        'FIB_17_SMA': 'SMA(2584) Very Long'
    }
    
    colors = sns.color_palette("husl", len(sma_cols))
    for (col, label), color in zip(sma_cols.items(), colors):
        if col in subset.columns:
            axes[0].plot(subset.index, subset[col], label=label, color=color, linewidth=1)
            
    # 中期BBの描画 (FIB_11=144) をサポレジの参考として追加
    if 'FIB_11_BB_up' in subset.columns:
        axes[0].fill_between(subset.index, subset['FIB_11_BB_down'], subset['FIB_11_BB_up'], color='gray', alpha=0.1, label='BB(144) ±2σ')
            
    axes[0].set_title(f"{title} - Price & Hierarchical SMAs")
    axes[0].legend(loc='upper left')
    axes[0].grid(True, alpha=0.3)
    
    # 2. SMA Slopes (傾きの揃い具合 = パーフェクトオーダーの確認)
    for (col, label), color in zip(sma_cols.items(), colors):
        slope_col = col.replace('_SMA', '_SMA_slope')
        if slope_col in subset.columns:
            # 値のスケールが異なるため、簡易的に見やすくする (100を掛けるなど)
            axes[1].plot(subset.index, subset[slope_col], label=label+' slope', color=color, linewidth=1)
            
    axes[1].axhline(0, color='black', linestyle='--', alpha=0.5)
    axes[1].set_title("SMA Slopes (0以上で上向き、0以下で下向き)")
    axes[1].legend(loc='upper left')
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, filename))
    plt.close()
    print(f"Saved {filename}")

def main():
    print("Loading data for EDA...")
    df_1h = load_discovery_data()
    print("Calculating features...")
    df_features = calculate_fib_features(df_1h, MAX_FIB_INDEX_1H)
    
    print("Generating plots for specific regimes...")
    # 代表的な相場レジームをサンプリング
    # 1. 強い上昇トレンド
    plot_regime(df_features, "Strong Uptrend (2020-10 to 2021-02)", "2020-10-01", "2021-02-01", "01_uptrend.png")
    
    # 2. 強い下降トレンド
    plot_regime(df_features, "Strong Downtrend (2022-04 to 2022-08)", "2022-04-01", "2022-08-01", "02_downtrend.png")
    
    # 3. レンジ・もみ合い
    plot_regime(df_features, "Range / Choppy (2023-05 to 2023-09)", "2023-05-01", "2023-09-01", "03_range.png")
    
    # 4. 短期SMAが長期SMAを下回った後の回帰/反発局面
    plot_regime(df_features, "Mean Reversion / Bounce (2023-08 to 2024-02)", "2023-08-01", "2024-02-01", "04_reversion.png")
    
    print("EDA for SMA/BB completed.")

if __name__ == "__main__":
    main()
