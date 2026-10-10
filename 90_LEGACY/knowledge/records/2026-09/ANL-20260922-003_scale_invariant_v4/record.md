---
analysis_id: ANL-20260922-003
title: "Scale-Invariant Architecture and Directional Guidance (Strategy V4)"
symbol: BTCUSD
timeframe: 1h
dataset_id: BTCUSD_1H_DISCOVERY
period:
  start: "2020-01-01"
  end: "2023-12-31"
status: completed

findings:
  - FIND-20260922-003-01
  - FIND-20260922-003-02
hypotheses:
  - HYP-20260922-003-01
derived_from: []
related: []
---

# Scale-Invariant Architecture and Directional Guidance (Strategy V4)

## 1. 目的と問い (Question)
特定のSMA（377や610など）に依存するハードコードされたマルチエンジン（V3）のカーブフィッティング問題を排除し、MTFにおける「最も圧縮されたボラティリティ階層」から動的にターゲットを算出する「完全スケール不変アーキテクチャ（V4）」の堅牢性を検証する。

## 2. 分析手法と数式 (Methodology)
特定パラメーターを排除し、以下のように動的にターゲットと損切りを決定する。

$$ k_{ignite} = \text{MTF階層の中で最もBandwidth Percentileが低い（圧縮された）階層} $$
$$ TP_{target} = \text{SMA}(k_{ignite} + 2) $$
$$ SL_{target} = \text{BB\_Lower}(k_{ignite}) $$

## 3. 主な結果 (Key Results)
V3の固定パラメーター依存から解放されたことで、トレード回数が数倍に激増し、あらゆるスケールの波を捕捉できるようになった（フラットな停滞期の完全消滅）。
しかし、最終ストレステスト（ロバストネス評価）において、純粋なV4は全階層でプロフィットファクターが1.0を割り込み、システムが崩壊することが判明した。

![V4 Equity Evolution](artifacts/v4_equity_evolution.png)
![Final Robustness Evaluation](artifacts/final_robustness_evaluation.png)

## 4. 解釈と考察 (Interpretation)
- **わかったこと**: ボラティリティの圧縮（スクイーズ）は「いつ、どれだけのエネルギーで価格が爆発するか」を完璧に予測するが、「上下どちらに爆発するか（方向）」は予測しない。V3が勝っていたのは、固定パラメーターの中に「上昇トレンド」というバイアスが偶然内包されていたからである。
- **課題**: ボラティリティエンジンには、方向性を決定づけるスケール不変の羅針盤（ダイバージェンス等）が不可欠である。

## 5. 発見と次の仮説 (Findings & Hypotheses)
- **[FIND-20260922-003-01]**: 動的ボラティリティ検知（Kinetic Engine）により、特定のSMAへの依存を排除してターゲットを動的算出（Scale-Invariance）することは可能である。
- **[FIND-20260922-003-02]**: スケール不変なボラティリティ検知のみでは勝率が維持できない。方向性を示すフィルター（Divergence等）が欠落すると、下落トレンド中の休止もロングしてしまう。
- **[HYP-20260922-003-01]**: 動的なボラティリティ検知（Kinetic Engine）に、スケール不変のダイバージェンス（Directional Compass）と無重力空間（The Void）を完全に統合すれば、全スケールにおいて堅牢なPFを持つ究極のフラクタルAIが完成するはずである。
  - $\rightarrow$ 次の検証計画：V4のロジックにスケール不変ダイバージェンスを統合したV5の検証。
