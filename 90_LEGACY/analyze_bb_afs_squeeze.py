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
    
    # 1. MTF BB Width (using FIB periods 21, 55, 144, 377)
    fib_periods = {7: 21, 9: 55, 11: 144, 13: 377}
    total_bb_width = 0
    for k, period in fib_periods.items():
        std = df_1h['close'].rolling(period).std()
        sma = df_1h[f'FIB_{k}_SMA']
        bb_width = (4 * std) / sma
        total_bb_width += bb_width
        
    df_1h['Total_BB_Width'] = total_bb_width
    
    # Squeeze Index: 0 = tightest in last 30 days (720 hours), 1 = widest
    roll_min = df_1h['Total_BB_Width'].rolling(720).min()
    roll_max = df_1h['Total_BB_Width'].rolling(720).max()
    df_1h['Squeeze_Index'] = (df_1h['Total_BB_Width'] - roll_min) / (roll_max - roll_min + 1e-8)
    
    # 2. AFS Order and Slope
    afs_7 = df_1h['AFS_7_19']
    afs_9 = df_1h['AFS_9_19']
    afs_11 = df_1h['AFS_11_19']
    afs_13 = df_1h['AFS_13_19']
    
    df_1h['AFS_Order_Score'] = (afs_7 > afs_9).astype(int) + (afs_9 > afs_11).astype(int) + (afs_11 > afs_13).astype(int)
    
    # Macro Slope (AFS 377 diff over 24h)
    df_1h['AFS_Macro_Slope'] = afs_13.diff(24)
    
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
    
    print("Simulating MFE & Extracting BB/AFS Features for Captured Oracles...")
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
        squeeze_idx = df_1h_2025.loc[t_1h_floor, 'Squeeze_Index']
        afs_order = df_1h_2025.loc[t_1h_floor, 'AFS_Order_Score']
        afs_slope = df_1h_2025.loc[t_1h_floor, 'AFS_Macro_Slope']
        
        if pd.isna(atr) or pd.isna(squeeze_idx): continue
            
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
            'squeeze_index': squeeze_idx,
            'afs_order': afs_order,
            'afs_slope_positive': afs_slope > 0
        })
        
    df_mfe = pd.DataFrame(mfe_data)
    df_mfe.drop_duplicates(subset=['time'], inplace=True)
    
    # Visualization: Vol-Momentum Heatmap
    print("Generating the Vol-Momentum Heatmap...")
    plt.figure(figsize=(12, 8))
    
    # Filter only positive slope for simplicity if needed, or just plot all
    df_plot = df_mfe.copy()
    
    # Add a small jitter to Y for better visualization since it's discrete (0,1,2,3)
    jitter = np.random.uniform(-0.15, 0.15, len(df_plot))
    
    scatter = plt.scatter(
        x=df_plot['squeeze_index'], 
        y=df_plot['afs_order'] + jitter,
        s=df_plot['mfe_atr'] * 20, 
        c=df_plot['mfe_atr'],      
        cmap='coolwarm',            
        alpha=0.8,
        edgecolors='black',
        linewidth=0.5
    )
    
    # Invert X axis (smaller values = tighter squeeze = left side)
    plt.gca().invert_xaxis()
    plt.yticks([0, 1, 2, 3], ['0 (Chaotic)', '1 (Weak)', '2 (Strong)', '3 (Perfect Order)'])
    
    plt.colorbar(scatter, label='Maximum Favorable Excursion (MFE in ATR)')
    
    plt.title('Vol-Expansion Breakout: MTF BB Squeeze & AFS Order vs MFE')
    plt.xlabel('MTF BB Squeeze Index (Reversed: 0 = Max Compression)')
    plt.ylabel('AFS Perfect Order Score (Alignment of Momentum)')
    
    # Annotate Sweet Spot
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.9, edgecolor='red')
    plt.gca().text(0.15, 0.90, "SWEET SPOT\n(Squeeze + Momentum)", transform=plt.gca().transAxes, fontsize=12, fontweight='bold', color='darkred', ha='center', bbox=props)
    
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.tight_layout()
    plt.savefig('vol_momentum_heatmap.png', dpi=300)
    print("Saved vol_momentum_heatmap.png")

if __name__ == '__main__':
    main()
