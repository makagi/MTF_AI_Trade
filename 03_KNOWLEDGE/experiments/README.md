# 実験記録 (Experiments)

**Doc ID:** KNOW-EXP-001  
**Version:** 0.3.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-25  
**Related Issues:** [#6](https://github.com/makagi/MTF_AI_Trade/issues/6), [#11](https://github.com/makagi/MTF_AI_Trade/issues/11), [#14](https://github.com/makagi/MTF_AI_Trade/issues/14), [#79](https://github.com/makagi/MTF_AI_Trade/issues/79)  
**Related Docs:** [../README.md](../README.md), [../knowledge-lineage.md](../knowledge-lineage.md), [../../02_SPECIFICATIONS/evaluation.md](../../02_SPECIFICATIONS/evaluation.md), [../../00_GOVERNANCE/issue-driven-workflow.md](../../00_GOVERNANCE/issue-driven-workflow.md)  

---

## 1. Purpose

本ディレクトリは、Analysis Issue（`#N`）に対応する自己完結型の実験記録ディレクトリ（`<N>-<slug>/`）を格納する。

---

## 2. Directory Naming Convention

```text
<Issue番号>-<短い英小文字スラグ>
例: 20-sma-mean-reversion
    25-htf-squeeze-breakout
```

---

## 3. Mandatory Structure

各実験ディレクトリは、単独で再実行可能かつ自己完結していなければならない。

* `record.md`: 実験の背景、事前登録仮説・判定基準の転記、実行結果、考察
* `config.yaml`: 使用したパラメータおよびデータセット指定
* `run.py`: 再現スクリプト（`uv run python run.py` で実行可能）
* `metrics.json`: `02_SPECIFICATIONS/evaluation.md` §4 で定める必須評価メトリクス
* `artifacts/`: 出力されたチャート、グラフ画像
* `review/`: Missed Opportunity Review (MOR) スイート（Stage A/B チャート各10枚、`gallery_stageA.md`、`gallery_stageB.md`、`answer_key.json`、`cases.json`、`observations.yaml`）

---

## 4. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-10 | 0.1.0 | 初版作成（Issue連動実験記録規約） | @makagi / [#20](https://github.com/makagi/MTF_AI_Trade/pull/20) |
| 2026-10-13 | 0.2.0 | 書式・メタデータヘッダー規約統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
| 2026-10-25 | 0.3.0 | Missed Opportunity Review (MOR) スイート（review/）の必須構成追加 | @makagi / [#80](https://github.com/makagi/MTF_AI_Trade/pull/80) |

