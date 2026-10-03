import os

# ==========================================
# プロジェクト設定 (CONSTITUTION準拠)
# ==========================================

# 1. パス設定
DATA_DIR = r"D:\work\AI-Trade\Data"
BTCUSD_1M_DIR = os.path.join(DATA_DIR, "BTCUSD_1m")
BTCUSD_1H_DIR = os.path.join(DATA_DIR, "BTCUSD_1h")

# 2. フィボナッチ期間の定義
# ユーザー定義: 1, 2, 3, 5, 8, ... 17711 (最大21項)
FIBONACCI_SERIES = [
    1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 
    377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711
]

# 最大適用インデックス (1-indexed と見なす)
# 1時間足では最大19項(6765)までとする
MAX_FIB_INDEX_1H = 19
# 1分足はフル(21項: 17711)とする
MAX_FIB_INDEX_1M = 21

# 3. 期間設定 (Data Partitioning)
# 発見・探索 (Train: 仮説生成、ゲート探索)
DISCOVERY_START = '2020-01-01'
DISCOVERY_END   = '2023-12-31'

# 準ホールドアウト (Validation: 一発勝負の仮説検定)
VALIDATION_START = '2024-01-01'
VALIDATION_END   = '2024-12-31'

# 最終封印 (Holdout: 最終性能評価、絶対に探索に使わない)
HOLDOUT_START    = '2025-01-01'

# 4. モデリング・評価パラメータ
TARGET_HORIZON_1H = 24  # 予測対象ホライズン (24h)
TARGET_HORIZON_1M = 60  # 1分足用

# リスク許容度設定
MAX_DRAWDOWN_LIMIT = 0.05
RISK_PER_TRADE = 0.02

# 取引コスト設定 (往復の実効コストを一元化)
BASE_COST = 0.002  # 0.2% (Taker手数料 + スリッページを含む保守的な往復コスト)
