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
90_LEGACY
99_HISTORY
```

### 00_GOVERNANCE

プロジェクト全体の目的、原則、文書体系、前提条件、意思決定ルール、および Issue 駆動の運用規約を定義する。

* `vision.md`: プロジェクトの目的・中長期ゴール
* `principles.md`: 設計・研究・運用の基本原則
* `documentation-architecture.md`: 本ドキュメント（文書構造・責務）
* `issue-driven-workflow.md`: GitHub Issue を起点とする開発・分析・文書管理規約
* `assumptions.md`: システムが暗黙的・明示的に置いている前提条件一覧

---

### 01_CONCEPTS

市場やシステムを理解するための概念・モデルを定義する。

例：

* MTF Framework
* Market Structure
* Market Regime
* Volatility
* Expected Value

Concept は、「何をどう理解するか（見方・モデル）」を扱い、特定の実装やパラメータに依存しないことを基本とする。個別パラメータや具体的な売買ルールはここに書かず、02_SPECIFICATIONS で定義する。

---

### 02_SPECIFICATIONS

Concept を具体的なシステム仕様や売買戦略へ変換する。

* **仕様（Specification: 部品）**:
  * `evaluation.md`: 摩擦コストモデル、データ期間分割、必須メトリクス、合否基準
  * Timeframe Specification
  * Feature Specification
  * Entry / Exit / Risk Specification
  * Position Sizing Specification
* **戦略（Strategy: 部品の組み合わせ）**:
  * `strategies/`: 特定の市場仮説に基づき、各仕様（Entry/Exit/Risk等）を有機的に組み合わせた、名前とバージョンを持つ売買ルール一式

「このシステムでは具体的にどうするか」を定義する。

---

### 03_KNOWLEDGE

仮説、分析、実験、証拠、結論など、プロジェクト活動によって得られた知識を蓄積する。

```text
03_KNOWLEDGE/
├── experiments/      # Issue番号に基づく自己完結した実験記録 (<N>-<slug>/)
└── knowledge/        # 検証・合意を経て体系化された知識 (K-xxx)
```

検証前の仮説（Analysis Issue にて事前登録）と、検証済みの知識（Knowledge）を明確に区別する。

---

### 04_IMPLEMENTATION

仕様を実際のシステム、コード、Agent、開発環境へ変換するための情報を扱う。

例：

* System Architecture
* Development Environment
* Development Workflow
* Agent Rules

Implementation は Specification の具体化であり、独自の仕様を勝手に上位概念へ昇格させない。

---

### 05_OPERATIONS

バックテストの定例実行、実運用、監視、デプロイ、障害対応など、システムを実際に動かすための情報を扱う。

---

### 90_LEGACY

現行ドキュメント体系（`00`〜`05`, `99`）導入前の過去資産（スクリプト、旧ナレッジ、レポート、モデル等）を保管する。

* **位置付け**: 過去検討のノウハウ・解析の実例として参照する資料（Read-only）。
* 現行の仕様・知識とは見なさず、直接の編集は行わない。
* 内容を現行体系へ取り込む場合は Issue を起票して移植・参照する。

---

### 99_HISTORY

過去の意思決定（ADR: Architecture Decision Records）、設計変更、廃止された仕様などを記録する。

現在の仕様だけでは説明できない、

> 「なぜ現在こうなっているのか」

を追跡するために使用する。

---

## 3. Document Relationships

文書間の関係は、**「静的な参照（依存）関係」** と **「動的な知識獲得と昇格のサイクル」** の2つの視点から整理する。

### 3.1 静的な参照（依存）関係

上位の文書が「方針・意図」を定義し、下位の文書がそれを「具体化」する。原則として下位文書が上位文書を参照する。

```text
Vision (00)
  ↓ 理念・目的の具体化
Principles (00)
  ↓ 設計原則の具体化
Concepts (01)
  ↓ 相場モデルの仕様化
Specifications (02) [部品: 評価仕様, 特徴量, サポレジ...]
  ↓ 部品の有機的組み合わせ
Strategies (02/strategies) [売買ルール一式]
  ↓ システム化
Implementation (04)
  ↓ 運用化
Operations (05)
```

同じ情報を複数の文書にコピーして保持するのではなく、単一の情報源（SSOT）を参照する。

### 3.2 動的な知識獲得と昇格のサイクル（Knowledge & Validation Loop）

仮説検証によって得られた知識は、上位の仕様や戦略へと昇格・フィードバックされる。

```text
Concepts (01)
  │ (相場モデルからの着想)
  ↓
Hypothesis (Analysis Issue / 03)
  │ (検証可能な形に定式化・事前登録)
  ↓
