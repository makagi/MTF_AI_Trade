"""EXP-69: 1h K-038 MVC x 1m Intra-bar Path Integration.

Implements SPEC-EVAL-001 v0.4.0 and SPEC-FEAT-001 v0.3.0.
Tracks 4,320-minute 1m price paths for all 86 independent K-038 MVC setups,
evaluates Early Invalidation Exit strategies (Fixed, Time-Elapsing, Dynamic SMA34),
measures Intra-bar Entry Refinements (Pullback Limit vs Micro-Breakout) and opportunity costs,
and evaluates Dynamic Trailing Profit Harvesting.
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
)
from src.evaluation import decluster_events


def compute_trade_metrics(trades: list[dict], total_opportunities: int = 86) -> dict:
    """Compute comprehensive trading performance metrics with 40 bps friction deducted."""
    df_t = pd.DataFrame(trades)
    n_executed = len(df_t)
    if n_executed == 0:
        return {
            "executed_trades": 0,
            "fill_rate_pct": 0.0,
            "net_mean_return_pct": 0.0,
            "profit_factor": 0.0,
            "win_rate_pct": 0.0,
            "worst_trade_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_duration_hours": 0.0,
            "total_opportunity_net_return_pct": 0.0,
        }

    net_rets = df_t["net_ret"].values
    net_mean = float(np.round(np.mean(net_rets) * 100, 2))
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

    # Total opportunity net return across all 86 opportunities
    total_net = float(np.round(np.sum(net_rets) * 100, 2))
    fill_rate = float(np.round(n_executed / total_opportunities * 100, 2))

    return {
        "executed_trades": n_executed,
        "fill_rate_pct": fill_rate,
        "net_mean_return_pct": net_mean,
        "profit_factor": pf,
        "win_rate_pct": win_rate,
        "worst_trade_pct": worst,
        "max_drawdown_pct": max_dd,
        "avg_duration_hours": avg_dur,
        "total_opportunity_net_return_pct": total_net,
    }


def main():
    print("=== Starting EXP-69: 1h K-038 MVC x 1m Intra-bar Path Integration ===")
    exp_dir = Path(__file__).resolve().parent
    plots_dir = exp_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    cost = 0.0040  # 40 bps roundtrip friction

    # =========================================================================
    # Part 1: Extracting 1h K-038 MVC Setups (N=86)
    # =========================================================================
    print("\n--- Part 1: Extracting K-038 MVC Setups from 1h Data ---")
    df_1h = load_ohlcv("BTCUSD", "1h").loc["2020-01-01":"2025-04-30"].copy()
    close_1h = df_1h["close"]
    high_1h = df_1h["high"]
    low_1h = df_1h["low"]
    atr_1h = calculate_atr(df_1h, 24)

    sma_34_1h = calculate_sma(close_1h, 34)
    sma_55_1h = calculate_sma(close_1h, 55)
    slope_55_1h = (sma_55_1h - sma_55_1h.shift(3)) / (3 * atr_1h)

    # Meso breakout raw & decluster (24h Trigger Cooldown)
    meso_breakout_raw = (close_1h > sma_34_1h) & (close_1h.shift(1) <= sma_34_1h.shift(1)) & (slope_55_1h > 0)
    meso_breakout_decl = decluster_events(meso_breakout_raw, 24)

    regime_df_1h = calculate_regime_age(df_1h)
    macro_age_ratio = regime_df_1h["macro_age_ratio"]
    afs_df_1h, afs_order_score, _ = calculate_afs(df_1h, [7, 9, 11, 13])

    mvc_mask = meso_breakout_decl & (macro_age_ratio <= 2.0) & (afs_order_score == 3)
    mvc_events = df_1h.index[mvc_mask]
    total_opportunities = len(mvc_events)
    print(f"Verified K-038 MVC Opportunities: {total_opportunities}")
    assert total_opportunities == 86, f"Expected 86 MVC setups, got {total_opportunities}"

    # Calendar Era tagging
    periods = {
        "P1_Bull": ("2020-01-01", "2021-12-31"),
        "P2_Bear": ("2022-01-01", "2022-12-31"),
        "P3_Mixed": ("2023-01-01", "2025-04-30"),
    }

    # =========================================================================
    # Part 2: Loading 1m High-Resolution Data
    # =========================================================================
    print("\n--- Part 2: Loading 1m High-Resolution Discovery Data ---")
    df_1m = load_ohlcv("BTCUSD", "1m")
    print(f"Loaded 1m DataFrame: {len(df_1m)} rows")

    # =========================================================================
    # Part 3: Simulating Invalidation & Dynamic Exit Strategies (HYP-1M-PATH-1 & 3)
    # =========================================================================
    print("\n--- Part 3: Simulating 1m Path Exit Strategies across all 86 Setups ---")

    # Strategy containers
    strat_trades = {
        "S0_Baseline_Fixed_72h": [],
        "S1_Fixed_Safe_Floor_579": [],
        "S2_Time_Elapsing_Safe_Floor": [],
        "S3_Dynamic_Structural_SMA34": [],
        "S4_Trailing_Profit_Harvest_849": [],
        "S5_Composite_Optimal_Exit": [],
    }

    period_trade_records = {p: {"S0": [], "S1": [], "S5": []} for p in periods}
    path_trajectories = []  # For plotting 1m path curves

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
        sma34_entry = sma_34_1h.loc[t0]

        # Determine period
        p_name = "P3_Mixed"
        for pname, (pstart, pend) in periods.items():
            if pd.Timestamp(pstart, tz="UTC") <= t0 <= pd.Timestamp(pend, tz="UTC"):
                p_name = pname
                break

        # Record trajectory in ATR for plotting sample
        sub_lows = sub_1m["low"].values
        sub_highs = sub_1m["high"].values
        sub_closes = sub_1m["close"].values
        sub_times = sub_1m.index

        # Final fixed 72h return
        p_final_72h = sub_closes[-1]
        ret_baseline = (p_final_72h - p0) / p0 - cost
        is_winner = ret_baseline > 0

        # Subsample path for visualization
        if len(path_trajectories) < 86:
            norm_path = (sub_closes[::30] - p0) / (atr0 + 1e-8)
            time_hours = np.linspace(0, 72, len(norm_path))
            path_trajectories.append({
                "time_hours": time_hours.tolist(),
                "path_atr": norm_path.tolist(),
                "is_winner": bool(is_winner),
            })

        # --- S0: Baseline Fixed 72h ---
        t_s0 = {"net_ret": ret_baseline, "duration_h": 72.0, "exit": "fixed_72h"}
        strat_trades["S0_Baseline_Fixed_72h"].append(t_s0)
        period_trade_records[p_name]["S0"].append(t_s0)

        # --- S1: Fixed Safe Floor (-5.79 ATR) ---
        stop_p_s1 = p0 - 5.79 * atr0
        hit_s1 = sub_lows <= stop_p_s1
        if hit_s1.any():
            hit_idx = np.where(hit_s1)[0][0]
            p_exit_s1 = min(sub_1m["open"].iloc[hit_idx], stop_p_s1)
            dur_s1 = float(np.round(hit_idx / 60.0, 2))
            ret_s1 = (p_exit_s1 - p0) / p0 - cost
            t_s1 = {"net_ret": ret_s1, "duration_h": dur_s1, "exit": "safe_floor_fixed"}
        else:
            t_s1 = t_s0
        strat_trades["S1_Fixed_Safe_Floor_579"].append(t_s1)
        period_trade_records[p_name]["S1"].append(t_s1)

        # --- S2: Time-Elapsing Safe Floor (12h: -3.63, 24h: -5.49, 72h: -5.79) ---
        exited_s2 = False
        for i in range(len(sub_1m)):
            elapsed_h = i / 60.0
            if elapsed_h <= 12.0:
                dyn_stop = 3.63
            elif elapsed_h <= 24.0:
                dyn_stop = 5.49
            else:
                dyn_stop = 5.79

            stop_p_s2 = p0 - dyn_stop * atr0
            if sub_lows[i] <= stop_p_s2:
                p_exit_s2 = min(sub_1m["open"].iloc[i], stop_p_s2)
                ret_s2 = (p_exit_s2 - p0) / p0 - cost
                strat_trades["S2_Time_Elapsing_Safe_Floor"].append({
                    "net_ret": ret_s2, "duration_h": float(np.round(elapsed_h, 2)), "exit": "time_elapsing_sf"
                })
                exited_s2 = True
                break
        if not exited_s2:
            strat_trades["S2_Time_Elapsing_Safe_Floor"].append(t_s0)

        # --- S3: Dynamic Structural Line (SMA34 - 4.43 ATR) ---
        # Look up 1h SMA34 for each hour of holding
        exited_s3 = False
        sub_1h_slice = df_1h.loc[entry_time:exit_time_72h]
        for i in range(len(sub_1m)):
            t_bar = sub_times[i]
            # Get latest available completed 1h SMA34
            t_1h_prev = t_bar.floor("1h")
            if t_1h_prev in sma_34_1h.index:
                sma34_cur = sma_34_1h.loc[t_1h_prev]
                atr_cur = atr_1h.loc[t_1h_prev]
            else:
                sma34_cur = sma34_entry
                atr_cur = atr0

            struct_stop = sma34_cur - 4.43 * atr_cur
            if sub_lows[i] <= struct_stop:
                p_exit_s3 = min(sub_1m["open"].iloc[i], struct_stop)
                dur_s3 = float(np.round(i / 60.0, 2))
                ret_s3 = (p_exit_s3 - p0) / p0 - cost
                strat_trades["S3_Dynamic_Structural_SMA34"].append({
                    "net_ret": ret_s3, "duration_h": dur_s3, "exit": "struct_sma34_hit"
                })
                exited_s3 = True
                break
        if not exited_s3:
            strat_trades["S3_Dynamic_Structural_SMA34"].append(t_s0)

        # --- S4: Trailing Profit Harvest (-8.49 ATR from peak after +3 ATR) ---
        peak_s4 = p0
        exited_s4 = False
        for i in range(len(sub_1m)):
            if sub_highs[i] > peak_s4:
                peak_s4 = sub_highs[i]
            dur_s4 = float(np.round(i / 60.0, 2))

            # Stop at -5.79 ATR
            if sub_lows[i] <= stop_p_s1:
                p_exit_s4 = min(sub_1m["open"].iloc[i], stop_p_s1)
                ret_s4 = (p_exit_s4 - p0) / p0 - cost
                strat_trades["S4_Trailing_Profit_Harvest_849"].append({
                    "net_ret": ret_s4, "duration_h": dur_s4, "exit": "stop"
                })
                exited_s4 = True
                break

            # Trailing take profit (activated when peak >= +3 ATR)
            if (peak_s4 - p0) >= 3.0 * atr0:
                trail_stop = peak_s4 - 8.49 * atr0
                if sub_lows[i] <= trail_stop and trail_stop > p0:
                    p_exit_s4 = min(sub_1m["open"].iloc[i], trail_stop)
                    ret_s4 = (p_exit_s4 - p0) / p0 - cost
                    strat_trades["S4_Trailing_Profit_Harvest_849"].append({
                        "net_ret": ret_s4, "duration_h": dur_s4, "exit": "trailing_harvest"
                    })
                    exited_s4 = True
                    break
        if not exited_s4:
            strat_trades["S4_Trailing_Profit_Harvest_849"].append(t_s0)

        # --- S5: Composite Optimal Exit (Time-Elapsing Safe Floor + Trailing Profit Take) ---
        peak_s5 = p0
        exited_s5 = False
        for i in range(len(sub_1m)):
            if sub_highs[i] > peak_s5:
                peak_s5 = sub_highs[i]
            dur_s5 = float(np.round(i / 60.0, 2))

            # Dynamic Stop
            if dur_s5 <= 12.0:
                cur_stop_atr = 3.63
            elif dur_s5 <= 24.0:
                cur_stop_atr = 5.49
            else:
                cur_stop_atr = 5.79
            stop_p_s5 = p0 - cur_stop_atr * atr0

            if sub_lows[i] <= stop_p_s5:
                p_exit_s5 = min(sub_1m["open"].iloc[i], stop_p_s5)
                ret_s5 = (p_exit_s5 - p0) / p0 - cost
                t_s5 = {"net_ret": ret_s5, "duration_h": dur_s5, "exit": "dyn_safe_floor"}
                strat_trades["S5_Composite_Optimal_Exit"].append(t_s5)
                period_trade_records[p_name]["S5"].append(t_s5)
                exited_s5 = True
                break

            # Trailing Take Profit
            if (peak_s5 - p0) >= 3.0 * atr0:
                trail_stop_s5 = peak_s5 - 8.49 * atr0
                if sub_lows[i] <= trail_stop_s5 and trail_stop_s5 > p0:
                    p_exit_s5 = min(sub_1m["open"].iloc[i], trail_stop_s5)
                    ret_s5 = (p_exit_s5 - p0) / p0 - cost
                    t_s5 = {"net_ret": ret_s5, "duration_h": dur_s5, "exit": "trailing_harvest"}
                    strat_trades["S5_Composite_Optimal_Exit"].append(t_s5)
                    period_trade_records[p_name]["S5"].append(t_s5)
                    exited_s5 = True
                    break
        if not exited_s5:
            strat_trades["S5_Composite_Optimal_Exit"].append(t_s0)
            period_trade_records[p_name]["S5"].append(t_s0)

    # Compute metrics for each strategy
    metrics_strategies = {}
    for s_name, t_list in strat_trades.items():
        metrics_strategies[s_name] = compute_trade_metrics(t_list, total_opportunities)
        print(f"{s_name:32s}: Net EV={metrics_strategies[s_name]['net_mean_return_pct']:+.2f}%, PF={metrics_strategies[s_name]['profit_factor']:.2f}, WinRate={metrics_strategies[s_name]['win_rate_pct']:.1f}%, Worst={metrics_strategies[s_name]['worst_trade_pct']:+.2f}%, MaxDD={metrics_strategies[s_name]['max_drawdown_pct']:.2f}%, AvgDur={metrics_strategies[s_name]['avg_duration_hours']:.1f}h")

    # =========================================================================
    # Part 4: Intra-bar 1m Execution Refinement (HYP-1M-PATH-2)
    # =========================================================================
    print("\n--- Part 4: Simulating Intra-bar 1m Execution Refinements ---")
    entry_refinements = {
        "E0_Instant_Close_Baseline": [],
        "E1_Pullback_03_ATR_Limit": [],
        "E2_Micro_Breakout_Confirmation": [],
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
        p_exit_72h = sub_1m["close"].iloc[-1]

        # E0: Baseline Instant
        entry_refinements["E0_Instant_Close_Baseline"].append({
            "net_ret": (p_exit_72h - p0) / p0 - cost, "filled": True, "duration_h": 72.0
        })

        first_60m = sub_1m.iloc[:60]

        # E1: Pullback 0.3 ATR limit order
        limit_p_e1 = p0 - 0.30 * atr0
        filled_e1 = first_60m["low"] <= limit_p_e1
        if filled_e1.any():
            ret_e1 = (p_exit_72h - limit_p_e1) / limit_p_e1 - cost
            entry_refinements["E1_Pullback_03_ATR_Limit"].append({
                "net_ret": ret_e1, "filled": True, "duration_h": 72.0
            })
        else:
            entry_refinements["E1_Pullback_03_ATR_Limit"].append({
                "net_ret": 0.0, "filled": False, "duration_h": 0.0
            })

        # E2: Micro Breakout Confirmation (Break above first 15m high during 15..60m)
        first_15m_high = sub_1m["high"].iloc[:15].max()
        remaining_45m = sub_1m.iloc[15:60]
        filled_e2 = remaining_45m["high"] > first_15m_high
        if filled_e2.any():
            fill_bar_idx = remaining_45m.index[filled_e2][0]
            fill_p_e2 = max(remaining_45m.loc[fill_bar_idx, "open"], first_15m_high)
            ret_e2 = (p_exit_72h - fill_p_e2) / fill_p_e2 - cost
            entry_refinements["E2_Micro_Breakout_Confirmation"].append({
                "net_ret": ret_e2, "filled": True, "duration_h": 72.0
            })
        else:
            entry_refinements["E2_Micro_Breakout_Confirmation"].append({
                "net_ret": 0.0, "filled": False, "duration_h": 0.0
            })

    metrics_entries = {}
    for e_name, e_list in entry_refinements.items():
        df_e = pd.DataFrame(e_list)
        filled_trades = df_e[df_e["filled"]]
        n_filled = len(filled_trades)
        fill_rate = float(np.round(n_filled / total_opportunities * 100, 2))
        filled_net_mean = float(np.round(filled_trades["net_ret"].mean() * 100, 2)) if n_filled > 0 else 0.0
        total_opportunity_net = float(np.round(df_e["net_ret"].sum() * 100, 2))
        metrics_entries[e_name] = {
            "total_opportunities": total_opportunities,
            "filled_trades": n_filled,
            "fill_rate_pct": fill_rate,
            "filled_net_mean_pct": filled_net_mean,
            "total_opportunity_net_return_pct": total_opportunity_net,
        }
        print(f"{e_name:32s}: FillRate={fill_rate:.1f}% ({n_filled}/{total_opportunities}), Filled Net EV={filled_net_mean:+.2f}%, Total Opportunity Net={total_opportunity_net:+.2f}%")

    # =========================================================================
    # Part 5: Cross-Period Invalidation Robustness (P1, P2, P3)
    # =========================================================================
    print("\n--- Part 5: Cross-Period Invalidation Robustness ---")
    metrics_periods = {}
    for p_name in periods:
        metrics_periods[p_name] = {
            "S0_Baseline": compute_trade_metrics(period_trade_records[p_name]["S0"], len(period_trade_records[p_name]["S0"])),
            "S1_Safe_Floor": compute_trade_metrics(period_trade_records[p_name]["S1"], len(period_trade_records[p_name]["S1"])),
            "S5_Composite": compute_trade_metrics(period_trade_records[p_name]["S5"], len(period_trade_records[p_name]["S5"])),
        }
        print(f"Period {p_name}: S0 Net={metrics_periods[p_name]['S0_Baseline']['net_mean_return_pct']:+.2f}% (Worst={metrics_periods[p_name]['S0_Baseline']['worst_trade_pct']:+.2f}%) -> S1 Net={metrics_periods[p_name]['S1_Safe_Floor']['net_mean_return_pct']:+.2f}% (Worst={metrics_periods[p_name]['S1_Safe_Floor']['worst_trade_pct']:+.2f}%)")

    # Save metrics.json
    final_metrics = {
        "experiment_id": "EXP-69",
        "description": "1h K-038 MVC x 1m Intra-bar Path Integration: Early Invalidation Exit & 1m Execution Refinement",
        "total_mvc_opportunities": total_opportunities,
        "exit_strategies": metrics_strategies,
        "entry_refinements": metrics_entries,
        "cross_period_robustness": metrics_periods,
    }

    metrics_path = exp_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(final_metrics, f, indent=2, ensure_ascii=False)
    print(f"Saved complete metrics to {metrics_path}")

    # =========================================================================
    # Part 6: Generating Diagnostic Visualizations
    # =========================================================================
    print("\n--- Part 6: Generating Diagnostic Visualizations ---")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    # Plot 1: 1m Path Trajectories & Safe Floor Boundary
    fig, ax = plt.subplots(figsize=(12, 6))
    for p in path_trajectories:
        color = "#27ae60" if p["is_winner"] else "#c0392b"
        alpha = 0.25 if p["is_winner"] else 0.40
        ax.plot(p["time_hours"], p["path_atr"], color=color, alpha=alpha, linewidth=1.0)

    # Plot Safe Floor line (-5.79 ATR)
    ax.axhline(-5.79, color="#e74c3c", linewidth=2.5, linestyle="--", label="Fixed Safe Floor (-5.79 ATR)")
    # Plot Time-Elapsing Safe Floor line
    t_elaps = [0, 12, 12, 24, 24, 72]
    sf_elaps = [-3.63, -3.63, -5.49, -5.49, -5.79, -5.79]
    ax.plot(t_elaps, sf_elaps, color="#f39c12", linewidth=2.5, label="Time-Elapsing Safe Floor")

    ax.set_xlabel("Elapsed Time from Entry (Hours)", fontsize=12)
    ax.set_ylabel("Normalized Path Trajectory (ATR)", fontsize=12)
    ax.set_title("K-038 MVC: 4,320-Minute 1m Price Paths vs Early Invalidation Boundaries (N=86)", fontsize=13, fontweight="bold")
    ax.set_ylim(-22, 25)
    ax.legend(frameon=True, fontsize=11, loc="upper left")
    plt.tight_layout()
    p1_path = plots_dir / "01_individual_1m_paths_and_safe_floor.png"
    plt.savefig(p1_path, dpi=300)
    plt.close()
    print(f"Saved: {p1_path}")

    # Plot 2: Exit Strategies Performance Comparison
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    s_names = ["S0_Baseline", "S1_Fixed_SF", "S2_Time_SF", "S3_SMA34_Line", "S4_Trailing", "S5_Composite"]
    net_evs = [metrics_strategies[k]["net_mean_return_pct"] for k in metrics_strategies]
    pfs = [metrics_strategies[k]["profit_factor"] for k in metrics_strategies]
    worsts = [metrics_strategies[k]["worst_trade_pct"] for k in metrics_strategies]

    x_s = np.arange(len(s_names))
    axes[0].bar(x_s, net_evs, color="#3498db", alpha=0.85, width=0.55)
    axes[0].set_xticks(x_s)
    axes[0].set_xticklabels(s_names, rotation=25, ha="right", fontsize=10)
    axes[0].set_ylabel("Net EV (% after 40 bps)", fontsize=11)
    axes[0].set_title("Exit Strategies: Net Expected Value", fontsize=12, fontweight="bold")

    # Worst Trade Reduction
    axes[1].bar(x_s, worsts, color="#e74c3c", alpha=0.85, width=0.55)
    axes[1].set_xticks(x_s)
    axes[1].set_xticklabels(s_names, rotation=25, ha="right", fontsize=10)
    axes[1].set_ylabel("Worst Single Trade (% after 40 bps)", fontsize=11)
    axes[1].set_title("Worst Trade Tail Risk Compression", fontsize=12, fontweight="bold")

    plt.tight_layout()
    p2_path = plots_dir / "02_exit_strategy_performance_comparison.png"
    plt.savefig(p2_path, dpi=300)
    plt.close()
    print(f"Saved: {p2_path}")

    # Plot 3: Entry Refinement Tradeoff Matrix
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    e_labels = ["E0 (Instant)", "E1 (Pullback 0.3 ATR)", "E2 (Micro-Breakout)"]
    fill_rates = [metrics_entries[k]["fill_rate_pct"] for k in metrics_entries]
    total_nets = [metrics_entries[k]["total_opportunity_net_return_pct"] for k in metrics_entries]

    x_e = np.arange(len(e_labels))
    axes[0].bar(x_e, fill_rates, color="#9b59b6", alpha=0.85, width=0.5)
    axes[0].set_xticks(x_e)
    axes[0].set_xticklabels(e_labels, fontsize=11)
    axes[0].set_ylabel("Fill Rate (%)", fontsize=11)
    axes[0].set_title("1m Execution: Fill Rate (Execution Certainty)", fontsize=12, fontweight="bold")
    axes[0].set_ylim(0, 110)

    axes[1].bar(x_e, total_nets, color="#2ecc71", alpha=0.85, width=0.5)
    axes[1].set_xticks(x_e)
    axes[1].set_xticklabels(e_labels, fontsize=11)
    axes[1].set_ylabel("Total Opportunity Net Return (% over 86 Setups)", fontsize=11)
    axes[1].set_title("Missed Opportunity Drag: Cumulative Return", fontsize=12, fontweight="bold")

    plt.tight_layout()
    p3_path = plots_dir / "03_entry_refinement_tradeoff_matrix.png"
    plt.savefig(p3_path, dpi=300)
    plt.close()
    print(f"Saved: {p3_path}")

    # Plot 4: Cross-Period Invalidation Stability
    fig, ax = plt.subplots(figsize=(10, 5.5))
    p_labels = list(periods.keys())
    x_p = np.arange(len(p_labels))
    w_p = 0.35

    s0_p_ev = [metrics_periods[p]["S0_Baseline"]["net_mean_return_pct"] for p in p_labels]
    s1_p_ev = [metrics_periods[p]["S1_Safe_Floor"]["net_mean_return_pct"] for p in p_labels]

    ax.bar(x_p - w_p / 2, s0_p_ev, w_p, label="S0: Baseline 72h Fixed", color="#7f8c8d")
    ax.bar(x_p + w_p / 2, s1_p_ev, w_p, label="S1: Fixed Safe Floor (-5.79 ATR)", color="#27ae60")
    ax.set_xticks(x_p)
    ax.set_xticklabels(["P1 (2020-21 Bull)", "P2 (2022 Bear)", "P3 (2023-25 Mixed)"], fontsize=11)
    ax.set_ylabel("Net EV (%) after 40 bps", fontsize=12)
    ax.set_title("Cross-Period Robustness: Invalidation Exit preserves Positive EV across Regimes", fontsize=13, fontweight="bold")
    ax.legend(frameon=True, fontsize=11)

    plt.tight_layout()
    p4_path = plots_dir / "04_cross_period_invalidation_stability.png"
    plt.savefig(p4_path, dpi=300)
    plt.close()
    print(f"Saved: {p4_path}")

    print("\n=== EXP-69 Execution Completed Successfully ===")


if __name__ == "__main__":
    main()
