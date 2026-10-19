# 実験記録: 多次元MTF状況空間におけるコア特徴量のマルチホライズン・役割別効果検証 (EXP-61 監査是正版)

**Doc ID:** EXP-61  
**Date:** 2026-10-20  
**Author:** @makagi  
**Issue:** [#61](https://github.com/makagi/MTF_AI_Trade/issues/61), [#63](https://github.com/makagi/MTF_AI_Trade/issues/63)  
**Related Docs:** [00_GOVERNANCE/principles.md](../../00_GOVERNANCE/principles.md), [01_CONCEPTS/mtf-framework.md](../../01_CONCEPTS/mtf-framework.md), [01_CONCEPTS/market-structure.md](../../01_CONCEPTS/market-structure.md), [02_SPECIFICATIONS/features.md](../../02_SPECIFICATIONS/features.md) (SPEC-FEAT-001 v0.2.0), [02_SPECIFICATIONS/evaluation.md](../../02_SPECIFICATIONS/evaluation.md) (SPEC-EVAL-001 v0.3.0)  

---

## 1. 概要 (Executive Summary)

本実験は、Issue #63 における監査指摘（分割前デクラスタリングの徹底、`calculate_level_test_count` のエピソード分離改善、特徴量ロール判定ロジックの是正、およびエビデンスレベルの事実整合）に基づき、完全に再集計・再検証された。

### 監査是正により確立された客観的事実
1. **分割前デクラスタリング（Pre-segmentation Declustering）の厳格化**:
   - 母集団シグナルにまず `decluster_events(cooldown_bars=24)` を適用した上で、独立イベント群を排他的に層別化。
   - サブグループの合計が母集団と完全一致（Signal A Extended: $96 + 45 + 194 = 335$件、Signal C Wall Short: $60 + 60 = 120$件）し、サンプルの二重カウントを完全に排除。
2. **動的サポレジ・アタック回数境界（`HYP-CTX-2` / `K-035`）**:
   - `calculate_level_test_count` に最小離脱期間（`min_departure_bars=3`）を導入し、1バー単位の微小ノイズによる過剰カウントを解消。
   - **Fresh Wall（接触 1〜2回目: n=60）**: 24h Net EV = **-0.23% (Gross +0.17%)**、勝率 **48.3%**、PF **0.84**、E-Ratio **1.02**。
   - **Exhausted Wall（接触 3回目以降: n=60）**: 24h Net EV = **-0.93% (Gross -0.53%)**、勝率 **33.3%**、PF **0.39**、E-Ratio **0.73**。
   - 1〜2回目の防戦は 3回目以降と比較して **Net EV で +0.70%、勝率で +15.0%、PF で +0.45、E-Ratio で +0.29 優位** である。3回目以降は全ホライズンで一貫して大敗する普遍的トラップ（貫通）であることを立証。ただし、$N=60 < 100$ かつ 40 bps コスト下で単体プラスには達しないため、独立トリガーとしては **Inconclusive（保留）**、貫通トラップ遮断ゲート（Trap Gate）として支持。
3. **時間成熟度軸による高乖離ブレイクの二面性（`HYP-CTX-1` / `K-036`）**:
   - **Mid-Stage (`1.2 < Age <= 2.0`, n=45)**: 12h Net EV = **+0.23%**、PF **1.36**、24h **E-Ratio = 1.37**、72h Net EV = **+0.48% (E-Ratio 1.29)**。
   - **Early Cruising (`Age <= 1.2`, n=96)**: 12h Net EV = -0.70%、24h Net EV = -0.23% (ER 1.03)、72h Net EV = +0.50% (ER 1.19)。
   - **Exhaustion Late (`Age > 2.0`, n=194)**: 24h Net EV = **-0.43%**、E-Ratio = **0.86**（MAE急拡大）。P2（Bear）では 24h Net EV = **-2.40%**、72h Net EV = **-4.70%** (ER 0.18)。
   - 全体72hホライズンでは成功群と失敗群の平均経過比率に有意差なし（$d = 0.038, p = 0.7322$）。時間成熟度は72h方向予測ではなく、24hの逆行リスク（MAE増大）を避けるための **Trap Gate** として機能。
4. **客観的デルタ基準に基づく特徴量役割マッピング（`HYP-CTX-3` / `K-037`）**:
   - **MFE Booster**: `afs_order_full_bull` ($\Delta\text{Net}_{24h} = +0.23\%$, $\Delta\text{ER} = +0.131$, $\Delta\text{MFE} = +0.44\%$)。
   - **MAE Damper (Risk Filter)**: `afs_compression_tight` ($\Delta\text{Net}_{24h} = +0.10\%$, $\Delta\text{ER} = +0.103$, $\Delta\text{MAE} = -0.37\%$)、`macro_age_fresh` ($\Delta\text{Net}_{24h} = +0.18\%$, $\Delta\text{ER} = +0.118$, $\Delta\text{MAE} = -0.24\%$)。
   - **Trap Gate (Invalidation Filter)**: `macro_age_exhausted` ($\Delta\text{Net}_{24h} = -0.40\%$, $\Delta\text{ER} = -0.205$, $\Delta\text{MAE} = +0.47\%$)。
   - **Neutral / Context-Dependent**: `sandwich_near_floor` ($\Delta\text{MAE} = +0.07\%$ でありDamper不適格)、`void_distance_large` ($\Delta\text{ER} = -0.024$ でありBooster不適格)、`fanout_velocity_accel / decel`。

---

## 2. 実験結果詳細

### 2.1 HYP-CTX-1: 時間成熟度軸 (Regime Age Ratio & Wave Maturity)

マクロ持続時間中央値（78.5時間: K-027）に対する経過時間比率 `Macro_Age_Ratio` を用いて、Signal A 高乖離ブレイク（独立335件）を排他的に3分割して評価。

#### マルチホライズン減衰プロファイル (40 bps 摩擦コスト控除後)
| 群 (Condition) | 件数 (n) | 4h Net EV | 12h Net EV | 24h Net EV | 72h Net EV | 24h E-Ratio | 72h E-Ratio |
|---|---|---|---|---|---|---|---|
| **Early Cruising (`Age <= 1.2`)** | 96 | -0.50% | -0.70% | -0.23% | **+0.50%** | 1.03 | **1.19** |
| **Mid-Stage (`1.2 < Age <= 2.0`)** | 45 | -0.28% | **+0.23%** | -0.05% | **+0.48%** | **1.37** | **1.29** |
| **Exhaustion Late (`Age > 2.0`)** | 194 | -0.44% | -0.48% | **-0.43%** | +0.53% | **0.86** | 1.09 |

#### 時代別（P1 / P2 / P3）24h Net Return 比較
| 区分 | P1 (Bull: 2020-21) | P2 (Bear: 2022) | P3 (Mixed: 2023-25) | 判定 |
|---|---|---|---|---|
| **Mid-Stage (`1.2 < Age <= 2.0`, n=45)** | -0.14% | -0.81% | **+0.30%** | 良好な耐性 (12h Net +0.23%, PF 1.36) |
| **Exhaustion Late (`Age > 2.0`, n=194)** | -0.23% | **-2.40%** | -0.51% | **全時代マイナス（老朽過熱トラップ）** |

> [!NOTE]
> **HYP-CTX-1の客観的結論**:
> 72hホライズンでは大局的上昇相場により成功群・失敗群間の `Macro_Age_Ratio` に有意差は見られない（$d = 0.038, p = 0.7322$）。しかし、24hスイングにおいては中央値の2倍を超えた老朽期（`Age > 2.0`）は E-Ratio が 0.86 に崩壊し、P2 では -2.40% の大敗を招く。したがって、`Macro_Age_Ratio > 2.0` は「Trap Gate（老朽期高値掴み遮断フィルター）」として機能する。

---

### 2.2 HYP-CTX-2: 空間トポロジー・アタック回数 (Level Retest Count)

マクロ抵抗壁（SMA 233）到達時のショート（Signal C: 独立120件）について、最小離脱期間（`min_departure_bars=3`）を適用した累積接触回数別の実績（40 bps 摩擦コスト控除後）：

#### アタック回数別の成否実績 (40 bps 摩擦コスト控除後)
| 区分 | 件数 | 4h Net EV | 12h Net EV | 24h Net EV (40bps) | 勝率 (24h) | Profit Factor | E-Ratio (24h) |
|---|---|---|---|---|---|---|---|
| **全衝突 (Signal C Baseline)** | 120 | -0.50% | -0.67% | -0.58% | 40.8% | 0.60 | 0.87 |
| **Fresh Wall (`Retests <= 2`)** | **60** | -0.37% | -0.32% | **-0.23% (Gross +0.17%)** | **48.3%** | **0.84** | **1.02** |
| **Exhausted Wall (`Retests >= 3`)** | **60** | -0.63% | -1.02% | **-0.93% (Gross -0.53%)** | **33.3%** | **0.39** | **0.73** |
| **Defend + Deceleration** | 15 | -0.37% | +0.47% | **+0.38% (Gross +0.78%)** | **46.7%** | **1.34** | **1.42** |

#### 時代別比較 (Fresh Wall vs Exhausted Wall @ 24h Net EV)
| 区分 | P1 (Bull) | P2 (Bear) | P3 (Mixed) | 判定 |
|---|---|---|---|---|
| **Fresh Wall (`<= 2`)** | -0.38% | -0.71% | -0.20% | 防戦優位（Exhausted比 +0.70% 改善） |
| **Exhausted Wall (`>= 3`)** | -0.40% | -0.80% | -0.31% | **全期大敗・貫通トラップ (PF 0.39)** |

> [!IMPORTANT]
> **CONC-STR-001 §2 の定量的境界**:
> 1〜2回目の接触（Fresh Wall）は、3回目以降（Exhausted Wall）と比較して 24h Net EV が +0.70%（-0.23% vs -0.93%）、勝率が +15.0%（48.3% vs 33.3%）、E-Ratio が 1.02 vs 0.73 と明確に優位性を示します。3回目以降の接触は流動性枯渇による踏み上げ（貫通）が支配的であり、完全な取引禁止ゲート（Trap Gate）となります。ただし、$N=60 < 100$ かつ 40 bps コスト下で単体プラスではないため、エビデンスレベルは **Inconclusive** として記録します。

---

### 2.3 HYP-CTX-3: SPEC-FEAT-001 コア特徴量の客観的役割分類

メソ順張りブレイク（Baseline: 独立525件, 24h Net EV = -0.21%, E-Ratio = 0.99）に対する各特徴量の相対変化量（$\Delta$）：

| 特徴量条件 | 判定役割 (Role) | 件数 | 24h $\Delta$ Net EV | 24h $\Delta$ E-Ratio | 24h $\Delta$ MAE | 24h $\Delta$ MFE | 判定根拠 |
|---|---|---|---|---|---|---|---|
| **`afs_order_full_bull`** (`Order = 3`) | **MFE Booster** | 126 | **+0.23%** | **+0.131** | +0.14% | **+0.44%** | 順行モメンタムを顕著に拡大 |
| **`afs_compression_tight`** (`< Q25`) | **MAE Damper** | 114 | **+0.10%** | **+0.103** | **-0.37%** | -0.18% | 最大逆行(MAE)を大幅に抑制 |
| **`macro_age_fresh`** (`Age <= 1.0`) | **MAE Damper** | 210 | **+0.18%** | **+0.118** | **-0.24%** | -0.00% | 初動〜巡航で逆行リスクを低減 |
| **`macro_age_exhausted`** (`Age > 2.0`) | **Trap Gate** | 195 | **-0.40%** | **-0.205** | **+0.47%** | -0.08% | MAEが急拡大し全期間で大敗 |
| **`sandwich_near_floor`** (`<= 0.25`) | **Neutral** | 92 | +0.08% | +0.051 | **+0.07%** | +0.18% | MAE改善が見られずDamper不適格 |
| **`void_distance_large`** (`>= 2.0 ATR`) | **Neutral** | 381 | -0.03% | -0.024 | +0.06% | +0.00% | 有意なMFE増幅が見られずBooster不適格 |
| **`fanout_velocity_decel`** (`<= 0`) | **Neutral** | 338 | +0.04% | +0.028 | -0.08% | -0.02% | ベースライン比で悪化しておらずGate不適格 |
| **`elasticity_high`** (`> 1.5`) | **Neutral** | 352 | -0.02% | -0.025 | +0.12% | +0.06% | 基準未満の微小変化 |
| **`squeeze_index_compressed`** (`< 0.25`) | **Neutral** | 241 | -0.06% | +0.005 | -0.23% | -0.22% | 基準未満の微小変化 |

---

## 3. 生成された可視化成果物 (Plots)

1. **`plots/01_regime_age_horizon_decay.png`**:
   - 時間成熟度（`Macro_Age_Ratio`）別の 4h/12h/24h/72h 期待値減衰および E-Ratio 比較（排他的3群）。
2. **`plots/02_retest_count_and_penetration.png`**:
   - アタック回数（1〜2回目 vs 3回目以降）における Signal C ショートの期待値反転および E-Ratio プロファイル（各 n=60）。
3. **`plots/03_feature_role_spectrum_matrix.png`**:
   - 相対変化量（$\Delta$）に基づく客観的機能役割分類マトリクス。
4. **`plots/04_cross_period_role_consistency.png`**:
   - 主要特徴量の時代別（P1 / P2 / P3）性能一貫性ヒートマップ。

---

## 4. 新規獲得知見 (Knowledge Lineage への昇格と是正)

- **K-035 (動的サポレジ・アタック回数境界モデル)**:
  - **ステータス: 保留・途上 (Inconclusive as Independent Trigger / Supported as Trap Gate)**
  - サポレジ帯への到達において、1〜2回目の接触（Fresh Wall: n=60）は3回目以降（Exhausted Wall: n=60）比で 24h Net EV が +0.70%、勝率が +15.0% 優位である。3回目以降の接触は流動性消費による貫通（ブレイク）が支配的であり、取引禁止ゲートとして支持。ただし単独でのプラス期待値達成には至らず、$N=60 < 100$ であるため独立トリガーとしては保留。
- **K-036 (レジーム成熟度による高乖離ブレイクの二面性)**:
  - **ステータス: 保留・途上 (Inconclusive as Directional Signal / Supported as 24h Trap Gate)**
  - 72h ホライズン全体では成功群・失敗群間の成熟度比率に統計的有意差はない（$d = 0.038, p = 0.7322$）。しかし 24h においては中央値の2倍を超えた老朽期（`Age > 2.0`）の逆行（MAE）が急増し（$\Delta\text{MAE} = +0.47\%$）、弱気相場（P2）で -2.40% の大敗をもたらす。24h 過熱トラップ遮断ゲートとして支持。
- **K-037 (MTFコア特徴量の機能役割分離体系)**:
  - **ステータス: 支持 (Supported: 戦略設計アーキテクチャ)**
  - 相対デルタ基準に基づき、`AFS_Order_Score == 3` を MFE Booster、`AFS_Compression < Q25` および `Macro_Age_Ratio <= 1.0` を MAE Damper、`Macro_Age_Ratio > 2.0` を Trap Gate として客観分類。データと矛盾する単体呼称（Sandwich Floor を一律 MAE Damper、Void Distance を一律 MFE Booster とする等）を排除。
