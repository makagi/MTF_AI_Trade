import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def calculate_atr(df, p=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['ATR'] = np.max(ranges, axis=1).rolling(p).mean()
    return df

def get_fib_periods():
    return [21, 55, 144, 233, 377, 610, 987, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        df[f'SMA_{p}'] = sma
        
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'BB_Upper_{p}'] = upper
        df[f'BB_Lower_{p}'] = lower
        
        bw = (upper - lower) / df['close']
        df[f'BW_Pct_{p}'] = bw.rolling(720).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] if not pd.isna(x).any() else np.nan)
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
    return df

def simulate_v3(df, start_capital=10000):
    # Re-run V3 for baseline
    bw144_q = ((df['SMA_144'] + 2*df['close'].rolling(144).std()) - (df['SMA_144'] - 2*df['close'].rolling(144).std())) / df['close']
    bw144_thresh = bw144_q.rolling(720).quantile(0.4)
    cond_macro_vol = (bw144_q < bw144_thresh)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55']) & (df['AFS_21'].shift(1) <= df['AFS_55'].shift(1))
    
    price_low = df['low'].rolling(24).min()
    price_prev_low = df['low'].shift(24).rolling(96).min()
    afs_curr = df['AFS_144'].rolling(24).min()
    afs_prev = df['AFS_144'].shift(24).rolling(96).min()
    bull_div = (price_low < price_prev_low) & (afs_curr > afs_prev)
    
    sma_cols = ['SMA_144', 'SMA_377', 'SMA_610', 'SMA_1597']
    def get_void(row):
        smas = row[sma_cols]
        ceiling = smas[smas > row['close']].min()
        if pd.isna(ceiling): return 10 
        return (ceiling - row['close']) / row['ATR']
    
    # We use vectorization where possible to speed up
    df['Void_ATR'] = df.apply(get_void, axis=1)
    engine1_signals = df[cond_macro_vol & cond_micro_mom & bull_div & (df['Void_ATR'] >= 3.0)].index
    
    cross_233_377 = (df['SMA_233'] > df['SMA_377']) & (df['SMA_233'].shift(1) <= df['SMA_377'].shift(1))
    is_hugging = (df['close'] > df['SMA_377']) & ((df['close'] - df['SMA_377']) / df['ATR'] < 1.5)
    engine2_signals = df[cross_233_377 & is_hugging].index
    
    macro_low = df['low'].shift(24).rolling(720).min()
    near_macro_bottom = (df['low'] <= macro_low * 1.01)
    v_shape_cross = (df['AFS_7'] > df['AFS_21']) & (df['AFS_7'].shift(1) <= df['AFS_21'].shift(1)) if 'AFS_7' in df.columns else (df['AFS_21'] > df['AFS_55']) & (df['AFS_21'].shift(1) <= df['AFS_55'].shift(1))
    engine3_signals = df[near_macro_bottom & v_shape_cross].index
    
    v3_signals = engine1_signals.union(engine2_signals).union(engine3_signals).sort_values()
    
    trades = []
    risk_pct = 0.01
    
    for idx in v3_signals:
        loc = df.index.get_loc(idx)
        if loc + 96 >= len(df): continue
        entry_price = df['close'].iloc[loc]
        sl_price = entry_price - (1.5 * df['ATR'].iloc[loc])
        
        # Risk exactly $100 per 10k
        qty = (start_capital * risk_pct) / (entry_price - sl_price)
        
        window = df.iloc[loc+1 : loc+97]
        exit_time = window.index[-1]
        exit_price = window['close'].iloc[-1]
        
        for i in range(len(window)):
            if window['low'].iloc[i] <= sl_price:
                exit_time = window.index[i]
                exit_price = sl_price
                break
                
        pnl = (exit_price - entry_price) * qty
        trades.append({'exit_time': exit_time, 'pnl': pnl})
        
    return pd.DataFrame(trades)

