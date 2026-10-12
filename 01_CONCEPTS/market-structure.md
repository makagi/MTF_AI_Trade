# MTFシステムトレード Market Structure (市場構造概念モデル)

**Doc ID:** CONC-STR-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-12  
**Related Issues:** [#5](https://github.com/makagi/MTF_AI_Trade/issues/5)  
**Related Docs:** [00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md), [mtf-framework.md](mtf-framework.md), [volatility.md](volatility.md)  

---

## 1. Purpose

本ドキュメントは、市場構造（Market Structure）、支持帯・抵抗帯（Support & Resistance）、流動性（Liquidity）、およびスイングの高値・安値に関する普遍的な相場概念を定義する。

特定パラメータや個別の数値（Specification）に依存せず、市場参加者の注文分布と価格相互作用をどう捉えるかを規定する。

---

## 2. Dynamic Support & Resistance (動的サポレジ領域)

従来のテクニカル分析では、サポレジを「永続的に機能する静的な水平線」と捉えがちである。  
しかし、本システムではサポレジを**「注文の集積と流動性の供給・吸収によって動的に変化する領域」** として理解する。

```text
       アタック 1回目          アタック 2回目          アタック 3回目
         (強反発)               (反発小)             (ブレイク / 貫通)
           ▲                       ▲                       │
           │                       │                       ▼
   ─────────────────────────────────────────────────────────────── 抵抗帯 (Resistance)
   [厚い指値注文]        →   [注文の消費]       →   [流動性の枯渇]
```

1. **アタック回数と流動性消費モデル**:
   * 同じサポレジ水準が何度もテストされるほど、そこに置かれていた防戦注文（流動性）が消費され、反発力は低下しブレイク確率が高まるというモデル。
2. **時間経過による陳腐化 (Decay)**:
   * 過去に形成されたサポレジも、時間が経過するにつれて市場参加者の関心が薄れ、その境界としての影響力は減衰する。
3. **ロールリバーサル (Role Reversal)**:
   * 支持帯が明確にブレイクされた場合、そこは新たな抵抗帯へと役割が転換する（逆も同様）。

---

## 3. Swing High / Swing Low and Directional Flow (スイング構造と方向性)

市場の構造は、スイングの高値（Swing High）と安値（Swing Low）の連続的な更新関係によってモデル化される。

* **Bullish Structure（上昇構造）**:
  * 高値切り上げ（Higher High: HH）と安値切り上げ（Higher Low: HL）が継続している状態。
* **Bearish Structure（下降構造）**:
  * 高値切り下げ（Lower High: LH）と安値切り下げ（Lower Low: LL）が継続している状態。
* **Structure Shift（構造破壊 / 転換）**:
  * 直近のスイング安値（Bullish時）または直近のスイング高値（Bearish時）をブレイクすることで、構造転換（トレンド終了・反転）が示唆されるという見方。

---

## 4. Liquidity Pools and False Breakouts (流動性プールとダマシ)

市場参加者の損切り注文（ストップロス）は、顕著なスイング高値の上やスイング安値の下に集中する（流動性プール: Liquidity Pool）。

1. **ストップ狩り（Liquidity Grab / Sweep）**:
   * 大口参加者が自身のポジションを約定させるため、意図的に境界線を一時的にブレイクさせ、滞留するストップ注文を巻き込んだ後に急反転する現象。
2. **ダマシの識別と作業仮説**:
   * 単なるヒゲによる一時的な境界突破と、実体を伴う終値ベースの定着を区別する。
   * 下位足でのブレイクであっても、上位足の強力なサポレジの壁（マクロ重力）に衝突している場合は、ダマシ（False Breakout）となるリスクが高まりやすいという作業仮説を持つ。

---

## 5. Moving Averages as Dynamic Structure (動的構造としての移動平均線)

移動平均線（SMA等）もまた、静的な線ではなく動的な支持・抵抗・引き寄せの場として機能する。

* **ファンアウト（拡散）と収束**:
  * 複数期間の移動平均線の乖離速度は、トレンドの勢い（モメンタム）と減速を先行して反映する見方。
* **ボラティリティ乖離の限界（磁石効果モデル）**:
  * 価格が移動平均からボラティリティ換算で統計的な極値まで乖離した場合、過度な売られすぎ・買われすぎとして平均へ回帰する圧力（Mean Reversion Power）が高まるという仮説。  
  ※ 具体的な乖離閾値や回帰判定ロジックは、個別仕様（[02_SPECIFICATIONS/](../02_SPECIFICATIONS/)）および検証実験（[03_KNOWLEDGE/](../03_KNOWLEDGE/)）の対象とする。

---

## 6. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-09 | 0.1.0 | 初版作成（市場構造概念モデル、サポレジ、Liquidity） | @makagi / [#16](https://github.com/makagi/MTF_AI_Trade/pull/16) |
| 2026-10-12 | 0.2.0 | 仕様記述分離、作業仮説表現への純化 | @makagi / [#24](https://github.com/makagi/MTF_AI_Trade/pull/24) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
