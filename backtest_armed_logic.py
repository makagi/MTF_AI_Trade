import pandas as pd
import numpy as np
import glob
import lightgbm as lgb
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from train_lightgbm import build_v5_0_features

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
    print("Loading 1h Data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    df_1h = calculate_diverse_features(df_1h)
    df_1h, feature_cols = build_v5_0_features(df_1h)
    
    # Base ATR
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    
    print("Evaluating Old Logic (LightGBM 1h)...")
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    df_1h_2025['pred_L'] = model_long.predict(df_1h_2025[feature_cols])
    df_1h_2025['Armed_Old'] = df_1h_2025['pred_L'] >= 0.33
    
    labels = get_binary_barrier_labels(df_1h_2025, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    oracle_1h_indices = labels[labels['tb_return'] == 1].index
    
    print("Loading 1m Data...")
    df_1m = load_all_1m_data_2025()
    
    print("Extracting exact 1m Oracle times...")
    oracle_1m_times = []
    for t_oracle in tqdm(oracle_1h_indices):
        t_start = t_oracle - pd.Timedelta(hours=1)
        t_end = t_oracle + pd.Timedelta(hours=1, minutes=59)
        window = df_1m.loc[t_start:t_end]
        if len(window) > 0:
            oracle_1m_times.append(window['low'].idxmin())
            
    oracle_1m_times = sorted(list(set(oracle_1m_times)))
    print(f"Total Unique Oracles (Ground Truth): {len(oracle_1m_times)}")
    
    print("Vectorizing Armed States...")
    df_1h_2025['Armed_Old_Shifted'] = df_1h_2025['Armed_Old'].shift(1)
    df_1m['Armed_Old'] = df_1h_2025['Armed_Old_Shifted'].reindex(df_1m.index, method='ffill').fillna(False)
    df_1m['ATR_1h'] = df_1h_2025['ATR_14'].reindex(df_1m.index, method='ffill')
    
    print("Calculating rolling high...")
    rolling_high = df_1m['high'].rolling('30min').max()
    
    print("Calculating trigger mask...")
    trigger_mask = (rolling_high - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    
    # New Logic: Armed if trigger occurred anytime in the last 2 hours
    print("Calculating Armed New...")
    df_1m['Armed_New'] = trigger_mask.rolling('2h').max() > 0
    
    print("\nEvaluating Captures...")
    captured_old = 0
    captured_new = 0
    
    for t in oracle_1m_times:
        try:
            if df_1m.loc[t, 'Armed_Old']: captured_old += 1
            if df_1m.loc[t, 'Armed_New']: captured_new += 1
        except KeyError:
            continue
            
    total_oracles = len(oracle_1m_times)
    
    time_burden_old = df_1m['Armed_Old'].mean() * 100
    time_burden_new = df_1m['Armed_New'].mean() * 100
    
    print(f"\n--- Backtest Results (Jan 2025 - Present) ---")
    print(f"Total Oracle Bottoms: {total_oracles}")
    print("-" * 50)
    print(f"[Old Logic] (1h Close pred >= 0.25)")
    print(f"Captured: {captured_old} ({(captured_old/total_oracles)*100:.1f}%)")
    print(f"Missed: {total_oracles - captured_old} ({((total_oracles - captured_old)/total_oracles)*100:.1f}%)")
    print(f"Time Burden (Armed %): {time_burden_old:.1f}%")
    print("-" * 50)
    print(f"[New Logic] (Real-time 1.5 ATR Drop -> 4h Decay)")
    print(f"Captured: {captured_new} ({(captured_new/total_oracles)*100:.1f}%)")
    print(f"Missed: {total_oracles - captured_new} ({((total_oracles - captured_new)/total_oracles)*100:.1f}%)")
    print(f"Time Burden (Armed %): {time_burden_new:.1f}%")
    
    # Save to a text file
    with open('armed_logic_backtest.txt', 'w') as f:
        f.write(f"Total Oracles: {total_oracles}\n")
        f.write(f"Old_Captured: {captured_old}\n")
        f.write(f"Old_Burden: {time_burden_old:.1f}\n")
        f.write(f"New_Captured: {captured_new}\n")
        f.write(f"New_Burden: {time_burden_new:.1f}\n")

if __name__ == '__main__':
    main()