def simulate_v4(df, start_capital=10000):
    periods = get_fib_periods()
    trades = []
    risk_pct = 0.01
    
    # Pre-calculate crossing for speed
    crosses = {}
    for i in range(1, len(periods)):
        k_micro = periods[i-1]
        k_ignite = periods[i]
        # AFS crosses up
        crosses[k_ignite] = (df[f'AFS_{k_micro}'] > df[f'AFS_{k_ignite}']) & (df[f'AFS_{k_micro}'].shift(1) <= df[f'AFS_{k_ignite}'].shift(1))
    
    # To optimize, we find indices where AT LEAST ONE cross happened
    any_cross = pd.Series(False, index=df.index)
    for c in crosses.values():
        any_cross = any_cross | c
        
    cross_indices = df[any_cross].index
    
    for idx in cross_indices:
        loc = df.index.get_loc(idx)
        if loc < 720 or loc + 120 >= len(df):
            continue
            
        row = df.iloc[loc]
        bw_pcts = {p: row[f'BW_Pct_{p}'] for p in periods[1:-2]} # Don't use 21 as ignite (no micro), nor 987/1597 (no macro target)
        
        if any(pd.isna(v) for v in bw_pcts.values()):
            continue
            
        k_ignite = min(bw_pcts, key=bw_pcts.get)
        min_bw_pct = bw_pcts[k_ignite]
        
        if min_bw_pct > 0.2: # Must be heavily squeezed
            continue
            
        # Check if the cross happened on THIS specific k_ignite
        if not crosses[k_ignite].iloc[loc]:
            continue
            
        # Dynamic Risk-Reward Setup
        k_ignite_idx = periods.index(k_ignite)
        k_target = periods[min(k_ignite_idx + 2, len(periods)-1)]
        
        entry_price = row['close']
        sl_price = row[f'BB_Lower_{k_ignite}']
        tp_price = row[f'SMA_{k_target}']
        
        # Valid trade check (Target must be above entry, SL below)
        if tp_price <= entry_price or sl_price >= entry_price:
            continue
            
        # Optional: ensure min RR
        rr = (tp_price - entry_price) / (entry_price - sl_price)
        if rr < 1.0:
            continue
            
        qty = (start_capital * risk_pct) / (entry_price - sl_price)
        
        # Fast forward simulation
        window = df.iloc[loc+1 : loc+168] # Give it 1 week to play out
        exit_time = window.index[-1]
        exit_price = window['close'].iloc[-1]
        
        for i in range(len(window)):
            if window['low'].iloc[i] <= sl_price:
                exit_time = window.index[i]
                exit_price = sl_price
                break
            if window['high'].iloc[i] >= tp_price:
                exit_time = window.index[i]
                exit_price = tp_price
                break
                
        pnl = (exit_price - entry_price) * qty
        trades.append({'exit_time': exit_time, 'pnl': pnl})
        
    return pd.DataFrame(trades)

def build_equity_curve(df, trades, start_capital=10000):
    daily_dates = df.resample('D').first().index
    equity = pd.Series(index=daily_dates, dtype=float)
    equity.iloc[0] = start_capital
    
    if len(trades) == 0:
        equity = equity.fillna(start_capital)
        return equity
        
    trades['exit_date'] = trades['exit_time'].dt.floor('D')
    daily_pnl = trades.groupby('exit_date')['pnl'].sum()
    
    current_capital = start_capital
    for date in equity.index:
        if date in daily_pnl.index:
            current_capital += daily_pnl[date]
        equity[date] = current_capital
        
    return equity

def calculate_stats(equity, trades):
    total_return = (equity.iloc[-1] - equity.iloc[0]) / equity.iloc[0] * 100
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max * 100
    max_dd = drawdown.min()
    
    is_flat = (equity < rolling_max)
    flat_streaks = is_flat.groupby((~is_flat).cumsum()).sum()
    max_days_flat = flat_streaks.max() if len(flat_streaks) > 0 else 0
    
    win_rate = len(trades[trades['pnl'] > 0]) / len(trades) * 100 if len(trades) > 0 else 0
    trade_count = len(trades)
    
    return total_return, max_dd, max_days_flat, win_rate, trade_count

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    start_cap = 10000
    t3 = simulate_v3(df, start_cap)
    t4 = simulate_v4(df, start_cap)
    
    eq3 = build_equity_curve(df, t3, start_cap)
    eq4 = build_equity_curve(df, t4, start_cap)
    
    s3 = calculate_stats(eq3, t3)
    s4 = calculate_stats(eq4, t4)
    
    # Plotting
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14, 8))
    
    ax.plot(eq3.index, eq3.values, color='cyan', alpha=0.6, linewidth=2, label=f'V3 (Hardcoded Multi-Engine): Ret {s3[0]:.1f}%, MDD {s3[1]:.1f}%')
    ax.plot(eq4.index, eq4.values, color='lime', linewidth=3, label=f'V4 (Scale-Invariant Dynamic): Ret {s4[0]:.1f}%, MDD {s4[1]:.1f}%')
    
    ax.set_title("V3 vs V4: The Evolution to Scale-Invariance\nDynamically adapting SL and TP across all Fractal Scales", fontsize=16, color='white')
    ax.set_ylabel("Account Balance ($)")
    ax.legend(loc='upper left', fontsize=12)
    ax.grid(color='white', alpha=0.1)
    
    col_labels = ['Total Return', 'Max Drawdown', 'Max Days Flat', 'Win Rate', 'Total Trades']
    row_labels = ['V3 (Hardcoded 377)', 'V4 (Scale-Invariant)']
    table_vals = [
        [f"{s3[0]:.1f}%", f"{s3[1]:.1f}%", f"{s3[2]:.0f} days", f"{s3[3]:.1f}%", f"{s3[4]}"],
        [f"{s4[0]:.1f}%", f"{s4[1]:.1f}%", f"{s4[2]:.0f} days", f"{s4[3]:.1f}%", f"{s4[4]}"]
    ]
    
    table = plt.table(cellText=table_vals, rowLabels=row_labels, colLabels=col_labels, 
                      loc='lower center', cellLoc='center', bbox=[0.1, -0.3, 0.8, 0.2])
    table.set_fontsize(12)
    table.scale(1, 1.5)
    for key, cell in table.get_celld().items():
        cell.set_facecolor('black')
        cell.set_text_props(color='white')
    
    plt.subplots_adjust(bottom=0.3)
    plt.savefig("v4_equity_evolution.png", dpi=300, bbox_inches='tight')
    print("Saved v4_equity_evolution.png")

if __name__ == '__main__':
    main()
