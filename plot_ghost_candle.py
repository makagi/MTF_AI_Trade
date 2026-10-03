import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.lines as lines
import lightgbm as lgb
import glob
import mplfinance as mpf
import warnings

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
    df_1h_raw.sort_index(inplace=True)
    
    print("Loading 1m Data for 2025...")
    df_1m = load_all_1m_data_2025()
    
    print("Loading LightGBM Model...")
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    
    print("Loading MTF Entries...")
    mtf = pd.read_csv('mtf_backtest_results.csv')
    mtf = mtf[(mtf['direction'] == 'LONG') & (mtf['hit'] == -1.0)].copy()
    mtf['entry_time'] = pd.to_datetime(mtf['entry_time'])
    mtf.sort_values('entry_time', inplace=True)
    
    tragic_row = None
    t_start_tragic = None
    ghost_candle = None
    
    print("Searching for a tragic failure (Ghost Candle)...")
    for idx, row in mtf.iterrows():
        t_end = row['entry_time']
        if t_end.minute >= 15:
            continue
            
        t_start = t_end.floor('h')
        pseudo_candle = get_pseudo_candle(df_1m, t_start, t_end)
        if pseudo_candle is None: continue
            
        t_hist_start = t_start - pd.Timedelta(hours=450)
        df_hist = df_1h_raw.loc[t_hist_start : t_start - pd.Timedelta(hours=1)].copy()
        if len(df_hist) < 400: continue
            
        df_eval = pd.concat([df_hist, pseudo_candle])
        df_eval = calculate_fib_features(df_eval, 19)
        df_eval = calculate_diverse_features(df_eval)
        df_eval, feature_cols = build_v5_0_features(df_eval)
        
        last_row = df_eval.iloc[-1:]
        pred_L = model_long.predict(last_row[feature_cols])[0]
        trigger_trend = last_row['F_Trigger_Trend_L'].values[0] > 0
        
        if pred_L > 0.25 and trigger_trend:
            tragic_row = row
            t_start_tragic = t_start
            ghost_candle = pseudo_candle
            break
            
    if tragic_row is None:
        print("No tragic failure found!")
        return
        
    print(f"Tragic trade found at {tragic_row['entry_time']}")
    
    T_entry = tragic_row['entry_time']
    T_start = t_start_tragic
    T_window_start = T_start - pd.Timedelta(minutes=30)
    T_window_end = T_start + pd.Timedelta(minutes=90)
    
    df_plot = df_1m.loc[T_window_start:T_window_end].copy()
    
    ghost_open = ghost_candle['open'].iloc[0]
    ghost_high = ghost_candle['high'].iloc[0]
    ghost_low = ghost_candle['low'].iloc[0]
    ghost_close = ghost_candle['close'].iloc[0]
    
    color = 'green' if ghost_close > ghost_open else 'red'
    
    mc = mpf.make_marketcolors(up='g', down='r', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')
    
    fig, axlist = mpf.plot(df_plot, type='candle', style=s, returnfig=True, figsize=(14, 8), title=f"Candle Completion Illusion at {T_entry}")
    ax = axlist[0]
    
    idx_start = df_plot.index.get_loc(T_start)
    idx_end = df_plot.index.get_loc(T_start + pd.Timedelta(minutes=59))
    idx_entry = df_plot.index.get_loc(T_entry)
    
    rect = patches.Rectangle((idx_start, min(ghost_open, ghost_close)), 
                             width=(idx_end - idx_start), 
                             height=abs(ghost_close - ghost_open), 
                             linewidth=2, edgecolor=color, facecolor=color, alpha=0.15)
    ax.add_patch(rect)
    
    wick_x = idx_start + (idx_end - idx_start) / 2
    wick = lines.Line2D([wick_x, wick_x], [ghost_low, ghost_high], 
                        color=color, alpha=0.3, linewidth=6)
    ax.add_line(wick)
    
    ax.plot(idx_entry, df_plot.loc[T_entry, 'close'], marker='^', color='blue', markersize=20, label='AI Buy Signal')
    ax.axhline(tragic_row['sl_price'], color='red', linestyle='--', linewidth=2, label='Stop Loss Hit')
    ax.legend(loc='upper right')
    
    fig.savefig('ghost_candle_illusion.png', dpi=300)
    print("Saved ghost_candle_illusion.png")

if __name__ == '__main__':
    main()
