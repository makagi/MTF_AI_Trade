# MTF_AI_Trade

Multi-Time-Frame（MTF）による市場認識を中心に、相場分析・仮説・検証・戦略・実装・運用を一貫して扱うシステムトレード基盤。

> [!IMPORTANT]
> 本プロジェクトは **Issue 駆動** で進める。作業を始める前に Issue を起票すること（[issue-driven-workflow.md](00_GOVERNANCE/issue-driven-workflow.md)）。

## ドキュメントマップ

| ディレクトリ | 役割 | 入口 |
|---|---|---|
| `00_GOVERNANCE/` | 目的・原則・文書体系・運用ルール | [vision.md](00_GOVERNANCE/vision.md), [principles.md](00_GOVERNANCE/principles.md), [documentation-architecture.md](00_GOVERNANCE/documentation-architecture.md) |
| `01_CONCEPTS/` | 市場理解のための概念モデル | [mtf-framework.md](01_CONCEPTS/mtf-framework.md), [glossary.md](01_CONCEPTS/glossary.md) |
| `02_SPECIFICATIONS/` | システム仕様・戦略 | [evaluation.md](02_SPECIFICATIONS/evaluation.md) |
| `03_KNOWLEDGE/` | 仮説・実験・知識の系譜 | [README.md](03_KNOWLEDGE/README.md), [knowledge-lineage.md](03_KNOWLEDGE/knowledge-lineage.md) |
| `04_IMPLEMENTATION/` | 開発環境・ワークフロー・Agent 規約 | [development-workflow.md](04_IMPLEMENTATION/development-workflow.md), [agent-rules.md](04_IMPLEMENTATION/agent-rules.md) |
| `05_OPERATIONS/` | 運用（未着手） | — |
| `90_LEGACY/` | 旧資産（参照専用） | [README.md](90_LEGACY/README.md) |
| `99_HISTORY/` | 意思決定ログ | [decision-log.md](99_HISTORY/decision-log.md) |

## 作業の始め方

1. [Issues](https://github.com/makagi/MTF_AI_Trade/issues) で既存 Issue を確認する。
2. なければテンプレート（Document / Analysis / Development）から起票する。
3. `<type>/<issue番号>-<説明>` ブランチで作業し、`Closes #<番号>` を付けた PR を出す。
