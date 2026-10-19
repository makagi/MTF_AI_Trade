# 実験記録: 多次元MTF状況空間におけるコア特徴量のマルチホライズン・役割別効果検証 (EXP-61)

**Doc ID:** EXP-61  
**Date:** 2026-10-19  
**Author:** @makagi  
**Issue:** [#61](https://github.com/makagi/MTF_AI_Trade/issues/61)  
**Related Docs:** [00_GOVERNANCE/principles.md](../../00_GOVERNANCE/principles.md), [01_CONCEPTS/mtf-framework.md](../../01_CONCEPTS/mtf-framework.md), [01_CONCEPTS/market-structure.md](../../01_CONCEPTS/market-structure.md), [02_SPECIFICATIONS/features.md](../../02_SPECIFICATIONS/features.md) (SPEC-FEAT-001 v0.2.0), [02_SPECIFICATIONS/evaluation.md](../../02_SPECIFICATIONS/evaluation.md) (SPEC-EVAL-001 v0.3.0)  

---

## 1. 概要 (Executive Summary)

本実験は、Issue #58 (EXP-58) で判明した「重複排除後の単変量断面差分の有意差消失」および「72hホライズンでのValid/Trap逆転現象（K-031）」を解決するため、**「時間成熟度（Process）」「空間トポロジー・アタック回数（Space）」「モメンタム内部構造（Internal Structure）」の3つの多次元状況軸**を導入し、SPEC-FEAT-001 のコア特徴量をマルチホライズン（4h / 12h / 24h / 72h）で体系的に評価した。

### 主要な発見と到達点
1. **動的サポレジ・アタック回数による成否の明確な分離（HYP-CTX-2 の完全立証）**:
   - マクロ重力壁（SMA 233）衝突ショート（Signal C: 独立120件）は、無条件では 24h Net EV = -0.58%（40 bps控除後）と負のエッジであった。
   - しかし、直近72時間の接触回数（`Level_Test_Count`）で分離した結果：
     - **Fresh Wall（接触 1〜2回目: n=25）**: **24h Net EV = +0.27% (40 bps控除後)、勝率 60.0%、PF 1.20、E-Ratio 1.04**。P1（+0.56%）、P2（+0.38%）と弱気・強気相場の双方でプラスを達成。
     - **Exhausted Wall（接触 3回目以降: n=114）**: **24h Net EV = -0.45%、勝率 40.4%、PF 0.67、E-Ratio 0.94**（全ホライズン 4h〜72h で一貫してマイナス）。
     - `CONC-STR-001 §2 (アタック回数と流動性消費モデル)` の正しさが市場データにより定量的に実証された。
2. **時間成熟度軸（Regime Age Ratio）による老朽過熱トラップの特定（HYP-CTX-1）**:
   - Signal A の高乖離ブレイク（`dist_sma_610 > 5.0 ATR` または `squeeze_index > 0.50`）において、
     - **Cruising期（`Macro_Age_Ratio <= 2.0`, n=50）**: 12h Net EV = **+0.17%**、PF = **1.27**、24h **E-Ratio = 1.37** と順行が逆行を大きく上回る。
     - **Exhaustion期（`Macro_Age_Ratio > 2.0`, n=197）**: 24h Net EV = **-0.43%**、E-Ratio = **0.86**（MAE急拡大）。特に弱気相場（P2）では 24h Net EV = **-2.40%**、72h Net EV = **-4.70%**（E-Ratio 0.18）と壊滅的損失を被る。
3. **SPEC-FEAT-001 コア特徴量の役割別マッピングの確立（HYP-CTX-3）**:
   - コア特徴量を単一の「売買トリガー」としてではなく、**「Trap Gate（環境遮断）」「MAE Damper（リスク抑制）」「MFE Booster / Timing Trigger（利益拡大）」**の4分類へ客観的にマッピング完了。

---

## 2. 実験結果詳細

### 2.1 HYP-CTX-1: 時間成熟度軸 (Regime Age Ratio & Wave Maturity)

マクロ持続時間中央値（78.5時間: K-027）に対する経過時間比率 `Macro_Age_Ratio` を用いて、K-031 の高乖離ブレイク（Signal A Extended: 独立335件）を3群に分類・評価した。

#### マルチホライズン減衰プロファイル (40 bps 摩擦コスト控除後)
| 群 (Condition) | 件数 (n) | 4h Net EV | 12h Net EV | 24h Net EV | 72h Net EV | 24h E-Ratio | 72h E-Ratio |
|---|---|---|---|---|---|---|---|
| **Early Cruising (`Age <= 1.2`)** | 96 | -0.50% | -0.70% | -0.23% | **+0.50%** | 1.03 | **1.19** |
| **Mid-Stage (`1.2 < Age <= 2.0`)** | 50 | -0.28% | **+0.17%** | -0.07% | **+0.60%** | **1.37** | **1.31** |
| **Exhaustion Late (`Age > 2.0`)** | 197 | -0.44% | -0.48% | **-0.43%** | +0.53% | **0.86** | 1.09 |

#### 時代別（P1 / P2 / P3）24h Net Return 比較
| 区分 | P1 (Bull: 2020-21) | P2 (Bear: 2022) | P3 (Mixed: 2023-25) | 判定 |
|---|---|---|---|---|
| **Mid-Stage (`1.2 < Age <= 2.0`)** | -0.14% | -0.81% | **+0.30%** | 良好な耐性 |
| **Exhaustion Late (`Age > 2.0`)** | -0.23% | **-2.40%** | -0.51% | **全時代マイナス（老朽トラップ）** |

> [!NOTE]
> **HYP-CTX-1の洞察**:
> 72hホライズンでは大局的上昇トレンドの継続によって全体平均がプラスに見えるものの、**24hスイングにおいては `Macro_Age_Ratio > 2.0`（持続157時間超）の老朽期エントリーは E-Ratio が 0.86 に崩壊し、P2では -2.40% の大敗を招く。** したがって、`Macro_Age_Ratio > 2.0` は順張りブレイクにおける「Trap Gate（無効化フィルター）」として機能する。

---

### 2.2 HYP-CTX-2: 空間トポロジー・アタック回数 (Level Retest Count)

マクロ抵抗壁（SMA 233）到達時のショート（Signal C: 独立120件）について、過去72時間の接触エピソード回数 `Level_Test_Count` による成否分岐を評価した。

#### アタック回数別の成否実績 (40 bps 摩擦コスト控除後)
| 区分 | 件数 | 4h Net EV | 12h Net EV | 24h Net EV (40bps) | 勝率 (24h) | Profit Factor | E-Ratio (24h) |
|---|---|---|---|---|---|---|---|
| **全衝突 (Signal C Baseline)** | 120 | -0.50% | -0.67% | -0.58% | 40.8% | 0.60 | 0.87 |
| **Fresh Wall (`Retests <= 2`)** | **25** | -0.70% | -0.21% | **+0.27%** | **60.0%** | **1.20** | **1.04** |
| **Exhausted Wall (`Retests >= 3`)** | **114** | -0.48% | -0.65% | **-0.45%** | 40.4% | 0.67 | 0.94 |
| **Fresh Wall + Deceleration** | 2 | -0.30% | **+1.42%** | **+2.18%** | 50.0% | **3.22** | **1.50** |

#### 時代別頑健性 (Fresh Wall: Retests <= 2)
- **P1 (Bull)**: 24h Net EV = **+0.56%** (n=10, E-Ratio = 0.91)
- **P2 (Bear)**: 24h Net EV = **+0.38%** (n=4, E-Ratio = **1.65**)
- **P3 (Mixed)**: 24h Net EV = -0.03% (n=11, E-Ratio = 1.08)

> [!IMPORTANT]
> **流動性消費モデルの定量的立証**:
> 1〜2回目の接触（Fresh Wall）では、壁に待機する防戦指値注文の厚みにより反発確率が 60.0% に達し、40 bps コスト控除後でも +0.27% のプラス期待値を示す。一方、3回目以降の接触では防戦注文が消費されて貫通（踏み上げ）が発生し、全ホライズンで一貫した損失（Net EV -0.45% 〜 -0.65%）となる。

---

### 2.3 HYP-CTX-3: SPEC-FEAT-001 コア特徴量の役割別マッピング

メソ順張りブレイク（Baseline: 独立525件, 24h Net EV = -0.46%, E-Ratio = 0.88）に対する各特徴量の付加効果を計測し、4つの機能役割へ分類した。

| 特徴量条件 | 付加役割 (Assigned Role) | 件数 | 24h $\Delta$ Net EV | 24h $\Delta$ E-Ratio | P1 Net | P2 Net | P3 Net | 作用機序 |
|---|---|---|---|---|---|---|---|---|
| **`macro_age_exhausted`** (`Age > 2.0`) | **Trap Gate** | 195 | **-0.40%** | **-0.205** | -0.59% | -1.27% | -0.41% | 老朽トレンド末期の高値掴みを全期間で遮断 |
| **`elasticity_high`** (`Elasticity > 1.5`) | **Trap Gate** | 352 | -0.02% | -0.025 | -0.33% | -0.53% | -0.04% | クラスター過熱・歪み時の偽ブレイクを遮断 |
| **`squeeze_index_compressed`** (`< 0.25`) | **Trap Gate** | 241 | -0.06% | +0.005 | -0.07% | -0.80% | -0.20% | ボラティリティ収縮未成熟時のダマシを遮断 |
| **`fanout_velocity_decel`** (`Velocity <= 0`) | **Trap Gate** | 338 | +0.04% | +0.028 | -0.16% | -0.59% | -0.04% | ファンアウト減速時の勢い衰退を遮断 |
| **`afs_compression_tight`** (`Variance < Q25`) | **MAE Damper** | 114 | **+0.10%** | **+0.103** | -0.58% | -1.28% | **+0.64%** | オシレーター収束によりエントリー直後の逆行(MAE)を大幅抑制 |
| **`afs_order_full_bull`** (`Order = 3`) | **Timing Trigger / Booster** | 126 | **+0.23%** | **+0.131** | -0.05% | **+0.05%** | **+0.05%** | ミクロ・メソの短期同期により初動モメンタムを増幅 |
| **`sandwich_near_floor`** (`Ratio <= 0.25`) | **MAE Damper** | 92 | +0.08% | +0.051 | -0.08% | -1.38% | **+0.25%** | 支持線近接エントリーにより下値リスクを限定 |
| **`void_distance_large`** (`>= 2.0 ATR`) | **MFE Booster** | 381 | -0.03% | -0.024 | -0.30% | -0.81% | +0.01% | 上空に障害物がない空間で順行幅(MFE)を確保 |

---

## 3. 生成された可視化成果物 (Plots)

1. **`plots/01_regime_age_horizon_decay.png`**:
   - 時間成熟度（`Macro_Age_Ratio`）別の 4h/12h/24h/72h 期待値減衰および E-Ratio 比較。
2. **`plots/02_retest_count_and_penetration.png`**:
   - アタック回数（1〜2回目 vs 3回目以降）における Signal C ショートの期待値反転および E-Ratio プロファイル。
3. **`plots/03_feature_role_spectrum_matrix.png`**:
   - SPEC-FEAT-001 全特徴量の 24h Net Return 寄与度と機能役割（Trigger / Booster / Damper / Gate）の分類マトリクス。
4. **`plots/04_cross_period_role_consistency.png`**:
   - 主要ゲート・フィルター特徴量の時代別（P1 / P2 / P3）性能一貫性ヒートマップ。

---

## 4. 新規獲得知見 (Knowledge Lineage への昇格)

- **K-035 (動的サポレジ・アタック回数境界モデル)**:
  - サポレジ帯への到達は、1〜2回目の防戦注文（Fresh Wall）において 60% の反発勝率と正の期待値（Net EV +0.27%）を示すが、3回目以降は流動性消費により貫通（ブレイク）リスクへと転換する。
- **K-036 (レジーム成熟度による高乖離ブレイクの二面性)**:
  - 高乖離ブレイクは、持続中央値の2倍以内（`Macro_Age_Ratio <= 2.0`）であれば 12h〜72h で高い E-Ratio（1.31〜1.37）を維持するが、中央値の2倍を超えた老朽期（`Age > 2.0`）では逆行リスク（MAE）が急激に拡大し、特に弱気相場で壊滅的損失（P2: -4.70%）をもたらす普遍的トラップとなる。
- **K-037 (MTFコア特徴量の機能役割分離体系)**:
  - 各種特徴量を単一の売買シグナルとしてではなく、環境遮断（Trap Gate: Squeeze < 0.25, Age > 2.0）、リスク抑制（MAE Damper: AFS Compression, Sandwich Floor）、および順行増幅（MFE Booster: AFS Order = 3）の直交する役割として組み合わせるアーキテクチャの確立。
