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
