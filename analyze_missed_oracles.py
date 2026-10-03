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
from train_lightgbm import build_v5_0_features

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
    print("Loading 1h Data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    df_1h = calculate_diverse_features(df_1h)
    df_1h, feature_cols = build_v5_0_features(df_1h)
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    
    # Simple RSI calculation for 1h
    delta = df_1h['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_1h['RSI_14'] = 100 - (100 / (1 + rs))
    
    df_1h['Trend_State'] = (df_1h['FIB_11_SMA'] - df_1h['FIB_13_SMA']) / df_1h['close'] * 100
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    oracle_1h_indices = labels[labels['tb_return'] == 1].index
    
    print("Loading 1m Data...")
    df_1m = load_all_1m_data_2025()
    
    print("Extracting Oracles & Vectorizing...")
    # Vectorize New Logic
    df_1m['ATR_1h'] = df_1h_2025['ATR_14'].reindex(df_1m.index, method='ffill')
    rolling_high = df_1m['high'].rolling('30min').max()
    trigger_mask = (rolling_high - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    df_1m['Armed_New'] = trigger_mask.rolling('2h').max() > 0
    
    oracle_data = []
    for t_oracle in tqdm(oracle_1h_indices):
        t_start = t_oracle - pd.Timedelta(hours=1)
        t_end = t_oracle + pd.Timedelta(hours=1, minutes=59)
        window = df_1m.loc[t_start:t_end]
        if len(window) > 0:
            t_1m = window['low'].idxmin()
            price = window.loc[t_1m, 'low']
            
            t_1h_floor = t_1m.floor('h')
            if t_1h_floor not in df_1h_2025.index: continue
            
            atr = df_1h_2025.loc[t_1h_floor, 'ATR_14']
            if pd.isna(atr): continue
                
            net_pnl = (2.5 * atr / price) - 0.004
            captured = df_1m.loc[t_1m, 'Armed_New']
            
            oracle_data.append({
                'time': t_1m,
                'captured': captured,
                'net_pnl': net_pnl,
                'Trend_State': df_1h_2025.loc[t_1h_floor, 'Trend_State'],
                'Floor_Proximity': df_1h_2025.loc[t_1h_floor, 'F_Floor_Proximity'],
                'RSI_14': df_1h_2025.loc[t_1h_floor, 'RSI_14']
            })
            
    df_oracles = pd.DataFrame(oracle_data).dropna()
    df_oracles.drop_duplicates(subset=['time'], inplace=True)
    
    # Filter only profitable oracles
    df_prof = df_oracles[df_oracles['net_pnl'] > 0].copy()
    
    df_prof['Status'] = df_prof['captured'].map({True: 'Captured (Crash)', False: 'Missed (Unknown)'})
    
    print("Generating Archetype Map...")
    plt.figure(figsize=(10, 8))
    sns.scatterplot(data=df_prof, x='Trend_State', y='Floor_Proximity', hue='Status', 
                    palette={'Captured (Crash)': 'blue', 'Missed (Unknown)': 'darkorange'}, 
                    alpha=0.7, s=50)
    plt.title('Archetype Map: Trend State vs Floor Proximity')
    plt.xlabel('Macro Trend State (SMA_144 - SMA_377) / Close [%]')
    plt.ylabel('Floor Proximity (0 = High, 1 = Absolute Bottom)')
    plt.axvline(x=0, color='black', linestyle='--')
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.savefig('missed_archetype_scatter.png', dpi=300)
    
    print("Generating KDE Plots...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    sns.kdeplot(data=df_prof, x='RSI_14', hue='Status', 
                palette={'Captured (Crash)': 'blue', 'Missed (Unknown)': 'darkorange'}, 
                fill=True, ax=axes[0])
    axes[0].set_title('1h RSI Distribution')
    
    sns.kdeplot(data=df_prof, x='Trend_State', hue='Status', 
                palette={'Captured (Crash)': 'blue', 'Missed (Unknown)': 'darkorange'}, 
                fill=True, ax=axes[1])
    axes[1].set_title('Macro Trend State Distribution')
    
    plt.tight_layout()
    plt.savefig('missed_kde_plots.png', dpi=300)
    print("Saved plots.")
    
    # Calculate stats for the text box
    captured_trend_gt_0 = df_prof[(df_prof['captured'] == True) & (df_prof['Trend_State'] > 0)]
    missed_trend_gt_0 = df_prof[(df_prof['captured'] == False) & (df_prof['Trend_State'] > 0)]
    print(f"Captured with Trend > 0: {len(captured_trend_gt_0)}")
    print(f"Missed with Trend > 0: {len(missed_trend_gt_0)}")

if __name__ == '__main__':
    main()
