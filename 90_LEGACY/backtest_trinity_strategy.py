import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
from matplotlib.colors import ListedColormap

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def calculate_atr(df, p=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(p).mean()
    return df

def get_fib_periods():
    return [21, 34, 55, 89, 144, 233, 377, 610, 987, 1597]

def calculate_trinity_features(df, periods):
    for p in periods:
        # 1. Volatility (Bandwidth)
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'BW_{p}'] = (upper - lower) / df['close']
        
        # 2. Momentum (AFS)
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
        
        # 3. Phase
        pctb = (df['close'] - lower) / (upper - lower + 1e-8)
        slope = (sma - sma.shift(p)) / sma.shift(p) * 100
        avg_pctb = pctb.rolling(p).mean()
        
        phase = np.zeros(len(df))
        uptrend = (slope > 0.5) & (avg_pctb > 0.5)
        downtrend = (slope < -0.5) & (avg_pctb < 0.5)
        
        phase[uptrend] = 1
        phase[downtrend] = -1
        phase[:p*2] = np.nan 
        
        df[f'PHASE_{p}'] = phase
        
    return df

def plot_trinity_case(df, periods, start, end, title, filename):
    zoom = df.loc[start:end]
    zoom_resampled = zoom.resample('12h').median()
    
    fig, axes = plt.subplots(4, 1, figsize=(18, 24), sharex=False, gridspec_kw={'height_ratios': [3, 1, 1, 1]})
    
    # --- Price ---
    ax0 = axes[0]
    ax0.plot(zoom.index, zoom['close'], color='white')
    ax0.set_title(title, fontsize=16, color='white')
    ax0.set_facecolor('black')
    
    y_labels = periods.copy()
    y_labels.reverse()
    
    # --- Heatmap 1: AFS ---
    afs_cols = [f'AFS_{p}' for p in periods]
    afs_cols.reverse()
    sns.heatmap(zoom_resampled[afs_cols].T, cmap='coolwarm', ax=axes[1], cbar=False)
    axes[1].set_title("Momentum (AFS)", color='white')
    axes[1].set_yticklabels(y_labels, rotation=0, color='white')
    
    # --- Heatmap 2: Volatility ---
    bw_cols = [f'BW_{p}' for p in periods]
    bw_cols.reverse()
    bw_norm = zoom_resampled[bw_cols].T.apply(lambda r: (r - r.min()) / (r.max() - r.min() + 1e-8), axis=1)
    sns.heatmap(bw_norm, cmap='inferno', ax=axes[2], cbar=False)
    axes[2].set_title("Volatility (Bandwidth Squeeze=Black)", color='white')
    axes[2].set_yticklabels(y_labels, rotation=0, color='white')
    
    # --- Heatmap 3: Phase ---
    ph_cols = [f'PHASE_{p}' for p in periods]
    ph_cols.reverse()
    cmap_phase = ListedColormap(['#ff4444', '#888888', '#44ff44'])
    sns.heatmap(zoom_resampled[ph_cols].T, cmap=cmap_phase, ax=axes[3], cbar=False, vmin=-1, vmax=1)
    axes[3].set_title("Trend Phase (Green=Up, Gray=Range, Red=Down)", color='white')
    axes[3].set_yticklabels(y_labels, rotation=0, color='white')
    
    for ax in axes[1:]:
        ax.set_xticks([])
    
    fig.patch.set_facecolor('#111111')
    plt.tight_layout()
    plt.savefig(filename, dpi=200, facecolor=fig.get_facecolor())
    plt.close()

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    
    periods = get_fib_periods()
    print("Calculating Trinity Features...")
    df = calculate_trinity_features(df, periods)
    
    print("Running Backtest...")
    # The Early Spark Logic
    # 1. Macro Volatility Compression (lowest 40% over last 30 days)
    bw144_q = df['BW_144'].rolling(720).quantile(0.4)
    cond_macro_vol = (df['BW_144'] < bw144_q)
    
    # 2. Macro Phase is Resting or Downtrend (<= 0)
    cond_macro_phase = (df['PHASE_144'] <= 0)
    
    # 3. Micro Momentum Spark (Short AFS > Long AFS)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55'])
    
    # 4. Micro Phase Ignition (Just turned to 1)
    cond_micro_phase = (df['PHASE_21'] == 1) & (df['PHASE_21'].shift(1) <= 0)
    
    # Buy Signal
    print(f"Cond Macro Vol: {cond_macro_vol.sum()}")
    print(f"Cond Macro Phase: {cond_macro_phase.sum()}")
    print(f"Cond Micro Mom: {cond_micro_mom.sum()}")
    print(f"Cond Micro Phase: {cond_micro_phase.sum()}")
    
    buy_signals = df[cond_macro_vol & cond_macro_phase & cond_micro_mom & cond_micro_phase].index
    
    trades = []
    in_trade = False
    entry_idx = None
    entry_price = 0
    sl_price = 0
    atr = 0
    
    for i in range(len(df)):
        idx = df.index[i]
        row = df.iloc[i]
        
        if not in_trade:
            if idx in buy_signals:
                in_trade = True
                entry_idx = idx
                entry_price = row['close']
                atr = row['ATR']
                sl_price = entry_price - (atr * 1.5) # Hard stop just in case
        else:
            # Check Stop Loss
            if row['low'] < sl_price:
                trades.append({'entry': entry_idx, 'exit': idx, 'pnl': sl_price - entry_price, 'atr_pnl': (sl_price - entry_price)/atr, 'reason': 'SL'})
                in_trade = False
            # Dynamic Exit: Micro Phase turns Red (-1)
            elif row['PHASE_21'] == -1:
                exit_price = row['close']
                trades.append({'entry': entry_idx, 'exit': idx, 'pnl': exit_price - entry_price, 'atr_pnl': (exit_price - entry_price)/atr, 'reason': 'Dynamic'})
                in_trade = False

    trades_df = pd.DataFrame(trades)
    if len(trades_df) == 0:
        print("No trades found.")
        return
        
    print(f"Total Trades: {len(trades_df)}")
    success = trades_df[trades_df['atr_pnl'] >= 1.0]
    failure = trades_df[trades_df['atr_pnl'] < -0.5]
    print(f"Success (>1 ATR): {len(success)}")
    print(f"Failure (<-0.5 ATR): {len(failure)}")
    
    # Find Missed (Price moved > 4 ATR in 24h, but no trade open)
    df['Fwd_Max'] = df['high'].rolling(24).max().shift(-24)
    df['Move_ATR'] = (df['Fwd_Max'] - df['close']) / df['ATR']
    # Exclude periods where we were in a trade
    in_trade_mask = np.zeros(len(df), dtype=bool)
    for t in trades:
        in_trade_mask[df.index.get_loc(t['entry']) : df.index.get_loc(t['exit'])] = True
        
    missed_mask = (df['Move_ATR'] > 4) & (~in_trade_mask)
    missed_events = df[missed_mask]
    print(f"Missed Massive Moves (>4 ATR): {len(missed_events)}")
    
    # Plot one of each
    if len(success) > 0:
        best = success.sort_values('atr_pnl', ascending=False).iloc[0]
        start = best['entry'] - pd.Timedelta(days=15)
        end = best['exit'] + pd.Timedelta(days=5)
        plot_trinity_case(df, periods, start, end, f"SUCCESS CASE (+{best['atr_pnl']:.1f} ATR)", "trinity_case_success.png")
        
    if len(failure) > 0:
        worst = failure.sort_values('atr_pnl', ascending=True).iloc[0]
        start = worst['entry'] - pd.Timedelta(days=15)
        end = worst['exit'] + pd.Timedelta(days=5)
        plot_trinity_case(df, periods, start, end, f"FAILURE CASE ({worst['atr_pnl']:.1f} ATR)\nNotice Macro Momentum was strongly Red", "trinity_case_failure.png")
        
    if len(missed_events) > 0:
        missed = missed_events.iloc[len(missed_events)//2]
        start = missed.name - pd.Timedelta(days=15)
        end = missed.name + pd.Timedelta(days=5)
        plot_trinity_case(df, periods, start, end, f"MISSED CASE (Meteor Strike)\nNotice there was no Volatility Compression (Black) beforehand", "trinity_case_missed.png")

if __name__ == '__main__':
    main()
