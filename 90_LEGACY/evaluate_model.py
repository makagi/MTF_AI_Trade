import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import matplotlib.pyplot as plt

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from src.config import MAX_FIB_INDEX_1H, HOLDOUT_START
from src.labels import get_binary_barrier_labels
from train_lightgbm import build_v5_0_features

def calculate_pnl(df_holdout, preds_long, preds_short, threshold, fee=0.004):
    pnl = np.zeros(len(df_holdout))
    # Keep track of which trigger fired for logging
    trigger_type = np.full(len(df_holdout), None, dtype=object)
    
    # We step through time to avoid overlapping trades
    i = 0
    while i < len(df_holdout):
        prob_long = preds_long[i]
        prob_short = preds_short[i]
        
        t_v5_L = df_holdout['F_Trigger_v5_L'].iloc[i]
        t_v5_S = df_holdout['F_Trigger_v5_S'].iloc[i]
        
        t_trend_L = df_holdout['F_Trigger_Trend_L'].iloc[i]
        t_trend_S = df_holdout['F_Trigger_Trend_S'].iloc[i]
        
        trigger_long = max(t_v5_L, t_trend_L)
        trigger_short = max(t_v5_S, t_trend_S)
        
        # Determine signal
        signal = 0
        current_trigger_type = None
        
        # Gating
        if prob_long > threshold and trigger_long > 0:
            signal = 1
            if t_v5_L > 0: current_trigger_type = "Sniper"
            elif t_trend_L > 0: current_trigger_type = "TrendPullback"
        elif prob_short > threshold and trigger_short > 0:
            signal = -1
            if t_v5_S > 0: current_trigger_type = "Sniper"
            elif t_trend_S > 0: current_trigger_type = "TrendPullback"
            
        if signal == 1:
            ret = df_holdout['tb_return_long'].iloc[i]
            hit_period = df_holdout['hit_period_long'].iloc[i]
            pnl[i] = ret - fee
            trigger_type[i] = current_trigger_type
            if threshold == 0.25:
                print(f"LONG ({current_trigger_type}) at {df_holdout.index[i]}")
            i += int(hit_period) if hit_period > 0 else 1
        elif signal == -1:
            ret = df_holdout['tb_return_short'].iloc[i]
            hit_period = df_holdout['hit_period_short'].iloc[i]
            pnl[i] = ret - fee
            trigger_type[i] = current_trigger_type
            if threshold == 0.25:
                print(f"SHORT ({current_trigger_type}) at {df_holdout.index[i]}")
            i += int(hit_period) if hit_period > 0 else 1
        else:
            i += 1
            
    return pnl, trigger_type

def run():
    print("Loading data (Holdout period only)...")
    df = load_1h_data(include_holdout=True)
    df = calculate_fib_features(df, MAX_FIB_INDEX_1H)
    df = calculate_diverse_features(df)
    
    print("Building v5.0 features...")
    df, feature_cols = build_v5_0_features(df)
    
    print("Generating Asymmetric Binary Labels for evaluation...")
    tb_long = get_binary_barrier_labels(df, pt_sl_ratio=[2.5, 1.0], time_barrier=72, direction='long')
    tb_short = get_binary_barrier_labels(df, pt_sl_ratio=[1.5, 1.0], time_barrier=72, direction='short')
    
    df['tb_return_long'] = tb_long['tb_return']
    df['hit_period_long'] = tb_long['hit_period']
    df['label_long'] = tb_long['label']
    
    df['tb_return_short'] = tb_short['tb_return']
    df['hit_period_short'] = tb_short['hit_period']
    df['label_short'] = tb_short['label']
    
    df.dropna(subset=['tb_return_long', 'tb_return_short'] + feature_cols, inplace=True)
    
    # Time-based Split (Holdout Only)
    df_holdout = df[df.index >= HOLDOUT_START].copy()
    X_holdout = df_holdout[feature_cols]
    
    print(f"Holdout size: {len(df_holdout)}")
    
    # Load trained models
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    model_short = lgb.Booster(model_file='models/lgbm_v5_0_short.txt')
    
    print("Predicting on Holdout set...")
    preds_long = model_long.predict(X_holdout)
    preds_short = model_short.predict(X_holdout)
    
    thresholds = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6]
    best_threshold = 0
    best_expectancy = -999
    best_pnl = None
    
    results = []
    
    for th in thresholds:
        pnl, trigger_type = calculate_pnl(df_holdout, preds_long, preds_short, th)
        trades = pnl[pnl != 0]
        n_trades = len(trades)
        
        if n_trades == 0:
            continue
        
        wins = trades[trades > 0]
        losses = trades[trades <= 0]
        
        win_rate = len(wins) / n_trades
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        total_pnl = pnl.sum()
        
        results.append({
            'Threshold': th,
            'Trades': n_trades,
            'Win Rate': win_rate,
            'Avg Win': avg_win,
            'Avg Loss': avg_loss,
            'Expectancy (Net)': expectancy,
            'Total PnL (Net)': total_pnl
        })
        
        if total_pnl > best_expectancy:
            best_expectancy = total_pnl
            best_threshold = th
            best_pnl = pnl
            
        if th == 0.25:
            # Breakdown by trigger
            t_df = pd.DataFrame({'pnl': pnl, 'type': trigger_type})
            t_df = t_df[t_df['pnl'] != 0]
            print("\n--- Breakdown for Threshold 0.25 ---")
            for t_name, grp in t_df.groupby('type'):
                gr_wins = len(grp[grp['pnl'] > 0])
                gr_total = len(grp)
                gr_wr = gr_wins / gr_total if gr_total > 0 else 0
                print(f"{t_name}: {gr_wins}/{gr_total} wins ({gr_wr*100:.1f}%), PnL: {grp['pnl'].sum():.2f}")
            print("------------------------------------")
            
    res_df = pd.DataFrame(results)
    print("\n=== Threshold Optimization Results (v5.0 Zero-Lag Macro Sniper, Holdout Set) ===")
    print(res_df.to_string(index=False))
    
    if best_pnl is not None:
        equity_curve = np.cumsum(best_pnl)
        plt.figure(figsize=(12, 6))
        plt.plot(df_holdout.index, equity_curve, label=f'Net Equity (Threshold > {best_threshold})')
        plt.title('v5.0 Zero-Lag Macro Sniper - Holdout Equity Curve (0.4% Fee)')
        plt.ylabel('Cumulative Return')
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        os.makedirs("results", exist_ok=True)
        plt.savefig("results/equity_curve_v5_0.png")
        print("\nSaved results/equity_curve_v5_0.png")

if __name__ == "__main__":
    run()
