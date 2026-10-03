import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START
from src.labels import get_triple_barrier_labels
from train_lightgbm import build_v4_features

def run_failure_analysis():
    print("Loading data for failure analysis...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    df, feature_cols = build_v4_features(df)
    
    # 1.5 ATR Symmetric TB
    tb_df = get_triple_barrier_labels(df, pt_sl_ratio=[1.5, 1.5], time_barrier=24, atr_col='ATR_14')
    df['label'] = tb_df['label']
    df['tb_return'] = tb_df['tb_return']
    df['hit_period'] = tb_df['hit_period']
    
    df.dropna(subset=['label'] + feature_cols, inplace=True)
    
    df_train = df[df.index < HOLDOUT_START].copy()
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    
    X_train = df_train[feature_cols]
    y_train = df_train['label'] + 1 
    
    X_holdout = df_holdout[feature_cols]
    y_holdout = df_holdout['label'] + 1
    
    model = lgb.LGBMClassifier(
        objective='multiclass', num_class=3, max_depth=3, 
        min_data_in_leaf=100, learning_rate=0.05, n_estimators=150, random_state=42, verbose=-1
    )
    model.fit(X_train, y_train)
    
    preds = model.predict_proba(X_holdout)
    
    # 解析用DataFrame
    df_res = df_holdout.copy()
    df_res['prob_short'] = preds[:, 0]
    df_res['prob_timeout'] = preds[:, 1]
    df_res['prob_long'] = preds[:, 2]
    
    # 強い自信があったが「完全に逆行した」負けトレードを抽出
    # Long失敗: prob_long > 0.50 だが label は -1 (Short Win = つまり下落してStop Lossにヒット)
    long_failures = df_res[(df_res['prob_long'] > 0.50) & (df_res['label'] == -1)]
    # Short失敗: prob_short > 0.50 だが label は 1 (Long Win = つまり上昇してStop Lossにヒット)
    short_failures = df_res[(df_res['prob_short'] > 0.50) & (df_res['label'] == 1)]
    
    print(f"\nTotal Holdout samples: {len(df_res)}")
    print(f"High Confidence Long Failures: {len(long_failures)}")
    print(f"High Confidence Short Failures: {len(short_failures)}")
    
    # 特徴量の平均値を比較して、失敗パターンの傾向を分析
    print("\n=== Feature Means for Failures vs All ===")
    all_means = df_res[feature_cols].mean()
    long_fail_means = long_failures[feature_cols].mean()
    short_fail_means = short_failures[feature_cols].mean()
    
    comp_df = pd.DataFrame({
        'All_Holdout': all_means,
        'Long_Failures': long_fail_means,
        'Short_Failures': short_fail_means
    })
    print(comp_df)
    
    # 最も自信があったのに負けたトップ3を描画
    os.makedirs("results/failures", exist_ok=True)
    
    worst_longs = long_failures.sort_values('prob_long', ascending=False).head(2)
    worst_shorts = short_failures.sort_values('prob_short', ascending=False).head(2)
    
    all_worst = pd.concat([worst_longs, worst_shorts])
    
    for idx, (entry_time, row) in enumerate(all_worst.iterrows()):
        trade_type = "LONG" if row['prob_long'] > 0.50 else "SHORT"
        prob = row['prob_long'] if trade_type == "LONG" else row['prob_short']
        
        # エントリー時刻の前後48時間を切り出し
        start_time = entry_time - pd.Timedelta(hours=48)
        end_time = entry_time + pd.Timedelta(hours=48)
        df_plot = df.loc[start_time:end_time]
        
        plt.figure(figsize=(12, 6))
        
        # Price and SMAs
        plt.plot(df_plot.index, df_plot['close'], color='black', label='Close')
        plt.plot(df_plot.index, df_plot['FIB_11_SMA'], color='red', alpha=0.5, label='SMA 11 (144)')
        plt.plot(df_plot.index, df_plot['FIB_16_SMA'], color='purple', alpha=0.5, label='SMA 16 (1597)')
        
        # Entry Point
        entry_price = row['close']
        atr = row['ATR_14']
        tp_price = entry_price + (1.5 * atr) if trade_type == "LONG" else entry_price - (1.5 * atr)
        sl_price = entry_price - (1.5 * atr) if trade_type == "LONG" else entry_price + (1.5 * atr)
        
        plt.scatter(entry_time, entry_price, color='blue' if trade_type == "LONG" else 'magenta', 
                    s=150, marker='^' if trade_type == "LONG" else 'v', 
                    label=f'{trade_type} Entry (Prob: {prob:.2f})')
                    
        # Draw TP / SL lines from entry to +24h
        time_limit = entry_time + pd.Timedelta(hours=24)
        plt.hlines(tp_price, entry_time, time_limit, colors='green', linestyles='dashed', label='Take Profit (1.5 ATR)')
        plt.hlines(sl_price, entry_time, time_limit, colors='red', linestyles='dashed', label='Stop Loss (1.5 ATR)')
        plt.axvline(time_limit, color='gray', linestyle='dotted', alpha=0.5)
        
        plt.title(f"FAILURE ANALYSIS: {trade_type} Trade at {entry_time}\nProb: {prob:.2f}, Sync_Long: {row['F_Sync_Long']:.2f}")
        plt.legend(loc='upper left')
        plt.grid(True, alpha=0.3)
        
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H'))
        plt.tight_layout()
        filename = f"results/failures/fail_{trade_type}_{entry_time.strftime('%Y%m%d_%H')}.png"
        plt.savefig(filename)
        plt.close()
        print(f"Saved failure chart: {filename}")

if __name__ == "__main__":
    run_failure_analysis()
