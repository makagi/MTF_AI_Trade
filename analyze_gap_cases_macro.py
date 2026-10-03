import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
import glob
import warnings
warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features

def get_binary_barrier_labels(df: pd.DataFrame, pt_sl_ratio=[2.5, 1.0], time_barrier=72) -> pd.DataFrame:
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
        if row.low <= sl_price: break
        if row.high > max_price: max_price = row.high
    return (max_price - entry_price) / atr

def calculate_bb(series, period, std_dev=2.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, lower

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
    
    # Calculate MTF BBs manually since we need them
    df_1h['BB_21_Upper'], df_1h['BB_21_Lower'] = calculate_bb(df_1h['close'], 21, 2.0)
    df_1h['BB_144_Upper'], df_1h['BB_144_Lower'] = calculate_bb(df_1h['close'], 144, 2.0)
    
    # Squeeze Index for dashboard
    fib_periods = {7: 21, 9: 55, 11: 144, 13: 377}
    total_bb_width = 0
    for k, period in fib_periods.items():
        std = df_1h['close'].rolling(period).std()
        sma = df_1h[f'FIB_{k}_SMA']
        bb_width = (4 * std) / sma
        total_bb_width += bb_width
    
    roll_min = total_bb_width.rolling(720).min()
    roll_max = total_bb_width.rolling(720).max()
    df_1h['Squeeze_Index'] = (total_bb_width - roll_min) / (roll_max - roll_min + 1e-8) * 100
    
    # Gap 55 vs 144
    df_1h['SMA_55_144_Gap'] = (df_1h['FIB_9_SMA'] - df_1h['FIB_11_SMA']) / df_1h['close'] * 100
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025)
    oracle_1h_indices = labels[labels['tb_return'] == 1].index
    
    print("Loading 1m Data...")
    df_1m = load_all_1m_data_2025()
    df_1m['ATR_1h'] = df_1h_2025['ATR_14'].reindex(df_1m.index, method='ffill')
    df_1m['Trend_State_1h'] = df_1h_2025['Trend_State'].reindex(df_1m.index, method='ffill')
    
    rolling_high_30m = df_1m['high'].rolling('30min').max()
    panic_mask = (rolling_high_30m - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    armed_single = panic_mask.rolling('2h').max() > 0
    
    rolling_high_60m = df_1m['high'].rolling('60min').max()
    trend_dip_mask = (df_1m['Trend_State_1h'] > 1.5) & ((rolling_high_60m - df_1m['low']) >= (1.0 * df_1m['ATR_1h']))
    armed_trend = trend_dip_mask.rolling('1h').max() > 0
    df_1m['Armed_Dual'] = armed_single | armed_trend
    
    # Extract Cases exactly as before
    case1, case2, case3 = None, None, None
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
        mfe_atr = simulate_mfe(df_1m.loc[t_1m : t_1m + pd.Timedelta(hours=72)], entry_price, sl_price, atr)
        is_armed = df_1m.loc[t_1m, 'Armed_Dual']
        
        if not is_armed and mfe_atr > 5.0 and not case1: case1 = t_1h_floor
        if is_armed and mfe_atr > 8.0 and not case2: case2 = t_1h_floor
        if case1 and case2: break
            
    false_positive_1h = labels[labels['tb_return'] == -1].index
    for t_fp in false_positive_1h:
        window = df_1m.loc[t_fp : t_fp + pd.Timedelta(hours=1, minutes=59)]
        if len(window) == 0: continue
        armed_points = window[window['Armed_Dual'] == True]
        if len(armed_points) > 0:
            t_1m = armed_points['low'].idxmin()
            entry_price = armed_points.loc[t_1m, 'low']
            t_1h_floor = t_1m.floor('h')
            if t_1h_floor not in df_1h_2025.index: continue
            atr = df_1h_2025.loc[t_1h_floor, 'ATR_14']
            if pd.isna(atr): continue
            
            sl_price = entry_price - 1.0 * atr
            tp_price = entry_price + 2.5 * atr
            hit_sl = False
            for row in df_1m.loc[t_1m : t_1m + pd.Timedelta(hours=72)].itertuples():
                if row.low <= sl_price: hit_sl = True; break
                if row.high >= tp_price: break
            
            if hit_sl:
                case3 = t_1h_floor
                break

    def plot_macro_case(t_1h_event, case_num, title):
        if not t_1h_event: return
        start_t = t_1h_event - pd.Timedelta(days=5)
        end_t = t_1h_event + pd.Timedelta(days=2)
        df_plot = df_1h_2025.loc[start_t:end_t].copy()
        if len(df_plot) < 20: return
        
        ap_dict = [
            mpf.make_addplot(df_plot['FIB_9_SMA'], color='blue', width=1.5), # 55
            mpf.make_addplot(df_plot['FIB_11_SMA'], color='orange', width=2), # 144
            mpf.make_addplot(df_plot['FIB_13_SMA'], color='red', width=2.5, linestyle='--'), # 377
            mpf.make_addplot(df_plot['BB_21_Upper'], color='gray', alpha=0.5, linestyle=':'),
            mpf.make_addplot(df_plot['BB_21_Lower'], color='gray', alpha=0.5, linestyle=':'),
            mpf.make_addplot(df_plot['BB_144_Upper'], color='purple', alpha=0.3, width=2),
            mpf.make_addplot(df_plot['BB_144_Lower'], color='purple', alpha=0.3, width=2)
        ]
        
        # Mark event
        event_series = pd.Series(index=df_plot.index, data=np.nan)
        event_series.loc[t_1h_event] = df_plot.loc[t_1h_event, 'low'] - df_plot.loc[t_1h_event, 'ATR_14']
        ap_dict.append(mpf.make_addplot(event_series, type='scatter', markersize=300, marker='^', color='magenta'))
        
        # Features Snapshot
        row = df_plot.loc[t_1h_event]
        stats = (f"Macro Snapshot @ Event:\n"
                 f"AFS_21:  {row['AFS_7_19']:.1f}\n"
                 f"AFS_55:  {row['AFS_9_19']:.1f}\n"
                 f"AFS_144: {row['AFS_11_19']:.1f}\n"
                 f"AFS_377: {row['AFS_13_19']:.1f}\n"
                 f"Squeeze: {row['Squeeze_Index']:.1f}%\n"
                 f"55-144 Gap: {row['SMA_55_144_Gap']:.2f}%")
                 
        fig, axes = mpf.plot(df_plot, type='candle', style='yahoo', addplot=ap_dict,
                             title=title, figsize=(14, 8), returnfig=True)
                             
        props = dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='black')
        axes[0].text(0.02, 0.95, stats, transform=axes[0].transAxes, fontsize=11,
                     verticalalignment='top', bbox=props, family='monospace')
                     
        # Legends
        axes[0].text(0.02, 0.05, "Blue: 55 SMA | Orange: 144 SMA | Red(Dash): 377 SMA\nGray(Dot): 21 BB | Purple: 144 BB",
                     transform=axes[0].transAxes, fontsize=10, bbox=dict(facecolor='white', alpha=0.7))
                     
        fig.savefig(f'macro_case_{case_num}.png', dpi=300)
        print(f"Saved macro_case_{case_num}.png")

    print("Plotting Macro Case 1...")
    plot_macro_case(case1, 1, "Case 1 Macro (Filter Gap): S/R Range & BB Bounce")
    print("Plotting Macro Case 2...")
    plot_macro_case(case2, 2, "Case 2 Macro (Exit Gap): SMA Trend Reversal / Golden Cross")
    print("Plotting Macro Case 3...")
    plot_macro_case(case3, 3, "Case 3 Macro (Failed Entry): Support Breakdown")

if __name__ == '__main__':
    main()
