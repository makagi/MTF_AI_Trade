import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import matplotlib.pyplot as plt
import seaborn as sns

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START
from src.labels import get_triple_barrier_labels
from train_lightgbm import build_v4_features

def run_macro_analysis():
    print("Loading FULL data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    df, feature_cols = build_v4_features(df)
    
    # 1.5 ATR Symmetric (v4.3)
    tb_df = get_triple_barrier_labels(df, pt_sl_ratio=[1.5, 1.5], time_barrier=24, atr_col='ATR_14')
    df['label'] = tb_df['label']
    df['tb_return'] = tb_df['tb_return']
    df['hit_period'] = tb_df['hit_period']
    
    # Calculate Macro Alignment Conditions (FIB 12=233, 13=377, 14=610, 15=987)
    df['FIB_12_slope'] = df['FIB_12_SMA'].diff()
    df['FIB_15_slope'] = df['FIB_15_SMA'].diff()
    
    df['Macro_Order_UP'] = (df['FIB_12_SMA'] > df['FIB_13_SMA']) & (df['FIB_13_SMA'] > df['FIB_14_SMA']) & (df['FIB_14_SMA'] > df['FIB_15_SMA'])
    df['Macro_Order_DOWN'] = (df['FIB_12_SMA'] < df['FIB_13_SMA']) & (df['FIB_13_SMA'] < df['FIB_14_SMA']) & (df['FIB_14_SMA'] < df['FIB_15_SMA'])
    
    df['Macro_Slope_UP'] = (df['FIB_12_slope'] > 0) & (df['FIB_15_slope'] > 0)
    df['Macro_Slope_DOWN'] = (df['FIB_12_slope'] < 0) & (df['FIB_15_slope'] < 0)
    
    # Perfect Macro
    df['Macro_Perfect_UP'] = df['Macro_Order_UP'] & df['Macro_Slope_UP']
    df['Macro_Perfect_DOWN'] = df['Macro_Order_DOWN'] & df['Macro_Slope_DOWN']
    
    df.dropna(subset=['label', 'tb_return'] + feature_cols, inplace=True)
    
    df_train = df[df.index < HOLDOUT_START].copy()
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    
    X_train = df_train[feature_cols]
    y_train = df_train['label'] + 1  
    X_holdout = df_holdout[feature_cols]
    y_holdout = df_holdout['label'] + 1
    
    print("Training Model...")
    model = lgb.LGBMClassifier(objective='multiclass', num_class=3, max_depth=3, min_data_in_leaf=100, learning_rate=0.05, n_estimators=150, random_state=42, verbose=-1)
    model.fit(X_train, y_train)
    preds = model.predict_proba(X_holdout)
    
    df_holdout['prob_short'] = preds[:, 0]
    df_holdout['prob_timeout'] = preds[:, 1]
    df_holdout['prob_long'] = preds[:, 2]
    
    df_holdout['pred_dir'] = np.where(df_holdout['prob_long'] > df_holdout['prob_short'], 'LONG', 'SHORT')
    df_holdout['pred_prob'] = np.where(df_holdout['prob_long'] > df_holdout['prob_short'], df_holdout['prob_long'], df_holdout['prob_short'])
    
    # Result mapping
    conditions = [
        (df_holdout['pred_dir'] == 'LONG') & (df_holdout['label'] == 1),
        (df_holdout['pred_dir'] == 'LONG') & (df_holdout['label'] == -1),
        (df_holdout['pred_dir'] == 'SHORT') & (df_holdout['label'] == -1),
        (df_holdout['pred_dir'] == 'SHORT') & (df_holdout['label'] == 1),
        (df_holdout['label'] == 0)
    ]
    choices = ['WIN', 'LOSS', 'WIN', 'LOSS', 'TIMEOUT']
    df_holdout['result'] = np.select(conditions, choices, default='UNKNOWN')
    
    high_conf = df_holdout[df_holdout['pred_prob'] >= 0.55].copy()
    
    def calc_metrics(subset, name):
        wins = len(subset[subset['result'] == 'WIN'])
        losses = len(subset[subset['result'] == 'LOSS'])
        timeouts = len(subset[subset['result'] == 'TIMEOUT'])
        total_resolved = wins + losses
        win_rate = wins / total_resolved if total_resolved > 0 else 0
        print(f"--- {name} ---")
        print(f"Total: {len(subset)}, Wins: {wins}, Losses: {losses}, Timeouts: {timeouts}")
        print(f"Win Rate (Excl. Timeouts): {win_rate:.2%}\n")
        return win_rate
        
    print("\n=== MACRO CONDITION ANALYSIS (Prob >= 0.55) ===")
    
    # LONGs
    longs = high_conf[high_conf['pred_dir'] == 'LONG']
    calc_metrics(longs, "ALL LONGS")
    calc_metrics(longs[longs['Macro_Perfect_UP'] == True], "LONGS with Perfect Macro UP")
    calc_metrics(longs[longs['Macro_Perfect_DOWN'] == True], "LONGS against Perfect Macro DOWN (Counter-Trend)")
    calc_metrics(longs[(longs['Macro_Perfect_UP'] == False) & (longs['Macro_Perfect_DOWN'] == False)], "LONGS in Range/Mixed Macro")
    
    # SHORTs
    shorts = high_conf[high_conf['pred_dir'] == 'SHORT']
    calc_metrics(shorts, "ALL SHORTS")
    calc_metrics(shorts[shorts['Macro_Perfect_DOWN'] == True], "SHORTS with Perfect Macro DOWN")
    calc_metrics(shorts[shorts['Macro_Perfect_UP'] == True], "SHORTS against Perfect Macro UP (Counter-Trend)")
    calc_metrics(shorts[(shorts['Macro_Perfect_UP'] == False) & (shorts['Macro_Perfect_DOWN'] == False)], "SHORTS in Range/Mixed Macro")

    # Plot failures
    os.makedirs("results/macro_failures", exist_ok=True)
    counter_trend_failures = longs[(longs['Macro_Perfect_DOWN'] == True) & (longs['result'].isin(['LOSS', 'TIMEOUT']))]
    
    if len(counter_trend_failures) > 0:
        worst_ct = counter_trend_failures.sort_values('pred_prob', ascending=False).head(2)
        import matplotlib.dates as mdates
        
        for idx, (entry_time, row) in enumerate(worst_ct.iterrows()):
            trade_type = row['pred_dir']
            prob = row['pred_prob']
            result = row['result']
            
            start_time = entry_time - pd.Timedelta(hours=120)
            end_time = entry_time + pd.Timedelta(hours=48)
            df_plot = df.loc[start_time:end_time]
            
            plt.figure(figsize=(14, 7))
            plt.plot(df_plot.index, df_plot['close'], color='black', label='Close')
            plt.plot(df_plot.index, df_plot['FIB_12_SMA'], color='orange', label='SMA 12 (233)', alpha=0.8)
            plt.plot(df_plot.index, df_plot['FIB_15_SMA'], color='blue', label='SMA 15 (987)', alpha=0.8)
            
            entry_price = row['close']
            atr = row['ATR_14']
            tp_price = entry_price + (1.5 * atr) if trade_type == "LONG" else entry_price - (1.5 * atr)
            sl_price = entry_price - (1.5 * atr) if trade_type == "LONG" else entry_price + (1.5 * atr)
            
            plt.scatter(entry_time, entry_price, color='blue' if trade_type == "LONG" else 'magenta', s=200, marker='^' if trade_type == "LONG" else 'v', label=f'{trade_type} Entry (Prob: {prob:.2f})')
            time_limit = entry_time + pd.Timedelta(hours=24)
            plt.hlines(tp_price, entry_time, time_limit, colors='green', linestyles='dashed', label='TP (1.5 ATR)')
            plt.hlines(sl_price, entry_time, time_limit, colors='red', linestyles='dashed', label='SL (1.5 ATR)')
            
            plt.title(f"COUNTER-TREND FAILURE ({result}): LONG in Macro DOWN at {entry_time}\nProb: {prob:.2f}")
            plt.legend(loc='upper right')
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(f"results/macro_failures/macro_fail_{idx}.png")
            plt.close()
            print(f"Saved Counter-Trend Failure Chart: results/macro_failures/macro_fail_{idx}.png")

if __name__ == "__main__":
    run_macro_analysis()
