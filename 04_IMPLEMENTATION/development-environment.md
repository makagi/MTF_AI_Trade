# MTFシステムトレード Development Environment

**Version:** 0.1
**Status:** Draft

## 1. Purpose

本ドキュメントは、プロジェクトにおける開発・実行環境、ディレクトリ責務、ツールチェーン、およびデータアクセス規程を定義する。

AIエージェントおよび開発者が一貫した環境で作業し、分析・実験・実装の**再現性（Reproducibility）**を担保することを目的とする。

---

## 2. Directory Structure and Responsibilities

`00_GOVERNANCE/documentation-architecture.md` に基づき、リポジトリ構成を以下の通り規定する。

```text
MTF_AI_Trade/
├── 00_GOVERNANCE/          # プロジェクトの目的、原則、文書体系
├── 01_CONCEPTS/            # 市場認識、MTFフレームワーク、概念モデル
├── 02_SPECIFICATIONS/      # 具体的なシステム仕様（時間軸、特徴量、売買ルール）
├── 03_KNOWLEDGE/           # 仮説、実験記録、知識の系譜（knowledge/ と連携）
├── 04_IMPLEMENTATION/      # アーキテクチャ、開発環境、ワークフロー、Agent規約
├── 05_OPERATIONS/          # バックテスト運用、実運用、監視規程
├── 99_HISTORY/             # 意思決定ログ（Decision Log / ADR）、履歴
├── src/                    # 共通・本番用Pythonソースコード
├── knowledge/              # 自己完結型 Analysis Record およびデータセット定義
├── reports/                # 検証レポート、監査ログ、可視化成果物
└── tools/                  # 運用支援ツール、ナレッジCLI（kb.py 等）
```

### ディレクトリ運用の鉄則
1. **ルート直下にファイルを散乱させない**:
   - スクリプトは `src/` または `tools/`、分析・実験記録は `knowledge/records/`、レポートは `reports/` に配置する。
2. **空ディレクトリの原則**:
   - 必要になるまで無意味なファイルを作成しない（Simplicityの原則）。

---

## 3. Core Runtime & Toolchain

- **OS**: Windows (x86_64) / PowerShell
- **Python**: Python 3.10+ / 3.11+
- **パッケージ & 仮想環境管理**: `uv` または 標準 `venv`
  - 仮想環境パス: `.venv/`
  - パッケージ依存関係: `requirements.txt`
- **主要ライブラリ群**:
  - データ処理: `pandas`, `numpy`, `scipy`
  - 機械学習 / 統計: `lightgbm`, `scikit-learn`
  - 描画 / レポート: `matplotlib`, `seaborn`
  - ユーティリティ: `tqdm`, `pyyaml`, `joblib`

---

## 4. Execution Conventions

### 基本実行コマンド
- スクリプト実行:
  ```powershell
  uv run python <path_to_script>.py
  # または
  .venv\Scripts\python <path_to_script>.py
  ```
- ナレッジベースCLI操作:
  ```powershell
  python tools/kb.py list       # レコード一覧表示
  python tools/kb.py validate   # 整合性検証
  python tools/kb.py index      # インデックス・系譜図の更新
  ```

---

## 5. Data Access & Management

- **市場データ保存先**:
  - プロジェクト外の共有データディレクトリ（例: `../Data`）または指定パスを参照する。
  - データパスのハードコードを避け、設定ファイル（`src/config.py` 等）で一元管理する。
- **データパーティショニング（期間分離規程）**:
  - **Discovery / Train**: 2020-01-01 〜 2023-12-31（仮説立案・探索・学習）
  - **Validation**: 2024-01-01 〜 2024-12-31（一発勝負の仮説検定・パラメータ固定検証）
  - **Holdout**: 2025-01-01 〜 （**完全封印**。探索・チューニングへの使用厳禁）
