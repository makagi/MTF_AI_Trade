import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import lightgbm as lgb
import glob
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from train_lightgbm import build_v5_0_features

def load_all_1m_data_2025():
    files = glob.glob("D:/work/AI-Trade/Data/BTCUSD_1m/BTCUSD_OHLC_2025*.csv")
    dfs = []
    for f in sorted(files):
        df = pd.read_csv(f)
        df.columns = [c.strip() for c in df.columns]
        dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df.set_index('DateTime', inplace=True)
    df.sort_index(inplace=True)
    return df

def get_pseudo_candle(df_1m, t_start, t_end):
    df_pseudo = df_1m.loc[t_start:t_end]
    if len(df_pseudo) == 0:
        return None
    return pd.DataFrame({
        'open': [df_pseudo['open'].iloc[0]],
        'high': [df_pseudo['high'].max()],
        'low': [df_pseudo['low'].min()],
        'close': [df_pseudo['close'].iloc[-1]],
        'volume': [df_pseudo['volume'].sum() if 'volume' in df_pseudo else 0]
    }, index=[t_start])

def main():
    print("Loading 1h Raw History...")
    df_1h_raw = load_1h_data(include_holdout=True)
    df_1h_raw.sort_index(inplace=True)
    
    print("Loading 1m Data for 2025...")
    df_1m = load_all_1m_data_2025()
    
    print("Loading LightGBM Model...")
    model_long = lgb.Booster(model_file='models/lgbm_v5_0_long.txt')
    
    print("Loading MTF Entries...")
    mtf = pd.read_csv('mtf_backtest_results.csv')
    mtf = mtf[mtf['direction'] == 'LONG'].copy()
    mtf['entry_time'] = pd.to_datetime(mtf['entry_time'])
    mtf.sort_values('entry_time', inplace=True)
    
    results = []
    
    print("Starting Zero-Lag Simulation...")
    for idx, row in tqdm(mtf.iterrows(), total=len(mtf)):
        t_end = row['entry_time']
        t_start = t_end.floor('h')
        
        pseudo_candle = get_pseudo_candle(df_1m, t_start, t_end)
        if pseudo_candle is None: continue
            
        t_hist_start = t_start - pd.Timedelta(hours=450)
        df_hist = df_1h_raw.loc[t_hist_start : t_start - pd.Timedelta(hours=1)].copy()
        if len(df_hist) < 400: continue
            
        df_eval = pd.concat([df_hist, pseudo_candle])
        df_eval = calculate_fib_features(df_eval, 19)
        df_eval = calculate_diverse_features(df_eval)
        df_eval, feature_cols = build_v5_0_features(df_eval)
        
        last_row = df_eval.iloc[-1:]
        pred_L = model_long.predict(last_row[feature_cols])[0]
        trigger_sniper = last_row['F_Trigger_v5_L'].values[0] > 0
        trigger_trend = last_row['F_Trigger_Trend_L'].values[0] > 0
        
        if pred_L > 0.25:
            if trigger_sniper or trigger_trend:
                row['engine'] = 'Sniper' if trigger_sniper else 'Trend'
                row['pred'] = pred_L
                # Add minute of hour
                row['minute'] = t_end.minute
                # Map hit to success (0 or 1)
                row['success'] = 1 if row['hit'] == 1 else 0
                results.append(row)
                
    if len(results) == 0:
        print("No trades")
        return
        
    df = pd.DataFrame(results)
    
    # Visualization: Distribution Shift (Candle Completion Illusion)
    bins = [-1, 14, 29, 44, 59]
    labels = ['0-14m', '15-29m', '30-44m', '45-59m']
    df['minute_bin'] = pd.cut(df['minute'], bins=bins, labels=labels)
    
    summary = df.groupby('minute_bin', observed=False)['success'].agg(['count', 'sum']).fillna(0)
    summary['win_rate'] = (summary['sum'] / summary['count']) * 100
    summary['loss'] = summary['count'] - summary['sum']
    
    sns.set_style('darkgrid')
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Left: Stacked Bar of Wins and Losses
    x = np.arange(len(labels))
    axes[0].bar(x, summary['sum'], color='green', label='Wins')
    axes[0].bar(x, summary['loss'], bottom=summary['sum'], color='red', label='Losses')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_title('Trade Volume & Outcomes by Minute of Hour')
    axes[0].set_xlabel('Minute of Hour (Candle Completion)')
    axes[0].set_ylabel('Number of Trades')
    axes[0].legend()
    
    # Right: Win Rate Line Plot
    axes[1].plot(x, summary['win_rate'], color='purple', marker='o', linewidth=3, markersize=10)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels)
    axes[1].set_ylim(0, 100)
    axes[1].axhline(y=50, color='gray', linestyle='--', alpha=0.5)
    axes[1].set_title('Win Rate % by Minute of Hour (Candle Completion Illusion)')
    axes[1].set_xlabel('Minute of Hour (Candle Completion)')
    axes[1].set_ylabel('Win Rate (%)')
    
    for i, txt in enumerate(summary['win_rate']):
        if not np.isnan(txt):
            axes[1].annotate(f'{txt:.1f}%', (x[i], summary['win_rate'].iloc[i] + 3), ha='center', fontsize=12)
            
    plt.tight_layout()
    plt.savefig('candle_completion_illusion.png', dpi=300)
    print("Saved candle_completion_illusion.png")

if __name__ == '__main__':
    main()
