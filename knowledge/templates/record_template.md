---
analysis_id: {analysis_id}
title: "{title}"
symbol: {symbol}
timeframe: {timeframe}
dataset_id: {dataset_id}
period:
  start: "{start_date}"
  end: "{end_date}"
status: draft

findings: []
hypotheses: []
derived_from: []
related: []
---

# {title}

## 1. 目的と問い (Question)
何を調べたいか？どういう背景・疑問からこの分析を始めたかを記述する。

## 2. 分析手法・数式 (Methodology)
分析の条件、指標の定義、数式（LaTeX形式）。

$$Condition_t = ...$$

## 3. 主な結果 (Key Results)
主要な統計値、発見、グラフの参照。詳細は `metrics.json` を参照。

![分析グラフ](artifacts/chart_1.png)

## 4. 解釈と考察 (Interpretation)
- **分かったこと**:
- **分からないこと / 課題**:
- **注意点 / バイアス**:

## 5. 発見と次の仮説 (Findings & Hypotheses)
- **[{finding_id}]**: 発見した客観的事実
- **[{hypothesis_id}]**: 発見から生まれた仮説
  - $\rightarrow$ 次の検証計画
