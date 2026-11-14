"""Experiment simulation script for Issue #129: Full Pyramid Curvature Divergence."""

from __future__ import annotations

import json
from pathlib import Path
import yaml
from src.data_loader import load_discovery_data
from src.evaluation import evaluate_returns, evaluate_yearly_breakdown

EXP_DIR = Path(__file__).resolve().parent

def main() -> None:
    # 1. Load config
    with open(EXP_DIR / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    symbol = config.get("symbol", "BTCUSD")
    timeframe = config.get("timeframe", "1h")

    # 2. Load Discovery data
    print(f"Loading {symbol} {timeframe} data...")
    df = load_discovery_data(symbol, timeframe)
    print(f"Data range: {df.index.min()} to {df.index.max()} ({len(df)} bars)")

    # 3. Execute strategy / analysis logic
    # TODO: Implement experiment logic here
    # Example dummy forward returns for illustration:
    returns = df["Close"].pct_change().dropna()

    # 4. Evaluate metrics (SPEC-EVAL-001)
    metrics = evaluate_returns(returns)
    yearly = evaluate_yearly_breakdown(returns)

    print("\nEvaluation Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    print("\nYearly Breakdown:")
    print(yearly)

    # 5. Save metrics
    with open(EXP_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved metrics to {EXP_DIR / 'metrics.json'}")

if __name__ == "__main__":
    main()
