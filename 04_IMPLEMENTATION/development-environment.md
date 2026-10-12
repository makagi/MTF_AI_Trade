# MTFシステムトレード Development Environment

**Doc ID:** DEV-ENV-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-12  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4), [#13](https://github.com/makagi/MTF_AI_Trade/issues/13), [#14](https://github.com/makagi/MTF_AI_Trade/issues/14)  
**Related Docs:** [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md), [development-workflow.md](development-workflow.md), [agent-rules.md](agent-rules.md), [03_KNOWLEDGE/README.md](../03_KNOWLEDGE/README.md)  

---

## 1. Purpose

本ドキュメントは、プロジェクトにおける開発・実行環境、ディレクトリ責務、ツールチェーン、およびデータアクセス規程を定義する。

AI エージェントおよび人間の開発者が一貫した環境で作業し、分析・実験・実装の**再現性（Reproducibility）**を担保することを目的とする。

---

## 2. Directory Structure and Responsibilities

`00_GOVERNANCE/documentation-architecture.md` に基づき、リポジトリ構成を以下の通り規定する。

```text
MTF_AI_Trade/
├── 00_GOVERNANCE/              # プロジェクト目的、原則、文書体系、運用規約
├── 01_CONCEPTS/                # 市場認識、MTFフレームワーク、概念モデル
├── 02_SPECIFICATIONS/          # 具体的なシステム仕様（評価仕様、特徴量、戦略）
├── 03_KNOWLEDGE/               # 仮説検証サイクル、実験記録、知識の系譜
│   ├── experiments/            # 自己完結した実験記録 (<N>-<slug>/)
│   └── knowledge/              # 体系化された知識 (K-xxx)
├── 04_IMPLEMENTATION/          # 開発環境、ワークフロー、Agent規約
├── 05_OPERATIONS/              # バックテスト定例運用、実運用規約
├── 90_LEGACY/                  # 過去資産アーカイブ（Read-only）
├── 99_HISTORY/                 # 意思決定ログ（ADR）、履歴
├── src/                        # 共通Pythonソースコード（config, data_loader, evaluation等）
├── tools/                      # 運用支援CLIツール（kb.py等）
├── pyproject.toml              # プロジェクトメタデータおよび依存関係定義
└── README.md                   # リポジトリ入口
```

### ディレクトリ運用の鉄則
1. **ルート直下にスクリプトや画像ファイルを散乱させない**:
   - 共通モジュールは `src/`、CLI は `tools/`、実験コード・出力は `03_KNOWLEDGE/experiments/<N>-<slug>/` に配置する。
2. **空ディレクトリの原則**:
   - 必要になるまで無意味なファイルを作成しない（Simplicity の原則）。

---

## 3. Core Runtime & Toolchain

- **OS**: Windows (x86_64) / PowerShell
- **Python**: Python 3.11 (`pyproject.toml` 準拠)
- **パッケージ & 仮想環境管理**: `uv`
  - 設定ファイル: `pyproject.toml`
  - 仮想環境パス: `.venv/`
- **主要ライブラリ群**:
  - データ処理: `pandas`, `numpy`, `scipy`
  - 機械学習 / 統計: `lightgbm`, `scikit-learn`
  - 描画 / レポート: `matplotlib`, `seaborn`
  - ユーティリティ: `tqdm`, `pyyaml`, `joblib`
  - 開発 / テスト: `pytest`

---

## 4. Execution Conventions

### 基本実行コマンド
* **依存関係の同期**:
  ```powershell
  uv sync
  ```
* **単体テストの実行**:
  ```powershell
  uv run pytest
  ```
* **新規実験の作成**:
  ```powershell
  uv run python tools/kb.py new <issue_no> <slug> --title "My Experiment Title"
  ```
* **実験スクリプトの実行**:
  ```powershell
  uv run python 03_KNOWLEDGE/experiments/<issue_no>-<slug>/run.py
  ```
* **実験ディレクトリの整合性検証**:
  ```powershell
  uv run python tools/kb.py validate
  ```

---

## 5. Data Access & Management

### 5.1 市場データの配置と動的解決
市場データの保存パスはハードコードせず、`src/config.py` の `get_data_dir()` を介して動的に解決する。

* **優先順位**:
  1. 環境変数 `MTF_DATA_DIR` が設定されている場合はそのパスを使用。
  2. 未設定の場合は `D:/work/AI-Trade/Data` を探索。
  3. 相対パス `../Data` または `./data` をフォールバック探索。

### 5.2 データパーティショニング規律
実験およびモデル学習で使用可能なデータ期間は、[02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) §2（Discovery / Validation / Holdout 期間の定義）に従う。

* **Discovery / Train (2020-01-01 〜 2025-04-30)**:
  - 通常のリサーチ・探索・モデル学習には `src.data_loader.load_discovery_data()` を使用する。
* **Validation (2025-05-01 〜 2026-03-31)**:
  - 一発勝負の仮説検証には `src.data_loader.load_validation_data()` を使用する（2025年5〜10月の上昇局面と10月〜2026年3月の下落局面の両面検証）。
* **Holdout (2026-04-01 〜 現在)**:
  - `src.data_loader.load_ohlcv()` はデフォルトで Holdout 期間のデータを物理的に遮断する（探索段階でのアクセス厳禁）。

