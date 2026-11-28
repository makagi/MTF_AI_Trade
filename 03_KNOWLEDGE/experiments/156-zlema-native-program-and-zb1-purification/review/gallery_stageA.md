# MOR-154-01 Stage A Blind Gallery (Pure ZLEMA, Strictly <= t0 ONLY)

> **CRITICAL BLINDING NOTICE**: This file contains strictly causal information `<= t0` (up to `t0 + 59m` on `1m` bars). NO SMA lines, NO `Z_COMP` gate status, NO `M1/C1/C2` labels, and NO forward outcomes are present.
> Follow `SKILL.md` Section 3 strictly: perform **Stage A1 (Profit-Room & Vacuum Analysis)** first using ONLY `case_XX_stageA.png` + this table. Request **Stage A2 (`stageA2_higher_order.json`)** ONLY for cases marked `unsure`.

| Case | UTC `t0` | Close | ATR_24 | `k*_Z` (`State`) | Gap `Z21`/`Z144`/`Z377` (ATR) | `Phi[k*]` (`d3h`) | `C_Phi38` / `C_Curv` / `C_Exp` | `N_ov_Exh` / `WaitGuard` / `Subm%` | `1m vs Z21_1m` (`L/U wick`) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CASE_01** | `2023-08-16 07:00Z` | 29,233.8 | 66.5 | `Z-13` (`Z_BEAR_PULLBACK`) | `+0.33` / `-2.08` / `-3.95` | `-0.15` (`-0.15`) | `-0.16` / `-0.09` / `-0.22` | `0` / `NONE` / `92%` | `-0.06A` (`0.14/0.00`) |
| **CASE_02** | `2024-06-23 06:00Z` | 64,475.5 | 107.4 | `Z-13` (`Z_BULL_PULLBACK`) | `+0.14` / `+3.15` / `+1.39` | `+0.24` (`-0.07`) | `-0.18` / `-0.03` / `-0.20` | `0` / `NONE` / `42%` | `-0.19A` (`0.03/0.13`) |
| **CASE_03** | `2023-10-15 19:00Z` | 26,955.5 | 37.4 | `Z-34` (`Z_BULL_PULLBACK`) | `+1.03` / `+4.83` / `-3.86` | `+0.24` (`+0.37`) | `-0.05` / `+0.14` / `-0.19` | `0` / `NONE` / `33%` | `-0.02A` (`0.02/0.02`) |
| **CASE_04** | `2022-11-06 18:00Z` | 21,273.8 | 64.9 | `Z-144` (`Z_BULL_PULLBACK`) | `+0.25` / `-0.23` / `+3.79` | `+0.23` (`-0.02`) | `+0.32` / `+0.33` / `-0.16` | `0` / `PRE_TOUCH_Z_BULL` / `25%` | `-0.15A` (`0.01/0.32`) |
| **CASE_05** | `2022-10-23 19:00Z` | 19,206.5 | 31.1 | `Z-377` (`Z_BEAR_PULLBACK`) | `+0.09` / `+1.99` / `+0.63` | `-0.21` (`-0.01`) | `-0.08` / `-0.07` / `-0.35` | `0` / `NONE` / `25%` | `-0.07A` (`0.24/0.76`) |
| **CASE_06** | `2024-02-26 15:00Z` | 51,230.2 | 195.9 | `Z-21` (`Z_BEAR_PULLBACK`) | `+0.07` / `-0.84` / `-5.75` | `-0.32` (`+0.21`) | `-0.01` / `-0.06` / `-0.05` | `0` / `NONE` / `67%` | `+0.05A` (`0.19/0.00`) |
| **CASE_07** | `2022-12-12 10:00Z` | 16,952.9 | 44.9 | `Z-21` (`Z_BEAR_PULLBACK`) | `+0.45` / `-5.24` / `-4.72` | `-0.25` (`+0.14`) | `-0.15` / `-0.10` / `-0.10` | `2` / `NONE` / `58%` | `-0.04A` (`0.47/0.40`) |
| **CASE_08** | `2020-03-07 11:00Z` | 9,104.5 | 42.0 | `Z-144` (`Z_BULL_PULLBACK`) | `+0.22` / `+0.79` / `+9.92` | `+0.25` (`-0.01`) | `+0.23` / `+0.38` / `-0.12` | `0` / `PRE_TOUCH_Z_BULL` / `33%` | `-0.04A` (`0.70/0.24`) |
| **CASE_09** | `2023-08-27 06:00Z` | 26,049.3 | 30.4 | `Z-34` (`Z_BEAR_PULLBACK`) | `+0.33` / `+1.71` / `+20.36` | `-0.16` (`-0.00`) | `-0.20` / `-0.23` / `-0.12` | `0` / `NONE` / `33%` | `-0.04A` (`0.00/0.22`) |
| **CASE_10** | `2024-12-17 17:00Z` | 108,148.7 | 675.6 | `Z-55` (`Z_BULL_PULLBACK`) | `+0.99` / `+3.19` / `+6.93` | `+0.37` (`+0.20`) | `+0.45` / `+0.26` / `+0.02` | `0` / `NONE` / `0%` | `+0.06A` (`0.52/0.04`) |

## Stage A1 / A2 Required Output Format per Case
- `Action`: `TAKE` | `PASS` | `unsure` (Stage A1 allows `unsure` -> escalates strictly to `stageA2_higher_order.json`; Final Stage A2 Verdict MUST be binary `TAKE` or `PASS`)
- `Profit Room` & `Main Obstacles`: pure ZLEMA structural assessment from `case_XX_stageA.png` + `1m` strip ONLY
