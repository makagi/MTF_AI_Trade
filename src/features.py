"""
特徴量計算モジュール (Feature Engineering Module)
SPEC-FEAT-001 (02_SPECIFICATIONS/features.md) に準拠したMTF特徴量計算関数群。
"""

from typing import List, Optional, Tuple
import numpy as np
import pandas as pd


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """単純移動平均 (SMA) を計算する。"""
    return series.rolling(window=period, min_periods=period).mean()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """True Range (TR) および Average True Range (ATR) を計算する。"""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def calculate_bollinger_bands(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    ボリンジャーバンド (Upper, Middle, Lower) を計算する。
    """
    mid = series.rolling(window=period, min_periods=period).mean()
    std = series.rolling(window=period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def calculate_elasticity_index(
    df: pd.DataFrame,
    cluster_periods: Optional[List[int]] = None,
    anchor_period: int = 377,
    eps: float = 1e-8,
) -> pd.Series:
    """
    ゴムパッチン指数 (Elasticity Index) を計算する (SPEC-FEAT-001 §4.1)。
    Cluster_Width = (max(SMA_k) - min(SMA_k)) / Close
    Magnet_Distance = |SMA_anchor - mean(SMA_k)| / Close
    Elasticity_Index = Magnet_Distance / (Cluster_Width + eps)
    """
    if cluster_periods is None:
        cluster_periods = [21, 55, 89]

    close = df["close"]
    smas = [calculate_sma(close, p) for p in cluster_periods]
    sma_cluster_df = pd.concat(smas, axis=1)

    cluster_max = sma_cluster_df.max(axis=1)
    cluster_min = sma_cluster_df.min(axis=1)
    cluster_mean = sma_cluster_df.mean(axis=1)

    cluster_width = (cluster_max - cluster_min) / close
    anchor_sma = calculate_sma(close, anchor_period)
    magnet_distance = (anchor_sma - cluster_mean).abs() / close

    return magnet_distance / (cluster_width + eps)


def calculate_squeeze_index(
    df: pd.DataFrame,
    periods: Optional[List[int]] = None,
    lookback_bars: int = 720,  # 30 days * 24 hours
    eps: float = 1e-8,
) -> pd.Series:
    """
    Squeeze Index (MTF ボラティリティ圧縮) を計算する (SPEC-FEAT-001 §4.2)。
    Total_BB_Width = sum((Upper_k - Lower_k) / Close)
    Squeeze_Index = (Total_BB_Width - min_30d) / (max_30d - min_30d + eps)
    """
    if periods is None:
        periods = [21, 55, 144, 377]

    close = df["close"]
    bb_widths = []
    for p in periods:
        up, _, low = calculate_bollinger_bands(close, period=p)
        rel_width = (up - low) / close
        bb_widths.append(rel_width)

    total_width = pd.concat(bb_widths, axis=1).sum(axis=1)
    min_width = total_width.rolling(window=lookback_bars, min_periods=lookback_bars // 2).min()
    max_width = total_width.rolling(window=lookback_bars, min_periods=lookback_bars // 2).max()

    return (total_width - min_width) / (max_width - min_width + eps)


def calculate_afs(
    df: pd.DataFrame,
    periods: Optional[List[int]] = None,
    eps: float = 1e-8,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    AFS (Average Fibonacci Stochastics) を計算する (SPEC-FEAT-001 §4.3)。
    K(p) = (Close - min_p(Low)) / (max_p(High) - min_p(Low) + eps) * 100
    AFS(p) = SMA(K(p), p)
    戻り値: (afs_df, order_score, compression_variance)
    """
    if periods is None:
        periods = [7, 9, 11, 13]

    close = df["close"]
    high = df["high"]
    low = df["low"]

    afs_dict = {}
    for p in periods:
        lowest_low = low.rolling(window=p, min_periods=p).min()
        highest_high = high.rolling(window=p, min_periods=p).max()
        k_line = ((close - lowest_low) / (highest_high - lowest_low + eps)) * 100
        afs = k_line.rolling(window=p, min_periods=p).mean()
        afs_dict[f"AFS_{p}"] = afs

    afs_df = pd.DataFrame(afs_dict, index=df.index)

    # Order Score (3段比較)
    order_score = pd.Series(0, index=df.index, dtype=int)
    for i in range(len(periods) - 1):
        p1 = periods[i]
        p2 = periods[i + 1]
        order_score += (afs_df[f"AFS_{p1}"] > afs_df[f"AFS_{p2}"]).astype(int)

    # Compression (Variance)
    compression = afs_df.var(axis=1)

    return afs_df, order_score, compression


def calculate_topology(
    df: pd.DataFrame,
    atr_period: int = 14,
    eps: float = 1e-8,
) -> Tuple[pd.Series, pd.Series]:
    """
    空間トポロジー (Sandwich Ratio & Wall Density) を計算する (SPEC-FEAT-001 §4.4)。
    """
    close = df["close"]
    atr = calculate_atr(df, period=atr_period)

    levels_list = []
    for p in [144, 377]:
        sma = calculate_sma(close, p)
        up, _, low = calculate_bollinger_bands(close, period=p)
        levels_list.extend([sma, up, low])

    levels_df = pd.concat(levels_list, axis=1)

    sandwich_ratios = []
    wall_densities = []

    for t, c in close.items():
        if pd.isna(c) or t not in levels_df.index:
            sandwich_ratios.append(np.nan)
            wall_densities.append(np.nan)
            continue

        row_levels = levels_df.loc[t].dropna().values
        if len(row_levels) == 0:
            sandwich_ratios.append(np.nan)
            wall_densities.append(np.nan)
            continue

        ceilings = [l for l in row_levels if l > c]
        floors = [l for l in row_levels if l < c]

        ceiling = min(ceilings) if ceilings else c * 1.10
        floor = max(floors) if floors else c * 0.90

        s_ratio = (c - floor) / (ceiling - floor + eps)
        current_atr = atr.loc[t] if not pd.isna(atr.loc[t]) else c * 0.01
        density = sum(1 for l in row_levels if (c - 0.5 * current_atr) <= l <= c)

        sandwich_ratios.append(s_ratio)
        wall_densities.append(density)

    return (
        pd.Series(sandwich_ratios, index=df.index, name="Sandwich_Ratio"),
        pd.Series(wall_densities, index=df.index, name="Wall_Density"),
    )


def calculate_fanout_velocity(
    df: pd.DataFrame,
    fast_period: int = 21,
    slow_period: int = 89,
    atr_period: int = 14,
    eps: float = 1e-8,
) -> pd.Series:
    """
    ATR正規化ファンアウト速度 (Fan-out Velocity) を計算する (SPEC-FEAT-001 §4.5)。
    Velocity = diff(SMA_fast - SMA_slow) / (ATR + eps)
    """
    close = df["close"]
    fast_sma = calculate_sma(close, fast_period)
    slow_sma = calculate_sma(close, slow_period)
    diff = (fast_sma - slow_sma).diff()
    atr = calculate_atr(df, period=atr_period)
    return diff / (atr + eps)
