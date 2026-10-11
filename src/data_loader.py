"""Data loader module for MTF_AI_Trade.

Implements strict Holdout period isolation and timeframe-specific loading
according to 02_SPECIFICATIONS/evaluation.md (SPEC-EVAL-001).
"""

from __future__ import annotations

import warnings
from pathlib import Path
import pandas as pd

from src.config import (
    get_symbol_dir,
    DISCOVERY_START,
    DISCOVERY_END,
    VALIDATION_START,
    VALIDATION_END,
    HOLDOUT_START,
)


def load_ohlcv(
    symbol: str = "BTCUSD",
    timeframe: str = "1h",
    include_holdout: bool = False,
) -> pd.DataFrame:
    """Load OHLCV data for given symbol and timeframe.

    Strictly cuts off data at HOLDOUT_START unless include_holdout=True is explicitly given.
    """
    symbol_dir = get_symbol_dir(symbol, timeframe)
    if not symbol_dir.exists():
        raise FileNotFoundError(f"Symbol directory not found: {symbol_dir}")

    # Search for standard file names
    csv_candidates = [
        symbol_dir / f"{symbol.upper()}_OHLC_all.csv",
        symbol_dir / f"{symbol.upper()}_{timeframe.lower()}.csv",
    ]
    file_path: Path | None = None
    for candidate in csv_candidates:
        if candidate.exists():
            file_path = candidate
            break

    if file_path is None:
        # Fallback: pick the first matching .csv
        found = list(symbol_dir.glob("*.csv"))
        if not found:
            raise FileNotFoundError(f"No CSV files found in {symbol_dir}")
        file_path = found[0]

    df = pd.read_csv(file_path)

    # Resolve DateTime column
    date_cols = [c for c in df.columns if c.lower() in ("datetime", "date", "timestamp", "time")]
    if not date_cols:
        raise ValueError(f"No datetime column found in {file_path}. Columns: {df.columns.tolist()}")
    date_col = date_cols[0]

    df[date_col] = pd.to_datetime(df[date_col], utc=True)
    df.set_index(date_col, inplace=True)
    df.index.name = "datetime"
    df.sort_index(inplace=True)

    # Drop duplicate timestamps
    df = df[~df.index.duplicated(keep="last")]

    # Strict Holdout period isolation (SPEC-EVAL-001 §2.3)
    if not include_holdout:
        df = df[df.index < pd.Timestamp(HOLDOUT_START, tz="UTC")].copy()
    else:
        warnings.warn(
            f"ACCESSING FINAL HOLDOUT PERIOD ({HOLDOUT_START}+)! "
            "Ensure this is strictly for the final verification audit.",
            UserWarning,
            stacklevel=2,
        )

    return df


def load_discovery_data(symbol: str = "BTCUSD", timeframe: str = "1h") -> pd.DataFrame:
    """Load Discovery / Train partition (2020-01-01 to 2023-12-31)."""
    df = load_ohlcv(symbol, timeframe, include_holdout=False)
    start = pd.Timestamp(DISCOVERY_START, tz="UTC")
    end = pd.Timestamp(DISCOVERY_END, tz="UTC") + pd.Timedelta(days=1, microseconds=-1)
    return df.loc[(df.index >= start) & (df.index <= end)].copy()


def load_validation_data(symbol: str = "BTCUSD", timeframe: str = "1h") -> pd.DataFrame:
    """Load Validation partition (2024-01-01 to 2024-12-31)."""
    df = load_ohlcv(symbol, timeframe, include_holdout=False)
    start = pd.Timestamp(VALIDATION_START, tz="UTC")
    end = pd.Timestamp(VALIDATION_END, tz="UTC") + pd.Timedelta(days=1, microseconds=-1)
    return df.loc[(df.index >= start) & (df.index <= end)].copy()
