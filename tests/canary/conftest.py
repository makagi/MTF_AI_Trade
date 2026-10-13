import json
from pathlib import Path
import pytest
import pandas as pd

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def synthetic_ohlcv():
    csv_path = FIXTURES_DIR / "synthetic_ohlcv.csv"
    assert csv_path.exists(), f"Missing fixture: {csv_path}"
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

@pytest.fixture
def gold_standards():
    json_path = FIXTURES_DIR / "gold_standards.json"
    assert json_path.exists(), f"Missing fixture: {json_path}"
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)
