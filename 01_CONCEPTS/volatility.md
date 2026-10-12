# MTFシステムトレード Volatility (ボラティリティ概念モデル)

**Doc ID:** CONC-VOL-001  
**Version:** 0.2.0  
**Status:** Accepted  
**Owner:** @makagi  
**Last Updated:** 2026-10-12  
**Related Issues:** [#5](https://github.com/makagi/MTF_AI_Trade/issues/5)  
**Related Docs:** [00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md), [mtf-framework.md](mtf-framework.md), [market-regime.md](market-regime.md)  

---

## 1. Purpose

本ドキュメントは、市場におけるボラティリティの性質、収縮（Squeeze）と拡散（Expansion）の周期的サイクル、およびボラティリティを用いた正規化（スケール不変性）の概念を定義する。

具体的な計算式や指標パラメータ（Specification）に依存せず、価格変動性を市場認識およびリスク管理の基軸としてどう捉えるかを規定する。

---

## 2. The Volatility Cycle (Squeeze & Expansion サイクルモデル)

ボラティリティはランダムに変動するだけでなく、**「収縮（エネルギー蓄積）」と「拡散（エネルギー解放）」を周期的に繰り返す傾向** を持つ。

```text
       ┌───────────┐           ┌───────────┐
       │ Squeeze   │ ───────→  │ Expansion │
       │ (収縮・沈静)│           │ (拡散・急変)│
       └─────┬─────┘           └─────┬─────┘
             ↑                       │
             └───────────────────────┘
```

1. **Squeeze（収縮・エネルギー蓄積モデル）**:
   * 変動幅が狭まり、取引レンジが圧縮される状態。
   * 市場参加者の確信が拮抗、または流動性が低下している局面。
   * 「圧縮期間が長いほど、次の解放時に大きなボラティリティ拡散が生じやすい」という作業仮説を持つ。
2. **Expansion（拡散・エネルギー解放モデル）**:
   * 収縮の境界をブレイクし、価格が急激に動意づく状態。
   * トレンドの初動、またはストップ注文を巻き込んだ乱高下が発生する。
   * 拡散が一定の極値に達すると過熱状態となり、再び収縮へ向かうという見方。

---

## 3. Scale-Invariance via Volatility Normalization (スケール不変性)

価格の絶対値（例: ビットコインが $10,000 か $60,000 か）は、市場のレジームや時代によって大きく異なる。  
固定された絶対値幅による判定は、過去データと現在データの比較を歪め、過学習を招く。

本システムでは、すべての価格変動幅・乖離度・サポレジ距離を**ボラティリティ単位（ATR等の変動性指標）で正規化**し、**スケール不変（Scale-Invariant）** な尺度として捉える。

```text
正規化距離 = (観測価格 - 基準価格) / Volatility
```

これにより、高価格帯でも低価格帯でも、同一の相対的意味（例:「一定のボラティリティ幅に相当する乖離」）として普遍的に比較・評価することが可能となる。

---

## 4. MTF Volatility Dynamics (時間軸間のボラティリティ相互作用)

ボラティリティもまた、時間軸によって異なる振る舞いを示す。

* **上位足のSqueeze × 下位足のExpansion**:
  * 上位足の狭いレンジ内で下位足が往復するノイズ局面。下位足ブレイクはダマシになりやすいと解釈する。
* **上位足のSqueeze終了 × 下位足の同調Expansion**:
  * 上位足のエネルギー解放に伴う本格的なマクロトレンドの初動。優位性が生じやすい作業仮説局面として注目する。
* **上位足のExpansion末期**:
  * 拡散が過熱し、上位足での平均回帰（Mean Reversion）や再収縮が近づいている状態と推論する。

---

## 5. Volatility as a Risk and Execution Filter (リスク・執行フィルター概念)

1. **ボラティリティに応じたセットアップ待機**:
   * 無秩序な拡散の最中に飛び乗るのではなく、圧縮から初期拡散へ向かう瞬間をセットアップ待機（仕様上の Armed 状態に相当）として捉える。
2. **動的ポジションサイジング**:
   * ボラティリティが高い局面ではポジションサイズを抑制し、ボラティリティが低い局面では適正サイズを確保することで、市場全体でのリスク露出度を一定に保つ（[00_GOVERNANCE/principles.md](../00_GOVERNANCE/principles.md) §1 Risk First 準拠）。

※ 具体的なボラティリティ計算指標（ATR期間等）やサイジング係数は仕様（[02_SPECIFICATIONS/](../02_SPECIFICATIONS/)）で規定する。

---

## 6. Change History

| 日付 | Version | 変更概要 | 担当者 / PR |
|---|---|---|---|
| 2026-10-09 | 0.1.0 | 初版作成（ボラティリティ概念、Squeeze/Expansion サイクル） | @makagi / [#16](https://github.com/makagi/MTF_AI_Trade/pull/16) |
| 2026-10-12 | 0.2.0 | 仕様記述分離、作業仮説表現への純化 | @makagi / [#24](https://github.com/makagi/MTF_AI_Trade/pull/24) |
| 2026-10-13 | 0.2.0 | 書式・メタデータ統一 | @makagi / [#31](https://github.com/makagi/MTF_AI_Trade/pull/31) |
