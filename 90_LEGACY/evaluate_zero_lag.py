import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import lightgbm as lgb
import glob
from tqdm import tqdm
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from train_lightgbm import build_v5_0_features

def load_all_1m_data_2025():
    files = glob.glob("D:/work/AI-Trade/Data/BTCUSD_1m/BTCUSD_OHLC_2025*.csv")
    dfs = []
    for f in sorted(files):
        df = pd.read_csv(f)
        df.columns = [c.strip() for c in df.columns]
        dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df.set_index('DateTime', inplace=True)
    df.sort_index(inplace=True)
    return df

def get_pseudo_candle(df_1m, t_start, t_end):
    df_pseudo = df_1m.loc[t_start:t_end]
    if len(df_pseudo) == 0:
        return None
        
    return pd.DataFrame({
        'open': [df_pseudo['open'].iloc[0]],
        'high': [df_pseudo['high'].max()],
        'low': [df_pseudo['low'].min()],
        'close': [df_pseudo['close'].iloc[-1]],
        'volume': [df_pseudo['volume'].sum() if 'volume' in df_pseudo else 0]
    }, index=[t_start])

def main():
    print("Loading 1h Raw History...")
    df_1h_raw = load_1h_data(include_holdout=True)
    # Ensure it's clean and sorted
    df_1h_raw.sort_index(inplace=True)
    
    print("Loading 1m Data for 2025...")
    df_1m = load_all_1m_data_2025()
    
    print("Loading LightGBM Model...")
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    
    print("Loading MTF Entries...")
    mtf = pd.read_csv('mtf_backtest_results.csv')
    mtf = mtf[mtf['direction'] == 'LONG'].copy()
    mtf['entry_time'] = pd.to_datetime(mtf['entry_time'])
    mtf.sort_values('entry_time', inplace=True)
    
    results = []
    
    print("Starting Zero-Lag Simulation...")
    for idx, row in tqdm(mtf.iterrows(), total=len(mtf)):
        t_end = row['entry_time']
        t_start = t_end.floor('h')
        
        # 1. Generate Pseudo 1h candle
        pseudo_candle = get_pseudo_candle(df_1m, t_start, t_end)
        if pseudo_candle is None:
            continue
            
        # 2. Grab 400 hours of history EXCLUDING current hour
        # using strictly < t_start
        t_hist_start = t_start - pd.Timedelta(hours=450)
        df_hist = df_1h_raw.loc[t_hist_start : t_start - pd.Timedelta(hours=1)].copy()
        
        if len(df_hist) < 400:
            continue
            
        # 3. Concat and Compute
        df_eval = pd.concat([df_hist, pseudo_candle])
        
        df_eval = calculate_fib_features(df_eval, 19)
        df_eval = calculate_diverse_features(df_eval)
        df_eval, feature_cols = build_v5_0_features(df_eval)
        
        last_row = df_eval.iloc[-1:]
        
        # 4. Predict
        pred_L = model_long.predict(last_row[feature_cols])[0]
        trigger_sniper = last_row['F_Trigger_v5_L'].values[0] > 0
        trigger_trend = last_row['F_Trigger_Trend_L'].values[0] > 0
        
        if pred_L > 0.25:
            if trigger_sniper:
                row['engine'] = 'Sniper'
                row['pred'] = pred_L
                results.append(row)
            elif trigger_trend:
                row['engine'] = 'Trend'
                row['pred'] = pred_L
                results.append(row)
                
    if len(results) == 0:
        print("\nNo Zero-Lag trades found!")
        return
        
    df_res = pd.DataFrame(results)
    
    print("\n=== ZERO-LAG ML EXECUTION RESULTS ===")
    total = len(df_res)
    wins = len(df_res[df_res['hit'] == 1])
    print(f"Total Trades: {total}, Wins: {wins} ({wins/total*100:.1f}%)")
    
    sniper = df_res[df_res['engine'] == 'Sniper']
    if len(sniper) > 0:
        s_wins = len(sniper[sniper['hit'] == 1])
        print(f"Sniper Trades: {len(sniper)}, Wins: {s_wins} ({s_wins/len(sniper)*100:.1f}%)")
        
    trend = df_res[df_res['engine'] == 'Trend']
    if len(trend) > 0:
        t_wins = len(trend[trend['hit'] == 1])
        print(f"Trend Trades: {len(trend)}, Wins: {t_wins} ({t_wins/len(trend)*100:.1f}%)")
        
    # Plotting
    sns.set_style('darkgrid')
    fig, axes = plt.subplots(2, 1, figsize=(10, 12))
    
    # 1. Equity Curve
    r_multiples = df_res['hit'].map({1: 2.5, -1: -1.0}).fillna(0)
    equity = r_multiples.cumsum()
    axes[0].plot(range(len(equity)), equity, color='purple', linewidth=2, marker='o')
    axes[0].set_title('Zero-Lag Dual Engine Equity Curve (R-Multiples)')
    axes[0].set_xlabel('Trade #')
    axes[0].set_ylabel('Cumulative R')
    
    # 2. Engine Breakdown
    sns.countplot(data=df_res, x='engine', hue='hit', ax=axes[1], palette={1: 'green', -1: 'red', 0: 'gray'})
    axes[1].set_title('Win/Loss by Engine')
    
    plt.tight_layout()
    plt.savefig('zero_lag_results.png', dpi=300)
    print("Saved zero_lag_results.png")

if __name__ == '__main__':
    main()
