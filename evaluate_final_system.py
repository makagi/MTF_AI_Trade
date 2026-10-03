import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def calculate_atr(df, p=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(p).mean()
    df['ATR_144'] = true_range.rolling(144).mean()
    return df

def get_fib_periods():
    return [21, 55, 144, 377, 610, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'SMA_{p}'] = sma
        df[f'BW_{p}'] = (upper - lower) / df['close']
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
        
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

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    # Base Conditions
    bw144_q = df['BW_144'].rolling(720).quantile(0.4)
    cond_macro_vol = (df['BW_144'] < bw144_q)
    cond_macro_phase = (df['PHASE_144'] <= 0)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55'])
    cond_micro_phase = (df['PHASE_21'] == 1) & (df['PHASE_21'].shift(1) <= 0)
    
    base_idx = df[cond_macro_vol & cond_macro_phase & cond_micro_mom & cond_micro_phase].index
    
    # First Fix (Divergence)
    price_low = df['low'].rolling(24).min()
    price_prev_low = df['low'].shift(24).rolling(96).min()
    afs_curr = df['AFS_144'].rolling(24).min()
    afs_prev = df['AFS_144'].shift(24).rolling(96).min()
    bull_div = (price_low < price_prev_low) & (afs_curr > afs_prev)
    
    first_fix_idx = df.loc[base_idx][bull_div.loc[base_idx]].index
    
    # Second Fix (The Void)
    sma_cols = ['SMA_144', 'SMA_377', 'SMA_610', 'SMA_1597']
    def get_void(row):
        smas = row[sma_cols]
        ceiling = smas[smas > row['close']].min()
        if pd.isna(ceiling):
            ceiling = row['close'] * 1.5 
        return (ceiling - row['close']) / row['ATR_144']
        
    df['Void_ATR'] = df.apply(get_void, axis=1)
    
    second_fix_idx = [idx for idx in first_fix_idx if df.loc[idx, 'Void_ATR'] >= 3.0]
    
    # Evaluate MAE/MFE for a 48h horizon
    def eval_trades(indices, label):
        results = []
        for idx in indices:
            loc = df.index.get_loc(idx)
            if loc + 48 >= len(df):
                continue
            entry_price = df['close'].iloc[loc]
            atr = df['ATR'].iloc[loc]
            future_prices = df['close'].iloc[loc:loc+48].values
            trajectory = (future_prices - entry_price) / atr
            results.append({
                'Stage': label,
                'MAE': trajectory.min(),
                'MFE': trajectory.max()
            })
        return pd.DataFrame(results)
        
    res_base = eval_trades(base_idx, '1. Base (N=145)')
    res_first = eval_trades(first_fix_idx, '2. + Divergence (N=13)')
    res_second = eval_trades(second_fix_idx, '3. + The Void (N=4)')
    
    all_res = pd.concat([res_base, res_first, res_second])
    
    # Plotting
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    
    # MAE Boxplot
    sns.boxplot(data=all_res, x='Stage', y='MAE', ax=axes[0], palette='Reds')
    axes[0].set_title("Drawdown Reduction (MAE)\nDivergence Filter kills 'Falling Knives'", fontsize=14, color='white')
    axes[0].axhline(0, color='white', linestyle='--', alpha=0.5)
    axes[0].set_ylabel("Max Adverse Excursion (ATR)")
    
    # MFE Boxplot
    sns.boxplot(data=all_res, x='Stage', y='MFE', ax=axes[1], palette='Blues')
    axes[1].set_title("Profit Explosion (MFE)\nThe Void Filter unleashes 'Zero-Gravity Phase'", fontsize=14, color='white')
    axes[1].axhline(0, color='white', linestyle='--', alpha=0.5)
    axes[1].set_ylabel("Max Favorable Excursion (ATR)")
    
    plt.tight_layout()
    plt.savefig("alpha_funnel_evaluation.png", dpi=300)
    print("Saved alpha_funnel_evaluation.png")
    
    # Calculate Win Rates (Success = MFE >= 1.5 and MAE > -1.0)
    for name, grp in all_res.groupby('Stage'):
        success = ((grp['MFE'] >= 1.5) & (grp['MAE'] > -1.0)).sum()
        total = len(grp)
        print(f"{name}: Win Rate = {success/total*100:.1f}% ({success}/{total})")

if __name__ == '__main__':
    main()