Experiment (03/experiments/<N>-<slug>/)
  │ (スクリプト実行・定量評価)
  ↓
Evidence (metrics.json, artifacts)
  │ (評価仕様に照らし合わせ)
  ↓
Knowledge (03/knowledge/K-xxx)
  │
  ├─ [Supported] ──→ Specification (02) または Strategy (02/strategies) に反映・昇格
  │                       │
  │                       ↓
  │                  Implementation (04) → Operations (05)
  │                       │ (実運用・監視からの結果)
  │                       ↓
  └─ [Refuted / Update] ─→ Knowledge 蓄積・仮説再設計 (フィードバック)
```

---

## 4. Concept / Specification / Strategy / Knowledge の区別

### Concept（相場概念・モデル）

「何をどう理解するか」

* 特定の実装コードや固定パラメータに依存しない普遍的な相場認識の枠組み。
* 例: 「市場は複数の時間軸から観測する必要がある」「ボラティリティは収縮と拡散を繰り返す」

### Specification（システム仕様: 部品）

「このシステムでは具体的にどう判定・処理するか」

* 個別のパラメータ、計算式、データ期間、評価基準などの具体的な定義。
* 例: 「Discovery 期間は 2020-2023 年とする」「標準摩擦コストは往復 0.4% を控除する」

### Strategy（戦略: 部品の組み合わせ）

「特定の市場仮説に基づき、各仕様を有機的に組み合わせた、名前とバージョンを持つ売買ルール一式」

* 複数の Specification（環境認識、エントリー、イグジット、リスク管理）を組み合わせた完結したトレードシステム。
* ライフサイクル（状態）:
  * `Candidate`: 仮説検証中・バックテスト評価中の候補戦略
  * `Adopted`: 評価基準を満たし、実運用・監視対象として承認された戦略
  * `Retired`: 市場環境変化等により役目を終え、廃止された旧戦略
* ※ 都度の「売買判断（Trade Decision）」や研究プロジェクトの「研究方針（Research Policy）」とは区別する。

### Hypothesis（仮説）

「検証したい問いと予想は何か」

* 事前登録された検証可能な命題（対象時間軸、発動条件、期待される効果）。
* Analysis Issue（`#N`）にて起票・事前登録される。

### Experiment（実験）

「仮説をどのように検証したか」

* 再現可能なスクリプト、設定、データ期間、パラメータ（`03_KNOWLEDGE/experiments/<N>-<slug>/`）。

### Evidence（証拠）

「実験によって何が観測されたか」

* 客観的なメトリクス（`metrics.json`）、グラフ（`artifacts/`）。

### Knowledge（知識）

「現在どこまで確認・合意できているか」

* 検証結果を客観的に総括し、証拠の強さ（Supported / Refuted / Inconclusive）と出典を明確にした知見（`03_KNOWLEDGE/knowledge/K-xxx`）。

これらを混同せず、各層の文書に適切に配置する。

---

## 5. Document Lifecycle & Approval Rules

ドキュメントは以下のライフサイクルを基本とし、GitHub の Issue / PR フローと連動して管理する。

```text
Draft (起票・作業ブランチで作成中)
  ↓
Review (PR 作成・レビュー中)
  ↓
Accepted (人間による PR マージ承認)
  ↓
Used (参照・実装・運用中)
  ↓
Deprecated (改訂・置換による廃止)
```

### 5.1 各ステータスの定義と遷移基準

| ステータス | 定義 | 遷移トリガー・担当 | 権限 |
|---|---|---|---|
| **Draft** | 作成中・編集中。仕様や前提が確定していない草案 | Issue 起票後に作業ブランチを作成し着手 | 人間 / AI Agent |
| **Review** | 完了条件を満たし、レビュー可能な状態 | PR を作成（`Review` に自動遷移） | 人間 / AI Agent |
| **Accepted** | 人間のレビューを経て正式に承認・合意された状態 | **人間オペレーターによる PR マージ** | **人間のみ** |
| **Used** | 実装コード、派生分析、実運用でアクティブに利用中 | マージ後の実稼働・参照 | システム / 人間 |
| **Deprecated** | 新しい仕様への置換や方針転換により廃止された状態 | 改訂 PR のマージ、または Decision Log 記録 | 人間 |

### 5.2 承認（合意）の記録と厳格な権限分離

* **PR マージ＝承認の記録**:
  * 人間の「合意」「承認」は口頭やチャットではなく、**GitHub Pull Request のマージ操作**をもって客観的なエビデンスとする。
  * マージコミット、PR スレッド、および関連 Issue に承認の文脈が恒久的に記録される。
