# 体系化された知識 (Knowledge)

**Doc ID:** KNOW-ITM-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-13  
**Related Issues:** [#6](https://github.com/makagi/MTF_AI_Trade/issues/6), [#9](https://github.com/makagi/MTF_AI_Trade/issues/9), [#11](https://github.com/makagi/MTF_AI_Trade/issues/11)  
**Related Docs:** [../README.md](../README.md), [../knowledge-lineage.md](../knowledge-lineage.md), [../../02_SPECIFICATIONS/evaluation.md](../../02_SPECIFICATIONS/evaluation.md)  

---

## 1. Purpose

本ディレクトリは、仮説検証を経て合意された確定知識項目（`K-xxx.md`）を格納する。

---

## 2. Numbering Convention

* `K-001`, `K-002`, `K-003`...
* PR レビューおよびマージ時に人間オペレーターの合意（Human Gate）を経て確定する。

---

## 3. File Structure

各 `K-xxx.md` は以下の情報を含める：

* **ステータス**: `Supported`（支持） / `Refuted`（反証・棄却） / `Inconclusive`（保留・途上） / `Observed`（観測）
* **要約**: 検証によって確認された事実・法則
* **起因 Issue / 実験**: 関連する Analysis Issue および `experiments/<N>-<slug>/` へのリンク
* **過去資産の出典**: `90_LEGACY/` 内の関連 ANL / FIND / HYP レコード
* **影響する仕様**: `02_SPECIFICATIONS/` の該当仕様への反映状況

---

## 4. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-10 | 0.1.0 | 初版作成（体系化知識K-xxx規約） | @makagi / [#20](https://github.com/makagi/MTF_AI_Trade/pull/20) |
| 2026-10-13 | 0.2.0 | 書式・メタデータヘッダー規約統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
