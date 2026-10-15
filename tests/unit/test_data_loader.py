import pandas as pd
import pytest
from src.config import (
    DISCOVERY_START,
    DISCOVERY_END,
    VALIDATION_START,
    VALIDATION_END,
    HOLDOUT_START,
)
from src.data_loader import load_ohlcv

def test_partitioning_constants():
    # Verify SPEC-EVAL-001 constants (2026-09 data extension)
    assert DISCOVERY_START == "2020-01-01"
    assert DISCOVERY_END == "2025-04-30"
    assert VALIDATION_START == "2025-05-01"
    assert VALIDATION_END == "2026-03-31"
    assert HOLDOUT_START == "2026-04-01"


def test_load_ohlcv_multi_file(tmp_path, monkeypatch):
    symbol_dir = tmp_path / "TEST_1m"
    symbol_dir.mkdir()

    # Create two monthly CSV files
    df1 = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=10, freq="1min"),
        "open": 100, "high": 105, "low": 95, "close": 102, "volume": 10
    })
    df2 = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01 00:10:00", periods=10, freq="1min"),
        "open": 102, "high": 108, "low": 101, "close": 107, "volume": 20
    })
    df1.to_csv(symbol_dir / "TEST_OHLC_202401.csv", index=False)
    df2.to_csv(symbol_dir / "TEST_OHLC_202402.csv", index=False)

    monkeypatch.setattr("src.data_loader.get_symbol_dir", lambda sym, tf: symbol_dir)
    res = load_ohlcv(symbol="TEST", timeframe="1m")
    assert len(res) == 20
    assert res.index.name == "datetime"
    assert res.index[0] == pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    assert res.index[-1] == pd.Timestamp("2024-01-01 00:19:00", tz="UTC")
