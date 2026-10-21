"""EXP-68: Unreachable Envelope & Boundary Breach Dynamics across 1h and 1m Scales.

Implements SPEC-EVAL-001 v0.4.0 and SPEC-FEAT-001 v0.3.0.
Calculates 90%, 95%, 99% upper excursion limits across multi-scale horizons (1h and 1m),
verifies fractal scaling power-law behavior, assesses cross-period boundary stability,
and analyzes Boundary Breach (Cascade vs Sweep) dynamics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.data_loader import load_ohlcv
from src.features import (
    calculate_sma,
    calculate_atr,
    calculate_afs,
    calculate_fanout_velocity,
    calculate_regime_age,
    calculate_level_test_count,
)
from src.evaluation import decluster_events


def compute_excursions(df: pd.DataFrame, horizons: list[int], atr_series: pd.Series) -> dict[str, pd.Series]:
    """Compute vectorized future upside and downside excursions (% and ATR-normalized)."""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    res = {}
    for h in horizons:
        fut_max = high.iloc[::-1].rolling(h).max().iloc[::-1].shift(-1)
        fut_min = low.iloc[::-1].rolling(h).min().iloc[::-1].shift(-1)
        res[f"up_pct_{h}"] = (fut_max - close) / close
        res[f"down_pct_{h}"] = (close - fut_min) / close
        res[f"up_atr_{h}"] = (fut_max - close) / (atr_series + 1e-8)
        res[f"down_atr_{h}"] = (close - fut_min) / (atr_series + 1e-8)
        res[f"fut_close_{h}"] = close.shift(-h)
    return res


def extract_quantiles(series: pd.Series, quantiles: list[float] = [0.90, 0.95, 0.99]) -> dict[str, float]:
    clean = series.dropna()
    if len(clean) == 0:
        return {f"q{int(q*100)}": 0.0 for q in quantiles}
    return {f"q{int(q*100)}": float(np.round(clean.quantile(q), 4)) for q in quantiles}


def main():
    print("=== Starting EXP-68: Unreachable Envelope & Boundary Breach Analysis ===")
    exp_dir = Path(__file__).resolve().parent
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # Part 1: 1h Scale Unreachable Envelope (HYP-BOUND-1)
    # =========================================================================
    print("\n--- Part 1: Computing 1h Scale Features and Envelopes ---")
    df_1h = load_ohlcv("BTCUSD", "1h").loc["2020-01-01":"2025-04-30"].copy()
    close_1h = df_1h["close"]
    high_1h = df_1h["high"]
    low_1h = df_1h["low"]
    atr_1h = calculate_atr(df_1h, 24)

    horizons_1h = [4, 12, 24, 72]
    excursions_1h = compute_excursions(df_1h, horizons_1h, atr_1h)

    # 1h Features
    smas_1h = {p: calculate_sma(close_1h, p) for p in [8, 13, 21, 34, 55, 89, 144, 233, 377]}
    afs_df_1h, afs_order_1h, _ = calculate_afs(df_1h, [13, 21, 34])
    age_df_1h = calculate_regime_age(df_1h)
    macro_age_bars = age_df_1h["macro_age_bars"]
    roll_q25 = macro_age_bars.rolling(720, min_periods=72).quantile(0.25).bfill()
    macro_age_ratio = macro_age_bars / roll_q25.replace(0, np.nan)
    fanout_1h = calculate_fanout_velocity(df_1h, fast_period=21, slow_period=89, atr_period=24)
    slope_55_1h = smas_1h[55].diff(5)
    slope_144_1h = smas_1h[144].diff(5)

    # 1h Overhead Wall Density (SMA 34..377 within +1.5 ATR with test_cnt <= 1)
    wall_count_up_1h = pd.Series(0, index=df_1h.index)
    for p in [34, 55, 89, 144, 233, 377]:
        sma = smas_1h[p]
        test_cnt = calculate_level_test_count(df_1h, sma, window_bars=72, atr_series=atr_1h)
        in_range = (sma > close_1h) & (sma <= close_1h + 1.5 * atr_1h) & (test_cnt <= 1)
        wall_count_up_1h += in_range.astype(int)

    # Context 1: Fortress Cap
    cond_fortress_1h = (wall_count_up_1h >= 2) & (fanout_1h <= 0)
    # Context 2: Energy Starved
    cond_starved_1h = (macro_age_ratio > 2.0) & (fanout_1h <= 0)
    # Context 3: Safe Floor (Bullish Alignment Initial Stage)
    cond_safe_floor_1h = (afs_order_1h == 2) & (macro_age_ratio <= 2.0) & (slope_55_1h > 0)

    # De-cluster (24h cooldown)
    mask_fortress_1h = decluster_events(cond_fortress_1h, 24)
    mask_starved_1h = decluster_events(cond_starved_1h, 24)
    mask_safe_floor_1h = decluster_events(cond_safe_floor_1h, 24)

    # K-038 MVC Setups for Winner vs Loser Safe Floor
    breakout_meso = (close_1h > smas_1h[55]) & (close_1h.shift(1) <= smas_1h[55].shift(1))
    mvc_raw = breakout_meso & (macro_age_ratio <= 2.0) & (afs_order_1h == 2)
    mask_mvc = decluster_events(mvc_raw, 24)
    ret_72_mvc = (close_1h.shift(-72) - close_1h) / close_1h - 0.0040
    mvc_winner_mask = mask_mvc & (ret_72_mvc > 0)
    mvc_loser_mask = mask_mvc & (ret_72_mvc <= 0)

    print(f"1h Events: Fortress={mask_fortress_1h.sum()}, Starved={mask_starved_1h.sum()}, Safe Floor={mask_safe_floor_1h.sum()}, MVC={mask_mvc.sum()} (Win={mvc_winner_mask.sum()}, Loss={mvc_loser_mask.sum()})")

    # Quantiles for 1h contexts
    metrics_1h = {"horizons": {}}
    for h in horizons_1h:
        h_key = str(h)
        metrics_1h["horizons"][h_key] = {
            "baseline": {
                "up_atr": extract_quantiles(excursions_1h[f"up_atr_{h}"]),
                "up_pct": extract_quantiles(excursions_1h[f"up_pct_{h}"]),
                "down_atr": extract_quantiles(excursions_1h[f"down_atr_{h}"]),
                "down_pct": extract_quantiles(excursions_1h[f"down_pct_{h}"]),
            },
            "fortress_cap": {
                "events": int(mask_fortress_1h.sum()),
                "up_atr": extract_quantiles(excursions_1h[f"up_atr_{h}"][mask_fortress_1h]),
                "up_pct": extract_quantiles(excursions_1h[f"up_pct_{h}"][mask_fortress_1h]),
            },
            "energy_starved": {
                "events": int(mask_starved_1h.sum()),
                "up_atr": extract_quantiles(excursions_1h[f"up_atr_{h}"][mask_starved_1h]),
                "up_pct": extract_quantiles(excursions_1h[f"up_pct_{h}"][mask_starved_1h]),
            },
            "safe_floor": {
                "events": int(mask_safe_floor_1h.sum()),
                "down_atr": extract_quantiles(excursions_1h[f"down_atr_{h}"][mask_safe_floor_1h]),
                "down_pct": extract_quantiles(excursions_1h[f"down_pct_{h}"][mask_safe_floor_1h]),
            },
            "mvc_safe_floor": {
                "winner_down_atr": extract_quantiles(excursions_1h[f"down_atr_{h}"][mvc_winner_mask]),
                "loser_down_atr": extract_quantiles(excursions_1h[f"down_atr_{h}"][mvc_loser_mask]),
            },
        }

    # Cross-Period Stability (P1 Bull, P2 Bear, P3 Mixed) for 1h
    periods = {
        "P1_Bull": ("2020-01-01", "2021-12-31"),
        "P2_Bear": ("2022-01-01", "2022-12-31"),
        "P3_Mixed": ("2023-01-01", "2025-04-30"),
    }
    metrics_period_stability = {}
    for p_name, (p_start, p_end) in periods.items():
        p_mask = (df_1h.index >= pd.Timestamp(p_start, tz="UTC")) & (df_1h.index <= pd.Timestamp(p_end, tz="UTC"))
        metrics_period_stability[p_name] = {}
        for h in [12, 24, 72]:
            sub_up = excursions_1h[f"up_atr_{h}"][p_mask]
            sub_fort = excursions_1h[f"up_atr_{h}"][p_mask & mask_fortress_1h]
            sub_safe = excursions_1h[f"down_atr_{h}"][p_mask & mask_safe_floor_1h]
            metrics_period_stability[p_name][str(h)] = {
                "baseline_up_atr_q95": float(np.round(sub_up.quantile(0.95), 4)),
                "fortress_up_atr_q95": float(np.round(sub_fort.quantile(0.95), 4)) if len(sub_fort) > 0 else 0.0,
                "safe_floor_down_atr_q95": float(np.round(sub_safe.quantile(0.95), 4)) if len(sub_safe) > 0 else 0.0,
            }

    # =========================================================================
    # Part 2: 1m Scale Unreachable Envelope (HYP-BOUND-2)
    # =========================================================================
    print("\n--- Part 2: Computing 1m Scale Features and Envelopes ---")
    df_1m = load_ohlcv("BTCUSD", "1m")
    close_1m = df_1m["close"]
    high_1m = df_1m["high"]
    low_1m = df_1m["low"]
    atr_1m = calculate_atr(df_1m, 60)

    horizons_1m = [15, 30, 60, 240]
    excursions_1m = compute_excursions(df_1m, horizons_1m, atr_1m)

    sma_21m = calculate_sma(close_1m, 21)
    sma_55m = calculate_sma(close_1m, 55)
    sma_233m = calculate_sma(close_1m, 233)
    sma_1440m = calculate_sma(close_1m, 1440)

    fanout_1m = (sma_55m - sma_233m).diff() / (atr_1m + 1e-8)
    wall_up_1m = ((sma_233m > close_1m) & (sma_233m <= close_1m + 1.5 * atr_1m)).astype(int) + \
                 ((sma_1440m > close_1m) & (sma_1440m <= close_1m + 1.5 * atr_1m)).astype(int)
    cond_fortress_1m = (wall_up_1m >= 1) & (fanout_1m <= 0)

    metrics_1m = {"horizons": {}}
    for tau in horizons_1m:
        tau_key = str(tau)
        metrics_1m["horizons"][tau_key] = {
            "baseline": {
                "up_atr": extract_quantiles(excursions_1m[f"up_atr_{tau}"]),
                "up_pct": extract_quantiles(excursions_1m[f"up_pct_{tau}"]),
                "down_atr": extract_quantiles(excursions_1m[f"down_atr_{tau}"]),
                "down_pct": extract_quantiles(excursions_1m[f"down_pct_{tau}"]),
            },
            "fortress_cap": {
                "events": int(cond_fortress_1m.sum()),
                "up_atr": extract_quantiles(excursions_1m[f"up_atr_{tau}"][cond_fortress_1m]),
                "up_pct": extract_quantiles(excursions_1m[f"up_pct_{tau}"][cond_fortress_1m]),
            },
        }

    # =========================================================================
    # Part 3: Fractal Scaling Law Analysis (Power-Law Regression)
    # =========================================================================
    print("\n--- Part 3: Evaluating Fractal Scaling Power-Law Behavior ---")
    # Hours array: 1m scale (0.25, 0.5, 1.0, 4.0), 1h scale (4.0, 12.0, 24.0, 72.0)
    scaling_data = []
    for tau in horizons_1m:
        h_equiv = tau / 60.0
        q95 = metrics_1m["horizons"][str(tau)]["baseline"]["up_pct"]["q95"]
        scaling_data.append({"scale": "1m", "horizon_hours": h_equiv, "q95_pct": q95})
    for h in horizons_1h:
        q95 = metrics_1h["horizons"][str(h)]["baseline"]["up_pct"]["q95"]
        scaling_data.append({"scale": "1h", "horizon_hours": float(h), "q95_pct": q95})

    df_scale = pd.DataFrame(scaling_data).sort_values("horizon_hours")
    log_h = np.log(df_scale["horizon_hours"].values)
    log_q95 = np.log(df_scale["q95_pct"].values)
    # Fit power law ln(q95) = ln(c) + alpha * ln(h)
    poly = np.polyfit(log_h, log_q95, 1)
    alpha = float(np.round(poly[0], 4))
    log_c = float(np.round(poly[1], 4))
    c_coeff = float(np.round(np.exp(log_c), 4))
    r_squared = float(np.round(np.corrcoef(log_h, log_q95)[0, 1] ** 2, 4))
    print(f"Fractal Scaling Fit: alpha = {alpha}, c = {c_coeff}, R^2 = {r_squared} (Random Walk benchmark = 0.50)")

    metrics_fractal = {
        "alpha_exponent": alpha,
        "prefactor_c": c_coeff,
        "r_squared": r_squared,
        "random_walk_alpha_benchmark": 0.50,
        "sub_diffusion_confirmed": bool(alpha < 0.50),
        "data_points": df_scale.to_dict(orient="records"),
    }

    # =========================================================================
    # Part 4: Boundary Breach Dynamics (Cascade vs Sweep) (HYP-BOUND-3)
    # =========================================================================
    print("\n--- Part 4: Analyzing Boundary Breach Dynamics (12h Horizon) ---")
    tau_breach = 12
    up_atr_breach = excursions_1h[f"up_atr_{tau_breach}"]
    fut_close_breach = excursions_1h[f"fut_close_{tau_breach}"]
    b95_12h = metrics_1h["horizons"][str(tau_breach)]["baseline"]["up_atr"]["q95"]

    breach_mask = up_atr_breach > b95_12h
    fut_ret = (fut_close_breach - close_1h) / (atr_1h + 1e-8)
    cascade_mask = breach_mask & (fut_ret > 0.5 * b95_12h)
    sweep_mask = breach_mask & (fut_ret < 0)
    neutral_mask = breach_mask & (~cascade_mask) & (~sweep_mask)

    total_breaches = int(breach_mask.sum())
    cascade_count = int(cascade_mask.sum())
    sweep_count = int(sweep_mask.sum())
    neutral_count = int(neutral_mask.sum())

    cascade_macro_aligned = float(np.round((slope_144_1h[cascade_mask] > 0).mean() * 100, 2))
    sweep_macro_aligned = float(np.round((slope_144_1h[sweep_mask] > 0).mean() * 100, 2))
    sweep_macro_counter = float(np.round(100.0 - sweep_macro_aligned, 2))

    bar_range_norm = (high_1h - low_1h) / (atr_1h + 1e-8)
    cascade_vol_spike = float(np.round(bar_range_norm[cascade_mask].mean(), 2))
    sweep_vol_spike = float(np.round(bar_range_norm[sweep_mask].mean(), 2))

    metrics_breach = {
        "horizon_hours": tau_breach,
        "boundary_q95_atr": b95_12h,
        "total_breaches": total_breaches,
        "cascade": {
            "count": cascade_count,
            "ratio_pct": float(np.round(cascade_count / total_breaches * 100, 2)),
            "macro_aligned_pct": cascade_macro_aligned,
            "entry_bar_range_atr": cascade_vol_spike,
        },
        "sweep": {
            "count": sweep_count,
            "ratio_pct": float(np.round(sweep_count / total_breaches * 100, 2)),
            "macro_counter_pct": sweep_macro_counter,
            "entry_bar_range_atr": sweep_vol_spike,
        },
        "neutral": {
            "count": neutral_count,
            "ratio_pct": float(np.round(neutral_count / total_breaches * 100, 2)),
        },
    }

    # Combine All Metrics
    final_metrics = {
        "experiment_id": "EXP-68",
        "description": "Unreachable Envelope and Boundary Breach Dynamics across 1h and 1m Scales",
        "1h_envelope": metrics_1h,
        "1m_envelope": metrics_1m,
        "cross_period_stability": metrics_period_stability,
        "fractal_scaling": metrics_fractal,
        "boundary_breach_dynamics": metrics_breach,
    }

    metrics_path = exp_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(final_metrics, f, indent=2, ensure_ascii=False)
    print(f"Saved complete metrics to {metrics_path}")

    # =========================================================================
    # Part 5: Generating High-Resolution Diagnostic Plots
    # =========================================================================
    print("\n--- Part 5: Generating Diagnostic Visualizations ---")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    # Plot 1: Multi-Scale Unreachable Envelopes
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    # 1h Plot
    h_labels = [4, 12, 24, 72]
    base_up_95 = [metrics_1h["horizons"][str(h)]["baseline"]["up_atr"]["q95"] for h in h_labels]
    fort_up_95 = [metrics_1h["horizons"][str(h)]["fortress_cap"]["up_atr"]["q95"] for h in h_labels]
    safe_down_95 = [metrics_1h["horizons"][str(h)]["safe_floor"]["down_atr"]["q95"] for h in h_labels]

    x = np.arange(len(h_labels))
    width = 0.25
    axes[0].bar(x - width, base_up_95, width, label="Baseline 95% Up Ceiling", color="#4a90e2", alpha=0.85)
    axes[0].bar(x, fort_up_95, width, label="Fortress Cap 95% Up Ceiling", color="#d9534f", alpha=0.85)
    axes[0].bar(x + width, safe_down_95, width, label="Safe Floor 95% Down Boundary", color="#5cb85c", alpha=0.85)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([f"{h}h" for h in h_labels], fontsize=11)
    axes[0].set_ylabel("Boundary Distance (ATR)", fontsize=12)
    axes[0].set_title("1h Scale: Unreachable Envelopes across Horizons", fontsize=13, fontweight="bold")
    axes[0].legend(frameon=True)

    # 1m Plot
    m_labels = [15, 30, 60, 240]
    base_m_95 = [metrics_1m["horizons"][str(tau)]["baseline"]["up_atr"]["q95"] for tau in m_labels]
    fort_m_95 = [metrics_1m["horizons"][str(tau)]["fortress_cap"]["up_atr"]["q95"] for tau in m_labels]
    x_m = np.arange(len(m_labels))
    axes[1].bar(x_m - width / 2, base_m_95, width, label="1m Baseline 95% Up Ceiling", color="#5bc0de", alpha=0.85)
    axes[1].bar(x_m + width / 2, fort_m_95, width, label="1m Fortress Cap 95% Up Ceiling", color="#f0ad4e", alpha=0.85)
    axes[1].set_xticks(x_m)
    axes[1].set_xticklabels([f"{m}m" for m in m_labels], fontsize=11)
    axes[1].set_ylabel("Boundary Distance (1m ATR_60)", fontsize=12)
    axes[1].set_title("1m Scale: Micro Fortress Envelope Compression", fontsize=13, fontweight="bold")
    axes[1].legend(frameon=True)

    plt.tight_layout()
    p1_path = plots_dir / "01_multi_scale_unreachable_envelopes.png"
    plt.savefig(p1_path, dpi=300)
    plt.close()
    print(f"Saved: {p1_path}")

    # Plot 2: Fractal Scaling Power-Law Fit
    plt.figure(figsize=(9, 6))
    h_vals = df_scale["horizon_hours"].values
    q95_pct_vals = df_scale["q95_pct"].values * 100  # in %
    fit_curve = (c_coeff * (h_vals ** alpha)) * 100
    rw_curve = (df_scale["q95_pct"].iloc[0] * ((h_vals / h_vals[0]) ** 0.50)) * 100

    plt.loglog(h_vals, q95_pct_vals, "o", markersize=8, color="#2c3e50", label="Empirical 95% Excursion Limit")
    plt.loglog(h_vals, fit_curve, "-", color="#e74c3c", linewidth=2.5, label=f"Empirical Power Law: $\\alpha={alpha:.3f}$ ($R^2={r_squared:.3f}$)")
    plt.loglog(h_vals, rw_curve, "--", color="#7f8c8d", linewidth=1.8, label="Random Walk Benchmark: $\\alpha=0.50$")

    plt.xlabel("Horizon (Hours, Log Scale)", fontsize=12)
    plt.ylabel("95% Max Upward Excursion (%, Log Scale)", fontsize=12)
    plt.title(f"Fractal Scaling of Reach Boundaries (15m to 72h): Sub-diffusion $\\alpha = {alpha:.3f}$", fontsize=13, fontweight="bold")
    plt.grid(True, which="both", ls="--", alpha=0.5)
    plt.legend(frameon=True, fontsize=11)
    plt.tight_layout()
    p2_path = plots_dir / "02_fractal_scaling_power_law.png"
    plt.savefig(p2_path, dpi=300)
    plt.close()
    print(f"Saved: {p2_path}")

    # Plot 3: Cross-Period Boundary Stability
    fig, ax = plt.subplots(figsize=(10, 5.5))
    h_eval = [12, 24, 72]
    x_p = np.arange(len(h_eval))
    width_p = 0.25

    p1_vals = [metrics_period_stability["P1_Bull"][str(h)]["baseline_up_atr_q95"] for h in h_eval]
    p2_vals = [metrics_period_stability["P2_Bear"][str(h)]["baseline_up_atr_q95"] for h in h_eval]
    p3_vals = [metrics_period_stability["P3_Mixed"][str(h)]["baseline_up_atr_q95"] for h in h_eval]

    ax.bar(x_p - width_p, p1_vals, width_p, label="P1 (2020-21 Bull)", color="#3498db")
    ax.bar(x_p, p2_vals, width_p, label="P2 (2022 Bear)", color="#e74c3c")
    ax.bar(x_p + width_p, p3_vals, width_p, label="P3 (2023-25 Mixed)", color="#2ecc71")

    ax.set_xticks(x_p)
    ax.set_xticklabels([f"{h}h" for h in h_eval], fontsize=11)
    ax.set_ylabel("95% Upward Excursion Limit (ATR)", fontsize=12)
    ax.set_title("Cross-Period Boundary Stability: Invariant ATR Multipliers across Market Regimes", fontsize=13, fontweight="bold")
    ax.legend(frameon=True, fontsize=11)
    plt.tight_layout()
    p3_path = plots_dir / "03_cross_period_boundary_stability.png"
    plt.savefig(p3_path, dpi=300)
    plt.close()
    print(f"Saved: {p3_path}")

    # Plot 4: Boundary Breach Cascade vs Sweep
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    categories = ["Cascade\n(True Breakout)", "Sweep\n(Liquidity Grab)", "Neutral\n(Drift)"]
    counts = [cascade_count, sweep_count, neutral_count]
    colors = ["#27ae60", "#c0392b", "#7f8c8d"]

    axes[0].pie(counts, labels=categories, autopct="%1.1f%%", startangle=140, colors=colors, textprops={"fontsize": 11, "fontweight": "bold"})
    axes[0].set_title(f"12h Boundary Breach Distribution ($N={total_breaches}$)", fontsize=13, fontweight="bold")

    # Macro Alignment in Cascade vs Sweep
    align_labels = ["Cascade", "Sweep"]
    macro_align = [cascade_macro_aligned, sweep_macro_aligned]
    macro_counter = [100.0 - cascade_macro_aligned, sweep_macro_counter]

    axes[1].bar(align_labels, macro_align, label="Macro Aligned (Slope > 0)", color="#2980b9", width=0.45)
    axes[1].bar(align_labels, macro_counter, bottom=macro_align, label="Macro Counter (Slope <= 0)", color="#e67e22", width=0.45)
    axes[1].set_ylabel("Percentage (%)", fontsize=12)
    axes[1].set_title("Macro Alignment: Cascade vs Sweep Divergence", fontsize=13, fontweight="bold")
    axes[1].legend(loc="upper right", frameon=True)

    plt.tight_layout()
    p4_path = plots_dir / "04_boundary_breach_cascade_vs_sweep.png"
    plt.savefig(p4_path, dpi=300)
    plt.close()
    print(f"Saved: {p4_path}")

    print("\n=== EXP-68 Execution Completed Successfully ===")


if __name__ == "__main__":
    main()
