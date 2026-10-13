"""Canary Benchmark: SPEC-EVAL-001 Compliance

Tests that worker-generated evaluation metrics adhere strictly to SPEC-EVAL-001:
1. Friction cost deduction (0.40% round-trip)
2. Net expected return calculation
3. Required metric fields format
"""
import pytest
import numpy as np
import pandas as pd
from src.config import STANDARD_FRICTION_COST
from src.evaluation import evaluate_returns

def test_spec_eval_friction_cost_deduction(gold_standards):
    """Verify that net expected return and win rate incorporate 0.40% friction."""
    sample = gold_standards["spec_eval_sample"]
    raw_returns = pd.Series(sample["raw_returns"])
    
    assert np.isclose(sample["friction_cost_applied"], STANDARD_FRICTION_COST), "Friction cost must match SSOT 0.40%"
    
    metrics = evaluate_returns(raw_returns, cost=STANDARD_FRICTION_COST)
    
    assert metrics["total_trades"] == sample["sample_count"]
    assert np.isclose(metrics["gross_mean_return"], sample["gross_mean_return"], atol=1e-4)
    assert np.isclose(metrics["net_mean_return"], sample["net_mean_return"], atol=1e-4)
    assert np.isclose(metrics["win_rate"], sample["win_rate"], atol=1e-2)

def test_spec_eval_required_keys():
    """Verify that evaluate_returns produces mandatory SPEC-EVAL-001 keys."""
    sample_returns = pd.Series([0.015, -0.008, 0.022, -0.011, 0.004])
    mfe = pd.Series([0.020, 0.005, 0.025, 0.002, 0.008])
    mae = pd.Series([-0.002, -0.012, -0.001, -0.015, -0.003])
    
    metrics = evaluate_returns(sample_returns, cost=STANDARD_FRICTION_COST, mfe=mfe, mae=mae)
    
    required_keys = [
        "total_trades",
        "friction_cost_applied",
        "gross_mean_return",
        "net_mean_return",
        "win_rate",
        "profit_factor",
        "net_cumulative_return",
        "max_drawdown",
        "mfe_mean",
        "mae_mean"
    ]
    for key in required_keys:
        assert key in metrics, f"Missing mandatory SPEC-EVAL-001 key: {key}"
