# 意思決定ログ (Decision Log / ADR)

本ドキュメントは、プロジェクトの設計方針、アーキテクチャ、戦略、および運用の重要決定（Architecture Decision Records: ADR）を記録します。  
過去の意思決定の背景、検討された選択肢、および採択理由を永続化することで、方針のブレやAIエージェントによる無断変更を防止します。

---

## 決定一覧 (Summary)

| 決定ID | 日付 | タイトル | ステータス | 影響範囲 |
|---|---|---|---|---|
| **D001** | 2026-10-02 | 5層＋1層の成熟度別ドキュメント体系の採用 | 採択 (Accepted) | リポジトリ全般 |
| **D002** | 2026-09-20 | 期間分割の再設計（Train 2020-23 / Val 2024 / Holdout 2025+） | 採択 (Accepted) | 評価・データ |
| **D003** | 2026-09-21 | 1時間足単一テクニカル指標の限界証明とSoft Logic/MTFへの移行 | 採択 (Accepted) | 戦略・特徴量 |
| **D004** | 2026-10-09 | Issue駆動による開発・分析・ドキュメント運用の採用 | 採択 (Accepted) | リポジトリ全般 |
| **D005** | 2026-10-09 | 旧資産の `90_LEGACY/` への隔離（参照専用化） | 採択 (Accepted) | リポジトリ全般 |
| **D006** | 2026-10-10 | 文書層の上下関係統一とStrategyの定義・配置 | 採択 (Accepted) | ガバナンス・仕様 |
| **D007** | 2026-10-10 | 文書メタデータヘッダー規約と承認ライフサイクル（PRマージ＝合意）の定義 | 採択 (Accepted) | ドキュメント全般 |
| **D008** | 2026-10-10 | 評価仕様（SPEC-EVAL-001）の策定と摩擦コスト・期間分割のSSOT化 | 採択 (Accepted) | 仕様・評価 |
| **D009** | 2026-10-10 | 知識管理アーキテクチャの一本化とID体系の統一（Issue連動実験とK-xxx） | 採択 (Accepted) | 知識管理 |
| **D010** | 2026-10-10 | 現行開発環境の再構築（uv・pyproject.toml・動的データパス・最小src） | 採択 (Accepted) | 開発環境 |
| **D011** | 2026-10-12 | AIエージェント3層協調体制・権限境界の確立と実装ドキュメントの更新 | 採択 (Accepted) | 開発体制・Agent規約 |
| **D012** | 2026-10-12 | リスク管理原則（Risk First）の導入と8段階証拠連鎖・反復改善フライホイールの確立 | 採択 (Accepted) | ガバナンス・原則 |
| **D013** | 2026-10-12 | 01_CONCEPTS からの仕様記述分離と作業仮説表現の純化 | 採択 (Accepted) | 概念モデル |

---

## 各決定の詳細

### D001: 5層＋1層の成熟度別ドキュメント体系の採用
- **日付**: 2026-10-02
- **ステータス**: 採択 (Accepted)
- **文脈・課題**:
  - プロジェクトが発展し、相場認識（MTF）、分析ログ（Analysis Record）、AIエージェント開発基盤などが混在。単一仕様書では変更頻度の異なる情報が混ざり、AIの参照効率や保守性が低下していた。
- **決定内容**:
  - `00_GOVERNANCE`、`01_CONCEPTS`、`02_SPECIFICATIONS`、`03_KNOWLEDGE`、`04_IMPLEMENTATION`、`05_OPERATIONS`、`99_HISTORY` の5層＋1層構造を採用。
  - 「普遍概念（Concept）」と「個別システム仕様（Specification）」を分離し、再利用性とAIエージェント権限境界を確立。
- **結果・影響**:
  - ドキュメント配置規約が確定し、AIが自律的にドキュメントやIssueを整理可能となった。

---

