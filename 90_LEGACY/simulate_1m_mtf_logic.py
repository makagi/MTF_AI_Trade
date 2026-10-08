import pandas as pd
import numpy as np
import os
import glob
from tqdm import tqdm
import matplotlib.pyplot as plt

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

def calculate_mtf_bb(df):
    """Calculate MTF BB directly on 1m data"""
    df['BB_1m_SMA'] = df['close'].rolling(20).mean()
    df['BB_1m_STD'] = df['close'].rolling(20).std()
    
    df['BB_5m_SMA'] = df['close'].rolling(100).mean()
    df['BB_5m_STD'] = df['close'].rolling(100).std()
    
    df['BB_15m_SMA'] = df['close'].rolling(300).mean()
    df['BB_15m_STD'] = df['close'].rolling(300).std()
    
    df['BB_1h_SMA'] = df['close'].rolling(1200).mean()
    df['BB_1h_STD'] = df['close'].rolling(1200).std()
    
    df['BB_1m_L'] = df['BB_1m_SMA'] - 2.0 * df['BB_1m_STD']
    df['BB_5m_L'] = df['BB_5m_SMA'] - 2.0 * df['BB_5m_STD']
    df['BB_15m_L'] = df['BB_15m_SMA'] - 2.0 * df['BB_15m_STD']
    df['BB_1h_L'] = df['BB_1h_SMA'] - 2.0 * df['BB_1h_STD']
    
    df['BB_1m_U'] = df['BB_1m_SMA'] + 2.0 * df['BB_1m_STD']
    df['BB_5m_U'] = df['BB_5m_SMA'] + 2.0 * df['BB_5m_STD']
    df['BB_15m_U'] = df['BB_15m_SMA'] + 2.0 * df['BB_15m_STD']
    df['BB_1h_U'] = df['BB_1h_SMA'] + 2.0 * df['BB_1h_STD']
    
    return df

def run_mtf_backtest():
    print("Loading all 2025 1m data...")
    df = load_all_1m_data_2025()
    print("Calculating MTF BBs...")
    df = calculate_mtf_bb(df)
    
    df.dropna(inplace=True)
    
    print("Running State Machine...")
    
    dates = df.index.values
    close_vals = df['close'].values
    low_vals = df['low'].values
    high_vals = df['high'].values
    
    bb1m_L = df['BB_1m_L'].values
    bb5m_L = df['BB_5m_L'].values
    bb1h_L = df['BB_1h_L'].values
    
    bb1m_U = df['BB_1m_U'].values
    bb5m_U = df['BB_5m_U'].values
    bb1h_U = df['BB_1h_U'].values
    
    # LONG State Machine
    long_trades = []
    state_L = 0 
    ft_val_L = None
    ft_idx_L = None
    bounce_max_L = None
    
    # SHORT State Machine
    short_trades = []
    state_S = 0
    ft_val_S = None
    ft_idx_S = None
    bounce_min_S = None
    
    for i in tqdm(range(len(df))):
        c = close_vals[i]
        l = low_vals[i]
        h = high_vals[i]
        
        # --- LONG LOGIC ---
        if state_L == 0:
            if l < bb1h_L[i] * 1.001 and l < bb1m_L[i]:
                state_L = 1
                ft_val_L = l
                ft_idx_L = i
                bounce_max_L = h
        elif state_L == 1:
            if l < ft_val_L:
                ft_val_L = l
                ft_idx_L = i
                bounce_max_L = h
            else:
                bounce_max_L = max(bounce_max_L, h)
                if c > bb5m_L[i] and bounce_max_L > ft_val_L * 1.002:
                    state_L = 2
                    
            if i - ft_idx_L > 120:
                state_L = 0
                
        elif state_L == 2:
            if l <= bb1m_L[i] or l <= bb5m_L[i]:
                if l > ft_val_L:
                    entry_price = c
                    sl_price = ft_val_L * 0.998
                    tp_price = entry_price + (entry_price - sl_price) * 2.5
                    long_trades.append({
                        'entry_time': dates[i],
                        'entry_price': entry_price,
                        'sl_price': sl_price,
                        'tp_price': tp_price,
                        'ft_time': dates[ft_idx_L],
                        'direction': 'LONG'
                    })
                    state_L = 0
                else:
                    state_L = 1
                    ft_val_L = l
                    ft_idx_L = i
                    bounce_max_L = h
                    
            if i - ft_idx_L > 180:
                state_L = 0
                
        # --- SHORT LOGIC ---
        if state_S == 0:
            if h > bb1h_U[i] * 0.999 and h > bb1m_U[i]:
                state_S = 1
                ft_val_S = h
                ft_idx_S = i
                bounce_min_S = l
        elif state_S == 1:
            if h > ft_val_S:
                ft_val_S = h
                ft_idx_S = i
                bounce_min_S = l
            else:
                bounce_min_S = min(bounce_min_S, l)
                if c < bb5m_U[i] and bounce_min_S < ft_val_S * 0.998:
                    state_S = 2
            if i - ft_idx_S > 120:
                state_S = 0
        elif state_S == 2:
            if h >= bb1m_U[i] or h >= bb5m_U[i]:
                if h < ft_val_S:
                    entry_price = c
                    sl_price = ft_val_S * 1.002
                    tp_price = entry_price - (sl_price - entry_price) * 2.5
                    short_trades.append({
                        'entry_time': dates[i],
                        'entry_price': entry_price,
                        'sl_price': sl_price,
                        'tp_price': tp_price,
                        'ft_time': dates[ft_idx_S],
                        'direction': 'SHORT'
                    })
                    state_S = 0
                else:
                    state_S = 1
                    ft_val_S = h
                    ft_idx_S = i
                    bounce_min_S = l
            if i - ft_idx_S > 180:
                state_S = 0
                
    trades = pd.DataFrame(long_trades + short_trades)
    if len(trades) == 0:
        print("No trades found.")
        return
        
    trades.sort_values('entry_time', inplace=True)
    trades.reset_index(drop=True, inplace=True)
    
    print(f"Generated {len(trades)} potential MTF entries.")
    
    print("Evaluating trades...")
    for idx, trade in tqdm(trades.iterrows(), total=len(trades)):
        start_t = trade['entry_time']
        tp = trade['tp_price']
        sl = trade['sl_price']
        d = trade['direction']
        
        future = df[df.index > start_t].head(1440)
        
        hit = 0
        for ft, frow in future.iterrows():
            if d == 'LONG':
                if frow['high'] >= tp:
                    hit = 1
                    break
                elif frow['low'] <= sl:
                    hit = -1
                    break
            else:
                if frow['low'] <= tp:
                    hit = 1
                    break
                elif frow['high'] >= sl:
                    hit = -1
                    break
                    
        trades.loc[idx, 'hit'] = hit
        
    win_rate = (trades['hit'] == 1).sum() / len(trades)
    print(f"Pure MTF Logic Win Rate: {win_rate:.2%} ({ (trades['hit'] == 1).sum() } / {len(trades)})")
    
    trades.to_csv('mtf_backtest_results.csv', index=False)
    print("Saved to mtf_backtest_results.csv")

if __name__ == "__main__":
    run_mtf_backtest()
