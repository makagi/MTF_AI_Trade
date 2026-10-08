import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from src.config import MAX_FIB_INDEX_1H, BASE_COST, TARGET_HORIZON_1H
from src.data_loader import load_discovery_data
from src.features import calculate_fib_features

OUTPUT_DIR = r"D:\work\AI-Trade\SakanaAISystemTrade\reports\EDA\03_edge_map"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 定数
HORIZONS = [1, 4, 12, 24]
MFE_MAE_WINDOW = 24
COST = 0.001 # 0.1% cost for round trip (entry + exit approximated)

def define_regimes(df: pd.DataFrame) -> pd.DataFrame:
    """レジームを定義（トレンド/レンジ、方向、ボラティリティ等）"""
    # トレンド vs レンジ
    slope_l_pct = df['FIB_11_SMA_slope'].abs() / df['close']
    afs_long = df['AFS_10_19']
    
    # 簡単な分類: トレンド(Trend) / レンジ(Range)
    df['regime_type'] = np.where((slope_l_pct > 0.0001) & ((afs_long > 60) | (afs_long < 40)), 'Trend', 'Range')
    
    # ボラティリティ (14期間ATRの簡易版: 高値-安値の平均等)
    tr = np.maximum(df['high'] - df['low'], 
                    np.maximum(abs(df['high'] - df['close'].shift(1)), 
                               abs(df['low'] - df['close'].shift(1))))
    atr = tr.rolling(14).mean()
    atr_pct = atr / df['close']
    
    # 期間全体の分位で高/中/低を判定
    q33 = atr_pct.quantile(0.33)
    q66 = atr_pct.quantile(0.66)
    
    conditions = [atr_pct <= q33, atr_pct <= q66, atr_pct > q66]
    choices = ['LowVol', 'MidVol', 'HighVol']
    df['regime_vol'] = np.select(conditions, choices, default='MidVol')
    
    df['regime_label'] = df['regime_type'] + "_" + df['regime_vol']
    return df

def define_signals(df: pd.DataFrame) -> dict:
    """各条件（シグナル）をブール系列で返す"""
    signals = {}
    
    # 1. SMA傾き整列 (パーフェクトオーダー)
    signals['SMA_Perfect_Long'] = (df['FIB_5_SMA_slope'] > 0) & (df['FIB_8_SMA_slope'] > 0) & (df['FIB_11_SMA_slope'] > 0)
    signals['SMA_Perfect_Short'] = (df['FIB_5_SMA_slope'] < 0) & (df['FIB_8_SMA_slope'] < 0) & (df['FIB_11_SMA_slope'] < 0)
    
    # 2. 価格 vs 全SMA
    signals['Price_Over_SMA'] = (df['close'] > df['FIB_5_SMA']) & (df['close'] > df['FIB_8_SMA']) & (df['close'] > df['FIB_11_SMA'])
    signals['Price_Under_SMA'] = (df['close'] < df['FIB_5_SMA']) & (df['close'] < df['FIB_8_SMA']) & (df['close'] < df['FIB_11_SMA'])
    
    # 3. stoch_d 上下関係＋反転 (押し目買い・戻り売り)
    signals['Stoch_Pullback_Long'] = (df['FIB_12_stoch_d'] > 60) & (df['FIB_3_stoch_d'].shift(1) < 25) & (df['FIB_3_stoch_d'] >= 25)
    signals['Stoch_Pullback_Short'] = (df['FIB_12_stoch_d'] < 40) & (df['FIB_3_stoch_d'].shift(1) > 75) & (df['FIB_3_stoch_d'] <= 75)
    
    # 4. AFS極値 (エネルギー偏りからの逆張り)
    signals['AFS_Extreme_Long'] = (df['AFS_1_19'] < 20) & (df['AFS_10_19'] < 25)
    signals['AFS_Extreme_Short'] = (df['AFS_1_19'] > 80) & (df['AFS_10_19'] > 75)
    
    # 5. BB反発
    if 'FIB_11_BB_down' in df.columns:
        signals['BB_Reversion_Long'] = (df['low'].shift(1) < df['FIB_11_BB_down'].shift(1)) & (df['close'] > df['FIB_11_BB_down'])
        signals['BB_Reversion_Short'] = (df['high'].shift(1) > df['FIB_11_BB_up'].shift(1)) & (df['close'] < df['FIB_11_BB_up'])
        
    return signals

