import pandas as pd
import numpy as np
import lightgbm as lgb
from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from train_lightgbm import build_v5_0_features

def main():
    print("Loading 1h signals...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    df_1h = calculate_diverse_features(df_1h)
    df_1h, feature_cols = build_v5_0_features(df_1h)
    
    df_1h = df_1h[df_1h.index >= '2025-01-01'].copy()
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    model_short = lgb.Booster(model_file='models/lgbm_v5_0_short.txt')
    
    df_1h['pred_L'] = model_long.predict(df_1h[feature_cols])
    df_1h['pred_S'] = model_short.predict(df_1h[feature_cols])
    
    mtf = pd.read_csv('mtf_backtest_results.csv')
    mtf['entry_time'] = pd.to_datetime(mtf['entry_time'])
    
    # We want to map each MTF entry to the LATEST 1h candle that closed before or exactly at the entry_time
    mtf['1h_candle_time'] = mtf['entry_time'].dt.floor('h')
    
    # Merge 1h ML predictions onto the MTF trades
    mtf = mtf.merge(df_1h[['pred_L', 'pred_S', 'F_Trigger_v5_L', 'F_Trigger_v5_S']], 
                    left_on='1h_candle_time', right_index=True, how='left')
    
    print(f"Total MTF trades: {len(mtf)}")
    print(f"MTF trades with matched 1h data: {mtf['pred_L'].notna().sum()}")
    print(f"Max pred_L at MTF entry: {mtf['pred_L'].max()}")
    print(f"Max pred_S at MTF entry: {mtf['pred_S'].max()}")
    
    mtf_L = mtf[mtf['direction'] == 'LONG'].copy()
    mtf_S = mtf[mtf['direction'] == 'SHORT'].copy()
    
    print("\n=== Scenario 1: Filtering MTF Trades with 1h ML (Threshold 0.15) ===")
    l_win = mtf_L[(mtf_L['pred_L'] > 0.25) & (mtf_L['hit'] == 1)]
    l_lose = mtf_L[(mtf_L['pred_L'] > 0.25) & (mtf_L['hit'] == -1)]
    
    s_win = mtf_S[(mtf_S['pred_S'] > 0.25) & (mtf_S['hit'] == 1)]
    s_lose = mtf_S[(mtf_S['pred_S'] > 0.25) & (mtf_S['hit'] == -1)]
    
    total_win = len(l_win) + len(s_win)
    total_lose = len(l_lose) + len(s_lose)
    total = total_win + total_lose
    
    if total > 0:
        print(f"Combined Win Rate at 0.25: {total_win/total:.2%} ({total_win} / {total})")
    
    print("\n=== Scenario 2: Finding 'Missed' Opportunities (Threshold 0.15 to 0.25) ===")
    missed_l_win = mtf_L[(mtf_L['pred_L'] > 0.15) & (mtf_L['pred_L'] <= 0.25) & (mtf_L['hit'] == 1)]
    missed_l_lose = mtf_L[(mtf_L['pred_L'] > 0.15) & (mtf_L['pred_L'] <= 0.25) & (mtf_L['hit'] == -1)]
    
    missed_s_win = mtf_S[(mtf_S['pred_S'] > 0.15) & (mtf_S['pred_S'] <= 0.25) & (mtf_S['hit'] == 1)]
    missed_s_lose = mtf_S[(mtf_S['pred_S'] > 0.15) & (mtf_S['pred_S'] <= 0.25) & (mtf_S['hit'] == -1)]
    
    missed_win = len(missed_l_win) + len(missed_s_win)
    missed_lose = len(missed_l_lose) + len(missed_s_lose)
    missed_total = missed_win + missed_lose
    
    print(f"If we relaxed ML threshold to 0.15 but REQUIRED MTF confirmation:")
    if missed_total > 0:
        print(f"Recovered Trades Win Rate: {missed_win/missed_total:.2%} ({missed_win} / {missed_total})")
    
    print("\nDetailed Missed Wins (False Negatives converted to True Positives):")
    if len(missed_l_win) > 0:
        print("LONG Missed Wins:")
        print(missed_l_win[['entry_time', 'pred_L', 'sl_price', 'tp_price']])
    if len(missed_s_win) > 0:
        print("SHORT Missed Wins:")
        print(missed_s_win[['entry_time', 'pred_S', 'sl_price', 'tp_price']])

if __name__ == "__main__":
    main()
