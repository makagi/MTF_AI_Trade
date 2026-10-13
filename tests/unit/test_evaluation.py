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
