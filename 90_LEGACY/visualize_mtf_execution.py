import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

def load_1m_data(year_month):
    file_path = f"D:/work/AI-Trade/Data/BTCUSD_1m/BTCUSD_OHLC_{year_month}.csv"
    if not os.path.exists(file_path):
        return None
    df = pd.read_csv(file_path)
    df.columns = [c.strip() for c in df.columns]
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df.set_index('DateTime', inplace=True)
    df.sort_index(inplace=True)
    return df

def calculate_mtf_bb(df, direction='long'):
    """Calculate MTF BB directly on 1m data"""
    df['BB_1m_SMA'] = df['close'].rolling(20).mean()
    df['BB_1m_STD'] = df['close'].rolling(20).std()
    
    df['BB_5m_SMA'] = df['close'].rolling(100).mean()
    df['BB_5m_STD'] = df['close'].rolling(100).std()
    
    df['BB_15m_SMA'] = df['close'].rolling(300).mean()
    df['BB_15m_STD'] = df['close'].rolling(300).std()
    
    df['BB_1h_SMA'] = df['close'].rolling(1200).mean()
    df['BB_1h_STD'] = df['close'].rolling(1200).std()
    
    if direction == 'long':
        df['BB_1m_L'] = df['BB_1m_SMA'] - 2.0 * df['BB_1m_STD']
        df['BB_5m_L'] = df['BB_5m_SMA'] - 2.0 * df['BB_5m_STD']
        df['BB_15m_L'] = df['BB_15m_SMA'] - 2.0 * df['BB_15m_STD']
        df['BB_1h_L'] = df['BB_1h_SMA'] - 2.0 * df['BB_1h_STD']
    else:
        df['BB_1m_U'] = df['BB_1m_SMA'] + 2.0 * df['BB_1m_STD']
        df['BB_5m_U'] = df['BB_5m_SMA'] + 2.0 * df['BB_5m_STD']
        df['BB_15m_U'] = df['BB_15m_SMA'] + 2.0 * df['BB_15m_STD']
        df['BB_1h_U'] = df['BB_1h_SMA'] + 2.0 * df['BB_1h_STD']
        
    return df

def find_next_extreme(df_window, direction='long'):
    if direction == 'long':
        first_touch_idx = df_window['low'].idxmin()
        first_touch_val = df_window.loc[first_touch_idx, 'low']
        
        after_touch = df_window[df_window.index > first_touch_idx]
        
        next_extreme_idx = None
        for i in range(1, len(after_touch)):
            idx = after_touch.index[i]
            row = after_touch.loc[idx]
            if row['low'] <= row['BB_1m_L'] or row['low'] <= row['BB_5m_L']:
                bounce_max = after_touch.loc[:idx, 'high'].max()
                if bounce_max > first_touch_val * 1.002: # at least 0.2% bounce
                    if row['low'] > first_touch_val: # Higher Low!
                        next_extreme_idx = idx
                        break
        return first_touch_idx, first_touch_val, next_extreme_idx
    else:
        first_touch_idx = df_window['high'].idxmax()
        first_touch_val = df_window.loc[first_touch_idx, 'high']
        after_touch = df_window[df_window.index > first_touch_idx]
        next_extreme_idx = None
        for i in range(1, len(after_touch)):
            idx = after_touch.index[i]
            row = after_touch.loc[idx]
            if row['high'] >= row['BB_1m_U'] or row['high'] >= row['BB_5m_U']:
                bounce_min = after_touch.loc[:idx, 'low'].min()
                if bounce_min < first_touch_val * 0.998:
                    if row['high'] < first_touch_val: # Lower High!
                        next_extreme_idx = idx
                        break
        return first_touch_idx, first_touch_val, next_extreme_idx

def visualize_mtf():
    print("Loading 2025-02 data...")
    df = load_1m_data('202502')
    df = calculate_mtf_bb(df, direction='long')
    
    target_date = '2025-02-03'
    window = df[(df.index >= f"{target_date} 07:00:00") & (df.index <= f"{target_date} 12:00:00")]
    
    ft_idx, ft_val, ne_idx = find_next_extreme(window, direction='long')
    
    plt.figure(figsize=(16, 8))
    plt.plot(window.index, window['close'], label='1m Close', color='black', linewidth=1.5)
    
    plt.plot(window.index, window['BB_1m_L'], label='1m BB_L (20)', color='blue', linestyle=':', alpha=0.6)
    plt.plot(window.index, window['BB_5m_L'], label='5m BB_L (100)', color='green', linestyle='--', alpha=0.6)
    plt.plot(window.index, window['BB_15m_L'], label='15m BB_L (300)', color='purple', linestyle='-.', alpha=0.8)
    plt.plot(window.index, window['BB_1h_L'], label='1h BB_L (1200)', color='red', linewidth=2.5, alpha=0.9)
    
    plt.scatter([ft_idx], [ft_val], color='red', s=200, zorder=5, label='First Touch (Absolute Bottom)')
    if ne_idx is not None:
        plt.scatter([ne_idx], [window.loc[ne_idx, 'close']], color='lime', s=200, zorder=5, label='Next Extreme (Higher Low / Entry)')
        
    plt.axvline(x=pd.to_datetime('2025-02-03 10:00:00'), color='grey', linestyle='--', label='1h Signal Point (Old Baseline Entry)')
    
    plt.title('MTF Fractal Execution (God\'s Eye View) - Trade 3 (LONG)', fontsize=16)
    plt.legend(loc='best')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('mtf_fractal_long.png', dpi=300)
    print(f"Saved mtf_fractal_long.png. Next Extreme at {ne_idx}")

    print("Loading 2025-01 data...")
    df_jan = load_1m_data('202501')
    df_jan = calculate_mtf_bb(df_jan, direction='short')
    target_date2 = '2025-01-19'
    window2 = df_jan[(df_jan.index >= f"{target_date2} 04:00:00") & (df_jan.index <= f"{target_date2} 09:00:00")]
    
    ft_idx2, ft_val2, ne_idx2 = find_next_extreme(window2, direction='short')
    
    plt.figure(figsize=(16, 8))
    plt.plot(window2.index, window2['close'], label='1m Close', color='black', linewidth=1.5)
    
    plt.plot(window2.index, window2['BB_1m_U'], label='1m BB_U (20)', color='blue', linestyle=':', alpha=0.6)
    plt.plot(window2.index, window2['BB_5m_U'], label='5m BB_U (100)', color='green', linestyle='--', alpha=0.6)
    plt.plot(window2.index, window2['BB_15m_U'], label='15m BB_U (300)', color='purple', linestyle='-.', alpha=0.8)
    plt.plot(window2.index, window2['BB_1h_U'], label='1h BB_U (1200)', color='red', linewidth=2.5, alpha=0.9)
    
    plt.scatter([ft_idx2], [ft_val2], color='red', s=200, zorder=5, label='First Touch (Absolute Top)')
    if ne_idx2 is not None:
        plt.scatter([ne_idx2], [window2.loc[ne_idx2, 'close']], color='lime', s=200, zorder=5, label='Next Extreme (Lower High / Entry)')
        
    plt.axvline(x=pd.to_datetime('2025-01-19 07:00:00'), color='grey', linestyle='--', label='1h Signal Point (Old Baseline Entry)')
    
    plt.title('MTF Fractal Execution (God\'s Eye View) - Trade 2 (SHORT)', fontsize=16)
    plt.legend(loc='best')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('mtf_fractal_short.png', dpi=300)
    print(f"Saved mtf_fractal_short.png. Next Extreme at {ne_idx2}")

if __name__ == "__main__":
    visualize_mtf()
