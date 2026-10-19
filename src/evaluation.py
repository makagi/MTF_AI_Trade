"""Evaluation metrics module for MTF_AI_Trade.

Implements mandatory metrics calculation (Sample size, Net Expected Return,
MFE/MAE summary, Yearly breakdown, Max Drawdown) according to
02_SPECIFICATIONS/evaluation.md (SPEC-EVAL-001).
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from src.config import STANDARD_FRICTION_COST


def calculate_max_drawdown(cumulative_returns: pd.Series) -> float:
    """Calculate maximum drawdown from a cumulative return series (1-based equity)."""
    if len(cumulative_returns) == 0:
        return 0.0
    equity = (1.0 + cumulative_returns).cumprod() if (cumulative_returns > -1.0).all() else 1.0 + cumulative_returns.cumsum()
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(drawdown.min())


def evaluate_returns(
    returns: pd.Series,
    cost: float = STANDARD_FRICTION_COST,
    mfe: pd.Series | None = None,
    mae: pd.Series | None = None,
) -> dict[str, Any]:
    """Calculate mandatory evaluation metrics for trade returns."""
    clean_returns = returns.dropna()
    n_trades = len(clean_returns)

    if n_trades == 0:
        return {
            "total_trades": 0,
            "gross_mean_return": 0.0,
            "net_mean_return": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        }

    net_returns = clean_returns - cost
    wins = net_returns[net_returns > 0]
    losses = net_returns[net_returns < 0]

    gross_mean = float(clean_returns.mean())
    net_mean = float(net_returns.mean())
    win_rate = float(len(wins) / n_trades)

    gross_profit = float(wins.sum())
    gross_loss = float(abs(losses.sum()))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # Max Drawdown based on cumulative net return
    equity_curve = net_returns.cumsum()
    running_max = equity_curve.cummax()
    drawdown = equity_curve - running_max
    max_dd = float(abs(drawdown.min())) if len(drawdown) > 0 else 0.0

    metrics: dict[str, Any] = {
        "total_trades": n_trades,
        "friction_cost_applied": cost,
        "gross_mean_return": gross_mean,
        "net_mean_return": net_mean,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "net_cumulative_return": float(net_returns.sum()),
        "max_drawdown": max_dd,
    }

    if mfe is not None and len(mfe.dropna()) > 0:
        clean_mfe = mfe.dropna()
        metrics["mfe_mean"] = float(clean_mfe.mean())
        metrics["mfe_median"] = float(clean_mfe.median())

    if mae is not None and len(mae.dropna()) > 0:
        clean_mae = mae.dropna()
        metrics["mae_mean"] = float(clean_mae.mean())
        metrics["mae_median"] = float(clean_mae.median())

    return metrics


def evaluate_yearly_breakdown(
    returns: pd.Series,
    cost: float = STANDARD_FRICTION_COST,
) -> pd.DataFrame:
    """Calculate annual performance breakdown to detect non-stationarity and overfitting."""
    clean_returns = returns.dropna()
    if not isinstance(clean_returns.index, pd.DatetimeIndex):
        raise TypeError("Returns series must have a DatetimeIndex for yearly breakdown.")

    records = []
    for year, group in clean_returns.groupby(clean_returns.index.year):
        net_group = group - cost
        n_trades = len(group)
        win_count = (net_group > 0).sum()

        wins = net_group[net_group > 0]
        losses = net_group[net_group < 0]
        gross_profit = float(wins.sum())
        gross_loss = float(abs(losses.sum()))
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

        records.append({
            "year": int(year),
            "trades": n_trades,
            "gross_mean": float(group.mean()),
            "net_mean": float(net_group.mean()),
            "win_rate": float(win_count / n_trades) if n_trades > 0 else 0.0,
            "net_total": float(net_group.sum()),
            "profit_factor": pf,
        })

    return pd.DataFrame(records).set_index("year")


def decluster_events(
    signal_mask: pd.Series,
    cooldown_bars: int = 24,
) -> pd.Series:
    """Decluster overlapping/consecutive signal triggers to obtain independent samples.

    Enforces a mandatory cooldown period so that subsequent triggers within
    `cooldown_bars` of a preceding trigger are filtered out.
    """
    clean_mask = signal_mask.fillna(False).astype(bool)
    indices = np.where(clean_mask.values)[0]
    if len(indices) == 0:
        return pd.Series(False, index=signal_mask.index)

    declustered_indices = []
    last_idx = -cooldown_bars - 1
    for idx in indices:
        if idx - last_idx >= cooldown_bars:
            declustered_indices.append(idx)
            last_idx = idx

    out = pd.Series(False, index=signal_mask.index)
    out.iloc[declustered_indices] = True
    return out


def calculate_cohens_d(
    group1: np.ndarray | pd.Series,
    group2: np.ndarray | pd.Series,
) -> float:
    """Calculate Cohen's d effect size between two groups."""
    g1 = np.asarray(group1, dtype=float)
    g2 = np.asarray(group2, dtype=float)
    g1 = g1[~np.isnan(g1)]
    g2 = g2[~np.isnan(g2)]

    n1, n2 = len(g1), len(g2)
    if n1 < 2 or n2 < 2:
        return 0.0
    var1, var2 = np.var(g1, ddof=1), np.var(g2, ddof=1)
    pooled_se = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_se == 0 or np.isnan(pooled_se):
        return 0.0
    return float((np.mean(g1) - np.mean(g2)) / pooled_se)


def evaluate_multi_horizon(
    df: pd.DataFrame,
    entry_mask: pd.Series,
    horizons: list[int] | None = None,
    cost: float = STANDARD_FRICTION_COST,
    is_short: bool = False,
) -> dict[int, dict[str, Any]]:
    """Evaluate performance across multiple forward horizons to observe feature decay profile.

    Computes Net Return, MFE, MAE, Win Rate, and E-Ratio (MFE/MAE) for each horizon.
    """
    if horizons is None:
        horizons = [4, 12, 24, 72]

    entries = df[entry_mask.fillna(False).astype(bool)].copy()
    if len(entries) == 0:
        return {h: {"total_trades": 0} for h in horizons}

    close = df["close"]
    high = df["high"]
    low = df["low"]

    results = {}
    for h in horizons:
        if is_short:
            fwd_ret = -(close.shift(-h) - close) / close
            fwd_high = high.shift(-1).rolling(h).max().shift(-(h - 1))
            fwd_low = low.shift(-1).rolling(h).min().shift(-(h - 1))
            mfe = (close - fwd_low) / close
            mae = (fwd_high - close) / close
        else:
            fwd_ret = (close.shift(-h) - close) / close
            fwd_high = high.shift(-1).rolling(h).max().shift(-(h - 1))
            fwd_low = low.shift(-1).rolling(h).min().shift(-(h - 1))
            mfe = (fwd_high - close) / close
            mae = (close - fwd_low) / close

        entries_h = entries.index.intersection(fwd_ret.dropna().index)
        sub_ret = fwd_ret.loc[entries_h]
        sub_mfe = mfe.loc[entries_h]
        sub_mae = mae.loc[entries_h]

        metrics = evaluate_returns(sub_ret, cost=cost, mfe=sub_mfe, mae=sub_mae)
        mean_mfe = metrics.get("mfe_mean", 0.0)
        mean_mae = metrics.get("mae_mean", 0.0)
        e_ratio = float(mean_mfe / mean_mae) if mean_mae > 0 else 0.0
        metrics["e_ratio"] = e_ratio
        metrics["horizon_bars"] = h
        results[h] = metrics

    return results

