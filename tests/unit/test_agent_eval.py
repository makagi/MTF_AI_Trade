"""Tests for Deterministic Gates CLI (tools/agent_eval.py)."""

from pathlib import Path
import json
import pytest
import yaml

from tools.agent_eval import (
    check_syntax,
    check_consistency,
    check_quantitative_contract,
    evaluate_experiment,
    EXPECTED_FRICTION_COST,
)


@pytest.fixture
def valid_exp_dir(tmp_path: Path):
    """Fixture providing a valid experiment directory conforming to all gates."""
    d = tmp_path / "10-valid-exp"
    d.mkdir()

    # config.yaml
    config = {
        "issue": 10,
        "title": "Valid Experiment",
        "symbol": "BTCUSD",
        "timeframe": "1h",
    }
    with open(d / "config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f)

    # run.py
    run_code = """
import pandas as pd
from src.evaluation import evaluate_returns

def run():
    print("running")

if __name__ == "__main__":
    run()
"""
    with open(d / "run.py", "w", encoding="utf-8") as f:
        f.write(run_code)

    # record.md
    record_content = """# Experiment
**Status:** In Progress
"""
    with open(d / "record.md", "w", encoding="utf-8") as f:
        f.write(record_content)

    # metrics.json
    metrics = {
        "total_trades": 150,
        "friction_cost_applied": EXPECTED_FRICTION_COST,
        "gross_mean_return": 0.008,
        "net_mean_return": 0.004,
        "win_rate": 0.55,
        "profit_factor": 1.4,
        "max_drawdown": 0.08,
    }
    with open(d / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f)

    return d


def test_valid_experiment_passes_all_gates(valid_exp_dir: Path):
    passed, violations = evaluate_experiment(valid_exp_dir)
    assert passed, f"Expected pass but got violations: {[str(v) for v in violations]}"
    assert len(violations) == 0


def test_syntax_gate_detects_syntax_error(valid_exp_dir: Path):
    run_file = valid_exp_dir / "run.py"
    run_file.write_text("def broken_syntax(:", encoding="utf-8")

    violations = check_syntax(run_file)
    assert len(violations) == 1
    assert violations[0].category == "Syntax"
    assert "Syntax error" in violations[0].message


def test_leakage_gate_detects_include_holdout(valid_exp_dir: Path):
    run_file = valid_exp_dir / "run.py"
    leak_code = """
from src.data_loader import load_ohlcv
df = load_ohlcv('BTCUSD', '1h', include_holdout=True)
"""
    run_file.write_text(leak_code, encoding="utf-8")

    violations = check_syntax(run_file)
    assert any(v.category == "LeakageGate" for v in violations)


def test_consistency_gate_detects_missing_file(valid_exp_dir: Path):
    (valid_exp_dir / "config.yaml").unlink()

    violations = check_consistency(valid_exp_dir)
    assert any("config.yaml" in v.message for v in violations)


def test_quant_gate_detects_missing_metrics(valid_exp_dir: Path):
    (valid_exp_dir / "metrics.json").unlink()

    violations = check_quantitative_contract(valid_exp_dir)
    assert any("metrics.json does not exist" in v.message for v in violations)


def test_quant_gate_detects_wrong_friction_cost(valid_exp_dir: Path):
    metrics_file = valid_exp_dir / "metrics.json"
    with open(metrics_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Change friction cost from 0.0040 to 0.0010 (wrong)
    data["friction_cost_applied"] = 0.0010
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    violations = check_quantitative_contract(valid_exp_dir)
    assert any("does not match SPEC-EVAL-001" in v.message for v in violations)


def test_quant_gate_detects_zero_trades(valid_exp_dir: Path):
    metrics_file = valid_exp_dir / "metrics.json"
    with open(metrics_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["total_trades"] = 0
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    violations = check_quantitative_contract(valid_exp_dir)
    assert any("total_trades is 0" in v.message for v in violations)
