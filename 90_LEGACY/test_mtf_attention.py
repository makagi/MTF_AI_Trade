import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from src.data_loader import load_1h_data
from src.features import calculate_fib_features
from src.config import MAX_FIB_INDEX_1H

def run():
    print("Loading data...")
    df = load_1h_data()
    df = df.iloc[-10000:].copy() # Test on last 10000 bars
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    
    macro_ks = [9, 10, 11, 12, 13, 14, 15] # 55, 89, 144, 233, 377, 610, 987
    micro_ks = [5, 6, 7, 8] # 5, 8, 13, 21, 34
    
    # Pre-calculate path length base
    abs_diff = df['close'].diff().abs()
    
    fib_lengths = [5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
    idx_to_len = {k: fib_lengths[k-5] for k in range(5, 16)} # Mapping K to length
    
    er_dict = {}
    for k in macro_ks + micro_ks:
        L = idx_to_len[k]
        net_change = (df['close'] - df['close'].shift(L)).abs()
        path_len = abs_diff.rolling(window=L).sum()
        er = net_change / (path_len + 1e-8)
        er_dict[k] = er

    tau_trend = 0.1
    tau_range = 0.1
    
    # Macro Weights
    exp_trend = {k: np.exp(er_dict[k] / tau_trend) for k in macro_ks}
    sum_exp_trend = sum(exp_trend.values())
    w_trend = {k: exp_trend[k] / sum_exp_trend for k in macro_ks}
    
    # Micro Weights (Inverse ER)
    exp_range = {k: np.exp(-er_dict[k] / tau_range) for k in micro_ks}
    sum_exp_range = sum(exp_range.values())
    w_range = {k: exp_range[k] / sum_exp_range for k in micro_ks}
    
    # Dynamic Features
    dyn_macro_slope = pd.Series(np.zeros(len(df)), index=df.index)
    dyn_micro_stoch = pd.Series(np.zeros(len(df)), index=df.index)
    
    # Approximate ATR for slope normalization
    atr = abs_diff.rolling(14).mean()
    
    for k in macro_ks:
        slope = (df[f'FIB_{k}_SMA'] - df[f'FIB_{k}_SMA'].shift(5)) / atr
        dyn_macro_slope += w_trend[k] * slope
        
    for k in micro_ks:
        dyn_micro_stoch += w_range[k] * df[f'FIB_{k}_stoch_d']
        
    df['Dyn_Macro_Slope'] = dyn_macro_slope
    df['Dyn_Micro_Stoch'] = dyn_micro_stoch
    
    # Plot weights for a visual sanity check
    start_plot = df.index[-2000]
    end_plot = df.index[-1000]
    
    plt.figure(figsize=(15, 10))
    
    plt.subplot(3, 1, 1)
    plt.plot(df.loc[start_plot:end_plot].index, df.loc[start_plot:end_plot]['close'], color='black')
    plt.title("Price Action")
    
    plt.subplot(3, 1, 2)
    for k in macro_ks:
        plt.plot(df.loc[start_plot:end_plot].index, w_trend[k].loc[start_plot:end_plot], label=f'W_trend (L={idx_to_len[k]})')
    plt.title("Macro Trend Attention Weights (Softmax of ER)")
    plt.legend(loc='upper left', fontsize='small')
    
    plt.subplot(3, 1, 3)
    for k in micro_ks:
        plt.plot(df.loc[start_plot:end_plot].index, w_range[k].loc[start_plot:end_plot], label=f'W_range (L={idx_to_len[k]})')
    plt.title("Micro Range Attention Weights (Softmax of -ER)")
    plt.legend(loc='upper left', fontsize='small')
    
    plt.tight_layout()
    import os
    os.makedirs("results", exist_ok=True)
    plt.savefig("results/mtf_attention_weights.png")
    print("Saved results/mtf_attention_weights.png")

if __name__ == "__main__":
    run()