def calc_forward_returns_and_mfe(df: pd.DataFrame):
    """前向きリターンとMFE/MAEを計算"""
    for h in HORIZONS:
        df[f'fwd_ret_{h}'] = df['close'].shift(-h) / df['close'] - 1.0
        
    # 前向きのローリングウィンドウ (未来W期間の最大・最小)
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=MFE_MAE_WINDOW)
    df['fwd_max_W'] = df['high'].rolling(window=indexer).max()
    df['fwd_min_W'] = df['low'].rolling(window=indexer).min()
    
    return df

def analyze_signals(df: pd.DataFrame, signals: dict):
    """シグナルごとのエッジマップを作成"""
    results = []
    mfe_mae_data = []
    
    for sig_name, sig_series in signals.items():
        is_long = 'Long' in sig_name or 'Over' in sig_name
        direction_mult = 1 if is_long else -1
        
        # シグナル発生時点のインデックス
        events = df[sig_series].copy()
        
        if len(events) == 0:
            continue
            
        # 期間（年単位ブロック）
        events['year'] = events.index.year
        
        for (year, regime), group in events.groupby(['year', 'regime_label']):
            n = len(group)
            if n < 5: # サンプル少なすぎる場合はスキップ
                continue
                
            row = {'Signal': sig_name, 'Year': year, 'Regime': regime, 'N': n}
            
            # 各ホライズンのリターン計算
            for h in HORIZONS:
                raw_ret = group[f'fwd_ret_{h}'] * direction_mult
                net_ret = raw_ret - COST
                
                row[f'Ret_{h}h_Mean'] = net_ret.mean()
                row[f'Ret_{h}h_WinRate'] = (net_ret > 0).mean()
                
            results.append(row)
            
        # 全期間のMFE/MAE保存 (イグジット設計用)
        for idx, event in events.iterrows():
            if pd.isna(event['fwd_max_W']) or pd.isna(event['fwd_min_W']):
                continue
                
            if is_long:
                mfe = event['fwd_max_W'] / event['close'] - 1.0
                mae = event['fwd_min_W'] / event['close'] - 1.0
                actual_ret = event[f'fwd_ret_{MFE_MAE_WINDOW}']
            else:
                mfe = 1.0 - event['fwd_min_W'] / event['close']
                mae = 1.0 - event['fwd_max_W'] / event['close']
                actual_ret = -event[f'fwd_ret_{MFE_MAE_WINDOW}']
                
            mfe_mae_data.append({
                'Signal': sig_name,
                'MFE': mfe,
                'MAE': mae, # MAE is usually negative or 0 for long. For short, if fwd_max > close, mae is negative.
                'FinalRet': actual_ret - COST
            })
            
    res_df = pd.DataFrame(results)
    mfe_df = pd.DataFrame(mfe_mae_data)
    return res_df, mfe_df

def plot_edge_heatmap(res_df: pd.DataFrame):
    if res_df.empty:
        return
        
    # 条件 × レジーム の期待値(24h)ヒートマップ
    pivot = res_df.pivot_table(index='Signal', columns='Regime', values='Ret_24h_Mean', aggfunc='mean')
    
    plt.figure(figsize=(12, 8))
    sns.heatmap(pivot * 100, annot=True, cmap='coolwarm', center=0, fmt='.2f')
    plt.title('Edge Heatmap: Net Return (24h, %) by Signal & Regime')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'edge_heatmap.png'))
    plt.close()
    
def plot_consistency(res_df: pd.DataFrame):
    if res_df.empty:
        return
        
    # 条件ごとの時期別推移
    pivot = res_df.pivot_table(index='Year', columns='Signal', values='Ret_24h_Mean', aggfunc='mean')
    
    plt.figure(figsize=(14, 8))
    for col in pivot.columns:
        plt.plot(pivot.index, pivot[col] * 100, marker='o', label=col)
    
    plt.axhline(0, color='black', linestyle='--')
    plt.title('Consistency over Years: Net Return (24h, %)')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'consistency.png'))
    plt.close()

