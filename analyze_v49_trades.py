import pandas as pd
import numpy as np
import lightgbm as lgb
from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START
from train_lightgbm import build_v4_9_features

def run_analysis():
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    df, feature_cols = build_v4_9_features(df)

    from src.labels import get_binary_barrier_labels
    tb_long = get_binary_barrier_labels(df, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    tb_short = get_binary_barrier_labels(df, pt_sl_ratio=[1.5, 1.0], time_barrier=72, direction='short')
    df['tb_return_long'] = tb_long['tb_return']
    df['tb_return_short'] = tb_short['tb_return']
    df['hit_period_long'] = tb_long['hit_period']
    df['hit_period_short'] = tb_short['hit_period']

    df.dropna(subset=['tb_return_long', 'tb_return_short'] + feature_cols, inplace=True)
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    X_holdout = df_holdout[feature_cols]

    model_long = lgb.Booster(model_file='models/lgbm_v4_9_long.txt')
    model_short = lgb.Booster(model_file='models/lgbm_v4_9_short.txt')
    preds_long = model_long.predict(X_holdout)
    preds_short = model_short.predict(X_holdout)

    threshold = 0.3
    fee = 0.004

    trades = []
    i = 0
    while i < len(df_holdout):
        prob_long = preds_long[i]
        prob_short = preds_short[i]
        trigger_long = df_holdout['F_Trigger_v4_L'].iloc[i]
        trigger_short = df_holdout['F_Trigger_v4_S'].iloc[i]
        
        signal = 0
        if prob_long > threshold and trigger_long > 0:
            signal = 1
        elif prob_short > threshold and trigger_short > 0:
            signal = -1
            
        if signal == 1:
            ret = df_holdout['tb_return_long'].iloc[i]
            hit_period = df_holdout['hit_period_long'].iloc[i]
            pnl = ret - fee
            trades.append({
                'timestamp': df_holdout.index[i],
                'direction': 'LONG',
                'prob': prob_long,
                'pnl': pnl,
                'success': pnl > 0,
                'proximity': df_holdout['F_Floor_Proximity'].iloc[i],
                'wave': df_holdout['F_Wave_Propagation_L'].iloc[i]
            })
            i += int(hit_period) if hit_period > 0 else 1
        elif signal == -1:
            ret = df_holdout['tb_return_short'].iloc[i]
            hit_period = df_holdout['hit_period_short'].iloc[i]
            pnl = ret - fee
            trades.append({
                'timestamp': df_holdout.index[i],
                'direction': 'SHORT',
                'prob': prob_short,
                'pnl': pnl,
                'success': pnl > 0,
                'proximity': df_holdout['F_Ceiling_Proximity'].iloc[i],
                'wave': df_holdout['F_Wave_Propagation_S'].iloc[i]
            })
            i += int(hit_period) if hit_period > 0 else 1
        else:
            i += 1

    trades_df = pd.DataFrame(trades)
    print("=== TRADES ===")
    print(trades_df.to_string())
    print(f"\nTotal Trades: {len(trades_df)}, Wins: {trades_df['success'].sum()}, Win Rate: {trades_df['success'].sum()/len(trades_df)*100:.2f}%")

if __name__ == "__main__":
    run_analysis()
