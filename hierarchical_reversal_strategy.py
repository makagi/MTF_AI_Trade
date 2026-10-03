import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from src.data_loader import load_1h_data, DISCOVERY_START, DISCOVERY_END
from src.features import calculate_fib_features
from src.config import MAX_FIB_INDEX_1H, BASE_COST

TARGET_HORIZON_1H = 6

def define_hierarchical_states(df: pd.DataFrame, k_long: int, k_short: int) -> pd.DataFrame:
    """
    ユーザー仮説に基づく「フィボナッチ階層構造の動的状況判定」
    k_longとその前後(k_long-1, k_long+1)を用いて長期の「反転待ち状態」を特定し、
    k_shortを用いて「短期トリガー」を判定する。
    """
    df = df.copy()
    
    # プレフィックスの定義
    kl_m1 = f"FIB_{k_long - 1}_"
    kl    = f"FIB_{k_long}_"
    kl_p1 = f"FIB_{k_long + 1}_"
    ks    = f"FIB_{k_short}_"
    
    # 必須カラムのチェック
    required_cols = [f"{kl_p1}SMA_slope", f"{kl}stoch_d", f"{ks}stoch_d", f"{kl_p1}BB_down", f"{kl_p1}BB_up"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column missing: {col}")

    # =========================================================================
    # 1. 長期の状況判定 (Long-term Context)
    # =========================================================================
    
    # --- 押し目買い/底打ちの「上昇反転待ち (Waiting for Pullback Reversal)」 ---
    # 条件:
    # - 大局(k+1)は上向きである (SMA_slope > 0)
    # - しかし、現在(k)のオシレーターは売られすぎ圏にある (stoch_d < 25) 
    # - 価格が強力なサポート（k+1のSMAやBB_down）に接近している (close <= kl_SMA または BB_posが0付近)
    
    df['LT_Uptrend'] = df[f'{kl_p1}SMA_slope'] > 0
    df['LT_Downtrend'] = df[f'{kl_p1}SMA_slope'] < 0
    
    # サポートへの接近 (k+1のBB_posが0.2以下、つまり下限に近い)
    # BB_pos = (close - BB_down) / (BB_up - BB_down)
    df['LT_Near_Support'] = df[f'{kl_p1}BB_pos'] < 0.2
    df['LT_Near_Resistance'] = df[f'{kl_p1}BB_pos'] > 0.8
    
    # 反転待ち状態フラグ
    df['LT_Wait_Long'] = df['LT_Uptrend'] & (df[f'{kl}stoch_d'] < 30) & df['LT_Near_Support']
    df['LT_Wait_Short'] = df['LT_Downtrend'] & (df[f'{kl}stoch_d'] > 70) & df['LT_Near_Resistance']
    
    # =========================================================================
    # 2. 短期の反転トリガー (Short-term Trigger)
    # =========================================================================
    
    # 短期トリガー（Long）: 短期のStoch_dが売られすぎから上抜け（ゴールデンクロス）
    # または短期のSMAが上向きに転換
    df['ST_Trigger_Long'] = (df[f'{ks}stoch_d'].shift(1) < 20) & (df[f'{ks}stoch_d'] >= 20)
    
    # 短期トリガー（Short）: 短期のStoch_dが買われすぎから下抜け（デッドクロス）
    df['ST_Trigger_Short'] = (df[f'{ks}stoch_d'].shift(1) > 80) & (df[f'{ks}stoch_d'] <= 80)
    
    # =========================================================================
    # 3. 複合シグナルの生成 (Combined Signal)
    # =========================================================================
    df['Signal_Long'] = df['LT_Wait_Long'] & df['ST_Trigger_Long']
    df['Signal_Short'] = df['LT_Wait_Short'] & df['ST_Trigger_Short']
    
    return df

def run_analysis(k_long=11, k_short=5):
    """ k_long=11(144), k_short=5(8) で検証 """
    print(f"Loading data and calculating features (k_long={k_long}, k_short={k_short})...")
    df = load_1h_data(include_holdout=False)
    df = df.loc[DISCOVERY_START:DISCOVERY_END].copy()
    
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df['target_return'] = df['close'].shift(-TARGET_HORIZON_1H) / df['close'] - 1
    
    # ロジックの適用
    df = define_hierarchical_states(df, k_long, k_short)
    
    # 分析
    long_events = df[df['Signal_Long']]
    short_events = df[df['Signal_Short']]
    
    print("\n--- Event Statistics ---")
    print(f"Total Bars: {len(df)}")
    print(f"LT Wait Long occurrences: {df['LT_Wait_Long'].sum()}")
    print(f"LT Wait Short occurrences: {df['LT_Wait_Short'].sum()}")
    print(f"Combined Long Events (LT Wait + ST Trigger): {len(long_events)}")
    print(f"Combined Short Events (LT Wait + ST Trigger): {len(short_events)}")
    
    # リターン分布の比較
    base_mean = df['target_return'].mean()
    long_mean = long_events['target_return'].mean() if len(long_events) > 0 else np.nan
    short_mean = short_events['target_return'].mean() if len(short_events) > 0 else np.nan
    
    # コスト控除後の期待値
    long_net = long_mean - BASE_COST if not np.isnan(long_mean) else np.nan
    short_net = -short_mean - BASE_COST if not np.isnan(short_mean) else np.nan
    
    print("\n--- Return Analysis (6h Horizon) ---")
    print(f"Baseline Mean Return: {base_mean:.4%}")
    print(f"Long Events Gross Mean: {long_mean:.4%} | Net (After {BASE_COST:.2%} cost): {long_net:.4%}")
    print(f"Short Events Gross Mean: {short_mean:.4%} | Net (After {BASE_COST:.2%} cost): {short_net:.4%}")
    
    # 勝率 (コスト考慮後)
    long_win_rate = (long_events['target_return'] > BASE_COST).mean() if len(long_events) > 0 else 0
    short_win_rate = (short_events['target_return'] < -BASE_COST).mean() if len(short_events) > 0 else 0
    print(f"Long Net Win Rate: {long_win_rate:.2%}")
    print(f"Short Net Win Rate: {short_win_rate:.2%}")
    
    # 可視化
    os.makedirs("results", exist_ok=True)
    plt.figure(figsize=(10, 6))
    
    # ベースラインの分布
    sns.kdeplot(df['target_return'].dropna(), label='Baseline', color='gray', alpha=0.5)
    
    # Longイベントの分布
    if len(long_events) > 1:
        sns.kdeplot(long_events['target_return'].dropna(), label='Long Signals', color='green', linewidth=2)
        plt.axvline(long_events['target_return'].mean(), color='green', linestyle='--')
        
    # Shortイベントの分布（符号反転して比較しやすくする）
    if len(short_events) > 1:
        sns.kdeplot(-short_events['target_return'].dropna(), label='Short Signals (Inverted)', color='red', linewidth=2)
        plt.axvline(-short_events['target_return'].mean(), color='red', linestyle='--')
        
    plt.axvline(BASE_COST, color='black', linestyle=':', label='Breakeven (Cost)')
    plt.title(f"Return Distribution: Hierarchical Reversal Logic (k_long={k_long}, k_short={k_short})")
    plt.xlabel(f"Forward {TARGET_HORIZON_1H}h Return")
    plt.xlim(-0.05, 0.05)
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig("results/hierarchical_reversal_dist.png")
    print("\nSaved results/hierarchical_reversal_dist.png")

if __name__ == "__main__":
    # k_long=11 (144期間), k_short=5 (8期間)
    run_analysis(11, 5)
    
    # 別パターンの検証 (中期の押し目)
    # k_long=8 (34期間), k_short=3 (3期間)
    # print("\n=============================================")
    # run_analysis(8, 3)
