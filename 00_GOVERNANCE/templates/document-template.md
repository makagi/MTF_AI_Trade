# [文書タイトル]

<!--
【メタデータヘッダー規約】
本リポジトリの全ドキュメント（00〜05）は、本ヘッダーを先頭に記載する。
-->
**Doc ID:** [省略可能: 例 SPEC-EVAL-001 / STRAT-001 等の管理番号]  
**Version:** 0.1.0  
**Status:** Draft  <!-- Draft | Review | Accepted | Deprecated -->  
**Owner:** [@username または プロジェクトロール名]  
**Last Updated:** YYYY-MM-DD  
**Related Issues:** [#番号](https://github.com/makagi/MTF_AI_Trade/issues/番号)  
**Related Docs:** [関連文書名](相対パス.md)  

---

## 1. Purpose（目的と対象読者）

本ドキュメントが何を定義し、何を対象外とするか、なぜ必要なのかを明確に記述する。

---

## 2. Core Content（主要な定義・仕様・概念）

* **文体規律**: 原則として「である」調（簡潔・論理的）で統一する。
* **事実と推論の分離**:
  * 客観的事実（観測データ、確定した仕様）と、仮説や推論（将来の予測、解釈）を混同しない。
  * 未検証の仮説を記載する場合は、必ず「仮説（Hypothesis）」と明記し、対応する Analysis Issue または仮説IDを併記する。
* **Single Source of Truth (SSOT)**:
  * 他文書で定義されている定数や規律（例: 摩擦コスト 0.4%、データ期間分割等）を再定義・ハードコードせず、正本文書へのリンクを参照する。

```text
ここに図表や構造、数式、ロジックを記載
```

---

## 3. Scope & Constraints（適用範囲と制約事項）

* 適用される条件（市場、時間軸、レジーム等）
* 前提条件（`00_GOVERNANCE/assumptions.md` への参照）
* 非対象（Out of Scope）事項

---

## 4. Change History（変更履歴）

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| YYYY-MM-DD | 0.1.0 | 初版作成 | @username / [#PR番号] |
