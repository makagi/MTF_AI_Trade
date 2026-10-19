import pandas as pd
import pytest
from src.config import STANDARD_FRICTION_COST
from src.evaluation import evaluate_returns, evaluate_yearly_breakdown

def test_evaluate_returns_basic():
    # 3 trades:
    # 1: raw 0.010 -> net 0.010 - 0.004 = +0.006
    # 2: raw -0.002 -> net -0.002 - 0.004 = -0.006
    # 3: raw 0.008 -> net 0.008 - 0.004 = +0.004
    returns = pd.Series([0.010, -0.002, 0.008])
    mfe = pd.Series([0.015, 0.005, 0.012])
    mae = pd.Series([-0.002, -0.008, -0.001])

    metrics = evaluate_returns(returns, cost=STANDARD_FRICTION_COST, mfe=mfe, mae=mae)

    assert metrics["total_trades"] == 3
    # net returns mean: (0.006 - 0.006 + 0.004) / 3 = 0.004 / 3 = 0.001333...
    assert pytest.approx(metrics["net_mean_return"], rel=1e-3) == 0.001333
    assert pytest.approx(metrics["win_rate"], rel=1e-2) == 2 / 3
    assert "mfe_mean" in metrics
    assert "mae_mean" in metrics

def test_evaluate_yearly_breakdown():
    idx = pd.to_datetime(["2022-05-01", "2023-05-01"])
    returns = pd.Series([0.010, 0.008], index=idx)

    yearly = evaluate_yearly_breakdown(returns, cost=STANDARD_FRICTION_COST)
    assert len(yearly) == 2
    assert yearly.loc[2022, "trades"] == 1
    assert yearly.loc[2023, "trades"] == 1


def test_decluster_events():
    from src.evaluation import decluster_events
    # Sequence of triggers: [True, True, True, False, False, True, False, True]
    # cooldown = 3 bars
    mask = pd.Series([True, True, True, False, False, True, False, True])
    declustered = decluster_events(mask, cooldown_bars=3)
    # Expected:
    # idx 0: True (first)
    # idx 1: False (within 3 bars of 0)
    # idx 2: False (within 3 bars of 0)
    # idx 3: False
    # idx 4: False
    # idx 5: True (idx 5 - idx 0 = 5 >= 3)
    # idx 6: False
    # idx 7: False (idx 7 - idx 5 = 2 < 3)
    expected = [True, False, False, False, False, True, False, False]
    assert declustered.tolist() == expected


def test_calculate_cohens_d():
    from src.evaluation import calculate_cohens_d
    import numpy as np
    g1 = np.array([10.0, 11.0, 12.0])
    g2 = np.array([5.0, 6.0, 7.0])
    d = calculate_cohens_d(g1, g2)
    assert d > 0  # g1 is clearly larger than g2
    assert pytest.approx(d, rel=1e-2) == 5.0


def test_evaluate_multi_horizon():
    from src.evaluation import evaluate_multi_horizon
    idx = pd.date_range("2023-01-01", periods=100, freq="1h")
    df = pd.DataFrame({
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
    }, index=idx)
    mask = pd.Series(False, index=idx)
    mask.iloc[10] = True
    mask.iloc[20] = True

    results = evaluate_multi_horizon(df, mask, horizons=[4, 12])
    assert 4 in results
    assert 12 in results
    assert results[4]["total_trades"] == 2
    assert "e_ratio" in results[4]

