import os
import glob
import pandas as pd
from src.config import (
    BTCUSD_1H_DIR, BTCUSD_1M_DIR, 
    HOLDOUT_START, DISCOVERY_START, DISCOVERY_END, 
    VALIDATION_START, VALIDATION_END
)

def load_1h_data(include_holdout=False) -> pd.DataFrame:
    """1時間足データを読み込む。デフォルトでHOLDOUT_START以降は物理的に返さない。"""
    file_path = os.path.join(BTCUSD_1H_DIR, "BTCUSD_OHLC_all.csv")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"1h data not found: {file_path}")
    
    print(f"Loading 1h data from {file_path}...")
    df = pd.read_csv(file_path)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df.set_index('DateTime', inplace=True)
    df.sort_index(inplace=True)
    # 重複排除
    df = df[~df.index.duplicated(keep='last')]
    
    if not include_holdout:
        df = df[df.index < HOLDOUT_START].copy()
    
    return df

def load_discovery_data() -> pd.DataFrame:
    """発見・探索（EDA/仮説生成）用データを読み込む"""
    df = load_1h_data()
    return df.loc[DISCOVERY_START:DISCOVERY_END].copy()

def load_validation_data() -> pd.DataFrame:
    """準ホールドアウト（一発勝負の検定）用データを読み込む"""
    df = load_1h_data()
    return df.loc[VALIDATION_START:VALIDATION_END].copy()


def load_1m_data(year_month_pattern: str = "*") -> pd.DataFrame:
    """
    1分足データを読み込む。
    メモリ制限を考慮し、年や月のパターンでフィルタ可能 (例: '2023*' または '20230[1-6]')
    """
    pattern = os.path.join(BTCUSD_1M_DIR, f"BTCUSD_OHLC_{year_month_pattern}.csv")
    files = glob.glob(pattern)
    
    if not files:
        print(f"No 1m data files found for pattern: {pattern}")
        return pd.DataFrame()
    
    print(f"Loading {len(files)} files for 1m data...")
    dfs = []
    for f in sorted(files):
        try:
            # 1分足はサイズが大きいため進捗を出力
            print(f"  Reading {os.path.basename(f)}...")
            df = pd.read_csv(f)
            dfs.append(df)
        except Exception as e:
            print(f"Error loading {f}: {e}")
            
    if not dfs:
        return pd.DataFrame()
        
    combined = pd.concat(dfs, ignore_index=True)
    combined['DateTime'] = pd.to_datetime(combined['DateTime'])
    combined.set_index('DateTime', inplace=True)
    combined.sort_index(inplace=True)
    
    # 重複排除
    combined = combined[~combined.index.duplicated(keep='last')]
    return combined

if __name__ == "__main__":
    # 簡単な動作テスト用
    df_1h = load_1h_data()
    print("1h data shape:", df_1h.shape)
    print(df_1h.head(2))
    print(df_1h.tail(2))
