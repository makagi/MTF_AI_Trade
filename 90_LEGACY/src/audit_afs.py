import pandas as pd
from src.config import MAX_FIB_INDEX_1H, BASE_COST, TARGET_HORIZON_1H
from src.data_loader import load_discovery_data
from src.features import calculate_fib_features
from src.eda_edge_map import define_signals

def main():
    df_1h = load_discovery_data()
    df_features = calculate_fib_features(df_1h, MAX_FIB_INDEX_1H)
    signals = define_signals(df_features)
    
    df_features['fwd_ret_24'] = df_features['close'].shift(-24) / df_features['close'] - 1.0
    
    events = df_features[signals['AFS_Extreme_Long']].copy()
    
    print(f"Number of AFS_Extreme_Long events: {len(events)}")
    if len(events) > 0:
        print(events[['close', 'AFS_1_19', 'AFS_10_19', 'fwd_ret_24']].head(20))
        print(f"Mean fwd_ret_24: {events['fwd_ret_24'].mean()*100:.2f}%")
        print(f"Median fwd_ret_24: {events['fwd_ret_24'].median()*100:.2f}%")

if __name__ == '__main__':
    main()
