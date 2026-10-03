# MTFシステムトレード Documentation Architecture

**Version:** 0.1
**Status:** Draft

## 1. Purpose

本ドキュメントは、プロジェクト内で作成するドキュメントの分類、責務、関係性を定義する。

目的は、情報を適切な場所に配置し、

* 再利用性
* 変更容易性
* AIによる理解・生成
* 人間によるレビュー
* Knowledge Lineage
* 再現性

を高めることである。

---

## 2. Top-Level Structure

```text
00_GOVERNANCE
01_CONCEPTS
02_SPECIFICATIONS
03_KNOWLEDGE
04_IMPLEMENTATION
05_OPERATIONS
99_HISTORY
```

### 00_GOVERNANCE

プロジェクト全体の目的、原則、文書体系、意思決定ルールなどを定義する。

「このプロジェクトは何を目指し、どのような考え方で進めるか」を扱う。

---

### 01_CONCEPTS

市場やシステムを理解するための概念・モデルを定義する。

例：

* Market Model
* MTF Framework
* Market Structure
* Support / Resistance
* Volatility
* Market Regime
* Expected Value

Conceptは、特定の実装やパラメータに強く依存しないことを基本とする。

---

### 02_SPECIFICATIONS

Conceptを具体的なシステム仕様へ変換する。

例：

* Timeframe Specification
* Analysis Specification
* Feature Specification
* Entry Specification
* Exit Specification
* Risk Specification
* Position Sizing Specification

「このシステムでは具体的にどうするか」を定義する。

---

### 03_KNOWLEDGE

仮説、分析、実験、証拠、結論など、プロジェクト活動によって得られた知識を蓄積する。

```text
Hypothesis
    ↓
Experiment
    ↓
Evidence
    ↓
Conclusion
    ↓
Knowledge
```

検証前の仮説と、検証済みの知識を明確に区別する。

---

### 04_IMPLEMENTATION

仕様を実際のシステム、コード、Agent、開発プロセスへ変換するための情報を扱う。

例：

* System Architecture
* Data Architecture
* Software Components
* AI Agents
* Development Workflow
* Testing
* GitHub Workflow

ImplementationはSpecificationの具体化であり、独自の仕様を勝手に上位概念へ昇格させない。

---

### 05_OPERATIONS

バックテスト、実運用、監視、デプロイ、障害対応など、システムを実際に動かすための情報を扱う。

---

### 99_HISTORY

過去の意思決定、変更、廃止された仕様などを記録する。

現在の仕様だけでは説明できない、

> 「なぜ現在こうなっているのか」

を追跡するために使用する。

---

## 3. Document Responsibility

各情報は原則として一つのPrimary Documentを持つ。

```text
Vision
  ↓
Principles
  ↓
Concept
  ↓
Specification
  ↓
Knowledge / Evidence
  ↓
Implementation
  ↓
Operation
```

同じ情報を複数の文書にコピーして保持するのではなく、必要に応じて参照する。

---

## 4. Concept / Specification / Knowledge の区別

### Concept

「何をどう理解するか」

例：

> 市場は複数の時間軸から観測する必要がある。

### Specification

「このシステムでは具体的にどうするか」

例：

> 上位時間軸としてWeekly、中位時間軸としてDaily、下位時間軸として1Hを使用する。

### Hypothesis

「検証したい仮説は何か」

例：

> 上位時間軸と下位時間軸の方向が一致した場合、特定条件下で期待値が変化する。

### Experiment

「仮説をどのように検証したか」

### Evidence

「実験によって何が観測されたか」

### Knowledge / Conclusion

「現在どこまで確認できているか」

これらを混在させない。

---

## 5. Document Lifecycle

ドキュメントは以下のライフサイクルを基本とする。

```text
Idea
 ↓
Draft
 ↓
Review
 ↓
Accepted
 ↓
Used
 ↓
Updated
 ↓
Deprecated
```

ただし、全ての文書が同じライフサイクルを必要とするわけではない。

---

## 6. Versioning

重要なConcept、Specification、Strategyなどはバージョンを管理する。

関連するAnalysis RecordやExperiment Recordでは、可能な限り使用したバージョンを記録する。

```text
Concept Version
Specification Version
Data Version
Code Version
Experiment Version
```

これにより、過去の分析や実験を再現できるようにする。

---

## 7. AIによるDocument Management

AI Agentは新しい情報を得た場合、以下を判断する。

1. 既存文書に追記すべきか
2. 新しい文書が必要か
3. Concept / Specification / Knowledgeのどれに該当するか
4. 既存仕様への変更が必要か
5. Decision Logへの記録が必要か
6. 関連する文書・コード・Experimentへの影響があるか

AIは既存のPrimary Documentを確認してから新しい情報を追加する。

同じ内容の文書を重複して作成しない。

---

## 8. Change Impact

仕様変更時には、可能な限り以下の依存関係を確認する。

```text
Concept
  ↓
Specification
  ↓
Strategy
  ↓
Experiment
  ↓
Implementation
  ↓
Operation
```

上位文書が変更された場合、下位文書への影響を確認する。

特に、過去のExperimentやKnowledgeが現在の仕様変更によって影響を受ける場合は、その関係を記録する。

---

## 9. Initial Repository Structure

初期段階では以下から開始する。

```text
00_GOVERNANCE/
├── vision.md
├── principles.md
└── documentation-architecture.md

01_CONCEPTS/

02_SPECIFICATIONS/

03_KNOWLEDGE/

04_IMPLEMENTATION/

05_OPERATIONS/

99_HISTORY/
```

空のディレクトリについては、必要になるまで詳細なファイルを作成しない。

---

## 10. Design Principle

ドキュメント構造そのものも固定的なものとは考えない。

実際の利用を通じて、

* 分類しにくい情報が増えた
* AIが適切に参照できない
* 変更影響を追跡できない
* 同じ情報が複数箇所に存在する
* 特定の領域が肥大化した

などの問題が発生した場合、Documentation Architecture自体を改善する。

**ドキュメント体系もまた、継続的に改善されるシステムの一部である。**
