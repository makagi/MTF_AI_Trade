import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
from tqdm import tqdm
import warnings
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data
from src.features import calculate_fib_features

def get_binary_barrier_labels_1h(df: pd.DataFrame, pt_sl_ratio=[2.5, 1.0], time_barrier=72) -> pd.DataFrame:
    df_labels = pd.DataFrame(index=df.index)
    returns = np.zeros(len(df))
    close_vals = df['close'].values
    high_vals = df['high'].values
    low_vals = df['low'].values
    atr_vals = df['ATR_14'].values
    
    for i in range(len(df)):
        if i + 1 >= len(df): break
        c = close_vals[i]
        atr = atr_vals[i]
        if pd.isna(atr) or atr == 0: continue
            
        tp = c + atr * pt_sl_ratio[0]
        sl = c - atr * pt_sl_ratio[1]
            
        future_highs = high_vals[i+1 : i+1+time_barrier]
        future_lows = low_vals[i+1 : i+1+time_barrier]
        
        hit_val = 0
        for j in range(len(future_highs)):
            if future_lows[j] <= sl:
                hit_val = -1
                break
            elif future_highs[j] >= tp:
                hit_val = 1
                break
        returns[i] = hit_val
    df_labels['tb_return'] = returns
    return df_labels

def calculate_bb(series, period, std_dev=2.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return sma + (std * std_dev), sma - (std * std_dev)

def calc_sandwich_ratio(levels, close, atr):
    ceilings = [l for l in levels if l > close]
    floors = [l for l in levels if l <= close]
    ceiling = min(ceilings) if ceilings else close + atr*5
    floor = max(floors) if floors else close - atr*5
    return (close - floor) / (ceiling - floor + 1e-8)

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

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-8)
    return 100 - (100 / (1 + rs))

