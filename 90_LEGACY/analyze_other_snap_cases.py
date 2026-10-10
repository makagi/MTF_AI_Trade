import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
from tqdm import tqdm
import warnings
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

def plot_snap_case(df, target_date, filename, title_prefix, mfe, mae):
    start_date = target_date - pd.Timedelta(hours=48)
    end_date = target_date + pd.Timedelta(hours=96)
    zoom_df = df.loc[start_date:end_date]
    
    pre_trigger = zoom_df.loc[:target_date - pd.Timedelta(hours=2)]
    abs_low_idx = pre_trigger['low'].idxmin()
    abs_low_val = pre_trigger.loc[abs_low_idx, 'low']
    
    between = zoom_df.loc[abs_low_idx + pd.Timedelta(hours=1) : target_date]
    if len(between) > 0:
        higher_low_idx = between['low'].idxmin()
        higher_low_val = between.loc[higher_low_idx, 'low']
    else:
        higher_low_idx = abs_low_idx
        higher_low_val = abs_low_val
    
    plt.figure(figsize=(16, 9))
    plt.fill_between(zoom_df.index, zoom_df['FIB_9_SMA'], zoom_df['FIB_10_SMA'], color='pink', alpha=0.15)
    plt.fill_between(zoom_df.index, zoom_df['FIB_10_SMA'], zoom_df['FIB_11_SMA'], color='red', alpha=0.15)
    
    plt.plot(zoom_df.index, zoom_df['FIB_5_SMA'], label='Micro (8)', color='cyan', linestyle=':')
    plt.plot(zoom_df.index, zoom_df['FIB_7_SMA'], label='Short (21)', color='lime', linestyle='--')
    plt.plot(zoom_df.index, zoom_df['FIB_9_SMA'], label='Tension (55)', color='orange', linewidth=2)
    plt.plot(zoom_df.index, zoom_df['FIB_10_SMA'], label='Sub-Anchor (89)', color='purple', linewidth=2)
    plt.plot(zoom_df.index, zoom_df['FIB_11_SMA'], label='Anchor (144)', color='red', linewidth=2)
    plt.plot(zoom_df.index, zoom_df['FIB_13_SMA'], label='Magnet (377)', color='magenta', linewidth=3)
    plt.plot(zoom_df.index, zoom_df['close'], label='Close Price', color='white', linewidth=2)
    
    plt.scatter(abs_low_idx, abs_low_val, color='red', s=200, zorder=5)
    plt.scatter(higher_low_idx, higher_low_val, color='green', s=200, zorder=5)
    
    if abs_low_idx != higher_low_idx:
        plt.plot([abs_low_idx, higher_low_idx], [abs_low_val, higher_low_val], color='green', linewidth=3, linestyle='-.', zorder=4)
        
    plt.scatter(target_date, zoom_df.loc[target_date, 'close'] - zoom_df.loc[target_date, 'ATR_14'], 
                color='yellow', s=300, marker='^', zorder=5)
                
    title_str = f"{title_prefix}\nDate: {target_date.strftime('%Y-%m-%d %H:%M')}"
    plt.title(title_str, fontsize=18)
    
    stats_text = (
        f"--- Event Stats ---\n"
        f"MFE (72h): {mfe:.2f} ATR\n"
        f"MAE (72h): {mae:.2f} ATR"
    )
    props = dict(boxstyle='round', facecolor='black', alpha=0.8, edgecolor='white')
    plt.gca().text(0.02, 0.95, stats_text, transform=plt.gca().transAxes, fontsize=14,
            verticalalignment='top', bbox=props, color='yellow', weight='bold')
    
    plt.legend(loc='lower left', frameon=True, facecolor='black', edgecolor='white', labelcolor='white')
    plt.grid(True, alpha=0.2)
    plt.gca().set_facecolor('black')
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    print(f"Saved {filename}")
    plt.close()

def main():
    print("Loading 1h Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, 14)
    
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift())
    df['tr2'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['ATR_14'] = df['tr'].rolling(14).mean()
    
    sma_8 = df['FIB_5_SMA']
    sma_21 = df['FIB_7_SMA']
    sma_55 = df['FIB_9_SMA']
    sma_89 = df['FIB_10_SMA']
    sma_144 = df['FIB_11_SMA']
    sma_377 = df['FIB_13_SMA']
    
    cond_wall = (sma_377 > sma_144) & (sma_144 > sma_89) & (sma_89 > sma_55)
    abs_low_24h = df['low'].rolling(24).min()
    local_low_4h = df['low'].rolling(4).min()
    cond_hl = (local_low_4h > abs_low_24h) & (local_low_4h < abs_low_24h + (1.0 * df['ATR_14']))
    
    score = np.zeros(len(df))
    score += (sma_8 > sma_21).astype(int)
    score += (df['close'] > sma_55).astype(int)
    score += (sma_21 > sma_55).astype(int)
    cond_prop = (score == 3) & (pd.Series(score).shift(1) < 3)
    
    cond_void = ((sma_377 - sma_144) / df['close']) > 0.02
    cond_afs_relaxed = (df['AFS_7_14'] > df['AFS_9_14']).rolling(3).max() > 0
    
    ultimate_trigger = cond_wall & cond_hl & cond_afs_relaxed & cond_prop & cond_void
    trigger_indices = df[ultimate_trigger == True].index
    print(f"Found {len(trigger_indices)} relaxed cases.")
    
    results = []
    for t_idx in trigger_indices:
        t_loc = df.index.get_loc(t_idx)
        if t_loc + 72 >= len(df): continue
        forward_highs = df.iloc[t_loc+1 : t_loc+72]['high']
        forward_lows = df.iloc[t_loc+1 : t_loc+72]['low']
        entry_price = df.iloc[t_loc]['close']
        atr = df.iloc[t_loc]['ATR_14']
        
        mfe = (forward_highs.max() - entry_price) / atr
        mae = (entry_price - forward_lows.min()) / atr
        results.append({'Date': t_idx, 'MFE': mfe, 'MAE': mae})
        
    res_df = pd.DataFrame(results).sort_values('MFE', ascending=False)
    
    if len(res_df) > 0:
        print("\nAll 14 Cases:")
        print(res_df.to_string())
        
        # Best Case was already plotted, but we can plot it again or just skip.
        
        # Case A: The Dud (Lowest MFE)
        dud = res_df.iloc[-1]
        plot_snap_case(df, dud['Date'], 'snap_case_a_dud.png', 'Case A: The Dud (Lowest MFE)', dud['MFE'], dud['MAE'])
        
        # Case B: The Struggle (Highest MAE)
        struggle = res_df.sort_values('MAE', ascending=False).iloc[0]
        plot_snap_case(df, struggle['Date'], 'snap_case_b_struggle.png', 'Case B: The Struggle (Highest MAE)', struggle['MFE'], struggle['MAE'])
        
        # Case C: The Median (Average MFE)
        median = res_df.iloc[len(res_df)//2]
        plot_snap_case(df, median['Date'], 'snap_case_c_median.png', 'Case C: The Average Joe (Median MFE)', median['MFE'], median['MAE'])

if __name__ == '__main__':
    main()
