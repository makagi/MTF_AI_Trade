"""Configuration module for MTF_AI_Trade.

Adheres to 02_SPECIFICATIONS/evaluation.md (SPEC-EVAL-001).
Data path is dynamically resolved via MTF_DATA_DIR environment variable
with automatic fallback to local directories.
"""

from __future__ import annotations

import os
from pathlib import Path

# ==============================================================================
# 1. Data Path Resolution
# ==============================================================================

def get_data_dir() -> Path:
    """Resolve data directory path dynamically.

    Priority:
    1. MTF_DATA_DIR environment variable
    2. D:/work/AI-Trade/Data
    3. ../Data (relative to project root)
    4. ./data (local folder)
    """
    env_dir = os.environ.get("MTF_DATA_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.exists():
            return p.resolve()

    candidates = [
        Path("D:/work/AI-Trade/Data"),
        Path(__file__).resolve().parent.parent.parent / "Data",
        Path(__file__).resolve().parent.parent / "data",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()

    # Fallback to default path
    return Path("D:/work/AI-Trade/Data")


def get_symbol_dir(symbol: str, timeframe: str) -> Path:
    """Get directory path for a given symbol and timeframe (e.g. BTCUSD, 1h)."""
    data_dir = get_data_dir()
    # Support folder names like BTCUSD_1h, BTCUSD_1m
    target_name = f"{symbol.upper()}_{timeframe.lower()}"
    symbol_dir = data_dir / target_name
    return symbol_dir


# ==============================================================================
# 2. Data Partitioning (SPEC-EVAL-001 §2)
# ==============================================================================

DISCOVERY_START = "2020-01-01"
DISCOVERY_END = "2025-04-30"

VALIDATION_START = "2025-05-01"
VALIDATION_END = "2026-03-31"

HOLDOUT_START = "2026-04-01"  # STRICTLY SEALED



# ==============================================================================
# 3. Friction Cost Model (SPEC-EVAL-001 §3)
# ==============================================================================

STANDARD_FRICTION_COST = 0.0040  # 0.40% Round-Trip (0.20% per side)
COMMISSION_COST = 0.0010         # 0.10% Round-Trip (0.05% per side)
SPREAD_COST = 0.0010             # 0.10% Round-Trip (0.05% per side)
SLIPPAGE_COST = 0.0020           # 0.20% Round-Trip (0.10% per side)


# ==============================================================================
# 4. Standard Math & Technical Constants
# ==============================================================================

FIBONACCI_SERIES = [
    1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233,
    377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711,
]
