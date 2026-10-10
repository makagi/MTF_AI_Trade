import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import lightgbm as lgb
from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from train_lightgbm import build_v5_0_features

def main():
    print("Loading 1h Macro data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    df_1h = calculate_diverse_features(df_1h)
    df_1h, feature_cols = build_v5_0_features(df_1h)
    df_1h = df_1h[df_1h.index >= '2025-01-01'].copy()
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    df_1h['pred_L'] = model_long.predict(df_1h[feature_cols])
    
    sniper_signal = (df_1h['pred_L'] > 0.25) & (df_1h['F_Trigger_v5_L'] > 0)
    df_1h['sniper_armed'] = sniper_signal.replace(False, np.nan).ffill(limit=4).fillna(False)
    
    trend_signal = (df_1h['pred_L'] > 0.25) & (df_1h['F_Trigger_Trend_L'] > 0)
    df_1h['trend_armed'] = trend_signal.replace(False, np.nan).ffill(limit=4).fillna(False)
    
    mtf = pd.read_csv('mtf_backtest_results.csv')
    mtf = mtf[mtf['direction'] == 'LONG'].copy()
    mtf['entry_time'] = pd.to_datetime(mtf['entry_time'])
    mtf['ft_time'] = pd.to_datetime(mtf['ft_time'])
    mtf['time_delta'] = (mtf['entry_time'] - mtf['ft_time']).dt.total_seconds() / 60.0
    mtf['macro_ts'] = mtf['entry_time'].dt.floor('h')
    
    merged = pd.merge(mtf, df_1h[['sniper_armed', 'trend_armed', 'pred_L']], left_on='macro_ts', right_index=True, how='inner')
    
    engine1_trades = merged[(merged['sniper_armed'] == True) & (merged['time_delta'] >= 10)].copy()
    engine2_trades = merged[(merged['trend_armed'] == True) & (merged['time_delta'] >= 30)].copy()
    
    wins1 = len(engine1_trades[engine1_trades['hit'] == 1])
    total1 = len(engine1_trades)
    print('--- Engine 1 (Sniper) ---')
    print('Trades:', total1, 'Wins:', wins1, f"({wins1/total1*100:.1f}%)" if total1 > 0 else "")
    
    wins2 = len(engine2_trades[engine2_trades['hit'] == 1])
    total2 = len(engine2_trades)
    print('--- Engine 2 (Trend Pullback) ---')
    print('Trades:', total2, 'Wins:', wins2, f"({wins2/total2*100:.1f}%)" if total2 > 0 else "")
    
    combined = pd.concat([engine1_trades, engine2_trades]).drop_duplicates(subset=['entry_time']).sort_values('entry_time')
    wins_c = len(combined[combined['hit'] == 1])
    total_c = len(combined)
    print('--- Combined ---')
    print('Trades:', total_c, 'Wins:', wins_c, f"({wins_c/total_c*100:.1f}%)" if total_c > 0 else "")
    
    sns.set_style('darkgrid')
    fig, axes = plt.subplots(3, 1, figsize=(12, 18))
    if total_c > 0:
        e1_r = engine1_trades['hit'].map({1: 2.5, -1: -1.0})
        e1_equity = e1_r.cumsum()
        axes[0].plot(range(len(e1_equity)), e1_equity, label='Engine 1', color='blue')
        e2_r = engine2_trades['hit'].map({1: 2.5, -1: -1.0})
        e2_equity = e2_r.cumsum()
        axes[0].plot(range(len(e2_equity)), e2_equity, label='Engine 2', color='orange')
        c_r = combined['hit'].map({1: 2.5, -1: -1.0})
        c_equity = c_r.cumsum()
        axes[0].plot(range(len(c_equity)), c_equity, label='Dual Engine Combined', color='green', linewidth=3)
        axes[0].legend()
    if total1 > 0 or total2 > 0:
        axes[1].bar(['Sniper', 'Trend'], [wins1, wins2], color='green')
        axes[1].bar(['Sniper', 'Trend'], [total1-wins1, total2-wins2], bottom=[wins1, wins2], color='red')
    
    all_trend = merged[merged['trend_armed'] == True].copy()
    if len(all_trend) > 0:
        colors = all_trend['hit'].map({1: 'green', -1: 'red'})
        axes[2].scatter(all_trend['time_delta'], all_trend['hit'], c=colors, alpha=0.5)
        axes[2].axvline(x=30, color='black', linestyle='--')
    plt.tight_layout()
    plt.savefig('dual_engine_dashboard.png', dpi=300)

if __name__ == '__main__':
    main()
