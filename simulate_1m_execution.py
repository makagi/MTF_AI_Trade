import pandas as pd
import numpy as np
import os
import glob
import lightgbm as lgb
import matplotlib.pyplot as plt

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from train_lightgbm import build_v5_0_features
from src.labels import get_binary_barrier_labels

def load_1m_data(year_month):
    """Load 1m data for a specific year_month like '202502'"""
    file_path = f"D:/work/AI-Trade/Data/BTCUSD_1m/BTCUSD_OHLC_{year_month}.csv"
    if not os.path.exists(file_path):
        return None
    df = pd.read_csv(file_path)
    # Ensure correct column names
    df.columns = [c.strip() for c in df.columns]
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df.set_index('DateTime', inplace=True)
    df.sort_index(inplace=True)
    return df

def calculate_1m_features(df):
    """Calculate RSI and BB on 1m data"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    sma = df['close'].rolling(window=20).mean()
    std = df['close'].rolling(window=20).std()
    df['BB_lower'] = sma - 2.5 * std
    df['BB_upper'] = sma + 2.5 * std
    df['BB_width'] = df['BB_upper'] - df['BB_lower']
    
    return df

def run_micro_execution():
    print("Loading 1h signals...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, 19)
    df = calculate_diverse_features(df)
    df, feature_cols = build_v5_0_features(df)
    
    tb_long = get_binary_barrier_labels(df, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    df['tb_return_long'] = tb_long['tb_return']
    df['hit_period_long'] = tb_long['hit_period']
    
    tb_short = get_binary_barrier_labels(df, pt_sl_ratio=[1.5, 1.0], time_barrier=72, direction='short')
    df['tb_return_short'] = tb_short['tb_return']
    df['hit_period_short'] = tb_short['hit_period']
    
    df.dropna(subset=['tb_return_long'] + feature_cols, inplace=True)
    
    df_h = df[df.index >= '2025-01-01'].copy()
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    model_short = lgb.Booster(model_file='models/lgbm_v5_0_short.txt')
    
    preds_L = model_long.predict(df_h[feature_cols])
    preds_S = model_short.predict(df_h[feature_cols])
    
    threshold = 0.25
    signals_list = []
    
    i = 0
    while i < len(df_h):
        prob_long = preds_L[i]
        trigger_long = df_h['F_Trigger_v5_L'].iloc[i]
        prob_short = preds_S[i]
        trigger_short = df_h['F_Trigger_v5_S'].iloc[i]
        
        signal = 0
        if prob_long > threshold and trigger_long > 0:
            signal = 1
        elif prob_short > threshold and trigger_short > 0:
            signal = -1
            
        if signal != 0:
            signals_list.append((df_h.index[i], signal))
            if signal == 1:
                hit_period = df_h['hit_period_long'].iloc[i]
            else:
                hit_period = df_h['hit_period_short'].iloc[i]
            i += int(hit_period) if hit_period > 0 else 1
        else:
            i += 1
            
    print(f"Found {len(signals_list)} total signals at threshold {threshold} (Sequential)")
    
    results = []
    
    for signal_time, direction in signals_list:
        ym = signal_time.strftime('%Y%m')
        df_1m = load_1m_data(ym)
        
        if df_1m is None:
            print(f"1m data missing for {ym}")
            continue
            
        df_1m = calculate_1m_features(df_1m)
        
        start_time = signal_time
        end_time = signal_time + pd.Timedelta(minutes=60)
        
        window = df_1m[(df_1m.index > start_time) & (df_1m.index <= end_time)]
        
        if len(window) == 0:
            continue
            
        executed = False
        entry_price = None
        entry_time = None
        exec_type = None
        
        for t, row in window.iterrows():
            if direction == 1:
                if row['close'] < row['BB_lower'] * 0.995: 
                    exec_type = 'CANCELLED_KNIFE'
                    break
                if row['RSI_14'] < 30 or row['close'] <= row['BB_lower']:
                    entry_price = row['close']
                    entry_time = t
                    exec_type = 'DIP_SNIPE'
                    executed = True
                    break
            else:
                if row['close'] > row['BB_upper'] * 1.005: 
                    exec_type = 'CANCELLED_KNIFE'
                    break
                if row['RSI_14'] > 70 or row['close'] >= row['BB_upper']:
                    entry_price = row['close']
                    entry_time = t
                    exec_type = 'RALLY_SNIPE'
                    executed = True
                    break
                
        if not executed and exec_type != 'CANCELLED_KNIFE':
            fomo_time = start_time + pd.Timedelta(minutes=10)
            if fomo_time in window.index:
                entry_price = window.loc[fomo_time, 'close']
                entry_time = fomo_time
                exec_type = 'FOMO_MARKET'
                executed = True
            else:
                entry_time = window.index[-1]
                entry_price = window.loc[entry_time, 'close']
                exec_type = 'END_OF_WINDOW'
                executed = True
                
        baseline_price = df_h.loc[signal_time, 'close']
        
        if executed:
            if direction == 1:
                price_improvement = (baseline_price - entry_price) / baseline_price
                atr = df_h.loc[signal_time, 'ATR_14']
                tp_price = entry_price + atr * 2.5
                sl_price = entry_price - atr * 1.0
            else:
                price_improvement = (entry_price - baseline_price) / baseline_price
                atr = df_h.loc[signal_time, 'ATR_14']
                tp_price = entry_price - atr * 2.5
                sl_price = entry_price + atr * 1.0
                
            future_1h = df_h[df_h.index > entry_time].head(72)
            
            hit = 0
            ret = 0.0
            for ft, frow in future_1h.iterrows():
                if direction == 1:
                    if frow['high'] >= tp_price:
                        hit = 1
                        ret = (tp_price / entry_price) - 1.0
                        break
                    elif frow['low'] <= sl_price:
                        hit = -1
                        ret = (sl_price / entry_price) - 1.0
                        break
                else:
                    if frow['low'] <= tp_price:
                        hit = 1
                        ret = (entry_price / tp_price) - 1.0
                        break
                    elif frow['high'] >= sl_price:
                        hit = -1
                        ret = (entry_price / sl_price) - 1.0
                        break
                        
            if hit == 0 and len(future_1h) > 0:
                if direction == 1:
                    ret = (future_1h.iloc[-1]['close'] / entry_price) - 1.0
                else:
                    ret = (entry_price / future_1h.iloc[-1]['close']) - 1.0
                    
            baseline_ret = df_h.loc[signal_time, 'tb_return_long'] if direction == 1 else df_h.loc[signal_time, 'tb_return_short']
            
            results.append({
                'signal_time': signal_time,
                'exec_time': entry_time,
                'exec_type': exec_type,
                'baseline_price': baseline_price,
                'entry_price': entry_price,
                'improvement_%': price_improvement * 100,
                'baseline_ret': baseline_ret,
                'new_ret': ret,
                'hit_tp': hit == 1
            })
        else:
            results.append({
                'signal_time': signal_time,
                'exec_time': None,
                'exec_type': exec_type,
                'baseline_price': baseline_price,
                'entry_price': None,
                'improvement_%': 0,
                'baseline_ret': df_h.loc[signal_time, 'tb_return_long'] if direction == 1 else df_h.loc[signal_time, 'tb_return_short'],
                'new_ret': 0,
                'hit_tp': False
            })
            
    res_df = pd.DataFrame(results)
    print("\n=== Micro Execution Results ===")
    print(res_df.to_string())
    
    print("\n=== Summary ===")
    print(f"Total Signals: {len(res_df)}")
    print(f"Executed: {len(res_df[res_df['exec_type'] != 'CANCELLED_KNIFE'])}")
    print(f"Cancelled (Knife): {len(res_df[res_df['exec_type'] == 'CANCELLED_KNIFE'])}")
    
    executed = res_df[res_df['exec_type'] != 'CANCELLED_KNIFE']
    if len(executed) > 0:
        print(f"Avg Price Improvement: {executed['improvement_%'].mean():.3f}%")
        
        baseline_win = (executed['baseline_ret'] > 0.004).sum()
        new_win = executed['hit_tp'].sum()
        print(f"Baseline Wins (among executed): {baseline_win} / {len(executed)}")
        print(f"New Wins (Hit TP): {new_win} / {len(executed)}")
        
        baseline_pnl = executed['baseline_ret'].sum() - (len(executed) * 0.004)
        new_pnl = executed['new_ret'].sum() - (len(executed) * 0.004)
        print(f"Baseline Net PnL: {baseline_pnl * 100:.2f}%")
        print(f"New Net PnL: {new_pnl * 100:.2f}%")

if __name__ == "__main__":
    run_micro_execution()
