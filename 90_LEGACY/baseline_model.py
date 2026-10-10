import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from lightgbm import LGBMClassifier

from src.data_loader import load_1h_data, DISCOVERY_START, DISCOVERY_END, VALIDATION_START, VALIDATION_END
from src.features import calculate_fib_features
from src.config import MAX_FIB_INDEX_1H, BASE_COST

# ホライズンを短く設定し、リスクを低減する
TARGET_HORIZON_1H = 6 

def run():
    print("Loading data...")
    df = load_1h_data(include_holdout=True)
    print("Calculating features...")
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)

    # 短期リターン
    df['target_return'] = df['close'].shift(-TARGET_HORIZON_1H) / df['close'] - 1
    df.dropna(subset=['target_return'], inplace=True)

    # 厳選した特徴量のみを使用し過学習を防ぐ
    selected_features = [
        'FIB_5_SMA_dist', 'FIB_8_SMA_dist', 'FIB_11_SMA_dist', 
        'FIB_5_SMA_slope', 'FIB_8_SMA_slope',
        'FIB_3_stoch_d', 'FIB_6_stoch_d', 'AFS_1_19'
    ]
    
    # 欠損値の削除
    df.dropna(subset=selected_features, inplace=True)

    # Stage 1: レジーム（ボラティリティがあるか）
    # 6時間で1%以上動くかどうか
    df['regime_target'] = (df['target_return'].abs() > 0.01).astype(int)

    # Stage 2: 方向
    df['direction_target'] = (df['target_return'] > 0).astype(int)

    # データ分割
    train_mask = (df.index >= DISCOVERY_START) & (df.index <= DISCOVERY_END)
    val_mask = (df.index >= VALIDATION_START) & (df.index <= VALIDATION_END)

    train_df = df[train_mask]
    val_df = df[val_mask]

    X_train = train_df[selected_features]
    y_train_regime = train_df['regime_target']
    y_train_dir = train_df['direction_target']

    X_val = val_df[selected_features]
    y_val_regime = val_df['regime_target']
    y_val_dir = val_df['direction_target']

    print("Training Stage 1...")
    # 過学習を防ぐための強力な正則化
    model_regime = LGBMClassifier(n_estimators=50, max_depth=3, learning_rate=0.01, min_child_samples=100, random_state=42)
    model_regime.fit(X_train, y_train_regime)

    print("Training Stage 2...")
    favorable_mask = (y_train_regime == 1)
    model_dir = LGBMClassifier(n_estimators=50, max_depth=3, learning_rate=0.01, min_child_samples=100, random_state=42)
    model_dir.fit(X_train[favorable_mask], y_train_dir[favorable_mask])

    print("Simulating trading...")
    val_df = val_df.copy()
    val_df['prob_regime'] = model_regime.predict_proba(X_val)[:, 1]
    val_df['prob_dir'] = model_dir.predict_proba(X_val)[:, 1]

    # より厳格なフィルター
    REGIME_THRESHOLD = 0.50
    val_df['signal'] = 0

    long_cond = (val_df['prob_regime'] > REGIME_THRESHOLD) & (val_df['prob_dir'] > 0.55)
    val_df.loc[long_cond, 'signal'] = 1

    short_cond = (val_df['prob_regime'] > REGIME_THRESHOLD) & (val_df['prob_dir'] < 0.45)
    val_df.loc[short_cond, 'signal'] = -1

    # シミュレーションロジック
    # 対象期間分ポジションをホールドする
    val_df['position'] = val_df['signal'].replace(0, np.nan).fillna(method='ffill', limit=TARGET_HORIZON_1H-1).fillna(0)
    
    # 時間ごとのリターン
    val_df['hourly_return'] = val_df['close'].pct_change().shift(-1).fillna(0)
    
    # 毎時のポジションによるリターン
    val_df['raw_strategy_return'] = val_df['position'] * val_df['hourly_return']
    
    # 取引コスト（ポジションが変わったタイミングで発生）
    val_df['trade_size'] = val_df['position'].diff().abs().fillna(0)
    val_df['cost'] = val_df['trade_size'] * BASE_COST
    
    val_df['strategy_return'] = val_df['raw_strategy_return'] - val_df['cost']

    # 累積計算
    val_df['cum_return'] = (1 + val_df['strategy_return']).cumprod()
    val_df['bnh_return'] = (1 + val_df['hourly_return']).cumprod()
    
    val_df['peak'] = val_df['cum_return'].cummax()
    val_df['drawdown'] = (val_df['cum_return'] - val_df['peak']) / val_df['peak']

    total_return = val_df['cum_return'].iloc[-1] - 1
    max_dd = val_df['drawdown'].min()
    
    returns = val_df['strategy_return']
    sharpe = np.sqrt(24 * 365) * returns.mean() / returns.std() if returns.std() > 0 else 0
    win_rate = (returns[returns != 0] > 0).mean() if len(returns[returns != 0]) > 0 else 0
    num_trades = val_df['trade_size'].sum()

    print("=== Validation Results ===")
    print(f"Total Return: {total_return:.2%}")
    print(f"Max Drawdown: {max_dd:.2%}")
    print(f"Sharpe Ratio: {sharpe:.2f}")
    print(f"Win Rate: {win_rate:.2%}")
    print(f"Number of Trades: {num_trades}")

    os.makedirs("results", exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(12, 15))
    axes[0].plot(val_df.index, val_df['cum_return'], label='Strategy')
    axes[0].plot(val_df.index, val_df['bnh_return'], label='Buy and Hold', alpha=0.7)
    axes[0].set_title('Cumulative Return (Validation)')
    axes[0].legend()
    axes[0].grid()

    axes[1].plot(val_df.index, val_df['drawdown'], color='red')
    axes[1].fill_between(val_df.index, val_df['drawdown'], 0, color='red', alpha=0.3)
    axes[1].set_title('Drawdown')
    axes[1].grid()

    importances = model_dir.feature_importances_
    indices = np.argsort(importances)
    axes[2].barh(range(len(indices)), importances[indices])
    axes[2].set_yticks(range(len(indices)))
    axes[2].set_yticklabels([selected_features[i] for i in indices])
    axes[2].set_title('Stage 2 Feature Importances')

    plt.tight_layout()
    plt.savefig("results/baseline_results.png")
    print("Saved results/baseline_results.png")

if __name__ == "__main__":
    run()
