import pandas as pd
from src.data_loader import load_1h_data
from analyze_feature_separation import add_features, calculate_atr

df = load_1h_data(include_holdout=True)
df = calculate_atr(df, 14)
df = add_features(df)

# The base conditions
bw144_q = df['BW_144'].rolling(720).quantile(0.4)
cond_macro_vol = (df['BW_144'] < bw144_q)
cond_macro_phase = (df['PHASE_144'] <= 0)
cond_micro_mom = (df['AFS_21'] > df['AFS_55'])
cond_micro_phase = (df['PHASE_21'] == 1) & (df['PHASE_21'].shift(1) <= 0)

base_buy = cond_macro_vol & cond_macro_phase & cond_micro_mom & cond_micro_phase

# The Divergence Filter
# Price Current Low (rolling 24h min)
price_low = df['low'].rolling(24).min()
# Price Previous Low (24h to 120h ago min)
price_prev_low = df['low'].shift(24).rolling(96).min()

# AFS 144 Current
afs_curr = df['AFS_144'].rolling(24).min()
# AFS 144 Previous
afs_prev = df['AFS_144'].shift(24).rolling(96).min()

bull_div = (price_low < price_prev_low) & (afs_curr > afs_prev)

div_buy = base_buy & bull_div

print(f"Base Buy Signals: {base_buy.sum()}")
print(f"Div Buy Signals: {div_buy.sum()}")
