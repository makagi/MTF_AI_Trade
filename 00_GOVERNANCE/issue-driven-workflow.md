# MTFシステムトレード Issue-Driven Workflow

**Doc ID:** GOV-WFL-001  
**Version:** 0.3.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-25  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4), [#11](https://github.com/makagi/MTF_AI_Trade/issues/11), [#79](https://github.com/makagi/MTF_AI_Trade/issues/79)  
**Related Docs:** [principles.md](principles.md), [documentation-architecture.md](documentation-architecture.md), [../99_HISTORY/decision-log.md](../99_HISTORY/decision-log.md), [../04_IMPLEMENTATION/agent-rules.md](../04_IMPLEMENTATION/agent-rules.md)  

---

## 1. Purpose

本ドキュメントは、本プロジェクトにおける全ての作業（ドキュメント作成・レビュー、分析・仮説検証、開発・環境構築）を **GitHub Issue 起点** で進めるための最小限のルールを定義する。

目的は、

* 作業の「なぜ（動機）」と「何をもって完了か」を作業前に明文化する
* 議論・判断・結果を Issue / PR に紐付けて追跡可能にする（Knowledge Lineage の入口）
* 人間と AI Agent が同じ単位（Issue）で作業を受け渡せるようにする

ことである。

> [!NOTE]
> 本ルール自体も Issue 駆動で改善する（Simplicity 原則に従い、運用で必要性が確認されたものから詳細化する）。

---

## 2. Basic Rule

1. **Issue なしで作業を始めない。** 軽微な誤字修正を除き、全ての変更は Issue に紐付ける。
2. **1 Issue = 1 つの完了条件。** 完了条件を 1 文で書けない Issue は分割する。
3. **1 PR は原則 1 Issue を閉じる。** PR 本文に `Closes #<番号>` を書く。
4. **議論と判断は Issue に残す。** チャットや口頭で決めた内容も、要点を Issue コメントに記録する。
5. **重要な判断は Decision Log へ昇格する。** Issue 内の判断のうち、方針・仕様・評価基準に関わるものは [decision-log.md](../99_HISTORY/decision-log.md) に Issue 番号付きで記録する。

---

## 3. Issue Types

Issue は以下の 3 種類のいずれかとして起票する（`.github/ISSUE_TEMPLATE/` のテンプレートを使用する）。

| Type | ラベル | 用途 | 主な成果物 |
|---|---|---|---|
| Document | `type:docs` | ドキュメントの新規作成・レビュー・改訂 | `00`〜`05`, `99` 配下の文書 |
| Analysis | `type:analysis` | 仮説の検証、データ分析、バックテスト | 仮説・実験記録、Evidence、結論 |
| Development | `type:dev` | コード、ツール、開発環境、CI | `src/`, `tools/`, 設定ファイル |

判断が必要で作業が止まる場合は `status:needs-decision` を付け、人間の判断を仰ぐ。

---

## 4. Labels

ラベルは「種類」「対象領域」「状態」の 3 系統に限定する。

| 系統 | ラベル | 意味 |
|---|---|---|
| 種類 | `type:docs` / `type:analysis` / `type:dev` | Issue Type（必須・1つ） |
| 領域 | `area:governance` / `area:concepts` / `area:specs` / `area:knowledge` / `area:implementation` / `area:operations` / `area:legacy` | 影響する文書層（任意・複数可） |
| 状態 | `status:needs-decision` | 人間の判断待ち |
| 状態 | `status:blocked` | 他 Issue 等の完了待ち（本文に依存先を記載） |

---

## 5. Lifecycle

```text
Open (起票: 背景・目的・完了条件を記載)
  ↓
In Progress (担当者アサイン、作業ブランチ作成)
  ↓
Review (PR 作成、Closes #N)
  ↓
Done (PR マージで自動 Close)
```

* 作業途中で発見した別の問題は、その場で直さず **新しい Issue として起票** し、元 Issue からリンクする。
* 完了条件を満たさずに打ち切る場合は、理由をコメントして `not planned` で Close する（失敗・中止も知識として残す: principles 1.3）。

---

## 6. Branch / Commit / PR Conventions

### 6.1 Branch

```text
<type>/<issue番号>-<短い説明>
例: docs/12-unify-layer-hierarchy
    analysis/20-htf-squeeze-breakout
    dev/7-setup-uv-env
```

### 6.2 Commit Message

```text
<type>(<scope>): <要約> (#<issue番号>)
例: docs(governance): 文書層の上下関係を統一 (#12)
```

`type` は `docs` / `analysis` / `dev` / `chore` のいずれか。

### 6.3 Pull Request

* `.github/pull_request_template.md` に従い、変更内容・影響範囲・確認事項を記載する。
* `main` への直接 push は行わない（初期ブートストラップを除く）。
* マージは人間がレビューした上で行う。

---

## 7. Missed Opportunity Review (MOR)

Analysis 実験の完了時（PR 作成前）に、シグナルが出なかったのに大きく動いた場面（見逃しエントリー：M1）と対照群（C1/C2）のチャートを提示し、人間の視点を仮説生成の入力として取り込むレビュー工程を実施する。

### 7.1 目的
バックテスト数値だけの過剰適合を抑止し、チャート上の文脈や見落としパターンを抽出して次期事前登録仮説のシードとする（`principles.md` 10.2）。

### 7.2 手順
1. `tools/missed_opportunity_review.py` を実行し、ブラインド画像（Stage A）と結末画像（Stage B）を生成する。
2. Stage A（判断時点 $t$ 以前のみ描画）を提示し、レビュアーの判断（`long` / `skip` / `unsure`）と根拠を記録する。
3. Stage B（結末と真の分類）を開示し、所見を収集する。
4. 正答率および仮説候補を `review/observations.yaml` に記録する。

### 7.3 バイアス対策
- **Holdout ガード**: Discovery 期間（`< 2025-05-01`）のみから抽出する。
- **2段階ブラインド**: Stage A 回答完了まで結末や正解ラベルを伏せる。
- **対照群混在**: 見逃し5件に対し、類似不発例（C1）や負けトレード（C2）計5件をシャッフル混在させる。
- **仮説と知見の厳格分離**: レビュアーの所見は仮説候補に留め、単独で知見（K-xxx）に登録してはならない。必ず事前登録と検証を経る。

### 7.4 記録先
各実験ディレクトリの `03_KNOWLEDGE/experiments/<N>-<slug>/review/observations.yaml` に保存する。

---

## 8. Definition of Done

| Type | 完了条件 |
|---|---|
| 共通 | Issue の完了条件を満たす / 関連文書のリンク切れがない / 新たに見つかった課題は別 Issue 化済み |
| Document | 文書の配置が [documentation-architecture.md](documentation-architecture.md) に従っている / 重複定義を作っていない（SSOT） |
| Analysis | 事前に定めた評価基準で判定済み / 再現情報（データ期間・コード・パラメータ）を記録 / 支持・棄却に関わらず結論を記録 / MOR を実施し `observations.yaml` を記録済み（ユーザーが明示的にスキップした場合は理由を記録） |
| Development | 実行手順が記載されている / 既存の分析・ツールを壊していない |

---

## 9. AI Agent の参加ルール

1. AI Agent への作業依頼は **Issue 番号を指定** して行う。
2. AI Agent は Issue の範囲外の変更を行わない。範囲外の問題を見つけた場合は Issue 起票を提案する。
3. AI Agent は作業結果の要約（何をしたか・何を判断したか・未解決事項）を Issue または PR にコメントする。
4. 人間の判断が必要な論点は `status:needs-decision` を付け、選択肢と推奨案を提示する。
5. AI Agent の行動規範の詳細は [agent-rules.md](../04_IMPLEMENTATION/agent-rules.md) に従う。

---

## 10. Legacy Assets

[90_LEGACY/](../90_LEGACY/README.md) の旧資産は参照専用とする。

* 旧資産のノウハウ・分析例を現行体系に取り込む場合は、Issue を起票し、取り込み先の文書から旧資産のパスを出典として参照する。
* 旧資産そのものは編集しない。

---

## 11. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-09 | 0.1.0 | 初版作成（Issue駆動ワークフロー、ラベル体系、PRルール策定） | @makagi / [#16](https://github.com/makagi/MTF_AI_Trade/pull/16) |
| 2026-10-13 | 0.2.0 | 書式・メタデータヘッダー規約統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
| 2026-10-25 | 0.3.0 | Missed Opportunity Review (MOR) 節の新設、Analysis DoD に MOR 実施条件を追加 | @makagi / [#80](https://github.com/makagi/MTF_AI_Trade/pull/80) |

