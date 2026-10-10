import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features

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

def get_binary_barrier_labels(df: pd.DataFrame, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long') -> pd.DataFrame:
    df_labels = pd.DataFrame(index=df.index)
    returns = np.zeros(len(df))
    close_vals = df['close'].values
    high_vals = df['high'].values
    low_vals = df['low'].values
    atr_vals = df['ATR_14'].values
    
    for i in range(len(df)):
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


def main():
    print("Loading 1h Data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    df_1h = calculate_diverse_features(df_1h)
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    df_1h['Trend_State'] = (df_1h['FIB_11_SMA'] - df_1h['FIB_13_SMA']) / df_1h['close'] * 100
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025)
    oracle_1h_indices = labels[labels['tb_return'] == 1].index
    
    print("Loading 1m Data...")
    df_1m = load_all_1m_data_2025()
    
    df_1m['ATR_1h'] = df_1h_2025['ATR_14'].reindex(df_1m.index, method='ffill')
    df_1m['Trend_State_1h'] = df_1h_2025['Trend_State'].reindex(df_1m.index, method='ffill')
    
    print("Calculating Dual Trigger Armed State...")
    rolling_high_30m = df_1m['high'].rolling('30min').max()
    panic_mask = (rolling_high_30m - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    armed_single = panic_mask.rolling('2h').max() > 0
    
    rolling_high_60m = df_1m['high'].rolling('60min').max()
    trend_dip_mask = (df_1m['Trend_State_1h'] > 1.5) & ((rolling_high_60m - df_1m['low']) >= (1.0 * df_1m['ATR_1h']))
    armed_trend = trend_dip_mask.rolling('1h').max() > 0
    
    df_1m['Armed_Dual'] = armed_single | armed_trend
    
    print("Simulating MFE for Captured Oracles...")
    mfe_data = []
    
    for t_oracle in tqdm(oracle_1h_indices):
        t_start = t_oracle - pd.Timedelta(hours=1)
        t_end = t_oracle + pd.Timedelta(hours=1, minutes=59)
        window = df_1m.loc[t_start:t_end]
        
        if len(window) == 0: continue
            
        t_1m = window['low'].idxmin()
        if t_1m not in df_1m.index: continue
            
        # Is it captured by Dual Trigger?
        is_captured = df_1m.loc[t_1m, 'Armed_Dual']
        if not is_captured: continue
            
        entry_price = df_1m.loc[t_1m, 'low']
        t_1h_floor = t_1m.floor('h')
        atr = df_1h_2025.loc[t_1h_floor, 'ATR_14'] if t_1h_floor in df_1h_2025.index else np.nan
        
        if pd.isna(atr): continue
            
        sl_price = entry_price - (1.0 * atr)
        
        # Simulate MFE for the next 72 hours
        t_future_end = t_1m + pd.Timedelta(hours=72)
        future_window = df_1m.loc[t_1m:t_future_end]
        
        max_price = entry_price
        for row in future_window.itertuples():
            if row.low <= sl_price:
                break
            if row.high > max_price:
                max_price = row.high
                
        mfe_atr = (max_price - entry_price) / atr
        
        mfe_data.append({
            'time': t_1m,
            'mfe_atr': mfe_atr
        })
        
    df_mfe = pd.DataFrame(mfe_data)
    df_mfe.drop_duplicates(subset=['time'], inplace=True)
    
    print(f"Total Captured Oracles for MFE Analysis: {len(df_mfe)}")
    
    # Plotting MFE Histogram
    plt.figure(figsize=(12, 7))
    bins = np.linspace(0, 10, 40)
    
    # Plot histogram
    counts, edges, patches = plt.hist(df_mfe['mfe_atr'].clip(upper=10), bins=bins, color='lightblue', edgecolor='black', alpha=0.7)
    
    # Highlight the "Money Left on the Table" (MFE > 2.5)
    for i in range(len(patches)):
        if edges[i] >= 2.5:
            patches[i].set_facecolor('gold')
            patches[i].set_alpha(0.8)
            
    plt.axvline(x=2.5, color='red', linestyle='--', linewidth=3, label='Current Take Profit (2.5 ATR)')
    
    # Aesthetics
    plt.title('Maximum Favorable Excursion (MFE): The Opportunity Cost of Early Take Profits')
    plt.xlabel('Maximum Profit Reached Before SL or 72h (ATR Multiples)')
    plt.ylabel('Number of Trades')
    plt.grid(True, linestyle=':', alpha=0.6)
    
    # Stats box
    pct_gt_25 = (df_mfe['mfe_atr'] > 2.5).mean() * 100
    pct_gt_50 = (df_mfe['mfe_atr'] > 5.0).mean() * 100
    
    stats_text = (f"Trades hitting > 2.5 ATR: {pct_gt_25:.1f}%\n"
                  f"Trades hitting > 5.0 ATR: {pct_gt_50:.1f}%\n"
                  f"Gold Area = 'Money Left on the Table'\n"
                  f"(Potential solved via Trailing Stops)")
                  
    props = dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='black')
    plt.gca().text(0.60, 0.85, stats_text, transform=plt.gca().transAxes, fontsize=12, verticalalignment='top', bbox=props)
    
    plt.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig('mfe_analysis.png', dpi=300)
    print("Saved mfe_analysis.png")

if __name__ == '__main__':
    main()
