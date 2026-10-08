import numpy as np
import pandas as pd
from src.config import FIBONACCI_SERIES

def calculate_sma(df: pd.DataFrame, column: str, period: int) -> pd.Series:
    # min_periodsを設定して、データ初期からある程度値が出るようにする
    return df[column].rolling(window=period, min_periods=max(1, period//4)).mean()

def calculate_std(df: pd.DataFrame, column: str, period: int) -> pd.Series:
    return df[column].rolling(window=period, min_periods=max(1, period//4)).std()

def calculate_stoch_k(df: pd.DataFrame, kperiod: int) -> pd.Series:
    lowest_low = df['low'].rolling(window=kperiod, min_periods=max(1, kperiod//4)).min()
    highest_high = df['high'].rolling(window=kperiod, min_periods=max(1, kperiod//4)).max()
    
    # 防止0除算
    denom = highest_high - lowest_low
    denom = denom.replace(0, np.nan)
    stoch_k = 100 * ((df['close'] - lowest_low) / denom)
    return stoch_k

def calculate_fib_features(df: pd.DataFrame, max_fib_index: int) -> pd.DataFrame:
    """
    データフレームに対してフィボナッチ項ベースの特徴量を追加して返す。
    max_fib_index: 適用するフィボナッチ項の最大インデックス (1-indexed)
    """
    print(f"Calculating Fibonacci features up to index {max_fib_index} (period {FIBONACCI_SERIES[max_fib_index-1]})...")
    df = df.copy()
    fib_series = FIBONACCI_SERIES[:max_fib_index]
    
    stoch_d_dict = {}
    
    for i, period in enumerate(fib_series):
        idx = i + 1  # 1-indexed (k)
        prefix = f"FIB_{idx}_"
        
        # SMA
        sma = calculate_sma(df, 'close', period)
        df[prefix + 'SMA'] = sma
        df[prefix + 'SMA_slope'] = sma.diff()
        df[prefix + 'SMA_dist'] = (df['close'] - sma) / sma
        
        # Bollinger Bands (2 period or more)
        if period >= 2:
            std = calculate_std(df, 'close', period)
            bb_up = sma + 2 * std
            bb_down = sma - 2 * std
            df[prefix + 'BB_up'] = bb_up
            df[prefix + 'BB_down'] = bb_down
            # 相対位置: 0なら下限、1なら上限
            bb_width = 4 * std
            bb_width = bb_width.replace(0, np.nan)
            df[prefix + 'BB_pos'] = (df['close'] - bb_down) / bb_width
            
        # Stochastic %D
        # ユーザー定義: stoch(kperiod=x, dperiod=x)%D 
        stoch_k = calculate_stoch_k(df, period)
        stoch_d = stoch_k.rolling(window=period, min_periods=max(1, period//4)).mean()
        df[prefix + 'stoch_d'] = stoch_d
        df[prefix + 'stoch_d_slope'] = stoch_d.diff()
        
        # AFS計算用に保存
        stoch_d_dict[idx] = stoch_d

    print("Calculating AFS (Average Fibonacci Stoch_d)...")
    # AFS (Average Fibonacci Stoch_d)
    # AFS(n, max_idx) = ave_fib_stoch_d(n, max_idx)
    # kがnからmax_idxまでのfib_stoch_dの平均
    for n in range(1, max_fib_index + 1):
        stoch_d_list = [stoch_d_dict[k] for k in range(n, max_fib_index + 1)]
        if stoch_d_list:
            afs = pd.concat(stoch_d_list, axis=1).mean(axis=1)
            df[f'AFS_{n}_{max_fib_index}'] = afs
            df[f'AFS_{n}_{max_fib_index}_slope'] = afs.diff()
            
    # メモリ節約と学習安定化のため、float64をfloat32に変換
    float_cols = df.select_dtypes(include=['float64']).columns
    df[float_cols] = df[float_cols].astype('float32')
            
    print("Feature calculation completed.")
    return df

def calculate_diverse_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    OHLCVデータから多様な特徴量（ボラティリティ、モメンタム、時間等）を計算して追加する。
    """
    df = df.copy()
    
    # --- ボラティリティ系 ---
    # 1. ATR (Average True Range) - period=14
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14, min_periods=1).mean()
    df['ATR_ratio'] = df['ATR_14'] / df['close']  # 正規化ATR
    
    # 2. Historical Volatility (過去24時間の対数収益率の標準偏差)
    log_ret = np.log(df['close'] / df['close'].shift(1))
    df['HV_24'] = log_ret.rolling(window=24, min_periods=1).std() * np.sqrt(24 * 365) # 年率換算
    
    # 3. Bollinger Band Width (20期間, 2σ)
    sma_20 = df['close'].rolling(window=20, min_periods=1).mean()
    std_20 = df['close'].rolling(window=20, min_periods=1).std()
    df['BB_width_20'] = (4 * std_20) / sma_20

    # --- モメンタム系 ---
    # 1. RSI (Relative Strength Index) - period=14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    df['RSI_14'] = df['RSI_14'].fillna(50) # 最初の方のNaN埋め
    
    # 2. MACD (12, 26, 9)
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD_line'] = ema_12 - ema_26
    df['MACD_signal'] = df['MACD_line'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD_line'] - df['MACD_signal']

    # --- 出来高系 ---
    if 'volume' in df.columns:
        # OBV
        direction = np.sign(df['close'].diff()).fillna(0)
        df['OBV'] = (direction * df['volume']).cumsum()
        
        # Volume Change Rate (24h)
        vol_sma_24 = df['volume'].rolling(window=24, min_periods=1).mean()
        df['Volume_ratio'] = df['volume'] / vol_sma_24.replace(0, np.nan)
    else:
        print("Warning: 'volume' column not found. Skipping volume-based features.")

    # --- 時間系 ---
    # IndexがDatetimeIndexであることを前提
    if isinstance(df.index, pd.DatetimeIndex):
        df['hour_of_day'] = df.index.hour
        df['day_of_week'] = df.index.dayofweek
    elif 'DateTime' in df.columns and pd.api.types.is_datetime64_any_dtype(df['DateTime']):
        df['hour_of_day'] = df['DateTime'].dt.hour
        df['day_of_week'] = df['DateTime'].dt.dayofweek
        
    return df
