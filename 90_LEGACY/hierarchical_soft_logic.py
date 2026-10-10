import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from lightgbm import LGBMClassifier

from src.data_loader import load_1h_data, DISCOVERY_START, DISCOVERY_END, VALIDATION_START, VALIDATION_END
from src.features import calculate_fib_features
from src.config import MAX_FIB_INDEX_1H, BASE_COST

TARGET_HORIZON_1H = 6

def build_soft_logic_features(df: pd.DataFrame, k_long: int=11, k_short: int=5, memory_window: int=21) -> pd.DataFrame:
    """
    階層構造の連続スコア（Soft Logic）と記憶（Memory）特徴量を構築する
    k_long=11(144), k_long+1=12(233)
    k_short=5(8)
    """
    df = df.copy()
    
    kl_p1 = f"FIB_{k_long + 1}_"
    kl    = f"FIB_{k_long}_"
    ks    = f"FIB_{k_short}_"
    
    # 1. 長期トレンドスコア (傾きを価格で正規化)
    df['Soft_LT_Trend'] = (df[f'{kl_p1}SMA_slope'] / df['close']) * 1000
    
    # 2. 長期サポート/レジスタンス接近スコア (BB_pos)
    # BB_pos = 0 が下限（サポート）、1 が上限（レジスタンス）
    df['Soft_LT_Pos'] = df[f'{kl_p1}BB_pos']
    
    # 3. 記憶 (Memory) 特徴量
    # 過去N時間における最も深いサポート到達(最小値)とレジスタンス到達(最大値)
    df[f'Soft_LT_Pos_Min_{memory_window}h'] = df['Soft_LT_Pos'].rolling(window=memory_window).min()
    df[f'Soft_LT_Pos_Max_{memory_window}h'] = df['Soft_LT_Pos'].rolling(window=memory_window).max()
    
    # 4. 中期の過熱度スコア
    df['Soft_Mid_Stoch'] = df[f'{kl}stoch_d']
    
    # 5. 短期トリガースコア
    df['Soft_ST_Stoch'] = df[f'{ks}stoch_d']
    df['Soft_ST_Stoch_Slope'] = df[f'{ks}stoch_d'].diff()
    
    features = [
        'Soft_LT_Trend', 
        'Soft_LT_Pos', 
        f'Soft_LT_Pos_Min_{memory_window}h', 
        f'Soft_LT_Pos_Max_{memory_window}h',
        'Soft_Mid_Stoch', 
        'Soft_ST_Stoch', 
        'Soft_ST_Stoch_Slope'
    ]
    return df, features

def run():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    
    # 6時間後のリターン
    df['target_return'] = df['close'].shift(-TARGET_HORIZON_1H) / df['close'] - 1
    df.dropna(subset=['target_return'], inplace=True)
    
    print("Building Soft Logic & Memory features...")
    df, feature_cols = build_soft_logic_features(df, k_long=11, k_short=5, memory_window=21)
    df.dropna(subset=feature_cols, inplace=True)
    
    # Stage 1: レジーム予測ではなく、直接方向(Long/Short)を予測するモデルに統合
    # 非常に浅い木を使うことで、ルールベース的なAND/OR条件をファジィに見つけさせる
    df['direction_target'] = (df['target_return'] > 0).astype(int)
    
    train_mask = (df.index >= DISCOVERY_START) & (df.index <= DISCOVERY_END)
    val_mask = (df.index >= VALIDATION_START) & (df.index <= VALIDATION_END)
    
    X_train = df.loc[train_mask, feature_cols]
    y_train = df.loc[train_mask, 'direction_target']
    
    X_val = df.loc[val_mask, feature_cols]
    y_val = df.loc[val_mask, 'direction_target']
    
    print("Training Shallow LightGBM (Depth=3) on hierarchical features...")
    model = LGBMClassifier(n_estimators=100, max_depth=3, learning_rate=0.01, min_child_samples=50, random_state=42)
    model.fit(X_train, y_train)
    
    val_df = df[val_mask].copy()
    val_df['prob_long'] = model.predict_proba(X_val)[:, 1]
    
    # 閾値でシグナル化（自信があるときだけエントリー）
    # Soft Logicによる複合スコアの最上位・最下位
    long_thresh = val_df['prob_long'].quantile(0.90)  # 上位10%
    short_thresh = val_df['prob_long'].quantile(0.10) # 下位10%
    
    val_df['signal'] = 0
    val_df.loc[val_df['prob_long'] > long_thresh, 'signal'] = 1
    val_df.loc[val_df['prob_long'] < short_thresh, 'signal'] = -1
    
    # ポジションホールド (6h)
    val_df['position'] = val_df['signal'].replace(0, np.nan).fillna(method='ffill', limit=TARGET_HORIZON_1H-1).fillna(0)
    
    val_df['hourly_return'] = val_df['close'].pct_change().shift(-1).fillna(0)
    val_df['raw_strategy_return'] = val_df['position'] * val_df['hourly_return']
    
    # 取引コスト
    val_df['trade_size'] = val_df['position'].diff().abs().fillna(0)
    val_df['cost'] = val_df['trade_size'] * BASE_COST
    val_df['strategy_return'] = val_df['raw_strategy_return'] - val_df['cost']
    
    val_df['cum_return'] = (1 + val_df['strategy_return']).cumprod()
    val_df['bnh_return'] = (1 + val_df['hourly_return']).cumprod()
    
    val_df['peak'] = val_df['cum_return'].cummax()
    val_df['drawdown'] = (val_df['cum_return'] - val_df['peak']) / val_df['peak']
    
    total_return = val_df['cum_return'].iloc[-1] - 1
    max_dd = val_df['drawdown'].min()
    
    returns = val_df['strategy_return']
    sharpe = np.sqrt(24 * 365) * returns.mean() / returns.std() if returns.std() > 0 else 0
    num_trades = val_df['trade_size'].sum()
    
    print("=== Validation Results (Soft Logic + Memory) ===")
    print(f"Total Return: {total_return:.2%}")
    print(f"Max Drawdown: {max_dd:.2%}")
    print(f"Sharpe Ratio: {sharpe:.2f}")
    print(f"Number of Trades: {num_trades}")
    
    os.makedirs("results", exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(12, 15))
    axes[0].plot(val_df.index, val_df['cum_return'], label='Strategy')
    axes[0].plot(val_df.index, val_df['bnh_return'], label='Buy and Hold', alpha=0.7)
    axes[0].set_title('Cumulative Return (Soft Logic + Memory)')
    axes[0].legend()
    axes[0].grid()
    
    axes[1].plot(val_df.index, val_df['drawdown'], color='red')
    axes[1].fill_between(val_df.index, val_df['drawdown'], 0, color='red', alpha=0.3)
    axes[1].set_title('Drawdown')
    axes[1].grid()
    
    importances = model.feature_importances_
    indices = np.argsort(importances)
    axes[2].barh(range(len(indices)), importances[indices])
    axes[2].set_yticks(range(len(indices)))
    axes[2].set_yticklabels([feature_cols[i] for i in indices])
    axes[2].set_title('Shallow LightGBM Feature Importances')
    
    plt.tight_layout()
    plt.savefig("results/hierarchical_soft_logic_results.png")
    print("Saved results/hierarchical_soft_logic_results.png")

if __name__ == "__main__":
    run()
