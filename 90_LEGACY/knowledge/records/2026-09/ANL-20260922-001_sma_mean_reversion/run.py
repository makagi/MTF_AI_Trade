"""
Reproduction script for ANL-20260922-001
Title: SMA -2 ATR Mean Reversion
"""
import sys
import json
import platform
from pathlib import Path
from datetime import datetime

import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_discovery_data

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['high'] if 'high' in df.columns else df['High']
    low = df['low'] if 'low' in df.columns else df['Low']
    close = df['close'] if 'close' in df.columns else df['Close']
    high_low = high - low
    high_close = (high - close.shift(1)).abs()
    low_close = (low - close.shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def main():
    record_dir = Path(__file__).resolve().parent
    config_file = record_dir / "config.yaml"
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    analysis_id = config["analysis_id"]
    dataset_id = config["dataset_id"]
    params = config.get("parameters", {})
    sma_period = params.get("sma_period", 233)
    atr_period = params.get("atr_period", 14)
    dev_threshold = params.get("deviation_threshold_atr", -2.0)
    horizon = params.get("horizon_bars", 24)

    print(f"[{analysis_id}] Loading discovery dataset...")
    df = load_discovery_data()
    
    close_col = 'close' if 'close' in df.columns else 'Close'
    
    # 1. Feature calculation
    df['SMA'] = df[close_col].rolling(sma_period).mean()
    df['ATR'] = calculate_atr(df, atr_period)
    df['ATR_Dev'] = (df[close_col] - df['SMA']) / df['ATR']
    
    # Forward return over horizon
    df['Fwd_Return'] = (df[close_col].shift(-horizon) - df[close_col]) / df[close_col]
    
    # 2. Filter condition: Extreme Downside Deviation (<= -2 ATR)
    df_clean = df.dropna(subset=['ATR_Dev', 'Fwd_Return']).copy()
    signals = df_clean[df_clean['ATR_Dev'] <= dev_threshold].copy()
    sample_count = len(signals)
    
    # 3. Calculate metrics
    returns = signals['Fwd_Return']
    win_rate = float((returns > 0).mean()) if sample_count > 0 else 0.0
    mean_return = float(returns.mean()) if sample_count > 0 else 0.0
    median_return = float(returns.median()) if sample_count > 0 else 0.0
    std_return = float(returns.std()) if sample_count > 0 else 0.0
    sharpe = float((mean_return / std_return) * np.sqrt(365 * 24 / horizon)) if std_return > 0 else 0.0
    
    baseline_returns = df_clean['Fwd_Return']
    baseline_mean = float(baseline_returns.mean())
    baseline_win_rate = float((baseline_returns > 0).mean())

    metrics_result = {
        "sample_count": sample_count,
        "win_rate": round(win_rate, 4),
        "mean_return": round(mean_return, 4),
        "median_return": round(median_return, 4),
        "std_return": round(std_return, 4),
        "sharpe_ratio_annualized": round(sharpe, 2),
        "baseline_win_rate": round(baseline_win_rate, 4),
        "baseline_mean_return": round(baseline_mean, 4),
        "alpha_expectancy_delta": round(mean_return - baseline_mean, 4),
    }

    # 4. Generate artifact chart
    artifacts_dir = record_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    chart_path = artifacts_dir / "mfe_distribution.png"

    plt.figure(figsize=(10, 5))
    plt.hist(returns * 100, bins=40, alpha=0.7, color='teal', edgecolor='black', label=f'Signals (<= {dev_threshold} ATR, N={sample_count})')
    plt.axvline(mean_return * 100, color='red', linestyle='--', linewidth=1.5, label=f'Signal Mean: {mean_return*100:.2f}%')
    plt.axvline(baseline_mean * 100, color='gray', linestyle=':', linewidth=1.5, label=f'Baseline Mean: {baseline_mean*100:.2f}%')
    plt.title(f"{analysis_id}: Forward {horizon}h Return Distribution on SMA-{sma_period} Deviation <= {dev_threshold} ATR", fontsize=12)
    plt.xlabel("Forward 24h Return (%)")
    plt.ylabel("Frequency")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"Chart saved to {chart_path}")

    # 5. Output metrics.json with execution metadata
    output = {
        "analysis_id": analysis_id,
        "dataset_id": dataset_id,
        "sample_count": sample_count,
        "metrics": metrics_result,
        "execution": {
            "python": platform.python_version(),
            "executed_at": datetime.now().astimezone().isoformat(),
        }
    }
    
    metrics_file = record_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to {metrics_file}")
    print(f"Summary: WinRate={win_rate:.1%}, MeanReturn={mean_return:.2%}, BaselineMean={baseline_mean:.2%}")

if __name__ == "__main__":
    main()
