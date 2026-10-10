---
name: trade-knowledge
description: >-
  Manage and explore quantitative trading analysis records, hypotheses, and knowledge lineage.
  Use when conducting new trade analyses, exploring past findings, checking edge hypotheses,
  reproducing backtest runs, or creating derived analysis records.
---

# System Trade Knowledge Base Skill

このスキルは、システムトレードにおける分析レコード（Analysis Record）の管理、過去の知見・仮説（Findings / Hypotheses）の探索、および再現可能な派生分析の作成プロシージャを提供します。

---

## 1. 基本原則 (Core Philosophy)

1. **データと分析の分離**:
   - データセットは `knowledge/datasets/*.yaml` で期間・ソースパス・ハッシュを固定。
   - 分析は `knowledge/records/YYYY-MM/ANL-YYYYMMDD-XXX_<slug>/` で自己完結。
2. **再現性の絶対担保**:
   - 各分析フォルダ内の `run.py` は単独で再実行可能でなければならない。
   - 実行時の環境情報（Pythonバージョン、実行日時）は `metrics.json` に自動記録する。
3. **知識系譜（Knowledge Lineage）の連鎖**:
   - `ANL`(分析) $\rightarrow$ `FIND`(発見した客観的事実) $\rightarrow$ `HYP`(仮説) $\rightarrow$ `ANL`(派生分析)。
   - 派生分析を作成する際は必ず `derived_from: [ANL-...]` を明記する。
4. **一方向生成の原則**:
   - `knowledge/index.json` および `knowledge/LINEAGE.md` は人間・AIが手動編集せず、必ず `python tools/kb.py index` で自動生成する。

---

## 2. エージェントの標準ワークフロー

### シナリオ A: 過去の知見を探索・回答する
ユーザーから「〜について過去に何を分析した？」「〜のエッジはある？」と質問された場合：
1. まず `knowledge/index.json` を読み、該当する `symbol`, `timeframe`, `findings`, `hypotheses` を持つレコードを特定する。
2. 特定したレコードの `record.md` と `metrics.json` を閲覧し、客観的な数値・結論を回答する。
3. 必要に応じて `knowledge/LINEAGE.md` から知見の系譜を説明する。

### シナリオ B: 新しい分析を実行・記録する
1. **新規レコード作成**:
   ```bash
   python tools/kb.py new --title "My Analysis Title" --symbol BTCUSD --timeframe 1h --dataset BTCUSD_1H_DISCOVERY --slug my_analysis
   ```
2. **パラメータと再現コードの実装**:
   - `config.yaml` に分析固有のパラメータを定義。
   - `run.py` を実装し、計算結果を `metrics.json`、グラフを `artifacts/` に保存。
3. **実行と検証**:
   ```bash
   uv run python knowledge/records/YYYY-MM/ANL-.../run.py
   ```
4. **ドキュメント記載**:
   - `record.md` に目的・数式・結果の考察・`findings`・`hypotheses` を記述。
5. **インデックス更新とバリデーション**:
   ```bash
   python tools/kb.py index
   python tools/kb.py validate
   ```

### シナリオ C: 過去の分析を元にした派生分析（継承）
過去の分析 `ANL-XXXX` の条件を引き継ぎつつ、パラメータや期間、追加フィルターを検証する場合：
1. `--derived-from` を指定して新規作成：
   ```bash
   python tools/kb.py new --title "Slope Moderated Analysis" --derived-from ANL-20260922-001 --slug slope_moderation
   ```
2. 先行分析の `run.py` や `config.yaml` をベースに改良。
3. `record.md` に先行分析との差分、仮説の検証結果（支持/棄却）を記録。
4. `python tools/kb.py index` を実行して系譜グラフを更新。

---

## 3. 主要コマンドリファレンス

| コマンド | 説明 |
| :--- | :--- |
| `python tools/kb.py new --title "..." --slug ...` | 新規分析レコード雛形を作成（連番自動採番） |
| `python tools/kb.py new --derived-from ANL-...` | 派生分析レコードを作成 |
| `python tools/kb.py list` | 登録済みレコードの一覧を表示 |
| `python tools/kb.py index` | `index.json` と `LINEAGE.md` を再生成 |
| `python tools/kb.py validate` | 全レコードのFrontmatter、必須ファイル、参照整合性をチェック |
| `python tools/kb.py web [--port 8765]` | Web UIダッシュボードを起動 |

---

## 4. プロンプト集との連動
ユーザーからの指示パターンや、エージェントが従うべきプロンプトテンプレートは [knowledge/PROMPTS.md](../../knowledge/PROMPTS.md) に体系化されています。
分析タスクを開始する際は、記載されているフォーマットに沿って客観的評価・再現コードの実装・系譜（Lineage）の更新を行ってください。
