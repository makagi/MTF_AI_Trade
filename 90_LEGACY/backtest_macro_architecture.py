import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import glob
import os
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

def calculate_bb(series, period, std_dev=2.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return sma + (std * std_dev), sma - (std * std_dev)

def calc_sandwich_ratio(levels, close, atr):
    ceilings = [l for l in levels if l > close]
    floors = [l for l in levels if l <= close]
    ceiling = min(ceilings) if ceilings else close + atr*5
    floor = max(floors) if floors else close - atr*5
    return (close - floor) / (ceiling - floor + 1e-8)

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

def run_backtest(df, armed_col):
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    atrs = df['ATR_1h'].values
    armed = df[armed_col].values
    
    in_position = False
    entry_price = 0
    sl = 0
    tp = 0
    expiration_idx = 0
    entry_i = 0
    atr_entry = 0
    
    trades = []
    equity_curve = np.zeros(len(df))
    current_equity = 0.0
    
    for i in range(1, len(df)):
        if in_position:
            # Check exits
            hit_sl = lows[i] <= sl
            hit_tp = highs[i] >= tp
            timeout = i >= expiration_idx
            
            if hit_sl or hit_tp or timeout:
                if hit_sl:
                    exit_price = sl
                elif hit_tp:
                    exit_price = tp
                else:
                    exit_price = closes[i]
                    
                # Net Return % = (exit - entry)/entry - 0.004 (0.4% fees/slippage)
                trade_ret = (exit_price - entry_price) / entry_price - 0.004
                
                current_equity += trade_ret * 100 # cumulative % return
                trades.append({
                    'entry_i': entry_i,
                    'exit_i': i,
                    'ret': trade_ret * 100,
                    'is_win': trade_ret > 0,
                    'r_multiple': (exit_price - entry_price) / atr_entry if atr_entry > 0 else 0
                })
                in_position = False
                
        if not in_position:
            # Detect False -> True transition for naive immediate entry
            if armed[i] and not armed[i-1]:
                atr_entry = atrs[i]
                if pd.isna(atr_entry) or atr_entry == 0:
                    continue
                in_position = True
                entry_price = closes[i]
                sl = entry_price - 1.0 * atr_entry
                tp = entry_price + 2.5 * atr_entry
                expiration_idx = i + 72 * 60 # 72 hours
                entry_i = i
                
        equity_curve[i] = current_equity
        
    return equity_curve, trades

def calculate_stats(trades, equity_curve):
    if len(trades) == 0:
        return {"Total PnL (%)": 0, "Win Rate (%)": 0, "Profit Factor": 0, "Max Drawdown (%)": 0, "Trades": 0}
        
    df_t = pd.DataFrame(trades)
    total_pnl = df_t['ret'].sum()
    win_rate = df_t['is_win'].mean() * 100
    
    gross_profit = df_t[df_t['ret'] > 0]['ret'].sum()
    gross_loss = abs(df_t[df_t['ret'] < 0]['ret'].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Max Drawdown
    roll_max = np.maximum.accumulate(equity_curve)
    drawdowns = roll_max - equity_curve
    max_dd = drawdowns.max()
    
    return {
        "Total PnL (%)": total_pnl,
        "Win Rate (%)": win_rate,
        "Profit Factor": pf,
        "Max Drawdown (%)": max_dd,
        "Trades": len(trades)
    }

def main():
    print("Loading 1h Data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    df_1h['Trend_State'] = (df_1h['FIB_11_SMA'] - df_1h['FIB_13_SMA']) / df_1h['close'] * 100
    
    df_1h['BB_144_Upper'], df_1h['BB_144_Lower'] = calculate_bb(df_1h['close'], 144, 2.0)
    df_1h['BB_377_Upper'], df_1h['BB_377_Lower'] = calculate_bb(df_1h['close'], 377, 2.0)
    
    # Squeeze Index
    fib_periods = {7: 21, 9: 55, 11: 144, 13: 377}
    total_bb_width = 0
    for k, period in fib_periods.items():
        std = df_1h['close'].rolling(period).std()
        sma = df_1h[f'FIB_{k}_SMA']
        total_bb_width += (4 * std) / sma
    
    roll_min = total_bb_width.rolling(720).min()
    roll_max = total_bb_width.rolling(720).max()
    df_1h['Squeeze_Index'] = (total_bb_width - roll_min) / (roll_max - roll_min + 1e-8)
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    
    print("Calculating SR_Long...")
    cols_long = ['FIB_11_SMA', 'FIB_12_SMA', 'FIB_13_SMA', 'BB_144_Upper', 'BB_144_Lower', 'BB_377_Upper', 'BB_377_Lower']
    sr_long_list = []
    for i in range(len(df_1h_2025)):
        row = df_1h_2025.iloc[i]
        c = row['close']
        atr = row['ATR_14']
        if pd.isna(atr): 
            sr_long_list.append(np.nan)
            continue
        levels_long = [row[col] for col in cols_long if not pd.isna(row[col])]
        sr_long_list.append(calc_sandwich_ratio(levels_long, c, atr) if levels_long else np.nan)
    df_1h_2025['SR_Long'] = sr_long_list
    
    print("Loading 1m Data and Mapping...")
    df_1m = load_all_1m_data_2025()
    
    # Mapping
    df_1h_mapped = df_1h_2025[['ATR_14', 'Trend_State', 'SR_Long', 'Squeeze_Index']]
    df_1h_mapped = df_1h_mapped.reindex(df_1m.index.floor('h')).ffill().values
    
    df_1m['ATR_1h'] = df_1h_mapped[:, 0]
    df_1m['Trend_State_1h'] = df_1h_mapped[:, 1]
    df_1m['SR_Long_1h'] = df_1h_mapped[:, 2]
    df_1m['Squeeze_Index_1h'] = df_1h_mapped[:, 3]
    
    print("Calculating Macro Triggers...")
    rolling_high_30m = df_1m['high'].rolling('30min').max()
    panic_mask = (rolling_high_30m - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    armed_single = panic_mask.rolling('2h').max() > 0
    
    rolling_high_60m = df_1m['high'].rolling('60min').max()
    trend_dip_mask = (df_1m['Trend_State_1h'] > 1.5) & ((rolling_high_60m - df_1m['low']) >= (1.0 * df_1m['ATR_1h']))
    armed_trend = trend_dip_mask.rolling('1h').max() > 0
    
    df_1m['Armed_Base'] = armed_single | armed_trend
    df_1m['Armed_Vetoed'] = df_1m['Armed_Base'] & (df_1m['SR_Long_1h'] <= 0.8)
    df_1m['Armed_Ghost'] = (df_1m['SR_Long_1h'] < 0.1) & (df_1m['Squeeze_Index_1h'] < 0.5)
    df_1m['Armed_Final'] = df_1m['Armed_Vetoed'] | df_1m['Armed_Ghost']
    
    print("Running Rigorous 1m Backtests...")
    eq_base, trades_base = run_backtest(df_1m, 'Armed_Base')
    eq_final, trades_final = run_backtest(df_1m, 'Armed_Final')
    
    stats_base = calculate_stats(trades_base, eq_base)
    stats_final = calculate_stats(trades_final, eq_final)
    
    print("\n--- Baseline Logic (Dual Trigger Only) ---")
    for k, v in stats_base.items(): print(f"{k}: {v:.2f}")
        
    print("\n--- Final Macro Architecture (Dual + SR Veto + SR Ghost) ---")
    for k, v in stats_final.items(): print(f"{k}: {v:.2f}")
    
    # Plotting
    plt.figure(figsize=(14, 7))
    plt.plot(df_1m.index, eq_base, label='Baseline (Dual Trigger)', color='gray', alpha=0.7, linewidth=1.5)
    plt.plot(df_1m.index, eq_final, label='Final Macro (Dual + SR Veto + SR Ghost)', color='forestgreen', linewidth=2)
    
    # Add stats box
    stats_text = (
        f"FINAL MACRO STATS (Naive Immediate Entry)\n"
        f"-----------------------------------------\n"
        f"Total PnL : +{stats_final['Total PnL (%)']:.1f}%\n"
        f"Win Rate  :  {stats_final['Win Rate (%)']:.1f}%\n"
        f"Prof. Fact:  {stats_final['Profit Factor']:.2f}\n"
        f"Max DD    : -{stats_final['Max Drawdown (%)']:.1f}%\n"
        f"Trades    :  {stats_final['Trades']}"
    )
    plt.gca().text(0.02, 0.95, stats_text, transform=plt.gca().transAxes, fontsize=11,
                 verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='black'), family='monospace')
                 
    plt.title("Rigorous 1m Backtest (No Micro AI): Baseline vs Final Macro Architecture", fontsize=15, fontweight='bold', pad=20)
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Cumulative Net PnL (%)", fontsize=12)
    plt.legend(loc='upper right', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig("macro_backtest_equity.png", dpi=300)
    print("Saved macro_backtest_equity.png")

if __name__ == '__main__':
    main()
