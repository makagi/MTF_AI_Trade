import pandas as pd
import numpy as np
import glob
from src.data_loader import load_1h_data
from src.features import calculate_fib_features, calculate_diverse_features
from visualize_dual_trigger_pnl import get_binary_barrier_labels

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

df_1h = load_1h_data()
df_1h = calculate_fib_features(df_1h, 19)
df_1h = calculate_diverse_features(df_1h)
df_1h['tr0'] = abs(df_1h['high'] - df_1h['low'])
df_1h['tr1'] = abs(df_1h['high'] - df_1h['close'].shift())
df_1h['tr2'] = abs(df_1h['low'] - df_1h['close'].shift())
df_1h['tr'] = df_1h[['tr0', 'tr1', 'tr2']].max(axis=1)
df_1h['ATR_14'] = df_1h['tr'].rolling(14).mean()
df_1h['Trend_State'] = (df_1h['FIB_11_SMA'] - df_1h['FIB_13_SMA']) / df_1h['close'] * 100

df_1h_2025 = df_1h[df_1h.index >= '2025-01-01'].copy()
labels = get_binary_barrier_labels(df_1h_2025)
oracle_1h_indices = labels[labels['tb_return'] == 1].index
df_1m = load_all_1m_data_2025()
df_1m['ATR_1h'] = df_1h_2025['ATR_14'].reindex(df_1m.index, method='ffill')
df_1m['Trend_State_1h'] = df_1h_2025['Trend_State'].reindex(df_1m.index, method='ffill')
rolling_high_30m = df_1m['high'].rolling('30min').max()
panic_mask = (rolling_high_30m - df_1m['low']) >= (1.5 * df_1m['ATR_1h'])
df_1m['Armed_Single'] = panic_mask.rolling('2h').max() > 0

rolling_high_60m = df_1m['high'].rolling('60min').max()
trend_dip_mask = (df_1m['Trend_State_1h'] > 1.5) & ((rolling_high_60m - df_1m['low']) >= (1.0 * df_1m['ATR_1h']))
armed_trend = trend_dip_mask.rolling('1h').max() > 0
df_1m['Armed_Dual'] = df_1m['Armed_Single'] | armed_trend

oracle_data = []
for t_oracle in oracle_1h_indices:
    window = df_1m.loc[t_oracle - pd.Timedelta(hours=1) : t_oracle + pd.Timedelta(hours=1, minutes=59)]
    if len(window) > 0:
        true_bottom_idx = window['low'].idxmin()
        true_bottom_price = window.loc[true_bottom_idx, 'low']
        t_1h_floor = true_bottom_idx.floor('h')
        atr = df_1h_2025.loc[t_1h_floor, 'ATR_14'] if t_1h_floor in df_1h_2025.index else np.nan
        if not pd.isna(atr):
            net_pnl_pct = (2.5 * atr / true_bottom_price) - 0.004
            oracle_data.append({
                'time': true_bottom_idx,
                'captured_single': df_1m.loc[true_bottom_idx, 'Armed_Single'] if true_bottom_idx in df_1m.index else False,
                'captured_dual': df_1m.loc[true_bottom_idx, 'Armed_Dual'] if true_bottom_idx in df_1m.index else False,
                'net_pnl_pct': net_pnl_pct
            })
            
df_oracles = pd.DataFrame(oracle_data)
df_oracles.drop_duplicates(subset=['time'], inplace=True)
df_prof = df_oracles[df_oracles['net_pnl_pct'] > 0]
ideal_pnl = df_prof['net_pnl_pct'].sum() * 100
single_pnl = df_prof[df_prof['captured_single']]['net_pnl_pct'].sum() * 100
dual_pnl = df_prof[df_prof['captured_dual']]['net_pnl_pct'].sum() * 100

print(f"Ideal PnL: {ideal_pnl:.1f}%")
print(f"Single PnL: {single_pnl:.1f}% ({(single_pnl/ideal_pnl*100):.1f}%)")
print(f"Dual PnL: {dual_pnl:.1f}% ({(dual_pnl/ideal_pnl*100):.1f}%)")
