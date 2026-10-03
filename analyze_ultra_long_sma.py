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
    
    # 1. Total Compression Width (FIB 7 to 15: 21 to 987)
    medium_long_smas = [f'FIB_{i}_SMA' for i in range(7, 16)]
    df_1h['Compression_Max'] = df_1h[medium_long_smas].max(axis=1)
    df_1h['Compression_Min'] = df_1h[medium_long_smas].min(axis=1)
    df_1h['Total_Compression_Width'] = (df_1h['Compression_Max'] - df_1h['Compression_Min']) / df_1h['close'] * 100
    
    # 2. Ultra-Long Features (FIB_16_SMA = 1597)
    df_1h['Slope_1597'] = (df_1h['FIB_16_SMA'] - df_1h['FIB_16_SMA'].shift(24)) / df_1h['close'] * 100
    df_1h['Dist_1597'] = (df_1h['FIB_16_SMA'] - df_1h['close']) / df_1h['close'] * 100
    
    # Already Reached 1597 Flag (Touched in last 72 hours)
    touched_1597 = (df_1h['high'] >= df_1h['FIB_16_SMA']) & (df_1h['low'] <= df_1h['FIB_16_SMA'])
    df_1h['Reached_1597'] = touched_1597.rolling(72).max() > 0
    
    # Categories for Boxplot (Based on slope and distance/touch)
    df_1h['Ultra_Category'] = 'Unknown'
    mask_bull = df_1h['Slope_1597'] > 0
    mask_bear = df_1h['Slope_1597'] < 0
    mask_not_reached = ~df_1h['Reached_1597']
    mask_reached = df_1h['Reached_1597']
    
    df_1h.loc[mask_bull & mask_not_reached, 'Ultra_Category'] = '1. Bullish & Not Reached (Magnetic Pull)'
    df_1h.loc[mask_bull & mask_reached, 'Ultra_Category'] = '2. Bullish & Reached (Energy Spent)'
    df_1h.loc[mask_bear & mask_not_reached, 'Ultra_Category'] = '3. Bearish & Not Reached (Magnetic Pull)'
    df_1h.loc[mask_bear & mask_reached, 'Ultra_Category'] = '4. Bearish & Reached (Energy Spent)'
    
    # Trend State for the Dual Trigger
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
    
    print("Simulating MFE & Extracting Ultra-Long Features for Captured Oracles...")
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
        
        if t_1h_floor not in df_1h_2025.index: continue
        
        atr = df_1h_2025.loc[t_1h_floor, 'ATR_14']
        comp_width = df_1h_2025.loc[t_1h_floor, 'Total_Compression_Width']
        ultra_cat = df_1h_2025.loc[t_1h_floor, 'Ultra_Category']
        dist_1597 = df_1h_2025.loc[t_1h_floor, 'Dist_1597']
        
        if pd.isna(atr) or pd.isna(comp_width): continue
            
        # Filter for "Total Compression" states (e.g., width < 3%)
        if comp_width > 3.0: 
            continue
            
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
            'mfe_atr': mfe_atr,
            'ultra_category': ultra_cat,
            'dist_1597': dist_1597
        })
        
    df_mfe = pd.DataFrame(mfe_data)
    df_mfe.drop_duplicates(subset=['time'], inplace=True)
    df_mfe = df_mfe[df_mfe['ultra_category'] != 'Unknown']
    df_mfe.sort_values('ultra_category', inplace=True)
    
    # Visualization: Box Plot
    print("Generating the Ultra-Long Magnet Box Plot...")
    plt.figure(figsize=(12, 8))
    
    sns.boxplot(
        x='mfe_atr', 
        y='ultra_category', 
        data=df_mfe, 
        palette='Set2', 
        width=0.6,
        showfliers=False
    )
    
    # Add stripplot to show individual trades
    sns.stripplot(
        x='mfe_atr', 
        y='ultra_category', 
        data=df_mfe, 
        color='black', 
        alpha=0.5, 
        size=4, 
        jitter=True
    )
    
    plt.axvline(x=2.5, color='red', linestyle='--', linewidth=2, label='Current TP (2.5 ATR)')
    plt.axvline(x=5.0, color='gold', linestyle='--', linewidth=2, label='Mega-Trend Threshold (5.0 ATR)')
    
    plt.title('Ultra-Long SMA Magnetism (1597) during Total Compression (Width < 3%)')
    plt.xlabel('Maximum Favorable Excursion (MFE in ATR)')
    plt.ylabel('Ultra-Long SMA State')
    
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig('ultra_long_magnet_mfe.png', dpi=300)
    print("Saved ultra_long_magnet_mfe.png")

if __name__ == '__main__':
    main()
