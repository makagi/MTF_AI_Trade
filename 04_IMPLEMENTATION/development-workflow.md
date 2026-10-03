# MTFシステムトレード Development Workflow

**Version:** 0.1
**Status:** Draft

## 1. Purpose

本ドキュメントは、人間とAIエージェントが協調して「仮説立案・検証・知識蓄積・実装」のサイクルを継続的かつ再現可能に回すための標準開発ワークフローを定義する。

---

## 2. Collaborative Lifecycle

```text
[Human / AI]
     ↓ 1. Idea / Issue
[Research Agent]
     ↓ 2. Context & Concept Mapping
[Hypothesis Agent]
     ↓ 3. Hypothesis Formulation (03_KNOWLEDGE/hypotheses/)
[Coding / Experiment Agent]
     ↓ 4. Script & Experiment Execution (knowledge/records/ or src/)
[Validation Agent]
     ↓ 5. Evidence & Cost-Adjusted Evaluation (MFE/MAE, Walk-Forward)
[Knowledge Agent]
     ↓ 6. Knowledge Lineage & Record Update (LINEAGE.md, index.json)
[Human Operator]
     ↓ 7. Review & Decision
[Implementation / Spec]
     ↓ 8. Specification & Decision Log Update (02_SPEC, 99_HISTORY)
```

---

## 3. AI Agent Roles & Responsibilities

`00_GOVERNANCE/principles.md` 第6章に基づき、AIエージェントの役割と責務を以下のように分担する。

| 役割 (Agent Role) | 責務 (Responsibilities) | 主な入力・参照 | 出力・編集先 |
|---|---|---|---|
| **Research Agent** | 既存知見の調査、先行分析の探索、相場観の概念整理 | `00_GOVERNANCE/`, `01_CONCEPTS/`, `03_KNOWLEDGE/` | 調査サマリ、論点整理 |
| **Hypothesis Agent** | アイデアを検証可能な仮説（HXXX）へ定式化 | `01_CONCEPTS/`, `03_KNOWLEDGE/` | `03_KNOWLEDGE/hypotheses/` |
| **Coding / Experiment Agent** | 実験スクリプトの実装、データ処理、シミュレーション実行 | `02_SPECIFICATIONS/`, `src/` | `src/`, `knowledge/records/` |
| **Validation Agent** | リーク監視、摩擦コスト控除後評価、年別・レジーム別頑健性検証 | `00_GOVERNANCE/principles.md`, 実験結果 | `reports/`, `metrics.json` |
| **Knowledge Agent** | 分析レコードの整合性検証、系譜図・インデックスの更新 | 実験結果・エビデンス | `03_KNOWLEDGE/`, `knowledge/` |

---

## 4. Step-by-Step Procedure

### Step 1: アイデア・課題の提示 (Idea / Issue)
- 人間が市場観察や直感から得た問題意識を提示する。
- 例:「長期上位足のボラティリティが圧縮している局面で、下位足のブレイク初動に乗るエッジはあるか？」

### Step 2: 既存知識の確認 & 概念マッピング (Research & Concept)
- AIは新規に手を動かす前に、既存のドキュメントおよびナレッジベースを確認する：
  1. `01_CONCEPTS/` に関連する相場モデルがあるか？
  2. 過去に同一・類似の実験が行われていないか？（`tools/kb.py list` や `knowledge-lineage.md` の確認）
- 過去の失敗や棄却された仮説と重複する場合、その旨を報告し無駄な再実験を防ぐ。

### Step 3: 仮説の定式化 (Hypothesis Formulation)
- アイデアを「事実・解釈・仮説」に分離し、検証可能な形にする。
- 対象時間軸、使用指標、前提レジーム、期待される効果を明確化する。

### Step 4: 実験の実装と実行 (Experiment Execution)
- 探索的分析の場合: `python tools/kb.py new` を使用し、独立した自己完結ディレクトリ（`knowledge/records/YYYY-MM/ANL-...`）を作成して実行する。
- 共通機能の追加の場合: `src/` 配下のモジュールを更新し、テストを作成する。
- **データ規律**: 探索・学習には 2020-2023年 のみを使用する。

### Step 5: 定量検証 & エビデンス判定 (Validation)
- 以下の規律に則り結果を評価する：
  1. **摩擦コスト控除**: 往復0.4%相当の現実的コストを差し引いても期待値プラスか。
  2. **非定常性の検証**: 年別・レジーム別で結果が一貫しているか（特定年のみの勝ちではないか）。
  3. **エントリーとイグジットの分離**: MFE/MAE分布によりエントリー自体のエッジを確認したか。

### Step 6: 知識の系譜（Knowledge Lineage）の更新
- 実験結果に基づき、客観的事実（FIND）と検証結果を記録：
  - 支持された場合（Supported）: エビデンスとともに知識へ昇格。
  - 反証された場合（Refuted）: 棄却理由・数学的根拠を記録。
- `python tools/kb.py index` および `python tools/kb.py validate` を実行してカタログを最新化する。

### Step 7: 人間レビュー & 意思決定 (Decision)
- 人間オペレーターがレポートを確認し、本番採用・再実験・棄却を判断する。
- 仕様への反映が必要な場合は `02_SPECIFICATIONS/` を更新し、`99_HISTORY/decision-log.md`（ADR）に採択理由を記録する。

---

## 5. AIによるドキュメント更新判断ルール

AIエージェントが作業を行う際は、常に以下の判断基準に従う（`documentation-architecture.md` 準拠）：

1. **情報の分類先**:
   - 相場の捉え方・普遍的な理解 → `01_CONCEPTS/`
   - 具体的な定数・計算式・売買ルール → `02_SPECIFICATIONS/`
   - 実験結果・エビデンス・仮説 → `03_KNOWLEDGE/`
   - 実装コード・開発環境・Agent規約 → `04_IMPLEMENTATION/`
   - 意思決定理由・変更理由 → `99_HISTORY/`
2. **単一情報源（Single Source of Truth）の維持**:
   - 同じ定義を複数ファイルに重複して書かない。必ず上位文書を参照（リンク）する。
3. **未検証仮説の確定事実化の禁止**:
   - 検証前の推論を仕様（Specification）や確定知識（Knowledge）として記述してはならない。