* **自己承認の禁止**:
  * AI Agent は PR の作成、レビュー指摘への対応を行うが、**自ら PR をマージして自己承認してはならない**（`agent-rules.md` 準拠）。
  * 特に `00_GOVERNANCE/`、`01_CONCEPTS/`、`02_SPECIFICATIONS/` の文書は、人間が内容を精読・承認した上でマージする。

---

## 6. Versioning & Metadata Header

### 6.1 メタデータヘッダー（必須項目）

主要ドキュメント（`00`〜`05`）の先頭には、必ず以下の共通メタデータヘッダーを含める（テンプレート: [document-template.md](templates/document-template.md)）。

```markdown
**Doc ID:** [任意: 管理番号 (例: SPEC-EVAL-001)]
**Version:** 0.1.0
**Status:** Draft  <!-- Draft | Review | Accepted | Deprecated -->
**Owner:** @username
**Last Updated:** YYYY-MM-DD
**Related Issues:** [#N](https://github.com/makagi/MTF_AI_Trade/issues/N)
**Related Docs:** [関連文書名](相対パス.md)
```

### 6.2 バージョニング規律

重要な Concept、Specification、Strategy、およびデータセット・コードはセマンティックバージョニング（`Major.Minor.Patch`）に準拠して管理する。

* **Major (X.0.0)**: 上位概念の根本的刷新、破壊的仕様変更、ドキュメント体系の再構築
* **Minor (x.Y.0)**: 新しい仕様・戦略・相場概念の追加、既存仕様の後方互換な機能拡張
* **Patch (x.y.Z)**: 誤字脱字の修正、表現の明確化、リンク切れの解消

実験記録（Experiment Record）や分析コードでは、使用した各仕様のバージョン（`Specification Version`, `Data Hash` 等）を必ず記録し、将来にわたり同一条件での再現性を担保する。

---

## 7. AIによるDocument Management

AI Agent は新しい情報・知見を扱う際、以下を判断する。

1. 既存文書への追記か、新規文書の作成か
2. Concept / Specification / Strategy / Knowledge / Implementation のどれに該当するか
3. 既存の仕様や戦略への変更が必要か
4. Decision Log への記録が必要か
5. 関連する文書・コード・Experiment への影響があるか
6. 未検証の推論を確定事実として扱っていないか

AI は既存の Primary Document を確認してから新しい情報を追加し、同じ内容の重複記述を行わない。

---

## 8. Change Impact

仕様や設計の変更時には、以下の依存関係に沿って影響範囲を確認する。

```text
Vision / Principles (00)
  ↓
Concept (01)
  ↓
Specification (02)
  ↓
Strategy (02/strategies)
  ↓
Implementation (04)
  ↓
Operation (05)
```

上位文書が変更された場合、下位文書への影響を確認し、必要に応じて更新または再検証を行う。  
また、下位の実験・運用から得られた Knowledge (03) が上位の Specification や Strategy を更新する契機となる。

---

## 9. Repository Structure

本アーキテクチャに基づくリポジトリ構成は以下の通りである。

```text
MTF_AI_Trade/
├── 00_GOVERNANCE/              # ガバナンス・原則・規約
│   ├── templates/              # 文書テンプレート (document-template.md)
│   ├── vision.md
│   ├── principles.md
│   ├── documentation-architecture.md
│   ├── issue-driven-workflow.md
│   └── assumptions.md
├── 01_CONCEPTS/                # 相場認識・概念モデル（MTF, Regime, Volatility...）
├── 02_SPECIFICATIONS/          # システム仕様・戦略
│   ├── evaluation.md           # 評価仕様（コストモデル、期間分割、判定基準）
│   └── strategies/             # 個別戦略定義（Candidate / Adopted / Retired）
├── 03_KNOWLEDGE/               # 実験記録・蓄積知識
│   ├── experiments/            # Issue連動実験記録 (<N>-<slug>/)
│   └── knowledge/              # 体系化された知識 (K-xxx)
├── 04_IMPLEMENTATION/          # 開発環境・ワークフロー・Agent規約
│   ├── agent-rules.md
│   ├── development-environment.md
│   └── development-workflow.md
├── 05_OPERATIONS/              # バックテスト運用・実運用規約
├── 90_LEGACY/                  # 過去資産アーカイブ（Read-only）
│   └── README.md
├── 99_HISTORY/                 # 意思決定ログ（ADR）
│   └── decision-log.md
├── README.md                   # リポジトリ入口・ドキュメントマップ
└── .github/                    # Issue / PR テンプレート
```

空のディレクトリについては、必要になるまで詳細なファイルを作成しない（Simplicity の原則）。

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
