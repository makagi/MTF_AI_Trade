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
    eff_atr = atr.fillna(close * 0.01)

    levels_list = []
    for p in [144, 377]:
        sma = calculate_sma(close, p)
        up, _, low = calculate_bollinger_bands(close, period=p)
        levels_list.extend([sma, up, low])

    levels_df = pd.concat(levels_list, axis=1)

    # Vectorized computation for performance and precision
    ceilings = levels_df.where(levels_df.gt(close, axis=0))
    floors = levels_df.where(levels_df.lt(close, axis=0))

    ceiling = ceilings.min(axis=1).fillna(close * 1.10)
    floor = floors.max(axis=1).fillna(close * 0.90)

    sandwich_ratio = (close - floor) / (ceiling - floor + eps)
    sandwich_ratio.name = "Sandwich_Ratio"

    # Wall Density: count of levels in [Close - 0.5 * ATR, Close]
    in_wall = levels_df.ge(close - 0.5 * eff_atr, axis=0) & levels_df.le(close, axis=0)
    wall_density = in_wall.sum(axis=1).astype(int)
    wall_density.name = "Wall_Density"

    # Preserve NaN for indices where close was NaN
    sandwich_ratio[close.isna()] = np.nan
    wall_density[close.isna()] = 0

    return sandwich_ratio, wall_density


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


def calculate_void_distance(
    df: pd.DataFrame,
    overhead_periods: Optional[List[int]] = None,
    atr_period: int = 14,
    eps: float = 1e-8,
) -> pd.Series:
    """
    真空地帯 (The Void Filter) を計算する (SPEC-FEAT-001 §4.6)。
    Overhead_SMA = min({SMA_k | SMA_k > Close} ∪ {Close * 1.20})
    Void_Distance = (Overhead_SMA - Close) / (ATR + eps)
    """
    if overhead_periods is None:
        overhead_periods = [55, 89, 144, 377]

    close = df["close"]
    atr = calculate_atr(df, period=atr_period)
    eff_atr = atr.fillna(close * 0.01)

    smas = [calculate_sma(close, p) for p in overhead_periods]
    smas_df = pd.concat(smas, axis=1)

    overheads = smas_df.where(smas_df.gt(close, axis=0))
    overhead_sma = overheads.min(axis=1).fillna(close * 1.20)

    void_dist = (overhead_sma - close) / (eff_atr + eps)
    void_dist.name = "Void_Distance"
    void_dist[close.isna()] = np.nan
    return void_dist


def calculate_regime_age(
    df: pd.DataFrame,
    macro_periods: Tuple[int, int, int] = (233, 377, 610),
    meso_periods: Tuple[int, int, int] = (34, 55, 89),
    micro_periods: Tuple[int, int, int] = (8, 13, 21),
    median_durations: Optional[dict] = None,
) -> pd.DataFrame:
    """
    時間成熟度 (Regime Age & Wave Maturity) を計算する (HYP-CTX-1 / K-027 準拠)。
    直近のレジーム転換からの経過バー数 (Age Bars) および持続時間中央値に対する比率 (Age Ratio) を算出する。
    """
    if median_durations is None:
        # K-027 empirical medians (hours)
        median_durations = {"macro": 78.5, "meso": 21.0, "micro": 6.0}

    close = df["close"]

    # 1. Macro Regime
    ma1 = calculate_sma(close, macro_periods[0])
    ma2 = calculate_sma(close, macro_periods[1])
    ma3 = calculate_sma(close, macro_periods[2])
    macro_slope = ma2.diff(3)
    macro_bull = (ma1 > ma2) & (ma2 > ma3) & (macro_slope > 0)
    macro_bear = (ma1 < ma2) & (ma2 < ma3) & (macro_slope < 0)
    macro_regime = pd.Series(
        np.where(macro_bull, "Bull", np.where(macro_bear, "Bear", "Range")),
        index=df.index,
    )

    # 2. Meso Regime
    me1 = calculate_sma(close, meso_periods[0])
    me2 = calculate_sma(close, meso_periods[1])
    me3 = calculate_sma(close, meso_periods[2])
    meso_slope = me2.diff(3)
    meso_bull = (me1 > me2) & (me2 > me3) & (meso_slope > 0)
    meso_bear = (me1 < me2) & (me2 < me3) & (meso_slope < 0)
    meso_regime = pd.Series(
        np.where(meso_bull, "Bull", np.where(meso_bear, "Bear", "Range")),
        index=df.index,
    )

    # 3. Micro Regime
    mi1 = calculate_sma(close, micro_periods[0])
    mi2 = calculate_sma(close, micro_periods[1])
    mi3 = calculate_sma(close, micro_periods[2])
    micro_bull = (mi1 > mi2) & (mi2 > mi3)
    micro_bear = (mi1 < mi2) & (mi2 < mi3)
    micro_regime = pd.Series(
        np.where(micro_bull, "Bull", np.where(micro_bear, "Bear", "Range")),
        index=df.index,
    )

    # Compute elapsed bars and age ratios
    def _compute_age(regime_series: pd.Series, median_dur: float):
        change = (regime_series != regime_series.shift(1)).astype(int)
        run_id = change.cumsum()
        age_bars = df.groupby(run_id).cumcount() + 1
        age_ratio = age_bars / median_dur
        return age_bars, age_ratio

    macro_age_bars, macro_age_ratio = _compute_age(
        macro_regime, median_durations.get("macro", 78.5)
    )
    meso_age_bars, meso_age_ratio = _compute_age(
        meso_regime, median_durations.get("meso", 21.0)
    )
    micro_age_bars, micro_age_ratio = _compute_age(
        micro_regime, median_durations.get("micro", 6.0)
    )

    result = pd.DataFrame(
        {
            "macro_regime": macro_regime,
            "macro_age_bars": macro_age_bars,
            "macro_age_ratio": macro_age_ratio,
            "meso_regime": meso_regime,
            "meso_age_bars": meso_age_bars,
            "meso_age_ratio": meso_age_ratio,
            "micro_regime": micro_regime,
            "micro_age_bars": micro_age_bars,
            "micro_age_ratio": micro_age_ratio,
        },
        index=df.index,
    )
    return result


def calculate_level_test_count(
    df: pd.DataFrame,
    level: pd.Series,
    window_bars: int = 72,
    tolerance_atr: float = 0.5,
    atr_series: Optional[pd.Series] = None,
) -> pd.Series:
    """
    動的サポレジ水準に対するアタック回数 (Level Test Count) を計算する (CONC-STR-001 §2 / HYP-CTX-2)。
    高値・安値が水準の許容バンド (level ± tolerance_atr * ATR) に接触した別個のエピソードを検出し、
    過去 window_bars 期間内の累計アタック回数を集計する。
    連続して接触しているバーは1回のエピソードとして扱う。
    """
    high = df["high"]
    low = df["low"]
    if atr_series is None:
        atr_series = calculate_atr(df, 14)
    eff_atr = atr_series.fillna(df["close"] * 0.01)

    upper_band = level + tolerance_atr * eff_atr
    lower_band = level - tolerance_atr * eff_atr

    # Contact occurs if bar intersects [lower_band, upper_band]
    is_touch = (high >= lower_band) & (low <= upper_band) & (~level.isna())

    # Episode start is a touch not preceded by a touch on the previous bar
    touch_start = is_touch & (~is_touch.shift(1).fillna(False))

    # Rolling count of distinct test episodes in past window_bars
    test_count = touch_start.rolling(window=window_bars, min_periods=1).sum().astype(int)
    test_count.name = "Level_Test_Count"
    return test_count
