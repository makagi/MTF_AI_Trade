# 90_LEGACY — 旧資産アーカイブ

**Doc ID:** LEG-ARCH-001  
**Version:** 0.2.0  
**Status:** Accepted (Read-only Archive)  
**Owner:** @makagi  
**Last Updated:** 2026-10-13  
**Related Issues:** [#15](https://github.com/makagi/MTF_AI_Trade/issues/15)  
**Related Docs:** [../00_GOVERNANCE/documentation-architecture.md](../00_GOVERNANCE/documentation-architecture.md), [../00_GOVERNANCE/issue-driven-workflow.md](../00_GOVERNANCE/issue-driven-workflow.md), [../README.md](../README.md)  

---

本ディレクトリは、現行ドキュメント体系（`00`〜`05`, `99`）を導入する以前の検討資産を保管する。

* **位置付け**: 過去検討のノウハウ・解析の実例として参照する資料。現行の仕様・知識ではない。
* **99_HISTORY との違い**: `99_HISTORY` は現行体系における意思決定・変更の履歴。`90_LEGACY` は現行体系の外にある過去資産そのもの。
* **編集禁止**: 旧資産は原則として編集しない。内容を現行体系へ取り込む場合は Issue を起票し、取り込み先の文書から本ディレクトリのパスを出典として参照する（[issue-driven-workflow.md](../00_GOVERNANCE/issue-driven-workflow.md) §9）。
* **記述の信頼度**: 旧資産内の「証明済み」「確定」等の表現は当時の判断であり、現行の評価基準で再確認されたものではない。

---

## 主な内容

| パス | 内容 |
|---|---|
| `CONSTITUTION.md` | 旧プロジェクト憲章（研究規律など） |
| `STATE.md` | 旧フェーズ進捗・主要発見のまとめ |
| `task.md` | 旧タスクリスト |
| `knowledge/` | 旧ナレッジベース（Analysis Record `ANL-*`、`FIND-*`、`HYP-*`、`LINEAGE.md`、`PROMPTS.md`、`DICTIONARY.md`） |
| `tools/` | 旧ナレッジ CLI（`kb.py` 等）。`knowledge/` との相対位置を保持しているため `90_LEGACY/` 配下でそのまま実行可能 |
| `src/` | 旧共通コード（データローダ、特徴量、評価、モデル等） |
| `reports/`, `results/`, `models/` | 旧検証レポート、出力画像、学習済みモデル |
| `agent-skills/trade-knowledge/` | 旧ナレッジベース用 Agent Skill（自動読み込みを避けるため `.agent/` から退避） |
| ルート直下の `*.py`, `*.png`, `*.csv`, `*.txt` | 旧ルート直下に置かれていた分析スクリプトと出力 |

> [!NOTE]
> 旧コードはデータパス等をリポジトリルート基準で参照している場合があり、移動により実行できないものがある。再利用する場合は Issue を起票して現行体系へ移植する。

---

## 90_LEGACY 資産棚卸し一覧 (Inventory & Triage)

Issue [#15](https://github.com/makagi/MTF_AI_Trade/issues/15) に基づき、旧資産の取り込み状況、現行体系での位置付け、および今後のアクションを以下の通り棚卸し・分類する。

### 分類区分 (Triage Category)
* **【完了】**: 既に現行文書体系（`00`〜`04`、`99`）に取り込み・昇格が完了している資産。
* **【要再検証 / 移植】**: 有用なアイデア・数式・コードを含むが、現行評価基準（SPEC-EVAL-001）や新環境（uv / `src/`）での再検証・移植を要する資産（後続 Issue 対象）。
* **【アーカイブ / 取り込み不要】**: 過去の作業用一時ファイル、古いタスクリスト、旧環境専用スクリプト等、現行体系への移植が不要な資産。

---

### 1. ガバナンス・研究規律・運用知見

| 旧資産 | 旧概要 | 分類 | 取り込み先 / 現行対応 | 今後のアクション |
|---|---|---|---|---|
| `CONSTITUTION.md` | 破産防止、Walk-Forward評価、リーク厳禁、非定常性前提、Research Discipline | **【完了】** | [`00_GOVERNANCE/principles.md`](../00_GOVERNANCE/principles.md) (Risk First / Evidence Chain), [`02_SPECIFICATIONS/evaluation.md`](../02_SPECIFICATIONS/evaluation.md) | 取り込み完了。恒久参照元として保持。 |
| `task.md` | 旧チェックリスト型タスク管理 | **【アーカイブ】** | [`00_GOVERNANCE/issue-driven-workflow.md`](../00_GOVERNANCE/issue-driven-workflow.md) | GitHub Issue/PR 運用へ全面移行済みのため取り込み不要。 |
| `knowledge/PROMPTS.md` | クオンツ分析用プロンプト集（System Prompt, 新規/派生/検証指示テンプレート） | **【要再検証 / 移植】** | `04_IMPLEMENTATION/` または Agent QA 基盤 | **Issue 起票対象**: Agent QA（Canary Benchmark）およびワーカーエージェント向け指示テンプレートとして現代化。 |

---

### 2. 相場発見・仮説・知識系譜

| 旧資産 | 旧概要 | 分類 | 取り込み先 / 現行対応 | 今後のアクション |
|---|---|---|---|---|
| `STATE.md` (重要発見 1〜4) | SMA下方乖離の回帰性、トレンド傾き、押し目、MAE無差別 | **【完了】** | [`03_KNOWLEDGE/knowledge-lineage.md`](../03_KNOWLEDGE/knowledge-lineage.md) (K-001等), [`00_GOVERNANCE/assumptions.md`](../00_GOVERNANCE/assumptions.md) | K-001 として体系化済み。 |
| `STATE.md` (重要発見 5〜7) | サポレジ非定常性、1m単独トリガー無価値、MoE単独の限界 | **【完了】** | [`03_KNOWLEDGE/knowledge-lineage.md`](../03_KNOWLEDGE/knowledge-lineage.md) (K-002, K-003, K-004), [`99_HISTORY/decision-log.md`](../99_HISTORY/decision-log.md) (D003) | 棄却知見として体系化済み。 |
| `STATE.md` (フェーズ4.7〜4.8) | Soft Logic、記憶特徴量、v4.0平滑化同調スコア、ファンアウト速度先行性 | **【完了 / 要再検証】** | [`03_KNOWLEDGE/knowledge-lineage.md`](../03_KNOWLEDGE/knowledge-lineage.md) (K-005: Inconclusive) | **Issue 起票対象**: 新環境・新データ（2026年9月まで）下で M3 定量検証を実施し、Supported/Refuted を判定。 |
| `knowledge/records/2026-09/ANL-001〜009` | 過去の個別分析レコード（SMA回帰、BBスクイーズ、Void、Hugging等） | **【要再検証 / 移植】** | `03_KNOWLEDGE/experiments/` | **Issue 起票対象**: 有望なテーマ（Void Edge, BB Squeeze等）を新実験ディレクトリへ移植・再検証。 |
| `knowledge/LINEAGE.md`, `index.json` | 旧知識ツリー・インデックス | **【完了】** | [`03_KNOWLEDGE/knowledge-lineage.md`](../03_KNOWLEDGE/knowledge-lineage.md), `tools/kb.py` | 知識系譜グラフおよび新 CLI への移行完了。 |
| `knowledge/DICTIONARY.md` | 特徴量形式化辞書（ゴムパッチン、Squeeze、AFS、Topology等） | **【要再検証 / 移植】** | `01_CONCEPTS/`, `02_SPECIFICATIONS/` | **Issue 起票対象**: 特徴量概念・計算仕様書（Feature Specification）として現行体系へ整理・昇格。 |

---

### 3. ソースコード・CLI・分析スクリプト

| 旧資産 | 旧概要 | 分類 | 取り込み先 / 現行対応 | 今後のアクション |
|---|---|---|---|---|
| `tools/kb.py` | 旧ナレッジ管理CLI | **【完了】** | [`tools/kb.py`](../tools/kb.py) | `MTF_AI_Trade` 新アーキテクチャ（Issue連動実験・バリデーション）へ再実装完了。 |
| `src/` (旧共通コード) | `data_loader`, `features`, `evaluation`, `models` 等 | **【完了 / 要再検証】** | [`src/config.py`](../src/config.py), [`src/data_loader.py`](../src/data_loader.py), [`src/evaluation.py`](../src/evaluation.py) | 基盤コードは再構築完了。`features.py` の有用ロジックは M3 で順次取り込み。 |
| `agent-skills/trade-knowledge/` | 旧エージェントスキル | **【完了】** | `agent-rules.md`, `development-workflow.md`, `tools/kb.py` | プロンプト・CLI・ワークフローに統合済み。単独スキルとしては退避維持。 |
| ルート直下の `*.py` (約70個) | 各種EDA・可視化・プロットスクリプト | **【アーカイブ / 要再検証】** | 必要に応じて個別実験へ移植 | 散乱スクリプト群はアーカイブ維持。必要な分析ロジックのみ実験ディレクトリ（`experiments/<N>-<slug>/`）へ抽出。 |
| ルート直下の `*.png`, `*.csv`, `*.txt` | 過去の検証出力画像・データ一時ファイル | **【アーカイブ】** | — | 過去の観測証跡として保管。現行体系への移植不要。 |
| `reports/`, `results/`, `models/` | 旧レポート、旧LightGBMモデルファイル | **【アーカイブ】** | — | アーカイブ保管。 |

---

## Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-09 | 0.1.0 | 初版作成（旧資産アーカイブ化・参照専用化） | @makagi / [#16](https://github.com/makagi/MTF_AI_Trade/pull/16) |
| 2026-10-13 | 0.2.0 | 旧資産棚卸し一覧（Inventory & Triage）および取り込み方針の策定 | @makagi / [#32](https://github.com/makagi/MTF_AI_Trade/pull/32) |