### D002: 期間分割の再設計（Train 2020-23 / Val 2024 / Holdout 2025+）
- **日付**: 2026-09-20
- **ステータス**: 採択 (Accepted)
- **文脈・課題**:
  - サンプルサイズ不足による過学習を防ぎつつ、非定常な市場変化を捉えるため、十分な長さの探索期間が必要であった。
- **決定内容**:
  - Discovery/Train 期間: 2020年〜2023年（4年間）
  - Validation 期間: 2024年（1年間）
  - Final Holdout 期間: 2025年以降（完全封印）
- **結果・影響**:
  - 4年分の年別オーバーレイによる頑健性評価（EDA 05）が可能になり、2025年以降へのデータリークを厳密に遮断。

---

### D003: 1時間足単一テクニカル指標の限界証明とSoft Logic/MTFへの移行
- **日付**: 2026-09-21
- **ステータス**: 採択 (Accepted)
- **文脈・課題**:
  - 1時間足のSMA, BB, Stoch等によるルールベースおよび機械学習（MoE）検証を行ったが、往復0.4%の摩擦コストに勝てず、Total Returnがマイナスとなった。
- **決定内容**:
  - 単一足の価格指標のみで勝つことは数学的に不可能（Signal-to-Noise Ratio不足）と結論付け、ハードな閾値から連続値による「Soft Logic」、多時間軸（MTF）の波の同調、および代替データ（OI, Funding Rate等）の導入へ移行する。
- **結果・影響**:
  - v4.0特徴量（平滑化同調スコア、マクロ重力逆行スコア等）の開発へ進展。

---

### D004: Issue駆動による開発・分析・ドキュメント運用の採用
- **日付**: 2026-10-09
- **ステータス**: 採択 (Accepted)
- **文脈・課題**:
  - ドキュメント体系の再構築、分析、開発環境整備を並行して進める必要があり、作業の動機・判断・結果を追跡可能にする単位が必要であった。
  - 人間と AI Agent の間で作業を受け渡す共通単位がなかった。
- **検討した選択肢**:
  1. ローカルのタスクファイル（旧 `task.md` 方式）で管理する
  2. GitHub Issue / PR で管理する
  3. GitHub Issue / PR に加え GitHub Projects（カンバン）も初期から導入する
- **決定内容**:
  - 選択肢 2 を採用。ドキュメント・環境整備も含め全ての作業を Issue 起点とする（[issue-driven-workflow.md](../00_GOVERNANCE/issue-driven-workflow.md)）。
  - Projects は Simplicity 原則に従い、必要性が確認されてから導入する。
  - 初回のブートストラップ（運用ルール・テンプレート・ラベル整備）のみ Issue 運用前に直接実施する。
- **結果・影響**:
  - 以降のドキュメントレビュー指摘は Issue として起票し、PR で解消する。

---

### D005: 旧資産の `90_LEGACY/` への隔離（参照専用化）
- **日付**: 2026-10-09
- **ステータス**: 採択 (Accepted)
- **文脈・課題**:
  - 現行体系導入前の資産（`CONSTITUTION.md`、`STATE.md`、旧 `knowledge/`、ルート直下の約190個のスクリプト・出力、`src/`、`tools/` 等）が現行体系と混在し、どれが正本か判別できなかった。
- **検討した選択肢**:
  1. `99_HISTORY/` に統合する
  2. 現行体系とも履歴とも別の `90_LEGACY/` に隔離する
- **決定内容**:
  - 選択肢 2 を採用。`99_HISTORY` は現行体系における判断履歴、`90_LEGACY` は過去検討のノウハウ・解析例として参照する資料と位置付ける。
  - 新体系（`00`〜`05`, `99`）以外の資産を全て移動。旧 Agent Skill（`trade-knowledge`）も自動読み込みを避けるため退避。
  - 正本リポジトリは `MTF_AI_Trade` とする（`SakanaAISystemTrade` 側の同名文書は正本ではない）。
- **結果・影響**:
  - `04_IMPLEMENTATION/` の文書内にある `src/`、`tools/kb.py`、`knowledge/records/` 等への参照は旧パスとなるため、別 Issue で更新する。

