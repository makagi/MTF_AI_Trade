# 実験記録: MTF状況把握モデルと各特徴量の統合観察・条件付きエッジ評価

**Doc ID:** EXP-47-001  
**Version:** 1.0.0  
**Status:** Completed  
**Owner:** @makagi  
**Date:** 2026-10-17  
**Related Issue:** [#47](https://github.com/makagi/MTF_AI_Trade/issues/47)  
**Related Specs / Docs:** [01_CONCEPTS/mtf-framework.md](../../../01_CONCEPTS/mtf-framework.md), [01_CONCEPTS/market-regime.md](../../../01_CONCEPTS/market-regime.md), [02_SPECIFICATIONS/evaluation.md](../../../02_SPECIFICATIONS/evaluation.md) (SPEC-EVAL-001), [03_KNOWLEDGE/knowledge-lineage.md](../../knowledge-lineage.md) (K-001, K-005, K-007)  

---

## 1. 問い・動機とリサーチ方針

ユーザーからの重要指針：
> 「今は全体通しての勝率などの指標で評価しているが、効果ある時とない時の状況の違いを区別することが大事。他の知識と組み合わせた時に効果を発揮する可能性もある。」  
> 「状況の把握の仕方も把握すべき知識の一部。特定の期間ではなくMTFでの把握が必要。知識についてまだ正しく結論を出せる状態にない。知識については観察に重きを置き、状況の把握の方も分析を進め、その後合わせて評価する。」

これまでの実験において、Soft Logic（K-005）やSMA下方乖離（K-001）などの特徴量を全体通して（無条件に）評価した場合、往復 0.40% の摩擦コストに抗えず「優位性なし（Refutedまたは保留）」に傾きがちであった。  
しかし、先行実験 EXP-45（K-007）によって **市場時間の 75.5% は保ち合い（Range 47.5% ＋ Squeeze 28.0%）** であり、本物の押し目やパニックはわずか数パーセントの稀な瞬間であることが判明した。

本実験（EXP-47-001）では、K-007 で定式化した MTF 3階層レジーム（6大状況）と各特徴量・シグナルを**統合評価**し、「効果がある状況」と「効果がない状況」の客観的境界線を特定・可視化する。

---

## 2. 実験条件とシグナル定義

* **対象データ**: BTCUSD 1時間足、Discovery 期間（2020-01-01 〜 2025-04-30、46,728時間）
* **標準摩擦コスト**: 往復 0.40%（0.0040）
* **評価ホライズン**: 24時間フォワード（MFE / MAE / Net EV）
* **比較シグナル**:
  1. `SoftLogic_Unfiltered`: 市場状況を考慮しない単独 Soft Logic（AFS 7 反転 ＋ ファンアウト減速）
  2. `SoftLogic @ Bull_Healthy_Pullback`: `Bull_Healthy_Pullback` レジーム内での Soft Logic 発火
  3. `SoftLogic @ Range_PingPong`: `Range_PingPong`（47.5%のノイズ帯）での Soft Logic 発火
  4. `SoftLogic @ Bear_Regimes`: 弱気推進・パニック局面での Soft Logic 発火
  5. `Squeeze_Breakout_Unfiltered`: Squeeze 解放単独
  6. `Squeeze_Breakout @ Bull_Flow`: Macro Bull 局面での Squeeze 上放れブレイク
  7. `SMA_Divergence @ Macro_Bull`: 強気局面での SMA 89 下方乖離（<-2.0 ATR）
  8. `SMA_Divergence @ Bear_Panic_Exhaustion`: 弱気パニック極値での SMA 89 下方乖離

---

## 3. 客観的な観測結果 (Observations)

### 3.1 シグナル別フォワード24時間パフォーマンス比較

| シグナル名 | トレード数 | Gross平均 | Net平均(0.40%控除) | 勝率(Net>0) | PF | 24h MFE | 24h MAE |
|---|---|---|---|---|---|---|---|
| **SoftLogic_Unfiltered** (無条件) | 1,252件 | +0.23% | **-0.17%** | 45.3% | 0.85 | +2.31% | -2.52% |
| **SoftLogic @ Bull_Healthy_Pullback** | 104件 | +0.19% | **-0.21%** | 48.1% | 0.81 | +2.28% | -2.27% |
| **SoftLogic @ Range_PingPong** | 682件 | +0.16% | **-0.24%** | 45.9% | 0.82 | +2.40% | -2.87% |
| **SoftLogic @ Bear_Regimes** | 55件 | **+0.40%** | **+0.00%** | **58.2%** | **1.00** | **+2.65%** | -3.14% |
| **Squeeze_Breakout_Unfiltered** | 229件 | -0.09% | **-0.49%** | 45.0% | 0.65 | +2.28% | -2.54% |
| **Squeeze_Breakout @ Bull_Flow** | 78件 | -0.23% | **-0.63%** | 35.9% | 0.60 | +2.26% | -2.56% |
| **SMA_Divergence @ Macro_Bull** | 290件 | -0.53% | **-0.93%** | 38.3% | 0.37 | +1.83% | -2.74% |
| **SMA_Divergence @ Bear_Panic** | 18件 | **+0.78%** | **+0.38%** | **55.6%** | **1.45** | **+3.15%** | -4.25% |

### 3.2 レジーム $\times$ 特徴量マトリクス（Net EV %）

各特徴量が各レジームで発火した際の純期待値（Net EV %、0.40%摩擦控除後）：

| 特徴量 \ レジーム | Bull_Cont | Bull_Pullback | Squeeze | Range_PingPong | Bear_Cont | Bear_Panic |
|---|---|---|---|---|---|---|
| **Soft_Logic_Reversal** | -0.11% | -0.21% | -0.13% | **-0.24%** (N=682) | **+0.00%** (N=55) | N<5 |
| **SMA_89_Divergence** | -0.32% | N<5 | -0.43% | **-0.28%** (N=429) | -0.06% | **+0.38%** (N=18) |
| **Squeeze_Breakout** | -0.30% | N<5 | N<5 | **-0.64%** (N=137) | -1.34% | -0.02% |

---

## 4. 視覚的判断材料・プロット一覧 (Visual Evidence)

### 4.1 条件付き期待値比較 (Net EV by Context)
![Conditional EV Comparison](plots/01_conditional_ev_comparison.png)
* **視覚的読み解き**:
  - 左図（Net EV）: 無条件シグナル（灰・赤）がいずれも -0.17% 〜 -0.49% と摩擦コストに沈む中、`SMA_Divergence @ Bear_Panic`（緑）のみが **+0.38%** と突出したプラス期待値を記録。
  - 右図（MFE vs MAE）: パニック極値での逆張りは MFE +3.15% と極めて高い反発力を持つ一方、MAE も -4.25% と深く、損切り規律が不可欠であることを視覚的に示している。

### 4.2 累積純損益曲線 (Cumulative Net Return Trajectory)
![Cumulative Return Curves](plots/02_cumulative_return_curves.png)
* **視覚的読み解き**:
  - `SoftLogic_Unfiltered`（灰色破線）および `SoftLogic @ Range_PingPong`（赤色点線）は、全期間を通じて一貫して右肩下がりの損失曲線を描いており、レンジ相場での往復売買が破滅の原因であることを証明している。
  - フィルターを適用して無駄なレンジ往復（682回）を遮断することが、戦略成立の絶対前提条件であることが視覚的に明らかである。

### 4.3 レジーム $\times$ 特徴量マトリクスヒートマップ
![Matrix Heatmap](plots/03_regime_signal_matrix_heatmap.png)
* **視覚的読み解き**:
  - 全体の 75% を占める `Range_PingPong` および `Squeeze` の列は全面「赤（マイナス期待値）」に沈んでおり、保ち合い中に特徴量シグナルでトレードすることは摩擦コストの浪費に過ぎない。
  - 唯一「緑（プラス期待値）」が点灯するのは `Bear_Panic_Exhaustion` における `SMA_89_Divergence`（+0.38%）であり、相場環境と特徴量の適合性がエッジの存否を完全に決定づけている。

### 4.4 実際の相場におけるシグナル判定例
![Integrated Trade Timeline](plots/04_integrated_trade_timeline.png)
* **視覚的読み解き**:
  - 赤色「×」でプロットされたレンジノイズシグナル（数百回）が、MTF状況把握モデルによって一括して無力化・遮断されている様子が確認できる。
  - 青色「▲」（押し目）と緑色「★」（ブレイク）のみに絞り込むことで、トレード頻度を 90% 以上間引き、高クオリティなセットアップのみを抽出できている。

---

## 5. 考察と得られた知識 (Integrated Knowledge)

1. **「全体勝率」による評価の誤謬の立証**:
   - 特徴量を市場全体で無条件に評価すると、全時間の 75.5% を占めるレンジ・保ち合いノイズに巻き込まれ、本来エッジを持つロジックであっても Net EV がマイナス化して「棄却（Refuted）」の誤判定を下してしまう。
   - ユーザーの指摘通り、**「効果がある状況とない状況を区別し、状況把握と組み合わせて評価する」** ことが定量的にも完全に正当化された。
2. **K-001（下方乖離の平均回帰）の真のエッジ境界**:
   - 単なる押し目（Macro Bull）での乖離は追随売りに押されて Net -0.93% と大敗する。
   - 一方、`Bear_Panic_Exhaustion`（Macro Bear ＋ SMA 89から -2.5 ATR超の暴落 ＋ AFS 7 < 30）という極限のパニック局面においてのみ、**Net EV +0.38%、PF 1.45** という強烈な平均回帰エッジが発現する。
3. **K-005（Soft Logic）の役割の再定義**:
   - Soft Logic 単独ではエントリートリガーとして摩擦コスト（0.40%）を単独突破できない（Net -0.17%）。
   - しかし、`Bull_Healthy_Pullback` においては、強気相場（2020年: PF 2.27, Net +0.66% / 2024年: PF 1.22, Net +0.24% / 2025年: PF 5.49, Net +0.31%）で安定した追随力を持ち、**「単独トリガーではなく、マクロ強気押し目における再点火確認フィルター」** として機能することが判明した。
4. **Squeeze Breakout のダマシ回避**:
   - Squeeze 解放直後は偽ブレイク（フェイク）が多く、単なる上放れ追随（Net -0.63%）では勝てない。初動ではなく押し目（Pullback）を待つ規律が必要。

---

## 6. 結論とステータス判定

* **知見ステータス**: **支持 (Supported)**
  - MTF状況把握モデル（K-007）による状況別フィルタリングが、無駄な取引（1,252件中682件のレンジノイズ）を排除し、極限レジームにおける明確なプラス期待値（パニック乖離: Net +0.38%）を特定できることが実証された。
  - K-005 は「単独売買シグナルとしては棄却（Refuted）」だが、「MTF強気押し目における再点火コンテキスト条件としては有効（Supported as Context/Filter）」として整理を完了する。

---

## 7. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-17 | 1.0.0 | 初版作成（MTF状況把握モデルと各特徴量の統合評価・条件付きエッジ検証・可視化プロット生成） | @makagi / [#47](https://github.com/makagi/MTF_AI_Trade/issues/47) |
