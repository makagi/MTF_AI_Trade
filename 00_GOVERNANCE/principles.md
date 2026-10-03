# MTFシステムトレード Principles

**Version:** 0.1
**Status:** Draft

## 1. Knowledge and Evidence

### 1.1 事実・解釈・仮説・結論を分離する

以下を混同しない。

```text
Observation
    ↓
Interpretation
    ↓
Hypothesis
    ↓
Experiment
    ↓
Evidence
    ↓
Conclusion
```

検証されていない仮説を確定した知識として扱わない。

### 1.2 根拠を追跡可能にする

重要な判断には、可能な限り、

* データ
* 分析
* 実験
* 過去の判断
* 関連する仕様

などの根拠を紐付ける。

### 1.3 結果だけでなく失敗も知識化する

期待した結果が得られなかった実験も記録する。

失敗した仮説や採用しなかった案も、将来の重複実験を防ぐ知識として扱う。

---

## 2. MTF Analysis

### 2.1 時間軸を明示する

市場分析では、可能な限り観測対象の時間軸を明示する。

「上昇している」「サポートがある」などの記述だけで完結させず、

> どの時間軸で見た場合の判断なのか

を明確にする。

### 2.2 時間軸間の関係を扱う

各時間軸を独立した情報として扱うだけでなく、

* 上位時間軸
* 中位時間軸
* 下位時間軸

の関係を分析する。

### 2.3 固定的な解釈を避ける

同じ価格水準や指標でも、時間軸・市場状態・ボラティリティなどによって意味が変わる可能性を考慮する。

---

## 3. Separation of Concerns

### 3.1 ConceptとSpecificationを分離する

**Concept**

> どう市場を理解するか。

**Specification**

> このシステムでは具体的にどう実装・判定するか。

Conceptを変更せずにSpecificationを変更できる構造を目指す。

### 3.2 StrategyとImplementationを分離する

戦略上の意図と、その実装方法を混同しない。

```text
Concept
    ↓
Specification
    ↓
Strategy
    ↓
Implementation
```

という関係を基本とする。

### 3.3 ResearchとProductionを分離する

研究・実験用コードと実運用コードを必要に応じて分離する。

---

## 4. Reproducibility

重要な分析・実験・バックテストについて、可能な限り以下を記録する。

* Data Version
* Code Version
* Specification Version
* Parameters
* Time Period
* Market
* Timeframe
* Result

「同じ条件なら同じ結果を再現できる」ことを基本的な目標とする。

---

## 5. Change Management

### 5.1 変更理由を記録する

重要な仕様変更では、

* 何を変更したか
* なぜ変更したか
* 何を根拠にしたか
* 影響範囲
* 変更後に何を再検証する必要があるか

を記録する。

### 5.2 過去の判断を消さない

現在の仕様だけを残して過去の判断を消去するのではなく、必要に応じてDecision LogやHistoryに残す。

---

## 6. AI Collaboration

### 6.1 AIに役割を与える

AI Agentは役割ごとに責務を明確化する。

例：

* Research Agent
* Analysis Agent
* Hypothesis Agent
* Experiment Agent
* Coding Agent
* Validation Agent
* Knowledge Agent

### 6.2 AIによる推測と確認済み情報を区別する

AIが推論した内容を、外部データや実験によって確認された事実と同一視しない。

### 6.3 AIによる変更を追跡可能にする

AIが作成・変更した重要なドキュメント、仕様、コードについて、可能な限り変更理由と関連Issueを追跡可能にする。

---

## 7. Simplicity

最初から過剰に複雑な仕組みを構築しない。

まず最小限の構造で開始し、実際の利用によって必要性が確認されたものから詳細化する。

**「将来必要かもしれない」だけで仕様を固定しない。**

---

## 8. Single Source of Truth

同じ意味の情報を複数箇所に重複して定義しない。

基本的には、

```text
Concept
    ↓
Specification
    ↓
Implementation
```

のように、上位の定義を下位が参照する構造を目指す。

重複が避けられない場合は、どの文書が正となるかを明示する。

---

## 9. Continuous Improvement

完成を最終目的としない。

```text
Build
 ↓
Measure
 ↓
Learn
 ↓
Change
 ↓
Validate
 ↓
Build
```

という継続的改善を基本とする。

システムだけでなく、

* 分析方法
* ドキュメント構造
* AI Agent
* 開発プロセス
* 検証方法

も改善対象とする。
