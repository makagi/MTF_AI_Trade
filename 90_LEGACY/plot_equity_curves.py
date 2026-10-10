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
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(p).mean()
    df['ATR_144'] = true_range.rolling(144).mean()
    return df

def get_fib_periods():
    return [7, 21, 55, 144, 233, 377, 610, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        df[f'SMA_{p}'] = sma
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
    return df

def simulate_trades(df, signals, risk_pct=0.01, start_capital=10000):
    # We assume 1.5 ATR is the stop loss distance
    sl_atr_multiplier = 1.5
    
    trades = []
    # To avoid overlapping trades taking double capital, we just log them and process sequentially
    # But since they are rare, we can just process all signals.
    for idx in signals:
        loc = df.index.get_loc(idx)
        if loc + 48 >= len(df):
            continue
            
        entry_price = df['close'].iloc[loc]
        atr = df['ATR'].iloc[loc]
        sl_price = entry_price - (atr * sl_atr_multiplier)
        
        # Risk exactly $100 (1% of 10000) for a drop of 1.5 ATR
        # (entry - sl) * qty = risk_amount
        risk_amount = start_capital * risk_pct
        qty = risk_amount / (entry_price - sl_price)
        
        # Check trajectory for next 48h
        window = df.iloc[loc+1 : loc+49]
        exit_time = window.index[-1]
        exit_price = window['close'].iloc[-1]
        hit_sl = False
        
        for i in range(len(window)):
            if window['low'].iloc[i] <= sl_price:
                exit_time = window.index[i]
                exit_price = sl_price
                hit_sl = True
                break
                
        pnl = (exit_price - entry_price) * qty
        trades.append({
            'entry_time': idx,
            'exit_time': exit_time,
            'pnl': pnl
        })
        
    return pd.DataFrame(trades)

def build_equity_curve(df, trades, start_capital=10000):
    # Daily equity curve
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

def calculate_stats(equity):
    total_return = (equity.iloc[-1] - equity.iloc[0]) / equity.iloc[0] * 100
    
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max * 100
    max_dd = drawdown.min()
    
    # Max Days Flat (Drawdown Duration)
    # Count consecutive days where equity < rolling_max
    is_flat = (equity < rolling_max)
    flat_streaks = is_flat.groupby((~is_flat).cumsum()).sum()
    max_days_flat = flat_streaks.max()
    
    # Calmar Ratio Proxy (Total Return / Abs(Max DD))
    calmar = total_return / abs(max_dd) if max_dd < 0 else np.inf
    
    return total_return, max_dd, max_days_flat, calmar

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    # V1: Base System
    bw144_q = ((df['SMA_144'] + 2*df['close'].rolling(144).std()) - (df['SMA_144'] - 2*df['close'].rolling(144).std())) / df['close']
    bw144_thresh = bw144_q.rolling(720).quantile(0.4)
    cond_macro_vol = (bw144_q < bw144_thresh)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55']) & (df['AFS_21'].shift(1) <= df['AFS_55'].shift(1))
    v1_signals = df[cond_macro_vol & cond_micro_mom].index
    
    # V2: Engine 1 Only (Divergence + Void)
    price_low = df['low'].rolling(24).min()
    price_prev_low = df['low'].shift(24).rolling(96).min()
    afs_curr = df['AFS_144'].rolling(24).min()
    afs_prev = df['AFS_144'].shift(24).rolling(96).min()
    bull_div = (price_low < price_prev_low) & (afs_curr > afs_prev)
    
    sma_cols = ['SMA_144', 'SMA_377', 'SMA_610', 'SMA_1597']
    def get_void(row):
        smas = row[sma_cols]
        ceiling = smas[smas > row['close']].min()
        if pd.isna(ceiling):
            ceiling = row['close'] * 1.5 
        return (ceiling - row['close']) / row['ATR_144']
    df['Void_ATR'] = df.apply(get_void, axis=1)
    
    engine1_signals = df[cond_macro_vol & cond_micro_mom & bull_div & (df['Void_ATR'] >= 3.0)].index
    
    # V3: Multi-Engine
    cross_233_377 = (df['SMA_233'] > df['SMA_377']) & (df['SMA_233'].shift(1) <= df['SMA_377'].shift(1))
    is_hugging = (df['close'] > df['SMA_377']) & ((df['close'] - df['SMA_377']) / df['ATR_144'] < 1.5)
    engine2_signals = df[cross_233_377 & is_hugging].index
    
    macro_low = df['low'].shift(24).rolling(720).min()
    near_macro_bottom = (df['low'] <= macro_low * 1.01)
    v_shape_cross = (df['AFS_7'] > df['AFS_21']) & (df['AFS_7'].shift(1) <= df['AFS_21'].shift(1)) & (df['AFS_21'] < 20)
    engine3_signals = df[near_macro_bottom & v_shape_cross].index
    
    v3_signals = engine1_signals.union(engine2_signals).union(engine3_signals).sort_values()
    
    print(f"Signals -> V1: {len(v1_signals)}, V2: {len(engine1_signals)}, V3: {len(v3_signals)}")
    
    # Simulate
    start_cap = 10000
    t1 = simulate_trades(df, v1_signals, 0.01, start_cap)
    t2 = simulate_trades(df, engine1_signals, 0.01, start_cap)
    t3 = simulate_trades(df, v3_signals, 0.01, start_cap)
    
    eq1 = build_equity_curve(df, t1, start_cap)
    eq2 = build_equity_curve(df, t2, start_cap)
    eq3 = build_equity_curve(df, t3, start_cap)
    
    s1 = calculate_stats(eq1)
    s2 = calculate_stats(eq2)
    s3 = calculate_stats(eq3)
    
    # Plotting
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(14, 8))
    
    ax.plot(eq1.index, eq1.values, color='gray', alpha=0.5, label=f'V1 (Base): Ret {s1[0]:.1f}%, MDD {s1[1]:.1f}%')
    ax.plot(eq2.index, eq2.values, color='blue', linewidth=2, label=f'V2 (Engine 1): Ret {s2[0]:.1f}%, MDD {s2[1]:.1f}%')
    ax.plot(eq3.index, eq3.values, color='lime', linewidth=3, label=f'V3 (Multi-Engine): Ret {s3[0]:.1f}%, MDD {s3[1]:.1f}%')
    
    ax.set_title("Equity Curve Comparison ($10,000 Initial, 1% Risk/Trade, 48h Hold)\nThe Power of Multi-Engine Orthogonality", fontsize=16, color='white')
    ax.set_ylabel("Account Balance ($)")
    ax.legend(loc='upper left', fontsize=12)
    ax.grid(color='white', alpha=0.1)
    
    # Add stats table to the plot
    col_labels = ['Total Return', 'Max Drawdown', 'Max Days Flat', 'Calmar Ratio Proxy']
    row_labels = ['V1 (Base)', 'V2 (Engine 1)', 'V3 (Multi-Engine)']
    table_vals = [
        [f"{s1[0]:.1f}%", f"{s1[1]:.1f}%", f"{s1[2]:.0f} days", f"{s1[3]:.2f}"],
        [f"{s2[0]:.1f}%", f"{s2[1]:.1f}%", f"{s2[2]:.0f} days", f"{s2[3]:.2f}"],
        [f"{s3[0]:.1f}%", f"{s3[1]:.1f}%", f"{s3[2]:.0f} days", f"{s3[3]:.2f}"]
    ]
    
    table = plt.table(cellText=table_vals, rowLabels=row_labels, colLabels=col_labels, 
                      loc='lower center', cellLoc='center', bbox=[0.1, -0.3, 0.8, 0.2])
    table.set_fontsize(12)
    table.scale(1, 1.5)
    for key, cell in table.get_celld().items():
        cell.set_facecolor('black')
        cell.set_text_props(color='white')
    
    plt.subplots_adjust(bottom=0.3)
    plt.savefig("equity_curve_comparison.png", dpi=300, bbox_inches='tight')
    print("Saved equity_curve_comparison.png")

if __name__ == '__main__':
    main()
