# MTFシステムトレード Development Workflow

**Doc ID:** DEV-WFL-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-12  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4), [#13](https://github.com/makagi/MTF_AI_Trade/issues/13)  
**Related Docs:** [00_GOVERNANCE/issue-driven-workflow.md](../00_GOVERNANCE/issue-driven-workflow.md), [agent-rules.md](agent-rules.md), [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md)  

## 1. Purpose

本ドキュメントは、人間とAIエージェントが協調して「仮説立案・検証・知識蓄積・実装」のサイクルを継続的かつ再現可能に回すための標準開発ワークフローを定義する。

---

## 2. Collaborative Lifecycle (3層協調ライフサイクル)

本プロジェクトの開発・実験サイクルは、以下の3層アーキテクチャおよび人間ゲート（Human Gate）に従って進行する。

```text
📱 ユーザー（スマホ / 人間）
     ↓ 1. アイデア・改善要求の提示
【第1層: 要求・仕様策定層】
   Antigravity (Requirements Agent)
     │ 2. コード・仕様・知見の事前調査 & 要求構造化
     ↓ 3. Issue 起票・更新判断（判定基準の事前登録）
【第2層: 状態・信頼の唯一の情報源 (SSOT)】
   GitHub Issues (#N)
     ↓ 4. タスク検知・作業指示
【第3層: 自律開発・実験管制層】
   Orca (Orchestrator)
     │ 5. トピックブランチ作成・タスク分解
     ↓ 6. 指示・呼び出し
   マルチエージェント群（Antigravity / Codex / Open Claw / ローカルLLM）
     │ 7. 自己完結実験（tools/kb.py new #N <slug>）& 実装（src/）
     │ 8. SPEC-EVAL-001 準拠の定量検証（metrics.json）
     │ 9. 実験総括（record.md）& PR 作成
     ↓
【Human Gate (承認ゲート)】
   ユーザー（人間オペレーター）
     │ 10. PR レビュー & 承認マージ
     ↓
【反映・記録】
   main ブランチ反映、知識系譜図（knowledge-lineage.md）、意思決定ログ（decision-log.md）
```

---

## 3. AI Agent Roles & Responsibilities

エージェント群は [agent-rules.md](agent-rules.md) の権限境界に基づき、以下の通り役割を分担する。

| レイヤー / 役割 | 担当主体 (例) | 主な責務 (Responsibilities) | 主な入力・参照 | 主な出力・成果物 |
|---|---|---|---|---|
| **Requirements Agent** | Antigravity | 人間の曖昧な要求を受け取り、コード・仕様・知見を調査し、判定基準付きのIssueを起票 | 人間の入力, `00`〜`04`, 既存Issue/PR | GitHub Issue（事前登録基準付き） |
| **Orchestrator** | Orca | GitHub Issueをトリガーとして開発ブランチ作成、作業分割、ワーカーエージェントの管制 | GitHub Issue, リポジトリ状態 | トピックブランチ, エージェント指示 |
| **Research Worker** | Antigravity, ローカルLLM 等 | 既存知見の調査、先行分析の探索、概念整理 | `01_CONCEPTS/`, `03_KNOWLEDGE/` | 調査サマリ、論点整理 |
| **Coding / Experiment Worker** | Antigravity, Codex, Open Claw 等 | 実験スクリプト・データ処理・特徴量計算の実装と実行 | `02_SPECIFICATIONS/`, `src/` | `03_KNOWLEDGE/experiments/<N>-<slug>/`, `src/` |
| **Validation Worker** | 各種Agent | リーク監視、摩擦コスト（0.40%）控除後評価、年別・レジーム別検証 | `SPEC-EVAL-001`, `src/evaluation.py` | `metrics.json`, `artifacts/` |
| **Knowledge Worker** | Antigravity 等 | 実験レコードの総括、系譜図・インデックスの更新 | `record.md`, 実験結果 | `03_KNOWLEDGE/knowledge-lineage.md` |

---

## 4. Step-by-Step Procedure

### Step 1: 要求・アイデアの提示 (Idea & Request)
- 人間がスマートフォンやチャットから問題意識・改善アイデアを提示する。
  - 例:「4H足のSR帯とATRを組み合わせて、ライン反発の許容幅を動的化したい」

### Step 2: リポジトリ調査 & 要求構造化 (Requirements Analysis)
- **Requirements Agent (Antigravity)** がコードベース・仕様・ナレッジベースを調査する：
  1. 現行ロジックの実装状況（`src/`）
  2. 関連する概念・仕様（`01_CONCEPTS/`, `02_SPECIFICATIONS/`）
  3. 過去の類似実験（`tools/kb.py list`, `03_KNOWLEDGE/knowledge-lineage.md`）
- 既存Issueの有無や調査専用タスク（`type:analysis`）の要否を判断する。

### Step 3: Issue 起票と判定基準の事前登録 (Pre-registration)
- Requirements Agent が GitHub Issue を作成する。
- **Analysis Issue** の場合、[02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) に準拠した客観的合否判定基準（往復0.40%コスト控除後期待値、Discovery期間限定等）を本文に事前登録する。
- 事前登録を経ない実験実行はチェリーピッキング防止のため禁止する。

### Step 4: 実験・実装の開始 (Orchestration & Experiment Setup)
- **Orchestrator (Orca)** が Issue を検知し、作業ブランチ（例: `analysis/<N>-<slug>`）を作成する。
- 実験の場合、CLI ツールを用いて自己完結ディレクトリを生成する：
  ```powershell
  uv run python tools/kb.py new <issue_no> <slug> --title "Experiment Title"
  ```
- ワーカーエージェント（Antigravity, Codex, Open Claw, ローカルLLM等）が `run.py` や `config.yaml` を実装する。

### Step 5: 定量検証 & エビデンス判定 (Validation)
- [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md)（SPEC-EVAL-001）に基づき実行・検証する：
  1. **Holdout遮断**: `src.data_loader` を用い、Discovery 期間（2020年〜2025年4月）のみで評価。
  2. **摩擦コスト控除**: `src.evaluation` により標準摩擦コスト（往復0.40%）控除後期待値を算出。
  3. **非定常性の検証**: 年別・レジーム別で結果が一貫しているか。
  4. **エントリーとイグジットの分離**: MFE/MAE 分布による初動エッジの確認。

### Step 6: 決定論的ゲート検証 & 実験記録総括 (Gates & PR)
- 実験ディレクトリ内の `record.md` に事前登録基準、実行結果、考察、および結論（Supported / Refuted / Inconclusive）を記録する。
- ワーカーエージェントは PR 作成前に必ず決定論的ゲート（`uv run python tools/agent_eval.py check 03_KNOWLEDGE/experiments/<N>-<slug>`）を実行し、全ゲート（構文・整合性・定量契約）の通過を確認する（指示テンプレート: [`prompts/task-templates.md`](prompts/task-templates.md)）。
- ワーカーエージェントが GitHub Pull Request（`Closes #<N>`）を作成する。

### Step 7: 人間レビュー & 意思決定 (Human Gate & Merge)
- 人間オペレーターが PR 本文、CI テスト結果（Canary Benchmark）、評価メトリクスを確認する。
- 人間が「マージ（承認）」を実行することで、成果物が正式に確定する（AIによる自己マージは厳禁）。
- 必要に応じて `02_SPECIFICATIONS/` や `99_HISTORY/decision-log.md` に反映する。


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

---

## 6. Continuous Flywheel (反復改善フライホイール)

本ワークフローは一方向の完了モデルではなく、`00_GOVERNANCE/principles.md` §10 に基づく反復改善ループとして運用される。

1. **特徴量理解の深化から戦略昇格へ (M3 $\rightarrow$ M4)**:
   - 単発で戦略を作るのではなく、市場レジームごとの特徴量（SR、ATR、ボラティリティ等）の振る舞いを `K-xxx` として蓄積し、十分な定量的裏付けが確立された段階で複合戦略へと昇格させる。
2. **実践を通じたエージェント基盤の洗練 (M3 $\rightarrow$ M2)**:
   - ワーカーエージェントの出力ミスや例外は、即座に「Canary Benchmark（事前テスト）」へ追加され、モデル選定・自動乗り換えの精度向上に還元される。
3. **ルールの自己進化 (M3/M4 $\rightarrow$ M1)**:
   - 実験や実運用の過程で生じたドキュメントの解釈揺れ・例外は、Issue 駆動でガバナンス・評価仕様へと恒久的にフィードバックされる。

---

## 7. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-10 | 0.1.0 | 初版作成（開発ワークフロー、ライフサイクル定義） | @makagi / [#21](https://github.com/makagi/MTF_AI_Trade/pull/21) |
| 2026-10-12 | 0.2.0 | 3層協調ライフサイクル、役割分担、反復改善フライホイール確立 | @makagi / [#22](https://github.com/makagi/MTF_AI_Trade/pull/22) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |

