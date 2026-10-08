import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
import glob
import os
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

def simulate_mfe(window, entry_price, sl_price, atr):
    max_price = entry_price
    for row in window.itertuples():
        if row.low <= sl_price:
            break
        if row.high > max_price:
            max_price = row.high
    return (max_price - entry_price) / atr

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
    df_1h['Trend_State'] = (df_1h['FIB_11_SMA'] - df_1h['FIB_13_SMA']) / df_1h['close'] * 100
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025)
    
    print("Loading 1m Data...")
    df_1m = load_all_1m_data_2025()
    df_1m['ATR_1h'] = df_1h_2025['ATR_14'].reindex(df_1m.index, method='ffill')
    df_1m['Trend_State_1h'] = df_1h_2025['Trend_State'].reindex(df_1m.index, method='ffill')
    
    print("Calculating Dual Trigger...")
    rolling_high_30m = df_1m['high'].rolling('30min').max()
    panic_mask = (rolling_high_30m - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    armed_single = panic_mask.rolling('2h').max() > 0
    
    rolling_high_60m = df_1m['high'].rolling('60min').max()
    trend_dip_mask = (df_1m['Trend_State_1h'] > 1.5) & ((rolling_high_60m - df_1m['low']) >= (1.0 * df_1m['ATR_1h']))
    armed_trend = trend_dip_mask.rolling('1h').max() > 0
    
    df_1m['Armed_Dual'] = armed_single | armed_trend
    
    print("Extracting Cases...")
    case1_candidate = None
    case2_candidate = None
    
    oracle_1h_indices = labels[labels['tb_return'] == 1].index
    
    for t_oracle in oracle_1h_indices:
        window = df_1m.loc[t_oracle - pd.Timedelta(hours=1) : t_oracle + pd.Timedelta(hours=1, minutes=59)]
        if len(window) == 0: continue
        t_1m = window['low'].idxmin()
        if t_1m not in df_1m.index: continue
        
        entry_price = df_1m.loc[t_1m, 'low']
        t_1h_floor = t_1m.floor('h')
        if t_1h_floor not in df_1h_2025.index: continue
        atr = df_1h_2025.loc[t_1h_floor, 'ATR_14']
        if pd.isna(atr): continue
            
        sl_price = entry_price - 1.0 * atr
        future_window = df_1m.loc[t_1m : t_1m + pd.Timedelta(hours=72)]
        mfe_atr = simulate_mfe(future_window, entry_price, sl_price, atr)
        
        is_armed = df_1m.loc[t_1m, 'Armed_Dual']
        
        if not is_armed and mfe_atr > 5.0 and case1_candidate is None:
            case1_candidate = (t_1m, entry_price, atr, mfe_atr)
            
        if is_armed and mfe_atr > 8.0 and case2_candidate is None:
            case2_candidate = (t_1m, entry_price, atr, mfe_atr)
            
        if case1_candidate and case2_candidate:
            break
            
    # Case 3: False Positive (Armed but hits SL before TP)
    case3_candidate = None
    # Find periods where Armed_Dual is True, but tb_return of the 1h block is -1
    false_positive_1h = labels[labels['tb_return'] == -1].index
    for t_fp in false_positive_1h:
        window = df_1m.loc[t_fp : t_fp + pd.Timedelta(hours=1, minutes=59)]
        if len(window) == 0: continue
        armed_points = window[window['Armed_Dual'] == True]
        if len(armed_points) > 0:
            # Assume entry at the lowest point while armed (best possible entry)
            t_1m = armed_points['low'].idxmin()
            entry_price = armed_points.loc[t_1m, 'low']
            t_1h_floor = t_1m.floor('h')
            if t_1h_floor not in df_1h_2025.index: continue
            atr = df_1h_2025.loc[t_1h_floor, 'ATR_14']
            if pd.isna(atr): continue
            
            sl_price = entry_price - 1.0 * atr
            tp_price = entry_price + 2.5 * atr
            
            future_window = df_1m.loc[t_1m : t_1m + pd.Timedelta(hours=72)]
            hit_sl = False
            for row in future_window.itertuples():
                if row.low <= sl_price:
                    hit_sl = True
                    break
                if row.high >= tp_price:
                    break
            
            if hit_sl:
                case3_candidate = (t_1m, entry_price, atr)
                break

    # Helper function to plot
    def plot_case(case_info, case_num, title, show_mfe=True):
        if not case_info: return
        t_1m, entry_price, atr = case_info[0], case_info[1], case_info[2]
        mfe_atr = case_info[3] if len(case_info) > 3 else None
        
        start_t = t_1m - pd.Timedelta(hours=3)
        end_t = t_1m + pd.Timedelta(hours=10) # 10 hours future to show the trend
        
        df_plot = df_1m.loc[start_t:end_t].copy()
        if len(df_plot) == 0: return
        
        # Calculate levels
        tp_price = entry_price + 2.5 * atr
        sl_price = entry_price - 1.0 * atr
        
        # Find MFE point within this plot window
        mfe_point = None
        if show_mfe and mfe_atr:
            mfe_abs_price = entry_price + mfe_atr * atr
            # Find the index where it hits the highest high before SL
            plot_future = df_plot.loc[t_1m:]
            max_idx = plot_future['high'].idxmax()
            mfe_point = (max_idx, plot_future.loc[max_idx, 'high'])

        ap_dict = []
        
        # Add Armed Background
        armed_series = df_plot['Armed_Dual'].astype(int) * df_plot['high'].max()
        armed_series[armed_series == 0] = np.nan
        if not armed_series.isna().all():
            ap_dict.append(mpf.make_addplot(armed_series, type='scatter', markersize=10, color='orange', alpha=0.1, marker='s'))
        
        # Entry Marker
        entry_series = pd.Series(index=df_plot.index, data=np.nan)
        entry_series.loc[t_1m] = entry_price - atr*0.5
        if not entry_series.isna().all():
            ap_dict.append(mpf.make_addplot(entry_series, type='scatter', markersize=200, marker='^', color='blue'))
        
        # MFE Marker
        if mfe_point:
            mfe_series = pd.Series(index=df_plot.index, data=np.nan)
            mfe_series.loc[mfe_point[0]] = mfe_point[1] + atr*0.5
            if not mfe_series.isna().all():
                ap_dict.append(mpf.make_addplot(mfe_series, type='scatter', markersize=300, marker='*', color='gold'))

        # Horizontal lines for TP and SL
        hlines = dict(hlines=[tp_price, sl_price], colors=['green', 'red'], linestyle='--', linewidths=[2,2])
        
        fig, axes = mpf.plot(df_plot, type='candle', style='yahoo', addplot=ap_dict, hlines=hlines,
                             title=title, figsize=(12, 8), returnfig=True)
                             
        # Fill between TP and SL for the "Battleground"
        ax = axes[0]
        # x-axis in mplfinance is 0 to N
        idx_t1m = df_plot.index.get_loc(t_1m)
        ax.fill_between(range(idx_t1m, len(df_plot)), sl_price, tp_price, color='gray', alpha=0.1)
        
        # Annotate
        ax.text(idx_t1m, entry_price - atr*0.8, 'Entry Point\n(Oracle)', color='blue', ha='center', fontweight='bold')
        ax.text(len(df_plot)-10, tp_price, 'TP (+2.5 ATR)', color='green', va='bottom', fontweight='bold')
        ax.text(len(df_plot)-10, sl_price, 'SL (-1.0 ATR)', color='red', va='top', fontweight='bold')
        
        if show_mfe and mfe_point:
            idx_mfe = df_plot.index.get_loc(mfe_point[0])
            ax.text(idx_mfe, mfe_point[1] + atr*0.8, f'MFE (+{mfe_atr:.1f} ATR)\nMissed Upside', color='goldenrod', ha='center', fontweight='bold')
            # Draw line from TP to MFE
            if mfe_point[1] > tp_price:
                ax.annotate('', xy=(idx_mfe, mfe_point[1]), xytext=(idx_mfe, tp_price),
                            arrowprops=dict(arrowstyle="->", color='goldenrod', lw=2, ls='--'))

        fig.savefig(f'gap_case_{case_num}.png', dpi=300)
        print(f"Saved gap_case_{case_num}.png")

    print("Plotting Case 1...")
    plot_case(case1_candidate, 1, "Case 1: Filter Gap (Missed Stealth Bottom)", show_mfe=True)
    
    print("Plotting Case 2...")
    plot_case(case2_candidate, 2, "Case 2: Exit Gap (The Chicken Exit)", show_mfe=True)
    
    print("Plotting Case 3...")
    plot_case(case3_candidate, 3, "Case 3: Failed Entry (The Falling Knife)", show_mfe=False)

if __name__ == '__main__':
    main()
