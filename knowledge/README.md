# システムトレード・ナレッジベース (System Trade Knowledge Base)

市場分析の結果、仮説、数式、再現コード、グラフを一体化し、人間とAIの双方が過去の分析を再利用・派生・検証できるようにするためのナレッジ基盤です。

---

## 1. 設計思想

```text
市場データ (Dataset)
       ↓
分析実行 (run.py + config.yaml)
       ↓
┌────────────────────────────────────────┐
│ Analysis Record (ANL-xxx)              │
│ ├─ 自然言語 (record.md)                 │
│ ├─ 数式 (KaTeX LaTeX)                  │
│ ├─ 定量結果・環境 (metrics.json)        │
│ ├─ チャート画像 (artifacts/)            │
│ └─ 発見 (FIND) と 仮説 (HYP)           │
└──────────────────┬─────────────────────┘
                   ↓
      知識系譜 (Knowledge Lineage)
                   ↓
         次の派生分析 (ANL-yyy)
```

1. **データと分析の分離**:
   - `knowledge/datasets/` でデータセットの期間・パス・タイムゾーンを定義。
2. **再現コードの同居**:
   - 各分析フォルダ内に `run.py` を格納し、単独で再実行可能にする。
3. **知識グラフ（Lineage）**:
   - `ANL` $\rightarrow$ `FIND` $\rightarrow$ `HYP` $\rightarrow$ `ANL` の連鎖を `LINEAGE.md` に可視化。
4. **AI検索のための軽量インデックス**:
   - `knowledge/index.json` に軽量なメタデータのみを集約し、AIがコンテキストを節約して探索可能。

---

## 2. ディレクトリ構成

```text
MTF_AI_Trade/
├── knowledge/
│   ├── index.json                   # [自動生成] AI検索用カタログ
│   ├── LINEAGE.md                   # [自動生成] Mermaid系譜図
│   ├── datasets/                    # データセット定義
│   │   ├── BTCUSD_1H_DISCOVERY.yaml
│   │   └── BTCUSD_1H_VALIDATION.yaml
│   ├── templates/
│   │   └── record_template.md       # 新規レコード用雛形
│   ├── records/                     # 個々の分析レコード
│   │   └── 2026-09/
│   │       ├── ANL-20260922-001_sma_mean_reversion/
│   │       │   ├── record.md
│   │       │   ├── config.yaml
│   │       │   ├── run.py
│   │       │   ├── metrics.json
│   │       │   └── artifacts/
│   │       └── ANL-20260922-002_sma_slope_moderation/
│   └── web/                         # Web UIアセット (SPA)
│       └── index.html
├── tools/
│   ├── kb.py                        # ナレッジ管理CLI
│   └── web_server.py                # 軽量Web/APIサーバー
└── launch_knowledge_web.bat         # ワンクリック起動バッチ
```

---

## 3. CLI コマンドリファレンス

### ① 新規レコード作成 (`new`)
```bash
python tools/kb.py new --title "分析タイトル" --symbol BTCUSD --timeframe 1h --slug my_analysis
```

### ② 派生分析の作成 (`--derived-from`)
```bash
python tools/kb.py new --title "派生分析" --derived-from ANL-20260922-001 --slug derived_test
```

### ③ 再現スクリプトの実行
```bash
uv run python knowledge/records/2026-09/ANL-.../run.py
```

### ④ インデックスと系譜図の自動更新 (`index`)
```bash
python tools/kb.py index
```

### ⑤ レコード一覧の確認 (`list`)
```bash
python tools/kb.py list
```

### ⑥ 整合性チェック (`validate`)
```bash
python tools/kb.py validate
```

---

## 4. Webインターフェース & Floorp 連携

### Webダッシュボードの起動
```bash
python tools/kb.py web
# またはプロジェクトルートの launch_knowledge_web.bat をダブルクリック
```
デフォルトで `http://localhost:8765` が立ち上がり、自動でブラウザが開きます。

### 主な機能
1. **Records Explorer**: 銘柄・時間足・ステータスによる絞り込み検索。
2. **Interactive Detail Viewer**: `record.md` のMarkdown＋KaTeX数式、画像、メトリクス表のリッチ表示。
3. **Lineage Graph**: Mermaid.js による知識系譜・仮説ネットワークのグラフィカル表示。
4. **Action UI**: ブラウザ上からの新規レコード作成、再実行トリガー、インデックス再生成。

## 5. トレード分析AIエージェント向けプロンプト

AIエージェント（Antigravity, Cursor, Cline, Claude Code等）にナレッジベース運用を徹底させるためのプロンプト集を用意しています。
詳細は [knowledge/PROMPTS.md](PROMPTS.md) を参照してください。

### エージェント常駐指示（System Prompt / AGENTS.md 向け）
```markdown
あなたは「MTF_AI_Trade」専属のクオンツ・リサーチエージェントです。
1. スクリプトや画像をルートディレクトリに散乱させてはならない。
2. すべての分析は `python tools/kb.py new` で `knowledge/records/` 配下に作成すること。
3. 派生分析の場合は `--derived-from ANL-xxxx` を指定して系譜（Lineage）を繋ぐこと。
4. 分析完了後は必ず `python tools/kb.py index` と `python tools/kb.py validate` を実行すること。
5. 客観的事実(FIND)と仮説(HYP)を明確に区別し、摩擦コスト控除後の期待値で評価すること。
```

### ユースケース別プロンプトテンプレート (PROMPTS.md)
* **テンプレート A**: 過去の知見を調査・回答させる（Querying Knowledge）
* **テンプレート B**: 新規仮説の分析とレコード作成（New Analysis Record）
* **テンプレート C**: 過去分析の継承と派生検証（Derived Analysis & Lineage）
* **テンプレート D**: 2024年（Validation期間）での一発勝負テスト（Out-of-Sample Validation）

