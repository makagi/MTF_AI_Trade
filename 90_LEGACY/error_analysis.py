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

def run_error_analysis():
    print("Loading data for Error Analysis...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    df, feature_cols = build_v4_features(df)
    
    # Asymmetric Barrier (v4.2)
    tb_df = get_triple_barrier_labels(df, pt_sl_ratio=[1.2, 2.5], time_barrier=24, atr_col='ATR_14')
    df['label'] = tb_df['label']
    df['tb_return'] = tb_df['tb_return']
    df['hit_period'] = tb_df['hit_period']
    
    df.dropna(subset=['label', 'tb_return'] + feature_cols, inplace=True)
    
    df_train = df[df.index < HOLDOUT_START].copy()
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    
    X_train = df_train[feature_cols]
    y_train = df_train['label'] + 1  # 0: Short Win(-1), 1: Timeout(0), 2: Long Win(1)
    
    X_holdout = df_holdout[feature_cols]
    y_holdout = df_holdout['label'] + 1
    
    # Train Model
    model = lgb.LGBMClassifier(
        objective='multiclass', num_class=3, max_depth=3, 
        min_data_in_leaf=100, learning_rate=0.05, n_estimators=150, random_state=42, verbose=-1
    )
    model.fit(X_train, y_train)
    
    preds = model.predict_proba(X_holdout)
    
    # 1. Trade Log DataFrame 作成
    log_df = df_holdout[feature_cols + ['label', 'tb_return', 'ATR_14', 'close']].copy()
    log_df['prob_short'] = preds[:, 0]
    log_df['prob_timeout'] = preds[:, 1]
    log_df['prob_long'] = preds[:, 2]
    
    # 方向と最大確率を決定
    log_df['pred_dir'] = np.where(log_df['prob_long'] > log_df['prob_short'], 'LONG', 'SHORT')
    log_df['pred_prob'] = np.where(log_df['prob_long'] > log_df['prob_short'], log_df['prob_long'], log_df['prob_short'])
    
    # トレード結果の判定
    # 実際のラベル: 1=Long利確, -1=Short利確(Long損切), 0=時間切れ
    conditions = [
        (log_df['pred_dir'] == 'LONG') & (log_df['label'] == 1),
        (log_df['pred_dir'] == 'LONG') & (log_df['label'] == -1),
        (log_df['pred_dir'] == 'SHORT') & (log_df['label'] == -1),
        (log_df['pred_dir'] == 'SHORT') & (log_df['label'] == 1),
        (log_df['label'] == 0)
    ]
    choices = ['WIN', 'LOSS', 'WIN', 'LOSS', 'TIMEOUT']
    log_df['result'] = np.select(conditions, choices, default='UNKNOWN')
    
    # 2. 確度別・結果別のマトリクス集計
    bins = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    log_df['prob_bin'] = pd.cut(log_df['pred_prob'], bins=bins)
    
    print("\n=== Trade Results by Probability Bin ===")
    pivot = pd.crosstab(log_df['prob_bin'], log_df['result'], margins=True)
    if 'WIN' in pivot.columns and 'LOSS' in pivot.columns:
        pivot['Win_Rate'] = pivot['WIN'] / (pivot['WIN'] + pivot['LOSS'])
    print(pivot)
    
    # 3. 高確度トレードのプロファイリング（High Confidence > 0.6）
    high_conf = log_df[log_df['pred_prob'] >= 0.6]
    tp_df = high_conf[high_conf['result'] == 'WIN']  # True Positives
    fp_df = high_conf[high_conf['result'] == 'LOSS'] # False Positives
    
    print(f"\nHigh Confidence (P>=0.6) True Positives (WIN): {len(tp_df)}")
    print(f"High Confidence (P>=0.6) False Positives (LOSS): {len(fp_df)}")
    
    # 分布比較プロット
    os.makedirs("results", exist_ok=True)
    fig, axes = plt.subplots(len(feature_cols) + 1, 1, figsize=(10, 3 * (len(feature_cols) + 1)))
    
    for i, f in enumerate(feature_cols + ['ATR_14']):
        ax = axes[i]
        sns.kdeplot(data=tp_df[f], ax=ax, color='green', label='WIN (True Positive)', fill=True, alpha=0.3)
        sns.kdeplot(data=fp_df[f], ax=ax, color='red', label='LOSS (False Positive)', fill=True, alpha=0.3)
        ax.set_title(f"Distribution of {f} (P >= 0.6)")
        ax.legend()
        
    plt.tight_layout()
    plt.savefig("results/error_analysis_kde.png")
    print("\nSaved KDE plots to results/error_analysis_kde.png")
    
    # テーブル出力用
    print("\n=== Mean Values for High Confidence Trades ===")
    mean_df = pd.DataFrame({
        'WIN_Mean': tp_df[feature_cols + ['ATR_14']].mean(),
        'LOSS_Mean': fp_df[feature_cols + ['ATR_14']].mean()
    })
    mean_df['Diff_%'] = ((mean_df['LOSS_Mean'] - mean_df['WIN_Mean']) / np.abs(mean_df['WIN_Mean'])) * 100
    import matplotlib.dates as mdates
    
    # 4. 可視化: 最も自信があって失敗(LOSS/TIMEOUT)したトレードのチャートを描画
    print("\nPlotting worst failures for visual inspection...")
    os.makedirs("results/failures", exist_ok=True)
    
    worst_losses = high_conf[high_conf['result'] == 'LOSS'].sort_values('pred_prob', ascending=False).head(3)
    worst_timeouts = high_conf[high_conf['result'] == 'TIMEOUT'].sort_values('pred_prob', ascending=False).head(3)
    
    all_worst = pd.concat([worst_losses, worst_timeouts])
    
    for idx, (entry_time, row) in enumerate(all_worst.iterrows()):
        trade_type = row['pred_dir']
        prob = row['pred_prob']
        result = row['result']
        
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
        tp_price = entry_price + (1.2 * atr) if trade_type == "LONG" else entry_price - (1.2 * atr)
        sl_price = entry_price - (2.5 * atr) if trade_type == "LONG" else entry_price + (2.5 * atr)
        
        plt.scatter(entry_time, entry_price, color='blue' if trade_type == "LONG" else 'magenta', 
                    s=150, marker='^' if trade_type == "LONG" else 'v', 
                    label=f'{trade_type} Entry (Prob: {prob:.2f})')
                    
        # Draw TP / SL lines from entry to +24h
        time_limit = entry_time + pd.Timedelta(hours=24)
        plt.hlines(tp_price, entry_time, time_limit, colors='green', linestyles='dashed', label='Take Profit (1.2 ATR)')
        plt.hlines(sl_price, entry_time, time_limit, colors='red', linestyles='dashed', label='Stop Loss (2.5 ATR)')
        plt.axvline(time_limit, color='gray', linestyle='dotted', alpha=0.5)
        
        plt.title(f"FAILURE ANALYSIS ({result}): {trade_type} Trade at {entry_time}\nProb: {prob:.2f}, Accel: {row.get('F_Fanout_Acceleration', 0):.4f}")
        plt.legend(loc='upper left')
        plt.grid(True, alpha=0.3)
        
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H'))
        plt.tight_layout()
        filename = f"results/failures/fail_v41_{result}_{trade_type}_{entry_time.strftime('%Y%m%d_%H')}.png"
        plt.savefig(filename)
        plt.close()
        print(f"Saved failure chart: {filename}")

if __name__ == "__main__":
    run_error_analysis()
