import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
from sklearn.tree import DecisionTreeClassifier, plot_tree

warnings.filterwarnings('ignore')

from src.data_loader import load_1h_data

def calculate_atr(df, p=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(p).mean()
    return df

def get_fib_periods():
    return [21, 55, 144, 377, 610, 1597]

def add_features(df):
    periods = get_fib_periods()
    for p in periods:
        sma = df['close'].rolling(p).mean()
        std = df['close'].rolling(p).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        df[f'BW_{p}'] = (upper - lower) / df['close']
        df[f'VEL_BW_{p}'] = df[f'BW_{p}'].diff(24)
        
        rolling_min = df['low'].rolling(window=p).min()
        rolling_max = df['high'].rolling(window=p).max()
        k_line = (df['close'] - rolling_min) / (rolling_max - rolling_min + 1e-8) * 100
        df[f'AFS_{p}'] = k_line.rolling(window=p).mean()
        
        pctb = (df['close'] - lower) / (upper - lower + 1e-8)
        slope = (sma - sma.shift(p)) / sma.shift(p) * 100
        avg_pctb = pctb.rolling(p).mean()
        
        phase = np.zeros(len(df))
        uptrend = (slope > 0.5) & (avg_pctb > 0.5)
        downtrend = (slope < -0.5) & (avg_pctb < 0.5)
        
        phase[uptrend] = 1
        phase[downtrend] = -1
        phase[:p*2] = np.nan 
        
        df[f'PHASE_{p}'] = phase
    return df

def run_backtest_and_get_trades(df):
    bw144_q = df['BW_144'].rolling(720).quantile(0.4)
    cond_macro_vol = (df['BW_144'] < bw144_q)
    cond_macro_phase = (df['PHASE_144'] <= 0)
    cond_micro_mom = (df['AFS_21'] > df['AFS_55'])
    cond_micro_phase = (df['PHASE_21'] == 1) & (df['PHASE_21'].shift(1) <= 0)
    
    buy_signals = df[cond_macro_vol & cond_macro_phase & cond_micro_mom & cond_micro_phase].index
    
    trades = []
    in_trade = False
    entry_idx = None
    entry_price = 0
    sl_price = 0
    atr = 0
    
    # Store all features
    periods = get_fib_periods()
    feature_cols = [f'AFS_{p}' for p in periods] + [f'BW_{p}' for p in periods] + [f'VEL_BW_{p}' for p in periods]
    
    for i in range(len(df)):
        idx = df.index[i]
        row = df.iloc[i]
        
        if not in_trade:
            if idx in buy_signals:
                in_trade = True
                entry_idx = idx
                entry_price = row['close']
                atr = row['ATR']
                sl_price = entry_price - (atr * 1.5)
        else:
            if row['low'] < sl_price:
                trade_data = {
                    'entry': entry_idx, 'exit': idx, 
                    'atr_pnl': (sl_price - entry_price)/atr, 
                }
                for col in feature_cols:
                    trade_data[col] = df.loc[entry_idx, col]
                trades.append(trade_data)
                in_trade = False
            elif row['PHASE_21'] == -1:
                exit_price = row['close']
                trade_data = {
                    'entry': entry_idx, 'exit': idx, 
                    'atr_pnl': (exit_price - entry_price)/atr,
                }
                for col in feature_cols:
                    trade_data[col] = df.loc[entry_idx, col]
                trades.append(trade_data)
                in_trade = False
                
    return pd.DataFrame(trades), feature_cols

def main():
    print("Loading Data...")
    df = load_1h_data(include_holdout=True)
    df = calculate_atr(df, 14)
    df = add_features(df)
    
    print("Running Backtest to extract features at entry...")
    trades, feature_cols = run_backtest_and_get_trades(df)
    
    if len(trades) == 0:
        print("No trades found.")
        return
        
    trades['Target'] = np.nan
    trades.loc[trades['atr_pnl'] >= 1.0, 'Target'] = 1 # Success
    trades.loc[trades['atr_pnl'] < -0.5, 'Target'] = 0 # Failure
    
    # Drop rows that are neither (between -0.5 and 1.0) and drop NaNs
    ml_data = trades.dropna(subset=['Target'] + feature_cols)
    
    print(f"Total Labeled Trades: {len(ml_data)}")
    print(f"Success: {len(ml_data[ml_data['Target']==1])}")
    print(f"Failure: {len(ml_data[ml_data['Target']==0])}")
    
    if len(ml_data[ml_data['Target']==1]) == 0 or len(ml_data[ml_data['Target']==0]) == 0:
        print("Not enough classes for Decision Tree.")
        return
        
    X = ml_data[feature_cols]
    y = ml_data['Target']
    
    # Train shallow Decision Tree
    clf = DecisionTreeClassifier(max_depth=2, random_state=42, class_weight='balanced')
    clf.fit(X, y)
    
    # Get feature importances
    importances = pd.Series(clf.feature_importances_, index=feature_cols).sort_values(ascending=False)
    top_features = importances[importances > 0].index.tolist()
    print("\nFeature Importances from Decision Tree:")
    print(importances.head())
    
    # Visualization
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(18, 12))
    
    # Plot 1: Decision Tree
    ax1 = plt.subplot2grid((2, 2), (0, 0), colspan=2)
    plot_tree(clf, feature_names=feature_cols, class_names=['Failure', 'Success'], 
              filled=True, rounded=True, ax=ax1, impurity=False, 
              proportion=True, precision=2)
    ax1.set_title("Decision Tree: Separation Boundary between Success and Failure", fontsize=16, color='white')
    
    # Plot 2: KDE of Top Feature 1
    if len(top_features) > 0:
        ax2 = plt.subplot2grid((2, 2), (1, 0))
        sns.kdeplot(data=ml_data, x=top_features[0], hue='Target', palette={0: 'red', 1: 'lime'}, 
                    fill=True, common_norm=False, alpha=0.5, ax=ax2)
        ax2.set_title(f"KDE: {top_features[0]} (Top Separator)", fontsize=14, color='white')
        
    # Plot 3: KDE of Top Feature 2
    if len(top_features) > 1:
        ax3 = plt.subplot2grid((2, 2), (1, 1))
        sns.kdeplot(data=ml_data, x=top_features[1], hue='Target', palette={0: 'red', 1: 'lime'}, 
                    fill=True, common_norm=False, alpha=0.5, ax=ax3)
        ax3.set_title(f"KDE: {top_features[1]} (2nd Separator)", fontsize=14, color='white')
    elif len(top_features) > 0:
        # Just plot the first one again or leave blank
        pass

    plt.tight_layout()
    plt.savefig("feature_separation_analysis.png", dpi=300)
    print("Saved feature_separation_analysis.png")

if __name__ == '__main__':
    main()
