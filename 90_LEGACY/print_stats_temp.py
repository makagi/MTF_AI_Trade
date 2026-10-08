import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def get_binary_barrier_labels(df: pd.DataFrame, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long') -> pd.DataFrame:
    df_labels = pd.DataFrame(index=df.index)
    returns = np.zeros(len(df))
    close_vals = df['close'].values
    high_vals = df['high'].values
    low_vals = df['low'].values
    atr_vals = df['ATR_14'].values
    
    for i in tqdm(range(len(df)), desc=f'Labeling {direction}'):
        if i + 1 >= len(df): break
        c = close_vals[i]
        atr = atr_vals[i]
        if pd.isna(atr) or atr == 0: continue
            
        tp = c + atr * pt_sl_ratio[0]
        sl = c - atr * pt_sl_ratio[1]
            
        future_highs = high_vals[i+1 : i+1+time_barrier]
        future_lows = low_vals[i+1 : i+1+time_barrier]
        
        hit_val = 0
        for j in range(len(future_highs)):
            if future_lows[j] <= sl:
                hit_val = -1
                break
            elif future_highs[j] >= tp:
                hit_val = 1
                break
        returns[i] = hit_val
    df_labels['tb_return'] = returns
    return df_labels

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

def main():
    print("Loading 1h data...")
    df_1h = load_1h_data(include_holdout=True)
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    
    labels_L = get_binary_barrier_labels(df_1h_2025, pt_sl_ratio=[2.5, 1.0], direction='long')
    
    oracle_1h_indices = labels_L[labels_L['tb_return'] == 1].index
    
    print("Loading 1m Data...")
    df_1m = load_all_1m_data_2025()
    
    print("Analyzing micro-timing of Oracles...")
    results = []
    
    for t_oracle in tqdm(oracle_1h_indices):
        t_start = t_oracle - pd.Timedelta(hours=1)
        t_end = t_oracle + pd.Timedelta(hours=1) + pd.Timedelta(minutes=59)
        
        window_1m = df_1m.loc[t_start:t_end]
        if len(window_1m) == 0: continue
            
        true_bottom_idx = window_1m['low'].idxmin()
        true_bottom_price = window_1m.loc[true_bottom_idx, 'low']
        
        if true_bottom_idx < t_oracle:
            hour_offset = -1
        elif true_bottom_idx >= t_oracle + pd.Timedelta(hours=1):
            hour_offset = 1
        else:
            hour_offset = 0
            
        try:
            h_minus_1 = df_1h.loc[t_oracle - pd.Timedelta(hours=1)]
            h_zero = df_1h.loc[t_oracle]
            h_plus_1 = df_1h.loc[t_oracle + pd.Timedelta(hours=1)]
        except:
            continue
            
        results.append({
            'oracle_1h_time': t_oracle,
            'true_bottom_time': true_bottom_idx,
            'minute_of_hour': true_bottom_idx.minute,
            'hour_offset': hour_offset,
            'true_bottom_price': true_bottom_price,
            'h_minus_1_open': h_minus_1['open'],
            'h_minus_1_close': h_minus_1['close'],
            'h_minus_1_low': h_minus_1['low'],
            'h_minus_1_high': h_minus_1['high'],
            'h_zero_open': h_zero['open'],
            'h_zero_close': h_zero['close'],
            'h_zero_low': h_zero['low'],
            'h_zero_high': h_zero['high'],
            'h_plus_1_open': h_plus_1['open'],
            'h_plus_1_close': h_plus_1['close'],
            'h_plus_1_low': h_plus_1['low'],
            'h_plus_1_high': h_plus_1['high']
        })
        
    df_res = pd.DataFrame(results)
    
    print('\
Minute Distribution:\
', df_res['minute_of_hour'].value_counts(normalize=True).sort_index() * 100)
    print('\
Hour Offset:\
', df_res['hour_offset'].value_counts())
    print('\
Composite Candle:\
', comp_df)
    plt.figure(figsize=(10, 6))
    sns.histplot(df_res['minute_of_hour'], bins=60, color='purple')
    plt.title('True Bottom (Oracle) Distribution by Minute of Hour')
    plt.xlabel('Minute of Hour (0-59)')
    plt.ylabel('Frequency')
    plt.savefig('oracle_minute_distribution.png')
    
    df_res['h_minus_1_open_norm'] = (df_res['h_minus_1_open'] - df_res['true_bottom_price'])
    df_res['h_minus_1_close_norm'] = (df_res['h_minus_1_close'] - df_res['true_bottom_price'])
    df_res['h_minus_1_high_norm'] = (df_res['h_minus_1_high'] - df_res['true_bottom_price'])
    df_res['h_minus_1_low_norm'] = (df_res['h_minus_1_low'] - df_res['true_bottom_price'])
    
    df_res['h_zero_open_norm'] = (df_res['h_zero_open'] - df_res['true_bottom_price'])
    df_res['h_zero_close_norm'] = (df_res['h_zero_close'] - df_res['true_bottom_price'])
    df_res['h_zero_high_norm'] = (df_res['h_zero_high'] - df_res['true_bottom_price'])
    df_res['h_zero_low_norm'] = (df_res['h_zero_low'] - df_res['true_bottom_price'])
    
    df_res['h_plus_1_open_norm'] = (df_res['h_plus_1_open'] - df_res['true_bottom_price'])
    df_res['h_plus_1_close_norm'] = (df_res['h_plus_1_close'] - df_res['true_bottom_price'])
    df_res['h_plus_1_high_norm'] = (df_res['h_plus_1_high'] - df_res['true_bottom_price'])
    df_res['h_plus_1_low_norm'] = (df_res['h_plus_1_low'] - df_res['true_bottom_price'])
    
    comp = df_res.mean(numeric_only=True)
    
    comp_df = pd.DataFrame({
        'Open': [comp['h_minus_1_open_norm'], comp['h_zero_open_norm'], comp['h_plus_1_open_norm']],
        'High': [comp['h_minus_1_high_norm'], comp['h_zero_high_norm'], comp['h_plus_1_high_norm']],
        'Low': [comp['h_minus_1_low_norm'], comp['h_zero_low_norm'], comp['h_plus_1_low_norm']],
        'Close': [comp['h_minus_1_close_norm'], comp['h_zero_close_norm'], comp['h_plus_1_close_norm']]
    }, index=pd.date_range('2025-01-01', periods=3, freq='H'))
    
    import mplfinance as mpf
    mc = mpf.make_marketcolors(up='g', down='r', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')
    mpf.plot(comp_df, type='candle', style=s, title='Composite Average Oracle Bottom (H-1, H0, H+1)', savefig='oracle_composite_bottom.png')
    
    print("Done. Saved oracle_minute_distribution.png and oracle_composite_bottom.png")

if __name__ == '__main__':
    main()
