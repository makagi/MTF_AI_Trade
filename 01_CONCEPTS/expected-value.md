# MTFシステムトレード Expected Value

**Doc ID:** CONCEPT-EXP-001  
**Version:** 0.1.0  
**Status:** Draft  
**Owner:** @makagi  
**Last Updated:** 2026-10-10  
**Related Issues:** [#4](https://github.com/makagi/MTF_AI_Trade/issues/4)  
**Related Docs:** [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md), [00_GOVERNANCE/assumptions.md](../00_GOVERNANCE/assumptions.md)  

---

## 1. Purpose

本ドキュメントは、トレード戦略の優位性（エッジ）を測るための数学的尺度である「期待値（Expected Value）」、非対称なリスク・リターン関係、および市場の摩擦コスト（Friction Costs）の概念を定義する。

---

## 2. Expected Value vs Prediction Accuracy

システムトレードの成否は「未来の価格が上がるか下がるかを当てる確率（勝率・予測精度）」では決まらない。  
**「1回の取引あたりに期待できる数学的純利益（期待値）」** によってのみ決定される。

$$E = (P_{\text{win}} \times W_{\text{avg}}) - (P_{\text{loss}} \times L_{\text{avg}})$$

* $P_{\text{win}}$: 勝率
* $W_{\text{avg}}$: 平均利益
* $P_{\text{loss}}$: 敗率 ($1 - P_{\text{win}}$)
* $L_{\text{avg}}$: 平均損失

勝率が90%であっても、1回の損失が巨大であれば破滅する。  
逆に勝率が30%であっても、平均利益が平均損失の数倍（非対称性）であれば、システムは長期的に莫大な利益を生み出す。

---

## 3. The Reality of Friction Costs (The Friction Wall)

バックテストで机上の利益が出ても、実運用で壊滅する最大の原因は「摩擦コスト」の軽視である。

1. **摩擦コストの構成要素**:
   * **手数料 (Commission / Fee)**: 取引所・ブローカーへの支払い。
   * **スプレッド (Bid-Ask Spread)**: 買値と売値の開き。
   * **スリッページ (Slippage)**: 発注から約定までの価格滑り。
   * **レイテンシ (Latency Delay)**: ネットワーク遅延による機会損失。
2. **コストの蓄積と過剰取引の罠**:
   * 暗号資産や高ボラティリティ商品において、現実的な往復コスト（Taker手数料＋スプレッド＋スリッページ）は無視できない障壁となる。
   * 1回あたりの期待リターンが摩擦コスト未満のシグナルは、どれだけ高頻度に打っても手数料負け（Churn）となり、資産曲線を急速に破壊する。
   * 「微小なエッジを多頻度に回転させる」アプローチは、摩擦コストに耐えうる十分な Signal-to-Noise Ratio がない限り成立しない。
   * ※ 当システムが評価で控除する具体的な摩擦コスト値（往復 0.40%）および内訳モデルは [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) §3 を参照。

---

## 4. Separation of Entry Edge and Exit Logic (MFE / MAE)

エントリー条件自体の真の優位性と、イグジット（利食い・損切りルール）の成否を混同してはならない。

1. **MFE (Maximum Favorable Excursion)**:
   * エントリー後に価格が有利な方向へ最大どこまで動いたか（潜在的利益余地）。
2. **MAE (Maximum Adverse Excursion)**:
   * エントリー後に価格が不利な方向へ最大どこまで逆行したか（潜在的ドローダウンリスク）。

```text
エントリー時点
      │
      ├───→ 最大逆行 (MAE): リスクの深さ・ストップ狩られやすさ
      │
      └───→ 最大順行 (MFE): エッジの大きさ・利食い余地
```

### 評価の順序規律
* **ステップ 1**: まずイグジットルールを適用しない純粋な前向きリターン（Forward Return）および MFE/MAE 分布により、「エントリー自体に有意な偏りがあるか」を計測する。
* **ステップ 2**: エントリーに優位性が確認された後に初めて、MFEのピークを刈り取りMAEの底を避けるイグジット設計を行う。

---

## 5. Asymmetry: Downside Truncation and Upside Convexity

長期的に生き残り利益を最大化するための唯一の構造は、**リスクリターンの非対称性（コンベキシティ: 凸性）** である。

* **下方リスクの厳格な切断 (Downside Truncation)**:
  * 致命的なテールリスク（想定外の急変、フラッシュクラッシュ）をストップロスや資金管理により確実に遮断する。
* **上方利益の追求 (Upside Convexity)**:
  * トレンドの伸張やボラティリティ拡散局面において、利益を固定幅で早期に手仕舞いせず、波の終焉まで追随する。