---

### D006: 文書層の上下関係統一とStrategyの定義・配置
- **日付**: 2026-10-10
- **ステータス**: 採択 (Accepted)
- **関連Issue**: [#2](https://github.com/makagi/MTF_AI_Trade/issues/2)
- **文脈・課題**:
  - 文書ごとに階層図の順序（例: Knowledge が Specification の下にある等）が食い違い、動的な知識フィードバックと静的な依存関係が混同されていた。
  - 「Strategy」という語が4つの文脈で多義的に使われており、管理すべき成果物としての Strategy の定義・配置場所・ライフサイクルが未定義だった。
- **検討した選択肢**:
  1. Strategy を独立ディレクトリ（`0X_STRATEGIES/`）として新設する
  2. Strategy を `02_SPECIFICATIONS/strategies/` に配置し、Specification（部品）を有機的に組み合わせたルール一式として定義する
  3. 当面 Strategy を文書体系から除外する
- **決定内容**:
  - 選択肢 2 を採用。
  - 文書間の関係を「静的な参照（依存）関係（Vision → Principles → Concepts → Specifications → Strategies → Implementation → Operations）」と「動的な知識獲得と昇格のサイクル（Knowledge & Validation Loop）」の2軸で明確に分離・図解した。
  - Strategy は「特定の市場仮説に基づき、各仕様（Entry/Exit/Risk等: 部品）を有機的に組み合わせた、名前とバージョンを持つ売買ルール一式」と定義し、`02_SPECIFICATIONS/strategies/` 配下に配置する。
  - Strategy にライフサイクル状態（`Candidate` / `Adopted` / `Retired`）を導入し、都度の「売買判断」や「研究方針」とは明確に区別する。
- **結果・影響**:
  - `00_GOVERNANCE/documentation-architecture.md` および `00_GOVERNANCE/principles.md` を改訂。
  - 知識が仕様・戦略へ昇格する経路が明確化された。

---

### D007: 文書メタデータヘッダー規約と承認ライフサイクル（PRマージ＝合意）の定義
- **日付**: 2026-10-10
- **ステータス**: 採択 (Accepted)
- **関連Issue**: [#3](https://github.com/makagi/MTF_AI_Trade/issues/3)
- **文脈・課題**:
  - 文書ヘッダーが不統一で、改訂・承認の責任者や追跡情報が欠如していた。
  - Draft から Accepted への遷移ルールが曖昧で、「合意」「承認」の客観的証跡が定義されていなかった。
- **検討した選択肢**:
  1. コミットログのみで管理し、文書ヘッダーは不要とする
  2. 文書ヘッダーにステータス・バージョン・オーナー・関連Issueを記録し、GitHub PR のマージ操作を公式な承認エビデンスとする
- **決定内容**:
  - 選択肢 2 を採用。
  - 共通テンプレート `00_GOVERNANCE/templates/document-template.md` を作成。
  - ライフサイクル（Draft → Review → Accepted → Used → Deprecated）を GitHub Issue / PR フローと連動させ、人間の PR マージを正式な承認記録と規定。
  - AI Agent による PR の自己マージ（自己承認）を禁止。
- **結果・影響**:
  - `00_GOVERNANCE/documentation-architecture.md` §5, §6 を改訂。
  - 全文書の標準フォーマットが確定し、Issue #11（全文書の書式・文体の統一）のブロッカーが解消。

---

### D008: 評価仕様（SPEC-EVAL-001）の策定と摩擦コスト・期間分割のSSOT化
- **日付**: 2026-10-10
- **ステータス**: 採択 (Accepted)
- **関連Issue**: [#4](https://github.com/makagi/MTF_AI_Trade/issues/4)
- **文脈・課題**:
  - 摩擦コスト（0.4%）やデータ期間分割が、`assumptions.md`、`expected-value.md`、`agent-rules.md`、`development-*.md` 等の複数箇所に重複して直書きされていた。
  - 0.4% の算出根拠・内訳（手数料、スプレッド、スリッページ）や、必須評価メトリクス、仮説判定基準の体系的な仕様書が存在しなかった。
- **検討した選択肢**:
  1. `00_GOVERNANCE/assumptions.md` を正本とし、数値を管理する
  2. `02_SPECIFICATIONS/evaluation.md`（評価仕様）を新設して正本とし、算出根拠・必須メトリクス・判定基準と合わせて体系化する
- **決定内容**:
  - 選択肢 2 を採用。
  - `02_SPECIFICATIONS/evaluation.md` (SPEC-EVAL-001) を作成し、評価規律の単一情報源（SSOT）とする。
  - 摩擦コストモデル（往復0.40% = 手数料0.10% + スプレッド0.10% + スリッページ0.20%）、データ期間分割（Discovery 2020-23 / Validation 2024 / Holdout 2025+）、必須評価メトリクス、合否基準を一元管理。
  - `assumptions.md` は前提条件（市場コストが0.40%以内に収まる前提）のみに純化し、他文書の数値直書きを評価仕様へのリンク参照に置き換えた。
- **結果・影響**:
  - 02_SPECIFICATIONS 層の最初の仕様書が成立し、リサーチとバックテストの評価規律が確立された。

---

### D009: 知識管理アーキテクチャの一本化とID体系の統一（Issue連動実験とK-xxx）
- **日付**: 2026-10-10
- **ステータス**: 採択 (Accepted)
- **関連Issue**: [#6](https://github.com/makagi/MTF_AI_Trade/issues/6)
- **文脈・課題**:
  - 旧ナレッジベース（`ANL-*` / `FIND-*` / `HYP-*`）と `03_KNOWLEDGE`（`H001` / `E001` / `K001`）の ID 体系が衝突・二重管理となっていた。
  - Analysis Issue の起票（仮説事前登録）と、自己完結した実験コード・出力成果物のリポジトリ内保存形式との関係が未定義だった。
- **検討した選択肢**:
  1. 旧 ANL 形式と kb.py をそのまま移植する（Issue との二重管理が発生）
  2. 03_KNOWLEDGE の H/E/K 手書き形式を維持する（複数エージェント並行作業時のID採番衝突リスク）
  3. Analysis Issue 番号（`#N`）を実験ディレクトリ ID に採用し、自己完結レコード形式で実験を蓄積、厳選知見のみ `K-xxx` として採番管理する
- **決定内容**:
  - 選択肢 3 を採用。
  - 3層アーキテクチャ（Layer 1: Analysis Issue `#N` 事前登録 $\rightarrow$ Layer 2: `03_KNOWLEDGE/experiments/<N>-<slug>/` 自己完結実験記録 $\rightarrow$ Layer 3: `knowledge/` & `knowledge-lineage.md` の `K-xxx` 体系化知識）を確立。
  - 旧資産（`90_LEGACY/knowledge/records/`）の過去レコードは再採番せず、そのままの ID で出典として引用する方針を確定。
  - 既存の K001〜K005 を `K-001`〜`K-005` として再整理し、`90_LEGACY/` 配下の元レコードへの出典リンクを紐付けた。
- **結果・影響**:
  - `03_KNOWLEDGE/README.md`、`knowledge-lineage.md`、`04_IMPLEMENTATION/development-workflow.md` を改訂。
  - 仮説検証のワークフローと成果物配置が完全に統一された。

---

### D010: 現行開発環境の再構築（uv・pyproject.toml・動的データパス・最小src）
- **日付**: 2026-10-10
- **ステータス**: 採択 (Accepted)
- **関連Issue**: [#14](https://github.com/makagi/MTF_AI_Trade/issues/14)
- **文脈・課題**:
  - D005 で旧コードを `90_LEGACY/` へ退避したため、現行の `src/` および `tools/` が空となり、Analysis Issue を即時実行するための環境が存在しなかった。
  - データ保存パス（`D:\work\AI-Trade\Data`）が旧コード内でハードコードされていた。
- **検討した選択肢**:
  1. 旧 `requirements.txt` とハードコードパスを維持する
  2. `pyproject.toml` + `uv` で一元管理し、環境変数による動的データパス解決と Holdout 遮断ガード付きデータローダーを新設する
- **決定内容**:
  - 選択肢 2 を採用。
  - `pyproject.toml` を作成し、`uv` による仮想環境同期・パッケージ管理を標準化。
  - `src/config.py`: 環境変数 `MTF_DATA_DIR` 優先の自動探索と `SPEC-EVAL-001` 準拠定数を定義。
  - `src/data_loader.py`: Holdout 期間アクセス遮断ガードと Discovery/Validation 分割ローダーを実装。
  - `src/evaluation.py`: `SPEC-EVAL-001` 準拠の必須メトリクス・年別分解計算モジュールを新設。
  - `tools/kb.py`: 新アーキテクチャ（`03_KNOWLEDGE/experiments/<N>-<slug>/`）対応の実験作成 CLI を新設。
- **結果・影響**:
  - `04_IMPLEMENTATION/development-environment.md` を改訂。
  - 新規 Analysis Issue の即時実行およびバックテストが可能な環境が整備された。

---

### D011: AIエージェント3層協調体制・権限境界の確立と実装ドキュメントの更新
- **日付**: 2026-10-12
- **ステータス**: 採択 (Accepted)
- **関連Issue**: [#13](https://github.com/makagi/MTF_AI_Trade/issues/13)
- **文脈・課題**:
  - D005 および D010 に伴い、`04_IMPLEMENTATION/` 配下の各ドキュメント（`development-workflow.md`, `agent-rules.md`, `development-environment.md`）に残存する旧パス参照（`knowledge/records/`, `reports/`）と新環境（Python 3.11, uv, `src/`, `tools/kb.py`, `03_KNOWLEDGE/experiments/`）との不整合を解消する必要があった。
  - 人間オペレーターが日常的にスマホから開発・分析を進めるにあたり、要件定義・開発管制・コーディングエージェントの分担および権限境界（勝手なPRマージやHoldoutアクセスの防止）を単一情報源（SSOT）として明文化する必要があった。
- **検討した選択肢**:
  1. 単一のAIアシスタントに全権限を委ね、都度チャットで指示する
  2. 3層協調アーキテクチャ（第1層: Requirements Agent = Antigravity、第2層: SSOT = GitHub、第3層: Orchestrator = Orca ＋ マルチエージェント群: Antigravity/Codex/Open Claw/ローカルLLM）と Human Gate（人間のみがPRマージ権限を持つ）を導入し、権限境界を `04_IMPLEMENTATION/agent-rules.md` に集約する
- **決定内容**:
  - 選択肢 2 を採用。
  - **第1層 Requirements Agent (Antigravity)**: 要求理解、コードベース・仕様・知見調査、Issue起票/更新を担当。権限は Read + Create/Update Issue に限定（直接コード変更やPRマージ権限は持たない）。
  - **第2層 SSOT (GitHub)**: GitHub Issues をバックログ・作業指示書、PR / Actions を変更差分・CIテスト・定量評価の記録基盤とする。
  - **第3層 Orchestrator (Orca) ＆ マルチエージェント群**: Orca が Issue を起点として開発ブランチ作成・タスク分解を行い、Antigravity, Codex, Open Claw, ローカルLLM (LM Studio / Lemonade) 等のマルチエージェント群をプラグイン可能として実装・実験（`tools/kb.py`）・検証（`SPEC-EVAL-001`）を実行、PRを作成する。
  - **Human Gate 原則**: AIによる PR の自己承認・自己マージは厳禁とし、合意および main 反映の権限は人間オペレーターのみが保持する。
  - `04_IMPLEMENTATION/` 配下の全ドキュメントおよび `03_KNOWLEDGE/README.md` を新開発環境と新アーキテクチャに完全同期。
- **結果・影響**:
  - `04_IMPLEMENTATION/agent-rules.md` がエージェント行動規範・権限境界の SSOT として確定。
  - `04_IMPLEMENTATION/` 内のリンク切れ・旧パス参照が完全に解消された。

---

### D012: リスク管理原則（Risk First）の導入と8段階証拠連鎖・反復改善フライホイールの確立
- **日付**: 2026-10-12
- **ステータス**: 採択 (Accepted)
- **関連Issue**: [#7](https://github.com/makagi/MTF_AI_Trade/issues/7)
- **文脈・課題**:
  - トレードシステムとして最重要である「リスク管理・資金保全（存続性優先、破産確率排除、ドローダウン制約）」が `principles.md` に明文化されていなかった。
  - `principles.md` §1.1 の認識連鎖が `Observation` から始まっており、`mtf-framework.md` §5 の `Fact → Observation → Interpretation` と不整合だった。
  - AIエージェントの役割記述が `principles.md` と `04_IMPLEMENTATION/agent-rules.md` で重複していた（SSOT原則違反）。
  - M1（ガバナンス/環境） $\rightarrow$ M2（Agent QA・管制） $\rightarrow$ M3（特徴量・仮説検証） $\rightarrow$ M4（戦略・実運用）の反復改善ループおよび「特徴量理解の深化による戦略昇格」が原則として明文化されていなかった。
- **決定内容**:
  - **Risk First 原則の新設**: 収益性最大化よりも資金存続性・破産確率の排除を最優先とし、下方リスクの厳格な切断とドローダウン制約を最高位原則として明記。
  - **8段階証拠連鎖への統一**: `Fact → Observation → Interpretation → Hypothesis → Experiment → Evidence → Conclusion → Decision` を定義し、未検証仮説の確定事実化を厳禁化。
  - **エージェント規約の SSOT 化**: 具体的な役割・権限境界は `04_IMPLEMENTATION/agent-rules.md` を正本とし、`principles.md` は原則のみを規定。
  - **継続的改善フライホイール（§10）の確立**: 特徴量に対する知識（`K-xxx`）を高めてから戦略（M4）へ昇格させる方針、および M3 の実験ミスを M2（Canary Benchmark）へ還元する自己進化ループを明文化。
- **結果・影響**:
  - `00_GOVERNANCE/principles.md` を v0.2.0 へ全面改訂。
  - `04_IMPLEMENTATION/development-workflow.md` にも反復改善フライホイールを追記。

---

### D013: 01_CONCEPTS からの仕様記述分離と作業仮説表現の純化
- **日付**: 2026-10-12
- **ステータス**: 採択 (Accepted)
- **関連Issue**: [#5](https://github.com/makagi/MTF_AI_Trade/issues/5)
- **文脈・課題**:
  - `01_CONCEPTS/` の各文書内に、特定の実装・時間軸・パラメータ（具体値: Weekly/Daily/4H/1H/15m/1m, ATR(14), -2 ATR, Armed状態等）が混入していた。
  - 「圧倒的に強い影響力」「ダマシとなる確率が極めて高い」「最も優位性が高い」「唯一の構造」といった未検証の主張や断定表現が散見され、`principles.md` §2（事実と仮説の分離）に抵触していた。
- **決定内容**:
  - `01_CONCEPTS/` の全5文書（`mtf-framework.md`, `market-structure.md`, `volatility.md`, `expected-value.md`, `market-regime.md`）から具体的パラメータ記述を分離し、「普遍的な相場概念・モデル」に純化。
  - 具体値（足の長さ、ATR期間等）はあくまで「代表例」として注記し、正式な定数・計算式は `02_SPECIFICATIONS/` に委ねる構造を徹底。
  - 断定的な未検証主張を「当システムにおける作業仮説（Working Hypothesis）」として表現を是正。
  - 全5文書に標準メタデータヘッダー（Doc ID, Version, Status, Related Issues/Docs）を配備。
- **結果・影響**:
  - Concept（普遍モデル）と Specification（具体パラメータ）の境界が厳格化され、AIエージェントによる仕様の無断混入が防止された。