def plot_mfe_mae(mfe_df: pd.DataFrame):
    if mfe_df.empty:
        return
        
    # 主要条件のMFE-MAE散布図 (勝ち負け別)
    top_signals = mfe_df['Signal'].value_counts().head(4).index
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    for i, sig in enumerate(top_signals):
        sub = mfe_df[mfe_df['Signal'] == sig].copy()
        sub['IsWin'] = sub['FinalRet'] > 0
        
        sns.scatterplot(data=sub, x='MAE', y='MFE', hue='IsWin', alpha=0.5, ax=axes[i])
        axes[i].set_title(f"MFE/MAE Scatter: {sig}")
        axes[i].axvline(0, color='gray', linestyle='--')
        axes[i].axhline(0, color='gray', linestyle='--')
        
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'mfe_mae_scatter.png'))
    plt.close()

def generate_report(res_df: pd.DataFrame):
    # 簡単な自動評価
    if not res_df.empty:
        overall = res_df.groupby('Signal')[['Ret_4h_Mean', 'Ret_24h_Mean', 'Ret_24h_WinRate']].mean()
        best_sig = overall.sort_values('Ret_24h_Mean', ascending=False).head(3)
    else:
        best_sig = pd.DataFrame()
        
    report_path = os.path.join(OUTPUT_DIR, 'report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# EDA第3弾：条件別エッジマップ＆MFE/MAE分析\n\n")
        f.write("## 憲法確認\n")
        f.write("第4章「観察と検証の規律」に基づき、目視ではなく定量的な前向きリターン（イグジット非依存）を用いてエントリーのエッジを評価しました。また、2024年以降のデータは最終ホールドアウトとして封印（本集計から除外）しています。\n\n")
        
        f.write("## 1. 上位エッジ条件（全期間平均）\n")
        f.write(best_sig.to_markdown() + "\n\n")
        
        f.write("## 2. 非定常の検証（一貫性とレジーム依存性）\n")
        f.write("画像 `edge_heatmap.png` および `consistency.png` を参照。\n")
        f.write("- レジームヒートマップより、どの相場環境で特定のシグナルが機能するかが確認できます。\n")
        f.write("- 時期別グラフより、そのエッジが一時的なものか、一貫して効いているかが確認できます。\n\n")
        
        f.write("## 3. MFE/MAE分析とイグジットの示唆\n")
        f.write("画像 `mfe_mae_scatter.png` を参照。\n")
        f.write("- MAE（最大逆行）の分布から、合理的な損切りライン（例：大半の勝ちトレードが耐えきった水準）を特定する手がかりが得られます。\n\n")
        
        f.write("## 次アクション\n")
        f.write("本定量結果をもとに、安定したプラス期待値と一貫性を示す「エッジ」を厳選し、MFE/MAEから導かれるイグジットロジックを付与したモデル（v3）の構築に進みます。\n")

def main():
    print("Loading data...")
    df_1h = load_discovery_data()
    
    # 最終ホールドアウトの封印 (2024-01-01 以降は見ない)
    # ユーザー指示: 一度も触れない最終ホールドアウトを封印する
    
    print(f"Data period (Holdout sealed): {df_1h.index[0]} to {df_1h.index[-1]}")
    
    print("Calculating features...")
    df_features = calculate_fib_features(df_1h, MAX_FIB_INDEX_1H)
    
    print("Preparing Regimes, Returns and MFE/MAE...")
    df_features = define_regimes(df_features)
    df_features = calc_forward_returns_and_mfe(df_features)
    
    print("Defining Signals...")
    signals = define_signals(df_features)
    
    print("Analyzing Signals...")
    res_df, mfe_df = analyze_signals(df_features, signals)
    
    print("Generating Outputs...")
    res_df.to_csv(os.path.join(OUTPUT_DIR, 'edge_map_summary.csv'), index=False)
    mfe_df.to_csv(os.path.join(OUTPUT_DIR, 'mfe_mae_raw.csv'), index=False)
    
    plot_edge_heatmap(res_df)
    plot_consistency(res_df)
    plot_mfe_mae(mfe_df)
    
    generate_report(res_df)
    print("Edge map EDA completed successfully.")

if __name__ == "__main__":
    main()
