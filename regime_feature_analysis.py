import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from lightgbm import LGBMRegressor

from src.data_loader import load_1h_data, DISCOVERY_START, DISCOVERY_END
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H

TARGET_HORIZON_1H = 6

def create_regimes(df: pd.DataFrame) -> pd.DataFrame:
    """
    レジームを定義する: ボラティリティ (HV_24) と トレンド強度 (FIB_11_SMA_slope)
    """
    if 'HV_24' not in df.columns or 'FIB_11_SMA_slope' not in df.columns:
        print("Required features for regime splitting not found.")
        return df

    hv_median = df['HV_24'].median()
    # 144期間SMAの傾きの絶対値の割合でトレンド強度を測る
    trend_strength = (df['FIB_11_SMA_slope'].abs() / df['close']).rolling(24).mean()
    trend_median = trend_strength.median()

    df['volatility_regime'] = np.where(df['HV_24'] > hv_median, 'High_Vol', 'Low_Vol')
    df['trend_regime'] = np.where(trend_strength > trend_median, 'Trend', 'Range')
    
    df['regime_label'] = df['volatility_regime'] + "_" + df['trend_regime']
    return df

def run_analysis():
    print("Loading 1h data (Discovery period)...")
    df = load_1h_data(include_holdout=False)
    df = df.loc[DISCOVERY_START:DISCOVERY_END].copy()

    print("Calculating base features (FIB/AFS)...")
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    
    print("Calculating diverse features (Vol/Mom/Time)...")
    df = calculate_diverse_features(df)

    # ターゲット (6時間後のリターン)
    df['target_return'] = df['close'].shift(-TARGET_HORIZON_1H) / df['close'] - 1
    
    df.dropna(subset=['target_return'], inplace=True)
    
    print("Assigning regimes...")
    df = create_regimes(df)

    # 分析対象の特徴量
    diverse_features = [
        'ATR_14', 'ATR_ratio', 'HV_24', 'BB_width_20',
        'RSI_14', 'MACD_line', 'MACD_hist', 'hour_of_day', 'day_of_week'
    ]
    # 一部のSMA, Stoch特徴量を混ぜて比較
    base_features = [
        'FIB_5_SMA_dist', 'FIB_8_SMA_dist', 'FIB_11_SMA_dist',
        'FIB_3_stoch_d', 'FIB_6_stoch_d', 'AFS_1_19'
    ]
    
    all_features = diverse_features + base_features
    
    # 欠損値を含む行を削除
    df.dropna(subset=all_features, inplace=True)

    regimes = df['regime_label'].unique()
    print(f"Found regimes: {regimes}")

    # 特徴量重要度を格納するデータフレーム
    importance_df_list = []

    os.makedirs("results", exist_ok=True)
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()

    for idx, regime in enumerate(sorted(regimes)):
        regime_df = df[df['regime_label'] == regime]
        print(f"Training LightGBM for {regime} (n={len(regime_df)})")
        
        X = regime_df[all_features]
        # 回帰でリターン予測に対する寄与を測る
        y = regime_df['target_return']

        model = LGBMRegressor(n_estimators=100, max_depth=4, random_state=42, n_jobs=-1)
        model.fit(X, y)
        
        importances = model.feature_importances_
        # 正規化
        importances = importances / importances.sum()
        
        for f_name, imp in zip(all_features, importances):
            importance_df_list.append({
                'Regime': regime,
                'Feature': f_name,
                'Importance': imp
            })
            
        # Plot
        ax = axes[idx]
        sorted_indices = np.argsort(importances)
        
        # 色分け (新しい特徴量: オレンジ, 従来の特徴量: 青)
        colors = ['orange' if all_features[i] in diverse_features else 'steelblue' for i in sorted_indices]
        
        ax.barh(range(len(all_features)), importances[sorted_indices], color=colors)
        ax.set_yticks(range(len(all_features)))
        ax.set_yticklabels([all_features[i] for i in sorted_indices])
        ax.set_title(f'Feature Importance in {regime}')
        ax.set_xlabel('Normalized Importance')

    plt.tight_layout()
    plt.savefig("results/regime_feature_importance.png")
    print("Saved results/regime_feature_importance.png")

    # 相関分析のヒートマップも追加
    print("Generating correlation heatmap across regimes...")
    fig_corr, axes_corr = plt.subplots(2, 2, figsize=(18, 14))
    axes_corr = axes_corr.flatten()
    
    for idx, regime in enumerate(sorted(regimes)):
        regime_df = df[df['regime_label'] == regime]
        corr = regime_df[all_features + ['target_return']].corr()
        
        # target_returnとの相関のみを抽出して棒グラフ化
        target_corr = corr['target_return'].drop('target_return').sort_values()
        
        ax = axes_corr[idx]
        colors = ['red' if val < 0 else 'green' for val in target_corr.values]
        ax.barh(target_corr.index, target_corr.values, color=colors)
        ax.set_title(f'Correlation with 6h Return ({regime})')
        ax.axvline(0, color='black', linewidth=0.8)

    plt.tight_layout()
    plt.savefig("results/regime_feature_correlation.png")
    print("Saved results/regime_feature_correlation.png")

if __name__ == "__main__":
    run_analysis()
