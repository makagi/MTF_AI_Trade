"""EXP-69: 1h K-038 MVC & Signal C x 1m Intra-bar Path Integration.

Implements SPEC-EVAL-001 v0.4.0 and SPEC-FEAT-001 v0.3.0.
Audited and remediated for Issue #73:
1. Strict causal alignment: zero lookahead in 1h structural feature lookups (assert confirmed 1h <= t_bar).
2. Full cross-period breakdowns (Full, P1_Bull, P2_Bear, P3_Mixed) for all exit strategies.
3. Sensitivity analysis of structural exit multiplier (k in {3.5, 4.43, 5.0}) and 1m wick vs 1h close breach.
4. Time & State-dependent dynamic floor (Profit Ratchet: BE at +2.0 ATR, trailing at +3.5 ATR).
5. Entry refinements (E0 instant, E1 limit, E2 breakout, E3 1m micro-structure confirmation).
6. Complete 1m intra-bar path tracking for Signal C (Stage 2 Short, N=15).
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
    calculate_regime_age,
    calculate_fanout_velocity,
    calculate_level_test_count,
)
from src.evaluation import decluster_events


def compute_metrics(trades: list[dict], total_opportunities: int, cost: float = 0.0040) -> dict:
    """Compute comprehensive trading performance metrics with friction deducted."""
    n_executed = len(trades)
    if n_executed == 0:
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

    df_t = pd.DataFrame(trades)
    net_rets = df_t["net_ret"].values
    gross_rets = net_rets + cost

    net_mean = float(np.round(np.mean(net_rets) * 100, 2))
    gross_mean = float(np.round(np.mean(gross_rets) * 100, 2))
    median_ret = float(np.round(np.median(net_rets) * 100, 2))
    win_rate = float(np.round((net_rets > 0).mean() * 100, 2))

    wins = net_rets[net_rets > 0]
    losses = net_rets[net_rets <= 0]
    pf = float(np.round(wins.sum() / abs(losses.sum()), 2)) if len(losses) > 0 and losses.sum() != 0 else 999.0
    worst = float(np.round(np.min(net_rets) * 100, 2))
    avg_dur = float(np.round(df_t["duration_h"].mean(), 1))

    # Equity curve and Max Drawdown
    equity = np.cumprod(1.0 + net_rets)
    peaks = np.maximum.accumulate(equity)
    dds = (equity - peaks) / peaks
    max_dd = float(np.round(abs(np.min(dds)) * 100, 2)) if len(dds) > 0 else 0.0

    total_net = float(np.round(np.sum(net_rets) * 100, 2))
    fill_rate = float(np.round(n_executed / total_opportunities * 100, 2))

    return {
        "executed_trades": n_executed,
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
    print("=== Starting EXP-69 Remediated Execution: 1h x 1m Intra-bar Path Integration ===")
    exp_dir = Path(__file__).resolve().parent
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    cost = 0.0040  # 40 bps roundtrip friction

    # =========================================================================
    # Part 1: Extracting 1h Signals (K-038 MVC N=86 and Signal C Stage 2 N=15)
    # =========================================================================
    print("\n--- Part 1: Extracting 1h Signals from BTCUSD 1h Data ---")
    df_1h = load_ohlcv("BTCUSD", "1h").loc["2020-01-01":"2025-04-30"].copy()
    close_1h = df_1h["close"]
    atr_1h = calculate_atr(df_1h, 24)

    sma_34_1h = calculate_sma(close_1h, 34)
    sma_55_1h = calculate_sma(close_1h, 55)
    sma_89_1h = calculate_sma(close_1h, 89)
    sma_233_1h = calculate_sma(close_1h, 233)
    sma_377_1h = calculate_sma(close_1h, 377)
    sma_610_1h = calculate_sma(close_1h, 610)

    slope_55_1h = (sma_55_1h - sma_55_1h.shift(3)) / (3 * atr_1h)
    slope_233_1h = (sma_233_1h - sma_233_1h.shift(3)) / (3 * atr_1h)
    slope_377_1h = (sma_377_1h - sma_377_1h.shift(3)) / (3 * atr_1h)

    # Signal A / Meso Breakout -> K-038 MVC
    meso_breakout_raw = (close_1h > sma_34_1h) & (close_1h.shift(1) <= sma_34_1h.shift(1)) & (slope_55_1h > 0)
    meso_breakout_decl = decluster_events(meso_breakout_raw, 24)

    regime_df_1h = calculate_regime_age(df_1h)
    macro_age_ratio = regime_df_1h["macro_age_ratio"]
    afs_df_1h, afs_order_score, _ = calculate_afs(df_1h, [7, 9, 11, 13])

    mvc_mask = meso_breakout_decl & (macro_age_ratio <= 2.0) & (afs_order_score == 3)
    mvc_events = df_1h.index[mvc_mask]
    total_mvc = len(mvc_events)
    print(f"Verified K-038 MVC Opportunities: {total_mvc}")
    assert total_mvc == 86, f"Expected 86 MVC setups, got {total_mvc}"

    # Signal C: Macro Dynamic S/R Collision Short (Stage 2: Defend + Decel)
    macro_alignment_bear = (sma_233_1h < sma_377_1h) & (sma_377_1h < sma_610_1h) & (slope_377_1h < 0)
    dist_sma_233 = (close_1h - sma_233_1h) / atr_1h
    sig_c_raw = macro_alignment_bear & (dist_sma_233.abs() < 0.5) & (slope_233_1h < 0)
    sig_c_decl = decluster_events(sig_c_raw, 24)
    retest_count_233 = calculate_level_test_count(df_1h, level=sma_233_1h, window_bars=72, tolerance_atr=0.5, atr_series=atr_1h, min_departure_bars=3)
    fanout_1h = calculate_fanout_velocity(df_1h, fast_period=21, slow_period=89, atr_period=14)
    sig_c_stage2 = sig_c_decl & (retest_count_233 <= 2) & (fanout_1h <= 0)
    sig_c_events = df_1h.index[sig_c_stage2]
    total_sig_c = len(sig_c_events)
    print(f"Verified Signal C Stage 2 Opportunities: {total_sig_c}")
    assert total_sig_c == 15, f"Expected 15 Signal C Stage 2 setups, got {total_sig_c}"

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

    # =========================================================================
    # Part 2: Loading 1m High-Resolution Data
    # =========================================================================
    print("\n--- Part 2: Loading 1m Discovery Data ---")
    df_1m = load_ohlcv("BTCUSD", "1m")
    print(f"Loaded 1m DataFrame: {len(df_1m)} rows")

    # =========================================================================
    # Part 3: Simulating Invalidation & Dynamic Exit Strategies for K-038 MVC
    # =========================================================================
    print("\n--- Part 3: Simulating 1m Path Exit Strategies across K-038 MVC (N=86) ---")

    strat_names = [
        "S0_Baseline_Fixed_72h",
        "S1_Fixed_Safe_Floor_579",
        "S2_Time_Elapsing_Safe_Floor",
        "S3_Dynamic_Structural_SMA34_k443",
        "S3_Sensitivity_k35",
        "S3_Sensitivity_k50",
        "S3_1h_Close_Breach",
        "S4_Dynamic_Profit_Ratchet",
        "S5_Composite_Dynamic_Ratchet",
    ]

    # Store trade lists per strategy per period
    all_period_keys = ["Full", "P1_Bull", "P2_Bear", "P3_Mixed"]
    strat_trades_mvc = {s: {p: [] for p in all_period_keys} for s in strat_names}
    path_trajectories = []

    for t0 in mvc_events:
        t0_loc = df_1h.index.get_loc(t0)
        if t0_loc + 72 >= len(df_1h):
            continue

        entry_time = t0 + pd.Timedelta(hours=1)
        exit_time_72h = entry_time + pd.Timedelta(hours=72)
        sub_1m = df_1m.loc[entry_time:exit_time_72h]
        if len(sub_1m) < 60:
            continue

        p_era = get_period(t0)
        p0 = sub_1m["open"].iloc[0]
        atr0 = atr_1h.loc[t0]
        sub_highs = sub_1m["high"].values
        sub_lows = sub_1m["low"].values
        sub_opens = sub_1m["open"].values
        sub_times = sub_1m.index

        # Store trajectory for visualization (normalized to entry price in ATR)
        if len(path_trajectories) < 86:
            norm_path = (sub_1m["close"].iloc[::15].values - p0) / atr0
            path_trajectories.append((norm_path, p_era))

        # --- S0: Baseline Fixed 72h ---
        p_exit_s0 = sub_1m["close"].iloc[-1]
        ret_s0 = (p_exit_s0 - p0) / p0 - cost
        t_s0 = {"net_ret": ret_s0, "duration_h": 72.0, "exit": "timeout_72h"}
        for p in ["Full", p_era]:
            strat_trades_mvc["S0_Baseline_Fixed_72h"][p].append(t_s0)

        # --- S1: Fixed Safe Floor -5.79 ATR ---
        stop_p_s1 = p0 - 5.79 * atr0
        exited_s1 = False
        for i in range(len(sub_1m)):
            if sub_lows[i] <= stop_p_s1:
                p_exit = min(sub_opens[i], stop_p_s1)
                t_s1 = {"net_ret": (p_exit - p0) / p0 - cost, "duration_h": float(np.round(i / 60.0, 2)), "exit": "stop"}
                for p in ["Full", p_era]:
                    strat_trades_mvc["S1_Fixed_Safe_Floor_579"][p].append(t_s1)
                exited_s1 = True
                break
        if not exited_s1:
            for p in ["Full", p_era]:
                strat_trades_mvc["S1_Fixed_Safe_Floor_579"][p].append(t_s0)

        # --- S2: Time-Elapsing Safe Floor (3-Step Function) ---
        exited_s2 = False
        for i in range(len(sub_1m)):
            dur_h = i / 60.0
            cur_sf = 3.63 if dur_h <= 12.0 else (5.49 if dur_h <= 24.0 else 5.79)
            stop_p = p0 - cur_sf * atr0
            if sub_lows[i] <= stop_p:
                p_exit = min(sub_opens[i], stop_p)
                t_s2 = {"net_ret": (p_exit - p0) / p0 - cost, "duration_h": float(np.round(dur_h, 2)), "exit": "step_sf"}
                for p in ["Full", p_era]:
                    strat_trades_mvc["S2_Time_Elapsing_Safe_Floor"][p].append(t_s2)
                exited_s2 = True
                break
        if not exited_s2:
            for p in ["Full", p_era]:
                strat_trades_mvc["S2_Time_Elapsing_Safe_Floor"][p].append(t_s0)

        # --- S3: Dynamic Structural Line (SMA34 - k * ATR) with Sensitivity k in {3.5, 4.43, 5.0} ---
        # Lookahead verification: confirmed 1h open time is (t_bar - 1h).floor('1h')
        for k_val, s_name in [(4.43, "S3_Dynamic_Structural_SMA34_k443"), (3.50, "S3_Sensitivity_k35"), (5.00, "S3_Sensitivity_k50")]:
            exited_s3 = False
            for i in range(len(sub_1m)):
                t_bar = sub_times[i]
                t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
                assert t_1h + pd.Timedelta(hours=1) <= t_bar, f"Lookahead in S3: 1h close {t_1h + pd.Timedelta(hours=1)} > 1m bar {t_bar}"
                sma34_cur = sma_34_1h.loc[t_1h] if t_1h in sma_34_1h.index else sma_34_1h.loc[t0]
                atr_cur = atr_1h.loc[t_1h] if t_1h in atr_1h.index else atr0
                stop_p = sma34_cur - k_val * atr_cur
                if sub_lows[i] <= stop_p:
                    p_exit = min(sub_opens[i], stop_p)
                    t_s3 = {"net_ret": (p_exit - p0) / p0 - cost, "duration_h": float(np.round(i / 60.0, 2)), "exit": "sma34_wick"}
                    for p in ["Full", p_era]:
                        strat_trades_mvc[s_name][p].append(t_s3)
                    exited_s3 = True
                    break
            if not exited_s3:
                for p in ["Full", p_era]:
                    strat_trades_mvc[s_name][p].append(t_s0)

        # --- S3_1h_Close_Breach: Exit on 1h confirmed close breach ---
        exited_s3_close = False
        sub_1h_slice = df_1h.loc[entry_time:exit_time_72h]
        for bar_idx in range(len(sub_1h_slice)):
            t_bar_1h = sub_1h_slice.index[bar_idx]
            c_1h = sub_1h_slice["close"].iloc[bar_idx]
            sma34_c = sma_34_1h.loc[t_bar_1h]
            atr_c = atr_1h.loc[t_bar_1h]
            if c_1h <= sma34_c - 4.43 * atr_c:
                t_breach_confirmed = t_bar_1h + pd.Timedelta(hours=1)
                if t_breach_confirmed in df_1m.index:
                    p_exit = df_1m.loc[t_breach_confirmed, "open"]
                    dur_h = float(np.round((t_breach_confirmed - entry_time).total_seconds() / 3600.0, 2))
                    t_s3_c = {"net_ret": (p_exit - p0) / p0 - cost, "duration_h": dur_h, "exit": "sma34_1h_close"}
                    for p in ["Full", p_era]:
                        strat_trades_mvc["S3_1h_Close_Breach"][p].append(t_s3_c)
                    exited_s3_close = True
                    break
        if not exited_s3_close:
            for p in ["Full", p_era]:
                strat_trades_mvc["S3_1h_Close_Breach"][p].append(t_s0)

        # --- S4: Dynamic Profit Ratchet (BE at +2.0 ATR, Trailing at +3.5 ATR) ---
        peak_s4 = p0
        exited_s4 = False
        for i in range(len(sub_1m)):
            if sub_highs[i] > peak_s4:
                peak_s4 = sub_highs[i]
            profit_atr = (peak_s4 - p0) / atr0
            if profit_atr >= 3.5:
                cur_floor = max(p0, peak_s4 - 2.0 * atr0)
            elif profit_atr >= 2.0:
                cur_floor = p0
            else:
                cur_floor = p0 - 5.79 * atr0

            if sub_lows[i] <= cur_floor:
                p_exit = min(sub_opens[i], cur_floor)
                t_s4 = {"net_ret": (p_exit - p0) / p0 - cost, "duration_h": float(np.round(i / 60.0, 2)), "exit": "ratchet_hit"}
                for p in ["Full", p_era]:
                    strat_trades_mvc["S4_Dynamic_Profit_Ratchet"][p].append(t_s4)
                exited_s4 = True
                break
        if not exited_s4:
            for p in ["Full", p_era]:
                strat_trades_mvc["S4_Dynamic_Profit_Ratchet"][p].append(t_s0)

        # --- S5: Composite Dynamic Ratchet (S3 + Step SF + Profit Ratchet) ---
        peak_s5 = p0
        exited_s5 = False
        for i in range(len(sub_1m)):
            if sub_highs[i] > peak_s5:
                peak_s5 = sub_highs[i]
            t_bar = sub_times[i]
            dur_h = i / 60.0
            t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
            sma34_cur = sma_34_1h.loc[t_1h] if t_1h in sma_34_1h.index else sma_34_1h.loc[t0]
            atr_cur = atr_1h.loc[t_1h] if t_1h in atr_1h.index else atr0
            
            struct_floor = sma34_cur - 4.43 * atr_cur
            step_sf = 3.63 if dur_h <= 12.0 else (5.49 if dur_h <= 24.0 else 5.79)
            base_floor = max(struct_floor, p0 - step_sf * atr0)

            profit_atr = (peak_s5 - p0) / atr0
            if profit_atr >= 3.5:
                cur_floor = max(base_floor, peak_s5 - 2.0 * atr0)
            elif profit_atr >= 2.0:
                cur_floor = max(base_floor, p0)
            else:
                cur_floor = base_floor

            if sub_lows[i] <= cur_floor:
                p_exit = min(sub_opens[i], cur_floor)
                t_s5 = {"net_ret": (p_exit - p0) / p0 - cost, "duration_h": float(np.round(dur_h, 2)), "exit": "composite_ratchet"}
                for p in ["Full", p_era]:
                    strat_trades_mvc["S5_Composite_Dynamic_Ratchet"][p].append(t_s5)
                exited_s5 = True
                break
        if not exited_s5:
            for p in ["Full", p_era]:
                strat_trades_mvc["S5_Composite_Dynamic_Ratchet"][p].append(t_s0)

    # Compute period breakdown metrics for all strategies
    period_sample_sizes = {"Full": 86, "P1_Bull": 29, "P2_Bear": 18, "P3_Mixed": 39}
    mvc_metrics_all = {}
    for s_name in strat_names:
        mvc_metrics_all[s_name] = {}
        for p_name in all_period_keys:
            mvc_metrics_all[s_name][p_name] = compute_metrics(
                strat_trades_mvc[s_name][p_name],
                period_sample_sizes[p_name],
                cost=cost,
            )

    print("\n=== K-038 MVC Performance Summary (Full / P1 / P2 / P3) ===")
    for s_name in strat_names:
        mf = mvc_metrics_all[s_name]["Full"]
        mp2 = mvc_metrics_all[s_name]["P2_Bear"]
        print(f"{s_name:35s}: Full EV={mf['net_mean_return_pct']:+.2f}%, PF={mf['profit_factor']:.2f}, Worst={mf['worst_trade_pct']:+.2f}%, MaxDD={mf['max_drawdown_pct']:.2f}%, Dur={mf['avg_duration_hours']:.1f}h | P2_Bear EV={mp2['net_mean_return_pct']:+.2f}%, PF={mp2['profit_factor']:.2f}, DD={mp2['max_drawdown_pct']:.2f}%")

    # =========================================================================
    # Part 4: Entry Refinements (E0, E1, E2, E3) on K-038 MVC
    # =========================================================================
    print("\n--- Part 4: Simulating Entry Refinements on K-038 MVC (N=86) ---")
    entry_records = {"E0_Instant_Close_Baseline": [], "E1_Pullback_03_ATR_Limit": [], "E2_Micro_Breakout_Confirmation": [], "E3_1m_Microstructure_Reclaim": []}

    for t0 in mvc_events:
        t0_loc = df_1h.index.get_loc(t0)
        if t0_loc + 72 >= len(df_1h):
            continue
        entry_time = t0 + pd.Timedelta(hours=1)
        exit_time_72h = entry_time + pd.Timedelta(hours=72)
        warmup_time = entry_time - pd.Timedelta(minutes=60)
        sub_1m_full = df_1m.loc[warmup_time:exit_time_72h]
        if len(sub_1m_full) < 120:
            continue

        c_1m = sub_1m_full["close"]
        sma21_1m = c_1m.rolling(21).mean()
        slope21_1m = sma21_1m - sma21_1m.shift(3)

        sub_1m = sub_1m_full.loc[entry_time:exit_time_72h]
        p0 = sub_1m["open"].iloc[0]
        atr0 = atr_1h.loc[t0]
        window_60 = sub_1m.iloc[:60]
        p_exit_72h = sub_1m["close"].iloc[-1]

        # E0
        ret_e0 = (p_exit_72h - p0) / p0 - cost
        entry_records["E0_Instant_Close_Baseline"].append({"filled": True, "p_entry": p0, "net_ret": ret_e0})

        # E1
        limit_p = p0 - 0.3 * atr0
        filled_e1 = False
        for i in range(len(window_60)):
            if window_60["low"].iloc[i] <= limit_p:
                p_fill = min(window_60["open"].iloc[i], limit_p)
                ret_e1 = (p_exit_72h - p_fill) / p_fill - cost
                entry_records["E1_Pullback_03_ATR_Limit"].append({"filled": True, "p_entry": p_fill, "net_ret": ret_e1})
                filled_e1 = True
                break
        if not filled_e1:
            entry_records["E1_Pullback_03_ATR_Limit"].append({"filled": False, "p_entry": np.nan, "net_ret": 0.0})

        # E2
        high_15m = window_60["high"].iloc[:15].max()
        filled_e2 = False
        for i in range(15, len(window_60)):
            if window_60["high"].iloc[i] > high_15m:
                p_fill = max(window_60["open"].iloc[i], high_15m)
                ret_e2 = (p_exit_72h - p_fill) / p_fill - cost
                entry_records["E2_Micro_Breakout_Confirmation"].append({"filled": True, "p_entry": p_fill, "net_ret": ret_e2})
                filled_e2 = True
                break
        if not filled_e2:
            entry_records["E2_Micro_Breakout_Confirmation"].append({"filled": False, "p_entry": np.nan, "net_ret": 0.0})

        # E3
        had_pullback = False
        filled_e3 = False
        for i in range(len(window_60)):
            t_now = window_60.index[i]
            c_now = window_60["close"].iloc[i]
            sma_now = sma21_1m.loc[t_now]
            slp_now = slope21_1m.loc[t_now]
            if window_60["low"].iloc[i] < p0:
                had_pullback = True
            if had_pullback and c_now > sma_now and slp_now > 0:
                p_fill = window_60["close"].iloc[i]
                ret_e3 = (p_exit_72h - p_fill) / p_fill - cost
                entry_records["E3_1m_Microstructure_Reclaim"].append({"filled": True, "p_entry": p_fill, "net_ret": ret_e3})
                filled_e3 = True
                break
        if not filled_e3:
            entry_records["E3_1m_Microstructure_Reclaim"].append({"filled": False, "p_entry": np.nan, "net_ret": 0.0})

    entry_metrics = {}
    for e_name, recs in entry_records.items():
        df_e = pd.DataFrame(recs)
        n_filled = int(df_e["filled"].sum())
        fill_rate = float(np.round(n_filled / total_mvc * 100, 2))
        filled_rets = df_e[df_e["filled"]]["net_ret"].values
        filled_mean = float(np.round(np.mean(filled_rets) * 100, 2)) if len(filled_rets) > 0 else 0.0
        total_ret = float(np.round(np.sum(df_e["net_ret"].values) * 100, 2))
        entry_metrics[e_name] = {
            "total_opportunities": total_mvc,
            "filled_trades": n_filled,
            "fill_rate_pct": fill_rate,
            "filled_net_mean_pct": filled_mean,
            "total_opportunity_net_return_pct": total_ret,
        }
        print(f"{e_name:32s}: Fills={n_filled}/{total_mvc} ({fill_rate:.1f}%), Filled Net EV={filled_mean:+.2f}%, Total Net Ret={total_ret:+.2f}%")

    # =========================================================================
    # Part 5: Simulating 1m Path for Signal C (Stage 2 Short, N=15)
    # =========================================================================
    print("\n--- Part 5: Simulating 1m Path for Signal C Stage 2 Short (N=15) ---")
    sig_c_strat_names = [
        "S0_Baseline_Fixed_72h",
        "S1_Fixed_Safe_Floor_579",
        "S3_Dynamic_Structural_SMA34",
    ]
    sig_c_trades = {s: [] for s in sig_c_strat_names}

    for t0 in sig_c_events:
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
        sub_highs = sub_1m["high"].values
        sub_lows = sub_1m["low"].values
        sub_opens = sub_1m["open"].values
        sub_times = sub_1m.index

        # S0 Short
        p_exit_s0 = sub_1m["close"].iloc[-1]
        ret_s0 = (p0 - p_exit_s0) / p0 - cost
        sig_c_trades["S0_Baseline_Fixed_72h"].append({"net_ret": ret_s0, "duration_h": 72.0, "exit": "timeout"})

        # S1 Short (Upper boundary breach: p0 + 5.79 ATR)
        stop_p_s1 = p0 + 5.79 * atr0
        exited_s1 = False
        for i in range(len(sub_1m)):
            if sub_highs[i] >= stop_p_s1:
                p_exit = max(sub_opens[i], stop_p_s1)
                ret_s1 = (p0 - p_exit) / p0 - cost
                sig_c_trades["S1_Fixed_Safe_Floor_579"].append({"net_ret": ret_s1, "duration_h": float(np.round(i / 60.0, 2)), "exit": "stop"})
                exited_s1 = True
                break
        if not exited_s1:
            sig_c_trades["S1_Fixed_Safe_Floor_579"].append({"net_ret": ret_s0, "duration_h": 72.0, "exit": "timeout"})

        # S3 Short (Dynamic SMA34 + 4.43 ATR breach)
        exited_s3 = False
        for i in range(len(sub_1m)):
            t_bar = sub_times[i]
            t_1h = (t_bar - pd.Timedelta(hours=1)).floor("1h")
            assert t_1h + pd.Timedelta(hours=1) <= t_bar, f"Lookahead in Signal C S3: {t_1h} vs {t_bar}"
            sma34_cur = sma_34_1h.loc[t_1h] if t_1h in sma_34_1h.index else sma_34_1h.loc[t0]
            atr_cur = atr_1h.loc[t_1h] if t_1h in atr_1h.index else atr0
            stop_p = sma34_cur + 4.43 * atr_cur
            if sub_highs[i] >= stop_p:
                p_exit = max(sub_opens[i], stop_p)
                ret_s3 = (p0 - p_exit) / p0 - cost
                sig_c_trades["S3_Dynamic_Structural_SMA34"].append({"net_ret": ret_s3, "duration_h": float(np.round(i / 60.0, 2)), "exit": "sma34_breach"})
                exited_s3 = True
                break
        if not exited_s3:
            sig_c_trades["S3_Dynamic_Structural_SMA34"].append({"net_ret": ret_s0, "duration_h": 72.0, "exit": "timeout"})

    sig_c_metrics = {}
    for s_name, trades in sig_c_trades.items():
        sig_c_metrics[s_name] = compute_metrics(trades, total_sig_c, cost=cost)
        m = sig_c_metrics[s_name]
        print(f"Signal C {s_name:30s}: Net EV={m['net_mean_return_pct']:+.2f}%, PF={m['profit_factor']:.2f}, WinRate={m['win_rate_pct']:.1f}%, Worst={m['worst_trade_pct']:+.2f}%, MaxDD={m['max_drawdown_pct']:.2f}%, TotalNet={m['total_opportunity_net_return_pct']:+.2f}%")

    # =========================================================================
    # Part 6: Save Comprehensive Remediated metrics.json
    # =========================================================================
    metrics_output = {
        "experiment_id": "EXP-69",
        "description": "1h K-038 MVC & Signal C x 1m Intra-bar Path Integration (Remediated: Zero Lookahead & Full Breakdown)",
        "audit_remediation_issue": "Issue #73",
        "total_mvc_opportunities": total_mvc,
        "total_signal_c_opportunities": total_sig_c,
        "mvc_exit_strategies": mvc_metrics_all,
        "mvc_entry_refinements": entry_metrics,
        "signal_c_exit_strategies": sig_c_metrics,
    }

    with open(exp_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_output, f, indent=2)
    print(f"\nSaved remediated metrics to {exp_dir / 'metrics.json'}")

    # =========================================================================
    # Part 7: Generate Publication-Quality Plots
    # =========================================================================
    print("\n--- Part 7: Generating Publication Plots ---")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    # Plot 1: 1m Individual Paths & Dynamic Safe Floor
    fig, ax = plt.subplots(figsize=(14, 7))
    for norm_p, era in path_trajectories:
        alpha = 0.25 if era == "P2_Bear" else 0.15
        color = "crimson" if era == "P2_Bear" else ("royalblue" if era == "P1_Bull" else "forestgreen")
        time_hrs = np.linspace(0, 72, len(norm_p))
        ax.plot(time_hrs, norm_p, color=color, alpha=alpha, linewidth=1.0)

    # Overplot theoretical envelopes
    ax.axhline(-5.79, color="darkred", linestyle="--", linewidth=2.5, label="Fixed Safe Floor (-5.79 ATR)")
    # Step function
    step_t = [0, 12, 12, 24, 24, 72]
    step_sf = [-3.63, -3.63, -5.49, -5.49, -5.79, -5.79]
    ax.plot(step_t, step_sf, color="orange", linestyle="-.", linewidth=2.5, label="Time-Elapsing Safe Floor (Step)")
    ax.axhline(0, color="black", linestyle=":", linewidth=1.5, label="Entry Price (p0)")

    ax.set_title("EXP-69: 1m Intra-bar Paths & Invalidation Floors (N=86 K-038 MVC)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Elapsed Time from Signal Execution (Hours)", fontsize=12)
    ax.set_ylabel("Price Excursion from Entry (ATR Units)", fontsize=12)
    ax.set_ylim(-16, 20)
    ax.legend(loc="upper left", frameon=True, fontsize=11)
    plt.tight_layout()
    plt.savefig(plots_dir / "01_individual_1m_paths_and_safe_floor.png", dpi=300)
    plt.close()

    # Plot 2: Exit Strategies Performance Comparison (Full Period)
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    s_labels = [
        "S0 Base", "S1 FixSF", "S2 StepSF", "S3 k=4.43",
        "S3 k=3.5", "S3 k=5.0", "S3 1hClose", "S4 Ratchet", "S5 Comp"
    ]
    net_evs = [mvc_metrics_all[s]["Full"]["net_mean_return_pct"] for s in strat_names]
    pfs = [mvc_metrics_all[s]["Full"]["profit_factor"] for s in strat_names]
    worsts = [mvc_metrics_all[s]["Full"]["worst_trade_pct"] for s in strat_names]
    durs = [mvc_metrics_all[s]["Full"]["avg_duration_hours"] for s in strat_names]

    axes[0, 0].bar(s_labels, net_evs, color="steelblue", alpha=0.85)
    axes[0, 0].axhline(mvc_metrics_all["S0_Baseline_Fixed_72h"]["Full"]["net_mean_return_pct"], color="red", linestyle="--")
    axes[0, 0].set_title("Net EV (%) Net of 40 bps", fontweight="bold")
    axes[0, 0].tick_params(axis="x", rotation=30)

    axes[0, 1].bar(s_labels, pfs, color="seagreen", alpha=0.85)
    axes[0, 1].axhline(mvc_metrics_all["S0_Baseline_Fixed_72h"]["Full"]["profit_factor"], color="red", linestyle="--")
    axes[0, 1].set_title("Profit Factor", fontweight="bold")
    axes[0, 1].tick_params(axis="x", rotation=30)

    axes[1, 0].bar(s_labels, worsts, color="indianred", alpha=0.85)
    axes[1, 0].axhline(mvc_metrics_all["S0_Baseline_Fixed_72h"]["Full"]["worst_trade_pct"], color="black", linestyle="--")
    axes[1, 0].set_title("Worst Trade Loss (%) [Higher is Better]", fontweight="bold")
    axes[1, 0].tick_params(axis="x", rotation=30)

    axes[1, 1].bar(s_labels, durs, color="mediumpurple", alpha=0.85)
    axes[1, 1].set_title("Average Holding Duration (Hours)", fontweight="bold")
    axes[1, 1].tick_params(axis="x", rotation=30)

    plt.suptitle("EXP-69: Exit Strategy Comparison on K-038 MVC (N=86, Remediated)", fontsize=15, fontweight="bold")
    plt.tight_layout()
    plt.savefig(plots_dir / "02_exit_strategy_performance_comparison.png", dpi=300)
    plt.close()

    # Plot 3: Entry Refinements Tradeoff (E0 to E3)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    e_labels = ["E0 (Instant)", "E1 (Pullback -0.3)", "E2 (15m Break)", "E3 (1m Reclaim)"]
    e_keys = ["E0_Instant_Close_Baseline", "E1_Pullback_03_ATR_Limit", "E2_Micro_Breakout_Confirmation", "E3_1m_Microstructure_Reclaim"]
    fill_rates = [entry_metrics[k]["fill_rate_pct"] for k in e_keys]
    total_rets = [entry_metrics[k]["total_opportunity_net_return_pct"] for k in e_keys]

    axes[0].bar(e_labels, fill_rates, color="teal", alpha=0.85)
    axes[0].set_title("Execution Fill Rate (%)", fontweight="bold", fontsize=12)
    axes[0].set_ylim(0, 110)
    for i, v in enumerate(fill_rates):
        axes[0].text(i, v + 2, f"{v:.1f}%", ha="center", fontweight="bold")

    axes[1].bar(e_labels, total_rets, color="darkorange", alpha=0.85)
    axes[1].set_title("Total Opportunity Cumulative Return (%) [Net of 40 bps]", fontweight="bold", fontsize=12)
    for i, v in enumerate(total_rets):
        axes[1].text(i, v + 2, f"+{v:.1f}%", ha="center", fontweight="bold")

    plt.suptitle("EXP-69: Execution Refinements & Opportunity Drag", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(plots_dir / "03_entry_refinement_tradeoff_matrix.png", dpi=300)
    plt.close()

    # Plot 4: Cross-Period Exit Robustness (P1 Bull, P2 Bear, P3 Mixed)
    fig, ax = plt.subplots(figsize=(14, 7))
    comp_strats = ["S0_Baseline_Fixed_72h", "S1_Fixed_Safe_Floor_579", "S2_Time_Elapsing_Safe_Floor", "S3_Sensitivity_k50", "S4_Dynamic_Profit_Ratchet"]
    x = np.arange(len(comp_strats))
    width = 0.25

    p1_ev = [mvc_metrics_all[s]["P1_Bull"]["net_mean_return_pct"] for s in comp_strats]
    p2_ev = [mvc_metrics_all[s]["P2_Bear"]["net_mean_return_pct"] for s in comp_strats]
    p3_ev = [mvc_metrics_all[s]["P3_Mixed"]["net_mean_return_pct"] for s in comp_strats]

    ax.bar(x - width, p1_ev, width, label="P1 Bull (2020-2021, N=29)", color="royalblue", alpha=0.85)
    ax.bar(x, p2_ev, width, label="P2 Bear (2022, N=18)", color="crimson", alpha=0.85)
    ax.bar(x + width, p3_ev, width, label="P3 Mixed (2023-2025, N=39)", color="forestgreen", alpha=0.85)

    ax.axhline(0, color="black", linestyle="--", alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(["S0 (Base)", "S1 (FixSF)", "S2 (StepSF)", "S3 (k=5.0)", "S4 (Ratchet)"], fontsize=11)
    ax.set_ylabel("Net Mean Return (%)", fontsize=12)
    ax.set_title("EXP-69: Cross-Period Regime Stability across Exit Strategies", fontsize=14, fontweight="bold")
    ax.legend(frameon=True, fontsize=11)
    plt.tight_layout()
    plt.savefig(plots_dir / "04_cross_period_invalidation_stability.png", dpi=300)
    plt.close()

    print("All plots generated successfully.")
    print("=== EXP-69 Remediated Execution Complete ===")


if __name__ == "__main__":
    main()
