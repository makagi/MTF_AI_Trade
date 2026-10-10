import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from src.config import MAX_FIB_INDEX_1H, TARGET_HORIZON_1H
from src.data_loader import load_1h_data
from src.features import calculate_fib_features
from src.model import create_target
from src.evaluation import calculate_metrics, plot_results
from src.model_v2 import detect_regimes, generate_signals_v2

# 出力先ディレクトリ
OUTPUT_DIR = r"D:\work\AI-Trade\SakanaAISystemTrade\reports\Backtests\02_hypothesis_verification"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def simulate_v2(df: pd.DataFrame, signals: pd.Series):
    """シンプルな仮説検証シミュレーター"""
    df = df.copy()
    df['signal'] = signals
    
    # ポジションはN時間（ターゲットホライズン）保持すると仮定
    # 厳密にはイグジット条件もレジームごとに作るべきだが、今回は優位性の確認
    df['strategy_return'] = df['signal'] * df['target_return']
    
    # コスト計算 (FEE_RATE + SLIPPAGE) = 0.0005 * 2 = 0.001
    df['trades'] = df['signal'].abs() > 0
    df.loc[df['trades'], 'strategy_return'] -= 0.001
    
    df['cum_return'] = (1 + df['strategy_return']).cumprod()
    df['bnh_return'] = (1 + df['target_return']).cumprod()
    
    df['peak'] = df['cum_return'].cummax()
    df['drawdown'] = (df['cum_return'] - df['peak']) / df['peak']
    
    return df

def main():
    print("=== Phase 2 Hypothesis Verification (Simulation) ===")
    
    # 1. データロードと特徴量生成
    df_1h = load_1h_data()
    # メモリと時間の節約のため、EDAで観察した2020年〜2024年の一部を使用（例として全期間）
    df_features = calculate_fib_features(df_1h, MAX_FIB_INDEX_1H)
    df_target = create_target(df_features, TARGET_HORIZON_1H)
    
    # 2. Stage 1: レジーム判定
    print("Detecting Regimes...")
    df_target['regime'] = detect_regimes(df_target)
    regime_counts = df_target['regime'].value_counts()
    print(f"Regime counts:\n{regime_counts}")
    
    # 3. Stage 2: シグナル生成
    print("Generating Signals based on Hypotheses...")
    signals = generate_signals_v2(df_target)
    signal_counts = signals.value_counts()
    print(f"Signal counts:\n{signal_counts}")
    
    # 4. シミュレーション評価
    print("Simulating trades...")
    result_df = simulate_v2(df_target, signals)
    
    # 評価は全体の後半部分で行う (Walk-ForwardのOOS相当)
    n = len(result_df)
    test_start = int(n * 0.7)
    test_df = result_df.iloc[test_start:]
    
    # 開始時のリターンを1.0にリセット
    test_df['cum_return'] = test_df['cum_return'] / test_df['cum_return'].iloc[0]
    test_df['bnh_return'] = test_df['bnh_return'] / test_df['bnh_return'].iloc[0]
    test_df['peak'] = test_df['cum_return'].cummax()
    test_df['drawdown'] = (test_df['cum_return'] - test_df['peak']) / test_df['peak']
    
    metrics = calculate_metrics(test_df, timeframe_hours=1)
    
    print("\n=== Verification Results (Out-of-Sample) ===")
    for k, v in metrics.items():
        if 'Return' in k or 'Drawdown' in k or 'Rate' in k:
            print(f"{k}: {v*100:.2f}%")
        else:
            print(f"{k}: {v}")
            
    # モックのモデルオブジェクト（Feature Importance描画回避用）
    class MockModel:
        feature_importances_ = np.zeros(5)
    
    plot_path = os.path.join(OUTPUT_DIR, "hypothesis_results.png")
    # plot_resultsはLightGBM用の特徴量重要度を描画しようとするため、簡易プロットを自作する
    fig, axes = plt.subplots(2, 1, figsize=(12, 10))
    axes[0].plot(test_df.index, test_df['cum_return'], label='Hypothesis Strategy')
    axes[0].plot(test_df.index, test_df['bnh_return'], label='Buy & Hold', alpha=0.6)
    axes[0].set_title('Cumulative Return (OOS Simulation)')
    axes[0].legend()
    
    axes[1].plot(test_df.index, test_df['drawdown'], color='red', label='Drawdown')
    axes[1].fill_between(test_df.index, test_df['drawdown'], 0, color='red', alpha=0.3)
    axes[1].set_title('Drawdown')
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig(plot_path)
    print(f"Plot saved to {plot_path}")
    
    # 最後にMarkdownレポートの雛形も書き出す
    report_path = os.path.join(OUTPUT_DIR, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 仮説検証シミュレーション結果\n\n")
        f.write("EDAの観察結果から構築した2段階アーキテクチャ（レジーム判定＋個別アクション）の優位性を検証しました。\n\n")
        f.write("## 評価結果\n")
        for k, v in metrics.items():
            if 'Return' in k or 'Drawdown' in k or 'Rate' in k:
                f.write(f"- **{k}**: {v*100:.2f}%\n")
            else:
                f.write(f"- **{k}**: {v}\n")
        f.write("\n## グラフ\n")
        f.write("![Simulation Results](hypothesis_results.png)\n")
    
if __name__ == "__main__":
    main()
