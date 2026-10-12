import pandas as pd
import pytest
from src.config import HOLDOUT_START
from src.data_loader import load_ohlcv

def test_holdout_start_constant():
    # Verify SPEC-EVAL-001 constant
    assert HOLDOUT_START == "2025-01-01"
