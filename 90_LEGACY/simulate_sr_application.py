import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

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

def calculate_bb(series, period, std_dev=2.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return sma + (std * std_dev), sma - (std * std_dev)

def calc_sandwich_ratio(levels, close, atr):
    ceilings = [l for l in levels if l > close]
    floors = [l for l in levels if l <= close]
    
    ceiling = min(ceilings) if ceilings else close + atr*5
    floor = max(floors) if floors else close - atr*5
    
    return (close - floor) / (ceiling - floor + 1e-8)

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

def plot_waterfall(values, labels, colors, title, ylabel, save_path):
    n = len(values)
    bottoms = [0] * n
    
    bottoms[0] = 0
    bottoms[1] = values[0]
    bottoms[2] = values[0] + values[1]
    bottoms[3] = 0
    
    fig, ax = plt.subplots(figsize=(10, 7))
    
    for i in range(n):
        if i == 0 or i == 3: # Total pillars
            ax.bar(labels[i], values[i], color=colors[i], edgecolor='black')
            ax.text(i, values[i]/2, f"{values[i]:.1f}", ha='center', va='center', color='white', fontweight='bold')
        else: # Gap steps (Positive additions)
            ax.bar(labels[i], values[i], bottom=bottoms[i], color=colors[i], edgecolor='black', hatch='//')
            ax.text(i, bottoms[i] + values[i]/2, f"+{values[i]:.1f}", ha='center', va='center', color='black', fontweight='bold')
    
    # Draw step lines
    ax.plot([0.5, 1.5], [bottoms[1], bottoms[1]], color='black', linewidth=1)
    ax.plot([1.5, 2.5], [bottoms[2], bottoms[2]], color='black', linewidth=1)
    ax.plot([2.5, 3.5], [values[3], values[3]], color='black', linewidth=1)
    
    plt.title(title, fontsize=14, pad=20)
    plt.ylabel(ylabel, fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    print(f"Saved {save_path}")

def main():
    print("Loading 1h Data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    df_1h['Trend_State'] = (df_1h['FIB_11_SMA'] - df_1h['FIB_13_SMA']) / df_1h['close'] * 100
    
    # Calculate MTF BBs
    df_1h['BB_21_Upper'], df_1h['BB_21_Lower'] = calculate_bb(df_1h['close'], 21, 2.0)
    df_1h['BB_55_Upper'], df_1h['BB_55_Lower'] = calculate_bb(df_1h['close'], 55, 2.0)
    df_1h['BB_144_Upper'], df_1h['BB_144_Lower'] = calculate_bb(df_1h['close'], 144, 2.0)
    df_1h['BB_377_Upper'], df_1h['BB_377_Lower'] = calculate_bb(df_1h['close'], 377, 2.0)
    
    # Squeeze Index
    fib_periods = {7: 21, 9: 55, 11: 144, 13: 377}
    total_bb_width = 0
    for k, period in fib_periods.items():
        std = df_1h['close'].rolling(period).std()
        sma = df_1h[f'FIB_{k}_SMA']
        total_bb_width += (4 * std) / sma
    
    roll_min = total_bb_width.rolling(720).min()
    roll_max = total_bb_width.rolling(720).max()
    df_1h['Squeeze_Index'] = (total_bb_width - roll_min) / (roll_max - roll_min + 1e-8)
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025)
    df_1h_2025['tb_return'] = labels['tb_return']
    
    print("Calculating SR_Long...")
    cols_long = ['FIB_11_SMA', 'FIB_12_SMA', 'FIB_13_SMA', 'BB_144_Upper', 'BB_144_Lower', 'BB_377_Upper', 'BB_377_Lower']
    sr_long_list = []
    for i in range(len(df_1h_2025)):
        row = df_1h_2025.iloc[i]
        c = row['close']
        atr = row['ATR_14']
        if pd.isna(atr): 
            sr_long_list.append(np.nan)
            continue
        levels_long = [row[col] for col in cols_long if not pd.isna(row[col])]
        sr_long_list.append(calc_sandwich_ratio(levels_long, c, atr) if levels_long else np.nan)
    df_1h_2025['SR_Long'] = sr_long_list
    
    print("Loading 1m Data and Mapping 1h Features...")
    df_1m = load_all_1m_data_2025()
    
    # Mapping 1h features to 1m
    df_1h_mapped = df_1h_2025[['ATR_14', 'Trend_State', 'SR_Long', 'Squeeze_Index', 'tb_return']]
    df_1h_mapped = df_1h_mapped.reindex(df_1m.index.floor('h')).values
    
    df_1m['ATR_1h'] = df_1h_mapped[:, 0]
    df_1m['Trend_State_1h'] = df_1h_mapped[:, 1]
    df_1m['SR_Long_1h'] = df_1h_mapped[:, 2]
    df_1m['Squeeze_Index_1h'] = df_1h_mapped[:, 3]
    df_1m['tb_return_1h'] = df_1h_mapped[:, 4]
    
    print("Calculating Macro Triggers...")
    rolling_high_30m = df_1m['high'].rolling('30min').max()
    panic_mask = (rolling_high_30m - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    armed_single = panic_mask.rolling('2h').max() > 0
    
    rolling_high_60m = df_1m['high'].rolling('60min').max()
    trend_dip_mask = (df_1m['Trend_State_1h'] > 1.5) & ((rolling_high_60m - df_1m['low']) >= (1.0 * df_1m['ATR_1h']))
    armed_trend = trend_dip_mask.rolling('1h').max() > 0
    
    # BASELINE: Original Dual Trigger
    df_1m['Armed_Base'] = armed_single | armed_trend
    
    # VETO FILTER: Cut off if SR_Long > 0.8
    df_1m['Armed_Vetoed'] = df_1m['Armed_Base'] & (df_1m['SR_Long_1h'] <= 0.8)
    
    # GHOST HUNTER TRIGGER: Catch stealth bottoms
    df_1m['Armed_Ghost'] = (df_1m['SR_Long_1h'] < 0.1) & (df_1m['Squeeze_Index_1h'] < 0.5)
    
    # FINAL: Vetoed + Ghost
    df_1m['Armed_Final'] = df_1m['Armed_Vetoed'] | df_1m['Armed_Ghost']
    
    print("Evaluating Performance (Heuristic Proxy PnL)...")
    
    # To evaluate, we'll look at the 1h blocks. If a 1h block is an Oracle (tb_return == 1),
    # did we have an Armed state during it or the preceding hour?
    
    def evaluate_logic(armed_col):
        # resample to 1h to check if it was armed anytime during the hour
        armed_1h = df_1m[armed_col].resample('1h').max() > 0
        df_eval = pd.DataFrame({'Armed': armed_1h, 'Return': df_1h_2025['tb_return']}).dropna()
        
        # Oracle captures (+2.5 R)
        captured_oracles = df_eval[(df_eval['Armed'] == True) & (df_eval['Return'] == 1)]
        # False Alarms (-1.0 R)
        false_alarms = df_eval[(df_eval['Armed'] == True) & (df_eval['Return'] == -1)]
        
        pnl = (len(captured_oracles) * 2.5) - (len(false_alarms) * 1.0)
        time_burden = df_eval['Armed'].mean() * 100
        
        return pnl, time_burden, len(captured_oracles), len(false_alarms)
        
    pnl_base, tb_base, oracles_base, false_base = evaluate_logic('Armed_Base')
    pnl_veto, tb_veto, oracles_veto, false_veto = evaluate_logic('Armed_Vetoed')
    pnl_final, tb_final, oracles_final, false_final = evaluate_logic('Armed_Final')
    
    # Metrics for Waterfall
    base_pnl = pnl_base
    saved_losses = pnl_veto - pnl_base # PnL gained just by applying Veto
    recaptured_gains = pnl_final - pnl_veto # PnL gained by adding Ghost trigger
    final_pnl = pnl_final
    
    print(f"Base PnL: {base_pnl:.1f}R | Time Burden: {tb_base:.1f}%")
    print(f"Final PnL: {final_pnl:.1f}R | Time Burden: {tb_final:.1f}%")
    
    values = [base_pnl, saved_losses, recaptured_gains, final_pnl]
    labels = ['Baseline\n(Dual Trigger)', 'Saved Losses\n(Veto SR > 0.8)', 'Recaptured Gains\n(Ghost SR < 0.1)', 'Final Logic\n(AI Context Base)']
    colors = ['gray', 'lightgreen', 'gold', 'forestgreen']
    
    plot_waterfall(values, labels, colors, "Impact of Topology Engineering: PnL Bridge Chart", "Cumulative R (Proxy PnL)", "sr_application_waterfall.png")
    
    # Subplot for Efficiency (Time Burden & False Alarms)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Time Burden
    axes[0].bar(['Baseline', 'Final Logic'], [tb_base, tb_final], color=['gray', 'forestgreen'], edgecolor='black')
    axes[0].set_title('Time Burden (Efficiency)', fontsize=14)
    axes[0].set_ylabel('% of Time Armed', fontsize=12)
    for i, v in enumerate([tb_base, tb_final]):
        axes[0].text(i, v/2, f"{v:.1f}%", ha='center', color='white', fontweight='bold', fontsize=12)
        
    # False Alarms
    axes[1].bar(['Baseline', 'Final Logic'], [false_base, false_final], color=['salmon', 'lightcoral'], edgecolor='black')
    axes[1].set_title('False Alarms (Avoided Falling Knives)', fontsize=14)
    axes[1].set_ylabel('Number of Stopped Out Triggers', fontsize=12)
    for i, v in enumerate([false_base, false_final]):
        axes[1].text(i, v/2, f"{v} times", ha='center', color='black', fontweight='bold', fontsize=12)
        
    plt.suptitle("System Efficiency Improvements", fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig('sr_application_efficiency.png', dpi=300)
    print("Saved sr_application_efficiency.png")

if __name__ == '__main__':
    main()
