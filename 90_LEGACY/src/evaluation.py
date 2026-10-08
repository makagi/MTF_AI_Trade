import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
from src.config import BASE_COST

def simulate_trading(test_df: pd.DataFrame, preds: np.ndarray, threshold_long: float = 0.55, threshold_short: float = 0.45):
    """
    予測確率に基づいて取引をシミュレーションする
    """
    df = test_df.copy()
    df['pred_prob'] = preds
    
    # シグナル生成 (1: Long, -1: Short, 0: Neutral)
    # 自信があるときのみエントリーする
    df['signal'] = 0
    df.loc[df['pred_prob'] >= threshold_long, 'signal'] = 1
    df.loc[df['pred_prob'] <= threshold_short, 'signal'] = -1
    
    # 簡易リターン計算（対象期間をそのまま保有した場合）
    df['strategy_return'] = df['signal'] * df['target_return']
    
    # 取引コスト（エントリー/エグジットで発生）
    # シグナルが変化したときにコストを引く
    df['trades'] = df['signal'].diff().abs() > 0
    cost_per_trade = BASE_COST
    df.loc[df['trades'], 'strategy_return'] -= (cost_per_trade * 2) # 往復コスト
    
    # 累積リターン
    df['cum_return'] = (1 + df['strategy_return']).cumprod()
    df['bnh_return'] = (1 + df['target_return']).cumprod()
    
    # ドローダウン
    df['peak'] = df['cum_return'].cummax()
    df['drawdown'] = (df['cum_return'] - df['peak']) / df['peak']
    
    return df

def calculate_metrics(df: pd.DataFrame, timeframe_hours=1):
    returns = df['strategy_return']
    
    total_return = df['cum_return'].iloc[-1] - 1 if len(df) > 0 else 0
    max_dd = df['drawdown'].min() if len(df) > 0 else 0
    
    # 年率換算Sharpe ratio
    periods_per_year = (24 / timeframe_hours) * 365
    sharpe = np.sqrt(periods_per_year) * returns.mean() / returns.std() if returns.std() > 0 else 0
    
    win_rate = (returns > 0).mean()
    num_trades = df['trades'].sum()
    
    bnh_return = df['bnh_return'].iloc[-1] - 1 if len(df) > 0 else 0
    
    return {
        'Total Return': total_return,
        'Max Drawdown': max_dd,
        'Sharpe Ratio': sharpe,
        'Win Rate': win_rate,
        'Num Trades': num_trades,
        'Buy & Hold Return': bnh_return
    }

def plot_results(df: pd.DataFrame, model, feature_cols, save_path="results.png"):
    fig, axes = plt.subplots(3, 1, figsize=(12, 15))
    
    # 1. 累積リターン比較
    axes[0].plot(df.index, df['cum_return'], label='Strategy (OOS)', color='blue')
    axes[0].plot(df.index, df['bnh_return'], label='Buy & Hold', color='gray', alpha=0.7)
    axes[0].set_title('Cumulative Return (Out-of-Sample)')
    axes[0].legend()
    axes[0].grid(True)
    
    # 2. ドローダウン
    axes[1].plot(df.index, df['drawdown'], label='Drawdown', color='red')
    axes[1].fill_between(df.index, df['drawdown'], 0, color='red', alpha=0.3)
    axes[1].set_title('Drawdown')
    axes[1].legend()
    axes[1].grid(True)
    
    # 3. 特徴量重要度 (上位15個)
    importances = model.feature_importances_
    indices = np.argsort(importances)[-15:]
    axes[2].barh(range(len(indices)), importances[indices], align='center')
    axes[2].set_yticks(range(len(indices)))
    axes[2].set_yticklabels([feature_cols[i] for i in indices])
    axes[2].set_title('Feature Importances (Top 15)')
    
    plt.tight_layout()
    plt.savefig(save_path)
    print(f"Plot saved to {save_path}")
