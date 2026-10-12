# 知識・実験管理 (03_KNOWLEDGE)

**Doc ID:** KNOW-ARCH-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-12  
**Related Issues:** [#6](https://github.com/makagi/MTF_AI_Trade/issues/6), [#13](https://github.com/makagi/MTF_AI_Trade/issues/13), [#14](https://github.com/makagi/MTF_AI_Trade/issues/14)  
**Related Docs:** [00_GOVERNANCE/issue-driven-workflow.md](../00_GOVERNANCE/issue-driven-workflow.md), [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md), [knowledge-lineage.md](knowledge-lineage.md)  

---

## 1. Purpose

本ディレクトリは、プロジェクトにおける仮説検証サイクル（Analysis Issue $\rightarrow$ Experiment $\rightarrow$ Evidence $\rightarrow$ Knowledge）を通じて得られた実験記録および体系化された知識を管理する。

客観的エビデンスに基づく再現可能な知識のみを蓄積し、主観的推論や未検証アイデアが仕様（`02_SPECIFICATIONS/`）に無断混入することを防止する。

---

## 2. 知識管理の3層アーキテクチャ

知識の生成プロセスを以下の3層で分離・管理する。

```text
Layer 1: 仮説・判定基準 (Analysis Issue: #N)
    │  ・動機、対象時間軸、発動条件、期待される効果
    │  ・合否判定基準（事前登録: 02_SPECIFICATIONS/evaluation.md 準拠）
    ↓
Layer 2: 自己完結型 実験記録 (03_KNOWLEDGE/experiments/<N>-<slug>/)
    │  ・パラメータ設定 (config.yaml)
    │  ・再現コード (run.py)
    │  ・定量メトリクス (metrics.json)
    │  ・可視化成果物 (artifacts/)
    │  ・実験総括・考察 (record.md)
    ↓
Layer 3: 体系化された知識 (03_KNOWLEDGE/knowledge/ & knowledge-lineage.md)
       ・厳選された確定知識 (K-xxx: Supported / Refuted)
       ・証拠の強さ、起因 Issue、実験記録、および 90_LEGACY 出典リンク
       ・仕様（02_SPECIFICATIONS/）への昇格判定
```

---

## 3. 実験記録 (Experiment Record) の標準構成

すべての検証・実験は、対応する Analysis Issue 番号 `N` をプレフィックスとする自己完結ディレクトリとして `experiments/` 配下に配置する。

```text
03_KNOWLEDGE/experiments/<N>-<slug>/
├── record.md       # 実験レポート（Issueの仮説・基準を転記し、結果・考察を記録）
├── config.yaml     # 実行パラメータ・データセット指定
├── run.py          # 単独で再実行可能なシミュレーション／分析コード
├── metrics.json    # 定量評価結果（02_SPECIFICATIONS/evaluation.md §4 準拠）
└── artifacts/      # 出力プロット・チャート画像
```

### 3.1 `record.md` の必須記載項目
1. **メタデータ**: Issue番号、日付、検証者、対象銘柄・時間軸、使用データ期間（Discovery 期間必須）
2. **事前登録仮説と判定基準**: Issue 起票時に登録した合否基準の完全転記（事後改変の禁止）
3. **実験結果**: 往復 0.40% コスト控除後期待値、年別オーバーレイ結果、サンプル数、MFE/MAE
4. **結論**: 支持（Supported）、反証（Refuted）、または判定保留（Inconclusive）の明記
5. **知識への昇格要否**: `K-xxx` として系譜図へ登録すべき知見の抽出

---

## 4. 体系化された知識 (Knowledge: K-xxx)

仮説検証を経て合意された知見は、`03_KNOWLEDGE/knowledge-lineage.md`（および個別知識文書 `knowledge/K-xxx.md`）に `K-xxx` として登録される。

* **採番ルール**: PR レビューおよびマージ時に人間オペレーターの合意を経て採番（`K-001`, `K-002`...）。
* **証拠レベルの明示**:
  * `Supported`: 評価仕様の合否基準を満たし、仕様や戦略に昇格・採用された知識。
  * `Refuted`: コスト負けや非定常性により明確に反証・棄却された知識（重複実験の防止用）。
  * `Inconclusive`: サンプル不足等により結論が留保された知見。

---

## 5. 過去資産 (`90_LEGACY/`) との連携方針

現行体系導入前の過去分析レコード（`90_LEGACY/knowledge/records/` 配下の `ANL-*`）および発見事項（`FIND-*`, `HYP-*`）は、**再採番や移動を行わず、そのままの ID で出典として引用**する。

```markdown
例:
- 起因分析: 90_LEGACY/knowledge/records/2026-09/ANL-20260922-001_sma_mean_reversion
- 過去知見: FIND-001 (SMA -2 ATR 下方乖離における平均回帰性)
```

過去の分析コードを再検証・発展させる場合は、新規に Analysis Issue を起票し、派生実験（`experiments/<N>-<slug>/`）として現行体系内で再現・評価を行う。

---

## 6. ツールチェーン方針

実験記録の新規生成（テンプレート展開）、インデックス自動生成、整合性バリデーション（Frontmatter や必須ファイルの確認）を行う CLI ツール（`tools/kb.py`）は、Issue [#14](https://github.com/makagi/MTF_AI_Trade/issues/14)（PR [#21](https://github.com/makagi/MTF_AI_Trade/pull/21)）において新アーキテクチャに準拠して整備済みである。

* 新規実験作成: `uv run python tools/kb.py new <issue_no> <slug> --title "Title"`
* 実験整合性検証: `uv run python tools/kb.py validate`

---

## 7. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-10 | 0.1.0 | 初版作成（知識管理3層アーキテクチャ・Issue連動実験・ID体系策定） | @makagi / [#20](https://github.com/makagi/MTF_AI_Trade/pull/20) |
| 2026-10-10 | 0.2.0 | 開発環境再構築・新 `tools/kb.py` 仕様反映 | @makagi / [#21](https://github.com/makagi/MTF_AI_Trade/pull/21) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |

