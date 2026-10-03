import numpy as np
import pandas as pd

def apply_binary_barrier(
    closes: np.ndarray, 
    highs: np.ndarray,
    lows: np.ndarray,
    atrs: np.ndarray, 
    pt_mul: float, 
    sl_mul: float, 
    time_barrier_periods: int,
    direction: int
):
    """
    Numpy-based binary barrier loop for Long-only (1) or Short-only (-1).
    Returns 1 if Take Profit is hit first, 0 if Stop Loss or Timeout.
    """
    n = len(closes)
    labels = np.zeros(n, dtype=int)
    returns = np.zeros(n, dtype=float)
    hit_times = np.zeros(n, dtype=int)
    
    for i in range(n):
        p0 = closes[i]
        if np.isnan(p0) or np.isnan(atrs[i]):
            labels[i] = 0
            continue
            
        if direction == 1:
            tp_price = p0 + atrs[i] * pt_mul
            sl_price = p0 - atrs[i] * sl_mul
        else:
            tp_price = p0 - atrs[i] * pt_mul
            sl_price = p0 + atrs[i] * sl_mul
        
        end_idx = min(i + time_barrier_periods, n - 1)
        
        hit = 0
        ret = 0.0
        hit_j = end_idx
        
        for j in range(i + 1, end_idx + 1):
            h = highs[j]
            l = lows[j]
            
            if direction == 1:
                hit_tp = h >= tp_price
                hit_sl = l <= sl_price
                
                if hit_tp and hit_sl:
                    hit = 0 # Pessimistic: SL hit first
                    ret = (sl_price / p0) - 1.0
                    hit_j = j
                    break
                elif hit_sl:
                    hit = 0
                    ret = (sl_price / p0) - 1.0
                    hit_j = j
                    break
                elif hit_tp:
                    hit = 1
                    ret = (tp_price / p0) - 1.0
                    hit_j = j
                    break
            else: # direction == -1 (Short)
                hit_tp = l <= tp_price
                hit_sl = h >= sl_price
                
                if hit_tp and hit_sl:
                    hit = 0 # Pessimistic: SL hit first
                    ret = (p0 / sl_price) - 1.0 # Short return
                    hit_j = j
                    break
                elif hit_sl:
                    hit = 0
                    ret = (p0 / sl_price) - 1.0
                    hit_j = j
                    break
                elif hit_tp:
                    hit = 1
                    ret = (p0 / tp_price) - 1.0
                    hit_j = j
                    break
                
        if hit == 0 and hit_j == end_idx:
            # Timeout
            if direction == 1:
                ret = (closes[end_idx] / p0) - 1.0
            else:
                ret = (p0 / closes[end_idx]) - 1.0
            
        labels[i] = hit
        returns[i] = ret
        hit_times[i] = hit_j - i
        
    return labels, returns, hit_times

def get_binary_barrier_labels(
    df: pd.DataFrame, 
    pt_sl_ratio: list, 
    time_barrier: int,
    direction: str = 'long',
    atr_col: str = 'ATR_14'
) -> pd.DataFrame:
    """
    DataFrameラッパー for Binary Classification
    direction: 'long' or 'short'
    pt_sl_ratio: [TP_ATR_Multiplier, SL_ATR_Multiplier] (e.g. [2.5, 1.0])
    Returns label=1 for Win (Hit TP), 0 for Loss/Timeout
    """
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    atrs = df[atr_col].values
    
    pt_mul = pt_sl_ratio[0]
    sl_mul = pt_sl_ratio[1]
    dir_int = 1 if direction == 'long' else -1
    
    labels, returns, hit_times = apply_binary_barrier(
        closes, highs, lows, atrs, pt_mul, sl_mul, time_barrier, dir_int
    )
    
    out_df = pd.DataFrame(index=df.index)
    out_df['label'] = labels
    out_df['tb_return'] = returns
    out_df['hit_period'] = hit_times
    
    return out_df

if __name__ == "__main__":
    from src.data_loader import load_1h_data
    from src.features import calculate_diverse_features
    print("Testing Binary Barrier Method...")
    df = load_1h_data().head(1000)
    df = calculate_diverse_features(df)
    df.dropna(subset=['ATR_14'], inplace=True)
    
    print("--- LONG ---")
    tb_long = get_binary_barrier_labels(df, pt_sl_ratio=[2.5, 1.0], time_barrier=24, direction='long')
    print(tb_long['label'].value_counts())
    
    print("--- SHORT ---")
    tb_short = get_binary_barrier_labels(df, pt_sl_ratio=[2.0, 1.0], time_barrier=24, direction='short')
    print(tb_short['label'].value_counts())
