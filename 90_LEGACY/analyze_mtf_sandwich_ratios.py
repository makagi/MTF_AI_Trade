import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
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

def main():
    print("Loading 1h Data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    
    # Calculate MTF BBs
    df_1h['BB_21_Upper'], df_1h['BB_21_Lower'] = calculate_bb(df_1h['close'], 21, 2.0)
    df_1h['BB_55_Upper'], df_1h['BB_55_Lower'] = calculate_bb(df_1h['close'], 55, 2.0)
    df_1h['BB_144_Upper'], df_1h['BB_144_Lower'] = calculate_bb(df_1h['close'], 144, 2.0)
    df_1h['BB_377_Upper'], df_1h['BB_377_Lower'] = calculate_bb(df_1h['close'], 377, 2.0)
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025)
    df_1h_2025['tb_return'] = labels['tb_return']
    
    print("Calculating MTF Sandwich Ratios...")
    
    data = []
    
    # Define layers
    cols_short = ['FIB_5_SMA', 'FIB_6_SMA', 'FIB_7_SMA', 'BB_21_Upper', 'BB_21_Lower'] # 8, 13, 21
    cols_mid = ['FIB_8_SMA', 'FIB_9_SMA', 'FIB_10_SMA', 'BB_55_Upper', 'BB_55_Lower'] # 34, 55, 89
    cols_long = ['FIB_11_SMA', 'FIB_12_SMA', 'FIB_13_SMA', 'BB_144_Upper', 'BB_144_Lower', 'BB_377_Upper', 'BB_377_Lower'] # 144, 233, 377
    
    for i in tqdm(range(len(df_1h_2025) - 72)):
        row = df_1h_2025.iloc[i]
        c = row['close']
        atr = row['ATR_14']
        
        if pd.isna(atr): continue
            
        levels_short = [row[col] for col in cols_short if not pd.isna(row[col])]
        levels_mid = [row[col] for col in cols_mid if not pd.isna(row[col])]
        levels_long = [row[col] for col in cols_long if not pd.isna(row[col])]
        
        if not levels_short or not levels_mid or not levels_long: continue
            
        sr_short = calc_sandwich_ratio(levels_short, c, atr)
        sr_mid = calc_sandwich_ratio(levels_mid, c, atr)
        sr_long = calc_sandwich_ratio(levels_long, c, atr)
        
        is_oracle = (row['tb_return'] == 1)
        
        data.append({
            'SR_Short': sr_short,
            'SR_Mid': sr_mid,
            'SR_Long': sr_long,
            'Is_Oracle': is_oracle
        })
            
    df_results = pd.DataFrame(data)
    
    baseline_prob = df_results['Is_Oracle'].mean() * 100
    print(f"Baseline Oracle Probability: {baseline_prob:.2f}%")
    
    print("Generating Visualizations...")
    sns.set_theme(style="whitegrid")
    
    bins = np.arange(0, 1.1, 0.1)
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=True)
    
    layers = ['SR_Short', 'SR_Mid', 'SR_Long']
    titles = ['Short-Term Layer (Noise)', 'Mid-Term Layer (Transition)', 'Long-Term Layer (Macro Structure)']
    colors = ['skyblue', 'orange', 'firebrick']
    
    for i, (col, title, color) in enumerate(zip(layers, titles, colors)):
        df_results['Ratio_Bin'] = pd.cut(df_results[col], bins=bins)
        prob = df_results.groupby('Ratio_Bin')['Is_Oracle'].mean() * 100
        
        ax = axes[i]
        prob.plot(kind='bar', color=color, edgecolor='black', ax=ax)
        
        # Draw Baseline
        ax.axhline(y=baseline_prob, color='red', linestyle='--', linewidth=2, label=f'Baseline ({baseline_prob:.1f}%)')
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=10)
        ax.set_xlabel('Sandwich Ratio (0.0 = Touching Floor)', fontsize=12)
        if i == 0:
            ax.set_ylabel('Oracle Probability (%)', fontsize=12)
        ax.set_xticklabels([f"{b.left:.1f}-{b.right:.1f}" for b in prob.index], rotation=45)
        
        # Calculate and annotate Lift for the 0.0-0.1 bin
        first_bin_prob = prob.iloc[0]
        if not pd.isna(first_bin_prob) and first_bin_prob > 0:
            lift = first_bin_prob / baseline_prob
            ax.annotate(f"Lift: {lift:.1f}x\n({first_bin_prob:.1f}%)", 
                        xy=(0, first_bin_prob), 
                        xytext=(0, first_bin_prob + (10 if first_bin_prob < 20 else 5)),
                        ha='center', va='bottom', fontsize=11, color='darkred', fontweight='bold',
                        arrowprops=dict(facecolor='darkred', arrowstyle='->'))
        
        ax.legend()
        
    plt.suptitle('MTF Sandwich Ratio Decomposition: Edge vs Noise by Timeframe', fontsize=18, fontweight='bold', y=1.05)
    plt.tight_layout()
    plt.savefig('mtf_sandwich_ratios.png', dpi=300, bbox_inches='tight')
    print("Saved mtf_sandwich_ratios.png")

if __name__ == '__main__':
    main()
