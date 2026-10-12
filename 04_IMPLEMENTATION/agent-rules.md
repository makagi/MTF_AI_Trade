# AIエージェント行動規範・権限境界 (Agent Rules)

**Doc ID:** RULE-AGT-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-12  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4), [#13](https://github.com/makagi/MTF_AI_Trade/issues/13)  
**Related Docs:** [00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md), [00_GOVERNANCE/issue-driven-workflow.md](../00_GOVERNANCE/issue-driven-workflow.md), [development-workflow.md](development-workflow.md), [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md)  

---

## 1. 目的と位置付け (Purpose & SSOT)

本ドキュメントは、本プロジェクトにおいて人間およびAIエージェント群が協調して開発・分析を進める際の**行動規範および権限境界の単一情報源（SSOT）**である。

AIエージェントの自律性を最大限活用しつつ、プロジェクトの健全性、科学的厳密性、およびコードベースの安全性を保つため、エージェントごとに明確な権限境界を定める。

---

## 2. 3層協調アーキテクチャと権限境界 (Architecture & Permissions)

システム全体は以下の3層構造および人間ゲート（Human Gate）によって統制される。

```text
📱 ユーザー（スマホ / 人間）
   │
   ▼
【第1層: 要求・仕様策定層】
   Antigravity (Requirements Agent)
   │  ・コードベース・仕様・知見の調査
   │  ・要求の構造化 & Issue作成（または更新 / 見送り判断）
   │  ・権限: Read（コード/知見） + Create/Update Issue に限定
   ▼
【第2層: 状態・信頼の唯一の情報源 (SSOT)】
   GitHub Issues / Pull Requests / Actions
   │  ・Issue: バックログ & 作業指示書
   │  ・PR / Actions: 変更差分 & CIテスト & 定量評価
   ▼
【第3層: 自律開発・実験管制層】
   Orca (Orchestrator) ＆ マルチエージェント群
   │  ・Orca: Issue検知・トピックブランチ作成・タスク分解
   │  ・ワーカーエージェント: Antigravity, Codex, Open Claw, ローカルLLM (LM Studio / Lemonade) 等
   │  ・実行: tools/kb.py による実験、src/ 実装、SPEC-EVAL-001 準拠評価
   │  ・成果物: Pull Request の作成
   ▼
【Human Gate (承認ゲート)】
   ユーザー（人間オペレーター）
      ・PRレビュー & マージ（仕様合意・本番反映の唯一の権限）
```

### 2.1 主体別の権限マトリクス

| 主体 | 主な役割 | 許可される権限 | 禁止される権限 |
|---|---|---|---|
| **ユーザー (人間)** | 意思決定・最終承認 | 全権限（Issue起票・裁定・PRマージ・リポジトリ設定） | - |
| **Requirements Agent**<br>(Antigravity) | 要求分析・Issue化 | リポジトリ読取、既存Issue/PR読取、Issue起票・コメント・ラベル更新 | コード直接コミット、PR作成、PRマージ、リポジトリ設定変更 |
| **Orchestrator**<br>(Orca) | 開発管制・タスク配分 | Issue読取・更新、作業ブランチ作成、ワーカーエージェントへの指示呼び出し | `main` ブランチへの直接push、PRの自己承認・自己マージ |
| **Coding / Experiment Agents**<br>(Antigravity, Codex, Open Claw, ローカルLLM等) | 実装・実験・評価 | トピックブランチ内でのファイル編集、スクリプト実行、PR作成 | `main` ブランチへのpush、Holdout期間データへのアクセス、PRマージ |

---

## 3. 禁止事項 (Strictly Prohibited)

1. **自己承認による PR マージの禁止 (No Self-Approval / No Auto-Merge)**:
   - いかなる AI エージェントも、自身や他のエージェントが作成した PR を自律的にマージしてはならない。PR のマージ（仕様合意）権限は人間オペレーターのみが保持する。
2. **仕様・原則の無断変更禁止 (No Unilateral Spec Changes)**:
   - `00_GOVERNANCE/`、`01_CONCEPTS/`、`02_SPECIFICATIONS/` の内容を、対応する Issue および人間の PR マージなしに変更してはならない。
3. **最終ホールドアウト期間へのアクセス禁止 (No Holdout Leakage)**:
   - [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) §2 で定義する Final Holdout 期間（2025年1月1日以降）のデータは、いかなる探索・学習・中間評価でもアクセスしてはならない（`src/data_loader.py` のアクセス制御をバイパスする行為も禁止）。
4. **未検証アイデアの「確定事実化」禁止**:
   - バックテストや統計検定を経ていないアイデアを「エッジがある」「有効である」と断定してドキュメントやコードに組み込んではならない。必ず「仮説（Hypothesis）」として扱うこと。
5. **チェリーピッキング・都合の良い結果のみの報告禁止**:
   - 特定の年や相場でのみ勝てた結果を誇張し、トータルで負けている結果やドローダウンを隠蔽してはならない。事前登録した判定基準（Analysis Issue）に忠実に評価すること。
6. **破壊的・範囲外の変更禁止**:
   - 指定された Issue の責務・完了条件を超えるリファクタリングや、不要な依存関係の追加を行ってはならない。

---

## 4. 必須行動 (Mandatory Actions)

1. **Issue 起点の行動**:
   - すべての変更は対応する Issue 番号を明確にし、PR 本文に `Closes #<番号>` を記載する。
2. **変更理由と系譜の記録**:
   - コードや特徴量の計算ロジックを変更する際は、必ず「どの仮説・実験・決定に基づく変更か」をコミットメッセージや PR に明記する。
3. **定量的根拠の提示 (SPEC-EVAL-001 準拠)**:
   - 改善や戦略の優位性を主張する場合、必ず [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) §4 で規定する必須評価メトリクス（サンプル数、摩擦コスト0.40%控除後期待値、年別・レジーム別分解、MFE/MAE、Max DD）を提示すること。
4. **再現性の担保**:
   - 実行したスクリプト名、引数、シード値、データ期間、出力ログを記録し、他のエージェントや人間が `uv run ...` で同一結果を再現できるようにする。
5. **判断保留時のエスカレーション**:
   - 設計方針のトレードオフや不確実な判断が生じた場合は、独断で進めず `status:needs-decision` を付与して人間に選択肢と推奨案を提示する。

