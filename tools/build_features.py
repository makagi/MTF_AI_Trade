import os
import sys
import pandas as pd
from datetime import datetime

# src をパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import load_1h_data
from src.features import calculate_fib_features
from src.config import MAX_FIB_INDEX_1H

# Processedデータの保存先
PROCESSED_DIR = r"D:\work\AI-Trade\Data\processed"
OUTPUT_FILE = os.path.join(PROCESSED_DIR, "BTCUSD_1h_features_exhaustive.parquet")

def main():
    print(f"[{datetime.now()}] Loading raw 1h data...")
    # 全データをロード（HOLDOUTも含めて計算し、分析時にフィルタする）
    df = load_1h_data(include_holdout=True)
    
    print(f"[{datetime.now()}] Calculating exhaustive Fibonacci features (up to index {MAX_FIB_INDEX_1H})...")
    # すべてのkについて網羅的に計算
    df_features = calculate_fib_features(df, max_fib_index=MAX_FIB_INDEX_1H)
    
    print(f"[{datetime.now()}] Added {len(df_features.columns) - len(df.columns)} new feature columns.")
    
    # 保存
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    print(f"[{datetime.now()}] Saving to {OUTPUT_FILE}...")
    df_features.to_parquet(OUTPUT_FILE)
    print(f"[{datetime.now()}] Done! File size: {os.path.getsize(OUTPUT_FILE) / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    main()
