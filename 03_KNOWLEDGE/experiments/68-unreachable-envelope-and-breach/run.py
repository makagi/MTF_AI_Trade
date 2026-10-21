"""EXP-68: Unreachable Envelope & Boundary Breach Dynamics across 1h and 1m Scales.

Audited and Corrected for Issue #71:
1. Strict SPEC-FEAT-001 feature definitions:
   - Macro_Age_Ratio = calculate_regime_age(df)["macro_age_ratio"] (SPEC-FEAT-001 §4.7)
   - AFS = calculate_afs(df, [7, 9, 11, 13]) (SPEC-FEAT-001 §4.3, 4-period, afs_order_score == 3)
   - Zero lookahead (.bfill() completely eliminated)
   - Full alignment with K-038 MVC standard: Meso breakout (N=525) -> MVC (N=86: 53 wins, 33 losses)
2. Dynamic Safe Floor & Trailing Envelope:
   - Tracks Drawdown from Entry, SMA34 penetration, and Pullback from Peak across elapsed time Delta t in [4h, 12h, 24h, 48h, 72h]
3. Non-tautological Boundary Breach Dynamics:
   - Evaluates post-breach performance over tau_post in [4h, 12h, 24h] from independent breach events
4. Declustered 1m Scale Envelope:
   - Evaluates independent 1m Fortress and Alignment events with 60m cooldown
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
    calculate_squeeze_index,
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
    print("=== Starting EXP-68 (Audited): Unreachable Envelope & Boundary Breach Analysis ===")
    exp_dir = Path(__file__).resolve().parent
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # Part 1: 1h Scale Features & Standard K-038 Alignment (Issue #71 Part 3)
    # =========================================================================
    print("\n--- Part 1: Computing 1h Standard Features and MVC Setups ---")
    df_1h = load_ohlcv("BTCUSD", "1h").loc["2020-01-01":"2025-04-30"].copy()
    close_1h = df_1h["close"]
    high_1h = df_1h["high"]
    low_1h = df_1h["low"]
    atr_1h = calculate_atr(df_1h, 24)

    horizons_1h = [4, 12, 24, 72]
    excursions_1h = compute_excursions(df_1h, horizons_1h, atr_1h)

    # SMAs and Slopes
    fib_periods = [8, 13, 21, 34, 55, 89, 144, 233, 377]
    smas_1h = {p: calculate_sma(close_1h, p) for p in fib_periods}
    slope_55_1h = (smas_1h[55] - smas_1h[55].shift(3)) / (3 * atr_1h)
    slope_233_1h = (smas_1h[233] - smas_1h[233].shift(3)) / (3 * atr_1h)

    # SPEC-FEAT-001 Compliant Features
    afs_df_1h, afs_order_1h, _ = calculate_afs(df_1h, [7, 9, 11, 13])
    regime_df_1h = calculate_regime_age(df_1h)
    macro_age_ratio = regime_df_1h["macro_age_ratio"]  # Strictly macro_age_bars / 78.5 without bfill
    meso_age_ratio = regime_df_1h["meso_age_ratio"]
    fanout_1h = calculate_fanout_velocity(df_1h, fast_period=21, slow_period=89, atr_period=24)

    # Overhead Wall Density (SMA 34..377 within +1.5 ATR with test_cnt <= 1)
    wall_count_up_1h = pd.Series(0, index=df_1h.index)
    for p in [34, 55, 89, 144, 233, 377]:
        sma = smas_1h[p]
        test_cnt = calculate_level_test_count(df_1h, sma, window_bars=72, atr_series=atr_1h)
        in_range = (sma > close_1h) & (sma <= close_1h + 1.5 * atr_1h) & (test_cnt <= 1)
        wall_count_up_1h += in_range.astype(int)

    # Context 1: Fortress Cap (Wall density up >= 2 and fanout <= 0)
    cond_fortress_1h = (wall_count_up_1h >= 2) & (fanout_1h <= 0)
    # Context 2: Energy Starved (Macro age > 2.0 and fanout <= 0)
    cond_starved_1h = (macro_age_ratio > 2.0) & (fanout_1h <= 0)
    # Context 3: Safe Floor (Bullish Alignment Initial Stage: AFS Order == 3, Macro age <= 2.0, slope_55 > 0)
    cond_safe_floor_1h = (afs_order_1h == 3) & (macro_age_ratio <= 2.0) & (slope_55_1h > 0)

    # Pre-segmentation Declustering (24h Cooldown)
    mask_fortress_1h = decluster_events(cond_fortress_1h, 24)
    mask_starved_1h = decluster_events(cond_starved_1h, 24)
    mask_safe_floor_1h = decluster_events(cond_safe_floor_1h, 24)

    # Standard K-038 MVC Setups (N=86)
    meso_breakout_raw = (close_1h > smas_1h[34]) & (close_1h.shift(1) <= smas_1h[34].shift(1)) & (slope_55_1h > 0)
    meso_breakout_decl = decluster_events(meso_breakout_raw, 24)
    mvc_mask = meso_breakout_decl & (macro_age_ratio <= 2.0) & (afs_order_1h == 3)
    ret_72_mvc = (close_1h.shift(-72) - close_1h) / close_1h - 0.0040
    mvc_winner_mask = mvc_mask & (ret_72_mvc > 0)
    mvc_loser_mask = mvc_mask & (ret_72_mvc <= 0)

    total_mvc = int(mvc_mask.sum())
    n_winners = int(mvc_winner_mask.sum())
    n_losers = int(mvc_loser_mask.sum())
    print(f"1h Events: Fortress={mask_fortress_1h.sum()}, Starved={mask_starved_1h.sum()}, Safe Floor={mask_safe_floor_1h.sum()}, MVC={total_mvc} (Win={n_winners}, Loss={n_losers})")
    assert total_mvc == 86, f"Expected MVC N=86, got {total_mvc}"

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
        }

    # =========================================================================
    # Part 2: Dynamic Safe Floor & Trailing Envelope (Issue #71 Part 1)
    # =========================================================================
    print("\n--- Part 2: Computing Dynamic Safe Floor across Elapsed Time ---")
    delta_t_list = [4, 12, 24, 48, 72]
    mvc_idx = df_1h.index[mvc_mask]

    dynamic_traj = {
        "Winners": {dt: {"dd_entry": [], "sma34_pen": [], "peak_pb": []} for dt in delta_t_list},
        "Losers": {dt: {"dd_entry": [], "sma34_pen": [], "peak_pb": []} for dt in delta_t_list},
    }

    for t0 in mvc_idx:
        t0_loc = df_1h.index.get_loc(t0)
        if t0_loc + 72 >= len(df_1h):
            continue
        group = "Winners" if mvc_winner_mask.loc[t0] else "Losers"
        p0 = close_1h.iloc[t0_loc]
        atr0 = atr_1h.iloc[t0_loc]

        for dt in delta_t_list:
            sub_high = high_1h.iloc[t0_loc + 1 : t0_loc + dt + 1]
            sub_low = low_1h.iloc[t0_loc + 1 : t0_loc + dt + 1]
            sub_sma34 = smas_1h[34].iloc[t0_loc + 1 : t0_loc + dt + 1]
            sub_atr = atr_1h.iloc[t0_loc + 1 : t0_loc + dt + 1]

            # 1. Max Drawdown from Entry: (P0 - min(Low)) / ATR0
            dd_entry = (p0 - sub_low.min()) / atr0
            dynamic_traj[group][dt]["dd_entry"].append(dd_entry)

            # 2. Dynamic SMA34 Penetration: min((Low_t - SMA34_t) / ATR_t)
            dist_sma = (sub_low - sub_sma34) / (sub_atr + 1e-8)
            dynamic_traj[group][dt]["sma34_pen"].append(dist_sma.min())

            # 3. Pullback from Peak: max((RunningPeak_t - Low_t) / ATR_t)
            peaks = pd.concat([pd.Series([p0]), sub_high]).cummax().iloc[1:]
            pullbacks = (peaks.values - sub_low.values) / (sub_atr.values + 1e-8)
            dynamic_traj[group][dt]["peak_pb"].append(float(np.max(pullbacks)))

    metrics_dynamic_safe_floor = {}
    for dt in delta_t_list:
        w_dd = np.array(dynamic_traj["Winners"][dt]["dd_entry"])
        l_dd = np.array(dynamic_traj["Losers"][dt]["dd_entry"])
        w_sma = np.array(dynamic_traj["Winners"][dt]["sma34_pen"])
        l_sma = np.array(dynamic_traj["Losers"][dt]["sma34_pen"])
        w_pb = np.array(dynamic_traj["Winners"][dt]["peak_pb"])
        l_pb = np.array(dynamic_traj["Losers"][dt]["peak_pb"])

        metrics_dynamic_safe_floor[str(dt)] = {
            "elapsed_hours": dt,
            "drawdown_from_entry_atr": {
                "winner_q90": float(np.round(np.quantile(w_dd, 0.90), 4)),
                "winner_q95": float(np.round(np.quantile(w_dd, 0.95), 4)),
                "loser_q90": float(np.round(np.quantile(l_dd, 0.90), 4)),
                "loser_q95": float(np.round(np.quantile(l_dd, 0.95), 4)),
            },
            "sma34_penetration_atr": {
                "winner_q05": float(np.round(np.quantile(w_sma, 0.05), 4)),  # 5th percentile extreme low
                "loser_q05": float(np.round(np.quantile(l_sma, 0.05), 4)),
            },
            "pullback_from_peak_atr": {
                "winner_q90": float(np.round(np.quantile(w_pb, 0.90), 4)),
                "winner_q95": float(np.round(np.quantile(w_pb, 0.95), 4)),
                "loser_q90": float(np.round(np.quantile(l_pb, 0.90), 4)),
                "loser_q95": float(np.round(np.quantile(l_pb, 0.95), 4)),
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
    # Part 3: Declustered 1m Scale Unreachable Envelope (Issue #71 Part 4)
    # =========================================================================
    print("\n--- Part 3: Computing Declustered 1m Scale Envelopes ---")
    df_1m = load_ohlcv("BTCUSD", "1m")
    close_1m = df_1m["close"]
    high_1m = df_1m["high"]
    low_1m = df_1m["low"]
    atr_1m = calculate_atr(df_1m, 60)

    horizons_1m = [15, 30, 60, 240]
    excursions_1m = compute_excursions(df_1m, horizons_1m, atr_1m)

    sma_55m = calculate_sma(close_1m, 55)
    sma_233m = calculate_sma(close_1m, 233)
    sma_610m = calculate_sma(close_1m, 610)
    sma_1440m = calculate_sma(close_1m, 1440)

    fanout_1m = (sma_55m - sma_233m).diff() / (atr_1m + 1e-8)
    wall_density_1m = (
        ((sma_55m > close_1m) & (sma_55m <= close_1m + 1.5 * atr_1m)).astype(int) +
        ((sma_233m > close_1m) & (sma_233m <= close_1m + 1.5 * atr_1m)).astype(int) +
        ((sma_610m > close_1m) & (sma_610m <= close_1m + 1.5 * atr_1m)).astype(int) +
        ((sma_1440m > close_1m) & (sma_1440m <= close_1m + 1.5 * atr_1m)).astype(int)
    )

    cond_fortress_1m_raw = (wall_density_1m >= 2) & (fanout_1m <= 0)
    fortress_1m_decl = decluster_events(cond_fortress_1m_raw, cooldown_bars=60)

    cond_align_1m_raw = (sma_55m > sma_233m) & (sma_233m > sma_610m) & (fanout_1m > 0)
    align_1m_decl = decluster_events(cond_align_1m_raw, cooldown_bars=60)

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
                "events": int(fortress_1m_decl.sum()),
                "up_atr": extract_quantiles(excursions_1m[f"up_atr_{tau}"][fortress_1m_decl]),
                "up_pct": extract_quantiles(excursions_1m[f"up_pct_{tau}"][fortress_1m_decl]),
            },
            "bullish_alignment": {
                "events": int(align_1m_decl.sum()),
                "up_atr": extract_quantiles(excursions_1m[f"up_atr_{tau}"][align_1m_decl]),
                "up_pct": extract_quantiles(excursions_1m[f"up_pct_{tau}"][align_1m_decl]),
            },
        }

    # =========================================================================
    # Part 4: Fractal Scaling Power-Law & Contextual Exponents (Issue #71 Part 1.3)
    # =========================================================================
    print("\n--- Part 4: Evaluating Fractal Scaling and Contextual Exponents ---")
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
    poly = np.polyfit(log_h, log_q95, 1)
    alpha = float(np.round(poly[0], 4))
    log_c = float(np.round(poly[1], 4))
    c_coeff = float(np.round(np.exp(log_c), 4))
    r_squared = float(np.round(np.corrcoef(log_h, log_q95)[0, 1] ** 2, 4))
    print(f"Fractal Scaling Fit: alpha = {alpha}, c = {c_coeff}, R^2 = {r_squared} (Random Walk benchmark = 0.50)")

    # 1h Contextual Alphas (Horizons: 4h, 12h, 24h, 72h)
    log_h_1h = np.log(np.array(horizons_1h))
    log_base_1h = np.log([metrics_1h["horizons"][str(h)]["baseline"]["up_pct"]["q95"] for h in horizons_1h])
    log_fort_1h = np.log([metrics_1h["horizons"][str(h)]["fortress_cap"]["up_pct"]["q95"] for h in horizons_1h])
    alpha_base_1h = float(np.round(np.polyfit(log_h_1h, log_base_1h, 1)[0], 4))
    alpha_fort_1h = float(np.round(np.polyfit(log_h_1h, log_fort_1h, 1)[0], 4))

    metrics_fractal = {
        "alpha_exponent": alpha,
        "prefactor_c": c_coeff,
        "r_squared": r_squared,
        "random_walk_alpha_benchmark": 0.50,
        "contextual_alphas_1h": {
            "baseline_alpha": alpha_base_1h,
            "fortress_cap_alpha": alpha_fort_1h,
            "sub_diffusion_confirmed": bool(alpha_fort_1h < alpha_base_1h),
        },
        "data_points": df_scale.to_dict(orient="records"),
    }

    # =========================================================================
    # Part 5: Non-Tautological Boundary Breach Dynamics (Issue #71 Part 2)
    # =========================================================================
    print("\n--- Part 5: Non-Tautological Boundary Breach Dynamics ---")
    # A true breach event occurs at t_breach when price crosses above a significant resistance:
    # We define Breach as a clean breakout above the 24h Rolling High
    roll_high_24 = high_1h.rolling(24).max().shift(1)
    breach_raw = (close_1h > roll_high_24) & (close_1h.shift(1) <= roll_high_24.shift(1))
    breach_events = decluster_events(breach_raw, cooldown_bars=24)
    total_breaches = int(breach_events.sum())
    print(f"Independent Structural Breakout Events: {total_breaches}")

    # Evaluate post-breach performance across tau_post in [4h, 12h, 24h]
    breach_post_eval = {}
    for tau_post in [4, 12, 24]:
        fut_close = close_1h.shift(-tau_post)
        fut_max = high_1h.iloc[::-1].rolling(tau_post).max().iloc[::-1].shift(-1)
        fut_min = low_1h.iloc[::-1].rolling(tau_post).min().iloc[::-1].shift(-1)

        post_ret = (fut_close - close_1h) / atr_1h
        post_mfe = (fut_max - close_1h) / atr_1h
        post_mae = (close_1h - fut_min) / atr_1h

        # Cascade: Further pushes up by > 1.0 ATR and ends in profit
        cascade_mask = breach_events & (post_mfe > 1.0) & (post_ret > 0)
        # Sweep: Fails to push further or closes negative
        sweep_mask = breach_events & (post_ret < 0)
        neutral_mask = breach_events & (~cascade_mask) & (~sweep_mask)

        n_casc = int(cascade_mask.sum())
        n_swp = int(sweep_mask.sum())
        n_neut = int(neutral_mask.sum())

        casc_macro_align = float(np.round((slope_233_1h[cascade_mask] > 0).mean() * 100, 2))
        swp_macro_align = float(np.round((slope_233_1h[sweep_mask] > 0).mean() * 100, 2))
        swp_macro_counter = float(np.round(100.0 - swp_macro_align, 2))

        bar_range_norm = (high_1h - low_1h) / atr_1h
        casc_range = float(np.round(bar_range_norm[cascade_mask].mean(), 2))
        swp_range = float(np.round(bar_range_norm[sweep_mask].mean(), 2))

        breach_post_eval[str(tau_post)] = {
            "tau_post_hours": tau_post,
            "cascade": {
                "count": n_casc,
                "ratio_pct": float(np.round(n_casc / total_breaches * 100, 2)),
                "macro_aligned_pct": casc_macro_align,
                "entry_bar_range_atr": casc_range,
                "mean_post_ret_atr": float(np.round(post_ret[cascade_mask].mean(), 2)),
            },
            "sweep": {
                "count": n_swp,
                "ratio_pct": float(np.round(n_swp / total_breaches * 100, 2)),
                "macro_counter_pct": swp_macro_counter,
                "entry_bar_range_atr": swp_range,
                "mean_post_ret_atr": float(np.round(post_ret[sweep_mask].mean(), 2)),
            },
            "neutral": {
                "count": n_neut,
                "ratio_pct": float(np.round(n_neut / total_breaches * 100, 2)),
            },
        }

    metrics_breach = {
        "event_definition": "Clean Breakout above 24h Rolling High with 24h Cooldown",
        "total_independent_breaches": total_breaches,
        "post_horizons": breach_post_eval,
    }

    # =========================================================================
    # Combine All Metrics & Save JSON
    # =========================================================================
    final_metrics = {
        "experiment_id": "EXP-68",
        "description": "Unreachable Envelope and Boundary Breach Dynamics across 1h and 1m Scales (Audited)",
        "1h_envelope": metrics_1h,
        "1m_envelope": metrics_1m,
        "dynamic_safe_floor_mvc": metrics_dynamic_safe_floor,
        "cross_period_stability": metrics_period_stability,
        "fractal_scaling": metrics_fractal,
        "boundary_breach_dynamics": metrics_breach,
    }

    metrics_path = exp_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(final_metrics, f, indent=2, ensure_ascii=False)
    print(f"Saved complete audited metrics to {metrics_path}")

    # =========================================================================
    # Part 6: Diagnostic Visualizations
    # =========================================================================
    print("\n--- Part 6: Generating Diagnostic Visualizations ---")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    # Plot 1: Dynamic Safe Floor Trajectory
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    dt_arr = np.array(delta_t_list)
    w_dd_arr = [metrics_dynamic_safe_floor[str(dt)]["drawdown_from_entry_atr"]["winner_q95"] for dt in delta_t_list]
    l_dd_arr = [metrics_dynamic_safe_floor[str(dt)]["drawdown_from_entry_atr"]["loser_q95"] for dt in delta_t_list]
    w_pb_arr = [metrics_dynamic_safe_floor[str(dt)]["pullback_from_peak_atr"]["winner_q95"] for dt in delta_t_list]
    l_pb_arr = [metrics_dynamic_safe_floor[str(dt)]["pullback_from_peak_atr"]["loser_q95"] for dt in delta_t_list]

    axes[0].plot(dt_arr, w_dd_arr, "o-", color="#27ae60", linewidth=2.5, markersize=8, label="Winner 95% Safe Floor (Drawdown)")
    axes[0].plot(dt_arr, l_dd_arr, "s--", color="#c0392b", linewidth=2.0, markersize=8, label="Loser 95% Drawdown")
    axes[0].set_xlabel("Elapsed Time Delta t (Hours)", fontsize=12)
    axes[0].set_ylabel("Max Drawdown from Entry (ATR)", fontsize=12)
    axes[0].set_title("K-038 MVC: Dynamic Safe Floor vs Loser Sinkhole across Time", fontsize=13, fontweight="bold")
    axes[0].legend(frameon=True, fontsize=11)

    axes[1].plot(dt_arr, w_pb_arr, "o-", color="#2980b9", linewidth=2.5, markersize=8, label="Winner 95% Trailing Pullback Limit")
    axes[1].plot(dt_arr, l_pb_arr, "s--", color="#d35400", linewidth=2.0, markersize=8, label="Loser 95% Peak Collapse")
    axes[1].set_xlabel("Elapsed Time Delta t (Hours)", fontsize=12)
    axes[1].set_ylabel("Max Pullback from Running Peak (ATR)", fontsize=12)
    axes[1].set_title("Dynamic Trailing Pullback Ceiling (Peak Retention)", fontsize=13, fontweight="bold")
    axes[1].legend(frameon=True, fontsize=11)

    plt.tight_layout()
    p1_path = plots_dir / "01_multi_scale_unreachable_envelopes.png"
    plt.savefig(p1_path, dpi=300)
    plt.close()
    print(f"Saved: {p1_path}")

    # Plot 2: Fractal Scaling Power-Law Fit
    plt.figure(figsize=(9, 6))
    h_vals = df_scale["horizon_hours"].values
    q95_pct_vals = df_scale["q95_pct"].values * 100
    fit_curve = (c_coeff * (h_vals ** alpha)) * 100
    rw_curve = (df_scale["q95_pct"].iloc[0] * ((h_vals / h_vals[0]) ** 0.50)) * 100

    plt.loglog(h_vals, q95_pct_vals, "o", markersize=8, color="#2c3e50", label="Empirical 95% Excursion Limit")
    plt.loglog(h_vals, fit_curve, "-", color="#e74c3c", linewidth=2.5, label=f"Empirical Power Law: $\\alpha={alpha:.3f}$ ($R^2={r_squared:.3f}$)")
    plt.loglog(h_vals, rw_curve, "--", color="#7f8c8d", linewidth=1.8, label="Random Walk Benchmark: $\\alpha=0.50$")

    plt.xlabel("Horizon (Hours, Log Scale)", fontsize=12)
    plt.ylabel("95% Max Upward Excursion (%, Log Scale)", fontsize=12)
    plt.title(f"Fractal Scaling of Reach Boundaries (15m to 72h): $\\alpha = {alpha:.3f}$ ($R^2 = {r_squared:.3f}$)", fontsize=13, fontweight="bold")
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

    # Plot 4: Non-Tautological Post-Breach Dynamics
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    post_horizons = ["4", "12", "24"]
    x_b = np.arange(len(post_horizons))
    w_b = 0.35

    casc_ratios = [breach_post_eval[h]["cascade"]["ratio_pct"] for h in post_horizons]
    swp_ratios = [breach_post_eval[h]["sweep"]["ratio_pct"] for h in post_horizons]

    axes[0].bar(x_b - w_b / 2, casc_ratios, w_b, label="Cascade (Follow-through)", color="#27ae60")
    axes[0].bar(x_b + w_b / 2, swp_ratios, w_b, label="Sweep (Immediate Trap)", color="#c0392b")
    axes[0].set_xticks(x_b)
    axes[0].set_xticklabels([f"+{h}h" for h in post_horizons], fontsize=11)
    axes[0].set_ylabel("Breach Outcome Ratio (%)", fontsize=12)
    axes[0].set_title(f"Post-Breach Outcomes across Horizons (N={total_breaches})", fontsize=13, fontweight="bold")
    axes[0].legend(frameon=True)

    # Macro Alignment Divergence at 24h Post-Breach
    tau_tgt = "24"
    align_data = [
        breach_post_eval[tau_tgt]["cascade"]["macro_aligned_pct"],
        100.0 - breach_post_eval[tau_tgt]["sweep"]["macro_counter_pct"],
    ]
    counter_data = [
        100.0 - breach_post_eval[tau_tgt]["cascade"]["macro_aligned_pct"],
        breach_post_eval[tau_tgt]["sweep"]["macro_counter_pct"],
    ]
    labels_b = ["Cascade", "Sweep"]

    axes[1].bar(labels_b, align_data, label="Macro Aligned (Slope_233 > 0)", color="#2980b9", width=0.45)
    axes[1].bar(labels_b, counter_data, bottom=align_data, label="Macro Counter (Slope_233 <= 0)", color="#e67e22", width=0.45)
    axes[1].set_ylabel("Macro Orientation (%)", fontsize=12)
    axes[1].set_title(f"Macro Orientation Divergence at +{tau_tgt}h Post-Breach", fontsize=13, fontweight="bold")
    axes[1].legend(frameon=True)

    plt.tight_layout()
    p4_path = plots_dir / "04_boundary_breach_cascade_vs_sweep.png"
    plt.savefig(p4_path, dpi=300)
    plt.close()
    print(f"Saved: {p4_path}")

    print("\n=== EXP-68 Audited Execution Completed Successfully ===")


if __name__ == "__main__":
    main()
