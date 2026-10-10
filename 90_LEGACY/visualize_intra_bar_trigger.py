import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as patches
import mplfinance as mpf
import glob
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
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
    print("Loading 1h data...")
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
    
    THRESHOLD_ATR = 1.5
    miracle_scene = None
    
    print("Searching for the perfect 'Miracle Scene'...")
    for t_oracle in tqdm(oracle_1h_indices):
        t_start_1m = t_oracle - pd.Timedelta(hours=1)
        t_end_1m = t_oracle + pd.Timedelta(hours=1) + pd.Timedelta(minutes=59)
        
        window_1m = df_1m.loc[t_start_1m:t_end_1m]
        if len(window_1m) == 0: continue
            
        true_bottom_idx = window_1m['low'].idxmin()
        true_bottom_price = window_1m.loc[true_bottom_idx, 'low']
        
        # We want bottoms that happened mid-hour
        if not (15 <= true_bottom_idx.minute <= 45):
            continue
            
        t_lookback_start = true_bottom_idx - pd.Timedelta(hours=12)
        lookback_window = df_1m.loc[t_lookback_start:true_bottom_idx]
        if len(lookback_window) == 0: continue
            
        peak_idx = lookback_window['high'].idxmax()
        peak_price = lookback_window.loc[peak_idx, 'high']
        
        try:
            atr = df_1h.loc[peak_idx.floor('h'), 'ATR_14']
        except KeyError:
            continue
            
        if pd.isna(atr) or atr == 0: continue
            
        trigger_price = peak_price - THRESHOLD_ATR * atr
        drop_window = df_1m.loc[peak_idx:true_bottom_idx]
        crosses = drop_window[drop_window['low'] <= trigger_price]
        if len(crosses) == 0: continue
            
        t_trigger = crosses.index[0]
        
        # Next top of the hour AFTER the true bottom (this is when the old logic wakes up)
        t_next_hour = (true_bottom_idx + pd.Timedelta(hours=1)).floor('h')
        
        if t_next_hour not in df_1m.index: continue
        price_at_next_hour = df_1m.loc[t_next_hour, 'close']
        
        # Condition: At the next hour (when old logic wakes up), the price has ALREADY rebounded by > 0.8 ATR
        rebound_atr = (price_at_next_hour - true_bottom_price) / atr
        
        if rebound_atr > 0.8:
            miracle_scene = {
                't_oracle_1h': t_oracle,
                't_trigger': t_trigger,
                't_bottom': true_bottom_idx,
                't_next_hour': t_next_hour,
                'peak_price': peak_price,
                'trigger_price': trigger_price,
                'bottom_price': true_bottom_price,
                'rebound_price': price_at_next_hour,
                'atr': atr
            }
            break
            
    if miracle_scene is None:
        print("No miracle scene found. Adjust conditions.")
        return
        
    print(f"Found Miracle Scene! Bottom at {miracle_scene['t_bottom']}")
    
    # Plotting
    # Window: 3 hours before trigger to 2 hours after bottom
    plot_start = miracle_scene['t_trigger'] - pd.Timedelta(hours=3)
    plot_end = miracle_scene['t_bottom'] + pd.Timedelta(hours=3)
    df_plot = df_1m.loc[plot_start:plot_end].copy()
    
    mc = mpf.make_marketcolors(up='g', down='r', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')
    
    fig, axlist = mpf.plot(df_plot, type='candle', style=s, returnfig=True, figsize=(16, 9), 
                           title=f"New Logic (Real-time Arming) vs Old Logic (1h Close) at {miracle_scene['t_bottom'].date()}")
    ax = axlist[0]
    
    # Calculate x-axis indices
    idx_start = 0
    idx_end = len(df_plot) - 1
    
    def get_x_idx(t):
        if t in df_plot.index:
            return df_plot.index.get_loc(t)
        return None
        
    x_trigger = get_x_idx(miracle_scene['t_trigger'])
    x_bottom = get_x_idx(miracle_scene['t_bottom'])
    x_next_hour = get_x_idx(miracle_scene['t_next_hour'])
    
    # 1. Peak line
    ax.axhline(miracle_scene['peak_price'], color='black', linestyle='-', linewidth=1, label='Local Peak')
    
    # 2. Trigger Line (-1.5 ATR)
    ax.axhline(miracle_scene['trigger_price'], color='red', linestyle='--', linewidth=2, label='Alert Line (-1.5 ATR)')
    
    # 3. Armed Mode Background (from trigger to +4 hours or plot end)
    x_trigger_end = get_x_idx(min(miracle_scene['t_trigger'] + pd.Timedelta(hours=4), plot_end))
    if x_trigger is not None and x_trigger_end is not None:
        rect = patches.Rectangle((x_trigger, ax.get_ylim()[0]), 
                                 width=(x_trigger_end - x_trigger), 
                                 height=(ax.get_ylim()[1] - ax.get_ylim()[0]), 
                                 linewidth=0, facecolor='yellow', alpha=0.2)
        ax.add_patch(rect)
        ax.text(x_trigger + 5, miracle_scene['peak_price'], "Armed Mode ON (4h)", color='olive', fontsize=12, weight='bold')
        ax.plot(x_trigger, miracle_scene['trigger_price'], marker='v', color='red', markersize=15)
        
    # 4. True Bottom (Oracle Captured)
    if x_bottom is not None:
        ax.plot(x_bottom, miracle_scene['bottom_price'] - 100, marker='*', color='green', markersize=25, label='Oracle Captured!')
        ax.text(x_bottom, miracle_scene['bottom_price'] - 200, "Oracle Captured!", color='green', fontsize=12, weight='bold', ha='center')
        
    # 5. Old Logic (Top of the hour)
    if x_next_hour is not None:
        ax.axvline(x=x_next_hour, color='gray', linestyle=':', linewidth=1)
        ax.plot(x_next_hour, miracle_scene['rebound_price'] + 100, marker='X', color='red', markersize=20, label='Old Logic Evaluates (Too Late!)')
        ax.text(x_next_hour, miracle_scene['rebound_price'] + 200, "Old Logic Evaluation\n(Too Late!)", color='red', fontsize=12, weight='bold', ha='center')
        
    # Mark all hour boundaries
    for t in df_plot.index:
        if t.minute == 0:
            x_t = get_x_idx(t)
            if x_t is not None:
                ax.axvline(x=x_t, color='gray', linestyle=':', linewidth=0.5, alpha=0.5)
                
    ax.legend(loc='upper left')
    plt.tight_layout()
    fig.savefig('concrete_scene_verification.png', dpi=300)
    print("Saved concrete_scene_verification.png")

if __name__ == '__main__':
    main()
