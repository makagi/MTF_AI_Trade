import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import random

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def get_fib_periods():
    return [21, 55, 144, 233, 377, 610, 987, 1597]

def calculate_atr(df, p=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['ATR'] = np.max(ranges, axis=1).rolling(p).mean()
    return df

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        df[f'SMA_{p}'] = sma
        
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'BB_Lower_{p}'] = lower
        
        bw = (upper - lower) / df['close']
        df[f'BW_Pct_{p}'] = bw.rolling(720).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] if not pd.isna(x).any() else np.nan)
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
    return df

def simulate_v4_with_k(df, start_capital=10000):
    periods = get_fib_periods()
    trades = []
    risk_pct = 0.01
    
    crosses = {}
    for i in range(1, len(periods)):
        k_micro = periods[i-1]
        k_ignite = periods[i]
        crosses[k_ignite] = (df[f'AFS_{k_micro}'] > df[f'AFS_{k_ignite}']) & (df[f'AFS_{k_micro}'].shift(1) <= df[f'AFS_{k_ignite}'].shift(1))
    
    any_cross = pd.Series(False, index=df.index)
    for c in crosses.values():
        any_cross = any_cross | c
        
    cross_indices = df[any_cross].index
    
    for idx in cross_indices:
        loc = df.index.get_loc(idx)
        if loc < 720 or loc + 120 >= len(df):
            continue
            
        row = df.iloc[loc]
        bw_pcts = {p: row[f'BW_Pct_{p}'] for p in periods[1:-2]} # skip 21 and max macro
        
        if any(pd.isna(v) for v in bw_pcts.values()):
            continue
            
        k_ignite = min(bw_pcts, key=bw_pcts.get)
        min_bw_pct = bw_pcts[k_ignite]
        
        if min_bw_pct > 0.2: 
            continue
            
        if not crosses[k_ignite].iloc[loc]:
            continue
            
        k_ignite_idx = periods.index(k_ignite)
        k_target = periods[min(k_ignite_idx + 2, len(periods)-1)]
        
        entry_price = row['close']
        sl_price = row[f'BB_Lower_{k_ignite}']
        tp_price = row[f'SMA_{k_target}']
        
        if tp_price <= entry_price or sl_price >= entry_price:
            continue
            
        qty = (start_capital * risk_pct) / (entry_price - sl_price)
        
        window = df.iloc[loc+1 : loc+168] 
        exit_price = window['close'].iloc[-1]
        
        for i in range(len(window)):
            if window['low'].iloc[i] <= sl_price:
                exit_price = sl_price
                break
            if window['high'].iloc[i] >= tp_price:
                exit_price = tp_price
                break
                
        pnl = (exit_price - entry_price) * qty
        trades.append({
            'k_ignite': k_ignite,
            'pnl': pnl
        })
        
    return pd.DataFrame(trades)

def monte_carlo_simulation(trades_df, num_simulations=1000, start_capital=10000):
    pnls = trades_df['pnl'].values
    n_trades = len(pnls)
    
    simulated_equities = []
    max_drawdowns = []
    
    for _ in range(num_simulations):
        # Sample with replacement
        sim_pnls = np.random.choice(pnls, size=n_trades, replace=True)
        equity = start_capital + np.cumsum(sim_pnls)
        simulated_equities.append(equity)
        
        rolling_max = np.maximum.accumulate(equity)
        drawdown = (equity - rolling_max) / rolling_max * 100
        max_drawdowns.append(np.min(drawdown))
        
    return np.array(simulated_equities), np.array(max_drawdowns)

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    print("Running V4 Simulation...")
    start_cap = 10000
    trades_df = simulate_v4_with_k(df, start_cap)
    
    if len(trades_df) == 0:
        print("No trades generated.")
        return
        
    # --- Test A: Fractal Uniformity (Scale-Invariance Proof) ---
    grouped = trades_df.groupby('k_ignite')
    stats = []
    for k, group in grouped:
        win_rate = len(group[group['pnl'] > 0]) / len(group) * 100
        gross_profit = group[group['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(group[group['pnl'] < 0]['pnl'].sum())
        pf = gross_profit / gross_loss if gross_loss > 0 else np.nan
        stats.append({'k_ignite': k, 'Win Rate (%)': win_rate, 'Profit Factor': pf, 'Count': len(group)})
    
    stats_df = pd.DataFrame(stats).dropna().set_index('k_ignite')
    print("Stats per Ignition Layer:")
    print(stats_df)
    
    # --- Test B: Monte Carlo Validation ---
    print("Running Monte Carlo Simulations...")
    sim_equities, mdds = monte_carlo_simulation(trades_df, num_simulations=1000, start_capital=start_cap)
    
    # --- Plotting ---
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(16, 10))
    
    # Grid specification
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.2])
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    
    # Plot 1: Win Rate per Scale
    stats_df['Win Rate (%)'].plot(kind='bar', color='cyan', ax=ax1, edgecolor='white')
    ax1.set_title("Fractal Uniformity: Win Rate per Scale (Ignition Layer)", fontsize=14, color='white')
    ax1.set_ylabel("Win Rate (%)")
    ax1.axhline(stats_df['Win Rate (%)'].mean(), color='yellow', linestyle='--', label='Mean Win Rate')
    ax1.legend()
    
    # Plot 2: Profit Factor per Scale
    stats_df['Profit Factor'].plot(kind='bar', color='magenta', ax=ax2, edgecolor='white')
    ax2.set_title("Fractal Uniformity: Profit Factor per Scale", fontsize=14, color='white')
    ax2.set_ylabel("Profit Factor")
    ax2.axhline(stats_df['Profit Factor'].mean(), color='yellow', linestyle='--', label='Mean PF')
    ax2.legend()
    
    # Plot 3: Monte Carlo Spaghetti & MDD
    # Plot a subset of 100 paths for visual clarity
    for eq in sim_equities[:100]:
        ax3.plot(eq, color='lime', alpha=0.1)
    
    # Plot the Original Equity
    original_eq = start_cap + np.cumsum(trades_df['pnl'].values)
    ax3.plot(original_eq, color='white', linewidth=3, label='Original V4 Equity Curve')
    
    ax3.set_title(f"Monte Carlo Validation (1,000 Shuffles, N={len(trades_df)} trades)\n"
                  f"Worst Case MDD (99th Pct): {np.percentile(mdds, 1):.1f}% | Median MDD: {np.median(mdds):.1f}%", 
                  fontsize=14, color='white')
    ax3.set_ylabel("Account Balance ($)")
    ax3.set_xlabel("Trade Number")
    ax3.legend()
    
    plt.tight_layout()
    plt.savefig("final_robustness_evaluation.png", dpi=300)
    print("Saved final_robustness_evaluation.png")

if __name__ == '__main__':
    main()
