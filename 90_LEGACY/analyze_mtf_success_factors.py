import pandas as pd
import numpy as np
import os
import glob
from tqdm import tqdm
import matplotlib.pyplot as plt
from sklearn.tree import DecisionTreeClassifier, plot_tree
import lightgbm as lgb
import seaborn as sns

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from train_lightgbm import build_v5_0_features

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
    print("Loading 1h Macro data...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    df_1h = calculate_diverse_features(df_1h)
    df_1h, feature_cols = build_v5_0_features(df_1h)
    
    df_1h = df_1h[df_1h.index >= '2025-01-01'].copy()
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    df_1h['pred_L'] = model_long.predict(df_1h[feature_cols])
    
    print("Loading 1m Micro data...")
    df_1m = load_all_1m_data_2025()
    
    print("Loading MTF Trades...")
    mtf = pd.read_csv('mtf_backtest_results.csv')
    mtf['entry_time'] = pd.to_datetime(mtf['entry_time'])
    mtf['ft_time'] = pd.to_datetime(mtf['ft_time'])
    
    # Analyze LONG trades only for cleaner logic
    mtf = mtf[mtf['direction'] == 'LONG'].copy()
    
    # 1. Micro Geometry Features
    print("Extracting Micro Geometry Features...")
    time_deltas = []
    rebound_amps = []
    wick_ratios = []
    
    for _, row in tqdm(mtf.iterrows(), total=len(mtf)):
        t1 = row['ft_time']
        t2 = row['entry_time']
        
        # Time Delta (minutes)
        td = (t2 - t1).total_seconds() / 60.0
        time_deltas.append(td)
        
        # Rebound Amplitude & Wick Ratio
        try:
            ft_candle = df_1m.loc[t1]
            body_bottom = min(ft_candle['open'], ft_candle['close'])
            low = ft_candle['low']
            high = ft_candle['high']
            candle_range = high - low
            if candle_range > 0:
                wick_ratio = (body_bottom - low) / candle_range
            else:
                wick_ratio = 0
            wick_ratios.append(wick_ratio)
            
            # Rebound
            window = df_1m[(df_1m.index >= t1) & (df_1m.index <= t2)]
            if len(window) > 0:
                max_high = window['high'].max()
                rebound_amps.append((max_high - low) / low * 100) # % rebound
            else:
                rebound_amps.append(0)
        except:
            wick_ratios.append(0)
            rebound_amps.append(0)
            
    mtf['time_delta'] = time_deltas
    mtf['rebound_amp'] = rebound_amps
    mtf['ft_wick_ratio'] = wick_ratios
    
    # 2. Macro Alignment Features
    print("Extracting Macro Alignment Features...")
    mtf['1h_candle_time'] = mtf['entry_time'].dt.floor('h')
    mtf = mtf.merge(df_1h[['pred_L', 'F_Wave_Propagation_L', 'FIB_13_stoch_d_slope', 'FIB_8_stoch_d_slope']], 
                    left_on='1h_candle_time', right_index=True, how='left')
                    
    mtf.dropna(subset=['pred_L'], inplace=True)
    
    analysis_df = mtf[mtf['pred_L'] > 0.15].copy()
    
    print(f"Data ready for analysis: {len(analysis_df)} trades.")
    
    features = ['time_delta', 'rebound_amp', 'ft_wick_ratio', 'pred_L', 'F_Wave_Propagation_L', 'FIB_13_stoch_d_slope']
    X = analysis_df[features]
    y = (analysis_df['hit'] == 1).astype(int)
    
    clf = DecisionTreeClassifier(max_depth=3, min_samples_leaf=20, random_state=42)
    clf.fit(X, y)
    
    plt.figure(figsize=(20, 10))
    plot_tree(clf, feature_names=features, class_names=['Lose', 'Win'], filled=True, rounded=True, proportion=True)
    plt.title("Decision Tree for MTF Next Extreme Success/Failure")
    plt.savefig("mtf_decision_tree.png", dpi=300)
    print("Saved mtf_decision_tree.png")
    
    importances = pd.Series(clf.feature_importances_, index=features).sort_values(ascending=False)
    print("\nFeature Importances:")
    print(importances)
    
    top2 = importances.index[:2]
    for feat in top2:
        if importances[feat] > 0:
            plt.figure(figsize=(10, 6))
            sns.histplot(data=analysis_df, x=feat, hue='hit', element="step", stat="density", common_norm=False, palette={1: 'green', -1: 'red'})
            plt.title(f"Distribution of {feat} by Success (Green) / Failure (Red)")
            plt.savefig(f"mtf_dist_{feat}.png")
            print(f"Saved mtf_dist_{feat}.png")
        
if __name__ == "__main__":
    main()
