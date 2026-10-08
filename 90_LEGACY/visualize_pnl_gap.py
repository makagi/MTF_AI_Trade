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
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    oracle_1h_indices = labels[labels['tb_return'] == 1].index
    
    print("Loading 1m Data...")
    df_1m = load_all_1m_data_2025()
    
    print("Extracting exact 1m Oracle times...")
    oracle_data = []
    for t_oracle in tqdm(oracle_1h_indices):
        t_start = t_oracle - pd.Timedelta(hours=1)
        t_end = t_oracle + pd.Timedelta(hours=1, minutes=59)
        window = df_1m.loc[t_start:t_end]
        if len(window) > 0:
            true_bottom_idx = window['low'].idxmin()
            true_bottom_price = window.loc[true_bottom_idx, 'low']
            
            # Fetch the 1h ATR at the time of the bottom
            atr = df_1h_2025.loc[true_bottom_idx.floor('h'), 'ATR_14']
            if pd.isna(atr): continue
                
            # Calculate Net PnL percentage (TP is 2.5 ATR, Fee is 0.4% round trip)
            gross_pnl_pct = (2.5 * atr) / true_bottom_price
            net_pnl_pct = gross_pnl_pct - 0.004
            
            oracle_data.append({
                'time': true_bottom_idx,
                'price': true_bottom_price,
                'atr': atr,
                'net_pnl_pct': net_pnl_pct
            })
            
    # Convert to DataFrame
    df_oracles = pd.DataFrame(oracle_data)
    df_oracles.drop_duplicates(subset=['time'], inplace=True)
    df_oracles.set_index('time', inplace=True)
    df_oracles.sort_index(inplace=True)
    
    print(f"Total Unique Oracles: {len(df_oracles)}")
    
    # Vectorize New Logic (1.5 ATR drop in 30min -> 2h decay)
    df_1m['ATR_1h'] = df_1h_2025['ATR_14'].reindex(df_1m.index, method='ffill')
    rolling_high = df_1m['high'].rolling('30min').max()
    trigger_mask = (rolling_high - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    df_1m['Armed_New'] = trigger_mask.rolling('2h').max() > 0
    
    # Map captures to Oracles
    df_oracles['captured'] = df_1m['Armed_New'].reindex(df_oracles.index).fillna(False)
    
    # Analyze Oracles by PnL profitability
    profitable_oracles = df_oracles[df_oracles['net_pnl_pct'] > 0]
    junk_oracles = df_oracles[df_oracles['net_pnl_pct'] <= 0]
    
    print(f"Profitable Oracles (> 0.4% fee): {len(profitable_oracles)}")
    print(f"Junk Oracles (Fee loss): {len(junk_oracles)}")
    
    # PnL Simulation (assuming 1 unit of capital compounded)
    # Actually, let's just do simple cumulative return (sum of percentages) for easier reading
    df_oracles['cumulative_ideal'] = profitable_oracles['net_pnl_pct'].cumsum()
    df_oracles['cumulative_ideal'].fillna(method='ffill', inplace=True)
    df_oracles['cumulative_ideal'].fillna(0, inplace=True)
    
    captured_oracles = df_oracles[(df_oracles['captured'] == True) & (df_oracles['net_pnl_pct'] > 0)]
    df_oracles['cumulative_captured'] = captured_oracles['net_pnl_pct'].cumsum()
    df_oracles['cumulative_captured'].fillna(method='ffill', inplace=True)
    df_oracles['cumulative_captured'].fillna(0, inplace=True)
    
    missed_oracles = df_oracles[(df_oracles['captured'] == False) & (df_oracles['net_pnl_pct'] > 0)]
    df_oracles['cumulative_missed'] = missed_oracles['net_pnl_pct'].cumsum()
    df_oracles['cumulative_missed'].fillna(method='ffill', inplace=True)
    df_oracles['cumulative_missed'].fillna(0, inplace=True)
    
    # Plotting
    plt.figure(figsize=(14, 8))
    plt.plot(df_oracles.index, df_oracles['cumulative_ideal'] * 100, label='Ideal (All Profitable Oracles)', color='blue', linewidth=2, alpha=0.5)
    plt.plot(df_oracles.index, df_oracles['cumulative_captured'] * 100, label='Captured (New Logic)', color='green', linewidth=3)
    plt.plot(df_oracles.index, df_oracles['cumulative_missed'] * 100, label='Missed (The Gap)', color='red', linestyle='--', linewidth=2)
    
    plt.title('Opportunity Cost Analysis: Ideal vs Captured PnL Gap (2025)')
    plt.xlabel('Date')
    plt.ylabel('Cumulative Profit (%)')
    plt.grid(True, linestyle=':', alpha=0.7)
    
    # Annotations
    final_ideal = df_oracles['cumulative_ideal'].iloc[-1] * 100
    final_captured = df_oracles['cumulative_captured'].iloc[-1] * 100
    final_missed = df_oracles['cumulative_missed'].iloc[-1] * 100
    
    plt.text(df_oracles.index[-1], final_ideal, f" Ideal: +{final_ideal:.1f}%", color='blue', fontsize=11, va='center')
    plt.text(df_oracles.index[-1], final_captured, f" Captured: +{final_captured:.1f}%", color='green', fontsize=12, weight='bold', va='center')
    plt.text(df_oracles.index[-1], final_missed, f" Missed: +{final_missed:.1f}%", color='red', fontsize=11, va='center')
    
    # Text box with analysis
    cap_rate_count = len(captured_oracles) / len(profitable_oracles) * 100
    cap_rate_pnl = final_captured / final_ideal * 100
    
    stats_text = (f"Total Profitable Oracles: {len(profitable_oracles)}\n"
                  f"Captured Count Rate: {cap_rate_count:.1f}%\n"
                  f"Captured PnL Rate: {cap_rate_pnl:.1f}%\n"
                  f"Junk Oracles Avoided: {len(junk_oracles)} (Fee traps)")
    
    props = dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='black')
    plt.gca().text(0.02, 0.95, stats_text, transform=plt.gca().transAxes, fontsize=12, verticalalignment='top', bbox=props)
    
    plt.legend(loc='upper left', bbox_to_anchor=(0.02, 0.75))
    plt.tight_layout()
    plt.savefig('pnl_gap_analysis.png', dpi=300)
    print("Saved pnl_gap_analysis.png")
    
    # Save the text stats for easy retrieval
    with open('pnl_stats.txt', 'w') as f:
        f.write(f"Count_Rate: {cap_rate_count:.1f}\n")
        f.write(f"PnL_Rate: {cap_rate_pnl:.1f}\n")
        f.write(f"Junk_Avoided: {len(junk_oracles)}\n")

if __name__ == '__main__':
    main()
