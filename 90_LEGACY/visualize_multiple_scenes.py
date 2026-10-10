import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
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

def plot_scene(df_plot, scene, title, filename):
    mc = mpf.make_marketcolors(up='g', down='r', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')
    
    fig, axlist = mpf.plot(df_plot, type='candle', style=s, returnfig=True, figsize=(16, 9), title=title)
    ax = axlist[0]
    
    def get_x_idx(t):
        if t in df_plot.index: return df_plot.index.get_loc(t)
        return None
        
    x_trigger = get_x_idx(scene['t_trigger'])
    x_bottom = get_x_idx(scene['t_bottom'])
    x_next_hour = get_x_idx(scene['t_next_hour'])
    
    # Peak and Trigger Lines
    ax.axhline(scene['peak_price'], color='black', linestyle='-', linewidth=1, label='Local Peak')
    ax.axhline(scene['trigger_price'], color='red', linestyle='--', linewidth=2, label='Alert Line (-1.5 ATR)')
    
    # Armed Window
    x_trigger_end = get_x_idx(min(scene['t_trigger'] + pd.Timedelta(hours=4), df_plot.index[-1]))
    if x_trigger is not None and x_trigger_end is not None:
        rect = patches.Rectangle((x_trigger, ax.get_ylim()[0]), 
                                 width=(x_trigger_end - x_trigger), 
                                 height=(ax.get_ylim()[1] - ax.get_ylim()[0]), 
                                 linewidth=0, facecolor='yellow', alpha=0.2)
        ax.add_patch(rect)
        ax.plot(x_trigger, scene['trigger_price'], marker='v', color='red', markersize=15)
        
    # Oracle Bottom
    if x_bottom is not None:
        ax.plot(x_bottom, scene['bottom_price'] - 100, marker='*', color='green', markersize=25, label='Oracle Captured')
        
    # Old Logic (Top of the next hour after bottom)
    if x_next_hour is not None:
        ax.axvline(x=x_next_hour, color='gray', linestyle=':', linewidth=1)
        ax.plot(x_next_hour, scene['rebound_price'] + 100, marker='X', color='red', markersize=20, label='Old Logic Evaluates')
        
    for t in df_plot.index:
        if t.minute == 0:
            x_t = get_x_idx(t)
            if x_t is not None:
                ax.axvline(x=x_t, color='gray', linestyle=':', linewidth=0.5, alpha=0.5)
                
    # Text box with stats
    stats_text = (f"Time to Oracle: {scene['time_to_oracle']:.0f} mins\n"
                  f"Max Drawdown: -{scene['max_drop_atr']:.2f} ATR\n"
                  f"Old Logic Penalty: Missed by +{scene['penalty_atr']:.2f} ATR")
    props = dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='black')
    ax.text(0.02, 0.05, stats_text, transform=ax.transAxes, fontsize=12, verticalalignment='bottom', bbox=props)
    
    ax.legend(loc='upper right')
    plt.tight_layout()
    fig.savefig(filename, dpi=300)
    print(f"Saved {filename}")

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
    case1 = None # V-shape (time_to_oracle < 30)
    case2 = None # U-shape (time_to_oracle > 120)
    case3 = None # W-shape (first bottom, bounce, lower bottom)
    
    print("Searching for diverse scenes...")
    for t_oracle in tqdm(oracle_1h_indices):
        if case1 and case2 and case3: break
            
        t_start_1m = t_oracle - pd.Timedelta(hours=1)
        t_end_1m = t_oracle + pd.Timedelta(hours=2)
        window_1m = df_1m.loc[t_start_1m:t_end_1m]
        if len(window_1m) == 0: continue
            
        true_bottom_idx = window_1m['low'].idxmin()
        true_bottom_price = window_1m.loc[true_bottom_idx, 'low']
        
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
        time_to_oracle = (true_bottom_idx - t_trigger).total_seconds() / 60.0
        
        t_next_hour = (true_bottom_idx + pd.Timedelta(hours=1)).floor('h')
        if t_next_hour not in df_1m.index: continue
        price_at_next_hour = df_1m.loc[t_next_hour, 'close']
        
        penalty_atr = (price_at_next_hour - true_bottom_price) / atr
        max_drop_atr = (peak_price - true_bottom_price) / atr
        
        scene_data = {
            't_oracle_1h': t_oracle,
            't_trigger': t_trigger,
            't_bottom': true_bottom_idx,
            't_next_hour': t_next_hour,
            'peak_price': peak_price,
            'trigger_price': trigger_price,
            'bottom_price': true_bottom_price,
            'rebound_price': price_at_next_hour,
            'atr': atr,
            'time_to_oracle': time_to_oracle,
            'max_drop_atr': max_drop_atr,
            'penalty_atr': penalty_atr
        }
        
        if penalty_atr > 0.5: # Only want scenes where old logic is bad
            if not case1 and time_to_oracle < 30:
                case1 = scene_data
            elif not case2 and 120 < time_to_oracle < 240:
                case2 = scene_data
            elif not case3 and 60 < time_to_oracle < 180:
                # Check for W-shape: a bounce of at least 0.5 ATR between trigger and bottom
                mid_window = drop_window.loc[t_trigger:true_bottom_idx]
                if len(mid_window) > 0:
                    local_bounce_max = mid_window['high'].max()
                    local_bounce_min = mid_window['low'].min()
                    # It bounced up, then went lower
                    if (local_bounce_max - local_bounce_min) / atr > 0.8:
                        case3 = scene_data
                        
    # Plotting
    if case1:
        plot_start = case1['t_trigger'] - pd.Timedelta(hours=2)
        plot_end = case1['t_bottom'] + pd.Timedelta(hours=2)
        plot_scene(df_1m.loc[plot_start:plot_end], case1, "Case 1: Flash Crash (V-Shape)", 'case1_v_shape.png')
        
    if case2:
        plot_start = case2['t_trigger'] - pd.Timedelta(hours=1)
        plot_end = case2['t_bottom'] + pd.Timedelta(hours=2)
        plot_scene(df_1m.loc[plot_start:plot_end], case2, "Case 2: Slow Bleeding (U-Shape)", 'case2_u_shape.png')
        
    if case3:
        plot_start = case3['t_trigger'] - pd.Timedelta(hours=1)
        plot_end = case3['t_bottom'] + pd.Timedelta(hours=2)
        plot_scene(df_1m.loc[plot_start:plot_end], case3, "Case 3: Stop Hunt Trap (W-Shape)", 'case3_w_shape.png')

if __name__ == '__main__':
    main()
