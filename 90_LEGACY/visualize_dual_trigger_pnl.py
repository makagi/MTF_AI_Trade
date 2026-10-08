import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import glob
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features

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
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    
    # Macro Trend State
    df_1h['Trend_State'] = (df_1h['FIB_11_SMA'] - df_1h['FIB_13_SMA']) / df_1h['close'] * 100
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    oracle_1h_indices = labels[labels['tb_return'] == 1].index
    
    print("Loading 1m Data...")
    df_1m = load_all_1m_data_2025()
    
    # Map 1h features to 1m
    df_1m['ATR_1h'] = df_1h_2025['ATR_14'].reindex(df_1m.index, method='ffill')
    df_1m['Trend_State_1h'] = df_1h_2025['Trend_State'].reindex(df_1m.index, method='ffill')
    
    # 1. Single Trigger (Panic Trigger)
    print("Calculating Single Trigger...")
    rolling_high_30m = df_1m['high'].rolling('30min').max()
    panic_mask = (rolling_high_30m - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    df_1m['Armed_Single'] = panic_mask.rolling('2h').max() > 0
    
    # 2. Dual Trigger (Panic + Trend Dip)
    print("Calculating Trend Dip Trigger...")
    rolling_high_60m = df_1m['high'].rolling('60min').max()
    trend_dip_mask = (df_1m['Trend_State_1h'] > 1.5) & ((rolling_high_60m - df_1m['low']) >= (1.0 * df_1m['ATR_1h']))
    
    # Dual Armed State
    print("Calculating Dual Armed State...")
    armed_trend = trend_dip_mask.rolling('1h').max() > 0
    df_1m['Armed_Dual'] = df_1m['Armed_Single'] | armed_trend
    
    time_burden_single = df_1m['Armed_Single'].mean() * 100
    time_burden_dual = df_1m['Armed_Dual'].mean() * 100
    print(f"Time Burden - Single: {time_burden_single:.1f}%")
    print(f"Time Burden - Dual:   {time_burden_dual:.1f}%")
    
    print("Extracting exact 1m Oracle times...")
    oracle_data = []
    for t_oracle in tqdm(oracle_1h_indices):
        t_start = t_oracle - pd.Timedelta(hours=1)
        t_end = t_oracle + pd.Timedelta(hours=1, minutes=59)
        window = df_1m.loc[t_start:t_end]
        if len(window) > 0:
            true_bottom_idx = window['low'].idxmin()
            true_bottom_price = window.loc[true_bottom_idx, 'low']
            
            t_1h_floor = true_bottom_idx.floor('h')
            atr = df_1h_2025.loc[t_1h_floor, 'ATR_14'] if t_1h_floor in df_1h_2025.index else np.nan
            if pd.isna(atr): continue
                
            net_pnl_pct = (2.5 * atr / true_bottom_price) - 0.004
            
            oracle_data.append({
                'time': true_bottom_idx,
                'captured_single': df_1m.loc[true_bottom_idx, 'Armed_Single'] if true_bottom_idx in df_1m.index else False,
                'captured_dual': df_1m.loc[true_bottom_idx, 'Armed_Dual'] if true_bottom_idx in df_1m.index else False,
                'net_pnl_pct': net_pnl_pct
            })
            
    df_oracles = pd.DataFrame(oracle_data)
    df_oracles.drop_duplicates(subset=['time'], inplace=True)
    df_oracles.set_index('time', inplace=True)
    df_oracles.sort_index(inplace=True)
    
    df_prof = df_oracles[df_oracles['net_pnl_pct'] > 0].copy()
    
    # Calculate Cumulative PnLs
    df_prof['ideal_pnl'] = df_prof['net_pnl_pct'].cumsum() * 100
    
    single_pnl = df_prof[df_prof['captured_single'] == True]['net_pnl_pct'].cumsum() * 100
    df_prof['single_pnl'] = single_pnl.reindex(df_prof.index, method='ffill').fillna(0)
    
    dual_pnl = df_prof[df_prof['captured_dual'] == True]['net_pnl_pct'].cumsum() * 100
    df_prof['dual_pnl'] = dual_pnl.reindex(df_prof.index, method='ffill').fillna(0)
    
    # Plotting
    plt.figure(figsize=(14, 8))
    plt.plot(df_prof.index, df_prof['ideal_pnl'], label='Ideal (All Profitable Oracles)', color='blue', linewidth=2, linestyle=':', alpha=0.5)
    plt.plot(df_prof.index, df_prof['single_pnl'], label='Single Trigger (Panic Only)', color='green', linewidth=2, alpha=0.7)
    plt.plot(df_prof.index, df_prof['dual_pnl'], label='Dual Trigger (Panic + Trend Dip)', color='gold', linewidth=3)
    
    plt.title('Dual-Trigger Implementation: Reclaiming the Missed PnL (2025)')
    plt.xlabel('Date')
    plt.ylabel('Cumulative Profit (%)')
    plt.grid(True, linestyle=':', alpha=0.7)
    
    final_ideal = df_prof['ideal_pnl'].iloc[-1]
    final_single = df_prof['single_pnl'].iloc[-1]
    final_dual = df_prof['dual_pnl'].iloc[-1]
    
    plt.text(df_prof.index[-1], final_ideal, f" Ideal: +{final_ideal:.1f}%", color='blue', fontsize=11, va='center')
    plt.text(df_prof.index[-1], final_single, f" Single: +{final_single:.1f}%", color='green', fontsize=11, va='center')
    plt.text(df_prof.index[-1], final_dual, f" Dual: +{final_dual:.1f}%", color='darkgoldenrod', fontsize=13, weight='bold', va='center')
    
    # Fill between to show the reclaimed profit
    plt.fill_between(df_prof.index, df_prof['single_pnl'], df_prof['dual_pnl'], color='gold', alpha=0.3, label='Reclaimed Profit (The Gap Closed)')
    
    stats_text = (f"Time Burden (Single): {time_burden_single:.1f}%\n"
                  f"Time Burden (Dual): {time_burden_dual:.1f}%\n"
                  f"PnL Rate (Single): {(final_single/final_ideal*100):.1f}%\n"
                  f"PnL Rate (Dual): {(final_dual/final_ideal*100):.1f}%")
    
    props = dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='black')
    plt.gca().text(0.02, 0.95, stats_text, transform=plt.gca().transAxes, fontsize=12, verticalalignment='top', bbox=props)
    
    plt.legend(loc='center left', bbox_to_anchor=(0.02, 0.70))
    plt.tight_layout()
    plt.savefig('dual_trigger_pnl.png', dpi=300)
    print("Saved dual_trigger_pnl.png")

if __name__ == '__main__':
    main()
