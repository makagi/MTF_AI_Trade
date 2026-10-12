# 前提条件 (Assumptions)

**Doc ID:** ASSUMP-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-13  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4), [#8](https://github.com/makagi/MTF_AI_Trade/issues/8), [#9](https://github.com/makagi/MTF_AI_Trade/issues/9), [#11](https://github.com/makagi/MTF_AI_Trade/issues/11)  
**Related Docs:** [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md), [00_GOVERNANCE/principles.md](principles.md), [00_GOVERNANCE/vision.md](vision.md), [03_KNOWLEDGE/knowledge-lineage.md](../03_KNOWLEDGE/knowledge-lineage.md)  

---

## 1. 市場・データに関する前提

- **A001: 対象市場の流動性**
  - 対象銘柄（Core: BTC/USDT等の主要暗号資産、Extended: 主要為替ペア）は十分な流動性を持ち、当システムの注文サイズでは板に重大なマーケットインパクトを与えないと仮定する。
- **A002: データの時間的一貫性**
  - 過去のOHLCVデータおよび将来のデータ取得において、タイムスタンプおよびバーの区切り（UTC基準）が厳密に一致しており、欠損バーは適切に穴埋めまたは除外処理されていると仮定する。
- **A003: 価格系テクニカル指標の情報量（Signal-to-Noise Ratio）の制約**
  - 単一足の価格指標（SMA, BB, Stoch等）単体はノイズ比率が極めて高く、摩擦コスト（0.40%）を上回るエッジを単独では提供できないことが過去実験で確認されている（根拠: [03_KNOWLEDGE/knowledge-lineage.md](../03_KNOWLEDGE/knowledge-lineage.md) K-004、[decision-log.md](../99_HISTORY/decision-log.md) D003）。したがって、多時間軸構造（MTF）または代替データの複合が不可欠であると前提する。

---

## 2. 取引・執行コストに関する前提

- **A004: 摩擦コストの許容上限**
  - 対象市場における実際の往復コスト（取引手数料＋スプレッド＋スリッページ）は、[02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) で規定する標準摩擦コスト（往復 0.40%）の範囲内に収まると仮定する。
  - 実環境におけるコストがこれを恒常的に上回る場合、エッジの成立基盤が崩れるため戦略の再検証を要する。
- **A005: 執行可能性（Fillability）**
  - 成行注文（Market Order）は即座に直前クローズまたは次バーオープン価格にスリッページを加えた価格で約定し、指値注文（Limit Order）はバーの安値/高値が指値価格をクロスした場合にのみ約定すると仮定する。

---

## 3. リサーチ・市場環境に関する前提

- **A006: 非定常性の存在**
  - 市場のボラティリティやトレンド特性は常に遷移する。単一の静的パラメータが全期間で均一に機能することは期待せず、レジームやボラティリティ状態による条件付き評価を行う。
  - ※ 評価におけるデータ期間分割（Discovery/Validation/Holdout）の規律は [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) §2 を参照。

---

## 4. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-09 | 0.1.0 | 初版作成（A001〜A006 定義） | @makagi / [#16](https://github.com/makagi/MTF_AI_Trade/pull/16) |
| 2026-10-13 | 0.1.1 | 科学的根拠リンク追記（K-004, D003 出典） | @makagi / [#29](https://github.com/makagi/MTF_AI_Trade/pull/29) |
| 2026-10-13 | 0.2.0 | 書式・メタデータヘッダー規約統一（Accepted へ昇格） | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
