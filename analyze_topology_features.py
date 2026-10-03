import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
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

def calculate_bb(series, period, std_dev=2.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return sma + (std * std_dev), sma - (std * std_dev)

def main():
    print("Loading 1h Data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    
    # Calculate MTF BBs (21, 55, 144)
    df_1h['BB_21_Upper'], df_1h['BB_21_Lower'] = calculate_bb(df_1h['close'], 21, 2.0)
    df_1h['BB_55_Upper'], df_1h['BB_55_Lower'] = calculate_bb(df_1h['close'], 55, 2.0)
    df_1h['BB_144_Upper'], df_1h['BB_144_Lower'] = calculate_bb(df_1h['close'], 144, 2.0)
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    labels = get_binary_barrier_labels(df_1h_2025)
    df_1h_2025['tb_return'] = labels['tb_return']
    
    print("Calculating Topology Features (Sandwich Ratio & Wall Density)...")
    
    sandwich_ratios = []
    wall_densities = []
    mfes = []
    is_oracle = []
    
    # List of support/resistance candidate lines
    level_cols = [
        'FIB_7_SMA', 'FIB_9_SMA', 'FIB_11_SMA', 'FIB_13_SMA',
        'BB_21_Upper', 'BB_21_Lower',
        'BB_55_Upper', 'BB_55_Lower',
        'BB_144_Upper', 'BB_144_Lower'
    ]
    
    for i in tqdm(range(len(df_1h_2025) - 72)):
        row = df_1h_2025.iloc[i]
        c = row['close']
        atr = row['ATR_14']
        
        if pd.isna(atr): continue
            
        levels = [row[col] for col in level_cols if not pd.isna(row[col])]
        if not levels: continue
            
        # Ceiling & Floor
        ceilings = [l for l in levels if l > c]
        floors = [l for l in levels if l <= c]
        
        ceiling = min(ceilings) if ceilings else c + atr*5
        floor = max(floors) if floors else c - atr*5
        
        # Sandwich Ratio
        ratio = (c - floor) / (ceiling - floor + 1e-8)
        sandwich_ratios.append(ratio)
        
        # Wall Density (Number of supports within 0.5 ATR below close)
        density = sum(1 for l in floors if (c - 0.5*atr) <= l <= c)
        wall_densities.append(density)
        
        # Is Oracle?
        oracle = (row['tb_return'] == 1)
        is_oracle.append(oracle)
        
        # MFE Simulation for 72h
        if oracle:
            entry_price = c
            sl_price = entry_price - 1.0 * atr
            future_highs = df_1h_2025['high'].iloc[i+1 : i+73].values
            future_lows = df_1h_2025['low'].iloc[i+1 : i+73].values
            
            max_price = entry_price
            for j in range(len(future_highs)):
                if future_lows[j] <= sl_price:
                    break
                if future_highs[j] > max_price:
                    max_price = future_highs[j]
            mfe_atr = (max_price - entry_price) / atr
            mfes.append(mfe_atr)
        else:
            mfes.append(np.nan)
            
    df_results = pd.DataFrame({
        'Sandwich_Ratio': sandwich_ratios,
        'Wall_Density': wall_densities,
        'Is_Oracle': is_oracle,
        'MFE_ATR': mfes
    })
    
    print("Generating Visualizations...")
    sns.set_theme(style="whitegrid")
    
    # Chart 1: Sandwich Ratio vs Oracle Probability
    plt.figure(figsize=(10, 6))
    bins = np.arange(0, 1.1, 0.1)
    df_results['Ratio_Bin'] = pd.cut(df_results['Sandwich_Ratio'], bins=bins)
    oracle_prob = df_results.groupby('Ratio_Bin')['Is_Oracle'].mean() * 100
    
    ax1 = oracle_prob.plot(kind='bar', color='royalblue', edgecolor='black')
    plt.title('Topology Edge: Sandwich Ratio vs Oracle Likelihood (Bottom Finding)', fontsize=14, pad=15)
    plt.xlabel('Sandwich Ratio (0.0 = Touching Floor Support, 1.0 = Touching Ceiling Resistance)', fontsize=12)
    plt.ylabel('Oracle Probability (%)', fontsize=12)
    plt.xticks(rotation=45)
    
    for p in ax1.patches:
        ax1.annotate(f"{p.get_height():.1f}%", (p.get_x() + p.get_width() / 2., p.get_height()),
                     ha='center', va='bottom', fontsize=10, color='black', fontweight='bold')
                     
    plt.tight_layout()
    plt.savefig('topology_sandwich_ratio.png', dpi=300)
    print("Saved topology_sandwich_ratio.png")
    
    # Chart 2: Wall Density vs MFE
    plt.figure(figsize=(10, 6))
    df_oracles = df_results[df_results['Is_Oracle'] == True].copy()
    # Group density 3+ together
    df_oracles['Wall_Density_Group'] = df_oracles['Wall_Density'].apply(lambda x: '3+' if x >= 3 else str(x))
    order = ['0', '1', '2', '3+']
    
    sns.boxplot(data=df_oracles, x='Wall_Density_Group', y='MFE_ATR', order=order, palette='autumn')
    plt.title('Support Strength: Wall Density vs Mega Trend Potential (MFE)', fontsize=14, pad=15)
    plt.xlabel('Wall Density (Number of SMAs/BBs grouped within 0.5 ATR below entry)', fontsize=12)
    plt.ylabel('Maximum Favorable Excursion (MFE in ATR)', fontsize=12)
    
    plt.tight_layout()
    plt.savefig('topology_wall_density.png', dpi=300)
    print("Saved topology_wall_density.png")

if __name__ == '__main__':
    main()
