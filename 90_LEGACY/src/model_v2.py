import numpy as np
import pandas as pd

def detect_regimes(df: pd.DataFrame) -> pd.Series:
    """
    Stage 1: 特徴量から相場のレジームを判定する（仮説検証用のルールベース）
    1: 上昇トレンド, -1: 下降トレンド, 2: レンジ/回帰待ち, 0: その他
    """
    regime = pd.Series(0, index=df.index)
    
    # 使用する代表特徴量
    # FIB_5(8), FIB_8(34), FIB_11(144)
    if 'FIB_5_SMA' not in df.columns:
        return regime
        
    sma_s = df['FIB_5_SMA']
    sma_m = df['FIB_8_SMA']
    sma_l = df['FIB_11_SMA']
    
    slope_s = df['FIB_5_SMA_slope']
    slope_m = df['FIB_8_SMA_slope']
    slope_l = df['FIB_11_SMA_slope']
    
    afs_long = df['AFS_10_19'] # 長期AFS
    
    # 1. 上昇トレンド条件: パーフェクトオーダー + 傾き正 + 長期AFSが高値圏
    uptrend_cond = (sma_s > sma_m) & (sma_m > sma_l) & \
                   (slope_s > 0) & (slope_m > 0) & (slope_l > 0) & \
                   (afs_long > 60)
    
    # -1. 下降トレンド条件: 逆パーフェクトオーダー + 傾き負 + 長期AFSが安値圏
    downtrend_cond = (sma_s < sma_m) & (sma_m < sma_l) & \
                     (slope_s < 0) & (slope_m < 0) & (slope_l < 0) & \
                     (afs_long < 40)
                     
    # 2. レンジ条件: 長期SMAの傾きがほぼフラット、かつAFSが張り付いていない
    # 終値に対する傾きの割合が非常に小さい
    slope_l_pct = slope_l.abs() / df['close']
    range_cond = (slope_l_pct < 0.0001) & (afs_long >= 40) & (afs_long <= 60)
    
    regime[uptrend_cond] = 1
    regime[downtrend_cond] = -1
    regime[range_cond] = 2
    
    return regime

def generate_signals_v2(df: pd.DataFrame) -> pd.Series:
    """
    Stage 2: レジームに応じたアクション（エントリーシグナル）を生成する
    1: Long, -1: Short, 0: No action
    """
    signal = pd.Series(0, index=df.index)
    regime = df['regime']
    
    # --- トレンド用ロジック（押し目買い・戻り売り） ---
    # 上昇トレンド中: 短期stoch_dが一度25を下回り、その後反発したタイミング
    stoch_short = df['FIB_3_stoch_d']
    
    # 前の足で25以下、今の足で25より上（ゴールデンクロス的な動き）
    pullback_long = (regime == 1) & (stoch_short.shift(1) < 25) & (stoch_short >= 25)
    signal[pullback_long] = 1
    
    # 下降トレンド中: 短期stoch_dが一度75を上回り、その後反落したタイミング
    pullback_short = (regime == -1) & (stoch_short.shift(1) > 75) & (stoch_short <= 75)
    signal[pullback_short] = -1
    
    # --- レンジ用ロジック（平均回帰・逆張り） ---
    # レンジ中: 全AFS(AFS_1_19)が極値に達した場合に逆張り
    afs_all = df['AFS_1_19']
    
    # AFSが80を超えたら「買われすぎ」としてショート
    range_short = (regime == 2) & (afs_all > 80)
    signal[range_short] = -1
    
    # AFSが20を下回ったら「売られすぎ」としてロング
    range_long = (regime == 2) & (afs_all < 20)
    signal[range_long] = 1
    
    return signal
