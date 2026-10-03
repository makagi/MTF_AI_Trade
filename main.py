import os
import pandas as pd
from src.config import MAX_FIB_INDEX_1H, TARGET_HORIZON_1H
from src.data_loader import load_1h_data
from src.features import calculate_fib_features
from src.model import create_target, train_lightgbm_baseline
from src.evaluation import simulate_trading, calculate_metrics, plot_results

def main():
    print("=== Phase 1 Baseline Execution ===")
    
    # 1. データロード
    print("Loading data...")
    df_1h = load_1h_data()
    print(f"Data shape: {df_1h.shape}")
    
    # 2. 特徴量生成 (1時間足)
    print("Generating features...")
    df_features = calculate_fib_features(df_1h, MAX_FIB_INDEX_1H)
    
    # 3. 目的変数生成
    print("Creating targets...")
    df_target = create_target(df_features, TARGET_HORIZON_1H)
    
    # 使用する特徴量のリスト抽出 (OHLCV等は除く)
    feature_cols = [c for c in df_target.columns if c.startswith('FIB_') or c.startswith('AFS_')]
    print(f"Number of features: {len(feature_cols)}")
    
    # 4. 学習 (Walk-Forward簡易版)
    print("Training LightGBM Baseline...")
    model, test_df, test_preds, train_df, val_df = train_lightgbm_baseline(df_target, feature_cols)
    
    # 5. シミュレーションと評価
    print("Simulating trades on Out-of-Sample (OOS) data...")
    # 閾値を厳しめにしてドローダウンを抑制するアプローチ
    result_df = simulate_trading(test_df, test_preds, threshold_long=0.55, threshold_short=0.45)
    
    metrics = calculate_metrics(result_df, timeframe_hours=1)
    
    print("\n=== Out-of-Sample Results ===")
    for k, v in metrics.items():
        if 'Return' in k or 'Drawdown' in k or 'Rate' in k:
            print(f"{k}: {v*100:.2f}%")
        else:
            print(f"{k}: {v}")
            
    # 結果のプロット
    plot_path = os.path.join(os.getcwd(), "baseline_results.png")
    plot_results(result_df, model, feature_cols, plot_path)
    print("Baseline execution completed.")

if __name__ == "__main__":
    main()
