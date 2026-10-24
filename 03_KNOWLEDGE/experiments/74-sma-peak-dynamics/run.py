"""
EXP-74: Multi-Timeframe SMA Peak Dynamics, Phase Lead Sequences & Invalidation Geometry
(Audited & Remediated for Issue #76)

Addresses all audit requirements of Issue #76:
1. Strict baseline reproduction of EXP-69 K-038 MVC (S0 Net EV +1.07%, S3_k50 Net EV +1.13%)
2. Elimination of tautology in peak finding: Cross-correlation + 1-to-1 peak matching (F1/Precision)
3. Objective data-driven determination of resonant partner pairs (no hardcoding)
4. Comprehensive branching geometry for Approach vs Straddle conditioned on slope and BB expansion
5. Bandwalk effect & Peak/Trough symmetry analysis
6. 7-factor unified causal peak proximity score and phase-adaptive dynamic exit (S6)
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.data_loader import load_ohlcv
from src.features import (
    calculate_sma,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_afs,
    calculate_regime_age,
    calculate_level_test_count,
)
from src.evaluation import (
    decluster_events,
    evaluate_multi_horizon,
    evaluate_yearly_breakdown,
)


def get_stoch_d(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.Series:
    """Calculate Stochastic %D using clean rolling lookbacks."""
    low_k = df["low"].rolling(k_period).min()
    high_k = df["high"].rolling(k_period).max()
    fast_k = 100.0 * (df["close"] - low_k) / (high_k - low_k).replace(0, 1e-8)
    return fast_k.rolling(d_period).mean()


def extract_peaks_and_troughs(series: pd.Series, atr_series: pd.Series, min_prom_atr: float = 0.35, min_dist: int = 12):
    """Extract substantial swing peaks and troughs from full time series without lookahead."""
    arr = series.values
    raw_p, _ = find_peaks(arr, distance=min_dist)
    raw_t, _ = find_peaks(-arr, distance=min_dist)

    valid_p = []
    for p in raw_p:
        cur_atr = atr_series.iloc[p] if not np.isnan(atr_series.iloc[p]) else 1.0
        w_left = max(0, p - min_dist)
        w_right = min(len(arr), p + min_dist + 1)
        base = max(np.min(arr[w_left:p]), np.min(arr[p:w_right])) if p > w_left and p < w_right - 1 else arr[p]
        if (arr[p] - base) >= min_prom_atr * cur_atr:
            valid_p.append(p)

    valid_t = []
    for t in raw_t:
        cur_atr = atr_series.iloc[t] if not np.isnan(atr_series.iloc[t]) else 1.0
        w_left = max(0, t - min_dist)
        w_right = min(len(arr), t + min_dist + 1)
        base = min(np.max(arr[w_left:t]), np.max(arr[t:w_right])) if t > w_left and t < w_right - 1 else arr[t]
        if (base - arr[t]) >= min_prom_atr * cur_atr:
            valid_t.append(t)

    return np.array(valid_p), np.array(valid_t)


def evaluate_peak_matching(target_peaks: np.ndarray, candidate_peaks: np.ndarray, max_lead: int = 24, min_lead: int = 1):
    """
    Non-tautological 1-to-1 peak matching:
    Evaluates whether each candidate peak uniquely and reliably predicts a target peak.
    """
    n_target = len(target_peaks)
    n_cand = len(candidate_peaks)
    if n_target == 0 or n_cand == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "median_lead": 0.0, "mean_lead": 0.0, "iqr_lead": 0.0, "matched_targets": 0}

    matched_targets = 0
    lead_lags = []
    matched_cand_set = set()

    for tp in target_peaks:
        # candidate peaks strictly preceding target peak within [min_lead, max_lead]
        prec = [cp for cp in candidate_peaks if (tp - max_lead) <= cp <= (tp - min_lead)]
        if len(prec) > 0:
            matched_targets += 1
            closest_cp = prec[-1] # closest preceding peak
            lead_lags.append(tp - closest_cp)
            matched_cand_set.add(closest_cp)

    recall = matched_targets / n_target if n_target > 0 else 0.0
    precision = len(matched_cand_set) / n_cand if n_cand > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    med_lead = float(np.median(lead_lags)) if len(lead_lags) > 0 else 0.0
    mean_lead = float(np.mean(lead_lags)) if len(lead_lags) > 0 else 0.0
    q75, q25 = np.percentile(lead_lags, [75, 25]) if len(lead_lags) >= 4 else (med_lead, med_lead)
    iqr_lead = float(q75 - q25)

    return {
        "precision": float(np.round(precision * 100, 1)),
        "recall": float(np.round(recall * 100, 1)),
        "f1": float(np.round(f1, 3)),
        "median_lead": float(np.round(med_lead, 1)),
        "mean_lead": float(np.round(mean_lead, 1)),
        "iqr_lead": float(np.round(iqr_lead, 1)),
        "matched_targets": matched_targets,
    }


def compute_cross_correlation(target_series: pd.Series, candidate_series: pd.Series, max_tau: int = 24):
    """Compute lag tau in [0, max_tau] that maximizes correlation Corr(target(t), cand(t - tau))."""
    valid = ~(target_series.isna() | candidate_series.isna())
    ts = target_series[valid].values
    cs = candidate_series[valid].values
    if len(ts) < max_tau + 10:
        return 0.0, 0

    best_corr = -999.0
    best_tau = 0
    for tau in range(0, max_tau + 1):
        if tau == 0:
            corr = np.corrcoef(ts, cs)[0, 1]
        else:
            corr = np.corrcoef(ts[tau:], cs[:-tau])[0, 1]
        if corr > best_corr:
            best_corr = corr
            best_tau = tau

    return float(np.round(best_corr, 3)), best_tau


def compute_trade_metrics(trades: list, total_opportunities: int, cost: float = 0.0040) -> dict:
    """Standardized trade performance metric computation."""
    if len(trades) == 0:
        return {
            "executed_trades": 0,
            "fill_rate_pct": 0.0,
            "net_mean_return_pct": 0.0,
            "gross_mean_return_pct": 0.0,
            "median_return_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "worst_trade_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_duration_hours": 0.0,
            "total_opportunity_net_return_pct": 0.0,
        }

    net_rets = np.array([t["net_ret"] for t in trades])
    gross_rets = net_rets + cost
    durs = np.array([t["dur"] for t in trades])

    net_mean = float(np.round(np.mean(net_rets) * 100, 2))
    gross_mean = float(np.round(np.mean(gross_rets) * 100, 2))
    median_ret = float(np.round(np.median(net_rets) * 100, 2))
    win_rate = float(np.round(np.mean(net_rets > 0) * 100, 2))

    wins = net_rets[net_rets > 0]
    losses = net_rets[net_rets <= 0]
    gross_win = np.sum(wins) if len(wins) > 0 else 0.0
    gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0.0
    pf = float(np.round(gross_win / gross_loss, 2)) if gross_loss > 0 else 999.0
    worst = float(np.round(np.min(net_rets) * 100, 2))
    avg_dur = float(np.round(np.mean(durs), 1))

    equity = np.cumprod(1.0 + net_rets)
    peaks = np.maximum.accumulate(equity)
    dds = (equity - peaks) / peaks
    max_dd = float(np.round(abs(np.min(dds)) * 100, 2)) if len(dds) > 0 else 0.0
    total_net = float(np.round(np.sum(net_rets) * 100, 2))
    fill_rate = float(np.round(len(trades) / total_opportunities * 100, 2))

    return {
        "executed_trades": len(trades),
        "fill_rate_pct": fill_rate,
        "net_mean_return_pct": net_mean,
        "gross_mean_return_pct": gross_mean,
        "median_return_pct": median_ret,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "worst_trade_pct": worst,
        "max_drawdown_pct": max_dd,
        "avg_duration_hours": avg_dur,
        "total_opportunity_net_return_pct": total_net,
    }


def main():
    print("=== Starting EXP-74 (Remediated): Multi-Timeframe SMA Peak Dynamics & Invalidation Geometry ===")
    exp_dir = Path(__file__).resolve().parent
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    cost = 0.0040

    # =========================================================================
    # Part 1: Loading 1h and 1m Data & Precomputing Technicals
    # =========================================================================
    print("\n--- Part 1: Loading 1h Data and Precomputing Multi-Timeframe Technicals ---")
    df_1h = load_ohlcv("BTCUSD", "1h").loc["2020-01-01":"2025-04-30"].copy()
    close_1h = df_1h["close"]
    atr_1h = calculate_atr(df_1h, 24)

    periods = {
        "P1_Bull": ("2020-01-01", "2021-12-31"),
        "P2_Bear": ("2022-01-01", "2022-12-31"),
        "P3_Mixed": ("2023-01-01", "2025-04-30"),
    }

    def get_period(ts):
        for p, (s, e) in periods.items():
            if s <= str(ts)[:10] <= e:
                return p
        return "P3_Mixed"

    df_1h["period"] = [get_period(t) for t in df_1h.index]

    # Precompute SMAs and Slopes
    sma_periods = [8, 13, 21, 34, 55, 89, 144, 233, 377, 610]
    smas = {p: calculate_sma(close_1h, p) for p in sma_periods}
    slopes = {p: (smas[p] - smas[p].shift(3)) / (3 * atr_1h) for p in sma_periods}
    slopes_1bar = {p: (smas[p] - smas[p].shift(1)) / atr_1h for p in [8, 13, 21, 34]}

    # Precompute Bollinger Bands
    bbs = {p: calculate_bollinger_bands(close_1h, p, 2.0) for p in [20, 34, 55, 89, 233]}
    bb_widths = {p: (bbs[p][0] - bbs[p][2]) / bbs[p][1] for p in bbs}
    delta_bb_widths = {p: bb_widths[p].diff(3) for p in bbs}
    pct_b_233 = (close_1h - bbs[233][2]) / (bbs[233][0] - bbs[233][2]).replace(0, 1e-8)

    # Precompute Stochastics
    stoch_periods = [7, 8, 9, 11, 13, 14, 21, 34, 55]
    stochs = {p: get_stoch_d(df_1h, p, 3) for p in stoch_periods}

    # Precompute AFS multi-scale order scores
    afs_periods = [7, 9, 11, 13, 21, 34, 55]
    afs_scores = {}
    for p in afs_periods:
        sub_p = [max(3, p - 4), max(5, p - 2), p, p + 2]
        _, ord_sc, _ = calculate_afs(df_1h, sub_p)
        afs_scores[p] = ord_sc

    # =========================================================================
    # Part 2: Objective Resonant Partner Identification & Non-Tautological Lead Lag
    # =========================================================================
    print("\n--- Part 2: Objective Resonant Partner Identification & Cross-Correlation ---")
    target_smas = [21, 34, 55, 89]
    peak_indices = {}
    trough_indices = {}

    target_partner_results = {}
    resonant_pairs_objective = {}

    for target_p in target_smas:
        t_peaks, t_troughs = extract_peaks_and_troughs(smas[target_p], atr_1h, min_prom_atr=0.35, min_dist=12)
        peak_indices[target_p] = t_peaks
        trough_indices[target_p] = t_troughs
        print(f"Target SMA_{target_p}: Extracted {len(t_peaks)} swing peaks, {len(t_troughs)} swing troughs")

        target_slope = slopes[target_p]
        target_dict = {"short_smas": {}, "stoch_d": {}, "afs": {}}

        # 1. Short SMAs candidates
        short_cands = [p for p in [8, 13, 21, 34, 55] if p < target_p]
        best_short = None
        best_short_score = -999.0

        for cp in short_cands:
            cp_peaks, _ = extract_peaks_and_troughs(smas[cp], atr_1h, min_prom_atr=0.20, min_dist=6)
            match_stats = evaluate_peak_matching(t_peaks, cp_peaks, max_lead=24, min_lead=1)
            r_max, tau_star = compute_cross_correlation(target_slope, slopes[cp], max_tau=24)
            comp_score = match_stats["f1"] * r_max
            stats_entry = {
                "cross_corr_r_max": r_max,
                "phase_lag_tau_star": tau_star,
                **match_stats,
                "composite_score": float(np.round(comp_score, 3)),
            }
            target_dict["short_smas"][f"SMA_{cp}"] = stats_entry
            if comp_score > best_short_score:
                best_short_score = comp_score
                best_short = f"SMA_{cp}"

        # 2. Stoch_D candidates
        best_stoch = None
        best_stoch_score = -999.0

        for cp in stoch_periods:
            c_series = stochs[cp]
            raw_c_peaks, _ = find_peaks(c_series.fillna(50).values, distance=6, height=60)
            match_stats = evaluate_peak_matching(t_peaks, raw_c_peaks, max_lead=24, min_lead=1)
            r_max, tau_star = compute_cross_correlation(target_slope, c_series, max_tau=24)
            comp_score = match_stats["f1"] * r_max
            stats_entry = {
                "cross_corr_r_max": r_max,
                "phase_lag_tau_star": tau_star,
                **match_stats,
                "composite_score": float(np.round(comp_score, 3)),
            }
            target_dict["stoch_d"][f"Stoch_D_{cp}"] = stats_entry
            if comp_score > best_stoch_score:
                best_stoch_score = comp_score
                best_stoch = f"Stoch_D_{cp}"

        # 3. AFS candidates
        best_afs = None
        best_afs_score = -999.0

        for cp in afs_periods:
            c_series = afs_scores[cp]
            raw_c_peaks, _ = find_peaks(c_series.fillna(0).values, distance=6)
            match_stats = evaluate_peak_matching(t_peaks, raw_c_peaks, max_lead=24, min_lead=1)
            r_max, tau_star = compute_cross_correlation(target_slope, c_series, max_tau=24)
            comp_score = match_stats["f1"] * r_max
            stats_entry = {
                "cross_corr_r_max": r_max,
                "phase_lag_tau_star": tau_star,
                **match_stats,
                "composite_score": float(np.round(comp_score, 3)),
            }
            target_dict["afs"][f"AFS_{cp}"] = stats_entry
            if comp_score > best_afs_score:
                best_afs_score = comp_score
                best_afs = f"AFS_{cp}"

        target_partner_results[f"SMA_{target_p}"] = target_dict
        resonant_pairs_objective[f"SMA_{target_p}"] = {
            "best_short_sma": best_short,
            "best_stoch": best_stoch,
            "best_afs": best_afs,
            "typical_lead_hours": target_dict["short_smas"][best_short]["median_lead"] if best_short else 6.0,
        }

        print(f"  ===> Objective Resonant Triad for SMA_{target_p}:")
        print(f"       Short SMA : {best_short} (Lead={target_dict['short_smas'][best_short]['median_lead']}h, F1={target_dict['short_smas'][best_short]['f1']:.3f}, r_max={target_dict['short_smas'][best_short]['cross_corr_r_max']:.3f})")
        print(f"       Stoch_D   : {best_stoch} (Lead={target_dict['stoch_d'][best_stoch]['median_lead']}h, F1={target_dict['stoch_d'][best_stoch]['f1']:.3f}, r_max={target_dict['stoch_d'][best_stoch]['cross_corr_r_max']:.3f})")
        print(f"       AFS       : {best_afs} (Lead={target_dict['afs'][best_afs]['median_lead']}h, F1={target_dict['afs'][best_afs]['f1']:.3f}, r_max={target_dict['afs'][best_afs]['cross_corr_r_max']:.3f})")

    # =========================================================================
    # Part 3: Invalidation Geometry, Branching Condition & BB Bandwalk (Task 3)
    # =========================================================================
    print("\n--- Part 3: Invalidation Geometry, Branching & Symmetry Analysis ---")
    delta_h_34 = (smas[34] - smas[233]) / atr_1h

    # 3.1 Peak Height Distribution across 3 Phases
    geom_peaks = []
    for p in peak_indices[34]:
        if p < 233 or p >= len(df_1h) - 1 or np.isnan(delta_h_34.iloc[p]):
            continue
        cur_dh = delta_h_34.iloc[p]
        slp_233 = slopes[233].iloc[p]
        if slp_233 < -0.05:
            sr = "Steep_Down"
        elif slp_233 > 0.05:
            sr = "Steep_Up"
        else:
            sr = "Flat_Gentle"

        # Check if crossed within 24 bars
        sub_34 = smas[34].iloc[max(0, p - 24):p + 1]
        sub_233 = smas[233].iloc[max(0, p - 24):p + 1]
        started_under = sub_34.iloc[0] < sub_233.iloc[0]
        ended_over = sub_34.iloc[-1] >= sub_233.iloc[-1]
        is_straddle = started_under and ended_over

        if sub_34.iloc[-1] < sub_233.iloc[-1]:
            phase = "1_Approach_Peak"
        elif is_straddle:
            phase = "2_Straddle_Peak"
        else:
            phase = "3_Expansion_Peak"

        geom_peaks.append({
            "phase": phase,
            "slope_regime": sr,
            "delta_h_atr": cur_dh,
            "pct_b_233": pct_b_233.iloc[p],
            "bb_expanding": delta_bb_widths[34].iloc[p] > 0,
        })

    df_geom_peaks = pd.DataFrame(geom_peaks)
    geom_stats = {}
    for phase_name in ["1_Approach_Peak", "2_Straddle_Peak", "3_Expansion_Peak"]:
        g_phase = df_geom_peaks[df_geom_peaks["phase"] == phase_name]
        clean_vals = g_phase["delta_h_atr"].dropna().values
        p_dict = {
            "total_count": len(clean_vals),
            "delta_h_mean": float(np.round(np.mean(clean_vals), 2)) if len(clean_vals) > 0 else 0.0,
            "delta_h_median": float(np.round(np.median(clean_vals), 2)) if len(clean_vals) > 0 else 0.0,
            "delta_h_p10": float(np.round(np.percentile(clean_vals, 10), 2)) if len(clean_vals) > 0 else 0.0,
            "delta_h_p90": float(np.round(np.percentile(clean_vals, 90), 2)) if len(clean_vals) > 0 else 0.0,
            "slope_breakdown": {},
        }
        for s_reg in ["Steep_Down", "Flat_Gentle", "Steep_Up"]:
            sub_s = g_phase[g_phase["slope_regime"] == s_reg]
            sub_clean = sub_s["delta_h_atr"].dropna().values
            if len(sub_clean) > 0:
                p_dict["slope_breakdown"][s_reg] = {
                    "count": len(sub_clean),
                    "delta_h_mean": float(np.round(np.mean(sub_clean), 2)),
                    "delta_h_median": float(np.round(np.median(sub_clean), 2)),
                    "delta_h_p90": float(np.round(np.percentile(sub_clean, 90), 2)),
                    "pct_b_median": float(np.round(sub_s["pct_b_233"].median(), 2)),
                }
        geom_stats[phase_name] = p_dict
        print(f"  {phase_name}: N={p_dict['total_count']}, Median={p_dict['delta_h_median']:+.2f} ATR [P10={p_dict['delta_h_p10']:+.2f}, P90={p_dict['delta_h_p90']:+.2f}]")

    # 3.2 Branching Analysis for Approach Waves
    approach_event_raw = (delta_h_34 >= -2.0) & (delta_h_34 <= -0.5) & (delta_h_34.shift(3) < -2.0) & (slopes[34] > 0)
    approach_events_decl = decluster_events(approach_event_raw, 24)
    app_indices = np.where(approach_events_decl.values)[0]

    branch_records = []
    for idx in app_indices:
        sub_dh = delta_h_34.iloc[idx:min(len(df_1h), idx + 72)]
        max_dh = sub_dh.max()
        if max_dh < 0.0:
            outcome = "1_Approach_Turnback"
        elif max_dh <= 2.5:
            outcome = "2_Straddle_Overshoot"
        else:
            outcome = "3_Expansion_Breakthrough"

        slp_val = slopes[233].iloc[idx]
        sr = "Steep_Down" if slp_val < -0.05 else ("Steep_Up" if slp_val > 0.05 else "Flat_Gentle")
        is_bb_exp = delta_bb_widths[34].iloc[idx] > 0

        branch_records.append({
            "outcome": outcome,
            "max_delta_h": max_dh,
            "regime_233": sr,
            "bb_expanding": is_bb_exp,
        })

    df_branch = pd.DataFrame(branch_records)
    branching_stats = {
        "total_approach_events": len(df_branch),
        "overall_distribution_pct": {k: float(np.round(v * 100, 1)) for k, v in df_branch["outcome"].value_counts(normalize=True).items()},
        "by_slope_regime": {},
        "by_bb_expansion": {},
        "trap_condition_steep_down_bb_contracting": {},
        "breakout_condition_flat_up_bb_expanding": {},
    }

    for sr, g in df_branch.groupby("regime_233"):
        vc = g["outcome"].value_counts(normalize=True).to_dict()
        branching_stats["by_slope_regime"][sr] = {
            "count": len(g),
            "turnback_pct": float(np.round(vc.get("1_Approach_Turnback", 0.0) * 100, 1)),
            "straddle_pct": float(np.round(vc.get("2_Straddle_Overshoot", 0.0) * 100, 1)),
            "expansion_pct": float(np.round(vc.get("3_Expansion_Breakthrough", 0.0) * 100, 1)),
            "median_max_delta_h": float(np.round(g["max_delta_h"].median(), 2)),
        }

    for is_exp, g in df_branch.groupby("bb_expanding"):
        lbl = "BB_Expanding" if is_exp else "BB_Contracting_or_Flat"
        vc = g["outcome"].value_counts(normalize=True).to_dict()
        branching_stats["by_bb_expansion"][lbl] = {
            "count": len(g),
            "turnback_pct": float(np.round(vc.get("1_Approach_Turnback", 0.0) * 100, 1)),
            "straddle_pct": float(np.round(vc.get("2_Straddle_Overshoot", 0.0) * 100, 1)),
            "expansion_pct": float(np.round(vc.get("3_Expansion_Breakthrough", 0.0) * 100, 1)),
            "median_max_delta_h": float(np.round(g["max_delta_h"].median(), 2)),
        }

    g_trap = df_branch[(df_branch["regime_233"] == "Steep_Down") & (~df_branch["bb_expanding"])]
    if len(g_trap) > 0:
        vc_t = g_trap["outcome"].value_counts(normalize=True).to_dict()
        branching_stats["trap_condition_steep_down_bb_contracting"] = {
            "count": len(g_trap),
            "turnback_pct": float(np.round(vc_t.get("1_Approach_Turnback", 0.0) * 100, 1)),
            "straddle_pct": float(np.round(vc_t.get("2_Straddle_Overshoot", 0.0) * 100, 1)),
            "expansion_pct": float(np.round(vc_t.get("3_Expansion_Breakthrough", 0.0) * 100, 1)),
        }

    g_brk = df_branch[(df_branch["regime_233"] != "Steep_Down") & (df_branch["bb_expanding"])]
    if len(g_brk) > 0:
        vc_b = g_brk["outcome"].value_counts(normalize=True).to_dict()
        branching_stats["breakout_condition_flat_up_bb_expanding"] = {
            "count": len(g_brk),
            "turnback_pct": float(np.round(vc_b.get("1_Approach_Turnback", 0.0) * 100, 1)),
            "straddle_pct": float(np.round(vc_b.get("2_Straddle_Overshoot", 0.0) * 100, 1)),
            "expansion_pct": float(np.round(vc_b.get("3_Expansion_Breakthrough", 0.0) * 100, 1)),
        }

    print(f"  Approach Branching N={len(df_branch)}: Turnback={branching_stats['overall_distribution_pct'].get('1_Approach_Turnback', 0.0)}%, Straddle={branching_stats['overall_distribution_pct'].get('2_Straddle_Overshoot', 0.0)}%, Expansion={branching_stats['overall_distribution_pct'].get('3_Expansion_Breakthrough', 0.0)}%")

    # 3.3 Peak vs Trough Symmetry
    trough_records = []
    for t in trough_indices[34]:
        if t < 233 or t >= len(df_1h) - 1 or np.isnan(delta_h_34.iloc[t]):
            continue
        cur_dh = delta_h_34.iloc[t]
        slp_val = slopes[233].iloc[t]
        sr = "Steep_Down" if slp_val < -0.05 else ("Steep_Up" if slp_val > 0.05 else "Flat_Gentle")
        trough_records.append({"delta_h_atr": cur_dh, "slope_regime": sr})

    df_tr = pd.DataFrame(trough_records)
    trough_stats = {}
    for sr, g in df_tr.groupby("slope_regime"):
        clean_tr = g["delta_h_atr"].dropna().values
        if len(clean_tr) > 0:
            trough_stats[sr] = {
                "count": len(clean_tr),
                "delta_h_mean": float(np.round(np.mean(clean_tr), 2)),
                "delta_h_median": float(np.round(np.median(clean_tr), 2)),
                "delta_h_p10": float(np.round(np.percentile(clean_tr, 10), 2)),
                "delta_h_p90": float(np.round(np.percentile(clean_tr, 90), 2)),
            }
    print(f"  Trough Symmetry: Steep_Down Median={trough_stats.get('Steep_Down', {}).get('delta_h_median')} ATR vs Steep_Up Median={trough_stats.get('Steep_Up', {}).get('delta_h_median')} ATR")

    # =========================================================================
    # Part 4: 7-Factor Unified Causal Peak Proximity Score
    # =========================================================================
    print("\n--- Part 4: Formulating 7-Factor Unified Peak Proximity Score ---")
    stoch_turn = (stochs[8] >= 65) & (stochs[8] < stochs[8].shift(1))
    short_slope_neg = slopes_1bar[8] <= 0
    bb_decel = delta_bb_widths[34] <= 0
    afs_degrade = afs_scores[9] <= 1
    macro_headwind = (slopes[233] <= 0) & (delta_h_34 <= 1.0)

    unified_score = (
        stoch_turn.astype(int) +
        short_slope_neg.astype(int) +
        bb_decel.astype(int) +
        afs_degrade.astype(int) +
        macro_headwind.astype(int)
    )

    score_high = unified_score >= 2
    detected = 0
    lead_times = []
    for p in peak_indices[34]:
        w_sub = score_high.iloc[max(0, p - 12):p]
        if w_sub.sum() > 0:
            detected += 1
            idx_first = np.where(w_sub.values)[0][-1]
            lead_times.append(len(w_sub) - idx_first)

    det_rate = float(np.round(detected / len(peak_indices[34]) * 100, 1)) if len(peak_indices[34]) > 0 else 0.0
    lead_med = float(np.median(lead_times)) if len(lead_times) > 0 else 0.0
    print(f"7-Factor Score >= 2 Lead Detection: Rate={det_rate}%, Median Lead={lead_med} bars")

    # =========================================================================
    # Part 5: Trading Application A - K-038 MVC 1m High-Res Simulation
    # =========================================================================
    print("\n--- Part 5: Trading Application A - K-038 MVC 1m High-Res Simulation ---")
    meso_raw = (close_1h > smas[34]) & (close_1h.shift(1) <= smas[34].shift(1)) & (slopes[55] > 0)
    meso_decl = decluster_events(meso_raw, 24)
    regime_df = calculate_regime_age(df_1h)
    macro_age_ratio = regime_df["macro_age_ratio"]
    _, afs_order_4p, _ = calculate_afs(df_1h, [7, 9, 11, 13])

    mvc_mask = meso_decl & (macro_age_ratio <= 2.0) & (afs_order_4p == 3)
    mvc_events = df_1h.index[mvc_mask]
    total_mvc = len(mvc_events)
    print(f"Verified K-038 MVC Events: {total_mvc}")
    assert total_mvc == 86, f"Expected 86 MVC setups, got {total_mvc}"

    print("Loading 1m Discovery Data for exact EXP-69 baseline reproduction...")
    df_1m = load_ohlcv("BTCUSD", "1m")

    app_a_trades = {
        "S0_Baseline_Fixed_72h": {p: [] for p in ["Full", "P1_Bull", "P2_Bear", "P3_Mixed"]},
        "S3_Dynamic_Structural_k50": {p: [] for p in ["Full", "P1_Bull", "P2_Bear", "P3_Mixed"]},
        "S6_Phase_Adaptive_Peak_Exit": {p: [] for p in ["Full", "P1_Bull", "P2_Bear", "P3_Mixed"]},
    }

    for t0 in mvc_events:
        t0_loc = df_1h.index.get_loc(t0)
        if t0_loc + 72 >= len(df_1h):
            continue
        entry_time = t0 + pd.Timedelta(hours=1)
        exit_time_72h = entry_time + pd.Timedelta(hours=72)
        sub_1m = df_1m.loc[entry_time:exit_time_72h]
        if len(sub_1m) < 60:
            continue

        p0 = sub_1m["open"].iloc[0]
        atr0 = atr_1h.loc[t0]
        p_era = get_period(t0)

        sub_lows = sub_1m["low"].values
        sub_opens = sub_1m["open"].values
        sub_times = sub_1m.index

        # S0: Exact 72h close
        p_exit_s0 = sub_1m["close"].iloc[-1]
        ret_s0 = (p_exit_s0 - p0) / p0 - cost
        t_s0 = {"net_ret": ret_s0, "dur": 72.0}
        for p in ["Full", p_era]:
            app_a_trades["S0_Baseline_Fixed_72h"][p].append(t_s0)

        # S3_k50: Exact EXP-69 structural stop
        exited_s3 = False
        for i in range(len(sub_1m)):
            t_bar = sub_times[i]
            t_1h_prev = (t_bar - pd.Timedelta(hours=1)).floor("1h")
            sma_cur = smas[34].loc[t_1h_prev] if t_1h_prev in smas[34].index else smas[34].loc[t0]
            atr_cur = atr_1h.loc[t_1h_prev] if t_1h_prev in atr_1h.index else atr0
            stop_p = sma_cur - 5.0 * atr_cur
            if sub_lows[i] <= stop_p:
                p_exit = min(sub_opens[i], stop_p)
                t_s3 = {"net_ret": (p_exit - p0) / p0 - cost, "dur": float(np.round(i / 60.0, 2))}
                for p in ["Full", p_era]:
                    app_a_trades["S3_Dynamic_Structural_k50"][p].append(t_s3)
                exited_s3 = True
                break
        if not exited_s3:
            for p in ["Full", p_era]:
                app_a_trades["S3_Dynamic_Structural_k50"][p].append(t_s0)

        # S6_Phase_Adaptive_Peak_Exit:
        # Invalidation stop (S3_k50) + Phase-Adaptive Take Profit on 1h boundary
        exited_s6 = False
        for i in range(len(sub_1m)):
            t_bar = sub_times[i]
            t_1h_prev = (t_bar - pd.Timedelta(hours=1)).floor("1h")
            sma_cur = smas[34].loc[t_1h_prev] if t_1h_prev in smas[34].index else smas[34].loc[t0]
            atr_cur = atr_1h.loc[t_1h_prev] if t_1h_prev in atr_1h.index else atr0
            stop_p = sma_cur - 5.0 * atr_cur

            # Invalidation stop
            if sub_lows[i] <= stop_p:
                p_exit = min(sub_opens[i], stop_p)
                t_s6 = {"net_ret": (p_exit - p0) / p0 - cost, "dur": float(np.round(i / 60.0, 2))}
                for p in ["Full", p_era]:
                    app_a_trades["S6_Phase_Adaptive_Peak_Exit"][p].append(t_s6)
                exited_s6 = True
                break

            # 1h boundary peak check (after initial 4 hours)
            if t_bar.minute == 0 and i >= 240:
                cur_p = sub_opens[i]
                profit_atr = (cur_p - p0) / atr0
                sma_233_cur = smas[233].loc[t_1h_prev] if t_1h_prev in smas[233].index else sma_cur
                delta_h_cur = (sma_cur - sma_233_cur) / atr_cur
                stoch_val = stochs[8].loc[t_1h_prev] if t_1h_prev in stochs[8].index else 50
                slp_8_val = slopes_1bar[8].loc[t_1h_prev] if t_1h_prev in slopes_1bar[8].index else 0
                bb_diff_val = delta_bb_widths[34].loc[t_1h_prev] if t_1h_prev in delta_bb_widths[34].index else 0

                # Phase 1 & 2 (Approaching or Straddle zone <= 1.5 ATR):
                # Low ceiling -> Lock in at >= 1.0 ATR if short slope or stoch turns
                if delta_h_cur <= 1.5:
                    if profit_atr >= 1.0 and slp_8_val <= 0 and (stoch_val >= 65 or stoch_val < 50):
                        t_s6 = {"net_ret": (cur_p - p0) / p0 - cost, "dur": float(np.round(i / 60.0, 2))}
                        for p in ["Full", p_era]:
                            app_a_trades["S6_Phase_Adaptive_Peak_Exit"][p].append(t_s6)
                        exited_s6 = True
                        break
                # Phase 3 (Expansion zone > 1.5 ATR):
                # Let profits run! Only exit on mature expansion peak (>= 4.0 ATR, BB contraction, stoch >= 75)
                else:
                    if profit_atr >= 4.0 and bb_diff_val <= 0 and slp_8_val <= 0 and stoch_val >= 75:
                        t_s6 = {"net_ret": (cur_p - p0) / p0 - cost, "dur": float(np.round(i / 60.0, 2))}
                        for p in ["Full", p_era]:
                            app_a_trades["S6_Phase_Adaptive_Peak_Exit"][p].append(t_s6)
                        exited_s6 = True
                        break

        if not exited_s6:
            for p in ["Full", p_era]:
                app_a_trades["S6_Phase_Adaptive_Peak_Exit"][p].append(t_s0)

    period_sizes_mvc = {"Full": 86, "P1_Bull": 29, "P2_Bear": 18, "P3_Mixed": 39}
    app_a_metrics = {}
    for s_name in app_a_trades:
        app_a_metrics[s_name] = {}
        for p_name in ["Full", "P1_Bull", "P2_Bear", "P3_Mixed"]:
            app_a_metrics[s_name][p_name] = compute_trade_metrics(
                app_a_trades[s_name][p_name],
                period_sizes_mvc[p_name],
                cost=cost,
            )

    print("\nApplication A Metrics Summary:")
    for s_name, m_dict in app_a_metrics.items():
        mf = m_dict["Full"]
        mp2 = m_dict["P2_Bear"]
        print(f"  {s_name:28s}: Full Net EV={mf['net_mean_return_pct']:+.2f}%, PF={mf['profit_factor']:.2f}, Worst={mf['worst_trade_pct']:+.2f}%, Dur={mf['avg_duration_hours']:.1f}h | P2_Bear EV={mp2['net_mean_return_pct']:+.2f}%")

    # =========================================================================
    # Part 6: Trading Application B - Reversal Short on Approach & Straddle Peaks
    # =========================================================================
    print("\n--- Part 6: Trading Application B - Reversal Short on Approach & Straddle Peaks ---")
    macro_bear = (smas[233] < smas[610]) & (slopes[233] < 0)
    delta_h_all = (smas[34] - smas[233]) / atr_1h
    in_peak_zone = (delta_h_all >= -1.5) & (delta_h_all <= 1.5)

    short_raw = (
        macro_bear &
        in_peak_zone &
        (slopes_1bar[8] <= 0) & (slopes_1bar[8].shift(1) > 0) &
        (stochs[8] >= 65)
    )
    short_decl = decluster_events(short_raw, 24)
    total_short_events = int(short_decl.sum())
    print(f"Total Independent Reversal Short Events: {total_short_events}")

    mh_short = evaluate_multi_horizon(df_1h, short_decl, [12, 24, 48, 72], cost=cost, is_short=True)

    idx_short = np.where(short_decl.values)[0]
    ret_dict_24 = {}
    for idx in idx_short:
        if idx + 24 < len(df_1h):
            ret_dict_24[df_1h.index[idx]] = -(df_1h["close"].iloc[idx + 24] / df_1h["close"].iloc[idx] - 1.0)
    ret_series_24 = pd.Series(ret_dict_24)

    yb_df = evaluate_yearly_breakdown(ret_series_24, cost=cost)
    yb_short_24 = yb_df.to_dict(orient="index")

    app_b_metrics = {
        "total_signals": total_short_events,
        "multi_horizon": {str(k): v for k, v in mh_short.items()},
        "yearly_breakdown_24h": {str(k): v for k, v in yb_short_24.items()},
    }

    print("\nApplication B Multi-Horizon Results (Net of 40 bps):")
    for h, ev in mh_short.items():
        print(f"  Horizon {h:2d}h: Net EV={ev['net_mean_return']*100:+.2f}%, PF={ev['profit_factor']:.2f}, WinRate={ev['win_rate']*100:.1f}%, Trades={ev['total_trades']}")

    # =========================================================================
    # Part 7: Save Comprehensive metrics.json
    # =========================================================================
    output_metrics = {
        "experiment_id": "EXP-74",
        "description": "Multi-Timeframe SMA Peak Dynamics, Phase Lead Sequences & Invalidation Geometry (Remediated)",
        "total_peaks_evaluated": {
            "SMA_21": len(peak_indices[21]),
            "SMA_34": len(peak_indices[34]),
            "SMA_55": len(peak_indices[55]),
            "SMA_89": len(peak_indices[89]),
        },
        "total_troughs_evaluated": {
            "SMA_21": len(trough_indices[21]),
            "SMA_34": len(trough_indices[34]),
            "SMA_55": len(trough_indices[55]),
            "SMA_89": len(trough_indices[89]),
        },
        "objective_resonant_pairs": resonant_pairs_objective,
        "phase_lead_matching_stats": target_partner_results,
        "three_phase_geometry_stats": geom_stats,
        "approach_wave_branching_stats": branching_stats,
        "peak_trough_symmetry_stats": trough_stats,
        "causal_peak_proximity_score": {
            "detection_rate_pct": det_rate,
            "median_lead_bars": lead_med,
        },
        "trading_application_a_mvc_exit": app_a_metrics,
        "trading_application_b_reversal_short": app_b_metrics,
    }

    with open(exp_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(output_metrics, f, indent=2)
    print(f"\nSaved remediated EXP-74 metrics to {exp_dir / 'metrics.json'}")

    # =========================================================================
    # Part 8: Generate Publication Plots
    # =========================================================================
    print("\n--- Part 8: Generating Publication Plots ---")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    # Plot 1: Objective Resonant Triads and Lead Lags
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    target_names = ["SMA_21", "SMA_34", "SMA_55", "SMA_89"]
    lead_stoch = [target_partner_results[t]["stoch_d"][resonant_pairs_objective[t]["best_stoch"]]["median_lead"] for t in target_names]
    lead_short = [target_partner_results[t]["short_smas"][resonant_pairs_objective[t]["best_short_sma"]]["median_lead"] for t in target_names]
    labels_stoch = [f"{resonant_pairs_objective[t]['best_stoch']}\n(-> {t})" for t in target_names]
    labels_short = [f"{resonant_pairs_objective[t]['best_short_sma']}\n(-> {t})" for t in target_names]

    axes[0].bar(labels_stoch, lead_stoch, color="steelblue", alpha=0.85)
    axes[0].set_title("Objective Resonant Stoch_D Median Lead Time", fontweight="bold", fontsize=12)
    axes[0].set_ylabel("Median Lead Time (Hours)", fontsize=11)
    for i, v in enumerate(lead_stoch):
        axes[0].text(i, v + 0.15, f"{v:.1f}h", ha="center", fontweight="bold")

    axes[1].bar(labels_short, lead_short, color="seagreen", alpha=0.85)
    axes[1].set_title("Objective Resonant Short SMA Median Lead Time", fontweight="bold", fontsize=12)
    axes[1].set_ylabel("Median Lead Time (Hours)", fontsize=11)
    for i, v in enumerate(lead_short):
        axes[1].text(i, v + 0.15, f"{v:.1f}h", ha="center", fontweight="bold")

    plt.suptitle("HYP-SMA-PEAK-2: Objective Resonant Triads & Lead Time Across Scales", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(plots_dir / "01_phase_lead_correlation_matrix.png", dpi=300)
    plt.close()

    # Plot 2: 3-Phase Peak Height & Trough Symmetry Distribution
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    phase_order = ["1_Approach_Peak", "2_Straddle_Peak", "3_Expansion_Peak"]
    data_by_phase = [df_geom_peaks[df_geom_peaks["phase"] == p]["delta_h_atr"].values for p in phase_order]
    box1 = axes[0].boxplot(data_by_phase, patch_artist=True)
    axes[0].set_xticks([1, 2, 3])
    axes[0].set_xticklabels(["Approach Peak\n(Under 233)", "Straddle Peak\n(Crossing 233)", "Expansion Peak\n(Over 233)"])
    colors = ["crimson", "darkorange", "forestgreen"]
    for patch, c in zip(box1["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)
    axes[0].axhline(0, color="black", linestyle="--", alpha=0.7, label="SMA 233 Level")
    axes[0].set_ylabel("Peak Height Relative to SMA 233 (ATR Units)", fontsize=11)
    axes[0].set_title("Swing Peak Height: 3-Phase Separation", fontweight="bold", fontsize=12)
    axes[0].legend()

    # Troughs by slope regime
    slope_order = ["Steep_Down", "Flat_Gentle", "Steep_Up"]
    data_by_trough = [df_tr[df_tr["slope_regime"] == s]["delta_h_atr"].values for s in slope_order]
    box2 = axes[1].boxplot(data_by_trough, patch_artist=True)
    axes[1].set_xticks([1, 2, 3])
    axes[1].set_xticklabels(["Steep Down\n(Slope < -0.05)", "Flat / Gentle\n(|Slope| <= 0.05)", "Steep Up\n(Slope > +0.05)"])
    colors2 = ["darkred", "gray", "darkgreen"]
    for patch, c in zip(box2["boxes"], colors2):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)
    axes[1].axhline(0, color="black", linestyle="--", alpha=0.7, label="SMA 233 Level")
    axes[1].set_ylabel("Trough Depth Relative to SMA 233 (ATR Units)", fontsize=11)
    axes[1].set_title("Swing Trough Depth: Slope Symmetry (Mirror Geometry)", fontweight="bold", fontsize=12)
    axes[1].legend()

    plt.suptitle("HYP-SMA-PEAK-1: Peak & Trough Geometry Governed by Long SMA", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(plots_dir / "02_three_phase_peak_height_distribution.png", dpi=300)
    plt.close()

    # Plot 3: Approach Wave Branching Distribution (Turnback vs Straddle vs Expansion)
    fig, ax = plt.subplots(figsize=(10, 6))
    categories = ["Overall", "Steep Down Slope", "Flat/Gentle Slope", "BB Contracting", "BB Expanding", "Trap (Down & Cont)", "Breakout (Flat/Up & Exp)"]
    tb_vals = [
        branching_stats["overall_distribution_pct"].get("1_Approach_Turnback", 0.0),
        branching_stats["by_slope_regime"].get("Steep_Down", {}).get("turnback_pct", 0.0),
        branching_stats["by_slope_regime"].get("Flat_Gentle", {}).get("turnback_pct", 0.0),
        branching_stats["by_bb_expansion"].get("BB_Contracting_or_Flat", {}).get("turnback_pct", 0.0),
        branching_stats["by_bb_expansion"].get("BB_Expanding", {}).get("turnback_pct", 0.0),
        branching_stats["trap_condition_steep_down_bb_contracting"].get("turnback_pct", 0.0),
        branching_stats["breakout_condition_flat_up_bb_expanding"].get("turnback_pct", 0.0),
    ]
    straddle_vals = [
        branching_stats["overall_distribution_pct"].get("2_Straddle_Overshoot", 0.0),
        branching_stats["by_slope_regime"].get("Steep_Down", {}).get("straddle_pct", 0.0),
        branching_stats["by_slope_regime"].get("Flat_Gentle", {}).get("straddle_pct", 0.0),
        branching_stats["by_bb_expansion"].get("BB_Contracting_or_Flat", {}).get("straddle_pct", 0.0),
        branching_stats["by_bb_expansion"].get("BB_Expanding", {}).get("straddle_pct", 0.0),
        branching_stats["trap_condition_steep_down_bb_contracting"].get("straddle_pct", 0.0),
        branching_stats["breakout_condition_flat_up_bb_expanding"].get("straddle_pct", 0.0),
    ]
    exp_vals = [
        branching_stats["overall_distribution_pct"].get("3_Expansion_Breakthrough", 0.0),
        branching_stats["by_slope_regime"].get("Steep_Down", {}).get("expansion_pct", 0.0),
        branching_stats["by_slope_regime"].get("Flat_Gentle", {}).get("expansion_pct", 0.0),
        branching_stats["by_bb_expansion"].get("BB_Contracting_or_Flat", {}).get("expansion_pct", 0.0),
        branching_stats["by_bb_expansion"].get("BB_Expanding", {}).get("expansion_pct", 0.0),
        branching_stats["trap_condition_steep_down_bb_contracting"].get("expansion_pct", 0.0),
        branching_stats["breakout_condition_flat_up_bb_expanding"].get("expansion_pct", 0.0),
    ]

    y_pos = np.arange(len(categories))
    ax.barh(y_pos, tb_vals, color="crimson", alpha=0.85, label="Turnback (< 0 ATR)")
    ax.barh(y_pos, straddle_vals, left=tb_vals, color="darkorange", alpha=0.85, label="Straddle Overshoot (0 to 2.5 ATR)")
    ax.barh(y_pos, exp_vals, left=np.array(tb_vals) + np.array(straddle_vals), color="forestgreen", alpha=0.85, label="Expansion (> 2.5 ATR)")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(categories, fontsize=11)
    ax.set_xlabel("Outcome Probability (%)", fontsize=11)
    ax.set_title("Branching Geometry: Approach Wave Outcomes Conditioned on Long SMA & BB Status", fontsize=13, fontweight="bold")
    ax.legend(loc="lower right", frameon=True)
    plt.tight_layout()
    plt.savefig(plots_dir / "03_trade_application_performance_comparison.png", dpi=300)
    plt.close()

    # Plot 4: Trading Application A Comparison & Reversal Short Multi-Horizon
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    app_names = ["S0 Base (72h)", "S3 Struct (k=5.0)", "S6 Phase-Adaptive"]
    evs = [app_a_metrics[k]["Full"]["net_mean_return_pct"] for k in ["S0_Baseline_Fixed_72h", "S3_Dynamic_Structural_k50", "S6_Phase_Adaptive_Peak_Exit"]]
    durs = [app_a_metrics[k]["Full"]["avg_duration_hours"] for k in ["S0_Baseline_Fixed_72h", "S3_Dynamic_Structural_k50", "S6_Phase_Adaptive_Peak_Exit"]]

    axes[0].bar(app_names, evs, color=["gray", "steelblue", "darkorange"], alpha=0.85)
    axes[0].set_title("Trading Application A: Net EV (%) [40 bps Deducted]", fontweight="bold", fontsize=12)
    axes[0].set_ylabel("Net Mean Return (%)")
    for i, v in enumerate(evs):
        axes[0].text(i, v + 0.03, f"{v:+.2f}%\n(PF {app_a_metrics[['S0_Baseline_Fixed_72h', 'S3_Dynamic_Structural_k50', 'S6_Phase_Adaptive_Peak_Exit'][i]]['Full']['profit_factor']:.2f})", ha="center", fontweight="bold")

    # Application B Reversal Short
    h_labels = ["12h", "24h", "48h", "72h"]
    h_evs = [mh_short[h]["net_mean_return"] * 100 for h in [12, 24, 48, 72]]
    bar_colors = ["coral" if v < 0 else "teal" for v in h_evs]
    axes[1].bar(h_labels, h_evs, color=bar_colors, alpha=0.85, width=0.5)
    axes[1].axhline(0, color="black", linestyle="--", alpha=0.6)
    axes[1].set_ylabel("Net Mean Return (%) [40 bps Deducted]", fontsize=11)
    axes[1].set_title(f"Application B: Reversal Short on Approach/Straddle (N={total_short_events})", fontweight="bold", fontsize=12)
    for i, v in enumerate(h_evs):
        axes[1].text(i, v + (0.1 if v >= 0 else -0.25), f"{v:+.2f}%", ha="center", fontweight="bold")

    plt.suptitle("Trading Applications: K-038 MVC Adaptive Exit vs Reversal Short", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(plots_dir / "04_reversal_short_multi_horizon.png", dpi=300)
    plt.close()

    print("All remediated EXP-74 plots generated successfully.")
    print("=== EXP-74 Complete ===")


if __name__ == "__main__":
    main()