def main():
    print("Loading 1h Data and computing macro labels/features...")
    df_1h = load_1h_data(include_holdout=True)
    df_1h = calculate_fib_features(df_1h, 19)
    
    df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
    df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
    df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
    df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
    df_1h['Trend_State'] = (df_1h['FIB_11_SMA'] - df_1h['FIB_13_SMA']) / df_1h['close'] * 100
    
    df_1h['BB_144_Upper'], df_1h['BB_144_Lower'] = calculate_bb(df_1h['close'], 144, 2.0)
    df_1h['BB_377_Upper'], df_1h['BB_377_Lower'] = calculate_bb(df_1h['close'], 377, 2.0)
    
    fib_periods = {7: 21, 9: 55, 11: 144, 13: 377}
    total_bb_width = 0
    for k, period in fib_periods.items():
        std = df_1h['close'].rolling(period).std()
        sma = df_1h[f'FIB_{k}_SMA']
        total_bb_width += (4 * std) / sma
    roll_min = total_bb_width.rolling(720).min()
    roll_max = total_bb_width.rolling(720).max()
    df_1h['Squeeze_Index'] = (total_bb_width - roll_min) / (roll_max - roll_min + 1e-8)
    
    df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
    
    cols_long = ['FIB_11_SMA', 'FIB_12_SMA', 'FIB_13_SMA', 'BB_144_Upper', 'BB_144_Lower', 'BB_377_Upper', 'BB_377_Lower']
    sr_long_list = []
    for i in range(len(df_1h_2025)):
        row = df_1h_2025.iloc[i]
        c = row['close']
        atr = row['ATR_14']
        if pd.isna(atr): 
            sr_long_list.append(np.nan)
            continue
        levels_long = [row[col] for col in cols_long if not pd.isna(row[col])]
        sr_long_list.append(calc_sandwich_ratio(levels_long, c, atr) if levels_long else np.nan)
    df_1h_2025['SR_Long'] = sr_long_list
    
    labels = get_binary_barrier_labels_1h(df_1h_2025)
    df_1h_2025['tb_return'] = labels['tb_return']
    
    print("Loading 1m Data and Mapping...")
    df_1m = load_all_1m_data_2025()
    
    df_1h_mapped = df_1h_2025[['ATR_14', 'Trend_State', 'SR_Long', 'Squeeze_Index', 'tb_return']]
    df_1h_mapped = df_1h_mapped.reindex(df_1m.index.floor('h')).ffill().values
    
    df_1m['ATR_1h'] = df_1h_mapped[:, 0]
    df_1m['Trend_State_1h'] = df_1h_mapped[:, 1]
    df_1m['SR_Long_1h'] = df_1h_mapped[:, 2]
    df_1m['Squeeze_Index_1h'] = df_1h_mapped[:, 3]
    df_1m['tb_return_1h'] = df_1h_mapped[:, 4]
    
    print("Calculating Macro Triggers...")
    rolling_high_30m = df_1m['high'].rolling('30min').max()
    panic_mask = (rolling_high_30m - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
    df_1m['Armed_Base'] = panic_mask.rolling('2h').max() > 0
    df_1m['Armed_Vetoed'] = df_1m['Armed_Base'] & (df_1m['SR_Long_1h'] <= 0.8)
    df_1m['Armed_Ghost'] = (df_1m['SR_Long_1h'] < 0.1) & (df_1m['Squeeze_Index_1h'] < 0.5)
    df_1m['Armed_Final'] = df_1m['Armed_Vetoed'] | df_1m['Armed_Ghost']
    
    print("Engineering 1m Micro Features (Price Action & Oscillators)...")
    candle_range = df_1m['high'] - df_1m['low']
    df_1m['Lower_Wick_Ratio'] = (df_1m[['open', 'close']].min(axis=1) - df_1m['low']) / (candle_range + 1e-8)
    df_1m['Micro_Hook'] = (df_1m['close'] > df_1m['high'].shift(1)).astype(int)
    df_1m['RSI_14'] = calculate_rsi(df_1m['close'], 14)
    df_1m['SMA_21'] = df_1m['close'].rolling(21).mean()
    df_1m['SMA_21_Dist'] = (df_1m['close'] - df_1m['SMA_21']) / df_1m['ATR_1h']
    
    print("Labeling 1m Target (Smoothing 15 mins around true bottom)...")
    df_1m['Target'] = 0
    oracle_1h_indices = df_1h_2025[df_1h_2025['tb_return'] == 1].index
    for t_1h in oracle_1h_indices:
        window = df_1m.loc[t_1h : t_1h + pd.Timedelta(hours=1, minutes=59)]
        if len(window) > 0:
            true_bottom = window['low'].idxmin()
            start_target = true_bottom - pd.Timedelta(minutes=15)
            end_target = true_bottom + pd.Timedelta(minutes=15)
            df_1m.loc[start_target:end_target, 'Target'] = 1
            
    print("Preparing LightGBM Dataset (Armed Domain Only)...")
    df_armed = df_1m[df_1m['Armed_Final'] == True].dropna()
    
    features = [
        'Trend_State_1h', 'SR_Long_1h', 'Squeeze_Index_1h',
        'Lower_Wick_Ratio', 'Micro_Hook', 'RSI_14', 'SMA_21_Dist'
    ]
    
    X = df_armed[features]
    y = df_armed['Target']
    
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"Training on {len(X_train)} samples, testing on {len(X_test)} samples")
    print(f"Positive samples ratio: {y_train.mean():.2%}")
    
    scale_pos = (len(y_train) - sum(y_train)) / sum(y_train) if sum(y_train) > 0 else 1
    clf = lgb.LGBMClassifier(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=5,
        scale_pos_weight=scale_pos,
        random_state=42
    )
    clf.fit(X_train, y_train)
    
    y_pred_proba = clf.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"Test ROC-AUC: {auc:.4f}")
    
    df_1m['AI_Proba'] = np.nan
    df_1m.loc[df_armed.index, 'AI_Proba'] = clf.predict_proba(X)[:, 1]
    df_1m['AI_Proba'].fillna(0, inplace=True)
    
    threshold = 0.8
    df_1m['Armed_AI_Sniper'] = (df_1m['Armed_Final'] == True) & (df_1m['AI_Proba'] > threshold)
    
    print("Simulating Execution: AI Sniper vs Naive Macro...")
    
    def run_backtest(df, armed_col):
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        atrs = df['ATR_1h'].values
        armed = df[armed_col].values
        
        in_position = False
        entry_price = sl = tp = expiration_idx = atr_entry = entry_i = 0
        trades = []
        equity_curve = np.zeros(len(df))
        current_equity = 0.0
        
        for i in range(1, len(df)):
            if in_position:
                hit_sl = lows[i] <= sl
                hit_tp = highs[i] >= tp
                timeout = i >= expiration_idx
                
                if hit_sl or hit_tp or timeout:
                    exit_price = sl if hit_sl else (tp if hit_tp else closes[i])
                    trade_ret = (exit_price - entry_price) / entry_price - 0.004
                    current_equity += trade_ret * 100
                    trades.append({'ret': trade_ret * 100, 'is_win': trade_ret > 0})
                    in_position = False
                    
            if not in_position:
                if armed[i] and not armed[i-1]:
                    atr_entry = atrs[i]
                    if pd.isna(atr_entry) or atr_entry == 0: continue
                    in_position = True
                    entry_price = closes[i]
                    sl = entry_price - 1.0 * atr_entry
                    tp = entry_price + 2.5 * atr_entry
                    expiration_idx = i + 72 * 60
                    entry_i = i
            equity_curve[i] = current_equity
        return equity_curve, trades
        
    eq_macro, trades_macro = run_backtest(df_1m, 'Armed_Final')
    eq_ai, trades_ai = run_backtest(df_1m, 'Armed_AI_Sniper')
    
    def get_stats(trades):
        if not trades: return 0, 0, 0, 0
        t = pd.DataFrame(trades)
        w = t['is_win'].mean() * 100
        pnl = t['ret'].sum()
        g_p = t[t['ret']>0]['ret'].sum()
        g_l = abs(t[t['ret']<0]['ret'].sum())
        pf = g_p / g_l if g_l > 0 else float('inf')
        return pnl, w, pf, len(trades)
        
    m_pnl, m_w, m_pf, m_count = get_stats(trades_macro)
    a_pnl, a_w, a_pf, a_count = get_stats(trades_ai)
    
    importance = pd.DataFrame({'Feature': features, 'Importance': clf.feature_importances_})
    importance = importance.sort_values('Importance', ascending=False)
    
    plt.figure(figsize=(15, 8))
    
    ax1 = plt.subplot2grid((1, 3), (0, 0), colspan=2)
    ax1.plot(df_1m.index, eq_macro, label=f'Naive Macro Entry ({m_count} trades)\nWin: {m_w:.1f}%, PF: {m_pf:.2f}', color='gray', alpha=0.5, linestyle='--')
    ax1.plot(df_1m.index, eq_ai, label=f'AI Sniper Entry ({a_count} trades)\nWin: {a_w:.1f}%, PF: {a_pf:.2f}', color='gold', linewidth=2.5)
    ax1.set_title("The Resurrection: AI Sniper vs Naive Execution", fontsize=15, fontweight='bold')
    ax1.set_ylabel("Cumulative Net PnL (%)")
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    ax2 = plt.subplot2grid((1, 3), (0, 2))
    sns.barplot(data=importance, x='Importance', y='Feature', palette='viridis', ax=ax2)
    ax2.set_title("AI Feature Importance")
    
    plt.tight_layout()
    plt.savefig("ai_sniper_resurrection.png", dpi=300)
    print("Saved ai_sniper_resurrection.png")
    
    print("\n=== FINAL SYSTEM PERFORMANCE ===")
    print(f"Naive Macro -> Total PnL: {m_pnl:.1f}%, Win Rate: {m_w:.1f}%, PF: {m_pf:.2f}")
    print(f"AI Sniper   -> Total PnL: {a_pnl:.1f}%, Win Rate: {a_w:.1f}%, PF: {a_pf:.2f}")

if __name__ == '__main__':
    main()
