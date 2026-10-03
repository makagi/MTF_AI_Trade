# MTFシステムトレード Vision

**Version:** 0.1
**Status:** Draft

## 1. Purpose

本プロジェクトは、Multi-Time-Frame（MTF）による市場認識を中心に、相場分析・仮説・検証・戦略・実装・運用を一貫して扱えるシステムトレード基盤を構築することを目的とする。

単に売買ロジックを実装するのではなく、

> **市場を理解する → 仮説を立てる → 検証する → 知識として蓄積する → 戦略に反映する → 実装する → 結果から学ぶ**

という循環を、再現可能な形で構築する。

## 2. Core Vision

最終的には、人間とAIが協調して継続的にシステムトレードを改善できる基盤を目指す。

```text
Market Data
    ↓
Market Recognition
    ↓
MTF Analysis
    ↓
Hypothesis
    ↓
Experiment
    ↓
Evidence
    ↓
Knowledge
    ↓
Strategy
    ↓
Implementation
    ↓
Validation
    ↓
Result
    ↓
Knowledge Update
    ↺
```

## 3. MTF as the Core Perspective

市場は単一の時間軸だけでは十分に捉えられない。

同一の価格であっても、観測する時間軸によって、

* トレンド
* レンジ
* サポート・レジスタンス
* ボラティリティ
* 市場構造
* 期待される値動き

などの意味が変化する。

本プロジェクトでは、MTFを単なるテクニカル分析手法ではなく、**市場状態を理解するための基本的な分析フレームワーク**として扱う。

## 4. Reproducibility

分析・判断・実験・戦略・実装は、可能な限り再現可能な形で記録する。

特に、

* 何を観測したか
* どのデータを使用したか
* どの時間軸を使用したか
* どの仮説に基づいたか
* どの仕様・パラメータを使用したか
* どの結果が得られたか
* その結果から何を学んだか

を追跡可能にする。

## 5. Knowledge Accumulation

本プロジェクトでは、経験や分析結果を単発の会話やコードとして消費しない。

仮説・実験・証拠・結論・意思決定を関連付け、**Knowledge Lineage（知識の系譜）**として蓄積する。

これにより、

> 「なぜ現在の仕様になっているのか」

を将来の人間・AIが追跡できる状態を目指す。

## 6. Human and AI Collaboration

AIは、分析・調査・実験・実装・レビュー・ドキュメント作成などを支援・自動化する。

ただし、AIが生成した内容は、

* 仮説
* 分析
* 実験結果
* 確認済み知識
* 仕様
* 意思決定

を明確に区別する。

重要な設計判断については、その根拠と変更履歴を記録する。

## 7. Long-Term Goal

最終的には、以下のサイクルを継続的に回せるシステムを目指す。

```text
Human / AI
    ↓
Idea
    ↓
Issue
    ↓
Research
    ↓
Hypothesis
    ↓
Experiment
    ↓
Validation
    ↓
Knowledge
    ↓
Strategy
    ↓
Code
    ↓
Backtest / Live Validation
    ↓
Result
    ↓
Knowledge Update
```

この循環を通じて、システムそのものだけでなく、**システムを改善するための知識と開発プロセスも継続的に進化させる。**
