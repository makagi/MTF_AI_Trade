# MTFシステムトレード Market Regime (市場レジーム概念モデル)

**Doc ID:** CONC-RGM-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-12  
**Related Issues:** [#5](https://github.com/makagi/MTF_AI_Trade/issues/5)  
**Related Docs:** [00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md), [volatility.md](volatility.md), [02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md)  

---

## 1. Purpose

本ドキュメントは、市場の非定常性（Non-stationarity）および市場局面（Regime）の概念、分類モデル、およびレジームがトレードの優位性に与える影響を定義する。

特定パラメータや個別の閾値（Specification）に依存せず、市場環境の変化をいかにモデル化して捉えるかを規定する。

---

## 2. Core Concept: Non-Stationary Markets (非定常市場)

市場の統計的性質（期待値、分散、自己相関、シグナルの有効性）は時間とともに変化する。

「すべての局面で永続的に機能する単一の売買ルール」は存在しない。  
ある期間や環境で機能した戦略も、市場レジームの変化によって急速に優位性（エッジ）を失う、あるいは損失要因へと転じる。

したがって、本システムでは**「現在の市場がどのレジームにあるか」を特定した上で、局面に応じた優位性を評価する**ことを基本思想とする。

---

## 3. Two-Dimensional Regime Model (直交2軸レジームモデル)

市場状態を直交する2つの基本軸（方向性と変動性）によってモデル化する。

```text
               ボラティリティ (Volatility)
                     高 (High Vol)
                          │
       High-Vol Range     │     High-Vol Trend
       (乱高下・拡散)     │     (強いトレンド・推進)
                          │
  ────────────────────────┼──────────────────────── 方向性 (Direction)
  レンジ (Range)          │          トレンド (Trend)
                          │
       Low-Vol Range      │     Low-Vol Trend
       (保ち合い・圧縮)   │     (緩やかなトレンド・登攀)
                          │
                     低 (Low Vol)
```

### 3.1 方向性軸 (Trend vs Range)
* **Trend（トレンド相場モデル）**:
  * 価格が一貫した方向へ推進している状態。
  * 順張り（モメンタム追随・ブレイクアウト）の期待値が高まりやすく、逆張りは致命的なドローダウンを招きやすいという作業仮説。
* **Range（レンジ相場モデル）**:
  * 価格が特定の境界内で往復運動している状態。
  * 平均回帰（Mean Reversion）の期待値が高まりやすく、ブレイクアウトはダマシ（False Breakout）となりやすいという作業仮説。

### 3.2 変動性軸 (High Volatility vs Low Volatility)
* **High Volatility（高ボラティリティモデル）**:
  * 価格変動幅が大きく、ノイズやスリッページが拡大する局面。
  * 利食い余地が広がる反面、ストップ狩りや急速な反転リスクが高まる。
* **Low Volatility（低ボラティリティモデル）**:
  * 変動が沈静化し、エネルギーが蓄積されている局面。
  * ノイズが小さいが、ボラティリティ拡大（Expansion）への前兆段階でもある。

---

## 4. MTF Perspective on Regimes (多時間軸レジーム相互作用)

レジーム認識は単一の時間軸で完結しない。  
上位足と下位足で異なるレジームが重なり合うことで、複合的な市場状態が形成される。

* **上位トレンド × 下位レンジ**:
  * 上位足の押し目・戻り目形成（トレンド継続のセットアップ待機状態）。
* **上位レンジ × 下位トレンド**:
  * レンジの境界から境界への移動波（レンジ内スイング波）。
* **上位・下位の同調トレンド**:
  * 推進力が強まりやすい局面（ただし過熱と急反転に注意が必要）。

---

## 5. Principles of Regime Application (レジーム適用の原則)

1. **レジーム別エッジの検証**:
   * バックテストや実験を行う際は、常に全期間の合算成績だけでなく「どのレジームで期待値がプラスだったか」を分解して評価する（[02_SPECIFICATIONS/evaluation.md](../02_SPECIFICATIONS/evaluation.md) SPEC-EVAL-001 準拠）。
2. **過学習の回避**:
   * レジームを細分化しすぎると、サンプルサイズが枯渇し過剰適合（Overfitting）を招く。最小限で本質的な軸に限定する（[00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md) §8 Simplicity 準拠）。
3. **レジーム転換の遅延認識**:
   * レジームの移行判定には一定の遅延（ラグ）が不可避であることを織り込み、境界付近での過剰なポジション反転を避ける。

---

## 6. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-09 | 0.1.0 | 初版作成（市場レジームモデル、4分類の定義） | @makagi / [#16](https://github.com/makagi/MTF_AI_Trade/pull/16) |
| 2026-10-12 | 0.2.0 | 仕様記述分離、作業仮説表現への純化 | @makagi / [#24](https://github.com/makagi/MTF_AI_Trade/pull/24) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
